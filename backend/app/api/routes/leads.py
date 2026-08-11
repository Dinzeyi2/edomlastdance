from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.db import get_db
from app.models.damage_assessment import DamageAssessment
from app.models.imagery import ImageryAsset
from app.models.lead import LEAD_STATUSES, Lead
from app.models.property import Property
from app.models.storm_event import StormEvent
from app.models.tenant import Tenant
from app.schemas.lead import (
    DamageAssessmentSummary,
    ImageryAssetSummary,
    LeadDetail,
    LeadListItem,
    LeadStatusUpdate,
    PropertySummary,
    StormEventSummary,
)

router = APIRouter(prefix="/leads", tags=["leads"])


async def _get_owned_lead(db: AsyncSession, tenant: Tenant, lead_id: str) -> Lead:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return lead


@router.get("", response_model=list[LeadListItem])
async def list_leads(
    status_filter: str | None = Query(default=None, alias="status"),
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=50, le=200),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[LeadListItem]:
    stmt = select(Lead).where(Lead.tenant_id == tenant.id)
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    if min_score is not None:
        stmt = stmt.where(Lead.priority_score >= min_score)
    stmt = stmt.order_by(Lead.priority_score.desc()).limit(limit)

    leads = (await db.execute(stmt)).scalars().all()

    items: list[LeadListItem] = []
    for lead in leads:
        prop = await db.get(Property, lead.property_id)
        storm_event = await db.get(StormEvent, lead.storm_event_id)
        items.append(
            LeadListItem(
                id=lead.id,
                property=PropertySummary.model_validate(prop),
                storm_event=StormEventSummary.model_validate(storm_event),
                priority_score=lead.priority_score,
                estimated_job_value=lead.estimated_job_value,
                status=lead.status,
                created_at=lead.created_at,
            )
        )
    return items


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(
    lead_id: str, tenant: Tenant = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)
) -> LeadDetail:
    lead = await _get_owned_lead(db, tenant, lead_id)
    prop = await db.get(Property, lead.property_id)
    storm_event = await db.get(StormEvent, lead.storm_event_id)
    assessment = await db.get(DamageAssessment, lead.damage_assessment_id)

    imagery = None
    if assessment is not None:
        imagery = await db.get(ImageryAsset, assessment.imagery_asset_id)

    return LeadDetail(
        id=lead.id,
        property=PropertySummary.model_validate(prop),
        storm_event=StormEventSummary.model_validate(storm_event),
        priority_score=lead.priority_score,
        estimated_job_value=lead.estimated_job_value,
        status=lead.status,
        created_at=lead.created_at,
        damage_assessment=DamageAssessmentSummary.model_validate(assessment),
        imagery=ImageryAssetSummary.model_validate(imagery) if imagery else None,
    )


@router.patch("/{lead_id}", response_model=LeadListItem)
async def update_lead_status(
    lead_id: str,
    body: LeadStatusUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> LeadListItem:
    if body.status not in LEAD_STATUSES:
        raise HTTPException(422, f"status must be one of {LEAD_STATUSES}")
    lead = await _get_owned_lead(db, tenant, lead_id)
    lead.status = body.status
    lead.status_updated_at = datetime.now(timezone.utc)
    await db.commit()

    prop = await db.get(Property, lead.property_id)
    storm_event = await db.get(StormEvent, lead.storm_event_id)
    return LeadListItem(
        id=lead.id,
        property=PropertySummary.model_validate(prop),
        storm_event=StormEventSummary.model_validate(storm_event),
        priority_score=lead.priority_score,
        estimated_job_value=lead.estimated_job_value,
        status=lead.status,
        created_at=lead.created_at,
    )
