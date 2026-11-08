"""Acceptance regressions identified during frozen-provider proof review."""
import json

import pytest
from langchain_core.messages import AIMessage

from tests.test_ground_truth_audit import Model, inventory, response, state
from tradingagents.ground_truth import _payload, _validate_claim, build_inventory, run_audit


@pytest.mark.parametrize("amount", ["$321M", "$1.2B", "50.25%"])
def test_omitted_financial_amounts_never_clear_review(amount):
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", f"Revenue was {amount}.")])]
    result = run_audit(state(), Model({"claims": [], "no_material_claims": True}),
                       inventory=inventory(parts=parts))
    assert result["status"] in {"partial", "unavailable"}
    assert result["coverage"]["reviewed_chunks"] == 0


def test_validated_source_table_context_survives_into_pm_evidence():
    chunk = {"chunk_id": "decision@0:20", "section_id": "decision", "start": 0,
             "text": "Revenue was 321 thousand USD."}
    source = {"source_id": "doc-1", "locator": "table-1", "text": "| Revenue | 321 | 200 |",
              "url": "https://www.sec.gov/Archives/edgar/data/1582961/example.htm",
              "known_at": "2026-11-03", "kind": "filing passage",
              "context": {"table_headers": ["Metric (USD thousands) | 2026 | 2025"]}}
    claim = {"quoted_claim": chunk["text"], "outcome": "supported", "explanation": "Source row.",
             "evidence": [{"source_id": "doc-1", "locator": "table-1", "quote": source["text"],
                           "context": {"table_headers": ["Invented EUR basis"]}}]}
    result = _validate_claim(claim, chunk, {("doc-1", "table-1"): source})
    assert result["evidence"][0]["context"] == source["context"]


def test_language_choice_is_bound_to_audit_identity_and_review_instructions():
    original = state()
    spanish = {**original, "run_settings": {"output_language": "Spanish"}}
    french = {**original, "run_settings": {"output_language": "French"}}
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "Revenue was 100 USD.")])]
    es = build_inventory(spanish, parts=parts, summary_text="")
    fr = build_inventory(french, parts=parts, summary_text="")
    assert es["digest"] != fr["digest"]
    model = Model(response())
    run_audit(spanish, model, inventory=es)
    assert "Spanish" in model.calls[0]


def test_text_block_model_response_parses_without_exposing_thinking():
    payload = {"claims": [], "no_material_claims": True}
    message = AIMessage(content=[{"type": "thinking", "thinking": "private reasoning"},
                                 {"type": "text", "text": json.dumps(payload)}])
    assert _payload(message) == payload


@pytest.mark.parametrize("text,expected", [
    ("Revenue was $321M.", "321M"),
    ("Revenue was $1.2B.", "1.2B"),
    ("Revenue was $1,234.50M.", "1,234.50M"),
    ("Margin was 50.25%.", "50.25%"),
])
def test_financial_tokens_keep_complete_decimal_magnitude_and_percent(text, expected):
    from tradingagents.ground_truth import _NUMBER

    tokens = _NUMBER.findall(text)
    assert len(tokens) == 1
    assert expected in tokens[0]


def test_number_tokens_do_not_swallow_following_comma_punctuation():
    from tradingagents.ground_truth import _NUMBER

    assert _NUMBER.findall("Three values were 3, 4, and 1,234.50.") == ["3", "4", "1,234.50"]


def qualified_claim(source):
    """A source already accepted into the engine index, with model spoof data."""
    chunk = {"chunk_id": "decision@0:29", "section_id": "decision", "start": 0,
             "text": "Revenue was 321 thousand USD."}
    model_reference = {"source_id": source["source_id"], "locator": source["locator"],
                       "quote": source["text"],
                       "context": {"table_headers": ["Invented EUR basis"],
                                   "fact": {"unit": "EUR", "basis": "Invented basis"}},
                       "source_character_start": 999999}
    claim = {"quoted_claim": chunk["text"], "outcome": "supported", "explanation": "Source evidence.",
             "evidence": [model_reference]}
    return _validate_claim(claim, chunk, {(source["source_id"], source["locator"]): source})


def indexed_source():
    return {"source_id": "doc-1", "locator": "table-1/chars-50-75",
            "text": "| Revenue | 321 | 200 |",
            "url": "https://www.sec.gov/Archives/edgar/data/1582961/example.htm",
            "known_at": "2026-11-03", "kind": "filing passage",
            "original_locator": "table-1", "source_character_start": 50, "source_character_end": 75,
            "context": {"table_headers": ["Metric (USD thousands) | 2026 | 2025"],
                        "source_section": "Quarterly results"}}


def test_trusted_table_context_and_original_spans_are_deep_copied_without_model_overrides():
    source = indexed_source()
    result = qualified_claim(source)
    evidence = result["evidence"][0]
    assert evidence["context"]["table_headers"] == source["context"]["table_headers"]
    assert evidence["context"] is not source["context"]
    assert evidence["context"]["table_headers"] is not source["context"]["table_headers"]
    assert evidence["original_locator"] == "table-1"
    assert (evidence["source_character_start"], evidence["source_character_end"]) == (50, 75)
    assert "Invented EUR" not in json.dumps(evidence)
    source["context"]["table_headers"][0] = "Mutated after validation"
    assert "USD thousands" in evidence["context"]["table_headers"][0]


def test_financial_fact_scope_survives_with_original_accounting_definition():
    source = indexed_source()
    source["kind"] = "canonical financial fields"
    source["fact"] = {"metric": "Revenue", "value": "321000", "unit": "USD",
                      "period_start": "2026-07-01", "period_end": "2026-09-30", "basis": "US-GAAP"}
    result = qualified_claim(source)
    fact = result["evidence"][0]["context"]["fact"]
    for key in ("metric", "value", "unit", "period_start", "period_end", "basis"):
        assert fact[key] == source["fact"][key]
    assert fact is not source["fact"]
    assert fact["unit"] == "USD" and fact["basis"] == "US-GAAP"


