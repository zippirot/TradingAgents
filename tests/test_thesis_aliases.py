"""Only equivalent condition labels normalize; provenance and identity survive."""
from uuid import uuid4

import pytest

from tests.test_thesis import margin_condition, margin_state
from tradingagents.memory import thesis


def prepare(row, evidence=None, prior=None):
    return thesis.prepare_thesis({'conditions':[row]}, prior, 'Hold', '2026-11-04',
                                str(uuid4()), financial_evidence=evidence)


def variant(**updates):
    return {**margin_condition(), 'metric':' gross   MARGIN ', 'metric_definition':'GROSS margin',
            'unit':'%', 'basis':'GAAP', **updates}


def test_equivalent_labels_observe_and_normalize_new_identity_with_original_diagnostics():
    evidence = margin_state()['financial_evidence']
    a = prepare(margin_condition(), evidence)['conditions'][0]
    b = prepare(variant(), evidence)['conditions'][0]
    assert a['condition_id'] == b['condition_id']
    assert b['metric'] == b['metric_definition'] == 'Gross Margin'
    assert b['unit'] == 'percent' and b['basis'] == 'US-GAAP'
    assert b['original_labels'] == {k:variant()[k] for k in ('metric','metric_definition','unit','basis')}
    observed = thesis.observe_conditions({'conditions':[variant()]}, margin_state())[0]
    assert observed['status'] == 'breached' and observed['formula_id'] == 'gross_margin_percent_v1'


@pytest.mark.parametrize('updates',[
    {'metric_definition':'Cloud Gross Margin'}, {'metric':'Adjusted Gross Margin'},
    {'basis':'non-GAAP'}, {'basis':'IFRS'}, {'unit':'USD'},
    {'period_start':'2026-01-01'},
])
def test_different_scope_basis_unit_or_period_remains_unknown(updates):
    assert thesis.observe_conditions({'conditions':[variant(**updates)]}, margin_state())[0]['status'] == 'unknown'


def test_gaap_alias_requires_established_us_gaap_package_scope():
    row = prepare(variant())['conditions'][0]
    assert row['basis'] == 'GAAP'
    data = margin_state()
    data['financial_evidence']['scope'] = 'IFRS statements'
    assert prepare(variant(), data['financial_evidence'])['conditions'][0]['basis'] == 'GAAP'
    assert thesis.observe_conditions({'conditions':[variant()]}, data)[0]['status'] == 'unknown'


def test_saved_identifiers_aliases_and_original_wording_survive_equivalent_reproposal():
    old = {**variant(), 'condition_id':'condition-'+'a'*24, 'condition_aliases':['condition-'+'b'*24]}
    prior = {'conditions':[old]}
    result = prepare(margin_condition(), margin_state()['financial_evidence'], prior)['conditions'][0]
    assert result['condition_id'] == old['condition_id']
    assert result['condition_aliases'] == old['condition_aliases']
    assert old['metric'] == ' gross   MARGIN '
    observed = thesis.observe_conditions(prior, margin_state())[0]
    assert observed['condition_id'] == old['condition_id']
    assert observed['original_labels']['metric'] == old['metric']


@pytest.mark.parametrize('updates',[
    {'unit':'EUR'}, {'unit':'USD/share'}, {'basis':'IFRS'},
    {'metric_definition':'Cloud Revenue'}, {'period_start':'2026-01-01'},
])
def test_revenue_alias_does_not_change_currency_scope_or_duration(updates):
    from tests.test_thesis import condition, state
    row = {**condition(), 'metric':' revenue ', 'metric_definition':'REVENUE', **updates}
    observed = thesis.observe_conditions({'conditions':[row]}, state('101'))[0]
    assert observed['status'] == 'unknown'
    base = prepare(condition(), state()['financial_evidence'])['conditions'][0]
    changed = prepare(row, state()['financial_evidence'])['conditions'][0]
    assert changed['condition_id'] != base['condition_id']


