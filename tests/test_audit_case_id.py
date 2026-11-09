"""Case-linked findings retain exact identity without rekeying legacy findings."""

from copy import deepcopy

from tests.test_advisory_audit import FakeModel
from tests.test_shared_valuation import state as case_state
from tests.test_valuation import pe_request
from tradingagents.agents.audit_pass import (
    _contexts,
    _finding_id,
    create_advisory_audit,
    prepare_audit_dispositions,
    render_advisory_audit,
)
from tradingagents.agents.shared_valuation import prepare_shared_valuation


def _state():
    state = case_state([{'name': 'Base', 'request': pe_request()}])
    state['shared_valuation_scenarios'] = prepare_shared_valuation(state)
    case = state['shared_valuation_scenarios']['rows'][0]
    quote = 'Base case assumes a 20 multiple.'
    state['investment_plan'] = quote
    return state, case, quote


def test_case_id_is_in_bounded_audit_context_and_survives_disposition():
    state, case, quote = _state()
    source, _ = _contexts(state)
    assert case['case_id'] in source['shared_valuation_cases']
    finding = {'role': 'research_manager', 'quoted_claim': quote,
               'issue_type': 'numerical_inconsistency', 'evidence_label': None,
               'explanation': 'Input is inconsistent.', 'case_id': case['case_id']}
    record = create_advisory_audit(FakeModel({'findings': [finding]}),
                                   deep_model_id='d', quick_model_id='q')(state)['advisory_audit']
    assert record['accepted_count'] == 1
    saved = record['findings'][0]
    assert saved['case_id'] == case['case_id']
    projected = prepare_audit_dispositions({**state, 'advisory_audit': record,
        'unvalidated_outputs': {'portfolio_manager': {'structured': {'audit_dispositions': [
            {'finding_id': saved['finding_id'], 'disposition': 'accepted', 'reason': 'Agree'}]}}}})
    assert projected['findings'][0]['case_id'] == case['case_id']
    assert projected['findings'][0]['disposition'] == 'accepted'
    assert case['case_id'] in render_advisory_audit(record, dispositions=projected)


def test_unknown_case_id_rejects_only_its_finding():
    state, case, quote = _state()
    base = {'role': 'research_manager', 'quoted_claim': quote,
            'issue_type': 'numerical_inconsistency', 'evidence_label': None,
            'explanation': 'Input is inconsistent.'}
    findings = [{**base, 'case_id': 'case-not-in-source'}, {**base, 'case_id': case['case_id']}]
    record = create_advisory_audit(FakeModel({'findings': findings}),
                                   deep_model_id='d', quick_model_id='q')(state)['advisory_audit']
    assert record['accepted_count'] == 1 and record['rejected_count'] == 1
    assert record['findings'][0]['case_id'] == case['case_id']
    assert 'case' in record['rejection_reasons'][0]


def test_optional_case_id_does_not_rekey_legacy_finding():
    state, case, quote = _state()
    plain = {'role': 'research_manager', 'quoted_claim': quote,
             'issue_type': 'numerical_inconsistency', 'evidence_label': None,
             'explanation': 'Input is inconsistent.'}
    scope = {'company_of_interest': 'DOCN', 'trade_date': '2026-10-19', 'run_id': ''}
    legacy = _finding_id(plain, scope)
    assert _finding_id({**plain, 'case_id': None}, scope) == legacy
    assert _finding_id({**plain, 'case_id': case['case_id']}, scope) != legacy
    copied = deepcopy(plain)
    copied['finding_id'] = 'forged'
    assert _finding_id(copied, scope) == legacy
