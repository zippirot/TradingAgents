"""Funding is assessed inside each revenue case from the filing's own schedules (Build Q, Q1)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.test_case_valuation import revenue_case
from tests.test_shared_valuation import state
from tradingagents.agents.shared_valuation import prepare_shared_valuation, render_shared_valuation
from tradingagents.agents.valuation_cases import CaseCapital, funding_check

SNAPSHOT = date(2026, 9, 30)
SCHEDULE = {"as_of": SNAPSHOT, "years": {"2026": Decimal("70400000"), "2027": Decimal("250000000"),
                                         "2028": Decimal("249100000")}}
NOTE = {"name": "2026 Convertible Notes", "principal_outstanding": "312322", "principal_unit": "USD thousands",
        "as_of": "2026-09-30", "maturity_date": "2026-12-01"}


def _value(amount):
    return {"value": str(amount), "fact_ids": ["x"], "assumption": "estimated", "reason": "r"}


def _capital(cash_changes=(), share_changes=(), borrowings=149578000, valuation_date="2027-12-31"):
    return CaseCapital.model_validate({
        "valuation_date": valuation_date, "currency": "USD", "closing_shares": _value(120), "cash": _value(1),
        "obligations": {"borrowings": _value(borrowings)},
        "cash_changes": [{"source": s, "amount": str(a), "reason": "r"} for s, a in cash_changes],
        "share_changes": list(share_changes)})


def _check(capital, schedule=SCHEDULE, notes=(NOTE,), borrowings_snapshot=Decimal(461630000)):
    return funding_check(capital, SNAPSHOT, borrowings_snapshot, {"schedule": schedule, "notes": list(notes)})


def test_case_stating_scheduled_payments_and_note_repayment_is_assessed():
    funding = _check(_capital([("finance_payments", -320400000), ("debt", -312322000), ("operations", 400000000),
                               ("capex", -150000000)]))
    assert funding["status"] == "assessed" and funding["reasons"] == []
    assert funding["scheduled_finance_payments"] == "320400000" and funding["stated_finance_payments"] == "320400000"
    assert funding["maturing_note_principal"] == "312322000"
    assert funding["summary"].startswith("Funding assessed: ")
    assert "not commenced" in funding["limit"]


def test_case_omitting_scheduled_payments_is_partial_with_the_amount():
    # No operating cash stated: code has no starting point for a bridge, so the gap is named.
    funding = _check(_capital([("debt", -312322000)]))
    assert funding["status"] == "partial"
    assert funding["reasons"] == ["Scheduled finance and equipment payments of 320.4M USD through 2027-12-31 "
                                  "are not stated in the case's cash changes."]
    # With operating cash stated and no finance payments, code deducts the filed schedule itself.
    completed = _check(_capital([("debt", -312322000), ("operations", 100000000)]))
    assert completed["status"] == "assessed" and completed["reasons"] == []
    assert "are deducted by code from the filed schedule" in completed["summary"]
    assert Decimal(completed["funded"]["payments_applied"]) == Decimal(completed["scheduled_finance_payments"])
    short = _check(_capital([("finance_payments", -100000000), ("debt", -312322000)]))
    assert short["reasons"] == ["Scheduled finance and equipment payments are 320.4M USD through 2027-12-31; "
                                "the case states 100.0M USD."]


@pytest.mark.parametrize("capital,covered", [
    (_capital([("finance_payments", -320400000)]), False),
    (_capital([("finance_payments", -320400000)], borrowings=461630000), True),
    (_capital([("finance_payments", -320400000), ("debt", -312322000)]), True),
    (_capital([("finance_payments", -320400000)], share_changes=[
        {"source": "conversion", "shares": "1", "converted_principal": "312322000", "instrument": "2026 notes",
         "reason": "r"}]), True),
])
def test_a_maturing_note_must_be_repaid_converted_or_still_owed(capital, covered):
    funding = _check(capital)
    assert (funding["status"] == "assessed") is covered
    if not covered:
        assert funding["reasons"] == ["2026 Convertible Notes: principal of 312.3M USD matures 2026-12-01; "
                                      "the case accounts for 0.0M USD and borrowings fall below the snapshot."]


def test_schedule_is_prorated_within_the_final_year_and_ignores_later_years():
    half = _check(_capital([("debt", -312322000)], valuation_date="2027-06-30"))
    expected = Decimal("70400000") + Decimal("250000000") * 181 / 365
    assert Decimal(half["scheduled_finance_payments"]) == expected
    first = _check(_capital([("debt", -312322000)], valuation_date="2026-12-31"))
    assert first["scheduled_finance_payments"] == "70400000"


@pytest.mark.parametrize("schedule", [None, {**SCHEDULE, "as_of": date(2026, 6, 30)}, {"as_of": SNAPSHOT, "years": {}}])
def test_no_schedule_for_the_snapshot_is_unassessed_with_the_reason(schedule):
    funding = _check(_capital([("debt", -312322000)]), schedule=schedule)
    assert funding["status"] == "unassessed" and funding["scheduled_finance_payments"] is None
    assert funding["reasons"] == ["No finance-lease and equipment payment schedule dated 2026-09-30 was retained."]


@pytest.mark.parametrize("years,valuation_date", [
    ({"2026": Decimal("70400000")}, "2027-12-31"),
    ({"2026": Decimal("70400000"), "2028": Decimal("249100000")}, "2028-12-31"),
    (SCHEDULE["years"], "2029-12-31"),
])
def test_a_schedule_that_does_not_reach_the_case_date_is_not_assessed(years, valuation_date):
    capital = _capital([("finance_payments", -900000000), ("debt", -312322000)], valuation_date=valuation_date)
    funding = _check(capital, schedule={"as_of": SNAPSHOT, "years": years})
    assert funding["status"] == "unassessed" and funding["scheduled_finance_payments"] is None
    assert funding["reasons"] == [f"The payment schedule dated 2026-09-30 does not state every year through {valuation_date}."]


def test_notes_outside_the_period_or_with_unknown_units_do_not_block():
    later = {**NOTE, "maturity_date": "2030-08-15"}
    assert _check(_capital([("finance_payments", -320400000)]), notes=[later])["status"] == "assessed"
    odd = {**NOTE, "principal_unit": "units"}
    funding = _check(_capital([("finance_payments", -320400000)]), notes=[odd, "junk", {"name": 3}])
    assert funding["status"] == "partial" and "unit is not recognised" in funding["reasons"][0]


def test_priced_case_carries_its_funding_status_in_place_of_the_blanket_warning():
    record = prepare_shared_valuation(state([revenue_case()]))
    row = record["rows"][0]
    assert row["funding"]["status"] == "unassessed"
    warnings = " ".join(row["result"]["warnings"])
    assert "Funding feasibility unassessed" not in warnings and row["funding"]["summary"] in warnings
    text = render_shared_valuation(record)
    assert row["funding"]["summary"] in text and row["funding"]["limit"] in text


def test_new_cash_change_sources_are_accepted_and_old_ones_still_are():
    for source in ("finance_payments", "capex", "operations", "atm", "debt", "other"):
        _capital([(source, -1)])
    with pytest.raises(ValueError):
        _capital([("leases", -1)])


def test_filing_terms_from_the_run_reach_the_case(monkeypatch):
    import tradingagents.agents.shared_valuation as shared

    monkeypatch.setattr(shared, "lease_maturities", lambda _state: {
        "as_of": date(2026, 9, 30), "amounts": {"2026": Decimal(5), "2027": Decimal(7), "total": Decimal(99)},
        "source": "s"})
    row = revenue_case()
    inputs = state([row])
    snapshot = date.fromisoformat(prepare_shared_valuation(inputs)["rows"][0]["result"]["capital_snapshot_date"])
    monkeypatch.setattr(shared, "lease_maturities", lambda _state: {
        "as_of": snapshot, "amounts": {str(snapshot.year): Decimal(5), "2027": Decimal(7), "total": Decimal(99)},
        "source": "s"})
    funding = prepare_shared_valuation(inputs)["rows"][0]["funding"]
    # The fixture case states operating cash and no finance payments, so code deducts the schedule.
    assert funding["status"] == "assessed" and Decimal(funding["scheduled_finance_payments"]) > 0
    assert funding["funded"]["payments_applied"] == funding["scheduled_finance_payments"]
    monkeypatch.setattr(shared, "lease_maturities", lambda _state: (_ for _ in ()).throw(RuntimeError("x")))
    assert prepare_shared_valuation(inputs)["rows"][0]["funding"]["status"] == "unassessed"
    assert SimpleNamespace  # keep import used
