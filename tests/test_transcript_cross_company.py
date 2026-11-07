"""Offline transcript checks from two actual public SEC earnings exhibits."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tradingagents.dataflows.vendors.alpha_vantage import transcript as ts
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

FIXTURES = Path(__file__).parent / "fixtures/document_access"


def _fixture(ticker: str):
    value = json.loads((FIXTURES / f"public_sec_earnings_{ticker.lower()}.json").read_text())
    assert value["fixture_kind"].startswith("offline excerpt from public SEC EX-99.1")
    corpus = DisclosurePackage.model_validate(value["package"])
    document = corpus.documents[0]
    provenance = value["provenance"]
    assert provenance["source_url"] == document.url
    assert provenance["filing_primary_url"] == document.filing.url
    assert provenance["source_content_sha256"] == document.content_hash
    assert provenance["filed_date"] == document.filing.filed_date.isoformat()
    assert set(provenance["excerpt_locators"]) == {b.locator for b in document.blocks}
    assert document.filing.form == "8-K" and "2.02" in document.filing.items
    assert document.source_id == "sec-document-" + hashlib.sha256(document.url.encode()).hexdigest()
    return value, corpus


def _vendor_stub(ticker: str) -> str:
    return json.dumps({
        "symbol": ticker, "quarter": "2026Q3",
        "transcript": [
            {"speaker": "Operator", "title": "Operator",
             "content": "Welcome to the third quarter call."},
            {"speaker": "Chief Executive", "title": "CEO",
             "content": "Capacity planning remains a management question."},
            {"speaker": "Operator", "title": "Operator",
             "content": "Your first question comes from Analyst One."},
            {"speaker": "Analyst One", "title": "Analyst",
             "content": "What changed in capacity?"},
            {"speaker": "Chief Executive", "title": "CEO",
             "content": "Capacity varies by market."},
        ],
    })


@pytest.mark.parametrize("ticker", ("JPM", "CAT"))
def test_real_sec_headline_names_quarter_without_calendar_inference(ticker):
    _, corpus = _fixture(ticker)
    headline = corpus.documents[0].blocks[0]
    assert ts._release_quarters(headline.text) == {"2026Q3"}
    assert ts._release_quarters("Results for quarter ended September 30, 2026") == set()


def test_jpm_actual_sec_call_date_future_cutoff_and_stubbed_vendor_search(monkeypatch, tmp_path):
    fixture, corpus = _fixture("JPM")
    dated = ts.resolve_sec_call_date(corpus, "2026Q3", "2026-11-06")
    assert dated["status"] == "dated"
    assert dated["call_date"] == "2026-10-13"
    assert dated["locator"] == "block-107"
    assert dated["source_url"] == fixture["provenance"]["source_url"]
    assert dated["content_hash"] == fixture["provenance"]["source_content_sha256"]
    assert "conference call today, October 13, 2026" in dated["quote"]
    assert ts.select_latest_eligible_call(corpus, "2026-11-06")["fiscal_quarter"] == "2026Q3"

    early = ts.resolve_sec_call_date(
        corpus, "2026Q3", "2026-10-13",
        cutoff_utc="2026-10-14T03:59:59+00:00",
    )
    assert early["status"] == "future"
    late = ts.resolve_sec_call_date(
        corpus, "2026Q3", "2026-10-13",
        cutoff_utc="2026-10-14T03:59:59.999999+00:00",
    )
    assert late["status"] == "dated"

    monkeypatch.setattr(ts, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    calls = []
    monkeypatch.setattr(
        ts, "_request_transcript",
        lambda *args: calls.append(args) or _vendor_stub("JPM"),
    )
    ready = ts.get_transcript_evidence(
        "JPM", "2026Q3", "2026-11-06",
        filing_corpus=corpus, allow_network=True,
    )
    assert calls == [("JPM", "2026Q3")]
    assert ready["status"] == "ready"
    assert ready["label"] == "vendor transcript, wording unverified"
    assert ready["date_evidence"]["source_url"] == fixture["provenance"]["source_url"]
    assert ready["date_evidence"]["call_date"] == "2026-10-13"
    found = ts.search_transcript_evidence(ready, "capacity")
    assert found["passages"]
    assert all(p["section"] == "Q&A" for p in found["passages"])
    assert all(p["label"] == "vendor transcript, wording unverified" for p in found["passages"])
    assert all(p["passage_hash"] == hashlib.sha256(p["text"].encode()).hexdigest()
               for p in found["passages"])
    assert ts.prepared_remarks_excerpt(ready)["call_date"] == "2026-10-13"
    with pytest.raises(ValueError, match="limit"):
        ts.search_transcript_evidence(ready, "capacity", max_chars=12001)
    unavailable = ts.parse_transcript_response(
        _vendor_stub("JPM"), "JPM", "2026Q3", "2026-10-13", corpus,
        cutoff_utc="2026-10-14T03:59:59+00:00",
    )
    assert unavailable["status"] == "unavailable" and not unavailable["turns"]


def test_cat_hyphenated_quarter_has_no_sec_call_date_and_never_fetches_vendor(
    monkeypatch, tmp_path,
):
    fixture, corpus = _fixture("CAT")
    assert fixture["provenance"]["call_date_claim"].startswith("no actual call date")
    dated = ts.resolve_sec_call_date(corpus, "2026Q3", "2026-11-06")
    assert dated["status"] == "undated"
    assert dated["call_date"] is None
    assert dated["reason"] == "No retained SEC earnings exhibit establishes the call date"
    selected = ts.select_latest_eligible_call(corpus, "2026-11-06")
    assert selected["status"] == "unavailable"
    assert selected["reason"] == "Explicit fiscal quarter found, but no SEC call date is available"
    monkeypatch.setattr(ts, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(
        ts, "_request_transcript",
        lambda *args: pytest.fail("Undated CAT call must not invoke Alpha Vantage"),
    )
    unavailable = ts.get_latest_transcript_evidence(
        "CAT", "2026-11-06", filing_corpus=corpus, allow_network=True,
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["label"] == "vendor transcript, wording unverified"
    assert "call date" in unavailable["reason"].lower()
    assert not unavailable["turns"]
    assert not list(tmp_path.rglob("*.json"))
    parsed = ts.parse_transcript_response(
        _vendor_stub("CAT"), "CAT", "2026Q3", "2026-11-06", corpus,
    )
    assert parsed["status"] == "unavailable" and not parsed["turns"]


def test_msft_real_first_quarter_release_does_not_establish_fiscal_year_or_call_date(
    monkeypatch, tmp_path,
):
    fixture, corpus = _fixture("MSFT")
    assert fixture["provenance"]["sic"] == "7372"
    assert fixture["provenance"]["call_date_claim"].startswith("unavailable")
    headline, release_date, call_text = corpus.documents[0].blocks
    assert "First Quarter Results" in headline.text
    assert "October 28, 2026" in release_date.text
    assert "conference call and webcast" in call_text.text
    assert "today" in call_text.text
    assert ts._release_quarters(headline.text) == set()
    assert ts._release_quarters(release_date.text) == set()
    assert ts.select_latest_eligible_call(corpus, "2026-11-06") == {
        "status": "unavailable", "fiscal_quarter": None, "date_evidence": None,
        "reason": "No retained SEC earnings exhibit names an explicit fiscal quarter",
    }
    # Supplying a hypothetical fiscal quarter cannot make release date or
    # cross-block "today" wording into a source-pinned call date.
    dated = ts.resolve_sec_call_date(corpus, "2027Q1", "2026-11-06")
    assert dated["status"] == "undated"
    assert dated["call_date"] is None
    monkeypatch.setattr(ts, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(
        ts, "_request_transcript",
        lambda *args: pytest.fail("Unpinned MSFT call must not invoke Alpha Vantage"),
    )
    unavailable = ts.get_latest_transcript_evidence(
        "MSFT", "2026-11-06", filing_corpus=corpus, allow_network=True,
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["label"] == "vendor transcript, wording unverified"
    assert "fiscal quarter" in unavailable["reason"].lower()
    assert not unavailable["turns"]
    assert not list(tmp_path.rglob("*.json"))
