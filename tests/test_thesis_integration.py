"""Thesis continuity survives canonical publication without enforcing a rating."""
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from tests.test_portfolio_valuation import state as portfolio_state
from tests.test_price_observation import install
from tests.test_thesis import condition, state as financial_state
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.schemas import PortfolioDecision
from tradingagents.dataflows.vendors.yahoo import price_observation as prices
from tradingagents.memory import publication, thesis
from tradingagents.report_html import _markdown, _render_agent_text


def test_malformed_optional_thesis_preserves_rating_and_raw_diagnostic():
    raw = {'conditions': [{'threshold': 'NaN'}]}
    decision = PortfolioDecision(rating='Buy', executive_summary='Research', investment_thesis='Hypothesis',
                                 thesis_candidate=raw)
    assert decision.rating.value == 'Buy'
    assert decision.thesis_candidate is None
    assert decision._unvalidated_thesis_candidate == raw


def test_advisory_breach_survives_publication_and_pending_restart(tmp_path, monkeypatch):
    now = datetime(2026, 11, 4, 22, tzinfo=UTC)
    monkeypatch.setattr(publication, '_utcnow', lambda: now)
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    config = {'results_dir': str(tmp_path)}
    prior = thesis.prepare_thesis({'rationale': 'Earlier research', 'conditions': [condition(thesis_role='supports_thesis')]},
                                 None, 'Buy', '2026-11-04', str(uuid4()))
    prior['observations'] = thesis.observe_conditions(prior, financial_state('99'))
    identifier = prior['conditions'][0]['condition_id']
    state = {**financial_state('99'), 'company_of_interest': 'DOCN', 'trade_date': '2026-11-04',
             'run_id': str(uuid4()), 'final_rating': 'Buy', 'prior_thesis': prior,
             'evidence_quality': {'status': 'limited'}, 'canonical_financial_context': 'Accepted Revenue 99 USD',
             'thesis_candidate': {'rationale': 'Research hypothesis', 'conditions': None,
                 'dispositions': [{'condition_id': identifier, 'disposition': 'overridden',
                                   'reason': 'Different forward assumption; not a verified fact'}]}}
    state.update(enforce_publication(state))
    assert state['final_rating'] == 'Buy'
    assert 'breached' in state['final_trade_decision'] and 'overridden' in state['final_trade_decision']
    assert 'Different forward assumption' in state['final_trade_decision']
    record = publication.publish(config, state, 'DOCN', '2026-11-04')
    assert record['thesis_version_id'] == state['thesis']['version_id']
    assert all(v['status'] == 'pending' for v in record['endpoints'].values())
    loaded = thesis.load_latest_thesis(config, 'DOCN', now)
    assert loaded['version_id'] == state['thesis']['version_id']
    assert loaded['prior_conditions'][0]['status'] == 'breached'
    assert thesis.load_latest_thesis(config, 'DOCN', '2026-11-04T21:59:59Z') is None


def test_three_condition_kinds_roundtrip_through_publication_and_next_run(tmp_path, monkeypatch):
    now = datetime(2026, 11, 4, 22, tzinfo=UTC)
    monkeypatch.setattr(publication, '_utcnow', lambda: now)
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    install(monkeypatch, now='2026-11-04T22:00:00+00:00')
    quote = prices.get_price_observation('DOCN', '2026-11-04')
    event = {'kind': 'event', 'description': '<script>Settlement announced</script>',
             'confirming_evidence': '8-K reporting note settlement',
             'expiry': '2027-01-31', 'rationale': 'Open question'}
    proposal = {'rationale': 'Research', 'conditions': [
        condition(), {'kind': 'price_level', 'comparator': '>=', 'threshold': '85',
                      'currency': 'USD', 'expiry': '2026-12-31', 'rationale': 'Watch close'},
        event, {**event, 'confirming_evidence': ''}]}
    decision = PortfolioDecision(rating='Hold', executive_summary='Wait',
                                 investment_thesis='Pending evidence', thesis_candidate=proposal)
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = decision
    input_state = {**portfolio_state(), **financial_state('99'),
                   'company_of_interest': 'DOCN', 'trade_date': '2026-11-04',
                   'price_observation': quote}
    pm_output = create_portfolio_manager(llm)(input_state)
    llm.with_structured_output.return_value.invoke.assert_called_once()
    llm.invoke.assert_not_called()
    assert pm_output['thesis_candidate'] == proposal
    assert pm_output['unvalidated_outputs']['portfolio_manager']['thesis_candidate'] == proposal
    run = {**input_state, **pm_output, 'run_id': str(uuid4()),
           'evidence_quality': {'status': 'limited'}, 'price_observation': quote,
           'canonical_financial_context': 'Accepted Revenue 99 USD'}
    run.update(enforce_publication(run))
    assert [row.get('kind', 'metric') for row in run['thesis']['conditions']] == [
        'metric', 'price_level', 'event']
    assert 'stated but not retained' in run['final_trade_decision']
    assert '<script>' not in run['final_trade_decision']
    assert '&lt;script&gt;' in run['final_trade_decision']
    html = _render_agent_text(_markdown(), run['final_trade_decision'])
    assert '<script>' not in html and 'Settlement announced' in html
    config = {'results_dir': str(tmp_path)}
    publication.publish(config, run, 'DOCN', '2026-11-04')
    loaded = thesis.load_latest_thesis(config, 'DOCN', now)
    assert [row.get('kind', 'metric') for row in loaded['conditions']] == [
        'metric', 'price_level', 'event']
    observed = thesis.observe_conditions(loaded, run)
    assert [row['status'] for row in observed] == ['breached', 'met', 'unobserved']
    context = thesis.render_prior_thesis({**loaded, 'observations': observed})
    assert 'completed close' in context and '8-K reporting note settlement' in context
    assert '<script>Settlement announced</script>' in context
    assert '&lt;script&gt;' not in context
    exported_context = _render_agent_text(_markdown(), context)
    assert '<script>' not in exported_context and '&lt;script&gt;' in exported_context
    next_llm = MagicMock()
    next_llm.with_structured_output.return_value.invoke.return_value = decision
    create_portfolio_manager(next_llm)({**input_state, 'thesis_context': context})
    next_prompt = next_llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert '<script>Settlement announced</script>' in next_prompt
    assert '8-K reporting note settlement' in next_prompt


