"""Offline projection of a saved Ground Truth review onto its exact report."""
from collections.abc import Mapping
from copy import deepcopy


def _diagnostic_text(state, text):
    if isinstance(state.get('publication_record'), Mapping) and state['publication_record']:
        return text.replace('evidence.json diagnostics', 'diagnostics.json')
    return text


def _diagnostic_parts(state, parts):
    """Use the same diagnostic reference in published runtime and export views."""
    if not isinstance(state.get('publication_record'), Mapping) or not state['publication_record']:
        return parts
    return [(heading, folder, [(name, filename, _diagnostic_text(state, text))
                               for name, filename, text in written])
            for heading, folder, written in parts]


def build_report_inventory(state, parts=None, summary=None):
    from tradingagents.ground_truth import build_inventory
    from tradingagents.report_summary import resolve_summary
    from tradingagents.reporting import (
        _summary_markdown,
        prepare_report_state,
        report_sections,
        summary_input_for_report,
    )

    prepared = prepare_report_state(state)
    if parts is None:
        parts = report_sections(prepared)
    if summary is None:
        summary = resolve_summary(summary_input_for_report(prepared, parts=parts),
                                  prepared.get("executive_summary"))
    return build_inventory(prepared, parts=_diagnostic_parts(state, parts), summary_text=_diagnostic_text(state, _summary_markdown(summary)))


def project_report(state, parts, summary):
    """Return a copy of report parts with matching findings and reader detail."""
    enabled = (state.get("run_settings") or {}).get("ground_truth_audit") is True
    saved = state.get("ground_truth_audit")
    if not enabled and not saved:
        return parts, summary, "", None
    from tradingagents.ground_truth import (
        corrected_parts,
        corrected_text,
        render_audit,
        resolve_audit,
    )

    parts = _diagnostic_parts(state, parts)
    inventory = build_report_inventory(state, parts, summary)
    record = resolve_audit(state, saved, inventory=inventory)
    updated = corrected_parts(deepcopy(parts), record)
    from tradingagents.reporting import _summary_markdown

    summary = {**summary, "_ground_truth_text": corrected_text(
        "summary/summary.md", _diagnostic_text(state, _summary_markdown(summary)), record)}
    text = audit_assessment(record, state) + "\n\n" + render_audit(record)
    unresolved_material = _recommendation_needs_review(record, state)
    if unresolved_material:
        text += "\n\n**Recommendation needs review.** Material factual questions remain in the delivered conclusion or its premises."
    reassessment = state.get("ground_truth_reassessment")
    if isinstance(reassessment, dict):
        from tradingagents.reporting import _plain_markdown

        if reassessment.get("status") != "completed":
            text += "\n\n**Recommendation needs review.** The requested reassessment could not be completed."
        else:
            text += "\n\nOne Portfolio Manager reassessment completed. Original rating " + _plain_markdown(
                str(reassessment.get("original_rating") or "unavailable")) + "."
    return updated, summary, text, record


def audit_assessment(record, state):
    """A short assessment accompanies the full source and finding companion."""
    from collections import Counter

    from tradingagents.reporting import _plain_markdown

    coverage = record.get("coverage") or {}
    counts = Counter(claim.get("outcome") for claim in record.get("claims", []))
    text = "### Ground Truth Audit\n\nStatus **" + _plain_markdown(str(record.get("status", "unavailable"))) + "**. "
    text += f"Reviewed {coverage.get('reviewed_chunks', 0)} of {coverage.get('total_chunks', 0)} report chunks. "
    text += f"Contradicted claims {counts['contradicted']}, unsupported claims {counts['unsupported']}."
    text += "\n\nSource quotations and calculations are checked in code. Interpretation of source meaning uses model review."
    if _recommendation_needs_review(record, state):
        text += "\n\n**Recommendation needs review.** Material factual questions remain or reassessment was unavailable."
    issues = _unresolved_material_claims(record, state)
    if issues:
        from urllib.parse import quote

        text += "\n\nMaterial unresolved findings\n"
        for issue in issues[:3]:
            passage = str(issue.get("quoted_claim") or "")
            snippet = passage[:257] + "…" if len(passage) > 260 else passage
            text += "\n- **" + _plain_markdown(str(issue.get("outcome"))) + "** — “" + _plain_markdown(snippet) + "”"
            text += " — " + _plain_markdown(str(issue.get("chunk_id") or issue.get("section_id") or "location unavailable"))
            for source in issue.get("evidence") or []:
                url = source.get("url") or ""
                if isinstance(url, str) and url.startswith("https://"):
                    text += " [Source](" + quote(url, safe=":/?&=#%") + ")"
                    break
        remainder = len(issues) - min(3, len(issues))
        if remainder:
            text += f"\n\n{remainder} additional material unresolved finding(s) appear in the Full Ground Truth Audit."
        else:
            text += "\n\nThe Full Ground Truth Audit contains all findings and source details."
    if record.get("reason"):
        text += "\n\n" + _plain_markdown(str(record["reason"]))
    for limit in [*coverage.get("source_gaps", []), *record.get("limits", [])][:3]:
        text += "\n\n" + _plain_markdown(str(limit))
    return text


def _correction_key(claim):
    refs = tuple(sorted((str(ref.get("source_id")), str(ref.get("locator")))
                        for ref in claim.get("evidence", [])))
    return (claim.get("section_id"), claim.get("quoted_claim"), claim.get("correction"), refs)


def _recommendation_needs_review(record, state):
    reassessment = state.get("ground_truth_reassessment") or {}
    if not isinstance(reassessment, dict):
        return True
    if reassessment and reassessment.get("status") != "completed":
        return True
    corrections = reassessment.get("corrections", [])
    if not isinstance(corrections, list) or any(not isinstance(c, dict) for c in corrections):
        return True
    return bool(_unresolved_material_claims(record, state))


def _unresolved_material_claims(record, state):
    reassessment = state.get("ground_truth_reassessment") or {}
    corrections = reassessment.get("corrections", []) if isinstance(reassessment, dict) else []
    handled = set()
    if (isinstance(reassessment, dict) and reassessment.get("status") == "completed"
            and isinstance(corrections, list) and all(isinstance(c, dict) for c in corrections)):
        handled = {_correction_key(c) for c in corrections}
    issues = []
    for claim in record.get("claims", []):
        if claim.get("decision_material") is not True:
            continue
        if claim.get("outcome") == "unsupported" or claim.get("outcome") == "contradicted" and (
                not claim.get("correction") or claim.get("ambiguous_location")
                or _correction_key(claim) not in handled):
            issues.append(claim)
    return sorted(issues, key=lambda claim: claim.get("outcome") != "contradicted")
