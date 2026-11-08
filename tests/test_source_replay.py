"""Replay freezes external source inputs; candidate transformations still execute."""

import json
from copy import deepcopy
from datetime import UTC, date, datetime

import pytest

from tradingagents.attempt_trace import AttemptRecorder
from tradingagents.source_replay import ReplaySession, external_input, session_context

SCOPE = {"ticker": "DOCN", "analysis_date": "2026-11-07", "analysis_timezone": "America/Denver"}


def recorder(root, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_TRACE", "1")
    return AttemptRecorder(root, root.name)


def test_replay_serves_recorded_return_for_identical_call(tmp_path, monkeypatch):
    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with session_context(original):
        assert external_input("get_news", {"symbol": "DOCN"}, lambda: "dated news") == "dated news"
    original.finish(True)

    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate):
        value = external_input("get_news", {"symbol": "DOCN"},
                               lambda: pytest.fail("replayed call reached vendor"))
    assert value == "dated news"
    assert candidate.misses == []


def test_replay_miss_is_live_and_marked_mixed_input(tmp_path, monkeypatch):
    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    original.finish(True)
    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate):
        assert external_input("get_news", {"symbol": "DOCN"}, lambda: "new source") == "new source"
    assert candidate.misses and candidate.status == "mixed_input"
    text = "".join(p.read_text() for p in (tmp_path / "candidate/trace").glob("*.jsonl"))
    assert "replay_miss" in text and "new source" in text


def test_replay_covers_source_acquisition_without_reusing_derived_results(tmp_path, monkeypatch):
    from tradingagents.dataflows.config import run_config
    from tradingagents.dataflows.vendors import sec_edgar

    raw = {"sample": {"value": 5}}
    monkeypatch.setattr(sec_edgar, "_fetch_json", lambda url: deepcopy(raw))
    config = {"data_cache_dir": str(tmp_path / "cache-before")}
    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with session_context(original), run_config(config):
        assert sec_edgar._cached_json("https://data.sec.gov/companyfacts", "test.json") == raw
    original.finish(True)

    monkeypatch.setattr(sec_edgar, "_fetch_json", lambda url: pytest.fail("new network read"))
    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate), run_config({"data_cache_dir": str(tmp_path / "cache-after")}):
        source = sec_edgar._cached_json("https://data.sec.gov/companyfacts", "test.json")
        # A changed candidate calculation consumes the original raw source.
        result = source["sample"]["value"] * 3
    assert result == 15
    assert candidate.misses == []
    assert json.loads((tmp_path / "cache-after/sec_edgar/test.json").read_text()) == raw


def test_replay_preserves_repeated_call_occurrence(tmp_path, monkeypatch):
    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with session_context(original):
        for value in ("first", "second"):
            external_input("news", {}, lambda value=value: value)
    original.finish(True)
    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate):
        actual = [external_input("news", {}, lambda: pytest.fail("network")) for _ in range(2)]
    assert actual == ["first", "second"]


def test_replay_rejects_incomplete_or_wrong_scope(tmp_path, monkeypatch):
    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with pytest.raises(ValueError, match="incomplete"):
        ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE, baseline=tmp_path / "baseline")
    original.finish(True)
    with pytest.raises(ValueError, match="scope"):
        ReplaySession(recorder(tmp_path / "wrong", monkeypatch), {**SCOPE, "ticker": "MSFT"},
                      baseline=tmp_path / "baseline")


def test_replayed_candidate_can_be_next_build_baseline(tmp_path, monkeypatch):
    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with session_context(original):
        external_input("news", {}, lambda: "original source")
    original.finish(True)
    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate):
        assert external_input("news", {}, lambda: pytest.fail("network")) == "original source"
    candidate.finish(True)
    next_build = ReplaySession(recorder(tmp_path / "next", monkeypatch), SCOPE,
                               baseline=tmp_path / "candidate")
    with session_context(next_build):
        assert external_input("news", {}, lambda: pytest.fail("network")) == "original source"


