"""Frozen publication retry is distinct from a current validated report view."""

import json
from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4

import pytest

from tests.test_publication_graph import graph_and_state
from tradingagents.memory import publication
from tradingagents.reporting import write_report_tree


def frozen(tmp_path):
    app, state = graph_and_state(tmp_path)
    state.update(
        run_id=str(uuid4()),
        run_settings=app.run_settings(),
        publication_versions={"code": "old", "prompt": "old", "schema": 1},
    )
    state["final_trade_decision"] = "Historical canonical REVIEW wording."
    record = publication.publish(app.config, state, "DOCN", state["trade_date"])
    state["publication_record"] = {
        k: record[k] for k in ("decision_id", "published_at", "record_sha256")
    }
    return app, state, record


def test_existing_retry_verifies_disk_before_any_projection(tmp_path, monkeypatch):
    app, state, record = frozen(tmp_path)
    import tradingagents.graph.trading_graph as graph

    project = Mock(side_effect=AssertionError("must not reproject frozen original"))
    monkeypatch.setattr(graph, "enforce_publication", project)
    for _ in range(2):
        app.record_decision("DOCN", state["trade_date"], state)
    assert state["final_trade_decision"] == "Historical canonical REVIEW wording."
    assert publication.load_record(app.config, record["decision_id"]) == record
    project.assert_not_called()


def test_mutated_original_is_rejected_despite_real_or_forged_marker(tmp_path):
    app, state, _ = frozen(tmp_path)
    state["final_trade_decision"] = "Changed canonical wording"
    with pytest.raises(ValueError, match="different canonical content"):
        app.record_decision("DOCN", state["trade_date"], state)
    with pytest.raises(ValueError, match="different canonical content"):
        write_report_tree(state, "DOCN", tmp_path / "export", publication_config=app.config)


def test_report_exports_original_snapshot_and_labels_current_projection(tmp_path):
    app, state, record = frozen(tmp_path)
    original = deepcopy(state)
    write_report_tree(state, "DOCN", tmp_path / "export", publication_config=app.config)
    exported = json.loads((tmp_path / "export/evidence.json").read_text())
    assert exported == publication.load_evidence(app.config, record)
    assert state == original
    for suffix in ("md", "html"):
        text = (tmp_path / f"export/complete_report.{suffix}").read_text()
        assert "Current validated presentation of a verified immutable publication" in text
    write_report_tree(state, "DOCN", tmp_path / "generic")
    assert (
        "Historical publication identity not verified"
        in (tmp_path / "generic/complete_report.md").read_text()
    )


def test_forged_marker_without_record_does_not_bypass_new_run_gate(tmp_path):
    app, state = graph_and_state(tmp_path)
    state.update(
        run_id=str(uuid4()),
        final_rating="Buy",
        final_trade_decision="Buy",
        publication_record={"decision_id": "fake", "published_at": "fake", "record_sha256": "fake"},
    )
    app.record_decision("DOCN", state["trade_date"], state)
    assert state["final_rating"] == "REVIEW"
    assert publication.load_record(app.config, state["run_id"])["canonical_rating"] == "REVIEW"


def test_corrupt_disk_snapshot_cannot_use_state_marker_as_authority(tmp_path):
    app, state, record = frozen(tmp_path)
    path = publication.record_root(app.config) / record["evidence_snapshot"]["path"]
    path.write_text("{}")
    with pytest.raises(ValueError, match="Evidence integrity"):
        app.record_decision("DOCN", state["trade_date"], state)
    with pytest.raises(ValueError, match="Evidence integrity"):
        write_report_tree(state, "DOCN", tmp_path / "export", publication_config=app.config)
