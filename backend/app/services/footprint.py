"""Building footprint isolation: given the fetched image (+ coordinates),
return the region that's actually roof, so the defect detector isn't looking
at trees/street/neighbors. Three tiers, matching the order you laid out:

  1. center_crop (default): a fixed inset rectangle. This is deliberately the
     "simple center-crop" you described replacing -- it's the honest
     baseline every request can use with zero dependencies.
  2. osm: a real building polygon from OpenStreetMap via the public Overpass
     API (free, no key). Implemented for real below -- BUT this sandbox's
     network egress policy blocks overpass-api.de (confirmed: 403 from the
     egress proxy), so I could not execute a live call to verify it. It
     should work once deployed on Railway (which has normal internet
     egress); worth a smoke test right after deploy.
  3. sam2: zero-shot pixel segmentation. Stubbed -- needs the `sam2` package,
     a multi-GB checkpoint download, and GPU-class compute to run at
     reasonable speed, none of which this environment has.

Note OSM gives a real polygon in lat/lng, not pixel coordinates in whatever
image IMAGERY_PROVIDER returned -- projecting a real-world polygon onto an
image requires knowing that image's ground-sample-distance and orientation
(real georeferencing metadata a real imagery vendor would provide). Until a
real imagery provider is wired in, OsmFootprintProvider returns the real
polygon/area (useful for scoring) alongside the same center-crop pixel bbox
used for the placeholder mask image.
"""
import hashlib
import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from shapely.geometry import Point, shape

from app.config import get_settings
from app.services.roof_art import SIZE

logger = logging.getLogger(__name__)

CENTER_CROP_MARGIN_PX = 60  # matches the margin used by roof_art.generate_schematic_roof
CENTER_CROP_BBOX = (
    CENTER_CROP_MARGIN_PX / SIZE,
    CENTER_CROP_MARGIN_PX / SIZE,
    (SIZE - CENTER_CROP_MARGIN_PX) / SIZE,
    (SIZE - CENTER_CROP_MARGIN_PX) / SIZE,
)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_SEARCH_RADIUS_M = 40
OVERPASS_TIMEOUT_S = 20.0


def building_id_for(lat: float, lng: float) -> str:
    """Deterministic stable ID for a building, from rounded coordinates
    (~0.1m precision at 6 decimals) so repeat requests for the same address
    resolve to the same building_id."""
    key = f"{round(lat, 6)},{round(lng, 6)}"
    return "bld_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass
class FootprintResult:
    bbox: tuple[float, float, float, float]  # normalized (x0, y0, x1, y1)
    polygon_geojson: str | None  # real lat/lng polygon, when available (osm)
    area_sqm: float | None
    source: str


class FootprintProvider(ABC):
    @abstractmethod
    async def get_footprint(self, lat: float, lng: float) -> FootprintResult:
        raise NotImplementedError


class CenterCropProvider(FootprintProvider):
    async def get_footprint(self, lat: float, lng: float) -> FootprintResult:
        return FootprintResult(
            bbox=CENTER_CROP_BBOX, polygon_geojson=None, area_sqm=None, source="center_crop"
        )


class OsmFootprintProvider(FootprintProvider):
    """Queries the public Overpass API for a `building` way within
    OVERPASS_SEARCH_RADIUS_M of the point, picks the one whose polygon
    actually contains the point (Overpass's `around` filter is a bounding
    search, not a strict containment check), and returns its real polygon +
    area. Falls back to the center-crop bbox for the placeholder mask image
    since we don't have georeferenced imagery to project onto yet -- see the
    module docstring.
    """

    async def get_footprint(self, lat: float, lng: float) -> FootprintResult:
        query = (
            f"[out:json][timeout:{int(OVERPASS_TIMEOUT_S)}];"
            f"way(around:{OVERPASS_SEARCH_RADIUS_M},{lat},{lng})[building];"
            "out geom;"
        )
        async with httpx.AsyncClient(timeout=OVERPASS_TIMEOUT_S) as client:
            resp = await client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            payload = resp.json()

        point = Point(lng, lat)
        for element in payload.get("elements", []):
            geometry = element.get("geometry")
            if not geometry:
                continue
            coords = [(node["lon"], node["lat"]) for node in geometry]
            if coords[0] != coords[-1]:
                coords.append(coords[0])  # close the ring
            polygon = shape({"type": "Polygon", "coordinates": [coords]})
            if polygon.contains(point) or polygon.touches(point):
                # Shapely area is in degrees^2 for lon/lat geometry -- rough
                # meters^2 conversion at this latitude, fine for an estimate.
                meters_per_degree_lat = 111_320
                meters_per_degree_lng = 111_320 * abs(math.cos(math.radians(lat)))
                area_sqm = polygon.area * meters_per_degree_lat * meters_per_degree_lng
                return FootprintResult(
                    bbox=CENTER_CROP_BBOX,
                    polygon_geojson=json.dumps({"type": "Polygon", "coordinates": [coords]}),
                    area_sqm=round(area_sqm, 1),
                    source="osm",
                )

        logger.warning("no OSM building found within %sm of (%s, %s), falling back to center_crop", OVERPASS_SEARCH_RADIUS_M, lat, lng)
        return FootprintResult(bbox=CENTER_CROP_BBOX, polygon_geojson=None, area_sqm=None, source="osm_fallback")


class Sam2FootprintProvider(FootprintProvider):
    """Real zero-shot segmentation, stubbed. To implement: `pip install
    sam2`, download a checkpoint (e.g. sam2-hiera-large, ~900MB+), load it
    once at process start (not per-request), run mask prediction seeded by
    the image center or an OSM-derived point, and convert the returned mask
    to a normalized bbox (or keep the full mask if the detector should run
    on masked pixels rather than a crop). GPU strongly recommended -- CPU
    inference is workable but slow per request.
    """

    async def get_footprint(self, lat: float, lng: float) -> FootprintResult:
        raise NotImplementedError(
            "SAM-2 footprint segmentation not yet implemented. Set FOOTPRINT_PROVIDER=center_crop "
            "or FOOTPRINT_PROVIDER=osm for now."
        )


_PROVIDERS = {
    "center_crop": CenterCropProvider,
    "osm": OsmFootprintProvider,
    "sam2": Sam2FootprintProvider,
}


def get_footprint_provider() -> FootprintProvider:
    return _PROVIDERS[get_settings().footprint_provider]()
