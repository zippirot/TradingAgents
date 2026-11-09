"""Portable continuity checks for legacy and newly stated advisory conditions."""
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tests.test_price_observation import install
from tests.test_thesis import condition, state
from tradingagents.agents.schemas import PortfolioDecision, ThesisProposal
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.dataflows.vendors.yahoo import price_observation as prices
from tradingagents.memory import thesis


def test_legacy_metric_identity_and_shape():
    old = condition()
    saved = thesis.prepare_thesis({'conditions': [old]}, None, 'Hold', '2026-11-04', str(uuid4()))
    row = saved['conditions'][0]
    assert 'kind' not in row
    payload = {k: v for k, v in row.items() if k not in {'condition_id', 'rationale', 'thesis_role'}}
    payload['threshold'] = [0, [1], 2]
    expected = 'condition-' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    assert row['condition_id'] == expected


def test_event_and_invalid_sibling_are_visible():
    event = {'thesis_role': 'reconsideration_trigger', 'kind': 'event', 'description': 'Settlement announced',
             'confirming_evidence': '8-K reporting note settlement',
             'expiry': '2027-01-31', 'rationale': 'Open question'}
    saved = thesis.prepare_thesis({'conditions': [event, {**event, 'confirming_evidence': ''},
                                                  {**event, 'description': '   '},
                                                  {**event, 'confirming_evidence': '   '}]},
                                  None, 'Hold', '2026-11-04', str(uuid4()))
    assert saved['conditions'][0]['kind'] == 'event'
    assert len(saved['conditions']) == 1
    assert sum('stated but not retained' in item for item in saved['warnings']) == 3
    assert 'stated but not retained' in thesis.render_thesis(saved)
    observed = thesis.observe_conditions(saved, {})
    assert observed[0]['status'] == 'unobserved'
    assert '8-K' in thesis.render_prior_thesis({**saved, 'observations': observed})


def test_prompt_context_is_plain_text_and_rationale_is_longer():
    prior = {'version_id': 'v', 'canonical_rating': 'Hold',
             'rationale': '8-K <note> & ticker_name [evidence] ' + 'x' * 350,
             'conditions': []}
    rendered = thesis.render_prior_thesis(prior)
    assert '8-K <note> & ticker_name [evidence]' in rendered
    assert 'x' * 350 in rendered
    assert '&lt;' not in rendered and r'ticker\_name' not in rendered


def test_pm_keeps_valid_event_when_sibling_invalid():
    event = {'thesis_role': 'reconsideration_trigger', 'kind': 'event', 'description': 'Settlement announced',
             'confirming_evidence': '8-K reporting note settlement',
             'expiry': '2027-01-31', 'rationale': 'Open question'}
    raw = {'conditions': [condition(), event, {**event, 'confirming_evidence': ''}]}
    decision = PortfolioDecision(rating='Hold', executive_summary='Wait',
                                 investment_thesis='Pending evidence', thesis_candidate=raw)
    assert decision.thesis_candidate is None
    assert decision._unvalidated_thesis_candidate == raw
    saved = thesis.prepare_thesis(decision._unvalidated_thesis_candidate, None, 'Hold',
                                  '2026-11-04', str(uuid4()))
    assert [row.get('kind', 'metric') for row in saved['conditions']] == ['metric', 'event']
    assert 'stated but not retained' in thesis.render_thesis(saved)


def test_pm_schema_accepts_all_three_kinds():
    proposal = ThesisProposal.model_validate({'conditions': [
        condition(),
        {'thesis_role': 'reconsideration_trigger', 'kind': 'price_level', 'comparator': '<', 'threshold': '80',
         'currency': 'USD', 'expiry': '2026-12-31', 'rationale': 'Watch close'},
        {'thesis_role': 'reconsideration_trigger', 'kind': 'event', 'description': 'Settlement announced',
         'confirming_evidence': '8-K reporting settlement',
         'expiry': '2027-01-31', 'rationale': 'Open question'}]})
    assert [item.kind for item in proposal.conditions] == ['metric', 'price_level', 'event']


def test_price_level_uses_only_validated_completed_close(monkeypatch):
    install(monkeypatch, now='2026-11-04T22:00:00+00:00')
    quote = prices.get_price_observation('DOCN', '2026-11-04')
    price = {'thesis_role': 'reconsideration_trigger', 'kind': 'price_level', 'comparator': '>=', 'threshold': '85',
             'currency': 'USD', 'expiry': '2026-12-31', 'rationale': 'Watch close'}
    saved = thesis.prepare_thesis({'conditions': [price]}, None, 'Hold', '2026-11-04',
                                  str(uuid4()), price_observation=quote, ticker='DOCN')
    assert saved['conditions'][0]['kind'] == 'price_level'
    run = {'company_of_interest': 'DOCN', 'trade_date': '2026-11-04', 'price_observation': quote}
    assert thesis.observe_conditions(saved, run)[0]['status'] == 'met'
    assert thesis.observe_conditions(saved, {**run, 'price_observation': None})[0]['status'] == 'unobserved'
    wrong = {**saved, 'conditions': [{**saved['conditions'][0], 'currency': 'EUR'}]}
    assert thesis.observe_conditions(wrong, run)[0]['status'] == 'unobserved'
    rejected = thesis.prepare_thesis({'conditions': [{**price, 'currency': 'EUR'}]}, None,
                                     'Hold', '2026-11-04', str(uuid4()),
                                     price_observation=quote, ticker='DOCN')
    assert not rejected['conditions'] and 'stated but not retained' in thesis.render_thesis(rejected)


