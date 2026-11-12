"""The Portfolio Manager's stance on each priced case, and what follows from it.

The manager accepts or rejects every priced case and weights the ones it accepts.
Code then states the conditional range and weighted value against the completed
close and whether the rating points the same way. Nothing here is a price target,
an expected return or a rating rule: a contrary rating needs an explanation, not
permission.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext

from tradingagents.agents.case_reference import BANDS
from tradingagents.agents.event_view import (
    render as render_events,
    retry_feedback as event_feedback,
    summarize as summarize_events,
)
from tradingagents.agents.required_return import (
    rate_from_state,
    render_required_return,
    value_today,
)
from tradingagents.agents.scenario_return import (
    annual_return,
    return_parts,
    short_period,
    sturdiness,
    today_basis,
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
        if (not isinstance(result, dict) or result.get("method") not in ("revenue_case", "earnings_case")
                or result.get("status") != "supported"
                or _decimal(result.get("target")) is None):
            continue
        funding, position = row.get("funding") or {}, row.get("reference_position") or {}
        request = row.get("request") if isinstance(row.get("request"), dict) else {}
        forecast = request.get("forecast") if isinstance(request.get("forecast"), dict) else {}
        cases.append({"case_id": row["case_id"], "version": row["version"], "name": row["name"],
                      "method": result["method"],
                      "forecast_revenue": forecast.get("value") if result["method"] == "revenue_case" else None,
                      "forecast_eps": forecast.get("value") if result["method"] == "earnings_case" else None,
                      "multiple": result.get("multiple"),
                      "multiple_basis": request.get("multiple_basis"), "net_obligations": result.get("net_obligations"),
                      "closing_shares": result.get("shares_outstanding"),
                      "role": _text(row.get("scenario_role"), 40) or "unlabelled", "price": str(_decimal(result["target"])),
                      "unit": result.get("unit"), "period_end": result.get("valuation_period_end"),
                      "funding": funding.get("status", "unassessed"), "funding_summary": funding.get("summary", ""),
                      "funding_bounds": funding.get("limit", "") if funding.get("bounds") else "",
                      "quote": _quote(row.get("comparison"), result.get("unit")),
                      "reference_band": position.get("band"), "reference_summary": position.get("summary", ""),
                      "reference_same_basis": position.get("basis") == "like_for_like",
                      "guidance_floor": (row.get("guidance_floor") or {}).get("summary", ""),
                      "flagged_by": [str(item) for item in row.get("disputed_by") or ()],
                      "flag_note": _text(row.get("dispute_note"), 300)})
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


UNEQUAL_SPREAD = Decimal("0.10")
# Points of yearly return either side of the required return inside which the accepted scenarios do not separate
# the stock from its price. The caller's portfolio file can set its own figure.
DEFAULT_HOLD_BAND = Decimal(3)


_VIEW_SIDE = {"Attractive": 1, "Fair": 0, "Unattractive": -1}
_ACTION_SIDE = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


def valuation_reading(gap, band) -> str | None:
    """Code's reading of the accepted scenarios: their yearly return against the required return, with the band as Fair."""
    if gap is None or band is None:
        return None
    return "Attractive" if gap > band else "Unattractive" if gap < -band else "Fair"


