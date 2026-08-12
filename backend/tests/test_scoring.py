from app.services.defects import DefectFinding
from app.services.scoring import compute_score


def _finding(type_="staining", severity="minor", confidence=0.6):
    return DefectFinding(type=type_, severity=severity, bbox=(0.1, 0.1, 0.2, 0.2), tile_index=(0, 0), confidence=confidence)


def test_no_findings_scores_high_confidence_modest():
    result = compute_score([])
    assert result.score >= 90
    assert result.condition == "good"
    assert result.confidence < 0.9  # deliberately not overconfident on "nothing found"


def test_more_severe_findings_score_lower():
    mild = compute_score([_finding(severity="minor")])
    severe = compute_score([_finding(type_="missing_shingles", severity="severe")])
    assert severe.score < mild.score


def test_score_bounded_0_100():
    many_severe = [_finding(type_="tarps", severity="severe") for _ in range(50)]
    result = compute_score(many_severe)
    assert 0 <= result.score <= 100


def test_condition_thresholds():
    assert compute_score([]).condition == "good"
    poor = compute_score([_finding(type_="missing_shingles", severity="severe") for _ in range(10)])
    assert poor.condition == "poor"
