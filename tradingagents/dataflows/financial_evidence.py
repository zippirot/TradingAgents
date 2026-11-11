"""Immutable, JSON-safe financial evidence and bounded period arithmetic.

Numbers remain Decimal values internally and decimal strings in JSON. These
records establish provenance and arithmetic, not the truth of free-form prose.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    cik: str
    url: str
    filed_date: date
    retrieved_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: str
    accession: str | None = None
    form: str


class FinancialFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    fact_id: str
    metric: str
    value: Decimal | None
    unit: str
    cik: str
    period_start: date | None = None
    period_end: date
    as_of: date
    basis: str = "US-GAAP"
    source_ids: tuple[str, ...] = ()
    locator: str
    origin: Literal["reported", "derived"] = "reported"
    missing_reason: str | None = None
    input_fact_ids: tuple[str, ...] = ()
    formula_id: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.period_end > self.as_of:
            raise ValueError("fact period ends after the evidence cutoff")
        if self.period_start and self.period_start > self.period_end:
            raise ValueError("fact period is reversed")
        if self.value is None and not self.missing_reason:
            raise ValueError("missing facts require an explicit reason")
        if self.value is not None and (not self.source_ids or self.missing_reason):
            raise ValueError("reported values need sources and cannot be missing")
        if self.origin == "derived" and (not self.formula_id or not self.input_fact_ids):
            raise ValueError("derived facts require formula and input lineage")
        if self.origin == "reported" and (self.formula_id or self.input_fact_ids):
            raise ValueError("reported facts cannot claim a derivation")
        return self


class EvidencePackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    cik: str
    as_of: date
    scope: str = "SEC US-GAAP statements"
    sources: tuple[SourceRecord, ...] = ()
    facts: tuple[FinancialFact, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def references(self):
        sources = {s.source_id: s for s in self.sources}
        facts = {f.fact_id: f for f in self.facts}
        if len(sources) != len(self.sources) or len(facts) != len(self.facts):
            raise ValueError("duplicate evidence identifiers")
        for source in self.sources:
            if source.cik != self.cik or source.filed_date > self.as_of:
                raise ValueError("source issuer or filing cutoff mismatch")
        for fact in self.facts:
            if fact.cik != self.cik or fact.as_of != self.as_of:
                raise ValueError("fact issuer or vintage mismatch")
            if any(s not in sources for s in fact.source_ids):
                raise ValueError("fact refers to missing source")
            if any(i not in facts or i == fact.fact_id for i in fact.input_fact_ids):
                raise ValueError("derivation refers to missing or self input")
        return self


# Only flows explicitly known to be additive. Never EPS, ratios, balances or
# weighted shares, even when the caller supplies a monetary-looking unit.
ADDITIVE_METRICS = frozenset(
    {
        "Revenue",
        "Cost of Revenue",
        "Gross Profit",
        "Operating Income",
        "Net Income",
        "Operating Cash Flow",
        "Investing Cash Flow",
        "Financing Cash Flow",
        "Capital Expenditure",
        "Common Stock Issuance Proceeds",
        "Stock Repurchase Payments",
        "Long-term Debt Issuance Proceeds",
        "Long-term Debt Repayments",
        "Finance Lease Principal Payments",
        "Equipment on Lease Payments",
        "Software Development Payments",
        "Cash-flow Share-based Compensation",
        "Equity Share-based Compensation",
        "Other Comprehensive Income Attributable to Parent",
        "Employee Stock Purchase Plan Issuance Value",
        "Noncash Finance Lease Additions",
        "Noncash Operating Lease Additions",
        "Income Tax Expense or Benefit",
        "Nonoperating Interest Expense",
        "Debt Interest Expense",
        "Finance Lease Interest Expense",
    }
)


# Gross payments/proceeds and noncash additions cannot be interpreted as a
# negative quarter merely because cumulative disclosures were revised.
NONNEGATIVE_FLOWS = frozenset(
    {
        "Capital Expenditure",
        "Common Stock Issuance Proceeds",
        "Stock Repurchase Payments",
        "Long-term Debt Issuance Proceeds",
        "Long-term Debt Repayments",
        "Finance Lease Principal Payments",
        "Equipment on Lease Payments",
        "Software Development Payments",
        "Noncash Finance Lease Additions",
        "Noncash Operating Lease Additions",
    }
)


def _compatible(inputs: tuple[FinancialFact, ...]):
    first = inputs[0]
    if first.metric not in ADDITIVE_METRICS or len(first.unit) != 3 or not first.unit.isupper():
        raise ValueError("only supported additive monetary flows may be derived")
    for f in inputs:
        if f.value is None or f.period_start is None:
            raise ValueError("derivation requires complete duration facts")
        if (f.metric, f.unit, f.cik, f.basis, f.as_of) != (
            first.metric,
            first.unit,
            first.cik,
            first.basis,
            first.as_of,
        ):
            raise ValueError("incompatible metric, unit, issuer, basis or vintage")
    if len({f.fact_id for f in inputs}) != len(inputs):
        raise ValueError("duplicate derivation inputs")


def _derived(inputs, start, end, value, formula, *, metric=None):
    ids = tuple(f.fact_id for f in inputs)
    identity = hashlib.sha256(
        json.dumps([formula, ids, str(value), str(start), str(end)]).encode()
    ).hexdigest()
    first = inputs[0]
    return FinancialFact(
        fact_id=identity,
        metric=metric or first.metric,
        value=value,
        unit=first.unit,
        cik=first.cik,
        period_start=start,
        period_end=end,
        as_of=first.as_of,
        basis=first.basis,
        source_ids=tuple(sorted({s for f in inputs for s in f.source_ids})),
        locator="Derived from referenced facts",
        origin="derived",
        input_fact_ids=ids,
        formula_id=formula,
    )



def derive_parent_net_income(
    profit: FinancialFact,
    noncontrolling: FinancialFact,
    profit_source: SourceRecord,
    noncontrolling_source: SourceRecord,
) -> FinancialFact:
    """Derive parent income only from one filing's distinct consolidated/NCI facts."""
    if (
        profit.metric != "Consolidated Profit (Loss)"
        or noncontrolling.metric != "Net Income Attributable to Noncontrolling Interests"
        or profit.origin != "reported" or noncontrolling.origin != "reported"
        or profit.value is None or noncontrolling.value is None
        or profit.period_start is None or noncontrolling.period_start is None
        or profit.unit != "USD" or noncontrolling.unit != "USD"
        or profit.basis != "US-GAAP" or noncontrolling.basis != "US-GAAP"
        or (profit.cik, profit.as_of, profit.period_start, profit.period_end)
        != (noncontrolling.cik, noncontrolling.as_of,
            noncontrolling.period_start, noncontrolling.period_end)
    ):
        raise ValueError("parent income inputs differ in definition, period, unit, issuer or basis")
    if (
        profit.source_ids != (profit_source.source_id,)
        or noncontrolling.source_ids != (noncontrolling_source.source_id,)
        or profit_source.locator != (
            f"us-gaap/ProfitLoss/USD/{profit.period_start}/{profit.period_end}/{profit_source.filed_date}"
        )
        or noncontrolling_source.locator != (
            "us-gaap/NetIncomeLossAttributableToNoncontrollingInterest/USD/"
            f"{noncontrolling.period_start}/{noncontrolling.period_end}/{noncontrolling_source.filed_date}"
        )
    ):
        raise ValueError("parent income inputs lack exact reported source tags")
    def vintage(source):
        return (
            source.cik, source.url, source.filed_date, source.retrieved_at,
            source.content_hash, source.accession, source.form,
        )
    if (
        vintage(profit_source) != vintage(noncontrolling_source)
        or not profit_source.accession
        or profit_source.form not in {"10-Q", "10-K"}
        or profit_source.cik != profit.cik
        or profit_source.filed_date > profit.as_of
    ):
        raise ValueError("parent income source vintage differs")
    with localcontext() as ctx:
        ctx.prec = 50
        value = profit.value - noncontrolling.value
    return _derived(
        (profit, noncontrolling), profit.period_start, profit.period_end,
        value, "consolidated_profit_less_nci_v1", metric="Net Income",
    )

