"""Part B: the six-month view built from dated events (arithmetic and checks)."""

from datetime import date
from decimal import Decimal

import pytest

from tradingagents.agents.event_view import (
    assess,
    horizon_date,
    open_conditions,
    render,
    render_for_manager,
    required,
    retry_feedback,
)

TODAY, HORIZON, RATE, CLOSE = "2026-11-10", date(2027, 5, 10), Decimal("0.10"), "80"
# Prices at 2027-12-31. At 10% a year, 235 days before that: 100 -> 94.05, 60 -> 56.43, 140 -> 131.67.
ACCEPTED = [
    {"case_id": "base", "version": 1, "price": "100", "period_end": "2027-12-31", "weight": "0.5"},
    {"case_id": "down", "version": 1, "price": "60", "period_end": "2027-12-31", "weight": "0.3"},
    {"case_id": "up", "version": 1, "price": "140", "period_end": "2027-12-31", "weight": "0.2"},
]
CONDITIONS = [{"condition_id": "condition-q4", "label": "Revenue >= 348000000 USD"},
              {"condition_id": "condition-notes", "label": "Notes settled"}]


def _set(base, down, up):
    return [{"case_id": "base", "version": 1, "weight": base}, {"case_id": "down", "version": 1, "weight": down},
            {"case_id": "up", "version": 1, "weight": up}]


def _event(**changes):
    return {"condition_id": "condition-q4", "expected_date": "2027-02-20", "favourable_when": "met",
            "favourable_weights": _set(0.5, 0.1, 0.4), "adverse_weights": _set(0.5, 0.5, 0.0),
            "reason": "Fourth-quarter revenue against the guidance low.", **changes}


def _assess(view, accepted=ACCEPTED, conditions=CONDITIONS, close=CLOSE, rate=RATE):
    return assess(accepted, conditions, view, TODAY, HORIZON, close, rate)


def test_horizon_date_adds_calendar_months_and_holds_to_month_end():
    assert horizon_date("2026-11-10", 6) == date(2027, 5, 10)
    assert horizon_date("2026-08-31", 6) == date(2027, 2, 28)
    assert horizon_date("2026-12-15", 1) == date(2027, 1, 15)
    assert horizon_date("not a date", 6) is None and horizon_date("2026-11-10", 0) is None


def test_only_unresolved_prior_conditions_can_be_named():
    rows = open_conditions([
        {"condition_id": "a", "status": "unknown", "metric": "Revenue", "comparator": ">=", "threshold": "348000000", "unit": "USD"},
        {"condition_id": "b", "status": "unobserved", "kind": "event", "description": "Notes settled"},
        {"condition_id": "c", "status": "met", "metric": "Gross Margin"},
        {"condition_id": "d", "status": "breached", "kind": "price_level", "comparator": "<", "threshold": "68.6"},
        {"status": "unknown"}, "text"])
    assert rows == [{"condition_id": "a", "label": "Revenue >= 348000000 USD"}, {"condition_id": "b", "label": "Notes settled"}]


def test_the_arithmetic_of_one_event():
    summary = _assess([_event()])
    assert summary["status"] == "addressed" and summary["problems"] == [] and summary["horizon_date"] == "2027-05-10"
    factor = Decimal("1.10") ** (Decimal(235) / Decimal(365))
    value = lambda base, down, up: (Decimal(base) * 100 + Decimal(down) * 60 + Decimal(up) * 140) / factor  # noqa: E731
    event = summary["events"][0]
    assert Decimal(summary["current_value"]).quantize(Decimal("0.0001")) == value("0.5", "0.3", "0.2").quantize(Decimal("0.0001"))
    high, low, now = value("0.5", "0.1", "0.4"), value("0.5", "0.5", "0.0"), value("0.5", "0.3", "0.2")
    assert Decimal(event["favourable"]["value"]).quantize(Decimal("0.0001")) == high.quantize(Decimal("0.0001"))
    assert Decimal(event["adverse"]["value"]).quantize(Decimal("0.0001")) == low.quantize(Decimal("0.0001"))
    assert Decimal(event["favourable"]["move_percent"]).quantize(Decimal("0.01")) == ((high / 80 - 1) * 100).quantize(Decimal("0.01"))
    # Today's 0.5 / 0.3 / 0.2 is exactly half of each outcome set. Before discounting: favourable 112, adverse 80,
    # current 96, so the value sits at the same 50%.
    assert Decimal(event["implied_odds_percent"]).quantize(Decimal("0.01")) == ((now - low) / (high - low) * 100).quantize(Decimal("0.01")) == Decimal("50.00")
    assert event["label"] == "Revenue >= 348000000 USD" and event["favourable_when"] == "met"


