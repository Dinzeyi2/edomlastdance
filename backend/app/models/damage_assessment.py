import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DamageAssessment(Base):
    """The output of running a VisionProvider over one ImageryAsset."""

    __tablename__ = "damage_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    imagery_asset_id: Mapped[str] = mapped_column(ForeignKey("imagery_assets.id"), index=True)
    damage_confidence: Mapped[float] = mapped_column(Float)  # 0.0 - 1.0
    material_guess: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
