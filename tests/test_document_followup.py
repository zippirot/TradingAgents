import hashlib
from datetime import UTC, date, datetime

import pytest

from tradingagents.agents.document_questions import (
    document_followup_context,
    document_question_instruction,
    lookup_document_questions,
    parse_document_questions,
    render_document_followups,
)
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)


def state_with_corpus():
    filing = FilingReference(
        cik="0001582961", accession="0001582961-26-000002", form="10-Q",
        filed_date=date(2026, 8, 5), report_date=date(2026, 6, 30),
        primary_document="quarter.htm", items="",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000158296126000002/quarter.htm",
    )
    document = FilingDocument(
        source_id="sec-document-" + hashlib.sha256(filing.url.encode()).hexdigest(),
        filing=filing, url=filing.url, retrieved_at=datetime(2026, 8, 5, tzinfo=UTC),
        content_hash="source-abc",
        blocks=(
            SourceBlock(locator="block-1", section="Leases", text="Lease commitments not yet commenced."),
            SourceBlock(locator="block-2", section="RPO", text="Remaining performance obligations: 12 months $100."),
        ),
    )
    corpus = DisclosurePackage(
        cik=filing.cik, as_of=date(2026, 9, 1), documents=(document,),
    )
    scope = {
        "schema_version": 1, "ticker": "DOCN", "as_of": "2026-09-01",
        "asset_type": "stock", "analysis_clock": {"cutoff_utc": "2026-09-02T00:00:00+00:00"},
    }
    return {
        "company_of_interest": "DOCN", "trade_date": "2026-09-01",
        "asset_type": "stock", "analysis_clock": scope["analysis_clock"],
        "issuer_identity": {"cik": filing.cik},
        "document_sources": {
            **scope, "status": "ready", "cik": filing.cik,
            "corpus": corpus.model_dump(mode="json"), "corpus_hash": corpus_hash(corpus),
            "reason": "",
        },
        "investment_debate_state": {
            "document_questions": {
                "bull": parse_document_questions(
                    'Final case.\n```document_questions\n["lease commitments"]\n```', "bull"
                ),
                "bear": parse_document_questions(
                    '```document_questions\n["RPO 12 months", "customer utilization"]\n```',
                    "bear",
                ),
            }
        },
    }


def test_instruction_only_on_stock_final_turn():
    assert not document_question_instruction({"asset_type": "crypto", "_document_question_final_turn": True})
    assert not document_question_instruction({"asset_type": "stock", "_document_question_final_turn": False})
    text = document_question_instruction({"asset_type": "stock", "_document_question_final_turn": True})
    assert "document_questions" in text
    assert "two" in text.lower()


def test_parser_bounds_and_rejects_duplicate_or_malformed_fences():
    parsed = parse_document_questions(
        '```document_questions\n["leases", "RPO", "extra"]\n```', "bull"
    )
    assert [q["query"] for q in parsed["questions"]] == ["leases", "RPO"]
    assert parsed["rejected"]
    assert parse_document_questions("no fence", "bear")["status"] == "missing"
    duplicate = '```document_questions\n["a"]\n```\n```document_questions\n["b"]\n```'
    assert parse_document_questions(duplicate, "bear")["status"] == "malformed"
    assert not parse_document_questions(duplicate, "bear")["questions"]
    assert parse_document_questions('```document_questions\n{"q":"lease"}\n```', "bull")["status"] == "malformed"


def test_lookup_retains_exact_passages_and_not_found_distinction():
    state = state_with_corpus()
    update = lookup_document_questions(state)
    record = update["document_followups"]
    assert len(record["results"]) == 3
    assert record["corpus_hash"] == state["document_sources"]["corpus_hash"]
    lease = record["results"][0]
    assert lease["status"] == "found"
    assert lease["passages"][0]["citation_ref"] == lease["passages"][0]["source_id"] + "#block-1"
    assert record["results"][2]["status"] == "not_found"
    assert record["results"][2]["reason"] == "not found in retained filings"
    assert sum(len(p["text"]) for r in record["results"] for p in r["passages"]) <= 4 * 12000


def test_resume_reuses_snapshot_and_detects_passage_or_corpus_tamper():
    state = state_with_corpus()
    state.update(lookup_document_questions(state))
    assert lookup_document_questions(state) == {}
    state["document_followups"]["results"][0]["passages"][0]["text"] = "altered"
    with pytest.raises(ValueError, match="follow-up|passage"):
        lookup_document_questions(state)
    state = state_with_corpus()
    state.update(lookup_document_questions(state))
    state["document_sources"]["corpus"]["documents"][0]["blocks"][0]["text"] = "altered"
    with pytest.raises(ValueError, match="corpus"):
        lookup_document_questions(state)


def test_context_and_report_require_actual_pm_reference():
    state = state_with_corpus()
    state.update(lookup_document_questions(state))
    context = document_followup_context(state)
    ref = state["document_followups"]["results"][0]["passages"][0]["citation_ref"]
    assert "UNTRUSTED" in context
    assert "not accepted evidence" in context
    assert ref in context
    assert "not found in retained filings" in context
    unresolved = render_document_followups(state, "No citation")
    assert 'source passages retrieved; final-decision citation not verified.' in unresolved
    assert ref not in unresolved
    cited = render_document_followups(state, "I considered " + ref)
    assert ref in cited
    assert "cited" in cited
    assert "not found in retained filings" in cited

