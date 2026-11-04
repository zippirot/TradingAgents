"""REVIEW is saved research, never a trading decision or a paid reflection."""

import json
from unittest.mock import Mock

from tradingagents.backtest import run_backtest, summarize
from tradingagents.memory import TradingMemoryLog, settlement


def legacy_log(tmp_path):
    path = tmp_path / "memory.md"
    path.write_text(
        "[2026-01-05 | DOCN | REVIEW | pending]\n\nDECISION:\nMissing core source"
        + TradingMemoryLog._SEPARATOR
        + "[2026-01-06 | DOCN | REVIEW | +10.0% | +5.0% | 5d | resolved:2026-02-01]\n\nDECISION:\nOld review\n\nREFLECTION:\nInvalid lesson"
        + TradingMemoryLog._SEPARATOR
    )
    return TradingMemoryLog({"memory_log_path": str(path)}), path


def test_new_review_does_not_create_trading_memory(tmp_path):
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
    log.store_decision("DOCN", "2026-01-05", "Rating: Buy", rating="REVIEW")
    log.store_decision("DOCN", "2026-01-06", "No readable rating")
    assert log.load_entries() == []


def test_legacy_review_remains_readable_but_never_pending_or_context(tmp_path):
    log, path = legacy_log(tmp_path)
    before = path.read_bytes()
    assert len(log.load_entries()) == 2
    assert log.get_pending_entries() == []
    assert log.get_past_context("DOCN", as_of="2026-03-01") == ""
    assert path.read_bytes() == before


def test_corrected_same_date_can_append_without_rewriting_legacy_review(tmp_path):
    log, path = legacy_log(tmp_path)
    before = path.read_bytes()
    log.store_decision("DOCN", "2026-01-05", "Rating: Buy")
    log.store_decision("DOCN", "2026-01-05", "Rating: Sell")
    entries = log.load_entries()
    assert len(entries) == 3 and entries[-1]["rating"] == "Buy"
    assert path.read_bytes().startswith(before)


def test_legacy_review_cannot_be_settled_directly_or_in_batch(tmp_path):
    log, path = legacy_log(tmp_path)
    before = path.read_bytes()
    assert not log.update_with_outcome("DOCN", "2026-01-05", 0.1, 0.05, 5, "bad")
    log.batch_update_with_outcomes(
        [
            {
                "ticker": "DOCN",
                "trade_date": "2026-01-05",
                "raw_return": 0.1,
                "alpha_return": 0.05,
                "holding_days": 5,
                "reflection": "bad",
            }
        ]
    )
    assert path.read_bytes() == before


def test_settlement_filters_review_even_from_custom_memory_provider(monkeypatch):
    import contextlib

    memory = Mock()
    memory.settling.return_value = contextlib.nullcontext(True)
    memory.get_pending_entries.return_value = [
        {"ticker": "DOCN", "date": "2026-01-05", "rating": "REVIEW", "decision": "Rating: Buy"}
    ]
    prices = Mock(side_effect=AssertionError("review must not fetch prices"))
    monkeypatch.setattr(settlement, "fetch_returns", prices)
    reflector = Mock()
    result = settlement.settle_pending("DOCN", memory, reflector, {})
    assert not result.settled and not result.failed
    prices.assert_not_called()
    reflector.reflect_on_final_decision.assert_not_called()


def test_legacy_review_is_unscored_not_pending(tmp_path):
    _, path = legacy_log(tmp_path)
    result = summarize(path)
    assert result.resolved == 0 and result.pending == 0 and result.unscored == 2
    assert result.by_rating == {}


