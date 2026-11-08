"""Restart proofs use the actual graph finalizer and opted-in audit flow."""
from copy import deepcopy
from uuid import uuid4

import pytest

from tests.test_publication_graph import graph_and_state
from tradingagents import ground_truth_flow
from tradingagents.memory import publication
from tradingagents.memory.log import TradingMemoryLog


class SimulatedProcessExit(BaseException):
    """Bypass recoverable provider-error handling to represent process loss."""


def application(tmp_path, monkeypatch, *, in_flight=False):
    app, checkpoint = graph_and_state(tmp_path)
    app.config.update(ground_truth_audit=True, ground_truth_max_requests=6)
    app.run_settings = lambda: {'ground_truth_audit': True}
    checkpoint.update(run_id=str(uuid4()), run_settings=app.run_settings(),
                      evidence_quality={'status': 'limited', 'checks': []},
                      final_rating='Hold', final_trade_decision='Rating: Hold\nRevenue was 10 USD.',
                      market_report='Original scoped research.')
    app.memory_log = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    events = {'pm': 0, 'audit': 0, 'crashed': False}

    class Model:
        def invoke(self, prompt):
            events['pm'] += 1
            if in_flight and not events['crashed']:
                events['crashed'] = True
                raise SimulatedProcessExit()
            return 'fixture model reply'
    app.deep_thinking_llm = Model()
    app.audit_llm = app.deep_thinking_llm

    def audit(state, model, config):
        progress = state.setdefault('ground_truth_execution', {'requests': 0, 'elapsed_seconds': 0., 'budget_tokens': 0})
        if progress['requests'] >= config['ground_truth_max_requests']:
            return {'status': 'partial', 'claims': [], 'limits': ['request budget exhausted']}
        events['audit'] += 1
        progress['requests'] += 1
        progress['budget_tokens'] += 10
        findings = [] if 'Changed scoped research.' in str(state.get('market_report')) else [{
            'quoted_claim': 'Revenue was 10 USD.', 'correction': 'Revenue was 20 USD.',
            'outcome': 'contradicted', 'decision_material': True, 'code_verified': True,
        }]
        return {'status': 'completed with findings', 'claims': findings}

    def pm_factory(model):
        def pm(state):
            model.invoke('fixture reassessment')
            return {'final_rating': 'Hold', 'final_trade_decision': 'Rating: Hold\nRevenue was 20 USD.'}
        return pm

    monkeypatch.setattr(ground_truth_flow, '_audit_pass', audit)
    monkeypatch.setattr('tradingagents.agents.managers.portfolio_manager.create_portfolio_manager', pm_factory)
    monkeypatch.setattr('tradingagents.graph.trading_graph.generate_summary', lambda *a: {'status': 'unavailable'})
    return app, checkpoint, events


def interrupt_before_publish(monkeypatch):
    original = publication.publish
    def fail(*args, **kwargs):
        raise OSError('fixture publication interrupted')
    monkeypatch.setattr(publication, 'publish', fail)
    return original


def test_completed_reassessment_survives_restart_before_publication(tmp_path, monkeypatch):
    app, checkpoint, events = application(tmp_path, monkeypatch)
    publish = interrupt_before_publish(monkeypatch)
    first = deepcopy(checkpoint)
    with pytest.raises(OSError, match='publication interrupted'):
        app.record_decision('DOCN', checkpoint['trade_date'], first)
    assert events['pm'] == 1
    monkeypatch.setattr(publication, 'publish', publish)
    resumed = deepcopy(checkpoint)
    app.record_decision('DOCN', checkpoint['trade_date'], resumed)
    assert events['pm'] == 1
    assert resumed['ground_truth_reassessment']['status'] == 'completed'
    assert resumed['ground_truth_reassessment']['original_rating'] == 'Hold'
    assert len(publication.list_records(app.config)) == 1


def test_in_flight_reassessment_never_automatically_repeats_after_restart(tmp_path, monkeypatch):
    app, checkpoint, events = application(tmp_path, monkeypatch, in_flight=True)
    with pytest.raises(SimulatedProcessExit):
        app.record_decision('DOCN', checkpoint['trade_date'], deepcopy(checkpoint))
    resumed = deepcopy(checkpoint)
    app.record_decision('DOCN', checkpoint['trade_date'], resumed)
    assert events['pm'] == 1
    assert resumed['ground_truth_reassessment']['status'] != 'completed'
    assert 'review' in str(resumed['ground_truth_reassessment']).lower()


