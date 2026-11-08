"""Offline native CLI replay for Build D. No provider, network or paid model calls."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langgraph.config import get_config as graph_config

import cli.run as cli_run
from cli.models import AnalystType
from tradingagents.agents.audit_pass import AuditOutput
from tradingagents.agents.schemas import (
    RequiredHorizonPortfolioDecision,
    ResearchPlan,
    TraderProposal,
)
from tradingagents.dataflows.vendors.yahoo import ohlcv, price_observation
from tradingagents.graph import trading_graph

DAY = "2026-11-06"
SECRET = "OFFLINE_SECRET_DO_NOT_PERSIST"


class OfflineModel(Runnable):
    def __init__(self, calls, control, schema=None):
        self.calls = calls
        self.control = control
        self.schema = schema

    def bind_tools(self, tools):
        return self

    def get_llm(self):
        return self

    def with_structured_output(self, schema, **kwargs):
        return OfflineModel(self.calls, self.control, schema)

    def invoke(self, prompt, config=None, **kwargs):
        node = graph_config().get("metadata", {}).get("langgraph_node", "unknown")
        self.calls.append((node, self.schema.__name__ if self.schema else "text"))
        if node == "Trader" and self.control.pop("interrupt_trader", False):
            raise KeyboardInterrupt("offline checkpoint interruption")
        if node == "agent" and sum(name == "agent" for name, _ in self.calls) == 1:
            return AIMessage(content="", tool_calls=[{"name": "get_stock_data",
                "args": {"start_date": "2026-11-05", "end_date": DAY}, "id": "offline-price-1"}])
        if self.schema is ResearchPlan:
            return ResearchPlan(recommendation="Hold", rationale="Recorded market data was thin.",
                                strategic_actions="Wait for more evidence.")
        if self.schema is TraderProposal:
            return TraderProposal(action="Hold", reasoning="Recorded market data was thin.")
        if self.schema is RequiredHorizonPortfolioDecision:
            return RequiredHorizonPortfolioDecision(
                rating="Hold", executive_summary="Offline review of recorded prices.",
                investment_thesis="Evidence is limited.", time_horizon="3 months",
                no_case_reason="No grounded valuation case was available.")
        if self.schema is AuditOutput:
            return AuditOutput(findings=[])
        return AIMessage(content="Offline fixture narrative; no unsupported numeric claim.",
                         usage_metadata={"input_tokens": 17, "output_tokens": 9, "total_tokens": 26})


class OfflineTicker:
    def __init__(self, copied_source):
        self.copied_source = copied_source
        self.retained = json.loads(pd.read_csv(copied_source, nrows=1)["__market_source"].iloc[0])

    @property
    def info(self):
        return {"longName": "DOCN recorded source", "quoteType": "EQUITY"}

    def get_history_metadata(self):
        return {"symbol": "DOCN", "exchangeTimezoneName": self.retained["exchange_timezone"],
                "currency": self.retained["currency"],
                "currentTradingPeriod": {"regular": {
                    "end": pd.Timestamp(self.retained["regular_end"]).timestamp()}}}

    def history(self, **kwargs):
        recorded = pd.read_csv(self.copied_source)
        dates = pd.to_datetime(recorded.pop("Date"), utc=True).dt.tz_convert("America/New_York")
        recorded = recorded.drop(columns=["__market_source"])
        recorded.index = pd.DatetimeIndex(dates, name="Date")
        # The retained CSV has no action column. This explicit zero-action
        # simulation proves CLI wiring only, not real historical comparability.
        recorded["Stock Splits"] = 0
        start, end = pd.Timestamp(kwargs["start"]).date(), pd.Timestamp(kwargs["end"]).date()
        return recorded[(recorded.index.date >= start) & (recorded.index.date < end)]


def _deny_network(*args, **kwargs):
    raise AssertionError("offline proof blocked network access")


def _store_hashes(config):
    paths = [Path(config["memory_log_path"])]
    for root in (Path(config["results_dir"]) / "publications", Path(config["data_cache_dir"])):
        paths.extend(path for path in root.rglob("*") if path.is_file())
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}


def _comparison_pair(root, cfg, common_flags):
    """Run the actual CLI twice, then inspect the candidate's reopened publication."""
    pair_config = {**cfg, "results_dir": "comparison-results",
                   "data_cache_dir": str(root / "comparison-input-cache"),
                   "memory_log_path": str(root / "comparison-input-memory.md")}
    calls, control = [], {}
    with patch.object(cli_run, "DEFAULT_CONFIG", pair_config), \
         patch.object(trading_graph, "create_tier_client", side_effect=lambda *a, **k: OfflineModel(calls, control)):
        cli_run.run_analysis(checkpoint=False, flags={**common_flags, "save": True})
        attempts_root = root / "comparison-results" / "DOCN" / DAY
        baseline = next(attempts_root.glob("*-*"))
        protected = _store_hashes(pair_config)
        calls.clear()
        with patch.dict(os.environ, {"TRADINGAGENTS_REPLAY_TRACE": str(baseline)}):
            cli_run.run_analysis(checkpoint=False, flags={**common_flags, "save": True})
        candidate = next(path for path in attempts_root.glob("*-*") if path != baseline)
    assert _store_hashes(pair_config) == protected
    original_manifest = json.loads((baseline / "comparison-start/manifest.json").read_text())
    candidate_manifest = json.loads((candidate / "comparison-start/manifest.json").read_text())
    assert candidate_manifest == original_manifest
    candidate_state = json.loads((candidate / "comparison-run/DOCN/TradingAgentsStrategy_logs"
                                 / f"full_states_log_{DAY}.json").read_text())
    assert candidate_state["replay_context"]["status"] == "replayed"
    assert candidate_state["replay_context"]["misses"] == []
    rows = [json.loads(line) for path in (candidate / "trace").glob("*.jsonl")
            for line in path.read_text().splitlines()]
    assert any(row["event"] == "source_replayed" for row in rows)
    assert all(row["event"] != "replay_miss" for row in rows)
    assert all(SECRET not in path.read_text(errors="ignore") for path in candidate.rglob("*") if path.is_file())
    assert (candidate / "reports/complete_report.html").is_file()
    return {"baseline": str(baseline), "candidate": str(candidate),
            "source_replay_hits": sum(row["event"] == "source_replayed" for row in rows),
            "replay_misses": 0, "starting_snapshot_equal": True,
            "baseline_stores_unchanged_by_candidate": True,
            "candidate_publication_id": candidate_state["publication_record"]["decision_id"],
            "candidate_state_sha256": hashlib.sha256(json.dumps(candidate_state, sort_keys=True).encode()).hexdigest()}