def test_future_metric_period_is_not_yet_reported_without_inventing_filing_date():
    future = condition()
    future['period_end'] = '2026-12-31'
    observed = thesis.observe_conditions({'conditions': [future]}, state())
    assert observed[0]['status'] == 'unknown'
    assert observed[0]['reason'] == 'Period not yet reported; measurement period ends after analysis date'
    missing = thesis.observe_conditions({'conditions': [condition()]}, state())
    assert 'not yet reported' not in missing[0]['reason'].lower()


def test_future_filing_date_is_not_accepted_as_retained_metadata():
    attempted = state()
    attempted['financial_evidence']['sources'][0]['filed_date'] = '2026-11-05'
    with pytest.raises(ValueError, match='filing cutoff mismatch'):
        EvidencePackage.model_validate(attempted['financial_evidence'])
    observed = thesis.observe_conditions({'conditions': [condition()]}, attempted)
    assert observed[0]['status'] == 'unknown'
    assert 'not yet reported' not in observed[0]['reason'].lower()


def test_expired_price_condition_is_unobserved(monkeypatch):
    install(monkeypatch, now='2026-11-04T20:00:00+00:00')
    quote = prices.get_price_observation('DOCN', '2026-11-04')
    assert quote['session_date'] == '2026-11-03'
    price = {'thesis_role': 'reconsideration_trigger', 'kind': 'price_level', 'comparator': '>=', 'threshold': '80',
             'currency': 'USD', 'expiry': '2026-12-31', 'rationale': 'Watch close'}
    run = {'company_of_interest': 'DOCN', 'trade_date': '2026-11-04', 'price_observation': quote}
    saved = thesis.prepare_thesis({'conditions': [price]}, None, 'Hold', '2026-11-04',
                                  str(uuid4()), price_observation=quote, ticker='DOCN')
    assert thesis.observe_conditions(saved, run)[0]['status'] == 'met'
    previous = {**saved, 'as_of': '2026-11-02', 'conditions': [
        {**saved['conditions'][0], 'expiry': '2026-11-03'}]}
    assert thesis.observe_conditions(previous, run)[0]['status'] == 'unobserved'


def test_retained_price_condition_uses_weekend_completed_close(monkeypatch):
    install(monkeypatch, now='2026-10-29T22:00:00+00:00',
            dates=('2026-10-29',), closes=(81,),
            metadata={'currentTradingPeriod': {'regular': {
                'end': datetime(2026, 10, 29, 21, tzinfo=UTC)}}})
    initial_quote = prices.get_price_observation('DOCN', '2026-10-29')
    price = {'thesis_role': 'reconsideration_trigger', 'kind': 'price_level', 'comparator': '>=', 'threshold': '80',
             'currency': 'USD', 'expiry': '2026-12-31', 'rationale': 'Watch close'}
    original = thesis.prepare_thesis({'conditions': [price]}, None, 'Hold', '2026-10-29',
                                     str(uuid4()), price_observation=initial_quote, ticker='DOCN')
    carried = thesis.prepare_thesis({'conditions': None}, original, 'Hold', '2026-10-31', str(uuid4()))
    assert carried['conditions'][0]['condition_id'] == original['conditions'][0]['condition_id']
    install(monkeypatch, now='2026-11-01T18:00:00+00:00',
            dates=('2026-10-30',), closes=(84,))
    sunday_quote = prices.get_price_observation('DOCN', '2026-11-01')
    assert sunday_quote['session_date'] == '2026-10-30'
    observation = thesis.observe_conditions(carried, {
        'company_of_interest': 'DOCN', 'trade_date': '2026-11-01',
        'price_observation': sunday_quote})[0]
    assert observation['status'] == 'met'


def test_new_proposal_without_role_is_rejected_legacy_rows_still_load():
    for role in ({}, {'thesis_role': 'unspecified'}):
        row = {k: v for k, v in condition().items() if k != 'thesis_role'} | role
        saved = thesis.prepare_thesis({'conditions': [row]}, None, 'Hold', '2026-11-04', str(uuid4()))
        assert saved['conditions'] == []
        assert any('Revenue needs thesis_role' in item for item in saved['warnings'])
    legacy = {k: v for k, v in condition().items() if k != 'thesis_role'}
    legacy['condition_id'] = 'condition-' + 'a' * 24
    carried = thesis.prepare_thesis({}, {'conditions': [legacy]}, 'Hold', '2026-11-04', str(uuid4()))
    assert carried['conditions'][0]['condition_id'] == legacy['condition_id']
    assert thesis.condition_role_label(carried['conditions'][0]) == 'Unspecified thesis role'


def test_rendered_pm_prompt_requires_a_role_for_every_new_condition():
    from unittest.mock import MagicMock

    from tests.test_memory_log import _make_pm_state
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError('free text')
    llm.invoke.return_value = MagicMock(content='**Rating**: Hold\n\nReason.')
    create_portfolio_manager(llm)(_make_pm_state())
    prompt = str(llm.invoke.call_args.args[0])
    assert 'Every new condition must set thesis_role' in prompt and 'unspecified means' not in prompt
