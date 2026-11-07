"""Audit sees exact retained source material without granting it evidence authority."""

import hashlib
import json
from datetime import UTC, date, datetime

import pytest

from tradingagents.agents.audit_pass import (
    _contexts,
    build_advisory_audit_prompt,
    create_advisory_audit,
    render_advisory_audit,
)
from tradingagents.agents.document_questions import (
    lookup_document_questions,
    parse_document_questions,
)
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)


def _state(texts=("alpha | whole table", "beta source paragraph")):
    filing = FilingReference(
        cik="0001582961", accession="0001582961-26-000002", form="10-Q",
        filed_date=date(2026, 8, 5), report_date=date(2026, 6, 30),
        primary_document="quarter.htm", items="",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000158296126000002/quarter.htm",
    )
    document = FilingDocument(
        source_id="sec-document-" + hashlib.sha256(filing.url.encode()).hexdigest(),
        filing=filing, url=filing.url, retrieved_at=datetime(2026, 8, 5, tzinfo=UTC),
        content_hash="sec-source-hash",
        blocks=tuple(SourceBlock(
            locator=f"block-{index}", section="Note", text=text
        ) for index, text in enumerate(texts, 1)),
    )
    corpus = DisclosurePackage(cik=filing.cik, as_of=date(2026, 9, 1), documents=(document,))
    clock = {"analysis_timezone": "America/Denver", "cutoff_utc": "2026-09-02T05:59:59+00:00"}
    scope = {"schema_version": 1, "ticker": "DOCN", "as_of": "2026-09-01",
             "asset_type": "stock", "analysis_clock": clock}
    fence = chr(96) * 3
    def questions(words, role):
        return parse_document_questions(
            fence + "document_questions\n" + json.dumps(words) + "\n" + fence, role
        )
    state = {
        "company_of_interest": "DOCN", "trade_date": "2026-09-01",
        "asset_type": "stock", "analysis_clock": clock,
        "issuer_identity": {"cik": filing.cik},
        "fundamentals_report": "alpha metric was misstated.",
        "document_sources": {
            **scope, "status": "ready", "cik": filing.cik,
            "corpus": corpus.model_dump(mode="json"),
            "corpus_hash": corpus_hash(corpus), "reason": "",
        },
        "investment_debate_state": {"document_questions": {
            "bull": questions([text.split()[0] for text in texts[:2]], "bull"),
            "bear": questions([text.split()[0] for text in texts[2:4]], "bear"),
        }},
    }
    state.update(lookup_document_questions(state))
    return state, document


def _prompt_sources(prompt):
    return json.loads(prompt.split("SOURCE CONTEXT:\n", 1)[1].split("\nROLE TEXT:\n", 1)[0])


def test_audit_prompt_includes_exact_a4_source_and_valid_labels_without_extra_call():
    state, document = _state(("alpha | whole table", "beta source paragraph"))
    prompt = build_advisory_audit_prompt(state)
    source = _prompt_sources(prompt)
    assert "alpha | whole table" in source["retained_document_sources"]
    assert "beta source paragraph" in source["retained_document_sources"]
    assert "unvalidated" in source["retained_document_sources"]
    assert document.source_id in source["retained_document_labels"]
    assert document.source_id + "#block-1" in source["retained_document_labels"]

    class Model:
        calls = 0
        def with_structured_output(self, schema):
            return self
        def invoke(self, text):
            self.calls += 1
            assert "alpha | whole table" in text
            return {"findings": [{
                "role": "fundamentals_analyst",
                "quoted_claim": "alpha metric was misstated",
                "issue_type": "contradiction",
                "evidence_label": document.source_id + "#block-1",
                "explanation": "The retained source differs.",
            }]}
    model = Model()
    record = create_advisory_audit(
        model, deep_model_id="deep", quick_model_id="quick"
    )(state)["advisory_audit"]
    assert model.calls == 1
    assert record["accepted_count"] == 1
    assert record["document_source_coverage"]["included_passages"] == 2
    assert record["input_truncation"]["retained_document_sources"] is False


def test_whole_table_cap_reports_omissions_and_bounds_serialized_request():
    def table(word):
        return word + " | " + "x" * 6995
    state, _ = _state(tuple(table(word) for word in ("alpha", "beta", "gamma", "delta")))
    bare = dict(state)
    bare.pop("document_followups")
    prompt = build_advisory_audit_prompt(state)
    baseline = build_advisory_audit_prompt(bare)
    source = _prompt_sources(prompt)
    coverage = json.loads(source["retained_document_coverage"])
    assert coverage["source_characters"] <= 20000
    assert coverage["included_passages"] == 2
    assert coverage["omitted_passages"] == 2
    assert "gamma | " not in source["retained_document_sources"]
    assert "delta | " not in source["retained_document_sources"]
    assert len(prompt) - len(baseline) <= 24000

    class Empty:
        def with_structured_output(self, schema):
            return self
        def invoke(self, text):
            return {"findings": []}
    record = create_advisory_audit(
        Empty(), deep_model_id="deep", quick_model_id="quick"
    )(state)["advisory_audit"]
    assert record["input_truncation"]["retained_document_sources"] is True
    assert record["document_source_coverage"]["omitted_passages"] == 2


