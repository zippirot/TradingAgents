"""Bounded repairs preserve strict evidence validation and exact occurrence coverage."""
import json

import pytest

from tests.test_ground_truth_audit import inventory, state
from tradingagents.ground_truth import _validate_claim, corrected_parts, render_audit, run_audit


def payload(claims):
    return {"claims": claims, "no_material_claims": not claims}


def assertion(text, outcome="unsupported", **extra):
    return {"quoted_claim": text, "outcome": outcome, "explanation": "The source does not establish causation.", **extra}


class Scripted:
    def __init__(self, outputs):
        self.outputs, self.prompts = iter(outputs), []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return next(self.outputs)


def inv(text):
    return inventory(parts=[("Decision", "5_portfolio", [("PM", "decision.md", text)])])


def test_invalid_r8_citation_retargets_exact_quote_even_without_new_sources():
    text = "Revenue was 100 USD.\n\nRPO rose because the product launch accelerated demand."
    good = assertion("Revenue was 100 USD.", "supported", evidence=[
        {"source_id": "doc-1", "locator": "table-1", "quote": "Revenue was 100 USD."}])
    bad = assertion(text.split("\n\n")[1], evidence=[{"source_id": "doc-1", "locator": "invented", "quote": "RPO"}])
    reviewer = Scripted([payload([good, bad]), payload([assertion(bad["quoted_claim"])])])
    result = run_audit(state(), reviewer, inventory=inv(text))
    assert len(reviewer.prompts) == 2
    follow = json.loads(reviewer.prompts[1].split("REPORT CHUNK:\n")[1].split("\nSUPPLIED SOURCES")[0])
    assert follow["review_claims"] == [bad["quoted_claim"]]
    assert "locator" in follow["prior_assessments"][0]["explanation"]
    assert [c["outcome"] for c in result["claims"]] == ["supported", "unsupported"]
    assert result["coverage"]["reviewed_chunks"] == 1


@pytest.mark.parametrize("tail", ["Cash was 100 USD.", "| Cash | 100 USD |", "**Price Target**: not provided"])
def test_omitted_occurrence_or_last_field_is_repaired_without_erasing_valid_claims(tail):
    first = assertion("Revenue was 100 USD.", "supported", evidence=[
        {"source_id": "doc-1", "locator": "table-1", "quote": "Revenue was 100 USD."}])
    text = first["quoted_claim"] + "\n\n" + tail
    reviewer = Scripted([payload([first]), payload([assertion(tail)])])
    result = run_audit(state(), reviewer, inventory=inv(text))
    assert len(reviewer.prompts) == 2
    assert result["coverage"]["reviewed_chunks"] == 1
    assert len(result["claims"]) == 2
    assert result["claims"][1]["quoted_claim"] == tail


def test_failed_repair_keeps_invalid_citation_out_and_shared_budget_partial():
    text = "RPO rose because the product launch accelerated demand."
    bad = assertion(text, evidence=[{"source_id": "invented", "locator": "x", "quote": "RPO"}])
    for cap in (1, 2):
        reviewer = Scripted([payload([bad]), payload([bad])])
        result = run_audit(state(), reviewer, {"ground_truth_max_requests": cap}, inventory=inv(text))
        assert len(reviewer.prompts) == cap
        assert result["status"] == "partial"
        assert result["coverage"]["reviewed_chunks"] == 0
        assert result["claims"] == []
        assert any("repair" in limit.lower() for limit in result["limits"])


