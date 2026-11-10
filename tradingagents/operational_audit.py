"""Small, run-bound observations and a deterministic operational report assessment.

This module judges execution and export evidence, never investment merit or the
quality of financial facts. It has no provider, graph, publication, or I/O calls.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

DEFINITIONS = {
    5: ("Strong", "Required work completed, integrity checks passed, and no material operational problem remains."),
    4: ("Good", "A minor operational issue occurred, with evidence it did not materially affect the report."),
    3: ("Degraded", "An operational problem reduced the reliability or completeness of identifiable parts of the report."),
    2: ("Low confidence", "A significant unresolved problem or missing essential evidence prevents establishing the reliability of important parts of the report."),
    1: ("Compromised", "A confirmed critical failure makes the report unreliable as a representation of this run."),
    None: ("Unrated — audit unavailable", "No usable run audit is available."),
}

# Explicit semantic classification. A source-supplied severity is never rating
# authority. In particular, answered no-data and routine recovered retries do
# not become incidents just because their numeric severity says otherwise.
REASONS = {
    "completed": (5, "Required work completed."),
    "vendor_no_data": (5, "The vendor answered with no matching data; no service failure was observed."),
    "model_retry_recovered": (5, "A model retry recovered and the required output completed."),
    "recovered_retry": (5, "A retry recovered and the required output completed."),
    "followup_judgment_overridden": (5, "A follow-up judgment was replaced by the retrieval result."),
    "vendor_fallback_recovered": (4, "A configured vendor failed, but another configured vendor supplied the input."),
    "fallback_recovered": (4, "A fallback supplied the required input after an earlier operation failed."),
    "optional_operation_failed": (4, "An optional operation failed; required inputs and outputs completed."),
    "optional_failure": (4, "An optional operation failed; required inputs and outputs completed."),
    "empty_output": (3, "A completed stage produced an empty output, reducing the usefulness of its section."),
    "vendor_unavailable": (3, "A vendor failure left an input unavailable for the affected section."),
    "input_unavailable": (3, "An input failure reduced support for the affected section."),
    "model_output_truncated": (3, "A model response was truncated before the full output was available."),
    "tool_error": (3, "A tool failed, reducing support for the affected section."),
    "summary_unavailable": (3, "The executive summary is unavailable; the underlying research and decision remain available."),
    "valuation_cases_rejected": (3, "Every submitted valuation case was rejected, so the report has no scenario values."),
    "price_session_fallback": (3, "The latest completed session had no close, so prices and indicators use an earlier session."),
    "valuation_case_rejected": (4, "A submitted valuation case was rejected; the remaining cases were priced."),
    "replay_miss": (3, "A comparison used a live external input absent from its baseline; input control is incomplete."),
    "stage_unusable": (2, "A required stage has no trustworthy usable completion."),
    "incomplete_history": (2, "Execution history is incomplete, so required work cannot be fully established."),
    "publication_mismatch": (1, "The saved report conflicts with the authoritative publication."),
    "mixed_run_input": (1, "A required stage used input belonging to another run."),
}

INPUT_NAMES = ("Stages", "Models/tools", "Run identity", "Report integrity", "Audit coverage")
_SAFE = re.compile(r"[A-Za-z][A-Za-z0-9_ -]{0,79}\Z")
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REVIEW_SKIP = {"Bull Researcher", "Bear Researcher", "Document Followup", "Research Manager",
                "Trader", "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst",
                "Advisory Audit", "Portfolio Manager"}


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def settings_digest(settings) -> str:
    """Hash only the retained, allowlisted run settings."""
    return hashlib.sha256(_canonical(settings).encode("utf-8")).hexdigest()


def _safe_text(value, limit=80) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Za-z0-9 _./:-]", "", value).strip()[:limit]


def observation(state, stage, *, status="completed", severity=5, code="completed", **optional) -> dict:
    """Build one bounded, replay-stable observation from a run's own identity."""
    if not isinstance(state, Mapping) or not isinstance(stage, str) or not _SAFE.fullmatch(stage):
        raise ValueError("invalid observation stage or state")
    if status not in {"completed", "unusable"} or not isinstance(code, str) or not _CODE.fullmatch(code):
        raise ValueError("invalid observation status or code")
    if type(severity) is not int or not 1 <= severity <= 5:
        raise ValueError("invalid observation severity")
    ticker = _safe_text(state.get("company_of_interest"), 32).upper()
    row = {"schema_version": 1, "run_id": _safe_text(state.get("run_id"), 128),
           "ticker": ticker, "trade_date": _safe_text(state.get("trade_date"), 10),
           "settings_sha256": settings_digest(state.get("run_settings")),
           "stage": stage, "status": status, "severity": severity, "code": code}
    if not row["run_id"] or not ticker or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["trade_date"]):
        raise ValueError("missing observation identity")
    stages = optional.get("expected_stages")
    if stages is not None:
        if not isinstance(stages, (list, tuple)) or len(stages) > 40 or any(
                not isinstance(item, str) or not _SAFE.fullmatch(item) for item in stages):
            raise ValueError("invalid expected stages")
        row["expected_stages"] = list(dict.fromkeys(stages))
    if optional.get("route") in {"full", "review"}:
        row["route"] = optional["route"]
    for field in ("scope", "locator"):
        if optional.get(field):
            row[field] = _safe_text(optional[field], 120)
    for field in ("count", "elapsed_ms"):
        value = optional.get(field)
        if type(value) is int and 0 <= value <= 1_000_000_000:
            row[field] = value
    if type(optional.get("recovered")) is bool:
        row["recovered"] = optional["recovered"]
    if optional.get("error_class"):
        row["error_class"] = _safe_text(optional["error_class"], 80)
    if optional.get("error_message"):
        row["error_message"] = _safe_text(optional["error_message"], 500)
    row["event_id"] = hashlib.sha256(_canonical(row).encode("utf-8")).hexdigest()
    return row


