"""A rating below Hold never opens or enlarges a position.

Seen across the loop's cycle-2 reports: Underweight on a stock that is not held printed a target of half
the standard weight, an opening purchase under a negative view. The user's rule (2026-11-12): for a stock
not held, Underweight and Sell both mean do not buy. The same holds for a holding smaller than the
Underweight weight: the rating does not add to it.
"""
from decimal import Decimal

from tradingagents.agents.case_reference import action_reading
from tradingagents.portfolio import PortfolioContext, render_sizing, sizing

BOOK = {"portfolio_value": 100000, "currency": "USD", "default_standard_weight": 0.05, "loss_budget": 0.01,
        "show_amounts": False,
        "rating_weights": {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0.0}}
QUOTE = {"close": "100", "session_date": "2026-11-11", "currency": "USD"}


def _sized(quantity, rating=None, levels=()):
    positions = [{"ticker": "WMT", "quantity": quantity}] if quantity else []
    return sizing({**BOOK, "positions": positions}, "WMT", QUOTE, rating=rating, levels=levels)


def _row(result, rating):
    return next(row for row in result["targets"] if row["rating"] == rating)


def test_underweight_on_a_stock_not_held_is_no_purchase():
    result = _sized(0, "Underweight", levels=("90",))
    row = result["final"]
    assert (Decimal(row["target_weight"]), row["units_change"], row["no_addition"]) == (Decimal(0), "0", True)
    assert Decimal(row["scale_weight"]) == Decimal("0.025")
    assert "target" not in result["loss"]                       # nothing would be bought, so nothing is tested
    line = next(text for text in render_sizing(result, final=True) if "final rating" in text)
    assert "no purchase" in line and "nothing is held" in line and "units more" not in line
    before = "\n".join(render_sizing(_sized(0)))
    assert "Underweight no purchase" in before and "Hold 5.0% of the portfolio (about 50 units more" in before


def test_underweight_does_not_add_to_a_holding_below_its_weight_and_still_cuts_a_larger_one():
    small = _row(_sized(10), "Underweight")                     # 1% held, Underweight weight 2.5%
    assert (Decimal(small["target_weight"]), small["units_change"], small["no_addition"]) == (Decimal("0.01"), "0", True)
    assert "you hold less than its 2.5% weight" in "\n".join(render_sizing(_sized(10)))
    large = _row(_sized(60), "Underweight")
    assert (Decimal(large["target_weight"]), large["units_change"]) == (Decimal("0.025"), "-35")
    assert "no_addition" not in large
    assert _row(_sized(60), "Sell")["units_change"] == "-60" and "no_addition" not in _row(_sized(0), "Sell")


def test_positive_ratings_and_short_positions_are_unchanged():
    assert _row(_sized(0), "Overweight")["units_change"] == "62" and _row(_sized(0), "Hold")["units_change"] == "50"
    assert _row(_sized(-10), "Underweight")["units_change"] == "35"


def test_the_reading_of_the_traders_sell_says_no_purchase_and_the_agents_are_told_the_rule():
    line = action_reading("Sell", "Underweight", _sized(0))
    assert not line.startswith("Reduce") and "nothing is held" in line and "no purchase" in line
    text = PortfolioContext.model_validate({"positions": [{"ticker": "MSFT", "quantity": 10}]}).render("WMT")
    assert "No current position in WMT" in text and "Underweight and Sell both mean do not buy" in text
    assert "do not buy" not in PortfolioContext.model_validate({"positions": [{"ticker": "WMT", "quantity": 10}]}).render("WMT")


def test_a_sell_with_nothing_held_reads_as_no_purchase_under_any_negative_rating():
    from tradingagents.agents.trader.trader import _reading
    line = action_reading("Sell", "Sell", _sized(0))
    assert "is not a sale here" in line and "no purchase" in line
    assert "cannot say this" in _reading("**Action**: Sell", "**Recommendation**: Sell", _sized(0))
    assert action_reading("Sell", "Sell", _sized(60)) is None and action_reading("Sell", "Sell") is None
    assert action_reading("Hold", "Sell", _sized(0)) is None
