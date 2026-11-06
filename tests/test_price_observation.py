from copy import deepcopy
from datetime import UTC, datetime

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo import price_observation as prices


def install(
    monkeypatch,
    now="2026-11-04T20:00:00+00:00",
    dates=("2026-11-03", "2026-11-04"),
    closes=(84, 85),
    metadata=None,
    splits=None,
):
    monkeypatch.setattr(prices, "_now", lambda: datetime.fromisoformat(now))
    meta = {
        "symbol": "DOCN",
        "currency": "USD",
        "exchangeTimezoneName": "America/New_York",
        "currentTradingPeriod": {"regular": {"end": datetime(2026, 11, 4, 21, tzinfo=UTC)}},
    }
    if metadata is not None:
        meta.update(metadata)
    calls = []

    class Ticker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                {"Close": closes, "Stock Splits": splits or [0] * len(dates)},
                index=pd.to_datetime(list(dates)).tz_localize("America/New_York"),
            )

        def get_history_metadata(self):
            return meta

    monkeypatch.setattr(prices.yf, "Ticker", lambda ticker: Ticker())
    return calls


@pytest.mark.parametrize(
    "now,session,close",
    [
        ("2026-11-04T20:00:00+00:00", "2026-11-03", "84"),
        ("2026-11-04T22:00:00+00:00", "2026-11-04", "85"),
    ],
)
def test_completed_session_and_metadata(monkeypatch, now, session, close):
    calls = install(monkeypatch, now)
    record = prices.get_price_observation("DOCN", "2026-11-04")
    assert record["status"] == "available", record
    assert record["session_date"] == session and record["close"] == close
    assert record["session_status"] == "completed" and record["currency"] == "USD"
    assert calls[0]["auto_adjust"] is False and calls[0]["actions"] is True
    assert prices.validate_price_observation(record, "DOCN", "2026-11-04") == record


@pytest.mark.parametrize(
    "metadata", [{"currency": None}, {"exchangeTimezoneName": None}, {"symbol": "MSFT"}]
)
def test_missing_or_mismatched_metadata_fails(monkeypatch, metadata):
    install(monkeypatch, metadata=metadata)
    assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"


def test_historical_weekend_future_stale_and_duplicates(monkeypatch):
    install(monkeypatch, dates=("2026-10-30",), closes=(84,))
    record = prices.get_price_observation("DOCN", "2026-11-01")
    assert record["session_date"] == "2026-10-30"
    assert prices.get_price_observation("DOCN", "2026-11-05")["status"] == "unavailable"
    install(monkeypatch, dates=("2026-10-20",), closes=(84,))
    assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"
    install(monkeypatch, dates=("2026-11-03", "2026-11-03"))
    assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"


@pytest.mark.parametrize("value", [0, -2, float("nan"), float("inf")])
def test_invalid_close_not_promoted(monkeypatch, value):
    install(monkeypatch, dates=("2026-11-03",), closes=(value,))
    assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"


def test_tampering_wrong_identity_and_split_coverage(monkeypatch):
    calls = install(monkeypatch, dates=("2026-09-30", "2026-11-03"), closes=(42, 84), splits=(0, 2))
    record = prices.get_price_observation("DOCN", "2026-11-04", "2026-09-30")
    assert record["coverage_complete"] and record["splits"] == [
        {"session_date": "2026-11-03", "ratio": "2"}
    ]
    assert calls[0]["start"] == "2026-09-23"
    for key, value in [("close", "999"), ("currency", "EUR"), ("session_date", "2026-11-04")]:
        changed = deepcopy(record)
        changed[key] = value
        with pytest.raises(ValueError):
            prices.validate_price_observation(changed, "DOCN", "2026-11-04")
    changed = deepcopy(record)
    changed["raw_source"]["bars"][0]["close"] = "999"
    with pytest.raises(ValueError):
        prices.validate_price_observation(changed, "DOCN", "2026-11-04")
    with pytest.raises(ValueError):
        prices.validate_price_observation(record, "MSFT", "2026-11-04")
    record = prices.get_price_observation("DOCN", "2026-11-04", "2024-01-01")
    assert not record["coverage_complete"] and record["requested_coverage_start"] == "2024-01-01"


