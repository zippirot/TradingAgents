"""The `batch` command: the existing analysis once per ticker, with the setup questions asked once."""

from __future__ import annotations

from datetime import date

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import PortfolioContext
from tradingagents.portfolio_review import latest_ratings


def plan_batch(book: PortfolioContext, tickers: list[str] | None, day: date, refresh: bool,
               config: dict | None = None) -> tuple[list[str], list[tuple[str, str]]]:
    """Which tickers to run and which to skip, with the reason. Refuses a malformed ticker before any run."""
    from cli.prompts import parse_ticker
    from tradingagents.memory.publication import scan_records

    names = list(dict.fromkeys(parse_ticker(name) for name in (tickers or book.review_tickers())))
    if not names:
        raise ValueError("no ticker to analyze: the portfolio file lists no positions and no watchlist")
    age = book.limits.rating_max_age_days if book.limits else 30
    ratings = latest_ratings(scan_records(config or DEFAULT_CONFIG)["records"], names, day, age)
    run, skipped = [], []
    for name in names:
        found = ratings[name.upper()]
        if not refresh and found["status"] == "rated" and not found["stale"]:
            skipped.append((name, f"rated {found['rating']} on {found['as_of']}, {found['age_days']} day(s) old"))
        else:
            run.append(name)
    return run, skipped


def run_batch(book: PortfolioContext, tickers: list[str] | None, date: str | None, refresh: bool,
              config: dict | None = None) -> dict:
    """Run each ticker that needs a rating; one failure is recorded and the rest still run."""
    import datetime as _datetime

    from cli.display import console
    from cli.prompts import detect_asset_type
    from cli.run import run_analysis
    from cli.selections import get_user_selections

    day = _datetime.date.fromisoformat(date) if date else _datetime.date.today()
    run, skipped = plan_batch(book, tickers, day, refresh, config)
    result = {"ran": [], "skipped": skipped, "failed": []}
    for name, reason in skipped:
        console.print(f"Skipping {name}: {reason}", markup=False)
    if not run:
        console.print("Nothing to run: every stock has a rating that is not stale. Use --refresh to run them anyway.",
                      markup=False)
        return result
    console.print(f"Will run {len(run)}: {', '.join(run)}. Each is a full paid analysis.", markup=False)
    flags = {"ticker": run[0], "date": str(day), "save": True, "show": False, "html": True}
    selections = get_user_selections(flags)
    for name in run:
        chosen = {**selections, "ticker": name, "asset_type": detect_asset_type(name).value}
        try:
            run_analysis(portfolio=book, flags={**flags, "ticker": name}, selections=chosen)
            result["ran"].append(name)
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # noqa: BLE001 - one stock failing must not stop the rest
            result["failed"].append((name, f"{type(exc).__name__}: {exc}".rstrip(": ")))
            console.print(f"{name} failed: {type(exc).__name__}", markup=False)
    return result
