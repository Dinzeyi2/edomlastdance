"""Test setup: scratch SQLite DB, local-disk storage, eager Celery (so async
jobs run inline and deterministically without a real Redis broker/worker
process), and no LLM reasoning pass (keeps tests free and offline). All env
vars are set *before* importing anything from `app`, since Settings and the
Celery app are both configured at import time.
"""
import os
import shutil
import tempfile

_tmp_db_fd, _TMP_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
_TMP_STORAGE_DIR = tempfile.mkdtemp(prefix="roofai_storage_")

os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = _TMP_STORAGE_DIR
os.environ["LLM_PROVIDER"] = "none"
os.environ["IMAGERY_PROVIDER"] = "mock"
os.environ["FOOTPRINT_PROVIDER"] = "center_crop"
os.environ["DEFECT_PROVIDER"] = "rule_based"
os.environ["RAILWAY_API_KEY"] = "test-key"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.db  # noqa: E402,F401 - register tables on Base.metadata
from app.db.session import Base, async_engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client():
    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp_dirs():
    yield
    shutil.rmtree(_TMP_STORAGE_DIR, ignore_errors=True)
