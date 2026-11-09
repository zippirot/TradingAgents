"""Accepted case-specific audit advice changes the displayed range, not arithmetic."""
from copy import deepcopy

from tests.test_case_valuation import revenue_case
from tests.test_shared_valuation import state
from tradingagents.agents.audit_pass import prepare_audit_dispositions
from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.shared_valuation import prepare_shared_valuation


def inputs(*, linked=True, disposition='accepted', all_cases=False):
    low, high = revenue_case(), revenue_case()
    high['name'] = 'Higher'
    high['request']['multiple'] = '4'
    low['request']['multiple_rationale'] = 'The distinct equipment assumption.'
    value = state([low, high])
    value.update(final_rating='Hold', unvalidated_outputs={'portfolio_manager': {'structured': {'time_horizon': '6 months'}}})
    value['shared_valuation_scenarios'] = prepare_shared_valuation(value)
    finding = {'role': 'fundamentals', 'quoted_claim': low['request']['multiple_rationale'],
               'issue_type': 'numerical_inconsistency', 'explanation': 'Equipment assumption disputed', 'evidence_label': None}
    if linked:
        finding['case_id'] = value['shared_valuation_scenarios']['rows'][0]['case_id']
    findings = [finding]
    if all_cases:
        findings.append({**finding, 'case_id': value['shared_valuation_scenarios']['rows'][1]['case_id']})
    value['advisory_audit'] = {'status': 'completed with findings', 'findings': findings}
    value['unvalidated_outputs']['portfolio_manager']['structured']['audit_dispositions'] = [
        {'finding_id': f['finding_id'], 'disposition': disposition, 'reason': 'Reviewed'}
        for f in prepare_audit_dispositions(value)['findings']]
    return value


def test_accepted_case_excluded_from_range_but_retained():
    value = inputs()
    original = deepcopy(value)
    group = prepare_decision_context(value)['case_groups'][0]
    assert group['low'] == group['high'] == value['shared_valuation_scenarios']['rows'][1]['result']['target']
    assert len(group['cases']) == 2 and group['cases'][0]['disputed_by']
    assert 'excluded from conditional range' in render_decision_context(prepare_decision_context(value))
    assert enforce_publication(value)['shared_valuation_scenarios']['rows'][0]['result'] == original['shared_valuation_scenarios']['rows'][0]['result']
    assert value == original


def test_exact_quote_fallback_and_rejected_finding():
    assert prepare_decision_context(inputs(linked=False))['scenarios']['supported_count'] == 1
    assert prepare_decision_context(inputs(disposition='rejected'))['scenarios']['supported_count'] == 2


def test_all_disputed_has_no_range():
    card = prepare_decision_context(inputs(all_cases=True))
    assert card['scenarios']['supported_count'] == 0
    assert card['case_groups'][0]['low'] is None
    assert 'No undisputed conditional range' in render_decision_context(card)


def test_adopted_disputed_case_keeps_supported_value_and_is_visibly_marked():
    value = inputs()
    original = deepcopy(value)
    row = value['shared_valuation_scenarios']['rows'][0]
    request = {'method': 'case', 'case_id': row['case_id'], 'version': row['version'],
               'rerating_assumption': 'none'}
    value['target_validation'] = {'request': request}
    value['unvalidated_outputs']['portfolio_manager'].update(
        case_contract=1, valuation_request=request)
    card = prepare_decision_context(value)
    assert card['rating'] == 'Hold'
    assert card['target']['status'] == 'supported'
    assert card['adopted_case']['value'] == row['result']['target']
    assert card['adopted_case']['disputed_by']
    adopted_line = next(line for line in render_decision_context(card).splitlines()
                        if line.startswith('Adopted '))
    assert 'disputed by accepted audit finding' in adopted_line
    assert 'excluded from conditional range' in adopted_line
    projected = enforce_publication(value)
    assert projected['target_validation']['status'] == 'supported'
    page = projected['final_trade_decision']
    assert page.index('Disputed PM-adopted calculation') < page.index('**Conditional valuation sensitivity**')
    assert value['shared_valuation_scenarios'] == original['shared_valuation_scenarios']
