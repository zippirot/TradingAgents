"""An earnings case built from revenue, net margin and diluted share count, not one stated figure.

Reassessment 2026-11-13: the two lowest scored factors on every company were the valuation ones, and the
evaluators' recurring words were "EPS is one unbuilt number". The build makes the analyst state the three inputs;
code computes the earnings per share, checks it reproduces the stated forecast, and sets each input beside the
filed year.

Boundary: an earnings case only. The build is optional in the record so cases saved before it still replay, and a
case without one is priced exactly as before and says it is not built. Code never alters an input or the value.
"""
from decimal import Decimal

import pytest

from tests.test_earnings_case import _request
from tests.test_shared_valuation import evidence
from tradingagents.agents.valuation_cases import earnings_build_parts, price_earnings_case
from tradingagents.dataflows.financial_evidence import EvidencePackage

BUILD = {"revenue": "1100", "net_margin": "0.27", "diluted_shares": "99", "revenue_reason": "r", "margin_reason": "m",
         "shares_reason": "s"}


def _package(eps="2.50", income="250", shares="100", drop=()):
    record = evidence().model_dump(mode="json")
    base = next(f for f in record["facts"] if f["fact_id"] == "eps")
    base["value"] = eps
    for fact_id, metric, value, unit in (("income", "Net Income", income, "USD"),
                                         ("dil", "Weighted Average Diluted Shares", shares, "shares")):
        if fact_id not in drop:
            record["facts"].append({**base, "fact_id": fact_id, "metric": metric, "value": value, "unit": unit})
    return EvidencePackage.model_validate(record)


def test_the_build_reproduces_the_forecast_and_each_input_is_set_beside_the_filed_year():
    request = _request(build=BUILD)                                  # 1100 x 0.27 / 99 = 3.00, the stated forecast
    result, _ = price_earnings_case(request, _package(), ())
    assert result.target == Decimal("60.00")
    text = " ".join(result.assumptions)
    assert "build: revenue 1100 (+10.0% on the filed 1000)" in text
    assert "net margin 27.0% (filed 25.0%)" in text and "diluted shares 99 (-1.0% on the filed 100)" in text
    parts = earnings_build_parts(request, _package())
    assert parts["status"] == "checked" and Decimal(parts["built_eps"]) == Decimal("3")
    # 2.50 -> x1.10 revenue -> x1.08 margin -> /0.99 shares = 3.00; the three effects sum to the +0.50 change
    effects = [Decimal(parts[key]) for key in ("revenue_effect", "margin_effect", "shares_effect")]
    assert abs(sum(effects) - Decimal("0.50")) < Decimal("0.0000001") and effects[0] == Decimal("0.25")


def test_a_build_that_does_not_give_the_stated_forecast_is_refused():
    with pytest.raises(ValueError, match="build gives 2.50 a share, not the stated forecast 3.00"):
        price_earnings_case(_request(build={**BUILD, "revenue": "916.67"}), _package(), ())


def test_the_filed_gap_between_eps_and_net_income_per_share_is_carried_into_the_check():
    """Preferred dividends and the like: filed EPS 2.40 on net income of 2.50 a share is a ratio of 0.96."""
    request = _request(build=BUILD, forecast={**_request().forecast.model_dump(mode="json"), "value": "2.88"})
    result, _ = price_earnings_case(request, _package(eps="2.40"), ())
    assert result.target == Decimal("57.60") and "0.96" in " ".join(result.assumptions)


def test_without_a_build_the_case_is_priced_as_before_and_says_so():
    result, _ = price_earnings_case(_request(), _package(), ())
    assert result.target == Decimal("60.00")
    assert "not built from revenue, net margin and share count" in " ".join(result.assumptions)
    assert earnings_build_parts(_request(), _package()) is None


def test_a_build_with_no_filed_year_to_set_it_against_is_still_checked_against_its_own_forecast():
    result, _ = price_earnings_case(_request(build=BUILD), _package(drop=("income",)), ())
    assert "filed net income or diluted shares for the earnings year are unavailable" in " ".join(result.assumptions)
    assert earnings_build_parts(_request(build=BUILD), _package(drop=("income",)))["status"] == "unchecked"
    with pytest.raises(ValueError, match="build gives"):
        price_earnings_case(_request(build={**BUILD, "net_margin": "0.10"}), _package(drop=("income",)), ())


def test_net_income_derived_from_the_filing_counts_as_the_filed_year():
    """Caterpillar, 2026-11-13: its parent net income is derived (profit less the minority share), and three
    built cases were printed as "not set beside the filings"."""
    record = _package().model_dump(mode="json")
    for fact in record["facts"]:
        if fact["fact_id"] == "income":
            fact.update(origin="derived", formula_id="profit_less_noncontrolling_v1", input_fact_ids=["eps"])
    package = EvidencePackage.model_validate(record)
    assert earnings_build_parts(_request(build=BUILD), package)["status"] == "checked"
