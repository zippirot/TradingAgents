"""Conditional Hold: a result close to the required return reads as a Hold with its conditions.

Agreed with the user 2026-11-12. Across 90 saved runs anything short of the required return was rated
Underweight, however narrowly, and 81 percent of ratings were negative. "Close" is defined as the accepted
scenarios' yearly return within a band of the required return: 3 points unless the caller's portfolio file
sets another figure.

Boundaries, each learned the hard way the same day:
- The manager chooses the rating. Code never changes one (a code-set Hold overrode an Underweight chain on
  the user's real DOCN run).
- Inside the band a rating other than Hold stands when the manager gives a reason other than this valuation.
- Outside the band nothing changes. The user's DOCN run sat 4.3 points short: outside a 3-point band.
- A position over the loss budget is still reported; a Conditional Hold never hides it.
"""
from decimal import Decimal

from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents.scenario_decision import (
    DEFAULT_HOLD_BAND,
    hold_band,
    render,
    retry_feedback,
    summarize,
)
from tradingagents.portfolio import PortfolioContext

NEAR = [_accept("base", 0.40), _accept("down", 0.15), _accept("up", 0.45)]
FAR = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]


def _with(view, rating, reason=None, band=None):
    state = {**_state(view, rating=rating, reason=reason), "trade_date": "2026-11-10", "required_return": RETURN}
    if band is not None:
        state["portfolio_inputs"] = {"hold_band_points": band}
    return state


def _gap(view):
    return abs(Decimal(summarize(_with(view, "Hold"), _three())["return_gap_points"]))


def test_the_band_is_three_points_unless_the_portfolio_file_sets_another():
    assert Decimal(3) == DEFAULT_HOLD_BAND
    assert hold_band({}) == (Decimal(3), "app setting")
    assert hold_band({"portfolio_inputs": {"hold_band_points": 5}}) == (Decimal(5), "portfolio file")
    own = PortfolioContext.model_validate({"positions": [], "hold_band_points": 5})
    assert own.inputs()["hold_band_points"] == 5
    assert own.fingerprint() != PortfolioContext.model_validate({"positions": []}).fingerprint()


def test_a_hold_inside_the_band_is_printed_as_a_conditional_hold():
    band = _gap(NEAR) + 1                                            # a band this fixture's result sits inside
    summary = summarize(_with(NEAR, "Hold", band=float(band)), _three())
    assert summary["hold_band"]["near"] is True and summary["conditional_hold"] is True
    assert summary["consistency"] == "consistent"
    card = "\n".join(render(summary))
    assert "Conditional Hold" in card and "a year against a required" in card and "set in your portfolio file" in card
    assert "loss budget" in card                                      # says the sizing block still reports a breach


def test_inside_the_band_another_rating_needs_a_reason_other_than_the_valuation_and_is_never_changed():
    band = float(_gap(NEAR) + 1)
    for rating in ("Underweight", "Overweight"):
        state = _with(NEAR, rating, band=band)
        summary = summarize(state, _three())
        assert summary["consistency"] == "unexplained" and summary["conditional_hold"] is False
        feedback = retry_feedback(state, _three())
        assert "Conditional Hold" in feedback and "other than this valuation" in feedback
    reasoned = _with(NEAR, "Underweight", reason="A dilutive share sale is authorised and not in any case.", band=band)
    summary = summarize(reasoned, _three())
    assert summary["consistency"] == "explained" and reasoned["final_rating"] == "Underweight"


def test_outside_the_band_nothing_changes():
    band = float(max(_gap(FAR) - 1, Decimal("0.1")))                  # a band this result sits outside
    summary = summarize(_with(FAR, "Underweight", band=band), _three())
    assert summary["hold_band"]["near"] is False and summary["conditional_hold"] is False
    assert summary["consistency"] == "consistent"
    hold = summarize(_with(FAR, "Hold", band=band), _three())
    assert hold["conditional_hold"] is False and "Conditional Hold" not in "\n".join(render(hold))
    plain = summarize({**_state(NEAR, rating="Hold"), "trade_date": "2026-11-10"}, _three())   # no required return
    assert plain.get("hold_band") is None and plain["conditional_hold"] is False


def test_a_band_of_fifteen_points_is_accepted():
    """The user chose 15 on 2026-11-13 after the outcome check showed views inside about 15 to 20 points of the
    required return did no better or worse than the market; the file refused anything over 10."""
    assert PortfolioContext.model_validate({"positions": [], "hold_band_points": 15}).hold_band_points == 15
    assert hold_band({"portfolio_inputs": {"hold_band_points": 15}}) == (Decimal(15), "portfolio file")
