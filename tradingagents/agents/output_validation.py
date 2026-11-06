"""Deterministic publication boundaries for research outcomes."""

from copy import deepcopy

from pydantic import ValidationError

from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.evidence_presentation import readable_evidence
from tradingagents.agents.evidence_validation import review_terminal_state
from tradingagents.agents.rating import normalized_evidence_quality
from tradingagents.agents.schemas import render_target_result
from tradingagents.agents.shared_valuation import prepare_shared_valuation
from tradingagents.agents.valuation import TargetResult, validate_target
from tradingagents.agents.valuation_comparison import (
    compare_valuation,
    price_implied_valuation,
    render_price_implied_valuation,
    render_valuation_comparison,
)
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
        "valuation_price_comparison": {"status": "unavailable", "rows": [], "reason": "Research incomplete; comparison not published."},
        "price_implied_valuation": {"status": "unavailable", "rows": [], "reason": "Research evidence insufficient for a price-implied table."},
        "mechanical_valuation_grid": {"status": "unavailable", "reason": "Research evidence insufficient; mechanical grid withheld."},
        "target_validation": TargetResult(
            status="unsupported", reasons=("Research incomplete; valuation not published.",),
        ).model_dump(mode="json"),
    }


def _thesis_update(state):
    if not state.get("run_id") or not state.get("trade_date") or not (
        state.get("thesis_candidate") is not None or state.get("prior_thesis") or state.get("thesis")
    ):
        return {}
    from tradingagents.agents.rating import run_rating
    from tradingagents.memory.thesis import observe_conditions, prepare_thesis

    saved = state.get("thesis")
    published = state.get("publication_record")
    if (isinstance(saved, dict) and isinstance(published, dict)
            and published.get("decision_id") == state["run_id"]
            and published.get("published_at") and published.get("record_sha256")
            and saved.get("run_id") == state["run_id"]
            and saved.get("version_id") == state.get("thesis_version_id")
            and saved.get("as_of") == str(state["trade_date"])
            and saved.get("canonical_rating") == run_rating(state)):
        # Re-export is a view of this already published research version. Identity
        # migrations belong to a new invocation, never to the same frozen version.
        # Publication persistence separately checks the immutable payload hash.
        return {"thesis": deepcopy(saved), "thesis_version_id": saved["version_id"]}
    prior = state.get("prior_thesis")
    if prior:
        usable = state if normalized_evidence_quality(state).get("status") in {"sufficient", "limited"} else {}
        prior = {**prior, "observations": observe_conditions(prior, usable)}
    candidate = state.get("thesis_candidate")
    if candidate is None and state.get("thesis"):
        saved = state["thesis"]
        candidate = {**saved, "dispositions": [
            {"condition_id": row["condition_id"], "disposition": row["disposition"],
             "reason": row["disposition_reason"]} for row in saved.get("prior_conditions", [])
        ]}
    item = prepare_thesis(candidate, prior, run_rating(state), str(state["trade_date"]), state["run_id"],
                          financial_evidence=state.get("financial_evidence"))
    return {"thesis": item, "thesis_version_id": item["version_id"]}