def test_not_asked_when_weights_cannot_move_or_values_cannot_be_computed():
    assert _assess(None, accepted=ACCEPTED[:1])["status"] == "not_applicable"
    assert _assess(None, conditions=[])["status"] == "not_applicable"
    assert _assess(None, rate=None)["status"] == "not_applicable"
    assert _assess(None, close=None)["status"] == "not_applicable"
    # A case whose period ends before the horizon date cannot be brought back to it.
    early = [{**ACCEPTED[0], "period_end": "2027-03-31"}, *ACCEPTED[1:]]
    assert _assess([_event()], accepted=early)["status"] == "not_applicable"
    assert not required(ACCEPTED, CONDITIONS, CLOSE, RATE, None)


def test_a_missing_view_is_unaddressed_when_asked():
    for view in (None, [], "text"):
        summary = _assess(view)
        assert summary["status"] == "unaddressed" and "event_view is missing" in summary["problems"][0]
        assert retry_feedback(summary).startswith("Your event_view could not be used: event_view is missing")
    assert retry_feedback(_assess([_event()])) == "" and retry_feedback(None) == ""


@pytest.mark.parametrize("change,fragment", [
    ({"condition_id": "condition-other"}, "is not an open advisory condition"),
    ({"expected_date": "2026-11-10"}, "needs an expected_date after 2026-11-10 and no later than 2027-05-10"),
    ({"expected_date": "2027-05-11"}, "needs an expected_date"),
    ({"expected_date": "soon"}, "needs an expected_date"),
    ({"favourable_when": "yes"}, "needs favourable_when"),
    ({"reason": " "}, "has no reason"),
    ({"favourable_weights": None}, "favourable_weights is missing"),
    ({"favourable_weights": _set(0.5, 0.1, 0.3)}, "favourable_weights sums to 0.9"),
    ({"adverse_weights": _set(0.5, 0.6, -0.1)}, "adverse_weights needs each accepted case once with a weight from 0 to 1"),
    ({"adverse_weights": _set(0.5, 0.5, 0.0)[:2]}, "adverse_weights must give a weight for every accepted case"),
    ({"adverse_weights": [*_set(0.5, 0.45, 0.0)[:2], {"case_id": "other", "version": 1, "weight": 0.05}]},
     "names a case that is not an accepted case"),
    ({"adverse_weights": [*_set(0.4, 0.3, 0.05), {"case_id": "down", "version": 1, "weight": 0.25}]},
     "needs each accepted case once"),
    # Favourable below adverse.
    ({"favourable_weights": _set(0.4, 0.55, 0.05), "adverse_weights": _set(0.5, 0.1, 0.4)}, "is not above"),
    ({"favourable_weights": _set(0.5, 0.3, 0.2), "adverse_weights": _set(0.5, 0.3, 0.2)}, "is not above"),
    # Today's weights are not a mix of these two sets.
    ({"favourable_weights": _set(0.6, 0.3, 0.1)}, "the three sets of weights disagree"),
])
def test_an_unusable_event_is_reported_and_nothing_is_computed(change, fragment):
    summary = _assess([_event(**change)])
    assert summary["status"] == "unaddressed" and summary["events"] == []
    assert any(fragment in problem for problem in summary["problems"]), summary["problems"]


