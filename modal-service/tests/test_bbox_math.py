"""Tests mask_to_bbox -- the one piece of sam2_service.py that's real numpy
logic, not a GPU/Modal call, so it's fully testable without a GPU, without
`modal deploy`, and without network access. Run with:

    pip install numpy pytest
    pytest tests/test_bbox_math.py -v

(Does NOT need `modal`, `sam2`, or `torch` installed -- mask_to_bbox has no
import-time dependency on them; it does its own local `import numpy` inside
the function body specifically so this test file doesn't need the rest of
sam2_service.py's heavier imports.)
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sam2_service import mask_to_bbox  # noqa: E402


def test_exact_rectangle():
    mask = np.zeros((100, 200), dtype=bool)
    mask[10:30, 40:80] = True

    x0, y0, x1, y1 = mask_to_bbox(mask)

    assert x0 == pytest.approx(40 / 200)
    assert x1 == pytest.approx(80 / 200)
    assert y0 == pytest.approx(10 / 100)
    assert y1 == pytest.approx(30 / 100)


def test_full_image():
    mask = np.ones((50, 50), dtype=bool)
    assert mask_to_bbox(mask) == [0.0, 0.0, 1.0, 1.0]


def test_single_pixel():
    mask = np.zeros((10, 10), dtype=bool)
    mask[5, 5] = True
    x0, y0, x1, y1 = mask_to_bbox(mask)
    assert (x0, y0, x1, y1) == pytest.approx((0.5, 0.5, 0.6, 0.6))


def test_empty_mask_returns_none():
    mask = np.zeros((50, 50), dtype=bool)
    assert mask_to_bbox(mask) is None


def test_output_always_normalized():
    rng = np.random.default_rng(42)
    for _ in range(20):
        h, w = rng.integers(10, 500), rng.integers(10, 500)
        mask = rng.random((h, w)) > 0.7
        bbox = mask_to_bbox(mask)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        assert 0 <= x0 <= x1 <= 1
        assert 0 <= y0 <= y1 <= 1
