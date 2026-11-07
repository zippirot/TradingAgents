"""The final factual review respects publication and per-run cost boundaries."""
from copy import deepcopy

from tradingagents import ground_truth_flow as flow


def test_disabled_never_invokes_auditor(monkeypatch):
    monkeypatch.setattr(flow, '_audit_pass', lambda *a, **k: (_ for _ in ()).throw(AssertionError('called')))
    state = {'final_rating': 'Hold'}
    before = deepcopy(state)
    flow.audit_before_publication(state, object(), {})
    flow.audit_after_summary(state, object(), {})
    assert state == before


def test_only_verified_material_contradictions_trigger_one_reassessment(monkeypatch):
    state = {'final_rating': 'Hold', 'final_trade_decision': 'Hold'}
    calls = []
    findings = {'claims': [
        {'outcome': 'unsupported', 'decision_material': True, 'code_verified': True},
        {'outcome': 'contradicted', 'decision_material': True, 'code_verified': True,
         'quoted_claim': 'Revenue is 10', 'correction': 'Revenue is 20'},
    ]}
    monkeypatch.setattr(flow, '_audit_pass', lambda *a: findings)
    def reassess(candidate, corrections, model):
        calls.append(corrections)
        return {'final_rating': 'Underweight', 'final_trade_decision': 'Underweight'}
    flow.audit_before_publication(state, None, {'ground_truth_audit': True}, reassess=reassess, validate=lambda s: {})
    assert len(calls) == 1 and len(calls[0]) == 1
    assert state['final_rating'] == 'Underweight'
    assert state['ground_truth_reassessment']['original_rating'] == 'Hold'
    assert state['ground_truth_reassessment']['status'] == 'completed'


def test_semantic_suspicion_does_not_trigger_rating_change(monkeypatch):
    state = {'final_rating': 'Hold'}
    monkeypatch.setattr(flow, '_audit_pass', lambda *a: {'claims': [
        {'outcome': 'contradicted', 'decision_material': True, 'code_verified': False}]})
    def forbidden(*args):
        raise AssertionError('semantic claim changed rating')
    flow.audit_before_publication(state, None, {'ground_truth_audit': True}, reassess=forbidden)
    assert state['final_rating'] == 'Hold'


def test_review_gate_skips_reassessment(monkeypatch):
    state = {'final_rating': 'REVIEW', 'evidence_quality': {'status': 'insufficient'}}
    monkeypatch.setattr(flow, '_audit_pass', lambda *a: {'claims': []})
    flow.audit_before_publication(state, None, {'ground_truth_audit': True}, reassess=lambda *a: (_ for _ in ()).throw(AssertionError()))
    assert state['final_rating'] == 'REVIEW'


def test_disabled_signature_matches_legacy_but_enabled_is_distinct():
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    app = object.__new__(TradingAgentsGraph)
    app.config = {'max_debate_rounds': 1, 'max_risk_discuss_rounds': 1}
    app.selected_analysts = ['market']
    legacy = app._run_signature('stock')
    app.config['ground_truth_audit'] = False
    assert app._run_signature('stock') == legacy
    app.config['ground_truth_audit'] = True
    assert app._run_signature('stock') != legacy


def test_final_audit_after_summary_is_saved_and_frozen_retry_is_offline(tmp_path, monkeypatch):
    from tests.test_publication_graph import graph_and_state
    from tradingagents.memory.publication import list_records
    app, state = graph_and_state(tmp_path)
    app.config['ground_truth_audit'] = True
    stages = []

    def audit(candidate, llm, config):
        stages.append((bool(candidate.get('publication_record')), bool(candidate.get('executive_summary'))))
        return {'status': 'completed', 'claims': [], 'phase': len(stages)}

    monkeypatch.setattr(flow, '_audit_pass', audit)
    app.record_decision('DOCN', state['trade_date'], state)
    assert stages == [(False, False), (True, True)]
    original = deepcopy(list_records(app.config))
    final = deepcopy(state['ground_truth_audit'])
    del state['ground_truth_audit']
    app.record_decision('DOCN', state['trade_date'], state)
    assert state['ground_truth_audit'] == final
    assert len(stages) == 2
    assert list_records(app.config) == original


def test_failed_reassessment_preserves_original_rating_and_flags_review(monkeypatch):
    state = {'final_rating': 'Hold', 'final_trade_decision': 'Hold'}
    monkeypatch.setattr(flow, '_audit_pass', lambda *a: {'claims': [
        {'outcome': 'contradicted', 'decision_material': True, 'code_verified': True, 'correction': 'corrected'}]})
    def broken(*args):
        raise ValueError('private details')
    flow.audit_before_publication(state, None, {'ground_truth_audit': True}, reassess=broken)
    assert state['final_rating'] == 'Hold'
    assert state['ground_truth_reassessment']['status'] == 'unavailable'
    assert 'private details' not in str(state)


def test_pm_fallback_shares_request_budget():
    import pytest
    class Model:
        def invoke(self, prompt):
            return prompt
        def with_structured_output(self, schema):
            return self
    progress = {'requests': 0, 'elapsed_seconds': 0}
    model = flow._BudgetedModel(Model(), progress, {'ground_truth_max_requests': 1})
    assert model.with_structured_output(object()).invoke('one') == 'one'
    with pytest.raises(RuntimeError, match='budget exhausted'):
        model.invoke('fallback')
    assert progress['requests'] == 1


