"""Narrow, source-addressed context for historical release KPI clauses.

This does not infer context from a document's proximity or from model prose.
Only a contiguous financial-highlights section and an explicitly named
same-document definition/comparison note are supported.
"""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from urllib.parse import urlsplit

from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

_HEADING = re.compile(
    r"(?P<period>(?:First|Second|Third|Fourth) Quarter (?P<year>(?:19|20)\d{2}))"
    r" Financial Highlights(?:\((?P<note>\d{1,2})\))?:?", re.I,
)
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_DATE_OR_PRIOR = re.compile(
    r"\b(?:19|20)\d{2}\b|\bQ[1-4]\b|\b(?:first|second|third|fourth) quarter\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b"
    r"|\b(?:prior|previous|earlier|last|hypothetical|scenario|if|expect|expects|expected|forecast|guidance|target|will|would|could)\b", re.I,
)


def _number(block):
    match = re.fullmatch(r"block-(\d+)", block.locator)
    return int(match[1]) if match else None


def validate_context(claim, blocks, packages):
    """Return (period_is_external, definition_is_external, rejection_reason)."""
    if not (claim.period_locator or claim.definition_locator or claim.comparison):
        return False, False, None
    try:
        if claim.definition is not None and claim.definition_locator is None:
            raise ValueError("context-backed definition requires its explicit source locator")
        matches = []
        for raw in packages:
            package = DisclosurePackage.model_validate(raw)
            for doc in package.documents:
                if doc.source_id != claim.source_id:
                    continue
                if doc.filing.cik != package.cik or doc.filing.filed_date > package.as_of:
                    raise ValueError("context document issuer or filing cutoff mismatch")
                base = f"/Archives/edgar/data/{int(package.cik)}/{doc.filing.accession.replace('-', '')}/"
                for url in (doc.filing.url, doc.url):
                    parsed = urlsplit(url)
                    name = parsed.path.removeprefix(base)
                    if (
                        parsed.scheme != "https" or parsed.netloc != "www.sec.gov"
                        or parsed.query or parsed.fragment or not parsed.path.startswith(base)
                        or not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
                    ):
                        raise ValueError("context URL does not identify the filed issuer/accession")
                if doc.source_id != "sec-document-" + hashlib.sha256(doc.url.encode()).hexdigest():
                    raise ValueError("context source identity does not match its URL")
                matches.append((package, doc))
        if len(matches) != 1:
            raise ValueError("context needs one unique source document")
        package, doc = matches[0]
        locators = [b.locator for b in doc.blocks]
        if len(set(locators)) != len(locators):
            raise ValueError("context source has duplicate block locators")
        by_locator = {b.locator: b for b in doc.blocks}

        def source(locator):
            block = by_locator.get(locator)
            if block is None or block.truncated:
                raise ValueError("context source block missing or truncated")
            if blocks.get((doc.source_id, locator)) != block.section + "\n" + block.text:
                raise ValueError("context block differs from canonical document")
            return block

        value_block = source(claim.locator)
        if value_block.text.count(claim.quote) != 1:
            raise ValueError("numeric quote must occur once in the source block")
        sentences = re.split(r"(?<=[.!?])\s+", value_block.text)
        sentence = next((s for s in sentences if claim.quote in s), "")
        subject = sentence.lstrip("•- ")
        if not subject.startswith(claim.quote):
            raise ValueError("numeric quote drops part of the source subject or qualifier")
        remainder = subject[len(claim.quote):]
        if not re.fullmatch(r"(?:,\s+an (?:increase|decrease) of " + _NUMBER + r"%)?\.?", remainder, re.I):
            raise ValueError("numeric quote omits unsupported source qualifications")
        heading = None
        period_external = bool(claim.period_locator)
        if period_external:
            if claim.kind != "historical":
                raise ValueError("external highlights period supports historical KPIs only")
            period_block = source(claim.period_locator)
            heading = _HEADING.fullmatch(period_block.text.strip())
            if (
                heading is None
                or heading["period"].casefold() != claim.period.casefold()
                or int(heading["year"]) > package.as_of.year
            ):
                raise ValueError("period is not the exact dated financial-highlights heading")
            start, end = locators.index(period_block.locator), locators.index(value_block.locator)
            if not 0 < end - start <= 32:
                raise ValueError("period heading does not precede a bounded claim section")
            span = doc.blocks[start:end + 1]
            numbers = [_number(b) for b in span]
            if any(n is None for n in numbers) or numbers != list(range(numbers[0], numbers[0] + len(span))):
                raise ValueError("missing or reordered source blocks in period scope")
            for block in span[1:-1]:
                source(block.locator)
                if not block.text.lstrip().startswith(("•", "- ")):
                    raise ValueError("intervening heading or prose breaks period scope")
            prefix = value_block.text[:value_block.text.index(claim.quote)]
            if not sentence or _DATE_OR_PRIOR.search(prefix + sentence):
                raise ValueError("claim clause has its own or contradictory temporal qualifier")
            # A separate prose disclaimer/forecast cannot silently govern the
            # selected sentence. Only preceding simple reported-value sentences
            # in this same highlight bullet are supported.
            # Match the subject check's list-marker handling: a bare leading
            # bullet is layout, not a preceding prose sentence. Keep all actual
            # words so qualifiers and unsupported preceding claims still fail.
            prose_prefix = prefix.lstrip("•- ").strip()
            preceding = re.split(r"(?<=[.!?])\s+", prose_prefix) if prose_prefix else []
            reported = (
                r"[^\d.!?:;]{1,160}\s+(?:was|were|ended the quarter at)\s+\$?"
                + _NUMBER + r"\s+(?:million|billion|thousand)"
                + r"(?:,\s+an (?:increase|decrease) of " + _NUMBER + r"%)?\."
            )
            if any(not re.fullmatch(reported, text.lstrip("•- "), re.I) for text in preceding):
                raise ValueError("unsupported preceding prose in the scoped highlight")

        definition_external = bool(claim.definition_locator)
        if definition_external:
            definition_block = source(claim.definition_locator)
            i = locators.index(definition_block.locator)
            if i == 0:
                raise ValueError("definition lacks its metric heading")
            title = source(locators[i - 1])
            if (
                title.text.strip().casefold() != claim.metric.casefold()
                or sum(b.text.strip().casefold() == claim.metric.casefold() for b in doc.blocks) != 1
                or _number(title) is None
                or _number(definition_block) != _number(title) + 1
                or claim.definition != definition_block.text
            ):
                raise ValueError("definition is not complete under a unique matching metric heading")
            metric = re.escape(claim.metric) + r"(?!\w)"
            if not re.match(
                r"(?:We calculate\s+" + metric + r"\s+by\b|" + metric + r"\s+(?:represents|means|is defined))",
                definition_block.text, re.I,
            ):
                raise ValueError("definition does not explicitly define the claimed metric")

        if claim.comparison:
            comparison = claim.comparison
            if heading is None or heading["note"] is None:
                raise ValueError("comparison basis requires a referenced highlights heading")
            suffix = value_block.text[value_block.text.index(claim.quote) + len(claim.quote):]
            match = re.match(r",\s+an (?:increase|decrease) of (" + _NUMBER + r")%", suffix, re.I)
            if (
                match is None or comparison.quote != match[0]
                or Decimal(match[1].replace(",", "")) != comparison.value
                or comparison.unit != "%"
                or not re.fullmatch(r"[.!?]?", suffix[len(match[0]):], re.S)
            ):
                raise ValueError("comparison is not the exact adjacent reported percentage")
            note = source(comparison.basis_locator)
            if not 0 < locators.index(note.locator) - locators.index(value_block.locator) <= 64:
                raise ValueError("comparison note is outside the bounded following source context")
            expected = (
                r"\(" + re.escape(heading["note"]) + r"\)\s*All growth rates are "
                r"year-over-year unless otherwise specified\."
            )
            if not re.fullmatch(expected, note.text, re.I):
                raise ValueError("comparison basis is not the referenced year-over-year note")
            note_span = doc.blocks[locators.index(period_block.locator):locators.index(note.locator) + 1]
            numbers = [_number(b) for b in note_span]
            if any(n is None for n in numbers) or numbers != list(range(numbers[0], numbers[0] + len(note_span))):
                raise ValueError("missing or reordered source blocks before comparison note")
            for block in note_span:
                source(block.locator)
            between = note_span[1:-1]
            if any(
                _HEADING.fullmatch(b.text.strip())
                or re.match(r"\(" + re.escape(heading["note"]) + r"\)", b.text.lstrip())
                for b in between
            ):
                raise ValueError("another highlights section or same-number note intervenes")
        return period_external, definition_external, None
    except (ValueError, TypeError, AttributeError, KeyError):
        return False, False, "missing, ambiguous or contradictory source-linked disclosure context"
