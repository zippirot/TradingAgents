"""Completed-session boundaries through the real stock, snapshot and indicator paths."""
import os
from datetime import UTC, datetime

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo import market, ohlcv, price_observation, snapshot


def install(monkeypatch, tmp_path, now="2026-11-05T17:00:00+00:00", end="2026-11-05T21:00:00+00:00", zone="America/New_York", dates=None, cutoff=None):
    clock = {"now": datetime.fromisoformat(now)}
    metadata = {"symbol": "DOCN", "currency": "USD", "exchangeTimezoneName": zone}
    if end:
        metadata["currentTradingPeriod"] = {"regular": {"end": datetime.fromisoformat(end)}}
    days = pd.to_datetime(dates or ["2026-11-03", "2026-11-04", "2026-11-05"]).tz_localize(zone)
    frame = pd.DataFrame({"Open": [80., 83., 80.], "High": [85., 85., 81.21], "Low": [79., 82., 72.],
                          "Close": [83., 84.02, 74.24], "Volume": [1000, 2000, 3000],
                          "Stock Splits": [0., 0., 0.]}, index=days)
    frame.index.name = "Date"
    calls = []

    class Ticker:
        def history(self, **kwargs):
            calls.append(kwargs)
            dates = frame.index.strftime("%Y-%m-%d")
            return frame[(dates >= kwargs["start"]) & (dates < kwargs["end"])].copy()

        def get_history_metadata(self):
            return metadata

    config = {"data_cache_dir": str(tmp_path)}
    if cutoff:
        config["_market_observation_cutoff"] = cutoff
    monkeypatch.setattr(ohlcv, "get_config", lambda: config)
    monkeypatch.setattr(price_observation, "_now", lambda: clock["now"])
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: pd.Timestamp(clock["now"]).tz_convert(None)))
    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda symbol: Ticker())
    return clock, calls, frame


def test_docn_partial_bar_excluded_before_all_calculations(monkeypatch, tmp_path):
    _, calls, _ = install(monkeypatch, tmp_path)
    stock = market.get_YFin_data_online("DOCN", "2026-11-03", "2026-11-05")
    report = snapshot.build_verified_market_snapshot("DOCN", "2026-11-05")
    indicators = market._get_stock_stats_bulk("DOCN", "close_50_sma", "2026-11-05")
    assert "74.24" not in stock
    assert "| Close | 84.02 |" in report
    assert "2026-11-05" not in indicators
    assert float(indicators["2026-11-04"]) == pytest.approx((83 + 84.02) / 2)
    assert all(c["auto_adjust"] is False for c in calls)
    assert "completed" in stock.lower()
    assert "not dividend-adjusted" in report


@pytest.mark.parametrize("now,end,expected", [
    ("2026-11-05T13:00:00+00:00", "2026-11-05T21:00:00+00:00", "2026-11-04"),
    ("2026-11-05T21:01:00+00:00", "2026-11-05T21:00:00+00:00", "2026-11-05"),
    ("2026-11-05T23:00:00+00:00", None, "2026-11-04"),
    ("2026-11-05T23:00:00+00:00", "2026-11-04T21:00:00+00:00", "2026-11-04"),
    ("2026-11-07T17:00:00+00:00", None, "2026-11-05"),
])
def test_actual_loader_respects_session_metadata(monkeypatch, tmp_path, now, end, expected):
    install(monkeypatch, tmp_path, now=now, end=end)
    frame = ohlcv.load_ohlcv("DOCN", now[:10])
    assert str(frame["Date"].iloc[-1].date()) == expected
    assert frame.attrs["market_provenance"]["session_status"] == "completed"


def test_preclose_cache_is_not_promoted_when_clock_passes_close(monkeypatch, tmp_path):
    clock, calls, _ = install(monkeypatch, tmp_path, now="2026-11-05T20:59:00+00:00")
    first = ohlcv.load_ohlcv("DOCN", "2026-11-05")
    assert first["Close"].iloc[-1] == 84.02
    cache = tmp_path / "DOCN-YFin-data.csv"
    stamp = pd.Timestamp(clock["now"]).tz_convert(None).to_pydatetime().timestamp()
    os.utime(cache, (stamp, stamp))
    clock["now"] = datetime(2026, 11, 5, 21, 1, tzinfo=UTC)
    second = ohlcv.load_ohlcv("DOCN", "2026-11-05")
    # Retaining the prior session until the existing TTL refresh is intentional.
    assert second["Close"].iloc[-1] == 84.02
    assert len(calls) == 1


