"""Follow-up judgments stay raw until the report is exported as HTML."""

from copy import deepcopy

from tests.test_na_followup_judgments import state_and_payload
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.report_html import render_report
from tradingagents.report_summary import build_summary_input
from tradingagents.reporting import report_sections, summary_input_for_report


def test_followup_judgment_reaches_summary_unescaped_and_html_as_text():
    state, payload = state_and_payload()
    explanation = "Revenue <script>alert(1)</script> & costs < 5; **uncertain**."
    payload["followup_judgments"][0]["explanation"] = explanation
    state["document_followup_judgments"] = payload["followup_judgments"]
    state["final_trade_decision"] = "Rating: Hold. Decision remains conditional."

    portfolio = next(part for part in report_sections(state) if part[1] == "5_portfolio")
    decision_text = next(text for _agent, name, text in portfolio[2] if name == "decision.md")
    assert explanation in decision_text
    assert "RM answer judgment (unvalidated): unanswered" in decision_text
    assert "Retrieval: relevant_passages_found" in decision_text

    summary = summary_input_for_report(state)
    portfolio_source = next(section["text"] for section in summary["sections"]
                            if section["key"] == "5_portfolio")
    assert explanation in portfolio_source
    assert "&lt;script&gt;" not in portfolio_source

    page = render_report("DOCN", state, None, None)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&amp; costs &lt; 5" in page
    assert "&amp;lt;script&amp;gt;" not in page


def test_summary_decodes_only_generated_pm_display_entities():
    state, payload = state_and_payload()
    state.update(evidence_quality={"status": "limited", "checks": [], "warnings": []},
                 final_rating="Hold", final_trade_decision="Raw decision")
    state["unvalidated_outputs"] = {"portfolio_manager": {"structured": {
        "executive_summary": "PP&E; literal &amp; and &lt;source&gt;.",
        "investment_thesis": "Cost < revenue; **conditional**.",
    }}}
    payload["followup_judgments"][0]["explanation"] = "Source says &lt;source&gt; literally."
    state["document_followup_judgments"] = payload["followup_judgments"]
    published = {**state, **enforce_publication(state)}
    parts = report_sections(published)
    original_state, original_parts = deepcopy(published), deepcopy(parts)

    raw_summary = build_summary_input(published, None, parts)
    summary = summary_input_for_report(published, parts=parts)
    source = next(section["text"] for section in summary["sections"]
                  if section["key"] == "5_portfolio")
    assert "PP&E; literal &amp; and &lt;source&gt;." in source
    assert "Cost < revenue; \\*\\*conditional\\*\\*." in source
    assert "Source says &lt;source&gt; literally." in source
    assert "PP&amp;E" not in source
    assert summary["source_input_digest"] == raw_summary["source_input_digest"]  # nothing left to decode
    assert published == original_state and parts == original_parts

    page = render_report("DOCN", published, None, parts)
    assert "PP&amp;E" in page
    assert "&lt;source&gt;" in page
    assert "<source>" not in page
