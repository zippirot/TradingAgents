"""Stage 3: every case carries one statement of its balances from the filing to the period end.

The statement changes no value. Each figure is one the arithmetic already used; the tests hold it to that.
"""
import re
from datetime import date
from decimal import Decimal

from tests.test_funded_cash import SNAPSHOT, TERMS, _capital
from tests.test_source_bound_lease_sensitivities import example
from tradingagents.agents.valuation_cases import (
    STATEMENT,
    CaseCapital,
    RevenueCase,
    carry_leases,
    funded_cash,
    funded_statement,
    price_case,
    settle_convertibles,
)
from tradingagents.dataflows.financial_evidence import EvidencePackage

M = Decimal(1_000_000)


def _lines(result):
    return [a[len(STATEMENT):] for a in result.assumptions if a.startswith(STATEMENT)]


def _figure(text, after):
    return Decimal(re.search(re.escape(after) + r" ([+-]?)([\d,]+\.\d)M", text).expand(r"\1\2").replace(",", ""))


def test_a_priced_case_states_every_balance_and_its_closing_figures_reproduce_the_value():
    state, submitted = example()
    package = EvidencePackage.model_validate(state["financial_evidence"])
    result, _ = price_case(RevenueCase.model_validate(submitted[0]["request"]), package, ())
    lines = _lines(result)
    assert [line.split(":")[0] for line in lines] == [
        "from the 2026-09-30 filing to 2027-12-31. Each line gives the opening balance as filed, what the analyst "
        "assumes, what code computes under a stated assumption, and the closing balance.",
        "cash", "borrowings", "shares", "value", "not stated by the case"]
    cash, debt, shares, value = lines[1:5]
    assert "(filed)" in cash and "(filed)" in debt and "(filed)" in shares
    # Closing borrowings less closing cash is the net obligation the value line uses, and the value is the target.
    net = _figure(debt, "closing") - _figure(cash, "closing")
    assert abs(net - _figure(value, "less net obligations of")) <= Decimal("0.1")
    assert abs(net - result.net_obligations / M) <= Decimal("0.1")
    assert f"{result.shares_outstanding:,.0f} shares, {result.target:.2f} a share." in value
    assert f"closing {result.shares_outstanding:,.0f}." in shares


def _statement(capital, terms=TERMS, basis="borrowings_only", notes=(), opening=None, unstated=()):
    funded = funded_cash(capital, SNAPSHOT, terms)
    carried = carry_leases({k: v.value for k, v in capital.obligations.items()
                            if k != "borrowings" and v.assumption == "unchanged_from_snapshot"},
                           SNAPSHOT, capital.valuation_date, terms)
    capitalized = Decimal(8_000_000_000)
    cash = capital.cash.value + Decimal(funded["adjustment"])
    net = None if basis == "equity" else capital.obligations["borrowings"].value - cash
    equity = capitalized if net is None else capitalized - net
    settled = settle_convertibles(equity, capital.closing_shares.value, list(notes),
                                  None if basis == "equity" else capital.obligations["borrowings"].value)
    opening = opening or {"cash": Decimal(1), "closing_shares": capital.closing_shares.value,
                          **{k: v.value for k, v in capital.obligations.items()}}
    return [line[len(STATEMENT):] for line in funded_statement(
        capital, SNAPSHOT, opening, funded, carried, settled, basis, capitalized, net, terms, unstated)], settled


def test_each_step_is_marked_analyst_or_code_and_code_steps_carry_their_amounts():
    lines, _ = _statement(_capital(after_interest=True, includes_rent=False))
    cash = lines[1]
    assert "analyst: finance payments -320.5M USD; operations +900.0M USD" in cash
    assert "code: lease interest already inside operating cash added back +" in cash
    assert "rent on leases that commence deducted -" in cash
    silent, _ = _statement(_capital())
    assert "code: no change" in silent[1]


