"""Building footprint isolation: given the fetched image (+ coordinates),
return the region that's actually roof, so the defect detector isn't looking
at trees/street/neighbors. Three tiers, matching the order you laid out:

  1. center_crop (default): a fixed inset rectangle. This is deliberately the
     "simple center-crop" you described replacing -- it's the honest
     baseline every request can use with zero dependencies.
  2. osm: a real building polygon from OpenStreetMap via the public Overpass
     API (free, no key). Implemented for real below -- BUT this sandbox's
     network egress policy blocks overpass-api.de (confirmed: 403 from the
     egress proxy), so I could not execute a live call to verify it. It
     should work once deployed on Railway (which has normal internet
     egress); worth a smoke test right after deploy.
  3. sam2: real zero-shot pixel segmentation against Meta's SAM-2 model.
     Needs a GPU worker (see Dockerfile.worker) -- the checkpoint's host is
     blocked from the dev/CI sandbox this was built in, so the model-loading
     and inference path is NOT live-verified from here. The mask-to-bbox
     math (_mask_to_bbox) IS unit-tested with a real synthetic mask array,
     independent of the model itself. See docs/sam2-railway-setup.md for
     the deploy steps.

Note OSM gives a real polygon in lat/lng, not pixel coordinates in whatever
image IMAGERY_PROVIDER returned -- projecting a real-world polygon onto an
image requires knowing that image's ground-sample-distance and orientation
(real georeferencing metadata a real imagery vendor would provide). Until a
real imagery provider is wired in, OsmFootprintProvider returns the real
polygon/area (useful for scoring) alongside the same center-crop pixel bbox
used for the placeholder mask image.

get_footprint() takes the fetched image bytes, not just coordinates --
SAM-2 fundamentally needs pixels to segment, so this is a required parameter
even though center_crop/osm ignore it.
"""
import hashlib
import io
import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
import numpy as np
from shapely.geometry import Point, shape

from app.config import get_settings
from app.services.roof_art import SIZE

logger = logging.getLogger(__name__)

CENTER_CROP_MARGIN_PX = 60  # matches the margin used by roof_art.generate_schematic_roof
CENTER_CROP_BBOX = (
    CENTER_CROP_MARGIN_PX / SIZE,
    CENTER_CROP_MARGIN_PX / SIZE,
    (SIZE - CENTER_CROP_MARGIN_PX) / SIZE,
    (SIZE - CENTER_CROP_MARGIN_PX) / SIZE,
)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_SEARCH_RADIUS_M = 40
OVERPASS_TIMEOUT_S = 20.0


def building_id_for(lat: float, lng: float) -> str:
    """Deterministic stable ID for a building, from rounded coordinates
    (~0.1m precision at 6 decimals) so repeat requests for the same address
    resolve to the same building_id."""
    key = f"{round(lat, 6)},{round(lng, 6)}"
    return "bld_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass
class FootprintResult:
    bbox: tuple[float, float, float, float]  # normalized (x0, y0, x1, y1)
    polygon_geojson: str | None  # real lat/lng polygon, when available (osm)
    area_sqm: float | None
    source: str


class FootprintProvider(ABC):
    @abstractmethod
    async def get_footprint(self, lat: float, lng: float, image_bytes: bytes) -> FootprintResult:
        raise NotImplementedError


class CenterCropProvider(FootprintProvider):
    async def get_footprint(self, lat: float, lng: float, image_bytes: bytes) -> FootprintResult:
        return FootprintResult(
            bbox=CENTER_CROP_BBOX, polygon_geojson=None, area_sqm=None, source="center_crop"
        )


class OsmFootprintProvider(FootprintProvider):
    """Queries the public Overpass API for a `building` way within
    OVERPASS_SEARCH_RADIUS_M of the point, picks the one whose polygon
    actually contains the point (Overpass's `around` filter is a bounding
    search, not a strict containment check), and returns its real polygon +
    area. Falls back to the center-crop bbox for the placeholder mask image
    since we don't have georeferenced imagery to project onto yet -- see the
    module docstring.
    """

    async def get_footprint(self, lat: float, lng: float, image_bytes: bytes) -> FootprintResult:
        query = (
            f"[out:json][timeout:{int(OVERPASS_TIMEOUT_S)}];"
            f"way(around:{OVERPASS_SEARCH_RADIUS_M},{lat},{lng})[building];"
            "out geom;"
        )
        async with httpx.AsyncClient(timeout=OVERPASS_TIMEOUT_S) as client:
            resp = await client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            payload = resp.json()

        point = Point(lng, lat)
        for element in payload.get("elements", []):
            geometry = element.get("geometry")
            if not geometry:
                continue
            coords = [(node["lon"], node["lat"]) for node in geometry]
            if coords[0] != coords[-1]:
                coords.append(coords[0])  # close the ring
            polygon = shape({"type": "Polygon", "coordinates": [coords]})
            if polygon.contains(point) or polygon.touches(point):
                # Shapely area is in degrees^2 for lon/lat geometry -- rough
                # meters^2 conversion at this latitude, fine for an estimate.
                meters_per_degree_lat = 111_320
                meters_per_degree_lng = 111_320 * abs(math.cos(math.radians(lat)))
                area_sqm = polygon.area * meters_per_degree_lat * meters_per_degree_lng
                return FootprintResult(
                    bbox=CENTER_CROP_BBOX,
                    polygon_geojson=json.dumps({"type": "Polygon", "coordinates": [coords]}),
                    area_sqm=round(area_sqm, 1),
                    source="osm",
                )

        logger.warning("no OSM building found within %sm of (%s, %s), falling back to center_crop", OVERPASS_SEARCH_RADIUS_M, lat, lng)
        return FootprintResult(bbox=CENTER_CROP_BBOX, polygon_geojson=None, area_sqm=None, source="osm_fallback")


