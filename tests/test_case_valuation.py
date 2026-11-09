"""Explicit synthetic case assumptions. Historical runs never supply these values."""
from copy import deepcopy
from decimal import Decimal

from tests.test_shared_valuation import state
from tests.test_valuation import forecast
from tradingagents.agents.shared_valuation import prepare_shared_valuation


def value(amount, reference):
    return {"value": str(amount), "fact_ids": [reference], "assumption": "estimated",
            "reason": "Illustrative closing balance based on the dated filing."}


def bridge(request, shares=100, cash=100):
    """State what moved estimated closing shares and cash away from the snapshot."""
    capital = request["capital"]
    share_delta = Decimal(capital["closing_shares"]["value"]) - shares
    cash_delta = Decimal(capital["cash"]["value"]) - cash
    capital["share_changes"] = [{"source": "sbc", "shares": str(share_delta), "instrument": "RSUs",
                                 "reason": "Illustrative issuance."}] if share_delta else []
    capital["cash_changes"] = [{"source": "operations", "amount": str(cash_delta),
                                "reason": "Illustrative cash flow."}] if cash_delta else []
    return request


def revenue_case(basis="borrowings_only"):
    row = _unbridged_case(basis)
    bridge(row["request"])
    return row


def _unbridged_case(basis):
    return {"name": "Base", "request": {"method": "revenue_case", "revenue_fact_id": "revenue",
            "forecast": forecast(), "multiple": "3", "multiple_basis": basis, "multiple_period": "forward",
            "multiple_assumption_date": "2026-10-19", "multiple_rationale": "Assumed market pricing.",
            "capital": {"valuation_date": "2027-12-31", "currency": "USD",
                       "closing_shares": value(110, "shares"), "cash": value(80, "cash"),
                       "obligations": {"borrowings": value(160, "debt")}}}}


def test_case_revenue_a_thousand_times_off_is_unsupported():
    row = revenue_case()
    row["request"]["forecast"]["value"] = "1200000"
    record = prepare_shared_valuation(state([row]))
    assert record["status"] == "unavailable" and not record["rows"]
    assert "unit scale mismatch" in record["reasons"][0]


def test_price_on_own_basis_and_reject_missing_or_incompatible_inputs():
    for basis, expected in (("equity", Decimal(3600)), ("borrowings_only", Decimal(3520))):
        row = revenue_case(basis)
        record = prepare_shared_valuation(state([row]))
        assert record["status"] == "available", record["reasons"]
        assert abs(Decimal(record["rows"][0]["result"]["target"]) * 110 - expected) < Decimal("1e-20")
    for key in ("closing_shares", "valuation_date", "cash"):
        row = revenue_case()
        del row["request"]["capital"][key]
        assert not prepare_shared_valuation(state([row]))["rows"]
    row = revenue_case("finance_equipment")
    assert not prepare_shared_valuation(state([row]))["rows"]
    for update in ({"fact_ids": ["cash"]}, {"reason": " "}, {"assumption": "unchanged_from_snapshot"}):
        bad = deepcopy(revenue_case())
        bad["request"]["capital"]["closing_shares"].update(update)
        assert not prepare_shared_valuation(state([bad]))["rows"]


