"""A reproduced equity/trailing multiple cannot certify another ratio basis."""
import json
from copy import deepcopy

import pytest

from tests.test_ground_truth_audit import inventory, state
from tradingagents import ground_truth as audit
from tradingagents.ground_truth_display import build_report_inventory
from tradingagents.report_html import render_report
from tradingagents.reporting import write_report_tree

LITERAL = 'Current reference: 7.89x equity value / trailing revenue. Own-history median: 4.47x equity value / trailing revenue.'
SOURCE = {'source_id': 'reproduced-reference', 'locator': 'current', 'text': LITERAL,
          'url': '', 'known_at': '2026-11-06', 'kind': 'reproduced valuation reference', 'truncated': False}
SOURCES = {(SOURCE['source_id'], SOURCE['locator']): SOURCE}


def raw_claim(quote, outcome='supported', **extra):
    return {'quoted_claim': quote, 'outcome': outcome, 'explanation': 'Synthetic reference assessment.',
            'evidence': [{'source_id': SOURCE['source_id'], 'locator': SOURCE['locator'], 'quote': LITERAL}], **extra}


def validate(quote, outcome='supported', **extra):
    return audit._validate_claim(raw_claim(quote, outcome, **extra),
        {'chunk_id': 'decision@0', 'section_id': 'decision', 'start': 0, 'text': quote}, SOURCES)


@pytest.mark.parametrize('quote', [
    'The market pays 6.81× today.',
    'The market multiple is 6.81.',
    'The ratio is 7.89x trailing revenue.',
    'The ratio is 7.89x forward revenue on an equity-value basis.',
    'The ratio is 7.89x trailing revenue on an enterprise-value basis.',
    'The ratio is 7.89x revenue on an equity-value basis.',
    'The market pays 6.81x; the reference is 7.89x trailing revenue on an equity-value basis.',
    'The market pays 6.81x; equity value is 100 USD and trailing revenue is 100 USD.',
    'The market pays 6.81x; the equity value / trailing revenue reference is 7.89x.',
    'The market pays 6.81x. Equity value / trailing revenue is 7.89x.',
    'EV / FY 2026 revenue is 6.81x.',
    'EV / FY 2026 revenue is 6.81.',
    'Enterprise value / forward revenue is 6.81x.',
    'EV / guidance revenue is 6.81x; equity value / trailing revenue is 7.89x.',
])
@pytest.mark.parametrize('outcome', ['supported', 'contradicted'])
def test_ambiguous_or_cross_basis_ratio_cannot_gain_reference_authority(quote, outcome):
    extra = {'correction': LITERAL, 'correction_scope': 'complete_claim'} if outcome == 'contradicted' else {}
    with pytest.raises(ValueError, match='basis'):
        validate(quote, outcome, **extra)


@pytest.mark.parametrize('quote', [
    'Equity value / trailing revenue is 7.89x.',
    'Market capitalization / TTM revenue multiple is 7.89.',
    'The own-history median equity value / trailing revenue was 4.47x.',
    'The multiple fell from 16.31x to 7.56x equity value / trailing revenue.',
    'At the dated November close, XYZ traded at 7.89 times trailing revenue on an equity-value basis, versus its historical median of 4.47 times.',
    'The multiple is 7.89x TTM revenue on a market-capitalization basis.',
])
@pytest.mark.parametrize('outcome', ['supported', 'contradicted'])
def test_explicit_same_basis_reference_claims_preserve_model_assessments(quote, outcome):
    extra = {'correction': LITERAL, 'correction_scope': 'complete_claim'} if outcome == 'contradicted' else {}
    result = validate(quote, outcome, **extra)
    assert result['outcome'] == outcome
    assert result['verification']['semantic_assessment'] == 'model' and not result['code_verified']


@pytest.mark.parametrize('quote,outcome', [
    ('The market pays 6.81× today.', 'unsupported'),
    ('EV / FY revenue could reach 6.81x.', 'hypothesis'),
    ('The observation date is 2026-09-30.', 'supported'),
    ('The share observation window spans eight quarters.', 'supported'),
    ('The multiple uses share counts from 2026-09-30.', 'supported'),
])
def test_qualified_outcomes_and_nonratio_window_claims_remain_available(quote, outcome):
    assert validate(quote, outcome)['outcome'] == outcome


@pytest.mark.parametrize('kind', ['filing passage', 'reproduced financial calculation'])
def test_guard_does_not_impose_equity_basis_on_other_source_kinds(kind):
    source = {**SOURCE, 'kind': kind, 'text': 'EV / FY 2026 revenue is 6.81x.'}
    quote = source['text']
    finding = raw_claim(quote)
    finding['evidence'][0]['quote'] = quote
    result = audit._validate_claim(finding, {'chunk_id': 'x', 'section_id': 'x', 'start': 0, 'text': quote},
                                    {(source['source_id'], source['locator']): source})
    assert result['outcome'] == 'supported'