def hold_band(state) -> tuple[Decimal, str]:
    """The band in points and where it came from."""
    inputs = state.get("portfolio_inputs") if isinstance(state, dict) or hasattr(state, "get") else None
    own = _decimal(inputs.get("hold_band_points")) if isinstance(inputs, dict) and inputs.get("hold_band_points") is not None else None
    if own is not None and 0 <= own <= 10:
        return own, "portfolio file"
    return DEFAULT_HOLD_BAND, "app setting"


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
    # Arithmetic on each case's own assumptions against one validated close. Rejecting a case removes it from
    # the accepted aggregate, never from this. The close is the one the accepted cases share; with nothing
    # accepted, the one every quoted case shares. Cases validated against different closes get no figure.
    if accepted:
        reference = accepted[0]["quote"] if all(row["quote"] is not None and row["quote"] == accepted[0]["quote"]
                                                for row in accepted) else None
    else:
        quoted = [row["quote"] for row in rows if row["quote"] is not None]
        reference = quoted[0] if quoted and all(quote == quoted[0] for quote in quoted) else None
    for row in rows:
        row["annual_return"] = None
        if reference is None or row["quote"] != reference:
            continue
        yearly = annual_return(row["price"], reference["close"], reference.get("session_date"), row.get("period_end"))
        row["annual_return"] = None if yearly is None else str(yearly)
        parts = return_parts(row, state.get("price_implied_valuation"), reference["close"])
        if parts is not None:
            row["return_parts"] = parts
    summary = {"status": "addressed", "cases": rows, "problems": [], "range": None, "weighted_value": None,
               "close": None, "session_date": None, "direction": None, "consistency": "not_checked",
               "rating_basis_reason": _text(structured.get("rating_basis_reason"), 1200),
               "required_return": state.get("required_return") if isinstance(state.get("required_return"), dict) else None,
               "sizing_rule": None, "direction_basis": None, "weighted_value_today": None, "sturdiness": None,
               "weight_basis": _text(structured.get("weight_basis"), 1200) or None, "weights_decide": False,
               "weights_unequal": False, "hold_band": None, "conditional_hold": False,
               "stock_view": structured.get("stock_view") if structured.get("stock_view") in _VIEW_SIDE else None,
               "stock_view_reason": _text(structured.get("stock_view_reason"), 1200) or None,
               "valuation_reading": None, "view_check": None, "position_action": state.get("final_rating")}
    if not accepted:
        return summary
    # More than ten points between the largest and smallest accepted weight is a departure from equal weights.
    given_weights = [Decimal(row["weight"]) for row in accepted]
    summary["weights_unequal"] = len(given_weights) > 1 and max(given_weights) - min(given_weights) > UNEQUAL_SPREAD
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
                       direction=_direction(weighted, close), direction_basis="period_end")
        summary["sizing_rule"] = sizing_rule(accepted, close)
        summary["event_view"] = summarize_events(state, accepted, close)
        # With a required return every accepted case has a value today, and the check moves to that basis:
        # a value at a later date and today's price are otherwise not comparable.
        # The weighted yearly return is earned from the dated close, which can be older than the analysis date.
        today = today_basis(accepted, close, rate_from_state(state), price.get("session_date"))
        if today is not None:
            summary.update(today, direction=_direction(Decimal(today["weighted_value_today"]), close),
                           direction_basis="value_today", sturdiness=sturdiness(accepted, close))
            # Equal weights on the other side of the close: the weights, not the cases, decide the comparison.
            equal = _decimal((summary["sturdiness"] or {}).get("equal_weight_vs_close_percent"))
            given = _decimal(today["weighted_today_vs_close_percent"])
            summary["weights_decide"] = bool(equal and given and (equal > 0) != (given > 0))
    rating = state.get("final_rating")
    contrary = ((rating in _BEARISH and summary["direction"] == "above")
                or (rating in _BULLISH and summary["direction"] == "below"))
    # Within 10 percent of the close the price test says nothing, but the accepted cases still say whether the
    # stock earns its required return. A rating on the other side of that owes a reason too.
    gap = _decimal(summary.get("return_gap_points"))
    summary["contrary_basis"] = "direction" if contrary else None
    if not contrary and gap is not None and ((rating in _BEARISH and gap > 0) or (rating in _BULLISH and gap < 0)):
        contrary, summary["contrary_basis"] = True, "return_gap"
    # Close to the required return the scenarios do not separate the stock from its price. There a Hold is a
    # Conditional Hold, and any other rating owes a reason other than this valuation. Code never changes the rating.
    if gap is not None:
        points, source = hold_band(state)
        near = abs(gap) <= points
        summary["hold_band"] = {"points": str(points), "source": source, "near": near}
        # Inside the band the band is the finding, whichever side of the required return the rating sits on.
        if near and rating in _BEARISH | _BULLISH and summary["contrary_basis"] != "direction":
            contrary, summary["contrary_basis"] = True, "near_required"
        summary["conditional_hold"] = near and rating == "Hold"
        summary["valuation_reading"] = valuation_reading(gap, points)
    # With a stated stock view the two questions are checked separately. The view is set against code's reading of
    # the scenarios; the rating, now the position action, is set against the view. Either may differ with a reason.
    view = summary["stock_view"]
    if view is not None:
        reading = summary["valuation_reading"]
        summary["view_check"] = ("consistent" if reading is None or view == reading else
                                 "explained" if summary["stock_view_reason"] else "unexplained")
        contrary = rating in _ACTION_SIDE and _ACTION_SIDE[rating] != _VIEW_SIDE[view]
        summary["contrary_basis"] = "action_against_view" if contrary else None
    summary["consistency"] = ("consistent" if not contrary else
                              "explained" if summary["rating_basis_reason"] else "unexplained")
    # A reason may argue against the code's return figure, but it may not restate it backwards.
    summary["reason_conflict"] = bool(
        summary["consistency"] == "explained" and gap is not None and gap != 0
        and (_SAYS_MISSED if gap > 0 else _SAYS_CLEARED).search(summary["rating_basis_reason"]))
    return summary


