"""Where a priced case sits against the company's own valuation history.

Cases are stated on different obligation bases. Each is restated here as equity
value over its forecast revenue, the same numerator as the retained own-history
series, and placed in that series' range. Nothing here says what a multiple
should be.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from pydantic import ValidationError

from tradingagents.agents.valuation_reference import _ttm_at
from tradingagents.dataflows.financial_evidence import EvidencePackage

BANDS = {
    "below_low": "below the low",
    "low_to_median": "between the low and the median",
    "median_to_high": "between the median and the high",
    "above_high": "above the high",
}


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _times(value):
    return f"{value:.2f}×"


def _own_history(state):
    reference = state.get("valuation_reference")
    history = reference.get("own_history") if isinstance(reference, dict) else None
    if not isinstance(history, dict) or history.get("status") != "available":
        return None
    stats = history.get("statistics")
    values = {key: _decimal(stats.get(key)) for key in ("low", "median", "high")} if isinstance(stats, dict) else {}
    if any(values.get(key) is None or values[key] <= 0 for key in ("low", "median", "high")):
        return None
    return history, values, stats.get("count")


MIN_LIKE_QUARTERS = 3
_BORROWINGS = ("Total Borrowings", "Long-term Borrowings (including current)")
_BASIS_LABEL = {"equity": "equity value", "borrowings_only": "equity value plus borrowings less cash"}


def _instant(state, metric, day):
    """One reported USD balance for ``metric`` on ``day``; None when absent, not in USD, or reported with two values."""
    facts = (state.get("financial_evidence") or {}).get("facts") if isinstance(state.get("financial_evidence"), dict) else None
    values = {_decimal(f.get("value")) for f in facts or () if isinstance(f, dict) and f.get("metric") == metric
              and f.get("period_start") in (None, "None") and str(f.get("period_end")) == day
              and f.get("unit") == "USD" and f.get("value") not in (None, "None")}
    values.discard(None)
    return values.pop() if len(values) == 1 else None


def _today_multiple(state, basis):
    if basis == "equity":
        found = _own_history(state)
        return _decimal((found[0].get("current_position") or {}).get("multiple")) if found else None
    implied = state.get("price_implied_valuation")
    row = next((r for r in (implied or {}).get("rows") or () if isinstance(r, dict) and r.get("perimeter") == basis
                and r.get("status") == "available"), None) if isinstance(implied, dict) else None
    return _decimal((row.get("ratios") or {}).get("trailing_revenue")) if row else None


def like_for_like(row, state) -> dict:
    """The company's own history on the case's obligation basis and revenue construction.

    A case applies its multiple to revenue of the twelve months ending at its period end. The matching
    history is, at each past quarter end, that basis's value over revenue of the preceding twelve months.
    A quarter without one reported borrowings and one reported cash balance is left out, never estimated.
    """
    request, result = row.get("request") or {}, row.get("result") or {}
    basis, multiple = request.get("multiple_basis"), _decimal(result.get("multiple"))
    found = _own_history(state)
    if result.get("method") != "revenue_case" or multiple is None or multiple <= 0:
        return {"status": "unavailable", "reason": "The case states no multiple to place."}
    if basis not in _BASIS_LABEL:
        return {"status": "unavailable", "basis": basis,
                "reason": "Past balances for this obligation basis are not retained, so no same-basis history is stated."}
    if found is None:
        return {"status": "unavailable", "basis": basis, "reason": "Own valuation history is unavailable for this run."}
    points, excluded = [], []
    with localcontext() as ctx:
        ctx.prec = 60
        for quarter in found[0].get("rows") or ():
            if not isinstance(quarter, dict) or quarter.get("status") != "available":
                continue
            day = str(quarter.get("quarter_end"))
            equity, revenue = _decimal(quarter.get("equity_value")), _decimal(quarter.get("revenue"))
            if equity is None or revenue is None or revenue <= 0 or quarter.get("equity_value_unit") != "USD":
                excluded.append({"quarter_end": day, "reason": "equity value or trailing revenue unavailable"})
                continue
            net = Decimal(0)
            if basis == "borrowings_only":
                owed = next((value for value in (_instant(state, metric, day) for metric in _BORROWINGS) if value is not None), None)
                cash = _instant(state, "Cash and Equivalents", day)
                if owed is None or cash is None:
                    excluded.append({"quarter_end": day, "reason": "no single reported borrowings or cash balance"})
                    continue
                net = owed - cash
            points.append({"quarter_end": day, "multiple": str((equity + net) / revenue)})
    if len(points) < MIN_LIKE_QUARTERS:
        return {"status": "unavailable", "basis": basis, "excluded": excluded,
                "reason": f"Fewer than {MIN_LIKE_QUARTERS} past quarters can be stated on the case's basis."}
    values = sorted(Decimal(point["multiple"]) for point in points)
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    low, high = values[0], values[-1]
    band = ("below_low" if multiple < low else "low_to_median" if multiple <= median
            else "median_to_high" if multiple <= high else "above_high")
    today = _today_multiple(state, basis)
    left_out = ("; left out for lack of a reported balance: " + ", ".join(item["quarter_end"] for item in excluded)) if excluded else ""
    summary = (f"Case multiple {_times(multiple)} of the twelve months' revenue ending at its period end, on "
               f"{_BASIS_LABEL[basis]}: {BANDS[band]} of the company's own {len(points)}-quarter range on the same basis "
               f"(low {_times(low)}, median {_times(median)}, high {_times(high)})"
               + (f"; today's price implies {_times(today)}" if today is not None else "") + left_out
               + ". The history is retrospective, not a point-in-time backtest; the case's revenue is a forecast.")
    return {"status": "available", "basis": basis, "multiple": str(multiple), "band": band, "low": str(low),
            "median": str(median), "high": str(high), "quarters": points, "excluded": excluded,
            "today": None if today is None else str(today), "summary": summary}


def reference_position(row, state) -> dict:
    """Place one priced revenue case in the own-history range, or say why it cannot be placed.

    The same-basis history is used when it can be stated; otherwise the case is restated on equity value
    over forecast revenue against the retained equity series, with that mismatch said.
    """
    same = like_for_like(row, state)
    position = _equity_position(row, state)
    if same["status"] != "available":
        return {**position, "like_for_like": same}
    return {**position, "status": "available", "basis": "like_for_like", "band": same["band"],
            "summary": same["summary"], "like_for_like": same}


def _equity_position(row, state) -> dict:
    found = _own_history(state)
    if found is None:
        return {"status": "unavailable", "reason": "Own valuation history is unavailable for this run."}
    history, stats, count = found
    result, request = row.get("result") or {}, row.get("request") or {}
    target, shares = _decimal(result.get("target")), _decimal(result.get("shares_outstanding"))
    revenue = _decimal((request.get("forecast") or {}).get("value"))
    if result.get("method") != "revenue_case" or None in (target, shares, revenue) or min(target, shares, revenue) <= 0:
        return {"status": "unavailable", "reason": "The case has no per-share value to restate on an equity basis."}
    with localcontext() as ctx:
        ctx.prec = 60
        implied = target * shares / revenue
    band = ("below_low" if implied < stats["low"] else "low_to_median" if implied <= stats["median"]
            else "median_to_high" if implied <= stats["high"] else "above_high")
    current = _decimal((history.get("current_position") or {}).get("multiple"))
    summary = (f"Implied equity value / forecast revenue {_times(implied)}: {BANDS[band]} of the company's own "
               f"{count}-quarter equity value / trailing revenue range (low {_times(stats['low'])}, median "
               f"{_times(stats['median'])}, high {_times(stats['high'])})"
               + (f"; today's trailing multiple is {_times(current)}" if current is not None else "")
               + ". The history is retrospective, not a point-in-time backtest, and uses trailing revenue where the "
                 "case uses forecast revenue.")
    return {"status": "available", "basis": "equity_value / forecast_revenue", "implied_multiple": str(implied),
            "band": band, "history_low": str(stats["low"]), "history_median": str(stats["median"]),
            "history_high": str(stats["high"]), "history_quarters": count,
            "current_trailing_multiple": None if current is None else str(current), "summary": summary}


def _year_earlier(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def history_context(state) -> list[dict]:
    """Growth and gross margin each history quarter was valued at, where retained facts allow."""
    found = _own_history(state)
    if found is None:
        return []
    try:
        package = EvidencePackage.model_validate(state.get("financial_evidence"))
    except ValidationError:
        return []
    quarters = []
    for row in found[0].get("rows") or ():
        try:
            end, currency = date.fromisoformat(row["quarter_end"]), row["revenue_unit"]
        except (KeyError, TypeError, ValueError):
            continue
        multiple = _decimal(row.get("multiple"))
        if multiple is None:
            continue
        revenue, prior = _ttm_at(package, end, "Revenue", currency), _ttm_at(package, _year_earlier(end), "Revenue", currency)
        profit = _ttm_at(package, end, "Gross Profit", currency, positive=False)
        with localcontext() as ctx:
            ctx.prec = 60
            growth = (revenue.value / prior.value - 1) * 100 if revenue is not None and prior is not None else None
            margin = profit.value / revenue.value * 100 if revenue is not None and profit is not None else None
        quarters.append({"quarter_end": str(end), "multiple": str(multiple),
                         "revenue_growth_percent": None if growth is None else str(growth),
                         "gross_margin_percent": None if margin is None else str(margin)})
    return quarters


def render_history_context(quarters) -> str:
    if not quarters:
        return ""

    def percent(value):
        number = _decimal(value)
        return "unavailable" if number is None else f"{number:.1f}%"

    def same(q):
        return f", {_times(_decimal(q['same_basis_multiple']))} with borrowings less cash" if q.get("same_basis_multiple") else ""

    cells = [f"{q['quarter_end']} {_times(_decimal(q['multiple']))}{same(q)} (trailing revenue growth "
             f"{percent(q['revenue_growth_percent'])}, gross margin {percent(q['gross_margin_percent'])})"
             for q in quarters]
    return ("Own-history reference quarters, equity value / trailing revenue with the trailing-twelve-month growth "
            "and gross margin each was valued at: " + "; ".join(cells) + ". Unavailable means the retained filings "
            "do not hold the facts; nothing is estimated.")
