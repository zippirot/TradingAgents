"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage

from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
)
from tradingagents.agents.schemas import (
    CARRIED_PLAN_HEADING,
    TraderProposal,
    label_legacy_trader_price,
    render_trader_proposal,
)
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)

_ACTION_LINE = re.compile(r"^\W*(?:action|final transaction proposal)\W+(?:buy|hold|sell)\b", re.I | re.M)
_REASONING = re.compile(r"^\W*reasoning\b", re.I | re.M)
_HEADING = re.compile(r"^[ \t]*(?:\*\*(?P<bold>[^*\n]+)\*\*|#{1,6}[ \t]+(?P<hash>[^\n]+))", re.M)
_CHECKPOINT = re.compile(r"\b(?:trigger|checkpoint)s?\b", re.I)


def _carried_plan(investment_plan: str) -> str:
    """The Research Manager's actions and checkpoint sections, copied word for word."""
    plan = investment_plan or ""
    marks = list(_HEADING.finditer(plan))
    actions, sections, covered = "", [], []
    for mark, following in zip(marks, [*marks[1:], None], strict=False):
        title = mark["bold"] or mark["hash"]
        end = following.start() if following else len(plan)
        if title.strip().rstrip(":").casefold() == "strategic actions" and not actions:
            actions = plan[mark.end():end].lstrip(": \n").rstrip()
            covered.append((mark.start(), end))
        elif _CHECKPOINT.search(title):
            sections.append(plan[mark.start():end].rstrip())
            covered.append((mark.start(), end))
    remainder = "".join(ch for index, ch in enumerate(plan) if not any(a <= index < b for a, b in covered))
    loose = [line.strip() for line in remainder.splitlines() if _CHECKPOINT.search(line)]
    lines = [CARRIED_PLAN_HEADING, ""]
    lines.append(actions or "No Strategic Actions section was found in the Research Manager's plan.")
    for block in (*sections, "\n".join(loose)):
        if block:
            lines += ["", block]
    return "\n".join(lines)


def _complete_fallback(text: str, investment_plan: str) -> str:
    if not get_language_instruction() and not _ACTION_LINE.search(text or ""):
        # A localized run may translate the label, so only English can be checked.
        raise ValueError("Trader free-text fallback has no Action line; no plan published")
    note = "" if _REASONING.search(text or "") else "\n\nThe free-text fallback has no Reasoning section."
    return f"{text}{note}\n\n{_carried_plan(investment_plan)}"


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        investment_plan = state["investment_plan"]
        # The research plan digests the debate but loses exact price structure;
        # give the Trader the technical market report so entry/stop levels are
        # grounded in real ATR / support-resistance / current price (#1167). The
        # report is empty when the user did not select the market analyst, so
        # only offer it (and the grounding instruction) when it has content.
        market_report = (state["market_report"] or "").strip()
        portfolio_context = get_portfolio_context_from_state(state)

        if market_report:
            grounding = (
                "Ground concrete price levels (purchase entry, reference sale level, stop-loss) in the technical "
                "market report's price structure -- current price, support/resistance, ATR, and "
                "volatility -- and use the research plan for direction and strategy. "
            )
            report_section = f"Technical Market Report:\n{market_report}\n\n"
        else:
            grounding = ""
            report_section = ""

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading agent analyzing market data to make investment decisions. "
                    "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
                    + grounding
                    # Entry/stop are numeric price fields. Asking for concrete
                    # levels invites a percentage ("15%"), which is not a price
                    # and fails the structured parse (#1288).
                    + "For Buy, optionally state a purchase entry price; for Sell, optionally state an advisory reference sale level. "
                    "A stop_loss is Buy-only. For Sell, optionally supply advisory_invalidation_level as a thesis reconsideration level; never an execution stop or short position proposal. "
                    "Never put a purchase entry on Sell or Hold. A sale reference is not an order, executable quote, "
                    "share quantity or instruction concerning unknown holdings. State price levels in quote currency "
                    "as absolute numbers, never percentages or ranges; omit unsupported levels. "
                    "Keep technical levels exactly as the market report states them; do not merge separate levels into bands. "
                    "Any claim about where prior trading did or did not occur must cite the Prior closes by price band table; "
                    "if that table is unavailable, say the historical claim is not checkable with these inputs. "
                    + NO_EXTERNAL_TOOLS
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Here is the research team's investment plan for {company_name}. "
                    f"{instrument_context}\n\n"
                    f"{report_section}"
                    f"{portfolio_context}\n\n"
                    f"Proposed Investment Plan:\n{investment_plan}\n\n"
                    "Make an informed, strategic trading decision.\n\n"
                    "## Output\n\n"
                    "Write these sections, in this order, starting with the action "
                    "on its own line:\n\n"
                    "- **Action**: exactly one of Buy / Hold / Sell. A research "
                    "recommendation of Overweight is a Buy and Underweight is a Sell, "
                    "sized by how strong the case is; conflict alone is not a Hold.\n"
                    "- **Reasoning**: why, against the plan and the price structure\n"
                    "- **Purchase Entry Price** for Buy, **Reference Sale Level** for Sell, **Stop Loss** for Buy or **Advisory Thesis Invalidation Level** for Sell, and **Position Sizing** in qualitative words only: holdings and loss budget are unknown, so give no percentages, fractions, share counts or currency amounts"
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            # The Research Manager's actions and triggers follow the proposal on
            # this path too, not only on the free-text fallback.
            lambda proposal: f"{render_trader_proposal(proposal)}\n\n{_carried_plan(investment_plan)}",
            "Trader",
            finish_freetext=lambda text: _complete_fallback(text, investment_plan),
        )

        trader_plan = label_legacy_trader_price(trader_plan)
        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
        }

    return trader_node
