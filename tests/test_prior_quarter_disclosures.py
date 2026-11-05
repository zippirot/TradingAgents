"""A missing comparator triggers one bounded, cutoff-aware prior filing request."""
import json

import pytest

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import sec_documents as docs


def metadata(extra=()):
    rows = [
        ('10-K', '2026-02-20', '2025-12-31', '0001582961-26-000001', 'annual.htm', ''),
        ('10-Q', '2026-05-05', '2026-03-31', '0001582961-26-000002', 'q1.htm', ''),
        ('10-Q', '2026-08-05', '2026-06-30', '0001582961-26-000003', 'q2.htm', ''),
        ('10-Q', '2026-11-04', '2026-09-30', '0001582961-26-000004', 'q3.htm', ''),
        *extra,
    ]
    names = ('form', 'filingDate', 'reportDate', 'accessionNumber', 'primaryDocument', 'items')
    return {'cik': '1582961', 'filings': {'recent': dict(zip(names, zip(*rows, strict=True), strict=True)), 'files': []}}


def test_selects_only_immediate_prior_quarter_and_eligible_amendment():
    amend = ('10-Q/A', '2026-09-01', '2026-06-30', '0001582961-26-000005', 'q2a.htm', '')
    future = ('10-Q/A', '2026-11-06', '2026-06-30', '0001582961-26-000006', 'future.htm', '')
    selected, gaps = docs.select_prior_quarter_filings(metadata((amend, future)), '0001582961', '2026-11-04', '2026-09-30')
    assert [f.primary_document for f in selected] == ['q2.htm', 'q2a.htm']
    assert not gaps


def test_wrong_issuer_is_rejected():
    with pytest.raises(VendorUnavailableError, match='issuer'):
        docs.select_prior_quarter_filings(metadata(), '0000320193', '2026-11-04', '2026-09-30')


def test_missing_or_future_anchor_never_fetches_a_guessed_comparator():
    selected, gaps = docs.select_prior_quarter_filings(metadata(), '0001582961', '2026-10-19', '2026-09-30')
    assert not selected and any('current' in gap.lower() for gap in gaps)
    data = metadata()
    for key in data['filings']['recent']:
        data['filings']['recent'][key] = [v for i, v in enumerate(data['filings']['recent'][key]) if i != 2]
    selected, gaps = docs.select_prior_quarter_filings(data, '0001582961', '2026-11-04', '2026-09-30')
    assert not selected and any('preceding quarter' in gap for gap in gaps)


def test_multiple_originals_or_amendments_are_visible_ambiguity():
    extra = ('10-Q', '2026-08-06', '2026-06-30', '0001582961-26-000005', 'other.htm', '')
    selected, gaps = docs.select_prior_quarter_filings(metadata((extra,)), '0001582961', '2026-11-04', '2026-09-30')
    assert not selected and any('ambiguous' in gap for gap in gaps)
    amendments = [('10-Q/A', f'2026-09-0{i}', '2026-06-30', f'0001582961-26-00000{i+4}', f'q2a{i}.htm', '') for i in (1, 2)]
    selected, gaps = docs.select_prior_quarter_filings(metadata(amendments), '0001582961', '2026-11-04', '2026-09-30')
    assert not selected and any('amendment' in gap for gap in gaps)


def test_retrieval_is_bounded_and_preserves_actual_prior_source(monkeypatch):
    asked = []
    monkeypatch.setattr(docs, 'cik_for', lambda ticker: '0001582961')
    def fetch(self, url):
        asked.append(url)
        text = json.dumps(metadata()) if 'submissions' in url else '<p>Remaining performance obligations were $893.828 million at June 30, 2026.</p>'
        import hashlib
        return {'url': url, 'text': text, 'content_hash': hashlib.sha256(text.encode()).hexdigest(), 'retrieved_at': '2026-11-04T22:00:00+00:00'}
    monkeypatch.setattr(docs.DocumentClient, 'fetch', fetch)
    package = docs.get_prior_quarter_evidence('DOCN', '2026-11-04', '2026-09-30')
    assert len(asked) == 2 and asked[-1].endswith('/q2.htm')
    assert len(package.documents) == 1
    doc = package.documents[0]
    assert str(doc.filing.report_date) == '2026-06-30'
    assert '893.828' in doc.blocks[0].text
    assert doc.content_hash
    assert package.selected_accessions == ('0001582961-26-000003',)


