"""Deterministic publication boundaries for research outcomes."""

from pydantic import ValidationError

from tradingagents.agents.evidence_validation import review_terminal_state
from tradingagents.agents.rating import normalized_evidence_quality
from tradingagents.agents.schemas import render_target_result
from tradingagents.agents.valuation import TargetResult, validate_target
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.financial_evidence import EvidencePackage


def enforce_evidence_review(state: dict) -> dict:
    """An evidence failure cannot be overridden by model prose or a stale rating."""
    quality = normalized_evidence_quality(state)
    if quality.get("status") != "insufficient":
        return {}
    original = dict(state.get("unvalidated_outputs") or {})
    for field in ("final_trade_decision", "investment_plan", "trader_investment_plan",
                  "investment_debate_state", "risk_debate_state", "target_validation"):
        if state.get(field) and field not in original:
            original[field] = state[field]
    return {
        **review_terminal_state(quality),
        "unvalidated_outputs": original,
        "target_validation": TargetResult(
            status="unsupported", reasons=("Research incomplete; valuation not published.",),
        ).model_dump(mode="json"),
    }


def enforce_publication(state: dict) -> dict:
    """Project new runs into canonical decisions, retaining raw prose separately.

    A language heuristic cannot prove that arbitrary prose agrees with a numeric
    valuation or a loss budget. Keep that prose as diagnostics and publish the
    independently checked record. Historical states have no evidence contract
    and are left intact; new exports label them legacy/unvalidated.
    """
    review = enforce_evidence_review(state)
    if review:
        return review
    if state.get("evidence_quality") is None:
        return {}
    from tradingagents.agents.rating import run_rating

    originals = dict(state.get("unvalidated_outputs") or {})
    updates = {}
    for field in (
        "investment_plan", "trader_investment_plan", "final_trade_decision",
        "investment_debate_state", "risk_debate_state",
    ):
        originals.setdefault(field, state.get(field))
    context = state.get("canonical_financial_context") or (
        "Detailed financial evidence is unavailable for this analysis scope. "
        "No fundamental fair-value calculation is published."
    )
    for field in ("market_report", "sentiment_report", "news_report", "fundamentals_report"):
        if state.get(field):
            originals.setdefault(field, state[field])
            if field == "fundamentals_report" and state.get("canonical_financial_context"):
                updates[field] = context
            else:
                updates[field] = (
                    "**Unvalidated model narrative — quoted prices, targets and sizing "
                    "are not validated recommendations.**\n\n" + originals[field]
                )
    updates["investment_plan"] = (
        "Research evidence summary\n\n" + context
        + "\n\nUnvalidated model reasoning is retained in evidence.json diagnostics."
    )
    updates["trader_investment_plan"] = (
        "Position sizing: qualitative guidance only. A numerical allocation is "
        "not published without verified portfolio, loss-budget and execution/gap assumptions.\n\n"
        "Technical entry and stop proposals remain unvalidated model diagnostics; "
        "they are not fundamental fair value."
    )
    for field in ("investment_debate_state", "risk_debate_state"):
        debate = state.get(field)
        if isinstance(debate, dict):
            updates[field] = {
                key: (
                    "Unvalidated debate narrative retained in evidence.json diagnostics."
                    if isinstance(value, str) and value else value
                )
                for key, value in debate.items()
            }
    saved_target = state.get("target_validation")
    request = saved_target.get("request") if isinstance(saved_target, dict) else None
    try:
        package = EvidencePackage.model_validate(state.get("financial_evidence"))
        target = validate_target(request, package, grounded_outlooks(state))
    except (ValidationError, ValueError, TypeError):
        target = TargetResult(
            status="unsupported",
            reasons=("Canonical financial evidence unavailable; target omitted.",),
        )
    updates["target_validation"] = {**target.model_dump(mode="json"), "request": request}
    target_text = render_target_result(target)
    if target.status != "supported":
        target_text = "Fundamental price target: unavailable.\\n\\n" + target_text
    updates["final_trade_decision"] = (
        f"**Rating**: {run_rating(state)}\n\n"
        "**Executive Summary**: Model recommendation; financial evidence and "
        "valuation coverage are shown below. This does not validate all model reasoning.\n\n"
        f"**Investment Thesis — canonical evidence**:\n\n{context}\n\n"
        f"{target_text}\n\n"
        "Position sizing: qualitative only; no validated numerical allocation.\n\n"
        "Original model narrative is retained separately in evidence.json diagnostics."
    )
    updates["unvalidated_outputs"] = originals
    return updates
