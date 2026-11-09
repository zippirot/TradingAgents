"""Located source numbers become coverage notes, never canonical fact acceptance."""

import hashlib
import json
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from tests.test_advisory_audit import FakeModel
from tests.test_audit_source_coverage import _state
from tests.test_portfolio_valuation import decision, state as portfolio_state
from tradingagents.agents.audit_pass import (
    create_advisory_audit,
    prepare_audit_dispositions,
    render_advisory_audit,
)
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.transcript_access import prepare_transcript_sources
from tradingagents.dataflows.filing_search import corpus_hash
from tradingagents.dataflows.vendors.alpha_vantage import transcript as vendor_transcript
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)


def _audit(text, *, quote='The induced conversion expense was $57.1M.', issue='unsupported_claim'):
    state, document = _state((text,))
    state.pop('document_followups', None)
    state['fundamentals_report'] = quote
    finding = {'role': 'fundamentals_analyst', 'quoted_claim': quote,
               'issue_type': issue, 'evidence_label': None,
               'explanation': 'No support in the bounded brief.'}
    record = create_advisory_audit(FakeModel({'findings': [finding]}),
                                   deep_model_id='d', quick_model_id='q')(state)['advisory_audit']
    return state, document, record


def test_unsupported_finding_located_in_full_10q_is_relabelled():
    state, document, record = _audit(
        'Amounts in thousands. Total induced conversion expense of $ 57,110.')
    found = record['findings'][0]
    assert found['issue_type'] == 'unsupported_claim'
    assert found['classification'] == 'located_in_retained_source'
    assert found['original_classification'] == 'unsupported_claim'
    assert found['source_location'] == {'source_id': document.source_id, 'locator': 'block-1'}
    assert 'not in the evidence brief' in found['coverage_note']
    assert record['located_source_count'] == 1
    assert record['counts_by_type']['unsupported_claim'] == 0
    assert record['accepted_count'] == 1
    projected = prepare_audit_dispositions({**state, 'advisory_audit': record})
    assert projected['findings'][0]['finding_id'] == found['finding_id']
    assert projected['findings'][0]['coverage_note'] == found['coverage_note']
    rendered = render_advisory_audit(record, dispositions=projected)
    assert 'located in retained source' in rendered.lower()
    assert 'unsupported claim 0' in rendered.lower()
    assert 'Located-source coverage notes: 1' in rendered
    assert document.source_id in rendered and 'unsupported claim' not in rendered.splitlines()[-1].lower()


def test_located_source_note_reaches_portfolio_manager_prompt():
    _, document, record = _audit('Amounts in thousands. Total induced conversion expense of $ 57,110.')
    value = portfolio_state()
    value['advisory_audit'] = record
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = decision()
    create_portfolio_manager(llm)(value)
    prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
    assert 'located in retained source' in prompt.lower()
    assert document.source_id in prompt
    assert record['findings'][0]['finding_id'] in prompt


def test_absent_amount_or_no_shared_word_stays_unsupported():
    _, _, absent = _audit('Amounts in thousands. Induced conversion expense of $ 50,000.')
    assert 'classification' not in absent['findings'][0]
    assert absent['counts_by_type']['unsupported_claim'] == 1
    _, _, unrelated = _audit('Amounts in thousands. Revenue was $ 57,110.')
    assert 'classification' not in unrelated['findings'][0]


def test_contradiction_is_not_relabelled_even_when_amount_is_located():
    _, _, record = _audit('Amounts in thousands. Total induced conversion expense of $ 57,110.',
                          issue='contradiction')
    assert record['findings'][0]['issue_type'] == 'contradiction'
    assert 'classification' not in record['findings'][0]


def test_tampered_corpus_cannot_relabel_claim():
    state, _ = _state(('Amounts in thousands. Induced conversion expense of $ 57,110.',))
    state.pop('document_followups', None)
    state['document_sources']['corpus']['documents'][0]['blocks'][0]['text'] += ' tampered'
    quote = 'The induced conversion expense was $57.1M.'
    state['fundamentals_report'] = quote
    finding = {'role': 'fundamentals_analyst', 'quoted_claim': quote,
               'issue_type': 'unsupported_claim', 'evidence_label': None,
               'explanation': 'Unverified.'}
    record = create_advisory_audit(FakeModel({'findings': [finding]}),
                                   deep_model_id='d', quick_model_id='q')(state)['advisory_audit']
    assert record['accepted_count'] == 1
    assert 'classification' not in record['findings'][0]


def test_amount_in_validated_full_transcript_is_coverage_note(monkeypatch):
    state, _ = _state(('Other filing text.',))
    filing = FilingReference(
        cik='0001582961', accession='0001628280-26-069125', form='8-K',
        filed_date=date(2026, 8, 20), report_date=date(2026, 8, 20),
        primary_document='release.htm', items='2.02',
        url='https://www.sec.gov/Archives/edgar/data/1582961/000162828026069125/release.htm')
    url = filing.url.replace('release.htm', 'ex99.htm')
    exhibit = FilingDocument(
        source_id='sec-document-' + hashlib.sha256(url.encode()).hexdigest(),
        filing=filing, url=url, retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
        content_hash='call-date-hash', blocks=(
            SourceBlock(locator='block-1', section='Results',
                        text='DigitalOcean Announces Second Quarter 2026 Financial Results.'),
            SourceBlock(locator='block-2', section='Call',
                        text='DigitalOcean will host a conference call on August 20, 2026.'),
        ))
    corpus = DisclosurePackage(
        cik=filing.cik, as_of=date(2026, 9, 1),
        documents=(*DisclosurePackage.model_validate(state['document_sources']['corpus']).documents, exhibit))
    state['document_sources']['corpus'] = corpus.model_dump(mode='json')
    state['document_sources']['corpus_hash'] = corpus_hash(corpus)
    state.pop('document_followups', None)
    raw = json.dumps({'symbol': 'DOCN', 'quarter': '2026Q2', 'transcript': [
        {'speaker': 'Operator', 'title': 'Operator', 'content': 'Welcome to the call.'},
        {'speaker': 'CEO', 'title': 'CEO',
         'content': 'The induced conversion expense was 57.1 million dollars.'},
        {'speaker': 'Operator', 'title': 'Operator',
         'content': 'Your first question comes next.'},
    ]})
    transcript = vendor_transcript.parse_transcript_response(
        raw, 'DOCN', '2026Q2', '2026-09-01', corpus,
        cutoff_utc=state['analysis_clock']['cutoff_utc'])
    monkeypatch.setattr('tradingagents.agents.transcript_access.vendor_transcript.get_latest_transcript_evidence',
                        lambda *a, **k: transcript)
    state.update(prepare_transcript_sources(state, {'news'}))
    quote = 'The induced conversion expense was $57.1M.'
    state['fundamentals_report'] = quote
    finding = {'role': 'fundamentals_analyst', 'quoted_claim': quote,
               'issue_type': 'unsupported_claim', 'evidence_label': None,
               'explanation': 'Not in the bounded brief.'}
    record = create_advisory_audit(FakeModel({'findings': [finding]}),
                                   deep_model_id='d', quick_model_id='q')(state)['advisory_audit']
    assert record['findings'][0]['classification'] == 'located_in_retained_source'
    assert record['findings'][0]['source_location'] == {
        'source_id': transcript['source_id'], 'locator': 'turn-2'}
