"""The offline scorer's transport: what was captured is replayed byte for byte, and a miss is never fetched."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "large_filer_score", Path(__file__).resolve().parents[1] / "scripts" / "large_filer_score.py")
scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scorer)


def _live(calls):
    def get(url, **kwargs):
        calls.append((url, kwargs.get("stream")))
        return SimpleNamespace(status_code=200, headers={"Content-Type": "text/html", "Set-Cookie": "x"},
                               content=b"<html>" + url.encode() + b"</html>")
    return get


def test_a_captured_response_replays_with_the_same_bytes_and_no_network(tmp_path):
    calls = []
    captured = scorer.Transport(scorer.Store(tmp_path), live=_live(calls))("https://www.sec.gov/a.htm", stream=True)
    assert calls == [("https://www.sec.gov/a.htm", False)] and captured.status_code == 200
    replay = scorer.Transport(scorer.Store(tmp_path))
    again = replay("https://www.sec.gov/a.htm", stream=True, timeout=1)
    assert b"".join(again.iter_content(4)) == captured.content and again.headers == {"Content-Type": "text/html"}
    again.raise_for_status()


def test_a_missing_or_altered_response_is_a_miss_not_a_fetch(tmp_path):
    scorer.Transport(scorer.Store(tmp_path), live=_live([]))("https://www.sec.gov/a.htm")
    replay = scorer.Transport(scorer.Store(tmp_path))
    with pytest.raises(scorer.ReplayMiss):
        replay("https://www.sec.gov/b.htm")
    assert replay.misses == ["https://www.sec.gov/b.htm"]
    next((tmp_path / "raw").iterdir()).write_bytes(b"changed")
    with pytest.raises(scorer.ReplayMiss, match="hash mismatch"):
        scorer.Transport(scorer.Store(tmp_path))("https://www.sec.gov/a.htm")


def test_a_run_with_a_miss_is_an_input_failure_even_if_the_step_absorbs_it(tmp_path, monkeypatch):
    def absorbed(ticker, as_of, transport):
        transport.misses.append("https://www.sec.gov/c.htm")
        return {"ticker": ticker, "as_of": as_of, "passes": 7, "all_seven": True, "checks": {},
                "replay_misses": list(transport.misses)}
    monkeypatch.setattr(scorer, "score_one", absorbed)
    row = scorer.run("score", ["MSFT"], "2026-11-11", tmp_path, None)["results"][0]
    assert row["all_seven"] is False and row["passes"] is None and "not in the store" in row["input_failure"]
