"""Replay the code-only steps of saved runs, with no model call and no network.

    replay  --logs DIR --out DIR [--ticker T]   one JSON summary per saved run, plus index.json
    compare BEFORE_DIR AFTER_DIR                what changed between two replays

A summary holds only what code computes from the saved state: the source checks, the valuation cases
priced from the saved requests, the price-implied multiples and a digest of the sizing block. Portfolio
figures never leave the state: the sizing block is reduced to a SHA-256 and the file fingerprint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

DEFAULT_LOGS = Path.home() / ".tradingagents" / "logs"


@contextmanager
def offline():
    """Refuse every outbound connection for the duration: a replay that needs the network is a defect."""
    real = socket.socket.connect

    def refuse(*_args, **_kwargs):
        raise OSError("network is disabled during replay")

    socket.socket.connect = refuse
    try:
        yield
    finally:
        socket.socket.connect = real


def saved_states(logs: Path, ticker: str | None = None):
    """Yield (path, state or None, error) once per run id; a re-export of the same run is collapsed."""
    seen = set()
    folders = [logs / ticker.upper()] if ticker else sorted(p for p in Path(logs).iterdir() if p.is_dir())
    for folder in folders:
        # The suffixed file is the per-run copy; the unsuffixed one is "latest that day" and sorts after it.
        for path in sorted((folder / "TradingAgentsStrategy_logs").glob("full_states_log_*.json"),
                           key=lambda p: (len(p.stem.split("_")) < 5, p.name)):
            try:
                state = json.loads(path.read_text())
                if not isinstance(state, dict) or not state.get("company_of_interest"):
                    raise ValueError("not a saved run state")
            except (OSError, ValueError) as exc:
                yield path, None, f"{type(exc).__name__}: {exc}"[:200]
                continue
            key = state.get("run_id") or path.name
            if key in seen:
                continue
            seen.add(key)
            yield path, state, None


def _money(value, places="0.0001"):
    try:
        return str(Decimal(str(value)).quantize(Decimal(places)))
    except (InvalidOperation, TypeError, ValueError):
        return None if value is None else str(value)


def _step(function):
    try:
        return function()
    except Exception as exc:  # noqa: BLE001 - one step failing is itself a result to compare
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}


def _source_checks(state):
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    package = EvidencePackage.model_validate(state.get("financial_evidence"))
    documents = DisclosurePackage.model_validate(state["filing_evidence"]) if state.get("filing_evidence") else None
    result = assess_financial_package(state, package, documents, source_only=True)
    return {"status": "replayed",
            "checks": [{"check": str(row.get("check") or row.get("name") or row.get("id") or index),
                        "status": row.get("status")}
                       for index, row in enumerate(result.get("source_checks") or [])]}


def _cases(state):
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    requests = (state.get("shared_valuation_scenarios") or {}).get("requests")
    if not requests:
        return {"status": "no_saved_requests", "rows": []}
    record = prepare_shared_valuation(state, requests)
    return {"status": record["status"], "reasons": list(record.get("reasons") or []),
            "rows": [{"name": row.get("name"), "status": (row.get("result") or {}).get("status"),
                      "target": _money((row.get("result") or {}).get("target")),
                      "unit": (row.get("result") or {}).get("unit")} for row in record.get("rows") or []]}


def _price_implied(state):
    from tradingagents.agents.valuation_comparison import price_implied_valuation

    record = price_implied_valuation(state)

    def rounded(value):
        return [rounded(item) for item in value] if isinstance(value, list) else _money(value)

    return {"status": record.get("status"), "reason": record.get("reason"),
            "rows": [{key: rounded(value) for key, value in (row.get("ratios") or {}).items()}
                     for row in record.get("rows") or []]}


def _sizing(state):
    from tradingagents.portfolio import render_sizing, sizing_from_state

    result = sizing_from_state(state, final=True)
    if result.get("status") == "not_configured":
        return {"status": "not_configured"}
    text = "\n".join(render_sizing(result, final=True))
    inputs = state.get("portfolio_inputs") if isinstance(state.get("portfolio_inputs"), dict) else {}
    return {"status": result.get("status"), "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "portfolio_fingerprint": inputs.get("fingerprint")}


def summarize(state: dict) -> dict:
    """The code-only results for one saved state on the code now checked out."""
    settings = state.get("run_settings") if isinstance(state.get("run_settings"), dict) else {}
    with offline():
        return {
            "run_id": state.get("run_id"), "ticker": state.get("company_of_interest"),
            "trade_date": str(state.get("trade_date")), "rating": state.get("final_rating"),
            "models": {"quick": settings.get("quick_think_llm"), "deep": settings.get("deep_think_llm")},
            "source_checks": _step(lambda: _source_checks(state)),
            "cases": _step(lambda: _cases(state)),
            "price_implied": _step(lambda: _price_implied(state)),
            "sizing": _step(lambda: _sizing(state)),
        }


def replay(logs: Path, out: Path, ticker: str | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    index = {"replayed": [], "skipped": []}
    for path, state, error in saved_states(logs, ticker):
        if state is None:
            index["skipped"].append({"file": path.name, "reason": error})
            continue
        summary = summarize(state)
        name = f"{summary['ticker']}_{str(summary['run_id'] or path.stem)[:8]}.json"
        (out / name).write_text(json.dumps(summary, indent=1, sort_keys=True))
        index["replayed"].append(name)
    (out / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True))
    return index


def _flatten(value, prefix=""):
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _flatten(value[key], f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for position, item in enumerate(value):
            label = item.get("name") or item.get("check") if isinstance(item, dict) else None
            yield from _flatten(item, f"{prefix}[{label if label is not None else position}]")
    else:
        yield prefix, value


def compare(before: Path, after: Path) -> list[dict]:
    """Every field that differs between two replay folders, and runs present on one side only."""
    changes = []
    names = {p.name for p in before.glob("*.json")} | {p.name for p in after.glob("*.json")}
    for name in sorted(names - {"index.json"}):
        left, right = before / name, after / name
        if not left.exists() or not right.exists():
            changes.append({"run": name, "field": "(run)", "before": left.exists(), "after": right.exists()})
            continue
        old, new = dict(_flatten(json.loads(left.read_text()))), dict(_flatten(json.loads(right.read_text())))
        for field in sorted(set(old) | set(new)):
            if old.get(field) != new.get(field):
                changes.append({"run": name, "field": field, "before": old.get(field), "after": new.get(field)})
    return changes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_subparsers(dest="mode", required=True)
    run = modes.add_parser("replay")
    run.add_argument("--logs", type=Path, default=DEFAULT_LOGS)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--ticker")
    diff = modes.add_parser("compare")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "replay":
        index = replay(args.logs, args.out, args.ticker)
        print(f"replayed {len(index['replayed'])} run(s), skipped {len(index['skipped'])}; summaries in {args.out}")
        for row in index["skipped"]:
            print(f"  skipped {row['file']}: {row['reason']}")
        return 0
    changes = compare(args.before, args.after)
    for row in changes:
        print(f"{row['run']}  {row['field']}: {row['before']} -> {row['after']}")
    print(f"{len(changes)} difference(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
