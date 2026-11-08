from tests.test_document_search_state import state
from tradingagents.agents.document_access import render_document_searches, run_document_search
from tradingagents.reporting import evidence_appendix


def test_report_queries_counts_omissions_and_exact_no_match_label():
    s = state()
    for query, call_id in (("revenue", "one"), ("utilization", "two")):
        result = run_document_search(s, query, role="fundamentals", call_id=call_id)
        s["document_search_trace"].update(result["document_search_trace"])
    rendered = evidence_appendix(s)
    assert "Document searches" in rendered
    assert "fundamentals | revenue | ok | 1" in rendered
    assert "utilization | not_found | 0 | not found in retained filings" in rendered
    assert "not disclosed" not in rendered
    assert "Third Quarter 2026 revenue was" not in rendered


def test_legacy_and_unavailable_search_reporting():
    assert render_document_searches({}) == ""
    s = state()
    s["document_sources"].update(status="unavailable", corpus=None, corpus_hash=None,
                                 reason="SEC unavailable")
    text = render_document_searches(s)
    assert "SEC unavailable" in text and "No analyst document searches were run" in text


def test_citation_hidden_in_raw_diagnostics_is_not_claimed_as_published():
    from tradingagents.agents.document_questions import (
        lookup_document_questions,
        parse_document_questions,
    )
    from tradingagents.reporting import _report_parts

    s = state()
    s["investment_debate_state"] = {"document_questions": {
        "bull": parse_document_questions('\x60\x60\x60document_questions\n["revenue"]\n\x60\x60\x60', "bull")}}
    s.update(lookup_document_questions(s))
    ref = s["document_followups"]["results"][0]["passages"][0]["citation_ref"]
    s["final_trade_decision"] = "Hold. No cited source in this published decision."
    s["unvalidated_outputs"] = {"portfolio_manager": {"rationale": ref}}
    rendered = str(_report_parts(s))
    assert "final-decision citation not verified." in rendered
    assert "RM answer judgment unavailable" in rendered
    assert "cited in final decision:" not in rendered.lower()
    assert ref not in rendered
