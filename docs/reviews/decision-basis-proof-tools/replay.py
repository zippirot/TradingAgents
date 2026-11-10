"""Replay of DOCN run eea86100 (two priced cases) for Build Q. Offline unless --live is given.

Run from the repository root:  PYTHONPATH=. python docs/reviews/decision-basis-proof-tools/replay.py
  --live N   re-run only the Portfolio Manager step N times with the run's own deep model (paid calls).
  --funded   with --live: first restate each saved case's cash so the scheduled finance and equipment
             payments are a separate entry (same closing cash, same price). Hand-made for this proof.
"""
import copy
import glob
import json
import os
import sys
import urllib.request
from decimal import Decimal

from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.scenario_decision import priced_cases, summarize
from tradingagents.agents.shared_valuation import _BLOCK, annotate_disputed_cases, replay_cases

LOG = glob.glob(os.path.expanduser(
    "~/.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-09_eea86100*.json"))[0]
with open(LOG) as handle:
    saved = json.load(handle)


def funded(state):
    """Split scheduled payments out of each case's operations entry; nothing else changes."""
    report = state["financial_claim_validation"]["raw_report"]
    body = _BLOCK.findall(report)[0]
    rows = json.loads(body)
    scheduled = {case["case_id"]: row["funding"]["scheduled_finance_payments"]
                 for case, row in zip(cases, replayed["rows"], strict=True)}
    amount = Decimal(next(iter(scheduled.values()))).quantize(Decimal(1))
    for row in rows:
        row.setdefault("scenario_role", "downside" if "ownside" in row["name"] else "base")
        changes = row["request"]["capital"]["cash_changes"]
        operations = next(change for change in changes if change["source"] == "operations")
        operations["amount"] = str(Decimal(operations["amount"]) + amount)
        operations["reason"] += " Stated before scheduled finance and equipment payments."
        changes.append({"source": "finance_payments", "amount": str(-amount),
                        "reason": "Scheduled finance-lease and equipment payments through the valuation date, "
                                  "from the maturity schedule in the 10-Q."})
    state["financial_claim_validation"]["raw_report"] = report.replace(body, json.dumps(rows))
    return state


def manager_time_state():
    """The state the Portfolio Manager read: raw role outputs, none of its own results."""
    raw = saved["unvalidated_outputs"]
    state = copy.deepcopy(saved)
    for key in ("investment_plan", "trader_investment_plan", "risk_debate_state", "investment_debate_state",
                "market_report", "sentiment_report", "news_report", "fundamentals_report"):
        if key in raw:
            state[key] = copy.deepcopy(raw[key])
    state["unvalidated_outputs"] = {k: v for k, v in raw.items() if k != "portfolio_manager"}
    for key in ("final_trade_decision", "final_rating", "decision_context", "target_validation"):
        state.pop(key, None)
    return state


def block(state):
    text = render_decision_context(prepare_decision_context(state), include_mechanical=False).replace("\\", "")
    return text[text.index("**Basis**"):text.index("**Horizon**")].strip()


replayed = annotate_disputed_cases(saved, replay_cases(saved))
cases = priced_cases(replayed)
print("== Q1/Q2 on the two saved cases")
for case in cases:
    print(f"- {case['name'][:48]}: {case['price'][:6]} | funding {case['funding']} | band {case['reference_band']}")
    print("  ", case["funding_summary"][:170])

print("\n== Q3 card, as the run recorded it (decision made before this contract)")
print(block(saved))
stub = copy.deepcopy(saved)
manager = stub["unvalidated_outputs"]["portfolio_manager"]
manager["scenario_contract"] = 1
print("\n== Q3 card, same decision under the new contract with no scenario_view")
print(block(stub))
manager["structured"]["scenario_view"] = [
    {"case_id": case["case_id"], "version": case["version"], "disposition": "accepted", "weight": weight,
     "rejected_input": None, "reason": "Stub answer for the offline replay."}
    for case, weight in zip(cases, (0.6, 0.4), strict=True)]
print("\n== Q3 card, stub answer accepting both cases 60/40")
print(block(stub))

if "--live" in sys.argv:
    from dotenv import dotenv_values, load_dotenv

    import tradingagents.agents.managers.portfolio_manager as manager_module
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients import create_tier_client

    env = os.path.expanduser("~/Documents/ChatGPT/Tauric/TradingAgents/.env")
    load_dotenv(env)

    def usage():
        request = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={
            "Authorization": "Bearer " + dotenv_values(env)["OPENROUTER_API_KEY"]})
        return float(json.load(urllib.request.urlopen(request, timeout=30))["data"]["usage"])

    settings = saved.get("run_settings") or {}
    config = {**DEFAULT_CONFIG, **{key: value for key, value in settings.items() if key in DEFAULT_CONFIG}}
    llm = create_tier_client(config, "deep").get_llm()
    calls, original = [], manager_module.invoke_structured

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    manager_module.invoke_structured = counted
    start = usage()
    for attempt in range(int(sys.argv[sys.argv.index("--live") + 1])):
        if usage() - start > 8:
            print("Stopped: spend guard reached.")
            break
        calls.clear()
        state = funded(manager_time_state()) if "--funded" in sys.argv else manager_time_state()
        result = manager_module.create_portfolio_manager(llm)(state)
        done = {**state, **result}
        structured = done["unvalidated_outputs"]["portfolio_manager"].get("structured") or {}
        summary = summarize(done, annotate_disputed_cases(done, replay_cases(done)))
        if "--funded" in sys.argv:
            for case in priced_cases(annotate_disputed_cases(state, replay_cases(state))):
                print(f"   funded case {case['name'][:40]}: {case['price'][:6]} | role {case['role']} | funding {case['funding']}")
        print(f"\n== LIVE {attempt + 1}: model {config['deep_think_llm']}; manager calls {len(calls)}; "
              f"rating {done.get('final_rating')}; scenario status {summary['status']}; "
              f"consistency {summary.get('consistency')}")
        print("scenario_view:", json.dumps(structured.get("scenario_view"))[:1500])
        print("rating_basis_reason:", structured.get("rating_basis_reason"))
        print("no_case_reason:", (structured.get("no_case_reason") or "")[:300])
        print(block(done))
    print(f"\nOpenRouter key usage for the live part: ${usage() - start:.2f}")
