from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PropertySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    address: str
    county: str
    lat: float
    lon: float
    year_built: int | None
    roof_material_guess: str | None
    footprint_sqft: float | None


class StormEventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_date: date
    event_type: str
    max_hail_in: float | None
    max_wind_mph: float | None
    source: str


class DamageAssessmentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    damage_confidence: float
    material_guess: str | None
    notes: str
    provider: str


class ImageryAssetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    image_ref: str
    captured_date: date | None
    provider: str


class LeadListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    property: PropertySummary
    storm_event: StormEventSummary
    priority_score: float
    estimated_job_value: float
    status: str
    created_at: datetime


class LeadDetail(LeadListItem):
    damage_assessment: DamageAssessmentSummary
    imagery: ImageryAssetSummary | None


class LeadStatusUpdate(BaseModel):
    status: str
