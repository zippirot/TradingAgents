"""The graph's operator note reflects a real, disposable settlement pass."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from tests.test_settlement_pass import provider, record, series
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.memory import publication, publication_outcomes as outcomes
from tradingagents.memory.log import TradingMemoryLog


class NoReflection:
    def reflect_on_final_decision(self, **kwargs):
        pytest.fail('publication-only settlement must not call a model')


def _graph(tmp_path):
    config = {'results_dir': str(tmp_path),
              'memory_log_path': str(tmp_path / 'empty-memory.md'),
              'benchmark_ticker': 'SPY'}
    graph = object.__new__(TradingAgentsGraph)
    graph.config = config
    graph.memory_log = TradingMemoryLog(config)
    graph.reflector = NoReflection()
    return graph


def _clock(monkeypatch, moment):
    monkeypatch.setattr(outcomes, '_now', lambda: moment)
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: moment.date().isoformat())


def _memory_step(graph, moment):
    state = {
        'company_of_interest': 'DOCN',
        'trade_date': moment.date().isoformat(),
        'analysis_clock': {'cutoff_utc': moment.replace(hour=23).isoformat(),
                           'analysis_timezone': 'UTC'},
    }
    result = graph._memory_step(state)
    assert {'past_context', 'memory_note', 'outcome_summary', 'prior_thesis',
            'thesis_context', 'analysis_clock'} <= result.keys()
    assert result['analysis_clock'] == state['analysis_clock']
    assert graph.memory_log.load_entries() == []
    return result


def test_memory_note_reports_resolved_endpoints_without_failure(tmp_path, monkeypatch):
    graph = _graph(tmp_path)
    row = record(graph.config, monkeypatch)
    moment = datetime(2026, 11, 7, 22, tzinfo=UTC)
    _clock(monkeypatch, moment)
    dates = pd.bdate_range('2025-12-29', '2026-11-06')
    calls = provider(monkeypatch, {'DOCN': series(dates), 'SPY': series(dates, 400)})

    result = _memory_step(graph, moment)

    assert outcomes.load_outcomes(graph.config, row)['endpoints']['5_sessions']['status'] == 'resolved'
    assert len(calls) == 2
    assert 'could not be settled' not in result['memory_note'].lower()
    assert 'resolved' in result['outcome_summary']


def test_memory_note_distinguishes_immature_from_retryable(tmp_path, monkeypatch):
    graph = _graph(tmp_path)
    row = record(graph.config, monkeypatch)
    moment = datetime(2026, 1, 7, 22, tzinfo=UTC)
    _clock(monkeypatch, moment)
    provider(monkeypatch, {'DOCN': series(['2026-01-06']),
                           'SPY': series(['2026-01-06'], 400)})

    result = _memory_step(graph, moment)

    assert outcomes.load_outcomes(graph.config, row)['endpoints']['5_sessions']['status'] == 'pending'
    assert 'await maturity' in result['memory_note'].lower()
    assert 'could not be settled' not in result['memory_note'].lower()


def test_memory_note_calls_provider_outage_retryable(tmp_path, monkeypatch):
    graph = _graph(tmp_path)
    record(graph.config, monkeypatch)
    moment = datetime(2026, 11, 7, 22, tzinfo=UTC)
    _clock(monkeypatch, moment)
    provider(monkeypatch, {'DOCN': TimeoutError('provider down'),
                           'SPY': series(pd.bdate_range('2025-12-29', '2026-11-06'), 400)})

    result = _memory_step(graph, moment)

    assert 'could not be settled this run' in result['memory_note'].lower()
    assert 'await maturity' not in result['memory_note'].lower()
    assert 'provider down' not in result['memory_note'].lower()


def test_memory_note_calls_verified_zero_coverage_terminal(tmp_path, monkeypatch):
    graph = _graph(tmp_path)
    row = record(graph.config, monkeypatch)
    empty = series([])
    empty.attrs['settlement_verified_empty'] = True
    provider(monkeypatch, {'DOCN': empty,
                           'SPY': series(pd.bdate_range('2026-01-01', '2026-03-01'), 400)})
    for day in (datetime(2026, 1, 15, 22, tzinfo=UTC),
                datetime(2026, 1, 29, 22, tzinfo=UTC)):
        _clock(monkeypatch, day)
        graph.settle_all_pending()
    moment = datetime(2026, 2, 12, 22, tzinfo=UTC)
    _clock(monkeypatch, moment)

    result = _memory_step(graph, moment)

    endpoint = outcomes.load_outcomes(graph.config, row)['endpoints']['5_sessions']
    assert endpoint['status'] == 'unresolvable'
    assert len(endpoint['zero_checks']) == 3
    assert 'unresolvable' in result['memory_note'].lower()
    assert 'No eligible instrument sessions' in result['outcome_summary']


def test_memory_note_reports_skipped_corrupt_publication(tmp_path, monkeypatch):
    graph = _graph(tmp_path)
    valid = record(graph.config, monkeypatch)
    broken = record(graph.config, monkeypatch, ticker='OTHER')
    path = publication.record_root(graph.config) / 'records' / f"{broken['decision_id']}.json"
    path.write_text('{"incomplete": ', encoding='utf-8')
    moment = datetime(2026, 11, 7, 22, tzinfo=UTC)
    _clock(monkeypatch, moment)
    dates = pd.bdate_range('2025-12-29', '2026-11-06')
    provider(monkeypatch, {'DOCN': series(dates), 'SPY': series(dates, 400)})

    result = _memory_step(graph, moment)

    assert outcomes.load_outcomes(graph.config, valid)['endpoints']['5_sessions']['status'] == 'resolved'
    assert path.read_text(encoding='utf-8') == '{"incomplete": '
    assert '1' in result['memory_note'] and 'unreadable publication' in result['memory_note'].lower()
    assert 'Integrity omissions: 1' in result['outcome_summary']
