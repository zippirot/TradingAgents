"""Synthetic valuation fixtures. Prices are arithmetic tests, not recommendations."""

from datetime import date
from decimal import Decimal

import pytest

from tradingagents.agents.valuation import GroundedOutlook, validate_target
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord


def evidence(**overrides):
    source = SourceRecord(
        source_id="s",
        cik="0001582961",
        url="https://www.sec.gov/example",
        filed_date="2026-08-05",
        retrieved_at="2026-11-04T12:00:00Z",
        content_hash="a" * 64,
        locator="synthetic",
        accession="0001582961-26-000001",
        form="10-Q",
    )
    entries = [
        ("revenue", "Revenue", 1000, "USD", "2025-01-01", "2025-12-31", "US-GAAP"),
        ("shares", "Common Shares Outstanding", 100, "shares", None, "2026-06-30", "US-GAAP"),
        ("cash", "Cash and Equivalents", 100, "USD", None, "2026-06-30", "US-GAAP"),
        ("debt", "Total Borrowings", 200, "USD", None, "2026-06-30", "US-GAAP"),
        ("finance", "Finance Lease Liabilities", 20, "USD", None, "2026-06-30", "US-GAAP"),
        ("equipment", "Equipment Financing Obligations", 10, "USD", None, "2026-06-30", "US-GAAP"),
        ("operating", "Operating Lease Liabilities", 30, "USD", None, "2026-06-30", "US-GAAP"),
        ("eps", "Diluted EPS", 2, "USD/shares", "2025-01-01", "2025-12-31", "US-GAAP"),
    ]
    facts = []
    for identifier, metric, value, unit, start, end, basis in entries:
        values = {
            "fact_id": identifier,
            "metric": metric,
            "value": value,
            "unit": unit,
            "period_start": start,
            "period_end": end,
            "basis": basis,
            "as_of": "2026-10-19",
            "cik": source.cik,
            "source_ids": ("s",),
            "locator": "synthetic/" + identifier,
        }
        values.update(overrides.get(identifier, {}))
        facts.append(FinancialFact(**values))
    return EvidencePackage(
        cik=source.cik, as_of="2026-10-19", facts=tuple(facts), sources=(source,)
    )


def forecast(value=1200, **overrides):
    return dict(
        value=value,
        unit="USD",
        period_start="2027-01-01",
        period_end="2027-12-31",
        basis="US-GAAP",
        kind="analyst_forecast",
        rationale="Synthetic revenue growth assumption.",
        **overrides,
    )


def ev_request():
    return {
        "method": "ev_revenue",
        "revenue_fact_id": "revenue",
        "shares_fact_id": "shares",
        "cash_fact_id": "cash",
        "obligation_ids_by_category": {"borrowings": ["debt"]},
        "perimeter": "borrowings_only",
        "multiple_perimeter": "borrowings_only",
        "capital_structure_assumption": "unchanged_from_snapshot",
        "capital_structure_rationale": "Assume reported debt, cash and outstanding shares remain unchanged.",
        "scenarios": [
            {
                "name": "Base",
                "weight": "1",
                "forecast": forecast(),
                "multiple": "3",
                "multiple_rationale": "Subjective scenario multiple.",
            }
        ],
    }


def pe_request():
    return {
        "method": "pe",
        "eps_fact_id": "eps",
        "eps_basis": "diluted",
        "accounting_basis": "US-GAAP",
        "multiple": "20",
        "multiple_rationale": "Subjective historical earnings multiple.",
    }


def test_ev_revenue_has_exact_equity_bridge_and_explicit_assumptions():
    result = validate_target(ev_request(), evidence())
    assert result.status == "supported" and result.target == Decimal("35")
    scenario = result.scenario_results[0]
    assert scenario.enterprise_value == Decimal("3600")
    assert scenario.equity_value == Decimal("3500")
    assert scenario.price == Decimal("35")
    assert set(result.input_fact_ids) == {"revenue", "shares", "debt", "cash"}
    assert any("unchanged" in item.lower() for item in result.assumptions)
    assert any("subjective" in item.lower() for item in result.assumptions)
    assert result.unit == "USD/shares"


def test_scenarios_weighted_price_is_deterministic_and_subjective():
    request = ev_request()
    request["weight_rationale"] = "Subjective illustrative scenario allocation; not calibrated."
    request["scenarios"] = [
        {
            "name": "Bear",
            "weight": ".25",
            "forecast": forecast(1000),
            "multiple": "2",
            "multiple_rationale": "Subjective lower multiple.",
        },
        {
            "name": "Bull",
            "weight": ".75",
            "forecast": forecast(1400),
            "multiple": "4",
            "multiple_rationale": "Subjective higher multiple.",
        },
    ]
    result = validate_target(request, evidence())
    assert result.target == Decimal("46")
    assert [s.price for s in result.scenario_results] == [Decimal("19"), Decimal("55")]
    assert any("subjective" in item.lower() for item in result.assumptions)


