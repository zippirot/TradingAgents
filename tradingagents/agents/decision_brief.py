"""What changed since the last decision, built from saved records without a model call.

The brief is arithmetic and bookkeeping on retained records. It never chooses a
rating: the Portfolio Manager states what the changes mean, and code only checks
that the stated meaning agrees with the two ratings.
"""
from __future__ import annotations

from datetime import UTC
from decimal import Decimal, InvalidOperation

from tradingagents.agents.assumption_history import (
    _filings,
    _stamp,
    compare_cases,
    prior_publication,
)
from tradingagents.agents.scenario_decision import priced_cases
from tradingagents.agents.shared_valuation import replay_cases
from tradingagents.memory.thesis import condition_status_label

LABEL = "Since the last decision"
ASSESSMENTS = {
    "no_material_change": "no material change",
    "strengthens": "strengthens the earlier call",
    "weakens": "weakens the earlier call",
    "reverses": "reverses the earlier call",
}
_PART_ERRORS = (ValueError, TypeError, KeyError, AttributeError, OSError, ArithmeticError)


def _text(value, limit=600):
    return " ".join(str(value).split())[:limit] if isinstance(value, str) else ""


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _quote(observation):
    if not isinstance(observation, dict) or _decimal(observation.get("close")) is None:
        return None
    fallback = observation.get("price_fallback")
    latest = fallback.get("latest_completed_session_date") if isinstance(fallback, dict) else None
    session = observation.get("session_date")
    return {"close": str(_decimal(observation["close"])), "currency": observation.get("currency"),
            "session_date": session,
            "stale": bool(isinstance(latest, str) and isinstance(session, str) and latest != session),
            "latest_completed_session_date": latest if isinstance(latest, str) else None}


def _price(snapshot, state):
    then, now = _quote(snapshot.get("price_observation")), _quote(state.get("price_observation"))
    part = {"then": then, "now": now, "change_percent": None}
    if then and now and then["currency"] == now["currency"] and Decimal(then["close"]) > 0:
        part["change_percent"] = str((Decimal(now["close"]) / Decimal(then["close"]) - 1) * 100)
    return part


def _new_filings(snapshot, state):
    old, new = _filings(snapshot), _filings(state)
    if old is None or new is None:
        return {"status": "unknown", "rows": []}
    forms = {d["filing"]["accession"]: d["filing"].get("form") for d in state["filing_evidence"]["documents"]}
    rows = [{"form": _text(forms.get(accession), 20) or "filing", "filed_date": filed, "accession": accession}
            for accession, filed in sorted(new - old, key=lambda row: (row[1], row[0]))]
    return {"status": "known", "rows": rows}


# Records saved before role wording was stored carry only the status word; "breached" there means not satisfied.
_PLAIN_STATUS = {"breached": "comparison not satisfied", "met": "comparison satisfied",
                 "unobserved": "no reading yet", "unknown": "no reading yet"}


def _conditions(record, snapshot, state):
    prior = state.get("prior_thesis")
    if not isinstance(prior, dict) or not isinstance(prior.get("observations"), list):
        return {"status": "none", "rows": [], "tracked": 0}
    if prior.get("publication_id") != record["decision_id"]:
        raise ValueError("advisory conditions in this run come from a different earlier record")
    before = {row.get("condition_id"): row.get("status")
              for row in (snapshot.get("decision_context") or {}).get("conditions") or () if isinstance(row, dict)}
    rows = []
    for row in prior["observations"]:
        then, now = before.get(row.get("condition_id"), "unobserved"), row.get("status")
        # Unobserved (new when first proposed) and unknown (not yet reported) are the same to a reader: no reading yet.
        if then == now or not {then, now} - {"unobserved", "unknown"}:
            continue
        # A trigger read for the first time and found not met is a first reading, not a change.
        if then in ("unobserved", "unknown") and now == "breached" and row.get("thesis_role") == "reconsideration_trigger":
            continue
        metric = row.get("metric") or ("Completed close" if row.get("kind") == "price_level" else "")
        label = " ".join(str(part or "") for part in (metric, row.get("comparator"), row.get("threshold"),
                                                       row.get("unit") or row.get("currency"))).strip()
        # The stored status word "breached" only means the comparison is not satisfied; readers get the role wording.
        rows.append({"condition": _text(label or row.get("description") or row.get("condition_id"), 160),
                     "then": then, "now": now,
                     "then_label": condition_status_label({**row, "status": then}),
                     "now_label": condition_status_label({**row, "status": now})})
    return {"status": "known", "rows": rows, "tracked": len(prior["observations"])}


def _prices(replayed):
    return {case["name"]: case for case in priced_cases(replayed)}


