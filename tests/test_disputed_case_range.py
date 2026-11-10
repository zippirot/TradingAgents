"""Accepted case-specific audit advice flags a displayed case; it never removes it or alters its arithmetic."""
from copy import deepcopy
from decimal import Decimal

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


def test_accepted_case_stays_in_range_flagged_and_retained():
    value = inputs()
    original = deepcopy(value)
    card = prepare_decision_context(value)
    group = card['case_groups'][0]
    targets = sorted(Decimal(row['result']['target']) for row in value['shared_valuation_scenarios']['rows'])
    assert (Decimal(group['low']), Decimal(group['high'])) == (targets[0], targets[1]) and targets[0] != targets[1]
    assert len(group['cases']) == 2 and group['cases'][0]['disputed_by']
    page = render_decision_context(card)
    assert 'flagged by accepted audit finding' in page and 'shown in the conditional range' in page
    assert 'excluded from conditional range' not in page and '**Conditional case range**' in page
    assert 'supported scenarios 2 (1 flagged by an accepted audit finding)' in page
    assert enforce_publication(value)['shared_valuation_scenarios']['rows'][0]['result'] == original['shared_valuation_scenarios']['rows'][0]['result']
    assert value == original


def test_exact_quote_fallback_and_rejected_finding():
    quoted = prepare_decision_context(inputs(linked=False))['scenarios']
    assert (quoted['supported_count'], quoted['disputed_count']) == (2, 1)
    rejected = prepare_decision_context(inputs(disposition='rejected'))['scenarios']
    assert (rejected['supported_count'], rejected['disputed_count']) == (2, 0)


def test_all_flagged_still_shows_the_whole_range_never_one_survivor():
    card = prepare_decision_context(inputs(all_cases=True))
    assert (card['scenarios']['supported_count'], card['scenarios']['disputed_count']) == (2, 2)
    group = card['case_groups'][0]
    assert group['low'] is not None and Decimal(group['low']) < Decimal(group['high'])
    page = render_decision_context(card)
    assert '**Conditional case range**' in page and page.count('shown in the conditional range') == 2


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
    assert 'excluded from conditional range' not in adopted_line
    projected = enforce_publication(value)
    assert projected['target_validation']['status'] == 'supported'
    page = projected['final_trade_decision']
    assert page.index('Disputed PM-adopted calculation') < page.index('**Conditional valuation sensitivity**')
    assert value['shared_valuation_scenarios'] == original['shared_valuation_scenarios']


def test_each_decision_card_statement_is_its_own_paragraph():
    """Run d58117ef's card ran change notes, basis, range and coverage together as one block."""
    from tradingagents.agents.decision_context import _spaced

    assert _spaced(['**A**: one', '- x', '- y', 'Changed since: z', 'No new filing.', '**B**: two']) == (
        '**A**: one\n\n- x\n- y\n\nChanged since: z\n\nNo new filing.\n\n**B**: two')
    assert _spaced(['### Card', '', 'a\nb']) == '### Card\n\na\n\nb'
    lines = render_decision_context(prepare_decision_context(inputs())).split('\n')
    for label in ('**Basis**', '**Horizon**', '**Evidence coverage**', '**Valuation availability**',
                  '**Trader provisional action**'):
        index = next(i for i, line in enumerate(lines) if line.startswith(label))
        assert lines[index - 1] == '', label
