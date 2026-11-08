"""What every Yahoo request shares: its retry, and how a failure or an empty answer is reported."""

import logging
import time
from io import StringIO

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.operational_capture import record_operation

logger = logging.getLogger(__name__)

YAHOO_HOST = "https://query2.finance.yahoo.com"


def recorded_history(symbol, *, source_factory=None, include_metadata=True, **request):
    """Replay raw Yahoo bars/metadata; callers still run all current validation."""
    from tradingagents.source_replay import current_session, external_input

    def fetch():
        source = (source_factory or yf.Ticker)(symbol)
        history = source.history(**request)
        method = getattr(source, "get_history_metadata", None)
        metadata = method() if method and include_metadata else {}
        return history, metadata

    if current_session() is None:
        return fetch()

    def acquire():
        from tradingagents.dataflows.vendors.yahoo.price_observation import _now, _price_precision

        history, metadata = fetch()
        if history is None:
            return {"csv": None, "metadata": metadata, "retrieved_at": _now().isoformat()}
        retained_metadata = {key: metadata.get(key) for key in (
            "symbol", "currency", "exchangeTimezoneName", "currentTradingPeriod")}
        precision = _price_precision(metadata.get("priceHint"))
        if precision is not None:
            retained_metadata["priceHint"] = precision
        return {**_frame_payload(history), "metadata": retained_metadata, "retrieved_at": _now().isoformat()}

    raw = external_input("yahoo_history", {"symbol": symbol, "request": request,
                                           "include_metadata": include_metadata}, acquire)
    metadata = {**raw["metadata"], "_trace_retrieved_at": raw["retrieved_at"]}
    if raw["csv"] is None:
        return None, metadata
    return _frame_from_payload(raw), metadata


def _frame_payload(frame):
    return {"csv": frame.to_csv(index=True, index_label="__trace_index"),
            "datetime_index": isinstance(frame.index, pd.DatetimeIndex),
            "index_timezone": str(frame.index.tz) if isinstance(frame.index, pd.DatetimeIndex)
            and frame.index.tz is not None else None,
            "index_name": frame.index.name,
            "column_dtypes": [str(dtype) for dtype in frame.dtypes]}


def _frame_from_payload(raw):
    frame = pd.read_csv(StringIO(raw["csv"]), index_col="__trace_index", float_precision="round_trip")
    for column, dtype in zip(frame.columns, raw["column_dtypes"], strict=True):
        frame[column] = frame[column].astype(dtype)
    if raw["datetime_index"]:
        frame.index = pd.to_datetime(frame.index, utc=bool(raw["index_timezone"]))
        if raw["index_timezone"]:
            frame.index = frame.index.tz_convert(raw["index_timezone"])
    frame.index.name = raw["index_name"]
    return frame


def recorded_estimate(symbol, method, source_factory):
    """Freeze Yahoo's five raw estimate inputs, not their deterministic projections."""
    from tradingagents.source_replay import current_session, external_input

    if current_session() is None:
        return getattr(source_factory(symbol), method)()

    def acquire():
        value = getattr(source_factory(symbol), method)()
        return {"frame": _frame_payload(value)} if isinstance(value, pd.DataFrame) else {"value": value}

    raw = external_input("yahoo_estimate", {"symbol": symbol, "method": method}, acquire)
    return _frame_from_payload(raw["frame"]) if "frame" in raw else raw["value"]


def raise_for_empty(symbol: str, canonical: str, what: str) -> None:
    """Report an empty Yahoo answer as an absence, or as an outage if it is one.

    An empty answer from a Yahoo that cannot be reached is not an answer about
    the symbol, so the host is probed before "this symbol has no {what}" is said.
    """
    if not vendor_reachable(YAHOO_HOST):
        raise VendorUnavailableError(f"Yahoo Finance is unreachable; no {what} was retrieved")
    raise NoMarketDataError(symbol, canonical, f"no {what}")


# yfinance answers some failed requests with an empty result, which would read as
# "no data" for a symbol nobody checked; raised, the failure is reported as one.
yf.config.debug.hide_exceptions = False


def _answered_empty(exc: Exception) -> bool:
    """Whether Yahoo answered that it has nothing: no such symbol (HTTP 404), or a
    price window with no prices in it.

    yfinance raises YFPricesMissingError for that answer and also for an answer
    that was an error (an error status, or Yahoo describing a failure), so only
    a chart with no prices, or Yahoo saying the data does not exist, counts.
    A missing time zone is not an answer: yfinance reports a failed lookup the same way.
    """
    if isinstance(exc, YFPricesMissingError):
        reason = exc.yahoo_reason
        return "status_code" not in (exc.debug_info or "") and (
            reason is None or reason.startswith("Data doesn't exist"))
    return getattr(getattr(exc, "response", None), "status_code", None) == 404


def yf_retry(func, max_retries=3, base_delay=2.0):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally, so this wrapper retries them. A rate limit that
    outlasts the retries, or any other exception, is raised as
    VendorUnavailableError: it failed in transit and says nothing about the
    symbol. Yahoo answering that it has nothing for the symbol returns None,
    an empty answer. ``func`` should build its own Ticker and make the request
    itself: a Ticker keeps a failed ``info`` fetch as done, so asking the same
    one again reads an empty profile.
    """
    for attempt in range(max_retries + 1):
        try:
            result = func()
            if attempt:
                record_operation('recovered_retry', scope='Yahoo Finance')
            return result
        except YFRateLimitError as exc:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise VendorUnavailableError(
                    f"Yahoo Finance rate limited after {max_retries} retries: {exc}"
                ) from exc
        except Exception as exc:
            if _answered_empty(exc):
                return None
            raise VendorUnavailableError(f"Yahoo Finance request failed: {type(exc).__name__}") from exc