def test_lookup_unavailable_source_and_legacy_no_questions():
    state = state_with_corpus()
    del state["document_sources"]
    record = lookup_document_questions(state)["document_followups"]
    assert all(result["status"] == "unavailable" for result in record["results"])
    assert all(not result["passages"] for result in record["results"])
    assert "unavailable" in render_document_followups({**state, "document_followups": record})
    legacy = {key: value for key, value in state.items() if key != "investment_debate_state"}
    assert lookup_document_questions(legacy) == {}
    assert document_followup_context(legacy) == ""


def test_parser_rejects_overlong_and_duplicate_queries():
    parsed = parse_document_questions(
        '```document_questions\n' +
        '["' + "x" * 201 + '", "lease", "LEASE"]\n```',
        "bull",
    )
    assert [question["query"] for question in parsed["questions"]] == ["lease"]
    assert any("200" in rejected for rejected in parsed["rejected"])
    assert any("duplicate" in rejected for rejected in parsed["rejected"])


def test_resume_detects_question_set_change_without_new_search():
    state = state_with_corpus()
    state.update(lookup_document_questions(state))
    state["investment_debate_state"]["document_questions"]["bull"]["questions"][0]["query"] = "changed"
    with pytest.raises(ValueError, match="questions"):
        lookup_document_questions(state)


def test_named_note_no_match_reason_is_visible_in_followup_report():
    state = state_with_corpus()
    state["investment_debate_state"]["document_questions"]["bull"] = parse_document_questions(
        '```document_questions\n["How will the 2026 Convertible Notes settle?"]\n```', "bull"
    )
    state["investment_debate_state"]["document_questions"]["bear"] = parse_document_questions(
        '```document_questions\n[]\n```', "bear"
    )
    state.update(lookup_document_questions(state))
    result = state["document_followups"]["results"][0]
    assert result["status"] == "not_found"
    assert "no passage names the 2026 Convertible Notes" in result["reason"]
    assert "no passage names the 2026 Convertible Notes" in render_document_followups(state)


def test_partial_named_note_coverage_is_visible_even_with_a_found_passage():
    state = state_with_corpus()
    state["document_sources"]["corpus"]["documents"][0]["blocks"].append({
        "locator": "block-3", "section": "Notes", "text": "The 2030 Convertible Notes affect diluted shares.",
        "truncated": False, "currency": None, "currency_locator": None,
    })
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    state["document_sources"]["corpus_hash"] = corpus_hash(
        DisclosurePackage.model_validate(state["document_sources"]["corpus"])
    )
    state["investment_debate_state"]["document_questions"]["bull"] = parse_document_questions(
        '```document_questions\n["Which 2026 and 2030 Convertible Notes affect diluted shares?"]\n```', "bull"
    )
    state["investment_debate_state"]["document_questions"]["bear"] = parse_document_questions(
        '```document_questions\n[]\n```', "bear"
    )
    state.update(lookup_document_questions(state))
    result = state["document_followups"]["results"][0]
    assert result["status"] == "found"
    assert "no passage names the 2026 Convertible Notes" in result["gaps"]
    assert "no passage names the 2026 Convertible Notes" in render_document_followups(state)
    assert "no passage names the 2026 Convertible Notes" in document_followup_context(state)


@pytest.mark.parametrize("truncated", [False, True])
def test_partial_named_note_omission_is_visible_without_claiming_absence(truncated):
    state = state_with_corpus()
    state["document_sources"]["corpus"]["documents"][0]["blocks"].extend((
        {"locator": "block-3", "section": "Notes", "text": "The 2030 Convertible Notes affect diluted shares.",
         "truncated": False, "currency": None, "currency_locator": None},
        {"locator": "block-4", "section": "Notes", "text": "The 2026 Convertible Notes " + "x" * 12000,
         "truncated": truncated, "currency": None, "currency_locator": None},
    ))
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    state["document_sources"]["corpus_hash"] = corpus_hash(
        DisclosurePackage.model_validate(state["document_sources"]["corpus"])
    )
    state["investment_debate_state"]["document_questions"]["bull"] = parse_document_questions(
        '```document_questions\n["Which 2026 and 2030 Convertible Notes affect diluted shares?"]\n```', "bull"
    )
    state["investment_debate_state"]["document_questions"]["bear"] = parse_document_questions(
        '```document_questions\n[]\n```', "bear"
    )
    state.update(lookup_document_questions(state))
    result = state["document_followups"]["results"][0]
    assert result["status"] == "found"
    expected = "incomplete source block omitted" if truncated else "passage omitted by search size limit"
    assert f"2026 Convertible Notes: {expected}" in result["gaps"]
    assert f"2026 Convertible Notes: {expected}" in render_document_followups(state)
    assert f"2026 Convertible Notes: {expected}" in document_followup_context(state)
    assert "no passage names the 2026 Convertible Notes" not in result["gaps"]