def test_reproduced_calculation_retains_definition_and_scoped_inputs():
    source = indexed_source()
    source["kind"] = "reproduced financial calculation"
    source["calculation"] = {
        "method": "borrowings_less_cash_v1", "status": "pass", "result": "321000", "unit": "USD",
        "message": "Total borrowings less cash, with lease liabilities outside this perimeter.",
        "input_fact_ids": ["borrowings", "cash"],
    }
    source["inputs"] = [
        {"fact_id": "borrowings", "metric": "Total Borrowings", "value": "521000", "unit": "USD",
         "period_start": None, "period_end": "2026-09-30", "basis": "US-GAAP"},
        {"fact_id": "cash", "metric": "Cash and Equivalents", "value": "200000", "unit": "USD",
         "period_start": None, "period_end": "2026-09-30", "basis": "US-GAAP"},
    ]
    result = qualified_claim(source)
    context = result["evidence"][0]["context"]
    for key in ("method", "result", "unit", "message", "input_fact_ids"):
        assert context["calculation"][key] == source["calculation"][key]
    assert context["inputs"][0]["metric"] == "Total Borrowings"
    assert context["inputs"][1]["value"] == "200000"
    assert context["inputs"] is not source["inputs"]
    assert context["inputs"][0] is not source["inputs"][0]
    source["calculation"]["message"] = "Changed perimeter"
    source["inputs"][0]["unit"] = "EUR"
    assert "lease liabilities outside" in context["calculation"]["message"]
    assert context["inputs"][0]["unit"] == "USD"


def test_source_detail_includes_units_periods_provenance_and_escapes_source_markup():
    from tradingagents.ground_truth import render_audit

    source = indexed_source()
    source["context"]["source_section"] = '<img src="x" onerror="alert(1)">'
    claim = qualified_claim(source)
    text = render_audit({"status": "completed", "coverage": {"total_chunks": 1, "reviewed_chunks": 1},
                         "claims": [claim]})
    assert "USD thousands" in text and "2026" in text and "2025" in text
    assert "2026-11-03" in text and "filing passage" in text
    assert "table-1" in text and "50" in text and "75" in text
    assert "<img" not in text
    assert "&lt;img" in text


def test_language_change_prevents_incremental_reuse_of_the_old_explanation():
    from tradingagents.ground_truth import _review_prompt

    base = state()
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "Revenue was 100 USD.")])]
    spanish = {**base, "run_settings": {"output_language": "Spanish"}}
    french = {**base, "run_settings": {"output_language": "French"}}
    es = build_inventory(spanish, parts=parts, summary_text="")
    first = run_audit(spanish, Model({"claims": response()["claims"][:1], "no_material_claims": False}), inventory=es)
    fr = build_inventory(french, parts=parts, summary_text="")
    changed = run_audit(french, Model(response()), {"ground_truth_max_requests": 0}, inventory=fr, prior_audit=first)
    assert not changed["coverage"]["reused_chunk_ids"]
    assert not changed["claims"]
    instruction = _review_prompt(es["chunks"][0], {})
    assert "Spanish" in instruction
    assert "quot" in instruction.lower() and "original" in instruction.lower()


def test_only_generated_archive_memory_count_is_excluded_from_number_completeness():
    from tradingagents.ground_truth import _coverage_text

    report = ("# Trading Analysis Report: DOCN\n\n"
              "- Memory log: 5 past decision(s) could not be settled this run and stay pending.\n"
              "- Vendor target: Revenue was $321M.\n\n"
              "## Research\n- Memory log: Revenue was $9M.\n")
    covered_text = _coverage_text(report)
    assert "5 past decision(s)" not in covered_text
    assert "- Vendor target: Revenue was $321M." in covered_text
    assert covered_text.endswith("## Research\n- Memory log: Revenue was $9M.\n")
    assert "5 past decision(s)" in report


@pytest.mark.parametrize("second", [
    "Cash was 100 USD.",
    "Cash was 100 EUR.",
    "Cash was 100 USD in Q2 2026.",
])
def test_repeated_numeric_value_does_not_clear_an_unreviewed_claim_occurrence(second):
    original = state()
    first = "Revenue was 100 USD in Q1 2026."
    text = first + " " + second
    original["filing_evidence"]["documents"][0]["blocks"][0]["text"] = text
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", text)])]
    model = Model({"claims": [{"quoted_claim": first, "outcome": "supported", "explanation": "Exact source statement.",
                              "evidence": [{"source_id": "doc-1", "locator": "table-1", "quote": first}]}],
                   "no_material_claims": False})
    result = run_audit(original, model, inventory=inventory(original, parts))
    assert len(result["claims"]) == 1
    assert result["status"] == "partial"
    assert result["coverage"]["reviewed_chunks"] == 0


def test_ambiguous_bare_amount_cannot_clear_two_separate_numeric_occurrences():
    text = "Revenue was 100 USD. Cash was 100 USD."
    original = state()
    original["filing_evidence"]["documents"][0]["blocks"][0]["text"] = text
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", text)])]
    result = run_audit(original, Model({"claims": [{"quoted_claim": "100 USD", "outcome": "supported",
        "explanation": "Amount occurs in source.", "evidence": [{"source_id": "doc-1", "locator": "table-1", "quote": "100 USD"}]}],
        "no_material_claims": False}), inventory=inventory(original, parts))
    assert result["claims"][0]["ambiguous_location"] is True
    assert result["status"] == "partial"
    assert result["coverage"]["reviewed_chunks"] == 0


def test_numeric_coverage_preserves_offsets_through_metadata_and_ordinal_masks():
    from tradingagents.ground_truth import _coverage_text

    original = state()
    statement = "Revenue was 100 USD."
    text = ("# Trading Analysis Report: DOCN\n\n"
            "- Memory log: 5 past decision(s) stay pending.\n\n"
            "## 1. Results\n\n" + statement)
    masked = _coverage_text(text)
    assert len(masked) == len(text)
    assert masked.index(statement) == text.index(statement)
    parts = [("Archived report", "archive", [("Complete", "complete_report.md", text)])]
    result = run_audit(original, Model({"claims": [{"quoted_claim": statement, "outcome": "supported",
        "explanation": "Exact source statement.", "evidence": [{"source_id": "doc-1", "locator": "table-1", "quote": statement}]}],
        "no_material_claims": False}), inventory=inventory(original, parts))
    assert result["status"] == "completed"
    assert result["coverage"]["reviewed_chunks"] == 1


