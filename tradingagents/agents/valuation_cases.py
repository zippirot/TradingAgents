"""Dated model capital assumptions for a single conditional revenue case."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import Field, model_validator

from tradingagents.agents.accounting_checks import validate_obligation_category
from tradingagents.agents.valuation import (
    DecisionUse,
    ForecastAssumption,
    TargetResult,
    _annual,
    _borrowings_complete,
    _fact,
    _forecast,
    _outlooks,
    _Record,
    re_currency,
)


class CapitalValue(_Record):
    value: Decimal = Field(ge=0, max_digits=40)
    fact_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
    reason: str = Field(min_length=1, max_length=1200)
    assumption: Literal["estimated", "unchanged_from_snapshot"]


class ShareChange(_Record):
    source: Literal["conversion", "atm", "sbc", "buyback", "other"]
    shares: Decimal = Field(max_digits=40)
    converted_principal: Decimal | None = Field(default=None, gt=0, max_digits=40)
    instrument: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def _principal_matches_source(self):
        if (self.source == "conversion") != (self.converted_principal is not None):
            raise ValueError("converted_principal is required for a conversion and only for a conversion")
        if self.source == "conversion" and self.instrument is None:
            raise ValueError("instrument is required for a conversion")
        return self


class CashChange(_Record):
    source: Literal["atm", "operations", "finance_payments", "capex", "debt", "other"]
    amount: Decimal = Field(max_digits=40)
    reason: str = Field(min_length=1, max_length=600)


class CaseCapital(_Record):
    valuation_date: date
    currency: str = Field(min_length=3, max_length=3)
    closing_shares: CapitalValue
    cash: CapitalValue
    obligations: dict[str, CapitalValue]
    share_changes: tuple[ShareChange, ...] = Field(default=(), max_length=12)
    cash_changes: tuple[CashChange, ...] = Field(default=(), max_length=12)


class RevenueCase(_Record):
    method: Literal["revenue_case"]
    revenue_fact_id: str
    forecast: ForecastAssumption
    multiple: Decimal = Field(gt=0, max_digits=20)
    multiple_basis: Literal["equity", "borrowings_only", "finance_equipment", "all_leases"]
    multiple_period: Literal["forward", "trailing"]
    multiple_assumption_date: date
    multiple_rationale: str = Field(min_length=1, max_length=1200)
    capital: CaseCapital


class CaseSelection(_Record):
    method: Literal["case"]
    case_id: str = Field(min_length=1, max_length=80)
    version: int = Field(strict=True, ge=1, le=2)
    decision_date: date | None = None
    rerating_assumption: str = Field(min_length=1, max_length=1200)


def obligation_bases(obligations):
    bases = {"borrowings_only": ("borrowings",),
             "finance_equipment": ("borrowings", "finance_equipment") if "finance_equipment" in obligations else ("borrowings", "finance_leases", "equipment")}
    bases["all_leases"] = (*bases["finance_equipment"], "operating_leases")
    return bases


def _validate_capital_bridge(capital, refs):
    """One instrument, one role: tie estimated shares and cash to what changed them."""
    shares, cash = capital.closing_shares, capital.cash
    share_delta = shares.value - refs["closing_shares"][0].value
    if (share_delta or capital.share_changes) and sum(c.shares for c in capital.share_changes) != share_delta:
        raise ValueError(f"share_changes must sum to the {share_delta} difference from the snapshot share count")
    cash_delta = cash.value - refs["cash"][0].value
    if (cash_delta or capital.cash_changes) and sum(c.amount for c in capital.cash_changes) != cash_delta:
        raise ValueError(f"cash_changes must sum to the {cash_delta} difference from the snapshot cash balance")
    if any(c.source == "atm" for c in capital.share_changes) != any(c.source == "atm" for c in capital.cash_changes):
        raise ValueError("ATM proceeds and ATM shares must both be stated")
    converted = sum(c.converted_principal for c in capital.share_changes if c.source == "conversion")
    borrowings = capital.obligations.get("borrowings")
    if not converted or borrowings is None:
        return
    # Debt repaid with cash already explains part of the fall in borrowings, so
    # it cannot also absorb the converted principal. Principal can exceed the
    # carrying value net of issuance costs; retiring everything always suffices.
    snapshot = sum(f.value for f in refs["borrowings"])
    repaid = max(-sum(c.amount for c in capital.cash_changes if c.source == "debt"), Decimal(0))
    if snapshot - borrowings.value < min(converted + repaid, snapshot):
        raise ValueError(f"Converted principal {converted} still counted in borrowings")


_NOTE_SCALE = {"USD": 1, "USD thousands": 1000, "USD millions": 1_000_000}
FUNDING_LIMIT = "Rent on leases that have not commenced is not modelled; no discounting."


def _money(value, currency):
    return f"{value / Decimal(1_000_000):,.1f}M {currency}"


def _amount(value):
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _month(text, *, last=False):
    """First (or last) day of a ``YYYY-MM`` month, or None."""
    try:
        year, month = (int(part) for part in str(text).split("-"))
        first = date(year, month, 1)
    except (ValueError, TypeError):
        return None
    if not last:
        return first
    return date(year + (month == 12), month % 12 + 1, 1).fromordinal(date(year + (month == 12), month % 12 + 1, 1).toordinal() - 1)


def funding_bounds(capital, snapshot_date, scheduled, terms, stated=None) -> dict:
    """Two open questions about a case's cash bridge, sized from the filing. Never changes the case.

    A case states operating cash flow as one figure. Whether that figure is before or after lease interest,
    and whether it includes rent on leases that have not commenced, is not stated.

    Interest: only payments the case itself deducts can be counted twice. The most interest those payments
    can hold is all the imputed interest remaining on the schedule, or the payments themselves if smaller;
    that is a true maximum. An even spread of interest across payments is given beside it as an estimate.
    Rent: the filing gives a total, an average term and a commencement window, not a payment schedule, so
    the figures are a level-payment sensitivity and not a bound.
    """
    shares, end, bounds = capital.closing_shares.value, capital.valuation_date, {}
    totals = terms.get("schedule_totals") if isinstance(terms.get("schedule_totals"), dict) else {}
    total, interest = _amount(totals.get("total")), _amount(totals.get("interest"))
    deducted = min(stated, scheduled) if stated is not None and scheduled is not None else None
    if deducted is not None and deducted > 0 and total is not None and interest is not None and 0 < abs(interest) < total:
        most, even = min(deducted, abs(interest)), deducted * abs(interest) / total
        bounds["interest"] = {"maximum": str(most), "per_share_maximum": str(most / shares),
                              "estimate": str(even), "per_share_estimate": str(even / shares),
                              "share_of_payments": str(abs(interest) / total)}
    low = high = run_rate = Decimal(0)
    windows = []
    for lease in terms.get("leases") or ():
        if not isinstance(lease, dict) or str(lease.get("as_of")) != str(snapshot_date):
            continue
        scale, amount = _NOTE_SCALE.get(lease.get("unit")), _amount(lease.get("undiscounted_amount"))
        term = _amount(lease.get("weighted_average_term_years"))
        start, finish = _month(lease.get("commencement_start")), _month(lease.get("commencement_end"), last=True)
        if None in (scale, amount, term, start, finish) or amount <= 0 or term <= 0 or finish < start:
            continue
        yearly = amount * scale / term
        run_rate += yearly
        # Every lease starting on the first day of the window is the most rent the period can carry;
        # every lease starting on its last day is the least.
        high += yearly * max((end - start).days, 0) / 365
        low += yearly * max((end - finish).days, 0) / 365
        windows.append(f"{lease['commencement_start']} to {lease['commencement_end']}")
    if run_rate > 0:
        bounds["rent"] = {"annual_run_rate": str(run_rate), "low": str(low), "high": str(high),
                          "per_share_low": str(low / shares), "per_share_high": str(high / shares),
                          "commencement": "; ".join(windows)}
    return bounds


def funding_limit(bounds, currency, counts_cash=True) -> str:
    """What the funding check leaves outside the case arithmetic, with the filing's bounds where it gives them."""
    if not counts_cash or not bounds:
        return FUNDING_LIMIT
    parts = []
    if "interest" in bounds:
        item = bounds["interest"]
        parts.append(f"if projected operating cash flow is already after lease interest, the finance payments the case "
                     f"deducts count that interest twice and the case is too low by at most "
                     f"{Decimal(item['per_share_maximum']):.2f} {currency} a share (all imputed interest remaining on the "
                     f"schedule), about {Decimal(item['per_share_estimate']):.2f} {currency} if interest falls evenly "
                     f"across the payments, an assumption the filing does not state")
    if "rent" in bounds:
        item = bounds["rent"]
        parts.append(f"if it leaves out rent on leases that have not commenced ({item['commencement']}), the case is too "
                     f"high; if payments were level over the weighted-average term (about "
                     f"{_money(Decimal(item['annual_run_rate']), currency)} a year once all have commenced), by "
                     f"{Decimal(item['per_share_low']):.2f} to {Decimal(item['per_share_high']):.2f} {currency} a share. "
                     "The filing gives no payment schedule, so the actual figure can fall outside this range")
    return ("Not in the case arithmetic, sized from the filing: " + "; ".join(parts)
            + ". The case does not say which applies. No discounting.")


