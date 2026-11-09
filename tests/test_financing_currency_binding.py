"""A dollar symbol needs explicit currency evidence in the same filed accession."""
from copy import deepcopy

import pytest

from tests.docn_workflow_fixture import source_json
from tradingagents.agents.issuer_events import issuer_supplement


def package():
    return source_json('cfae95e9-bounded.json.gz')


def atm(package):
    return next(d for d in package['documents'] if any('equity distribution agreement' in b['text'] for b in d['blocks']))


def records(package):
    return issuer_supplement({}, package, cik=package['cik'], as_of=package['as_of'])['financing_records']


def binding(document, *, xbrl=True):
    block = deepcopy(document['blocks'][0])
    block.update(locator='block-999', text='All amounts in this filing are stated in U.S. dollars.')
    if xbrl:
        block.update(text='Retained statement table', currency='USD',
                     currency_locator='inline XBRL unitRef USD -> iso4217:USD')
    document['blocks'].append(block)


@pytest.mark.parametrize('xbrl', [True, False])
def test_dollar_sign_uses_only_same_filing_currency_binding(xbrl):
    source = package()
    document = atm(source)
    binding(document, xbrl=xbrl)
    record = records(source)[0]
    assert record['currency'] == 'USD'
    assert record['currency_source']['source_id'] == document['source_id']
    assert record['currency_source']['locator'] == 'block-999'


def test_dollar_sign_without_currency_binding_stays_unresolved():
    source = package()
    assert records(source)[0]['currency'] is None
    document = atm(source)
    other = next(d for d in source['documents'] if d['filing']['accession'] != document['filing']['accession'])
    binding(other)
    assert records(source)[0]['currency'] is None


def test_conflicting_filing_reporting_currencies_stay_unresolved():
    source = package()
    document = atm(source)
    binding(document)
    conflict = deepcopy(document['blocks'][-1])
    conflict.update(locator='block-1000', currency='CAD',
                    currency_locator='inline XBRL unitRef CAD -> iso4217:CAD')
    document['blocks'].append(conflict)
    assert records(source)[0]['currency'] is None


@pytest.mark.parametrize('kind,statement', [
    ('notes', 'On November 2, 2026, the Company issued $500 million of senior notes. All dollar amounts in this agreement are in U.S. dollars.'),
    ('credit_agreement', 'On November 2, 2026, the Company entered into a credit agreement for a $400 million revolving credit facility. All dollar amounts in this agreement are in U.S. dollars.'),
])
def test_brief_reuses_source_matcher_for_notes_and_credit_events(kind, statement):
    from tests.docn_workflow_fixture import source_state
    from tradingagents.agents.context import build_shared_source_brief
    from tradingagents.agents.issuer_events import financing_sensitivities

    state = source_state()
    source = state['filing_evidence']
    doc = atm(source)
    doc['filing']['items'] = '1.01,8.01'
    block = next(b for b in doc['blocks'] if b['locator'] == 'block-31')
    block['text'] = statement
    result = records(source)
    event = next(r for r in result if r['type'] == kind)
    assert event['quote'] == statement
    brief = build_shared_source_brief(state)
    assert statement in brief
    assert event['source_id'] in brief and '2026-11-03' in brief
    assert financing_sensitivities(state) == []  # No hypothetical ATM issuance from other financing types.
