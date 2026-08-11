from app.pipeline.scoring import compute_priority_score, estimate_job_value, normalize_storm_severity


def test_estimate_job_value_uses_material_cost():
    shingle = estimate_job_value(2000, "asphalt_shingle")
    metal = estimate_job_value(2000, "metal")
    assert metal > shingle > 0


def test_estimate_job_value_falls_back_for_unknown_material():
    value = estimate_job_value(2000, "solar_tile_exotic")
    assert value > 0


def test_normalize_storm_severity_hail_vs_wind():
    assert normalize_storm_severity(2.5, None) == 1.0
    assert normalize_storm_severity(None, 90) == 1.0
    assert normalize_storm_severity(None, 40) == 0.0
    assert 0 < normalize_storm_severity(1.0, None) < 1.0


def test_compute_priority_score_bounded_and_monotonic():
    low = compute_priority_score(0.1, max_hail_in=0.5, max_wind_mph=None, estimated_job_value=5000)
    high = compute_priority_score(0.9, max_hail_in=2.5, max_wind_mph=None, estimated_job_value=25000)
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low