_HURDLE = r"(?:required\s+(?:annual\s+|yearly\s+)?(?:rate\s+of\s+)?return|required\s+rate|hurdle(?:\s+rate)?)"
_NEAR = r"(?:(?!\.\s)[^;,]){0,30}?"
_SAYS_MISSED = re.compile(
    r"(?i)\b(?:below|under|beneath|short\s+of|less\s+than|lower\s+than|miss(?:es|ed)?|"
    r"(?:fails?|failed|failing)\s+to\s+(?:meet|clear|reach|exceed|beat)|"
    r"(?:does|do|did)\s+not\s+(?:meet|clear|reach|exceed|beat)|doesn't\s+(?:meet|clear|reach|exceed|beat))\b"
    + _NEAR + _HURDLE
    + r"|" + _HURDLE + r"\s+(?:is|was|remains)\s+not\s+(?:met|cleared|reached|exceeded)")
_SAYS_CLEARED = re.compile(
    r"(?i)\b(?:above|exceeds?|exceeded|clears?|cleared|meets?|beats?|more\s+than|higher\s+than|in\s+excess\s+of)\b"
    + _NEAR + _HURDLE
    + r"|" + _HURDLE + r"\s+(?:is|was)\s+(?:met|cleared|reached|exceeded)")


def _return_figures(summary) -> str:
    return (f"{Decimal(summary['weighted_annual_return']) * 100:+.1f}% a year against a required "
            f"{Decimal(summary['required_return']['rate']) * 100:.2f}%")


