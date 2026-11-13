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
    # The assumed sale price of an "atm" entry, before costs, so code can check shares against cash.
    price: Decimal | None = Field(default=None, gt=0, max_digits=20)

    @model_serializer(mode="wrap")
    def _unpriced_stays_absent(self, handler):
        record = handler(self)
        if record.get("price") is None:
            record.pop("price", None)
        return record

    @model_validator(mode="after")
    def _principal_matches_source(self):
        if self.price is not None and self.source != "atm":
            raise ValueError("price belongs to an atm share change only")
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


class CashModel(_Record):
    """Operating cash flow and cash capital spending as shares of the case's own revenue.

    Code turns the rates into amounts over the months between the filed balance sheet and the valuation date,
    so a case with more revenue has more of both and no amount can be chosen to make cash come out even.
    """
    operating_cash_margin: Decimal = Field(gt=-1, lt=1, max_digits=8)
    operating_cash_reason: str = Field(min_length=1, max_length=600)
    capex_rate: Decimal = Field(ge=0, lt=1, max_digits=8)
    capex_reason: str = Field(min_length=1, max_length=600)


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
    cash_model: CashModel | None = None

    @model_serializer(mode="wrap")
    def _unstated_stays_absent(self, handler):
        """A request that does not answer the two questions keeps the record shape it always had."""
        record = handler(self)
        for key in ("operations_after_lease_interest", "operations_include_new_lease_rent", "cash_model"):
            if record.get(key) is None:
                record.pop(key, None)
        return record

    @model_validator(mode="after")
    def _one_statement_of_operating_cash(self):
        if self.cash_model is not None and any(c.source in ("operations", "capex") for c in self.cash_changes):
            raise ValueError("State operating cash and capital spending as cash_model rates or as cash_changes "
                             "amounts, not both")
        return self


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


class EarningsBuild(_Record):
    """The three inputs an earnings forecast is built from, for the forecast period."""
    revenue: Decimal = Field(gt=0, max_digits=40)
    net_margin: Decimal = Field(gt=0, lt=1, max_digits=20)
    diluted_shares: Decimal = Field(gt=0, max_digits=40)
    revenue_reason: str = Field(min_length=1, max_length=400)
    margin_reason: str = Field(min_length=1, max_length=400)
    shares_reason: str = Field(min_length=1, max_length=400)


class EarningsCase(_Record):
    """Forecast diluted earnings per share times a stated multiple, for a company with positive filed earnings."""
    method: Literal["earnings_case"]
    eps_fact_id: str
    forecast: ForecastAssumption
    multiple: Decimal = Field(gt=0, max_digits=20)
    multiple_assumption_date: date
    multiple_rationale: str = Field(min_length=1, max_length=1200)
    # Optional so cases saved before the build still replay; a case without one says it is not built.
    build: EarningsBuild | None = None

    @model_serializer(mode="wrap")
    def _absent_build_stays_absent(self, handler):
        data = handler(self)
        if data.get("build") is None:
            data.pop("build", None)
        return data


BUILD_TOLERANCE = Decimal("0.03")


def earnings_build_parts(request: EarningsCase, package) -> dict | None:
    """What the build gives a share and how each input moves it from the filed year; None without a build.

    Filed EPS is not always net income over diluted shares (preferred dividends, participating securities), so
    the filed ratio between the two is carried into the built figure. The three effects are applied in order,
    revenue, margin, shares, and sum exactly to the built figure less the filed EPS.
    """
    build = request.build
    if build is None:
        return None
    filed = _fact(package, request.eps_fact_id)

    def one(metric):
        # Parent net income is often derived from the filing (profit less the minority share); that is the filed year too.
        found = {f.value for f in package.facts if f.metric == metric and f.value is not None
                 and (f.period_start, f.period_end) == (filed.period_start, filed.period_end)}
        return next(iter(found)) if len(found) == 1 else None

    revenue, income, shares = one("Revenue"), one("Net Income"), one("Weighted Average Diluted Shares")
    with localcontext() as context:
        context.prec = 60
        raw = build.revenue * build.net_margin / build.diluted_shares
        if None in (revenue, income, shares) or min(revenue, income, shares) <= 0 or filed.value <= 0:
            return {"status": "unchecked", "built_eps": str(raw), "ratio": "1"}
        ratio = filed.value / (income / shares)
        margin = income / revenue
        after_revenue = filed.value * build.revenue / revenue
        after_margin = after_revenue * build.net_margin / margin
        built = after_margin * shares / build.diluted_shares
        return {"status": "checked", "built_eps": str(built), "ratio": str(ratio),
                "filed_revenue": str(revenue), "filed_margin": str(margin), "filed_shares": str(shares),
                "revenue_change_percent": str((build.revenue / revenue - 1) * 100),
                "margin_change_points": str((build.net_margin - margin) * 100),
                "shares_change_percent": str((build.diluted_shares / shares - 1) * 100),
                "revenue_effect": str(after_revenue - filed.value), "margin_effect": str(after_margin - after_revenue),
                "shares_effect": str(built - after_margin)}


