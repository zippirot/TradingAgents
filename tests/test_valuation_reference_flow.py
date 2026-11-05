"""Reference acquisition honors user intent and retains cutoff-bound inputs."""
import json
from datetime import UTC, datetime

import pytest

from tradingagents.agents.valuation_reference_flow import (
    default_peer_selection,
    parse_peer_proposal,
)

FENCE = chr(96) * 3


def block(body):
    return FENCE + "peers\n" + body + "\n" + FENCE


def test_peer_proposals_are_bounded_named_json_blocks():
    result = parse_peer_proposal(block('[{"ticker":"AKAM","reason":"Cloud infrastructure"}]'), "DOCN")
    assert result["status"] == "available"
    assert result["peers"] == [{"ticker": "AKAM", "reason": "Cloud infrastructure"}]
    assert parse_peer_proposal(block("[]"), "DOCN")["status"] == "available"


@pytest.mark.parametrize("body", [
    '[{"ticker":"DOCN","reason":"Self"}]',
    '[{"ticker":"AKAM","reason":"A"},{"ticker":"AKAM","reason":"B"}]',
    '[{"ticker":true,"reason":"Invalid"}]',
    '[{"ticker":"AKAM","reason":""}]',
    '[NaN]',
])
def test_invalid_proposals_do_not_create_peer_facts(body):
    result = parse_peer_proposal(block(body), "DOCN")
    assert result["status"] == "unavailable"
    assert result["peers"] == []


def test_user_empty_pin_is_authoritative_and_does_not_read_publications(tmp_path, monkeypatch):
    from tradingagents.memory import publication
    path = tmp_path / "peers.json"
    path.write_text(json.dumps({"DOCN": []}))
    monkeypatch.setattr(publication, "list_records", lambda *args: pytest.fail("pins must precede publication lookup"))
    selection = default_peer_selection({"company_of_interest": "DOCN"}, {"valuation_peers_file": str(path)})
    assert selection["kind"] == "user-pinned"
    assert selection["peers"] == []


def test_previous_peer_set_is_latest_published_before_cutoff(monkeypatch):
    from tradingagents.memory import publication
    records = [
        {"published_at": "2026-11-04T20:00:00+00:00", "sequence": 1, "decision_id": "earlier"},
        {"published_at": "2026-11-05T22:00:00+00:00", "sequence": 2, "decision_id": "future"},
    ]
    monkeypatch.setattr(publication, "list_records", lambda *args: records)
    monkeypatch.setattr(publication, "load_evidence", lambda _, record: {
        "valuation_reference": {"peers": {"accepted": [
            {"ticker": "AKAM" if record["decision_id"] == "earlier" else "MSFT", "reason": "Prior comparison"}
        ]}}
    })
    result = default_peer_selection({
        "company_of_interest": "DOCN",
        "market_observation_cutoff": datetime(2026, 11, 5, 21, tzinfo=UTC).isoformat(),
        "run_id": "current",
    }, {"results_dir": "/isolated/results"})
    assert result["peers"] == [{"ticker": "AKAM", "reason": "Prior comparison"}]
    assert result["publication_id"] == "earlier"


