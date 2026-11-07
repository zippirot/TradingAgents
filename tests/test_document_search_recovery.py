from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from tests.test_document_search_state import state
from tests.test_document_tool_integration import tool_calls
from tradingagents.agents import document_access
from tradingagents.agents.state import AgentState
from tradingagents.agents.tools import search_documents


def test_interrupted_tool_replays_retained_corpus_without_fetch_or_duplicate_journal(monkeypatch):
    actual = document_access.run_document_search
    returned = []

    def interrupted(state, query, **kwargs):
        result = actual(state, query, **kwargs)
        returned.append(result)
        interrupt("search result computed before journal persistence")
        return result

    monkeypatch.setattr(document_access, "run_document_search", interrupted)
    def no_fetch(*args, **kwargs):
        raise AssertionError("Search recovery must not acquire or substitute cache content")
    monkeypatch.setattr("tradingagents.dataflows.vendors.sec_documents.get_filing_search_evidence", no_fetch)
    workflow = StateGraph(AgentState)
    workflow.add_node("tools", ToolNode([search_documents]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    compiled = workflow.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "retained-document-interruption"}}
    source = state()
    source["messages"] = [tool_calls(1)]
    stopped = compiled.invoke(source, config)
    assert stopped["__interrupt__"]
    assert not stopped["document_search_trace"]
    resumed = compiled.invoke(Command(resume=True), config)
    assert len(resumed["document_search_trace"]) == 1
    assert returned[0] == returned[1]
    assert resumed["document_search_trace"] == returned[0]["document_search_trace"]
    assert resumed["document_sources"] == source["document_sources"]