def main():
    calls = []
    control = {}
    with contextlib.nullcontext(tempfile.mkdtemp(prefix="ta-operations-proof-")) as scratch:
        root = Path(scratch)
        original = Path.home() / ".tradingagents/cache/DOCN-YFin-data.csv"
        assert original.is_file(), "recorded DOCN cache is required for this private offline proof"
        original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
        source_copy = root / "recorded" / original.name
        source_copy.parent.mkdir()
        shutil.copyfile(original, source_copy)
        source_copy.chmod(0o444)
        assert hashlib.sha256(source_copy.read_bytes()).hexdigest() == original_hash
        source_data = pd.read_csv(source_copy)
        source_close = round(float(source_data.loc[source_data["Date"].str.startswith(DAY), "Close"].iloc[0]), 2)
        cfg = deepcopy(cli_run.DEFAULT_CONFIG)
        cfg.update(results_dir="results", data_cache_dir=str(root / "cache"),
                   memory_log_path=str(root / "memory.md"), checkpoint_enabled=True,
                   max_debate_rounds=1, max_risk_discuss_rounds=1, max_tool_rounds=1,
                   input_cost_per_million=1.0, output_cost_per_million=2.0)
        selections = {"ticker": "DOCN", "analysis_date": DAY, "asset_type": "stock",
                      "analysts": [AnalystType.MARKET], "research_depth": 1,
                      "quick_think_llm": "offline-quick", "deep_think_llm": "offline-deep",
                      "backend_url": None, "llm_provider": "openai", "output_language": "English"}
        stream = io.StringIO()
        with contextlib.chdir(root), \
             patch.object(cli_run, "DEFAULT_CONFIG", cfg), \
             patch.object(cli_run, "get_user_selections", return_value=selections), \
             patch.object(trading_graph, "create_tier_client", side_effect=lambda *a, **k: OfflineModel(calls, control)), \
             patch.object(trading_graph, "resolve_instrument_identity", return_value={"company_name": "DOCN recorded source"}), \
             patch.object(price_observation, "get_price_observation", return_value={"status": "unavailable", "reason": "Canonical price observation not replayed in this proof"}), \
             patch.object(ohlcv.yf, "Ticker", side_effect=lambda *a, **k: OfflineTicker(source_copy)), \
             patch.object(socket.socket, "connect", _deny_network), \
             patch.object(socket, "create_connection", _deny_network), \
             patch.dict(os.environ, {"OPENAI_API_KEY": SECRET, "TRADINGAGENTS_NO_UPDATE_CHECK": "1",
                                    "TRADINGAGENTS_TRACE": "1",
                                    "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
                                    "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
                                    "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
                                    "TRADINGAGENTS_LLM_PROVIDER": "openai",
                                    "TRADINGAGENTS_QUICK_THINK_LLM": "offline-quick"}, clear=True), \
             contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            common_flags = {"ticker": "DOCN", "date": DAY, "analysts": "market",
                            "show": False, "html": True}
            cli_run.run_analysis(checkpoint=True, flags={**common_flags, "save": True})
            comparison_receipt = _comparison_pair(root, cfg, common_flags)
            original_save = trading_graph.TradingAgentsGraph.save_reports
            save_calls = []

            def fail_once(graph, *args, **kwargs):
                save_calls.append(1)
                if len(save_calls) == 1:
                    raise OSError(SECRET)
                return original_save(graph, *args, **kwargs)

            answers = iter(["Y", "", "Y", ""])

            def prompt_answer(*args, **kwargs):
                answer = next(answers)
                return kwargs.get("default", "") if answer == "" else answer

            with patch.object(cli_run.sys, "stdin", SimpleNamespace(isatty=lambda: True)), \
                 patch.object(cli_run.typer, "prompt", side_effect=prompt_answer), \
                 patch.object(cli_run, "_graphical_browser", return_value=None), \
                 patch.object(trading_graph.TradingAgentsGraph, "save_reports", fail_once):
                cli_run.run_analysis(checkpoint=True, flags={**common_flags, "save": None})
            assert len(save_calls) == 2, "interactive save must retry once"

            control["interrupt_trader"] = True
            try:
                cli_run.run_analysis(checkpoint=True, flags={**common_flags, "save": True})
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("real graph interruption was not raised")
            cli_run.run_analysis(checkpoint=True, flags={**common_flags, "save": True})
        attempts = sorted((root / "results" / "DOCN" / DAY).glob("*-*"))
        state_dir = root / "results" / "DOCN" / "TradingAgentsStrategy_logs"
        latest = state_dir / f"full_states_log_{DAY}.json"
        archives = sorted(state_dir.glob(f"full_states_log_{DAY}_*.json"))
        reports = [item / "reports" for item in attempts]
        complete_pages = sorted(root.glob("results/DOCN/*/*/reports*/complete_report.md"))
        reopened_reports = [page.read_text() for page in complete_pages]
        latest_state = json.loads(latest.read_text()) if latest.is_file() else {}
        archive_states = [json.loads(path.read_text()) for path in archives]
        event_rows = [json.loads(line.removeprefix("[Evaluation Attempt] "))
                      for line in (root / "results" / "DOCN" / DAY / "message_tool.log").read_text().splitlines()
                      if line.startswith("[Evaluation Attempt] ")]
        attempt_events = [row["event"] for row in event_rows]
        events_by_short_id = {}
        for row in event_rows:
            events_by_short_id.setdefault(row["attempt_id"][:8], []).append(row["event"])
        receipt = {"disposable_root": str(root), "results_configuration": "relative results; Enter returns displayed default",
                   "controlled_comparison": comparison_receipt,
                   "recorded_source_sha256": original_hash,
                   "copied_source_unchanged": hashlib.sha256(source_copy.read_bytes()).hexdigest() == original_hash,
                   "split_actions": "simulated zero actions; no live absence claim",
                   "attempt_count": len(attempts), "model_calls": len(calls),
                   "roles_exercised": sorted({name for name, _ in calls}),
                   "attempt_events": attempt_events,
                   "attempts": [{"events": events_by_short_id[item.name.rsplit("-", 1)[-1]],
                                 "files": sorted(str(p.relative_to(item)) for p in item.rglob("*") if p.is_file()),
                                 "run_log_bytes": (item / "run.log").stat().st_size,
                                 "message_log_bytes": (item / "message_tool.log").stat().st_size}
                                for item in attempts],
                   "completed_reports": sum((folder / "complete_report.md").is_file() for folder in reports),
                   "save_retry_report": any((folder.parent / "reports-retry" / "complete_report.md").is_file()
                                            for folder in reports),
                   "market_tool_data_seen": any(
                       "[Data] # Stock data for DOCN" in (item / "message_tool.log").read_text()
                       and f"{DAY}," in (item / "message_tool.log").read_text()
                       and f",{source_close}," in (item / "message_tool.log").read_text()
                       for item in attempts),
                   "latest_state": latest.is_file(), "state_archives": len(archives),
                   "distinct_published_runs": len({row.get("run_id") for row in archive_states}),
                   "reopened_report_hashes": [hashlib.sha256(text.encode()).hexdigest()[:12]
                                              for text in reopened_reports],
                   "html_pages": [str(path) for path in sorted(root.glob(
                       "results/DOCN/*/*/reports*/complete_report.html"))],
                   "latest_rating": latest_state.get("final_rating"),
                   "source_hash_matches_state": bool(latest_state.get("run_settings", {}).get("source_hash"))
                       and all(latest_state["run_settings"]["source_hash"] in text
                               for text in reopened_reports),
                   "source_hash_in_report": all("Source hash:" in (folder / "complete_report.md").read_text()
                                                for folder in reports if (folder / "complete_report.md").is_file()),
                   "save_failure_logged": any("Report save failed" in (item / "run.log").read_text()
                                              for item in attempts),
                   "resumed_message": any("Resuming the saved run" in (item / "message_tool.log").read_text()
                                          for item in attempts),
                   "summary": [line for line in stream.getvalue().splitlines()
                               if "Tokens:" in line or "Run log:" in line or "Analysis Complete" in line],
                   "network_blocked": True, "credentials_isolated": True,
                   "secret_found": SECRET in stream.getvalue() or any(
                       SECRET in p.read_text(errors="ignore") for p in root.rglob("*") if p.is_file()),
                   }
        assert receipt["attempt_count"] == 4 and receipt["completed_reports"] == 2
        assert receipt["copied_source_unchanged"]
        assert attempt_events == ["started", "completed", "started", "completed",
                                  "started", "interrupted", "started", "completed"]
        assert receipt["save_retry_report"] and receipt["market_tool_data_seen"]
        assert receipt["latest_state"] and receipt["state_archives"] == 3
        assert receipt["distinct_published_runs"] == 3
        assert len(receipt["reopened_report_hashes"]) == 3
        assert receipt["latest_rating"] in {"Hold", "REVIEW"} and receipt["source_hash_matches_state"], (
            receipt["latest_rating"], receipt["source_hash_matches_state"])
        assert receipt["source_hash_in_report"] and receipt["save_failure_logged"]
        assert receipt["resumed_message"] and not receipt["secret_found"]
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
