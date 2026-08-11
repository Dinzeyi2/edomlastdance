"""Stage 5 (terminal): compute priority score + job value, then create/update
a Lead for every tenant whose territory covers the property. This is where
tenant scoping happens -- see app/pipeline/geo.py for the point-in-polygon
check against each Territory.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.damage_assessment import DamageAssessment
from app.models.lead import Lead
from app.models.property import Property
from app.models.storm_event import StormEvent
from app.models.territory import Territory
from app.pipeline.geo import point_in_polygon
from app.pipeline.scoring import compute_priority_score, estimate_job_value


async def run_score_lead(db: AsyncSession, payload: dict) -> dict:
    damage_assessment_id = payload["damage_assessment_id"]
    property_id = payload["property_id"]
    storm_event_id = payload["storm_event_id"]

    assessment = await db.get(DamageAssessment, damage_assessment_id)
    prop = await db.get(Property, property_id)
    storm_event = await db.get(StormEvent, storm_event_id)
    if assessment is None or prop is None or storm_event is None:
        return {"error": "missing assessment/property/storm_event"}

    job_value = estimate_job_value(prop.footprint_sqft, prop.roof_material_guess)
    priority = compute_priority_score(
        damage_confidence=assessment.damage_confidence,
        max_hail_in=storm_event.max_hail_in,
        max_wind_mph=storm_event.max_wind_mph,
        estimated_job_value=job_value,
    )

    territories = (await db.execute(select(Territory))).scalars().all()
    matching_tenant_ids = {
        t.tenant_id
        for t in territories
        if point_in_polygon(prop.lat, prop.lon, t.polygon_geojson)
    }

    lead_ids: list[str] = []
    for tenant_id in matching_tenant_ids:
        stmt = select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.property_id == prop.id,
            Lead.storm_event_id == storm_event.id,
        )
        lead = (await db.execute(stmt)).scalar_one_or_none()
        if lead is None:
            lead = Lead(
                tenant_id=tenant_id,
                property_id=prop.id,
                storm_event_id=storm_event.id,
                damage_assessment_id=assessment.id,
                priority_score=priority,
                estimated_job_value=job_value,
                status="new",
            )
            db.add(lead)
        else:
            lead.damage_assessment_id = assessment.id
            lead.priority_score = priority
            lead.estimated_job_value = job_value
        await db.flush()
        lead_ids.append(lead.id)

    return {"leads_upserted": lead_ids}