def test_exact_revision_selection_and_dated_horizon(monkeypatch):
    from tests.test_valuation_comparison import state as quoted
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )
    from tradingagents.agents.shared_valuation import replay_cases

    row = revenue_case()
    inputs = {**state([row]), **quoted(monkeypatch)}
    inputs.update(final_rating="Hold", unvalidated_outputs={"portfolio_manager": {
        "contract_version": "decision_horizon_v1", "structured": {"time_horizon": "3-6 months"}}})
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    revised = deepcopy(row)
    revised["request"]["multiple"] = "4"
    record = replay_cases(inputs, revision=[revised])
    inputs["shared_valuation_scenarios"] = record
    selected = {"method": "case", "case_id": record["rows"][0]["case_id"], "version": 2,
                "rerating_assumption": "none"}
    inputs["target_validation"] = {"request": selected}
    inputs["unvalidated_outputs"]["portfolio_manager"].update(case_contract=1, valuation_request=selected)
    card = prepare_decision_context(inputs)
    assert card["basis"] == "valuation", card["target"]
    assert "no dated assumption supplied" in render_decision_context(card)
    selected["version"] = 1
    assert prepare_decision_context(inputs)["basis"] == "risk assessment"
    selected.update(version=2, decision_date="2027-02-01", rerating_assumption="Early re-rating")
    assert prepare_decision_context(inputs)["basis"] == "risk assessment"  # estimated year-end capital postdates decision
    for v in [revised["request"]["capital"]["closing_shares"], revised["request"]["capital"]["cash"],
              revised["request"]["capital"]["obligations"]["borrowings"]]:
        v["assumption"] = "unchanged_from_snapshot"
    for v, amt in zip([revised["request"]["capital"]["closing_shares"], revised["request"]["capital"]["cash"],
                       revised["request"]["capital"]["obligations"]["borrowings"]], [100, 100, 200], strict=True):
        v["value"] = str(amt)
    bridge(revised["request"])
    record = replay_cases(inputs, revision=[revised])
    inputs["shared_valuation_scenarios"] = record
    card = prepare_decision_context(inputs)
    assert card["basis"] == "valuation"
    assert "assumption, not a forecast" in render_decision_context(card)
    selected["decision_date"] = "2027-05-01"
    assert "outside" in str(prepare_decision_context(inputs)["target"]["reasons"])


def test_compatible_card_group_only_sensitivities_excluded_and_no_early_rescue(monkeypatch):
    from tests.test_valuation_comparison import state as quoted
    from tradingagents.agents.decision_context import prepare_decision_context

    first = revenue_case()
    second = deepcopy(first)
    second["name"] = "High"
    second["request"]["multiple"] = "4"
    third = deepcopy(first)
    third["name"] = "Later"
    third["request"]["forecast"].update(period_start="2028-01-01", period_end="2028-12-31")
    third["request"]["capital"]["valuation_date"] = "2028-12-31"
    inputs = {**state([first, second, third]), **quoted(monkeypatch), "final_rating": "Hold",
              "unvalidated_outputs": {"portfolio_manager": {"structured": {"time_horizon": "6 months"}}}}
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    card = prepare_decision_context(inputs)
    assert card["basis"] == "risk assessment" and card["adopted_case"] is None
    assert len(card["case_groups"]) == 2
    assert [len(group["cases"]) for group in card["case_groups"]] == [2, 1]
    assert card["case_groups"][0]["close_position"] == "below"


def test_financing_sensitivity_only_for_accepted_authorization_and_incremental_shares(monkeypatch):
    from tests.test_issuer_events import release
    from tests.test_valuation_comparison import state as quoted
    from tradingagents.agents.issuer_events import financing_sensitivities

    inputs = quoted(monkeypatch)
    filing = release()
    filing["as_of"] = inputs["trade_date"]
    doc = filing["documents"][0]
    doc["filing"].update(filed_date="2026-10-15", report_date="2026-10-14")
    words = ("On October 14, 2026, the Company entered into an equity distribution agreement "
             "to sell shares of common stock having an aggregate offering price of up to $1.0 billion "
             "from time to time through an “at-the-market” offering program. "
             "All dollar amounts in this agreement are in U.S. dollars.")
    doc["blocks"] = [dict(doc["blocks"][0], text=words)]
    inputs["filing_evidence"] = filing
    result = financing_sensitivities(inputs)
    assert len(result) == 1, result
    assert Decimal(result[0]["conditional_shares"]) == 50000000
    assert result[0]["issuance"] is None and result[0]["remaining_capacity"] is None
    assert result[0]["fee_assumption_percent"] == "0"
    doc["blocks"][0]["text"] = words.replace("October 14", "June 30")
    assert "snapshot" in financing_sensitivities(inputs)[0]["reason"]
    doc["blocks"][0]["text"] = "A model guessed an offering."
    assert not financing_sensitivities(inputs)


