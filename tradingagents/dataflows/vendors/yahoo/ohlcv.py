import hashlib
import json
import logging
import os
from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component
from tradingagents.dataflows.vendors.yahoo.common import raise_for_empty, recorded_history, yf_retry
from tradingagents.dataflows.vendors.yahoo.price_observation import (
    ADJUSTMENT,
    _number,
    _timestamp,
    session_is_complete,
)

_SOURCE_COLUMN = "__market_source"

logger = logging.getLogger(__name__)

# A vendor's latest OHLCV row this many calendar days before the requested date
# is treated as stale. Generous enough to span long holiday weekends, tight
# enough to catch the year-old frames yfinance occasionally returns (#1021).
MAX_OHLCV_STALE_DAYS = 10

# How long a same-day cache that does not yet reach the requested day may be
# reused before it is refetched (#1150). Short enough that an intraday run picks
# up today's close soon after it publishes, long enough that a day with no bar
# at all (weekend, holiday) cannot trigger a download on every call.
OHLCV_CACHE_TTL_SECONDS = 900


def _retrieval_time():
    from tradingagents.dataflows.vendors.yahoo.price_observation import _now
    return _now()


def _source_metadata(source, downloaded, canonical, retrieved):
    method = getattr(source, "get_history_metadata", None)
    metadata = source if isinstance(source, Mapping) else method() if method is not None else {}
    metadata = metadata if isinstance(metadata, Mapping) else {}
    if metadata.get("_trace_retrieved_at"):
        retrieved = datetime.fromisoformat(metadata["_trace_retrieved_at"])
    zone = metadata.get("exchangeTimezoneName") or str(getattr(downloaded.index, "tz", "") or "")
    end = metadata.get("currentTradingPeriod", {}).get("regular", {}).get("end")
    return {
        "ticker": canonical,
        "retrieved_at": retrieved.isoformat(),
        "exchange_timezone": zone or None,
        "currency": metadata.get("currency"),
        "regular_end": _timestamp(end).isoformat() if end is not None else None,
        "adjustment_basis": ADJUSTMENT,
        "actions_requested": True,
        "source_id": "yahoo-ohlcv-" + hashlib.sha256(
            (canonical + retrieved.isoformat() + downloaded.to_csv()).encode()
        ).hexdigest(),
    }


def market_provenance_lines(data):
    source = data.attrs.get("market_provenance") or {}
    if not source:
        return ["- Session provenance unavailable."]
    historical = source.get("analysis_date", "9999") < source["retrieved_at"][:10]
    timing = (["- Retrospective retrieval; timestamps retained with the source, not as-of research facts."]
              if historical else [
                  f"- Retrieved at: {source['retrieved_at']}",
                  f"- Observation cutoff: {source.get('observation_cutoff') or source['retrieved_at']}",
              ])
    return [
        "- Session status: completed; unfinished daily rows excluded before calculation.",
        f"- Completed session: {source.get('session_date', 'unavailable')}",
        f"- Exchange timezone: {source.get('exchange_timezone') or 'unknown'}",
        f"- Currency: {source.get('currency') or 'unknown'}",
        *timing,
        *([f"- Price fallback: {source['price_fallback']['reason']}; "
           f"latest completed session {source['price_fallback']['latest_completed_session_date']}; "
           f"selected session {source['price_fallback']['selected_session_date']}."]
          if source.get("price_fallback") else []),
        f"- Adjustment basis: {source['adjustment_basis']}",
        f"- Source: {source['source_id']}",
        "- A completed close is a dated observation, not an executable quote.",
    ]


