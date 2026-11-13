"""Bounded SEC filing discovery and section-addressable source text.

Everything in source blocks is untrusted document data, never instructions.
This adapter establishes retrieval coverage, not accounting or KPI completeness.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from pydantic import BaseModel, ConfigDict

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.vendors.sec_edgar import _user_agent, cik_for

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:htm|html|xml)$", re.I)
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}$")
_RATE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


class FilingReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cik: str
    accession: str
    form: str
    filed_date: date
    report_date: date | None
    primary_document: str
    items: str
    url: str


class SourceBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    locator: str
    section: str
    text: str
    truncated: bool = False
    currency: str | None = None
    currency_locator: str | None = None


class RemainingPerformanceObligationFact(BaseModel):
    """One exact consolidated instant RPO inline fact, not arbitrary XBRL."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    metric: str = "Revenue Remaining Performance Obligation"
    locator: str
    value: Decimal
    currency: str
    period_end: date
    recognition_start: date | None = None
    display_value: str
    scale: int
    decimals: int | None
    context_id: str
    unit_id: str
    character_start: int
    character_end: int
    exact_html: str
    context_html: str
    unit_html: str


class FilingDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    filing: FilingReference
    url: str
    retrieved_at: datetime
    content_hash: str
    blocks: tuple[SourceBlock, ...]
    gaps: tuple[str, ...] = ()
    rpo_facts: tuple[RemainingPerformanceObligationFact, ...] = ()


class DisclosurePackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = 1
    cik: str
    as_of: date
    documents: tuple[FilingDocument, ...] = ()
    gaps: tuple[str, ...] = ()
    scope: str = (
        "Selected SEC annual/quarterly filings and subsequent earnings/financing disclosures"
    )
    # These are retrieval facts only. No 'complete' label is inferred from prose.
    selected_accessions: tuple[str, ...] = ()


_OLDER_ARCHIVE_LIMIT = 3


def with_older_annual(client, data: dict, as_of: str) -> dict:
    """The submissions metadata with older archive files added when the recent list holds no annual report.

    SEC keeps only the latest filings in the recent list; a filer with hundreds of other forms a year can
    have its 10-K only in an older file. At most three older files are read, in the order SEC lists them,
    and reading stops at the first that holds a 10-K filed by the analysis date. Malformed data is returned
    as it came, for the caller's own validation to refuse.
    """
    try:
        recent, files = data["filings"]["recent"], data["filings"].get("files") or ()

        def has_annual(columns):
            return any(form == "10-K" and str(filed) <= as_of
                       for form, filed in zip(columns["form"], columns["filingDate"], strict=True))

        if not files or has_annual(recent):
            return data
        merged = {name: list(values) for name, values in recent.items() if isinstance(values, (list, tuple))}
        for entry in list(files)[:_OLDER_ARCHIVE_LIMIT]:
            name = str(entry.get("name", ""))
            if not re.fullmatch(r"[A-Za-z0-9._-]+\.json", name):
                break
            older = json.loads(client.fetch(f"https://data.sec.gov/submissions/{name}")["text"])
            if any(not isinstance(older.get(column), list) or len(older[column]) != len(older["form"]) for column in merged):
                break
            for column in merged:
                merged[column].extend(older[column])
            if has_annual(older):
                break
        return {**data, "filings": {**data["filings"], "recent": merged}}
    except (KeyError, TypeError, ValueError):
        return data


