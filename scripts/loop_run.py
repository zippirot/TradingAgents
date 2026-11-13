"""Start one unattended Shallow analysis for the improvement loop and record what it cost.

    loop_run.py --ticker WMT [--date YYYY-MM-DD] [--cycle N] [--dry-run]

Every question the app would ask is answered here: Shallow depth (one debate round, one risk round), the
loop's models, save, no show. The run uses the loop's own results, cache and memory folders and a
made-up portfolio file, so the user's rating history and holdings are never read or changed. It refuses
to start when what is left of the cycle's budget is below the last measured cost of a run.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "docs" / "loop" / "state.json"
# LOOP_PORTFOLIO picks another made-up file, such as the concentrated one; never the user's own.
PORTFOLIO = Path(os.environ.get("LOOP_PORTFOLIO") or ROOT / "docs" / "loop" / "portfolio.loop.json")
LOOP_HOME = Path.home() / ".tradingagents" / "loop"
LAUNCHER = Path.home() / "Documents" / "ChatGPT" / "Tauric" / "TradingAgents"
# The user's ChatGPT plan (signed in once with `tradingagents login chatgpt`) is the default since 2026-11-13;
# LOOP_PROVIDER=openrouter goes back to the paid key, where cost is measured.
PROVIDER = os.environ.get("LOOP_PROVIDER") or "chatgpt"
MODEL = "openai/gpt-6.1-terra-pro" if PROVIDER == "openrouter" else "gpt-6.1-terra"
SETTINGS = {
    "TRADINGAGENTS_LLM_PROVIDER": PROVIDER,
    "TRADINGAGENTS_LLM_BACKEND_URL": "https://openrouter.ai/api/v1" if PROVIDER == "openrouter" else "https://api.openai.com/v1",
    "TRADINGAGENTS_QUICK_THINK_LLM": MODEL,
    "TRADINGAGENTS_DEEP_THINK_LLM": MODEL,
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
    "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
    "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
    "TRADINGAGENTS_NO_UPDATE_CHECK": "1",
}
# LOOP_ANALYSTS limits the analysts, e.g. "market,fundamentals" for a look-back run where undated feeds would leak.
ANALYSTS = os.environ.get("LOOP_ANALYSTS") or "market,social,news,fundamentals"


def load_state(path: Path = STATE) -> dict:
    return json.loads(path.read_text()) if path.exists() else {"budget_per_cycle": 50.0, "runs": []}


def remaining(state: dict, cycle: int) -> float:
    spent = sum(run.get("cost") or 0 for run in state["runs"] if run.get("cycle") == cycle)
    return float(state["budget_per_cycle"]) - spent


def last_cost(state: dict) -> float | None:
    costs = [run["cost"] for run in state["runs"] if run.get("cost") and run.get("kind") != "second_opinion"]
    return costs[-1] if costs else None


def refusal(state: dict, cycle: int) -> str | None:
    """Why this run may not start, or None. An unmeasured cost never blocks the first run."""
    left, cost = remaining(state, cycle), last_cost(state)
    if left <= 0:
        return f"cycle {cycle} has spent its {state['budget_per_cycle']:.2f} dollar budget"
    if cost is not None and left < cost:
        return f"cycle {cycle} has {left:.2f} dollars left and the last run cost {cost:.2f}"
    return None


def command(ticker: str, date: str) -> list[str]:
    python = LAUNCHER / ".venv" / "bin" / "python"
    return [str(python), "-m", "cli.main", "--ticker", ticker, "--date", date, "--analysts", ANALYSTS,
            "--save", "--no-show", "--no-ground-truth-audit", "--html", "--no-checkpoint",
            "--portfolio", str(PORTFOLIO)]


def environment(home: Path = LOOP_HOME, results: str = "logs") -> dict:
    from dotenv import dotenv_values

    keys = {name: value for name, value in dotenv_values(LAUNCHER / ".env").items() if value}
    return {**os.environ, **keys, **SETTINGS,
            "TRADINGAGENTS_RESULTS_DIR": str(home / results), "TRADINGAGENTS_CACHE_DIR": str(home / "cache"),
            "TRADINGAGENTS_MEMORY_LOG_PATH": str(home / "memory" / "trading_memory.md"),
            "TRADINGAGENTS_PREFS_PATH": str(home / "cli_prefs.json")}


def provider_usage(env: dict) -> float | None:
    """Dollars the provider has billed this key so far; the difference across a run is its cost."""
    if PROVIDER != "openrouter":
        return None  # a subscription run bills nothing to the key
    try:
        request = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                         headers={"Authorization": f"Bearer {env['OPENROUTER_API_KEY']}"})
        with urllib.request.urlopen(request, timeout=20) as reply:  # noqa: S310 - fixed https address
            return float(json.load(reply)["data"]["usage"])
    except Exception:  # noqa: BLE001 - cost is then reported as unmeasured, never guessed
        return None


def newest_run(home: Path, ticker: str, date: str, results: str = "logs") -> Path | None:
    folders = [path for path in (home / results / ticker.upper() / date).glob("*") if path.is_dir()]
    return max(folders, key=lambda path: path.stat().st_mtime) if folders else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--date", default=str(datetime.date.today()))
    parser.add_argument("--cycle", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fresh", metavar="TAG", help="use a results folder of its own (logs-TAG), so the run has no "
                        "earlier rating or thesis to lean on; repeats of one company are then independent")
    parser.add_argument("--skip-cost", action="store_true", help="do not measure cost (runs in parallel are "
                        "measured together by the caller)")
    parser.add_argument("--state", type=Path, default=STATE)
    args = parser.parse_args(argv)
    state = load_state(args.state)
    blocked = refusal(state, args.cycle)
    line = command(args.ticker, args.date)
    print("command:", " ".join(line))
    for name, value in SETTINGS.items():
        print(f"  {name}={value}")
    print(f"  results, cache and memory under {LOOP_HOME}; portfolio {PORTFOLIO.name} (made-up figures)")
    print(f"  cycle {args.cycle}: {remaining(state, args.cycle):.2f} of {state['budget_per_cycle']:.2f} dollars left; "
          f"last measured run cost: {last_cost(state) if last_cost(state) is not None else 'not yet measured'}")
    if blocked:
        print("REFUSED:", blocked)
        return 2
    if args.dry_run:
        print("dry run: nothing was started")
        return 0
    results = f"logs-{args.fresh}" if args.fresh else "logs"
    env = environment(results=results)
    if args.fresh:
        env["TRADINGAGENTS_MEMORY_LOG_PATH"] = str(LOOP_HOME / results / "trading_memory.md")
    for folder in (results, "cache", "memory"):
        (LOOP_HOME / folder).mkdir(parents=True, exist_ok=True)
    before, started = (None if args.skip_cost else provider_usage(env)), datetime.datetime.now().isoformat(timespec="seconds")
    log = LOOP_HOME / results / f"loop_run_{args.ticker.upper()}_{started.replace(':', '')}.log"
    with log.open("w") as out:
        code = subprocess.run(line, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=out,  # noqa: S603
                              stderr=subprocess.STDOUT, check=False).returncode
    after = None if args.skip_cost else provider_usage(env)
    cost = round(after - before, 4) if before is not None and after is not None else None
    folder = newest_run(LOOP_HOME, args.ticker, args.date, results)
    state = load_state(args.state)
    state["runs"].append({"cycle": args.cycle, "ticker": args.ticker.upper(), "date": args.date, "exit": code,
                          "cost": cost, "started": started, "tag": args.fresh, "run_dir": str(folder) if folder else None,
                          "log": str(log)})
    args.state.write_text(json.dumps(state, indent=1))
    print(f"exit {code}; run folder: {folder}; cost: {cost if cost is not None else 'not measured'} dollars; log: {log}")
    return code


if __name__ == "__main__":
    sys.exit(main())
