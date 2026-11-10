"""The Portfolio Manager decides from priced cases (Build Q, Q3)."""

from decimal import Decimal

import pytest

from tradingagents.agents.scenario_decision import (
    LABEL,
    priced_cases,
    render,
    render_cases_for_manager,
    retry_feedback,
    summarize,
    view_problems,
)


def _row(case_id, price, role="base", **extra):
    return {"case_id": case_id, "version": 1, "name": f"Case {case_id}", "scenario_role": role,
            "result": {"method": "revenue_case", "status": "supported", "target": price, "unit": "USD/shares",
                       "valuation_period_end": "2027-12-31"},
            "funding": {"status": "partial", "summary": "Funding partial: x."},
            "reference_position": {"status": "available", "band": "low_to_median", "summary": "Implied 3.65×."}, **extra}


REPLAYED = {"rows": [_row("a", "74.45"), _row("b", "52.75", role="downside")]}


def _state(view, rating="Underweight", close="78.31", reason=None):
    return {"final_rating": rating,
            "price_observation": {"status": "available", "close": close, "session_date": "2026-11-09"},
            "unvalidated_outputs": {"portfolio_manager": {"scenario_contract": 1, "structured": {
                "scenario_view": view, "rating_basis_reason": reason}}}}


def _accept(case_id, weight, **extra):
    return {"case_id": case_id, "version": 1, "disposition": "accepted", "weight": weight, "reason": "r", **extra}


def _reject(case_id, rejected_input="multiple"):
    return {"case_id": case_id, "version": 1, "disposition": "rejected", "rejected_input": rejected_input, "reason": "r"}


def test_only_supported_undisputed_revenue_cases_with_a_price_can_be_weighed():
    rows = [_row("a", "74.45"), _row("b", None), _row("c", "10", disputed_by=["AF-1"]),
            {**_row("d", "10"), "result": {**_row("d", "10")["result"], "method": "pe"}},
            {**_row("e", "10"), "result": {**_row("e", "10")["result"], "status": "unsupported"}}]
    assert [case["case_id"] for case in priced_cases({"rows": rows})] == ["a"]
    assert priced_cases(None) == [] and priced_cases({"rows": "x"}) == []


def test_accepted_cases_give_range_weighted_value_and_direction_from_replayed_prices():
    summary = summarize(_state([_accept("a", 0.6), _accept("b", 0.4)]), REPLAYED)
    assert summary["status"] == "addressed" and summary["problems"] == []
    assert summary["range"] == {"low": "52.75", "high": "74.45"}
    assert Decimal(summary["weighted_value"]) == Decimal("65.77")
    assert summary["direction"] == "below" and summary["consistency"] == "consistent"
    assert abs(Decimal(summary["weighted_vs_close_percent"]) - Decimal("-16.01")) < Decimal("0.01")
    # A price stored in the manager's answer is never used.
    tampered = summarize(_state([_accept("a", 0.6, price="999"), _accept("b", 0.4)]), REPLAYED)
    assert tampered["weighted_value"] == summary["weighted_value"]


@pytest.mark.parametrize("view,text", [
    (None, "scenario_view is missing"),
    ([], "scenario_view is missing"),
    ([_accept("a", 1)], "Case b (Case b) is not addressed."),
    ([_accept("a", 0.5), _accept("b", 0.4)], "Accepted weights sum to 0.9; they must sum to 1."),
    ([_accept("a", 0), _reject("b")], "accepted without a weight"),
    ([_accept("a", True), _reject("b")], "accepted without a weight"),
    ([_accept("a", 1), _reject("b", "uncalibrated")], "rejected without naming the input rejected"),
    ([_accept("a", 1), {**_reject("b"), "reason": " "}], "has no reason"),
    ([_accept("a", 1), {**_reject("b"), "disposition": "maybe"}], "needs disposition accepted or rejected"),
    ([_accept("a", 1), _reject("b"), _reject("z")], "Case z version 1 is not a priced case"),
    ([_accept("a", 0.5), _accept("a", 0.5), _reject("b")], "listed more than once"),
    (["x", _accept("a", 1), _reject("b")], "entries must be objects"),
])
def test_an_unusable_scenario_view_is_named(view, text):
    assert any(text in problem for problem in view_problems(priced_cases(REPLAYED), view))
    summary = summarize(_state(view), REPLAYED)
    assert summary["status"] == "unaddressed" and "range" not in summary
    assert "opinion only" in render(summary)[0]
    assert "Resubmit the complete decision" in retry_feedback(_state(view), REPLAYED)


