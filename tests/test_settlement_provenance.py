"""Outcome provenance must reconstruct the calculation without another price fetch."""
import pandas as pd
import pytest

from tradingagents.memory import settlement


def prices(monkeypatch):
    stock = pd.Series(range(100, 110), index=pd.date_range('2026-01-03', periods=10, tz='UTC'))
    bench = pd.Series([400., 404., 408., 412., 416., 420.],
                      index=pd.bdate_range('2026-01-02', periods=6, tz='America/New_York'))
    def get(symbol, start, end):
        series = stock if symbol == 'BTC-USD' else bench
        return series[(series.index >= start) & (series.index < end)]
    monkeypatch.setattr(settlement, 'get_closes', get)


def test_outcome_preserves_actual_benchmark_sessions_and_prices(monkeypatch):
    prices(monkeypatch)
    outcome = settlement.fetch_outcome('BTC-USD', '2026-01-03', 5, 'SPY')
    assert outcome['entry'] == {'date': '2026-01-04', 'price': 101.0}
    assert outcome['exit'] == {'date': '2026-01-09', 'price': 106.0}
    assert outcome['benchmark_entry'] == {'date': '2026-01-02', 'price': 400.0}
    assert outcome['benchmark_exit'] == {'date': '2026-01-09', 'price': 420.0}
    assert outcome['raw_return'] == pytest.approx(106 / 101 - 1)
    assert outcome['alpha_return'] == pytest.approx(106 / 101 - 1 - .05)
    assert outcome['price_source'] == 'Yahoo Finance via yfinance'
    assert outcome['price_adjustment'] == 'auto_adjust=True (splits and dividends)'
    assert outcome['bar_time_basis'] == 'daily session date; not an execution timestamp'
    assert settlement.fetch_returns('BTC-USD', '2026-01-03', 5, 'SPY') == (
        outcome['raw_return'], outcome['alpha_return'], 5, '2026-01-09')


def test_longer_window_stays_pending(monkeypatch):
    prices(monkeypatch)
    assert settlement.fetch_outcome('BTC-USD', '2026-01-03', 21, 'SPY') is None


@pytest.mark.parametrize('days', [0, -1, 1.5, True])
def test_invalid_horizon_is_rejected_before_fetch(monkeypatch, days):
    monkeypatch.setattr(settlement, 'get_closes', lambda *a: pytest.fail('must not fetch'))
    with pytest.raises(ValueError, match='positive integer'):
        settlement.fetch_outcome('DOCN', '2026-01-03', days)


def test_nonfinite_prices_cannot_create_a_resolved_outcome(monkeypatch):
    dates = pd.bdate_range('2026-01-05', periods=7)
    stock = pd.Series([100., 101., 102., 103., 104., 105., float('inf')], index=dates)
    bench = pd.Series([400.] * 7, index=dates)
    monkeypatch.setattr(settlement, 'get_closes', lambda symbol, *a: stock if symbol == 'DOCN' else bench)
    # The infinite endpoint is unavailable, not a 5-session return of infinity.
    assert settlement.fetch_outcome('DOCN', '2026-01-05', 5) is None


def test_live_entry_respects_actual_publication_in_instrument_timezone(monkeypatch):
    idx = pd.bdate_range('2026-01-05', periods=15, tz='America/New_York')
    stock = pd.Series([100. + i for i in range(15)], index=idx)
    bench = pd.Series([400. + i for i in range(15)], index=idx)
    monkeypatch.setattr(settlement, 'get_closes', lambda symbol, *a: stock if symbol == 'DOCN' else bench)
    # Jan 8 UTC is still Jan 7 in New York: first eligible close is Jan 8.
    outcome = settlement.fetch_outcome('DOCN', '2026-01-05', 5,
                                       published_at='2026-01-08T02:00:00+00:00')
    assert outcome['entry']['date'] == '2026-01-08'
    assert outcome['cutoff_date'] == '2026-01-07'
    assert outcome['publication_session_timezone'] == 'America/New_York'


def test_current_partial_session_cannot_resolve_endpoint(monkeypatch):
    prices(monkeypatch)
    assert settlement.fetch_outcome('BTC-USD', '2026-01-03', 5,
                                    prices_before='2026-01-09') is None
    outcome = settlement.fetch_outcome('BTC-USD', '2026-01-03', 5,
                                       prices_before='2026-01-10')
    assert outcome['resolution_date'] == '2026-01-09'
    assert outcome['prices_before'] == '2026-01-10'


def test_visibility_cutoff_cannot_admit_future_exchange_bars(monkeypatch):
    idx = pd.bdate_range('2099-01-05', periods=8, tz='America/New_York')
    series = pd.Series([100. + i for i in range(8)], index=idx)
    monkeypatch.setattr(settlement, 'get_closes', lambda *a: series)
    assert settlement.fetch_outcome('DOCN', '2099-01-05', 5,
                                    prices_before='2100-01-01') is None
