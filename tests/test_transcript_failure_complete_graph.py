"""Offline DOCN graph proof for a failed transcript provider."""
from __future__ import annotations

import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from tests.test_document_retained_replay import _retained_corpus
from tradingagents.agents import transcript_access
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup
from tradingagents.reporting import write_report_tree


class OfflineModel(BaseChatModel):
    """Only model output is scripted; graph nodes and evidence checks are real."""

    fundamentals_text: str
    calls: list = Field(default_factory=list)
    tools: tuple = ()

    @property
    def _llm_type(self):
        return "offline-transcript-failure-proof"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"tools": tuple(tools)})

    def with_structured_output(self, schema, **kwargs):
        raise NotImplementedError("offline free-text model")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = "\n".join(str(m.content) for m in messages)
        names = {tool.name for tool in self.tools}
        self.calls.append((names, prompt))
        if "get_financial_evidence" in names:
            response = self.fundamentals_text
        elif "Prioritize contradictions and numerical inconsistencies" in prompt:
            response = json.dumps({"findings": []})
        elif "As the Portfolio Manager" in prompt:
            response = ("Rating: Hold\nExecutive Summary: Offline provider failure replay.\n"
                        "Investment Thesis: Source-restricted research.\nTime Horizon: 6 months.")
        elif "Research Manager and debate facilitator" in prompt:
            response = "Recommendation: Hold\nRationale: Source-restricted research.\nStrategic Actions: None."
        elif "trader" in prompt.lower() and "transaction proposal" in prompt.lower():
            response = "FINAL TRANSACTION PROPOSAL: HOLD"
        else:
            response = "Offline research continues with retained sources."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=response))])


def test_forced_transcript_failure_completes_actual_docn_graph_with_financial_gate(
    monkeypatch, tmp_path,
):
    from tradingagents.agents.analysts import sentiment_analyst
    from tradingagents.dataflows import router
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar

    def no_source_fetch(*args, **kwargs):
        raise AssertionError("retained source replay must not refetch SEC evidence")
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", no_source_fetch)
    monkeypatch.setattr(sec_documents, "get_filing_evidence", no_source_fetch)
    monkeypatch.setattr(sec_documents, "get_filing_search_evidence", no_source_fetch)

    # Social sources are fetched before the model turn; substitute only their
    # provider boundaries so the proof never attempts a network request.
    for vendor in router.VENDOR_METHODS["get_news"]:
        monkeypatch.setitem(router.VENDOR_METHODS["get_news"], vendor,
                            lambda *a, **k: "offline news unavailable")
    monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages",
                        lambda *a, **k: "offline social unavailable")
    monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts",
                        lambda *a, **k: "offline social unavailable")
    monkeypatch.setattr(sentiment_analyst, "jev_screen", lambda *a, **k: None)

    saved, corpus = _retained_corpus()
    state = Propagator().create_initial_state("DOCN", "2026-11-06")
    state.update({
        "analysis_clock": saved["analysis_clock"],
        "market_observation_cutoff": saved["market_observation_cutoff"],
        "issuer_identity": saved["issuer_identity"],
        "evidence_acquisition": saved["evidence_acquisition"],
        "filing_evidence": saved["filing_evidence"],
        "shared_source_brief": saved["shared_source_brief"],
        "price_observation": saved["price_observation"],
        "run_settings": saved["run_settings"],
        "evaluation_mode": "historical",
        "document_sources": {
            "schema_version": 1, "ticker": "DOCN", "as_of": "2026-11-06",
            "asset_type": "stock", "analysis_clock": saved["analysis_clock"],
            "status": "ready", "cik": corpus.cik,
            "corpus": corpus.model_dump(mode="json"),
            "corpus_hash": corpus_hash(corpus), "reason": "",
        },
    })
    calls = []
    def unavailable(*args, **kwargs):
        calls.append((args, kwargs))
        raise VendorUnavailableError("forced transcript source failure")
    monkeypatch.setattr(
        transcript_access.vendor_transcript, "get_latest_transcript_evidence",
        unavailable,
    )
    state.update(transcript_access.prepare_transcript_sources(
        state, ("market", "social", "news", "fundamentals"),
    ))
    assert len(calls) == 1
    assert state["transcript_sources"]["status"] == "unavailable"
    reason = "Vendor transcript unavailable: Transcript provider or cache unavailable"

    model = OfflineModel(
        fundamentals_text=saved["financial_claim_validation"]["raw_report"],
    )
    graph = GraphSetup(
        model, model, ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
        max_tool_rounds=1, quick_model_id="offline", deep_model_id="offline",
    ).setup_graph(selected_analysts=("market", "social", "news", "fundamentals")).compile()
    visited = []
    with run_config({
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "tool_vendors": {"get_stock_data": "none"},
    }):
        for mode, chunk in graph.stream(state, stream_mode=["updates", "values"],
                                        config={"recursion_limit": 100}):
            if mode == "updates":
                visited.extend(chunk)
            else:
                final_state = chunk
    state = final_state
    assert set(visited) >= {
        "Source Acquisition", "Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst",
        "Evidence Check", "Bull Researcher", "Bear Researcher", "Document Followup",
        "Research Manager", "Trader", "Aggressive Analyst", "Conservative Analyst",
        "Neutral Analyst", "Advisory Audit", "Portfolio Manager", "Run Metrics",
    }
    assert state["financial_claim_validation"]["status"] == "pass"
    assert state["evidence_quality"]["status"] in {"sufficient", "limited"}
    assert state["final_trade_decision"] and state["final_rating"] != "REVIEW"
    assert len(calls) == 1  # Compatible retained failure is not fetched again.
    assert state["transcript_sources"]["status"] == "unavailable"
    prompts = [prompt for names, prompt in model.calls if
               "get_financial_evidence" in names or "get_macro_indicators" in names]
    assert len(prompts) == 2 and all(reason in prompt for prompt in prompts)
    # Report metadata describes this replay, never the paid models named in
    # the original input snapshot.
    state["run_settings"] = {
        **state["run_settings"], "llm_provider": "offline",
        "deep_think_provider": "offline", "quick_think_provider": "offline",
        "deep_think_llm": "offline", "quick_think_llm": "offline",
        "max_debate_rounds": 1, "max_risk_discuss_rounds": 1,
    }
    state["report_view_note"] = (
        "Offline forced-provider-failure verification; scripted models; "
        "no live API call or publication."
    )
    target = tmp_path / "report"
    markdown = write_report_tree(
        state, "DOCN", target, settings=state["run_settings"], html=True,
    ).read_text()
    assert "Offline forced-provider-failure verification" in markdown
    assert "offline, deep offline, quick offline" in markdown
    assert reason in markdown
    assert reason in (target / "complete_report.html").read_text()