def _filing_rows(data: dict, cik: str, as_of: str, *, include_prospectus=False):
    """Validate recent submissions once for both bounded selection paths."""
    cutoff = date.fromisoformat(as_of)
    if not isinstance(data, dict) or str(data.get("cik", "")).zfill(10) != cik:
        raise VendorUnavailableError("SEC submissions issuer mismatch")
    try:
        recent = data["filings"]["recent"]
        names = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument")
        if any(not isinstance(recent[n], (list, tuple)) for n in names):
            raise ValueError()
        count = len(recent["form"])
        if any(len(recent[n]) != count for n in names):
            raise ValueError()
        items = recent.get("items", [""] * count)
        if not isinstance(items, (list, tuple)) or len(items) != count:
            raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise VendorUnavailableError("Malformed SEC submissions metadata") from exc
    rows, gaps = [], []
    if data["filings"].get("files"):
        gaps.append(
            "Older submissions archive not retrieved; coverage is limited to recent metadata"
        )
    for i in range(count):
        form = recent["form"][i]
        if form not in {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A"} and not (include_prospectus and re.fullmatch(r"424B[1-9]?", str(form))):
            continue
        try:
            filed = date.fromisoformat(recent["filingDate"][i])
            report = (
                date.fromisoformat(recent["reportDate"][i]) if recent["reportDate"][i] else None
            )
        except (TypeError, ValueError):
            gaps.append("Malformed filing date in submissions metadata")
            continue
        if filed > cutoff:
            continue
        if report and report > cutoff:
            gaps.append("Filing report period exceeds analysis cutoff")
            continue
        name, accession = recent["primaryDocument"][i], recent["accessionNumber"][i]
        if (
            not isinstance(name, str)
            or not _NAME.fullmatch(name)
            or not isinstance(accession, str)
            or not _ACCESSION.fullmatch(accession)
        ):
            gaps.append(f"Filing {accession}: unsupported primary document or accession")
            continue
        rows.append(
            FilingReference(
                cik=cik,
                accession=accession,
                form=form,
                filed_date=filed,
                report_date=report,
                primary_document=name,
                items=str(items[i]),
                url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{name}",
            )
        )
    return rows, gaps


# Current-report items that can bear on the accounting evidence: earnings, financing, agreements, other
# events, and Item 4.02 (non-reliance on previously issued financial statements).
_EVENT_ITEMS = ("2.02", "2.03", "1.01", "3.02", "8.01", "4.02")


def unselected_events(data: dict, cik: str, as_of: str, selected) -> list[str]:
    """Every current report since the latest quarter that was not selected, by accession, items and reason."""
    rows, _ = _filing_rows(data, cik, as_of)
    quarterly = [r.report_date for r in selected if r.form == "10-Q" and r.report_date]
    baseline = max(quarterly, default=max((r.report_date for r in selected if r.report_date), default=None))
    chosen = {r.accession for r in selected}
    out = []
    for row in sorted(rows, key=lambda r: (r.filed_date, r.accession)):
        if not row.form.startswith("8-K") or row.accession in chosen or (baseline and row.filed_date < baseline):
            continue
        reason = ("item codes outside earnings, financing, agreements, other events and non-reliance"
                  if row.items and not any(item in row.items for item in _EVENT_ITEMS) else "filing count limit")
        out.append(f"{row.accession} {row.form} items {row.items or 'none stated'} filed {row.filed_date}: "
                   f"not selected; {reason}")
    return out


def select_filings(data: dict, cik: str, as_of: str, limit: int = 6):
    """Select annual/quarterly baselines and subsequent relevant 8-Ks."""
    cutoff = date.fromisoformat(as_of)
    rows, gaps = _filing_rows(data, cik, as_of)
    selected = []
    # Keep originals alongside amendments; an amendment is not a full replacement.
    for form in ("10-K", "10-Q"):
        originals = [r for r in rows if r.form == form]
        if originals:
            latest = max(originals, key=lambda r: (r.report_date or date.min, r.filed_date))
            selected.append(latest)
            selected.extend(
                r
                for r in rows
                if r.form == form + "/A"
                and r.report_date == latest.report_date
                and r.filed_date >= latest.filed_date
            )
        else:
            gaps.append(f"No eligible {form} primary filing in recent metadata")
    quarterly = [r.report_date for r in selected if r.form == "10-Q" and r.report_date]
    baseline = max(
        quarterly, default=max((r.report_date for r in selected if r.report_date), default=cutoff)
    )
    events = [
        r
        for r in rows
        if r.form.startswith("8-K")
        and r.filed_date >= baseline
        and (
            not r.items or any(item in r.items for item in _EVENT_ITEMS)
        )
    ]
    selected.extend(events)
    selected = sorted(
        {r.accession: r for r in selected}.values(), key=lambda r: (r.filed_date, r.accession)
    )
    if len(selected) > limit:
        gaps.append(f"Filing count limit {limit} reached; selected coverage is incomplete")
        # Preserve statements and the latest earnings/financing disclosures
        # before generic events. Otherwise frequent 8.01 notices can crowd out
        # the only earnings release even though it is within the selected period.
        statements = [r for r in selected if not r.form.startswith("8-K")]
        events = [r for r in selected if r.form.startswith("8-K")]
        reserved = {}
        # A notice withdrawing reliance on issued statements is never crowded out: every one is kept.
        reserved["non-reliance"] = [r for r in events if "4.02" in r.items]
        if not reserved["non-reliance"]:
            del reserved["non-reliance"]
        for category, item_codes in (
            ("earnings", ("2.02",)),
            ("financing", ("2.03", "1.01", "3.02")),
        ):
            relevant = [r for r in events if any(code in r.items for code in item_codes)]
            originals = [r for r in relevant if r.form == "8-K"]
            if originals:
                latest = max(originals, key=lambda r: (r.filed_date, r.accession))
                reserved[category] = [latest] + [
                    r
                    for r in relevant
                    if r.form == "8-K/A"
                    and r.report_date == latest.report_date
                    and r.filed_date >= latest.filed_date
                ]
            elif relevant:
                reserved[category] = [max(relevant, key=lambda r: (r.filed_date, r.accession))]
                gaps.append(f"{category} amendment has no eligible original filing")
        priority = statements + [r for group in reserved.values() for r in group]
        priority += list(reversed(events))
        selected = list({r.accession: r for r in priority}.values())[:limit]
        retained = {r.accession for r in selected}
        for category, required in reserved.items():
            if any(r.accession not in retained for r in required):
                gaps.append(
                    f"Required {category} disclosure or amendment omitted by filing count limit"
                )
        selected.sort(key=lambda r: (r.filed_date, r.accession))
    return selected, gaps


class _Sections(HTMLParser):
    def __init__(self, unit_currencies=None):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.section = "Document"
        self.parts = []
        self.blocks = []
        self.links = []
        self.href = None
        self.link_text = []
        self.heading = False
        self.table_depth = 0
        self.row_cells = 0
        self.unit_currencies = unit_currencies or {}
        self.table_currencies = set()
        self.table_currency_refs = set()
        self.table_section = None
        self.notes_heading = None
        self.notes_scale = None
        self.note_title = None
        self.last_table_locator = None
        self.last_table_statement_context = None
        self.table_statement_context = None

    def _table_context(self):
        prior = self.blocks
        statement = []
        if prior and prior[-1].locator == self.last_table_locator:
            # Consecutive statement tables can share a single immediately
            # preceding heading/scale; no prose may intervene.
            statement = self.last_table_statement_context or []
        else:
            end = len(prior)
            if end and re.fullmatch(r"\(?unaudited\)?", prior[end - 1].text, re.I):
                end -= 1
            if end >= 2:
                scale = prior[end - 1].text
                heading_index = end - 2
                if re.fullmatch(r"\(?unaudited\)?", prior[heading_index].text, re.I):
                    heading_index -= 1
                if heading_index >= 0:
                    heading = prior[heading_index].text
                    earlier = prior[heading_index - 1].text if heading_index else ""
                    if (
                        re.search(r"\bSTATEMENTS? OF\b", heading, re.I)
                        and not re.search(r"\b(?:19|20)\d{2}\b", heading + " " + scale)
                        and not re.search(r"\bSTATEMENTS? OF\b", earlier, re.I)
                        and re.match(r"^\(?(?:in|Dollars in) (?:thousands|millions|billions)\b", scale, re.I)
                    ):
                        statement = [heading, scale]
        self.table_statement_context = statement if not self.notes_heading else None
        if self.notes_heading and self.notes_scale:
            context = [self.notes_heading, self.notes_scale]
            if self.note_title:
                context.append(self.note_title)
        else:
            context = statement
        if prior and prior[-1].text.endswith("as follows:"):
            context.append(prior[-1].text)
        return " ; ".join(dict.fromkeys(filter(None, [self.section, *context])))[:600]

    def flush(self, table=False):
        text = " ".join("".join(self.parts).split())
        self.parts = []
        if text:
            currency = (
                next(iter(self.table_currencies))
                if table and len(self.table_currencies) == 1
                else None
            )
            self.blocks.append(
                SourceBlock(
                    locator=f"block-{len(self.blocks) + 1}",
                    section=self.table_section if table and self.table_section else self.section,
                    text=text,
                    truncated=bool(self.table_depth),
                    currency=currency,
                    currency_locator=(
                        next(
                            (
                                f"inline XBRL unitRef {ref} -> iso4217:{currency}"
                                for ref in sorted(self.table_currency_refs)
                                if self.unit_currencies.get(ref) == currency
                            ),
                            None,
                        )
                        if currency
                        else None
                    ),
                )
            )
            if table:
                self.last_table_locator = self.blocks[-1].locator
                self.last_table_statement_context = self.table_statement_context
            if self.heading:
                self.section = text[:200]
            if not table:
                if re.match(r"^NOTES TO .*FINANCIAL STATEMENTS$", text, re.I):
                    self.notes_heading, self.notes_scale, self.note_title = text, None, None
                elif (
                    self.notes_heading
                    and not self.notes_scale
                    and re.match(r"^\(in (?:thousands|millions|billions)\b", text, re.I)
                ):
                    self.notes_scale = text
                elif self.notes_heading and re.match(r"^Note \d+\.", text, re.I):
                    self.note_title = text[:200]
                elif re.match(r"^(?:Item \d+\.|PART [IVX]+\b)", text, re.I):
                    self.notes_heading = self.notes_scale = self.note_title = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.hidden:
            if tag not in {
                "area",
                "base",
                "br",
                "embed",
                "hr",
                "img",
                "input",
                "link",
                "meta",
                "source",
                "wbr",
            }:
                self.hidden += 1
            return
        style = re.sub(r"\s+", "", attrs.get("style", "")).lower()
        if (
            tag in ("script", "style", "ix:hidden", "ix:header", "head")
            or "display:none" in style
            or "visibility:hidden" in style
            or "hidden" in attrs
        ):
            self.hidden = 1
            return
        if tag == "table":
            if not self.table_depth:
                self.flush()
                self.heading = False
                self.table_section = self._table_context()
                self.table_currencies = set()
                self.table_currency_refs = set()
            self.table_depth += 1
        if self.table_depth:
            if tag == "tr":
                if self.parts:
                    self.parts.append(" ; ")
                self.row_cells = 0
            elif tag in ("td", "th"):
                if self.row_cells:
                    self.parts.append(" | ")
                self.row_cells += 1
            elif tag in ("p", "div"):
                self.parts.append(" ")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "tr", "div"):
            self.flush()
            self.heading = tag.startswith("h") and len(tag) == 2
        if tag == "br":
            self.parts.append(" ")
        if tag == "ix:nonfraction" and self.table_depth:
            currency = self.unit_currencies.get(attrs.get("unitref"))
            if currency:
                self.table_currencies.add(currency)
                self.table_currency_refs.add(attrs["unitref"])
        if tag == "a":
            self.href = attrs.get("href")
            self.link_text = []

    def handle_startendtag(self, tag, attrs):
        # HTMLParser emits an end event for <meta/> and <link/>. Hidden
        # containers must not close when those void children end.
        if self.hidden and tag in {
            "area",
            "base",
            "br",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "source",
            "wbr",
        }:
            return
        super().handle_startendtag(tag, attrs)

    def handle_endtag(self, tag):
        if self.hidden:
            self.hidden -= 1
            return
        if tag == "a" and self.href is not None:
            self.links.append((self.href, "".join(self.link_text).strip()))
            self.href = None
        if tag == "table" and self.table_depth:
            self.table_depth -= 1
            if not self.table_depth:
                self.flush(table=True)
                self.table_section = None
                self.table_currencies = set()
                self.table_currency_refs = set()
        elif self.table_depth:
            if tag in ("p", "div"):
                self.parts.append(" ")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "tr", "div"):
            self.flush()
            self.heading = False

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.href is not None:
                self.link_text.append(data)