@pytest.mark.parametrize("rating,close,reason,direction,consistency", [
    ("Underweight", "78.31", None, "below", "consistent"),
    ("Underweight", "50", None, "above", "unexplained"),
    ("Sell", "50", "Funding risk dominates.", "above", "explained"),
    ("Buy", "78.31", None, "below", "unexplained"),
    ("Overweight", "78.31", "Bounce expected.", "below", "explained"),
    ("Hold", "50", None, "above", "consistent"),
    ("Underweight", "70", None, "near", "consistent"),
    ("Buy", "70", None, "near", "consistent"),
])
def test_rating_is_checked_against_the_weighted_value(rating, close, reason, direction, consistency):
    state = _state([_accept("a", 0.6), _accept("b", 0.4)], rating=rating, close=close, reason=reason)
    summary = summarize(state, REPLAYED)
    assert (summary["direction"], summary["consistency"]) == (direction, consistency)
    feedback = retry_feedback(state, REPLAYED)
    assert ("rating_basis_reason" in feedback) is (consistency == "unexplained")
    text = "\n".join(render(summary))
    assert {"consistent": "does not point against", "explained": "reason (unvalidated): " + (reason or ""),
            "unexplained": "no reason was given"}[consistency] in text


def test_threshold_is_ten_percent_inclusive():
    for close, direction in (("59.79", "above"), ("59.80", "near"), ("73.07", "near"), ("73.08", "below")):
        summary = summarize(_state([_accept("a", 0.6), _accept("b", 0.4)], close=close), REPLAYED)
        assert summary["direction"] == direction, close


def test_all_rejected_gives_no_range_and_no_retry():
    state = _state([_reject("a", "funding"), _reject("b", "revenue_forecast")])
    summary = summarize(state, REPLAYED)
    assert summary["status"] == "addressed" and summary["range"] is None and summary["consistency"] == "not_checked"
    assert retry_feedback(state, REPLAYED) == ""
    text = "\n".join(render(summary))
    assert "rejected on funding" in text and "All priced cases were rejected" in text


def test_no_priced_cases_is_stated_and_needs_nothing_from_the_manager():
    summary = summarize(_state(None), {"rows": []})
    assert summary == {"status": "no_priced_cases", "cases": [], "problems": []}
    assert render(summary) == [f"**{LABEL}**: no priced scenario; the rating is a research opinion."]
    assert retry_feedback(_state(None), {"rows": []}) == ""
    assert "omit scenario_view" in render_cases_for_manager([])


def test_a_decision_made_before_this_contract_is_not_judged():
    state = _state(None)
    del state["unvalidated_outputs"]["portfolio_manager"]["scenario_contract"]
    summary = summarize(state, REPLAYED)
    assert summary["status"] == "not_applicable" and render(summary) == []
    assert retry_feedback(state, REPLAYED) == ""


def test_missing_close_states_the_range_without_a_direction():
    state = _state([_accept("a", 1), _reject("b")])
    state["price_observation"] = {"status": "unavailable"}
    summary = summarize(state, REPLAYED)
    assert summary["weighted_value"] == "74.45" and summary["direction"] is None
    assert "No completed close is available" in "\n".join(render(summary))


