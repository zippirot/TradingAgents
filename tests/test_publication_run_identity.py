"""Each invocation has identity independent of its resumable checkpoint key."""
from uuid import UUID

import pytest
from langgraph.graph import END, StateGraph

from tradingagents.agents.state import AgentState
from tradingagents.graph.checkpointer import get_checkpointer
from tradingagents.graph.propagation import Propagator


def test_new_invocations_differ_but_checkpoint_restart_preserves_identity(tmp_path):
    first = Propagator().create_initial_state('DOCN', '2026-11-04')
    second = Propagator().create_initial_state('DOCN', '2026-11-04')
    assert UUID(first['run_id']) != UUID(second['run_id'])
    fail = True
    def finish(state):
        if fail:
            raise RuntimeError('interrupted')
        return {'news_report': 'completed'}
    builder = StateGraph(AgentState)
    builder.add_node('finish', finish)
    builder.set_entry_point('finish')
    builder.add_edge('finish', END)
    config = {'configurable': {'thread_id': 'same-checkpoint-key'}}
    with get_checkpointer(str(tmp_path), 'DOCN') as saver:
        graph = builder.compile(checkpointer=saver)
        with pytest.raises(RuntimeError, match='interrupted'):
            graph.invoke(first, config=config)
    fail = False
    with get_checkpointer(str(tmp_path), 'DOCN') as saver:
        result = builder.compile(checkpointer=saver).invoke(None, config=config)
    assert result['run_id'] == first['run_id']
    assert result['news_report'] == 'completed'
