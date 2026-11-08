"""Historical exact search returns stay valid after current ranking changes."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.docn_workflow_fixture import source_json
from tradingagents.agents.document_access import retained_search_packages, run_document_search
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage


def legacy_state():
    corpus = DisclosurePackage.model_validate(source_json('cfae95e9-corpus.json.gz'))
    baseline = json.loads((Path(__file__).resolve().parents[1] /
                           'docs/reviews/2026-11-08-document-followup-baseline.json').read_text())
    captured = baseline['questions'][0]
    passages = []
    for ref in captured['before_passages']:
        document = next(d for d in corpus.documents if d.source_id == ref['source_id'])
        block = next(b for b in document.blocks if b.locator == ref['locator'])
        assert hashlib.sha256(block.text.encode()).hexdigest() == ref['passage_hash']
        passages.append({'source_id': document.source_id, 'locator': block.locator,
                         'section': block.section, 'text': block.text, 'truncated': False,
                         'currency': block.currency, 'currency_locator': block.currency_locator,
                         'filing_form': document.filing.form, 'filing_date': str(document.filing.filed_date),
                         'filing_accession': document.filing.accession, 'url': document.url,
                         'content_hash': document.content_hash, 'passage_hash': ref['passage_hash']})
    entry = {'role': 'fundamentals', 'call_id': 'legacy-1', 'query': captured['query'],
             'status': 'ok', 'counted': True, 'corpus_hash': corpus_hash(corpus),
             'passages': passages, 'gaps': [], 'reason': ''}
    state = {'company_of_interest': 'DOCN', 'trade_date': '2026-11-07', 'asset_type': 'stock',
             'analysis_clock': {}, 'issuer_identity': {'cik': corpus.cik},
             'document_sources': {'schema_version': 1, 'ticker': 'DOCN', 'as_of': '2026-11-07',
                                  'asset_type': 'stock', 'analysis_clock': {}, 'status': 'ready',
                                  'cik': corpus.cik, 'corpus': corpus.model_dump(mode='json'),
                                  'corpus_hash': corpus_hash(corpus), 'reason': ''},
             'document_search_trace': {'fundamentals:legacy-1': entry}}
    return state, entry


def test_unversioned_journal_replays_original_ranking_without_rewriting():
    state, entry = legacy_state()
    before = json.dumps(state['document_search_trace'], sort_keys=True)
    packages = retained_search_packages(state)
    assert packages
    expected = {(p['source_id'], p['locator']) for p in entry['passages']}
    actual = {(d.source_id, b.locator) for p in packages for d in p.documents for b in d.blocks}
    assert actual == expected
    assert run_document_search(state, entry['query'], role='fundamentals', call_id='legacy-1')['result'] == entry
    assert json.dumps(state['document_search_trace'], sort_keys=True) == before


def test_new_journal_uses_current_ranking_and_cannot_claim_legacy_passages():
    state, legacy = legacy_state()
    state['document_search_trace'] = {}
    update = run_document_search(state, legacy['query'], role='fundamentals', call_id='current-1')
    current = update['result']
    assert current['search_version'] == 3
    assert current['passages'][0]['locator'] == 'block-148'
    state['document_search_trace'].update(update['document_search_trace'])
    assert retained_search_packages(state)
    current['passages'] = deepcopy(legacy['passages'])
    with pytest.raises(ValueError, match='differs from retained source'):
        retained_search_packages(state)


def test_legacy_journal_still_rejects_tampering_and_unknown_versions():
    state, entry = legacy_state()
    entry['passages'][0]['text'] += ' fabricated'
    with pytest.raises(ValueError, match='differs from retained source'):
        retained_search_packages(state)
    state, entry = legacy_state()
    entry['search_version'] = 99
    with pytest.raises(ValueError, match='version'):
        retained_search_packages(state)
