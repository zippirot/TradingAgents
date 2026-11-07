import json

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tests.test_document_search_state import state
from tradingagents.agents.state import AgentState
from tradingagents.agents.tools import search_documents


def tool_calls(count=4):
    return AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "revenue"}, "id": f"search-{i}"}
        for i in range(count)
    ])


def tools_graph():
    graph = StateGraph(AgentState)
    graph.add_node("tools", ToolNode([search_documents]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile()


def test_actual_toolnode_enforces_parallel_budget_and_retains_exact_passages():
    original = state()
    original["messages"] = [tool_calls()]
    result = tools_graph().invoke(original)
    trace = result["document_search_trace"]
    messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(trace) == 4
    assert sum(r["status"] == "ok" for r in trace.values()) == 3
    assert trace["fundamentals:search-3"]["status"] == "limit_reached"
    assert all(isinstance(m, ToolMessage) for m in messages)
    for message in messages:
        record = json.loads(message.content)
        assert record == trace[f"fundamentals:{message.tool_call_id}"]
    resumed = {**original, "document_search_trace": trace}
    assert tools_graph().invoke(resumed)["document_search_trace"] == trace


def test_search_tool_schema_hides_role_state_and_call_id():
    assert set(search_documents.args) == {"query"}
    assert "12000" in search_documents.description
    assert "3" in search_documents.description


def test_real_analyst_subgraph_returns_journal_without_leaking_corpus():
    from tradingagents.graph.analyst_execution import AnalystNodeSpec
    from tradingagents.graph.setup import _analyst_graph

    seen = []
    def analyst(s):
        seen.append(s.get("document_search_role"))
        if not any(isinstance(m, ToolMessage) for m in s["messages"]):
            return {"messages": [tool_calls()], "fundamentals_report": ""}
        return {"messages": [AIMessage(content="research")], "fundamentals_report": "research"}
    spec = AnalystNodeSpec("fundamentals", "Fundamentals Analyst", "fundamentals_report", (search_documents,))
    graph = _analyst_graph(spec, analyst, 4)
    initial = state()
    initial.pop("document_search_role")
    result = graph.invoke(initial)
    assert seen == ["fundamentals", "fundamentals"]
    assert result["fundamentals_report"] == "research"
    assert len(result["document_search_trace"]) == 4
    assert "document_sources" not in result
