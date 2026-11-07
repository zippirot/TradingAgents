"""Claims about retained input content receive the exact original brief."""
import hashlib

from tradingagents.ground_truth_context import context_sources


def state():
    return {'run_id': 'run-1', 'company_of_interest': 'DOCN', 'trade_date': '2026-11-06',
            'issuer_identity': {'cik': '0001582961'},
            'shared_source_brief': 'Revenue was 100 USD. Shares outstanding were 10.',
            'filing_evidence': {'documents': [{'source_id': 'filing-with-rpo',
                'blocks': [{'locator': 'rpo-table', 'text': 'RPO was 893 USD.'}]}]}}


def test_complete_brief_context_does_not_inherit_text_from_other_sources():
    original = state()
    rows, gaps = context_sources(original)
    assert not gaps and len(rows) == 1
    row = next(iter(rows.values()))
    assert row['text'].encode('utf-8') == original['shared_source_brief'].encode('utf-8')
    assert row['coverage']['field'] == 'shared_source_brief'
    assert row['coverage']['full_text_included'] is True
    assert row['coverage']['field_sha256'] == hashlib.sha256(row['text'].encode()).hexdigest()
    assert 'RPO' not in row['text']
    assert 'no financial authority' in row['kind']
    assert 'does not establish which input' in row['scope']


def test_identity_changes_with_brief_run_ticker_date_or_cutoff():
    original = state()
    baseline = context_sources(original)[0]
    for key, value in [('run_id', 'run-2'), ('company_of_interest', 'OTHER'),
                       ('trade_date', '2026-11-05'), ('issuer_identity', {'cik': '0000000001'}),
                       ('shared_source_brief', 'RPO was 100 USD.'),
                       ('analysis_clock', {'cutoff_utc': '2026-11-06T10:00:00Z'})]:
        changed = {**original, key: value}
        assert set(context_sources(changed)[0]) != set(baseline)
    assert original == state()


def test_missing_identity_empty_or_over_packet_context_discloses_coverage():
    for change in [{'run_id': None}, {'trade_date': 'bad'}, {'company_of_interest': '../DOCN'},
                   {'shared_source_brief': ''}, {'shared_source_brief': 'X' * 25000}]:
        rows, gaps = context_sources({**state(), **change})
        assert not rows and gaps


def test_synonymous_performance_obligation_disclosure_is_available_without_rpo_token():
    from tradingagents.ground_truth import _select_sources

    brief = ('The contracted transaction price allocated to unsatisfied or partially unsatisfied '
             'performance obligations was 799.707 million USD.\nThis sentence is retained exactly.\n')
    original = {**state(), 'shared_source_brief': brief}
    rows, gaps = context_sources(original)
    selected, _ = _select_sources('No RPO fact is in the retained brief.', rows, 24000)
    assert not gaps and selected
    assert 'RPO' not in brief
    assert next(iter(selected.values()))['text'] == brief
    assert 'performance obligations' in next(iter(selected.values()))['text']
    ordinary, _ = _select_sources('Revenue was 100 USD and RPO was 799.707 million USD.', rows, 24000)
    assert not ordinary
    too_small, omitted = _select_sources('No RPO fact is in the retained brief.', rows, 10)
    assert not too_small and omitted


def test_context_quotation_never_grants_financial_or_pm_authority():
    from tradingagents.ground_truth_flow import _material_correction

    row = next(iter(context_sources(state())[0].values()))
    finding = {'outcome': 'contradicted', 'decision_material': True, 'code_verified': False,
               'correction': row['text'], 'verification': {'source_quotes_validated': True},
               'evidence': [{'kind': row['kind'], 'quote': row['text']}]}
    assert not _material_correction(finding)
    assert 'fact' not in row