def extract_sections(
    text: str, max_chars: int = 60000, *, prioritize_rpo: bool = False,
    prioritize_guidance: bool = False,
):
    unit_currencies = {
        ref: code.upper()
        for ref, code in re.findall(
            r"<xbrli:unit\b[^>]*\bid=[\"\']([^\"\']+)[\"\'][^>]*>\s*<xbrli:measure>\s*iso4217:([A-Za-z]{3})\s*</xbrli:measure>",
            text,
            re.I,
        )
    }
    parser = _Sections(unit_currencies)
    gaps = []
    try:
        parser.feed(text)
        parser.close()
        parser.flush()
    except (ValueError, AssertionError):
        gaps.append("Malformed HTML; section extraction incomplete")
    if parser.hidden:
        gaps.append("Unclosed hidden HTML section; extraction incomplete")
    if parser.table_depth:
        gaps.append("Unclosed HTML table; column context may be incomplete")
    blocks, used = [], 0
    candidates = [[(index, block)] for index, block in enumerate(parser.blocks)]
    guidance_starts = set()
    bounded = sum(len(block.text) for block in parser.blocks) > max_chars
    if bounded:
        gaps.append("Document text limit reached; selected sections omit other content")
        guidance_runs = []
        # A styled paragraph can be a heading even when its HTML tag is not
        # h1-h6. Preserve guidance blocks through the next unrelated heading.
        def heading(block):
            label = block.text.strip()
            title = label.removesuffix(":")
            return (len(label) <= 80 and not label.startswith(("•", "-", "–"))
                    and (title.istitle() or title.isupper()))

        position = 0
        while position < len(parser.blocks):
            label = parser.blocks[position].text.strip()
            if (heading(parser.blocks[position])
                    and re.search(r"\b(?:outlook|guidance)\b", label, re.I)):
                end = position + 1
                while end < len(parser.blocks):
                    next_label = parser.blocks[end].text.strip()
                    if (heading(parser.blocks[end])
                            and not re.search(r"\b(?:outlook|guidance)\b", next_label, re.I)):
                        break
                    end += 1
                guidance_runs.append((position, end, label.removesuffix(":")))
                guidance_starts.add(position)
                position = end
            else:
                position += 1
        by_start = {start: end for start, end, _ in guidance_runs}
        candidates = []
        position = 0
        while position < len(parser.blocks):
            end = by_start.get(position, position + 1)
            candidates.append([(index, parser.blocks[index]) for index in range(position, end)])
            position = end
        financial = re.compile(
            r"equity|lease|financ|commitment|guidance|outlook|revenue|net retention|"
            r"remaining performance|earnings|reconciliation|cash flow|capital|debt|"
            r"shares|stock|AI customer|AI product|borrow|loan|credit|convertible|"
            r"drawdown|acquisit|equipment",
            re.I,
        )

        # Prefer relevant notes even when they occur after cover pages and risk
        # boilerplate. Stable locators still refer to original document order.
        financing_scope = re.compile(
            r"net carrying amount.{0,100}debt|credit agreement|term loan facility|"
            r"revolving facility|drawn? down|drawdowns|"
            r"net cash (?:used in investing|provided by financing) activities",
            re.I,
        )

        def block_priority(pair):
            _, block = pair
            hits = len(financial.findall(block.text))
            table = "|" in block.text
            statement_table = table and re.search(r"\bSTATEMENTS? OF\b", block.section, re.I)
            obligation_table = table and re.search(
                r"\bNote \d+\.\s*(?:Debt|Finance Leases?|Equipment Financing)\b",
                block.section,
                re.I,
            )
            numerical_guidance = (
                re.search(r"\b(?:guidance|outlook|forecast|expect|expects|expected)\b", block.text, re.I)
                and re.search(r"\d", block.text)
            )
            # Source statements and obligation tables establish the numbers;
            # adjacent financing/acquisition prose establishes their scope.
            tier = (
                4
                if prioritize_rpo and re.search(r"remaining performance obligations", block.text, re.I)
                and re.search(r"aggregate transaction price|recognize.*revenue", block.text, re.I)
                else 4
                if prioritize_guidance and numerical_guidance
                else 3
                if statement_table or obligation_table
                else 2
                if financing_scope.search(block.text)
                else 1
                if hits or numerical_guidance
                else 0
            )
            return (
                tier,
                bool(numerical_guidance),
                hits + bool(re.search(r"\d", block.text)) * bool(hits),
                bool(financial.search(block.section)),
            )

        def priority(unit):
            return max(block_priority(pair) for pair in unit)

        candidates.sort(key=priority, reverse=True)
    selected = []
    for unit in candidates:
        remaining = max_chars - used
        if remaining <= 0:
            break
        length = sum(len(block.text) for _, block in unit)
        if length > remaining and (len(unit) > 1 or unit[0][0] in guidance_starts):
            continue
        index, block = unit[0]
        if length > remaining:
            # Prefer whole shorter blocks; use a partial block only when there
            # is no smaller remaining block to preserve.
            if any(
                len(other[0][1].text) <= remaining
                for other in candidates
                if len(other) == 1 and other[0][0] not in {i for i, _ in selected}
                and other[0][0] != index
            ):
                continue
            selected.append(
                (
                    index,
                    block.model_copy(update={"text": block.text[:remaining], "truncated": True}),
                )
            )
            gaps.append("Document text limit reached; section truncated")
            break
        selected.extend(unit)
        used += length
    if bounded:
        retained = {index for index, _ in selected}
        for start, end, label in guidance_runs:
            if not all(index in retained for index in range(start, end)):
                gaps.append(f"Document text limit reached; {label} guidance run omitted")
    blocks = [block for _, block in sorted(selected)]
    if not blocks:
        gaps.append("Document contains no usable visible sections")
    return blocks, parser.links, gaps