def test_supported_outcome_instruction_covers_the_entire_mixed_assertion():
    from tradingagents.ground_truth import _review_prompt

    chunk = {"chunk_id": "decision@0:54", "section_id": "decision", "start": 0,
             "text": "Profit was 12 million before the existing expense.", "output_language": "English"}
    prompt = _review_prompt(chunk, {}).casefold()
    assert "entire asserted claim" in prompt
    assert "matching figures alone" in prompt
    assert "implication" in prompt and "unsupported or contradicted" in prompt
    assert "exact quoted subclaims" in prompt
    assert "outcome must agree with the explanation" in prompt


def legacy_signed_audit():
    from tradingagents.ground_truth import seal_audit

    inv = inventory()
    record = run_audit(state(), Model(response()), inventory=inv)
    return inv, seal_audit({**record, "schema_version": 2})


def test_weaker_signed_schema2_record_is_unavailable_without_new_inference():
    from tradingagents.ground_truth import resolve_audit

    inv, legacy = legacy_signed_audit()
    resolved = resolve_audit(state(), legacy, inventory=inv)
    assert resolved["status"] == "unavailable"
    assert not resolved["claims"]


def test_weaker_schema2_prior_cannot_supply_current_review_coverage():
    inv, legacy = legacy_signed_audit()
    model = Model(response())
    result = run_audit(state(), model, {"ground_truth_max_requests": 0}, inventory=inv, prior_audit=legacy)
    assert not model.calls
    assert not result["coverage"]["reused_chunk_ids"]
    assert result["coverage"]["reviewed_chunks"] == 0
    assert not result["claims"]


def test_source_followup_retains_the_original_unresolved_semantic_reason(monkeypatch):
    import tradingagents.ground_truth as engine

    original = state()
    original["filing_evidence"]["documents"][0]["blocks"] = [
        {"locator": "a-amount", "text": "Profit was 12 USD."},
        {"locator": "z-expense", "text": "Profit of 12 USD already reflects the expense."}]
    statement = "Profit was 12 USD before expense."
    reason = "The amount matches, but the statement ignores an expense already recorded in that profit."
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", statement)])]
    # A broad first-pass packet can omit the newly relevant definition even
    # when the focused packet has room to retain both old and new evidence.
    real_select = engine._select_sources
    first_selection = []
    def narrow_first(query, sources, cap):
        if not first_selection:
            first_selection.append(True)
            selected = {key: source for key, source in sources.items() if source["locator"] == "a-amount"}
            return selected, len(sources) - len(selected)
        return real_select(query, sources, cap)
    monkeypatch.setattr(engine, "_select_sources", narrow_first)
    cap = 24000
    class Reviewer:
        def __init__(self):
            self.calls = 0
            self.follow_inputs = []
        def invoke(self, prompt):
            self.calls += 1
            chunk = json.loads(prompt.split("REPORT CHUNK:\n")[1].split("\nSUPPLIED SOURCES")[0])
            if chunk.get("review_claims"):
                self.follow_inputs.append((chunk, prompt))
            return {"claims": [{"quoted_claim": statement, "outcome": "unsupported",
                                "explanation": reason, "evidence": []}], "no_material_claims": False}
    reviewer = Reviewer()
    result = run_audit(original, reviewer, {"ground_truth_max_source_characters": cap}, inventory=inventory(original, parts))
    assert reviewer.calls == 2
    follow_chunk, follow_prompt = reviewer.follow_inputs[0]
    assert follow_chunk["review_claims"] == [statement]
    assert follow_chunk.get("prior_assessments") == [{"quoted_claim": statement,
                                                    "outcome": "unsupported", "explanation": reason}]
    assert "Resolve that original concern" in follow_prompt
    assert "matching number alone cannot resolve" in follow_prompt
    assert result["claims"][0]["outcome"] == "unsupported"
    assert result["claims"][0]["explanation"] == reason


def test_explicit_valuation_reference_question_preserves_basis_and_median_amid_filings():
    from tradingagents.ground_truth import _select_sources

    source_map = {}
    for i in range(20):
        source_map[(f"filing-{i}", "body")] = {
            "source_id": f"filing-{i}", "locator": "body", "kind": "filing passage",
            "text": "Revenue history in annual filings. " * 4,
        }
    source_map[("history-basis", "basis")] = {
        "source_id": "history-basis", "locator": "basis", "kind": "reproduced valuation reference",
        "text": "Observed own-history reference basis is equity value divided by trailing revenue. Enterprise value / revenue has a different denominator and obligation perimeter.",
    }
    source_map[("history-median", "median")] = {
        "source_id": "history-median", "locator": "median", "kind": "reproduced valuation reference",
        "text": "Own eight-quarter median is 4.47 equity value / TTM revenue. This reference does not select an enterprise value valuation multiple.",
    }
    source_map[("revenue-fact", "Revenue")] = {
        "source_id": "revenue-fact", "locator": "Revenue", "kind": "canonical financial fields",
        "fact": {"metric": "Revenue", "value": "321192000", "unit": "USD"},
        "text": "Revenue 321192000 USD for the stated quarter.",
    }
    source_map[("completed-close", "close")] = {
        "source_id": "completed-close", "locator": "close", "kind": "validated retained market observation",
        "text": "Completed close 70.70 USD on 2026-11-05.",
    }
    query = "Own eight-quarter median 4.47: equity versus EV / trailing revenue basis. Revenue was 321M and the completed close was 70.70."
    selected, omitted = _select_sources(query, source_map, 1500)
    assert ("history-basis", "basis") in selected
    assert ("history-median", "median") in selected
    assert ("revenue-fact", "Revenue") in selected
    assert ("completed-close", "close") in selected
    assert omitted > 0
    assert all("fact" not in source for source in selected.values()
               if source["kind"] == "reproduced valuation reference")