def _identity(row):
    return tuple(row.get(field) for field in ("run_id", "ticker", "trade_date", "settings_sha256"))


def merge_observations(left, right) -> dict:
    """Merge parallel node writes without loss; replaying a row changes nothing."""
    combined = {}
    identity = None
    for group in (left or {}, right or {}):
        if not isinstance(group, Mapping):
            raise ValueError("invalid observations")
        for key, row in group.items():
            if not isinstance(row, Mapping) or key != row.get("event_id"):
                raise ValueError("invalid observation row")
            current = _identity(row)
            if identity is not None and current != identity:
                raise ValueError("observation identity conflict")
            identity = current
            if key in combined and combined[key] != row:
                raise ValueError("observation event conflict")
            combined[key] = dict(row)
    return dict(sorted(combined.items()))


def _valid_row(key, row, identity):
    if not isinstance(row, Mapping) or key != row.get("event_id") or row.get("schema_version") != 1:
        return False
    if _identity(row) != identity or not isinstance(row.get("stage"), str) or not _SAFE.fullmatch(row["stage"]):
        return False
    if row.get("status") not in {"completed", "unusable"} or row.get("code") not in REASONS:
        return False
    if type(row.get("severity")) is not int or not 1 <= row["severity"] <= 5:
        return False
    payload = {k: v for k, v in row.items() if k != "event_id"}
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest() == key


