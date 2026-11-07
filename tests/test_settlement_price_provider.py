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
