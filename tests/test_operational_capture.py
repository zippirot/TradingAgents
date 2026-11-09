"""Operational observations come from real graph and routing boundaries."""
import pytest

from tests.test_graph_end_to_end import TRADE_DATE, ScriptedModel, _graph, offline  # noqa: F401


@pytest.mark.unit
@pytest.mark.parametrize('debug', [False, True])
def test_completed_graph_retains_actual_run_bound_stages(tmp_path, monkeypatch, offline, debug):  # noqa: F811
    graph = _graph(tmp_path, monkeypatch, ScriptedModel(), debug=debug)
    state, _ = graph.propagate('NVDA', TRADE_DATE)
    rows = list(state.get('operational_observations', {}).values())
    stages = {r['stage'] for r in rows}
    assert {'Source Acquisition', 'Market Analyst', 'Portfolio Manager', 'Run Metrics'} <= stages
    assert all(r['run_id'] == state['run_id'] for r in rows)
    assert all(r['ticker'] == 'NVDA' and r['trade_date'] == TRADE_DATE for r in rows)
    source = next(r for r in rows if r['stage'] == 'Source Acquisition' and r['code'] == 'completed')
    assert set(source['expected_stages']) <= stages


@pytest.mark.unit
@pytest.mark.parametrize('recovered', [False, True])
def test_router_observes_recovered_or_exhausted_vendor_failure(monkeypatch, recovered):
    from tradingagents.dataflows import router
    from tradingagents.dataflows.config import run_config
    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.operational_capture import observed_node

    def fail(*args, **kwargs):
        raise VendorUnavailableError('private exception must never be copied')

    vendors = {'yfinance': fail, 'alpha_vantage': (lambda *a, **kw: 'usable') if recovered else fail}
    monkeypatch.setitem(router.VENDOR_METHODS, 'get_stock_data', vendors)
    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    with run_config({'data_vendors': {'core_stock_apis': 'yfinance,alpha_vantage'}}):
        result = observed_node(lambda s: {'answer': router.route_to_vendor('get_stock_data', 'NVDA')},
                               'Market Analyst')(state, {})
    rows = list(result['operational_observations'].values())
    code = 'vendor_fallback_recovered' if recovered else 'vendor_unavailable'
    assert code in {r['code'] for r in rows}
    assert 'private exception' not in str(rows)


@pytest.mark.unit
def test_caught_acquisition_outage_is_retained_on_intentional_review(tmp_path, monkeypatch, offline):  # noqa: F811
    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.dataflows.vendors import sec_edgar
    from tradingagents.operational_audit import assess_audit

    def unavailable(*args, **kwargs):
        raise VendorUnavailableError('private request details')

    monkeypatch.setattr(sec_edgar, 'cik_for', unavailable)
    graph = _graph(tmp_path, monkeypatch, ScriptedModel(),
                   selected_analysts=('market', 'social', 'news', 'fundamentals'))
    state, signal = graph.propagate('NVDA', TRADE_DATE)
    assert signal == 'REVIEW'
    assessment = assess_audit(state)
    assert assessment['score'] == 3
    assert any(r['code'] == 'vendor_unavailable' for r in state['operational_observations'].values())
    assert 'private request details' not in str(state['operational_observations'])


@pytest.mark.unit
def test_caught_advisory_failure_is_an_operational_incident():
    from tradingagents.operational_capture import observed_node

    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    result = observed_node(lambda s: {'advisory_audit': {'status': 'unavailable'}},
                           'Advisory Audit')(state, {})
    assert {r['code'] for r in result['operational_observations'].values()} == {'empty_output'}


