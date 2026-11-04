"""Deterministic evidence checks at the analyst-to-debate boundary."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tradingagents.dataflows.financial_evidence import EvidencePackage


class FinancialClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    kind: Literal["reported", "derived"]
    fact_id: str = Field(min_length=1, max_length=128)
    metric: str = Field(min_length=1, max_length=160)
    value: Decimal
    unit: str = Field(min_length=1, max_length=80)
    period_start: date | None = None
    period_end: date


class Hypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["hypothesis"]
    text: str = Field(min_length=1, max_length=1200)


def validate_financial_claims(report: str, package: EvidencePackage) -> dict:
    """Replace unvalidated prose with deterministic values from cited facts.

    The original narrative stays available for diagnosis and saved research,
    but is never the canonical financial context. Matching a model's small
    claim list does not establish core evidence coverage or accounting quality.
    """
    fence = chr(96) * 3
    matches = re.findall(fence + r"financial_claims\s*\n(.*?)\n" + fence, report, re.S)
    reasons, accepted, hypotheses = [], [], []
    if len(matches) != 1 or len(matches[0]) > 48000:
        reasons.append("Missing, duplicate or oversized material financial claim extraction")
        rows = []
    else:
        try:
            rows = json.loads(matches[0])
            if not isinstance(rows, list) or len(rows) > 32:
                raise ValueError()
        except (ValueError, TypeError):
            reasons.append("Malformed material financial claim extraction")
            rows = []
    facts = {fact.fact_id: fact for fact in package.facts}
    for index, row in enumerate(rows):
        try:
            if isinstance(row, dict) and row.get("kind") == "hypothesis":
                hypotheses.append(Hypothesis.model_validate(row).text)
                continue
            claim = FinancialClaim.model_validate(row)
        except ValidationError:
            reasons.append(f"Claim {index}: malformed fields")
            continue
        fact = facts.get(claim.fact_id)
        if fact is None or fact.value is None:
            reasons.append(f"Claim {index}: unavailable canonical fact")
            continue
        if (
            claim.kind,
            claim.metric,
            claim.value,
            claim.unit,
            claim.period_start,
            claim.period_end,
        ) != (fact.origin, fact.metric, fact.value, fact.unit, fact.period_start, fact.period_end):
            reasons.append(
                f"Claim {index}: value, definition, period or origin contradicts canonical fact"
            )
            continue
        if fact not in accepted:
            accepted.append(fact)
    if not accepted:
        reasons.append("No grounded material financial claims")
    lines = [
        "Canonical financial evidence",
        "These values are rendered from source records; the original narrative is unvalidated research.",
    ]
    for fact in accepted:
        period = (
            f"{fact.period_start} to {fact.period_end}"
            if fact.period_start
            else str(fact.period_end)
        )
        lines.append(
            f"- {fact.metric}: {fact.value} {fact.unit}; {period}; {fact.origin}; fact {fact.fact_id}; sources {', '.join(fact.source_ids)}"
        )
    return {
        "status": "unavailable" if reasons else "pass",
        "reasons": reasons,
        "fact_ids": [fact.fact_id for fact in accepted],
        "canonical_summary": "\n".join(lines),
        "hypotheses": hypotheses,
        "raw_report": report,
    }


def validate_calculation_lineage(package: EvidencePackage) -> list[str]:
    """Replay only named supported derivations; unresolved cycles never pass."""
    from tradingagents.dataflows.financial_evidence import (
        derive_cash_outflow,
        derive_quarter,
        derive_ttm,
    )

    ready = {fact.fact_id: fact for fact in package.facts if fact.origin == "reported"}
    pending = [fact for fact in package.facts if fact.origin == "derived"]
    reasons = []
    while pending:
        next_pending = []
        for fact in pending:
            if any(parent not in ready for parent in fact.input_fact_ids):
                next_pending.append(fact)
                continue
            inputs = [ready[parent] for parent in fact.input_fact_ids]
            try:
                if fact.formula_id == "cumulative_difference_v1" and len(inputs) == 2:
                    expected = derive_quarter(*inputs)
                elif fact.formula_id == "reported_cash_outflow_magnitude_v1" and len(inputs) == 1:
                    expected = derive_cash_outflow(inputs[0])
                elif fact.formula_id == "four_quarter_sum_v1":
                    expected = derive_ttm(inputs)
                else:
                    raise ValueError("unsupported formula")
                if expected != fact:
                    raise ValueError("calculation differs from canonical inputs")
            except (ValueError, TypeError) as exc:
                reasons.append(f"{fact.fact_id}: {exc}")
                continue
            ready[fact.fact_id] = fact
        if len(next_pending) == len(pending):
            reasons.append("Missing, invalid or cyclic derivation input references")
            break
        pending = next_pending
    return reasons


def latest_balance_check(package: EvidencePackage):
    """Reconcile one common latest balance date, never stale cross-date inputs."""
    from tradingagents.agents.accounting_checks import Calculation, check_balance_sheet

    metrics = ("Total Assets", "Total Liabilities", "Stockholders Equity")
    balances = [
        f
        for f in package.facts
        if f.metric in metrics and f.period_start is None and f.value is not None
    ]
    if not balances:
        return Calculation(
            method="assets_equals_liabilities_plus_equity_v1",
            status="unavailable",
            reason_code="missing_core_balance",
            message="Core balance-sheet evidence unavailable",
        )
    end = max(f.period_end for f in balances)
    ids = []
    for metric in metrics:
        selected = [f for f in balances if f.metric == metric and f.period_end == end]
        if len({(f.value, f.unit, f.basis) for f in selected}) != 1:
            return Calculation(
                method="assets_equals_liabilities_plus_equity_v1",
                status="unavailable",
                reason_code="missing_or_ambiguous_core_balance",
                message=f"{metric} unavailable or ambiguous at common balance date {end}",
                input_fact_ids=tuple(ids),
            )
        ids.append(selected[0].fact_id)
    return check_balance_sheet(package, *ids, precision={})


REQUIRED_FINANCIAL_CHECKS = (
    "source_integrity",
    "core_statements",
    "balance_sheet",
    "equity_movement",
    "obligation_perimeter",
    "cash_flow_perimeter",
    "disclosure_coverage",
    "material_claims",
)


def evidence_quality(checks: list[dict]) -> dict:
    """Aggregate executed checks; omitted critical checks never imply success."""
    by_code = {}
    for check in checks:
        if check["code"] in by_code:
            raise ValueError("duplicate evidence check code")
        if check["status"] not in {"pass", "fail", "unavailable", "not_applicable"}:
            raise ValueError("unknown evidence check status")
        by_code[check["code"]] = dict(check)
    for code in REQUIRED_FINANCIAL_CHECKS:
        by_code.setdefault(
            code,
            {
                "code": code,
                "status": "unavailable",
                "message": "Required evidence check not completed",
            },
        )
    critical = [by_code[code] for code in REQUIRED_FINANCIAL_CHECKS]
    # Applicability is decided before invoking this US-filer aggregator. A
    # critical check cannot bypass this scope by claiming not_applicable.
    insufficient = any(check["status"] != "pass" for check in critical)
    warnings = [
        check
        for code, check in by_code.items()
        if code not in REQUIRED_FINANCIAL_CHECKS and check["status"] in {"fail", "unavailable"}
    ]
    return {
        "schema_version": 1,
        "scope": "Selected US SEC-filer fundamentals",
        "status": "insufficient" if insufficient else ("limited" if warnings else "sufficient"),
        "checks": list(by_code.values()),
        "warnings": [check["message"] for check in warnings],
    }


def review_terminal_state(quality: dict) -> dict:
    """Complete skipped-node fields while retaining the graph's saved research."""
    reasons = [
        check["message"]
        for check in quality["checks"]
        if check["status"] in {"fail", "unavailable"}
    ]
    explanation = "Research incomplete — REVIEW\n\n" + "\n".join(
        "- " + reason for reason in dict.fromkeys(reasons)
    )
    explanation += "\n\nNo actionable trading decision was produced. The research remains available for inspection."
    return {
        "evidence_quality": quality,
        "final_rating": "REVIEW",
        "final_trade_decision": explanation,
        "investment_plan": "",
        "trader_investment_plan": "",
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "count": 0,
        },
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 0,
        },
    }


