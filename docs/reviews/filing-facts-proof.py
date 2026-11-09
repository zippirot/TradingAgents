"""Offline DOCN acquisition, real prompt factories and saved report proof.

Reads private original inputs; all caches, state and exports are disposable.
Only the sanitized receipt is suitable for committing.
"""
import hashlib
import importlib
import json
import os
import shutil
import socket
import sys
import tempfile
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage

from tradingagents.agents.document_access import validated_document_corpus
from tradingagents.agents.evidence_validation import create_evidence_gate, create_source_acquisition
from tradingagents.dataflows.config import run_config
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.reporting import write_report_tree


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def forbidden(*args, **kwargs):
    raise AssertionError('Live network/model boundary forbidden in offline proof')


socket.socket.connect = forbidden
original = Path.home() / '.tradingagents'
saved_path = original / 'logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-07.json'
saved = json.loads(saved_path.read_text())
root = Path(tempfile.mkdtemp(prefix='filing-facts-proof-'))
cache = root / 'cache'
source_files = [saved_path]
for folder in ('sec_documents', 'sec_edgar'):
    destination = cache / folder
    destination.mkdir(parents=True)
    for path in (original / 'cache' / folder).glob('*.json'):
        # SEC only; never copy credentials, application settings or model traces.
        shutil.copy2(path, destination / path.name)
        os.utime(destination / path.name, None)  # Fresh local copy, no source mutation.
        source_files.append(path)
source_hashes = {str(path): digest(path) for path in source_files}
config = deepcopy(DEFAULT_CONFIG)
config.update(data_cache_dir=str(cache), results_dir=str(root / 'results'),
              memory_log_path=str(root / 'memory.md'))
config['data_vendors'] = {**config.get('data_vendors', {}), 'core_stock_apis': 'yfinance'}
selected = ['market', 'social', 'news', 'fundamentals']
initial = {key: deepcopy(saved[key]) for key in (
    'company_of_interest', 'trade_date', 'asset_type', 'analysis_clock')}
initial.update(messages=[], investment_debate_state={'count': 0},
               risk_debate_state={'count': 0, 'history': ''}, instrument_context='DOCN; DigitalOcean Holdings')
