import asyncio

from app.services.footprint import CenterCropProvider, building_id_for


def test_building_id_is_deterministic_and_rounds_coordinates():
    a = building_id_for(40.712800, -74.006000)
    b = building_id_for(40.7128001, -74.0060004)  # sub-meter difference
    c = building_id_for(41.0, -74.0)
    assert a == b
    assert a != c
    assert a.startswith("bld_")


def test_center_crop_bbox_is_inset_and_normalized():
    result = asyncio.run(CenterCropProvider().get_footprint(0.0, 0.0))
    x0, y0, x1, y1 = result.bbox
    assert 0 < x0 < x1 < 1
    assert 0 < y0 < y1 < 1
    assert result.source == "center_crop"
    assert result.polygon_geojson is None
