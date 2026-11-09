"""Full-corpus filing facts are delivered before analyst reasoning and survive export."""
from copy import deepcopy

import pytest


def source_state():
    from tests.test_instrument_terms import package
    from tradingagents.dataflows.filing_search import corpus_hash
    corpus = package()
    return {
        'company_of_interest': 'DOCN', 'trade_date': '2026-11-07', 'asset_type': 'stock',
        'issuer_identity': {'cik': corpus.cik},
        'document_sources': {
            'schema_version': 1, 'ticker': 'DOCN', 'as_of': '2026-11-07',
            'asset_type': 'stock', 'analysis_clock': {}, 'status': 'ready',
            'cik': corpus.cik, 'corpus': corpus.model_dump(mode='json'),
            'corpus_hash': corpus_hash(corpus), 'reason': '',
        },
    }


def test_full_corpus_note_is_in_preanalyst_brief_and_report_export(tmp_path):
    import json

    from tradingagents.agents.context import build_shared_source_brief
    from tradingagents.agents.filing_terms import prepare_filing_terms
    from tradingagents.reporting import evidence_appendix, evidence_snapshot
    state = source_state()
    state.update(prepare_filing_terms(state))
    state['shared_source_brief'] = build_shared_source_brief(state)
    assert '312322 USD thousands' in state['shared_source_brief']
    assert '178.51 USD/share' in state['shared_source_brief']
    assert 'block-430' in state['shared_source_brief']
    assert 'not a completed transaction' in state['shared_source_brief']
    snapshot = evidence_snapshot(state)
    path = tmp_path / 'evidence.json'
    path.write_text(json.dumps(snapshot))
    reopened = json.loads(path.read_text())
    assert reopened['filing_terms_evidence'] == state['filing_terms_evidence']
    assert '312322 USD thousands' in evidence_appendix({**state, **reopened})


@pytest.mark.parametrize('fault', ['issuer', 'cutoff', 'source_hash', 'record'])
def test_changed_source_or_retained_record_cannot_render_as_filing_terms(fault):
    from tradingagents.agents.filing_terms import prepare_filing_terms, render_filing_terms
    state = source_state()
    state.update(prepare_filing_terms(state))
    state = deepcopy(state)
    if fault == 'issuer':
        state['issuer_identity']['cik'] = '0000320193'
    elif fault == 'cutoff':
        state['trade_date'] = '2026-11-06'
    elif fault == 'source_hash':
        state['document_sources']['corpus']['documents'][0]['content_hash'] = 'b' * 64
    else:
        state['filing_terms_evidence']['notes'][0]['principal_outstanding'] = '1'
    with pytest.raises(ValueError):
        render_filing_terms(state)


def test_legacy_export_without_new_records_remains_available():
    from tradingagents.agents.filing_terms import render_filing_terms
    assert render_filing_terms({}) == ''


def test_acquisition_keeps_liquidity_canonical_source_identity_and_shared_row(monkeypatch):
    from tests.test_sec_edgar import _current_securities_inputs
    from tradingagents.agents import kpi_comparisons, transcript_access, valuation_reference_flow
    from tradingagents.agents.evidence_validation import (
        create_evidence_gate,
        create_source_acquisition,
    )
    from tradingagents.dataflows.config import run_config
    from tradingagents.dataflows.filing_search import corpus_hash
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar
    from tradingagents.dataflows.vendors.yahoo import price_observation
    from tradingagents.default_config import DEFAULT_CONFIG

    package, corpus = _current_securities_inputs(monkeypatch)
    state = {'company_of_interest': 'DOCN', 'trade_date': str(package.as_of),
             'asset_type': 'stock', 'issuer_identity': {'cik': package.cik},
             'document_sources': {
                 'schema_version': 1, 'ticker': 'DOCN', 'as_of': str(package.as_of),
                 'asset_type': 'stock', 'analysis_clock': {}, 'status': 'ready',
                 'cik': corpus.cik, 'corpus': corpus.model_dump(mode='json'),
                 'corpus_hash': corpus_hash(corpus), 'reason': '',
             }}
    monkeypatch.setattr(sec_edgar, 'get_financial_evidence', lambda *args: package)
    monkeypatch.setattr(sec_documents, 'get_filing_evidence', lambda *args: corpus)
    monkeypatch.setattr(price_observation, 'get_price_observation', lambda *args: {'status': 'unavailable', 'reason': 'Offline'})
    monkeypatch.setattr(kpi_comparisons, 'retrieve_rpo_comparison', lambda *args: None)
    monkeypatch.setattr(transcript_access, 'prepare_transcript_sources', lambda *args: {})
    monkeypatch.setattr(valuation_reference_flow, 'acquire_reference_inputs', lambda *args: {})
    with run_config(DEFAULT_CONFIG):
        update = create_source_acquisition(['fundamentals'])(state)
    check = next(c for c in update['evidence_acquisition']['source_checks'] if c['code'] == 'source_integrity')
    assert check['status'] == 'pass', check
    assert '844741000 USD' in update['shared_source_brief']
    state.update(update)
    state['fundamentals_report'] = 'No model claims supplied'
    gate = create_evidence_gate(['fundamentals'])(state)
    assert next(c for c in gate['financial_calculations']
                if c['method'] == 'cash_plus_marketable_securities_v1')['result'] == '844741000'


def test_current_securities_cannot_replace_valuation_cash():
    from decimal import Decimal

    from tests.test_valuation import ev_request, evidence
    from tradingagents.agents.valuation import validate_target
    from tradingagents.dataflows.financial_evidence import FinancialFact

    package = evidence()
    baseline = validate_target(ev_request(), package)
    securities = FinancialFact(fact_id='securities', metric='Current Marketable Securities',
        value=9000, unit='USD', cik=package.cik, period_end='2026-06-30',
        as_of=package.as_of, source_ids=('s',), locator='synthetic/current-securities')
    augmented = package.model_copy(update={'facts': (*package.facts, securities)})
    assert validate_target(ev_request(), augmented) == baseline
    substituted = {**ev_request(), 'cash_fact_id': 'securities'}
    result = validate_target(substituted, augmented)
    assert result.status == 'unsupported' and 'cash' in result.reasons[0]
    assert baseline.target == Decimal(35)


def test_liquidity_duration_security_is_rejected_by_existing_period_guard():
    from tests.test_valuation import evidence
    from tradingagents.agents.accounting_checks import check_cash_plus_marketable_securities
    package = evidence()
    security = package.facts[2].model_copy(update={
        'fact_id': 'duration-security', 'metric': 'Current Marketable Securities',
        'period_start': package.facts[0].period_start,
    })
    result = check_cash_plus_marketable_securities(package.model_copy(update={
        'facts': (*package.facts, security)}))
    assert result.status == 'unavailable' and result.reason_code == 'incompatible_inputs'
    assert 'period mismatch' in result.message
