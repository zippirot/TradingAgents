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
        if len({f.metric for f in components}) != len(components):
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
                        "Long-term Debt Repayments",
                    }
                    or f.value < 0
                    for f in principal
                ):
                    raise ValueError(
                        "principal variant cannot deduct operating lease cash or noncash additions"
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