@pytest.mark.unit
@pytest.mark.parametrize('outage', [False, True])
def test_real_finalization_exports_clean_or_degraded_assessment(tmp_path, monkeypatch, offline, outage):  # noqa: F811
    from langchain_core.runnables import RunnableLambda

    from tests.test_report_summary import FakeLLM, valid_payload
    from tradingagents.agents.audit_pass import AuditOutput
    from tradingagents.graph import trading_graph
    from tradingagents.operational_audit import assess_audit
    from tradingagents.report_summary import generate_summary

    class CompleteModel(ScriptedModel):
        def bind_tools(self, tools, **kwargs):
            # This fixture has vendor responses but no retained document corpus.
            # Choose the applicable vendor tools instead of inventing a document query.
            return super().bind_tools([t for t in tools if t.name != 'search_documents'], **kwargs)

        def with_structured_output(self, schema, **kwargs):
            if schema is AuditOutput:
                return RunnableLambda(lambda _: {'findings': []})
            return super().with_structured_output(schema, **kwargs)

    payload = valid_payload()
    payload['sentences'][2]['text'] = 'The trader and portfolio manager favored increased exposure.'
    monkeypatch.setattr(trading_graph, 'generate_summary',
                        lambda context, llm: generate_summary(context, FakeLLM(payload)))
    if outage:
        from tradingagents.dataflows import router
        from tradingagents.dataflows.errors import VendorUnavailableError

        def unavailable(*args, **kwargs):
            raise VendorUnavailableError('offline induced outage')
        for vendor in router.VENDOR_METHODS['get_news']:
            monkeypatch.setitem(router.VENDOR_METHODS['get_news'], vendor, unavailable)
    graph = _graph(tmp_path, monkeypatch, CompleteModel(structured=True))
    state, _ = graph.propagate('NVDA', TRADE_DATE)
    assert state['executive_summary']['status'] == 'completed', state['executive_summary']
    assert assess_audit(state)['score'] == (3 if outage else 5), assess_audit(state)['findings']
    output = graph.save_reports(state, 'NVDA', tmp_path / 'report')
    expected = '3/5 — Degraded' if outage else '5/5 — Strong'
    for path in (output, output.with_suffix('.html'), output.parent / 'operational_audit.md'):
        assert expected in path.read_text(), path.name
    assert output.read_text().rstrip().endswith('(./operational_audit.md)')


@pytest.mark.unit
def test_default_vendor_discovery_skips_unconfigured_provider_without_penalty(monkeypatch):
    from tradingagents.dataflows import router
    from tradingagents.dataflows.config import run_config
    from tradingagents.dataflows.errors import VendorNotConfiguredError
    from tradingagents.operational_capture import observed_node

    def unconfigured(*args, **kwargs):
        raise VendorNotConfiguredError('optional credential absent')
    monkeypatch.setitem(router.VENDOR_METHODS, 'get_stock_data',
                        {'yfinance': unconfigured, 'alpha_vantage': lambda *a, **kw: 'usable'})
    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    with run_config({'data_vendors': {'core_stock_apis': 'default'}}):
        result = observed_node(lambda s: {'answer': router.route_to_vendor('get_stock_data', 'NVDA')},
                               'Market Analyst')(state, {})
    assert {r['code'] for r in result['operational_observations'].values()} == {'completed'}


@pytest.mark.unit
def test_failed_structured_call_records_successful_fallback():
    from tradingagents.agents.structured import invoke_structured_or_freetext
    from tradingagents.operational_capture import observed_node

    class BrokenStructured:
        def invoke(self, *args):
            raise ValueError('malformed structured response')

    class Plain:
        def invoke(self, *args):
            from langchain_core.messages import AIMessage
            return AIMessage(content='complete report')

    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    def node(s):
        return {'report': invoke_structured_or_freetext(BrokenStructured(), Plain(), [], str, 'Analyst')}
    result = observed_node(node, 'Market Analyst')(state, {})
    assert 'fallback_recovered' in {r['code'] for r in result['operational_observations'].values()}


@pytest.mark.unit
def test_provider_truncation_is_observed_from_actual_model_callback():
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    from tradingagents.operational_capture import observed_node

    model = FakeMessagesListChatModel(responses=[AIMessage(content='partial', response_metadata={'finish_reason': 'length'})])
    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    result = observed_node(lambda s: {'report': model.invoke('fixture').content}, 'Market Analyst')(state, {})
    assert 'model_output_truncated' in {r['code'] for r in result['operational_observations'].values()}