def test_real_engine_passes_share_budget_and_final_result_matches_delivered_inventory():
    from tests.test_ground_truth_audit import state as source_state
    from tradingagents.ground_truth import resolve_audit
    from tradingagents.ground_truth_display import build_report_inventory
    class Model:
        def __init__(self):
            self.calls = 0
        def invoke(self, prompt):
            self.calls += 1
            return {'claims': [], 'no_material_claims': True}
    candidate = source_state()
    candidate.update(final_rating='Hold', final_trade_decision='The outlook is uncertain.')
    model = Model()
    config = {'ground_truth_audit': True, 'ground_truth_max_requests': 2}
    flow.audit_before_publication(candidate, model, config)
    before = model.calls
    flow.audit_after_summary(candidate, model, config)
    assert 0 < before <= model.calls <= 2
    assert candidate['ground_truth_execution']['requests'] == model.calls
    final = candidate['ground_truth_audit']
    assert final['digest'] == build_report_inventory(candidate)['digest']
    assert resolve_audit(candidate, final, inventory=build_report_inventory(candidate))['status'] == final['status']


def test_literal_primary_source_correction_reaches_one_independent_pm_reassessment(monkeypatch):
    from tests.test_ground_truth_audit import Model, state as source_state
    from tradingagents import ground_truth_display
    from tradingagents.ground_truth import build_inventory

    candidate = source_state()
    candidate['filing_evidence']['documents'][0]['blocks'][0]['text'] = 'Revenue was 20 USD.'
    candidate.update(final_rating='Hold', final_trade_decision='Revenue was 100 USD.')
    parts = [('Decision', '5_portfolio', [('PM', 'decision.md', 'Revenue was 100 USD.')])]
    monkeypatch.setattr(ground_truth_display, 'build_report_inventory',
                        lambda state: build_inventory(state, parts=parts, summary_text=''))
    model = Model({'no_material_claims': False, 'claims': [{
        'quoted_claim': 'Revenue was 100 USD.', 'outcome': 'contradicted',
        'decision_material': True, 'explanation': 'The dated filing reports 20 USD.',
        'correction': 'Revenue was 20 USD.',
        'evidence': [{'source_id': 'doc-1', 'locator': 'table-1', 'quote': 'Revenue was 20 USD.'}],
    }]})
    calls = []
    def reconsider(state, corrections, budgeted_model):
        calls.append(corrections)
        assert 'independently assess' in state['investment_plan']
        assert corrections[0]['evidence'][0]['known_at'] == '2026-11-03'
        assert corrections[0]['code_verified'] is False
        # The PM can independently retain the original rating after review.
        return {'final_rating': 'Hold', 'final_trade_decision': 'Revenue was 20 USD.'}
    flow.audit_before_publication(candidate, model, {'ground_truth_audit': True},
                                  reassess=reconsider, validate=lambda s: {})
    flow.audit_before_publication(candidate, model, {'ground_truth_audit': True},
                                  reassess=reconsider, validate=lambda s: {})
    assert len(calls) == 1
    assert candidate['final_rating'] == 'Hold'
    assert candidate['ground_truth_reassessment']['status'] == 'completed'


def test_vendor_only_or_missing_literal_replacement_never_triggers_pm(monkeypatch):
    for kind, quote, outcome in [('attributed vendor output', 'Revenue was 20 USD.', 'contradicted'),
                                  ('filing passage', 'Revenue was 30 USD.', 'contradicted'),
                                  ('filing passage', 'Revenue was 20 USD.', 'unsupported')]:
        candidate = {'final_rating': 'Hold'}
        finding = {'outcome': outcome, 'decision_material': True, 'code_verified': False,
                   'correction': 'Revenue was 20 USD.', 'verification': {'source_quotes_validated': True},
                   'evidence': [{'kind': kind, 'quote': quote}]}
        monkeypatch.setattr(flow, '_audit_pass', lambda *a, finding=finding: {'claims': [finding]})
        def forbidden(*args):
            raise AssertionError('unsupported correction reached the PM')
        flow.audit_before_publication(candidate, None, {'ground_truth_audit': True}, reassess=forbidden)
        assert 'ground_truth_reassessment' not in candidate


def test_pm_and_audit_phases_share_token_allowance_and_preserve_zero(monkeypatch):
    from types import SimpleNamespace

    class Model:
        def __init__(self):
            self.calls = 0
        def invoke(self, prompt):
            self.calls += 1
            return SimpleNamespace(usage_metadata={'input_tokens': 2, 'output_tokens': 3})
    model = Model()
    progress = {'requests': 0, 'elapsed_seconds': 0}
    wrapped = flow._BudgetedModel(model, progress, {'ground_truth_max_tokens': 100000})
    wrapped.invoke('Test prompt')
    assert progress['budget_tokens'] == 5
    state = {'ground_truth_execution': progress}
    assert flow._remaining_config(state, {'ground_truth_max_tokens': 5})['ground_truth_max_tokens'] == 0
    import pytest
    wrapped = flow._BudgetedModel(model, progress, {'ground_truth_max_tokens': 5})
    with pytest.raises(RuntimeError, match='token budget exhausted'):
        wrapped.invoke('Another prompt')
    assert model.calls == 1
    assert progress['requests'] == 1
