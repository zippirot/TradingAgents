"""Fetch one filing's XBRL instance and calculation linkbase from SEC, within a small fixed budget."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.filed_instance import InstanceError, parse_calculation, parse_instance


def filed_statement_data(cik: str, accession: str, client=None) -> dict:
    """Facts and declared sums of one filing, with the instance document's address and hash.

    Three requests at most: the filing index, the instance, and the calculation linkbase (a separate file,
    or the schema when the filer embeds its linkbases there).
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
    linkbases = [name for name in names if name.endswith("_cal.xml")] or [name for name in names if name.endswith(".xsd")]
    if len(instances) != 1 or len(linkbases) != 1:
        raise VendorUnavailableError("SEC filing has no single XBRL instance and calculation linkbase")
    instance = client.fetch(f"{base}/{instances[0]}")
    linkbase = client.fetch(f"{base}/{linkbases[0]}")
    try:
        return {"facts": parse_instance(instance["text"].encode()),
                "calculation": parse_calculation(linkbase["text"].encode()),
                "url": instance["url"], "content_hash": instance["content_hash"],
                "retrieved_at": datetime.fromisoformat(instance["retrieved_at"]) if instance.get("retrieved_at")
                else datetime.now(UTC)}
    except InstanceError as exc:
        raise VendorUnavailableError(f"SEC XBRL data unreadable: {exc}") from exc
