"""Optional pre-debate scenarios, calculated with the final valuation engine.

Forecasts and multiples remain model assumptions. This record never determines
an actionable rating, a final target, or the evidence gate's verdict.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from pydantic import ValidationError

from tradingagents.agents.accounting_checks import _OBLIGATION_METRICS
from tradingagents.agents.case_reference import (
    guidance_floor,
    history_context,
    reference_position,
    render_history_context,
)
from tradingagents.agents.document_access import validated_document_corpus
from tradingagents.agents.evidence_validation import _select_compatible_fact, obligation_checks
from tradingagents.agents.retained_kpi_context import lease_maturities
from tradingagents.agents.valuation import EVRevenueTarget, PETarget, validate_target
from tradingagents.agents.valuation_cases import (
    CONVERSION,
    MULTIPLE_CONSTRUCTION,
    EarningsCase,
    RevenueCase,
    carry_leases,
    case_funding,
    obligation_bases,
    price_case,
    price_earnings_case,
    unstated_lease_lines,
    with_lease_lines,
)
from tradingagents.agents.valuation_comparison import (
    comparable_quote,
    compare_valuation,
    display_number,
    display_value,
    price_implied_valuation,
    render_valuation_comparison,
)
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.convertibles import discover_convertibles
from tradingagents.dataflows.financial_evidence import EvidencePackage

MAX_PAYLOAD = 48000
SCOPE = "Selected US SEC-filer fundamentals"


def _record(status, requests=(), rows=(), reasons=()):
    return {"status": status, "requests": list(requests), "rows": list(rows), "reasons": list(reasons)}


_BLOCK = re.compile(r"```valuation_scenarios\s*\n(.*?)\n```", re.S)
_CORRECTION_FAILED = "Correction attempt did not produce an accepted case."


class _SubmissionError(ValueError):
    """The submission failed as a whole; ``kind`` says how, for the reader and the correction attempt."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def _decode(body):
    if len(body) > MAX_PAYLOAD:
        raise _SubmissionError("oversized", f"Valuation block is larger than {MAX_PAYLOAD} characters.")
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        near = " ".join(body[max(0, exc.pos - 30):exc.pos + 30].split())
        raise _SubmissionError("unreadable", f'Valuation block is not valid JSON: {exc.msg} near "{near}"') from None
    if not isinstance(value, list):
        raise _SubmissionError("unreadable", "Valuation block must be a JSON list of cases.")
    return value


def _parse(report):
    matches = _BLOCK.findall(report)
    if not matches:
        raise _SubmissionError("missing_block", "No valuation_scenarios block was found in the fundamentals report.")
    if len(matches) > 1:
        raise _SubmissionError("duplicate_block", "More than one valuation_scenarios block was found; exactly one is required.")
    return _decode(matches[0])


def _report_digest(state):
    report = (state.get("financial_claim_validation") or {}).get("raw_report")
    return hashlib.sha256(report.encode()).hexdigest() if isinstance(report, str) else None


def _saved_correction(state):
    """A correction applies only to the report it was written for."""
    saved = state.get("shared_valuation_scenarios")
    correction = saved.get("corrected_submission") if isinstance(saved, dict) else None
    if (not isinstance(correction, dict) or not isinstance(correction.get("block"), str)
            or not isinstance(correction.get("notes"), list)
            or not all(isinstance(note, str) for note in correction["notes"])
            or correction.get("report_sha256") != _report_digest(state)):
        return None
    return correction


def _saved_attempt(state):
    """A failed correction attempt stays on record for the report it was made on."""
    saved = state.get("shared_valuation_scenarios")
    attempt = saved.get("correction_attempt") if isinstance(saved, dict) else None
    if (not isinstance(attempt, dict) or not isinstance(attempt.get("outcome"), str)
            or attempt.get("report_sha256") != _report_digest(state)):
        return None
    return attempt


def _priced(rows):
    return [row for row in rows if row["result"].get("target") is not None]


def _comparable(request, result):
    common = (request.method, result.unit, result.valuation_period_start,
              result.valuation_period_end, result.accounting_basis, result.decision_date)
    if isinstance(request, RevenueCase):
        return (*common, request.multiple_basis, request.multiple_period, request.capital.valuation_date,
                tuple(request.capital.closing_shares.fact_ids), "closing common shares")
    if isinstance(request, EVRevenueTarget):
        return (*common, request.perimeter, request.shares_fact_id, request.revenue_fact_id)
    if isinstance(request, EarningsCase):
        return (*common, request.eps_fact_id, "diluted", True)
    return (*common, request.eps_fact_id, request.eps_basis, request.forecast is not None)


def _funding_terms(state):
    """The filing's own payment schedule and note terms, for the funding check on each case."""
    try:
        record = lease_maturities(state)
    except Exception:  # noqa: BLE001 - an unreadable schedule leaves funding unassessed, never fails pricing
        record = None
    schedule = None
    if isinstance(record, dict):
        schedule = {"as_of": record["as_of"],
                    "years": {key: value for key, value in record["amounts"].items() if re.fullmatch(r"20\d{2}", key)}}
    notes = (state.get("filing_terms_evidence") or {}).get("notes")
    leases = (state.get("filing_terms_evidence") or {}).get("leases")
    totals = ({key: record["amounts"][key] for key in ("total", "interest") if key in record["amounts"]}
              if isinstance(record, dict) else {})
    try:
        # Read from the pinned filing each time, so a saved run reprices without a stored copy of the terms.
        corpus = validated_document_corpus(state)
        # No filing to read is "not read", which is not the same as a filing that states no note.
        convertibles = discover_convertibles(corpus, date.fromisoformat(state["trade_date"])) if corpus else None
    except Exception:  # noqa: BLE001 - unreadable note terms leave every note as debt, never fail pricing
        convertibles = None
    return {"schedule": schedule, "schedule_totals": totals, "notes": notes if isinstance(notes, list) else [],
            "leases": leases if isinstance(leases, list) else [], "convertibles": convertibles}


def _with_conversion(funding, result):
    """Say beside the funding check what code decided for each convertible note, where every reader looks."""
    marker = "convertible notes: "
    lines = [text[len(marker):] for text in result.assumptions
             if text.startswith(marker) and not text.startswith((marker + CONVERSION, marker + "not "))]
    return {**funding, "convertibles": lines, "summary": " ".join((funding["summary"], *lines))} if lines else funding


