"""The Celery task behind POST /analyze/async. Runs app/services/pipeline.py's
async run_analysis() via asyncio.run() (Celery tasks are plain synchronous
functions), updating the Job row's progress/stage as each pipeline stage
completes so GET /jobs/{id} reflects live progress, then notifies Lovable via
webhook on completion (or failure).
"""
import asyncio
import logging
from datetime import datetime, timezone

from app.db.models import Job
from app.db.session import SyncSessionLocal
from app.services.pipeline import run_analysis
from app.services.webhook import notify_lovable
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="run_analysis_task", bind=True, max_retries=0)
def run_analysis_task(self, job_id: str) -> None:
    asyncio.run(_run_analysis_task_async(job_id))


async def _run_analysis_task_async(job_id: str) -> None:
    with SyncSessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            logger.error("job %s not found -- nothing to process", job_id)
            return

        job.status = "processing"
        db.commit()

        async def on_progress(progress: float, stage: str) -> None:
            job.progress = progress
            job.stage = stage
            job.updated_at = datetime.now(timezone.utc)
            db.commit()

        try:
            result = await run_analysis(
                job_id=job.id,
                lat=job.lat,
                lng=job.lng,
                compare_year=job.compare_year,
                resolution_cm=job.resolution_cm,
                include_raw_tiles=job.include_raw_tiles,
                on_progress=on_progress,
            )
            job.status = "completed"
            job.progress = 1.0
            job.stage = "completed"
            job.result = result.model_dump()
            db.commit()
            await notify_lovable(job.id, job.user_id, "completed", job.result)
        except Exception as exc:  # noqa: BLE001 - must not crash the worker process
            logger.exception("analysis failed for job %s", job_id)
            job.status = "failed"
            job.error = str(exc)
            db.commit()
            await notify_lovable(job.id, job.user_id, "failed", None)
