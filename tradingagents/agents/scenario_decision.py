"""The Portfolio Manager's stance on each priced case, and what follows from it.

The manager accepts or rejects every priced case and weights the ones it accepts.
Code then states the conditional range and weighted value against the completed
close and whether the rating points the same way. Nothing here is a price target,
an expected return or a rating rule: a contrary rating needs an explanation, not
permission.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

from tradingagents.agents.case_reference import BANDS
from tradingagents.agents.required_return import (
    rate_from_state,
    render_required_return,
    value_today,
)

REJECTABLE_INPUTS = ("revenue_forecast", "multiple", "shares", "cash", "obligations", "funding")
DIRECTION_THRESHOLD = Decimal("0.10")
_BEARISH, _BULLISH = {"Sell", "Underweight"}, {"Buy", "Overweight"}
LABEL = "Conditional scenario range (not a price target)"


def _decimal(value):
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _text(value, limit=600):
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _quote(comparison, unit):
    """The completed close this case was validated against on replay, or None when it is not comparable."""
    price = comparison.get("price") if isinstance(comparison, dict) and comparison.get("status") == "available" else None
    close = _decimal(price.get("close")) if isinstance(price, dict) else None
    if close is None or close <= 0 or not isinstance(price.get("currency"), str) or price["currency"] + "/shares" != unit:
        return None
    return {"close": str(close), "currency": price["currency"], "session_date": price.get("session_date")}


def priced_cases(replayed) -> list[dict]:
    """Cases with a price the manager can weigh: supported revenue cases.

    A case an accepted audit finding names stays priced and carries the finding ids as ``flagged_by``:
    the manager answers the findings and weighs the cases in one reply, so removing a case because of
    that reply would void the weights given in it.
    """
    cases = []
    for row in (replayed or {}).get("rows") or ():
        result = row.get("result") if isinstance(row, dict) else None
        if (not isinstance(result, dict) or result.get("method") != "revenue_case" or result.get("status") != "supported"
                or _decimal(result.get("target")) is None):
            continue
        funding, position = row.get("funding") or {}, row.get("reference_position") or {}
        cases.append({"case_id": row["case_id"], "version": row["version"], "name": row["name"],
                      "role": _text(row.get("scenario_role"), 40) or "unlabelled", "price": str(_decimal(result["target"])),
                      "unit": result.get("unit"), "period_end": result.get("valuation_period_end"),
                      "funding": funding.get("status", "unassessed"), "funding_summary": funding.get("summary", ""),
                      "quote": _quote(row.get("comparison"), result.get("unit")),
                      "reference_band": position.get("band"), "reference_summary": position.get("summary", ""),
                      "flagged_by": [str(item) for item in row.get("disputed_by") or ()]})
    return cases


def with_value_today(cases, state) -> list[dict]:
    """Add each case's value brought back to the analysis date, when the run recorded a required return."""
    rate = rate_from_state(state)
    if rate is None:
        return cases
    priced = []
    for case in cases:
        today = value_today(case["price"], state.get("trade_date"), case.get("period_end"), rate)
        priced.append({**case, "value_today": None if today is None else str(today)})
    return priced


def sizing_rule(accepted, close) -> dict | None:
    """Position size per unit of accepted loss, from the lowest accepted case's value today.

    Arithmetic on the cases the manager accepted and the stated required return. It needs no holdings
    and is a ratio for the reader's own loss limit, never an allocation.
    """
    valued = [row for row in accepted if row.get("value_today") is not None]
    if close is None or close <= 0 or not valued or len(valued) != len(accepted):
        return None
    lowest = min(valued, key=lambda row: Decimal(row["value_today"]))
    with localcontext() as ctx:
        ctx.prec = 40
        fall = (close - Decimal(lowest["value_today"])) / close
        rule = {"case_id": lowest["case_id"], "version": lowest["version"], "name": lowest["name"],
                "role": lowest["role"], "value_today": lowest["value_today"], "fall": str(fall)}
        if fall <= 0:
            return {**rule, "status": "not_limiting"}
        return {**rule, "status": "available", "weight_per_point_of_loss": str(1 / fall)}


