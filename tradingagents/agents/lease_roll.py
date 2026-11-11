"""Lease balances and payments carried from a filing's snapshot to a case's period end.

Inputs are what a filing states: a payment schedule by year with its total and imputed interest, and
leases that have not commenced (a total, an average term, a commencement window). Everything else is
one of three stated assumptions, named in ``ASSUMPTIONS`` and repeated wherever a figure is shown:
payments fall mid-way through each scheduled period; a lease not yet commenced pays level amounts over
its average term; commencements are spread evenly across the stated window.

Nothing here knows a company. A filing without a schedule, or without leases awaiting commencement,
yields None for that part and the caller says so.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

ASSUMPTIONS = {
    "timing": "scheduled payments fall mid-way through each period",
    "level": "a lease that has not commenced pays level amounts over its weighted-average term",
    "spread": "commencements are spread evenly across the stated window",
}
_SCALE = {"USD": 1, "USD thousands": 1000, "USD millions": 1_000_000}
_STEPS = 240


def _years(start: date, end: date) -> float:
    return (end - start).days / 365


def _periods(years: dict, as_of: date):
    """Each scheduled amount with the dates it covers; the snapshot year's column is the rest of that year."""
    rows = []
    for label in sorted(years, key=int):
        year = int(label)
        if year < as_of.year:
            return None
        start = as_of if year == as_of.year else date(year - 1, 12, 31)
        finish = date(year, 12, 31)
        if finish <= start:
            continue
        rows.append((start, finish, float(years[label])))
    return rows or None


def _present(rows, rate: float, at: date) -> float:
    """Value at ``at`` of the scheduled payments falling after it, each paid mid-way through its period."""
    total = 0.0
    for start, finish, amount in rows:
        if finish <= at:
            continue
        begin = max(start, at)
        share = (finish - begin).days / (finish - start).days
        total += amount * share / (1 + rate) ** (_years(at, begin) + _years(begin, finish) / 2)
    return total


def implied_rate(years: dict, total, interest, as_of: date) -> float | None:
    """The yearly rate at which the schedule's payments are worth its stated present value, or None."""
    rows = _periods(years or {}, as_of)
    try:
        gross, imputed = float(total), abs(float(interest))
    except (TypeError, ValueError):
        return None
    if not rows or not 0 < imputed < gross or abs(sum(r[2] for r in rows) - gross) > gross * 0.001:
        return None
    target, low, high = gross - imputed, 0.0, 1.0
    if _present(rows, high, as_of) > target:
        return None
    for _ in range(80):
        middle = (low + high) / 2
        low, high = (middle, high) if _present(rows, middle, as_of) > target else (low, middle)
    return (low + high) / 2


def roll_schedule(schedule, totals, as_of: date, end: date) -> dict | None:
    """Opening balance, payments, their interest and principal, and the closing balance at ``end``."""
    if not isinstance(schedule, dict) or schedule.get("as_of") != as_of or not isinstance(totals, dict) or end <= as_of:
        return None
    years = schedule.get("years") or {}
    if not all(str(year) in years for year in range(as_of.year, end.year + 1)):
        return None  # a year the table does not state is unknown, never zero
    rate = implied_rate(years, totals.get("total"), totals.get("interest"), as_of)
    if rate is None:
        return None
    rows = _periods(years, as_of)
    opening, closing = _present(rows, rate, as_of), _present(rows, rate, end)
    paid = sum(amount * max((min(finish, end) - start).days, 0) / (finish - start).days for start, finish, amount in rows)
    principal = opening - closing
    return {"rate": rate, "opening": _money(opening), "paid": _money(paid), "principal": _money(principal),
            "interest": _money(paid - principal), "closing": _money(closing)}


def _money(value: float) -> Decimal:
    return Decimal(repr(round(value)))


def _month(text, *, last=False):
    """The first day of a yyyy-mm month, or its last day."""
    try:
        year, month = (int(part) for part in str(text).split("-")[:2])
        first = date(year, month, 1)
    except (ValueError, TypeError):
        return None
    return date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1) if last else first


def roll_new_leases(leases, as_of: date, end: date, rate: float | None) -> dict | None:
    """Rent paid by ``end`` on leases that had not commenced at ``as_of``, and what they still owe then.

    Central figures spread commencement evenly across the window; low and high are the least and most
    over every commencement date in it. The liability needs a rate; without one it is None.
    """
    rent = {"central": 0.0, "low": 0.0, "high": 0.0}
    owed = {"central": 0.0, "low": 0.0, "high": 0.0}
    run_rate, windows = 0.0, []
    for lease in leases or ():
        if not isinstance(lease, dict) or str(lease.get("as_of")) != str(as_of):
            continue
        try:
            scale = _SCALE[lease.get("unit")]
            amount, term = float(lease["undiscounted_amount"]) * scale, float(lease["weighted_average_term_years"])
        except (KeyError, TypeError, ValueError):
            continue
        start, finish = _month(lease.get("commencement_start")), _month(lease.get("commencement_end"), last=True)
        if start is None or finish is None or amount <= 0 or term <= 0 or finish < start:
            continue
        yearly = amount / term
        run_rate += yearly
        paid, remaining = [], []
        for step in range(_STEPS + 1):
            after_start = _years(start, finish) * step / _STEPS      # in years, so half-days are not dropped
            commenced_before_end = _years(start, end) - after_start
            elapsed = min(max(commenced_before_end, 0.0), term)
            paid.append(yearly * elapsed)
            left = term - elapsed if commenced_before_end >= 0 else 0.0
            remaining.append(0.0 if rate is None or left <= 0 else
                             yearly * left if rate == 0 else yearly * (1 - (1 + rate) ** -left) / rate)
        for bucket, series in ((rent, paid), (owed, remaining)):
            bucket["central"] += sum(series) / len(series)
            bucket["low"] += min(series)
            bucket["high"] += max(series)
        windows.append(f"{lease['commencement_start']} to {lease['commencement_end']}")
    if not windows:
        return None
    return {"annual_run_rate": _money(run_rate), "commencement": "; ".join(windows),
            "rent": {key: _money(value) for key, value in rent.items()},
            "liability": None if rate is None else {key: _money(value) for key, value in owed.items()}}
