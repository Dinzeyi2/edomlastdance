"""Proves BuildingFootprintCache is actually read/written -- previously the
table existed but nothing touched it (caught on review, see
app/services/footprint_cache.py's docstring).
"""
from sqlalchemy import select

from app.db.models import BuildingFootprintCache
from app.db.session import AsyncSessionLocal
from app.services.footprint import CenterCropProvider, get_footprint_provider
from app.services.footprint_cache import get_cached_footprint, save_footprint_cache


async def test_cache_miss_then_hit():
    lat, lng = 40.7128, -74.0060
    assert await get_cached_footprint(lat, lng) is None

    result = await CenterCropProvider().get_footprint(lat, lng, b"")
    await save_footprint_cache(lat, lng, result)

    cached = await get_cached_footprint(lat, lng)
    assert cached is not None
    assert cached.source == "center_crop_cached"
    assert cached.bbox == result.bbox


async def test_cache_row_actually_persisted_in_db():
    lat, lng = 51.5074, -0.1278
    result = await CenterCropProvider().get_footprint(lat, lng, b"")
    await save_footprint_cache(lat, lng, result)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(BuildingFootprintCache))).scalars().all()
    assert any(r.lat == lat and r.lng == lng for r in rows)


async def test_pipeline_uses_cache_on_second_call(monkeypatch):
    calls = {"count": 0}
    real_provider = get_footprint_provider()

    class _CountingWrapper:
        async def get_footprint(self, lat, lng, image_bytes):
            calls["count"] += 1
            return await real_provider.get_footprint(lat, lng, image_bytes)

    monkeypatch.setattr("app.services.pipeline.get_footprint_provider", lambda: _CountingWrapper())

    from app.services.pipeline import run_analysis

    await run_analysis(job_id="job_test1", lat=9.99, lng=9.99, compare_year=None, resolution_cm=10, include_raw_tiles=False)
    await run_analysis(job_id="job_test2", lat=9.99, lng=9.99, compare_year=None, resolution_cm=10, include_raw_tiles=False)

    assert calls["count"] == 1  # second run should hit the cache, not the provider
