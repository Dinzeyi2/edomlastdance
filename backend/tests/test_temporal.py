from app.services.defects import DefectFinding
from app.services.scoring import ScoreResult
from app.services.temporal import compute_temporal


def _finding(type_):
    return DefectFinding(type=type_, severity="moderate", bbox=(0, 0, 0.1, 0.1), tile_index=(0, 0), confidence=0.7)


def test_no_previous_data_returns_none_delta():
    result = compute_temporal(ScoreResult(80, "good", 0.8), [], None, None)
    assert result.previous_score is None
    assert result.score_delta is None
    assert "no prior" in result.change_summary.lower()


def test_new_defect_type_flagged_in_summary():
    current = [_finding("staining")]
    previous = []
    result = compute_temporal(
        ScoreResult(70, "aging", 0.8), current, ScoreResult(90, "good", 0.8), previous
    )
    assert result.score_delta == -20
    assert "staining" in result.change_summary


def test_improved_score_flagged():
    result = compute_temporal(
        ScoreResult(90, "good", 0.9), [], ScoreResult(50, "poor", 0.7), []
    )
    assert result.score_delta == 40
    assert "improved" in result.change_summary.lower()


def test_no_significant_change():
    result = compute_temporal(
        ScoreResult(80, "good", 0.9), [_finding("debris")], ScoreResult(81, "good", 0.9), [_finding("debris")]
    )
    assert "no significant change" in result.change_summary.lower()
