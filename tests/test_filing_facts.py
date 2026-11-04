"""Synthetic table fixtures, not recorded SEC/live evidence."""

from datetime import date
from decimal import Decimal

import pytest

from tradingagents.dataflows.filing_facts import (
    FilingCellSelection,
    discover_filing_cells,
    verify_filing_cells,
)
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)


def package(text, section="Statement of changes in stockholders equity"):
    filing = FilingReference(
        cik="0001582961",
        accession="0001582961-26-000001",
        form="10-Q",
        filed_date="2026-08-05",
        report_date="2026-06-30",
        primary_document="filing.htm",
        items="",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000158296126000001/filing.htm",
    )
    doc = FilingDocument(
        source_id="doc",
        filing=filing,
        url=filing.url,
        retrieved_at="2026-11-04T12:00:00Z",
        content_hash="a" * 64,
        blocks=(SourceBlock(locator="table-1", section=section, text=text),),
    )
    return DisclosurePackage(cik=filing.cik, as_of="2026-10-19", documents=(doc,))


EQUITY = """Amounts in thousands of US dollars. Six months ended June 30, 2026 ;
Movement | Common Stock | Total Stockholders' Equity ;
Balance at December 31, 2025 | 2 | 100000 ;
Issuance of common stock, net of issuance costs | 1 | 887888 ;
Net income | 0 | 30000 ;
Share-based compensation | 0 | 5000 ;
Repurchases and retirement of common stock | 0 | (37335) ;
Balance at June 30, 2026 | 3 | 985553"""


def test_valid_equity_table_retains_signed_values_periods_and_complete_coverage():
    data = package(EQUITY)
    selections = discover_filing_cells(data)
    result = verify_filing_cells(data, selections)
    facts = {f.metric: f for f in result.evidence.facts if f.period_start}
    issuance = facts["Equity Common Stock Issuance Value"]
    assert issuance.value == Decimal("887888000")
    assert issuance.period_start == date(2026, 1, 1)
    assert issuance.period_end == date(2026, 6, 30)
    assert facts["Equity Stock Repurchases/Retirements"].value == Decimal("-37335000")
    assert result.rounding_quantum_by_fact[issuance.fact_id] == Decimal("1000")
    assert result.equity_coverage[0].complete
    assert result.equity_coverage[0].signed_components
    assert all(sign == 1 for _, sign in result.equity_coverage[0].signed_components)
    assert all("table-1/row-" in f.locator for f in result.evidence.facts)
    assert all(s.content_hash == "a" * 64 for s in result.evidence.sources)


def test_model_cannot_select_par_value_as_total_equity():
    data = package(EQUITY)
    selection = FilingCellSelection(
        source_id="doc",
        locator="table-1",
        metric="Equity Common Stock Issuance Value",
        row_index=3,
        column_index=1,
    )
    result = verify_filing_cells(data, [selection])
    assert not result.evidence.facts
    assert any("total-equity column" in gap for gap in result.gaps)


def test_missing_selected_movement_prevents_coverage():
    data = package(EQUITY)
    selections = [s for s in discover_filing_cells(data) if s.metric != "Net Income"]
    result = verify_filing_cells(data, selections)
    assert not result.equity_coverage[0].complete
    assert 4 in result.equity_coverage[0].omitted_rows


def test_unrecognized_nonzero_movement_prevents_coverage():
    data = package(EQUITY.replace("Net income", "Mysterious transfer"))
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.equity_coverage[0].complete
    assert 4 in result.equity_coverage[0].unmapped_rows


@pytest.mark.parametrize(
    "replacement", ["Amounts presented below.", "Amounts in thousands or millions of US dollars."]
)
def test_missing_or_ambiguous_source_scale_is_unavailable(replacement):
    data = package(EQUITY.replace("Amounts in thousands of US dollars.", replacement))
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert result.gaps


def test_cash_flow_proceeds_cannot_be_relabelled_equity_issuance():
    data = package(EQUITY, section="Statement of cash flows")
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not any(f.metric == "Equity Common Stock Issuance Value" for f in result.evidence.facts)
    assert result.gaps


