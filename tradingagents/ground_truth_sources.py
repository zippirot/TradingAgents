"""Fetch at most two incomplete, already identified SEC sources for an audit."""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import date

from pydantic import ValidationError

from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.vendors import sec_documents
from tradingagents.ground_truth import (
    DEFAULT_MAX_SECONDS,
    _digest,
    _known_before_cutoff,
    _positive,
    _trusted_sec_url,
)


def _candidates(state):
    cik = (state.get("issuer_identity") or {}).get("cik") or (state.get("financial_evidence") or {}).get("cik")
    cutoff = str(state.get("trade_date") or "")
    candidates, limits = {}, []
    try:
        date.fromisoformat(cutoff)
    except ValueError:
        return [], ["Analysis date unavailable for supplemental retrieval."]

    def inspect(value, package_gaps=False):
        if isinstance(value, list):
            for item in value:
                inspect(item, package_gaps)
        elif isinstance(value, dict):
            incomplete_package = package_gaps or bool(value.get("gaps"))
            for raw in value.get("documents") or []:
                try:
                    document = sec_documents.FilingDocument.model_validate(raw)
                    if not (incomplete_package or document.gaps or any(b.truncated for b in document.blocks)):
                        continue
                    if (document.filing.cik != cik or str(document.filing.filed_date) > cutoff
                            or not _trusted_sec_url(document.url, cik)
                            or not _trusted_sec_url(document.filing.url, cik)
                            or not _known_before_cutoff(state, document.filing.filed_date)
                            or not re.fullmatch(r"[0-9a-f]{64}", document.content_hash)):
                        raise ValueError("source scope invalid")
                    candidates[document.url] = document
                except (ValidationError, ValueError, TypeError):
                    limits.append("An incomplete source failed issuer, SEC address or cutoff validation.")
            for key, child in value.items():
                if key != "documents" and isinstance(child, (dict, list)):
                    inspect(child, incomplete_package)

    inspect(state.get("filing_evidence"))
    inspect(state.get("disclosure_evidence"))
    ordered = sorted(candidates.values(), key=lambda d: (str(d.filing.filed_date), d.url), reverse=True)
    if len(ordered) > 2:
        limits.append(f"Supplemental retrieval covers two of {len(ordered)} incomplete retained sources.")
    return ordered[:2], list(dict.fromkeys(limits))


def acquire_sources(state, config):
    """Return supplemental documents and telemetry without changing old evidence.

    Only enabled, unpublished runs can fetch. Repeated finalization reuses the
    signed same-run result. Missing source discovery is intentionally limited
    to trusted addresses already retained by the normal acquisition pipeline.
    """
    if config.get("ground_truth_audit") is not True or state.get("publication_record"):
        return {}
    candidates, limits = _candidates(state)
    identity = {key: state.get(key) for key in
                ("run_id", "company_of_interest", "trade_date", "issuer_identity", "analysis_clock")}
    binding = _digest({"identity": identity,
                       "candidates": [d.model_dump(mode="json") for d in candidates]})
    previous = state.get("ground_truth_source_acquisition")
    previous_docs = state.get("ground_truth_source_documents") or []
    if (isinstance(previous, dict) and previous.get("source_input_digest") == binding
            and previous.get("record_sha256") == _digest({
                "record": {k: v for k, v in previous.items() if k != "record_sha256"},
                "documents": previous_docs})):
        return {"ground_truth_source_documents": deepcopy(previous_docs),
                "ground_truth_source_acquisition": deepcopy(previous)}
    documents, errors, attempted = [], [], []
    requests = 0
    seconds = min(30, _positive(config, "ground_truth_max_seconds", DEFAULT_MAX_SECONDS, 14400))
    if candidates and seconds <= 0:
        limits.append("Supplemental retrieval skipped because the audit time allowance is exhausted.")
    if candidates and seconds > 0:
        # One shared client supplies an overall request/deadline allowance.
        client = sec_documents.DocumentClient(max_bytes=2_500_000, max_requests=2, max_seconds=seconds)
        with run_config(config):
            for document in candidates:
                attempted.append(document.url)
                try:
                    source = client.fetch(document.url)
                    raw = source["text"].encode("utf-8")
                    if (source["url"] != document.url or len(raw) > 2_500_000
                            or hashlib.sha256(raw).hexdigest() != source["content_hash"]):
                        raise ValueError("fetched content integrity mismatch")
                    blocks, _links, gaps = sec_documents.extract_sections(source["text"], max_chars=60000)
                    if not blocks:
                        raise ValueError("no source text")
                    identifier = "ground-truth-sec-" + hashlib.sha256(
                        (document.url + "\n" + source["content_hash"]).encode()).hexdigest()
                    supplement = sec_documents.FilingDocument(
                        source_id=identifier, filing=document.filing, url=document.url,
                        retrieved_at=source["retrieved_at"], content_hash=source["content_hash"],
                        blocks=tuple(blocks), gaps=tuple(gaps))
                    documents.append(supplement.model_dump(mode="json"))
                    if gaps or any(block.truncated for block in blocks):
                        limits.append("Supplemental extraction remains bounded; additional source text is omitted.")
                except Exception as exc:
                    errors.append(type(exc).__name__)
        requests = client.requests
    if errors:
        limits.append("Some supplemental source retrievals failed; retained sources remain available.")
    status = ("partial" if documents and (errors or limits) else "acquired" if documents else
              "unavailable" if candidates or limits else "not_needed")
    record = {"schema_version": 1, "status": status, "source_input_digest": binding,
              "attempted_urls": attempted, "requests": requests, "documents": len(documents),
              "limits": list(dict.fromkeys(limits)), "error_categories": errors,
              "bounds": {"max_requests": 2, "max_seconds": seconds, "max_bytes_per_document": 2_500_000,
                         "max_retained_characters": 120000}}
    record["record_sha256"] = _digest({"record": record, "documents": documents})
    return {"ground_truth_source_documents": documents, "ground_truth_source_acquisition": record}