def test_audit_detail_prioritizes_and_labels_material_findings_without_losing_others():
    from tradingagents.ground_truth import render_audit

    claims = [
        {"chunk_id": "decision@0:20", "quoted_claim": "Early small discrepancy.", "outcome": "contradicted",
         "decision_material": False, "explanation": "Nonmaterial issue.", "evidence": []},
        {"chunk_id": "decision@20:40", "quoted_claim": "Supported reference.", "outcome": "supported",
         "decision_material": False, "explanation": "Known reference.", "evidence": []},
        {"chunk_id": "decision@40:60", "quoted_claim": "Late material limitation.", "outcome": "unsupported",
         "decision_material": True, "explanation": "Could change the recommendation.", "evidence": []},
    ]
    text = render_audit({"status": "completed with findings", "claims": claims,
                         "coverage": {"total_chunks": 3, "reviewed_chunks": 3}})
    assert text.index("Late material limitation.") < text.index("Early small discrepancy.") < text.index("Supported reference.")
    material_line = next(line for line in text.splitlines() if "Late material limitation." in line)
    assert "material" in material_line.casefold() and "recommendation" in material_line.casefold()
    assert all(text.count(claim["quoted_claim"]) == 1 for claim in claims)
    assert all(claim["chunk_id"] in text for claim in claims)


def indexed_cash_flow_arithmetic():
    from copy import deepcopy

    from tests.test_ground_truth_audit import financial_state
    from tradingagents.ground_truth import _source_index

    s = financial_state()
    prototype = s["financial_evidence"]["facts"][0]
    facts = []
    for ident, metric, value in (("operating", "Operating Cash Flow", "100"),
                                 ("investing", "Investing Cash Flow", "10")):
        fact = deepcopy(prototype)
        fact.update(fact_id=ident, metric=metric, value=value, locator=metric)
        facts.append(fact)
    s["financial_evidence"]["facts"] = facts
    sources, _ = _source_index(s)
    evidence = [{"source_id": ident, "locator": sources[(ident, metric)]["locator"],
                 "quote": sources[(ident, metric)]["text"]}
                for ident, metric in (("operating", "Operating Cash Flow"), ("investing", "Investing Cash Flow"))]
    calculation = {"operation": "sum", "fact_ids": ["operating", "investing"], "value": "110",
                   "decimal_places": 0, "scope": "Invented EUR financial meaning"}
    return sources, evidence, calculation


@pytest.mark.parametrize("replacement", [
    "Net income was 110 USD.",
    "Cash flows were 110 USD because utilization collapsed.",
    "Buy the stock because the computed amount is 110 USD.",
])
def test_arithmetic_result_cannot_authorize_unrelated_prose_replacements(replacement):
    sources, evidence, calculation = indexed_cash_flow_arithmetic()
    statement = "The sum of operating and investing cash flows was 100 USD."
    chunk = {"chunk_id": "decision@0:64", "section_id": "decision", "start": 0, "text": statement}
    raw = {"quoted_claim": statement, "outcome": "contradicted", "explanation": "The computed sum is different.",
           "correction": replacement, "decision_material": True,
           "evidence": evidence, "calculation": calculation}
    claim = _validate_claim(raw, chunk, sources)
    assert claim["outcome"] == "contradicted"
    assert claim["quoted_claim"] == statement
    assert claim["verification"]["arithmetic_reproduced"] is True
    assert claim["correction"] is None
    assert claim["correction_withheld"] is True
    assert claim["code_verified"] is False
    assert "wording" in claim["correction_withheld_reason"].casefold()


def test_supported_scoped_calculation_keeps_reproduced_math_and_trusted_operand_definitions():
    from tradingagents.ground_truth import render_audit

    sources, evidence, calculation = indexed_cash_flow_arithmetic()
    statement = "The sum of operating and investing cash flows was 110 USD."
    chunk = {"chunk_id": "decision@0:64", "section_id": "decision", "start": 0, "text": statement}
    raw = {"quoted_claim": statement, "outcome": "supported", "explanation": "The stated sum reproduces.",
           "evidence": evidence, "calculation": calculation}
    claim = _validate_claim(raw, chunk, sources)
    assert claim["verification"]["arithmetic_reproduced"] is True
    proof = claim["verification"]["arithmetic_proof"]
    assert proof["operation"] == "sum" and proof["result"] == "110"
    assert proof["unit"] == "USD"
    assert [operand["fact_id"] for operand in proof["operands"]] == ["operating", "investing"]
    assert all(operand["period_end"] == "2026-09-30" and operand["basis"] == "US-GAAP" for operand in proof["operands"])
    assert "Invented EUR" not in json.dumps(proof)
    assert claim["code_verified"] is False
    text = render_audit({"status": "completed", "coverage": {}, "claims": [claim]})
    assert "Operating Cash Flow" in text and "Investing Cash Flow" in text
    assert "110" in text and "USD" in text


def test_withheld_arithmetic_prose_is_visible_without_showing_the_unsafe_recommendation():
    from tradingagents.ground_truth import render_audit

    sources, evidence, calculation = indexed_cash_flow_arithmetic()
    statement = "The sum of operating and investing cash flows was 100 USD."
    raw = {"quoted_claim": statement, "outcome": "contradicted", "explanation": "The sum differs.",
           "correction": "Buy the stock because the total is 110 USD.", "evidence": evidence,
           "calculation": calculation}
    claim = _validate_claim(raw, {"chunk_id": "decision@0:64", "section_id": "decision", "start": 0, "text": statement}, sources)
    text = render_audit({"status": "completed with findings", "coverage": {}, "claims": [claim]})
    assert statement in text
    assert "withheld" in text.casefold() and "wording" in text.casefold()
    assert "Buy the stock" not in text


def test_brief_context_cannot_establish_an_ordinary_financial_fact():
    source = {"source_id": "brief", "locator": "full", "text": "Revenue was 100 USD.",
              "url": "", "known_at": "2026-11-06", "kind": "retained report context; no financial authority"}
    claim = {"quoted_claim": "Revenue was 100 USD.", "outcome": "supported", "explanation": "Brief repeats figure.",
             "evidence": [{"source_id": "brief", "locator": "full", "quote": source["text"]}]}
    chunk = {"chunk_id": "decision@0:20", "section_id": "decision", "start": 0, "text": claim["quoted_claim"]}
    with pytest.raises(ValueError, match="brief"):
        _validate_claim(claim, chunk, {("brief", "full"): source})


