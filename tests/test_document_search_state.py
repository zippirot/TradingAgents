import copy
import hashlib
from datetime import UTC, date, datetime

import pytest
from langchain_core.messages import AIMessage

from tradingagents.agents.document_access import (
    merge_search_traces,
    prepare_document_sources,
    retained_search_packages,
    run_document_search,
    validated_document_corpus,
)
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)


def package():
    url = "https://www.sec.gov/Archives/edgar/data/1582961/000158296126000002/q.htm"
    filing = FilingReference(
        cik="0001582961", accession="0001582961-26-000002", form="10-Q",
        filed_date=date(2026, 8, 5), report_date=date(2026, 6, 30),
        primary_document="q.htm", items="", url=url,
    )
    return DisclosurePackage(
        cik=filing.cik, as_of=date(2026, 9, 1),
        documents=(FilingDocument(
            source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
            filing=filing, url=url, retrieved_at=datetime(2026, 8, 5, tzinfo=UTC),
            content_hash="abc123",
            blocks=(SourceBlock(
                locator="block-1", section="Results",
                text="Third Quarter 2026 revenue was $50 million.",
                currency="USD", currency_locator="block-1",
            ),),
        ),),
    )


def state(pkg=None):
    pkg = pkg or package()
    return {
        "company_of_interest": "NVDA", "trade_date": "2026-09-01",
        "asset_type": "stock",
        "analysis_clock": {"cutoff_utc": "2026-09-01T23:59:59+00:00"},
        "issuer_identity": {"ticker": "NVDA", "cik": pkg.cik, "as_of": "2026-09-01"},
        "filing_evidence": pkg.model_dump(mode="json"),
        "document_sources": {
            "schema_version": 1, "status": "ready", "ticker": "NVDA",
            "as_of": "2026-09-01", "asset_type": "stock",
            "analysis_clock": {"cutoff_utc": "2026-09-01T23:59:59+00:00"},
            "cik": pkg.cik, "corpus": pkg.model_dump(mode="json"),
            "corpus_hash": corpus_hash(pkg), "reason": "",
        },
        "document_search_trace": {},
        "document_search_role": "fundamentals", "messages": [],
    }


def call(s, query, call_id):
    return run_document_search(s, query, role="fundamentals", call_id=call_id)


def test_prepare_resume_and_bounded_brief_unchanged(monkeypatch):
    s = state()
    s.pop("document_sources")
    s["shared_source_brief"] = "bounded text"
    seen = []
    def fetch(ticker, as_of, *, bounded_package=None):
        seen.append(bounded_package)
        return package()
    monkeypatch.setattr("tradingagents.dataflows.vendors.sec_documents.get_filing_search_evidence", fetch)
    prepared = prepare_document_sources(s, ["fundamentals", "news"])
    assert prepared["document_sources"]["status"] == "ready"
    assert "shared_source_brief" not in prepared
    assert s["shared_source_brief"] == "bounded text"
    assert seen == [package()]
    s.update(prepared)
    assert prepare_document_sources(s, ["fundamentals", "news"]) == {}
    assert len(seen) == 1


def test_nonapplicable_and_vendor_failure(monkeypatch):
    s = state()
    s.pop("document_sources")
    def fail(*args, **kwargs):
        raise AssertionError("SEC called")
    monkeypatch.setattr("tradingagents.dataflows.vendors.sec_documents.get_filing_search_evidence", fail)
    assert prepare_document_sources(s, ["market"])["document_sources"]["status"] == "not_applicable"
    s["asset_type"] = "crypto"
    assert prepare_document_sources(s, ["fundamentals"])["document_sources"]["status"] == "not_applicable"
    from tradingagents.dataflows.errors import VendorUnavailableError
    def unavailable(*args, **kwargs):
        raise VendorUnavailableError("SEC unavailable")
    monkeypatch.setattr("tradingagents.dataflows.vendors.sec_documents.get_filing_search_evidence", unavailable)
    s["asset_type"] = "stock"
    record = prepare_document_sources(s, ["fundamentals"])["document_sources"]
    assert record["status"] == "unavailable" and record["corpus"] is None
    assert "SEC unavailable" in record["reason"]


def test_scope_future_duplicate_source_and_hash_tamper_fail_closed():
    assert validated_document_corpus(state()) == package()
    assert validated_document_corpus({"trade_date": "2026-09-01"}) is None
    for mutate in (
        lambda s: s["document_sources"].update(corpus_hash="wrong"),
        lambda s: s.update(company_of_interest="AMD"),
        lambda s: s["document_sources"]["corpus"]["documents"][0]["filing"].update(filed_date="2026-09-02"),
        lambda s: s["document_sources"]["corpus"]["documents"].append(
            copy.deepcopy(s["document_sources"]["corpus"]["documents"][0])),
    ):
        s = state()
        mutate(s)
        if s["document_sources"]["corpus_hash"] != "wrong":
            s["document_sources"]["corpus_hash"] = corpus_hash(
                DisclosurePackage.model_validate(s["document_sources"]["corpus"])
            )
        with pytest.raises(ValueError):
            validated_document_corpus(s)