def _with_filed_leases(request, result, supplemental, package):
    """Show, in the case's funded statement, the filed lease balances the case itself leaves out.

    They come from the widest lease-inclusive request already priced for the sensitivities, so the statement
    and the sensitivities read the same balances. Nothing here changes a value.
    """
    wide = supplemental.get("all_leases") or supplemental.get("finance_equipment")
    if not wide:
        return result
    by_id = {f.fact_id: f.value for f in package.facts}
    added = {category: item for category, item in wide["capital"]["obligations"].items()
             if category not in request.capital.obligations}
    opening = {category: sum(by_id[i] for i in item["fact_ids"]) for category, item in added.items()}
    closing = {category: Decimal(item["value"]) for category, item in added.items()}
    lines = unstated_lease_lines(opening, closing, request.capital.currency, request.multiple_basis)
    return result.model_copy(update={"assumptions": with_lease_lines(result.assumptions, lines)})


def _source_bound_lease_requests(request, result, package, outlooks, sensitivities, terms=None):
    """Price missing lease perimeters on separate requests with dated filing balances."""
    supplemental = {}
    capital = request.capital
    if "borrowings" not in capital.obligations:
        return supplemental
    bases = {"borrowings_finance_equipment_less_cash_v1": "finance_equipment",
             "all_classified_obligations_less_cash_v1": "all_leases"}
    by_id = {f.fact_id: f for f in package.facts}
    # A check may use a complete total when component selection returned
    # nothing. An absent component is fine; competing versions are ambiguous.
    dated = {}
    for fact in package.facts:
        if fact.period_start is None and fact.period_end == result.capital_snapshot_date and fact.value is not None:
            dated.setdefault(fact.metric, []).append(fact)
    ambiguous_categories = {
        category for category, metrics in _OBLIGATION_METRICS.items()
        if any(len(dated.get(metric, ())) > 1 and _select_compatible_fact(package, dated[metric]) is None
               for metric in metrics)
    }
    for check in obligation_checks(package):
        basis = bases.get(check.method)
        if not basis or check.status != "pass" or basis == request.multiple_basis or basis in sensitivities:
            continue
        relevant = {"finance_equipment", "finance_leases", "equipment"}
        if basis == "all_leases":
            relevant.add("operating_leases")
        if ambiguous_categories & relevant:
            continue
        source_facts = [by_id[i] for i in check.input_fact_ids]
        if any(f.period_end != result.capital_snapshot_date or f.unit != capital.currency for f in source_facts):
            continue
        candidate = request.model_dump(mode="json")
        candidate["multiple_basis"] = basis
        obligations = candidate["capital"]["obligations"]
        # Keep the submitted combined/separate representation if one exists.
        permitted = (obligation_bases(obligations)[basis]
                     if obligations.keys() & {"finance_equipment", "finance_leases", "equipment"}
                     else relevant)
        groups = {category: [f for f in source_facts if f.metric in metrics]
                  for category, metrics in _OBLIGATION_METRICS.items()
                  if category not in obligations and category in permitted}
        with localcontext() as ctx:
            ctx.prec = 60
            filed = {category: sum(f.value for f in group) for category, group in groups.items() if group}
            rolled = carry_leases(filed, result.capital_snapshot_date, capital.valuation_date, terms)
            for category, amount in filed.items():
                carried = rolled.get(category)
                obligations[category] = {
                    "value": str(amount), "fact_ids": [f.fact_id for f in groups[category]],
                    "assumption": "unchanged_from_snapshot",
                    "reason": (f"{category} obligations as of {result.capital_snapshot_date} held constant "
                               f"through {capital.valuation_date}, with no growth or repayment assumed."),
                } if carried is None else {
                    "value": str(carried["value"]), "fact_ids": [f.fact_id for f in groups[category]],
                    "assumption": "estimated", "reason": carried["reason"],
                }
        if obligations.keys() == capital.obligations.keys():
            continue
        try:
            priced, _ = price_case(RevenueCase.model_validate(candidate), package, outlooks, terms)
        except (ValueError, ArithmeticError):
            # An overlapping category or nonpositive equity can invalidate only
            # this alternative. Never replace the accepted case or guess a price.
            continue
        sensitivities[basis] = str(priced.target)
        supplemental[basis] = candidate
    return supplemental


def _label_capital_estimates(raw, index, notes):
    """A capital value submitted without its label is the analyst's estimate; the case is still priced."""
    capital = raw.get("capital")
    if not isinstance(capital, dict):
        return raw
    filled = {**raw, "capital": dict(capital)}
    values = [("closing_shares", None), ("cash", None)]
    if isinstance(capital.get("obligations"), dict):
        filled["capital"]["obligations"] = dict(capital["obligations"])
        values += [("obligations", category) for category in capital["obligations"]]
    for field, category in values:
        holder = filled["capital"] if category is None else filled["capital"]["obligations"]
        key = field if category is None else category
        value = holder.get(key)
        if isinstance(value, dict) and "assumption" not in value:
            holder[key] = {**value, "assumption": "estimated"}
            notes.append(f"Row {index}: assumption label missing on "
                         f"{field if category is None else f'{field}.{category}'}; treated as estimated.")
    return filled


def _fill_equity_capital(raw, package, index, notes):
    """An equity-basis case that leaves out cash or obligations is still priced: neither enters its value.

    Cash is held at the filed balance on the date of the share count the case cites; no obligation is assumed.
    A case on any other basis uses both and must state them.
    """
    capital = raw.get("capital")
    if raw.get("multiple_basis") != "equity" or not isinstance(capital, dict) or {"cash", "obligations"} <= capital.keys():
        return raw
    filled, missing = {**raw, "capital": dict(capital)}, [key for key in ("cash", "obligations") if key not in capital]
    if "cash" in missing:
        cited = (capital.get("closing_shares") or {}).get("fact_ids") if isinstance(capital.get("closing_shares"), dict) else None
        shares = next((f for f in package.facts if cited and f.fact_id == cited[0]), None)
        filed = [f for f in package.facts if shares is not None and f.metric == "Cash and Equivalents"
                 and f.period_start is None and f.period_end == shares.period_end and f.value is not None]
        cash = filed[0] if len(filed) == 1 else _select_compatible_fact(package, filed) if filed else None
        if cash is None:
            return raw
        filled["capital"]["cash"] = {
            "value": str(cash.value), "fact_ids": [cash.fact_id], "assumption": "unchanged_from_snapshot",
            "reason": f"Not stated by the analyst; code holds filed cash as of {cash.period_end} unchanged. "
                      "An equity-basis value does not use cash."}
    filled["capital"].setdefault("obligations", {})
    notes.append(f"Row {index}: {' and '.join(missing)} {'were' if len(missing) > 1 else 'was'} not stated; an "
                 "equity-basis value uses neither, so the case is priced with filed cash held unchanged and no "
                 "obligation assumed.")
    return filled