def test_prior_kpi_retrieval_preserves_rpo_instead_of_expanding_global_text_budget(monkeypatch):
    monkeypatch.setattr(docs, 'cik_for', lambda ticker: '0001582961')
    note = 'The aggregate transaction price allocated to the remaining performance obligations at June 30, 2026 is $893,828.'
    crowded = ''.join('<p>Credit agreement term loan facility debt financing ' + ('word ' * 200) + '</p>' for _ in range(60))
    def fetch(self, url):
        import hashlib
        text = json.dumps(metadata()) if 'submissions' in url else crowded + '<p>' + note + '</p>'
        return {'url': url, 'text': text, 'content_hash': hashlib.sha256(text.encode()).hexdigest(), 'retrieved_at': '2026-11-04T22:00:00+00:00'}
    monkeypatch.setattr(docs.DocumentClient, 'fetch', fetch)
    package = docs.get_prior_quarter_evidence('DOCN', '2026-11-04', '2026-09-30')
    assert any(block.text == note for block in package.documents[0].blocks)
    assert sum(len(block.text) for block in package.documents[0].blocks) <= 40000
    assert package.gaps


def test_year_end_snapshot_is_kept_as_annual_not_relabelled_as_quarter():
    selected, gaps = docs.select_prior_quarter_filings(metadata(), '0001582961', '2026-05-05', '2026-03-31')
    assert len(selected) == 1 and selected[0].form == '10-K'
    assert str(selected[0].report_date) == '2025-12-31'
    assert not gaps


def test_failed_prior_document_is_a_visible_gap(monkeypatch):
    monkeypatch.setattr(docs, 'cik_for', lambda ticker: '0001582961')
    def fetch(self, url):
        if 'submissions' in url:
            return {'text': json.dumps(metadata())}
        raise VendorUnavailableError('SEC document byte limit exceeded')
    monkeypatch.setattr(docs.DocumentClient, 'fetch', fetch)
    package = docs.get_prior_quarter_evidence('DOCN', '2026-11-04', '2026-09-30')
    assert not package.documents
    assert any('byte limit' in gap for gap in package.gaps)
    assert package.selected_accessions == ('0001582961-26-000003',)


def test_recorded_prior_source_retains_unit_scale_and_recognition_qualifiers():
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / 'fixtures/docn_2026q2/prior_quarter_rpo.json').read_text())
    package = docs.DisclosurePackage.model_validate(fixture['package'])
    document = package.documents[0]
    block = next(block for block in document.blocks if block.locator == 'block-149')
    assert document.filing.accession == '0001628280-26-052556'
    assert str(document.filing.report_date) == '2026-06-30'
    assert '$893,828' in block.text and '$365,901' in block.text
    assert '3.7 years' in block.text and 'next 12 months' in block.text
    spans = fixture['provenance']['source_spans']
    assert 'iso4217:USD' in spans[0]['exact_html']
    assert 'scale="3"' in spans[1]['exact_html']
    assert document.content_hash == fixture['provenance']['full_source_sha256']


def inline_rpo(amount='893,828', scale='3', currency='USD', instant='2026-06-30', dimension=''):
    return (f'<xbrli:unit id="usd"><xbrli:measure>iso4217:{currency}</xbrli:measure></xbrli:unit>'
            '<xbrli:context id="c1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1582961</xbrli:identifier>'
            + dimension + f'</xbrli:entity><xbrli:period><xbrli:instant>{instant}</xbrli:instant></xbrli:period></xbrli:context>'
            f'<p>The remaining performance obligations are $<ix:nonFraction id="rpo1" name="us-gaap:RevenueRemainingPerformanceObligation" '
            f'contextRef="c1" unitRef="usd" scale="{scale}" format="ixt:num-dot-decimal">{amount}</ix:nonFraction>.</p>')


