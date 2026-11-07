"""Full-state log keeps validated document/transcript snapshots and debate questions."""

import hashlib
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from tradingagents.agents.document_access import (
    retained_search_packages,
    run_document_search,
    validated_document_corpus,
)
from tradingagents.agents.document_questions import (
    lookup_document_questions,
    parse_document_questions,
    render_document_followups,
)
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _state(*, with_call=False):
    filing = FilingReference(
        cik="0001582961", accession="0001582961-26-000002", form="10-Q",
        filed_date=date(2026, 8, 5), report_date=date(2026, 6, 30),
        primary_document="quarter.htm", items="",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000158296126000002/quarter.htm",
    )
    document = FilingDocument(
        source_id="sec-document-" + hashlib.sha256(filing.url.encode()).hexdigest(),
        filing=filing, url=filing.url, retrieved_at=datetime(2026, 8, 5, tzinfo=UTC),
        content_hash="sec-source-hash",
        blocks=(SourceBlock(locator="block-1", section="Note", text="alpha | whole table"),),
    )
    documents = [document]
    if with_call:
        call = FilingReference(
            cik=filing.cik, accession="0001628280-26-069125", form="8-K",
            filed_date=date(2026, 8, 20), report_date=date(2026, 8, 20),
            primary_document="release.htm", items="2.02",
            url="https://www.sec.gov/Archives/edgar/data/1582961/000162828026069125/release.htm",
        )
        url = call.url.replace("release.htm", "ex99.htm")
        documents.append(FilingDocument(
            source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
            filing=call, url=url, retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
            content_hash="sec-call-hash",
            blocks=(
                SourceBlock(locator="block-1", section="Results",
                            text="DigitalOcean Announces Second Quarter 2026 Financial Results."),
                SourceBlock(locator="block-2", section="Call",
                            text="DigitalOcean will host a conference call on August 20, 2026."),
            ),
        ))
    corpus = DisclosurePackage(
        cik=filing.cik, as_of=date(2026, 9, 1), documents=tuple(documents),
    )
    clock = {"analysis_timezone": "America/Denver", "cutoff_utc": "2026-09-02T05:59:59+00:00"}
    scope = {"schema_version": 1, "ticker": "DOCN", "as_of": "2026-09-01",
             "asset_type": "stock", "analysis_clock": clock}
    fence = chr(96) * 3
    questions = parse_document_questions(
        fence + "document_questions\n[\"alpha\"]\n" + fence, "bull",
    )
    state = {
        "company_of_interest": "DOCN", "trade_date": "2026-09-01",
        "asset_type": "stock", "analysis_clock": clock,
        "issuer_identity": {"cik": filing.cik},
        "document_sources": {
            **scope, "status": "ready", "cik": filing.cik,
            "corpus": corpus.model_dump(mode="json"), "corpus_hash": corpus_hash(corpus),
            "reason": "",
        },
        "investment_debate_state": {
            "bull_history": "Bull asks about alpha", "bear_history": "Bear view",
            "history": "Debate", "current_response": "Bull asks about alpha", "count": 2,
            "document_questions": {
                "bull": questions,
                "bear": parse_document_questions("No questions", "bear"),
            },
        },
        "risk_debate_state": {
            "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "history": "",
        },
        "market_report": "", "sentiment_report": "", "news_report": "",
        "fundamentals_report": "alpha metric was misstated.",
        "trader_investment_plan": "", "investment_plan": "",
        "final_trade_decision": "No trade.", "final_rating": "REVIEW",
    }
    return state, corpus


def _save_and_reload(tmp_path, state):
    stub = SimpleNamespace(
        config={"results_dir": str(tmp_path)}, run_settings=lambda: {},
    )
    TradingAgentsGraph._log_state(stub, state["trade_date"], state)
    path = (tmp_path / "DOCN" / "TradingAgentsStrategy_logs"
            / "full_states_log_2026-09-01.json")
    return json.loads(path.read_text())


def test_log_reload_preserves_a4_corpus_journal_questions_and_report(tmp_path):
    state, _ = _state()
    trace = run_document_search(
        state, "alpha", role="fundamentals", call_id="call-1",
    )
    state["document_search_trace"] = trace["document_search_trace"]
    state.update(lookup_document_questions(state))
    saved = _save_and_reload(tmp_path, state)
    assert saved["asset_type"] == "stock"
    assert saved["document_sources"] == state["document_sources"]
    assert saved["document_search_trace"] == state["document_search_trace"]
    assert saved["document_followups"] == state["document_followups"]
    assert saved["investment_debate_state"]["document_questions"] == state["investment_debate_state"]["document_questions"]
    assert saved["investment_debate_state"]["count"] == 2
    assert validated_document_corpus(saved) is not None
    assert len(retained_search_packages(saved)) == 1
    assert lookup_document_questions(saved) == {}
    ref = saved["document_followups"]["results"][0]["passages"][0]["citation_ref"]
    assert ref in render_document_followups(saved, "The decision cites " + ref)


def test_log_reload_preserves_ready_transcript_pin_when_b_module_exists(tmp_path, monkeypatch):
    access = pytest.importorskip("tradingagents.agents.transcript_access")
    vendor = pytest.importorskip("tradingagents.dataflows.vendors.alpha_vantage.transcript")
    state, corpus = _state(with_call=True)
    raw = json.dumps({"symbol": "DOCN", "quarter": "2026Q2", "transcript": [
        {"speaker": "Operator", "title": "Operator", "content": "Welcome."},
        {"speaker": "CEO", "title": "CEO", "content": "Revenue was $100 million."},
        {"speaker": "Operator", "title": "Operator", "content": "Your first question comes next."},
    ]})
    transcript = vendor.parse_transcript_response(
        raw, "DOCN", "2026Q2", "2026-09-01", corpus,
        cutoff_utc=state["analysis_clock"]["cutoff_utc"],
    )
    monkeypatch.setattr(access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: transcript)
    state.update(access.prepare_transcript_sources(state, {"news"}))
    state.update(lookup_document_questions(state))
    saved = _save_and_reload(tmp_path, state)
    assert saved["transcript_sources"]["record_hash"] == state["transcript_sources"]["record_hash"]
    assert access.validated_transcript_record(saved)["fiscal_quarter"] == "2026Q2"
    assert lookup_document_questions(saved) == {}
