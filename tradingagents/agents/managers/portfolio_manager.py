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

from tradingagents.agents.audit_pass import prepare_audit_dispositions, render_advisory_audit
from tradingagents.agents.context import (
    EVIDENCE_DISCIPLINE,
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
)
from tradingagents.agents.decision_context import (
    DECISION_HORIZON_CONTRACT,
    horizon_incomplete,
    validate_final_case,
)
from tradingagents.agents.rating import parse_rating
from tradingagents.agents.schemas import RequiredHorizonPortfolioDecision, render_pm_decision
from tradingagents.agents.structured import NO_EXTERNAL_TOOLS, bind_structured, invoke_structured
from tradingagents.agents.valuation import TargetResult
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.financial_evidence import EvidencePackage, bounded_evidence_view


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, RequiredHorizonPortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state, include_mechanical=True)
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

        audit_context = (render_advisory_audit(state["advisory_audit"], dispositions=prepare_audit_dispositions(state))
                         if "advisory_audit" in state else
                         "Advisory audit was not run for this legacy or incomplete state.")
        audit_projection = prepare_audit_dispositions(state)
        if (isinstance(state.get("advisory_audit"), dict)
                and state["advisory_audit"].get("status") == "completed with findings"
                and audit_projection['findings']):
            audit_context += "\nSupply one audit_dispositions response per finding in this call: exact finding_id, disposition accepted/rejected, and short reason. Missing responses stay unanswered; no rating or publication gate."
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

**Rating Scale**:
- **Buy**: Strong conviction to enter/add
- **Overweight**: Favorable, gradually increase exposure
- **Hold**: Maintain position
- **Underweight**: Reduce exposure/partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

{audit_context}
Audit findings are unverified advice, never rating authority. An unavailable audit implies no clearance; normal evidence limits apply.

**Canonical financial facts for optional valuation_request (bounded view):**
{canonical_facts}
Select a supported active case through valuation_request with method "case", exact case_id and integer version.
For a case-period value only, explicitly set rerating_assumption to "none" and omit decision_date.
A dated link needs a future date within your stated decision horizon and a substantive rerating assumption.
Capital and the multiple must be suitable at that date. Never derive a horizon price by discounting or interpolation.
If no case is adopted, omit valuation_request and state why in no_case_reason. The rating remains your research opinion.

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

Write in order, rating first:

- **Rating**: exactly one of Buy / Overweight / Hold / Underweight / Sell
- **Executive Summary**: call and action
- **Investment Thesis**: decisive evidence and reconsideration conditions
- **Time Horizon**: REQUIRED explicit days/weeks/months or YYYY-MM-DD. Never infer from forecasts or default to 3–6 months; unknown means incomplete, rating unchanged.

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
                "contract_version": DECISION_HORIZON_CONTRACT,
                "case_contract": 1,
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
            target = validate_final_case({**state, "unvalidated_outputs": original}, request)
            final_trade_decision = render_pm_decision(decision, target)
            final_rating = decision.rating.value
        else:
            final_trade_decision = llm.invoke(prompt).content
            final_rating = parse_rating(final_trade_decision)
            thesis_candidate = {"rationale": final_trade_decision[:3000]}
            original["portfolio_manager"] = {"fallback": final_trade_decision, "contract_version": DECISION_HORIZON_CONTRACT}
            target = TargetResult(
                status="unsupported",
                reasons=(
                    "Free-text fallback has no validated structured valuation bridge; target omitted.",
                ),
            )

        if horizon_incomplete({"unvalidated_outputs": original}):
            final_trade_decision += "\n\nDecision incomplete: explicit decision horizon missing or invalid; no horizon inferred."

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
