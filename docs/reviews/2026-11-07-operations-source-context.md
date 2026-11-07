# Exact source context for Build D independent audit

Verbatim bodies at application candidate `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; context only, not additional requirements. Named complete modules/functions follow. Diff supplies all changed code/tests including role consumers and LLM adapter changes. Missing unrelated bodies are not implied available. Selected bodies may reference module constants/imports present in diff or the explicitly supplied complete owning source modules. `_COPY_SCRIPT` is unchanged from D1 and is supplied through full report_html.py in the governing inputs. Runtime receipts are builder observations, not auditor-executed tests.


## `cli/run.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `afc2b48dc00d12bf9d364e97f52a43b70a5477e121bb119aae6a75fcf7c0f202`.

```python
"""Running one analysis from the CLI: build the graph, stream it into the live view, save the report."""

import logging
import os
import sys
import time
import webbrowser
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from uuid import UUID, uuid4

import typer
from rich.live import Live

from cli.display import (
    ANALYST_ORDER,
    AnalystWallTimeTracker,
    classify_message_type,
    console,
    create_layout,
    display_complete_report,
    message_buffer,
    update_analyst_statuses,
    update_display,
    update_research_team_status,
)
from cli.run_logging import cleanup_run_logging, configure_run_logging
from cli.selections import depth_from_env, get_user_selections, unattended_gaps
from cli.stats_handler import StatsCallbackHandler, render_usage_cost
from tradingagents.agents.rating import is_review, run_rating
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import (
    build_analyst_execution_plan,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph, record_attempt_event

logger = logging.getLogger(__name__)


def _configure_run_logging(results_dir: Path) -> Path:
    return configure_run_logging(results_dir)


def _run_directory(config: dict, ticker: str, trade_date: str, attempt_id: str | None = None) -> Path:
    """One directory per invocation; checkpoint run identity stays independent."""
    component = safe_ticker_component(ticker)
    day = date.fromisoformat(trade_date).isoformat()
    identity = str(UUID(attempt_id)) if attempt_id else str(uuid4())
    return Path(config["results_dir"]) / component / day / (datetime.now().strftime("%H%M%S") + "-" + identity[:8])


def _cleanup_run(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        methods = {name: getattr(message_buffer, name) for name in (
            "add_message", "add_tool_call", "update_report_section")}
        try:
            return function(*args, **kwargs)
        finally:
            for name, method in methods.items():
                setattr(message_buffer, name, method)
            cleanup_run_logging()
    return invoke


def _announce_checkpoint_state(graph, ticker: str, trade_date: str) -> None:
    """Say whether this run resumed a saved one, where the user can see it.

    The graph logs this, but nothing in the CLI configures logging and the live
    view owns the screen, so a resume was invisible.
    """
    if getattr(graph, "_resuming", False):
        message_buffer.add_message(
            "System", f"Resuming the saved run for {ticker} on {trade_date}"
        )
    else:
        message_buffer.add_message("System", f"Starting fresh for {ticker} on {trade_date}")


def _build_run_config(selections: dict, checkpoint: bool | None) -> dict:
    """Assemble the run config from interactive selections, honoring env precedence.

    Round counts and checkpoint follow "explicit env/flag wins": an env-applied
    value on DEFAULT_CONFIG is preserved unless the user overrode it on the CLI.
    """
    config = DEFAULT_CONFIG.copy()
    # Research depth sets both round counts, but an explicit env override
    # (TRADINGAGENTS_MAX_DEBATE_ROUNDS / _MAX_RISK_ROUNDS) wins over the
    # interactive selection — leave the env-applied value in place (#977).
    rounds = (("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "max_debate_rounds"),
              ("TRADINGAGENTS_MAX_RISK_ROUNDS", "max_risk_discuss_rounds"))
    depth_was_asked = not depth_from_env()
    for env_var, key in rounds:
        if not os.environ.get(env_var):
            config[key] = selections["research_depth"]
        elif depth_was_asked:
            # The depth question appeared (it is skipped only when both are
            # set), so say which half of the answer the environment overrode.
            console.print(
                f"[green]✓ {key} from environment:[/green] {config[key]} "
                f"(set by {env_var}, so the research depth you chose does not apply to it)"
            )
    config["quick_think_llm"] = selections["quick_think_llm"]
    config["deep_think_llm"] = selections["deep_think_llm"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    # Provider-specific thinking configuration. Only the main provider's is
    # asked; a tier on another provider keeps its configured value (#1440).
    for key in ("google_thinking_level", "openai_reasoning_effort", "anthropic_effort"):
        if selections.get(key) is not None:
            config[key] = selections[key]
    config["output_language"] = selections.get("output_language", "English")
    # --checkpoint/--no-checkpoint overrides only when explicitly given; omitting
    # the flag preserves TRADINGAGENTS_CHECKPOINT_ENABLED / the default (#976).
    if checkpoint is not None:
        config["checkpoint_enabled"] = checkpoint
    return config


@_cleanup_run
def run_analysis(checkpoint: bool | None = None, portfolio=None, flags=None):
    flags = flags or {}
    # With no terminal nothing can answer a prompt: name every question still
    # open before any model is called, rather than stopping at the first one.
    if not (sys.stdin and sys.stdin.isatty()):
        gaps = unattended_gaps(flags)
        if gaps:
            console.print("[red]No terminal to answer the setup questions. Set:[/red]")
            for gap in gaps:
                console.print(f"  {gap}")
            raise typer.Exit(code=1)

    selections = get_user_selections(flags)

    config = _build_run_config(selections, checkpoint)

    attempt_id = str(uuid4())
    results_dir = _run_directory(config, selections["ticker"], selections["analysis_date"], attempt_id)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_log = _configure_run_logging(results_dir)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)
    stats_handler = StatsCallbackHandler()

    # Normalize analyst selection to predefined order (selection is a 'set', order is fixed)
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]
    analyst_execution_plan = build_analyst_execution_plan(selected_analyst_keys)
    analyst_wall_time_tracker = AnalystWallTimeTracker(analyst_execution_plan)

    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    message_buffer.init_for_analysis(selected_analyst_keys)

    # Track start time for elapsed display
    start_time = time.time()

    def save_message_decorator(obj, func_name):
        func = getattr(obj, func_name)

        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, message_type, content = obj.messages[-1]
            content = content.replace("\n", " ")  # Replace newlines with spaces
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [{message_type}] {content}\n")
        return wrapper

    def save_tool_call_decorator(obj, func_name):
        func = getattr(obj, func_name)

        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, tool_name, args = obj.tool_calls[-1]
            args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\n")
        return wrapper

    def save_report_section_decorator(obj, func_name):
        func = getattr(obj, func_name)

        @wraps(func)
        def wrapper(section_name, content):
            func(section_name, content)
            if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                content = obj.report_sections[section_name]
                if content:
                    file_name = f"{section_name}.md"
                    text = "\n".join(str(item) for item in content) if isinstance(content, list) else content
                    with open(report_dir / file_name, "w", encoding="utf-8") as f:
                        f.write(text)
        return wrapper

    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(message_buffer, "add_tool_call")
    message_buffer.update_report_section = save_report_section_decorator(message_buffer, "update_report_section")

    layout = create_layout()

    # The alternate screen keeps a layout taller than the window from redrawing
    # by scrolling; the final report prints after this block, on the normal screen.
    with Live(layout, refresh_per_second=4, screen=True):
        # Initial display
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        if selections["asset_type"] != "stock":
            message_buffer.add_message("System", f"Detected asset type: {selections['asset_type']}")
        message_buffer.add_message(
            "System", f"Analysis date: {selections['analysis_date']}"
        )
        message_buffer.add_message(
            "System",
            f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}",
        )
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # The analysts start together.
        for spec in analyst_execution_plan.specs:
            message_buffer.update_agent_status(spec.agent_node, "in_progress")
            analyst_wall_time_tracker.mark_started(spec.key)
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        spinner_text = (
            f"Analyzing {selections['ticker']} on {selections['analysis_date']}..."
        )
        update_display(layout, spinner_text, stats_handler=stats_handler, start_time=start_time)

        # The same initial state propagate() builds, with the resolved
        # instrument identity; the graph's Memory Log step settles past
        # decisions and loads their lessons alongside the analysts.
        init_agent_state = graph.create_run_state(
            selections["ticker"], selections["analysis_date"], selections["asset_type"], portfolio
        )
        # Pass callbacks to graph config for tool execution tracking
        # (LLM tracking is handled separately via LLM constructor)
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])

        # Recompile with a checkpointer and inject the thread_id so --checkpoint
        # actually saves and resumes on the CLI path (#1249); a no-op when
        # checkpointing is disabled. Torn down in the finally below.
        checkpoint_tid = graph.begin_checkpoint(
            selections["ticker"], selections["analysis_date"], selections["asset_type"], portfolio
        )
        if checkpoint_tid is not None:
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_tid
            _announce_checkpoint_state(graph, selections["ticker"], selections["analysis_date"])

        # Stream the analysis. On resume, feed None so LangGraph continues the
        # interrupted run instead of re-appending the initial state (#1249); the
        # try/finally tears the checkpointer down even if the stream raises.
        trace = []
        record_attempt_event(config, attempt_id, selections["ticker"], selections["analysis_date"], "started")
        try:
            for messages, chunk in graph.stream_run(graph.checkpoint_input(init_agent_state), **args):
                for message in messages:
                    msg_id = getattr(message, "id", None)
                    if msg_id is not None:
                        if msg_id in message_buffer._processed_message_ids:
                            continue
                        message_buffer._processed_message_ids.add(msg_id)

                    msg_type, content = classify_message_type(message)
                    if content and content.strip():
                        message_buffer.add_message(msg_type, content)

                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            if isinstance(tool_call, dict):
                                message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                            else:
                                message_buffer.add_tool_call(tool_call.name, tool_call.args)

                if chunk is None:   # a step inside an analyst's graph: messages only
                    update_display(layout, stats_handler=stats_handler, start_time=start_time)
                    continue

                update_analyst_statuses(
                    message_buffer,
                    chunk,
                    wall_time_tracker=analyst_wall_time_tracker,
                )

                # Research Team - Handle Investment Debate State
                if chunk.get("investment_debate_state"):
                    debate_state = chunk["investment_debate_state"]
                    bull_hist = debate_state.get("bull_history", "").strip()
                    bear_hist = debate_state.get("bear_history", "").strip()
                    judge = (chunk.get("investment_plan") or "").strip()

                    # Only update status when there's actual content
                    if bull_hist or bear_hist:
                        update_research_team_status("in_progress")
                    if bull_hist:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Bull Researcher Analysis\n{bull_hist}"
                        )
                    if bear_hist:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Bear Researcher Analysis\n{bear_hist}"
                        )
                    if judge:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Research Manager Decision\n{judge}"
                        )
                        update_research_team_status("completed")
                        message_buffer.update_agent_status("Trader", "in_progress")

                # Trading Team
                if chunk.get("trader_investment_plan"):
                    message_buffer.update_report_section(
                        "trader_investment_plan", chunk["trader_investment_plan"]
                    )
                    if message_buffer.agent_status.get("Trader") != "completed":
                        message_buffer.update_agent_status("Trader", "completed")
                        message_buffer.update_agent_status("Aggressive Analyst", "in_progress")

                # Risk Management Team - Handle Risk Debate State
                if chunk.get("risk_debate_state"):
                    risk_state = chunk["risk_debate_state"]
                    agg_hist = risk_state.get("aggressive_history", "").strip()
                    con_hist = risk_state.get("conservative_history", "").strip()
                    neu_hist = risk_state.get("neutral_history", "").strip()
                    judge = (chunk.get("final_trade_decision") or "").strip()

                    if agg_hist:
                        if message_buffer.agent_status.get("Aggressive Analyst") != "completed":
                            message_buffer.update_agent_status("Aggressive Analyst", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Aggressive Analyst Analysis\n{agg_hist}"
                        )
                    if con_hist:
                        if message_buffer.agent_status.get("Conservative Analyst") != "completed":
                            message_buffer.update_agent_status("Conservative Analyst", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Conservative Analyst Analysis\n{con_hist}"
                        )
                    if neu_hist:
                        if message_buffer.agent_status.get("Neutral Analyst") != "completed":
                            message_buffer.update_agent_status("Neutral Analyst", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Neutral Analyst Analysis\n{neu_hist}"
                        )
                    if judge and message_buffer.agent_status.get("Portfolio Manager") != "completed":
                        message_buffer.update_agent_status("Portfolio Manager", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Portfolio Manager Decision\n{judge}"
                        )
                        message_buffer.update_agent_status("Aggressive Analyst", "completed")
                        message_buffer.update_agent_status("Conservative Analyst", "completed")
                        message_buffer.update_agent_status("Neutral Analyst", "completed")
                        message_buffer.update_agent_status("Portfolio Manager", "completed")

                update_display(layout, stats_handler=stats_handler, start_time=start_time)

                trace.append(chunk)

            # Streamed chunks are per-node deltas, not full state. Merge them
            # so every report field populated across the run is present.
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)

            # Clean run: log the decision, then drop this run's checkpoint so a
            # later run starts fresh. A mid-stream failure skips both, keeping
            # the checkpoint for resume.
            graph.record_decision(selections["ticker"], selections["analysis_date"], final_state)
            graph.clear_checkpoint_on_success(
                selections["ticker"], selections["analysis_date"], selections["asset_type"], portfolio
            )
        except BaseException as exc:
            event = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
            record_attempt_event(config, attempt_id, selections["ticker"], selections["analysis_date"], event,
                                 error_type=type(exc).__name__)
            raise
        else:
            record_attempt_event(config, attempt_id, selections["ticker"], selections["analysis_date"], "completed",
                                 decision_id=(final_state.get("publication_record") or {}).get("decision_id"))
        finally:
            # Always restore the plain uncheckpointed graph, even on failure.
            graph.end_checkpoint()

        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message(
            "System", f"Completed analysis for {selections['analysis_date']}"
        )
        message_buffer.add_message("System", analyst_wall_time_tracker.format_summary())

        from tradingagents.reporting import prepare_report_state

        report_state = prepare_report_state(final_state)
        for section in message_buffer.report_sections:
            if section in report_state:
                message_buffer.update_report_section(section, report_state[section])

        update_display(layout, stats_handler=stats_handler, start_time=start_time)

    # Post-analysis prompts (outside Live context for clean interaction)
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")

    console.print(f"Run log: {run_log}", markup=False)
    console.print(render_usage_cost(stats_handler.get_stats(), config), markup=False)

    # A decision nobody can read is not a position. Say so here rather than
    # leaving the run to look like a normal result.
    if is_review(run_rating(final_state)):
        console.print(_review_explanation(final_state), style="yellow", markup=False)

    console.print(f"[dim]{analyst_wall_time_tracker.format_summary()}[/dim]")

    saved = _offer_reports(final_state, graph, selections["ticker"], results_dir=results_dir,
                           save=flags.get("save"), show=flags.get("show"), html=flags.get("html"))
    if saved is False:
        raise typer.Exit(code=1)


def _yes(question: str) -> bool:
    return typer.prompt(question, default="Y").strip().upper() in ("Y", "YES", "")


def _graphical_browser():
    """A browser that opens a page in its own window on this machine, or None.

    Over SSH the page sits on the remote machine, and a terminal browser (lynx,
    w3m, elinks) would take over the terminal, so neither is offered.
    """
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return None
    try:
        browser = webbrowser.get()
    except webbrowser.Error:
        return None
    if type(browser) is webbrowser.GenericBrowser or isinstance(browser, webbrowser.Elinks):
        return None
    return browser


def _open_page(page: Path) -> None:
    """Offer to open the saved page in a browser window, and say where it is if opening fails."""
    browser = _graphical_browser()
    if browser is None or not _yes("Open it in your browser?"):
        return
    try:
        opened = browser.open(page.as_uri())
    except (webbrowser.Error, OSError):
        opened = False
    if not opened:
        console.print(f"  [dim]Could not open a browser; the page is at:[/dim] {page}")


def _resolve_save_path(answer: str, default: Path, results_dir: Path) -> Path:
    cleaned = answer.strip()
    if not cleaned:
        return default
    if cleaned.casefold() in {"y", "yes", "n", "no"} or len(cleaned) < 3:
        raise ValueError("Enter a folder path, not a yes/no answer")
    path = Path(cleaned).expanduser()
    if not path.is_absolute():
        base = (results_dir / "reports").resolve()
        path = (base / path).resolve()
        if not path.is_relative_to(base):
            raise ValueError("Relative save path must remain under this run's reports folder")
    return path


def _prompt_save_path(default, results_dir):
    for _ in range(2):
        answer = typer.prompt("Save path (press Enter for default)", default=str(default))
        try:
            return _resolve_save_path(answer, default, results_dir)
        except ValueError as exc:
            console.print(str(exc), style="yellow", markup=False)
    console.print("Using the default report folder.")
    return default


def _offer_reports(final_state, graph, ticker, save=None, show=None, html=None, results_dir=None):
    """Save once, with one interactive retry; unattended failures never prompt."""
    asked = save is None
    if asked:
        save = _yes("Save report?")
    succeeded = not save
    if save:
        root = Path(results_dir) if results_dir is not None else Path(graph.config["results_dir"])
        default = root / "reports" if results_dir is not None else graph.default_report_path(ticker)
        save_path = _prompt_save_path(default, root) if asked else default
        if html is None:
            html = _yes("Also save it as an HTML page?") if asked else True
        for attempt in range(2 if asked else 1):
            try:
                report_file = graph.save_reports(final_state, ticker, save_path, html=html)
                succeeded = True
                console.print("\nReport saved to: " + str(save_path.resolve()), style="green", markup=False)
                console.print("Complete report: " + report_file.name, markup=False)
                break
            except Exception as exc:
                logger.warning("Report save failed", exc_info=True)
                console.print(f"Report save failed ({type(exc).__name__}).", style="red", markup=False)
                if attempt or not asked or not _yes("Retry saving to a new folder?"):
                    break
                failed_path = save_path.resolve()
                retry_default = default.with_name(default.name + "-retry")
                if retry_default.resolve() == failed_path:
                    retry_default = default.with_name(default.name + "-retry-" + uuid4().hex[:8])
                save_path = _prompt_save_path(retry_default, root)
                if save_path.resolve() == failed_path:
                    console.print("Using a different retry folder.")
                    save_path = retry_default
        if succeeded and html:
            page = (save_path / "complete_report.html").resolve()
            console.print("HTML report: " + page.name, markup=False)
            if asked:
                _open_page(page)
    if show is None:
        show = _yes("\nDisplay full report on screen?")
    if show:
        display_complete_report(final_state)
    return succeeded


def _review_explanation(final_state: dict) -> str:
    from tradingagents.agents.rating import normalized_evidence_quality

    quality = normalized_evidence_quality(final_state)
    if quality.get("status") == "insufficient":
        reasons = [check["message"] for check in quality.get("checks", []) if check.get("status") in {"fail", "unavailable"} and check.get("message")]
        return "Research incomplete — REVIEW. No trading decision was added to memory.\n" + "\n".join("- " + reason for reason in dict.fromkeys(reasons))
    return "No rating could be read from the final decision. Research is retained for review; no trading decision was added to memory.\n"

```


