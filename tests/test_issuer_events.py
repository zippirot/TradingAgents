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


def test_atm_program_is_source_linked_authorization_never_issuance():
    from tradingagents.agents.issuer_events import issuer_supplement
    package = release()
    doc = package['documents'][0]
    doc['blocks'] = [dict(doc['blocks'][0], locator='block-31', text=(
        'On November 2, 2026, the Company entered into an equity distribution agreement '
        'to sell shares of common stock having an aggregate offering price of up to $1.0 billion '
        'from time to time through an “at-the-market” offering program.'))]
    result = issuer_supplement({'independent_news': {'status': 'available'}}, package,
                               cik=package['cik'], as_of=package['as_of'])
    record = result['financing_records'][0]
    assert record['type'] == 'at_the_market_program'
    assert record['event_date'] == '2026-11-02'
    assert record['authorized_amount'] == '1000000000.0'
    assert record['currency'] is None
    assert record['source_unit'] == '$'
    assert record['currency_source'] is None
    assert 'denomination unknown' in result['financing_text']
    assert 'None' not in result['financing_text']
    assert record['amount_comparator'] == 'up_to'
    assert record['issuance'] is None and record['remaining_capacity'] is None
    assert record['locator'] == 'block-31'
    assert record['content_hash'] == doc['content_hash']
    assert record['quote'] == doc['blocks'][0]['text']
    assert record['url'] == doc['url']
    assert 'does not establish issuance' in result['financing_text']
    # A future agreement date cannot create a record.
    doc['blocks'][0]['text'] = doc['blocks'][0]['text'].replace('November 2', 'November 5')
    assert not issuer_supplement({}, package, cik=package['cik'], as_of=package['as_of'])['financing_records']


def test_gate_keeps_model_and_deterministic_disclosure_results_separate():
    from datetime import date

    from tests.test_evidence_gate import complete_evidence
    from tradingagents.agents.evidence_validation import assess_financial_package
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
    facts, accounting = complete_evidence()
    actual = DisclosurePackage.model_validate(release())
    facts = facts.model_copy(update={'as_of': date(2026, 11, 4)})
    docs = actual.model_copy(update={'documents': (*accounting.documents, *actual.documents),
                                    'selected_accessions': (*accounting.selected_accessions, *actual.selected_accessions)})
    update = assess_financial_package({'fundamentals_report': '```disclosures\n[{"bad": true}]\n```'}, facts, docs)
    evidence = update['disclosure_evidence']
    assert evidence['submission_counts']['model_accepted'] == 0
    assert evidence['submission_counts']['model_rejected'] == 1
    assert evidence['submission_counts']['deterministic_accepted'] > 0
    assert evidence['model_extraction']['rejected'] == ['record 0: malformed disclosure record']
    assert evidence['deterministic_extraction']['claims']
    notices = [check for check in update['evidence_quality']['checks'] if check['code'].startswith('optional_disclosure_')]
    assert len(notices) == 1
    assert 'raw details retained in disclosure evidence' in notices[0]['message']
    assert 'malformed disclosure record' not in notices[0]['message']
    prepared = assess_financial_package({}, facts, docs, source_only=True)
    assert prepared['disclosure_evidence']['model_extraction'] is None
    assert prepared['disclosure_evidence']['submission_counts']['model_rejected'] is None
    assert prepared['issuer_event_evidence']['events']


def test_financing_requires_complete_explicit_authorization_not_model_prose():
    from tradingagents.agents.issuer_events import issuer_supplement
    package = release()
    doc = package['documents'][0]
    quote = ('On November 2, 2026, the Company entered into an equity distribution agreement '
             'to sell shares of common stock having an aggregate offering price of up to $1.0 billion '
             'from time to time through an “at-the-market” offering program.')
    original = doc['blocks'][0]
    for text in (quote.replace('up to ', ''), quote.replace('entered into', 'may enter into'),
                 quote.replace('1.0', '0'), quote.replace('November 2', 'November 32'),
                 quote.replace('at-the-market', 'underwritten')):
        doc['blocks'] = [dict(original, text=text)]
        assert not issuer_supplement({}, package, cik=package['cik'], as_of=package['as_of'])['financing_records']
    doc['blocks'] = [dict(original, text=quote, truncated=True)]
    assert not issuer_supplement({}, package, cik=package['cik'], as_of=package['as_of'])['financing_records']



def test_financing_currency_requires_explicit_local_denomination_statement():
    from tradingagents.agents.issuer_events import issuer_supplement
    package = release()
    doc = package['documents'][0]
    quote = ('On November 2, 2026, the Company entered into an equity distribution agreement '
             'to sell shares of common stock having an aggregate offering price of up to $1.0 billion '
             'from time to time through an “at-the-market” offering program.')
    original = doc['blocks'][0]
    for suffix, expected in (('', None), (' The company has U.S. dollar cash deposits.', None),
                             (' All dollar amounts in this agreement are in Canadian dollars.', 'CAD'),
                             (' All dollar amounts in this agreement are in U.S. dollars.', 'USD')):
        doc['blocks'] = [dict(original, text=quote + suffix)]
        result = issuer_supplement({}, package, cik=package['cik'], as_of=package['as_of'])
        record = result['financing_records'][0]
        assert record['currency'] == expected
        assert record['quote'] == quote + suffix
        if expected:
            assert record['currency_source']['locator'] == original['locator']
            assert record['currency_source']['quote'] == suffix.strip()
        else:
            assert record['currency_source'] is None
            assert 'denomination unknown' in result['financing_text']
