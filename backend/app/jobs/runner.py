"""Drains pending jobs from the queue, running each through the pipeline
orchestrator until nothing is left (or max_jobs is hit). Used by:
  - the standalone worker process (app/jobs/worker.py), in a poll loop
  - the ingest API route, which drains synchronously after enqueueing so a
    single POST /storm-events/ingest call demonstrates the full pipeline
    without needing a second worker process running -- reasonable given mock
    providers are instant; a real deployment with slow vendor APIs would want
    the worker process to own this instead (see README).
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.queue import claim_next
from app.pipeline.orchestrator import run_stage

logger = logging.getLogger(__name__)


async def process_one(db: AsyncSession) -> bool:
    """Claim and run a single pending job. Returns False if the queue was
    empty (nothing to do)."""
    job = await claim_next(db)
    if job is None:
        return False

    try:
        result = await run_stage(db, job.job_type, job.payload)
        job.status = "done"
        job.result = result
    except Exception as exc:  # noqa: BLE001 - job failures must not crash the drain loop
        logger.exception("job %s (%s) failed", job.id, job.job_type)
        job.status = "failed"
        job.error = str(exc)

    await db.commit()
    return True


async def drain(db: AsyncSession, max_jobs: int = 1000) -> int:
    """Process pending jobs until the queue is empty or max_jobs is reached.
    Returns the number of jobs processed."""
    processed = 0
    while processed < max_jobs:
        did_work = await process_one(db)
        if not did_work:
            break
        processed += 1
    return processed
