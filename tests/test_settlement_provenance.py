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
