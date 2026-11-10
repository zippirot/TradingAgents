"""Offline replays for the decision-inputs build. No model call, no write to the user's stores.

Run from the repository root:  PYTHONPATH=. python docs/reviews/decision-inputs-proof-tools/replay.py changes
  changes   the "Since the last decision" brief and the repaired comparison for three saved DOCN runs.
  record    the track-record scorecard from the real outcome store (read only), the same store copied
            with every 5-session window settled by hand-made prices, and the real memory entries as
            the manager now sees them.
  sizing    the "Position and sizing" block for saved run c463bdac with the sample portfolio file beside
            this script (made-up holdings), as the agents see it and as the report shows it, and the same
            run with no file.
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


def sizing():
    import tempfile
    from pathlib import Path

    from tradingagents.agents.context import get_portfolio_context_from_state
    from tradingagents.agents.output_validation import enforce_publication
    from tradingagents.portfolio import load_portfolio
    from tradingagents.reporting import evidence_snapshot, position_sizing_note, write_report_tree

    book = load_portfolio(Path(__file__).with_name("sample-portfolio.json"))
    state = saved("c463bdac")
    plain = enforce_publication(state)["final_trade_decision"]
    print("== no file: fixed sentence present:",
          "Position sizing: qualitative only; no validated numerical allocation." in plain,
          "| block:", repr(position_sizing_note(state)))
    state.update(portfolio_context=book.render("DOCN"), portfolio_inputs=book.inputs())
    print("\n== what the Trader, risk analysts and Portfolio Manager are given")
    print(get_portfolio_context_from_state(state))
    updated = {**state, **enforce_publication(state)}
    print("\n== what the report shows above the decision")
    print(position_sizing_note(updated))
    line = [row for row in updated["final_trade_decision"].splitlines() if row.startswith("Position sizing:")]
    print("\n== line in the published decision text:", line)
    published = json.dumps([updated["final_trade_decision"], evidence_snapshot(updated)])
    private = ("portfolio_value", "loss_budget", "rating_weights", "150 units", "4.7% of the portfolio",
               "units fewer than you hold")
    print("== published text and evidence contain any portfolio input or computed figure:",
          [text for text in private if text in published], "| the fingerprint:", book.fingerprint() in published)
    with tempfile.TemporaryDirectory() as scratch:
        write_report_tree(updated, "DOCN", Path(scratch))
        for name in ("complete_report.md", "complete_report.html"):
            print(f"== {name} carries the block:", "Position and sizing" in (Path(scratch) / name).read_text())


if __name__ == "__main__":
    {"changes": changes, "record": record, "sizing": sizing}[sys.argv[1] if len(sys.argv) > 1 else "changes"]()
