"""Closure of the 2026-11-11 audit (run 432ea74b) and two defects seen in run 3f72250f."""
import copy
import json
from types import SimpleNamespace

from tests.test_case_valuation import revenue_case
from tests.test_citation_check import BRIEF, _state
from tests.test_event_view import ACCEPTED, _assess, _event, _set
from tests.test_shared_valuation import state
from tradingagents.agents.citation_check import check_pm_citations
from tradingagents.agents.evidence_presentation import PORTFOLIO_WITHHELD, without_portfolio_figures
from tradingagents.agents.shared_valuation import prepare_with_correction

RATES = {"operating_cash_margin": "0.30", "operating_cash_reason": "Near the filed margin.",
         "capex_rate": "0.12", "capex_reason": "Near the filed rate."}


class Model:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.reply)


def _fenced(rows):
    return "```valuation_scenarios\n" + json.dumps(rows) + "\n```"


def _with(row, *, changes=(), cash="100", model=None, flags=None):
    row = copy.deepcopy(row)
    capital = row["request"]["capital"]
    capital["cash_changes"] = [dict(change) for change in changes]
    capital["cash"] = {**capital["cash"], "value": cash,
                       "assumption": "unchanged_from_snapshot" if cash == "100" else capital["cash"].get("assumption")}
    for key in ("cash_model", "operations_after_lease_interest", "operations_include_new_lease_rent"):
        capital.pop(key, None)
    if model:
        capital["cash_model"] = dict(model)
    if flags:
        capital["operations_after_lease_interest"], capital["operations_include_new_lease_rent"] = flags
    return row


BALANCED = ({"source": "operations", "amount": "40", "reason": "Chosen to balance."},
            {"source": "capex", "amount": "-40", "reason": "Chosen to balance."})


def test_amounts_that_balance_to_zero_are_asked_for_rates_once_and_the_rates_replace_them():
    """Run 3f72250f: the analyst kept +500M / -179.5M / -320.5M from its prior cases and was asked nothing."""
    plug = _with(revenue_case(), changes=BALANCED, flags=(True, False))
    rated = _with(revenue_case(), model=RATES, flags=(True, False))
    model = Model(_fenced([rated]))
    record = prepare_with_correction(state([plug]), model, "SHAPE")
    assert len(model.prompts) == 1
    assert "amounts that sum to zero" in model.prompts[0]
    # F1: the request must not ask for rates beside the amounts the validator rejects together.
    assert "Leave cash and cash_changes as they are" not in model.prompts[0]
    assert "Remove the operations, capex and finance_payments entries" in model.prompts[0]
    capital = record["rows"][0]["request"]["capital"]
    assert capital["cash_model"]["capex_rate"] == "0.12" and not capital.get("cash_changes")
    assert record["corrected_submission"]["kind"] == "cash_bridge"
    # A reply that keeps balancing amounts is not accepted as an answer.
    kept = Model(_fenced([plug]))
    assert "corrected_submission" not in prepare_with_correction(state([plug]), kept, "SHAPE")


def test_a_case_with_operating_cash_but_no_capex_can_answer_with_rates():
    """F1: the one request was wasted because rates beside the kept operations amount fail validation."""
    half = _with(revenue_case(), changes=[{"source": "operations", "amount": "40", "reason": "Operating cash."}],
                 cash="140", flags=(True, False))
    rated = _with(revenue_case(), model=RATES, flags=(True, False))
    record = prepare_with_correction(state([half]), Model(_fenced([rated])), "SHAPE")
    assert record["rows"][0]["request"]["capital"]["cash_model"]["operating_cash_margin"] == "0.30"


def test_rates_without_the_two_lease_answers_are_asked_for_them():
    """F2: a rates-only case left the lease-interest and new-rent questions open and was treated as complete."""
    open_ = _with(revenue_case(), model=RATES)
    answered = _with(revenue_case(), model=RATES, flags=(True, False))
    model = Model(_fenced([answered]))
    record = prepare_with_correction(state([open_]), model, "SHAPE")
    assert len(model.prompts) == 1 and "operations_after_lease_interest" in model.prompts[0]
    assert record["rows"][0]["request"]["capital"]["operations_after_lease_interest"] is True
    # Still unanswered: the cases stand as submitted.
    again = prepare_with_correction(state([open_]), Model(_fenced([open_])), "SHAPE")
    assert "corrected_submission" not in again
    # Answered from the start: nothing is asked.
    quiet = Model("unused")
    prepare_with_correction(state([answered]), quiet, "SHAPE")
    assert quiet.prompts == []


def test_weights_that_one_mix_reproduces_within_the_stated_tolerance_are_accepted():
    """F3: least squares picked 53.6% (largest gap 0.0536) although a 50% mix is within 0.05 on every case."""
    accepted = [{**row, "weight": weight} for row, weight in zip(ACCEPTED, ("0.20", "0.35", "0.45"), strict=True)]
    summary = _assess([_event(favourable_weights=_set(0.20, 0.20, 0.60), adverse_weights=_set(0.30, 0.40, 0.30))],
                      accepted=accepted)
    assert summary["status"] == "addressed", summary["problems"]


def test_a_sign_word_in_another_clause_does_not_carry_the_sign():
    """F4: 'down' anywhere in the sentence let a positive figure pass against a negative fact."""
    brief = BRIEF.replace("- [C2]", "- [F35] Net Income: -42609000 USD; 2026-09-30; source S1\n- [C2]")

    def check(sentence):
        result = check_pm_citations({**_state(sentence), "canonical_financial_context": brief})
        return result["matched"], result["checked"]

    assert check("Q3 net income was $42.609 million (F35), down from last year.") == (0, 1)
    assert check("Margins fell, and the quarter's net loss was $42.609 million (F35).") == (1, 1)
    assert check("Q3 net loss was $42.609 million (F35).") == (1, 1)


def test_a_case_weight_with_words_between_is_not_a_portfolio_figure():
    """Run 3f72250f: all three case reasons were withheld for 'Subjective central weight retained: $1.93bn ...'."""
    for kept in ("Subjective central weight retained: $1.93bn 2027 revenue and 6x borrowings-only multiple assume "
                 "capacity ramp; funding and share assumptions remain illustrative.",
                 "Subjective downside weight retained: $1.70bn 2027 revenue and 4x multiple capture execution risk."):
        assert without_portfolio_figures(kept) == kept
    for leaked in ("The subjective view is that a 2.5% portfolio weight is right.",
                   "Subjective target weight of 2.5% is retained."):
        assert PORTFOLIO_WITHHELD in without_portfolio_figures(leaked)
