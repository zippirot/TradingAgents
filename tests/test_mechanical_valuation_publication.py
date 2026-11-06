"""B1 publication remains a deterministic diagnostic and preserves legacy replay."""
from copy import deepcopy

from tests.test_valuation_reference_flow import flow_fixture


def prepared_state(monkeypatch):
    from tradingagents.agents import valuation_reference_flow as flow
    state, config, _, _ = flow_fixture(monkeypatch)
    monkeypatch.setattr(flow, "default_peer_selection", lambda *a: {
        "kind": "previous", "status": "available", "reason": None,
        "peers": [{"ticker": "AKAM", "reason": "Cloud infrastructure"}]})
    return {**state, **flow.acquire_reference_inputs(state, config),
            "evidence_quality": {"status": "limited"}, "final_rating": "Hold"}


def test_new_small_peer_set_has_individuals_without_pooled_range_and_legacy_replays(monkeypatch):
    from tradingagents.agents import valuation_reference_flow as flow
    state = prepared_state(monkeypatch)
    record = state["valuation_reference"]
    assert record["schema_version"] == 3
    assert len(record["peers"]["accepted"]) == 1
    assert record["peers"]["range"]["status"] == "unavailable"
    text = flow.render_valuation_reference(record)
    assert "AKAM" in text and "fewer than three" in text.lower()
    assert "Separate peer range:" not in text
    assert flow.replay_valuation_reference(state, record) == record
    old = deepcopy(record)
    old["schema_version"] = 2
    old = flow._assemble(state, old)
    assert old["peers"]["range"]["status"] == "available"
    assert flow.replay_valuation_reference(state, old) == old
    # Old empty defaults must preserve their original unavailable reason too.
    old["default_selection"]["peers"] = []
    old = flow._assemble(state, old)
    assert old["default_peers"]["range"]["reason"] == "No usable peer multiples"
    assert flow.replay_valuation_reference(state, old) == old


def test_grid_is_recomputed_at_publication_and_never_sets_rating_or_model_target(monkeypatch):
    from tradingagents.agents.output_validation import enforce_publication
    state = prepared_state(monkeypatch)
    state["mechanical_valuation_grid"] = {"status": "available", "conditional_price": "999999"}
    before = deepcopy(state)
    update = enforce_publication(state)
    assert state == before
    assert update["mechanical_valuation_grid"] != state["mechanical_valuation_grid"]
    assert "999999" not in str(update["mechanical_valuation_grid"])
    assert update.get("final_rating", state["final_rating"]) == "Hold"
    assert "mechanical sensitivity from reference ranges, not a forecast" not in update["final_trade_decision"].lower()
    # The separate report panel must not become settlement learning or a target.
    assert "mechanical_valuation_grid" not in update["target_validation"]
    public = {**state, **update}
    assert {**public, **enforce_publication(public)} == public


def test_review_withholds_grid_and_preserves_no_action_authority(monkeypatch):
    from tradingagents.agents.output_validation import enforce_publication
    state = prepared_state(monkeypatch)
    state["evidence_quality"] = {"status": "insufficient", "checks": []}
    state["mechanical_valuation_grid"] = {"status": "available", "conditional_price": "999999"}
    update = enforce_publication(state)
    assert update["mechanical_valuation_grid"]["status"] == "unavailable"
    assert update["final_rating"].lower() == "review"
    assert "999999" not in update["final_trade_decision"]


def test_markdown_html_and_snapshot_include_recomputed_grid(monkeypatch, tmp_path):
    import json

    from tradingagents.reporting import write_report_tree
    state = prepared_state(monkeypatch)
    state["mechanical_valuation_grid"] = {"status": "available", "conditional_price": "999999"}
    write_report_tree(state, "DOCN", tmp_path)
    for name in ("complete_report.md", "complete_report.html"):
        text = (tmp_path / name).read_text()
        assert "Mechanical sensitivity" in text
        assert "999999" not in text
    snapshot = json.loads((tmp_path / "evidence.json").read_text())
    assert "mechanical_valuation_grid" in snapshot
    assert "999999" not in str(snapshot["mechanical_valuation_grid"])


