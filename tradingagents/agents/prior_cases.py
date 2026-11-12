"""The analyst's cases from the last decision, offered back as the starting point for this run.

Without them each run re-derives every multiple, forecast and share count from scratch, and the same
evidence can price a third higher or lower from one run to the next. With them a changed assumption has
to be a decision: the analyst keeps the earlier value or says what is new. Nothing here overrides the
analyst; code only states what was carried and, later, what changed.
"""

from __future__ import annotations

import json

MAX_CHARS = 14000
_ERRORS = (OSError, ValueError, KeyError, TypeError)


def _text(value, limit=200):
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def prior_cases(config, ticker, state) -> dict | None:
    """The earlier decision's analyst cases and the filings retained since, or None when there is nothing to carry."""
    from tradingagents.agents.assumption_history import prior_publication
    from tradingagents.agents.decision_brief import _new_filings
    from tradingagents.memory.publication import load_evidence

    try:
        found = prior_publication(config, ticker, state)
        if found is None:
            return None
        record, label = found
        snapshot = load_evidence(config, record)
        saved = snapshot.get("shared_valuation_scenarios") or {}
        requests = saved.get("analyst_requests", saved.get("requests"))
        cases = [{"name": item["name"], **({"scenario_role": item["scenario_role"]} if item.get("scenario_role") else {}),
                  "request": item["request"]}
                 for item in requests or ()
                 if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("request"), dict)
                 and item["request"].get("method") in ("revenue_case", "earnings_case")]
        if not cases:
            return None
        try:
            filings = _new_filings(snapshot, state)
        except _ERRORS:
            filings = {"status": "unknown", "rows": []}
        return {"decision_id": record["decision_id"], "label": label, "rating": record.get("canonical_rating"),
                "cases": cases, "filings": filings}
    except _ERRORS:
        return None


def render_prior_cases(context) -> str:
    """Prompt text for the fundamentals analyst, or '' when there is nothing usable to carry."""
    if not isinstance(context, dict) or not context.get("cases"):
        return ""
    block = json.dumps(context["cases"], ensure_ascii=False, separators=(",", ":"))
    if len(block) > MAX_CHARS:
        return ""
    filings = context.get("filings") or {}
    rows = filings.get("rows") or []
    if filings.get("status") != "known":
        new = "Whether a filing is new since then could not be established from the retained lists."
    elif rows:
        new = ("Filings retained since then: " + "; ".join(
            f"{_text(row.get('form'), 20)} filed {_text(str(row.get('filed_date')), 10)}" for row in rows[:6]) + ".")
    else:
        new = "No new filing has been retained since then."
    return (
        f"\n\nYour valuation cases in the last decision ({_text(str(context.get('label')), 80)}) are below. {new} "
        "Start from these cases. Keep each multiple, revenue forecast, earnings per share forecast, share count, cash change and obligation value "
        "exactly as it was unless a fact that is new since that decision changes it: a new filing, a reported result, "
        "new guidance, a completed financing, or a price move that changes an input you derive from price. Choosing a "
        "different reference point, or reading the same evidence differently, is not a new fact. For every value you "
        "change, begin that value's reason or rationale with 'Changed since the last decision:' and name the new fact. "
        "If nothing is new, resubmit the same values; update only dates and fact IDs that this run requires. A multiple "
        "that was set against one reference stays at its value when you cite a different reference. Answering the two "
        "operating-cash questions on a case that did not have them is not a change to its values. These earlier cases "
        "are your own earlier assumptions, not evidence.\n"
        "```previous_valuation_scenarios\n" + block + "\n```")
