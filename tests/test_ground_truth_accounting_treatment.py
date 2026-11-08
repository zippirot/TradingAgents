"""Expense amounts alone cannot certify a full accounting-treatment assertion."""
import json
from copy import deepcopy

import pytest

from tests.test_ground_truth_audit import inventory, state
from tradingagents import ground_truth as audit
from tradingagents.ground_truth_display import build_report_inventory
from tradingagents.report_html import render_report
from tradingagents.reporting import write_report_tree

CLAIM = 'That is before treating roughly $35M of quarterly stock compensation as the real cost it is.'
AMOUNT = 'Stock-based compensation | 35,045 | 18,800'
DEFINITION = 'We define adjusted net income as net income excluding stock-based compensation and conversion expense.'
SOURCE = {'source_id': 'issuer', 'locator': 'reconciliation', 'kind': 'filing passage',
          'text': 'GAAP Net loss | (41,609) ; ' + AMOUNT + ' ; Conversion expense | 56,110 ; Adjusted net income | 49,546',
          'url': 'https://www.sec.gov/Archives/edgar/data/1582961/example.htm', 'known_at': '2026-11-03'}
SOURCES = {(SOURCE['source_id'], SOURCE['locator']): SOURCE}


def raw(quote=CLAIM, outcome='supported', excerpt=AMOUNT):
    return {'quoted_claim': quote, 'outcome': outcome, 'decision_material': True,
            'explanation': 'The amount agrees; the further accounting adjustment is a judgment.',
            'evidence': [{'source_id': SOURCE['source_id'], 'locator': SOURCE['locator'], 'quote': excerpt}]}


def validate(claim, sources=None):
    return audit._validate_claim(claim, {'chunk_id': 'decision@0', 'section_id': 'decision', 'start': 0,
                                       'text': claim['quoted_claim']}, sources or SOURCES)


@pytest.mark.parametrize('excerpt', [AMOUNT, SOURCE['text']])
def test_amount_row_or_full_numeric_reconciliation_cannot_certify_treatment(excerpt):
    with pytest.raises(ValueError, match='accounting treatment'):
        validate(raw(excerpt=excerpt))


def test_reproduced_sum_cannot_certify_treatment_even_if_model_quotes_its_own_interpretation():
    source = {**SOURCE, 'kind': 'reproduced financial calculation', 'text': CLAIM}
    with pytest.raises(ValueError, match='accounting treatment'):
        validate(raw(excerpt=CLAIM), {(source['source_id'], source['locator']): source})


@pytest.mark.parametrize('quote', ['Quarterly stock-based compensation was roughly $35M.',
                                  'Stock-based compensation: 35,045 USD.'])
def test_plain_compensation_amount_claims_preserve_model_assessment(quote):
    assert validate(raw(quote))['outcome'] == 'supported'


def test_exact_primary_narrative_definition_remains_supported():
    source = {**SOURCE, 'text': DEFINITION}
    result = validate(raw(DEFINITION, excerpt=DEFINITION), {(source['source_id'], source['locator']): source})
    assert result['outcome'] == 'supported' and result['verification']['source_quotes_validated']
    assert not result['code_verified']


def test_different_narrative_treatment_cannot_certify_full_deictic_assertion():
    source = {**SOURCE, 'text': DEFINITION}
    with pytest.raises(ValueError, match='accounting treatment'):
        validate(raw(excerpt=DEFINITION), {(source['source_id'], source['locator']): source})


@pytest.mark.parametrize('outcome', ['unsupported', 'hypothesis', 'contradicted'])
def test_qualified_or_contradicted_assessments_keep_existing_rules(outcome):
    assert validate(raw(outcome=outcome))['outcome'] == outcome


class Reviewer:
    def __init__(self, mode):
        self.mode, self.calls = mode, []
    def invoke(self, prompt):
        chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
        self.calls.append(chunk)
        if chunk.get('review_claims'):
            assert chunk['review_claims'] == [CLAIM]
            if self.mode == 'qualified':
                qualified = raw(outcome='unsupported')
                qualified['explanation'] = 'The amount row does not establish whether the starting income already includes this expense.'
                return {'claims': [qualified], 'no_material_claims': False}
            if self.mode == 'amount_only':
                return {'claims': [raw('roughly $35M of quarterly stock compensation')], 'no_material_claims': False}
        return {'claims': [raw()], 'no_material_claims': False}


