from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.db import get_db
from app.models.tenant import Tenant
from app.models.territory import Territory
from app.schemas.territory import TerritoryCreate, TerritoryOut

router = APIRouter(prefix="/territories", tags=["territories"])


@router.post("", response_model=TerritoryOut, status_code=201)
async def create_territory(
    body: TerritoryCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TerritoryOut:
    territory = Territory(tenant_id=tenant.id, name=body.name, polygon_geojson=body.polygon_geojson)
    db.add(territory)
    await db.commit()
    await db.refresh(territory)
    return TerritoryOut.model_validate(territory)


@router.get("", response_model=list[TerritoryOut])
async def list_territories(
    tenant: Tenant = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)
) -> list[TerritoryOut]:
    stmt = select(Territory).where(Territory.tenant_id == tenant.id)
    territories = (await db.execute(stmt)).scalars().all()
    return [TerritoryOut.model_validate(t) for t in territories]
