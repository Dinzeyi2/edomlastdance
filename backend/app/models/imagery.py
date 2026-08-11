import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ImageryAsset(Base):
    """A single aerial/satellite image reference for a property. image_ref is
    a path or URL, resolved by whichever ImageryProvider fetched it.
    """

    __tablename__ = "imagery_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)
    image_ref: Mapped[str] = mapped_column(String(500))
    captured_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
