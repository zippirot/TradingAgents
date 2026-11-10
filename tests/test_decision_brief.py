"""What changed since the last decision: bookkeeping from saved records, then the manager's reading of it."""
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from tests.test_assumption_history import inputs, set_cases, store
from tests.test_case_valuation import revenue_case
from tradingagents.agents.decision_brief import (
    assessment_problems,
    finalize,
    render,
    since_last_decision,
)

QUOTE = {"status": "available", "close": "20", "currency": "USD", "session_date": "2026-10-19"}


def _two_cases():
    later = deepcopy(revenue_case())
    later["name"] = "Later"
    later["request"]["forecast"].update(period_start="2028-01-01", period_end="2028-12-31")
    later["request"]["capital"]["valuation_date"] = "2028-12-31"
    return [revenue_case(), later]


def _published(tmp_path, monkeypatch, value=None, **extra):
    config = {"results_dir": str(tmp_path)}
    value = value or inputs()
    value.update(extra)
    return config, store(config, value, monkeypatch)


# The comparison no longer fails whole ---------------------------------------

def test_one_unusable_earlier_case_is_named_and_the_other_case_is_still_compared(tmp_path, monkeypatch):
    from tradingagents.agents.assumption_history import assumption_changes

    prior = set_cases(inputs(), _two_cases())
    del prior["shared_valuation_scenarios"]["requests"][1]["request"]["multiple"]
    config, _record = _published(tmp_path, monkeypatch, prior)
    changed = _two_cases()
    changed[0]["request"]["multiple"] = "4"
    result = assumption_changes(config, "DOCN", set_cases(inputs(), changed))
    assert result["status"] == "available"
    assert [(row["scenario"], row["field"]) for row in result["rows"]] == [("Base", "multiple")]
    assert result["unusable"] == [{"side": "previous", "scenario": "Later", "reason": "multiple: Field required"}]


def test_a_case_retained_without_an_assumption_label_is_compared_as_an_estimate(tmp_path, monkeypatch):
    """Run 86aa515f: one missing label made the whole comparison unavailable (ValidationError)."""
    from tradingagents.agents.assumption_history import assumption_changes

    prior = inputs()
    del prior["shared_valuation_scenarios"]["requests"][0]["request"]["capital"]["obligations"]["borrowings"]["assumption"]
    config, _record = _published(tmp_path, monkeypatch, prior)
    result = assumption_changes(config, "DOCN", inputs("4"))
    assert result["status"] == "available" and "unusable" not in result
    assert [(row["scenario"], row["field"]) for row in result["rows"]] == [("Base", "multiple")]


def test_a_case_unusable_on_one_side_is_not_reported_as_added_or_dropped(tmp_path, monkeypatch):
    from tradingagents.agents.assumption_history import assumption_changes

    prior = set_cases(inputs(), _two_cases())
    del prior["shared_valuation_scenarios"]["requests"][1]["request"]["multiple"]
    config, _record = _published(tmp_path, monkeypatch, prior)
    result = assumption_changes(config, "DOCN", set_cases(inputs(), _two_cases()))
    assert result["rows"] == [] and len(result["unusable"]) == 1


def test_the_card_names_the_unusable_case(tmp_path, monkeypatch):
    from tradingagents.agents.assumption_history import assumption_changes
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_condition_summary,
    )

    prior = set_cases(inputs(), _two_cases())
    del prior["shared_valuation_scenarios"]["requests"][1]["request"]["multiple"]
    config, _record = _published(tmp_path, monkeypatch, prior)
    current = set_cases(inputs(), _two_cases())
    card = prepare_decision_context(current)
    card["assumption_changes"] = assumption_changes(config, "DOCN", current)
    text = render_condition_summary(card)
    assert "Not compared: case Later in the earlier record is unusable" in text


# The brief ------------------------------------------------------------------

def test_no_earlier_decision_gives_no_brief_and_no_card_entry(tmp_path):
    from tradingagents.agents.decision_context import prepare_decision_context

    current = inputs()
    brief = since_last_decision({"results_dir": str(tmp_path)}, "DOCN", current)
    assert brief["status"] == "no_prior" and render(brief) == [] and render(brief, for_manager=True) == []
    assert "since_last_decision" not in prepare_decision_context({**current, "decision_brief": brief})