def retry_feedback(state, replayed) -> str:
    """What to send back to the manager once, or '' when its scenario answer can stand."""
    summary = summarize(state, replayed)
    if summary["status"] == "unaddressed":
        return ("Your scenario_view could not be used: " + " ".join(summary["problems"])
                + " Resubmit the complete decision with a valid scenario_view.")
    parts = []
    if summary.get("reason_conflict"):
        claim = "fall short of" if Decimal(summary["return_gap_points"]) > 0 else "clear"
        parts.append(
            f"Your rating_basis_reason says the accepted scenarios {claim} the required return. Code's figure on "
            f"those same cases: bought at the close they return {_return_figures(summary)}, a gap of "
            f"{Decimal(summary['return_gap_points']):+.1f} points. The value today already has the required "
            "return taken out, so its gap to the close is not a yearly return to hold against that rate. Resubmit "
            "the complete decision: start rating_basis_reason from the code's figure and say, with figures, why "
            "the rating still stands (naming any other basis you mean), or revise the rating or the scenario_view.")
    elif summary.get("consistency") == "unexplained" and summary.get("contrary_basis") == "return_gap":
        parts.append(
            "Your rating points against your own accepted scenarios: bought at the close, their weighted value "
            f"returns {_return_figures(summary)}, a gap of "
            f"{Decimal(summary['return_gap_points']):+.1f} points. Resubmit the complete decision and either state "
            "in rating_basis_reason, with figures, why the rating still stands, or revise the rating or the "
            "scenario_view.")
    elif summary.get("consistency") == "unexplained" and summary.get("contrary_basis") == "action_against_view":
        parts.append(
            f"Your stock_view is {summary['stock_view']} and your rating, the position action, is "
            f"{state.get('final_rating')}. They point different ways and you gave no reason. Resubmit the complete "
            "decision and state in rating_basis_reason what about the caller's position or portfolio leads to this "
            "action (its size against the standard weight, the loss budget, other holdings). Do not change the stock "
            "view to fit the action.")
    elif summary.get("consistency") == "unexplained" and summary.get("contrary_basis") == "near_required":
        parts.append(
            f"Your accepted scenarios return {_return_figures(summary)}, a gap of "
            f"{Decimal(summary['return_gap_points']):+.1f} points. That is inside the "
            f"{Decimal(summary['hold_band']['points']):g}-point band in which the scenarios do not separate the stock "
            "from its price. The rating that fits is Hold, which the report prints as a Conditional Hold with your "
            "conditions. Resubmit the complete decision: either rate Hold, or keep your rating and state in "
            "rating_basis_reason the reason, other than this valuation, that supports it.")
    elif summary.get("consistency") == "unexplained":
        basis = "weighted value today" if summary.get("direction_basis") == "value_today" else "weighted value"
        parts.append(f"Your rating points against your own accepted scenarios ({basis} {summary['direction']} the "
                     "completed close by more than 10 percent). Resubmit the complete decision and either state why in "
                     "rating_basis_reason or revise the rating or the scenario_view.")
    # There is one resubmission, so everything it must correct goes back together.
    if summary.get("view_check") == "unexplained":
        parts.append(
            f"Your stock_view is {summary['stock_view']}; code's reading of your accepted scenarios is "
            f"{summary['valuation_reading']} (they return {_return_figures(summary)}). Resubmit the complete decision: "
            "either state in stock_view_reason the evidence outside those scenarios that supports your view, or "
            "set the view the scenarios support.")
    if summary.get("weights_unequal") and not summary.get("weights_decide") and not summary.get("weight_basis"):
        parts.append(
            "Your weights depart from equal weights and you gave no basis for them. Resubmit the complete decision: "
            "either weight the accepted cases equally, or keep your weights and state in weight_basis, case by case, "
            "the evidence specific to this company that moves each weight away from equal.")
    if summary.get("weights_decide") and not summary.get("weight_basis"):
        parts.append(
            "Your weights decide the comparison with the close: with them the accepted cases are worth "
            f"{Decimal(summary['weighted_today_vs_close_percent']):+.1f}% against the close today, with equal weights "
            f"{Decimal(summary['sturdiness']['equal_weight_vs_close_percent']):+.1f}%. Resubmit the complete decision "
            "with weight_basis: the evidence, case by case, for weighting them this way rather than equally.")
    # The size test is printed by code and never sent back: asked to answer it, the manager changed the rating
    # to fit the caller's loss budget (three MSFT runs, 2026-11-12). The rating is the view of the stock.
    parts.append(event_feedback(summary.get("event_view")))
    return " ".join(part for part in parts if part)