def funding_check(capital, snapshot_date, borrowings_snapshot, terms, counts_cash=True):
    """Compare a case's stated cash changes with the filing's payment schedule and maturing notes.

    The check reads retained source terms only. It reports what the case leaves
    unstated; it never adds a payment or changes the case's arithmetic.
    """
    terms = terms or {}
    schedule, currency, end = terms.get("schedule"), capital.currency, capital.valuation_date
    stated = -sum(c.amount for c in capital.cash_changes if c.source == "finance_payments")
    reasons, scheduled = [], None
    years = schedule.get("years") if isinstance(schedule, dict) and schedule.get("as_of") == snapshot_date else None
    # A year the table does not state is unknown, never zero.
    covered = bool(years) and all(str(year) in years for year in range(snapshot_date.year, end.year + 1))
    if years and covered:
        scheduled = Decimal(0)
        for label, amount in years.items():
            year = int(label)
            if snapshot_date.year <= year < end.year:
                scheduled += amount
            elif year == end.year:
                # The snapshot year's column is the remainder of that year.
                start = snapshot_date if year == snapshot_date.year else date(year - 1, 12, 31)
                whole = (date(year, 12, 31) - start).days
                scheduled += amount * (end - start).days / whole if whole > 0 else 0
    principal = Decimal(0)
    for note in terms.get("notes") or ():
        if not isinstance(note, dict) or not isinstance(note.get("name"), str):
            continue
        try:
            matures = date.fromisoformat(str(note.get("maturity_date")))
            if not snapshot_date < matures <= end:
                continue
            scale = _NOTE_SCALE.get(note.get("principal_unit"))
            if scale is None:
                reasons.append(f"{note['name'][:80]}: principal unit is not recognised, so its maturity is not checked.")
                continue
            amount = Decimal(str(note.get("principal_outstanding"))) * scale
        except (ValueError, ArithmeticError):
            continue
        principal += amount
        covered = (-sum(c.amount for c in capital.cash_changes if c.source == "debt" and c.amount < 0)
                   + sum(c.converted_principal for c in capital.share_changes if c.source == "conversion"))
        owed = capital.obligations.get("borrowings")
        still_owed = borrowings_snapshot is not None and owed is not None and owed.value >= borrowings_snapshot
        if covered < principal and not still_owed:
            reasons.append(f"{note['name'][:80]}: principal of {_money(amount, currency)} matures {matures}; "
                           f"the case accounts for {_money(covered, currency)} and borrowings fall below the snapshot.")
    if scheduled is None:
        reasons.insert(0, f"The payment schedule dated {snapshot_date} does not state every year through {end}."
                       if years else
                       f"No finance-lease and equipment payment schedule dated {snapshot_date} was retained.")
    elif stated < scheduled:
        reasons.insert(0, (f"Scheduled finance and equipment payments of {_money(scheduled, currency)} through {end} "
                           "are not stated in the case's cash changes." if stated <= 0 else
                           f"Scheduled finance and equipment payments are {_money(scheduled, currency)} through {end}; "
                           f"the case states {_money(stated, currency)}."))
    status = "unassessed" if scheduled is None else ("partial" if reasons else "assessed")
    summary = (f"Funding assessed: scheduled finance and equipment payments of {_money(scheduled, currency)} through {end} "
               "are stated and maturing notes are accounted for." if status == "assessed"
               else f"Funding {status}: " + " ".join(reasons))
    bounds = funding_bounds(capital, snapshot_date, scheduled, terms, stated) if counts_cash else {}
    return {"status": status, "scheduled_finance_payments": None if scheduled is None else str(scheduled),
            "stated_finance_payments": str(stated), "maturing_note_principal": str(principal),
            "reasons": reasons, "summary": summary, "bounds": bounds,
            "limit": funding_limit(bounds, currency, counts_cash)}