def derive_quarter(cumulative: FinancialFact, preceding: FinancialFact) -> FinancialFact:
    """Annual minus nine months, or adjacent YTD totals, with explicit lineage."""
    inputs = (cumulative, preceding)
    _compatible(inputs)
    if cumulative.period_start != preceding.period_start:
        raise ValueError("cumulative periods must have the same fiscal start")
    start = preceding.period_end + timedelta(days=1)
    duration = (cumulative.period_end - start).days + 1
    whole = (cumulative.period_end - cumulative.period_start).days + 1
    prior = (preceding.period_end - preceding.period_start).days + 1
    if not (60 <= duration <= 115 and 150 <= whole <= 400 and 60 <= prior <= 290):
        raise ValueError("difference is not a supported fiscal quarter")
    with localcontext() as ctx:
        ctx.prec = 50
        value = cumulative.value - preceding.value
    if cumulative.metric in NONNEGATIVE_FLOWS and value < 0:
        raise ValueError("reconciliation required for decreasing cumulative gross flow")
    return _derived(inputs, start, cumulative.period_end, value, "cumulative_difference_v1")


def derive_ttm(quarters: list[FinancialFact] | tuple[FinancialFact, ...]) -> FinancialFact:
    """Sum exactly four contiguous fiscal quarters, never cumulative YTD values."""
    if len(quarters) != 4:
        raise ValueError("TTM requires four quarters")
    inputs = tuple(sorted(quarters, key=lambda f: f.period_end))
    _compatible(inputs)
    for i, f in enumerate(inputs):
        if not 60 <= (f.period_end - f.period_start).days + 1 <= 115:
            raise ValueError("TTM input is not a discrete quarter")
        if i and inputs[i - 1].period_end + timedelta(days=1) != f.period_start:
            raise ValueError("TTM quarters overlap or have a gap")
    if not 330 <= (inputs[-1].period_end - inputs[0].period_start).days + 1 <= 400:
        raise ValueError("TTM does not span a fiscal year")
    with localcontext() as ctx:
        ctx.prec = 50
        value = sum((f.value for f in inputs), Decimal(0))
    return _derived(
        inputs, inputs[0].period_start, inputs[-1].period_end, value, "four_quarter_sum_v1"
    )


