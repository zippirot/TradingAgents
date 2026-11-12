"""A case period much shorter than a year is stated as what it is before any yearly figure.

Seen on all three WMT reports of the loop's cycles 3 and 4: the cases ended 81 days out (fiscal year end),
and a -19% gap to the close printed as "-61.3% a year" with nothing beside it.
"""
from decimal import Decimal

from tradingagents.agents.scenario_decision import render_today_basis
from tradingagents.agents.scenario_return import short_period

SUMMARY = {"unit": "USD/shares", "direction": "below", "direction_basis": "value_today", "session_date": "2026-11-11", "close": "125.67",
           "weighted_value": "101.80", "weighted_value_today": "99.70", "weighted_today_vs_close_percent": "-20.7",
           "range_today": {"low": "61.21", "high": "130.00"}, "range_today_vs_close_percent": {"low": "-51.3", "high": "3.4"},
           "weighted_annual_return": "-0.613", "return_gap_points": "-71.2", "required_return": {"rate": "0.0988"},
           "cases": [{"disposition": "accepted", "period_end": "2027-01-31"},
                     {"disposition": "accepted", "period_end": "2027-01-31"}]}


def test_a_period_under_half_a_year_gives_its_own_return_and_a_longer_one_gives_nothing():
    short = short_period("101.80", "125.67", "2026-11-11", "2027-01-31")
    assert short["days"] == 81 and Decimal(short["period_return"]).quantize(Decimal("0.001")) == Decimal("-0.190")
    assert short_period("101.80", "125.67", "2026-11-11", "2027-06-30") is None
    assert short_period("101.80", None, "2026-11-11", "2027-01-31") is None


def test_the_card_states_the_period_return_first_and_says_what_the_yearly_figure_is():
    text = render_today_basis(SUMMARY)[0]
    assert "returns -19.0% over the 81 days to 2027-01-31" in text
    assert "-61.3% a year" in text and "repeats that 81-day move for a full year" in text
    assert "against a required 9.88%" in text and "gap of -71.2 points" in text
    longer = {**SUMMARY, "cases": [{"disposition": "accepted", "period_end": "2027-12-31"}]}
    assert "returns -61.3% a year against a required 9.88%, a gap of -71.2 points" in render_today_basis(longer)[0]
