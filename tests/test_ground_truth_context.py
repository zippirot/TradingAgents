"""A claim about a brief is checked against that specific retained field."""
import json
from copy import deepcopy

from tradingagents.ground_truth_context import context_sources


def state():
    return {'run_id': 'run-1', 'company_of_interest': 'DOCN', 'trade_date': '2026-11-06',
            'issuer_identity': {'cik': '0001582961'},
            'shared_source_brief': 'Revenue was 100 USD. Shares outstanding were 10.',
            'filing_evidence': {'documents': [{'source_id': 'filing-with-rpo',
                'blocks': [{'locator': 'rpo-table', 'text': 'RPO was 893 USD.'}]}]}}


def test_brief_context_index_does_not_inherit_terms_from_other_sources():
    rows, gaps = context_sources(state())
    assert not gaps and len(rows) == 1
    row = next(iter(rows.values()))
    assert row['coverage']['field'] == 'shared_source_brief'
    assert row['coverage']['token_index_complete'] is True
    assert row['coverage']['full_text_included'] is False
    assert 'rpo' not in json.loads(row['text'].split('\n', 1)[1])['tokens']
    assert 'revenue' in json.loads(row['text'].split('\n', 1)[1])['tokens']
    assert 'financial authority' in row['kind']
    assert 'does not establish which input a particular analyst received' in row['text']


def test_index_identity_changes_with_brief_run_ticker_or_date():
    original = state()
    baseline = context_sources(original)[0]
    for key, value in [('run_id', 'run-2'), ('company_of_interest', 'OTHER'),
                       ('trade_date', '2026-11-05'), ('issuer_identity', {'cik': '0000000001'}), ('shared_source_brief', 'RPO was 100 USD.')]:
        changed = {**original, key: value}
        assert set(context_sources(changed)[0]) != set(baseline)
    changed = deepcopy(original)
    changed['shared_source_brief'] += ' RPO was 100 USD.'
    row = next(iter(context_sources(changed)[0].values()))
    assert 'rpo' in json.loads(row['text'].split('\n', 1)[1])['tokens']


def test_missing_identity_or_empty_context_cannot_assert_complete_coverage():
    for change in [{'run_id': None}, {'trade_date': 'bad'}, {'company_of_interest': '../DOCN'},
                   {'shared_source_brief': ''}]:
        rows, gaps = context_sources({**state(), **change})
        assert not rows and gaps
