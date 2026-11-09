import logging
from datetime import datetime
from typing import Annotated

import numpy as np
import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta
from stockstats import wrap

from tradingagents.dataflows.errors import NoMarketDataError, VendorError, VendorUnavailableError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import raise_for_empty, recorded_history, yf_retry
from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv, market_provenance_lines

logger = logging.getLogger(__name__)


def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Resolve broker/forex symbols to Yahoo's convention (XAUUSD+ -> GC=F).
    canonical = normalize_symbol(symbol)

    # Stock, snapshot and indicator paths share the same retained daily series,
    # adjustment basis and completed-session filter.
    data = load_ohlcv(canonical, end_date, fill_gaps=False)
    data = data[data["Date"] >= pd.Timestamp(start_date)].copy()
    if data.empty:
        raise_for_empty(symbol, canonical, f"completed rows between {start_date} and {end_date}")
    data = data.set_index("Date")

    # Round numerical values to 2 decimal places for cleaner display
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    csv_string = data.to_csv()

    # Name the resolved symbol when it differs, so the reader sees which
    # instrument was priced.
    label = canonical if canonical == symbol.upper() else f"{canonical} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += "\n".join(market_provenance_lines(data)) + "\n\n"

    return header + csv_string


def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    as_of_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:

    best_ind_params = {
        # Moving Averages
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        # MACD Related
        "macd": (
            "MACD: Computes momentum via differences of EMAs. "
            "Usage: Look for crossovers and divergence as signals of trend changes. "
            "Tips: Confirm with other indicators in low-volatility or sideways markets."
        ),
        "macds": (
            "MACD Signal: An EMA smoothing of the MACD line. "
            "Usage: Use crossovers with the MACD line to trigger trades. "
            "Tips: Should be part of a broader strategy to avoid false positives."
        ),
        "macdh": (
            "MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(best_ind_params.keys())}"
        )

    end_date = as_of_date
    as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    before = as_of_dt - relativedelta(days=look_back_days)

    # Optimized: Get stock data once and calculate indicators for all dates
    provenance = {}
    try:
        indicator_data = _get_stock_stats_bulk(symbol, indicator, as_of_date, provenance=provenance)

        # Generate the date range we need
        current_dt = as_of_dt
        date_values = []

        while current_dt >= before:
            date_str = current_dt.strftime('%Y-%m-%d')

            # Look up the indicator value for this date
            if date_str in indicator_data:
                indicator_value = indicator_data[date_str]
            else:
                indicator_value = "N/A: No completed bar at the cutoff (open session, weekend, holiday or unavailable)"

            date_values.append((date_str, indicator_value))
            current_dt = current_dt - relativedelta(days=1)

        ind_string = ""
        for date_str, value in date_values:
            ind_string += f"{date_str}: {value}\n"

    except VendorError:
        raise  # Unknown/delisted symbol — let the router emit the sentinel
    except Exception as e:
        logger.warning("Bulk stockstats fetch failed, falling back per-day: %s", e)
        # Fallback to original implementation if bulk method fails
        ind_string = ""
        as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
        while as_of_dt >= before:
            indicator_value = get_stockstats_indicator(
                symbol, indicator, as_of_dt.strftime("%Y-%m-%d")
            )
            ind_string += f"{as_of_dt.strftime('%Y-%m-%d')}: {indicator_value}\n"
            as_of_dt = as_of_dt - relativedelta(days=1)

    provenance_frame = pd.DataFrame()
    provenance_frame.attrs["market_provenance"] = provenance
    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ("\n".join(market_provenance_lines(provenance_frame)) + "\n\n"
           if provenance else "")
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
    )

    return result_str


def _get_stock_stats_bulk(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    as_of_date: Annotated[str, "current date for reference"],
    *,
    provenance: dict | None = None,
) -> dict:
    """
    Optimized bulk calculation of stock stats indicators.
    Fetches data once and calculates indicator for all available dates.
    Returns dict mapping date strings to indicator values.
    """
    from stockstats import wrap

    data = load_ohlcv(symbol, as_of_date)
    if provenance is not None:
        provenance.update(data.attrs.get("market_provenance") or {})
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    df[indicator]  # This triggers stockstats to calculate the indicator

    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]

        if pd.isna(indicator_value):
            result_dict[date_str] = "N/A"
        else:
            result_dict[date_str] = str(indicator_value)

    return result_dict


def get_stockstats_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    as_of_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
) -> str:

    as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    as_of_date = as_of_dt.strftime("%Y-%m-%d")

    try:
        indicator_value = get_stock_stats(
            symbol,
            indicator,
            as_of_date,
        )
    except VendorError:
        raise  # Unknown/delisted symbol — let the router emit the sentinel
    except Exception as e:
        # An empty string renders as "2026-05-08: " in the indicator table, which
        # reads as no value that day rather than a read that failed. Raise so the
        # router can try the next vendor or report the series unavailable.
        raise NoMarketDataError(
            symbol, symbol, "Indicator calculation or retrieval unavailable"
        ) from e

    return str(indicator_value)