def _request_record(request):
    """Dump a request; a case with no stated bridge keeps its original record shape."""
    record = request.model_dump(mode="json")
    capital = record.get("capital")
    if isinstance(capital, dict):
        for key in ("share_changes", "cash_changes"):
            if not capital.get(key):
                capital.pop(key, None)
    return record


def prepare_shared_valuation(state, requests=None):
    """Calculate optional inputs without modifying state or making external calls.

    Supplying saved requests replays calculations for publication. Stored prices
    and status strings are never used as inputs to this boundary.
    """
    correction = _saved_correction(state) if requests is None else None
    if correction:
        try:
            corrected = _decode(correction["block"])
        except _SubmissionError:
            corrected = None
        if corrected is not None:
            # Every later replay prices the analyst's corrected cases, not the rejected original.
            record = _prepare(state, corrected)
            return {**record, "reasons": [*record["reasons"], *correction["notes"]],
                    "corrected_submission": correction}
    record = _prepare(state, requests)
    attempt = _saved_attempt(state) if requests is None else None
    if attempt and record["status"] != "not_applicable":
        record = {**record, "reasons": [*record["reasons"], attempt["outcome"]], "correction_attempt": attempt}
    return record


def _prepare(state, requests):
    quality = state.get("evidence_quality") or {}
    if (quality.get("status") not in {"sufficient", "limited"}
            or quality.get("scope") != SCOPE or state.get("asset_type", "stock") != "stock"):
        return _record("not_applicable", reasons=("Shared valuation scenarios do not apply to this evidence scope.",))
    try:
        package = EvidencePackage.model_validate(state.get("financial_evidence"))
        if str(package.as_of) != state.get("trade_date"):
            raise ValueError("Financial evidence date differs from this run")
        if requests is None:
            validation = state.get("financial_claim_validation") or {}
            report = validation.get("raw_report", "")
            if not isinstance(report, str):
                raise ValueError("Original fundamentals report unavailable")
            requests = _parse(report)
        # Apply the same collection limits to parsed and replayed requests.
        if not isinstance(requests, list):
            raise ValueError("Scenario inputs must be a list")
        if len(requests) > 3:
            raise _SubmissionError("too_many", f"Valuation block has {len(requests)} cases; at most three are accepted.")
        if len(json.dumps(requests)) > MAX_PAYLOAD:
            raise _SubmissionError("oversized", f"Valuation block is larger than {MAX_PAYLOAD} characters.")
        if not requests:
            return _record("unavailable", requests, reasons=("No valuation scenarios were proposed; no numerical sensitivity published.",))
        names = [r.get("name") for r in requests if isinstance(r, dict)]
        valid_names = [n.strip() for n in names if isinstance(n, str)]
        if len(valid_names) != len(set(valid_names)):
            raise _SubmissionError("duplicate_names", "Scenario names must be distinct.")
    except (ValidationError, ValueError, TypeError, OverflowError) as exc:
        whole = isinstance(exc, _SubmissionError)
        record = _record("unavailable", reasons=(
            str(exc) if whole else
            "Shared scenario inputs or canonical evidence are missing, malformed, duplicated or oversized.",))
        if whole:
            record["submission_error"] = exc.kind
        if isinstance(requests, list) and requests:
            # The submission itself is not retained; its size is, so the loss stays visible.
            record["rejected_submissions"] = len(requests)
        return record

    outlooks = grounded_outlooks(state)
    terms = _funding_terms(state)
    rows, reasons, comparisons, notes = [], [], [], []
    kinds = {row["request"].get("method") for row in requests
             if isinstance(row, dict) and isinstance(row.get("request"), dict)} & {"revenue_case", "earnings_case"}
    if len(kinds) > 1:
        # A weighted value across a revenue multiple and an earnings multiple is not defined.
        return _record("unavailable", requests, reasons=(
            "Cases mix revenue cases and earnings cases; submit every case on one method. No case was priced.",))
    for index, row in enumerate(requests, 1):
        try:
            if (isinstance(row, dict) and isinstance(row.get("capital"), dict)
                    and isinstance(row.get("request"), dict) and "capital" not in row["request"]):
                # Only one place it can belong, and nothing in it changes: read it where it was meant to be.
                row = {**{key: value for key, value in row.items() if key != "capital"},
                       "request": {**row["request"], "capital": row["capital"]}}
                notes.append(f"Row {index}: capital was submitted beside request; code read it inside request, "
                             "content unchanged.")
            extra = sorted(set(row) - {"name", "request", "scenario_role"}) if isinstance(row, dict) else []
            if extra:
                raise ValueError(f"unexpected field{'s' if len(extra) > 1 else ''} {', '.join(map(str, extra))[:200]} "
                                 "beside name and request"
                                 + ("; capital belongs inside request" if "capital" in extra else ""))
            if not isinstance(row, dict) or not {"name", "request"} <= set(row):
                raise ValueError("Expected name and request fields")
            scenario_role = row.get("scenario_role")
            if scenario_role is not None and (not isinstance(scenario_role, str) or not scenario_role.strip()):
                raise ValueError("Scenario role must be an explicit nonempty string")
            name = row["name"]
            if not isinstance(name, str) or not name.strip() or len(name) > 80:
                raise ValueError("Scenario name missing or oversized")
            raw = row["request"]
            if not isinstance(raw, dict):
                raise ValueError("Scenario request malformed")
            sensitivities = {}
            supplemental = {}
            if raw.get("method") == "revenue_case":
                row_notes = []
                request = RevenueCase.model_validate(_label_capital_estimates(
                    _fill_equity_capital(raw, package, index, row_notes), index, row_notes))
                notes += row_notes
                result, sensitivities = price_case(request, package, outlooks, terms)
                supplemental = _source_bound_lease_requests(request, result, package, outlooks, sensitivities, terms)
                result = _with_filed_leases(request, result, supplemental, package)
            elif raw.get("method") == "earnings_case":
                request = EarningsCase.model_validate(raw)
                result, sensitivities = price_earnings_case(request, package, outlooks)
            elif raw.get("method") == "ev_revenue" and raw.get("capital_structure_assumption") == "forward_capital_v1":
                request = EVRevenueTarget.model_validate(raw)
                if len(request.scenarios) != 1 or request.scenarios[0].weight != 1:
                    raise ValueError("Shared legacy funding diagnostic requires one independent scenario")
                result = validate_target(request, package, outlooks)
            elif raw.get("method") == "ev_revenue":
                raise ValueError("Legacy revenue case lacks dated per-value capital assumptions; original request retained")
            elif raw.get("method") == "pe":
                request = PETarget.model_validate(raw)
                result = validate_target(request, package, outlooks)
            else:
                raise ValueError("Unsupported scenario valuation method")
            diagnostic = (result.status == "unsupported" and len(result.scenario_results) == 1
                          and bool(result.scenario_results[0].funding_gap))
            if result.status != "supported":
                if not diagnostic:
                    reasons.append(f"Row {index} omitted: " + "; ".join(result.reasons))
                    continue
                reasons.append(f"Row {index} retained as funding diagnostic only: " + "; ".join(result.reasons))
            comparisons.append(_comparable(request, result))
            historical = result.decision_use.classification == "historical_diagnostic"
            comparison = None
            if isinstance(request, (RevenueCase, EarningsCase)):
                try:
                    quote = comparable_quote(state, package, result.unit, result.capital_snapshot_date)
                    comparison = {"status": "available", "price": {k: quote[k] for k in ("close", "currency", "session_date")}}
                except (ValueError, TypeError, KeyError) as exc:
                    comparison = {"status": "unavailable", "reason": str(exc)}
            elif not historical or result.decision_use.suitability == "conditional":
                comparison = compare_valuation(state, result, request)
            case_id = "case-" + hashlib.sha256(name.strip().encode()).hexdigest()[:16]
            rows.append({"name": name.strip(), "case_id": case_id, "version": 1,
                         **({"scenario_role": scenario_role} if scenario_role is not None else {}),
                         "request": _request_record(request), "result": result.model_dump(mode="json"),
                         "diagnostic_only": not isinstance(request, (RevenueCase, EarningsCase)), "comparison": comparison,
                         "sensitivities": sensitivities,
                         **({"funding": _with_conversion(case_funding(request, package, terms), result)}
                            if isinstance(request, RevenueCase) else {}),
                         **({"source_bound_sensitivity_requests": supplemental} if supplemental else {})})
        except ValidationError as exc:
            error = exc.errors(include_input=False)[0]
            where = ".".join(map(str, error["loc"]))
            reasons.append(f"Row {index} omitted: " + (f"required field {where} is missing" if error["type"] == "missing"
                                                        else f"malformed valuation request at {where}"))
        except (ValueError, TypeError, ArithmeticError) as exc:
            reasons.append(f"Row {index} omitted: {exc}")
    if comparisons and all(r["request"]["method"] not in ("revenue_case", "earnings_case") for r in rows) and any(key != comparisons[0] for key in comparisons[1:]):
        return _record("unavailable", requests, reasons=("Scenario rows use incomparable methods, periods, bases or capital inputs; table omitted.",))
    revenue_rows = [r for r in rows if r["request"]["method"] == "revenue_case"]
    if revenue_rows:
        from tradingagents.agents.mechanical_valuation import _share_bases
        source = price_implied_valuation(state)
        for row in revenue_rows:
            result = row["result"]
            with localcontext() as ctx:
                ctx.prec = 60
                equity = Decimal(result["target"]) * Decimal(result["shares_outstanding"])
                for share in _share_bases(source):
                    if share["kind"] == "guided diluted weighted average" and Decimal(share["value"]) > 0:
                        key = f"guided diluted weighted average {share['point']} ({share['value']} shares, {share['period']})"
                        row["sensitivities"][key] = str(equity / Decimal(share["value"]))
    status = ("partial" if reasons else "available") if rows else "unavailable"
    for row in rows:
        short = horizon_note(row["name"], row["result"].get("valuation_period_end"), state)
        if short:
            notes.append(short)
    record = _record(status, requests, rows, [*reasons, *notes])
    baselines = {f.fact_id: {"value": str(f.value), "period_start": str(f.period_start), "period_end": str(f.period_end)}
                 for f in package.facts
                 if f.fact_id in {r["request"].get("eps_fact_id") for r in rows if r["request"]["method"] == "earnings_case"}}
    if baselines:
        record["earnings_baselines"] = baselines
    from tradingagents.agents.earnings_anchor import earnings_anchor, multiple_reference
    expectations = state.get("vendor_expectations") if isinstance(state.get("vendor_expectations"), dict) else {}
    reference = state.get("valuation_reference") if isinstance(state.get("valuation_reference"), dict) else {}
    own = reference.get("own_history") if isinstance(reference.get("own_history"), dict) else {}
    for row in rows:
        anchor = earnings_anchor(row["request"], package.facts, state.get("trade_date"), expectations.get("estimates"))
        placed = multiple_reference(row["request"], own.get("earnings_history"))
        if anchor or placed:
            row["earnings_anchor"] = {**(anchor or {}), "lines": [*((anchor or {}).get("lines") or ()), *([placed] if placed else ())]}
        if row["request"].get("method") == "earnings_case":
            from tradingagents.agents.valuation_cases import earnings_build_parts
            try:
                built = earnings_build_parts(EarningsCase.model_validate(row["request"]), package)
            except (ValueError, TypeError, ArithmeticError):
                built = None
            row["earnings_build"] = built or {"status": "none"}
    priced = [row for row in rows if row["result"]["method"] == "revenue_case"]
    for row in priced:
        row["reference_position"] = reference_position(row, state)
        floor = guidance_floor(row, state)
        if floor is not None:
            row["guidance_floor"] = floor
    if any(row["reference_position"]["status"] == "available" for row in priced):
        record["reference_history"] = history_context(state)
        # The same quarters restated with borrowings less cash, beside the growth and margin they were valued at.
        restated = next((row["reference_position"]["like_for_like"] for row in priced
                         if (row["reference_position"].get("like_for_like") or {}).get("basis") == "borrowings_only"
                         and row["reference_position"]["like_for_like"]["status"] == "available"), None)
        by_quarter = {point["quarter_end"]: point["multiple"] for point in (restated or {}).get("quarters", ())}
        for quarter in record["reference_history"]:
            if quarter["quarter_end"] in by_quarter:
                quarter["same_basis_multiple"] = by_quarter[quarter["quarter_end"]]
    return record


