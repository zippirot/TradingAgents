"""Code completes a case's cash bridge from the filing once the analyst gives operating cash flow.

It deducts the scheduled finance-lease and equipment payments the case does not state, and repays a note that
falls due inside the period. With no operating cash stated it does neither: a bridge with outflows only would
understate cash.
"""
from datetime import date
from decimal import Decimal

from tests.test_case_funding import NOTE, SCHEDULE, SNAPSHOT, _capital
from tradingagents.agents.valuation_cases import (
    STATEMENT,
    applied_payments,
    funded_cash,
    funded_statement,
    repaid_notes,
    scheduled_payments,
    settle_convertibles,
)

TERMS = {"schedule": SCHEDULE, "schedule_totals": {}, "leases": [], "notes": [NOTE]}
END = date(2027, 12, 31)
OPENING = Decimal(461630000)


def test_scheduled_payments_run_from_the_snapshot_to_the_period_end():
    scheduled, retained = scheduled_payments(TERMS, SNAPSHOT, END)
    assert scheduled == Decimal("320400000") and retained
    assert scheduled_payments({"schedule": None}, SNAPSHOT, END) == (None, False)
    assert scheduled_payments(TERMS, SNAPSHOT, date(2029, 12, 31)) == (None, True)     # 2029 is not in the table


def test_payments_are_deducted_only_from_a_bridge_that_starts_with_operating_cash():
    scheduled = Decimal("320400000")
    with_operations = _capital([("operations", 900000000), ("capex", -400000000)], borrowings=461630000)
    assert applied_payments(with_operations, scheduled) == scheduled
    funded = funded_cash(with_operations, SNAPSHOT, TERMS)
    assert funded["payments_applied"] == "320400000" and funded["adjustment"] == "-320400000"
    assert funded["decided"] == ["payments"] and "the filed schedule puts through 2027-12-31 is deducted" in funded["lines"][0]
    # No operating cash: nothing is deducted. Payments the case states itself: nothing is deducted twice.
    for changes in ([], [("capex", -1)], [("operations", 900000000), ("finance_payments", -320400000)]):
        capital = _capital(changes, borrowings=461630000)
        assert applied_payments(capital, scheduled) == 0
        assert funded_cash(capital, SNAPSHOT, TERMS).get("payments_applied") is None
    assert applied_payments(with_operations, None) == 0


def test_interest_inside_payments_code_deducts_is_added_back_like_interest_inside_stated_ones():
    from tests.test_funded_cash import TERMS as LEASE_TERMS
    base = {"valuation_date": "2027-12-31", "currency": "USD",
            "closing_shares": {"value": "120000000", "fact_ids": ["x"], "assumption": "estimated", "reason": "r"},
            "cash": {"value": "1", "fact_ids": ["x"], "assumption": "estimated", "reason": "r"},
            "obligations": {"borrowings": {"value": "149578000", "fact_ids": ["x"], "assumption": "estimated", "reason": "r"}},
            "operations_after_lease_interest": True, "operations_include_new_lease_rent": True}
    from tradingagents.agents.valuation_cases import CaseCapital
    stated = CaseCapital.model_validate({**base, "cash_changes": [
        {"source": "operations", "amount": "900000000", "reason": "r"},
        {"source": "finance_payments", "amount": "-320453000", "reason": "r"}]})
    by_code = CaseCapital.model_validate({**base, "cash_changes": [
        {"source": "operations", "amount": "900000000", "reason": "r"}]})
    one, other = funded_cash(stated, SNAPSHOT, LEASE_TERMS), funded_cash(by_code, SNAPSHOT, LEASE_TERMS)
    applied = Decimal(other["payments_applied"])
    assert abs(applied - Decimal(320453000)) < 1000
    # The interest added back is the same whoever deducted the payments.
    assert abs(Decimal(one["interest_added_back"]) - Decimal(other["interest_added_back"])) < 1000
    assert Decimal(other["adjustment"]) == Decimal(other["interest_added_back"]) - applied


