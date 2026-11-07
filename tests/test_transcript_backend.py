import hashlib
import json
from datetime import UTC, date, datetime

import pytest

from tradingagents.dataflows.vendors.alpha_vantage import transcript as ts
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)


def filing_corpus(*, filed=date(2026, 11, 3), call_line=None):
    filing = FilingReference(
        cik="0001582961", accession="0001628280-26-069125", form="8-K",
        filed_date=filed, report_date=filed, primary_document="release.htm",
        items="2.02,9.01",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000162828026069125/release.htm",
    )
    url = filing.url.replace("release.htm", "ex99.htm")
    blocks = (
        SourceBlock(locator="block-1", section="Results",
                    text="DigitalOcean Announces Third Quarter 2026 Financial Results."),
        SourceBlock(locator="block-2", section="Conference Call Information",
                    text=call_line or "DigitalOcean will host a conference call today, November 3, 2026, at 8:00 a.m. ET."),
    )
    doc = FilingDocument(
        source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
        filing=filing, url=url, retrieved_at=datetime(2026, 11, 3, tzinfo=UTC),
        content_hash="sec-hash", blocks=blocks,
    )
    return DisclosurePackage(cik=filing.cik, as_of=date(2026, 11, 6), documents=(doc,))


def payload():
    return json.dumps({
        "symbol": "DOCN", "quarter": "2026Q3",
        "transcript": [
            {"speaker": "Operator", "title": "Operator", "content": "Welcome to the third quarter call.", "sentiment": "0.0"},
            {"speaker": "CEO", "title": "Chief Executive Officer", "content": "Revenue grew 40 percent.", "sentiment": "0.0"},
            {"speaker": "Operator", "title": "Operator", "content": "Your first question comes from Analyst A.", "sentiment": "0.0"},
            {"speaker": "Analyst A", "title": "Analyst", "content": "What happened to capacity?", "sentiment": "0.0"},
            {"speaker": "CEO", "title": "Chief Executive Officer", "content": "Capacity has 75 megawatts active.", "sentiment": "0.0"},
        ],
    })


def test_sec_exhibit_establishes_actual_call_date_and_pin():
    resolved = ts.resolve_sec_call_date(filing_corpus(), "2026Q3", "2026-11-06")
    assert resolved["status"] == "dated"
    assert resolved["call_date"] == "2026-11-03"
    assert resolved["locator"] == "block-2"
    assert resolved["content_hash"] == "sec-hash"


def test_future_and_undated_call_excluded_without_fiscal_quarter_proxy():
    future = ts.parse_transcript_response(
        payload(), "DOCN", "2026Q3", "2026-11-02", filing_corpus()
    )
    assert future["status"] == "unavailable"
    assert not future["turns"]
    undated = ts.parse_transcript_response(
        payload(), "DOCN", "2026Q3", "2026-11-06",
        filing_corpus(call_line="A conference call is planned."),
    )
    assert undated["status"] == "unavailable"
    assert not undated["turns"]


def test_transcript_source_is_unverified_and_qa_search_whole_turns():
    record = ts.parse_transcript_response(
        payload(), "DOCN", "2026Q3", "2026-11-06", filing_corpus()
    )
    assert record["status"] == "ready"
    assert record["label"] == "vendor transcript, wording unverified"
    assert len(record["turns"]) == 5
    remarks = ts.prepared_remarks_excerpt(record)
    assert "Revenue grew 40 percent" in remarks["text"]
    assert "What happened to capacity" not in remarks["text"]
    found = ts.search_transcript_evidence(record, "capacity")
    assert found["passages"]
    assert all(p["section"] == "Q&A" for p in found["passages"])
    assert any("75 megawatts" in p["text"] for p in found["passages"])
    assert all(p["passage_hash"] == hashlib.sha256(p["text"].encode()).hexdigest() for p in found["passages"])
    with pytest.raises(ValueError, match="limit"):
        ts.search_transcript_evidence(record, "capacity", max_passages=4)


