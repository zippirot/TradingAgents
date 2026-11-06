"""Narrow, replayable cover-page share fallback for peer diagnostics only.

These dated counts do not enter canonical subject valuation or own history.
Class aggregation needs explicit equal economic rights and one-for-one conversion.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from html import unescape

from tradingagents.dataflows.vendors.sec_documents import (
    DocumentClient,
    FilingReference,
    _filing_rows,
    _inline_attribute,
)


def replay_peer_cover_shares(raw: dict, cik: str, as_of: str, completed_cutoff: str) -> dict:
    """Re-extract source facts; never trust a saved projected share total."""
    filing = FilingReference.model_validate(raw["filing"])
    source = raw["source"]
    cutoff = date.fromisoformat(as_of)
    completed = date.fromisoformat(completed_cutoff)
    expected = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{filing.accession.replace('-', '')}/{filing.primary_document}")
    if (filing.cik != cik or filing.filed_date > cutoff or completed > cutoff
            or filing.form not in {"10-Q", "10-K", "10-Q/A", "10-K/A"}
            or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", filing.accession)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:htm|html)", filing.primary_document)
            or filing.url != expected or source["url"] != expected
            or filing.report_date is None or filing.report_date > cutoff):
        raise ValueError("Peer cover filing issuer, URL, form or cutoff mismatch")
    html = source["text"]
    if (not isinstance(html, str) or len(html.encode()) > 5_000_000
            or hashlib.sha256(html.encode()).hexdigest() != source["content_hash"]
            or datetime.fromisoformat(source["retrieved_at"]).utcoffset() is None):
        raise ValueError("Peer cover source hash or retrieval metadata invalid")
    searchable = re.sub(r"<!--.*?-->|<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>",
                        lambda m: " " * len(m.group()), html, flags=re.S | re.I)
    contexts, units = {}, {}
    for tag, mapping in (("context", contexts), ("unit", units)):
        for match in re.finditer(r"<xbrli:" + tag + r"\b[^>]*>.*?</xbrli:" + tag + ">", searchable, re.S):
            key = _inline_attribute(match.group(), "id")
            mapping.setdefault(key, []).append(match.group())
    candidates = [
        m for m in re.finditer(r"<ix:nonFraction\b[^>]*>.*?</ix:nonFraction>", searchable, re.S)
        if _inline_attribute(m.group(), "name") == "dei:EntityCommonStockSharesOutstanding"
    ]
    if not candidates or len(candidates) > 16:
        raise ValueError("Bounded outstanding cover-share facts unavailable")
    rows, ids = [], set()
    for match in candidates:
        cell = match.group()
        identity = _inline_attribute(cell, "id")
        context_id, unit_id = _inline_attribute(cell, "contextRef"), _inline_attribute(cell, "unitRef")
        if (not identity or identity in ids or len(cell) > 2000 or cell != html[match.start():match.end()]
                or len(contexts.get(context_id, [])) != 1 or len(units.get(unit_id, [])) != 1):
            raise ValueError("Peer cover cell identity/context/unit ambiguous")
        ids.add(identity)
        context, unit = contexts[context_id][0], units[unit_id][0]
        identifiers = re.findall(r"<xbrli:identifier\b[^>]*>(.*?)</xbrli:identifier>", context, re.S)
        instants = re.findall(r"<xbrli:instant>(.*?)</xbrli:instant>", context)
        if (len(context) > 5000 or len(unit) > 1000 or len(identifiers) != 1
                or identifiers[0].strip().zfill(10) != cik or len(instants) != 1
                or "<xbrli:startDate>" in context or "<xbrli:endDate>" in context):
            raise ValueError("Peer cover instant/issuer is invalid")
        day = date.fromisoformat(instants[0].strip())
        if day > filing.filed_date:
            raise ValueError("Peer cover measurement exceeds its filing date")
        if day > completed:
            raise ValueError("Peer cover measurement exceeds completed cutoff")
        members = re.findall(r"<xbrldi:explicitMember\b[^>]*>.*?</xbrldi:explicitMember>", context, re.S)
        member = "consolidated"
        if members:
            segments = re.findall(r"<xbrli:segment>(.*?)</xbrli:segment>", context, re.S)
            if (len(members) != 1 or len(segments) != 1 or segments[0].strip() != members[0]
                    or _inline_attribute(members[0], "dimension") != "us-gaap:StatementClassOfStockAxis"):
                raise ValueError("Peer cover class dimensions are ambiguous")
            value = unescape(members[0].split(">", 1)[1].rsplit("<", 1)[0]).strip()
            if value not in {"us-gaap:CommonClassAMember", "us-gaap:CommonClassBMember"}:
                raise ValueError(f"Unsupported peer common-share class {value[:160]!r}; "
                                 "complete class set and equivalent economic rights are not established")
            member = "A" if value.endswith("AMember") else "B"
        elif re.search(r"<(?:xbrli:(?:segment|scenario)|xbrldi:)", context):
            raise ValueError("Unsupported peer cover dimensional context")
        if ("<xbrldi:typedMember" in context or "<xbrli:scenario" in context
                or unit.count("<xbrli:measure>") != 1
                or "<xbrli:measure>xbrli:shares</xbrli:measure>" not in unit
                or "<xbrli:divide>" in unit):
            raise ValueError("Peer cover unit or dimension unsupported")
        if (_inline_attribute(cell, "scale") not in (None, "0")
                or _inline_attribute(cell, "sign") not in (None, "+")
                or _inline_attribute(cell, "xsi:nil") is not None
                or _inline_attribute(cell, "decimals") not in (None, "0", "INF")
                or _inline_attribute(cell, "format") not in (None, "ixt:num-dot-decimal", "ixt:numdotdecimal")):
            raise ValueError("Peer cover share transform unsupported")
        displayed = unescape(cell.split(">", 1)[1].rsplit("<", 1)[0]).strip()
        if not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)", displayed):
            raise ValueError("Peer cover shares must be a positive integer")
        value = Decimal(displayed.replace(",", ""))
        if value <= 0:
            raise ValueError("Peer cover shares must be positive")
        rows.append({"class": member, "shares": str(value), "measurement_date": str(day),
                     "locator": "inline-fact-" + identity, "context_id": context_id,
                     "exact_html": cell, "context_html": context, "unit_html": unit,
                     "character_start": match.start(), "character_end": match.end()})
    latest = max(row["measurement_date"] for row in rows)
    rows = [row for row in rows if row["measurement_date"] == latest]
    by_class = {}
    for row in sorted(rows, key=lambda r: r["locator"]):
        if row["class"] in by_class and row["shares"] != by_class[row["class"]]["shares"]:
            raise ValueError("Conflicting peer cover class share counts")
        by_class.setdefault(row["class"], row)
    plain = " ".join(unescape(re.sub(r"<[^>]+>", " ", searchable)).split())
    rights_quote = "Consolidated DEI cover count; no class aggregation."
    assumptions = ["Cover shares held constant from measurement date to the completed price; intervening capital changes are not resolved."]
    if set(by_class) == {"A", "B"}:
        rights = re.search(r"The rights of the holders of Class A and Class B common stock are identical, except with respect to voting and conversion\.", plain)
        conversion = re.search(r"Shares of (?:the Company's|our) Class B common stock are convertible into an equivalent number of shares of (?:the Company's|our) Class A common stock", plain)
        complete = re.search(r"Class A common stock and Class B common stock are referred to, collectively, as common stock", plain)
        if not rights or not conversion or not complete:
            raise ValueError("Complete common classes and equivalent economic rights are not established")
        rights_quote = rights.group() + " " + conversion.group() + ". " + complete.group() + "."
        assumptions.append("Class A completed quote applied to A+B as common-share equivalents; voting/control premiums are not separately valued.")
    elif set(by_class) != {"consolidated"}:
        raise ValueError("Complete consolidated cover shares unavailable")
    components = list(by_class.values())
    total = sum((Decimal(r["shares"]) for r in components), Decimal(0))
    sid = "sec-peer-cover-" + source["content_hash"]
    return {"shares": str(total), "share_date": latest, "quality": "lower_quality_dated_cover",
            "basis": "Conditional dated cover-share sensitivity, not a same-date capitalization",
            "rights_quote": rights_quote, "pricing_assumptions": assumptions, "components": components,
            "source_id": sid, "content_hash": source["content_hash"],
            "source": {"source_id": sid, "url": expected, "filed_date": str(filing.filed_date),
                       "retrieved_at": source["retrieved_at"], "accession": filing.accession}}


def get_peer_cover_shares(cik: str, as_of: str, completed_cutoff: str) -> dict:
    """At most two existing SEC document reads, only for a missing peer count."""
    client = DocumentClient(max_requests=3, max_seconds=45)
    metadata = client.fetch(f"https://data.sec.gov/submissions/CIK{cik}.json")
    filings, _ = _filing_rows(json.loads(metadata["text"]), cik, as_of)
    eligible = sorted((f for f in filings if f.form in {"10-K", "10-Q"}),
                      key=lambda f: (f.report_date or date.min, f.filed_date), reverse=True)[:2]
    if not eligible:
        raise ValueError("No eligible peer annual/quarterly filing for cover shares")
    for filing in eligible:
        raw = {"filing": filing.model_dump(mode="json"), "source": client.fetch(filing.url)}
        try:
            replay_peer_cover_shares(raw, cik, as_of, completed_cutoff)
            return raw
        except ValueError as exc:
            # An unavailable/future cover instant cannot hide an older eligible
            # filing. Ambiguous classes, issuer, hash or rights still fail closed.
            if str(exc) not in {"Peer cover measurement exceeds completed cutoff",
                                "Bounded outstanding cover-share facts unavailable"}:
                raise
    raise ValueError("No usable dated cover shares in the two eligible filings")
