"""How much scores and ratings vary between repeat runs of the same code.

    loop_noise.py REPORTS_FOLDER [REPORTS_FOLDER ...]

Each folder holds a report with its `evaluation.json`. Runs are grouped by company. For each company:
the ratings given and how many agree, and the mean and spread (highest minus lowest) of the Decision
score and of D1 to D7. The largest spread is the line a later change has to beat.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

FACTORS = [f"D{n}" for n in range(1, 8)]


def read(folder: Path) -> dict:
    record = json.loads((folder / "evaluation.json").read_text())
    decision = (folder / "final_trade_decision.md").read_text() if (folder / "final_trade_decision.md").exists() else ""
    rating = re.search(r"\*\*(?:Canonical Portfolio Manager rating|Rating)\*\*:\s*([A-Za-z]+)", decision)
    scores = {"Decision": record["scores"]["investment_decision_quality"], "Research": record["scores"]["research_quality"]}
    scores.update({name: record["decision_components"][name]["score"] for name in FACTORS})
    return {"ticker": (record.get("identity") or {}).get("ticker"), "rating": rating.group(1) if rating else None,
            "scores": scores}


def summarize(runs: list[dict]) -> dict:
    out = {}
    groups = defaultdict(list)
    for run in runs:
        groups[str(run["ticker"]).upper()].append(run)
    for ticker, rows in sorted(groups.items()):
        ratings = Counter(row["rating"] for row in rows)
        stats = {}
        for name in rows[0]["scores"]:
            values = [float(row["scores"][name]) for row in rows if row["scores"].get(name) is not None]
            stats[name] = {"mean": round(sum(values) / len(values), 2), "spread": round(max(values) - min(values), 2)}
        out[ticker] = {"runs": len(rows), "ratings": dict(ratings),
                       "rating_agreement": f"{ratings.most_common(1)[0][1]} of {len(rows)}", "scores": stats}
    return out


def main(argv=None):
    result = summarize([read(Path(name)) for name in (argv if argv is not None else sys.argv[1:])])
    for ticker, row in result.items():
        print(f"{ticker}: {row['runs']} run(s); ratings {row['ratings']} (agreement {row['rating_agreement']})")
        print("   " + "  ".join(f"{name} {stat['mean']} ±{stat['spread']}" for name, stat in row["scores"].items()))
    spreads = [row["scores"]["Decision"]["spread"] for row in result.values() if row["runs"] > 1]
    if spreads:
        print(f"largest Decision spread between repeats: {max(spreads)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