def test_a_note_falling_due_is_repaid_by_code_only_when_the_case_leaves_it_untouched():
    untouched = _capital([("operations", 900000000)], borrowings=461630000)
    assert repaid_notes(untouched, OPENING, SNAPSHOT, TERMS) == (Decimal(312322000), ["2026 Convertible Notes"])
    for capital in (_capital([], borrowings=461630000),                                        # no operating cash
                    _capital([("operations", 1), ("debt", -312322000)], borrowings=461630000),  # repaid by the case
                    _capital([("operations", 1)], borrowings=149578000)):                       # already out of borrowings
        assert repaid_notes(capital, OPENING, SNAPSHOT, TERMS) == (Decimal(0), [])
    assert repaid_notes(untouched, None, SNAPSHOT, TERMS) == (Decimal(0), [])
    later = {**TERMS, "notes": [{**NOTE, "maturity_date": "2030-08-15"}]}
    assert repaid_notes(untouched, OPENING, SNAPSHOT, later) == (Decimal(0), [])


def test_the_statement_shows_both_code_steps_and_net_obligations_do_not_move_for_the_repayment():
    capital = _capital([("operations", 900000000)], borrowings=461630000)
    funded = funded_cash(capital, SNAPSHOT, TERMS)
    repaid, _ = repaid_notes(capital, OPENING, SNAPSHOT, TERMS)
    cash = capital.cash.value + Decimal(funded["adjustment"]) - repaid
    net = (capital.obligations["borrowings"].value - repaid) - cash
    without = capital.obligations["borrowings"].value - (capital.cash.value + Decimal(funded["adjustment"]))
    assert net == without
    settled = settle_convertibles(Decimal(8_000_000_000) - net, capital.closing_shares.value, [], Decimal(1))
    lines = [line[len(STATEMENT):] for line in funded_statement(
        capital, SNAPSHOT, {"cash": Decimal(1), "closing_shares": Decimal(120), "borrowings": OPENING},
        funded, {}, settled, "borrowings_only", Decimal(8_000_000_000), net, TERMS, repaid=repaid)]
    assert ("code: scheduled finance and equipment payments deducted -320.4M USD; notes falling due repaid "
            "-312.3M USD") in lines[1]
    assert "code: notes falling due repaid -312.3M USD; closing 149.3M USD." in lines[2]
    assert lines[-1] == "nothing the filing schedules inside the period is left unstated by the case."


def test_the_case_value_moves_by_exactly_the_payments_code_deducts(monkeypatch):
    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state
    from tradingagents.agents import shared_valuation
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    def price():
        record = prepare_shared_valuation(state([revenue_case()]))      # states operations of -20 and nothing else
        assert record["status"] == "available", record["reasons"]
        return record["rows"][0]

    before = price()
    snapshot = date.fromisoformat(before["result"]["capital_snapshot_date"])
    monkeypatch.setattr(shared_valuation, "_funding_terms", lambda value: {
        "schedule": {"as_of": snapshot, "years": {str(year): Decimal(11) for year in range(snapshot.year, 2028)}},
        "schedule_totals": {}, "notes": [], "leases": []})
    after = price()
    applied = Decimal(after["funding"]["funded"]["payments_applied"])
    assert applied > 0 and after["funding"]["status"] == "assessed"
    assert abs((Decimal(before["result"]["target"]) - Decimal(after["result"]["target"])) * 110 - applied) < Decimal("1e-20")
    assert any("scheduled finance and equipment payments deducted" in a for a in after["result"]["assumptions"])


# --- the one request for an empty bridge ---

def _request_setup():
    import json as _json
    from types import SimpleNamespace

    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state

    class Model:
        def __init__(self, reply=None, error=None):
            self.reply, self.error, self.prompts = reply, error, []

        def invoke(self, prompt):
            self.prompts.append(prompt)
            if self.error:
                raise self.error
            return SimpleNamespace(content=self.reply)

    def fenced(rows):
        return "```valuation_scenarios\n" + _json.dumps(rows) + "\n```"

    def completed(row=None):
        row = row or revenue_case()
        capital = row["request"]["capital"]
        capital["cash_changes"] = [{"source": "operations", "amount": "40", "reason": "Operating cash flow."},
                                   {"source": "capex", "amount": "-25", "reason": "Capital spending."}]
        capital["cash"]["value"] = "115"              # snapshot 100 plus the two changes
        capital["operations_after_lease_interest"] = True
        capital["operations_include_new_lease_rent"] = False
        return row

    return revenue_case, state, Model, fenced, completed


