"""Tests for the deterministic market-data verification snapshot (#830/#881)."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.snapshot as validator
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.yahoo import ohlcv, price_observation


def _sample_ohlcv() -> pd.DataFrame:
    dates = pd.bdate_range("2026-04-01", "2026-05-20")
    closes = [100 + i for i in range(len(dates))]
    return pd.DataFrame({
        "Date": dates,
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1_000_000 + i for i in range(len(dates))],
    })


def _band_ohlcv() -> pd.DataFrame:
    """A 252-session window with DOCN-like March closes and a November close."""
    dates = pd.bdate_range(end="2026-11-06", periods=253)
    closes = [72.48] * len(dates)
    closes[0] = 1.00  # outside the most recent 252 completed sessions
    for day, close in {
        "2026-03-02": 66.22,
        "2026-03-12": 68.63,
        "2026-03-25": 68.69,
        "2026-03-30": 62.01,
    }.items():
        closes[dates.get_loc(pd.Timestamp(day))] = close
    return pd.DataFrame({
        "Date": dates,
        "Open": closes,
        "High": closes,
        "Low": closes,
        "Close": closes,
        "Volume": [1000] * len(dates),
    })


@pytest.mark.unit
class TestVerifiedSnapshot:
    def test_band_table_lists_march_closes_below_lower_band(self, monkeypatch):
        calls = []

        def load(symbol, date, fill_gaps=True):
            calls.append((symbol, date, fill_gaps))
            return _band_ohlcv()

        monkeypatch.setattr(validator, "load_ohlcv", load)
        snap = validator.build_verified_market_snapshot("DOCN", "2026-11-06", indicators=("rsi",))
        table = snap.split("### Prior closes by price band", 1)[1]
        assert "65.2–68.9" in table
        assert "| 65.2–68.9 | 3 | 2026-03-25 | 66.22 | 68.69 |" in table
        assert "| 61.6–65.2 | 1 | 2026-03-30 | 62.01 | 62.01 |" in table
        assert "1.00" not in table
        assert calls == [("DOCN", "2026-11-06", False)]

    def test_band_table_respects_cutoff(self, monkeypatch):
        data = _band_ohlcv()
        data.loc[data["Date"] == pd.Timestamp("2026-04-01"), "Close"] = 80.00
        data.loc[len(data)] = [pd.Timestamp("2026-11-09"), 10, 10, 10, 10, 1000]
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)
        snap = validator.build_verified_market_snapshot("DOCN", "2026-11-06", indicators=("rsi",))
        table = snap.split("### Prior closes by price band", 1)[1]
        assert "2026-11-09" not in table
        assert "10.00" not in table
        assert "80.00" not in table
        assert "| 65.2–68.9 | 3 | 2026-03-25 | 66.22 | 68.69 |" in table

    def test_empty_band_says_no_closes(self, monkeypatch):
        data = _band_ohlcv()
        data.loc[data["Close"].isin([66.22, 68.63, 68.69]), "Close"] = 72.48
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)
        snap = validator.build_verified_market_snapshot("DOCN", "2026-11-06", indicators=("rsi",))
        table = snap.split("### Prior closes by price band", 1)[1]
        assert "| 65.2–68.9 | 0 | no closes in the last 252 sessions | — | — |" in table

    def test_band_table_uses_completed_sessions_with_missing_close(self, monkeypatch):
        data = _band_ohlcv()
        missing_date = pd.Timestamp("2026-10-30")
        sessions = data["Date"].tail(252).dt.strftime("%Y-%m-%d").tolist()
        data = data[data["Date"] != missing_date].copy()
        data.attrs["completed_session_dates"] = sessions
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)
        snap = validator.build_verified_market_snapshot("DOCN", "2026-11-06", indicators=("rsi",))
        table = snap.split("### Prior closes by price band", 1)[1]
        assert "1.00" not in table  # an older close cannot replace the missing session
        assert "1 completed session has no available close" in table
        assert "| 65.2–68.9 | 3 | 2026-03-25 | 66.22 | 68.69 |" in table

    def test_missing_close_does_not_make_empty_band_certain(self, monkeypatch):
        data = _band_ohlcv()
        sessions = data["Date"].tail(252).dt.strftime("%Y-%m-%d").tolist()
        data = data[data["Date"] != pd.Timestamp("2026-10-30")].copy()
        data.loc[data["Close"].isin([66.22, 68.63, 68.69]), "Close"] = 72.48
        data.attrs["completed_session_dates"] = sessions
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)
        snap = validator.build_verified_market_snapshot("DOCN", "2026-11-06", indicators=("rsi",))
        table = snap.split("### Prior closes by price band", 1)[1]
        assert "| 65.2–68.9 | 0 | no observed closes; missing close coverage | — | — |" in table
        assert "no closes in the last 252 sessions" not in table

    def test_no_close_in_completed_session_window_reports_unavailable(self, monkeypatch):
        data = _band_ohlcv().iloc[:1].copy()
        data.attrs["completed_session_dates"] = ["2026-11-06"]
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)
        snap = validator.build_verified_market_snapshot("DOCN", "2026-11-06", indicators=("rsi",))
        table = snap.split("### Prior closes by price band", 1)[1]
        assert "No available closes in the completed-session window; price bands unavailable." in table

    def test_excludes_future_rows(self, monkeypatch):
        data = pd.concat([
            _sample_ohlcv(),
            pd.DataFrame({"Date": [pd.Timestamp("2026-06-01")], "Open": [999.0],
                          "High": [999.0], "Low": [999.0], "Close": [999.0], "Volume": [999]}),
        ], ignore_index=True)
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)

        snap = validator.build_verified_market_snapshot("COF", "2026-05-13")
        assert "Verified market data snapshot for COF" in snap
        assert "Requested analysis date: 2026-05-13" in snap
        assert "Latest trading row used: 2026-05-13" in snap
        assert "999.00" not in snap          # future row excluded
        assert "boll_lb" in snap             # indicators present

    def test_uses_previous_trading_day_when_date_is_weekend(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        # 2026-05-16 is a Saturday; latest row should be Fri 2026-05-15
        snap = validator.build_verified_market_snapshot("COF", "2026-05-16")
        assert "Latest trading row used: 2026-05-15" in snap
        assert "Recent verified closes" in snap

    def test_raises_when_no_rows_on_or_before_date(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        with pytest.raises(NoMarketDataError):
            validator.build_verified_market_snapshot("COF", "2020-01-01")

    def test_raises_on_empty_data(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: pd.DataFrame())
        with pytest.raises(NoMarketDataError):
            validator.build_verified_market_snapshot("COF", "2026-05-13")

    def test_look_back_window_capped_at_30(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        snap = validator.build_verified_market_snapshot("COF", "2026-05-20", look_back_days=999)
        # last-N closes table has at most 30 data rows
        close_rows = [ln for ln in snap.splitlines() if ln.startswith("| 2026-")]
        assert 0 < len(close_rows) <= 30


@pytest.mark.unit
class TestTool:
    def test_tool_delegates_to_builder(self, monkeypatch):
        from tradingagents.agents.tools import get_verified_market_snapshot
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        out = get_verified_market_snapshot.invoke(
            {"symbol": "COF", "curr_date": "2026-05-20"}
        )
        assert "Verified market data snapshot for COF" in out


@pytest.mark.unit
def test_band_table_lists_march_closes_from_retained_docn_source(monkeypatch, tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "docn_2026_11_07"
    source = fixture / "DOCN-YFin-data.csv.gz"
    manifest = json.loads((fixture / "manifest.json").read_text())
    expected = manifest["source_files"][source.name]
    compressed = source.read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == expected["sha256"]
    decoded = gzip.decompress(compressed)
    assert hashlib.sha256(decoded).hexdigest() == expected["decoded_sha256"]
    assert len(decoded) == expected["decoded_bytes"]

    captured = pd.read_csv(io.BytesIO(decoded), float_precision="round_trip")
    retained = json.loads(captured.pop("__market_source").iloc[0])
    zone = retained["exchange_timezone"]
    captured["Date"] = pd.to_datetime(captured["Date"], utc=True).dt.tz_convert(zone)
    captured = captured.set_index("Date")
    retrieved = datetime.fromisoformat(retained["retrieved_at"])
    metadata = {
        "currency": retained["currency"],
        "exchangeTimezoneName": zone,
        "currentTradingPeriod": {"regular": {"end": retained["regular_end"]}},
    }
    calls = []

    class Ticker:
        def history(self, **kwargs):
            calls.append(kwargs)
            dates = captured.index.strftime("%Y-%m-%d")
            return captured[(dates >= kwargs["start"]) & (dates < kwargs["end"])].copy()

        def get_history_metadata(self):
            return metadata

    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(price_observation, "_now", lambda: retrieved)
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(
        lambda: pd.Timestamp(retrieved).tz_convert(zone).tz_localize(None)
    ))
    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda symbol: Ticker())

    report = validator.build_verified_market_snapshot("DOCN", "2026-11-06")
    table = report.split("### Prior closes by price band", 1)[1]
    assert "| Close | 72.48 |" in report
    assert "Last 252 available completed sessions (up to 252)" in table
    assert "| 65.2–68.9 | 6 | 2026-03-13 | 66.22 | 68.69 |" in table
    assert "| 61.6–65.2 | 8 | 2026-03-10 | 62.01 | 64.74 |" in table
    for day, close in {
        "2026-03-10": 62.01,
        "2026-03-11": 68.69,
        "2026-03-12": 66.22,
        "2026-03-13": 68.63,
    }.items():
        row = captured.loc[pd.Timestamp(day, tz=zone)]
        assert row["Close"] == pytest.approx(close, abs=0.005)
    assert len(calls) == 1
