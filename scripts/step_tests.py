"""Re-run single steps of a saved TradingAgents run, for cheap decision-quality tests.

Plan: 2026-11-09-tradingagents-decision-quality-step-tests-plan.md. No product code is
changed by this script; it calls the real step functions built by
``tradingagents/graph/setup.py``.

Subcommands
  baseline  one traced full run through the real CLI in disposable directories; the
            run's LangGraph checkpoint is kept so later steps start from exact inputs.
  prove     free faithfulness proof: rebuild each supported step's prompt from the saved
            run and compare it with the prompt recorded in the run's trace. No model call
            is made: the call is stopped before any request leaves the process.
  step      re-run one supported step (and, optionally, the steps after it) from the saved
            run with the real models, metered against a spending cap.

Every model call made by ``baseline`` and ``step`` is metered: a call is refused before it
is sent when the cap could be exceeded, and each completed call's tokens and cost are
appended to a ledger. Credentials are read from the existing TradingAgents ``.env`` and
never printed or written.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
import threading
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

# Run this checkout's code, never another copy installed in the environment.
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

SOURCE_ENV = Path("/Users/zipp/Documents/ChatGPT/Tauric/TradingAgents/.env")
LAUNCHER_HOME = Path.home() / ".tradingagents"
# Only these values cross from the user's .env into a run.
PASSED_KEYS = ("OPENROUTER_API_KEY", "SEC_EDGAR_USER_AGENT", "FRED_API_KEY", "ALPHA_VANTAGE_API_KEY")

# The installed launcher's settings (publication run_settings of runs 2a2e47dd/eea86100).
LAUNCHER_SETTINGS = {
    "TRADINGAGENTS_LLM_PROVIDER": "openrouter",
    "TRADINGAGENTS_LLM_BACKEND_URL": "https://openrouter.ai/api/v1",
    "TRADINGAGENTS_QUICK_THINK_LLM": "anthropic/claude-opus-5.5",
    "TRADINGAGENTS_DEEP_THINK_LLM": "openai/gpt-6.1-terra-pro",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "3",
    "TRADINGAGENTS_MAX_RISK_ROUNDS": "3",
    "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
    "TRADINGAGENTS_NO_UPDATE_CHECK": "1",
    # No automatic retries of a paid call (approved limit).
    "TRADINGAGENTS_LLM_MAX_RETRIES": "0",
}
ANALYSTS = "market,social,news,fundamentals"

# Public OpenRouter rates per token (input, output), read 2026-11-09. Terra Pro charges
# the higher pair above 272k prompt tokens. A model not listed here is refused.
RATES = {
    "anthropic/claude-opus-5.5": ((4e-6, 20e-6), None),
    "openai/gpt-6.1-terra-pro": ((1e-6, 5e-6), (272_000, (2e-6, 7.5e-6))),
}
OUTPUT_ALLOWANCE = 12_000  # output tokens reserved for a call before it is sent

# Supported start points: CLI name -> graph node.
START_POINTS = {
    "fundamentals": "Fundamentals Analyst",
    "research_manager": "Research Manager",
    "risk": "Aggressive Analyst",
    "portfolio_manager": "Portfolio Manager",
}
STOP_POINTS = ("Fundamentals Analyst", "Research Manager", "Trader", "Aggressive Analyst",
               "Conservative Analyst", "Neutral Analyst", "Portfolio Manager")
RISK_NODES = ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst")


class BudgetExceeded(BaseException):
    """Raised before a call that could exceed the cap. BaseException, so no product
    fallback path (which catches Exception) can turn it into a second paid call."""


class StopBeforeCall(BaseException):
    """Raised by the free proof once the prompt is captured, before any request."""


def model_rates(model: str, prompt_tokens: int) -> tuple[float, float]:
    if model not in RATES:
        raise BudgetExceeded(f"model {model!r} has no budgeted rate")
    base, override = RATES[model]
    if override and prompt_tokens > override[0]:
        return override[1]
    return base


def _model_name(kwargs: dict) -> str | None:
    params = kwargs.get("invocation_params") or {}
    return params.get("model") or params.get("model_name")


def _message_chars(messages) -> int:
    total = 0
    for group in messages:
        for message in group:
            content = getattr(message, "content", message)
            total += len(content if isinstance(content, str) else json.dumps(content, default=str))
    return total


class CostMeter(BaseCallbackHandler):
    """Refuses a call that could pass the cap; records each call's tokens and cost.

    The ledger is shared by every invocation under one budget name, so a cap spans
    all step tests. A call whose usage is not reported keeps its full reservation.
    """

    raise_error = True

    def __init__(self, ledger: Path, budget: str, cap: float, label: str):
        self.ledger, self.budget, self.cap, self.label = Path(ledger), budget, cap, label
        self.lock = threading.Lock()
        self.reserved: dict[str, tuple[str, float]] = {}
        # A handler reached both through a model and through the run config hears
        # each event twice; each call is reserved and recorded once.
        self.seen: set[str] = set()
        self.done: set[str] = set()

    def spent(self) -> float:
        if not self.ledger.exists():
            return 0.0
        rows = [json.loads(line) for line in self.ledger.read_text().splitlines() if line.strip()]
        return sum(row["cost_usd"] for row in rows if row.get("budget") == self.budget)

    def _append(self, row: dict) -> None:
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": datetime.now(UTC).isoformat(), "budget": self.budget,
                                     "label": self.label, **row}, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        model = _model_name(kwargs)
        # Conservative: about three characters per token.
        prompt_tokens = _message_chars(messages) // 3 + 1
        rate_in, rate_out = model_rates(model, prompt_tokens)
        estimate = prompt_tokens * rate_in + OUTPUT_ALLOWANCE * rate_out
        with self.lock:
            if str(run_id) in self.seen:
                return
            committed = self.spent() + sum(cost for _, cost in self.reserved.values())
            if committed + estimate > self.cap:
                raise BudgetExceeded(
                    f"{self.budget}: ${committed:.2f} committed, next call up to ${estimate:.2f}, "
                    f"cap ${self.cap:.2f}")
            self.seen.add(str(run_id))
            self.reserved[str(run_id)] = (model, estimate)

    def on_llm_end(self, response, *, run_id, **kwargs):
        with self.lock:
            if str(run_id) not in self.reserved:
                return
            model, estimate = self.reserved.pop(str(run_id))
            usage = _usage(response)
            if usage is None:
                self._append({"model": model, "cost_usd": estimate, "cost_source": "reserved_no_usage"})
                return
            prompt, completion, reported = usage
            if reported is not None:
                cost, source = reported, "provider_reported"
            else:
                rate_in, rate_out = model_rates(model, prompt)
                cost, source = prompt * rate_in + completion * rate_out, "list_rate"
            self._append({"model": model, "input_tokens": prompt, "output_tokens": completion,
                          "cost_usd": cost, "cost_source": source})

    def on_llm_error(self, error, *, run_id, **kwargs):
        with self.lock:
            if str(run_id) not in self.reserved:
                return
            model, estimate = self.reserved.pop(str(run_id))
            if isinstance(error, BudgetExceeded):
                return
            # A failed request may still be billed; keep the reservation.
            self._append({"model": model, "cost_usd": estimate, "cost_source": "reserved_after_error",
                          "error_class": type(error).__name__})


def _usage(response) -> tuple[int, int, float | None] | None:
    for group in getattr(response, "generations", []) or []:
        for generation in group:
            message = getattr(generation, "message", None)
            usage = getattr(message, "usage_metadata", None) or {}
            raw = (getattr(message, "response_metadata", None) or {}).get("token_usage") or {}
            if isinstance(usage.get("input_tokens"), int) and isinstance(usage.get("output_tokens"), int):
                reported = raw.get("cost")
                reported = float(reported) if isinstance(reported, (int, float)) else None
                return usage["input_tokens"], usage["output_tokens"], reported
    raw = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
    if isinstance(raw.get("prompt_tokens"), int) and isinstance(raw.get("completion_tokens"), int):
        reported = raw.get("cost")
        return raw["prompt_tokens"], raw["completion_tokens"], (
            float(reported) if isinstance(reported, (int, float)) else None)
    return None


class PromptCapture(BaseCallbackHandler):
    """Records the exact chat messages of the first call, then stops it unsent."""

    raise_error = True

    def __init__(self):
        self.prompts: list = []

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self.prompts.append(messages)
        raise StopBeforeCall()


# ---------------------------------------------------------------- environment

def load_credentials() -> dict[str, str]:
    from dotenv import dotenv_values

    values = dotenv_values(SOURCE_ENV)
    return {key: values[key] for key in PASSED_KEYS if values.get(key)}


def run_environment(root: Path, credentials: dict[str, str]) -> dict[str, str]:
    """Disposable results, cache, memory and preferences under ``root``."""
    return {
        **LAUNCHER_SETTINGS,
        **credentials,
        "TRADINGAGENTS_RESULTS_DIR": str(root / "results"),
        "TRADINGAGENTS_CACHE_DIR": str(root / "cache"),
        "TRADINGAGENTS_MEMORY_LOG_PATH": str(root / "memory" / "trading_memory.md"),
        "TRADINGAGENTS_PREFS_PATH": str(root / "cli_prefs.json"),
    }


def assert_disposable(env: dict[str, str]) -> None:
    """Refuse any location inside the launcher's own home."""
    home = LAUNCHER_HOME.resolve()
    for key in ("TRADINGAGENTS_RESULTS_DIR", "TRADINGAGENTS_CACHE_DIR",
                "TRADINGAGENTS_MEMORY_LOG_PATH", "TRADINGAGENTS_PREFS_PATH"):
        path = Path(env[key]).expanduser().resolve()
        if path == home or home in path.parents:
            raise SystemExit(f"{key} points inside the launcher's home; refusing")