def create_evidence_gate(selected_analysts):
    """Acquire canonical evidence outside model choice, then assess selected scope."""
    from tradingagents.dataflows.errors import VendorError
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar

    def out_of_scope(reason):
        return {
            "evidence_quality": {
                "schema_version": 1,
                "scope": "not_applicable",
                "status": "limited",
                "checks": [{"code": "scope", "status": "not_applicable", "message": reason}],
                "warnings": [reason],
            }
        }

    def gate(state):
        if "fundamentals" not in selected_analysts:
            return out_of_scope("Fundamentals not selected; no US accounting validation performed")
        if state.get("asset_type", "stock") != "stock":
            return out_of_scope("Non-stock asset; US-filer accounting checks do not apply")
        try:
            if sec_edgar.cik_for(state["company_of_interest"]) is None:
                return out_of_scope(
                    "Instrument not identified in SEC issuer map; no US accounting validation performed"
                )
            package = sec_edgar.get_financial_evidence(
                state["company_of_interest"], state["trade_date"]
            )
        except (VendorError, ValidationError, ValueError) as exc:
            quality = evidence_quality(
                [{"code": "source_integrity", "status": "unavailable", "message": str(exc)}]
            )
            return review_terminal_state(quality)
        try:
            disclosures = sec_documents.get_filing_evidence(
                state["company_of_interest"], state["trade_date"]
            )
        except (VendorError, ValidationError, ValueError) as exc:
            return assess_financial_package(state, package, disclosure_error=str(exc))
        return assess_financial_package(state, package, disclosures)

    return gate


