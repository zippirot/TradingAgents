"""Dated comparisons replay source inputs and use each scenario's capital."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

import pytest

from tests.test_price_observation import install
from tests.test_valuation import ev_request, evidence, pe_request
from tests.test_valuation_funding import request as funded_request
from tradingagents.agents.valuation import validate_target
from tradingagents.agents.valuation_comparison import compare_valuation, render_valuation_comparison
from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation


def state(monkeypatch, *, splits=(0, 0), currency='USD', dates=('2025-12-31', '2026-10-19')):
    install(monkeypatch, now='2026-10-19T22:00:00+00:00', dates=dates, closes=(20, 20),
            splits=splits, metadata={'currency': currency, 'currentTradingPeriod': {'regular': {
                'end': datetime.fromisoformat('2026-10-19T21:00:00+00:00')}}})
    quote = get_price_observation('DOCN', '2026-10-19', '2025-12-31')
    assert quote['status'] == 'available', quote
    return {'company_of_interest': 'DOCN', 'trade_date': '2026-10-19',
            'issuer_identity': {'ticker': 'DOCN', 'cik': evidence().cik, 'as_of': '2026-10-19', 'source': 'SEC issuer map'},
            'financial_evidence': evidence().model_dump(mode='json'), 'price_observation': quote}


def compare(s, request=None):
    request = deepcopy(request or ev_request())
    for row in request.get('scenarios', [request]):
        row['multiple_assumption_date'] = '2026-10-19'
    return compare_valuation(s, validate_target(request, evidence()), request)


def test_ev_reverse_algebra_dates_and_conditional_label(monkeypatch):
    record = compare(state(monkeypatch))
    assert record['status'] == 'available', record
    row = record['rows'][0]
    assert Decimal(row['conditional_return_percent']) == 75
    assert Decimal(row['implied_enterprise_value']) == 2100
    assert Decimal(row['implied_multiple']) == Decimal('1.75')
    assert Decimal(row['implied_revenue']) == 700
    assert row['capital_date'] == '2026-06-30' and row['price_date'] == '2026-10-19'
    assert record['label'] == 'conditional sensitivity'
    assert 'Conditional scenario comparison' in render_valuation_comparison(record)


def test_forward_comparison_uses_own_capital_and_original_split_anchor(monkeypatch):
    raw = funded_request(equity_proceeds=200, equity_issue_price=20)
    record = compare(state(monkeypatch), raw)
    assert record['status'] == 'available', record
    row = record['rows'][0]
    assert Decimal(row['implied_enterprise_value']) == 2130  # 20*110 + (200-270)
    assert row['capital_date'] == '2027-12-31'
    bad = compare(state(monkeypatch, splits=(0, 2)), raw)
    assert bad['status'] == 'unavailable' and 'split' in bad['reason'].lower()


def test_historical_pe_without_capital_comparability_has_no_replayed_price_comparison(monkeypatch):
    record = compare(state(monkeypatch), pe_request())
    assert record['status'] == 'unavailable', record
    assert 'comparability_unestablished' in record['reason']
    assert not record['rows']


@pytest.mark.parametrize('mode', ['tamper', 'future', 'currency', 'coverage', 'split'])
def test_invalid_or_incomparable_price_is_unavailable(monkeypatch, mode):
    s = state(monkeypatch, currency='EUR' if mode == 'currency' else 'USD',
              splits=(0, 2) if mode == 'split' else (0, 0),
              dates=('2026-10-15', '2026-10-19') if mode == 'coverage' else ('2025-12-31', '2026-10-19'))
    if mode == 'tamper':
        s['price_observation']['close'] = '999'
    if mode == 'future':
        s['price_observation']['session_date'] = '2026-10-20'
    record = compare(s)
    assert record['status'] == 'unavailable' and not record['rows']
    assert 'unavailable' in render_valuation_comparison(record).lower()


def test_funding_gap_does_not_publish_returns_or_implied_claims(monkeypatch):
    record = compare(state(monkeypatch), funded_request(cash_capex=500))
    assert record['status'] == 'unavailable' and not record['rows']
    assert 'shortfall' in record['reason']


def test_saved_target_tampering_is_recomputed(monkeypatch):
    raw = ev_request()
    raw['scenarios'][0]['multiple_assumption_date'] = '2026-10-19'
    fake = validate_target(raw, evidence()).model_copy(update={'target': Decimal(999999)})
    record = compare_valuation(state(monkeypatch), fake, raw)
    assert Decimal(record['rows'][0]['scenario_price']) == 35


@pytest.mark.parametrize('method', ['ev', 'pe'])
def test_decision_date_requires_future_date_and_paired_rationale(method):
    raw = ev_request() if method == 'ev' else pe_request()
    for values in ({'decision_date': '2027-01-19'}, {'rerating_assumption': 'Catalyst'},
                   {'decision_date': '2026-10-19', 'rerating_assumption': 'Catalyst'},
                   {'decision_date': '2027-01-19', 'rerating_assumption': ' '}):
        assert validate_target(raw | values, evidence()).status == 'unsupported'


def test_decision_date_does_not_relabel_later_forward_capital(monkeypatch):
    raw = funded_request()
    raw.update(decision_date='2027-01-19', rerating_assumption='Market rerates on results.')
    calculated = validate_target(raw, evidence())
    assert calculated.status == 'supported', calculated.reasons
    assert str(calculated.decision_date) == '2027-01-19'
    record = compare(state(monkeypatch), raw)
    assert record['label'] == 'conditional sensitivity'
    assert 'capital' in record['horizon_note'].lower()
    raw['decision_date'] = '2028-01-19'
    record = compare(state(monkeypatch), raw)
    assert record['label'] == 'conditional decision-date scenario'
    raw['rerating_assumption'] = '<script>| test'
    rendered = render_valuation_comparison(compare(state(monkeypatch), raw))
    assert '&lt;' not in rendered and r'\| test' in rendered
    from tradingagents.report_html import _markdown
    assert '<script>' not in _markdown().render(rendered)


def test_different_scenario_funding_uses_each_rows_share_and_obligation_bridge(monkeypatch):
    raw = funded_request()
    second = deepcopy(raw['scenarios'][0])
    second['name'] = 'Equity funded'
    second['funding'].update(equity_proceeds=200, equity_issue_price=20)
    raw['scenarios'][0]['weight'] = second['weight'] = '0.5'
    raw['scenarios'].append(second)
    raw['weight_rationale'] = 'Equal illustrative subjective weights.'
    record = compare(state(monkeypatch), raw)
    assert record['status'] == 'available', record
    assert [Decimal(r['shares_outstanding']) for r in record['rows']] == [100, 110]
    assert [Decimal(r['net_obligations']) for r in record['rows']] == [130, -70]
    for row in record['rows']:
        ev = Decimal(row['implied_enterprise_value'])
        assert ev == 20 * Decimal(row['shares_outstanding']) + Decimal(row['net_obligations'])
        assert Decimal(row['implied_revenue']) * Decimal(row['assumed_multiple']) == ev


def test_split_before_original_capital_does_not_reject_current_share_basis(monkeypatch):
    record = compare(state(monkeypatch, splits=(2, 0)))
    assert record['status'] == 'available', record


def test_missing_run_ticker_cannot_validate_price_identity(monkeypatch):
    inputs = state(monkeypatch)
    inputs.pop('company_of_interest')
    record = compare(inputs)
    assert record['status'] == 'unavailable' and 'ticker' in record['reason']


def test_legacy_undated_multiples_cannot_supply_dated_comparison(monkeypatch):
    for raw in (ev_request(), pe_request()):
        record = compare_valuation(state(monkeypatch), validate_target(raw, evidence()), raw)
        assert record['status'] == 'unavailable'
        assert ('undated' in record['reason'].lower()
                or 'comparability_unestablished' in record['reason'])


def test_incomplete_session_split_invalidates_prior_completed_close_basis(monkeypatch):
    install(monkeypatch, now='2026-10-19T19:00:00+00:00',
            dates=('2025-12-31', '2026-10-16', '2026-10-19'), closes=(10, 10, 11),
            splits=(0, 0, 2), metadata={'currentTradingPeriod': {'regular': {
                'end': datetime.fromisoformat('2026-10-19T20:00:00+00:00')}}})
    quote = get_price_observation('DOCN', '2026-10-19', '2025-12-31')
    assert quote['status'] == 'available' and quote['session_date'] == '2026-10-16'
    inputs = {'company_of_interest': 'DOCN', 'trade_date': '2026-10-19',
              'issuer_identity': {'ticker': 'DOCN', 'cik': evidence().cik, 'as_of': '2026-10-19', 'source': 'SEC issuer map'},
              'financial_evidence': evidence().model_dump(mode='json'), 'price_observation': quote}
    record = compare(inputs, funded_request())
    assert record['status'] == 'unavailable' and not record['rows']
    assert 'split' in record['reason'].lower()


def test_price_comparison_requires_matching_gate_issuer_identity(monkeypatch):
    current = state(monkeypatch)
    current['issuer_identity'] = {'ticker': 'AAPL', 'cik': evidence().cik,
                                  'as_of': current['trade_date'], 'source': 'SEC issuer map'}
    record = compare(current)
    assert record['status'] == 'unavailable' and 'issuer' in record['reason'].lower()
    current.pop('issuer_identity')
    assert compare(current)['status'] == 'unavailable'