def test_an_earlier_decision_the_same_day_is_compared_with_its_time_rating_and_price(tmp_path, monkeypatch):
    config, record = _published(tmp_path, monkeypatch, price_observation={
        **QUOTE, "close": "16", "session_date": "2026-10-16",
        "price_fallback": {"latest_completed_session_date": "2026-10-19"}})
    current = inputs("4")
    current["price_observation"] = dict(QUOTE)
    brief = since_last_decision(config, "DOCN", current)
    assert brief["status"] == "available" and brief["parts_unavailable"] == []
    assert brief["prior"] == {"decision_id": record["decision_id"], "as_of": "2026-10-19", "rating": "Hold",
                              "published_at": "2026-10-19 16:00 UTC", "label": brief["prior"]["label"]}
    assert brief["price"]["then"]["stale"] is True and brief["price"]["now"]["stale"] is False
    assert brief["price"]["change_percent"] == "25.00"
    text = "\n".join(render(brief))
    assert "Since the last decision** (2026-10-19 16:00 UTC, rating Hold, run " + record["decision_id"][:8] in text
    assert ("Price: 16.00 USD on 2026-10-16 (stale: the latest completed session had no close) then; "
            "20.00 USD on 2026-10-19 now; +25.0%.") in text
    assert "\"Base\" multiple 3× " in text and " to 4× " in text


def test_prices_in_different_currencies_get_no_percentage(tmp_path, monkeypatch):
    config, _record = _published(tmp_path, monkeypatch, price_observation={**QUOTE, "currency": "EUR"})
    current = inputs()
    current["price_observation"] = dict(QUOTE)
    brief = since_last_decision(config, "DOCN", current)
    assert brief["price"]["change_percent"] is None and "%" not in render(brief)[1]


def _filing(accession, form, filed):
    return {"source_id": "s-" + accession, "url": "https://www.sec.gov/x", "retrieved_at": "2026-10-19T00:00:00+00:00",
            "content_hash": "0" * 64, "blocks": [], "gaps": [], "rpo_facts": [],
            "filing": {"cik": "0001582961", "accession": accession, "form": form, "filed_date": filed,
                       "report_date": None, "primary_document": "d.htm", "items": "", "url": "https://www.sec.gov/x"}}


def _package(value, *documents):
    return {"schema_version": 1, "cik": value["financial_evidence"]["cik"], "as_of": value["trade_date"],
            "documents": list(documents), "gaps": [], "selected_accessions": []}


def test_a_new_filing_between_the_runs_is_listed(tmp_path, monkeypatch):
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    first = inputs()
    old = _filing("0001582961-26-000001", "10-Q", "2026-08-05")
    first["filing_evidence"] = _package(first, old)
    DisclosurePackage.model_validate(first["filing_evidence"])
    config, _record = _published(tmp_path, monkeypatch, first)
    current = inputs()
    current["filing_evidence"] = _package(current, old, _filing("0001582961-26-000002", "8-K", "2026-10-19"))
    brief = since_last_decision(config, "DOCN", current)
    assert brief["filings"]["rows"] == [{"form": "8-K", "filed_date": "2026-10-19",
                                         "accession": "0001582961-26-000002"}]
    assert "- Filings: 1 new since then: 8-K filed 2026-10-19." in render(brief)
    current["filing_evidence"] = _package(current, old)
    assert "- Filings: no new filing was retained between the two runs." in render(
        since_last_decision(config, "DOCN", current))
    del current["filing_evidence"]
    assert "- Filings: not comparable; one of the two runs retained no filing list." in render(
        since_last_decision(config, "DOCN", current))


def test_a_condition_that_changed_status_is_listed_and_unchanged_ones_are_counted(tmp_path, monkeypatch):
    first = inputs()
    first["decision_context"]["conditions"] = [{"condition_id": "c1", "status": "unknown"},
                                               {"condition_id": "c2", "status": "unknown"}]
    config, record = _published(tmp_path, monkeypatch, first)
    current = inputs()
    rows = [{"condition_id": "c1", "status": "met", "metric": "Gross Margin", "comparator": ">=",
             "threshold": "55.5", "unit": "percent"}, {"condition_id": "c2", "status": "unknown", "metric": "Revenue"}]
    current["prior_thesis"] = {"publication_id": record["decision_id"], "observations": rows}
    brief = since_last_decision(config, "DOCN", current)
    assert brief["conditions"] == {"status": "known", "tracked": 2, "rows": [
        {"condition": "Gross Margin >= 55.5 percent", "then": "unknown", "now": "met",
         "then_label": "Comparison unknown; thesis role unspecified",
         "now_label": "Comparison satisfied; thesis role unspecified"}]}
    assert ("- Advisory conditions changed: Gross Margin >= 55.5 percent: Comparison unknown; thesis role unspecified "
            "to Comparison satisfied; thesis role unspecified.") in render(brief)
    first["decision_context"]["conditions"][0]["status"] = "unobserved"
    rows[0]["status"] = "unknown"
    assert "- Advisory conditions: 2 tracked, none changed status." in render(
        since_last_decision(config, "DOCN", current))


