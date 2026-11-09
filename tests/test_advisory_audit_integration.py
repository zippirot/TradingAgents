import pytest

from tradingagents.agents.audit_pass import render_advisory_audit
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import RISK_ANALYSIS_PATH_MAP
from tradingagents.reporting import evidence_appendix, evidence_snapshot


def test_risk_debate_routes_through_advisory_audit_before_portfolio_manager():
    assert ConditionalLogic(1, 1).should_continue_risk_analysis({
        "risk_debate_state": {"count": 3, "latest_speaker": "Neutral Analyst"}
    }) == "Portfolio Manager"
    assert RISK_ANALYSIS_PATH_MAP["Portfolio Manager"] == "Advisory Audit"
    assert "Portfolio Manager" not in RISK_ANALYSIS_PATH_MAP.values()


def test_audit_is_retained_in_evidence_and_rendered_only_for_new_runs():
    record = {
        "status": "completed with findings",
        "findings": [{"role": "trader", "quoted_claim": "Buy at 120",
                      "issue_type": "unsupported_claim", "evidence_label": None,
                      "explanation": "No support in supplied material."}],
        "counts_by_type": {"unsupported_claim": 1},
        "rejected_count": 0,
        "independence_by_role": {"trader": "different model", "research_manager": "same model"},
    }
    state = {"advisory_audit": record, "evidence_quality": {"status": "limited"}}
    assert evidence_snapshot(state)["advisory_audit"] == record
    assert "Buy at 120" in evidence_appendix(state)
    legacy = {"evidence_quality": {"status": "limited"}}
    assert "Advisory audit" not in evidence_appendix(legacy)
    assert "research manager" in render_advisory_audit(record)


def test_compiled_graph_has_one_audit_step_between_risk_and_pm():
    from tradingagents.graph.setup import GraphSetup

    workflow = GraphSetup(object(), object(), ConditionalLogic(), 1).setup_graph(["market"])
    assert ("Advisory Audit", "Portfolio Manager") in workflow.edges
    assert ("Portfolio Manager", "Run Metrics") in workflow.edges


def test_portfolio_manager_receives_findings_without_rating_authority():
    from unittest.mock import MagicMock

    from tests.test_portfolio_valuation import decision, state
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

    inputs = state()
    inputs["advisory_audit"] = {
        "status": "completed with findings", "counts_by_type": {"contradiction": 1},
        "independence_by_role": {"research_manager": "same model"},
        "findings": [{"role": "trader", "quoted_claim": "Buy at 120",
                      "issue_type": "contradiction", "evidence_label": None,
                      "explanation": "Conflicts with the brief."}],
    }
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = decision(rating="Hold")
    output = create_portfolio_manager(llm)(inputs)
    prompt = str(llm.with_structured_output.return_value.invoke.call_args.args[0])
    assert "Buy at 120" in prompt
    assert "one audit_dispositions response per finding" in prompt
    assert output["final_rating"] == "Hold"
    assert "advisory_audit" not in output


@pytest.mark.parametrize("pause_before", ["Advisory Audit", "Portfolio Manager"])
@pytest.mark.parametrize("retry", [False, True])
def test_checkpoint_resume_does_not_duplicate_audit_or_pm_calls(pause_before, retry):
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph

    from tradingagents.agents.audit_pass import create_advisory_audit
    from tradingagents.agents.state import AgentState

    class AuditModel:
        calls = 0

        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            self.calls += 1
            if retry and self.calls == 1:
                raise TimeoutError("offline forced first attempt failure")
            return {"findings": []}

    model = AuditModel()
    pm_calls = []

    def pm(state):
        pm_calls.append(state["advisory_audit"]["status"])
        return {"final_rating": "Hold", "final_trade_decision": "**Rating**: Hold"}

    workflow = StateGraph(AgentState)
    workflow.add_node("Risk Debate", lambda state: {"risk_debate_state": {"count": 3, "history": "risk"}})
    workflow.add_node("Advisory Audit", create_advisory_audit(model, deep_model_id="deep", quick_model_id="quick", sdk_retries_disabled=True))
    workflow.add_node("Portfolio Manager", pm)
    workflow.add_edge(START, "Risk Debate")
    workflow.add_edge("Risk Debate", "Advisory Audit")
    workflow.add_edge("Advisory Audit", "Portfolio Manager")
    workflow.add_edge("Portfolio Manager", END)
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": f"audit-{pause_before}"}}
    paused = workflow.compile(checkpointer=saver, interrupt_before=[pause_before])
    paused.invoke({"messages": [], "company_of_interest": "DOCN"}, config=config)
    assert model.calls == (0 if pause_before == "Advisory Audit" else 1 + retry)
    assert not pm_calls
    complete = workflow.compile(checkpointer=saver)
    result = complete.invoke(None, config=config)
    assert result["advisory_audit"]["status"] == "completed with zero findings"
    assert result["final_rating"] == "Hold"
    assert model.calls == 1 + retry
    assert pm_calls == ["completed with zero findings"]


def test_over_limit_audit_reports_rejected_submission_count():
    from tradingagents.agents.audit_pass import create_advisory_audit

    class TooMany:
        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            return {"findings": [{}] * 21}

    record = create_advisory_audit(TooMany(), deep_model_id="d", quick_model_id="q")({})["advisory_audit"]
    assert record["status"] == "unavailable"
    assert record["submitted_count"] == 21
    assert record["rejected_count"] == 21


def test_configured_slots_alone_cannot_establish_model_independence():
    from tradingagents.agents.audit_pass import create_advisory_audit

    class Empty:
        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            return {"findings": []}

    state = {"market_report": "price", "investment_plan": "plan",
             "trader_investment_plan": "trade",
             "investment_debate_state": {"bull_history": "bull", "bear_history": "bear"},
             "risk_debate_state": {"aggressive_history": "risk"}}
    different = create_advisory_audit(
        Empty(), deep_model_id="anthropic/claude-opus-5.5", quick_model_id="openai/gpt-6.1-sol"
    )(state)["advisory_audit"]
    same = create_advisory_audit(
        Empty(), deep_model_id="openai/gpt-6.1-terra-pro", quick_model_id="openai/gpt-6.1-terra-pro"
    )(state)["advisory_audit"]
    assert all(flag == "unknown" for flag in different["independence_by_role"].values())
    assert all(flag == "unknown" for flag in same["independence_by_role"].values())
