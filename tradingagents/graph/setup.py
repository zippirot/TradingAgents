import logging
from collections import Counter
from typing import Annotated, Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_fundamentals_analyst,
    create_market_analyst,
    create_neutral_debator,
    create_news_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_sentiment_analyst,
    create_trader,
)
from tradingagents.agents.analysts.turn import WRAP_UP
from tradingagents.agents.audit_evidence import AUDIT_TOOL_FIELDS, collect_tool_outputs
from tradingagents.agents.audit_pass import create_advisory_audit
from tradingagents.agents.document_access import merge_search_traces
from tradingagents.agents.document_questions import lookup_document_questions
from tradingagents.agents.evidence_validation import create_evidence_gate, create_source_acquisition
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.state import AgentState
from tradingagents.operational_capture import observed_node

from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)

# Every target a shared conditional router can return. Each edge driven by the
# router maps all of them, so a fall-through return (e.g. under prompt/i18n/
# refactor drift in the speaker labels) can never hit a missing path_map entry
# and crash LangGraph mid-run (#1088).
DEBATE_PATH_MAP = {
    "Bull Researcher": "Bull Researcher",
    "Bear Researcher": "Bear Researcher",
    "Research Manager": "Document Followup",
}
RISK_ANALYSIS_PATH_MAP = {
    "Aggressive Analyst": "Aggressive Analyst",
    "Conservative Analyst": "Conservative Analyst",
    "Neutral Analyst": "Neutral Analyst",
    "Portfolio Manager": "Advisory Audit",
}


def _tools_or_done(state) -> str:
    """Route an analyst's turn: run its tool calls, or finish with its report."""
    return "tools" if state["messages"][-1].tool_calls else END