def flow_fixture(monkeypatch):
    import pandas as pd

    from tests.test_price_observation import install
    from tests.test_valuation_reference import fixture
    from tradingagents.dataflows.vendors import sec_edgar
    from tradingagents.dataflows.vendors.yahoo import (
        expectations,
        price_observation,
        reference_history,
    )
    package, identity = fixture()
    quotes = {}
    for ticker in ("DOCN", "AKAM", "MSFT"):
        install(monkeypatch, now="2026-10-19T22:00:00+00:00",
                dates=("2026-09-30", "2026-10-19"), closes=(18, 20),
                metadata={"symbol": ticker, "currentTradingPeriod": {"regular": {
                    "end": datetime(2026, 10, 19, 21, tzinfo=UTC)}}})
        quotes[ticker] = price_observation.get_price_observation(ticker, "2026-10-19", "2026-09-30")
    calls = []
    def history(ticker, as_of, ends, **kwargs):
        calls.append(("history", ticker))
        raw = {
            "ticker": ticker, "as_of": as_of, "quarter_ends": ends,
            "retrieved_at": "2026-10-19T22:00:00+00:00",
            "observation_cutoff": kwargs.get("observation_cutoff"),
            "history_start": str(pd.Timestamp(min(ends)).date() - __import__("datetime").timedelta(days=7)),
            "history_end_exclusive": "2026-10-20", "interval": "1d", "auto_adjust": False, "actions": True,
            "metadata": {"symbol": ticker, "currency": "USD", "exchangeTimezoneName": "America/New_York",
                         "regular_end": "2026-10-19T21:00:00+00:00"},
            "bars": [{"timestamp": day.isoformat(), "close": "20", "stock_splits": "0"}
                     for day in pd.bdate_range(pd.Timestamp(min(ends)) - pd.Timedelta(days=7),
                                              "2026-10-19", tz="America/New_York")],
        }
        return reference_history._project(raw)
    monkeypatch.setattr(reference_history, "get_reference_history", history)
    peer_packages = {ticker: fixture(cik=cik, ticker=ticker)[0]
                     for ticker, cik in (("AKAM", "0001000001"), ("MSFT", "0001000002"))}
    monkeypatch.setattr(sec_edgar, "cik_for", lambda t: calls.append(("identity", t)) or peer_packages[t].cik)
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", lambda t, d: calls.append(("facts", t)) or peer_packages[t])
    monkeypatch.setattr(price_observation, "get_price_observation", lambda t, *a: calls.append(("price", t)) or quotes[t])
    monkeypatch.setattr(expectations, "get_vendor_expectations", lambda t, d, **kw:
                        expectations.VendorExpectations(status="unavailable", reason="Fixture has no consensus",
                                                        ticker=t, requested_as_of=d))
    state = {"company_of_interest": "DOCN", "trade_date": "2026-10-19", "asset_type": "stock",
             "market_observation_cutoff": "2026-10-19T22:00:00+00:00",
             "analysis_clock": {"timezone": "America/Denver", "cutoff_utc": "2026-10-20T05:59:59+00:00"},
             "evidence_acquisition": {"status": "ready"}, "financial_evidence": package.model_dump(mode="json"),
             "issuer_identity": identity, "price_observation": quotes["DOCN"]}
    config = {"data_vendors": {"core_stock_apis": "yfinance"}, "analysis_timezone": "America/Denver"}
    return state, config, calls, quotes


def test_acquire_then_finalize_retains_both_peer_vintages_and_current_history(monkeypatch):
    from tradingagents.agents import valuation_reference_flow as flow
    state, config, calls, _ = flow_fixture(monkeypatch)
    monkeypatch.setattr(flow, "default_peer_selection", lambda *a: {
        "kind": "previous", "status": "available", "reason": None,
        "peers": [{"ticker": "AKAM", "reason": "Prior cloud comparison"}]})
    prepared = flow.acquire_reference_inputs(state, config)
    record = prepared["valuation_reference"]
    assert record["phase"] == "preanalyst"
    assert record["own_history"]["status"] == "available", record
    assert record["own_history"]["current_position"]["multiple"] == record["subject"]["multiple"]
    assert [r["ticker"] for r in record["default_peers"]["accepted"]] == ["AKAM"]
    assert not {"evidence_quality", "final_rating", "financial_claim_validation"} & prepared.keys()
    state.update(prepared)
    state["financial_claim_validation"] = {"raw_report": block('[{"ticker":"MSFT","reason":"New cloud comparison"}]')}
    state["fundamentals_report"] = "Canonical replacement"
    final = flow.finalize_peer_reference(state, config)
    record = final["valuation_reference"]
    assert record["phase"] == "final"
    assert [r["ticker"] for r in record["peers"]["accepted"]] == ["MSFT"]
    assert [r["ticker"] for r in record["default_peers"]["accepted"]] == ["AKAM"]
    assert calls.count(("facts", "AKAM")) == calls.count(("facts", "MSFT")) == 1
    assert record["changes"] == {"added": ["MSFT"], "removed": ["AKAM"]}
    assert "business comparability" in final["valuation_reference_brief"]
    assert "vendor consensus, unverified" in final["valuation_reference_brief"]
    assert "model-selected" in final["valuation_reference_brief"]
    assert len(final["valuation_reference_brief"]) <= flow.MAX_REFERENCE_BRIEF


