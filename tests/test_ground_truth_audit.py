"""Ground Truth audit tests use local synthetic sources and fake model responses."""
from copy import deepcopy

from tradingagents.ground_truth import (
    build_inventory,
    corrected_parts,
    render_audit,
    resolve_audit,
    run_audit,
)

PARTS = [("Decision", "5_portfolio", [("Portfolio Manager", "decision.md", "Revenue was 100 USD.\n\nLast claim is 9 USD.")])]


def state():
    return {"run_id": "run-1", "company_of_interest": "DOCN", "trade_date": "2026-11-06",
            "issuer_identity": {"cik": "0001582961"},
            "filing_evidence": {"cik": "0001582961", "as_of": "2026-11-06", "documents": [{
                "source_id": "doc-1", "filing": {"cik": "0001582961", "filed_date": "2026-11-03"},
                "url": "https://www.sec.gov/Archives/edgar/data/1582961/example.htm",
                "blocks": [{"locator": "table-1", "text": "Revenue was 100 USD. Last claim is 10 USD."}]}]}}


class Model:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def invoke(self, prompt):
        self.calls.append(prompt)
        return self.output


def response():
    return {"claims": [
        {"quoted_claim": "Revenue was 100 USD.", "outcome": "supported", "explanation": "Source agrees.",
         "evidence": [{"source_id": "doc-1", "locator": "table-1", "quote": "Revenue was 100 USD."}]},
        {"quoted_claim": "Last claim is 9 USD.", "outcome": "contradicted", "explanation": "Source states 10.",
         "correction": "Last claim is 10 USD.", "correction_scope": "complete_claim",
         "evidence": [{"source_id": "doc-1", "locator": "table-1", "quote": "Last claim is 10 USD."}]},
    ], "no_material_claims": False}


def inventory(s=None, parts=None):
    return build_inventory(s or state(), parts=parts or PARTS, summary_text="")


def test_inventory_preserves_all_characters_and_binds_report_sources_run_and_summary():
    s = state()
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "a" * 17000 + "Final assertion 99.")])]
    inv = inventory(s, parts)
    assert "".join(c["text"] for c in inv["chunks"]) == parts[0][2][0][2]
    assert inv["chunks"][-1]["text"].endswith("Final assertion 99.")
    for field, value in (("run_id", "other"), ("trade_date", "2026-11-05")):
        changed = {**s, field: value}
        assert inventory(changed, parts)["digest"] != inv["digest"]
    changed = deepcopy(s)
    changed["filing_evidence"]["documents"][0]["blocks"][0]["text"] += " revised"
    assert inventory(changed, parts)["digest"] != inv["digest"]
    assert build_inventory(s, parts=parts, summary_text="A new summary.")["digest"] != inv["digest"]


def test_review_cites_real_source_locations_and_retains_original_corrections():
    s = state()
    before = deepcopy(s)
    result = run_audit(s, Model(response()), inventory=inventory(s))
    assert result["status"] == "completed with findings"
    assert result["coverage"]["reviewed_chunks"] == result["coverage"]["total_chunks"] == 1
    assert len(result["claims"]) == 2
    assert result["claims"][1]["quoted_claim"] == "Last claim is 9 USD."
    updated = corrected_parts(PARTS, result)
    assert "Last claim is 10 USD." in updated[0][2][0][2]
    assert "Last claim is 9 USD." in updated[0][2][0][2]
    assert s == before
    assert "model" in render_audit(result).lower()
    assert "https://www.sec.gov/" in render_audit(result)


def test_fabricated_source_quote_or_report_claim_never_clears_review():
    for field, value in (("quoted_claim", "A fabricated report assertion"),):
        output = response()
        output["claims"][0][field] = value
        result = run_audit(state(), Model(output), inventory=inventory())
        assert result["status"] == "partial"
    for key, value in (("source_id", "invented"), ("quote", "A fabricated source quote"), ("locator", "wrong-table")):
        output = response()
        output["claims"][0]["evidence"][0][key] = value
        result = run_audit(state(), Model(output), inventory=inventory())
        assert result["status"] == "partial"
        assert not any(c["outcome"] == "supported" for c in result["claims"])


