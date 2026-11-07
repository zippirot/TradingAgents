"""Synthetic, exact accounting fixtures; no model or network involved."""

from decimal import Decimal, localcontext

import pytest

from tradingagents.agents.accounting_checks import (
    calculate_cash_generation,
    calculate_obligations,
    check_adjusted_bridge,
    check_balance_sheet,
    check_cash_plus_marketable_securities,
    check_eps,
    check_equity_rollforward,
)
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord


def fact(key, value, metric=None, **kwargs):
    return FinancialFact(
        fact_id=key,
        metric=metric or key,
        value=value,
        unit=kwargs.pop("unit", "USD"),
        cik="0001582961",
        period_end=kwargs.pop("period_end", "2026-06-30"),
        as_of="2026-10-19",
        source_ids=("s",),
        locator=key,
        **kwargs,
    )


def package(*facts):
    source = SourceRecord(
        source_id="s",
        cik="0001582961",
        url="https://data.sec.gov/source",
        filed_date="2026-08-04",
        retrieved_at="2026-10-19T00:00:00Z",
        content_hash="a" * 64,
        locator="source",
        form="10-Q",
    )
    return EvidencePackage(cik="0001582961", as_of="2026-10-19", sources=(source,), facts=facts)


def test_balance_sheet_and_precision_bound():
    p = package(
        fact("a", "1000", "Total Assets"),
        fact("l", "600", "Total Liabilities"),
        fact("e", "400", "Stockholders Equity"),
    )
    result = check_balance_sheet(
        p, "a", "l", "e", {"a": Decimal("1"), "l": Decimal("1"), "e": Decimal("1")}
    )
    assert result.status == "pass" and result.residual == 0 and result.tolerance == Decimal("1.5")
    assert result.input_fact_ids == ("a", "l", "e")
    assert check_balance_sheet(p, "a", "l", "missing", {}).status == "unavailable"
    assert check_balance_sheet(p, "a", "l", "e", {}).status == "pass"


def test_balance_sheet_rejects_units_periods_and_material_residual():
    for replacement in [
        fact("e", "350", "Stockholders Equity"),
        fact("e", "400", "Stockholders Equity", unit="EUR"),
        fact("e", "400", "Stockholders Equity", period_end="2025-12-31"),
    ]:
        p = package(
            fact("a", "1000", "Total Assets"), fact("l", "600", "Total Liabilities"), replacement
        )
        assert (
            check_balance_sheet(p, "a", "l", "e", dict.fromkeys(["a", "l", "e"], Decimal(1))).status
            != "pass"
        )


def test_equity_rollforward_exact_values_and_missing_offering():
    # Arithmetic fixture uses assessment amounts with synthetic role assignments.
    # These assignments do not prove the unresolved DOCN movement classification.
    components = [
        ("other_equity_reduction", -37335000),
        ("espp", 2494000),
        ("issuance", 887888000),
        ("sbc", 55962000),
        ("oci", -796000),
        ("net_income", 51208000),
    ]
    fs = [
        fact("opening", -28690000, "Stockholders Equity", period_end="2025-12-31"),
        fact("closing", 930731000, "Stockholders Equity"),
    ]
    roles = {
        "other_equity_reduction": "Equity Stock Repurchases/Retirements",
        "espp": "Employee Stock Purchase Plan Issuance Value",
        "issuance": "Equity Common Stock Issuance Value",
        "sbc": "Equity Share-based Compensation",
        "oci": "Other Comprehensive Income Attributable to Parent",
        "net_income": "Net Income",
    }
    fs += [fact(k, v, roles[k], period_start="2026-01-01") for k, v in components]
    p = package(*fs)
    ids = tuple((k, 1) for k, _ in components)
    precision = dict.fromkeys([f.fact_id for f in fs], Decimal(1000))
    assert check_equity_rollforward(p, "opening", "closing", ids, True, precision).status == "pass"
    assert (
        check_equity_rollforward(p, "opening", "closing", ids[1:], True, precision).status == "fail"
    )
    assert (
        check_equity_rollforward(p, "opening", "closing", ids, False, precision).status
        == "unavailable"
    )