def test_provider_notice_is_unavailable_without_exposing_notice():
    raw = json.dumps({"Information": "Premium access required for secret-key-123"})
    result = ts.parse_transcript_response(raw, "DOCN", "2026Q3", "2026-11-06", filing_corpus())
    assert result["status"] == "unavailable"
    assert "premium" in result["reason"].lower()
    assert "secret-key-123" not in json.dumps(result)


def test_missing_date_prevents_fetch_even_if_network_allowed(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ts, "_request_transcript", lambda *a, **k: pytest.fail("provider call forbidden"))
    result = ts.get_transcript_evidence(
        "DOCN", "2026Q3", "2026-11-06",
        filing_corpus=filing_corpus(call_line="A conference call is planned."),
        allow_network=True,
    )
    assert result["status"] == "unavailable"
    assert not list(tmp_path.rglob("*.json"))


def test_cache_preserves_provider_text_hash_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    calls = []
    monkeypatch.setattr(ts, "_request_transcript", lambda *a, **k: calls.append((a, k)) or payload())
    first = ts.get_transcript_evidence(
        "DOCN", "2026Q3", "2026-11-06", filing_corpus=filing_corpus(),
        allow_network=True,
    )
    second = ts.get_transcript_evidence(
        "DOCN", "2026Q3", "2026-11-06", filing_corpus=filing_corpus(),
        allow_network=False,
    )
    assert first["content_hash"] == hashlib.sha256(payload().encode()).hexdigest()
    assert first["content_hash"] == second["content_hash"]
    assert len(calls) == 1

def test_call_start_does_not_establish_full_transcript_availability():
    for cutoff in ("2026-11-03T12:59:59+00:00", "2026-11-03T13:00:00+00:00",
                   "2026-11-04T04:59:59+00:00", "2026-11-04T04:59:59.500000+00:00"):
        result = ts.resolve_sec_call_date(filing_corpus(), "2026Q3", "2026-11-03",
                                          cutoff_utc=cutoff)
        assert result["status"] == "future"
    after = ts.resolve_sec_call_date(filing_corpus(), "2026Q3", "2026-11-03",
                                     cutoff_utc="2026-11-04T04:59:59.999999+00:00")
    assert after["status"] == "dated"
    assert after["available_at_utc"] == "2026-11-04T04:59:59.999999+00:00"
    assert "publication time unavailable" in after["availability_basis"]


def test_date_only_call_uses_same_conservative_eastern_day_end():
    corpus = filing_corpus(call_line="DigitalOcean will host a conference call on November 3, 2026.")
    early = ts.resolve_sec_call_date(corpus, "2026Q3", "2026-11-03",
                                     cutoff_utc="2026-11-04T04:59:59.500000+00:00")
    late = ts.resolve_sec_call_date(corpus, "2026Q3", "2026-11-03",
                                    cutoff_utc="2026-11-04T04:59:59.999999+00:00")
    assert early["status"] == "future"
    assert late["status"] == "dated"
    assert "publication time unavailable" in late["availability_basis"]


def test_same_quarter_end_without_matching_release_quarter_is_undated():
    corpus = filing_corpus()
    document = corpus.documents[0]
    altered = document.model_copy(update={
        "blocks": (
            SourceBlock(locator="block-1", section="Results",
                        text="Results for the second quarter ended June 30, 2026."),
            document.blocks[1],
        )
    })
    corpus = corpus.model_copy(update={"documents": (altered,)})
    assert ts.resolve_sec_call_date(corpus, "2026Q3", "2026-11-06")["status"] == "undated"