def _build_lines(request: EarningsCase, package) -> tuple[str, ...]:
    parts = earnings_build_parts(request, package)
    if parts is None:
        return ("build: none. The earnings figure is stated, not built from revenue, net margin and share count.",)
    build, built, stated = request.build, Decimal(parts["built_eps"]), request.forecast.value
    if abs(built / stated - 1) > BUILD_TOLERANCE:
        raise ValueError(f"The build gives {built:.2f} a share, not the stated forecast {stated:.2f}; revenue times net "
                         "margin over diluted shares must reproduce the forecast")
    if parts["status"] == "unchecked":
        return (f"build: revenue {build.revenue}, net margin {build.net_margin * 100:.1f}%, diluted shares "
                f"{build.diluted_shares} give {built:.2f} a share. Not set beside the filings: filed net income or "
                "diluted shares for the earnings year are unavailable.",)
    ratio = Decimal(parts["ratio"])
    carried = ("" if abs(ratio - 1) < Decimal("0.005") else
               f" Filed earnings per share were {ratio:.2f} of filed net income per diluted share, and that ratio is kept.")
    return (f"build: revenue {build.revenue} ({Decimal(parts['revenue_change_percent']):+.1f}% on the filed "
            f"{Decimal(parts['filed_revenue']):f}), net margin {build.net_margin * 100:.1f}% (filed "
            f"{Decimal(parts['filed_margin']) * 100:.1f}%), diluted shares {build.diluted_shares} "
            f"({Decimal(parts['shares_change_percent']):+.1f}% on the filed {Decimal(parts['filed_shares']):f}) give "
            f"{built:.2f} a share.{carried}",
            f"build effects on earnings per share from the filed year: revenue {Decimal(parts['revenue_effect']):+.2f}, "
            f"margin {Decimal(parts['margin_effect']):+.2f}, share count {Decimal(parts['shares_effect']):+.2f}.")


def price_earnings_case(request: EarningsCase, package, outlooks):
    """Value a share at forecast diluted EPS times the multiple. Earnings are after interest, so nothing is netted."""
    filed = _fact(package, request.eps_fact_id)
    if filed.metric != "Diluted EPS" or filed.origin != "reported" or not _annual(filed.period_start, filed.period_end) \
            or filed.basis != "US-GAAP":
        raise ValueError("An earnings case needs the filed annual Diluted EPS fact as its baseline")
    if filed.value <= 0:
        raise ValueError("An earnings case needs positive filed annual diluted earnings per share; use a revenue case")
    _forecast_value, warnings = _forecast(request.forecast, package, "Diluted EPS", filed.unit, filed.basis,
                                          _outlooks(package, outlooks), baseline=filed.value)
    if request.multiple_assumption_date != package.as_of or not request.multiple_rationale.strip():
        raise ValueError("Multiple needs the analysis date and a stated rationale")
    # The price the case is compared with is on today's share basis. The filed EPS is on that basis only if the
    # share count has not been split since its year: the filing's own diluted share counts show whether it has.
    def diluted(start, end):
        found = {f.value for f in package.facts if f.metric == "Weighted Average Diluted Shares" and f.value
                 and (f.period_start, f.period_end) == (start, end)}
        return next(iter(found)) if len(found) == 1 else None

    then = diluted(filed.period_start, filed.period_end)
    later = [f for f in package.facts if f.metric == "Weighted Average Diluted Shares" and f.value
             and f.period_start is not None and f.period_end > filed.period_end]
    latest = max(later, key=lambda f: (f.period_end, f.period_start), default=None)
    share_note = "share basis: no later diluted share count is filed to check the earnings year's against."
    if then and latest is not None:
        ratio = latest.value / then
        if not Decimal("0.67") <= ratio <= Decimal("1.5"):
            raise ValueError("Diluted shares changed by more than half since the earnings year; a share split is "
                             "suspected and the filed earnings per share is not on today's share basis")
        share_note = (f"share basis: diluted shares were {then:,.0f} for the earnings year and {latest.value:,.0f} for "
                      f"the period ended {latest.period_end}; no split since the earnings year.")
    balances = [f.period_end for f in package.facts if f.metric == "Cash and Equivalents" and f.value is not None
                and f.period_start is None]
    build_lines = _build_lines(request, package)
    expected = request.forecast.value
    with localcontext() as context:
        context.prec = 60
        target = expected * request.multiple
        change = (expected / filed.value - 1) * 100
    assumptions = (
        f"earnings case: forecast diluted earnings per share {expected} for {request.forecast.period_start} to "
        f"{request.forecast.period_end}, times a multiple of {request.multiple}, gives {target} a share.",
        f"baseline: filed diluted earnings per share {filed.value} for {filed.period_start} to {filed.period_end}; "
        f"the forecast is {change:+.1f}% against it.",
        "no net-debt bridge: earnings are after interest, so cash and borrowings are not netted; a change in the "
        "share count enters only through the analyst's per-share forecast.",
        share_note,
        *build_lines,
    )
    result = TargetResult(
        status="supported", method="earnings_case", target=target, unit=filed.unit, input_fact_ids=(filed.fact_id,),
        capital_snapshot_date=max(balances, default=filed.period_end),
        multiple=request.multiple, earnings_value=expected, eps_basis="diluted",
        multiple_assumption_date=request.multiple_assumption_date,
        valuation_period_start=request.forecast.period_start, valuation_period_end=request.forecast.period_end,
        accounting_basis=request.forecast.basis, assumptions=assumptions, warnings=tuple(warnings),
        decision_use=DecisionUse(classification="forward_scenario", suitability="conditional", final_target_eligible=True))
    return result, {}


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
    # What the case itself retires of each note. A conversion always concerns a note; a debt change names
    # one only when its label says so.
    retired = [(c.instrument, c.converted_principal) for c in capital.share_changes
               if c.source == "conversion" and c.instrument]
    retired += [(c.instrument, -c.amount) for c in capital.cash_changes
                if c.source == "debt" and c.instrument and c.amount < 0 and re.search(r"note|convert", c.instrument, re.I)]
    for note in (terms or {}).get("convertibles") or ():
        try:
            name, principal = str(note["name"])[:80], Decimal(str(note["principal"]))
            matures = date.fromisoformat(str(note["maturity_date"]))
            price = None if note.get("conversion_price") is None else Decimal(str(note["conversion_price"]))
            rate = None if note.get("conversion_rate") is None else Decimal(str(note["conversion_rate"]))
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
        principal -= sum((amount for label, amount in retired if year and year.group() in label), Decimal(0))
        if principal <= 0:
            lines.append(f"{name}: the case states its own repayment or conversion, so code adds nothing.")
        elif price is None or price <= 0:
            lines.append(f"{name}: left open. The filing's conversion price was not read, so the note stays as debt.")
        else:
            # A capped call that has expired by the period end offsets nothing.
            notes.append({"name": name, "principal": principal, "price": price,
                          "rate": rate if rate is not None and rate > 0 else None, "call": call if call and call[2] >= capital.valuation_date else None})
    return notes, lines