def get_closes(symbol: str, start_date: str, end_date: str) -> pd.Series:
    """Daily closes from ``start_date`` up to, not including, ``end_date``."""
    canonical = normalize_symbol(symbol)
    response = yf_retry(lambda: recorded_history(canonical, source_factory=yf.Ticker,
                                                include_metadata=False, start=start_date,
                                                end=end_date, auto_adjust=True))
    history = response[0] if response is not None else None
    return history["Close"] if history is not None and "Close" in history else pd.Series(dtype=float)


def _explicit_settlement_zero(exc, source, canonical, start, end):
    """Accept only Yahoo's structured, exact-window negative answer.

    A generic missing-prices exception is also used for service/malformed data.
    Do not inspect its display message or fetch extra metadata to repair it.
    """
    import re
    from zoneinfo import ZoneInfo

    from yfinance.exceptions import YFPricesMissingError

    if (not isinstance(exc, YFPricesMissingError) or getattr(exc, 'ticker', None) != canonical
            or 'status_code' in (getattr(exc, 'debug_info', None) or '')):
        return None
    reason = getattr(exc, 'yahoo_reason', None)
    if not isinstance(reason, str):
        return None
    match = re.fullmatch(r"Data doesn't exist for startDate = (-?\d+), endDate = (-?\d+)", reason)
    timezone = getattr(getattr(source, '_price_history', None), 'tz', None)
    if match is None or not isinstance(timezone, str):
        return None
    try:
        zone = ZoneInfo(timezone)
        expected = tuple(int(datetime.combine(day, datetime.min.time(), zone).timestamp()) for day in (start, end))
        if tuple(map(int, match.groups())) != expected:
            return None
        closes = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz=zone), name='Close')
    except (ValueError, KeyError, OverflowError, OSError):
        return None
    closes.attrs.update(settlement_verified_empty=True,
                        settlement_zero_source='yahoo_explicit_window_no_data',
                        settlement_request_start=str(start), settlement_request_end=str(end))
    return closes


def get_settlement_closes(symbol: str, start_date: str, end_date: str) -> pd.Series:
    """Read settlement closes without treating an unknown empty as zero coverage.

    The exclusive end date and adjustment basis match ``get_closes``. A
    successful, well-formed empty history is distinguished from a failed read;
    the caller must still establish its own eligibility and horizon conditions.
    """
    canonical = normalize_symbol(symbol)
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if start >= end:
        raise ValueError("settlement price window must have a positive length")

    source = None
    def factory(symbol):
        nonlocal source
        source = yf.Ticker(symbol)
        return source

    try:
        # yfinance 1.7.0 accepts raise_errors in PriceHistory.history. Without
        # it, transport and Yahoo errors can become a plausible empty frame.
        history, _ = recorded_history(canonical, source_factory=factory, include_metadata=False,
                                      start=start_date, end=end_date, auto_adjust=True, raise_errors=True)
    except Exception as exc:
        zero = _explicit_settlement_zero(exc, source, canonical, start, end)
        if zero is not None:
            return zero
        # The type alone never establishes zero coverage.
        raise VendorUnavailableError(
            f"Yahoo Finance settlement request failed: {type(exc).__name__}"
        ) from exc

    required = ("Open", "High", "Low", "Close", "Volume")
    if (
        not isinstance(history, pd.DataFrame)
        or not isinstance(history.index, pd.DatetimeIndex)
        or history.index.hasnans
        or not history.index.is_unique
        or not history.index.is_monotonic_increasing
        or any(column not in history for column in required)
        or any(not pd.api.types.is_numeric_dtype(history[column]) for column in required)
    ):
        raise VendorUnavailableError("Yahoo Finance settlement history has invalid shape")

    if history.empty:
        closes = history["Close"].copy()
        closes.attrs["settlement_verified_empty"] = True
        closes.attrs["settlement_zero_source"] = 'well_formed_empty_history'
        closes.attrs["settlement_request_start"] = start_date
        closes.attrs["settlement_request_end"] = end_date
        return closes

    if (
        any(day < start or day >= end for day in history.index.date)
        or not np.isfinite(history["Close"].to_numpy(dtype=float)).all()
        or not (history["Close"] > 0).all()
    ):
        raise VendorUnavailableError("Yahoo Finance settlement history has invalid prices or dates")
    closes = history["Close"].copy()
    closes.attrs.pop("settlement_verified_empty", None)
    closes.attrs["settlement_request_start"] = start_date
    closes.attrs["settlement_request_end"] = end_date
    return closes


def get_stock_stats(
    symbol: Annotated[str, "ticker symbol for the company"],
    indicator: Annotated[
        str, "quantitative indicators based off of the stock data for the company"
    ],
    as_of_date: Annotated[
        str, "curr date for retrieving stock price data, YYYY-mm-dd"
    ],
):
    data = load_ohlcv(symbol, as_of_date)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    as_of_str = pd.to_datetime(as_of_date).strftime("%Y-%m-%d")

    df[indicator]  # trigger stockstats to calculate the indicator
    matching_rows = df[df["Date"].str.startswith(as_of_str)]

    if not matching_rows.empty:
        indicator_value = matching_rows[indicator].values[0]
        return indicator_value
    else:
        return "N/A: No completed bar at the cutoff (open session, weekend, holiday or unavailable)"
