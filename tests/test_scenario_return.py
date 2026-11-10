"""One time basis for the rating check, yearly returns, return parts and weight sturdiness (plan Build 1)."""
from decimal import Decimal

import pytest

from tests.test_required_return import RETURN, _run, _three
from tests.test_scenario_decision import _accept, _reject, _state
from tradingagents.agents.scenario_decision import (
    priced_cases,
    render,
    render_cases_for_manager,
    retry_feedback,
    summarize,
    with_value_today,
)
from tradingagents.agents.scenario_return import (
    annual_return,
    return_parts,
    sturdiness,
    today_basis,
)

WEIGHED = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]
IMPLIED = {"status": "available", "price": {"close": "78.30", "currency": "USD"}, "shares": {"value": "117920731"},
           "trailing_revenue_usd": "1102671000",
           "rows": [{"perimeter": "borrowings_only", "status": "available", "net_obligations_usd": "-204466000"},
                    {"perimeter": "finance_equipment", "status": "available", "net_obligations_usd": "719133000"}]}


def _q(value, places="0.01"):
    return Decimal(value).quantize(Decimal(places))


def test_yearly_return_from_the_close_to_a_period_end_value():
    assert _q(annual_return("110", "100", "2026-01-01", "2027-01-01"), "0.0001") == Decimal("0.1000")
    assert _q(annual_return("77.22", "78.30", "2026-11-10", "2027-12-31"), "0.001") == Decimal("-0.012")
    for bad in (("0", "78.3", "2026-11-10", "2027-12-31"), ("77", "0", "2026-11-10", "2027-12-31"),
                ("77", "78.3", "2026-11-10", "2026-11-10"), ("77", "78.3", "2026-11-10", "x"), ("77", None, "a", "b")):
        assert annual_return(*bad) is None


def test_the_rating_check_moves_to_values_today_and_states_the_return_gap():
    summary = _run(WEIGHED)
    assert (summary["direction"], summary["direction_basis"], summary["consistency"]) == ("below", "value_today", "consistent")
    assert _q(summary["weighted_value_today"]) == Decimal("63.64") and _q(summary["weighted_value"]) == Decimal("70.84")
    assert _q(summary["weighted_today_vs_close_percent"], "0.1") == Decimal("-18.7")
    # The weighted case earns about -8.4% a year against a required 9.86%.
    assert _q(summary["weighted_annual_return"], "0.001") == Decimal("-0.084")
    assert _q(summary["return_gap_points"], "0.1") == Decimal("-18.3")
    text = "\n".join(render(summary))
    assert "On one time basis: accepted range today 38.57 USD/shares to 92.76 USD/shares" in text
    assert "weighted value today 63.64 USD/shares, -18.7% against the close" in text
    assert "returns -8.4% a year against a required 9.86%, a gap of -18.3 points" in text
    assert text.count("Direction:") == 1 and "Direction: below the close" in text
    assert "-40.9% a year from the close" in text and "+27.4% a year from the close" in text


def test_a_value_between_the_two_bases_changes_what_a_bullish_rating_owes():
    """70.84 at the period end is 'near' the 78.30 close; 63.64 today is 'below' it. A Buy now owes a reason."""
    state = {**_state(WEIGHED, rating="Buy"), "trade_date": "2026-11-10"}
    assert summarize(state, _three())["consistency"] == "consistent"            # no required return: period-end basis
    assert retry_feedback(state, _three()) == ""
    state["required_return"] = RETURN
    summary = summarize(state, _three())
    assert (summary["direction"], summary["consistency"]) == ("below", "unexplained")
    assert "weighted value today below the completed close" in retry_feedback(state, _three())
    explained = {**_state(WEIGHED, rating="Buy", reason="Capacity arrives early."), "trade_date": "2026-11-10",
                 "required_return": RETURN}
    assert summarize(explained, _three())["consistency"] == "explained"


def test_without_a_required_return_the_check_stays_on_period_end_values():
    summary = _run(WEIGHED, required=None)
    assert (summary["direction"], summary["direction_basis"]) == ("near", "period_end")
    assert summary["weighted_value_today"] is None and summary["sturdiness"] is None
    text = "\n".join(render(summary))
    assert "On one time basis" not in text and "If the weights are wrong" not in text
    assert "Direction: near the close, using a 10 percent threshold." in text
    # The yearly return needs no required return, only the close and the two dates.
    assert "-1.2% a year from the close" in text