## `cli/run_logging.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `81dcad95822e8b71ea7b56868179b8257637841fd15eb53593ed59610494cb7c`.

```python
"""A replaceable, sanitized warning log for one analysis attempt."""

import logging
import traceback
from pathlib import Path

_owned_handler: logging.FileHandler | None = None
_previous_root_level: int | None = None


class _RunLogFilter(logging.Filter):
    """Keep third-party SDK diagnostics out of the run log."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "root" or record.name == "cli" or record.name.startswith(
            "cli."
        ) or record.name == "tradingagents" or record.name.startswith("tradingagents.")


class _SafeRunFormatter(logging.Formatter):
    """Retain event text and stack location, never exception details or values."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.msg if isinstance(record.msg, str) else type(record.msg).__name__
        if record.args:
            # Log templates are app-owned; arguments may contain provider payloads.
            # Keep their types for diagnosis without evaluating __str__/__repr__.
            args = record.args.values() if isinstance(record.args, dict) else record.args
            message += " [arg types: " + ", ".join(type(arg).__name__ for arg in args) + "]"
        timestamp = self.formatTime(record, self.datefmt)
        rendered = f"{timestamp} {record.levelname} {record.name}: {message}"
        if record.exc_info:
            exc_type, _, tb = record.exc_info
            rendered += "\nTraceback (most recent call last):"
            for frame in traceback.extract_tb(tb):
                rendered += f'\n  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
            rendered += f"\n{exc_type.__name__ if exc_type else 'Exception'}"
        return rendered


def cleanup_run_logging() -> None:
    """Remove only this module's file handler and restore the root level."""
    global _owned_handler, _previous_root_level
    root = logging.getLogger()
    if _owned_handler is not None:
        root.removeHandler(_owned_handler)
        _owned_handler.close()
        _owned_handler = None
    if _previous_root_level is not None:
        root.setLevel(_previous_root_level)
        _previous_root_level = None


def configure_run_logging(results_dir: Path) -> Path:
    """Install a WARNING log at ``results_dir/run.log`` for the current run."""
    global _owned_handler, _previous_root_level
    cleanup_run_logging()
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "run.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.WARNING)
    handler.addFilter(_RunLogFilter())
    handler.setFormatter(_SafeRunFormatter())
    root = logging.getLogger()
    _previous_root_level = root.level
    if root.level > logging.WARNING:
        root.setLevel(logging.WARNING)
    root.addHandler(handler)
    _owned_handler = handler
    return path

```


## `cli/stats_handler.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `4730905c4d03784cac0cca4c8a8df49c42f62561aad15be5bc528d5f880fc6b4`.

```python
import threading
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult


class StatsCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks LLM calls, tool calls, and token usage."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.token_usage_calls = 0
        self.token_usage_missing = 0

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when an LLM starts."""
        with self._lock:
            self.llm_calls += 1

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when a chat model starts."""
        with self._lock:
            self.llm_calls += 1

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token usage from LLM response."""
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return

        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata

        valid = (isinstance(usage_metadata, dict) and
                 all(type(usage_metadata.get(key)) is int and usage_metadata[key] >= 0
                     for key in ("input_tokens", "output_tokens")))
        with self._lock:
            if valid:
                self.tokens_in += usage_metadata["input_tokens"]
                self.tokens_out += usage_metadata["output_tokens"]
                self.token_usage_calls += 1
            else:
                self.token_usage_missing += 1

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Increment tool call counter when a tool starts."""
        with self._lock:
            self.tool_calls += 1

    def get_stats(self) -> dict[str, Any]:
        """Return current statistics."""
        with self._lock:
            scope = ("complete_observed" if self.token_usage_calls > 0
                     and self.token_usage_calls == self.llm_calls and self.token_usage_missing == 0
                     else "partial_observed" if self.token_usage_calls > 0 else "unavailable")
            return {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "token_usage_calls": self.token_usage_calls,
                "token_usage_missing": self.token_usage_missing,
                "token_usage_scope": scope,
            }


def _valid_price(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return price if price.is_finite() and price >= 0 else None


def render_usage_cost(stats: dict, config: dict) -> str:
    """One CLI usage line, with an optional estimate for observed tokens only."""
    scope = stats.get("token_usage_scope")
    count_in, count_out = stats.get("tokens_in"), stats.get("tokens_out")
    if scope not in {"complete_observed", "partial_observed"} or any(
        type(value) is not int or value < 0 for value in (count_in, count_out)
    ):
        return "Tokens: unavailable (usage was not observed)"

    coverage = "complete observed" if scope == "complete_observed" else "partial observed"
    line = f"Tokens: {count_in:,} in / {count_out:,} out ({coverage})"
    input_price = _valid_price(config.get("input_cost_per_million"))
    output_price = _valid_price(config.get("output_cost_per_million"))
    if input_price is None or output_price is None:
        return line
    try:
        cost = (Decimal(count_in) * input_price + Decimal(count_out) * output_price) / 1_000_000
    except DecimalException:
        return line
    scope_note = "observed tokens only; not the whole run or a billing total" if scope == "partial_observed" else (
        "observed tokens only; not a billing total"
    )
    return f"{line}\nEstimated cost at configured prices: ${cost:.6f} ({scope_note})"

```


## `cli/updates.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `5f310940ea1cb33889114cea1baf6c29d28a33341155a101790e2c6f90dfece6`.

```python
"""What's new, for the person at the terminal: a newer release, and notices from Tauric Research.

At most once a day a background thread asks GitHub for the latest release and
the announcements server for notices, and writes the answers to a small cache.
The lines shown at start-up are read from that cache, so a run never waits on
the network and news shows up on the next run. Nothing identifying is sent.
Unattended, scripted and CI runs contact no server; set
TRADINGAGENTS_NO_UPDATE_CHECK=1 to turn the check off.
"""

import importlib.metadata
import json
import os
import re
import shlex
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from packaging.version import InvalidVersion, Version

from tradingagents.dataflows.files import replace_file
from tradingagents.default_config import _TRADINGAGENTS_HOME, _coerce

RELEASES_URL = "https://api.github.com/repos/TauricResearch/TradingAgents/releases/latest"
NOTICES_URL = "https://api.tauric.ai/v1/announcements"
CACHE = Path(_TRADINGAGENTS_HOME) / "update_check.json"
CHECK_EVERY = 24 * 3600
TIMEOUT = 2.0
SUMMARY_LIMIT = 160
OPT_OUT = "TRADINGAGENTS_NO_UPDATE_CHECK"
# Control characters, C0 and C1, read as spaces; invisible spaces and direction marks are dropped.
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
INVISIBLE = re.compile(r"[\u061c\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def enabled() -> bool:
    """Whether a person is at the terminal and has not turned the check off."""
    at_a_terminal = bool(sys.stdin and sys.stdin.isatty() and sys.stdout and sys.stdout.isatty())
    try:
        opted_out = _coerce(os.environ.get(OPT_OUT, "0"), False)
    except ValueError:
        opted_out = True  # an invalid opt-out value never starts a network check
    return at_a_terminal and not os.environ.get("CI") and not opted_out


# --- the cache and the check -------------------------------------------------------

def read_cache() -> dict:
    """The cache, keeping only fields of the shape this version writes."""
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    shapes = {"checked_at": (int, float), "latest": dict, "notices": list}
    return {key: data[key] for key, shape in shapes.items() if isinstance(data.get(key), shape)}


def due(cache: dict, now: float) -> bool:
    checked = cache.get("checked_at")
    return not isinstance(checked, (int, float)) or not 0 <= now - checked < CHECK_EVERY


def summary_of(body: str) -> str:
    """The release's one-line summary: its first paragraph on one line (sanitised when shown)."""
    first = re.split(r"\n\s*\n", (body or "").strip(), maxsplit=1)[0]
    text = " ".join(first.split())
    if len(text) > SUMMARY_LIMIT:
        text = text[: SUMMARY_LIMIT - 3].rsplit(" ", 1)[0] + "..."
    return text


def parse_notices(payload) -> list | None:
    """The targeted notices in an announcements answer; None when it has no notices list."""
    notices = payload.get("notices") if isinstance(payload, dict) else None
    return notices if isinstance(notices, list) else None


def _get_json(url: str):
    response = requests.get(url, timeout=TIMEOUT)
    return response.json() if response.ok else None


def refresh(now: float | None = None) -> None:
    """Ask for the latest release and notices and record the answers. Never raises or prints;
    a failed check keeps what was known and is not retried for a day."""
    now = time.time() if now is None else now
    cache = read_cache()
    cache["checked_at"] = now
    try:
        release = _get_json(RELEASES_URL)
        if isinstance(release, dict) and release.get("tag_name"):
            cache["latest"] = {
                "version": str(release["tag_name"]).removeprefix("v"),
                "url": release.get("html_url"),
                "summary": summary_of(release.get("body") or ""),
            }
    except Exception:
        pass
    try:
        notices = parse_notices(_get_json(NOTICES_URL))
        if notices is not None:
            cache["notices"] = notices
    except Exception:
        pass
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        replace_file(CACHE, lambda temp: Path(temp).write_text(json.dumps(cache), encoding="utf-8"))
    except Exception:
        pass


def start_background_refresh() -> None:
    """Refresh the cache in a daemon thread when a check is due."""
    if due(read_cache(), time.time()):
        threading.Thread(target=refresh, name="tradingagents-update-check", daemon=True).start()


# --- what is shown ---------------------------------------------------------------

def _version(text) -> Version | None:
    try:
        return Version(str(text))
    except (InvalidVersion, TypeError):
        return None


def _plain(text) -> str:
    return " ".join(CONTROL.sub(" ", INVISIBLE.sub("", str(text or ""))).split())


def _applies(notice: dict, running: Version, today: date) -> bool:
    """Whether a notice is for this version and unexpired; a bound or date that cannot be read
    keeps it hidden. A notice is shown through its ``expires`` date (UTC)."""
    low, high = notice.get("min_version"), notice.get("max_version")
    if low is not None and ((floor := _version(low)) is None or running < floor):
        return False
    if high is not None and ((ceiling := _version(high)) is None or running > ceiling):
        return False
    expires = notice.get("expires")
    if expires is None:
        return True
    try:
        return isinstance(expires, str) and bool(DATE.fullmatch(expires)) and date.fromisoformat(expires) >= today
    except ValueError:
        return False


def messages(cache: dict, running: str, upgrade: Callable[[], str | None] = lambda: None) -> list[str]:
    """The lines to show: a newer release with its upgrade command (``upgrade()``, asked only
    when there is one), then the notices for this version."""
    current = _version(running)
    if current is None:
        return []
    lines = []
    latest = cache.get("latest") or {}
    newest = _version(latest.get("version"))
    if newest is not None and newest > current:
        lines.append(f"TradingAgents {_plain(latest['version'])} is available (you have {_plain(running)}): "
                     f"{_plain(latest.get('summary'))}")
        if latest.get("url"):
            lines.append(_plain(latest["url"]))
        command = upgrade()
        if command:
            lines.append(f"Upgrade: {_plain(command)}")
    today = datetime.now(UTC).date()
    for notice in cache.get("notices") or []:
        if not (isinstance(notice, dict) and isinstance(notice.get("message"), str) and _plain(notice["message"])
                and _applies(notice, current, today)):
            continue
        url = notice.get("url")
        link = url if isinstance(url, str) and url.lower().startswith(("http://", "https://")) else None
        lines.append(_plain(notice["message"]) + (f" {_plain(link)}" if link else ""))
    return lines


def upgrade_command(dist=None) -> str | None:
    """The command that upgrades this install, from how pip or uv recorded it; None when unsure."""
    if os.environ.get("TRADINGAGENTS_IN_DOCKER"):
        return "git pull && docker compose build (on the host)"
    if os.name == "nt":                    # the commands below are POSIX shell
        return None
    try:
        dist = dist or importlib.metadata.distribution("tradingagents")
        direct = json.loads(dist.read_text("direct_url.json") or "null")
        installer = (dist.read_text("INSTALLER") or "").strip()
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        return None
    if not isinstance(direct, dict) or not direct.get("url"):
        return None
    python = shlex.quote(sys.executable)
    install = f"uv pip install --python {python}" if installer == "uv" else f"{python} -m pip install"
    if "vcs_info" in direct:
        return f"{install} -U git+{direct['url']}"
    parsed = urlparse(direct["url"])
    if parsed.scheme != "file":
        return None
    clone = Path(unquote(parsed.path))
    if not (clone / ".git").exists():
        return None
    editable = (direct.get("dir_info") or {}).get("editable")
    target = shlex.quote(str(clone))
    return f"git -C {target} pull && {install} {'-e ' if editable else ''}{target}"


def show(console) -> None:
    """Print what's new from the cache, under the welcome panel."""
    from rich.panel import Panel
    from rich.text import Text

    from tradingagents import __version__

    lines = messages(read_cache(), running=__version__, upgrade=upgrade_command)
    if lines:
        console.print(Panel(Text("\n".join(lines)), border_style="cyan", padding=(1, 2), title="What's new"))
        console.print()

```


## `tradingagents/dataflows/router.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `46a44126c07bf2eefa3fbb9bac305b3cd38a022eb4405633142d46cd560e9cc0`.

```python
import logging
import re

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors.alpha_vantage import (
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_global_news as get_alpha_vantage_global_news,
    get_income_statement as get_alpha_vantage_income_statement,
    get_indicator as get_alpha_vantage_indicator,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_stock as get_alpha_vantage_stock,
)
from tradingagents.dataflows.vendors.fred import get_macro_data as get_fred_macro_data
from tradingagents.dataflows.vendors.polymarket import (
    get_prediction_markets as get_polymarket_prediction_markets,
)
from tradingagents.dataflows.vendors.sec_edgar import (
    get_balance_sheet as get_sec_edgar_balance_sheet,
    get_cashflow as get_sec_edgar_cashflow,
    get_income_statement as get_sec_edgar_income_statement,
)
from tradingagents.dataflows.vendors.yahoo.fundamentals import (
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_fundamentals as get_yfinance_fundamentals,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from tradingagents.dataflows.vendors.yahoo.market import (
    get_stock_stats_indicators_window,
    get_YFin_data_online,
)
from tradingagents.dataflows.vendors.yahoo.news import get_global_news_yfinance, get_news_yfinance
from tradingagents.operational_capture import record_operation

logger = logging.getLogger(__name__)

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    "macro_data": {
        "description": "Macroeconomic indicators (rates, inflation, labor, growth)",
        "tools": [
            "get_macro_indicators",
        ]
    },
    "prediction_markets": {
        "description": "Market-implied probabilities for forward-looking events",
        "tools": [
            "get_prediction_markets",
        ]
    }
}

# Optional enrichment categories. These add macro/event context to the news
# analyst but are not core to a decision, so a vendor failure here degrades to a
# sentinel instead of aborting the run (a bad LLM-supplied indicator, a missing
# key, or a network blip should not crash an analysis over flavour data). Core
# categories (prices, fundamentals, news) still raise so a broken primary is loud.
OPTIONAL_CATEGORIES = {"macro_data", "prediction_markets"}

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "sec_edgar": get_sec_edgar_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "sec_edgar": get_sec_edgar_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "sec_edgar": get_sec_edgar_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # macro_data
    "get_macro_indicators": {
        "fred": get_fred_macro_data,
    },
    # prediction_markets
    "get_prediction_markets": {
        "polymarket": get_polymarket_prediction_markets,
    },
}


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")


def vendor_unavailable(method: str, error: Exception) -> str:
    """What a call returns when every vendor was throttled or unreachable."""
    safe_reasons = {
        "retained_scope_mismatch": "Requested issuer or cutoff differs from retained source evidence; no replacement vintage was fetched.",
        "retained_source_unavailable": "Retained SEC unavailable; no replacement vintage was fetched.",
        "retained_filing_unavailable": "Retained SEC filing evidence unavailable; no replacement vintage was fetched.",
        "retained_integrity_unavailable": "Retained financial source integrity is unavailable; no replacement vintage was fetched.",
        "retained_package_invalid": "Retained source package invalid or unavailable; no replacement vintage was fetched.",
    }
    reason = safe_reasons.get(getattr(error, "reason_code", None), "")
    return (
        f"DATA_UNAVAILABLE: configured vendor unreachable or unavailable for {method} right now "
        f"({type(error).__name__}). {reason} This says nothing about the instrument; report the "
        f"data as unavailable and do not estimate or fabricate values."
    )


def no_data_available(error: NoMarketDataError) -> str:
    """What a call returns when every vendor that answered had no usable data."""
    resolved = "" if error.canonical == error.symbol else f" (resolved to '{error.canonical}')"
    # Only known, locally constructed no-data explanations reach the model.
    # Arbitrary vendor detail can be an exception payload or credential.
    fixed = {
        "no rows", "not covered", "not a US SEC filer", "US filer with no us-gaap facts",
        "no price rows", "no fundamentals", "no fundamental fields",
        "no Balance Sheet data", "no Cash Flow data", "no Income Statement data",
        "invalid nonempty closing price in source data",
        "no completed price rows at the observation cutoff",
        "no bar in range has a closing price",
        "Historical adjustment basis unavailable beyond 400-day verification bound",
        "Historical adjustment basis is not compatible with the analysis cutoff",
        "Historical adjustment basis verification unavailable",
    }
    dated = (
        r"no price rows on or before \d{4}-\d{2}-\d{2}",
        r"no completed rows between \d{4}-\d{2}-\d{2} and \d{4}-\d{2}-\d{2}",
        r"no (?:annual|quarterly) (?:balance sheet|income statement|cash flow statement) filed by \d{4}-\d{2}-\d{2}",
        r"no statement evidence filed by \d{4}-\d{2}-\d{2}",
        r"latest row is \d{4}-\d{2}-\d{2}, \d+ days before the requested \d{4}-\d{2}-\d{2} "
        r"\(stale\) — refusing to use it",
    )
    detail = error.detail
    safe_detail = detail in fixed or (error.__cause__ is None and len(detail) <= 300
                                      and any(re.fullmatch(pattern, detail) for pattern in dated))
    if error.__cause__ is not None and detail != "Historical adjustment basis verification unavailable":
        safe_detail = False
    reason = f" ({detail})" if safe_detail else ""
    return (
        f"NO_DATA_AVAILABLE: No usable market data for '{error.symbol}'{resolved} from "
        f"any configured vendor{reason}. The symbol may be invalid, delisted, "
        f"not covered, or the vendor returned stale data. Do not estimate or "
        f"fabricate values — report that data is unavailable for this symbol."
    )


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available_vendors = list(VENDOR_METHODS[method].keys())

    # The configured vendor list IS the chain: we do NOT silently fall back to
    # vendors the user did not choose (#988/#289) — that returned data from an
    # unexpected source and caused cross-vendor inconsistencies. For multi-vendor
    # fallback, list them in order, e.g. data_vendors="yfinance,alpha_vantage".
    # The "default" sentinel (no explicit config) uses all available vendors.
    explicit = [v for v in primary_vendors if v and v != "default"]
    if explicit:
        vendor_chain = [v for v in explicit if v in VENDOR_METHODS[method]]
        if not vendor_chain:
            raise ValueError(
                f"Configured vendor(s) {explicit} not available for '{method}'. "
                f"Available: {all_available_vendors}."
            )
    else:
        vendor_chain = all_available_vendors

    last_no_data: NoMarketDataError | None = None
    last_unavailable: VendorUnavailableError | None = None
    failed: Exception | None = None     # a vendor that raised something untyped
    first_error: Exception | None = None
    failed_vendors = []
    for vendor in vendor_chain:
        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            value = impl_func(*args, **kwargs)
            if failed_vendors:
                record_operation('vendor_fallback_recovered', scope=f'{method} via {vendor} after {" ".join(failed_vendors)}')
            return value
        except VendorUnavailableError as e:
            failed_vendors.append(vendor)
            logger.warning("Vendor %r unavailable for %s: %s; trying next vendor.", vendor, method, type(e).__name__)
            # Kept so an all-unavailable chain can say the vendor was the
            # problem, rather than reporting nothing about the symbol.
            last_unavailable = e
            continue
        except VendorNotConfiguredError as e:
            # Default discovery may include optional providers without credentials.
            # An explicitly selected provider is expected to be configured.
            if explicit:
                failed_vendors.append(vendor)
            logger.warning("Vendor %r not configured for %s; trying next vendor.", vendor, method)
            if first_error is None:
                first_error = e  # Surface it if no other vendor can serve the call.
            continue
        except NoMarketDataError as e:
            last_no_data = e  # No data here; another configured vendor may have it
            continue
        except Exception as e:
            failed_vendors.append(vendor)
            # Don't let one vendor's failure crash the call when another can
            # serve it, but never swallow silently: a broken primary must be
            # visible in the logs (#989), not hidden behind a fallback's verdict.
            logger.warning("Vendor %r failed for %s: %s", vendor, method, type(e).__name__)
            if first_error is None:
                first_error = e
            failed = e
            continue

    if not failed_vendors and isinstance(first_error, VendorNotConfiguredError):
        record_operation('vendor_unavailable', scope=method)
    if failed_vendors:
        record_operation('vendor_unavailable', scope=f'{method} {" ".join(failed_vendors)}')
    elif last_no_data is not None:
        record_operation('vendor_no_data', scope=method)

    # A vendor that throttled or failed the request never said whether it has
    # the symbol, so no other vendor's "no data" can speak for the whole chain:
    # report the vendors as the problem, not the instrument. It must not end
    # the run either.
    if last_unavailable is not None:
        return vendor_unavailable(method, last_unavailable)
    if failed is not None and last_no_data is not None:
        return vendor_unavailable(method, failed)

    # Every vendor that answered reported "no data": the symbol is genuinely unavailable.
    # Return one explicit, instructive sentinel rather than a vendor-specific
    # empty string, so the agent reports "unavailable" instead of inventing a
    # value. This takes precedence over incidental fallback errors.
    if last_no_data is not None:
        if first_error is not None:
            # A vendor also hit a real error; surface it in logs so the no-data
            # verdict can't hide a broken primary (network/auth/etc.).
            logger.warning(
                "Returning NO_DATA for %s, but a vendor errored earlier: %s",
                method, type(first_error).__name__,
            )
        return no_data_available(last_no_data)

    # No vendor returned data and none reported clean "no data" — surface the
    # first real error (e.g. the primary vendor's network failure). Optional
    # enrichment categories degrade to a sentinel instead, so flavour data can't
    # abort the run.
    if first_error is not None:
        if category in OPTIONAL_CATEGORIES:
            logger.warning("Optional %s unavailable for %s: %s", category, method, type(first_error).__name__)
            return (
                f"DATA_UNAVAILABLE: optional {category} could not be retrieved "
                f"({type(first_error).__name__}). Proceed without it; do not fabricate values."
            )
        raise first_error

    raise RuntimeError(f"No available vendor for '{method}'")

```