def test_large_qa_turn_is_omitted_whole_with_gap():
    raw = json.loads(payload())
    raw["transcript"][4]["content"] = "Capacity " + "x" * 12001
    record = ts.parse_transcript_response(
        json.dumps(raw), "DOCN", "2026Q3", "2026-11-06", filing_corpus()
    )
    result = ts.search_transcript_evidence(record, "capacity")
    assert all(len(p["text"]) <= 12000 for p in result["passages"])
    assert any("turn-5" in gap and "omitted whole turn" in gap for gap in result["gaps"])

def test_prepared_excerpt_is_contiguous_and_labels_partial_turn():
    raw = json.loads(payload())
    raw["transcript"][1]["content"] = "CEO opening. " + "x" * 5000
    record = ts.parse_transcript_response(
        json.dumps(raw), "DOCN", "2026Q3", "2026-11-06", filing_corpus()
    )
    excerpt = ts.prepared_remarks_excerpt(record)
    assert [turn["locator"] for turn in excerpt["turns"]] == ["turn-1", "turn-2"]
    assert excerpt["turns"][-1]["truncated"] is True
    assert len(excerpt["turns"][-1]["text"]) < len(raw["transcript"][1]["content"])
    assert "partial" in " ".join(excerpt["gaps"])

def test_changed_cache_is_unavailable_without_replacement(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ts, "_request_transcript", lambda *a, **k: payload())
    ts.get_transcript_evidence(
        "DOCN", "2026Q3", "2026-11-06", filing_corpus=filing_corpus(),
        allow_network=True,
    )
    path = next(tmp_path.rglob("*.json"))
    cached = json.loads(path.read_text())
    cached["raw"] = cached["raw"].replace("75 megawatts", "90 megawatts")
    path.write_text(json.dumps(cached))
    monkeypatch.setattr(ts, "_request_transcript", lambda *a, **k: pytest.fail("must not refetch"))
    result = ts.get_transcript_evidence(
        "DOCN", "2026Q3", "2026-11-06", filing_corpus=filing_corpus(),
        allow_network=True,
    )
    assert result["status"] == "unavailable"
    assert "cache" in result["reason"].lower()

def test_free_quota_notice_with_premium_word_is_rate_limit():
    notice = json.dumps({
        "Information": "Your API key reached 25 requests per day on the free tier. Premium plans are available."
    })
    result = ts.parse_transcript_response(
        notice, "DOCN", "2026Q3", "2026-11-06", filing_corpus()
    )
    assert "rate limit" in result["reason"].lower()
    assert "premium entitlement" not in result["reason"].lower()


def test_latest_quarter_comes_from_explicit_release_words_only():
    selected = ts.select_latest_eligible_call(filing_corpus(), "2026-11-06")
    assert selected["status"] == "ready"
    assert selected["fiscal_quarter"] == "2026Q3"
    corpus = filing_corpus()
    document = corpus.documents[0]
    altered = document.model_copy(update={
        "blocks": (
            SourceBlock(locator="block-1", section="Results",
                        text="DigitalOcean reported results for the period ended September 30, 2026."),
            document.blocks[1],
        ),
    })
    unsupported = ts.select_latest_eligible_call(
        corpus.model_copy(update={"documents": (altered,)}), "2026-11-06"
    )
    assert unsupported["status"] == "unavailable"
    assert "fiscal quarter" in unsupported["reason"].lower()


def test_transcript_transport_timeout_is_unavailable(monkeypatch, tmp_path):
    import requests

    monkeypatch.setattr(ts, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ts, "_request_transcript", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout("synthetic")))
    result = ts.get_transcript_evidence(
        "DOCN", "2026Q3", "2026-11-06",
        filing_corpus=filing_corpus(), allow_network=True,
    )
    assert result["status"] == "unavailable"
    assert "provider" in result["reason"].lower()
    assert not list(tmp_path.rglob("*.json"))


