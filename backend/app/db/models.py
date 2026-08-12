import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

JOB_STATUSES = ("queued", "processing", "completed", "failed")


def _job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


class Job(Base):
    """One analysis request. Written by the API on POST /analyze/async, read
    by GET /jobs/{id}, updated by the Celery task as it progresses through
    app/services/pipeline.py's stages.
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_job_id)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)

    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    compare_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_cm: Mapped[int] = mapped_column(Integer, default=10)
    include_raw_tiles: Mapped[bool] = mapped_column(default=True)

    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class BuildingFootprintCache(Base):
    """Caches the resolved footprint for a building so repeat requests for the
    same coordinates don't re-run segmentation. Keyed by building_id, a
    deterministic hash of rounded lat/lng -- see app/services/footprint.py.
    """

    __tablename__ = "building_footprint_cache"

    building_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    footprint_geojson: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


class Feedback(Base):
    """Roofer-submitted corrections/labels on a completed job's findings --
    the raw material for eventually training a real defect-detection model
    (see the "train real YOLO model" step in the README roadmap)."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    corrected_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_findings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
