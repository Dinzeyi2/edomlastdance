"""Postgres-backed footprint cache -- your spec's "Cached footprints" line.
Previously the BuildingFootprintCache table existed but nothing read or
wrote it (a real gap, caught on review). Wired in now: app/services/pipeline.py
checks this before calling a footprint provider, and writes the result after,
so repeat requests for the same building skip re-running
segmentation/lookup.

Uses its own short-lived async session rather than threading one through
both call paths (the sync /analyze route and the Celery worker's sync DB
session) -- both already run inside an asyncio event loop, so an ad-hoc
AsyncSession here is cheap and keeps app/services/pipeline.py's signature
simple.
"""
from app.db.models import BuildingFootprintCache
from app.db.session import AsyncSessionLocal
from app.services.footprint import FootprintResult, building_id_for


async def get_cached_footprint(lat: float, lng: float) -> FootprintResult | None:
    building_id = building_id_for(lat, lng)
    async with AsyncSessionLocal() as db:
        row = await db.get(BuildingFootprintCache, building_id)
        if row is None:
            return None
        return FootprintResult(
            bbox=_bbox_from_cache(row),
            polygon_geojson=row.footprint_geojson if row.footprint_geojson != "null" else None,
            area_sqm=None,  # not persisted separately; re-derive from polygon if needed later
            source=f"{row.source}_cached",
        )


async def save_footprint_cache(lat: float, lng: float, result: FootprintResult) -> None:
    building_id = building_id_for(lat, lng)
    async with AsyncSessionLocal() as db:
        existing = await db.get(BuildingFootprintCache, building_id)
        if existing is not None:
            return  # already cached -- footprints don't change often enough to need refresh logic yet
        db.add(
            BuildingFootprintCache(
                building_id=building_id,
                lat=lat,
                lng=lng,
                footprint_geojson=result.polygon_geojson or _bbox_to_geojson(result.bbox),
                source=result.source,
            )
        )
        await db.commit()


def _bbox_to_geojson(bbox: tuple[float, float, float, float]) -> str:
    import json

    x0, y0, x1, y1 = bbox
    return json.dumps({"type": "bbox", "coordinates": [x0, y0, x1, y1]})


def _bbox_from_cache(row: BuildingFootprintCache) -> tuple[float, float, float, float]:
    import json

    from app.services.footprint import CENTER_CROP_BBOX

    try:
        parsed = json.loads(row.footprint_geojson)
        if parsed.get("type") == "bbox":
            return tuple(parsed["coordinates"])
    except (ValueError, KeyError, TypeError):
        pass
    # Real OSM polygon cached, no pixel bbox stored separately -- fall back to
    # the same placeholder crop pipeline.py uses elsewhere until real
    # georeferenced imagery makes a precise pixel bbox meaningful.
    return CENTER_CROP_BBOX
