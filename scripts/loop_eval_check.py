"""Check an evaluator's record before its scores enter the ledger.

    loop_eval_check.py PATH/evaluation.json [...]

A record passes when it parses, carries the skill version, has D1 to D7 with the fixed weights summing
to 100%, and its weighted Decision score recomputes from the components. Prints one ledger-ready line.
"""
from __future__ import annotations

import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

WEIGHTS = {"D1": "0.25", "D2": "0.20", "D3": "0.15", "D4": "0.15", "D5": "0.10", "D6": "0.10", "D7": "0.05"}


def problems(record: dict) -> list[str]:
    found = []
    if not str((record.get("identity") or {}).get("rubric_version") or "").startswith("TAE-"):
        found.append("identity.rubric_version is missing")
    scores, parts = record.get("scores") or {}, record.get("decision_components") or {}
    total, weight = Decimal(0), Decimal(0)
    for name, expected in WEIGHTS.items():
        part = parts.get(name) or {}
        try:
            score, given = Decimal(str(part["score"])), Decimal(str(part["weight"]))
        except (KeyError, ArithmeticError, TypeError):
            found.append(f"decision_components.{name} lacks a numeric score and weight")
            continue
        if not 0 <= score <= 10:
            found.append(f"{name} score {score} is outside 0 to 10")
        if given != Decimal(expected):
            found.append(f"{name} weight is {given}, not {expected}")
        total, weight = total + score * given, weight + given
    if not found:
        if weight != 1:
            found.append(f"weights sum to {weight}, not 1")
        stated = scores.get("decision_weighted")
        computed = total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if stated is None or abs(Decimal(str(stated)) - computed) > Decimal("0.05"):
            found.append(f"decision_weighted is {stated}; the components give {computed}")
    for name in ("research_quality", "investment_decision_quality"):
        value = scores.get(name)
        if not isinstance(value, (int, float)) or not 0 <= value <= 10:
            found.append(f"scores.{name} is not a number from 0 to 10")
    return found


def line(record: dict) -> str:
    scores = record.get("scores") or {}
    parts = record.get("decision_components") or {}
    caps = [row.get("rule") for row in record.get("critical_failures") or [] if isinstance(row, dict) and row.get("triggered")]
    detail = " ".join(f"{name}={(parts.get(name) or {}).get('score')}" for name in WEIGHTS)
    return (f"Decision {scores.get('investment_decision_quality')} (weighted {scores.get('decision_weighted')}) | "
            f"Research {scores.get('research_quality')} | Operational {scores.get('operational_quality_independent')} | "
            f"{detail} | caps: {', '.join(map(str, caps)) or 'none'} | {(record.get('identity') or {}).get('rubric_version')}")


def main(argv=None):
    failed = 0
    for name in argv if argv is not None else sys.argv[1:]:
        try:
            record = json.loads(Path(name).read_text())
            found = problems(record)
        except (OSError, ValueError) as exc:
            record, found = {}, [f"unreadable: {exc}"]
        print(name)
        print("  " + (line(record) if not found else "REJECTED: " + "; ".join(found)))
        failed += bool(found)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
