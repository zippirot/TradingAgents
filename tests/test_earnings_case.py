"""An earnings case: forecast diluted earnings per share times a stated multiple.

For a mature, profitable company a multiple of revenue is the wrong yardstick. The case takes the filed
annual diluted EPS as its baseline, an explicit annual forecast period after the analysis date, and a
multiple dated the analysis date. It has no net-debt bridge: earnings are after interest.
"""
from decimal import Decimal

import pytest

from tests.test_shared_valuation import evidence
from tests.test_valuation import forecast
from tradingagents.agents.valuation_cases import EarningsCase, price_earnings_case
from tradingagents.dataflows.financial_evidence import EvidencePackage


def _package(eps="2.50"):
    record = evidence().model_dump(mode="json")
    for fact in record["facts"]:
        if fact["fact_id"] == "eps":
            fact["value"] = eps
    return EvidencePackage.model_validate(record)


def _request(**changes):
    expected = {**forecast(), "value": "3.00", "unit": "USD/shares"}
    return EarningsCase.model_validate({"method": "earnings_case", "eps_fact_id": "eps", "forecast": expected,
                                        "multiple": "20", "multiple_assumption_date": "2026-10-19",
                                        "multiple_rationale": "Assumed market pricing.", **changes})


def test_value_is_forecast_earnings_per_share_times_the_multiple_and_says_how_it_was_reached():
    result, sensitivities = price_earnings_case(_request(), _package(), ())
    assert (result.status, result.method, result.target, result.unit) == ("supported", "earnings_case", Decimal("60.00"), "USD/shares")
    assert result.multiple == 20 and result.earnings_value == Decimal("3.00") and result.eps_basis == "diluted"
    assert result.input_fact_ids == ("eps",) and result.net_obligations is None and sensitivities == {}
    assert result.decision_use.classification == "forward_scenario" and result.decision_use.final_target_eligible
    text = " ".join(result.assumptions)
    assert "3.00" in text and "20" in text and "2.50" in text and "20.0%" in text      # forecast is 20% above filed
    assert "no net-debt bridge" in text


def test_a_company_without_positive_filed_earnings_is_refused_and_pointed_to_a_revenue_case():
    with pytest.raises(ValueError, match="positive filed annual diluted earnings per share"):
        price_earnings_case(_request(), _package(eps="-0.40"), ())
    with pytest.raises(ValueError, match="required source fact unavailable"):
        price_earnings_case(_request(eps_fact_id="missing"), _package(), ())
    with pytest.raises(ValueError, match="Diluted EPS"):
        price_earnings_case(_request(eps_fact_id="revenue"), _package(), ())


def test_the_multiple_must_be_dated_the_analysis_date_and_the_forecast_must_be_in_per_share_units():
    with pytest.raises(ValueError, match="analysis date"):
        price_earnings_case(_request(multiple_assumption_date="2026-10-01"), _package(), ())
    whole = {**forecast(), "value": "300000000", "unit": "USD"}
    with pytest.raises(ValueError, match="unit"):
        price_earnings_case(_request(forecast=whole), _package(), ())


# ---- in the report's valuation step ----

def _state(rows, eps="2.50"):
    import json

    from tests.test_shared_valuation import state

    saved = state(rows)
    saved["financial_evidence"] = _package(eps).model_dump(mode="json")
    saved["financial_claim_validation"]["raw_report"] = "Research\n```valuation_scenarios\n" + json.dumps(rows) + "\n```"
    return saved


def _row(name="Base", role="base", **changes):
    return {"name": name, "scenario_role": role, "request": _request(**changes).model_dump(mode="json")}


def test_earnings_cases_are_priced_as_weighable_cases_not_diagnostics():
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    record = prepare_shared_valuation(_state([_row(), _row("Downside", "downside", multiple="15")]))
    assert record["status"] == "available" and [row["diagnostic_only"] for row in record["rows"]] == [False, False]
    assert [Decimal(row["result"]["target"]) for row in record["rows"]] == [Decimal("60.00"), Decimal("45.00")]
    assert all(row["result"]["method"] == "earnings_case" for row in record["rows"])


def test_a_submission_that_mixes_revenue_and_earnings_cases_prices_nothing_and_says_why():
    from tests.test_case_valuation import revenue_case
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    record = prepare_shared_valuation(_state([_row("Earnings base"), revenue_case()]))
    assert record["status"] == "unavailable" and record["rows"] == []
    assert "one method" in record["reasons"][0]


def test_earnings_cases_reach_the_managers_weighing_and_the_printed_valuation_section():
    from tradingagents.agents.scenario_decision import priced_cases
    from tradingagents.agents.shared_valuation import (
        prepare_shared_valuation,
        render_shared_valuation,
    )

    record = prepare_shared_valuation(_state([_row(), _row("Downside", "downside", multiple="15")]))
    cases = priced_cases(record)
    assert [(c["name"], c["role"], c["method"], Decimal(c["price"]), c["forecast_eps"], c["forecast_revenue"]) for c in cases] == [
        ("Base", "base", "earnings_case", Decimal("60.00"), "3.00", None),
        ("Downside", "downside", "earnings_case", Decimal("45.00"), "3.00", None)]
    text = render_shared_valuation(record)
    assert "forecast EPS × multiple" in text and "Earnings case: forecast diluted earnings per share" in text
    assert "no net-debt bridge" in text


def test_the_decision_card_groups_earnings_cases_into_one_range_on_a_forward_earnings_basis():
    from tradingagents.agents.decision_context import _case_groups
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    record = prepare_shared_valuation(_state([_row(), _row("Downside", "downside", multiple="15")]))
    (group,) = _case_groups(record["rows"])
    assert group["multiple_basis"] == "forward P/E" and group["share_basis"] == "diluted EPS"
    assert (Decimal(group["low"]), Decimal(group["high"])) == (Decimal("45.00"), Decimal("60.00"))
    assert [case["name"] for case in group["cases"]] == ["Base", "Downside"]


def _with_diluted(package, year, latest):
    record = package.model_dump(mode="json")
    eps = next(f for f in record["facts"] if f["fact_id"] == "eps")
    record["facts"] += [
        {**eps, "fact_id": "w-year", "metric": "Weighted Average Diluted Shares", "value": str(year), "unit": "shares"},
        {**eps, "fact_id": "w-latest", "metric": "Weighted Average Diluted Shares", "value": str(latest), "unit": "shares",
         "period_start": "2026-04-01", "period_end": "2026-06-30"}]
    return EvidencePackage.model_validate(record)


def test_a_share_count_that_has_changed_by_more_than_half_since_the_earnings_year_refuses_the_case():
    steady, _ = price_earnings_case(_request(), _with_diluted(_package(), 100, 98), ())
    assert any("no split since the earnings year" in line for line in steady.assumptions)
    assert str(steady.capital_snapshot_date) == "2026-06-30"          # the latest balance sheet, as the price is anchored
    with pytest.raises(ValueError, match="share split is suspected"):
        price_earnings_case(_request(), _with_diluted(_package(), 100, 300), ())
    unchecked, _ = price_earnings_case(_request(), _package(), ())
    assert any("no later diluted share count is filed" in line for line in unchecked.assumptions)