def seed_root(root: Path, launcher: Path = LAUNCHER_HOME) -> dict:
    """Copy (never link) what the launcher's next run would read: its cache without
    checkpoints, its publications and its memory file."""
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"{root} is not empty; choose a new run folder")
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(launcher / "cache", root / "cache",
                    ignore=shutil.ignore_patterns("checkpoints"))
    shutil.copytree(launcher / "logs" / "publications", root / "results" / "publications")
    (root / "memory").mkdir()
    shutil.copy2(launcher / "memory" / "trading_memory.md", root / "memory" / "trading_memory.md")
    receipt = {"seeded_at": datetime.now(UTC).isoformat(), "from": str(launcher),
               "copied": ["cache (without checkpoints)", "logs/publications", "memory/trading_memory.md"]}
    (root / "seed.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


# ------------------------------------------------------------------- baseline

def cmd_baseline(args) -> int:
    root = Path(args.root).expanduser().resolve()
    credentials = load_credentials()
    if args.dry_run:
        # Everything up to the first model call, which the $0 cap refuses unsent.
        credentials["OPENROUTER_API_KEY"] = "dry-run-no-request-is-sent"
        args.cap = 0.0
    env = run_environment(root, credentials)
    assert_disposable(env)
    seed_root(root)
    os.environ.update(env)
    os.environ["TRADINGAGENTS_TRACE"] = "1"

    import cli.run as cli_run
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    meter = CostMeter(Path(args.ledger), "dry-run" if args.dry_run else "baseline", args.cap, root.name)
    base_handler = cli_run.StatsCallbackHandler

    class MeteredStats(base_handler):
        # The CLI hands its stats handler to every model and to the graph config.
        raise_error = True

        def on_chat_model_start(self, serialized, messages, **kwargs):
            meter.on_chat_model_start(serialized, messages, **kwargs)
            return super().on_chat_model_start(serialized, messages, **kwargs)

        def on_llm_end(self, response, **kwargs):
            meter.on_llm_end(response, **kwargs)
            return super().on_llm_end(response, **kwargs)

        def on_llm_error(self, error, **kwargs):
            meter.on_llm_error(error, **kwargs)
            return super().on_llm_error(error, **kwargs)

    cli_run.StatsCallbackHandler = MeteredStats
    # Keep the finished run's checkpoint: the step tool starts from its exact states.
    TradingAgentsGraph.clear_checkpoint_on_success = lambda self, *a, **k: None

    from cli.main import app

    argv = ["--ticker", args.ticker, "--date", args.date or date.today().isoformat(),
            "--analysts", ANALYSTS, "--save", "--no-show", "--html", "--checkpoint",
            "--no-ground-truth-audit"]
    try:
        app(argv, standalone_mode=False)
    finally:
        print(json.dumps({"baseline_spent_usd": round(meter.spent(), 6)}))
    return 0


# ------------------------------------------------------------- saved run access

class SavedRun:
    """One finished run: its attempt folder (trace), state log and checkpoint."""

    def __init__(self, root: Path, attempt: Path | None = None):
        self.root = Path(root)
        if attempt is None:
            traced = sorted(p.parent for p in (self.root / "results").glob("*/*/*/trace"))
            if len(traced) != 1:
                raise SystemExit(f"expected one traced attempt under {self.root}, found {len(traced)}")
            attempt = traced[0]
        self.attempt = Path(attempt)
        self.ticker = self.attempt.parents[1].name
        self.trade_date = self.attempt.parent.name

    def trace_rows(self) -> list[dict]:
        rows = []
        for path in sorted((self.attempt / "trace").glob("*.jsonl")):
            rows.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
        return sorted(rows, key=lambda row: row["sequence"])

    def run_id(self) -> str:
        ids = {row.get("run_id") for row in self.trace_rows() if row.get("run_id")}
        if len(ids) != 1:
            raise SystemExit(f"trace has {len(ids)} run ids")
        return ids.pop()

    def recorded_prompts(self, stage: str) -> list:
        return [row["prompts"] for row in self.trace_rows()
                if row.get("stage") == stage and row.get("event") == "model_start"]

    def state_log(self) -> dict:
        path = (self.root / "results" / self.ticker / "TradingAgentsStrategy_logs"
                / f"full_states_log_{self.trade_date}_{self.run_id()[:8]}.json")
        return json.loads(path.read_text())

    def checkpoint_db(self) -> Path:
        return self.root / "cache" / "checkpoints" / f"{self.ticker.upper()}.db"


def checkpoint_states(run: SavedRun, workflow) -> list:
    """Every saved state of the run's single checkpoint thread, oldest first."""
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    db = run.checkpoint_db()
    if not db.exists():
        raise SystemExit("the run kept no checkpoint")
    # Read a private copy so a test never writes into the saved run.
    conn = sqlite3.connect(str(db), check_same_thread=False)
    memory = sqlite3.connect(":memory:", check_same_thread=False)
    conn.backup(memory)
    conn.close()
    saver = SqliteSaver(memory)
    threads = {row[0] for row in memory.execute("SELECT DISTINCT thread_id FROM checkpoints")}
    if len(threads) != 1:
        raise SystemExit(f"checkpoint holds {len(threads)} threads")
    graph = workflow.compile(checkpointer=saver)
    history = list(graph.get_state_history({"configurable": {"thread_id": threads.pop()}}))
    return list(reversed(history))


def state_before(node: str, snapshots: list, occurrence: int = 0) -> dict:
    """The exact state the graph handed to ``node`` (its ``occurrence``-th turn)."""
    found = [snap for snap in snapshots if node in (snap.next or ())]
    if len(found) <= occurrence:
        raise SystemExit(f"no saved state precedes {node} turn {occurrence + 1}")
    return dict(found[occurrence].values)


def saved_state_before(node: str, saved: dict) -> dict:
    """Rebuild the state before ``node`` from the final state log (Task 0 alternative).

    The log keeps final values only: fields a later step rewrote are reset from what
    the log retains. Fundamentals is unsupported: its message history is not logged.
    """
    state = json.loads(json.dumps(saved))
    later = {
        "Research Manager": ["investment_plan", "trader_investment_plan", "final_trade_decision",
                             "final_rating", "document_followup_judgments", "target_validation",
                             "thesis_candidate", "thesis", "thesis_version_id", "publication_record",
                             "advisory_audit", "executive_summary"],
        "Aggressive Analyst": ["final_trade_decision", "final_rating", "target_validation",
                               "thesis_candidate", "thesis", "thesis_version_id",
                               "publication_record", "advisory_audit", "executive_summary"],
        "Portfolio Manager": ["final_trade_decision", "final_rating", "target_validation",
                              "thesis_candidate", "thesis", "thesis_version_id",
                              "publication_record", "executive_summary"],
    }
    if node not in later:
        raise SystemExit(f"saved-state rebuild does not support {node}")
    for key in later[node]:
        state.pop(key, None)
    outputs = dict(state.get("unvalidated_outputs") or {})
    outputs.pop("portfolio_manager", None)
    if node == "Research Manager":
        outputs.pop("trader", None)
    state["unvalidated_outputs"] = outputs
    risk = state.get("risk_debate_state") or {}
    if node == "Aggressive Analyst":
        state["risk_debate_state"] = {"history": "", "aggressive_history": "", "conservative_history": "",
                                      "neutral_history": "", "latest_speaker": "",
                                      "current_aggressive_response": "",
                                      "current_conservative_response": "",
                                      "current_neutral_response": "", "count": 0}
    elif node == "Portfolio Manager":
        state["risk_debate_state"] = {**risk, "latest_speaker": "Neutral",
                                      "current_aggressive_response": "",
                                      "current_conservative_response": "",
                                      "current_neutral_response": "",
                                      "count": 3 * int(saved["run_settings"]["max_risk_discuss_rounds"])}
    else:
        state["risk_debate_state"] = {"history": "", "aggressive_history": "", "conservative_history": "",
                                      "neutral_history": "", "latest_speaker": "",
                                      "current_aggressive_response": "",
                                      "current_conservative_response": "",
                                      "current_neutral_response": "", "count": 0}
    return state


# ------------------------------------------------------------------ the graph

def build_graph(run: SavedRun, work: Path, callbacks: list, *, api_key: str | None = None):
    """The real graph with the launcher's settings, writing only under ``work``."""
    credentials = load_credentials()
    if api_key is not None:
        credentials["OPENROUTER_API_KEY"] = api_key
    env = run_environment(work, credentials)
    assert_disposable(env)
    os.environ.update(env)
    from tradingagents.default_config import build_default_config
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = build_default_config()
    config["checkpoint_enabled"] = False
    analysts = run.state_log()["run_settings"]["analysts"]
    return TradingAgentsGraph(analysts, config=config, callbacks=callbacks)


def node_runnable(graph, node: str):
    return graph.workflow.nodes[node].runnable


def merge_update(state: dict, update: dict) -> dict:
    """Apply a node's update the way the graph's reducers would."""
    from typing import get_type_hints

    from tradingagents.agents.state import AgentState

    hints = get_type_hints(AgentState, include_extras=True)
    merged = dict(state)
    for key, value in update.items():
        reducer = next((meta for meta in getattr(hints.get(key), "__metadata__", ())
                        if callable(meta)), None)
        merged[key] = reducer(merged.get(key), value) if reducer and key in merged else value
    return merged


def apply_variant(state: dict, variant: str | None) -> dict:
    """Input-side variants that need no product change."""
    if variant in (None, "none"):
        return state
    if variant == "withhold_prior_thesis":
        return {**state, "prior_thesis": None, "thesis_context": ""}
    raise SystemExit(f"unknown variant {variant}")


# ---------------------------------------------------------------------- prove

def _comparable(prompts) -> list:
    from tradingagents.attempt_trace import AttemptRecorder

    cleaned = AttemptRecorder(Path("/nonexistent"), "proof").clean(prompts)
    return json.loads(json.dumps(cleaned, ensure_ascii=False))


def first_prompt(graph, node: str, state: dict, capture: PromptCapture) -> list | None:
    from langchain_core.messages import HumanMessage

    if node == "Fundamentals Analyst" and not state.get("messages"):
        state = {**state, "messages": [HumanMessage(state["company_of_interest"])]}
    capture.prompts.clear()
    with contextlib.suppress(StopBeforeCall):
        node_runnable(graph, node).invoke(state, {"callbacks": [capture]})
    return _comparable(capture.prompts[0]) if capture.prompts else None


def compare_prompts(built, recorded) -> dict:
    if built is None:
        return {"match": False, "reason": "no prompt built"}
    if built == recorded:
        return {"match": True}
    first = None
    for gi, (b_group, r_group) in enumerate(zip(built, recorded, strict=False)):
        for mi, (b, r) in enumerate(zip(b_group, r_group, strict=False)):
            if b != r:
                b_text, r_text = str(b.get("content")), str(r.get("content"))
                at = next((i for i, (x, y) in enumerate(zip(b_text, r_text, strict=False)) if x != y),
                          min(len(b_text), len(r_text)))
                first = {"group": gi, "message": mi, "char": at,
                         "fields": sorted(k for k in set(b) | set(r) if b.get(k) != r.get(k)),
                         "built": b_text[max(0, at - 80):at + 120],
                         "recorded": r_text[max(0, at - 80):at + 120]}
                break
        if first:
            break
    return {"match": False, "first_difference": first,
            "built_messages": sum(map(len, built)), "recorded_messages": sum(map(len, recorded))}


def cmd_prove(args) -> int:
    run = SavedRun(Path(args.run).expanduser())
    work = Path(args.out).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=False)
    os.environ.pop("TRADINGAGENTS_TRACE", None)
    capture = PromptCapture()
    # A placeholder key: the proof never sends a request.
    graph = build_graph(run, work, [], api_key="proof-no-request-is-sent")
    snapshots = checkpoint_states(run, graph.workflow) if run.checkpoint_db().exists() else None
    saved = run.state_log()
    report = {"attempt": str(run.attempt), "run_id": run.run_id(), "results": {}}
    for name, node in START_POINTS.items():
        recorded = run.recorded_prompts(node)
        entry = {"recorded_calls": len(recorded)}
        if not recorded:
            entry["status"] = "no recorded prompt"
            report["results"][name] = entry
            continue
        target = _comparable(recorded[0])
        if snapshots is not None:
            entry["checkpoint"] = compare_prompts(
                first_prompt(graph, node, state_before(node, snapshots), capture), target)
        try:
            entry["saved_state"] = compare_prompts(
                first_prompt(graph, node, saved_state_before(node, saved), capture), target)
        except SystemExit as exc:
            entry["saved_state"] = {"match": False, "reason": str(exc)}
        report["results"][name] = entry
    (work / "proof.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    summary = {name: {method: value.get("match") for method, value in entry.items()
                      if isinstance(value, dict)} for name, entry in report["results"].items()}
    print(json.dumps(summary, indent=2))
    return 0