def assess_audit(state, *, integrity="verified", expected_stages=None) -> dict:
    """Assess retained execution evidence plus the current export check."""
    raw = state.get("operational_observations") if isinstance(state, Mapping) else None
    identity = (state.get("run_id"), _safe_text(state.get("company_of_interest"), 32).upper(),
                str(state.get("trade_date")), settings_digest(state.get("run_settings"))) if isinstance(state, Mapping) else ()
    if not isinstance(raw, Mapping) or not raw:
        return _assessment(None, state, [], [], [], integrity, "No execution observations were retained.", 0, 0)

    rows = [row for key, row in raw.items() if _valid_row(key, row, identity)]
    invalid = len(raw) - len(rows)
    source = next((r for r in rows if r["stage"] == "Source Acquisition" and
                   isinstance(r.get("expected_stages"), list)), None)
    expected = expected_stages if expected_stages is not None else (source or {}).get("expected_stages")
    if not isinstance(expected, (list, tuple)) or not expected:
        expected = []
    else:
        expected = [x for x in dict.fromkeys(expected) if isinstance(x, str) and _SAFE.fullmatch(x)]
    gate = next((r for r in rows if r["stage"] == "Evidence Check" and r.get("route") in {"full", "review"}), None)
    if gate and gate["route"] == "review":
        expected = [stage for stage in expected if stage not in _REVIEW_SKIP]
    completed = {r["stage"] for r in rows if r["status"] == "completed"}
    missing = [stage for stage in expected if stage not in completed]
    if not expected:
        missing = ["Expected stage list"]
    if "Evidence Check" in expected and not gate:
        missing = list(dict.fromkeys([*missing, "Evidence Check route"]))

    findings = []
    for row in rows:
        code = row["code"]
        if code == "completed" or REASONS[code][0] == 5:
            continue
        score, meaning = REASONS[code]
        stage = row["stage"]
        scope = row.get("scope")
        text = f"{stage}: {meaning}"
        if scope:
            text += f" Affected: {scope}."
        findings.append({"score": score, "code": code, "stage": stage, "text": text,
                         "locator": row.get("locator") or f"operational_observations.{row['event_id'][:12]}"})
    if missing:
        findings.append({"score": 2, "code": "missing_stage", "stage": ", ".join(missing),
                         "text": "No trustworthy completion record for: " + ", ".join(missing) + ".",
                         "locator": "operational_observations"})
    if invalid:
        findings.append({"score": 2, "code": "invalid_observations", "stage": "Audit coverage",
                         "text": f"{invalid} observation record(s) were stale or malformed; their claims cannot be used.",
                         "locator": "operational_observations"})
    if integrity == "unverified":
        findings.append({"score": 2, "code": "unverified_export", "stage": "Report integrity",
                         "text": "The claimed publication could not be independently verified for this export.",
                         "locator": "publication_record"})
    elif integrity == "compromised":
        findings.append({"score": 1, "code": "compromised_export", "stage": "Report integrity",
                         "text": "The export conflicts with independently checked authoritative content.",
                         "locator": "publication_record"})
    elif integrity not in {"verified", "not_applicable"}:
        findings.append({"score": 2, "code": "unknown_integrity", "stage": "Report integrity",
                         "text": "Export integrity could not be established.", "locator": "publication_record"})
    summary = state.get("executive_summary") if isinstance(state, Mapping) else None
    if isinstance(summary, Mapping) and summary.get("status") == "unavailable":
        findings.append({"score": 3, "code": "summary_unavailable", "stage": "Executive Summary",
                         "text": "The executive summary is unavailable; the underlying research and decision remain available.",
                         "locator": "executive_summary.status"})
    findings.extend(_capability_findings(state))
    findings.sort(key=lambda item: (item["score"], item["stage"], item["code"]))
    score = min((item["score"] for item in findings), default=5)
    headline = [findings[0]['text']] if findings else []
    headline.extend(f['text'] for f in findings[1:] if f['code'] in {'fallback_recovered', 'vendor_fallback_recovered', 'model_fallback_recovered',
                                                                         'valuation_cases_rejected', 'price_session_fallback'})
    return _assessment(score, state, rows, expected, missing, integrity, ' '.join(dict.fromkeys(headline)) if findings else
                       "All required stages completed and no material operational problem was observed.", invalid, len(raw), findings)


def _capability_findings(state) -> list[dict]:
    """Stages can all complete while the report still loses its scenario values or its current price."""
    findings = []
    scenarios = state.get("shared_valuation_scenarios")
    if isinstance(scenarios, Mapping) and isinstance(scenarios.get("requests"), list) and isinstance(scenarios.get("rows"), list):
        submitted, priced = len(scenarios["requests"]), len(scenarios["rows"])
        if priced < submitted:
            code = "valuation_case_rejected" if priced else "valuation_cases_rejected"
            findings.append({"score": REASONS[code][0], "code": code, "stage": "Valuation Scenarios",
                             "text": f"Valuation Scenarios: {REASONS[code][1]} Rejected: {submitted - priced} of "
                                     f"{submitted} submitted valuation cases.",
                             "locator": "shared_valuation_scenarios.reasons"})
    price = state.get("price_observation")
    fallback = price.get("price_fallback") if isinstance(price, Mapping) else None
    if isinstance(fallback, Mapping):
        latest, selected = _safe_text(fallback.get("latest_completed_session_date"), 10), _safe_text(price.get("session_date"), 10)
        if latest and selected and latest != selected:
            code = "price_session_fallback"
            findings.append({"score": REASONS[code][0], "code": code, "stage": "Market Price",
                             "text": f"Market Price: {REASONS[code][1]} Used {selected}; latest completed session {latest}.",
                             "locator": "price_observation.price_fallback"})
    return findings