def assess_financial_package(
    state: dict, package: EvidencePackage, disclosures=None, disclosure_error=None
) -> dict:
    """Assess available canonical evidence; unfinished critical bridges remain unavailable."""
    calculations = []
    extraction = None
    source_errors = []
    if disclosures is not None:
        try:
            package, calculations, extraction = filing_accounting_evidence(package, disclosures)
        except (ValueError, ValidationError) as exc:
            source_errors.append(str(exc))
    lineage = [
        *source_errors,
        *validate_calculation_lineage(package),
        *reported_fact_conflicts(package),
    ]
    claims = validate_financial_claims(state.get("fundamentals_report", ""), package)
    balance = latest_balance_check(package)
    checks = [
        core_statement_check(package),
        {
            "code": "source_integrity",
            "status": "fail" if lineage else "pass",
            "message": "; ".join(lineage)
            if lineage
            else "Canonical source references and supported derivations checked",
        },
        {"code": "balance_sheet", "status": balance.status, "message": balance.message},
        {
            "code": "material_claims",
            "status": claims["status"],
            "message": "; ".join(claims["reasons"])
            if claims["reasons"]
            else "Material fact claims matched canonical values; original prose retained as unvalidated",
        },
    ]
    if calculations:
        equity = calculations[0]
        checks.append(
            {"code": "equity_movement", "status": equity.status, "message": equity.message}
        )
    for i, adjusted in enumerate(calculations[1:]):
        checks.append(
            {
                "code": f"optional_adjusted_bridge_{i}",
                "status": adjusted.status,
                "message": adjusted.message,
            }
        )
        if adjusted.status == "fail":
            source_check = next(check for check in checks if check["code"] == "source_integrity")
            source_check["status"] = "fail"
            source_check["message"] += (
                "; management-adjusted reconciliation failed: " + adjusted.message
            )
    obligations = obligation_checks(package)
    calculations.extend(obligations)
    checks.append(
        {
            "code": "obligation_perimeter",
            "status": obligations[-1].status,
            "message": obligations[-1].message,
        }
    )
    cash_results, cash_check, cash_warnings = cash_flow_checks(package, disclosures)
    calculations.extend(cash_results)
    checks.append(cash_check)
    checks.extend(
        {"code": f"optional_cash_scope_{i}", "status": "unavailable", "message": warning}
        for i, warning in enumerate(cash_warnings)
    )
    checks.append(disclosure_coverage_check(package, disclosures, disclosure_error))
    earnings = earnings_checks(package, extraction.rounding_quantum_by_fact if extraction else {})
    calculations.extend(earnings)
    for i, calculation in enumerate(earnings):
        if calculation.status == "fail":
            source_check = next(check for check in checks if check["code"] == "source_integrity")
            source_check["status"] = "fail"
            source_check["message"] += "; earnings reconciliation failed: " + calculation.message
        checks.append(
            {
                "code": f"optional_earnings_bridge_{i}",
                "status": calculation.status,
                "message": calculation.message,
            }
        )
    disclosure_summary = ""
    if disclosures is not None:
        from tradingagents.dataflows.disclosure_evidence import parse_disclosure_report

        blocks = {
            (doc.source_id, block.locator): block.section + "\n" + block.text
            for doc in disclosures.documents
            for block in doc.blocks
        }
        grounded = parse_disclosure_report(state.get("fundamentals_report", ""), blocks)
        disclosure_lines = [
            "Source-grounded disclosure excerpts (definitions and stated periods retained)"
        ]
        for claim in grounded.claims:
            disclosure_lines.append(
                f"- {claim.kind}: {claim.quote} Definition: {claim.definition or 'not extracted'}. Source {claim.source_id}, {claim.locator}"
            )
        disclosure_summary = "\n".join(disclosure_lines) if grounded.claims else ""
        notices = [*grounded.rejected, *grounded.warnings]
        if not grounded.claims:
            notices.append(
                "No operating KPI or guidance record extracted; do not invent undisclosed metrics or consensus."
            )
        checks.extend(
            {"code": f"optional_disclosure_{i}", "status": "unavailable", "message": notice}
            for i, notice in enumerate(notices)
        )
    if disclosures is not None:
        checks.extend(
            {"code": f"optional_source_scope_{i}", "status": "unavailable", "message": gap}
            for i, gap in enumerate(disclosures.gaps)
            if "Document text limit reached" in gap
            or "Older submissions archive not retrieved" in gap
        )
    quality = evidence_quality(checks)
    update = {
        "financial_evidence": package.model_dump(mode="json"),
        "financial_calculations": [
            balance.model_dump(mode="json"),
            *(c.model_dump(mode="json") for c in calculations),
        ],
        "financial_claim_validation": claims,
        "evidence_quality": quality,
        "canonical_financial_context": canonical_accounting_context(
            package, [balance, *calculations]
        ),
    }
    if quality["warnings"]:
        update["canonical_financial_context"] += "\n\nEvidence coverage warnings:\n" + "\n".join(
            "- " + warning for warning in quality["warnings"]
        )
    if disclosure_summary:
        update["canonical_financial_context"] += "\n\n" + disclosure_summary
    if disclosures is not None:
        update["filing_evidence"] = disclosures.model_dump(mode="json")
    if extraction is not None:
        update["filing_fact_extraction"] = extraction.model_dump(mode="json")
    if quality["status"] == "insufficient":
        update.update(review_terminal_state(quality))
    else:
        update["fundamentals_report"] = (
            claims["canonical_summary"] + "\n\n" + update["canonical_financial_context"]
        )
    return update


