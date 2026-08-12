"""Roofer feedback API -- step 8 in your build order. Saves corrections/labels
back to Postgres; this is the raw material for eventually training a real
YOLO defect model (step 9), which is out of scope until there's enough of
this to train on.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.db.models import Feedback
from app.db.session import get_db
from app.schemas.analyze import FeedbackRequest

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"], dependencies=[Depends(require_api_key)])


@router.post("", status_code=201)
async def submit_feedback(body: FeedbackRequest, db: AsyncSession = Depends(get_db)) -> dict:
    feedback = Feedback(
        job_id=body.job_id,
        user_id=body.user_id,
        corrected_score=body.corrected_score,
        notes=body.notes,
        corrected_findings=[f.model_dump() for f in body.corrected_findings] if body.corrected_findings else None,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return {"id": feedback.id, "status": "saved"}
