"""Replay saved run 7822a890 with a constructed event_view answer. No model call.

Usage: PYTHONPATH=$PWD python docs/reviews/event-view-proof-tools/replay.py
The manager's answer below is constructed for the proof; no saved run contains a real one.
"""

import copy
import glob
import json
from pathlib import Path

from tradingagents.agents import scenario_decision
from tradingagents.agents.event_view import (
    conditions_from_state,
    horizon_from_state,
    render_for_manager,
)
from tradingagents.agents.shared_valuation import annotate_disputed_cases, replay_cases
from tradingagents.operational_audit import REASONS

SAVED = glob.glob(str(Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_*7822a890*.json"))[0]


def main():
    state = json.loads(Path(SAVED).read_text())
    replayed = annotate_disputed_cases(state, replay_cases(state))
    conditions = conditions_from_state(state)
    print("prior_thesis observations present:", isinstance((state.get("prior_thesis") or {}).get("observations"), list))
    print("open conditions:", len(conditions), "| horizon date:", horizon_from_state(state))
    print("--- what the manager would be shown ---")
    print(render_for_manager(conditions, True, horizon_from_state(state))[:1500])
    before = scenario_decision.summarize(state, replayed)
    print("--- saved run as it is (not asked) ---")
    print("event view status:", before["event_view"]["status"])
    accepted = [(c["case_id"], c["version"], c["role"], c["weight"]) for c in before["cases"] if c["disposition"] == "accepted"]
    print("accepted cases and weights:", [(role, weight) for _i, _v, role, weight in accepted])

    def weights(by_role):
        return [{"case_id": case_id, "version": version, "weight": by_role[role]} for case_id, version, role, _w in accepted]

    def pick(words):
        return next(row["condition_id"] for row in conditions if all(word in row["label"] for word in words))

    answer = [
        {"condition_id": pick(["Revenue", ">="]), "expected_date": "2027-02-25", "favourable_when": "met",
         "favourable_weights": weights({"base": 0.55, "downside": 0.15, "upside": 0.30}),
         "adverse_weights": weights({"base": 0.40, "downside": 0.55, "upside": 0.05}),
         "reason": "Constructed for the proof: fourth-quarter revenue against the guidance low."},
        {"condition_id": pick(["convertible notes"]), "expected_date": "2026-12-15", "favourable_when": "met",
         "favourable_weights": weights({"base": 0.55, "downside": 0.25, "upside": 0.20}),
         "adverse_weights": weights({"base": 0.45, "downside": 0.40, "upside": 0.15}),
         "reason": "Constructed for the proof: how the December 1 notes were settled."}]
    asked = copy.deepcopy(state)
    manager = asked["unvalidated_outputs"]["portfolio_manager"]
    manager["event_contract"] = 1
    manager["structured"]["event_view"] = answer
    summary = scenario_decision.summarize(asked, replayed)
    print("--- with the constructed answer ---")
    print("status:", summary["event_view"]["status"], "| retry feedback:", repr(scenario_decision.retry_feedback(asked, replayed)))
    for line in scenario_decision.render(summary):
        if "Six-month view" in line or line.startswith("- Revenue") or line.startswith("- Disclosure") or "implied odds" in line:
            print(line)
    bad = copy.deepcopy(asked)
    bad["unvalidated_outputs"]["portfolio_manager"]["structured"]["event_view"][0]["favourable_weights"] = weights(
        {"base": 0.45, "downside": 0.45, "upside": 0.10})
    print("--- inconsistent answer ---")
    print(scenario_decision.retry_feedback(bad, replayed)[:600])
    missing = copy.deepcopy(asked)
    missing["unvalidated_outputs"]["portfolio_manager"]["structured"]["event_view"] = None
    print("--- missing answer ---")
    print(scenario_decision.summarize(missing, replayed)["event_view"]["problems"], "| score if unresolved:",
          REASONS["event_view_unaddressed"][0])


if __name__ == "__main__":
    main()
