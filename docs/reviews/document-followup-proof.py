"""Offline R2 real lookup/context/state/report path over retained public source.

Original question strings are scripted inputs, not new model judgments. The
separate operations-cli proof owns whole-graph/publication/memory/restart wiring.
"""
from __future__ import annotations

import hashlib
import json
import socket
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.docn_workflow_fixture import ROOT, source_json
from tradingagents.agents import document_questions as followup
from tradingagents.agents.context import get_instrument_context_from_state
from tradingagents.agents.document_access import retained_search_packages
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def deny_network(*args, **kwargs):
    raise AssertionError("R2 offline proof forbids network access")


def main():
    baseline = json.loads(Path(__file__).with_name('2026-11-08-document-followup-baseline.json').read_text())
    corpus = DisclosurePackage.model_validate(source_json('cfae95e9-corpus.json.gz'))
    assert corpus_hash(corpus) == baseline['corpus_hash']
    root = Path(tempfile.mkdtemp(prefix='r2-document-followup-'))
    state = Propagator().create_initial_state('DOCN', '2026-11-07')
    state['analysis_clock'] = {}
    state['issuer_identity'] = {'cik': corpus.cik}
    state['document_sources'] = {
        'schema_version': 1, 'ticker': 'DOCN', 'as_of': '2026-11-07', 'asset_type': 'stock',
        'analysis_clock': {}, 'status': 'ready', 'cik': corpus.cik,
        'corpus': corpus.model_dump(mode='json'), 'corpus_hash': corpus_hash(corpus), 'reason': '',
    }
    questions = {role: followup.parse_document_questions(
        '```document_questions\n' + json.dumps([q['query'] for q in baseline['questions'] if q['role'] == role])
        + '\n```', role) for role in ('bull', 'bear')}
    state['investment_debate_state']['document_questions'] = questions
    state.update(investment_plan='Offline lookup proof; no model answer judgment.',
                 trader_investment_plan='Offline lookup proof; no trade authorization.',
                 final_trade_decision='Offline source lookup demonstration; no validated rating.',
                 run_settings={'proof': 'R2 recorded public source and scripted original questions'})
    state['unvalidated_outputs'] = {'portfolio_manager': {'reason': state['final_trade_decision']}}
    with patch.object(socket.socket, 'connect', deny_network), patch.object(socket, 'create_connection', deny_network):
        with patch.object(followup, 'search_retained_document_sources', wraps=followup.search_retained_document_sources) as search:
            state.update(followup.lookup_document_questions(state))
            lookup_count = search.call_count
        record = state['document_followups']
        assert lookup_count == 3 and len(record['results']) == 4
        rows = {row['question_id']: row for row in record['results']}
        assert rows['bear-1']['duplicate_of'] == 'bull-1'
        for ident in ('bull-1', 'bear-1'):
            top = rows[ident]['passages'][0]
            assert top['locator'] == 'block-148' and top['url'].endswith('docn-20260930.htm')
            assert '$799,707' in top['text'] and '$345,111' in top['text']
        seal = record['record_hash']
        assert followup.lookup_document_questions(state) == {} and record['record_hash'] == seal
        context = followup.document_followup_context(state)
        assert context.count(rows['bull-1']['passages'][0]['text']) == 1
        assert 'UNTRUSTED RETRIEVED SOURCE TEXT' in context
        assert context in get_instrument_context_from_state(state)
        for row in record['results']:
            assert row['status'] == 'no_relevant_passage'  # full questions include terms the sources do not establish
        positive = deepcopy(state)
        positive.pop('document_followups')
        positive['investment_debate_state']['document_questions'] = {
            role: followup.parse_document_questions('```document_questions\n' + json.dumps(
                ['remaining performance obligations next 12 months'] if role == 'bull' else []) + '\n```', role)
            for role in ('bull', 'bear')}
        positive.update(followup.lookup_document_questions(positive))
        assert positive['document_followups']['results'][0]['status'] == 'relevant_passages_found'
        application = object.__new__(TradingAgentsGraph)
        application.config = {'results_dir': str(root / 'results')}
        application.run_settings = lambda: state['run_settings']
        application._log_state(state['trade_date'], state)
        reopened = json.loads(next((root / 'results').rglob('full_states_log_*.json')).read_text())
        assert reopened['document_followups'] == record
        assert followup.lookup_document_questions(reopened) == {}
        report = write_report_tree(state, 'DOCN', root / 'reports')
        markdown = report.read_text()
        html = report.with_suffix('.html').read_text()
        evidence = json.loads((root / 'reports/evidence.json').read_text())
        assert evidence['document_followups'] == record
        assert 'no_relevant_passage' in markdown and 'no_relevant_passage' in html
        assert 'RM answer judgment unavailable' in markdown and 'RM answer judgment unavailable' in html
        assert 'passage(s)' not in markdown
        original = Path.home() / '.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-07_cfae95e9.json'
        assert original.is_file(), 'Machine2 original immutable snapshot required for legacy compatibility proof'
        original_hash = digest(original)
        assert original_hash == baseline['original_state_sha256']
        old = json.loads(original.read_text())
        old_seal = old['document_followups']['record_hash']
        old_journal = json.dumps(old.get('document_search_trace'), sort_keys=True)
        assert retained_search_packages(old)
        assert followup.lookup_document_questions(old) == {}
        assert 'legacy_relevance_not_assessed' in followup.render_document_followups(old)
        assert old['document_followups']['record_hash'] == old_seal and digest(original) == original_hash
        assert json.dumps(old.get('document_search_trace'), sort_keys=True) == old_journal
    receipt = {
        'disposable_root': str(root), 'source_corpus_hash': corpus_hash(corpus),
        'fixture_manifest_sha256': digest(ROOT / 'manifest.json'),
        'original_state_sha256': original_hash, 'original_unchanged': True,
        'lookup_count': lookup_count, 'retained_question_count': len(record['results']),
        'rows': [{'question_id': row['question_id'], 'query': row['query'], 'lookup_query': row['lookup_query'],
                  'duplicate_of': row['duplicate_of'], 'status': row['status'],
                  'top': {k: row['passages'][0][k] for k in ('source_id', 'locator', 'url', 'content_hash', 'passage_hash')},
                  'top_excerpt': row['passages'][0]['text'][:700]} for row in record['results']],
        'keyword_positive_control': 'relevant_passages_found',
        'sealed_reuse': True, 'legacy_snapshot_unchanged': True, 'context_passage_deduplication': True,
        'legacy_search_journal_exact_replay_unchanged': True,
        'saved_state_reopened': True, 'markdown_and_html_status_visible': True,
        'report_evidence_exact': True, 'network_denied': True, 'paid_calls': 0,
        'output_sha256': {str(p.relative_to(root)): digest(p) for p in root.rglob('*') if p.is_file()},
        'limitations': ['Real lookup/context/state/report functions execute directly; this is not a whole-graph CLI proof.',
                        'Original queries are scripted input; no live model compliance or RM answer judgment is claimed.',
                        'Original full questions remain no_relevant_passage when source bodies lack all content words; partial source text stays explicitly untrusted.',
                        'Bull2/bear2 top rankings are recorded as observed, not claimed complete answers.',
                        'Separate existing operations-cli proof covers compiled graph/publication/memory/save/retry/checkpoint/replay wiring.'],
    }
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
