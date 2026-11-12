"""A case that ends short of cash says so, and says how the shortfall is treated.

Named by the user's evaluator and by the loop's on every DOCN report (2026-11-12): "the downside case runs
out of cash without modeling how that shortfall is funded" (closing cash -11.1M). The arithmetic already
nets a shortfall as an obligation, which values it exactly as a sale of shares at the case's own value;
nothing said so. Code now states the shortfall, that equivalence, and what the filed current investments
would cover. No value changes.
"""
from decimal import Decimal

from tradingagents.agents.valuation_cases import shortfall_statement


def test_a_shortfall_is_stated_with_the_share_sale_it_is_equivalent_to_and_what_investments_cover():
    text = shortfall_statement(Decimal("-11139216"), Decimal("178645000"), Decimal("120642916"), Decimal("56.27"), "USD")
    assert text.startswith("cash shortfall: the case ends 11.1M USD short of cash")
    # 11,139,216 / 56.27 = 197,960 shares, 0.16% of 120,642,916.
    assert "197,960 shares" in text and "0.16%" in text and "same value per share" in text
    assert "current investments of 178.6M USD" in text and "cover it" in text and "not counted" in text


def test_investments_that_do_not_cover_it_and_none_at_all_are_said_plainly():
    part = shortfall_statement(Decimal("-500000000"), Decimal("178645000"), Decimal("120000000"), Decimal("50"), "USD")
    assert "cover 178.6M USD of it" in part and "321.4M USD" in part and "new financing" in part
    none = shortfall_statement(Decimal("-500000000"), None, Decimal("120000000"), Decimal("50"), "USD")
    assert "No current investments are filed" in none and "new financing, share sales or lower spending" in none


def test_no_shortfall_no_statement():
    assert shortfall_statement(Decimal("101420384"), Decimal("178645000"), Decimal("120000000"), Decimal("96.76"), "USD") is None
    assert shortfall_statement(Decimal("0"), None, Decimal("120000000"), Decimal("96.76"), "USD") is None
    assert shortfall_statement(Decimal("-5"), None, Decimal("120000000"), Decimal("0"), "USD") is None
