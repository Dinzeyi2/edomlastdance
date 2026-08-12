"""Test setup: scratch SQLite DB, local-disk storage, eager Celery (so async
jobs run inline and deterministically without needing a separate worker
process), a REAL Redis server on a dedicated port (used for real by the
imagery cache and rate limiter -- not mocked out, since those need to be
proven to actually work against Redis, not just import cleanly), and no LLM
reasoning pass (keeps tests free and offline). All env vars are set *before*
importing anything from `app`, since Settings/Celery/the rate limiter are all
configured at import or first-use time.
"""
import os
import shutil
import socket
import subprocess
import tempfile
import time

_tmp_db_fd, _TMP_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
_TMP_STORAGE_DIR = tempfile.mkdtemp(prefix="roofai_storage_")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_REDIS_PORT = _free_port()
_redis_proc = subprocess.Popen(
    ["redis-server", "--port", str(_REDIS_PORT), "--daemonize", "no", "--save", "", "--appendonly", "no"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
for _ in range(50):
    try:
        with socket.create_connection(("127.0.0.1", _REDIS_PORT), timeout=0.2):
            break
    except OSError:
        time.sleep(0.1)
else:
    raise RuntimeError("test Redis server did not start in time")

os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"
os.environ["REDIS_URL"] = f"redis://127.0.0.1:{_REDIS_PORT}/0"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = _TMP_STORAGE_DIR
os.environ["LLM_PROVIDER"] = "none"
os.environ["IMAGERY_PROVIDER"] = "mock"
os.environ["FOOTPRINT_PROVIDER"] = "center_crop"
os.environ["DEFECT_PROVIDER"] = "rule_based"
os.environ["RAILWAY_API_KEY"] = "test-key"
# High enough that ordinary test traffic never trips it -- see
# tests/test_rate_limit.py for a dedicated test that exercises the real 429
# path against a deliberately low limit.
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.db  # noqa: E402,F401 - register tables on Base.metadata
from app.db.session import Base, async_engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from app.services.redis_client import get_redis

    await get_redis().flushdb()
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
    _redis_proc.terminate()
    try:
        _redis_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _redis_proc.kill()
