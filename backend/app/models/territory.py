import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Territory(Base):
    """A tenant's coverage area. polygon_geojson is a GeoJSON Polygon (lon/lat
    ring) stored as text -- see app/pipeline/geo.py for how it's used to filter
    which properties/leads belong to which tenant.
    """

    __tablename__ = "territories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    polygon_geojson: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
