"""The size the final rating calls for is tested against the report's own lowest accepted case.

Seen in the loop's cycle-2 MSFT and CAT reports: the decision card said the downside case allows at most
4.8% of the portfolio per 1% of accepted loss, the sizing block put the Overweight target at 6.2% under a
1% loss budget, and nothing in the report joined the two. Code now states the result and the manager is
asked once to answer it.
"""
from decimal import Decimal

from tradingagents.portfolio import downside_test, render_sizing, sizing, sizing_from_state

BOOK = {"portfolio_value": 100000, "currency": "USD", "default_standard_weight": 0.05, "loss_budget": 0.01,
        "show_amounts": False, "fingerprint": "abc",
        "rating_weights": {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0.0}}
QUOTE = {"close": "500", "session_date": "2026-11-11", "currency": "USD"}
RULE = {"status": "available", "role": "downside", "name": "Slower cloud", "value_today": "395", "fall": "0.21",
        "weight_per_point_of_loss": "4.7619", "case_id": "c", "version": 1}


def _sized(quantity, rating):
    return sizing({**BOOK, "positions": [{"ticker": "MSFT", "quantity": quantity}]}, "MSFT", QUOTE, rating=rating)


def test_a_size_that_loses_more_than_the_budget_in_the_lowest_accepted_case_is_said_so():
    test = downside_test(_sized(10, "Overweight"), RULE)
    assert (Decimal(test["weight"]), Decimal(test["loss"]), test["inside"]) == (Decimal("0.0625"), Decimal("0.013125"), False)
    assert f"{Decimal(test['ceiling']) * 100:.1f}" == "4.8"
    line = next(text for text in render_sizing({**_sized(10, "Overweight"), "downside": test}, final=True)
                if "lowest accepted case" in text)
    assert "21.0% below the close" in line and "would lose 1.31%" in line and "OUTSIDE" in line and "at most 4.8%" in line


def test_a_size_inside_the_budget_is_said_inside_and_nothing_is_tested_without_a_size_or_a_limiting_case():
    inside = downside_test(_sized(10, "Underweight"), RULE)          # 2.5% x 21% = 0.525%
    assert inside["inside"] is True
    assert "inside" in "\n".join(render_sizing({**_sized(10, "Underweight"), "downside": inside}, final=True))
    assert downside_test(_sized(10, "Sell"), RULE) is None           # nothing would be held
    assert downside_test(_sized(0, "Underweight"), RULE) is None     # no purchase
    assert downside_test(_sized(10, "Overweight"), {**RULE, "status": "not_limiting"}) is None
    assert downside_test(_sized(10, "Overweight"), None) is None
    assert downside_test({"status": "not_configured"}, RULE) is None
    no_budget = sizing({**BOOK, "loss_budget": None, "positions": []}, "MSFT", QUOTE, rating="Overweight")
    assert downside_test(no_budget, RULE) is None


def test_the_report_reads_the_rule_from_the_decision_card():
    state = {"portfolio_inputs": {**BOOK, "positions": [{"ticker": "MSFT", "quantity": 10}]},
             "company_of_interest": "MSFT", "price_observation": QUOTE, "final_rating": "Overweight",
             "decision_context": {"scenario_decision": {"sizing_rule": RULE}}}
    assert sizing_from_state(state, final=True)["downside"]["inside"] is False
    assert "downside" not in sizing_from_state(state)                 # before the decision nothing is accepted yet


def test_the_size_test_is_printed_and_never_sent_back_to_the_manager():
    """Asked to answer it, the manager changed the rating to fit the loss budget (three MSFT runs, 2026-11-12)."""
    from tests.test_required_return import RETURN, _three
    from tests.test_scenario_decision import _accept, _state
    from tradingagents.agents import scenario_decision

    assert not hasattr(scenario_decision, "size_feedback")
    book = {**BOOK, "positions": [{"ticker": "MSFT", "quantity": 100}]}
    state = {**_state([_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)], rating="Underweight"),
             "trade_date": "2026-11-10", "required_return": RETURN, "portfolio_inputs": book,
             "company_of_interest": "MSFT"}
    feedback = scenario_decision.retry_feedback(state, _three())
    assert "loss budget" not in feedback and "of the portfolio" not in feedback
    line = next(text for text in render_sizing({**_sized(10, "Overweight"), "downside": downside_test(_sized(10, "Overweight"), RULE)}, final=True)
                if "lowest accepted case" in text)
    assert "The rating is the view of the stock and is not changed by this" in line
