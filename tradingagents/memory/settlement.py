"""Settling past decisions: once a decision's holding window has traded, score
it against its benchmark and record a reflection on it in the memory log."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.market import get_closes
from tradingagents.memory.log import is_trading_entry

logger = logging.getLogger(__name__)


def resolve_benchmark(ticker: str, config: dict) -> str:
    """Pick the benchmark ticker for alpha calculation against ``ticker``.

    ``config["benchmark_ticker"]`` overrides everything when set; otherwise
    the suffix map matches the ticker's exchange suffix (e.g. ``.T`` for
    Tokyo). US-listed tickers without a dotted suffix fall through to the
    empty-suffix entry (SPY by default). Unrecognised suffixes, including
    US tickers with dots like ``BRK.B``, also take the empty-suffix entry.
    Returns are compared as percentages, each in its own currency.
    """

    explicit = config.get("benchmark_ticker")
    if explicit:
        # Same alias mapping as the analyzed ticker; an unmapped alias finds
        # no prices, and the decision would stay pending for good.
        return normalize_symbol(explicit)
    benchmark_map = config.get("benchmark_map", {})
    ticker_upper = normalize_symbol(ticker)
    for suffix, benchmark in benchmark_map.items():
        if suffix and ticker_upper.endswith(suffix.upper()):
            return benchmark
    return benchmark_map.get("", "SPY")


def _by_day(closes):
    """Closes keyed by the calendar day of their bar, missing closes dropped.

    Yahoo stamps a daily bar at midnight in its market's time zone (UTC for a
    coin, New York for SPY), so two series meet on their dates, not their
    instants. A missing or non-positive close is no price at all, not a bar to
    score on.
    """
    closes = closes[(closes > 0) & closes.map(math.isfinite)]
    if getattr(closes.index, "tz", None) is not None:
        closes = closes.tz_localize(None)
    return closes


def fetch_returns(
    ticker: str,
    trade_date: str,
    holding_days: int = 5,
    benchmark: str = "SPY",
) -> tuple[float | None, float | None, int | None, str | None]:
    """Fetch raw and alpha return for ticker over holding_days after trade_date.

    The position is entered at the first close after ``trade_date``: a run dated
    ``trade_date`` reads news published after that day's close (#1518).

    ``benchmark`` is the index used as the alpha baseline (resolved by the
    caller via ``resolve_benchmark``). Returns ``(raw_return, alpha_return,
    holding_days, resolution_date)`` — where ``resolution_date`` is the date
    of the last price bar used, i.e. when the outcome became known (#1251) —
    or ``(None, None, None, None)`` when the full holding window has not traded
    yet (#1169). A failure to get or read the prices is raised, for the caller
    to report.
    """
    outcome = fetch_outcome(ticker, trade_date, holding_days, benchmark)
    if outcome is None:
        return None, None, None, None
    return (outcome["raw_return"], outcome["alpha_return"], holding_days,
            outcome["resolution_date"])


def fetch_outcome(
    ticker: str, trade_date: str, holding_days: int = 5, benchmark: str = "SPY",
    *, published_at: str | None = None, prices_before: str | None = None,
) -> dict | None:
    """Return a reconstructable daily-close outcome, or None while pending.

    The caller supplies the publication/as-of session cutoff. Daily bars do
    not establish executable timestamps. Benchmark prices retain their actual
    sessions when calendars differ, rather than inheriting stock dates.
    """
    if type(holding_days) is not int or holding_days < 1:
        raise ValueError("holding_days must be a positive integer")
    start = datetime.strptime(trade_date, "%Y-%m-%d")
    publication = datetime.fromisoformat(published_at) if published_at else None
    if publication is not None and publication.utcoffset() is None:
        raise ValueError("published_at must have a timezone")
    # Request enough history for either side of UTC midnight. The instrument's
    # own bar timezone below determines the actual publication-session cutoff.
    request_start = start
    if publication is not None:
        request_start = max(start, datetime.combine(publication.date(), datetime.min.time()) - timedelta(days=1))
    # holding_days counts trading days after the entry session, so ask for the
    # calendar span they occupy (about 7 for every 5) plus a week for holidays.
    end = request_start + timedelta(days=round((holding_days + 1) * 7 / 5) + 9)
    end_str = end.strftime("%Y-%m-%d")

    # Closes for the instrument the analysis priced (XAUUSD -> GC=F, #984),
    # from the first session after the decision date.
    stock_prices = get_closes(ticker, request_start.strftime("%Y-%m-%d"), end_str)
    publication_timezone = None
    if publication is not None:
        publication_timezone = getattr(stock_prices.index, "tz", None)
        if stock_prices.empty:
            return None
        if publication_timezone is None:
            raise ValueError("Instrument timezone unavailable for publication-session cutoff")
        publication_day = publication.astimezone(publication_timezone).date()
        start = max(start, datetime.combine(publication_day, datetime.min.time()))
    stock = _by_day(stock_prices)
    stock = stock[stock.index > start]
    if prices_before is not None:
        before = datetime.strptime(prices_before, "%Y-%m-%d")
        stock_timezone = getattr(stock_prices.index, "tz", None)
        if stock_timezone is not None:
            exchange_today = datetime.now(stock_timezone).date()
            before = min(before, datetime.combine(exchange_today, datetime.min.time()))
        stock = stock[stock.index < before]
    # From a week earlier, so the benchmark has a close on or before entry.
    bench_start = (start - timedelta(days=7)).strftime("%Y-%m-%d")
    benchmark_prices = get_closes(benchmark, bench_start, end_str)
    bench = _by_day(benchmark_prices)
    if prices_before is not None:
        benchmark_before = datetime.strptime(prices_before, "%Y-%m-%d")
        benchmark_timezone = getattr(benchmark_prices.index, "tz", None)
        if benchmark_timezone is not None:
            benchmark_today = datetime.now(benchmark_timezone).date()
            benchmark_before = min(benchmark_before, datetime.combine(benchmark_today, datetime.min.time()))
        bench = bench[bench.index < benchmark_before]

    # Require the full holding window to have traded. A rerun before it has
    # leaves the entry pending to retry next run, rather than settling on a
    # premature partial return (#1169).
    if len(stock) <= holding_days:
        return None
    entry, exit_ = stock.index[0], stock.index[holding_days]
    # The window is the stock's own sessions; the benchmark is valued at its
    # last close by each end, so both returns span the same dates even when
    # the calendars differ (a coin trades at weekends, an index does not).
    # It must have traded through the exit, or its close there may yet move.
    if bench.empty or bench.index[0] > entry or bench.index[-1] < exit_:
        return None

    raw = float((stock.iloc[holding_days] - stock.iloc[0]) / stock.iloc[0])
    bench_entry, bench_exit = bench.asof(entry), bench.asof(exit_)
    bench_ret = float((bench_exit - bench_entry) / bench_entry)
    alpha = raw - bench_ret
    # Every close used is known by the exit: the point-in-time cutoff for
    # injecting the lesson (#1251).
    resolution_date = exit_.strftime("%Y-%m-%d")
    return {
        "raw_return": raw, "alpha_return": alpha, "benchmark_return": bench_ret,
        "holding_days": holding_days, "resolution_date": resolution_date,
        "ticker": normalize_symbol(ticker), "benchmark": normalize_symbol(benchmark),
        "cutoff_date": start.strftime("%Y-%m-%d"),
        "published_at": published_at,
        "prices_before": prices_before,
        "publication_session_timezone": str(publication_timezone) if publication_timezone else None,
        "entry": {"date": entry.strftime("%Y-%m-%d"), "price": float(stock.iloc[0])},
        "exit": {"date": resolution_date, "price": float(stock.iloc[holding_days])},
        "benchmark_entry": {
            "date": bench.loc[:entry].index[-1].strftime("%Y-%m-%d"),
            "price": float(bench_entry),
        },
        "benchmark_exit": {
            "date": bench.loc[:exit_].index[-1].strftime("%Y-%m-%d"),
            "price": float(bench_exit),
        },
        "price_source": "Yahoo Finance via yfinance",
        "price_adjustment": "auto_adjust=True (splits and dividends)",
        "bar_time_basis": "daily session date; not an execution timestamp",
        "entry_policy": "first valid close strictly after cutoff_date",
        "benchmark_policy": "last valid close on or before each instrument endpoint",
    }


@dataclass
class Settlement:
    """What a settlement pass did: the decisions it settled and those it could not."""

    endpoint_settled: list[tuple[str, str]] = field(default_factory=list)  # (decision_id, endpoint)
    settled: list[tuple[str, str]] = field(default_factory=list)  # (ticker, date)
    failed: list[tuple[str, str, str]] = field(default_factory=list)  # (ticker, date, reason)


def settle_pending(
    ticker: str, memory_log, reflector, config: dict, wait: bool = True
) -> Settlement:
    """Settle ``ticker``'s pending decisions whose holding window has traded.

    One pass at a time per log (``memory_log.settling()``), so runs sharing a log
    never pay for the same reflection twice. Each outcome is written as soon as
    its reflection is done, so an interrupted pass keeps what it finished.
    Entries whose window has not traded yet are skipped; an entry whose prices
    or reflection could not be had stays pending and is reported as failed.
    With ``wait=False`` a pass already running elsewhere is left to do the work.
    """
    result = Settlement()
    if config.get("results_dir"):
        from tradingagents.memory.publication_outcomes import settle_publications
        endpoints = settle_publications(config, ticker, wait=wait)
        result.endpoint_settled.extend(endpoints["settled"])
        result.failed.extend((ticker, decision_id, reason) for decision_id, reason in endpoints["failed"])
    with memory_log.settling(wait=wait) as held:
        if not held:
            return result
        pending = [
            e
            for e in memory_log.get_pending_entries()
            if e["ticker"] == ticker and is_trading_entry(e)
        ]
        if not pending:
            return result
        benchmark = resolve_benchmark(ticker, config)
        for entry in pending:
            try:
                raw, alpha, days, resolution_date, used_benchmark = _returns_for_entry(
                    config, ticker,
                    entry["date"],
                    config.get("holding_period_days", 5),
                    benchmark=benchmark,
                )
            except Exception as exc:
                logger.warning(
                    "Prices for settling %s on %s were unavailable: %s", ticker, entry["date"], exc
                )
                result.failed.append((ticker, entry["date"], f"prices unavailable: {exc}"))
                continue
            if raw is None:
                continue  # the holding window has not traded yet: try again next run
            try:
                reflection = reflector.reflect_on_final_decision(
                    final_decision=entry.get("decision", ""),
                    raw_return=raw,
                    alpha_return=alpha,
                    benchmark_name=used_benchmark,
                    holding_days=days,
                )
            except Exception as exc:
                # Reflection calls a provider: a transient failure leaves the entry
                # pending for the next pass rather than stopping the analysis.
                logger.warning("Reflection failed for %s on %s: %s", ticker, entry["date"], exc)
                result.failed.append((ticker, entry["date"], f"reflection failed: {exc}"))
                continue
            if memory_log.update_with_outcome(
                ticker, entry["date"], raw, alpha, days, reflection, resolution_date=resolution_date
            ):
                result.settled.append((ticker, entry["date"]))
    return result


def _returns_for_entry(config, ticker, trade_date, holding_days, benchmark):
    """New publications use their declared window; old memory remains readable."""
    if config.get("results_dir"):
        from tradingagents.memory.publication import list_records
        from tradingagents.memory.publication_outcomes import load_outcomes
        primary = next((r for r in list_records(config, ticker)
                        if r["requested_as_of"] == trade_date and r["eligibility"]["primary"]), None)
        if primary:
            endpoint = load_outcomes(config, primary)["endpoints"].get(f"{holding_days}_sessions")
            if endpoint is not None:
                if endpoint["status"] != "resolved":
                    return None, None, None, None, primary["benchmark"]
                outcome = endpoint["outcome"]
            else:
                from tradingagents.dataflows.date_window import get_current_date
                outcome = fetch_outcome(ticker, trade_date, holding_days, primary["benchmark"],
                    published_at=primary["published_at"] if primary["evaluation_mode"] == "prospective" else None,
                    prices_before=get_current_date())
                if outcome is None:
                    return None, None, None, None, primary["benchmark"]
            return outcome["raw_return"], outcome["alpha_return"], holding_days, outcome["resolution_date"], primary["benchmark"]
    return (*fetch_returns(ticker, trade_date, holding_days, benchmark=benchmark), benchmark)


def settle_all_pending(memory_log, reflector, config: dict, wait: bool = True) -> Settlement:
    """Settle every ticker's pending decisions whose holding window has traded (#1445).

    A run settles its own ticker; a ticker no longer analysed would otherwise
    keep its decisions pending, and their lessons out of later runs.
    """
    result = Settlement()
    tickers = [e["ticker"] for e in memory_log.get_pending_entries() if is_trading_entry(e)]
    if config.get("results_dir"):
        from tradingagents.memory.publication import list_records
        tickers.extend(r["ticker"] for r in list_records(config))
    for ticker in dict.fromkeys(tickers):
        done = settle_pending(ticker, memory_log, reflector, config, wait=wait)
        result.endpoint_settled.extend(done.endpoint_settled)
        result.settled.extend(done.settled)
        result.failed.extend(done.failed)
    return result