# ----------------------------------------------------------------------- step

def _rating(text: str | None) -> str | None:
    from tradingagents.agents.rating import parse_rating

    return parse_rating(text) if text else None


def _conditions(state: dict) -> list:
    candidate = state.get("thesis_candidate") or {}
    return [{key: row.get(key) for key in ("kind", "metric", "description", "comparator", "threshold",
                                           "thesis_role", "expiry")}
            for row in candidate.get("conditions") or [] if isinstance(row, dict)]


def summarize(state: dict) -> dict:
    target = state.get("target_validation") or {}
    return {
        "research_recommendation": _rating(state.get("investment_plan")),
        "final_rating": state.get("final_rating"),
        "target": {key: target.get(key) for key in ("status", "value", "currency", "decision_date")},
        "conditions": _conditions(state),
    }


def run_steps(graph, state: dict, start: str, stop: str, config: dict, baseline: dict) -> tuple[dict, list]:
    """Run ``start`` and each later step up to and including the first turn of ``stop``.

    The risk turns are routed by the graph's own ConditionalLogic. The advisory audit
    is not re-run: the Portfolio Manager sees the baseline run's audit.
    """
    from tradingagents.graph.conditional_logic import ConditionalLogic

    logic = ConditionalLogic(graph.config["max_debate_rounds"], graph.config["max_risk_discuss_rounds"])
    node, ran = start, []
    while True:
        state = merge_update(state, node_runnable(graph, node).invoke(state, config))
        ran.append(node)
        if node == stop or node in ("Fundamentals Analyst", "Portfolio Manager"):
            return state, ran
        if node == "Research Manager":
            node = "Trader"
        elif node == "Trader":
            node = "Aggressive Analyst"
        else:
            node = logic.should_continue_risk_analysis(state)
            if node == "Portfolio Manager" and "advisory_audit" in baseline:
                state = {**state, "advisory_audit": baseline["advisory_audit"]}