def test_current_weights_equal_to_an_outcome_set_give_zero_or_full_odds():
    full = _assess([_event(favourable_weights=_set(0.5, 0.3, 0.2))])
    assert full["status"] == "addressed" and Decimal(full["events"][0]["implied_odds_percent"]) == 100
    none = _assess([_event(adverse_weights=_set(0.5, 0.3, 0.2))])
    assert none["status"] == "addressed" and Decimal(none["events"][0]["implied_odds_percent"]) == 0


def test_duplicates_extra_entries_and_one_bad_event_among_good_ones():
    twice = _assess([_event(), _event()])
    assert twice["status"] == "unaddressed" and any("more than once" in p for p in twice["problems"])
    second = _event(condition_id="condition-notes", expected_date="2026-12-15")
    both = _assess([_event(), second])
    assert both["status"] == "addressed" and [e["condition_id"] for e in both["events"]] == ["condition-q4", "condition-notes"]
    many = _assess([_event(), second, _event(condition_id="x"), _event(condition_id="y")])
    assert many["status"] == "unaddressed" and "at most 3 are used" in many["problems"][0]
    assert _assess([_event(), "text"])["status"] == "unaddressed"


def test_the_manager_is_shown_the_open_conditions_only_when_an_answer_can_be_used():
    text = render_for_manager(CONDITIONS, True, HORIZON)
    assert "- condition-q4: Revenue >= 348000000 USD" in text and "horizon date 2027-05-10" in text
    assert "Do not state a probability." in text
    assert render_for_manager([], True, HORIZON) == "" and render_for_manager(CONDITIONS, False, HORIZON) == ""
    assert render_for_manager(CONDITIONS, True, None) == ""


def test_the_reader_lines():
    lines = render(_assess([_event()]))
    assert lines[0].startswith("**Six-month view from dated events** (to 2027-05-10;")
    assert "On today's weights that is 90.29, +12.9% against the close of 80.00." in lines[0]
    assert lines[1] == ("- Revenue >= 348000000 USD (expected by 2027-02-20; favourable if met): 105.33 (+31.7%) if "
                        "favourable, 75.24 (-6.0%) if adverse; today's weights imply about 50% for the favourable "
                        "outcome. Reason (unvalidated): Fourth-quarter revenue against the guidance low.")
    assert lines[-1].startswith("The implied odds are not a probability the manager stated")
    unusable = render(_assess(None))
    assert len(unusable) == 1 and "not stated" in unusable[0] and "event_view is missing" in unusable[0]
    assert render(None) == [] and render({"status": "not_applicable"}) == []


# Through the scenario summary, the manager's retry and the report -------------------------------

from tests.test_required_return import RETURN, _three  # noqa: E402
from tests.test_scenario_decision import _accept, _state  # noqa: E402
from tradingagents.agents import scenario_decision  # noqa: E402

WEIGHED = [_accept("base", 0.55), _accept("down", 0.30), _accept("up", 0.15)]
OBSERVED = [{"condition_id": "condition-q4", "status": "unknown", "metric": "Revenue", "comparator": ">=",
             "threshold": "348000000", "unit": "USD"},
            {"condition_id": "condition-close", "status": "breached", "kind": "price_level", "comparator": "<",
             "threshold": "68.6"}]


def _weights(base, down, up):
    return [{"case_id": "base", "version": 1, "weight": base}, {"case_id": "down", "version": 1, "weight": down},
            {"case_id": "up", "version": 1, "weight": up}]


def _answer(**changes):
    return {"condition_id": "condition-q4", "expected_date": "2027-02-20", "favourable_when": "met",
            "favourable_weights": _weights(0.55, 0.15, 0.30), "adverse_weights": _weights(0.50, 0.45, 0.05),
            "reason": "Q4 revenue against the guidance low.", **changes}


def _decision(event_view, contract=True, view=WEIGHED, **extra):
    state = {**_state(view), "trade_date": "2026-11-10", "required_return": RETURN,
             "prior_thesis": {"publication_id": "p1", "observations": OBSERVED}, **extra}
    manager = state["unvalidated_outputs"]["portfolio_manager"]
    manager["configured_horizon_months"] = 6
    manager["structured"]["event_view"] = event_view
    if contract:
        manager["event_contract"] = 1
    return state


