
"""Mechanical arithmetic is source-only and preserves separate horizons/bases."""
from copy import deepcopy
from decimal import Decimal

import pytest

from tests.test_price_implied_guidance_ranges import source_state
from tradingagents.agents import mechanical_valuation as grid, valuation_reference_flow as flow


def prepared(monkeypatch):
    state = source_state(monkeypatch)
    state["valuation_reference"] = {"fixture": "retained canonical boundary"}
    reference = {
        "own_history": {"status": "available", "statistics": {
            "low": "2", "median": "4", "high": "6", "count": 8}},
        "peers": {"accepted": [{"ticker": "AKAM", "statistics": {
            "status": "available", "multiple": "3", "share_date": "2026-09-30"}}],
            "range": {"status": "unavailable"}},
    }
    monkeypatch.setattr(flow, "replay_valuation_reference", lambda state, saved: deepcopy(reference))
    monkeypatch.setattr(flow, "validate_vendor_expectations", lambda state: {
        "status": "unavailable", "reason": "No retained estimates"})
    return state, reference


def test_equity_price_without_debt_and_growth_floor_only_one_outlook(monkeypatch):
    state, _ = prepared(monkeypatch)
    before = deepcopy(state)
    state["target_validation"] = {"target": "999999"}
    state["shared_valuation_scenarios"] = {"model": "ignored"}
    result = grid.mechanical_valuation_grid(state)
    assert result["status"] == "available", result
    rows = result["blocks"]["management"]["rows"]
    row = next(r for r in rows if r["outlook"]["label"] == "guidance low"
               and r["reference"]["name"] == "low"
               and r["reference"]["group"] == "own_history"
               and r["shares"]["kind"] == "outstanding")
    assert Decimal(row["conditional_price"]) == Decimal("24.16")
    assert Decimal(row["price_change_percent"]) == Decimal("20.8")
    assert row["basis"] == "equity value / revenue"
    assert row["shares"]["date"] == "2026-09-30"
    outlooks = result["blocks"]["management"]["outlooks"]
    floor = [r for r in outlooks if r["label"] == "at the guidance floor"]
    assert len(floor) == 1
    assert floor[0]["revenue"] == "1932800000"
    assert floor[0]["base_revenue"] == "1208000000"
    assert floor[0]["base_period"] == "full year 2026"
    assert floor[0]["period"] == "2027"
    assert "not a lower bound" in floor[0]["qualification"]
    assert all(r["reference"]["name"] == "AKAM" for r in rows
               if r["reference"]["group"] == "peers")
    assert all(not r["decision_comparable"] for r in rows)
    state.pop("target_validation")
    state.pop("shared_valuation_scenarios")
    assert state == before


def test_guided_weighted_average_period_is_distinct_from_outstanding(monkeypatch):
    state, _ = prepared(monkeypatch)
    result = grid.mechanical_valuation_grid(state)
    rows = result["blocks"]["management"]["rows"]
    guided = [r for r in rows if r["shares"]["kind"] == "guided diluted weighted average"]
    assert {r["shares"]["value"] for r in guided} == {"128000000", "129000000"}
    assert all(r["shares"]["date"] is None and
               r["shares"]["period"] == "fourth quarter ending December 31, 2026" for r in guided)
    assert all(any("period" in why for why in r["comparability_reasons"]) for r in guided)
    text = grid.render_mechanical_valuation_grid(result)
    assert "not a forecast" in text
    assert "not a forecast year-end count" in text
    assert "price changes" in text and "not annualized" in text
    assert "2027" in text and "source_id" in text


def test_vendor_next_fiscal_year_is_separate_unverified_dates(monkeypatch):
    state, _ = prepared(monkeypatch)
    monkeypatch.setattr(flow, "validate_vendor_expectations", lambda state: {
        "status": "available", "snapshot_hash": "a" * 64, "retrieved_at": "2026-11-04T22:00:00+00:00",
        "vendor_as_of": None, "estimates": [
            {"metric": "revenue", "period_code": "+1y", "period_start": None, "period_end": None,
             "currency": "USD", "unit": "USD", "basis": None,
             "low": "2000000000", "average": "2100000000", "high": "2200000000"}]})
    result = grid.mechanical_valuation_grid(state)
    vendor = result["blocks"]["vendor"]
    assert vendor["status"] == "available"
    assert vendor["label"] == "vendor consensus, unverified"
    assert {r["outlook"]["label"] for r in vendor["rows"]} == {
        "vendor low", "vendor average", "vendor high"}
    assert all(r["outlook"]["period"] == "vendor next fiscal year (+1y), dates unverified"
               and r["outlook"]["period_start"] is None
               and r["outlook"]["period_end"] is None for r in vendor["rows"])
    assert all(not r["decision_comparable"] for r in vendor["rows"])
    assert all(r["outlook"]["kind"] != "vendor" for r in result["blocks"]["management"]["rows"])


