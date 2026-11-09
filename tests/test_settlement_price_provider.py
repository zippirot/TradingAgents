"""A settlement fetch must distinguish a verified empty chart from a failed read."""

import numpy as np
import pandas as pd
import pytest
import yfinance as yf
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.yahoo.market import get_settlement_closes


@pytest.mark.unit
def test_settlement_closes_returns_valid_prices_and_exact_request(monkeypatch):
    frame = pd.DataFrame(
        {"Open": [10.0], "High": [12.0], "Low": [9.0], "Close": [11.0], "Volume": [100]},
        index=pd.DatetimeIndex(["2026-09-21"], name="Date", tz="America/New_York"),
    )
    calls = []

    def history(self, **kwargs):
        calls.append((self.ticker, kwargs))
        return frame

    monkeypatch.setattr(yf.Ticker, "history", history)
    result = get_settlement_closes("AAPL", "2026-09-21", "2026-09-25")
    pd.testing.assert_series_equal(result, frame["Close"])
    assert result.attrs.get("settlement_verified_empty") is not True
    assert result.attrs["settlement_request_start"] == "2026-09-21"
    assert result.attrs["settlement_request_end"] == "2026-09-25"
    assert calls == [("AAPL", {"start": "2026-09-21", "end": "2026-09-25",
                               "auto_adjust": True, "raise_errors": True})]


@pytest.mark.unit
def test_settlement_closes_marks_only_a_well_formed_empty_chart(monkeypatch):
    frame = pd.DataFrame({name: pd.Series(dtype="float64") for name in
                          ("Open", "High", "Low", "Close", "Volume")},
                         index=pd.DatetimeIndex([], name="Date", tz="America/New_York"))
    monkeypatch.setattr(yf.Ticker, "history", lambda self, **kwargs: frame)
    result = get_settlement_closes("AAPL", "2026-09-21", "2026-09-25")
    assert result.empty
    assert result.attrs["settlement_verified_empty"] is True
    assert str(result.index.tz) == "America/New_York"
    assert result.attrs["settlement_request_start"] == "2026-09-21"
    assert result.attrs["settlement_request_end"] == "2026-09-25"


@pytest.mark.unit
@pytest.mark.parametrize("bad", [
    None,
    pd.DataFrame(index=pd.DatetimeIndex([], name="Date")),
    pd.DataFrame({"Close": pd.Series(dtype="float64")}, index=pd.Index([], name="Date")),
    pd.DataFrame({"Close": [np.nan]}, index=pd.DatetimeIndex(["2026-09-21"])),
    pd.DataFrame({"Open": [10.0], "High": [12.0], "Low": [9.0],
                  "Close": pd.array([pd.NA], dtype="Float64"), "Volume": [100]},
                 index=pd.DatetimeIndex(["2026-09-21"])),
    pd.DataFrame({"Close": [-1.0]}, index=pd.DatetimeIndex(["2026-09-21"])),
    pd.DataFrame({"Close": [11.0]}, index=pd.DatetimeIndex(["2026-09-26"])),
    pd.DataFrame({"Close": [11.0, 12.0]}, index=pd.DatetimeIndex(["2026-09-21"] * 2)),
], ids=["none", "missing-close", "malformed-index", "nan-close", "nullable-missing-close", "negative-close",
        "outside-window", "duplicate-index"])
def test_settlement_closes_rejects_unknown_or_invalid_data(monkeypatch, bad):
    monkeypatch.setattr(yf.Ticker, "history", lambda self, **kwargs: bad)
    with pytest.raises(VendorUnavailableError):
        get_settlement_closes("AAPL", "2026-09-21", "2026-09-25")


@pytest.mark.unit
@pytest.mark.parametrize("error", [
    RuntimeError("secret provider detail"),
    YFRateLimitError(),
    YFPricesMissingError("AAPL", " (1d 2026-09-21 -> 2026-09-25)"),
])
def test_settlement_closes_keeps_exceptions_retryable_without_leaking_text(monkeypatch, error):
    def history(self, **kwargs):
        raise error

    monkeypatch.setattr(yf.Ticker, "history", history)
    with pytest.raises(VendorUnavailableError) as caught:
        get_settlement_closes("AAPL", "2026-09-21", "2026-09-25")
    assert type(error).__name__ in str(caught.value)
    assert "secret provider detail" not in str(caught.value)