def test_duplicate_or_nonadjacent_equity_input_is_rejected():
    p = package(
        fact("opening", 100, "Stockholders Equity", period_end="2025-12-31"),
        fact("closing", 120, "Stockholders Equity"),
        fact("income", 20, "Net Income", period_start="2026-02-01"),
    )
    assert (
        check_equity_rollforward(
            p,
            "opening",
            "closing",
            (("income", 1),),
            True,
            dict.fromkeys(["opening", "closing", "income"], Decimal(1)),
        ).status
        == "unavailable"
    )
    assert (
        check_equity_rollforward(
            p, "opening", "closing", (("income", 1), ("income", 1)), True, {}
        ).status
        == "unavailable"
    )


def obligations():
    return package(
        fact("debt", 100, "Long-term Borrowings (including current)"),
        fact("short", 0, "Short-term Borrowings"),
        fact("finance", 20, "Finance Lease Liabilities"),
        fact("equipment", 10, "Equipment Financing Obligations"),
        fact("operating", 30, "Operating Lease Liabilities"),
        fact("cash", 40, "Cash and Equivalents"),
    )


def test_obligation_perimeters_are_separate_and_no_double_count():
    groups = {
        "borrowings": ("debt", "short"),
        "finance_leases": ("finance",),
        "equipment": ("equipment",),
        "operating_leases": ("operating",),
    }
    out = calculate_obligations(obligations(), groups, "cash")
    assert [r.result for r in out] == [Decimal(60), Decimal(90), Decimal(120)]
    bad = package(*obligations().facts, fact("current", 15, "Current Finance Lease Liabilities"))
    assert (
        calculate_obligations(bad, {**groups, "finance_leases": ("finance", "current")}, "cash")[
            1
        ].status
        == "unavailable"
    )
    assert (
        calculate_obligations(obligations(), {**groups, "equipment": ()}, "cash")[1].status
        == "unavailable"
    )


def test_cash_generation_separates_capex_principal_and_requires_coverage():
    p = package(
        fact("ocf", 100, "Operating Cash Flow", period_start="2026-01-01"),
        fact("capex", 20, "Capital Expenditure", period_start="2026-01-01"),
        fact("software", 5, "Software Development Payments", period_start="2026-01-01"),
        fact("principal", 10, "Finance Lease Principal Payments", period_start="2026-01-01"),
    )
    out = calculate_cash_generation(p, "ocf", ("capex", "software"), ("principal",), True)
    assert [r.result for r in out] == [Decimal(75), Decimal(65)]
    assert (
        calculate_cash_generation(p, "ocf", ("capex",), ("principal",), False)[0].status
        == "unavailable"
    )
    assert (
        calculate_cash_generation(p, "ocf", ("principal",), ("principal",), True)[0].status
        == "unavailable"
    )


def test_eps_uses_explicit_numerator_and_matching_basis():
    p = package(
        fact("n", 36.827e6, "Diluted Earnings Numerator", period_start="2026-04-01"),
        fact(
            "s",
            126548000,
            "Weighted Average Diluted Shares",
            unit="shares",
            period_start="2026-04-01",
        ),
        fact("eps", "0.29", "Diluted EPS", unit="USD/shares", period_start="2026-04-01"),
    )
    out = check_eps(
        p, "n", "s", "eps", {"n": Decimal(1000), "s": Decimal(1000), "eps": Decimal(".01")}
    )
    assert out.status == "pass" and out.result > Decimal(".29")
    wrong = package(fact("n", 36.827e6, "Net Income", period_start="2026-04-01"), *p.facts[1:])
    assert check_eps(wrong, "n", "s", "eps", {}).status == "unavailable"
    zero = package(
        p.facts[0],
        fact("s", 0, "Weighted Average Diluted Shares", unit="shares", period_start="2026-04-01"),
        p.facts[2],
    )
    assert check_eps(zero, "n", "s", "eps", {}).status == "unavailable"