def annotate_disputed_cases(state, record):
    """An accepted finding can exclude a displayed case, never alter its math."""
    from tradingagents.agents.audit_pass import prepare_audit_dispositions
    findings = [f for f in prepare_audit_dispositions(state)['findings'] if f['disposition'] == 'accepted']
    def prose(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'reason', 'rationale', 'multiple_rationale', 'assumption_text'} and isinstance(item, str):
                    yield item
                elif isinstance(item, (dict, list)):
                    yield from prose(item)
        elif isinstance(value, list):
            for item in value:
                yield from prose(item)
    rows = []
    for row in record.get('rows', []):
        text = list(prose(row.get('request', {})))
        ids = [f['finding_id'] for f in findings
               if (f.get('case_id') == row['case_id'] if f.get('case_id') else
                   bool(f.get('quoted_claim')) and any(f['quoted_claim'] in part for part in text))]
        clean = {key: value for key, value in row.items() if key not in {'disputed_by', 'dispute_note'}}
        # A finding can name a case because a role misdescribed it. That corrects the role, not the case.
        # A finding disputes the case only when it quotes the case's own inputs. A role's statement about the case,
        # the analyst's narrative included, is a correction of that role.
        about_case = [f for f in findings if f['finding_id'] in ids and (
            bool(f.get('quoted_claim')) and any(f['quoted_claim'] in part for part in text))]
        note = {}
        if ids and not about_case:
            roles = sorted({str(f.get('role') or 'a role').replace('_', ' ') for f in findings if f['finding_id'] in ids})
            many = len(ids) > 1
            note = {'dispute_note': ('accepted audit findings ' if many else 'accepted audit finding ') + ', '.join(ids)
                                    + (' correct statements the ' if many else ' corrects a statement the ')
                                    + ' and '.join(roles) + ' made about this case; its inputs and arithmetic are not disputed'}
        rows.append({**clean, **({'disputed_by': ids} if ids else {}), **note})
    return {**record, 'rows': rows}


