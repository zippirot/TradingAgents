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
from datetime import UTC, date, datetime
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


class FilingDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    filing: FilingReference
    url: str
    retrieved_at: datetime
    content_hash: str
    blocks: tuple[SourceBlock, ...]
    gaps: tuple[str, ...] = ()


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


def select_filings(data: dict, cik: str, as_of: str, limit: int = 6):
    """Select annual/quarterly baselines and subsequent relevant 8-Ks."""
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
        if form not in {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A"}:
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
            not r.items or any(item in r.items for item in ("2.02", "2.03", "1.01", "3.02", "8.01"))
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
    def __init__(self):
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

    def flush(self):
        text = " ".join("".join(self.parts).split())
        self.parts = []
        if text:
            self.blocks.append(
                SourceBlock(
                    locator=f"block-{len(self.blocks) + 1}", section=self.section, text=text
                )
            )
            if self.heading:
                self.section = text[:200]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "ix:hidden", "head"):
            self.hidden += 1
        if self.hidden:
            return
        if tag == "table":
            if not self.table_depth:
                self.flush()
                self.heading = False
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
        if tag == "a":
            self.href = attrs.get("href")
            self.link_text = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "ix:hidden", "head") and self.hidden:
            self.hidden -= 1
            return
        if self.hidden:
            return
        if tag == "a" and self.href is not None:
            self.links.append((self.href, "".join(self.link_text).strip()))
            self.href = None
        if tag == "table" and self.table_depth:
            self.table_depth -= 1
            if not self.table_depth:
                self.flush()
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


def extract_sections(text: str, max_chars: int = 60000):
    parser = _Sections()
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
    candidates = list(enumerate(parser.blocks))
    bounded = sum(len(block.text) for block in parser.blocks) > max_chars
    if bounded:
        gaps.append("Document text limit reached; selected sections omit other content")
        financial = re.compile(
            r"equity|lease|financ|commitment|guidance|outlook|revenue|net retention|"
            r"remaining performance|earnings|reconciliation|cash flow|capital|debt|"
            r"shares|stock|AI customer|AI product",
            re.I,
        )

        # Prefer relevant notes even when they occur after cover pages and risk
        # boilerplate. Stable locators still refer to original document order.
        def priority(pair):
            _, block = pair
            hits = len(financial.findall(block.text))
            return (
                hits + bool(re.search(r"\d", block.text)) * bool(hits),
                bool(financial.search(block.section)),
            )

        candidates.sort(key=priority, reverse=True)
    selected = []
    for index, block in candidates:
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(block.text) > remaining:
            # Prefer whole shorter blocks; use a partial block only when there
            # is no smaller remaining block to preserve.
            if any(
                len(other.text) <= remaining
                for j, other in candidates
                if j not in {i for i, _ in selected} and j != index
            ):
                continue
            selected.append((index, block.model_copy(update={"text": block.text[:remaining]})))
            gaps.append("Document text limit reached; section truncated")
            break
        selected.append((index, block))
        used += len(block.text)
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


class DocumentClient:
    """Finite per-run HTTP acquisition with immutable-content cache metadata."""

    def __init__(self, max_bytes=2_000_000, max_requests=10, max_seconds=90):
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


def get_filing_evidence(ticker: str, as_of_date: str) -> DisclosurePackage:
    cutoff = date.fromisoformat(as_of_date)
    cik = cik_for(ticker)
    if cik is None:
        raise NoMarketDataError(ticker, ticker, "not a US SEC filer")
    client = DocumentClient()
    metadata = client.fetch(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:
        filings, gaps = select_filings(json.loads(metadata["text"]), cik, as_of_date)
    except ValueError as exc:
        raise VendorUnavailableError("Unreadable SEC submissions JSON") from exc
    documents, remaining = [], 120000
    for filing in filings:
        pending = [filing.url]
        seen = set()
        while pending and len(documents) < 8:
            url = pending.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                source = client.fetch(url)
                blocks, links, extraction_gaps = extract_sections(
                    source["text"], max_chars=min(40000, remaining)
                )
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
                    exhibits = [
                        exhibit_url(filing, href)
                        for href, label in links
                        if re.search(r"(?:99[._-]?\d|ex99)", href + " " + label, re.I)
                    ]
                    exhibits = list(dict.fromkeys(u for u in exhibits if u and u != filing.url))
                    pending.extend(exhibits[:2])
                    if len(exhibits) > 2:
                        gaps.append(f"{filing.accession}: exhibit count limit reached")
                    if "2.02" in filing.items and not exhibits:
                        gaps.append(f"{filing.accession}: earnings exhibit unavailable")
            except VendorUnavailableError as exc:
                gaps.append(f"{filing.accession}: {exc}")
        if pending or len(documents) >= 8:
            gaps.append("Document count limit reached; coverage incomplete")
    return DisclosurePackage(
        cik=cik,
        as_of=cutoff,
        documents=tuple(documents),
        gaps=tuple(dict.fromkeys(gaps)),
        selected_accessions=tuple(f.accession for f in filings),
    )
