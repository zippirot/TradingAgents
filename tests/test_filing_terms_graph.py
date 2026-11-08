"""Compiled graph proof of pre-analyst filing term delivery and state retention."""

from langchain_core.messages import AIMessage

from tests.test_commitments import MDNA, lease_package
from tradingagents.agents import kpi_comparisons, transcript_access, valuation_reference_flow
from tradingagents.agents.analysts import fundamentals_analyst
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.dataflows.vendors import sec_documents, sec_edgar
from tradingagents.dataflows.vendors.yahoo import price_observation
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup


def test_compiled_graph_delivers_full_filing_terms_before_fundamentals_and_retains_them(
    monkeypatch,
):
    corpus = lease_package(mdna=MDNA)
    financial = EvidencePackage(cik=corpus.cik, as_of=corpus.as_of)
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: corpus.cik)
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", lambda *args: financial)
    monkeypatch.setattr(sec_documents, "get_filing_evidence", lambda *args: corpus)
    monkeypatch.setattr(sec_documents, "get_filing_search_evidence", lambda *args, **kwargs: corpus)
    monkeypatch.setattr(price_observation, "get_price_observation", lambda *args: {
        "status": "unavailable", "reason": "Offline synthetic price unavailable",
    })
    monkeypatch.setattr(kpi_comparisons, "retrieve_rpo_comparison", lambda *args: None)
    monkeypatch.setattr(transcript_access, "prepare_transcript_sources", lambda *args: {})
    monkeypatch.setattr(valuation_reference_flow, "acquire_reference_inputs", lambda *args: {})

    prompts = []

    def model_boundary(prompt, _llm, _tools, messages):
        text = "\n".join(str(item.content) for item in prompt.invoke({"messages": messages}).to_messages())
        prompts.append(text)
        return AIMessage(content="Research based on the retained filing; financial coverage unavailable."), "Research based on the retained filing; financial coverage unavailable."

    monkeypatch.setattr(fundamentals_analyst, "take_turn", model_boundary)
    graph = GraphSetup(object(), object(), ConditionalLogic(), 1).setup_graph(["fundamentals"]).compile()
    initial = Propagator().create_initial_state("DOCN", str(corpus.as_of))
    with run_config({**DEFAULT_CONFIG, "tool_vendors": {"get_stock_data": "yfinance"}}):
        final = graph.invoke(initial, config={"recursion_limit": 100})

    assert len(prompts) == 1
    assert "312322 USD thousands" in prompts[0]
    assert "2955158 USD thousands" in prompts[0]
    assert "block-430" in prompts[0]
    assert final["filing_terms_evidence"]["notes"][0]["principal_outstanding"] == "312322"
    assert final["filing_terms_evidence"]["leases"][0]["undiscounted_amount"] == "2955158"
    assert final["fundamentals_report"].startswith("Research based on")
    assert final["evidence_quality"]["status"] == "insufficient"


def test_filing_brief_version_separates_predecessor_checkpoint_identity():
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.checkpointer import thread_id
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.config = dict(DEFAULT_CONFIG)
    graph.selected_analysts = ["fundamentals"]
    current = graph._run_signature("stock")
    assert "shared_source_brief=5" in current
    for version in (3, 4):
        predecessor = current.replace("shared_source_brief=5", f"shared_source_brief={version}")
        assert thread_id("DOCN", "2026-11-06", current) != thread_id("DOCN", "2026-11-06", predecessor)


def test_retrieval_semantics_separate_predecessor_checkpoint_identity():
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.checkpointer import thread_id
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.config = dict(DEFAULT_CONFIG)
    graph.selected_analysts = ["fundamentals"]
    current = graph._run_signature("stock")
    assert "document_search=3" in current and "document_followup=3" in current
    old = current.replace("document_search=3", "document_search=2").replace(
        "document_followup=3", "document_followup=2")
    assert thread_id("DOCN", "2026-11-06", current) != thread_id("DOCN", "2026-11-06", old)
