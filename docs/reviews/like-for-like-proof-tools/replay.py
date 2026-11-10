"""Offline replay of saved DOCN run d58117ef through Build 2 (same-basis multiple reference, funding bounds).

No network or model call. Run from the repository root:
    PYTHONPATH=. python docs/reviews/like-for-like-proof-tools/replay.py
"""
import json
from decimal import Decimal
from pathlib import Path

from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.required_return import required_return_record
from tradingagents.agents.shared_valuation import replay_cases
from tradingagents.operational_audit import assess_audit

LOGS = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs"

if __name__ == "__main__":
    saved = json.loads((LOGS / "full_states_log_2026-11-10_d58117ef.json").read_text())
    print("== saved report (before): reference position per case")
    for row in saved["shared_valuation_scenarios"]["rows"]:
        position = row["reference_position"]
        print(f"  {row['scenario_role']:9} {position['basis']}: band {position['band']}")
    replayed = replay_cases(saved)
    print("== now: same-basis history")
    quarters = replayed["rows"][0]["reference_position"]["like_for_like"]
    for point in quarters["quarters"]:
        print(f"  {point['quarter_end']}  {Decimal(point['multiple']):.2f}x")
    print("  left out:", [(item["quarter_end"], item["reason"]) for item in quarters["excluded"]])
    print(f"  low {Decimal(quarters['low']):.2f}x  median {Decimal(quarters['median']):.2f}x  "
          f"high {Decimal(quarters['high']):.2f}x  today {Decimal(quarters['today']):.2f}x")
    for row in replayed["rows"]:
        position, funding = row["reference_position"], row["funding"]
        print(f"== {row['scenario_role']} ({row['name'][:44]})")
        print(f"  multiple {row['result']['multiple']}x: {position['band']} on {position['basis']}")
        print("  " + position["summary"])
        print("  bounds:", {k: {kk: str(round(Decimal(vv), 2)) if kk != "commencement" else vv for kk, vv in v.items()}
                           for k, v in funding["bounds"].items()})
        print("  " + funding["limit"])
        print(f"  price unchanged: {Decimal(row['result']['target']):.4f}")
    state = {**saved, "required_return": required_return_record({"date": "2026-11-06", "value": "4.86"}, Decimal("0.05"),
                                                                saved["trade_date"])}
    record = prepare_decision_context(state)
    page = render_decision_context(record, include_mechanical=False).replace("\\", "")
    print("== decision card case lines")
    for line in page.split("\n"):
        if line.startswith(("- base", "- downside", "- upside")) and "funding" in line:
            print("  " + line[:330])
    basis = record["scenario_decision"]
    print(f"== unchanged: weighted today {Decimal(basis['weighted_value_today']):.2f}, direction {basis['direction']}, "
          f"score {assess_audit({**state, 'decision_context': record})['score']}")
    for run in ("520623df", "2a2e47dd", "eea86100", "86aa515f", "c463bdac"):
        old = json.loads((LOGS / f"full_states_log_2026-11-09_{run}.json").read_text())
        card = prepare_decision_context(old)
        bands = [(row["reference_position"].get("basis"), row["reference_position"].get("band"))
                 for row in replay_cases(old)["rows"] if row["result"]["method"] == "revenue_case"]
        print(f"  {run}: score {assess_audit({**old, 'decision_context': card})['score']}, references {bands}")
