from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import app.db  # noqa: F401 - registers Job/BuildingFootprintCache/Feedback on Base.metadata
from app.config import get_settings
from app.db.session import init_db_async
from app.routes import analyze, feedback, health, jobs


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Retries with backoff -- on Railway the web service and its Postgres
    # addon can both be booting at once.
    await init_db_async()
    yield


app = FastAPI(title="RoofAI Analysis Backend", lifespan=lifespan)

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(jobs.router)
app.include_router(feedback.router)

# Serves files written by LocalDiskStorageService (STORAGE_PROVIDER=local, the
# default -- zero-config for local dev/tests). Irrelevant when
# STORAGE_PROVIDER=s3: those URLs point directly at the S3/R2 bucket.
_settings = get_settings()
if _settings.storage_provider == "local":
    Path(_settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/storage", StaticFiles(directory=_settings.local_storage_dir), name="storage")
