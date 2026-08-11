import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

JOB_STATUSES = ("pending", "running", "done", "failed")


class Job(Base):
    """Postgres/SQLite-backed job queue -- deliberately not Redis/Celery for
    v1 so local dev needs no extra infra. A worker claims pending jobs (see
    app/jobs/queue.py), dispatches to the matching pipeline stage in
    app/pipeline/orchestrator.py, and enqueues the next stage on success.
    This table is the seam to swap in a real broker later without touching
    pipeline code.
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_type: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
