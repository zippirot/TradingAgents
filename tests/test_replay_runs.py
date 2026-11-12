"""The loop's free check: saved runs replay through today's code with no model call and no network."""
import json
import socket

import pytest

from scripts import replay_runs
from tests.test_case_valuation import revenue_case
from tests.test_shared_valuation import state

SECRET = 987654321


def _saved(tmp_path, run_id="11111111-aaaa", name=None, multiple="3"):
    case = revenue_case()
    case["request"]["multiple"] = multiple
    saved = state([case])
    saved.update(run_id=run_id, final_rating="Hold",
                 shared_valuation_scenarios={"status": "unavailable", "requests": [case]},
                 portfolio_inputs={"cash": SECRET, "portfolio_value": SECRET, "positions": {"DOCN": {"shares": SECRET}},
                                   "currency": "USD", "fingerprint": "abc123"})
    folder = tmp_path / "logs" / "DOCN" / "TradingAgentsStrategy_logs"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (name or f"full_states_log_2026-10-19_{run_id[:8]}.json")).write_text(json.dumps(saved))
    return tmp_path / "logs"


def test_a_saved_run_replays_to_the_same_summary_twice_and_prices_its_saved_cases(tmp_path):
    logs = _saved(tmp_path)
    first = replay_runs.replay(logs, tmp_path / "a")
    replay_runs.replay(logs, tmp_path / "b")
    assert first == {"replayed": ["DOCN_11111111.json"], "skipped": []}
    assert replay_runs.compare(tmp_path / "a", tmp_path / "b") == []
    summary = json.loads((tmp_path / "a" / "DOCN_11111111.json").read_text())
    assert summary["cases"]["status"] == "available" and summary["cases"]["rows"][0]["target"]


def test_a_difference_in_what_code_computes_shows_in_the_comparison(tmp_path):
    replay_runs.replay(_saved(tmp_path / "x", multiple="3"), tmp_path / "a")
    replay_runs.replay(_saved(tmp_path / "y", multiple="4"), tmp_path / "b")
    fields = [row["field"] for row in replay_runs.compare(tmp_path / "a", tmp_path / "b")]
    assert "cases.rows[Base].target" in fields


def test_a_damaged_run_is_listed_and_skipped_and_a_re_export_of_one_run_is_counted_once(tmp_path):
    logs = _saved(tmp_path)
    _saved(tmp_path, name="full_states_log_2026-10-19.json")
    (logs / "DOCN" / "TradingAgentsStrategy_logs" / "full_states_log_2026-10-18_bad.json").write_text("{not json")
    index = replay_runs.replay(logs, tmp_path / "out")
    assert index["replayed"] == ["DOCN_11111111.json"]
    assert [row["file"] for row in index["skipped"]] == ["full_states_log_2026-10-18_bad.json"]


def test_no_portfolio_figure_reaches_any_output_only_the_fingerprint(tmp_path, capsys):
    replay_runs.main(["replay", "--logs", str(_saved(tmp_path)), "--out", str(tmp_path / "out")])
    written = "".join(path.read_text() for path in (tmp_path / "out").glob("*.json")) + capsys.readouterr().out
    assert str(SECRET) not in written and "abc123" in written


def test_replay_refuses_the_network_and_restores_it_afterwards():
    real = socket.socket.connect
    with replay_runs.offline(), pytest.raises(OSError, match="disabled during replay"):
        socket.socket().connect(("127.0.0.1", 9))
    assert socket.socket.connect is real