def replay_cases(state, *, revision=None):
    saved = state.get("shared_valuation_scenarios") or {}
    if not isinstance(saved, dict):
        saved = {}
    raw = state.get("financial_claim_validation") or {}
    if isinstance(raw, dict) and "raw_report" in raw:
        analyst = prepare_shared_valuation(state)
    else:
        retained = saved.get("analyst_requests", saved.get("requests", []))
        analyst = prepare_shared_valuation(state, retained)
        # Old requests can still explain diagnostic arithmetic. They cannot
        # establish a new versioned analyst case without its original submission.
        if any(r["request"]["method"] == "revenue_case" for r in analyst["rows"]):
            rows = [r for r in analyst["rows"] if r["diagnostic_only"]]
            analyst = _record("partial" if rows else "unavailable", analyst["requests"], rows,
                              (*analyst["reasons"], "Original analyst case submission unavailable; cached revenue cases withheld."))

    revision = saved.get("revision_request") if revision is None else revision
    if revision is None or analyst["status"] == "not_applicable":
        return analyst
    revised = prepare_shared_valuation(state, revision)
    accepted = revised["status"] == "available" and all(not r["diagnostic_only"] for r in revised["rows"])
    for row in revised["rows"]:
        row["version"] = 2
    kept = {key: analyst[key] for key in ("corrected_submission", "correction_attempt") if key in analyst}
    if accepted and "corrected_submission" in analyst:
        # The revision replaces the analyst's rows; a surviving case still says it had been corrected.
        surviving = {row["name"] for row in revised["rows"]}
        kept["reasons"] = [*revised["reasons"], *(
            f'Analyst case "{case["name"]}" was corrected before this revision: {case["cause"]}'
            for case in analyst["corrected_submission"].get("cases", ())
            if isinstance(case, dict) and case.get("name") in surviving)]
    return {**(revised if accepted else analyst), **kept, "analyst_requests": analyst["requests"],
            "analyst_rows": analyst["rows"], "revision_request": revision,
            "revision_status": "accepted" if accepted else "rejected", "revision_reasons": revised["reasons"]}


def _reply_text(reply):
    content = getattr(reply, "content", reply)
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else part if isinstance(part, str) else ""
                          for part in content)
    return content if isinstance(content, str) else ""


BRIDGE_ASKED = "cash_bridge"
_BRIDGE_DECLINED = ("Cash bridge request: the analyst did not state operating cash flow and capital spending when "
                    "asked once; the cases stand as submitted.")
_BRIDGE_FIELDS = ("cash", "cash_changes", "cash_model", "operations_after_lease_interest",
                  "operations_include_new_lease_rent")


def _bridge_capital(item):
    request = item.get("request") if isinstance(item, dict) else None
    if not isinstance(request, dict) or request.get("method") != "revenue_case" or request.get("multiple_basis") == "equity":
        return None
    return request.get("capital") if isinstance(request.get("capital"), dict) else {}


def _lacks_bridge(item) -> bool:
    """A revenue case whose value uses cash but states no operating cash flow or no capital spending."""
    capital = _bridge_capital(item)
    if capital is None:
        return False
    sources = {change.get("source") for change in capital.get("cash_changes") or () if isinstance(change, dict)}
    return not isinstance(capital.get("cash_model"), dict) and not {"operations", "capex"} <= sources


def _balances_to_zero(item) -> bool:
    """Stated operating cash and capital spending that, with the other changes, sum to nothing: a plug, not a forecast."""
    capital = _bridge_capital(item)
    if capital is None or isinstance(capital.get("cash_model"), dict):
        return False
    changes = [change for change in capital.get("cash_changes") or () if isinstance(change, dict)]
    if len(changes) < 2 or not any(change.get("source") in ("operations", "capex") for change in changes):
        return False
    try:
        return sum(Decimal(str(change.get("amount"))) for change in changes) == 0
    except (InvalidOperation, ValueError):
        return False