def core_statement_check(package: EvidencePackage) -> dict:
    """Require statements at one balance date, retaining each duration explicitly."""
    code = "core_statements"
    valid = [f for f in package.facts if f.value is not None and f.basis == "US-GAAP"]
    assets = [f for f in valid if f.metric == "Total Assets" and f.period_start is None]
    if not assets:
        return {
            "code": code,
            "status": "unavailable",
            "message": "Latest balance-sheet date unavailable",
        }
    end = max(f.period_end for f in assets)
    units = {f.unit for f in assets if f.period_end == end}
    missing = []
    for metric in (
        "Total Assets",
        "Total Liabilities",
        "Stockholders Equity",
        "Revenue",
        "Net Income",
        "Operating Cash Flow",
    ):
        duration = metric in {"Revenue", "Net Income", "Operating Cash Flow"}
        found = [
            f
            for f in valid
            if f.metric == metric
            and f.period_end == end
            and (f.period_start is not None) == duration
        ]
        if not found or any(f.unit not in units for f in found) or len(units) != 1:
            missing.append(metric)
    return {
        "code": code,
        "status": "unavailable" if missing else "pass",
        "message": f"Missing or incompatible statements at {end}: {', '.join(missing)}"
        if missing
        else f"Core statements cover {end}; quarter and YTD durations remain separately labeled",
    }