def test_the_summary_carries_the_event_view_and_the_card_prints_it():
    summary = scenario_decision.summarize(_decision([_answer()]), _three())
    events = summary["event_view"]
    assert events["status"] == "addressed" and events["horizon_date"] == "2027-05-10" and events["close"] == "78.30"
    event = events["events"][0]
    assert event["label"] == "Revenue >= 348000000 USD"
    assert Decimal(event["adverse"]["value"]) < Decimal(events["current_value"]) < Decimal(event["favourable"]["value"])
    assert 0 < Decimal(event["implied_odds_percent"]) < 100
    text = "\n".join(scenario_decision.render(summary))
    assert "**Six-month view from dated events** (to 2027-05-10;" in text
    assert "- Revenue >= 348000000 USD (expected by 2027-02-20; favourable if met):" in text
    assert scenario_decision.retry_feedback(_decision([_answer()]), _three()) == ""


def test_a_run_that_was_not_asked_is_not_judged():
    summary = scenario_decision.summarize(_decision(None, contract=False), _three())
    assert summary["event_view"]["status"] == "not_applicable"
    assert "Six-month view" not in "\n".join(scenario_decision.render(summary))
    assert scenario_decision.retry_feedback(_decision(None, contract=False), _three()) == ""
    # Asked, but nothing open to name: also not judged.
    resolved = _decision(None, prior_thesis={"observations": [OBSERVED[1]]})
    assert scenario_decision.summarize(resolved, _three())["event_view"]["status"] == "not_applicable"


def test_an_unusable_answer_is_sent_back_once_and_then_scored():
    from tradingagents.operational_audit import REASONS

    bad = _decision([_answer(favourable_weights=_weights(0.6, 0.35, 0.05))])
    feedback = scenario_decision.retry_feedback(bad, _three())
    assert feedback.startswith("Your event_view could not be used: Event condition-q4:")
    assert "Resubmit the complete decision with a valid event_view." in feedback
    summary = scenario_decision.summarize(bad, _three())
    assert summary["status"] == "addressed" and summary["event_view"]["status"] == "unaddressed"
    text = "\n".join(scenario_decision.render(summary))
    assert "**Six-month view from dated events**: not stated" in text
    assert REASONS["event_view_unaddressed"][0] == 3
    missing = scenario_decision.retry_feedback(_decision(None), _three())
    assert "event_view is missing" in missing


def test_the_rating_feedback_comes_first_and_the_event_feedback_is_not_lost():
    # A scenario answer that cannot be used is reported before any event problem.
    state = _decision([_answer()], view=None)
    assert scenario_decision.retry_feedback(state, _three()).startswith("Your scenario_view could not be used")


# Through the Portfolio Manager call ---------------------------------------------------------------

def _two_case_state(monkeypatch):
    import json as _json
    from copy import deepcopy

    from tests.test_case_valuation import revenue_case
    from tests.test_scenario_decision import _case_state
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    inputs, _row = _case_state(monkeypatch)
    upside = deepcopy(revenue_case())
    upside["name"], upside["request"]["multiple"] = "Upside", "4"
    rows = [revenue_case(), upside]
    inputs["financial_claim_validation"] = {**(inputs.get("financial_claim_validation") or {}),
                                            "raw_report": "R\n```valuation_scenarios\n" + _json.dumps(rows) + "\n```"}
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    priced = inputs["shared_valuation_scenarios"]["rows"]
    assert len(priced) == 2
    inputs["required_return"] = {**RETURN, "as_of": inputs["trade_date"]}
    inputs["prior_thesis"] = {"publication_id": "p1", "observations": OBSERVED}
    return inputs, priced


