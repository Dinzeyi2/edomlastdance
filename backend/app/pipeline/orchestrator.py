"""Maps a job_type string to the pipeline stage function that handles it.
Both the background worker (app/jobs/worker.py) and tests use this dispatch
table rather than importing stage functions directly, so adding a new stage
is a one-line change here.
"""
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline.imagery import run_fetch_imagery
from app.pipeline.inference import run_inference
from app.pipeline.ingestion import run_ingest_storm
from app.pipeline.resolve_properties import run_resolve_properties
from app.pipeline.score_lead import run_score_lead

StageFn = Callable[[AsyncSession, dict], Awaitable[dict]]

STAGES: dict[str, StageFn] = {
    "ingest_storm": run_ingest_storm,
    "resolve_properties": run_resolve_properties,
    "fetch_imagery": run_fetch_imagery,
    "run_inference": run_inference,
    "score_lead": run_score_lead,
}


async def run_stage(db: AsyncSession, job_type: str, payload: dict) -> dict:
    stage_fn = STAGES.get(job_type)
    if stage_fn is None:
        raise ValueError(f"Unknown job_type: {job_type}")
    return await stage_fn(db, payload)
