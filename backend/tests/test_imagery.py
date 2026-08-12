from app.services.imagery import MockImageryProvider


async def test_mock_imagery_deterministic_for_same_coords_and_year():
    provider = MockImageryProvider()
    a = await provider.fetch_image(40.7128, -74.0060, 10)
    b = await provider.fetch_image(40.7128, -74.0060, 10)
    assert a.image_bytes == b.image_bytes


async def test_mock_imagery_differs_by_coords():
    provider = MockImageryProvider()
    a = await provider.fetch_image(40.7128, -74.0060, 10)
    b = await provider.fetch_image(51.5074, -0.1278, 10)
    assert a.image_bytes != b.image_bytes


async def test_mock_imagery_historical_differs_from_current():
    provider = MockImageryProvider()
    current = await provider.fetch_image(40.7128, -74.0060, 10)
    historical = await provider.fetch_image(40.7128, -74.0060, 10, year=2020)
    assert current.image_bytes != historical.image_bytes
    assert historical.captured_date.year == 2020
    assert current.captured_date is not None
