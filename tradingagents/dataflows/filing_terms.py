"""Shared source selection and unit context for stated filing terms."""

from __future__ import annotations

import hashlib
import re
from datetime import date

from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage, FilingDocument


def latest_primary(package: DisclosurePackage, as_of: date) -> FilingDocument | None:
    """Select one current primary report, never combine reporting periods."""
    if package.as_of != as_of:
        return None
    eligible = []
    for doc in package.documents:
        filing = doc.filing
        if (
            filing.form not in {"10-Q", "10-K"}
            or filing.cik != package.cik
            or filing.report_date is None
            or filing.report_date > as_of
            or filing.filed_date > as_of
            or filing.filed_date > package.as_of
            or doc.url != filing.url
            or f"/{filing.accession.replace('-', '')}/" not in filing.url
            or not filing.url.endswith("/" + filing.primary_document)
            or doc.source_id != "sec-document-" + hashlib.sha256(doc.url.encode()).hexdigest()
            or not re.fullmatch(r"[0-9a-f]{64}", doc.content_hash)
            or (package.selected_accessions and filing.accession not in package.selected_accessions)
        ):
            continue
        eligible.append(doc)
    if not eligible:
        return None
    latest = max((doc.filing.report_date, doc.filing.filed_date) for doc in eligible)
    matches = [doc for doc in eligible if (doc.filing.report_date, doc.filing.filed_date) == latest]
    return matches[0] if len(matches) == 1 else None


def notes_unit_context(document: FilingDocument, locator: str) -> tuple[str, str, str] | None:
    """Find explicit notes scale and USD evidence in this same primary filing."""
    blocks = document.blocks
    target = next((i for i, block in enumerate(blocks) if block.locator == locator), None)
    if target is None:
        return None
    heading = None
    for block in blocks[:target + 1]:
        if block.truncated:
            continue
        if block.text.strip().upper().startswith("NOTES TO") and len(block.text) < 120:
            heading = None
        if re.search(r"\(in thousands, except share and per share amounts\)", block.text, re.I):
            heading = block
    if heading is None:
        return None
    heading_index = blocks.index(heading)
    currency = next((block for block in blocks[heading_index:target + 1]
                     if not block.truncated and block.currency == "USD" and block.currency_locator), None)
    if currency is None:
        return None
    return "USD thousands", heading.locator, currency.locator
