"""Optional pre-debate scenarios, calculated with the final valuation engine.

Forecasts and multiples remain model assumptions. This record never determines
an actionable rating, a final target, or the evidence gate's verdict.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, localcontext

from pydantic import ValidationError

from tradingagents.agents.accounting_checks import _OBLIGATION_METRICS
from tradingagents.agents.case_reference import (
    history_context,
    reference_position,
    render_history_context,
)
from tradingagents.agents.evidence_validation import _select_compatible_fact, obligation_checks
from tradingagents.agents.retained_kpi_context import lease_maturities
from tradingagents.agents.valuation import EVRevenueTarget, PETarget, validate_target
from tradingagents.agents.valuation_cases import (
    RevenueCase,
    case_funding,
    obligation_bases,
    price_case,
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
    return {"schedule": schedule, "notes": notes if isinstance(notes, list) else []}


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
        for category, metrics in _OBLIGATION_METRICS.items():
            if category in obligations or category not in permitted:
                continue
            group = [f for f in source_facts if f.metric in metrics]
            if group:
                with localcontext() as ctx:
                    ctx.prec = 60
                    obligations[category] = {
                        "value": str(sum(f.value for f in group)), "fact_ids": [f.fact_id for f in group],
                        "assumption": "unchanged_from_snapshot",
                        "reason": (f"{category} obligations as of {result.capital_snapshot_date} held constant "
                                   f"through {capital.valuation_date}, with no growth or repayment assumed."),
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
    for index, row in enumerate(requests, 1):
        try:
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
                request = RevenueCase.model_validate(_label_capital_estimates(raw, index, row_notes))
                notes += row_notes
                result, sensitivities = price_case(request, package, outlooks, terms)
                supplemental = _source_bound_lease_requests(request, result, package, outlooks, sensitivities, terms)
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
            if isinstance(request, RevenueCase):
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
                         "diagnostic_only": not isinstance(request, RevenueCase), "comparison": comparison, "sensitivities": sensitivities,
                         **({"funding": case_funding(request, package, terms)} if isinstance(request, RevenueCase) else {}),
                         **({"source_bound_sensitivity_requests": supplemental} if supplemental else {})})
        except ValidationError as exc:
            error = exc.errors(include_input=False)[0]
            reasons.append(f"Row {index} omitted: malformed valuation request at " + ".".join(map(str, error["loc"])))
        except (ValueError, TypeError, ArithmeticError) as exc:
            reasons.append(f"Row {index} omitted: {exc}")
    if comparisons and all(r["request"]["method"] != "revenue_case" for r in rows) and any(key != comparisons[0] for key in comparisons[1:]):
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
    record = _record(status, requests, rows, [*reasons, *notes])
    priced = [row for row in rows if row["result"]["method"] == "revenue_case"]
    for row in priced:
        row["reference_position"] = reference_position(row, state)
    if any(row["reference_position"]["status"] == "available" for row in priced):
        record["reference_history"] = history_context(state)
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
        clean = {key: value for key, value in row.items() if key != 'disputed_by'}
        rows.append({**clean, **({'disputed_by': ids} if ids else {})})
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
            f'Analyst case "{case["name"]}" was corrected after a validation error before this revision: {case["cause"]}'
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
            or record.get("submission_error") == "missing_block"
            or not (record.get("submission_error") or omitted)):
        return record
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
    if row.get("disputed_by"):
        return f"{value} — disputed ({', '.join(row['disputed_by'])}), excluded from range"
    return value


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
            lines.append(" | ".join(_cell(v) for v in (row["name"], {"pe": "P/E", "ev_revenue": "EV/revenue", "revenue_case": row["request"].get("multiple_basis", "") + " / " + row["request"].get("multiple_period", "") + " revenue"}[result["method"]],
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
                lines.append('Disputed by accepted audit finding ' + ', '.join(row['disputed_by']) + '; excluded from conditional range. Arithmetic retained unchanged.')
            if result["method"] == "revenue_case":
                request = row["request"]
                clock = "trailing at the future valuation date" if request["multiple_period"] == "trailing" else "forward from the analysis date"
                lines.append(f"{_cell(request['multiple_basis'])} / revenue ({clock}): {display_number(request['forecast']['value'])} × {display_number(request['multiple'])}; " +
                             ("equity basis, no debt or cash adjustment" if request['multiple_basis'] == 'equity' else f"less net obligations {display_number(result['net_obligations'])}") +
                             f"; divide by {display_number(result['shares_outstanding'])} assumed closing common shares at {request['capital']['valuation_date']}.")
                funding = row.get("funding")
                if isinstance(funding, dict):
                    lines.append(_cell(funding["summary"]) + " " + _cell(funding["limit"]))
                position = row.get("reference_position")
                if isinstance(position, dict) and position.get("status") == "available":
                    lines.append(_cell(position["summary"]))
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
            if result['method'] != 'revenue_case':
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
            if result['method'] != 'revenue_case':
                lines += ["", render_valuation_comparison(row.get('comparison'))]
    if record.get("status") == "partial":
        lines += ["", "Partial table: some proposed scenarios were omitted or remain unfunded diagnostics."]
    lines += ["- " + _cell(v) for v in record.get("reasons", [])]
    context = render_history_context(record.get("reference_history"))
    if context:
        lines += ["", _cell(context)]
    return "\n".join(lines)

