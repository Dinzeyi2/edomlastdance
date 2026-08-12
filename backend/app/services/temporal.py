"""Temporal change detection: compare a current analysis against a prior
year's. Pure logic, no external calls -- real code, not a stub, since it
doesn't depend on anything not already available (imagery + detector +
scorer results for both years).
"""
from dataclasses import dataclass

from app.services.defects import DefectFinding
from app.services.scoring import ScoreResult

WORSENED_THRESHOLD = -5
IMPROVED_THRESHOLD = 5


@dataclass
class TemporalResult:
    previous_score: int | None
    score_delta: int | None
    change_summary: str


def compute_temporal(
    current_score: ScoreResult,
    current_findings: list[DefectFinding],
    previous_score: ScoreResult | None,
    previous_findings: list[DefectFinding] | None,
) -> TemporalResult:
    if previous_score is None:
        return TemporalResult(
            previous_score=None, score_delta=None, change_summary="No prior-year imagery available for comparison."
        )

    delta = current_score.score - previous_score.score
    current_types = {f.type for f in current_findings}
    previous_types = {f.type for f in (previous_findings or [])}
    new_types = sorted(current_types - previous_types)

    if new_types:
        summary = f"New {', '.join(new_types)} visible since prior imagery."
    elif delta <= WORSENED_THRESHOLD:
        summary = "Existing damage appears to have worsened since prior imagery."
    elif delta >= IMPROVED_THRESHOLD:
        summary = "Roof condition appears improved since prior imagery (repair or replacement likely)."
    else:
        summary = "No significant change detected since prior imagery."

    return TemporalResult(previous_score=previous_score.score, score_delta=delta, change_summary=summary)
