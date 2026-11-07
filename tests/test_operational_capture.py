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
    assert {'Source Acquisition', 'Market Analyst', 'Evidence Check', 'Portfolio Manager', 'Run Metrics'} <= stages
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
    graph = _graph(tmp_path, monkeypatch, ScriptedModel())
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
