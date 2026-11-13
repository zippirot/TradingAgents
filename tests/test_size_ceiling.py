"""The caller's loss budget and sector limit are ceilings on the size the rating calls for.

User decision 2026-11-13 (map 2b-5, target C): the rating still sets the size. If that size would lose more
than the loss budget in the report's lowest accepted case, or take the sector over the caller's limit, the
size is cut to what fits and the block says which limit did it.

Boundary: the size only. The rating and the stock view are never changed, a limit never raises a size, and
with no loss budget, no accepted case below the close and no sector limit nothing changes.
"""
from decimal import Decimal

from tradingagents.portfolio import downside_test, limit_size, render_sizing, sizing

QUOTE = {"status": "available", "close": "100", "currency": "USD", "session_date": "2026-11-12"}
RULE = {"status": "available", "fall": "0.40", "role": "downside", "name": "Downside"}


def _sized(rating="Hold", quantity=0, budget=0.01, related=None, standard=0.05):
    inputs = {"portfolio_value": 100000, "default_standard_weight": standard, "fingerprint": "f", "loss_budget": budget,
              "rating_weights": {"Buy": 2.0, "Overweight": 1.5, "Hold": 1.0, "Underweight": 0.5, "Sell": 0.0},
              "positions": [{"ticker": "MSFT", "quantity": quantity}] if quantity else []}
    result = sizing(inputs, "MSFT", QUOTE, rating=rating, related=related)
    test = downside_test(result, RULE)
    return {**result, "downside": test} if test else result


def test_the_loss_budget_cuts_a_size_that_would_lose_more_than_it_in_the_lowest_case():
    # Overweight is 7.5%; a 40% fall on that loses 3%, over the 1% budget; 1% / 40% = 2.5% is what fits.
    result = limit_size(_sized("Overweight", quantity=50))
    assert result["limited"]["bound_by"] == "loss_budget" and Decimal(result["limited"]["weight"]) == Decimal("0.025")
    assert Decimal(result["limited"]["rating_weight"]) == Decimal("0.075") and Decimal(result["limited"]["units_change"]) == -25
    text = "\n".join(render_sizing(result, final=True))
    assert "Size after your limits: 2.5% of the portfolio" in text and "your loss budget" in text
    assert "about 25 units fewer than you hold" in text and "For the final rating Overweight" in text


def test_the_sector_limit_cuts_a_size_that_would_take_the_group_over_it():
    related = {"status": "available", "sector": "Technology", "others_weight": "0.27", "count": 2, "left_out": [], "limit": 0.30}
    result = limit_size(_sized("Overweight", quantity=50, budget=0.10, related=related))
    assert result["limited"]["bound_by"] == "sector_limit" and Decimal(result["limited"]["weight"]) == Decimal("0.03")
    assert "your sector limit" in "\n".join(render_sizing(result, final=True))


def test_a_limit_never_raises_a_size_and_nothing_changes_without_one():
    inside = limit_size(_sized("Underweight", quantity=50, budget=0.05))      # 2.5% x 40% = 1%, inside 5%
    assert "limited" not in inside and "Size after your limits" not in "\n".join(render_sizing(inside, final=True))
    assert "limited" not in limit_size(_sized("Overweight", quantity=50, budget=None))
    assert "limited" not in limit_size({"status": "not_configured"})
    full = {"status": "available", "sector": "Technology", "others_weight": "0.40", "count": 2, "left_out": [], "limit": 0.30}
    over = limit_size(_sized("Hold", quantity=50, budget=0.10, related=full))  # the group is over the limit without it
    assert Decimal(over["limited"]["weight"]) == 0 and over["limited"]["bound_by"] == "sector_limit"