def view_problems(cases, view) -> list[str]:
    """Why a scenario_view cannot be used; empty when every priced case is properly addressed."""
    if not cases:
        return []
    if not isinstance(view, list) or not view:
        return ["scenario_view is missing: every priced case needs an accepted or rejected entry."]
    problems, seen, total = [], {}, Decimal(0)
    for entry in view:
        if not isinstance(entry, dict):
            problems.append("scenario_view entries must be objects.")
            continue
        key = (entry.get("case_id"), entry.get("version"))
        if not isinstance(key[0], str) or type(key[1]) is not int:
            problems.append("Each scenario_view entry needs a text case_id and an integer version.")
            continue
        if key in seen:
            problems.append(f"Case {key[0]} is listed more than once.")
        seen[key] = entry
    known = {(case["case_id"], case["version"]) for case in cases}
    for key in seen:
        if key not in known:
            problems.append(f"Case {key[0]} version {key[1]} is not a priced case in this run.")
    accepted = 0
    for case in cases:
        entry = seen.get((case["case_id"], case["version"]))
        label = f"Case {case['case_id']} ({case['name']})"
        if entry is None:
            problems.append(f"{label} is not addressed.")
            continue
        if not _text(entry.get("reason")):
            problems.append(f"{label} has no reason.")
        if entry.get("disposition") == "accepted":
            weight = _decimal(entry.get("weight"))
            if weight is None or not 0 < weight <= 1:
                problems.append(f"{label} is accepted without a weight above 0 and at most 1.")
            else:
                accepted, total = accepted + 1, total + weight
        elif entry.get("disposition") == "rejected":
            if entry.get("rejected_input") not in REJECTABLE_INPUTS:
                problems.append(f"{label} is rejected without naming the input rejected: one of "
                                + ", ".join(REJECTABLE_INPUTS) + ".")
        else:
            problems.append(f"{label} needs disposition accepted or rejected.")
    if accepted and abs(total - 1) > Decimal("0.001"):
        problems.append(f"Accepted weights sum to {total.normalize()}; they must sum to 1.")
    return problems


def _direction(value, close):
    if value >= close * (1 + DIRECTION_THRESHOLD):
        return "above"
    if value <= close * (1 - DIRECTION_THRESHOLD):
        return "below"
    return "near"


def summarize(state, replayed) -> dict:
    """Recalculate the scenario basis of a decision from replayed cases and the manager's retained answer."""
    cases = with_value_today(priced_cases(replayed), state)
    if not cases:
        return {"status": "no_priced_cases", "cases": [], "problems": []}
    manager = ((state.get("unvalidated_outputs") or {}).get("portfolio_manager") or {})
    if not manager.get("scenario_contract"):
        # A decision made before the manager was asked about the cases is not judged for omitting them.
        return {"status": "not_applicable", "cases": cases, "problems": []}
    structured = manager.get("structured") if isinstance(manager.get("structured"), dict) else {}
    view = structured.get("scenario_view")
    problems = view_problems(cases, view)
    if problems:
        return {"status": "unaddressed", "cases": cases, "problems": problems}
    entries = {(e["case_id"], e["version"]): e for e in view if isinstance(e, dict)}
    rows, accepted = [], []
    for case in cases:
        entry = entries[(case["case_id"], case["version"])]
        row = {**case, "disposition": entry["disposition"], "reason": _text(entry.get("reason")),
               "weight": None, "rejected_input": None}
        if entry["disposition"] == "accepted":
            row["weight"] = str(_decimal(entry["weight"]))
            accepted.append(row)
        else:
            row["rejected_input"] = entry["rejected_input"]
        rows.append(row)
    summary = {"status": "addressed", "cases": rows, "problems": [], "range": None, "weighted_value": None,
               "close": None, "session_date": None, "direction": None, "consistency": "not_checked",
               "rating_basis_reason": _text(structured.get("rating_basis_reason"), 1200),
               "required_return": state.get("required_return") if isinstance(state.get("required_return"), dict) else None,
               "sizing_rule": None}
    if not accepted:
        return summary
    # Only the close each accepted case was validated against on replay is comparable; the raw
    # price observation is never read here, so a quote in another currency cannot be compared.
    quotes = [row["quote"] for row in accepted]
    price = quotes[0] if quotes[0] is not None and all(quote == quotes[0] for quote in quotes) else {}
    close = _decimal(price.get("close"))
    with localcontext() as ctx:
        ctx.prec = 40
        values = [Decimal(row["price"]) for row in accepted]
        weighted = sum(Decimal(row["weight"]) * Decimal(row["price"]) for row in accepted) / sum(
            Decimal(row["weight"]) for row in accepted)
        summary.update(range={"low": str(min(values)), "high": str(max(values))}, weighted_value=str(weighted),
                       unit=accepted[0]["unit"])
        if close is None or close <= 0:
            return summary
        summary.update(close=str(close), session_date=price.get("session_date"),
                       weighted_vs_close_percent=str((weighted / close - 1) * 100),
                       range_vs_close_percent={"low": str((min(values) / close - 1) * 100),
                                               "high": str((max(values) / close - 1) * 100)},
                       direction=_direction(weighted, close))
        summary["sizing_rule"] = sizing_rule(accepted, close)
    rating = state.get("final_rating")
    contrary = ((rating in _BEARISH and summary["direction"] == "above")
                or (rating in _BULLISH and summary["direction"] == "below"))
    summary["consistency"] = ("consistent" if not contrary else
                              "explained" if summary["rating_basis_reason"] else "unexplained")
    return summary


