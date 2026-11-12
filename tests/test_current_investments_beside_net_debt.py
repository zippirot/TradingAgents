"""Current investments are shown beside every net-debt figure; no existing figure changes.

The figures a case and the history are compared on stay "less cash", because past quarters carry no
established investments figure and the two would stop being on one basis.
"""
from decimal import Decimal

from tests.test_case_valuation import revenue_case
from tests.test_price_implied_guidance_ranges import source_state
from tests.test_shared_valuation import state
from tradingagents.agents.shared_valuation import prepare_shared_valuation
from tradingagents.agents.valuation_comparison import (
    price_implied_valuation,
    render_price_implied_valuation,
)


def _with_investments(package, value, like="cash"):
    cash = next(f for f in package["facts"] if f["fact_id"] == like)
    package["facts"].append({**cash, "fact_id": "investments", "metric": "Current Marketable Securities", "value": str(value),
                             "locator": "synthetic/investments"})
    return package


def test_the_price_implied_table_also_states_each_multiple_with_current_investments_deducted(monkeypatch):
    plain = source_state(monkeypatch)
    before = price_implied_valuation(plain)
    assert "less_current_investments" not in before["rows"][0]["ratios"]
    assert "Current investments" not in render_price_implied_valuation(before)
    _with_investments(plain["financial_evidence"], 50_000_000)
    after = price_implied_valuation(plain)
    row = after["rows"][0]
    # Equity 20 x 100M = 2,000M; borrowings 200M less cash 100M; trailing revenue 1,000M.
    assert Decimal(row["ratios"]["trailing_revenue"]) == Decimal("2.1") == Decimal(before["rows"][0]["ratios"]["trailing_revenue"])
    assert Decimal(row["ratios"]["less_current_investments"]) == Decimal("2.05")
    assert after["current_investments"]["fact_id"] == "investments"
    text = render_price_implied_valuation(after)
    assert "Current investments of 50000000" in text and "are not deducted in the table" in text and "2.05×" in text


def test_a_case_on_a_net_debt_basis_says_what_counting_current_investments_would_add_and_keeps_its_value():
    plain = prepare_shared_valuation(state([revenue_case()]))
    with_them = state([revenue_case()])
    _with_investments(with_them["financial_evidence"], 33)
    record = prepare_shared_valuation(with_them)
    assert record["status"] == "available", record["reasons"]
    assert record["rows"][0]["result"]["target"] == plain["rows"][0]["result"]["target"]
    lines = [a for a in record["rows"][0]["result"]["assumptions"] if "current investments" in a]
    # 33 over the case's 110 closing shares.
    assert len(lines) == 1 and "not counted in cash" in lines[0] and "0.30 a share" in lines[0]
    assert not any("current investments" in a for a in plain["rows"][0]["result"]["assumptions"])
    equity = state([revenue_case("equity")])
    _with_investments(equity["financial_evidence"], 33)
    assert not any("current investments" in a for a in prepare_shared_valuation(equity)["rows"][0]["result"]["assumptions"])
