"""Retained one-query Yahoo historical closes and split-action coverage.

Yahoo Close with auto_adjust=False is historically split adjusted. A past
analysis cutoff can use it only when the returned action window confirms no
split between that cutoff and retrieval. The raw result is retained so the
projection can be replayed without a provider call.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from zoneinfo import ZoneInfo

import yfinance as yf

from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import yf_retry
from tradingagents.dataflows.vendors.yahoo.price_observation import (
    _timestamp,
    session_is_complete,
)

MAX_QUARTERS = 24
MAX_BARS = 2000
MAX_HISTORY_DAYS = 1830


def _now():
    return datetime.now(UTC)


def _hash(raw):
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _number(value, *, positive=False):
    if isinstance(value, bool):
        raise ValueError("Boolean price or split ratio")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Malformed price or split ratio") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError("Nonfinite or nonpositive price or split ratio")
    rendered = format(result, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _quarters(quarter_ends, as_of):
    if not isinstance(quarter_ends, (list, tuple)) or not 1 <= len(quarter_ends) <= MAX_QUARTERS:
        raise ValueError("Historical quarter list must contain 1 to 24 dates")
    dates = tuple(date.fromisoformat(str(item)) for item in quarter_ends)
    if len(set(dates)) != len(dates) or any(day > as_of for day in dates):
        raise ValueError("Duplicate or future historical quarter end")
    if min(dates) < as_of - timedelta(days=MAX_HISTORY_DAYS):
        raise ValueError("Historical quarter exceeds five-year request bound")
    return tuple(sorted(dates))


def _project(raw):
    ticker = raw["ticker"]
    if ticker != normalize_symbol(ticker):
        raise ValueError("Noncanonical history ticker")
    as_of = date.fromisoformat(raw["as_of"])
    quarters = _quarters(raw["quarter_ends"], as_of)
    retrieved = _timestamp(raw["retrieved_at"])
    if retrieved.utcoffset() != timedelta(0):
        raise ValueError("Retrieval timestamp must be UTC")
    cutoff = _timestamp(raw["observation_cutoff"]) if raw["observation_cutoff"] else None
    if cutoff and (cutoff.utcoffset() != timedelta(0) or cutoff > retrieved):
        raise ValueError("Invalid UTC observation cutoff")
    metadata = raw["metadata"]
    zone = ZoneInfo(metadata["exchangeTimezoneName"])
    retrieval_day = retrieved.astimezone(zone).date()
    if as_of > retrieval_day or (cutoff and as_of > cutoff.astimezone(zone).date()):
        raise ValueError("Analysis date exceeds acquisition or observation cutoff")
    if metadata["symbol"] != ticker or not re.fullmatch(r"[A-Z]{3}", metadata["currency"]):
        raise ValueError("Yahoo instrument or currency identity mismatch")
    regular_end = metadata["regular_end"]
    if regular_end is not None:
        _timestamp(regular_end)
    start = min(quarters) - timedelta(days=7)
    end = retrieved.date() + timedelta(days=1)
    if (raw["history_start"], raw["history_end_exclusive"]) != (str(start), str(end)):
        raise ValueError("Historical provider request window mismatch")
    if (raw["interval"], raw["auto_adjust"], raw["actions"]) != ("1d", False, True):
        raise ValueError("Unsupported Yahoo adjustment or action request")
    bars = raw["bars"]
    if not isinstance(bars, list) or not 1 <= len(bars) <= MAX_BARS:
        raise ValueError("Missing or oversized historical bars")
    by_session = {}
    actions = []
    for bar in bars:
        stamp = _timestamp(bar["timestamp"])
        session = stamp.astimezone(zone).date()
        if session in by_session or not start <= session < end or session > retrieval_day:
            raise ValueError("Duplicate or out-of-window historical bar")
        close = _number(bar["close"], positive=True)
        ratio = _number(bar["stock_splits"])
        complete = session_is_complete(
            session, retrieved, str(zone), regular_end, raw["observation_cutoff"]
        )
        by_session[session] = (close, complete)
        if Decimal(ratio) != 0:
            if session > as_of:
                raise ValueError("Post-cutoff split makes historical price basis incompatible")
            if not complete:
                raise ValueError("Split on incomplete session has uncertain price basis")
            actions.append((session, ratio))
    sessions = sorted(by_session)
    if sessions[0] > min(quarters) or (retrieval_day - sessions[-1]).days > 7:
        raise ValueError("Insufficient provider-returned action coverage")
    if any((right - left).days > 7 for left, right in zip(sessions, sessions[1:], strict=False)):
        raise ValueError("Gap in provider-returned price/action coverage")
    if not any(session <= as_of for session in sessions):
        raise ValueError("No price or action coverage at analysis cutoff")
    content_hash = _hash(raw)
    source_id = "yahoo-reference-" + content_hash
    url = "https://query2.finance.yahoo.com/v8/finance/chart/" + quote(ticker, safe="")
    prices = []
    for quarter in quarters:
        candidates = [session for session in sessions if session <= quarter and by_session[session][1]]
        if not candidates:
            continue
        session = candidates[-1]
        if (quarter - session).days > 7:
            continue
        prices.append({
            "ticker": ticker, "quarter_end": str(quarter), "session_date": str(session),
            "session_status": "completed", "close": by_session[session][0],
            "currency": metadata["currency"], "source_id": source_id,
            "content_hash": content_hash, "source_url": url,
            "adjustment_basis": "historical_split_adjusted", "split_basis_date": str(as_of),
        })
    if not prices:
        raise ValueError("No completed quarter-end price within seven days")
    split_history = {
        "ticker": ticker, "coverage_complete": True,
        "coverage_start": str(sessions[0]), "coverage_end": str(as_of),
        "split_basis_date": str(as_of), "source_id": source_id,
        "content_hash": content_hash,
        "splits": [
            {"session_date": str(session), "ratio": ratio, "source_id": source_id}
            for session, ratio in actions
        ],
    }
    return {
        "status": "available", "reason": None, "ticker": ticker, "as_of": str(as_of),
        "quarter_ends": [str(day) for day in quarters], "retrieved_at": raw["retrieved_at"],
        "observation_cutoff": raw["observation_cutoff"], "source_id": source_id,
        "content_hash": content_hash, "source_url": url,
        "coverage_note": "Provider-returned daily bars/actions with no gaps over seven days; no exchange-calendar completeness guarantee",
        "prices": prices, "split_history": split_history, "raw_source": raw,
    }


def replay_reference_history(record, ticker, as_of, quarter_ends):
    """Recheck raw payload and every retained projection without a provider call."""
    try:
        projected = _project(record["raw_source"])
        expected_quarters = [str(day) for day in _quarters(quarter_ends, date.fromisoformat(str(as_of)))]
        if (
            record != projected or projected["ticker"] != normalize_symbol(ticker)
            or projected["as_of"] != str(date.fromisoformat(str(as_of)))
            or projected["quarter_ends"] != expected_quarters
        ):
            raise ValueError("Historical observation identity or retained projection mismatch")
        return projected["prices"], projected["split_history"]
    except (KeyError, TypeError, ValueError, OverflowError, ArithmeticError) as exc:
        raise ValueError("Invalid retained reference history: " + str(exc)) from exc


def get_reference_history(ticker, as_of, quarter_ends, *, observation_cutoff=None):
    """Fetch one bounded history window and retain its replayable source payload."""
    try:
        canonical = normalize_symbol(ticker)
        analysis = date.fromisoformat(str(as_of))
        quarters = _quarters(quarter_ends, analysis)
        retrieved = _now()
        if retrieved.utcoffset() != timedelta(0):
            raise ValueError("Acquisition clock must be UTC")
        cutoff = _timestamp(observation_cutoff) if observation_cutoff else None
        if cutoff and cutoff > retrieved:
            raise ValueError("Observation cutoff exceeds acquisition time")
        start = min(quarters) - timedelta(days=7)
        end = retrieved.date() + timedelta(days=1)
        if (end - start).days > MAX_HISTORY_DAYS + 370:
            raise ValueError("Historical source request exceeds bounded window")

        def fetch():
            source = yf.Ticker(canonical)
            history = source.history(
                start=str(start), end=str(end), interval="1d",
                auto_adjust=False, actions=True,
            )
            return history, source.get_history_metadata()

        response = yf_retry(fetch)
        if response is None:
            raise ValueError("Yahoo reference history unavailable")
        history, metadata = response
        regular = metadata.get("currentTradingPeriod", {}).get("regular", {}).get("end")
        raw = {
            "ticker": canonical, "as_of": str(analysis),
            "quarter_ends": [str(day) for day in quarters],
            "retrieved_at": retrieved.isoformat(),
            "observation_cutoff": cutoff.isoformat() if cutoff else None,
            "history_start": str(start), "history_end_exclusive": str(end),
            "interval": "1d", "auto_adjust": False, "actions": True,
            "metadata": {
                "symbol": metadata.get("symbol"), "currency": metadata.get("currency"),
                "exchangeTimezoneName": metadata.get("exchangeTimezoneName"),
                "regular_end": _timestamp(regular).isoformat() if regular is not None else None,
            },
            "bars": [
                {"timestamp": index.isoformat(), "close": str(row["Close"]),
                 "stock_splits": str(row["Stock Splits"])}
                for index, row in history.iterrows()
            ],
        }
        return _project(raw)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return {"status": "unavailable", "ticker": str(ticker)[:24],
                "as_of": str(as_of)[:24], "reason": reason[:240]}
