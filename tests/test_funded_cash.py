"""A case that says what its operating cash holds has its cash completed by code; one that does not is unchanged."""
from datetime import date
from decimal import Decimal

from tests.test_lease_roll import FILED, LEASE, TOTALS
from tradingagents.agents.valuation_cases import CaseCapital, funded_cash, funding_check

SNAPSHOT = date(2026, 9, 30)
TERMS = {"schedule": FILED, "schedule_totals": TOTALS, "leases": [LEASE], "notes": []}


def _value(amount):
    return {"value": str(amount), "fact_ids": ["x"], "assumption": "estimated", "reason": "r"}


def _capital(after_interest=None, includes_rent=None, payments=-320453000):
    answers = {key: value for key, value in (("operations_after_lease_interest", after_interest),
                                             ("operations_include_new_lease_rent", includes_rent)) if value is not None}
    return CaseCapital.model_validate({
        "valuation_date": "2027-12-31", "currency": "USD", "closing_shares": _value(120000000), "cash": _value(1),
        "obligations": {"borrowings": _value(149578000)},
        "cash_changes": [{"source": "finance_payments", "amount": str(payments), "reason": "r"},
                         {"source": "operations", "amount": "900000000", "reason": "r"}], **answers})


def test_a_case_that_answers_neither_question_is_left_exactly_as_before():
    funded = funded_cash(_capital(), SNAPSHOT, TERMS)
    assert funded["adjustment"] == "0" and funded["decided"] == []
    funding = funding_check(_capital(), SNAPSHOT, None, TERMS)
    assert "funded" not in funding and funding["limit"].startswith("Not in the case arithmetic, sized from the filing: ")
    assert "operations_after_lease_interest" not in _capital().model_dump(mode="json")


def test_interest_inside_the_payments_is_added_back_when_operating_cash_is_after_interest():
    funded = funded_cash(_capital(after_interest=True, includes_rent=True), SNAPSHOT, TERMS)
    back = Decimal(funded["interest_added_back"])
    assert Decimal("50000000") < back < Decimal("80000000") and funded["adjustment"] == str(back)
    assert funded["decided"] == ["interest", "rent"] and funded["rent_deducted"] is None
    # A case that deducts only half the scheduled payments can only have half the interest counted twice.
    half = funded_cash(_capital(after_interest=True, includes_rent=True, payments=-160226500), SNAPSHOT, TERMS)
    assert abs(Decimal(half["interest_added_back"]) * 2 - back) <= 1


def test_rent_on_leases_that_commence_is_deducted_when_operating_cash_leaves_it_out():
    funded = funded_cash(_capital(after_interest=False, includes_rent=False), SNAPSHOT, TERMS)
    rent = Decimal(funded["rent_deducted"])
    assert funded["interest_added_back"] is None and funded["adjustment"] == str(-rent)
    low, high = (Decimal(v) for v in funded["rent_range"])
    assert low == 0 and low < rent < high
    text = funding_check(_capital(after_interest=False, includes_rent=False), SNAPSHOT, None, TERMS)["limit"]
    assert text.startswith("Computed in the case arithmetic: operating cash is stated before lease interest")
    assert "is deducted (" in text and "Not in the case arithmetic" not in text and text.endswith("No discounting.")
    assert "commencements are spread evenly across the stated window" in text


def test_one_answer_completes_one_line_and_the_other_question_stays_open():
    funding = funding_check(_capital(after_interest=True), SNAPSHOT, None, TERMS)
    assert funding["funded"]["decided"] == ["interest"]
    assert "is added back" in funding["limit"] and "if it leaves out rent on leases that have not commenced" in funding["limit"]
    assert "counts that interest twice" not in funding["limit"]


def test_what_the_filing_cannot_size_changes_nothing_and_stays_open():
    bare = {"schedule": None, "schedule_totals": {}, "leases": [], "notes": []}
    funded = funded_cash(_capital(after_interest=True, includes_rent=False), SNAPSHOT, bare)
    # No schedule: the interest cannot be split, so nothing is added back. No lease awaiting commencement: no rent.
    assert funded["adjustment"] == "0" and funded["decided"] == ["rent"]
    assert "no lease awaiting commencement was retained" in funded["lines"][0]
    unreadable = funded_cash(_capital(includes_rent=False), SNAPSHOT, {**bare, "leases": [{"unit": "EUR"}]})
    assert unreadable["adjustment"] == "0" and unreadable["decided"] == []
    no_payments = funded_cash(_capital(after_interest=True, payments=0), SNAPSHOT, TERMS)
    assert no_payments["adjustment"] == "0" and no_payments["decided"] == []


def test_the_case_value_moves_by_exactly_the_completed_cash(monkeypatch):
    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state
    from tradingagents.agents import shared_valuation
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    def price(answers):
        row = revenue_case()
        row["request"]["capital"].update(answers)
        record = prepare_shared_valuation(state([row]))
        assert record["status"] == "available", record["reasons"]
        return record["rows"][0]

    lease = {"undiscounted_amount": "110", "unit": "USD", "as_of": None, "commencement_start": "2026-01",
             "commencement_end": "2026-01", "weighted_average_term_years": "11"}

    before = price({})
    snapshot = before["result"]["capital_snapshot_date"]
    monkeypatch.setattr(shared_valuation, "_funding_terms", lambda value: {
        "schedule": None, "schedule_totals": {}, "notes": [], "leases": [{**lease, "as_of": snapshot}]})
    same, after = price({}), price({"operations_include_new_lease_rent": False})
    assert same["result"]["target"] == before["result"]["target"]
    deducted = Decimal(after["funding"]["funded"]["rent_deducted"])
    assert deducted > 0
    assert (Decimal(before["result"]["target"]) - Decimal(after["result"]["target"])) * 110 == deducted
    assert any(line.startswith("cash completed by code:") for line in after["result"]["assumptions"])
    assert after["request"]["capital"]["operations_include_new_lease_rent"] is False


