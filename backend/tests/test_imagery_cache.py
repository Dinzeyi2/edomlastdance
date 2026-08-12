"""Proves CachedImageryProvider actually round-trips through the real Redis
server started in conftest.py: a second fetch for the same coordinates must
NOT call the underlying provider again.
"""
from datetime import date

from app.services.imagery import ImageryResult
from app.services.imagery_cache import CachedImageryProvider


class _CountingProvider:
    def __init__(self, payload: bytes = b"fake-tile-bytes"):
        self.calls = 0
        self._payload = payload

    async def fetch_image(self, lat, lng, resolution_cm, year=None):
        self.calls += 1
        return ImageryResult(image_bytes=self._payload, media_type="image/png", captured_date=date(2024, 1, 1), provider="counting")


async def test_second_fetch_for_same_coords_is_served_from_cache():
    inner = _CountingProvider()
    cached = CachedImageryProvider(inner, provider_name="counting")

    first = await cached.fetch_image(12.34, 56.78, 10)
    second = await cached.fetch_image(12.34, 56.78, 10)

    assert inner.calls == 1
    assert first.image_bytes == second.image_bytes == b"fake-tile-bytes"
    assert second.provider == "counting_cached"


async def test_different_coords_are_not_cross_cached():
    inner = _CountingProvider()
    cached = CachedImageryProvider(inner, provider_name="counting")

    await cached.fetch_image(1.0, 1.0, 10)
    await cached.fetch_image(2.0, 2.0, 10)

    assert inner.calls == 2


async def test_current_and_historical_are_cached_separately():
    inner = _CountingProvider()
    cached = CachedImageryProvider(inner, provider_name="counting")

    await cached.fetch_image(5.0, 5.0, 10)  # current
    await cached.fetch_image(5.0, 5.0, 10, year=2020)  # historical

    assert inner.calls == 2


async def test_fails_open_when_redis_is_unreachable(monkeypatch):
    """Caught by actually testing this: an unreachable Redis must not fail
    the request -- it should fall straight through to the real provider.
    Points get_redis at a port nothing is listening on to force a real
    connection failure, not a mocked one."""
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(
        "app.services.redis_client.get_redis",
        lambda: redis_asyncio.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=1),
    )

    inner = _CountingProvider()
    cached = CachedImageryProvider(inner, provider_name="counting")
    result = await cached.fetch_image(7.0, 7.0, 10)

    assert result.image_bytes == b"fake-tile-bytes"
    assert inner.calls == 1
