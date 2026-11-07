import hashlib
from datetime import UTC, date, datetime

import pytest

from tradingagents.dataflows.filing_search import corpus_hash, search_filing_evidence
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)


def corpus(blocks, *, filed=date(2026, 8, 5), as_of=date(2026, 9, 1)):
    filing = FilingReference(
        cik="0001582961", accession="0001582961-26-000002", form="10-Q",
        filed_date=filed, report_date=date(2026, 6, 30),
        primary_document="quarter.htm", items="",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000158296126000002/quarter.htm",
    )
    document = FilingDocument(
        source_id="sec-document-" + hashlib.sha256(filing.url.encode()).hexdigest(),
        filing=filing, url=filing.url, retrieved_at=datetime.now(UTC),
        content_hash="abc123", blocks=tuple(blocks),
    )
    return DisclosurePackage(cik=filing.cik, as_of=as_of, documents=(document,))


def test_search_finds_complete_table_and_source_identity():
    package = corpus((
        SourceBlock(locator="block-1", section="Note 4. Remaining performance obligations",
                    text="Backlog timing ; 2026 | $50 million ; 2027 | $80 million"),
        SourceBlock(locator="block-2", section="Note 5. Leases",
                    text="Future lease commitments have not commenced."),
    ))
    result = search_filing_evidence(package, "backlog timing")
    assert len(result["passages"]) == 1
    passage = result["passages"][0]
    assert passage["text"] == package.documents[0].blocks[0].text
    assert passage["locator"] == "block-1"
    assert passage["source_id"] == package.documents[0].source_id
    assert passage["filing_form"] == "10-Q"
    assert passage["filing_date"] == "2026-08-05"
    assert passage["content_hash"] == "abc123"
    assert passage["passage_hash"] == hashlib.sha256(passage["text"].encode()).hexdigest()
    assert result["corpus_hash"] == corpus_hash(package)


def test_search_excludes_after_cutoff_and_incomplete_table():
    future = corpus((SourceBlock(locator="block-1", section="Leases", text="Secret future lease"),),
                    filed=date(2026, 9, 2))
    assert not search_filing_evidence(future, "lease")["passages"]
    partial = corpus((SourceBlock(locator="block-1", section="Leases", text="lease | partial", truncated=True),))
    assert not search_filing_evidence(partial, "lease")["passages"]
    assert any("incomplete" in gap for gap in search_filing_evidence(partial, "lease")["gaps"])


def test_search_limits_refuse_overlimit_and_report_oversize_table():
    package = corpus((SourceBlock(locator="block-1", section="Leases", text="lease | " + "x" * 12010),))
    result = search_filing_evidence(package, "lease")
    assert not result["passages"]
    assert any("size limit" in gap for gap in result["gaps"])
    with pytest.raises(ValueError, match="limit"):
        search_filing_evidence(package, "lease", max_passages=4)
    with pytest.raises(ValueError, match="limit"):
        search_filing_evidence(package, "lease", max_chars=12001)


def test_no_match_is_not_disclosure_absence():
    result = search_filing_evidence(corpus((SourceBlock(locator="block-1", section="Cash", text="cash"),)), "leases")
    assert result["passages"] == []
    assert "not found in retained filings" in result["gaps"]

def test_search_prefers_all_query_words_over_note_heading_substrings():
    package = corpus((
        SourceBlock(locator="block-1", section="Note 6. Leases",
                    text="Lease balance table | current obligations"),
        SourceBlock(locator="block-2", section="Document",
                    text="Leases not yet commenced at the report date."),
    ))
    result = search_filing_evidence(package, "not yet commenced leases")
    assert result["passages"][0]["locator"] == "block-2"

def test_section_name_search_returns_heading_and_following_source_block():
    package = corpus((
        SourceBlock(locator="block-1", section="Document", text="Note 8. Operating Leases"),
        SourceBlock(locator="block-2", section="Document",
                    text="The company leases facilities and has future obligations."),
        SourceBlock(locator="block-3", section="Document ; Note 8. Operating Leases", text="Leases maturities | 2027 | 100"),
        SourceBlock(locator="block-4", section="Document", text="Note 9. Finance Leases"),
    ))
    result = search_filing_evidence(package, "leases")
    assert [p["locator"] for p in result["passages"]][:2] == ["block-1", "block-2"]
