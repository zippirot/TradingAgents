import hashlib
import json
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


def _queries(state, bull, bear):
    for role, values in (("bull", bull), ("bear", bear)):
        state["investment_debate_state"]["document_questions"][role] = parse_document_questions(
            "```document_questions\n" + json.dumps(values) + "\n```", role,
        )


def test_unrelated_passages_are_not_reported_as_relevant():
    state = state_with_corpus()
    _queries(state, ["remaining performance obligations customer utilization"], ["RPO 12 months"])
    state.update(lookup_document_questions(state))
    first, second = state["document_followups"]["results"]
    assert first["passages"]  # diagnostic partial matches are retained, not called relevant
    assert first["status"] == "no_relevant_passage"
    assert second["status"] == "relevant_passages_found"


def test_retrieval_never_reports_answered():
    state = state_with_corpus()
    state.update(lookup_document_questions(state))
    assert {r["status"] for r in state["document_followups"]["results"]} == {
        "relevant_passages_found", "no_relevant_passage",
    }
    card = render_document_followups(state)
    assert "Retrieval: relevant_passages_found" in card
    assert "Retrieval: no_relevant_passage" in card
    assert "RM answer judgment unavailable" in card
    assert "answered" not in card
    context = document_followup_context(state)
    assert "Retrieval: relevant_passages_found" in context
    assert "Retrieval: no_relevant_passage" in context
    assert "not that a question was answered" in context


def test_card_shows_retrieval_status_without_rm_judgment():
    from tradingagents.reporting import _report_parts

    state = state_with_corpus()
    state.update(lookup_document_questions(state))
    state["final_trade_decision"] = "Hold; source interpretation remains unvalidated."
    portfolio = next(part for part in _report_parts(state) if part[1] == "5_portfolio")
    text = "\n".join(row[2] for row in portfolio[2])
    assert "relevant_passages_found" in text and "no_relevant_passage" in text
    assert "RM answer judgment unavailable" in text
    assert "passage(s)" not in text and "passages retrieved" not in text


def test_duplicate_rpo_questions_use_one_slot(monkeypatch):
    import tradingagents.agents.document_questions as module

    state = state_with_corpus()
    _queries(state, ["What does RPO say for the next 12 months?"],
             ["What do remaining performance obligations say for the next 12 months?"])
    calls = []
    search = module.search_retained_document_sources
    def capture(*args, **kwargs):
        calls.append(args[1])
        return search(*args, **kwargs)
    monkeypatch.setattr(module, "search_retained_document_sources", capture)
    state.update(lookup_document_questions(state))
    assert len(calls) == 1
    results = state["document_followups"]["results"]
    assert [r["question_id"] for r in results] == ["bull-1", "bear-1"]
    assert results[1]["duplicate_of"] == "bull-1"
    assert results[0]["passages"] == results[1]["passages"]
    assert lookup_document_questions(state) == {}


def test_followup_context_has_no_repeated_passage():
    state = state_with_corpus()
    _queries(state, ["RPO"], ["remaining performance obligations 12 months"])
    state.update(lookup_document_questions(state))
    text = document_followup_context(state)
    assert text.count("Remaining performance obligations: 12 months $100.") == 1
    assert "bull-1" in text and "bear-1" in text


def test_opposite_or_different_instrument_questions_do_not_share_lookup(monkeypatch):
    import tradingagents.agents.document_questions as module

    state = state_with_corpus()
    _queries(state, ["finance leases commenced", "2026 Convertible Notes"],
             ["finance leases not yet commenced", "2030 Convertible Notes"])
    calls = []
    search = module.search_retained_document_sources
    def capture(*args, **kwargs):
        calls.append(args[1])
        return search(*args, **kwargs)
    monkeypatch.setattr(module, "search_retained_document_sources", capture)
    state.update(lookup_document_questions(state))
    assert len(calls) == 4
    assert all(r["duplicate_of"] is None for r in state["document_followups"]["results"])


def test_relevance_is_revalidated_even_after_record_is_resealed():
    from tradingagents.agents.document_questions import _digest

    state = state_with_corpus()
    _queries(state, ["RPO customer utilization"], [])
    state.update(lookup_document_questions(state))
    record = state["document_followups"]
    record["results"][0]["status"] = "relevant_passages_found"
    record["record_hash"] = _digest({k: v for k, v in record.items() if k != "record_hash"})
    with pytest.raises(ValueError, match="relevance|status"):
        lookup_document_questions(state)


def test_legacy_snapshot_is_reused_without_rewriting_or_inventing_relevance():
    from tradingagents.agents.document_questions import _digest

    state = state_with_corpus()
    state.update(lookup_document_questions(state))
    record = state["document_followups"]
    record["schema_version"] = 1
    for result in record["results"]:
        result.pop("lookup_query")
        result.pop("duplicate_of")
        result["status"] = "found" if result["passages"] else "not_found"
    record["record_hash"] = _digest({k: v for k, v in record.items() if k != "record_hash"})
    before = json.dumps(record, sort_keys=True)
    assert lookup_document_questions(state) == {}
    assert "legacy_relevance_not_assessed" in render_document_followups(state)
    assert "relevant_passages_found" not in render_document_followups(state)
    assert json.dumps(record, sort_keys=True) == before


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
    assert lease["status"] == "relevant_passages_found"
    assert lease["passages"][0]["citation_ref"] == lease["passages"][0]["source_id"] + "#block-1"
    assert record["results"][2]["status"] == "no_relevant_passage"
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
    assert "final-decision citation not verified." in unresolved
    assert "RM answer judgment unavailable" in unresolved
    assert ref not in unresolved
    cited = render_document_followups(state, "I considered " + ref)
    assert ref in cited
    assert "Cited in final decision" in cited
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
    assert result["status"] == "no_relevant_passage"
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
    assert result["status"] == "no_relevant_passage"
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
    assert result["status"] == "no_relevant_passage"
    expected = "incomplete source block omitted" if truncated else "passage omitted by search size limit"
    assert f"2026 Convertible Notes: {expected}" in result["gaps"]
    assert f"2026 Convertible Notes: {expected}" in render_document_followups(state)
    assert f"2026 Convertible Notes: {expected}" in document_followup_context(state)
    assert "no passage names the 2026 Convertible Notes" not in result["gaps"]