def _ensure_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize the date column to ``Date``.

    Some yfinance builds leave the index unnamed (so ``reset_index()`` yields
    ``index``) or use ``Datetime`` for intraday data. Rename the first
    date-like column so indicators don't silently drop when it isn't ``Date``.
    """
    if "Date" in data.columns:
        return data
    for candidate in ("index", "Datetime", "date"):
        if candidate in data.columns:
            return data.rename(columns={candidate: "Date"})
    return data


def _local_midnight(value) -> pd.Timestamp:
    """A single timestamp as its naive, midnight-normalized local date (or NaT)."""
    if pd.isna(value):
        return pd.NaT
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return pd.NaT
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)  # drop tz, keep the local wall-clock date
    return ts.normalize()


def _normalize_dates(dates) -> pd.Series:
    """Parse to naive, midnight-normalized dates so tz-aware or intraday
    timestamps compare correctly against the naive ``as_of_date`` cutoff (#1201).

    Normalized per element: 5 years of yfinance bars span daylight-saving
    changes (and cache CSVs round-trip the offsets as strings), so the series can
    carry mixed UTC offsets that ``pd.to_datetime`` cannot unify without
    ``utc=True`` — which would shift non-US (positive-offset) markets to the
    previous day. Keeping each bar's own local date avoids both.
    """
    return pd.to_datetime(pd.Series(dates).map(_local_midnight))


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse/normalize dates and
    coerce prices to numeric (NaN where invalid). Dropping incomplete rows and
    filling gaps is left to ``_fill_price_gaps`` so the caller can first inspect
    the latest in-range bar (#1201)."""
    data = _ensure_date_column(data)
    data["Date"] = _normalize_dates(data["Date"])
    data = data.dropna(subset=["Date"]).copy()

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    return data


def _validate_close_values(data, symbol, canonical):
    """Do not reinterpret corrupt nonempty closes as missing-price fallbacks."""
    raw = data["Close"]
    missing = raw.map(lambda value: pd.isna(value) or isinstance(value, str) and not value.strip())
    numeric = pd.to_numeric(raw, errors="coerce")
    invalid = ~missing & (
        numeric.isna() | numeric.le(0) | numeric.isin([float("inf"), float("-inf")])
        | raw.map(lambda value: isinstance(value, bool))
    )
    if invalid.any():
        raise NoMarketDataError(symbol, canonical, "invalid nonempty closing price in source data")


def _fill_price_gaps(data: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with no close and forward/back-fill remaining price gaps so
    indicators compute on a continuous series."""
    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    # copy() so a filtered (sliced) input is written to safely, not via a view.
    data = data.dropna(subset=["Close"]).copy()
    data[price_cols] = data[price_cols].ffill().bfill()
    return data


def _coerce_ohlcv_dates(data: pd.DataFrame) -> pd.Series:
    """Return parsed dates from an OHLCV frame, whether Date is a column or the index."""
    if "Date" in data.columns:
        return pd.to_datetime(data["Date"], errors="coerce").dropna()
    # yfinance keeps the dates in the index (a DatetimeIndex, sometimes unnamed).
    if isinstance(data.index, pd.DatetimeIndex):
        return pd.Series(pd.to_datetime(data.index, errors="coerce")).dropna()
    # Fallback: expose the index and look for any date-like column.
    df = data.reset_index()
    for col in ("Date", "Datetime", "date", "index"):
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce").dropna()
            if not parsed.empty:
                return parsed
    return pd.Series(dtype="datetime64[ns]")


def _assert_ohlcv_not_stale(
    data: pd.DataFrame,
    as_of_date: str,
    symbol: str,
    canonical: str | None = None,
    *,
    max_stale_days: int = MAX_OHLCV_STALE_DAYS,
) -> None:
    """Reject OHLCV whose latest row is far older than as_of_date.

    Raises NoMarketDataError (with a stale-specific detail) so the router treats
    it like any other "no usable data from this vendor" — try the next vendor,
    then emit one clear unavailable signal. Empty frames are left to the
    caller's existing no-data handling; this guards only the dangerous case of
    present-but-stale rows (a vendor returning a year-old frame that would
    otherwise feed wrong prices to the agent, #1021).
    """
    if data is None or data.empty:
        return
    requested = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(requested):
        return
    requested = requested.normalize()
    dates = _coerce_ohlcv_dates(data)
    if dates.empty:
        return
    latest = dates.max().normalize()
    stale_days = (requested - latest).days
    if stale_days > max_stale_days:
        raise NoMarketDataError(
            symbol,
            canonical,
            f"latest row is {latest.date()}, {stale_days} days before the "
            f"requested {requested.date()} (stale) — refusing to use it",
        )


def _cache_is_fresh(data_file, as_of_dt, now) -> bool:
    """Whether the symbol's cached download can serve this request.

    The file holds the download made on the day it was written, so it serves
    only that day. A current-day request also refetches once the file is older
    than the TTL: Yahoo publishes a partial daily candle during market hours,
    whose ``Close`` is not the closing price, and row inspection cannot tell it
    from a final one (#1150).
    """
    written = pd.Timestamp.fromtimestamp(os.path.getmtime(data_file))
    if written.date() != now.date():
        return False
    return as_of_dt.date() < now.date() or (now - written).total_seconds() <= OHLCV_CACHE_TTL_SECONDS


def _verify_historical_adjustment(data, metadata, as_of_dt, symbol, canonical):
    """Inspect the full retrieved action window before historical rows are hidden."""
    unavailable = "Historical adjustment basis verification unavailable"
    try:
        zone = ZoneInfo(metadata["exchange_timezone"])
        today = _timestamp(metadata["retrieved_at"]).astimezone(zone).date()
        cutoff = as_of_dt.date()
        if cutoff >= today:
            return
        if (today - cutoff).days > 400:
            raise NoMarketDataError(
                symbol, canonical,
                "Historical adjustment basis unavailable beyond 400-day verification bound",
            )
        if metadata.get("actions_requested") is not True or "Stock Splits" not in data:
            raise ValueError("missing verified split actions")
        start = max(cutoff - timedelta(days=7), today - timedelta(days=400))
        sessions = set()
        for _, row in _ensure_date_column(data).iterrows():
            session = _local_midnight(row["Date"])
            if pd.isna(session) or session.date() > today:
                raise ValueError("invalid action verification window")
            if session.date() < start:
                continue
            if session.date() in sessions:
                raise ValueError("duplicate action verification session")
            sessions.add(session.date())
            ratio = _number(row["Stock Splits"])
            if session.date() > cutoff and Decimal(ratio) != 0:
                raise NoMarketDataError(
                    symbol, canonical,
                    "Historical adjustment basis is not compatible with the analysis cutoff",
                )
        if not sessions or min(sessions) > cutoff or (today - max(sessions)).days > 7:
            raise ValueError("insufficient action verification coverage")
    except NoMarketDataError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, ZoneInfoNotFoundError) as exc:
        raise NoMarketDataError(symbol, canonical, unavailable) from exc


def load_ohlcv(symbol: str, as_of_date: str, fill_gaps: bool = True) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads 5 years of data up to today and caches per symbol. On
    subsequent calls the cache is reused. Rows after as_of_date are
    filtered out so backtests never see future prices.

    ``fill_gaps`` carries prices forward over gaps so indicators compute on a
    continuous series. Pass ``False`` to read the values as the vendor reported
    them, leaving a cell that was never reported empty.
    """
    # Resolve broker/forex symbols (XAUUSD+ -> GC=F) to Yahoo's convention,
    # then reject values that would escape the cache directory when
    # interpolated into the cache filename (e.g. ``../../tmp/x``).
    canonical = normalize_symbol(symbol)
    safe_symbol = safe_ticker_component(canonical)

    config = get_config()
    as_of_dt = pd.to_datetime(as_of_date).normalize()

    # One cache file per symbol, holding the latest 5y-to-today download.
    from tradingagents.source_replay import current_session, source_now

    now = pd.Timestamp(source_now().astimezone().replace(tzinfo=None)) if current_session() else pd.Timestamp.today()
    start_date = now - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    # End is exclusive. An exchange can already be on the next UTC date;
    # include that date independent of the host timezone or requested past date.
    # The retained cutoff and exchange metadata below still exclude partial rows.
    end_str = (_retrieval_time() + pd.Timedelta(days=2)).strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-YFin-data.csv",
    )

    # A cached file may be empty if a prior fetch failed (unknown symbol,
    # transient rate limit). Treat an empty/columnless cache as a miss and
    # re-fetch rather than serving the poisoned file forever.
    data = None
    source_metadata = None
    if os.path.exists(data_file):
        cached = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
        if (
            not cached.empty
            and "Close" in cached.columns
            and _SOURCE_COLUMN in cached.columns
            and _cache_is_fresh(data_file, as_of_dt, now)
        ):
            try:
                retained = json.loads(cached[_SOURCE_COLUMN].iloc[0])
                if retained["adjustment_basis"] == ADJUSTMENT and retained["ticker"] == canonical:
                    _timestamp(retained["retrieved_at"])
                    historical = as_of_dt.date() < _timestamp(retained["retrieved_at"]).date()
                    if not historical or (retained.get("actions_requested") is True
                                          and "Stock Splits" in cached):
                        source_metadata = retained
                        data = cached.drop(columns=[_SOURCE_COLUMN])
            except (KeyError, TypeError, ValueError):
                pass  # Legacy/malformed provenance uses the existing fetch path.

    if data is None:
        # yf.download catches every error, a rate limit included, and returns
        # an empty frame. Ticker.history raises the rate limit, so it is retried.
        def fetch():
            downloaded, metadata = recorded_history(
                canonical, source_factory=yf.Ticker, start=start_str, end=end_str, auto_adjust=False, actions=True,
            )
            if downloaded is None or downloaded.empty:
                return None
            return downloaded, _source_metadata(metadata, downloaded, canonical, _retrieval_time())

        response = yf_retry(fetch)
        downloaded, source_metadata = response if response is not None else (None, None)
        if downloaded is None:
            raise_for_empty(symbol, canonical, "price rows")
        downloaded = _ensure_date_column(downloaded.reset_index())
        # Only cache real data — never persist an empty frame.
        if downloaded.empty or "Close" not in downloaded.columns:
            raise_for_empty(symbol, canonical, "price rows")
        _validate_close_values(downloaded, symbol, canonical)
        cached = downloaded.assign(**{_SOURCE_COLUMN: json.dumps(source_metadata, sort_keys=True)})
        replace_file(data_file, lambda temp: cached.to_csv(temp, index=False, encoding="utf-8"))
        data = downloaded

    _validate_close_values(data, symbol, canonical)
    _verify_historical_adjustment(data, source_metadata, as_of_dt, symbol, canonical)
    # Actions are only for private basis verification, never model input.
    data = data.drop(columns=["Stock Splits", "Dividends", "Capital Gains"], errors="ignore")
    data = _clean_dataframe(data)

    # Filter to as_of_date to prevent look-ahead bias in backtesting.
    data = data[data["Date"] <= as_of_dt]
    requested_cutoff = config.get("_market_observation_cutoff")
    cutoff = min(_retrieval_time(), _timestamp(requested_cutoff)).isoformat() if requested_cutoff else _retrieval_time().isoformat()
    data = data[data["Date"].map(lambda value: session_is_complete(
        value.date(), source_metadata["retrieved_at"], source_metadata["exchange_timezone"],
        source_metadata["regular_end"], cutoff,
    ))].copy()
    if data.empty:
        raise NoMarketDataError(symbol, canonical, "no completed price rows at the observation cutoff")

    # Select actual completed sessions; never carry a prior close under an empty
    # latest session's date. Sorting also makes the retained explanation stable.
    data = data.sort_values("Date")
    # Keep the session window separate from close observations: callers that
    # summarize 252 sessions must not pull in an older close when one session
    # in that window has no reported close.
    completed_session_dates = [str(day.date()) for day in data["Date"].tail(252)]
    price_fallback = None

    # A closeless newest bar is an unsettled session, not a symbol without data.
    # _fill_price_gaps below drops it, here and mid-series alike, so the frame
    # ends at the last settled bar; only a range with no close anywhere is no
    # data (#1201, #1289).
    if not data.empty and pd.isna(data["Close"].iloc[-1]):
        settled = data["Close"].notna().to_numpy().nonzero()[0]
        if settled.size == 0:
            raise NoMarketDataError(
                symbol, canonical, "no bar in range has a closing price"
            )
        price_fallback = {
            "reason": "Latest completed session has no close; using last valid completed session",
            "latest_completed_session_date": str(data["Date"].iloc[-1].date()),
            "selected_session_date": str(data["Date"].iloc[settled[-1]].date()),
            "missing_completed_session_dates": [
                str(day.date()) for day in data["Date"].iloc[settled[-1] + 1:]
            ],
        }
        logger.warning(
            "%s: %d trailing bar(s) through %s have no closing price; using %s "
            "as the latest close.", canonical, len(data) - settled[-1] - 1,
            data["Date"].iloc[-1].date(), data["Date"].iloc[settled[-1]].date(),
        )

    # Indicators need a continuous series, so gaps are carried forward. A caller
    # that reports the numbers themselves asks for the frame as it was reported:
    # a filled cell is the previous session's price under this session's date.
    data = _fill_price_gaps(data) if fill_gaps else data.dropna(subset=["Close"]).copy()

    # Reject a stale frame (latest row far older than as_of_date) rather than
    # feeding year-old prices into indicators (#1021).
    _assert_ohlcv_not_stale(data, as_of_date, symbol, canonical)
    data.attrs["market_provenance"] = {
        **source_metadata, "observation_cutoff": cutoff, "analysis_date": str(as_of_dt.date()),
        "session_date": str(data["Date"].max().date()) if not data.empty else None,
        "session_status": "completed",
        **({"price_fallback": price_fallback} if price_fallback else {}),
    }
    data.attrs["completed_session_dates"] = completed_session_dates
    return data