def test_card_lines_carry_every_label():
    summary = summarize(_state([_accept("a", 0.6), _accept("b", 0.4)]), REPLAYED)
    text = "\n".join(render(summary))
    for label in ("not a price target", "subjective and uncalibrated", "not discounted", "funding partial",
                  "accepted, weight 0.60", "base — Case a: 74.45 USD/shares", "downside — Case b",
                  "weighted value 65.77 USD/shares, -16.0% against the 2026-11-09 close of 78.31",
                  "Direction: below the close, using a 10 percent threshold"):
        assert label in text, label
    assert render(None) == [] and render({"status": "not_applicable"}) == []


def test_manager_sees_each_case_with_its_funding_and_reference():
    text = render_cases_for_manager(priced_cases(REPLAYED))
    assert "case_id a, version 1, role base" in text and "74.45 USD/shares at 2027-12-31" in text
    assert "Funding partial: x." in text and "Implied 3.65×." in text
    assert "revenue_forecast, multiple, shares, cash, obligations, funding" in text
    assert "never a price target" in text
    # Without this standard the live manager rejected every case on limits common to all of them.
    assert "Reject a case only when you can state the value the rejected input should take" in text
    assert "expressed through lower weights and the downside case, not by rejecting" in text


# Wiring: the manager's call, the decision card and the operational score -------

def _case_state():
    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state as case_state
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    inputs = case_state([revenue_case()])
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    row = inputs["shared_valuation_scenarios"]["rows"][0]
    inputs.update({
        "investment_plan": "Plan", "trader_investment_plan": "Proposal", "final_rating": "Underweight",
        "risk_debate_state": {"history": "Debate", "aggressive_history": "", "conservative_history": "",
                              "neutral_history": "", "current_aggressive_response": "",
                              "current_conservative_response": "", "current_neutral_response": "", "count": 1},
        "price_observation": {"status": "available", "close": "40", "session_date": "2026-10-16"}})
    return inputs, row


def _decision(**fields):
    from tradingagents.agents.schemas import RequiredHorizonPortfolioDecision

    return RequiredHorizonPortfolioDecision(**{
        "rating": "Underweight", "executive_summary": "Summary.", "investment_thesis": "Thesis.",
        "time_horizon": "6 months", **fields})


def _manager(*answers):
    from unittest.mock import MagicMock

    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

    llm = MagicMock()
    structured = llm.with_structured_output.return_value
    structured.invoke.side_effect = list(answers)
    return create_portfolio_manager(llm), structured


def test_manager_is_shown_the_priced_case_and_a_valid_answer_needs_one_call():
    inputs, row = _case_state()
    view = [{"case_id": row["case_id"], "version": 1, "disposition": "accepted", "weight": 1, "rejected_input": None,
             "reason": "Reasonable base."}]
    node, structured = _manager(_decision(scenario_view=view))
    result = node(inputs)
    assert structured.invoke.call_count == 1
    prompt = structured.invoke.call_args.args[0]
    assert f"case_id {row['case_id']}, version 1" in prompt and "Scenario basis (not a price target)" in prompt
    saved = result["unvalidated_outputs"]["portfolio_manager"]["structured"]["scenario_view"]
    assert saved == view


def test_an_unaddressed_case_gets_one_correction_and_the_second_answer_is_used():
    inputs, row = _case_state()
    view = [{"case_id": row["case_id"], "version": 1, "disposition": "rejected", "weight": None,
             "rejected_input": "multiple", "reason": "Above the history high."}]
    node, structured = _manager(_decision(), _decision(rating="Hold", scenario_view=view))
    result = node(inputs)
    assert structured.invoke.call_count == 2
    assert "Your scenario_view could not be used" in structured.invoke.call_args.args[0]
    assert result["final_rating"] == "Hold"
    assert result["unvalidated_outputs"]["portfolio_manager"]["structured"]["scenario_view"] == view


