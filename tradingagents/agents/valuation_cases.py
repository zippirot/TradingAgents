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
    instrument: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def _principal_matches_source(self):
        if (self.source == "conversion") != (self.converted_principal is not None):
            raise ValueError("converted_principal is required for a conversion and only for a conversion")
        return self


class CashChange(_Record):
    source: Literal["atm", "operations", "debt", "other"]
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


def price_case(request, package, outlooks):
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
            assumptions.append(f"share change ({change.source}, {change.instrument}): {change.shares}. Reason: {change.reason}")
        for change in capital.cash_changes:
            assumptions.append(f"cash change ({change.source}): {change.amount}. Reason: {change.reason}")
        result = TargetResult(status="supported", method="revenue_case", target=equity / capital.closing_shares.value,
            unit=capital.currency + "/shares", input_fact_ids=(revenue.fact_id, *ids), capital_snapshot_date=cash.period_end,
            shares_outstanding=capital.closing_shares.value, multiple=request.multiple,
            net_obligations=net.get(request.multiple_basis), multiple_assumption_date=request.multiple_assumption_date,
            valuation_period_start=request.forecast.period_start, valuation_period_end=request.forecast.period_end,
            accounting_basis=request.forecast.basis, assumptions=tuple(assumptions),
            warnings=(*warnings, "Funding feasibility unassessed. No cash plug or discounting."),
            decision_use=DecisionUse(classification="forward_scenario", suitability="conditional", final_target_eligible=True))
        return result, sensitivities