def test_a_trigger_first_read_as_not_met_is_not_a_change_and_the_stored_word_is_never_printed(tmp_path, monkeypatch):
    """Run d58117ef printed 'unobserved to breached' for three price triggers a 78.30 close did not meet."""
    first = inputs()
    first["decision_context"]["conditions"] = [{"condition_id": "c3", "status": "breached"}]
    config, record = _published(tmp_path, monkeypatch, first)
    current = inputs()
    trigger = {"kind": "price_level", "thesis_role": "reconsideration_trigger", "currency": "USD"}
    rows = [{**trigger, "condition_id": "c1", "comparator": ">=", "threshold": "85.69", "status": "breached"},
            {**trigger, "condition_id": "c2", "comparator": "<", "threshold": "68.92", "status": "breached"},
            {**trigger, "condition_id": "c3", "comparator": ">", "threshold": "90.5", "status": "met"},
            {"condition_id": "c4", "thesis_role": "supports_thesis", "metric": "Gross Margin", "comparator": ">=",
             "threshold": "55.5", "unit": "percent", "status": "breached"}]
    current["prior_thesis"] = {"publication_id": record["decision_id"], "observations": rows}
    brief = since_last_decision(config, "DOCN", current)
    assert [(row["condition"], row["then_label"], row["now_label"]) for row in brief["conditions"]["rows"]] == [
        ("Completed close > 90.5 USD", "Reconsideration trigger not met", "Reconsideration trigger met"),
        ("Gross Margin >= 55.5 percent", "Unobserved; advisory question remains open", "Support condition breached")]
    line = next(text for text in render(brief) if text.startswith("- Advisory conditions changed"))
    assert "85.69" not in line and "68.92" not in line and "unobserved to breached" not in line
    assert "Reconsideration trigger not met to Reconsideration trigger met" in line
    old = {**brief, "conditions": {"status": "known", "tracked": 1, "rows": [
        {"condition": ">= 85.69", "then": "unobserved", "now": "breached"}]}}
    assert "- Advisory conditions changed: >= 85.69: no reading yet to comparison not satisfied." in render(old)


def test_one_unusable_part_is_named_and_the_rest_of_the_brief_stands(tmp_path, monkeypatch):
    config, _record = _published(tmp_path, monkeypatch, price_observation=dict(QUOTE))
    current = inputs()
    current["price_observation"] = dict(QUOTE)
    # Conditions carried from some other record cannot be compared with this one.
    current["prior_thesis"] = {"publication_id": "another-record", "observations": []}
    brief = since_last_decision(config, "DOCN", current)
    assert brief["status"] == "available" and brief["conditions"] is None
    assert brief["parts_unavailable"] == [{
        "part": "conditions", "reason": "advisory conditions in this run come from a different earlier record"}]
    text = "\n".join(render(brief))
    assert "- Price: 20.00 USD on 2026-10-19 then" in text and "- Not compared: conditions (" in text


def test_an_unreadable_earlier_record_is_stated_not_hidden(tmp_path, monkeypatch):
    from tradingagents.memory import publication

    config, _record = _published(tmp_path, monkeypatch)
    monkeypatch.setattr(publication, "load_evidence", lambda *a: (_ for _ in ()).throw(ValueError("changed")))
    brief = since_last_decision(config, "DOCN", inputs())
    assert brief["status"] == "unavailable"
    assert render(brief) == ["**Since the last decision**: comparison unavailable. "
                             "The earlier decision record could not be read (ValueError)."]
    assert assessment_problems(brief, "Hold", None) == []


def test_a_repriced_case_is_stated_with_both_values(tmp_path, monkeypatch):
    config, _record = _published(tmp_path, monkeypatch)
    brief = since_last_decision(config, "DOCN", inputs("4"))
    assert brief["cases"]["priced_then"] == brief["cases"]["priced_now"] == 1
    row = brief["cases"]["repriced"][0]
    assert row["scenario"] == "Base" and row["then"] != row["now"]
    assert "- Valuation cases: 1 priced (" in "\n".join(render(brief))
    assert f"\"Base\" repriced {float(row['then']):.2f} to {float(row['now']):.2f} USD" in "\n".join(render(brief))


# The manager's reading ------------------------------------------------------