def test_trailing_at_future_date_never_rendered_or_pooled_as_forward():
    from tradingagents.agents.decision_context import prepare_decision_context
    from tradingagents.agents.shared_valuation import render_shared_valuation

    forward = revenue_case()
    trailing = deepcopy(forward)
    trailing["name"] = "Year-end"
    trailing["request"]["multiple_period"] = "trailing"
    inputs = state([forward, trailing])
    record = prepare_shared_valuation(inputs)
    assert len(record["rows"]) == 2
    assert "trailing at the future valuation date" in render_shared_valuation(record)
    inputs.update(shared_valuation_scenarios=record, final_rating="Hold",
                  unvalidated_outputs={"portfolio_manager":{"structured":{"time_horizon":"6 months"}}})
    groups = prepare_decision_context(inputs)["case_groups"]
    assert len(groups) == 2 and all(len(g["cases"]) == 1 for g in groups)


def test_invalid_rm_revision_and_stale_cached_target_cannot_override_pm_selection():
    from tradingagents.agents.decision_context import prepare_decision_context
    from tradingagents.agents.output_validation import enforce_publication
    from tradingagents.agents.shared_valuation import render_shared_valuation, replay_cases

    inputs = state([revenue_case()])
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    bad = revenue_case()
    del bad["request"]["capital"]["cash"]
    record = replay_cases(inputs, revision=[bad])
    assert record["revision_status"] == "rejected" and "revision rejected" in render_shared_valuation(record)
    assert record["rows"][0]["version"] == 1
    valid = {"method":"case", "case_id":record["rows"][0]["case_id"], "version":1, "rerating_assumption":"none"}
    inputs.update(shared_valuation_scenarios=record, final_rating="Hold", target_validation={"request":valid},
                  unvalidated_outputs={"portfolio_manager":{"case_contract":1, "valuation_request":dict(valid, version=2),
                                                            "structured":{"time_horizon":"6 months"}}})
    assert prepare_decision_context(inputs)["basis"] == "risk assessment"
    assert enforce_publication(inputs)["target_validation"]["target"] is None


def test_legacy_forward_pe_arithmetic_cannot_bypass_dated_capital():
    from tests.test_valuation import pe_request
    from tradingagents.agents.decision_context import prepare_decision_context

    legacy = pe_request()
    legacy["forecast"] = {**forecast(), "value": "3", "unit": "USD/shares"}
    inputs = state([{"name": "Legacy forward EPS", "request": legacy}])
    record = prepare_shared_valuation(inputs)
    row = record["rows"][0]
    assert row["result"]["status"] == "supported" and row["diagnostic_only"]
    inputs.update(shared_valuation_scenarios=record, final_rating="Hold",
                  unvalidated_outputs={"portfolio_manager":{"structured":{"time_horizon":"6 months"}}},
                  target_validation={"request":{"method":"case", "case_id":row["case_id"], "version":1,
                                                "rerating_assumption":"none"}})
    inputs["unvalidated_outputs"]["portfolio_manager"].update(case_contract=1, valuation_request=inputs["target_validation"]["request"])
    card = prepare_decision_context(inputs)
    assert card["basis"] == "risk assessment" and not card["case_groups"]


def test_cached_case_selection_without_raw_pm_request_is_never_authority():
    from tradingagents.agents.decision_context import prepare_decision_context
    from tradingagents.agents.output_validation import enforce_publication

    inputs = state([revenue_case()])
    record = prepare_shared_valuation(inputs)
    cached = {"method": "case", "case_id": record["rows"][0]["case_id"], "version": 1,
              "rerating_assumption": "none"}
    inputs.update(shared_valuation_scenarios=record, final_rating="Hold", target_validation={"request": cached},
                  unvalidated_outputs={"portfolio_manager": {"structured": {"time_horizon": "6 months"}}})
    assert prepare_decision_context(inputs)["basis"] == "risk assessment"
    assert enforce_publication(inputs)["target_validation"]["target"] is None