def test_a_failed_correction_keeps_the_first_answer_and_no_third_call_is_made():
    inputs, _row_ = _case_state()
    node, structured = _manager(_decision(), None)
    result = node(inputs)
    assert structured.invoke.call_count == 2 and result["final_rating"] == "Underweight"
    node, structured = _manager(_decision(), _decision())
    node(inputs)
    assert structured.invoke.call_count == 2


def test_no_priced_case_means_no_extra_call():
    inputs, _row_ = _case_state()
    inputs["shared_valuation_scenarios"] = {"status": "unavailable", "requests": [], "rows": [], "reasons": []}
    inputs["financial_claim_validation"] = {"raw_report": "```valuation_scenarios\n[]\n```"}
    node, structured = _manager(_decision())
    node(inputs)
    assert structured.invoke.call_count == 1
    assert "No priced scenario case in this run" in structured.invoke.call_args.args[0]


def _card(view, rating="Underweight", reason=None):
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )

    inputs, row = _case_state()
    inputs["final_rating"] = rating
    inputs["evidence_quality"] = {**inputs["evidence_quality"], "checks": []}
    entries = None if view is None else [{**entry, "case_id": row["case_id"], "version": 1} for entry in view]
    inputs["unvalidated_outputs"] = {"portfolio_manager": {
        "case_contract": 1, "scenario_contract": 1, "contract_version": 1, "configured_horizon_months": 6,
        "structured": {"rating": rating, "time_horizon": "6 months", "scenario_view": entries,
                       "rating_basis_reason": reason, "no_case_reason": "x"}}}
    record = prepare_decision_context(inputs)
    # The card escapes Markdown punctuation; compare the text a reader sees.
    return record, render_decision_context(record, include_mechanical=False).replace("\\", ""), inputs


def test_decision_card_states_the_scenario_basis():
    record, text, _ = _card([{"disposition": "accepted", "weight": 1, "reason": "Base."}])
    assert record["scenario_decision"]["status"] == "addressed" and record["basis"] == "conditional scenarios"
    assert LABEL in text and "accepted, weight 1.00" in text and "Rating check:" in text
    assert "not a price target or a demonstrated expected return" in text
    # The strict price-target path is untouched.
    assert record["adopted_case"] is None and record["target"]["status"] == "unsupported"


def test_decision_card_says_when_the_cases_were_not_addressed_and_the_score_drops():
    from tests.test_operational_audit import observed
    from tradingagents.operational_audit import assess_audit

    record, text, _ = _card(None)
    assert record["scenario_decision"]["status"] == "unaddressed" and record["basis"] == "risk assessment"
    assert "decision basis is opinion only" in text
    assessment = assess_audit({**observed(), "decision_context": record})
    assert (assessment["score"], assessment["findings"][0]["code"]) == (3, "decision_basis_unaddressed")
    good, _, _ = _card([{"disposition": "accepted", "weight": 1, "reason": "Base."}])
    assert assess_audit({**observed(), "decision_context": good})["score"] == 5


def test_an_unexplained_contrary_rating_is_printed_and_scored():
    from tests.test_operational_audit import observed
    from tradingagents.operational_audit import assess_audit

    record, text, inputs = _card([{"disposition": "accepted", "weight": 1, "reason": "Base."}], rating="Buy")
    summary = record["scenario_decision"]
    if summary["direction"] == "below":
        assert summary["consistency"] == "unexplained" and "no reason was given" in text
        assert assess_audit({**observed(), "decision_context": record})["score"] == 3
        explained, text, _ = _card([{"disposition": "accepted", "weight": 1, "reason": "Base."}], rating="Buy",
                                   reason="Rebound expected.")
        assert explained["scenario_decision"]["consistency"] == "explained" and "Rebound expected." in text
        assert assess_audit({**observed(), "decision_context": explained})["score"] == 5
    else:
        pytest.fail(f"fixture case is not below the close: {summary['direction']} {summary['weighted_value']}")