def exhibit_url(filing: FilingReference, href: str) -> str | None:
    if not isinstance(href, str):
        return None
    parsed = urlsplit(href)
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        return None
    candidate = urljoin(filing.url, href)
    base = filing.url.rsplit("/", 1)[0] + "/"
    if not candidate.startswith(base) or not _NAME.fullmatch(candidate[len(base) :]):
        return None
    return candidate


_DOCUMENT_TRANSPORT_MAX_BYTES = 16_000_000


class DocumentClient:
    """Finite per-run HTTP acquisition with immutable-content cache metadata."""

    def __init__(self, max_bytes=2_500_000, max_requests=10, max_seconds=90):
        self.max_bytes = max_bytes
        self.max_requests = max_requests
        self.deadline = time.monotonic() + max_seconds
        self.requests = 0

    def fetch(self, url: str):
        global _LAST_REQUEST
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc not in {"www.sec.gov", "data.sec.gov"}
            or parsed.query
            or parsed.fragment
        ):
            raise VendorUnavailableError("Unsupported SEC document URL")
        from tradingagents.source_replay import external_input

        value = external_input("sec_document", {"url": url}, lambda: self._fetch(url))
        raw = value["text"].encode()
        if (value["url"] != url or len(raw) > self.max_bytes
                or hashlib.sha256(raw).hexdigest() != value["content_hash"]):
            raise VendorUnavailableError("Recorded SEC document identity/hash/size mismatch")
        return value

    def _fetch(self, url: str):
        global _LAST_REQUEST

        key = hashlib.sha256(url.encode()).hexdigest()
        path = Path(get_config()["data_cache_dir"]) / "sec_documents" / (key + ".json")
        if (
            path.exists()
            and path.stat().st_size <= self.max_bytes * 7 + 2048
            and time.time() - path.stat().st_mtime < 86400
        ):
            try:
                cached = json.loads(path.read_text())
                if not isinstance(cached, dict) or not isinstance(cached.get("text"), str):
                    raise ValueError("Malformed cache")
                raw = cached["text"].encode()
                if (
                    cached["url"] == url
                    and len(raw) <= self.max_bytes
                    and hashlib.sha256(raw).hexdigest() == cached["content_hash"]
                ):
                    datetime.fromisoformat(cached["retrieved_at"])
                    return cached
            except (ValueError, KeyError, TypeError):
                pass
        if self.requests >= self.max_requests or time.monotonic() >= self.deadline:
            raise VendorUnavailableError("SEC request/time budget exhausted")
        response = None
        try:
            with _RATE_LOCK:
                time.sleep(max(0, 0.25 - (time.monotonic() - _LAST_REQUEST)))
                _LAST_REQUEST = time.monotonic()
            self.requests += 1
            response = requests.get(
                url,
                headers={"User-Agent": _user_agent()},
                stream=True,
                allow_redirects=False,
                timeout=(5, min(15, max(0.1, self.deadline - time.monotonic()))),
            )
            response.raise_for_status()
            if response.status_code != 200:
                raise VendorUnavailableError("SEC redirect or unsupported response")
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > self.max_bytes:
                    raise VendorUnavailableError("SEC document byte limit exceeded")
                if time.monotonic() >= self.deadline:
                    raise VendorUnavailableError("SEC request/time budget exhausted")
                chunks.append(chunk)
            raw = b"".join(chunks)
            text = raw.decode("utf-8-sig")
            # Hash the actual response bytes; canonical UTF-8 text preserves the
            # cache hash (BOM stripped only for parsing, not acquisition).
            if raw.startswith(b"\xef\xbb\xbf"):
                text = raw.decode("utf-8")
            value = {
                "url": url,
                "text": text,
                "content_hash": hashlib.sha256(raw).hexdigest(),
                "retrieved_at": datetime.now(UTC).isoformat(),
            }
            # Cache failure does not invalidate retrieved data; report persistence is separate.
            with suppress(OSError):
                path.parent.mkdir(parents=True, exist_ok=True)
                replace_file(path, lambda tmp: Path(tmp).write_text(json.dumps(value)))
            return value
        except (requests.RequestException, UnicodeError) as exc:
            raise VendorUnavailableError(
                f"SEC document unavailable ({type(exc).__name__})"
            ) from exc
        finally:
            if response is not None:
                response.close()


def _model_package_gap(gap: str) -> str:
    """This limit bounds what agents read; extraction and search use the full filing."""
    if gap.startswith("Document text limit reached;"):
        return f"{gap} (model package only; extraction and search read the full filing)"
    return gap


def _indexed_exhibits(client, filing) -> list[str]:
    """Exhibit documents of an 8-K from its filing index: every page in the submission but the cover.

    An 8-K submission holds its cover page and its exhibits. Release-like names come first so the
    two-exhibit allowance reaches the earnings release before a slide deck.
    """
    base = filing.url.rsplit("/", 1)[0]
    cover = filing.url.rsplit("/", 1)[-1]
    try:
        items = json.loads(client.fetch(f"{base}/index.json")["text"])["directory"]["item"]
    except (VendorUnavailableError, ValueError, KeyError, TypeError):
        return []
    names = [item.get("name", "") for item in items if isinstance(item, dict)]
    pages = [name for name in names if name.lower().endswith((".htm", ".html")) and name != cover
             and not re.fullmatch(r"R\d+\.htm", name) and "-index" not in name]
    pages.sort(key=lambda name: not re.search(r"release|ex-?99|press|earnings", name, re.I))
    return [f"{base}/{name}" for name in pages]