def test_comparison_clock_frozen_but_live_acquisition_timestamp_is_real(tmp_path, monkeypatch):
    from tradingagents.source_replay import source_now, source_today

    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    original.observed_at = datetime(2001, 1, 1, tzinfo=UTC)
    original.local_date = date(2001, 1, 1)
    with session_context(original):
        assert source_now().year == source_today().year == 2001
        assert external_input("live", {}, lambda: source_now().year) > 2001
        assert source_now().year == 2001


def test_replay_rebinds_call_ids_and_preserves_command_updates(tmp_path, monkeypatch):
    from langchain_core.messages import AIMessage, ToolMessage

    from tests.test_document_search_state import state
    from tests.test_document_tool_integration import tools_graph
    from tradingagents.operational_capture import observed_node

    retained = state()
    local_scope = {"ticker": retained["company_of_interest"], "analysis_date": retained["trade_date"]}
    baseline_recorder = recorder(tmp_path / "baseline", monkeypatch)
    original = ReplaySession(baseline_recorder, local_scope)
    node = observed_node(tools_graph(), "Fundamentals Analyst")
    returned = []
    initial = {**retained, "run_id": "baseline-run", "run_settings": {}, "messages": [
        AIMessage(content="", tool_calls=[{"name": "search_documents", "args": {"query": "revenue"}, "id": "old-call"}])
    ]}
    with session_context(original):
        returned.append(node(initial, {"callbacks": [baseline_recorder]}))
    original.finish(True)
    candidate_recorder = recorder(tmp_path / "candidate", monkeypatch)
    candidate = ReplaySession(candidate_recorder, local_scope, baseline=tmp_path / "baseline")
    initial = {**retained, "run_id": "candidate-run", "run_settings": {}, "messages": [
        AIMessage(content="", tool_calls=[{"name": "search_documents", "args": {"query": "revenue"}, "id": "new-call"}])
    ]}
    with session_context(candidate):
        result = node(initial, {"callbacks": [candidate_recorder]})
    assert "fundamentals:new-call" in result["document_search_trace"]
    assert "fundamentals:old-call" not in result["document_search_trace"]
    messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert messages[0].tool_call_id == "new-call"
    assert result["document_sources"] == retained["document_sources"]
    assert json.loads(messages[0].content)["passages"] == json.loads(
        next(m for m in returned[0]["messages"] if isinstance(m, ToolMessage)).content)["passages"]
    assert candidate.misses == []


def test_raw_yahoo_replay_keeps_precision_dtype_and_timezone(tmp_path, monkeypatch):
    import numpy as np
    import pandas as pd

    from tradingagents.dataflows.vendors.yahoo.common import recorded_history

    history = pd.DataFrame({"Close": [70.12345678901234, 72.12345678901234], "Volume": [1000, 2000]},
                           index=pd.DatetimeIndex(["2026-11-05", "2026-11-06"], tz="America/New_York", name="Date"))

    class Source:
        def __init__(self, symbol):
            pass

        def history(self, **kwargs):
            return history

        def get_history_metadata(self):
            return {"symbol": "DOCN", "currency": "USD", "exchangeTimezoneName": "America/New_York",
                    "currentTradingPeriod": {"regular": {
                        "end": pd.Timestamp("2026-11-06T16:00:00-05:00"), "gmtoffset": np.int64(-18000)}}}

    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with session_context(original):
        before, metadata = recorded_history("DOCN", source_factory=Source, start="2026-11-05")
    original.finish(True)
    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate):
        after, replay_metadata = recorded_history("DOCN", source_factory=lambda s: pytest.fail("vendor call"),
                                                  start="2026-11-05")
    pd.testing.assert_frame_equal(before, history)
    pd.testing.assert_frame_equal(after, history)
    assert replay_metadata == metadata
    assert type(replay_metadata["currentTradingPeriod"]["regular"]["gmtoffset"]) is np.int64


