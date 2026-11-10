"""Replay saved run b9dde628 (2026-11-10 13:47) through the weight-stability build. No model call.

Usage: PYTHONPATH=$PWD python docs/reviews/weight-stability-proof-tools/replay.py
"""

import glob
import json
from pathlib import Path

from tradingagents.agents.decision_brief import render, since_last_decision
from tradingagents.agents.decision_context import prepare_decision_context
from tradingagents.agents.shared_valuation import annotate_disputed_cases, replay_cases
from tradingagents.default_config import DEFAULT_CONFIG

LOGS = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs"


def main():
    state = json.loads(Path(glob.glob(str(LOGS / "full_states_log_*b9dde628*.json"))[0]).read_text())
    print("--- flags on the cases of run b9dde628 ---")
    for row in annotate_disputed_cases(state, replay_cases(state))["rows"]:
        print(row["name"][:40], "|", row.get("disputed_by"), "|", row.get("dispute_note"))
    card = prepare_decision_context({**state, "decision_brief": since_last_decision(DEFAULT_CONFIG, "DOCN", state)})
    print("flagged scenarios counted:", card["scenarios"]["disputed_count"])
    brief = card["since_last_decision"]
    print("--- earlier decision:", brief["prior"]["decision_id"][:8], "---")
    print("reader:", [line for line in render(brief) if line.startswith("- Case weights")])
    following = {"trade_date": "2026-11-11", "company_of_interest": "DOCN", "run_id": "next-run",
                 "filing_evidence": state.get("filing_evidence")}
    later = since_last_decision(DEFAULT_CONFIG, "DOCN", following)
    print("--- what the next run's manager would be shown (earlier decision", later["prior"]["decision_id"][:8], ") ---")
    print([line for line in render(later, for_manager=True) if "Your case weights" in line])


if __name__ == "__main__":
    main()
