"""Deterministic disclosure coverage reaches the actual gate without forgiving bad proposals."""
import json
from datetime import date
from pathlib import Path

from tests.test_evidence_gate import complete_evidence
from tradingagents.agents.evidence_validation import assess_financial_package
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage


def test_recorded_outlooks_discovered_without_model_rows_and_lower_bound_labeled():
    facts, accounting = complete_evidence()
    release = DisclosurePackage.model_validate(json.loads(Path('tests/fixtures/docn_2026q3/release_context.json').read_text())['package'])
    facts = facts.model_copy(update={'as_of': date(2026, 11, 4)})
    docs = release.model_copy(update={'documents': (*accounting.documents, *release.documents),
                                      'selected_accessions': (*accounting.selected_accessions, *release.selected_accessions)})
    bad = {'source_id': release.documents[0].source_id, 'locator': 'block-40; block-41',
           'metric': 'Revenue', 'value': '348', 'upper_value': '351', 'unit': 'million',
           'period': 'Q4 2026', 'kind': 'guidance', 'quote': 'Revenue of $348 million to $351 million'}
    state = {'fundamentals_report': '```disclosures\n' + json.dumps([bad]) + '\n```'}
    update = assess_financial_package(state, facts, docs)
    extracted = update['disclosure_evidence']['extraction']
    assert extracted['rejected']
    assert any(c['kind'] == 'guidance' and c['locator'] == 'block-41' for c in extracted['claims'])
    assert any(c['comparator'] == 'at_least' for c in extracted['claims'])
    assert '≥60' in update['canonical_financial_context']
    assert 'not an exact forecast' in update['canonical_financial_context']


def test_authentic_second_issuer_fiscal_outlook_keeps_tolerance_and_assumption():
    from tradingagents.dataflows.financial_evidence import EvidencePackage
    raw = json.loads(Path('tests/fixtures/nvda_2027q2/release_context.json').read_text())
    docs = DisclosurePackage.model_validate(raw['package'])
    # This isolates actual release acceptance; absent core statements still REVIEW.
    result = assess_financial_package({'fundamentals_report': ''},
                                     EvidencePackage(cik=docs.cik, as_of=docs.as_of), docs)
    assert result['final_rating'] == 'REVIEW'
    claims = result['disclosure_evidence']['extraction']['claims']
    revenue = next(c for c in claims if c['metric'] == 'Revenue')
    assert revenue['comparator'] == 'central_estimate'
    assert revenue['tolerance_percent'] == '2'
    assert revenue['period'] == 'third quarter of fiscal 2027'
    assert 'China' in revenue['quote']
    assert '±2%' in result['canonical_financial_context']