def test_adjusted_bridge_requires_complete_explicit_adjustments():
    p = package(
        fact("gaap", 10, "Net Income", period_start="2026-01-01"),
        fact(
            "adjusted",
            15,
            "Adjusted Net Income",
            period_start="2026-01-01",
            basis="management-adjusted",
        ),
        fact("sbc", 5, "Management Share-based Compensation Adjustment", period_start="2026-01-01"),
    )
    precision = dict.fromkeys(["gaap", "adjusted", "sbc"], Decimal(1))
    assert (
        check_adjusted_bridge(p, "gaap", "adjusted", (("sbc", 1),), True, precision).status
        == "pass"
    )
    assert (
        check_adjusted_bridge(p, "gaap", "adjusted", (("sbc", 1),), False, precision).status
        == "unavailable"
    )


def test_unknown_precision_does_not_excuse_nonzero_residual():
    p = package(
        fact("a", 1000, "Total Assets"),
        fact("l", 600, "Total Liabilities"),
        fact("e", 399, "Stockholders Equity"),
    )
    result = check_balance_sheet(p, "a", "l", "e", {})
    assert result.status == "unavailable" and result.reason_code == "precision_unavailable"
    assert result.residual == Decimal("-1")
    result = check_balance_sheet(
        p, "a", "l", "e", {"a": Decimal("NaN"), "l": Decimal(1), "e": Decimal(1)}
    )
    assert result.status == "unavailable"


def test_recorded_docn_balance_sheet_is_exact(monkeypatch):
    import json
    from pathlib import Path

    from tradingagents.dataflows.vendors import sec_edgar as sec

    data = json.loads(
        (Path(__file__).parent / "fixtures/docn_2026q2/companyfacts.json").read_text()
    )
    monkeypatch.setattr(sec, "cik_for", lambda ticker: "0001582961")
    monkeypatch.setattr(sec, "_cached_json", lambda *a: data)
    p = sec.get_financial_evidence("DOCN", "2026-10-19")
    facts = {
        f.metric: f for f in p.facts if str(f.period_end) == "2026-06-30" and f.period_start is None
    }
    result = check_balance_sheet(
        p,
        *(facts[k].fact_id for k in ("Total Assets", "Total Liabilities", "Stockholders Equity")),
        {},
    )
    assert result.status == "pass" and result.residual == 0 and result.result == 3123053000


def test_cash_plus_current_marketable_is_statement_liquidity_only():
    p = package(fact("cash", 666_096_000, "Cash and Equivalents"),
                fact("sec", 178_645_000, "Current Marketable Securities"))
    result = check_cash_plus_marketable_securities(p)
    assert result.method == "cash_plus_marketable_securities_v1"
    assert result.status == "pass" and result.result == 844_741_000
    assert result.unit == "USD" and result.input_fact_ids == ("cash", "sec")
    assert "not unrestricted valuation cash" in result.message
    assert calculate_obligations(p, {"borrowings": ("sec",)}, "cash")[0].status == "unavailable"


def test_cash_plus_marketable_fails_closed_for_missing_or_incompatible_securities():
    cash = fact("cash", 666_096_000, "Cash and Equivalents")
    assert check_cash_plus_marketable_securities(package(cash)).status == "unavailable"
    for securities in (
        fact("sec", 178_645_000, "Marketable Securities"),
        fact("sec", 178_645_000, "Current Marketable Securities", unit="EUR"),
        fact("sec", 178_645_000, "Current Marketable Securities", period_end="2025-12-31"),
    ):
        assert check_cash_plus_marketable_securities(package(cash, securities)).status == "unavailable"
    newer_cash = fact("newcash", 10, "Cash and Equivalents", period_end="2026-09-30")
    old_securities = fact("oldsec", 20, "Current Marketable Securities")
    assert check_cash_plus_marketable_securities(package(cash, newer_cash, old_securities)).status == "unavailable"


def test_cash_generation_rejects_non_cash_and_operating_lease_inputs():
    for metric in ["Noncash Finance Lease Additions", "Operating Lease Payments"]:
        p = package(
            fact("ocf", 100, "Operating Cash Flow", period_start="2026-01-01"),
            fact("capex", 20, "Capital Expenditure", period_start="2026-01-01"),
            fact("p", 10, metric, period_start="2026-01-01"),
        )
        assert (
            calculate_cash_generation(p, "ocf", ("capex",), ("p",), True)[1].status == "unavailable"
        )