def filing_accounting_evidence(package, disclosures):
    """Use independently verified filing cells, never model-supplied amounts."""
    from tradingagents.agents.accounting_checks import Calculation, check_equity_rollforward
    from tradingagents.dataflows.filing_facts import discover_filing_cells, verify_filing_cells

    if package.cik != disclosures.cik or package.as_of != disclosures.as_of:
        raise ValueError("Filing package issuer or cutoff mismatch")
    extraction = verify_filing_cells(disclosures, discover_filing_cells(disclosures))
    sources = {s.source_id: s for s in package.sources}
    facts = {f.fact_id: f for f in package.facts}
    for source in extraction.evidence.sources:
        if source.source_id in sources and sources[source.source_id] != source:
            raise ValueError("Conflicting source identifier")
        sources[source.source_id] = source
    for fact in extraction.evidence.facts:
        if fact.fact_id in facts and facts[fact.fact_id] != fact:
            raise ValueError("Conflicting fact identifier")
        facts[fact.fact_id] = fact
    from tradingagents.dataflows.financial_evidence import derive_cash_outflow

    for fact in tuple(facts.values()):
        if (
            fact.metric == "Equipment Financing Principal Payments"
            and fact.origin == "reported"
            and fact.value is not None
            and fact.value < 0
        ):
            normalized = derive_cash_outflow(fact)
            facts[normalized.fact_id] = normalized
    merged = EvidencePackage(
        cik=package.cik,
        as_of=package.as_of,
        scope=package.scope,
        sources=tuple(sources.values()),
        facts=tuple(facts.values()),
        warnings=(*package.warnings, *extraction.gaps),
    )
    assets = [f for f in package.facts if f.metric == "Total Assets" and f.value is not None]
    end = max((f.period_end for f in assets), default=None)
    coverage = [
        c
        for c in extraction.equity_coverage
        if c.period_end and (end is None or c.period_end == end)
    ]
    if not coverage:
        equity = Calculation(
            method="opening_equity_plus_disclosed_movements_v1",
            status="unavailable",
            reason_code="equity_source_unavailable",
            message="Complete dated equity-movement table unavailable",
        )
    else:
        selected = max(
            coverage,
            key=lambda c: (c.period_end, -(c.period_start.toordinal() if c.period_start else 0)),
        )
        equity = check_equity_rollforward(
            merged,
            selected.opening_fact_id or "missing-opening-equity",
            selected.closing_fact_id or "missing-closing-equity",
            selected.signed_components,
            selected.complete,
            extraction.rounding_quantum_by_fact,
        )
    from tradingagents.agents.accounting_checks import check_adjusted_bridge

    adjusted = [
        check_adjusted_bridge(
            merged,
            coverage.gaap_fact_id or "missing-gaap-base",
            coverage.adjusted_fact_id or "missing-adjusted-result",
            coverage.signed_components,
            coverage.complete,
            extraction.rounding_quantum_by_fact,
        )
        for coverage in extraction.adjusted_coverage
        if end is None or coverage.period_end == end
    ]
    return merged, [equity, *adjusted], extraction