@pytest.mark.unit
def test_delivered_analyst_text_marks_only_truncated_response():
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage

    from tradingagents.agents.analysts.turn import take_turn

    prompt = MagicMock()
    model = MagicMock()
    prompt.__or__.return_value = model
    model.bind_tools.return_value = model
    model.invoke.side_effect = [
        AIMessage(content='partial', response_metadata={'finish_reason': 'length'}),
        AIMessage(content='complete', response_metadata={'finish_reason': 'stop'}),
    ]
    _, first = take_turn(prompt, model, [], [])
    _, second = take_turn(prompt, model, [], [])
    assert 'truncated' in first.lower()
    assert 'truncated' not in second.lower()


@pytest.mark.unit
def test_wrap_up_and_generation_metadata_mark_delivered_report():
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage, HumanMessage

    from tradingagents.agents.analysts.turn import WRAP_UP, take_turn

    prompt = MagicMock()
    model = MagicMock()
    prompt.partial.return_value = prompt
    prompt.__or__.return_value = model
    raw = AIMessage(content='partial')
    raw.response_metadata = {'stop_reason': 'max_tokens'}
    model.invoke.return_value = raw
    _, report = take_turn(prompt, model, [], [HumanMessage(WRAP_UP)])
    assert 'truncated' in report.lower()


@pytest.mark.unit
@pytest.mark.parametrize('fallback_stop,expected', [('stop', False), ('length', True)])
def test_structured_failed_attempt_labels_only_delivered_fallback(fallback_stop, expected):
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage

    from tradingagents.agents.structured import invoke_structured_or_freetext

    structured = MagicMock()
    structured.invoke.return_value = {
        'raw': AIMessage(content='bad json', response_metadata={'finish_reason': 'length'}),
        'parsed': None, 'parsing_error': ValueError('bad json'),
    }
    plain = MagicMock()
    plain.invoke.return_value = AIMessage(content='fallback', response_metadata={'finish_reason': fallback_stop})
    report = invoke_structured_or_freetext(structured, plain, 'prompt', str, 'Trader')
    assert ('truncated' in report.lower()) is expected


@pytest.mark.unit
def test_structured_raw_finish_marks_rendered_narrative_without_changing_parsed_model():
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage

    from tradingagents.agents.structured import invoke_structured_or_freetext

    parsed = object()
    structured = MagicMock()
    structured.invoke.return_value = {
        'raw': AIMessage(content='json', response_metadata={'finish_reason': 'length'}),
        'parsed': parsed, 'parsing_error': None,
    }
    plain = MagicMock()
    report = invoke_structured_or_freetext(structured, plain, 'prompt', lambda value: 'rendered' if value is parsed else 'wrong', 'Trader')
    assert report.startswith('rendered') and 'truncated' in report.lower()
    plain.invoke.assert_not_called()


@pytest.mark.unit
def test_generation_info_finish_status_is_recognized_without_duplicate_observation():
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    from tradingagents.operational_capture import (
        _Outcomes,
        delivered_narrative,
        observed_node,
        output_was_truncated,
    )

    generation = ChatGeneration(message=AIMessage(content='partial'), generation_info={'finish_reason': 'length'})
    assert output_was_truncated(generation)
    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    def node(_state):
        _Outcomes().on_llm_end(LLMResult(generations=[[generation]]))
        return {'report': delivered_narrative(generation.message.content, generation.message)}
    result = observed_node(node, 'Market Analyst')(state, {})
    assert 'Model output truncated by provider' in result['report']
    rows = [row for row in result['operational_observations'].values() if row['code'] == 'model_output_truncated']
    assert len(rows) == 1 and rows[0].get('count', 1) == 1


