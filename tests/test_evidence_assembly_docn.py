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