@pytest.mark.parametrize('mode', ['qualified', 'amount_only', 'refused'])
def test_existing_repair_requires_disposition_of_the_entire_mixed_target(monkeypatch, mode):
    monkeypatch.setattr(audit, '_source_index', lambda state: (deepcopy(SOURCES), []))
    inv = inventory(parts=[('Decision', '5_portfolio', [('PM', 'decision.md', CLAIM)])])
    reviewer = Reviewer(mode)
    result = audit.run_audit(state(), reviewer, inventory=inv)
    assert len(reviewer.calls) == 2
    if mode == 'qualified':
        assert result['status'] == 'completed with findings'
        assert result['claims'][0]['quoted_claim'] == CLAIM
        assert result['claims'][0]['outcome'] == 'unsupported'
    else:
        assert result['status'] == 'partial' and result['claims'] == []
        assert result['coverage']['reviewed_chunks'] == 0
        assert result['unresolved_repairs'][0]['quoted_claim'] == CLAIM


def test_prompt_requires_primary_treatment_support_and_full_repair_disposition():
    prompt = audit._review_prompt({'text': CLAIM, 'chunk_id': 'x'}, SOURCES)
    assert 'Accounting-treatment assertions' in prompt
    assert 'amount row or reproduced sum' in prompt
    assert 'exact primary narrative' in prompt
    assert 'entire requested mixed assertion' in prompt


@pytest.mark.parametrize('legacy_schema', [6, 7])
def test_prior_schema_false_complete_cannot_resolve_or_export_offline(tmp_path, legacy_schema):
    candidate = {**state(), 'run_settings': {'ground_truth_audit': True}, 'final_rating': 'Hold', 'final_trade_decision': CLAIM}
    inv = build_report_inventory(candidate)
    chunk = next(c for c in inv['chunks'] if CLAIM in c['text'])
    legacy_quote = CLAIM if legacy_schema == 6 else 'roughly $35M of quarterly stock compensation'
    start = chunk['start'] + chunk['text'].index(legacy_quote)
    finding = {**raw(legacy_quote), 'chunk_id': chunk['chunk_id'], 'section_id': chunk['section_id'],
               'character_start': start, 'character_end': start + len(legacy_quote), 'ambiguous_location': False,
               'correction': None, 'code_verified': False, 'evidence': []}
    old = {'schema_version': legacy_schema, 'status': 'completed', 'digest': inv['digest'], 'evidence_digest': inv['evidence_digest'],
           'identity': inv['identity'], 'claims': [finding],
           'chunk_digests': {c['chunk_id']: audit._digest(c) for c in inv['chunks']},
           'coverage': {'total_chunks': len(inv['chunks']), 'reviewed_chunks': len(inv['chunks']),
                        'reviewed_chunk_ids': [c['chunk_id'] for c in inv['chunks']], 'remaining_chunks': []}}
    candidate['ground_truth_audit'] = audit.seal_audit(old)
    assert audit.resolve_audit(candidate, inventory=inv)['status'] == 'unavailable'
    write_report_tree(candidate, 'DOCN', tmp_path)
    for name in ['complete_report.md', 'complete_report.html']:
        text = (tmp_path / name).read_text()
        assert 'unavailable' in text.lower() and 'Supported' not in text
    assert 'unavailable' in render_report('DOCN', candidate, None).lower()


class InitialAmountReviewer:
    def __init__(self, outcome='unsupported', amount_only=False):
        self.calls, self.outcome, self.amount_only = [], outcome, amount_only
    def invoke(self, prompt):
        chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
        self.calls.append(chunk)
        if chunk.get('review_claims') and not self.amount_only:
            return {'claims': [raw(quote, outcome=self.outcome) for quote in chunk['review_claims']], 'no_material_claims': False}
        return {'claims': [raw('roughly $35M of quarterly stock compensation')], 'no_material_claims': False}


