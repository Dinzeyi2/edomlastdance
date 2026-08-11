"""Deterministic synthetic property/parcel data for a given storm polygon.
Stands in for a real parcel data vendor (see regrid.py) -- generates
plausible addresses, build years, and roof materials scattered inside the
polygon.
"""
import hashlib
import random

from app.pipeline.geo import random_point_in_polygon
from app.providers.base import PropertyData, PropertyDataProvider

STREET_NAMES = [
    "Oak", "Maple", "Cedar", "Elm", "Willow", "Birch", "Pine", "Sycamore",
    "Magnolia", "Hickory", "Aspen", "Meadow", "Ridge", "Creek", "Prairie",
]
STREET_SUFFIXES = ["St", "Ave", "Dr", "Ln", "Ct", "Rd"]
ROOF_MATERIALS = ["asphalt_shingle", "asphalt_shingle", "asphalt_shingle", "metal", "tile", "wood_shake"]
COUNTIES = ["Tarrant County", "Dallas County", "Denton County", "Collin County"]


class MockPropertyProvider(PropertyDataProvider):
    async def resolve_properties(self, polygon_geojson: str, max_results: int = 50) -> list[PropertyData]:
        seed = hashlib.sha256(polygon_geojson.encode("utf-8")).hexdigest()
        rng = random.Random(seed)
        count = rng.randint(min(15, max_results), max_results)

        properties: list[PropertyData] = []
        for i in range(count):
            lat, lon = random_point_in_polygon(polygon_geojson, rng)
            house_number = rng.randint(100, 9999)
            street = f"{rng.choice(STREET_NAMES)} {rng.choice(STREET_SUFFIXES)}"
            parcel_ref = f"{seed[:12]}-{i}"
            properties.append(
                PropertyData(
                    address=f"{house_number} {street}",
                    county=rng.choice(COUNTIES),
                    lat=lat,
                    lon=lon,
                    year_built=rng.randint(1965, 2020),
                    roof_material_guess=rng.choice(ROOF_MATERIALS),
                    footprint_sqft=round(rng.uniform(1200, 3800), 0),
                    source="mock",
                    parcel_ref=parcel_ref,
                )
            )
        return properties
