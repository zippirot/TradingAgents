"""The previous PM version remains readable without replacing the current one."""
import json
from copy import deepcopy
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tests import test_graph_end_to_end as graph_fixture
from tests.test_graph_end_to_end import offline as offline
from tests.test_ground_truth_audit import state as source_state
from tradingagents import ground_truth_flow as flow
from tradingagents.agents import schemas
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.ground_truth import resolve_audit
from tradingagents.ground_truth_display import build_report_inventory
from tradingagents.report_html import render_report
from tradingagents.reporting import prepare_report_state, write_report_tree

OLD_REASON = 'ORIGINAL_REASONING_SENTINEL <script>historical-injection</script> [unsafe](javascript:alert(1))'
OLD_CLAIM = 'ORIGINAL_WRONG_CLAIM_SENTINEL: Revenue was 99 USD.'
CORRECTION = 'CORRECTED_OLD_CLAIM_SENTINEL: Revenue was 100 USD.'
SOURCE_QUOTE = CORRECTION + ' Period 2026-07-01 to 2026-09-30; USD; US-GAAP.'
NEW_REASON = 'REAL_PM_NEW_REASONING_SENTINEL'


class HistoryModel(graph_fixture.ScriptedModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = messages[-1].content if messages else ''
        if isinstance(prompt, str) and '\nREPORT CHUNK:\n' in prompt:
            self._count()
            chunk = json.loads(prompt.split('REPORT CHUNK:\n', 1)[1].split('\nSUPPLIED SOURCES', 1)[0])
            claims = [{'quoted_claim': chunk['text'], 'outcome': 'hypothesis', 'decision_material': False,
                       'explanation': 'Scripted history wiring fixture.', 'evidence': []}]
            if OLD_CLAIM in chunk['text']:
                claims.append({'quoted_claim': OLD_CLAIM, 'outcome': 'contradicted', 'decision_material': True,
                               'explanation': 'The retained fixture reports a different amount.', 'correction': CORRECTION, 'correction_scope': 'complete_claim',
                               'evidence': [{'source_id': 'doc-1', 'locator': 'table-1', 'quote': SOURCE_QUOTE}]})
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps({
                'claims': claims, 'no_material_claims': False})))])
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def seed():
    state = source_state()
    state['filing_evidence']['documents'][0]['blocks'][0]['text'] = SOURCE_QUOTE
    old = '**Rating**: Buy\n\n' + OLD_REASON + '\n\n' + OLD_CLAIM
    state.update(run_id=str(uuid4()), run_settings={'ground_truth_audit': True}, asset_type='stock',
                 final_rating='Buy', final_trade_decision=old,
                 evidence_quality={'schema_version': 1, 'scope': 'not_applicable', 'status': 'limited',
                                   'checks': [{'code': 'scope', 'status': 'not_applicable',
                                               'message': 'Fundamentals not selected'}], 'warnings': []},
                 unvalidated_outputs={'final_trade_decision': old}, investment_plan='', trader_investment_plan='',
                 market_report='', sentiment_report='', news_report='', fundamentals_report='',
                 investment_debate_state={'bull_history': '', 'bear_history': '', 'history': '', 'current_response': ''},
                 risk_debate_state={**dict.fromkeys(('aggressive_history', 'conservative_history', 'neutral_history',
                     'history', 'current_aggressive_response', 'current_conservative_response', 'current_neutral_response'), ''),
                     'count': 0})
    state.update(enforce_publication(state))
    return state


def finish(tmp_path, monkeypatch, *, validation_fails=False):
    state = seed()
    original = deepcopy(state)
    decision = graph_fixture.STRUCTURED[schemas.RequiredHorizonPortfolioDecision].model_copy(update={
        'rating': schemas.PortfolioRating.HOLD, 'executive_summary': NEW_REASON, 'investment_thesis': NEW_REASON})
    monkeypatch.setitem(graph_fixture.STRUCTURED, schemas.RequiredHorizonPortfolioDecision, decision)
    model = HistoryModel(structured=True)
    callbacks = []

    def reconsider(candidate, corrections, budgeted_model):
        callbacks.append(deepcopy(corrections))
        # Real PM node, including its structured metadata and its old diagnostic cache.
        return create_portfolio_manager(budgeted_model)(candidate)

    def validate(candidate):
        if validation_fails:
            candidate['unvalidated_outputs']['final_trade_decision'] = 'FAILED_VALIDATION_MUTATION'
            raise ValueError('invalid revision')
        return enforce_publication(candidate)

    config = {'ground_truth_audit': True, 'results_dir': str(tmp_path), 'ground_truth_max_requests': 64}
    flow.audit_before_publication(state, model, config, reassess=reconsider, validate=validate)
    flow.audit_after_summary(state, model, config)
    return state, original, model, callbacks


