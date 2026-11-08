"""Offline regressions for explicit horizons and action-aware invalidation."""
from unittest.mock import MagicMock

from tests.test_decision_context import state as card_state
from tests.test_portfolio_valuation import decision, invoke, state
from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.schemas import (
    TraderProposal,
    label_legacy_trader_price,
    render_trader_proposal,
)


def test_new_schema_requires_horizon_and_missing_retains_rating_without_retry():
    result, llm = invoke(decision(time_horizon=None))
    schema = llm.with_structured_output.call_args.args[0].model_json_schema()
    assert 'time_horizon' in schema['required']
    assert result['final_rating'] == 'Buy'
    assert result['unvalidated_outputs']['portfolio_manager']['contract_version'] == 'decision_horizon_v1'
    assert 'incomplete' in result['final_trade_decision'].lower()
    llm.invoke.assert_not_called()


def test_new_missing_horizon_cannot_publish_valuation_or_infer_forecast_date():
    from tests.test_valuation import ev_request
    value = card_state()
    value['unvalidated_outputs']['portfolio_manager'] = {'contract_version': 'decision_horizon_v1', 'structured': {}}
    value['target_validation']['request'] = ev_request() | {'decision_date': '2027-01-19', 'rerating_assumption': 'Catalyst'}
    record = prepare_decision_context(value)
    assert record['rating'] == 'Underweight'
    assert record['target']['status'] == 'unsupported'
    assert record['basis'] == 'risk assessment'
    assert 'incomplete' in record['horizon']['text'].lower()
    published = enforce_publication(value)
    assert published['target_validation']['status'] == 'unsupported'
    assert '**Rating**: Underweight' in published['final_trade_decision']
    assert 'not specified' not in render_decision_context(record).split('**Horizon**:')[1].split('\n')[0]


def test_free_text_horizon_is_explicit_bounded_and_ambiguity_is_incomplete():
    for text, expected in [('Rating: Sell\n**Time Horizon**: 12 months', '6 months (configured default)'),
                           ('Rating: Sell\nTime Horizon: 12 months\nHorizon Reason: Refinancing next year', '12 months (pm override:'),
                           ('Rating: Sell\nA 2027 forecast supports my view.', 'incomplete'),
                           ('Rating: Sell\nTime Horizon: 3 months\nTime Horizon: 6 months', 'incomplete')]:
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError
        llm.invoke.return_value.content = text
        result = create_portfolio_manager(llm)(state())
        record = prepare_decision_context(card_state() | result)
        assert expected in record['horizon']['text'].lower()
        assert result['final_rating'] == 'Sell'
        llm.invoke.assert_called_once()


def test_sell_stop_is_advisory_only_buy_stop_and_legacy_entry_survive():
    proposal = TraderProposal(action='Sell', reasoning='Risk', stop_loss=90, reference_sale_level=70, entry_price=71)
    assert proposal.stop_loss is None
    assert proposal.advisory_invalidation_level == 90
    text = render_trader_proposal(proposal)
    assert '**Stop Loss**: 90' not in text
    assert '**Advisory Thesis Invalidation Level**: 90' in text
    assert 'short position' in text
    assert proposal.entry_price == 71 and proposal.reference_sale_level == 70
    buy = TraderProposal(action='Buy', reasoning='Thesis', stop_loss=60)
    assert buy.stop_loss == 60 and '**Stop Loss**: 60' in render_trader_proposal(buy)


def test_fallback_sell_stop_label_does_not_imply_execution_stop():
    text = label_legacy_trader_price('**Action**: Sell\n**Stop Loss**: 90\nFINAL TRANSACTION PROPOSAL: **SELL**')
    assert '**Stop Loss**: 90' not in text
    assert 'Advisory Thesis Invalidation Level' in text and 'short position' in text
    buy = '**Action**: Buy\n**Stop Loss**: 60'
    assert label_legacy_trader_price(buy) == buy


def test_fresh_explicit_horizon_stays_separate_from_supported_target_date():
    from tests.test_valuation import ev_request
    value = card_state()
    value['unvalidated_outputs']['portfolio_manager']['contract_version'] = 'decision_horizon_v1'
    value['target_validation']['request'] = ev_request() | {'decision_date': '2027-01-19', 'rerating_assumption': 'Catalyst'}
    record = prepare_decision_context(value)
    assert record['horizon']['text'] == '3–6 months'
    assert record['target']['status'] == 'supported'
    assert record['basis'] == 'risk assessment'  # direct legacy arithmetic, no case adoption
    assert enforce_publication(value)['target_validation']['status'] == 'supported'


def test_legacy_missing_horizon_does_not_invalidate_reexported_valuation():
    from tests.test_valuation import ev_request
    value = card_state()
    value['unvalidated_outputs']['portfolio_manager']['structured'] = {}
    value['target_validation']['request'] = ev_request() | {'decision_date': '2027-01-19', 'rerating_assumption': 'Catalyst'}
    assert enforce_publication(value)['target_validation']['status'] == 'supported'
    value['target_validation']['request'].pop('decision_date')
    assert 'legacy' in prepare_decision_context(value)['horizon']['text']


def test_new_missing_horizon_publication_is_repeatable_and_review_is_preserved():
    value = card_state()
    value['unvalidated_outputs']['portfolio_manager'] = {'contract_version': 'decision_horizon_v1', 'structured': {'time_horizon': 'forecast FY2027'}}
    first = enforce_publication(value)
    second = enforce_publication(value | first)
    assert first['final_trade_decision'] == second['final_trade_decision']
    assert first['target_validation'] == second['target_validation']
    value['evidence_quality'] = {'status': 'insufficient', 'checks': []}
    reviewed = enforce_publication(value)
    assert reviewed['decision_context']['rating'] == 'REVIEW'
    assert reviewed['target_validation']['status'] == 'unsupported'


def test_new_schema_omission_is_retained_for_validation_without_parse_retry():
    from tradingagents.agents.schemas import RequiredHorizonPortfolioDecision
    result = RequiredHorizonPortfolioDecision.model_validate({'rating': 'Underweight', 'executive_summary': 'Risk', 'investment_thesis': 'Thesis'})
    assert result.time_horizon is None and result.rating.value == 'Underweight'