def _per_share(equity, shares, converted):
    """Value per share once the converted notes' shares, net of capped-call shares, are counted.

    Each converted note adds its principal at the filed conversion rate (principal / price when the filing
    states no rate). Its capped call returns shares worth the gain between
    the strike and the cap on those same shares. The count depends on the value, so the two are solved together.
    """
    def new_shares(value, note):
        gross = note["principal"] * note["rate"] / 1000 if note.get("rate") else note["principal"] / note["price"]
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
    converted, left, value, counts, unsettled = [], borrowings, equity / shares, [], {}
    for note in sorted(notes, key=lambda n: n["price"]):
        removed = min(note["principal"], left) if left is not None else Decimal(0)
        trial = [*converted, {**note, "removed": removed}]
        trial_value, trial_counts = _per_share(equity + sum(n["removed"] for n in trial), shares, trial)
        if trial_value <= note["price"]:
            # When the basis counts the whole note as debt, both readings agree. When it does not, the value
            # can sit above the price as debt and below it converted: neither holds, and that is said.
            if value > note["price"]:
                unsettled[note["name"]] = trial_value
            continue
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
        if note["name"] in unsettled and value > note["price"]:
            lines.append(f"{note['name']}: left open. As debt the case's value is {value:.2f} a share, above the "
                         f"{note['price']} conversion price; converted it would be {unsettled[note['name']]:.2f}, below it, "
                         "because this basis does not count all of the note as debt. The note stays as debt and the "
                         "value is not settled.")
        elif note["name"] not in done:
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


def scheduled_payments(terms, snapshot_date, end):
    """Finance-lease and equipment payments the filed schedule puts between the snapshot and ``end``.

    Returns (amount or None, whether a schedule dated at the snapshot was retained). A year the table does
    not state is unknown, never zero.
    """
    schedule = (terms or {}).get("schedule")
    years = schedule.get("years") if isinstance(schedule, dict) and schedule.get("as_of") == snapshot_date else None
    first = snapshot_date.year + (snapshot_date == date(snapshot_date.year, 12, 31))  # an ended year needs no column
    if not years or not all(str(year) in years for year in range(first, end.year + 1)):
        return None, bool(years)
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
    return scheduled, True


def states_operations(capital) -> bool:
    """Whether the case gives operating cash flow. Code completes a bridge only from that starting point."""
    return capital.cash_model is not None or any(c.source == "operations" for c in capital.cash_changes)