def _rates_unexplained(item) -> bool:
    """Rates given without saying whether the margin is after lease interest and includes rent on new leases."""
    capital = _bridge_capital(item)
    return bool(capital) and isinstance(capital.get("cash_model"), dict) and any(
        not isinstance(capital.get(key), bool)
        for key in ("operations_after_lease_interest", "operations_include_new_lease_rent"))


def _needs_bridge(item) -> bool:
    return _lacks_bridge(item) or _balances_to_zero(item) or _rates_unexplained(item)


def _outside_bridge(item):
    """A submitted case with the cash bridge taken out, to check that a completed bridge changed nothing else."""
    copy = json.loads(json.dumps(item))
    capital = copy["request"].get("capital") if isinstance(copy.get("request"), dict) else None
    if isinstance(capital, dict):
        for field in _BRIDGE_FIELDS:
            capital.pop(field, None)
    return copy


def _request_cash_bridge(state, llm, shape, record, report):
    """Ask the analyst once for operating cash flow and capital spending in cases that state neither.

    The completed cases replace the originals only when every case still prices and nothing outside the cash
    bridge changed. Otherwise the submitted cases stand: this never removes a case.
    """
    priced = {row["name"] for row in _priced(record["rows"]) if not row.get("diagnostic_only")}
    submitted = [item for item in record["requests"] if isinstance(item, dict)]
    asked = [item["name"].strip() for item in submitted
             if isinstance(item.get("name"), str) and item["name"].strip() in priced and _needs_bridge(item)]
    if not asked:
        return record
    original = "\n\n".join(_BLOCK.findall(report))[:MAX_PAYLOAD]
    prompt = (
        "Your valuation cases price, but these state no operating cash flow or no capital spending between the "
        "balance-sheet date and the valuation date, or state amounts that sum to zero so that cash simply stays at "
        "the filed balance, or give rates without saying what the margin holds; their closing cash is not a "
        "forecast: " + "; ".join(asked) + ". Return only one corrected ```valuation_scenarios fenced block and "
        'nothing else. In each of those cases give capital "cash_model":{"operating_cash_margin":"<fraction of '
        'revenue, e.g. 0.30>","operating_cash_reason":"<why, against the filed margin>","capex_rate":"<fraction of '
        'revenue>","capex_reason":"<why, against the filed rate>"}: operating cash flow before finance-lease and '
        "equipment payments, and cash capital spending, each as a share of revenue you expect over that period. Give "
        "each case the rates that fit its own story; a slower-growth case need not earn the base case's margin. Do "
        "not give amounts and do not choose rates to make cash come out at any figure: code applies the rates to "
        'each case\'s revenue. Set "operations_after_lease_interest" and "operations_include_new_lease_rent" to true '
        "or false for the margin you give. Rates and amounts cannot stand together: Remove the operations, capex and "
        "finance_payments entries from cash_changes and leave out the repayment of a note that falls due in the "
        "period, because code applies your rates, deducts the filed payment schedule and repays such a note "
        "itself. Keep any other cash_changes entry, and set cash to the filed balance plus only the entries that "
        "remain (with none remaining, the filed balance, unchanged from the snapshot). Change "
        "nothing else: keep every name, forecast, multiple, basis, "
        "share count, obligation, fact ID and rationale exactly as you wrote it. Do not add or remove cases."
        "\n\nRequired shape:" + shape + "\n\nYour original block:\n```valuation_scenarios\n" + original + "\n```"
    )

    def declined(reason=_BRIDGE_DECLINED):
        return {**record, "reasons": [*record["reasons"], reason],
                "correction_attempt": {"outcome": reason, "report_sha256": _report_digest(state)}}

    try:
        text = _reply_text(llm.invoke(prompt))
    except Exception as exc:  # noqa: BLE001 - a failed request must never fail the run
        return declined(f"Cash bridge request failed: {type(exc).__name__}; the cases stand as submitted.")
    blocks = _BLOCK.findall(text)
    try:
        corrected = _decode(blocks[0] if len(blocks) == 1 else text.strip())
    except _SubmissionError:
        return declined()
    before = {item["name"].strip(): item for item in submitted if isinstance(item.get("name"), str)}
    after = {item["name"].strip(): item for item in corrected
             if isinstance(item, dict) and isinstance(item.get("name"), str)} if isinstance(corrected, list) else {}
    if (before.keys() != after.keys() or len(after) != len(corrected)
            or any(not isinstance(after[name].get("request"), dict)
                   or _outside_bridge(after[name]) != _outside_bridge(before[name]) for name in before)
            or any(_needs_bridge(after[name]) for name in asked)):
        return declined()
    candidate = _prepare(state, corrected)
    if {row["name"] for row in _priced(candidate["rows"])} != {row["name"] for row in _priced(record["rows"])}:
        return declined()
    cause = ("its operating cash flow and capital spending were missing, balanced to zero or left unexplained; the "
             "analyst was asked once to state them")
    notes = [f"Row {index}: cash bridge stated by the analyst at code's request (operating cash flow and capital "
             "spending); nothing else in the case changed."
             for index, item in enumerate(corrected, 1) if item["name"].strip() in asked]
    correction = {"block": json.dumps(corrected), "notes": notes, "kind": BRIDGE_ASKED,
                  "cases": [{"name": name, "cause": cause} for name in asked], "report_sha256": _report_digest(state)}
    return {**candidate, "reasons": [*candidate["reasons"], *notes], "corrected_submission": correction}


