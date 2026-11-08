"""Source acquisition precedes reasoning and keeps one replayable vintage."""
import copy
import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from tests.test_evidence_gate import complete_evidence
from tradingagents.agents.evidence_validation import create_evidence_gate, create_source_acquisition
from tradingagents.dataflows.config import run_config
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture
def sources(monkeypatch):
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar
    from tradingagents.dataflows.vendors.yahoo import price_observation

    facts, docs = complete_evidence()
    calls = []
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: calls.append("identity") or facts.cik)
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", lambda *a: calls.append("facts") or facts)
    monkeypatch.setattr(sec_documents, "get_filing_evidence", lambda *a: calls.append("filings") or docs)
    monkeypatch.setattr(price_observation, "get_price_observation",
                        lambda *a: calls.append("price") or {"status": "unavailable", "reason": "fixture price"})
    return facts, docs, calls


def initial():
    return {"company_of_interest": "DOCN", "trade_date": "2026-10-19", "asset_type": "stock",
            "messages": [], "market_observation_cutoff": "2026-10-19T19:00:00Z"}


def acquire(state, selected=("fundamentals",)):
    with run_config(DEFAULT_CONFIG):
        return create_source_acquisition(selected)(state)


def test_source_only_cannot_validate_or_replace_model_report(sources):
    facts, docs, calls = sources
    state = {**initial(), "fundamentals_report": "Untrusted narrative"}
    prepared = acquire(state)
    assert calls == ["identity", "facts", "filings", "price"]
    assert not {"evidence_quality", "final_rating", "fundamentals_report", "financial_claim_validation"} & prepared.keys()
    assert prepared["evidence_acquisition"]["status"] == "ready"
    assert "material_claims" not in {c["code"] for c in prepared["evidence_acquisition"]["source_checks"]}
    assert prepared["filing_evidence"] == docs.model_dump(mode="json")
    assert prepared["shared_source_brief"]
    assert state["fundamentals_report"] == "Untrusted narrative"
    checked = create_evidence_gate(["fundamentals"])({**state, **prepared})
    assert calls == ["identity", "facts", "filings", "price"]
    assert checked["final_rating"] == "REVIEW"
    assert checked["financial_claim_validation"]["raw_report"] == "Untrusted narrative"


def test_retained_sources_validate_later_claims_without_refetch(sources):
    facts, _, calls = sources
    prepared = acquire(initial())
    fact = next(f for f in facts.facts if f.metric == "Revenue")
    row = {"kind": fact.origin, "fact_id": fact.fact_id, "metric": fact.metric,
           "value": str(fact.value), "unit": fact.unit,
           "period_start": str(fact.period_start), "period_end": str(fact.period_end)}
    report = "Research.\n" + chr(96)*3 + "financial_claims\n" + json.dumps([row]) + "\n" + chr(96)*3
    checked = create_evidence_gate(["fundamentals"])({**initial(), **prepared, "fundamentals_report": report})
    assert checked["evidence_quality"]["status"] == "limited"
    assert checked["financial_claim_validation"]["raw_report"] == report
    assert checked["financial_evidence"] == prepared["financial_evidence"]
    assert calls.count("facts") == calls.count("filings") == calls.count("price") == 1
    assert acquire({**initial(), **prepared}) == {}


@pytest.mark.parametrize("selected,asset", [(("market",), "stock"), (("fundamentals",), "crypto")])
def test_technical_and_nonstock_get_price_without_sec(sources, selected, asset):
    _, _, calls = sources
    prepared = acquire({**initial(), "asset_type": asset}, selected)
    assert calls == ["price"]
    assert prepared["evidence_acquisition"]["status"] == "not_applicable"
    assert prepared["price_observation"]["reason"] == "fixture price"
    checked = create_evidence_gate(selected)({**initial(), "asset_type": asset, **prepared})
    assert checked["evidence_quality"]["scope"] == "not_applicable"