def test_brief_context_can_support_only_its_exact_report_content_scope():
    source = {"source_id": "brief", "locator": "full", "text": "Revenue was 100 USD.",
              "url": "", "known_at": "2026-11-06", "kind": "retained report context; no financial authority"}
    text = "The retained brief states revenue was 100 USD."
    claim = {"quoted_claim": text, "outcome": "supported", "explanation": "Only the brief's wording is established.",
             "evidence": [{"source_id": "brief", "locator": "full", "quote": source["text"]}]}
    result = _validate_claim(claim, {"chunk_id": "decision@0:45", "section_id": "decision", "start": 0, "text": text},
                             {("brief", "full"): source})
    assert result["outcome"] == "supported"
    assert result["code_verified"] is False
    assert result["evidence"][0]["kind"].startswith("retained report context")


def test_followup_retains_relevant_prior_premises_with_new_evidence_under_same_packet_cap(monkeypatch):
    import tradingagents.ground_truth as engine

    original = state()
    original["filing_evidence"]["documents"][0]["blocks"] = [
        {"locator": "a-gaap", "text": "Reported loss of 42.6 million USD already includes compensation expense."},
        {"locator": "z-compensation", "text": "Compensation expense was 36 million USD."}]
    text = "That profit is before treating 36 million USD compensation expense."
    reason = "The reported loss already includes compensation expense; finding its amount does not remove that definition issue."
    real_select = engine._select_sources
    selections = []
    def limited_first(query, sources, cap):
        if not selections:
            packet = {key: value for key, value in sources.items() if value["locator"] == "a-gaap"}
            selections.append(packet)
            return packet, len(sources) - len(packet)
        packet, omitted = real_select(query, sources, cap)
        selections.append(packet)
        return packet, omitted
    monkeypatch.setattr(engine, "_select_sources", limited_first)
    class Reviewer:
        def __init__(self):
            self.packets = []
        def invoke(self, prompt):
            packet = json.loads(prompt.split("SUPPLIED SOURCES (selection may be incomplete):\n")[1])
            self.packets.append(packet)
            return {"claims": [{"quoted_claim": text, "outcome": "unsupported", "explanation": reason, "evidence": []}],
                    "no_material_claims": False}
    reviewer = Reviewer()
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", text)])]
    result = run_audit(original, reviewer, {"ground_truth_max_source_characters": 24000}, inventory=inventory(original, parts))
    assert len(reviewer.packets) == 2
    assert {source["locator"] for source in reviewer.packets[1]} == {"a-gaap", "z-compensation"}
    assert sum(len(engine._json(source)) for source in reviewer.packets[1]) <= 24000
    assert result["claims"][0]["outcome"] == "unsupported"


def test_followup_does_not_pay_to_repeat_the_same_source_packet():
    original = state()
    original["shared_source_brief"] = "Revenue 99 USD was discussed in the supplied brief."
    text = "Revenue was 99 USD."
    model = Model({"claims": [{"quoted_claim": text, "outcome": "unsupported",
                               "explanation": "The supplied brief alone cannot establish the figure.", "evidence": []}],
                   "no_material_claims": False})
    result = run_audit(original, model, inventory=inventory(original, [
        ("Decision", "5_portfolio", [("PM", "decision.md", text)])]))
    assert len(model.calls) == 1
    assert result["usage"]["requests"] == 1
    assert result["claims"][0]["outcome"] == "unsupported"
    assert result["status"] == "completed with findings"
    assert not any("follow-up was incomplete" in limit for limit in result["limits"])


def test_followup_discloses_new_source_cannot_fit_alongside_retained_brief_context():
    from tradingagents.ground_truth import _json, _source_index

    original = state()
    original["shared_source_brief"] = "The retained brief discusses revenue and cash figures. " * 250
    sources, _ = _source_index(original)
    context = next(source for source in sources.values() if source["kind"].startswith("retained report context"))
    cap = len(_json(context)) + 1
    statement = "No obligations fact is in the retained brief."
    model = Model({"claims": [{"quoted_claim": statement, "outcome": "unsupported",
                               "explanation": "Revenue and cash alone leave the obligation question unresolved.", "evidence": []}],
                   "no_material_claims": False})
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", statement)])]
    result = run_audit(original, model, {"ground_truth_max_source_characters": cap}, inventory=inventory(original, parts))
    assert len(model.calls) == 1
    assert result["status"] == "partial"
    assert any("follow-up source allowance" in limit for limit in result["limits"])
    assert result["claims"][0]["outcome"] == "unsupported"


def test_reference_provenance_does_not_promote_every_history_row_above_primary_premises():
    from tradingagents.ground_truth import _select_sources

    prefix = ("Ticker DOCN; analysis date 2026-11-06. Reproduced valuation reference; "
              "equity value / trailing revenue, retrospective filings known by the analysis cutoff; "
              "not forward EV/revenue. ")
    sources = {}
    for index in range(43):
        key = (f"reference-{index}", "row")
        sources[key] = {"source_id": key[0], "locator": key[1], "kind": "reproduced valuation reference",
                        "text": prefix + f"Quarter 2020-{index + 1}; unrelated historical observation. " * 2}
    sources[("reference-median", "row")] = {
        "source_id": "reference-median", "locator": "row", "kind": "reproduced valuation reference",
        "text": prefix + "Own history equity value / trailing revenue: median 4.47 across eight quarters."}
    sources[("issuer-income", "row")] = {
        "source_id": "issuer-income", "locator": "row", "kind": "filing passage",
        "text": "Adjusted operating income was $74 million for the quarter."}
    query = "Own median 4.47 versus enterprise value basis; adjusted operating income was $74 million."
    selected, _ = _select_sources(query, sources, 2400)
    assert ("reference-median", "row") in selected
    assert ("issuer-income", "row") in selected