def test_pins_cannot_be_replaced_and_currency_mismatch_is_excluded(monkeypatch, tmp_path):
    from tradingagents.agents import valuation_reference_flow as flow
    from tradingagents.dataflows.vendors.yahoo.price_observation import _project
    state, config, calls, quotes = flow_fixture(monkeypatch)
    path = tmp_path / "peers.json"
    path.write_text(json.dumps({"DOCN": ["AKAM"]}))
    config["valuation_peers_file"] = str(path)
    quotes["AKAM"]["raw_source"]["metadata"]["currency"] = "EUR"
    quotes["AKAM"] = _project(quotes["AKAM"]["raw_source"])
    prepared = flow.acquire_reference_inputs(state, config)
    final = flow.finalize_peer_reference({**state, **prepared,
        "fundamentals_report": block('[{"ticker":"MSFT","reason":"Ignore pins"}]')}, config)
    peers = final["valuation_reference"]["peers"]
    assert peers["kind"] == "user-pinned" and peers["accepted"] == []
    assert peers["rejected"][0]["ticker"] == "AKAM"
    assert "currency" in peers["rejected"][0]["reason"].lower()
    assert ("facts", "MSFT") not in calls


def test_reference_replay_recomputes_from_sources_and_never_fetches(monkeypatch):
    from copy import deepcopy

    from tradingagents.agents import valuation_reference_flow as flow
    state, config, calls, _ = flow_fixture(monkeypatch)
    prepared = flow.acquire_reference_inputs(state, config)
    combined = {**state, **prepared}
    record = prepared["valuation_reference"]
    before = list(calls)
    assert flow.replay_valuation_reference(combined, record) == record
    assert calls == before
    for mutation in (
        lambda r: r["own_history"]["rows"][0].update(multiple="999"),
        lambda r: r["subject"].update(multiple="999"),
        lambda r: r["raw_sources"]["history"]["prices"][0].update(close="999"),
    ):
        tampered = deepcopy(record)
        mutation(tampered)
        with pytest.raises(ValueError):
            flow.replay_valuation_reference(combined, tampered)


def test_missing_current_price_does_not_hide_independent_history(monkeypatch):
    from tradingagents.agents import valuation_reference_flow as flow
    state, config, _, _ = flow_fixture(monkeypatch)
    state["price_observation"] = {"status": "unavailable", "reason": "No completed close"}
    prepared = flow.acquire_reference_inputs(state, config)
    assert prepared["valuation_reference"]["own_history"]["status"] == "available"
    assert prepared["valuation_reference"]["subject"]["status"] == "unavailable"
    assert "No completed close" in prepared["valuation_reference_brief"]


def test_nonstock_or_no_fundamentals_does_not_fetch_reference_sources(monkeypatch):
    from tradingagents.agents import valuation_reference_flow as flow
    state, config, calls, _ = flow_fixture(monkeypatch)
    state["evidence_acquisition"]["status"] = "not_applicable"
    state["evidence_acquisition"]["reason"] = "Fundamentals not selected"
    prepared = flow.acquire_reference_inputs(state, config)
    assert calls == []
    assert prepared["valuation_reference"]["status"] == "not_applicable"


