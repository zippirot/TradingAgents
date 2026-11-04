"""Readable research must not become authoritative decision or memory input."""
from copy import deepcopy

import pytest

from tradingagents.agents.output_validation import enforce_publication
from tradingagents.reporting import prepare_report_state, write_report_tree


def narrative_state(scope="US SEC filer"):
    return {
        "evidence_quality": {"status": "limited", "scope": scope, "checks": [], "warnings": []},
        "final_rating": "Hold",
        "canonical_financial_context": "Revenue: 800 USD (fact revenue-1)",
        "market_report": "Momentum is weakening.",
        "fundamentals_report": "Growth improved but financing remains a risk.",
        "investment_plan": "Weigh stronger demand against dilution.",
        "trader_investment_plan": "Model proposes allocating 5% at $96.",
        "final_trade_decision": "Model thesis: target ninety-six dollars despite financing uncertainty.",
        "investment_debate_state": {"bull_history": "Bull: demand strengthens.", "bear_history": "Bear: dilution matters.", "count": 2},
        "risk_debate_state": {"aggressive_history": "Aggressive: accept volatility.", "conservative_history": "Conservative: preserve capital.", "neutral_history": "Neutral: balance risks.", "count": 3},
    }


@pytest.mark.parametrize("scope", ["US SEC filer", "technical-only", "non-SEC"])
def test_research_retained_in_presentation_not_canonical_decision(scope):
    state = narrative_state(scope)
    if scope != "US SEC filer":
        state["evidence_quality"]["scope"] = "not_applicable"
        state.pop("canonical_financial_context")
    canonical = {**state, **enforce_publication(state)}
    before = deepcopy(canonical)
    shown = prepare_report_state(canonical)
    assert canonical == before
    for field in ("market_report", "fundamentals_report", "investment_plan",
                  "trader_investment_plan", "final_trade_decision"):
        assert state[field] in shown[field]
        assert "Unvalidated model research" in shown[field]
    for field in ("investment_debate_state", "risk_debate_state"):
        for key, value in state[field].items():
            if isinstance(value, str):
                assert value in shown[field][key]
                assert "Unvalidated model research" in shown[field][key]
            else:
                assert shown[field][key] == value
    assert "Fundamental price target: unavailable." in shown["final_trade_decision"]
    assert "\\n\\n" not in shown["final_trade_decision"]
    assert state["final_trade_decision"] not in canonical["final_trade_decision"]
    assert state["final_trade_decision"] == canonical["unvalidated_outputs"]["final_trade_decision"]
    assert prepare_report_state(shown) == shown


def test_saved_reports_retain_qualified_prose_and_evidence_is_canonical(tmp_path):
    import json
    state = narrative_state()
    before = deepcopy(state)
    write_report_tree(state, "DOCN", tmp_path)
    assert state == before
    for name in ("complete_report.md", "complete_report.html"):
        text = (tmp_path / name).read_text()
        assert "Weigh stronger demand against dilution." in text
        assert "Bull: demand strengthens." in text
        assert "Unvalidated model research" in text
        assert "Fundamental price target: unavailable." in text
    evidence = json.loads((tmp_path / "evidence.json").read_text())
    assert evidence["target_validation"]["target"] is None
    assert evidence["raw_diagnostics"]["unvalidated_outputs"]["final_trade_decision"] == state["final_trade_decision"]


def test_review_still_withholds_actionable_research():
    state = narrative_state()
    state["evidence_quality"]["status"] = "insufficient"
    shown = prepare_report_state(state)
    assert shown["final_rating"] == "REVIEW"
    assert state["trader_investment_plan"] not in str(shown.get("trader_investment_plan"))
    assert state["final_trade_decision"] not in shown["final_trade_decision"]
    assert "research incomplete" in shown["final_trade_decision"].lower()


def test_displayed_research_cannot_enter_memory_even_if_presentation_is_passed_back(tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory.log import TradingMemoryLog

    state = narrative_state()
    shown = prepare_report_state(state)
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.memory_log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
    logged = []
    graph._log_state = lambda date, value: logged.append(deepcopy(value))
    graph.record_decision("DOCN", "2026-11-04", shown)
    entries = graph.memory_log.load_entries()
    assert len(entries) == 1
    text = (tmp_path / "memory.md").read_text()
    assert state["final_trade_decision"] not in text
    assert "Unvalidated model research" not in text
    assert "Fundamental price target: unavailable" in text
    assert state["final_trade_decision"] not in logged[0]["final_trade_decision"]


def test_cli_complete_display_contains_labeled_research(capsys):
    from cli.display import display_complete_report
    display_complete_report(narrative_state())
    text = capsys.readouterr().out
    assert "Weigh stronger demand against dilution." in text
    assert "Unvalidated model research" in text
    assert "Fundamental price target: unavailable" in text


def test_supported_target_remains_authoritative_next_to_conflicting_research():
    from tests.test_valuation import evidence
    state = narrative_state()
    state["financial_evidence"] = evidence().model_dump(mode="json")
    state["target_validation"] = {
        "request": {"method": "pe", "eps_fact_id": "eps", "eps_basis": "diluted",
                    "accounting_basis": "US-GAAP", "multiple": 10,
                    "multiple_rationale": "Subjective illustrative assumption"},
    }
    shown = prepare_report_state(state)
    assert shown["target_validation"]["target"] == "20"
    assert "**Price Target**: 20.00 USD/shares" in shown["final_trade_decision"]
    assert state["final_trade_decision"] in shown["final_trade_decision"]
    assert shown["final_trade_decision"].index("20.00 USD/shares") < shown["final_trade_decision"].index("Unvalidated model research")


def test_fundamentals_original_reasoning_survives_gate_rewrite():
    state = narrative_state()
    original = "Original fundamentals reasoning: expansion may offset financing risk."
    state["financial_claim_validation"] = {"raw_report": original, "status": "pass"}
    shown = prepare_report_state(state)
    assert original in shown["fundamentals_report"]
    assert state["canonical_financial_context"] in shown["fundamentals_report"]
    assert prepare_report_state(shown) == shown