def test_unknown_vendor_currency_or_unit_cannot_generate_price(monkeypatch):
    state, _ = prepared(monkeypatch)
    for currency, unit in [(None, "USD"), ("EUR", "USD"), ("USD", None), ("USD", "millions")]:
        monkeypatch.setattr(flow, "validate_vendor_expectations", lambda state, currency=currency, unit=unit: {
            "status": "available", "estimates": [{"metric": "revenue", "period_code": "+1y",
             "currency": currency, "unit": unit, "low": "200", "average": "220", "high": "240"}]})
        vendor = grid.mechanical_valuation_grid(state)["blocks"]["vendor"]
        assert not vendor["rows"]
        assert vendor["status"] == "unavailable"


def test_large_peer_set_uses_separate_range_and_missing_blocks_are_independent(monkeypatch):
    state, reference = prepared(monkeypatch)
    reference["peers"]["accepted"] *= 3
    reference["peers"]["range"] = {"status": "available", "statistics": {"low": "3", "median": "5", "high": "7"}}
    result = grid.mechanical_valuation_grid(state)
    refs = result["reference_blocks"]
    assert {r["name"] for r in refs["peers"]["rows"]} == {"low", "median", "high"}
    reference["own_history"] = {"status": "unavailable", "reason": "Insufficient history"}
    result = grid.mechanical_valuation_grid(state)
    assert result["blocks"]["management"]["rows"]
    assert all(r["reference"]["group"] == "peers" for r in result["blocks"]["management"]["rows"])


def test_canonical_replay_failure_and_asset_scope_do_not_publish_numbers(monkeypatch):
    state, _ = prepared(monkeypatch)
    monkeypatch.setattr(flow, "replay_valuation_reference", lambda *a: (_ for _ in ()).throw(ValueError("tampered reference")))
    result = grid.mechanical_valuation_grid(state)
    assert result["status"] == "unavailable"
    assert not result["blocks"]["management"]["rows"]
    state["asset_type"] = "crypto"
    assert grid.mechanical_valuation_grid(state)["status"] == "not_applicable"



def test_real_canonical_reference_vendor_replay_and_projection_tamper(monkeypatch):
    from tests.test_valuation_reference_flow import flow_fixture
    from tradingagents.dataflows.vendors.yahoo.expectations import VendorExpectations, _hash

    state, config, _, _ = flow_fixture(monkeypatch)
    monkeypatch.setattr(flow, "default_peer_selection", lambda *a: {
        "kind": "previous", "status": "available", "reason": None,
        "peers": [{"ticker": "AKAM", "reason": "Cloud comparison"}]})
    state.update(flow.acquire_reference_inputs(state, config))
    vendor = VendorExpectations(status="available", ticker="DOCN", requested_as_of=state["trade_date"],
        retrieved_at="2026-10-19T22:00:00+00:00", estimates=[{
            "metric": "revenue", "period_code": "+1y", "currency": "USD", "unit": "USD",
            "low": 1000000, "average": 1100000, "high": 1200000}])
    vendor.snapshot_hash = _hash(vendor)
    state["vendor_expectations"] = vendor.model_dump(mode="json")
    before = deepcopy(state)
    result = grid.mechanical_valuation_grid(state)
    assert result["status"] == "available", result
    assert result["blocks"]["vendor"]["rows"]
    assert not result["blocks"]["management"]["rows"]
    assert grid.validate_mechanical_valuation_grid(state, result) == result
    changed = deepcopy(result)
    changed["blocks"]["vendor"]["rows"][0]["conditional_price"] = "9999"
    with pytest.raises(ValueError):
        grid.validate_mechanical_valuation_grid(state, changed)
    assert state == before
    state["valuation_reference"]["own_history"]["statistics"]["low"] = "9999"
    assert grid.mechanical_valuation_grid(state)["status"] == "unavailable"
    state = deepcopy(before)
    state["vendor_expectations"]["estimates"][0]["average"] = "9999"
    assert not grid.mechanical_valuation_grid(state)["blocks"]["vendor"]["rows"]