def test_unknown_metric_spelling_is_not_fuzzy_matched():
    row = variant(metric='GrossMargin')
    result = prepare(row, margin_state()['financial_evidence'])['conditions'][0]
    assert result['metric'] == 'GrossMargin'
    assert thesis.observe_conditions({'conditions':[row]}, margin_state())[0]['status'] == 'unknown'


def test_canonical_existing_identity_and_saved_aliases_are_unchanged():
    row = margin_condition()
    expected = thesis._id(thesis.ThesisCondition.model_validate(row))
    assert prepare(row, margin_state()['financial_evidence'])['conditions'][0]['condition_id'] == expected
    old = {**row, 'condition_id':expected, 'condition_aliases':['condition-'+'c'*24]}
    result = prepare(variant(), margin_state()['financial_evidence'], {'conditions':[old]})['conditions'][0]
    assert result['condition_id'] == expected
    assert result['condition_aliases'] == old['condition_aliases']


def _event(description):
    return {'thesis_role': 'reconsideration_trigger', 'kind': 'event', 'description': description,
            'confirming_evidence': 'Subsequent SEC filing', 'expiry': '2027-01-31', 'rationale': 'Open question'}


def _restated(prior_text, new_text):
    prior = prepare(_event(prior_text))
    identifier = prior['conditions'][0]['condition_id']
    return identifier, thesis.prepare_thesis(
        {'conditions': [_event(new_text)],
         'dispositions': [{'condition_id': identifier, 'disposition': 'kept', 'reason': 'Still open.'}]},
        prior, 'Hold', '2026-11-09', str(uuid4()))


@pytest.mark.parametrize('prior_text,new_text', [
    ("Disclosure of how DOCN's 2026 convertible notes were settled or refinanced.",
     "Disclosure of settlement or refinancing of DOCN's 2026 convertible notes."),
    ('Disclosure of material ATM issuance or a substantive capacity financing plan.',
     'Disclosure of material ATM issuance or a substantive capacity-funding plan.'),
])
def test_paraphrased_event_is_aliased(prior_text, new_text):
    identifier, saved = _restated(prior_text, new_text)
    assert [row['condition_id'] for row in saved['conditions']] == [identifier]
    assert len(saved['conditions'][0]['condition_aliases']) == 1
    assert not any('omitted from proposal' in warning for warning in saved['warnings'])


@pytest.mark.parametrize('prior_text,new_text', [
    ('Management cuts its 2027 revenue growth guidance.', 'Disclosure of material ATM issuance.'),
    ("Disclosure of how DOCN's 2026 convertible notes were settled.", "Disclosure of how DOCN's 2030 convertible notes were settled."),
    ('Management cuts its 2027 revenue growth guidance.', 'Management raises its 2027 revenue growth guidance.'),
])
def test_different_event_is_new(prior_text, new_text):
    _, saved = _restated(prior_text, new_text)
    assert len(saved['conditions']) == 2


@pytest.mark.parametrize('new_text', [
    'Management does not cut its 2027 revenue growth guidance.',
    "Management doesn't cut its 2027 revenue growth guidance.",
])
def test_negated_event_is_new(new_text):
    _, saved = _restated('Management cuts its 2027 revenue growth guidance.', new_text)
    assert len(saved['conditions']) == 2


@pytest.mark.parametrize('new_conditions', [[], [_event('Disclosure of material ATM issuance.')]])
def test_keep_by_id_alone_is_not_an_omission(new_conditions):
    prior = prepare(_event('Management cuts its 2027 revenue growth guidance.'))
    identifier = prior['conditions'][0]['condition_id']
    saved = thesis.prepare_thesis(
        {'conditions': new_conditions,
         'dispositions': [{'condition_id': identifier, 'disposition': 'kept', 'reason': 'Still open.'}]},
        prior, 'Hold', '2026-11-09', str(uuid4()))
    assert [row['condition_id'] for row in saved['conditions']].count(identifier) == 1
    assert len(saved['conditions']) == 1 + len(new_conditions)
    assert not any('omitted from proposal' in warning for warning in saved['warnings'])
