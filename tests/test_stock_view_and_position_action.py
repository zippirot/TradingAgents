"""The report says two things separately: what the stock is worth, and what to do with the position.

Found 2026-11-12: one rating was carrying both. DOCN was valued 23 percent above its price and rated
Underweight because the position was 39 percent of the book; MSFT sat inside the Hold band and was rated
Underweight because of the other technology holdings. 81 percent of 90 runs were negative. A look-back the
same day found the valuation, not the rating, was what lined up with later returns. The user's decision:
split them.

- Stock view: Attractive, Fair or Unattractive. It is the manager's view of the stock alone. Code states
  its own reading of the accepted scenarios beside it (their yearly return against the required return,
  with the Hold band as "Fair") and asks once for a reason when the two differ.
- Position action: the five-way rating, now said to be what to do with the caller's position. It may point
  the other way from the stock view; when it does, the manager states the portfolio reason.

Boundaries: code never changes the view or the rating. A decision with no stock view (older saved runs, the
free-text fallback) is read exactly as before.
"""
from decimal import Decimal

from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents.scenario_decision import (
    render,
    retry_feedback,
    summarize,
    valuation_reading,
)

ABOVE = [_accept("base", 0.20), _accept("down", 0.05), _accept("up", 0.75)]      # returns well above the required return
BELOW = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]      # well below it


def _with(view, rating, stock_view=None, view_reason=None, reason=None):
    state = {**_state(view, rating=rating, reason=reason), "trade_date": "2026-11-10", "required_return": RETURN}
    state["unvalidated_outputs"]["portfolio_manager"]["structured"].update(stock_view=stock_view, stock_view_reason=view_reason)
    return state


def test_code_reads_the_scenarios_as_attractive_fair_or_unattractive():
    assert valuation_reading(Decimal("5"), Decimal(3)) == "Attractive"
    assert valuation_reading(Decimal("-5"), Decimal(3)) == "Unattractive"
    assert valuation_reading(Decimal("2.9"), Decimal(3)) == "Fair" and valuation_reading(Decimal("-3"), Decimal(3)) == "Fair"
    assert valuation_reading(None, Decimal(3)) is None
    assert summarize(_with(ABOVE, "Hold", "Attractive"), _three())["valuation_reading"] == "Attractive"
    assert summarize(_with(BELOW, "Hold", "Unattractive"), _three())["valuation_reading"] == "Unattractive"


def test_an_attractive_stock_can_carry_a_trim_when_the_portfolio_reason_is_stated():
    """The DOCN case: worth more than its price, and too large a position."""
    silent = _with(ABOVE, "Underweight", "Attractive")
    summary = summarize(silent, _three())
    assert (summary["view_check"], summary["consistency"], summary["contrary_basis"]) == ("consistent", "unexplained", "action_against_view")
    feedback = retry_feedback(silent, _three())
    assert "position" in feedback and "rating_basis_reason" in feedback and "Do not change the stock view" in feedback
    stated = _with(ABOVE, "Underweight", "Attractive", reason="The position is 39% of the book against a 5% standard weight.")
    summary = summarize(stated, _three())
    assert summary["consistency"] == "explained"
    card = "\n".join(render(summary))
    assert "Stock view: Attractive" in card and "Position action: Underweight" in card and "39% of the book" in card


def test_a_view_that_differs_from_the_scenarios_needs_its_own_reason():
    differs = _with(ABOVE, "Underweight", "Unattractive")
    summary = summarize(differs, _three())
    assert summary["view_check"] == "unexplained" and summary["consistency"] == "consistent"   # action agrees with the view
    feedback = retry_feedback(differs, _three())
    assert "stock_view_reason" in feedback and "Attractive" in feedback
    explained = summarize(_with(ABOVE, "Underweight", "Unattractive", view_reason="A dilutive share sale is authorised and in no case."), _three())
    assert explained["view_check"] == "explained"
    assert "Stock view: Unattractive" in "\n".join(render(explained)) and "code's reading of the accepted scenarios: Attractive" in "\n".join(render(explained))


def test_view_and_action_that_agree_owe_nothing_and_the_manager_is_told_about_both():
    agree = _with(BELOW, "Underweight", "Unattractive")
    summary = summarize(agree, _three())
    assert (summary["view_check"], summary["consistency"]) == ("consistent", "consistent")
    assert retry_feedback(agree, _three()) == ""
    from tradingagents.agents.scenario_decision import (
        priced_cases,
        render_cases_for_manager,
        with_value_today,
    )
    cases = with_value_today(priced_cases(_three()), {"trade_date": "2026-11-10", "required_return": RETURN})
    text = render_cases_for_manager(cases, RETURN)
    assert "stock_view" in text and "Attractive, Fair or Unattractive" in text and "position" in text


def test_a_decision_with_no_stock_view_is_read_as_before():
    old = summarize(_with(ABOVE, "Underweight"), _three())
    assert old["stock_view"] is None and old["view_check"] is None
    assert old["contrary_basis"] in ("direction", "return_gap", "near_required")
    assert "Stock view:" not in "\n".join(render(old))


def test_the_report_opens_with_the_stock_view_above_the_position_action():
    from tradingagents.agents.output_validation import _stock_view_line

    line = _stock_view_line({"scenario_decision": {"stock_view": "Attractive", "valuation_reading": "Attractive"}})
    assert line.startswith("**Stock view**: Attractive") and "position action" in line
    assert _stock_view_line({"scenario_decision": {"stock_view": None}}) == "" and _stock_view_line({}) == ""