def reported_fact_conflicts(package):
    groups = {}
    for fact in package.facts:
        if fact.origin == "reported" and fact.value is not None:
            key = (fact.metric, fact.unit, fact.period_start, fact.period_end, fact.basis)
            groups.setdefault(key, set()).add(fact.value)
    return [
        f"Conflicting reported values for {key[0]} at {key[3]}"
        for key, values in groups.items()
        if len(values) > 1
    ]


def disclosure_coverage_check(package, disclosures, error=None):
    code = "disclosure_coverage"
    if disclosures is None:
        return {
            "code": code,
            "status": "unavailable",
            "message": error or "Dated filing disclosure package unavailable",
        }
    if disclosures.cik != package.cik or disclosures.as_of != package.as_of:
        return {"code": code, "status": "fail", "message": "Filing issuer or cutoff mismatch"}
    dates = [
        f.period_end for f in package.facts if f.metric == "Total Assets" and f.value is not None
    ]
    end = max(dates, default=None)
    primary = [
        doc
        for doc in disclosures.documents
        if doc.filing.form in {"10-Q", "10-K"} and doc.filing.report_date == end and doc.blocks
    ]
    if not primary:
        return {
            "code": code,
            "status": "unavailable",
            "message": "Primary filing at latest statement date unavailable",
        }
    # Text excerpts are explicitly bounded; completeness of accounting tables
    # is separately established by the cell verifier. Acquisition failures and
    # omitted filings/exhibits remain critical.
    informational = ("Document text limit reached", "Older submissions archive not retrieved")
    critical = [gap for gap in disclosures.gaps if not any(text in gap for text in informational)]
    return {
        "code": code,
        "status": "unavailable" if critical else "pass",
        "message": "; ".join(critical)
        if critical
        else "Dated primary filing and selected subsequent disclosure retrieval checked; excerpt scope remains explicit",
    }


def _instant_at(package, metric, end):
    candidates = [
        f
        for f in package.facts
        if f.metric == metric
        and f.period_end == end
        and f.period_start is None
        and f.value is not None
    ]
    meanings = {(f.value, f.unit, f.basis) for f in candidates}
    return candidates[0] if len(meanings) == 1 else None