## `tradingagents/dataflows/errors.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `aaff347711d4f6452d17bd58193a5d71bf8af9a20dfe8378758e7d0c5b45b51d`.

```python
"""Vendor data-error taxonomy.

A single hierarchy so the routing layer reacts by *behavior*, not by vendor:
every condition where a vendor cannot return usable data derives from
``VendorError``, and the router catches the base types. A new vendor raises
these (or a thin vendor-named subclass) and needs no new ``except`` clause.

    VendorError
    ├── NoMarketDataError          no usable rows (empty result OR stale data)
    ├── VendorUnavailableError     throttled or failed request -> skip to next vendor
    └── VendorNotConfiguredError   missing API key/config -> vendor unavailable

The number of types is the number of distinct router reactions, not the number
of human-describable causes: empty and stale data get identical handling, so
they share ``NoMarketDataError`` and differ only in the free-text ``detail``.
"""

from __future__ import annotations


class VendorError(Exception):
    """Base for any condition where a vendor could not return usable data."""


class NoMarketDataError(VendorError):
    """A vendor returned no usable rows for a symbol (empty result or stale data).

    Carries both the symbol the user requested and the canonical symbol the
    vendor was actually queried with, plus a free-text ``detail``, so callers
    can build a clear message instead of emitting a vendor-specific empty
    string into the data channel.
    """

    def __init__(self, symbol: str, canonical: str | None = None, detail: str = ""):
        self.symbol = symbol
        self.canonical = canonical or symbol
        self.detail = detail
        msg = f"No market data for {symbol!r}"
        if canonical and canonical != symbol:
            msg += f" (queried as {canonical!r})"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class VendorUnavailableError(VendorError):
    """A vendor could not answer: it throttled or failed the request.

    Says nothing about the instrument; the router skips to the next vendor.
    """

    def __init__(self, message: str = "", *, reason_code: str | None = None):
        super().__init__(message)
        self.reason_code = reason_code


class VendorNotConfiguredError(VendorError, ValueError):
    """A vendor was selected but its API key/configuration is missing.

    Also a ``ValueError`` so existing callers that catch ``ValueError`` keep
    working while the routing layer can treat it as "vendor unavailable".
    """

```


## `tradingagents/dataflows/vendors/yahoo/ohlcv.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `03dd8e8ef1e8ca050e58aa21207d409e5f60df9ee07fd2217edf5e7655e81c59`.

```python
import hashlib
import json
import logging
import os
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component
from tradingagents.dataflows.vendors.yahoo.common import raise_for_empty, yf_retry
from tradingagents.dataflows.vendors.yahoo.price_observation import (
    ADJUSTMENT,
    _number,
    _timestamp,
    session_is_complete,
)

_SOURCE_COLUMN = "__market_source"

logger = logging.getLogger(__name__)

# A vendor's latest OHLCV row this many calendar days before the requested date
# is treated as stale. Generous enough to span long holiday weekends, tight
# enough to catch the year-old frames yfinance occasionally returns (#1021).
MAX_OHLCV_STALE_DAYS = 10

# How long a same-day cache that does not yet reach the requested day may be
# reused before it is refetched (#1150). Short enough that an intraday run picks
# up today's close soon after it publishes, long enough that a day with no bar
# at all (weekend, holiday) cannot trigger a download on every call.
OHLCV_CACHE_TTL_SECONDS = 900


def _retrieval_time():
    from tradingagents.dataflows.vendors.yahoo.price_observation import _now
    return _now()


def _source_metadata(source, downloaded, canonical, retrieved):
    method = getattr(source, "get_history_metadata", None)
    metadata = method() if method is not None else {}
    metadata = metadata if isinstance(metadata, Mapping) else {}
    zone = metadata.get("exchangeTimezoneName") or str(getattr(downloaded.index, "tz", "") or "")
    end = metadata.get("currentTradingPeriod", {}).get("regular", {}).get("end")
    return {
        "ticker": canonical,
        "retrieved_at": retrieved.isoformat(),
        "exchange_timezone": zone or None,
        "currency": metadata.get("currency"),
        "regular_end": _timestamp(end).isoformat() if end is not None else None,
        "adjustment_basis": ADJUSTMENT,
        "actions_requested": True,
        "source_id": "yahoo-ohlcv-" + hashlib.sha256(
            (canonical + retrieved.isoformat() + downloaded.to_csv()).encode()
        ).hexdigest(),
    }


def market_provenance_lines(data):
    source = data.attrs.get("market_provenance") or {}
    if not source:
        return ["- Session provenance unavailable."]
    historical = source.get("analysis_date", "9999") < source["retrieved_at"][:10]
    timing = (["- Retrospective retrieval; timestamps retained with the source, not as-of research facts."]
              if historical else [
                  f"- Retrieved at: {source['retrieved_at']}",
                  f"- Observation cutoff: {source.get('observation_cutoff') or source['retrieved_at']}",
              ])
    return [
        "- Session status: completed; unfinished daily rows excluded before calculation.",
        f"- Completed session: {source.get('session_date', 'unavailable')}",
        f"- Exchange timezone: {source.get('exchange_timezone') or 'unknown'}",
        f"- Currency: {source.get('currency') or 'unknown'}",
        *timing,
        *([f"- Price fallback: {source['price_fallback']['reason']}; "
           f"latest completed session {source['price_fallback']['latest_completed_session_date']}; "
           f"selected session {source['price_fallback']['selected_session_date']}."]
          if source.get("price_fallback") else []),
        f"- Adjustment basis: {source['adjustment_basis']}",
        f"- Source: {source['source_id']}",
        "- A completed close is a dated observation, not an executable quote.",
    ]


def _ensure_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize the date column to ``Date``.

    Some yfinance builds leave the index unnamed (so ``reset_index()`` yields
    ``index``) or use ``Datetime`` for intraday data. Rename the first
    date-like column so indicators don't silently drop when it isn't ``Date``.
    """
    if "Date" in data.columns:
        return data
    for candidate in ("index", "Datetime", "date"):
        if candidate in data.columns:
            return data.rename(columns={candidate: "Date"})
    return data


def _local_midnight(value) -> pd.Timestamp:
    """A single timestamp as its naive, midnight-normalized local date (or NaT)."""
    if pd.isna(value):
        return pd.NaT
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return pd.NaT
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)  # drop tz, keep the local wall-clock date
    return ts.normalize()


def _normalize_dates(dates) -> pd.Series:
    """Parse to naive, midnight-normalized dates so tz-aware or intraday
    timestamps compare correctly against the naive ``as_of_date`` cutoff (#1201).

    Normalized per element: 5 years of yfinance bars span daylight-saving
    changes (and cache CSVs round-trip the offsets as strings), so the series can
    carry mixed UTC offsets that ``pd.to_datetime`` cannot unify without
    ``utc=True`` — which would shift non-US (positive-offset) markets to the
    previous day. Keeping each bar's own local date avoids both.
    """
    return pd.to_datetime(pd.Series(dates).map(_local_midnight))


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse/normalize dates and
    coerce prices to numeric (NaN where invalid). Dropping incomplete rows and
    filling gaps is left to ``_fill_price_gaps`` so the caller can first inspect
    the latest in-range bar (#1201)."""
    data = _ensure_date_column(data)
    data["Date"] = _normalize_dates(data["Date"])
    data = data.dropna(subset=["Date"]).copy()

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    return data


def _validate_close_values(data, symbol, canonical):
    """Do not reinterpret corrupt nonempty closes as missing-price fallbacks."""
    raw = data["Close"]
    missing = raw.map(lambda value: pd.isna(value) or isinstance(value, str) and not value.strip())
    numeric = pd.to_numeric(raw, errors="coerce")
    invalid = ~missing & (
        numeric.isna() | numeric.le(0) | numeric.isin([float("inf"), float("-inf")])
        | raw.map(lambda value: isinstance(value, bool))
    )
    if invalid.any():
        raise NoMarketDataError(symbol, canonical, "invalid nonempty closing price in source data")


def _fill_price_gaps(data: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with no close and forward/back-fill remaining price gaps so
    indicators compute on a continuous series."""
    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    # copy() so a filtered (sliced) input is written to safely, not via a view.
    data = data.dropna(subset=["Close"]).copy()
    data[price_cols] = data[price_cols].ffill().bfill()
    return data


def _coerce_ohlcv_dates(data: pd.DataFrame) -> pd.Series:
    """Return parsed dates from an OHLCV frame, whether Date is a column or the index."""
    if "Date" in data.columns:
        return pd.to_datetime(data["Date"], errors="coerce").dropna()
    # yfinance keeps the dates in the index (a DatetimeIndex, sometimes unnamed).
    if isinstance(data.index, pd.DatetimeIndex):
        return pd.Series(pd.to_datetime(data.index, errors="coerce")).dropna()
    # Fallback: expose the index and look for any date-like column.
    df = data.reset_index()
    for col in ("Date", "Datetime", "date", "index"):
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce").dropna()
            if not parsed.empty:
                return parsed
    return pd.Series(dtype="datetime64[ns]")


def _assert_ohlcv_not_stale(
    data: pd.DataFrame,
    as_of_date: str,
    symbol: str,
    canonical: str | None = None,
    *,
    max_stale_days: int = MAX_OHLCV_STALE_DAYS,
) -> None:
    """Reject OHLCV whose latest row is far older than as_of_date.

    Raises NoMarketDataError (with a stale-specific detail) so the router treats
    it like any other "no usable data from this vendor" — try the next vendor,
    then emit one clear unavailable signal. Empty frames are left to the
    caller's existing no-data handling; this guards only the dangerous case of
    present-but-stale rows (a vendor returning a year-old frame that would
    otherwise feed wrong prices to the agent, #1021).
    """
    if data is None or data.empty:
        return
    requested = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(requested):
        return
    requested = requested.normalize()
    dates = _coerce_ohlcv_dates(data)
    if dates.empty:
        return
    latest = dates.max().normalize()
    stale_days = (requested - latest).days
    if stale_days > max_stale_days:
        raise NoMarketDataError(
            symbol,
            canonical,
            f"latest row is {latest.date()}, {stale_days} days before the "
            f"requested {requested.date()} (stale) — refusing to use it",
        )


def _cache_is_fresh(data_file, as_of_dt, now) -> bool:
    """Whether the symbol's cached download can serve this request.

    The file holds the download made on the day it was written, so it serves
    only that day. A current-day request also refetches once the file is older
    than the TTL: Yahoo publishes a partial daily candle during market hours,
    whose ``Close`` is not the closing price, and row inspection cannot tell it
    from a final one (#1150).
    """
    written = pd.Timestamp.fromtimestamp(os.path.getmtime(data_file))
    if written.date() != now.date():
        return False
    return as_of_dt.date() < now.date() or (now - written).total_seconds() <= OHLCV_CACHE_TTL_SECONDS


def _verify_historical_adjustment(data, metadata, as_of_dt, symbol, canonical):
    """Inspect the full retrieved action window before historical rows are hidden."""
    unavailable = "Historical adjustment basis verification unavailable"
    try:
        zone = ZoneInfo(metadata["exchange_timezone"])
        today = _timestamp(metadata["retrieved_at"]).astimezone(zone).date()
        cutoff = as_of_dt.date()
        if cutoff >= today:
            return
        if (today - cutoff).days > 400:
            raise NoMarketDataError(
                symbol, canonical,
                "Historical adjustment basis unavailable beyond 400-day verification bound",
            )
        if metadata.get("actions_requested") is not True or "Stock Splits" not in data:
            raise ValueError("missing verified split actions")
        start = max(cutoff - timedelta(days=7), today - timedelta(days=400))
        sessions = set()
        for _, row in _ensure_date_column(data).iterrows():
            session = _local_midnight(row["Date"])
            if pd.isna(session) or session.date() > today:
                raise ValueError("invalid action verification window")
            if session.date() < start:
                continue
            if session.date() in sessions:
                raise ValueError("duplicate action verification session")
            sessions.add(session.date())
            ratio = _number(row["Stock Splits"])
            if session.date() > cutoff and Decimal(ratio) != 0:
                raise NoMarketDataError(
                    symbol, canonical,
                    "Historical adjustment basis is not compatible with the analysis cutoff",
                )
        if not sessions or min(sessions) > cutoff or (today - max(sessions)).days > 7:
            raise ValueError("insufficient action verification coverage")
    except NoMarketDataError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, ZoneInfoNotFoundError) as exc:
        raise NoMarketDataError(symbol, canonical, unavailable) from exc


def load_ohlcv(symbol: str, as_of_date: str, fill_gaps: bool = True) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads 5 years of data up to today and caches per symbol. On
    subsequent calls the cache is reused. Rows after as_of_date are
    filtered out so backtests never see future prices.

    ``fill_gaps`` carries prices forward over gaps so indicators compute on a
    continuous series. Pass ``False`` to read the values as the vendor reported
    them, leaving a cell that was never reported empty.
    """
    # Resolve broker/forex symbols (XAUUSD+ -> GC=F) to Yahoo's convention,
    # then reject values that would escape the cache directory when
    # interpolated into the cache filename (e.g. ``../../tmp/x``).
    canonical = normalize_symbol(symbol)
    safe_symbol = safe_ticker_component(canonical)

    config = get_config()
    as_of_dt = pd.to_datetime(as_of_date).normalize()

    # One cache file per symbol, holding the latest 5y-to-today download.
    now = pd.Timestamp.today()
    start_date = now - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    # End is exclusive. An exchange can already be on the next UTC date;
    # include that date independent of the host timezone or requested past date.
    # The retained cutoff and exchange metadata below still exclude partial rows.
    end_str = (_retrieval_time() + pd.Timedelta(days=2)).strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-YFin-data.csv",
    )

    # A cached file may be empty if a prior fetch failed (unknown symbol,
    # transient rate limit). Treat an empty/columnless cache as a miss and
    # re-fetch rather than serving the poisoned file forever.
    data = None
    source_metadata = None
    if os.path.exists(data_file):
        cached = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
        if (
            not cached.empty
            and "Close" in cached.columns
            and _SOURCE_COLUMN in cached.columns
            and _cache_is_fresh(data_file, as_of_dt, now)
        ):
            try:
                retained = json.loads(cached[_SOURCE_COLUMN].iloc[0])
                if retained["adjustment_basis"] == ADJUSTMENT and retained["ticker"] == canonical:
                    _timestamp(retained["retrieved_at"])
                    historical = as_of_dt.date() < _timestamp(retained["retrieved_at"]).date()
                    if not historical or (retained.get("actions_requested") is True
                                          and "Stock Splits" in cached):
                        source_metadata = retained
                        data = cached.drop(columns=[_SOURCE_COLUMN])
            except (KeyError, TypeError, ValueError):
                pass  # Legacy/malformed provenance uses the existing fetch path.

    if data is None:
        # yf.download catches every error, a rate limit included, and returns
        # an empty frame. Ticker.history raises the rate limit, so it is retried.
        def fetch():
            source = yf.Ticker(canonical)
            downloaded = source.history(
                start=start_str, end=end_str, auto_adjust=False, actions=True,
            )
            if downloaded is None or downloaded.empty:
                return None
            return downloaded, _source_metadata(source, downloaded, canonical, _retrieval_time())

        response = yf_retry(fetch)
        downloaded, source_metadata = response if response is not None else (None, None)
        if downloaded is None:
            raise_for_empty(symbol, canonical, "price rows")
        downloaded = _ensure_date_column(downloaded.reset_index())
        # Only cache real data — never persist an empty frame.
        if downloaded.empty or "Close" not in downloaded.columns:
            raise_for_empty(symbol, canonical, "price rows")
        _validate_close_values(downloaded, symbol, canonical)
        cached = downloaded.assign(**{_SOURCE_COLUMN: json.dumps(source_metadata, sort_keys=True)})
        replace_file(data_file, lambda temp: cached.to_csv(temp, index=False, encoding="utf-8"))
        data = downloaded

    _validate_close_values(data, symbol, canonical)
    _verify_historical_adjustment(data, source_metadata, as_of_dt, symbol, canonical)
    # Actions are only for private basis verification, never model input.
    data = data.drop(columns=["Stock Splits", "Dividends", "Capital Gains"], errors="ignore")
    data = _clean_dataframe(data)

    # Filter to as_of_date to prevent look-ahead bias in backtesting.
    data = data[data["Date"] <= as_of_dt]
    requested_cutoff = config.get("_market_observation_cutoff")
    cutoff = min(_retrieval_time(), _timestamp(requested_cutoff)).isoformat() if requested_cutoff else _retrieval_time().isoformat()
    data = data[data["Date"].map(lambda value: session_is_complete(
        value.date(), source_metadata["retrieved_at"], source_metadata["exchange_timezone"],
        source_metadata["regular_end"], cutoff,
    ))].copy()
    if data.empty:
        raise NoMarketDataError(symbol, canonical, "no completed price rows at the observation cutoff")

    # Select actual completed sessions; never carry a prior close under an empty
    # latest session's date. Sorting also makes the retained explanation stable.
    data = data.sort_values("Date")
    price_fallback = None

    # A closeless newest bar is an unsettled session, not a symbol without data.
    # _fill_price_gaps below drops it, here and mid-series alike, so the frame
    # ends at the last settled bar; only a range with no close anywhere is no
    # data (#1201, #1289).
    if not data.empty and pd.isna(data["Close"].iloc[-1]):
        settled = data["Close"].notna().to_numpy().nonzero()[0]
        if settled.size == 0:
            raise NoMarketDataError(
                symbol, canonical, "no bar in range has a closing price"
            )
        price_fallback = {
            "reason": "Latest completed session has no close; using last valid completed session",
            "latest_completed_session_date": str(data["Date"].iloc[-1].date()),
            "selected_session_date": str(data["Date"].iloc[settled[-1]].date()),
            "missing_completed_session_dates": [
                str(day.date()) for day in data["Date"].iloc[settled[-1] + 1:]
            ],
        }
        logger.warning(
            "%s: %d trailing bar(s) through %s have no closing price; using %s "
            "as the latest close.", canonical, len(data) - settled[-1] - 1,
            data["Date"].iloc[-1].date(), data["Date"].iloc[settled[-1]].date(),
        )

    # Indicators need a continuous series, so gaps are carried forward. A caller
    # that reports the numbers themselves asks for the frame as it was reported:
    # a filled cell is the previous session's price under this session's date.
    data = _fill_price_gaps(data) if fill_gaps else data.dropna(subset=["Close"]).copy()

    # Reject a stale frame (latest row far older than as_of_date) rather than
    # feeding year-old prices into indicators (#1021).
    _assert_ohlcv_not_stale(data, as_of_date, symbol, canonical)
    data.attrs["market_provenance"] = {
        **source_metadata, "observation_cutoff": cutoff, "analysis_date": str(as_of_dt.date()),
        "session_date": str(data["Date"].max().date()) if not data.empty else None,
        "session_status": "completed",
        **({"price_fallback": price_fallback} if price_fallback else {}),
    }
    return data



```


