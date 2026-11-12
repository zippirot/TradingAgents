"""An earnings case states how its forecast sits against the filed earnings and the vendor range.

Seen in the loop's cycle-2 MSFT report: the base case forecast 21.00 a share, above the highest vendor
estimate printed in the same report (20.63), and no agent examined it. Code now prints the comparison
beside each earnings case, so the debate and the managers read it.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from tradingagents.agents.earnings_anchor import earnings_anchor


def _fact(fact_id, start, end, value, metric="Diluted EPS"):
    return SimpleNamespace(fact_id=fact_id, metric=metric, period_start=date.fromisoformat(start),
                           period_end=date.fromisoformat(end), value=Decimal(value))


FACTS = [_fact("fy26", "2025-07-01", "2026-06-30", "17.95"), _fact("q1-26", "2025-07-01", "2025-09-30", "3.72"),
         _fact("h1-26", "2025-07-01", "2025-12-31", "8.87"), _fact("q1-27", "2026-07-01", "2026-09-30", "4.92"),
         _fact("rev", "2026-07-01", "2026-09-30", "77000000000", metric="Revenue")]
REQUEST = {"method": "earnings_case", "eps_fact_id": "fy26",
           "forecast": {"value": "21.00", "period_start": "2026-07-01", "period_end": "2027-06-30"}}
VENDOR = [{"metric": "revenue", "period_code": "0y", "low": "1", "high": "2", "average": "1.5"},
          {"metric": "eps", "period_code": "0y", "analyst_count": 32, "average": "20.01357", "low": "19.55", "high": "20.63"}]


def test_the_forecast_is_set_against_the_filed_year_the_filed_quarters_and_the_vendor_range():
    anchor = earnings_anchor(REQUEST, FACTS, "2026-11-11", VENDOR)
    text = " ".join(anchor["lines"])
    assert "17.0% above the filed 17.95" in text
    assert "4.92 through 2026-09-30" in text and "3.72" in text and "32.3% above" in text
    # 21.00 - 4.92 = 16.08 left, against 17.95 - 3.72 = 14.23 a year earlier.
    assert "16.08" in text and "14.23" in text and "13.0% above" in text
    assert "low 19.55" in text and "high 20.63" in text and "above the high" in text and "unverified" in text.lower()
    assert anchor["vendor"]["position"] == "above_high" and anchor["growth_percent"].startswith("16.99")


def test_what_cannot_be_stated_is_left_out_not_estimated():
    # No filed quarter in the forecast period, and the forecast period does not contain the analysis date.
    later = {**REQUEST, "forecast": {"value": "24", "period_start": "2027-07-01", "period_end": "2028-06-30"}}
    anchor = earnings_anchor(later, FACTS, "2026-11-11", VENDOR)
    assert len(anchor["lines"]) == 1 and "33.7% above the filed 17.95" in anchor["lines"][0] and anchor["vendor"] is None
    # Two different filed values for the same quarter: the year-to-date line is not stated.
    twice = [*FACTS, _fact("q1-27b", "2026-07-01", "2026-09-30", "4.90")]
    assert not any("through 2026-09-30" in line for line in earnings_anchor(REQUEST, twice, "2026-11-11", VENDOR)["lines"])
    inside = {**REQUEST, "forecast": {**REQUEST["forecast"], "value": "20.00"}}
    assert "inside the range" in " ".join(earnings_anchor(inside, FACTS, "2026-11-11", VENDOR)["lines"])
    assert earnings_anchor({**REQUEST, "eps_fact_id": "missing"}, FACTS, "2026-11-11", None) is None
    assert earnings_anchor({"method": "revenue_case"}, FACTS, "2026-11-11", VENDOR) is None
    loss = [_fact("fy26", "2025-07-01", "2026-06-30", "-1.20")]
    assert earnings_anchor(REQUEST, loss, "2026-11-11", None) is None


def test_a_fiscal_calendar_that_shifts_by_a_few_days_still_finds_last_years_quarter():
    facts = [_fact("fy26", "2025-02-01", "2026-01-31", "2.41"), _fact("h1-26", "2025-02-01", "2025-07-31", "1.24"),
             _fact("h1-27", "2026-02-01", "2026-07-31", "1.38")]
    request = {"method": "earnings_case", "eps_fact_id": "fy26",
               "forecast": {"value": "2.70", "period_start": "2026-02-01", "period_end": "2027-01-31"}}
    text = " ".join(earnings_anchor(request, facts, "2026-11-11", None)["lines"])
    assert "1.38 through 2026-07-31" in text and "1.24" in text and "1.32" in text and "1.17" in text



def test_an_earnings_case_prints_the_comparison_in_the_block_the_agents_and_the_report_read():
    from tests.test_earnings_case import _row, _state
    from tradingagents.agents.shared_valuation import (
        prepare_shared_valuation,
        render_shared_valuation,
    )

    record = prepare_shared_valuation(_state([_row(), _row("Downside", "downside", multiple="15")]))
    assert record["rows"][0]["earnings_anchor"]["growth_percent"].startswith("20")     # 3.00 against the filed 2.50
    assert "Against the filings: the forecast of 3.00 is 20.0% above the filed 2.50" in render_shared_valuation(record)


def test_a_case_multiple_is_placed_against_the_companys_own_year_end_points():
    from tradingagents.agents.earnings_anchor import multiple_reference

    history = {"status": "available", "today": {"multiple": "46.03"},
               "rows": [{"multiple": "28.8"}, {"multiple": "40.7"}, {"multiple": "43.6"}]}
    line = multiple_reference({"method": "earnings_case", "multiple": "36"}, history)
    assert "36.0× is inside the span" in line and "28.8×, 40.7×, 43.6×" in line and "46.0× filed earnings" in line
    assert "above the highest" in multiple_reference({"method": "earnings_case", "multiple": "50"}, history)
    assert multiple_reference({"method": "earnings_case", "multiple": "36"}, {"status": "unavailable"}) is None
    assert multiple_reference({"method": "revenue_case", "multiple": "5"}, history) is None
