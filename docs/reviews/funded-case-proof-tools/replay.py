"""Reprice the saved cases of run 6fe6324b with the two operating-cash questions answered. No model call."""
import copy
import json
import os
from decimal import Decimal

from tradingagents.agents.shared_valuation import prepare_shared_valuation

PATH = os.path.expanduser("~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-10_6fe6324b.json")


def main():
    state = json.load(open(PATH))
    saved = state["shared_valuation_scenarios"]["rows"]
    for label, answers in (("as saved (neither answered)", {}),
                           ("after interest: yes; includes new rent: no", {"operations_after_lease_interest": True,
                                                                            "operations_include_new_lease_rent": False}),
                           ("after interest: yes; includes new rent: yes", {"operations_after_lease_interest": True,
                                                                             "operations_include_new_lease_rent": True}),
                           ("after interest: no; includes new rent: no", {"operations_after_lease_interest": False,
                                                                           "operations_include_new_lease_rent": False})):
        requests = []
        for row in saved:
            request = copy.deepcopy(row["request"])
            request["capital"].update(answers)
            requests.append({"name": row["name"], "request": request})
        record = prepare_shared_valuation(state, requests)
        print(f"\n== {label}: {record['status']} {record.get('reasons') or ''}")
        for row, before in zip(record["rows"], saved, strict=True):
            now, then = Decimal(row["result"]["target"]), Decimal(before["result"]["target"])
            print(f"{row['name'][:40]:40} {then:8.2f} -> {now:8.2f}  ({now - then:+.2f})  "
                  + json.dumps({k: v for k, v in (row["funding"].get("funded") or {}).items() if k != "lines"}))
            print("   sensitivities:", {k: f"{Decimal(v):.2f}" for k, v in row["sensitivities"].items()})
        if answers.get("operations_after_lease_interest") and not answers.get("operations_include_new_lease_rent"):
            print("   limit:", record["rows"][0]["funding"]["limit"])


if __name__ == "__main__":
    main()
