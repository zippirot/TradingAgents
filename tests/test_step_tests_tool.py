"""The single-step re-run tool (scripts/step_tests.py), offline with scripted models."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tests.test_graph_end_to_end import TRADE_DATE, ScriptedModel, _Client, offline  # noqa: F401
from tradingagents.attempt_trace import AttemptRecorder
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph
from tradingagents.source_replay import ReplaySession, session_context

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("step_tests", ROOT / "scripts" / "step_tests.py")
step_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(step_tests)


def _saved_run(root: Path, monkeypatch, model) -> Path:
    """A traced run whose checkpoint is kept, laid out as the CLI lays it out."""
    monkeypatch.setenv("TRADINGAGENTS_TRACE", "1")
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _Client(model))
    config = {**DEFAULT_CONFIG, "results_dir": str(root / "results"), "data_cache_dir": str(root / "cache"),
              "memory_log_path": str(root / "memory" / "trading_memory.md"), "checkpoint_enabled": True,
              "max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
    graph = trading_graph.TradingAgentsGraph(("market", "social", "news"), config=config)
    attempt = root / "results" / "NVDA" / TRADE_DATE / "attempt-1"
    recorder = AttemptRecorder(attempt, "attempt-1")
    scope = {"ticker": "NVDA", "analysis_date": TRADE_DATE}
    session = ReplaySession(recorder, scope)
    with session_context(session):
        state = graph.create_run_state("NVDA", TRADE_DATE)
        tid = graph.begin_checkpoint("NVDA", TRADE_DATE)
        try:
            final = graph.graph.invoke(state, {"callbacks": [recorder], "recursion_limit": 100,
                                               "configurable": {"thread_id": tid}})
        finally:
            graph.end_checkpoint()
    session.finish(True)
    graph.record_decision("NVDA", TRADE_DATE, final)
    monkeypatch.delenv("TRADINGAGENTS_TRACE")
    return attempt


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(step_tests, "load_credentials", lambda: {})
    monkeypatch.setattr(step_tests, "LAUNCHER_HOME", tmp_path / "launcher-home")
    for key in ("TRADINGAGENTS_RESULTS_DIR", "TRADINGAGENTS_CACHE_DIR", "TRADINGAGENTS_MEMORY_LOG_PATH",
                "TRADINGAGENTS_PREFS_PATH", "TRADINGAGENTS_QUICK_THINK_LLM", "TRADINGAGENTS_DEEP_THINK_LLM",
                "TRADINGAGENTS_MAX_DEBATE_ROUNDS", "TRADINGAGENTS_MAX_RISK_ROUNDS", "OPENROUTER_API_KEY",
                "TRADINGAGENTS_LLM_PROVIDER", "TRADINGAGENTS_LLM_BACKEND_URL", "TRADINGAGENTS_LLM_MAX_RETRIES",
                "TRADINGAGENTS_OUTPUT_LANGUAGE", "TRADINGAGENTS_NO_UPDATE_CHECK"):
        monkeypatch.setenv(key, "")
    # The step tool reads the launcher's settings; the scripted run used one round each.
    monkeypatch.setitem(step_tests.LAUNCHER_SETTINGS, "TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1")
    monkeypatch.setitem(step_tests.LAUNCHER_SETTINGS, "TRADINGAGENTS_MAX_RISK_ROUNDS", "1")
    return tmp_path


@pytest.mark.unit
def test_proof_rebuilds_each_recorded_prompt_from_the_checkpoint(isolated, monkeypatch, offline):  # noqa: F811
    _saved_run(isolated / "run", monkeypatch, ScriptedModel())
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _Client(ScriptedModel()))

    step_tests.main(["prove", "--run", str(isolated / "run"), "--out", str(isolated / "proof")])

    report = json.loads((isolated / "proof" / "proof.json").read_text())["results"]
    for name in ("research_manager", "risk", "portfolio_manager"):
        assert report[name]["checkpoint"] == {"match": True}, name
    assert report["fundamentals"]["status"] == "no recorded prompt"


@pytest.mark.unit
def test_proof_reports_a_changed_prompt_with_its_first_difference(isolated, monkeypatch, offline):  # noqa: F811
    _saved_run(isolated / "run", monkeypatch, ScriptedModel())
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _Client(ScriptedModel()))
    from tradingagents.agents.managers import portfolio_manager

    original = portfolio_manager.get_language_instruction
    monkeypatch.setattr(portfolio_manager, "get_language_instruction", lambda: original() + "\nEXTRA")

    step_tests.main(["prove", "--run", str(isolated / "run"), "--out", str(isolated / "proof")])

    result = json.loads((isolated / "proof" / "proof.json").read_text())["results"]["portfolio_manager"]
    assert result["checkpoint"]["match"] is False
    assert "EXTRA" in result["checkpoint"]["first_difference"]["built"]


@pytest.mark.unit
def test_a_step_reruns_only_the_named_steps_and_meters_each_call(isolated, monkeypatch, offline):  # noqa: F811
    _saved_run(isolated / "run", monkeypatch, ScriptedModel())
    model = ScriptedModel()
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _Client(model))
    ledger = isolated / "ledger.jsonl"
    # The scripted model reports no usage, so each call keeps its reservation.
    monkeypatch.setitem(step_tests.RATES, None, ((1e-6, 1e-6), None))

    step_tests.main(["step", "--run", str(isolated / "run"), "--start", "research_manager",
                     "--stop", "Trader", "--repeat", "2", "--out", str(isolated / "out"),
                     "--ledger", str(ledger), "--label", "t", "--cap", "5"])

    report = json.loads((isolated / "out" / "report.json").read_text())
    assert [row["ran"] for row in report["repeats"]] == [["Research Manager", "Trader"]] * 2
    assert len(model.calls) == 4 and report["calls"] == 4
    assert report["repeats"][0]["after"]["research_recommendation"] == "Overweight"
    trace = list((isolated / "out" / "repeat-1" / "trace").glob("*research-manager.jsonl"))
    assert trace and "model_start" in trace[0].read_text()


@pytest.mark.unit
def test_a_risk_start_runs_the_whole_debate_then_the_manager_with_the_saved_audit(
        isolated, monkeypatch, offline):  # noqa: F811
    _saved_run(isolated / "run", monkeypatch, ScriptedModel())
    model = ScriptedModel()
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _Client(model))
    monkeypatch.setitem(step_tests.RATES, None, ((1e-6, 1e-6), None))

    step_tests.main(["step", "--run", str(isolated / "run"), "--start", "risk",
                     "--stop", "Portfolio Manager", "--out", str(isolated / "out"),
                     "--ledger", str(isolated / "ledger.jsonl"), "--label", "t", "--cap", "5"])

    report = json.loads((isolated / "out" / "report.json").read_text())
    assert report["repeats"][0]["ran"] == ["Aggressive Analyst", "Conservative Analyst",
                                           "Neutral Analyst", "Portfolio Manager"]
    assert report["repeats"][0]["after"]["final_rating"] == "Overweight"


@pytest.mark.unit
def test_the_meter_refuses_a_call_that_could_pass_the_cap(tmp_path):
    meter = step_tests.CostMeter(tmp_path / "ledger.jsonl", "development", 0.05, "t")
    messages = [[AIMessage(content="x" * 3000)]]
    params = {"invocation_params": {"model": "anthropic/claude-opus-5.5"}}
    # 12k reserved output tokens at $20/M is $0.24, above a $0.05 cap.
    with pytest.raises(step_tests.BudgetExceeded):
        meter.on_chat_model_start({}, messages, run_id="a", **params)
    assert not (tmp_path / "ledger.jsonl").exists()


@pytest.mark.unit
def test_the_meter_records_reported_cost_and_counts_it_against_the_cap(tmp_path):
    meter = step_tests.CostMeter(tmp_path / "ledger.jsonl", "development", 1.0, "t")
    params = {"invocation_params": {"model": "openai/gpt-6.1-terra-pro"}}
    meter.on_chat_model_start({}, [[AIMessage(content="hello")]], run_id="a", **params)
    message = AIMessage(content="ok", usage_metadata={"input_tokens": 1000, "output_tokens": 200,
                                                       "total_tokens": 1200},
                        response_metadata={"token_usage": {"cost": 0.0123}})
    meter.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id="a")
    row = json.loads((tmp_path / "ledger.jsonl").read_text())
    assert row["cost_usd"] == 0.0123 and row["cost_source"] == "provider_reported"
    assert row["input_tokens"] == 1000 and meter.spent() == pytest.approx(0.0123)
    # Without a reported cost the list rate applies.
    meter.on_chat_model_start({}, [[AIMessage(content="hello")]], run_id="b", **params)
    plain = AIMessage(content="ok", usage_metadata={"input_tokens": 1000, "output_tokens": 200,
                                                     "total_tokens": 1200})
    meter.on_llm_end(LLMResult(generations=[[ChatGeneration(message=plain)]]), run_id="b")
    assert meter.spent() == pytest.approx(0.0123 + 1000 * 1e-6 + 200 * 5e-6)


@pytest.mark.unit
def test_an_unbudgeted_model_is_refused(tmp_path):
    meter = step_tests.CostMeter(tmp_path / "ledger.jsonl", "development", 100.0, "t")
    with pytest.raises(step_tests.BudgetExceeded, match="no budgeted rate"):
        meter.on_chat_model_start({}, [[AIMessage(content="x")]], run_id="a",
                                  invocation_params={"model": "openai/other"})


@pytest.mark.unit
def test_run_folders_inside_the_launcher_home_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(step_tests, "LAUNCHER_HOME", tmp_path / "home")
    env = step_tests.run_environment(tmp_path / "home" / "logs", {})
    with pytest.raises(SystemExit, match="launcher's home"):
        step_tests.assert_disposable(env)
    step_tests.assert_disposable(step_tests.run_environment(tmp_path / "elsewhere", {}))


@pytest.mark.unit
def test_seeding_copies_without_checkpoints_and_refuses_a_used_folder(tmp_path):
    home = tmp_path / "home"
    (home / "cache" / "checkpoints").mkdir(parents=True)
    (home / "cache" / "checkpoints" / "DOCN.db").write_text("x")
    (home / "cache" / "sec.json").write_text("{}")
    (home / "logs" / "publications" / "records").mkdir(parents=True)
    (home / "memory").mkdir()
    (home / "memory" / "trading_memory.md").write_text("memory")
    step_tests.seed_root(tmp_path / "run", home)
    assert (tmp_path / "run" / "cache" / "sec.json").exists()
    assert not (tmp_path / "run" / "cache" / "checkpoints").exists()
    assert (tmp_path / "run" / "memory" / "trading_memory.md").read_text() == "memory"
    with pytest.raises(SystemExit, match="not empty"):
        step_tests.seed_root(tmp_path / "run", home)


@pytest.mark.unit
def test_a_call_heard_twice_is_reserved_and_recorded_once(tmp_path):
    meter = step_tests.CostMeter(tmp_path / "ledger.jsonl", "development", 1.0, "t")
    params = {"invocation_params": {"model": "openai/gpt-6.1-terra-pro"}}
    message = AIMessage(content="ok", usage_metadata={"input_tokens": 10, "output_tokens": 2,
                                                       "total_tokens": 12})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    for _ in range(2):
        meter.on_chat_model_start({}, [[AIMessage(content="hello")]], run_id="a", **params)
    for _ in range(2):
        meter.on_llm_end(result, run_id="a")
    assert len((tmp_path / "ledger.jsonl").read_text().splitlines()) == 1
    assert not meter.reserved


@pytest.mark.unit
def test_a_fact_is_present_only_when_its_patterns_share_a_window():
    patterns = ["RPO|remaining performance obligation", r"\$\s?800(\.0)?\s?(million|M)\b"]
    assert step_tests.fact_present("Remaining performance obligation was $800 million.", patterns)
    assert not step_tests.fact_present("RPO grew." + " filler" * 200 + " $800 million", patterns)
    assert not step_tests.fact_present("RPO was $8,000 million", patterns)


@pytest.mark.unit
def test_recall_follows_a_fact_from_the_debate_state_into_the_bull_and_bear_prompts(
        isolated, monkeypatch, offline):  # noqa: F811
    _saved_run(isolated / "run", monkeypatch, ScriptedModel())
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _Client(ScriptedModel()))
    facts = isolated / "facts.json"
    facts.write_text(json.dumps({"facts": [
        {"id": "ticker", "fact": "the ticker", "patterns": ["NVDA"]},
        {"id": "absent", "fact": "never present", "patterns": ["no such phrase anywhere"]}]}))

    step_tests.main(["recall", "--run", str(isolated / "run"), "--facts", str(facts),
                     "--out", str(isolated / "recall")])

    report = json.loads((isolated / "recall" / "recall.json").read_text())
    rows = {row["id"]: row for row in report["facts"]}
    assert rows["ticker"]["reaches_bull"] and rows["ticker"]["reaches_bear"]
    assert rows["ticker"]["found_in"]["debate_state"]
    assert not rows["absent"]["reaches_bull"] and report["reached_both"] == 1