def test_compound_literal_is_retained_as_excerpt_without_whole_claim_correction_authority():
    quote = "Q4 and FY adjusted margin guidance is 41–43%."
    literal = "Adjusted margin of 41% to 42%."
    source = {"source_id": "issuer", "locator": "fy", "text": literal,
              "url": "https://www.sec.gov/Archives/edgar/data/1582961/example.htm", "known_at": "2026-11-03",
              "kind": "filing passage", "context": {"preceding_introductions": [{"text": "For the full year 2026:"}]}}
    chunk = {"chunk_id": "decision@0", "section_id": "5_portfolio/decision.md", "start": 0, "text": quote}
    raw = assertion(quote, "contradicted", correction=literal, decision_material=True,
                    evidence=[{"source_id": "issuer", "locator": "fy", "quote": literal}])
    claim = _validate_claim(raw, chunk, {("issuer", "fy"): source})
    assert claim["correction"] is None
    assert claim["supporting_source_excerpt"] == literal
    assert claim["correction_withheld"] is True
    assert "whole" in claim["correction_withheld_reason"]
    record = {"claims": [claim], "coverage": {}, "status": "partial"}
    assert literal in render_audit(record)
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", quote)])]
    annotated = corrected_parts(parts, record)[0][2][0][2]
    assert quote in annotated and literal in annotated and "full year 2026" in annotated


def test_complete_literal_prose_scope_preserves_source_based_correction_policy():
    text = "The completed close was 99 USD."
    literal = "The completed close was 101 USD."
    source = {"source_id": "price", "locator": "close", "text": literal, "url": "https://example.com",
              "known_at": "2026-11-03", "kind": "validated retained market observation"}
    raw = assertion(text, "contradicted", correction=literal, correction_scope="complete_claim",
                    decision_material=True, evidence=[{"source_id": "price", "locator": "close", "quote": literal}])
    claim = _validate_claim(raw, {"chunk_id": "x", "section_id": "x", "start": 0, "text": text},
                            {("price", "close"): source})
    assert claim["correction"] == literal
    assert not claim["correction_withheld"]
    assert not claim["code_verified"]  # Scope remains model assessed, not code truth.
    from tradingagents.ground_truth_flow import _material_correction
    assert _material_correction(claim)


def test_ambiguous_rejected_prose_quote_cannot_be_repaired_as_unique_location():
    text = "RPO rose because the launch accelerated demand."
    bad = assertion(text, evidence=[{"source_id": "invented", "locator": "x", "quote": "RPO"}])
    reviewer = Scripted([payload([bad])])
    result = run_audit(state(), reviewer, inventory=inv(text + "\n\n" + text))
    assert len(reviewer.prompts) == 1
    assert result["status"] == "partial" and not result["claims"]
    assert result["coverage"]["reviewed_chunks"] == 0


def test_fabricated_raw_quote_is_not_a_repair_target_or_accepted_finding():
    bad = assertion("Invented launch causality.", evidence=[])
    reviewer = Scripted([payload([bad])])
    result = run_audit(state(), reviewer, inventory=inv("The launch caused demand."))
    assert len(reviewer.prompts) == 1
    assert result["status"] == "partial" and not result["claims"]


def test_schema_three_record_cannot_reuse_weaker_correction_or_coverage_contract():
    from tradingagents.ground_truth import resolve_audit, seal_audit
    text = "Revenue was 100 USD."
    record = run_audit(state(), Scripted([payload([assertion(text)])]), inventory=inv(text))
    record["schema_version"] = 3
    seal_audit(record)
    assert resolve_audit(state(), record, inventory=inv(text))["status"] == "unavailable"
    reviewer = Scripted([payload([assertion(text)])])
    fresh = run_audit(state(), reviewer, inventory=inv(text), prior_audit=record)
    assert len(reviewer.prompts) == 1
    assert fresh["coverage"]["reused_chunk_ids"] == []


def test_failed_repair_retains_exact_unresolved_passage_in_bound_human_detail():
    text = "RPO rose because <script>launch</script> accelerated demand."
    bad = assertion(text, evidence=[{"source_id": "invented", "locator": "x", "quote": "RPO"}])
    result = run_audit(state(), Scripted([payload([bad]), payload([bad])]), inventory=inv(text))
    assert result["claims"] == []
    diagnostic = result["unresolved_repairs"][0]
    assert diagnostic["quoted_claim"] == text
    assert diagnostic["character_start"] == 0 and diagnostic["character_end"] == len(text)
    assert "source quote or locator" in diagnostic["reason"]
    detail = render_audit(result)
    assert "Unresolved citation or coverage repairs" in detail
    assert "not accepted factual verdicts" in detail
    assert "&lt;script&gt;" in detail and "<script>" not in detail


