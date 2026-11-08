"""Recorded public DOCN source acceptance; no network, private state or models."""
import json
import random

from tests.docn_workflow_fixture import ROOT, source_bytes, source_json, source_state
from tradingagents.agents.context import build_shared_source_brief
from tradingagents.dataflows.disclosure_discovery import discover_disclosures


def test_recorded_source_fixture_hashes():
    for name in json.loads((ROOT / 'manifest.json').read_text())['source_files']:
        source_bytes(name)


def test_16416b7e_corpus_accepts_guided_shares_and_margin_guides():
    package = source_json('16416b7e-corpus.json.gz')
    result = discover_disclosures((package,))
    assert not result.rejected
    assert len(result.claims) == 15
    required = {
        ('Fully diluted weighted average shares outstanding', '128', '129'),
        ('Fully diluted weighted average shares outstanding', '122', '123'),
        ('Adjusted EBITDA margin', '42', '43'),
        ('Adjusted EBITDA margin', '41', '42'),
        ('Adjusted free cash flow margin', '20', '22'),
    }
    accepted = {(c.metric, str(c.value), str(c.upper_value)) for c in result.claims if c.kind == 'guidance'}
    assert required <= accepted


def test_discovery_is_order_independent():
    package = source_json('16416b7e-corpus.json.gz')
    expected = discover_disclosures((package,)).model_dump(mode='json')
    shuffle = random.Random(17)
    shuffle.shuffle(package['documents'])
    for doc in package['documents']:
        shuffle.shuffle(doc['blocks'])
    assert discover_disclosures((package,)).model_dump(mode='json') == expected


def test_brief_includes_retained_atm_8k():
    state = source_state()
    text = build_shared_source_brief(state)
    document = next(d for d in state['filing_evidence']['documents']
                    if any(b['locator'] == 'block-31' and 'equity distribution' in b['text'] for b in d['blocks']))
    assert 'Financing authorization' in text
    assert '1000000000' in text
    assert document['source_id'] in text
    assert '2026-11-03' in text
    assert 'does not establish issuance' in text


def test_brief_omits_financing_outside_window():
    state = source_state()
    for doc in state['filing_evidence']['documents']:
        doc['filing']['filed_date'] = '2026-11-08'
    assert 'Financing authorization' not in build_shared_source_brief(state)


def test_source_acquisition_grounds_full_retained_corpus_before_analysts():
    from tradingagents.agents.document_access import _scope
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.filing_search import corpus_hash
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    state = source_state()
    corpus = DisclosurePackage.model_validate(source_json('cfae95e9-corpus.json.gz'))
    state['document_sources'] = {**_scope(state), 'status': 'ready', 'cik': corpus.cik,
                                 'corpus': corpus.model_dump(mode='json'), 'corpus_hash': corpus_hash(corpus)}
    result = assess_financial_package(state, EvidencePackage.model_validate(state['financial_evidence']),
                                     DisclosurePackage.model_validate(state['filing_evidence']), source_only=True)
    extraction = result['disclosure_evidence']['deterministic_extraction']
    assert len(extraction['claims']) == 15
    assert not extraction['rejected']


def test_rpo_context_includes_year_ago_and_fiscal_year_end():
    from tests.test_retained_kpi_context import _state
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

    state = _state()
    brief = build_shared_source_brief(state)
    result = assess_financial_package(state, EvidencePackage.model_validate(state['financial_evidence']),
                                     DisclosurePackage.model_validate(state['filing_evidence']), source_only=True)
    for text in (brief, result['canonical_financial_context']):
        for fragment in ('$61 million', 'third quarter of 2025', '134,085,000 USD',
                         '893,828,000 USD', '799,707,000 USD', '345,111,000 USD',
                         'prior periods recast to include all contracts', 'sec-document-'):
            assert fragment in text
        assert 'Finance lease and equipment maturities (undiscounted, include imputed interest)' in text
        assert '2027 $250.0M' in text and 'present value $923.6M' in text
        assert 'Scheduled payments are not principal.' in text
    assert len(brief) <= 18000
