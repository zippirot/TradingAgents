"""Public filing facts with illustrative FY2027 assumptions. No saved model output."""
from copy import deepcopy
from decimal import Decimal

import pytest

from tests.docn_workflow_fixture import source_state
from tests.test_case_valuation import bridge, revenue_case, value
from tradingagents.agents.shared_valuation import (
    SCOPE,
    prepare_shared_valuation,
    render_shared_valuation,
)
from tradingagents.agents.valuation_cases import RevenueCase, price_case
from tradingagents.dataflows.financial_evidence import EvidencePackage


def example():
    state = source_state()
    state["evidence_quality"] = {"status": "limited", "scope": SCOPE}
    facts = state["financial_evidence"]["facts"]

    def fact_id(metric, end):
        return next(f["fact_id"] for f in facts if f["metric"] == metric and f["period_end"] == end
                    and (metric != "Revenue" or f["period_start"] == "2025-01-01"))

    submitted = revenue_case()
    request = submitted["request"]
    request.update(revenue_fact_id=fact_id("Revenue", "2025-12-31"), multiple="7.5",
                   multiple_assumption_date=state["trade_date"])
    request["forecast"]["value"] = "1300000000"
    capital = request["capital"]
    capital["cash"] = value(650000000, fact_id("Cash and Equivalents", "2026-09-30"))
    capital["closing_shares"] = value(128000000, fact_id("Common Shares Outstanding", "2026-09-30"))
    capital["obligations"] = {"borrowings": value(450000000, fact_id("Total Borrowings", "2026-09-30"))}
    snapshot = {f["metric"]: Decimal(str(f["value"])) for f in facts if f["period_end"] == "2026-09-30" and f["period_start"] is None}
    bridge(request, snapshot["Common Shares Outstanding"], snapshot["Cash and Equivalents"])
    return state, [submitted]


def test_borrowings_only_submission_missing_lease_inputs_preserves_original_request_and_target():
    state, submitted = example()
    original = deepcopy(submitted)
    package = EvidencePackage.model_validate(state["financial_evidence"])
    request = RevenueCase.model_validate(original[0]["request"])
    base, sensitivities = price_case(request, package, ())
    assert base.target == Decimal("77.734375") and sensitivities == {}
    record = prepare_shared_valuation(state, submitted)
    row, = record["rows"]
    assert submitted == original == record["requests"]
    assert row["request"] == request.model_dump(mode="json")
    # The row's statement also shows the filed lease balances the case left out; nothing else differs.
    shown = [a for a in row["result"]["assumptions"] if "analyst: not stated in this case" not in a]
    assert len(shown) < len(row["result"]["assumptions"])
    assert {**row["result"], "assumptions": shown} == base.model_dump(mode="json")
    for basis in ("finance_equipment", "all_leases"):
        supplemental = RevenueCase.model_validate(row["source_bound_sensitivity_requests"][basis])
        recalculated, _ = price_case(supplemental, package, ())
        assert recalculated.target == Decimal(row["sensitivities"][basis])
        assert supplemental.capital.obligations["borrowings"] == request.capital.obligations["borrowings"]
        for category, item in supplemental.capital.obligations.items():
            if category != "borrowings":
                assert item.assumption == "unchanged_from_snapshot"


def test_docn_case_renders_finance_equipment_and_all_leases_sensitivities():
    record = prepare_shared_valuation(*example())
    row, = record["rows"]
    prices = row["sensitivities"]
    assert Decimal(prices["all_leases"]) < Decimal(prices["finance_equipment"]) < Decimal(row["result"]["target"])
    expected = {"finance_equipment": "70.52", "all_leases": "65.31"}
    lines = render_shared_valuation(record).splitlines()
    for basis, display in expected.items():
        assert any("Sensitivity only" in line and basis in line and display in line for line in lines)


def test_sensitivity_states_obligation_date_assumption():
    record = prepare_shared_valuation(*example())
    for basis in ("finance_equipment", "all_leases"):
        line = next(line for line in render_shared_valuation(record).splitlines()
                    if "Sensitivity only" in line and basis in line)
        assert all(text in line for text in ("2026-09-30", "2027-12-31", "held constant", "no growth or repayment"))


@pytest.mark.parametrize("change", ["missing", "conflicting", "currency", "date", "basis"])
def test_incompatible_operating_lease_withholds_only_all_leases(change):
    state, requests = example()
    facts = state["financial_evidence"]["facts"]
    current = next(f for f in facts if f["metric"] == "Current Operating Lease Liabilities"
                   and f["period_end"] == "2026-09-30")
    # Exercise component fallback without an independent filed total. For a
    # contradictory component, also retain the total to prove conflict is visible.
    if change != "conflicting":
        facts[:] = [f for f in facts if not (f["metric"] == "Operating Lease Liabilities"
                                             and f["period_end"] == "2026-09-30")]
    if change == "missing":
        facts.remove(current)
    elif change == "conflicting":
        facts.append(dict(current, fact_id="conflicting-current-lease", value="1"))
    else:
        current.update({"currency": {"unit": "EUR"}, "date": {"period_end": "2026-09-29"},
                        "basis": {"basis": "non-GAAP"}}[change])
    row, = prepare_shared_valuation(state, requests)["rows"]
    assert "finance_equipment" in row["sensitivities"] and "all_leases" not in row["sensitivities"]


def test_finance_equipment_base_preserves_submitted_separate_categories():
    state, submitted = example()
    request = submitted[0]["request"]
    request["multiple_basis"] = "finance_equipment"
    obligations = request["capital"]["obligations"]
    for category, metric in (("finance_leases", "Finance Lease Liabilities"),
                             ("equipment", "Equipment Financing Obligations")):
        fact = next(f for f in state["financial_evidence"]["facts"]
                    if f["metric"] == metric and f["period_end"] == "2026-09-30")
        obligations[category] = value(100000000, fact["fact_id"])
    row, = prepare_shared_valuation(state, submitted)["rows"]
    assert row["result"]["target"] == "76.171875"
    augmented = row["source_bound_sensitivity_requests"]["all_leases"]["capital"]["obligations"]
    assert augmented.keys() == obligations.keys() | {"operating_leases"}
    assert all(augmented[k] == obligations[k] for k in obligations)
