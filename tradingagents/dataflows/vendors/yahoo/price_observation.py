"""Dated completed-session Yahoo closes, retained independently of model prose.

A content hash detects mutation, not publisher authenticity. Only this provider's
retrieval path should introduce these records into canonical application state.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from zoneinfo import ZoneInfo

import yfinance as yf

from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import yf_retry

ADJUSTMENT = "Yahoo Close with auto_adjust=False: historical split-adjusted, not dividend-adjusted"


def _now():
    return datetime.now(UTC)


def _number(value, *, positive=False):
    if isinstance(value, bool):
        raise ValueError("Boolean price/action is invalid")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Malformed price/action") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(
            "Price/action must be finite and positive (zero allowed only for no split)"
        )
    rendered = format(result, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _timestamp(value):
    if isinstance(value, bool):
        raise ValueError("Invalid session timestamp")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must carry a timezone")
    return parsed


@contextmanager
def completed_price_scope(state=None):
    """Bind the retained run cutoff across market tools and canonical retrieval."""
    from tradingagents.dataflows.config import get_config, run_config

    state = state or {}
    cutoff = state.get("market_observation_cutoff")
    if cutoff is None:
        cutoff = (state.get("analysis_clock") or {}).get("cutoff_utc")
    if cutoff is None:
        yield
        return
    with run_config({**get_config(), "_market_observation_cutoff": cutoff}):
        yield


def session_is_complete(session, retrieved_at, exchange_timezone, regular_end=None, cutoff=None):
    """Finality at acquisition, capped by the run's resolved observation instant.

    A stored pre-close bar never becomes final through elapsed wall-clock time.
    No exchange closing hour is guessed; same-day promotion needs provider end
    metadata. Prior dates retain the existing completed-session interpretation.
    """
    retrieved = _timestamp(retrieved_at)
    effective = min(retrieved, _timestamp(cutoff)) if cutoff else retrieved
    if not exchange_timezone:
        # With no instrument zone, require the date to have ended in even the
        # latest possible local timezone. Never call an unknown today's bar final.
        return session < (effective - timedelta(hours=12)).date()
    zone = ZoneInfo(exchange_timezone)
    today = effective.astimezone(zone).date()
    if session < today:
        return True
    if session != today or regular_end is None:
        return False
    end = _timestamp(regular_end)
    return end.astimezone(zone).date() == session and end <= effective


def _hash(raw):
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _verify_adjustment_basis(raw):
    """Verify provider adjustment basis without publishing future action values."""
    cutoff = date.fromisoformat(raw["as_of"])
    zone = ZoneInfo(raw["metadata"]["exchangeTimezoneName"])
    today = _timestamp(raw["retrieved_at"]).astimezone(zone).date()
    if cutoff >= today:
        return None
    if (today - cutoff).days > 400:
        raise ValueError(
            "Historical adjustment basis unavailable beyond 400-day verification bound"
        )
    start = max(cutoff - timedelta(days=7), today - timedelta(days=400))

    def fetch():
        source = yf.Ticker(raw["ticker"])
        history = source.history(
            start=str(start),
            end=str(today + timedelta(days=1)),
            interval="1d",
            auto_adjust=False,
            actions=True,
        )
        return history, source.get_history_metadata()

    response = yf_retry(fetch)
    if response is None:
        raise ValueError("Historical adjustment basis verification unavailable")
    history, metadata = response
    if any(
        metadata.get(key) != raw["metadata"][key]
        for key in ("symbol", "currency", "exchangeTimezoneName")
    ):
        raise ValueError("Historical adjustment basis metadata mismatch")
    actions = []
    sessions = set()
    for index, row in history.iterrows():
        session = _timestamp(index.isoformat()).astimezone(zone).date()
        if session in sessions or not start <= session <= today:
            raise ValueError("Historical adjustment verification window invalid")
        sessions.add(session)
        ratio = _number(row["Stock Splits"])
        actions.append({"session_date": str(session), "stock_splits": ratio})
        if session > cutoff and Decimal(ratio) != 0:
            raise ValueError(
                "Historical quote adjustment basis is not compatible with the analysis cutoff"
            )
    if not sessions or min(sessions) > cutoff or (today - max(sessions)).days > 7:
        raise ValueError("Historical adjustment verification coverage unavailable")
    return {
        "status": "passed",
        "purpose": "provider adjustment verification, not as-of research evidence",
        "window_start": str(start),
        "window_end": str(today),
        "observed_at": raw["retrieved_at"],
        "source_payload_sha256": _hash(actions),
        "quote_payload_sha256": _hash(raw["bars"]),
        "returned_sessions": len(sessions),
    }


def _validate_adjustment_receipt(raw, today):
    cutoff = date.fromisoformat(raw["as_of"])
    receipt = raw.get("adjustment_verification")
    if cutoff == today:
        if receipt is not None:
            raise ValueError("Unexpected historical adjustment verification")
        return
    start = max(cutoff - timedelta(days=7), today - timedelta(days=400))
    if (today - cutoff).days > 400 or not isinstance(receipt, dict):
        raise ValueError("Historical adjustment verification unavailable within 400-day bound")
    expected = {
        "status": "passed",
        "purpose": "provider adjustment verification, not as-of research evidence",
        "window_start": str(start),
        "window_end": str(today),
        "observed_at": raw["retrieved_at"],
        "quote_payload_sha256": _hash(raw["bars"]),
    }
    if (
        any(receipt.get(key) != value for key, value in expected.items())
        or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("source_payload_sha256", "")))
        or type(receipt.get("returned_sessions")) is not int
        or not 1 <= receipt["returned_sessions"] <= 401
        or set(receipt) != {*expected, "source_payload_sha256", "returned_sessions"}
    ):
        raise ValueError("Historical adjustment verification receipt mismatch")


def _project(raw):
    ticker = raw["ticker"]
    if ticker != normalize_symbol(ticker):
        raise ValueError("Noncanonical ticker")
    as_of = date.fromisoformat(raw["as_of"])
    retrieved = _timestamp(raw["retrieved_at"])
    metadata = raw["metadata"]
    zone = ZoneInfo(metadata["exchangeTimezoneName"])
    today = retrieved.astimezone(zone).date()
    if as_of > today:
        raise ValueError("Future analysis date")
    _validate_adjustment_receipt(raw, today)
    currency = metadata["currency"]
    if not isinstance(currency, str) or not re.fullmatch("[A-Z]{3}", currency):
        raise ValueError("Missing or unsupported currency metadata")
    if metadata["symbol"] != ticker:
        raise ValueError("Yahoo symbol does not match requested issuer")
    requested = min(
        as_of - timedelta(days=14),
        date.fromisoformat(raw["capital_snapshot_date"]) if raw["capital_snapshot_date"] else as_of,
    )
    fetch_start = (
        min(requested, date.fromisoformat(raw["capital_snapshot_date"]) - timedelta(days=7))
        if raw["capital_snapshot_date"]
        else requested
    )
    start = max(fetch_start, as_of - timedelta(days=400))
    if raw["history_start"] != str(start) or raw["history_end_exclusive"] != str(
        as_of + timedelta(days=1)
    ):
        raise ValueError("History request window mismatch")
    if raw["capital_snapshot_date"] and date.fromisoformat(raw["capital_snapshot_date"]) > as_of:
        raise ValueError("Capital snapshot exceeds analysis date")
    if raw["auto_adjust"] is not False or raw["actions"] is not True or raw["interval"] != "1d":
        raise ValueError("Unsupported source adjustment/action request")
    bars = raw["bars"]
    if not isinstance(bars, list) or not 1 <= len(bars) <= 401:
        raise ValueError("Missing or oversized daily history")
    sessions, completed = set(), []
    splits = []
    for bar in bars:
        timestamp = _timestamp(bar["timestamp"])
        session = timestamp.astimezone(zone).date()
        if session in sessions:
            raise ValueError("Duplicate daily price session")
        sessions.add(session)
        if not start <= session <= as_of:
            raise ValueError("Price row outside requested window")
        close = _number(bar["close"], positive=True)
        split = _number(bar["stock_splits"])
        if session > today:
            raise ValueError("Future price session")
        is_complete = session_is_complete(
            session, retrieved, str(zone), metadata["regular_end"], raw.get("observation_cutoff")
        )
        if is_complete:
            completed.append((session, close))
        if Decimal(split) != 0:
            splits.append({"session_date": str(session), "ratio": split})
    if not completed:
        raise ValueError("No completed session available")
    session, close = max(completed)
    if (as_of - session).days > 7:
        raise ValueError("Completed price is more than seven calendar days stale")
    url = "https://query2.finance.yahoo.com/v8/finance/chart/" + quote(ticker, safe="")
    capital = (
        date.fromisoformat(raw["capital_snapshot_date"])
        if raw["capital_snapshot_date"]
        else requested
    )
    return {
        "status": "available",
        "ticker": ticker,
        "as_of": str(as_of),
        "close": close,
        "currency": currency,
        "session_date": str(session),
        "session_status": "completed",
        "exchange_timezone": str(zone),
        "retrieved_at": raw["retrieved_at"],
        "metadata_observed_at": raw["retrieved_at"],
        "adjustment_basis": ADJUSTMENT,
        "capital_snapshot_date": raw["capital_snapshot_date"],
        "coverage_note": "Returned Yahoo daily bars/actions; no exchange-calendar completeness guarantee",
        "requested_coverage_start": str(requested),
        "coverage_start": str(min(sessions)),
        "coverage_end": str(max(sessions)),
        "coverage_complete": start <= requested and min(sessions) <= capital,
        "splits": sorted(splits, key=lambda s: s["session_date"]),
        "source_id": "yahoo-price-" + _hash(raw),
        "url": url,
        "content_hash": _hash(raw),
        "raw_source": raw,
    }


def validate_price_observation(record, ticker, as_of):
    """Revalidate retained source payload and every projection; never fetch."""
    try:
        projected = _project(record["raw_source"])
        if (
            record != projected
            or projected["ticker"] != normalize_symbol(ticker)
            or projected["as_of"] != str(date.fromisoformat(str(as_of)))
        ):
            raise ValueError("Price observation identity or retained payload mismatch")
        return projected
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid canonical price observation: " + str(exc)) from exc


def get_price_observation(ticker, as_of, capital_snapshot_date=None):
    """Fetch a bounded daily window and preserve observed price/action metadata."""
    canonical = normalize_symbol(ticker)
    try:
        cutoff = date.fromisoformat(str(as_of))
        capital = date.fromisoformat(str(capital_snapshot_date)) if capital_snapshot_date else None
        if capital and capital > cutoff:
            raise ValueError("Capital snapshot exceeds analysis date")
        requested = min(cutoff - timedelta(days=14), capital or cutoff)
        fetch_start = min(requested, capital - timedelta(days=7)) if capital else requested
        start = max(fetch_start, cutoff - timedelta(days=400))

        def fetch():
            source = yf.Ticker(canonical)
            history = source.history(
                start=str(start),
                end=str(cutoff + timedelta(days=1)),
                interval="1d",
                auto_adjust=False,
                actions=True,
            )
            return history, source.get_history_metadata()

        response = yf_retry(fetch)
        if response is None:
            raise ValueError("Yahoo price history unavailable")
        history, metadata = response
        end = metadata.get("currentTradingPeriod", {}).get("regular", {}).get("end")
        raw = {
            "ticker": canonical,
            "as_of": str(cutoff),
            "capital_snapshot_date": str(capital) if capital else None,
            "retrieved_at": _now().isoformat(),
            "history_start": str(start),
            "history_end_exclusive": str(cutoff + timedelta(days=1)),
            "auto_adjust": False,
            "actions": True,
            "interval": "1d",
            "metadata": {
                "symbol": metadata.get("symbol"),
                "currency": metadata.get("currency"),
                "exchangeTimezoneName": metadata.get("exchangeTimezoneName"),
                "regular_end": _timestamp(end).isoformat() if end is not None else None,
            },
            "bars": [
                {
                    "timestamp": index.isoformat(),
                    "close": str(row["Close"]),
                    "stock_splits": str(row["Stock Splits"]),
                }
                for index, row in history.iterrows()
            ],
        }
        from tradingagents.dataflows.config import get_config
        observation_cutoff = get_config().get("_market_observation_cutoff")
        if observation_cutoff:
            raw["observation_cutoff"] = _timestamp(observation_cutoff).isoformat()
        raw["adjustment_verification"] = _verify_adjustment_basis(raw)
        return _project(raw)
    except Exception as exc:
        # Provider exceptions can embed URLs or secrets; expose bounded types only.
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return {
            "status": "unavailable",
            "ticker": canonical,
            "as_of": str(as_of),
            "reason": reason[:240],
        }