@pytest.mark.parametrize("period", [{}, {"regular": {"end": "2026-11-03T21:00:00+00:00"}}])
def test_missing_or_other_date_session_end_uses_prior_close(monkeypatch, period):
    install(monkeypatch, now="2026-11-04T23:00:00+00:00", metadata={"currentTradingPeriod": period})
    record = prices.get_price_observation("DOCN", "2026-11-04")
    assert record["session_date"] == "2026-11-03"


def test_exact_decimal_source_is_not_rounded_by_decimal_context(monkeypatch):
    value = "84.123456789012345678901234567890123456789"
    install(monkeypatch, dates=("2026-11-03",), closes=(value,))
    record = prices.get_price_observation("DOCN", "2026-11-04")
    assert record["close"] == value


def test_same_day_split_is_retained_even_before_completed_close(monkeypatch):
    install(monkeypatch, splits=(0, 2))
    record = prices.get_price_observation("DOCN", "2026-11-04")
    assert record["session_date"] == "2026-11-03"
    assert record["splits"] == [{"session_date": "2026-11-04", "ratio": "2"}]


def test_weekend_capital_snapshot_fetches_preceding_session(monkeypatch):
    calls = install(monkeypatch, dates=("2026-10-30", "2026-11-03"), closes=(83, 84))
    record = prices.get_price_observation("DOCN", "2026-11-04", "2026-11-01")
    assert record["coverage_complete"]
    assert record["capital_snapshot_date"] == "2026-11-01"
    assert calls[0]["start"] == "2026-10-21"
    assert "no exchange-calendar completeness guarantee" in record["coverage_note"]


def test_unknown_split_actions_cannot_claim_coverage(monkeypatch):
    install(monkeypatch, splits=(float("nan"), 0))
    assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"


@pytest.mark.parametrize("later_split,available", [(2, False), (0, True)])
def test_historical_adjustment_checked_through_retrieval_without_future_evidence(
    monkeypatch, later_split, available
):
    install(monkeypatch)
    calls = []

    class Ticker:
        def history(self, **kwargs):
            calls.append(kwargs)
            if kwargs["end"] == "2026-11-01":
                dates, closes, splits = ["2026-10-30"], [42], [0]
            else:
                dates, closes, splits = (
                    ["2026-10-30", "2026-11-03", "2026-11-04"],
                    [42, 84, 85],
                    [0, later_split, 0],
                )
            return pd.DataFrame(
                {"Close": closes, "Stock Splits": splits},
                index=pd.to_datetime(dates).tz_localize("America/New_York"),
            )

        def get_history_metadata(self):
            return {"symbol": "DOCN", "currency": "USD", "exchangeTimezoneName": "America/New_York"}

    monkeypatch.setattr(prices.yf, "Ticker", lambda _: Ticker())
    record = prices.get_price_observation("DOCN", "2026-10-31")
    assert (record["status"] == "available") is available, record
    assert len(calls) == 2 and calls[1]["end"] == "2026-11-05"
    if available:
        assert record["close"] == "42" and record["session_date"] == "2026-10-30"
        assert all(
            row["timestamp"].startswith("2026-10-30") for row in record["raw_source"]["bars"]
        )
        receipt = record["raw_source"]["adjustment_verification"]
        assert receipt["status"] == "passed" and "source_payload_sha256" in receipt
        assert "splits" not in receipt and "bars" not in receipt
        assert prices.validate_price_observation(record, "DOCN", "2026-10-31") == record
    else:
        assert "close" not in record and "raw_source" not in record
        assert "2026-11-03" not in str(record) and "ratio" not in str(record)


def test_historical_verification_beyond_bound_is_unavailable(monkeypatch):
    install(monkeypatch, dates=("2024-01-02",), closes=(42,))
    result = prices.get_price_observation("DOCN", "2024-01-02")
    assert result["status"] == "unavailable"
    assert "400" in result["reason"]


