"""MSFT run 5bc202c4 (2026-11-11): three equity-basis cases stated shares only and all were rejected at capital.cash.

An equity-basis value is revenue times the multiple over shares; cash and debt do not enter it.
"""
from decimal import Decimal

from tests.test_case_valuation import revenue_case
from tests.test_shared_valuation import state
from tradingagents.agents.shared_valuation import prepare_shared_valuation


def _shares_only(basis):
    row = revenue_case(basis)
    for key in ("cash", "obligations", "cash_changes"):
        row["request"]["capital"].pop(key, None)
    return row


def test_an_equity_case_that_states_only_shares_is_priced_and_says_what_code_filled_in():
    record = prepare_shared_valuation(state([_shares_only("equity")]))
    assert record["status"] == "available", record["reasons"]
    row = record["rows"][0]
    assert abs(Decimal(row["result"]["target"]) * 110 - Decimal(3600)) < Decimal("1e-20")
    cash = row["request"]["capital"]["cash"]
    assert cash["assumption"] == "unchanged_from_snapshot" and cash["fact_ids"] == ["cash"]
    assert any("Row 1: cash and obligations were not stated" in reason for reason in record["reasons"])


def test_a_case_whose_value_uses_cash_still_has_to_state_it_and_is_told_what_is_missing():
    record = prepare_shared_valuation(state([_shares_only("borrowings_only")]))
    assert not record["rows"]
    assert "Row 1 omitted: required field capital.cash is missing" in record["reasons"][0]


def test_the_trader_action_reading_does_not_claim_a_position_is_already_held():
    """The same run: 'a change in the size of an existing position, not ... a new position' with nothing held."""
    from tradingagents.agents.trader.trader import _reading

    text = _reading("Action: Buy", "**Recommendation**: Overweight")
    assert "opening one where none is held" in text and "existing position" not in text
