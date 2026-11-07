"""Assumption history uses actual verified publications, not a second ledger."""
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from tests.test_case_valuation import revenue_case
from tests.test_shared_valuation import state
from tradingagents.agents.decision_context import prepare_decision_context, render_condition_summary
from tradingagents.agents.shared_valuation import prepare_shared_valuation, replay_cases
from tradingagents.memory import publication


def inputs(multiple="3", horizon="6 months"):
    row = revenue_case()
    row["request"]["multiple"] = multiple
    value = state([row])
    value.update(run_id=str(uuid4()), final_rating="Hold", final_trade_decision="Rating: Hold",
                 analysis_clock={"cutoff_utc": "2026-10-19T20:00:00+00:00",
                                 "analysis_timezone": "America/Denver"},
                 unvalidated_outputs={"portfolio_manager": {"contract_version": "decision_horizon_v1",
                                                          "structured": {"time_horizon": horizon}}})
    value["shared_valuation_scenarios"] = prepare_shared_valuation(value)
    value["decision_context"] = prepare_decision_context(value)
    return value


def store(config, value, monkeypatch, hour=16):
    monkeypatch.setattr(publication, "_utcnow", lambda: datetime(2026, 10, 19, hour, tzinfo=UTC))
    return publication.publish(config, value, "DOCN", value["trade_date"])


def test_changes_use_verified_prior_and_only_report_changed_assumptions(tmp_path, monkeypatch):
    from tradingagents.agents.assumption_history import assumption_changes

    config = {"results_dir": str(tmp_path)}
    prior = store(config, inputs(), monkeypatch)
    current = inputs("4", "4 months")
    original = deepcopy(current)
    result = assumption_changes(config, "DOCN", current)
    assert result["status"] == "available" and result["prior_decision_id"] == prior["decision_id"]
    assert {(r["scenario"], r["field"]) for r in result["rows"]} == {("Base", "multiple"), ("Decision", "horizon")}
    assert result["new_filings_between"] is None  # absent inventory does not prove no new filing
    assert current == original


def test_no_prior_and_corrupt_history_do_not_resurrect_or_invent_comparisons(tmp_path, monkeypatch):
    from tradingagents.agents.assumption_history import assumption_changes

    config = {"results_dir": str(tmp_path)}
    assert assumption_changes(config, "DOCN", inputs())["status"] == "no_prior"
    rec = store(config, inputs(), monkeypatch)
    (publication.record_root(config) / "records" / f"{rec['decision_id']}.json").write_text("{")
    assert assumption_changes(config, "DOCN", inputs())["status"] == "unavailable"


def test_publication_time_and_identity_exclude_future_and_self(tmp_path, monkeypatch):
    from tradingagents.agents.assumption_history import assumption_changes

    config = {"results_dir": str(tmp_path)}
    first = store(config, inputs(), monkeypatch, 16)
    second = store(config, inputs("4"), monkeypatch, 18)
    current = inputs("5")
    own = store(config, current, monkeypatch, 19)
    current["publication_record"] = {k: own[k] for k in ("decision_id", "published_at", "record_sha256")}
    store(config, inputs("7"), monkeypatch, 21)
    result = assumption_changes(config, "DOCN", current)
    assert result["prior_decision_id"] == second["decision_id"] != first["decision_id"]
    assert len(result["rows"]) == 1 and result["rows"][0]["field"] == "multiple"


def test_effective_revision_is_compared_and_rejected_revision_is_not(tmp_path, monkeypatch):
    from tradingagents.agents.assumption_history import assumption_changes

    config = {"results_dir": str(tmp_path)}
    store(config, inputs(), monkeypatch)
    current = inputs()
    revised = revenue_case()
    revised["request"]["multiple"] = "4"
    current["shared_valuation_scenarios"] = replay_cases(current, revision=[revised])
    assert assumption_changes(config, "DOCN", current)["rows"][0]["field"] == "multiple"
    del revised["request"]["capital"]["cash"]
    current["shared_valuation_scenarios"] = replay_cases(current, revision=[revised])
    assert assumption_changes(config, "DOCN", current)["rows"] == []


def test_finalization_retains_comparison_and_export_does_not_read_later_history(tmp_path, monkeypatch):
    from tradingagents.agents.output_validation import enforce_publication
    from tradingagents.reporting import write_report_tree

    config = {"results_dir": str(tmp_path)}
    prior = store(config, inputs(), monkeypatch)
    current = inputs("4", "4 months")
    current.update(enforce_publication(current, publication_config=config))
    changes = deepcopy(current["decision_context"]["assumption_changes"])
    assert changes["prior_decision_id"] == prior["decision_id"]
    rec = store(config, current, monkeypatch, 19)
    current["publication_record"] = {k: rec[k] for k in ("decision_id", "published_at", "record_sha256")}
    store(config, inputs("7"), monkeypatch, 21)
    monkeypatch.setattr(publication, "list_records", lambda *a, **k: (_ for _ in ()).throw(AssertionError("export read history")))
    write_report_tree(current, "DOCN", tmp_path / "export", publication_config=config)
    assert prepare_decision_context(current)["assumption_changes"] == changes
    text = (tmp_path / "export" / "complete_report.md").read_text()
    html = (tmp_path / "export" / "complete_report.html").read_text()
    for payload in (text, html):
        assert "Changed since 2026-10-19" in payload and "4 months" in payload
    assert "No new filing was retained" not in render_condition_summary(current["decision_context"])


def test_real_graph_publication_persists_history_once_and_retry_keeps_it(tmp_path, monkeypatch):
    from tradingagents.graph.propagation import Propagator
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory.log import TradingMemoryLog

    config = {"results_dir": str(tmp_path), "memory_log_path": str(tmp_path / "memory.md")}
    prior = store(config, inputs(), monkeypatch)
    current = {**Propagator().create_initial_state("DOCN", "2026-10-19"),
               **inputs("4", "4 months")}
    app = object.__new__(TradingAgentsGraph)
    app.config = config
    app.run_settings = lambda: {"version": "test"}
    app.memory_log = TradingMemoryLog(config)
    app.record_decision("DOCN", current["trade_date"], current)
    actual = publication.load_record(config, current["run_id"])
    changes = publication.load_evidence(config, actual)["decision_context"]["assumption_changes"]
    assert changes["prior_decision_id"] == prior["decision_id"]
    assert len(changes["rows"]) == 2
    app.record_decision("DOCN", current["trade_date"], current)
    assert publication.load_record(config, current["run_id"]) == actual
    saved = app.save_reports(current, "DOCN", tmp_path / "reopened")
    assert "Changed since 2026-10-19" in saved.read_text()


def test_no_new_filing_requires_retained_inventories_on_both_sides(tmp_path, monkeypatch):
    from tradingagents.agents.assumption_history import assumption_changes

    config = {"results_dir": str(tmp_path)}
    first = inputs()
    first["filing_evidence"] = {"schema_version": 1, "cik": first["financial_evidence"]["cik"],
                                "as_of": first["trade_date"], "documents": [],
                                "gaps": [], "selected_accessions": []}
    store(config, first, monkeypatch)
    current = inputs("4")
    assert assumption_changes(config, "DOCN", current)["new_filings_between"] is None
    current["filing_evidence"] = deepcopy(first["filing_evidence"])
    changes = assumption_changes(config, "DOCN", current)
    assert changes["new_filings_between"] is False
    card = prepare_decision_context(current)
    card["assumption_changes"] = changes
    assert "No new filing was retained" in render_condition_summary(card)
