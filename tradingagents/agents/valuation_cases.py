"""Dated model capital assumptions for a single conditional revenue case."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import Field, model_serializer, model_validator

from tradingagents.agents.accounting_checks import validate_obligation_category
from tradingagents.agents.lease_roll import ASSUMPTIONS, roll_new_leases, roll_schedule
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
    # Names the note a "debt" change repays or repurchases, so code does not also convert it.
    instrument: str | None = Field(default=None, min_length=1, max_length=200)

    @model_serializer(mode="wrap")
    def _unnamed_stays_absent(self, handler):
        record = handler(self)
        if record.get("instrument") is None:
            record.pop("instrument", None)
        return record


class CaseCapital(_Record):
    valuation_date: date
    currency: str = Field(min_length=3, max_length=3)
    closing_shares: CapitalValue
    cash: CapitalValue
    obligations: dict[str, CapitalValue]
    share_changes: tuple[ShareChange, ...] = Field(default=(), max_length=12)
    cash_changes: tuple[CashChange, ...] = Field(default=(), max_length=12)
    # What the "operations" cash change holds. Stated, code completes the cash bridge; left out (older
    # requests), the two questions stay open beside the case as before.
    operations_after_lease_interest: bool | None = None
    operations_include_new_lease_rent: bool | None = None

    @model_serializer(mode="wrap")
    def _unstated_stays_absent(self, handler):
        """A request that does not answer the two questions keeps the record shape it always had."""
        record = handler(self)
        for key in ("operations_after_lease_interest", "operations_include_new_lease_rent"):
            if record.get(key) is None:
                record.pop(key, None)
        return record


class RevenueCase(_Record):
    method: Literal["revenue_case"]
    revenue_fact_id: str
    forecast: ForecastAssumption
    multiple: Decimal = Field(gt=0, max_digits=20)
    multiple_basis: Literal["equity", "borrowings_only", "finance_equipment", "all_leases"]
    # No longer asked for: the word changes no arithmetic. Kept, with the old default, so saved requests replay.
    multiple_period: Literal["forward", "trailing"] = "forward"
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
# How every revenue case is priced: its multiple times the case period's revenue, with shares and net
# obligations at the period end. The same construction as a past quarter's value over the preceding
# twelve months' revenue, which is what the same-basis history states.
MULTIPLE_CONSTRUCTION = "applied at the period end to that period's revenue"
# A stated finance-payment total this close to the filing's schedule is the schedule, typed with a slip.
FUNDING_TOLERANCE = Decimal("0.001")
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


CONVERSION = ("A convertible note outstanding at the period end is treated as converted when the case's own value "
              "per share is above its conversion price: its shares are added and its principal leaves borrowings, never both.")


def outstanding_convertibles(capital, snapshot_date, terms) -> tuple[list, list]:
    """Notes the filing states that are still outstanding at the case's period end, and plain lines for the rest."""
    notes, lines = [], []
    named = " ".join(str(c.instrument) for c in (*capital.share_changes, *capital.cash_changes)
                     if c.instrument and c.source in ("conversion", "debt"))
    for note in (terms or {}).get("convertibles") or ():
        try:
            name, principal = str(note["name"])[:80], Decimal(str(note["principal"]))
            matures = date.fromisoformat(str(note["maturity_date"]))
            price = None if note.get("conversion_price") is None else Decimal(str(note["conversion_price"]))
            call = note.get("capped_call")
            call = None if call is None else (Decimal(str(call["strike"])), Decimal(str(call["cap"])),
                                             date.fromisoformat(str(call["expires"])))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        if str(note.get("as_of")) != str(snapshot_date) or note.get("currency") != capital.currency or principal <= 0:
            continue
        if matures <= capital.valuation_date:
            continue  # the maturity check covers a note that falls due inside the period
        year = re.search(r"20\d{2}", name)
        if year and year.group() in named:
            lines.append(f"{name}: the case states its own repayment or conversion, so code adds nothing.")
        elif price is None or price <= 0:
            lines.append(f"{name}: left open. The filing's conversion price was not read, so the note stays as debt.")
        else:
            # A capped call that has expired by the period end offsets nothing.
            notes.append({"name": name, "principal": principal, "price": price,
                          "call": call if call and call[2] >= capital.valuation_date else None})
    return notes, lines


