from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_tenant
from app.models.tenant import Tenant

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantOut(BaseModel):
    id: str
    name: str


@router.get("/me", response_model=TenantOut)
async def get_current_tenant_info(tenant: Tenant = Depends(get_current_tenant)) -> TenantOut:
    return TenantOut(id=tenant.id, name=tenant.name)