def test_transcript_request_uses_one_scrubbed_call_and_classifies_free_quota(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ts, "get_api_key", lambda: "fake-key")
    calls = []

    class Response:
        text = json.dumps({
            "Information": "Your API key hit 25 requests per day. Premium plans offer higher limits."
        })

    def scrubbed(url, *, params, timeout, secret):
        calls.append((url, params, timeout, secret))
        return Response()

    monkeypatch.setattr(ts, "get_scrubbed", scrubbed)
    result = ts.get_transcript_evidence(
        "DOCN", "2026Q3", "2026-11-06",
        filing_corpus=filing_corpus(), allow_network=True,
    )
    assert result["status"] == "unavailable"
    assert "rate limit" in result["reason"].lower()
    assert len(calls) == 1
    assert calls[0][1]["function"] == "EARNINGS_CALL_TRANSCRIPT"
    assert calls[0][1]["quarter"] == "2026Q3"
    assert calls[0][1]["apikey"] == calls[0][3] == "fake-key"


def test_latest_eligible_call_beats_older_quarter_without_calendar_inference():
    current = filing_corpus()
    doc = current.documents[0]
    old_filing = doc.filing.model_copy(update={
        "accession": "0001628280-26-050000",
        "filed_date": date(2026, 8, 5),
        "report_date": date(2026, 8, 5),
        "url": doc.filing.url.replace("000162828026069125", "000162828026050000"),
    })
    old_url = old_filing.url.replace("release.htm", "ex99.htm")
    older = doc.model_copy(update={
        "filing": old_filing, "url": old_url,
        "source_id": "sec-document-" + hashlib.sha256(old_url.encode()).hexdigest(),
        "blocks": (
            SourceBlock(locator="block-1", section="Results",
                        text="DigitalOcean Announces Second Quarter 2026 Financial Results."),
            SourceBlock(locator="block-2", section="Call",
                        text="DigitalOcean will host a conference call on August 5, 2026."),
        ),
    })
    corpus = current.model_copy(update={"documents": (older, doc)})
    selected = ts.select_latest_eligible_call(corpus, "2026-11-06")
    assert selected["fiscal_quarter"] == "2026Q3"


def test_release_footnote_about_old_quarter_does_not_select_old_call():
    corpus = filing_corpus()
    doc = corpus.documents[0]
    filler = tuple(
        SourceBlock(locator=f"block-{i}", section="Other", text="Financial details.")
        for i in range(3, 22)
    )
    footnote = SourceBlock(
        locator="block-22", section="Footnote",
        text="Beginning in Fourth Quarter 2025, earnings results used a revised definition.",
    )
    corpus = corpus.model_copy(update={
        "documents": (doc.model_copy(update={
            "blocks": (*doc.blocks, *filler, footnote),
        }),),
    })
    assert ts.select_latest_eligible_call(corpus, "2026-11-06")["fiscal_quarter"] == "2026Q3"


def test_explicit_earnings_call_in_primary_8k_is_authoritative_too():
    corpus = filing_corpus()
    doc = corpus.documents[0]
    doc = doc.model_copy(update={
        "url": doc.filing.url,
        "source_id": "sec-document-" + hashlib.sha256(doc.filing.url.encode()).hexdigest(),
    })
    corpus = corpus.model_copy(update={"documents": (doc,)})
    selected = ts.select_latest_eligible_call(corpus, "2026-11-06")
    assert selected["status"] == "ready"
    assert selected["date_evidence"]["source_id"] == doc.source_id


def test_older_quarter_in_late_footnote_cannot_borrow_current_call_date():
    corpus = filing_corpus()
    doc = corpus.documents[0]
    filler = tuple(SourceBlock(locator=f"block-{i}", section="Other", text="Financial details.")
                   for i in range(3, 22))
    old = SourceBlock(locator="block-22", section="Footnotes",
                      text="Results of the second quarter 2026 are also discussed.")
    doc = doc.model_copy(update={"blocks": (*doc.blocks, *filler, old)})
    corpus = corpus.model_copy(update={"documents": (doc,)})
    assert ts.resolve_sec_call_date(corpus, "2026Q2", "2026-11-06")["status"] == "undated"
