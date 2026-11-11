"""PM citation display checks compare cited figures to canonical IDs only."""

from tradingagents.agents.citation_check import check_pm_citations, render_pm_citation_check

BRIEF = """Accepted evidence brief
- [F46] Revenue: 321200000 USD; 2026-09-30; source S1
- [C2] gross margin: pass; 29.455 percent; inputs F46

<!-- evidence-references:start -->
- F46: fact_id revenue-fact
- K1: source_id rpo-current; source
- D1: source_id guidance-source; source
<!-- evidence-references:end -->"""


def _state(summary, thesis="", **extra):
    return {
        "canonical_financial_context": BRIEF,
        "unvalidated_outputs": {"portfolio_manager": {"structured": {
            "executive_summary": summary, "investment_thesis": thesis}}},
        **extra,
    }


def test_pm_cited_revenue_matches():
    result = check_pm_citations(_state("Revenue was $321.2 million (F46)."))
    assert (result["matched"], result["checked"], result["uncited_sentences"]) == (1, 1, 0)
    assert result["mismatches"] == []
    assert "PM citation check: 1 of 1 cited figures matched" in render_pm_citation_check(result)


def test_pm_cited_value_mismatch_listed():
    sentence = "Revenue was $322.2 million (F46)."
    result = check_pm_citations(_state(sentence))
    assert (result["matched"], result["checked"]) == (0, 1)
    assert result["mismatches"][0]["sentence"] == sentence
    assert result["mismatches"][0]["citation_id"] == "F46"
    assert "321200000 USD" in result["mismatches"][0]["canonical_value"]
    rendered = render_pm_citation_check(result)
    assert sentence in rendered and "321200000 USD" in rendered


def test_uncited_sentences_counted_not_checked_and_unknown_id_unresolved():
    result = check_pm_citations(_state("Revenue might grow. Revenue was $321.2 million (F46).",
                                       "Margins may improve. A number is 2 (F99)."))
    assert (result["matched"], result["checked"], result["uncited_sentences"]) == (1, 1, 2)
    assert result["unresolved_citations"] == ["F99"]


def test_percent_and_millions_rounding():
    result = check_pm_citations(_state(
        "Revenue was $321.2 million (F46). Gross margin was 29.46% (C2)."))
    assert (result["matched"], result["checked"]) == (2, 2)
    changed = check_pm_citations(_state("Gross margin was 29.47% (C2)."))
    assert changed["matched"] == 0 and changed["checked"] == 1


def test_canonical_rounded_percent_marker_is_not_part_of_unit():
    state = _state("Gross margin was 29.46% (C2).")
    state["canonical_financial_context"] = BRIEF.replace(
        "29.455 percent", "29.455 (rounded for display) percent")
    result = check_pm_citations(state)
    assert (result["matched"], result["checked"]) == (1, 1)


def test_k_and_d_use_existing_reference_mappings_and_structured_values():
    state = _state(
        "Current RPO was $2.4 billion (K1). Guidance is at least 35.00% (D1).",
        disclosure_evidence={
            "kpi_comparisons": [{"status": "pass", "current_value": "2400000000",
                                 "sources": {"current": {"source_id": "rpo-current"}}}],
            "extraction": {"claims": [{"source_id": "guidance-source", "value": "35",
                                        "unit": "%"}]},
        },
    )
    result = check_pm_citations(state)
    assert (result["matched"], result["checked"]) == (2, 2)


def test_disclosure_value_keeps_its_canonical_million_unit():
    state = _state("Guidance was $321.2 million (D1).", disclosure_evidence={
        "extraction": {"claims": [{"source_id": "guidance-source", "value": "321.2",
                                   "unit": "million"}]},
    })
    result = check_pm_citations(state)
    assert (result["matched"], result["checked"]) == (1, 1)


def test_citation_only_sentence_is_not_a_checked_figure():
    result = check_pm_citations(_state(
        "See F46, C2 for source figures.",
        "Revenue was $321.2 million (F46)."))
    assert (result["matched"], result["checked"]) == (1, 1)
    assert result["citation_only_sentences"] == 1
    assert result["mismatches"] == []
    rendered = render_pm_citation_check(result)
    assert "1 of 1 cited figures matched" in rendered
    assert "Citation-only sentences: 1 (not checked)" in rendered


def test_exact_full_precision_percent_and_millions_match_before_display_rounding():
    state = _state("Revenue was $321.192 million (F46). Gross margin was 29.455% (C2).")
    state["canonical_financial_context"] = BRIEF.replace("321200000 USD", "321192000 USD")
    result = check_pm_citations(state)
    assert (result["matched"], result["checked"]) == (2, 2)
    assert result["mismatches"] == []
    rounded = _state("Revenue was $321.2 million (F46). Gross margin was 29.46% (C2).")
    rounded["canonical_financial_context"] = state["canonical_financial_context"]
    assert check_pm_citations(rounded)["matched"] == 2
    wrong = _state("Revenue was $321.3 million (F46). Gross margin was 29.47% (C2).")
    wrong["canonical_financial_context"] = state["canonical_financial_context"]
    assert check_pm_citations(wrong)["matched"] == 0


