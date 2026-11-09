"""Private attempt traces exercise the real node/callback boundaries."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from tradingagents.attempt_trace import AttemptRecorder
from tradingagents.operational_capture import observed_node


def state():
    return {"run_id": "one", "company_of_interest": "DOCN", "trade_date": "2026-11-07",
            "run_settings": {}}


def run(recorder, name="Market Analyst", node=None):
    node = node or (lambda s: {"market_report": "retained output"})
    return observed_node(node, name)(state(), {"callbacks": [recorder]})


def events(root):
    return [json.loads(line) for path in (root / "trace").glob("*.jsonl")
            for line in path.read_text().splitlines()]


def test_trace_default_off(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_TRACE", raising=False)
    run(AttemptRecorder(tmp_path, "attempt-one"))
    assert not (tmp_path / "trace").exists()


def test_transcript_has_line_per_observed_node(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_TRACE", raising=False)
    recorder = AttemptRecorder(tmp_path, "attempt-one")
    run(recorder, "Source Acquisition")
    run(recorder, "Market Analyst")
    text = (tmp_path / "message_tool.log").read_text()
    assert "Source Acquisition" in text and "Market Analyst" in text
    assert "market_report" in text
    assert "retained output" not in text  # the durable state pointer is sufficient


def test_trace_ordering_across_concurrent_stages(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_TRACE", "1")
    recorder = AttemptRecorder(tmp_path, "attempt-one")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda stage: run(recorder, stage), ["Market Analyst", "News Analyst"]))
    paths = list((tmp_path / "trace").glob("*.jsonl"))
    assert len(paths) == 2
    rows = events(tmp_path)
    assert len({row["sequence"] for row in rows}) == len(rows)
    for path in paths:
        stage = [json.loads(line) for line in path.read_text().splitlines()]
        assert [row["event"] for row in stage] == ["stage_start", "stage_end"]
        assert stage[0]["sequence"] < stage[-1]["sequence"]
        assert all(row["attempt_id"] == "attempt-one" and row["run_id"] == "one" for row in stage)


def test_trace_restart_isolation_and_incomplete_write(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_TRACE", "1")

    def fail(s):
        raise RuntimeError("private-error")

    with pytest.raises(RuntimeError):
        run(AttemptRecorder(tmp_path / "first", "attempt-one"), node=fail)
    run(AttemptRecorder(tmp_path / "second", "attempt-two"))
    assert events(tmp_path / "first")[-1]["incomplete"] is True
    assert events(tmp_path / "second")[-1]["incomplete"] is False
    assert "private-error" not in str(events(tmp_path / "first"))
    assert {r["attempt_id"] for r in events(tmp_path / "second")} == {"attempt-two"}


def test_trace_excludes_secrets_and_report_exports(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_TRACE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-private-token")
    llm = FakeListChatModel(responses=["echo synthetic-private-token"])

    def node(s, config):
        return {"market_report": llm.invoke("prompt synthetic-private-token", config).content}

    result = run(AttemptRecorder(tmp_path, "attempt-one"), node=node)
    rows = events(tmp_path)
    assert {r["event"] for r in rows} >= {"model_start", "model_end"}
    assert "synthetic-private-token" not in str(rows)
    assert "[REDACTED]" in str(rows)
    assert not (tmp_path / "reports" / "trace").exists()
    assert result["model_call_metadata"]
    assert all(row["actual_model"] is None for row in result["model_call_metadata"].values())


def test_model_call_metadata_available_without_full_trace(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_TRACE", raising=False)
    llm = FakeListChatModel(responses=["output"])

    def node(s, config):
        return {"market_report": llm.invoke("prompt", config).content}

    result = run(AttemptRecorder(tmp_path, "attempt-one"), node=node)
    assert not (tmp_path / "trace").exists()
    metadata = list(result["model_call_metadata"].values())
    assert len(metadata) == 1 and metadata[0]["stage"] == "Market Analyst"
    assert "prompt" not in str(metadata) and "output" not in str(metadata)


def test_post_graph_summary_is_in_attempt_trace(tmp_path, monkeypatch):
    from tests.test_publication_graph import graph_and_state

    monkeypatch.setenv("TRADINGAGENTS_TRACE", "1")
    app, final_state = graph_and_state(tmp_path / "records")
    app.callbacks = [AttemptRecorder(tmp_path / "attempt", "attempt-one")]
    app.record_decision("DOCN", "2026-11-04", final_state)
    rows = events(tmp_path / "attempt")
    assert {row["stage"] for row in rows} == {"Executive Summary"}
    assert rows[-1]["event"] == "stage_end"


@pytest.mark.parametrize("fail", [False, True])
def test_real_tool_arguments_returns_and_errors_exclude_secrets(tmp_path, monkeypatch, fail):
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from langgraph.graph import END, START, StateGraph
    from langgraph.prebuilt import ToolNode

    from tradingagents.agents.state import AgentState

    monkeypatch.setenv("TRADINGAGENTS_TRACE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-private-token")

    @tool
    def echo(value: str) -> str:
        """Return the requested text for a controlled provider-boundary proof."""
        if fail:
            raise RuntimeError(value)
        return value

    graph = StateGraph(AgentState)
    graph.add_node("tools", ToolNode([echo], handle_tool_errors=lambda error: "unavailable"))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    initial = {**state(), "messages": [AIMessage(content="", tool_calls=[{
        "name": "echo", "args": {"value": "synthetic-private-token"}, "id": "call"
    }])]}
    observed_node(graph.compile(), "Market Analyst")(
        initial, {"callbacks": [AttemptRecorder(tmp_path, "attempt-one")]})
    rows = events(tmp_path)
    assert "synthetic-private-token" not in str(rows)
    assert "[REDACTED]" in str(rows)
    assert "tool_start" in {row["event"] for row in rows}
    assert ("tool_error" if fail else "tool_end") in {row["event"] for row in rows}