def test_repair_reuses_shared_token_allowance_without_invocation_when_exhausted():
    text = "Revenue was 100 USD."
    reviewer = Scripted([payload([])])
    result = run_audit(state(), reviewer, {"ground_truth_max_tokens": 1}, inventory=inv(text))
    assert not reviewer.prompts and result["usage"]["requests"] == 0
    assert result["status"] != "completed"


def test_same_line_repeated_amount_repairs_only_the_uncovered_sentence():
    first = assertion("Revenue was 100 USD.", "supported", evidence=[
        {"source_id": "doc-1", "locator": "table-1", "quote": "Revenue was 100 USD."}])
    tail = "Cash was 100 EUR for FY 2025."
    reviewer = Scripted([payload([first]), payload([assertion(tail)])])
    result = run_audit(state(), reviewer, inventory=inv(first["quoted_claim"] + " " + tail))
    follow = json.loads(reviewer.prompts[1].split("REPORT CHUNK:\n")[1].split("\nSUPPLIED SOURCES")[0])
    assert follow["review_claims"] == [tail]
    assert result["coverage"]["reviewed_chunks"] == 1
    assert result["claims"][1]["character_start"] == len(first["quoted_claim"]) + 1


def test_partial_declared_scope_blocks_pm_and_prompt_requires_whole_claim_scope():
    from tradingagents.ground_truth import _review_prompt
    from tradingagents.ground_truth_flow import _material_correction
    quote, literal = "Both periods had margin of 9%.", "Annual margin was 8%."
    source = {"source_id": "issuer", "locator": "annual", "text": literal,
              "url": "https://www.sec.gov/Archives/edgar/data/1582961/example.htm",
              "known_at": "2026-11-03", "kind": "filing passage"}
    chunk = {"chunk_id": "x", "section_id": "x", "start": 0, "text": quote}
    raw = assertion(quote, "contradicted", correction=literal, correction_scope="supporting_excerpt",
                    decision_material=True, evidence=[{"source_id": "issuer", "locator": "annual", "quote": literal}])
    result = _validate_claim(raw, chunk, {("issuer", "annual"): source})
    assert result["correction"] is None and not _material_correction(result)
    assert result["supporting_source_excerpt"] == literal
    prompt = _review_prompt(chunk, {})
    assert "ALL clauses, periods, units, definitions and qualifiers" in prompt
    assert "correction_scope" in prompt and "complete_claim" in prompt and "supporting_excerpt" in prompt


def test_failed_numeric_repair_does_not_falsely_cover_repeated_occurrences():
    text = "Revenue was 100 USD. Cash was 100 EUR."
    reviewer = Scripted([payload([assertion("Revenue was 100 USD.")]),
                         payload([assertion("Revenue was 100 USD.")])])
    result = run_audit(state(), reviewer, inventory=inv(text))
    assert len(result["claims"]) == 1
    assert result["coverage"]["reviewed_chunks"] == 0
    assert result["status"] == "partial"
    assert result["unresolved_repairs"][0]["quoted_claim"] == "Cash was 100 EUR."


def test_table_date_header_cannot_claim_source_support_without_a_citation():
    header = "| Perimeter (9/30/2026) | Net obligations | Source |"
    chunk = {"chunk_id": "table", "section_id": "decision", "start": 0, "text": header}
    with pytest.raises(ValueError, match="source-backed outcome needs evidence"):
        _validate_claim(assertion(header, "supported", evidence=[]), chunk, {})
    declared_scope = _validate_claim(assertion(
        header, "hypothesis", evidence=[],
        explanation="Declared table scope only; dated source inputs are needed to verify its rows."), chunk, {})
    assert declared_scope["outcome"] == "hypothesis"
    assert not declared_scope["code_verified"]
    assert declared_scope["verification"]["source_quotes_validated"] is False