def enforce_publication(state: dict) -> dict:
    """Project new runs into canonical decisions, retaining raw prose separately.

    A language heuristic cannot prove that arbitrary prose agrees with a numeric
    valuation or a loss budget. Keep that prose as diagnostics and publish the
    independently checked record. Historical states have no evidence contract
    and are left intact; new exports label them legacy/unvalidated.
    """
    review = enforce_evidence_review(state)
    if review:
        if "event_comparison" in state:
            review["event_comparison"] = {"status": "unavailable", "reason": "Research incomplete; event comparison withheld"}
        if "shared_valuation_scenarios" in state:
            review["shared_valuation_scenarios"] = prepare_shared_valuation({**state, **review}, [])
        continuity = _thesis_update({**state, **review})
        if continuity:
            from tradingagents.memory.thesis import render_thesis
            review.update(continuity)
            review["final_trade_decision"] += "\n\n" + render_thesis(continuity["thesis"])
        card = prepare_decision_context({**state, **review})
        review["decision_context"] = card
        review["final_trade_decision"] += "\n\n" + render_decision_context(card, include_mechanical=False)
        review["final_trade_decision"] += "\n\n" + render_price_implied_valuation(review["price_implied_valuation"])
        return review
    if state.get("evidence_quality") is None:
        return {}
    from tradingagents.agents.rating import run_rating

    originals = dict(state.get("unvalidated_outputs") or {})
    updates = {}
    if "shared_valuation_scenarios" in state:
        saved = state["shared_valuation_scenarios"]
        requests = saved.get("requests", []) if isinstance(saved, dict) else []
        updates["shared_valuation_scenarios"] = prepare_shared_valuation(state, requests)
    for field in (
        "investment_plan", "trader_investment_plan", "final_trade_decision",
        "investment_debate_state", "risk_debate_state",
    ):
        originals.setdefault(field, state.get(field))
    context = state.get("canonical_financial_context") or (
        "Detailed financial evidence is unavailable for this analysis scope. "
        "No fundamental fair-value calculation is published."
    )
    context = readable_evidence(context)
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
    comparison = compare_valuation(state, target, request)
    updates["valuation_price_comparison"] = comparison
    independent = price_implied_valuation(state)
    updates["price_implied_valuation"] = independent
    from tradingagents.agents.mechanical_valuation import mechanical_valuation_grid
    # Recompute every export from retained sources, never trust a saved grid.
    grid = mechanical_valuation_grid(state)
    updates["mechanical_valuation_grid"] = grid
    reference_text = ""
    if "valuation_reference" in state:
        from tradingagents.agents.valuation_reference_flow import (
            render_guidance_consensus,
            render_valuation_reference,
            replay_valuation_reference,
            validate_vendor_expectations,
        )
        try:
            reference = replay_valuation_reference(state, state["valuation_reference"])
        except (ValueError, TypeError, KeyError):
            originals.setdefault("valuation_reference", state["valuation_reference"])
            reference = {"status": "unavailable", "reason": "Retained valuation reference could not be verified"}
        updates["valuation_reference"] = reference
        updates["vendor_expectations"] = validate_vendor_expectations(state)
        reference_text = ("\n\n" + render_valuation_reference(reference) +
                          "\n\n" + render_guidance_consensus({**state, **updates}))
    target_text = (render_price_implied_valuation(independent) + reference_text + "\n\n"
                   + render_target_result(target) + "\n\n" + render_valuation_comparison(comparison))
    if "event_comparison" in state:
        from tradingagents.agents.event_comparison import (
            render_event_comparison,
            replay_event_comparison,
        )
        try:
            event = replay_event_comparison(state, state["event_comparison"])
        except (ValueError, TypeError, KeyError):
            event = {"status": "unavailable", "reason": "Retained event comparison could not be verified"}
        updates["event_comparison"] = event
        target_text += "\n\n" + render_event_comparison(event)
    if target.status != "supported" or not target.decision_use.final_target_eligible:
        target_text = "Fundamental price target: unavailable.\n\n" + target_text
    updates["final_trade_decision"] = (
        f"**Rating**: {run_rating(state)}\n\n"
        "**Executive Summary**: Model recommendation; financial evidence and "
        "valuation coverage are shown below. This does not validate all model reasoning.\n\n"
        f"{target_text}\n\n"
        f"**Investment Thesis — canonical evidence**:\n\n{context}\n\n"
        "Position sizing: qualitative only; no validated numerical allocation.\n\n"
        "Original model narrative is retained separately in evidence.json diagnostics."
    )
    continuity = _thesis_update({**state, **updates})
    if continuity:
        from tradingagents.memory.thesis import render_thesis
        updates.update(continuity)
        updates["final_trade_decision"] = updates["final_trade_decision"].replace(
            "**Investment Thesis — canonical evidence**:",
            render_thesis(continuity["thesis"]) + "\n\n**Investment Thesis — canonical evidence**:", 1)
    updates["unvalidated_outputs"] = originals
    card = prepare_decision_context({**state, **updates})
    updates["decision_context"] = card
    updates["final_trade_decision"] = updates["final_trade_decision"].replace(
        "**Executive Summary**:", render_decision_context(card, include_mechanical=False) + "\n\n**Executive Summary**:", 1)
    return updates
