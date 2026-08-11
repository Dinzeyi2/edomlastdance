"""Turns a damage assessment + storm + property into a priority score and a
dollar estimate. Deliberately simple/linear for v1 -- weights and lookup
tables are named constants so they're easy to tune once real outcome data
(Lead.status) starts coming back through the feedback loop.
"""

# --- estimated_job_value ---------------------------------------------------

MATERIAL_COST_PER_SQFT = {
    "asphalt_shingle": 5.5,
    "metal": 11.0,
    "tile": 14.0,
    "wood_shake": 9.5,
}
DEFAULT_MATERIAL_COST_PER_SQFT = 6.5

# Roofs are pitched, so surface area exceeds the flat footprint. A flat mock-up
# value; a real system would derive this from imagery/parcel geometry.
ROOF_PITCH_AREA_FACTOR = 1.3

# --- priority_score ----------------------------------------------------------

WEIGHT_DAMAGE_CONFIDENCE = 0.5
WEIGHT_STORM_SEVERITY = 0.3
WEIGHT_JOB_VALUE = 0.2

HAIL_SEVERITY_CAP_IN = 2.5  # hail diameter (inches) treated as "max severity"
WIND_SEVERITY_FLOOR_MPH = 50.0  # winds below this contribute ~0 severity
WIND_SEVERITY_CAP_MPH = 90.0

JOB_VALUE_NORMALIZATION_CAP = 30_000.0  # job value at/above this scores 1.0


def estimate_job_value(footprint_sqft: float | None, roof_material_guess: str | None) -> float:
    footprint = footprint_sqft or 1800.0
    cost_per_sqft = MATERIAL_COST_PER_SQFT.get(roof_material_guess, DEFAULT_MATERIAL_COST_PER_SQFT)
    return round(footprint * ROOF_PITCH_AREA_FACTOR * cost_per_sqft, 2)


def normalize_storm_severity(max_hail_in: float | None, max_wind_mph: float | None) -> float:
    hail_score = min(1.0, (max_hail_in or 0.0) / HAIL_SEVERITY_CAP_IN)
    wind_range = WIND_SEVERITY_CAP_MPH - WIND_SEVERITY_FLOOR_MPH
    wind_score = min(1.0, max(0.0, ((max_wind_mph or 0.0) - WIND_SEVERITY_FLOOR_MPH) / wind_range))
    return max(hail_score, wind_score)


def compute_priority_score(
    damage_confidence: float,
    max_hail_in: float | None,
    max_wind_mph: float | None,
    estimated_job_value: float,
) -> float:
    severity = normalize_storm_severity(max_hail_in, max_wind_mph)
    normalized_value = min(1.0, estimated_job_value / JOB_VALUE_NORMALIZATION_CAP)
    score = (
        WEIGHT_DAMAGE_CONFIDENCE * damage_confidence
        + WEIGHT_STORM_SEVERITY * severity
        + WEIGHT_JOB_VALUE * normalized_value
    )
    return round(min(1.0, max(0.0, score)), 4)
