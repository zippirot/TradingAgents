"""The latest trading day's bar must not silently vanish (#1201).

yfinance can return the newest in-range bar with a NaN close (an unsettled or
glitched session). The old path parsed dates without normalizing timezone and
dropped every NaN-close row before applying the curr_date cutoff, so the latest
bar disappeared and the previous trading day looked like the latest. Now dates
are normalized before the cutoff, so the frame ends at the last settled bar
instead of carrying a fabricated close.

Refusing the whole frame instead (the first attempt at #1201) reported a
tradable symbol as invalid or delisted (#1289), so only a range with no close
anywhere counts as no data and the staleness check judges the rest.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.yahoo import ohlcv


def _stamp(path, ts):
    """Set ``path``'s mtime to the wall-clock ``ts``, read back in local time as
    the cache does. A naive ``pd.Timestamp.timestamp()`` would be taken as UTC."""
    t = ts.to_pydatetime().timestamp()
    os.utime(path, (t, t))

# --- date normalization -----------------------------------------------------


@pytest.mark.unit
def test_normalize_dates_strips_tz_and_normalizes_to_midnight():
    aware = pd.Series(pd.to_datetime(
        ["2026-05-08 09:30:00-04:00", "2026-05-09 16:00:00-04:00"]
    ))
    out = ohlcv._normalize_dates(aware)
    assert out.dt.tz is None
    assert list(out) == [pd.Timestamp("2026-05-08"), pd.Timestamp("2026-05-09")]


@pytest.mark.unit
def test_normalize_dates_leaves_naive_dates_at_midnight():
    naive = pd.Series(pd.to_datetime(["2026-05-08 14:30:00", "2026-05-09 00:00:00"]))
    out = ohlcv._normalize_dates(naive)
    assert out.dt.tz is None
    assert list(out) == [pd.Timestamp("2026-05-08"), pd.Timestamp("2026-05-09")]


@pytest.mark.unit
def test_normalize_dates_handles_mixed_dst_offsets():
    # 5y of US bars span DST; via a cache CSV they arrive as mixed-offset
    # strings, which pd.to_datetime can't unify. Each keeps its own local date.
    mixed = pd.Series([
        "2026-01-08 00:00:00-05:00",  # EST
        "2026-06-08 00:00:00-04:00",  # EDT
        "not-a-date",                 # -> NaT
    ])
    out = ohlcv._normalize_dates(mixed)
    assert out.iloc[0] == pd.Timestamp("2026-01-08")
    assert out.iloc[1] == pd.Timestamp("2026-06-08")
    assert pd.isna(out.iloc[2])


@pytest.mark.unit
def test_normalize_dates_keeps_positive_offset_local_date():
    # A Tokyo bar at local midnight (+09:00) must stay on its own calendar day,
    # not shift to the previous UTC day (which utc=True parsing would cause).
    jst = pd.Series(["2026-05-08 00:00:00+09:00"])
    assert ohlcv._normalize_dates(jst).iloc[0] == pd.Timestamp("2026-05-08")


# --- fill vs guard responsibilities ----------------------------------------

@pytest.mark.unit
def test_clean_dataframe_keeps_nan_close_for_the_caller_to_inspect():
    # _clean_dataframe normalizes but no longer drops the NaN close itself.
    df = pd.DataFrame({"Date": ["2026-05-08", "2026-05-09"], "Close": [100.0, float("nan")]})
    cleaned = ohlcv._clean_dataframe(df)
    assert len(cleaned) == 2
    assert pd.isna(cleaned["Close"].iloc[-1])


@pytest.mark.unit
def test_fill_price_gaps_drops_nan_close_rows():
    df = pd.DataFrame({"Date": pd.to_datetime(["2026-05-07", "2026-05-08"]),
                       "Close": [float("nan"), 100.0]})
    filled = ohlcv._fill_price_gaps(df)
    assert len(filled) == 1
    assert filled["Close"].iloc[0] == 100.0


# --- load_ohlcv end-to-end (with a mocked cache read) -----------------------

def _run_load(monkeypatch, tmp_path, frame, curr_date):
    """Drive load_ohlcv against a pre-seeded cache frame (no network)."""
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    today = pd.Timestamp(curr_date) + pd.Timedelta(hours=23)
    monkeypatch.setattr(ohlcv, "_retrieval_time", lambda: today.tz_localize("UTC").to_pydatetime())
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: today))
    cache_file = tmp_path / "AAPL-YFin-data.csv"
    source = {"ticker": "AAPL", "retrieved_at": today.tz_localize("UTC").isoformat(),
              "exchange_timezone": "UTC", "regular_end": curr_date + "T22:00:00+00:00",
              "currency": "USD", "adjustment_basis": ohlcv.ADJUSTMENT, "source_id": "fixture-cache"}
    cache_file.write_text(frame.assign(__market_source=json.dumps(source)).to_csv(index=False))
    _stamp(cache_file, today)

    def _fail_download(*a, **k):
        raise AssertionError("should use the seeded cache, not download")
    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda symbol: SimpleNamespace(history=_fail_download))
    return ohlcv.load_ohlcv("AAPL", curr_date)


@pytest.mark.unit
def test_unsettled_latest_bar_is_served_as_the_last_settled_bar(monkeypatch, tmp_path):
    # Newest bar (the curr_date) has no close: serve the last settled bar rather
    # than reporting the whole symbol as unavailable (#1289).
    frame = pd.DataFrame({
        "Date": ["2026-05-07", "2026-05-08"],
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [100.5, float("nan")], "Volume": [1_000_000, 1_000_000],
    })
    out = _run_load(monkeypatch, tmp_path, frame, "2026-05-08")
    assert out["Date"].iloc[-1] == pd.Timestamp("2026-05-07")
    assert out["Close"].iloc[-1] == 100.5


@pytest.mark.unit
def test_no_settled_bar_at_all_is_still_no_data(monkeypatch, tmp_path):
    frame = pd.DataFrame({
        "Date": ["2026-05-07", "2026-05-08"],
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [float("nan"), float("nan")], "Volume": [1_000_000, 1_000_000],
    })
    with pytest.raises(NoMarketDataError, match="no bar in range has a closing price"):
        _run_load(monkeypatch, tmp_path, frame, "2026-05-08")


@pytest.mark.unit
def test_serving_the_last_settled_bar_does_not_bypass_the_staleness_check(
    monkeypatch, tmp_path
):
    # Falling back must not resurrect a long-dead series: once the closeless
    # tail is gone, the remaining bar is judged on its age like any other.
    frame = pd.DataFrame({
        "Date": ["2026-01-05", "2026-05-08"],
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [100.5, float("nan")], "Volume": [1_000_000, 1_000_000],
    })
    with pytest.raises(NoMarketDataError, match="stale"):
        _run_load(monkeypatch, tmp_path, frame, "2026-05-08")


@pytest.mark.unit
def test_older_nan_close_row_is_still_dropped(monkeypatch, tmp_path):
    # A stale gap mid-series is dropped; the valid latest bar is served.
    frame = pd.DataFrame({
        "Date": ["2026-05-06", "2026-05-07", "2026-05-08"],
        "Open": [100.0, 101.0, 102.0], "High": [101.0, 102.0, 103.0],
        "Low": [99.0, 100.0, 101.0],
        "Close": [100.5, float("nan"), 102.5], "Volume": [1_000_000, 1_000_000, 1_000_000],
    })
    out = _run_load(monkeypatch, tmp_path, frame, "2026-05-08")
    assert out["Close"].iloc[-1] == 102.5
    assert (out["Date"] == pd.Timestamp("2026-05-07")).sum() == 0  # the NaN row is gone


@pytest.mark.unit
def test_tz_aware_latest_bar_is_kept_at_the_cutoff(monkeypatch, tmp_path):
    # A tz-aware/intraday latest bar on the cutoff day must not be filtered out
    # by a naive-vs-aware comparison.
    frame = pd.DataFrame({
        "Date": ["2026-05-07 09:30:00-04:00", "2026-05-08 09:30:00-04:00"],
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [100.5, 101.5], "Volume": [1_000_000, 1_000_000],
    })
    out = _run_load(monkeypatch, tmp_path, frame, "2026-05-08")
    assert out["Close"].iloc[-1] == 101.5
    assert out["Date"].iloc[-1] == pd.Timestamp("2026-05-08")


@pytest.mark.unit
def test_the_snapshot_does_not_present_a_filled_price_as_reported(monkeypatch, tmp_path):
    """Gap filling exists so indicators compute on a continuous series. The
    verification snapshot is the one place a number must be what the vendor
    reported, or the module built to stop invented prices supplies them."""
    from tradingagents.dataflows.vendors.yahoo import ohlcv, snapshot

    frame = pd.DataFrame({
        "Date": ["2026-05-06", "2026-05-07", "2026-05-08"],
        "Open": [100.0, 104.5, ""],     # the latest bar has not settled
        "High": [101.0, 105.5, ""],
        "Low": [99.0, 103.5, ""],
        "Close": [100.5, 105.0, 106.0],
        "Volume": [1000000, 1000000, ""],
    })
    # A completed row can still have a missing high/open/volume. This test
    # verifies no gap fill, independently of the intraday finality tests.
    today = pd.Timestamp("2026-05-08 23:00")
    monkeypatch.setattr(ohlcv, "_retrieval_time", lambda: today.tz_localize("UTC").to_pydatetime())
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: today))
    cache = tmp_path / "AAPL-YFin-data.csv"
    source = {"ticker": "AAPL", "retrieved_at": today.tz_localize("UTC").isoformat(),
              "exchange_timezone": "UTC", "regular_end": "2026-05-08T22:00:00+00:00",
              "currency": "USD", "adjustment_basis": ohlcv.ADJUSTMENT, "source_id": "fixture-cache"}
    cache.write_text(frame.assign(__market_source=json.dumps(source)).to_csv(index=False))
    _stamp(cache, today)
    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda symbol: SimpleNamespace(
        history=lambda *a, **k: (_ for _ in ()).throw(AssertionError("should read the seeded cache"))))

    out = snapshot.build_verified_market_snapshot("AAPL", "2026-05-08", 3)

    row = out.split("Latest verified OHLCV row")[1].split("###")[0]
    assert "104.50" not in row and "105.50" not in row  # the previous session's numbers
    assert "106.00" in row  # the close the vendor did report

# --- historical split-adjustment basis --------------------------------------

def _historical_market(monkeypatch, tmp_path, *, cache=False, cache_actions=True,
                       cache_marker=True,
                       splits=(0, 0, 0), download_fails=False,
                       dates=("2026-10-30", "2026-11-03", "2026-11-06")):
    from tradingagents.dataflows.vendors.yahoo.market import get_YFin_data_online

    now = pd.Timestamp("2026-11-07 23:00")
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: now))
    monkeypatch.setattr(ohlcv, "_retrieval_time", lambda: now.tz_localize("UTC").to_pydatetime())
    frame = pd.DataFrame({"Date": pd.to_datetime(dates),
                          "Close": [42.0, 84.0, 85.0][:len(dates)],
                          "Stock Splits": list(splits)}).set_index("Date")
    calls = []

    def history(**kwargs):
        calls.append(kwargs)
        if download_fails:
            raise RuntimeError("offline vendor failure")
        return frame.copy()

    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda symbol: SimpleNamespace(
        history=history,
        get_history_metadata=lambda: {"exchangeTimezoneName": "UTC", "currency": "USD"},
    ))
    cache_file = tmp_path / "AAPL-YFin-data.csv"
    if cache:
        source = {"ticker": "AAPL", "retrieved_at": now.tz_localize("UTC").isoformat(),
                  "exchange_timezone": "UTC", "regular_end": None, "currency": "USD",
                  "adjustment_basis": ohlcv.ADJUSTMENT, "source_id": "cached",
                  **({"actions_requested": True} if cache_marker else {})}
        cached = frame.reset_index()
        if not cache_actions:
            cached = cached.drop(columns=["Stock Splits"])
        cache_file.write_text(cached.assign(__market_source=json.dumps(source)).to_csv(index=False))
        _stamp(cache_file, now)
    return get_YFin_data_online, calls, cache_file


@pytest.mark.unit
@pytest.mark.parametrize("cache", [False, True])
def test_historical_market_rejects_later_split_before_cutoff_filter(monkeypatch, tmp_path, cache):
    tool, calls, _ = _historical_market(monkeypatch, tmp_path, cache=cache, splits=(0, 2, 0))
    with pytest.raises(NoMarketDataError, match="adjustment basis.*not compatible"):
        tool("AAPL", "2026-10-29", "2026-10-30")
    if not cache:
        assert calls[0]["actions"] is True


@pytest.mark.unit
@pytest.mark.parametrize("splits,as_of", [
    ((2, 0, 0), "2026-11-03"),  # split is before the requested cutoff
    ((0, 0, 0), "2026-10-30"),  # absence verified through retrieval
])
@pytest.mark.parametrize("cache", [False, True])
def test_historical_market_returns_only_cutoff_rows_when_basis_comparable(
    monkeypatch, tmp_path, splits, as_of, cache
):
    tool, calls, _ = _historical_market(monkeypatch, tmp_path, splits=splits, cache=cache)
    response = tool("AAPL", "2026-10-29", as_of)
    assert "2026-10-30,42.0" in response
    assert "2026-11-06" not in response
    assert ("2026-11-03,84.0" in response) == (as_of == "2026-11-03")
    assert "Stock Splits" not in response and "stock_splits" not in response
    if cache:
        assert not calls
    else:
        assert calls[0]["actions"] is True


@pytest.mark.unit
@pytest.mark.parametrize("dates,splits", [
    (("2026-11-03", "2026-11-06"), (0, 0)),
    (("2026-10-30", "2026-11-03", "2026-11-06"), (0, float("nan"), 0)),
])
def test_historical_market_requires_coverage_and_known_actions(
    monkeypatch, tmp_path, dates, splits
):
    tool, _, _ = _historical_market(monkeypatch, tmp_path, dates=dates, splits=splits)
    with pytest.raises(NoMarketDataError, match="adjustment basis verification unavailable"):
        tool("AAPL", "2026-10-29", "2026-10-30")


@pytest.mark.unit
@pytest.mark.parametrize("download_fails", [False, True])
@pytest.mark.parametrize("cache_actions,cache_marker", [(True, False), (False, True)])
def test_legacy_cache_refetches_for_historical_action_verification(
    monkeypatch, tmp_path, download_fails, cache_actions, cache_marker
):
    tool, calls, _ = _historical_market(monkeypatch, tmp_path, cache=True,
                                       cache_actions=cache_actions, cache_marker=cache_marker,
                                       download_fails=download_fails)
    if download_fails:
        from tradingagents.dataflows.errors import VendorUnavailableError
        with pytest.raises(VendorUnavailableError):
            tool("AAPL", "2026-10-29", "2026-10-30")
    else:
        response = tool("AAPL", "2026-10-29", "2026-10-30")
        assert "2026-10-30,42.0" in response and "2026-11-03" not in response
    assert len(calls) == 1 and calls[0]["actions"] is True
