"""Decision-quality Part A: corrections that change what the decision agents and the reader see."""

import json
from decimal import Decimal

from tests.test_case_funding import _capital, _check
from tests.test_case_valuation import revenue_case
from tests.test_shared_valuation import state
from tradingagents.agents.audit_pass import _case_context, build_advisory_audit_prompt
from tradingagents.agents.case_reference import action_reading, guidance_floor
from tradingagents.agents.decision_context import render_decision_context
from tradingagents.agents.shared_valuation import prepare_shared_valuation, render_shared_valuation
from tradingagents.agents.trader.trader import _reading
from tradingagents.agents.valuation_cases import MULTIPLE_CONSTRUCTION

PLAN = "**Recommendation**: Underweight\n\n**Rationale**: Reduce on strength."


# A1 --------------------------------------------------------------------------

def _replayed(**extra):
    return {"rows": [{"case_id": "case-0", "name": "Base", "request": {"note": "x"}, **extra}]}


def test_the_auditor_is_given_what_code_computed_about_each_case(monkeypatch):
    rows = _replayed(reference_position={"status": "available", "summary": "Low of the same-basis history is 4.84x."},
                     funding={"summary": "Funding assessed: scheduled 320.5M.", "limit": "No discounting."},
                     guidance_floor={"summary": "Revenue forecast 1.930B is 0.15% below the floor."})
    monkeypatch.setattr("tradingagents.agents.shared_valuation.replay_cases", lambda state: rows)
    case = json.loads(_case_context({})["shared_valuation_cases"])[0]
    assert case["computed_by_code"] == {
        "multiple_reference": "Low of the same-basis history is 4.84x.",
        "funding": "Funding assessed: scheduled 320.5M. No discounting.",
        "guidance_floor": "Revenue forecast 1.930B is 0.15% below the floor."}


def test_an_unavailable_reference_and_an_oversized_case_are_handled(monkeypatch):
    rows = {"rows": [
        {"case_id": "a", "name": "A", "request": {"note": "x"},
         "reference_position": {"status": "unavailable", "summary": "No history retained."}},
        {"case_id": "b", "name": "B", "request": {"note": "x" * 9000},
         "funding": {"summary": "S" * 5000}}]}
    monkeypatch.setattr("tradingagents.agents.shared_valuation.replay_cases", lambda state: rows)
    first, second = json.loads(_case_context({})["shared_valuation_cases"])
    assert "computed_by_code" not in first
    # The request is dropped at its cap; the computed lines stay, each bounded.
    assert second["request"].startswith("omitted at") and len(second["computed_by_code"]["funding"]) == 1500


def test_the_auditor_is_told_the_computed_block_is_support(monkeypatch):
    monkeypatch.setattr("tradingagents.agents.shared_valuation.replay_cases", lambda state: _replayed())
    prompt = build_advisory_audit_prompt({})
    text = prompt if isinstance(prompt, str) else json.dumps(prompt, default=str)
    assert "computed_by_code block was calculated by code from retained filings" in text


# A2 --------------------------------------------------------------------------

def test_one_description_of_the_multiple_whichever_period_word_was_given():
    trailing = revenue_case()
    trailing["name"], trailing["request"]["multiple_period"] = "Year-end", "trailing"
    record = prepare_shared_valuation(state([revenue_case(), trailing]))
    text = render_shared_valuation(record)
    assert text.count(f"/ revenue ({MULTIPLE_CONSTRUCTION})") == 2
    for row in record["rows"]:
        assert any(line.endswith(MULTIPLE_CONSTRUCTION + ".") for line in row["result"]["assumptions"])
    assert "forward revenue" not in text and "trailing revenue" not in text


# A3 --------------------------------------------------------------------------

def test_a_typing_difference_on_the_payment_schedule_is_not_a_funding_gap():
    # Schedule 320.4M through the period end; the case states 25,000 less (0.008%).
    close = _check(_capital([("finance_payments", -320375000), ("debt", -312322000)]))
    assert close["status"] == "assessed" and close["reasons"] == []
    assert (close["scheduled_finance_payments"], close["stated_finance_payments"]) == ("320400000", "320375000")
    # 0.125% short is a real difference and still says so.
    short = _check(_capital([("finance_payments", -320000000), ("debt", -312322000)]))
    assert short["status"] == "partial" and "the case states 320.0M USD" in short["reasons"][0]
    # Exactly at the tolerance passes; one dollar beyond does not.
    edge = Decimal("320400000") * (1 - Decimal("0.001"))
    assert _check(_capital([("finance_payments", -edge), ("debt", -312322000)]))["status"] == "assessed"
    assert _check(_capital([("finance_payments", -(edge - 1)), ("debt", -312322000)]))["status"] == "partial"


# A4 --------------------------------------------------------------------------