## `tradingagents/agents/structured.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `4b5eb845df98cb8d7e7d6c2a160f256cbf414819f7d9f854016aaa847048f45a`.

```python
"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. If the structured call itself fails for any reason
   (malformed JSON from a weak model, transient provider issue), fall
   back to a plain ``llm.invoke`` so the pipeline never blocks.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from tradingagents.operational_capture import (
    delivered_narrative,
    record_operation,
    remember_structured_raw,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Schema-only structured output binds exactly one tool (the schema itself), so a
# model that reaches for a search tool emits an unknown tool call and the whole
# structured attempt is discarded for a free-text retry. Agents on this path
# state the constraint explicitly rather than relying on the binding alone
# (#1130).
NO_EXTERNAL_TOOLS = (
    "Use only the evidence provided in this prompt. Do not call external tools "
    "or search the web; if something is missing, say so explicitly."
)


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Any | None:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    try:
        try:
            return llm.with_structured_output(schema, include_raw=True)
        except TypeError:
            return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, type(exc).__name__,
        )
        return None


def invoke_structured(structured_llm: Any | None, prompt: Any, agent_name: str) -> T | None:
    """Run the structured call; ``None`` when there is none or it fails.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape), so a caller can forward the same value to its free-text fallback.
    """
    remember_structured_raw(None)
    if structured_llm is None:
        return None
    try:
        result = structured_llm.invoke(prompt)
        if isinstance(result, dict) and "parsed" in result and "raw" in result:
            remember_structured_raw(result["raw"])
            if result.get("parsing_error") is not None:
                raise ValueError("structured output parsing failed")
            result = result["parsed"]
        if result is None:
            # A thinking model can answer in plain text instead of calling
            # the tool, leaving the parser with nothing to return. Treat it
            # as a structured miss and fall back, with a clear reason.
            raise ValueError("structured output returned no parsed result")
        return result
    except Exception as exc:
        logger.warning(
            "%s: structured-output invocation failed (%s); retrying once as free text",
            agent_name, type(exc).__name__,
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure."""
    result = invoke_structured(structured_llm, prompt, agent_name)
    if result is not None:
        return delivered_narrative(render(result))
    raw = plain_llm.invoke(prompt)
    text = delivered_narrative(raw.content, raw)
    if structured_llm is not None:
        record_operation('fallback_recovered')
    return text

```


## `tradingagents/operational_capture.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `4d40630f5376cda1bd58f62a31aa77385ccaf250a2a6b54f921dd854df79ac98`.

```python
"""Small execution observations scoped to one actual graph node invocation."""
from collections.abc import Mapping
from contextvars import ContextVar
from threading import Lock

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda

from tradingagents.operational_audit import observation

_active = ContextVar('operational_node', default=None)
_last_structured_raw = ContextVar('last_structured_raw', default=None)

TRUNCATION_NOTE = "[Model output truncated by provider; this narrative may be incomplete.]"


def output_was_truncated(raw):
    """Use the bounded provider finish status while its raw response is available."""
    metadata = getattr(raw, 'response_metadata', None)
    info = getattr(raw, 'generation_info', None)
    metadata = metadata if isinstance(metadata, Mapping) else {}
    info = info if isinstance(info, Mapping) else {}
    stop = metadata.get('finish_reason') or metadata.get('stop_reason') or info.get('finish_reason') or info.get('stop_reason')
    return stop in {'length', 'max_tokens', 'MAX_TOKENS'}


def delivered_narrative(text, raw=None):
    """Label only the response actually presented to a later agent."""
    if raw is None:
        raw = _last_structured_raw.get()
    return f"{text}\n\n{TRUNCATION_NOTE}" if output_was_truncated(raw) else text


def remember_structured_raw(raw):
    _last_structured_raw.set(raw)


def record_operation(code, *, scope=None):
    """Record a bounded reason code without provider payloads or exceptions."""
    active = _active.get()
    if active is None:
        return
    state, stage, events, lock = active
    with lock:
        key = (code, scope)
        if key in events:
            previous = events[key]
            events[key] = observation(state, stage, code=code, scope=scope,
                                      count=previous.get('count', 1) + 1)
        elif len(events) < 128:
            events[key] = observation(state, stage, code=code, scope=scope)
        else:
            events[('incomplete_history', None)] = observation(
                state, stage, code='incomplete_history', scope='observation limit')


class _Outcomes(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, 'message', None)
                metadata = getattr(message, 'response_metadata', None)
                info = getattr(generation, 'generation_info', None)
                if (message is not None and isinstance(metadata, Mapping)
                        and not (metadata.get('finish_reason') or metadata.get('stop_reason'))
                        and isinstance(info, Mapping)):
                    stop = info.get('finish_reason') or info.get('stop_reason')
                    if stop in {'length', 'max_tokens', 'MAX_TOKENS'}:
                        message.response_metadata = {**metadata, 'finish_reason': stop}
                if output_was_truncated(message) or output_was_truncated(generation):
                    record_operation('model_output_truncated')

    def on_tool_error(self, error, **kwargs):
        record_operation('tool_error')

    def on_tool_end(self, output, **kwargs):
        if getattr(output, 'status', None) == 'error':
            record_operation('tool_error')


def observed_node(node, stage, *, report_key=None, expected_stages=None):
    """Wrap a node while retaining LangGraph config and subgraph execution."""
    runnable = node if hasattr(node, 'invoke') else RunnableLambda(node)

    def invoke(state, config):
        if not state.get('run_id'):
            return runnable.invoke(state, config)
        events = {}
        token = _active.set((state, stage, events, Lock()))
        try:
            from langchain_core.runnables.config import merge_configs
            result = runnable.invoke(state, merge_configs(config, {'callbacks': [_Outcomes()]}))
        finally:
            _active.reset(token)
        code = 'empty_output' if report_key and not result.get(report_key) else 'completed'
        extra = {}
        if expected_stages is not None:
            extra['expected_stages'] = expected_stages
        if stage == 'Evidence Check':
            extra['route'] = 'review' if result.get('evidence_quality', {}).get('status') == 'insufficient' else 'full'
        if stage == 'Advisory Audit' and result.get('advisory_audit', {}).get('status') == 'unavailable':
            code = 'empty_output'
        row = observation(state, stage, code=code, **extra)
        rows = {row['event_id']: row}
        for event in events.values():
            rows[event['event_id']] = event
        return {**result, 'operational_observations': rows}

    return invoke

```


## `tradingagents/graph/setup.py` — complete module

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `8131cfd5783e68dcd674f0cb5b3d952e2005dd5b83899b2aed223c3cc99d7a60`.

```python
import logging
from collections import Counter
from typing import Annotated, Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_fundamentals_analyst,
    create_market_analyst,
    create_neutral_debator,
    create_news_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_sentiment_analyst,
    create_trader,
)
from tradingagents.agents.analysts.turn import WRAP_UP
from tradingagents.agents.audit_evidence import AUDIT_TOOL_FIELDS, collect_tool_outputs
from tradingagents.agents.audit_pass import create_advisory_audit
from tradingagents.agents.document_access import merge_search_traces
from tradingagents.agents.document_questions import lookup_document_questions
from tradingagents.agents.evidence_validation import create_evidence_gate, create_source_acquisition
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.state import AgentState
from tradingagents.operational_capture import observed_node

from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)

# Every target a shared conditional router can return. Each edge driven by the
# router maps all of them, so a fall-through return (e.g. under prompt/i18n/
# refactor drift in the speaker labels) can never hit a missing path_map entry
# and crash LangGraph mid-run (#1088).
DEBATE_PATH_MAP = {
    "Bull Researcher": "Bull Researcher",
    "Bear Researcher": "Bear Researcher",
    "Research Manager": "Document Followup",
}
RISK_ANALYSIS_PATH_MAP = {
    "Aggressive Analyst": "Aggressive Analyst",
    "Conservative Analyst": "Conservative Analyst",
    "Neutral Analyst": "Neutral Analyst",
    "Portfolio Manager": "Advisory Audit",
}


def _tools_or_done(state) -> str:
    """Route an analyst's turn: run its tool calls, or finish with its report."""
    return "tools" if state["messages"][-1].tool_calls else END


def _analyst_graph(spec, agent, max_tool_rounds: int):
    """One analyst as a graph of its own: the model and its tools, on a private message history.

    It returns only its report, so analysts running side by side never write the
    same key, and its tool calls never reach the other analysts' messages. After
    ``max_tool_rounds`` rounds of tool calls it is told to write its report, and
    that turn ends it whatever it answers, so a model that keeps calling tools
    cannot run the graph into its recursion limit (#1420).
    """
    evidence_field = AUDIT_TOOL_FIELDS[spec.key]
    output_fields = {spec.report_key: str, evidence_field: dict}
    if spec.key in {"fundamentals", "news"}:
        output_fields["document_search_trace"] = Annotated[dict, merge_search_traces]
    if spec.key == "fundamentals":
        output_fields["disclosure_evidence"] = dict
    if spec.key == "news":
        output_fields["news_coverage"] = dict
    output = TypedDict(f"{spec.key.capitalize()}Report", output_fields)
    graph = StateGraph(AgentState, output_schema=output)
    def run_agent(state):
        return {"document_search_role": spec.key, **agent({**state, "document_search_role": spec.key})}

    graph.add_node("agent", run_agent)
    graph.add_edge(START, "agent")

    def finish(state):
        evidence = state.get(evidence_field) if spec.key == "social" else None
        evidence = dict(evidence or collect_tool_outputs(state, spec.key))
        calls = {call.get("id") for message in state.get("messages", [])
                 for call in (getattr(message, "tool_calls", None) or [])
                 if isinstance(call, dict) and isinstance(call.get("id"), str)}
        responses = [message for message in state.get("messages", [])
                     if getattr(message, "tool_call_id", None) in calls]
        failed = bool(calls) and not any(
            getattr(message, "status", None) != "error"
            and bool(str(message.content).strip())
            and not str(message.content).lstrip().startswith(("DATA_UNAVAILABLE:", "NO_DATA_AVAILABLE:"))
            for message in responses
        )
        evidence["all_tools_failed"] = failed
        result = {evidence_field: evidence}
        if failed:
            warning = "Warning: requested tool calls supplied no support for this report."
            if state.get("shared_source_brief") or state.get("disclosure_evidence"):
                warning += " Separately supplied shared filing evidence may still be available."
            result[spec.report_key] = warning + "\n\n" + (state.get(spec.report_key) or "")
        return result

    graph.add_node("finish", finish)
    graph.add_edge("finish", END)
    if not spec.tools:
        graph.add_edge("agent", "finish")
        return graph.compile()

    def calls(messages):
        return [call["name"] for m in messages for call in (getattr(m, "tool_calls", None) or [])]

    def rounds(messages) -> int:
        return sum(1 for m in messages if getattr(m, "tool_calls", None))

    def more_or_wrap_up(state) -> str:
        return "wrap_up" if rounds(state["messages"]) >= max_tool_rounds else "agent"

    def wrap_up(state):
        repeated = ", ".join(f"{name} x{n}" for name, n in Counter(calls(state["messages"])).most_common())
        logger.warning("%s used its %d tool rounds (%s); asking for its report",
                       spec.agent_node, max_tool_rounds, repeated)
        return agent({**state, "messages": [*state["messages"], HumanMessage(WRAP_UP)]})

    graph.add_node("tools", ToolNode(
        list(spec.tools),
        handle_tool_errors=lambda exc: f"DATA_UNAVAILABLE: tool failed ({type(exc).__name__}); do not infer values.",
    ))
    graph.add_node("wrap_up", wrap_up)
    graph.add_conditional_edges("agent", lambda state: "tools" if _tools_or_done(state) == "tools" else "finish",
                                ["tools", "finish"])
    graph.add_conditional_edges("tools", more_or_wrap_up, ["agent", "wrap_up"])
    graph.add_edge("wrap_up", "finish")
    return graph.compile()


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        conditional_logic: ConditionalLogic,
        max_tool_rounds: int,
        quick_model_id: str = "unknown",
        deep_model_id: str = "unknown",
        metrics_observer=None,
        audit_llm=None,
        audit_sdk_retries_disabled=False,
        publication_config=None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.conditional_logic = conditional_logic
        self.max_tool_rounds = max_tool_rounds
        self.quick_model_id = quick_model_id
        self.deep_model_id = deep_model_id
        self.metrics_observer = metrics_observer
        self.audit_llm = audit_llm if audit_llm is not None else deep_thinking_llm
        self.audit_sdk_retries_disabled = audit_sdk_retries_disabled
        self.publication_config = publication_config

    def setup_graph(
        self, selected_analysts=("market", "social", "news", "fundamentals"), memory_node=None
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Sentiment analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
            memory_node: Node that settles past decisions and returns the run's
                ``past_context``. It runs alongside the analysts.
        """
        plan = build_analyst_execution_plan(selected_analysts)

        analyst_factories = {
            "market": lambda: create_market_analyst(self.quick_thinking_llm),
            "social": lambda: create_sentiment_analyst(self.quick_thinking_llm),
            "news": lambda: create_news_analyst(self.quick_thinking_llm),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm),
        }

        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        raw_portfolio_manager = create_portfolio_manager(self.deep_thinking_llm)

        def portfolio_manager_node(state):
            decision = raw_portfolio_manager(state)
            return {**decision, **enforce_publication({**state, **decision})}


        workflow = StateGraph(AgentState)

        expected = ['Source Acquisition', *[spec.agent_node for spec in plan.specs],
                    'Evidence Check', 'Bull Researcher', 'Bear Researcher', 'Document Followup',
                    'Research Manager', 'Trader', 'Aggressive Analyst', 'Conservative Analyst',
                    'Neutral Analyst', 'Advisory Audit', 'Portfolio Manager', 'Run Metrics']
        if memory_node is not None:
            expected.append('Memory Log')

        def add_node(name, node, report_key=None):
            workflow.add_node(name, observed_node(
                node, name, report_key=report_key,
                expected_stages=expected if name == 'Source Acquisition' else None))

        for spec in plan.specs:
            add_node(spec.agent_node,
                     _analyst_graph(spec, analyst_factories[spec.key](), self.max_tool_rounds),
                     report_key=spec.report_key)

        def final_question_turn(node, role):
            def invoke(state):
                count = (state.get("investment_debate_state") or {}).get("count", 0)
                threshold = 2 * self.conditional_logic.max_debate_rounds - (2 if role == "bull" else 1)
                return node({**state, "_document_question_final_turn": count >= threshold})
            return invoke

        add_node("Bull Researcher", final_question_turn(bull_researcher_node, "bull"))
        add_node("Bear Researcher", final_question_turn(bear_researcher_node, "bear"))
        add_node("Document Followup", lookup_document_questions)
        workflow.add_edge("Document Followup", "Research Manager")
        add_node("Research Manager", research_manager_node, report_key="investment_plan")
        add_node("Trader", trader_node, report_key="trader_investment_plan")
        add_node("Aggressive Analyst", aggressive_analyst)
        add_node("Neutral Analyst", neutral_analyst)
        add_node("Conservative Analyst", conservative_analyst)
        add_node("Portfolio Manager", portfolio_manager_node, report_key="final_trade_decision")
        raw_audit = create_advisory_audit(
            self.audit_llm, deep_model_id=self.deep_model_id,
            quick_model_id=self.quick_model_id,
            sdk_retries_disabled=self.audit_sdk_retries_disabled)

        def audit_node(state):
            result = raw_audit(state)
            if self.metrics_observer:
                result["run_metrics"] = self.metrics_observer({**state, **result})
            return result

        def metrics_node(state):
            result = {"run_metrics": self.metrics_observer(state)} if self.metrics_observer else {}
            if (state.get("evidence_quality") or {}).get("status") == "insufficient" and "advisory_audit" not in state:
                # The existing REVIEW gate bypasses all decision calls. Disclose
                # the missing audit without invoking a model or changing the gate.
                result["advisory_audit"] = {
                    "status": "unavailable", "findings": [], "counts_by_type": {},
                    "submitted_count": 0, "accepted_count": 0, "rejected_count": 0,
                    "rejection_reasons": [], "independence_by_role": {},
                    "error": "not run: insufficient evidence; risk debate and Portfolio Manager were bypassed",
                }
            # Retain the display comparison before the terminal checkpoint, so
            # crash recovery verifies the same canonical publication payload.
            if self.publication_config is not None:
                result.update(enforce_publication(
                    {**state, **result}, publication_config=self.publication_config))
            return result

        add_node("Advisory Audit", audit_node)
        add_node("Run Metrics", metrics_node)

        # One retained source vintage precedes parallel analyst reasoning. The
        # memory log retains its independent start and joins every analyst before
        # evidence validation, preserving prior-thesis cutoff dependencies.
        first_steps = [spec.agent_node for spec in plan.specs]
        if memory_node is not None:
            add_node("Memory Log", memory_node)
            first_steps.append("Memory Log")
        add_node("Source Acquisition", create_source_acquisition(selected_analysts))
        workflow.add_edge(START, "Source Acquisition")
        for spec in plan.specs:
            workflow.add_edge("Source Acquisition", spec.agent_node)
        if memory_node is not None:
            workflow.add_edge(START, "Memory Log")
        evidence_gate = create_evidence_gate(selected_analysts)

        def evidence_with_scenarios(state):
            from tradingagents.agents.shared_valuation import prepare_shared_valuation

            checked = evidence_gate(state)
            if state.get("prior_thesis"):
                from tradingagents.memory.thesis import observe_conditions, render_prior_thesis
                usable = {**state, **checked} if checked.get("evidence_quality", {}).get("status") in {"sufficient", "limited"} else {}
                prior = {**state["prior_thesis"], "observations": observe_conditions(state["prior_thesis"], usable)}
                checked.update(prior_thesis=prior, thesis_context=render_prior_thesis(prior))
            from tradingagents.agents.event_comparison import prepare_event_comparison
            from tradingagents.agents.valuation_reference_flow import finalize_peer_reference
            from tradingagents.dataflows.config import get_config

            checked.update(finalize_peer_reference({**state, **checked}, get_config()))
            event = prepare_event_comparison({**state, **checked}, get_config())
            scenarios = prepare_shared_valuation({**state, **checked})
            return {**checked, "shared_valuation_scenarios": scenarios, "event_comparison": event}

        add_node("Evidence Check", evidence_with_scenarios)
        workflow.add_edge(first_steps, "Evidence Check")
        workflow.add_conditional_edges(
            "Evidence Check",
            lambda state: "Run Metrics" if state.get("evidence_quality", {}).get("status") == "insufficient" else "Bull Researcher",
            {"Run Metrics": "Run Metrics", "Bull Researcher": "Bull Researcher"},
        )

        # Both research-debate edges share the complete DEBATE_PATH_MAP (#1088).
        for debate_node in ("Bull Researcher", "Bear Researcher"):
            workflow.add_conditional_edges(
                debate_node,
                self.conditional_logic.should_continue_debate,
                DEBATE_PATH_MAP,
            )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        # All three risk edges share the complete RISK_ANALYSIS_PATH_MAP (#1088).
        for risk_node in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
            workflow.add_conditional_edges(
                risk_node,
                self.conditional_logic.should_continue_risk_analysis,
                RISK_ANALYSIS_PATH_MAP,
            )

        workflow.add_edge("Advisory Audit", "Portfolio Manager")
        workflow.add_edge("Portfolio Manager", "Run Metrics")
        workflow.add_edge("Run Metrics", END)

        return workflow

```