def test_equipment_obligations_dated_columns_and_decimal_precision():
    data = package(
        "Amounts in millions of US dollars ; Obligation | June 30, 2026 | December 31, 2025 ; Finance lease and equipment financing obligations | 577.72 | 499.20",
        section="Finance leases and equipment financing",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert len(result.evidence.facts) == 2
    current = next(f for f in result.evidence.facts if f.period_end == date(2026, 6, 30))
    assert current.metric == "Finance Lease and Equipment Obligations"
    assert current.value == Decimal("577720000")
    assert result.rounding_quantum_by_fact[current.fact_id] == Decimal("10000")
    assert current.period_start is None


def test_generic_lease_liability_cannot_be_called_equipment_obligations():
    data = package(
        "US dollars in thousands ; Obligation | June 30, 2026 ; Lease liabilities | 577720",
        section="Leases",
    )
    selection = FilingCellSelection(
        source_id="doc",
        locator="table-1",
        metric="Equipment Financing Obligations",
        row_index=2,
        column_index=1,
    )
    result = verify_filing_cells(data, [selection])
    assert not result.evidence.facts
    assert any("label" in gap for gap in result.gaps)


def test_ambiguous_multirow_header_is_unavailable():
    data = package(
        "US dollars in thousands ; June 30, 2026 | December 31, 2025 ; Obligation | Current | Noncurrent | Current | Noncurrent ; Equipment financing obligations | 1 | 2 | 3 | 4",
        section="Financing",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert result.gaps


def test_future_period_or_issuer_mismatch_never_produces_fact():
    data = package(EQUITY.replace("June 30, 2026", "June 30, 2027"))
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert result.gaps
    mismatch = package(EQUITY).model_copy(update={"cik": "0000320193"})
    result = verify_filing_cells(mismatch, discover_filing_cells(mismatch))
    assert not result.evidence.facts
    assert any("issuer" in gap for gap in result.gaps)


def test_selection_cannot_supply_scale_or_numeric_value():
    with pytest.raises(ValueError):
        FilingCellSelection(
            source_id="doc",
            locator="table-1",
            metric="Equity Common Stock Issuance Value",
            row_index=3,
            column_index=2,
            value=1,
            scale=1000,
        )


def test_dashes_missing_values_do_not_become_zero_or_complete():
    data = package(EQUITY.replace("Net income | 0 | 30000", "Net income | 0 | —"))
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not any(f.metric == "Net Income" for f in result.evidence.facts)
    assert not result.equity_coverage[0].complete


def test_explicit_zero_unknown_movement_does_not_create_material_gap():
    data = package(EQUITY.replace("Net income | 0 | 30000", "Mysterious transfer | 0 | 0"))
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert result.equity_coverage[0].complete


def test_trailing_zeroes_do_not_invent_coarser_source_precision():
    data = package(EQUITY)
    result = verify_filing_cells(data, discover_filing_cells(data))
    opening = next(
        f
        for f in result.evidence.facts
        if f.metric == "Stockholders Equity" and f.period_end == date(2025, 12, 31)
    )
    assert opening.value == Decimal("100000000")
    assert result.rounding_quantum_by_fact[opening.fact_id] == Decimal("1000")


def test_mixed_currency_heading_is_not_usd_evidence():
    data = package(EQUITY.replace("thousands of US dollars", "thousands of US dollars and EUR"))
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert result.gaps


def test_numeric_scaling_is_exact_beyond_default_decimal_context():
    data = package(
        "Amounts in millions of US dollars ; Obligation | June 30, 2026 ; Equipment financing obligations | 12345678901234567890123.456789",
        section="Financing",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert result.evidence.facts[0].value == Decimal("12345678901234567890123456789")


def test_closing_before_opening_cannot_prove_table_coverage():
    data = package(
        EQUITY.replace("Balance at December 31, 2025", "Balance at SWAP")
        .replace("Balance at June 30, 2026", "Balance at December 31, 2025")
        .replace("Balance at SWAP", "Balance at June 30, 2026")
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.equity_coverage[0].complete


def test_source_gaps_cannot_prove_complete_table():
    data = package(EQUITY)
    doc = data.documents[0].model_copy(
        update={
            "gaps": ("Document text limit reached; section truncated",),
            "blocks": (data.documents[0].blocks[0].model_copy(update={"truncated": True}),),
        }
    )
    data = data.model_copy(update={"documents": (doc,)})
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.equity_coverage[0].complete


def test_duplicate_source_identifier_is_unavailable():
    data = package(EQUITY)
    data = data.model_copy(update={"documents": data.documents * 2})
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert any("duplicate" in g for g in result.gaps)


def test_current_liability_section_is_not_total_equipment_obligations():
    data = package(
        "Amounts in thousands of US dollars ; Obligation | June 30, 2026 ; Equipment financing obligations | 100",
        section="Current liabilities",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert result.gaps


def test_positive_repurchases_in_signed_equity_statement_are_not_sign_flipped():
    data = package(EQUITY.replace("(37335)", "37335"))
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not any(
        f.metric == "Equity Stock Repurchases/Retirements" for f in result.evidence.facts
    )
    assert not result.equity_coverage[0].complete


@pytest.mark.parametrize("label", ["Total borrowings"])
def test_total_borrowings_requires_explicit_total_label_and_debt_context(label):
    data = package(
        f"Amounts in thousands of US dollars ; Debt | June 30, 2026 ; {label} | 1500000",
        section="Debt and borrowings",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert len(result.evidence.facts) == 1
    fact = result.evidence.facts[0]
    assert fact.metric == "Total Borrowings"
    assert fact.value == Decimal("1500000000")
    assert fact.period_end == date(2026, 6, 30)


@pytest.mark.parametrize(
    "section", ["Equity", "Debt securities held for investment", "Long-term debt"]
)
def test_total_debt_in_wrong_or_partial_source_context_is_unavailable(section):
    data = package(
        "Amounts in thousands of US dollars ; Debt | June 30, 2026 ; Total borrowings | 1500000",
        section=section,
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert result.gaps


def test_long_term_debt_row_is_not_total_borrowings():
    data = package(
        "Amounts in thousands of US dollars ; Debt | June 30, 2026 ; Long-term debt | 1500000",
        section="Debt and borrowings",
    )
    selection = FilingCellSelection(
        source_id="doc", locator="table-1", metric="Total Borrowings", row_index=2, column_index=1
    )
    result = verify_filing_cells(data, [selection])
    assert not result.evidence.facts
    assert result.gaps


def test_realstyle_html_multilevel_header_remains_ambiguous():
    from tradingagents.dataflows.vendors.sec_documents import extract_sections

    html = """<h2>Debt and borrowings</h2><table><caption>Amounts in thousands of US dollars</caption>
    <tr><th></th><th colspan="2">June 30, 2026</th><th colspan="2">December 31, 2025</th></tr>
    <tr><th>Debt</th><th>Current</th><th>Noncurrent</th><th>Current</th><th>Noncurrent</th></tr>
    <tr><td><p>Total borrowings</p></td><td><p>10</p></td><td><p>1500</p></td><td><p>20</p></td><td><p>1400</p></td></tr></table>"""
    blocks, _, _ = extract_sections(html)
    data = package("")
    document = data.documents[0].model_copy(update={"blocks": tuple(blocks)})
    data = data.model_copy(update={"documents": (document,)})
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert any("aligned dated" in gap for gap in result.gaps)


@pytest.mark.parametrize(
    "label",
    [
        "Principal payments on equipment financing obligations",
        "Repayments of equipment financing obligations",
    ],
)
def test_equipment_principal_cashflow_has_source_duration_and_signed_amount(label):
    data = package(
        f"Amounts in thousands of US dollars. Six months ended ; Cash flow | June 30, 2026 | June 30, 2025 ; {label} | (1234) | (1000)",
        section="Cash flows from financing activities",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert len(result.evidence.facts) == 2
    current = next(f for f in result.evidence.facts if f.period_end == date(2026, 6, 30))
    assert current.metric == "Equipment Financing Principal Payments"
    assert current.period_start == date(2026, 1, 1)
    assert current.value == Decimal("-1234000")
    assert result.rounding_quantum_by_fact[current.fact_id] == Decimal("1000")
    prior = next(f for f in result.evidence.facts if f.period_end == date(2025, 6, 30))
    assert prior.period_start == date(2025, 1, 1)


def test_generic_acquisition_payment_is_not_equipment_principal():
    data = package(
        "Amounts in thousands of US dollars. Six months ended ; Cash flow | June 30, 2026 ; Payments to acquire equipment on lease | (1234)",
        section="Cash flows from financing activities",
    )
    selected = FilingCellSelection(
        source_id="doc",
        locator="table-1",
        metric="Equipment Financing Principal Payments",
        row_index=2,
        column_index=1,
    )
    result = verify_filing_cells(data, [selected])
    assert not result.evidence.facts
    assert any("label" in g for g in result.gaps)


@pytest.mark.parametrize(
    "caption",
    [
        "Amounts in thousands of US dollars.",
        "Amounts in thousands of US dollars. Three months ended and six months ended",
        "Amounts in thousands of US dollars. Six months ended December 31, 2025",
    ],
)
def test_equipment_principal_missing_mixed_or_conflicting_duration_is_unavailable(caption):
    data = package(
        f"{caption} ; Cash flow | June 30, 2026 ; Repayments of equipment financing obligations | (1234)",
        section="Cash flows from financing activities",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert any("duration" in g for g in result.gaps)


def test_equipment_principal_requires_cashflow_or_financing_source_context():
    data = package(
        "Amounts in thousands of US dollars. Six months ended ; Cash flow | June 30, 2026 ; Repayments of equipment financing obligations | (1234)",
        section="Statement of stockholders equity",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert result.gaps


@pytest.mark.parametrize("label", ["Total debt", "Total debt outstanding"])
def test_generic_total_debt_cannot_establish_disjoint_borrowings(label):
    data = package(
        f"Amounts in thousands of US dollars ; Debt | June 30, 2026 ; {label} | 1500000",
        section="Debt and borrowings",
    )
    selection = FilingCellSelection(
        source_id="doc", locator="table-1", metric="Total Borrowings", row_index=2, column_index=1
    )
    result = verify_filing_cells(data, [selection])
    assert not result.evidence.facts
    assert any("label" in gap for gap in result.gaps)


@pytest.mark.parametrize(
    "footnote",
    [
        "Includes finance lease liabilities.",
        "Equipment financing obligations are included in the total.",
        "Borrowings include operating leases and other instruments.",
    ],
)
def test_after_total_footnote_prevents_unproved_disjoint_borrowings(footnote):
    data = package(
        f"Amounts in thousands of US dollars ; Debt | June 30, 2026 ; Total borrowings | 1500000 ; {footnote}",
        section="Debt and borrowings",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert any("perimeter" in gap for gap in result.gaps)


ADJUSTED = """Amounts in thousands of US dollars. Six months ended ;
Measure | June 30, 2026 | June 30, 2025 ;
Net income | 100 | 80 ;
Share-based compensation | 20 | 10 ;
Acquisition costs | 5 | 2 ;
Tax adjustment | (3) | (2) ;
Adjusted net income | 122 | 90"""


def test_adjusted_net_income_table_has_source_basis_and_complete_arithmetic():
    from tradingagents.agents.accounting_checks import check_adjusted_bridge

    data = package(ADJUSTED, section="Non-GAAP reconciliation of net income to adjusted net income")
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert len(result.adjusted_coverage) == 2
    current = next(c for c in result.adjusted_coverage if c.period_end == date(2026, 6, 30))
    assert current.complete
    by_id = {f.fact_id: f for f in result.evidence.facts}
    assert by_id[current.gaap_fact_id].basis == "US-GAAP"
    assert by_id[current.adjusted_fact_id].basis == "management-adjusted"
    assert all(
        by_id[fact_id].basis == "management-adjusted" and sign == 1
        for fact_id, sign in current.signed_components
    )
    assert any(by_id[fact_id].value == Decimal("-3000") for fact_id, _ in current.signed_components)
    check = check_adjusted_bridge(
        result.evidence,
        current.gaap_fact_id,
        current.adjusted_fact_id,
        current.signed_components,
        current.complete,
        result.rounding_quantum_by_fact,
    )
    assert check.status == "pass" and check.result == Decimal("122000")


def test_omitted_adjustment_row_prevents_complete_reconciliation():
    data = package(ADJUSTED, section="Non-GAAP reconciliation")
    selected = [
        s
        for s in discover_filing_cells(data)
        if s.metric != "Management Acquisition Cost Adjustment"
    ]
    result = verify_filing_cells(data, selected)
    assert result.adjusted_coverage
    assert all(not c.complete and 4 in c.omitted_rows for c in result.adjusted_coverage)


def test_unmapped_adjustment_row_prevents_complete_reconciliation():
    data = package(
        ADJUSTED.replace("Acquisition costs", "Strategic value enhancement"),
        section="Non-GAAP reconciliation",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert all(not c.complete and 4 in c.unmapped_rows for c in result.adjusted_coverage)


def test_adjustment_alias_does_not_override_equity_statement_role():
    data = package(EQUITY)
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert any(f.metric == "Equity Share-based Compensation" for f in result.evidence.facts)
    assert not result.adjusted_coverage
    assert not any(f.metric.startswith("Management") for f in result.evidence.facts)


@pytest.mark.parametrize(
    "changed",
    [
        ADJUSTED.replace("Six months ended", "Three months ended and six months ended"),
        ADJUSTED.replace("US dollars", "EUR"),
        ADJUSTED.replace("Measure | June 30, 2026 | June 30, 2025", "Measure | 2026 | 2025"),
    ],
)
def test_adjusted_wrong_period_or_unit_cannot_complete(changed):
    data = package(changed, section="Non-GAAP reconciliation")
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert result.adjusted_coverage and all(not c.complete for c in result.adjusted_coverage)
    assert result.gaps


def test_ambiguous_gaap_base_is_not_chosen_by_model():
    data = package(
        ADJUSTED.replace(
            "Net income | 100 | 80", "Net income | 100 | 80 ; Operating income | 120 | 90"
        ),
        section="Non-GAAP reconciliation",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert all(not c.complete for c in result.adjusted_coverage)
    assert any("base" in gap for gap in result.gaps)


def test_adjusted_measure_requires_reconciliation_context():
    data = package(ADJUSTED, section="Performance commentary")
    selected = FilingCellSelection(
        source_id="doc",
        locator="table-1",
        metric="Adjusted Net Income",
        row_index=6,
        column_index=1,
    )
    result = verify_filing_cells(data, [selected])
    assert not result.evidence.facts
    assert result.gaps


def test_known_zero_adjustment_may_be_omitted_without_hiding_unknown_nonzero():
    data = package(
        ADJUSTED.replace("Acquisition costs | 5 | 2", "Acquisition costs | 0 | 0"),
        section="Non-GAAP reconciliation",
    )
    selected = [
        s
        for s in discover_filing_cells(data)
        if s.metric != "Management Acquisition Cost Adjustment"
    ]
    result = verify_filing_cells(data, selected)
    assert all(c.complete for c in result.adjusted_coverage)


@pytest.mark.parametrize(
    "table,section,kind",
    [
        (EQUITY, "Statement of changes in stockholders equity", "equity_coverage"),
        (ADJUSTED, "Non-GAAP reconciliation", "adjusted_coverage"),
    ],
)
def test_intact_table_can_complete_with_unrelated_omitted_sections(table, section, kind):
    data = package(table, section=section)
    document = data.documents[0].model_copy(
        update={"gaps": ("Document text limit reached; selected sections omit other content",)}
    )
    data = data.model_copy(update={"documents": (document,)})
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert all(c.complete for c in getattr(result, kind))
    assert any("omit other content" in gap for gap in result.gaps)


@pytest.mark.parametrize(
    "table,section,kind",
    [
        (EQUITY, "Statement of changes in stockholders equity", "equity_coverage"),
        (ADJUSTED, "Non-GAAP reconciliation", "adjusted_coverage"),
    ],
)
def test_actual_partial_table_cannot_supply_cells_or_complete(table, section, kind):
    data = package(table, section=section)
    document = data.documents[0].model_copy(
        update={"blocks": (data.documents[0].blocks[0].model_copy(update={"truncated": True}),)}
    )
    data = data.model_copy(update={"documents": (document,)})
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert not result.evidence.facts
    assert all(not c.complete for c in getattr(result, kind))
    assert any("truncated" in gap for gap in result.gaps)


def test_adjusted_ebitda_uses_supported_gaap_pair_and_source_adjustments():
    from tradingagents.agents.accounting_checks import check_adjusted_bridge

    text = """Amounts in thousands of US dollars. Three months ended ; Measure | June 30, 2026 ;
    Net income | 100 ; Depreciation and amortization | 40 ; Interest expense | 5 ;
    Income tax expense | 10 ; Adjusted EBITDA | 155"""
    data = package(text, section="Reconciliation of net income to adjusted EBITDA")
    result = verify_filing_cells(data, discover_filing_cells(data))
    coverage = result.adjusted_coverage[0]
    assert coverage.complete and coverage.period_start == date(2026, 4, 1)
    check = check_adjusted_bridge(
        result.evidence,
        coverage.gaap_fact_id,
        coverage.adjusted_fact_id,
        coverage.signed_components,
        coverage.complete,
        result.rounding_quantum_by_fact,
    )
    assert check.status == "pass"


def test_adjusted_unsupported_gaap_pair_cannot_complete():
    data = package(
        ADJUSTED.replace("Net income | 100 | 80", "Operating cash flow | 100 | 80"),
        section="Non-GAAP reconciliation",
    )
    result = verify_filing_cells(data, discover_filing_cells(data))
    assert all(not c.complete for c in result.adjusted_coverage)
    assert any("Unsupported GAAP" in gap for gap in result.gaps)
