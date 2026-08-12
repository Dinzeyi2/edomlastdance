"""Imagery fetcher: given lat/lng (+ optional year for historical), return an
aerial image.

GoogleSolarProvider is a REAL implementation against Google's documented
Solar API (Data Layers endpoint), not a stub -- see its docstring for exactly
what's verified vs. not. NearmapProvider remains a stub: Nearmap's API is
behind an enterprise sales process with no public self-serve key, so there's
no documented public request shape to implement against yet.
"""
import hashlib
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import httpx
import numpy as np
from PIL import Image

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


SOLAR_API_BASE = "https://solar.googleapis.com/v1"
SOLAR_API_RADIUS_METERS = 50  # covers a typical residential lot + margin
SOLAR_API_TIMEOUT_S = 30.0


class GoogleSolarProvider(ImageryProvider):
    """Real implementation against Google's Solar API "Data Layers" endpoint
    (https://developers.google.com/maps/documentation/solar/data-layers).
    Two real HTTP calls: (1) dataLayers:get, which returns metadata + a
    signed URL for the RGB aerial GeoTIFF around the point, then (2) fetch
    that GeoTIFF and decode it with rasterio into a standard RGB image.

    Verified: this sandbox can reach solar.googleapis.com (confirmed via a
    direct connectivity check -- unlike most third-party APIs, this one is
    NOT blocked by the sandbox's egress policy). NOT verified: an actual
    successful call, since that needs a real Google Cloud API key with the
    Solar API enabled, which I don't have. Written against the documented
    request/response shape as precisely as I can from memory -- give me a
    real key and I can test and fix this in the same sandbox that couldn't
    reach OpenAI/Nearmap/Overpass/S3-compatible-non-AWS-endpoints.

    The Solar API doesn't take a `year` parameter -- it returns whatever
    imagery it has (with an `imageryDate` in the response), so `year` is
    accepted but not something this call can honor; there's no historical
    archive selection in this API the way NEXRAD/NOAA has for weather.
    """

    async def fetch_image(
        self, lat: float, lng: float, resolution_cm: int, year: int | None = None
    ) -> ImageryResult:
        settings = get_settings()
        if not settings.google_solar_api_key:
            raise RuntimeError("IMAGERY_PROVIDER=google_solar requires GOOGLE_SOLAR_API_KEY.")

        async with httpx.AsyncClient(timeout=SOLAR_API_TIMEOUT_S) as client:
            layers_resp = await client.get(
                f"{SOLAR_API_BASE}/dataLayers:get",
                params={
                    "location.latitude": lat,
                    "location.longitude": lng,
                    "radiusMeters": SOLAR_API_RADIUS_METERS,
                    "view": "IMAGERY_LAYERS",
                    "requiredQuality": "MEDIUM",
                    "key": settings.google_solar_api_key,
                },
            )
            layers_resp.raise_for_status()
            layers = layers_resp.json()

            rgb_url = layers.get("rgbUrl")
            if not rgb_url:
                raise RuntimeError(f"Solar API returned no rgbUrl for ({lat}, {lng}): {layers}")

            # rgbUrl is itself an API endpoint, not a public storage URL -- it
            # needs the API key too.
            tiff_resp = await client.get(rgb_url, params={"key": settings.google_solar_api_key})
            tiff_resp.raise_for_status()
            image_bytes = _geotiff_to_png(tiff_resp.content)

        imagery_date = layers.get("imageryDate")
        captured = (
            date(imagery_date["year"], imagery_date["month"], imagery_date["day"]) if imagery_date else None
        )

        return ImageryResult(image_bytes=image_bytes, media_type="image/png", captured_date=captured, provider="google_solar")


def _geotiff_to_png(tiff_bytes: bytes) -> bytes:
    """Decode a GeoTIFF (as returned by the Solar API's rgbUrl) into a
    standard RGB PNG. Local import of rasterio -- it's a real dependency in
    requirements.txt (unlike ultralytics/sam2), but only this code path
    needs it.
    """
    import rasterio
    from rasterio.io import MemoryFile

    with MemoryFile(tiff_bytes) as memfile, memfile.open() as dataset:
        band_count = min(3, dataset.count)
        arr = dataset.read(list(range(1, band_count + 1)))  # (bands, H, W)
        arr = np.transpose(arr, (1, 2, 0))  # (H, W, bands)
        if band_count == 1:
            arr = np.repeat(arr, 3, axis=2)
        if arr.dtype != np.uint8:
            # Solar API RGB bands are typically already uint8, but normalize
            # defensively in case a MEDIUM/LOW quality response differs.
            arr = ((arr - arr.min()) / max(1, arr.max() - arr.min()) * 255).astype(np.uint8)

    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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
    """Returns the configured provider wrapped in a Redis tile cache -- see
    app/services/imagery_cache.py. Caching applies regardless of which
    provider is selected, matching the spec's tile-caching requirement as a
    general capability rather than something each vendor integration has to
    reimplement.
    """
    from app.services.imagery_cache import CachedImageryProvider

    name = get_settings().imagery_provider
    return CachedImageryProvider(_PROVIDERS[name](), provider_name=name)
