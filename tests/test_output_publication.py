"""Publication uses canonical evidence, not unreconciled numeric model prose."""
from copy import deepcopy

import pytest

from tradingagents.agents.output_validation import enforce_publication


@pytest.mark.parametrize("claim", [
    "Fair value is $96. Allocate 5% of the portfolio.",
    "Our target is ninety-six dollars. Use five percent.",
    "Nuestro precio objetivo es noventa y seis dólares.",
])
@pytest.mark.parametrize("scope", ["US SEC filer", "technical-only"])
def test_unreconciled_prose_is_preserved_only_in_diagnostics(claim, scope):
    state = {
        "evidence_quality": {"status": "limited", "scope": scope, "checks": [], "warnings": []},
        "final_rating": "Overweight",
        "final_trade_decision": claim,
        "investment_plan": claim,
        "trader_investment_plan": claim,
        "investment_debate_state": {"bull_history": claim, "count": 1},
        "risk_debate_state": {"history": claim, "count": 1},
        "canonical_financial_context": "Revenue: USD 800, source fact revenue-1",
    }
    before = deepcopy(state)
    updates = enforce_publication(state)
    assert state == before
    public = {**state, **updates}
    assert public["final_rating"] == "Overweight"
    for field in ("final_trade_decision", "investment_plan", "trader_investment_plan"):
        assert claim not in public[field]
        assert public["unvalidated_outputs"][field] == claim
    assert claim not in str(public["investment_debate_state"])
    assert claim not in str(public["risk_debate_state"])
    assert public["unvalidated_outputs"]["risk_debate_state"]["history"] == claim
    assert "Fundamental price target: unavailable" in public["final_trade_decision"]
    assert "Revenue: USD 800" in public["final_trade_decision"]
    assert "Position sizing" in public["trader_investment_plan"]
    assert {**public, **enforce_publication(public)} == public


def test_legacy_state_is_not_rewritten_by_publication_guard():
    old = {"final_trade_decision": "Historical target $96", "final_rating": "Buy"}
    assert enforce_publication(old) == {}


def test_saved_and_direct_html_outputs_use_public_projection(tmp_path):
    import json

    from tradingagents.report_html import render_report
    from tradingagents.reporting import _report_parts, write_report_tree

    state = {
        "evidence_quality": {"status": "limited", "checks": [], "warnings": []},
        "final_rating": "Buy",
        "final_trade_decision": "Target $96; allocate 5%",
        "investment_plan": "Target ninety-six dollars",
        "trader_investment_plan": "Allocate 5%",
        "risk_debate_state": {"history": "Target $96"},
        "investment_debate_state": {"bull_history": "Target $96"},
    }
    write_report_tree(state, "DOCN", tmp_path)
    for name in ("complete_report.md", "complete_report.html"):
        text = (tmp_path / name).read_text()
        assert "$96" not in text
        assert "ninety-six" not in text
        assert "5%" not in text
        assert "Fundamental price target: unavailable" in text
    direct = render_report("DOCN", state, None, _report_parts(state))
    assert "$96" not in direct
    evidence = json.loads((tmp_path / "evidence.json").read_text())
    assert "$96" in evidence["raw_diagnostics"]["unvalidated_outputs"]["final_trade_decision"]


def test_analyst_prose_remains_explicitly_unvalidated_and_idempotent():
    state = {
        "evidence_quality": {"status": "limited"},
        "final_rating": "Hold",
        "market_report": "Technical resistance $96",
        "news_report": "Broker has a $96 price target",
        "fundamentals_report": "Our fair value is ninety-six dollars",
        "canonical_financial_context": "Revenue: 800 USD",
    }
    public = {**state, **enforce_publication(state)}
    assert public["fundamentals_report"] == "Revenue: 800 USD"
    for field in ("market_report", "news_report"):
        assert public[field].startswith("**Unvalidated model narrative")
        assert state[field] in public[field]
    assert {**public, **enforce_publication(public)} == public


def test_supported_target_is_replayed_not_trusted_from_saved_number():
    from tests.test_valuation import evidence
    state = {
        "evidence_quality": {"status": "limited"},
        "final_rating": "Buy",
        "financial_evidence": evidence().model_dump(mode="json"),
        "target_validation": {
            "status": "supported", "target": "999",
            "request": {"method": "pe", "eps_fact_id": "eps", "eps_basis": "diluted",
                        "accounting_basis": "US-GAAP", "multiple": 10,
                        "multiple_rationale": "Subjective illustrative assumption"},
        },
    }
    public = {**state, **enforce_publication(state)}
    assert public["target_validation"]["target"] == "20"
    assert "**Price Target**: 20.00 USD/shares" in public["final_trade_decision"]
    assert "999" not in public["final_trade_decision"]
    assert "**Source fact IDs**: eps" in public["final_trade_decision"]
    assert {**public, **enforce_publication(public)} == public


def test_supported_label_without_replayable_request_cannot_publish_a_target():
    state = {
        "evidence_quality": {"status": "limited"},
        "final_rating": "Buy",
        "target_validation": {"status": "supported", "target": "999"},
    }
    public = {**state, **enforce_publication(state)}
    assert public["target_validation"]["target"] is None
    assert public["target_validation"]["status"] == "unsupported"
    assert "999" not in public["final_trade_decision"]


def test_insufficient_evidence_clears_target_and_retains_debate_diagnostics():
    state = {
        "evidence_quality": {"status": "insufficient", "checks": [
            {"code": "equity", "status": "unavailable", "message": "Equity bridge missing"},
        ]},
        "final_rating": "Buy",
        "target_validation": {"status": "supported", "target": "96"},
        "risk_debate_state": {"history": "Target $96"},
        "investment_debate_state": {"bull_history": "Allocate 5%"},
    }
    public = {**state, **enforce_publication(state)}
    assert public["target_validation"]["target"] is None
    assert public["target_validation"]["status"] == "unsupported"
    assert public["unvalidated_outputs"]["target_validation"]["target"] == "96"
    assert public["unvalidated_outputs"]["risk_debate_state"]["history"] == "Target $96"
    assert public["final_rating"] == "REVIEW"


def test_target_replay_compares_forecast_with_source_grounded_management_outlook():
    from tests.test_valuation import ev_request, evidence
    from tests.test_valuation_outlooks import state as outlook_state

    state = outlook_state()
    package = evidence().model_dump(mode="json")
    package["sources"] += state["financial_evidence"]["sources"]
    state.update({
        "financial_evidence": package,
        "evidence_quality": {"status": "limited"},
        "final_rating": "Hold",
        "target_validation": {"request": ev_request()},
    })
    public = {**state, **enforce_publication(state)}
    assert public["target_validation"]["status"] == "supported"
    assert any("below management guidance" in warning
               for warning in public["target_validation"]["warnings"])
    assert "below management guidance" in public["final_trade_decision"]
