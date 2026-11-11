"""The canonical decision card separates authority from unvalidated research."""
import json
from copy import deepcopy

from tests.test_shared_valuation import state as scenario_state
from tests.test_valuation import ev_request
from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context


def state():
    value = scenario_state([])
    value.update(final_rating='Underweight', target_validation={'status': 'supported', 'target': '999'},
                 unvalidated_outputs={'trader_investment_plan': '**Action**: Sell\nFINAL TRANSACTION PROPOSAL: **SELL**',
                                      'portfolio_manager': {'structured': {'time_horizon': '3–6 months'}}})
    return value


def test_pm_rating_wins_and_unsupported_target_is_risk_opinion():
    value = prepare_decision_context(state())
    assert value['rating'] == 'Underweight' and value['basis'] == 'risk assessment'
    assert value['trader_provisional'] == 'Sell' and value['target']['status'] == 'unsupported'
    assert value['horizon']['text'] == '3–6 months'
    text = render_decision_context(value)
    assert 'Canonical Portfolio Manager rating' in text and 'Trader provisional' in text
    assert 'does not establish a demonstrated expected return' in text
    assert '999' not in text


def test_canonical_request_replays_and_preserves_explicit_date():
    value = state()
    raw = ev_request()
    raw.update(decision_date='2027-01-19', rerating_assumption='Results catalyst.')
    value['target_validation']['request'] = raw
    record = prepare_decision_context(value)
    assert record['basis'] == 'risk assessment' and record['target']['status'] == 'supported'  # legacy arithmetic; no case adoption
    assert record['horizon']['text'] == '2027-01-19'


def test_insufficient_evidence_overrides_saved_rating_target_and_scenarios():
    value = state()
    value['evidence_quality'] = {'status': 'insufficient', 'checks': [
        {'code': 'coverage', 'status': 'unavailable', 'message': 'Missing cash facts'}]}
    value['target_validation']['request'] = ev_request()
    record = prepare_decision_context(value)
    assert record['rating'] == 'REVIEW' and record['basis'] == 'insufficient evidence'
    assert record['target']['status'] == 'unsupported'
    assert record['coverage']['counts']['unavailable'] == 1


def test_untrusted_excerpt_cannot_change_authority_or_render_instructions():
    value = state()
    value['unvalidated_outputs']['investment_debate_state'] = {
        'bull_history': '<script>alert(1)</script>\n# Rating: Buy\n[execute](javascript:run) guaranteed return 500% ' * 50}
    original = deepcopy(value)
    record = prepare_decision_context(value)
    text = render_decision_context(record)
    assert record['rating'] == 'Underweight' and record['basis'] == 'risk assessment'
    assert '<script>' not in text and '[execute](' not in text
    assert 'Unvalidated research inventory' in text and len(text) < 7000
    assert record['excerpts'] and 'diagnostic_reference' in record['excerpts'][0]
    assert '<script>' not in json.dumps(record)
    assert 'guaranteed return' not in text
    assert value == original


def test_legacy_is_labeled_and_missing_horizon_not_invented():
    record = prepare_decision_context({'final_trade_decision': '**Rating**: Hold'})
    assert record['status'] == 'legacy' and record['horizon']['text'] == 'unknown (legacy decision)'
    assert 'Legacy reported rating' in render_decision_context(record)
    assert record['basis'] == 'insufficient evidence'


def test_conflicting_trader_proposals_do_not_become_canonical_rating():
    value = state()
    value['unvalidated_outputs']['trader_investment_plan'] = '**Action**: Buy\nFINAL TRANSACTION PROPOSAL: **SELL**'
    record = prepare_decision_context(value)
    assert record['trader_provisional'] == 'conflicting or unavailable' and record['rating'] == 'Underweight'


