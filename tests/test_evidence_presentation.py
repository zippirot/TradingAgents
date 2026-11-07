"""Readable evidence projections preserve the exact source records."""

import hashlib
from decimal import Decimal

from tests.test_evidence_gate import complete_evidence
from tradingagents.agents.evidence_validation import canonical_accounting_context
from tradingagents.agents.output_validation import enforce_publication


def _package():
    package, _ = complete_evidence()
    ids = {f.fact_id: hashlib.sha256(f.fact_id.encode()).hexdigest() for f in package.facts}
    sources = {s.source_id: "sec-" + hashlib.sha256(s.source_id.encode()).hexdigest() for s in package.sources}
    return package.model_copy(update={
        "facts": tuple(f.model_copy(update={
            "fact_id": ids[f.fact_id],
            "source_ids": tuple(sources[s] for s in f.source_ids),
            "input_fact_ids": tuple(ids[i] for i in f.input_fact_ids),
        }) for f in package.facts),
        "sources": tuple(s.model_copy(update={"source_id": sources[s.source_id]}) for s in package.sources),
    })


def test_brief_contains_core_values_with_single_exact_reference_index():
    package = _package()
    rendered = canonical_accounting_context(package, [])
    revenue = next(f for f in package.facts if f.metric == "Revenue")
    assert "Accepted evidence brief" in rendered
    assert "Revenue" in rendered
    assert str(revenue.value) in rendered
    assert rendered.count(revenue.fact_id) == 1
    assert "Evidence reference appendix" in rendered
    for source in package.sources:
        assert rendered.count(source.source_id) <= 1


def test_conflicting_core_facts_are_not_silently_selected():
    package = _package()
    revenue = next(f for f in package.facts if f.metric == "Revenue")
    conflicting = revenue.model_copy(update={
        "fact_id": hashlib.sha256(b"conflicting revenue").hexdigest(),
        "value": revenue.value + Decimal("1000000"),
    })
    package = package.model_copy(update={"facts": (*package.facts, conflicting)})
    rendered = canonical_accounting_context(package, [])
    assert "conflicting values or incompatible source bases" in rendered
    assert revenue.fact_id not in rendered
    assert conflicting.fact_id not in rendered


def test_published_decision_retains_values_without_hash_index():
    package = _package()
    canonical = canonical_accounting_context(package, [])
    state = {
        "company_of_interest": "DOCN",
        "evidence_quality": {"status": "limited"},
        "canonical_financial_context": canonical,
        "financial_evidence": package.model_dump(mode="json"),
        "final_trade_decision": "**Rating**: Hold",
    }
    result = enforce_publication(state)
    assert "Revenue" in result["final_trade_decision"]
    assert "Evidence reference appendix" not in result["final_trade_decision"]
    for fact in package.facts:
        assert fact.fact_id not in result["final_trade_decision"]
    assert state["canonical_financial_context"] == canonical


def test_report_has_one_reference_appendix_and_memory_keeps_readable_decision(tmp_path):
    from tradingagents.memory import TradingMemoryLog
    from tradingagents.reporting import evidence_appendix, prepare_report_state, write_report_tree

    package = _package()
    state = {
        "company_of_interest": "DOCN",
        "evidence_quality": {"status": "limited"},
        "canonical_financial_context": canonical_accounting_context(package, []),
        "financial_evidence": package.model_dump(mode="json"),
        "final_trade_decision": "**Rating**: Hold",
        "financial_claim_validation": {
            "raw_report": 'Research hypothesis.\n```financial_claims\n[{"fact_id":"untrusted-row"}]\n```',
        },
    }
    published = {**state, **enforce_publication(state)}
    rendered = prepare_report_state(published)
    assert "Research hypothesis." in rendered["fundamentals_report"]
    assert "untrusted-row" not in rendered["fundamentals_report"]
    assert "untrusted-row" in published["financial_claim_validation"]["raw_report"]
    saved = write_report_tree(published, "DOCN", tmp_path / "reports")
    report_text = saved.read_text()
    assert report_text.count("### Evidence reference appendix") == 1
    # This prepared report has no risk debate, so evidence is the fifth section.
    assert report_text.splitlines().count("## V. Evidence and Quality") == 1
    assert prepare_report_state(published) == rendered
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
    log.store_decision("DOCN", "2026-11-04", published["final_trade_decision"])
    decision = log.load_entries()[0]["decision"]
    assert "Revenue" in decision
    assert "Evidence reference appendix" not in decision
    for fact in package.facts:
        assert fact.fact_id not in decision
    assert all(source.source_id in evidence_appendix(rendered) for source in package.sources)


def test_legacy_memory_hashes_are_compact_only_in_prompt_view(tmp_path):
    from tradingagents.memory import TradingMemoryLog

    path = tmp_path / "legacy.md"
    log = TradingMemoryLog({"memory_log_path": str(path)})
    ident = hashlib.sha256(b"legacy fact").hexdigest()
    decision = f"Rating: Hold\nRevenue: 100 USD; fact {ident}; source sec-document-{ident}."
    log.store_decision("DOCN", "2026-10-19", decision)
    log.update_with_outcome("DOCN", "2026-10-19", .02, .01, 5, "Short-window observation", resolution_date="2026-10-27")
    before = path.read_bytes()
    context = log.get_past_context("DOCN", as_of="2026-11-04")
    assert ident not in context
    assert "Revenue: 100 USD" in context
    assert "Short-window observation" in context
    assert "original memory record" in context
    assert log.load_entries()[0]["decision"] == decision
    assert path.read_bytes() == before


def test_source_rejection_warning_keeps_reason_and_locator_without_repeated_hash():
    from tradingagents.agents.evidence_presentation import (
        REFERENCE_END,
        REFERENCE_START,
        readable_evidence,
    )

    source_id = "sec-document-" + hashlib.sha256(b"release").hexdigest()
    context = (
        "Accepted evidence brief\nRevenue: 321 million USD"
        + REFERENCE_START + f"### Evidence reference appendix\n- D1: source_id {source_id}; https://www.sec.gov/release.htm"
        + REFERENCE_END
        + f"\nrecord 2: missing source-linked context ({source_id}, block-17)"
    )
    rendered = readable_evidence(context)
    assert "record 2: missing source-linked context (D1, block-17)" in rendered
    assert source_id not in rendered
    assert source_id in context