def _pm_answer(priced, event_view, weights=(0.6, 0.4)):
    from tests.test_scenario_decision import _decision as pm_decision

    view = [{"case_id": row["case_id"], "version": 1, "disposition": "accepted", "weight": weight,
             "rejected_input": None, "reason": "Reasonable."} for row, weight in zip(priced, weights, strict=True)]
    return pm_decision(rating="Hold", scenario_view=view, event_view=event_view)


def _pm_event(priced, favourable=(0.4, 0.6), adverse=(0.8, 0.2), **changes):
    def weights(pair):
        return [{"case_id": row["case_id"], "version": 1, "weight": weight} for row, weight in zip(priced, pair, strict=True)]
    return {"condition_id": "condition-q4", "expected_date": "2027-02-20", "favourable_when": "met",
            "favourable_weights": weights(favourable), "adverse_weights": weights(adverse), "reason": "Q4 revenue.",
            **changes}


def test_the_manager_is_asked_in_its_existing_call_and_a_valid_answer_needs_one_call(monkeypatch):
    from tests.test_scenario_decision import _manager

    inputs, priced = _two_case_state(monkeypatch)
    node, structured = _manager(_pm_answer(priced, [_pm_event(priced)]))
    result = node(inputs)
    assert structured.invoke.call_count == 1
    prompt = structured.invoke.call_args.args[0]
    assert "Six-month view from dated events (horizon date " in prompt
    assert "- condition-q4: Revenue >= 348000000 USD" in prompt and "condition-close" not in prompt
    record = result["unvalidated_outputs"]["portfolio_manager"]
    assert record["event_contract"] == 1 and record["structured"]["event_view"][0]["condition_id"] == "condition-q4"
    summary = scenario_decision.summarize({**inputs, **result}, inputs["shared_valuation_scenarios"])
    assert summary["event_view"]["status"] == "addressed"
    # 0.6 on the lower case sits halfway between 0.8 (adverse) and 0.4 (favourable).
    assert Decimal(summary["event_view"]["events"][0]["implied_odds_percent"]).quantize(Decimal("0.1")) == Decimal("50.0")


def test_a_missing_or_inconsistent_event_view_gets_the_one_correction(monkeypatch):
    from tests.test_scenario_decision import _manager

    inputs, priced = _two_case_state(monkeypatch)
    good = _pm_answer(priced, [_pm_event(priced)])
    node, structured = _manager(_pm_answer(priced, None), good)
    result = node(inputs)
    assert structured.invoke.call_count == 2
    assert "Your event_view could not be used: event_view is missing" in structured.invoke.call_args.args[0]
    assert result["unvalidated_outputs"]["portfolio_manager"]["structured"]["event_view"]
    # Current weights outside the two outcome sets: sent back once, and never a third time.
    bad = _pm_answer(priced, [_pm_event(priced, favourable=(0.7, 0.3))])
    node, structured = _manager(bad, bad)
    node(inputs)
    assert structured.invoke.call_count == 2
    assert "the three sets of weights disagree" in structured.invoke.call_args.args[0]


def test_the_manager_is_not_asked_without_open_conditions_a_return_or_two_cases(monkeypatch):
    from tests.test_scenario_decision import _manager

    for change in ({"prior_thesis": None}, {"required_return": None}):
        inputs, priced = _two_case_state(monkeypatch)
        inputs.update(change)
        node, structured = _manager(_pm_answer(priced, None))
        result = node(inputs)
        assert structured.invoke.call_count == 1
        assert "Six-month view from dated events" not in structured.invoke.call_args.args[0]
        assert "event_contract" not in result["unvalidated_outputs"]["portfolio_manager"]


def test_an_unusable_event_view_is_scored_three_and_a_usable_one_is_not(monkeypatch):
    from tests.test_operational_audit import observed
    from tradingagents.operational_audit import assess_audit

    def card(events):
        return {"scenario_decision": {"status": "addressed", "consistency": "consistent", "event_view": events}}

    unusable = {"status": "unaddressed", "events": [], "problems": ["event_view is missing: name one."]}
    assessment = assess_audit({**observed(), "decision_context": card(unusable)})
    assert (assessment["score"], assessment["findings"][0]["code"]) == (3, "event_view_unaddressed")
    assert "event_view is missing" in assessment["findings"][0]["text"]
    for fine in ({"status": "addressed", "events": [{}], "problems": []}, {"status": "not_applicable"}, None):
        assert assess_audit({**observed(), "decision_context": card(fine)})["findings"] == []


