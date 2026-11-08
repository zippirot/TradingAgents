"""Offline R1 source acquisition through evidence gate, using public fixtures.

SEC transport and the Yahoo completed-price response are recorded inputs;
selection, extraction, validation, brief assembly, state save and exports execute.
The original model report is a private read-only scripted input, not new model work.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
from contextlib import ExitStack
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langchain_core.messages import ToolMessage

from tests.docn_workflow_fixture import ROOT, source_json
from tradingagents.agents.analysts.fundamentals_analyst import _disclosures
from tradingagents.agents.document_access import validated_document_corpus
from tradingagents.agents.evidence_validation import create_evidence_gate, create_source_acquisition
from tradingagents.agents.issuer_events import news_tool_coverage
from tradingagents.agents.shared_valuation import prepare_shared_valuation, render_shared_valuation
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import sec_documents, sec_edgar
from tradingagents.dataflows.vendors.yahoo import news, price_observation
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def forbidden(*args, **kwargs):
    raise AssertionError('Network or unrecorded source forbidden in offline R1 proof')


os.umask(0o077)
root = Path(tempfile.mkdtemp(prefix='r1-evidence-assembly-'))
original = Path.home() / '.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-07_cfae95e9.json'
original_hash = digest(original)
saved = json.loads(original.read_text())
config = deepcopy(DEFAULT_CONFIG)
config.update(data_cache_dir=str(root / 'cache'), results_dir=str(root / 'results'),
              memory_log_path=str(root / 'memory.md'))
config['data_vendors'] = {**config.get('data_vendors', {}), 'core_stock_apis': 'yfinance'}
selected = ['market', 'social', 'news', 'fundamentals']
initial = Propagator().create_initial_state('DOCN', '2026-11-07', instrument_context='DOCN recorded source proof')
initial.update(analysis_clock=deepcopy(saved.get('analysis_clock') or {}), messages=[],
               trader_investment_plan='', investment_plan='',
               final_trade_decision='R1 source evidence proof only; no new portfolio decision.', final_rating='REVIEW')
# Choose the exact current corpus version, never replace the older fixture's raw bytes.
corpus = source_json('16416b7e-corpus.json.gz')
transport = {doc['url']: source_json('sec-' + doc['content_hash'] + '.json.gz') for doc in corpus['documents']}
submission = source_json('docn-submissions.json.gz')
transport[submission['url']] = submission
raw_facts = source_json('raw-companyfacts-docn.json.gz')
issuer_map = source_json('issuer-map.json.gz')
price_source = source_json('cfae95e9-price-source.json.gz')


def sec_json(url):
    if url == sec_edgar._TICKERS_URL:
        return deepcopy(issuer_map)
    if url == sec_edgar._FACTS_URL.format(cik='0001582961'):
        return deepcopy(raw_facts)
    return forbidden(url)


with ExitStack() as stack, run_config(config):
    from tradingagents.agents import transcript_access, valuation_reference_flow

    stack.enter_context(patch.object(socket.socket, 'connect', forbidden))
    stack.enter_context(patch.object(sec_edgar, '_fetch_json', side_effect=sec_json))
    stack.enter_context(patch.object(sec_documents.DocumentClient, '_fetch',
                                    lambda self, url: deepcopy(transport[url]) if url in transport else forbidden(url)))
    stack.enter_context(patch.object(price_observation, 'get_price_observation',
                                    side_effect=lambda ticker, as_of, *args: price_observation.validate_price_observation(
                                        deepcopy(price_source), ticker, as_of)))
    # Independent reference/transcript acquisition is not this source-family proof.
    stack.enter_context(patch.object(transcript_access, 'prepare_transcript_sources', return_value={}))
    stack.enter_context(patch.object(valuation_reference_flow, 'acquire_reference_inputs', return_value={}))
    acquired = create_source_acquisition(selected)(initial)
    state = {**initial, **acquired}
    assert state['evidence_acquisition']['status'] == 'ready', state['evidence_acquisition']
    assert 'Financing authorization' in state['shared_source_brief']
    assert '1000000000' in state['shared_source_brief']
    for text in (state['shared_source_brief'], state['canonical_financial_context']):
        for fragment in ('$61 million', '134,085,000 USD', '893,828,000 USD', '799,707,000 USD',
                         '345,111,000 USD', 'prior periods recast to include all contracts',
                         '2027 $250.0M', 'present value $923.6M', 'Scheduled payments are not principal.'):
            assert fragment in text, fragment
    acquisition_claims = state['disclosure_evidence']['deterministic_extraction']
    assert len(acquisition_claims['claims']) == 15 and not acquisition_claims['rejected'], acquisition_claims
    verified_corpus = validated_document_corpus(state)
    # Script the exact original analyst submission; all source checking reruns.
    report = saved['financial_claim_validation']['raw_report']
    state['messages'] = [ToolMessage(name='get_filing_evidence', tool_call_id='fixture-filing',
                                     content=json.dumps(state['filing_evidence']))]
    def failed_quote(**kwargs):
        raise VendorUnavailableError('Offline fixture quote-feed failure')
    stack.enter_context(patch.object(news.yf, 'Ticker', return_value=SimpleNamespace(get_news=failed_quote)))
    stack.enter_context(patch.object(news.yf, 'Search', return_value=SimpleNamespace(
        news=[{'title': 'Synthetic headline for offline R1 proof', 'publisher': 'Offline fixture publisher',
               'relatedTickers': ['DOCN'],
               'providerPublishTime': int(datetime(2026, 11, 3, tzinfo=UTC).timestamp())}],
        quotes=[{'symbol': 'DOCN'}])))
    state['news_report'] = news.get_news_yfinance('DOCN', '2026-10-31', '2026-11-07')
    state['news_coverage'] = news_tool_coverage([
        ToolMessage(name='get_news', tool_call_id='fixture-news', content=state['news_report'])])
    assert '2026-11-03T00:00:00+00:00' in state['news_report']
    assert state['news_coverage']['independent_news']['status'] == 'degraded'
    state['fundamentals_report'] = report
    state['disclosure_evidence'] = _disclosures(state, report)
    state.update(create_evidence_gate(selected)(state))
    extraction = state['disclosure_evidence']
    assert len(extraction['model_extraction']['claims']) == 6, extraction['model_extraction']
    assert len(extraction['model_extraction']['rejected']) == 3, extraction['model_extraction']
    assert extraction['model_extraction']['rejected'] == saved['disclosure_evidence']['model_extraction']['rejected'][6:]
    assert not extraction['deterministic_extraction']['rejected'], extraction['deterministic_extraction']
    cases = prepare_shared_valuation(state, requests=saved['shared_valuation_scenarios']['requests'])
    assert len(cases['rows']) == 2, cases
    for old, new in zip(saved['shared_valuation_scenarios']['rows'], cases['rows'], strict=True):
        assert old['request'] == new['request']
        assert old['result']['target'] == new['result']['target']
        assert {'finance_equipment', 'all_leases'} <= new['sensitivities'].keys(), new
    state['shared_valuation_scenarios'] = cases
    rendered = render_shared_valuation(cases)
    assert '2026-09-30' in rendered and '2027-12-31' in rendered
    # Save/reopen through the existing application writer and report exporters.
    state.update(market_report='Offline recorded-source R1 proof',
                 sentiment_report='Offline sentiment source proof', run_settings={'proof': 'R1 recorded source inputs'})
    application = object.__new__(TradingAgentsGraph)
    application.config = config
    application.run_settings = lambda: state['run_settings']
    application._log_state(state['trade_date'], state)
    reopened = json.loads(next((root / 'results').rglob('full_states_log_*.json')).read_text())
    assert reopened['shared_source_brief'] == state['shared_source_brief']
    write_report_tree(state, 'DOCN', root / 'reports')
    evidence = json.loads((root / 'reports/evidence.json').read_text())
    assert evidence['shared_source_brief'] == state['shared_source_brief']
    assert evidence['shared_valuation_scenarios'] == cases
    assert original_hash == digest(original)
    receipt = {'disposable_root': str(root), 'source_state_sha256': original_hash,
               'original_unchanged': True, 'source_fixture_manifest_sha256': digest(ROOT / 'manifest.json'),
               'source_corpus_hash': state['document_sources']['corpus_hash'],
               'full_corpus_blocks': sum(len(d.blocks) for d in verified_corpus.documents),
               'source_only_disclosures': {'accepted': len(acquisition_claims['claims']), 'rejected': len(acquisition_claims['rejected'])},
               'model_disclosures': {'accepted': len(extraction['model_extraction']['claims']), 'rejected': len(extraction['model_extraction']['rejected'])},
               'deterministic_disclosures': {'accepted': len(extraction['deterministic_extraction']['claims']), 'rejected': len(extraction['deterministic_extraction']['rejected'])},
               'quality': state['evidence_quality']['status'],
               'news_fixture': {'synthetic': True, 'timestamp_and_publisher_visible': True,
                                'coverage': state['news_coverage']['independent_news']},
               'case_targets': [{'base': r['result']['target'], 'sensitivities': r['sensitivities']} for r in cases['rows']],
               'saved_state_reopened': True, 'report_evidence_reopened': True,
               'export_hashes': {p.name: digest(p) for p in (root / 'reports').iterdir() if p.is_file()},
               'limitations': ['SEC transport and Yahoo completed-price replies are recorded doubles; no live provider claim.',
                               'Original model report is scripted input; no model compliance or paid comparison claim.',
                               'News timestamp/publisher are explicitly synthetic; actual news formatting/coverage paths execute.',
                               'Source/evidence nodes execute directly, not a new CLI/whole-graph proof.',
                               'Reference/peer and transcript acquisition disabled in this source-family proof; separately tested.',
                               'All writes are in disposable stores; no publication or private input is mutated.']}
    print(json.dumps(receipt, indent=2))
