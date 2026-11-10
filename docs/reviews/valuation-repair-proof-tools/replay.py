"""Offline replay of three real rejected valuation submissions (Build R). No network or model call.

Run from the repository root:  PYTHONPATH=. python docs/reviews/valuation-repair-proof-tools/replay.py
Pass --live to send run c463bdac's rejected block to the configured quick model once (one paid call).
"""
import copy
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from tradingagents.agents.analysts.fundamentals_analyst import SHARED_VALUATION_INPUTS
from tradingagents.agents.shared_valuation import (
    _BLOCK,
    prepare_shared_valuation,
    prepare_with_correction,
)
from tradingagents.operational_audit import assess_audit

LOGS = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs"


class Stub:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def invoke(self, prompt):
        self.calls += 1
        return SimpleNamespace(content=self.reply)


def load(run):
    state = json.loads((LOGS / f"full_states_log_2026-11-09_{run}.json").read_text())
    state.pop("shared_valuation_scenarios", None)
    return state


def hand_corrected(run, state):
    """What a correct answer looks like for each run's failure, for the stub."""
    body = _BLOCK.findall(state["financial_claim_validation"]["raw_report"])[0]
    if run == "c463bdac":  # capital closed outside request
        row, _ = json.JSONDecoder().raw_decode(body[1:])
        rows = [{"name": row["name"], "request": {**row["request"], "capital": row["capital"]}}]
    else:
        rows = json.loads(body)
        for row in rows:
            capital = row["request"]["capital"]
            for value in capital["obligations"].values():
                value.setdefault("assumption", "estimated")
            for change in capital.get("share_changes", []):
                if change.get("source") == "conversion":
                    change.setdefault("instrument", "2030 Convertible Notes")
    return "```valuation_scenarios\n" + json.dumps(rows) + "\n```"


def summary(record):
    prices = [(row["name"][:40], str(row["result"].get("target"))[:8]) for row in record["rows"]]
    return record["status"], prices, [reason[:150] for reason in record["reasons"]]


for run in ("2a2e47dd", "86aa515f", "c463bdac"):
    state = load(run)
    first = prepare_shared_valuation(state)
    print(f"\n== {run} as submitted:", *summary(first))
    if not first["reasons"] or first["status"] == "available":
        print("   nothing to correct on current code")
        continue
    good = Stub(hand_corrected(run, copy.deepcopy(state)))
    fixed = prepare_with_correction(state, good, SHARED_VALUATION_INPUTS)
    print("   good correction:", *summary(fixed), "| calls", good.calls,
          "| score", assess_audit({**state, "shared_valuation_scenarios": fixed})["score"])
    bad = Stub(_BLOCK.search(state["financial_claim_validation"]["raw_report"]).group(0))
    kept = prepare_with_correction(state, bad, SHARED_VALUATION_INPUTS)
    audit = assess_audit({**state, "shared_valuation_scenarios": kept})
    print("   bad correction:", *summary(kept), "| score", audit["score"],
          [finding["code"] for finding in audit["findings"]])

if "--live" in sys.argv:
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients import create_tier_client

    state = load("c463bdac")
    settings = state.get("run_settings") or {}
    config = {**DEFAULT_CONFIG, **{key: value for key, value in settings.items() if key in DEFAULT_CONFIG}}
    llm = create_tier_client(config, "quick").get_llm()
    record = prepare_with_correction(state, llm, SHARED_VALUATION_INPUTS)
    print("\n== c463bdac LIVE correction by", config["quick_think_llm"], ":", *summary(record))
    print("   corrected:", "corrected_submission" in record,
          "| score", assess_audit({**state, "shared_valuation_scenarios": record})["score"])
    assert re.search(r"corrected by the analyst", " ".join(record["reasons"])), "live correction was not accepted"
