"""Thesis continuity survives canonical publication without enforcing a rating."""
from datetime import UTC, datetime
from uuid import uuid4

from tests.test_thesis import condition, state as financial_state
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.schemas import PortfolioDecision
from tradingagents.memory import publication, thesis


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
    prior = thesis.prepare_thesis({'rationale': 'Earlier research', 'conditions': [condition()]},
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
