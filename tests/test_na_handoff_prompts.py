"""Rendered hand-offs preserve source conditions and avoid duplicated turns."""
from unittest.mock import MagicMock

import pytest

from tests.test_debate_opening import _REPORTS, _investment_state, _risk_state
from tradingagents.agents.document_questions import document_question_instruction
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.schemas import PortfolioDecision, TraderAction, TraderProposal
from tradingagents.agents.trader.trader import create_trader


@pytest.mark.parametrize('factory', [create_aggressive_debator, create_conservative_debator,
                                     create_neutral_debator])
def test_risk_receives_research_conditions_and_each_opponent_turn_once(factory):
    state = _risk_state(current_aggressive_response='Aggressive Analyst: A exact point.',
                        current_conservative_response='Conservative Analyst: C exact point.',
                        current_neutral_response='Neutral Analyst: N exact point.')
    risk = state['risk_debate_state']
    risk['history'] = '\n'.join(risk[key] for key in ('current_aggressive_response',
        'current_conservative_response', 'current_neutral_response'))
    state['investment_plan'] = 'RM conditions: margin below 50.15%; recovery to 55.5%.'
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content='Research condition discussed.')
    result = factory(llm)(state)
    prompt = llm.invoke.call_args.args[0]
    assert state['investment_plan'] in prompt
    assert 'drops or contradicts a research condition' in prompt
    for marker in ('A exact point.', 'C exact point.', 'N exact point.'):
        assert prompt.count(marker) == 1
    assert result['risk_debate_state']['history'].startswith(risk['history'])


@pytest.mark.parametrize('factory', [create_bull_researcher, create_bear_researcher])
def test_second_research_round_requires_numbered_point_response(factory):
    state = _investment_state('Opponent: 1. margin; 2. cash.')
    state['investment_debate_state']['count'] = 2
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content='1. Concede margin; 2. Answer cash.')
    factory(llm)(state)
    prompt = llm.invoke.call_args.args[0]
    assert "opponent's numbered points" in prompt
    assert 'answer or concede each' in prompt
    assert 'triggers' in prompt


def test_document_question_instruction_asks_for_short_phrases():
    instruction = document_question_instruction({'asset_type': 'stock',
                                                  '_document_question_final_turn': True})
    assert 'short filing search phrases (3–6 words)' in instruction


def test_trader_preserves_separate_levels_and_requires_band_table_citations():
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = TraderProposal(
        action=TraderAction.SELL, reasoning='Separate support levels.')
    create_trader(llm)({**_REPORTS, 'investment_plan': 'Underweight',
                        'market_report': 'Separate levels: 51.2 and 52.8.'})
    prompt = '\n'.join(row['content'] for row in llm.with_structured_output.return_value.invoke.call_args.args[0])
    assert 'do not merge separate levels into bands' in prompt
    assert 'Prior closes by price band' in prompt and 'cite' in prompt


def test_pm_sees_quality_at_rating_rules_and_evidence_based_horizon_override():
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = PortfolioDecision(
        rating='Hold', executive_summary='Balanced.', investment_thesis='Mixed evidence.',
        time_horizon='6 months')
    state = _risk_state()
    state.update(investment_plan='Research plan', trader_investment_plan='Hold',
                 evidence_quality={'status': 'limited', 'checks': [
                     {'status': 'pass'}, {'status': 'pass'}, {'status': 'unavailable'}]})
    create_portfolio_manager(llm)(state)
    prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert 'Evidence quality: limited (2 pass / 1 unavailable)' in prompt
    assert 'Attribute every price level and condition to the role that proposed it' in prompt
    assert 'specific evidence-based reason' in prompt and '6 months' in prompt
