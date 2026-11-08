"""Narrow, source-addressed context for historical release KPI clauses.

This does not infer context from a document's proximity or from model prose.
Only a contiguous financial-highlights section and an explicitly named
same-document definition/comparison note are supported.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
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


_OUTLOOK = re.compile(
    r"(?:[A-Za-z][A-Za-z .&-]{0,80} is providing guidance for the "
    r"(?P<quarter>(?:first|second|third|fourth) quarter ending "
    r"(?:March 31|June 30|September 30|December 31), (?P<qyear>(?:19|20)\d{2})) as follows:"
    r"|For the (?P<annual>full year (?P<ayear>(?:19|20)\d{2})), we now expect:"
    r"|[A-Za-z][A-Za-z .&-]{0,80}[’']s outlook for the (?P<fiscal>(?:first|second|third|fourth) quarter of fiscal (?P<fyear>(?:19|20)\d{2})) is as follows:)", re.I,
)


def outlook_period(text):
    match = _OUTLOOK.fullmatch(text.strip())
    return (match['quarter'] or match['annual'] or match['fiscal']) if match else None


def lower_bound_clause(text):
    """One supported complete two-period release headline, not an arbitrary cut."""
    match = re.fullmatch(
        r"Raising Q[1-4] 20\d{2} exit revenue growth outlook to " + _NUMBER
        + r"[-–]" + _NUMBER + r"% and (?P<quote>increasing expected (?P<year>20\d{2}) "
        r"(?P<metric>revenue growth) to (?P<value>" + _NUMBER + r")%\+)\.?", text, re.I)
    return match


def central_estimate_clause(text):
    """Supported revenue outlook with its explicit tolerance and market exclusion."""
    return re.fullmatch(
        r"(?P<amount>Revenue is expected to be \$(?P<value>" + _NUMBER + r") billion), "
        r"plus or minus (?P<tolerance>" + _NUMBER + r")%\. "
        r"NVIDIA is not assuming any Data Center compute revenue from China in its outlook\.", text)


def qualified_value_spans(quote, kind):
    """Only these complete release sentences support a separate numeric span.

    Remaining qualifications are retained verbatim; they are not discarded or
    reassigned to the selected value. Unknown clauses/instructions fail closed.
    """
    n = _NUMBER
    if kind == 'historical':
        match = re.fullmatch(
            r"(?P<amount>Revenue was \$" + n + r" (?:million|billion)), an (?:increase|decrease) of "
            + n + r"%\.", quote, re.I)
        if match:
            return (match['amount'],)
        match = re.fullmatch(
            r"(?P<amount>(?P<metric>Adjusted operating income|Adjusted EBITDA) was \$" + n
            + r" (?:million|billion)), an (?:increase|decrease) of " + n
            + r"%, and (?P<margin>(?P<margin_metric>adjusted operating income|adjusted EBITDA) margin was "
            + n + r"%)\.", quote, re.I)
        if match and match['metric'].casefold() == match['margin_metric'].casefold():
            return (match['amount'], match['margin'])
        match = re.fullmatch(
            r"(?P<amount>Remaining Performance Obligation (?:[('“\"]+RPO[)'”\"]+)(?:\(\d{1,2}\))? was \$"
            + n + r" (?:million|billion)), of which, \$" + n
            + r" (?:million|billion) is expected to be recognized over the next 12 months\.", quote, re.I)
        if match:
            return (match['amount'],)
    if kind == 'guidance':
        central = central_estimate_clause(quote)
        if central:
            return (central['amount'],)
        match = re.fullmatch(
            r"(?P<amount>Total revenue of \$" + n + r" to \$" + n
            + r" (?:million|billion)), up (?:approximately )?" + n
            + r"%(?: to " + n + r"%)? year-over-year\.", quote, re.I)
        if match:
            return (match['amount'],)
    return ()


def _number(block):
    match = re.fullmatch(r"block-(\d+)", block.locator)
    return int(match[1]) if match else None


def _historical_period_error(claim, packages):
    """Explicit future dates/years cannot be historical at the source date.

    Fiscal year numbers alone do not establish calendar dates. No fiscal
    calendar or completion date is invented for a partial period label.
    """
    if claim.kind != 'historical':
        return None
    period=claim.period
    explicit_dates=[]
    try:
        for value in re.findall(r'\b(?:19|20)\d{2}-\d{2}-\d{2}\b',period):
            explicit_dates.append(date.fromisoformat(value))
        for value in re.findall(r'\b[A-Z][a-z]+ \d{1,2}, (?:19|20)\d{2}\b',period):
            explicit_dates.append(datetime.strptime(value,'%B %d, %Y').date())
        years=[] if re.search(r'\bfiscal\b|\bFY\s*\d',period,re.I) else [
            int(value) for value in re.findall(r'\b(?:19|20)\d{2}\b',period)]
        for raw in packages:
            package=DisclosurePackage.model_validate(raw)
            for document in package.documents:
                if document.source_id != claim.source_id:
                    continue
                known=min(package.as_of,document.filing.filed_date)
                if any(day>known for day in explicit_dates) or any(year>known.year for year in years):
                    return 'historical period extends beyond the source-known date'
    except (ValueError,TypeError):
        return 'historical period/source date could not be validated'
    return None


def collapse_quote_packages(packages):
    """Merge repeat retrievals of one immutable document, rejecting conflicts.

    Block locators identify original source order. Bounded and full views may
    contribute different locators, but may never disagree at a shared locator.
    Issuer/cutoff checks remain at their existing validation boundaries.
    """
    parsed = tuple(DisclosurePackage.model_validate(p) for p in packages)
    if not parsed:
        return ()
    scope = {(p.cik, p.as_of) for p in parsed}
    if len(scope) != 1:
        raise ValueError("conflicting document metadata: package issuer/cutoff")
    documents, hashes, sources = {}, {}, {}
    for package in parsed:
        for doc in package.documents:
            identity = (doc.filing.cik, doc.filing.accession, doc.filing.primary_document,
                        doc.url, doc.source_id)
            if ((doc.content_hash in hashes and hashes[doc.content_hash] != identity)
                    or (doc.source_id in sources and sources[doc.source_id] != identity)):
                raise ValueError("conflicting document metadata: identity/content hash")
            hashes[doc.content_hash] = identity
            sources[doc.source_id] = identity
            previous = documents.get(identity)
            if previous and (previous.content_hash != doc.content_hash or previous.filing != doc.filing):
                raise ValueError("conflicting document metadata: filing/content hash")
            views = (previous, doc) if previous else (doc,)
            by_locator = {}
            for view in views:
                seen = set()
                for block in view.blocks:
                    if block.locator in seen:
                        raise ValueError("conflicting document metadata: duplicate block locator")
                    seen.add(block.locator)
                    if block.locator in by_locator and by_locator[block.locator] != block:
                        raise ValueError("conflicting document metadata: block text or attributes")
                    by_locator[block.locator] = block
            if all(re.fullmatch(r"block-\d+", loc) for loc in by_locator):
                blocks = tuple(sorted(by_locator.values(), key=_number))
            else:
                full = max(views, key=lambda view: len(view.blocks))
                if set(by_locator) != {b.locator for b in full.blocks}:
                    raise ValueError("conflicting document metadata: source block order unavailable")
                blocks = full.blocks
            rpo = {}
            for view in views:
                for fact in view.rpo_facts:
                    if fact.locator in rpo and rpo[fact.locator] != fact:
                        raise ValueError("conflicting document metadata: inline fact")
                    rpo[fact.locator] = fact
            documents[identity] = (previous or doc).model_copy(update={
                "blocks": blocks, "rpo_facts": tuple(rpo[k] for k in sorted(rpo)),
                "gaps": tuple(sorted({g for v in views for g in v.gaps})),
            })
    package = parsed[0].model_copy(update={
        "documents": tuple(documents[k] for k in sorted(documents)),
        "gaps": tuple(sorted({g for p in parsed for g in p.gaps})),
        "selected_accessions": tuple(sorted({a for p in parsed for a in p.selected_accessions})),
    })
    return (package,)


def validate_context(claim, blocks, packages):
    """Return (period_is_external, definition_is_external, rejection_reason)."""
    historical_error = _historical_period_error(claim, packages)
    if historical_error:
        return False, False, historical_error
    scoped = bool(claim.period_locator or claim.definition_locator or claim.comparison or claim.value_quote)
    if not scoped and (claim.comparator != "at_least" or not packages):
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
        if claim.comparator == "at_least":
            bound = lower_bound_clause(value_block.text.strip())
            if bound is None or claim.quote not in (bound['quote'], value_block.text.strip()):
                raise ValueError("lower-bound clause lacks its supported complete source headline")
        if not scoped:
            return False, False, None
        qualified = bool(claim.value_quote)
        central = central_estimate_clause(claim.quote)
        if central:
            if (claim.kind != "guidance" or claim.comparator != "central_estimate"
                    or claim.tolerance_percent != Decimal(central['tolerance'])):
                raise ValueError("central revenue estimate must retain its explicit percentage tolerance")
        elif claim.comparator == "central_estimate" or claim.tolerance_percent is not None:
            raise ValueError("uncertainty fields lack a supported complete source statement")
        if qualified and (not claim.period_locator or claim.value_quote not in qualified_value_spans(claim.quote, claim.kind)):
            raise ValueError("numeric value span lacks a supported complete qualified source sentence")
        if value_block.text.count(claim.quote) != 1:
            raise ValueError("numeric quote must occur once in the source block")
        if qualified:
            following = value_block.text.split(claim.quote, 1)[1].strip()
            prior_rpo = (claim.quote.startswith("Remaining Performance Obligation") and re.fullmatch(
                r"RPO was \$" + _NUMBER + r" (?:million|billion) in the (?:first|second|third|fourth) quarter of (?:19|20)\d{2}\.", following, re.I))
            if following and not prior_rpo:
                raise ValueError("qualified metric has unsupported following source qualifications")
        sentences = re.split(r"(?<=[.!?])\s+", value_block.text)
        sentence = claim.quote if central else next((s for s in sentences if claim.quote in s), "")
        subject = sentence.lstrip("•- ")
        if not subject.startswith(claim.quote):
            raise ValueError("numeric quote drops part of the source subject or qualifier")
        remainder = subject[len(claim.quote):]
        if not re.fullmatch(r"(?:,\s+an (?:increase|decrease) of " + _NUMBER + r"%)?\.?", remainder, re.I):
            raise ValueError("numeric quote omits unsupported source qualifications")
        heading = None
        period_external = bool(claim.period_locator)
        if period_external:
            period_block = source(claim.period_locator)
            if central and (package.cik != "0001045810" or not re.match(r"NVIDIA[’']s outlook", period_block.text)):
                raise ValueError("named central-estimate pattern must share NVIDIA issuer and outlook heading")
            if claim.kind == "guidance":
                declared = outlook_period(period_block.text)
                if declared is None or declared.casefold() != claim.period.casefold():
                    raise ValueError("period is not the exact supported outlook heading")
                year = int(re.search(r"(?:19|20)\d{2}", declared)[0])
                if not package.as_of.year <= year <= package.as_of.year + 1:
                    raise ValueError("outlook heading year is outside the bounded current/next-year scope")
            elif claim.kind == "historical":
                heading = _HEADING.fullmatch(period_block.text.strip())
                if (heading is None or heading["period"].casefold() != claim.period.casefold()
                        or int(heading["year"]) > package.as_of.year):
                    raise ValueError("period is not the exact dated financial-highlights heading")
            else:
                raise ValueError("external period scope supports historical highlights or explicit guidance")
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
            if not sentence or _DATE_OR_PRIOR.search(prefix) or (not qualified and _DATE_OR_PRIOR.search(sentence)):
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
            numeric_quote = claim.value_quote or claim.quote
            suffix = value_block.text[value_block.text.index(numeric_quote) + len(numeric_quote):]
            match = re.match(r",\s+an (?:increase|decrease) of (" + _NUMBER + r")%", suffix, re.I)
            if (
                match is None or comparison.quote != match[0]
                or Decimal(match[1].replace(",", "")) != comparison.value
                or comparison.unit != "%"
                or (not qualified and not re.fullmatch(r"[.!?]?", suffix[len(match[0]):], re.S))
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
    except ValueError as exc:
        return False, False, "source-linked disclosure context: " + str(exc)[:240]
    except (TypeError, AttributeError, KeyError):
        return False, False, "malformed source-linked disclosure context"
