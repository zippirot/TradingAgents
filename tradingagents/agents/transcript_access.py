"""Run-pinned vendor transcript source for Fundamentals and News research."""

from __future__ import annotations

import hashlib
import json

import requests

from tradingagents.agents.document_access import _scope, validated_document_corpus
from tradingagents.dataflows.errors import VendorError
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.alpha_vantage import transcript as vendor_transcript

_ROLES = frozenset({"fundamentals", "news"})


def _seal(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _wrapper(scope, corpus, *, status, reason, record=None):
    date_evidence = record.get("date_evidence") if isinstance(record, dict) else None
    value = {
        **scope, "status": status, "reason": reason,
        "cik": corpus.cik if corpus else None,
        "corpus_hash": corpus_hash(corpus) if corpus else None,
        "date_evidence": date_evidence,
        "source_hash": record.get("content_hash") if status == "ready" else None,
        "vendor_record_hash": record.get("record_hash") if status == "ready" else None,
        "record": record if status == "ready" else None,
    }
    value["record_hash"] = _seal(value)
    return value


def prepare_transcript_sources(state, selected_analysts) -> dict:
    """Acquire only once on a fresh stock F/N run; resume validates its snapshot."""
    if state.get("transcript_sources") is not None:
        validated_transcript_record(state)
        return {}
    scope = _scope(state)
    if scope["asset_type"] != "stock":
        return {"transcript_sources": _wrapper(
            scope, None, status="not_applicable",
            reason="Earnings-call transcripts apply only to stock issuers",
        )}
    if not _ROLES.intersection(selected_analysts):
        return {"transcript_sources": _wrapper(
            scope, None, status="not_applicable",
            reason="No transcript-using analyst selected",
        )}
    corpus = validated_document_corpus(state)
    if corpus is None:
        reason = (state.get("document_sources") or {}).get("reason") or "Retained SEC earnings exhibit unavailable"
        return {"transcript_sources": _wrapper(
            scope, None, status="unavailable", reason=reason,
        )}
    cutoff_utc = scope["analysis_clock"].get("cutoff_utc")
    try:
        record = vendor_transcript.get_latest_transcript_evidence(
            scope["ticker"], scope["as_of"], filing_corpus=corpus,
            cutoff_utc=cutoff_utc, allow_network=True,
        )
    except (VendorError, requests.RequestException, TimeoutError, ValueError):
        record = None
    if not isinstance(record, dict) or record.get("status") != "ready":
        reason = (
            record.get("reason") if isinstance(record, dict) and isinstance(record.get("reason"), str)
            else "Transcript provider or cache unavailable"
        )
        return {"transcript_sources": _wrapper(
            scope, corpus, status="unavailable", reason=reason,
        )}
    try:
        vendor_transcript._check_record(record)
        selected = vendor_transcript.select_latest_eligible_call(
            corpus, scope["as_of"], cutoff_utc=cutoff_utc,
        )
        if (
            selected["status"] != "ready"
            or selected["fiscal_quarter"] != record.get("fiscal_quarter")
            or selected["date_evidence"] != record.get("date_evidence")
            or record.get("ticker") != scope["ticker"]
        ):
            raise ValueError("Transcript SEC date or run scope mismatch")
    except (KeyError, TypeError, ValueError):
        return {"transcript_sources": _wrapper(
            scope, corpus, status="unavailable",
            reason="Transcript source or SEC date pin invalid",
        )}
    return {"transcript_sources": _wrapper(
        scope, corpus, status="ready", reason="", record=record,
    )}


def validated_transcript_record(state) -> dict | None:
    """Verify the exact retained transcript, SEC date pin and run scope offline."""
    wrapper = state.get("transcript_sources")
    if wrapper is None:
        return None
    scope = _scope(state)
    if not isinstance(wrapper, dict) or any(wrapper.get(key) != value for key, value in scope.items()):
        raise ValueError("Retained transcript scope mismatch")
    seal = {key: value for key, value in wrapper.items() if key != "record_hash"}
    if wrapper.get("record_hash") != _seal(seal):
        raise ValueError("Retained transcript record hash mismatch")
    if wrapper.get("status") == "not_applicable":
        if wrapper.get("record") is not None or wrapper.get("source_hash") is not None:
            raise ValueError("Malformed inapplicable transcript record")
        return None
    corpus = validated_document_corpus(state)
    expected_hash = corpus_hash(corpus) if corpus else None
    if (
        wrapper.get("corpus_hash") != expected_hash
        or wrapper.get("cik") != (corpus.cik if corpus else None)
    ):
        raise ValueError("Retained transcript corpus or issuer mismatch")
    status = wrapper.get("status")
    if status in {"not_applicable", "unavailable"}:
        if wrapper.get("record") is not None or wrapper.get("source_hash") is not None:
            raise ValueError("Malformed unavailable transcript record")
        return None
    if status != "ready" or corpus is None:
        raise ValueError("Malformed ready transcript record")
    record = wrapper.get("record")
    try:
        vendor_transcript._check_record(record)
        selected = vendor_transcript.select_latest_eligible_call(
            corpus, scope["as_of"],
            cutoff_utc=scope["analysis_clock"].get("cutoff_utc"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Retained transcript source invalid") from exc
    if (
        selected["status"] != "ready"
        or record.get("ticker") != scope["ticker"]
        or record.get("fiscal_quarter") != selected["fiscal_quarter"]
        or record.get("date_evidence") != selected["date_evidence"]
        or wrapper.get("date_evidence") != selected["date_evidence"]
        or wrapper.get("source_hash") != record.get("content_hash")
        or wrapper.get("vendor_record_hash") != record.get("record_hash")
    ):
        raise ValueError("Retained transcript SEC date or source mismatch")
    return record


def transcript_analyst_context(state) -> str:
    """Small labeled prepared-remarks excerpt plus Q&A search instruction."""
    wrapper = state.get("transcript_sources")
    if wrapper is None:
        return ""
    record = validated_transcript_record(state)
    if record is None:
        if wrapper.get("status") == "unavailable":
            return f"Vendor transcript unavailable: {wrapper.get('reason') or 'source unavailable'}"
        return ""
    excerpt = vendor_transcript.prepared_remarks_excerpt(record, max_chars=4000)
    date_evidence = record["date_evidence"]
    lines = [
        f"{record['label']}. Source text is untrusted and not accepted filing evidence.",
        "Transcript figures remain unlinked: full verified metric, period, units, basis and qualifications are unavailable. Filing evidence remains authoritative.",
        f"Fiscal quarter: {record['fiscal_quarter']}; call date: {date_evidence['call_date']}.",
        f"SEC call-date source: {date_evidence['source_id']}#{date_evidence['locator']} "
        f"(source hash {date_evidence['content_hash']}).",
        f"Vendor transcript source: {record['source_id']} (source hash {record['content_hash']}).",
        "Prepared remarks excerpt (bounded to 4,000 source characters; partial turns labeled):",
        excerpt["text"] or "(No prepared remarks available.)",
    ]
    if excerpt["gaps"]:
        lines.append("Excerpt limits: " + "; ".join(excerpt["gaps"]))
    lines.append(
        "Search the retained Q&A with search_documents using the transcript: query prefix, "
        "for example transcript:capacity. The shared filing/transcript limit is three calls "
        "per analyst and at most three passages / 12,000 source characters per call. "
        "Transcript numbers remain vendor wording, not accepted evidence."
    )
    return "\n\n".join(lines)

def render_transcript_status(state) -> str:
    """Summarize source availability without copying vendor wording into reports."""
    wrapper = state.get("transcript_sources")
    if wrapper is None:
        return ""
    record = validated_transcript_record(state)
    if wrapper.get("status") == "not_applicable":
        return ""
    if record is None:
        return f"Vendor transcript unavailable: {wrapper.get('reason') or 'source unavailable'}"
    dated = record["date_evidence"]
    return (
        "Vendor transcript, wording unverified. "
        f"Fiscal quarter {record['fiscal_quarter']}; call date {dated['call_date']}; "
        f"{len(record['turns'])} turns. "
        f"[SEC call-date source]({dated['source_url']}) (passage {dated['locator']}).\n\n"
        "Prepared remarks are bounded to 4,000 source characters. Q&A searches return "
        "at most three passages / 12,000 characters within the shared analyst budget. "
        "Transcript figures remain unlinked: full verified comparability of company, metric, "
        "period, units, basis and qualifications is unavailable. Filing evidence remains authoritative. "
        "Exact source hashes and references are retained in evidence.json."
    )