BRIEF = {"version": 1, "status": "available", "parts_unavailable": [],
         "prior": {"decision_id": "86aa515f-9c88-4a0f-b0bf-af3964a20ce0", "as_of": "2026-11-09",
                   "label": "2026-11-09", "published_at": "2026-11-09 23:57 UTC", "rating": "Underweight"}}


@pytest.mark.parametrize(("rating", "answer", "problem"), [
    ("Underweight", {"status": "no_material_change", "reason": "Nothing new was filed."}, None),
    ("Underweight", {"status": "strengthens", "reason": "Margin fell again."}, None),
    ("Underweight", {"status": "weakens", "reason": "Price fell toward the base case."}, None),
    ("Hold", {"status": "weakens", "reason": "Funding was disclosed."}, None),
    ("Overweight", {"status": "reverses", "reason": "Funding was disclosed."}, None),
    ("Underweight", None, "change_assessment is missing"),
    ("Underweight", {"status": "bigger", "reason": "x"}, "change_assessment is missing"),
    ("Underweight", {"status": "weakens", "reason": " "}, "has no reason"),
    ("Hold", {"status": "no_material_change", "reason": "Nothing."}, "moved from Underweight to Hold"),
    ("Hold", {"status": "strengthens", "reason": "More."}, "moved from Underweight to Hold"),
    ("Underweight", {"status": "reverses", "reason": "Flip."}, "unchanged at Underweight"),
])
def test_the_reading_must_agree_with_the_two_ratings(rating, answer, problem):
    problems = assessment_problems(BRIEF, rating, answer)
    assert (problems == []) if problem is None else (problem in " ".join(problems))


def _pm_state(monkeypatch, brief=BRIEF):
    from tests.test_scenario_decision import _case_state

    state, _row = _case_state(monkeypatch)
    state["shared_valuation_scenarios"] = {"status": "unavailable", "requests": [], "rows": [], "reasons": []}
    state["financial_claim_validation"] = {"raw_report": "```valuation_scenarios\n[]\n```"}
    if brief is not None:
        state["decision_brief"] = brief
    return state


def test_manager_sees_the_brief_and_a_consistent_reading_needs_one_call(monkeypatch):
    from tests.test_scenario_decision import _decision, _manager

    answer = {"status": "no_material_change", "reason": "No filing and a small price move."}
    node, structured = _manager(_decision(change_assessment=answer))
    result = node(_pm_state(monkeypatch))
    assert structured.invoke.call_count == 1
    prompt = structured.invoke.call_args.args[0]
    assert "**Since the last decision** (2026-11-09 23:57 UTC, rating Underweight, run 86aa515f)" in prompt
    assert "Supply change_assessment" in prompt and "must be weakens or reverses" in prompt
    saved = result["unvalidated_outputs"]["portfolio_manager"]
    assert saved["change_contract"] == 1 and saved["structured"]["change_assessment"] == answer


def test_a_missing_reading_gets_one_correction_and_the_second_answer_is_used(monkeypatch):
    from tests.test_scenario_decision import _decision, _manager

    answer = {"status": "weakens", "reason": "Funding was disclosed."}
    node, structured = _manager(_decision(), _decision(rating="Hold", change_assessment=answer))
    result = node(_pm_state(monkeypatch))
    assert structured.invoke.call_count == 2
    assert "Your change_assessment could not be used: change_assessment is missing" in structured.invoke.call_args.args[0]
    assert result["final_rating"] == "Hold"


def test_a_rating_change_called_no_material_change_is_sent_back_once(monkeypatch):
    from tests.test_scenario_decision import _decision, _manager

    wrong = {"status": "no_material_change", "reason": "Nothing."}
    node, structured = _manager(_decision(rating="Hold", change_assessment=wrong),
                                _decision(rating="Hold", change_assessment=wrong))
    result = node(_pm_state(monkeypatch))
    assert structured.invoke.call_count == 2 and result["final_rating"] == "Hold"
    assert "moved from Underweight to Hold" in structured.invoke.call_args.args[0]


def test_without_a_brief_the_manager_prompt_and_record_are_as_before(monkeypatch):
    from tests.test_scenario_decision import _decision, _manager

    node, structured = _manager(_decision())
    result = node(_pm_state(monkeypatch, brief=None))
    assert structured.invoke.call_count == 1
    assert "Since the last decision" not in structured.invoke.call_args.args[0]
    assert "change_contract" not in result["unvalidated_outputs"]["portfolio_manager"]
    node, structured = _manager(_decision())
    node(_pm_state(monkeypatch, brief={"version": 1, "status": "no_prior", "prior": None, "parts_unavailable": []}))
    assert structured.invoke.call_count == 1
    assert "Since the last decision" not in structured.invoke.call_args.args[0]