@pytest.mark.unit
def test_generation_info_only_truncation_reaches_next_prompt_from_model_callback():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from tradingagents.operational_capture import delivered_narrative, observed_node

    class GenerationOnlyModel(BaseChatModel):
        @property
        def _llm_type(self):
            return 'generation-only-fixture'

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(generations=[ChatGeneration(
                message=AIMessage(content='partial research'),
                generation_info={'finish_reason': 'length'},
            )])

    model = GenerationOnlyModel()
    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    def analyst(_state):
        raw = model.invoke('research prompt')
        return {'report': delivered_narrative(raw.content, raw)}
    result = observed_node(analyst, 'Market Analyst')(state, {})
    next_prompt = f"Review the analyst report:\n{result['report']}"
    assert 'Model output truncated by provider' in next_prompt
    truncated = [row for row in result['operational_observations'].values()
                 if row['code'] == 'model_output_truncated']
    assert len(truncated) == 1 and truncated[0].get('count', 1) == 1


@pytest.mark.unit
def test_checkpoint_resume_and_second_run_keep_separate_observations(tmp_path, monkeypatch, offline):  # noqa: F811
    import json

    from tradingagents.operational_audit import assess_audit

    model = ScriptedModel(fail_at=10)
    graph = _graph(tmp_path, monkeypatch, model, checkpoint_enabled=True)
    with pytest.raises(RuntimeError, match='provider unavailable'):
        graph.propagate('NVDA', TRADE_DATE)
    checkpoint_id = graph.begin_checkpoint('NVDA', TRADE_DATE)
    saved = graph.graph.get_state({'configurable': {'thread_id': checkpoint_id}})
    original_rows = dict(saved.values.get('operational_observations') or {})
    original_run = saved.values['run_id']
    graph.end_checkpoint()
    assert original_rows
    resumed, _ = graph.propagate('NVDA', TRADE_DATE)
    assert resumed['run_id'] == original_run
    assert original_rows.items() <= resumed['operational_observations'].items()
    # The next invocation starts a new run after successful checkpoint clearing.
    another, _ = graph.propagate('NVDA', TRADE_DATE)
    assert another['run_id'] != original_run
    assert all(row['run_id'] == another['run_id'] for row in another['operational_observations'].values())
    assert assess_audit(another)['inputs']['Run identity'] == 'matched'
    log = tmp_path / 'results/NVDA/TradingAgentsStrategy_logs' / f'full_states_log_{TRADE_DATE}.json'
    assert json.loads(log.read_text())['operational_observations'] == another['operational_observations']


@pytest.mark.unit
def test_direct_price_failure_is_retained_even_when_fetch_returns_placeholder(monkeypatch):
    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.dataflows.vendors.yahoo import price_observation
    from tradingagents.operational_capture import observed_node

    def failed(*args, **kwargs):
        raise VendorUnavailableError('private transport details')
    monkeypatch.setattr(price_observation, 'yf_retry', failed)
    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    result = observed_node(lambda s: {'price': price_observation.get_price_observation('NVDA', TRADE_DATE)},
                           'Source Acquisition')(state, {})
    assert result['price']['status'] == 'unavailable'
    rows = result['operational_observations']
    assert 'vendor_unavailable' in {r['code'] for r in rows.values()}
    assert 'private transport details' not in str(rows)


@pytest.mark.unit
def test_application_visible_yahoo_retry_records_recovery():
    from yfinance.exceptions import YFRateLimitError

    from tradingagents.dataflows.vendors.yahoo.common import yf_retry
    from tradingagents.operational_capture import observed_node

    attempts = 0
    def transient():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise YFRateLimitError()
        return 'complete'
    state = {'run_id': 'run-one', 'company_of_interest': 'NVDA', 'trade_date': TRADE_DATE,
             'run_settings': {}}
    result = observed_node(lambda s: {'data': yf_retry(transient, base_delay=0)}, 'Source Acquisition')(state, {})
    assert attempts == 3
    assert 'recovered_retry' in {r['code'] for r in result['operational_observations'].values()}