# Follow-through in a later run ------------------------------------------------------------------

def _earlier_events():
    cases = [{"case_id": "base", "version": 1, "role": "base", "name": "Base"},
             {"case_id": "down", "version": 1, "role": "downside", "name": "Downside"}]
    event = {"condition_id": "c1", "label": "Revenue >= 348000000 USD", "expected_date": "2026-10-25",
             "favourable_when": "met",
             "favourable": {"weights": [{"case_id": "base", "version": 1, "weight": "0.8"},
                                        {"case_id": "down", "version": 1, "weight": "0.2"}]},
             "adverse": {"weights": [{"case_id": "base", "version": 1, "weight": "0.4"},
                                     {"case_id": "down", "version": 1, "weight": "0.6"}]}}
    return {"status": "addressed", "cases": cases,
            "event_view": {"status": "addressed", "events": [event, {**event, "condition_id": "c2", "label": "Notes settled",
                                                                     "expected_date": "2027-03-01"}]}}


@pytest.mark.parametrize("status,expected", [
    ("met", ("favourable", "base 80%, downside 20%")), ("breached", ("adverse", "base 40%, downside 60%"))])
def test_a_later_run_states_which_outcome_occurred_and_the_weights_committed_to(tmp_path, monkeypatch, status, expected):
    from tests.test_assumption_history import inputs
    from tests.test_decision_brief import _published
    from tradingagents.agents.decision_brief import render as render_brief, since_last_decision

    first = inputs()
    first["decision_context"]["scenario_decision"] = _earlier_events()
    config, record = _published(tmp_path, monkeypatch, first)
    current = inputs()
    current["prior_thesis"] = {"publication_id": record["decision_id"], "observations": [
        {"condition_id": "c1", "status": status}, {"condition_id": "c2", "status": "unobserved"}]}
    brief = since_last_decision(config, "DOCN", current)
    assert brief["events"]["tracked"] == 2 and [row["outcome"] for row in brief["events"]["rows"]] == [expected[0]]
    line = next(line for line in render_brief(brief) if line.startswith("- Dated event"))
    assert line == (f"- Dated event resolved {expected[0]}: Revenue >= 348000000 USD. The earlier decision said it "
                    f"would then hold {expected[1]}.")
    brief["events"]["weights_now"] = [{"role": "base", "name": "Base", "weight": "0.5"},
                                      {"role": "downside", "name": "Downside", "weight": "0.5"}]
    assert any(line.endswith("This decision holds base 50%, downside 50%.") for line in render_brief(brief))


def test_unresolved_overdue_and_absent_events(tmp_path, monkeypatch):
    from tests.test_assumption_history import inputs
    from tests.test_decision_brief import _published
    from tradingagents.agents.decision_brief import render as render_brief, since_last_decision

    first = inputs()
    first["decision_context"]["scenario_decision"] = _earlier_events()
    config, record = _published(tmp_path, monkeypatch, first)
    current = inputs()
    current["prior_thesis"] = {"publication_id": record["decision_id"], "observations": [
        {"condition_id": "c1", "status": "unknown"}, {"condition_id": "c2", "status": "unobserved"}]}
    current["trade_date"] = "2026-10-19"
    brief = since_last_decision(config, "DOCN", current)
    assert brief["events"]["rows"] == [] and "- Dated events: 2 from the earlier decision, none resolved yet." in render_brief(brief)
    # Past its expected date with nothing read: said plainly.
    current["trade_date"] = "2026-10-26"
    late = since_last_decision(config, "DOCN", current)
    assert late["status"] == "available" and [row["outcome"] for row in late["events"]["rows"]] == ["overdue"]
    assert ("- Dated event: Revenue >= 348000000 USD was expected by 2026-10-25 and has not been read as resolved."
            in render_brief(late))
    # An earlier decision with no event view adds nothing.
    plain_config, _record = _published(tmp_path / "plain", monkeypatch, inputs())
    assert since_last_decision(plain_config, "DOCN", inputs())["events"] == {"status": "none", "rows": [], "tracked": 0}