def test_calculation_is_immutable_and_json_exact():
    from pydantic import ValidationError

    p = package(
        fact("a", "1000.123456789", "Total Assets"),
        fact("l", "600", "Total Liabilities"),
        fact("e", "400.123456789", "Stockholders Equity"),
    )
    result = check_balance_sheet(p, "a", "l", "e", {})
    assert type(result).model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        result.result = Decimal(0)


def test_known_broad_productive_assets_cannot_double_count_software():
    capex = fact("capex", 20, "Capital Expenditure", period_start="2026-01-01").model_copy(
        update={"locator": "us-gaap/PaymentsToAcquireProductiveAssets/USD/2026-01-01/2026-06-30"}
    )
    p = package(
        fact("ocf", 100, "Operating Cash Flow", period_start="2026-01-01"),
        capex,
        fact("software", 5, "Software Development Payments", period_start="2026-01-01"),
    )
    assert (
        calculate_cash_generation(p, "ocf", ("capex", "software"), (), True)[0].status
        == "unavailable"
    )


def test_coverage_declaration_must_be_boolean_true():
    p = package(
        fact("ocf", 100, "Operating Cash Flow", period_start="2026-01-01"),
        fact("capex", 20, "Capital Expenditure", period_start="2026-01-01"),
    )
    assert (
        calculate_cash_generation(p, "ocf", ("capex",), (), "complete")[0].status == "unavailable"
    )


@pytest.mark.parametrize(
    "opening_metric,component_metric",
    [
        ("Total Assets", "Net Income"),
        ("Stockholders Equity", "Revenue"),
        ("Stockholders Equity", "Cash-flow Share-based Compensation"),
    ],
)
def test_equity_role_mismatch_cannot_pass_exact_arithmetic(opening_metric, component_metric):
    p = package(
        fact("opening", 100, opening_metric, period_end="2025-12-31"),
        fact("closing", 120, "Stockholders Equity"),
        fact("movement", 20, component_metric, period_start="2026-01-01"),
    )
    assert (
        check_equity_rollforward(p, "opening", "closing", (("movement", 1),), True, {}).status
        == "unavailable"
    )


@pytest.mark.parametrize(
    "gaap_metric,adjusted_metric,component_metric",
    [
        ("Revenue", "Adjusted Net Income", "Management Share-based Compensation Adjustment"),
        ("Net Income", "Adjusted Revenue", "Management Share-based Compensation Adjustment"),
        ("Net Income", "Adjusted Net Income", "Revenue"),
    ],
)
def test_adjusted_bridge_rejects_unrelated_roles(gaap_metric, adjusted_metric, component_metric):
    p = package(
        fact("gaap", 10, gaap_metric, period_start="2026-01-01"),
        fact(
            "adjusted", 15, adjusted_metric, period_start="2026-01-01", basis="management-adjusted"
        ),
        fact("adjustment", 5, component_metric, period_start="2026-01-01"),
    )
    assert (
        check_adjusted_bridge(p, "gaap", "adjusted", (("adjustment", 1),), True, {}).status
        == "unavailable"
    )


def test_cash_issuance_proceeds_are_not_equity_statement_movement():
    p = package(
        fact("opening", 100, "Stockholders Equity", period_end="2025-12-31"),
        fact("closing", 120, "Stockholders Equity"),
        fact("issuance", 20, "Common Stock Issuance Proceeds", period_start="2026-01-01"),
    )
    assert (
        check_equity_rollforward(p, "opening", "closing", (("issuance", 1),), True, {}).status
        == "unavailable"
    )
    equity_issuance = p.facts[-1].model_copy(
        update={"metric": "Equity Common Stock Issuance Value"}
    )
    corrected = package(*p.facts[:-1], equity_issuance)
    assert (
        check_equity_rollforward(
            corrected, "opening", "closing", (("issuance", 1),), True, {}
        ).status
        == "pass"
    )


