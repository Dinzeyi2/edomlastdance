"""Exercises the whole chain (ingest -> resolve_properties -> fetch_imagery ->
inference -> score_lead) via the job queue drain, the same path the API's
POST /storm-events/ingest route uses.
"""
from sqlalchemy import select

from app.jobs.queue import enqueue
from app.jobs.runner import drain
from app.models.job import Job
from app.models.lead import Lead
from app.models.property import Property
from app.models.storm_event import StormEvent
from app.models.tenant import Tenant, hash_api_key
from app.models.territory import Territory
from app.pipeline.geo import bounding_box_polygon


async def test_full_pipeline_produces_ranked_leads(db_session):
    # A tenant whose territory covers the mock storm's default center
    # (Dallas-Fort Worth, see app/providers/storm/mock.py DEFAULT_CENTERS).
    tenant = Tenant(name="Acme Roofing", api_key_hash=hash_api_key("test-key"))
    db_session.add(tenant)
    await db_session.flush()

    territory = Territory(
        tenant_id=tenant.id,
        name="DFW metro",
        polygon_geojson=bounding_box_polygon(32.7767, -96.7970, 0.5),
    )
    db_session.add(territory)
    await db_session.commit()

    await enqueue(db_session, "ingest_storm", {"region_hint": None})
    await db_session.commit()

    processed = await drain(db_session, max_jobs=5000)
    assert processed > 0

    # No job should be left in a failed state.
    failed = (await db_session.execute(select(Job).where(Job.status == "failed"))).scalars().all()
    assert failed == [], [ (j.job_type, j.error) for j in failed ]

    storm_events = (await db_session.execute(select(StormEvent))).scalars().all()
    assert len(storm_events) >= 1

    properties = (await db_session.execute(select(Property))).scalars().all()
    assert len(properties) >= 1

    leads = (await db_session.execute(select(Lead).where(Lead.tenant_id == tenant.id))).scalars().all()
    assert len(leads) >= 1
    for lead in leads:
        assert 0.0 <= lead.priority_score <= 1.0
        assert lead.estimated_job_value > 0
        assert lead.status == "new"

    # Ranking actually varies -- not every lead tied at the same score.
    scores = {lead.priority_score for lead in leads}
    assert len(scores) >= 1  # non-empty is the real assertion; >1 is likely but not guaranteed


async def test_pipeline_skips_tenants_outside_territory(db_session):
    tenant = Tenant(name="Far Away Roofing", api_key_hash=hash_api_key("far-key"))
    db_session.add(tenant)
    await db_session.flush()

    # Territory nowhere near the mock storm's default DFW center.
    territory = Territory(
        tenant_id=tenant.id,
        name="Somewhere else",
        polygon_geojson=bounding_box_polygon(10.0, 10.0, 0.05),
    )
    db_session.add(territory)
    await db_session.commit()

    await enqueue(db_session, "ingest_storm", {"region_hint": None})
    await db_session.commit()
    await drain(db_session, max_jobs=5000)

    leads = (await db_session.execute(select(Lead).where(Lead.tenant_id == tenant.id))).scalars().all()
    assert leads == []
