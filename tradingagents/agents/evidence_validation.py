"""Deterministic evidence checks at the analyst-to-debate boundary."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, localcontext
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
        derive_parent_net_income,
        derive_quarter,
        derive_ttm,
    )

    sources = {source.source_id: source for source in package.sources}
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
                elif fact.formula_id == "consolidated_profit_less_nci_v1" and len(inputs) == 2:
                    if any(len(item.source_ids) != 1 or item.source_ids[0] not in sources
                           for item in inputs):
                        raise ValueError("parent income needs exact source references")
                    expected = derive_parent_net_income(
                        *inputs, *(sources[item.source_ids[0]] for item in inputs)
                    )
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


def latest_balance_check(package: EvidencePackage, source_precision=None):
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
        chosen = _select_compatible_fact(package, selected, source_precision)
        if chosen is None:
            return Calculation(
                method="assets_equals_liabilities_plus_equity_v1",
                status="unavailable",
                reason_code="missing_or_ambiguous_core_balance",
                message=f"{metric} unavailable or ambiguous at common balance date {end}",
                input_fact_ids=tuple(ids),
            )
        ids.append(chosen.fact_id)
    by_id = {fact.fact_id: fact for fact in package.facts}
    return check_balance_sheet(
        package,
        *ids,
        precision=_comparison_precision(package, [by_id[i] for i in ids], source_precision),
    )


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


def _outside_financial_scope(reason):
    return {
        "evidence_quality": {
            "schema_version": 1, "scope": "not_applicable", "status": "limited",
            "checks": [{"code": "scope", "status": "not_applicable", "message": reason}],
            "warnings": [reason],
        }
    }


def _acquisition_scope(state, selected_analysts):
    from tradingagents.dataflows.symbols import normalize_symbol

    return {
        "schema_version": 1,
        "ticker": normalize_symbol(state.get("company_of_interest", "")),
        "as_of": str(state.get("trade_date", "")),
        "asset_type": state.get("asset_type", "stock"),
        "selected_analysts": list(selected_analysts),
    }


def create_source_acquisition(selected_analysts):
    """Acquire one source vintage before analyst fan-out; never authorize publication."""
    from tradingagents.dataflows.errors import NoMarketDataError, VendorError
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar
    from tradingagents.operational_capture import record_operation

    def acquire(state):
        scope = _acquisition_scope(state, selected_analysts)
        retained = state.get("evidence_acquisition")
        if retained is not None:
            if any(retained.get(key) != value for key, value in scope.items()):
                raise ValueError("Retained evidence acquisition differs from run scope; start a fresh run")
            return {}  # A compatible resumed node must never replace its vintage.
        record = {**scope, "status": "not_applicable", "reason": "",
                  "raw_financial_evidence": None, "disclosure_error": None,
                  "rpo_comparison": None, "source_checks": []}
        update = {}
        if "fundamentals" not in selected_analysts:
            record["reason"] = "Fundamentals not selected; no US accounting validation performed"
        elif scope["asset_type"] != "stock":
            record["reason"] = "Non-stock asset; US-filer accounting checks do not apply"
        else:
            try:
                mapped_cik = sec_edgar.cik_for(scope["ticker"])
                if mapped_cik is None:
                    record["status"] = "unavailable"
                    record["reason"] = (
                        "Stock not identified in SEC issuer map; issuer filing status cannot be verified "
                        "and US accounting validation was not performed"
                    )
                else:
                    package = sec_edgar.get_financial_evidence(scope["ticker"], scope["as_of"])
                    if package.cik != mapped_cik or str(package.as_of) != scope["as_of"]:
                        raise ValueError("SEC financial package issuer or cutoff differs from requested instrument")
                    record["raw_financial_evidence"] = package.model_dump(mode="json")
                    record["status"] = "ready"
                    update["issuer_identity"] = {"ticker": scope["ticker"], "cik": mapped_cik,
                                                "as_of": scope["as_of"], "source": "SEC issuer map"}
                    disclosures = None
                    try:
                        disclosures = sec_documents.get_filing_evidence(scope["ticker"], scope["as_of"])
                        if disclosures.cik != package.cik or str(disclosures.as_of) != scope["as_of"]:
                            raise ValueError("SEC filing package issuer or cutoff differs from requested instrument")
                    except (VendorError, ValidationError, ValueError) as exc:
                        record_operation("vendor_no_data" if isinstance(exc, NoMarketDataError) else "vendor_unavailable", scope="SEC filings")
                        record["disclosure_error"] = str(exc)
                        disclosures = None
                    if disclosures is not None:
                        from tradingagents.agents.kpi_comparisons import retrieve_rpo_comparison

                        record["rpo_comparison"] = retrieve_rpo_comparison(scope["ticker"], disclosures)
                    from tradingagents.agents.document_access import prepare_document_sources

                    if disclosures is not None:
                        update["filing_evidence"] = disclosures.model_dump(mode="json")
                    update.update(prepare_document_sources({**state, **update}, selected_analysts))
                    prepared = assess_financial_package(
                        {**state, **update}, package, disclosures, record["disclosure_error"],
                        rpo_comparison=record["rpo_comparison"], source_only=True,
                    )
                    record["source_checks"] = prepared.pop("source_checks")
                    update.update(prepared)
            except (VendorError, ValidationError, ValueError) as exc:
                record_operation("vendor_no_data" if isinstance(exc, NoMarketDataError) else "vendor_unavailable", scope="SEC financial acquisition")
                record["status"] = "unavailable"
                record["reason"] = str(exc)
        # Price is independent of financial scope and critical-accounting status.
        from tradingagents.dataflows.config import get_config
        from tradingagents.dataflows.vendors.yahoo.price_observation import (
            completed_price_scope,
            get_price_observation,
        )

        config = get_config()
        chain = config.get("tool_vendors", {}).get("get_stock_data") or config.get("data_vendors", {}).get("core_stock_apis", "")
        if "yfinance" in {name.strip() for name in str(chain).split(",")}:
            dates = [date.fromisoformat(f["period_end"])
                     for f in update.get("financial_evidence", {}).get("facts", [])
                     if f["metric"] == "Cash and Equivalents" and f.get("value") is not None
                     and f.get("period_start") is None]
            with completed_price_scope(state):
                update["price_observation"] = get_price_observation(
                    scope["ticker"], scope["as_of"], max(dates, default=None))
        else:
            update["price_observation"] = {"status": "unavailable",
                "reason": "No supported dated-close provider is configured; no additional vendor was used"}
        update["evidence_acquisition"] = record
        from tradingagents.agents.document_access import prepare_document_sources

        update.update(prepare_document_sources({**state, **update}, selected_analysts))
        from tradingagents.agents.filing_terms import prepare_filing_terms

        update.update(prepare_filing_terms({**state, **update}))
        from tradingagents.agents.transcript_access import prepare_transcript_sources

        update.update(prepare_transcript_sources({**state, **update}, selected_analysts))
        from tradingagents.agents.valuation_reference_flow import acquire_reference_inputs

        update.update(acquire_reference_inputs({**state, **update}, config))
        from tradingagents.agents.context import build_shared_source_brief

        update["shared_source_brief"] = build_shared_source_brief({**state, **update})
        return update

    return acquire


def create_evidence_gate(selected_analysts):
    """Validate model claims against the retained source vintage after all analysts."""
    def gate(state):
        retained = state.get("evidence_acquisition")
        if retained is None:
            # Narrow compatibility for direct callers outside the compiled graph.
            if "fundamentals" not in selected_analysts:
                return _outside_financial_scope("Fundamentals not selected; no US accounting validation performed")
            if state.get("asset_type", "stock") != "stock":
                return _outside_financial_scope("Non-stock asset; US-filer accounting checks do not apply")
            acquired = create_source_acquisition(selected_analysts)(state)
            return {**acquired, **gate({**state, **acquired})}
        scope = _acquisition_scope(state, selected_analysts)
        if any(retained.get(key) != value for key, value in scope.items()):
            quality = evidence_quality([{"code": "source_integrity", "status": "unavailable",
                "message": "Retained evidence acquisition differs from run scope; start a fresh run"}])
            return review_terminal_state(quality)
        if retained["status"] == "not_applicable":
            return _outside_financial_scope(retained["reason"])
        if retained["status"] != "ready":
            return review_terminal_state(evidence_quality([
                {"code": "source_integrity", "status": "unavailable", "message": retained["reason"]}]))
        from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

        try:
            package = EvidencePackage.model_validate(retained["raw_financial_evidence"])
            disclosures = (DisclosurePackage.model_validate(state["filing_evidence"])
                           if state.get("filing_evidence") and not retained.get("disclosure_error") else None)
            if package.cik != state.get("issuer_identity", {}).get("cik") or str(package.as_of) != scope["as_of"]:
                raise ValueError("Retained financial package issuer or cutoff mismatch")
            if disclosures is not None and (disclosures.cik, disclosures.as_of) != (package.cik, package.as_of):
                raise ValueError("Retained filing package issuer or cutoff mismatch")
        except (KeyError, ValidationError, ValueError) as exc:
            return review_terminal_state(evidence_quality([
                {"code": "source_integrity", "status": "unavailable", "message": str(exc)}]))
        return assess_financial_package(
            state, package, disclosures, retained.get("disclosure_error"),
            rpo_comparison=retained.get("rpo_comparison"),
        )

    return gate


def assess_financial_package(
    state: dict, package: EvidencePackage, disclosures=None, disclosure_error=None, *, rpo_comparison=None, source_only=False
) -> dict:
    """Assess available canonical evidence; unfinished critical bridges remain unavailable."""
    from tradingagents.agents.document_access import validated_document_corpus
    from tradingagents.dataflows.vendors.sec_edgar import confirm_current_marketable_securities

    package = confirm_current_marketable_securities(package, validated_document_corpus(state))
    if rpo_comparison is not None:
        from tradingagents.agents.kpi_comparisons import replay_rpo_comparison

        rpo_comparison = replay_rpo_comparison(rpo_comparison, cik=package.cik, as_of=package.as_of)
    calculations = []
    extraction = None
    source_errors = []
    search_packages = []
    if not source_only:
        from tradingagents.agents.document_access import retained_search_packages

        try:
            search_packages = retained_search_packages(state)
        except ValueError as exc:
            source_errors.append(f"Retained document search integrity: {exc}")
    quote_packages = tuple(([disclosures] if disclosures is not None else []) + search_packages)
    if quote_packages:
        try:
            if disclosures is not None:
                package, calculations, extraction = filing_accounting_evidence(package, disclosures)
            # Outlooks cite full filing excerpts, not only the accounting cells
            # selected elsewhere. Register their canonical document provenance
            # without replacing an existing ID with different source metadata.
            from tradingagents.dataflows.financial_evidence import SourceRecord

            sources = {source.source_id: source for source in package.sources}
            document_ids = set()
            quote_documents = {}
            for quote_package in quote_packages:
                for document in quote_package.documents:
                    previous = quote_documents.get(document.source_id)
                    if previous and (previous.filing != document.filing
                                     or previous.url != document.url
                                     or previous.content_hash != document.content_hash):
                        raise ValueError("conflicting retained filing source metadata")
                    quote_documents.setdefault(document.source_id, document)
            for document in quote_documents.values():
                if document.source_id in document_ids:
                    raise ValueError("duplicate canonical filing document source ID")
                document_ids.add(document.source_id)
                if document.filing.cik != package.cik or document.filing.filed_date > package.as_of:
                    raise ValueError("filing document source issuer or cutoff mismatch")
                source = SourceRecord(
                    source_id=document.source_id,
                    cik=document.filing.cik,
                    url=document.url,
                    filed_date=document.filing.filed_date,
                    retrieved_at=document.retrieved_at,
                    content_hash=document.content_hash,
                    locator="document",
                    accession=document.filing.accession,
                    form=document.filing.form,
                )
                if source.source_id in sources and sources[source.source_id] != source:
                    raise ValueError("canonical filing document source ID collision")
                sources[source.source_id] = source
            package = EvidencePackage.model_validate(
                {
                    **package.model_dump(),
                    "sources": tuple(sources.values()),
                }
            )
        except (ValueError, ValidationError) as exc:
            source_errors.append(str(exc))
    source_precision = extraction.rounding_quantum_by_fact if extraction else {}
    lineage = [
        *source_errors,
        *validate_calculation_lineage(package),
        *reported_fact_conflicts(package, source_precision),
    ]
    claims = ({"status": "unavailable", "reasons": ["Model claims are assessed after analyst reasoning"]}
              if source_only else validate_financial_claims(state.get("fundamentals_report", ""), package))
    balance = latest_balance_check(package, source_precision)
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
    obligations = obligation_checks(package, source_precision)
    calculations.extend(obligations)
    checks.append(
        {
            "code": "obligation_perimeter",
            "status": obligations[-1].status,
            "message": obligations[-1].message,
        }
    )
    cash_results, cash_check, cash_warnings = cash_flow_checks(
        package, disclosures, source_precision, extraction=extraction
    )
    calculations.extend(cash_results)
    checks.append(cash_check)
    for calculation in cash_results:
        checks.append({"code": "optional_cash_" + calculation.method,
                       "status": calculation.status, "message": calculation.message})
        if calculation.status == "fail":
            integrity = next(c for c in checks if c["code"] == "source_integrity")
            integrity["status"] = "fail"
            integrity["message"] += "; cash reconciliation failed: " + calculation.message
    checks.extend(
        {"code": f"optional_cash_scope_{i}", "status": "unavailable", "message": warning}
        for i, warning in enumerate(cash_warnings)
    )
    checks.append(disclosure_coverage_check(package, disclosures, disclosure_error))
    earnings = earnings_checks(package, source_precision)
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
    from tradingagents.agents.operating_metrics import operating_metrics

    operating = operating_metrics(package)
    calculations.extend(operating)
    checks.extend({"code": "optional_operating_" + c.method, "status": c.status,
                   "message": c.message} for c in operating)
    from tradingagents.agents.accounting_checks import check_cash_plus_marketable_securities

    calculations.append(check_cash_plus_marketable_securities(package))
    disclosure_summary = ""
    disclosure_references = []
    if quote_packages:
        from tradingagents.dataflows.disclosure_discovery import discover_disclosures
        from tradingagents.dataflows.disclosure_evidence import parse_disclosure_report

        blocks = {
            (doc.source_id, block.locator): block.section + "\n" + block.text
            for quote_package in quote_packages
            for doc in quote_package.documents
            for block in doc.blocks
        }
        discovered = discover_disclosures((disclosures,) if disclosures is not None else ())
        grounded = discovered if source_only else parse_disclosure_report(
            state.get("fundamentals_report", ""), blocks, packages=quote_packages)
        model_grounded = None if source_only else grounded
        # Deterministic proposals pass the same validator. Keep rejected model
        # submissions visible; accepted discovery never retroactively repairs them.
        accepted = {}
        for claim in (*discovered.claims, *grounded.claims):
            identity = (claim.source_id, claim.locator, claim.metric, claim.value,
                        claim.upper_value, claim.comparator, claim.tolerance_percent, claim.unit, claim.period, claim.kind)
            accepted.setdefault(identity, claim)
        grounded = grounded.model_copy(update={
            "claims": tuple(accepted.values()),
            "rejected": tuple(dict.fromkeys((*grounded.rejected, *discovered.rejected))),
            "warnings": tuple(dict.fromkeys((*grounded.warnings, *discovered.warnings))),
        })
        disclosure_lines = [
            "Source-grounded disclosure excerpts (definitions and stated periods retained)"
        ]
        source_labels = {
            source_id: f"D{i}"
            for i, source_id in enumerate(sorted({c.source_id for c in grounded.claims}), 1)
        }
        for document in {
            doc.source_id: doc for quote_package in quote_packages for doc in quote_package.documents
        }.values():
            if document.source_id in source_labels:
                disclosure_references.append(
                    f"- {source_labels[document.source_id]}: source_id {document.source_id}; {document.url}"
                )
        for claim in grounded.claims:
            source_label = source_labels[claim.source_id]
            disclosure_lines.append(
                f"- {'verified historical' if claim.kind == 'historical' else 'verified management statement'} ({claim.kind}): {claim.quote} Period: {claim.period}"
                f" ({source_label}, {claim.period_locator or claim.locator})."
                f" Definition: {claim.definition or 'not extracted'}"
                f" ({source_label}, {claim.definition_locator or claim.locator})."
                f" Value source {source_label}, {claim.locator}."
                + (f" Lower bound: ≥{claim.value}{claim.unit}; no upper bound supplied, not an exact forecast."
                   if claim.comparator == "at_least" else "")
                + (f" Central estimate: {claim.value} {claim.unit} ±{claim.tolerance_percent}%; "
                   "source qualifications retained; not an exact forecast."
                   if claim.comparator == "central_estimate" else "")
                + (
                    f" Reported comparison: {claim.comparison.quote}; year-over-year basis source"
                    f" {source_label}, {claim.comparison.basis_locator}. No comparator amount inferred."
                    if claim.comparison else ""
                )
            )
        disclosure_summary = "\n".join(disclosure_lines) if grounded.claims else ""
        notices = [*grounded.rejected, *grounded.warnings]
        if not grounded.claims:
            notices.append(
                "No operating KPI or guidance record extracted; do not invent undisclosed metrics or consensus."
            )
        if notices:
            # Keep the same optional-unavailable quality outcome without
            # flooding decision/report coverage with per-record diagnostics.
            # Full rejects and warnings remain in the extraction evidence.
            checks.append({"code": "optional_disclosure_summary", "status": "unavailable",
                "message": f"Disclosure extraction: {len(grounded.rejected)} validation rejection(s), "
                           f"{len(grounded.warnings)} warning(s); raw details retained in disclosure evidence."
                           + (" No supported operating KPI or guidance record extracted." if not grounded.claims else "")})
    if disclosures is not None:
        checks.extend(
            {"code": f"optional_source_scope_{i}", "status": "unavailable", "message": gap}
            for i, gap in enumerate(disclosures.gaps)
            if "Document text limit reached" in gap
            or "Older submissions archive not retrieved" in gap
        )
    if rpo_comparison is not None:
        checks.append({"code": "optional_rpo_comparison", "status": rpo_comparison["status"],
                       "message": rpo_comparison["reason"]})
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
    if quote_packages:
        update["disclosure_evidence"] = {
            "packages": [item.model_dump(mode="json") for item in quote_packages],
            "extraction": grounded.model_dump(mode="json"),
            "coverage_gaps": list(dict.fromkeys(gap for item in quote_packages for gap in item.gaps)),
            "model_extraction": model_grounded.model_dump(mode="json") if model_grounded is not None else None,
            "deterministic_extraction": discovered.model_dump(mode="json"),
            "submission_counts": {
                "model_accepted": len(model_grounded.claims) if model_grounded is not None else None,
                "model_rejected": len(model_grounded.rejected) if model_grounded is not None else None,
                "deterministic_accepted": len(discovered.claims),
                "deterministic_rejected": len(discovered.rejected),
            },
        }
    if rpo_comparison is not None and disclosures is not None:
        update["disclosure_evidence"]["kpi_comparisons"] = [rpo_comparison]
        update["canonical_financial_context"] += "\n\n" + rpo_comparison["text"]
        references = []
        for i, (role, source) in enumerate(rpo_comparison.get("sources", {}).items(), 1):
            label = f"K{i}"
            update["canonical_financial_context"] += (
                f" {role.capitalize()} RPO: {label}, {source['fact']['locator']}; "
                f"filed {source['known_at']}."
            )
            references.append(f"- {label}: source_id {source['source_id']}; {source['url']}")
        if references:
            from tradingagents.agents.evidence_presentation import REFERENCE_END

            update["canonical_financial_context"] = update["canonical_financial_context"].replace(
                REFERENCE_END, "\n" + "\n".join(references) + REFERENCE_END, 1,
            )
    if quality["warnings"]:
        update["canonical_financial_context"] += "\n\nEvidence coverage warnings:\n" + "\n".join(
            "- " + warning for warning in quality["warnings"]
        )
    if disclosure_summary:
        update["canonical_financial_context"] += "\n\n" + disclosure_summary
        from tradingagents.agents.evidence_presentation import REFERENCE_END

        update["canonical_financial_context"] = update["canonical_financial_context"].replace(
            REFERENCE_END, "\n" + "\n".join(disclosure_references) + REFERENCE_END, 1,
        )
    if disclosures is not None:
        update["filing_evidence"] = disclosures.model_dump(mode="json")
        from tradingagents.agents.valuation_outlooks import grounded_outlook_warnings

        conflicts = grounded_outlook_warnings({**state, **update, "trade_date": str(package.as_of)})
        if conflicts and "disclosure_evidence" in update:
            update["disclosure_evidence"]["warnings"] = list(conflicts)
            update["canonical_financial_context"] += "\n\nOutlook grounding warnings:\n" + "\n".join(
                "- " + warning for warning in conflicts
            )
    from tradingagents.agents.issuer_events import issuer_supplement
    supplement = issuer_supplement(
        state.get("news_coverage", {}), disclosures, cik=package.cik, as_of=str(package.as_of),
        accepted_source_ids={claim.source_id for claim in grounded.claims} if disclosures is not None else (),
    )
    update["issuer_event_evidence"] = supplement
    update["canonical_financial_context"] += "\n\nSource coverage: " + "; ".join(
        f"{name.replace('_', ' ')}: {item['status']}" for name, item in supplement["coverage"].items()
    )
    if supplement["financing_text"]:
        update["canonical_financial_context"] += "\n\n" + supplement["financing_text"]
    if supplement["text"]:
        update["canonical_financial_context"] += "\n\n" + supplement["text"]
    from tradingagents.agents.filing_terms import render_filing_terms

    terms = render_filing_terms(state)
    if terms:
        update["canonical_financial_context"] += "\n\n" + terms
    if source_only:
        if extraction is not None:
            update["filing_fact_extraction"] = extraction.model_dump(mode="json")
        update["source_checks"] = [check for check in checks if check["code"] != "material_claims"]
        update.pop("evidence_quality")
        update.pop("financial_claim_validation")
        return update
    if extraction is not None:
        update["filing_fact_extraction"] = extraction.model_dump(mode="json")
    if quality["status"] == "insufficient":
        update.update(review_terminal_state(quality))
    else:
        update["fundamentals_report"] = update["canonical_financial_context"]
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
            fact.metric
            in {
                "Equipment Financing Principal Payments",
                "Finance Lease and Financing Arrangement Principal Payments",
            }
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


def _known_quantum(package, fact, source_precision):
    """Only the deterministic filing parser supplies source rounding quantum."""
    precision = source_precision or {}
    value = precision.get(fact.fact_id)
    # The magnitude transformation changes sign, never source precision.
    if (
        value is None
        and fact.formula_id == "reported_cash_outflow_magnitude_v1"
        and len(fact.input_fact_ids) == 1
    ):
        value = precision.get(fact.input_fact_ids[0])
    if value is None:
        return None
    try:
        value = Decimal(str(value))
        return value if value.is_finite() and value >= 0 else None
    except (ValueError, ArithmeticError):
        return None


def _same_filing_vintage(package, facts):
    sources = {source.source_id: source for source in package.sources}
    vintages = set()
    for fact in facts:
        if not fact.source_ids:
            return False
        for identifier in fact.source_ids:
            source = sources.get(identifier)
            if source is None or not source.accession:
                return False
            vintages.add((source.cik, source.accession, source.filed_date, source.form))
    return len(vintages) == 1


def _rounding_bound(package, facts, source_precision):
    if not _same_filing_vintage(package, facts):
        return None
    quanta = [_known_quantum(package, fact, source_precision) for fact in facts]
    if all(quantum is None for quantum in quanta):
        return None
    with localcontext() as context:
        context.prec = 60
        # Unknown precision contributes no allowance. This does not infer its
        # source quantum from the number's trailing zeros.
        return sum((quantum for quantum in quanta if quantum is not None), Decimal(0)) / 2


def _select_compatible_fact(package, candidates, source_precision=None):
    if not candidates:
        return None
    keys = {(f.metric, f.unit, f.basis, f.period_start, f.period_end) for f in candidates}
    if len(keys) != 1:
        return None
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if left.value == right.value:
                continue
            bound = _rounding_bound(package, (left, right), source_precision)
            if bound is None or abs(left.value - right.value) > bound:
                return None
    # Keep every fact in the package; select one reproducible calculation input.
    # A parsed filed value retains its known source rounding for reconciliation.
    return min(
        candidates,
        key=lambda fact: (
            _known_quantum(package, fact, source_precision) is None,
            _known_quantum(package, fact, source_precision) or Decimal(0),
            fact.origin != "reported",
            fact.fact_id,
        ),
    )


def _comparison_precision(package, facts, source_precision):
    """Known allowances for a calculation, without inventing unknown precision."""
    if not _same_filing_vintage(package, facts):
        return {}
    values = {fact.fact_id: _known_quantum(package, fact, source_precision) for fact in facts}
    if not any(value is not None for value in values.values()):
        return {}
    return {
        identifier: value if value is not None else Decimal(0)
        for identifier, value in values.items()
    }


def _sum_matches(package, total, parts, source_precision):
    facts = [total, *parts]
    if len({(f.unit, f.basis, f.period_start, f.period_end) for f in facts}) != 1:
        return False
    with localcontext() as context:
        context.prec = 60
        residual = sum((f.value for f in parts), Decimal(0)) - total.value
    if residual == 0:
        return True
    bound = _rounding_bound(package, facts, source_precision)
    return bound is not None and abs(residual) <= bound


def reported_fact_conflicts(package, source_precision=None):
    groups = {}
    for fact in package.facts:
        if fact.origin == "reported" and fact.value is not None:
            key = (fact.metric, fact.unit, fact.period_start, fact.period_end, fact.basis)
            groups.setdefault(key, []).append(fact)
    return [
        f"Conflicting reported values for {key[0]} at {key[3]}"
        for key, facts in groups.items()
        if _select_compatible_fact(package, facts, source_precision) is None
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


def _instant_at(package, metric, end, source_precision=None):
    candidates = [
        f
        for f in package.facts
        if f.metric == metric
        and f.period_end == end
        and f.period_start is None
        and f.value is not None
    ]
    return _select_compatible_fact(package, candidates, source_precision)


def obligation_checks(package, source_precision=None):
    """Require complete named perimeters; do not infer missing categories as zero."""
    from tradingagents.agents.accounting_checks import calculate_obligations

    end = max(
        (f.period_end for f in package.facts if f.metric == "Total Assets" and f.value is not None),
        default=None,
    )

    def selected(metric):
        return _instant_at(package, metric, end, source_precision)

    def identifiers(*facts):
        return tuple(f.fact_id for f in facts if f is not None)

    def total_or_components(total_name, current_name, noncurrent_name):
        total, current, noncurrent = map(selected, (total_name, current_name, noncurrent_name))
        if total:
            if (
                current
                and noncurrent
                and not _sum_matches(package, total, (current, noncurrent), source_precision)
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
            if not _sum_matches(package, total, parts, source_precision):
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
            if not _sum_matches(package, combined, parts, source_precision):
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


def _duration_at(package, metric, start, end, source_precision=None):
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
    return _select_compatible_fact(package, candidates, source_precision)


def _canonical_filing_cash_fact(package, fact, disclosures):
    """Replay deterministic extraction; a source locator alone is not proof."""
    if disclosures is None or (package.cik, package.as_of) != (disclosures.cik, disclosures.as_of):
        return False
    from tradingagents.dataflows.filing_facts import discover_filing_cells, verify_filing_cells
    from tradingagents.dataflows.financial_evidence import derive_cash_outflow

    extracted = verify_filing_cells(disclosures, discover_filing_cells(disclosures)).evidence
    sources = {source.source_id: source for source in package.sources}
    canonical_sources = {source.source_id: source for source in extracted.sources}
    for original in extracted.facts:
        if original.metric != fact.metric or original.value is None:
            continue
        candidate = original
        if original.value < 0 and original.metric == (
            "Finance Lease and Financing Arrangement Principal Payments"
        ):
            candidate = derive_cash_outflow(original)
        if candidate != fact:
            continue
        return all(
            source_id in canonical_sources
            and sources.get(source_id) == canonical_sources[source_id]
            for source_id in original.source_ids
        )
    return False


def cash_flow_checks(package, disclosures=None, source_precision=None, *, extraction=None):
    """Publish enumerated cash investment separately from lease/equipment principal."""
    from tradingagents.agents.accounting_checks import (
        calculate_cash_after_acquisitions,
        calculate_cash_generation,
        cash_statement_reconciliations,
        check_financed_equipment_bridge,
    )

    end = max(
        (f.period_end for f in package.facts if f.metric == "Total Assets" and f.value is not None),
        default=None,
    )
    if end is None:
        end = max((f.period_end for f in package.facts
                   if f.metric == "Operating Cash Flow" and f.origin == "reported" and f.value is not None), default=None)
    ocfs = [
        f
        for f in package.facts
        if f.metric == "Operating Cash Flow"
        and f.period_end == end
        and f.period_start
        and f.value is not None
    ]
    # Use a filed statement duration for the primary cash perimeter. Derived
    # trailing-year and quarter facts remain available as supplemental evidence;
    # their longer/shorter spans must not displace the reported YTD statement.
    reported_ocfs = [f for f in ocfs if f.origin == "reported"]
    start = min((f.period_start for f in (reported_ocfs or ocfs)), default=None)

    def lookup(metric):
        return _duration_at(package, metric, start, end, source_precision)

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
    combined = lookup("Finance Lease and Financing Arrangement Principal Payments")
    if combined is not None and not _canonical_filing_cash_fact(package, combined, disclosures):
        reasons.append("Combined principal lacks verified same-period equipment scope")
        combined = None
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
    acquisition = lookup("Equipment Financing Acquisition Payments")
    proceeds = lookup("Equipment Financing Proceeds")
    financed_bridge = None
    if acquisition is not None or proceeds is not None:
        financed_bridge = check_financed_equipment_bridge(
            package,
            acquisition.fact_id if acquisition else "missing-financed-acquisition",
            proceeds.fact_id if proceeds else "missing-equipment-financing-proceeds",
            source_precision or {},
        )
        if not (
            acquisition
            and proceeds
            and _canonical_filing_cash_fact(package, acquisition, disclosures)
            and _canonical_filing_cash_fact(package, proceeds, disclosures)
        ):
            financed_bridge = financed_bridge.model_copy(
                update={
                    "status": "unavailable",
                    "reason_code": "financed_acquisition_source_unavailable",
                    "message": "Gross financed acquisition/proceeds lack canonical equipment scope",
                }
            )
        if financed_bridge.status != "pass":
            reasons.append(financed_bridge.message)
    acquisition_classified = bool(
        financed_bridge
        and financed_bridge.status == "pass"
        and unclassified
        and _same_filing_vintage(package, (acquisition, unclassified))
        and _sum_matches(
            package,
            acquisition.model_copy(update={"value": abs(acquisition.value)}),
            (unclassified.model_copy(update={"value": abs(unclassified.value)}),),
            source_precision,
        )
    )
    if unclassified and unclassified.value != 0 and not acquisition_classified:
        reasons.append(
            "Equipment acquisition payments lack a verified gross acquisition/proceeds bridge; "
            "acquisition is not financing principal"
        )
    principal = [combined] if combined else [f for f in (lease, equipment) if f is not None]
    if (
        combined
        and lease is not None
        and equipment is not None
        and not _sum_matches(package, combined, (lease, equipment), source_precision)
    ):
        reasons.append("Combined principal conflicts with separately reported components")
    if combined is None and (lease is None or equipment is None):
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
    if (combined or (lease is not None and equipment is not None)) and results[1].status != "pass":
        reasons.append(results[1].message)
    check = {
        "code": "cash_flow_perimeter",
        "status": "unavailable" if reasons else "pass",
        "message": "; ".join(dict.fromkeys(reasons))
        if reasons
        else "Enumerated cash capital spending and explicitly classified lease/equipment principal are separate measures",
    }
    if financed_bridge is not None:
        results = (*results, financed_bridge)
    if extraction is not None:
        statement = cash_statement_reconciliations(package, extraction, source_precision or {}, start=start, end=end)
        acquisition_ids = tuple(f.fact_id for f in (
            lookup("Intangible Asset Acquisition Payments"), lookup("Business Acquisition Payments")) if f is not None)
        after_acquisitions = calculate_cash_after_acquisitions(
            package, ocf.fact_id if ocf else "missing-operating-cash", capex_ids,
            tuple(f.fact_id for f in principal), acquisition_ids, capex is not None,
        )
        results = (*results, *statement, after_acquisitions)
    return results, check, warnings


def canonical_accounting_context(package, calculations):
    """Render readable values once, with a separate exact-ID reference index."""
    from tradingagents.agents.evidence_presentation import REFERENCE_END, REFERENCE_START

    by_id = {fact.fact_id: fact for fact in package.facts}
    selected = {
        ident for calculation in calculations for ident in calculation.input_fact_ids
        if ident in by_id
    }
    core = {
        "Revenue", "Gross Profit", "Operating Income", "Net Income",
        "Operating Cash Flow", "Cash and Cash Equivalents", "Total Assets",
        "Total Liabilities", "Stockholders Equity", "Basic EPS", "Diluted EPS",
        "Common Shares Outstanding", "Capital Expenditure",
    }
    coverage = []
    for metric in sorted(core):
        rows = [
            f for f in package.facts if f.metric == metric
            and (f.origin == "reported" or (
                metric == "Net Income" and f.formula_id == "consolidated_profit_less_nci_v1"
            ))
        ]
        # The definition bridge is source-replayed and remains explicitly
        # derived; a missing direct-tag placeholder must not hide it. Do not
        # broaden this to arbitrary calculated quarters or TTM values.
        if any(f.formula_id == "consolidated_profit_less_nci_v1" for f in rows):
            rows = [f for f in rows if f.value is not None]
        latest = max((f.period_end for f in rows), default=None)
        rows = [f for f in rows if f.period_end == latest]
        # Retain the latest reported quarter and YTD bases where available.
        # Calculated TTM values and their lineage enter through calculations,
        # never through an implicit expansion of this reported-value brief.
        starts = [f.period_start for f in rows if f.period_start is not None]
        keep = {min(starts), max(starts)} if starts else {None}
        for start in sorted(keep, key=str):
            candidates = [f for f in rows if f.period_start == start and f.value is not None]
            chosen = _select_compatible_fact(package, candidates)
            if chosen is not None:
                selected.add(chosen.fact_id)
            elif candidates:
                coverage.append(f"- {metric} ({start or 'instant'} to {latest}): conflicting values or incompatible source bases; see full evidence records.")
            elif rows:
                coverage.append(f"- {metric}: unavailable; " + "; ".join(sorted({f.missing_reason or "missing value" for f in rows})))
    pending = list(selected)
    while pending:
        for parent in by_id[pending.pop()].input_fact_ids:
            if parent not in selected and parent in by_id:
                selected.add(parent)
                pending.append(parent)
    ordered = sorted(selected, key=lambda key: (by_id[key].metric, str(by_id[key].period_start), key))
    labels = {ident: f"F{i}" for i, ident in enumerate(ordered, 1)}
    source_ids = {sid for ident in selected for sid in by_id[ident].source_ids}
    sources = [source for source in package.sources if source.source_id in source_ids]
    source_labels = {source.source_id: f"S{i}" for i, source in enumerate(sources, 1)}
    documents = {}
    for source in sources:
        key = (source.url, source.filed_date, source.form)
        documents.setdefault(key, f"U{len(documents) + 1}")
    lines = [
        "Accepted evidence brief — source values and deterministic checks",
        "Evidence checks determine usability; reported values are not forecasts. "
        "Unvalidated interpretation cannot replace these inputs. Missing values are not zero.",
    ]
    lines.extend(coverage)
    for ident in ordered:
        fact = by_id[ident]
        period = f"{fact.period_start} to {fact.period_end}" if fact.period_start else str(fact.period_end)
        value = str(fact.value) if fact.value is not None else f"unavailable ({fact.missing_reason})"
        lines.append(
            f"- [{labels[ident]}] {fact.metric}: {value} {fact.unit}; {period}; "
            f"{fact.basis}; {fact.origin}; sources "
            + ", ".join(source_labels[sid] for sid in fact.source_ids)
        )
    references = ["### Evidence reference appendix", "Use exact IDs below for structured requests; display labels are not IDs."]
    if calculations:
        lines.append("Accounting checks:")
    for i, calculation in enumerate(calculations, 1):
        value = str(calculation.result) if calculation.result is not None else "unavailable"
        if calculation.result is not None and calculation.unit == "percent":
            value = f"{calculation.result:.2f} (rounded for display)"
        title = calculation.method.removesuffix("_v1").replace("_", " ")
        inputs = ", ".join(labels.get(ident, "unavailable input") for ident in calculation.input_fact_ids)
        lines.append(f"- [C{i}] {title}: {calculation.status}; {value} {calculation.unit or ''}; {calculation.message}; inputs {inputs}")
        references.append(f"- C{i}: method {calculation.method}")
    for ident in ordered:
        fact = by_id[ident]
        references.append(f"- {labels[ident]}: fact_id {ident}")
    for source in sources:
        references.append(
            f"- {source_labels[source.source_id]}: source_id {source.source_id}; "
            f"{documents[(source.url, source.filed_date, source.form)]}; {source.locator}"
        )
    for (url, filed_date, form), label in documents.items():
        references.append(f"- {label}: filed {filed_date}, {form}; {url}")
    return "\n".join(lines) + REFERENCE_START + "\n".join(references) + REFERENCE_END


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
        numerator = _duration_at(
            package, f"{basis} Earnings Numerator", start, end, source_precision
        )
        shares = _duration_at(
            package, f"Weighted Average {basis} Shares", start, end, source_precision
        )
        eps = _duration_at(package, f"{basis} EPS", start, end, source_precision)
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
