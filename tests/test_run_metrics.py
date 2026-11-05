import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


class Counter:
    def __init__(self, calls=0):
        self.calls = calls

    def get_stats(self):
        return {"llm_calls": self.calls}


def owner(counter=None):
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph._metrics_callback = counter
    graph._metrics_observer_id = "current-process"
    graph._metrics_start = graph._callback_calls()
    return graph


@pytest.mark.parametrize("depth", [1, 2, 3, 5])
def test_completed_rounds_and_debate_characters_use_actual_state(depth):
    callback = Counter(4)
    graph = owner(callback)
    initial = graph._initial_run_metrics()
    callback.calls = 4 + 7 * depth
    state = {
        "run_metrics": initial,
        "investment_debate_state": {"count": 2 * depth, "history": "B" * (14 * depth)},
        "risk_debate_state": {"count": 3 * depth, "history": "R" * (21 * depth)},
    }
    metrics = graph._observe_run_metrics(state)
    assert metrics["research_rounds_completed"] == depth
    assert metrics["risk_rounds_completed"] == depth
    assert metrics["research_debate_characters"] == 14 * depth
    assert metrics["risk_debate_characters"] == 21 * depth
    assert metrics["model_calls"] == 7 * depth
    assert metrics["model_call_scope"] == "complete_observed"


def test_missing_callback_does_not_fabricate_call_count():
    graph = owner()
    metrics = graph._observe_run_metrics({
        "run_metrics": graph._initial_run_metrics(),
        "investment_debate_state": {"count": 4, "history": "research"},
        "risk_debate_state": {"count": 6, "history": "risk"},
    })
    assert metrics["model_calls"] is None
    assert metrics["model_call_scope"] == "unavailable"
    assert metrics["research_rounds_completed"] == 2
    assert metrics["risk_rounds_completed"] == 2


def test_restarted_callback_preserves_partial_scope_after_later_node():
    graph = owner(Counter(0))
    state = {
        "run_metrics": {"observer_id": "old-process", "model_calls": 9,
                        "model_call_scope": "complete_observed", "callback_baseline": 0},
        "investment_debate_state": {"count": 2, "history": "debate"},
        "risk_debate_state": {"count": 3, "history": "risk"},
    }
    graph._metrics_callback.calls = 1
    at_audit = graph._observe_run_metrics(state)
    assert at_audit["model_calls"] == 10
    assert at_audit["model_call_scope"] == "partial_observed"
    graph._metrics_callback.calls = 2
    after_pm = graph._observe_run_metrics({**state, "run_metrics": at_audit})
    assert after_pm["model_calls"] == 11
    assert after_pm["model_call_scope"] == "partial_observed"


def test_reused_graph_counts_each_run_from_its_own_baseline():
    counter = Counter(3)
    graph = owner(counter)
    first = graph._initial_run_metrics()
    counter.calls = 10
    assert graph._observe_run_metrics({"run_metrics": first})["model_calls"] == 7
    second = graph._initial_run_metrics()
    counter.calls = 13
    assert graph._observe_run_metrics({"run_metrics": second})["model_calls"] == 3
