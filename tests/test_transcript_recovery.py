from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from tests.test_transcript_access import state_with_sec_corpus
from tests.test_transcript_backend import payload
from tradingagents.agents.state import AgentState
from tradingagents.agents.transcript_access import prepare_transcript_sources
from tradingagents.dataflows.vendors.alpha_vantage import transcript


def test_interrupted_transcript_acquisition_reuses_atomic_cache_without_duplicate_request(monkeypatch, tmp_path):
    state, _ = state_with_sec_corpus()
    monkeypatch.setattr(transcript, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    requests = []
    def response(*args, **kwargs):
        requests.append(1)
        return payload()
    monkeypatch.setattr(transcript, "_request_transcript", response)
    observed = []
    def acquire(state):
        update = prepare_transcript_sources(state, ["fundamentals", "news"])
        observed.append(update)
        interrupt("transcript fetched and cached before source checkpoint commit")
        return update
    workflow = StateGraph(AgentState)
    workflow.add_node("acquire", acquire)
    workflow.add_edge(START, "acquire")
    workflow.add_edge("acquire", END)
    compiled = workflow.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "transcript-source-interruption"}}
    stopped = compiled.invoke(state, config)
    assert stopped["__interrupt__"]
    assert requests == [1]
    assert "transcript_sources" not in stopped
    resumed = compiled.invoke(Command(resume=True), config)
    assert len(requests) == 1
    assert observed[0] == observed[1]
    assert resumed["transcript_sources"] == observed[0]["transcript_sources"]
    assert resumed["transcript_sources"]["status"] == "ready"
    assert prepare_transcript_sources(resumed, ["fundamentals", "news"]) == {}
