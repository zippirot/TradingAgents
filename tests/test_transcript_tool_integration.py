import copy

import pytest
from langchain_core.messages import AIMessage

from tests.test_transcript_access import state_with_sec_corpus, transcript_record
from tradingagents.agents import transcript_access
from tradingagents.agents.document_access import retained_search_packages, run_document_search
from tradingagents.agents.document_questions import (
    document_followup_context,
    lookup_document_questions,
    parse_document_questions,
    render_document_followups,
)


def ready(monkeypatch):
    state, corpus = state_with_sec_corpus()
    monkeypatch.setattr(transcript_access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: transcript_record(corpus))
    state.update(transcript_access.prepare_transcript_sources(state, ["fundamentals", "news"]))
    state["messages"] = []
    state["document_search_trace"] = {}
    return state


def test_transcript_query_returns_labeled_qa_never_quoteable_filing_evidence(monkeypatch):
    state = ready(monkeypatch)
    out = run_document_search(state, "transcript:capacity", role="fundamentals", call_id="one")
    assert out["result"]["status"] == "ok"
    assert all(p["label"] == "vendor transcript, wording unverified" for p in out["result"]["passages"])
    state["document_search_trace"].update(out["document_search_trace"])
    assert retained_search_packages(state) == []
    assert run_document_search(state, "transcript:capacity", role="fundamentals", call_id="one") == out
    bad = copy.deepcopy(state)
    bad["transcript_sources"]["record"]["turns"][3]["text"] = "different cache contents"
    with pytest.raises(ValueError):
        run_document_search(bad, "transcript:capacity", role="fundamentals", call_id="one")


def test_filings_and_transcript_share_parallel_three_call_budget(monkeypatch):
    state = ready(monkeypatch)
    queries = ["conference", "transcript:capacity", "Results", "transcript:capacity"]
    state["messages"] = [AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": query}, "id": str(i)}
        for i, query in enumerate(queries)])]
    for i, query in enumerate(queries):
        out = run_document_search(state, query, role="news", call_id=str(i))
        state["document_search_trace"].update(out["document_search_trace"])
    assert sum(e["counted"] for e in state["document_search_trace"].values()) == 3
    assert out["result"]["status"] == "limit_reached"
    with pytest.raises(ValueError):
        # Query-prefix characters are part of the shared 200-character limit.
        from tradingagents.agents.document_access import search_retained_document_sources
        search_retained_document_sources(state, "transcript:" + "x" * 200)


def test_debate_transcript_lookup_labeled_and_unresolved_on_no_pm_citation(monkeypatch):
    state = ready(monkeypatch)
    state["investment_debate_state"] = {"document_questions": {
        "bull": parse_document_questions('\x60\x60\x60document_questions\n["transcript:capacity"]\n\x60\x60\x60', "bull")}}
    state.update(lookup_document_questions(state))
    assert state["document_followups"]["results"][0]["status"] == "found"
    assert "vendor transcript, wording unverified" in document_followup_context(state)
    assert "unresolved" in render_document_followups(state, "Hold without a citation")
    assert lookup_document_questions(state) == {}


@pytest.mark.parametrize("available", [True, False])
def test_real_fundamentals_and_news_nodes_receive_dated_excerpt_or_failure(monkeypatch, available):
    from tradingagents.agents.analysts import fundamentals_analyst, news_analyst
    from tradingagents.dataflows.errors import VendorUnavailableError

    state, corpus = state_with_sec_corpus()
    def acquire(*args, **kwargs):
        if not available:
            raise VendorUnavailableError("forced transcript source failure")
        return transcript_record(corpus)
    monkeypatch.setattr(transcript_access.vendor_transcript, "get_latest_transcript_evidence", acquire)
    state.update(transcript_access.prepare_transcript_sources(state, ["fundamentals", "news"]))
    state["messages"] = []
    prompts = []
    def take_turn(prompt, llm, tools, messages):
        text = "\n".join(str(message.content) for message in prompt.format_messages(messages=messages))
        prompts.append(text)
        return AIMessage(content="Research continues"), "Research continues"
    for module, factory in (
        (fundamentals_analyst, fundamentals_analyst.create_fundamentals_analyst),
        (news_analyst, news_analyst.create_news_analyst),
    ):
        monkeypatch.setattr(module, "take_turn", take_turn)
        assert any(value == "Research continues" for value in factory(object())(state).values())
    assert len(prompts) == 2
    if available:
        assert all("vendor transcript, wording unverified" in text and
                   "Revenue grew this quarter" in text and "2026-11-03" in text for text in prompts)
    else:
        assert all("Vendor transcript unavailable: Transcript provider or cache unavailable" in text for text in prompts)


