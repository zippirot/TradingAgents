"""Deterministic, offline lookup over a retained full-source SEC corpus."""

from __future__ import annotations

import hashlib
import json
import re

from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

MAX_PASSAGES = 3
MAX_CHARS = 12_000
MAX_QUERY_CHARS = 200
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"a", "an", "and", "for", "in", "of", "the", "to", "what", "which"}
_ALIASES = {
    "rpo": "remaining performance obligations",
    "backlog": "remaining performance obligations",
}


def corpus_hash(corpus: DisclosurePackage) -> str:
    """Hash the exact retained package, including source hashes and block text."""
    data = json.dumps(corpus.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def _terms(query: str) -> tuple[str, list[str]]:
    normalized = " ".join(_WORD.findall(query.lower()))
    for short, expanded in _ALIASES.items():
        normalized = re.sub(r"\b" + short + r"\b", expanded, normalized)
    words = [word for word in normalized.split() if word not in _STOP]
    return normalized, words


def _contains(text: str, term: str) -> bool:
    suffix = "s?" if len(term) >= 4 and not term.endswith("s") else ""
    return re.search(r"\b" + re.escape(term) + suffix + r"\b", text) is not None


def search_filing_evidence(
    corpus: DisclosurePackage, query: str, *, max_passages: int = MAX_PASSAGES,
    max_chars: int = MAX_CHARS,
) -> dict:
    """Return whole source blocks, never a shortened table or a new network fetch.

    Callers retain this response alongside the corpus. Returned text is unvalidated
    source material; claims still require the disclosure evidence validator.
    """
    if not 1 <= max_passages <= MAX_PASSAGES or not 1 <= max_chars <= MAX_CHARS:
        raise ValueError(f"Search limit exceeded: at most {MAX_PASSAGES} passages and {MAX_CHARS} characters")
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"Search query must contain 1-{MAX_QUERY_CHARS} characters")
    phrase, terms = _terms(query)
    if not terms:
        raise ValueError("Search query has no searchable terms")
    section_window = {}
    if len(terms) <= 2:
        ordered = sorted(
            corpus.documents,
            key=lambda doc: (doc.filing.filed_date, doc.filing.accession), reverse=True,
        )
        for document in ordered:
            filing = document.filing
            if filing.cik != corpus.cik or filing.filed_date > corpus.as_of or (
                filing.report_date and filing.report_date > corpus.as_of
            ):
                continue
            for index, block in enumerate(document.blocks):
                heading = block.text.strip()
                if (
                    len(heading) > 120 or "|" in heading
                    or not (re.match(r"^(?:Note|Item) \d+[. ]", heading) or heading.istitle())
                    or not all(_contains(heading.lower(), term) for term in terms)
                ):
                    continue
                for offset, nearby in enumerate(document.blocks[index:index + max_passages]):
                    if offset and (
                        re.match(r"^(?:Note|Item) \d+[. ]", nearby.text)
                        or nearby.text.istitle()
                    ):
                        break
                    section_window[(document.source_id, nearby.locator)] = 100 - offset * 10
                break
            if section_window:
                break
    candidates = []
    gaps = list(corpus.gaps)
    for document in corpus.documents:
        filing = document.filing
        if filing.cik != corpus.cik or filing.filed_date > corpus.as_of or (
            filing.report_date is not None and filing.report_date > corpus.as_of
        ):
            gaps.append(f"{filing.accession}: excluded by issuer or analysis cutoff")
            continue
        if document.source_id != "sec-document-" + hashlib.sha256(document.url.encode()).hexdigest():
            gaps.append(f"{filing.accession}: source identity mismatch")
            continue
        for block in document.blocks:
            if block.truncated:
                gaps.append(f"{filing.accession} {block.locator}: incomplete source block omitted")
                continue
            heading = block.section.lower()
            body = block.text.lower()
            heading_hits = sum(_contains(heading, term) for term in terms)
            body_hits = sum(_contains(body, term) for term in terms)
            if not heading_hits and not body_hits and (document.source_id, block.locator) not in section_window:
                continue
            score = (
                section_window.get((document.source_id, block.locator), 0)
                + 8 * (phrase in heading) + 10 * (phrase in body)
                + 2 * heading_hits + body_hits + 4 * (body_hits == len(terms))
            )
            candidates.append((score, document, block))
    candidates.sort(key=lambda item: (
        -item[0], -item[1].filing.filed_date.toordinal(),
        item[1].filing.accession, item[2].locator,
    ))
    passages = []
    used = 0
    for _, document, block in candidates:
        if len(passages) >= max_passages:
            break
        if len(block.text) > max_chars - used:
            gaps.append(
                f"{document.filing.accession} {block.locator}: passage omitted by search size limit"
            )
            continue
        filing = document.filing
        passages.append({
            "source_id": document.source_id,
            "locator": block.locator,
            "section": block.section,
            "text": block.text,
            "truncated": False,
            "currency": block.currency,
            "currency_locator": block.currency_locator,
            "filing_form": filing.form,
            "filing_date": filing.filed_date.isoformat(),
            "filing_accession": filing.accession,
            "url": document.url,
            "content_hash": document.content_hash,
            "passage_hash": hashlib.sha256(block.text.encode()).hexdigest(),
        })
        used += len(block.text)
    if not passages:
        gaps.append("not found in retained filings")
    return {
        "query": query,
        "corpus_hash": corpus_hash(corpus),
        "passages": passages,
        "gaps": list(dict.fromkeys(gaps)),
    }