class FakeGraph:
    instances = []
    review = True

    def __init__(self, selected_analysts, config):
        self.config = config
        self.memory_log = TradingMemoryLog(config)
        self.calls = []
        self.instances.append(self)

    def propagate(self, ticker, date, asset_type, portfolio=None):
        from pathlib import Path

        self.calls.append((ticker, date))
        state = {
            "company_of_interest": ticker,
            "trade_date": date,
            "final_rating": "REVIEW" if self.review else "Buy",
            "final_trade_decision": "Missing SEC filing" if self.review else "Rating: Buy",
            "evidence_quality": {
                "status": "insufficient" if self.review else "sufficient",
                "reasons": ["Missing SEC filing"] if self.review else [],
            },
        }
        path = (
            Path(self.config["results_dir"])
            / ticker
            / "TradingAgentsStrategy_logs"
            / f"full_states_log_{date}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))
        self.memory_log.store_decision(
            ticker, date, state["final_trade_decision"], state["final_rating"]
        )
        return state, state["final_rating"]

    def settle_pending(self, ticker):
        pass


def test_review_cell_runs_once_per_explicit_launch_and_reports_incomplete(tmp_path, monkeypatch):
    import tradingagents.backtest as bt

    FakeGraph.instances = []
    FakeGraph.review = True
    monkeypatch.setattr(bt, "TradingAgentsGraph", FakeGraph)
    config = {"results_dir": str(tmp_path / "results")}
    first = run_backtest(["DOCN"], ["2026-01-05"], config, run_id="proof")
    assert first.cells_run == 1 and len(FakeGraph.instances[-1].calls) == 1
    assert first.incomplete == [("DOCN", "2026-01-05", "Missing SEC filing")]
    summary = summarize(first)
    assert summary.incomplete == 1 and summary.resolved == 0 and summary.pending == 0
    assert "REVIEW" in summary.render() and "explicit" in summary.render().lower()
    FakeGraph.review = False
    second = run_backtest(["DOCN"], ["2026-01-05"], config, run_id="proof")
    assert second.cells_run == 1 and second.skipped == 0
    assert second.prior_quality == [("DOCN", "2026-01-05", "Missing SEC filing")]
    assert summarize(second).incomplete == 0
    third = run_backtest(["DOCN"], ["2026-01-05"], config, run_id="proof")
    assert third.skipped == 1 and third.cells_run == 0


def test_corrected_entry_settles_without_mutating_prior_review_and_rotation_keeps_history(tmp_path):
    log, path = legacy_log(tmp_path)
    legacy = path.read_bytes()
    log._max_entries = 1
    log.store_decision("DOCN", "2026-01-05", "Rating: Buy")
    assert log.update_with_outcome("DOCN", "2026-01-05", 0.1, 0.05, 5, "valid", "2026-02-01")
    assert path.read_bytes().startswith(legacy)
    entries = log.load_entries()
    assert entries[0]["pending"] and entries[-1]["rating"] == "Buy" and not entries[-1]["pending"]
    assert "Invalid lesson" not in log.get_past_context("DOCN")


def test_legacy_review_cell_is_retried_on_explicit_resume(tmp_path, monkeypatch):
    import tradingagents.backtest as bt

    FakeGraph.instances = []
    FakeGraph.review = False
    monkeypatch.setattr(bt, "TradingAgentsGraph", FakeGraph)
    run_dir = tmp_path / "results" / "backtest" / "proof"
    run_dir.mkdir(parents=True)
    path = run_dir / "trading_memory.md"
    legacy = (
        "[2026-01-05 | DOCN | REVIEW | pending]\n\nDECISION:\nOld incomplete research"
        + TradingMemoryLog._SEPARATOR
    )
    path.write_text(legacy)
    result = run_backtest(
        ["DOCN"], ["2026-01-05"], {"results_dir": str(tmp_path / "results")}, run_id="proof"
    )
    assert result.skipped == 0 and result.cells_run == 1
    assert result.prior_quality == [
        ("DOCN", "2026-01-05", "Legacy REVIEW: no trading decision recorded")
    ]
    assert path.read_text().startswith(legacy)
    assert summarize(result).incomplete == 0


def test_malformed_saved_quality_does_not_crash_summary(tmp_path):
    from tradingagents.backtest import BacktestResult

    path = tmp_path / "DOCN" / "TradingAgentsStrategy_logs" / "full_states_log_2026-01-05.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "company_of_interest": "DOCN",
                "trade_date": "2026-01-05",
                "final_rating": "REVIEW",
                "evidence_quality": [1],
            }
        )
    )
    summary = summarize(BacktestResult("proof", tmp_path / "trading_memory.md"))
    assert summary.incomplete == 1 and summary.resolved == 0


def test_prior_review_is_preserved_if_explicit_retry_fails(tmp_path, monkeypatch):
    import tradingagents.backtest as bt

    FakeGraph.instances = []
    FakeGraph.review = True
    monkeypatch.setattr(bt, "TradingAgentsGraph", FakeGraph)
    config = {"results_dir": str(tmp_path / "results")}
    first = run_backtest(["DOCN"], ["2026-01-05"], config, run_id="proof")

    def fail(*a, **kw):
        raise RuntimeError("source timeout")

    monkeypatch.setattr(FakeGraph, "propagate", fail)
    second = run_backtest(["DOCN"], ["2026-01-05"], config, run_id=first.run_id)
    assert second.failures == [("DOCN", "2026-01-05", "source timeout")]
    assert summarize(second).incomplete == 1