def test_known_provider_failure_replays_without_private_exception_text(tmp_path, monkeypatch):
    from tradingagents.dataflows.errors import VendorUnavailableError

    def unavailable():
        raise VendorUnavailableError("private-provider-diagnostic", reason_code="retained_scope_mismatch")

    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with session_context(original), pytest.raises(VendorUnavailableError):
        external_input("vendor", {}, unavailable)
    original.finish(True)
    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate), pytest.raises(VendorUnavailableError) as error:
        external_input("vendor", {}, lambda: pytest.fail("vendor call"))
    assert error.value.reason_code == "retained_scope_mismatch"
    assert "private-provider-diagnostic" not in "".join(
        path.read_text() for path in (tmp_path / "baseline/trace").glob("*.jsonl"))


def test_nonfinite_source_values_round_trip_without_becoming_zero_or_missing(tmp_path, monkeypatch):
    import math

    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with session_context(original):
        before = external_input("profile", {}, lambda: {"bad_number": float("nan"), "missing": None})
    original.finish(True)
    assert math.isnan(before["bad_number"])
    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate):
        after = external_input("profile", {}, lambda: pytest.fail("vendor call"))
    assert math.isnan(after["bad_number"]) and after["missing"] is None
    assert candidate.misses == []


def test_replay_empty_settlement_history_preserves_verified_zero_coverage(tmp_path, monkeypatch):
    import pandas as pd

    from tradingagents.dataflows.vendors.yahoo import market

    frame = pd.DataFrame({name: pd.Series(dtype=float) for name in ("Open", "High", "Low", "Close", "Volume")},
                         index=pd.DatetimeIndex([], tz="America/New_York", name="Date"))

    class EmptySource:
        def __init__(self, symbol):
            pass

        def history(self, **kwargs):
            return frame

    monkeypatch.setattr(market.yf, "Ticker", EmptySource)
    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    with session_context(original):
        before = market.get_settlement_closes("DOCN", "2026-11-01", "2026-11-07")
    original.finish(True)
    monkeypatch.setattr(market.yf, "Ticker", lambda s: pytest.fail("vendor call"))
    candidate = ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                              baseline=tmp_path / "baseline")
    with session_context(candidate):
        after = market.get_settlement_closes("DOCN", "2026-11-01", "2026-11-07")
    pd.testing.assert_series_equal(before, after)
    assert after.attrs["settlement_verified_empty"] is True
    assert after.attrs == before.attrs and candidate.misses == []


def test_resumed_checkpoint_trace_is_not_a_complete_comparison_baseline(tmp_path, monkeypatch):
    original = ReplaySession(recorder(tmp_path / "baseline", monkeypatch), SCOPE)
    original.checkpoint_resumed = True
    original.finish(True)
    with pytest.raises(ValueError, match="incomplete"):
        ReplaySession(recorder(tmp_path / "candidate", monkeypatch), SCOPE,
                      baseline=tmp_path / "baseline")


def test_replay_comparison_starts_fresh_without_restoring_model_outputs(tmp_path, monkeypatch):
    from cli.run import _prepare_attempt_comparison
    from tradingagents.graph import trading_graph
    from tradingagents.source_replay import current_session

    config = {"results_dir": str(tmp_path / "results"), "data_cache_dir": str(tmp_path / "cache"),
              "memory_log_path": str(tmp_path / "memory.md"), "checkpoint_enabled": True}
    selections = {"ticker": "DOCN", "analysis_date": "2026-11-07", "asset_type": "stock"}
    baseline = tmp_path / "baseline"
    with session_context(None):
        _prepare_attempt_comparison(config, baseline, selections, recorder(baseline, monkeypatch))
        current_session().finish(True)
    monkeypatch.setenv("TRADINGAGENTS_REPLAY_TRACE", str(baseline))
    with session_context(None):
        prepared = _prepare_attempt_comparison(config, tmp_path / "candidate", selections,
                                               recorder(tmp_path / "candidate", monkeypatch))
    assert prepared["checkpoint_enabled"] is False
    graph = object.__new__(trading_graph.TradingAgentsGraph)
    graph.config = prepared
    monkeypatch.setattr(trading_graph, "get_checkpointer", lambda *a, **k: pytest.fail("restored old model outputs"))
    assert graph.begin_checkpoint("DOCN", "2026-11-07") is None
