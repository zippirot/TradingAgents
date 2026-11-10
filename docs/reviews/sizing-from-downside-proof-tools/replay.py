"""Offline replay of saved DOCN run d58117ef through Build 3 (required return, value today, sizing rule).

No network or model call. The saved run predates this build and holds no retrieved yield, so the replay
supplies the 10-year Treasury yield that run's own macro section reports: 4.86% on 2026-11-06.

Run from the repository root:  PYTHONPATH=. python docs/reviews/sizing-from-downside-proof-tools/replay.py
"""
import json
from decimal import Decimal
from pathlib import Path

from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.required_return import required_return_record
from tradingagents.operational_audit import assess_audit

LOG = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-10_d58117ef.json"


def show(label, state):
    card = prepare_decision_context(state)
    basis = card["scenario_decision"]
    print(f"== {label}")
    print("  required return:", basis.get("required_return"))
    for case in basis["cases"]:
        today = case.get("value_today")
        print(f"    {case['role']:9} period end {Decimal(case['price']):8.2f}  today "
              f"{'-' if today is None else round(Decimal(today), 2)}  weight {case.get('weight')}")
    print("  sizing rule:", {k: (v if k in ('status', 'case_id', 'role') else str(round(Decimal(v), 4)))
                             for k, v in (basis.get("sizing_rule") or {}).items()
                             if k in ("status", "case_id", "role", "value_today", "fall", "weight_per_point_of_loss")})
    print(f"  unchanged period-end basis: weighted {Decimal(basis['weighted_value']):.2f}, direction "
          f"{basis['direction']}, consistency {basis['consistency']}")
    print("  operational score:", assess_audit({**state, "decision_context": card})["score"])
    page = render_decision_context(card, include_mechanical=False).replace("\\", "")
    start = page.index("**Conditional scenario range")
    print("  " + page[start:page.index("**Horizon**")].strip().replace("\n", "\n  "))


if __name__ == "__main__":
    saved = json.loads(LOG.read_text())
    show("d58117ef as saved (no required return recorded)", saved)
    record = required_return_record({"date": "2026-11-06", "value": "4.86"}, Decimal("0.05"), saved["trade_date"])
    show("d58117ef with the run's own 10-year yield (4.86% on 2026-11-06) plus 5 points", {**saved, "required_return": record})
    show("d58117ef when the yield could not be retrieved",
         {**saved, "required_return": {"status": "unavailable", "reason": "The 10-year Treasury yield could not be retrieved (OSError)"}})
