"""Exercises the real pixel-CV path in RuleBasedDefectDetector -- these are
regression tests for the edge-artifact bug caught while building this (roof
texture/border lines were getting flagged as defects; see
app/services/roof_art.py's comments).

All tests crop to the roof bbox first, same as app/services/pipeline.py does
before ever calling the detector -- feeding it the full, uncropped image
(which includes the yard background) is not how it's actually used and
produces a different, expected result (the yard registers as one big
frame-shaped contour around the roof).
"""
from app.services.defects import TAXONOMY, RuleBasedDefectDetector
from app.services.footprint import CENTER_CROP_BBOX
from app.services.roof_art import SIZE, generate_schematic_roof, image_to_png_bytes


def _detector_input(seed: int, num_damage_marks: int) -> bytes:
    img = generate_schematic_roof(seed=seed, num_damage_marks=num_damage_marks)
    x0, y0, x1, y1 = CENTER_CROP_BBOX
    cropped = img.crop((int(x0 * SIZE), int(y0 * SIZE), int(x1 * SIZE), int(y1 * SIZE)))
    return image_to_png_bytes(cropped)


async def test_zero_damage_marks_yields_zero_findings():
    findings = await RuleBasedDefectDetector().detect(_detector_input(seed=1, num_damage_marks=0))
    assert len(findings) == 0


async def test_damage_marks_are_detected():
    findings = await RuleBasedDefectDetector().detect(_detector_input(seed=2, num_damage_marks=15))
    assert len(findings) > 0
    assert len(findings) <= 15  # can't detect more distinct marks than were drawn (touching marks may merge)
    for f in findings:
        assert f.type in TAXONOMY
        assert f.severity in ("minor", "moderate", "severe")
        assert 0 <= f.confidence <= 1
        x0, y0, x1, y1 = f.bbox
        assert 0 <= x0 < x1 <= 1
        assert 0 <= y0 < y1 <= 1


async def test_more_damage_marks_generally_means_more_findings():
    few = await RuleBasedDefectDetector().detect(_detector_input(seed=3, num_damage_marks=3))
    many = await RuleBasedDefectDetector().detect(_detector_input(seed=3, num_damage_marks=20))
    assert len(many) > len(few)


async def test_detection_is_deterministic():
    img_bytes = _detector_input(seed=7, num_damage_marks=10)
    first = await RuleBasedDefectDetector().detect(img_bytes)
    second = await RuleBasedDefectDetector().detect(img_bytes)
    assert [f.type for f in first] == [f.type for f in second]
    assert [f.bbox for f in first] == [f.bbox for f in second]


async def test_uncropped_yard_is_not_mistaken_for_zero_findings():
    """Documents the expected behavior when the detector IS handed an
    uncropped image (which real usage never does): the yard background
    registers as a real anomaly relative to the roof fill color -- this is
    correct contour-detection behavior, not a bug, given that input."""
    full_bytes = image_to_png_bytes(generate_schematic_roof(seed=1, num_damage_marks=0))
    findings = await RuleBasedDefectDetector().detect(full_bytes)
    assert len(findings) == 1
    assert findings[0].bbox == (0.0, 0.0, 1.0, 1.0)
