"""Dated, unverified Alpha Vantage transcript source with offline turn search."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import VendorError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.net import get_scrubbed
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.alpha_vantage.common import (
    API_BASE_URL,
    REQUEST_TIMEOUT,
    get_api_key,
)
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
from tradingagents.source_replay import source_now

_LABEL = "vendor transcript, wording unverified"
_MONTHS = (
    "(?:January|February|March|April|May|June|July|August|September|October|November|December)"
)
_CALL_DATE = re.compile(
    rf"\b(?:conference|earnings)\s+call\b.{{0,160}}?\b({_MONTHS}\s+\d{{1,2}},?\s+\d{{4}})\b",
    re.I,
)
_QUARTER_WORDS = {"1": ("first", "1st", "q1"), "2": ("second", "2nd", "q2"),
                  "3": ("third", "3rd", "q3"), "4": ("fourth", "4th", "q4")}
_MAX_RAW = 1_000_000
_MAX_TURNS = 250
_MAX_TEXT = 500_000
_MAX_QUERY = 200
_MAX_PASSAGES = 3
_MAX_CHARS = 12_000


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _json_hash(value: dict) -> str:
    return _hash(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _quarter_parts(quarter: str):
    match = re.fullmatch(r"(20\d{2})Q([1-4])", quarter or "")
    if not match:
        raise ValueError("Transcript fiscal quarter must be YYYYQ1-YYYYQ4")
    return match.groups()


def _release_quarters(text: str) -> set[str]:
    """Find a directly named fiscal year/quarter in an earnings-results line.

    A nearby calendar date after "quarter ended" is insufficient to determine
    a non-calendar fiscal year.
    """
    text = re.sub(r"[-\u2010-\u2015]", " ", text)
    if not re.search(r"\b(?:results?|earnings|announc\w*|report\w*)\b", text, re.I):
        return set()
    matches = []
    for number, names in _QUARTER_WORDS.items():
        words = "|".join(names)
        quarter = rf"(?:(?:{words})\s+quarter|q{number})"
        after = rf"\b{quarter}\s+(?:of\s+)?(?:fiscal\s+)?(?:year\s+)?(20\d{{2}})\b"
        before = rf"\b(?:fiscal\s+)?(?:year\s+)?(20\d{{2}})\s+{quarter}\b"
        for pattern in (after, before):
            for match in re.finditer(pattern, text, re.I):
                matches.append((match.start(), f"{match.group(1)}Q{number}"))
    return {min(matches)[1]} if matches else set()

def _quarter_match(text: str, quarter: str) -> bool:
    _quarter_parts(quarter)
    return quarter in _release_quarters(text)

def _cutoff(as_of_date: str, cutoff_utc: str | None):
    day = date.fromisoformat(as_of_date)
    if cutoff_utc is None:
        return day, None
    moment = datetime.fromisoformat(cutoff_utc.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("Transcript cutoff_utc must include a timezone")
    return day, moment.astimezone(UTC)


def _call_availability(call_day: date, _text: str) -> tuple[datetime, str]:
    # Announced start time cannot prove that later Q&A or the vendor's full
    # transcript was available. With no publication/end timestamp, withhold
    # it for exact intraday cutoffs until the end of the dated ET call day.
    eastern = ZoneInfo("America/New_York")
    return (datetime.combine(call_day, time.max, eastern).astimezone(UTC),
            "conservative end of ET call day; publication time unavailable")


def resolve_sec_call_date(
    filing_corpus: DisclosurePackage | None, fiscal_quarter: str, as_of_date: str,
    *, cutoff_utc: str | None = None,
) -> dict:
    """Use a matching 8-K earnings exhibit, never the fiscal quarter as a date."""
    _quarter_parts(fiscal_quarter)
    cutoff_day, cutoff_moment = _cutoff(as_of_date, cutoff_utc)
    unavailable = {
        "status": "undated", "call_date": None, "available_at_utc": None,
        "source_id": None, "locator": None, "content_hash": None,
        "source_url": None, "quote": None,
        "reason": "No retained SEC earnings exhibit establishes the call date",
    }
    if filing_corpus is None:
        return unavailable
    matches = []
    for document in filing_corpus.documents:
        filing = document.filing
        if (
            filing.cik != filing_corpus.cik or not filing.form.startswith("8-K")
            or "2.02" not in filing.items
            or filing.filed_date > cutoff_day
            or (filing.report_date and filing.report_date > cutoff_day)
        ):
            continue
        if not any(_quarter_match(block.text, fiscal_quarter) for block in document.blocks[:20]):
            continue
        for block in document.blocks:
            if block.truncated:
                continue
            found = _CALL_DATE.search(block.text)
            if not found:
                continue
            raw_date = found.group(1).replace(",", "")
            try:
                call_day = datetime.strptime(raw_date, "%B %d %Y").date()
                available_at, basis = _call_availability(call_day, block.text)
            except ValueError:
                continue
            matches.append({
                "status": "dated", "call_date": call_day.isoformat(),
                "available_at_utc": available_at.isoformat(),
                "availability_basis": basis,
                "source_id": document.source_id, "locator": block.locator,
                "content_hash": document.content_hash, "source_url": document.url,
                "quote": block.text, "reason": "",
            })
    if not matches:
        return unavailable
    dates = {item["call_date"] for item in matches}
    if len(dates) != 1:
        return {**unavailable, "status": "ambiguous", "reason": "Conflicting SEC call dates"}
    chosen = sorted(matches, key=lambda item: (
        item["source_url"], item["locator"],
    ))[0]
    if date.fromisoformat(chosen["call_date"]) > cutoff_day or (
        cutoff_moment and datetime.fromisoformat(chosen["available_at_utc"]) > cutoff_moment
    ):
        return {
            **unavailable, "status": "future",
            "reason": "SEC-dated earnings call occurs after analysis cutoff",
        }
    return chosen


def _unavailable(ticker: str, quarter: str, reason: str, date_evidence: dict | None = None) -> dict:
    return {
        "schema_version": 1, "status": "unavailable", "ticker": ticker,
        "fiscal_quarter": quarter, "provider": "Alpha Vantage", "label": _LABEL,
        "reason": reason, "date_evidence": date_evidence,
        "source_id": None, "content_hash": None, "retrieved_at": None,
        "qa_start": None, "turns": [], "record_hash": None,
    }


def _notice_reason(payload: dict) -> str | None:
    notice = payload.get("Information") or payload.get("Note")
    if isinstance(notice, str):
        lower = notice.lower()
        if any(word in lower for word in ("rate limit", "requests per day", "call frequency")):
            return "Alpha Vantage transcript rate limit reached"
        if "premium" in lower or "entitlement" in lower:
            return "Alpha Vantage transcript premium entitlement required"
        if "api key" in lower or "apikey" in lower:
            return "Alpha Vantage transcript API key unavailable"
        return "Alpha Vantage transcript provider notice"
    if payload.get("Error Message"):
        return "Alpha Vantage transcript request rejected"
    return None


def parse_transcript_response(
    raw: str, ticker: str, fiscal_quarter: str, as_of_date: str,
    filing_corpus: DisclosurePackage | None, *, cutoff_utc: str | None = None,
    retrieved_at: str | None = None,
) -> dict:
    """Normalize a provider response only after an eligible SEC call-date pin."""
    ticker = normalize_symbol(ticker)
    date_evidence = resolve_sec_call_date(
        filing_corpus, fiscal_quarter, as_of_date, cutoff_utc=cutoff_utc,
    )
    if date_evidence["status"] != "dated":
        return _unavailable(ticker, fiscal_quarter, date_evidence["reason"], date_evidence)
    if not isinstance(raw, str) or len(raw.encode()) > _MAX_RAW:
        return _unavailable(ticker, fiscal_quarter, "Transcript response exceeds byte limit", date_evidence)
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return _unavailable(ticker, fiscal_quarter, "Malformed transcript response", date_evidence)
    if not isinstance(payload, dict):
        return _unavailable(ticker, fiscal_quarter, "Malformed transcript response", date_evidence)
    notice = _notice_reason(payload)
    if notice:
        return _unavailable(ticker, fiscal_quarter, notice, date_evidence)
    if payload.get("symbol") != ticker or payload.get("quarter") != fiscal_quarter:
        return _unavailable(ticker, fiscal_quarter, "Transcript symbol or fiscal quarter mismatch", date_evidence)
    raw_turns = payload.get("transcript")
    if not isinstance(raw_turns, list) or not 1 <= len(raw_turns) <= _MAX_TURNS:
        return _unavailable(ticker, fiscal_quarter, "Transcript turn count invalid or exceeds limit", date_evidence)
    turns = []
    size = 0
    qa_start = None
    for index, item in enumerate(raw_turns):
        if not isinstance(item, dict):
            return _unavailable(ticker, fiscal_quarter, "Malformed transcript turn", date_evidence)
        speaker, title, content = item.get("speaker"), item.get("title"), item.get("content")
        if (
            not isinstance(speaker, str) or not speaker.strip() or len(speaker) > 160
            or not isinstance(title, str) or len(title) > 160
            or not isinstance(content, str) or not content.strip()
        ):
            return _unavailable(ticker, fiscal_quarter, "Malformed transcript turn", date_evidence)
        size += len(content)
        if size > _MAX_TEXT:
            return _unavailable(ticker, fiscal_quarter, "Transcript text limit exceeded", date_evidence)
        if qa_start is None and speaker.strip().lower() == "operator" and re.search(
            r"\b(?:first question|question.and.answer session|begin (?:the )?q\s*&\s*a)\b",
            content, re.I,
        ):
            qa_start = index
        turns.append({
            "locator": f"turn-{index + 1}", "speaker": speaker.strip(),
            "title": title.strip(), "text": content,
            "section": "Q&A" if qa_start is not None else "Prepared remarks",
        })
    source_hash = _hash(raw)
    record = {
        "schema_version": 1, "status": "ready", "ticker": ticker,
        "fiscal_quarter": fiscal_quarter, "provider": "Alpha Vantage",
        "label": _LABEL, "reason": "", "date_evidence": date_evidence,
        "source_id": "vendor-transcript-" + _hash(f"{ticker}:{fiscal_quarter}:{source_hash}"),
        "content_hash": source_hash,
        "retrieved_at": retrieved_at or source_now(UTC).isoformat(),
        "qa_start": qa_start, "turns": turns,
    }
    record["record_hash"] = _json_hash(record)
    return record


def _cache_path(ticker: str, quarter: str) -> Path:
    key = _hash(f"{ticker}:{quarter}")
    return Path(get_config()["data_cache_dir"]) / "transcripts" / (key + ".json")


def _request_transcript(ticker: str, fiscal_quarter: str) -> str:
    """One bounded free-key request; preserve raw notices for accurate classification."""
    from tradingagents.source_replay import external_input

    return external_input("vendor_transcript", {"ticker": ticker, "quarter": fiscal_quarter},
                          lambda: _request_transcript_live(ticker, fiscal_quarter))


def _request_transcript_live(ticker: str, fiscal_quarter: str) -> str:
    api_key = get_api_key()
    response = get_scrubbed(
        API_BASE_URL,
        params={
            "function": "EARNINGS_CALL_TRANSCRIPT",
            "symbol": ticker, "quarter": fiscal_quarter,
            "apikey": api_key, "source": "trading_agents",
        },
        timeout=REQUEST_TIMEOUT,
        secret=api_key,
    )
    return response.text


def get_transcript_evidence(
    ticker: str, fiscal_quarter: str, as_of_date: str, *,
    filing_corpus: DisclosurePackage | None, cutoff_utc: str | None = None,
    allow_network: bool = False,
) -> dict:
    """Read pinned cache; optional provider call is for authorized acquisition."""
    ticker = normalize_symbol(ticker)
    date_evidence = resolve_sec_call_date(
        filing_corpus, fiscal_quarter, as_of_date, cutoff_utc=cutoff_utc,
    )
    if date_evidence["status"] != "dated":
        return _unavailable(ticker, fiscal_quarter, date_evidence["reason"], date_evidence)
    path = _cache_path(ticker, fiscal_quarter)
    if path.exists():
        try:
            if path.stat().st_size > _MAX_RAW * 2:
                raise ValueError("Cached transcript exceeds limit")
            cached = json.loads(path.read_text())
            if (
                cached["ticker"] != ticker or cached["quarter"] != fiscal_quarter
                or not isinstance(cached["raw"], str)
                or _hash(cached["raw"]) != cached["content_hash"]
            ):
                raise ValueError("Cached transcript hash or identity mismatch")
            return parse_transcript_response(
                cached["raw"], ticker, fiscal_quarter, as_of_date, filing_corpus,
                cutoff_utc=cutoff_utc, retrieved_at=cached["retrieved_at"],
            )
        except (OSError, ValueError, KeyError, TypeError):
            return _unavailable(
                ticker, fiscal_quarter, "Cached transcript changed or malformed",
                date_evidence,
            )
    if not allow_network:
        return _unavailable(ticker, fiscal_quarter, "Transcript absent from local cache", date_evidence)
    try:
        raw = _request_transcript(ticker, fiscal_quarter)
    except (VendorError, requests.RequestException, TimeoutError) as exc:
        name = type(exc).__name__.lower()
        reason = (
            "Alpha Vantage transcript API key unavailable" if "notconfigured" in name
            else "Alpha Vantage transcript rate limit reached" if "ratelimit" in name
            else "Alpha Vantage transcript provider unavailable"
        )
        return _unavailable(ticker, fiscal_quarter, reason, date_evidence)
    record = parse_transcript_response(
        raw, ticker, fiscal_quarter, as_of_date, filing_corpus,
        cutoff_utc=cutoff_utc,
    )
    if record["status"] == "ready":
        cache = {
            "ticker": ticker, "quarter": fiscal_quarter, "raw": raw,
            "content_hash": record["content_hash"], "retrieved_at": record["retrieved_at"],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            replace_file(path, lambda target: Path(target).write_text(json.dumps(cache)))
        except OSError:
            pass
    return record


def _check_record(record: dict) -> None:
    if not isinstance(record, dict) or record.get("status") != "ready":
        raise ValueError("Transcript source unavailable")
    seal = {key: value for key, value in record.items() if key != "record_hash"}
    if record.get("record_hash") != _json_hash(seal):
        raise ValueError("Transcript source changed")
    if record.get("label") != _LABEL or record.get("provider") != "Alpha Vantage":
        raise ValueError("Transcript source label mismatch")


def prepared_remarks_excerpt(record: dict, *, max_chars: int = 4000) -> dict:
    """Return whole prepared turns only, with an explicit limit gap."""
    _check_record(record)
    if not 1 <= max_chars <= 4000:
        raise ValueError("Prepared remarks size limit exceeded")
    selected, used, gaps = [], 0, []
    for turn in record["turns"]:
        if turn["section"] != "Prepared remarks":
            break
        remaining = max_chars - used
        if remaining <= 0:
            gaps.append("Prepared remarks size limit reached")
            break
        if len(turn["text"]) > remaining:
            selected.append({**turn, "text": turn["text"][:remaining], "truncated": True})
            gaps.append(f"{turn['locator']}: partial prepared-remarks excerpt at size limit")
            break
        selected.append({**turn, "truncated": False})
        used += len(turn["text"])
    if record["qa_start"] is None:
        gaps.append("Q&A boundary not identified in vendor transcript")
    return {
        "label": _LABEL, "content_hash": record["content_hash"],
        "call_date": record["date_evidence"]["call_date"],
        "turns": selected,
        "text": "\n\n".join(f"{turn['speaker']}: {turn['text']}" for turn in selected),
        "gaps": gaps,
    }


def search_transcript_evidence(
    record: dict, query: str, *, max_passages: int = _MAX_PASSAGES,
    max_chars: int = _MAX_CHARS,
) -> dict:
    """Search exact Q&A turns offline; never truncate a returned turn."""
    _check_record(record)
    if not 1 <= max_passages <= _MAX_PASSAGES or not 1 <= max_chars <= _MAX_CHARS:
        raise ValueError("Transcript search limit exceeded")
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= _MAX_QUERY:
        raise ValueError("Transcript search query limit exceeded")
    words = [word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) >= 3]
    if not words:
        raise ValueError("Transcript search query has no searchable words")
    ranked = []
    for turn in record["turns"]:
        if turn["section"] != "Q&A":
            continue
        low = turn["text"].lower()
        hits = sum(re.search(r"\b" + re.escape(word) + r"s?\b", low) is not None for word in words)
        if hits:
            ranked.append((hits, turn))
    ranked.sort(key=lambda item: (-item[0], int(item[1]["locator"].split("-")[1])))
    passages, used, gaps = [], 0, []
    for _, turn in ranked:
        if len(passages) >= max_passages:
            break
        if used + len(turn["text"]) > max_chars:
            gaps.append(f"{turn['locator']}: transcript search size limit; omitted whole turn")
            continue
        passage = {
            **turn, "source_id": record["source_id"],
            "provider": record["provider"], "label": _LABEL,
            "call_date": record["date_evidence"]["call_date"],
            "call_date_source_id": record["date_evidence"]["source_id"],
            "call_date_locator": record["date_evidence"]["locator"],
            "content_hash": record["content_hash"],
            "passage_hash": _hash(turn["text"]),
            "citation_ref": f"{record['source_id']}#{turn['locator']}",
        }
        passages.append(passage)
        used += len(turn["text"])
    if record["qa_start"] is None:
        gaps.append("Q&A boundary not identified in vendor transcript")
    if not passages:
        gaps.append("not found in retained vendor transcript")
    return {
        "query": query, "label": _LABEL, "content_hash": record["content_hash"],
        "passages": passages, "gaps": gaps,
    }

def select_latest_eligible_call(
    filing_corpus: DisclosurePackage | None, as_of_date: str, *,
    cutoff_utc: str | None = None,
) -> dict:
    """Choose a call from explicit SEC fiscal-quarter wording, not calendar math."""
    cutoff_day, _ = _cutoff(as_of_date, cutoff_utc)
    if filing_corpus is None:
        return {
            "status": "unavailable", "fiscal_quarter": None,
            "date_evidence": None, "reason": "Retained SEC earnings exhibits unavailable",
        }
    quarters = set()
    for document in filing_corpus.documents:
        filing = document.filing
        if (
            filing.cik != filing_corpus.cik or not filing.form.startswith("8-K")
            or "2.02" not in filing.items
            or filing.filed_date > cutoff_day
            or (filing.report_date and filing.report_date > cutoff_day)
        ):
            continue
        for block in document.blocks[:20]:
            if not block.truncated:
                quarters.update(_release_quarters(block.text))
    if not quarters:
        return {
            "status": "unavailable", "fiscal_quarter": None,
            "date_evidence": None,
            "reason": "No retained SEC earnings exhibit names an explicit fiscal quarter",
        }
    candidates, failures = [], []
    for quarter in sorted(quarters):
        dated = resolve_sec_call_date(
            filing_corpus, quarter, as_of_date, cutoff_utc=cutoff_utc,
        )
        if dated["status"] == "dated":
            candidates.append((quarter, dated))
        else:
            failures.append(dated)
    if not candidates:
        reason = (
            "Conflicting SEC conference-call dates"
            if any(item["status"] == "ambiguous" for item in failures)
            else "SEC-dated earnings call occurs after analysis cutoff"
            if any(item["status"] == "future" for item in failures)
            else "Explicit fiscal quarter found, but no SEC call date is available"
        )
        return {
            "status": "unavailable", "fiscal_quarter": None,
            "date_evidence": None, "reason": reason,
        }
    candidates.sort(key=lambda item: (
        item[1]["call_date"], item[1]["available_at_utc"], item[0],
    ), reverse=True)
    latest = candidates[0]
    if len(candidates) > 1 and candidates[1][1]["call_date"] == latest[1]["call_date"]:
        return {
            "status": "unavailable", "fiscal_quarter": None,
            "date_evidence": None, "reason": "Multiple fiscal quarters share the latest SEC call date",
        }
    return {
        "status": "ready", "fiscal_quarter": latest[0],
        "date_evidence": latest[1], "reason": "",
    }


def get_latest_transcript_evidence(
    ticker: str, as_of_date: str, *,
    filing_corpus: DisclosurePackage | None, cutoff_utc: str | None = None,
    allow_network: bool = False,
) -> dict:
    """Select the latest eligible explicitly named quarter before acquisition."""
    choice = select_latest_eligible_call(
        filing_corpus, as_of_date, cutoff_utc=cutoff_utc,
    )
    if choice["status"] != "ready":
        return _unavailable(
            normalize_symbol(ticker), "", choice["reason"], choice["date_evidence"],
        )
    return get_transcript_evidence(
        ticker, choice["fiscal_quarter"], as_of_date,
        filing_corpus=filing_corpus, cutoff_utc=cutoff_utc,
        allow_network=allow_network,
    )
