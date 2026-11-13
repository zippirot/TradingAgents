"""A Fair stock held at its standard weight is a Hold unless a portfolio reason is named.

Exposed by the split, 2026-11-12: in three MSFT runs the manager called the stock Fair, the holding was at
its standard weight, and the action was Underweight, with a "reason" that restated the valuation. Evaluators
marked it down each time (CF3).

Boundary: only this one case is touched (view Fair, holding at standard, action not Hold). The manager is
told the rule before deciding; code says what follows from the scale and never changes the action. Any other
combination, and a run with no sizing inputs, is read as before.
"""
from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents.scenario_decision import (
    priced_cases,
    render,
    render_cases_for_manager,
    summarize,
    with_value_today,
)

VIEW = [_accept("base", 0.34), _accept("down", 0.33), _accept("up", 0.33)]
QUOTE = {"status": "available", "close": "100", "currency": "USD", "session_date": "2026-11-09"}


def _with(rating, quantity, stock_view="Fair", reason=None):
    state = {**_state(VIEW, rating=rating, reason=reason), "trade_date": "2026-11-10", "required_return": RETURN,
             "company_of_interest": "MSFT", "price_observation": QUOTE,
             "portfolio_inputs": {"portfolio_value": 100000, "default_standard_weight": 0.05, "fingerprint": "f",
                                  "rating_weights": {"Hold": 1.0, "Underweight": 0.5},
                                  "positions": [{"ticker": "MSFT", "quantity": quantity}] if quantity else []}}
    state["unvalidated_outputs"]["portfolio_manager"]["structured"]["stock_view"] = stock_view
    return state


def test_a_trim_of_a_standard_size_holding_on_a_fair_stock_is_named_for_what_it_is():
    summary = summarize(_with("Underweight", 50), _three())                 # 50 x 100 = 5% = the standard weight
    assert summary["contrary_basis"] == "fair_at_standard" and summary["consistency"] == "unexplained"
    card = "\n".join(render(summary))
    assert "at its standard weight" in card and "the action that follows from the scale is Hold" in card
    held = summarize(_with("Hold", 50), _three())
    assert held["contrary_basis"] is None and "follows from the scale is Hold" not in "\n".join(render(held))


def test_other_combinations_are_not_touched():
    assert summarize(_with("Underweight", 400), _three())["contrary_basis"] == "action_against_view"   # 40% held: a size reason is asked for as before
    assert summarize(_with("Underweight", 50, stock_view="Unattractive"), _three())["contrary_basis"] != "fair_at_standard"
    no_inputs = _with("Underweight", 50)
    no_inputs.pop("portfolio_inputs")
    assert summarize(no_inputs, _three())["contrary_basis"] == "action_against_view"


def test_the_manager_is_told_the_rule_before_deciding():
    cases = with_value_today(priced_cases(_three()), {"trade_date": "2026-11-10", "required_return": RETURN})
    text = render_cases_for_manager(cases, RETURN)
    assert "Fair stock held at its standard weight is a Hold" in text and "named portfolio reason" in text