with ExitStack() as stack, run_config(config):
    from tradingagents.agents import kpi_comparisons, transcript_access, valuation_reference_flow
    from tradingagents.dataflows.vendors.yahoo import price_observation
    # Unrelated source families have retained provider results; no extra acquisition.
    stack.enter_context(patch.object(price_observation, 'get_price_observation', return_value=saved['price_observation']))
    stack.enter_context(patch.object(kpi_comparisons, 'retrieve_rpo_comparison', return_value=None))
    stack.enter_context(patch.object(transcript_access, 'prepare_transcript_sources', return_value={}))
    stack.enter_context(patch.object(valuation_reference_flow, 'acquire_reference_inputs', return_value={}))
    acquired = create_source_acquisition(selected)(initial)
    state = {**initial, **acquired}
    assert state['evidence_acquisition']['status'] == 'ready'
    records = state['filing_terms_evidence']
    assert len(records['notes']) == len(records['leases']) == 1, records
    note, lease = records['notes'][0], records['leases'][0]
    assert note['principal_outstanding'] == '312322' and note['principal_unit'] == 'USD thousands'
    assert note['conversion_price'] == '178.51' and note['stated_plan_locator'] == 'block-430'
    assert lease['undiscounted_amount'] == '2955158' and lease['locator'] == 'block-218'
    calculation = next(c for c in acquired['financial_calculations'] if c['method'] == 'cash_plus_marketable_securities_v1')
    assert calculation['status'] == 'pass' and calculation['result'] == '844741000', calculation
    corpus = validated_document_corpus(state)
    bounded = deepcopy(state['filing_evidence'])
    # A3 budgets are unchanged. Explicitly remove every new-term section from the
    # short package in a separate replay; only the validated full corpus supplies it.
    absent = {'block-204', 'block-205', 'block-218', 'block-430'}
    for doc in bounded['documents']:
        if doc['url'].endswith('docn-20260930.htm'):
            doc['blocks'] = [b for b in doc['blocks'] if b['locator'] not in absent]
    replay = {**state, 'filing_evidence': bounded, 'document_sources': deepcopy(saved['document_sources'])}
    from tradingagents.agents.filing_terms import prepare_filing_terms
    retained_records = prepare_filing_terms(replay)['filing_terms_evidence']
    assert retained_records['notes'] == records['notes'] and retained_records['leases'] == records['leases']
    from tradingagents.dataflows.vendors import sec_documents
    stack.enter_context(patch.object(sec_documents.DocumentClient, 'fetch', forbidden))
    (root / 'source-acquisition.json').write_text(json.dumps(acquired, default=str))
    assert '844741000 USD' in state['shared_source_brief'], [(c['code'], c['status'], c.get('message', '')[:300]) for c in state['evidence_acquisition']['source_checks'] if c['status'] != 'pass']
    captures = {}
    def capture(role, prompt):
        text = str(prompt)
        for phrase in ('312322 USD thousands', '178.51 USD/share', 'block-430',
                       '2955158 USD thousands', '844741000 USD'):
            assert phrase in text, (role, phrase)
        captures[role] = {'sha256': hashlib.sha256(text.encode()).hexdigest(), 'chars': len(text)}
    class ModelDouble:
        def __init__(self, role): self.role = role
        def invoke(self, prompt):
            capture(self.role, prompt)
            return AIMessage(content='**Rating**: Hold\nOffline provider double; no execution proposal.')
        def with_structured_output(self, *args, **kwargs): raise NotImplementedError('offline double')
    # Actual analyst prompt construction; only model/provider responses substituted.
    for role in ('market', 'news', 'fundamentals'):
        module = importlib.import_module('tradingagents.agents.analysts.' + role + '_analyst')
        def turn(prompt, llm, tools, messages, role=role):
            capture(role, prompt.format_messages(messages=messages))
            text = saved['financial_claim_validation']['raw_report'] if role == 'fundamentals' else 'Offline analyst reply'
            return AIMessage(content=text), text
        with patch.object(module, 'take_turn', turn):
            state.update(getattr(module, 'create_' + role + '_analyst')(ModelDouble(role))(state))
    social = importlib.import_module('tradingagents.agents.analysts.sentiment_analyst')
    stack.enter_context(patch.object(social, 'bind_structured', return_value=None))
    for name, value in [('jev_screen', None), ('fetch_stocktwits_messages', 'Offline social response'),
                        ('fetch_reddit_posts', 'Unavailable'), ('subreddits_for', ())]:
        stack.enter_context(patch.object(social, name, return_value=value))
    stack.enter_context(patch.object(social.get_news, 'func', return_value='Offline news response'))
    state.update(social.create_sentiment_analyst(ModelDouble('social'))(state))
    state.update(create_evidence_gate(selected)(state))
    assert next(c for c in state['financial_calculations'] if c['method'] == calculation['method']) == calculation
    for package, module_name, factory, role in [
        ('researchers', 'bull_researcher', 'create_bull_researcher', 'bull'),
        ('researchers', 'bear_researcher', 'create_bear_researcher', 'bear'),
        ('managers', 'research_manager', 'create_research_manager', 'research_manager'),
        ('trader', 'trader', 'create_trader', 'trader'),
        ('risk_mgmt', 'aggressive_debator', 'create_aggressive_debator', 'aggressive'),
        ('risk_mgmt', 'conservative_debator', 'create_conservative_debator', 'conservative'),
        ('risk_mgmt', 'neutral_debator', 'create_neutral_debator', 'neutral'),
        ('managers', 'portfolio_manager', 'create_portfolio_manager', 'portfolio_manager')]:
        module = importlib.import_module(f'tradingagents.agents.{package}.{module_name}')
        state.update(getattr(module, factory)(ModelDouble(role))(state))
    # Freeze only this disposable run. No historical publication is edited.
    state.pop('publication_record', None)
    state['run_settings'] = {'proof': 'Offline B provider doubles'}
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    application = object.__new__(TradingAgentsGraph)
    application.config = config
    application.run_settings = lambda: state['run_settings']
    application._log_state(state['trade_date'], state)
    reopened_state = json.loads(next((root / 'results').rglob('full_states_log_*.json')).read_text())
    assert reopened_state['filing_terms_evidence'] == records
    write_report_tree(state, 'DOCN', root / 'reports')
    evidence = json.loads((root / 'reports/evidence.json').read_text())
    assert evidence['filing_terms_evidence'] == records
    assert reopened_state['shared_source_brief'] == evidence['shared_source_brief'] == state['shared_source_brief']
    assert '844741000' in (root / 'reports/complete_report.md').read_text()
    for extension in ('md', 'html'):
        text = (root / 'reports' / f'complete_report.{extension}').read_text()
        assert '312322' in text and '2955158' in text and 'block-430' in text
    assert source_hashes == {str(path): digest(path) for path in source_files}
    receipt = {
        'stage': sys.argv[1] if len(sys.argv) > 1 else 'proof',
        'source_state_sha256': source_hashes[str(saved_path)], 'source_files_unchanged': len(source_files),
        'disposable_root': str(root), 'source_corpus_hash': state['document_sources']['corpus_hash'],
        'notes': len(records['notes']), 'note_locators': [note['locator'], note['conversion_price_locator'], note['stated_plan_locator']],
        'leases': len(records['leases']), 'lease_locator': lease['locator'],
        'liquidity_usd': calculation['result'], 'liquidity_input_fact_ids': calculation['input_fact_ids'],
        'prompt_receipts': captures, 'full_corpus_blocks': sum(len(d.blocks) for d in corpus.documents),
        'short_package_removed_locators_replay': sorted(absent), 'evidence_export_reopened': True, 'application_state_log_reopened': True,
        'saved_validated_corpus_replayed': True, 'saved_corpus_hash': replay['document_sources']['corpus_hash'],
        'source_acquisition_after_replay_forbidden': True,
        'network_calls': 0, 'paid_model_calls': 0,
        'limitations': ['Model/provider replies are offline doubles; no live model compliance proven.',
                       'Actual source acquisition, each role factory, evidence gate and report export execute.',
                       'Factories invoked in application order; compiled graph scheduling is covered separately.'],
    }
    print(json.dumps(receipt, indent=2))