def cmd_step(args) -> int:
    from tradingagents.attempt_trace import AttemptRecorder
    from tradingagents.source_replay import ReplaySession, session_context

    run = SavedRun(Path(args.run).expanduser())
    start, stop = START_POINTS[args.start], args.stop or START_POINTS[args.start]
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(run.root / "cache", out / "cache", ignore=shutil.ignore_patterns("checkpoints"))
    os.environ["TRADINGAGENTS_TRACE"] = "1"
    meter = CostMeter(Path(args.ledger), args.budget, args.cap, args.label)
    graph = build_graph(run, out, [meter])
    snapshots = checkpoint_states(run, graph.workflow)
    baseline_final = dict(snapshots[-1].values)
    scope = next((row["scope"] for row in run.trace_rows()
                  if row.get("event") == "source_session_start"), None)
    results = []
    for repeat in range(1, args.repeat + 1):
        attempt = out / f"repeat-{repeat}"
        recorder = AttemptRecorder(attempt, f"step-{uuid.uuid4()}")
        state = apply_variant(state_before(start, snapshots), args.variant)
        # Fetched inputs come from the saved run's trace; a miss is fetched live and counted.
        session = ReplaySession(recorder, scope, baseline=run.attempt) if scope is not None else None
        try:
            with session_context(session):
                final, ran = run_steps(graph, state, start, stop,
                                       {"callbacks": [recorder, meter]}, baseline_final)
        except BudgetExceeded as exc:
            if session:
                session.finish(False)
            results.append({"repeat": repeat, "stopped": f"budget: {exc}"})
            break
        if session:
            session.finish(True)
        keep = {key: final.get(key) for key in (
            "fundamentals_report", "disclosure_evidence", "investment_plan", "trader_investment_plan",
            "risk_debate_state", "final_trade_decision", "final_rating", "target_validation",
            "thesis_candidate", "document_followup_judgments") if key in final}
        attempt.mkdir(parents=True, exist_ok=True)
        (attempt / "outputs.json").write_text(json.dumps(keep, indent=2, ensure_ascii=False, default=str))
        results.append({"repeat": repeat, "ran": ran,
                        "replay_misses": len(session.misses) if session else None,
                        "after": summarize(final)})
    rows = [json.loads(line) for line in Path(args.ledger).read_text().splitlines()
            if line.strip()] if Path(args.ledger).exists() else []
    mine = [row for row in rows if row.get("label") == args.label and row.get("budget") == args.budget]
    report = {"run": str(run.attempt), "start": start, "stop": stop, "variant": args.variant,
              "before": summarize(baseline_final),
              "repeats": results,
              "calls": len(mine), "input_tokens": sum(row.get("input_tokens", 0) for row in mine),
              "output_tokens": sum(row.get("output_tokens", 0) for row in mine),
              "cost_usd": round(sum(row["cost_usd"] for row in mine), 6),
              "budget_spent_usd": round(meter.spent(), 6), "budget_cap_usd": args.cap}
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


