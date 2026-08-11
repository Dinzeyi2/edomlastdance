"""Stage 3: get (or reuse) an imagery asset for a property, then enqueue
damage inference on it.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue
from app.models.imagery import ImageryAsset
from app.models.property import Property
from app.providers import get_imagery_provider
from app.providers.base import PropertyData

IMAGERY_FRESHNESS_DAYS = 30


async def run_fetch_imagery(db: AsyncSession, payload: dict) -> dict:
    property_id = payload["property_id"]
    storm_event_id = payload["storm_event_id"]

    prop = await db.get(Property, property_id)
    if prop is None:
        return {"error": f"property {property_id} not found"}

    cutoff = date.today() - timedelta(days=IMAGERY_FRESHNESS_DAYS)
    stmt = (
        select(ImageryAsset)
        .where(ImageryAsset.property_id == prop.id, ImageryAsset.captured_date >= cutoff)
        .order_by(ImageryAsset.captured_date.desc())
        .limit(1)
    )
    imagery = (await db.execute(stmt)).scalar_one_or_none()

    if imagery is None:
        provider = get_imagery_provider()
        image_data = await provider.fetch_image(
            PropertyData(
                address=prop.address,
                county=prop.county,
                lat=prop.lat,
                lon=prop.lon,
                year_built=prop.year_built,
                roof_material_guess=prop.roof_material_guess,
                footprint_sqft=prop.footprint_sqft,
                source=prop.source,
                parcel_ref=prop.parcel_ref,
            )
        )
        imagery = ImageryAsset(
            property_id=prop.id,
            image_ref=image_data.image_ref,
            captured_date=image_data.captured_date,
            provider=image_data.provider,
        )
        db.add(imagery)
        await db.flush()

    await enqueue(
        db,
        "run_inference",
        {"imagery_asset_id": imagery.id, "storm_event_id": storm_event_id},
    )
    return {"imagery_asset_id": imagery.id}