@pytest.mark.parametrize('refuse', [False, True])
def test_invalid_basis_goes_through_exact_quote_repair_without_automatic_verdict(monkeypatch, refuse):
    quote = 'The market pays 6.81× today.'
    monkeypatch.setattr(audit, '_source_index', lambda state: (deepcopy(SOURCES), []))
    class Reviewer:
        def __init__(self):
            self.calls = []
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            self.calls.append(chunk)
            if chunk.get('review_claims') and not refuse:
                assert chunk['review_claims'] == [quote]
                assert 'basis' in chunk['prior_assessments'][0]['explanation']
                qualified = raw_claim(quote, 'unsupported')
                qualified['explanation'] = 'The report does not specify the ratio basis; the equity/trailing reference cannot establish this ambiguous multiple.'
                return {'no_material_claims': False, 'claims': [qualified]}
            return {'no_material_claims': False, 'claims': [raw_claim(quote, 'contradicted',
                    correction=LITERAL, correction_scope='complete_claim', decision_material=True)]}
    reviewer = Reviewer()
    result = audit.run_audit(state(), reviewer, inventory=inventory(parts=[('Decision', '5_portfolio', [('PM', 'decision.md', quote)])]))
    assert len(reviewer.calls) == 2
    if refuse:
        assert result['status'] == 'partial' and result['claims'] == []
        assert result['unresolved_repairs'][0]['quoted_claim'] == quote
    else:
        assert result['status'] == 'completed with findings'
        assert result['claims'][0]['outcome'] == 'unsupported' and result['claims'][0]['correction'] is None


def test_schema_five_false_correction_is_unavailable_in_offline_exports(tmp_path):
    quote = 'The market pays 6.81× today.'
    candidate = {**state(), 'run_settings': {'ground_truth_audit': True}, 'final_rating': 'Hold', 'final_trade_decision': quote}
    inv = build_report_inventory(candidate)
    chunk = next(c for c in inv['chunks'] if quote in c['text'])
    start = chunk['start'] + chunk['text'].index(quote)
    finding = {'chunk_id': chunk['chunk_id'], 'section_id': chunk['section_id'], 'character_start': start,
               'character_end': start + len(quote), 'ambiguous_location': False, 'quoted_claim': quote,
               'outcome': 'contradicted', 'explanation': 'Legacy cross-basis comparison.', 'correction': LITERAL,
               'decision_material': True, 'code_verified': False, 'evidence': []}
    old = {'schema_version': 5, 'status': 'completed with findings', 'digest': inv['digest'],
           'evidence_digest': inv['evidence_digest'], 'identity': inv['identity'], 'claims': [finding],
           'chunk_digests': {c['chunk_id']: audit._digest(c) for c in inv['chunks']},
           'coverage': {'total_chunks': len(inv['chunks']), 'reviewed_chunks': len(inv['chunks']),
                        'reviewed_chunk_ids': [c['chunk_id'] for c in inv['chunks']], 'remaining_chunks': []}}
    candidate['ground_truth_audit'] = audit.seal_audit(old)
    assert audit.resolve_audit(candidate, inventory=inv)['status'] == 'unavailable'
    write_report_tree(candidate, 'DOCN', tmp_path)
    for name in ['complete_report.md', 'complete_report.html']:
        text = (tmp_path / name).read_text()
        assert 'unavailable' in text.lower() and LITERAL not in text
    assert LITERAL not in render_report('DOCN', candidate, None)


def test_prompt_states_reference_basis_contract_without_rewriting_report_quote():
    quote = 'The market pays 6.81× today.'
    prompt = audit._review_prompt({'text': quote, 'start': 0, 'chunk_id': 'x'}, SOURCES)
    assert 'equity value / trailing revenue' in prompt
    assert 'Never replace one ratio basis with another' in prompt
    assert 'ambiguous, EV, forward or mixed-basis' in prompt
    assert 'Keep the exact report quotation unchanged' in prompt


def test_pending_partial_chunk_cannot_auto_complete_when_the_word_order_becomes_valid(monkeypatch):
    first = 'Equity value / trailing revenue is 7.89x.'
    pending = 'The multiple is 7.89x trailing revenue on an equity-value basis.'
    parts = [('Decision', '5_portfolio', [('First', 'first.md', first), ('Pending', 'pending.md', pending)])]
    inv = inventory(parts=parts)
    monkeypatch.setattr(audit, '_source_index', lambda state: (deepcopy(SOURCES), []))
    class Reviewer:
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            return {'claims': [raw_claim(chunk['text'])], 'no_material_claims': False}
    prior = audit.run_audit(state(), Reviewer(), {'ground_truth_max_requests': 1}, inventory=inv)
    assert prior['status'] == 'partial' and prior['coverage']['reviewed_chunks'] == 1
    remaining = prior['coverage']['remaining_chunks']
    result = audit.run_audit(state(), None, inventory=inv, prior_audit=prior)
    assert result['status'] == 'partial' and result['usage']['requests'] == 0
    assert result['coverage']['reviewed_chunks'] == 1 and result['coverage']['remaining_chunks'] == remaining
    assert result['claims'] == prior['claims']
