"""Real property/parcel data source, stubbed for future implementation.

Intended sources: Regrid (parcel boundaries + attributes) and/or ATTOM Data /
CoreLogic for enriched building attributes (year built, assessed value).
Swap in via PROPERTY_PROVIDER=regrid once implemented.
"""
from app.providers.base import PropertyData, PropertyDataProvider


class RegridPropertyProvider(PropertyDataProvider):
    async def resolve_properties(self, polygon_geojson: str, max_results: int = 50) -> list[PropertyData]:
        raise NotImplementedError(
            "Regrid/ATTOM property data integration not yet implemented. "
            "Set PROPERTY_PROVIDER=mock for now."
        )
