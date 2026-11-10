"""Offline replay of saved DOCN runs through the decision-basis repair. No network or model call.

Run from the repository root:  PYTHONPATH=. python docs/reviews/decision-basis-repair-proof-tools/replay.py
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

from tradingagents.agents.decision_brief import render as render_brief, since_last_decision
from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.operational_audit import assess_audit

LOGS = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs"
RUNS = [("2026-11-10", "d58117ef"), ("2026-11-09", "520623df"), ("2026-11-09", "2a2e47dd"),
        ("2026-11-09", "eea86100"), ("2026-11-09", "86aa515f"), ("2026-11-09", "c463bdac")]


def replay(day, run):
    state = json.loads((LOGS / f"full_states_log_{day}_{run}.json").read_text())
    saved = state.get("decision_context") or {}
    card = prepare_decision_context(state)
    basis = card.get("scenario_decision") or {}
    print(f"== {run} ({day})")
    print("  scenario decision: saved", (saved.get("scenario_decision") or {}).get("status"), "-> now", basis.get("status"))
    for case in basis.get("cases", []):
        print(f"    {case['role']:9} {Decimal(case['price']):8.2f}  {case.get('disposition')}  weight {case.get('weight')}"
              f"  flagged_by {case.get('flagged_by')}")
    if basis.get("range"):
        print(f"    range {Decimal(basis['range']['low']):.2f} to {Decimal(basis['range']['high']):.2f}; weighted "
              f"{Decimal(basis['weighted_value']):.2f}; close {basis.get('close')}; direction {basis.get('direction')}; "
              f"consistency {basis.get('consistency')}")
    print("    problems:", basis.get("problems"))
    for group in card.get("case_groups", []):
        print(f"  displayed range: {group['low'] and round(Decimal(group['low']), 2)} to "
              f"{group['high'] and round(Decimal(group['high']), 2)}; close {group.get('close_position')}")
    print("  scenarios:", card.get("scenarios"))
    before = assess_audit(state)
    after = assess_audit({**state, "decision_context": card})
    print(f"  operational score: saved card {before['score']} -> new card {after['score']}; "
          f"findings now {[f['code'] for f in after['findings']]}")
    return state, card


if __name__ == "__main__":
    for day, run in RUNS:
        state, card = replay(day, run)
        if run == "d58117ef":
            page = render_decision_context(card, include_mechanical=False)
            start = page.index("**Basis**")
            print("  --- card from Basis onward ---")
            print("  " + page[start:start + 2600].replace("\n", "\n  "))
            if "--brief" in sys.argv:
                from tradingagents.default_config import DEFAULT_CONFIG
                brief = since_last_decision(DEFAULT_CONFIG, "DOCN", state)
                print("  --- condition change note recomputed ---")
                print("  ", brief.get("conditions"))
                print("  ", [line for line in render_brief(brief) if "conditions" in line])