def test_followup_packing_gives_each_exact_target_its_own_evidence_rank():
    import tradingagents.ground_truth as engine

    sources = {}
    for index in range(43):
        sources[(f"history-{index}", "row")] = {
            "source_id": f"history-{index}", "locator": "row", "kind": "reproduced valuation reference",
            "text": f"Own historical equity value / trailing revenue observation {index + 20}. " * 2}
    sources[("median", "row")] = {
        "source_id": "median", "locator": "row", "kind": "reproduced valuation reference",
        "text": "Own eight-quarter historical median 4.47 equity value / trailing revenue."}
    sources[("income", "row")] = {
        "source_id": "income", "locator": "row", "kind": "filing passage",
        "text": "Adjusted operating income was $74 million in the stated quarter."}
    assessments = [
        {"quoted_claim": "The own historical median is 4.47.", "explanation": "Compare equity and enterprise value basis."},
        {"quoted_claim": "Adjusted operating income was $74 million.", "explanation": "The issuer passage was absent."},
    ]
    selected, _ = engine._select_followup_sources(assessments, sources, 1800)
    assert ("median", "row") in selected
    assert ("income", "row") in selected
    assert sum(len(engine._json(source)) for source in selected.values()) <= 1800


def test_source_rows_retain_literal_introductory_period_without_inferred_scope():
    from tradingagents.ground_truth import _source_index

    original = state()
    original["filing_evidence"]["documents"][0]["blocks"] = [
        {"locator": "intro-q4", "text": "Providing guidance for the quarter ending December 31, 2026 as follows:"},
        {"locator": "shares", "text": "Weighted average shares of 128 to 129 million."},
        {"locator": "intro-year", "text": "For the full year 2026, we now expect:"},
        {"locator": "year-revenue", "text": "Total revenue of $1.208 to $1.211 billion."},
    ]
    sources, _ = _source_index(original)
    row = next(source for source in sources.values() if source["locator"] == "year-revenue")
    context = row["context"]["preceding_introductions"]
    assert context[0] == {"locator": "intro-year", "text": "For the full year 2026, we now expect:"}
    assert all("period_start" not in passage and "period_end" not in passage for passage in context)
    claim = {"quoted_claim": "The annual guidance was $1.208 billion.", "outcome": "supported", "explanation": "Literal context.",
             "evidence": [{"source_id": row["source_id"], "locator": row["locator"], "quote": row["text"]}]}
    chunk = {"chunk_id": "x", "section_id": "x", "start": 0, "text": claim["quoted_claim"]}
    result = _validate_claim(claim, chunk, {(row["source_id"], row["locator"]): row})
    assert result["evidence"][0]["context"]["preceding_introductions"] == context


@pytest.mark.parametrize("field", [
    "Price Target: not provided.",
    "**Price Target**: not provided.",
    "**Price Target:** not provided.",
    "- **Final Rating**: REVIEW",
    "### Recommendation: Hold",
    "Position Sizing: no position.",
    "| Allocation | no change |",
])
def test_unreviewed_explicit_decision_field_in_last_paragraph_never_clears_coverage(field):
    text = "Revenue was 100 USD.\n\n" + field
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", text)])]
    output = {"claims": [response()["claims"][0]], "no_material_claims": False}
    result = run_audit(state(), Model(output), inventory=inventory(parts=parts))
    assert result["status"] == "partial"
    assert result["coverage"]["reviewed_chunks"] == 0
    assert result["claims"][0]["outcome"] == "supported"


@pytest.mark.parametrize("field,outcome", [
    ("**Price Target**: not provided.", "unsupported"),
    ("**Recommendation**: Hold", "hypothesis"),
    ("Position Sizing: no position.", "hypothesis"),
    ("**Final Rating**: REVIEW", "unsupported"),
])
def test_explicitly_reviewed_negative_or_hypothetical_fields_have_known_coverage(field, outcome):
    text = "Revenue was 100 USD.\n\n" + field
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", text)])]
    field_claim = {"quoted_claim": field, "outcome": outcome,
                   "explanation": "The explicit field is reviewed; underlying target or decision authority is unchanged.",
                   "evidence": []}
    output = {"claims": [response()["claims"][0], field_claim], "no_material_claims": False}
    result = run_audit(state(), Model(output), inventory=inventory(parts=parts))
    assert result["status"] == ("completed" if outcome == "hypothesis" else "completed with findings")
    assert result["coverage"]["reviewed_chunks"] == 1
    assert result["claims"][-1]["quoted_claim"] == field
    assert result["claims"][-1]["outcome"] == outcome
    assert result["claims"][-1]["correction"] is None


def test_repeated_ambiguous_decision_field_quote_does_not_cover_both_occurrences():
    field = "Price Target: not provided."
    text = field + "\n\n" + field
    output = {"claims": [{"quoted_claim": field, "outcome": "unsupported", "explanation": "Not established.", "evidence": []}],
              "no_material_claims": False}
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", text)])]
    result = run_audit(state(), Model(output), inventory=inventory(parts=parts))
    assert result["status"] == "partial"
    assert result["coverage"]["reviewed_chunks"] == 0


def test_review_prompt_explicitly_requires_disposition_of_empty_decision_fields():
    model = Model({"claims": [], "no_material_claims": True})
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "Price Target: not provided.")])]
    result = run_audit(state(), model, inventory=inventory(parts=parts))
    assert result["status"] in {"partial", "unavailable"}
    assert "explicit recommendation, rating, target and sizing fields" in model.calls[0]
    assert "not provided" in model.calls[0]


@pytest.mark.parametrize("text,expected", [
    ("−$42.6M", "-42600000"), ("-$42.6M", "-42600000"),
    ("$-42.6M", "-42600000"), ("(42,609)", "-42609"),
    ("($42.6 million)", "-42600000"), ("+$36M", "36000000"),
])
def test_numeric_lookup_preserves_financial_sign_currency_and_accounting_parentheses(text, expected):
    from decimal import Decimal

    from tradingagents.ground_truth import _numeric_values

    assert _numeric_values(text) == {Decimal(expected)}


def test_stock_compensation_does_not_promote_a_market_price_above_issuer_evidence():
    from tradingagents.ground_truth import _source_priority

    price = {"source_id": "price", "locator": "close", "kind": "validated retained market observation",
             "text": "Completed close 70.70 USD."}
    filing = {"source_id": "issuer", "locator": "reconciliation", "kind": "filing passage",
              "text": "Stock-based compensation | 36,045; in thousands."}
    query = "Quarterly stock compensation was approximately $36M."
    assert _source_priority(query, filing) < _source_priority(query, price)
    assert _source_priority("The completed close was 70.70 USD.", price) == 0