def test_shared_usage_is_recovered_instead_of_reset_by_terminal_checkpoint(tmp_path, monkeypatch):
    app, checkpoint, events = application(tmp_path, monkeypatch)
    publish = interrupt_before_publish(monkeypatch)
    first = deepcopy(checkpoint)
    with pytest.raises(OSError):
        app.record_decision('DOCN', checkpoint['trade_date'], first)
    requests_before = first['ground_truth_execution']['requests']
    tokens_before = first['ground_truth_execution']['budget_tokens']
    monkeypatch.setattr(publication, 'publish', publish)
    resumed = deepcopy(checkpoint)
    app.record_decision('DOCN', checkpoint['trade_date'], resumed)
    usage = resumed['ground_truth_execution']
    assert usage['requests'] == events['audit'] + events['pm']
    assert requests_before <= usage['requests'] <= app.config['ground_truth_max_requests']
    assert usage['budget_tokens'] >= tokens_before


@pytest.mark.parametrize('change_run', [False, True])
def test_changed_report_or_new_run_rejects_old_correction(tmp_path, monkeypatch, change_run):
    app, checkpoint, events = application(tmp_path, monkeypatch)
    publish = interrupt_before_publish(monkeypatch)
    with pytest.raises(OSError):
        app.record_decision('DOCN', checkpoint['trade_date'], deepcopy(checkpoint))
    resumed = deepcopy(checkpoint)
    resumed['market_report'] = 'Changed scoped research.'
    resumed['final_trade_decision'] = 'Rating: Hold\nA revised thesis.'
    if change_run:
        resumed['run_id'] = str(uuid4())
    monkeypatch.setattr(publication, 'publish', publish)
    app.record_decision('DOCN', checkpoint['trade_date'], resumed)
    assert events['pm'] == 1
    assert resumed.get('ground_truth_reassessment', {}).get('status') != 'completed'
    assert not resumed.get('ground_truth_reassessment', {}).get('corrections')


def test_unknown_audit_request_reserves_remaining_allowance_across_restart(tmp_path, monkeypatch):
    actual_audit = ground_truth_flow._audit_pass
    app, checkpoint, events = application(tmp_path, monkeypatch, in_flight=True)
    monkeypatch.setattr(ground_truth_flow, '_audit_pass', actual_audit)
    with pytest.raises(SimulatedProcessExit):
        app.record_decision('DOCN', checkpoint['trade_date'], deepcopy(checkpoint))
    resumed = deepcopy(checkpoint)
    app.record_decision('DOCN', checkpoint['trade_date'], resumed)
    assert events['pm'] == 1  # The interrupted model call was the first audit, before PM.
    assert resumed['ground_truth_execution']['requests'] == app.config['ground_truth_max_requests']
    assert resumed['ground_truth_audit']['status'] in {'partial', 'unavailable'}


def test_unpublished_recovery_never_overwrites_an_existing_daily_state_log(tmp_path, monkeypatch):
    app, checkpoint, _ = application(tmp_path, monkeypatch)
    log = tmp_path / 'DOCN/TradingAgentsStrategy_logs' / f"full_states_log_{checkpoint['trade_date']}.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    existing = '{"run_id":"previous-published-run","publication_record":{"decision_id":"previous"}}'
    log.write_text(existing)
    interrupt_before_publish(monkeypatch)
    with pytest.raises(OSError):
        app.record_decision('DOCN', checkpoint['trade_date'], deepcopy(checkpoint))
    assert log.read_text() == existing


@pytest.mark.parametrize('revised_rating', ['Hold', 'Underweight'])
def test_concurrent_finalizers_for_same_run_share_one_pm_call(tmp_path, monkeypatch, revised_rating):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    app, checkpoint, events = application(tmp_path, monkeypatch)
    entered, repeated, release = Event(), Event(), Event()
    guard = Lock()
    count = 0
    original_invoke = app.audit_llm.invoke
    def held_model(prompt):
        nonlocal count
        with guard:
            count += 1
            first = count == 1
        if first:
            entered.set()
            assert release.wait(3), 'fixture first PM request was never released'
        else:
            repeated.set()
        return original_invoke(prompt)
    monkeypatch.setattr(app.audit_llm, 'invoke', held_model)
    def factory(model):
        def reconsider(state):
            model.invoke('fixture reassessment')
            return {'final_rating': revised_rating,
                    'final_trade_decision': f'Rating: {revised_rating}\nRevenue was 20 USD.'}
        return reconsider
    monkeypatch.setattr('tradingagents.agents.managers.portfolio_manager.create_portfolio_manager', factory)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(app.record_decision, 'DOCN', checkpoint['trade_date'], deepcopy(checkpoint))
        assert entered.wait(3), 'fixture first finalizer did not reach PM'
        second = executor.submit(app.record_decision, 'DOCN', checkpoint['trade_date'], deepcopy(checkpoint))
        try:
            assert not repeated.wait(.2), 'same-run concurrent finalizer repeated the PM'
        finally:
            release.set()
        first.result(timeout=3)
        second.result(timeout=3)
    assert events['pm'] == 1
    records = publication.list_records(app.config)
    assert len(records) == 1 and records[0]['canonical_rating'] == revised_rating