def bridge_revenue(package, snapshot_date, forecast, currency):
    """Revenue between the filed balance sheet and the forecast's period end, and how it was put together.

    Before the forecast period starts, revenue runs at the latest reported quarter's daily rate; with no such
    quarter in the evidence, at the forecast's own rate. Both are stated assumptions, not filed figures.
    """
    span = (forecast.period_end - forecast.period_start).days + 1
    if snapshot_date >= forecast.period_start:
        left = max((forecast.period_end - snapshot_date).days, 0)
        return forecast.value * left / span, "the case's forecast rate for the rest of its period"
    stub = (forecast.period_start - snapshot_date).days - 1
    quarter = None
    for fact in package.facts:
        if (fact.metric == "Revenue" and fact.period_end == snapshot_date and fact.period_start is not None
                and fact.basis == "US-GAAP" and fact.unit == currency and fact.value is not None and fact.value > 0
                and 80 <= (fact.period_end - fact.period_start).days + 1 <= 100):
            quarter = fact
    last_stub_day = date.fromordinal(forecast.period_start.toordinal() - 1)
    if quarter is None:
        return forecast.value * (stub + span) / span, "the case's forecast rate throughout"
    days = (quarter.period_end - quarter.period_start).days + 1
    return (quarter.value * stub / days + forecast.value,
            f"the latest reported quarter's rate to {last_stub_day}, then the case's forecast")


def model_flows(capital, revenue):
    """Operating cash and capital spending the case's rates give on that revenue, or None without rates."""
    model = capital.cash_model
    if model is None or revenue is None:
        return None
    return {"operations": (model.operating_cash_margin * revenue).quantize(Decimal(1)),
            "capex": (model.capex_rate * revenue).quantize(Decimal(1))}


def filed_cash_rates(package, snapshot_date, currency):
    """What operating cash flow and cash capital spending were as shares of revenue in the latest filed period."""
    found = {}
    for fact in package.facts:
        if (fact.period_end == snapshot_date and fact.period_start is not None and fact.basis == "US-GAAP"
                and fact.unit == currency and fact.value is not None):
            found.setdefault((fact.period_start, fact.metric), fact.value)
    for start in sorted({start for start, _ in found}):       # the longest period ending at the snapshot first
        revenue, cash = found.get((start, "Revenue")), found.get((start, "Operating Cash Flow"))
        capex = found.get((start, "Capital Expenditure"))
        if revenue and revenue > 0 and cash is not None and capex is not None:
            spent = abs(capex) + abs(found.get((start, "Software Development Payments"), Decimal(0)))
            return {"operating_cash_margin": cash / revenue, "capex_rate": spent / revenue,
                    "period": f"{start} to {snapshot_date}"}
    return None


def cash_model_line(capital, flows, revenue, how, filed, snapshot_date) -> str | None:
    """One sentence on the case's operating cash and capital spending against the filed rates."""
    currency, end = capital.currency, capital.valuation_date
    if revenue is None or revenue <= 0:
        return None
    base = f"the {_money(revenue, currency)} of revenue between {snapshot_date} and {end} ({how})"
    history = ("" if filed is None else
               f" In the filed period {filed['period']} they were {filed['operating_cash_margin'] * 100:.1f}% and "
               f"{filed['capex_rate'] * 100:.1f}% (cash capital spending and software).")
    if flows is not None:
        model = capital.cash_model
        return (f"cash model: the analyst's operating cash margin of {model.operating_cash_margin * 100:.1f}% and "
                f"capital spending rate of {model.capex_rate * 100:.1f}%, applied by code to {base}, give operating "
                f"cash of {_signed(flows['operations'], currency)} and capital spending of "
                f"{_signed(-flows['capex'], currency)}.{history} Reasons (unvalidated): "
                f"{model.operating_cash_reason} {model.capex_reason}")
    operations = sum(c.amount for c in capital.cash_changes if c.source == "operations")
    capex = -sum(c.amount for c in capital.cash_changes if c.source == "capex")
    if not any(c.source in ("operations", "capex") for c in capital.cash_changes):
        return None
    line = (f"cash model: the case states amounts, not rates. Operating cash of {_signed(operations, currency)} is "
            f"{operations / revenue * 100:.1f}% of {base}; capital spending of {_signed(-capex, currency)} is "
            f"{capex / revenue * 100:.1f}%.{history}")
    if len(capital.cash_changes) >= 2 and sum(c.amount for c in capital.cash_changes) == 0:
        line += (" The stated cash changes sum to zero, so cash before code's steps equals the filed balance: the "
                 "amounts balance one another and are not an independent forecast.")
    return line


def applied_payments(capital, scheduled) -> Decimal:
    """Scheduled payments code deducts itself: the case states operating cash and no finance payments of its own."""
    if scheduled is None or scheduled <= 0 or not states_operations(capital):
        return Decimal(0)
    return Decimal(0) if any(c.source == "finance_payments" for c in capital.cash_changes) else scheduled


