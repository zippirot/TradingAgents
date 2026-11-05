"""Crypto's continuous sessions retain the established benchmark-asof policy."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pandas as pd
import pytest

from tradingagents.memory import TradingMemoryLog, publication, publication_outcomes, settlement


@pytest.mark.parametrize(
    "asof,entry,exit_date,benchmark_entry,benchmark_exit",
    [
        ("2026-01-03", "2026-01-04", "2026-01-09", "2026-01-02", "2026-01-09"),
        ("2026-01-05", "2026-01-06", "2026-01-11", "2026-01-06", "2026-01-09"),
    ],
)
def test_crypto_weekend_windows_settle_and_feed_one_labeled_lesson(
    tmp_path,
    monkeypatch,
    asof,
    entry,
    exit_date,
    benchmark_entry,
    benchmark_exit,
):
    config = {
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
    }
    monkeypatch.setattr(
        publication, "_utcnow", lambda: datetime.fromisoformat(asof + "T22:00:00+00:00")
    )
    monkeypatch.setattr(publication, "get_current_date", lambda: asof)
    monkeypatch.setattr(publication_outcomes, "get_current_date", lambda: "2026-01-20")
    stock = pd.Series(range(100, 118), index=pd.date_range("2026-01-03", periods=18, tz="UTC"))
    index = pd.bdate_range("2026-01-02", "2026-01-20", tz="America/New_York")
    benchmark = pd.Series([400.0 + i for i in range(len(index))], index=index)

    def get_closes(ticker, start, end):
        value = stock if ticker == "BTC-USD" else benchmark
        return value[(value.index >= start) & (value.index < end)]

    monkeypatch.setattr(settlement, "get_closes", get_closes)
    state = {
        "run_id": str(uuid4()),
        "asset_type": "crypto",
        "final_rating": "Buy",
        "final_trade_decision": "Rating: Buy",
        "evidence_quality": {"status": "limited"},
    }
    record = publication.publish(config, state, "BTC-USD", asof)
    assert all(e["benchmark_alignment"] == "asof" for e in record["endpoints"].values())
    memory = TradingMemoryLog(config)
    memory.store_decision("BTC-USD", asof, "Rating: Buy", decision_id=record["decision_id"])
    reflector = Mock()
    reflector.reflect_on_final_decision.return_value = (
        "Five-session observation only; longer thesis remains pending."
    )
    result = settlement.settle_pending("BTC-USD", memory, reflector, config)
    assert result.failed == [] and result.settled == [("BTC-USD", asof)]
    saved = publication_outcomes.load_outcomes(config, record)["endpoints"]
    measured = saved["5_sessions"]["outcome"]
    assert (measured["entry"]["date"], measured["exit"]["date"]) == (entry, exit_date)
    assert (measured["benchmark_entry"]["date"], measured["benchmark_exit"]["date"]) == (
        benchmark_entry,
        benchmark_exit,
    )
    assert measured["benchmark_alignment"] == "asof"
    assert (
        saved["21_sessions"]["status"] == "pending"
        and saved["3_calendar_months"]["status"] == "pending"
    )
    expected = settlement.fetch_outcome(
        "BTC-USD", asof, 5, published_at=record["published_at"], prices_before="2026-01-20"
    )
    assert measured["alpha_return"] == expected["alpha_return"]
    reflector.reflect_on_final_decision.assert_called_once()
    assert reflector.reflect_on_final_decision.call_args.kwargs["holding_days"] == 5
    assert (
        reflector.reflect_on_final_decision.call_args.kwargs["alpha_return"]
        == expected["alpha_return"]
    )
    assert "Five-session observation only" in memory.get_past_context("BTC-USD")
    text = publication_outcomes.render_outcome_summary(config)
    assert "asof" in text and "benchmark dates" in text
    settlement.settle_pending("BTC-USD", memory, reflector, config)
    reflector.reflect_on_final_decision.assert_called_once()
    assert publication.load_record(config, record["decision_id"]) == record


def test_new_stock_is_exact_and_existing_crypto_record_is_not_rewritten(tmp_path, monkeypatch):
    import json

    config = {"results_dir": str(tmp_path)}
    monkeypatch.setattr(publication, "_utcnow", lambda: datetime(2026, 1, 3, 22, tzinfo=UTC))
    state = {
        "run_id": str(uuid4()),
        "asset_type": "stock",
        "final_rating": "Hold",
        "final_trade_decision": "Rating: Hold",
        "evidence_quality": {"status": "limited"},
    }
    stock = publication.publish(config, state, "DOCN", "2026-01-03")
    assert all(e["benchmark_alignment"] == "exact_sessions" for e in stock["endpoints"].values())
    state = {**state, "run_id": str(uuid4()), "asset_type": "crypto"}
    crypto = publication.publish(config, state, "BTC-USD", "2026-01-03")
    # Model an already stored exact-policy record from before this correction.
    for endpoint in crypto["endpoints"].values():
        endpoint["benchmark_alignment"] = "exact_sessions"
        endpoint.pop("benchmark_alignment_note", None)
    crypto["record_sha256"] = publication._digest(
        {k: v for k, v in crypto.items() if k != "record_sha256"}
    )
    path = publication.record_root(config) / "records" / f"{crypto['decision_id']}.json"
    path.write_text(json.dumps(crypto))
    original = path.read_bytes()
    assert publication.publish(config, state, "BTC-USD", "2026-01-03") == crypto
    assert path.read_bytes() == original


def test_existing_symbol_identity_supports_crypto_import_without_asset_metadata(tmp_path):
    entry = {"ticker": "BTCUSD", "date": "2026-01-03", "rating": "Buy", "decision": "Rating: Buy"}
    record = publication.import_legacy_entry(
        {"results_dir": str(tmp_path)}, entry, source_label="memory.md", source_sha256="a" * 64
    )
    assert record["ticker"] == "BTC-USD"
    assert all(e["benchmark_alignment"] == "asof" for e in record["endpoints"].values())
