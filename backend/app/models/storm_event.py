import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StormEvent(Base):
    """A single storm (hail or wind) occurrence, with the geographic area it
    affected. This is the trigger that kicks off the rest of the pipeline.
    """

    __tablename__ = "storm_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_date: Mapped[date] = mapped_column(Date)
    event_type: Mapped[str] = mapped_column(String(20))  # "hail" | "wind"
    polygon_geojson: Mapped[str] = mapped_column(Text)
    max_hail_in: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_wind_mph: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(50))  # provider name, e.g. "mock", "noaa"
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
