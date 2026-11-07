"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

import json

from tradingagents.agents.context import (
    EVIDENCE_DISCIPLINE,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.shared_valuation import replay_cases
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state, include_mechanical=True)
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

The debate always contains conflicting arguments; deciding which side is stronger is the job, so conflict alone is not a reason to Hold. Commit to the side with the stronger case, sized by how decisively it wins. Choose Hold only when the evidence is still balanced after that weighing, or too thin to support a call; do not manufacture a direction to appear decisive. Weigh the bull and bear cases on their merits, independent of which side spoke first or last.

---

Use the shared valuation scenarios, when available, to distinguish disputed assumptions from established inputs. In revised_cases you may supply one complete revised list in the analyst format, preserving existing names for the same case. Copy original requests and change only assumptions you justify. Otherwise omit revised_cases. Explain which assumptions the debate supports and what would change the case. Do not promote a scenario or an uncalculated debate alternative into a validated final target.

**Debate History:**
{history}

## Output

Write these sections, in this order, starting with the recommendation on its own line:

- **Recommendation**: exactly one of Buy / Overweight / Hold / Underweight / Sell
- **Rationale**: which arguments decided it
- **Strategic Actions**: qualitative steps for the trader; numerical sizing requires actual portfolio and loss-budget inputs

{NO_EXTERNAL_TOOLS}""" + EVIDENCE_DISCIPLINE + get_language_instruction()

        saved = replay_cases(state) if state.get("shared_valuation_scenarios") else {}
        if saved.get("status") not in (None, "not_applicable"):
            from tradingagents.agents.analysts.fundamentals_analyst import SHARED_VALUATION_INPUTS

            prompt += "\nFor any optional revised_cases use the following analyst input contract, returning the list in revised_cases instead of a fence:\n" + SHARED_VALUATION_INPUTS
        if saved.get("requests"):
            prompt += "\nOriginal case inputs (unvalidated model assumptions):\n" + json.dumps(saved["requests"])
        decision = invoke_structured(structured_llm, prompt, "Research Manager")
        investment_plan = render_research_plan(decision) if decision is not None else llm.invoke(prompt).content
        revision = {}
        if decision is not None and decision.revised_cases is not None and saved:
            revision["shared_valuation_scenarios"] = replay_cases(state, revision=decision.revised_cases)

        new_investment_debate_state = {
            **investment_debate_state,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            **revision,
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