def test_a_priced_case_with_no_operating_cash_or_capex_is_asked_for_them_once_and_nothing_else_may_change():
    from tradingagents.agents.shared_valuation import (
        prepare_shared_valuation,
        prepare_with_correction,
    )
    revenue_case, state, Model, fenced, completed = _request_setup()
    inputs = state([revenue_case()])
    first = prepare_shared_valuation(inputs)
    model = Model(fenced([completed()]))
    record = prepare_with_correction(inputs, model, "SHAPE")
    assert len(model.prompts) == 1 and "state no operating cash flow or no capital spending" in model.prompts[0]
    assert "Base" in model.prompts[0] and "code deducts the filed payment schedule" in model.prompts[0]
    assert record["corrected_submission"]["kind"] == "cash_bridge" and len(record["rows"]) == 1
    sources = [c["source"] for c in record["rows"][0]["request"]["capital"]["cash_changes"]]
    assert sources == ["operations", "capex"] and record["rows"][0]["request"]["capital"]["cash"]["value"] == "115"
    assert record["reasons"][-1].startswith("Row 1: cash bridge stated by the analyst at code's request")
    # The completed case is what every later replay prices, with no second call.
    saved = {**inputs, "shared_valuation_scenarios": record}
    again = Model(fenced([completed()]))
    assert prepare_with_correction(saved, again, "SHAPE")["rows"] == record["rows"] and again.prompts == []
    assert prepare_shared_valuation(saved)["rows"][0]["result"]["target"] == record["rows"][0]["result"]["target"]
    assert record["rows"][0]["result"]["target"] != first["rows"][0]["result"]["target"]


def test_a_reply_that_changes_anything_outside_the_bridge_or_fails_leaves_the_cases_as_submitted():
    from tradingagents.agents.shared_valuation import (
        prepare_shared_valuation,
        prepare_with_correction,
    )
    revenue_case, state, Model, fenced, completed = _request_setup()
    inputs = state([revenue_case()])
    first = prepare_shared_valuation(inputs)
    richer = completed()
    richer["request"]["multiple"] = "4"                                   # not the analyst's to change here
    renamed = completed()
    renamed["name"] = "Base case"
    still_empty = revenue_case()
    unbalanced = completed()
    unbalanced["request"]["capital"]["cash"]["value"] = "500"             # does not sum: fails validation
    for reply in (fenced([richer]), fenced([renamed]), fenced([still_empty]), fenced([unbalanced]),
                  fenced([completed(), completed()]), "I cannot do that.", "```valuation_scenarios\n[]\n```"):
        record = prepare_with_correction(inputs, Model(reply), "SHAPE")
        assert record["rows"] == first["rows"], reply[:60]
        assert "corrected_submission" not in record
        assert record["correction_attempt"]["outcome"].startswith("Cash bridge request: the analyst did not state")
    failed = prepare_with_correction(inputs, Model(error=RuntimeError("secret")), "SHAPE")
    assert failed["rows"] == first["rows"] and "RuntimeError" in failed["reasons"][-1] and "secret" not in str(failed)
    # The declined request is on record, so a replay does not ask again.
    saved = {**inputs, "shared_valuation_scenarios": record}
    quiet = Model(fenced([completed()]))
    prepare_with_correction(saved, quiet, "SHAPE")
    assert quiet.prompts == []


def test_a_rejected_submission_still_gets_the_validation_correction_not_the_bridge_request():
    from tradingagents.agents.shared_valuation import prepare_with_correction
    revenue_case, state, Model, fenced, completed = _request_setup()
    bad = revenue_case()
    bad["request"]["capital"]["cash"]["assumption"] = "guess"
    inputs = state([bad])
    model = Model(fenced([revenue_case()]))
    record = prepare_with_correction(inputs, model, "SHAPE")
    assert len(model.prompts) == 1 and model.prompts[0].startswith("Validation rejected the valuation_scenarios block")
    assert record["corrected_submission"].get("kind") is None
