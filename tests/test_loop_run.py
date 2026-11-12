"""The loop's run command: every question answered up front, and no start past the cycle's budget."""
import json

from scripts import loop_run


def _state(tmp_path, runs):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"budget_per_cycle": 50.0, "runs": runs}))
    return path


def test_a_dry_run_prints_the_command_and_settings_and_starts_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(loop_run.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("started")))
    assert loop_run.main(["--ticker", "WMT", "--date", "2026-11-11", "--dry-run", "--state", str(_state(tmp_path, []))]) == 0
    out = capsys.readouterr().out
    assert "--ticker WMT --date 2026-11-11" in out and "--save --no-show" in out
    assert "TRADINGAGENTS_MAX_DEBATE_ROUNDS=1" in out and "TRADINGAGENTS_MAX_RISK_ROUNDS=1" in out
    assert "portfolio.loop.json" in out and "not yet measured" in out and "nothing was started" in out


def test_a_run_is_refused_when_what_is_left_of_the_cycle_is_below_the_last_measured_cost(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(loop_run.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("started")))
    spent = [{"cycle": 1, "cost": 20.0}, {"cycle": 1, "cost": 20.0}]
    assert loop_run.main(["--ticker", "WMT", "--cycle", "1", "--state", str(_state(tmp_path, spent))]) == 2
    assert "REFUSED" in capsys.readouterr().out
    # Another cycle has its own budget, and an unmeasured cost does not block the first run.
    assert loop_run.refusal(json.loads(_state(tmp_path, spent).read_text()), 2) is None
    assert loop_run.refusal({"budget_per_cycle": 50.0, "runs": []}, 0) is None


def test_the_run_never_uses_the_users_own_portfolio_or_results_folders():
    assert "--portfolio" in loop_run.command("WMT", "2026-11-11")
    env = loop_run.environment()
    assert all("/.tradingagents/loop/" in env[name] for name in
               ("TRADINGAGENTS_RESULTS_DIR", "TRADINGAGENTS_CACHE_DIR", "TRADINGAGENTS_MEMORY_LOG_PATH"))