def render_cases_for_manager(cases, required=None) -> str:
    if not cases:
        return "No priced scenario case in this run; omit scenario_view."
    valued = all(case.get("value_today") for case in cases)
    lines = ["Priced scenario cases. Each is conditional arithmetic on stated assumptions at its period end"
             + (". The value today is the period-end value brought back at the required return. "
                + render_required_return(required) if valued else ", not discounted to today:")]
    for case in cases:
        today = f" ({Decimal(case['value_today']):.2f} {case['unit']} today)" if valued else ""
        lines.append(f"- case_id {case['case_id']}, version {case['version']}, role {case['role']}, "
                     f"\"{case['name']}\": {Decimal(case['price']):.2f} {case['unit']} at {case['period_end']}{today}. "
                     f"{case['funding_summary']} {case.get('funding_bounds', '')} {case['reference_summary']} "
                     f"{case.get('guidance_floor', '')}"
                     .replace("  ", " ").rstrip())
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
        + ("compares the weighted value today of your accepted cases with the completed close, so a later value and "
           "today's price are on one time basis. If your rating points the " if valued else
           "compares the weighted value of your accepted cases with the completed close. If your rating points the ")
        + "other way by more than 10 percent, state why in rating_basis_reason."
        + " Give two separate answers. stock_view is your view of the stock alone, as if none were held: Attractive, "
          "Fair or Unattractive against the required return; code prints its reading of your scenarios beside it, and a "
          "view that differs needs stock_view_reason. The rating is the position action for this caller's position "
          "and portfolio. The two may differ (an attractive stock held too large is still a trim); then say why in "
          "rating_basis_reason."
        + " Start from equal weights across the cases you accept. Move a weight away from equal only for evidence "
          "specific to this company, and state in weight_basis, case by case, what that evidence is and how far it "
          "moves the weight. A general sense that the downside matters more, or that the base case is the central "
          "one, is not evidence. Code prints what equal weights would give."
        + (" The same applies inside 10 percent when the weighted value returns more than the required return and "
           "your rating is Underweight or Sell, or less than it and your rating is Overweight or Buy: give the "
           "reason with figures." if valued else "")
        + " This is a labelled conditional range, never a price target.")
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
             + ("; each value today is that value brought back at the required return stated below, and the "
                "rating check uses values today." if valued else " and are not discounted.")]
    for case in summary["cases"]:
        stance = (f"accepted, weight {Decimal(case['weight']):.2f}" if case["disposition"] == "accepted"
                  else f"rejected on {case['rejected_input'].replace('_', ' ')}")
        position = ((f"multiple {BANDS[case['reference_band']]} of its own history on the same basis"
                     if case.get("reference_same_basis") else
                     f"implied multiple {BANDS[case['reference_band']]} of its own history")
                    if case.get("reference_band") in BANDS else "reference position unavailable")
        flag = ("; " + (case.get("flag_note") or "flagged by accepted audit finding " + ", ".join(case["flagged_by"]))
                ) if case.get("flagged_by") else ""
        today = f" at {case['period_end']}, {_money(case['value_today'], case['unit'])} today" if case.get("value_today") else ""
        if case.get("annual_return") is not None:
            short = short_period(case.get("price"), summary.get("close"), summary.get("session_date"), case.get("period_end"))
            today += (f", {Decimal(short['period_return']) * 100:+.1f}% from the close over {short['days']} days "
                      f"({Decimal(case['annual_return']) * 100:+.1f}% if repeated for a year)" if short else
                      f", {Decimal(case['annual_return']) * 100:+.1f}% a year from the close")
        # "Assessed" covered the filed schedule only; the operating cash in a case is always an assumption.
        funding = {"assessed": "scheduled payments covered, operating cash assumed"}.get(
            case["funding"], f"funding {case['funding']}")
        lines.append(f"- {case['role']} — {case['name']}: {_money(case['price'], case['unit'])}{today}; "
                     f"{funding}; {position}; {stance}{flag}. Reason (unvalidated): {case['reason']}")
    if summary["range"] is None:
        lines.append("All priced cases were rejected; no conditional range is stated and the rating is a research opinion.")
        # A value today printed above is never left without the assumption behind it.
        return lines + render_return_parts(summary) + render_sizing_rule(summary)
    unit, span = summary["unit"], summary["range"]
    text = (f"Accepted range {_money(span['low'], unit)} to {_money(span['high'], unit)}; weighted value "
            f"{_money(summary['weighted_value'], unit)}")
    if summary["close"] is None:
        lines.append(text + ". No comparable completed close is available, so no comparison with the price is made.")
        return lines + render_sizing_rule(summary)
    lines.append(text + f", {Decimal(summary['weighted_vs_close_percent']):+.1f}% against the "
                 f"{summary['session_date']} close of {_money(summary['close'], unit)} "
                 f"(range {Decimal(summary['range_vs_close_percent']['low']):+.1f}% to "
                 f"{Decimal(summary['range_vs_close_percent']['high']):+.1f}%)."
                 + ("" if summary.get("direction_basis") == "value_today" else
                    f" Direction: {summary['direction']} the close, using a 10 percent threshold."))
    lines.extend(render_today_basis(summary))
    if summary.get("stock_view"):
        reading = summary.get("valuation_reading")
        lines.append(
            f"Stock view: {summary['stock_view']} (the Portfolio Manager's view of the stock alone"
            + (f"; code's reading of the accepted scenarios: {reading}, from a return of {_return_figures(summary)}"
               if reading and summary.get("weighted_annual_return") is not None else "") + ")."
            + (f" Why it differs from that reading (unvalidated): {summary['stock_view_reason']}"
               if summary.get("view_check") == "explained" else
               " It differs from that reading and no reason was given." if summary.get("view_check") == "unexplained" else ""))
        against = summary.get("contrary_basis") == "action_against_view"
        lines.append(
            f"Position action: {summary.get('position_action') or 'not recorded'} (what to do with the caller's position; "
            "sizes are in the Position and sizing block)."
            + (f" Why it differs from the stock view (unvalidated): {summary['rating_basis_reason']}"
               if against and summary.get("rating_basis_reason") else
               " It points a different way from the stock view and no reason was given." if against else ""))
    if summary.get("conditional_hold"):
        band = summary["hold_band"]
        lines.append(
            f"Conditional Hold: bought at the close the accepted scenarios return {_return_figures(summary)}, inside "
            f"the {Decimal(band['points']):g}-point band"
            + (" (set in your portfolio file)" if band["source"] == "portfolio file" else "")
            + " in which they do not separate the stock from its price. The Hold stands while the conditions in the "
            "advisory conditions list stay as they are; that list says what would move the rating up or down. A "
            "position over your loss budget is still reported in the Position and sizing block.")
    against = ("the rating is not Hold although the accepted scenarios sit inside the Hold band"
               if summary.get("contrary_basis") == "near_required" else
               "the rating points against the accepted scenarios, which return "
               + ("more" if _decimal(summary.get("return_gap_points")) > 0 else "less") + " than the required return"
               if summary.get("contrary_basis") == "return_gap" else
               "the rating points against the accepted scenarios")
    lines.append({"consistent": "Rating check: the rating does not point against the accepted scenarios.",
                  "explained": f"Rating check: {against}. Portfolio Manager's "
                               "reason (unvalidated): " + summary["rating_basis_reason"],
                  "unexplained": f"Rating check: {against} and no reason was given.",
                  }.get(summary["consistency"], "Rating check: not performed."))
    if summary.get("reason_conflict"):
        missed = Decimal(summary["return_gap_points"]) > 0
        lines.append(f"Code note on that reason: it says the required return is {'not met' if missed else 'met'}; on "
                     f"the accepted cases the return is {_return_figures(summary)}. The value today already has the "
                     "required return taken out, so its gap to the close is not a yearly return.")
    lines.extend(render_return_parts(summary))
    lines.extend(render_sturdiness(summary))
    if summary.get("weight_basis"):
        lines.append("Why these weights (the Portfolio Manager's statement, unvalidated): " + summary["weight_basis"])
    elif summary.get("weights_decide"):
        lines.append("The weights decide the comparison with the close (equal weights put the accepted cases on the "
                     "other side of it) and no basis for them was stated.")
    lines.extend(render_events(summary.get("event_view")))
    lines.extend(render_sizing_rule(summary))
    return lines


