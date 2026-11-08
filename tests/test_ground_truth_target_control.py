"""Target declarations can be checked against retained report controls only."""
from copy import deepcopy

from tradingagents.agents.schemas import render_target_result
from tradingagents.agents.valuation import TargetResult
from tradingagents.ground_truth_context import target_control_sources


def state(target=None):
    return {'run_id': 'target-control-run', 'company_of_interest': 'SYNTH', 'trade_date': '2026-11-06',
            'target_validation': target if target is not None else {
                'status': 'unsupported', 'target': None, 'reasons': ['No eligible valuation request.'],
                'request': None}}


def test_null_target_exposes_existing_declaration_without_financial_authority():
    original = state()
    before = deepcopy(original)
    sources, gaps = target_control_sources(original)
    assert not gaps and len(sources) == 1
    row = next(iter(sources.values()))
    declaration = render_target_result(TargetResult(status='unsupported', reasons=('No eligible valuation request.',)))
    assert declaration in row['text']
    assert 'Price Target' in row['text'] and 'not provided' in row['text']
    assert row['control'] == {'status': 'unsupported', 'target': None, 'unit': None,
                              'reasons': ['No eligible valuation request.'],
                              'decision_use': {'final_target_eligible': False,
                                               'classification': 'unassessed', 'suitability': 'unassessed'}}
    assert row['kind'] == 'retained target declaration; no financial or rating authority'
    assert 'fact' not in row and original == before


def test_supported_but_ineligible_target_still_uses_existing_not_provided_declaration():
    target = TargetResult(status='supported', target='125', unit='USD',
                          decision_use={'classification': 'historical_diagnostic', 'suitability': 'excluded',
                                        'final_target_eligible': False, 'reasons': ['Historical sensitivity only.']})
    sources, gaps = target_control_sources(state(target.model_dump(mode='json')))
    assert not gaps
    row = next(iter(sources.values()))
    assert '**Price Target**: not provided' in row['text']
    assert row['control']['target'] == '125'


def test_missing_or_malformed_or_unbound_control_does_not_invent_absence():
    missing = state()
    missing.pop('target_validation')
    assert target_control_sources(missing) == ({}, [])
    for change in [{'target_validation': None}, {'target_validation': {}},
                   {'target_validation': {'status': 'unknown'}}, {'run_id': None},
                   {'company_of_interest': '../SYNTH'}, {'trade_date': 'bad'}]:
        rows, gaps = target_control_sources({**state(), **change})
        assert not rows and gaps


def test_changed_target_or_run_scope_changes_source_identity():
    original = state()
    ids = set(target_control_sources(original)[0])
    for change in [{'run_id': 'other-run'}, {'company_of_interest': 'OTHER'}, {'trade_date': '2026-11-05'},
                   {'target_validation': {'status': 'supported', 'target': '120', 'unit': 'USD'}},
                   {'target_validation': {'status': 'unsupported', 'target': None, 'reasons': ['Changed reason.']}}]:
        assert set(target_control_sources({**original, **change})[0]) != ids


def test_target_control_cannot_reassess_rating_or_expose_request_payload():
    from tradingagents.ground_truth_flow import _material_correction

    original = state()
    original['target_validation']['request'] = {'private_extra_field': 'Do not expose the raw request'}
    row = next(iter(target_control_sources(original)[0].values()))
    assert 'private_extra_field' not in row['text']
    finding = {'outcome': 'contradicted', 'decision_material': True, 'code_verified': False,
               'correction': row['text'], 'verification': {'source_quotes_validated': True},
               'evidence': [{'quote': row['text'], 'kind': row['kind']}]}
    assert not _material_correction(finding)


def test_equal_positive_targets_keep_units_and_distinct_decision_use_scope():
    observed = []
    for eligible in (False, True):
        target = TargetResult(status='supported', target='100', unit='USD',
                              decision_use={'final_target_eligible': eligible,
                                            'classification': 'forward_scenario' if eligible else 'historical_diagnostic',
                                            'suitability': 'conditional' if eligible else 'excluded'})
        rows, gaps = target_control_sources(state(target.model_dump(mode='json')))
        assert not gaps
        row = next(iter(rows.values()))
        assert row['control']['target'] == '100'
        assert row['control']['unit'] == 'USD'
        assert row['control']['decision_use'] == {
            'final_target_eligible': eligible,
            'classification': 'forward_scenario' if eligible else 'historical_diagnostic',
            'suitability': 'conditional' if eligible else 'excluded'}
        expected = '\n'.join(line for line in render_target_result(target).splitlines()
                             if line.startswith('**Price Target**:'))
        assert row['declaration'] == expected
        if eligible:
            assert row['declaration'] == ''
            assert '**Price Target**' not in row['text']
        else:
            assert '**Price Target**: not provided' in row['declaration']
        observed.append(row['source_id'])
    assert observed[0] != observed[1]