# Current reports the latest package did not select, per issuer and cutoff. Kept beside the package rather
# than inside it: the package's shape is part of saved results' fingerprints.
_UNSELECTED: dict[tuple[str, str], tuple[str, ...]] = {}


def unselected_for(cik: str, as_of_date: str) -> tuple[str, ...]:
    """Current reports in the period that the package built for this issuer and cutoff did not select."""
    return _UNSELECTED.get((cik, as_of_date), ())


# A report that combines results with other items (officer changes, a closing) carries three or four exhibits;
# at two, such a report stopped the run (ADBE, NKE, HON on past dates, 2026-11-13). More than this is still a gap.
_EXHIBITS_PER_8K = 4


def get_filing_evidence(ticker: str, as_of_date: str) -> DisclosurePackage:
    cutoff = date.fromisoformat(as_of_date)
    cik = cik_for(ticker)
    if cik is None:
        raise NoMarketDataError(ticker, ticker, "not a US SEC filer")
    client = DocumentClient(max_bytes=_DOCUMENT_TRANSPORT_MAX_BYTES)
    metadata = client.fetch(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:
        submissions = with_older_annual(client, json.loads(metadata["text"]), as_of_date)
        filings, gaps = select_filings(submissions, cik, as_of_date)
    except ValueError as exc:
        raise VendorUnavailableError("Unreadable SEC submissions JSON") from exc
    try:
        _UNSELECTED[(cik, as_of_date)] = tuple(unselected_events(submissions, cik, as_of_date, filings))
    except VendorUnavailableError:
        _UNSELECTED.pop((cik, as_of_date), None)
    documents, remaining = [], 120000
    latest_earnings = max(
        (filing for filing in filings if filing.form.startswith("8-K") and "2.02" in filing.items),
        key=lambda filing: (filing.filed_date, filing.accession), default=None,
    )
    # Acquire the two baseline statements and the latest release before notices
    # can consume the shared document and text budgets.
    ordered = sorted(
        filings,
        key=lambda filing: (
            0 if filing.form == "10-K" else
            1 if filing.form == "10-Q" else
            2 if filing == latest_earnings else 3,
            filing.filed_date, filing.accession,
        ),
    )
    for position, filing in enumerate(ordered):
        pending = [filing.url]
        seen = set()
        # Every selected filing's own document is read before the cap can be spent on another filing's exhibits:
        # an exhibit takes a place only while one remains for each filing still to come.
        still_to_come = len(ordered) - position - 1
        while pending and len(documents) < (8 if pending[0] == filing.url else 8 - still_to_come):
            url = pending.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                source = client.fetch(url)
                # The primary 8-K supplies exhibit links; its release needs a
                # separate allocation. Keep the existing per-document ceiling.
                is_latest_primary = filing == latest_earnings and url == filing.url
                available_chars = min(4000 if is_latest_primary else 40000, remaining)
                if available_chars <= 0:
                    # The excerpt budget bounds what agents read, not what is covered: the filing is still
                    # retrieved, hashed and read for its exhibits, and is recorded with no excerpt.
                    _unused, links, _unused_gaps = extract_sections(source["text"], max_chars=4000)
                    blocks, extraction_gaps = [], [
                        "Document text limit reached; package text limit 120000 reached; "
                        "retrieved and recorded with no excerpt"]
                else:
                    blocks, links, extraction_gaps = extract_sections(
                        source["text"], max_chars=available_chars,
                        prioritize_guidance=filing == latest_earnings and not is_latest_primary,
                    )
                if 0 < available_chars < 40000 and any(block.truncated for block in blocks):
                    extraction_gaps.append(
                        "Document text limit reached; package remaining "
                        f"{available_chars} characters; full source section/table not retained"
                    )
                extraction_gaps = [_model_package_gap(gap) for gap in extraction_gaps]
                remaining -= sum(len(b.text) for b in blocks)
                documents.append(
                    FilingDocument(
                        source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
                        filing=filing,
                        url=url,
                        retrieved_at=source["retrieved_at"],
                        content_hash=source["content_hash"],
                        blocks=tuple(blocks),
                        gaps=tuple(extraction_gaps),
                    )
                )
                gaps.extend(f"{filing.accession}: {g}" for g in extraction_gaps)
                if filing.form.startswith("8-K") and url == filing.url:
                    exhibit_links = [
                        (exhibit_url(filing, href), href, label)
                        for href, label in links
                        if re.search(r"(?:99[._-]?\d|ex99)", href + " " + label, re.I)
                        or (
                            "2.02" in filing.items
                            and (
                                re.search(r"\bpress release issued by\b", label, re.I)
                                or re.search(r"^press release,?\s+dated\b", label, re.I)
                            )
                        )
                    ]
                    if filing == latest_earnings:
                        exhibit_links.sort(
                            key=lambda entry: not bool(re.search(
                                r"(?:99[._-]?1|ex99[._-]?1)\b|press release",
                                entry[1] + " " + entry[2], re.I,
                            ))
                        )
                    exhibits = list(dict.fromkeys(
                        url for url, _, _ in exhibit_links if url and url != filing.url
                    ))
                    if "2.02" in filing.items and not exhibits:
                        # The cover page names its exhibits in many ways. The filing's own index lists them.
                        exhibits = _indexed_exhibits(client, filing)
                    pending.extend(exhibits[:_EXHIBITS_PER_8K])
                    if len(exhibits) > _EXHIBITS_PER_8K:
                        gaps.append(f"{filing.accession}: exhibit count limit reached")
                    if "2.02" in filing.items and not exhibits:
                        gaps.append(f"{filing.accession}: earnings exhibit unavailable")
            except VendorUnavailableError as exc:
                gaps.append(f"{filing.accession}: {exc}")
        if pending:
            # Reported only when a document was actually left out, not when the last one exactly filled the cap.
            gaps.append("Document count limit reached; coverage incomplete")
    return DisclosurePackage(
        cik=cik,
        as_of=cutoff,
        documents=tuple(documents),
        gaps=tuple(dict.fromkeys(gaps)),
        selected_accessions=tuple(f.accession for f in filings),
    )


def select_prior_quarter_filings(data: dict, cik: str, as_of: str, current_report_date: str):
    """One preceding quarter snapshot, explicitly requested for a KPI comparator.

    A 10-K can supply a year-end point-in-time KPI for a first-quarter comparison;
    it is never relabeled a quarterly income/cash-flow statement. Missing quarters,
    competing originals and multiple amendments remain visible coverage gaps.
    """
    rows, gaps = _filing_rows(data, cik, as_of)
    current = date.fromisoformat(current_report_date)
    originals = [row for row in rows if row.form in {'10-Q', '10-K'} and row.report_date]
    if not any(row.report_date == current for row in originals):
        return [], gaps + ['No eligible current report-period anchor for prior-quarter retrieval']
    candidates = [row for row in originals if 60 <= (current - row.report_date).days <= 120]
    if not candidates:
        return [], gaps + ['Immediately preceding quarter filing unavailable in recent metadata']
    prior_date = max(row.report_date for row in candidates)
    prior = [row for row in candidates if row.report_date == prior_date]
    if len(prior) != 1:
        return [], gaps + ['Prior-quarter original filing is ambiguous; comparison unavailable']
    original = prior[0]
    amendments = [row for row in rows if row.form == original.form + '/A'
                  and row.report_date == prior_date and row.filed_date >= original.filed_date]
    if len(amendments) > 1:
        return [], gaps + ['Multiple prior-quarter amendments exceed bounded comparison coverage']
    return [original, *amendments], gaps


def get_prior_quarter_evidence(ticker: str, as_of_date: str, current_report_date: str) -> DisclosurePackage:
    """Retrieve only the prior snapshot when the evidence gate requests it.

    Reuses the existing SEC cache and request policy, with at most metadata,
    one original and one amendment. No exhibits or unrelated annual/events are
    fetched, and failed/truncated retrieval stays an explicit package gap.
    """
    cutoff = date.fromisoformat(as_of_date)
    cik = cik_for(ticker)
    if cik is None:
        raise NoMarketDataError(ticker, ticker, 'not a US SEC filer')
    client = DocumentClient(max_bytes=_DOCUMENT_TRANSPORT_MAX_BYTES, max_requests=3, max_seconds=45)
    metadata = client.fetch(f'https://data.sec.gov/submissions/CIK{cik}.json')
    try:
        filings, gaps = select_prior_quarter_filings(json.loads(metadata['text']), cik,
                                                    as_of_date, current_report_date)
    except ValueError as exc:
        raise VendorUnavailableError('Unreadable prior-quarter submissions metadata') from exc
    documents = []
    for filing in filings:
        try:
            source = client.fetch(filing.url)
            blocks, _, extraction_gaps = extract_sections(source['text'], max_chars=40000, prioritize_rpo=True)
            rpo_facts, rpo_gaps = extract_rpo_facts(source['text'], cik, as_of_date)
            extraction_gaps = [*extraction_gaps, *rpo_gaps]
            documents.append(FilingDocument(
                source_id='sec-document-' + hashlib.sha256(filing.url.encode()).hexdigest(),
                filing=filing, url=filing.url, retrieved_at=source['retrieved_at'],
                content_hash=source['content_hash'], blocks=tuple(blocks), gaps=tuple(extraction_gaps),
                rpo_facts=rpo_facts,
            ))
            gaps.extend(f'{filing.accession}: {gap}' for gap in extraction_gaps)
        except VendorUnavailableError as exc:
            gaps.append(f'{filing.accession}: {exc}')
    return DisclosurePackage(cik=cik, as_of=cutoff, documents=tuple(documents),
                             gaps=tuple(dict.fromkeys(gaps)),
                             selected_accessions=tuple(f.accession for f in filings),
                             scope='Explicitly requested immediately preceding quarter KPI snapshot; not current financial statements')


def _inline_attribute(fragment: str, name: str) -> str | None:
    matches = re.findall(r"\s" + re.escape(name) + r"\s*=\s*([\"'])(.*?)\1", fragment.split('>', 1)[0], re.S)
    if len(matches) > 1:
        raise ValueError('duplicate inline attribute')
    return unescape(matches[0][1]) if matches else None


def extract_rpo_facts(text: str, cik: str, as_of_date: str):
    """Parse only the standard consolidated instant RPO concept and its basis.

    Keep exact cell/context/unit spans. Missing or ambiguous units, dimensions,
    unsupported number transforms and issuer/date mismatches stay unavailable.
    """
    cutoff = date.fromisoformat(as_of_date)
    # Preserve source offsets while excluding quoted code/comments from facts.
    searchable = re.sub(r'<!--.*?-->|<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>',
                        lambda match: ' ' * len(match.group()), text, flags=re.S | re.I)
    contexts, units = {}, {}
    for tag, target in (('context', contexts), ('unit', units)):
        for match in re.finditer(r'<xbrli:' + tag + r'\b[^>]*>.*?</xbrli:' + tag + '>', searchable, re.S):
            fragment = match.group()
            try:
                identity = _inline_attribute(fragment, 'id')
                if identity:
                    target.setdefault(identity, []).append(fragment)
            except ValueError:
                continue
    facts, gaps, seen = [], [], set()
    duplicate_ids = False
    candidates = [m for m in re.finditer(r'<ix:nonFraction\b[^>]*>.*?</ix:nonFraction>', searchable, re.S)
                  if re.search(r"""\bname\s*=\s*(["'])us-gaap:RevenueRemainingPerformanceObligation\1""", m.group().split('>', 1)[0])]
    if len(candidates) > 16:
        return (), ('RPO inline fact count exceeds bounded extraction',)
    for match in candidates:
        fragment = match.group()
        try:
            if fragment != text[match.start():match.end()]:
                raise ValueError('RPO cell contains excluded code/comment content')
            if len(fragment) > 2000 or _inline_attribute(fragment, 'name') != 'us-gaap:RevenueRemainingPerformanceObligation':
                raise ValueError('unsupported inline RPO cell')
            identity = _inline_attribute(fragment, 'id')
            context_id, unit_id = _inline_attribute(fragment, 'contextRef'), _inline_attribute(fragment, 'unitRef')
            duplicate_ids = duplicate_ids or identity in seen
            if (not identity or not re.fullmatch(r'[A-Za-z0-9_.:-]+', identity)
                    or identity in seen or len(contexts.get(context_id, [])) != 1
                    or len(units.get(unit_id, [])) != 1):
                raise ValueError('RPO source identity, context or unit is missing/ambiguous')
            seen.add(identity)
            context, unit = contexts[context_id][0], units[unit_id][0]
            if len(context) > 4000 or len(unit) > 1000:
                raise ValueError('RPO context/unit exceeds bounded extraction')
            identifiers = re.findall(r'<xbrli:identifier\b[^>]*>(.*?)</xbrli:identifier>', context, re.S)
            instants = re.findall(r'<xbrli:instant>(.*?)</xbrli:instant>', context)
            if len(identifiers) != 1 or identifiers[0].strip().zfill(10) != cik or len(instants) != 1:
                raise ValueError('RPO context issuer/instant mismatch')
            period = date.fromisoformat(instants[0].strip())
            if period > cutoff or '<xbrli:startDate>' in context or '<xbrli:endDate>' in context:
                raise ValueError('RPO instant exceeds cutoff or conflicts with duration')
            recognition_start = None
            if re.search(r'<(?:xbrli:(?:segment|scenario)|xbrldi:)', context):
                axis = 'us-gaap:RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionStartDateAxis'
                members = re.findall(r'<xbrldi:typedMember\b[^>]*>.*?</xbrldi:typedMember>', context, re.S)
                segments = re.findall(r'<xbrli:segment>(.*?)</xbrli:segment>', context, re.S)
                if (len(members) != 1 or len(segments) != 1 or segments[0].strip() != members[0]
                        or '<xbrli:scenario' in context or '<xbrldi:explicitMember' in context
                        or _inline_attribute(members[0], 'dimension') != axis):
                    raise ValueError('RPO dimensional context is not a supported total')
                starts = re.findall(r'<us-gaap:date.domain>(.*?)</us-gaap:date.domain>', members[0])
                if len(starts) != 1:
                    raise ValueError('RPO recognition-start axis unavailable')
                recognition_start = date.fromisoformat(starts[0].strip())
                if recognition_start != period + timedelta(days=1):
                    raise ValueError('RPO recognition start does not immediately follow the instant')
            measures = re.findall(r'<xbrli:measure>iso4217:([A-Z]{3})</xbrli:measure>', unit)
            if len(measures) != 1 or '<xbrli:divide>' in unit or unit.count('<xbrli:measure>') != 1:
                raise ValueError('RPO currency unit unavailable')
            if _inline_attribute(fragment, 'sign') not in (None, '+') or _inline_attribute(fragment, 'xsi:nil') is not None:
                raise ValueError('RPO negative/nil amount unsupported')
            if _inline_attribute(fragment, 'format') not in (None, 'ixt:num-dot-decimal', 'ixt:numdotdecimal'):
                raise ValueError('RPO number transform unsupported')
            displayed = unescape(fragment.split('>', 1)[1].rsplit('<', 1)[0]).strip()
            if not re.fullmatch(r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', displayed):
                raise ValueError('RPO numeric value malformed')
            scale = int(_inline_attribute(fragment, 'scale') or '0')
            if not -9 <= scale <= 12:
                raise ValueError('RPO scale unsupported')
            decimals_text = _inline_attribute(fragment, 'decimals')
            decimals = int(decimals_text) if decimals_text not in (None, 'INF') else None
            value = Decimal(displayed.replace(',', '')) * (Decimal(10) ** scale)
            if not value.is_finite() or value < 0:
                raise ValueError('RPO amount must be finite/nonnegative')
            facts.append(RemainingPerformanceObligationFact(
                locator='inline-fact-' + identity, value=value, currency=measures[0], period_end=period, recognition_start=recognition_start,
                display_value=displayed, scale=scale, decimals=decimals, context_id=context_id, unit_id=unit_id,
                character_start=match.start(), character_end=match.end(), exact_html=fragment,
                context_html=context, unit_html=unit,
            ))
        except (ValueError, ArithmeticError) as exc:
            gaps.append(str(exc))
    if not candidates:
        gaps.append('Standard consolidated instant RPO inline fact unavailable')
    if duplicate_ids:
        return (), tuple(dict.fromkeys(gaps + ['Duplicate RPO inline fact IDs']))
    return tuple(facts), tuple(dict.fromkeys(gaps))


def get_current_quarter_rpo_evidence(current: DisclosurePackage) -> DisclosurePackage:
    """Re-extract the current RPO section from its same cached SEC filing bytes.

    At most one latest primary filing is re-read. Changed bytes do not silently
    acquire the original document identity/hash; the comparison stays unavailable.
    """
    originals = [d for d in current.documents if d.filing.form in {'10-Q', '10-K'}
                 and d.filing.report_date and d.url == d.filing.url
                 and d.filing.cik == current.cik and d.filing.filed_date <= current.as_of
                 and d.filing.report_date <= current.as_of]
    if not originals:
        return current.model_copy(update={'documents': (), 'gaps': ('Current RPO primary filing unavailable',)})
    latest = max(d.filing.report_date for d in originals)
    candidates = [d for d in originals if d.filing.report_date == latest]
    if len(candidates) != 1:
        return current.model_copy(update={'documents': (), 'gaps': ('Current RPO primary filing ambiguous',)})
    document = candidates[0]
    expected_url = (f"https://www.sec.gov/Archives/edgar/data/{int(current.cik)}/"
                    f"{document.filing.accession.replace('-', '')}/{document.filing.primary_document}")
    if (not _ACCESSION.fullmatch(document.filing.accession)
            or not _NAME.fullmatch(document.filing.primary_document)
            or document.url != expected_url
            or document.source_id != 'sec-document-' + hashlib.sha256(document.url.encode()).hexdigest()):
        return current.model_copy(update={'documents': (), 'gaps': ('Current RPO source identity mismatch',)})
    try:
        source = DocumentClient(max_bytes=_DOCUMENT_TRANSPORT_MAX_BYTES, max_requests=1, max_seconds=20).fetch(document.url)
        if source['content_hash'] != document.content_hash:
            raise VendorUnavailableError('Current filing content changed; RPO comparison unavailable')
        blocks, _, gaps = extract_sections(source['text'], max_chars=40000, prioritize_rpo=True)
        facts, fact_gaps = extract_rpo_facts(source['text'], current.cik, str(current.as_of))
        updated = document.model_copy(update={'blocks': tuple(blocks), 'gaps': tuple(gaps), 'rpo_facts': facts})
        return current.model_copy(update={'documents': (updated,), 'gaps': tuple(dict.fromkeys([*gaps, *fact_gaps])),
                                          'selected_accessions': (document.filing.accession,),
                                          'scope': 'Current-quarter RPO source supplement; same filing bytes'})
    except VendorUnavailableError as exc:
        return current.model_copy(update={'documents': (), 'gaps': (str(exc),), 'selected_accessions': (document.filing.accession,)})

# Search acquisition has its own limits. The accepted-evidence brief above keeps
# its original selection, extraction and request budgets.
_SEARCH_FILING_LIMIT = 24
_SEARCH_DOCUMENT_LIMIT = 32
_SEARCH_EXHIBITS_PER_8K = 4


def select_search_filings(
    data: dict, cik: str, as_of: str, *, limit: int = _SEARCH_FILING_LIMIT
):
    """Select full-source periodic baselines and financing/event documents."""
    if not 1 <= limit <= _SEARCH_FILING_LIMIT:
        raise ValueError(f"Search filing limit must be 1-{_SEARCH_FILING_LIMIT}")
    rows, gaps = _filing_rows(data, cik, as_of, include_prospectus=True)
    periodic = []
    for form in ("10-K", "10-Q"):
        originals = [row for row in rows if row.form == form and row.report_date]
        if not originals:
            gaps.append(f"No eligible {form} primary filing in recent metadata")
            continue
        latest = max(originals, key=lambda row: (row.report_date, row.filed_date))
        periodic.append(latest)
        periodic.extend(
            row for row in rows if row.form == form + "/A"
            and row.report_date == latest.report_date
            and row.filed_date >= latest.filed_date
        )
    current_quarters = [row for row in periodic if row.form == "10-Q"]
    if current_quarters:
        current = max(current_quarters, key=lambda row: row.report_date or date.min)
        prior, prior_gaps = select_prior_quarter_filings(
            data, cik, as_of, str(current.report_date)
        )
        periodic.extend(prior)
        gaps.extend(prior_gaps)
    else:
        gaps.append("Prior-quarter 10-Q unavailable without current-quarter anchor")
    baseline = max(
        (row.report_date for row in periodic if row.report_date),
        default=date.fromisoformat(as_of),
    )
    events = [
        row for row in rows
        if (row.form.startswith("8-K") or row.form.startswith("424B"))
        and row.filed_date >= baseline
    ]
    # Keep all periodic anchors first; then newest event/prospectus filings.
    priority = list(dict.fromkeys(row.accession for row in periodic))
    by_accession = {row.accession: row for row in (*periodic, *events)}
    priority.extend(
        row.accession for row in sorted(
            events, key=lambda row: (row.filed_date, row.accession), reverse=True
        ) if row.accession not in priority
    )
    for accession in priority[limit:]:
        row = by_accession[accession]
        gaps.append(f"Filing count limit {limit}: omitted {accession} {row.url}")
    selected = [by_accession[accession] for accession in priority[:limit]]
    selected.sort(key=lambda row: (row.filed_date, row.accession))
    return selected, gaps


def get_filing_search_evidence(
    ticker: str, as_of_date: str, *, bounded_package: DisclosurePackage | None = None
) -> DisclosurePackage:
    """Acquire full visible filing blocks, separately from the bounded brief.

    If a bounded brief was already read, matching URLs must have the identical
    source hash. Changed cache/network content is omitted rather than replacing
    the source vintage previously supplied to the analysis.
    """
    cutoff = date.fromisoformat(as_of_date)
    cik = cik_for(ticker)
    if cik is None:
        raise NoMarketDataError(ticker, ticker, "not a US SEC filer")
    if bounded_package is not None and (
        bounded_package.cik != cik or bounded_package.as_of != cutoff
    ):
        raise ValueError("Bounded filing package issuer or cutoff mismatch")
    pins = {document.url: document.content_hash for document in (
        bounded_package.documents if bounded_package else ()
    )}
    client = DocumentClient(max_bytes=_DOCUMENT_TRANSPORT_MAX_BYTES,
                            max_requests=1 + _SEARCH_DOCUMENT_LIMIT, max_seconds=240)
    metadata = client.fetch(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:
        filings, gaps = select_search_filings(
            with_older_annual(client, json.loads(metadata["text"]), as_of_date), cik, as_of_date)
    except ValueError as exc:
        raise VendorUnavailableError("Unreadable SEC submissions JSON") from exc
    documents = []
    for filing in filings:
        pending = [filing.url]
        seen = set()
        exhibit_count = 0
        while pending:
            url = pending.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if len(documents) >= _SEARCH_DOCUMENT_LIMIT:
                gaps.append(
                    f"Document count limit {_SEARCH_DOCUMENT_LIMIT}: omitted "
                    f"{filing.accession} {url}"
                )
                for rest in pending:
                    gaps.append(
                        f"Document count limit {_SEARCH_DOCUMENT_LIMIT}: omitted "
                        f"{filing.accession} {rest}"
                    )
                continue
            try:
                source = client.fetch(url)
                if url in pins and source["content_hash"] != pins[url]:
                    gaps.append(f"{filing.accession} {url}: content changed from bounded source; omitted")
                    continue
                blocks, links, extraction_gaps = extract_sections(
                    source["text"], max_chars=max(1, len(source["text"]) * 2)
                )
                if any("Document text limit reached" in gap for gap in extraction_gaps):
                    gaps.append(f"{filing.accession} {url}: full source extraction limit reached; omitted")
                    continue
                rpo_facts = ()
                if filing.form in {"10-Q", "10-K"} and url == filing.url:
                    rpo_facts, _ = extract_rpo_facts(source["text"], cik, as_of_date)
                documents.append(FilingDocument(
                    source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
                    filing=filing, url=url, retrieved_at=source["retrieved_at"],
                    content_hash=source["content_hash"], blocks=tuple(blocks),
                    gaps=tuple(extraction_gaps), rpo_facts=rpo_facts,
                ))
                gaps.extend(f"{filing.accession} {url}: {gap}" for gap in extraction_gaps)
                if filing.form.startswith("8-K") and url == filing.url:
                    exhibits = []
                    for href, label in links:
                        if re.search(
                            r"(?:ex(?:hibit)?[-\s]?(?:1|4|5|10|23|99)[._-]?\d*|"
                            r"\b(?:1|4|5|10|23|99)[._-]\d+\b)",
                            href + " " + label, re.I,
                        ) or (
                            "2.02" in filing.items and re.search(
                                r"press release", label, re.I
                            )
                        ):
                            candidate = exhibit_url(filing, href)
                            if candidate and candidate != filing.url and candidate not in exhibits:
                                exhibits.append(candidate)
                            elif candidate is None:
                                gaps.append(
                                    f"{filing.accession}: unsupported exhibit link omitted "
                                    f"{urljoin(filing.url, href)[:300]}"
                                )
                    pending.extend(exhibits[:_SEARCH_EXHIBITS_PER_8K])
                    exhibit_count = len(exhibits)
                    for omitted in exhibits[_SEARCH_EXHIBITS_PER_8K:]:
                        gaps.append(
                            f"{filing.accession}: exhibit count limit "
                            f"{_SEARCH_EXHIBITS_PER_8K}; omitted {omitted}"
                        )
                    if "2.02" in filing.items and not exhibit_count:
                        gaps.append(f"{filing.accession}: earnings exhibit unavailable")
            except VendorUnavailableError as exc:
                gaps.append(f"{filing.accession} {url}: {exc}")
    return DisclosurePackage(
        cik=cik, as_of=cutoff, documents=tuple(documents),
        gaps=tuple(dict.fromkeys(gaps)),
        selected_accessions=tuple(filing.accession for filing in filings),
        scope="Full visible SEC filing source blocks for deterministic search; unvalidated source text",
    )
