"""The decision horizon stated through dated events the manager already tracks.

The manager names up to three open advisory conditions it expects to resolve inside the horizon and, for
each, the case weights it would hold after a favourable and after an adverse outcome. Code brings every
accepted case back to the horizon date at the required return, prices each set of weights, and states
the odds the manager's current weights imply. Nothing here forecasts a price or changes the rating.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from tradingagents.agents.required_return import rate_from_state, value_today

MAX_EVENTS = 3
OPEN_STATUSES = ("unknown", "unobserved")
_SUM_TOLERANCE = Decimal("0.001")
# Today's weights must be one mix of the two outcome sets. A case's weight may sit this far from that mix
# before the three sets are said to disagree: weights are usually given to the nearest five points.
WEIGHT_TOLERANCE = Decimal("0.05")


def _decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _text(value, limit=600):
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _day(value):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def horizon_date(analysis_date, months) -> date | None:
    """The calendar date ``months`` after ``analysis_date``, held to the month's last day."""
    start = _day(analysis_date)
    if start is None or type(months) is not int or months <= 0:
        return None
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def open_conditions(observations) -> list[dict]:
    """Prior advisory conditions still unresolved in this run: the only ones an event may name."""
    rows = []
    for row in observations or ():
        if isinstance(row, dict) and isinstance(row.get("condition_id"), str) and row.get("status") in OPEN_STATUSES:
            label = (f"Completed close {row.get('comparator')} {row.get('threshold')}" if row.get("kind") == "price_level"
                     else " ".join(str(part) for part in (row.get("metric"), row.get("comparator"), row.get("threshold"),
                                                          row.get("unit")) if part) if row.get("metric")
                     else row.get("description"))
            rows.append({"condition_id": row["condition_id"], "label": _text(label or row["condition_id"], 200)})
    return rows


def required(accepted, conditions, close, rate, horizon) -> bool:
    """Whether the manager is asked for an event view: weights can move, an event exists, values are computable."""
    return (len(accepted) >= 2 and bool(conditions) and horizon is not None
            and _decimal(close) is not None and _decimal(close) > 0 and rate is not None
            and all(_value(case, horizon, rate) is not None for case in accepted))


def _value(case, horizon, rate):
    return value_today(case.get("price"), horizon, case.get("period_end"), rate)


def _weights(entries, accepted, label, problems):
    """Weights keyed by case, or None with the reason added to ``problems``."""
    known = {(case["case_id"], case["version"]) for case in accepted}
    if not isinstance(entries, list) or not entries:
        problems.append(f"{label} is missing: give a weight for every accepted case.")
        return None
    found, total = {}, Decimal(0)
    for entry in entries:
        key = (entry.get("case_id"), entry.get("version")) if isinstance(entry, dict) else None
        weight = _decimal(entry.get("weight")) if isinstance(entry, dict) else None
        # An identifier of the wrong type is an unusable answer, never a crash.
        if key is None or not isinstance(key[0], str) or not isinstance(key[1], int) or key not in known:
            problems.append(f"{label} names a case that is not an accepted case in scenario_view.")
            return None
        if key in found or weight is None or not 0 <= weight <= 1:
            problems.append(f"{label} needs each accepted case once with a weight from 0 to 1.")
            return None
        found[key], total = weight, total + weight
    if set(found) != known:
        problems.append(f"{label} must give a weight for every accepted case (0 is allowed).")
        return None
    if abs(total - 1) > _SUM_TOLERANCE:
        problems.append(f"{label} sums to {total.normalize()}; it must sum to 1.")
        return None
    return found


def _priced(weights, values):
    return sum(weights[key] * values[key] for key in weights)