def test_unavailable_sec_is_retained_but_price_and_analysts_can_proceed(sources, monkeypatch):
    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.dataflows.vendors import sec_edgar

    monkeypatch.setattr(sec_edgar, "cik_for", lambda t: (_ for _ in ()).throw(VendorUnavailableError("SEC unavailable")))
    prepared = acquire(initial())
    assert prepared["evidence_acquisition"]["status"] == "unavailable"
    assert "final_rating" not in prepared
    assert prepared["price_observation"]
    checked = create_evidence_gate(["fundamentals"])({**initial(), **prepared})
    assert checked["final_rating"] == "REVIEW"


def test_retained_scope_mismatch_fails_without_new_vintage(sources):
    prepared = acquire(initial())
    changed = {**initial(), **prepared, "trade_date": "2026-10-20"}
    with pytest.raises(ValueError, match="fresh run"):
        acquire(changed)
    assert create_evidence_gate(["fundamentals"])(changed)["final_rating"] == "REVIEW"
    assert sources[2] == ["identity", "facts", "filings", "price"]


def test_actual_graph_resume_after_acquisition_preserves_vintage_and_memory_join(sources, monkeypatch):
    from tradingagents.graph import setup
    from tradingagents.graph.conditional_logic import ConditionalLogic

    seen = []
    fail = [True]
    def analyst(report_key):
        def run(state):
            assert state["evidence_acquisition"]["status"] == "ready"
            assert state["shared_source_brief"]
            seen.append((report_key, state["shared_source_brief"], copy.deepcopy(state["price_observation"])))
            if report_key == "news_report" and fail[0]:
                raise RuntimeError("interrupted after acquisition")
            return {"messages": [AIMessage(content="research")], report_key: "research"}
        return run
    for factory, report_key in [
        ("create_market_analyst", "market_report"), ("create_news_analyst", "news_report"),
        ("create_sentiment_analyst", "sentiment_report"), ("create_fundamentals_analyst", "fundamentals_report"),
    ]:
        monkeypatch.setattr(setup, factory, lambda llm, key=report_key: analyst(key))
    # Insufficient material claims end at REVIEW, so debate model is never called.
    graph = setup.GraphSetup(object(), object(), ConditionalLogic(), 1).setup_graph(
        memory_node=lambda state: {"memory_note": "memory joined"})
    compiled = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "acquisition-resume"}}
    with run_config(DEFAULT_CONFIG):
        with pytest.raises(RuntimeError, match="after acquisition"):
            compiled.invoke(initial(), config)
        retained = compiled.get_state(config).values
        assert retained["evidence_acquisition"]["status"] == "ready"
        fail[0] = False
        result = compiled.invoke(None, config)
    assert result["final_rating"] == "REVIEW"
    assert result["memory_note"] == "memory joined"
    assert {s[0] for s in seen} == {"market_report", "news_report", "sentiment_report", "fundamentals_report"}
    assert all(item[1:] == seen[0][1:] for item in seen)
    assert sources[2] == ["identity", "facts", "filings", "price"]


def test_disclosure_failure_keeps_facts_and_final_review_without_retry(sources, monkeypatch):
    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.dataflows.vendors import sec_documents

    monkeypatch.setattr(sec_documents, "get_filing_evidence",
                        lambda *a: (_ for _ in ()).throw(VendorUnavailableError("filing unavailable dummy-secret-987")))
    prepared = acquire(initial())
    assert prepared["financial_evidence"]["facts"]
    assert prepared["evidence_acquisition"]["disclosure_error"] == "SEC filing unavailable (VendorUnavailableError)"
    assert "dummy-secret-987" not in str(prepared)
    assert "filing_evidence" not in prepared
    checked = create_evidence_gate(["fundamentals"])({**initial(), **prepared})
    assert checked["final_rating"] == "REVIEW"
    assert sources[2] == ["identity", "facts", "price"]


