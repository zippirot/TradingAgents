"""The return the cases are judged on includes the dividend.

Reassessment 2026-11-13: the yearly return set against the required return was the price change alone, so a
dividend payer was judged one to four points a year short of what a holder would receive.

Boundary: the last filed annual dividend per share, held flat, as a yield on the close, added to the gap against
the required return and so to code's reading of the stock. Case values, the weighted value and the price
comparison stay prices. No filed annual dividend means no change at all. Code never changes a rating.
"""
from decimal import Decimal

from tests.test_required_return import RETURN, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents.scenario_decision import render, summarize
from tradingagents.agents.scenario_return import dividend_yield

VIEW = [_accept("base", 0.34), _accept("down", 0.33), _accept("up", 0.33)]


def _fact(value, start="2025-01-01", end="2025-12-31", metric="Dividends Declared Per Share"):
    return {"metric": metric, "value": value, "unit": "USD/shares", "period_start": start, "period_end": end}


def _run(facts):
    state = {**_state(VIEW), "trade_date": "2026-11-10", "required_return": RETURN}
    if facts is not None:
        state["financial_evidence"] = {"facts": facts}
    return summarize(state, _three())


def test_the_latest_filed_annual_dividend_is_a_yield_on_the_close():
    facts = [_fact("1.00", "2024-01-01", "2024-12-31"), _fact("1.566"), _fact("0.40", "2026-01-01", "2026-03-31")]
    found = dividend_yield(facts, "78.30")
    assert found["per_share"] == "1.566" and found["period_end"] == "2025-12-31" and Decimal(found["yield_percent"]) == 2
    assert dividend_yield([_fact("0")], "78.30") is None and dividend_yield([], "78.30") is None
    assert dividend_yield([_fact("1.5"), _fact("1.6")], "78.30") is None        # two values for one year: say nothing


def test_the_gap_against_the_required_return_gains_the_yield_and_the_card_says_so():
    without, paid = _run(None), _run([_fact("1.566")])
    assert abs(Decimal(paid["return_gap_points"]) - Decimal(without["return_gap_points"]) - 2) < Decimal("0.0000001")
    assert paid["return_gap_before_dividend"] == without["return_gap_points"] and paid["weighted_value"] == without["weighted_value"]
    card = "\n".join(render(paid))
    assert "dividend of 1.566 a share filed for the year to 2025-12-31 (2.0% of the close)" in card
    assert "dividend" not in "\n".join(render(without)) and "return_gap_before_dividend" not in without
