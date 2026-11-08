"""The bounded audit prioritizes each role's verified final turn."""

from tests.test_advisory_audit import FakeModel
from tests.test_debate_opening import _capturing_llm, _investment_state
from tradingagents.agents.audit_pass import _contexts, create_advisory_audit
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher


def test_research_producers_retain_exact_final_turns():
    first = create_bull_researcher(_capturing_llm({}))(_investment_state(''))['investment_debate_state']
    second = create_bear_researcher(_capturing_llm({}))({**_investment_state(''),
        'investment_debate_state': first})['investment_debate_state']
    assert second['current_bull_response'] == first['current_bull_response']
    assert second['bull_history'].endswith(second['current_bull_response'])
    assert second['bear_history'].endswith(second['current_bear_response'])


def test_final_turn_of_each_debate_role_is_prioritized_and_coverage_disclosed():
    long_earlier = 'earlier-head ' + 'x' * 7000 + ' earlier-tail'
    final = 'FINAL TURN: supported contrary evidence'
    state = {'investment_debate_state': {
        'bull_history': long_earlier + final, 'current_bull_response': final,
        'bear_history': long_earlier + final, 'current_bear_response': final},
        'risk_debate_state': {
            'aggressive_history': long_earlier + final, 'current_aggressive_response': final,
            'conservative_history': long_earlier + final, 'current_conservative_response': final,
            'neutral_history': long_earlier + final, 'current_neutral_response': final}}
    _, roles = _contexts(state)
    for role in ('bull_researcher', 'bear_researcher', 'aggressive_risk_analyst',
                 'conservative_risk_analyst', 'neutral_risk_analyst'):
        assert final in roles[role]
        assert roles[role].startswith('earlier-head')
        assert 'earlier-tail' in roles[role]
        assert len(roles[role]) <= 6000
    model = FakeModel({'findings': []})
    record = create_advisory_audit(model, deep_model_id='deep', quick_model_id='quick')(state)['advisory_audit']
    for role in ('bull_researcher', 'bear_researcher', 'aggressive_risk_analyst'):
        coverage = record['role_input_coverage'][role]
        assert coverage['total_characters'] > coverage['audited_characters']
        assert 'final_turn' in coverage['segments']


def test_oversized_final_turn_gets_head_and_tail_within_budget():
    final = 'final-head ' + 'z' * 7000 + ' final-tail'
    state = {'risk_debate_state': {'aggressive_history': 'old argument\n' + final,
                                   'current_aggressive_response': final}}
    _, roles = _contexts(state)
    assert roles['aggressive_risk_analyst'].startswith('final-head')
    assert roles['aggressive_risk_analyst'].endswith('final-tail')
    assert 'old argument' not in roles['aggressive_risk_analyst']
    assert len(roles['aggressive_risk_analyst']) <= 6000
    record = create_advisory_audit(FakeModel({'findings': []}), deep_model_id='d',
                                   quick_model_id='q')(state)['advisory_audit']
    coverage = record['role_input_coverage']['aggressive_risk_analyst']
    assert coverage['segments'] == ['final_head', 'final_tail']
    assert coverage['earlier_characters_audited'] == 0


def test_legacy_history_without_final_turn_metadata_discloses_unknown():
    state = {'investment_debate_state': {'bull_history': 'old ' + 'x' * 7000 + ' latest'}}
    record = create_advisory_audit(FakeModel({'findings': []}), deep_model_id='d',
                                   quick_model_id='q')(state)['advisory_audit']
    coverage = record['role_input_coverage']['bull_researcher']
    assert coverage['final_turn_status'] == 'unknown'
    assert coverage['total_characters'] > coverage['audited_characters']


def test_nearly_full_final_turn_discloses_tail_only_earlier_coverage():
    final = 'F' * 5998
    state = {'risk_debate_state': {'aggressive_history': 'earlier ' * 1000 + final,
                                   'current_aggressive_response': final}}
    record = create_advisory_audit(FakeModel({'findings': []}), deep_model_id='d',
                                   quick_model_id='q')(state)['advisory_audit']
    assert record['role_input_coverage']['aggressive_risk_analyst']['segments'] == [
        'earlier_tail', 'final_turn']