def _per_share(equity, shares, converted):
    """Value per share once the converted notes' shares, net of capped-call shares, are counted.

    Each converted note adds principal / price shares. Its capped call returns shares worth the gain between
    the strike and the cap on those same shares. The count depends on the value, so the two are solved together.
    """
    def new_shares(value, note):
        gross = note["principal"] / note["price"]
        if note["call"] is None or value <= note["call"][0]:
            return gross, Decimal(0)
        return gross, gross * (min(value, note["call"][1]) - note["call"][0]) / value

    low, high = Decimal(0), equity / shares
    for _ in range(200):
        value = (low + high) / 2
        count = shares + sum(g - o for g, o in (new_shares(value, n) for n in converted))
        low, high = (value, high) if value * count < equity else (low, value)
    value = (low + high) / 2
    return value, [new_shares(value, n) for n in converted]


def settle_convertibles(equity, shares, notes, borrowings):
    """Decide each outstanding note at the case's own value: converted into shares, or left as debt.

    `equity` is the case's equity value with every note still counted as debt; `borrowings` is the debt the
    basis counts (None when the basis counts none, so removing a note changes no value).
    """
    converted, left, value, counts = [], borrowings, equity / shares, []
    for note in sorted(notes, key=lambda n: n["price"]):
        removed = min(note["principal"], left) if left is not None else Decimal(0)
        trial = [*converted, {**note, "removed": removed}]
        trial_value, trial_counts = _per_share(equity + sum(n["removed"] for n in trial), shares, trial)
        if trial_value <= note["price"]:
            break
        converted, value, counts = trial, trial_value, trial_counts
        left = None if left is None else left - removed
    done = {n["name"] for n in converted}
    lines = []
    for note, (gross, offset) in zip(converted, counts, strict=True):
        line = (f"{note['name']}: treated as converted by code. The case's value of {value:.2f} a share is above the "
                f"{note['price']} conversion price, so {gross:,.0f} shares are added")
        if offset:
            line += (f", less {offset:,.0f} shares returned by the capped call (gain between its {note['call'][0]} strike "
                     f"and {note['call'][1]} cap on the same shares)")
        line += (f", and {note['removed']:,.0f} leaves borrowings." if borrowings is not None else
                 "; this basis counts no borrowings, so no debt is removed.")
        lines.append(line)
    for note in notes:
        if note["name"] not in done:
            lines.append(f"{note['name']}: stays as debt. The case's value of {value:.2f} a share is not above the "
                         f"{note['price']} conversion price.")
    return {"value": value, "shares": shares + sum(g - o for g, o in counts),
            "debt_removed": sum((n["removed"] for n in converted), Decimal(0)), "lines": lines}


LEASE_FINANCE = ("finance_equipment", "finance_leases", "equipment")


def carry_leases(filed: dict, snapshot_date, end, terms) -> dict:
    """Lease balances as filed, carried to a case's period end where the filing allows: category -> value, reason.

    Finance leases and equipment: the filed payment schedule repays principal, so the balance falls. It is used
    only when the schedule's own present value agrees with the filed balances given (within 0.1%), so a partial
    set of categories is never scaled. Operating leases have no retained schedule and stay as filed; what leases
    commencing in the period will still owe at the period end is added to them. A category absent from the
    result is held as filed.
    """
    terms, carried = terms or {}, {}
    roll = roll_schedule(terms.get("schedule"), terms.get("schedule_totals"), snapshot_date, end)
    finance = [c for c in LEASE_FINANCE if c in filed]
    total = sum(filed[c] for c in finance)
    if roll is not None and total > 0 and abs(roll["opening"] - total) <= total / 1000:
        closing, left = (total * roll["closing"] / roll["opening"]).quantize(Decimal(1)), None
        left = closing
        for index, category in enumerate(finance):
            # The last category takes the remainder, so the parts always sum to the carried total.
            value = left if index == len(finance) - 1 else (filed[category] * closing / total).quantize(Decimal(1))
            left -= value
            carried[category] = {"value": value, "reason": (
                f"{category} obligations of {filed[category]} as of {snapshot_date} carried to {end} on the filed "
                f"payment schedule: {roll['principal']} of principal repaid by then, at the "
                f"{Decimal(repr(roll['rate'])) * 100:.2f}% a year the schedule implies, where {ASSUMPTIONS['timing']}. "
                "No new finance lease or equipment financing is assumed.")}
    new = roll_new_leases(terms.get("leases"), snapshot_date, end, roll["rate"] if roll else None)
    if "operating_leases" in filed and new is not None and new["liability"] and new["liability"]["central"] > 0:
        owed = new["liability"]
        carried["operating_leases"] = {"value": filed["operating_leases"] + owed["central"], "reason": (
            f"operating_leases obligations of {filed['operating_leases']} as of {snapshot_date} held as filed, plus "
            f"{owed['central']} still owed at {end} on leases commencing {new['commencement']} ({owed['low']} to "
            f"{owed['high']} across every commencement date in the window). {ASSUMPTIONS['level'].capitalize()}; "
            f"{ASSUMPTIONS['spread']}; discounted at the rate the filed finance schedule implies. Their "
            "classification is not stated in the filing.")}
    return carried


