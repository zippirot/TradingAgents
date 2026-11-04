"""Mark model prose in stream views before the final publication boundary.

These projections never flow back into LangGraph state or tool invocation data.
"""

from langchain_core.messages import AIMessage

PROVISIONAL = "[Provisional, unvalidated model output — not a published decision.]\n"
_REPORT_FIELDS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
)
_DEBATE_FIELDS = ("investment_debate_state", "risk_debate_state")
_DEBATE_TEXT = {
    "history",
    "bull_history",
    "bear_history",
    "aggressive_history",
    "conservative_history",
    "neutral_history",
    "current_response",
    "current_aggressive_response",
    "current_conservative_response",
    "current_neutral_response",
}


def provisional_text(value: str) -> str:
    """Prefix once; leave empty and already qualified prose unchanged."""
    if not value or value.startswith(PROVISIONAL):
        return value
    return PROVISIONAL + value


def provisional_messages(messages):
    """Copy AI prose while retaining IDs, tool calls and tool results exactly."""
    result = []
    for message in messages:
        if not isinstance(message, AIMessage):
            result.append(message)
            continue
        content = message.content
        if isinstance(content, str):
            updated = provisional_text(content)
        elif isinstance(content, list):
            updated = []
            marked = False
            for block in content:
                if not marked and isinstance(block, str) and block:
                    updated.append(provisional_text(block))
                    marked = True
                elif (
                    not marked
                    and isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                    and block["text"]
                ):
                    updated.append({**block, "text": provisional_text(block["text"])})
                    marked = True
                else:
                    updated.append(block)
        else:
            updated = content
        result.append(
            message if updated == content else message.model_copy(update={"content": updated})
        )
    return result


def _canonical_final(state: dict) -> bool:
    quality = state.get("evidence_quality") or {}
    return bool(
        state.get("final_trade_decision")
        and (
            state.get("unvalidated_outputs") is not None
            or (quality.get("status") == "insufficient" and state.get("final_rating") == "REVIEW")
        )
    )


def provisional_state(state: dict | None):
    """Copy exposed report fields; preserve all other state and original objects."""
    if state is None:
        return None
    projected = dict(state)
    if "messages" in projected:
        projected["messages"] = provisional_messages(projected["messages"])
    if _canonical_final(state):
        return projected
    for field in _REPORT_FIELDS:
        if isinstance(projected.get(field), str):
            projected[field] = provisional_text(projected[field])
    for field in _DEBATE_FIELDS:
        debate = projected.get(field)
        if isinstance(debate, dict):
            projected[field] = {
                key: provisional_text(value)
                if key in _DEBATE_TEXT and isinstance(value, str)
                else value
                for key, value in debate.items()
            }
    return projected
