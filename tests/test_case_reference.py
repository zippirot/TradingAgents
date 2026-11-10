"""A priced case is placed against the company's own history on one basis (Build Q, Q2)."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.test_case_valuation import revenue_case
from tests.test_shared_valuation import state
from tradingagents.agents import case_reference
from tradingagents.agents.case_reference import (
    history_context,
    reference_position,
    render_history_context,
)
from tradingagents.agents.shared_valuation import prepare_shared_valuation, render_shared_valuation

HISTORY = {"status": "available", "statistics": {"low": "3", "median": "5", "high": "16", "count": 8},
           "current_position": {"status": "available", "multiple": "8.37"},
           "rows": [{"quarter_end": "2025-12-31", "multiple": "4.9", "revenue_unit": "USD"},
                    {"quarter_end": "2026-06-30", "multiple": "16", "revenue_unit": "USD"}]}


def _row(target, shares="100", revenue="1000", method="revenue_case"):
    return {"result": {"method": method, "target": target, "shares_outstanding": shares},
            "request": {"forecast": {"value": revenue}}}


def _with_history(history=HISTORY):
    return {"valuation_reference": {"own_history": history}}


@pytest.mark.parametrize("target,band", [("20", "below_low"), ("30", "low_to_median"), ("50", "low_to_median"),
                                         ("51", "median_to_high"), ("160", "median_to_high"), ("161", "above_high")])
def test_each_band_of_the_history_range(target, band):
    position = reference_position(_row(target), _with_history())
    assert position["status"] == "available" and position["band"] == band
    assert Decimal(position["implied_multiple"]) == Decimal(target) / 10
    assert case_reference.BANDS[band] in position["summary"]
    assert "8.37×" in position["summary"] and "not a point-in-time backtest" in position["summary"]
    assert "8-quarter" in position["summary"]


def test_same_per_share_value_gets_the_same_position_on_any_obligation_basis():
    equity = prepare_shared_valuation({**state([revenue_case("equity")]), **_with_history()})["rows"][0]
    on_debt = prepare_shared_valuation({**state([revenue_case("borrowings_only")]), **_with_history()})["rows"][0]
    for row in (equity, on_debt):
        implied = (Decimal(row["result"]["target"]) * Decimal(row["result"]["shares_outstanding"])
                   / Decimal(row["request"]["forecast"]["value"]))
        assert abs(Decimal(row["reference_position"]["implied_multiple"]) - implied) < Decimal("1e-20")
    assert equity["reference_position"]["basis"] == on_debt["reference_position"]["basis"] == "equity_value / forecast_revenue"


@pytest.mark.parametrize("inputs", [
    {}, {"valuation_reference": None}, _with_history({"status": "unavailable", "reason": "x"}),
    _with_history({**HISTORY, "statistics": {"low": "0", "median": "5", "high": "16", "count": 8}}),
    _with_history({**HISTORY, "statistics": "text"}),
])
def test_unavailable_history_gives_no_position(inputs):
    position = reference_position(_row("40"), inputs)
    assert position == {"status": "unavailable", "reason": "Own valuation history is unavailable for this run."}
    assert history_context(inputs) == []


@pytest.mark.parametrize("row", [_row(None), _row("40", shares="0"), _row("40", method="pe"), _row("x")])
def test_a_case_without_a_per_share_value_is_not_placed(row):
    assert reference_position(row, _with_history())["status"] == "unavailable"


def test_history_quarters_show_growth_and_margin_only_where_facts_exist(monkeypatch):
    facts = {("Revenue", "2025-12-31"): 400, ("Revenue", "2024-12-31"): 320, ("Gross Profit", "2025-12-31"): 240,
             ("Revenue", "2026-06-30"): 500}

    def ttm(_package, end, metric, _currency, *, positive=True):
        value = facts.get((metric, str(end)))
        return None if value is None else SimpleNamespace(value=Decimal(value))

    monkeypatch.setattr(case_reference, "_ttm_at", ttm)
    inputs = {**state([]), **_with_history()}
    quarters = history_context(inputs)
    assert quarters == [
        {"quarter_end": "2025-12-31", "multiple": "4.9", "revenue_growth_percent": "25.00", "gross_margin_percent": "60.0"},
        {"quarter_end": "2026-06-30", "multiple": "16", "revenue_growth_percent": None, "gross_margin_percent": None}]
    text = render_history_context(quarters)
    assert "2025-12-31 4.90× (trailing revenue growth 25.0%, gross margin 60.0%)" in text
    assert "2026-06-30 16.00× (trailing revenue growth unavailable, gross margin unavailable)" in text
    assert render_history_context([]) == ""


def test_scenario_table_shows_each_position_and_the_history_once():
    inputs = {**state([revenue_case()]), **_with_history()}
    record = prepare_shared_valuation(inputs)
    row = record["rows"][0]
    text = render_shared_valuation(record)
    assert row["reference_position"]["summary"] in text
    assert text.count("Own-history reference quarters") == (1 if record.get("reference_history") else 0)
    plain = prepare_shared_valuation(state([revenue_case()]))
    assert plain["rows"][0]["reference_position"]["status"] == "unavailable"
    assert "Implied equity value / forecast revenue" not in render_shared_valuation(plain)