def check_code_location() -> None:
    import cli
    import tradingagents

    for module in (tradingagents, cli):
        if REPO not in Path(module.__file__).resolve().parents:
            raise SystemExit(f"{module.__name__} loaded from {module.__file__}, not {REPO}")


def main(argv: list[str] | None = None) -> int:
    check_code_location()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    base = sub.add_parser("baseline")
    base.add_argument("--root", required=True)
    base.add_argument("--ticker", default="DOCN")
    base.add_argument("--date")
    base.add_argument("--ledger", required=True)
    base.add_argument("--cap", type=float, default=12.0)
    base.add_argument("--dry-run", action="store_true")
    prove = sub.add_parser("prove")
    prove.add_argument("--run", required=True)
    prove.add_argument("--out", required=True)
    step = sub.add_parser("step")
    step.add_argument("--run", required=True)
    step.add_argument("--start", choices=sorted(START_POINTS), required=True)
    step.add_argument("--stop", choices=STOP_POINTS)
    step.add_argument("--repeat", type=int, default=1)
    step.add_argument("--variant", default="none")
    step.add_argument("--out", required=True)
    step.add_argument("--ledger", required=True)
    step.add_argument("--budget", default="development")
    step.add_argument("--cap", type=float, default=25.0)
    step.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    return {"baseline": cmd_baseline, "prove": cmd_prove, "step": cmd_step}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
