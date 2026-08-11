"""Stage 1: pull storm events from the configured StormDataProvider and
persist any that aren't already known (deduped on source+external_ref). Each
new storm event enqueues a resolve_properties job.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue
from app.models.storm_event import StormEvent
from app.providers import get_storm_provider


async def run_ingest_storm(db: AsyncSession, payload: dict) -> dict:
    region_hint = payload.get("region_hint")
    provider = get_storm_provider()
    events = await provider.fetch_recent_events(region_hint=region_hint)

    created_ids: list[str] = []
    for event_data in events:
        existing = None
        if event_data.external_ref:
            stmt = select(StormEvent).where(
                StormEvent.source == event_data.source,
                StormEvent.external_ref == event_data.external_ref,
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            continue

        storm_event = StormEvent(
            event_date=event_data.event_date,
            event_type=event_data.event_type,
            polygon_geojson=event_data.polygon_geojson,
            max_hail_in=event_data.max_hail_in,
            max_wind_mph=event_data.max_wind_mph,
            source=event_data.source,
            external_ref=event_data.external_ref,
        )
        db.add(storm_event)
        await db.flush()
        created_ids.append(storm_event.id)
        await enqueue(db, "resolve_properties", {"storm_event_id": storm_event.id})

    return {"storm_events_created": created_ids}