def render_today_basis(summary) -> list[str]:
    """The comparison the rating check uses when a required return is recorded."""
    if summary.get("direction_basis") != "value_today":
        return []
    unit, span, percent = summary["unit"], summary["range_today"], summary["range_today_vs_close_percent"]
    text = (f"On one time basis: accepted range today {_money(span['low'], unit)} to {_money(span['high'], unit)}; "
            f"weighted value today {_money(summary['weighted_value_today'], unit)}, "
            f"{Decimal(summary['weighted_today_vs_close_percent']):+.1f}% against the close (range "
            f"{Decimal(percent['low']):+.1f}% to {Decimal(percent['high']):+.1f}%).")
    if summary.get("weighted_annual_return") is not None:
        required = Decimal(summary["required_return"]["rate"]) * 100
        ends = {case.get("period_end") for case in summary.get("cases") or () if case.get("disposition") == "accepted"}
        short = short_period(summary.get("weighted_value"), summary.get("close"), summary.get("session_date"),
                             next(iter(ends))) if len(ends) == 1 else None
        yearly = f"{Decimal(summary['weighted_annual_return']) * 100:+.1f}% a year"
        tail = f"against a required {required:.2f}%, a gap of {Decimal(summary['return_gap_points']):+.1f} points."
        text += (f" Bought at the close, the weighted case returns {Decimal(short['period_return']) * 100:+.1f}% over the "
                 f"{short['days']} days to {next(iter(ends))}. The yearly figure, {yearly}, repeats that {short['days']}-day "
                 f"move for a full year and is not a forecast of one; it is set {tail}" if short else
                 f" Bought at the close, the weighted case returns {yearly} {tail}")
    return [text + f" Direction: {summary['direction']} the close, using a 10 percent threshold."]


