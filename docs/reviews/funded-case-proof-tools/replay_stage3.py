"""Reprice the saved cases of two real runs and print each case's funded statement. No model call.

b7396f4f (Terra, 2026-11-11) leaves every balance as filed; fe8979c2 (Opus + Terra, 2026-11-10) states cash
changes. The statement must change no value in either.
"""
import json
import os
import sys
from decimal import Decimal

from tradingagents.agents.shared_valuation import prepare_shared_valuation
from tradingagents.agents.valuation_cases import STATEMENT

LOGS = os.path.expanduser("~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/")
RUNS = ("full_states_log_2026-11-11_b7396f4f.json", "full_states_log_2026-11-10_fe8979c2.json")


def main():
    moved = 0
    for name in RUNS:
        with open(LOGS + name) as handle:
            state = json.load(handle)
        saved = state["shared_valuation_scenarios"]["rows"]
        record = prepare_shared_valuation(state, [{"name": row["name"], "request": row["request"]} for row in saved])
        print(f"\n===== {name[-13:-5]}: status {record['status']} {record.get('reasons') or ''}")
        for row, before in zip(record["rows"], saved, strict=True):
            now, then = Decimal(row["result"]["target"]), Decimal(before["result"]["target"])
            moved += now != then
            print(f"\n{row['name'][:60]}: {then:.2f} -> {now:.2f}")
            for line in row["result"]["assumptions"]:
                if line.startswith(STATEMENT):
                    print("   " + line[len(STATEMENT):])
    print(f"\ncases whose value moved: {moved}")
    return moved


if __name__ == "__main__":
    sys.exit(main())
