import hashlib
from datetime import UTC, date, datetime

import pytest

from tradingagents.dataflows.filing_search import (
    corpus_hash,
    passage_matches_query,
    query_content_terms,
    search_filing_evidence,
)
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


def test_named_2026_notes_exclude_2030_near_miss_and_retrieve_terms():
    package = corpus((
        SourceBlock(locator="block-1", section="Notes", text="The 2030 Convertible Notes may be settled in cash, shares, or a combination. As of September 30, 2026."),
        SourceBlock(locator="block-2", section="Notes", text="The 2026 Convertible Notes have an initial conversion price of $178.51."),
        SourceBlock(locator="block-3", section="Notes", text="The 2026 Convertible Notes mature December 1, 2026 and may be settled in cash, shares, or a combination."),
    ))
    result = search_filing_evidence(package, "How will the 2026 convertible notes settle in cash or shares, and what are the conversion price and maturity date?")
    assert {p["locator"] for p in result["passages"]} == {"block-2", "block-3"}


def test_named_notes_missing_and_incidental_year_are_not_answers():
    package = corpus((SourceBlock(locator="block-1", section="Notes", text="The 2030 Convertible Notes may settle in cash or shares at September 30, 2026."),))
    result = search_filing_evidence(package, "How will the 2026 Convertible Notes settle?")
    assert result["passages"] == []
    assert "no passage names the 2026 Convertible Notes" in result["gaps"]
    assert search_filing_evidence(package, "How will convertible notes settle at September 30, 2026?")["passages"]


def test_two_named_notes_keep_both_identities_and_report_missing_one():
    package = corpus((
        SourceBlock(locator="block-1", section="Notes", text="The 2026 Convertible Notes affect diluted shares."),
        SourceBlock(locator="block-2", section="Notes", text="The 2030 Convertible Notes affect diluted shares."),
    ))
    result = search_filing_evidence(package, "Which 2026 and 2030 convertible notes affect diluted shares?", max_passages=1)
    assert len(result["passages"]) == 1
    assert any("omitted by search passage limit" in gap for gap in result["gaps"])
    result = search_filing_evidence(package, "Which 2026 and 2030 convertible notes affect diluted shares?")
    assert {p["locator"] for p in result["passages"]} == {"block-1", "block-2"}


def test_named_note_oversize_and_truncated_material_report_omission():
    large = corpus((SourceBlock(locator="block-1", section="Notes", text="2026 Convertible Notes " + "x" * 12000),))
    result = search_filing_evidence(large, "2026 Convertible Notes")
    assert any("size limit" in gap for gap in result["gaps"])
    assert not any("no passage names" in gap for gap in result["gaps"])
    partial = corpus((SourceBlock(locator="block-1", section="Notes", text="2026 Convertible Notes settlement", truncated=True),))
    result = search_filing_evidence(partial, "2026 Convertible Notes")
    assert any("incomplete" in gap for gap in result["gaps"])
    assert not any("no passage names" in gap for gap in result["gaps"])


def test_named_notes_prefer_latest_eligible_filing_and_respect_cutoff_and_issuer():
    old = corpus((SourceBlock(locator="block-1", section="Notes", text="The 2026 Convertible Notes cash shares conversion price and maturity date are discussed here."),), filed=date(2026, 8, 5))
    latest = corpus((SourceBlock(locator="block-2", section="Notes", text="The 2026 Convertible Notes have a conversion price of $178.51."),), filed=date(2026, 8, 6))
    query = "2026 Convertible Notes cash shares conversion price and maturity date"
    combined = old.model_copy(update={"documents": old.documents + latest.documents})
    assert search_filing_evidence(combined, query, max_passages=1)["passages"][0]["locator"] == "block-2"
    future = corpus((SourceBlock(locator="block-1", section="Notes", text="2026 Convertible Notes settle in cash."),), filed=date(2026, 9, 2))
    assert search_filing_evidence(future, query)["passages"] == []
    wrong = old.model_copy(update={"cik": "0000000001"})
    assert search_filing_evidence(wrong, query)["passages"] == []


def test_question_shaped_rpo_queries_rank_q3_note_above_lease_and_release():
    from tests.docn_workflow_fixture import source_json

    package = DisclosurePackage.model_validate(source_json("cfae95e9-corpus.json.gz"))
    questions = (
        "What does the 10-Q say caused remaining performance obligations to decline "
        "from June 30 to September 30, 2026?",
        "What reason does the 10-Q give for the decrease in remaining performance "
        "obligations, and what portion is expected to be recognized within the next 12 months?",
    )
    for question in questions:
        first = search_filing_evidence(package, question)["passages"][0]
        assert first["locator"] == "block-148"
        assert first["filing_accession"] == "0001628280-26-069141"
        assert "$799,707" in first["text"]
        assert "$345,111" in first["text"]


def test_docn_keyword_queries_still_find_rpo_and_uncommenced_leases():
    from tests.docn_workflow_fixture import source_json

    package = DisclosurePackage.model_validate(source_json("cfae95e9-corpus.json.gz"))
    assert search_filing_evidence(package, "remaining performance obligations next 12 months")["passages"][0]["locator"] == "block-148"
    assert search_filing_evidence(package, "leases not yet commenced")["passages"][0]["locator"] == "block-218"


def test_content_terms_and_relevance_use_body_with_meaningful_constraints():
    assert query_content_terms("What does the 10-Q say about RPO from June 30, 2026?") == (
        "remaining", "performance", "obligations",
    )
    assert query_content_terms("2026 Convertible Notes") == ("2026", "convertible", "notes")
    assert query_content_terms("next 12 months") == ("next", "12", "months")
    assert query_content_terms("2026") == ("2026",)
    assert passage_matches_query("RPO next 12 months", "Remaining performance obligation is due over the next 12 months.")
    assert not passage_matches_query("RPO decline next 12 months", "Remaining performance obligations are due over the next 12 months.")
    assert not passage_matches_query("not yet commenced leases", "Lease commitments have commenced.")


def test_date_only_queries_keep_month_day_and_year():
    assert query_content_terms("June 30, 2026") == ("june", "30", "2026")
    assert query_content_terms("June") == ("june",)
    assert query_content_terms("2026") == ("2026",)


def test_mixed_queries_drop_iso_slash_and_day_first_dates():
    expected = ("remaining", "performance", "obligations", "decline")
    assert query_content_terms("RPO decline from 2026-06-30 to 2026-09-30") == expected
    assert query_content_terms("RPO decline from 2026/06/30 to 2026/09/30") == expected
    assert query_content_terms("RPO decline from 30 June 2026 to 30 September 2026") == expected
    assert query_content_terms("2026-06-30") == ("2026", "06", "30")
    assert query_content_terms("30 June 2026") == ("30", "june", "2026")
    assert query_content_terms("2026 Convertible Notes next 12 months") == (
        "2026", "convertible", "notes", "next", "12", "months",
    )


def test_recorded_rpo_question_with_iso_dates_still_ranks_q3_note_first():
    from tests.docn_workflow_fixture import source_json

    package = DisclosurePackage.model_validate(source_json("cfae95e9-corpus.json.gz"))
    query = (
        "What does the 10-Q say caused remaining performance obligations to decline "
        "from 2026-06-30 to 2026-09-30?"
    )
    first = search_filing_evidence(package, query)["passages"][0]
    assert first["locator"] == "block-148"
    assert first["filing_accession"] == "0001628280-26-069141"