def test_lease_balances_are_carried_to_the_period_end_only_when_the_schedule_matches_the_filed_balance():
    from tradingagents.agents.valuation_cases import carry_leases

    end = date(2027, 12, 31)
    filed = {"finance_leases": Decimal("736179000"), "equipment": Decimal("187420000"),
             "operating_leases": Decimal("666611000")}
    carried = carry_leases(filed, SNAPSHOT, end, TERMS)
    assert Decimal("400000000") < carried["finance_leases"]["value"] < filed["finance_leases"]   # principal repaid
    assert "carried to 2027-12-31 on the filed payment schedule" in carried["finance_leases"]["reason"]
    assert carried["operating_leases"]["value"] > filed["operating_leases"]
    assert "Their classification is not stated in the filing" in carried["operating_leases"]["reason"]
    # A filed balance the schedule does not reproduce is held as filed: nothing is carried for it.
    off = carry_leases({"finance_equipment": Decimal("500000000"), "operating_leases": Decimal(1)}, SNAPSHOT, end, TERMS)
    assert "finance_equipment" not in off and "operating_leases" in off
    # A company with no schedule and no lease awaiting commencement gets nothing carried at all.
    assert carry_leases(filed, SNAPSHOT, end, {"schedule": None, "leases": []}) == {}
    assert carry_leases(filed, SNAPSHOT, end, None) == {} and carry_leases({}, SNAPSHOT, end, TERMS) == {}


def test_the_analyst_is_asked_the_two_questions_and_a_carried_case_may_answer_them():
    import inspect

    from tradingagents.agents import prior_cases
    from tradingagents.agents.analysts import fundamentals_analyst
    prompt = inspect.getsource(fundamentals_analyst)
    assert '"operations_after_lease_interest": true or false' in prompt
    assert '"operations_include_new_lease_rent": true or false' in prompt
    assert "Funding feasibility remains unassessed" not in prompt
    assert "is not a change to its values" in inspect.getsource(prior_cases)


def test_a_question_the_filing_cannot_size_stays_visible_when_the_other_is_resolved():
    bare = {"schedule": None, "schedule_totals": {}, "leases": [LEASE], "notes": []}
    funding = funding_check(_capital(after_interest=True, includes_rent=False), SNAPSHOT, None, bare)
    assert funding["funded"]["decided"] == ["rent"]
    assert "is deducted" in funding["limit"]
    assert "lease interest" in funding["limit"] and "could not be sized" in funding["limit"]
    unreadable = funding_check(_capital(after_interest=False, includes_rent=False), SNAPSHOT, None,
                               {**bare, "leases": [{"unit": "EUR"}]})
    assert "rent on leases that commence" in unreadable["limit"] and "could not be sized" in unreadable["limit"]


def test_a_case_that_supplies_lease_balances_as_filed_has_them_carried_like_one_that_leaves_them_out():
    from tradingagents.agents.valuation_cases import carry_leases

    filed = {"finance_equipment": Decimal("923599000"), "operating_leases": Decimal("666611000")}
    carried = carry_leases(filed, SNAPSHOT, date(2027, 12, 31), TERMS)
    assert carried["finance_equipment"]["value"] < filed["finance_equipment"]
    assert carried["operating_leases"]["value"] > filed["operating_leases"]
    # Finance leases and equipment given separately are scaled together; a partial set is not carried.
    split = carry_leases({"finance_leases": Decimal("736179000"), "equipment": Decimal("187420000")}, SNAPSHOT,
                         date(2027, 12, 31), TERMS)
    assert split["finance_leases"]["value"] + split["equipment"]["value"] == carried["finance_equipment"]["value"]
    assert "finance_leases" not in carry_leases({"finance_leases": Decimal("736179000")}, SNAPSHOT, date(2027, 12, 31), TERMS)


def test_supplied_and_omitted_lease_balances_price_the_same(monkeypatch):
    """The audit's case: unchanged_from_snapshot lease balances must not stay flat when the schedule can carry them."""
    import json
    import os

    from tradingagents.agents.shared_valuation import prepare_shared_valuation
    path = os.path.expanduser("~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-10_6fe6324b.json")
    if not os.path.exists(path):
        import pytest
        pytest.skip("saved run not on this machine")
    with open(path) as handle:
        state = json.load(handle)
    saved = state["shared_valuation_scenarios"]["rows"][0]
    omitted = prepare_shared_valuation(state, [{"name": saved["name"], "request": saved["request"]}])["rows"][0]
    supplied = json.loads(json.dumps(omitted["source_bound_sensitivity_requests"]["finance_equipment"]))
    lease = supplied["capital"]["obligations"]["finance_equipment"]
    lease.update(value="923599000", assumption="unchanged_from_snapshot", reason="As filed.")
    priced = prepare_shared_valuation(state, [{"name": saved["name"], "request": supplied}])
    assert priced["status"] == "available", priced["reasons"]
    assert priced["rows"][0]["result"]["target"] == omitted["sensitivities"]["finance_equipment"]
