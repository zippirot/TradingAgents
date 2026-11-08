"""Running one analysis from the CLI: build the graph, stream it into the live view, save the report."""

import hashlib
import json
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
from tradingagents.attempt_trace import AttemptRecorder
from tradingagents.comparison_snapshot import capture_starting_snapshot, clone_starting_snapshot
from tradingagents.dataflows.date_window import resolve_analysis_cutoff
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import (
    build_analyst_execution_plan,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph, record_attempt_event
from tradingagents.source_replay import ReplaySession, current_session, session_context, set_session

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
            with session_context(None):
                succeeded = False
                try:
                    result = function(*args, **kwargs)
                    succeeded = True
                    return result
                finally:
                    session = current_session()
                    if session:
                        session.finish(succeeded)
        finally:
            for name, method in methods.items():
                setattr(message_buffer, name, method)
            cleanup_run_logging()
    return invoke


def _prepare_attempt_comparison(config, results_dir, selections, recorder):
    """Snapshot before graph construction; candidates get fresh pre-baseline stores."""
    if not recorder.enabled:
        return config
    baseline = os.getenv("TRADINGAGENTS_REPLAY_TRACE")
    config = dict(config)
    if baseline:
        config.update(clone_starting_snapshot(
            Path(baseline).expanduser().resolve() / "comparison-start",
            (results_dir / "comparison-run").resolve()))
        # Inputs are replayed; opaque model outputs from a checkpoint are not.
        config["checkpoint_enabled"] = False
    roots = {key: str(Path(config[key]).expanduser().resolve())
             for key in ("results_dir", "data_cache_dir", "memory_log_path")}
    manifest = capture_starting_snapshot(roots, (results_dir / "comparison-start").resolve())
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    clock = resolve_analysis_cutoff(str(selections["analysis_date"]),
                                   config.get("analysis_timezone", "America/Denver"),
                                   config.get("analysis_cutoff_utc"))
    scope = {"ticker": selections["ticker"], "analysis_date": str(selections["analysis_date"]),
             "asset_type": selections["asset_type"], "analysis_clock": clock,
             "starting_snapshot_sha256": digest,
             "settings": {key: config.get(key) for key in (
                 "quick_think_llm", "deep_think_llm", "llm_provider", "deep_think_provider",
                 "max_debate_rounds", "max_risk_discuss_rounds", "output_language")}}
    set_session(ReplaySession(recorder, scope, baseline=Path(baseline).expanduser().resolve() if baseline else None))
    return config


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
    attempt_recorder = AttemptRecorder(results_dir, attempt_id)
    config = _prepare_attempt_comparison(config, results_dir, selections, attempt_recorder)

    # Normalize analyst selection to predefined order (selection is a 'set', order is fixed)
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]
    analyst_execution_plan = build_analyst_execution_plan(selected_analyst_keys)
    analyst_wall_time_tracker = AnalystWallTimeTracker(analyst_execution_plan)

    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler, attempt_recorder],
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
        args = graph.propagator.get_graph_args(callbacks=[stats_handler, attempt_recorder])

        # Recompile with a checkpointer and inject the thread_id so --checkpoint
        # actually saves and resumes on the CLI path (#1249); a no-op when
        # checkpointing is disabled. Torn down in the finally below.
        checkpoint_tid = graph.begin_checkpoint(
            selections["ticker"], selections["analysis_date"], selections["asset_type"], portfolio
        )
        if checkpoint_tid is not None:
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_tid
            _announce_checkpoint_state(graph, selections["ticker"], selections["analysis_date"])
            if current_session():
                current_session().checkpoint_resumed = bool(getattr(graph, "_resuming", False))

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
            session = current_session()
            if session:
                final_state["replay_context"] = {"status": session.status, "scope": session.scope,
                                                  "checkpoint_resumed": session.checkpoint_resumed,
                                                  "misses": list(session.misses)}
                if session.misses:
                    from tradingagents.operational_audit import merge_observations, observation

                    event = observation(final_state, "Source Replay", code="replay_miss",
                                        scope="mixed-input comparison", count=len(session.misses))
                    final_state["operational_observations"] = merge_observations(
                        final_state.get("operational_observations"), {event["event_id"]: event})

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
    default = Path(default).resolve()
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
