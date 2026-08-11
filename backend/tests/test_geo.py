from app.pipeline.geo import bounding_box_polygon, point_in_polygon, random_point_in_polygon
import random


def test_point_in_polygon_inside_and_outside():
    polygon = bounding_box_polygon(32.0, -97.0, 0.05)
    assert point_in_polygon(32.0, -97.0, polygon) is True
    assert point_in_polygon(40.0, -97.0, polygon) is False


def test_random_point_in_polygon_is_always_inside():
    polygon = bounding_box_polygon(39.7392, -104.9903, 0.03)
    rng = random.Random(42)
    for _ in range(25):
        lat, lon = random_point_in_polygon(polygon, rng)
        assert point_in_polygon(lat, lon, polygon)
