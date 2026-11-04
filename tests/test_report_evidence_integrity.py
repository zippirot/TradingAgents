"""Recovery contracts for evidence-aware application runs."""
from typing import TypedDict

from langgraph.graph import END, StateGraph

from tradingagents.graph.checkpointer import checkpoint_step, get_checkpointer, thread_id
from tradingagents.graph.trading_graph import TradingAgentsGraph


def test_prevalidation_checkpoint_is_preserved_but_not_resumed(tmp_path):
    app = object.__new__(TradingAgentsGraph)
    app.selected_analysts = ("market", "fundamentals")
    app.config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
    signature = app._run_signature("stock")
    assert "evidence=1" in signature and "publication=1" in signature
    old_signature = signature.replace("|evidence=1", "").replace("|publication=1", "")

    class State(TypedDict):
        count: int

    builder = StateGraph(State)
    builder.add_node("after_old_validation", lambda state: {"count": state["count"] + 1})
    builder.set_entry_point("after_old_validation")
    builder.add_edge("after_old_validation", END)
    old_id = thread_id("DOCN", "2026-11-04", old_signature)
    new_id = thread_id("DOCN", "2026-11-04", signature)
    assert old_id != new_id
    with get_checkpointer(str(tmp_path), "DOCN") as saver:
        graph = builder.compile(checkpointer=saver)
        graph.invoke({"count": 40}, config={"configurable": {"thread_id": old_id}})
        assert graph.get_state({"configurable": {"thread_id": new_id}}).values == {}
        fresh = graph.invoke({"count": 0}, config={"configurable": {"thread_id": new_id}})
        assert fresh["count"] == 1
        assert graph.get_state({"configurable": {"thread_id": old_id}}).values["count"] == 41
    assert checkpoint_step(str(tmp_path), "DOCN", "2026-11-04", old_signature) is not None


def test_interrupted_full_state_write_preserves_prior_snapshot_and_no_memory(tmp_path, monkeypatch):
    import json

    import pytest

    from tradingagents.agents.evidence_validation import review_terminal_state
    from tradingagents.dataflows import files

    app = object.__new__(TradingAgentsGraph)
    app.config = {"results_dir": str(tmp_path)}
    app.run_settings = lambda: {}
    state = {
        **review_terminal_state({"status": "insufficient", "checks": [
            {"status": "unavailable", "message": "Source unavailable"},
        ]}),
        "company_of_interest": "DOCN",
        "trade_date": "2026-11-04",
        **dict.fromkeys(("market_report", "news_report", "sentiment_report", "fundamentals_report"), ""),
    }
    app._log_state("2026-11-04", state)
    path = tmp_path / "DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-04.json"
    original = path.read_bytes()
    real_replace = files.os.replace

    def interrupted_replace(source, dest):
        raise PermissionError("simulated interrupted required write")

    monkeypatch.setattr(files.os, "replace", interrupted_replace)
    state["market_report"] = "changed"
    with pytest.raises(PermissionError, match="interrupted"):
        app.record_decision("DOCN", "2026-11-04", state)
    assert path.read_bytes() == original
    assert not list(path.parent.glob("*.tmp"))
    monkeypatch.setattr(files.os, "replace", real_replace)
    app.record_decision("DOCN", "2026-11-04", state)
    saved = json.loads(path.read_text())
    assert saved["market_report"] == "changed"
    assert saved["final_rating"] == "REVIEW"


def test_two_synthetic_issuers_keep_concurrent_evidence_and_failures_isolated(monkeypatch):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from tests.test_evidence_gate import complete_evidence
    from tradingagents.agents.evidence_validation import create_evidence_gate
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    base, filing = complete_evidence()
    packages, documents, states = {}, {}, {}
    for ticker, cik, revenue in (("FIRST", "0000000001", "234000000"),
                                 ("SECOND", "0000000002", "468000000")):
        raw = base.model_dump(mode="json")
        raw["cik"] = cik
        for source in raw["sources"]:
            source["cik"] = cik
        for fact in raw["facts"]:
            fact["cik"] = cik
            if fact["metric"] == "Revenue":
                fact["value"] = revenue
        packages[ticker] = EvidencePackage.model_validate(raw)
        doc = filing.model_dump(mode="json")
        doc["cik"] = cik
        for source in doc["documents"]:
            source["filing"]["cik"] = cik
            source["filing"]["accession"] = cik + "-26-000001"
            source["filing"]["url"] = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{cik}26000001/filing.htm"
            )
            source["url"] = source["filing"]["url"]
            source["source_id"] = "synthetic-document-" + cik
        documents[ticker] = DisclosurePackage.model_validate(doc)
        fact = next(f for f in packages[ticker].facts if f.metric == "Revenue")
        claim = {"kind": fact.origin, "fact_id": fact.fact_id, "metric": fact.metric,
                 "value": str(fact.value), "unit": fact.unit,
                 "period_start": str(fact.period_start), "period_end": str(fact.period_end)}
        fence = chr(96) * 3
        states[ticker] = {"company_of_interest": ticker, "trade_date": str(base.as_of),
                          "asset_type": "stock",
                          "fundamentals_report": fence + "financial_claims\n" + json.dumps([claim]) + "\n" + fence}

    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: packages[ticker].cik)
    monkeypatch.setattr(sec_documents, "get_filing_evidence", lambda ticker, date: documents[ticker])
    gate = create_evidence_gate(["fundamentals"])

    def run_pair():
        overlap = Barrier(2)

        def get_facts(ticker, date):
            overlap.wait(timeout=5)
            return packages[ticker]

        monkeypatch.setattr(sec_edgar, "get_financial_evidence", get_facts)
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(gate, [states["FIRST"], states["SECOND"]]))

    first, second = run_pair()
    assert first["evidence_quality"]["status"] == second["evidence_quality"]["status"] == "limited"
    assert first["financial_evidence"]["cik"] == "0000000001"
    assert second["financial_evidence"]["cik"] == "0000000002"
    assert next(f["value"] for f in first["financial_evidence"]["facts"] if f["metric"] == "Revenue") == "234000000"
    assert next(f["value"] for f in second["financial_evidence"]["facts"] if f["metric"] == "Revenue") == "468000000"
    packages["SECOND"] = packages["SECOND"].model_copy(update={
        "facts": tuple(f for f in packages["SECOND"].facts if f.metric != "Operating Cash Flow"),
    })
    first, second = run_pair()
    assert first["evidence_quality"]["status"] == "limited"
    assert second["evidence_quality"]["status"] == "insufficient"
    assert second["final_rating"] == "REVIEW"