def test_real_typed_pm_refreshes_readable_prose_and_retains_exact_original(tmp_path, monkeypatch, offline):
    state, original, _, calls = finish(tmp_path, monkeypatch)
    old_prepared = next(section['text'] for section in build_report_inventory(original)['sections']
                        if section['section_id'] == '5_portfolio/decision.md')
    assert len(calls) == 1
    assert OLD_REASON not in original['final_trade_decision']
    assert state['ground_truth_reassessment']['original_decision'] == old_prepared
    assert NEW_REASON in prepare_report_state(state)['final_trade_decision']
    assert OLD_REASON not in prepare_report_state(state)['final_trade_decision']
    assert state['final_rating'] == 'Hold'
    assert state['unvalidated_outputs']['portfolio_manager']['structured']['investment_thesis'] == NEW_REASON
    assert state['target_validation']['status'] == 'unsupported'
    assert state['target_validation']['target'] is None
    assert state['ground_truth_reassessment']['status'] == 'completed'


def test_full_detail_contains_bound_historical_reasoning_corrections_and_sources(tmp_path, monkeypatch, offline):
    state, _, model, calls = finish(tmp_path, monkeypatch)
    record = resolve_audit(state, state['ground_truth_audit'], inventory=build_report_inventory(state))
    assert record['status'] != 'unavailable'
    assert not any(OLD_CLAIM in claim['quoted_claim'] for claim in record['claims'])
    history = record['reassessment_history']
    assert OLD_REASON in history['original_decision']
    assert history['corrections'][0]['quoted_claim'] == OLD_CLAIM
    assert history['corrections'][0]['correction'] == CORRECTION
    before = deepcopy(state)
    count = len(model.calls)
    for folder in ('first', 'reexport'):
        write_report_tree(state, 'DOCN', tmp_path / folder)
        detail = next((tmp_path / folder).glob('ground_truth_audit-*.md')).read_text()
        assert 'Historical reassessment' in detail
        assert 'ORIGINAL_REASONING_SENTINEL' in detail
        assert OLD_CLAIM in detail and CORRECTION in detail
        assert 'doc-1/table-1' in detail and '2026-11-03' in detail
        assert '99 USD' in detail and '100 USD' in detail
        assert '2026-07-01' in detail and '2026-09-30' in detail and 'US-GAAP' in detail
        assert 'Contradicted claims 0, unsupported claims 0' in detail
        assert NEW_REASON in (tmp_path / folder / 'complete_report.md').read_text()
        assert 'historical-injection</script>' not in detail
        assert '[unsafe](javascript:' not in detail
    html = render_report('DOCN', state, None)
    assert 'Historical reassessment' in html and 'ORIGINAL_REASONING_SENTINEL' in html
    assert '<script>historical-injection</script>' not in html
    assert 'href="javascript:' not in html
    assert len(model.calls) == count and len(calls) == 1
    assert state == before
    # Historical text is inside the signed record, not read from mutable state at export.
    changed_history = deepcopy(state)
    changed_history['ground_truth_reassessment']['original_decision'] = 'UNBOUND_HISTORY_SENTINEL'
    changed_history['ground_truth_reassessment']['original_rating'] = 'UNBOUND_RATING_SENTINEL'
    projected = render_report('DOCN', changed_history, None)
    assert 'UNBOUND_HISTORY_SENTINEL' not in projected and 'ORIGINAL_REASONING_SENTINEL' in projected
    assert 'UNBOUND_RATING_SENTINEL' not in projected
    other_run = {**state, 'run_id': str(uuid4())}
    stale_html = render_report('DOCN', other_run, None)
    assert 'Saved audit unavailable' in stale_html
    assert 'ORIGINAL_REASONING_SENTINEL' not in stale_html and OLD_CLAIM not in stale_html
    tampered = deepcopy(state)
    tampered['ground_truth_audit']['reassessment_history']['original_decision'] = 'TAMPERED_HISTORY'
    assert resolve_audit(tampered, inventory=build_report_inventory(tampered))['status'] == 'unavailable'


def test_failed_validation_keeps_previous_readable_candidate_without_cache_mutation(tmp_path, monkeypatch, offline):
    state, original, _, calls = finish(tmp_path, monkeypatch, validation_fails=True)
    assert len(calls) == 1
    assert state['ground_truth_reassessment']['status'] != 'completed'
    assert state['final_rating'] == original['final_rating'] == 'Buy'
    assert state['final_trade_decision'] == original['final_trade_decision']
    assert state['unvalidated_outputs'] == original['unvalidated_outputs']
    assert NEW_REASON not in prepare_report_state(state)['final_trade_decision']
    assert 'FAILED_VALIDATION_MUTATION' not in str(state['unvalidated_outputs'])