def obligation_checks(package):
    """Require complete named perimeters; do not infer missing categories as zero."""
    from tradingagents.agents.accounting_checks import calculate_obligations

    end = max(
        (f.period_end for f in package.facts if f.metric == "Total Assets" and f.value is not None),
        default=None,
    )

    def selected(metric):
        return _instant_at(package, metric, end)

    def identifiers(*facts):
        return tuple(f.fact_id for f in facts if f is not None)

    def total_or_components(total_name, current_name, noncurrent_name):
        total, current, noncurrent = map(selected, (total_name, current_name, noncurrent_name))
        if total:
            if (
                current
                and noncurrent
                and (
                    current.unit != total.unit
                    or noncurrent.unit != total.unit
                    or current.value + noncurrent.value != total.value
                )
            ):
                return ()
            return identifiers(total)
        return identifiers(current, noncurrent) if current and noncurrent else ()

    groups = {}
    total = selected("Total Borrowings")
    long_term = total_or_components(
        "Long-term Borrowings (including current)",
        "Current Long-term Borrowings",
        "Noncurrent Long-term Borrowings",
    )
    short_term = selected("Short-term Borrowings")
    if total:
        groups["borrowings"] = identifiers(total)
        if long_term and short_term:
            by_id = {f.fact_id: f for f in package.facts}
            parts = [by_id[i] for i in long_term] + [short_term]
            if (
                any(f.unit != total.unit for f in parts)
                or sum(f.value for f in parts) != total.value
            ):
                groups["borrowings"] = ()
    elif long_term and short_term:
        groups["borrowings"] = (*long_term, short_term.fact_id)
    combined = selected("Finance Lease and Equipment Obligations")
    finance = total_or_components(
        "Finance Lease Liabilities",
        "Current Finance Lease Liabilities",
        "Noncurrent Finance Lease Liabilities",
    )
    equipment = selected("Equipment Financing Obligations")
    if combined:
        groups["finance_equipment"] = identifiers(combined)
        if finance and equipment:
            by_id = {f.fact_id: f for f in package.facts}
            parts = [by_id[i] for i in finance] + [equipment]
            if (
                any(f.unit != combined.unit for f in parts)
                or sum(f.value for f in parts) != combined.value
            ):
                groups["finance_equipment"] = ()
    else:
        groups["finance_leases"] = finance
        groups["equipment"] = identifiers(equipment)
    groups["operating_leases"] = total_or_components(
        "Operating Lease Liabilities",
        "Current Operating Lease Liabilities",
        "Noncurrent Operating Lease Liabilities",
    )
    cash = selected("Cash and Equivalents")
    return calculate_obligations(
        package, groups, cash.fact_id if cash else "missing-unrestricted-cash"
    )


def _duration_at(package, metric, start, end):
    candidates = [
        f
        for f in package.facts
        if f.metric == metric
        and f.period_start == start
        and f.period_end == end
        and f.value is not None
    ]
    signed_inputs = {
        parent
        for f in candidates
        if f.formula_id == "reported_cash_outflow_magnitude_v1"
        for parent in f.input_fact_ids
    }
    candidates = [f for f in candidates if f.fact_id not in signed_inputs]
    if len({(f.value, f.unit, f.basis) for f in candidates}) != 1:
        return None
    return candidates[0]


def cash_flow_checks(package, disclosures=None):
    """Publish enumerated cash investment separately from lease/equipment principal."""
    from tradingagents.agents.accounting_checks import calculate_cash_generation

    end = max(
        (f.period_end for f in package.facts if f.metric == "Total Assets" and f.value is not None),
        default=None,
    )
    ocfs = [
        f
        for f in package.facts
        if f.metric == "Operating Cash Flow"
        and f.period_end == end
        and f.period_start
        and f.value is not None
    ]
    start = min((f.period_start for f in ocfs), default=None)

    def lookup(metric):
        return _duration_at(package, metric, start, end)

    ocf, capex, software, lease, equipment, unclassified = map(
        lookup,
        (
            "Operating Cash Flow",
            "Capital Expenditure",
            "Software Development Payments",
            "Finance Lease Principal Payments",
            "Equipment Financing Principal Payments",
            "Equipment on Lease Payments",
        ),
    )
    warnings, reasons = [], []
    if software is None:
        warnings.append(
            "Software capital spending not separately available; the cash measure includes only enumerated spending, not an assumed zero."
        )
        text = (
            " ".join(block.text for doc in disclosures.documents for block in doc.blocks)
            if disclosures
            else ""
        )
        if re.search(
            r"capitalized software|capitalised software|payments to develop software|capitalization of software",
            text,
            re.I,
        ):
            reasons.append("Disclosed software capitalization lacks a compatible cash amount")
    if (
        unclassified
        and unclassified.value != 0
        and (
            equipment is None
            or equipment.unit != unclassified.unit
            or equipment.value != abs(unclassified.value)
        )
    ):
        reasons.append(
            "Equipment acquisition payments are not reconciled to explicitly classified financing principal"
        )
    principal = [f for f in (lease, equipment) if f is not None]
    if lease is None or equipment is None:
        reasons.append(
            "Lease/equipment principal cash-flow coverage unavailable; closing balances do not establish payments during the period"
        )
    # Core capex is mandatory. Unknown optional components are never supplied as zero.
    capex_ids = tuple(f.fact_id for f in (capex, software) if f is not None)
    results = calculate_cash_generation(
        package,
        ocf.fact_id if ocf else "missing-operating-cash",
        capex_ids,
        tuple(f.fact_id for f in principal),
        capex is not None,
    )
    if results[0].status != "pass":
        reasons.append(results[0].message)
    if lease is not None and equipment is not None and results[1].status != "pass":
        reasons.append(results[1].message)
    check = {
        "code": "cash_flow_perimeter",
        "status": "unavailable" if reasons else "pass",
        "message": "; ".join(dict.fromkeys(reasons))
        if reasons
        else "Enumerated cash capital spending and explicitly classified lease/equipment principal are separate measures",
    }
    return results, check, warnings