def repaid_notes(capital, opening_borrowings, snapshot_date, terms) -> tuple[Decimal, list[str]]:
    """Notes falling due inside the period that code repays from cash: (amount, names).

    Only for a case that states operating cash, leaves borrowings at or above the filed balance, and neither
    repays nor converts the note itself. Cash and borrowings fall together, so net obligations do not move.
    """
    owed = capital.obligations.get("borrowings")
    if (not states_operations(capital) or owed is None or opening_borrowings is None
            or owed.value < opening_borrowings):
        return Decimal(0), []
    dealt = (-sum(c.amount for c in capital.cash_changes if c.source == "debt" and c.amount < 0)
             + sum(c.converted_principal for c in capital.share_changes if c.source == "conversion"))
    repaid, names = Decimal(0), []
    for name, amount, _ in sorted(_maturing_notes(terms, snapshot_date, capital.valuation_date), key=lambda n: n[2]):
        if dealt >= amount:
            dealt -= amount
            continue
        short, dealt = amount - dealt, Decimal(0)
        short = min(short, owed.value - repaid)
        if short > 0:
            repaid += short
            names.append(name)
    return repaid, names


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
    applied = applied_payments(capital, scheduled_payments(terms, snapshot_date, end)[0])
    if applied:
        # The case gives operating cash and no finance payments, so the filed schedule is deducted for it.
        adjustment -= applied
        stated += applied
        decided.append("payments")
        record["payments_applied"] = str(applied)
        lines.append(f"the case states operating cash and no finance payments, so the {_money(applied, currency)} "
                     f"the filed schedule puts through {end} is deducted ({applied / shares:.2f} {currency} a share)")
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
    currency, end = capital.currency, capital.valuation_date
    stated = -sum(c.amount for c in capital.cash_changes if c.source == "finance_payments")
    reasons = []
    scheduled, years = scheduled_payments(terms, snapshot_date, end)
    by_code = applied_payments(capital, scheduled) if counts_cash else Decimal(0)
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
    elif scheduled - stated - by_code > scheduled * FUNDING_TOLERANCE:
        reasons.insert(0, (f"Scheduled finance and equipment payments of {_money(scheduled, currency)} through {end} "
                           "are not stated in the case's cash changes." if stated <= 0 else
                           f"Scheduled finance and equipment payments are {_money(scheduled, currency)} through {end}; "
                           f"the case states {_money(stated, currency)}."))
    status = "unassessed" if scheduled is None else ("partial" if reasons else "assessed")
    summary = (f"Scheduled payments covered: finance and equipment payments of {_money(scheduled, currency)} through {end} "
               + ("are deducted by code from the filed schedule" if by_code else "are stated")
               + " and maturing notes are accounted for." if status == "assessed"
               else f"Funding {status}: " + " ".join(reasons))
    # What the schedule covers is filed; what the business earns and spends is not.
    summary += (" Operating cash flow and capital spending are the analyst's assumptions, not filed figures or guidance."
                if capital.cash_model is not None or any(c.source in ("operations", "capex") for c in capital.cash_changes)
                else " The case states no operating cash flow or capital spending.")
    bounds = funding_bounds(capital, snapshot_date, scheduled, terms, stated) if counts_cash else {}
    funded = funded_cash(capital, snapshot_date, terms) if counts_cash else None
    return {"status": status, **({"funded": funded} if funded and (funded["decided"] or funded["unsized"]) else {}), "scheduled_finance_payments": None if scheduled is None else str(scheduled),
            "stated_finance_payments": str(stated), "maturing_note_principal": str(principal),
            "reasons": reasons, "summary": summary, "bounds": bounds,
            "limit": funding_limit(bounds, currency, counts_cash, funded)}


STATEMENT = "funded statement: "
_LINE_NAMES = {"borrowings": "borrowings", "finance_equipment": "finance leases and equipment",
               "finance_leases": "finance leases", "equipment": "equipment financing",
               "operating_leases": "operating leases"}


def _signed(value, currency):
    return ("+" if value >= 0 else "-") + _money(abs(value), currency)


def _maturing_notes(terms, snapshot_date, end):
    """Retained notes whose principal falls due inside the period: (name, amount, date)."""
    found = []
    for note in (terms or {}).get("notes") or ():
        if not isinstance(note, dict) or not isinstance(note.get("name"), str):
            continue
        try:
            matures = date.fromisoformat(str(note.get("maturity_date")))
            scale = _NOTE_SCALE.get(note.get("principal_unit"))
            if scale is None or not snapshot_date < matures <= end:
                continue
            found.append((note["name"][:80], Decimal(str(note.get("principal_outstanding"))) * scale, matures))
        except (ValueError, ArithmeticError):
            continue
    return found


