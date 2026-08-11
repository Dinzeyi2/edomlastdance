from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class TerritoryCreate(BaseModel):
    name: str
    polygon_geojson: str

    @field_validator("polygon_geojson")
    @classmethod
    def must_be_polygon(cls, v: str) -> str:
        import json

        parsed = json.loads(v)  # raises ValueError -> 422 if not valid JSON
        if parsed.get("type") != "Polygon":
            raise ValueError("polygon_geojson must be a GeoJSON Polygon")
        return v


class TerritoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    name: str
    polygon_geojson: str
    created_at: datetime
