"""Retained calculation summaries gain authority only after deterministic replay."""
from copy import deepcopy

from tradingagents.ground_truth_calculations import calculation_sources


def fixture():
    from tests.test_evidence_gate import complete_evidence
    from tradingagents.agents.evidence_validation import assess_financial_package
    package, documents = complete_evidence()
    state = {'company_of_interest': 'DOCN', 'trade_date': str(package.as_of),
             'financial_evidence': package.model_dump(mode='json'),
             'filing_evidence': documents.model_dump(mode='json')}
    replay = assess_financial_package(state, package, documents, source_only=True)
    state.update({key: replay[key] for key in ('financial_evidence', 'financial_calculations')})
    trusted = {(f['fact_id'], f['locator']): {'source_id': f['fact_id'], 'locator': f['locator'],
               'fact': deepcopy(f), 'kind': 'canonical financial fields',
               'known_at': state['trade_date'], 'url': 'https://www.sec.gov/example'}
               for f in state['financial_evidence']['facts'] if f.get('value') is not None}
    return state, trusted


def test_matching_replay_exposes_definition_and_inputs_without_rating_authority():
    state, trusted = fixture()
    sources, gaps = calculation_sources(state, trusted)
    assert sources
    assert not gaps
    for source in sources.values():
        assert source['kind'] == 'reproduced financial calculation'
        assert 'fact' not in source
        assert source['calculation']['status'] == 'pass'
        assert source['calculation']['input_fact_ids']
        assert source['inputs']
        assert all(f['fact_id'] in source['text'] for f in source['inputs'])
        assert source['calculation']['message'] in source['text']


def test_changed_result_or_definition_is_rejected_with_gap():
    state, trusted = fixture()
    target = next(c for c in state['financial_calculations'] if c.get('status') == 'pass' and c.get('result') is not None)
    for key, value in [('result', '999999999'), ('message', 'A different definition'), ('unit', 'EUR')]:
        altered = deepcopy(state)
        item = next(c for c in altered['financial_calculations'] if c['method'] == target['method'])
        item[key] = value
        sources, gaps = calculation_sources(altered, trusted)
        assert gaps
        assert all(c['calculation']['method'] != target['method'] for c in sources.values())


def test_missing_or_changed_trusted_input_cannot_be_promoted():
    state, trusted = fixture()
    assert calculation_sources(state)[0] == {}
    assert calculation_sources(state, {})[0] == {}
    altered = deepcopy(trusted)
    for item in altered.values():
        item['fact']['unit'] = 'EUR'
    sources, gaps = calculation_sources(state, altered)
    assert not sources and gaps