def shortfall_statement(closing_cash, investments, shares, value, currency) -> str | None:
    """What a case that ends short of cash is said to mean; None when it does not end short.

    The case arithmetic nets a shortfall as an obligation. That gives the same value per share as selling
    shares at the case's own value to cover it, which is said here with the count. Nothing is changed.
    """
    if closing_cash >= 0 or value <= 0 or shares <= 0:
        return None
    gap = -closing_cash
    sold = gap / value
    text = (f"cash shortfall: the case ends {_money(gap, currency)} short of cash and states no funding for it. Code "
            "leaves the shortfall in net obligations, which gives the same value per share as selling "
            f"{sold:,.0f} shares at the case's own value to cover it ({sold / shares * 100:.2f}% more shares) or "
            "borrowing it at no cost. ")
    if investments is None or investments <= 0:
        return text + "No current investments are filed to draw on: it needs new financing, share sales or lower spending."
    if investments >= gap:
        return (text + f"The filed current investments of {_money(investments, currency)} would cover it "
                f"{investments / gap:.1f} times; they are not counted in this case's cash.")
    return (text + f"The filed current investments of {_money(investments, currency)} would cover "
            f"{_money(investments, currency)} of it; the remaining {_money(gap - investments, currency)} needs new "
            "financing, share sales or lower spending.")


def funded_statement(capital, snapshot_date, opening, funded, carried, settled, basis, capitalized, net, terms,
                     unstated=(), repaid=Decimal(0), flows=None) -> list[str]:
    """One statement per case: each balance from the filing to the period end, and who supplied each step.

    `opening` holds the filed snapshot balances; `net` is the basis's net obligations before any converted
    debt is removed (None on an equity basis). Nothing here changes a value: every figure is one the case
    arithmetic already used, laid out so a reader can see what is filed, what the analyst assumes and what
    code computes under a stated assumption.
    """
    currency, end = capital.currency, capital.valuation_date
    counted = set(obligation_bases(capital.obligations).get(basis, ())) if basis != "equity" else set()
    lines = [f"from the {snapshot_date} filing to {end}. Each line gives the opening balance as filed, what the "
             "analyst assumes, what code computes under a stated assumption, and the closing balance."]
    # Cash.
    stated = [f"{c.source.replace('_', ' ')} {_signed(c.amount, currency)}" for c in capital.cash_changes]
    if flows is not None:
        stated += [f"operations {_signed(flows['operations'], currency)} and capex {_signed(-flows['capex'], currency)} "
                   "(the analyst's rates, applied by code to the case's revenue)"]
    code = []
    if funded.get("payments_applied"):
        code.append(f"scheduled finance and equipment payments deducted {_signed(-Decimal(funded['payments_applied']), currency)}")
    if repaid:
        code.append(f"notes falling due repaid {_signed(-repaid, currency)}")
    if funded.get("interest_added_back"):
        code.append(f"lease interest already inside operating cash added back {_signed(Decimal(funded['interest_added_back']), currency)}")
    if funded.get("rent_deducted"):
        code.append(f"rent on leases that commence deducted {_signed(-Decimal(funded['rent_deducted']), currency)}")
    closing_cash = capital.cash.value + Decimal(funded["adjustment"]) - repaid
    if flows is not None:
        closing_cash += flows["operations"] - flows["capex"]
    lines.append(f"cash: opening {_money(opening['cash'], currency)} (filed); analyst: "
                 + ("; ".join(stated) if stated else "no change stated") + "; code: "
                 + ("; ".join(code) if code else "no change") + f"; closing {_money(closing_cash, currency)}"
                 + ("" if basis != "equity" else "; this equity basis does not use cash") + ".")
    # Obligations.
    for category, item in capital.obligations.items():
        start, analyst, code, closing = opening[category], "no change stated", [], item.value
        if item.assumption == "estimated" and item.value != start:
            analyst = f"closing set to {_money(item.value, currency)} ({_signed(item.value - start, currency)})"
        elif item.assumption == "estimated":
            analyst = "closing estimated at the filed balance"
        if category in carried:
            closing = carried[category]["value"]
            how = ("the filed payment schedule" if category in LEASE_FINANCE
                   else "leases that commence in the period added")
            code.append(f"carried to the period end on {how} {_signed(closing - item.value, currency)}")
        if category == "borrowings" and repaid:
            closing -= repaid
            code.append(f"notes falling due repaid {_signed(-repaid, currency)}")
        if category == "borrowings" and category in counted and settled["debt_removed"]:
            closing -= settled["debt_removed"]
            code.append(f"converted notes leave borrowings {_signed(-settled['debt_removed'], currency)}")
        lines.append(f"{_LINE_NAMES.get(category, category)}: opening {_money(start, currency)} (filed); analyst: "
                     f"{analyst}; code: " + ("; ".join(code) if code else "no change")
                     + f"; closing {_money(closing, currency)}"
                     + ("." if category in counted else
                        f"; outside this case's {basis.replace('_', ' ')} basis, used in the sensitivities only."))
    # Shares.
    stated = [f"{c.source} {'+' if c.shares >= 0 else '-'}{abs(c.shares):,.0f}" for c in capital.share_changes]
    added = settled["shares"] - capital.closing_shares.value
    lines.append(f"shares: opening {opening['closing_shares']:,.0f} (filed); analyst: "
                 + ("; ".join(stated) if stated else "no change stated") + "; code: "
                 + (f"notes converted, net of any capped call +{added:,.0f}" if added else "no change")
                 + f"; closing {settled['shares']:,.0f}.")
    # Value.
    if basis == "equity":
        lines.append(f"value: revenue times the multiple is {_money(capitalized, currency)} of equity value, over "
                     f"{settled['shares']:,.0f} shares, {settled['value']:.2f} a share.")
    else:
        owed = net - settled["debt_removed"]
        lines.append(f"value: revenue times the multiple is {_money(capitalized, currency)}; less net obligations of "
                     f"{_signed(owed, currency)} (the closing {', '.join(_LINE_NAMES.get(c, c) for c in capital.obligations if c in counted)} "
                     f"above less closing cash); equity value {_money(capitalized - owed, currency)} over "
                     f"{settled['shares']:,.0f} shares, {settled['value']:.2f} a share.")
    # What the filing schedules inside the period and the case does not state.
    open_items = [str(reason) for reason in unstated]
    filed_debt, owed_debt = opening.get("borrowings"), capital.obligations.get("borrowings")
    dealt = repaid + (-sum(c.amount for c in capital.cash_changes if c.source == "debt" and c.amount < 0)
                      + sum(c.converted_principal for c in capital.share_changes if c.source == "conversion"))
    # Earliest first, and what the case repays or converts is used once, so one repayment never covers two notes.
    for name, amount, matures in sorted(_maturing_notes(terms, snapshot_date, end), key=lambda note: note[2]):
        if dealt >= amount:
            dealt -= amount
            continue
        short, dealt = amount - dealt, Decimal(0)
        if filed_debt is not None and owed_debt is not None and owed_debt.value >= filed_debt:
            open_items.append(f"{name}: {_money(short, currency)} of principal falls due {matures}, inside the period. "
                              "The case states no repayment of it and leaves it in borrowings; if it is repaid from "
                              "cash, cash and borrowings both fall by that amount and net obligations are unchanged.")
    lines.append("not stated by the case: " + " ".join(open_items) if open_items else
                 "nothing the filing schedules inside the period is left unstated by the case.")
    return [STATEMENT + line for line in lines]