def retry_feedback(state, replayed) -> str:
    """What to send back to the manager once, or '' when its scenario answer can stand."""
    summary = summarize(state, replayed)
    if summary["status"] == "unaddressed":
        return ("Your scenario_view could not be used: " + " ".join(summary["problems"])
                + " Resubmit the complete decision with a valid scenario_view.")
    if summary.get("consistency") == "unexplained":
        return (f"Your rating points against your own accepted scenarios (weighted value {summary['direction']} the "
                "completed close by more than 10 percent). Resubmit the complete decision and either state why in "
                "rating_basis_reason or revise the rating or the scenario_view.")
    return ""


def render_cases_for_manager(cases) -> str:
    if not cases:
        return "No priced scenario case in this run; omit scenario_view."
    lines = ["Priced scenario cases. Each is conditional arithmetic on stated assumptions at its period end, "
             "not discounted to today:"]
    for case in cases:
        lines.append(f"- case_id {case['case_id']}, version {case['version']}, role {case['role']}, "
                     f"\"{case['name']}\": {Decimal(case['price']):.2f} {case['unit']} at {case['period_end']}. "
                     f"{case['funding_summary']} {case['reference_summary']}".rstrip())
    lines.append(
        "Supply scenario_view with one entry per case above: case_id, version, disposition (accepted or rejected), "
        "reason, and for accepted cases a weight above 0 and at most 1; accepted weights must sum to 1 and are your "
        "subjective weights, not measured probabilities. To reject a case name the single input you reject in "
        "rejected_input: one of " + ", ".join(REJECTABLE_INPUTS) + ". The funding status and reference position "
        "printed above are computed; do not call a case unassessed or uncalibrated unless they say so. A limit that "
        "applies equally to every case, or an uncertainty you cannot size, is expressed through lower weights and the "
        "downside case, not by rejecting. Reject a case only when you can state the value the rejected input should "
        "take and that value changes the case materially; say that value in the reason. Accepting an audit finding that "
        "names a case does not remove the case: it stays in this list, is shown flagged, and still needs your entry. Code then "
        "compares the weighted value of your accepted cases with the completed close. If your rating points the "
        "other way by more than 10 percent, state why in rating_basis_reason. This is a labelled conditional range, "
        "never a price target.")
    return "\n".join(lines)


def _money(value, unit):
    return f"{Decimal(value):.2f} {unit}"