@pytest.mark.parametrize("zone,now,end,dates", [
    ("America/New_York", "2026-07-02T17:01:00+00:00", "2026-07-02T17:00:00+00:00", ["2026-06-30", "2026-07-01", "2026-07-02"]),
    ("Asia/Tokyo", "2026-11-05T06:31:00+00:00", "2026-11-05T06:30:00+00:00", ["2026-11-03", "2026-11-04", "2026-11-05"]),
    ("UTC", "2026-11-05T17:00:00+00:00", None, ["2026-11-03", "2026-11-04", "2026-11-05"]),
])
def test_early_close_dst_non_us_and_continuous_asset_scope(monkeypatch, tmp_path, zone, now, end, dates):
    install(monkeypatch, tmp_path, now, end, zone, dates)
    frame = ohlcv.load_ohlcv("DOCN", now[:10])
    assert frame["Close"].iloc[-1] == (84.02 if end is None else 74.24)


def test_historical_cutoff_and_frozen_intraday_cutoff(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, now="2026-11-05T22:00:00+00:00", cutoff="2026-11-05T17:00:00+00:00")
    assert ohlcv.load_ohlcv("DOCN", "2026-11-05")["Close"].iloc[-1] == 84.02
    assert ohlcv.load_ohlcv("DOCN", "2026-11-03")["Close"].iloc[-1] == 83


def test_exchange_date_ahead_of_host_date_has_same_completed_close(monkeypatch, tmp_path):
    clock, calls, _ = install(monkeypatch, tmp_path, now="2026-11-05T06:31:00+00:00",
                              end="2026-11-05T06:30:00+00:00", zone="Asia/Tokyo")
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: pd.Timestamp("2026-11-04 23:31")))
    earlier = ohlcv.load_ohlcv("DOCN", "2026-11-04")
    assert earlier["Close"].iloc[-1] == 84.02
    cache = tmp_path / "DOCN-YFin-data.csv"
    stamp = pd.Timestamp("2026-11-04 23:31").to_pydatetime().timestamp()
    os.utime(cache, (stamp, stamp))
    technical = ohlcv.load_ohlcv("DOCN", "2026-11-05")
    assert len(calls) == 1
    canonical = price_observation.get_price_observation("DOCN", "2026-11-05")
    assert canonical["status"] == "available"
    assert str(technical["Date"].iloc[-1].date()) == canonical["session_date"] == "2026-11-05"
    assert technical["Close"].iloc[-1] == float(canonical["close"]) == 74.24


def test_graph_injected_cutoff_keeps_tools_and_canonical_price_on_same_session(monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, StateGraph
    from langgraph.prebuilt import ToolNode

    from tradingagents.agents.state import AgentState
    from tradingagents.agents.tools import (
        get_indicators,
        get_stock_data,
        get_verified_market_snapshot,
    )
    from tradingagents.dataflows import config
    from tradingagents.dataflows.vendors.yahoo.price_observation import completed_price_scope

    install(monkeypatch, tmp_path, now="2026-11-05T22:00:00+00:00")
    monkeypatch.setattr(ohlcv, "get_config", config.get_config)
    state = {
        "company_of_interest": "DOCN", "trade_date": "2026-11-05",
        "market_observation_cutoff": "2026-11-05T17:00:00+00:00",
        "messages": [AIMessage(content="", tool_calls=[
            {"name": "get_stock_data", "id": "stock", "args": {"start_date": "2026-11-03", "end_date": "2026-11-05"}},
            {"name": "get_verified_market_snapshot", "id": "snapshot", "args": {"curr_date": "2026-11-05"}},
            {"name": "get_indicators", "id": "indicator", "args": {"indicator": "close_50_sma", "curr_date": "2026-11-05", "look_back_days": 2}},
        ])],
    }
    cfg = {"data_cache_dir": str(tmp_path), "data_vendors": {"core_stock_apis": "yfinance",
                                                          "technical_indicators": "yfinance"}}
    with config.run_config(cfg):
        graph = StateGraph(AgentState)
        graph.add_node("tools", ToolNode([get_stock_data, get_verified_market_snapshot, get_indicators]))
        graph.add_edge(START, "tools")
        graph.add_edge("tools", END)
        result = graph.compile().invoke(state)
        with completed_price_scope(state):
            canonical = price_observation.get_price_observation("DOCN", "2026-11-05")
    messages = [m.content for m in result["messages"] if m.type == "tool"]
    assert all("74.24" not in text for text in messages)
    assert "84.02" in messages[0] and "| Close | 84.02 |" in messages[1]
    assert "2026-11-05: N/A: No completed bar" in messages[2]
    assert canonical["session_date"] == "2026-11-04" and canonical["close"] == "84.02"


def test_legacy_adjusted_cache_refreshes_through_existing_fetch(monkeypatch, tmp_path):
    _, calls, _ = install(monkeypatch, tmp_path)
    cache = tmp_path / "DOCN-YFin-data.csv"
    pd.DataFrame({"Date": ["2026-11-04"], "Close": [999.]}).to_csv(cache, index=False)
    actual = ohlcv.load_ohlcv("DOCN", "2026-11-05")
    assert len(calls) == 1
    assert actual["Close"].iloc[-1] == 84.02
    assert actual.attrs["market_provenance"]["adjustment_basis"] == price_observation.ADJUSTMENT



@pytest.mark.parametrize("now,expected", [
    ("2026-11-05T17:00:00+00:00", 84.02),
    ("2026-11-05T22:00:00+00:00", 74.24),
])
def test_installed_yfinance_lazy_mapping_preserves_session_metadata(monkeypatch, tmp_path, now, expected):
    from types import SimpleNamespace

    from yfinance.scrapers.history import HistoryMetadata

    install(monkeypatch, tmp_path, now=now)
    ticker = ohlcv.yf.Ticker("DOCN")
    plain = ticker.get_history_metadata()
    lazy = HistoryMetadata(SimpleNamespace(
        _history_metadata=plain,
        _load_history_metadata_trading_periods=lambda: pytest.fail("must not fetch lazy intraday periods"),
    ))
    ticker.get_history_metadata = lambda: lazy
    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda _: ticker)
    result = ohlcv.load_ohlcv("DOCN", "2026-11-05")
    assert result.attrs["market_provenance"]["currency"] == "USD"
    assert result.attrs["market_provenance"]["regular_end"] == "2026-11-05T21:00:00+00:00"
    assert result["Close"].iloc[-1] == expected


