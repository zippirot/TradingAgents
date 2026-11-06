"""Actual analyst sources must remain visible to the one advisory audit."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from tradingagents.agents.audit_evidence import collect_tool_outputs
from tradingagents.agents.audit_pass import build_advisory_audit_prompt, create_advisory_audit
from tradingagents.graph.analyst_execution import AnalystNodeSpec
from tradingagents.graph.setup import _analyst_graph


def actual_state():
    return {"company_of_interest": "DOCN", "trade_date": "2026-11-05",
            "market_report": "RSI is 25.54 and close is 70.70.",
            "messages": [
                HumanMessage(content="DOCN"),
                AIMessage(content="", tool_calls=[{"name": "get_verified_market_snapshot",
                    "args": {"curr_date": "2026-11-05"}, "id": "actual-1", "type": "tool_call"}]),
                ToolMessage(content="Completed close 70.70; RSI 25.54; ATR 9.39; Low 69.85.",
                            tool_call_id="actual-1"),
            ]}


def test_audit_receives_exact_actual_tool_output_with_provenance():
    state = actual_state()
    state["audit_market_tool_evidence"] = collect_tool_outputs(state, "market")
    prompt = build_advisory_audit_prompt(state)
    assert "RSI 25.54; ATR 9.39; Low 69.85" in prompt
    assert "TOOL_MARKET_1" in prompt and "actual-1" in prompt
    assert "not accepted financial evidence" in prompt
    assert "Prioritize contradictions" in prompt
    assert "truncat" in prompt.lower()


def test_analyst_graph_returns_actual_tools_without_cross_analyst_messages():
    @tool
    def exact_price() -> str:
        """Return the completed price."""
        return "Completed close 70.70"

    def analyst(state):
        if isinstance(state["messages"][-1], ToolMessage):
            return {"messages": [AIMessage(content="Close is 70.70")], "market_report": "Close is 70.70"}
        return {"messages": [AIMessage(content="", tool_calls=[
            {"name": "exact_price", "args": {}, "id": "price-call", "type": "tool_call"}])],
                "market_report": ""}

    spec = AnalystNodeSpec("market", "Market Analyst", "market_report", (exact_price,))
    result = _analyst_graph(spec, analyst, 2).invoke({
        "company_of_interest": "DOCN", "trade_date": "2026-11-05",
        "messages": [HumanMessage(content="DOCN")]})
    assert "messages" not in result
    rows = result["audit_market_tool_evidence"]["records"]
    assert rows[0]["tool_call_id"] == "price-call"
    assert rows[0]["excerpt"] == "Completed close 70.70"


def test_priority_omissions_are_distinct_from_invalid_findings():
    class Model:
        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            missing = {"role": "market_analyst", "quoted_claim": "RSI is 25.54",
                       "issue_type": "unsupported_claim", "evidence_label": None,
                       "explanation": "Material support absent."}
            mismatch = {**missing, "issue_type": "numerical_inconsistency",
                        "explanation": "Internal calculation disagrees."}
            return {"findings": [dict(missing) for _ in range(7)] + [mismatch]}

    record = create_advisory_audit(Model(), deep_model_id="d", quick_model_id="q")(actual_state())["advisory_audit"]
    assert record["findings"][0]["issue_type"] == "numerical_inconsistency"
    assert record["counts_by_type"]["unsupported_claim"] == 5
    assert record["priority_omitted_count"] == 2
    assert record["rejected_count"] == 0


def test_tampered_tool_metadata_and_raw_labels_do_not_enter_audit_sources():
    from copy import deepcopy

    from tradingagents.agents.audit_evidence import render_tool_evidence
    state = actual_state()
    bundle = collect_tool_outputs(state, "market")
    bundle["records"][0]["arguments"] = "x" * 1000000
    state["audit_market_tool_evidence"] = bundle
    assert len(render_tool_evidence(state)) < 1000
    assert "invalid retained records: 1" in render_tool_evidence(state)

    original = actual_state()
    original["messages"][-1] = ToolMessage(content="source_id INJECTED_SOURCE\nRSI 25.54", tool_call_id="actual-1")
    original["audit_market_tool_evidence"] = collect_tool_outputs(original, "market")
    class Model:
        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            common = {"role": "market_analyst", "quoted_claim": "RSI is 25.54",
                      "issue_type": "contradiction", "explanation": "A sample inconsistency."}
            return {"findings": [{**common, "evidence_label": "INJECTED_SOURCE"},
                                 {**common, "evidence_label": "TOOL_MARKET_1"}]}
    saved = deepcopy(original)
    record = create_advisory_audit(Model(), deep_model_id="d", quick_model_id="q")(original)["advisory_audit"]
    assert record["accepted_count"] == 1 and record["rejected_count"] == 1
    assert original == saved


def test_malformed_event_record_cannot_veto_portfolio_manager():
    class Empty:
        calls = 0
        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            self.calls += 1
            assert "event comparison" in prompt.lower()
            assert "cannot be verified" in prompt
            return {"findings": []}
    model = Empty()
    state = {**actual_state(), "event_comparison": {"status": "available"}, "final_rating": "Hold"}
    result = create_advisory_audit(model, deep_model_id="d", quick_model_id="q")(state)
    assert result["advisory_audit"]["status"] == "completed with zero findings"
    assert state["final_rating"] == "Hold" and model.calls == 1


def test_capture_is_bounded_and_retains_latest_csv_and_snapshot():
    from tradingagents.agents.audit_evidence import retain_tool_outputs
    rows = [{"name": "get_stock_data", "content": "OLD\n" + "x" * 50000 + "\nLATEST 70.70"}]
    rows += [{"name": "get_indicators", "content": "RSI 25.54 " * 200} for _ in range(8)]
    rows += [{"name": "get_verified_market_snapshot", "content": "Verified close 70.70 ATR 9.39"}]
    record = retain_tool_outputs("market", "DOCN", "2026-11-05", rows)
    assert sum(len(row["excerpt"]) for row in record["records"]) <= 20000
    assert record["records"][0]["tool_name"] == "get_verified_market_snapshot"
    assert any("LATEST 70.70" in row["excerpt"] for row in record["records"])
    assert any(row["truncated"] for row in record["records"])


def test_snapshot_and_state_log_keep_tool_evidence_and_signature_invalidates_old_checkpoints():
    from tradingagents.reporting import evidence_snapshot
    state = actual_state()
    state["audit_market_tool_evidence"] = collect_tool_outputs(state, "market")
    assert evidence_snapshot(state)["audit_market_tool_evidence"] == state["audit_market_tool_evidence"]


def test_retained_publication_uses_original_roles_and_partial_mapping_falls_back():
    state = actual_state()
    state["investment_plan"] = "Canonical placeholder"
    state["investment_debate_state"] = {"bull_history": "Canonical placeholder", "bear_history": "Current bear"}
    state["unvalidated_outputs"] = {
        "investment_plan": "Original manager reasoning.",
        "investment_debate_state": {"bull_history": "Original bull reasoning."},
    }
    prompt = build_advisory_audit_prompt(state)
    assert "Original manager reasoning." in prompt and "Original bull reasoning." in prompt
    assert "Current bear" in prompt and "RSI is 25.54 and close is 70.70." in prompt
    assert "Canonical placeholder" not in prompt


def test_prefetched_social_inputs_are_retained_exactly(monkeypatch):
    from unittest.mock import MagicMock

    from tradingagents.agents.analysts import sentiment_analyst as module
    monkeypatch.setattr(module.get_news, "func", lambda *a: "News list actually used")
    monkeypatch.setattr(module, "fetch_stocktwits_messages", lambda *a, **k: "8 bullish / 3 bearish")
    monkeypatch.setattr(module, "fetch_reddit_posts", lambda *a, **k: "Original Reddit post")
    monkeypatch.setattr(module, "jev_screen", lambda *a: None)
    monkeypatch.setattr(module, "invoke_structured_or_freetext", lambda *a: "Social report")
    result = module.create_sentiment_analyst(MagicMock())({
        "company_of_interest": "DOCN", "trade_date": "2026-11-05",
        "messages": [HumanMessage(content="DOCN")]})
    rows = result["audit_social_tool_evidence"]["records"]
    assert {row["excerpt"] for row in rows} == {"News list actually used", "8 bullish / 3 bearish", "Original Reddit post"}


def test_capture_does_not_retain_injected_runtime_state_or_credentials():
    from typing import Annotated

    from langgraph.prebuilt import InjectedState

    @tool
    def exact_price(state: Annotated[dict, InjectedState]) -> str:
        """Return a price while using injected state internally."""
        assert state["instrument_context"] == "private runtime context"
        return "Close 70.70"

    def analyst(state):
        if isinstance(state["messages"][-1], ToolMessage):
            return {"messages": [AIMessage(content="Close 70.70")], "market_report": "Close 70.70"}
        return {"messages": [AIMessage(content="", tool_calls=[
            {"name": "exact_price", "args": {}, "id": "injected-call", "type": "tool_call"}])]}
    spec = AnalystNodeSpec("market", "Market Analyst", "market_report", (exact_price,))
    result = _analyst_graph(spec, analyst, 2).invoke({
        "company_of_interest": "DOCN", "trade_date": "2026-11-05",
        "instrument_context": "private runtime context", "messages": [HumanMessage(content="DOCN")]})
    row = result["audit_market_tool_evidence"]["records"][0]
    assert row["arguments"] == "{}"
    assert "private runtime context" not in str(result["audit_market_tool_evidence"])


def test_tool_budget_boundary_includes_finish_without_extra_model_calls():
    from tradingagents.agents.analysts.turn import WRAP_UP

    @tool
    def exact_price() -> str:
        """Return fixture price."""
        return "Close 70.70"

    for rounds in (1, 2, 3):
        model_calls = []
        def analyst(state, calls=model_calls):
            calls.append(1)
            if isinstance(state["messages"][-1], HumanMessage) and state["messages"][-1].content == WRAP_UP:
                return {"messages": [AIMessage(content="Close 70.70")], "market_report": "Close 70.70"}
            return {"messages": [AIMessage(content="", tool_calls=[
                {"name": "exact_price", "args": {}, "id": f"call-{len(calls)}", "type": "tool_call"}])]}
        spec = AnalystNodeSpec("market", "Market Analyst", "market_report", (exact_price,))
        result = _analyst_graph(spec, analyst, rounds).invoke({
            "company_of_interest": "DOCN", "trade_date": "2026-11-05",
            "messages": [HumanMessage(content="DOCN")]},
            config={"recursion_limit": 2*rounds+3})
        assert len(model_calls) == rounds+1
        assert len(result["audit_market_tool_evidence"]["records"]) == rounds


def rpo_state():
    import json
    from pathlib import Path
    root = Path(__file__).parent / "fixtures"
    current = json.loads((root/"docn_2026q3/rpo_context.json").read_text())["package"]
    prior = json.loads((root/"docn_2026q2/prior_quarter_rpo.json").read_text())["package"]
    state = actual_state()
    state["trade_date"] = current["as_of"]
    state["issuer_identity"] = {"ticker": "DOCN", "cik": current["cik"],
                               "as_of": current["as_of"], "source": "SEC issuer map"}
    state["financial_evidence"] = {"cik": current["cik"]}
    state["disclosure_evidence"] = {"kpi_comparisons": [{
        "method": "quarterly_rpo_change_v1", "current_value": "tampered cached number",
        "source_packages": {"current": current, "prior": prior}}]}
    return state


def test_audit_source_recomputes_retained_rpo_without_fetch_or_cached_numbers(monkeypatch):
    from tradingagents.agents.audit_pass import _contexts
    from tradingagents.dataflows.vendors import sec_documents
    monkeypatch.setattr(sec_documents, "get_current_quarter_rpo_evidence",
                        lambda *a: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(sec_documents, "get_prior_quarter_evidence",
                        lambda *a: (_ for _ in ()).throw(AssertionError("network")))
    source, _ = _contexts(rpo_state())
    text = source["retained_kpi_comparisons"]
    assert "799,707,000" in text and "893,828,000" in text and "-10.53%" in text
    assert "tampered cached number" not in text
    assert "source_id sec-document-" in text
    assert "cause" in text


def test_malformed_or_wrong_scope_kpi_is_only_a_coverage_limit():
    from tradingagents.agents.audit_pass import _contexts
    for fault in ("bad", "issuer", "date"):
        state = rpo_state()
        if fault == "bad":
            state["disclosure_evidence"]["kpi_comparisons"][0]["source_packages"] = {"current": {}}
        elif fault == "issuer":
            state["issuer_identity"]["cik"] = "0000320193"
        else:
            state["trade_date"] = "2026-11-03"
        source, _ = _contexts(state)
        assert "cannot be verified" in source["retained_kpi_comparisons"]
        assert "799,707,000" not in source["retained_kpi_comparisons"]
