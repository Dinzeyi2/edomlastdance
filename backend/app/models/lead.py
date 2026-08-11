import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

LEAD_STATUSES = ("new", "contacted", "won", "lost")


class Lead(Base):
    """A ranked, tenant-scoped opportunity: one property + one storm event +
    its damage assessment, with a computed priority score and job value
    estimate. Status is the feedback loop -- reps mark outcomes here.
    """

    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)
    storm_event_id: Mapped[str] = mapped_column(ForeignKey("storm_events.id"), index=True)
    damage_assessment_id: Mapped[str] = mapped_column(ForeignKey("damage_assessments.id"))

    priority_score: Mapped[float] = mapped_column(Float)
    estimated_job_value: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="new")

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    status_updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
