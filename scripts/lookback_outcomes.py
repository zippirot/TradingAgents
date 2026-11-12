"""What the shares did after each look-back rating, against the market.

Reads the loop's look-back runs (results folders named logs-lb*), takes each run's rating and its
valuation against the close, and sets them beside the price change over the next 21 and 63 trading
sessions, less the change in SPY over the same sessions. Prices come from Yahoo daily closes (free).

Evidence, not proof: few ratings, overlapping windows, the same companies on every date, and the
look-back runs use the market and fundamentals analysts only.

    PYTHONPATH=$PWD python scripts/lookback_outcomes.py [--home ~/.tradingagents/loop] [--out FILE.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

HORIZONS = (21, 63)
_SIDE = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


def runs(home: Path, prefix: str = "logs-lb") -> list[dict]:
    """One row per look-back run that reached a rating."""
    rows, seen = [], set()
    for path in sorted(glob.glob(str(home / f"{prefix}*" / "*" / "TradingAgentsStrategy_logs" / "full_states_log_*.json"))):
        try:
            state = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        key = (state.get("company_of_interest"), state.get("trade_date"), state.get("run_id") or path)
        rating = state.get("final_rating")
        if key[:2] in seen or rating not in _SIDE:
            continue
        seen.add(key[:2])
        card = ((state.get("decision_context") or {}).get("scenario_decision") or {})
        structured = (((state.get("unvalidated_outputs") or {}).get("portfolio_manager") or {}).get("structured") or {})
        rows.append({"ticker": key[0], "date": key[1], "rating": rating, "stock_view": structured.get("stock_view"),
                     "valuation_reading": card.get("valuation_reading"),
                     "valuation_vs_close": _number(card.get("weighted_today_vs_close_percent")),
                     "return_gap_points": _number(card.get("return_gap_points"))})
    return rows


def _number(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def change(closes: list[float], sessions: int) -> float | None:
    """Percent change from the first close to the close ``sessions`` later; None when not yet traded."""
    return None if len(closes) <= sessions or closes[0] <= 0 else (closes[sessions] / closes[0] - 1) * 100


def closes_from(ticker: str, day: str) -> list[float]:
    import yfinance

    frame = yfinance.Ticker(ticker).history(start=day, auto_adjust=True)
    return [float(value) for value in frame["Close"].tolist()]


def outcomes(rows: list[dict], fetch=closes_from) -> list[dict]:
    market = {}
    for row in rows:
        own = fetch(row["ticker"], row["date"])
        if row["date"] not in market:
            market[row["date"]] = fetch("SPY", row["date"])
        for sessions in HORIZONS:
            stock, index = change(own, sessions), change(market[row["date"]], sessions)
            row[f"excess_{sessions}"] = None if stock is None or index is None else round(stock - index, 2)
    return rows


def rank_correlation(pairs: list[tuple[float, float]]) -> float | None:
    """Spearman's rank correlation; None with fewer than four pairs."""
    if len(pairs) < 4:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=values.__getitem__)
        result = [0.0] * len(values)
        for position, index in enumerate(order):
            result[index] = float(position)
        return result
    first, second = ranks([a for a, _ in pairs]), ranks([b for _, b in pairs])
    try:
        return round(statistics.correlation(first, second), 2)
    except statistics.StatisticsError:
        return None


def summary(rows: list[dict]) -> dict:
    result = {"ratings": len(rows), "by_rating": {}, "horizons": {}}
    for sessions in HORIZONS:
        key = f"excess_{sessions}"
        scored = [row for row in rows if row.get(key) is not None]
        by = {}
        for rating in _SIDE:
            values = [row[key] for row in scored if row["rating"] == rating]
            if values:
                by[rating] = {"count": len(values), "mean_excess": round(statistics.mean(values), 2),
                              "share_below_market": round(sum(1 for value in values if value < 0) / len(values), 2)}
        views = {}
        for view in ("Attractive", "Fair", "Unattractive"):
            values = [row[key] for row in scored if row.get("stock_view") == view]
            if values:
                views[view] = {"count": len(values), "mean_excess": round(statistics.mean(values), 2),
                               "share_below_market": round(sum(1 for value in values if value < 0) / len(values), 2)}
        directional = [row for row in scored if _SIDE[row["rating"]]]
        right = sum(1 for row in directional if (row[key] > 0) == (_SIDE[row["rating"]] > 0))
        result["horizons"][sessions] = {
            "scored": len(scored), "by_rating": by, "by_stock_view": views,
            "directional_right": f"{right} of {len(directional)}",
            "valuation_rank_correlation": rank_correlation(
                [(row["valuation_vs_close"], row[key]) for row in scored if row["valuation_vs_close"] is not None])}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", type=Path, default=Path.home() / ".tradingagents" / "loop")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--prefix", default="logs-lb", help="results folders to read, by name prefix")
    args = parser.parse_args()
    rows = outcomes(runs(args.home, args.prefix))
    report = {"rows": rows, "summary": summary(rows)}
    if args.out:
        args.out.write_text(json.dumps(report, indent=1))
    for row in rows:
        print(f"{row['date']} {row['ticker']:5} {row['rating']:11} view {row.get('stock_view')} valuation {row['valuation_vs_close']}  "
              + "  ".join(f"+{s}s {row[f'excess_{s}']}" for s in HORIZONS))
    print(json.dumps(report["summary"], indent=1))


if __name__ == "__main__":
    main()
