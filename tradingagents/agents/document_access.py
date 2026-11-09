"""Run-scoped SEC document corpus and bounded analyst search journal.

The retained corpus is private run state. Only passages actually returned in the
journal are converted to quoteable DisclosurePackages.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from tradingagents.dataflows.date_window import resolve_analysis_cutoff
from tradingagents.dataflows.errors import NoMarketDataError, VendorError
from tradingagents.dataflows.filing_search import (
    corpus_hash,
    replay_legacy_filing_evidence,
    search_filing_evidence,
)
from tradingagents.dataflows.router import no_data_available
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

_ROLES = frozenset({"fundamentals", "news"})
_LIMIT = 3


def _scope(state):
    return {
        "schema_version": 1,
        "ticker": normalize_symbol(state.get("company_of_interest", "")),
        "as_of": str(state.get("trade_date", "")),
        "asset_type": state.get("asset_type", "stock"),
        "analysis_clock": dict(state.get("analysis_clock") or {}),
    }


def _intraday_unproven(document, scope):
    """A filingDate proves its day, not availability before an explicit instant."""
    clock = scope["analysis_clock"]
    resolved = resolve_analysis_cutoff(
        scope["as_of"], clock.get("analysis_timezone") or clock.get("timezone"),
        clock.get("cutoff_utc"),
    )
    local = datetime.fromisoformat(resolved["cutoff_utc"]).astimezone(
        ZoneInfo(resolved["analysis_timezone"]))
    return local.time() < time.max and document.filing.filed_date >= local.date()


def _check_corpus(corpus, scope, expected_cik, *, strict_identity=True):
    if corpus.schema_version != 1 or str(corpus.as_of) != scope["as_of"]:
        raise ValueError("Document corpus analysis cutoff mismatch")
    if expected_cik and corpus.cik != expected_cik:
        raise ValueError("Document corpus issuer mismatch")
    try:
        cutoff = date.fromisoformat(scope["as_of"])
        clock = scope["analysis_clock"]
        resolved = resolve_analysis_cutoff(
            scope["as_of"], clock.get("analysis_timezone") or clock.get("timezone"),
            clock.get("cutoff_utc"),
        )
        clock_cutoff = datetime.fromisoformat(resolved["cutoff_utc"]).astimezone(
            ZoneInfo(resolved["analysis_timezone"])
        ).date()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Document analysis cutoff unavailable") from exc
    ids = set()
    for document in corpus.documents:
        filing = document.filing
        if filing.cik != corpus.cik or filing.filed_date > cutoff or filing.filed_date > clock_cutoff or (
            filing.report_date and (filing.report_date > cutoff or filing.report_date > clock_cutoff)
        ):
            raise ValueError("Document corpus issuer or filing date mismatch")
        if document.source_id in ids:
            raise ValueError("Duplicate document source ID")
        ids.add(document.source_id)
        if strict_identity and _intraday_unproven(document, scope):
            raise ValueError("Same-day document publication time unavailable at intraday cutoff")
        if document.url != filing.url and not document.url.startswith(
            filing.url.rsplit("/", 1)[0] + "/"
        ):
            raise ValueError("Document URL outside filing accession")
        if strict_identity and document.source_id != "sec-document-" + hashlib.sha256(document.url.encode()).hexdigest():
            raise ValueError("Document source identity mismatch")
        locators = [block.locator for block in document.blocks]
        if len(set(locators)) != len(locators):
            raise ValueError("Duplicate document block locator")


def prepare_document_sources(state, selected_analysts) -> dict:
    """Acquire once during fresh SourceAcquisition; resumed runs keep their vintage."""
    if state.get("document_sources") is not None:
        validated_document_corpus(state)
        return {}
    scope = _scope(state)
    record = {
        **scope, "status": "not_applicable", "cik": None,
        "corpus": None, "corpus_hash": None, "reason": "",
    }
    if scope["asset_type"] != "stock":
        record["reason"] = "SEC document search applies only to stock issuers"
        return {"document_sources": record}
    if not _ROLES.intersection(selected_analysts):
        record["reason"] = "No filing-using analyst selected"
        return {"document_sources": record}

    bounded = state.get("filing_evidence")
    try:
        bounded_package = DisclosurePackage.model_validate(bounded) if bounded else None
        if bounded_package is not None:
            _check_corpus(bounded_package, scope, (state.get("issuer_identity") or {}).get("cik"), strict_identity=False)
        from tradingagents.dataflows.vendors.sec_documents import get_filing_search_evidence
        corpus = get_filing_search_evidence(
            scope["ticker"], scope["as_of"], bounded_package=bounded_package
        )
        omitted = [doc for doc in corpus.documents if _intraday_unproven(doc, scope)]
        if omitted:
            corpus = corpus.model_copy(update={
                "documents": tuple(doc for doc in corpus.documents if doc not in omitted),
                "gaps": (*corpus.gaps, *(
                    f"{doc.filing.accession} {doc.url}: omitted; same-day publication time unavailable at intraday cutoff"
                    for doc in omitted)),
            })
        _check_corpus(corpus, scope, (state.get("issuer_identity") or {}).get("cik"))
    except VendorError as exc:
        reason = (f"SEC unavailable: {no_data_available(exc)}" if isinstance(exc, NoMarketDataError)
                  else f"SEC unavailable ({type(exc).__name__})")
        record.update(status="unavailable", reason=reason)
        return {"document_sources": record}
    except ValidationError as exc:
        raise ValueError("Malformed bounded filing evidence") from exc

    record.update(
        status="ready", cik=corpus.cik, corpus=corpus.model_dump(mode="json"),
        corpus_hash=corpus_hash(corpus),
    )
    return {"document_sources": record}


def validated_document_corpus(state) -> DisclosurePackage | None:
    """Check exact retained corpus and run scope; old states safely have none."""
    record = state.get("document_sources")
    if record is None:
        return None
    if not isinstance(record, dict) or any(record.get(k) != v for k, v in _scope(state).items()):
        raise ValueError("Retained document source scope mismatch")
    if record.get("status") != "ready":
        if record.get("status") not in {"not_applicable", "unavailable"} or record.get("corpus") is not None:
            raise ValueError("Malformed unavailable document source")
        return None
    if not record.get("corpus") or not record.get("corpus_hash") or not record.get("cik"):
        raise ValueError("Incomplete document corpus")
    try:
        corpus = DisclosurePackage.model_validate(record["corpus"])
    except ValidationError as exc:
        raise ValueError("Malformed document corpus") from exc
    expected_cik = (state.get("issuer_identity") or {}).get("cik") or record["cik"]
    if corpus.cik != record["cik"]:
        raise ValueError("Document corpus issuer mismatch")
    _check_corpus(corpus, _scope(state), expected_cik)
    if corpus_hash(corpus) != record["corpus_hash"]:
        raise ValueError("Document corpus hash mismatch")
    return corpus


def merge_search_traces(left: dict | None, right: dict | None) -> dict:
    """LangGraph reducer: parallel updates commute unless an ID conflicts."""
    merged = dict(left or {})
    for key, entry in (right or {}).items():
        if key in merged and merged[key] != entry:
            raise ValueError(f"Document search trace conflict for {key}")
        merged[key] = entry
    return merged


def _batch_position(state, role, call_id, trace):
    messages = state.get("messages") or ()
    latest = next((message for message in reversed(messages) if isinstance(message, AIMessage)), None)
    if latest is None:
        return sum(key.startswith(role + ":") and entry.get("counted") for key, entry in trace.items())
    ids = [item.get("id") for item in latest.tool_calls if item.get("name") == "search_documents"]
    if call_id not in ids:
        return sum(key.startswith(role + ":") and entry.get("counted") for key, entry in trace.items())
    if any(not ident for ident in ids) or len(ids) != len(set(ids)):
        raise ValueError("Document search batch has missing or duplicate call IDs")
    previous = {key.split(":", 1)[1] for key, entry in trace.items()
                if key.startswith(role + ":") and entry.get("counted")}
    return len(previous) + sum(ident not in previous for ident in ids[:ids.index(call_id)])


def search_retained_document_sources(state, query, *, max_passages=3, max_chars=12000):
    """Explicit transcript: queries search vendor Q&A; default stays SEC filings."""
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise ValueError("Search query must contain 1-200 characters")
    corpus = validated_document_corpus(state)
    if query.casefold().startswith("transcript:"):
        from tradingagents.agents.transcript_access import validated_transcript_record
        from tradingagents.dataflows.vendors.alpha_vantage.transcript import (
            search_transcript_evidence,
        )

        record = validated_transcript_record(state)
        if record is None:
            wrapper = state.get("transcript_sources") or {}
            return {"passages": [], "gaps": [wrapper.get("reason") or "Transcript unavailable"],
                    "unavailable": True}
        return search_transcript_evidence(record, query.split(":", 1)[1].strip(),
                                         max_passages=max_passages, max_chars=max_chars)
    if corpus is None:
        return {"passages": [], "gaps": ["Retained filing source unavailable"], "unavailable": True}
    return search_filing_evidence(corpus, query, max_passages=max_passages, max_chars=max_chars)


def run_document_search(state, query, *, role: str, call_id: str) -> dict:
    """Return one reducer update and one public result, without new acquisition."""
    if role not in _ROLES or not isinstance(call_id, str) or not call_id:
        raise ValueError("Invalid document search role or call ID")
    trace = state.get("document_search_trace") or {}
    if not isinstance(trace, dict):
        raise ValueError("Malformed document search trace")
    key = f"{role}:{call_id}"
    corpus = validated_document_corpus(state)
    retained_search_packages(state)
    transcript_hash = None
    if isinstance(query, str) and query.casefold().startswith("transcript:"):
        from tradingagents.agents.transcript_access import validated_transcript_record
        validated_transcript_record(state)
        transcript_hash = (state.get("transcript_sources") or {}).get("record_hash")
    prior = trace.get(key)
    position = _batch_position(state, role, call_id, trace)
    if prior is not None:
        if prior.get("query") != query:
            raise ValueError("Document search call ID reused with different query")
        if corpus is None and prior.get("passages"):
            raise ValueError("Document passages exist without retained corpus")
        if corpus and prior.get("corpus_hash") != corpus_hash(corpus):
            raise ValueError("Document search corpus changed on resume")
        if prior.get("passages"):
            retained_search_packages(state)
        return {"document_search_trace": {key: prior}, "result": dict(prior)}
    result = {
        "query": query, "role": role, "call_id": call_id,
        "search_version": 3,
        "status": "unavailable", "counted": position < _LIMIT,
        "corpus_hash": corpus_hash(corpus) if corpus else None,
        "passages": [], "gaps": [], "reason": "",
    }
    if isinstance(query, str) and query.casefold().startswith("transcript:"):
        result["transcript_hash"] = transcript_hash
    if position >= _LIMIT:
        result.update(status="limit_reached", reason=f"At most {_LIMIT} document searches per analyst")
    elif corpus is None:
        result["reason"] = (state.get("document_sources") or {}).get("reason") or "Document corpus unavailable"
    else:
        try:
            found = search_retained_document_sources(state, query, max_passages=3, max_chars=12000)
        except ValueError as exc:
            result.update(status="invalid_query", reason=str(exc))
        else:
            result.update(
                status="ok" if found["passages"] else "unavailable" if found.get("unavailable") else "not_found",
                passages=found["passages"], gaps=found["gaps"],
                reason="" if found["passages"] else "; ".join(found["gaps"]),
            )
    return {"document_search_trace": {key: result}, "result": result}


def _validate_search_trace(trace, corpus):
    if not isinstance(trace, dict):
        raise ValueError("Malformed document search trace")
    counts = dict.fromkeys(_ROLES, 0)
    for key, entry in trace.items():
        if (not isinstance(entry, dict) or entry.get("role") not in _ROLES
                or not isinstance(entry.get("call_id"), str) or not entry["call_id"]
                or key != f"{entry['role']}:{entry['call_id']}"
                or type(entry.get("counted")) is not bool):
            raise ValueError("Malformed document search journal entry")
        version = entry.get("search_version", 2)
        if type(version) is not int or version not in {2, 3}:
            raise ValueError("Unknown document search journal version")
        status = entry.get("status")
        if status not in {"ok", "not_found", "invalid_query", "unavailable", "limit_reached"}:
            raise ValueError("Malformed document search journal status")
        if entry["counted"] != (status != "limit_reached"):
            raise ValueError("Invalid document search counted status")
        counts[entry["role"]] += entry["counted"]
        if counts[entry["role"]] > _LIMIT:
            raise ValueError("Retained document search call limit exceeded")
        passages = entry.get("passages")
        if (not isinstance(passages, list) or len(passages) > 3
                or any(not isinstance(p, dict) or not isinstance(p.get("text"), str) for p in passages)
                or sum(len(p["text"]) for p in passages) > 12000):
            raise ValueError("Document search passage limit exceeded")
        if bool(passages) != (status == "ok"):
            raise ValueError("Document search passage status mismatch")
        if passages and corpus is None:
            raise ValueError("Document passages exist without retained corpus")
        if entry.get("corpus_hash") != (corpus_hash(corpus) if corpus else None):
            raise ValueError("Document search journal corpus mismatch")


def retained_search_packages(state) -> list[DisclosurePackage]:
    """Reconstruct quoteable packages solely from exact journal-returned blocks."""
    corpus = validated_document_corpus(state)
    trace = state.get("document_search_trace") or {}
    _validate_search_trace(trace, corpus)
    if corpus is None:
        if any(not isinstance(entry, dict) or entry.get("passages") for entry in trace.values()):
            raise ValueError("Document passages exist without retained corpus")
        return []
    documents = {doc.source_id: doc for doc in corpus.documents}
    packages = []
    for key, entry in trace.items():
        if isinstance(entry.get("query"), str) and entry["query"].casefold().startswith("transcript:"):
            from tradingagents.agents.transcript_access import validated_transcript_record

            validated_transcript_record(state)
            if entry.get("transcript_hash") != (state.get("transcript_sources") or {}).get("record_hash"):
                raise ValueError("Retained transcript search source changed")
        if not isinstance(entry, dict) or key != f"{entry.get('role')}:{entry.get('call_id')}" or entry.get("role") not in _ROLES:
            raise ValueError("Malformed document search journal entry")
        if entry.get("corpus_hash") != corpus_hash(corpus):
            raise ValueError("Document search journal corpus mismatch")
        passages = entry.get("passages")
        if not isinstance(passages, list) or len(passages) > 3 or sum(len(p.get("text", "")) for p in passages) > 12000:
            raise ValueError("Document search passage limit exceeded")
        if not passages:
            continue
        if not entry.get("counted") or entry.get("status") != "ok":
            raise ValueError("Uncounted document search passage")
        try:
            if entry.get("search_version", 2) == 2 and not entry["query"].casefold().startswith("transcript:"):
                expected = replay_legacy_filing_evidence(corpus, entry["query"], max_passages=3, max_chars=12000)
            else:
                expected = search_retained_document_sources(state, entry["query"], max_passages=3, max_chars=12000)
        except (KeyError, ValueError) as exc:
            raise ValueError("Invalid retained document search query") from exc
        if expected["passages"] != passages:
            raise ValueError("Document search passage differs from retained source")
        chosen = {}
        for passage in passages:
            if passage.get("provider") == "Alpha Vantage":
                continue  # Exact vendor return validated above; never accepted filing evidence.
            doc = documents.get(passage["source_id"])
            if doc is None or passage["content_hash"] != doc.content_hash:
                raise ValueError("Document search source mismatch")
            block = next((b for b in doc.blocks if b.locator == passage["locator"]), None)
            if block is None or block.truncated or passage["passage_hash"] != hashlib.sha256(block.text.encode()).hexdigest():
                raise ValueError("Document search block mismatch")
            chosen.setdefault(doc.source_id, set()).add(block.locator)
        if not chosen:
            continue
        selected = tuple(
            doc.model_copy(update={"blocks": tuple(
                block for block in doc.blocks if block.locator in chosen.get(doc.source_id, ())
            )})
            for doc in corpus.documents if doc.source_id in chosen
        )
        packages.append(corpus.model_copy(update={
            "documents": selected,
            "selected_accessions": tuple(dict.fromkeys(doc.filing.accession for doc in selected)),
        }))
    return packages



def render_document_searches(state) -> str:
    """Report acquisition gaps and each attempted query without dumping source text."""
    record = state.get("document_sources")
    trace = state.get("document_search_trace") or {}
    if record is None and not trace:
        return ""
    corpus = validated_document_corpus(state)
    retained_search_packages(state)
    def cell(value):
        return str(value or "").replace("|", "\\|").replace("\n", " ")
    lines = ["#### Document searches", ""]
    if corpus is None:
        lines.append("Document search unavailable: " + cell((record or {}).get("reason") or "No retained filings"))
    else:
        lines.append(f"Retained filings: {len(corpus.documents)} documents. Search results are source text; interpretations require validation.")
        if corpus.gaps:
            lines += ["", "Acquisition omissions and limits:", *("- " + cell(gap) for gap in corpus.gaps)]
    if not trace:
        lines += ["", "No analyst document searches were run."]
    else:
        lines += ["", "Analyst | Query | Status | Passages | Finding", "--- | --- | --- | --- | ---"]
        for key, entry in sorted(trace.items()):
            if not isinstance(entry, dict):
                raise ValueError("Malformed document search trace")
            reason = entry.get("reason") or ""
            if entry.get("status") == "not_found":
                reason = ("not found in retained vendor transcript"
                          if str(entry.get("query", "")).casefold().startswith("transcript:")
                          else "not found in retained filings")
            gaps = "; ".join(str(g) for g in entry.get("gaps", []))
            finding = "; ".join(part for part in (reason, gaps) if part)
            lines.append(" | ".join((cell(entry.get("role") or key.split(":")[0]),
                cell(entry.get("query")), cell(entry.get("status")),
                str(len(entry.get("passages") or [])), cell(finding))))
    return "\n".join(lines)