def test_retained_free_docn_response_schema_and_actual_sec_call_date(monkeypatch):
    import json

    from tests.test_document_retained_replay import ROOT, _retained_corpus
    from tradingagents.agents.document_access import _scope
    from tradingagents.dataflows.filing_search import corpus_hash
    from tradingagents.dataflows.vendors.alpha_vantage.transcript import parse_transcript_response

    response = ROOT / "private/evidence/transcript-availability/response-redacted.json"
    if not response.is_file():
        pytest.skip("Private retained free DOCN transcript response unavailable")
    _, corpus = _retained_corpus()
    raw = response.read_text()
    assert len(json.loads(raw)["transcript"]) == 47
    record = parse_transcript_response(raw, "DOCN", "2026Q3", "2026-11-06", corpus)
    assert record["status"] == "ready" and len(record["turns"]) == 47
    assert record["date_evidence"]["call_date"] == "2026-11-03"
    assert record["date_evidence"]["locator"] == "block-54"
    state = {"company_of_interest": "DOCN", "trade_date": "2026-11-06", "asset_type": "stock",
             "analysis_clock": {}, "issuer_identity": {"cik": corpus.cik},
             "messages": [], "document_search_trace": {}}
    state["document_sources"] = {**_scope(state), "status": "ready", "cik": corpus.cik,
        "corpus": corpus.model_dump(mode="json"), "corpus_hash": corpus_hash(corpus), "reason": ""}
    monkeypatch.setattr(transcript_access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: record)
    state.update(transcript_access.prepare_transcript_sources(state, ["fundamentals", "news"]))
    context = transcript_access.transcript_analyst_context(state)
    assert "vendor transcript, wording unverified" in context
    assert "2026-11-03" in context
    query = run_document_search(state, "transcript:capacity", role="news", call_id="retained")
    assert query["result"]["status"] == "ok"
    assert query["result"]["passages"]


@pytest.mark.parametrize("role", ["fundamentals", "news"])
def test_real_analyst_subgraph_calls_transcript_tool_with_private_pinned_state(monkeypatch, role):
    from langchain_core.messages import ToolMessage

    from tradingagents.agents.analysts import fundamentals_analyst, news_analyst
    from tradingagents.graph.analyst_execution import build_analyst_execution_plan
    from tradingagents.graph.setup import _analyst_graph

    state = ready(monkeypatch)
    module = fundamentals_analyst if role == "fundamentals" else news_analyst
    factory = module.create_fundamentals_analyst if role == "fundamentals" else module.create_news_analyst
    def turn(prompt, llm, tools, messages):
        assert any(tool.name == "search_documents" for tool in tools)
        if not any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content="", tool_calls=[{
                "name": "search_documents", "args": {"query": "transcript:capacity"}, "id": "qa-one"
            }]), ""
        result = next(message for message in messages if isinstance(message, ToolMessage))
        assert "vendor transcript, wording unverified" in result.content
        return AIMessage(content="Labeled vendor research"), "Labeled vendor research"
    monkeypatch.setattr(module, "take_turn", turn)
    spec = build_analyst_execution_plan([role]).specs[0]
    out = _analyst_graph(spec, factory(object()), 4).invoke(state)
    assert out[spec.report_key] == "Labeled vendor research"
    assert out["document_search_trace"][role + ":qa-one"]["status"] == "ok"
    assert "transcript_sources" not in out


@pytest.mark.parametrize("available", [True, False])
def test_markdown_html_and_cli_render_vendor_status_honestly(monkeypatch, tmp_path, available):
    import io
    import os
    from pathlib import Path

    from rich.console import Console

    from cli import display
    from tradingagents.reporting import write_report_tree

    state = ready(monkeypatch)
    if not available:
        state.pop("transcript_sources")
        monkeypatch.setattr(transcript_access.vendor_transcript, "get_latest_transcript_evidence",
                            lambda *a, **k: {"status": "unavailable", "reason": "forced provider failure"})
        state.update(transcript_access.prepare_transcript_sources(state, ["fundamentals", "news"]))
    state["final_trade_decision"] = "Offline report display fixture, no accepted transcript valuation."
    output = Path(os.environ.get("DOCUMENT_ACCESS_B_RENDER_OUTPUT") or str(tmp_path)) / str(available)
    write_report_tree(state, "DOCN", output)
    markdown = (output / "complete_report.md").read_text()
    html = (output / "complete_report.html").read_text()
    capture = io.StringIO()
    monkeypatch.setattr(display, "console", Console(file=capture, force_terminal=False, width=120))
    display.display_complete_report(state)
    cli = capture.getvalue()
    (output / "cli.txt").write_text(cli)
    if available:
        assert all("wording unverified" in text and "2026-11-03" in text for text in (markdown, html, cli))
        assert "Transcript figures remain unlinked" in markdown
        assert "Revenue grew this quarter" not in markdown
    else:
        assert all("Vendor transcript unavailable: forced provider failure" in text for text in (markdown, html, cli))
