"""Application-level geo helpers. Territories and storm events store a GeoJSON
Polygon as text; properties store a plain lat/lon. Point-in-polygon is done
here with Shapely instead of a database GIS extension (ST_Within) -- this is
the deliberate trade documented in the plan: it removes the PostGIS
dependency so the pipeline runs against plain SQLite/Postgres, at the cost of
scaling less gracefully than an indexed DB-side spatial query. Fine for the
lead volumes this product deals in (thousands of properties per territory,
not millions); revisit with PostGIS or a spatial index if that changes.
"""
import json
import random

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry


def polygon_from_geojson(polygon_geojson: str) -> BaseGeometry:
    return shape(json.loads(polygon_geojson))


def point_in_polygon(lat: float, lon: float, polygon_geojson: str) -> bool:
    geom = polygon_from_geojson(polygon_geojson)
    return geom.contains(Point(lon, lat)) or geom.touches(Point(lon, lat))


def random_point_in_polygon(polygon_geojson: str, rng: random.Random) -> tuple[float, float]:
    """Rejection-sample a random (lat, lon) inside the polygon. Used by the
    mock property provider to synthesize addresses within a storm's footprint.
    """
    geom = polygon_from_geojson(polygon_geojson)
    min_lon, min_lat, max_lon, max_lat = geom.bounds
    for _ in range(200):
        lon = rng.uniform(min_lon, max_lon)
        lat = rng.uniform(min_lat, max_lat)
        if geom.contains(Point(lon, lat)):
            return lat, lon
    # Extremely thin/degenerate polygon fallback: just use the centroid.
    centroid = geom.centroid
    return centroid.y, centroid.x


def bounding_box_polygon(center_lat: float, center_lon: float, half_width_deg: float) -> str:
    """Build a simple square GeoJSON polygon around a center point. Used by
    the mock storm provider to fabricate a plausible storm footprint.
    """
    poly = {
        "type": "Polygon",
        "coordinates": [
            [
                [center_lon - half_width_deg, center_lat - half_width_deg],
                [center_lon + half_width_deg, center_lat - half_width_deg],
                [center_lon + half_width_deg, center_lat + half_width_deg],
                [center_lon - half_width_deg, center_lat + half_width_deg],
                [center_lon - half_width_deg, center_lat - half_width_deg],
            ]
        ],
    }
    return json.dumps(poly)
