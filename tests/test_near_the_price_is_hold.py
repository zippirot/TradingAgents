"""When the accepted cases put the stock within 10 percent of its price, they support Hold.

Diagnosed 2026-11-12 from thirteen saved MSFT runs on one close: the weighted value today was within 5.3%
of the close every time, and the rating was Overweight, Underweight or Hold according to whether the
modelled yearly return fell above or below the required return, a difference smaller than the spread
between runs. The code already calls that band "near the close". Inside it a rating other than Hold now
owes a stated reason, on either side. Boundary: outside the band nothing changes, and a stated reason
still lets any rating stand.

A Hold on a stock that is not held opens no position: there is nothing to hold. The portfolio review
already reads it as "No action".
"""
from decimal import Decimal

from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents.scenario_decision import (
    render_cases_for_manager,
    retry_feedback,
    summarize,
)
from tradingagents.portfolio import PortfolioContext, render_sizing, sizing

NEAR = [_accept("base", 0.40), _accept("down", 0.15), _accept("up", 0.45)]      # weighted value today a little under the close
BELOW = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]     # about 19% below the close


def _with(view, rating, reason=None):
    state = {**_state(view, rating=rating, reason=reason), "trade_date": "2026-11-10", "required_return": RETURN}
    state["unvalidated_outputs"]["portfolio_manager"]["structured"]["weight_basis"] = "Stated."
    return state


def test_inside_the_band_only_hold_stands_without_a_reason_on_either_side():
    assert summarize(_with(NEAR, "Hold"), _three())["direction"] == "near"
    assert summarize(_with(NEAR, "Hold"), _three())["consistency"] == "consistent"
    assert retry_feedback(_with(NEAR, "Hold"), _three()) == ""
    for rating in ("Overweight", "Underweight", "Buy", "Sell"):
        summary = summarize(_with(NEAR, rating), _three())
        assert summary["consistency"] == "unexplained" and summary["contrary_basis"] in ("near", "return_gap")
        feedback = retry_feedback(_with(NEAR, rating), _three())
        assert "within 10 percent" in feedback and "Hold" in feedback and "Resubmit" in feedback
    reasoned = _with(NEAR, "Overweight", reason="A signed contract not in any case adds capacity revenue from March.")
    assert summarize(reasoned, _three())["consistency"] == "explained"


def test_outside_the_band_nothing_changes():
    assert summarize(_with(BELOW, "Underweight"), _three())["consistency"] == "consistent"
    assert summarize(_with(BELOW, "Hold"), _three())["consistency"] == "consistent"
    assert summarize(_with(BELOW, "Overweight"), _three())["contrary_basis"] == "direction"


def test_the_manager_is_told_the_rule_before_deciding():
    from tradingagents.agents.scenario_decision import priced_cases, with_value_today
    cases = with_value_today(priced_cases(_three()), {"trade_date": "2026-11-10", "required_return": RETURN})
    text = render_cases_for_manager(cases, RETURN)
    assert "within 10 percent of the close" in text and "Hold" in text


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
