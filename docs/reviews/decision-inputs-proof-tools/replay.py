"""Offline replays for the decision-inputs build. No model call, no write to the user's stores.

Run from the repository root:  PYTHONPATH=. python docs/reviews/decision-inputs-proof-tools/replay.py changes
  changes   the "Since the last decision" brief and the repaired comparison for three saved DOCN runs.
"""
import glob
import json
import os
import sys

from tradingagents.default_config import DEFAULT_CONFIG

LOGS = os.path.expanduser("~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/")


def saved(run):
    with open(glob.glob(f"{LOGS}full_states_log_*_{run}*.json")[0]) as handle:
        return json.load(handle)


def changes():
    from tradingagents.agents.assumption_history import assumption_changes
    from tradingagents.agents.decision_brief import render, since_last_decision

    config = dict(DEFAULT_CONFIG)
    for run in ("eea86100", "86aa515f", "c463bdac"):
        state = saved(run)
        before = (state.get("decision_context") or {}).get("assumption_changes") or {}
        print(f"== run {run}: saved comparison was {before.get('status')}"
              + (f" ({before.get('reason')})" if before.get("reason") else ""))
        now = assumption_changes(config, "DOCN", state)
        print(f"   comparison now: {now['status']}, {len(now['rows'])} row(s), "
              f"{len(now.get('unusable', []))} unusable case(s), against {str(now['prior_decision_id'])[:8]}")
        brief = since_last_decision(config, "DOCN", state)
        print("\n".join(render(brief)) or f"   brief: {brief['status']}")
        print()


if __name__ == "__main__":
    {"changes": changes}[sys.argv[1] if len(sys.argv) > 1 else "changes"]()
