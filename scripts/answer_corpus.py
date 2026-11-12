"""Collect what models actually answered in saved runs, and run each answer through today's code.

    collect --logs DIR --out DIR             one file per kind, every saved answer with its run, models and date
    check   --kind KIND [--logs DIR]          accepted and rejected counts with reasons, no model call

Kinds: valuation_cases, trader_proposals, thesis_conditions, disclosure_submissions. A handoff fix is
tested here against every real answer of its kind before any paid run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.replay_runs import DEFAULT_LOGS, offline, saved_states


def _raw(state, field):
    held = state.get("unvalidated_outputs")
    return (held.get(field) if isinstance(held, dict) else None) or state.get(field)


def _valuation_cases(state):
    return (state.get("shared_valuation_scenarios") or {}).get("requests") or None


def _disclosure(state):
    held = state.get("disclosure_evidence")
    return held.get("model_extraction") if isinstance(held, dict) else None


ANSWERS = {
    "valuation_cases": _valuation_cases,
    "trader_proposals": lambda state: _raw(state, "trader_investment_plan") or None,
    "thesis_conditions": lambda state: state.get("thesis_candidate"),
    "disclosure_submissions": _disclosure,
}


def _check_valuation(state, answer):
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    record = prepare_shared_valuation(state, answer)
    rows = [{"item": row.get("name"), "accepted": (row.get("result") or {}).get("target") is not None,
             "reasons": [] if (row.get("result") or {}).get("target") is not None
             else [str((row.get("result") or {}).get("reason") or (row.get("result") or {}).get("status"))]}
            for row in record.get("rows") or []]
    # A case code refused outright has no row; its reason is carried on the record.
    rows += [{"item": "(omitted case)", "accepted": False, "reasons": [str(reason)]}
             for reason in record.get("reasons") or [] if "omitted" in str(reason)]
    return rows or [{"item": "(all cases)", "accepted": False, "reasons": [str(r) for r in record.get("reasons") or []]}]


def _check_trader(state, answer):
    from tradingagents.agents.trader.trader import _reading

    read = bool(_reading(answer, _raw(state, "investment_plan") or ""))
    return [{"item": "action", "accepted": read,
             "reasons": [] if read else ["no single Buy, Hold or Sell action that reads under the research rating"]}]


def _check_thesis(state, answer):
    from tradingagents.agents.output_validation import _thesis_update

    fresh = {key: value for key, value in state.items() if key not in {"thesis", "thesis_version_id", "publication_record"}}
    thesis = _thesis_update({**fresh, "thesis_candidate": answer}).get("thesis") or {}
    asked, kept = len(answer.get("conditions") or []), len(thesis.get("conditions") or [])
    rows = [{"item": f"condition kept ({kept} of {asked})", "accepted": True, "reasons": []}] * kept
    if asked > kept:
        rows += [{"item": "condition dropped", "accepted": False,
                  "reasons": [str(note) for note in thesis.get("warnings") or ["dropped without a stated reason"]]}] * (asked - kept)
    return rows or [{"item": "no conditions offered", "accepted": True, "reasons": []}]


def _check_disclosure(state, answer):
    # The model's raw submission is not retained, only what code made of it, so this reports the saved result.
    rows = [{"item": "claim", "accepted": True, "reasons": []} for _ in answer.get("claims") or []]
    rows += [{"item": "claim", "accepted": False, "reasons": [str(row.get("reason") if isinstance(row, dict) else row)]}
             for row in answer.get("rejected") or []]
    return rows or [{"item": "no submission", "accepted": True, "reasons": []}]


CHECKS = {"valuation_cases": _check_valuation, "trader_proposals": _check_trader,
          "thesis_conditions": _check_thesis, "disclosure_submissions": _check_disclosure}


def entries(kind: str, logs: Path, ticker: str | None = None):
    """Yield (entry, state) for each saved answer of this kind, once per run."""
    for _path, state, _error in saved_states(logs, ticker):
        answer = ANSWERS[kind](state) if state else None
        if not answer:
            continue
        settings = state.get("run_settings") if isinstance(state.get("run_settings"), dict) else {}
        yield {"run_id": state.get("run_id"), "ticker": state.get("company_of_interest"),
               "date": str(state.get("trade_date")),
               "models": {"quick": settings.get("quick_think_llm"), "deep": settings.get("deep_think_llm")},
               "answer": answer}, state


def collect(logs: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for kind in ANSWERS:
        rows = [entry for entry, _state in entries(kind, logs)]
        (out / f"{kind}.json").write_text(json.dumps(rows, indent=1, sort_keys=True, default=str))
        counts[kind] = len(rows)
    return counts


def check(kind: str, logs: Path, ticker: str | None = None) -> dict:
    """Run every saved answer of one kind through the code now checked out."""
    result = {"kind": kind, "answers": 0, "accepted": 0, "rejected": 0, "reasons": {}, "runs": []}
    with offline():
        for entry, state in entries(kind, logs, ticker):
            try:
                rows = CHECKS[kind](state, entry["answer"])
            except Exception as exc:  # noqa: BLE001 - code failing on a real answer is the finding
                rows = [{"item": "(code error)", "accepted": False, "reasons": [f"{type(exc).__name__}: {exc}"[:200]]}]
            result["answers"] += 1
            taken = sum(row["accepted"] for row in rows)
            result["accepted"] += taken
            result["rejected"] += len(rows) - taken
            for row in rows:
                for reason in row["reasons"]:
                    result["reasons"][reason[:200]] = result["reasons"].get(reason[:200], 0) + 1
            result["runs"].append({"run_id": entry["run_id"], "ticker": entry["ticker"], "accepted": taken,
                                   "rejected": len(rows) - taken})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_subparsers(dest="mode", required=True)
    gather = modes.add_parser("collect")
    gather.add_argument("--logs", type=Path, default=DEFAULT_LOGS)
    gather.add_argument("--out", type=Path, required=True)
    run = modes.add_parser("check")
    run.add_argument("--kind", choices=sorted(ANSWERS), required=True)
    run.add_argument("--logs", type=Path, default=DEFAULT_LOGS)
    run.add_argument("--ticker")
    run.add_argument("--json", type=Path, help="also write the full result here")
    args = parser.parse_args(argv)
    if args.mode == "collect":
        for kind, count in collect(args.logs, args.out).items():
            print(f"{kind}: {count} saved answer(s)")
        return 0
    result = check(args.kind, args.logs, args.ticker)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1, sort_keys=True))
    print(f"{args.kind}: {result['answers']} answer(s); {result['accepted']} item(s) accepted, {result['rejected']} rejected")
    for reason, count in sorted(result["reasons"].items(), key=lambda pair: -pair[1]):
        print(f"  {count} x {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
