import hashlib
import json
from datetime import UTC, date, datetime

import pytest

from tradingagents.agents import transcript_access as access
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.alpha_vantage import transcript as vendor
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)


def state_with_sec_corpus():
    filing = FilingReference(
        cik="0001582961", accession="0001628280-26-069125", form="8-K",
        filed_date=date(2026, 11, 3), report_date=date(2026, 11, 3),
        primary_document="release.htm", items="2.02,9.01",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000162828026069125/release.htm",
    )
    url = filing.url.replace("release.htm", "ex99.htm")
    doc = FilingDocument(
        source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
        filing=filing, url=url, retrieved_at=datetime(2026, 11, 3, tzinfo=UTC),
        content_hash="sec-hash",
        blocks=(
            SourceBlock(locator="block-1", section="Results",
                        text="DigitalOcean Announces Third Quarter 2026 Financial Results."),
            SourceBlock(locator="block-2", section="Conference Call",
                        text="DigitalOcean will host a conference call today, November 3, 2026, at 8:00 a.m. ET."),
        ),
    )
    corpus = DisclosurePackage(cik=filing.cik, as_of=date(2026, 11, 6), documents=(doc,))
    clock = {
        "analysis_timezone": "America/Denver",
        "cutoff_utc": "2026-11-07T06:59:59+00:00",
    }
    scope = {
        "schema_version": 1, "ticker": "DOCN", "as_of": "2026-11-06",
        "asset_type": "stock", "analysis_clock": clock,
    }
    state = {
        "company_of_interest": "DOCN", "trade_date": "2026-11-06",
        "asset_type": "stock", "analysis_clock": clock,
        "issuer_identity": {"cik": filing.cik},
        "document_sources": {
            **scope, "status": "ready", "cik": filing.cik,
            "corpus": corpus.model_dump(mode="json"),
            "corpus_hash": corpus_hash(corpus), "reason": "",
        },
    }
    return state, corpus


def transcript_record(corpus):
    raw = json.dumps({
        "symbol": "DOCN", "quarter": "2026Q3",
        "transcript": [
            {"speaker": "Operator", "title": "Operator", "content": "Welcome to the call."},
            {"speaker": "CEO", "title": "CEO", "content": "Revenue grew this quarter."},
            {"speaker": "Operator", "title": "Operator", "content": "Your first question comes from Analyst."},
            {"speaker": "Analyst", "title": "Analyst", "content": "What changed in capacity?"},
        ],
    })
    return vendor.parse_transcript_response(
        raw, "DOCN", "2026Q3", "2026-11-06", corpus,
        cutoff_utc="2026-11-07T06:59:59+00:00",
    )


def test_fresh_acquisition_pins_corpus_date_and_labeled_context(monkeypatch):
    state, corpus = state_with_sec_corpus()
    calls = []
    monkeypatch.setattr(
        access.vendor_transcript, "get_latest_transcript_evidence",
        lambda *a, **k: calls.append((a, k)) or transcript_record(corpus),
    )
    update = access.prepare_transcript_sources(state, {"fundamentals"})
    wrapper = update["transcript_sources"]
    assert len(calls) == 1
    assert calls[0][1]["allow_network"] is True
    assert wrapper["status"] == "ready"
    assert wrapper["cik"] == corpus.cik
    assert wrapper["corpus_hash"] == state["document_sources"]["corpus_hash"]
    assert wrapper["date_evidence"]["locator"] == "block-2"
    state.update(update)
    assert access.validated_transcript_record(state)["fiscal_quarter"] == "2026Q3"
    context = access.transcript_analyst_context(state)
    assert "vendor transcript, wording unverified" in context
    assert "Revenue grew this quarter" in context
    assert "transcript:" in context
    assert "sec-document-" in context