def test_wrong_issuer_and_future_sources_are_excluded():
    for field, value in (("cik", "0000000001"), ("filed_date", "2026-11-07")):
        s = state()
        s["filing_evidence"]["documents"][0]["filing"][field] = value
        result = run_audit(s, Model(response()), inventory=inventory(s))
        assert result["status"] == "partial"
        assert result["coverage"]["source_gaps"]


def test_empty_or_malformed_response_and_unreviewed_numbers_are_partial():
    for output in (None, {}, {"claims": [], "no_material_claims": True},
                   {"claims": response()["claims"][:1], "no_material_claims": False}):
        result = run_audit(state(), Model(output), inventory=inventory())
        assert result["status"] in ("partial", "unavailable")
        assert result["coverage"]["reviewed_chunks"] == 0


def test_request_budget_leaves_last_paragraph_explicitly_unreviewed():
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "A fact.\n\n" * 2000 + "Last assertion 99.")])]
    inv = inventory(parts=parts)
    model = Model({"claims": [], "no_material_claims": True})
    result = run_audit(state(), model, {"ground_truth_max_requests": 1}, inventory=inv)
    assert len(model.calls) == 1
    assert result["status"] == "partial"
    assert result["coverage"]["remaining_chunks"]
    assert "budget" in " ".join(result["limits"]).lower()


def test_saved_result_is_reused_offline_only_for_the_matching_inventory():
    s = state()
    inv = inventory(s)
    result = run_audit(s, Model(response()), inventory=inv)
    assert resolve_audit(s, result, inventory=inv)["status"] == "completed with findings"
    changed = inventory({**s, "run_id": "another-run"})
    assert resolve_audit(s, result, inventory=changed)["status"] == "unavailable"
    tampered = deepcopy(result)
    tampered["claims"][0]["quoted_claim"] = "Forged record"
    assert resolve_audit(s, tampered, inventory=inv)["status"] == "unavailable"


def test_provider_failure_is_bounded_and_sanitized():
    class Failing:
        def invoke(self, prompt):
            raise RuntimeError("Secret API key should never appear in the audit")
    result = run_audit(state(), Failing(), inventory=inventory())
    assert result["status"] == "unavailable"
    assert "Secret" not in str(result)


def financial_state():
    s = state()
    s["financial_evidence"] = {
        "schema_version": 1, "cik": "0001582961", "as_of": "2026-11-06",
        "sources": [{"source_id": "sec-fact", "cik": "0001582961",
                     "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001582961.json",
                     "filed_date": "2026-11-03", "retrieved_at": "2026-11-06T00:00:00Z",
                     "content_hash": "a" * 64, "locator": "Revenue", "form": "10-Q"}],
        "facts": [{"fact_id": "revenue", "metric": "Revenue", "value": "100", "unit": "USD",
                   "cik": "0001582961", "period_start": "2026-07-01", "period_end": "2026-09-30",
                   "as_of": "2026-11-06", "basis": "US-GAAP", "source_ids": ["sec-fact"],
                   "locator": "Revenue", "origin": "reported"}],
    }
    return s