def assess(accepted, conditions, view, analysis_date, horizon, close, rate, none_reason=None) -> dict:
    """Check an event view and compute its arithmetic.

    ``accepted`` are the accepted scenario rows (case_id, version, price, period_end, weight).
    Returns status not_applicable (nothing to ask), unaddressed (asked, unusable) or addressed.
    """
    if not required(accepted, conditions, close, rate, horizon):
        return {"status": "not_applicable", "events": [], "problems": []}
    base = {"horizon_date": str(horizon), "close": str(_decimal(close))}
    if not isinstance(view, list) or not view:
        if _text(none_reason):
            # A stated view that nothing listed resolves inside the horizon is an answer, printed as such.
            return {**base, "status": "none_expected", "events": [], "problems": [], "reason": _text(none_reason)}
        return {**base, "status": "unaddressed", "events": [],
                "problems": ["event_view is missing: name at least one open advisory condition expected inside the "
                             "horizon, or give no_event_reason if none of them is."]}
    problems, events, seen = [], [], set()
    if len(view) > MAX_EVENTS:
        problems.append(f"event_view has {len(view)} entries; at most {MAX_EVENTS} are used.")
    labels = {row["condition_id"]: row["label"] for row in conditions}
    start, close = _day(analysis_date), _decimal(close)
    with localcontext() as ctx:
        ctx.prec = 40
        values = {(case["case_id"], case["version"]): _value(case, horizon, rate) for case in accepted}
        current = {(case["case_id"], case["version"]): _decimal(case["weight"]) for case in accepted}
        current_value = _priced(current, values) / sum(current.values())
        names = {(case["case_id"], case["version"]): _text(case.get("role"), 40) or case["case_id"] for case in accepted}
        for entry in view[:MAX_EVENTS]:
            if not isinstance(entry, dict):
                problems.append("event_view entries must be objects.")
                continue
            identity = entry.get("condition_id")
            name = f"Event {_text(identity, 60) if isinstance(identity, str) else 'with an unusable condition_id'}"
            if not isinstance(identity, str) or identity not in labels:
                problems.append(f"{name} is not an open advisory condition listed for this run.")
                continue
            if identity in seen:
                problems.append(f"{name} is listed more than once.")
                continue
            seen.add(identity)
            before = len(problems)
            expected = _day(entry.get("expected_date"))
            if expected is None or start is None or not start < expected <= horizon:
                problems.append(f"{name} needs an expected_date after {analysis_date} and no later than {horizon}.")
            if entry.get("favourable_when") not in ("met", "not_met"):
                problems.append(f"{name} needs favourable_when: met or not_met.")
            if not _text(entry.get("reason")):
                problems.append(f"{name} has no reason.")
            favourable = _weights(entry.get("favourable_weights"), accepted, f"{name} favourable_weights", problems)
            adverse = _weights(entry.get("adverse_weights"), accepted, f"{name} adverse_weights", problems)
            if len(problems) > before:
                continue
            high, low = _priced(favourable, values), _priced(adverse, values)
            if high <= low:
                problems.append(f"{name}: the favourable weights give a value at the horizon ({high:.2f}) that is not above "
                                f"the adverse weights' ({low:.2f}); the two outcomes must differ in that direction.")
                continue
            # Today's weight on each case must be one mix of the two outcome weights: odds x favourable plus
            # (1 - odds) x adverse. The odds are the best single fit across the cases, held to 0 to 1.
            spread = {key: favourable[key] - adverse[key] for key in current}
            odds = (sum((current[key] - adverse[key]) * spread[key] for key in current)
                    / sum(value * value for value in spread.values()))
            odds = min(max(odds, Decimal(0)), Decimal(1))
            mixed = {key: adverse[key] + odds * spread[key] for key in current}
            if max(abs(mixed[key] - current[key]) for key in current) > WEIGHT_TOLERANCE:
                problems.append(
                    f"{name}: the three sets of weights disagree. The closest single mix of your outcome weights "
                    f"(about {odds * 100:.0f}% favourable) gives case weights "
                    + ", ".join(f"{names[key]} {mixed[key]:.2f}" for key in current) + "; your scenario_view holds "
                    + ", ".join(f"{names[key]} {current[key]:.2f}" for key in current)
                    + ". Today's weight on each case must equal one probability times its "
                    "favourable weight plus the rest times its adverse weight, within 0.05. Revise the outcome "
                    "weights or the scenario_view weights.")
                continue
            events.append({
                "condition_id": identity, "label": labels[identity], "expected_date": str(expected),
                "favourable_when": entry["favourable_when"], "reason": _text(entry.get("reason")),
                "implied_odds_percent": str(odds * 100),
                **{side: {"value": str(value), "move_percent": str((value / close - 1) * 100),
                          "weights": [{"case_id": key[0], "version": key[1], "weight": str(weights[key])}
                                      for key in sorted(weights)]}
                   for side, value, weights in (("favourable", high, favourable), ("adverse", low, adverse))}})
        summary = {**base, "current_value": str(current_value),
                   "current_move_percent": str((current_value / close - 1) * 100)}
    if problems:
        return {**summary, "status": "unaddressed", "events": [], "problems": problems}
    return {**summary, "status": "addressed", "events": events, "problems": []}


def conditions_from_state(state) -> list[dict]:
    """The open prior conditions of this run, read the same way for the prompt and for the check."""
    prior = state.get("prior_thesis")
    if not isinstance(prior, dict):
        return []
    observations = prior.get("observations")
    if not isinstance(observations, list):
        from tradingagents.memory.thesis import observe_conditions
        try:
            observations = observe_conditions(prior, state)
        except (ValueError, TypeError, KeyError):
            return []
    return open_conditions(observations)