def test_kept_prior_and_eight_new_conditions_survive_publication_and_next_run(tmp_path, monkeypatch):
    """A full PM proposal must not lose its price/events behind kept legacy rows."""
    from copy import deepcopy

    from tradingagents.agents.decision_context import prepare_decision_context
    from tradingagents.agents.schemas import ThesisProposal

    now = datetime(2026, 11, 4, 22, tzinfo=UTC)
    monkeypatch.setattr(publication, '_utcnow', lambda: now)
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    install(monkeypatch, now='2026-11-04T22:00:00+00:00')
    quote = prices.get_price_observation('DOCN', '2026-11-04')
    prior = thesis.prepare_thesis({'conditions': [
        {**condition(), 'threshold': str(100 + index)} for index in range(4)]},
        None, 'Hold', '2026-11-04', str(uuid4()))
    prior['observations'] = thesis.observe_conditions(prior, financial_state())
    original = deepcopy(prior)
    kept_ids = [row['condition_id'] for row in prior['conditions']]
    proposal = {'rationale': 'Retain earlier questions and add current advisory conditions',
        'dispositions': [{'condition_id': identifier, 'disposition': 'kept',
                          'reason': 'Still an open research question'} for identifier in kept_ids],
        'conditions': [*[{**condition(), 'threshold': str(200 + index)} for index in range(4)],
            *[{'kind': 'price_level', 'comparator': '>=', 'threshold': str(level),
               'currency': 'USD', 'expiry': '2026-12-31', 'rationale': 'Observe completed close'}
              for level in (80, 85)],
            *[{'kind': 'event', 'description': event,
               'confirming_evidence': 'Subsequent SEC filing', 'expiry': '2027-01-31',
               'rationale': 'Remain unobserved until explicitly disposed'}
              for event in ('Note settlement confirmed', 'Actual ATM issuance disclosed')]]}
    ThesisProposal.model_validate(proposal)
    run = {**portfolio_state(), **financial_state(),
           'company_of_interest': 'DOCN', 'trade_date': '2026-11-04',
           'run_id': str(uuid4()), 'final_rating': 'Hold',
           'price_observation': quote, 'prior_thesis': prior,
           'thesis_candidate': proposal, 'evidence_quality': {'status': 'limited'},
           'canonical_financial_context': 'Accepted Revenue 99 USD'}
    run.update(enforce_publication(run))
    conditions = run['thesis']['conditions']
    assert len(conditions) == 12
    assert [row['condition_id'] for row in conditions[:4]] == kept_ids
    assert [row.get('kind', 'metric') for row in conditions[-4:]] == [
        'price_level', 'price_level', 'event', 'event']
    assert 'Actual ATM issuance disclosed' in run['final_trade_decision']
    assert prior == original
    config = {'results_dir': str(tmp_path)}
    record = publication.publish(config, run, 'DOCN', '2026-11-04')
    loaded = thesis.load_latest_thesis(config, 'DOCN', now)
    assert loaded['publication_id'] == record['decision_id']
    assert loaded['conditions'] == conditions
    loaded['observations'] = thesis.observe_conditions(loaded, run)
    assert len(loaded['observations']) == 12
    rendered = thesis.render_prior_thesis(loaded)
    assert all(row['condition_id'] in rendered for row in conditions)
    assert 'Actual ATM issuance disclosed' in rendered
    dispositions = [{'condition_id': row['condition_id'], 'disposition': 'kept',
                     'reason': 'Keep this exact existing condition'} for row in conditions]
    ThesisProposal.model_validate({'conditions': None, 'dispositions': dispositions})
    following = thesis.prepare_thesis({'conditions': None, 'dispositions': dispositions},
        loaded, 'Hold', '2026-11-04', str(uuid4()),
        price_observation=quote, ticker='DOCN')
    assert following['conditions'] == conditions
    assert len(following['prior_conditions']) == 12
    card = prepare_decision_context({**run, 'prior_thesis': loaded, 'thesis': following})
    assert len(card['conditions']) == 12
    assert all(row['disposition'] == 'kept' for row in card['conditions'])


def test_new_proposal_limit_remains_eight_and_overflow_is_visible():
    import pytest
    from pydantic import ValidationError

    from tradingagents.agents.schemas import ThesisProposal

    raw = {'conditions': [{**condition(), 'threshold': str(index)} for index in range(9)]}
    with pytest.raises(ValidationError):
        ThesisProposal.model_validate(raw)
    run = {**portfolio_state(), **financial_state(), 'company_of_interest': 'DOCN',
           'trade_date': '2026-11-04', 'run_id': str(uuid4()), 'final_rating': 'Hold',
           'thesis_candidate': raw, 'evidence_quality': {'status': 'limited'},
           'canonical_financial_context': 'Accepted Revenue 99 USD'}
    run.update(enforce_publication(run))
    assert len(run['thesis']['conditions']) == 8
    assert '8' not in {row['threshold'] for row in run['thesis']['conditions']}
    assert 'stated but not retained' in run['final_trade_decision']
    assert 'new proposal limit is eight' in run['final_trade_decision']
    assert run['final_rating'] == 'Hold'