def _billions(value):
    return f"{Decimal(value) / Decimal(10) ** 9:.2f}B"


def render_return_parts(summary) -> list[str]:
    """Per share, where each case's change from the close comes from."""
    rows = [case for case in summary["cases"] if case.get("return_parts")]
    if not rows:
        return []
    first = rows[0]["return_parts"]
    lines = [f"Where each case's value comes from, per share, from the {rows[0]['quote']['session_date']} close, applied in "
             f"order: revenue, then the multiple, then shares and net obligations. Today's price is "
             f"{Decimal(first['multiple_today']):.2f}x revenue of the last twelve months "
             f"({_billions(first['revenue_today'])}) on the case's own obligation basis; each case applies its multiple "
             "to revenue of the twelve months ending at its period end."]
    for case in rows:
        parts = case["return_parts"]
        lines.append(f"- {case['role']} — revenue to {_billions(parts['revenue_case'])}: "
                     f"{Decimal(parts['revenue_effect']):+.2f}; multiple {Decimal(parts['multiple_today']):.2f}x to "
                     f"{Decimal(parts['multiple_case']):.2f}x: {Decimal(parts['multiple_effect']):+.2f}; shares and net "
                     f"obligations: {Decimal(parts['capital_effect']):+.2f}; total {Decimal(parts['total']):+.2f} "
                     f"to {_money(case['price'], case['unit'])}.")
    return lines


def render_sturdiness(summary) -> list[str]:
    """How much the weights would have to change before the comparison with the close changes."""
    check = summary.get("sturdiness")
    if not check:
        return []
    unit, top = summary["unit"], check["highest"]
    text = (f"If the weights are wrong: with equal weights the value today is "
            f"{_money(check['equal_weight_value_today'], unit)}, {Decimal(check['equal_weight_vs_close_percent']):+.1f}% "
            "against the close.")
    given = f"{Decimal(top['weight']) * 100:.0f}%"
    if check["break_even"] == "available":
        text += (f" The highest accepted case ({top['role']}) would need a weight of "
                 f"{Decimal(check['break_even_weight']) * 100:.0f}%, against the {given} given, for the weighted value "
                 "today to equal the close.")
    elif check["break_even"] == "unreachable":
        text += " No accepted case is worth more than the close today, so no weighting reaches the close."
    else:
        text += " The other accepted cases already average at or above the close today, whatever weight the highest gets."
    return [text]


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