def horizon_from_state(state) -> date | None:
    manager = ((state.get("unvalidated_outputs") or {}).get("portfolio_manager") or {})
    months = manager.get("configured_horizon_months")
    if months is None:
        months = (state.get("run_settings") or {}).get("decision_horizon_months", 6)
    return horizon_date(state.get("trade_date"), months)


def summarize(state, accepted, close) -> dict:
    """The event view of a decision, from the manager's retained answer; not judged for runs that were not asked."""
    manager = ((state.get("unvalidated_outputs") or {}).get("portfolio_manager") or {})
    if not manager.get("event_contract"):
        return {"status": "not_applicable", "events": [], "problems": []}
    structured = manager.get("structured") if isinstance(manager.get("structured"), dict) else {}
    return assess(accepted, conditions_from_state(state), structured.get("event_view"), state.get("trade_date"),
                  horizon_from_state(state), close, rate_from_state(state), structured.get("no_event_reason"))


def render_for_manager(conditions, accepted_possible, horizon) -> str:
    """The instruction and the list of open conditions, or '' when no event view is asked for."""
    if not conditions or not accepted_possible or horizon is None:
        return ""
    lines = [f"Six-month view from dated events (horizon date {horizon}). Open advisory conditions from the earlier "
             "decision:"]
    lines += [f"- {row['condition_id']}: {row['label']}" for row in conditions]
    lines.append(
        f"When you accept two or more cases, supply event_view with one to {MAX_EVENTS} of these conditions that you "
        "expect to resolve by the horizon date: condition_id (exact), expected_date (YYYY-MM-DD, after the analysis "
        "date and no later than the horizon date), favourable_when (met or not_met: which result of the condition "
        "is the favourable one for the stock), favourable_weights and adverse_weights (the case weights you would "
        "hold after each outcome: every accepted case once, 0 allowed, each set summing to 1), and a short reason. "
        "Code prices each set at the horizon date and derives the odds your current weights imply: your "
        "scenario_view weight on each case must equal one probability times its favourable weight plus the rest "
        "times its adverse weight, within 0.05. Do not state a probability. If you expect none of the listed "
        "conditions to resolve by the horizon date, leave event_view null and say why in no_event_reason.")
    return "\n".join(lines)


def retry_feedback(summary) -> str:
    if not isinstance(summary, dict) or summary.get("status") != "unaddressed":
        return ""
    return ("Your event_view could not be used: " + " ".join(summary["problems"][:6])
            + " Resubmit the complete decision with a valid event_view.")


def render(summary) -> list[str]:
    """The reader's table: each event, its date, the implied move under each outcome and the implied odds."""
    if isinstance(summary, dict) and summary.get("status") == "unaddressed":
        return ["**Six-month view from dated events**: not stated; the Portfolio Manager's event_view could not be "
                "used. " + " ".join(summary.get("problems", [])[:3])]
    if isinstance(summary, dict) and summary.get("status") == "none_expected":
        return [f"**Six-month view from dated events**: the Portfolio Manager expects none of the open conditions to "
                f"resolve by {summary['horizon_date']}. Reason (unvalidated): {summary['reason']}"]
    if not isinstance(summary, dict) or summary.get("status") != "addressed" or not summary.get("events"):
        return []
    lines = [f"**Six-month view from dated events** (to {summary['horizon_date']}; arithmetic on the manager's own "
             f"weights, not a forecast): each accepted case is brought back to {summary['horizon_date']} at the "
             f"required return. On today's weights that is {Decimal(summary['current_value']):.2f}, "
             f"{Decimal(summary['current_move_percent']):+.1f}% against the close of {Decimal(summary['close']):.2f}. "
             "A move shown is what the price would do if it went to that value."]
    for event in summary["events"]:
        favourable, adverse = (f"{Decimal(event[side]['value']):.2f} ({Decimal(event[side]['move_percent']):+.1f}%)"
                               for side in ("favourable", "adverse"))
        lines.append(f"- {event['label']} (expected by {event['expected_date']}; favourable if "
                     f"{'met' if event['favourable_when'] == 'met' else 'not met'}): {favourable} if favourable, "
                     f"{adverse} if adverse; today's weights imply about "
                     f"{Decimal(event['implied_odds_percent']):.0f}% for the favourable outcome. "
                     f"Reason (unvalidated): {event['reason']}")
    lines.append("The implied odds are not a probability the manager stated: they are the single mix of its two "
                 "outcome weight sets that best reproduces today's weights (each case within 5 points).")
    return lines
