"""The price record reaches back to the earnings year when a company files no cash balance.

Map 2b-14, seen on every JPMorgan and Progressive run: with no "Cash and Equivalents" balance the price was
fetched for two weeks only, the earnings case is anchored on its earnings year, and the comparison with price
failed ("Insufficient split coverage ..."). So bank and insurer reports carried no value against the price, no
reading of the stock by code, and nothing to catch an Overweight on a stock called Unattractive.

Boundary: only when no cash balance is filed; then the latest filed annual diluted EPS year end is the anchor,
the same fallback the earnings case itself uses. A company with a cash balance is fetched exactly as before.
"""
from datetime import date

from tradingagents.agents.evidence_validation import price_anchor


def _fact(metric, end, start=None, value="1"):
    return {"metric": metric, "value": value, "period_start": start, "period_end": end}


def test_the_latest_cash_balance_is_the_anchor_when_there_is_one():
    facts = [_fact("Cash and Equivalents", "2026-06-30"), _fact("Cash and Equivalents", "2026-09-30"),
             _fact("Diluted EPS", "2025-12-31", "2025-01-01")]
    assert price_anchor(facts) == date(2026, 9, 30)


def test_without_a_cash_balance_the_latest_annual_earnings_year_end_is_the_anchor():
    facts = [_fact("Cash and Equivalents", "2026-09-30", value=None), _fact("Diluted EPS", "2024-12-31", "2024-01-01"),
             _fact("Diluted EPS", "2025-12-31", "2025-01-01"), _fact("Diluted EPS", "2026-09-30", "2026-07-01")]
    assert price_anchor(facts) == date(2025, 12, 31)
    assert price_anchor([]) is None
