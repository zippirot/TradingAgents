"""Offline replay of saved DOCN runs through Build 1 (one time basis, return parts, weight sturdiness).

No network or model call. Run d58117ef predates the required return, so the replay supplies the 10-year
Treasury yield that run's own macro section reports: 4.86% on 2026-11-06.

Run from the repository root:  PYTHONPATH=. python docs/reviews/time-basis-return-proof-tools/replay.py
"""
import json
from decimal import Decimal
from pathlib import Path

from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.managers.portfolio_manager import (
    priced_cases,
    render_cases_for_manager,
    with_value_today,
)
from tradingagents.agents.required_return import required_return_record
from tradingagents.agents.shared_valuation import annotate_disputed_cases, replay_cases
from tradingagents.operational_audit import assess_audit

LOGS = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs"
EARLIER = ["520623df", "2a2e47dd", "eea86100", "86aa515f", "c463bdac"]


def card(state):
    record = prepare_decision_context(state)
    return record, render_decision_context(record, include_mechanical=False).replace("\\", "")


def section(page):
    start = page.index("**Conditional scenario range")
    return page[start:page.index("**Horizon**")].strip()


if __name__ == "__main__":
    saved = json.loads((LOGS / "full_states_log_2026-11-10_d58117ef.json").read_text())
    required = required_return_record({"date": "2026-11-06", "value": "4.86"}, Decimal("0.05"), saved["trade_date"])
    for label, state in (("d58117ef as saved (no required return): period-end basis", saved),
                         ("d58117ef with 4.86% + 5 points: value-today basis", {**saved, "required_return": required})):
        record, page = card(state)
        basis = record["scenario_decision"]
        print(f"== {label}")
        print(f"  direction {basis['direction']} on {basis['direction_basis']}; consistency {basis['consistency']}; "
              f"operational score {assess_audit({**state, 'decision_context': record})['score']}")
        print("  " + section(page).replace("\n", "\n  "))
    state = {**saved, "required_return": required}
    replayed = annotate_disputed_cases(state, replay_cases(state))
    print("== what the Portfolio Manager would be shown (first lines)")
    for line in render_cases_for_manager(with_value_today(priced_cases(replayed), state), required).split("\n")[:4]:
        print("  " + line[:330])
    print("== earlier runs: card section and score must be unchanged by this build (no required return saved)")
    for run in EARLIER:
        old = json.loads((LOGS / f"full_states_log_2026-11-09_{run}.json").read_text())
        record, page = card(old)
        basis = record.get("scenario_decision") or {}
        print(f"  {run}: scenario {basis.get('status')}, basis {basis.get('direction_basis')}, "
              f"score {assess_audit({**old, 'decision_context': record})['score']}, "
              f"'On one time basis' printed: {'On one time basis' in page}")
