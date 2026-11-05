"""Financial evidence must remain exact, dated and reproducible across serialization."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tradingagents.dataflows.financial_evidence import (
    EvidencePackage,
    FinancialFact,
    SourceRecord,
    derive_quarter,
    derive_ttm,
)


def fact(value="100.125", **changes):
    data = {
        "fact_id": "a",
        "metric": "Revenue",
        "value": value,
        "unit": "USD",
        "cik": "0001582961",
        "period_start": "2025-10-01",
        "period_end": "2026-09-30",
        "as_of": "2026-11-04",
        "basis": "US-GAAP",
        "source_ids": ("src",),
        "locator": "us-gaap:Revenues",
        "origin": "reported",
    }
    data.update(changes)
    return FinancialFact(**data)


def test_exact_values_survive_json_and_are_frozen():
    f = fact("281123456.123456789")
    assert FinancialFact.model_validate_json(f.model_dump_json()).value == Decimal(
        "281123456.123456789"
    )
    with pytest.raises(ValidationError):
        f.value = Decimal(0)


def test_missing_value_requires_reason_and_zero_is_not_missing():
    with pytest.raises(ValidationError):
        fact(None)
    assert fact(None, missing_reason="not tagged").value is None
    assert fact("0").value == 0


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_values_are_rejected(value):
    with pytest.raises(ValidationError):
        fact(value)


def test_fiscal_q4_uses_compatible_annual_and_nine_month_periods():
    annual = fact("100.125")
    ytd = fact("70.025", fact_id="b", period_end="2026-06-30", source_ids=("other",))
    q4 = derive_quarter(annual, ytd)
    assert q4.value == Decimal("30.100")
    assert q4.period_start == date(2026, 7, 1)
    assert q4.period_end == date(2026, 9, 30)
    assert q4.origin == "derived"
    assert q4.input_fact_ids == ("a", "b")
    assert q4.source_ids == ("other", "src")
    assert q4.formula_id == "cumulative_difference_v1"


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "EUR"},
        {"cik": "0000320193"},
        {"basis": "adjusted"},
        {"as_of": "2026-10-19"},
        {"period_start": "2025-10-02"},
        {"value": None, "missing_reason": "unavailable"},
        {"metric": "Net Income"},
    ],
)
def test_quarter_derivation_refuses_incompatible_or_missing_inputs(changes):
    ytd = fact(**{"value": "70", "fact_id": "b", "period_end": "2026-06-30", **changes})
    with pytest.raises(ValueError):
        derive_quarter(fact(), ytd)


def test_eps_and_weighted_shares_are_never_subtracted():
    for metric, unit in [
        ("Diluted EPS", "USD/shares"),
        ("Weighted Average Diluted Shares", "shares"),
    ]:
        with pytest.raises(ValueError):
            derive_quarter(
                fact(metric=metric, unit=unit),
                fact("70", fact_id="b", metric=metric, unit=unit, period_end="2026-06-30"),
            )


def quarters():
    periods = [
        ("2025-10-01", "2025-12-31"),
        ("2026-01-01", "2026-03-31"),
        ("2026-04-01", "2026-06-30"),
        ("2026-07-01", "2026-09-30"),
    ]
    return [
        fact(str(i + 1), fact_id=str(i), period_start=start, period_end=end)
        for i, (start, end) in enumerate(periods)
    ]


def test_ttm_requires_four_contiguous_quarters_and_keeps_lineage():
    q = quarters()
    result = derive_ttm(q[::-1])
    assert result.value == Decimal(10)
    assert result.input_fact_ids == ("0", "1", "2", "3")
    assert result.formula_id == "four_quarter_sum_v1"
    with pytest.raises(ValueError):
        derive_ttm(q[:3])
    with pytest.raises(ValueError):
        derive_ttm([q[0], q[0], q[2], q[3]])
    q[1] = fact("2", fact_id="1", period_start="2026-01-02", period_end="2026-03-31")
    with pytest.raises(ValueError):
        derive_ttm(q)


def source(**changes):
    data = {
        "source_id": "src",
        "cik": "0001582961",
        "url": "https://data.sec.gov/example.json",
        "filed_date": "2026-10-30",
        "retrieved_at": "2026-11-04T17:00:00Z",
        "content_hash": "a" * 64,
        "locator": "us-gaap/Revenues",
        "form": "10-K",
    }
    data.update(changes)
    return SourceRecord(**data)


def test_package_checks_cutoff_issuer_references_and_unique_ids():
    base = {"cik": "0001582961", "as_of": "2026-11-04", "facts": (fact(),), "sources": (source(),)}
    package = EvidencePackage(**base)
    assert EvidencePackage.model_validate_json(package.model_dump_json()) == package
    for changes in [
        {"sources": ()},
        {"sources": (source(filed_date="2026-11-05"),)},
        {"sources": (source(cik="0000320193"),)},
        {"facts": (fact(), fact())},
    ]:
        with pytest.raises(ValidationError):
            EvidencePackage(**{**base, **changes})


def test_package_derivations_are_available_without_replacing_reported_values():
    from tradingagents.dataflows.financial_evidence import add_period_calculations

    q = quarters()
    package = EvidencePackage(
        cik="0001582961", as_of="2026-11-04", facts=tuple(q), sources=(source(),)
    )
    enriched = add_period_calculations(package)
    assert enriched.facts[:4] == tuple(q)
    ttm = [f for f in enriched.facts if f.formula_id == "four_quarter_sum_v1"]
    assert len(ttm) == 1 and ttm[0].value == Decimal(10)
    assert add_period_calculations(enriched) == enriched


def test_evidence_tool_pins_cutoff_to_graph_state(monkeypatch):
    import json

    from tradingagents.agents import tools

    captured = []
    package = EvidencePackage(
        cik="0001582961", as_of="2026-11-04", facts=(fact(),), sources=(source(),)
    )
    monkeypatch.setattr(
        tools,
        "build_financial_evidence",
        lambda ticker, cutoff: captured.append((ticker, cutoff)) or package,
    )
    result = tools.get_financial_evidence.func("DOCN", "2099-01-01", trade_date="2026-11-04")
    assert captured == [("DOCN", "2026-11-04")]
    assert json.loads(result)["facts"][0]["value"] == "100.125"


def test_evidence_tool_reports_retrieval_failure_without_bare_exception(monkeypatch):
    from tradingagents.agents import tools
    from tradingagents.dataflows.errors import VendorUnavailableError

    def unavailable(*args):
        raise VendorUnavailableError("SEC unavailable")

    monkeypatch.setattr(tools, "build_financial_evidence", unavailable)
    result = tools.get_financial_evidence.func("DOCN", "2026-11-04", trade_date="2026-11-04")
    assert "DATA_UNAVAILABLE" in result and "get_financial_evidence" in result


def test_decreasing_cumulative_issuance_is_a_reconciliation_gap_not_negative_proceeds():
    from tradingagents.dataflows.financial_evidence import add_period_calculations

    q1 = fact(
        "888778000",
        fact_id="q1",
        metric="Common Stock Issuance Proceeds",
        period_start="2026-01-01",
        period_end="2026-03-31",
    )
    h1 = fact(
        "887888000",
        fact_id="h1",
        metric="Common Stock Issuance Proceeds",
        period_start="2026-01-01",
        period_end="2026-06-30",
    )
    with pytest.raises(ValueError, match="reconciliation"):
        derive_quarter(h1, q1)
    package = EvidencePackage(
        cik="0001582961", as_of="2026-11-04", facts=(q1, h1), sources=(source(),)
    )
    enriched = add_period_calculations(package)
    assert len(enriched.facts) == 2
    assert any(
        "reconciliation" in warning and "q1" in warning and "h1" in warning
        for warning in enriched.warnings
    )


def test_reported_annual_value_takes_precedence_over_conflicting_ttm():
    from tradingagents.dataflows.financial_evidence import add_period_calculations

    annual = fact("10.001", fact_id="annual")
    package = EvidencePackage(
        cik="0001582961", as_of="2026-11-04", facts=(*quarters(), annual), sources=(source(),)
    )
    enriched = add_period_calculations(package)
    assert not any(f.formula_id == "four_quarter_sum_v1" for f in enriched.facts)
    assert any("reconciliation" in w and "annual" in w for w in enriched.warnings)


def test_signed_principal_outflow_has_explicit_magnitude_lineage():
    from tradingagents.dataflows.financial_evidence import derive_cash_outflow

    original = fact("-1234000", metric="Equipment Financing Principal Payments")
    magnitude = derive_cash_outflow(original)
    assert magnitude.value == Decimal("1234000")
    assert magnitude.origin == "derived"
    assert magnitude.input_fact_ids == ("a",)
    assert magnitude.formula_id == "reported_cash_outflow_magnitude_v1"
    assert original.value == Decimal("-1234000")
    with pytest.raises(ValueError):
        derive_cash_outflow(fact("-1234000", metric="Revenue"))


def test_explicit_combined_principal_preserves_reported_sign_and_derived_lineage():
    from tradingagents.dataflows.financial_evidence import derive_cash_outflow

    reported = fact(
        "-39895000",
        metric="Finance Lease and Financing Arrangement Principal Payments",
        period_start="2026-01-01",
        period_end="2026-09-30",
    )
    result = derive_cash_outflow(reported)
    assert reported.value < 0 and result.value == 39895000
    assert result.metric == reported.metric and result.input_fact_ids == (reported.fact_id,)
    assert result.source_ids == reported.source_ids


def test_bounded_tool_view_retains_annual_valuation_baselines_without_extra_data():
    from tradingagents.dataflows.financial_evidence import bounded_evidence_view

    recent = [fact(fact_id=f"recent-{i}", metric=f"Metric {i}",
                   period_start="2026-07-01", locator="source " + "x" * 1000)
              for i in range(80)]
    annual = [fact(fact_id=metric, metric=metric, period_start="2025-01-01",
                   period_end="2025-12-31", unit=unit)
              for metric, unit in (("Revenue", "USD"), ("Diluted EPS", "USD/shares"),
                                   ("Basic EPS", "USD/shares"))]
    recent += [f.model_copy(update={"fact_id": "quarter-" + f.fact_id,
                                   "period_start": date(2026, 7, 1),
                                   "period_end": date(2026, 9, 30)}) for f in annual]
    package = EvidencePackage(cik="0001582961", as_of="2026-11-04",
                              facts=tuple(recent + annual), sources=(source(),))
    original = package.model_dump_json()
    view = bounded_evidence_view(package)
    assert len(view.model_dump_json()) <= 64000
    assert {f.fact_id for f in annual} <= {f.fact_id for f in view.facts}
    assert all(f in package.facts for f in view.facts)
    assert package.model_dump_json() == original