## `tradingagents/graph/trading_graph.py` — complete `_state_log_path` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `ff0003096dd3d55207fa3e01b99b7e38c9f7a92d2c0c8db8af11e402a349b2a4`.

```python
def _state_log_path(config, ticker, trade_date, run_id=None):
    directory = Path(config["results_dir"]) / safe_ticker_component(ticker) / "TradingAgentsStrategy_logs"
    suffix = "_" + safe_ticker_component(str(run_id)[:8]) if run_id else ""
    return directory / f"full_states_log_{trade_date}{suffix}.json"
```


## `tradingagents/graph/trading_graph.py` — complete `_recover_logged_summary` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `c95b11076f322f8111b5a8d68e54acd0212bfaebd4bbd39d5e1b4b91ae7083d2`.

```python
def _recover_logged_summary(config, ticker, trade_date, record):
    path = _state_log_path(config, ticker, _validate_trade_date(trade_date), record.get("run_id"))
    if not path.exists():
        path = _state_log_path(config, ticker, trade_date)
    try:
        with path.open(encoding="utf-8") as saved:
            state = json.load(saved)
    except FileNotFoundError:
        return None
    except (UnicodeError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Prior editorial projection unavailable (%s)", type(exc).__name__)
        return None
    if isinstance(state, dict) and state.get("run_id") == record["run_id"]:
        return state.get("executive_summary")
    return None
```


## `tradingagents/graph/trading_graph.py` — complete `record_attempt_event` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `44597d897b4510fd04b03a927e2dc2c87b8fa3cbce670413fe091765ec67e8d6`.

```python
def record_attempt_event(config, attempt_id, ticker, trade_date, event, *, decision_id=None, error_type=None):
    """Append minimal execution coverage to the existing log; never provider errors."""
    row = {"schema_version": 1, "attempt_id": attempt_id, "event": event,
           "recorded_at": datetime.now(UTC).isoformat(), "ticker": ticker,
           "requested_as_of": trade_date}
    if decision_id:
        row["decision_id"] = decision_id
    if error_type:
        row["error_type"] = error_type
    try:
        path = Path(config["results_dir"]) / safe_ticker_component(ticker) / trade_date / "message_tool.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("[Evaluation Attempt] " + json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        logger.warning("Evaluation attempt coverage could not be written")
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph.__init__` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `37e24b004d43056c35d4c8e2b3e6370721271a290815e55f842e93e80680097e`.

```python
    def __init__(
        self,
        selected_analysts=("market", "social", "news", "fundamentals"),
        debug=False,
        config: dict[str, Any] = None,
        callbacks: list | None = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []
        self._metrics_observer_id = str(uuid4())
        self._metrics_callback = next((item for item in self.callbacks
                                       if callable(getattr(item, "get_stats", None))), None)
        self._metrics_start = self._callback_calls()

        set_config(self.config)

        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        extra = {"callbacks": self.callbacks} if self.callbacks else {}
        self.deep_thinking_llm = create_tier_client(self.config, "deep", **extra).get_llm()
        self.quick_thinking_llm = create_tier_client(self.config, "quick", **extra).get_llm()
        self.audit_llm = create_tier_client(
            {**self.config, "llm_max_retries": 0}, "deep", **extra
        ).get_llm()

        self.memory_log = TradingMemoryLog(self.config)

        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        # An analyst takes two steps per tool round, plus wrap-up and the
        # retained-tool-input finish step; the recursion limit must exceed that.
        # A tool budget past this boundary would end the run
        # there instead.
        max_tool_rounds, max_recur_limit = self.config["max_tool_rounds"], self.config["max_recur_limit"]
        if 2 * max_tool_rounds + 2 >= max_recur_limit:
            raise ValueError(
                f"max_tool_rounds={max_tool_rounds} needs max_recur_limit above {2 * max_tool_rounds + 2}"
            )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.conditional_logic,
            max_tool_rounds,
            quick_model_id=str(self.config.get("quick_think_llm")),
            deep_model_id=str(self.config.get("deep_think_llm")),
            metrics_observer=self._observe_run_metrics,
            audit_llm=self.audit_llm,
            audit_sdk_retries_disabled=True,
            publication_config=self.config,
        )

        self.propagator = Propagator(
            max_recur_limit=max_recur_limit,
        )
        self.reflector = Reflector(self.quick_thinking_llm)

        # Graph-shape-affecting run choices, kept for the checkpoint signature.
        self.selected_analysts = tuple(selected_analysts)

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts, memory_node=self._memory_step)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None
        self._resuming = False
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph._run_signature` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `5b17caf107ceed70c8377acf3a2554b27028efbe75f25e4a3af84f0b240d38a2`.

```python
    def _run_signature(self, asset_type: str, portfolio=None) -> str:
        """Run inputs that must invalidate a checkpoint if changed.

        Keyed into the checkpoint thread ID so a resume under a different analyst
        selection, debate/risk depth, or asset mode starts fresh instead of
        silently continuing the previous graph (#1089). The rest of the config
        counts too (provider, models, endpoint, language, vendors, limits): a
        resume must not carry reports that other settings produced. Only where
        the run keeps its files and how it retries are left out.
        """
        from tradingagents.agents.valuation_reference_flow import peer_selection_fingerprint

        settings = {k: v for k, v in self.config.items() if k not in _NOT_IN_SIGNATURE}
        digest = hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()[:12]
        return "|".join([
            "analysts=" + ",".join(self.selected_analysts),
            f"debate={self.config['max_debate_rounds']}",
            f"risk={self.config['max_risk_discuss_rounds']}",
            f"asset={asset_type}",
            # None, an empty book and a changed book are three different runs.
            f"portfolio={portfolio.fingerprint() if portfolio is not None else 'none'}",
            # The layout itself: a checkpoint saved when analysts ran one after
            # another has pending nodes this graph no longer has, and one saved
            # before the Memory Log step would resume without the lessons.
            "analysts=parallel",
            "memory=parallel",
            # Old checkpoints must not resume beyond the new evidence gate or
            # publication projection. Different IDs leave historical files intact.
            "evidence=4",
            "source_acquisition=1",
            "publication=1",
            "shared_valuation=7",
            "advisory_thesis=2",
            "price_observation=3",
            "completed_market_inputs=2",
            "event_comparison=2",
            "valuation_reference=3",
            "mechanical_valuation_grid=2",
            "mechanical_shared_context=1",
            f"peer_pins={peer_selection_fingerprint(self.config)}",
            "decision_context=4",
            "evidence_presentation=1",
            "publication_record=3",
            "analysis_cutoff=2",
            "advisory_audit=5",
            "run_metrics=2",
            "financing_evidence=2",
            "shared_source_brief=4",
            "operational_delivery=1",
            "financial_claim_prompt=1",
            "document_search=2",
            "document_followup=2",
            "vendor_transcript=1",
            "audit_dispositions=1",
            f"settings={digest}",
        ])
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph.begin_checkpoint` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `1d46f204a8f2bff813533c5d11581d7bde7dfcf2a5ebe96ac193192c4f3d20ae`.

```python
    def begin_checkpoint(self, company_name, trade_date, asset_type: str = "stock", portfolio=None) -> str | None:
        """Recompile the graph with a per-ticker checkpointer and return the
        ``thread_id`` to inject into the stream/invoke ``config`` (or ``None``
        when checkpointing is disabled).

        Pair every call with :meth:`end_checkpoint` in a ``finally``. Both
        ``propagate`` (via :meth:`checkpoint_scope`) and the CLI stream path use
        this so ``--checkpoint`` actually resumes (#1249); previously the setup
        lived only inside ``propagate`` and the CLI streamed the checkpointer-less
        graph, making the flag a no-op.
        """
        self._resuming = False
        if not self.config.get("checkpoint_enabled"):
            return None
        signature = self._run_signature(asset_type, portfolio)
        self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], company_name)
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)

        step = checkpoint_step(
            self.config["data_cache_dir"], company_name, str(trade_date), signature
        )
        self._resuming = step is not None
        if step is not None:
            logger.info("Resuming from step %d for %s on %s", step, company_name, trade_date)
        else:
            logger.info("Starting fresh for %s on %s", company_name, trade_date)
        return thread_id(company_name, str(trade_date), signature)
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph.checkpoint_input` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `9bc124cb35aaf00ec639be3fe8be19008c582f04be31aa9e5347dfc41de164db`.

```python
    def checkpoint_input(self, init_state):
        """The value to stream/invoke: ``None`` to resume an existing checkpoint,
        else the initial state for a fresh run.

        LangGraph resumes an interrupted thread when invoked with ``None``;
        re-passing the initial state instead appends it through the message
        reducer, duplicating messages in the resumed state (#1249).
        """
        return None if self._resuming else init_state
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph.run_settings` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `36b48e71f9cfcc85f4dfae6cf9bf07b8dbb45de3f633831c7aca13012e31438b`.

```python
    def run_settings(self) -> dict:
        """What produces this graph's runs, for the saved report and state log.

        An allowlist: endpoints (a backend_url can carry credentials), keys and
        local paths are never recorded.
        """
        cfg = self.config
        return {
            "version": tradingagents.__version__,
            "source_hash": publication.runtime_versions()["code"],
            **{key: cfg.get(key) for key in ("openai_reasoning_effort", "anthropic_effort", "google_thinking_level")},
            "llm_provider": cfg.get("llm_provider"),
            "deep_think_provider": tier_provider(cfg, "deep") if cfg.get("llm_provider") else None,
            "deep_think_llm": cfg.get("deep_think_llm"),
            "quick_think_provider": tier_provider(cfg, "quick") if cfg.get("llm_provider") else None,
            "quick_think_llm": cfg.get("quick_think_llm"),
            "analysts": list(self.selected_analysts),
            "max_debate_rounds": cfg.get("max_debate_rounds"),
            "max_risk_discuss_rounds": cfg.get("max_risk_discuss_rounds"),
            "output_language": cfg.get("output_language"),
            "data_vendors": dict(cfg.get("data_vendors") or {}),
            "tool_vendors": dict(cfg.get("tool_vendors") or {}),
        }
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph.save_reports` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `fed3929d66650a62bda66f51b0f636b5ed33d9b9a26ca47fa22b4c7915bb8dcf`.

```python
    def save_reports(self, final_state, ticker, save_path=None, html=True) -> Path:
        """Write the report tree for a completed run, like the CLI does.

        Programmatic callers get the same on-disk reports the CLI produces. Pass
        an explicit ``save_path`` or let it default under ``results_dir``; the
        report is also written as one HTML page unless ``html`` is False.
        """
        if save_path is None:
            save_path = self.default_report_path(ticker)
        return write_report_tree(final_state, ticker, save_path, settings=self.run_settings(), html=html, publication_config=getattr(self, "config", None))
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph.create_run_state` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `5e15830223e8ec12ae455c8a411acb42cc3272832b14b34e04f693b6a51e02d0`.

```python
    def create_run_state(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Build a run's initial state; propagate() and the CLI both start here.

        Injects the resolved instrument identity for every agent (#814). The
        memory log's lessons are not here: the graph's Memory Log step settles
        and loads them alongside the analysts (see ``_memory_step``).
        """
        state = self.propagator.create_initial_state(
            company_name,
            trade_date,
            asset_type=asset_type,
            instrument_context=self.resolve_instrument_context(company_name, asset_type, trade_date),
            portfolio_context=portfolio.render(company_name) if portfolio is not None else "",
        )

        state["run_metrics"] = self._initial_run_metrics()
        state["evaluation_mode"] = self.config.get("evaluation_mode", "prospective")
        state["run_settings"] = self.run_settings()
        state["publication_versions"] = publication.runtime_versions()
        state["run_settings"]["source_hash"] = state["publication_versions"]["code"]
        state["analysis_clock"] = self._analysis_cutoff(trade_date)
        state["market_observation_cutoff"] = min(
            datetime.now(UTC), datetime.fromisoformat(state["analysis_clock"]["cutoff_utc"])
        ).isoformat()
        return state
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph.record_decision` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `6ca94f7238e9cc819ed2f6355a392ee976c03c2d4ca00a85fb502ff8d43c8e50`.

