from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.jobs.queue import enqueue
from app.jobs.runner import drain
from app.schemas.storm_event import IngestRequest, IngestResponse

router = APIRouter(prefix="/storm-events", tags=["storm-events"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_storm_events(body: IngestRequest, db: AsyncSession = Depends(get_db)) -> IngestResponse:
    """Kick off the pipeline: fetch storm events for a region, then drain the
    job queue synchronously so the whole ingest -> properties -> imagery ->
    inference -> scoring chain runs before responding. See app/jobs/runner.py
    for why this is synchronous in v1 rather than requiring a separate
    worker process to be running.
    """
    job = await enqueue(db, "ingest_storm", {"region_hint": body.region_hint})
    await db.commit()

    processed = await drain(db, max_jobs=2000)

    storm_events_created = (job.result or {}).get("storm_events_created", [])
    return IngestResponse(storm_events_created=storm_events_created, jobs_processed=processed)
