import pytest

from app.providers.imagery.mock import MockImageryProvider
from app.providers.property.mock import MockPropertyProvider
from app.providers.storm.mock import MockStormProvider
from app.providers.vision.stub import StubVisionProvider


async def test_mock_storm_provider_is_deterministic():
    provider = MockStormProvider()
    first = await provider.fetch_recent_events(region_hint="32.5,-97.1")
    second = await provider.fetch_recent_events(region_hint="32.5,-97.1")
    assert [e.external_ref for e in first] == [e.external_ref for e in second]
    assert len(first) >= 1


@pytest.mark.asyncio
async def test_mock_property_provider_returns_points_inside_polygon():
    storm_provider = MockStormProvider()
    events = await storm_provider.fetch_recent_events(region_hint="Denver, CO")
    property_provider = MockPropertyProvider()
    properties = await property_provider.resolve_properties(events[0].polygon_geojson, max_results=10)
    assert len(properties) >= 1
    assert all(p.address for p in properties)


@pytest.mark.asyncio
async def test_mock_imagery_provider_is_deterministic_per_property():
    from app.providers.base import PropertyData

    prop = PropertyData(
        address="1 Test St",
        county="Test County",
        lat=1.0,
        lon=1.0,
        year_built=2000,
        roof_material_guess="asphalt_shingle",
        footprint_sqft=2000,
        source="mock",
        parcel_ref="abc-123",
    )
    provider = MockImageryProvider()
    first = await provider.fetch_image(prop)
    second = await provider.fetch_image(prop)
    assert first.image_ref == second.image_ref


@pytest.mark.asyncio
async def test_stub_vision_scores_higher_for_severe_storms():
    provider = StubVisionProvider()
    mild = await provider.assess_damage(
        "img-a", {"max_hail_in": 0.4, "max_wind_mph": None, "roof_material_guess": "metal", "year_built": 2018}
    )
    severe = await provider.assess_damage(
        "img-a",
        {"max_hail_in": 2.4, "max_wind_mph": None, "roof_material_guess": "wood_shake", "year_built": 1990},
    )
    assert severe.damage_confidence > mild.damage_confidence