@pytest.mark.parametrize('outcome', ['unsupported', 'hypothesis'])
def test_initial_amount_only_cannot_omit_the_full_treatment_interpretation(monkeypatch, outcome):
    monkeypatch.setattr(audit, '_source_index', lambda state: (deepcopy(SOURCES), []))
    inv = inventory(parts=[('Decision', '5_portfolio', [('PM', 'decision.md', CLAIM)])])
    model = InitialAmountReviewer(outcome)
    result = audit.run_audit(state(), model, inventory=inv)
    assert len(model.calls) == 2 and model.calls[1]['review_claims'] == [CLAIM]
    assert result['coverage']['reviewed_chunks'] == 1
    assert result['claims'][0]['quoted_claim'] == 'roughly $35M of quarterly stock compensation'
    assert result['claims'][1]['quoted_claim'] == CLAIM and result['claims'][1]['outcome'] == outcome


@pytest.mark.parametrize('mode', ['amount_only', 'budget', 'duplicate'])
def test_unassessed_treatment_never_completes_when_numeric_amounts_are_already_covered(monkeypatch, mode):
    monkeypatch.setattr(audit, '_source_index', lambda state: (deepcopy(SOURCES), []))
    text = CLAIM if mode != 'duplicate' else 'First case\n' + CLAIM + '\nSecond case\n' + CLAIM
    model = InitialAmountReviewer(amount_only=True)
    result = audit.run_audit(state(), model, {'ground_truth_max_requests': 1} if mode == 'budget' else {},
                            inventory=inventory(parts=[('Decision', '5_portfolio', [('PM', 'decision.md', text)])]))
    assert result['status'] == 'partial' and result['coverage']['reviewed_chunks'] == 0
    assert result['unresolved_repairs']
    assert len(model.calls) == (1 if mode == 'budget' else 2)


def test_final_treatment_coverage_remains_partial_after_the_hundred_target_allowance(monkeypatch):
    monkeypatch.setattr(audit, '_source_index', lambda state: (deepcopy(SOURCES), []))
    lines = [f'Case {chr(65 + i // 26)}{chr(65 + i % 26)}: Net income excludes compensation.' for i in range(120)]
    text = '\n'.join(lines)
    class ManyReviewer:
        def __init__(self):
            self.calls = []
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            self.calls.append(chunk)
            targets = chunk.get('review_claims', [])
            return {'claims': [raw(quote, outcome='unsupported') for quote in targets], 'no_material_claims': not targets}
    model = ManyReviewer()
    result = audit.run_audit(state(), model, inventory=inventory(parts=[('Decision', '5_portfolio', [('PM', 'decision.md', text)])]))
    assert len(model.calls) == 2 and len(model.calls[1]['review_claims']) == 100
    assert result['status'] == 'partial' and result['coverage']['reviewed_chunks'] == 0
    assert len(result['unresolved_repairs']) == 20


@pytest.mark.parametrize('outcome', ['unsupported', 'hypothesis', 'supported'])
def test_complete_treatment_disposition_does_not_add_an_unnecessary_repair(monkeypatch, outcome):
    quote = DEFINITION if outcome == 'supported' else CLAIM
    source = {**SOURCE, 'text': quote}
    monkeypatch.setattr(audit, '_source_index', lambda state: ({('issuer', 'reconciliation'): source}, []))
    class FullReviewer:
        calls = 0
        def invoke(self, prompt):
            self.calls += 1
            return {'claims': [raw(quote, outcome=outcome, excerpt=quote)], 'no_material_claims': False}
    model = FullReviewer()
    result = audit.run_audit(state(), model, inventory=inventory(parts=[('Decision', '5_portfolio', [('PM', 'decision.md', quote)])]))
    assert model.calls == 1 and result['coverage']['reviewed_chunks'] == 1


def test_final_treatment_check_keeps_oversized_unquotable_statement_partial():
    text = 'Before treating compensation as a real cost, ' + 'additional context ' * 330 + 'the conclusion is conditional.'
    inv = audit.build_inventory(state(), parts=[('Decision', '5_portfolio', [('PM', 'decision.md', text)])],
                                summary_text='', chunk_characters=10000)
    assert len(inv['chunks']) == 1 and len(text) > 6000
    class EmptyReviewer:
        calls = 0
        def invoke(self, prompt):
            self.calls += 1
            return {'claims': [], 'no_material_claims': True}
    model = EmptyReviewer()
    result = audit.run_audit(state(), model, inventory=inv)
    assert model.calls == 1
    assert result['status'] == 'partial' and result['coverage']['reviewed_chunks'] == 0
    assert result['coverage']['remaining_chunks']
