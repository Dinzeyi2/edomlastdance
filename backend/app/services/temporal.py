"""Temporal change detection: compare a current analysis against a prior
year's. Pure logic, no external calls -- real code, not a stub, since it
doesn't depend on anything not already available (imagery + detector +
scorer results for both years).

Also generates the diff heatmap your spec called for: a per-pixel visual of
where the two images differ, not just a text summary. Real image processing
(numpy + OpenCV's colormap), not a placeholder -- see compute_diff_heatmap.
No image registration/alignment step: the mock imagery provider returns
same-size, same-framing images for a given lat/lng regardless of year (it's
synthetic, not a real photo with perspective differences), so pixel-aligned
diffing is valid as-is. A real imagery vendor with actual perspective/zoom
variance between captures would need alignment (e.g. feature matching) added
here before diffing -- flagged, not implemented, since there's no real
misaligned imagery to test it against yet.
"""
import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from app.services.defects import DefectFinding
from app.services.scoring import ScoreResult

WORSENED_THRESHOLD = -5
IMPROVED_THRESHOLD = 5


@dataclass
class TemporalResult:
    previous_score: int | None
    score_delta: int | None
    change_summary: str


def compute_temporal(
    current_score: ScoreResult,
    current_findings: list[DefectFinding],
    previous_score: ScoreResult | None,
    previous_findings: list[DefectFinding] | None,
) -> TemporalResult:
    if previous_score is None:
        return TemporalResult(
            previous_score=None, score_delta=None, change_summary="No prior-year imagery available for comparison."
        )

    delta = current_score.score - previous_score.score
    current_types = {f.type for f in current_findings}
    previous_types = {f.type for f in (previous_findings or [])}
    new_types = sorted(current_types - previous_types)

    if new_types:
        summary = f"New {', '.join(new_types)} visible since prior imagery."
    elif delta <= WORSENED_THRESHOLD:
        summary = "Existing damage appears to have worsened since prior imagery."
    elif delta >= IMPROVED_THRESHOLD:
        summary = "Roof condition appears improved since prior imagery (repair or replacement likely)."
    else:
        summary = "No significant change detected since prior imagery."

    return TemporalResult(previous_score=previous_score.score, score_delta=delta, change_summary=summary)


def compute_diff_heatmap(current_image_bytes: bytes, previous_image_bytes: bytes) -> bytes:
    """Per-pixel absolute difference between the two (already same-crop)
    images, rendered as a JET colormap heatmap PNG -- blue/green = little
    change, red = large change. Real pixel math, not a mock."""
    current = np.array(Image.open(io.BytesIO(current_image_bytes)).convert("RGB"))
    previous = np.array(Image.open(io.BytesIO(previous_image_bytes)).convert("RGB"))
    if current.shape != previous.shape:
        previous = np.array(
            Image.fromarray(previous).resize((current.shape[1], current.shape[0]))
        )

    diff = np.abs(current.astype(np.int16) - previous.astype(np.int16)).sum(axis=2)
    diff_normalized = np.clip(diff, 0, 255).astype(np.uint8)
    heatmap_bgr = cv2.applyColorMap(diff_normalized, cv2.COLORMAP_JET)
    heatmap_rgb = cv2.cvtColor(heatmap_bgr, cv2.COLOR_BGR2RGB)

    buf = io.BytesIO()
    Image.fromarray(heatmap_rgb).save(buf, format="PNG")
    return buf.getvalue()
