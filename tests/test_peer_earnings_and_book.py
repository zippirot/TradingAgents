"""Peers and the company itself are also compared on earnings and on book value, not only on revenue.

Reassessment 2026-11-13: evaluators marked every earnings-valued company down because "peers are compared on
revenue multiples only", and banks because there is "no price-to-book or return-on-equity". An earnings case had
no peer figure on its own basis.

Boundary: three extra figures per company (price over the latest filed annual diluted EPS, market value over the
latest filed stockholders' equity, the latest filed annual net income over that equity), each stated only when
its filed inputs exist once and are positive. The revenue figures and which peers are accepted do not change.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from tradingagents.agents.valuation_reference import earnings_and_book, render_earnings_and_book


def _fact(metric, value, end, start=None):
    return SimpleNamespace(metric=metric, value=Decimal(value), origin="reported",
                           period_start=date.fromisoformat(start) if start else None, period_end=date.fromisoformat(end))


FACTS = [_fact("Diluted EPS", "4", "2025-12-31", "2025-01-01"), _fact("Diluted EPS", "1.2", "2026-06-30", "2026-04-01"),
         _fact("Net Income", "400", "2025-12-31", "2025-01-01"), _fact("Stockholders Equity", "2000", "2026-06-30"),
         _fact("Stockholders Equity", "1800", "2025-12-31")]


def test_the_three_figures_come_from_the_latest_filed_annual_and_balance_figures():
    found = earnings_and_book(FACTS, Decimal("80"), Decimal("100"), date(2026, 10, 19))
    assert Decimal(found["price_to_earnings"]) == 20 and found["eps_period_end"] == "2025-12-31"
    assert Decimal(found["price_to_book"]) == 4 and found["equity_date"] == "2026-06-30"       # 80 x 100 / 2000
    assert Decimal(found["return_on_equity_percent"]) == 20                                     # 400 / 2000
    text = render_earnings_and_book(found)
    assert "20.0× filed annual diluted EPS" in text and "4.0× book value" in text and "return on equity 20.0%" in text


def test_a_figure_without_its_filed_input_is_left_out_not_guessed():
    losses = [_fact("Diluted EPS", "-1", "2025-12-31", "2025-01-01"), *FACTS[2:]]
    found = earnings_and_book(losses, Decimal("80"), Decimal("100"), date(2026, 10, 19))
    assert found["price_to_earnings"] is None and found["price_to_book"] is not None
    assert "diluted EPS" not in render_earnings_and_book(found)
    assert render_earnings_and_book(earnings_and_book([], Decimal("80"), Decimal("100"), date(2026, 10, 19))) == ""
    later = earnings_and_book([_fact("Stockholders Equity", "2000", "2026-12-31")], Decimal("80"), Decimal("100"), date(2026, 10, 19))
    assert later["price_to_book"] is None            # a balance after the price session is not used
