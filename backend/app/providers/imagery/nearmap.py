"""Real imagery source, stubbed for future implementation.

Intended source: Nearmap (high-frequency post-storm aerial capture) or
EagleView, with Google/Bing aerial tiles as a lower-cost fallback for areas
without recent Nearmap coverage. Swap in via IMAGERY_PROVIDER=nearmap once
implemented.
"""
from app.providers.base import ImageryAssetData, ImageryProvider, PropertyData


class NearmapImageryProvider(ImageryProvider):
    async def fetch_image(self, prop: PropertyData) -> ImageryAssetData:
        raise NotImplementedError(
            "Nearmap imagery integration not yet implemented. "
            "Set IMAGERY_PROVIDER=mock for now."
        )
