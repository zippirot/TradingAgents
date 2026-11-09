"""Offline replay of DOCN run 2a2e47dd for Build W. No network or model call.

Run from the repository root:  PYTHONPATH=. python docs/reviews/report-defect-closure-proof-tools/replay_w.py
"""
import copy
import json
import re
from pathlib import Path

from tradingagents.agents.citation_check import check_pm_citations
from tradingagents.agents.decision_context import prepare_decision_context, render_decision_context
from tradingagents.agents.document_questions import (
    enforce_followup_judgments,
    lookup_document_questions,
    render_document_followups,
)
from tradingagents.agents.shared_valuation import prepare_shared_valuation
from tradingagents.memory import thesis
from tradingagents.operational_audit import assess_audit

LOG = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-09_2a2e47dd.json"
s = json.loads(LOG.read_text())

# W1
scenarios = s["shared_valuation_scenarios"]
record = prepare_shared_valuation(s, copy.deepcopy(scenarios["requests"]))
print("W1 rows:", [(row.get("name"), row["result"]["status"], row["result"].get("target")) for row in record["rows"]])
print("W1 reasons:", record["reasons"])
priced = {**s, "shared_valuation_scenarios": record}

# W2: restore the judgments as the Research Manager wrote them, then enforce.
marker = re.compile(r"^No retrieved passage; model judgment '(\w+)' discarded\. ")
original = []
for row in s["document_followup_judgments"]:
    found = marker.match(row["explanation"])
    original.append({**row, "classification": found[1], "explanation": row["explanation"][found.end():]} if found else row)
print("W2 retained record still validates:", lookup_document_questions(s) == {})
print("W2 enforced:", [(row["question_id"], row["classification"]) for row in enforce_followup_judgments(original, s["document_followups"])])
print("W2 card:", [line[:110] for line in render_document_followups(s).splitlines() if "bear-1" in line])

# W3
audit = assess_audit(s)
print("W3 score:", audit["score"], audit["name"])
print("W3 invalid or identity findings:", [f["text"] for f in audit["findings"] if re.search("malformed|mismatch", f["text"])])
print("W3 inputs:", audit["inputs"])

# W5
result = thesis.prepare_thesis(s["thesis_candidate"], s["prior_thesis"], s["final_rating"], s["trade_date"], s["run_id"],
                               financial_evidence=s["financial_evidence"], price_observation=s["price_observation"],
                               ticker=s["company_of_interest"])
events = [row for row in result["conditions"] if row.get("kind") == "event"]
print("W5 event rows:", [(row["description"][:60], len(row.get("condition_aliases", []))) for row in events])
print("W5 omitted warnings:", [w for w in result["warnings"] if "omitted from proposal" in w])

# W6
context = prepare_decision_context({**priced, "thesis": result})
card = render_decision_context(context)
print("W6 double periods on card:", card.count(".."))
print("W6 citation mismatches:", [(m["citation_id"], m["canonical_value"]) for m in check_pm_citations(s)["mismatches"]])