def test_a_sell_under_an_underweight_rating_reads_as_reduce():
    assert action_reading("Sell", "Underweight") == "Reduce (the Trader's Sell under the research rating Underweight)"
    assert action_reading("Buy", "Overweight") == "Add (the Trader's Buy under the research rating Overweight)"
    for action, rating in (("Sell", "Sell"), ("Buy", "Buy"), ("Hold", "Underweight"), ("Sell", None), ("unavailable", "Underweight")):
        assert action_reading(action, rating) is None


def test_the_trader_text_carries_the_reading_and_keeps_its_action():
    text = "**Action**: Sell\n\n**Reasoning**: Valuation."
    line = _reading(text, PLAN)
    assert "Reading of this action: Reduce (the Trader's Sell under the research rating Underweight)." in line
    assert "not an exit" in line
    assert _reading(text, "**Rating**: Sell") == "" and _reading("No action line.", PLAN) == ""
    assert _reading("**Action**: Hold", PLAN) == ""
    # The older "Rating" label still reads; two different recommendations are no reading.
    assert "Reduce" in _reading(text, "**Rating**: Underweight")
    assert _reading(text, PLAN + "\n**Recommendation**: Sell") == ""


def test_the_decision_card_prints_the_reading_and_keeps_the_stored_action():
    from tests.test_decision_context import state as card_state
    from tradingagents.agents.decision_context import prepare_decision_context

    value = card_state()
    value["unvalidated_outputs"]["investment_plan"] = PLAN
    record = prepare_decision_context(value)
    assert record["trader_provisional"] == "Sell"
    assert record["trader_reading"] == "Reduce (the Trader's Sell under the research rating Underweight)"
    # Brackets are escaped for markdown and print as plain brackets.
    assert "**Trader provisional action**: Reduce \\(the Trader's Sell under" in render_decision_context(record)
    value["unvalidated_outputs"]["investment_plan"] = "**Recommendation**: Sell"
    plain = prepare_decision_context(value)
    assert plain["trader_reading"] is None
    assert "**Trader provisional action**: Sell;" in render_decision_context(plain)
    # A card saved before this build has no reading and still prints.
    del plain["trader_reading"]
    assert "**Trader provisional action**: Sell;" in render_decision_context(plain)


# A6 --------------------------------------------------------------------------

def _implied(**changes):
    return {"price_implied_valuation": {
        "status": "available", "analysis_year": 2026, "growth_floor_percent": "30", "growth_floor_period": "2027",
        "management_revenue_guidance_period": "FY2026",
        "management_revenue_guidance_range_usd": ["1486800000", "1488800000"], **changes}}


def _row(value, start="2027-01-01", end="2027-12-31", unit="USD"):
    return {"request": {"forecast": {"value": value, "period_start": start, "period_end": end, "unit": unit}}}


def test_a_forecast_is_placed_against_the_guidance_floor_arithmetic():
    # 1,486.8M x 1.30 = 1,932.84M.
    below = guidance_floor(_row("1930000000"), _implied())
    assert below["floor"] == "1932840000.0" or Decimal(below["floor"]) == Decimal("1932840000")
    assert below["position"] == "below" and Decimal(below["gap_percent"]).quantize(Decimal("0.01")) == Decimal("-0.15")
    assert below["summary"].startswith("Revenue forecast 1.930B is 0.15% below the 1.9328B that follows from the low end "
                                       "of FY2026 guidance and management's 30% growth floor for 2027.")
    assert guidance_floor(_row("1932840000"), _implied())["position"] == "at"
    above = guidance_floor(_row("2000000000"), _implied())
    assert above["position"] == "above" and "3.47% above" in above["summary"]


def test_the_floor_note_is_withheld_when_its_inputs_do_not_line_up():
    row = _row("1930000000")
    assert guidance_floor(row, {}) is None
    assert guidance_floor(row, _implied(status="unavailable")) is None
    assert guidance_floor(row, _implied(growth_floor_percent=None)) is None
    assert guidance_floor(row, _implied(management_revenue_guidance_range_usd=None)) is None
    assert guidance_floor(row, _implied(growth_floor_period="2028")) is None
    assert guidance_floor(row, _implied(management_revenue_guidance_period="FY2025")) is None
    assert guidance_floor(_row("1930000000", end="2027-06-30"), _implied()) is None
    assert guidance_floor(_row("1930000", unit="USD thousands"), _implied()) is None
    assert guidance_floor(_row("not a number"), _implied()) is None
    assert guidance_floor({"request": {}}, _implied()) is None


def test_the_floor_note_reaches_the_case_card_and_the_manager():
    from tradingagents.agents.scenario_decision import priced_cases, render_cases_for_manager

    inputs = {**state([revenue_case()]), **_implied(management_revenue_guidance_range_usd=["1000", "1100"])}
    record = prepare_shared_valuation(inputs)
    row = record["rows"][0]
    note = row.get("guidance_floor")
    forecast = row["request"]["forecast"]
    if (forecast["period_start"], forecast["period_end"], forecast["unit"]) != ("2027-01-01", "2027-12-31", "USD"):
        assert note is None
        return
    assert note["summary"] in render_shared_valuation(record)
    assert note["summary"] in render_cases_for_manager(priced_cases(record))
