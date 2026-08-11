from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.db import get_db
from app.models.property import Property
from app.models.tenant import Tenant
from app.schemas.lead import PropertySummary

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("/{property_id}", response_model=PropertySummary)
async def get_property(
    property_id: str,
    # Auth required (not for data ownership -- properties aren't tenant-owned,
    # only leads are) but so property lookups aren't a free, unauthenticated
    # way to enumerate every address the system has ever ingested.
    _tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> PropertySummary:
    prop = await db.get(Property, property_id)
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    return PropertySummary.model_validate(prop)
