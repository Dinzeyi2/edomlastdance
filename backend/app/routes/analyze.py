import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.db.models import Job, _job_id
from app.db.session import get_db
from app.schemas.analyze import AnalysisResult, AnalyzeRequest, AsyncAnalyzeResponse
from app.services.pipeline import run_analysis
from app.workers.tasks import run_analysis_task

router = APIRouter(prefix="/api/v1", tags=["analyze"], dependencies=[Depends(require_api_key)])

# Rough estimate surfaced in the async response -- not measured live, just a
# reasonable expectation to show a caller while it polls.
ESTIMATED_SECONDS = 60


@router.post("/analyze", response_model=AnalysisResult)
async def analyze_sync(body: AnalyzeRequest) -> AnalysisResult:
    """Run the full pipeline inline and return the result directly. Fine for
    testing/demoing; for real traffic prefer /analyze/async so the caller
    isn't holding a request open for 30-120s (see spec section H)."""
    # A synchronous call still needs a job_id to namespace uploaded evidence
    # under -- reuse the same id format the async path uses.
    job_id = _job_id()
    return await run_analysis(
        job_id=job_id,
        lat=body.lat,
        lng=body.lng,
        compare_year=body.compare_year,
        resolution_cm=body.resolution_cm,
        include_raw_tiles=body.include_raw_tiles,
    )


@router.post("/analyze/async", response_model=AsyncAnalyzeResponse)
async def analyze_async(body: AnalyzeRequest, db: AsyncSession = Depends(get_db)) -> AsyncAnalyzeResponse:
    job = Job(
        lat=body.lat,
        lng=body.lng,
        address=body.address,
        user_id=body.user_id,
        compare_year=body.compare_year,
        resolution_cm=body.resolution_cm,
        include_raw_tiles=body.include_raw_tiles,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Dispatch off-thread. In real (non-eager) mode this just keeps a quick
    # sync Redis call off the event loop; in CELERY_TASK_ALWAYS_EAGER mode
    # (local dev/tests) it's what makes the task's internal asyncio.run()
    # work at all -- run inline on this thread it would collide with the
    # event loop this very request handler is running on.
    await asyncio.to_thread(run_analysis_task.delay, job.id)

    return AsyncAnalyzeResponse(job_id=job.id, status="queued", estimated_seconds=ESTIMATED_SECONDS)