@pytest.mark.parametrize("different_section", [False, True])
def test_introductory_context_does_not_leak_across_distant_blocks_or_sections(different_section):
    from tradingagents.ground_truth import _source_index

    original = state()
    blocks = [{"locator": "guidance", "section": "Outlook", "text": "For full-year 2026, we expect:"}]
    if not different_section:
        blocks.extend({"locator": f"gap-{index}", "section": "Outlook", "text": "Unrelated filing text."}
                      for index in range(8))
    blocks.append({"locator": "reconciliation", "section": "Net income" if different_section else "Outlook",
                   "text": "Quarterly net loss was 42,609 USD thousands."})
    original["filing_evidence"]["documents"][0]["blocks"] = blocks
    sources, _ = _source_index(original)
    row = next(source for source in sources.values() if source["locator"] == "reconciliation")
    assert row["context"]["preceding_introductions"] == []


def test_standard_scoped_margin_identity_does_not_require_an_extra_definition_source():
    model = Model({"claims": [], "no_material_claims": True})
    run_audit(state(), model, inventory=inventory())
    assert "same-period, same-basis net income / revenue" in model.calls[0]
    assert "separate textbook definition citation is not required" in model.calls[0]
    assert "nonstandard adjustments" in model.calls[0]


def test_computation_matches_displayed_financial_magnitudes_without_granting_prose_authority():
    from tradingagents.ground_truth import _arithmetic

    sources, _, calculation = indexed_cash_flow_arithmetic()
    for source in sources.values():
        if "fact" in source:
            source["fact"]["value"] = str(int(source["fact"]["value"]) * 1_000_000)
    claim = {"quoted_claim": "Operating cash and investing cash totaled $110M.", "outcome": "supported",
             "calculation": {**calculation, "value": "110000000"}}
    assert _arithmetic(claim, sources) is True


def test_percentage_computation_matches_percent_notation_but_currency_sum_does_not():
    from tradingagents.ground_truth import _arithmetic

    sources, _, calculation = indexed_cash_flow_arithmetic()
    facts = [source["fact"] for source in sources.values() if "fact" in source]
    facts[0]["metric"] = facts[1]["metric"] = "Revenue"
    facts[0]["value"], facts[1]["value"] = "8673", "10000"
    claim = {"quoted_claim": "Revenue changed −13.27%.", "outcome": "supported",
             "calculation": {**calculation, "operation": "percentage_change", "value": "-13.27", "decimal_places": 2}}
    assert _arithmetic(claim, sources) is True
    facts[0]["value"], facts[1]["value"] = "90", "20"
    claim = {"quoted_claim": "Margin was 110%.", "outcome": "supported", "calculation": calculation}
    assert _arithmetic(claim, sources) is False


def test_followup_domain_priority_uses_asserted_claim_not_negative_vendor_reason():
    from tradingagents.ground_truth import _select_followup_sources

    sources = {}
    for index in range(22):
        source_id = f"vendor-expectations-{index}"
        sources[(source_id, "row")] = {
            "source_id": source_id, "locator": "row", "kind": "attributed vendor output",
            "text": "Vendor consensus revenue forecast for zero-year period, unverified. " * 3}
    sources[("issuer", "guidance")] = {
        "source_id": "issuer", "locator": "guidance", "kind": "filing passage",
        "text": "Full-year revenue guidance: $1.208 to $1.211 billion."}
    assessment = {"quoted_claim": "The low guidance implies $1.9328 billion after 60% growth.",
                  "explanation": "The vendor consensus zero-year forecast cannot replace issuer guidance."}
    packet, _ = _select_followup_sources([assessment], sources, 700)
    assert ("issuer", "guidance") in packet


@pytest.mark.parametrize("token,source_text", [
    ("6%", "Adjusted operating income increased 6%, to 74 million USD."),
    ("$6", "Adjusted operating income increased 6 USD."),
])
def test_explicit_small_financial_quantity_retains_exact_numeric_retrieval_weight(token, source_text):
    from tradingagents.ground_truth import _relevance

    source = {"source_id": "issuer", "locator": "income", "kind": "filing passage", "text": source_text}
    # Bare structural ordinal 6 remains excluded; an explicitly financial amount
    # is a different retrieval assertion even when its word context is equal.
    assert _relevance(f"Adjusted operating income increased {token}.", source) >= (
        _relevance("Adjusted operating income increased 6.", source) + 40)


def target_control_state():
    original = state()
    original["target_validation"] = {"status": "unsupported", "target": None,
                                     "reasons": ["no supported structured target provided"]}
    return original


def test_target_control_is_indexed_only_for_report_declarations_and_binds_reuse_identity():
    from tradingagents.ground_truth import _select_sources, _source_index

    original = target_control_state()
    field = "**Price Target**: not provided — no supported structured target provided"
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", field)])]
    before = inventory(original, parts)
    changed = {**original, "target_validation": {"status": "supported", "target": "100", "unit": "USD"}}
    assert before["evidence_digest"] != inventory(changed, parts)["evidence_digest"]
    sources, _ = _source_index(original)
    controls = {key: row for key, row in sources.items() if row["kind"].startswith("retained target declaration")}
    assert len(controls) == 1
    assert _select_sources(field, controls, 90000)[0]
    assert not _select_sources("DOCN will reach 100 USD next year because revenue grew.", controls, 90000)[0]
    absent, _ = _source_index(state())
    assert not any(row["kind"].startswith("retained target declaration") for row in absent.values())


def test_target_record_change_prevents_reusing_a_reviewed_negative_declaration():
    original = target_control_state()
    field = "**Price Target**: not provided"
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", field)])]
    model = Model({"claims": [{"quoted_claim": field, "outcome": "unsupported", "explanation": "No record yet.", "evidence": []}],
                   "no_material_claims": False})
    prior = run_audit(original, model, inventory=inventory(original, parts))
    changed = {**original, "target_validation": {"status": "unsupported", "target": None, "reasons": ["Changed reason"]}}
    second = Model(model.output)
    result = run_audit(changed, second, inventory=inventory(changed, parts), prior_audit=prior)
    assert second.calls
    assert result["coverage"]["reused_chunk_ids"] == []


