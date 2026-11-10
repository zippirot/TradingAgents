"""A case's multiple against the company's own history on the same basis, and funding bounds (plan Build 2)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tradingagents.agents.case_reference import BANDS, like_for_like, reference_position
from tradingagents.agents.valuation_cases import FUNDING_LIMIT, funding_bounds, funding_limit

QUARTERS = [("2024-12-31", "3142429966", "780615000"), ("2025-03-31", "3045843324", "806588000"),
            ("2025-06-30", "2602235069", "832812000"), ("2025-09-30", "3124487291", "863962000"),
            ("2025-12-31", "4424519087", "901427000"), ("2026-03-31", "8948800564", "948629000"),
            ("2026-06-30", "16488530983", "1011113000"), ("2026-09-30", "15729446236", "1102671000")]
BORROWINGS = {"2024-12-31": "1485366000", "2025-09-30": "1293815000", "2025-12-31": "1295762000",
              "2026-03-31": "919722000", "2026-06-30": "921053000"}
CASH = {"2024-12-31": "428446000", "2025-03-31": "360000000", "2025-06-30": "388000000", "2025-09-30": "236600000",
        "2025-12-31": "254477000", "2026-03-31": "741000000", "2026-06-30": "766000000", "2026-09-30": "666096000"}


def _fact(metric, day, value, unit="USD"):
    return {"metric": metric, "period_start": None, "period_end": day, "value": value, "unit": unit}


def _state(**change):
    facts = [_fact("Long-term Borrowings (including current)", day, value) for day, value in BORROWINGS.items()]
    facts += [_fact("Total Borrowings", "2026-09-30", "461630000")]
    facts += [_fact("Cash and Equivalents", day, value) for day, value in CASH.items()]
    rows = [{"quarter_end": day, "status": "available", "equity_value": equity, "equity_value_unit": "USD",
             "revenue": revenue, "multiple": str(Decimal(equity) / Decimal(revenue))} for day, equity, revenue in QUARTERS]
    state = {"financial_evidence": {"facts": facts},
             "valuation_reference": {"own_history": {
                 "status": "available", "rows": rows, "current_position": {"multiple": "8.37"},
                 "statistics": {"low": "3.12", "median": "4.47", "high": "16.31", "count": 8}}},
             "price_implied_valuation": {"status": "available", "rows": [
                 {"perimeter": "borrowings_only", "status": "available", "ratios": {"trailing_revenue": "8.19"}}]}}
    state.update(change)
    return state


def _row(multiple, basis="borrowings_only", target="77.22"):
    return {"result": {"method": "revenue_case", "multiple": multiple, "target": target, "shares_outstanding": "120420731"},
            "request": {"multiple_basis": basis, "forecast": {"value": "1950000000"}}}


def test_history_is_restated_on_the_cases_basis_from_reported_balances():
    same = like_for_like(_row("4.7"), _state())
    assert same["status"] == "available" and [q["quarter_end"] for q in same["quarters"]] == [
        "2024-12-31", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]
    # 2024-12-31: (3,142.4M + 1,485.4M - 428.4M) / 780.6M = 5.38.
    assert Decimal(same["quarters"][0]["multiple"]).quantize(Decimal("0.01")) == Decimal("5.38")
    assert [item["quarter_end"] for item in same["excluded"]] == ["2025-03-31", "2025-06-30"]
    assert (Decimal(same["low"]).quantize(Decimal("0.01")), same["band"], same["today"]) == (Decimal("4.84"), "below_low", "8.19")
    assert "left out for lack of a reported balance: 2025-03-31, 2025-06-30" in same["summary"]
    assert "today's price implies 8.19×" in same["summary"] and "on the same basis" in same["summary"]


@pytest.mark.parametrize("multiple,band", [("4.0", "below_low"), ("5.0", "low_to_median"), ("7.0", "low_to_median"),
                                           ("9.0", "median_to_high"), ("17", "above_high")])
def test_the_case_multiple_is_placed_directly_against_that_range(multiple, band):
    position = reference_position(_row(multiple), _state())
    assert (position["status"], position["basis"], position["band"]) == ("available", "like_for_like", band)
    assert BANDS[band] in position["summary"] and position["like_for_like"]["multiple"] == multiple
    # The earlier equity restatement is kept beside it for continuity.
    assert "implied_multiple" in position


def test_the_old_mismatched_comparison_put_the_same_case_in_a_higher_band():
    """Run d58117ef: 4.7x read as 'between the median and the high' of an equity/trailing series."""
    state = _state()
    assert reference_position(_row("4.7"), state)["band"] == "below_low"
    without_balances = {**state, "financial_evidence": {"facts": []}}
    fallback = reference_position(_row("4.7"), without_balances)
    assert fallback["basis"] == "equity_value / forecast_revenue" and fallback["band"] == "median_to_high"
    assert fallback["like_for_like"]["status"] == "unavailable" and "uses trailing revenue where the case uses forecast" in fallback["summary"]


def test_an_equity_case_uses_the_equity_series_and_other_bases_say_why_not():
    equity = like_for_like(_row("5", basis="equity"), _state())
    assert equity["status"] == "available" and len(equity["quarters"]) == 8 and equity["today"] == "8.37"
    for basis in ("finance_equipment", "all_leases", None):
        other = like_for_like(_row("5", basis=basis), _state())
        assert other["status"] == "unavailable" and "not retained" in other["reason"]


def test_a_quarter_is_left_out_not_estimated_when_its_balance_is_missing_ambiguous_or_not_in_usd():
    state = _state()
    state["financial_evidence"]["facts"] += [_fact("Cash and Equivalents", "2024-12-31", "1")]      # two values
    state["financial_evidence"]["facts"] = [f for f in state["financial_evidence"]["facts"]
                                            if not (f["metric"].startswith("Long-term") and f["period_end"] == "2025-09-30")]
    state["financial_evidence"]["facts"] += [_fact("Long-term Borrowings (including current)", "2025-09-30", "5", unit="EUR")]
    same = like_for_like(_row("4.7"), state)
    assert [q["quarter_end"] for q in same["quarters"]] == ["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]
    state["financial_evidence"]["facts"] = [f for f in state["financial_evidence"]["facts"] if f["period_end"] > "2026-03-31"]
    few = like_for_like(_row("4.7"), state)
    assert few["status"] == "unavailable" and "Fewer than 3" in few["reason"]
    assert like_for_like({"result": {"method": "revenue_case", "multiple": None}, "request": {}}, _state())["status"] == "unavailable"


def _capital(shares="120420731", end=date(2027, 12, 31)):
    return SimpleNamespace(closing_shares=SimpleNamespace(value=Decimal(shares)), valuation_date=end)


TERMS = {"schedule_totals": {"total": "1059176000", "interest": "-135577000"},
         "leases": [{"undiscounted_amount": "2955158", "unit": "USD thousands", "as_of": "2026-09-30",
                     "commencement_start": "2026-11", "commencement_end": "2028-06", "weighted_average_term_years": "11.1"}]}


def test_funding_bounds_come_from_the_filing_and_never_from_the_case():
    bounds = funding_bounds(_capital(), date(2026, 9, 30), Decimal("320453000"), TERMS, Decimal("320453000"))
    # 320.453M of deducted payments x 135.577 / 1,059.176 of interest = 41.0M; / 120.4M shares = 0.34.
    assert Decimal(bounds["interest"]["per_share_estimate"]).quantize(Decimal("0.01")) == Decimal("0.34")
    rent = bounds["rent"]
    # 2,955.158M / 11.1 years = 266.2M a year; 425 days from 2026-11-01 to 2027-12-31.
    assert Decimal(rent["annual_run_rate"]).quantize(Decimal("1e6")) == Decimal("266000000")
    assert (Decimal(rent["per_share_low"]), Decimal(rent["per_share_high"]).quantize(Decimal("0.01"))) == (0, Decimal("2.57"))
    text = funding_limit(bounds, "USD")
    assert "about 0.34 USD if interest falls evenly" in text
    assert "by 0.00 to 2.57 USD a share" in text and "The case does not say which applies" in text


def test_a_period_ending_after_the_commencement_window_has_a_floor_above_zero():
    rent = funding_bounds(_capital(end=date(2028, 12, 31)), date(2026, 9, 30), None, TERMS)["rent"]
    assert Decimal(rent["low"]) > 0 and Decimal(rent["low"]) < Decimal(rent["high"])


@pytest.mark.parametrize("terms", [
    {}, {"schedule_totals": {"total": "0", "interest": "-1"}, "leases": [{}]},
    {"schedule_totals": {"total": "10", "interest": "x"}, "leases": [{**TERMS["leases"][0], "as_of": "2025-12-31"}]},
    {"leases": [{**TERMS["leases"][0], "unit": "units"}, {**TERMS["leases"][0], "weighted_average_term_years": "0"},
                {**TERMS["leases"][0], "commencement_start": "soon"}, "text"]},
])
def test_unusable_terms_state_no_bound(terms):
    assert funding_bounds(_capital(), date(2026, 9, 30), Decimal("320453000"), terms, Decimal("320453000")) == {}
    assert funding_limit({}, "USD") == FUNDING_LIMIT


def test_an_equity_basis_case_carries_no_bounds_because_cash_does_not_enter_its_value():
    bounds = funding_bounds(_capital(), date(2026, 9, 30), Decimal("320453000"), TERMS, Decimal("320453000"))
    assert funding_limit(bounds, "USD", counts_cash=False) == FUNDING_LIMIT


def _bounds(stated, scheduled="320453000", terms=TERMS):
    return funding_bounds(_capital(), date(2026, 9, 30), None if scheduled is None else Decimal(scheduled), terms,
                          Decimal(stated))


def test_the_interest_figure_is_a_true_maximum_with_the_even_spread_labelled_as_an_estimate():
    """Audit finding: a lifetime-average share was printed as 'up to'. Interest can fall earlier than payments do."""
    item = _bounds("320453000")["interest"]
    # The most interest the period's payments can hold is all remaining imputed interest, 135.577M: 1.13 a share.
    assert Decimal(item["per_share_maximum"]).quantize(Decimal("0.01")) == Decimal("1.13")
    assert Decimal(item["per_share_estimate"]).quantize(Decimal("0.01")) == Decimal("0.34")
    text = funding_limit(_bounds("320453000"), "USD")
    assert "too low by at most 1.13 USD a share" in text and "about 0.34 USD if interest falls evenly" in text
    assert "an assumption the filing does not state" in text
    # Payments smaller than the remaining interest cap the maximum at the payments themselves.
    small = _bounds("100000000", scheduled="100000000")["interest"]
    assert Decimal(small["maximum"]) == Decimal("100000000")


def test_no_double_counting_is_claimed_for_payments_the_case_does_not_deduct():
    """Audit finding: the warning appeared even when the case deducted no finance payments."""
    assert "interest" not in _bounds("0") and "interest" not in _bounds("-5")
    assert "count that interest twice" not in funding_limit(_bounds("0"), "USD")
    # A case deducting part of the schedule can only double count interest inside what it deducts.
    part = _bounds("100000000")["interest"]
    assert Decimal(part["maximum"]) == Decimal("100000000")
    assert Decimal(part["estimate"]).quantize(Decimal("1")) == (Decimal("100000000") * Decimal("135577000") / Decimal("1059176000")).quantize(Decimal("1"))
    assert "interest" not in _bounds("320453000", scheduled=None)


def test_rent_is_called_a_level_payment_sensitivity_not_a_bound():
    """Audit finding: commitments, an average term and a window do not establish level payments."""
    text = funding_limit(_bounds("320453000"), "USD")
    assert "sized from the filing" in text and "bounded from the filing" not in text
    assert "if payments were level over the weighted-average term" in text
    assert "0.00 to 2.57 USD a share" in text and "The filing gives no payment schedule, so the actual figure can fall outside this range" in text


def test_the_same_basis_figure_sits_beside_the_growth_and_margin_of_its_quarter():
    from tradingagents.agents.case_reference import render_history_context

    text = render_history_context([
        {"quarter_end": "2024-12-31", "multiple": "4.03", "same_basis_multiple": "5.38",
         "revenue_growth_percent": None, "gross_margin_percent": "59.7"},
        {"quarter_end": "2025-03-31", "multiple": "3.78", "revenue_growth_percent": None, "gross_margin_percent": "60.3"}])
    assert "2024-12-31 4.03×, 5.38× with borrowings less cash (trailing revenue growth unavailable, gross margin 59.7%)" in text
    assert "2025-03-31 3.78× (trailing revenue growth" in text
