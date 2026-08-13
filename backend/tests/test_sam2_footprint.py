"""Tests Sam2FootprintProvider, which is now an HTTP client calling a
Modal-hosted SAM-2 endpoint (Railway has no GPU tier -- see
/modal-service). Mocks the HTTP call itself (real network calls to Modal
aren't reachable from this sandbox anyway -- confirmed, see
/modal-service/README.md), but tests the real request/response handling
logic: auth header construction, missing-config error, bbox parsing, and
the fallback when SAM-2 finds nothing.
"""
import httpx
import pytest

from app.services.footprint import CENTER_CROP_BBOX, Sam2FootprintProvider


class _FakeResponse:
    def __init__(self, json_body: dict, status_code: int = 200):
        self._json_body = json_body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self) -> dict:
        return self._json_body


async def test_missing_config_raises_clear_error(monkeypatch):
    monkeypatch.setenv("SAM2_MODAL_ENDPOINT_URL", "")
    monkeypatch.setenv("SAM2_MODAL_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SAM2_MODAL_ENDPOINT_URL"):
            await Sam2FootprintProvider().get_footprint(1.0, 1.0, b"fake-image-bytes")
    finally:
        get_settings.cache_clear()


async def test_sends_correct_auth_header_and_body(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SAM2_MODAL_ENDPOINT_URL", "https://example--roofai-sam2.modal.run")
    monkeypatch.setenv("SAM2_MODAL_API_KEY", "test-modal-key")
    get_settings.cache_clear()

    captured = {}

    async def fake_post(self, url, content=None, headers=None, **kwargs):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        return _FakeResponse({"bbox": [0.1, 0.2, 0.8, 0.9]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    try:
        result = await Sam2FootprintProvider().get_footprint(1.0, 1.0, b"fake-image-bytes")
    finally:
        get_settings.cache_clear()

    assert captured["url"] == "https://example--roofai-sam2.modal.run"
    assert captured["content"] == b"fake-image-bytes"
    assert captured["headers"]["Authorization"] == "Bearer test-modal-key"
    assert result.bbox == (0.1, 0.2, 0.8, 0.9)
    assert result.source == "sam2"


async def test_null_bbox_falls_back_to_center_crop(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SAM2_MODAL_ENDPOINT_URL", "https://example--roofai-sam2.modal.run")
    monkeypatch.setenv("SAM2_MODAL_API_KEY", "test-modal-key")
    get_settings.cache_clear()

    async def fake_post(self, url, content=None, headers=None, **kwargs):
        return _FakeResponse({"bbox": None})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    try:
        result = await Sam2FootprintProvider().get_footprint(1.0, 1.0, b"fake-image-bytes")
    finally:
        get_settings.cache_clear()

    assert result.bbox == CENTER_CROP_BBOX
    assert result.source == "sam2_fallback"


async def test_http_error_propagates(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SAM2_MODAL_ENDPOINT_URL", "https://example--roofai-sam2.modal.run")
    monkeypatch.setenv("SAM2_MODAL_API_KEY", "wrong-key")
    get_settings.cache_clear()

    async def fake_post(self, url, content=None, headers=None, **kwargs):
        return _FakeResponse({}, status_code=401)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await Sam2FootprintProvider().get_footprint(1.0, 1.0, b"fake-image-bytes")
    finally:
        get_settings.cache_clear()
