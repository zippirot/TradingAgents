"""The `review` command: gather saved ratings, prices and sectors, then print and save the portfolio review."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import default_portfolio_path, load_portfolio
from tradingagents.portfolio_review import (
    amounts_review,
    direction_review,
    latest_ratings,
    render_review,
)


def _quote(ticker: str, as_of: str) -> dict:
    from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation

    try:
        return get_price_observation(ticker, as_of)
    except Exception as exc:  # noqa: BLE001 - one ticker's price must not stop the review
        return {"status": "unavailable", "reason": f"price fetch failed ({type(exc).__name__})"}


def _sector(ticker: str) -> str | None:
    from tradingagents.dataflows.vendors.yahoo.fundamentals import get_company_profile

    try:
        sector = get_company_profile(ticker).get("sector")
    except Exception:  # noqa: BLE001 - an unknown sector is reported, not fatal
        return None
    return sector if isinstance(sector, str) and sector.strip() else None


def run_review(portfolio_path: str | None = None, as_of: str | None = None, config: dict | None = None) -> Path:
    """Print the review and save it under the local results folder; returns the saved file."""
    from cli.display import console
    from tradingagents.memory.publication import scan_records

    config = config or DEFAULT_CONFIG
    path = portfolio_path or default_portfolio_path()
    if not path:
        raise ValueError("no portfolio file: pass --portfolio or create the file named by portfolio_path")
    book = load_portfolio(path)
    day = date.fromisoformat(as_of) if as_of else date.today()
    tickers = book.review_tickers()
    if not tickers:
        raise ValueError("the portfolio file lists no positions and no watchlist")
    scanned = scan_records(config)
    age = book.limits.rating_max_age_days if book.limits else 30
    ratings = latest_ratings(scanned["records"], tickers, day, age)
    quotes = {ticker: _quote(ticker, str(day)) for ticker in tickers}
    # A sector on the position wins; the vendor is asked only where the file is silent.
    sectors = {ticker: None if (book.position_in(ticker) and book.position_in(ticker).sector) else _sector(ticker)
               for ticker in tickers}
    direction = direction_review(book, ratings, quotes, sectors)
    amounts = amounts_review(direction, book, quotes)
    now = datetime.now()
    text = render_review(direction, amounts, fingerprint=book.fingerprint(), generated=now.strftime("%Y-%m-%d %H:%M"),
                         currency=book.currency or "USD", damaged=len(scanned["skipped"]))
    folder = Path(config["results_dir"]) / "portfolio_reviews"
    folder.mkdir(parents=True, exist_ok=True)
    saved = folder / f"{now.strftime('%Y-%m-%d-%H%M%S')}.md"
    saved.write_text(text, encoding="utf-8")
    console.print(text, markup=False, highlight=False)
    console.print(f"Saved: {saved}", markup=False)
    return saved
