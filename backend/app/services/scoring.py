"""Turns a list of defect findings into a 0-100 Roof Opportunity Score. Two
layers, matching your spec's two options:

  1. compute_score(): deterministic, no LLM, always runs. Weights are named
     constants so they're easy to tune once real roofer feedback
     (app/db/models.py Feedback table) starts coming back.
  2. ReasoningProvider: optional LLM pass over the same findings, off by
     default (LLM_PROVIDER=none) per your note that this can stay in
     Lovable instead. OpenAIReasoningProvider is real, working code -- it
     just needs OPENAI_API_KEY and is not exercised unless you opt in.
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import get_settings
from app.services.defects import DefectFinding

SEVERITY_WEIGHT = {"minor": 1.0, "moderate": 2.2, "severe": 4.0}

# Relative cost/urgency impact per defect type -- structural/water-intrusion
# issues (missing shingles, tarps already up, flashing, ponding) weighted
# heavier than cosmetic ones (staining, debris).
TYPE_WEIGHT = {
    "missing_shingles": 3.0,
    "tarps": 3.0,
    "flashing_damage": 2.6,
    "ponding": 2.5,
    "cracking": 2.2,
    "rust": 1.8,
    "patchwork": 1.5,
    "staining": 1.2,
    "vegetation": 1.0,
    "debris": 0.8,
}
DEFAULT_TYPE_WEIGHT = 1.5

MAX_DEDUCTION = 88
DEDUCTION_SCALE = 3.2

CONDITION_GOOD_MIN = 80
CONDITION_AGING_MIN = 55


@dataclass
class ScoreResult:
    score: int
    condition: str  # good | aging | poor
    confidence: float


def compute_score(findings: list[DefectFinding]) -> ScoreResult:
    if not findings:
        # No findings could mean a genuinely sound roof, or a bad/empty crop
        # -- keep confidence modest rather than claiming certainty either way.
        return ScoreResult(score=96, condition="good", confidence=0.6)

    impact = sum(SEVERITY_WEIGHT[f.severity] * TYPE_WEIGHT.get(f.type, DEFAULT_TYPE_WEIGHT) for f in findings)
    deduction = min(MAX_DEDUCTION, impact * DEDUCTION_SCALE)
    score = round(max(5, 100 - deduction))

    if score >= CONDITION_GOOD_MIN:
        condition = "good"
    elif score >= CONDITION_AGING_MIN:
        condition = "aging"
    else:
        condition = "poor"

    avg_finding_confidence = sum(f.confidence for f in findings) / len(findings)
    confidence = round(min(0.97, 0.55 + 0.03 * len(findings) + avg_finding_confidence * 0.2), 3)

    return ScoreResult(score=score, condition=condition, confidence=confidence)


# --- optional LLM reasoning pass ---------------------------------------------

SYSTEM_PROMPT = (
    "You are assisting a roofing sales team by reviewing an automated roof "
    "defect scan. You'll be given a deterministic score and a list of "
    "detected findings (type, severity, confidence). Respond with STRICT "
    "JSON only: "
    '{"score": <int 0-100, your own refined score>, '
    '"condition": <"good"|"aging"|"poor">, '
    '"confidence": <float 0-1>, '
    '"summary": <1-3 sentence human-readable explanation a sales rep could '
    "read to a homeowner>}. "
    "Use the deterministic score as a strong prior; only deviate if the "
    "findings clearly justify it."
)


@dataclass
class ReasoningResult:
    score: int
    condition: str
    confidence: float
    summary: str


class ReasoningProvider(ABC):
    @abstractmethod
    async def refine(self, deterministic: ScoreResult, findings: list[DefectFinding]) -> ReasoningResult | None:
        """Return a refined result, or None to just use the deterministic
        score as-is."""
        raise NotImplementedError


class NullReasoningProvider(ReasoningProvider):
    async def refine(self, deterministic: ScoreResult, findings: list[DefectFinding]) -> ReasoningResult | None:
        return None


class OpenAIReasoningProvider(ReasoningProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai requires OPENAI_API_KEY to be set.")
        from openai import AsyncOpenAI  # lazy import, only needed on this path

        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_reasoning_model

    async def refine(self, deterministic: ScoreResult, findings: list[DefectFinding]) -> ReasoningResult | None:
        findings_payload = [
            {"type": f.type, "severity": f.severity, "confidence": f.confidence, "tile_index": list(f.tile_index)}
            for f in findings
        ]
        user_content = json.dumps(
            {
                "deterministic_score": deterministic.score,
                "deterministic_condition": deterministic.condition,
                "findings": findings_payload,
            }
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None

        return ReasoningResult(
            score=int(parsed.get("score", deterministic.score)),
            condition=str(parsed.get("condition", deterministic.condition)),
            confidence=float(parsed.get("confidence", deterministic.confidence)),
            summary=str(parsed.get("summary", "")),
        )


_PROVIDERS = {"none": NullReasoningProvider, "openai": OpenAIReasoningProvider}


def get_reasoning_provider() -> ReasoningProvider:
    return _PROVIDERS[get_settings().llm_provider]()
