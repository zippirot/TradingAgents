"""Scenario weights start from equal; each departure is argued from the company's own evidence.

Diagnosed 2026-11-12 from 90 saved runs across eight kinds of company: the weights were the same shape
for every one (base about 0.50, downside about 0.30, upside about 0.18), the downside carrying about 1.7
times the upside's weight for a bank, a retailer and a software company alike. The user's decision: test
having the manager start from equal weights and justify each departure.

Boundary: nothing is forced. The manager is told the starting point, and weights that depart from equal
with no stated basis are sent back once for a basis. Near-equal weights owe nothing; a stated basis lets
any weights stand; code never changes a weight.
"""
from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents.scenario_decision import (
    priced_cases,
    render_cases_for_manager,
    retry_feedback,
    summarize,
    with_value_today,
)

HABIT = [_accept("base", 0.50), _accept("down", 0.32), _accept("up", 0.18)]
EQUAL = [_accept("base", 0.34), _accept("down", 0.33), _accept("up", 0.33)]


def _with(view, basis=None, rating="Underweight"):
    state = {**_state(view, rating=rating), "trade_date": "2026-11-10", "required_return": RETURN}
    state["unvalidated_outputs"]["portfolio_manager"]["structured"]["weight_basis"] = basis
    return state


def test_the_manager_is_told_to_start_from_equal_weights():
    cases = with_value_today(priced_cases(_three()), {"trade_date": "2026-11-10", "required_return": RETURN})
    text = render_cases_for_manager(cases, RETURN)
    assert "Start from equal weights" in text and "specific to this company" in text and "weight_basis" in text


def test_weights_that_depart_from_equal_with_no_basis_are_sent_back_once_for_one():
    summary = summarize(_with(HABIT), _three())
    assert summary["weights_unequal"] is True
    feedback = retry_feedback(_with(HABIT), _three())
    assert "equal weights" in feedback and "weight_basis" in feedback and "Resubmit" in feedback
    stated = _with(HABIT, "Signed capacity contracts cover the base case; the upside needs a second site not yet leased.")
    assert "weight_basis" not in retry_feedback(stated, _three())


def test_near_equal_weights_owe_nothing():
    assert summarize(_with(EQUAL), _three())["weights_unequal"] is False
    assert "weight_basis" not in retry_feedback(_with(EQUAL), _three())
    one = [_accept("base", 1.0)]
    assert not summarize(_with(one), _three()).get("weights_unequal")
