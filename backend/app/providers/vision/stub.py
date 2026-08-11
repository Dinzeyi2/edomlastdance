"""Deterministic, free damage scorer -- does not look at the image at all,
just derives a plausible confidence from storm severity and roof attributes
passed in `context`. This is the default VISION_PROVIDER so the whole
pipeline runs with zero API cost and zero external calls; swap to
VISION_PROVIDER=claude for a real LLM vision assessment of the image.
"""
import hashlib
import random

from app.providers.base import DamageAssessmentData, VisionProvider

OLDER_ROOF_YEAR_CUTOFF = 2005
SOFT_MATERIALS = {"asphalt_shingle", "wood_shake"}


class StubVisionProvider(VisionProvider):
    async def assess_damage(self, image_ref: str, context: dict) -> DamageAssessmentData:
        seed = hashlib.sha256(image_ref.encode("utf-8")).hexdigest()
        rng = random.Random(seed)

        base = rng.uniform(0.05, 0.35)

        hail_in = context.get("max_hail_in") or 0
        wind_mph = context.get("max_wind_mph") or 0
        severity_bonus = min(0.45, hail_in * 0.22) + min(0.25, max(0, wind_mph - 50) * 0.006)

        material = context.get("roof_material_guess")
        material_bonus = 0.08 if material in SOFT_MATERIALS else 0.0

        year_built = context.get("year_built")
        age_bonus = 0.07 if year_built and year_built < OLDER_ROOF_YEAR_CUTOFF else 0.0

        confidence = max(0.0, min(1.0, base + severity_bonus + material_bonus + age_bonus))

        notes = (
            f"[stub] heuristic score from storm severity (hail={hail_in}in, wind={wind_mph}mph), "
            f"material={material}, year_built={year_built}. No image was actually inspected -- "
            f"set VISION_PROVIDER=claude for a real assessment."
        )

        return DamageAssessmentData(
            damage_confidence=round(confidence, 3),
            material_guess=material,
            notes=notes,
            provider="stub",
        )
