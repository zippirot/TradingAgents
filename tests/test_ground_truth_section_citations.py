"""Retained primary section text has an explicit citation namespace."""
from copy import deepcopy

import pytest

from tradingagents import ground_truth as audit
from tradingagents.report_html import _markdown

NARRATIVE = 'Stock-based compensation is included in the statements of operations as follows:'
SECTION = 'Document ; Note 12. Compensation ; ' + NARRATIVE
SOURCE = {'source_id': 'issuer', 'locator': 'block-A@400:800', 'original_locator': 'block-A',
          'source_character_start': 400, 'source_character_end': 800,
          'text': 'Total | 35,045 | 18,800', 'context': {'source_section': SECTION},
          'url': 'https://www.sec.gov/Archives/edgar/data/1582961/example.htm',
          'known_at': '2026-11-03', 'kind': 'filing passage'}


def validate(quote=NARRATIVE, *, refquote=NARRATIVE, field='section', source=None, outcome='supported'):
    source = source or SOURCE
    reference = {'source_id': source['source_id'], 'locator': source['locator'], 'quote': refquote}
    if field != 'OMITTED':
        reference['field'] = field
    return audit._validate_claim({'quoted_claim': quote, 'outcome': outcome, 'explanation': 'Exact retained primary wording.',
                                  'evidence': [reference]},
                                 {'text': quote, 'chunk_id': 'decision@0', 'section_id': 'decision', 'start': 0},
                                 {(source['source_id'], source['locator']): source})


def test_section_citation_is_exact_field_scoped_and_does_not_inherit_body_offsets():
    before = deepcopy(SOURCE)
    claim = validate()
    reference = claim['evidence'][0]
    assert reference['quote'] == NARRATIVE and reference['locator'] == 'block-A#section'
    assert reference['original_locator'] == 'block-A' and reference['source_field'] == 'section'
    assert 'source_character_start' not in reference and 'source_character_end' not in reference
    assert not claim['code_verified'] and not claim['verification']['arithmetic_reproduced']
    assert before == SOURCE


def test_unchanged_default_body_reference_still_rejects_section_only_text():
    with pytest.raises(ValueError, match='source quote or locator'):
        validate(field='OMITTED')
    with pytest.raises(ValueError, match='source quote or locator'):
        validate(field='text')


def test_body_reference_path_preserves_fragment_locator_and_offsets():
    claim = validate('The total amount is 35,045.', refquote=SOURCE['text'], field='OMITTED')
    reference = claim['evidence'][0]
    assert reference['locator'] == SOURCE['locator']
    assert reference['original_locator'] == 'block-A'
    assert reference['source_character_start'] == 400 and reference['source_character_end'] == 800
    assert 'source_field' not in reference


@pytest.mark.parametrize('field', [None, False, {}, 'context', 'source_section', 'section.notes'])
def test_unknown_fields_are_not_citable(field):
    with pytest.raises(ValueError, match='field'):
        validate(field=field)


@pytest.mark.parametrize('kind', ['canonical financial fields', 'reproduced financial calculation',
                                  'reproduced valuation reference', 'attributed vendor output',
                                  'retained report context; no financial authority'])
def test_only_trusted_indexed_filing_passages_have_a_section_namespace(kind):
    with pytest.raises(ValueError, match='section'):
        validate(source={**SOURCE, 'kind': kind})


@pytest.mark.parametrize('context', [{}, {'source_section': None}, {'source_section': ''}])
def test_missing_section_does_not_fall_back_to_body_text(context):
    with pytest.raises(ValueError, match='section'):
        validate(refquote=SOURCE['text'], source={**SOURCE, 'context': context})


def test_section_field_cannot_certify_the_false_full_accounting_treatment():
    quote = 'That is before treating quarterly stock compensation as a real cost.'
    with pytest.raises(ValueError, match='accounting treatment'):
        validate(quote, outcome='supported')
    qualified = validate(quote, outcome='unsupported')
    assert qualified['outcome'] == 'unsupported' and qualified['correction'] is None


def test_full_detail_and_html_preserve_field_provenance_without_fake_body_spans():
    claim = validate()
    record = {'status': 'completed', 'claims': [claim], 'coverage': {'total_chunks': 1, 'reviewed_chunks': 1}}
    text = audit.render_audit(record)
    assert 'block-A#section' in text and 'Source field: section' in text
    assert 'Original source field: block-A.section' in text
    assert 'characters unknown' not in text and 'characters 400' not in text
    html = _markdown().render(text)
    assert 'block-A#section' in html and 'Source field: section' in html


def test_prompt_requires_explicit_field_and_forbids_arbitrary_context_citations():
    prompt = audit._review_prompt({'text': NARRATIVE, 'chunk_id': 'x'}, {('issuer', SOURCE['locator']): SOURCE})
    assert 'field: text or section' in prompt
    assert 'context.source_section' in prompt
    assert 'Other context fields are not citable' in prompt


def test_schema_eight_record_is_unavailable_under_new_field_contract():
    from tests.test_ground_truth_audit import Model, inventory, response, state
    inv = inventory()
    old = audit.run_audit(state(), Model(response()), inventory=inv)
    old['schema_version'] = 8
    audit.seal_audit(old)
    assert audit.resolve_audit(state(), old, inventory=inv)['status'] == 'unavailable'


def test_model_lineage_fields_cannot_override_the_explicit_namespace_or_trusted_pointer():
    reference = {'source_id': SOURCE['source_id'], 'locator': SOURCE['locator'], 'quote': NARRATIVE,
                 'source_field': 'section', 'original_locator': 'invented-270'}
    raw = {'quoted_claim': NARRATIVE, 'outcome': 'supported', 'explanation': 'Exact narrative.', 'evidence': [reference]}
    chunk = {'text': NARRATIVE, 'chunk_id': 'x', 'section_id': 'x', 'start': 0}
    with pytest.raises(ValueError, match='source quote or locator'):
        audit._validate_claim(raw, chunk, {(SOURCE['source_id'], SOURCE['locator']): SOURCE})
    reference['field'] = 'section'
    result = audit._validate_claim(raw, chunk, {(SOURCE['source_id'], SOURCE['locator']): SOURCE})
    assert result['evidence'][0]['original_locator'] == 'block-A'
    assert result['evidence'][0]['locator'] == 'block-A#section'


def test_historical_detail_preserves_section_lineage_without_body_offsets():
    claim = validate()
    history = {'status': 'completed', 'original_decision': 'Historical reasoning.', 'corrections': [claim]}
    detail = audit._render_reassessment_history(history)
    text = '\n'.join(detail) if isinstance(detail, list) else detail
    assert 'Original source field: block-A.section' in text
    assert 'Source field: section' in text
    assert 'characters 400' not in text and 'characters unknown' not in text