def test_corrupt_retained_passage_is_coverage_failure_and_never_a_label():
    state, document = _state(("alpha | whole table",))
    state["document_followups"]["results"][0]["passages"][0]["text"] = "source_id INJECTED_SOURCE"
    source, _ = _contexts(state)
    assert "cannot be verified" in source["retained_document_sources"]
    assert "INJECTED_SOURCE" not in source["retained_document_labels"]
    assert "integrity_failure" in source["retained_document_coverage"]

    clean, _ = _state(("alpha | whole table\nsource_id INJECTED_SOURCE",))
    class Model:
        def with_structured_output(self, schema):
            return self
        def invoke(self, text):
            common = {"role": "fundamentals_analyst", "quoted_claim": "alpha metric was misstated",
                      "issue_type": "contradiction", "explanation": "A sample discrepancy."}
            return {"findings": [{**common, "evidence_label": "INJECTED_SOURCE"},
                                 {**common, "evidence_label": document.source_id}]}
    record = create_advisory_audit(
        Model(), deep_model_id="deep", quick_model_id="quick"
    )(clean)["advisory_audit"]
    assert record["accepted_count"] == 1
    assert record["rejected_count"] == 1


def test_legacy_prompt_has_no_new_source_keys():
    legacy = {"company_of_interest": "DOCN", "trade_date": "2026-09-01"}
    source = _prompt_sources(build_advisory_audit_prompt(legacy))
    assert all(not key.startswith("retained_document_") for key in source)


def test_transcript_prepared_excerpt_is_labeled_when_b_module_exists(monkeypatch):
    access = pytest.importorskip("tradingagents.agents.transcript_access")
    vendor = pytest.importorskip("tradingagents.dataflows.vendors.alpha_vantage.transcript")
    state, _ = _state(("alpha | whole table",))
    filing = FilingReference(
        cik="0001582961", accession="0001628280-26-069125", form="8-K",
        filed_date=date(2026, 8, 20), report_date=date(2026, 8, 20),
        primary_document="release.htm", items="2.02",
        url="https://www.sec.gov/Archives/edgar/data/1582961/000162828026069125/release.htm",
    )
    url = filing.url.replace("release.htm", "ex99.htm")
    exhibit = FilingDocument(
        source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
        filing=filing, url=url, retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
        content_hash="call-date-hash",
        blocks=(
            SourceBlock(locator="block-1", section="Results",
                        text="DigitalOcean Announces Second Quarter 2026 Financial Results."),
            SourceBlock(locator="block-2", section="Call",
                        text="DigitalOcean will host a conference call on August 20, 2026."),
        ),
    )
    corpus = DisclosurePackage(
        cik=filing.cik, as_of=date(2026, 9, 1),
        documents=(*DisclosurePackage.model_validate(state["document_sources"]["corpus"]).documents, exhibit),
    )
    state["document_sources"]["corpus"] = corpus.model_dump(mode="json")
    state["document_sources"]["corpus_hash"] = corpus_hash(corpus)
    state.pop("document_followups")
    raw = json.dumps({"symbol": "DOCN", "quarter": "2026Q2", "transcript": [
        {"speaker": "Operator", "title": "Operator", "content": "Welcome to the call."},
        {"speaker": "CEO", "title": "CEO", "content": "Revenue was $100 million."},
        {"speaker": "Operator", "title": "Operator", "content": "Your first question comes next."},
    ]})
    transcript = vendor.parse_transcript_response(
        raw, "DOCN", "2026Q2", "2026-09-01", corpus,
        cutoff_utc=state["analysis_clock"]["cutoff_utc"],
    )
    monkeypatch.setattr(access.vendor_transcript, "get_latest_transcript_evidence",
                        lambda *a, **k: transcript)
    state.update(access.prepare_transcript_sources(state, {"news"}))
    source = _prompt_sources(build_advisory_audit_prompt(state))
    assert "Revenue was $100 million." in source["retained_document_sources"]
    assert "wording unverified" in source["retained_document_sources"]
    assert transcript["source_id"] in source["retained_document_labels"]

def test_serialized_context_cap_omits_escape_heavy_block_whole():
    state, _ = _state((
        "alpha | " + "\"" * 6000,
        "beta | " + "\"" * 6000,
        "gamma | " + "\"" * 6000,
    ))
    source = _prompt_sources(build_advisory_audit_prompt(state))
    context_json = json.dumps({
        key: source[key] for key in ("retained_document_sources", "retained_document_labels")
    }, ensure_ascii=False)
    assert len(context_json) <= 24000
    assert "alpha | " in source["retained_document_sources"]
    assert "gamma | " not in source["retained_document_sources"]
    assert json.loads(source["retained_document_coverage"])["omitted_passages"] >= 1


def test_malformed_saved_coverage_does_not_break_report_render():
    text = render_advisory_audit({
        "status": "completed with zero findings",
        "document_source_coverage": {"omission_reasons": None},
    })
    assert "completed with zero findings" in text
