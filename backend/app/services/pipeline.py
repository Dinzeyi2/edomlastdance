"""Orchestrates one full analysis: imagery -> footprint -> defect detection
-> (temporal diff, if compare_year given) -> scoring -> storage upload.
Used by both POST /analyze (runs this inline, synchronously) and the Celery
task behind POST /analyze/async (runs this, then persists progress/result to
the Job row as it goes) -- one implementation, two callers, matching the
"single backend, not two pipelines" goal.
"""
import io
from collections.abc import Awaitable, Callable

from PIL import Image

from app.schemas.analyze import AnalysisResult, Finding, ImageUrls, TemporalComparison
from app.services.defects import get_defect_detector
from app.services.footprint import building_id_for, get_footprint_provider
from app.services.footprint_cache import get_cached_footprint, save_footprint_cache
from app.services.imagery import get_imagery_provider
from app.services.scoring import compute_score, get_reasoning_provider
from app.services.storage import get_storage_service, new_object_key
from app.services.temporal import compute_diff_heatmap, compute_temporal

GRID_SIZE = 3
ProgressCallback = Callable[[float, str], Awaitable[None]]


def _crop_and_grid(image_bytes: bytes, bbox: tuple[float, float, float, float]) -> tuple[bytes, list[bytes]]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    x0, y0, x1, y1 = bbox
    crop = img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    cw, ch = crop.size

    tiles: list[bytes] = []
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            tile = crop.crop((col * cw // GRID_SIZE, row * ch // GRID_SIZE, (col + 1) * cw // GRID_SIZE, (row + 1) * ch // GRID_SIZE))
            buf = io.BytesIO()
            tile.save(buf, format="PNG")
            tiles.append(buf.getvalue())

    crop_buf = io.BytesIO()
    crop.save(crop_buf, format="PNG")
    return crop_buf.getvalue(), tiles


async def run_analysis(
    *,
    job_id: str,
    lat: float,
    lng: float,
    compare_year: int | None,
    resolution_cm: int,
    include_raw_tiles: bool,
    on_progress: ProgressCallback | None = None,
) -> AnalysisResult:
    async def progress(p: float, stage: str) -> None:
        if on_progress:
            await on_progress(p, stage)

    await progress(0.05, "fetching_imagery")
    imagery = get_imagery_provider()
    current_img = await imagery.fetch_image(lat, lng, resolution_cm)

    previous_img = None
    if compare_year:
        previous_img = await imagery.fetch_image(lat, lng, resolution_cm, year=compare_year)

    await progress(0.25, "footprint_masking")
    footprint = await get_cached_footprint(lat, lng)
    if footprint is None:
        footprint = await get_footprint_provider().get_footprint(lat, lng)
        await save_footprint_cache(lat, lng, footprint)
    building_id = building_id_for(lat, lng)
    masked_bytes, tiles = _crop_and_grid(current_img.image_bytes, footprint.bbox)

    await progress(0.45, "defect_detection")
    detector = get_defect_detector()
    current_findings = await detector.detect(masked_bytes)
    current_score = compute_score(current_findings)

    temporal = None
    prev_masked_bytes = None
    if previous_img:
        await progress(0.6, "temporal_comparison")
        prev_masked_bytes, _ = _crop_and_grid(previous_img.image_bytes, footprint.bbox)
        previous_findings = await detector.detect(prev_masked_bytes)
        previous_score = compute_score(previous_findings)
        temporal = compute_temporal(current_score, current_findings, previous_score, previous_findings)

    await progress(0.78, "scoring")
    reasoning = await get_reasoning_provider().refine(current_score, current_findings)
    final_score = reasoning.score if reasoning else current_score.score
    final_condition = reasoning.condition if reasoning else current_score.condition
    final_confidence = reasoning.confidence if reasoning else current_score.confidence

    await progress(0.9, "uploading_evidence")
    storage = get_storage_service()
    image_urls = ImageUrls(masked=await storage.upload(new_object_key(job_id, "masked"), masked_bytes, "image/png"))
    if include_raw_tiles:
        image_urls.full = await storage.upload(new_object_key(job_id, "full"), current_img.image_bytes, "image/png")
        image_urls.tiles = [
            await storage.upload(new_object_key(job_id, f"tile-{i}"), tile_bytes, "image/png")
            for i, tile_bytes in enumerate(tiles)
        ]
    if prev_masked_bytes is not None:
        heatmap_bytes = compute_diff_heatmap(masked_bytes, prev_masked_bytes)
        image_urls.diff_heatmap = await storage.upload(new_object_key(job_id, "diff-heatmap"), heatmap_bytes, "image/png")

    await progress(1.0, "finalizing")

    return AnalysisResult(
        building_id=building_id,
        score=final_score,
        condition=final_condition,
        confidence=final_confidence,
        resolution_cm=resolution_cm,
        footprint_masked=True,
        imagery_date=current_img.captured_date.isoformat() if current_img.captured_date else None,
        findings=[
            Finding(type=f.type, severity=f.severity, bbox=list(f.bbox), tile_index=list(f.tile_index), confidence=f.confidence)
            for f in current_findings
        ],
        temporal=(
            TemporalComparison(
                previous_score=temporal.previous_score, score_delta=temporal.score_delta, change_summary=temporal.change_summary
            )
            if temporal
            else None
        ),
        image_urls=image_urls,
    )