```python
    def record_decision(self, company_name, trade_date, final_state):
        """Record a finished run: its state log, and its decision in the memory log
        for reflection on the next same-ticker run. propagate() and the CLI both end here."""
        frozen = verified_publication(self.config, final_state, company_name, trade_date)
        if frozen is not None:
            record, _snapshot = frozen
        else:
            final_state.setdefault("run_id", str(uuid4()))
            final_state.update(enforce_publication(
                {**final_state, "company_of_interest": company_name, "trade_date": str(trade_date)},
                publication_config=self.config))
            # An actual new publication uses current validators; a forged saved
            # marker cannot turn this path into a historical re-export.
            final_state.setdefault("run_id", str(uuid4()))
            final_state.setdefault("run_settings", self.run_settings())
            if "publication_versions" not in final_state:
                final_state["publication_versions"] = publication.runtime_versions()
            record = publication.publish(self.config, final_state, company_name, trade_date)
        final_state["publication_record"] = {
            key: record[key] for key in ("decision_id", "published_at", "record_sha256")
        }
        try:
            final_state["outcome_summary"] = self.outcome_summary(company_name, limit=10)
        except Exception as exc:
            logger.warning("Publication saved but outcome summary unavailable: %s", exc)
            final_state["outcome_summary"] = "Outcome history unavailable; retained records need inspection."
        if frozen is None:
            # Editorial output belongs only to the readable projection. Publication
            # and its immutable metrics/evidence have already been committed.
            try:
                context = summary_input_for_report(prepare_report_state(final_state))
                saved = final_state.get("executive_summary")
                if not saved or resolve_summary(context, saved)["status"] != "completed":
                    final_state["executive_summary"] = generate_summary(
                        context, getattr(self, "deep_thinking_llm", None)
                    )
            except Exception as exc:
                # An editorial adapter failure cannot cancel a published decision.
                # Provider exceptions can include private prompt text or endpoints.
                logger.warning("Executive summary unavailable (%s)", type(exc).__name__)
                final_state["executive_summary"] = {
                    "schema_version": 1, "status": "unavailable", "error_category": "preparation",
                }
        elif "executive_summary" not in final_state:
            # A terminal graph checkpoint predates the post-publication state log.
            # On retry, reuse the summary only from this exact publication.
            recovered = _recover_logged_summary(self.config, company_name, trade_date, record)
            if recovered is not None:
                final_state["executive_summary"] = recovered
        self._log_state(trade_date, final_state)
        if is_review(run_rating(final_state)):
            logger.info("Research REVIEW for %s on %s saved without trading-memory insertion", company_name, trade_date)
            return
        decision = final_state.get("final_trade_decision")
        if not decision:
            logger.warning("No final decision for %s on %s; nothing added to the memory log",
                           company_name, trade_date)
            return
        # Publication order, not projection scheduling, chooses the daily
        # observation. A later revision may repair a missing primary projection.
        primary = next((r for r in publication.list_records(self.config, company_name)
                        if r["requested_as_of"] == str(trade_date) and r["eligibility"]["primary"]), None)
        if primary is not None:
            memory_decision = decision if primary["decision_id"] == record["decision_id"] else primary["canonical_decision"]
            if primary["decision_truncated"] and primary["decision_id"] != record["decision_id"]:
                memory_decision += "\n[Bounded publication excerpt; full decision hash retained in publication.]"
            self.memory_log.store_decision(
                ticker=company_name, trade_date=trade_date, final_trade_decision=memory_decision,
                rating=primary["canonical_rating"], decision_id=primary["decision_id"],
            )
        elif not final_state.get("evidence_quality"):
            # Existing unvalidated programmatic callers retain legacy behavior;
            # do not link their memory to an ineligible measurement record.
            self.memory_log.store_decision(
                ticker=company_name, trade_date=trade_date, final_trade_decision=decision,
                rating=run_rating(final_state),
            )
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph.stream_run` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `e030fa3bb2b92e25722fc7a91b19bf327f2f3ad23ae46204b542c5ec83eb5a3c`.

```python
    def stream_run(self, graph_input, **args):
        """Stream a run as ``(messages, state)`` pairs.

        ``messages`` are the agents' messages, the analysts' included. ``state``
        is the run's state after a top-level step; for a step inside an analyst's
        graph it is that analyst's report once filed, else None.

        Each analyst works in a graph of its own, and the run's state takes the
        analysts' reports only when the slowest has finished, so their messages
        and reports come from their own finished steps ("tasks") as they happen.
        """
        from tradingagents.agents.stream_publication import provisional_messages, provisional_state

        args = {**args, "stream_mode": ["values", "tasks"]}
        # The graph's own config serves every tool call, as in propagate(), even
        # when the process-wide config has changed since. Each step runs in the
        # run's context, so the caller keeps its own between steps.
        context = run_config_context(self.config)
        stream = context.run(self.graph.stream, graph_input, subgraphs=True, **args)
        try:
            while (step := context.run(next, stream, None)) is not None:
                namespace, mode, chunk = step
                if namespace:
                    result = chunk.get("result") if mode == "tasks" else None
                    if isinstance(result, dict):
                        report = {k: v for k, v in result.items() if k != "messages" and v}
                        if result.get("messages") or report:
                            yield provisional_messages(result.get("messages", [])), provisional_state(report or None)
                elif mode == "values":
                    yield provisional_messages(chunk.get("messages", [])), provisional_state(chunk)
        finally:
            context.run(stream.close)
```


## `tradingagents/graph/trading_graph.py` — complete `TradingAgentsGraph._log_state` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `45430847c36c08e4c572113400eb2a6d7014a040e2725b87aec03a8809fafb3f`.

```python
    def _log_state(self, trade_date, final_state):
        """Write a run's final state to JSON under the run's own ticker."""
        entry = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                **({"count": final_state["investment_debate_state"]["count"]}
                   if "count" in final_state["investment_debate_state"] else {}),
                **({"document_questions": final_state["investment_debate_state"]["document_questions"]}
                   if "document_questions" in final_state["investment_debate_state"] else {}),
            },
            "trader_investment_plan": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
            "final_rating": run_rating(final_state),
            "run_settings": final_state.get("run_settings", self.run_settings()),
        }

        for field in ("operational_observations", "executive_summary", "audit_market_tool_evidence", "audit_social_tool_evidence", "audit_news_tool_evidence", "audit_fundamentals_tool_evidence", "advisory_audit", "run_metrics", "valuation_reference", "valuation_reference_brief", "vendor_expectations", "analysis_clock", "asset_type", "document_sources", "transcript_sources", "document_search_trace", "document_followups", "market_observation_cutoff", "evidence_acquisition", "shared_source_brief", "prior_thesis", "thesis_context", "thesis_candidate", "thesis", "thesis_version_id", "price_observation", "valuation_price_comparison", "price_implied_valuation", "mechanical_valuation_grid", "decision_context", "event_comparison", "issuer_identity", "news_coverage", "issuer_event_evidence", "evaluation_mode", "outcome_summary", "run_id", "publication_versions", "publication_record", "evidence_quality", "financial_evidence", "financial_calculations", "financial_claim_validation", "canonical_financial_context", "filing_evidence", "filing_fact_extraction", "filing_terms_evidence", "disclosure_evidence", "target_validation", "unvalidated_outputs", "shared_valuation_scenarios"):
            if field in final_state:
                entry[field] = final_state[field]

        # A ticker that would escape the results directory is rejected.
        log_path = _state_log_path(self.config, final_state["company_of_interest"], trade_date)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        from tradingagents.dataflows.files import replace_file

        def write_snapshot(temp):
            with open(temp, "w", encoding="utf-8") as f:
                # Reports can be in any language and this file is read by a person.
                json.dump(entry, f, indent=4, ensure_ascii=False)

        if final_state.get("run_id"):
            archive = _state_log_path(self.config, final_state["company_of_interest"], trade_date, final_state["run_id"])
            replace_file(archive, write_snapshot, strict=True)
        replace_file(log_path, write_snapshot, strict=True)
```


## `tradingagents/memory/publication.py` — complete `runtime_versions` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `0740f7ef4cbf0f26de8758b97493fae93305b48a6aac3d7d3002bf7365f9fe2c`.

```python
def runtime_versions() -> dict:
    """Fingerprint installed source, including prompts, without storing local paths.

    Unlike a Git HEAD alone this also describes an uncommitted candidate or an
    installed package. Call at invocation start and preserve through checkpoints.
    """
    package = Path(__file__).resolve().parents[1]
    code, prompts = hashlib.sha256(), hashlib.sha256()
    for path in sorted(package.rglob('*.py')):
        relative = path.relative_to(package).as_posix()
        entry = relative.encode() + b'\0' + path.read_bytes() + b'\0'
        code.update(entry)
        if relative.startswith('agents/'):
            prompts.update(entry)
    return {'code': 'sha256:' + code.hexdigest(),
            'prompt': 'sha256:' + prompts.hexdigest(), 'schema': _SCHEMA}
```


## `tradingagents/reporting.py` — complete `_header` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `a828a74ff042c9e8a895a3b1f393015f48b208231ac4d89368fb67d5462ae537`.

```python
def _header(ticker: str, final_state: dict, settings: dict | None, *, metadata_only: bool = False) -> str:
    """The report's title and what produced it: analysis date, version, models, analysts, vendors."""
    lines = [] if metadata_only else [f"# Trading Analysis Report: {_plain_markdown(ticker)}", ""]
    if final_state.get("trade_date") and not metadata_only:
        lines.append(f"- Analysis date: {_plain_markdown(final_state['trade_date'])}")
    if final_state.get("final_trade_decision"):
        lines.append(f"- Rating: {_plain_markdown(run_rating(final_state))}")
        if final_state.get("decision_context"):
            lines += ["", render_condition_summary(final_state["decision_context"]), ""]
    if not final_state.get("evidence_quality"):
        lines.append("- Evidence: Legacy export — financial evidence unvalidated")
    publication = final_state.get("publication_record")
    if publication:
        lines.append(f"- Decision ID: {_plain_markdown(publication['decision_id'])}")
        lines.append(f"- First published: {_plain_markdown(publication['published_at'])}")
    label = "Export generated" if publication else "Generated"
    lines.append(f"- {label}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if final_state.get("report_view_note"):
        lines.append("- Export view: " + _plain_markdown(final_state["report_view_note"]))
    elif publication:
        lines.append("- Historical publication identity not verified against a configured store; current validated projection.")
    if settings:
        s = settings.get
        deep_provider = s("deep_think_provider") or s("llm_provider", "?")
        quick_provider = s("quick_think_provider") or s("llm_provider", "?")
        if deep_provider == quick_provider:
            models = f"{deep_provider}, deep {s('deep_think_llm', '?')}, quick {s('quick_think_llm', '?')}"
        else:  # each tier on its own provider (#1440)
            models = (
                f"deep {deep_provider} {s('deep_think_llm', '?')}, "
                f"quick {quick_provider} {s('quick_think_llm', '?')}"
            )
        lines.append(f"- TradingAgents {_plain_markdown(s('version', '?'))}: {_plain_markdown(models)}")
        if s("source_hash"):
            lines.append(f"- Source hash: {_plain_markdown(s('source_hash'))}")
        for key, label in (("openai_reasoning_effort", "OpenAI/OpenRouter reasoning effort"),
                           ("anthropic_effort", "Anthropic effort"),
                           ("google_thinking_level", "Google thinking level")):
            if s(key):
                lines.append(f"- {label}: {_plain_markdown(s(key))}")
        lines.append(
            f"- Analysts: {_plain_markdown(', '.join(analyst_names(s('analysts'))))}; "
            f"research debate rounds {_plain_markdown(s('max_debate_rounds', '?'))}, "
            f"risk debate rounds {_plain_markdown(s('max_risk_discuss_rounds', '?'))}"
        )
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        if vendors:
            lines.append("- Data vendors: " + _plain_markdown(", ".join(f"{k} {v}" for k, v in vendors.items())))
    if final_state.get("memory_note"):
        lines.append(f"- Memory log: {_plain_markdown(final_state['memory_note'])}")
    return "\n".join(lines) + "\n\n"
```


## `tradingagents/reporting.py` — complete `prepare_report_state` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `8a8c2763286e18744c310dae342249a937773baff70889726935023a7089a0e3`.

```python
def prepare_report_state(final_state: dict) -> dict:
    """Return readable research without changing canonical state or memory inputs.

    Python callers may pass the state returned by propagate() here for the
    same labeled research shown by CLI/Markdown/HTML. Use the original state for
    decision consumers; this copy is for presentation only.
    """
    prepared = {**final_state, **enforce_publication(final_state)}
    if (prepared.get("evidence_quality") or {}).get("status") == "insufficient":
        diagnostics = dict(prepared.get("unvalidated_outputs") or {})
        for field in ("market_report", "sentiment_report", "news_report", "fundamentals_report"):
            raw = prepared.get(field)
            if raw:
                diagnostics.setdefault(field, raw)
                prepared[field] = (
                    "Analyst narrative is unvalidated for this REVIEW run. "
                    "The original text is retained in evidence.json diagnostics."
                )
        if diagnostics:
            prepared["unvalidated_outputs"] = diagnostics
        if isinstance(prepared.get("trader_investment_plan"), str):
            prepared["trader_investment_plan"] = label_legacy_trader_price(prepared["trader_investment_plan"])
        return prepared
    if not prepared.get("evidence_quality"):
        # New export commentary is presentation-only: never rewrite an old
        # decision or introduce a current assessment into publication/memory state.
        original = prepared.get("final_trade_decision")
        reason = "Legacy evidence was not validated; current source-only assessment unavailable."
        if isinstance(original, str) and original.strip() and reason not in original:
            from tradingagents.agents.valuation_comparison import render_price_implied_valuation

            section = render_price_implied_valuation({"status": "unavailable", "reason": reason})
            if "### What the price implies" in original:
                section = section.replace("### What the price implies", "### Current price-implied assessment", 1)
            prepared["final_trade_decision"] = original + "\n\n" + section
        if isinstance(prepared.get("trader_investment_plan"), str):
            prepared["trader_investment_plan"] = label_legacy_trader_price(prepared["trader_investment_plan"])
        return prepared
    originals = prepared.get("unvalidated_outputs") or {}

    def research(text):
        return (
            "### Unvalidated model research\n\n"
            "The following is model-authored research, not validated instructions. "
            "Its numbers, targets, allocations and execution proposals are unverified claims. "
            "The canonical rating, evidence scope, target result and sizing limits remain authoritative.\n\n"
            + text
        )

    for field in ("market_report", "sentiment_report", "news_report", "fundamentals_report",
                  "investment_plan", "trader_investment_plan", "final_trade_decision"):
        raw = originals.get(field)
        if field == "fundamentals_report":
            validation = prepared.get("financial_claim_validation") or {}
            if isinstance(validation, dict) and isinstance(validation.get("raw_report"), str):
                raw = validation["raw_report"] or raw
            if isinstance(raw, str):
                raw = analyst_prose(raw)
        if not isinstance(raw, str) or not raw:
            continue
        canonical = prepared.get(field) or ""
        if field in ("market_report", "sentiment_report", "news_report") or field == "fundamentals_report" and not prepared.get("canonical_financial_context"):
            canonical = ""
        prepared[field] = (
            ("### Canonical evidence and decision limits\n\n" + canonical + "\n\n")
            if canonical else ""
        ) + research(raw)
    for field in ("investment_debate_state", "risk_debate_state"):
        original = originals.get(field)
        if isinstance(original, dict):
            prepared[field] = {
                key: research(value) if isinstance(value, str) and value else value
                for key, value in original.items()
            }
            if field == "investment_debate_state":
                questions = (final_state.get(field) or {}).get("document_questions")
                if questions is not None:
                    prepared[field]["document_questions"] = questions
    scenarios = prepared.get("shared_valuation_scenarios")
    if scenarios:
        from tradingagents.agents.shared_valuation import render_shared_valuation

        table = render_shared_valuation(scenarios)
        if table:
            prepared["fundamentals_report"] = table + "\n\n" + (prepared.get("fundamentals_report") or "")
    if isinstance(prepared.get("trader_investment_plan"), str):
        prepared["trader_investment_plan"] = label_legacy_trader_price(prepared["trader_investment_plan"])
    return prepared
```


## `tradingagents/reporting.py` — complete `verified_publication` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `56a744124429804c1698110c9c8c9c1d2f533d4deb0d3dfbd4e1f5b6738d4cf9`.

```python
def verified_publication(config: dict, state: dict, ticker: str, asof: str):
    """Verify an existing disk publication against the complete original state.

    Missing records return None for ordinary new-run validation. Serialized
    publication markers never establish authority; corruption/mismatch raises.
    """
    from tradingagents.memory import publication

    if not state.get('run_id'):
        return None
    try:
        record = publication.load_record(config, state['run_id'])
    except FileNotFoundError:
        return None
    snapshot = publication.load_evidence(config, record)
    # Existing-record publish performs the full payload comparison, including
    # the full decision hash when the stored readable excerpt was truncated.
    checked = publication.publish(config, state, ticker, asof)
    return checked, snapshot
```


## `tradingagents/reporting.py` — complete `write_report_tree` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `7f2ec45bbdd5a872a809e62c9cd2532ab30e3bacde94fd35084630b17616a05f`.

```python
def write_report_tree(
    final_state: dict, ticker: str, save_path, settings: dict | None = None, html: bool = True,
    *, publication_config: dict | None = None,
) -> Path:
    """Save a completed run's reports to ``save_path``; return the complete-report path.

    ``settings`` (``TradingAgentsGraph.run_settings()``) adds what produced the run
    to the report's header. ``html`` also writes ``complete_report.html``, one
    self-contained page of the same report (#1419).
    """
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    with locked(save_path / ".report-export"):
        return _write_report_tree_locked(final_state, ticker, save_path, settings, html,
                                         publication_config=publication_config)
```


## `tradingagents/reporting.py` — complete `_write_report_tree_locked` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `2e3c32b32221373dafdb61affb64bb76e314b43f74c8755a4b3144cfb9b51538`.

