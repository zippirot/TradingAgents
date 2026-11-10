"""The analyst's bounded final response keeps source-backed blocks independently usable."""
import json
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage

from tests.test_case_valuation import revenue_case
from tests.test_disclosure_evidence import TEXT, claim
from tests.test_shared_valuation import state
from tradingagents.agents.analysts import fundamentals_analyst
from tradingagents.agents.shared_valuation import prepare_shared_valuation
from tradingagents.agents.valuation_reference_flow import parse_peer_proposal
from tradingagents.dataflows.disclosure_evidence import parse_disclosure_report


def test_fundamentals_receives_one_consistent_completion_order(monkeypatch):
    prompts = []

    def capture(prompt, llm, tools, messages):
        prompts.append(prompt.format_messages(messages=messages)[0].content)
        return AIMessage(content="Done"), "Done"

    monkeypatch.setattr(fundamentals_analyst, "take_turn", capture)
    fundamentals_analyst.create_fundamentals_analyst(object())({
        "trade_date": "2026-10-19", "company_of_interest": "DOCN", "instrument_context": "Offline",
        "messages": []})
    (system,) = prompts
    assert "valuation_scenarios, peers, financial_claims, disclosures" in system
    assert "Submit a base case and a downside case" in system and "scenario_role of base, downside or upside" in system
    assert "compact valid JSON" in system and "500 words" in system
    assert "Never shorten a qualified sentence" in system
    for conflict in ("as much detail as possible", "Always finish with", "End your final report with",
                     "Emit indented", "up to three justified conditional scenarios"):
        assert conflict not in system


def fence(label, value):
    marker = chr(96) * 3
    return f"{marker}{label}\n{json.dumps(value, separators=(',', ':'))}\n{marker}"


@pytest.mark.parametrize("count", [0, 1, 2])
def test_closed_compact_response_keeps_cases_and_sources_independent(count):
    base = revenue_case()
    upper = deepcopy(base)
    upper["name"] = "Higher"
    upper["request"]["multiple"] = "4"
    disclosure = claim().model_dump(mode="json")
    report = "\n".join((fence("valuation_scenarios", [base, upper][:count]), fence("peers", []),
                        fence("financial_claims", []), fence("disclosures", [disclosure]),
                        "Research narrative citing the retained financial and disclosure records."))
    inputs = state([])
    inputs["financial_claim_validation"]["raw_report"] = report
    record = prepare_shared_valuation(inputs)
    assert len(record["rows"]) == count
    assert record["status"] == ("available" if count else "unavailable")
    assert parse_peer_proposal(report, "DOCN")["status"] == "available"
    extracted = parse_disclosure_report(report, {("s", "p1"): TEXT})
    assert not extracted.rejected and extracted.claims[0].quote == disclosure["quote"]
    assert extracted.claims[0].definition == disclosure["definition"]


def test_truncated_third_case_never_authorizes_complete_prefix():
    base = revenue_case()
    second = deepcopy(base)
    second["name"] = "Higher"
    inputs = state([])
    inputs["financial_claim_validation"]["raw_report"] = (
        chr(96) * 3 + "valuation_scenarios\n" + json.dumps([base, second], separators=(",", ":"))[:-1] + ',{"name"')
    rejected = prepare_shared_valuation(inputs)
    assert rejected["status"] == "unavailable" and not rejected["rows"]