def test_code_verified_requires_complete_period_unit_and_value_binding():
    import json

    s = financial_state()
    fact = s["financial_evidence"]["facts"][0]
    check = {k: fact[k] for k in ("fact_id", "metric", "value", "unit", "period_start", "period_end", "basis")}
    canonical = "Revenue: 100 USD; 2026-07-01 to 2026-09-30; US-GAAP."
    for quote in (canonical, "Revenue was 1000 USD in 2024.", "Revenue was 100 EUR."):
        parts = [("Decision", "5_portfolio", [("PM", "decision.md", quote)])]
        model = Model({"no_material_claims": False, "claims": [{
            "quoted_claim": quote, "outcome": "supported", "explanation": "Check fields.",
            "fact_check": check, "evidence": [{"source_id": "revenue", "locator": "Revenue",
                "quote": json.dumps(fact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}]}]})
        # Model dumps add default fields, so use the exact retained excerpt from
        # the actual prompt instead of predicting serialization details.
        class FactModel:
            def invoke(self, prompt, response_model=model):
                source = json.loads(prompt.split("SUPPLIED SOURCES (selection may be incomplete):\n")[1])
                candidate = next(v for v in source if v["source_id"] == "revenue")
                result = deepcopy(response_model.output)
                result["claims"][0]["evidence"][0]["quote"] = candidate["text"]
                return result
        result = run_audit(s, FactModel(), inventory=inventory(s, parts))
        assert len(result["claims"]) == 1
        assert result["claims"][0]["code_verified"] is (quote == canonical)


def test_zero_budget_never_resets_to_default_or_invokes_provider():
    model = Model(response())
    result = run_audit(state(), model, {"ground_truth_max_requests": 0}, inventory=inventory())
    assert not model.calls
    assert result["usage"]["requests"] == 0
    assert result["coverage"]["remaining_chunks"]


def test_incremental_review_reuses_only_matching_chunk_text_and_source_version():
    s = state()
    initial = run_audit(s, Model(response()), inventory=inventory(s))
    # A newly generated summary is the only new text. The report body is reused.
    inv = build_inventory(s, parts=PARTS, summary_text="A qualified hypothesis.")
    model = Model({"claims": [], "no_material_claims": True})
    final = run_audit(s, model, inventory=inv, prior_audit=initial)
    assert final["usage"]["requests"] == 1
    assert len(final["coverage"]["reused_chunk_ids"]) == 1
    assert len(final["claims"]) == 2
    # Changed report assertions must be reviewed anew, and old claims disappear.
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "A qualified hypothesis.")])]
    changed = run_audit(s, model, inventory=inventory(s, parts), prior_audit=initial)
    assert not changed["coverage"]["reused_chunk_ids"]
    assert not changed["claims"]
    # Evidence changes invalidate reuse even when reader text stays identical.
    changed_state = deepcopy(s)
    changed_state["filing_evidence"]["documents"][0]["blocks"][0]["text"] += " Changed evidence."
    no_budget = run_audit(changed_state, model, {"ground_truth_max_requests": 0},
                          inventory=inventory(changed_state), prior_audit=initial)
    assert no_budget["coverage"]["reviewed_chunks"] == 0
    forged = deepcopy(initial)
    forged["claims"][0]["explanation"] = "Forged assessment"
    assert not run_audit(s, model, {"ground_truth_max_requests": 0},
                         inventory=inventory(s), prior_audit=forged)["coverage"]["reused_chunk_ids"]


def test_one_invalid_claim_preserves_other_verified_findings_with_partial_coverage():
    output = response()
    output["claims"][0]["evidence"][0]["quote"] = "Invented citation text"
    result = run_audit(state(), Model(output), inventory=inventory())
    assert result["status"] == "partial"
    assert result["coverage"]["reviewed_chunks"] == 0
    assert len(result["claims"]) == 1
    assert result["claims"][0]["correction"] == "Last claim is 10 USD."


def test_relevance_prefers_explicit_fact_and_specific_value_over_generic_terms():
    from tradingagents.ground_truth import _select_sources

    sources = {
        ("generic", "paragraph"): {"source_id": "generic", "locator": "paragraph",
                                    "text": "The report evidence company financial data sources."},
        ("actual-rpo", "table"): {"source_id": "actual-rpo", "locator": "table",
                                  "text": "Remaining performance obligations total 893.828 million."},
    }
    selected, omitted = _select_sources("RPO was 893.828 million (actual-rpo).", sources, 170)
    assert ("actual-rpo", "table") in selected
    assert omitted == 1


def test_financial_sources_require_trusted_issuer_scoped_sec_addresses():
    from tradingagents.ground_truth import _source_index

    for url in ("https://example.invalid/revenue", "https://www.sec.gov/Archives/edgar/data/999/statement.htm",
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json",
                "https://www.sec.gov@evil.example/Archives/edgar/data/1582961/a.htm",
                "https://www.sec.gov/Archives/edgar/data/1582961/../../999/a.htm",
                "https://www.sec.gov/Archives/edgar/data/1582961/%2e%2e/999/a.htm"):
        s = financial_state()
        s["financial_evidence"]["sources"][0]["url"] = url
        sources, gaps = _source_index(s)
        assert not any(source.get("fact") for source in sources.values())
        assert gaps