def canonical_accounting_context(package, calculations):
    """Render actual checked inputs and arithmetic independently of analyst prose."""
    by_id = {fact.fact_id: fact for fact in package.facts}
    selected = {
        ident
        for calculation in calculations
        for ident in calculation.input_fact_ids
        if ident in by_id
    }
    pending = list(selected)
    while pending:
        fact = by_id[pending.pop()]
        for parent in fact.input_fact_ids:
            if parent not in selected and parent in by_id:
                selected.add(parent)
                pending.append(parent)
    lines = [
        "Canonical accounting context — source values and deterministic checks",
        "This context controls financial arithmetic. It does not verify all narrative interpretations.",
    ]
    for calculation in calculations:
        value = str(calculation.result) if calculation.result is not None else "unavailable"
        lines.append(
            f"- {calculation.method}: {calculation.status}; result {value} {calculation.unit or ''}; {calculation.message}; inputs {', '.join(calculation.input_fact_ids)}"
        )
    for ident in sorted(selected):
        fact = by_id[ident]
        period = (
            f"{fact.period_start} to {fact.period_end}"
            if fact.period_start
            else str(fact.period_end)
        )
        lines.append(
            f"- Fact {ident}: {fact.metric} = {fact.value} {fact.unit}; {period}; {fact.origin}; sources {', '.join(fact.source_ids)}"
        )
    source_ids = {source_id for ident in selected for source_id in by_id[ident].source_ids}
    for source in package.sources:
        if source.source_id in source_ids:
            lines.append(
                f"- Source {source.source_id}: filed {source.filed_date}, {source.form}; {source.locator}; {source.url}"
            )
    return "\n".join(lines)


def earnings_checks(package, source_precision=None):
    """Match reported EPS to its own numerator and shares, never net-income guesses."""
    from tradingagents.agents.accounting_checks import check_eps

    assets = [
        f.period_end for f in package.facts if f.metric == "Total Assets" and f.value is not None
    ]
    fallback = [
        f.period_end
        for f in package.facts
        if f.metric in {"Basic EPS", "Diluted EPS"} and f.value is not None
    ]
    end = max(assets or fallback, default=None)
    results = []
    for basis in ("Basic", "Diluted"):
        eps_rows = [
            f
            for f in package.facts
            if f.metric == f"{basis} EPS"
            and f.period_end == end
            and f.period_start
            and f.value is not None
        ]
        start = max((f.period_start for f in eps_rows), default=None)
        numerator = _duration_at(package, f"{basis} Earnings Numerator", start, end)
        shares = _duration_at(package, f"Weighted Average {basis} Shares", start, end)
        eps = _duration_at(package, f"{basis} EPS", start, end)
        results.append(
            check_eps(
                package,
                numerator.fact_id if numerator else f"missing-{basis}-earnings-numerator",
                shares.fact_id if shares else f"missing-{basis}-weighted-shares",
                eps.fact_id if eps else f"missing-{basis}-eps",
                source_precision or {},
            )
        )
    return results
