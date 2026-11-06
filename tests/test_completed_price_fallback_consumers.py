"""A missing latest close remains dated throughout source and peer contexts."""
from copy import deepcopy

import pytest

from tests.test_valuation_reference_flow import flow_fixture


def fallback_quote(quote):
    from tradingagents.dataflows.vendors.yahoo.price_observation import _project
    raw = deepcopy(quote["raw_source"])
    previous = {**raw["bars"][-1], "timestamp": "2026-10-16T00:00:00-04:00", "close": "19"}
    raw["bars"].insert(-1, previous)
    raw["bars"][-1]["close"] = None
    return _project(raw)


def test_canonical_brief_and_price_implied_show_fallback_reason(monkeypatch):
    from tradingagents.agents.context import build_shared_source_brief
    from tradingagents.agents.valuation_comparison import (
        price_implied_valuation,
        render_price_implied_valuation,
    )
    state, _, _, _ = flow_fixture(monkeypatch)
    state["price_observation"] = fallback_quote(state["price_observation"])
    text = build_shared_source_brief(state)
    assert "2026-10-16" in text and "2026-10-19" in text
    assert "Latest completed session has no close" in text
    record = price_implied_valuation(state)
    assert record["status"] == "available", record
    assert record["price"]["price_fallback"] == state["price_observation"]["price_fallback"]
    assert "Latest completed session has no close" in render_price_implied_valuation(record)


def test_earlier_peer_fallback_is_visible_diagnostic_and_not_same_session_range(monkeypatch):
    from tradingagents.agents import valuation_reference_flow as flow
    state, config, _, quotes = flow_fixture(monkeypatch)
    quotes["AKAM"] = fallback_quote(quotes["AKAM"])
    monkeypatch.setattr(flow, "default_peer_selection", lambda *a: {
        "kind": "previous", "status": "available", "reason": None,
        "peers": [{"ticker": "AKAM", "reason": "Cloud comparison"}]})
    record = flow.acquire_reference_inputs(state, config)["valuation_reference"]
    peers = record["peers"]
    assert peers["accepted"] == []
    assert peers["range"]["status"] == "unavailable"
    diagnostic = peers["dated_price_diagnostics"][0]["statistics"]
    assert diagnostic["price_session"] == "2026-10-16"
    assert diagnostic["multiple"] is not None
    assert diagnostic["price_fallback"]["latest_completed_session_date"] == "2026-10-19"
    brief = flow.render_valuation_reference(record)
    assert "2026-10-16" in brief and "Latest completed session has no close" in brief
    assert "excluded from the same-session peer range" in brief
    assert diagnostic["revenue_fact"]["period_start"] in brief
    assert diagnostic["revenue_fact"]["period_end"] in brief
    assert diagnostic["revenue_definition"] in brief
    assert flow.replay_valuation_reference(state, record) == record
    tampered = deepcopy(record)
    tampered["peers"]["dated_price_diagnostics"][0]["statistics"]["multiple"] = "999"
    with pytest.raises(ValueError):
        flow.replay_valuation_reference(state, tampered)


def test_subject_and_peer_with_same_fallback_session_remain_comparable(monkeypatch):
    from tradingagents.agents import valuation_reference_flow as flow
    state, config, _, quotes = flow_fixture(monkeypatch)
    state["price_observation"] = fallback_quote(quotes["DOCN"])
    quotes["AKAM"] = fallback_quote(quotes["AKAM"])
    monkeypatch.setattr(flow, "default_peer_selection", lambda *a: {
        "kind": "previous", "status": "available", "reason": None,
        "peers": [{"ticker": "AKAM", "reason": "Cloud comparison"}]})
    prepared = flow.acquire_reference_inputs(state, config)
    peers = prepared["valuation_reference"]["peers"]
    assert len(peers["accepted"]) == 1
    assert peers["accepted"][0]["statistics"]["price_session"] == "2026-10-16"
    assert "Latest completed session has no close" in prepared["valuation_reference_brief"]