def test_preacquisition_checkpoint_can_resume_and_old_signature_is_untouched(sources):
    from tradingagents.graph import setup
    from tradingagents.graph.checkpointer import thread_id
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    owner = object.__new__(TradingAgentsGraph)
    owner.selected_analysts = ["market"]
    owner.config = DEFAULT_CONFIG
    signature = owner._run_signature("stock")
    assert "financial_claim_prompt=1" in signature
    old_prompt_signature = signature.replace("|financial_claim_prompt=1", "")
    assert thread_id("DOCN", "2026-10-19", old_prompt_signature) != thread_id("DOCN", "2026-10-19", signature)
    legacy = signature.replace("evidence=4", "evidence=3").replace("|source_acquisition=1", "")
    assert signature != legacy
    old_id, new_id = (thread_id("DOCN", "2026-10-19", s) for s in (legacy, signature))
    assert old_id != new_id
    workflow = setup.GraphSetup(object(), object(), ConditionalLogic(), 1).setup_graph(["market"])
    saver = InMemorySaver()
    paused = workflow.compile(checkpointer=saver, interrupt_before=["Source Acquisition"])
    old_config = {"configurable": {"thread_id": old_id}}
    new_config = {"configurable": {"thread_id": new_id}}
    paused.invoke(initial(), old_config)
    old_snapshot = paused.get_state(old_config)
    assert old_snapshot.next == ("Source Acquisition",)
    assert not sources[2]
    assert not paused.get_state(new_config).values
    paused.invoke(initial(), new_config)
    assert paused.get_state(old_config) == old_snapshot
    # Advance only acquisition, simulating the second interruption boundary.
    resumed = workflow.compile(checkpointer=saver, interrupt_after=["Source Acquisition"])
    with run_config(DEFAULT_CONFIG):
        resumed.invoke(None, new_config)
    state = resumed.get_state(new_config)
    assert state.next == ("Market Analyst",)
    assert state.values["evidence_acquisition"]["status"] == "not_applicable"
    assert sources[2] == ["price"]
    assert paused.get_state(old_config) == old_snapshot


def test_reference_sources_are_acquired_before_shared_analyst_context(sources, monkeypatch):
    from tradingagents.agents import valuation_reference_flow
    from tradingagents.agents.context import get_instrument_context_from_state

    seen = []
    def reference(state, config):
        assert state["evidence_acquisition"]["status"] == "ready"
        assert state["financial_evidence"] and state["price_observation"]
        seen.append("reference")
        return {"valuation_reference": {"status": "fixture"},
                "valuation_reference_brief": "Reference fixture: default peers before analysts"}
    monkeypatch.setattr(valuation_reference_flow, "acquire_reference_inputs", reference)
    state = initial()
    prepared = acquire(state)
    assert seen == ["reference"]
    assert "default peers before analysts" in get_instrument_context_from_state({**state, **prepared})


def test_r1_context_starts_fresh_without_reusing_r5_checkpoint(sources):
    from tradingagents.graph import setup
    from tradingagents.graph.checkpointer import thread_id
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    owner = object.__new__(TradingAgentsGraph)
    owner.selected_analysts = ['market']
    owner.config = DEFAULT_CONFIG
    signature = owner._run_signature('stock')
    r5_signature = signature.replace('shared_source_brief=5', 'shared_source_brief=4')
    old_config = {'configurable': {'thread_id': thread_id('DOCN', '2026-10-19', r5_signature)}}
    current_config = {'configurable': {'thread_id': thread_id('DOCN', '2026-10-19', signature)}}
    workflow = setup.GraphSetup(object(), object(), ConditionalLogic(), 1).setup_graph(['market'])
    paused = workflow.compile(checkpointer=InMemorySaver(), interrupt_before=['Source Acquisition'])
    paused.invoke(initial(), old_config)
    old_snapshot = paused.get_state(old_config)
    assert not paused.get_state(current_config).values
    paused.invoke(initial(), current_config)
    assert paused.get_state(old_config) == old_snapshot
    assert not sources[2]