@pytest.mark.parametrize("quote", ["DOCN will reach 100 USD next year.",
                                    "Revenue was 100 USD.",
                                    "Price Target: $100 because revenue doubled."])
def test_target_control_cannot_support_future_prices_financial_facts_or_mixed_implications(quote):
    from tradingagents.ground_truth_context import target_control_sources

    row = next(iter(target_control_sources(target_control_state())[0].values()))
    claim = {"quoted_claim": quote, "outcome": "supported", "explanation": "Control is not financial evidence.",
             "evidence": [{"source_id": row["source_id"], "locator": row["locator"], "quote": row["declaration"]}]}
    chunk = {"chunk_id": "x", "section_id": "x", "start": 0, "text": quote}
    with pytest.raises(ValueError, match="target declaration"):
        _validate_claim(claim, chunk, {(row["source_id"], row["locator"]): row})


def test_target_control_can_establish_the_literal_negative_declaration_without_pm_authority():
    from tradingagents.ground_truth_context import target_control_sources
    from tradingagents.ground_truth_flow import _material_correction

    row = next(iter(target_control_sources(target_control_state())[0].values()))
    quote = row["declaration"]
    reference = {"source_id": row["source_id"], "locator": row["locator"], "quote": quote}
    finding = _validate_claim({"quoted_claim": quote, "outcome": "supported", "explanation": "The run declares no validated target.",
                               "evidence": [reference]},
                              {"chunk_id": "x", "section_id": "x", "start": 0, "text": quote},
                              {(row["source_id"], row["locator"]): row})
    assert finding["code_verified"] is False
    correction_quote = "Price Target: $100"
    correction = _validate_claim({"quoted_claim": correction_quote, "outcome": "contradicted", "decision_material": True,
                                 "explanation": "The run actually declares no validated target.", "correction": quote,
                                 "evidence": [reference]},
                                {"chunk_id": "x", "section_id": "x", "start": 0, "text": correction_quote},
                                {(row["source_id"], row["locator"]): row})
    assert correction["correction"] == quote
    assert not _material_correction(correction)


def test_target_control_evidence_retains_typed_unit_and_eligibility_without_model_spoof():
    from tradingagents.ground_truth_context import target_control_sources

    original = target_control_state()
    original["target_validation"] = {"status": "supported", "target": "100", "unit": "USD",
                                     "decision_use": {"final_target_eligible": False,
                                                      "classification": "forward_scenario", "suitability": "conditional"}}
    row = next(iter(target_control_sources(original)[0].values()))
    quote = row["declaration"]
    claim = {"quoted_claim": quote, "outcome": "supported", "explanation": "Only the report's declared field is established.",
             "evidence": [{"source_id": row["source_id"], "locator": row["locator"], "quote": quote,
                           "context": {"target_control": {"unit": "EUR", "decision_use": {"final_target_eligible": True}}}}]}
    result = _validate_claim(claim, {"chunk_id": "x", "section_id": "x", "start": 0, "text": quote},
                             {(row["source_id"], row["locator"]): row})
    control = result["evidence"][0]["context"]["target_control"]
    assert control["target"] == "100"
    assert control["unit"] == "USD"
    assert control["decision_use"] == {"final_target_eligible": False,
                                       "classification": "forward_scenario", "suitability": "conditional"}
    row["control"]["decision_use"]["final_target_eligible"] = True
    assert control["decision_use"]["final_target_eligible"] is False
    assert result["code_verified"] is False


@pytest.mark.parametrize("followup", [False, True])
def test_review_prompt_excludes_report_chunk_ids_from_citable_sources_while_retaining_assumptions(followup):
    from tradingagents.ground_truth import _review_prompt

    chunk = {"chunk_id": "report.md@0:100", "section_id": "report.md", "text": "Middle scenario assumption: 1.93B."}
    if followup:
        chunk["review_claims"] = [chunk["text"]]
        chunk["prior_assessments"] = [{"quoted_claim": chunk["text"], "outcome": "unsupported", "explanation": "Premise missing."}]
    prompt = _review_prompt(chunk, {})
    assert "Only source_id and locator pairs listed in SUPPLIED SOURCES are citable" in prompt
    assert "report filenames, chunk IDs and offsets are not source records" in prompt
    assert "Scenario assumptions in REPORT CHUNK may be read as stated assumptions" in prompt
    assert "cite supplied external records for their factual premises" in prompt


def test_valid_primary_references_do_not_rescue_an_invented_report_chunk_citation():
    from tradingagents.ground_truth import _source_index

    original = state()
    original["filing_evidence"]["documents"][0]["blocks"] += [
        {"locator": "annual-guidance", "text": "Full-year 2026 revenue guidance was $1.208 billion at the low end."},
        {"locator": "forecast", "text": "Management expects 2027 revenue growth of at least 60%."}]
    text = "The middle scenario assumption is slightly below the $1.9328 billion implied by low guidance and 60% growth."
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "Revenue was 100 USD.\n\n" + text)])]
    report = inventory(original, parts)
    chunk = report["chunks"][0]
    references = [
        {"source_id": "doc-1", "locator": "annual-guidance", "quote": original["filing_evidence"]["documents"][0]["blocks"][1]["text"]},
        {"source_id": "doc-1", "locator": "forecast", "quote": original["filing_evidence"]["documents"][0]["blocks"][2]["text"]},
    ]
    claim = {"quoted_claim": text, "outcome": "supported", "explanation": "Conditional arithmetic uses a stated scenario assumption.",
             "evidence": references}
    sources, _ = _source_index(original)
    accepted = _validate_claim(claim, chunk, sources)
    assert accepted["outcome"] == "supported"
    assert accepted["code_verified"] is False
    invented = {"source_id": chunk["chunk_id"], "locator": "text", "quote": text}
    rejected = {**claim, "evidence": [*references, invented]}
    with pytest.raises(ValueError, match="source quote or locator not present"):
        _validate_claim(rejected, chunk, sources)
    result = run_audit(original, Model({"claims": [response()["claims"][0], rejected], "no_material_claims": False}), inventory=report)
    assert result["status"] == "partial"
    assert result["coverage"]["reviewed_chunks"] == 0
    assert [finding["quoted_claim"] for finding in result["claims"]] == ["Revenue was 100 USD."]
