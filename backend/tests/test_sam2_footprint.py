"""Tests the parts of Sam2FootprintProvider that don't need the actual SAM-2
model: _mask_to_bbox's pure numpy math (real, unit-tested against real mask
arrays) and the missing-checkpoint error path. The model-loading/inference
path itself is NOT tested here -- see the module docstring in
app/services/footprint.py for exactly why (checkpoint host blocked from this
sandbox). tests/test_yolo_detector_optional.py is the pattern for what a
"real model, optional test" looks like when the weights ARE reachable;
apply the same pattern once you can download a SAM-2 checkpoint somewhere
this can reach.
"""
import numpy as np
import pytest

from app.services.footprint import CENTER_CROP_BBOX, Sam2FootprintProvider, _mask_to_bbox


def test_mask_to_bbox_exact_rectangle():
    mask = np.zeros((100, 200), dtype=bool)
    mask[10:30, 40:80] = True  # rows 10-29, cols 40-79

    x0, y0, x1, y1 = _mask_to_bbox(mask)

    assert x0 == pytest.approx(40 / 200)
    assert x1 == pytest.approx(80 / 200)
    assert y0 == pytest.approx(10 / 100)
    assert y1 == pytest.approx(30 / 100)


def test_mask_to_bbox_full_image():
    mask = np.ones((50, 50), dtype=bool)
    x0, y0, x1, y1 = _mask_to_bbox(mask)
    assert (x0, y0, x1, y1) == (0.0, 0.0, 1.0, 1.0)


def test_mask_to_bbox_single_pixel():
    mask = np.zeros((10, 10), dtype=bool)
    mask[5, 5] = True
    x0, y0, x1, y1 = _mask_to_bbox(mask)
    assert x0 == pytest.approx(0.5)
    assert y0 == pytest.approx(0.5)
    assert x1 == pytest.approx(0.6)
    assert y1 == pytest.approx(0.6)


def test_mask_to_bbox_empty_mask_falls_back_to_center_crop():
    mask = np.zeros((50, 50), dtype=bool)
    assert _mask_to_bbox(mask) == CENTER_CROP_BBOX


def test_mask_to_bbox_output_is_always_normalized():
    rng = np.random.default_rng(42)
    for _ in range(20):
        h, w = rng.integers(10, 500), rng.integers(10, 500)
        mask = rng.random((h, w)) > 0.7
        x0, y0, x1, y1 = _mask_to_bbox(mask)
        assert 0 <= x0 <= x1 <= 1
        assert 0 <= y0 <= y1 <= 1


async def test_missing_checkpoint_path_raises_clear_error(monkeypatch):
    monkeypatch.setenv("SAM2_CHECKPOINT_PATH", "")
    from app.config import get_settings

    get_settings.cache_clear()
    Sam2FootprintProvider._model = None
    try:
        with pytest.raises(RuntimeError, match="SAM2_CHECKPOINT_PATH"):
            await Sam2FootprintProvider().get_footprint(1.0, 1.0, b"fake-image-bytes")
    finally:
        get_settings.cache_clear()