def test_date_only_sources_cannot_establish_same_day_intraday_availability():
    from tradingagents.ground_truth import _source_index

    s = financial_state()
    s["analysis_clock"] = {"cutoff_utc": "2026-11-06T01:00:00Z"}
    s["financial_evidence"]["sources"][0]["filed_date"] = "2026-11-06"
    s["financial_evidence"]["sources"][0]["retrieved_at"] = "2026-11-07T00:00:00Z"
    doc = s["filing_evidence"]["documents"][0]
    doc["filing"]["filed_date"] = "2026-11-06"
    doc["retrieved_at"] = "2026-11-07T00:00:00Z"
    sources, gaps = _source_index(s)
    assert not sources
    assert len(gaps) >= 2
    # A trusted retained retrieval before the cutoff bounds actual availability.
    doc["retrieved_at"] = "2026-11-06T00:30:00Z"
    assert ("doc-1", "table-1") in _source_index(s)[0]


def test_corrections_use_exact_chunk_location_and_preserve_table_rows():
    from tradingagents.ground_truth import corrected_text

    text = "Q1\n\nRevenue was 9 USD.\n\nQ2\n\nRevenue was 9 USD.\n\n| Metric | Value |\n| --- | --- |\n| Revenue | 9 USD |\n| Cash | 8 USD |\n\nEnd."
    quote = "Revenue was 9 USD."
    position = text.rindex(quote)
    table_quote = "9 USD"
    table_start = text.index(table_quote, text.index("| Metric"))
    record = {"claims": [
        {"section_id": "5_portfolio/decision.md", "quoted_claim": quote,
         "character_start": position, "character_end": position + len(quote),
         "outcome": "contradicted", "correction": "Revenue was 10 USD."},
        {"section_id": "5_portfolio/decision.md", "quoted_claim": table_quote,
         "character_start": table_start, "character_end": table_start + len(table_quote),
         "outcome": "contradicted", "correction": "10 USD"}]}
    output = corrected_text("5_portfolio/decision.md", text, record)
    assert output.startswith("Q1\n\nRevenue was 9 USD.\n\nQ2\n\nRevenue was 9 USD.")
    assert output.index("Revenue was 10 USD.") > output.index("Q2")
    assert "| Revenue | 9 USD |\n| Cash | 8 USD |" in output
    assert output.index("Supporting source excerpt: 10 USD") > output.index("| Cash | 8 USD |")


def test_ambiguous_repeated_quote_is_retained_as_finding_without_auto_annotation():
    from tradingagents.ground_truth import corrected_text

    text = "Revenue was 100 USD.\n\nRevenue was 100 USD."
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", text)])]
    output = {"claims": response()["claims"][:1], "no_material_claims": False}
    output["claims"][0]["outcome"] = "contradicted"
    output["claims"][0]["correction"] = "Revenue was 100 USD."
    result = run_audit(state(), Model(output), inventory=inventory(parts=parts))
    assert result["claims"][0]["ambiguous_location"]
    assert corrected_text("5_portfolio/decision.md", text, result) == text


def test_fractional_remaining_seconds_and_invalid_limits_do_not_reset_allowance():
    from tradingagents.ground_truth import _positive

    assert _positive({"ground_truth_max_seconds": 0.25}, "ground_truth_max_seconds", 600, 7200) == 0.25
    for value in (-1, float("nan"), True, "20"):
        model = Model(response())
        result = run_audit(state(), model, {"ground_truth_max_requests": value}, inventory=inventory())
        assert not model.calls
        assert result["usage"]["requests"] == 0


def test_real_chat_message_content_is_parsed_before_pydantic_message_envelope():
    import json

    from langchain_core.messages import AIMessage

    for content in (json.dumps(response()), [{"type": "text", "text": json.dumps(response())}]):
        model = Model(AIMessage(content=content, usage_metadata={"input_tokens": 10,
                                                              "output_tokens": 20, "total_tokens": 30}))
        result = run_audit(state(), model, inventory=inventory())
        assert result["status"] == "completed with findings"
        assert len(result["claims"]) == 2
        assert result["usage"]["output_tokens"] == 20


def test_token_budget_reserves_unknown_usage_before_provider_calls():
    model = Model(response())
    empty = run_audit(state(), model, {"ground_truth_max_tokens": 10}, inventory=inventory())
    assert not model.calls
    assert empty["usage"]["budget_tokens"] == 0
    assert "Token allowance" in str(empty["limits"])
    result = run_audit(state(), model, inventory=inventory())
    assert result["usage"]["budget_tokens"] > 16384
    assert result["usage"]["unknown_usage_requests"] == 1


