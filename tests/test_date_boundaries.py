"""yfinance treats ``end`` as exclusive; we must request one extra day so the
requested end_date (and the current day) is actually included.

Regressions for #986 (current-day OHLCV excluded) and #987 (requested end_date
row omitted).
"""
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.market as yfin
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.vendors.yahoo import ohlcv


@pytest.mark.unit
def test_get_yfin_requests_inclusive_end(monkeypatch, tmp_path):
    set_config({"data_cache_dir": str(tmp_path)})
    captured = {}
    observed = datetime.fromisoformat("2025-05-10T23:00:00+00:00")
    monkeypatch.setattr(ohlcv, "_retrieval_time", lambda: observed)
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: pd.Timestamp("2025-05-10 23:00")))

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end, **kwargs):
            captured["start"] = start
            captured["end"] = end
            idx = pd.to_datetime(["2025-05-08", "2025-05-09"])
            return pd.DataFrame(
                {"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0],
                 "Close": [1.0, 2.0], "Volume": [1, 2], "Stock Splits": [0, 0]},
                index=idx,
            )

        def get_history_metadata(self):
            return {"symbol": "AAPL", "currency": "USD",
                    "exchangeTimezoneName": "America/New_York"}

    monkeypatch.setattr(yfin.yf, "Ticker", FakeTicker)
    out = yfin.get_YFin_data_online("AAPL", "2025-05-01", "2025-05-09")

    # The shared cache may fetch a wider range; its exclusive end must include
    # the requested date and the returned data must retain that completed row.
    assert captured["start"] <= "2025-05-01" and captured["end"] > "2025-05-09"
    assert "2025-05-09,2.0" in out
    # Header still reflects the requested range, not the internal +1 day.
    assert "to 2025-05-09" in out


@pytest.mark.unit
def test_load_ohlcv_requests_inclusive_end(monkeypatch, tmp_path):
    set_config({"data_cache_dir": str(tmp_path)})
    captured = {}
    observed = datetime.fromisoformat("2026-11-05T22:00:00+00:00")
    monkeypatch.setattr(ohlcv, "_retrieval_time", lambda: observed)
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: pd.Timestamp("2026-11-05 22:00")))

    def fake_history(start, end, **kwargs):
        captured["end"] = end
        idx = pd.to_datetime([pd.Timestamp.today().normalize()])
        return pd.DataFrame(
            {"Open": [100.0], "High": [100.0], "Low": [100.0],
             "Close": [100.0], "Volume": [1]},
            index=idx,
        )

    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda symbol: SimpleNamespace(
        history=fake_history, get_history_metadata=lambda: {
            "symbol": "AAPL", "currency": "USD", "exchangeTimezoneName": "America/New_York",
            "currentTradingPeriod": {"regular": {"end": "2026-11-05T21:00:00+00:00"}},
        }))
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    ohlcv.load_ohlcv("AAPL", today)

    assert captured["end"] == "2026-11-07"  # also covers a completed exchange date ahead of UTC
