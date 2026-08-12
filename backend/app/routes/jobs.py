from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.db.models import Job
from app.db.session import get_db
from app.schemas.analyze import AnalysisResult, JobStatusResponse

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> JobStatusResponse:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        result=AnalysisResult.model_validate(job.result) if job.result else None,
        error=job.error,
    )