def test_vendor_replay_rejects_mutation_and_guidance_difference_requires_all_dimensions(monkeypatch):
    from tradingagents.agents import valuation_outlooks, valuation_reference_flow as flow
    from tradingagents.agents.valuation import GroundedOutlook
    from tradingagents.dataflows.vendors.yahoo.expectations import (
        Estimate,
        VendorExpectations,
        _hash,
    )
    state, _, _, _ = flow_fixture(monkeypatch)
    snapshot = VendorExpectations(status="available", ticker="DOCN", requested_as_of="2026-10-19",
        retrieved_at=datetime(2026,10,19,22,tzinfo=UTC), estimates=[
            Estimate(metric="revenue", period_code="+1y", period_start="2027-01-01", period_end="2027-12-31",
                     currency="USD", unit="USD", basis="US-GAAP", average=120, low=110, high=130, analyst_count=4)])
    snapshot.snapshot_hash = _hash(snapshot)
    state["vendor_expectations"] = snapshot.model_dump(mode="json")
    outlook = GroundedOutlook(record_id="guide", source_ids=("sec",), metric="Revenue", unit="USD",
                              period_start="2027-01-01", period_end="2027-12-31",
                              basis="US-GAAP", low=90, high=110, kind="guidance")
    monkeypatch.setattr(valuation_outlooks, "grounded_outlooks", lambda state: (outlook,))
    assert flow.validate_vendor_expectations(state)["status"] == "available"
    text = flow.render_guidance_consensus(state)
    assert "20" in text and "comparable" in text
    state["vendor_expectations"]["estimates"][0]["average"] = "999"
    assert flow.validate_vendor_expectations(state)["status"] == "unavailable"
    assert "999" not in flow.render_guidance_consensus(state)


def test_evidence_step_finalizes_peers_before_event_and_debate(monkeypatch):
    from tradingagents.agents import event_comparison, valuation_reference_flow as flow
    from tradingagents.graph import setup
    from tradingagents.graph.conditional_logic import ConditionalLogic
    state, config, _, _ = flow_fixture(monkeypatch)
    state.update(flow.acquire_reference_inputs(state, config))
    state["fundamentals_report"] = block('[{"ticker":"AKAM","reason":"Cloud comparison"}]')
    monkeypatch.setattr(setup, "create_evidence_gate", lambda selected:
                        lambda state: {"evidence_quality": {"status": "limited"},
                                       "financial_claim_validation": {"raw_report": state["fundamentals_report"]}})
    seen = []
    def event(state, config):
        seen.append(state["valuation_reference"]["phase"])
        assert state["valuation_reference"]["peers"]["accepted"][0]["ticker"] == "AKAM"
        return {"status": "unavailable", "reason": "fixture no event"}
    monkeypatch.setattr(event_comparison, "prepare_event_comparison", event)
    workflow = setup.GraphSetup(object(), object(), ConditionalLogic(), 1).setup_graph(["fundamentals"])
    update = workflow.nodes["Evidence Check"].runnable.invoke(state)
    assert seen == ["final"]
    assert update["valuation_reference"]["phase"] == "final"
    assert "AKAM" in update["valuation_reference_brief"]


def test_publication_replays_reference_near_top_and_does_not_publish_tampered_values(monkeypatch):
    from copy import deepcopy

    from tradingagents.agents import valuation_reference_flow as flow
    from tradingagents.agents.output_validation import enforce_publication
    state, config, _, _ = flow_fixture(monkeypatch)
    state.update(flow.acquire_reference_inputs(state, config))
    state.update(evidence_quality={"status": "limited"}, final_rating="Hold")
    output = enforce_publication(state)
    text = output["final_trade_decision"]
    assert "Own history" in text and "vendor consensus, unverified" in text
    assert text.index("Valuation reference points") < text.index("Investment Thesis")
    altered = deepcopy(state)
    altered["valuation_reference"]["subject"]["multiple"] = "999"
    output = enforce_publication(altered)
    assert output["valuation_reference"]["status"] == "unavailable"
    assert "999" not in output["final_trade_decision"]
    assert output["unvalidated_outputs"]["valuation_reference"]["subject"]["multiple"] == "999"


def test_peer_pins_are_case_normalized_and_checkpoint_fingerprint_tracks_content(tmp_path):
    from tradingagents.agents import valuation_reference_flow as flow
    path = tmp_path / "peers.json"
    path.write_text(json.dumps({"docn": ["akam"]}))
    config = {"valuation_peers_file": str(path)}
    before = flow.peer_selection_fingerprint(config)
    selection = flow.default_peer_selection({"company_of_interest": "DOCN"}, config)
    assert selection["kind"] == "user-pinned"
    assert selection["peers"][0]["ticker"] == "AKAM"
    path.write_text(json.dumps({"DOCN": []}))
    assert flow.peer_selection_fingerprint(config) != before
    assert flow.default_peer_selection({"company_of_interest": "DOCN"}, config)["peers"] == []


