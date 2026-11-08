"""Audit responses are advisory records, outside the canonical decision."""
from copy import deepcopy
from unittest.mock import MagicMock

from tests.test_portfolio_valuation import decision, state
from tradingagents.agents import audit_pass
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.output_validation import enforce_publication


def audit_state():
    value = state()
    value['advisory_audit'] = {'status': 'completed with findings', 'findings': [
        {'role': 'research_manager', 'quoted_claim': f'Claim {n}', 'issue_type': 'unsupported_claim', 'explanation': f'Unverified {n}', 'evidence_label': None}
        for n in range(10)]}
    return value


def responses(value, count=10):
    return [{'finding_id': row['finding_id'], 'disposition': 'accepted' if n % 2 else 'rejected', 'reason': 'Evidence differs.'}
            for n, row in enumerate(audit_pass.prepare_audit_dispositions(value)['findings'][:count])]


def with_responses(value, rows):
    value = deepcopy(value)
    value.setdefault('unvalidated_outputs', {})['portfolio_manager'] = {'structured': {'time_horizon': '6 months', 'audit_dispositions': rows}}
    return value


def test_all_and_partial_dispositions_are_rendered_and_stable_under_reorder():
    value = audit_state()
    initial = audit_pass.prepare_audit_dispositions(value)
    reordered = deepcopy(value)
    reordered['advisory_audit']['findings'].reverse()
    assert {r['finding_id'] for r in initial['findings']} == {r['finding_id'] for r in audit_pass.prepare_audit_dispositions(reordered)['findings']}
    for count in (10, 4, 0):
        projected = audit_pass.prepare_audit_dispositions(with_responses(value, responses(value, count)))
        assert projected['answered_count'] == count
        assert projected['unanswered_count'] == 10-count
        rendered = audit_pass.render_advisory_audit(value['advisory_audit'], dispositions=projected)
        assert rendered.count('PM disposition: **unanswered**') == 10-count
        assert all(row['finding_id'] in rendered for row in initial['findings'])


def test_unknown_invalid_and_duplicate_responses_are_advisory_rejections():
    value = audit_state()
    rows = responses(value, 2)
    rows += [dict(rows[0]), {'finding_id': 'unknown', 'disposition': 'accepted', 'reason': 'No'}, {'bad': True}]
    projection = audit_pass.prepare_audit_dispositions(with_responses(value, rows))
    assert projection['answered_count'] == 1 and projection['unanswered_count'] == 9
    assert len(projection['rejected_responses']) == 4
    rendered = audit_pass.render_advisory_audit(value['advisory_audit'], dispositions=projection)
    assert 'unknown finding identifier' in rendered and 'duplicate finding identifier' in rendered


def test_malformed_response_does_not_discard_pm_or_call_again():
    llm = MagicMock()
    schema = None
    def bind(value):
        nonlocal schema
        schema = value
        return llm.bound
    llm.with_structured_output.side_effect = bind
    node = create_portfolio_manager(llm)
    llm.bound.invoke.return_value = schema.model_validate(decision().model_dump() | {'audit_dispositions': 'invalid list'})
    result = node(audit_state())
    assert result['final_rating'] == 'Buy'
    llm.bound.invoke.assert_called_once()
    llm.invoke.assert_not_called()
    assert 'PM disposition' not in result['final_trade_decision']
    assert audit_pass.prepare_audit_dispositions(audit_state() | result)['rejected_responses']


def test_unavailable_audit_does_not_request_responses():
    value = audit_state()
    value['advisory_audit'] = {'status': 'unavailable', 'findings': []}
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = decision()
    create_portfolio_manager(llm)(value)
    prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert 'one audit_dispositions response' not in prompt
    assert 'Portfolio Manager’s own text is not audited' in prompt


def test_publication_does_not_change_with_advisory_responses():
    from tests.test_decision_context import state as published_state
    value = published_state()
    value['advisory_audit'] = audit_state()['advisory_audit']
    unanswered = enforce_publication(value)
    answered_state = with_responses(value, responses(value))
    # Same horizon is required for the comparison to isolate audit responses.
    answered_state['unvalidated_outputs']['portfolio_manager']['structured']['time_horizon'] = '3–6 months'
    answered = enforce_publication(answered_state)
    assert 'PM responded to 0' in unanswered['final_trade_decision']
    assert 'PM responded to 10' in answered['final_trade_decision']
    assert answered['final_trade_decision'].replace('PM responded to 10', 'PM responded to 0') == unanswered['final_trade_decision']
    assert answered['target_validation'] == unanswered['target_validation']
    assert enforce_publication(answered_state | answered)['final_trade_decision'] == answered['final_trade_decision']


def test_pm_receives_stable_ids_and_responds_in_existing_call_only():
    from tradingagents.agents.schemas import RequiredHorizonPortfolioDecision
    value = audit_state()
    raw = decision().model_dump() | {'audit_dispositions': responses(value)}
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = RequiredHorizonPortfolioDecision.model_validate(raw)
    result = create_portfolio_manager(llm)(value)
    prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert all(row['finding_id'] in prompt for row in responses(value))
    assert audit_pass.prepare_audit_dispositions(value | result)['answered_count'] == 10
    assert 'Evidence differs.' not in result['final_trade_decision']
    llm.with_structured_output.return_value.invoke.assert_called_once()
    llm.invoke.assert_not_called()


def test_scope_changes_ids_but_legacy_saved_fake_id_does_not():
    value = audit_state()
    ids = [r['finding_id'] for r in audit_pass.prepare_audit_dispositions(value)['findings']]
    for finding in value['advisory_audit']['findings']:
        finding['finding_id'] = 'fake-model-id'
    assert ids == [r['finding_id'] for r in audit_pass.prepare_audit_dispositions(value)['findings']]
    value['trade_date'] = '2026-11-07'
    assert set(ids).isdisjoint(r['finding_id'] for r in audit_pass.prepare_audit_dispositions(value)['findings'])


def test_invalid_rows_and_unavailable_responses_are_rejected_without_authority():
    value = audit_state()
    valid = responses(value, 1)[0]
    for changed in ({'disposition': []}, {'reason': ''}, {'reason': 'x'*501}, {'extra': True}):
        projected = audit_pass.prepare_audit_dispositions(with_responses(value, [valid | changed]))
        assert projected['answered_count'] == 0 and projected['rejected_responses']
    value['advisory_audit']['status'] = 'unavailable'
    projected = audit_pass.prepare_audit_dispositions(with_responses(value, [valid]))
    assert projected['answered_count'] == 0
    assert 'not applicable' in projected['rejected_responses'][0]['reason']