@pytest.mark.parametrize("missing", [None, float("nan"), "", "  ", pd.NA])
def test_missing_completed_close_falls_back_with_dated_reason(monkeypatch, missing):
    install(monkeypatch, now="2026-11-04T22:00:00+00:00", closes=(84, missing))
    record = prices.get_price_observation("DOCN", "2026-11-04")
    assert record["status"] == "available", record
    assert record["close"] == "84" and record["session_date"] == "2026-11-03"
    fallback = record["price_fallback"]
    assert fallback["latest_completed_session_date"] == "2026-11-04"
    assert fallback["selected_session_date"] == "2026-11-03"
    assert fallback["missing_completed_session_dates"] == ["2026-11-04"]
    assert "no close" in fallback["reason"]
    assert record["raw_source"]["bars"][-1]["close"] is None
    assert prices.validate_price_observation(record, "DOCN", "2026-11-04") == record


def test_multiple_missing_completed_closes_and_retained_splits(monkeypatch):
    install(monkeypatch, now="2026-11-04T22:00:00+00:00",
            dates=("2026-11-02", "2026-11-03", "2026-11-04"),
            closes=(84, None, float("nan")), splits=(0, 2, 0))
    record = prices.get_price_observation("DOCN", "2026-11-04")
    assert record["status"] == "available", record
    assert record["session_date"] == "2026-11-02"
    assert record["price_fallback"]["missing_completed_session_dates"] == [
        "2026-11-03", "2026-11-04"]
    assert record["splits"] == [{"session_date": "2026-11-03", "ratio": "2"}]
    for mutate in ("projection", "source"):
        changed = deepcopy(record)
        if mutate == "projection":
            changed["price_fallback"]["missing_completed_session_dates"] = []
        else:
            changed["raw_source"]["bars"][-1]["close"] = "85"
        with pytest.raises(ValueError):
            prices.validate_price_observation(changed, "DOCN", "2026-11-04")


def test_partial_or_cutoff_excluded_missing_close_does_not_trigger_fallback(monkeypatch):
    install(monkeypatch, closes=(84, float("nan")))
    record = prices.get_price_observation("DOCN", "2026-11-04")
    assert record["status"] == "available", record
    assert record["session_date"] == "2026-11-03"
    assert "price_fallback" not in record
    with prices.completed_price_scope({"market_observation_cutoff": "2026-11-04T20:00:00+00:00"}):
        install(monkeypatch, now="2026-11-04T22:00:00+00:00", closes=(84, None))
        record = prices.get_price_observation("DOCN", "2026-11-04")
    assert record["session_date"] == "2026-11-03"
    assert "price_fallback" not in record


@pytest.mark.parametrize("value", [0, -1, float("inf"), -float("inf"), "broken", "nan", True])
def test_invalid_nonempty_latest_close_does_not_fall_back(monkeypatch, value):
    install(monkeypatch, now="2026-11-04T22:00:00+00:00", closes=("84", value))
    assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"


def test_missing_fallback_preserves_identity_currency_and_action_guards(monkeypatch):
    for metadata, splits in [
        ({"symbol": "MSFT"}, (0, 0)), ({"currency": None}, (0, 0)),
        ({}, (0, float("nan"))),
    ]:
        install(monkeypatch, now="2026-11-04T22:00:00+00:00", closes=(84, None),
                metadata=metadata, splits=splits)
        assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"


def test_missing_close_cannot_bypass_staleness_or_future_session(monkeypatch):
    install(monkeypatch, now="2026-11-04T22:00:00+00:00",
            dates=("2026-10-26", "2026-11-04"), closes=(84, None))
    assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"
    install(monkeypatch, now="2026-11-04T22:00:00+00:00",
            dates=("2026-11-03", "2026-11-05"), closes=(84, None))
    assert prices.get_price_observation("DOCN", "2026-11-04")["status"] == "unavailable"
