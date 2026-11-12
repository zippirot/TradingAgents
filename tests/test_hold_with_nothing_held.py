"""A Hold on a stock that is not held opens no position: there is nothing to hold.

The portfolio review already reads it as "No action". Only Buy or Overweight opens a position.

Tried and removed the same day (2026-11-12): asking the manager for a reason whenever its rating was not Hold
while its accepted cases sat within 10 percent of the close. Three paid MSFT runs on one close still gave
Overweight, Hold and Underweight; the manager stated a reason and kept its rating. A soft ask does not steady
the rating. Whether code should set the rating inside that band is the user's decision.
"""
from decimal import Decimal

from tradingagents.portfolio import PortfolioContext, render_sizing, sizing

BOOK = {"portfolio_value": 100000, "currency": "USD", "default_standard_weight": 0.05, "loss_budget": 0.01,
        "show_amounts": False,
        "rating_weights": {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0.0}}
QUOTE = {"close": "100", "session_date": "2026-11-11", "currency": "USD"}


def test_a_hold_with_nothing_held_opens_no_position_and_a_held_hold_is_unchanged():
    flat = sizing({**BOOK, "positions": []}, "WMT", QUOTE, rating="Hold")
    row = flat["final"]
    assert (Decimal(row["target_weight"]), row["units_change"], row["no_addition"]) == (Decimal(0), "0", True)
    line = next(text for text in render_sizing(flat, final=True) if "final rating" in text)
    assert "no purchase" in line and "nothing is held" in line
    held = sizing({**BOOK, "positions": [{"ticker": "WMT", "quantity": 10}]}, "WMT", QUOTE, rating="Hold")
    assert held["final"]["units_change"] == "40" and "no_addition" not in held["final"]       # as before
    assert sizing({**BOOK, "positions": []}, "WMT", QUOTE, rating="Overweight")["final"]["units_change"] == "62"
    text = PortfolioContext.model_validate({"positions": []}).render("WMT")
    assert "Hold, Underweight and Sell all mean do not buy" in text and "Buy or Overweight" in text
