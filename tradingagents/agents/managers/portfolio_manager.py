"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call. Its rating is the run's
``final_rating``, and the decision is rendered to markdown as
``final_trade_decision`` for the memory log, CLI display and saved reports.
When a provider does not expose structured output, the agent falls back to
free-text generation and the rating is read from that text.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from tradingagents.agents.audit_pass import render_advisory_audit
from tradingagents.agents.context import (
    EVIDENCE_DISCIPLINE,
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
)
from tradingagents.agents.rating import parse_rating
from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.structured import NO_EXTERNAL_TOOLS, bind_structured, invoke_structured
from tradingagents.agents.valuation import TargetResult, validate_target
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.financial_evidence import EvidencePackage, bounded_evidence_view


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        package = None
        canonical_facts = "Canonical financial evidence unavailable; omit valuation_request."
        try:
            candidate = state.get("financial_evidence")
            package = EvidencePackage.model_validate(
                candidate.model_dump() if isinstance(candidate, EvidencePackage) else candidate
            )
            canonical_facts = bounded_evidence_view(package).model_dump_json()
        except (ValidationError, TypeError, ValueError):
            pass

        outlooks = grounded_outlooks(state)
        outlook_context = json.dumps([outlook.model_dump(mode="json") for outlook in outlooks])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        audit_context = (render_advisory_audit(state["advisory_audit"])
                         if "advisory_audit" in state else
                         "Advisory audit was not run for this legacy or incomplete state.")
        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

{portfolio_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

{audit_context}
Treat audit findings as unverified advice. State which findings mattered to your decision,
or state that none changed it. If the audit is unavailable, do not imply it cleared the analysis.
You retain the rating decision and normal evidence limits.

**Canonical financial facts for optional valuation_request (bounded view):**
{canonical_facts}
Use only these exact fact IDs for a supported EV/revenue or P/E request. Forecasts,
multiples and scenario weights are assumptions, not verified outcomes. A legacy
price_target does not establish a target. Management guidance/ambition cannot be
self-certified: without a separately validated outlook mapping, omit that claim.
Use multiple_assumption_date for each multiple (the current analysis date for your
subjective assumption). A multi-scenario final request requires weight_rationale;
weights are subjective, never calibrated probabilities. A dated decision valuation
requires both decision_date and an explicit rerating_assumption. A future annual
value is otherwise only a sensitivity, not a three-/six-month price target.
For material financing or dilution, use capital_structure_assumption=forward_capital_v1
and the typed funding bridge: cash flow, capex, acquisitions, explicit debt/lease
changes, equity issuance and other share dilution. Assumptions must cover the
entire interval after the source capital snapshot to the forecast end. Never fill
a funding gap silently; unavailable assumptions may leave valuation unsupported.
An unchanged snapshot remains an explicitly limited sensitivity. A risk-based
Underweight does not establish a negative expected return.

**Source-grounded management outlook records (guidance and ambitions are distinct):**
{outlook_context}
Use a record_id as outlook_id only when period, metric, unit and basis match.
Disclose divergence from these ranges; do not invent consensus.

---

Ground conclusions in specific evidence. Weigh competing cases independently of speaking order. Choose Hold for balanced or insufficient evidence; conflict alone is not a reason to Hold. Do not force a direction to appear decisive.

## Advisory thesis continuity

Supply thesis_candidate in this call: rationale, assumptions, canonical references
and measurable advisory conditions, never hard rules. Use exact canonical metric
and metric_definition, unit/basis, period and expiry. Gross Margin uses Gross
Profit / Revenue: metric/definition "Gross Margin", unit "percent", basis US-GAAP.
Set thesis_role: supports_thesis supports the current thesis; reconsideration_trigger
means reconsider if met; unspecified means unknown intent. A trigger not met is
not a failed thesis. Never infer legacy intent from comparator or rating.
For each prior ID give kept/overridden/retired and a specific reason. Conditions
never choose the rating; unknown measurements stay unknown. Legacy rules, including
53% margin, have unestablished binding authority; never invent a sell instruction.

## Output

Write these sections, in this order, starting with the rating on its own line:

- **Rating**: exactly one of Buy / Overweight / Hold / Underweight / Sell
- **Executive Summary**: the call and how to act on it
- **Investment Thesis**: the evidence that decided it, and what would change it

{NO_EXTERNAL_TOOLS}{EVIDENCE_DISCIPLINE}{get_language_instruction()}"""

        # The typed rating is the decision; the rendered text only carries it.
        # Read back from text, a rating the thesis quotes could replace it.
        decision = invoke_structured(structured_llm, prompt, "Portfolio Manager")
        original = dict(state.get("unvalidated_outputs") or {})
        request = None
        thesis_candidate = None
        if decision is not None:
            thesis_candidate = decision._unvalidated_thesis_candidate
            if thesis_candidate is None and decision.thesis_candidate is not None:
                thesis_candidate = decision.thesis_candidate.model_dump(mode="json")
            if thesis_candidate is None:
                thesis_candidate = {"rationale": decision.investment_thesis}
            thesis_candidate = json.loads(json.dumps(thesis_candidate, default=str), parse_constant=str)
            request = decision._unvalidated_valuation_request
            if request is None and decision.valuation_request is not None:
                request = decision.valuation_request.model_dump(mode="json")
            # JSON-safe preservation also retains invalid optional requests;
            # nonfinite raw numeric tokens are diagnostic strings, not JSON NaN.
            request = json.loads(json.dumps(request, default=str), parse_constant=str)
            original["portfolio_manager"] = {
                "structured": json.loads(
                    json.dumps(
                        {**decision.model_dump(mode="json"), "valuation_request": request},
                        default=str,
                    ),
                    parse_constant=str,
                ),
                "valuation_request": request,
                "thesis_candidate": thesis_candidate,
            }
            target = (
                validate_target(request, package, outlooks)
                if package is not None
                else TargetResult(
                    status="unsupported",
                    reasons=("Canonical financial evidence unavailable; target omitted.",),
                )
            )
            final_trade_decision = render_pm_decision(decision, target)
            final_rating = decision.rating.value
        else:
            final_trade_decision = llm.invoke(prompt).content
            final_rating = parse_rating(final_trade_decision)
            thesis_candidate = {"rationale": final_trade_decision[:3000]}
            original["portfolio_manager"] = {"fallback": final_trade_decision}
            target = TargetResult(
                status="unsupported",
                reasons=(
                    "Free-text fallback has no validated structured valuation bridge; target omitted.",
                ),
            )

        new_risk_debate_state = {
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
            "final_rating": final_rating,
            "target_validation": {**target.model_dump(mode="json"), "request": request},
            "unvalidated_outputs": original,
            "thesis_candidate": thesis_candidate,
        }

    return portfolio_manager_node
