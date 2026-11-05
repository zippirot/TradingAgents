"""Source-backed cash bridges must reach the application's canonical brief."""
from decimal import Decimal

from tests.test_cash_bridge import extraction
from tests.test_filing_facts import recorded_docn_filings
from tradingagents.agents.evidence_validation import canonical_accounting_context, cash_flow_checks


def test_recorded_statement_bridges_are_wired_into_cash_checks():
    docs = recorded_docn_filings()
    extracted = extraction(docs)
    results, _, _ = cash_flow_checks(extracted.evidence, docs, extracted.rounding_quantum_by_fact,
                                    extraction=extracted)
    by_method = {r.method: r for r in results}
    expected = {'signed_investing_components_to_total_v1': '-381974000',
                'cash_flows_plus_fx_to_cash_change_v1': '411619000',
                'opening_plus_change_to_cash_including_restricted_v1': '666252000'}
    for name, value in expected.items():
        assert by_method[name].status == 'pass'
        assert by_method[name].result == Decimal(value)
    brief = canonical_accounting_context(extracted.evidence, results)
    assert '666252000' in brief and '411619000' in brief


def test_operating_percent_display_rounds_without_mutating_canonical_result():
    from datetime import date

    from tradingagents.agents.accounting_checks import Calculation
    from tradingagents.dataflows.financial_evidence import EvidencePackage

    exact = Decimal('39.871273419010')
    calculation = Calculation(method='revenue_yoy_growth_v1', status='pass', result=exact,
                              unit='percent', reason_code='calculated', message='Derived YoY')
    brief = canonical_accounting_context(EvidencePackage(cik='0001582961', as_of=date(2026, 11, 4)),
                                        [calculation])
    assert '39.87 (rounded for display)' in brief
    assert calculation.result == exact
