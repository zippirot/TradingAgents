"""Endpoint settlement survives restart independently of rotating prompt memory."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tradingagents.memory import publication, publication_outcomes as outcomes


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config = {'results_dir': str(tmp_path)}
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-10-19')
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 10, 19, 22, tzinfo=UTC))
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-04')
    state = {'run_id': str(uuid4()), 'final_rating': 'Underweight',
             'final_trade_decision': 'Underweight', 'evidence_quality': {'status': 'limited'}}
    record = publication.publish(config, state, 'DOCN', '2026-10-19')
    return config, record


def measured(days=5):
    if days is None:
        return None  # calendar windows have not matured in this October fixture
    return {'raw_return': .05, 'alpha_return': .03, 'benchmark_return': .02,
            'holding_days': days, 'resolution_date': '2026-10-27',
            'ticker': 'DOCN', 'benchmark': 'SPY',
            'entry': {'date': '2026-10-20', 'price': 100.},
            'exit': {'date': '2026-10-27', 'price': 105.},
            'benchmark_entry': {'date': '2026-10-20', 'price': 400.},
            'benchmark_exit': {'date': '2026-10-27', 'price': 408.},
            'price_source': 'fixture', 'price_adjustment': 'adjusted'}


def test_short_endpoint_persists_without_consuming_longer_windows(setup, monkeypatch):
    config, record = setup
    calls = []
    def fetch(ticker, date, days, benchmark, **kwargs):
        calls.append((days, kwargs))
        return measured(days) if days == 5 else None
    monkeypatch.setattr(outcomes, 'fetch_outcome', fetch)
    first = outcomes.settle_publications(config)
    assert first['settled'] == [(record['decision_id'], '5_sessions')]
    saved = outcomes.load_outcomes(config, record)
    assert saved['endpoints']['5_sessions']['status'] == 'resolved'
    assert saved['endpoints']['21_sessions']['status'] == 'pending'
    assert calls[0][1] == {'published_at': record['published_at'], 'prices_before': '2026-11-04', 'benchmark_alignment': 'exact_sessions'}
    calls.clear()
    assert outcomes.settle_publications(config)['settled'] == []
    assert [c[0] for c in calls] == [21, 63, None, None]
    assert publication.load_record(config, record['decision_id']) == record
    assert outcomes.load_outcomes(config, record)['endpoints']['5_sessions'] == saved['endpoints']['5_sessions']


def test_concurrent_settlement_records_each_endpoint_once(setup, monkeypatch):
    config, record = setup
    calls = []
    def fetch(ticker, date, days, benchmark, **kwargs):
        calls.append(days)
        return measured(days)
    monkeypatch.setattr(outcomes, 'fetch_outcome', fetch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: outcomes.settle_publications(config), range(4)))
    assert sorted(day for day in calls if day is not None) == [5, 21, 63]
    assert sum(len(r['settled']) for r in results) == 3
    assert all(e['status'] == ('resolved' if e['holding_days'] else 'pending')
               for e in outcomes.load_outcomes(config, record)['endpoints'].values())


def test_price_failure_does_not_hide_other_endpoints(setup, monkeypatch):
    config, record = setup
    def fetch(ticker, date, days, benchmark, **kwargs):
        if days == 5:
            raise TimeoutError('private provider details')
        return measured(days) if days == 21 else None
    monkeypatch.setattr(outcomes, 'fetch_outcome', fetch)
    result = outcomes.settle_publications(config)
    assert result['settled'] == [(record['decision_id'], '21_sessions')]
    assert len(result['failed']) == 1
    assert 'private' not in str(result)
    assert outcomes.load_outcomes(config, record)['endpoints']['5_sessions']['status'] == 'pending'


def test_corrupt_companion_fails_visibly_without_replacing_it(setup, monkeypatch):
    config, record = setup
    monkeypatch.setattr(outcomes, 'fetch_outcome', lambda *a, **k: measured(a[2]))
    outcomes.settle_publications(config)
    path = publication.record_root(config) / 'outcomes' / (record['decision_id'] + '.json')
    original = json.loads(path.read_text())
    original['endpoints']['5_sessions']['outcome']['raw_return'] = 100.
    path.write_text(json.dumps(original))
    damaged = path.read_bytes()
    with pytest.raises(ValueError, match='integrity'):
        outcomes.load_outcomes(config, record)
    result = outcomes.settle_publications(config)
    assert result['failed'] and not result['settled']
    assert path.read_bytes() == damaged


def test_write_interruption_retries_without_losing_previous_endpoint(setup, monkeypatch):
    config, record = setup
    monkeypatch.setattr(outcomes, 'fetch_outcome', lambda *a, **k: measured(a[2]))
    actual = outcomes.replace_file
    count = 0
    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise PermissionError('interrupted')
        return actual(*args, **kwargs)
    monkeypatch.setattr(outcomes, 'replace_file', fail_second)
    first = outcomes.settle_publications(config)
    assert first['failed']
    assert outcomes.load_outcomes(config, record)['endpoints']['5_sessions']['status'] == 'resolved'
    monkeypatch.setattr(outcomes, 'replace_file', actual)
    second = outcomes.settle_publications(config)
    assert (record['decision_id'], '5_sessions') not in second['settled']
    assert all(e['status'] == ('resolved' if e['holding_days'] else 'pending')
               for e in outcomes.load_outcomes(config, record)['endpoints'].values())


def test_review_is_audited_but_not_scored(setup, monkeypatch):
    config, _ = setup
    state = {'run_id': str(uuid4()), 'final_rating': 'REVIEW', 'final_trade_decision': 'REVIEW'}
    review = publication.publish(config, state, 'OTHER', '2026-10-19')
    monkeypatch.setattr(outcomes, 'fetch_outcome', lambda *a, **k: pytest.fail('ineligible'))
    assert outcomes.settle_publications(config, ticker='OTHER') == {'settled': [], 'failed': []}
    assert all(e['status'] == 'ineligible' for e in outcomes.load_outcomes(config, review)['endpoints'].values())


def test_historical_simulation_does_not_use_today_as_historical_publication(setup, monkeypatch):
    config, _ = setup
    state = {'run_id': str(uuid4()), 'final_rating': 'Hold', 'final_trade_decision': 'Hold',
             'evidence_quality': {'status': 'limited'}}
    state['evaluation_mode'] = 'historical'
    record = publication.publish(config, state, 'DOCN', '2026-09-01')
    observed = []
    def fetch(*args, **kwargs):
        observed.append(kwargs['published_at'])
        return None
    monkeypatch.setattr(outcomes, 'fetch_outcome', fetch)
    outcomes.settle_publications(config)
    assert observed[-3:] == [None] * 3
    assert outcomes.load_outcomes(config, record)['evaluation_mode'] == 'historical'


def test_real_price_window_calculator_settles_short_window_and_keeps_current_bars_pending(setup, monkeypatch):
    import pandas as pd

    from tradingagents.memory import settlement

    config, record = setup
    index = pd.bdate_range('2026-10-20', periods=23, tz='America/New_York')
    stock = pd.Series([100. + i for i in range(23)], index=index)
    benchmark = pd.Series([400. + i for i in range(23)], index=index)
    monkeypatch.setattr(settlement, 'get_closes', lambda ticker, *a: stock if ticker == 'DOCN' else benchmark)
    result = outcomes.settle_publications(config)
    assert result['failed'] == []
    assert result['settled'] == [(record['decision_id'], '5_sessions')]
    saved = outcomes.load_outcomes(config, record)
    assert saved['endpoints']['5_sessions']['outcome']['resolution_date'] == '2026-10-27'
    assert saved['endpoints']['21_sessions']['status'] == 'pending'
    assert saved['endpoints']['63_sessions']['status'] == 'pending'


def test_unfinished_current_day_cannot_be_resolved_even_if_provider_returns_it(setup, monkeypatch):
    config, record = setup
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-10-27')
    monkeypatch.setattr(outcomes, 'fetch_outcome', lambda *a, **k: measured(a[2]))
    assert outcomes.settle_publications(config) == {'settled': [], 'failed': []}
    assert outcomes.load_outcomes(config, record)['endpoints']['5_sessions']['status'] == 'pending'


def test_existing_graph_settlement_scans_publications_after_memory_is_empty(setup, monkeypatch):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory.log import TradingMemoryLog
    config, record = setup
    config['memory_log_path'] = str(publication.record_root(config) / 'empty-memory.md')
    graph = object.__new__(TradingAgentsGraph)
    graph.config = config
    graph.memory_log = TradingMemoryLog(config)
    class NoReflection:
        def reflect_on_final_decision(self, **kwargs):
            pytest.fail('additional endpoint scoring must not call a model')
    graph.reflector = NoReflection()
    monkeypatch.setattr(outcomes, 'fetch_outcome', lambda *a, **k: measured() if a[2] == 5 else None)
    result = graph.settle_all_pending()
    assert result.endpoint_settled == [(record['decision_id'], '5_sessions')]
    assert result.failed == []
    assert graph.settle_all_pending().endpoint_settled == []
    saved = outcomes.load_outcomes(config, record)
    assert saved['endpoints']['21_sessions']['status'] == 'pending'
    assert saved['endpoints']['63_sessions']['status'] == 'pending'


def test_nested_entry_policy_cannot_be_relabelled_even_with_valid_checksum(setup, monkeypatch):
    config, record = setup
    monkeypatch.setattr(outcomes, 'fetch_outcome', lambda *a, **k: measured(a[2]))
    outcomes.settle_publications(config)
    path = publication.record_root(config) / 'outcomes' / (record['decision_id'] + '.json')
    saved = json.loads(path.read_text())
    saved['endpoints']['5_sessions']['outcome']['entry_policy'] = 'same-day executable opening trade'
    outcomes._write(path, saved)
    with pytest.raises(ValueError, match='integrity'):
        outcomes.load_outcomes(config, record)
