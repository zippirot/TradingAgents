"""Deterministic publication boundaries for research outcomes."""

from copy import deepcopy

from tradingagents.agents.decision_context import (
    _display,
    final_request,
    prepare_decision_context,
    render_case_summary,
    render_decision_context,
    validate_final_case,
)
from tradingagents.agents.evidence_presentation import readable_evidence
from tradingagents.agents.evidence_validation import review_terminal_state
from tradingagents.agents.rating import normalized_evidence_quality
from tradingagents.agents.schemas import render_target_result
from tradingagents.agents.shared_valuation import (
    annotate_disputed_cases,
    prepare_shared_valuation,
    replay_cases,
)
from tradingagents.agents.valuation import TargetResult
from tradingagents.agents.valuation_comparison import (
    compare_valuation,
    price_implied_valuation,
    render_price_implied_valuation,
    render_valuation_comparison,
)


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
                          financial_evidence=state.get("financial_evidence"),
                          price_observation=state.get("price_observation"),
                          ticker=state.get("company_of_interest"))
    return {"thesis": item, "thesis_version_id": item["version_id"]}


def _decision_card(state, publication_config):
    card = prepare_decision_context(state)
    if publication_config is not None and card.get('assumption_changes', {}).get('comparison_version') != 2:
        from tradingagents.agents.assumption_history import assumption_changes

        card['assumption_changes'] = assumption_changes(
            publication_config, state.get('company_of_interest', ''), {**state, 'horizon': card['horizon']})
    return card


def enforce_publication(state: dict, *, publication_config: dict | None = None) -> dict:
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
        card = _decision_card({**state, **review}, publication_config)
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
        updates["shared_valuation_scenarios"] = annotate_disputed_cases(state, replay_cases(state))
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
        + "\n\nUnvalidated model reasoning is retained in diagnostics.json."
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
                    "Unvalidated debate narrative retained in diagnostics.json."
                    if isinstance(value, str) and value else value
                )
                for key, value in debate.items()
            }
    request = final_request(state)
    target = validate_final_case(state, request, updates.get("shared_valuation_scenarios"))
    updates["target_validation"] = {**target.model_dump(mode="json"), "request": request}
    comparison = ({"status": "unavailable", "rows": [], "reason": "Case-period completed-close comparison is shown on the decision card."}
                  if isinstance(request, dict) and request.get("method") == "case" else compare_valuation(state, target, request))
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
    continuity = _thesis_update({**state, **updates})
    if continuity:
        updates.update(continuity)
    updates["unvalidated_outputs"] = originals
    card = _decision_card({**state, **updates}, publication_config)
    updates["decision_context"] = card
    disputed = (card.get('adopted_case') or {}).get('disputed_by')
    if disputed:
        target_result_text = render_target_result(target)
        notice = ('**Disputed PM-adopted calculation**: accepted audit finding '
                  + ', '.join(disputed) + '; excluded from conditional range. '
                  'Calculation retained unchanged; this is not validated fair value.\n\n')
        target_text = target_text.replace(target_result_text, notice + target_result_text, 1)
    pm = originals.get('portfolio_manager') or {}
    structured = pm.get('structured') or {}
    def pm_text(key):
        value = structured.get(key)
        return _display(value[:20000]) + (' [truncated at 20,000 characters]' if len(value) > 20000 else '') if isinstance(value, str) and value.strip() else 'Unavailable in the retained structured PM output; see diagnostics.'
    from tradingagents.agents.audit_pass import prepare_audit_dispositions
    from tradingagents.agents.citation_check import check_pm_citations, render_pm_citation_check
    responses = prepare_audit_dispositions({**state, **updates})
    audit = state.get('advisory_audit') or {}
    audit_line = (f"{len(responses['findings'])} findings; PM responded to {responses['answered_count']}."
                  if audit.get('status') == 'completed with findings' else str(audit.get('status') or 'not run; no clearance implied'))
    updates['final_trade_decision'] = (
        f"**Rating**: {run_rating(state)}\n\n**Horizon**: {_display(card['horizon']['text'])}\n\n"
        f"**Executive Summary — unvalidated PM reasoning**:\n\n{pm_text('executive_summary')}\n\n"
        f"**Investment Thesis — unvalidated PM reasoning**:\n\n{pm_text('investment_thesis')}\n\n"
        f"**Advisory audit**: {_display(audit_line)}\n\n"
        + _display(render_pm_citation_check(check_pm_citations(state))) + '\n\n'
        + render_decision_context(card, include_mechanical=False, include_cases=False) + '\n\n' + target_text
        + '\n\n' + render_case_summary(card, include_mechanical=False)
        + f"\n\n**Canonical evidence**:\n\n{context}\n\n"
        'Position sizing: qualitative only; no validated numerical allocation.\n\n'
        'Original model narrative is retained separately in diagnostics.json.'
    )
    return updates
