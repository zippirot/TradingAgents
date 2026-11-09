"""RM interpretations stay separate from sealed deterministic retrieval results."""
from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from tests.test_document_followup import state_with_corpus
from tests.test_document_state_log_replay import _save_and_reload, _state
from tradingagents.agents.document_questions import (
    lookup_document_questions,
    render_document_followups,
)
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import ResearchPlan
from tradingagents.agents.state import AgentState
from tradingagents.reporting import evidence_snapshot


def state_and_payload():
    state = state_with_corpus()
    state['investment_debate_state'].update(history='Bull and bear disagree.', count=2)
    state.update(lookup_document_questions(state))
    payload = {'recommendation': 'Hold', 'rationale': 'Evidence remains balanced.',
               'strategic_actions': 'Wait for the missing evidence.',
               'followup_judgments': [
                   {'question_id': 'bull-1', 'classification': 'unanswered',
                    'explanation': 'The passage does not quantify lease commitments.'},
                   {'question_id': 'bear-1', 'classification': 'partially_answered',
                    'explanation': '$100 RPO appears in block-2, but its cause is unknown; the bear point remains open.'},
                   {'question_id': 'bear-2', 'classification': 'unanswered',
                    'explanation': 'Customer utilization is unknown.'}]}
    return state, payload


def test_rm_judgments_survive_typed_graph_and_card_without_changing_retrieval():
    state, payload = state_and_payload()
    sealed = deepcopy(state['document_followups'])
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = ResearchPlan.model_validate(payload)
    graph = StateGraph(AgentState)
    graph.add_node('Research Manager', create_research_manager(llm))
    graph.add_edge(START, 'Research Manager')
    graph.add_edge('Research Manager', END)
    result = graph.compile().invoke(state)
    assert result.get('document_followup_judgments') == payload['followup_judgments']
    assert result['document_followups'] == sealed
    prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert 'answered' in prompt and 'partially_answered' in prompt and 'unanswered' in prompt
    assert 'figure' in prompt and 'source' in prompt and 'bull or bear' in prompt
    assert 'unvalidated' in result['investment_plan']
    card = render_document_followups(result)
    assert 'Retrieval: relevant_passages_found' in card
    assert 'RM answer judgment (unvalidated): partially answered' in card
    assert '$100 RPO' in card
    assert 'RM answer judgment (unvalidated): unanswered' in card
    assert result['document_followups'] == sealed


def test_fallback_and_ambiguous_judgments_remain_unavailable():
    state, payload = state_and_payload()
    state['document_followup_judgments'] = payload['followup_judgments'] * 2
    assert 'RM answer judgment unavailable' in render_document_followups(state)
    assert 'RM answer judgment (unvalidated)' not in render_document_followups(state)
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError('unsupported')
    llm.invoke.return_value = MagicMock(content='Hold; follow-up interpretation not structured.')
    result = create_research_manager(llm)(state)
    assert result.get('document_followup_judgments') == []
    assert 'RM answer judgment unavailable' in render_document_followups({**state, **result})


def test_followup_judgment_schema_rejects_unknown_classification():
    _, payload = state_and_payload()
    payload['followup_judgments'][0]['classification'] = 'verified_fact'
    with pytest.raises(ValidationError):
        ResearchPlan.model_validate(payload)


def test_new_advisory_fields_survive_existing_full_state_log_and_evidence(tmp_path):
    state, _ = _state()
    _, payload = state_and_payload()
    state.update(document_followup_judgments=payload['followup_judgments'],
                 prompt_evidence_references={'exact-fact-id': 'F1', 'exact-source-id': 'S1'})
    saved = _save_and_reload(tmp_path, state)
    snapshot = evidence_snapshot(state)
    for key in ('document_followup_judgments', 'prompt_evidence_references'):
        assert saved.get(key) == snapshot.get(key) == state[key]


def _no_passage(state):
    for row in state['document_followups']['results']:
        row.update(status='no_relevant_passage', passages=[])
    return state['document_followups']


def test_partially_answered_without_passages_is_coerced_to_unanswered():
    from tradingagents.agents.document_questions import enforce_followup_judgments

    state, payload = state_and_payload()
    rows = enforce_followup_judgments(payload['followup_judgments'], _no_passage(state))
    bear = next(row for row in rows if row['question_id'] == 'bear-1')
    assert bear['classification'] == 'unanswered'
    assert bear['explanation'].startswith("No retrieved passage; model judgment 'partially_answered' discarded.")


def test_answered_with_passages_is_kept():
    from tradingagents.agents.document_questions import enforce_followup_judgments

    state, payload = state_and_payload()
    for row in state['document_followups']['results']:
        row['status'] = 'relevant_passages_found'
    assert enforce_followup_judgments(payload['followup_judgments'], state['document_followups']) == payload['followup_judgments']


def test_override_is_disclosed_on_card():
    from tradingagents.agents.document_questions import enforce_followup_judgments, render_document_followups

    state, payload = state_and_payload()
    state['document_followup_judgments'] = enforce_followup_judgments(
        payload['followup_judgments'], {'results': [{'question_id': 'bear-1', 'status': 'no_relevant_passage'}]})
    assert "No retrieved passage; model judgment 'partially_answered' discarded." in render_document_followups(state)


def test_override_records_one_observation_per_coercion(monkeypatch):
    from tradingagents.agents import document_questions as dq

    seen = []
    monkeypatch.setattr(dq, 'record_operation', lambda code, scope=None: seen.append((code, scope)))
    state, payload = state_and_payload()
    dq.enforce_followup_judgments(payload['followup_judgments'], _no_passage(state))
    assert seen == [('followup_judgment_overridden', 'bear-1')]


def test_rm_sentence_states_the_rule():
    import inspect

    from tradingagents.agents.managers import research_manager
    assert 'must be unanswered; any other classification is discarded' in inspect.getsource(research_manager)
