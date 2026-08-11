import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Property(Base):
    """A single parcel/address resolved from a storm event's affected area.
    Deduplicated on (source, parcel_ref) so re-ingesting overlapping storms
    doesn't create duplicate properties.
    """

    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("source", "parcel_ref", name="uq_property_source_parcel"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    address: Mapped[str] = mapped_column(String(500))
    county: Mapped[str] = mapped_column(String(100))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roof_material_guess: Mapped[str | None] = mapped_column(String(50), nullable=True)
    footprint_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(50))
    parcel_ref: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