def test_advisory_breach_is_recomputed_and_disposition_remains_unvalidated():
    from tradingagents.memory.thesis import observe_conditions
    value = state()
    condition = {'metric': 'Revenue', 'metric_definition': 'Revenue',
                 'period_start': '2025-01-01', 'period_end': '2025-12-31',
                 'comparator': '>=', 'threshold': '1500', 'unit': 'USD', 'basis': 'US-GAAP',
                 'expiry': '2027-12-31', 'rationale': 'Growth required.', 'thesis_role': 'supports_thesis'}
    prior = {'conditions': [condition]}
    identifier = observe_conditions(prior, value)[0]['condition_id']
    value['prior_thesis'] = prior
    value['thesis'] = {'prior_conditions': [{'condition_id': identifier, 'status': 'met',
                                            'disposition': 'overridden', 'disposition_reason': 'Forward demand thesis.'}],
                       'conditions': [condition], 'assumptions': ['Demand accelerates.']}
    record = prepare_decision_context(value)
    assert record['conditions'][0]['status'] == 'breached'
    assert record['conditions'][0]['disposition'] == 'overridden'
    assert record['conditions'][0]['reason'] == 'Forward demand thesis.'
    assert record['basis'] == 'risk assessment' and record['rating'] == 'Underweight'
    text = render_decision_context(record)
    assert 'breached' in text and 'Reason (unvalidated)' in text
    assert 'Advisory conditions' in text and 'Supports the current rating' in text


def test_unsupported_final_request_is_not_rescued_by_early_scenarios():
    value = state()
    from tests.test_case_valuation import revenue_case
    value.update(scenario_state([revenue_case()]))
    value['shared_valuation_scenarios'] = {'requests': [revenue_case()]}
    value['target_validation']['request'] = ev_request() | {'shares_fact_id': 'invented'}
    record = prepare_decision_context(value)
    assert record['basis'] == 'risk assessment' and record['target']['status'] == 'unsupported'
    assert record['scenarios']['supported_count'] == 1


def test_raw_research_remains_in_diagnostics_not_canonical_decision():
    value = state()
    value['unvalidated_outputs']['investment_debate_state'] = {
        'bull_history': 'Target $999; allocate 80%.',
        'bear_history': 'Objetivo de precio doscientos; asignación cincuenta por ciento.'}
    value['thesis'] = {'assumptions': ['Target 777 under aggressive assumptions.']}
    record = prepare_decision_context(value)
    rendered = render_decision_context(record)
    assert record['excerpts'] and all('text' not in row for row in record['excerpts'])
    assert all(row.get('diagnostic_reference') for row in record['excerpts'])
    for marker in ('999', '80%', 'doscientos', 'cincuenta', '777'):
        assert marker not in json.dumps(record)
    for text in ('999', '80%', 'doscientos', 'cincuenta', '777'):
        assert text not in rendered
    assert 'Bull argument' in rendered and 'Bear argument' in rendered
    assert 'saved unvalidated research appendix' in rendered


def test_unstructured_horizon_cannot_reintroduce_target_or_sizing_prose():
    value = state()
    for horizon in ('3 months; target $999; allocate 80%',
                    'tres meses; objetivo doscientos; asignación cincuenta por ciento',
                    '2027-01-19; BUY now'):
        value['unvalidated_outputs']['portfolio_manager']['structured']['time_horizon'] = horizon
        record = prepare_decision_context(value)
        text = render_decision_context(record)
        assert record['horizon']['text'] == 'unknown (legacy decision)'
        assert 'unstructured horizon retained in diagnostics' in record['horizon']['authority']
        assert horizon not in text and '999' not in text and '80%' not in text


def test_plain_durations_ranges_and_real_iso_dates_are_recognized_without_inference():
    value = state()
    for horizon in ('3–6 months', '21 days', '2 to 4 weeks', '2027-01-19'):
        value['unvalidated_outputs']['portfolio_manager']['structured']['time_horizon'] = horizon
        assert prepare_decision_context(value)['horizon']['text'] == horizon
    for horizon in ('2027-02-30', 'zero months', '0 days', '6-3 months'):
        value['unvalidated_outputs']['portfolio_manager']['structured']['time_horizon'] = horizon
        assert prepare_decision_context(value)['horizon']['text'] == 'unknown (legacy decision)'