def test_weight_sturdiness_states_the_equal_weight_value_and_the_break_even_weight():
    summary = _run(WEIGHED)
    check = summary["sturdiness"]
    assert _q(check["equal_weight_value_today"]) == Decimal("66.90") and check["highest"]["case_id"] == "up"
    # Others average (0.55*69.37 + 0.30*38.57) / 0.85 = 58.50; (78.30 - 58.50) / (92.76 - 58.50) = 0.578.
    assert (check["break_even"], _q(check["break_even_weight"], "0.001")) == ("available", Decimal("0.578"))
    text = "\n".join(render(summary))
    assert "would need a weight of 58%, against the 15% given" in text
    rows = [{"case_id": c, "name": c, "role": c, "weight": w, "value_today": v}
            for c, w, v in (("a", "0.5", "60"), ("b", "0.5", "70"))]
    assert sturdiness(rows, "78.30")["break_even"] == "unreachable"
    assert sturdiness(rows, "55")["break_even"] == "not_needed"
    assert sturdiness(rows[:1], "78.30") is None and sturdiness(rows, None) is None
    assert sturdiness([{**rows[0], "value_today": None}, rows[1]], "78.30") is None
    assert today_basis([{**rows[0], "value_today": None, "price": "1", "period_end": "2027-12-31"}], "78.3", "0.1", "2026-11-10") is None


def _case(basis="borrowings_only", **change):
    return {"price": "77.2187888479", "unit": "USD/shares", "forecast_revenue": "1950000000", "multiple": "4.7",
            "multiple_basis": basis, "net_obligations": "-133743000", "closing_shares": "120420731", **change}


def test_return_parts_split_the_change_from_the_close_and_sum_to_it_exactly():
    parts = return_parts(_case(), IMPLIED, "78.30")
    assert _q(parts["multiple_today"]) == Decimal("8.19")
    assert (_q(parts["revenue_effect"]), _q(parts["multiple_effect"]), _q(parts["capital_effect"])) == (
        Decimal("58.84"), Decimal("-57.68"), Decimal("-2.24"))
    total = sum(Decimal(parts[key]) for key in ("revenue_effect", "multiple_effect", "capital_effect"))
    assert abs(total - (Decimal("77.2187888479") - Decimal("78.30"))) < Decimal("1e-20") and _q(parts["total"]) == Decimal("-1.08")


@pytest.mark.parametrize("case,implied,close", [
    (_case(), {**IMPLIED, "status": "unavailable"}, "78.30"),
    (_case(), IMPLIED, "80.00"),                                  # the implied valuation used another close
    (_case("all_leases"), IMPLIED, "78.30"),                      # that perimeter is not in the implied valuation
    (_case("unknown"), IMPLIED, "78.30"),
    (_case(unit="EUR/shares"), IMPLIED, "78.30"),
    (_case(multiple=None), IMPLIED, "78.30"),
    (_case(price="90"), IMPLIED, "78.30"),                        # not priced by this construction
    (_case(), None, "78.30"),
])
def test_return_parts_say_nothing_when_they_cannot_be_exact(case, implied, close):
    assert return_parts(case, implied, close) is None


def test_return_parts_on_an_equity_basis_use_no_obligations():
    case = _case("equity", price="76.1080", net_obligations="0")
    parts = return_parts(case, IMPLIED, "78.30")
    assert _q(parts["multiple_today"]) == Decimal("8.37") and _q(parts["total"]) == Decimal("-2.19")


def test_the_card_prints_return_parts_for_cases_that_carry_the_inputs():
    rows = _three()
    for row, (revenue, multiple, net, shares, price) in zip(rows["rows"], (
            ("1950000000", "4.7", "-133743000", "120420731", "77.2187888479"),
            ("1700000000", "3.0", "-283743000", "125420731", "42.9254634148"),
            ("2050000000", "6.0", "-133743000", "120420731", "103.2525122273")), strict=True):
        row["request"] = {"forecast": {"value": revenue}, "multiple_basis": "borrowings_only"}
        row["result"].update(multiple=multiple, net_obligations=net, shares_outstanding=shares, target=price)
    state = {**_state(WEIGHED), "trade_date": "2026-11-10", "required_return": RETURN, "price_implied_valuation": IMPLIED}
    text = "\n".join(render(summarize(state, rows)))
    assert "Today's price is 8.19x revenue of the last twelve months (1.10B)" in text
    assert "- base — revenue to 1.95B: +58.84; multiple 8.19x to 4.70x: -57.68; shares and net obligations: -2.24; total -1.08" in text
    assert "- upside — revenue to 2.05B: +65.78; multiple 8.19x to 6.00x: -38.04" in text
    # Cases without those inputs (the fixtures above) print no such block.
    assert "Where each case's value comes from" not in "\n".join(render(_run(WEIGHED)))


