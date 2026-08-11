"""Deterministic synthetic imagery. Points each property at one of the
bundled schematic fixture images under backend/fixtures/sample_roofs/ (see
scripts/generate_fixtures.py) -- these are placeholders, not real aerial
photos, and are picked by hashing the parcel_ref, not by any real damage
signal. Swap in via IMAGERY_PROVIDER=nearmap (or similar) once a real vendor
is wired up.
"""
import hashlib
from datetime import date, timedelta
from pathlib import Path

from app.providers.base import ImageryAssetData, ImageryProvider, PropertyData

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "sample_roofs"
FIXTURE_NAMES = [
    "roof_pristine.png",
    "roof_light_damage.png",
    "roof_moderate_damage.png",
    "roof_severe_damage.png",
]


class MockImageryProvider(ImageryProvider):
    async def fetch_image(self, prop: PropertyData) -> ImageryAssetData:
        digest = hashlib.sha256(prop.parcel_ref.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % len(FIXTURE_NAMES)
        image_path = FIXTURES_DIR / FIXTURE_NAMES[idx]
        return ImageryAssetData(
            image_ref=str(image_path),
            captured_date=date.today() - timedelta(days=int(digest[8:10], 16) % 60),
            provider="mock",
        )