def test_cli_pane_is_separate_from_decision(monkeypatch):
    import io

    from rich.console import Console

    from cli import display
    from tradingagents.agents import mechanical_valuation

    state = prepared_state(monkeypatch)
    monkeypatch.setattr(mechanical_valuation, "mechanical_valuation_grid", lambda state: {
        "status": "unavailable", "reason": "B1_GRID_EXCLUSION_SENTINEL"})
    stream = io.StringIO()
    monkeypatch.setattr(display, "console", Console(file=stream, width=160, color_system=None))
    display.display_complete_report(state)
    assert "B1_GRID_EXCLUSION_SENTINEL" in stream.getvalue()
    assert "mechanical_valuation_grid" not in state


def test_publication_retry_memory_and_reflection_exclude_grid(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from tradingagents.agents import mechanical_valuation
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory import publication, publication_outcomes, settlement
    from tradingagents.memory.log import TradingMemoryLog

    state = prepared_state(monkeypatch)
    monkeypatch.setattr(mechanical_valuation, "mechanical_valuation_grid", lambda state: {
        "status": "unavailable", "reason": "B1_GRID_EXCLUSION_SENTINEL"})
    app = object.__new__(TradingAgentsGraph)
    app.config = {"results_dir": str(tmp_path), "memory_log_path": str(tmp_path / "memory.md")}
    app.run_settings = lambda: {"version": "test"}
    app.outcome_summary = lambda *a, **k: "No measured outcome yet"
    app.memory_log = TradingMemoryLog(app.config)
    attempts = []
    def interrupted(*args):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("projection interruption")
    app._log_state = interrupted
    import pytest
    with pytest.raises(OSError, match="projection interruption"):
        app.record_decision("DOCN", state["trade_date"], state)
    app.record_decision("DOCN", state["trade_date"], state)
    assert len(publication.list_records(app.config)) == 1
    assert len(app.memory_log.load_entries()) == 1
    entry = app.memory_log.load_entries()[0]
    assert "B1_GRID_EXCLUSION_SENTINEL" not in entry["decision"]
    record = publication.list_records(app.config)[0]
    assert "B1_GRID_EXCLUSION_SENTINEL" not in record["canonical_decision"]
    snapshot = publication.load_evidence(app.config, record)
    assert snapshot["mechanical_valuation_grid"]["reason"] == "B1_GRID_EXCLUSION_SENTINEL"
    # Fixture outcomes isolate the real publication/memory/reflection routing.
    monkeypatch.setattr(publication_outcomes, "settle_publications", lambda *a, **k: {"settled": [], "failed": []})
    monkeypatch.setattr(settlement, "_returns_for_entry", lambda *a, **k: (0.1, 0.05, 5, "2026-10-27", "SPY"))
    seen = []
    reflector = SimpleNamespace(reflect_on_final_decision=lambda **kwargs: seen.append(kwargs["final_decision"]) or "Fixture reflection")
    result = settlement.settle_pending("DOCN", app.memory_log, reflector, app.config)
    assert result.settled == [("DOCN", state["trade_date"])]
    assert len(seen) == 1 and "B1_GRID_EXCLUSION_SENTINEL" not in seen[0]



def test_nonstock_scope_has_no_empty_stock_grid_pane(monkeypatch):
    import io

    from rich.console import Console

    from cli import display
    from tradingagents.reporting import _report_parts, prepare_report_state
    state = prepared_state(monkeypatch)
    state["asset_type"] = "crypto"
    prepared = prepare_report_state(state)
    assert prepared["mechanical_valuation_grid"]["status"] == "not_applicable"
    assert not any(name == "Mechanical sensitivity" for _, _, items in _report_parts(prepared)
                   for name, _, _ in items)
    stream = io.StringIO()
    monkeypatch.setattr(display, "console", Console(file=stream, width=160, color_system=None))
    display.display_complete_report(state)
    assert "Mechanical sensitivity" not in stream.getvalue()
