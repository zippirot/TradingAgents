"""Structured PM reasoning survives the canonical decision display cap."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tradingagents.memory import publication


def _state():
    return {
        "run_id": str(uuid4()),
        "final_rating": "Hold",
        "final_trade_decision": "Rating: Hold\n" + "D" * 12010,
        "evidence_quality": {"status": "limited"},
        "financial_evidence": {"schema_version": 1, "sources": []},
    }


def _structured(summary="Summary", thesis="Thesis", conditions=None):
    return {
        "portfolio_manager": {
            "structured": {"executive_summary": summary, "investment_thesis": thesis},
            "thesis_candidate": {"conditions": conditions},
        },
    }


def test_record_keeps_pm_summary_thesis_and_stated_conditions_in_full(tmp_path, monkeypatch):
    monkeypatch.setattr(publication, "_utcnow", lambda: datetime(2026, 11, 8, 18, tzinfo=UTC))
    config = {"results_dir": str(tmp_path)}
    state = _state()
    state['run_settings'] = {'decision_horizon_months': 6}
    state["unvalidated_outputs"] = _structured(
        summary="S" * 15000,
        thesis="T" * 20005,
        conditions=[{"metric": "Gross Margin", "threshold": "55.5", "rationale": "R" * 20010}],
    )
    record = publication.publish(config, state, "DOCN", "2026-11-08")
    assert len(record["canonical_decision"]) == 12000
    assert record['run_settings']['decision_horizon_months'] == 6
    assert record["decision_truncated"] is True
    assert record["pm_executive_summary"] == {"text": "S" * 15000, "truncated": False}
    assert record["pm_investment_thesis"] == {"text": "T" * 20000, "truncated": True}
    assert len(record["pm_stated_conditions"]["text"]) == 20000
    assert record["pm_stated_conditions"]["truncated"] is True
    assert '"Gross Margin"' in record["pm_stated_conditions"]["text"]
    assert publication.load_record(config, record["decision_id"]) == record
    assert publication.publish(config, deepcopy(state), "DOCN", "2026-11-08") == record
    state["unvalidated_outputs"]["portfolio_manager"]["structured"]["executive_summary"] = "Changed PM prose"
    with pytest.raises(ValueError, match="already published"):
        publication.publish(config, state, "DOCN", "2026-11-08")
    assert publication.load_record(config, record["decision_id"]) == record


def test_record_hash_stable_and_old_record_bytes_unchanged_on_new_pm_prose(tmp_path, monkeypatch):
    monkeypatch.setattr(publication, "_utcnow", lambda: datetime(2026, 11, 8, 18, tzinfo=UTC))
    config = {"results_dir": str(tmp_path)}
    state = _state()
    old = publication.publish(config, state, "DOCN", "2026-11-08")
    root = publication.record_root(config)
    record_path = root / "records" / f"{old['decision_id']}.json"
    evidence_path = root / old["evidence_snapshot"]["path"]
    old_bytes, evidence_bytes = record_path.read_bytes(), evidence_path.read_bytes()
    assert "pm_executive_summary" not in old
    state["unvalidated_outputs"] = _structured("Later summary", "Later thesis", [{"metric": "Revenue"}])
    assert publication.publish(config, state, "DOCN", "2026-11-08") == old
    assert record_path.read_bytes() == old_bytes
    assert evidence_path.read_bytes() == evidence_bytes
    assert "pm_executive_summary" not in publication.load_record(config, old["decision_id"])

    state["final_trade_decision"] += " Changed original decision."
    with pytest.raises(ValueError, match="already published"):
        publication.publish(config, state, "DOCN", "2026-11-08")
    state["final_trade_decision"] = "Rating: Hold\n" + "D" * 12010
    state["financial_evidence"]["sources"].append({"source_id": "changed"})
    with pytest.raises(ValueError, match="already published"):
        publication.publish(config, state, "DOCN", "2026-11-08")
    assert record_path.read_bytes() == old_bytes
    assert evidence_path.read_bytes() == evidence_bytes


@pytest.mark.parametrize(
    ("pm_output", "field", "expected"),
    [
        ({"structured": {"executive_summary": "Summary only"}},
         "pm_executive_summary", "Summary only"),
        ({"structured": {"investment_thesis": "Thesis only"}},
         "pm_investment_thesis", "Thesis only"),
        ({"structured": {}, "thesis_candidate": {"conditions": [{"metric": "Revenue"}]}},
         "pm_stated_conditions", '[{"metric":"Revenue"}]'),
    ],
)
def test_partial_pm_fields_are_retained_independently_and_sealed(
    tmp_path, monkeypatch, pm_output, field, expected,
):
    monkeypatch.setattr(publication, "_utcnow", lambda: datetime(2026, 11, 8, 18, tzinfo=UTC))
    config = {"results_dir": str(tmp_path)}
    state = _state()
    state["unvalidated_outputs"] = {"portfolio_manager": deepcopy(pm_output)}

    record = publication.publish(config, state, "DOCN", "2026-11-08")
    assert record[field] == {"text": expected, "truncated": False}
    assert record["pm_reasoning_status"] == "unvalidated structured PM output"
    assert {key for key in record if key.startswith("pm_")} == {field, "pm_reasoning_status"}
    assert publication.publish(config, deepcopy(state), "DOCN", "2026-11-08") == record

    path = publication.record_root(config) / "records" / f"{record['decision_id']}.json"
    original_bytes = path.read_bytes()
    if field == "pm_stated_conditions":
        state["unvalidated_outputs"]["portfolio_manager"]["thesis_candidate"]["conditions"] = []
    else:
        source_key = "executive_summary" if field == "pm_executive_summary" else "investment_thesis"
        state["unvalidated_outputs"]["portfolio_manager"]["structured"][source_key] += " changed"
    with pytest.raises(ValueError, match="already published"):
        publication.publish(config, state, "DOCN", "2026-11-08")
    assert path.read_bytes() == original_bytes