def test_derived_broad_capex_keeps_overlap_prohibition():
    from tradingagents.dataflows.financial_evidence import derive_quarter

    q1 = fact(
        "q1", 10, "Capital Expenditure", period_start="2026-01-01", period_end="2026-03-31"
    ).model_copy(
        update={"locator": "us-gaap/PaymentsToAcquireProductiveAssets/USD/2026-01-01/2026-03-31"}
    )
    h1 = fact("h1", 30, "Capital Expenditure", period_start="2026-01-01").model_copy(
        update={"locator": "us-gaap/PaymentsToAcquireProductiveAssets/USD/2026-01-01/2026-06-30"}
    )
    q2 = derive_quarter(h1, q1)
    p = package(
        q1,
        h1,
        q2,
        fact("ocf", 100, "Operating Cash Flow", period_start="2026-04-01"),
        fact("software", 5, "Software Development Payments", period_start="2026-04-01"),
    )
    result = calculate_cash_generation(p, "ocf", (q2.fact_id, "software"), (), True)[0]
    assert result.status == "unavailable"


def test_combined_finance_equipment_disclosure_does_not_invent_component_residual():
    p = package(
        fact("debt", 921053000, "Long-term Borrowings (including current)"),
        fact("combined", 577720000, "Finance Lease and Equipment Obligations"),
        fact("operating", 479087000, "Operating Lease Liabilities"),
        fact("cash", 767026000, "Cash and Equivalents"),
    )
    groups = {
        "borrowings": ("debt",),
        "finance_equipment": ("combined",),
        "operating_leases": ("operating",),
    }
    out = calculate_obligations(p, groups, "cash")
    assert [item.result for item in out] == [
        Decimal(154027000),
        Decimal(731747000),
        Decimal(1210834000),
    ]
    assert out[1].input_fact_ids == ("debt", "combined", "cash")
    assert not any("residual" in item.method for item in out)


@pytest.mark.parametrize("extra_category", ["finance_leases", "equipment"])
def test_combined_obligations_reject_separate_category_overlap(extra_category):
    p = package(
        *obligations().facts, fact("combined", 30, "Finance Lease and Equipment Obligations")
    )
    groups = {
        "borrowings": ("debt",),
        "finance_equipment": ("combined",),
        "operating_leases": ("operating",),
        extra_category: ("finance" if extra_category == "finance_leases" else "equipment",),
    }
    out = calculate_obligations(p, groups, "cash")
    assert out[0].status == "pass"
    assert out[1].status == out[2].status == "unavailable"


def test_source_backed_total_borrowings_avoids_inferred_short_term_zero():
    p = package(fact("total", 100, "Total Borrowings"), fact("cash", 40, "Cash and Equivalents"))
    result = calculate_obligations(p, {"borrowings": ("total",)}, "cash")[0]
    assert result.status == "pass" and result.result == Decimal(60)
    assert result.input_fact_ids == ("total", "cash")


@pytest.mark.parametrize(
    "metric",
    [
        "Short-term Borrowings",
        "Long-term Borrowings (including current)",
        "Current Long-term Borrowings",
        "Noncurrent Long-term Borrowings",
    ],
)
def test_total_borrowings_cannot_overlap_any_borrowing_component(metric):
    p = package(
        fact("total", 100, "Total Borrowings"),
        fact("component", 20, metric),
        fact("cash", 40, "Cash and Equivalents"),
    )
    result = calculate_obligations(p, {"borrowings": ("total", "component")}, "cash")[0]
    assert result.status == "unavailable"


def test_equipment_acquisition_payment_is_not_financing_principal():
    p = package(
        fact("ocf", 100, "Operating Cash Flow", period_start="2026-01-01"),
        fact("capex", 20, "Capital Expenditure", period_start="2026-01-01"),
        fact("equipment", 10, "Equipment on Lease Payments", period_start="2026-01-01"),
    )
    result = calculate_cash_generation(p, "ocf", ("capex",), ("equipment",), True)
    assert result[0].status == "pass"
    assert result[1].status == "unavailable"
    principal = p.facts[-1].model_copy(update={"metric": "Equipment Financing Principal Payments"})
    corrected = package(*p.facts[:-1], principal)
    result = calculate_cash_generation(corrected, "ocf", ("capex",), ("equipment",), True)
    assert result[1].status == "pass" and result[1].result == Decimal(70)


