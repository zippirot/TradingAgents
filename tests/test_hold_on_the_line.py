"""When the accepted scenarios put a stock at about its price, the published rating is Hold (on the line).

Diagnosed 2026-11-12: with the numbers carried forward and identical run to run (MSFT valued 1.4% above its
close), the rating still came out Hold, then Underweight twice. The user's decision: when a small shift in
the weights would move the valuation across the price, code prints Hold, shows the manager's own rating as
the lean with what would tip it, and the position is left as it is.

Boundary: "on the line" is decided from the report's own weight arithmetic, never a fixed percentage of the
price: equal weights put the cases on the other side of the close, or the highest case's weight needs to
move by no more than ON_THE_LINE_SHIFT (10 points, the spread measured between runs). Off the line nothing
changes. The manager's weights, cases and text are never altered; only the published rating is.
"""
from decimal import Decimal

from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents.scenario_decision import (
    ON_THE_LINE_SHIFT,
    line_feedback,
    on_the_line,
    render,
    settle_on_the_line,
    summarize,
)
from tradingagents.portfolio import render_sizing, sizing, sizing_from_state

ON_LINE = [_accept("base", 0.20), _accept("down", 0.05), _accept("up", 0.75)]       # above the close; equal weights below
OFF_LINE = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]      # 19% below; no small shift crosses


def _with(view, rating, lean=None):
    state = {**_state(view, rating=rating), "trade_date": "2026-11-10", "required_return": RETURN}
    structured = state["unvalidated_outputs"]["portfolio_manager"]["structured"]
    structured.update(weight_basis="Stated.", rating_lean=lean)
    return state


def test_the_line_is_found_from_the_weights_not_from_a_percentage_of_the_price():
    assert summarize(_with(ON_LINE, "Overweight"), _three())["on_the_line"]["reason"] == "equal_weights"
    assert summarize(_with(OFF_LINE, "Underweight"), _three())["on_the_line"] is None
    base = {"direction_basis": "value_today", "weights_decide": False, "weighted_today_vs_close_percent": "4.5",
            "sturdiness": {"break_even": "available", "break_even_weight": "0.21", "highest": {"weight": "0.15", "role": "upside"},
                           "equal_weight_vs_close_percent": "2.2"}}
    found = on_the_line(base)
    assert found["reason"] == "weight_shift" and Decimal(found["shift"]) == Decimal("0.06") and Decimal("0.06") <= ON_THE_LINE_SHIFT
    far = {**base, "sturdiness": {**base["sturdiness"], "break_even_weight": "0.40"}}
    assert on_the_line(far) is None
    assert on_the_line({**base, "sturdiness": {**base["sturdiness"], "break_even": "unreachable"}}) is None
    assert on_the_line({**base, "direction_basis": "period_end"}) is None and on_the_line({"sturdiness": None}) is None


def test_on_the_line_the_published_rating_is_hold_and_the_managers_rating_is_the_lean():
    line = {"reason": "weight_shift", "shift": "0.06"}
    assert settle_on_the_line("Underweight", None, line) == ("Hold", "Underweight")
    assert settle_on_the_line("Hold", "Overweight", line) == ("Hold", "Overweight")     # the manager complied and said its lean
    assert settle_on_the_line("Hold", None, line) == ("Hold", None)
    assert settle_on_the_line("Hold", "Hold", line) == ("Hold", None)
    assert settle_on_the_line("Underweight", "Overweight", None) == ("Underweight", None)   # off the line: untouched


def test_the_manager_is_told_once_and_the_card_says_what_was_done():
    summary = summarize(_with(ON_LINE, "Overweight"), _three())
    text = line_feedback(summary, "Overweight")
    assert "on the line" in text and "rating_lean" in text and "Hold" in text and "Resubmit" in text
    assert " or revise" not in text                                         # an instruction, not a choice
    assert line_feedback(summary, "Hold") == "" and line_feedback({"on_the_line": None}, "Overweight") == ""
    card = "\n".join(render(summarize(_with(ON_LINE, "Hold", lean="Overweight"), _three())))
    assert "Hold (on the line)" in card and "leans Overweight" in card and "set by code" in card
    assert "equal weights" in card and "**" not in next(text for text in card.splitlines() if "on the line" in text)
    from tradingagents.agents.output_validation import _line_note
    note = _line_note({"scenario_decision": {"on_the_line": {"reason": "weight_shift"}, "rating_lean": "Underweight"}})
    assert note.startswith("**Rating note**: Hold (on the line), set by code") and "leans Underweight" in note
    assert _line_note({"scenario_decision": {"on_the_line": None}}) == "" and _line_note({}) == ""
    plain = "\n".join(render(summarize(_with(OFF_LINE, "Underweight"), _three())))
    assert "on the line" not in plain


BOOK = {"portfolio_value": 100000, "currency": "USD", "default_standard_weight": 0.05, "loss_budget": 0.01,
        "show_amounts": False, "fingerprint": "abc",
        "rating_weights": {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0.0}}
QUOTE = {"close": "100", "session_date": "2026-11-11", "currency": "USD"}


def test_on_the_line_the_holding_is_left_as_it_is():
    book = {**BOOK, "positions": [{"ticker": "MSFT", "quantity": 20}]}          # 2% held, standard 5%
    usual = sizing(book, "MSFT", QUOTE, rating="Hold")
    assert usual["final"]["units_change"] == "30"                                # an ordinary Hold goes to standard
    kept = sizing(book, "MSFT", QUOTE, rating="Hold", in_place=True)
    assert (kept["final"]["units_change"], Decimal(kept["final"]["target_weight"])) == ("0", Decimal("0.02"))
    line = next(text for text in render_sizing(kept, final=True) if "final rating" in text)
    assert "on the line" in line and "left as it is" in line
    state = {"portfolio_inputs": book, "company_of_interest": "MSFT", "price_observation": QUOTE, "final_rating": "Hold",
             "decision_context": {"scenario_decision": {"on_the_line": {"reason": "weight_shift", "shift": "0.06"}}}}
    assert sizing_from_state(state, final=True)["final"]["units_change"] == "0"
    assert sizing_from_state({**state, "decision_context": {"scenario_decision": {"on_the_line": None}}},
                             final=True)["final"]["units_change"] == "30"


def test_settling_keeps_the_managers_private_fields_and_the_decision_text_names_the_lean():
    from tradingagents.agents.schemas import (
        PortfolioRating,
        RequiredHorizonPortfolioDecision,
        render_pm_decision,
    )

    decision = RequiredHorizonPortfolioDecision(rating="Underweight", executive_summary="s", investment_thesis="t",
                                                time_horizon="6 months")
    decision._unvalidated_thesis_candidate = {"rationale": "kept"}
    settled = decision.model_copy(update={"rating": PortfolioRating("Hold"), "rating_lean": "Underweight"})
    assert settled._unvalidated_thesis_candidate == {"rationale": "kept"} and settled.rating.value == "Hold"
    text = render_pm_decision(settled)
    assert text.startswith("**Rating**: Hold") and "Hold (on the line), set by code; the Portfolio Manager leans Underweight" in text
    assert "Rating note" not in render_pm_decision(decision)
