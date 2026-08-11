from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401 - populate Base.metadata before init_db()
from app.api.routes import health, leads, properties, storm_events, tenants, territories
from app.core.db import SessionLocal, init_db
from app.core.seed import ensure_dev_tenant


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    async with SessionLocal() as db:
        await ensure_dev_tenant(db)
    yield


app = FastAPI(title="Roofing AI Lead Engine", lifespan=lifespan)

app.include_router(health.router)
app.include_router(storm_events.router)
app.include_router(leads.router)
app.include_router(properties.router)
app.include_router(territories.router)
app.include_router(tenants.router)
