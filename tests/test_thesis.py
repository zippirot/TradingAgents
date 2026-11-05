"""Advisory conditions do not acquire publication or trading authority."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tradingagents.memory import thesis


def condition(**updates):
    return dict(metric='Revenue', metric_definition='Revenue', period_start='2026-07-01',
                period_end='2026-09-30', comparator='>=', threshold='100', unit='USD',
                basis='US-GAAP', expiry='2026-12-31', rationale='Growth assumption', **updates)


def state(value='99', quantum=None):
    result = {'financial_evidence': {'cik': '1', 'as_of': '2026-11-04',
        'sources': [{'source_id': 's', 'cik': '1', 'url': 'https://www.sec.gov/source',
                     'filed_date': '2026-11-01', 'retrieved_at': '2026-11-04T20:00:00Z',
                     'content_hash': 'a'*64, 'locator': 'x', 'form': '10-Q'}],
        'facts': [{'fact_id': 'f', 'metric': 'Revenue', 'value': value, 'unit': 'USD', 'cik': '1',
                   'period_start': '2026-07-01', 'period_end': '2026-09-30', 'as_of': '2026-11-04',
                   'basis': 'US-GAAP', 'source_ids': ['s'], 'locator': 'x'}]}}
    if quantum is not None:
        result['filing_fact_extraction'] = {'rounding_quantum_by_fact': {'f': quantum}}
    return result


@pytest.mark.parametrize('value,quantum,status', [('101', None, 'met'), ('99', None, 'breached'),
    ('99', '4', 'unknown'), ('98', '2', 'breached'), ('101', '2', 'met')])
def test_threshold_rounding(value, quantum, status):
    result = thesis.observe_conditions({'conditions': [condition()]}, state(value, quantum))
    assert result[0]['status'] == status
    assert result[0]['source_ids'] == ['s']


@pytest.mark.parametrize('field,value', [('unit','EUR'), ('basis','adjusted'), ('period_start','2026-01-01')])
def test_incompatible_fact_unknown(field, value):
    data = state()
    data['financial_evidence']['facts'][0][field] = value
    assert thesis.observe_conditions({'conditions':[condition()]}, data)[0]['status'] == 'unknown'


def test_expired_and_missing_are_visible():
    c = condition()
    c['expiry'] = '2026-10-01'
    assert 'expired' in thesis.observe_conditions({'conditions':[c]}, state())[0]['reason']
    assert thesis.observe_conditions({'conditions':[condition()]}, {})[0]['status'] == 'unknown'


def test_versioning_supersession_and_no_enforcement():
    run = str(uuid4())
    first = thesis.prepare_thesis({'rationale':'Research', 'conditions':[condition()]}, None, 'Buy', '2026-11-04', run)
    assert first == thesis.prepare_thesis({'rationale':'Research', 'conditions':[condition()]}, None, 'Buy', '2026-11-04', run)
    first['observations'] = thesis.observe_conditions(first, state())
    second = thesis.prepare_thesis({'conditions':[], 'disposition_reason':'Changed assumptions'}, first, 'Buy', '2026-11-04', str(uuid4()))
    assert second['parent_version_id'] == first['version_id']
    assert second['canonical_rating'] == 'Buy'
    assert second['prior_conditions'][0]['status'] == 'breached'
    assert second['prior_conditions'][0]['disposition'] == 'superseded'
    assert second['authority'] == 'candidate_advisory'


def test_malformed_optional_condition_is_visible_and_does_not_discard_rating():
    result = thesis.prepare_thesis({'conditions':[condition(), {'threshold':'NaN'}]}, None, 'Hold', '2026-11-04', str(uuid4()))
    assert len(result['conditions']) == 1 and result['warnings']
    assert result['canonical_rating'] == 'Hold'


def test_load_pending_publication_uses_actual_time_and_snapshot(monkeypatch, tmp_path):
    from tradingagents.memory import publication
    config = {'results_dir': str(tmp_path)}
    now = datetime(2026,11,4,22,tzinfo=UTC)
    monkeypatch.setattr(publication,'_utcnow',lambda: now)
    monkeypatch.setattr(publication,'get_current_date',lambda:'2026-11-04')
    item = thesis.prepare_thesis({'conditions':[condition()]}, None, 'Hold','2026-11-04',str(uuid4()))
    # Exercise existing content-addressed storage before parent adds snapshot projection.
    original = publication.evidence_snapshot
    monkeypatch.setattr(publication,'evidence_snapshot',lambda s: {**original(s),'thesis':item})
    record = publication.publish(config, {'run_id':str(uuid4()),'final_rating':'Hold',
        'final_trade_decision':'Rating: Hold','evidence_quality':{'status':'limited'}},'DOCN','2026-11-04')
    assert record['endpoints']['5_sessions']['status'] == 'pending'
    assert thesis.load_latest_thesis(config,'DOCN','2026-11-04T21:59:59Z') is None
    loaded = thesis.load_latest_thesis(config,'DOCN','2026-11-04T22:00:00Z')
    assert loaded['version_id'] == item['version_id']
    assert loaded['publication_id'] == record['decision_id']
    assert thesis.load_latest_thesis(config,'AAPL','2026-11-04') is None


@pytest.mark.parametrize('operator,value,status', [('>', '100', 'breached'), ('<=', '100','met'),
    ('<','100','breached'), ('==','100','met'), ('==','101','breached')])
def test_all_comparators(operator, value, status):
    row = condition()
    row['comparator'] = operator
    assert thesis.observe_conditions({'conditions':[row]}, state(value))[0]['status'] == status


def test_conflicting_values_and_invalid_precision_remain_unknown():
    data = state()
    fact = data['financial_evidence']['facts'][0]
    data['financial_evidence']['facts'].append({**fact, 'fact_id':'other', 'value':'105'})
    assert thesis.observe_conditions({'conditions':[condition()]}, data)[0]['status'] == 'unknown'
    assert thesis.observe_conditions({'conditions':[condition()]}, state('99','NaN'))[0]['status'] == 'unknown'


def test_explicit_override_reason_and_missing_reason_do_not_change_rating():
    first = thesis.prepare_thesis({'conditions':[condition()]},None,'Buy','2026-11-04',str(uuid4()))
    first['observations'] = thesis.observe_conditions(first,state())
    identifier = first['conditions'][0]['condition_id']
    second = thesis.prepare_thesis({'dispositions':[{'condition_id':identifier,'disposition':'overridden','reason':'New assumption'}]},
                                  first,'Buy','2026-11-04',str(uuid4()))
    assert second['prior_conditions'][0]['disposition'] == 'overridden'
    assert second['prior_conditions'][0]['disposition_reason'] == 'New assumption'
    missing = thesis.prepare_thesis({},first,'Buy','2026-11-04',str(uuid4()))
    assert missing['prior_conditions'][0]['disposition_reason'] == 'reason not supplied'
    assert missing['canonical_rating'] == 'Buy'
    assert missing['conditions'][0]['condition_id'] == identifier


def test_latest_legacy_snapshot_does_not_resurrect_old_thesis(monkeypatch):
    from tradingagents.memory import publication
    old = {'schema_version':1,'version_id':'old'}
    records = [{'decision_id':'1','published_at':'2026-11-04T20:00:00+00:00','sequence':1},
               {'decision_id':'2','published_at':None,'imported_at':'2026-11-04T21:00:00+00:00','sequence':2}]
    monkeypatch.setattr(publication,'list_records',lambda *_:records)
    monkeypatch.setattr(publication,'load_evidence',lambda _,r: {'thesis':old} if r['decision_id']=='1' else {})
    assert thesis.load_latest_thesis({},'DOCN','2026-11-04') is None
    assert thesis.load_latest_thesis({},'DOCN','2026-11-04T20:30:00Z')['version_id']=='old'
    with pytest.raises(ValueError,match='timezone'):
        thesis.load_latest_thesis({},'DOCN','2026-11-04T20:30:00')


def test_corrupt_snapshot_is_visible(monkeypatch):
    from tradingagents.memory import publication
    monkeypatch.setattr(publication,'list_records',lambda *_:[{'decision_id':'1','published_at':'2026-11-04T20:00:00+00:00','sequence':1}])
    monkeypatch.setattr(publication,'load_evidence',lambda *_:{'thesis':{}})
    with pytest.raises(ValueError,match='Invalid published thesis'):
        thesis.load_latest_thesis({},'DOCN','2026-11-04')


def test_specialized_metric_definition_cannot_borrow_consolidated_fact():
    row = condition()
    row['metric_definition'] = 'pure AI revenue'
    result = thesis.observe_conditions({'conditions':[row]}, state('150'))[0]
    assert result['status'] == 'unknown'
    assert 'definition' in result['reason']


def test_prior_render_preserves_condition_id_and_advisory_observation():
    item = thesis.prepare_thesis({'conditions':[condition()]},None,'Buy','2026-11-04',str(uuid4()))
    item['observations'] = thesis.observe_conditions(item,state('99'))
    rendered = thesis.render_prior_thesis(item)
    assert item['conditions'][0]['condition_id'] in rendered
    assert 'Comparison not satisfied; thesis role unspecified' in rendered and '99' in rendered and '2026-09-30' in rendered
    assert 'advisory' in rendered.lower() and 'not binding' in rendered.lower()
    assert 'Buy' in rendered and '2026-07-01' in rendered


def test_current_render_discloses_missing_reason_and_truncates_unvalidated_text():
    prior = thesis.prepare_thesis({'conditions':[condition()]},None,'Buy','2026-11-04',str(uuid4()))
    prior['observations'] = thesis.observe_conditions(prior,state())
    item = thesis.prepare_thesis({'rationale':'<script>target | ' + 'x'*1000, 'assumptions':['y'*1000]},
                                prior,'Buy','2026-11-04',str(uuid4()))
    rendered = thesis.render_thesis(item)
    assert 'Comparison not satisfied; thesis role unspecified' in rendered and 'kept' in rendered and 'reason not supplied' in rendered
    assert 'unvalidated research' in rendered.lower() and '[truncated]' in rendered
    assert '<script>' not in rendered and '&lt;script&gt;' in rendered and 'target |' not in rendered
    assert 'x'*301 not in rendered
    assert prior['version_id'] in rendered


def test_render_bounds_conditions_and_handles_absent_thesis():
    assert 'unavailable' in thesis.render_prior_thesis(None).lower()
    row = {**condition(), 'condition_id':'condition-example'}
    rendered = thesis.render_thesis({'conditions':[row]*10,'prior_conditions':[]})
    assert rendered.count('condition-example') == 8
    assert '2 additional conditions omitted' in rendered


@pytest.mark.parametrize('proposal', [None, 'bad-list', [{'threshold':'NaN'}]])
def test_missing_or_wholly_malformed_conditions_retain_prior(proposal):
    prior = thesis.prepare_thesis({'conditions':[condition()]},None,'Buy','2026-11-04',str(uuid4()))
    next_record = thesis.prepare_thesis({'conditions':proposal},prior,'Hold','2026-11-04',str(uuid4()))
    assert next_record['conditions'] == prior['conditions']
    assert next_record['canonical_rating'] == 'Hold'
    if proposal is not None:
        assert next_record['warnings']


def margin_state(profit='161070000', revenue='321192000', quantum=None):
    data = state(revenue, quantum)
    revenue_fact = data['financial_evidence']['facts'][0]
    data['financial_evidence']['facts'].append({**revenue_fact, 'fact_id':'gp','metric':'Gross Profit','value':profit})
    if quantum is not None:
        data['filing_fact_extraction']['rounding_quantum_by_fact']['gp'] = quantum
    return data


def margin_condition():
    return {**condition(), 'metric':'Gross Margin','metric_definition':'Gross Margin','unit':'percent','threshold':'53'}


def test_gross_margin_uses_two_canonical_inputs_and_preserves_lineage():
    observed = thesis.observe_conditions({'conditions':[margin_condition()]}, margin_state())[0]
    assert observed['status'] == 'breached'
    assert observed['observed_value'].startswith('50.147575')
    assert set(observed['fact_ids']) == {'f','gp'} and observed['source_ids'] == ['s']
    assert observed['formula_id'] == 'gross_margin_percent_v1'


@pytest.mark.parametrize('profit,revenue,quantum,status', [('53','100','2','unknown'),
    ('50','100','1','breached'), ('56','100','1','met'), ('-5','100','1','breached'),
    ('1','0',None,'unknown'), ('1','1','4','unknown')])
def test_gross_margin_bounds(profit,revenue,quantum,status):
    observed = thesis.observe_conditions({'conditions':[margin_condition()]},margin_state(profit,revenue,quantum))[0]
    assert observed['status'] == status


@pytest.mark.parametrize('field,value', [('unit','EUR'),('basis','adjusted'),('period_start','2026-01-01')])
def test_gross_margin_incompatible_inputs_stay_unknown(field,value):
    data = margin_state()
    data['financial_evidence']['facts'][1][field] = value
    assert thesis.observe_conditions({'conditions':[margin_condition()]},data)[0]['status'] == 'unknown'


def test_gross_margin_missing_or_competing_fact_stays_unknown():
    assert thesis.observe_conditions({'conditions':[margin_condition()]},state())[0]['status'] == 'unknown'
    data = margin_state()
    data['financial_evidence']['facts'].append({**data['financial_evidence']['facts'][1],'fact_id':'other','value':'170000000'})
    assert thesis.observe_conditions({'conditions':[margin_condition()]},data)[0]['status'] == 'unknown'


def test_margin_exact_threshold_and_nonquarter_condition():
    result = thesis.observe_conditions({'conditions':[margin_condition()]},margin_state('53','100'))[0]
    assert result['status'] == 'met'
    row = margin_condition()
    row['period_start'] = '2026-01-01'
    data = margin_state()
    for fact in data['financial_evidence']['facts']:
        fact['period_start'] = '2026-01-01'
    assert thesis.observe_conditions({'conditions':[row]},data)[0]['status'] == 'unknown'


def test_legacy_context_preserves_threshold_wording_without_authority():
    entries = [
        {'ticker':'DOCN','date':'2026-10-19','decision':'Q3 gross-margin line: <53% exit; 53-55.5 stay reduced; >=55.5 rebuild.'},
        {'ticker':'DOCN','date':'2026-11-05','decision':'Future text'},
        {'ticker':'AAPL','date':'2026-11-04','decision':'Other issuer'},
        {'ticker':'DOCN','date':'2026-11-04','decision':'Linked record','decision_id':'linked'},
    ]
    rendered = thesis.legacy_thesis_context(entries,'DOCN','2026-11-04')
    assert '53% exit' in rendered and '53-55.5 stay reduced' in rendered and '55.5 rebuild' in rendered
    assert 'publication time unknown' in rendered and 'binding authority unestablished' in rendered
    assert 'not a hard rule' in rendered
    assert all(text not in rendered for text in ('Future text','Other issuer','Linked record'))
    assert thesis.legacy_thesis_context(entries,'DOCN','2026-11-04',historical=True) == ''


def test_legacy_context_is_bounded_and_skips_invalid_entries():
    entries = [{'ticker':'DOCN','date':'2026-10-19','decision':'Q3 gross margin 53%. '+('x'*10000)},
               {'ticker':'DOCN','date':'invalid','decision':'Bad date'}]
    rendered = thesis.legacy_thesis_context(entries,'DOCN','2026-11-04')
    assert len(rendered) <= 2800 and '[truncated]' in rendered
    assert 'Q3 gross margin 53%' in rendered
    assert thesis.legacy_thesis_context(entries,'AAPL','2026-11-04') == ''


def test_retired_condition_is_removed_from_next_active_thesis():
    prior = thesis.prepare_thesis({'conditions':[condition()]},None,'Buy','2026-11-04',str(uuid4()))
    prior['observations'] = thesis.observe_conditions(prior,state())
    identifier = prior['conditions'][0]['condition_id']
    next_thesis = thesis.prepare_thesis({'dispositions':[{'condition_id':identifier,'disposition':'retired','reason':'No longer relevant'}]},
                                      prior,'Buy','2026-11-04',str(uuid4()))
    assert not next_thesis['conditions']
    assert next_thesis['prior_conditions'][0]['disposition'] == 'retired'
    assert next_thesis['canonical_rating'] == 'Buy'


def test_kept_but_omitted_condition_is_preserved_with_visible_warning():
    prior = thesis.prepare_thesis({'conditions':[condition()]},None,'Buy','2026-11-04',str(uuid4()))
    prior['observations'] = thesis.observe_conditions(prior,state())
    identifier = prior['conditions'][0]['condition_id']
    next_thesis = thesis.prepare_thesis({'conditions':[], 'dispositions':[{'condition_id':identifier,'disposition':'kept'}]},
                                      prior,'Hold','2026-11-04',str(uuid4()))
    assert next_thesis['conditions'] == prior['conditions']
    assert next_thesis['prior_conditions'][0]['disposition'] == 'kept'
    assert next_thesis['prior_conditions'][0]['disposition_reason'] == 'reason not supplied'
    assert next_thesis['warnings']


def test_duplicate_dispositions_preserve_prior_and_condition_limit():
    prior = thesis.prepare_thesis({'conditions':[condition()]},None,'Buy','2026-11-04',str(uuid4()))
    prior['observations'] = thesis.observe_conditions(prior,state())
    identifier = prior['conditions'][0]['condition_id']
    proposals = [{**condition(),'threshold':str(n)} for n in range(8)]
    item = thesis.prepare_thesis({'conditions':proposals, 'dispositions':[
        {'condition_id':identifier,'disposition':'kept'},
        {'condition_id':identifier,'disposition':'retired'}]},prior,'Hold','2026-11-04',str(uuid4()))
    assert len(item['conditions']) == 8
    assert item['conditions'][0] == prior['conditions'][0]
    assert item['prior_conditions'][0]['disposition'] == 'kept'
    assert item['prior_conditions'][0]['disposition_reason'] == 'reason not supplied'
    assert any('Ambiguous' in warning for warning in item['warnings'])
    assert any('limit' in warning for warning in item['warnings'])


def test_condition_identity_ignores_rationale_and_exact_decimal_spelling():
    variants = [condition(), {**condition(), 'rationale': 'Reworded', 'threshold': '100.00'},
                {**condition(), 'threshold': '1E+2'}]
    identifiers = [thesis.prepare_thesis({'conditions':[c]},None,'Hold','2026-11-04',str(uuid4()))['conditions'][0]['condition_id'] for c in variants]
    assert len(set(identifiers)) == 1
    merged = thesis.prepare_thesis({'conditions': variants},None,'Hold','2026-11-04',str(uuid4()))
    assert len(merged['conditions']) == 1
    base = {**condition(), 'threshold':'123456789012345678901234567891'}
    other = {**base, 'threshold':'123456789012345678901234567892'}
    assert thesis._id(thesis.ThesisCondition.model_validate(base)) != thesis._id(thesis.ThesisCondition.model_validate(other))


def test_existing_legacy_ids_survive_observation_and_reworded_proposal():
    legacy = {**condition(), 'condition_id':'condition-' + 'a'*24}
    prior = {'conditions':[legacy], 'canonical_rating':'Hold'}
    prior['observations'] = thesis.observe_conditions(prior,state())
    assert prior['observations'][0]['condition_id'] == legacy['condition_id']
    proposal = {**condition(), 'rationale':'New wording', 'threshold':'100.0', 'condition_id':'forged'}
    result = thesis.prepare_thesis({'conditions':[proposal], 'dispositions':[
        {'condition_id':legacy['condition_id'], 'disposition':'kept', 'reason':'Still material'}]},prior,'Hold','2026-11-04',str(uuid4()))
    assert len(result['conditions']) == 1
    assert result['conditions'][0]['condition_id'] == legacy['condition_id']
    assert result['prior_conditions'][0]['disposition_reason'] == 'Still material'


@pytest.mark.parametrize('change', [{'threshold':'101'}, {'expiry':'2027-01-31'}])
def test_changed_measurement_contract_is_new_condition(change):
    prior = thesis.prepare_thesis({'conditions':[condition()]},None,'Hold','2026-11-04',str(uuid4()))
    result = thesis.prepare_thesis({'conditions':[{**condition(), **change}]},prior,'Hold','2026-11-04',str(uuid4()))
    assert result['conditions'][0]['condition_id'] != prior['conditions'][0]['condition_id']


def test_duplicated_legacy_ids_coalesce_and_conflicting_alias_dispositions_preserve():
    first = {**condition(), 'condition_id':'condition-'+'a'*24}
    second = {**condition(), 'rationale':'Reworded', 'condition_id':'condition-'+'b'*24}
    prior = {'conditions':[first,second]}
    prior['observations'] = thesis.observe_conditions(prior,state())
    assert len(prior['observations']) == 1
    result = thesis.prepare_thesis({'conditions':[], 'dispositions':[
        {'condition_id':first['condition_id'],'disposition':'kept','reason':'Keep reasoning'},
        {'condition_id':second['condition_id'],'disposition':'retired','reason':'Retire reasoning'}]},prior,'Buy','2026-11-04',str(uuid4()))
    assert len(result['conditions']) == 1
    assert result['conditions'][0]['condition_id'] == first['condition_id']
    assert second['condition_id'] in result['conditions'][0]['condition_aliases']
    assert any('Ambiguous' in w for w in result['warnings'])
    supplied = result['prior_conditions'][0]['alias_dispositions']
    assert {d['reason'] for d in supplied} == {'Keep reasoning','Retire reasoning'}
    assert result['canonical_rating'] == 'Buy' and result['authority'] == 'candidate_advisory'


def test_alias_retirement_applies_to_one_measurement_contract():
    first = {**condition(), 'condition_id':'condition-'+'a'*24}
    second = {**condition(), 'rationale':'Reworded', 'condition_id':'condition-'+'b'*24}
    prior = {'conditions':[first,second]}
    prior['observations'] = thesis.observe_conditions(prior,state())
    result = thesis.prepare_thesis({'dispositions':[
        {'condition_id':second['condition_id'],'disposition':'retired','reason':'Retired contract'}]},prior,'Hold','2026-11-04',str(uuid4()))
    assert not result['conditions']
    assert result['prior_conditions'][0]['disposition'] == 'retired'


def test_malformed_alias_disposition_is_visible_without_changing_rating():
    prior = thesis.prepare_thesis({'conditions':[condition()]},None,'Hold','2026-11-04',str(uuid4()))
    identifier = prior['conditions'][0]['condition_id']
    item = thesis.prepare_thesis({'conditions':[], 'dispositions':[
        {'condition_id': {'invalid':'id'}, 'disposition':'retired'},
        {'condition_id':identifier,'disposition': {'invalid':'action'}}]},prior,'Sell','2026-11-04',str(uuid4()))
    assert len(item['conditions']) == 1 and item['canonical_rating'] == 'Sell'
    assert any('Ambiguous' in warning for warning in item['warnings'])


def test_published_same_run_projection_preserves_legacy_thesis_exactly():
    import hashlib
    import json
    from copy import deepcopy

    from tradingagents.agents.output_validation import _thesis_update

    run_id = str(uuid4())
    first = condition()
    second = {**condition(), 'rationale':'Reworded legacy duplicate'}
    rows = []
    for item in (first, second):
        payload = thesis.ThesisCondition.model_validate(item).model_dump(mode='json')
        identifier = 'condition-' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
        rows.append({**payload, 'condition_id':identifier})
    saved = thesis.prepare_thesis({'conditions':[first]},None,'Hold','2026-11-04',run_id)
    saved['conditions'] = rows
    inputs = {'run_id':run_id,'trade_date':'2026-11-04','final_rating':'Hold',
              'thesis_candidate':{'conditions':[first,second]}, 'thesis':saved,
              'thesis_version_id':saved['version_id'],
              'publication_record':{'decision_id':run_id, 'published_at':'2026-11-04T20:00:00+00:00',
                                    'record_sha256':'a'*64}}
    original = deepcopy(inputs)
    assert _thesis_update(inputs)['thesis'] == saved
    assert inputs == original
    # A genuinely new version fixes duplicates, but retains the earliest prior ID.
    next_thesis = thesis.prepare_thesis({'conditions':[second]},saved,'Hold','2026-11-04',str(uuid4()))
    assert len(next_thesis['conditions']) == 1
    assert next_thesis['conditions'][0]['condition_id'] == rows[0]['condition_id']


@pytest.mark.parametrize('role,value,expected', [
    ('supports_thesis', '99', 'Support condition breached'),
    ('supports_thesis', '101', 'Support condition met'),
    ('reconsideration_trigger', '99', 'Reconsideration trigger not met'),
    ('reconsideration_trigger', '101', 'Reconsideration trigger met'),
    ('unspecified', '99', 'Comparison not satisfied; thesis role unspecified'),
])
def test_condition_role_separates_comparison_from_thesis_meaning(role, value, expected):
    proposed = condition(thesis_role=role)
    prior = thesis.prepare_thesis({'conditions':[proposed]}, None, 'Underweight', '2026-11-04', str(uuid4()))
    prior['observations'] = thesis.observe_conditions(prior, state(value))
    assert len(prior['observations']) == 1
    assert expected in thesis.render_prior_thesis(prior)
    if role == 'reconsideration_trigger' and value == '99':
        assert 'breached' not in thesis.render_prior_thesis(prior)
    updated = thesis.prepare_thesis({}, prior, 'Underweight', '2026-11-04', str(uuid4()))
    assert expected in thesis.render_thesis(updated)
    assert updated['canonical_rating'] == 'Underweight'


def test_role_annotation_does_not_rekey_measurement_or_rewrite_prior_meaning():
    old = thesis.prepare_thesis({'conditions':[condition()]}, None, 'Underweight', '2026-11-04', str(uuid4()))
    old['observations'] = thesis.observe_conditions(old, state('99'))
    identity = old['conditions'][0]['condition_id']
    new = thesis.prepare_thesis({'conditions':[condition(thesis_role='reconsideration_trigger')],
        'dispositions':[{'condition_id':identity,'disposition':'kept','reason':'Keep measurement; explicitly classify its prospective role'}]},
        old,'Underweight','2026-11-04',str(uuid4()))
    assert new['conditions'][0]['condition_id'] == identity
    assert new['conditions'][0]['thesis_role'] == 'reconsideration_trigger'
    assert new['prior_conditions'][0].get('thesis_role', 'unspecified') == 'unspecified'


def test_inverse_margin_wording_has_explicit_support_or_reconsideration_meaning():
    source = margin_state()
    support = {**margin_condition(), 'comparator':'<', 'thesis_role':'supports_thesis'}
    trigger = {**margin_condition(), 'comparator':'>=', 'thesis_role':'reconsideration_trigger'}
    prior = thesis.prepare_thesis({'conditions':[support, trigger]},None,'Underweight','2026-11-04',str(uuid4()))
    prior['observations'] = thesis.observe_conditions(prior,source)
    text = thesis.render_prior_thesis(prior)
    assert 'Support condition met' in text
    assert 'Reconsideration trigger not met' in text
    assert 'Support condition breached' not in text
    assert prior['canonical_rating'] == 'Underweight'


def test_conflicting_roles_for_same_measurement_stay_unclassified():
    row = condition(thesis_role='supports_thesis')
    proposed = thesis.prepare_thesis({'conditions':[row,{**row,'thesis_role':'reconsideration_trigger'}]},
                                     None,'Hold','2026-11-04',str(uuid4()))
    assert len(proposed['conditions']) == 1
    assert proposed['conditions'][0]['thesis_role'] == 'unspecified'
    assert any('Conflicting roles' in item for item in proposed['warnings'])
