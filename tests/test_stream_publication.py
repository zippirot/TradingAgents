"""Stream subscribers see provisional prose without changing graph state."""

from copy import deepcopy
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from tradingagents.graph.trading_graph import TradingAgentsGraph


def stream(events):
    class Graph:
        def stream(self, *_args, **_kwargs):
            yield from events

    holder = SimpleNamespace(config={}, graph=Graph())
    return list(TradingAgentsGraph.stream_run(holder, {"company_of_interest": "DOCN"}))


def test_analyst_and_debate_reports_are_provisional_and_originals_unchanged():
    analyst = {"messages": [AIMessage(content="Buy at $96")], "fundamentals_report": "Buy at $96"}
    debate = {
        "messages": [],
        "investment_plan": "Buy target $96",
        "investment_debate_state": {
            "bull_history": "Allocate 5%",
            "bear_history": "Sell at $90",
            "count": 2,
        },
    }
    before = deepcopy((analyst, debate))
    emitted = stream([(("analyst",), "tasks", {"result": analyst}), ((), "values", debate)])
    assert "Provisional" in emitted[0][0][0].content
    assert "Provisional" in emitted[0][1]["fundamentals_report"]
    assert "Provisional" in emitted[1][1]["investment_plan"]
    assert "Provisional" in emitted[1][1]["investment_debate_state"]["bull_history"]
    assert emitted[1][1]["investment_debate_state"]["count"] == 2
    assert (analyst, debate) == before


def test_tool_calls_and_tool_results_are_not_modified():
    call = {"name": "get_financial_evidence", "args": {"curr_date": "2026-10-19"}, "id": "call_1"}
    ai = AIMessage(content="Looking up filing", tool_calls=[call])
    tool = ToolMessage(
        content='{"value":"96"}', tool_call_id="call_1", name="get_financial_evidence"
    )
    originals = deepcopy((ai, tool))
    emitted = stream([((), "values", {"messages": [ai, tool], "market_report": "Price $96"})])
    messages = emitted[0][0]
    assert messages[0].content.startswith("[Provisional")
    assert messages[0].tool_calls == ai.tool_calls
    assert messages[1] == tool
    assert (ai, tool) == originals


def test_final_canonical_pm_state_is_not_prefixed_and_repeat_is_idempotent():
    final = {
        "messages": [AIMessage(content="Canonical decision")],
        "final_trade_decision": "**Rating**: Hold\nNo target",
        "final_rating": "Hold",
        "unvalidated_outputs": {"final_trade_decision": "Buy target $96"},
        "target_validation": {"status": "unsupported", "target": None},
    }
    emitted = stream([((), "values", final)])
    assert emitted[0][1]["final_trade_decision"] == final["final_trade_decision"]
    assert emitted[0][0][0].content.startswith("[Provisional")
    already = "[Provisional, unvalidated model output — not a published decision.]\nBuy $96"
    repeated = stream(
        [((), "values", {"messages": [AIMessage(content=already)], "market_report": already})]
    )
    assert repeated[0][0][0].content == already
    assert repeated[0][1]["market_report"] == already


def test_ai_content_blocks_are_qualified_without_changing_nontext_blocks():
    ai = AIMessage(
        content=[{"type": "reasoning", "id": "r"}, {"type": "text", "text": "Target $96"}]
    )
    emitted = stream([((), "values", {"messages": [ai]})])
    content = emitted[0][0][0].content
    assert content[0] == {"type": "reasoning", "id": "r"}
    assert content[1]["text"].startswith("[Provisional")
    assert ai.content[1]["text"] == "Target $96"