def test_research_manager_is_shown_the_brief(monkeypatch):
    from tradingagents.agents.managers.research_manager import create_research_manager
    from tradingagents.agents.schemas import ResearchPlan

    llm = MagicMock()
    structured = llm.with_structured_output.return_value
    structured.invoke.return_value = ResearchPlan(recommendation="Hold", rationale="r", strategic_actions="s")
    state = {**_pm_state(monkeypatch), "investment_debate_state": {"history": "Debate", "count": 2}}
    create_research_manager(llm)(state)
    assert "**Since the last decision** (2026-11-09 23:57 UTC" in structured.invoke.call_args.args[0]
    assert "Supply change_assessment" not in structured.invoke.call_args.args[0]
    del state["decision_brief"]
    create_research_manager(llm)(state)
    assert "Since the last decision" not in structured.invoke.call_args.args[0]


# The page and the score -----------------------------------------------------

def _finished(monkeypatch, rating, answer):
    state = _pm_state(monkeypatch)
    state.update(final_rating=rating, final_trade_decision=f"**Rating**: {rating}",
                 evidence_quality={**state["evidence_quality"], "checks": []},
                 unvalidated_outputs={"portfolio_manager": {
                     "contract_version": "decision_horizon_v1", "scenario_contract": 1, "change_contract": 1,
                     "structured": {"time_horizon": "6 months", "executive_summary": "Summary.",
                                    "investment_thesis": "Thesis.", "change_assessment": answer}}})
    return state


def test_the_decision_page_opens_with_the_brief_above_the_thesis(monkeypatch):
    from tradingagents.agents.output_validation import enforce_publication

    state = _finished(monkeypatch, "Underweight", {"status": "strengthens", "reason": "Margin fell again."})
    text = enforce_publication(state)["final_trade_decision"]
    assert text.index("**Since the last decision**") < text.index("**Executive Summary")
    assert text.index("**Horizon**") < text.index("**Since the last decision**")
    assert "Portfolio Manager's reading (unvalidated): strengthens the earlier call. Margin fell again." in text
    assert "Change check: consistent with the two ratings." in text


def test_an_inconsistent_reading_is_printed_and_scored(monkeypatch):
    from tests.test_operational_audit import observed
    from tradingagents.agents.decision_context import prepare_decision_context
    from tradingagents.operational_audit import assess_audit

    state = _finished(monkeypatch, "Hold", {"status": "no_material_change", "reason": "Nothing."})
    card = prepare_decision_context(state)
    assert "moved from Underweight to Hold" in " ".join(render(card["since_last_decision"]))
    assessment = assess_audit({**observed(), "decision_context": card})
    assert (assessment["score"], assessment["findings"][0]["code"]) == (3, "change_assessment_unusable")
    good = prepare_decision_context(_finished(monkeypatch, "Hold", {"status": "weakens", "reason": "Funding."}))
    assert assess_audit({**observed(), "decision_context": good})["findings"] == []


def test_a_decision_made_before_this_contract_is_not_judged(monkeypatch):
    state = _finished(monkeypatch, "Hold", None)
    del state["unvalidated_outputs"]["portfolio_manager"]["change_contract"]
    assert "assessment" not in finalize(BRIEF, state)


def test_a_saved_card_is_rendered_without_recomputing(monkeypatch):
    from tradingagents.agents.decision_context import prepare_decision_context

    state = _finished(monkeypatch, "Underweight", {"status": "strengthens", "reason": "Margin fell again."})
    card = prepare_decision_context(state)
    del state["decision_brief"]
    assert prepare_decision_context({**state, "decision_context": card})["since_last_decision"] == card["since_last_decision"]


@pytest.mark.parametrize("status", [[], {}, 3, None])
def test_a_status_that_is_not_text_is_an_unusable_answer_not_a_crash(monkeypatch, status):
    from tests.test_scenario_decision import _decision, _manager
    from tradingagents.agents.decision_context import prepare_decision_context

    answer = {"status": status, "reason": "Changed."}
    assert "change_assessment is missing" in assessment_problems(BRIEF, "Hold", answer)[0]
    node, structured = _manager(_decision(change_assessment=answer), _decision(change_assessment=answer))
    node(_pm_state(monkeypatch))
    assert structured.invoke.call_count == 2
    assert "Your change_assessment could not be used" in structured.invoke.call_args.args[0]
    card = prepare_decision_context(_finished(monkeypatch, "Underweight", answer))
    assert card["since_last_decision"]["assessment"]["status"] is None
    assert "change_assessment is missing" in " ".join(render(card["since_last_decision"]))