def funded_cash(capital, snapshot_date, terms) -> dict:
    """What code adds to or takes from a case's closing cash once the case says what its operating cash holds.

    Interest: when operating cash is already after lease interest, the scheduled payments the case deducts
    carry that interest a second time, so the interest part of those payments is added back. The split of
    payments into interest and principal comes from the filed schedule at its own implied rate.
    Rent: when operating cash leaves out rent on leases that commence in the period, that rent is deducted,
    at the central figure for commencement spread evenly across the filed window.
    A question the case does not answer, or that the filing cannot size, stays open and changes nothing.
    """
    terms, end, currency = terms or {}, capital.valuation_date, capital.currency
    shares = capital.closing_shares.value
    roll = roll_schedule(terms.get("schedule"), terms.get("schedule_totals"), snapshot_date, end)
    new = roll_new_leases(terms.get("leases"), snapshot_date, end, roll["rate"] if roll else None)
    stated = -sum(c.amount for c in capital.cash_changes if c.source == "finance_payments")
    adjustment, decided, lines, unsized = Decimal(0), [], [], []
    record = {"interest_added_back": None, "rent_deducted": None, "rent_range": None}
    if capital.operations_after_lease_interest is False:
        decided.append("interest")
        lines.append("operating cash is stated before lease interest, so the scheduled payments carry that interest once")
    elif capital.operations_after_lease_interest is True and roll is not None and stated > 0 and roll["paid"] > 0:
        back = (roll["interest"] * min(stated, roll["paid"]) / roll["paid"]).quantize(Decimal(1))
        adjustment += back
        decided.append("interest")
        record["interest_added_back"] = str(back)
        lines.append(f"operating cash is stated after lease interest, so {_money(back, currency)} of interest inside the "
                     f"scheduled payments is added back ({back / shares:.2f} {currency} a share; the filed schedule "
                     f"implies {Decimal(repr(roll['rate'])) * 100:.2f}% a year, where "
                     f"{ASSUMPTIONS['timing']})")
    elif capital.operations_after_lease_interest is True and stated > 0:
        unsized.append("operating cash is stated after lease interest, but the lease interest inside the scheduled "
                       "payments could not be sized from a filed schedule, so none is added back")
    if capital.operations_include_new_lease_rent is True:
        decided.append("rent")
        lines.append("operating cash is stated after rent on leases that commence in the period")
    elif capital.operations_include_new_lease_rent is False and new is not None:
        rent = new["rent"]
        adjustment -= rent["central"]
        decided.append("rent")
        record["rent_deducted"], record["rent_range"] = str(rent["central"]), [str(rent["low"]), str(rent["high"])]
        lines.append(f"operating cash leaves out rent on leases that commence {new['commencement']}, so "
                     f"{_money(rent['central'], currency)} is deducted ({rent['central'] / shares:.2f} {currency} a share; "
                     f"{rent['low'] / shares:.2f} to {rent['high'] / shares:.2f} across every commencement date in the "
                     f"window; {ASSUMPTIONS['level']}, and {ASSUMPTIONS['spread']})")
    elif capital.operations_include_new_lease_rent is False and not terms.get("leases"):
        decided.append("rent")
        lines.append("no lease awaiting commencement was retained from the filing, so no new rent is deducted")
    elif capital.operations_include_new_lease_rent is False:
        unsized.append("operating cash leaves out rent on leases that commence in the period, but that rent could "
                       "not be sized from the retained lease terms, so none is deducted")
    return {**record, "adjustment": str(adjustment), "decided": decided, "lines": lines, "unsized": unsized}