def test_the_manager_sees_values_today_and_the_basis_of_the_check_only_when_a_return_is_recorded():
    state = {"trade_date": "2026-11-10", "required_return": RETURN}
    valued = render_cases_for_manager(with_value_today(priced_cases(_three()), state), RETURN)
    assert "(69.37 USD/shares today)" in valued and "Required return 9.86% a year" in valued
    assert "compares the weighted value today of your accepted cases with the completed close" in valued
    plain = render_cases_for_manager(with_value_today(priced_cases(_three()), {}), None)
    assert "today)" not in plain and "not discounted to today" in plain
    assert "compares the weighted value of your accepted cases with the completed close" in plain


def test_a_rejected_case_gets_a_yearly_return_but_does_not_move_the_basis():
    summary = _run([_accept("base", 0.5), _reject("down"), _accept("up", 0.5)])
    down = next(case for case in summary["cases"] if case["case_id"] == "down")
    assert down["annual_return"] is not None and _q(summary["range_today"]["low"]) == Decimal("69.37")


def test_yearly_returns_run_from_the_dated_close_not_the_analysis_date():
    """Audit finding: the close can be days older than the analysis date; the return is earned from the close."""
    rows = _three()
    for row in rows["rows"]:
        row["comparison"]["price"]["session_date"] = "2026-11-06"     # a Friday close read the following Tuesday
    state = {**_state(WEIGHED), "trade_date": "2026-11-10", "required_return": RETURN}
    summary = summarize(state, rows)
    base = next(case for case in summary["cases"] if case["case_id"] == "base")
    assert Decimal(base["annual_return"]) == annual_return("77.22", "78.30", "2026-11-06", "2027-12-31")
    assert Decimal(base["annual_return"]) != annual_return("77.22", "78.30", "2026-11-10", "2027-12-31")
    weighted = sum(Decimal(w) * Decimal(p) for w, p in (("0.55", "77.22"), ("0.30", "42.93"), ("0.15", "103.25")))
    assert Decimal(summary["weighted_annual_return"]) == annual_return(weighted, "78.30", "2026-11-06", "2027-12-31")
    # Value today is still brought back to the analysis date.
    assert _q(base["value_today"]) == Decimal("69.37")
    rows["rows"][0]["comparison"]["price"]["session_date"] = None
    undated = summarize(state, rows)
    assert next(case for case in undated["cases"] if case["case_id"] == "base")["annual_return"] is None


def test_rejecting_every_case_keeps_each_cases_own_arithmetic_and_drops_only_the_aggregate():
    """Audit finding: with nothing accepted the per-case returns and return parts disappeared."""
    rows = _three()
    for row, (revenue, multiple, net, shares, price) in zip(rows["rows"], (
            ("1950000000", "4.7", "-133743000", "120420731", "77.2187888479"),
            ("1700000000", "3.0", "-283743000", "125420731", "42.9254634148"),
            ("2050000000", "6.0", "-133743000", "120420731", "103.2525122273")), strict=True):
        row["request"] = {"forecast": {"value": revenue}, "multiple_basis": "borrowings_only"}
        row["result"].update(multiple=multiple, net_obligations=net, shares_outstanding=shares, target=price)
    state = {**_state([_reject("base"), _reject("down"), _reject("up")]), "trade_date": "2026-11-10",
             "required_return": RETURN, "price_implied_valuation": IMPLIED}
    summary = summarize(state, rows)
    assert summary["range"] is None and summary["sizing_rule"] is None and summary["weighted_value_today"] is None
    assert all(case["annual_return"] is not None and case.get("return_parts") for case in summary["cases"])
    text = "\n".join(render(summary))
    assert "-40.9% a year from the close" in text and "- base — revenue to 1.95B: +58.84" in text
    assert "Where each case's value comes from, per share, from the 2026-11-09 close" in text
    assert "Accepted range" not in text and "Rating check" not in text and "Sizing from the downside" not in text
    # A case with no comparable close of its own gets neither figure.
    rows["rows"][1]["comparison"] = {"status": "unavailable"}
    down = next(case for case in summarize(state, rows)["cases"] if case["case_id"] == "down")
    assert down["annual_return"] is None and "return_parts" not in down
