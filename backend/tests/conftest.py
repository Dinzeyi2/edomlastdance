"""Test setup. Points the app at a scratch SQLite file (set via env var
*before* app.core.config is ever imported, since Settings is lru_cache'd) and
recreates the schema fresh before every test.
"""
import os
import tempfile

_tmp_db_fd, _TMP_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB_PATH}"
os.environ.setdefault("VISION_PROVIDER", "stub")
os.environ.setdefault("STORM_PROVIDER", "mock")
os.environ.setdefault("PROPERTY_PROVIDER", "mock")
os.environ.setdefault("IMAGERY_PROVIDER", "mock")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.models  # noqa: E402,F401 - register tables on Base.metadata
from app.core.db import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def db_session():
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def client():
    # httpx's ASGITransport doesn't fire ASGI lifespan events, so init_db()/
    # ensure_dev_tenant() from app.main's lifespan won't run here -- schema
    # creation is already handled by _reset_db, so just seed the dev tenant
    # directly.
    from app.core.seed import ensure_dev_tenant
    from app.main import app as fastapi_app

    async with SessionLocal() as db:
        await ensure_dev_tenant(db)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
