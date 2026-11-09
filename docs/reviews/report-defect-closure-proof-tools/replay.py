"""Offline replay of DOCN run 520623df for Builds V, T, E, P, F, X and S. No network or model call.

Run from the repository root:  PYTHONPATH=. python docs/reviews/report-defect-closure-proof-tools/replay.py
"""
import copy
import json
import re
import tempfile
from datetime import date
from decimal import Decimal as D
from pathlib import Path

from tradingagents.agents.citation_check import check_pm_citations
from tradingagents.agents.decision_context import prepare_decision_context
from tradingagents.agents.document_questions import enforce_followup_judgments
from tradingagents.agents.shared_valuation import prepare_shared_valuation
from tradingagents.agents.trader.trader import _complete_fallback
from tradingagents.agents.valuation_reference import _latest_ttm
from tradingagents.dataflows.disclosure_context import collapse_quote_packages
from tradingagents.dataflows.disclosure_evidence import parse_disclosure_report
from tradingagents.dataflows.vendors import sec_edgar
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
from tradingagents.memory import thesis
from tradingagents.reporting import evidence_appendix, write_report_tree

LOG = Path.home() / ".tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-09_520623df.json"
s = json.loads(LOG.read_text())

# V: as recorded, then with the bridge the case's own reasons describe.
scenarios = s["shared_valuation_scenarios"]
requests = scenarios.get("analyst_requests") or scenarios["requests"]
print("V as recorded:", prepare_shared_valuation(s, copy.deepcopy(requests))["reasons"])
bridged = copy.deepcopy(requests)
capital = bridged[0]["request"]["capital"]
facts = {f["fact_id"]: f for f in s["financial_evidence"]["facts"]}
shares = D(str(facts[capital["closing_shares"]["fact_ids"][0]]["value"]))
cash = D(str(facts[capital["cash"]["fact_ids"][0]]["value"]))
capital["share_changes"] = [
    {"source": "conversion", "shares": "3900000", "converted_principal": "153200000", "instrument": "2030 notes", "reason": "as stated"},
    {"source": "sbc", "shares": str(D(capital["closing_shares"]["value"]) - shares - 3900000), "instrument": "RSU and ESPP", "reason": "as stated"}]
capital["cash_changes"] = [
    {"source": "debt", "amount": "-312300000", "reason": "as stated"},
    {"source": "operations", "amount": str(D(capital["cash"]["value"]) - cash + 312300000), "reason": "as stated"}]
print("V stated bridge:", prepare_shared_valuation(s, bridged)["reasons"])

# T
result = thesis.prepare_thesis(s["thesis_candidate"], s["prior_thesis"], s["final_rating"], s["trade_date"], s["run_id"],
                               financial_evidence=s["financial_evidence"], price_observation=s["price_observation"],
                               ticker=s["company_of_interest"])
print("T rows:", [(row["metric"][:32], row["disposition"]) for row in prepare_decision_context({**s, "thesis": result})["conditions"]])
print("T warnings:", result["warnings"])

# E
citations = check_pm_citations(s)
print("E citations:", citations["matched"], "of", citations["checked"], "mismatches", citations["mismatches"], "unresolved", citations["unresolved_citations"])
print("E prompt-only section:", "#### Prompt-only references" in evidence_appendix(s))
out = Path(tempfile.mkdtemp())
write_report_tree(s, "DOCN", out, settings=s.get("run_settings") or {}, html=True)
for name in ("complete_report.md", "complete_report.html"):
    text = (out / name).read_text()
    print("E", name, {k: text.count(k) for k in ("&#x27;", "&amp;#", "unavailable USD")})

# P (cached SEC companyfacts)
package = sec_edgar.get_financial_evidence("NBIS", "2026-11-09", peer_revenue_definitions=True, period_floor=date(2023, 11, 9))
print("P:", [w for w in package.warnings if "Revenues" in w], "TTM:", _latest_ttm(package, date(2026, 11, 6), "USD"))

# F
for row in enforce_followup_judgments(s["document_followup_judgments"], s["document_followups"]):
    print("F", row["question_id"], row["classification"], row["explanation"][:70])

# X
outputs = s["unvalidated_outputs"]
print("X carried:", "Carried from the Research Manager" in _complete_fallback(outputs["trader_investment_plan"], outputs["investment_plan"]))

# S
raw = s["financial_claim_validation"]["raw_report"]
packages = collapse_quote_packages(tuple(DisclosurePackage.model_validate(p) for p in s["disclosure_evidence"]["packages"]))
blocks = {(d.source_id, b.locator): b.section + "\n" + b.text for p in packages for d in p.documents for b in d.blocks}
parsed = parse_disclosure_report(raw, blocks, packages=packages)
print("S accepted:", [(c.metric, str(c.value)) for c in parsed.claims])
print("S rejected:", [re.sub(r" \(sec-document.*", "", r) for r in parsed.rejected])
