"""Reprice the saved cases of run 6fe6324b with convertible notes decided by code. No model call."""
import json
import os
from decimal import Decimal

from tradingagents.agents.shared_valuation import _funding_terms, prepare_shared_valuation

PATH = os.path.expanduser("~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-10_6fe6324b.json")


def main():
    with open(PATH) as handle:
        state = json.load(handle)
    for note in _funding_terms(state)["convertibles"]:
        print("read from the filing:", json.dumps({k: v for k, v in note.items() if k != "source_id"}))
    saved = state["shared_valuation_scenarios"]["rows"]
    record = prepare_shared_valuation(state, [{"name": row["name"], "request": row["request"]} for row in saved])
    print(f"\nstatus: {record['status']} {record.get('reasons') or ''}")
    for row, before in zip(record["rows"], saved, strict=True):
        now, then = Decimal(row["result"]["target"]), Decimal(before["result"]["target"])
        print(f"\n{row['name'][:44]:44} {then:8.2f} -> {now:8.2f}  ({now - then:+.2f})")
        print(f"   shares {Decimal(before['result']['shares_outstanding']):,.0f} -> {Decimal(row['result']['shares_outstanding']):,.0f}; "
              f"net obligations {Decimal(before['result']['net_obligations']):,.0f} -> {Decimal(row['result']['net_obligations']):,.0f}")
        print("   sensitivities:", {k[:18]: f"{Decimal(v):.2f}" for k, v in row["sensitivities"].items()})
        for line in row["result"]["assumptions"]:
            if line.startswith(("convertible notes: 20", "share sales")):
                print("   " + line)


if __name__ == "__main__":
    main()