```python
def _write_report_tree_locked(
    final_state: dict, ticker: str, save_path: Path, settings: dict | None, html: bool,
    *, publication_config: dict | None,
) -> Path:
    """Build and publish one report while holding its destination lock."""
    original_state = final_state
    frozen = (verified_publication(publication_config, final_state, ticker, final_state.get("trade_date"))
              if publication_config is not None else None)
    if publication_config is not None and final_state.get("publication_record") and frozen is None:
        raise ValueError("Claimed historical publication is missing from the configured store")
    original_quality = evidence_quality_snapshot(final_state)
    original_diagnostics = evidence_snapshot(final_state).get("raw_diagnostics", {})
    final_state = prepare_report_state(final_state)
    if frozen is not None:
        record, original_snapshot = frozen
        final_state["publication_record"] = {key: record[key] for key in ("decision_id", "published_at", "record_sha256")}
        final_state["report_view_note"] = ("Current validated presentation of a verified immutable publication. "
            "Display and current validation may differ from the original; evidence.json retains its original immutable snapshot. "
            "For this export, diagnostic references in the research text refer to companion diagnostics.json.")
    elif final_state.get("publication_record"):
        final_state["report_view_note"] = ("Historical publication identity not verified against a configured store. "
            "This export is a current validated projection, not an immutable publication snapshot.")
    _write_json(save_path / "quality.json", original_quality if frozen else evidence_quality_snapshot(final_state))
    _write_json(save_path / "evidence.json", original_snapshot if frozen else evidence_snapshot(final_state))
    if frozen:
        _write_json(save_path / "diagnostics.json", original_diagnostics)
    display_settings = (final_state.get("run_settings") if isinstance(final_state.get("run_settings"), dict)
                        else settings)
    parts = report_sections(final_state)
    from tradingagents.report_summary import resolve_summary

    summary = resolve_summary(summary_input_for_report(final_state, display_settings, parts),
                              final_state.get("executive_summary"))
    _write_json(save_path / "executive_summary.json",
                _summary_companion(final_state.get("executive_summary"), summary))
    if frozen:
        parts = [(heading, folder, [(agent, filename, text.replace("evidence.json diagnostics", "diagnostics.json"))
                                   for agent, filename, text in written])
                 for heading, folder, written in parts]
    anchors = historical_anchors(parts)
    sections = []
    for heading, folder, written in parts:
        (save_path / folder).mkdir(exist_ok=True)
        for _agent, filename, text in written:
            (save_path / folder / filename).write_text(text, encoding="utf-8")
        content = "\n\n".join(f'<a id="{anchors[folder]}-{index}"></a>\n### {agent}\n{text}'
                                for index, (agent, _filename, text) in enumerate(written, 1))
        sections.append(f'<a id="{anchors[folder]}"></a>\n## {heading}\n\n{content}')

    markdown_base = (
        f"# Trading Analysis Report: {_plain_markdown(ticker)}\n\n"
        + (f"- Analysis date: {_plain_markdown(final_state['trade_date'])}\n\n"
           if final_state.get("trade_date") else "")
        + _summary_markdown(summary) + "\n" + _contents_markdown(parts) + "\n"
        + _header(ticker, final_state, display_settings, metadata_only=True) + "\n\n".join(sections)
        + "\n\n---\n\n" + render_token_usage(final_state.get("run_metrics")) + "\n"
    )
    # Assess the original run record after the prepared presentation is known.
    # A claimed historical publication needs the configured store to establish
    # its identity, even if the report can still be exported without one.
    integrity = "unverified" if original_state.get("publication_record") and not frozen else "verified"
    from tradingagents import operational_audit as audit

    audit_path = None
    try:
        assessment = _operational_assessment(original_state, summary, integrity)
        audit_text = audit.render_audit(assessment)
        destination = _audit_filename(save_path, audit_text)
        if not destination.exists():
            _write_text(destination, audit_text)
        elif destination.read_text(encoding="utf-8") != audit_text:
            raise OSError("Operational audit content changed during export")
        audit_path = f"./{destination.name}"
    except Exception:
        assessment = _unavailable_assessment("The operational audit could not be completed for this export.")
    footer = audit.render_assessment(assessment, audit_path)
    markdown = markdown_base.rstrip() + "\n\n---\n\n" + footer + "\n"
    _write_text(save_path / "complete_report.md", markdown)
    if html:
        from tradingagents.report_html import _render_prepared_report

        page = _render_prepared_report(ticker, final_state, display_settings, parts, summary,
                                       diagnostics_sidecar=bool(frozen), assessment=assessment,
                                       audit_path=audit_path)
        _write_text(save_path / "complete_report.html", page)
    # A report is successful only when its final contents and linked companion
    # still match the bytes constructed from this prepared presentation.
    if audit_path and (save_path / audit_path).read_text(encoding="utf-8") != audit_text:
        raise OSError("Operational audit changed during export")
    return save_path / "complete_report.md"
```


## `tradingagents/report_html.py` — complete `_run_details` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `51c5e8779c4952d4e16a953233226fd0fb983a394062cae80e50250a61d27c05`.

```python
def _run_details(final_state: dict, settings: dict | None) -> list[tuple[str, str]]:
    """The run details as (label, value HTML); every value from the run is escaped."""
    publication = final_state.get("publication_record")
    label = "Export generated" if publication else "Generated"
    details = [(label, escape(datetime.now().strftime("%Y-%m-%d %H:%M")))]
    if publication:
        details.extend([
            ("Decision ID", escape(publication["decision_id"])),
            ("First published", escape(publication["published_at"])),
        ])
    if settings:
        s = settings.get
        for tier in ("deep", "quick"):
            provider = s(f"{tier}_think_provider") or s("llm_provider", "?")
            details.append(
                (f"{tier.capitalize()} model", _fields([provider, s(f"{tier}_think_llm", "?")]))
            )
        details.append(("Analysts", _fields(analyst_names(s("analysts")))))
        details.append(
            (
                "Debate rounds",
                " ".join(
                    (
                        _group("research", _fields([s("max_debate_rounds", "?")])),
                        _group("risk", _fields([s("max_risk_discuss_rounds", "?")])),
                    )
                ),
            )
        )
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        if vendors:
            details.append(
                (
                    "Data vendors",
                    " ".join(_group(_CATEGORY.get(k, k), _chain(v)) for k, v in vendors.items()),
                )
            )
        details.append(("Version", escape(f"TradingAgents {s('version', '?')}")))
        if s("source_hash"):
            details.append(("Source hash", escape(str(s("source_hash")))))
        for key, label in (("openai_reasoning_effort", "OpenAI/OpenRouter reasoning effort"),
                           ("anthropic_effort", "Anthropic effort"),
                           ("google_thinking_level", "Google thinking level")):
            if s(key):
                details.append((label, escape(str(s(key)))))
    if final_state.get("memory_note"):
        details.append(("Memory log", escape(final_state["memory_note"])))
    if not final_state.get("evidence_quality"):
        details.append(("Evidence", "Legacy export — financial evidence unvalidated"))
    return details
```


## `tradingagents/report_html.py` — complete `render_report` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `959ff013d527557a1c9ffeacff7eb1831ba0bea1e109c6a0e44457e72c72f8d1`.

```python
def render_report(ticker: str, final_state: dict, settings: dict | None, parts=None, *,
                  diagnostics_sidecar: bool = False) -> str:
    """Build a direct HTML export with current validation and no model calls."""
    prepared = prepare_report_state(final_state)
    parts = report_sections(prepared, None if prepared != final_state else parts)
    display_settings = (prepared.get("run_settings") if isinstance(prepared.get("run_settings"), dict)
                        else settings)
    from tradingagents.report_summary import resolve_summary

    summary = resolve_summary(summary_input_for_report(prepared, display_settings, parts),
                              prepared.get("executive_summary"))
    from tradingagents.reporting import _operational_assessment, _unavailable_assessment

    try:
        assessment = _operational_assessment(final_state, summary,
                    "unverified" if final_state.get("publication_record") else "not_applicable")
    except Exception:
        assessment = _unavailable_assessment("The operational audit could not be completed for this export.")
    return _render_prepared_report(ticker, prepared, display_settings, parts, summary,
                                   diagnostics_sidecar=diagnostics_sidecar, assessment=assessment)
```


## `tradingagents/report_html.py` — complete `_render_prepared_report` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `7998b4fecb480b53437375e1f401e2775633adcfae58e96b6ee7a9c764bf16cd`.

```python
def _render_prepared_report(ticker: str, final_state: dict, settings: dict | None, parts,
                            summary: dict, *, diagnostics_sidecar: bool = False,
                            assessment: dict | None = None, audit_path: str | None = None) -> str:
    """Render one already prepared and resolved presentation."""
    anchors = historical_anchors(parts)
    md = _markdown()
    rating = run_rating(final_state) if final_state.get("final_trade_decision") else ""
    tone = _TONE.get(rating, "review")
    date = final_state.get("trade_date", "")

    title = f'<span class="ticker">{escape(ticker)}</span>'
    if rating:
        title += f' <span class="rating {tone}">{escape(rating)}</span>'
    export_view = ("<p>" + escape(final_state["report_view_note"]) + "</p>"
                   if final_state.get("report_view_note") else
                   "<p>Historical publication identity not verified against a configured store; current validated projection.</p>"
                   if final_state.get("publication_record") else "")
    condition_summary = (md.render(render_condition_summary(final_state["decision_context"]))
                         if final_state.get("decision_context") else "")
    details = "".join(
        f'<div class="{"note" if label == "Memory log" else "detail"}">'
        f"<dt>{escape(label)}</dt><dd>{value}</dd></div>"
        for label, value in _run_details(final_state, settings)
    )

    contents, body = [], []
    for heading, folder, written in parts:
        anchor = anchors[folder]
        agents = "".join(
            f'<li><a href="#{anchor}-{m}"><span class="label">{escape(agent)}</span></a></li>'
            for m, (agent, _f, _t) in enumerate(written, 1)
        )
        numeral, _, name = heading.partition(". ")
        contents.append(
            f'<li><a href="#{anchor}"><span class="num">{escape(numeral)}</span> '
            f'<span class="label">{escape(name)}</span></a>'
            f'<span class="description">{escape(_DESCRIPTIONS[folder])}</span><ul>{agents}</ul></li>'
        )
        body.append(f'<section id="{anchor}"><h2>{escape(heading)}</h2>')
        for m, (agent, _filename, text) in enumerate(written, 1):
            if diagnostics_sidecar:
                text = text.replace("evidence.json diagnostics", "diagnostics.json")
            body.append(f'<h3 id="{anchor}-{m}">{escape(agent)}</h3>\n{_render_agent_text(md, text)}')
        body.append("</section>")

    summary_html = (
        '<section class="summary" aria-labelledby="executive-summary">'
        '<h2 id="executive-summary">Executive summary</h2>'
        f'<p>{escape(summary.get("process") or "")}</p>'
        f'<p>{escape(" ".join(summary.get("sentences") or []))}</p></section>'
    )

    if assessment is None:
        from tradingagents.reporting import _unavailable_assessment

        assessment = _unavailable_assessment("The operational audit was not available for this export.")
    from tradingagents.operational_audit import render_assessment

    audit_html = _markdown().render(render_assessment(assessment, audit_path))

    page_title = " ".join(x for x in (ticker, date, rating) if x)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src '{_copy_script_csp_hash()}'">
<title>{escape(page_title)}: TradingAgents report</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page" id="top">
<header class="masthead">
<button type="button" class="copy-all" id="copy-all" aria-label="Copy the full report as text" aria-live="polite">Copy All</button>
<a class="logo" href="{_COMPANY}" rel="noopener" aria-label="Tauric Research">{_LOGO}</a>
<h1>{title}</h1>
<p class="date">{escape(f"Analysis of {date}" if date else "Analysis")}</p>
</header>
{summary_html}
<nav class="contents" aria-label="Table of contents"><h2>Table of contents</h2><ul>{"".join(contents)}</ul></nav>
<aside class="report-meta" aria-label="Report details">
<div class="condition-summary">{condition_summary}</div>
<dl class="run">{details}</dl>
{export_view}
</aside>
<main>
{"".join(body)}
</main>
<p class="credit">{escape(render_token_usage(final_state.get("run_metrics")))}</p>
<footer class="credit"><a href="{_PROJECT}" rel="noopener">TradingAgents</a> powered by <a class="brand" href="{_ORG}" rel="noopener">Tauric Research</a></footer>
<a class="to-top" href="#top">Top</a>
<section class="operational-assessment" aria-label="Operational quality assessment">{audit_html}</section>
</div>
<script>{_COPY_SCRIPT}</script>
</body>
</html>
"""
```


## `tradingagents/report_html.py` — complete `_copy_script_csp_hash` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `c5cf8dc374e5995ee26845a58c68f9ce598d81ddbbf34bc8c3f48bad1d49ac87`.

```python
def _copy_script_csp_hash() -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(_COPY_SCRIPT.encode()).digest()).decode()
```


## `tradingagents/dataflows/vendors/yahoo/price_observation.py` — complete `_verify_adjustment_basis` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `80d784c26dba6d7413c72e19c2b63a48fafb7bc9417f93422ea9ff34f92ea4f6`.

```python
def _verify_adjustment_basis(raw):
    """Verify provider adjustment basis without publishing future action values."""
    cutoff = date.fromisoformat(raw["as_of"])
    zone = ZoneInfo(raw["metadata"]["exchangeTimezoneName"])
    today = _timestamp(raw["retrieved_at"]).astimezone(zone).date()
    if cutoff >= today:
        return None
    if (today - cutoff).days > 400:
        raise ValueError(
            "Historical adjustment basis unavailable beyond 400-day verification bound"
        )
    start = max(cutoff - timedelta(days=7), today - timedelta(days=400))

    def fetch():
        source = yf.Ticker(raw["ticker"])
        history = source.history(
            start=str(start),
            end=str(today + timedelta(days=1)),
            interval="1d",
            auto_adjust=False,
            actions=True,
        )
        return history, source.get_history_metadata()

    response = yf_retry(fetch)
    if response is None:
        raise ValueError("Historical adjustment basis verification unavailable")
    history, metadata = response
    if any(
        metadata.get(key) != raw["metadata"][key]
        for key in ("symbol", "currency", "exchangeTimezoneName")
    ):
        raise ValueError("Historical adjustment basis metadata mismatch")
    actions = []
    sessions = set()
    for index, row in history.iterrows():
        session = _timestamp(index.isoformat()).astimezone(zone).date()
        if session in sessions or not start <= session <= today:
            raise ValueError("Historical adjustment verification window invalid")
        sessions.add(session)
        ratio = _number(row["Stock Splits"])
        actions.append({"session_date": str(session), "stock_splits": ratio})
        if session > cutoff and Decimal(ratio) != 0:
            raise ValueError(
                "Historical quote adjustment basis is not compatible with the analysis cutoff"
            )
    if not sessions or min(sessions) > cutoff or (today - max(sessions)).days > 7:
        raise ValueError("Historical adjustment verification coverage unavailable")
    return {
        "status": "passed",
        "purpose": "provider adjustment verification, not as-of research evidence",
        "window_start": str(start),
        "window_end": str(today),
        "observed_at": raw["retrieved_at"],
        "source_payload_sha256": _hash(actions),
        "quote_payload_sha256": _hash(raw["bars"]),
        "returned_sessions": len(sessions),
    }
```


## `tradingagents/dataflows/vendors/yahoo/price_observation.py` — complete `session_is_complete` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `30f2dd99a6e98ac9185b3f7c85e12e1b8ead3b59f55134e1d36f3cd4373ba453`.

```python
def session_is_complete(session, retrieved_at, exchange_timezone, regular_end=None, cutoff=None):
    """Finality at acquisition, capped by the run's resolved observation instant.

    A stored pre-close bar never becomes final through elapsed wall-clock time.
    No exchange closing hour is guessed; same-day promotion needs provider end
    metadata. Prior dates retain the existing completed-session interpretation.
    """
    retrieved = _timestamp(retrieved_at)
    effective = min(retrieved, _timestamp(cutoff)) if cutoff else retrieved
    if not exchange_timezone:
        # With no instrument zone, require the date to have ended in even the
        # latest possible local timezone. Never call an unknown today's bar final.
        return session < (effective - timedelta(hours=12)).date()
    zone = ZoneInfo(exchange_timezone)
    today = effective.astimezone(zone).date()
    if session < today:
        return True
    if session != today or regular_end is None:
        return False
    end = _timestamp(regular_end)
    return end.astimezone(zone).date() == session and end <= effective
```


## `tradingagents/dataflows/files.py` — complete `replace_file` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `9582207554f80e19c489ffcec065387eb8bec0ac114c5022821f63e36869ea2f`.

```python
def replace_file(path, write: Callable[[str], None], *, strict: bool = False) -> None:
    """Write ``path`` through a uniquely named temp file beside it, then move it into place.

    A reader sees the old file or the new one, never a partial write, and two
    writers of the same path (tool calls run concurrently) never share a temp file.
    ``write`` receives the temp path and creates the file, so it gets the usual
    permissions. The file is a cache: where another reader holds it open (Windows),
    the old one stays and the write is skipped. Required writes set ``strict``
    so permission failures propagate to the caller.
    """
    path = Path(path)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write(str(temp))
        os.replace(temp, path)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        if strict:
            raise
        logger.warning("Kept the cached %s; it is in use (%s)", path.name, exc)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
```


## `cli/selections.py` — complete `_prompt_selections` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `efcbb4bcac9a3d979dfc1abd334d969c168615f27f25fe6bff3613577dff2ee4`.

