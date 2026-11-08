"""Duplicate retrieval paths must not change source grounding or hide conflicts."""
from datetime import date

import pytest

from tests.test_disclosure_context import blocks_for, recorded_claim, recorded_package
from tradingagents.dataflows.disclosure_evidence import validate_disclosure_claims


def check(packages):
    claim = recorded_claim(recorded_package())
    blocks = {key: text for package in packages for key, text in blocks_for(package).items()}
    return validate_disclosure_claims([claim], blocks, packages=packages)


def test_same_document_from_two_paths_is_one_source():
    package = recorded_package()
    result = check((package, package))
    assert result.claims == (recorded_claim(package),)
    assert result.rejected == ()


@pytest.mark.parametrize('field,value', [('accession', '0001582961-26-000999'), ('cik', '0000000002')])
def test_same_hash_conflicting_accession_rejected(field, value):
    package = recorded_package()
    doc = package.documents[0]
    other = doc.model_copy(update={'filing': doc.filing.model_copy(update={field: value})})
    result = check((package, package.model_copy(update={'documents': (other,)})))
    assert not result.claims
    assert 'conflicting document metadata' in result.rejected[0]


def test_same_identity_different_hash_rejected():
    package = recorded_package()
    other = package.documents[0].model_copy(update={'content_hash': 'f' * 64})
    result = check((package, package.model_copy(update={'documents': (other,)})))
    assert not result.claims
    assert 'conflicting document metadata' in result.rejected[0]


def test_bounded_and_full_blocks_merge_by_locator():
    package = recorded_package()
    doc = package.documents[0]
    bounded = package.model_copy(update={'documents': (doc.model_copy(update={'blocks': doc.blocks[:14]}),)})
    for packages in ((bounded, package), (package, bounded)):
        result = check(packages)
        assert result.claims == (recorded_claim(package),)
        assert not result.rejected


def test_conflicting_block_text_rejected():
    package = recorded_package()
    doc = package.documents[0]
    changed = tuple(b.model_copy(update={'text': b.text + ' changed'}) if b.locator == 'block-13' else b for b in doc.blocks)
    other = package.model_copy(update={'documents': (doc.model_copy(update={'blocks': changed}),)})
    result = check((other, package))
    assert not result.claims
    assert 'conflicting document metadata' in result.rejected[0]


def test_cutoff_and_issuer_checks_unchanged_after_dedupe():
    package = recorded_package()
    doc = package.documents[0]
    for change in ({'filed_date': date(2026, 11, 8)}, {'cik': '0000000002'}):
        invalid = package.model_copy(update={'documents': (doc.model_copy(update={'filing': doc.filing.model_copy(update=change)}),)})
        result = check((invalid, invalid))
        assert not result.claims
        assert 'issuer or filing cutoff mismatch' in result.rejected[0]


def test_conflicting_document_metadata_fails_gate_without_crashing():
    from tests.test_evidence_gate import complete_evidence
    from tradingagents.agents.evidence_validation import assess_financial_package

    facts, package = complete_evidence()
    document = package.documents[0]
    conflicting = document.model_copy(update={"content_hash": "f" * 64})
    package = package.model_copy(update={"documents": (document, conflicting)})
    result = assess_financial_package({"fundamentals_report": ""}, facts, package)
    assert result["final_rating"] == "REVIEW"
    integrity = next(c for c in result["evidence_quality"]["checks"] if c["code"] == "source_integrity")
    assert integrity["status"] == "fail"
    assert "conflicting document metadata" in integrity["message"]