def test_inline_rpo_retains_source_unit_scale_instant_and_exact_spans():
    text = inline_rpo()
    facts, gaps = docs.extract_rpo_facts(text, '0001582961', '2026-11-04')
    assert not gaps and len(facts) == 1
    fact = facts[0]
    assert str(fact.value) == '893828000'
    assert fact.currency == 'USD' and str(fact.period_end) == '2026-06-30'
    assert fact.locator == 'inline-fact-rpo1'
    assert text[fact.character_start:fact.character_end] == fact.exact_html
    assert 'scale="3"' in fact.exact_html and 'iso4217:USD' in fact.unit_html
    assert '2026-06-30' in fact.context_html


@pytest.mark.parametrize('change', [
    {'amount': '-2'}, {'amount': 'NaN'}, {'scale': 'bad'}, {'currency': 'usd'},
    {'instant': '2026-12-31'}, {'dimension': '<xbrli:segment><xbrldi:explicitMember>Product</xbrldi:explicitMember></xbrli:segment>'},
])
def test_bad_or_segmented_inline_rpo_is_unavailable(change):
    facts, gaps = docs.extract_rpo_facts(inline_rpo(**change), '0001582961', '2026-11-04')
    assert not facts and gaps


def test_inline_rpo_wrong_issuer_or_duplicate_context_is_rejected():
    text = inline_rpo()
    assert not docs.extract_rpo_facts(text, '0000320193', '2026-11-04')[0]
    import re
    context = re.search(r'<xbrli:context.*?</xbrli:context>', text).group()
    assert not docs.extract_rpo_facts(text + context, '0001582961', '2026-11-04')[0]


def test_recognition_start_axis_is_distinct_from_business_segmentation():
    dimension = ('<xbrli:segment><xbrldi:typedMember dimension="us-gaap:RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionStartDateAxis">'
                 '<us-gaap:date.domain>2026-07-01</us-gaap:date.domain></xbrldi:typedMember></xbrli:segment>')
    facts, gaps = docs.extract_rpo_facts(inline_rpo(dimension=dimension), '0001582961', '2026-11-04')
    assert len(facts) == 1 and not gaps
    assert str(facts[0].recognition_start) == '2026-07-01'
    assert not docs.extract_rpo_facts(inline_rpo(dimension=dimension.replace('2026-07-01', '2026-08-01')),
                                      '0001582961', '2026-11-04')[0]


def test_current_rpo_helper_uses_same_source_identity_and_retains_runtime_scale(monkeypatch):
    import hashlib
    from pathlib import Path
    package = docs.DisclosurePackage.model_validate(json.loads(
        (Path(__file__).parent / 'fixtures/docn_2026q2/prior_quarter_rpo.json').read_text())['package'])
    raw = inline_rpo()
    document = package.documents[0].model_copy(update={'content_hash': hashlib.sha256(raw.encode()).hexdigest(), 'rpo_facts': ()})
    package = package.model_copy(update={'documents': (document,)})
    calls = []
    def fetch(self, url):
        assert self.max_requests == 1
        calls.append(url)
        return {'url': url, 'text': raw, 'content_hash': document.content_hash, 'retrieved_at': '2026-11-04T22:00:00+00:00'}
    monkeypatch.setattr(docs.DocumentClient, 'fetch', fetch)
    result = docs.get_current_quarter_rpo_evidence(package)
    assert calls == [document.url]
    assert result.documents[0].source_id == document.source_id
    assert result.documents[0].content_hash == document.content_hash
    assert result.documents[0].rpo_facts[0].value == 893828000
    wrong = package.model_copy(update={'documents': (document.model_copy(update={'source_id': 'wrong'}),)})
    assert not docs.get_current_quarter_rpo_evidence(wrong).documents
    assert len(calls) == 1


