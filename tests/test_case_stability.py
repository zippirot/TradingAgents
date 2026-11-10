"""Stability build: earlier cases carried forward, the rating check on the return gap, and what a flag means."""

import json
from decimal import Decimal

from tests.test_required_return import RETURN, _run, _three
from tests.test_scenario_decision import _accept, _state
from tradingagents.agents import scenario_decision
from tradingagents.agents.prior_cases import prior_cases, render_prior_cases

# 1. Earlier cases carried forward ------------------------------------------------------------------

CASES = [{"name": "Base", "scenario_role": "base", "request": {"method": "revenue_case", "multiple": "6.0"}}]


def test_the_analyst_is_shown_its_earlier_cases_and_what_is_new():
    text = render_prior_cases({"label": "2026-11-10 19:50 UTC (36c26c9d)", "cases": CASES,
                               "filings": {"status": "known", "rows": []}})
    assert "Your valuation cases in the last decision (2026-11-10 19:50 UTC (36c26c9d)) are below." in text
    assert "No new filing has been retained since then." in text
    assert "Choosing a different reference point, or reading the same evidence differently, is not a new fact." in text
    assert "'Changed since the last decision:'" in text
    block = text.split("```previous_valuation_scenarios\n")[1].split("\n```")[0]
    assert json.loads(block) == CASES
    newer = render_prior_cases({"label": "x", "cases": CASES, "filings": {"status": "known", "rows": [
        {"form": "10-K", "filed_date": "2027-02-24", "accession": "a"}]}})
    assert "Filings retained since then: 10-K filed 2027-02-24." in newer
    unknown = render_prior_cases({"label": "x", "cases": CASES, "filings": {"status": "unknown", "rows": []}})
    assert "could not be established" in unknown


def test_nothing_is_carried_when_there_is_nothing_usable():
    assert render_prior_cases(None) == "" and render_prior_cases({"cases": []}) == ""
    huge = [{"name": "Base", "request": {"method": "revenue_case", "note": "x" * 20000}}]
    assert render_prior_cases({"label": "x", "cases": huge, "filings": {"status": "known", "rows": []}}) == ""
    assert prior_cases({"results_dir": "/nonexistent-results"}, "DOCN", {"trade_date": "2026-11-10"}) is None


def test_earlier_cases_come_from_the_last_publication_and_reach_the_analyst_prompt(tmp_path, monkeypatch):
    from tests.test_assumption_history import inputs
    from tests.test_decision_brief import _published
    from tradingagents.graph.setup import GraphSetup

    first = inputs(multiple="6")
    config, record = _published(tmp_path, monkeypatch, first)
    current = inputs(multiple="6")
    context = prior_cases(config, "DOCN", current)
    assert context["decision_id"] == record["decision_id"] and context["filings"]["rows"] == []
    assert [case["request"]["multiple"] for case in context["cases"]] == ["6"]
    seen = {}

    def analyst(state):
        seen.update(state)
        return {}

    setup = GraphSetup.__new__(GraphSetup)
    setup.publication_config = config
    setup._with_prior_cases(analyst)(current)
    assert "```previous_valuation_scenarios" in seen["prior_case_context"] and '"multiple":"6"' in seen["prior_case_context"]
    # No publication store: the analyst is called exactly as before.
    seen.clear()
    setup.publication_config = None
    setup._with_prior_cases(analyst)(current)
    assert "prior_case_context" not in seen


def test_the_fundamentals_prompt_carries_the_earlier_cases_only_when_present():
    import inspect

    from tradingagents.agents.analysts import fundamentals_analyst

    source = inspect.getsource(fundamentals_analyst.create_fundamentals_analyst)
    assert '+ (state.get("prior_case_context") or "")' in source


