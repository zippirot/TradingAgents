"""A note still outstanding at the period end converts when the case's own value is above its conversion price.

A made-up company throughout: 110 shares, a case worth 3,520 with every note counted as debt (32.00 a share).
"""
from datetime import date
from decimal import Decimal

import pytest

from tradingagents.agents.valuation_cases import (
    CaseCapital,
    outstanding_convertibles,
    settle_convertibles,
)

EQUITY, SHARES = Decimal(3520), Decimal(110)
SNAPSHOT = date(2026, 9, 30)


def note(price, principal=100, call=None, name="2030 Convertible Notes"):
    return {"name": name, "principal": Decimal(principal), "price": Decimal(price), "call": call}


def close(a, b):
    return abs(Decimal(a) - Decimal(b)) < Decimal("1e-20")


def test_a_note_below_the_case_value_becomes_shares_and_leaves_borrowings():
    settled = settle_convertibles(EQUITY, SHARES, [note(20)], Decimal(160))
    # 100 of principal at 20 is 5 shares; the debt is no longer owed.
    assert close(settled["value"], Decimal(3620) / 115) and settled["shares"] == 115 and settled["debt_removed"] == 100
    assert "treated as converted by code" in settled["lines"][0] and "and 100 leaves borrowings." in settled["lines"][0]


def test_a_note_above_the_case_value_stays_as_debt_and_changes_nothing():
    settled = settle_convertibles(EQUITY, SHARES, [note(40)], Decimal(160))
    assert settled["value"] == 32 and settled["shares"] == 110 and settled["debt_removed"] == 0
    assert settled["lines"] == ["2030 Convertible Notes: stays as debt. The case's value of 32.00 a share is not above "
                                "the 40 conversion price."]
    assert settle_convertibles(EQUITY, SHARES, [], Decimal(160)) == {
        "value": Decimal(32), "shares": SHARES, "debt_removed": Decimal(0), "lines": []}


def test_a_capped_call_returns_shares_up_to_its_cap_and_no_further():
    call = (Decimal(20), Decimal(25), date(2030, 8, 15))
    above = settle_convertibles(EQUITY, SHARES, [note(20, call=call)], Decimal(160))
    # Above the cap the call is worth (25 - 20) on each of the 5 shares: value = (3620 + 25) / 115.
    assert close(above["value"], Decimal(3645) / 115) and "returned by the capped call" in above["lines"][0]
    assert close(above["shares"], 115 - 25 / above["value"])
    wide = (Decimal(20), Decimal(50), date(2030, 8, 15))
    inside = settle_convertibles(EQUITY, SHARES, [note(20, call=wide)], Decimal(160))
    # Between strike and cap the call returns every share above par: only the principal's worth of shares is added.
    assert close(inside["value"], Decimal(3520) / 110) and close(inside["shares"], 110 + 100 / inside["value"])


def test_each_note_is_decided_on_its_own_price_and_debt_is_never_removed_twice():
    settled = settle_convertibles(EQUITY, SHARES, [note(40, name="2031 Convertible Notes"), note(20)], Decimal(160))
    assert settled["debt_removed"] == 100 and settled["shares"] == 115
    assert "2030 Convertible Notes: treated as converted" in settled["lines"][0]
    assert "2031 Convertible Notes: stays as debt" in settled["lines"][1]
    both = settle_convertibles(EQUITY, SHARES, [note(10, name="2031 Convertible Notes"), note(20)], Decimal(160))
    # Only 160 is owed, so the second note can remove no more than the 60 that is left.
    assert both["debt_removed"] == 160 and both["shares"] == 125 and close(both["value"], Decimal(3680) / 125)


def test_a_basis_that_counts_no_borrowings_adds_the_shares_and_removes_no_debt():
    settled = settle_convertibles(Decimal(3600), SHARES, [note(20)], None)
    assert settled["debt_removed"] == 0 and close(settled["value"], Decimal(3600) / 115)
    assert "this basis counts no borrowings" in settled["lines"][0]


def test_a_note_whose_own_dilution_takes_the_value_below_its_price_stays_as_debt():
    settled = settle_convertibles(EQUITY, SHARES, [note(31, principal=3410)], None)
    assert settled["value"] == 32 and settled["shares"] == 110 and "stays as debt" in settled["lines"][0]


def _capital(**extra):
    value = {"fact_ids": ["x"], "assumption": "estimated", "reason": "r"}
    return CaseCapital.model_validate({
        "valuation_date": "2027-12-31", "currency": "USD", "closing_shares": {**value, "value": "110"},
        "cash": {**value, "value": "80"}, "obligations": {"borrowings": {**value, "value": "160"}}, **extra})