def test_malformed_vendor_does_not_hide_management_and_input_lineage_is_revalidated(monkeypatch):
    state, _ = prepared(monkeypatch)
    monkeypatch.setattr(flow, "validate_vendor_expectations", lambda state: {
        "status": "available", "estimates": [{"metric": "revenue", "period_code": "+1y",
            "currency": "USD", "unit": "USD", "average": "-1"}]})
    result = grid.mechanical_valuation_grid(state)
    assert result["blocks"]["management"]["rows"]
    assert not result["blocks"]["vendor"]["rows"]
    state["financial_evidence"]["facts"][-1]["value"] = "9999"
    assert grid.mechanical_valuation_grid(state)["status"] == "unavailable"



def test_renderer_has_distinct_history_and_peer_tables(monkeypatch):
    state, _ = prepared(monkeypatch)
    text = grid.render_mechanical_valuation_grid(grid.mechanical_valuation_grid(state))
    own = text.index("##### Own-history reference sensitivities")
    peer = text.index("##### Peer reference sensitivities")
    assert own < peer
    assert "AKAM" not in text[own:peer]
    assert "AKAM" in text[peer:]


def test_maximum_annual_vendor_grid_is_bounded_and_vendor_removal_leaves_management_exact(monkeypatch):
    state, reference = prepared(monkeypatch)
    reference["peers"]["accepted"] *= 3
    reference["peers"]["range"] = {"status": "available", "statistics": {
        "low": "3", "median": "5", "high": "7"}}
    estimates = [{"metric": "revenue", "period_code": period, "currency": "USD", "unit": "USD",
                  "low": "2000000000", "average": "2100000000", "high": "2200000000"}
                 for period in ("0y", "+1y")]
    monkeypatch.setattr(flow, "validate_vendor_expectations", lambda state: {
        "status": "available", "estimates": estimates})
    result = grid.mechanical_valuation_grid(state)
    assert sum(len(b["rows"]) for b in result["blocks"].values()) == grid.MAX_ROWS == 162
    management = deepcopy(result["blocks"]["management"])
    monkeypatch.setattr(flow, "validate_vendor_expectations", lambda state: {
        "status": "unavailable", "reason": "No consensus"})
    assert grid.mechanical_valuation_grid(state)["blocks"]["management"] == management
    state.pop("disclosure_evidence")
    result = grid.mechanical_valuation_grid(state)
    assert result["status"] == "unavailable"
    assert result["blocks"]["management"]["reason"] == "No source-bound management revenue outlook available."


def test_enterprise_reference_cannot_be_relabelled_equity(monkeypatch):
    state, reference = prepared(monkeypatch)
    reference["own_history"]["basis"] = "enterprise_value / trailing_revenue"
    result = grid.mechanical_valuation_grid(state)
    assert result["status"] == "unavailable"
    assert "basis" in result["reason"]



def test_duplicated_vendor_period_withholds_vendor_only(monkeypatch):
    state, _ = prepared(monkeypatch)
    estimate = {"metric": "revenue", "period_code": "+1y", "currency": "USD", "unit": "USD",
                "average": "2000000000"}
    monkeypatch.setattr(flow, "validate_vendor_expectations", lambda state: {
        "status": "available", "estimates": [estimate, estimate]})
    result = grid.mechanical_valuation_grid(state)
    assert result["blocks"]["management"]["rows"]
    assert not result["blocks"]["vendor"]["rows"]



def test_renderer_retains_each_numeric_cell_with_consistent_reference_columns(monkeypatch):
    from tradingagents.agents.valuation_comparison import display_number

    state, _ = prepared(monkeypatch)
    result = grid.mechanical_valuation_grid(state)
    text = grid.render_mechanical_valuation_grid(result)
    rows = result["blocks"]["management"]["rows"]
    assert text.count(" USD / ") == len(rows)
    for row in rows:
        cell = f"{display_number(row['conditional_price'])} USD / {display_number(row['price_change_percent'])}%"
        assert cell in text
    assert f"low: {display_number(2)}× equity value / revenue" in text
    assert f"AKAM: {display_number(3)}× equity value / revenue" in text
    expected_columns = None
    for line in text.splitlines():
        if " | " not in line:
            expected_columns = None
            continue
        count = len(line.split(" | "))
        if expected_columns is None:
            expected_columns = count
        assert count == expected_columns
    data_lines = [line for line in text.splitlines() if " USD / " in line]
    assert len(data_lines) == 18  # nine outlook/share bases per independent group
