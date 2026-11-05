"""Only configured provider retrieval can introduce the valuation close."""
import json

from tests.test_evidence_gate import complete_evidence
from tradingagents.agents.evidence_validation import create_evidence_gate
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.vendors import sec_documents, sec_edgar
from tradingagents.dataflows.vendors.yahoo import price_observation


def valid_state(package):
    fact = next(f for f in package.facts if f.metric == 'Revenue')
    claim = {'kind': fact.origin, 'fact_id': fact.fact_id, 'metric': fact.metric,
             'value': str(fact.value), 'unit': fact.unit, 'period_start': str(fact.period_start),
             'period_end': str(fact.period_end)}
    return {'company_of_interest': 'DOCN', 'trade_date': str(package.as_of),
            'fundamentals_report': '```financial_claims\n' + json.dumps([claim]) + '\n```'}


def test_gate_acquires_once_and_preserves_price_provider_record(monkeypatch):
    package, docs = complete_evidence()
    monkeypatch.setattr(sec_edgar, 'cik_for', lambda _: package.cik)
    monkeypatch.setattr(sec_edgar, 'get_financial_evidence', lambda *a: package)
    monkeypatch.setattr(sec_documents, 'get_filing_evidence', lambda *a: docs)
    calls = []
    def retrieve(ticker, asof, capital):
        calls.append((ticker, asof, capital))
        return {'status': 'unavailable', 'reason': 'Controlled provider outage'}
    monkeypatch.setattr(price_observation, 'get_price_observation', retrieve)
    state = valid_state(package)
    with run_config({'data_vendors': {'core_stock_apis': 'yfinance'}}):
        result = create_evidence_gate(['fundamentals'])(state)
    assert result['issuer_identity'] == {'ticker': 'DOCN', 'cik': package.cik, 'as_of': str(package.as_of), 'source': 'SEC issuer map'}
    assert len(calls) == 1
    assert result['price_observation']['reason'] == 'Controlled provider outage'
    assert result['evidence_quality']['status'] == 'limited'


def test_gate_does_not_silently_add_unconfigured_quote_provider(monkeypatch):
    package, docs = complete_evidence()
    monkeypatch.setattr(sec_edgar, 'cik_for', lambda _: package.cik)
    monkeypatch.setattr(sec_edgar, 'get_financial_evidence', lambda *a: package)
    monkeypatch.setattr(sec_documents, 'get_filing_evidence', lambda *a: docs)
    monkeypatch.setattr(price_observation, 'get_price_observation', lambda *a: (_ for _ in ()).throw(AssertionError('unexpected vendor')))
    with run_config({'data_vendors': {'core_stock_apis': 'alpha_vantage'}}):
        result = create_evidence_gate(['fundamentals'])(valid_state(package))
    assert result['price_observation']['status'] == 'unavailable'
    assert 'configured' in result['price_observation']['reason']


def test_gate_rejects_companyfacts_from_different_mapped_issuer(monkeypatch):
    package, docs = complete_evidence()
    monkeypatch.setattr(sec_edgar, 'cik_for', lambda _: '0000320193')
    monkeypatch.setattr(sec_edgar, 'get_financial_evidence', lambda *a: package)
    monkeypatch.setattr(sec_documents, 'get_filing_evidence', lambda *a: (_ for _ in ()).throw(AssertionError('wrong issuer continued')))
    result = create_evidence_gate(['fundamentals'])(valid_state(package))
    assert result['evidence_quality']['status'] == 'insufficient'
    assert result['final_rating'] == 'REVIEW'