def test_oversized_claimed_number_is_mismatch_without_crash():
    result = check_pm_citations(_state("Revenue was $" + "9" * 400 + " million (F46)."))
    assert (result["matched"], result["checked"]) == (0, 1)


_NOV_BRIEF = (
    "- [F44] Revenue: 229000000 USD; period\n"
    "- [F46] Revenue: 320000000 USD; period\n"
    "- [F50] Gross Profit: 160000000 USD; period\n"
    "- [C15] revenue yoy growth: pass; 39.87 (rounded for display) percent; Derived revenue growth; inputs F46, F44\n"
)


def _nov_state(summary, **extra):
    return {"canonical_financial_context": _NOV_BRIEF,
            "unvalidated_outputs": {"portfolio_manager": {"structured": {"executive_summary": summary, "investment_thesis": ""}}},
            **extra}


def test_inputs_of_matched_calculation_are_not_mismatches():
    result = check_pm_citations(_nov_state("Revenue grew 39.87% year over year (F46, F44, C15)."))
    assert result["mismatches"] == [] and (result["matched"], result["checked"]) == (3, 3)


def test_inputs_of_unmatched_calculation_still_mismatch():
    result = check_pm_citations(_nov_state("Revenue grew 50% year over year (F46, F44, C15)."))
    assert {item["citation_id"] for item in result["mismatches"]} == {"F46", "F44", "C15"}


def test_unrelated_fact_label_still_mismatches():
    result = check_pm_citations(_nov_state("Revenue grew 39.87% year over year (F50, C15)."))
    assert [item["citation_id"] for item in result["mismatches"]] == ["F50"]


def test_prompt_only_label_resolves_to_fact_value():
    extra = {"prompt_evidence_references": {"fact-63": "F63"},
             "financial_evidence": {"facts": [{"fact_id": "fact-63", "value": "1071000000", "unit": "USD"}]}}
    result = check_pm_citations(_nov_state("Current assets were $1,071 million (F63).", **extra))
    assert result["unresolved_citations"] == [] and result["matched"] == 1
    wrong = check_pm_citations(_nov_state("Current assets were $900 million (F63).", **extra))
    assert [item["citation_id"] for item in wrong["mismatches"]] == ["F63"]


def test_disclosure_comparison_percentage_matches():
    state = _state("Revenue rose 6% (D1).", disclosure_evidence={"extraction": {"claims": [
        {"source_id": "guidance-source", "value": "321", "unit": "million",
         "comparison": {"quote": ", an increase of 6%", "value": "6", "unit": "%", "basis_locator": "block-35"}}]}})
    result = check_pm_citations(state)
    assert (result["matched"], result["mismatches"]) == (1, [])


def test_a_block_locator_inside_a_citation_is_not_a_figure_to_match():
    """Run 6cf38ab1: a definition cited as (D1/block-95) was counted as a mismatched figure."""
    state = _state("AI Customer ARR includes non-AI spending by customers using AI/ML (D1/block-95), so it is not "
                   "a measure of AI-product revenue.")
    state["canonical_financial_context"] = BRIEF.replace("- [C2]", "- [D1] guidance: 60 percent; source D1\n- [C2]")
    result = check_pm_citations(state)
    assert (result["matched"], result["checked"], result["citation_only_sentences"]) == (0, 0, 1)
    assert result["mismatches"] == []
    stated = check_pm_citations(_state("Revenue was $322.2 million (F46/block-12)."))
    assert (stated["matched"], stated["checked"]) == (0, 1)        # a real figure beside a locator is still checked


def test_a_loss_stated_as_a_positive_amount_matches_its_negative_canonical_value():
    """Run 9149f33b: 'net loss $42.609 million (F35)' was counted as a mismatch against -42609000."""
    brief = BRIEF.replace("- [C2]", "- [F35] Net Income: -42609000 USD; 2026-09-30; source S1\n- [C2]")
    loss = check_pm_citations({**_state("Q3 net loss was $42.609 million (F35)."), "canonical_financial_context": brief})
    assert (loss["matched"], loss["checked"]) == (1, 1)
    # Without a word that carries the sign, a positive figure for a negative fact is still a mismatch.
    gain = check_pm_citations({**_state("Q3 net income was $42.609 million (F35)."), "canonical_financial_context": brief})
    assert (gain["matched"], gain["checked"]) == (0, 1)
