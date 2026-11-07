import unittest

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from tradingagents.graph.analyst_execution import (
    AnalystNodeSpec,
    build_analyst_execution_plan,
)


@pytest.mark.unit
@pytest.mark.parametrize("outcomes,expected,shared", [
    (["DATA_UNAVAILABLE: no source"], True, False),
    (["NO_DATA_AVAILABLE: no rows", "usable data"], False, False),
    ([], False, False),
    (["NO_DATA_AVAILABLE: no rows"], True, True),
    (["  \n  "], True, False),
])
def test_analyst_tool_support_warning_reaches_report_and_evidence(outcomes, expected, shared):
    from tradingagents.graph.setup import _analyst_graph

    @tool
    def lookup(query: str) -> str:
        """Read offline fixture."""
        return outcomes.pop(0)

    seen = []
    def agent(state):
        seen.append(state["messages"])
        if len(seen) == 1 and outcomes:
            return {"messages": [AIMessage(content="", tool_calls=[
                {"name": "lookup", "args": {"query": "x"}, "id": f"call_{i}"}
                for i in range(len(outcomes))])], "market_report": ""}
        return {"messages": [AIMessage(content="Report")], "market_report": "Report"}

    spec = AnalystNodeSpec("market", "Market Analyst", "market_report", (lookup,))
    result = _analyst_graph(spec, agent, 2).invoke({"messages": [], "company_of_interest": "X", "trade_date": "2026-01-01",
                                                  "shared_source_brief": "Independent filing" if shared else ""})
    assert result["audit_market_tool_evidence"]["all_tools_failed"] is expected
    assert result["market_report"].startswith("Warning: requested tool calls supplied no support") is expected
    if expected:
        assert any(isinstance(m, ToolMessage) for m in seen[-1])
    assert ("Separately supplied shared filing evidence" in result["market_report"]) is shared


@pytest.mark.unit
@pytest.mark.parametrize("raised", [True, False])
def test_vendor_secret_never_reaches_next_analyst_turn_or_evidence(raised, caplog, tmp_path):
    from cli.run_logging import cleanup_run_logging, configure_run_logging
    from tradingagents.graph.setup import _analyst_graph

    secret = "dummy-secret-987"
    @tool
    def lookup(query: str) -> str:
        """Read offline fixture."""
        if raised:
            raise RuntimeError(secret)
        from tradingagents.dataflows.router import vendor_unavailable
        return vendor_unavailable("lookup", RuntimeError(secret))

    seen = []
    def agent(state):
        seen.append(state["messages"])
        if len(seen) == 1:
            return {"messages": [AIMessage(content="", tool_calls=[
                {"name": "lookup", "args": {"query": "x"}, "id": "c1"}])], "market_report": ""}
        return {"messages": [AIMessage(content="No data")], "market_report": "No data"}

    spec = AnalystNodeSpec("market", "Market Analyst", "market_report", (lookup,))
    log_path = configure_run_logging(tmp_path)
    try:
        result = _analyst_graph(spec, agent, 2).invoke({"messages": [], "company_of_interest": "X", "trade_date": "2026-01-01"})
    finally:
        cleanup_run_logging()
    assert "DATA_UNAVAILABLE:" in str(seen[-1])
    assert "Warning: requested tool calls supplied no support" in result["market_report"]
    assert result["audit_market_tool_evidence"]["all_tools_failed"] is True
    assert secret not in str(seen) + str(result) + caplog.text + log_path.read_text()


class AnalystExecutionPlanTests(unittest.TestCase):
    def test_build_plan_preserves_selected_order(self):
        plan = build_analyst_execution_plan(["news", "market"])

        self.assertEqual([spec.key for spec in plan.specs], ["news", "market"])
        self.assertEqual(plan.specs[0].agent_node, "News Analyst")
        self.assertEqual(plan.specs[0].report_key, "news_report")
        self.assertFalse(hasattr(plan.specs[0], "clear_node"))

    def test_rejects_unknown_analyst_keys(self):
        with self.assertRaises(ValueError):
            build_analyst_execution_plan(["market", "macro"])

    def test_social_key_displays_as_sentiment_analyst(self):
        # The wire key stays "social" for saved-config back-compat, but the
        # user-visible agent_node label must match the v0.2.5 rename so the
        # wall-time summary and any future consumer of agent_node says
        # "Sentiment Analyst" rather than the legacy "Social Analyst".
        plan = build_analyst_execution_plan(["social"])
        spec = plan.specs[0]
        self.assertEqual(spec.key, "social")
        self.assertEqual(spec.agent_node, "Sentiment Analyst")
        self.assertEqual(spec.report_key, "sentiment_report")