def test_unexpected_audit_exception_keeps_conservative_usage_reservation(tmp_path, monkeypatch):
    import tradingagents.ground_truth as engine

    actual_audit = ground_truth_flow._audit_pass
    app, checkpoint, events = application(tmp_path, monkeypatch)
    monkeypatch.setattr(ground_truth_flow, '_audit_pass', actual_audit)
    calls = []
    def unknown_outcome(state, model, config, **kwargs):
        if config['ground_truth_max_requests'] == 0:
            return {'status': 'partial', 'claims': [], 'usage': {'requests': 0, 'budget_tokens': 0}}
        calls.append(1)
        raise RuntimeError('unexpected internal audit failure after possible invocation')
    monkeypatch.setattr(engine, 'run_audit', unknown_outcome)
    state = deepcopy(checkpoint)
    app.record_decision('DOCN', checkpoint['trade_date'], state)
    assert len(calls) == 1
    assert state['ground_truth_execution']['requests'] == app.config['ground_truth_max_requests']
    assert state['ground_truth_execution']['budget_tokens'] > 0


def test_disabled_run_has_no_recovery_sidecar_or_lock(tmp_path, monkeypatch):
    from tradingagents import ground_truth_recovery

    app, state = graph_and_state(tmp_path)
    monkeypatch.setattr(ground_truth_recovery, 'run_scope', lambda *a: (_ for _ in ()).throw(AssertionError('disabled lock')))
    app.record_decision('DOCN', state['trade_date'], state)
    assert not list(tmp_path.rglob('ground_truth_progress_*'))


@pytest.mark.parametrize('keep_marker', [False, True])
def test_mutated_existing_publication_keeps_full_immutable_comparison(tmp_path, monkeypatch, keep_marker):
    app, checkpoint, _ = application(tmp_path, monkeypatch)
    finalized = deepcopy(checkpoint)
    app.record_decision('DOCN', checkpoint['trade_date'], finalized)
    original = deepcopy(publication.list_records(app.config))
    mutated = deepcopy(finalized)
    mutated['final_trade_decision'] = 'Sell. Changed canonical decision.'
    mutated['final_rating'] = 'Sell'
    if not keep_marker:
        mutated.pop('publication_record', None)
    with pytest.raises(ValueError, match='different canonical content'):
        app.record_decision('DOCN', checkpoint['trade_date'], mutated)
    assert publication.list_records(app.config) == original


@pytest.mark.parametrize('repeated', [False, True])
def test_ambiguous_source_bound_correction_has_no_pm_authority(tmp_path, monkeypatch, repeated):
    import json

    from tests.test_ground_truth_audit import state as source_state
    from tradingagents import ground_truth_display
    from tradingagents.ground_truth import build_inventory

    candidate = source_state()
    candidate['filing_evidence']['documents'][0]['blocks'][0]['text'] = 'Revenue was 20 USD.'
    original = 'Revenue was 100 USD.'
    body = '\n\n'.join([original] * (2 if repeated else 1))
    candidate.update(final_rating='Hold', final_trade_decision=body)
    monkeypatch.setattr(ground_truth_display, 'build_report_inventory', lambda state: build_inventory(
        state, parts=[('Decision', '5_portfolio', [('PM', 'decision.md', state['final_trade_decision'])])],
        summary_text=''))
    class Reviewer:
        def invoke(self, prompt):
            chunk = json.loads(prompt.split('REPORT CHUNK:\n')[1].split('\nSUPPLIED SOURCES')[0])
            wrong = original in chunk['text']
            return {'no_material_claims': False, 'claims': [{
                'quoted_claim': original if wrong else chunk['text'],
                'outcome': 'contradicted' if wrong else 'supported',
                'decision_material': True, 'explanation': 'The retained source reports a different value.',
                **({'correction': 'Revenue was 20 USD.', 'correction_scope': 'complete_claim'} if wrong else {}),
                'evidence': [{'source_id': 'doc-1', 'locator': 'table-1', 'quote': 'Revenue was 20 USD.'}]}]}
    calls = []
    def reconsider(state, corrections, model):
        calls.append(corrections)
        return {'final_rating': 'Hold', 'final_trade_decision': 'Revenue was 20 USD.'}
    ground_truth_flow.audit_before_publication(candidate, Reviewer(), {'ground_truth_audit': True},
                                              reassess=reconsider, validate=lambda state: {})
    assert len(calls) == (0 if repeated else 1)
    assert candidate['final_rating'] == 'Hold'
    if repeated:
        findings = candidate['ground_truth_prepublication']['claims']
        assert findings[0]['ambiguous_location'] is True
        assert findings[0]['verification']['source_quotes_validated'] is True
        assert 'ground_truth_reassessment' not in candidate
        assessment = ground_truth_display.audit_assessment(candidate['ground_truth_prepublication'], candidate)
        assert 'Recommendation needs review' in assessment
        assert original in assessment
