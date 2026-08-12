"""Imagery fetcher: given lat/lng (+ optional year for historical), return an
aerial image. Real vendors (Google Solar API, Nearmap) are stubbed -- see
GoogleSolarProvider/NearmapProvider -- pending API keys and their actual
request/response shapes, which are involved enough (Solar API returns a
data layer bundle, not a single tile) that a guessed implementation would be
worse than an honest NotImplementedError.
"""
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from app.config import get_settings
from app.services.roof_art import generate_schematic_roof, image_to_png_bytes


@dataclass
class ImageryResult:
    image_bytes: bytes
    media_type: str
    captured_date: date | None
    provider: str


class ImageryProvider(ABC):
    @abstractmethod
    async def fetch_image(
        self, lat: float, lng: float, resolution_cm: int, year: int | None = None
    ) -> ImageryResult:
        """Return an aerial image for the given coordinates. `year`, if given,
        requests historical imagery from that year for temporal comparison;
        omit for the most recent available capture."""
        raise NotImplementedError


class MockImageryProvider(ImageryProvider):
    """Deterministic synthetic imagery -- see app/services/roof_art.py. Damage
    mark count is derived from (lat, lng, year) so the same building/year
    always returns the same image, and different years differ in a way
    app/services/temporal.py can meaningfully diff.
    """

    async def fetch_image(
        self, lat: float, lng: float, resolution_cm: int, year: int | None = None
    ) -> ImageryResult:
        key = f"{round(lat, 5)},{round(lng, 5)},{year or 'current'}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        seed = int(digest[:8], 16)
        # Capped at 24 so scores actually spread across good/aging/poor
        # instead of nearly every seed saturating the scorer's floor -- see
        # app/services/scoring.py's MAX_DEDUCTION.
        base_marks = int(digest[8:10], 16) % 25
        # Historical imagery (a compare_year request) is seeded to look
        # better-kept than "current" -- a stand-in for the roof having aged
        # since then, so the temporal diff has something real to show.
        damage_marks = max(0, base_marks - 10) if year else base_marks

        img = generate_schematic_roof(seed=seed, num_damage_marks=damage_marks)
        captured = date(year, 6, 15) if year else date.today()
        return ImageryResult(
            image_bytes=image_to_png_bytes(img),
            media_type="image/png",
            captured_date=captured,
            provider="mock",
        )


class GoogleSolarProvider(ImageryProvider):
    """Real source, stubbed. See
    https://developers.google.com/maps/documentation/solar for the Data
    Layers API this would call -- it returns a GeoTIFF bundle (DSM, RGB, mask,
    flux layers), not a single PNG, so implementing this for real also means
    adding GeoTIFF handling (e.g. rasterio) that isn't in requirements.txt
    yet. Enable via IMAGERY_PROVIDER=google_solar once implemented.
    """

    async def fetch_image(
        self, lat: float, lng: float, resolution_cm: int, year: int | None = None
    ) -> ImageryResult:
        settings = get_settings()
        if not settings.google_solar_api_key:
            raise RuntimeError("IMAGERY_PROVIDER=google_solar requires GOOGLE_SOLAR_API_KEY.")
        raise NotImplementedError(
            "Google Solar API integration not yet implemented. Set IMAGERY_PROVIDER=mock for now."
        )


class NearmapProvider(ImageryProvider):
    """Real source, stubbed. Enable via IMAGERY_PROVIDER=nearmap once
    implemented against Nearmap's Tile API / AI Package."""

    async def fetch_image(
        self, lat: float, lng: float, resolution_cm: int, year: int | None = None
    ) -> ImageryResult:
        settings = get_settings()
        if not settings.nearmap_api_key:
            raise RuntimeError("IMAGERY_PROVIDER=nearmap requires NEARMAP_API_KEY.")
        raise NotImplementedError(
            "Nearmap integration not yet implemented. Set IMAGERY_PROVIDER=mock for now."
        )


_PROVIDERS = {"mock": MockImageryProvider, "google_solar": GoogleSolarProvider, "nearmap": NearmapProvider}


def get_imagery_provider() -> ImageryProvider:
    return _PROVIDERS[get_settings().imagery_provider]()