def _cases(snapshot, state):
    compared = compare_cases(snapshot, state)
    then = _prices(snapshot.get("shared_valuation_scenarios"))
    now = _prices(replay_cases(state) if state.get("shared_valuation_scenarios") else {})
    repriced = [{"scenario": name, "then": then[name]["price"], "now": now[name]["price"], "unit": now[name]["unit"]}
                for name in sorted(then.keys() & now.keys())
                if then[name]["unit"] == now[name]["unit"] and Decimal(then[name]["price"]) != Decimal(now[name]["price"])]
    def values(cases):
        return [{"role": case["role"], "price": case["price"], "unit": case["unit"]} for case in cases.values()]
    return {**compared, "repriced": repriced, "priced_then": len(then), "priced_now": len(now),
            "values_then": values(then), "values_now": values(now)}


def _sources(snapshot, state):
    notes = []
    then, now = snapshot.get("quality_status"), (state.get("evidence_quality") or {}).get("status")
    if then and now and then != now:
        notes.append(f"Evidence quality was {then} then and is {now} now.")
    return notes


def since_last_decision(config: dict, ticker: str, state: dict) -> dict:
    """Compare this run with the last directional decision of any earlier run.

    Each part is computed on its own: one unusable part is named with its reason
    and the rest of the brief stands.
    """
    from tradingagents.memory.publication import load_evidence

    brief = {"version": 1, "status": "unavailable", "prior": None, "parts_unavailable": []}
    try:
        found = prior_publication(config, ticker, state)
        if found is None:
            return {**brief, "status": "no_prior"}
        record, label = found
        snapshot = load_evidence(config, record)
        brief["prior"] = {"decision_id": record["decision_id"], "as_of": record["requested_as_of"], "label": label,
                          "published_at": f"{_stamp(record['published_at']).astimezone(UTC):%Y-%m-%d %H:%M} UTC",
                          "rating": record["canonical_rating"]}
    except _PART_ERRORS as exc:
        return {**brief, "reason": f"The earlier decision record could not be read ({type(exc).__name__})."}
    brief["status"] = "available"
    for name, build in (("price", lambda: _price(snapshot, state)),
                        ("filings", lambda: _new_filings(snapshot, state)),
                        ("conditions", lambda: _conditions(record, snapshot, state)),
                        ("cases", lambda: _cases(snapshot, state)),
                        ("sources", lambda: _sources(snapshot, state))):
        try:
            brief[name] = build()
        except _PART_ERRORS as exc:
            brief[name] = None
            brief["parts_unavailable"].append(
                {"part": name, "reason": _text(str(exc), 200) or type(exc).__name__})
    return brief


def _usable(assessment) -> bool:
    return (isinstance(assessment, dict) and isinstance(assessment.get("status"), str)
            and assessment["status"] in ASSESSMENTS)


def assessment_problems(brief, rating, assessment) -> list[str]:
    """Why the manager's change assessment cannot stand; empty when it agrees with the two ratings."""
    if not isinstance(brief, dict) or brief.get("status") != "available":
        return []
    if not _usable(assessment):
        return ["change_assessment is missing: state one of " + ", ".join(ASSESSMENTS) + " with a reason."]
    problems = []
    if not _text(assessment.get("reason")):
        problems.append("change_assessment has no reason naming the change that matters.")
    earlier, status = brief["prior"]["rating"], assessment["status"]
    if rating != earlier and status not in {"weakens", "reverses"}:
        problems.append(f"The rating moved from {earlier} to {rating}, so change_assessment must be weakens or "
                        f"reverses and name the cause; it says {status}.")
    if rating == earlier and status == "reverses":
        problems.append(f"The rating is unchanged at {rating}, so change_assessment cannot be reverses.")
    return problems


def finalize(brief, state) -> dict:
    """Attach the manager's retained answer and the consistency check for the decision card."""
    manager = ((state.get("unvalidated_outputs") or {}).get("portfolio_manager") or {})
    if not isinstance(brief, dict) or brief.get("status") != "available" or not manager.get("change_contract"):
        return brief
    structured = manager.get("structured") if isinstance(manager.get("structured"), dict) else {}
    answer = structured.get("change_assessment")
    problems = assessment_problems(brief, state.get("final_rating"), answer)
    valid = _usable(answer)
    return {**brief, "assessment": {"status": answer["status"] if valid else None,
                                    "reason": _text(answer.get("reason"), 600) if valid else "",
                                    "rating": state.get("final_rating"), "problems": problems}}


def retry_feedback(brief, rating, assessment) -> str:
    problems = assessment_problems(brief, rating, assessment)
    return ("Your change_assessment could not be used: " + " ".join(problems)
            + " Resubmit the complete decision with a valid change_assessment.") if problems else ""


def _money(quote):
    return f"{Decimal(quote['close']):.2f} {quote['currency'] or ''}".strip()


