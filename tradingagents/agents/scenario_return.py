"""Arithmetic that puts accepted scenario cases and today's price on one time basis.

Everything here is computed from priced cases, the dated close and the stated required return.
Nothing is a forecast, a probability or a price target.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

# The case's obligation basis and the matching row of the price-implied valuation.
PERIMETERS = {"equity": None, "borrowings_only": "borrowings_only", "finance_equipment": "finance_equipment",
              "all_leases": "all_classified_obligations"}


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _days(analysis_date, period_end):
    try:
        return (date.fromisoformat(str(period_end)) - date.fromisoformat(str(analysis_date))).days
    except ValueError:
        return None


def annual_return(value, close, analysis_date, period_end) -> Decimal | None:
    """The yearly return from ``close`` on the analysis date to ``value`` at the period end."""
    value, close, days = _decimal(value), _decimal(close), _days(analysis_date, period_end)
    if value is None or close is None or value <= 0 or close <= 0 or not days or days <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        return (value / close) ** (Decimal(365) / Decimal(days)) - 1


def today_basis(accepted, close, rate, analysis_date) -> dict | None:
    """Weighted value today against the close; None unless every accepted case has a value today."""
    close = _decimal(close)
    if close is None or close <= 0 or not accepted or any(row.get("value_today") is None for row in accepted):
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        weights = [Decimal(row["weight"]) for row in accepted]
        values = [Decimal(row["value_today"]) for row in accepted]
        weighted = sum(w * v for w, v in zip(weights, values, strict=True)) / sum(weights)
        basis = {"weighted_value_today": str(weighted), "range_today": {"low": str(min(values)), "high": str(max(values))},
                 "weighted_today_vs_close_percent": str((weighted / close - 1) * 100),
                 "range_today_vs_close_percent": {"low": str((min(values) / close - 1) * 100),
                                                  "high": str((max(values) / close - 1) * 100)},
                 "weighted_annual_return": None, "return_gap_points": None}
        ends = {row.get("period_end") for row in accepted}
        rate = _decimal(rate)
        if len(ends) == 1 and rate is not None:
            period_end = sum(w * Decimal(row["price"]) for w, row in zip(weights, accepted, strict=True)) / sum(weights)
            yearly = annual_return(period_end, close, analysis_date, next(iter(ends)))
            if yearly is not None:
                basis.update(weighted_annual_return=str(yearly), return_gap_points=str((yearly - rate) * 100))
    return basis


def sturdiness(accepted, close) -> dict | None:
    """How far the weights would have to move for the weighted value today to equal the close."""
    close = _decimal(close)
    if close is None or close <= 0 or len(accepted) < 2 or any(row.get("value_today") is None for row in accepted):
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        values = [Decimal(row["value_today"]) for row in accepted]
        result = {"equal_weight_value_today": str(sum(values) / len(values)),
                  "equal_weight_vs_close_percent": str((sum(values) / len(values) / close - 1) * 100)}
        top = max(accepted, key=lambda row: Decimal(row["value_today"]))
        rest = [row for row in accepted if row is not top]
        rest_weight = sum(Decimal(row["weight"]) for row in rest)
        others = sum(Decimal(row["weight"]) * Decimal(row["value_today"]) for row in rest) / rest_weight
        high = Decimal(top["value_today"])
        result.update(highest={"case_id": top["case_id"], "name": top["name"], "role": top["role"],
                               "weight": top["weight"]})
        if others >= close:
            result["break_even"] = "not_needed"   # the other accepted cases already average at or above the close
        elif high <= close:
            result["break_even"] = "unreachable"  # no accepted case is above the close
        else:
            result.update(break_even="available", break_even_weight=str((close - others) / (high - others)))
    return result


def return_parts(case, implied, close) -> dict | None:
    """Split one case's change from the close into revenue, multiple, and shares and net obligations.

    Per share at the case's period end, applied in that order from today's price, so the three parts sum
    exactly to the case value less the close. Today's multiple is on the case's own obligation basis and
    on revenue of the preceding twelve months, the same construction the case applies at its period end.
    """
    if not isinstance(implied, dict) or implied.get("status") != "available" or case.get("multiple_basis") not in PERIMETERS:
        return None
    close, value = _decimal(close), _decimal(case.get("price"))
    quote = _decimal((implied.get("price") or {}).get("close"))
    shares_now = _decimal((implied.get("shares") or {}).get("value"))
    revenue_now = _decimal(implied.get("trailing_revenue_usd"))
    revenue, multiple = _decimal(case.get("forecast_revenue")), _decimal(case.get("multiple"))
    net, shares = _decimal(case.get("net_obligations")), _decimal(case.get("closing_shares"))
    perimeter = PERIMETERS[case["multiple_basis"]]
    net_now = Decimal(0)
    if perimeter is not None:
        row = next((r for r in implied.get("rows") or () if isinstance(r, dict) and r.get("perimeter") == perimeter
                    and r.get("status") == "available"), None)
        net_now = _decimal(row.get("net_obligations_usd")) if row else None
    numbers = (close, value, quote, shares_now, revenue_now, revenue, multiple, net, shares, net_now)
    if None in numbers or case.get("unit") != "USD/shares" or quote != close or min(shares_now, revenue_now, revenue,
                                                                                 multiple, shares) <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        multiple_now = (close * shares_now + net_now) / revenue_now
        after_revenue = (revenue * multiple_now - net_now) / shares_now
        after_multiple = (revenue * multiple - net_now) / shares_now
        rebuilt = (revenue * multiple - net) / shares
        if abs(rebuilt - value) > Decimal("0.005"):
            return None   # the case was not priced by this construction; say nothing rather than misattribute
        return {"multiple_today": str(multiple_now), "multiple_case": str(multiple),
                "revenue_today": str(revenue_now), "revenue_case": str(revenue),
                "revenue_effect": str(after_revenue - close), "multiple_effect": str(after_multiple - after_revenue),
                "capital_effect": str(value - after_multiple), "total": str(value - close)}