FILED = {"name": "2030 Convertible Notes", "principal": "100", "currency": "USD", "as_of": "2026-09-30",
         "maturity_date": "2030-08-15", "conversion_price": "20",
         "capped_call": {"strike": "20", "cap": "25", "expires": "2030-08-15", "locator": "b"}}


def test_only_notes_outstanding_at_the_period_end_and_not_already_treated_by_the_case_are_decided():
    notes, lines = outstanding_convertibles(_capital(), SNAPSHOT, {"convertibles": [FILED]})
    assert notes == [{"name": "2030 Convertible Notes", "principal": Decimal(100), "price": Decimal(20),
                      "call": (Decimal(20), Decimal(25), date(2030, 8, 15))}] and lines == []
    for skipped in ({**FILED, "maturity_date": "2027-06-01"}, {**FILED, "as_of": "2026-06-30"},
                    {**FILED, "currency": "EUR"}, {**FILED, "principal": "n/a"}, {"name": "x"}):
        assert outstanding_convertibles(_capital(), SNAPSHOT, {"convertibles": [skipped]}) == ([], [])
    assert outstanding_convertibles(_capital(), SNAPSHOT, None) == ([], [])
    # A capped call that expires before the period end offsets nothing.
    (early,), _ = outstanding_convertibles(_capital(), SNAPSHOT, {"convertibles": [
        {**FILED, "capped_call": {**FILED["capped_call"], "expires": "2027-06-30"}}]})
    assert early["call"] is None
    open_notes, open_lines = outstanding_convertibles(_capital(), SNAPSHOT, {"convertibles": [{**FILED, "conversion_price": None}]})
    assert open_notes == [] and "left open" in open_lines[0] and "stays as debt" in open_lines[0]


@pytest.mark.parametrize("stated", [
    {"cash_changes": [{"source": "debt", "amount": "-100", "reason": "Repurchased.", "instrument": "2030 notes"}]},
    {"share_changes": [{"source": "conversion", "shares": "5", "converted_principal": "100",
                        "instrument": "2030 Convertible Notes", "reason": "Converted."}]}])
def test_a_note_the_case_repays_or_converts_itself_is_never_converted_again(stated):
    notes, lines = outstanding_convertibles(_capital(**stated), SNAPSHOT, {"convertibles": [FILED]})
    assert notes == [] and lines == ["2030 Convertible Notes: the case states its own repayment or conversion, so code adds nothing."]


def test_an_unnamed_cash_change_keeps_the_record_shape_it_always_had():
    record = _capital(cash_changes=[{"source": "debt", "amount": "-1", "reason": "r"}]).model_dump(mode="json")
    assert "instrument" not in record["cash_changes"][0]


def test_a_whole_case_is_priced_with_the_note_converted(monkeypatch):
    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state
    from tradingagents.agents import shared_valuation
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    def price():
        record = prepare_shared_valuation(state([revenue_case()]))
        assert record["status"] == "available", record["reasons"]
        return record["rows"][0]["result"]

    before = price()
    assert Decimal(before["target"]) == 32 and not any("convertible" in line for line in before["assumptions"])
    terms = {"schedule": None, "schedule_totals": {}, "notes": [], "leases": [],
             "convertibles": [{**FILED, "as_of": before["capital_snapshot_date"]}]}
    monkeypatch.setattr(shared_valuation, "_funding_terms", lambda value: terms)
    after = price()
    assert close(after["target"], Decimal(3645) / 115) and Decimal(after["net_obligations"]) == -20
    assert close(after["shares_outstanding"], 115 - 25 / Decimal(after["target"]))
    lines = [line for line in after["assumptions"] if line.startswith("convertible notes: ")]
    assert "treated as converted by code" in lines[0] and "never both" in lines[-1]
    assert "A capped call covering notes already repurchased is not valued." in lines[-1]
    # The outcome is said beside the funding check, where the report and the manager's brief read it.
    row = prepare_shared_valuation(state([revenue_case()]))["rows"][0]
    assert row["funding"]["convertibles"] == [lines[0][len("convertible notes: "):]]
    assert row["funding"]["summary"].endswith(row["funding"]["convertibles"][0])


def test_the_analyst_is_told_code_decides_outstanding_notes():
    from tradingagents.agents.analysts.fundamentals_analyst import SHARED_VALUATION_INPUTS as text
    assert "Code decides every convertible note still outstanding at the valuation date" in text
    assert '"instrument":"<note name>"' in text and "add no conversion shares for it yourself" in text