def test_observed_provider_token_overrun_is_disclosed_and_debited():
    import json

    from langchain_core.messages import AIMessage

    model = Model(AIMessage(content=json.dumps(response()), usage_metadata={
        "input_tokens": 100, "output_tokens": 50000, "total_tokens": 50100}))
    result = run_audit(state(), model, {"ground_truth_max_tokens": 40000,
                                      "ground_truth_output_token_reservation": 16384}, inventory=inventory())
    assert result["usage"]["budget_tokens"] == 50100
    assert result["usage"]["unknown_usage_requests"] == 0
    assert "exceeded" in str(result["limits"])


def test_structural_ordinals_are_ignored_but_heading_counts_require_coverage():
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "## 1. Summary\n\n## 2. Why these 8 indicators")])]
    result = run_audit(state(), Model({"claims": [], "no_material_claims": True}), inventory=inventory(parts=parts))
    assert result["coverage"]["reviewed_chunks"] == 0
    clean = [("Decision", "5_portfolio", [("PM", "decision.md", "## 1. Summary\n\n## 2. Conclusions")])]
    result = run_audit(state(), Model({"claims": [], "no_material_claims": True}), inventory=inventory(parts=clean))
    assert result["coverage"]["reviewed_chunks"] == 1


def test_repeated_malformed_provider_output_stops_after_three_failures():
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", "A fact.\n\n" * 4000)])]
    model = Model({"unexpected": "schema"})
    result = run_audit(state(), model, inventory=inventory(parts=parts))
    assert len(model.calls) == 3
    assert result["coverage"]["remaining_chunks"]
    assert "Consecutive review failures" in str(result["limits"])


def test_partial_chunks_with_valid_findings_count_as_progress():
    parts = [("Decision", "5_portfolio", [
        ("PM", f"section-{i}.md", "Revenue was 100 USD. Additional claim 99.") for i in range(5)])]
    model = Model({"claims": response()["claims"][:1], "no_material_claims": False})
    result = run_audit(state(), model, inventory=inventory(parts=parts))
    assert len(model.calls) == 10  # One bounded repair for each omitted occurrence.
    assert len(result["claims"]) == 5
    assert result["status"] == "partial"
    assert result["coverage"]["reviewed_chunks"] == 0
    assert not any("Consecutive" in limit for limit in result["limits"])


def test_long_tables_split_on_rows_and_retain_column_period_and_unit_context():
    header = "| Metric (USD millions) | September 2026 | September 2025 |\n| --- | --- | --- |\n"
    text = "# Quarterly results\n\n" + header + "".join(f"| Revenue {i} | 321 | 200 |\n" for i in range(600))
    parts = [("Financials", "1_analysts", [("Fundamentals", "fundamentals.md", text)])]
    inv = inventory(parts=parts)
    assert "".join(chunk["text"] for chunk in inv["chunks"]) == text
    for chunk in inv["chunks"][1:]:
        assert chunk["text"].startswith("|")
        assert "USD millions" in " ".join(chunk["context"]["table_headers"])
        assert "September 2026" in " ".join(chunk["context"]["table_headers"])
        assert "Quarterly results" in " ".join(chunk["context"]["headings"])


def test_changed_external_section_context_invalidates_incremental_reuse():
    class WholeChunkModel:
        def invoke(self, prompt):
            import json
            chunk = json.loads(prompt.split("REPORT CHUNK:\n")[1].split("\nSUPPLIED SOURCES")[0])
            return {"claims": [{"quoted_claim": chunk["text"], "outcome": "unsupported",
                                "explanation": "Missing support", "evidence": []}], "no_material_claims": False}
    original = inventory(parts=[("Quarter 2026", "5_portfolio", [("PM", "decision.md", "Revenue was 99 USD.")])])
    prior = run_audit(state(), WholeChunkModel(), inventory=original)
    changed = inventory(parts=[("Quarter 2025", "5_portfolio", [("PM", "decision.md", "Revenue was 99 USD.")])])
    result = run_audit(state(), WholeChunkModel(), {"ground_truth_max_requests": 0},
                       inventory=changed, prior_audit=prior)
    assert not result["coverage"]["reused_chunk_ids"]


