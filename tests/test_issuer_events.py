"""Issuer disclosures supplement a news outage without becoming independent news."""
import json
from pathlib import Path

from langchain_core.messages import ToolMessage


def release():
    return json.loads(Path('tests/fixtures/docn_2026q3/release_context.json').read_text())['package']


def test_tool_coverage_keeps_empty_news_distinct_from_failed_optional_macro():
    from tradingagents.agents.issuer_events import news_tool_coverage
    messages = [ToolMessage(name='get_news', tool_call_id='1', content='No news found for DOCN between 2026-10-28 and 2026-11-04'),
                ToolMessage(name='get_macro_indicators', tool_call_id='2', content='DATA_UNAVAILABLE: optional macro_data could not be retrieved (FRED_API_KEY environment variable is not set).')]
    result = news_tool_coverage(messages)
    assert result['independent_news']['status'] == 'no_data'
    assert result['optional_macro']['status'] == 'unavailable'
    assert result['consensus']['status'] == 'not_retrieved'


def test_news_outage_reuses_eligible_release_without_certifying_document():
    from tradingagents.agents.issuer_events import issuer_supplement
    package = release()
    result = issuer_supplement({'independent_news': {'status': 'unavailable'}}, package,
                               cik=package['cik'], as_of=package['as_of'])
    assert result['coverage']['independent_news']['status'] == 'unavailable'
    assert result['coverage']['issuer_events']['status'] == 'retrieved_but_unvalidated'
    assert 'Issuer disclosures' in result['text']
    assert 'not independent reporting or consensus' in result['text']
    assert package['documents'][0]['url'] in result['text']
    assert result['events'][0]['content_hash'] == package['documents'][0]['content_hash']


def test_future_or_wrong_issuer_release_is_not_a_substitute():
    from tradingagents.agents.issuer_events import issuer_supplement
    package = release()
    for cik, as_of in [('0000000001', package['as_of']), (package['cik'], '2026-10-01')]:
        result = issuer_supplement({}, package, cik=cik, as_of=as_of)
        assert result['events'] == []
        assert result['coverage']['issuer_events']['status'] == 'unavailable'


def test_available_news_keeps_original_coverage_without_outage_supplement():
    from tradingagents.agents.issuer_events import issuer_supplement
    package = release()
    result = issuer_supplement({'independent_news': {'status': 'available'}}, package,
                               cik=package['cik'], as_of=package['as_of'])
    assert result['events']
    assert result['text'] == ''


def test_post_analyst_gate_adds_supplement_without_rewriting_news_prose():
    from datetime import date

    from tests.test_evidence_gate import complete_evidence
    from tradingagents.agents.context import get_instrument_context_from_state
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
    facts, accounting_docs = complete_evidence()  # synthetic accounting; real release metadata below
    actual = DisclosurePackage.model_validate(release())
    facts = facts.model_copy(update={'as_of': date(2026, 11, 4)})
    docs = actual.model_copy(update={'documents': (*accounting_docs.documents, *actual.documents),
                                    'selected_accessions': (*accounting_docs.selected_accessions, *actual.selected_accessions)})
    state = {'company_of_interest': 'DOCN', 'trade_date': '2026-11-04', 'fundamentals_report': '', 'news_report': 'Original analyst: news unavailable.',
             'news_coverage': {'independent_news': {'status': 'unavailable'}}}
    update = assess_financial_package(state, facts, docs)
    assert 'news_report' not in update
    assert 'Issuer disclosures' in get_instrument_context_from_state({**state, **update})
    assert update['issuer_event_evidence']['events']
    assert update['issuer_event_evidence']['coverage']['independent_news']['status'] == 'unavailable'
    assert update['financial_claim_validation']['raw_report'] == ''
