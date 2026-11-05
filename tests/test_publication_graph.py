"""Graph publication is durable before optional projections and retry-safe."""
import json

import pytest

from tradingagents.agents.evidence_validation import review_terminal_state
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.memory.publication import list_records


def graph_and_state(tmp_path):
    app = object.__new__(TradingAgentsGraph)
    app.config = {'results_dir': str(tmp_path)}
    app.run_settings = lambda: {'version': 'test'}
    state = {
        **review_terminal_state({'status': 'insufficient', 'checks': [
            {'status': 'unavailable', 'message': 'Source unavailable'},
        ]}),
        'company_of_interest': 'DOCN', 'trade_date': '2026-11-04',
        **dict.fromkeys(('market_report', 'news_report', 'sentiment_report', 'fundamentals_report'), ''),
    }
    return app, state


def test_required_projection_failure_keeps_authoritative_record_for_retry(tmp_path, monkeypatch):
    app, state = graph_and_state(tmp_path)
    real_log = app._log_state
    monkeypatch.setattr(app, '_log_state', lambda *a: (_ for _ in ()).throw(OSError('disk interrupted')))
    with pytest.raises(OSError, match='disk interrupted'):
        app.record_decision('DOCN', '2026-11-04', state)
    records = list_records(app.config)
    assert len(records) == 1
    first = records[0]
    assert first['canonical_rating'] == 'REVIEW'
    assert first['versions']['code']
    monkeypatch.setattr(app, '_log_state', real_log)
    app.record_decision('DOCN', '2026-11-04', state)
    assert list_records(app.config) == [first]
    saved = json.loads((tmp_path / 'DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-04.json').read_text())
    assert saved['run_id'] == first['run_id']
    assert saved['publication_record']['decision_id'] == first['decision_id']
    assert saved['publication_record']['published_at'] == first['published_at']


def test_report_export_preserves_publication_identity(tmp_path):
    app, state = graph_and_state(tmp_path)
    app.record_decision('DOCN', '2026-11-04', state)
    original = list_records(app.config)[0]
    for name in ('first-export', 'second-export'):
        destination = app.save_reports(state, 'DOCN', tmp_path / name, html=True)
        text = destination.read_text()
        assert f"First published: {original['published_at']}" in text
        assert original['decision_id'] in text
        assert 'Export generated:' in text
        assert 'Recommendation outcome horizons' in text
        assert '5 sessions | ineligible' in text
        html = destination.with_suffix('.html').read_text()
        assert original['decision_id'] in html
    assert list_records(app.config) == [original]


def test_memory_keeps_exact_publication_link_after_outcome(tmp_path):
    from uuid import uuid4

    from tradingagents.memory.log import TradingMemoryLog
    memory = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    identity = str(uuid4())
    memory.store_decision('DOCN', '2026-10-19', 'Rating: Underweight', decision_id=identity)
    assert memory.load_entries()[0]['decision_id'] == identity
    memory.update_with_outcome('DOCN', '2026-10-19', .01, .005, 5, 'Five-day lesson',
                               resolution_date='2026-10-27')
    assert memory.load_entries()[0]['decision_id'] == identity


def test_later_revision_cannot_win_memory_while_primary_projection_is_delayed(tmp_path):
    from tradingagents.memory.log import TradingMemoryLog
    app, _ = graph_and_state(tmp_path)
    app.memory_log = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    first = {'final_rating': 'Underweight', 'final_trade_decision': 'Underweight',
             'evidence_quality': {'status': 'limited'}}
    second = {'final_rating': 'Hold', 'final_trade_decision': 'Hold',
              'evidence_quality': {'status': 'limited'}}
    called = False
    def delayed(date, state):
        nonlocal called
        if not called:
            called = True
            app.record_decision('DOCN', '2026-11-04', second)
    app._log_state = delayed
    app.record_decision('DOCN', '2026-11-04', first)
    records = list_records(app.config)
    primary = next(r for r in records if r['eligibility']['primary'])
    entry = app.memory_log.load_entries()[0]
    assert entry['decision_id'] == primary['decision_id']
    assert entry['rating'] == 'Underweight'