def add_period_calculations(package: EvidencePackage) -> EvidencePackage:
    """Add only derivations supported by a complete, compatible set of inputs."""
    original = tuple(f for f in package.facts if f.origin == "reported" and f.value is not None)
    added = {f.fact_id: f for f in package.facts}
    warnings = list(package.warnings)
    for metric in sorted(ADDITIVE_METRICS):
        values = [f for f in original if f.metric == metric and f.period_start]
        reported_periods = {(f.period_start, f.period_end) for f in values}
        for current in values:
            preceding = sorted(
                (
                    f
                    for f in values
                    if f.period_start == current.period_start and f.period_end < current.period_end
                ),
                key=lambda f: f.period_end,
                reverse=True,
            )
            for previous in preceding:
                try:
                    derived = derive_quarter(current, previous)
                except ValueError as exc:
                    if "reconciliation" in str(exc):
                        warning = f"reconciliation required: {metric} cumulative difference, inputs {current.fact_id}, {previous.fact_id}"
                        if warning not in warnings:
                            warnings.append(warning)
                    continue
                if (derived.period_start, derived.period_end) not in reported_periods:
                    added.setdefault(derived.fact_id, derived)
                break
        quarter_periods = {}
        for f in added.values():
            if (
                f.metric == metric
                and f.value is not None
                and f.period_start
                and 60 <= (f.period_end - f.period_start).days + 1 <= 115
            ):
                key = (f.period_start, f.period_end)
                if key not in quarter_periods or f.origin == "reported":
                    quarter_periods[key] = f
        quarters = sorted(quarter_periods.values(), key=lambda f: f.period_end)
        for i in range(len(quarters) - 3):
            try:
                ttm = derive_ttm(quarters[i : i + 4])
            except ValueError:
                continue
            reported = next(
                (
                    f
                    for f in values
                    if (f.period_start, f.period_end) == (ttm.period_start, ttm.period_end)
                ),
                None,
            )
            if reported:
                if reported.value != ttm.value:
                    warning = f"reconciliation required: reported {reported.fact_id} differs from quarter sum {ttm.input_fact_ids}; reported value retained"
                    if warning not in warnings:
                        warnings.append(warning)
                continue
            added.setdefault(ttm.fact_id, ttm)
    return EvidencePackage(
        **{**package.model_dump(), "facts": tuple(added.values()), "warnings": tuple(warnings)}
    )


