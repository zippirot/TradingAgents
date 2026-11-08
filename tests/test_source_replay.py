"""Replay freezes external source inputs; candidate transformations still execute."""

import json
from copy import deepcopy
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

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


@pytest.mark.parametrize('vendor', ['stocktwits', 'reddit'])
def test_direct_social_acquisition_replays_raw_input_and_current_render(tmp_path, monkeypatch, vendor):
    from tradingagents.dataflows.vendors import reddit, stocktwits
    module = stocktwits if vendor == 'stocktwits' else reddit
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = (json.dumps({'messages': [
        {'created_at': '2026-11-06T16:00:00Z', 'body': 'first'},
        {'created_at': '2026-11-06T15:00:00Z', 'body': 'second'}]}).encode() if vendor == 'stocktwits' else
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>first</title><published>2026-11-06T16:00:00Z</published></entry><entry><title>second</title><published>2026-11-06T15:00:00Z</published></entry></feed>')
    monkeypatch.setattr(module, 'urlopen', lambda *a, **k: response)
    def fetch(limit):
        return (module.fetch_stocktwits_messages('DOCN', limit=limit) if vendor == 'stocktwits' else
                module.fetch_reddit_posts('DOCN', ['stocks'], limit_per_sub=limit))
    original = ReplaySession(recorder(tmp_path/'baseline', monkeypatch), SCOPE)
    with session_context(original):
        assert 'second' in fetch(2)
    original.finish(True)
    monkeypatch.setattr(module, 'urlopen', lambda *a, **k: pytest.fail('candidate reached live social source'))
    candidate = ReplaySession(recorder(tmp_path/'candidate', monkeypatch), SCOPE, baseline=tmp_path/'baseline')
    with session_context(candidate):
        text = fetch(1)
    assert 'first' in text and 'second' not in text
    assert not candidate.misses


def test_reference_history_replays_raw_bars_not_retained_projection(tmp_path, monkeypatch):
    from tests.test_reference_history import ENDS, install
    from tradingagents.dataflows.vendors.yahoo import reference_history
    install(monkeypatch)
    original = ReplaySession(recorder(tmp_path/'baseline', monkeypatch), SCOPE)
    with session_context(original):
        baseline = reference_history.get_reference_history('DOCN', '2026-11-05', ENDS)
    assert baseline['status'] == 'available'
    original.finish(True)
    monkeypatch.setattr(reference_history.yf, 'Ticker', lambda *a: pytest.fail('candidate reached live reference source'))
    project = reference_history._project
    def current_project(raw):
        return {**project(raw), 'candidate_projection_executed': True}
    monkeypatch.setattr(reference_history, '_project', current_project)
    candidate = ReplaySession(recorder(tmp_path/'candidate', monkeypatch), SCOPE, baseline=tmp_path/'baseline')
    with session_context(candidate):
        result = reference_history.get_reference_history('DOCN', '2026-11-05', ENDS)
    assert result['status'] == 'available' and result['candidate_projection_executed']
    assert result['raw_source'] == baseline['raw_source']
    assert not candidate.misses


def test_threaded_optional_post_screen_retains_and_replays_vendor_input(tmp_path, monkeypatch):
    from tests.test_post_screen import _post_answers
    from tradingagents.agents import post_screen
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-typesafe-credential')
    monkeypatch.setattr(post_screen, 'resolve_instrument_identity', lambda _: {'company_name': 'DOCN'})
    monkeypatch.setattr(post_screen.requests, 'post', lambda *a, **k: _post_answers(0.9))
    original = ReplaySession(recorder(tmp_path/'baseline', monkeypatch), SCOPE)
    with session_context(original):
        before = post_screen.jev_screen('DOCN')(['first', 'second'])
    original.finish(True)
    monkeypatch.setattr(post_screen.requests, 'post', lambda *a, **k: pytest.fail('candidate reached live post screen'))
    candidate = ReplaySession(recorder(tmp_path/'candidate', monkeypatch), SCOPE, baseline=tmp_path/'baseline')
    with session_context(candidate):
        assert post_screen.jev_screen('DOCN')(['first', 'second']) == before
    assert not candidate.misses
    rows = [json.loads(line) for p in (tmp_path/'baseline/trace').glob('*.jsonl') for line in p.read_text().splitlines()]
    assert len([r for r in rows if r['event']=='source_input']) == 2
    assert 'synthetic-typesafe-credential' not in str(rows)


def test_raw_utf8_source_bytes_replay_without_changing_encoding(tmp_path, monkeypatch):
    from tradingagents.source_replay import external_input
    raw = '<feed>caf\u00e9</feed>'.encode()
    original = ReplaySession(recorder(tmp_path/'baseline', monkeypatch), SCOPE)
    with session_context(original):
        assert external_input('raw_feed', {}, lambda: raw) == raw
    original.finish(True)
    candidate = ReplaySession(recorder(tmp_path/'candidate', monkeypatch), SCOPE, baseline=tmp_path/'baseline')
    with session_context(candidate):
        assert external_input('raw_feed', {}, lambda: pytest.fail('new source read')) == raw
    assert not candidate.misses


def test_credential_in_raw_feed_is_redacted_and_not_silently_replayed(tmp_path, monkeypatch):
    from tradingagents.source_replay import external_input
    secret = 'synthetic-feed-secret'
    monkeypatch.setenv('OPENAI_API_KEY', secret)
    original = ReplaySession(recorder(tmp_path/'baseline', monkeypatch), SCOPE)
    with session_context(original):
        external_input('raw_feed', {}, lambda: ('<feed>'+secret+'</feed>').encode())
    original.finish(True)
    text = ''.join(p.read_text() for p in (tmp_path/'baseline/trace').glob('*.jsonl'))
    assert secret not in text and secret.encode().hex() not in text
    candidate = ReplaySession(recorder(tmp_path/'candidate', monkeypatch), SCOPE, baseline=tmp_path/'baseline')
    with session_context(candidate):
        assert external_input('raw_feed', {}, lambda: b'<feed>new input</feed>') == b'<feed>new input</feed>'
    assert candidate.status == 'mixed_input' and len(candidate.misses) == 1


@pytest.mark.parametrize('key,before,after', [
    ('openai_reasoning_effort', 'medium', 'high'),
    ('temperature', 0.1, 0.9),
    ('quick_think_provider', 'openai', 'anthropic'),
    ('max_tokens', 1000, 2000),
])
def test_changed_model_settings_cannot_claim_same_comparison_scope(tmp_path, monkeypatch, key, before, after):
    from cli.run import _prepare_attempt_comparison
    from tradingagents.source_replay import current_session
    config = {'results_dir': str(tmp_path/'results'), 'data_cache_dir': str(tmp_path/'cache'),
              'memory_log_path': str(tmp_path/'memory.md'), key: before}
    selections = {'ticker':'DOCN', 'analysis_date':'2026-11-07', 'asset_type':'stock'}
    baseline = tmp_path/'baseline'
    with session_context(None):
        _prepare_attempt_comparison(config, baseline, selections, recorder(baseline, monkeypatch))
        current_session().finish(True)
    monkeypatch.setenv('TRADINGAGENTS_REPLAY_TRACE', str(baseline))
    with session_context(None), pytest.raises(ValueError, match='scope'):
        _prepare_attempt_comparison({**config,key:after}, tmp_path/'candidate', selections,
                                    recorder(tmp_path/'candidate', monkeypatch))


def test_unfinished_social_screen_request_keeps_comparison_trace_incomplete(tmp_path, monkeypatch):
    from threading import Event

    from tests.test_post_screen import _post_answers, _Response
    from tradingagents.agents import post_screen

    entered, release, completed = Event(), Event(), Event()

    class SlowResponse:
        status_code = 200
        headers = {}

        def json(self):
            entered.set()
            assert release.wait(5)
            completed.set()
            return _post_answers(0.9).json()

    def post(url, **kwargs):
        if kwargs['json']['state']['post'] == 'slow':
            return SlowResponse()
        assert entered.wait(5)
        return _Response(401)

    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-typesafe-credential')
    monkeypatch.setattr(post_screen, 'resolve_instrument_identity', lambda _: {'company_name': 'DOCN'})
    monkeypatch.setattr(post_screen.requests, 'post', post)
    baseline = tmp_path / 'baseline'
    original = ReplaySession(recorder(baseline, monkeypatch), SCOPE)
    try:
        with session_context(original):
            keep, note = post_screen.jev_screen('DOCN')(['slow', 'bad'])
            assert keep == [True, True] and 'unavailable' in note
            original.finish(True)
        with pytest.raises(ValueError, match='incomplete'):
            ReplaySession(recorder(tmp_path / 'candidate', monkeypatch), SCOPE, baseline=baseline)
    finally:
        release.set()
        assert completed.wait(5)


@pytest.mark.parametrize('case', ['undated_item', 'empty_feed_coverage'])
def test_social_window_classification_uses_frozen_comparison_clock(tmp_path, monkeypatch, case):
    from tradingagents.dataflows.date_window import coverage_gap, in_window

    original = ReplaySession(recorder(tmp_path / 'baseline', monkeypatch), SCOPE)
    original.observed_at = datetime(2001, 1, 1, 12, tzinfo=UTC)
    with session_context(original):
        if case == 'undated_item':
            assert in_window(None, datetime(2001, 1, 1), datetime(2001, 1, 1)) is True
        else:
            assert coverage_gap([], '2001-01-01', '2001-01-01', 'social', 'posts') is None


def test_live_reference_history_records_acquisition_clock_not_comparison_clock(tmp_path, monkeypatch):
    from tests.test_reference_history import ENDS, install
    from tradingagents.dataflows.vendors.yahoo import reference_history

    acquisition_clock = reference_history._now
    install(monkeypatch)
    monkeypatch.setattr(reference_history, '_now', acquisition_clock)

    class AcquisitionTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 5, 22, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(reference_history, 'datetime', AcquisitionTime)
    original = ReplaySession(recorder(tmp_path / 'baseline', monkeypatch), SCOPE)
    original.observed_at = datetime(2026, 11, 5, 21, 59, tzinfo=UTC)
    with session_context(original):
        result = reference_history.get_reference_history('DOCN', '2026-11-05', ENDS)
    assert result['status'] == 'available', result
    assert result['raw_source']['retrieved_at'] == '2026-11-05T22:00:00+00:00'
