"""Offline replays for the decision-inputs build. No model call, no write to the user's stores.

Run from the repository root:  PYTHONPATH=. python docs/reviews/decision-inputs-proof-tools/replay.py changes
  changes   the "Since the last decision" brief and the repaired comparison for three saved DOCN runs.
  record    the track-record scorecard from the real outcome store (read only), the same store copied
            with every 5-session window settled by hand-made prices, and the real memory entries as
            the manager now sees them.
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


def record():
    import shutil
    import tempfile
    from pathlib import Path

    from tradingagents.memory import publication, publication_outcomes as outcomes
    from tradingagents.memory.log import TradingMemoryLog

    config = dict(DEFAULT_CONFIG)
    print("== real outcome store, read only")
    print(outcomes.render_scorecard(outcomes.scorecard(config, "DOCN")))
    with tempfile.TemporaryDirectory() as scratch:
        # A copy, so the hand-made settlements never reach the user's records.
        shutil.copytree(publication.record_root(config), Path(scratch) / "publications")
        copy = {**config, "results_dir": scratch}

        def prices(ticker, cutoff, days, benchmark, **kwargs):
            if days != 5:
                return None
            return {"raw_return": -.04, "alpha_return": -.06, "benchmark_return": .02, "holding_days": 5,
                    "resolution_date": "2026-11-09", "ticker": ticker, "benchmark": benchmark,
                    "entry": {"date": "2026-11-02", "price": 100.}, "exit": {"date": "2026-11-09", "price": 96.},
                    "benchmark_entry": {"date": "2026-11-02", "price": 400.},
                    "benchmark_exit": {"date": "2026-11-09", "price": 408.},
                    "price_source": "hand-made for this proof", "price_adjustment": "none"}
        outcomes.fetch_outcome = prices
        done = outcomes.settle_publications(copy)
        print("\n== copy of the store with every 5-session window settled at -6% excess (hand-made)")
        print({key: len(value) if isinstance(value, list) else value for key, value in done.items()})
        print(outcomes.render_scorecard(outcomes.scorecard(copy, "DOCN")))
    print("\n== real memory log as the manager now sees it (allocation figures removed), first 1,600 characters")
    context = TradingMemoryLog(config).get_past_context("DOCN")
    print(context[:1600])
    print("...\n30-35% present:", "30-35%" in context, "| withheld notes:", context.count("Numeric sizing withheld"))


if __name__ == "__main__":
    {"changes": changes, "record": record}[sys.argv[1] if len(sys.argv) > 1 else "changes"]()
