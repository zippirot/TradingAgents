
"""Compact sensitivity views preserve exact original cells and source distinctions."""
from copy import deepcopy
from decimal import Decimal

from tests.test_mechanical_valuation import prepared
from tradingagents.agents import mechanical_valuation as grid, valuation_reference_flow as flow


def test_compact_views_reduce_rows_without_mutating_exact_cells(monkeypatch):
    state, _ = prepared(monkeypatch)
    record = grid.mechanical_valuation_grid(state)
    before = deepcopy(record)
    compact = grid.compact_mechanical_valuation_grid(record)
    groups = compact["blocks"]["management"]["reference_groups"]
    history = next(g for g in groups if g["group"] == "own_history")
    assert len(history["rows"]) == 2
    guidance = history["rows"][0]
    assert guidance["label"] == "management guidance range"
    assert guidance["revenue_range"] == ["1208000000", "1211000000"]
    reported = guidance["reported_shares"]
    assert list(map(Decimal, reported["price_range"])) == [Decimal("24.16"), Decimal("72.66")]
    assert list(map(Decimal, reported["median_price_range"])) == [Decimal("48.32"), Decimal("48.44")]
    assert guidance["guided_shares"]["shares_range"] == ["128000000", "129000000"]
    assert record == before
    assert len(record["blocks"]["management"]["rows"]) == 36


def test_history_median_positions_use_unrounded_numbers_and_independent_share_bases(monkeypatch):
    state, _ = prepared(monkeypatch)
    record = grid.mechanical_valuation_grid(state)
    result = grid.history_median_position(record)
    rows = result["rows"]
    assert len(rows) == 4
    row = next(r for r in rows if r["view_id"] == "management-guidance" and r["share_basis"] == "outstanding")
    assert row["position"] == "below"
    assert row["price_interval"] == ["48.32", "48.44"]
    assert row["share_date"] == "2026-09-30"
    assert not row["decision_comparable"]
    text = grid.render_history_median_position(result)
    assert len(text) <= 2500
    assert "below" in text and "2027" in text and "conditional" in text.lower()
    assert "- Management guidance, full year 2026; reported shares as of 2026-09-30:" in text
    assert "guided diluted weighted-average shares for fourth quarter ending December 31, 2026" in text
    assert "the close is below the history-median sensitivity of" in text
    assert "management-guidance/" not in text and "@" not in text
    assert "fair value" not in text.lower()
    original_rows = record["blocks"]["management"]["rows"]
    for position, low, high, close in [
        ("above", "20", "30", "30.00000000001"),
        ("within", "20", "30", "25"),
        ("equal", "25", "25", "25"),
        ("below", "20", "30", "19.99999999999"),
    ]:
        changed = deepcopy(record)
        changed["price"]["close"] = close
        for r in changed["blocks"]["management"]["rows"]:
            if r["reference"]["name"] == "median":
                r["conditional_price"] = low if r["outlook"]["label"] == "guidance low" else high
        result = grid.history_median_position(changed)
        assert next(r for r in result["rows"] if r["view_id"] == "management-guidance")["position"] == position
    assert record["blocks"]["management"]["rows"] == original_rows


def test_vendor_periods_and_small_peer_sets_remain_separate(monkeypatch):
    state, _ = prepared(monkeypatch)
    monkeypatch.setattr(flow, "validate_vendor_expectations", lambda state: {
        "status": "available", "estimates": [{"metric": "revenue", "period_code": period,
            "currency": "USD", "unit": "USD", "average": "2000000000",
            "low": "1900000000", "high": "2100000000"} for period in ("0y", "+1y")]})
    record = grid.mechanical_valuation_grid(state)
    compact = grid.compact_mechanical_valuation_grid(record)
    peer_groups = [g for g in compact["blocks"]["management"]["reference_groups"] if g["group"] == "peers"]
    assert [g["name"] for g in peer_groups] == ["AKAM"]
    vendor = compact["blocks"]["vendor"]
    assert vendor["label"] == "vendor consensus, unverified"
    history = next(g for g in vendor["reference_groups"] if g["group"] == "own_history")
    assert len(history["rows"]) == 2
    assert all(r["period_start"] is None and r["period_end"] is None for r in history["rows"])
    summary = grid.history_median_position(record)
    assert len(summary["rows"]) == 8
    rendered = grid.render_history_median_position(summary)
    assert len(rendered) <= 2500
    assert "- Vendor consensus, unverified; next fiscal year (+1y), dates unverified" in rendered


def test_missing_share_basis_and_history_do_not_invent_summary(monkeypatch):
    state, _ = prepared(monkeypatch)
    record = grid.mechanical_valuation_grid(state)
    for block in record["blocks"].values():
        block["rows"] = [r for r in block["rows"] if r["shares"]["kind"] != "guided diluted weighted average"]
    result = grid.compact_mechanical_valuation_grid(record)
    assert all(r["guided_shares"] is None for g in result["blocks"]["management"]["reference_groups"] for r in g["rows"])
    assert len(grid.history_median_position(record)["rows"]) == 2
    for block in record["blocks"].values():
        block["rows"] = [r for r in block["rows"] if r["reference"]["group"] != "own_history"]
    summary = grid.history_median_position(record)
    assert summary["status"] == "unavailable"
    assert not summary["rows"]
    assert grid.compact_mechanical_valuation_grid({"status": "not_applicable", "blocks": {}})["status"] == "not_applicable"
    assert grid.render_mechanical_valuation_grid({"status": "not_applicable"}) == ""




def test_median_is_not_invented_from_other_reference_points(monkeypatch):
    state, _ = prepared(monkeypatch)
    record = grid.mechanical_valuation_grid(state)
    for block in record["blocks"].values():
        block["rows"] = [row for row in block["rows"] if row["reference"]["name"] != "median"]
    compact = grid.compact_mechanical_valuation_grid(record)
    history = next(group for group in compact["blocks"]["management"]["reference_groups"] if group["group"] == "own_history")
    assert history["rows"][0]["reported_shares"]["price_range"]
    assert history["rows"][0]["reported_shares"]["median_price_range"] is None
    assert grid.history_median_position(record)["status"] == "unavailable"



def test_intervals_and_summary_do_not_depend_on_numeric_cell_order(monkeypatch):
    state, _ = prepared(monkeypatch)
    record = grid.mechanical_valuation_grid(state)
    before = grid.history_median_position(record)
    expected = [(row["view_id"], row["share_basis"], row["price_interval"], row["position"])
                for row in before["rows"]]
    reordered = deepcopy(record)
    for block in reordered["blocks"].values():
        block["rows"].reverse()
    summary = grid.history_median_position(reordered)
    assert [(row["view_id"], row["share_basis"], row["price_interval"], row["position"])
            for row in summary["rows"]] == expected
    assert grid.render_mechanical_valuation_grid(reordered) == grid.render_mechanical_valuation_grid(record)
