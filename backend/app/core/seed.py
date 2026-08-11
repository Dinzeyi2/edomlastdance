"""Dev convenience: ensure a single tenant exists, keyed by
DEV_SEED_TENANT_KEY, so the API is usable immediately after `uvicorn` starts
without a separate signup flow. A real deployment would gate tenant creation
behind an admin console or billing signup instead -- out of scope for v1, see
the plan file.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.tenant import Tenant, hash_api_key


async def ensure_dev_tenant(db: AsyncSession) -> Tenant:
    settings = get_settings()
    key_hash = hash_api_key(settings.dev_seed_tenant_key)
    stmt = select(Tenant).where(Tenant.api_key_hash == key_hash)
    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name="Dev Roofing Co", api_key_hash=key_hash)
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
    return tenant
