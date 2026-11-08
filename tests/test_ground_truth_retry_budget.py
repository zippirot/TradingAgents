"""Audit HTTP attempts must stay within the shared logical request allowance."""
import json
import socket
from uuid import uuid4

import httpx
import pytest
from langchain_core.callbacks import BaseCallbackHandler

from tests.test_publication_graph import graph_and_state
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph as graph
from tradingagents.llm_clients.factory import create_tier_client


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-test-key')
    monkeypatch.setenv('LANGSMITH_TRACING', 'false')
    monkeypatch.setenv('LANGCHAIN_TRACING_V2', 'false')
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: (_ for _ in ()).throw(AssertionError('Network forbidden')))


def clients_from_constructor(tmp_path, monkeypatch, failure):
    attempts = {'deep': 0, 'quick': 0, 'audit': 0}
    clients, calls = [], []
    callback = BaseCallbackHandler()

    def factory(config, tier, **extra):
        label = 'audit' if config.get('llm_max_retries') == 0 else tier
        def handle(request):
            attempts[label] += 1
            if attempts[label] == 1:
                if failure == 'timeout':
                    raise httpx.ReadTimeout('synthetic timeout', request=request)
                return httpx.Response(429, headers={'retry-after-ms': '1'}, json={'error': {'message': 'synthetic limit', 'type': 'rate_limit_error'}}, request=request)
            return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1, 'model': 'gpt-4o', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps({'claims': [], 'no_material_claims': True})}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8}}, request=request)
        transport = httpx.Client(transport=httpx.MockTransport(handle))
        clients.append(transport)
        calls.append((dict(config), tier, extra))
        return create_tier_client(config, tier, http_client=transport, **extra)

    class StopAfterClients(Exception):
        pass
    monkeypatch.setattr(graph, 'create_tier_client', factory)
    monkeypatch.setattr(graph, 'TradingMemoryLog', lambda *a: (_ for _ in ()).throw(StopAfterClients()))
    config = {**DEFAULT_CONFIG, 'llm_provider': 'openai', 'deep_think_provider': 'openai', 'quick_think_provider': 'openai', 'deep_think_llm': 'gpt-4o', 'quick_think_llm': 'gpt-4o', 'llm_max_retries': None, 'backend_url': 'https://fixture.invalid/v1', 'results_dir': str(tmp_path / 'constructor'), 'data_cache_dir': str(tmp_path / 'cache')}
    built = object.__new__(graph.TradingAgentsGraph)
    with pytest.raises(StopAfterClients):
        built.__init__(config=config, callbacks=[callback])
    assert built.deep_thinking_llm is not built.audit_llm
    assert built.deep_thinking_llm.root_client.max_retries == 2
    assert built.audit_llm.root_client.max_retries == 0
    assert {k: v for k, v in calls[0][0].items() if k != 'llm_max_retries'} == {k: v for k, v in calls[2][0].items() if k != 'llm_max_retries'}
    assert calls[0][1:] == calls[2][1:] == ('deep', {'callbacks': [callback]})
    return built, attempts, clients


@pytest.mark.parametrize('failure', ['429', 'timeout'])
def test_actual_graph_audit_http_attempts_respect_aggregate_one_request(tmp_path, monkeypatch, failure):
    built, attempts, transports = clients_from_constructor(tmp_path, monkeypatch, failure)
    app, state = graph_and_state(tmp_path / 'publication')
    app.deep_thinking_llm, app.audit_llm = built.deep_thinking_llm, built.audit_llm
    app.config.update(ground_truth_audit=True, ground_truth_max_requests=1)
    state['run_id'] = str(uuid4())
    monkeypatch.setattr(graph, 'generate_summary', lambda *a: {'status': 'unavailable'})
    try:
        app.record_decision('DOCN', state['trade_date'], state)
        assert attempts == {'deep': 0, 'quick': 0, 'audit': 1}
        assert state['ground_truth_execution']['requests'] == 1
        assert state['ground_truth_execution']['budget_tokens'] > 8
    finally:
        for transport in transports:
            transport.close()


@pytest.mark.parametrize('enabled', [None, False])
def test_no_audit_keeps_both_distinct_clients_offline(tmp_path, monkeypatch, enabled):
    built, attempts, transports = clients_from_constructor(tmp_path, monkeypatch, '429')
    app, state = graph_and_state(tmp_path / 'publication')
    app.deep_thinking_llm, app.audit_llm = built.deep_thinking_llm, built.audit_llm
    if enabled is not None:
        app.config['ground_truth_audit'] = enabled
    monkeypatch.setattr(graph, 'generate_summary', lambda *a: {'status': 'unavailable'})
    try:
        app.record_decision('DOCN', state['trade_date'], state)
        assert attempts == {'deep': 0, 'quick': 0, 'audit': 0}
        assert 'ground_truth_execution' not in state
    finally:
        for transport in transports:
            transport.close()


def test_pm_fallback_uses_retry_zero_and_remaining_shared_budget(tmp_path, monkeypatch):
    from tests.test_ground_truth_recovery_acceptance import application
    app, state, events = application(tmp_path / 'publication', monkeypatch)
    built, attempts, transports = clients_from_constructor(tmp_path, monkeypatch, '429')
    app.deep_thinking_llm, app.audit_llm = built.deep_thinking_llm, built.audit_llm
    app.config['ground_truth_max_requests'] = 2
    fallback = []
    def pm_factory(model):
        def pm(candidate):
            try:
                model.invoke('first structured PM attempt')
            except Exception:
                fallback.append(True)
                model.invoke('PM fallback')
            return {'final_rating': 'Hold', 'final_trade_decision': 'Rating: Hold'}
        return pm
    monkeypatch.setattr('tradingagents.agents.managers.portfolio_manager.create_portfolio_manager', pm_factory)
    try:
        app.record_decision('DOCN', state['trade_date'], state)
        assert attempts == {'deep': 0, 'quick': 0, 'audit': 1}
        assert fallback == [True]
        assert state['ground_truth_execution']['requests'] == 2
        assert state['ground_truth_reassessment']['status'] == 'unavailable'
        assert state['ground_truth_reassessment']['original_rating'] == state['final_rating'] == 'Hold'
    finally:
        for transport in transports:
            transport.close()


def test_both_audit_phases_use_constructor_audit_client_summary_keeps_deep(tmp_path, monkeypatch):
    from tradingagents import ground_truth_flow
    built, attempts, transports = clients_from_constructor(tmp_path, monkeypatch, '429')
    app, state = graph_and_state(tmp_path / 'publication')
    app.deep_thinking_llm, app.audit_llm = built.deep_thinking_llm, built.audit_llm
    app.config['ground_truth_audit'] = True
    phases, summaries = [], []
    def audit(candidate, model, config):
        phases.append((bool(candidate.get('publication_record')), model))
        return {'status': 'completed', 'claims': []}
    def summary(context, model):
        summaries.append(model)
        return {'status': 'unavailable'}
    monkeypatch.setattr(ground_truth_flow, '_audit_pass', audit)
    monkeypatch.setattr(graph, 'generate_summary', summary)
    try:
        app.record_decision('DOCN', state['trade_date'], state)
        assert phases == [(False, built.audit_llm), (True, built.audit_llm)]
        assert summaries == [built.deep_thinking_llm]
        assert attempts == {'deep': 0, 'quick': 0, 'audit': 0}
    finally:
        for transport in transports:
            transport.close()