def prepare_with_correction(state, llm, shape):
    """Price the analyst's cases; a rejected submission gets one correction attempt by the analyst model.

    The corrected cases pass the same validation and replace the original only when
    they price more cases without changing any that was already priced.
    """
    record = prepare_shared_valuation(state)
    report = (state.get("financial_claim_validation") or {}).get("raw_report")
    omitted = [reason for reason in record["reasons"] if re.match(r"Row \d+ omitted: ", reason)]
    if (record["status"] == "not_applicable" or "corrected_submission" in record
            or "correction_attempt" in record or not isinstance(report, str)
            or record.get("submission_error") == "missing_block"):
        return record
    if not (record.get("submission_error") or omitted):
        # Nothing was rejected, so the one request can go to an empty cash bridge instead.
        return _request_cash_bridge(state, llm, shape, record, report)
    original = "\n\n".join(_BLOCK.findall(report))[:MAX_PAYLOAD]
    prompt = (
        "Validation rejected the valuation_scenarios block in your fundamentals report. Return only one corrected "
        "```valuation_scenarios fenced block and nothing else. Change only what the reasons below require; keep "
        "every case, assumption, value, fact ID and rationale otherwise exactly as you wrote it. Do not add or "
        "remove cases.\n\nReasons:\n" + "\n".join("- " + reason for reason in record["reasons"])
        + "\n\nRequired shape:" + shape + "\n\nYour original block:\n```valuation_scenarios\n" + original + "\n```"
    )

    def failed(reason=_CORRECTION_FAILED):
        return {**record, "reasons": [*record["reasons"], reason],
                "correction_attempt": {"outcome": reason, "report_sha256": _report_digest(state)}}

    try:
        text = _reply_text(llm.invoke(prompt))
    except Exception as exc:  # noqa: BLE001 - a failed correction must never fail the run
        return failed(f"Correction attempt failed: {type(exc).__name__}.")
    blocks = _BLOCK.findall(text)
    try:
        corrected = _decode(blocks[0] if len(blocks) == 1 else text.strip())
    except _SubmissionError:
        return failed()
    candidate = _prepare(state, corrected)
    names = [item.get("name").strip() if isinstance(item, dict) and isinstance(item.get("name"), str) else None
             for item in corrected]
    submitted = [item.get("name").strip() if isinstance(item, dict) and isinstance(item.get("name"), str) else None
                 for item in record["requests"]]
    after = {row["case_id"]: row for row in candidate["rows"]}
    # More cases must gain a price, none may be dropped, and none already retained may change.
    if (len(_priced(candidate["rows"])) <= len(_priced(record["rows"]))
            or (submitted and sorted(map(str, names)) != sorted(map(str, submitted)))
            or any(row["case_id"] not in after or after[row["case_id"]]["request"] != row["request"]
                   or after[row["case_id"]]["result"] != row["result"] for row in record["rows"])):
        return failed()
    before = {row["case_id"] for row in record["rows"]}
    notes, cases = [], []
    for row in _priced(candidate["rows"]):
        if row["case_id"] in before:
            continue
        number = names.index(row["name"]) + 1
        cause = next((reason.removeprefix(f"Row {number} omitted: ") for reason in omitted
                      if reason.startswith(f"Row {number} omitted: ")), record["reasons"][0])
        notes.append(f"Row {number}: corrected by the analyst after a validation error: {cause}")
        cases.append({"name": row["name"], "cause": cause})
    correction = {"block": json.dumps(corrected), "notes": notes, "cases": cases,
                  "report_sha256": _report_digest(state)}
    return {**candidate, "reasons": [*candidate["reasons"], *notes], "corrected_submission": correction}


def _cell(value):
    return " ".join(str(value).split()).replace("|", r"\|")


def _summary_value(row):
    result = row["result"]
    value = display_value(result["target"], result["unit"])
    if row.get("dispute_note"):
        return f"{value} — a statement about this case was corrected ({', '.join(row['disputed_by'])}); inputs not disputed"
    if row.get("disputed_by"):
        return f"{value} — flagged ({', '.join(row['disputed_by'])}), shown in range"
    return value


def horizon_note(name, period_end, state) -> str | None:
    """A sentence for a case whose period ends before the run's decision horizon; None when it reaches it."""
    from datetime import date

    from tradingagents.agents.analysts.fundamentals_analyst import horizon_end
    end = horizon_end(state)
    try:
        case_end, today = date.fromisoformat(str(period_end)[:10]), date.fromisoformat(str(state.get("trade_date"))[:10])
    except (ValueError, TypeError):
        return None
    if end is None or case_end >= end:
        return None
    return (f"{name}: the case period ends on {case_end}, {(case_end - today).days} days after the analysis date and "
            f"before the decision horizon ends on {end}; its value says nothing about the months after it.")


def _implied_earnings_multiple(row, record) -> str:
    """What the close already pays for the filed earnings, beside the multiple the case assumes."""
    price = (row.get("comparison") or {}).get("price") or {}
    filed = (record.get("earnings_baselines") or {}).get(row["request"]["eps_fact_id"])
    try:
        close, earned = Decimal(str(price["close"])), Decimal(str(filed["value"]))
        if earned <= 0:
            return ""
        return (f"What the price implies: the {price['session_date']} close of {display_number(close)} is "
                f"{display_number(close / earned)} times the filed diluted earnings per share of {display_number(earned)} "
                f"for {filed['period_start']} to {filed['period_end']}; this case assumes "
                f"{display_number(row['request']['multiple'])} times its forecast.")
    except (KeyError, TypeError, ArithmeticError):
        return ""