def test_search_journal_reuses_exact_call_and_counts_all_attempts():
    s = state()
    first = call(s, "revenue", "id1")
    assert first["result"]["status"] == "ok" and first["result"]["counted"] is True
    s["document_search_trace"] = first["document_search_trace"]
    assert call(s, "revenue", "id1") == first
    with pytest.raises(ValueError, match="query"):
        call(s, "different", "id1")
    for query, call_id, status in (
        ("leases", "id2", "not_found"), ("", "id3", "invalid_query"),
        ("more", "id4", "limit_reached"),
    ):
        update = call(s, query, call_id)
        assert update["result"]["status"] == status
        if call_id != "id4":
            s["document_search_trace"] = merge_search_traces(
                s["document_search_trace"], update["document_search_trace"]
            )


def test_parallel_batch_limit_and_duplicate_ids():
    s = state()
    s["messages"] = [AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "revenue"}, "id": f"id{n}"}
        for n in range(4)
    ])]
    assert call(s, "revenue", "id2")["result"]["status"] == "ok"
    assert call(s, "revenue", "id3")["result"]["status"] == "limit_reached"
    s["messages"] = [AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "revenue"}, "id": "same"},
        {"name": "search_documents", "args": {"query": "revenue"}, "id": "same"},
    ])]
    with pytest.raises(ValueError, match="duplicate"):
        call(s, "revenue", "same")


def test_merge_idempotence_and_conflict():
    entry = call(state(), "revenue", "id1")["document_search_trace"]
    assert merge_search_traces(entry, entry) == entry
    other = copy.deepcopy(entry)
    other["fundamentals:id1"]["query"] = "changed"
    with pytest.raises(ValueError, match="conflict"):
        merge_search_traces(entry, other)


def test_retained_packages_exact_passage_and_fabrication():
    s = state()
    s["document_search_trace"] = call(s, "revenue", "id1")["document_search_trace"]
    retained = retained_search_packages(s)
    assert len(retained) == 1
    assert retained[0].documents[0].blocks == package().documents[0].blocks
    for mutate in (
        lambda p: p.update(locator="invented"),
        lambda p: p.update(text="Third Quarter 2026 revenue was $60 million."),
        lambda p: p.update(content_hash="wrong"),
        lambda p: p.update(passage_hash="wrong"),
    ):
        changed = copy.deepcopy(s)
        mutate(changed["document_search_trace"]["fundamentals:id1"]["passages"][0])
        with pytest.raises(ValueError):
            retained_search_packages(changed)



def test_retained_quote_passes_disclosure_validator_but_paraphrase_does_not():
    import json

    from tradingagents.dataflows.disclosure_evidence import parse_disclosure_report

    s = state()
    s["document_search_trace"] = call(s, "revenue", "id1")["document_search_trace"]
    packages = retained_search_packages(s)
    doc = packages[0].documents[0]
    block = doc.blocks[0]
    blocks = {(doc.source_id, block.locator): block.section + "\n" + block.text}
    claim = {
        "source_id": doc.source_id, "locator": block.locator,
        "metric": "revenue", "value": "50", "unit": "million",
        "period": "Third Quarter 2026", "kind": "historical",
        "quote": block.text,
    }
    report = "~~~disclosures\n" + json.dumps([claim]) + "\n~~~"
    report = report.replace("~~~", "```")
    good = parse_disclosure_report(
        report, blocks, packages=[item.model_dump(mode="json") for item in packages]
    )
    assert len(good.claims) == 1 and not good.rejected
    claim["quote"] = "Revenue in the third quarter was fifty million dollars."
    bad = parse_disclosure_report(
        "~~~disclosures\n".replace("~~~", "```") + json.dumps([claim]) + "\n```",
        blocks, packages=[item.model_dump(mode="json") for item in packages],
    )
    assert not bad.claims and any("exact retrieved source span" in reason for reason in bad.rejected)



def test_resume_refuses_passages_without_corpus_and_duplicate_active_id():
    s = state()
    s["document_search_trace"] = call(s, "revenue", "id1")["document_search_trace"]
    s.pop("document_sources")
    with pytest.raises(ValueError, match="without retained corpus"):
        call(s, "revenue", "id1")
    s = state()
    s["document_search_trace"] = call(s, "revenue", "id1")["document_search_trace"]
    s["messages"] = [AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "revenue"}, "id": "id1"},
        {"name": "search_documents", "args": {"query": "revenue"}, "id": "id1"},
    ])]
    with pytest.raises(ValueError, match="duplicate"):
        call(s, "revenue", "id1")



