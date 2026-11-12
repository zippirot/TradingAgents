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
