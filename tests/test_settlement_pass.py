"""Publication settlement shares observed prices and keeps retry evidence durable."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pandas as pd
import pytest

from tradingagents.memory import publication, publication_outcomes as outcomes, settlement


def record(config, monkeypatch, ticker='DOCN', day='2026-01-05'):
    published = (datetime.fromisoformat(day) + timedelta(days=1)).replace(hour=22, tzinfo=UTC)
    monkeypatch.setattr(publication, '_utcnow', lambda: published)
    state = {'run_id': str(uuid4()), 'final_rating': 'Hold', 'final_trade_decision': 'Hold',
             'evaluation_mode': 'historical', 'evidence_quality': {'status': 'limited'}}
    return publication.publish(config, state, ticker, day)


def provider(monkeypatch, data):
    calls = []
    def fetch(ticker, start, end):
        calls.append((ticker, start, end))
        value = data[ticker]
        if isinstance(value, Exception):
            raise value
        selected = value[(value.index.tz_localize(None) >= start) &
                         (value.index.tz_localize(None) < end)].copy()
        selected.attrs.update(value.attrs)
        selected.attrs.update(settlement_request_start=start, settlement_request_end=end)
        return selected
    monkeypatch.setattr(settlement, 'get_settlement_closes', fetch, raising=False)
    monkeypatch.setattr(settlement, 'get_closes', fetch)
    return calls


def series(dates, value=100):
    return pd.Series([float(value+i) for i in range(len(dates))],
                     index=pd.DatetimeIndex(dates, tz='America/New_York'))


def test_one_symbol_request_across_real_pass_records_and_shared_benchmarks(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    rows = [record(cfg, monkeypatch), record(cfg, monkeypatch, day='2026-01-06'),
            record(cfg, monkeypatch, ticker='NVDA')]
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-07')
    dates = pd.bdate_range('2025-12-29', '2026-11-06')
    calls = provider(monkeypatch, {'DOCN': series(dates), 'NVDA': series(dates, 200),
                                  'SPY': series(dates, 400)})
    done = outcomes.settle_publications(cfg)
    assert len(done['settled']) == 15 and not done['failed']
    assert sorted(t for t, _, _ in calls) == ['DOCN', 'NVDA', 'SPY']
    assert all(end == '2026-11-07' for _, _, end in calls)
    for row in rows:
        saved = outcomes.load_outcomes(cfg, row)
        short = saved['endpoints']['5_sessions']['outcome']
        expected_entry = '2026-01-06' if row['requested_as_of'] == '2026-01-05' else '2026-01-07'
        assert short['entry']['date'] == expected_entry
        assert short['exit']['date'] == ('2026-01-13' if expected_entry.endswith('06') else '2026-01-14')
        assert short['instrument_retrieval_spans'] == [
            {'start': '2026-01-05', 'end_exclusive': '2026-11-07'}]
    calls.clear()
    assert not outcomes.settle_publications(cfg)['settled'] and calls == []


def test_shared_calendar_window_uses_suspended_actual_entry(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = record(cfg, monkeypatch)
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-07')
    calls = provider(monkeypatch, {'DOCN': series(['2026-03-04', '2026-06-04', '2026-09-04']),
                                  'SPY': series(pd.bdate_range('2026-01-01', '2026-11-06'), 400)})
    outcomes.settle_publications(cfg)
    value = outcomes.load_outcomes(cfg, row)['endpoints']['6_calendar_months']['outcome']
    assert value['entry']['date'] == '2026-03-04'
    assert value['nominal_exit_date'] == value['exit']['date'] == '2026-09-04'
    assert len(calls) == 2


def test_actual_outer_settlement_pass_shares_symbols_across_tickers(tmp_path, monkeypatch):
    from tradingagents.memory.log import TradingMemoryLog

    cfg = {'results_dir': str(tmp_path), 'memory_log_path': str(tmp_path / 'empty-memory.md')}
    record(cfg, monkeypatch)
    record(cfg, monkeypatch, ticker='NVDA')
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-07')
    dates = pd.bdate_range('2025-12-29', '2026-11-06')
    calls = provider(monkeypatch, {'DOCN': series(dates), 'NVDA': series(dates, 200),
                                  'SPY': series(dates, 400)})
    class NoReflection:
        def reflect_on_final_decision(self, **kwargs):
            pytest.fail('publication settlement must not invoke a model')
    result = settlement.settle_all_pending(TradingMemoryLog(cfg), NoReflection(), cfg)
    assert len(result.endpoint_settled) == 10
    assert sorted(t for t, _, _ in calls) == ['DOCN', 'NVDA', 'SPY']


def test_no_evidence_read_when_nothing_resolves_then_once_for_multiple_resolutions(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = record(cfg, monkeypatch)
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-01-07')
    provider(monkeypatch, {'DOCN': series(['2026-01-06']), 'SPY': series(['2026-01-06'], 400)})
    reads = []
    real = outcomes.load_evidence
    monkeypatch.setattr(outcomes, 'load_evidence', lambda *args: reads.append(args) or real(*args))
    first = outcomes.settle_publications(cfg)
    assert not first['settled'] and reads == []
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-07')
    provider(monkeypatch, {'DOCN': series(pd.bdate_range('2026-01-06', '2026-11-06')),
                          'SPY': series(pd.bdate_range('2026-01-06', '2026-11-06'), 400)})
    assert len(outcomes.settle_publications(cfg)['settled']) == 5
    assert len(reads) == 1
    assert len(outcomes.load_outcomes(cfg, row)['endpoints']) == 5


def test_verified_zero_checks_count_only_distinct_due_post_horizon_passes_and_reopen(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = record(cfg, monkeypatch)
    empty = series([])
    empty.attrs['settlement_verified_empty'] = True
    calls = provider(monkeypatch, {'DOCN': empty,
                                  'SPY': series(pd.bdate_range('2026-01-01', '2026-11-06'), 400)})
    clock = [datetime(2026, 1, 8, 22, tzinfo=UTC)]
    monkeypatch.setattr(outcomes, '_now', lambda: clock[0], raising=False)
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: clock[0].date().isoformat())
    outcomes.settle_publications(cfg, pass_id=str(uuid4()))  # pre-horizon
    assert not outcomes.load_outcomes(cfg, row)['endpoints']['5_sessions'].get('zero_checks')
    origin = datetime(2026, 2, 2, 22, tzinfo=UTC)
    passes = [str(uuid4()) for _ in range(3)]
    for delta, expected in [(0, 1), (13, 1), (14, 2), (27, 2), (28, 3)]:
        clock[0] = origin + timedelta(days=delta)
        done = outcomes.settle_publications(cfg, pass_id=passes[min(delta//14, 2)])
        saved = outcomes.load_outcomes(cfg, row)  # reload real companion each attempt
        endpoint = saved['endpoints']['5_sessions']
        assert len(endpoint['zero_checks']) == expected
        assert endpoint['status'] == ('unresolvable' if expected == 3 else 'pending')
        if delta == 28:
            assert (row['decision_id'], '5_sessions') in done['terminal']
    endpoint = outcomes.load_outcomes(cfg, row)['endpoints']['5_sessions']
    assert endpoint['terminal']['reason'] == 'No eligible instrument sessions on three post-horizon checks'
    assert 'unresolvable' in outcomes.render_outcome_summary(cfg, as_of=clock[0].isoformat())
    assert 'unresolvable' not in outcomes.render_outcome_summary(cfg, as_of=origin.isoformat())
    # Freeze all siblings as unavailable to isolate endpoint-only fetch avoidance.
    previous = endpoint.copy()
    reopened = outcomes.reopen_endpoint(cfg, row['decision_id'], '5_sessions')
    assert reopened['endpoints']['5_sessions']['status'] == 'pending'
    assert reopened['endpoints']['5_sessions']['zero_checks'] == []
    for name in row['endpoints']:
        if name != '5_sessions':
            assert reopened['endpoints'][name] == saved['endpoints'][name]
    assert reopened['endpoints']['5_sessions']['terminal_history'][0]['reason'] == previous['terminal']['reason']
    clock[0] += timedelta(days=1)
    provider(monkeypatch, {'DOCN': series(pd.bdate_range('2026-01-06', '2026-11-06')),
                          'SPY': series(pd.bdate_range('2026-01-01', '2026-11-06'), 400)})
    assert (row['decision_id'], '5_sessions') in outcomes.settle_publications(cfg)['settled']
    assert calls


def test_verified_closed_calendar_terminal_never_licenses_asof_or_performance(tmp_path, monkeypatch):
    from tradingagents.backtest import evaluate_publications

    cfg = {'results_dir': str(tmp_path)}
    row = record(cfg, monkeypatch, ticker='FOREIGN', day='2026-07-02')
    monkeypatch.setattr(outcomes, '_now', lambda: datetime(2026, 11, 7, 22, tzinfo=UTC))
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-07')
    dates = pd.bdate_range('2026-06-25', '2026-11-06')
    benchmark_dates = dates[dates != pd.Timestamp('2026-07-03')]
    calls = provider(monkeypatch, {'FOREIGN': series(dates), 'SPY': series(benchmark_dates, 400)})
    done = outcomes.settle_publications(cfg)
    assert (row['decision_id'], '5_sessions') in done['terminal']
    endpoint = outcomes.load_outcomes(cfg, row)['endpoints']['5_sessions']
    assert endpoint['status'] == 'unresolvable' and 'outcome' not in endpoint
    assert endpoint['terminal']['proof']['closed_date'] == '2026-07-03'
    assert endpoint['benchmark_alignment'] == 'exact_sessions'
    report = evaluate_publications(cfg, '2026-11-08T00:00:00+00:00')
    short = next(group for group in report['groups'] if group['horizon'] == ['trading_sessions', 5])
    assert short['resolved'] == short['pending'] == 0 and short['unresolvable'] == 1
    assert report['observations'] == []
    calls.clear()
    requested = []
    calculate = outcomes.fetch_outcome
    def observe(*args, **kwargs):
        requested.append((args[2], kwargs.get('calendar_months')))
        return calculate(*args, **kwargs)
    monkeypatch.setattr(outcomes, 'fetch_outcome', observe)
    outcomes.settle_publications(cfg)
    assert requested == [(None, 6)]  # Only the still-immature sibling is evaluated.


def test_missing_benchmark_row_without_verified_calendar_proof_stays_retryable(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = record(cfg, monkeypatch, day='2026-07-05')
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-07')
    dates = pd.bdate_range('2026-06-25', '2026-11-06')
    provider(monkeypatch, {'DOCN': series(dates),
                          'SPY': series(dates[dates != pd.Timestamp('2026-07-13')], 400)})
    done = outcomes.settle_publications(cfg)
    assert done['failed']
    endpoint = outcomes.load_outcomes(cfg, row)['endpoints']['5_sessions']
    assert endpoint['status'] == 'pending' and not endpoint.get('terminal')


def test_future_horizon_is_immature_without_inventing_zero_coverage(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = record(cfg, monkeypatch, day='2026-11-06')
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-07')
    provider(monkeypatch, {'DOCN': series([]), 'SPY': series([])})
    done = outcomes.settle_publications(cfg)
    assert len(done['immature']) == 5 and not done['failed']
    assert not outcomes.load_outcomes(cfg, row)['endpoints']['5_sessions'].get('zero_checks')


def test_corrupt_evidence_is_verified_only_once_without_committing_any_price(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = record(cfg, monkeypatch)
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: '2026-11-07')
    dates = pd.bdate_range('2026-01-01', '2026-11-06')
    provider(monkeypatch, {'DOCN': series(dates), 'SPY': series(dates, 400)})
    reads = []
    def corrupt(*args):
        reads.append(args)
        raise ValueError('corrupt retained evidence')
    monkeypatch.setattr(outcomes, 'load_evidence', corrupt)
    done = outcomes.settle_publications(cfg)
    assert done['settled'] == [] and done['failed']
    assert len(reads) == 1
    assert all(e['status'] == 'pending' for e in outcomes.load_outcomes(cfg, row)['endpoints'].values())