@pytest.mark.parametrize("weight", ["-1", "0.9", "NaN", "Infinity"])
def test_bad_weights_never_produce_target(weight):
    request = ev_request()
    request["scenarios"][0]["weight"] = weight
    result = validate_target(request, evidence())
    assert result.target is None and result.status == "unsupported" and result.reasons


@pytest.mark.parametrize(
    "overrides",
    [
        {"shares": {"metric": "Weighted Average Diluted Shares"}},
        {"shares": {"value": 0}},
        {"shares": {"value": -10}},
        {"shares": {"period_end": "2026-03-31"}},
        {"cash": {"metric": "Cash Including Restricted Cash"}},
        {"cash": {"unit": "EUR"}},
        {"debt": {"period_start": "2026-01-01"}},
        {"debt": {"metric": "Long-term Borrowings (including current)"}},
        {"revenue": {"period_start": "2025-10-01"}},
    ],
)
def test_ev_invalid_source_definition_unit_period_or_denominator(overrides):
    result = validate_target(ev_request(), evidence(**overrides))
    assert result.target is None and result.reasons


def test_missing_fact_and_unsupported_method_are_readable_null_results():
    request = ev_request()
    request["shares_fact_id"] = "missing"
    assert validate_target(request, evidence()).target is None
    result = validate_target({"method": "dcf", "target": 96}, evidence())
    assert result.target is None and result.status == "unsupported" and result.reasons


def test_lease_inclusive_multiple_requires_matching_equity_bridge():
    request = ev_request()
    request["multiple_perimeter"] = "all_leases"
    result = validate_target(request, evidence())
    assert result.target is None
    request["perimeter"] = "all_leases"
    request["obligation_ids_by_category"].update(
        finance_leases=["finance"], equipment=["equipment"], operating_leases=["operating"]
    )
    result = validate_target(request, evidence())
    assert result.target == Decimal("34.4")


def test_missing_category_does_not_mean_zero_or_allow_overlap():
    request = ev_request()
    request["perimeter"] = request["multiple_perimeter"] = "finance_equipment"
    request["obligation_ids_by_category"]["finance_leases"] = ["finance"]
    assert validate_target(request, evidence()).target is None
    request["obligation_ids_by_category"].update(
        equipment=["equipment"], finance_equipment=["finance"]
    )
    assert validate_target(request, evidence()).target is None


def test_negative_equity_value_never_publishes_negative_target():
    result = validate_target(ev_request(), evidence(debt={"value": 5000}))
    assert result.target is None and not result.scenario_results


def test_pe_exact_basis_matched_reported_annual_eps():
    result = validate_target(pe_request(), evidence())
    assert result.target == Decimal("40")
    assert result.input_fact_ids == ("eps",)
    assert any("historical" in warning.lower() for warning in result.warnings)


@pytest.mark.parametrize(
    "source,request_change",
    [
        ({"eps": {"metric": "Basic EPS"}}, {}),
        ({"eps": {"basis": "management-adjusted"}}, {}),
        ({"eps": {"value": 0}}, {}),
        ({"eps": {"value": -2}}, {}),
        ({"eps": {"unit": "USD"}}, {}),
        ({"eps": {"period_start": "2025-10-01"}}, {}),
        ({}, {"multiple": "NaN"}),
        ({}, {"multiple": "-1"}),
    ],
)
def test_pe_rejects_wrong_share_basis_accounting_basis_units_and_values(source, request_change):
    request = pe_request()
    request.update(request_change)
    assert validate_target(request, evidence(**source)).target is None


def test_forward_eps_is_explicit_forecast_not_historical_fact():
    request = pe_request()
    request["forecast"] = {
        "value": "3",
        "unit": "USD/shares",
        "period_start": "2027-01-01",
        "period_end": "2027-12-31",
        "basis": "US-GAAP",
        "kind": "analyst_forecast",
        "rationale": "Explicit synthetic forward EPS assumption.",
    }
    result = validate_target(request, evidence())
    assert result.target == Decimal("60")
    assert any("forecast" in item.lower() for item in result.assumptions)
    request["forecast"]["basis"] = "management-adjusted"
    assert validate_target(request, evidence()).target is None


def outlook(kind="guidance"):
    return GroundedOutlook(
        record_id="outlook",
        source_ids=("s",),
        metric="Revenue",
        unit="USD",
        period_start="2027-01-01",
        period_end="2027-12-31",
        basis="US-GAAP",
        low=1000,
        high=1100,
        kind=kind,
    )


def test_same_period_guidance_divergence_is_visible_with_rationale():
    result = validate_target(ev_request(), evidence(), outlooks=(outlook(),))
    assert result.target == Decimal("35")
    assert any(
        "above" in warning.lower() and "guidance" in warning.lower() for warning in result.warnings
    )
    assert any("Synthetic revenue growth assumption" in item for item in result.assumptions)


