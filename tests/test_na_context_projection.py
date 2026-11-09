"""Post-gate prompt projections retain source-only evidence and exact lineage."""

import json

from tests.test_evidence_gate import complete_evidence
from tradingagents.agents.context import get_instrument_context_from_state
from tradingagents.agents.evidence_presentation import (
    REFERENCE_END,
    REFERENCE_START,
    prompt_reference_map,
)
from tradingagents.agents.evidence_validation import assess_financial_package


def test_gate_retains_exact_to_short_reference_map():
    package, disclosures = complete_evidence()
    state = {"company_of_interest": "DOCN", "trade_date": "2026-10-19",
             "fundamentals_report": "Research text"}
    result = assess_financial_package(state, package, disclosures)
    refs = result["prompt_evidence_references"]
    assert refs
    assert all(alias[0] in "FSDK" and alias[1:].isdigit() for alias in refs.values())
    assert all(exact in result["canonical_financial_context"] for exact in refs)
    assert len(set(refs.values())) == len(refs)


def test_supplement_aliases_only_retained_exact_identifiers():
    canonical = ("- [F1] Revenue: 10 USD; sources S1" + REFERENCE_START
                 + "- F1: fact_id fact-original\n- S1: source_id source-original; U1; locator"
                 + REFERENCE_END)
    brief = "\n".join([
        json.dumps({"fact_id": "fact-new", "source_ids": ["source-new"]}),
        json.dumps({"fact_id": "untrusted-fact", "source_ids": ["untrusted-source"]}),
    ])
    refs = prompt_reference_map(canonical, brief, fact_ids={"fact-new"}, source_ids={"source-new"})
    assert refs == {"fact-original": "F1", "source-original": "S1",
                    "fact-new": "F2", "source-new": "S2"}


def test_already_short_ids_do_not_rewrite_ordinary_source_prose():
    from tradingagents.agents.evidence_presentation import prompt_id_view

    text = "Management's guidance remains conditional. Source s is already short."
    assert prompt_id_view(text, {'s': 'S1'}) == text


def test_postgate_prompt_shortens_only_proven_duplicate_facts():
    represented = "a" * 64
    source_only = "b" * 64
    source = "sec-document-" + "c" * 64
    fact = {"fact_id": represented, "metric": "Revenue", "value": "10", "source_ids": [source]}
    extra = {"fact_id": source_only, "metric": "Revenue", "value": "11", "source_ids": [source]}
    shared = "\n".join([
        "Shared primary-source brief", json.dumps(fact), json.dumps(extra),
        "- Instrument terms (source-bound): convertible note; principal 1 USD.",
        "Financing authorization: at-the-market program up to 100 USD; source_id " + source,
        "RPO prior-year observation: 55 USD; source_id " + source,
        "Finance lease and equipment maturities: 2027 $250.0M.",
        "Canonical completed price: 20 USD; source_id " + source,
    ])
    canonical = ("Accepted evidence brief\n- [F1] Revenue: 10 USD; sources S1\n"
                 "- Instrument terms (source-bound): convertible note; principal 1 USD.\n"
                 "Finance lease and equipment maturities: 2027 $250.0M."
                 + REFERENCE_START + "### Evidence reference appendix\n"
                 + f"- F1: fact_id {represented}\n- S1: source_id {source}; U1; locator"
                 + REFERENCE_END)
    state = {"company_of_interest": "DOCN", "instrument_context": "Issuer DOCN",
             "shared_source_brief": shared, "canonical_financial_context": canonical,
             "evidence_quality": {"status": "limited"},
             "prompt_evidence_references": {represented: "F1", source: "S1", source_only: "F2"}}
    before = dict(state)
    prompt = get_instrument_context_from_state(state)
    assert prompt.count("- [F1] Revenue") == 1
    assert represented not in prompt
    assert source_only not in prompt
    assert '"fact_id": "F2"' in prompt and '"value": "11"' in prompt
    assert prompt.count("- Instrument terms (source-bound)") == 1
    assert prompt.count("Finance lease and equipment maturities") == 1
    for item in ("Financing authorization", "RPO prior-year observation", "Canonical completed price"):
        assert item in prompt
    assert source not in prompt and "source_id S1" in prompt
    assert "Evidence reference appendix" not in prompt
    assert state == before
    pre_gate = get_instrument_context_from_state({**state, "evidence_quality": None})
    assert shared in pre_gate and canonical not in pre_gate
