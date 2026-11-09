"""Audit independence follows completed provider identities, including fallbacks."""

from langchain_core.messages import AIMessage

from tradingagents.agents.audit_pass import create_advisory_audit, render_advisory_audit


class EmptyAudit:
    def __init__(self, actual=None):
        self.actual = actual

    def with_structured_output(self, schema, *, include_raw=True):
        return self

    def invoke(self, prompt):
        return {'raw': AIMessage(content='', response_metadata={
                    'model_name': self.actual} if self.actual else {}),
                'parsed': {'findings': []}, 'parsing_error': None}


def test_independence_uses_actual_completed_calls_and_fallback():
    state = {'market_report': 'Market claim', 'investment_plan': 'Manager claim',
             'trader_investment_plan': 'Trader claim',
             'model_call_metadata': {
                 'market': {'stage': 'Market Analyst', 'attempt_id': 'a',
                            'requested_model': 'requested/quick', 'actual_model': 'provider/model-a',
                            'status': 'completed'},
                 'manager': {'stage': 'Research Manager', 'attempt_id': 'a',
                             'requested_model': 'requested/deep', 'actual_model': 'provider/model-b',
                             'status': 'completed'},
                 'trader-failed': {'stage': 'Trader', 'attempt_id': 'a',
                                   'requested_model': 'provider/model-a', 'actual_model': None,
                                   'status': 'failed'},
                 'trader-fallback': {'stage': 'Trader', 'attempt_id': 'a',
                                     'requested_model': 'requested/fallback',
                                     'actual_model': 'provider/model-a', 'status': 'completed'},
             }}
    record = create_advisory_audit(EmptyAudit('provider/model-a'),
                                   deep_model_id='requested/deep',
                                   quick_model_id='requested/quick')(state)['advisory_audit']
    assert record['auditor_actual_model_id'] == 'provider/model-a'
    assert record['independence_by_role']['market_analyst'] == 'same model'
    assert record['independence_by_role']['research_manager'] == 'different model'
    assert record['independence_by_role']['trader'] == 'same model'
    assert record['model_identity_by_role']['trader']['requested_model'] == 'requested/fallback'
    assert record['model_identity_by_role']['trader']['actual_model'] == 'provider/model-a'
    assert 'portfolio_manager' not in record['independence_by_role']


def test_unknown_actual_identity_never_infers_from_configured_slots():
    state = {'market_report': 'Market claim', 'investment_plan': 'Manager claim',
             'model_call_metadata': {'market': {'stage': 'Market Analyst', 'attempt_id': 'a',
                 'requested_model': 'same', 'actual_model': None, 'status': 'completed'}}}
    record = create_advisory_audit(EmptyAudit(), deep_model_id='same',
                                   quick_model_id='same')(state)['advisory_audit']
    assert record['independence_by_role']['market_analyst'] == 'unknown'
    assert record['independence_by_role']['research_manager'] == 'unknown'
    assert 'unknown' in render_advisory_audit(record).lower()


def test_reordered_completed_calls_with_different_actual_models_are_ambiguous():
    calls = {
        'z-earlier': {'stage': 'Market Analyst', 'attempt_id': 'a',
                      'requested_model': 'requested/first', 'actual_model': 'provider/model-a',
                      'status': 'completed'},
        'a-later': {'stage': 'Market Analyst', 'attempt_id': 'a',
                    'requested_model': 'requested/fallback', 'actual_model': 'provider/model-b',
                    'status': 'completed'},
    }
    for ordered in (calls, dict(reversed(list(calls.items())))):
        state = {'market_report': 'Market claim', 'model_call_metadata': ordered}
        record = create_advisory_audit(EmptyAudit('provider/model-a'),
                                       deep_model_id='requested/deep',
                                       quick_model_id='requested/quick')(state)['advisory_audit']
        identity = record['model_identity_by_role']['market_analyst']
        assert identity['actual_model'] is None
        assert identity['requested_model'] is None
        assert identity['call_id'] is None
        assert {row['actual_model'] for row in identity['recorded_calls']} == {
            'provider/model-a', 'provider/model-b'}
        assert record['independence_by_role']['market_analyst'] == 'unknown'


def test_uniform_repeated_completed_calls_establish_actual_but_not_final_call():
    state = {'market_report': 'Market claim', 'model_call_metadata': {
        'z': {'stage': 'Market Analyst', 'attempt_id': 'first',
              'requested_model': 'requested/quick', 'actual_model': 'provider/model-a',
              'status': 'completed'},
        'a': {'stage': 'Market Analyst', 'attempt_id': 'second',
              'requested_model': 'requested/fallback', 'actual_model': 'provider/model-a',
              'status': 'completed'},
    }}
    record = create_advisory_audit(EmptyAudit('provider/model-a'),
                                   deep_model_id='requested/deep',
                                   quick_model_id='requested/quick')(state)['advisory_audit']
    identity = record['model_identity_by_role']['market_analyst']
    assert identity['actual_model'] == 'provider/model-a'
    assert identity['requested_model'] is None
    assert identity['attempt_id'] is None
    assert identity['call_id'] is None
    assert len(identity['recorded_calls']) == 2
    assert record['independence_by_role']['market_analyst'] == 'same model'


def test_missing_actual_in_one_completed_call_prevents_identity_inference():
    state = {'market_report': 'Market claim', 'model_call_metadata': {
        'one': {'stage': 'Market Analyst', 'attempt_id': 'a',
                'requested_model': 'configured/quick', 'actual_model': 'provider/model-a',
                'status': 'completed'},
        'two': {'stage': 'Market Analyst', 'attempt_id': 'a',
                'requested_model': 'configured/quick', 'actual_model': None,
                'status': 'completed'},
    }}
    record = create_advisory_audit(EmptyAudit('provider/model-a'),
                                   deep_model_id='configured/deep',
                                   quick_model_id='configured/quick')(state)['advisory_audit']
    identity = record['model_identity_by_role']['market_analyst']
    assert identity['actual_model'] is None
    assert identity['selection_basis'] == 'ambiguous completed calls'
    assert len(identity['recorded_calls']) == 2
    assert record['independence_by_role']['market_analyst'] == 'unknown'
    assert 'Call order is not retained' in render_advisory_audit(record)