def render(summary) -> list[str]:
    """Decision-card lines for the scenario basis; every figure stays labelled conditional."""
    if not isinstance(summary, dict) or summary.get("status") in (None, "not_applicable"):
        return []
    if summary["status"] == "no_priced_cases":
        return [f"**{LABEL}**: no priced scenario; the rating is a research opinion."]
    if summary["status"] == "unaddressed":
        return [f"**{LABEL}**: decision basis is opinion only; the Portfolio Manager did not address the priced cases. "
                + " ".join(summary["problems"][:4])]
    valued = any(case.get("value_today") for case in summary["cases"])
    lines = [f"**{LABEL}**: the Portfolio Manager's stance on each priced case. Weights are subjective and "
             "uncalibrated; values are at each case's period end"
             + ("; each value today is that value brought back at the required return stated below. The range, "
                "weighted value and rating check use the period-end values." if valued else " and are not discounted.")]
    for case in summary["cases"]:
        stance = (f"accepted, weight {Decimal(case['weight']):.2f}" if case["disposition"] == "accepted"
                  else f"rejected on {case['rejected_input'].replace('_', ' ')}")
        position = (f"implied multiple {BANDS[case['reference_band']]} of its own history"
                    if case.get("reference_band") in BANDS else "reference position unavailable")
        flag = ("; flagged by accepted audit finding " + ", ".join(case["flagged_by"])) if case.get("flagged_by") else ""
        today = f" at {case['period_end']}, {_money(case['value_today'], case['unit'])} today" if case.get("value_today") else ""
        lines.append(f"- {case['role']} — {case['name']}: {_money(case['price'], case['unit'])}{today}; funding "
                     f"{case['funding']}; {position}; {stance}{flag}. Reason (unvalidated): {case['reason']}")
    if summary["range"] is None:
        lines.append("All priced cases were rejected; no conditional range is stated and the rating is a research opinion.")
        return lines
    unit, span = summary["unit"], summary["range"]
    text = (f"Accepted range {_money(span['low'], unit)} to {_money(span['high'], unit)}; weighted value "
            f"{_money(summary['weighted_value'], unit)}")
    if summary["close"] is None:
        lines.append(text + ". No comparable completed close is available, so no comparison with the price is made.")
        return lines
    lines.append(text + f", {Decimal(summary['weighted_vs_close_percent']):+.1f}% against the "
                 f"{summary['session_date']} close of {_money(summary['close'], unit)} "
                 f"(range {Decimal(summary['range_vs_close_percent']['low']):+.1f}% to "
                 f"{Decimal(summary['range_vs_close_percent']['high']):+.1f}%). Direction: {summary['direction']} "
                 "the close, using a 10 percent threshold.")
    lines.append({"consistent": "Rating check: the rating does not point against the accepted scenarios.",
                  "explained": "Rating check: the rating points against the accepted scenarios. Portfolio Manager's "
                               "reason (unvalidated): " + summary["rating_basis_reason"],
                  "unexplained": "Rating check: the rating points against the accepted scenarios and no reason was given.",
                  }.get(summary["consistency"], "Rating check: not performed."))
    lines.extend(render_sizing_rule(summary))
    return lines


def render_sizing_rule(summary) -> list[str]:
    """The required return and the holdings-free sizing ratio, or why they are not stated."""
    stated = render_required_return(summary.get("required_return"))
    if not stated:
        return []
    rule, unit = summary.get("sizing_rule"), summary.get("unit")
    if not rule:
        return [stated]
    lowest = f"the lowest accepted case ({rule['role']} — {rule['name']})"
    if rule["status"] != "available":
        return [stated, f"Sizing from the downside: {lowest} is worth {_money(rule['value_today'], unit)} today, "
                        "not below the close, so the accepted cases set no loss-based limit on the position."]
    fall, per_point = Decimal(rule["fall"]) * 100, Decimal(rule["weight_per_point_of_loss"])
    return [stated, f"Sizing from the downside (arithmetic on the accepted cases, not an allocation): in {lowest} the "
                    f"position is worth {_money(rule['value_today'], unit)} today, {fall:.1f}% below the "
                    f"{summary['session_date']} close. For each 1% of a portfolio you accept losing in that case, the "
                    f"position can be at most {per_point:.1f}% of the portfolio. Your holdings, loss limit and other "
                    "exposures are not known to this report."]