```python
def _prompt_selections(prefs, flags):
    """Walk the selection steps. ``prefs`` prefills; flags and the environment skip."""
    with open(Path(__file__).parent / "static" / "welcome.txt", encoding="utf-8") as f:
        welcome_ascii = f.read()

    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Management\n\n"
    welcome_content += (
        "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"
    )

    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents",
        subtitle="Multi-Agents LLM Financial Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()
    console.print()  # Add vertical space before announcements

    # What's new comes from a cache refreshed in the background, and only for
    # someone at a terminal: a run never waits on it and unattended runs skip it.
    if updates.enabled():
        updates.show(console)
        updates.start_background_refresh()

    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    def thinking_value_or_prompt(env_var, config_key, label, box_title, box_body, prompt_fn):
        """Return the env-configured reasoning/thinking value, or prompt for it.

        When ``env_var`` is set the interactive choice is skipped and the value
        the env overlay placed on DEFAULT_CONFIG is used — mirroring the
        env-precedence rule applied to the other selection steps.
        """
        if os.environ.get(env_var):
            value = DEFAULT_CONFIG[config_key]
            console.print(f"[green]✓ {label} from environment:[/green] {value}")
            return value
        console.print(create_question_box(box_title, box_body))
        return prompt_fn()

    # Step 1: Ticker symbol
    if flags.get("ticker") is not None:
        selected_ticker = _from_flag(parse_ticker, flags["ticker"])
        console.print(f"[green]✓ Ticker from --ticker:[/green] {selected_ticker}")
    else:
        console.print(
            create_question_box(
                "Step 1: Ticker Symbol",
                "Enter the ticker, with exchange suffix when needed (e.g. SPY, 0700.HK, BTC-USD)",
                "SPY",
            )
        )
        selected_ticker = get_ticker()
    asset_type = detect_asset_type(selected_ticker)
    # Only announce when it's not the default stock path, to avoid printing
    # "stock" on every run.
    if asset_type.value != "stock":
        console.print(
            f"[green]Detected asset type:[/green] {asset_type.value}"
        )

    # Step 2: Analysis date
    if flags.get("date") is not None:
        analysis_date = _from_flag(parse_analysis_date, flags["date"])
        console.print(f"[green]✓ Analysis date from --date:[/green] {analysis_date}")
    else:
        default_date = datetime.datetime.now().strftime("%Y-%m-%d")
        console.print(
            create_question_box(
                "Step 2: Analysis Date",
                "Enter the analysis date (YYYY-MM-DD)",
                default_date,
            )
        )
        analysis_date = get_analysis_date()

    # Step 3: Output language (skipped when set via TRADINGAGENTS_OUTPUT_LANGUAGE)
    if os.environ.get("TRADINGAGENTS_OUTPUT_LANGUAGE"):
        output_language = DEFAULT_CONFIG["output_language"]
        console.print(
            f"[green]✓ Output language from environment:[/green] {output_language}"
        )
    else:
        console.print(
            create_question_box(
                "Step 3: Output Language",
                "Select the language for analyst reports and final decision"
            )
        )
        output_language = ask_output_language(prefs.get("output_language"))

    # Step 4: Select analysts
    prefs = sanitize(prefs, asset_type.value)
    if flags.get("analysts") is not None:
        selected_analysts = _from_flag(parse_analysts, flags["analysts"], asset_type)
    else:
        console.print(
            create_question_box(
                "Step 4: Analysts Team", "Select your LLM analyst agents for the analysis"
            )
        )
        selected_analysts = select_analysts(asset_type, prefs.get("analysts"))
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # Step 5: Research depth (skipped when both round counts are set via env).
    # Research depth maps to the debate + risk round counts; when both are
    # supplied through TRADINGAGENTS_MAX_DEBATE_ROUNDS / _MAX_RISK_ROUNDS we keep
    # the run non-interactive and honor the env values (#977).
    if depth_from_env():
        selected_research_depth = DEFAULT_CONFIG["max_debate_rounds"]
        console.print(
            f"[green]✓ Research depth from environment:[/green] "
            f"{DEFAULT_CONFIG['max_debate_rounds']} debate / "
            f"{DEFAULT_CONFIG['max_risk_discuss_rounds']} risk rounds"
        )
    else:
        console.print(
            create_question_box(
                "Step 5: Research Depth", "Select your research depth level"
            )
        )
        selected_research_depth = select_research_depth(prefs.get("research_depth"))

    # Step 6: LLM Provider (skipped when set via TRADINGAGENTS_LLM_PROVIDER).
    # The backend URL comes from TRADINGAGENTS_LLM_BACKEND_URL when set,
    # otherwise the provider's default endpoint — the same value the menu
    # would have picked.
    provider_from_env = bool(os.environ.get("TRADINGAGENTS_LLM_PROVIDER"))
    if provider_from_env:
        selected_llm_provider = DEFAULT_CONFIG["llm_provider"].lower()
        backend_url = resolve_backend_url(
            selected_llm_provider, env_url=DEFAULT_CONFIG["backend_url"]
        )
        console.print(f"[green]✓ LLM provider from environment:[/green] {selected_llm_provider}")
        console.print(f"[green]✓ Backend URL:[/green] {backend_url}")
    else:
        console.print(
            create_question_box(
                "Step 6: LLM Provider", "Select your LLM provider"
            )
        )
        selected_llm_provider, backend_url = select_llm_provider(prefs.get("llm_provider"))

        # Providers with regional endpoints prompt for the region as a secondary
        # step so the main dropdown stays clean (mainland China and international
        # accounts cannot share API keys).
        if selected_llm_provider == "qwen":
            selected_llm_provider, backend_url = ask_qwen_region()
        elif selected_llm_provider == "minimax":
            selected_llm_provider, backend_url = ask_minimax_region()
        elif selected_llm_provider == "glm":
            selected_llm_provider, backend_url = ask_glm_region()

        # Honor an explicit env backend URL even when the provider was chosen
        # interactively, so it isn't overwritten by the menu default (#978).
        backend_url = resolve_backend_url(
            selected_llm_provider, backend_url, env_url=DEFAULT_CONFIG["backend_url"]
        )

        # The generic OpenAI-compatible endpoint has no default; ask for it if
        # neither the menu nor the environment supplied one.
        if selected_llm_provider == "openai_compatible" and not backend_url:
            remembered_url = (prefs.get("backend_url")
                              if prefs.get("llm_provider") == selected_llm_provider else None)
            backend_url = prompt_openai_compatible_url(remembered_url)

        # For Ollama, surface the resolved endpoint (OLLAMA_BASE_URL vs default)
        # before model selection so it's obvious where we're connecting.
        if selected_llm_provider == "ollama":
            confirm_ollama_endpoint(backend_url)


    _check_tier_providers(selected_llm_provider, backend_url)

    # Step 7: Thinking agents (skipped when either model is set via environment)
    if os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM"):
        selected_shallow_thinker = DEFAULT_CONFIG["quick_think_llm"]
        selected_deep_thinker = DEFAULT_CONFIG["deep_think_llm"]
        console.print(
            f"[green]✓ Thinking agents from environment:[/green] "
            f"quick={selected_shallow_thinker}, deep={selected_deep_thinker}"
        )
    else:
        console.print(
            create_question_box(
                "Step 7: Thinking Agents", "Select your thinking agents for analysis"
            )
        )
        remembered = prefs if prefs.get("llm_provider") == selected_llm_provider else {}
        selected_shallow_thinker = select_shallow_thinking_agent(
            selected_llm_provider, remembered.get("quick_think_llm")
        )
        selected_deep_thinker = select_deep_thinking_agent(
            selected_llm_provider, remembered.get("deep_think_llm")
        )

    # Step 8: Provider-specific reasoning/thinking configuration. Each knob is
    # settable via its TRADINGAGENTS_* env var; when that var is set (or the
    # provider itself came from env) the prompt is skipped and the configured
    # value is used — same env-precedence rule as the steps above. None = each
    # provider's own default.
    thinking_level = None
    reasoning_effort = None
    anthropic_effort = None

    provider_lower = selected_llm_provider.lower()
    if provider_from_env:
        thinking_level = DEFAULT_CONFIG["google_thinking_level"]
        reasoning_effort = DEFAULT_CONFIG["openai_reasoning_effort"]
        anthropic_effort = DEFAULT_CONFIG["anthropic_effort"]
    elif provider_lower == "google":
        thinking_level = thinking_value_or_prompt(
            "TRADINGAGENTS_GOOGLE_THINKING_LEVEL", "google_thinking_level",
            "Gemini thinking mode", "Step 8: Thinking Mode",
            "Configure Gemini thinking mode", ask_gemini_thinking_config,
        )
    elif provider_lower in REASONING_EFFORT_PROVIDERS:
        reasoning_effort = thinking_value_or_prompt(
            "TRADINGAGENTS_OPENAI_REASONING_EFFORT", "openai_reasoning_effort",
            "Reasoning effort", "Step 8: Reasoning Effort",
            "Configure OpenAI reasoning effort level", ask_openai_reasoning_effort,
        )
    elif provider_lower == "anthropic":
        anthropic_effort = thinking_value_or_prompt(
            "TRADINGAGENTS_ANTHROPIC_EFFORT", "anthropic_effort",
            "Claude effort", "Step 8: Effort Level",
            "Configure Claude effort level", ask_anthropic_effort,
        )

    return {
        "ticker": selected_ticker,
        "asset_type": asset_type.value,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "quick_think_llm": selected_shallow_thinker,
        "deep_think_llm": selected_deep_thinker,
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
        "anthropic_effort": anthropic_effort,
        "output_language": output_language,
    }
```


## `tradingagents/agents/tools.py` — complete `_retained_source_package` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `e9e830b5bc1e49823bb75ef4078a7b895890cb7d54487028371a76caaa378085`.

```python
def _retained_source_package(ticker, cutoff, state, field):
    """A present acquisition record forbids fetching a replacement source vintage."""
    if not state or "evidence_acquisition" not in state:
        return None
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    from tradingagents.dataflows.symbols import normalize_symbol
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    record = state["evidence_acquisition"]
    if (record.get("schema_version") != 1 or record.get("ticker") != normalize_symbol(ticker)
            or record.get("as_of") != str(cutoff)):
        raise VendorUnavailableError("Requested issuer or cutoff differs from retained source evidence; no newer source was fetched",
                                     reason_code="retained_scope_mismatch")
    if record.get("status") != "ready":
        raise VendorUnavailableError("Retained source evidence unavailable", reason_code="retained_source_unavailable")
    if field == "filing_evidence" and record.get("disclosure_error"):
        raise VendorUnavailableError("Retained filing evidence unavailable", reason_code="retained_filing_unavailable")
    if field == "financial_evidence" and not any(
        check.get("code") == "source_integrity" and check.get("status") == "pass"
        for check in record.get("source_checks", ())
    ):
        raise VendorUnavailableError("Retained financial source integrity is not established",
                                     reason_code="retained_integrity_unavailable")
    try:
        model = EvidencePackage if field == "financial_evidence" else DisclosurePackage
        package = model.model_validate(state.get(field))
        raw_cik = (record.get("raw_financial_evidence") or {}).get("cik")
        if str(package.as_of) != str(cutoff) or package.cik != raw_cik:
            raise ValueError("Retained source package issuer/cutoff mismatch")
        return package
    except (ValueError, TypeError) as exc:
        raise VendorUnavailableError("Retained source package unavailable or invalid; no replacement vintage fetched",
                                     reason_code="retained_package_invalid") from exc
```


## `tradingagents/agents/evidence_validation.py` — complete `create_source_acquisition` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `f5ef1fa91ee11b41bc59f0e3c441cdd3842f4c8bbcec8b20abd468e93b04ceeb`.

```python
def create_source_acquisition(selected_analysts):
    """Acquire one source vintage before analyst fan-out; never authorize publication."""
    from tradingagents.dataflows.errors import NoMarketDataError, VendorError
    from tradingagents.dataflows.router import no_data_available
    from tradingagents.dataflows.vendors import sec_documents, sec_edgar
    from tradingagents.operational_capture import record_operation

    def acquire(state):
        scope = _acquisition_scope(state, selected_analysts)
        retained = state.get("evidence_acquisition")
        if retained is not None:
            if any(retained.get(key) != value for key, value in scope.items()):
                raise ValueError("Retained evidence acquisition differs from run scope; start a fresh run")
            return {}  # A compatible resumed node must never replace its vintage.
        record = {**scope, "status": "not_applicable", "reason": "",
                  "raw_financial_evidence": None, "disclosure_error": None,
                  "rpo_comparison": None, "source_checks": []}
        update = {}
        if "fundamentals" not in selected_analysts:
            record["reason"] = "Fundamentals not selected; no US accounting validation performed"
        elif scope["asset_type"] != "stock":
            record["reason"] = "Non-stock asset; US-filer accounting checks do not apply"
        else:
            try:
                mapped_cik = sec_edgar.cik_for(scope["ticker"])
                if mapped_cik is None:
                    record["status"] = "unavailable"
                    record["reason"] = (
                        "Stock not identified in SEC issuer map; issuer filing status cannot be verified "
                        "and US accounting validation was not performed"
                    )
                else:
                    package = sec_edgar.get_financial_evidence(scope["ticker"], scope["as_of"])
                    if package.cik != mapped_cik or str(package.as_of) != scope["as_of"]:
                        raise ValueError("SEC financial package issuer or cutoff differs from requested instrument")
                    record["raw_financial_evidence"] = package.model_dump(mode="json")
                    record["status"] = "ready"
                    update["issuer_identity"] = {"ticker": scope["ticker"], "cik": mapped_cik,
                                                "as_of": scope["as_of"], "source": "SEC issuer map"}
                    disclosures = None
                    try:
                        disclosures = sec_documents.get_filing_evidence(scope["ticker"], scope["as_of"])
                        if disclosures.cik != package.cik or str(disclosures.as_of) != scope["as_of"]:
                            raise ValueError("SEC filing package issuer or cutoff differs from requested instrument")
                    except (VendorError, ValidationError, ValueError) as exc:
                        record_operation("vendor_no_data" if isinstance(exc, NoMarketDataError) else "vendor_unavailable", scope="SEC filings")
                        record["disclosure_error"] = (
                            f"SEC filing unavailable: {no_data_available(exc)}" if isinstance(exc, NoMarketDataError)
                            else f"SEC filing unavailable ({type(exc).__name__})")
                        disclosures = None
                    if disclosures is not None:
                        from tradingagents.agents.kpi_comparisons import retrieve_rpo_comparison

                        record["rpo_comparison"] = retrieve_rpo_comparison(scope["ticker"], disclosures)
                    from tradingagents.agents.document_access import prepare_document_sources

                    if disclosures is not None:
                        update["filing_evidence"] = disclosures.model_dump(mode="json")
                    update.update(prepare_document_sources({**state, **update}, selected_analysts))
                    prepared = assess_financial_package(
                        {**state, **update}, package, disclosures, record["disclosure_error"],
                        rpo_comparison=record["rpo_comparison"], source_only=True,
                    )
                    record["source_checks"] = prepared.pop("source_checks")
                    update.update(prepared)
            except (VendorError, ValidationError, ValueError) as exc:
                record_operation("vendor_no_data" if isinstance(exc, NoMarketDataError) else "vendor_unavailable", scope="SEC financial acquisition")
                record["status"] = "unavailable"
                record["reason"] = (
                    f"SEC unavailable: {no_data_available(exc)}" if isinstance(exc, NoMarketDataError)
                    else f"SEC unavailable ({type(exc).__name__})")
        # Price is independent of financial scope and critical-accounting status.
        from tradingagents.dataflows.config import get_config
        from tradingagents.dataflows.vendors.yahoo.price_observation import (
            completed_price_scope,
            get_price_observation,
        )

        config = get_config()
        chain = config.get("tool_vendors", {}).get("get_stock_data") or config.get("data_vendors", {}).get("core_stock_apis", "")
        if "yfinance" in {name.strip() for name in str(chain).split(",")}:
            dates = [date.fromisoformat(f["period_end"])
                     for f in update.get("financial_evidence", {}).get("facts", [])
                     if f["metric"] == "Cash and Equivalents" and f.get("value") is not None
                     and f.get("period_start") is None]
            with completed_price_scope(state):
                update["price_observation"] = get_price_observation(
                    scope["ticker"], scope["as_of"], max(dates, default=None))
        else:
            update["price_observation"] = {"status": "unavailable",
                "reason": "No supported dated-close provider is configured; no additional vendor was used"}
        update["evidence_acquisition"] = record
        from tradingagents.agents.document_access import prepare_document_sources

        update.update(prepare_document_sources({**state, **update}, selected_analysts))
        from tradingagents.agents.filing_terms import prepare_filing_terms

        update.update(prepare_filing_terms({**state, **update}))
        from tradingagents.agents.transcript_access import prepare_transcript_sources

        update.update(prepare_transcript_sources({**state, **update}, selected_analysts))
        from tradingagents.agents.valuation_reference_flow import acquire_reference_inputs

        update.update(acquire_reference_inputs({**state, **update}, config))
        from tradingagents.agents.context import build_shared_source_brief

        update["shared_source_brief"] = build_shared_source_brief({**state, **update})
        return update

    return acquire
```


## `tradingagents/agents/document_access.py` — complete `prepare_document_sources` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `4157d46f4d3504390de519de05e4f713bd39e504afb8eda62d576fbe4865e5b4`.

```python
def prepare_document_sources(state, selected_analysts) -> dict:
    """Acquire once during fresh SourceAcquisition; resumed runs keep their vintage."""
    if state.get("document_sources") is not None:
        validated_document_corpus(state)
        return {}
    scope = _scope(state)
    record = {
        **scope, "status": "not_applicable", "cik": None,
        "corpus": None, "corpus_hash": None, "reason": "",
    }
    if scope["asset_type"] != "stock":
        record["reason"] = "SEC document search applies only to stock issuers"
        return {"document_sources": record}
    if not _ROLES.intersection(selected_analysts):
        record["reason"] = "No filing-using analyst selected"
        return {"document_sources": record}

    bounded = state.get("filing_evidence")
    try:
        bounded_package = DisclosurePackage.model_validate(bounded) if bounded else None
        if bounded_package is not None:
            _check_corpus(bounded_package, scope, (state.get("issuer_identity") or {}).get("cik"), strict_identity=False)
        from tradingagents.dataflows.vendors.sec_documents import get_filing_search_evidence
        corpus = get_filing_search_evidence(
            scope["ticker"], scope["as_of"], bounded_package=bounded_package
        )
        omitted = [doc for doc in corpus.documents if _intraday_unproven(doc, scope)]
        if omitted:
            corpus = corpus.model_copy(update={
                "documents": tuple(doc for doc in corpus.documents if doc not in omitted),
                "gaps": (*corpus.gaps, *(
                    f"{doc.filing.accession} {doc.url}: omitted; same-day publication time unavailable at intraday cutoff"
                    for doc in omitted)),
            })
        _check_corpus(corpus, scope, (state.get("issuer_identity") or {}).get("cik"))
    except VendorError as exc:
        reason = (f"SEC unavailable: {no_data_available(exc)}" if isinstance(exc, NoMarketDataError)
                  else f"SEC unavailable ({type(exc).__name__})")
        record.update(status="unavailable", reason=reason)
        return {"document_sources": record}
    except ValidationError as exc:
        raise ValueError("Malformed bounded filing evidence") from exc

    record.update(
        status="ready", cik=corpus.cik, corpus=corpus.model_dump(mode="json"),
        corpus_hash=corpus_hash(corpus),
    )
    return {"document_sources": record}
```


## `tradingagents/agents/transcript_access.py` — complete `prepare_transcript_sources` body

Commit `da6f1876adc5ac37b015baa1f8e5f7244421c34e`; excerpt SHA-256 `f97087475fa335099dcf5e962111b33040f3efd23c18611dd443fc33b206a420`.

```python
def prepare_transcript_sources(state, selected_analysts) -> dict:
    """Acquire only once on a fresh stock F/N run; resume validates its snapshot."""
    if state.get("transcript_sources") is not None:
        validated_transcript_record(state)
        return {}
    scope = _scope(state)
    if scope["asset_type"] != "stock":
        return {"transcript_sources": _wrapper(
            scope, None, status="not_applicable",
            reason="Earnings-call transcripts apply only to stock issuers",
        )}
    if not _ROLES.intersection(selected_analysts):
        return {"transcript_sources": _wrapper(
            scope, None, status="not_applicable",
            reason="No transcript-using analyst selected",
        )}
    corpus = validated_document_corpus(state)
    if corpus is None:
        reason = (state.get("document_sources") or {}).get("reason") or "Retained SEC earnings exhibit unavailable"
        return {"transcript_sources": _wrapper(
            scope, None, status="unavailable", reason=reason,
        )}
    cutoff_utc = scope["analysis_clock"].get("cutoff_utc")
    try:
        record = vendor_transcript.get_latest_transcript_evidence(
            scope["ticker"], scope["as_of"], filing_corpus=corpus,
            cutoff_utc=cutoff_utc, allow_network=True,
        )
    except (VendorError, requests.RequestException, TimeoutError, ValueError):
        record = None
    if not isinstance(record, dict) or record.get("status") != "ready":
        reason = "Transcript provider or cache unavailable"
        return {"transcript_sources": _wrapper(
            scope, corpus, status="unavailable", reason=reason,
        )}
    try:
        vendor_transcript._check_record(record)
        selected = vendor_transcript.select_latest_eligible_call(
            corpus, scope["as_of"], cutoff_utc=cutoff_utc,
        )
        if (
            selected["status"] != "ready"
            or selected["fiscal_quarter"] != record.get("fiscal_quarter")
            or selected["date_evidence"] != record.get("date_evidence")
            or record.get("ticker") != scope["ticker"]
        ):
            raise ValueError("Transcript SEC date or run scope mismatch")
    except (KeyError, TypeError, ValueError):
        return {"transcript_sources": _wrapper(
            scope, corpus, status="unavailable",
            reason="Transcript source or SEC date pin invalid",
        )}
    return {"transcript_sources": _wrapper(
        scope, corpus, status="ready", reason="", record=record,
    )}
```
