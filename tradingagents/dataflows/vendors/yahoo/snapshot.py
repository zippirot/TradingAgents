"""Deterministic market-data verification snapshot.

The market analyst is an LLM that can confabulate exact numbers — citing a
Bollinger band or a "historically validated bounce" that the underlying data
doesn't support (#830). This module computes a ground-truth snapshot (latest
OHLCV row on or before the analysis date, common indicators, recent closes)
the analyst is told to treat as the source of truth for any exact numeric
claim. Deterministic, no LLM involved.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv, market_provenance_lines

# A fixed, common indicator set so the snapshot is the same shape every run.
DEFAULT_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_10_ema", "close_50_sma", "close_200_sma",
    "rsi", "boll", "boll_ub", "boll_lb",
    "macd", "macds", "macdh", "atr",
)


def _verified_rows(symbol: str, as_of_date: str) -> pd.DataFrame:
    """OHLCV on or before as_of_date, date-sorted. Raises NoMarketDataError if nothing usable.

    ``load_ohlcv`` already normalizes the Date column and filters out
    look-ahead rows, but we re-apply the cutoff defensively — this is a
    verification path, so it must not trust its input to be pre-filtered.
    """
    # As reported: this snapshot is quoted by the agents as exact prices, so a
    # gap-filled cell would put the previous session's number under this date.
    data = load_ohlcv(symbol, as_of_date, fill_gaps=False)
    if data is None or data.empty:
        raise NoMarketDataError(symbol, normalize_symbol(symbol), "no price rows")

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    cutoff = pd.to_datetime(as_of_date)
    df = df[df["Date"] <= cutoff].sort_values("Date")
    if df.empty:
        raise NoMarketDataError(symbol, normalize_symbol(symbol), f"no price rows on or before {as_of_date}")
    if "completed_session_dates" in data.attrs:
        df.attrs["completed_session_dates"] = [
            day for day in data.attrs["completed_session_dates"] if pd.Timestamp(day) <= cutoff
        ]
    return df


def _fmt(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        if value and abs(value) < 1:
            return f"{value:.4g}"
        return f"{value:.2f}"
    return str(value)


def _prior_close_band_lines(df: pd.DataFrame) -> list[str]:
    """Summarize closes in the last 252 completed sessions in 5%-of-latest bands."""
    session_dates = df.attrs.get("completed_session_dates")
    history = (
        df[df["Date"].dt.strftime("%Y-%m-%d").isin(session_dates)]
        if session_dates is not None else df.tail(252)
    )
    session_count = len(session_dates) if session_dates is not None else len(history)
    missing_count = session_count - len(history)
    if history.empty:
        return [
            "", "### Prior closes by price band", "",
            "No available closes in the completed-session window; price bands unavailable.",
        ]
    latest = Decimal(str(history["Close"].iloc[-1]))
    width = latest * Decimal("0.05")
    lowest = Decimal(str(history["Close"].min()))
    band_count = max(1, int(((latest - lowest) / width).to_integral_value(rounding=ROUND_CEILING)))
    bands: list[list[tuple[pd.Timestamp, Decimal]]] = [[] for _ in range(band_count)]
    for _, row in history.iterrows():
        close = Decimal(str(row["Close"]))
        if close > latest:
            continue
        distance = (latest - close) / width
        index = max(0, int(distance.to_integral_value(rounding=ROUND_CEILING)) - 1)
        bands[index].append((row["Date"], close))

    # Retain distinct bounds even when a 5% band is smaller than one tenth.
    bound_decimals = max(1, -width.adjusted())

    def label(value: Decimal) -> str:
        quantum = Decimal(1).scaleb(-bound_decimals)
        return str(value.quantize(quantum, rounding=ROUND_HALF_UP))

    lines = [
        "", "### Prior closes by price band", "",
        f"Last {session_count} available completed sessions (up to 252); "
        "bands are 5% of the latest completed close. Exact bounds determine membership; "
        f"displayed bounds are rounded to {bound_decimals} decimal {'place' if bound_decimals == 1 else 'places'}.",
        *([f"{missing_count} completed session{'s' if missing_count != 1 else ''} "
           f"ha{'ve' if missing_count != 1 else 's'} no available close. "
           "Counts include observed closes only; empty bands are uncertain."]
          if missing_count else []),
        "| Price band | Closes | Most recent date | Lowest close | Highest close |",
        "|---|---:|---|---:|---:|",
    ]
    for index, closes in enumerate(bands):
        upper = latest - width * index
        lower = upper - width
        band = f"{label(lower)}–{label(upper)}"
        if closes:
            lines.append(
                f"| {band} | {len(closes)} | {_fmt(max(day for day, _ in closes))} | "
                f"{_fmt(float(min(close for _, close in closes)))} | "
                f"{_fmt(float(max(close for _, close in closes)))} |"
            )
        else:
            empty = (
                "no observed closes; missing close coverage" if missing_count
                else "no closes in the last 252 sessions"
            )
            lines.append(f"| {band} | 0 | {empty} | — | — |")
    return lines


def build_verified_market_snapshot(
    symbol: str,
    as_of_date: str,
    look_back_days: int = 30,
    indicators: Iterable[str] | None = None,
) -> str:
    """Render a ground-truth snapshot: latest OHLCV row, indicators, recent closes."""
    # `df` keeps the original capitalized OHLCV columns (Open/High/Low/Close/
    # Volume); stockstats `wrap()` lowercases columns and adds indicator
    # columns, so read raw prices from `df` and indicators from `stock_df`.
    df = _verified_rows(symbol, as_of_date)
    stock_df = wrap(df.copy())

    selected = tuple(indicators or DEFAULT_SNAPSHOT_INDICATORS)
    indicator_values: dict[str, str] = {}
    for name in selected:
        try:
            stock_df[name]  # triggers stockstats calculation
            indicator_values[name] = _fmt(stock_df.iloc[-1][name])
        except Exception as exc:  # noqa: BLE001 — one bad indicator shouldn't sink the snapshot
            indicator_values[name] = f"N/A ({type(exc).__name__})"

    latest = df.iloc[-1]
    latest_date = _fmt(latest["Date"])
    window = max(1, min(int(look_back_days), 30))
    recent = df.tail(window)

    lines = [
        f"## Verified market data snapshot for {symbol.upper()}",
        "",
        f"- Requested analysis date: {as_of_date}",
        f"- Latest trading row used: {latest_date}",
        "- Rows after the requested analysis date are excluded before verification.",
        *market_provenance_lines(df),
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for field in ("Open", "High", "Low", "Close", "Volume"):
        lines.append(f"| {field} | {_fmt(latest.get(field))} |")

    lines += ["", "### Verified technical indicators (latest row)", "",
              "| Indicator | Value |", "|---|---:|"]
    for name, value in indicator_values.items():
        lines.append(f"| {name} | {value} |")

    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "",
              "| Date | Close |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")

    lines += _prior_close_band_lines(df)

    lines += [
        "",
        "Use this snapshot as the source of truth for exact OHLCV, price-level, "
        "and indicator-value claims. If another tool output conflicts with it, "
        "flag the discrepancy rather than inventing a reconciled number. Do not "
        "claim historical validation, support/resistance bounces, or exact "
        "percentage moves unless directly supported by tool output with concrete "
        "dates and prices.",
    ]
    return "\n".join(lines)