def test_current_changed_source_cannot_reuse_original_hash(monkeypatch):
    from pathlib import Path
    package = docs.DisclosurePackage.model_validate(json.loads(
        (Path(__file__).parent / 'fixtures/docn_2026q2/prior_quarter_rpo.json').read_text())['package'])
    monkeypatch.setattr(docs.DocumentClient, 'fetch', lambda self, url: {'content_hash': 'different'})
    result = docs.get_current_quarter_rpo_evidence(package)
    assert not result.documents
    assert any('content changed' in gap for gap in result.gaps)


def test_recorded_runtime_rpo_facts_match_quarters_without_assumed_scale():
    from pathlib import Path
    root = Path(__file__).parent / 'fixtures'
    prior = docs.DisclosurePackage.model_validate(json.loads((root / 'docn_2026q2/prior_quarter_rpo.json').read_text())['package'])
    current = docs.DisclosurePackage.model_validate(json.loads((root / 'docn_2026q3/rpo_context.json').read_text())['package'])
    left, right = prior.documents[0].rpo_facts[0], current.documents[0].rpo_facts[0]
    assert left.value == 893828000 and right.value == 799707000
    assert left.currency == right.currency == 'USD'
    assert (str(left.period_end), str(right.period_end)) == ('2026-06-30', '2026-09-30')
    assert left.recognition_start and right.recognition_start


def test_commented_or_scripted_inline_cells_are_not_filing_facts():
    for wrapper in ('<!-- {cell} -->', '<script>{cell}</script>', '<style>{cell}</style>'):
        facts, gaps = docs.extract_rpo_facts(wrapper.format(cell=inline_rpo()), '0001582961', '2026-11-04')
        assert not facts and gaps


@pytest.mark.parametrize('items,expected', [('2.02,9.01', True), ('8.01,9.01', False)])
def test_recorded_nvda_fragmented_dated_release_link(monkeypatch, items, expected):
    """Actual exhibit has a non-99 filename and splits its label across anchors."""
    import hashlib
    from pathlib import Path
    recorded = json.loads((Path(__file__).parent / 'fixtures/nvda_2027q2/earnings_exhibit_link.json').read_text())
    names = ('form', 'filingDate', 'reportDate', 'accessionNumber', 'primaryDocument', 'items')
    rows = [('8-K', '2026-08-26', '2026-08-26', '0001045810-26-000073', 'nvda-20260826.htm', items)]
    data = {'cik': '1045810', 'filings': {'recent': dict(zip(names, zip(*rows, strict=True), strict=True)), 'files': []}}
    # Incidental references and unsafe URLs must not become candidate exhibits.
    cover = '<table>' + recorded['exact_html'] + '</table>' + (
        '<a href="incidental.htm">See prior Press Release, dated August 1</a>'
        '<a href="https://evil.test/foreign.htm">Press Release, dated August 26</a>'
        '<a href="../escape.htm">Press Release, dated August 26</a>')
    _, links, _ = docs.extract_sections(cover)
    assert ('q2fy27pr.htm', 'Press Release, dated') in links
    assert len([link for link in links if link[0] == 'q2fy27pr.htm']) > 1
    monkeypatch.setattr(docs, 'cik_for', lambda _: '0001045810')
    calls = []
    def fetch(self, url):
        calls.append(url)
        text = json.dumps(data) if 'submissions' in url else cover if url == recorded['url'] else '<p>Earnings release.</p>'
        return {'url': url, 'text': text, 'content_hash': hashlib.sha256(text.encode()).hexdigest(), 'retrieved_at': recorded['retrieved_at']}
    monkeypatch.setattr(docs.DocumentClient, 'fetch', fetch)
    package = docs.get_filing_evidence('NVDA', '2026-08-26')
    release = recorded['url'].rsplit('/', 1)[0] + '/q2fy27pr.htm'
    assert (release in calls) is expected
    assert calls.count(release) == int(expected)
    assert all(not any(name in url for name in ('incidental', 'evil.test', 'escape')) for url in calls)
    assert any(doc.url == release for doc in package.documents) is expected
