"""Cash bridges use the recorded statement's signed, complete source rows."""
from datetime import date
from decimal import Decimal

from tests.test_filing_facts import recorded_docn_filings
from tradingagents.agents import accounting_checks as checks
from tradingagents.dataflows.filing_facts import discover_filing_cells, verify_filing_cells


def extraction(data=None):
    data = data or recorded_docn_filings()
    return verify_filing_cells(data, discover_filing_cells(data))


def current(result, metric, end=date(2026, 9, 30)):
    return next(f for f in result.evidence.facts if f.metric == metric and f.period_end == end)


def test_recorded_investing_components_preserve_gross_financed_assets_and_zero_sale():
    result = extraction()
    coverage = next(c for c in result.investing_coverage if c.period_end == date(2026, 9, 30))
    assert coverage.complete, coverage.gaps
    amounts = {f.metric: f.value for f in result.evidence.facts if f.fact_id in coverage.component_fact_ids}
    assert amounts == {
        'Cash-flow Property and Equipment Payments': Decimal('-105124000'),
        'Cash-flow Software Development Payments': Decimal('-19279000'),
        'Equipment Financing Acquisition Payments': Decimal('-75143000'),
        'Intangible Asset Acquisition Payments': Decimal('-754000'),
        'Business Acquisition Payments': Decimal('-4042000'),
        'Financial Investment Purchases': Decimal('-177632000'),
        'Property and Equipment Sale Proceeds': Decimal(0),
    }
    outcome = checks.check_investing_cash_bridge(result.evidence, coverage.total_fact_id,
        coverage.component_fact_ids, coverage.complete, result.rounding_quantum_by_fact)
    assert outcome.status == 'pass' and outcome.result == Decimal('-381974000')
    assert outcome.residual == 0


def test_recorded_cash_change_and_restricted_cash_balance_reconcile():
    result = extraction()
    metrics = ['Operating Cash Flow', 'Investing Cash Flow', 'Financing Cash Flow',
               'Exchange Effect on Cash Including Restricted Cash', 'Change in Cash Including Restricted Cash']
    ids = [current(result, m).fact_id for m in metrics]
    opening = current(result, 'Cash Including Restricted Cash', date(2025, 12, 31))
    closing = current(result, 'Cash Including Restricted Cash')
    outcomes = checks.check_cash_balance_bridge(result.evidence, *ids, opening.fact_id,
                                                closing.fact_id, result.rounding_quantum_by_fact)
    assert [o.status for o in outcomes] == ['pass', 'pass']
    assert [o.result for o in outcomes] == [Decimal('411619000'), Decimal('666252000')]
    assert closing.value != Decimal('666096000')


def test_missing_investing_row_is_not_assumed_zero_or_residual_capex():
    data = recorded_docn_filings()
    doc = data.documents[0]
    changed = doc.model_copy(update={'blocks': tuple(b.model_copy(update={'text': b.text.replace(
        'Purchase of marketable securities', 'Unclassified investment transaction')}) for b in doc.blocks)})
    result = extraction(data.model_copy(update={'documents': (changed,)}))
    coverage = next(c for c in result.investing_coverage if c.period_end == date(2026, 9, 30))
    assert not coverage.complete and coverage.unmapped_rows
    outcome = checks.check_investing_cash_bridge(result.evidence, coverage.total_fact_id,
        coverage.component_fact_ids, coverage.complete, result.rounding_quantum_by_fact)
    assert outcome.status == 'unavailable' and outcome.result is None


def test_acquisition_adjusted_cash_measure_uses_explicit_payments_not_total_investing():
    result = extraction()
    # Convert the two signed source rows to explicitly derived gross spending;
    # the application may also use compatible reported companyfacts magnitudes.
    derived = []
    for metric, normalized in [('Cash-flow Property and Equipment Payments', 'Capital Expenditure'),
                               ('Cash-flow Software Development Payments', 'Software Development Payments'),
                               ('Finance Lease and Financing Arrangement Principal Payments',
                                'Finance Lease and Financing Arrangement Principal Payments')]:
        original = current(result, metric)
        derived.append(original.model_copy(update={'fact_id': original.fact_id + '-magnitude',
            'metric': normalized, 'value': abs(original.value), 'origin': 'derived',
            'input_fact_ids': (original.fact_id,), 'formula_id': 'explicit_cash_outflow_magnitude'}))
    package = result.evidence.model_copy(update={'facts': (*result.evidence.facts, *derived)})
    acquisitions = [current(result, m).fact_id for m in
                    ['Intangible Asset Acquisition Payments', 'Business Acquisition Payments']]
    base = checks.calculate_cash_generation(package, current(result, 'Operating Cash Flow').fact_id,
                                             [f.fact_id for f in derived[:2]], [derived[2].fact_id], True)[1]
    assert base.result == Decimal('153818000')
    outcome = checks.calculate_cash_after_acquisitions(package, current(result, 'Operating Cash Flow').fact_id,
        [f.fact_id for f in derived[:2]], [derived[2].fact_id], acquisitions, True)
    assert outcome.status == 'pass' and outcome.result == Decimal('149022000')
    bad = checks.calculate_cash_after_acquisitions(package, current(result, 'Operating Cash Flow').fact_id,
        [f.fact_id for f in derived[:2]], [derived[2].fact_id],
        [current(result, 'Financial Investment Purchases').fact_id], True)
    assert bad.status == 'unavailable'
    incomplete = checks.calculate_cash_after_acquisitions(package, current(result, 'Operating Cash Flow').fact_id,
        [f.fact_id for f in derived[:2]], [derived[2].fact_id], acquisitions[:1], True)
    assert incomplete.status == 'unavailable'


