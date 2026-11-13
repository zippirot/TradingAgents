"""One-query retained historical Yahoo closes and split-basis replay."""
from copy import deepcopy
from datetime import UTC, datetime

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo import reference_history

ENDS = ("2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30")
NOW = "2026-11-05T22:00:00+00:00"


def install(monkeypatch, *, now=NOW, split_date=None, split_ratio=2, missing=(), metadata=None, blank=()):
    calls = []
    dates = pd.bdate_range("2025-12-24", "2026-11-05", tz="America/New_York")
    dates = [day for day in dates if day.date().isoformat() not in missing]
    splits = [split_ratio if day.date().isoformat() == split_date else 0 for day in dates]
    closes = [float("nan") if day.date().isoformat() in blank else 20 for day in dates]
    frame = pd.DataFrame({"Close": closes, "Stock Splits": splits}, index=dates)
    meta = {"symbol": "DOCN", "currency": "USD", "exchangeTimezoneName": "America/New_York",
            "currentTradingPeriod": {"regular": {"end": datetime(2026, 11, 5, 21, tzinfo=UTC)}}}
    if metadata:
        meta.update(metadata)
    monkeypatch.setattr(reference_history, "_now", lambda: datetime.fromisoformat(now))

    class Ticker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return frame

        def get_history_metadata(self):
            return meta

    monkeypatch.setattr(reference_history.yf, "Ticker", lambda ticker: Ticker())
    return calls


@pytest.mark.unit
def test_one_bounded_query_retains_source_and_replays_quarter_prices(monkeypatch):
    calls = install(monkeypatch, split_date="2026-06-15")
    record = reference_history.get_reference_history("DOCN", "2026-11-05", ENDS)
    assert record["status"] == "available", record
    assert len(calls) == 1
    assert calls[0] == {"start": "2025-12-24", "end": "2026-11-06", "interval": "1d",
                        "auto_adjust": False, "actions": True}
    prices, splits = reference_history.replay_reference_history(record, "DOCN", "2026-11-05", ENDS)
    assert len(prices) == 4
    assert all(p["session_status"] == "completed" and p["close"] == "20" for p in prices)
    assert all(p["ticker"] == "DOCN" and p["split_basis_date"] == "2026-11-05" for p in prices)
    assert all(p["content_hash"] == record["content_hash"] for p in prices)
    assert splits["coverage_complete"] is True
    assert splits["splits"] == [{"session_date": "2026-06-15", "ratio": "2", "source_id": record["source_id"]}]


@pytest.mark.unit
def test_replay_detects_hash_identity_and_projection_tampering(monkeypatch):
    install(monkeypatch)
    record = reference_history.get_reference_history("DOCN", "2026-11-05", ENDS)
    for change in (
        lambda r: r["raw_source"]["bars"][0].update(close="999"),
        lambda r: r.update(ticker="AAPL"),
        lambda r: r.update(content_hash="a" * 64),
        lambda r: r["raw_source"]["metadata"].update(currency="EUR"),
    ):
        altered = deepcopy(record)
        change(altered)
        with pytest.raises(ValueError):
            reference_history.replay_reference_history(altered, "DOCN", "2026-11-05", ENDS)


@pytest.mark.unit
def test_incomplete_current_bar_never_becomes_completed_quarter_price(monkeypatch):
    install(monkeypatch, now="2026-11-05T20:00:00+00:00")
    ends = (*ENDS, "2026-11-05")
    record = reference_history.get_reference_history("DOCN", "2026-11-05", ends)
    assert record["status"] == "available", record
    prices, _ = reference_history.replay_reference_history(record, "DOCN", "2026-11-05", ends)
    assert prices[-1]["quarter_end"] == "2026-11-05"
    assert prices[-1]["session_date"] == "2026-11-04"


@pytest.mark.unit
def test_future_split_or_missing_continuity_makes_history_unavailable(monkeypatch):
    install(monkeypatch, split_date="2026-10-15")
    result = reference_history.get_reference_history("DOCN", "2026-09-30", ENDS)
    assert result["status"] == "unavailable" and "split" in result["reason"].lower()

    missing = tuple(day.date().isoformat() for day in pd.bdate_range("2026-02-01", "2026-02-20"))
    install(monkeypatch, missing=missing)
    result = reference_history.get_reference_history("DOCN", "2026-11-05", ENDS)
    assert result["status"] == "unavailable" and "coverage" in result["reason"].lower()


@pytest.mark.unit
def test_duplicate_nonfinite_or_wrong_instrument_is_unavailable(monkeypatch):
    install(monkeypatch)
    original = reference_history.yf.Ticker("DOCN").history()
    def broken(frame):
        class Ticker:
            def history(self, **kwargs):
                return frame

            def get_history_metadata(self):
                return {"symbol": "DOCN", "currency": "USD",
                        "exchangeTimezoneName": "America/New_York",
                        "currentTradingPeriod": {"regular": {"end": datetime(2026, 11, 5, 21, tzinfo=UTC)}}}
        return Ticker

    for frame in (pd.concat([original, original.iloc[[0]]]), original.assign(Close=float("nan"))):
        monkeypatch.setattr(reference_history.yf, "Ticker", broken(frame))
        assert reference_history.get_reference_history("DOCN", "2026-11-05", ENDS)["status"] == "unavailable"
    install(monkeypatch, metadata={"symbol": "AAPL"})
    assert reference_history.get_reference_history("DOCN", "2026-11-05", ENDS)["status"] == "unavailable"


@pytest.mark.unit
def test_an_empty_close_on_the_latest_bar_does_not_cost_the_whole_history(monkeypatch):
    """Seen 2026-11-12 evening on MSFT, DOCN and JPM (14 runs): the vendor returned the latest bar with no close and
    the whole history, with both own-history references, was dropped. Boundary: only the latest bar, only when it
    carries no split; that bar supplies no price. An empty close anywhere else still makes the history unavailable."""
    install(monkeypatch, blank=("2026-11-05",))
    record = reference_history.get_reference_history("DOCN", "2026-11-05", ENDS)
    assert record["status"] == "available", record
    prices, _splits = reference_history.replay_reference_history(record, "DOCN", "2026-11-05", ENDS)
    assert len(prices) == 4 and all(p["close"] == "20" for p in prices)
    install(monkeypatch, blank=("2026-08-03",))
    assert reference_history.get_reference_history("DOCN", "2026-11-05", ENDS)["status"] == "unavailable"
    install(monkeypatch, blank=("2026-11-05",), split_date="2026-11-05")
    assert reference_history.get_reference_history("DOCN", "2026-11-05", ENDS)["status"] == "unavailable"
