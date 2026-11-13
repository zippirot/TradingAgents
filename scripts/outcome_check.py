"""The loop's yardstick in one command: were the app's past views right?

    PYTHONPATH=$PWD python scripts/outcome_check.py run    --label NAME [--parallel 4]
    PYTHONPATH=$PWD python scripts/outcome_check.py report --label NAME [--against BASELINE]

`run` analyses every company in docs/loop/outcome_set.json as of every date in it, with the code of the
checkout this script is in, the made-up standard portfolio, and the market and fundamentals analysts only
(news and social feeds are not dated and would leak). A run already saved under the label is not repeated,
so an interrupted check is resumed by the same command. `report` sets each view beside what the shares
then did against the market over 21 and 63 trading sessions, and beside another label when one is named.

Evidence, not proof: the windows overlap and one market period is covered. A view is counted once per
company and date.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SET = ROOT / "docs" / "loop" / "outcome_set.json"
HOME = Path.home() / ".tradingagents" / "loop"


def tag(label: str, day: str) -> str:
    return f"oc-{label}-{day.replace('-', '')}"


def plan(chosen: dict, label: str, home: Path = HOME) -> list[tuple[str, str]]:
    """Every company and date of the set not yet saved under this label."""
    todo = []
    for day in chosen["dates"]:
        for ticker in chosen["tickers"]:
            saved = home / f"logs-{tag(label, day)}" / ticker / "TradingAgentsStrategy_logs"
            if not any(saved.glob("full_states_log_*.json")):
                todo.append((ticker, day))
    return todo


def command(ticker: str, day: str, label: str, home: Path = HOME) -> list[str]:
    return [sys.executable, str(ROOT / "scripts" / "loop_run.py"), "--ticker", ticker, "--date", day, "--fresh",
            tag(label, day), "--skip-cost", "--state", str(home / f"oc-state-{label}.json")]


def run(label: str, parallel: int, chosen: dict, home: Path = HOME) -> int:
    todo = plan(chosen, label, home)
    total = len(chosen["dates"]) * len(chosen["tickers"])
    print(f"{label}: {total - len(todo)} of {total} already saved; starting {len(todo)}, {parallel} at a time")
    env = {**os.environ, "LOOP_ANALYSTS": "market,fundamentals", "PYTHONPATH": str(ROOT),
           "LOOP_PORTFOLIO": str(ROOT / "docs" / "loop" / "portfolio.loop.json")}

    def one(item):
        done = subprocess.run(command(*item, label, home), cwd=ROOT, env=env, capture_output=True, text=True, check=False)  # noqa: S603
        print(f"  {item[0]} {item[1]}: exit {done.returncode}", flush=True)
        return done.returncode

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        failed = sum(1 for code in pool.map(one, todo) if code)
    print(f"{label}: finished; {failed} run(s) did not exit cleanly")
    return 1 if failed else 0


def lines(summary: dict, other: dict | None = None, names=("this", "against")) -> list[str]:
    """The comparison as text: one block per horizon, the second label beside the first when given."""
    out = []
    for sessions, block in summary["horizons"].items():
        theirs = (other or {}).get("horizons", {}).get(sessions) or (other or {}).get("horizons", {}).get(str(sessions))
        out.append(f"After {sessions} trading sessions, against the market ({names[0]}"
                   + (f" | {names[1]}" if theirs else "") + "):")
        for view in ("Attractive", "Fair", "Unattractive"):
            def cell(source, view=view):
                row = (source or {}).get("by_stock_view", {}).get(view)
                return (f"{row['mean_excess']:+.1f} points, {row['count']} views, "
                        f"{round(row['share_below_market'] * row['count'])} below the market") if row else "none"
            out.append(f"  {view:12} {cell(block)}" + (f" | {cell(theirs)}" if theirs else ""))
        out.append(f"  direction right  {block['directional_right']}" + (f" | {theirs['directional_right']}" if theirs else ""))
        out.append(f"  valuation rank   {block['valuation_rank_correlation']}"
                   + (f" | {theirs['valuation_rank_correlation']}" if theirs else ""))
    return out


def report(label: str, against: str | None, home: Path = HOME) -> dict:
    from scripts.lookback_outcomes import outcomes, runs, summary

    result = {}
    for name in filter(None, (label, against)):
        rows = outcomes(runs(home, f"logs-oc-{name}-"))
        result[name] = {"rows": rows, "summary": summary(rows)}
    print(f"{label}: {len(result[label]['rows'])} rated views"
          + (f"; {against}: {len(result[against]['rows'])}" if against else ""))
    print("\n".join(lines(result[label]["summary"], result[against]["summary"] if against else None, (label, against))))
    (home / f"outcome-check-{label}.json").write_text(json.dumps(result, indent=1))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("run", "report"))
    parser.add_argument("--label", required=True, help="a short name for this version of the code, e.g. base or the commit")
    parser.add_argument("--against", help="report only: another label to set beside this one")
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args(argv)
    if args.action == "run":
        return run(args.label, args.parallel, json.loads(SET.read_text()))
    report(args.label, args.against)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
