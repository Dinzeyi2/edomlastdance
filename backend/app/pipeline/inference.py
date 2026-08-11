"""Stage 4: run the configured VisionProvider over an imagery asset, using
the related storm event + property as context, and enqueue scoring.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import enqueue
from app.models.damage_assessment import DamageAssessment
from app.models.imagery import ImageryAsset
from app.models.property import Property
from app.models.storm_event import StormEvent
from app.providers import get_vision_provider


async def run_inference(db: AsyncSession, payload: dict) -> dict:
    imagery_asset_id = payload["imagery_asset_id"]
    storm_event_id = payload["storm_event_id"]

    imagery = await db.get(ImageryAsset, imagery_asset_id)
    if imagery is None:
        return {"error": f"imagery_asset {imagery_asset_id} not found"}
    prop = await db.get(Property, imagery.property_id)
    storm_event = await db.get(StormEvent, storm_event_id)

    context = {
        "event_type": storm_event.event_type if storm_event else None,
        "max_hail_in": storm_event.max_hail_in if storm_event else None,
        "max_wind_mph": storm_event.max_wind_mph if storm_event else None,
        "roof_material_guess": prop.roof_material_guess if prop else None,
        "year_built": prop.year_built if prop else None,
    }

    provider = get_vision_provider()
    result = await provider.assess_damage(imagery.image_ref, context)

    assessment = DamageAssessment(
        imagery_asset_id=imagery.id,
        damage_confidence=result.damage_confidence,
        material_guess=result.material_guess,
        notes=result.notes,
        provider=result.provider,
    )
    db.add(assessment)
    await db.flush()

    await enqueue(
        db,
        "score_lead",
        {
            "damage_assessment_id": assessment.id,
            "property_id": imagery.property_id,
            "storm_event_id": storm_event_id,
        },
    )
    return {"damage_assessment_id": assessment.id}