# Audit closure ------------------------------------------------------------------------------------

def test_outcome_weights_that_no_single_probability_reconciles_are_sent_back():
    # F1: at 50/50 these outcome sets give 0.45 / 0.325 / 0.225, not today's 0.5 / 0.3 / 0.2; no one
    # probability reproduces today's weights within 5 points a case, although the values happen to line up.
    summary = _assess([_event(favourable_weights=_set(0.5, 0.1, 0.4), adverse_weights=_set(0.3, 0.7, 0.0))])
    assert summary["status"] == "unaddressed"
    assert "the three sets of weights disagree" in summary["problems"][0]
    assert "base" in summary["problems"][0] or "0." in summary["problems"][0]
    # A small rounding difference is not disagreement.
    near = _assess([_event(favourable_weights=_set(0.52, 0.1, 0.38), adverse_weights=_set(0.5, 0.5, 0.0))])
    assert near["status"] == "addressed"


def test_saying_no_listed_condition_is_expected_inside_the_horizon_is_an_answer():
    # F2: a truthful "none inside the horizon" must not be scored as a missing answer.
    summary = assess(ACCEPTED, CONDITIONS, [], TODAY, HORIZON, CLOSE, RATE,
                     none_reason="Both conditions depend on the 2027 annual report, due after the horizon.")
    assert summary["status"] == "none_expected" and summary["problems"] == []
    assert retry_feedback(summary) == ""
    lines = render(summary)
    assert len(lines) == 1 and "expects none of the open conditions to resolve by 2027-05-10" in lines[0]
    assert "due after the horizon" in lines[0]
    # Without a reason it is still a missing answer; with events supplied the reason is ignored.
    assert assess(ACCEPTED, CONDITIONS, [], TODAY, HORIZON, CLOSE, RATE, none_reason=" ")["status"] == "unaddressed"
    assert assess(ACCEPTED, CONDITIONS, [_event()], TODAY, HORIZON, CLOSE, RATE, none_reason="x")["status"] == "addressed"


def test_none_expected_through_the_manager_call_is_not_corrected_or_scored(monkeypatch):
    from tests.test_operational_audit import observed
    from tests.test_scenario_decision import _decision as pm_decision, _manager
    from tradingagents.operational_audit import assess_audit

    inputs, priced = _two_case_state(monkeypatch)
    view = [{"case_id": row["case_id"], "version": 1, "disposition": "accepted", "weight": weight,
             "rejected_input": None, "reason": "Reasonable."} for row, weight in zip(priced, (0.6, 0.4), strict=True)]
    node, structured = _manager(pm_decision(rating="Hold", scenario_view=view, event_view=None,
                                            no_event_reason="Nothing listed reports before the horizon date."))
    result = node(inputs)
    assert structured.invoke.call_count == 1
    summary = scenario_decision.summarize({**inputs, **result}, inputs["shared_valuation_scenarios"])
    assert summary["event_view"]["status"] == "none_expected"
    card = {"scenario_decision": summary}
    assert not [f for f in assess_audit({**observed(), "decision_context": card})["findings"]
                if f["code"] == "event_view_unaddressed"]


def test_identifiers_of_the_wrong_type_are_unusable_answers_not_crashes():
    """Audit run f4692472, F3: a list where an identifier belongs raised TypeError inside the checker."""
    for view in ([_event(condition_id=["condition-q4"])], [_event(condition_id={"id": 1})],
                 [_event(favourable_weights=[{"case_id": ["base"], "version": 1, "weight": 1}])],
                 [_event(adverse_weights=[{"case_id": "base", "version": [1], "weight": 1}])]):
        summary = _assess(view)
        assert summary["status"] == "unaddressed" and summary["problems"]