def test_eps_unknown_precision_preserves_calculation_without_claiming_reconciliation():
    p = package(
        fact("n", 36827000, "Diluted Earnings Numerator", period_start="2026-04-01"),
        fact(
            "s",
            126548000,
            "Weighted Average Diluted Shares",
            unit="shares",
            period_start="2026-04-01",
        ),
        fact("eps", ".29", "Diluted EPS", unit="USD/shares", period_start="2026-04-01"),
    )
    result = check_eps(p, "n", "s", "eps", {})
    assert result.status == "unavailable" and result.reason_code == "precision_unavailable"
    assert result.result is not None and Decimal(".291") < result.result < Decimal(".292")
    assert result.expected == Decimal(".29")
    with localcontext() as ctx:
        ctx.prec = 50
        assert result.residual == result.result - result.expected
    assert result.unit == "USD/shares" and result.input_fact_ids == ("n", "s", "eps")
    assert result.tolerance is None


def test_recorded_docn_nine_month_equity_uses_exact_new_roles():
    # Transcribed total-equity column of DOCN 2026-09-30 10-Q, accession
    # 000162828026069141; raw SHA256
    # f5f9cd5e507ba82006afbbe1776e5b8e4912d442a634c990b7c58068df5604e5.
    # Acquisition is proved separately; no generic cash-flow role substitutes.
    movements = (
        ("incentive", "Equity Incentive Plan Issuance Net of Withholding", -58740000),
        ("espp", "Employee Stock Purchase Plan Issuance Value", 2494000),
        ("offering", "Equity Common Stock Issuance Value", 887888000),
        ("conversion", "Equity Conversion of Debt", 515696000),
        ("sbc", "Equity Share-based Compensation", 90246000),
        ("oci", "Other Comprehensive Income Attributable to Parent", -1037000),
        ("income", "Net Income Attributable to Common Stockholders", 8599000),
    )
    facts = [
        fact("opening", -28690000, "Stockholders Equity", period_end="2025-12-31"),
        fact("closing", 1416456000, "Stockholders Equity", period_end="2026-09-30"),
        *(
            fact(key, value, metric, period_start="2026-01-01", period_end="2026-09-30")
            for key, metric, value in movements
        ),
    ]
    from datetime import date

    from tradingagents.dataflows.financial_evidence import SourceRecord

    source = SourceRecord(
        source_id="s",
        cik="0001582961",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000162828026069141/docn-20260930.htm",
        filed_date="2026-11-03",
        retrieved_at="2026-11-04T19:40:15.075791+00:00",
        content_hash="f5f9cd5e507ba82006afbbe1776e5b8e4912d442a634c990b7c58068df5604e5",
        locator="2026 stockholders equity table, total column",
        accession="0001628280-26-069141",
        form="10-Q",
    )
    facts = [f.model_copy(update={"as_of": date(2026, 11, 4)}) for f in facts]
    evidence = EvidencePackage(
        cik=source.cik, as_of="2026-11-04", sources=(source,), facts=tuple(facts)
    )
    result = check_equity_rollforward(
        evidence,
        "opening",
        "closing",
        tuple((key, 1) for key, _, _ in movements),
        True,
        dict.fromkeys((f.fact_id for f in facts), Decimal(1000)),
    )
    assert result.status == "pass" and result.residual == 0 and result.result == Decimal(1416456000)


def test_equity_net_income_total_and_common_shareholder_subset_cannot_both_be_added():
    p = package(
        fact("opening", 100, "Stockholders Equity", period_end="2025-12-31"),
        fact("closing", 120, "Stockholders Equity"),
        fact("net", 10, "Net Income", period_start="2026-01-01"),
        fact(
            "common",
            10,
            "Net Income Attributable to Common Stockholders",
            period_start="2026-01-01",
        ),
    )
    assert (
        check_equity_rollforward(
            p, "opening", "closing", (("net", 1), ("common", 1)), True, {}
        ).status
        == "unavailable"
    )


