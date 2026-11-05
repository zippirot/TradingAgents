"""The debate receives accepted evidence once, without replaying the fundamentals report."""

from importlib import import_module
from types import SimpleNamespace

import pytest

ROLES = (
    ("researchers.bull_researcher", "create_bull_researcher"),
    ("researchers.bear_researcher", "create_bear_researcher"),
    ("risk_mgmt.aggressive_debator", "create_aggressive_debator"),
    ("risk_mgmt.conservative_debator", "create_conservative_debator"),
    ("risk_mgmt.neutral_debator", "create_neutral_debator"),
)


def _state(*, with_evidence: bool, report: str) -> dict:
    debate = {"history": "", "current_response": "", "count": 0}
    risk_debate = {
        "history": "", "count": 0,
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
    }
    state = {
        "company_of_interest": "DOCN",
        "instrument_context": "Instrument: DOCN",
        "market_report": "TECHNICAL_SENTINEL",
        "sentiment_report": "SENTIMENT_SENTINEL",
        "news_report": "NEWS_SENTINEL",
        "fundamentals_report": report,
        "investment_debate_state": debate,
        "risk_debate_state": risk_debate,
        "trader_investment_plan": "Propose holding.",
    }
    if with_evidence:
        state.update({
            "canonical_financial_context": "ACCEPTED_EVIDENCE_SENTINEL",
            "financial_claim_validation": {
                "raw_report": (
                    "RESEARCH_INTERPRETATION_SENTINEL\n"
                    "```financial_claims\nUNVALIDATED_CLAIM_SENTINEL\n```"
                ),
            },
            "shared_valuation_scenarios": {
                "status": "unavailable",
                "reasons": ["SCENARIO_STATUS_SENTINEL"],
            },
        })
    return state


def _prompt(module_name: str, factory_name: str, state: dict) -> str:
    captured = []
    llm = SimpleNamespace(
        invoke=lambda prompt: captured.append(prompt) or SimpleNamespace(content="argument")
    )
    module = import_module(f"tradingagents.agents.{module_name}")
    getattr(module, factory_name)(llm)(state)
    assert len(captured) == 1
    return captured[0]


@pytest.mark.parametrize("module_name,factory_name", ROLES)
def test_accepted_evidence_is_not_replayed_as_fundamentals(module_name, factory_name):
    prompt = _prompt(
        module_name, factory_name,
        _state(
            with_evidence=True,
            report="ACCEPTED_EVIDENCE_SENTINEL and superseded report prose",
        ),
    )
    assert prompt.count("ACCEPTED_EVIDENCE_SENTINEL") == 1
    assert "superseded report prose" not in prompt
    assert prompt.count("RESEARCH_INTERPRETATION_SENTINEL") == 1
    assert "UNVALIDATED_CLAIM_SENTINEL" not in prompt
    assert "See the accepted evidence brief and labeled research context above." in prompt
    assert "SCENARIO_STATUS_SENTINEL" in prompt
    for marker in ("TECHNICAL_SENTINEL", "SENTIMENT_SENTINEL", "NEWS_SENTINEL"):
        assert marker in prompt


@pytest.mark.parametrize("module_name,factory_name", ROLES)
def test_fundamentals_fallback_without_evidence(module_name, factory_name):
    raw_prompt = _prompt(
        module_name, factory_name,
        _state(with_evidence=False, report="RAW_FUNDAMENTALS_SENTINEL"),
    )
    assert raw_prompt.count("RAW_FUNDAMENTALS_SENTINEL") == 1
    assert "See the accepted evidence brief" not in raw_prompt

    absent_prompt = _prompt(
        module_name, factory_name,
        _state(with_evidence=False, report=""),
    )
    assert "No fundamentals report in this run" in absent_prompt
    assert "See the accepted evidence brief" not in absent_prompt