def test_ambition_is_not_relabelled_guidance():
    result = validate_target(ev_request(), evidence(), outlooks=(outlook("ambition"),))
    assert any("ambition" in warning.lower() for warning in result.warnings)
    assert not any("management guidance" in warning.lower() for warning in result.warnings)


def test_management_forecast_requires_matching_grounded_outlook():
    request = ev_request()
    request["scenarios"][0]["forecast"].update(
        value=1050, kind="management_guidance", outlook_id="outlook"
    )
    assert validate_target(request, evidence()).target is None
    assert validate_target(request, evidence(), outlooks=(outlook(),)).target == Decimal("30.5")
    assert validate_target(request, evidence(), outlooks=(outlook("ambition"),)).target is None


def test_outlook_other_period_not_used_as_same_period_guidance():
    other = outlook().model_copy(
        update={"period_end": date(2028, 12, 31), "period_start": date(2028, 1, 1)}
    )
    result = validate_target(ev_request(), evidence(), outlooks=(other,))
    assert not any("above" in warning.lower() for warning in result.warnings)
    assert any("unavailable" in warning.lower() for warning in result.warnings)


def test_grounded_outlook_requires_actual_package_source():
    invalid = outlook().model_copy(update={"source_ids": ("missing",)})
    result = validate_target(ev_request(), evidence(), outlooks=(invalid,))
    assert result.target is None


def test_raw_request_cannot_supply_numeric_target_to_bypass_formula():
    request = pe_request()
    request["target"] = 96
    result = validate_target(request, evidence())
    assert result.target is None
    assert not any("96" in reason for reason in result.reasons)


def test_source_derivation_cannot_make_additive_eps_or_weighted_shares_a_reported_input():
    package = evidence()
    eps = next(f for f in package.facts if f.fact_id == "eps")
    eps = eps.model_copy(
        update={
            "origin": "derived",
            "formula_id": "four_quarter_sum_v1",
            "input_fact_ids": ("revenue",),
        }
    )
    changed = package.model_copy(
        update={"facts": tuple(eps if f.fact_id == "eps" else f for f in package.facts)}
    )
    result = validate_target(pe_request(), changed)
    assert result.target is None
    shares = next(f for f in package.facts if f.fact_id == "shares").model_copy(
        update={
            "origin": "derived",
            "formula_id": "unverified_share_bridge",
            "input_fact_ids": ("revenue",),
        }
    )
    changed = package.model_copy(
        update={"facts": tuple(shares if f.fact_id == "shares" else f for f in package.facts)}
    )
    assert validate_target(ev_request(), changed).target is None


def test_scenarios_with_different_forecast_periods_are_not_weighted():
    request = ev_request()
    request["weight_rationale"] = "Subjective illustrative scenario allocation; not calibrated."
    request["scenarios"] = [
        {
            "name": "A",
            "weight": ".5",
            "forecast": forecast(),
            "multiple": 3,
            "multiple_rationale": "Assumption",
        },
        {
            "name": "B",
            "weight": ".5",
            "forecast": forecast(),
            "multiple": 3,
            "multiple_rationale": "Assumption",
        },
    ]
    request["scenarios"][1]["forecast"].update(period_start="2028-01-01", period_end="2028-12-31")
    assert validate_target(request, evidence()).target is None


def test_future_eps_basis_can_match_verified_management_adjusted_eps():
    request = pe_request()
    request["accounting_basis"] = "management-adjusted"
    result = validate_target(request, evidence(eps={"basis": "management-adjusted"}))
    assert result.target == Decimal("40")


def test_model_copy_invalid_values_are_revalidated():
    from tradingagents.agents.valuation import PETarget

    request = PETarget.model_validate(pe_request()).model_copy(update={"multiple": Decimal("NaN")})
    assert validate_target(request, evidence()).target is None


def test_rationale_is_qualified_as_unvalidated_not_verified_prose():
    request = pe_request()
    request["multiple_rationale"] = "This proves a $96 target."
    result = validate_target(request, evidence())
    assert result.target == Decimal("40")
    assert all("unvalidated" in text.lower() for text in result.assumptions if "$96" in text)


def test_positive_explicit_forward_eps_can_follow_reported_historical_loss():
    request = pe_request()
    request["forecast"] = {
        "value": "3",
        "unit": "USD/shares",
        "period_start": "2027-01-01",
        "period_end": "2027-12-31",
        "basis": "US-GAAP",
        "kind": "analyst_forecast",
        "rationale": "Explicit profitability assumption, not an annualization of the loss.",
    }
    result = validate_target(request, evidence(eps={"value": -2}))
    assert result.target == Decimal("60")
    assert result.earnings_value == Decimal("3")
    assert result.valuation_period_end == date(2027, 12, 31)
