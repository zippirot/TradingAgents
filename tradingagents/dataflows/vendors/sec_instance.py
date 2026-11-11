"""Fetch one filing's XBRL instance and calculation linkbase from SEC, within a small fixed budget."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.filed_instance import InstanceError, parse_instance, parse_structure


def filed_statement_data(cik: str, accession: str, client=None) -> dict:
    """Facts and declared sums of one filing, with the instance document's address and hash.

    Three requests at most: the filing index, the instance, and SEC's resolved structure file for the filing
    (declared sums, which side each tag sits on, and where each tag is shown).
    """
    from tradingagents.dataflows.vendors.sec_documents import (
        _DOCUMENT_TRANSPORT_MAX_BYTES,
        DocumentClient,
    )

    client = client or DocumentClient(max_bytes=_DOCUMENT_TRANSPORT_MAX_BYTES, max_requests=3, max_seconds=45)
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    try:
        names = [item.get("name", "") for item in json.loads(client.fetch(f"{base}/index.json")["text"])["directory"]["item"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise VendorUnavailableError("SEC filing index unreadable") from exc
    instances = [name for name in names if name.endswith("_htm.xml")]
    if len(instances) != 1 or "MetaLinks.json" not in names:
        raise VendorUnavailableError("SEC filing has no single XBRL instance with its structure file")
    instance = client.fetch(f"{base}/{instances[0]}")
    structure = client.fetch(f"{base}/MetaLinks.json")
    try:
        parsed = parse_structure(structure["text"].encode())
        return {"facts": parse_instance(instance["text"].encode()),
                "structure": parsed, "calculation": parsed.calculation,
                "url": instance["url"], "content_hash": instance["content_hash"],
                "retrieved_at": datetime.fromisoformat(instance["retrieved_at"]) if instance.get("retrieved_at")
                else datetime.now(UTC)}
    except InstanceError as exc:
        raise VendorUnavailableError(f"SEC XBRL data unreadable: {exc}") from exc
