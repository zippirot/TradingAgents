"""Offline source excerpt checks across a bank and an industrial issuer."""
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from tradingagents.dataflows.filing_search import search_filing_evidence
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

FIXTURES = Path(__file__).parent / 'fixtures' / 'document_access'


@pytest.mark.parametrize('ticker', ['jpm', 'cat'])
def test_public_sec_excerpt_search_and_limits(ticker):
    fixture = json.loads((FIXTURES / f'public_sec_excerpt_{ticker}.json').read_text())
    assert fixture['fixture_kind'].startswith('offline excerpt from public SEC filing')
    package = DisclosurePackage.model_validate(fixture['package'])
    document = package.documents[0]
    provenance = fixture['provenance']
    queries = fixture['queries']
    assert package.cik == document.filing.cik
    assert provenance['source_url'] == document.url == document.filing.url
    assert provenance['source_content_sha256'] == document.content_hash
    assert len(provenance['source_content_sha256']) == 64
    assert set(provenance['excerpt_locators']) == {b.locator for b in document.blocks}

    for kind in ('table', 'prose'):
        locator = queries[f'{kind}_locator']
        query = queries[f'{kind}_query']
        result = search_filing_evidence(package, query)
        matching = [p for p in result['passages'] if p['locator'] == locator]
        assert matching, (ticker, kind, result)
        passage = matching[0]
        block = next(b for b in document.blocks if b.locator == locator)
        assert passage['text'] == block.text
        assert passage['source_id'] == document.source_id
        assert passage['content_hash'] == provenance['source_content_sha256']
        assert passage['passage_hash'] == hashlib.sha256(block.text.encode()).hexdigest()
        assert passage['filing_form'] == '10-Q'
        assert passage['filing_date'] == document.filing.filed_date.isoformat()
        assert len(result['passages']) <= 3
        assert sum(len(p['text']) for p in result['passages']) <= 12000
        assert result == search_filing_evidence(package, query)

    table = next(b for b in document.blocks if b.locator == queries['table_locator'])
    limited = search_filing_evidence(package, queries['table_query'], max_chars=len(table.text) - 1)
    assert all(p['locator'] != table.locator for p in limited['passages'])
    assert any('passage omitted by search size limit' in gap for gap in limited['gaps'])

    prior_cutoff = package.model_copy(update={'as_of': document.filing.filed_date - timedelta(days=1)})
    excluded = search_filing_evidence(prior_cutoff, queries['table_query'])
    assert not excluded['passages']
    assert any('excluded by issuer or analysis cutoff' in gap for gap in excluded['gaps'])
    assert 'not found in retained filings' in excluded['gaps']

    with pytest.raises(ValueError, match='Search limit exceeded'):
        search_filing_evidence(package, queries['table_query'], max_chars=12001)