def test_investing_bridge_rejects_period_unit_sign_and_duplicate_categories():
    result = extraction()
    coverage = next(c for c in result.investing_coverage if c.period_end == date(2026, 9, 30))
    original = current(result, 'Financial Investment Purchases')
    for update in [{'unit': 'EUR'}, {'period_start': date(2026, 4, 1)}, {'value': abs(original.value)},
                   {'basis': 'management-adjusted'}, {'metric': 'Cash-flow Property and Equipment Payments'}]:
        package = result.evidence.model_copy(update={'facts': tuple(f.model_copy(update=update)
            if f.fact_id == original.fact_id else f for f in result.evidence.facts)})
        outcome = checks.check_investing_cash_bridge(package, coverage.total_fact_id,
            coverage.component_fact_ids, True, result.rounding_quantum_by_fact)
        assert outcome.status == 'unavailable', update


def test_cash_balance_rejects_unrestricted_cash_substitution_and_wrong_opening_date():
    result = extraction()
    metrics = ['Operating Cash Flow', 'Investing Cash Flow', 'Financing Cash Flow',
               'Exchange Effect on Cash Including Restricted Cash', 'Change in Cash Including Restricted Cash']
    ids = [current(result, m).fact_id for m in metrics]
    opening = current(result, 'Cash Including Restricted Cash', date(2025, 12, 31))
    closing = current(result, 'Cash Including Restricted Cash')
    for original, update in [(closing, {'metric': 'Cash and Equivalents', 'value': Decimal('666096000')}),
                             (opening, {'period_end': date(2026, 1, 1)})]:
        package = result.evidence.model_copy(update={'facts': tuple(f.model_copy(update=update)
            if f.fact_id == original.fact_id else f for f in result.evidence.facts)})
        outcomes = checks.check_cash_balance_bridge(package, *ids, opening.fact_id,
                                                    closing.fact_id, result.rounding_quantum_by_fact)
        assert outcomes[0].status == 'pass' and outcomes[1].status == 'unavailable'


def test_explicit_zero_marker_is_not_general_missing_value_or_non_cash_permission():
    data = recorded_docn_filings()
    doc = data.documents[0]
    # Removing the printed zero marker must not silently substitute a zero.
    changed = doc.model_copy(update={'blocks': tuple(b.model_copy(update={'text': b.text.replace(
        'Proceeds from sale of equipment | —', 'Proceeds from sale of equipment | unknown')}) for b in doc.blocks)})
    result = extraction(data.model_copy(update={'documents': (changed,)}))
    coverage = next(c for c in result.investing_coverage if c.period_end == date(2026, 9, 30))
    assert not coverage.complete and coverage.omitted_rows


def test_cash_statement_integration_selects_same_period_reported_source_rows():
    result = extraction()
    outcomes = checks.cash_statement_reconciliations(result.evidence, result,
        result.rounding_quantum_by_fact, start=date(2026, 1, 1), end=date(2026, 9, 30))
    assert [o.status for o in outcomes] == ['pass', 'pass', 'pass']
    assert [o.result for o in outcomes] == [Decimal('-381974000'), Decimal('411619000'), Decimal('666252000')]


def test_cash_statement_integration_missing_total_or_ambiguous_coverage_stays_visible():
    result = extraction()
    total = current(result, 'Investing Cash Flow')
    package = result.evidence.model_copy(update={'facts': tuple(f for f in result.evidence.facts
                                                               if f.fact_id != total.fact_id)})
    outcomes = checks.cash_statement_reconciliations(package, result, result.rounding_quantum_by_fact,
        start=date(2026, 1, 1), end=date(2026, 9, 30))
    assert outcomes[0].status == outcomes[1].status == 'unavailable'
    assert outcomes[2].status == 'pass'
    coverage = next(c for c in result.investing_coverage if c.period_end == date(2026, 9, 30))
    duplicate = result.model_copy(update={'investing_coverage': (coverage, coverage)})
    outcomes = checks.cash_statement_reconciliations(result.evidence, duplicate,
        result.rounding_quantum_by_fact, start=date(2026, 1, 1), end=date(2026, 9, 30))
    assert all(o.status == 'unavailable' and 'coverage' in o.message for o in outcomes)


def test_cash_statement_integration_reports_absent_extraction():
    result = extraction()
    outcomes = checks.cash_statement_reconciliations(result.evidence, None, {}, start=None, end=None)
    assert len(outcomes) == 3 and all(o.status == 'unavailable' for o in outcomes)


def test_real_multi_document_package_prioritizes_current_statement_within_cell_limit():
    import json
    from pathlib import Path

    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    raw = json.loads((Path(__file__).parent / 'fixtures/docn_2026q3/live02_filing_package.json').read_text())
    data = DisclosurePackage.model_validate(raw['disclosures'])
    # Original live package order starts with old annual material and a long
    # earnings release; the bounded selector must still reach current 10-Q cash.
    selections = discover_filing_cells(data)
    assert len(selections) <= 128
    result = verify_filing_cells(data, selections)
    coverage = next(c for c in result.investing_coverage
                    if c.period_end == date(2026, 9, 30) and c.complete)
    outcomes = checks.cash_statement_reconciliations(result.evidence, result,
        result.rounding_quantum_by_fact, start=coverage.period_start, end=coverage.period_end)
    assert [o.status for o in outcomes] == ['pass', 'pass', 'pass']
    assert [o.result for o in outcomes] == [Decimal('-381974000'), Decimal('411619000'), Decimal('666252000')]
    assert any('selection limit reached' in gap.lower() for gap in result.gaps)
