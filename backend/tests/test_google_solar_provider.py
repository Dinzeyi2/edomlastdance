"""Tests the parts of GoogleSolarProvider that don't need a live API call:
- the missing-key error path
- _geotiff_to_png against a REAL GeoTIFF constructed with rasterio (not the
  Solar API's actual output, but real GeoTIFF bytes with known pixel data,
  so this proves the decode logic -- band selection, transpose, dtype
  handling -- is actually correct, independent of whether the live HTTP
  call to Google works, which this sandbox cannot verify -- see
  app/services/imagery.py's GoogleSolarProvider docstring).
"""
import io

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.io import MemoryFile

from app.services.imagery import GoogleSolarProvider, _geotiff_to_png


async def test_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="GOOGLE_SOLAR_API_KEY"):
            await GoogleSolarProvider().fetch_image(1.0, 1.0, 10)
    finally:
        get_settings.cache_clear()


def _make_geotiff(arr: np.ndarray) -> bytes:
    """arr: (bands, H, W) uint8."""
    bands, h, w = arr.shape
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", height=h, width=w, count=bands, dtype=arr.dtype) as dataset:
            dataset.write(arr)
        return memfile.read()


def test_geotiff_decoding_preserves_pixel_values_for_3_band_rgb():
    # A known 2x2 RGB image: red, green, blue, white pixels.
    arr = np.array(
        [
            [[255, 0], [0, 255]],   # R band
            [[0, 255], [0, 255]],   # G band
            [[0, 0], [255, 255]],   # B band
        ],
        dtype=np.uint8,
    )
    tiff_bytes = _make_geotiff(arr)
    png_bytes = _geotiff_to_png(tiff_bytes)

    img = Image.open(io.BytesIO(png_bytes))
    assert img.mode == "RGB"
    assert img.size == (2, 2)
    pixels = np.array(img)
    assert tuple(pixels[0, 0]) == (255, 0, 0)  # red
    assert tuple(pixels[0, 1]) == (0, 255, 0)  # green
    assert tuple(pixels[1, 0]) == (0, 0, 255)  # blue
    assert tuple(pixels[1, 1]) == (255, 255, 255)  # white


def test_geotiff_decoding_handles_single_band_by_replicating_to_rgb():
    arr = np.array([[[100, 200], [50, 25]]], dtype=np.uint8)  # 1 band
    tiff_bytes = _make_geotiff(arr)
    png_bytes = _geotiff_to_png(tiff_bytes)

    img = Image.open(io.BytesIO(png_bytes))
    assert img.mode == "RGB"
    pixels = np.array(img)
    assert tuple(pixels[0, 0]) == (100, 100, 100)