def _analyst_graph(spec, agent, max_tool_rounds: int):
    """One analyst as a graph of its own: the model and its tools, on a private message history.

    It returns only its report, so analysts running side by side never write the
    same key, and its tool calls never reach the other analysts' messages. After
    ``max_tool_rounds`` rounds of tool calls it is told to write its report, and
    that turn ends it whatever it answers, so a model that keeps calling tools
    cannot run the graph into its recursion limit (#1420).
    """
    evidence_field = AUDIT_TOOL_FIELDS[spec.key]
    output_fields = {spec.report_key: str, evidence_field: dict}
    if spec.key in {"fundamentals", "news"}:
        output_fields["document_search_trace"] = Annotated[dict, merge_search_traces]
    if spec.key == "fundamentals":
        output_fields["disclosure_evidence"] = dict
    if spec.key == "news":
        output_fields["news_coverage"] = dict
    output = TypedDict(f"{spec.key.capitalize()}Report", output_fields)
    graph = StateGraph(AgentState, output_schema=output)
    def run_agent(state):
        return {"document_search_role": spec.key, **agent({**state, "document_search_role": spec.key})}

    graph.add_node("agent", run_agent)
    graph.add_edge(START, "agent")

    def finish(state):
        evidence = state.get(evidence_field) if spec.key == "social" else None
        evidence = dict(evidence or collect_tool_outputs(state, spec.key))
        calls = {call.get("id") for message in state.get("messages", [])
                 for call in (getattr(message, "tool_calls", None) or [])
                 if isinstance(call, dict) and isinstance(call.get("id"), str)}
        responses = [message for message in state.get("messages", [])
                     if getattr(message, "tool_call_id", None) in calls]
        failed = bool(calls) and not any(
            getattr(message, "status", None) != "error"
            and bool(str(message.content).strip())
            and not str(message.content).lstrip().startswith(("DATA_UNAVAILABLE:", "NO_DATA_AVAILABLE:"))
            for message in responses
        )
        evidence["all_tools_failed"] = failed
        result = {evidence_field: evidence}
        if failed:
            warning = "Warning: requested tool calls supplied no support for this report."
            if state.get("shared_source_brief") or state.get("disclosure_evidence"):
                warning += " Separately supplied shared filing evidence may still be available."
            result[spec.report_key] = warning + "\n\n" + (state.get(spec.report_key) or "")
        return result

    graph.add_node("finish", finish)
    graph.add_edge("finish", END)
    if not spec.tools:
        graph.add_edge("agent", "finish")
        return graph.compile()

    def calls(messages):
        return [call["name"] for m in messages for call in (getattr(m, "tool_calls", None) or [])]

    def rounds(messages) -> int:
        return sum(1 for m in messages if getattr(m, "tool_calls", None))

    def more_or_wrap_up(state) -> str:
        return "wrap_up" if rounds(state["messages"]) >= max_tool_rounds else "agent"

    def wrap_up(state):
        repeated = ", ".join(f"{name} x{n}" for name, n in Counter(calls(state["messages"])).most_common())
        logger.warning("%s used its %d tool rounds (%s); asking for its report",
                       spec.agent_node, max_tool_rounds, repeated)
        return agent({**state, "messages": [*state["messages"], HumanMessage(WRAP_UP)]})

    graph.add_node("tools", ToolNode(
        list(spec.tools),
        handle_tool_errors=lambda exc: f"DATA_UNAVAILABLE: tool failed ({type(exc).__name__}); do not infer values.",
    ))
    graph.add_node("wrap_up", wrap_up)
    graph.add_conditional_edges("agent", lambda state: "tools" if _tools_or_done(state) == "tools" else "finish",
                                ["tools", "finish"])
    graph.add_conditional_edges("tools", more_or_wrap_up, ["agent", "wrap_up"])
    graph.add_edge("wrap_up", "finish")
    return graph.compile()


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        conditional_logic: ConditionalLogic,
        max_tool_rounds: int,
        quick_model_id: str = "unknown",
        deep_model_id: str = "unknown",
        metrics_observer=None,
        audit_llm=None,
        audit_sdk_retries_disabled=False,
        publication_config=None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.conditional_logic = conditional_logic
        self.max_tool_rounds = max_tool_rounds
        self.quick_model_id = quick_model_id
        self.deep_model_id = deep_model_id
        self.metrics_observer = metrics_observer
        self.audit_llm = audit_llm if audit_llm is not None else deep_thinking_llm
        self.audit_sdk_retries_disabled = audit_sdk_retries_disabled
        self.publication_config = publication_config

    def setup_graph(
        self, selected_analysts=("market", "social", "news", "fundamentals"), memory_node=None
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Sentiment analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
            memory_node: Node that settles past decisions and returns the run's
                ``past_context``. It runs alongside the analysts.
        """
        plan = build_analyst_execution_plan(selected_analysts)

        analyst_factories = {
            "market": lambda: create_market_analyst(self.quick_thinking_llm),
            "social": lambda: create_sentiment_analyst(self.quick_thinking_llm),
            "news": lambda: create_news_analyst(self.quick_thinking_llm),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm),
        }

        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        raw_portfolio_manager = create_portfolio_manager(self.deep_thinking_llm)

        def portfolio_manager_node(state):
            decision = raw_portfolio_manager(state)
            return {**decision, **enforce_publication({**state, **decision})}


        workflow = StateGraph(AgentState)

        expected = ['Source Acquisition', *[spec.agent_node for spec in plan.specs],
                    'Evidence Check', 'Bull Researcher', 'Bear Researcher', 'Document Followup',
                    'Research Manager', 'Trader', 'Aggressive Analyst', 'Conservative Analyst',
                    'Neutral Analyst', 'Advisory Audit', 'Portfolio Manager', 'Run Metrics']
        if memory_node is not None:
            expected.append('Memory Log')

        def add_node(name, node, report_key=None):
            workflow.add_node(name, observed_node(
                node, name, report_key=report_key,
                expected_stages=expected if name == 'Source Acquisition' else None))

        for spec in plan.specs:
            add_node(spec.agent_node,
                     _analyst_graph(spec, analyst_factories[spec.key](), self.max_tool_rounds),
                     report_key=spec.report_key)

        def final_question_turn(node, role):
            def invoke(state):
                count = (state.get("investment_debate_state") or {}).get("count", 0)
                threshold = 2 * self.conditional_logic.max_debate_rounds - (2 if role == "bull" else 1)
                return node({**state, "_document_question_final_turn": count >= threshold})
            return invoke

        add_node("Bull Researcher", final_question_turn(bull_researcher_node, "bull"))
        add_node("Bear Researcher", final_question_turn(bear_researcher_node, "bear"))
        add_node("Document Followup", lookup_document_questions)
        workflow.add_edge("Document Followup", "Research Manager")
        add_node("Research Manager", research_manager_node, report_key="investment_plan")
        add_node("Trader", trader_node, report_key="trader_investment_plan")
        add_node("Aggressive Analyst", aggressive_analyst)
        add_node("Neutral Analyst", neutral_analyst)
        add_node("Conservative Analyst", conservative_analyst)
        add_node("Portfolio Manager", portfolio_manager_node, report_key="final_trade_decision")
        raw_audit = create_advisory_audit(
            self.audit_llm, deep_model_id=self.deep_model_id,
            quick_model_id=self.quick_model_id,
            sdk_retries_disabled=self.audit_sdk_retries_disabled)

        def audit_node(state):
            result = raw_audit(state)
            if self.metrics_observer:
                result["run_metrics"] = self.metrics_observer({**state, **result})
            return result

        def metrics_node(state):
            result = {"run_metrics": self.metrics_observer(state)} if self.metrics_observer else {}
            if (state.get("evidence_quality") or {}).get("status") == "insufficient" and "advisory_audit" not in state:
                # The existing REVIEW gate bypasses all decision calls. Disclose
                # the missing audit without invoking a model or changing the gate.
                result["advisory_audit"] = {
                    "status": "unavailable", "findings": [], "counts_by_type": {},
                    "submitted_count": 0, "accepted_count": 0, "rejected_count": 0,
                    "rejection_reasons": [], "independence_by_role": {},
                    "error": "not run: insufficient evidence; risk debate and Portfolio Manager were bypassed",
                }
            # Retain the display comparison before the terminal checkpoint, so
            # crash recovery verifies the same canonical publication payload.
            if self.publication_config is not None:
                result.update(enforce_publication(
                    {**state, **result}, publication_config=self.publication_config))
            return result

        add_node("Advisory Audit", audit_node)
        add_node("Run Metrics", metrics_node)

        # One retained source vintage precedes parallel analyst reasoning. The
        # memory log retains its independent start and joins every analyst before
        # evidence validation, preserving prior-thesis cutoff dependencies.
        first_steps = [spec.agent_node for spec in plan.specs]
        if memory_node is not None:
            add_node("Memory Log", memory_node)
            first_steps.append("Memory Log")
        add_node("Source Acquisition", create_source_acquisition(selected_analysts))
        workflow.add_edge(START, "Source Acquisition")
        for spec in plan.specs:
            workflow.add_edge("Source Acquisition", spec.agent_node)
        if memory_node is not None:
            workflow.add_edge(START, "Memory Log")
        evidence_gate = create_evidence_gate(selected_analysts)

        def evidence_with_scenarios(state):
            from tradingagents.agents.analysts.fundamentals_analyst import SHARED_VALUATION_INPUTS
            from tradingagents.agents.shared_valuation import prepare_with_correction

            checked = evidence_gate(state)
            if state.get("prior_thesis"):
                from tradingagents.memory.thesis import observe_conditions, render_prior_thesis
                usable = {**state, **checked} if checked.get("evidence_quality", {}).get("status") in {"sufficient", "limited"} else {}
                prior = {**state["prior_thesis"], "observations": observe_conditions(state["prior_thesis"], usable)}
                checked.update(prior_thesis=prior, thesis_context=render_prior_thesis(prior))
            from tradingagents.agents.event_comparison import prepare_event_comparison
            from tradingagents.agents.valuation_reference_flow import finalize_peer_reference
            from tradingagents.dataflows.config import get_config

            checked.update(finalize_peer_reference({**state, **checked}, get_config()))
            event = prepare_event_comparison({**state, **checked}, get_config())
            # A rejected submission gets one correction attempt by the analyst's own model.
            scenarios = prepare_with_correction({**state, **checked}, self.quick_thinking_llm, SHARED_VALUATION_INPUTS)
            return {**checked, "shared_valuation_scenarios": scenarios, "event_comparison": event}

        add_node("Evidence Check", evidence_with_scenarios)
        workflow.add_edge(first_steps, "Evidence Check")
        workflow.add_conditional_edges(
            "Evidence Check",
            lambda state: "Run Metrics" if state.get("evidence_quality", {}).get("status") == "insufficient" else "Bull Researcher",
            {"Run Metrics": "Run Metrics", "Bull Researcher": "Bull Researcher"},
        )

        # Both research-debate edges share the complete DEBATE_PATH_MAP (#1088).
        for debate_node in ("Bull Researcher", "Bear Researcher"):
            workflow.add_conditional_edges(
                debate_node,
                self.conditional_logic.should_continue_debate,
                DEBATE_PATH_MAP,
            )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        # All three risk edges share the complete RISK_ANALYSIS_PATH_MAP (#1088).
        for risk_node in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
            workflow.add_conditional_edges(
                risk_node,
                self.conditional_logic.should_continue_risk_analysis,
                RISK_ANALYSIS_PATH_MAP,
            )

        workflow.add_edge("Advisory Audit", "Portfolio Manager")
        workflow.add_edge("Portfolio Manager", "Run Metrics")
        workflow.add_edge("Run Metrics", END)

        return workflow
