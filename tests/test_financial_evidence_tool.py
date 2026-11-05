"""The analyst's bounded tool view includes the gate's verified filing facts."""

import json

import pytest

from tests.test_filing_facts import recorded_docn_filings
from tradingagents.agents import tools
from tradingagents.agents.evidence_validation import filing_accounting_evidence
from tradingagents.dataflows.financial_evidence import EvidencePackage


def setup(monkeypatch):
    disclosures = recorded_docn_filings()
    base = EvidencePackage(cik=disclosures.cik, as_of=disclosures.as_of)
    calls = []
    monkeypatch.setattr(tools, "build_financial_evidence", lambda ticker, cutoff: base)
    monkeypatch.setattr(
        tools,
        "build_filing_evidence",
        lambda ticker, cutoff: calls.append((ticker, cutoff)) or disclosures,
    )
    return base, disclosures, calls


def test_tool_borrowing_ids_match_gate_and_repeat_without_mutation(monkeypatch):
    base, disclosures, calls = setup(monkeypatch)
    result = tools.get_financial_evidence.func("DOCN", "2099-01-01", trade_date=str(base.as_of))
    shown = EvidencePackage.model_validate_json(result)
    gate, _, _ = filing_accounting_evidence(base, disclosures)
    expected = [f for f in gate.facts if f.metric == "Total Borrowings"]
    assert expected and all(f in shown.facts for f in expected)
    sources = {s.source_id: s for s in gate.sources}
    shown_sources = {s.source_id: s for s in shown.sources}
    assert all(shown_sources[sid] == sources[sid] for f in expected for sid in f.source_ids)
    assert calls == [("DOCN", str(base.as_of))]
    assert (
        tools.get_financial_evidence.func("DOCN", str(base.as_of), trade_date=str(base.as_of))
        == result
    )
    assert not base.facts and not base.sources
    again, _, _ = filing_accounting_evidence(shown, disclosures)
    assert all(f in again.facts for f in expected)
    assert len({f.fact_id for f in again.facts}) == len(again.facts)


@pytest.mark.parametrize("failure", ["provider", "cutoff", "issuer"])
def test_optional_supplement_failure_preserves_base_and_visible_warning(monkeypatch, failure):
    base, disclosures, _ = setup(monkeypatch)
    if failure == "provider":

        def unavailable(*args):
            raise RuntimeError("private-provider-url-or-token")

        monkeypatch.setattr(tools, "build_filing_evidence", unavailable)
    else:
        updates = {"as_of": "2026-10-19"} if failure == "cutoff" else {"cik": "0000320193"}
        # Change package-level identity only; gate must refuse the entire supplement.
        monkeypatch.setattr(
            tools, "build_filing_evidence", lambda *args: disclosures.model_copy(update=updates)
        )
    result = json.loads(
        tools.get_financial_evidence.func("DOCN", str(base.as_of), trade_date=str(base.as_of))
    )
    assert result["facts"] == [] and result["sources"] == []
    assert any("supplement unavailable" in warning.lower() for warning in result["warnings"])
    assert "private-provider-url" not in str(result)


def test_bounded_large_base_retains_new_verified_borrowing_metric(monkeypatch):
    base, disclosures, _ = setup(monkeypatch)
    extracted, _, _ = filing_accounting_evidence(base, disclosures)
    template = extracted.facts[0]
    facts = tuple(
        template.model_copy(
            update={"fact_id": f"base-{i}", "metric": f"Existing metric {i}", "locator": "x" * 1000}
        )
        for i in range(90)
    )
    package = base.model_copy(update={"facts": facts, "sources": extracted.sources})
    monkeypatch.setattr(tools, "build_financial_evidence", lambda *args: package)
    response = tools.get_financial_evidence.func(
        "DOCN", str(base.as_of), trade_date=str(base.as_of)
    )
    shown = EvidencePackage.model_validate_json(response)
    assert len(response) <= 64000
    assert any(f.metric == "Total Borrowings" for f in shown.facts)
    assert any("bounded tool view" in warning for warning in shown.warnings)
