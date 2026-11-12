"""When the scenario weights decide the answer, the manager states the evidence for them.

Named as the biggest weakness across the loop's last batches (DOCN, MSFT, WMT): "with the Portfolio Manager's
45/45/10 weights the stock is 4.6% below the close; with equal weights the same cases put it 11.7% above. No
reason for the weights is published." The user's decision (2026-11-12): the report requires a stated basis.
The rule's boundary: it asks only when equal weights would put the accepted cases on the other side of the
close; where equal weights agree with the manager's, nothing is asked.
"""
from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents.scenario_decision import (
    render,
    render_cases_for_manager,
    retry_feedback,
    summarize,
)
from tradingagents.agents.schemas import RequiredHorizonPortfolioDecision

# Values today of the three cases sit near 69 / 38 / 93 against a 78.30 close: equal weights give about -14%.
TILTED_UP = [_accept("base", 0.20), _accept("down", 0.05), _accept("up", 0.75)]      # above the close; equal weights below
AGREEING = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]       # below the close, as equal weights are


def _with(view, basis=None, rating="Hold"):
    state = {**_state(view, rating=rating), "trade_date": "2026-11-10", "required_return": RETURN}
    state["unvalidated_outputs"]["portfolio_manager"]["structured"]["weight_basis"] = basis
    return state


def test_weights_that_decide_the_side_of_the_close_need_a_stated_basis_once():
    state = _with(TILTED_UP)
    summary = summarize(state, _three())
    assert summary["weights_decide"] is True and summary["weight_basis"] is None
    feedback = retry_feedback(state, _three())
    assert "weight_basis" in feedback and "equal weights" in feedback and "Resubmit" in feedback
    assert "no basis for them was stated" in "\n".join(render(summary))
    answered = _with(TILTED_UP, "Two signed capacity contracts cover the upside revenue; the downside needs both to lapse.")
    assert "weight_basis" not in retry_feedback(answered, _three())
    text = "\n".join(render(summarize(answered, _three())))
    assert "Why these weights (the Portfolio Manager's statement, unvalidated): Two signed capacity contracts" in text


def test_weights_that_agree_with_equal_weights_owe_nothing_and_a_given_basis_is_still_printed():
    state = _with(AGREEING, rating="Underweight")
    assert summarize(state, _three())["weights_decide"] is False
    assert "weight_basis" not in retry_feedback(state, _three())
    assert "no basis for them was stated" not in "\n".join(render(summarize(state, _three())))
    given = _with(AGREEING, "Guidance midpoint supports the base case.", rating="Underweight")
    assert "Why these weights" in "\n".join(render(summarize(given, _three())))
    # No required return: no value today, so nothing to compare and nothing asked.
    plain = {**_state(TILTED_UP, rating="Hold"), "trade_date": "2026-11-10"}
    assert summarize(plain, _three())["weights_decide"] is False


def test_the_manager_is_told_and_has_a_field_for_it():
    assert "weight_basis" in RequiredHorizonPortfolioDecision.model_fields
    from tradingagents.agents.scenario_decision import priced_cases, with_value_today
    cases = with_value_today(priced_cases(_three()), {"trade_date": "2026-11-10", "required_return": RETURN})
    assert "weight_basis" in render_cases_for_manager(cases, RETURN)
