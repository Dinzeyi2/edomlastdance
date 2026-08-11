"""Deterministic synthetic storm data. No network calls -- seeds a RNG off the
region hint so repeated calls with the same hint are stable (useful for
tests/demos), while different hints/dates produce different storms.
"""
import random
from datetime import date, timedelta

from app.pipeline.geo import bounding_box_polygon
from app.providers.base import StormDataProvider, StormEventData

# A few real hail-prone metro centers, used when no region hint is given.
DEFAULT_CENTERS = [
    ("Dallas-Fort Worth, TX", 32.7767, -96.7970),
    ("Denver, CO", 39.7392, -104.9903),
    ("Oklahoma City, OK", 35.4676, -97.5164),
]


def _parse_region_hint(region_hint: str | None) -> tuple[str, float, float]:
    if region_hint:
        parts = region_hint.split(",")
        if len(parts) == 2:
            try:
                lat, lon = float(parts[0].strip()), float(parts[1].strip())
                return region_hint, lat, lon
            except ValueError:
                pass
        # Treat as a free-text place name -- hash it onto one of the defaults
        # so the same name always maps to the same place.
        idx = sum(ord(c) for c in region_hint) % len(DEFAULT_CENTERS)
        name, lat, lon = DEFAULT_CENTERS[idx]
        return region_hint or name, lat, lon
    name, lat, lon = DEFAULT_CENTERS[0]
    return name, lat, lon


class MockStormProvider(StormDataProvider):
    async def fetch_recent_events(self, region_hint: str | None = None) -> list[StormEventData]:
        label, center_lat, center_lon = _parse_region_hint(region_hint)
        rng = random.Random(f"storm:{label}")

        events: list[StormEventData] = []
        num_events = rng.randint(1, 2)
        for i in range(num_events):
            event_type = rng.choice(["hail", "wind"])
            half_width = rng.uniform(0.03, 0.09)  # roughly 2-6 miles
            jitter_lat = center_lat + rng.uniform(-0.05, 0.05)
            jitter_lon = center_lon + rng.uniform(-0.05, 0.05)
            polygon = bounding_box_polygon(jitter_lat, jitter_lon, half_width)

            events.append(
                StormEventData(
                    event_date=date.today() - timedelta(days=rng.randint(1, 14)),
                    event_type=event_type,
                    polygon_geojson=polygon,
                    max_hail_in=round(rng.uniform(0.75, 2.5), 2) if event_type == "hail" else None,
                    max_wind_mph=round(rng.uniform(58, 90), 1) if event_type == "wind" else None,
                    source="mock",
                    external_ref=f"mock-{label}-{i}",
                )
            )
        return events
