"""A valuation submission that fails validation gets one correction attempt (Build R)."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from tests.test_case_valuation import revenue_case
from tests.test_operational_audit import observed
from tests.test_shared_valuation import state
from tradingagents.agents.shared_valuation import (
    prepare_shared_valuation,
    prepare_with_correction,
    render_shared_valuation,
    replay_cases,
)
from tradingagents.operational_audit import assess_audit, render_audit

SHAPE = "Shape: a JSON list of objects having exactly name and request."


def _report(body):
    return "Research\n```valuation_scenarios\n" + body + "\n```\nNarrative."


def _state(body):
    base = state([])
    base["financial_claim_validation"] = {"raw_report": _report(body)}
    return base


def _misplaced_capital():
    """Run c463bdac: capital closed outside request, one brace too many."""
    row = revenue_case()
    capital = row["request"].pop("capital")
    return "[" + json.dumps(row)[:-1] + ',"capital":' + json.dumps(capital) + "}}]"


def _invalid_label():
    row = revenue_case()
    row["request"]["capital"]["cash"]["assumption"] = "guess"
    return row


def _conversion_without_instrument():
    """Run 2a2e47dd: a conversion share change with no instrument."""
    row = revenue_case()
    changes = row["request"]["capital"]["share_changes"]
    changes[0] = {"source": "conversion", "shares": changes[0]["shares"], "converted_principal": "1000",
                  "reason": "as stated"}
    return row


class Model:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.prompts = reply, error, []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.reply)


def _fenced(rows):
    return "```valuation_scenarios\n" + json.dumps(rows) + "\n```"


# R1 ------------------------------------------------------------------------

def test_unreadable_block_says_where_the_json_breaks():
    record = prepare_shared_valuation(_state(_misplaced_capital()))
    assert record["submission_error"] == "unreadable" and not record["rows"]
    reason = record["reasons"][0]
    assert reason.startswith("Valuation block is not valid JSON: ") and ' near "' in reason
    assert '"}}}}]' in reason or '}}]' in reason


def test_capital_beside_request_is_read_inside_it_and_prices_the_same():
    expected = prepare_shared_valuation(state([revenue_case()]))["rows"][0]["result"]["target"]
    row = revenue_case()
    row["capital"] = row["request"].pop("capital")
    record = prepare_shared_valuation(state([row]))
    assert record["rows"][0]["result"]["target"] == expected and "submission_error" not in record
    assert record["reasons"] == ["Row 1: capital was submitted beside request; code read it inside request, "
                                 "content unchanged."]


def test_a_field_beside_request_that_code_cannot_place_is_still_named():
    both = revenue_case()
    both["capital"] = dict(both["request"]["capital"])     # two capitals: which one is meant is not code's call
    record = prepare_shared_valuation(state([both]))
    assert record["reasons"] == [
        "Row 1 omitted: unexpected field capital beside name and request; capital belongs inside request"]
    other = revenue_case()
    other["multiple"] = "3"
    assert "unexpected field multiple beside name and request" in prepare_shared_valuation(state([other]))["reasons"][0]
    assert "submission_error" not in record


@pytest.mark.parametrize("report,kind,text", [
    ("Research with no block.", "missing_block", "No valuation_scenarios block was found"),
    (_report("[]") + "\n" + _report("[]"), "duplicate_block", "More than one valuation_scenarios block"),
    (_report("[" + " " * 48001 + "]"), "oversized", "Valuation block is larger than"),
    (_report(json.dumps([revenue_case(), revenue_case()])), "duplicate_names", "Scenario names must be distinct"),
    (_report(json.dumps({"name": "x"})), "unreadable", "Valuation block must be a JSON list"),
    (_report(json.dumps([{"name": f"n{i}", "request": {}} for i in range(4)])), "too_many", "at most three"),
])
def test_each_whole_submission_failure_has_its_own_reason(report, kind, text):
    base = state([])
    base["financial_claim_validation"] = {"raw_report": report}
    record = prepare_shared_valuation(base)
    assert record["submission_error"] == kind and text in record["reasons"][0]
    assert not record["rows"]


def test_valid_and_empty_submissions_have_no_submission_error():
    for rows in ([], [revenue_case()]):
        assert "submission_error" not in prepare_shared_valuation(state(rows))
    missing_evidence = state([revenue_case()])
    missing_evidence["financial_evidence"] = None
    record = prepare_shared_valuation(missing_evidence)
    assert "submission_error" not in record and "canonical evidence" in record["reasons"][0]


# R2 ------------------------------------------------------------------------

@pytest.mark.parametrize("broken", ["brace", "label", "instrument"])
def test_a_rejected_submission_is_corrected_once_and_priced(broken):
    body = {"brace": _misplaced_capital(), "label": json.dumps([_invalid_label()]),
            "instrument": json.dumps([_conversion_without_instrument()])}[broken]
    inputs = _state(body)
    first = prepare_shared_valuation(inputs)
    assert not first["rows"]
    model = Model(_fenced([revenue_case()]))
    record = prepare_with_correction(inputs, model, SHAPE)
    assert len(model.prompts) == 1
    prompt = model.prompts[0]
    assert body in prompt and first["reasons"][0] in prompt and SHAPE in prompt
    assert record["status"] == "available" and len(record["rows"]) == 1
    expected = prepare_shared_valuation(state([revenue_case()]))["rows"][0]["result"]["target"]
    assert record["rows"][0]["result"]["target"] == expected
    cause = first["reasons"][0].removeprefix("Row 1 omitted: ")
    note = f"Row 1: corrected by the analyst after a validation error: {cause}"
    assert record["reasons"] == [note] and note in render_shared_valuation(record)
    # The analyst's report is untouched, and every later replay prices the corrected case.
    assert inputs["financial_claim_validation"]["raw_report"] == _report(body)
    saved = {**inputs, "shared_valuation_scenarios": record}
    for replayed in (replay_cases(saved), replay_cases({**saved, "shared_valuation_scenarios": replay_cases(saved)})):
        assert len(replayed["rows"]) == 1 and replayed["reasons"] == [note]
        assert replayed["corrected_submission"] == record["corrected_submission"]


def test_a_correction_that_is_still_invalid_keeps_the_original_record():
    inputs = _state(_misplaced_capital())
    first = prepare_shared_valuation(inputs)
    for reply in (_fenced([_invalid_label()]), "I cannot fix this.", _misplaced_capital(), ""):
        record = prepare_with_correction(inputs, Model(reply), SHAPE)
        assert not record["rows"] and record["submission_error"] == "unreadable"
        assert record["reasons"] == [*first["reasons"], "Correction attempt did not produce an accepted case."]
        assert "corrected_submission" not in record


def test_a_correction_may_not_alter_a_case_that_was_already_priced():
    good, bad = revenue_case(), _invalid_label()
    bad["name"] = "Downside"
    inputs = state([good, bad])
    changed = deepcopy(good)
    changed["request"]["multiple"] = "9"
    fixed = revenue_case()
    fixed["name"] = "Downside"
    record = prepare_with_correction(inputs, Model(_fenced([changed, fixed])), SHAPE)
    assert [row["name"] for row in record["rows"]] == ["Base"]
    assert record["reasons"][-1] == "Correction attempt did not produce an accepted case."
    kept = prepare_with_correction(inputs, Model(_fenced([good, fixed])), SHAPE)
    assert [row["name"] for row in kept["rows"]] == ["Base", "Downside"]
    assert kept["reasons"] == ["Row 2: corrected by the analyst after a validation error: "
                               "malformed valuation request at capital.cash.assumption"]


def test_a_provider_error_leaves_the_original_record():
    inputs = _state(_misplaced_capital())
    record = prepare_with_correction(inputs, Model(error=RuntimeError("secret detail")), SHAPE)
    assert not record["rows"] and record["reasons"][-1] == "Correction attempt failed: RuntimeError."
    assert "secret" not in json.dumps(record)


@pytest.mark.parametrize("make", [
    lambda: state([]), lambda: state([revenue_case()]),
    lambda: {**state([_invalid_label()]), "evidence_quality": {"status": "insufficient"}},
    lambda: {**_state("x"), "financial_claim_validation": {"raw_report": "No block."}},
    lambda: {**state([_invalid_label()]), "financial_evidence": None},
])
def test_no_correction_call_when_nothing_can_be_corrected(make):
    model = Model(_fenced([revenue_case()]))
    inputs = make()
    assert prepare_with_correction(inputs, model, SHAPE) == prepare_shared_valuation(inputs)
    assert model.prompts == []


def test_a_saved_correction_for_a_different_report_is_ignored():
    inputs = _state(_misplaced_capital())
    record = prepare_with_correction(inputs, Model(_fenced([revenue_case()])), SHAPE)
    other = _state(json.dumps([_invalid_label()]))
    replayed = replay_cases({**other, "shared_valuation_scenarios": record})
    assert not replayed["rows"] and "corrected_submission" not in replayed


def test_list_content_from_the_model_is_read():
    inputs = _state(_misplaced_capital())
    model = Model([{"type": "text", "text": _fenced([revenue_case()])}])
    assert len(prepare_with_correction(inputs, model, SHAPE)["rows"]) == 1


def _named(row, name):
    row = deepcopy(row)
    row["name"] = name
    return row


def test_a_correction_may_not_drop_a_rejected_case():
    priced, second, third = revenue_case(), _named(_invalid_label(), "B"), _named(_invalid_label(), "C")
    inputs = state([priced, second, third])
    dropped = prepare_with_correction(inputs, Model(_fenced([priced, _named(revenue_case(), "B")])), SHAPE)
    assert [row["name"] for row in dropped["rows"]] == ["Base"]
    assert dropped["reasons"][-1] == "Correction attempt did not produce an accepted case."
    assert assess_audit({**observed(), "shared_valuation_scenarios": dropped})["score"] == 4
    partly = prepare_with_correction(
        inputs, Model(_fenced([priced, _named(revenue_case(), "B"), third])), SHAPE)
    assert [row["name"] for row in partly["rows"]] == ["Base", "B"]
    assert any(reason.startswith("Row 3 omitted: ") for reason in partly["reasons"])
    assert assess_audit({**observed(), "shared_valuation_scenarios": partly})["score"] == 4


def _unfunded():
    from tests.test_valuation_funding import request as funding_request

    return {"name": "Unfunded", "request": funding_request(cash_capex=500)}


def test_a_correction_into_an_unpriced_funding_diagnostic_is_not_a_recovery():
    diagnostic = prepare_shared_valuation(state([_unfunded()]))
    assert len(diagnostic["rows"]) == 1 and diagnostic["rows"][0]["result"]["target"] is None
    inputs = _state(_misplaced_capital())
    record = prepare_with_correction(inputs, Model(_fenced([_unfunded()])), SHAPE)
    assert not record["rows"] and "corrected_submission" not in record
    assert assess_audit({**observed(), "shared_valuation_scenarios": record})["score"] == 3


@pytest.mark.parametrize("model,reason", [
    (Model("no"), "Correction attempt did not produce an accepted case."),
    (Model(error=RuntimeError("x")), "Correction attempt failed: RuntimeError."),
])
def test_a_failed_correction_is_still_explained_after_replay(model, reason):
    inputs = _state(_misplaced_capital())
    record = prepare_with_correction(inputs, model, SHAPE)
    saved = {**inputs, "shared_valuation_scenarios": record}
    once = replay_cases(saved)
    twice = replay_cases({**saved, "shared_valuation_scenarios": once})
    for replayed in (once, twice):
        assert replayed["reasons"] == record["reasons"] and replayed["reasons"][-1] == reason
        assert reason in render_shared_valuation(replayed)
        assert replayed["submission_error"] == "unreadable"
    # No second attempt once one is on record, and none is replayed against another report.
    again = Model(_fenced([revenue_case()]))
    assert prepare_with_correction(saved, again, SHAPE)["reasons"] == record["reasons"] and again.prompts == []
    other = {**_state(json.dumps([_invalid_label()])), "shared_valuation_scenarios": record}
    assert reason not in replay_cases(other)["reasons"]


def test_an_accepted_revision_still_shows_that_the_analyst_case_was_corrected():
    inputs = _state(_misplaced_capital())
    record = prepare_with_correction(inputs, Model(_fenced([revenue_case()])), SHAPE)
    saved = {**inputs, "shared_valuation_scenarios": record}
    same = replay_cases(saved, revision=[revenue_case()])
    assert same["revision_status"] == "accepted" and len(same["rows"]) == 1
    note = 'Analyst case "Base" was corrected after a validation error before this revision: '
    assert [reason for reason in same["reasons"] if reason.startswith(note)]
    assert note in render_shared_valuation(same)
    again = replay_cases({**saved, "shared_valuation_scenarios": same})
    assert again["reasons"] == same["reasons"]
    renamed = replay_cases(saved, revision=[_named(revenue_case(), "Manager case")])
    assert renamed["revision_status"] == "accepted"
    assert not [reason for reason in renamed["reasons"] if "was corrected" in reason]


# R3 ------------------------------------------------------------------------

def test_an_unreadable_uncorrected_submission_is_degraded():
    record = prepare_with_correction(_state(_misplaced_capital()), Model("no"), SHAPE)
    assessment = assess_audit({**observed(), "shared_valuation_scenarios": record})
    assert (assessment["score"], assessment["findings"][0]["code"]) == (3, "valuation_cases_rejected")
    assert "could not be read" in assessment["findings"][0]["text"]


def test_a_corrected_submission_stays_strong_and_is_listed():
    record = prepare_with_correction(_state(_misplaced_capital()), Model(_fenced([revenue_case()])), SHAPE)
    assessment = assess_audit({**observed(), "shared_valuation_scenarios": record})
    assert assessment["score"] == 5 and assessment["findings"] == []
    assert "The analyst corrected its valuation submission after a validation error" in render_audit(assessment)
    clean = assess_audit({**observed(), "shared_valuation_scenarios": prepare_shared_valuation(state([revenue_case()]))})
    assert "corrected its valuation submission" not in render_audit(clean)


def test_a_missing_block_is_not_counted_as_a_lost_case():
    base = state([])
    base["financial_claim_validation"] = {"raw_report": "No block."}
    assert assess_audit({**observed(), "shared_valuation_scenarios": prepare_shared_valuation(base)})["score"] == 5
