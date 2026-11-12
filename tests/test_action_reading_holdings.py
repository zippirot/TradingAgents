"""The code's reading of the Trader's Buy/Hold/Sell agrees with the holding in the sizing block.

Seen in every loop baseline report: "Reduce (the Trader's Sell under Underweight)" printed for a stock that
is not held, while the sizing block on the same page put the Underweight target above the holding.
"""
from tradingagents.agents.case_reference import action_reading
from tradingagents.agents.trader.trader import _reading
from tradingagents.portfolio import sizing

BOOK = {"portfolio_value": 100000, "currency": "USD", "default_standard_weight": 0.05, "show_amounts": False,
        "rating_weights": {"Buy": 1.5, "Overweight": 1.25, "Hold": 1.0, "Underweight": 0.5, "Sell": 0.0}}
QUOTE = {"close": "100", "session_date": "2026-11-11", "currency": "USD"}


def _sized(quantity):
    return sizing({**BOOK, "positions": [{"ticker": "WMT", "quantity": quantity}] if quantity else []}, "WMT", QUOTE)


def test_a_sell_under_underweight_is_not_called_a_reduction_when_the_holding_is_below_the_target():
    line = action_reading("Sell", "Underweight", _sized(0))
    assert not line.startswith("Reduce") and "nothing is held" in line
    assert "no purchase" in line and "units above" not in line
    short = action_reading("Sell", "Underweight", _sized(10))
    assert "nothing is held" not in short and "less is held than the rating's weight" in short


def test_a_reading_that_agrees_with_the_holding_is_unchanged_and_no_sizing_reads_as_before():
    plain = "Reduce (the Trader's Sell under the research rating Underweight)"
    assert action_reading("Sell", "Underweight", _sized(60)) == plain          # 60 held, target 25
    assert action_reading("Sell", "Underweight") == plain
    assert action_reading("Sell", "Underweight", {"status": "not_configured"}) == plain
    assert action_reading("Buy", "Overweight", _sized(0)).startswith("Add ")
    over = action_reading("Buy", "Overweight", _sized(100))                    # 100 held, target 63
    assert not over.startswith("Add") and "units below the current holding" in over


def test_the_line_under_the_traders_proposal_points_to_the_sizing_block_instead_of_claiming_a_direction():
    text, plan = "**Action**: Sell", "**Rating**: Underweight"
    line = _reading(text, plan, _sized(0))
    assert "Reduce" not in line and "it is not an exit" not in line and "Position and sizing block" in line
    assert "Reduce" in _reading(text, plan, _sized(60)) and "Reduce" in _reading(text, plan)