def test_financial_scaling_and_completed_price_relevance_normalize_display_values():
    from tradingagents.ground_truth import _numeric_values, _relevance

    assert 321_000_000 in _numeric_values("Revenue 321M USD")
    assert 1_200_000_000 in _numeric_values("Revenue 1.2 billion USD")
    fact = {"source_id": "canonical", "locator": "Revenue", "text": '{"value":"321332000","unit":"USD"}',
            "fact": {"metric": "Revenue"}}
    boilerplate = {"source_id": "generic", "locator": "body", "text": "Financial report 2026-11-06 with financial sources."}
    assert _relevance("Quarterly Revenue was 321M in 2026-11-06.", fact) > _relevance("Quarterly Revenue was 321M in 2026-11-06.", boilerplate)
    market = {"source_id": "close", "locator": "completed", "text": "DOCN completed close 70.7 USD.",
              "kind": "validated retained market observation"}
    assert _relevance("The stock closed at $70.70.", market) > _relevance("The stock closed at $70.70.", boilerplate)


def test_long_source_blocks_remain_selectable_as_traceable_fragments():
    from tradingagents.ground_truth import _select_sources, _source_index

    s = state()
    text = "| Metric (USD millions) | 2026 | 2025 |\n| --- | --- | --- |\n" + "| Other | 1 | 2 |\n" * 500 + "| Revenue | 321 | 200 |\n"
    s["filing_evidence"]["documents"][0]["blocks"][0]["text"] = text
    sources, _ = _source_index(s)
    selected, _ = _select_sources("Revenue 321 million USD in 2026.", sources, 6000)
    relevant = next(source for source in selected.values() if "| Revenue | 321 | 200 |" in source["text"])
    assert relevant["original_locator"] == "table-1"
    assert text[relevant["source_character_start"]:relevant["source_character_end"]] == relevant["text"]
    assert "USD millions" in str(relevant["context"]["table_headers"])


def test_claim_dependent_followup_can_recover_evidence_omitted_from_first_packet():
    import json

    from tradingagents.ground_truth import _json, _source_index

    s = state()
    s["filing_evidence"]["documents"][0]["blocks"] = [
        {"locator": "a-revenue", "text": "Revenue was 100 USD."},
        {"locator": "z-staffing", "text": "Staffing 9."}]
    text = "Revenue was 100 USD. Staffing 9."
    parts = [("Decision", "5_portfolio", [("PM", "decision.md", text)])]
    source_cap = max(len(_json(source)) for source in _source_index(s)[0].values()) + 1
    class Reviewer:
        def __init__(self):
            self.calls = 0
        def invoke(self, prompt):
            self.calls += 1
            chunk = json.loads(prompt.split("REPORT CHUNK:\n")[1].split("\nSUPPLIED SOURCES")[0])
            supplied = json.loads(prompt.split("SUPPLIED SOURCES (selection may be incomplete):\n")[1])
            if chunk.get("review_claims"):
                assert prompt.startswith("Recheck ONLY the exact review_claims target strings")
                assert chunk["review_claims"] == ["Staffing 9."]
                source = next(source for source in supplied if source["locator"] == "z-staffing")
                return {"no_material_claims": False, "claims": [{
                    "quoted_claim": "Staffing 9.", "outcome": "supported", "explanation": "Additional source agrees.",
                    "evidence": [{"source_id": source["source_id"], "locator": source["locator"], "quote": source["text"]}]},
                    # A weak provider may repeat a nontarget with missing
                    # references. It cannot erase the previously valid result.
                    {"quoted_claim": "Revenue was 100 USD.", "outcome": "supported", "explanation": "Extra output.", "evidence": []}]}
            source = next(source for source in supplied if source["locator"] == "a-revenue")
            return {"no_material_claims": False, "claims": [
                {"quoted_claim": "Revenue was 100 USD.", "outcome": "supported", "explanation": "Source agrees.",
                 "evidence": [{"source_id": source["source_id"], "locator": source["locator"], "quote": source["text"]}]},
                {"quoted_claim": "Staffing 9.", "outcome": "unsupported", "explanation": "Not in first packet.", "evidence": []}]}
    reviewer = Reviewer()
    result = run_audit(s, reviewer, {"ground_truth_max_source_characters": source_cap}, inventory=inventory(s, parts))
    assert reviewer.calls == 2
    assert result["usage"]["requests"] == 2
    assert result["status"] == "completed"
    assert all(claim["outcome"] == "supported" for claim in result["claims"])
    limited = run_audit(s, Reviewer(), {"ground_truth_max_source_characters": source_cap,
                                      "ground_truth_max_requests": 1}, inventory=inventory(s, parts))
    assert limited["status"] == "partial"
    assert limited["usage"]["requests"] == 1
    assert any(claim["outcome"] == "unsupported" for claim in limited["claims"])


