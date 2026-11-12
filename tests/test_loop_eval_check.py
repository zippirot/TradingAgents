"""An evaluator's record is checked before its scores are used."""
from scripts.loop_eval_check import WEIGHTS, line, problems


def _record(**scores):
    parts = {name: {"score": 8, "weight": float(weight)} for name, weight in WEIGHTS.items()}
    return {"identity": {"rubric_version": "TAE-1.1-loop1"}, "decision_components": parts,
            "scores": {"research_quality": 9, "investment_decision_quality": 7.5, "decision_weighted": 8.0, **scores},
            "critical_failures": [{"rule": "CF1", "triggered": True}, {"rule": "CF2", "triggered": False}]}


def test_a_consistent_record_passes_and_gives_a_ledger_line():
    record = _record()
    assert problems(record) == []
    assert "Decision 7.5 (weighted 8.0)" in line(record) and "caps: CF1 |" in line(record)


def test_a_weighted_score_that_does_not_recompute_is_rejected():
    assert any("components give 8.0" in text for text in problems(_record(decision_weighted=8.6)))


def test_a_changed_weight_a_missing_component_and_a_missing_version_are_rejected():
    record = _record()
    record["decision_components"]["D1"]["weight"] = 0.30
    del record["decision_components"]["D7"]
    record["identity"] = {}
    found = " ".join(problems(record))
    assert "D1 weight is 0.3" in found and "D7 lacks" in found and "rubric_version" in found