def test_a_converted_note_shows_on_both_the_borrowings_and_the_shares_lines():
    note = {"name": "2030 Convertible Notes", "principal": Decimal(100_000_000), "price": Decimal(20), "call": None}
    lines, settled = _statement(_capital(), notes=[note])
    debt, shares = lines[2], lines[3]
    assert "code: converted notes leave borrowings -100.0M USD; closing 49.6M USD." in debt
    assert "code: notes converted, net of any capped call +5,000,000; closing 125,000,000." in shares
    assert settled["debt_removed"] == 100_000_000


def test_an_estimated_balance_is_the_analysts_and_a_lease_outside_the_basis_says_so():
    capital = CaseCapital.model_validate({
        **_capital().model_dump(mode="json"),
        "obligations": {"borrowings": {"value": "100000000", "fact_ids": ["x"], "assumption": "estimated", "reason": "r"},
                        "finance_equipment": {"value": "923599000", "fact_ids": ["y"],
                                              "assumption": "unchanged_from_snapshot", "reason": "r"}}})
    lines, _ = _statement(capital, opening={"cash": Decimal(1), "closing_shares": Decimal(120_000_000),
                                            "borrowings": Decimal(149_578_000), "finance_equipment": Decimal(923_599_000)})
    assert "borrowings: opening 149.6M USD (filed); analyst: closing set to 100.0M USD (-49.6M USD)" in lines[2]
    lease = lines[3]
    assert lease.startswith("finance leases and equipment: opening 923.6M USD (filed); analyst: no change stated; "
                            "code: carried to the period end on the filed payment schedule -")
    assert lease.endswith("outside this case's borrowings only basis, used in the sensitivities only.")


def test_a_note_falling_due_in_the_period_that_the_case_leaves_on_both_sides_is_named():
    terms = {**TERMS, "notes": [{"name": "2026 Convertible Notes", "maturity_date": "2026-12-01",
                                 "principal_outstanding": "312322", "principal_unit": "USD thousands"}]}
    lines, _ = _statement(_capital(), terms=terms, unstated=["Scheduled payments of 1.0M USD are not stated."])
    last = lines[-1]
    assert last.startswith("not stated by the case: Scheduled payments of 1.0M USD are not stated. 2026 Convertible "
                           "Notes: 312.3M USD of principal falls due 2026-12-01, inside the period.")
    assert "net obligations are the same either way" in last
    # Repaid by the case, or due after the period: nothing to name.
    repaid = CaseCapital.model_validate({**_capital().model_dump(mode="json"), "cash_changes": [
        {"source": "debt", "amount": "-312322000", "reason": "r"}, {"source": "operations", "amount": "1", "reason": "r"}]})
    assert _statement(repaid, terms=terms)[0][-1] == "nothing the filing schedules inside the period is left unstated by the case."
    later = {**TERMS, "notes": [{**terms["notes"][0], "maturity_date": "2030-08-15"}]}
    assert "falls due" not in _statement(_capital(), terms=later)[0][-1]


def test_an_equity_basis_and_a_company_with_nothing_but_cash_and_shares_still_get_a_plain_statement():
    bare = {"schedule": None, "schedule_totals": {}, "leases": [], "notes": []}
    capital = CaseCapital.model_validate({
        "valuation_date": "2027-12-31", "currency": "USD", "obligations": {},
        "closing_shares": {"value": "1000", "fact_ids": ["s"], "assumption": "unchanged_from_snapshot", "reason": "r"},
        "cash": {"value": "50000000", "fact_ids": ["c"], "assumption": "unchanged_from_snapshot", "reason": "r"}})
    lines, _ = _statement(capital, terms=bare, basis="equity",
                          opening={"cash": Decimal(50_000_000), "closing_shares": Decimal(1000)})
    assert [line.split(":")[0] for line in lines[1:]] == ["cash", "shares", "value",
                                                         "nothing the filing schedules inside the period is left unstated by the case."]
    assert "this equity basis does not use cash" in lines[1] and "8,000.0M USD of equity value, over 1,000 shares" in lines[3]
    assert date(2027, 12, 31) == capital.valuation_date