def test_unbound_completed_state_cannot_hide_a_current_material_finding():
    from tests.test_ground_truth_audit import Model, inventory, response
    from tradingagents.ground_truth import run_audit, seal_audit
    from tradingagents.ground_truth_display import audit_assessment

    state = source_state()
    output = response()
    output['claims'][1]['decision_material'] = True
    record = run_audit(state, Model(output), inventory=inventory(state))
    record['reassessment_history'] = {'status': 'completed', 'corrections': []}
    record = seal_audit(record)
    forged = {**state, 'ground_truth_reassessment': {
        'status': 'completed', 'corrections': [deepcopy(record['claims'][1])]}}
    text = audit_assessment(record, forged)
    assert 'Recommendation needs review' in text
    assert 'Last claim is 9 USD.' in text
    assert record['reassessment_history']['corrections'] == []


def test_actual_finalizer_publishes_reassessed_history_once_and_reexports_offline(tmp_path, monkeypatch, offline):
    import socket

    from langchain_core.runnables import RunnableLambda
    from pydantic import Field

    from tests.test_publication_graph import graph_and_state
    from tradingagents.memory import TradingMemoryLog
    from tradingagents.memory.publication import list_records
    from tradingagents.report_summary import SummaryOutput

    network = []
    def no_network(*args, **kwargs):
        network.append(True)
        raise AssertionError('No live calls in finalizer fixture')
    monkeypatch.setattr(socket.socket, 'connect', no_network)

    class TrackedPMModel(HistoryModel):
        pm_invocations: list = Field(default_factory=list)

        def with_structured_output(self, schema, **kwargs):
            bound = super().with_structured_output(schema, **kwargs)
            if schema is not schemas.RequiredHorizonPortfolioDecision:
                return bound
            def invoke(payload):
                self.pm_invocations.append(schema.__name__)
                return bound.invoke(payload)
            return RunnableLambda(invoke)

    decision = graph_fixture.STRUCTURED[schemas.RequiredHorizonPortfolioDecision].model_copy(update={
        'rating': schemas.PortfolioRating.HOLD, 'executive_summary': NEW_REASON, 'investment_thesis': NEW_REASON})
    monkeypatch.setitem(graph_fixture.STRUCTURED, schemas.RequiredHorizonPortfolioDecision, decision)
    monkeypatch.setitem(graph_fixture.STRUCTURED, SummaryOutput, {'sentences': [
        {'text': 'The research context constrains assumptions.', 'sections': ['2_research']},
        {'text': 'The trading proposal remains conditional research.', 'sections': ['3_trading']},
        {'text': 'The Portfolio Manager independently revised the decision.', 'sections': ['5_portfolio']},
        {'text': 'Evidence coverage limits the valuation assessment.', 'sections': ['6_evidence']},
    ]})
    app, _ = graph_and_state(tmp_path)
    app.config.update(ground_truth_audit=True, memory_log_path=str(tmp_path / 'memory.md'), ground_truth_max_requests=64)
    app.memory_log = TradingMemoryLog(app.config)
    app.audit_llm = TrackedPMModel(structured=True)
    app.deep_thinking_llm = graph_fixture.ScriptedModel(structured=True)
    state = seed()
    app.record_decision('DOCN', state['trade_date'], state)
    assert len(app.audit_llm.pm_invocations) == 1
    assert state['final_rating'] == 'Hold'
    assert NEW_REASON in prepare_report_state(state)['final_trade_decision']
    assert OLD_REASON not in prepare_report_state(state)['final_trade_decision']
    assert state['executive_summary']['status'] == 'completed'
    record = resolve_audit(state, state['ground_truth_audit'], inventory=build_report_inventory(state))
    assert record['status'] != 'unavailable'
    assert OLD_REASON in record['reassessment_history']['original_decision']
    publications = deepcopy(list_records(app.config))
    assert len(publications) == 1
    memory = deepcopy(app.memory_log.load_entries())
    assert len(memory) == 1 and memory[0]['rating'] == 'Hold'
    assert memory[0]['decision_id'] == state['publication_record']['decision_id'] == publications[0]['decision_id']
    counters = (len(app.audit_llm.calls), len(app.deep_thinking_llm.calls))
    for folder in ('first-finalized-export', 'offline-finalized-reexport'):
        app.save_reports(state, 'DOCN', tmp_path / folder, html=True)
        detail = next((tmp_path / folder).glob('ground_truth_audit-*.md')).read_text()
        assert 'ORIGINAL_REASONING_SENTINEL' in detail and OLD_CLAIM in detail and CORRECTION in detail
        assert 'Historical reassessment' in detail
        for extension in ('md', 'html'):
            report = (tmp_path / folder / f'complete_report.{extension}').read_text()
            assert NEW_REASON in report and 'Saved audit unavailable' not in report
            assert 'ORIGINAL_REASONING_SENTINEL' not in report and OLD_CLAIM not in report
        assert resolve_audit(state, state['ground_truth_audit'], inventory=build_report_inventory(state))['status'] != 'unavailable'
    app.record_decision('DOCN', state['trade_date'], state)
    assert (len(app.audit_llm.calls), len(app.deep_thinking_llm.calls)) == counters
    assert len(app.audit_llm.pm_invocations) == 1
    assert list_records(app.config) == publications
    assert app.memory_log.load_entries() == memory
    assert not network