def test_real_vendor_explicit_no_data_response_preserves_verified_window(monkeypatch):
    """Exercise actual yfinance parsing; substitute only its HTTP response."""
    from datetime import datetime
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo

    from yfinance.scrapers.history import PriceHistory

    start, end = '2026-01-05', '2026-02-02'
    zone = ZoneInfo('America/New_York')
    first = int(datetime.fromisoformat(start).replace(tzinfo=zone).timestamp())
    last = int(datetime.fromisoformat(end).replace(tzinfo=zone).timestamp())
    reason = f"Data doesn't exist for startDate = {first}, endDate = {last}"
    requests = []
    def fetch(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(text='', json=lambda: {
            'chart': {'result': None, 'error': {'code': 'Bad Request', 'description': reason}}})
    source = yf.Ticker('DOCN')
    source._price_history = PriceHistory(
        SimpleNamespace(get=fetch, cache_get=fetch), 'DOCN', 'America/New_York')
    monkeypatch.setattr(yf, 'Ticker', lambda symbol: source)
    result = get_settlement_closes('DOCN', start, end)
    assert result.empty and result.attrs['settlement_verified_empty'] is True
    assert result.attrs['settlement_zero_source'] == 'yahoo_explicit_window_no_data'
    assert str(result.index.tz) == 'America/New_York'
    assert len(requests) == 1
    assert requests[0]['params']['period1'] == first and requests[0]['params']['period2'] == last


@pytest.mark.parametrize('failure', ['wrong_bounds', 'no_timezone', 'service_reason', 'error_status'])
def test_explicit_no_data_requires_matched_authoritative_request_context(monkeypatch, failure):
    from types import SimpleNamespace

    reason = "Data doesn't exist for startDate = 1767589200, endDate = 1770008400"
    if failure == 'wrong_bounds':
        reason = "Data doesn't exist for startDate = 18000, endDate = 2696400"
    if failure == 'service_reason':
        reason = 'Service temporarily unavailable'
    debug = ' (1d 2026-01-05 -> 2026-02-02)'
    if failure == 'error_status':
        debug += '(Yahoo status_code = 503)'
    def history(**kwargs):
        raise YFPricesMissingError('DOCN', debug, yahoo_reason=reason)
    source = SimpleNamespace(history=history, _price_history=SimpleNamespace(
        tz=None if failure == 'no_timezone' else 'America/New_York'))
    monkeypatch.setattr(yf, 'Ticker', lambda symbol: source)
    with pytest.raises(VendorUnavailableError):
        get_settlement_closes('DOCN', '2026-01-05', '2026-02-02')


def test_actual_vendor_no_data_parser_reaches_three_check_terminal_policy(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from yfinance.scrapers.history import PriceHistory

    from tests.test_settlement_pass import record, series
    from tradingagents.dataflows.vendors.yahoo import market
    from tradingagents.memory import publication_outcomes as outcomes, settlement

    cfg = {'results_dir': str(tmp_path)}
    row = record(cfg, monkeypatch)
    clock = [datetime(2026, 8, 3, 22, tzinfo=UTC)]
    requests = []
    def http(**kwargs):
        requests.append(kwargs)
        params = kwargs['params']
        reason = f"Data doesn't exist for startDate = {params['period1']}, endDate = {params['period2']}"
        return SimpleNamespace(text='', json=lambda: {
            'chart': {'result': None, 'error': {'code': 'Bad Request', 'description': reason}}})
    ticker_class = yf.Ticker
    def source(symbol):
        ticker = ticker_class(symbol)
        ticker._price_history = PriceHistory(
            SimpleNamespace(get=http, cache_get=http), symbol, 'America/New_York')
        return ticker
    monkeypatch.setattr(yf, 'Ticker', source)
    benchmark = series(pd.bdate_range('2026-01-01', '2026-11-06'), 400)
    def fetch(symbol, start, end):
        if symbol == 'DOCN':
            return market.get_settlement_closes(symbol, start, end)
        assert symbol == 'SPY'
        selected = benchmark[(benchmark.index.tz_localize(None) >= start) &
                             (benchmark.index.tz_localize(None) < end)].copy()
        selected.attrs.update(settlement_request_start=start, settlement_request_end=end)
        return selected
    monkeypatch.setattr(settlement, 'get_settlement_closes', fetch)
    monkeypatch.setattr(outcomes, '_now', lambda: clock[0])
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: clock[0].date().isoformat())
    for index in range(3):
        outcomes.settle_publications(cfg)
        endpoint = outcomes.load_outcomes(cfg, row)['endpoints']['5_sessions']
        assert len(endpoint['zero_checks']) == index + 1
        assert all(check['zero_source'] == 'yahoo_explicit_window_no_data' for check in endpoint['zero_checks'])
        clock[0] += timedelta(days=14)
    assert endpoint['status'] == 'unresolvable'
    assert len(requests) == 3
    outcomes.settle_publications(cfg)
    assert len(requests) == 3  # All declared horizons reached terminal; no endpoint-only fetch.
