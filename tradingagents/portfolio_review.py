"""What to do with each stock in the book, from the latest saved rating. Plain arithmetic: no model, no network.

Level 1 is direction only. Level 2 turns it into units and amounts, is labelled a work in progress, and never
alters Level 1. Every figure is arithmetic on the caller's own file and is not an order.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from tradingagents.portfolio import AT_STANDARD_BAND, RATINGS, PortfolioContext, sizing

_NO_WEIGHTS = {"Buy": "Add", "Overweight": "Add", "Hold": "Hold", "Underweight": "Trim", "Sell": "Exit"}
_BUYING = ("Buy", "Add")


def latest_ratings(records: list[dict], tickers: list[str], today: date, max_age_days: int) -> dict[str, dict]:
    """The latest saved record for each ticker: its rating, its date and whether it is stale."""
    found = {}
    for ticker in tickers:
        symbol = ticker.strip().upper()
        own = [r for r in records if str(r.get("ticker", "")).upper() == symbol]
        if not own:
            found[symbol] = {"status": "none", "rating": None, "as_of": None, "age_days": None, "stale": False, "run_id": None}
            continue
        latest = max(own, key=lambda r: (r["requested_as_of"], r["sequence"]))
        rating = latest.get("canonical_rating")
        age = (today - date.fromisoformat(latest["requested_as_of"])).days
        rated = rating in RATINGS
        found[symbol] = {"status": "rated" if rated else "review", "rating": rating if rated else None,
                         "as_of": latest["requested_as_of"], "age_days": age, "stale": rated and age > max_age_days,
                         "run_id": latest.get("run_id")}
    return found


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _percent(value) -> str:
    return f"{Decimal(value) * 100:.1f}%"


def direction_review(book: PortfolioContext, ratings: dict, quotes: dict, sectors: dict) -> dict:
    """Level 1: Buy, Add, Hold, Trim, Exit, No action or Not reviewed for each held and watched ticker."""
    limits, inputs = book.limits, book.inputs()
    value = Decimal(str(book.portfolio_value)) if book.portfolio_value else None
    rows, warnings, sector_weights, holdings = [], [], {}, Decimal(0)
    for ticker in book.review_tickers():
        position = book.position_in(ticker)
        quantity = Decimal(str(position.quantity)) if position else Decimal(0)
        rating = ratings.get(ticker) or {"status": "none", "rating": None, "as_of": None, "stale": False}
        quote = quotes.get(ticker) or {}
        sector = (position.sector if position and position.sector else None) or sectors.get(ticker) or None
        row = {"ticker": ticker, "held": quantity != 0, "rating": rating["rating"], "rating_status": rating["status"],
               "stale": bool(rating.get("stale")), "as_of": rating.get("as_of"), "current_weight": None,
               "target_weight": None, "sector": sector, "direction": "Not reviewed", "note": "", "rank": None,
               "units_held": _text(quantity), "close": None}
        rows.append(row)
        try:
            close = Decimal(str(quote.get("close")))
        except (ArithmeticError, ValueError):
            close = None
        usable = quote.get("status", "available") == "available" and close is not None and close > 0
        mismatch = (usable and book.currency and quote.get("currency")
                    and book.currency.upper() != str(quote["currency"]).upper())
        if usable and not mismatch:
            row["close"] = _text(close)
            if value is not None:
                weight = quantity * close / value
                row["current_weight"] = _text(weight)
                if quantity > 0:
                    holdings += quantity * close
                    if sector:
                        sector_weights[sector] = sector_weights.get(sector, Decimal(0)) + weight
        if quantity < 0:
            row["note"] = "short position, not reviewed"
        elif rating["status"] == "review":
            row["note"] = "No rating (analysis stopped at REVIEW)"
        elif rating["status"] != "rated":
            row["note"] = "No rating; no saved analysis for this stock"
        elif not usable:
            row["note"] = "no usable price: " + str(quote.get("reason") or "no completed close is available")
        elif mismatch:
            row["note"] = f"the portfolio file is in {book.currency} and the price is in {quote['currency']}"
        else:
            sized = sizing(inputs, ticker, quote, rating=rating["rating"]) if value is not None else {}
            final = sized.get("final")
            target = Decimal(final["target_weight"]) if final else None
            notes = []
            if not row["held"]:
                row["direction"] = "Buy" if rating["rating"] in ("Buy", "Overweight") else "No action"
                if target is not None:
                    row["target_weight"] = _text(target)
            elif target is None:
                row["direction"] = _NO_WEIGHTS[rating["rating"]]
                notes.append("standard weight or rating weights were not supplied, so the direction follows the rating alone")
            else:
                row["target_weight"] = _text(target)
                gap = Decimal(row["current_weight"]) - target
                row["direction"] = ("Exit" if target == 0 else "Hold" if abs(gap) <= target * AT_STANDARD_BAND
                                    else "Add" if gap < 0 else "Trim")
            row["note"] = "; ".join(notes)
    # Limits read current weights only; nothing here allocates.
    cap = Decimal(str(limits.max_position_weight)) if limits and limits.max_position_weight else None
    sector_cap = Decimal(str(limits.max_sector_weight)) if limits and limits.max_sector_weight else None
    for row in rows:
        if row["direction"] == "Not reviewed":
            continue
        notes = [row["note"]] if row["note"] else []
        current = Decimal(row["current_weight"]) if row["current_weight"] is not None else None
        if cap is not None and current is not None and row["held"]:
            if current > cap and row["direction"] != "Exit":
                row["direction"] = "Trim"
                notes.append(f"above position limit of {_percent(cap)}")
            elif current >= cap * (1 - AT_STANDARD_BAND) and row["direction"] == "Add":
                row["direction"] = "Hold"
                notes.append(f"at position limit of {_percent(cap)}")
        if sector_cap is not None and row["direction"] in _BUYING:
            if not row["sector"]:
                notes.append("sector unknown, so not counted in the sector limit")
            elif sector_weights.get(row["sector"], Decimal(0)) >= sector_cap:
                row["direction"] = "Hold" if row["held"] else "No action"
                notes.append(f"sector at limit ({row['sector']} is {_percent(sector_weights[row['sector']])} "
                             f"against {_percent(sector_cap)})")
        row["note"] = "; ".join(notes)
    cash_weight = None
    if value is not None and book.cash is not None:
        cash_weight = Decimal(str(book.cash)) / value
        if limits and limits.min_cash_weight is not None and cash_weight < Decimal(str(limits.min_cash_weight)):
            warnings.append(f"Cash is {_percent(cash_weight)} of the portfolio, below your minimum of "
                            f"{_percent(limits.min_cash_weight)}.")
    if value is not None and holdings > value:
        warnings.append("Your holdings at these closes are worth more than the portfolio_value in your file; weights "
                        "use portfolio_value as you entered it, so they are overstated until it is updated.")
    stale = [row["ticker"] for row in rows if row["stale"]]
    if stale:
        age = limits.rating_max_age_days if limits else 30
        warnings.append(f"Ratings older than {age} days are still used but are stale: {', '.join(stale)}.")
    if sector_cap is not None:
        unknown = [row["ticker"] for row in rows if row["held"] and not row["sector"]]
        if unknown:
            warnings.append(f"Sector unknown, so left out of the sector limit: {', '.join(unknown)}.")

    def shortfall(row):
        if row["target_weight"] is None:
            return Decimal(0)
        return Decimal(row["target_weight"]) - Decimal(row["current_weight"] or 0)
    buying = sorted((row for row in rows if row["direction"] in _BUYING),
                    key=lambda row: (RATINGS.index(row["rating"]), -shortfall(row), row["ticker"]))
    for rank, row in enumerate(buying, 1):
        row["rank"] = rank
    return {"rows": rows, "sector_weights": {name: _text(weight) for name, weight in sorted(sector_weights.items())},
            "cash_weight": _text(cash_weight) if cash_weight is not None else None, "warnings": warnings}


def _cents(value: Decimal) -> str:
    return f"{value:.2f}"


def amounts_review(direction: dict, book: PortfolioContext, quotes: dict) -> dict:
    """Level 2 (work in progress): units and amounts. Sales fund purchases; limits and the cash floor hold."""
    missing = [name for name, present in (
        ("portfolio_value", book.portfolio_value), ("cash", book.cash is not None),
        ("a standard weight", book.default_standard_weight or any(p.standard_weight for p in book.positions)),
        ("rating_weights", book.rating_weights)) if not present]
    if missing:
        return {"status": "unavailable", "reason": "your portfolio file does not give " + ", ".join(missing),
                "rows": [], "cash_before": None, "cash_after": None, "cash_floor": None}
    limits = book.limits
    value, cash = Decimal(str(book.portfolio_value)), Decimal(str(book.cash))
    cap = Decimal(str(limits.max_position_weight)) if limits and limits.max_position_weight else None
    sector_cap = Decimal(str(limits.max_sector_weight)) if limits and limits.max_sector_weight else None
    floor = Decimal(str(limits.min_cash_weight)) * value if limits and limits.min_cash_weight else Decimal(0)
    sector_weights = {name: Decimal(weight) for name, weight in direction["sector_weights"].items()}
    rows, proceeds, done = [], Decimal(0), {}

    def out(row, units, note):
        close, held = Decimal(row["close"]), Decimal(row["units_held"])
        return {"ticker": row["ticker"], "direction": row["direction"], "units": _text(units),
                "amount": _cents(units * close), "resulting_weight": _text((held + units) * close / value), "note": note}

    for row in direction["rows"]:
        if row["direction"] not in ("Exit", "Trim"):
            continue
        close, held, current = Decimal(row["close"]), Decimal(row["units_held"]), Decimal(row["current_weight"])
        if row["direction"] == "Exit":
            units, note = held, "sells the whole position"
        else:
            goals = [(Decimal(row["target_weight"]), "target weight")] if row["target_weight"] is not None else []
            if cap is not None:
                goals.append((cap, "position limit"))
            if not goals:
                rows.append(out(row, Decimal(0), "no target weight or limit to trim to"))
                continue
            goal, name = min(goals, key=lambda item: item[0])
            units = min(held, ((current - goal) * value / close).to_integral_value(ROUND_CEILING))
            note = f"sells down to the {name} of {_percent(goal)}"
        proceeds += units * close
        if row["sector"] in sector_weights:
            sector_weights[row["sector"]] -= units * close / value
        done[row["ticker"]] = out(row, -units, note)
    funds = max(Decimal(0), cash - floor + proceeds)
    spent = Decimal(0)
    for row in sorted((r for r in direction["rows"] if r["rank"]), key=lambda r: r["rank"]):
        close, current = Decimal(row["close"]), Decimal(row["current_weight"])
        if row["target_weight"] is None:
            done[row["ticker"]] = out(row, Decimal(0), "no target weight, so no amount")
            continue
        goal, reasons = Decimal(row["target_weight"]), []
        if cap is not None and cap < goal:
            goal, reasons = cap, [f"capped by position limit of {_percent(cap)}"]
        wanted = max(Decimal(0), goal - current)
        if sector_cap is not None and row["sector"]:
            room = max(Decimal(0), sector_cap - sector_weights.get(row["sector"], Decimal(0)))
            if room < wanted:
                wanted, reasons = room, [*reasons, f"capped by sector limit of {_percent(sector_cap)}"]
        full = (wanted * value / close).to_integral_value(ROUND_FLOOR)
        units = min(full, ((funds - spent) / close).to_integral_value(ROUND_FLOOR))
        if units < full:
            reasons.append("not funded: no cash left above your cash floor" if units == 0 else
                           f"partly funded: cash above your cash floor covers {_text(units)} of {_text(full)} units")
        spent += units * close
        if row["sector"]:
            sector_weights[row["sector"]] = sector_weights.get(row["sector"], Decimal(0)) + units * close / value
        done[row["ticker"]] = out(row, units, "; ".join(reasons) or "funded")
    rows += [done[row["ticker"]] for row in direction["rows"] if row["ticker"] in done]
    return {"status": "available", "reason": None, "rows": rows, "cash_before": _cents(cash),
            "cash_after": _cents(cash + proceeds - spent), "cash_floor": _cents(floor)}


def _cell(value) -> str:
    return " ".join(str(value).split()).replace("|", r"\|")


def render_review(direction: dict, amounts: dict, *, fingerprint: str, generated: str, currency: str = "USD",
                  damaged: int = 0) -> str:
    """The review as markdown: warnings, Level 1 with no amounts, then Level 2 as its own section."""
    lines = [f"# Portfolio review, {generated}", "",
             f"Arithmetic on your portfolio file (fingerprint {fingerprint}) and the latest saved rating for each "
             "stock; not an order. No model was called."]
    warnings = list(direction["warnings"])
    if damaged:
        warnings.append(f"{damaged} saved record file(s) could not be read and were left out.")
    if warnings:
        lines += ["", "**Warnings**", *("- " + warning for warning in warnings)]
    lines += ["", "## Level 1: Direction", "", "Ticker | Held | Rating | Rated on | Direction | Note",
              "--- | --- | --- | --- | --- | ---"]
    for row in direction["rows"]:
        rating = row["rating"] or ("REVIEW" if row["rating_status"] == "review" else "none")
        when = (row["as_of"] or "") + (" (stale)" if row["stale"] else "")
        lines.append(" | ".join(_cell(cell) for cell in (
            row["ticker"], "yes" if row["held"] else "no", rating, when, row["direction"], row["note"])))
    lines += ["", "## Level 2: Recommended amounts (work in progress)", ""]
    if amounts["status"] != "available":
        lines.append(f"Not computed: {amounts['reason']}.")
    else:
        def money(text):
            return f"{Decimal(text):,.2f} {currency}"
        if amounts["rows"]:
            lines += ["Ticker | Direction | Units | Amount | Resulting weight | Note", "--- | --- | ---: | ---: | ---: | ---"]
            for row in amounts["rows"]:
                lines.append(" | ".join(_cell(cell) for cell in (
                    row["ticker"], row["direction"], f"{Decimal(row['units']):+,}", money(row["amount"]),
                    _percent(row["resulting_weight"]), row["note"])))
        else:
            lines.append("No purchase or sale follows from Level 1.")
        lines += ["", f"Cash before: {money(amounts['cash_before'])}. Cash after: {money(amounts['cash_after'])}. "
                      f"Cash floor: {money(amounts['cash_floor'])}.", "",
                  "Method: sales first (an Exit sells everything, a Trim sells down to the lower of the target weight "
                  "and your position limit).",
                  "Purchases then run in Level 1 rank order, up to the lower of the target weight and your position "
                  "limit, within your sector limit, in whole units rounded down.",
                  "Purchases use only cash above your cash floor plus sale proceeds. The ratings behind these amounts "
                  "have no settled track record yet."]
    unrated = [row["ticker"] for row in direction["rows"] if row["rating_status"] != "rated"]
    if unrated:
        lines += ["", f"No rating yet: {', '.join(unrated)}. To produce them (each is a full paid analysis): "
                      f"`tradingagents batch {','.join(unrated)}`"]
    return "\n".join(lines) + "\n"
