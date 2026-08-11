"""Abstract interfaces for every external data dependency. Pipeline code only
ever imports these types, never a concrete provider -- see
app/providers/__init__.py for the factory that wires the concrete
implementation in based on config. This is the seam that lets a real vendor
(NOAA, Regrid, Nearmap, ...) get swapped in later without touching
app/pipeline/*.

Each provider returns plain dataclasses, not SQLAlchemy models, so providers
never need a DB session and stay trivially unit-testable.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class StormEventData:
    event_date: date
    event_type: str  # "hail" | "wind"
    polygon_geojson: str
    max_hail_in: float | None
    max_wind_mph: float | None
    source: str
    external_ref: str | None = None


@dataclass
class PropertyData:
    address: str
    county: str
    lat: float
    lon: float
    year_built: int | None
    roof_material_guess: str | None
    footprint_sqft: float | None
    source: str
    parcel_ref: str


@dataclass
class ImageryAssetData:
    image_ref: str
    captured_date: date | None
    provider: str


@dataclass
class DamageAssessmentData:
    damage_confidence: float  # 0.0 - 1.0
    material_guess: str | None
    notes: str
    provider: str


class StormDataProvider(ABC):
    @abstractmethod
    async def fetch_recent_events(self, region_hint: str | None = None) -> list[StormEventData]:
        """Return storm events worth ingesting. `region_hint` narrows the
        search (e.g. a city/state name or a bounding polygon) when the
        provider supports it; providers that don't may ignore it."""
        raise NotImplementedError


class PropertyDataProvider(ABC):
    @abstractmethod
    async def resolve_properties(self, polygon_geojson: str, max_results: int = 50) -> list[PropertyData]:
        """Return properties (parcels/addresses) located inside the given
        GeoJSON polygon."""
        raise NotImplementedError


class ImageryProvider(ABC):
    @abstractmethod
    async def fetch_image(self, prop: PropertyData) -> ImageryAssetData:
        """Return a recent aerial/satellite image reference for a property."""
        raise NotImplementedError


class VisionProvider(ABC):
    @abstractmethod
    async def assess_damage(self, image_ref: str, context: dict) -> DamageAssessmentData:
        """Assess roof damage from an image. `context` carries hints the
        provider may use (storm severity, roof material guess, etc.)."""
        raise NotImplementedError
