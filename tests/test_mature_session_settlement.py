"""Bounded retrieval uses observed sessions and preserves legacy completion safety."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradingagents.memory import TradingMemoryLog, settlement

# Authoritative Shanghai Stock Exchange announcement, published 2025-12-22,
# accessed 2026-11-05. Calendar dates are authentic; prices below are synthetic.
# https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml
# Relevant inclusive closures: Spring Festival Feb15–23, Qingming Apr4–6,
# Labour Day May1–5. Weekends remain closed, including make-up working weekends.
SSE_2026_CLOSURES = [('2026-02-15', '2026-02-23'), ('2026-04-04', '2026-04-06'),
                     ('2026-05-01', '2026-05-05')]


def provider(monkeypatch, dates, missing_benchmark=()):
    index = pd.DatetimeIndex(dates).tz_localize('Asia/Shanghai')
    stock = pd.Series([100. + i for i in range(len(index))], index=index)
    bench = pd.Series([400. + i for i in range(len(index))], index=index)
    bench = bench.drop([pd.Timestamp(d, tz='Asia/Shanghai') for d in missing_benchmark])
    calls = []
    def fetch(ticker, start, end):
        calls.append((ticker, start, end))
        prices = stock if ticker == '600000.SS' else bench
        return prices[(prices.index >= start) & (prices.index < end)]
    monkeypatch.setattr(settlement, 'get_closes', fetch)
    return calls


def sse_sessions():
    dates = pd.bdate_range('2026-01-30', '2026-06-01')
    for start, end in SSE_2026_CLOSURES:
        dates = dates[(dates < start) | (dates > end)]
    return dates


@pytest.mark.parametrize('days', [5, 21, 63])
def test_authentic_sse_closures_extend_to_mature_session_without_refetch(monkeypatch, days):
    dates = sse_sessions()
    calls = provider(monkeypatch, dates)
    result = settlement.fetch_outcome('600000.SS', '2026-01-29', days,
                                      prices_before='2026-06-02', benchmark_alignment='exact_sessions')
    assert result is not None
    assert result['entry']['date'] == '2026-01-30'
    assert result['exit']['date'] == dates[days].strftime('%Y-%m-%d')
    stock_calls = [c for c in calls if c[0] == '600000.SS']
    assert len(stock_calls) <= 3
    if days == 63:
        assert len(stock_calls) > 1
    assert all(first[2] == second[1] for first, second in zip(stock_calls, stock_calls[1:], strict=False))
    assert all(c[2] <= '2026-06-02' for c in calls)


def test_immature_window_stops_at_completed_cutoff(monkeypatch):
    calls = provider(monkeypatch, sse_sessions())
    assert settlement.fetch_outcome('600000.SS', '2026-01-29', 63, prices_before='2026-02-05') is None
    assert [c for c in calls if c[0] == '600000.SS'] == [('600000.SS','2026-01-29','2026-02-05')]
    assert all(c[2] <= '2026-02-05' for c in calls)


def test_suspended_or_missing_history_remains_pending_with_bounded_reason(monkeypatch):
    calls = provider(monkeypatch, pd.to_datetime(['2026-01-30']))
    with pytest.raises(settlement.SettlementCoverageError, match='completed instrument sessions'):
        settlement.fetch_outcome('600000.SS', '2026-01-29', 63, prices_before='2026-06-02')
    assert 2 <= len([c for c in calls if c[0] == '600000.SS']) <= 3


def test_delayed_entry_is_not_lost_when_it_is_beyond_both_estimated_spans(monkeypatch):
    dates = pd.bdate_range('2026-04-01', periods=7)
    calls = provider(monkeypatch, dates)
    result = settlement.fetch_outcome('600000.SS', '2026-01-29', 5, prices_before='2026-06-02')
    assert result['entry']['date'] == '2026-04-01'
    assert result['exit']['date'] == dates[5].strftime('%Y-%m-%d')
    assert len([c for c in calls if c[0] == '600000.SS']) == 3


def test_extended_stock_window_does_not_fill_missing_exact_benchmark(monkeypatch):
    dates = sse_sessions()
    provider(monkeypatch, dates, missing_benchmark=[dates[63].strftime('%Y-%m-%d')])
    assert settlement.fetch_outcome('600000.SS', '2026-01-29', 63,
                                    prices_before='2026-06-02', benchmark_alignment='exact_sessions') is None


def test_unversioned_legacy_today_bar_cannot_trigger_reflection(tmp_path, monkeypatch):
    from tradingagents.dataflows import date_window
    monkeypatch.setattr(date_window, 'get_current_date', lambda: '2026-01-13')
    dates = pd.bdate_range('2026-01-06', periods=6)
    provider(monkeypatch, dates)
    log = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    log.store_decision('600000.SS', '2026-01-05', 'Rating: Underweight', rating='Underweight')
    reflector = MagicMock()
    reflector.reflect_on_final_decision.return_value = 'Five-session legacy observation.'
    first = settlement.settle_pending('600000.SS', log, reflector, {})
    assert first.settled == []
    reflector.reflect_on_final_decision.assert_not_called()
    assert len(log.get_pending_entries()) == 1
    monkeypatch.setattr(date_window, 'get_current_date', lambda: '2026-01-14')
    second = settlement.settle_pending('600000.SS', log, reflector, {})
    assert second.settled == [('600000.SS', '2026-01-05')]
    reflector.reflect_on_final_decision.assert_called_once()
    saved = (tmp_path / 'memory.md').read_bytes()
    settlement.settle_pending('600000.SS', log, reflector, {})
    reflector.reflect_on_final_decision.assert_called_once()
    assert (tmp_path / 'memory.md').read_bytes() == saved


def test_extension_cannot_change_instrument_timezone(monkeypatch):
    calls = 0
    def fetch(ticker, start, end):
        nonlocal calls
        calls += 1
        zone = 'Asia/Shanghai' if calls == 1 else 'UTC'
        index = pd.DatetimeIndex([pd.Timestamp(start) + pd.Timedelta(days=1)]).tz_localize(zone)
        return pd.Series([100.], index=index)
    monkeypatch.setattr(settlement, 'get_closes', fetch)
    with pytest.raises(ValueError, match='timezone changed'):
        settlement.fetch_outcome('600000.SS', '2026-01-29', 63, prices_before='2026-06-02')
    assert calls == 2


def test_completed_legacy_reflection_failure_stays_retryable_then_once(tmp_path, monkeypatch):
    from tradingagents.dataflows import date_window
    monkeypatch.setattr(date_window, 'get_current_date', lambda: '2026-01-14')
    provider(monkeypatch, pd.bdate_range('2026-01-06', periods=6))
    log = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    log.store_decision('600000.SS', '2026-01-05', 'Rating: Underweight', rating='Underweight')
    reflector = MagicMock()
    reflector.reflect_on_final_decision.side_effect = [TimeoutError('offline test'), 'Legacy five-session lesson.']
    before = (tmp_path / 'memory.md').read_bytes()
    first = settlement.settle_pending('600000.SS', log, reflector, {})
    assert first.failed and not first.settled
    assert (tmp_path / 'memory.md').read_bytes() == before
    assert settlement.settle_pending('600000.SS', log, reflector, {}).settled
    assert settlement.settle_pending('600000.SS', log, reflector, {}).settled == []
    assert reflector.reflect_on_final_decision.call_count == 2
    entry = log.load_entries()[0]
    assert entry.get('decision_id') is None
    assert entry['resolved'] == '2026-01-13'