def funding_limit(bounds, currency, counts_cash=True, funded=None) -> str:
    """What code completed in the case's cash, then what stays outside the arithmetic, sized where the filing allows."""
    if not counts_cash:
        return FUNDING_LIMIT
    decided = set((funded or {}).get("decided") or ())
    computed = "Computed in the case arithmetic: " + "; ".join(funded["lines"]) + ". " if decided else ""
    parts = []
    if "interest" in bounds and "interest" not in decided:
        item = bounds["interest"]
        parts.append(f"if projected operating cash flow is already after lease interest, the finance payments the case "
                     f"deducts count that interest twice and the case is too low by at most "
                     f"{Decimal(item['per_share_maximum']):.2f} {currency} a share (all imputed interest remaining on the "
                     f"schedule), about {Decimal(item['per_share_estimate']):.2f} {currency} if interest falls evenly "
                     f"across the payments, an assumption the filing does not state")
    if "rent" in bounds and "rent" not in decided:
        item = bounds["rent"]
        parts.append(f"if it leaves out rent on leases that have not commenced ({item['commencement']}), the case is too "
                     f"high; if payments were level over the weighted-average term (about "
                     f"{_money(Decimal(item['annual_run_rate']), currency)} a year once all have commenced), by "
                     f"{Decimal(item['per_share_low']):.2f} to {Decimal(item['per_share_high']):.2f} {currency} a share. "
                     "The filing gives no payment schedule, so the actual figure can fall outside this range")
    unsized = (funded or {}).get("unsized") or []
    if unsized:
        computed += "Left open: " + "; ".join(unsized) + ". "
    if not parts:
        return computed + ("No discounting." if "rent" in decided or unsized else FUNDING_LIMIT)
    return (computed + "Not in the case arithmetic, sized from the filing: " + "; ".join(parts)
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
    first = snapshot_date.year + (snapshot_date == date(snapshot_date.year, 12, 31))  # an ended year needs no column
    covered = bool(years) and all(str(year) in years for year in range(first, end.year + 1))
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
    elif scheduled - stated > scheduled * FUNDING_TOLERANCE:
        reasons.insert(0, (f"Scheduled finance and equipment payments of {_money(scheduled, currency)} through {end} "
                           "are not stated in the case's cash changes." if stated <= 0 else
                           f"Scheduled finance and equipment payments are {_money(scheduled, currency)} through {end}; "
                           f"the case states {_money(stated, currency)}."))
    status = "unassessed" if scheduled is None else ("partial" if reasons else "assessed")
    summary = (f"Funding assessed: scheduled finance and equipment payments of {_money(scheduled, currency)} through {end} "
               "are stated and maturing notes are accounted for." if status == "assessed"
               else f"Funding {status}: " + " ".join(reasons))
    bounds = funding_bounds(capital, snapshot_date, scheduled, terms, stated) if counts_cash else {}
    funded = funded_cash(capital, snapshot_date, terms) if counts_cash else None
    return {"status": status, **({"funded": funded} if funded and (funded["decided"] or funded["unsized"]) else {}), "scheduled_finance_payments": None if scheduled is None else str(scheduled),
            "stated_finance_payments": str(stated), "maturing_note_principal": str(principal),
            "reasons": reasons, "summary": summary, "bounds": bounds,
            "limit": funding_limit(bounds, currency, counts_cash, funded)}


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
    # The arithmetic is the same whichever period word the analyst chose, so one description is printed.
    period_label = MULTIPLE_CONSTRUCTION
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
        # Cash as the case stated it, completed by code where the case says what its operating cash holds.
        funded = funded_cash(capital, cash.period_end, terms)
        closing_cash = capital.cash.value + Decimal(funded["adjustment"])
        # A lease balance supplied as filed is carried to the period end like one the case leaves out.
        carried = carry_leases({k: v.value for k, v in obligations.items()
                                if k != "borrowings" and v.assumption == "unchanged_from_snapshot"},
                               cash.period_end, capital.valuation_date, terms)
        owed = {k: carried[k]["value"] if k in carried else v.value for k, v in obligations.items()}
        net = {basis: sum(owed[k] for k in cats) - closing_cash
               for basis, cats in bases.items() if set(cats) <= components.keys()}
        equity = capitalized if request.multiple_basis == "equity" else capitalized - net[request.multiple_basis]
        if equity <= 0:
            raise ValueError("Nonpositive conditional equity value; no per-share value")
        # Notes still outstanding at the period end are converted or left as debt at each basis's own value.
        notes, note_lines = outstanding_convertibles(capital, cash.period_end, terms)
        debt = owed.get("borrowings")
        settled = settle_convertibles(equity, capital.closing_shares.value, notes,
                                      None if request.multiple_basis == "equity" else debt)
        sensitivities = {basis: str(settle_convertibles(capitalized - owing, capital.closing_shares.value, notes, debt)["value"])
                         for basis, owing in net.items() if basis != request.multiple_basis and capitalized > owing}
        assumptions = [forecast, f"Assumed {request.multiple_basis} / revenue multiple {request.multiple}, {period_label}."]
        for label, v in values.items():
            assumptions.append(f"{label}: {v.value} ({v.assumption.replace('_', ' ')}); references {', '.join(v.fact_ids)}. Reason: {v.reason}")
        for change in capital.share_changes:
            change_label = f"{change.source}, {change.instrument}" if change.instrument else change.source
            assumptions.append(f"share change ({change_label}): {change.shares}. Reason: {change.reason}")
        for change in capital.cash_changes:
            assumptions.append(f"cash change ({change.source}): {change.amount}. Reason: {change.reason}")
        for category, item in carried.items():
            assumptions.append(f"{category} carried by code: {item['value']}. {item['reason']}")
        atm_shares = sum(c.shares for c in capital.share_changes if c.source == "atm")
        atm_cash = sum(c.amount for c in capital.cash_changes if c.source == "atm")
        if atm_shares or atm_cash:
            if atm_shares <= 0 or atm_cash <= 0:
                raise ValueError("A share-sale programme adds shares and cash; both must be positive")
            assumptions.append(f"share sales checked by code: {atm_shares:,.0f} shares for {atm_cash:,.0f} of cash is "
                               f"{atm_cash / atm_shares:.2f} a share after costs; this case's value is {settled['value']:.2f} a share.")
        assumptions.extend(f"convertible notes: {line}" for line in (*settled["lines"], *note_lines))
        if settled["lines"]:
            assumptions.append("convertible notes: " + CONVERSION + " A capped call covering notes already repurchased is not valued.")
        if request.multiple_basis != "equity" and Decimal(funded["adjustment"]):
            assumptions.append(f"cash completed by code: {closing_cash} (stated {capital.cash.value}, adjustment "
                               f"{Decimal(funded['adjustment']):+}). " + "; ".join(funded["lines"]) + ".")
        result = TargetResult(status="supported", method="revenue_case", target=settled["value"],
            unit=capital.currency + "/shares", input_fact_ids=(revenue.fact_id, *ids), capital_snapshot_date=cash.period_end,
            shares_outstanding=settled["shares"], multiple=request.multiple,
            net_obligations=(None if request.multiple_basis == "equity"
                             else net[request.multiple_basis] - settled["debt_removed"]),
            multiple_assumption_date=request.multiple_assumption_date,
            valuation_period_start=request.forecast.period_start, valuation_period_end=request.forecast.period_end,
            accounting_basis=request.forecast.basis, assumptions=tuple(assumptions),
            warnings=(*warnings, "{summary} {limit}".format(**case_funding(request, package, terms))),
            decision_use=DecisionUse(classification="forward_scenario", suitability="conditional", final_target_eligible=True))
        return result, sensitivities
