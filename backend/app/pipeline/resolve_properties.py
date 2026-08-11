"""Stage 2: given a storm event's polygon, ask the PropertyDataProvider for
the properties inside it, upsert them (deduped on source+parcel_ref), and
enqueue a fetch_imagery job for each one.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue
from app.models.property import Property
from app.models.storm_event import StormEvent
from app.providers import get_property_provider

MAX_PROPERTIES_PER_EVENT = 50


async def run_resolve_properties(db: AsyncSession, payload: dict) -> dict:
    storm_event_id = payload["storm_event_id"]
    storm_event = await db.get(StormEvent, storm_event_id)
    if storm_event is None:
        return {"error": f"storm_event {storm_event_id} not found"}

    provider = get_property_provider()
    candidates = await provider.resolve_properties(
        storm_event.polygon_geojson, max_results=MAX_PROPERTIES_PER_EVENT
    )

    property_ids: list[str] = []
    for candidate in candidates:
        stmt = select(Property).where(
            Property.source == candidate.source, Property.parcel_ref == candidate.parcel_ref
        )
        prop = (await db.execute(stmt)).scalar_one_or_none()
        if prop is None:
            prop = Property(
                address=candidate.address,
                county=candidate.county,
                lat=candidate.lat,
                lon=candidate.lon,
                year_built=candidate.year_built,
                roof_material_guess=candidate.roof_material_guess,
                footprint_sqft=candidate.footprint_sqft,
                source=candidate.source,
                parcel_ref=candidate.parcel_ref,
            )
            db.add(prop)
            await db.flush()

        property_ids.append(prop.id)
        await enqueue(
            db, "fetch_imagery", {"property_id": prop.id, "storm_event_id": storm_event.id}
        )

    return {"properties_resolved": property_ids}
