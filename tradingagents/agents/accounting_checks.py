"""Small deterministic accounting methods over immutable, dated source facts.

Callers own evidence coverage and the meaning of signed adjustments. A successful
arithmetic check is not a declaration that all issuer disclosures were found.
No residual is converted into a transaction or a balancing plug.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tradingagents.dataflows.financial_evidence import EvidencePackage


class Calculation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    method: str
    status: Literal["pass", "fail", "unavailable"]
    result: Decimal | None = None
    expected: Decimal | None = None
    residual: Decimal | None = None
    tolerance: Decimal | None = None
    unit: str | None = None
    input_fact_ids: tuple[str, ...] = ()
    reason_code: str
    message: str


def _unavailable(method, ids, code, message):
    return Calculation(
        method=method,
        status="unavailable",
        input_fact_ids=tuple(ids),
        reason_code=code,
        message=message,
    )


def _facts(package, ids):
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("missing or duplicate input identifiers")
    lookup = {f.fact_id: f for f in package.facts}
    if any(i not in lookup or lookup[i].value is None for i in ids):
        raise ValueError("required input fact unavailable")
    facts = [lookup[i] for i in ids]
    if len({(f.cik, f.as_of) for f in facts}) != 1:
        raise ValueError("issuer or vintage mismatch")
    return facts


def _same(facts, *, duration=False, basis=True):
    if len({(f.unit, f.period_start, f.period_end) for f in facts}) != 1:
        raise ValueError("unit or period mismatch")
    if duration and facts[0].period_start is None:
        raise ValueError("duration facts required")
    if basis and len({f.basis for f in facts}) != 1:
        raise ValueError("accounting basis mismatch")


def _money(facts):
    if any(len(f.unit) != 3 or not f.unit.isupper() for f in facts):
        raise ValueError("monetary currency units required")


def _quantum(precision, ids):
    if any(i not in precision for i in ids):
        return None
    values = [Decimal(str(precision[i])) for i in ids]
    if any(not v.is_finite() or v < 0 for v in values):
        raise ValueError("source rounding quantum must be finite and nonnegative")
    return values


def _reconcile(method, ids, value, expected, unit, precision):
    residual = value - expected
    quanta = _quantum(precision, ids)
    if quanta is None and residual != 0:
        return Calculation(
            method=method,
            status="unavailable",
            result=value,
            expected=expected,
            residual=residual,
            unit=unit,
            input_fact_ids=tuple(ids),
            reason_code="precision_unavailable",
            message="Nonzero residual cannot be assessed without source rounding precision",
        )
    tolerance = sum(quanta, Decimal(0)) / 2 if quanta is not None else Decimal(0)
    ok = abs(residual) <= tolerance
    return Calculation(
        method=method,
        status="pass" if ok else "fail",
        result=value,
        expected=expected,
        residual=residual,
        tolerance=tolerance,
        unit=unit,
        input_fact_ids=tuple(ids),
        reason_code="reconciled" if ok else "material_residual",
        message="Within source rounding bounds"
        if ok
        else "Unexplained residual exceeds source rounding bounds",
    )


def check_balance_sheet(package: EvidencePackage, assets_id, liabilities_id, equity_id, precision):
    method = "assets_equals_liabilities_plus_equity_v1"
    ids = (assets_id, liabilities_id, equity_id)
    try:
        a, liabilities, e = _facts(package, ids)
        _same([a, liabilities, e])
        _money([a, liabilities, e])
        if a.period_start is not None:
            raise ValueError("balance sheet requires instant facts")
        if (a.metric, liabilities.metric, e.metric) != (
            "Total Assets",
            "Total Liabilities",
            "Stockholders Equity",
        ):
            raise ValueError("balance-sheet input roles do not match")
        with localcontext() as ctx:
            ctx.prec = 50
            return _reconcile(method, ids, liabilities.value + e.value, a.value, a.unit, precision)
    except (ValueError, ArithmeticError) as exc:
        return _unavailable(method, ids, "incompatible_inputs", str(exc))


def _signed_components(package, ids, signed_components):
    if any(sign not in (-1, 1) or isinstance(sign, bool) for _, sign in signed_components):
        raise ValueError("components require explicit +1 or -1 signs")
    return _facts(package, ids)


_EQUITY_MOVEMENTS = frozenset(
    {
        "Net Income",
        "Net Income Attributable to Common Stockholders",
        "Equity Incentive Plan Issuance Net of Withholding",
        "Equity Common Stock Issuance Value",
        "Equity Share-based Compensation",
        "Employee Stock Purchase Plan Issuance Value",
        "Other Comprehensive Income Attributable to Parent",
        "Equity Stock Repurchases/Retirements",
        "Equity Award Tax Withholding",
        "Equity Dividends",
        "Equity Conversion of Debt",
    }
)


def check_equity_rollforward(
    package, opening_id, closing_id, signed_components, complete, precision
):
    method = "opening_equity_plus_disclosed_movements_v1"
    ids = (opening_id, closing_id, *(i for i, _ in signed_components))
    if complete is not True or not signed_components:
        return _unavailable(
            method, ids, "coverage_incomplete", "Complete signed equity movements are required"
        )
    try:
        opening, closing, *components = _signed_components(package, ids, signed_components)
        if opening.metric != "Stockholders Equity" or closing.metric != "Stockholders Equity":
            raise ValueError("opening and closing equity roles must be Stockholders Equity")
        if any(f.metric not in _EQUITY_MOVEMENTS for f in components):
            raise ValueError(
                "unsupported equity movement role; residuals and cash-flow proxies are not movements"
            )
        metrics = {f.metric for f in components}
        if {"Net Income", "Net Income Attributable to Common Stockholders"} <= metrics:
            raise ValueError("total net income and common-stockholder subset overlap")
        if (
            "Equity Incentive Plan Issuance Net of Withholding" in metrics
            and "Equity Award Tax Withholding" in metrics
        ):
            raise ValueError(
                "net incentive issuance and separate tax withholding require disjoint source scope"
            )
        if len(metrics) != len(components):
            raise ValueError(
                "duplicate equity movement role requires explicit source disaggregation"
            )
        if (
            opening.period_start is not None
            or closing.period_start is not None
            or opening.period_end >= closing.period_end
        ):
            raise ValueError("equity requires opening and closing instant balances")
        _money([opening, closing, *components])
        if len({(f.unit, f.basis) for f in [opening, closing, *components]}) != 1:
            raise ValueError("equity unit or basis mismatch")
        if any(
            f.period_start != opening.period_end + timedelta(days=1)
            or f.period_end != closing.period_end
            for f in components
        ):
            raise ValueError("equity movements must cover exactly the opening-to-closing period")
        with localcontext() as ctx:
            ctx.prec = 50
            value = opening.value + sum(
                (
                    f.value * sign
                    for f, (_, sign) in zip(components, signed_components, strict=True)
                ),
                Decimal(0),
            )
            return _reconcile(method, ids, value, closing.value, closing.unit, precision)
    except (ValueError, ArithmeticError) as exc:
        return _unavailable(method, ids, "incompatible_inputs", str(exc))


_OBLIGATION_METRICS = {
    "borrowings": {
        "Total Borrowings",
        "Long-term Borrowings (including current)",
        "Current Long-term Borrowings",
        "Noncurrent Long-term Borrowings",
        "Short-term Borrowings",
    },
    "finance_leases": {
        "Finance Lease Liabilities",
        "Current Finance Lease Liabilities",
        "Noncurrent Finance Lease Liabilities",
    },
    "equipment": {"Equipment Financing Obligations"},
    "finance_equipment": {"Finance Lease and Equipment Obligations"},
    "operating_leases": {
        "Operating Lease Liabilities",
        "Current Operating Lease Liabilities",
        "Noncurrent Operating Lease Liabilities",
    },
}
_TOTAL_COMPONENTS = (
    (
        "Long-term Borrowings (including current)",
        "Current Long-term Borrowings",
        "Noncurrent Long-term Borrowings",
    ),
    (
        "Finance Lease Liabilities",
        "Current Finance Lease Liabilities",
        "Noncurrent Finance Lease Liabilities",
    ),
    (
        "Operating Lease Liabilities",
        "Current Operating Lease Liabilities",
        "Noncurrent Operating Lease Liabilities",
    ),
)


def calculate_obligations(package, components_by_category, cash_id):
    """Three dated net perimeters; an absent category is never an inferred zero.

    A filed combined finance/equipment amount may replace both separate
    categories. It is never decomposed by an invented residual.
    """
    outputs = []
    for categories, method in [
        (("borrowings",), "borrowings_less_cash_v1"),
        (
            ("borrowings", "finance_leases", "equipment"),
            "borrowings_finance_equipment_less_cash_v1",
        ),
        (
            ("borrowings", "finance_leases", "equipment", "operating_leases"),
            "all_classified_obligations_less_cash_v1",
        ),
    ]:
        combined = "finance_equipment" in components_by_category and "finance_leases" in categories
        if combined:
            categories = tuple(c for c in categories if c != "equipment")
            categories = tuple(
                "finance_equipment" if c == "finance_leases" else c for c in categories
            )
        ids = (*(i for c in categories for i in components_by_category.get(c, ())), cash_id)
        try:
            if combined and any(
                c in components_by_category for c in ("finance_leases", "equipment")
            ):
                ids = (
                    *ids,
                    *(
                        i
                        for c in ("finance_leases", "equipment")
                        for i in components_by_category.get(c, ())
                    ),
                )
                raise ValueError(
                    "combined finance/equipment amount overlaps separately declared categories"
                )
            if any(not components_by_category.get(c) for c in categories):
                raise ValueError(
                    "required obligation category unavailable; explicit sourced zero required for absence"
                )
            facts = _facts(package, ids)
            _same(facts)
            _money(facts)
            if facts[0].period_start is not None or facts[-1].metric != "Cash and Equivalents":
                raise ValueError("obligations require instant balances and unrestricted cash")
            if any(f.value < 0 for f in facts):
                raise ValueError("negative gross obligation or cash requires reconciliation")
            for category in categories:
                group = _facts(package, components_by_category[category])
                metrics = {f.metric for f in group}
                if not metrics <= _OBLIGATION_METRICS[category] or len(metrics) != len(group):
                    raise ValueError("unclassified or duplicate obligation components")
                if category == "borrowings" and "Total Borrowings" in metrics and len(metrics) > 1:
                    raise ValueError("total borrowings overlaps borrowing components")
                for total, current, noncurrent in _TOTAL_COMPONENTS:
                    if total in metrics and metrics & {current, noncurrent}:
                        raise ValueError("overlapping total and components")
                    if metrics & {current, noncurrent} and not {current, noncurrent} <= metrics:
                        raise ValueError("current/noncurrent coverage incomplete")
            with localcontext() as ctx:
                ctx.prec = 50
                result = sum((f.value for f in facts[:-1]), Decimal(0)) - facts[-1].value
            outputs.append(
                Calculation(
                    method=method,
                    status="pass",
                    result=result,
                    unit=facts[0].unit,
                    input_fact_ids=ids,
                    reason_code="calculated",
                    message="Declared dated obligation perimeter; excludes undisclosed categories",
                )
            )
        except (ValueError, ArithmeticError) as exc:
            outputs.append(_unavailable(method, ids, "incompatible_or_missing_perimeter", str(exc)))
    return tuple(outputs)


def _has_source_tag(package, facts, tag):
    """Follow all inherited inputs and source locators, not the derived label."""
    by_id = {fact.fact_id: fact for fact in package.facts}
    sources = {source.source_id: source for source in package.sources}
    pending = list(facts)
    visited = set()
    while pending:
        fact = pending.pop()
        if fact.fact_id in visited:
            continue
        visited.add(fact.fact_id)
        if tag in fact.locator:
            return True
        for source_id in fact.source_ids:
            if source_id not in sources:
                raise ValueError("missing source provenance")
            if tag in sources[source_id].locator:
                return True
        for input_id in fact.input_fact_ids:
            if input_id not in by_id:
                raise ValueError("missing derivation provenance")
            pending.append(by_id[input_id])
    return False


def _combined_principal_scope(package, fact):
    """Require separate, same-filing source provenance for the combined scope.

    The evidence gate independently replays the filing parser against canonical
    text. This arithmetic boundary verifies linkage, never infers equipment
    scope from an accounting label alone.
    """
    sources = [s for s in package.sources if s.source_id in fact.source_ids]
    definitions = [
        s for s in sources if s.locator.endswith("; finance/equipment principal definition")
    ]
    tables = [s for s in sources if s not in definitions]
    fields = ("cik", "accession", "filed_date", "form", "content_hash", "url")
    return bool(definitions and tables) and all(
        s.accession and all(getattr(s, key) == getattr(tables[0], key) for key in fields)
        for s in sources
    )


def check_financed_equipment_bridge(package, acquisition_id, proceeds_id, precision):
    """Reconcile explicitly scoped gross acquisition and financing cash flows."""
    method = "equipment_financing_acquisition_plus_proceeds_v1"
    ids = (acquisition_id, proceeds_id)
    try:
        acquisition, proceeds = _facts(package, ids)
        _same((acquisition, proceeds), duration=True)
        _money((acquisition, proceeds))
        if (
            acquisition.metric != "Equipment Financing Acquisition Payments"
            or proceeds.metric != "Equipment Financing Proceeds"
            or acquisition.origin != "reported"
            or proceeds.origin != "reported"
            or acquisition.value > 0
            or proceeds.value < 0
        ):
            raise ValueError("explicit signed gross equipment acquisition/proceeds roles required")
        sources = {s.source_id: s for s in package.sources}
        shared = set(acquisition.source_ids) & set(proceeds.source_ids)
        definition_ids = {
            ident
            for ident in shared
            if ident in sources
            and sources[ident].locator.endswith(
                "; equipment financing acquisition/proceeds definition"
            )
        }
        all_ids = set(acquisition.source_ids) | set(proceeds.source_ids)
        if not definition_ids or any(ident not in sources for ident in all_ids):
            raise ValueError("shared equipment acquisition/proceeds definition source required")
        records = [sources[ident] for ident in all_ids]
        fields = ("cik", "accession", "filed_date", "form", "content_hash", "url")
        if any(
            not source.accession
            or any(getattr(source, key) != getattr(records[0], key) for key in fields)
            for source in records
        ):
            raise ValueError("equipment acquisition/proceeds must share filing provenance")
        with localcontext() as ctx:
            ctx.prec = 50
            result = _reconcile(
                method,
                ids,
                acquisition.value + proceeds.value,
                Decimal(0),
                acquisition.unit,
                precision,
            )
        return result.model_copy(
            update={
                "message": "Gross financed equipment acquisition plus proceeds; separate from cash capex and principal. "
                + result.message
            }
        )
    except (ValueError, ArithmeticError) as exc:
        return _unavailable(method, ids, "incompatible_financed_acquisition", str(exc))


def calculate_cash_generation(package, ocf_id, capex_ids, principal_ids, complete):
    """Conventional cash investment and separate financing-principal variant.

    Coverage must explicitly enumerate cash capital spending and financing
    principal. Noncash asset additions and operating lease cash are excluded.
    """
    outputs = []
    for include_principal, method in [
        (False, "ocf_less_enumerated_cash_capex_v1"),
        (True, "ocf_less_capex_and_financing_principal_v1"),
    ]:
        ids = (ocf_id, *capex_ids, *(principal_ids if include_principal else ()))
        try:
            if complete is not True or not capex_ids or (include_principal and not principal_ids):
                raise ValueError("explicit complete cash spending coverage required")
            fs = _facts(package, ids)
            _same(fs, duration=True)
            _money(fs)
            if fs[0].metric != "Operating Cash Flow":
                raise ValueError("operating cash flow input required")
            capex = _facts(package, capex_ids)
            if any(
                f.metric not in {"Capital Expenditure", "Software Development Payments"}
                or f.value < 0
                for f in capex
            ):
                raise ValueError(
                    "capital spending must be nonnegative enumerated cash acquisitions"
                )
            if _has_source_tag(package, capex, "PaymentsToAcquireProductiveAssets") and any(
                f.metric == "Software Development Payments" for f in capex
            ):
                raise ValueError(
                    "broad productive-asset spending may overlap software; disaggregation required"
                )
            if len({f.metric for f in capex}) != len(capex):
                raise ValueError("duplicate capital spending metric")
            if include_principal:
                principal = _facts(package, principal_ids)
                if any(
                    f.metric
                    not in {
                        "Finance Lease Principal Payments",
                        "Equipment Financing Principal Payments",
                        "Finance Lease and Financing Arrangement Principal Payments",
                        "Long-term Debt Repayments",
                    }
                    or f.value < 0
                    for f in principal
                ):
                    raise ValueError(
                        "principal variant cannot deduct operating lease cash or noncash additions"
                    )
                combined = [
                    f
                    for f in principal
                    if f.metric == "Finance Lease and Financing Arrangement Principal Payments"
                ]
                if combined and (
                    len(principal) != 1 or not _combined_principal_scope(package, combined[0])
                ):
                    raise ValueError(
                        "combined lease/equipment principal needs distinct linked scope; components overlap"
                    )
                if len({f.metric for f in principal}) != len(principal):
                    raise ValueError("duplicate financing principal metric")
            with localcontext() as ctx:
                ctx.prec = 50
                result = fs[0].value - sum((f.value for f in fs[1:]), Decimal(0))
            outputs.append(
                Calculation(
                    method=method,
                    status="pass",
                    result=result,
                    unit=fs[0].unit,
                    input_fact_ids=ids,
                    reason_code="calculated",
                    message="Enumerated cash-flow definition; noncash additions and commitments remain separate",
                )
            )
        except (ValueError, ArithmeticError) as exc:
            outputs.append(
                _unavailable(method, ids, "incompatible_or_missing_cash_coverage", str(exc))
            )
    return tuple(outputs)


def check_eps(package, numerator_id, shares_id, eps_id, precision):
    method = "reported_earnings_numerator_divided_by_weighted_shares_v1"
    ids = (numerator_id, shares_id, eps_id)
    try:
        numerator, shares, eps = _facts(package, ids)
        if (
            len({(f.period_start, f.period_end, f.basis) for f in (numerator, shares, eps)}) != 1
            or numerator.period_start is None
        ):
            raise ValueError("EPS period or basis mismatch")
        if (
            numerator.basis != "US-GAAP"
            or shares.unit != "shares"
            or eps.unit != numerator.unit + "/shares"
        ):
            raise ValueError("EPS requires GAAP earnings and matching currency/share units")
        _money([numerator])
        allowed = {
            ("Basic Earnings Numerator", "Weighted Average Basic Shares", "Basic EPS"),
            ("Diluted Earnings Numerator", "Weighted Average Diluted Shares", "Diluted EPS"),
        }
        if (numerator.metric, shares.metric, eps.metric) not in allowed or shares.value <= 0:
            raise ValueError(
                "explicit matched earnings numerator and positive weighted shares required"
            )
        with localcontext() as ctx:
            ctx.prec = 50
            value = numerator.value / shares.value
            residual = value - eps.value
            quanta = _quantum(precision, ids)
            if quanta is None and residual != 0:
                return Calculation(
                    method=method,
                    status="unavailable",
                    result=value,
                    expected=eps.value,
                    residual=residual,
                    unit=eps.unit,
                    input_fact_ids=ids,
                    reason_code="precision_unavailable",
                    message="Numerator/share arithmetic calculated; EPS reconciliation needs source precision",
                )
            tolerance = Decimal(0)
            if quanta is not None:
                nq, sq, eq = (q / 2 for q in quanta)
                if shares.value - sq <= 0:
                    raise ValueError("share rounding interval includes nonpositive denominator")
                bounds = [
                    (numerator.value + n) / (shares.value + s) for n in (-nq, nq) for s in (-sq, sq)
                ]
                tolerance = max(abs(v - value) for v in bounds) + eq
            ok = abs(residual) <= tolerance
            return Calculation(
                method=method,
                status="pass" if ok else "fail",
                result=value,
                expected=eps.value,
                residual=residual,
                tolerance=tolerance,
                unit=eps.unit,
                input_fact_ids=ids,
                reason_code="reconciled" if ok else "material_residual",
                message="Matched GAAP numerator/shares; no net-income substitute for diluted numerator",
            )
    except (ValueError, ArithmeticError) as exc:
        return _unavailable(method, ids, "incompatible_inputs", str(exc))


# This is deliberately a small set of supported measure/adjustment roles.
# A caller must source the management reconciliation and classify these roles;
# a complete=True declaration never permits unrelated financial facts.
_ADJUSTED_PAIRS = frozenset(
    {
        ("Net Income", "Adjusted Net Income"),
        ("Net Income", "Adjusted EBITDA"),
        ("Operating Income", "Adjusted Operating Income"),
        ("Operating Cash Flow", "Adjusted Free Cash Flow"),
    }
)
_MANAGEMENT_ADJUSTMENTS = frozenset(
    {
        "Management Share-based Compensation Adjustment",
        "Management Depreciation and Amortization Adjustment",
        "Management Interest Adjustment",
        "Management Tax Adjustment",
        "Management Restructuring Adjustment",
        "Management Acquisition Cost Adjustment",
        "Management Capital Expenditure Adjustment",
        "Management Software Development Adjustment",
        "Management Financing Principal Adjustment",
    }
)


def check_adjusted_bridge(package, gaap_id, adjusted_id, signed_components, complete, precision):
    method = "gaap_plus_disclosed_management_adjustments_v1"
    ids = (gaap_id, adjusted_id, *(i for i, _ in signed_components))
    if complete is not True or not signed_components:
        return _unavailable(
            method,
            ids,
            "coverage_incomplete",
            "Complete explicit management reconciliation required",
        )
    try:
        gaap, adjusted, *components = _signed_components(package, ids, signed_components)
        if (gaap.metric, adjusted.metric) not in _ADJUSTED_PAIRS:
            raise ValueError("unsupported GAAP/adjusted measure pair")
        if any(f.metric not in _MANAGEMENT_ADJUSTMENTS for f in components):
            raise ValueError("unsupported management adjustment role")
        if len({f.metric for f in components}) != len(components):
            raise ValueError("duplicate management adjustment role")
        _same([gaap, adjusted, *components], duration=True, basis=False)
        _money([gaap, adjusted, *components])
        if gaap.basis != "US-GAAP" or adjusted.basis != "management-adjusted":
            raise ValueError(
                "GAAP and management-adjusted measures must remain explicitly distinct"
            )
        with localcontext() as ctx:
            ctx.prec = 50
            result = gaap.value + sum(
                (
                    f.value * sign
                    for f, (_, sign) in zip(components, signed_components, strict=True)
                ),
                Decimal(0),
            )
            return _reconcile(method, ids, result, adjusted.value, gaap.unit, precision)
    except (ValueError, ArithmeticError) as exc:
        return _unavailable(method, ids, "incompatible_inputs", str(exc))


_INVESTING_PAYMENTS = frozenset({
    "Cash-flow Property and Equipment Payments", "Cash-flow Software Development Payments",
    "Equipment Financing Acquisition Payments", "Intangible Asset Acquisition Payments",
    "Business Acquisition Payments", "Financial Investment Purchases",
})
_INVESTING_PROCEEDS = frozenset({"Financial Investment Sale Proceeds", "Property and Equipment Sale Proceeds"})


def _cash_statement_sources(package, facts):
    """Signed statement bridges require reported rows from the same filed statement."""
    sources = {s.source_id: s for s in package.sources}
    if any(f.origin != "reported" for f in facts):
        raise ValueError("signed statement bridge requires reported cash-flow rows")
    if any(s not in sources for f in facts for s in f.source_ids):
        raise ValueError("cash statement input refers to an unavailable source")
    records = [sources[s] for f in facts for s in f.source_ids]
    if not records or any(not s.accession for s in records) or len({
        (s.cik, s.accession, s.filed_date, s.content_hash, s.url) for s in records
    }) != 1:
        raise ValueError("cash statement inputs must share exact filing provenance")


def check_investing_cash_bridge(package, total_id, component_ids, complete, precision):
    """Reconcile signed investing rows without netting financed equipment away."""
    method = "signed_investing_components_to_total_v1"
    ids = (total_id, *component_ids)
    try:
        if complete is not True or not component_ids:
            raise ValueError("complete investing statement row coverage required")
        facts = _facts(package, ids)
        _same(facts, duration=True)
        _money(facts)
        _cash_statement_sources(package, facts)
        total, components = facts[0], facts[1:]
        if total.metric != "Investing Cash Flow":
            raise ValueError("reported investing cash-flow total required")
        if len({f.metric for f in components}) != len(components):
            raise ValueError("duplicate investing category risks overlapping cash flows")
        for fact in components:
            if fact.metric in _INVESTING_PAYMENTS:
                if fact.value > 0:
                    raise ValueError("investing payment needs original nonpositive statement sign")
            elif fact.metric in _INVESTING_PROCEEDS:
                if fact.value < 0:
                    raise ValueError("investing proceeds need original nonnegative statement sign")
            else:
                raise ValueError("unclassified investing component")
        with localcontext() as context:
            context.prec = 50
            result = _reconcile(method, ids, sum((f.value for f in components), Decimal(0)),
                                total.value, total.unit, precision)
        return result.model_copy(update={"message":
            "Signed investing components; financed equipment retained gross, acquisitions and securities separate. "
            + result.message})
    except (ValueError, ArithmeticError) as exc:
        return _unavailable(method, ids, "incomplete_or_incompatible_investing_bridge", str(exc))


def check_cash_balance_bridge(package, ocf_id, investing_id, financing_id, fx_id, change_id,
                              opening_id, closing_id, precision):
    """Cash-flow change and cash-plus-restricted-cash closing balance, independently checked."""
    flow_ids = (ocf_id, investing_id, financing_id, fx_id, change_id)
    flow_method = "cash_flows_plus_fx_to_cash_change_v1"
    balance_method = "opening_plus_change_to_cash_including_restricted_v1"
    try:
        facts = _facts(package, flow_ids)
        _same(facts, duration=True)
        _money(facts)
        _cash_statement_sources(package, facts)
        expected_roles = ("Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow",
                          "Exchange Effect on Cash Including Restricted Cash", "Change in Cash Including Restricted Cash")
        if tuple(f.metric for f in facts) != expected_roles:
            raise ValueError("cash-flow and FX roles must explicitly include restricted cash in the change")
        with localcontext() as context:
            context.prec = 50
            flow = _reconcile(flow_method, flow_ids, sum((f.value for f in facts[:4]), Decimal(0)),
                              facts[4].value, facts[4].unit, precision)
    except (ValueError, ArithmeticError) as exc:
        flow = _unavailable(flow_method, flow_ids, "incompatible_cash_change_inputs", str(exc))
    balance_ids = (change_id, opening_id, closing_id)
    try:
        change, opening, closing = _facts(package, balance_ids)
        _money((change, opening, closing))
        _cash_statement_sources(package, (change, opening, closing))
        if (change.metric != "Change in Cash Including Restricted Cash"
                or opening.metric != "Cash Including Restricted Cash" or closing.metric != opening.metric
                or change.period_start is None or opening.period_start is not None or closing.period_start is not None
                or opening.period_end != change.period_start - timedelta(days=1)
                or closing.period_end != change.period_end
                or len({f.unit for f in (change, opening, closing)}) != 1
                or len({f.basis for f in (change, opening, closing)}) != 1):
            raise ValueError("opening/closing restricted-cash scope, currency, basis or dates differ")
        if opening.value < 0 or closing.value < 0:
            raise ValueError("cash balances cannot be negative")
        with localcontext() as context:
            context.prec = 50
            balance = _reconcile(balance_method, balance_ids, opening.value + change.value,
                                 closing.value, closing.unit, precision)
        balance = balance.model_copy(update={"message":
            "Statement cash plus restricted cash; not unrestricted valuation cash. " + balance.message})
    except (ValueError, ArithmeticError) as exc:
        balance = _unavailable(balance_method, balance_ids, "incompatible_cash_balance_inputs", str(exc))
    return flow, balance


def calculate_cash_after_acquisitions(package, ocf_id, capex_ids, principal_ids, acquisition_ids, complete):
    """Principal-adjusted cash generation after explicitly enumerated acquisitions.

    Uses the existing nonnegative capex/principal definition. Acquisition rows
    retain their original signed statement amounts; securities purchases and
    financed-equipment gross acquisition are not deducted in this measure.
    """
    method = "ocf_less_capex_principal_and_acquisitions_v1"
    ids = (ocf_id, *capex_ids, *principal_ids, *acquisition_ids)
    try:
        base = calculate_cash_generation(package, ocf_id, capex_ids, principal_ids, complete)[1]
        if base.status != "pass" or complete is not True or not acquisition_ids:
            raise ValueError("complete compatible capex, principal and acquisition coverage required")
        facts = _facts(package, ids)
        _same(facts, duration=True)
        _money(facts)
        acquisitions = _facts(package, acquisition_ids)
        if {f.metric for f in acquisitions} != {"Intangible Asset Acquisition Payments", "Business Acquisition Payments"}:
            raise ValueError("both intangible and business acquisition cash coverage required; absent is not zero")
        if len({f.metric for f in acquisitions}) != len(acquisitions) or any(
            f.metric not in {"Intangible Asset Acquisition Payments", "Business Acquisition Payments"}
            or f.origin != "reported" or f.value > 0 for f in acquisitions
        ):
            raise ValueError("acquisitions must be distinct, reported, signed intangible/business cash payments")
        _cash_statement_sources(package, acquisitions)
        with localcontext() as context:
            context.prec = 50
            value = base.result + sum((f.value for f in acquisitions), Decimal(0))
        return Calculation(method=method, status="pass", result=value, unit=facts[0].unit,
                           input_fact_ids=ids, reason_code="calculated",
                           message="OCF less enumerated PP&E/software, financing principal and business/intangible acquisitions; "
                                   "excludes securities, financed-equipment gross flows and noncash additions; not universal shareholder free cash flow")
    except (ValueError, ArithmeticError) as exc:
        return _unavailable(method, ids, "incomplete_or_incompatible_acquisition_cash", str(exc))


def cash_statement_reconciliations(package, extraction, precision, *, start, end):
    """Wire one explicitly selected statement duration to the three cash bridges.

    Caller supplies the same primary start/end used by existing cash-generation
    selection. Only exact extracted facts still present in the canonical package
    qualify; companyfacts with similar labels cannot displace signed table rows.
    """
    methods = ("signed_investing_components_to_total_v1", "cash_flows_plus_fx_to_cash_change_v1",
               "opening_plus_change_to_cash_including_restricted_v1")
    coverages = [c for c in getattr(extraction, "investing_coverage", ())
                 if start is not None and end is not None and c.period_start == start and c.period_end == end]
    if len(coverages) != 1:
        return tuple(_unavailable(method, (), "cash_statement_coverage_unavailable",
                                  "One source-linked investing coverage record for the selected cash period required")
                     for method in methods)
    coverage = coverages[0]
    canonical = {f.fact_id: f for f in package.facts}
    extracted = {f.fact_id: f for f in extraction.evidence.facts}
    verified = {key: fact for key, fact in extracted.items() if canonical.get(key) == fact}
    anchor = next((verified[key] for key in (coverage.total_fact_id, *coverage.component_fact_ids)
                   if key in verified), None)
    if anchor is None:
        return tuple(_unavailable(method, (), "cash_statement_source_unavailable",
                                  "Selected cash statement coverage has no canonical verified source rows")
                     for method in methods)

    def select(metric, period_start, period_end):
        candidates = []
        for fact in verified.values():
            if (fact.metric != metric or fact.period_start != period_start or fact.period_end != period_end
                    or fact.value is None or fact.origin != "reported"):
                continue
            try:
                _cash_statement_sources(package, (anchor, fact))
            except ValueError:
                continue
            candidates.append(fact.fact_id)
        return candidates[0] if len(candidates) == 1 else "missing-or-ambiguous:" + metric

    investing = check_investing_cash_bridge(package, coverage.total_fact_id or "missing-investing-total",
        coverage.component_fact_ids, coverage.complete, precision)
    roles = ("Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow",
             "Exchange Effect on Cash Including Restricted Cash", "Change in Cash Including Restricted Cash")
    flows = [select(metric, start, end) for metric in roles]
    opening = select("Cash Including Restricted Cash", None, start - timedelta(days=1))
    closing = select("Cash Including Restricted Cash", None, end)
    return (investing, *check_cash_balance_bridge(package, *flows, opening, closing, precision))
