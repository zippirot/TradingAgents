"""Read-only private DOCN inputs; all application writes target a temporary clone."""

import hashlib
import json
import shutil
import socket
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.memory import publication, publication_outcomes as outcomes, settlement
from tradingagents.memory.log import TradingMemoryLog


def forbidden(*args, **kwargs):
    raise AssertionError("Network and model calls are forbidden in this replay")


socket.socket.connect = forbidden
original = {"results_dir": str(Path.home() / ".tradingagents/logs")}
records = publication.list_records(original, "DOCN")
source = publication.record_root(original)
cache = Path.home() / ".tradingagents/cache/DOCN-YFin-data.csv"
root = Path(tempfile.mkdtemp(prefix="settlement-docn-proof-"))
config = {
    "results_dir": str(root),
    "memory_log_path": str(root / "empty-memory.md"),
    "analysis_timezone": "America/Denver",
}
inputs = [cache]
for record in records:
    paths = [
        Path("records") / (record["decision_id"] + ".json"),
        Path(record["evidence_snapshot"]["path"]),
    ]
    existing = source / "outcomes" / (record["decision_id"] + ".json")
    if existing.exists():
        paths.append(existing.relative_to(source))
    for relative in paths:
        path = source / relative
        target = root / "publications" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        inputs.append(path)
original_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
frame = pd.read_csv(cache)
metadata = [json.loads(raw) for raw in frame["__market_source"].unique()]
clock = datetime(2026, 11, 7, 17, tzinfo=UTC)
assert all(
    m["ticker"] == "DOCN" and datetime.fromisoformat(m["retrieved_at"]) <= clock for m in metadata
)
index = pd.to_datetime(frame["Date"], utc=True).dt.tz_convert("America/New_York")
# Installed yfinance.utils.auto_adjust explicitly renames Adj Close to Close.
# Retain that basis instead of presenting the cached unadjusted Close as total return.
closes = pd.Series(pd.to_numeric(frame["Adj Close"]).to_numpy(), index=pd.DatetimeIndex(index))
assert closes.index.is_unique and (closes > 0).all()
assert closes.index.max().date().isoformat() == "2026-11-06"
calls, evidence_reads = [], []


def fetch(symbol, start, end):
    calls.append((symbol, start, end))
    assert symbol == "DOCN", "No recorded benchmark supplied; this replay must remain immature"
    selected = closes[
        (closes.index.tz_localize(None) >= start) & (closes.index.tz_localize(None) < end)
    ].copy()
    selected.attrs.update(settlement_request_start=start, settlement_request_end=end)
    return selected


class NoReflection:
    reflect_on_final_decision = staticmethod(forbidden)


graph = object.__new__(TradingAgentsGraph)
graph.config = config
graph.memory_log = TradingMemoryLog(config)
graph.reflector = NoReflection()
state = {
    "company_of_interest": "DOCN",
    "trade_date": "2026-11-07",
    "analysis_clock": {"cutoff_utc": clock.isoformat(), "analysis_timezone": "America/Denver"},
}
real_evidence = outcomes.load_evidence
with (
    patch.object(settlement, "get_settlement_closes", fetch),
    patch.object(settlement, "get_closes", fetch),
    patch.object(outcomes, "_now", lambda: clock),
    patch.object(outcomes, "get_current_date", lambda: "2026-11-07"),
    patch.object(
        outcomes, "load_evidence", lambda *a: evidence_reads.append(a) or real_evidence(*a)
    ),
):
    first = graph._memory_step(state)
    first_calls = list(calls)
    calls.clear()
    second = graph._memory_step(state)
expected = sum(len(r["endpoints"]) for r in records if r["eligibility"]["directional"])
assert f"{expected} outcome(s) await maturity." in first["memory_note"], first["memory_note"]
assert "could not be settled" not in first["memory_note"]
assert second["memory_note"] == first["memory_note"]
assert len(first_calls) == len(calls) == 1 and calls[0][0] == "DOCN"
assert evidence_reads == []  # The separate prior-thesis read still verifies its own snapshot.
assert graph.memory_log.load_entries() == []
assert all(
    e["status"] in {"pending", "ineligible"}
    for r in records
    for e in outcomes.load_outcomes(config, r)["endpoints"].values()
)
assert all(
    hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    for path, digest in original_hashes.items()
)
(root / "memory-step.json").write_text(json.dumps(first, indent=2))
receipt = {
    "proof_clock": clock.isoformat(),
    "disposable_root": str(root),
    "source_record_count": len(records),
    "directional_count": sum(r["eligibility"]["directional"] for r in records),
    "expected_immature_endpoints": expected,
    "memory_note": first["memory_note"],
    "first_pass_requests": first_calls,
    "second_pass_requests": calls,
    "settlement_evidence_reads": len(evidence_reads),
    "reflector_calls": 0,
    "source_unchanged": True,
    "cache_sha256": original_hashes[str(cache)],
    "source_basis": "Retained Yahoo Adj Close renamed to Close, matching installed yfinance.auto_adjust",
    "benchmark_limitation": "No benchmark series is needed or supplied for these provably immature DOCN windows",
    "source_ids": sorted({m["source_id"] for m in metadata}),
    "record_ids": [r["decision_id"] for r in records],
}
Path("/tmp/settlement-docn-runtime.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