def render_shared_valuation(record):
    """Render a freshly calculated record; callers must replay persisted inputs."""
    if not record or record.get("status") == "not_applicable":
        return ""
    lines = ["### Shared valuation scenarios — conditional research inputs", "",
             "Display values are rounded; exact arithmetic and provenance remain in evidence.json. Forecasts and multiples are assumptions, not verified predictions. These are independent scenarios, not a final price target or probability-weighted forecast.", ""]
    if record.get("revision_status"):
        lines.append("Research Manager revision " + record["revision_status"] + ". " + " ".join(map(_cell, record["revision_reasons"])))
    rows = record.get("rows") or []
    if any(not isinstance(row, dict) or not row.get("case_id") or not row.get("version") for row in rows):
        return "\n".join(lines + ["Legacy case projection unavailable until its original requests are replayed against retained evidence."])
    if rows:
        lines += ["Scenario | Method | Period | Conditional price / historical arithmetic", "--- | --- | --- | ---"]
        for row in rows:
            result = row["result"]
            lines.append(" | ".join(_cell(v) for v in (row["name"], {"pe": "P/E", "ev_revenue": "EV/revenue", "earnings_case": "forecast EPS × multiple",
                                                                 "revenue_case": row["request"].get("multiple_basis", "") + " / period revenue"}[result["method"]],
                f"{result['valuation_period_start']} to {result['valuation_period_end']}",
                _summary_value(row) if result['status'] == 'supported'
                else "Unavailable — unfunded scenario")))
        if any(row["result"]["method"] == "ev_revenue" or row["request"].get("forecast") for row in rows):
            lines += ["", "Future-period scenario values are not discounted to today."]
        for row in rows:
            result = row["result"]
            assessment = result.get("decision_use", {})
            if row.get("diagnostic_only") and assessment.get("classification") != "historical_diagnostic":
                lines.append("Legacy calculation only; no dated per-value revenue case capital contract supplied.")
            if assessment.get("classification") == "historical_diagnostic":
                lines += ["", "Historical diagnostic — " + _cell(assessment.get("suitability")) + ". Not a forward target.",
                          "Decision-use assessment: " + "; ".join(_cell(v) for v in assessment.get("reasons", []))]
                for event in assessment.get("events", []):
                    lines += ["Capital-change evidence: " + _cell(event["fact_id"]) + "; sources "
                              + ", ".join(_cell(v) for v in event["source_ids"])
                              + "; interval " + _cell(event["period_start"]) + " to " + _cell(event["period_end"]) + "."]
            lines += ["", f"**{_cell(row['name'])} — inputs and assumptions**", "",
                      "Source fact IDs: " + ", ".join(_cell(v) for v in result["input_fact_ids"])
                      + ". Exact values: evidence.json → shared_valuation_scenarios.", ""]
            lines.append(f"Case ID {row['case_id']}, version {row['version']}.")
            if row.get('disputed_by'):
                lines.append((row['dispute_note'][0].upper() + row['dispute_note'][1:] + '.') if row.get('dispute_note') else
                             'Disputed by accepted audit finding ' + ', '.join(row['disputed_by']) + '; shown flagged in the conditional range. Arithmetic retained unchanged.')
            if result["method"] == "earnings_case":
                request = row["request"]
                lines.append(f"Earnings case: forecast diluted earnings per share {display_number(request['forecast']['value'])} "
                             f"for {request['forecast']['period_start']} to {request['forecast']['period_end']} × "
                             f"{display_number(request['multiple'])}; no debt or cash adjustment (earnings are after interest).")
                implied = _implied_earnings_multiple(row, record)
                if implied:
                    lines.append(implied)
                lines.extend(_cell(line) for line in (row.get("earnings_anchor") or {}).get("lines") or ())
            if result["method"] == "revenue_case":
                request = row["request"]
                clock = MULTIPLE_CONSTRUCTION
                lines.append(f"{_cell(request['multiple_basis'])} / revenue ({clock}): {display_number(request['forecast']['value'])} × {display_number(request['multiple'])}; " +
                             ("equity basis, no debt or cash adjustment" if request['multiple_basis'] == 'equity' else f"less net obligations {display_number(result['net_obligations'])}") +
                             f"; divide by {display_number(result['shares_outstanding'])} assumed closing common shares at {request['capital']['valuation_date']}.")
                funding = row.get("funding")
                if isinstance(funding, dict):
                    lines.append(_cell(funding["summary"]) + " " + _cell(funding["limit"]))
                position = row.get("reference_position")
                if isinstance(position, dict) and position.get("status") == "available":
                    lines.append(_cell(position["summary"]))
                if isinstance(row.get("guidance_floor"), dict):
                    lines.append(_cell(row["guidance_floor"]["summary"]))
                supplemental = row.get("source_bound_sensitivity_requests", {})
                for basis, price in row["sensitivities"].items():
                    assumptions = []
                    if basis in supplemental:
                        for category, item in supplemental[basis]["capital"]["obligations"].items():
                            if category not in request["capital"]["obligations"]:
                                assumptions.append(_cell(item["reason"]))
                    label = (f"Sensitivity only, same numerical multiple held fixed — {_cell(basis)}: "
                             f"{display_value(price, _cell(result['unit']))}.")
                    lines.append(" ".join([label, *assumptions]))
            elif result["method"] == "ev_revenue":
                s = result["scenario_results"][0]
                lines.append(f"Revenue {display_number(s['revenue'])} × multiple {display_number(s['multiple'])} = enterprise value {display_number(s['enterprise_value'])}; less scenario net obligations {display_number(s['net_obligations'])} = conditional equity {display_number(s['equity_value'])}.")
                if result['status'] == 'supported':
                    lines.append(f"Conditional equity divided by {display_number(s['shares_outstanding'])} actual common shares = {display_number(s['price'])}.")
                else:
                    lines.append("Funding diagnostic only: no conditional price or return is published until the shortfall is resolved.")
                lines.append(f"Original capital snapshot: {result['capital_snapshot_date']}; scenario capital date: {s['capital_date']}; closing cash {display_number(s['closing_cash'])}; closing obligations {display_number(s['closing_obligations'])}; actual shares {display_number(s['shares_outstanding'])}; funding gap {display_number(s['funding_gap'])}.")
                lines.append(f"Multiple assumption date: {s.get('multiple_assumption_date') or 'undated; conditional sensitivity only'}.")
            else:
                lines.append(f"{_cell(result['eps_basis'])} EPS {display_number(result['earnings_value'])} × multiple {display_number(result['multiple'])} = {display_number(result['target'])}; {_cell(result['accounting_basis'])}.")
                lines.append(f"Multiple assumption date: {result.get('multiple_assumption_date') or 'undated; conditional sensitivity only'}.")
            if result['method'] not in ('revenue_case', 'earnings_case'):
                lines.append(f"Decision date: {result.get('decision_date') or 'not specified'}; unvalidated rerating assumption: {_cell(result.get('rerating_assumption') or 'not supplied')}.")
            lines.append("")
            lines += ["- " + _cell(v) for v in result["assumptions"] if not v.startswith("Scenario weights and valuation multiples")]
            for warning in result["warnings"]:
                # Original warnings remain in the base result. Qualify their
                # scope when the separate source-bound request is available.
                prefix = "Original submission: " if any(
                    warning.startswith(basis + " sensitivity unavailable:")
                    for basis in row.get("source_bound_sensitivity_requests", {})
                ) else "Limitation: "
                lines.append("- " + prefix + _cell(warning))
            if result['method'] not in ('revenue_case', 'earnings_case'):
                lines += ["", render_valuation_comparison(row.get('comparison'))]
    if record.get("status") == "partial":
        lines += ["", "Partial table: some proposed scenarios were omitted or remain unfunded diagnostics."]
    lines += ["- " + _cell(v) for v in record.get("reasons", [])]
    context = render_history_context(record.get("reference_history"))
    if context:
        lines += ["", _cell(context)]
    return "\n".join(lines)