def combined_principal_package(scoped=True):
    p = package(
        fact("ocf", 100000000, "Operating Cash Flow", period_start="2026-01-01"),
        fact("capex", 20000000, "Capital Expenditure", period_start="2026-01-01"),
        fact(
            "combined",
            39895000,
            "Finance Lease and Financing Arrangement Principal Payments",
            period_start="2026-01-01",
        ),
        fact("lease", 10000000, "Finance Lease Principal Payments", period_start="2026-01-01"),
    )
    source = p.sources[0].model_copy(
        update={"accession": "0001582961-26-000001", "locator": "table/row-1/column-1"}
    )
    if not scoped:
        return p.model_copy(update={"sources": (source,)})
    definition = source.model_copy(
        update={
            "source_id": "definition",
            "locator": "scope; finance/equipment principal definition",
        }
    )
    combined = p.facts[2].model_copy(update={"source_ids": ("s", "definition")})
    return p.model_copy(
        update={"sources": (source, definition), "facts": (*p.facts[:2], combined, p.facts[3])}
    )


def test_combined_principal_requires_linked_scope_and_stays_combined():
    p = combined_principal_package()
    result = calculate_cash_generation(p, "ocf", ("capex",), ("combined",), True)[1]
    assert result.status == "pass" and result.result == Decimal(40105000)
    assert result.input_fact_ids == ("ocf", "capex", "combined")
    assert (
        calculate_cash_generation(
            combined_principal_package(False), "ocf", ("capex",), ("combined",), True
        )[1].status
        == "unavailable"
    )


def test_combined_principal_plus_component_is_never_double_deducted():
    p = combined_principal_package()
    assert (
        calculate_cash_generation(p, "ocf", ("capex",), ("combined", "lease"), True)[1].status
        == "unavailable"
    )


def test_financed_equipment_bridge_preserves_gross_signed_cash_and_requires_roles():
    from tradingagents.agents.accounting_checks import check_financed_equipment_bridge

    p = package(
        fact(
            "acquisition",
            -75143000,
            "Equipment Financing Acquisition Payments",
            period_start="2026-01-01",
        ),
        fact("proceeds", 75143000, "Equipment Financing Proceeds", period_start="2026-01-01"),
    )
    source = p.sources[0].model_copy(update={"accession": "0001582961-26-000001"})
    definition = source.model_copy(
        update={
            "source_id": "definition",
            "locator": "scope; equipment financing acquisition/proceeds definition",
        }
    )
    p = p.model_copy(
        update={
            "sources": (source, definition),
            "facts": tuple(
                f.model_copy(update={"source_ids": ("s", "definition")}) for f in p.facts
            ),
        }
    )
    result = check_financed_equipment_bridge(p, "acquisition", "proceeds", {})
    assert result.status == "pass" and result.result == 0
    assert result.input_fact_ids == ("acquisition", "proceeds")
    unrelated = p.model_copy(
        update={
            "facts": (
                p.facts[0],
                p.facts[1].model_copy(update={"metric": "Long-term Debt Proceeds"}),
            )
        }
    )
    assert (
        check_financed_equipment_bridge(unrelated, "acquisition", "proceeds", {}).status
        == "unavailable"
    )
    no_scope = p.model_copy(update={"sources": (source,)})
    assert (
        check_financed_equipment_bridge(no_scope, "acquisition", "proceeds", {}).status
        == "unavailable"
    )
    for updates in (
        {"period_start": None},
        {"unit": "EUR"},
        {"value": Decimal(-75143000)},
    ):
        incompatible = p.model_copy(
            update={
                "facts": (
                    p.facts[0],
                    p.facts[1].model_copy(update=updates),
                )
            }
        )
        assert (
            check_financed_equipment_bridge(incompatible, "acquisition", "proceeds", {}).status
            == "unavailable"
        )
    mismatch = p.model_copy(
        update={
            "facts": (
                p.facts[0],
                p.facts[1].model_copy(update={"value": Decimal(75100000)}),
            )
        }
    )
    assert (
        check_financed_equipment_bridge(
            mismatch,
            "acquisition",
            "proceeds",
            {
                "acquisition": 1000,
                "proceeds": 1000,
            },
        ).status
        == "fail"
    )
