"""The decision is readable before the supporting evidence."""
from tests.test_decision_context import state
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.reporting import prepare_report_state


def inputs():
    value = state()
    value['canonical_financial_context'] = 'Evidence appendix ' * 3000
    value['unvalidated_outputs']['portfolio_manager']['structured'].update(
        executive_summary='The distinctive PM summary.', investment_thesis='The distinctive PM thesis.',
        no_case_reason='A complete reason ' * 40)
    value['investment_plan'] = 'Original manager plan.'
    return value


def test_decision_page_starts_with_rating_then_pm_summary():
    page = enforce_publication(inputs())['final_trade_decision']
    assert page.startswith('**Rating**: Underweight')
    assert 'The distinctive PM summary.' in '\n'.join(page.splitlines()[:40])
    assert page.index('**Horizon**') < page.index('The distinctive PM summary.') < page.index('The distinctive PM thesis.')
    assert page.index('The distinctive PM thesis.') < page.index('Advisory conditions') < page.index('Evidence appendix')


def test_no_placeholder_executive_summary():
    assert 'Model recommendation; financial evidence' not in enforce_publication(inputs())['final_trade_decision']


def test_manager_export_plan_first():
    value = prepare_report_state(inputs())
    assert value['investment_plan'].index('Original manager plan.') < value['investment_plan'].index('Evidence appendix')


def test_no_case_reason_not_truncated():
    value = inputs()
    value['unvalidated_outputs']['portfolio_manager']['case_contract'] = 1
    assert ('A complete reason ' * 40).strip() in enforce_publication(value)['final_trade_decision']


def test_risk_export_in_speaking_order(tmp_path):
    from tradingagents.reporting import write_report_tree
    value = inputs()
    value['risk_debate_state'] = {'history': 'Neutral first.\nAggressive second.\nNeutral last.',
        'neutral_history': 'Neutral role archive.', 'aggressive_history': 'Aggressive role archive.'}
    path = write_report_tree(value, 'DOCN', tmp_path, html=False)
    page = path.read_text()
    assert 'Neutral first.\nAggressive second.\nNeutral last.' in page
    assert 'Neutral role archive.' not in page
    assert 'Neutral role archive.' in (tmp_path / '4_risk/neutral.md').read_text()


def test_operational_headline_lists_all_fallbacks():
    from tests.test_operational_audit import observed, run_state
    from tradingagents.operational_audit import assess_audit, observation
    result = assess_audit(observed(*[observation(run_state(), stage, code='fallback_recovered')
                                    for stage in ('Market Analyst', 'News Analyst')]))
    assert 'Market Analyst' in result['consequence'] and 'News Analyst' in result['consequence']


def test_two_gross_margin_conditions_render_distinct_thresholds_and_all_four():
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )
    value = inputs()
    value['thesis'] = {'conditions': [
        {'condition_id': f'condition-{n}', 'metric': 'Gross Margin', 'comparator': '>=',
         'threshold': threshold, 'unit': 'percent'}
        for n, threshold in enumerate(('50.15', '55.5', '57.3', '60.1'))]}
    card = prepare_decision_context(value)
    page = render_decision_context(card)
    assert len(card['conditions']) == 4
    assert page.count('Advisory conditions at a glance') == 1
    for threshold in ('50.15', '55.5', '57.3', '60.1'):
        assert threshold + ' percent' in page