def test_resume_never_fetches_and_detects_changed_record_or_corpus(monkeypatch):
    state, corpus = state_with_sec_corpus()
    monkeypatch.setattr(access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: transcript_record(corpus))
    state.update(access.prepare_transcript_sources(state, {"news"}))
    monkeypatch.setattr(access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: pytest.fail("resume must not fetch"))
    assert access.prepare_transcript_sources(state, {"news"}) == {}
    state["transcript_sources"]["record"]["turns"][1]["text"] = "altered"
    with pytest.raises(ValueError, match="transcript|record"):
        access.prepare_transcript_sources(state, {"news"})
    state, corpus = state_with_sec_corpus()
    monkeypatch.setattr(access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: transcript_record(corpus))
    state.update(access.prepare_transcript_sources(state, {"news"}))
    state["document_sources"]["corpus"]["documents"][0]["blocks"][1]["text"] = "changed"
    with pytest.raises(ValueError, match="corpus"):
        access.validated_transcript_record(state)


def test_failed_provider_and_missing_source_stay_unavailable(monkeypatch):
    state, corpus = state_with_sec_corpus()
    monkeypatch.setattr(
        access.vendor_transcript, "get_latest_transcript_evidence",
        lambda *a, **k: {
            **vendor._unavailable("DOCN", "2026Q3", "Alpha Vantage transcript provider unavailable"),
        },
    )
    state.update(access.prepare_transcript_sources(state, {"news"}))
    assert state["transcript_sources"]["status"] == "unavailable"
    assert access.validated_transcript_record(state) is None
    assert "provider or cache unavailable" in access.transcript_analyst_context(state)
    state, _ = state_with_sec_corpus()
    state["document_sources"] = None
    monkeypatch.setattr(access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: pytest.fail("no SEC source, no transcript fetch"))
    assert access.prepare_transcript_sources(state, {"fundamentals"})["transcript_sources"]["status"] == "unavailable"


def test_legacy_and_non_stock_or_unselected_scope():
    state, _ = state_with_sec_corpus()
    assert access.validated_transcript_record(state) is None
    assert access.transcript_analyst_context(state) == ""
    state.update(access.prepare_transcript_sources(state, {"market"}))
    assert state["transcript_sources"]["status"] == "not_applicable"
    assert access.validated_transcript_record(state) is None
    assert access.transcript_analyst_context(state) == ""
    del state["transcript_sources"]
    state["asset_type"] = "crypto"
    assert access.prepare_transcript_sources(state, {"news"})["transcript_sources"]["status"] == "not_applicable"


def test_resumed_date_pin_mismatch_fails_closed(monkeypatch):
    state, corpus = state_with_sec_corpus()
    monkeypatch.setattr(access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: transcript_record(corpus))
    state.update(access.prepare_transcript_sources(state, {"news"}))
    state["transcript_sources"]["date_evidence"]["call_date"] = "2026-11-02"
    with pytest.raises(ValueError, match="date|transcript"):
        access.validated_transcript_record(state)

def test_malformed_fresh_provider_record_is_unavailable_without_crashing(monkeypatch):
    state, _ = state_with_sec_corpus()
    monkeypatch.setattr(
        access.vendor_transcript, "get_latest_transcript_evidence",
        lambda *a, **k: {"status": "ready", "record_hash": "bad"},
    )
    update = access.prepare_transcript_sources(state, {"fundamentals"})
    assert update["transcript_sources"]["status"] == "unavailable"
    assert update["transcript_sources"]["record"] is None
    state.update(update)
    assert access.validated_transcript_record(state) is None

def test_report_status_is_labeled_and_omits_transcript_body(monkeypatch):
    state, corpus = state_with_sec_corpus()
    assert access.render_transcript_status(state) == ""
    monkeypatch.setattr(access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: transcript_record(corpus))
    state.update(access.prepare_transcript_sources(state, {"news"}))
    rendered = access.render_transcript_status(state)
    assert "Vendor transcript, wording unverified" in rendered
    assert "2026Q3" in rendered
    assert "2026-11-03" in rendered
    assert "[SEC call-date source](https://www.sec.gov/" in rendered
    assert "12,000" in rendered
    assert "Revenue grew" not in rendered
    state, _ = state_with_sec_corpus()
    state["document_sources"] = None
    state.update(access.prepare_transcript_sources(state, {"news"}))
    assert "Vendor transcript unavailable:" in access.render_transcript_status(state)