def case_funding(request, package, terms):
    """The funding check for a validated revenue case, read against its own snapshot facts."""
    capital = request.capital
    snapshot = _fact(package, capital.cash.fact_ids[0]).period_end
    owed = capital.obligations.get("borrowings")
    borrowings = sum(_fact(package, i).value for i in owed.fact_ids) if owed is not None else None
    # On an equity basis cash does not enter the value, so the bridge's open questions cannot move it.
    return funding_check(capital, snapshot, borrowings, terms, counts_cash=request.multiple_basis != "equity")


def price_case(request, package, outlooks, terms=None):
    capital = request.capital
    revenue = _fact(package, request.revenue_fact_id)
    if (revenue.metric != "Revenue" or revenue.value <= 0 or not _annual(revenue.period_start, revenue.period_end)
            or revenue.basis != "US-GAAP" or not re_currency(revenue.unit) or revenue.unit != capital.currency):
        raise ValueError("An annual reported revenue baseline in the case currency is required")
    forecast, warnings = _forecast(request.forecast, package, "Revenue", revenue.unit, revenue.basis,
                                  _outlooks(package, outlooks), baseline=revenue.value)
    if capital.valuation_date != request.forecast.period_end:
        raise ValueError("Closing capital valuation date must match the revenue case period end")
    if request.multiple_assumption_date != package.as_of or not request.multiple_rationale.strip():
        raise ValueError("Multiple needs the analysis date and a stated rationale")
    # Both views use the explicitly forecast annual period. It is historical
    # relative only to its assumed future closing date, never observed today.
    period_label = ("trailing at the future valuation date" if request.multiple_period == "trailing"
                    else "forward from the analysis date")
    obligations = capital.obligations
    bases = obligation_bases(obligations)
    if set(obligations) - set(bases["all_leases"]):
        raise ValueError("Unknown or overlapping obligation categories")
    if request.multiple_basis != "equity" and not set(bases[request.multiple_basis]) <= obligations.keys():
        raise ValueError("Missing required obligation category is unknown; selected basis unavailable")
    values = {"closing_shares": capital.closing_shares, "cash": capital.cash, **obligations}
    refs = {k: [_fact(package, i) for i in v.fact_ids] for k, v in values.items()}
    if len(refs["closing_shares"]) != 1 or len(refs["cash"]) != 1:
        raise ValueError("Closing shares and cash each require one corresponding reported snapshot fact")
    shares, cash = refs["closing_shares"][0], refs["cash"][0]
    if (shares.metric != "Common Shares Outstanding" or shares.unit != "shares" or shares.origin != "reported"
            or shares.value <= 0 or capital.closing_shares.value <= 0 or cash.metric != "Cash and Equivalents"):
        raise ValueError("Closing shares require actual common shares outstanding; cash requires unrestricted cash")
    ids = [i for v in values.values() for i in v.fact_ids]
    if len(ids) != len(set(ids)):
        raise ValueError("Capital references overlap")
    for label, facts in refs.items():
        v = values[label]
        if (not v.reason.strip() or any(f.basis != "US-GAAP" or f.period_start is not None or f.period_end != cash.period_end
                or f.value < 0 or f.unit != ("shares" if label == "closing_shares" else capital.currency) for f in facts)):
            raise ValueError(f"{label} needs a reason and compatible same-snapshot references")
        if v.assumption == "unchanged_from_snapshot" and sum(f.value for f in facts) != v.value:
            raise ValueError(f"{label} unchanged from snapshot conflicts with its source value")
    _validate_capital_bridge(capital, refs)
    components = {k: v.fact_ids for k, v in obligations.items()}
    for category in components:
        validate_obligation_category(category, refs[category])
    if "borrowings" in components:
        _borrowings_complete(package, components["borrowings"])
    for basis, categories in bases.items():
        missing = set(categories) - components.keys()
        if missing:
            warnings.append(f"{basis} sensitivity unavailable: {', '.join(sorted(missing))} unknown.")
    with localcontext() as ctx:
        ctx.prec = 60
        capitalized = request.forecast.value * request.multiple
        net = {basis: sum(obligations[k].value for k in cats) - capital.cash.value
               for basis, cats in bases.items() if set(cats) <= components.keys()}
        equity = capitalized if request.multiple_basis == "equity" else capitalized - net[request.multiple_basis]
        if equity <= 0:
            raise ValueError("Nonpositive conditional equity value; no per-share value")
        sensitivities = {basis: str((capitalized - debt) / capital.closing_shares.value)
                         for basis, debt in net.items() if basis != request.multiple_basis and capitalized > debt}
        assumptions = [forecast, f"Assumed {request.multiple_basis} / revenue multiple {request.multiple}, {period_label}."]
        for label, v in values.items():
            assumptions.append(f"{label}: {v.value} ({v.assumption.replace('_', ' ')}); references {', '.join(v.fact_ids)}. Reason: {v.reason}")
        for change in capital.share_changes:
            change_label = f"{change.source}, {change.instrument}" if change.instrument else change.source
            assumptions.append(f"share change ({change_label}): {change.shares}. Reason: {change.reason}")
        for change in capital.cash_changes:
            assumptions.append(f"cash change ({change.source}): {change.amount}. Reason: {change.reason}")
        result = TargetResult(status="supported", method="revenue_case", target=equity / capital.closing_shares.value,
            unit=capital.currency + "/shares", input_fact_ids=(revenue.fact_id, *ids), capital_snapshot_date=cash.period_end,
            shares_outstanding=capital.closing_shares.value, multiple=request.multiple,
            net_obligations=net.get(request.multiple_basis), multiple_assumption_date=request.multiple_assumption_date,
            valuation_period_start=request.forecast.period_start, valuation_period_end=request.forecast.period_end,
            accounting_basis=request.forecast.basis, assumptions=tuple(assumptions),
            warnings=(*warnings, "{summary} {limit}".format(**case_funding(request, package, terms))),
            decision_use=DecisionUse(classification="forward_scenario", suitability="conditional", final_target_eligible=True))
        return result, sensitivities