def test_dated_link_requires_split_compatible_close_and_only_its_own_capital(monkeypatch):
    from tests.test_valuation_comparison import state as quoted
    from tradingagents.agents.decision_context import prepare_decision_context

    row = revenue_case()
    cap = row["request"]["capital"]
    for item, amount in ((cap["closing_shares"], "100"), (cap["cash"], "100"),
                         (cap["obligations"]["borrowings"], "200")):
        item.update(value=amount, assumption="unchanged_from_snapshot")
    bridge(row["request"])
    cap["obligations"].update(finance_leases=value(25, "finance"), equipment=value(12, "equipment"))
    inputs = {**state([row]), **quoted(monkeypatch, splits=(0, 2)), "final_rating": "Hold"}
    record = prepare_shared_valuation(inputs)
    selected = {"method": "case", "case_id": record["rows"][0]["case_id"], "version": 1,
                    "decision_date": "2027-02-01", "rerating_assumption": "Early rerating."}
    inputs.update(shared_valuation_scenarios=record, unvalidated_outputs={"portfolio_manager":{
        "case_contract": 1, "valuation_request": selected, "structured":{"time_horizon":"3-6 months"}}})
    rejected = prepare_decision_context(inputs)
    assert "split" in str(rejected["target"]["reasons"]).lower()
    inputs.update(quoted(monkeypatch))
    assert prepare_decision_context(inputs)["basis"] == "valuation"


def test_precontract_role_context_replays_raw_inputs_without_trusting_cached_rows():
    from tests.test_valuation import ev_request
    from tradingagents.agents.context import get_instrument_context_from_state
    from tradingagents.agents.shared_valuation import render_shared_valuation

    row = {"name": "Old case", "request": ev_request()}
    inputs = state([row])
    inputs["shared_valuation_scenarios"] = {
        "status": "available", "requests": [row], "rows": [{"name": "Old case", "result":{"target":"77777"}}]}
    assert "Legacy case projection unavailable" in render_shared_valuation(inputs["shared_valuation_scenarios"])
    inputs["instrument_context"] = "Offline context"
    delivered = get_instrument_context_from_state(inputs)
    assert "Legacy revenue case lacks" in delivered and "77777" not in delivered


def test_partial_off_basis_categories_only_block_incomplete_sensitivity():
    for basis in ("equity", "borrowings_only"):
        row = revenue_case(basis)
        row["request"]["capital"]["obligations"]["finance_leases"] = value(25, "finance")
        result = prepare_shared_valuation(state([row]))
        assert result["status"] == "available", result
        priced = result["rows"][0]
        assert "finance_equipment" not in priced["sensitivities"]
        assert any("equipment" in warning and "unknown" in warning for warning in priced["result"]["warnings"])
        row["request"]["capital"]["obligations"]["finance_leases"]["fact_ids"] = ["operating"]
        assert not prepare_shared_valuation(state([row]))["rows"]


def test_cached_analyst_input_cannot_reprice_existing_case_version():
    from tradingagents.agents.decision_context import prepare_decision_context
    from tradingagents.agents.output_validation import enforce_publication

    row = revenue_case()
    inputs = state([row])
    record = prepare_shared_valuation(inputs)
    original = record["rows"][0]["result"]["target"]
    record["requests"][0]["request"]["multiple"] = "30"
    inputs.update(shared_valuation_scenarios=record, final_rating="Hold", unvalidated_outputs={"portfolio_manager":{
        "case_contract": 1, "valuation_request": {"method":"case", "case_id":record["rows"][0]["case_id"],
                                                  "version":1, "rerating_assumption":"none"},
        "structured":{"time_horizon":"6 months"}}})
    assert prepare_decision_context(inputs)["adopted_case"]["value"] == original
    assert enforce_publication(inputs)["target_validation"]["target"] == original
    del inputs["financial_claim_validation"]["raw_report"]
    assert prepare_decision_context(inputs)["adopted_case"] is None