def _mask_to_bbox(mask: np.ndarray) -> tuple[float, float, float, float]:
    """Convert a boolean segmentation mask to a normalized (x0, y0, x1, y1)
    bbox -- the existing crop/tile pipeline (app/services/pipeline.py) works
    in bbox terms, not arbitrary polygons, so this is the bridge between a
    real per-pixel mask and that pipeline. Pure numpy, no SAM-2 dependency --
    fully unit-testable without the model itself, see tests/test_sam2_footprint.py.
    Falls back to the center-crop bbox if the mask is empty (SAM-2 found
    nothing at the prompt point).
    """
    h, w = mask.shape
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return CENTER_CROP_BBOX
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return (round(x0 / w, 4), round(y0 / h, 4), round((x1 + 1) / w, 4), round((y1 + 1) / h, 4))


class Sam2FootprintProvider(FootprintProvider):
    """Real zero-shot segmentation against Meta's SAM-2. Loads the model once
    per worker process (class-level cache, same pattern as
    app/services/defects.py's YoloDefectDetector), prompts it with the image
    center point (the imagery provider is expected to center the frame on
    the requested lat/lng, so the building of interest should be roughly
    centered), takes the highest-scoring of SAM-2's returned masks, and
    converts it to a bbox via _mask_to_bbox.

    Needs SAM2_CHECKPOINT_PATH (a downloaded .pt file, e.g.
    sam2_hiera_large.pt) and the real `sam2` + `torch` packages -- deliberately
    NOT in the base requirements.txt (multi-GB, GPU-oriented), see
    requirements-gpu.txt and Dockerfile.worker. IMPORTANT: `pip install sam2`
    installs an unrelated third party's PyPI upload, not Meta's package --
    confirmed by downloading and inspecting it (see requirements-gpu.txt).
    Install from Meta's actual repo instead.

    build_sam2()'s config_file argument (SAM2_CONFIG_NAME) is confirmed
    correct by reading the real build_sam.py source directly (its
    HF_MODEL_ID_TO_FILENAMES table) -- default is
    "configs/sam2/sam2_hiera_l.yaml", matching the sam2_hiera_large.pt
    checkpoint. NOT live-verified: model loading and inference themselves,
    since this was written in a sandbox whose network egress blocks the
    checkpoint's host (dl.fbaipublicfiles.com), so no checkpoint could be
    downloaded to actually run this here. The non-model-dependent part
    (_mask_to_bbox) is unit-tested for real.
    """

    _model = None  # class-level: loaded once per worker process, not per-request

    def _load_predictor(self):
        if Sam2FootprintProvider._model is not None:
            return Sam2FootprintProvider._model

        settings = get_settings()
        if not settings.sam2_checkpoint_path:
            raise RuntimeError(
                "FOOTPRINT_PROVIDER=sam2 requires SAM2_CHECKPOINT_PATH to point at a "
                "downloaded SAM-2 checkpoint (e.g. sam2_hiera_large.pt). "
                "Set FOOTPRINT_PROVIDER=center_crop or =osm for now."
            )
        try:
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
        except ImportError as exc:
            raise RuntimeError(
                "FOOTPRINT_PROVIDER=sam2 requires the `sam2` package plus torch "
                "(pip install -r requirements-gpu.txt) -- not installed by default, "
                "see Dockerfile.worker."
            ) from exc

        sam2_model = build_sam2(settings.sam2_config_name, settings.sam2_checkpoint_path, device=settings.sam2_device)
        Sam2FootprintProvider._model = SAM2ImagePredictor(sam2_model)
        return Sam2FootprintProvider._model

    async def get_footprint(self, lat: float, lng: float, image_bytes: bytes) -> FootprintResult:
        import asyncio

        predictor = self._load_predictor()
        # torch inference is sync/blocking -- run off the event loop so it
        # doesn't stall other requests/tasks in the same process.
        return await asyncio.to_thread(self._segment, predictor, image_bytes)

    @staticmethod
    def _segment(predictor, image_bytes: bytes) -> FootprintResult:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)
        h, w = arr.shape[:2]

        predictor.set_image(arr)
        center_point = np.array([[w // 2, h // 2]])
        center_label = np.array([1])  # 1 = foreground prompt

        masks, scores, _ = predictor.predict(
            point_coords=center_point, point_labels=center_label, multimask_output=True
        )
        best_mask = masks[int(np.argmax(scores))].astype(bool)

        return FootprintResult(bbox=_mask_to_bbox(best_mask), polygon_geojson=None, area_sqm=None, source="sam2")


_PROVIDERS = {
    "center_crop": CenterCropProvider,
    "osm": OsmFootprintProvider,
    "sam2": Sam2FootprintProvider,
}


def get_footprint_provider() -> FootprintProvider:
    return _PROVIDERS[get_settings().footprint_provider]()
