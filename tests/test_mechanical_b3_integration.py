"""B3 shares fresh bounded calculations without changing decision or memory authority."""
from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace

import pytest

from tests.test_mechanical_valuation import prepared


def state_fixture(monkeypatch):
    state, _ = prepared(monkeypatch)
    state.update({
        "evidence_quality": {"status": "limited"}, "final_rating": "Hold",
        "instrument_context": "Instrument DOCN", "canonical_financial_context": "CANONICAL_SOURCE_CONTROL",
        "market_report": "Market", "news_report": "News", "sentiment_report": "Social",
        "fundamentals_report": "Research", "trader_investment_plan": "Hold", "investment_plan": "Research plan",
        "investment_debate_state": {"history": "", "bull_history": "", "bear_history": "",
                                   "current_response": "", "count": 0},
        "risk_debate_state": {"history": "", "aggressive_history": "", "conservative_history": "",
                             "neutral_history": "", "latest_speaker": "",
                             "current_aggressive_response": "", "current_conservative_response": "",
                             "current_neutral_response": "", "count": 0},
    })
    return state


@pytest.mark.parametrize("module_name,factory_name", [
    ("researchers.bull_researcher", "create_bull_researcher"),
    ("researchers.bear_researcher", "create_bear_researcher"),
    ("managers.research_manager", "create_research_manager"),
    ("managers.portfolio_manager", "create_portfolio_manager"),
])
def test_actual_four_role_factories_receive_identical_fresh_compact_context(monkeypatch, module_name, factory_name):
    from tradingagents.agents.mechanical_context import mechanical_role_context
    state = state_fixture(monkeypatch)
    state["mechanical_valuation_grid"] = {"status": "available", "conditional_price": "999999999"}
    before = deepcopy(state)
    expected = mechanical_role_context(state)
    assert "History-median" in expected and "Guided diluted" in expected
    assert len(expected) <= 12000
    prompts = []
    llm = SimpleNamespace(invoke=lambda prompt, **kwargs: prompts.append(str(prompt)) or
                          SimpleNamespace(content="Hold"))
    mod = import_module("tradingagents.agents." + module_name)
    if hasattr(mod, "bind_structured"):
        monkeypatch.setattr(mod, "bind_structured", lambda *a, **kw: None)
    getattr(mod, factory_name)(llm)(state)
    assert len(prompts) == 1
    assert expected in prompts[0]
    assert "999999999" not in prompts[0]
    assert "dispute" in prompts[0].lower()
    assert state == before


def test_default_analyst_context_unchanged_and_review_nonstock_withhold(monkeypatch):
    from tradingagents.agents.context import get_instrument_context_from_state
    from tradingagents.agents.mechanical_context import mechanical_role_context
    state = state_fixture(monkeypatch)
    assert "Shared mechanical valuation" not in get_instrument_context_from_state(state)
    assert "Shared mechanical valuation" in get_instrument_context_from_state(state, include_mechanical=True)
    legacy = {key: value for key, value in state.items() if key != "valuation_reference"}
    assert mechanical_role_context(legacy) == ""
    state["evidence_quality"] = {"status": "insufficient"}
    assert "guidance low" not in mechanical_role_context(state)
    state["asset_type"] = "crypto"
    assert mechanical_role_context(state) == ""


def test_public_card_has_position_but_canonical_decision_and_memory_do_not(monkeypatch, tmp_path):
    from tradingagents.agents import valuation_reference_flow
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )
    from tradingagents.agents.output_validation import enforce_publication
    from tradingagents.reporting import prepare_report_state
    # This fixture isolates the new context/card boundary; its arithmetic
    # reference stub intentionally omits the unrelated full Part A renderer.
    monkeypatch.setattr(valuation_reference_flow, "render_valuation_reference", lambda record: "Test reference view")
    state = state_fixture(monkeypatch)
    before = deepcopy(state)
    card = prepare_decision_context(state)
    assert card["mechanical_position"]["status"] == "available"
    assert card["basis"] == "risk assessment"
    assert "History-median" in render_decision_context(card)
    canonical = {**state, **enforce_publication(state)}
    assert "History-median sensitivity position" not in canonical["final_trade_decision"]
    from tradingagents.agents.decision_context import render_condition_summary
    assert "History-median" in render_condition_summary(prepare_report_state(canonical)["decision_context"])
    assert state == before
    # Saved advisory numbers are recomputed, not trusted on current projection.
    canonical["decision_context"]["mechanical_position"]["rows"][0]["price_interval"] = ["999999999", "999999999"]
    projected = enforce_publication(canonical)
    assert "999999999" not in str(projected["decision_context"]["mechanical_position"])


def test_review_card_has_no_directional_mechanical_position(monkeypatch):
    from tradingagents.agents.decision_context import prepare_decision_context
    state = state_fixture(monkeypatch)
    state["evidence_quality"] = {"status": "insufficient", "checks": []}
    state["final_rating"] = "REVIEW"
    card = prepare_decision_context(state)
    assert card["mechanical_position"]["status"] == "unavailable"
    assert not card["mechanical_position"]["rows"]


def test_audit_sees_shared_calculation_without_manufactured_evidence_labels(monkeypatch):
    import json

    from tradingagents.agents.audit_pass import (
        _contexts,
        _known_labels,
        build_advisory_audit_prompt,
    )
    from tradingagents.agents.mechanical_context import mechanical_role_context
    state = state_fixture(monkeypatch)
    source, _ = _contexts(state)
    assert source["shared_mechanical_sensitivities"] == mechanical_role_context(state)
    assert "History-median" in build_advisory_audit_prompt(state)
    assert "references" not in _known_labels({key: value for key, value in source.items()
                                            if key != "shared_mechanical_sensitivities"})
    assert "conditional" in source["shared_mechanical_sensitivities"]
    assert json.loads(json.dumps(source)) == source


def test_actual_memory_record_retains_advisory_card_only_in_evidence(monkeypatch, tmp_path):
    from tradingagents.agents import valuation_reference_flow
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory.log import TradingMemoryLog
    from tradingagents.memory.publication import list_records, load_evidence
    monkeypatch.setattr(valuation_reference_flow, "render_valuation_reference", lambda record: "Test reference view")
    state = state_fixture(monkeypatch)
    app = object.__new__(TradingAgentsGraph)
    app.config = {"results_dir": str(tmp_path), "memory_log_path": str(tmp_path / "memory.md")}
    app.run_settings = lambda: {"version": "test"}
    app.outcome_summary = lambda *a, **k: "No measured outcome"
    app._log_state = lambda *a: None
    app.memory_log = TradingMemoryLog(app.config)
    app.record_decision("DOCN", state["trade_date"], state)
    record = list_records(app.config)[0]
    saved = load_evidence(app.config, record)
    assert saved["decision_context"]["mechanical_position"]["status"] == "available"
    decision = app.memory_log.load_entries()[0]["decision"]
    assert "History-median sensitivity position" not in decision
    assert "Completed-price position" not in decision
    assert "Shared mechanical valuation context" not in decision
