"""Real storm data source, stubbed for future implementation.

Intended source: NOAA NCEI Storm Events Database
(https://www.ncdc.noaa.gov/stormevents/) for historical hail/wind reports, or
NEXRAD-derived hail-swath products for near-real-time detection. Swap this in
via STORM_PROVIDER=noaa once implemented -- app/providers/__init__.py already
routes to it, and nothing in app/pipeline needs to change.
"""
from app.providers.base import StormDataProvider, StormEventData


class NoaaStormProvider(StormDataProvider):
    async def fetch_recent_events(self, region_hint: str | None = None) -> list[StormEventData]:
        raise NotImplementedError(
            "NOAA storm data integration not yet implemented. "
            "Set STORM_PROVIDER=mock for now, or implement this against the "
            "NOAA NCEI Storm Events API / NEXRAD hail-swath feed."
        )