def unstated_lease_lines(opening: dict, closing: dict, currency, basis) -> list[str]:
    """Statement lines for filed lease balances a case leaves out: category -> filed opening and carried closing."""
    lines = []
    for category, start in opening.items():
        end = closing[category]
        how = "the filed payment schedule" if category in LEASE_FINANCE else "leases that commence in the period added"
        code = "held as filed" if end == start else f"carried to the period end on {how} {_signed(end - start, currency)}"
        lines.append(f"{STATEMENT}{_LINE_NAMES.get(category, category)}: opening {_money(start, currency)} (filed); "
                     f"analyst: not stated in this case; code: {code}; closing {_money(end, currency)}; outside this "
                     f"case's {basis.replace('_', ' ')} basis, used in the sensitivities only.")
    return lines


def with_lease_lines(assumptions, lines) -> tuple:
    """The assumptions with those lines placed after the statement's last balance line and before its shares line."""
    at = next((i for i, text in enumerate(assumptions) if text.startswith(STATEMENT + "shares:")), None)
    return tuple(assumptions) if at is None or not lines else (*assumptions[:at], *lines, *assumptions[at:])


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
    counted = shares.origin == "reported" or shares.formula_id in {"shares_issued_less_treasury_v1",
                                                                    "cover_count_after_balance_v1"}
    if (shares.metric != "Common Shares Outstanding" or shares.unit != "shares" or not counted
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
        if any(f.metric == "Total Borrowings Including Finance Leases" for f in refs["borrowings"]):
            warnings.append("Borrowings are as the filing presents them: the filer states its debt together with its "
                            "finance leases, so this basis includes them.")
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
        # Operating cash and capital spending given as rates become amounts on this case's own revenue.
        between, how = bridge_revenue(package, cash.period_end, request.forecast, capital.currency)
        flows = model_flows(capital, between)
        if flows is not None:
            closing_cash += flows["operations"] - flows["capex"]
        # A lease balance supplied as filed is carried to the period end like one the case leaves out.
        carried = carry_leases({k: v.value for k, v in obligations.items()
                                if k != "borrowings" and v.assumption == "unchanged_from_snapshot"},
                               cash.period_end, capital.valuation_date, terms)
        owed = {k: carried[k]["value"] if k in carried else v.value for k, v in obligations.items()}
        # A note falling due inside the period that the case leaves untouched is repaid from cash by code.
        repaid, repaid_names = repaid_notes(
            capital, sum(f.value for f in refs["borrowings"]) if "borrowings" in refs else None, cash.period_end, terms)
        if repaid:
            closing_cash -= repaid
            owed["borrowings"] -= repaid
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
            sales = [c for c in capital.share_changes if c.source == "atm"]
            if any(c.price is not None for c in sales):
                if any(c.price is None for c in sales):
                    raise ValueError("Every atm share change needs a price when one states it")
                # Proceeds are after costs: never above shares times price, and within a tenth of it.
                gross = sum(c.shares * c.price for c in sales)
                if atm_cash > gross * (1 + FUNDING_TOLERANCE):
                    raise ValueError(f"ATM proceeds of {atm_cash} are more than shares times the stated price ({gross})")
                if atm_cash < gross * Decimal("0.9"):
                    raise ValueError(f"ATM proceeds of {atm_cash} are less than nine tenths of shares times the stated price ({gross})")
                stated = " and ".join(sorted({str(c.price) for c in sales}))
                assumptions.append(f"share sales: checked by code. {atm_shares:,.0f} shares at a stated {stated} a share is "
                                   f"{gross:,.0f} before costs; the case takes in {atm_cash:,.0f}, costs of "
                                   f"{(1 - atm_cash / gross) * 100:.1f}%. This case's value is {settled['value']:.2f} a share.")
            else:
                assumptions.append(f"share sales: {atm_shares:,.0f} shares for {atm_cash:,.0f} of cash is "
                                   f"{atm_cash / atm_shares:.2f} a share after costs; no sale price is stated to check "
                                   f"it against. This case's value is {settled['value']:.2f} a share.")
        else:
            assumptions.append("share sales: not applicable; the case states none.")
        assumptions.extend(f"convertible notes: {line}" for line in (*settled["lines"], *note_lines))
        if not isinstance((terms or {}).get("convertibles"), list):
            assumptions.append("convertible notes: not read from a filing for this case.")
        elif not settled["lines"] and not note_lines:
            assumptions.append("convertible notes: not applicable; none is outstanding at the period end.")
        if settled["lines"]:
            assumptions.append("convertible notes: " + CONVERSION + " A capped call covering notes already repurchased is not valued.")
        modelled = cash_model_line(capital, flows, between, how,
                                   filed_cash_rates(package, cash.period_end, capital.currency), cash.period_end)
        if modelled and request.multiple_basis != "equity":
            assumptions.append(modelled)
        if request.multiple_basis != "equity" and (Decimal(funded["adjustment"]) or repaid or flows):
            assumptions.append(f"cash completed by code: {closing_cash} (stated {capital.cash.value}, adjustment "
                               f"{closing_cash - capital.cash.value:+}). " + "; ".join(
                                   [*funded["lines"], *([f"{' and '.join(repaid_names)} falling due inside the period "
                                                         f"repaid from cash, {_money(repaid, capital.currency)}, and "
                                                         "removed from borrowings"] if repaid else [])]) + ".")
        counted_shares = refs["closing_shares"][0]
        if counted_shares.formula_id == "cover_count_after_balance_v1":
            by_id = {f.fact_id: f for f in package.facts}
            cover, average = (by_id[i] for i in counted_shares.input_fact_ids)
            assumptions.append(
                f"share count: {counted_shares.value:,.0f} is the filing's cover-page count dated {cover.period_end}, "
                f"used for the {counted_shares.period_end} balance date because the filing tags no count at that date; "
                f"the filing's average count for the period ending then is {average.value:,.0f}.")
        # Investments the filing presents within current assets are not in the case's cash. Said beside the value,
        # not added to it: the history a multiple is chosen against nets cash only.
        held = [f for f in package.facts if f.metric == "Current Marketable Securities" and f.value is not None
                and f.period_start is None and f.period_end == cash.period_end and f.unit == capital.currency and f.value > 0]
        if request.multiple_basis != "equity" and len(held) == 1:
            assumptions.append(
                f"current investments: {_money(held[0].value, capital.currency)} filed as of "
                f"{cash.period_end} are not counted in cash; counted as cash at that amount they would add "
                f"{held[0].value / settled['shares']:.2f} a share.")
        short = (shortfall_statement(closing_cash, held[0].value if len(held) == 1 else None, settled["shares"],
                                     settled["value"], capital.currency) if request.multiple_basis != "equity" else None)
        if short:
            assumptions.append(short)
        funding = case_funding(request, package, terms)
        assumptions.extend(funded_statement(
            capital, cash.period_end, {label: sum(f.value for f in facts) for label, facts in refs.items()},
            funded, carried, settled, request.multiple_basis, capitalized, net.get(request.multiple_basis), terms,
            unstated=funding["reasons"], repaid=repaid, flows=flows))
        result = TargetResult(status="supported", method="revenue_case", target=settled["value"],
            unit=capital.currency + "/shares", input_fact_ids=(revenue.fact_id, *ids), capital_snapshot_date=cash.period_end,
            shares_outstanding=settled["shares"], multiple=request.multiple,
            net_obligations=(None if request.multiple_basis == "equity"
                             else net[request.multiple_basis] - settled["debt_removed"]),
            multiple_assumption_date=request.multiple_assumption_date,
            valuation_period_start=request.forecast.period_start, valuation_period_end=request.forecast.period_end,
            accounting_basis=request.forecast.basis, assumptions=tuple(assumptions),
            warnings=(*warnings, "{summary} {limit}".format(**funding)),
            decision_use=DecisionUse(classification="forward_scenario", suitability="conditional", final_target_eligible=True))
        return result, sensitivities
