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


def reference_position(row, state) -> dict:
    """Place one priced revenue case in the own-history range, or say why it cannot be placed."""
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

    cells = [f"{q['quarter_end']} {_times(_decimal(q['multiple']))} (trailing revenue growth "
             f"{percent(q['revenue_growth_percent'])}, gross margin {percent(q['gross_margin_percent'])})"
             for q in quarters]
    return ("Own-history reference quarters, equity value / trailing revenue with the trailing-twelve-month growth "
            "and gross margin each was valued at: " + "; ".join(cells) + ". Unavailable means the retained filings "
            "do not hold the facts; nothing is estimated.")