def _assessment(score, state, rows, expected, missing, integrity, consequence, invalid, total, findings=None):
    name, definition = DEFINITIONS[score]
    stages = "unknown" if score is None else ("missing: " + ", ".join(missing) if missing else "completed")
    model_issues = [f for f in (findings or []) if f["stage"] not in {"Audit coverage", "Report integrity"}
                    and f["code"] not in {"missing_stage"}]
    inputs = {
        "Stages": stages,
        "Models/tools": "unknown" if score is None else (model_issues[0]["code"].replace("_", " ") if model_issues else "no material failure observed"),
        "Run identity": "unknown" if score is None else ("mismatched or malformed record" if invalid else "matched"),
        "Report integrity": "unknown" if score is None else (
            "not applicable (in-memory rendering)" if integrity == "not_applicable" else integrity),
        "Audit coverage": "unavailable" if score is None else ("partial" if invalid or missing else "sufficient"),
    }
    publication = state.get("publication_record") if isinstance(state, Mapping) else None
    return {"score": score, "name": name, "definition": definition, "consequence": consequence,
            "inputs": inputs, "findings": findings or [],
            "coverage": {"expected_stages": expected, "observed_stages": sorted({r["stage"] for r in rows}),
                         "missing_stages": missing, "valid_observations": len(rows), "invalid_observations": invalid,
                         "total_observations": total},
            "run_id": _safe_text(state.get("run_id")) if isinstance(state, Mapping) else "",
            "ticker": _safe_text(state.get("company_of_interest"), 32).upper() if isinstance(state, Mapping) else "",
            "trade_date": _safe_text(state.get("trade_date"), 10) if isinstance(state, Mapping) else "",
            "publication_id": _safe_text(publication.get("decision_id"), 128) if isinstance(publication, Mapping) else ""}


def _verdict(assessment):
    score = assessment.get("score")
    return f"{score}/5 — {assessment['name']}" if score in DEFINITIONS and score is not None else DEFINITIONS[None][0]


def render_assessment(assessment, audit_path=None) -> str:
    """Render the compact final footer for either report format."""
    lines = [f"**Operational quality: {_verdict(assessment)}**", "",
             f"**Meaning:** {assessment['definition']}", "",
             f"**This run:** {assessment['consequence']}", "",
             "**Rating inputs:** " + " · ".join(f"{name}: {assessment['inputs'].get(name, 'unknown')}"
                                             for name in INPUT_NAMES) + "."]
    if audit_path and re.fullmatch(r"\./[A-Za-z0-9_.-]+\.md", audit_path):
        lines += ["", f"**Full operational audit:** [{audit_path}]({audit_path})"]
    return "\n".join(lines)


def render_audit(assessment) -> str:
    """Render a readable companion audit from the identical assessment."""
    lines = ["# Operational audit", "", f"**Operational quality: {_verdict(assessment)}**", "",
             assessment["definition"], "", assessment["consequence"], "",
             "## Run", "", f"- Run: {assessment.get('run_id') or 'unknown'}",
             f"- Ticker: {assessment.get('ticker') or 'unknown'}",
             f"- Analysis date: {assessment.get('trade_date') or 'unknown'}",
             f"- Publication: {assessment.get('publication_id') or 'not independently identified'}",
             "", "## Rating inputs", ""]
    lines.extend(f"- {name}: {assessment['inputs'].get(name, 'unknown')}" for name in INPUT_NAMES)
    coverage = assessment["coverage"]
    lines += ["", "## Execution coverage", "",
              "- Expected stages: " + (", ".join(coverage["expected_stages"]) or "unknown"),
              "- Observed stages: " + (", ".join(coverage["observed_stages"]) or "none"),
              f"- Valid observations: {coverage['valid_observations']}; invalid or stale: {coverage['invalid_observations']}"]
    if assessment["findings"]:
        lines += ["", "## Material findings", ""]
        lines.extend(f"- {item['text']} Record: `{item['locator']}`." for item in assessment["findings"])
    lines += ["", "## Observation limits", "",
              "Observations cover completed nodes. Events from an interrupted attempt before its last "
              "successful checkpoint are not retained, so their count and causes remain unknown after resume. "
              "Provider-internal retries and optional timing are unknown unless separately observed. "
              "This assessment describes execution and export integrity, not investment merit or financial evidence quality."]
    return "\n".join(lines) + "\n"