def test_a_change_of_assumption_with_no_new_filing_is_named(tmp_path, monkeypatch):
    from tests.test_assumption_history import inputs
    from tests.test_decision_brief import _published
    from tradingagents.agents.decision_brief import render as render_brief, since_last_decision

    config, _record = _published(tmp_path, monkeypatch, inputs(multiple="3"))
    brief = since_last_decision(config, "DOCN", inputs(multiple="4"))
    brief["filings"] = {"status": "known", "rows": []}
    line = "- Case assumptions changed and no new filing was retained between the two runs"
    assert any(text.startswith(line) for text in render_brief(brief))
    assert any("which new fact supports each change you rely on" in text for text in render_brief(brief, for_manager=True))
    brief["filings"] = {"status": "known", "rows": [{"form": "10-K", "filed_date": "2027-02-24", "accession": "a"}]}
    assert not any(text.startswith(line) for text in render_brief(brief))
    same = since_last_decision(config, "DOCN", inputs(multiple="3"))
    same["filings"] = {"status": "known", "rows": []}
    assert not any(text.startswith(line) for text in render_brief(same))


# 2. The rating check on the return gap ---------------------------------------------------------------

# Three cases against a 78.30 close whose weighted value today is within 10% of it but beats the required return.
NEAR = [_accept("base", 0.40), _accept("down", 0.05), _accept("up", 0.55)]
# Also within 10% of the close, but short of the required return.
SHORT = [_accept("base", 0.50), _accept("down", 0.10), _accept("up", 0.40)]


def test_a_bearish_rating_on_cases_that_beat_the_required_return_owes_a_reason():
    summary = _run(NEAR)
    assert summary["direction"] == "near" and Decimal(summary["return_gap_points"]) > 0
    assert (summary["consistency"], summary["contrary_basis"]) == ("unexplained", "return_gap")
    state = {**_state(NEAR), "trade_date": "2026-11-10", "required_return": RETURN}
    feedback = scenario_decision.retry_feedback(state, _three())
    assert "against a required 9.86%" in feedback and "rating_basis_reason, with figures" in feedback
    text = "\n".join(scenario_decision.render(summary))
    assert ("Rating check: the rating points against the accepted scenarios, which return more than the required "
            "return and no reason was given.") in text
    explained = scenario_decision.summarize(
        {**_state(NEAR, reason="Lease rent is outside every case."), "trade_date": "2026-11-10",
         "required_return": RETURN}, _three())
    assert explained["consistency"] == "explained"
    assert "Lease rent is outside every case." in "\n".join(scenario_decision.render(explained))


def test_the_return_gap_test_does_not_touch_ratings_it_agrees_with_or_hold():
    for rating in ("Hold", "Overweight", "Buy"):
        state = {**_state(NEAR, rating=rating), "trade_date": "2026-11-10", "required_return": RETURN}
        assert scenario_decision.summarize(state, _three())["consistency"] == "consistent"
    # The mirror case: a bullish rating on cases that fall short of the required return.
    short = scenario_decision.summarize({**_state(SHORT, rating="Overweight"), "trade_date": "2026-11-10",
                                         "required_return": RETURN}, _three())
    assert short["direction"] == "near" and Decimal(short["return_gap_points"]) < 0
    assert (short["consistency"], short["contrary_basis"]) == ("unexplained", "return_gap")
    assert "which return less than the required return" in "\n".join(scenario_decision.render(short))
    assert _run(SHORT)["consistency"] == "consistent"
    # Without a required return there is no gap and the old 10 percent rule stands alone.
    assert _run(SHORT, required=None)["contrary_basis"] is None
    # NEAR undiscounted is more than 10% above the close, so the old rule, not the gap, is what fires.
    assert _run(NEAR, required=None)["contrary_basis"] == "direction"
    # A direction contradiction keeps its own wording.
    high = [_accept("base", 0.1), _accept("down", 0.1), _accept("up", 0.8)]
    summary = _run(high)
    if summary["direction"] == "above":
        assert summary["contrary_basis"] == "direction"


# 3. What a flag means ----------------------------------------------------------------------------------