def test_invalid_pin_rows_are_listed_without_discarding_valid_pins(monkeypatch, tmp_path):
    from tradingagents.agents import valuation_reference_flow as flow
    state, config, calls, _ = flow_fixture(monkeypatch)
    path = tmp_path / "peers.json"
    path.write_text(json.dumps({"DOCN": ["DOCN", "AKAM", "AKAM", "MSFT"]}))
    config["valuation_peers_file"] = str(path)
    prepared = flow.acquire_reference_inputs(state, config)
    peers = prepared["valuation_reference"]["peers"]
    assert [row["ticker"] for row in peers["accepted"]] == ["AKAM", "MSFT"]
    assert len(peers["rejected"]) == 2
    assert {row["ticker"] for row in peers["rejected"]} == {"DOCN", "AKAM"}
    final = flow.finalize_peer_reference({**state, **prepared, "fundamentals_report": block("[]")}, config)
    assert [row["ticker"] for row in final["valuation_reference"]["peers"]["accepted"]] == ["AKAM", "MSFT"]


def test_same_issuer_under_a_different_ticker_cannot_be_a_peer(monkeypatch):
    from tests.test_valuation_reference import fixture
    from tradingagents.agents import valuation_reference_flow as flow
    from tradingagents.dataflows.vendors import sec_edgar
    state, config, _, _ = flow_fixture(monkeypatch)
    package, _ = fixture()
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: package.cik)
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", lambda *args: package)
    state.update(flow.acquire_reference_inputs(state, config))
    final = flow.finalize_peer_reference({**state, "fundamentals_report": block(
        '[{"ticker":"AKAM","reason":"Fixture alias of same issuer"}]')}, config)
    peers = final["valuation_reference"]["peers"]
    assert not peers["accepted"]
    assert "subject issuer" in peers["rejected"][0]["reason"]


def test_missing_quarter_end_share_is_visible_as_an_unavailable_quarter(monkeypatch):
    from tradingagents.agents import valuation_reference_flow as flow
    state, config, _, _ = flow_fixture(monkeypatch)
    facts = state["financial_evidence"]["facts"]
    shares = next(row for row in facts if row["metric"] == "Common Shares Outstanding" and row["period_end"] == "2025-12-31")
    shares["period_end"] = "2026-01-15"  # Cover-page shares must not substitute for quarter-end.
    prepared = flow.acquire_reference_inputs(state, config)
    history = prepared["valuation_reference"]["own_history"]
    assert history["status"] == "available"
    assert any("2025-12-31" in row and "shares" in row for row in history["excluded"])
    assert "Excluded 2025-12-31" in prepared["valuation_reference_brief"]
    assert "2025-12-31" in prepared["valuation_reference"]["raw_sources"]["history"]["quarter_ends"]


def test_price_implied_tables_explicitly_name_enterprise_value_basis(monkeypatch):
    from tests.test_price_implied_valuation import synthetic_state
    from tradingagents.agents.valuation_comparison import (
        price_implied_valuation,
        render_price_implied_valuation,
    )
    result = price_implied_valuation(synthetic_state(monkeypatch))
    rendered = render_price_implied_valuation(result)
    assert "Obligation perimeter (enterprise value / revenue)" in rendered
    assert "Enterprise value numerator USD" in rendered


def test_source_management_guidance_is_adjacent_to_unknown_consensus(monkeypatch):
    from tradingagents.agents import valuation_comparison, valuation_reference_flow as flow
    state, _, _, _ = flow_fixture(monkeypatch)
    monkeypatch.setattr(valuation_comparison, "price_implied_valuation", lambda state: {
        "status": "available", "management_revenue_guidance_range_usd": ["1208000000", "1211000000"],
        "management_revenue_guidance_period": "full year 2026", "analysis_year": 2026,
        "disclosure_references": {"revenue": {"source_id": "sec-guidance", "locator": "block-46"}}})
    text = flow.render_guidance_consensus(state)
    assert "Management revenue guidance (full year 2026)" in text
    assert "sec-guidance" in text and "block-46" in text
    assert "Guidance/consensus difference unavailable" in text
    assert "explicit fiscal dates" in text
