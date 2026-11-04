"""Small deterministic, conditional valuation bridges.

Source facts establish historical inputs. Forecasts, multiples and scenario
weights remain explicit assumptions; successful arithmetic is not a verified
prediction. GroundedOutlook must come from the caller's validated disclosure
extraction, never from the model's target request.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from tradingagents.agents.accounting_checks import calculate_obligations
from tradingagents.dataflows.financial_evidence import EvidencePackage

Basis = Literal["US-GAAP", "management-adjusted"]
Perimeter = Literal["borrowings_only", "finance_equipment", "all_leases"]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ForecastAssumption(_Record):
    value: Decimal = Field(gt=0, max_digits=40)
    unit: str = Field(min_length=1, max_length=16)
    period_start: date
    period_end: date
    basis: Basis
    kind: Literal["analyst_forecast", "management_guidance", "management_ambition"]
    rationale: str = Field(min_length=1, max_length=1200)
    outlook_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def duration(self):
        if self.period_start > self.period_end:
            raise ValueError("forecast period is reversed")
        if not self.rationale.strip():
            raise ValueError("forecast rationale is blank")
        if self.kind != "analyst_forecast" and not self.outlook_id:
            raise ValueError("management forecast needs grounded outlook reference")
        return self


class GroundedOutlook(_Record):
    record_id: str = Field(min_length=1, max_length=128)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    metric: Literal["Revenue", "Basic EPS", "Diluted EPS"]
    unit: str = Field(min_length=1, max_length=16)
    period_start: date
    period_end: date
    basis: Basis
    low: Decimal = Field(max_digits=40)
    high: Decimal = Field(max_digits=40)
    kind: Literal["guidance", "ambition"]

    @model_validator(mode="after")
    def interval(self):
        if self.low > self.high or self.period_start > self.period_end:
            raise ValueError("outlook interval or period reversed")
        return self


class RevenueScenario(_Record):
    name: str = Field(min_length=1, max_length=80)
    weight: Decimal = Field(ge=0, le=1, max_digits=16)
    forecast: ForecastAssumption
    multiple: Decimal = Field(gt=0, max_digits=20)
    multiple_rationale: str = Field(min_length=1, max_length=1200)


class EVRevenueTarget(_Record):
    method: Literal["ev_revenue"] = "ev_revenue"
    revenue_fact_id: str
    shares_fact_id: str
    cash_fact_id: str
    obligation_ids_by_category: dict[str, tuple[str, ...]]
    perimeter: Perimeter
    multiple_perimeter: Perimeter
    capital_structure_assumption: Literal["unchanged_from_snapshot"]
    capital_structure_rationale: str = Field(min_length=1, max_length=1200)
    scenarios: tuple[RevenueScenario, ...] = Field(min_length=1, max_length=5)


class PETarget(_Record):
    method: Literal["pe"] = "pe"
    eps_fact_id: str
    eps_basis: Literal["basic", "diluted"]
    accounting_basis: Basis
    multiple: Decimal = Field(gt=0, max_digits=20)
    multiple_rationale: str = Field(min_length=1, max_length=1200)
    forecast: ForecastAssumption | None = None


class ScenarioResult(_Record):
    name: str
    weight: Decimal
    revenue: Decimal
    multiple: Decimal
    enterprise_value: Decimal
    equity_value: Decimal
    price: Decimal
    forecast_period_start: date
    forecast_period_end: date


class TargetResult(_Record):
    status: Literal["supported", "unsupported"]
    target: Decimal | None = None
    unit: str | None = None
    method: str | None = None
    input_fact_ids: tuple[str, ...] = ()
    scenario_results: tuple[ScenarioResult, ...] = ()
    valuation_period_start: date | None = None
    valuation_period_end: date | None = None
    capital_snapshot_date: date | None = None
    net_obligations: Decimal | None = None
    shares_outstanding: Decimal | None = None
    multiple: Decimal | None = None
    earnings_value: Decimal | None = None
    accounting_basis: Basis | None = None
    eps_basis: Literal["basic", "diluted"] | None = None
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


def _fact(package, identifier):
    fact = next((f for f in package.facts if f.fact_id == identifier), None)
    if fact is None or fact.value is None or not fact.value.is_finite():
        raise ValueError("required source fact unavailable")
    if not fact.source_ids:
        raise ValueError("required fact lacks source provenance")
    return fact


def _annual(start, end):
    return start is not None and 330 <= (end - start).days + 1 <= 400


def _outlooks(package, outlooks):
    if len(outlooks) > 30:
        raise ValueError("grounded outlook limit exceeded")
    sources = {source.source_id for source in package.sources}
    validated = tuple(
        GroundedOutlook.model_validate(o.model_dump() if isinstance(o, GroundedOutlook) else o)
        for o in outlooks
    )
    if len({o.record_id for o in validated}) != len(validated):
        raise ValueError("ambiguous grounded outlook identifier")
    if any(not set(o.source_ids) <= sources for o in validated):
        raise ValueError("grounded outlook has missing package source")
    return validated


def _forecast(assumption, package, metric, unit, basis, outlooks):
    if (assumption.unit, assumption.basis) != (unit, basis):
        raise ValueError("forecast unit or accounting basis differs from source measure")
    if not _annual(assumption.period_start, assumption.period_end):
        raise ValueError("valuation forecast must be an explicit annual period")
    if assumption.period_end <= package.as_of:
        raise ValueError("forward forecast period must extend after analysis cutoff")
    matching = [
        o
        for o in outlooks
        if (o.metric, o.unit, o.basis, o.period_start, o.period_end)
        == (metric, unit, basis, assumption.period_start, assumption.period_end)
    ]
    if assumption.kind != "analyst_forecast":
        candidate = next((o for o in matching if o.record_id == assumption.outlook_id), None)
        expected_kind = "guidance" if assumption.kind == "management_guidance" else "ambition"
        if (
            candidate is None
            or candidate.kind != expected_kind
            or not candidate.low <= assumption.value <= candidate.high
        ):
            raise ValueError(
                "management forecast does not match grounded outlook kind, period or range"
            )
    warnings = []
    if not matching:
        warnings.append(
            f"Same-period management outlook unavailable for {metric}; no consensus assumed."
        )
    for outlook in matching:
        if assumption.value > outlook.high:
            warnings.append(
                f"{metric} forecast {assumption.value} is above management {outlook.kind} range {outlook.low}–{outlook.high} for {outlook.period_end}; unvalidated rationale: {assumption.rationale}"
            )
        elif assumption.value < outlook.low:
            warnings.append(
                f"{metric} forecast {assumption.value} is below management {outlook.kind} range {outlook.low}–{outlook.high} for {outlook.period_end}; unvalidated rationale: {assumption.rationale}"
            )
        else:
            warnings.append(
                f"{metric} forecast lies within management {outlook.kind} range for {outlook.period_end}; this does not verify the forecast."
            )
    description = f"{assumption.kind} {metric} forecast: {assumption.value} {unit}, {assumption.period_start} to {assumption.period_end}, {basis}. Unvalidated rationale: {assumption.rationale}"
    return description, warnings


def _borrowings_complete(package, ids):
    metrics = {_fact(package, identifier).metric for identifier in ids}
    if metrics == {"Total Borrowings"}:
        return
    long_term = {"Long-term Borrowings (including current)"}
    split_long_term = {"Current Long-term Borrowings", "Noncurrent Long-term Borrowings"}
    if metrics not in (
        long_term | {"Short-term Borrowings"},
        split_long_term | {"Short-term Borrowings"},
    ):
        raise ValueError(
            "borrowing perimeter requires sourced total or complete short/long-term components"
        )


def _ev(request, package, outlooks):
    if request.perimeter != request.multiple_perimeter:
        raise ValueError("multiple and equity bridge use incompatible lease perimeters")
    if not request.capital_structure_rationale.strip():
        raise ValueError("unchanged capital structure needs an explicit rationale")
    revenue = _fact(package, request.revenue_fact_id)
    shares = _fact(package, request.shares_fact_id)
    cash = _fact(package, request.cash_fact_id)
    if (
        revenue.metric != "Revenue"
        or not _annual(revenue.period_start, revenue.period_end)
        or revenue.value <= 0
    ):
        raise ValueError("EV/revenue needs a source-backed annual revenue baseline")
    if revenue.basis != "US-GAAP" or not re_currency(revenue.unit):
        raise ValueError("revenue accounting basis or currency unsupported")
    if (
        shares.metric != "Common Shares Outstanding"
        or shares.origin != "reported"
        or shares.unit != "shares"
        or shares.period_start is not None
        or shares.value <= 0
    ):
        raise ValueError("equity per-share bridge requires positive common shares outstanding")
    if cash.metric != "Cash and Equivalents" or cash.period_start is not None or cash.value < 0:
        raise ValueError("equity bridge requires unrestricted instant cash")
    if (
        cash.unit != revenue.unit
        or cash.period_end != shares.period_end
        or cash.basis != shares.basis
        or cash.basis != "US-GAAP"
    ):
        raise ValueError("cash, shares or revenue have incompatible units, basis or snapshot dates")
    categories = set(request.obligation_ids_by_category)
    required = {"borrowings"}
    if request.perimeter != "borrowings_only":
        required |= (
            {"finance_equipment"}
            if "finance_equipment" in categories
            else {"finance_leases", "equipment"}
        )
    if request.perimeter == "all_leases":
        required.add("operating_leases")
    if categories != required:
        raise ValueError("missing or extra obligation category changes declared perimeter")
    if any(not ids or len(ids) > 4 for ids in request.obligation_ids_by_category.values()):
        raise ValueError("empty or oversized obligation category")
    _borrowings_complete(package, request.obligation_ids_by_category["borrowings"])
    calculations = calculate_obligations(
        package, request.obligation_ids_by_category, request.cash_fact_id
    )
    selected = calculations[
        {"borrowings_only": 0, "finance_equipment": 1, "all_leases": 2}[request.perimeter]
    ]
    if selected.status != "pass" or selected.result is None:
        raise ValueError("debt/cash bridge has missing, overlapping or incompatible source inputs")
    if selected.unit != revenue.unit:
        raise ValueError("net obligations and revenue currency mismatch")
    with localcontext() as context:
        context.prec = 60
        if sum((s.weight for s in request.scenarios), Decimal(0)) != 1:
            raise ValueError("subjective scenario weights must sum exactly to one")
    if len({s.name for s in request.scenarios}) != len(request.scenarios):
        raise ValueError("scenario names must be distinct")
    periods = {(s.forecast.period_start, s.forecast.period_end) for s in request.scenarios}
    if len(periods) != 1:
        raise ValueError("weighted scenarios must use the same forecast period")
    assumptions = [
        f"Capital structure unchanged from {cash.period_end}. Unvalidated rationale: {request.capital_structure_rationale}",
        f"EV/revenue multiple and equity bridge use {request.perimeter}.",
        "Scenario weights and valuation multiples are subjective assumptions, not calibrated probabilities or verified market fair values.",
    ]
    warnings, results = [], []
    for scenario in request.scenarios:
        if not scenario.multiple_rationale.strip():
            raise ValueError("scenario multiple needs an explicit rationale")
        description, comparisons = _forecast(
            scenario.forecast, package, "Revenue", revenue.unit, revenue.basis, outlooks
        )
        assumptions.extend(
            (
                f"{scenario.name}: {description}",
                f"{scenario.name} multiple {scenario.multiple}. Unvalidated rationale: {scenario.multiple_rationale}",
            )
        )
        warnings.extend(comparisons)
        with localcontext() as context:
            context.prec = 60
            ev = scenario.forecast.value * scenario.multiple
            equity = ev - selected.result
            price = equity / shares.value
        if not price.is_finite() or price < 0:
            raise ValueError("equity bridge produces a negative or nonfinite target")
        results.append(
            ScenarioResult(
                name=scenario.name,
                weight=scenario.weight,
                revenue=scenario.forecast.value,
                multiple=scenario.multiple,
                enterprise_value=ev,
                equity_value=equity,
                price=price,
                forecast_period_start=scenario.forecast.period_start,
                forecast_period_end=scenario.forecast.period_end,
            )
        )
    with localcontext() as context:
        context.prec = 60
        target = sum((scenario.weight * scenario.price for scenario in results), Decimal(0))
    return TargetResult(
        status="supported",
        target=target,
        unit=revenue.unit + "/shares",
        method=request.method,
        input_fact_ids=tuple(
            dict.fromkeys((revenue.fact_id, shares.fact_id, *selected.input_fact_ids))
        ),
        scenario_results=tuple(results),
        valuation_period_start=request.scenarios[0].forecast.period_start,
        valuation_period_end=request.scenarios[0].forecast.period_end,
        capital_snapshot_date=cash.period_end,
        net_obligations=selected.result,
        shares_outstanding=shares.value,
        accounting_basis=revenue.basis,
        assumptions=tuple(assumptions),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def re_currency(unit):
    return len(unit) == 3 and unit.isascii() and unit.isalpha() and unit.isupper()


def _pe(request, package, outlooks):
    eps = _fact(package, request.eps_fact_id)
    expected_metric = "Basic EPS" if request.eps_basis == "basic" else "Diluted EPS"
    parts = eps.unit.split("/")
    if (
        eps.metric != expected_metric
        or eps.basis != request.accounting_basis
        or eps.origin != "reported"
    ):
        raise ValueError("EPS share basis or accounting basis differs from requested multiple")
    if len(parts) != 2 or not re_currency(parts[0]) or parts[1] != "shares":
        raise ValueError("P/E requires reported currency-per-share EPS")
    if not _annual(eps.period_start, eps.period_end):
        raise ValueError(
            "P/E requires an annual EPS baseline; quarterly EPS cannot be annualized implicitly"
        )
    if request.forecast is None and eps.value <= 0:
        raise ValueError("Historical P/E requires positive reported EPS")
    if not request.multiple_rationale.strip():
        raise ValueError("earnings multiple needs an explicit rationale")
    value = eps.value
    assumptions = [
        f"Subjective {request.eps_basis} {request.accounting_basis} earnings multiple {request.multiple}. Unvalidated rationale: {request.multiple_rationale}"
    ]
    warnings = []
    if request.forecast is not None:
        description, warnings = _forecast(
            request.forecast, package, expected_metric, eps.unit, eps.basis, outlooks
        )
        assumptions.append(description)
        value = request.forecast.value
    else:
        warnings.append(
            f"P/E uses historical reported EPS for {eps.period_start} to {eps.period_end}; it is not a forward earnings forecast."
        )
    with localcontext() as context:
        context.prec = 60
        target = value * request.multiple
    if not target.is_finite() or target < 0:
        raise ValueError("earnings multiple produces a negative or nonfinite target")
    return TargetResult(
        status="supported",
        target=target,
        unit=eps.unit,
        method=request.method,
        input_fact_ids=(eps.fact_id,),
        valuation_period_start=request.forecast.period_start
        if request.forecast
        else eps.period_start,
        valuation_period_end=request.forecast.period_end if request.forecast else eps.period_end,
        multiple=request.multiple,
        earnings_value=value,
        accounting_basis=request.accounting_basis,
        eps_basis=request.eps_basis,
        assumptions=tuple(assumptions),
        warnings=tuple(warnings),
    )


def validate_target(raw, package: EvidencePackage, outlooks=()) -> TargetResult:
    """Invalid targets become null with reasons; never retain model numeric output."""
    try:
        package = EvidencePackage.model_validate(package.model_dump())
        outlooks = _outlooks(package, tuple(outlooks))
        if isinstance(raw, (EVRevenueTarget, PETarget)):
            raw = raw.model_dump()
        if not isinstance(raw, dict):
            raise ValueError("no supported structured target provided")
        if raw.get("method") == "ev_revenue":
            request = EVRevenueTarget.model_validate(raw)
            return _ev(request, package, outlooks)
        if raw.get("method") == "pe":
            request = PETarget.model_validate(raw)
            return _pe(request, package, outlooks)
        raise ValueError("unsupported target method; numeric target omitted")
    except ValidationError as exc:
        error = exc.errors(include_input=False)[0]
        path = ".".join(str(part) for part in error["loc"])
        reason = f"Invalid target/source contract at {path or 'root'} ({error['type']}); numeric target omitted"
    except (ValueError, TypeError, ArithmeticError) as exc:
        reason = str(exc)
    return TargetResult(status="unsupported", reasons=(reason,))