def test_a_finding_about_another_roles_statement_does_not_read_as_a_disputed_case():
    from tests.test_disputed_case_range import inputs
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )
    from tradingagents.agents.shared_valuation import (
        annotate_disputed_cases,
        render_shared_valuation,
        replay_cases,
    )

    value = inputs()
    finding = value["advisory_audit"]["findings"][0]
    finding.update(role="bear_researcher", quoted_claim="The downside does not need the ATM to hold")
    from tradingagents.agents.audit_pass import prepare_audit_dispositions
    value["unvalidated_outputs"]["portfolio_manager"]["structured"]["audit_dispositions"] = [
        {"finding_id": f["finding_id"], "disposition": "accepted", "reason": "Reviewed"}
        for f in prepare_audit_dispositions(value)["findings"]]
    rows = annotate_disputed_cases(value, replay_cases(value))["rows"]
    flagged = next(row for row in rows if row.get("disputed_by"))
    assert flagged["dispute_note"].endswith("corrects a statement the bear researcher made about this case; "
                                            "its inputs and arithmetic are not disputed")
    card = prepare_decision_context(value)
    assert card["scenarios"]["disputed_count"] == 0
    text = render_decision_context(card)
    assert "its inputs and arithmetic are not disputed" in text and "flagged by accepted audit finding" not in text
    assert "inputs not disputed" in render_shared_valuation(annotate_disputed_cases(value, replay_cases(value)))


def test_a_finding_about_the_cases_own_inputs_keeps_the_disputed_wording():
    from tests.test_disputed_case_range import inputs
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )

    card = prepare_decision_context(inputs())
    assert card["scenarios"]["disputed_count"] == 1
    assert "flagged by accepted audit finding" in render_decision_context(card)


# Audit closure -------------------------------------------------------------------------------------

def _with_capital(field, amount):
    from tests.test_assumption_history import inputs, set_cases
    from tests.test_case_valuation import revenue_case

    row = revenue_case()
    target = row["request"]["capital"]["cash"] if field == "cash" else row["request"]["capital"]["obligations"]["borrowings"]
    target["value"] = str(amount)
    if field == "cash":
        from tests.test_case_valuation import bridge
        bridge(row["request"])
    return set_cases(inputs(), [row])


def test_a_cash_only_or_obligation_only_change_is_named_too(tmp_path, monkeypatch):
    # F1: the warning relied on a comparison that covered forecast, multiple and shares only.
    from tests.test_assumption_history import inputs
    from tests.test_decision_brief import _published
    from tradingagents.agents.decision_brief import render as render_brief, since_last_decision

    config, _record = _published(tmp_path, monkeypatch, inputs())
    line = "- Case assumptions changed and no new filing was retained between the two runs"
    for field, amount in (("cash", 95), ("obligations", 150)):
        current = _with_capital(field, amount)
        assert current["shared_valuation_scenarios"]["rows"], "the changed case must still price"
        brief = since_last_decision(config, "DOCN", current)
        brief["filings"] = {"status": "known", "rows": []}
        assert any(row["field"] == field for row in brief["cases"]["rows"]), brief["cases"]["rows"]
        assert any(text.startswith(line) for text in render_brief(brief))
        assert any(text.startswith(line) for text in render_brief(brief, for_manager=True))
    unchanged = since_last_decision(config, "DOCN", inputs())
    unchanged["filings"] = {"status": "known", "rows": []}
    assert not any(text.startswith(line) for text in render_brief(unchanged))


def test_the_label_states_only_what_is_established(tmp_path, monkeypatch):
    # F2: no new filing is not the same as no new evidence (a price move can be a new fact).
    from tests.test_assumption_history import inputs
    from tests.test_decision_brief import _published
    from tradingagents.agents.decision_brief import render as render_brief, since_last_decision

    config, _record = _published(tmp_path, monkeypatch, inputs(multiple="3"))
    brief = since_last_decision(config, "DOCN", inputs(multiple="4"))
    brief["filings"] = {"status": "known", "rows": []}
    reader, manager = "\n".join(render_brief(brief)), "\n".join(render_brief(brief, for_manager=True))
    assert "not of evidence" not in reader and "not of evidence" not in manager
    assert "Where no new fact is named for a change, the earlier value remains the reference." in reader
    assert "say in your reasons which new fact supports each change you rely on" in manager