def test_date_only_scope_uses_existing_cutoff_rules_and_malformed_clock_fails(monkeypatch):
    from tradingagents.dataflows.date_window import resolve_analysis_cutoff

    s = state()
    s.pop("document_sources")
    s.pop("analysis_clock")
    monkeypatch.setattr(
        "tradingagents.dataflows.vendors.sec_documents.get_filing_search_evidence",
        lambda *args, **kwargs: package(),
    )
    prepared = prepare_document_sources(s, ["fundamentals"])
    s.update(prepared)
    assert validated_document_corpus(s) == package()
    assert resolve_analysis_cutoff(s["trade_date"])["analysis_timezone"] == "UTC"
    s["analysis_clock"] = {"cutoff_utc": "not-a-time"}
    with pytest.raises(ValueError, match="cutoff|scope"):
        validated_document_corpus(s)


def test_resumed_journal_tamper_is_refused_before_tool_result():
    s = state()
    s["document_search_trace"] = call(s, "revenue", "id1")["document_search_trace"]
    s["document_search_trace"]["fundamentals:id1"]["passages"][0]["text"] = "invented"
    with pytest.raises(ValueError, match="passage"):
        call(s, "revenue", "id1")



def test_exact_clock_uses_local_analysis_day_and_refuses_earlier_filing():
    s = state()
    s["analysis_clock"] = {
        "analysis_timezone": "America/Denver",
        "cutoff_utc": "2026-09-02T05:59:59+00:00",
    }
    s["document_sources"]["analysis_clock"] = dict(s["analysis_clock"])
    assert validated_document_corpus(s) == package()
    s["analysis_clock"]["cutoff_utc"] = "2026-08-04T23:00:00+00:00"
    s["document_sources"]["analysis_clock"] = dict(s["analysis_clock"])
    with pytest.raises(ValueError, match="filing date"):
        validated_document_corpus(s)
    s = state()
    s.pop("document_sources")
    s["analysis_clock"] = {"cutoff_utc": "not-a-time"}
    with pytest.raises(ValueError, match="cutoff"):
        prepare_document_sources(s, ["fundamentals"])



def test_resume_rejects_forged_over_budget_and_impossible_empty_success():
    s = state()
    trace = {}
    for i in range(4):
        trace.update(call(state(), "revenue", f"forged-{i}")["document_search_trace"])
    s["document_search_trace"] = trace
    with pytest.raises(ValueError, match="call limit"):
        retained_search_packages(s)
    with pytest.raises(ValueError, match="call limit"):
        call(s, "revenue", "forged-0")
    s = state()
    bad = call(s, "revenue", "one")["document_search_trace"]
    bad["fundamentals:one"].update(passages=[], counted=False)
    s["document_search_trace"] = bad
    with pytest.raises(ValueError, match="counted status"):
        call(s, "revenue", "one")


def test_same_day_filing_with_only_a_date_is_withheld_at_explicit_intraday_cutoff(monkeypatch):
    s = state()
    pkg = package()
    doc = pkg.documents[0]
    doc = doc.model_copy(update={"filing": doc.filing.model_copy(update={"filed_date": date(2026, 9, 1)})})
    pkg = pkg.model_copy(update={"documents": (doc,)})
    s["analysis_clock"] = {"cutoff_utc": "2026-09-01T10:00:00+00:00"}
    s.pop("document_sources")
    monkeypatch.setattr("tradingagents.dataflows.vendors.sec_documents.get_filing_search_evidence",
                        lambda *a, **k: pkg)
    prepared = prepare_document_sources(s, ["fundamentals"])
    s.update(prepared)
    assert validated_document_corpus(s).documents == ()
    assert "publication time unavailable" in prepared["document_sources"]["corpus"]["gaps"][0]
    assert call(s, "revenue", "one")["result"]["passages"] == []
    for cutoff in ("2026-09-01T23:59:59+00:00", "2026-09-01T23:59:59.500000+00:00"):
        boundary = {**s, "analysis_clock": {"cutoff_utc": cutoff}}
        boundary.pop("document_sources")
        assert prepare_document_sources(boundary, ["fundamentals"])["document_sources"]["corpus"]["documents"] == []
    # The normal date-only day-end analysis still includes same-date filing text.
    s.pop("document_sources")
    s["analysis_clock"] = {}
    prepared = prepare_document_sources(s, ["fundamentals"])
    assert prepared["document_sources"]["corpus"]["documents"]
