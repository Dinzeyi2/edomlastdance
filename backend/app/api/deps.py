"""Per-tenant API key auth. Deliberately simple for v1 -- a hashed key on the
Tenant row, checked via a header. Enough to prove multi-tenancy without
building full OAuth; see plan for what's explicitly out of scope.
"""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.tenant import Tenant, hash_api_key


async def get_current_tenant(
    x_tenant_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    if not x_tenant_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-Tenant-Key header")
    stmt = select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_tenant_key))
    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return tenant
