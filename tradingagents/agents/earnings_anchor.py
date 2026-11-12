"""How an earnings case's forecast sits against what the company has filed and what the vendor shows.

Arithmetic only. It never changes or rejects a case, and whatever cannot be stated from one filed value
is left out rather than estimated. The vendor range is unverified and is said to be.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

CALENDAR_SLACK = timedelta(days=7)  # 52/53-week fiscal years move a period end by up to a week


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _day(value):
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _year_before(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def _one(facts, metric, start, end, slack=timedelta(0)):
    """The single filed value for ``metric`` over a period, or None when absent or filed with two values."""
    found = {(f.period_start, f.period_end, _decimal(f.value)) for f in facts
             if f.metric == metric and _day(f.period_start) is not None and _day(f.period_end) is not None
             and abs(_day(f.period_start) - start) <= slack and abs(_day(f.period_end) - end) <= slack}
    values = {value for _start, _end, value in found}
    return values.pop() if len(values) == 1 and None not in values else None


def _against(value, base):
    gap = (value / base - 1) * 100
    return "level with" if abs(gap) < Decimal("0.05") else f"{abs(gap):.1f}% {'above' if gap > 0 else 'below'}"


def earnings_anchor(request, facts, trade_date, vendor_estimates) -> dict | None:
    """Lines placing an earnings case's forecast against filed earnings; None when there is no filed base."""
    forecast = request.get("forecast") if isinstance(request, dict) and request.get("method") == "earnings_case" else None
    facts = list(facts or ())
    base = next((f for f in facts if f.fact_id == request.get("eps_fact_id")), None) if forecast else None
    value = _decimal(forecast.get("value")) if isinstance(forecast, dict) else None
    start, end = (_day(forecast.get(key)) for key in ("period_start", "period_end")) if isinstance(forecast, dict) else (None, None)
    filed = _decimal(base.value) if base is not None else None
    if None in (value, start, end, filed) or filed <= 0 or value <= 0:
        return None
    lines = [f"Against the filings: the forecast of {value:.2f} is {_against(value, filed)} the filed {filed:.2f} "
             f"for {base.period_start} to {base.period_end}."]
    result = {"growth_percent": str((value / filed - 1) * 100), "year_to_date": None, "vendor": None}
    # The longest filed stretch that starts with the forecast period and ends inside it.
    partial = sorted({_day(f.period_end) for f in facts if f.metric == base.metric and _day(f.period_start) == start
                      and _day(f.period_end) is not None and _day(f.period_end) < end})
    if partial:
        so_far_end = partial[-1]
        so_far = _one(facts, base.metric, start, so_far_end)
        before = _one(facts, base.metric, _year_before(start), _year_before(so_far_end), CALENDAR_SLACK)
        year = _one(facts, base.metric, _year_before(start), _year_before(end), CALENDAR_SLACK)
        if None not in (so_far, before, year) and before > 0 and year - before > 0 and value - so_far > 0:
            rest, rest_before = value - so_far, year - before
            lines.append(f"Filed so far in the forecast period: {so_far:.2f} through {so_far_end}, {_against(so_far, before)} "
                         f"the {before:.2f} of the same months a year earlier. The forecast leaves {rest:.2f} for the rest "
                         f"of the period, {_against(rest, rest_before)} the {rest_before:.2f} of those months a year "
                         "earlier (per-share figures do not add exactly across quarters).")
            result["year_to_date"] = {"through": str(so_far_end), "filed": str(so_far), "year_earlier": str(before),
                                      "rest": str(rest), "rest_year_earlier": str(rest_before)}
    today = _day(trade_date)
    row = next((r for r in vendor_estimates or () if isinstance(r, dict) and r.get("metric") == "eps"
                and r.get("period_code") == "0y"), None)
    low, high, average = (_decimal(row.get(key)) for key in ("low", "high", "average")) if row else (None, None, None)
    if today is not None and start <= today <= end and None not in (low, high) and 0 < low <= high:
        position = "below_low" if value < low else "above_high" if value > high else "inside"
        words = {"below_low": "below the low", "above_high": "above the high", "inside": "inside the range"}[position]
        count = f" from {row['analyst_count']} analysts" if row.get("analyst_count") else ""
        lines.append(f"Unverified vendor estimates for the company's current fiscal year (the vendor does not state the "
                     f"period or basis): low {low:.2f}, " + (f"average {average:.2f}, " if average is not None else "")
                     + f"high {high:.2f}{count}; this forecast is {words}.")
        result["vendor"] = {"low": str(low), "high": str(high), "position": position}
    return {**result, "lines": lines}