def test_brief_context_only_enters_packets_for_explicit_brief_scope_claims():
    from tradingagents.ground_truth import _select_sources, _source_index

    s = {**state(), "shared_source_brief": "Revenue was 100 USD. No RPO field."}
    sources, _ = _source_index(s)
    normal, _ = _select_sources("Revenue was 100 USD.", sources, 24000)
    assert not any(source["kind"].startswith("retained report context") for source in normal.values())
    scope, _ = _select_sources("No RPO fact is in the retained brief.", sources, 24000)
    assert any(source["kind"].startswith("retained report context") for source in scope.values())


def test_actual_source_captions_and_filing_metadata_are_preserved_without_inferred_periods():
    from tradingagents.ground_truth import _source_index

    s = state()
    doc = s["filing_evidence"]["documents"][0]
    doc["blocks"][0]["section"] = "Quarterly operating highlights in USD millions"
    doc["filing"].update(report_date="2026-11-03", form="8-K")
    sources, _ = _source_index(s)
    context = sources[("doc-1", "table-1")]["context"]
    assert context["source_section"] == "Quarterly operating highlights in USD millions"
    assert context["filing_report_date"] == "2026-11-03"
    assert context["filing_form"] == "8-K"
    assert "not an inferred accounting period" in context["date_scope"]


def test_reproduced_calculation_sources_are_usable_without_new_financial_authority():
    from tests.test_ground_truth_calculations import fixture
    from tradingagents.ground_truth import _source_index

    s, _trusted = fixture()
    sources, _ = _source_index(s)
    calculation = next(source for source in sources.values() if source["kind"] == "reproduced financial calculation")
    assert "fact" not in calculation
    text = calculation["text"]
    parts = [("Calculations", "1_analysts", [("Fundamentals", "fundamentals.md", text)])]
    result = run_audit(s, Model({"claims": [{"quoted_claim": text, "outcome": "supported",
        "explanation": "Exact retained source replay.", "decision_material": True,
        "evidence": [{"source_id": calculation["source_id"], "locator": calculation["locator"], "quote": text}]}],
        "no_material_claims": False}), inventory=inventory(s, parts))
    assert result["claims"]
    assert all(not claim["code_verified"] for claim in result["claims"])
    altered = deepcopy(s)
    for source in altered["financial_evidence"]["sources"]:
        source["url"] = "https://example.invalid/forged"
    assert not any(source["kind"] == "reproduced financial calculation"
                   for source in _source_index(altered)[0].values())


def test_retained_rpo_change_is_replayed_with_exact_scope_without_rating_authority():
    import json
    from pathlib import Path

    from tradingagents.agents.kpi_comparisons import compare_rpo
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
    from tradingagents.ground_truth import _source_index

    fixtures = Path(__file__).parent / "fixtures"
    current = DisclosurePackage.model_validate(json.loads((fixtures / "docn_2026q3/rpo_context.json").read_text())["package"])
    prior = DisclosurePackage.model_validate(json.loads((fixtures / "docn_2026q2/prior_quarter_rpo.json").read_text())["package"])
    s = {**state(), "trade_date": str(current.as_of),
         "disclosure_evidence": {"kpi_comparisons": [compare_rpo(current, prior)]}}
    sources, _ = _source_index(s)
    rpo = next(source for source in sources.values() if source["kind"] == "reproduced RPO comparison")
    assert "-10.53%" in rpo["text"]
    assert "does not establish the cause" in rpo["text"]
    assert "fact" not in rpo
    altered = {**s, "issuer_identity": {"cik": "0000000001"}}
    assert not any(source["kind"] == "reproduced RPO comparison" for source in _source_index(altered)[0].values())