def render(brief, *, for_manager: bool = False, display=str) -> list[str]:
    """Lines for the manager's prompt and the decision page. Empty when there is no earlier decision.

    ``display`` escapes retained text (names, reasons) where the caller renders markdown.
    """
    if not isinstance(brief, dict) or brief.get("status") not in {"available", "unavailable"} or (
            brief["status"] == "unavailable" and not brief.get("reason")):
        return []
    if brief["status"] == "unavailable":
        return [f"**{LABEL}**: comparison unavailable. {display(brief['reason'])}"]
    prior = brief["prior"]
    lines = [f"**{LABEL}** ({prior['published_at']}, rating {display(prior['rating'])}, run {prior['decision_id'][:8]}). "
             "Bookkeeping on saved records, not a recommendation:"]
    price = brief.get("price")
    if price and price["then"] and price["now"]:
        def side(quote):
            return f"{_money(quote)} on {quote['session_date']}" + (
                " (stale: the latest completed session had no close)" if quote["stale"] else "")
        text = f"- Price: {side(price['then'])} then; {side(price['now'])} now"
        if price["change_percent"] is not None:
            text += f"; {Decimal(price['change_percent']):+.1f}%"
        lines.append(text + ".")
    elif price:
        lines.append("- Price: no comparable close is retained for both runs.")
    filings = brief.get("filings")
    if filings and filings["status"] == "known":
        rows = filings["rows"]
        lines.append("- Filings: no new filing was retained between the two runs." if not rows else
                     f"- Filings: {len(rows)} new since then: "
                     + "; ".join(f"{display(row['form'])} filed {row['filed_date']}" for row in rows[:6])
                     + ("; more not listed" if len(rows) > 6 else "") + ".")
    elif filings:
        lines.append("- Filings: not comparable; one of the two runs retained no filing list.")
    conditions = brief.get("conditions")
    if conditions and conditions["status"] == "known":
        rows = conditions["rows"]
        lines.append(f"- Advisory conditions: {conditions['tracked']} tracked, none changed status." if not rows else
                     "- Advisory conditions changed: "
                     + "; ".join(f"{display(row['condition'])}: {display(row.get('then_label') or _PLAIN_STATUS.get(row['then'], row['then']))} to "
                                 f"{display(row.get('now_label') or _PLAIN_STATUS.get(row['now'], row['now']))}"
                                 for row in rows[:8]) + ".")
    elif conditions:
        lines.append("- Advisory conditions: none carried from the earlier decision.")
    cases = brief.get("cases")
    if cases:
        changes = [f"\"{display(row['scenario'])}\" repriced {Decimal(row['then']):.2f} to "
                   f"{Decimal(row['now']):.2f} {display(row['unit'])}" for row in cases["repriced"]]
        changes += [f"\"{display(row['scenario'])}\" {row['current']}" if row["field"] == "case" else
                    f"\"{display(row['scenario'])}\" {row['field'].replace('_', ' ')} {display(row['previous'])} "
                    f"to {display(row['current'])}" for row in cases["rows"][:12]]
        if cases.get("summary_message"):
            changes.append(display(cases["summary_message"]))
        def priced(rows):
            return (f"{len(rows)} priced (" + ", ".join(
                f"{'' if row['role'] == 'unlabelled' else display(row['role']) + ' '}{Decimal(row['price']):.2f} "
                f"{display(row['unit'])}" for row in rows) + ")"
                    ) if rows else "none priced"
        lines.append(f"- Valuation cases: {priced(cases['values_then'])} then; {priced(cases['values_now'])} now; "
                     + ("; ".join(changes) if changes else "no input or value change") + ".")
        for row in cases["unusable"]:
            where = "the earlier record" if row["side"] == "previous" else "this run"
            lines.append(f"- Not compared: case \"{display(row['scenario'])}\" in {where} is unusable "
                         f"({display(row['reason'])}).")
    for note in brief.get("sources") or ():
        lines.append("- Data: " + display(note))
    for row in brief["parts_unavailable"]:
        lines.append(f"- Not compared: {row['part']} ({display(row['reason'])}).")
    if for_manager:
        lines.append(
            "Supply change_assessment: status one of " + ", ".join(ASSESSMENTS) + ", and a one-sentence reason naming "
            "the change that matters. A rating different from the earlier " + prior["rating"] + " must be weakens or "
            "reverses and name its cause. The same rating with no_material_change is allowed. This is your judgment "
            "of the changes listed; the list itself does not choose the rating.")
        return lines
    assessment = brief.get("assessment")
    if assessment:
        if assessment["status"]:
            lines.append(f"Portfolio Manager's reading (unvalidated): {ASSESSMENTS[assessment['status']]}. "
                         + display(assessment["reason"]))
        lines.append("Change check: " + ("consistent with the two ratings." if not assessment["problems"] else
                                         display(" ".join(assessment["problems"]))))
    return lines
