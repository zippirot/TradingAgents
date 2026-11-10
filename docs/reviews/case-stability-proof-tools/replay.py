"""Replay saved run 36c26c9d (2026-11-10 12:50) through the stability build. No model call.

Usage: PYTHONPATH=$PWD python docs/reviews/case-stability-proof-tools/replay.py
"""

import glob
import json
from pathlib import Path

from tradingagents.agents import scenario_decision
from tradingagents.agents.prior_cases import prior_cases, render_prior_cases
from tradingagents.agents.shared_valuation import annotate_disputed_cases, replay_cases
from tradingagents.default_config import DEFAULT_CONFIG

LOGS = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs"


def main():
    state = json.loads(Path(glob.glob(str(LOGS / "full_states_log_*36c26c9d*.json"))[0]).read_text())
    replayed = annotate_disputed_cases(state, replay_cases(state))
    print("--- 3. what the flag on the downside case now says ---")
    for row in replayed["rows"]:
        if row.get("disputed_by"):
            print(row["name"][:50], "|", row.get("dispute_note"))
    summary = scenario_decision.summarize(state, replayed)
    print("--- 2. rating check on the saved decision ---")
    print("rating", state["final_rating"], "| direction", summary["direction"], "| return gap",
          summary["return_gap_points"][:6], "| consistency", summary["consistency"], "| basis", summary["contrary_basis"])
    print([line for line in scenario_decision.render(summary) if line.startswith("Rating check")][0])
    print("sent back once with:", scenario_decision.retry_feedback(state, replayed))
    print("--- 1. what the next run's analyst would be shown (next run = one after 36c26c9d) ---")
    following = {"trade_date": "2026-11-11", "company_of_interest": "DOCN", "run_id": "next-run",
                 "filing_evidence": state.get("filing_evidence")}
    context = prior_cases(DEFAULT_CONFIG, "DOCN", following)
    if context is None:
        print("no earlier publication found with this configuration")
        return
    print("earlier decision:", context["decision_id"][:8], "| label:", context["label"], "| new filings:",
          len(context["filings"]["rows"]), "| status:", context["filings"]["status"])
    print("multiples carried:", [(c.get("scenario_role"), c["request"]["multiple"]) for c in context["cases"]])
    text = render_prior_cases(context)
    print("prompt text length:", len(text))
    print(text[:900])


if __name__ == "__main__":
    main()