@pytest.mark.parametrize("missing_count", [1, 2])
def test_missing_completed_close_reason_reaches_stock_snapshot_and_indicator(monkeypatch, tmp_path, missing_count):
    _, _, frame = install(monkeypatch, tmp_path, now="2026-11-05T22:00:00+00:00")
    frame.loc[frame.index[-missing_count:], "Close"] = float("nan")
    selected = "2026-11-04" if missing_count == 1 else "2026-11-03"
    data = ohlcv.load_ohlcv("DOCN", "2026-11-05")
    fallback = data.attrs["market_provenance"]["price_fallback"]
    assert fallback["latest_completed_session_date"] == "2026-11-05"
    assert fallback["selected_session_date"] == selected
    assert len(fallback["missing_completed_session_dates"]) == missing_count
    stock = market.get_YFin_data_online("DOCN", "2026-11-03", "2026-11-05")
    report = snapshot.build_verified_market_snapshot("DOCN", "2026-11-05")
    indicators = market.get_stock_stats_indicators_window("DOCN", "close_50_sma", "2026-11-05", 2)
    for text in (stock, report, indicators):
        assert fallback["reason"] in text
        assert "latest completed session 2026-11-05" in text
        assert "selected session " + selected in text
    assert "2026-11-05: N/A: No completed bar" in indicators
    assert "74.24" not in stock + report + indicators


def test_partial_missing_close_does_not_claim_completed_fallback(monkeypatch, tmp_path):
    _, _, frame = install(monkeypatch, tmp_path)
    frame.loc[frame.index[-1], "Close"] = float("nan")
    data = ohlcv.load_ohlcv("DOCN", "2026-11-05")
    assert data.attrs["market_provenance"]["session_date"] == "2026-11-04"
    assert "price_fallback" not in data.attrs["market_provenance"]
    assert "Latest completed session has no close" not in "\n".join(ohlcv.market_provenance_lines(data))


@pytest.mark.parametrize("invalid", ["broken", "NaN", float("inf"), -1, 0, True])
def test_invalid_nonempty_completed_close_is_not_empty_fallback(monkeypatch, tmp_path, invalid):
    from tradingagents.dataflows.errors import NoMarketDataError
    _, _, frame = install(monkeypatch, tmp_path, now="2026-11-05T22:00:00+00:00")
    frame["Close"] = frame["Close"].astype(object)
    frame.loc[frame.index[-1], "Close"] = invalid
    with pytest.raises(NoMarketDataError, match="invalid nonempty closing price"):
        ohlcv.load_ohlcv("DOCN", "2026-11-05")

@pytest.mark.parametrize("empty", [None, "", "   "])
def test_empty_provider_closes_get_labeled_fallback(monkeypatch, tmp_path, empty):
    _, _, frame = install(monkeypatch, tmp_path, now="2026-11-05T22:00:00+00:00")
    frame["Close"] = frame["Close"].astype(object)
    frame.loc[frame.index[-1], "Close"] = empty
    data = ohlcv.load_ohlcv("DOCN", "2026-11-05")
    assert data.attrs["market_provenance"]["price_fallback"]["selected_session_date"] == "2026-11-04"
    assert data["Close"].iloc[-1] == 84.02


def test_indicator_reason_does_not_fetch_a_second_series(monkeypatch, tmp_path):
    _, calls, frame = install(monkeypatch, tmp_path, now="2026-11-05T22:00:00+00:00")
    frame.loc[frame.index[-1], "Close"] = float("nan")
    report = market.get_stock_stats_indicators_window("DOCN", "close_50_sma", "2026-11-05", 2)
    assert "Latest completed session has no close" in report
    assert len(calls) == 1