def bounded_evidence_view(package: EvidencePackage) -> EvidencePackage:
    """Cap model input while retaining latest metrics and complete selected lineage.

    The full immutable package remains available to deterministic validators.
    Round-robin history selection prevents one richly tagged metric crowding out
    another metric. This is an explicit partial view, never a coverage claim.
    """
    if len(package.model_dump_json()) <= 64000:
        return package
    warnings = (
        *package.warnings,
        "bounded tool view: some facts omitted; annual valuation baselines prioritized; this is not the full evidence package",
    )
    by_id = {f.fact_id: f for f in package.facts}
    groups = {}
    for fact in package.facts:
        groups.setdefault(fact.metric, []).append(fact)
    for group in groups.values():
        group.sort(key=lambda f: (f.period_end, f.origin == "reported"), reverse=True)
    # Preserve the annual baselines needed by the existing valuation methods.
    # Latest-quarter facts alone cannot support annual EPS/revenue scenarios.
    # These are existing source facts, still subject to the same byte/lineage cap.
    prioritized_groups = {}
    for metric in ("Revenue", "Diluted EPS", "Basic EPS"):
        annual = next((f for f in groups.get(metric, ())
                       if f.origin == "reported" and f.value is not None
                       and f.period_start is not None
                       and 330 <= (f.period_end - f.period_start).days <= 400), None)
        if annual is not None:
            prioritized_groups[metric] = [annual, *(f for f in groups[metric] if f != annual)]
    groups = {**prioritized_groups, **{k: v for k, v in groups.items() if k not in prioritized_groups}}
    ordered = [
        group[i]
        for i in range(max(map(len, groups.values())))
        for group in groups.values()
        if i < len(group)
    ]
    selected = set()

    def with_inputs(fact_id, result):
        if fact_id in result:
            return
        result.add(fact_id)
        for parent in by_id[fact_id].input_fact_ids:
            with_inputs(parent, result)

    def view(ids):
        facts = tuple(f for f in package.facts if f.fact_id in ids)
        sources = {s for f in facts for s in f.source_ids}
        return EvidencePackage(
            cik=package.cik,
            as_of=package.as_of,
            scope=package.scope,
            facts=facts,
            sources=tuple(s for s in package.sources if s.source_id in sources),
            warnings=warnings,
        )

    # Reconciliation warnings must retain the evidence needed to inspect them.
    for warning in package.warnings:
        for fact_id in re.findall(r"\b[0-9a-f]{64}\b", warning):
            if fact_id in by_id:
                with_inputs(fact_id, selected)
    result = view(selected)
    if len(result.model_dump_json()) > 64000:
        # Never publish dangling warning references or exceed the context cap.
        # The full package keeps every detail for deterministic validation.
        warnings = (
            "Reconciliation detail exceeds the tool-view budget; inspect the full evidence package. This partial view cannot establish financial consistency.",
        )
        selected = set()
        result = view(selected)
    for fact in ordered:
        candidate = selected.copy()
        with_inputs(fact.fact_id, candidate)
        proposed = view(candidate)
        if len(proposed.model_dump_json()) <= 64000:
            selected, result = candidate, proposed
    return result


LIABILITIES_AND_EQUITY = "Liabilities and Equity"
TOTAL_EQUITY = "Total Equity Including Noncontrolling Interests"
NONCONTROLLING = "Noncontrolling Interests"
TEMPORARY_EQUITY_TAGS = (
    "RedeemableNoncontrollingInterestEquityCarryingAmount",
    "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests",
    "TemporaryEquityCarryingAmountAttributableToParent",
    "RedeemableNoncontrollingInterestEquityCommonCarryingAmount",
    "RedeemableNoncontrollingInterestEquityPreferredCarryingAmount",
)
TOTAL_LIABILITIES_FORMULA = "liabilities_and_equity_less_equity_v1"


def temporary_equity_metric(tag: str) -> str:
    return f"Temporary Equity [{tag}]"


TEMPORARY_EQUITY_METRICS = frozenset(temporary_equity_metric(tag) for tag in TEMPORARY_EQUITY_TAGS)


def derive_total_liabilities(inputs: tuple[FinancialFact, ...]) -> FinancialFact:
    """Total liabilities for a filer that reports none: the filed total less all equity, each input cited.

    Inputs are the reported liabilities-and-equity total, one equity total (consolidated, or the parent's
    where the caller established there is no noncontrolling interest), and at most one temporary-equity
    balance, all on one date, unit, basis and vintage.
    """
    if not 2 <= len(inputs) <= 3 or len({f.fact_id for f in inputs}) != len(inputs):
        raise ValueError("total liabilities needs the filed total, one equity total and at most one temporary balance")
    total, equity, *temporary = inputs
    if (total.metric != LIABILITIES_AND_EQUITY or equity.metric not in (TOTAL_EQUITY, "Stockholders Equity")
            or any(f.metric not in TEMPORARY_EQUITY_METRICS for f in temporary)):
        raise ValueError("total liabilities inputs have the wrong roles")
    if any(f.origin != "reported" or f.value is None or f.period_start is not None for f in inputs):
        raise ValueError("total liabilities needs reported balances")
    if len({(f.unit, f.cik, f.basis, f.as_of, f.period_end) for f in inputs}) != 1 or len(total.unit) != 3:
        raise ValueError("incompatible unit, issuer, basis, vintage or date")
    value = total.value - equity.value - sum((f.value for f in temporary), Decimal(0))
    if value < 0:
        raise ValueError("derived total liabilities is negative")
    return _derived(inputs, None, total.period_end, value, TOTAL_LIABILITIES_FORMULA, metric="Total Liabilities")


def derive_cash_outflow(reported: FinancialFact) -> FinancialFact:
    """Convert an explicitly classified signed payment to its gross magnitude."""
    if (
        reported.metric
        not in {
            "Equipment Financing Principal Payments",
            "Finance Lease and Financing Arrangement Principal Payments",
        }
        or reported.origin != "reported"
    ):
        raise ValueError("requires an explicitly reported financing-principal payment")
    if reported.value is None or reported.period_start is None or reported.unit != "USD":
        raise ValueError("requires complete dated USD payment evidence")
    return _derived(
        (reported,),
        reported.period_start,
        reported.period_end,
        reported.value.copy_abs(),
        "reported_cash_outflow_magnitude_v1",
    )
