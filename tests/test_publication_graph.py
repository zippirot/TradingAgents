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


def test_pending_memory_follows_latest_publication_when_first_projection_is_delayed(tmp_path):
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
    latest = max(records, key=lambda r: r['sequence'])
    entry = app.memory_log.load_entries()[0]
    assert primary['canonical_rating'] == 'Underweight'
    assert latest['eligibility']['primary'] is False
    assert entry['decision_id'] == latest['decision_id']
    assert entry['rating'] == 'Hold'
    assert len(app.memory_log.load_entries()) == 1


def test_concurrent_publication_cannot_pass_an_inflight_memory_projection(tmp_path):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event

    from tradingagents.memory.log import TradingMemoryLog

    app, _ = graph_and_state(tmp_path)
    app.memory_log = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    app._log_state = lambda *args: None
    selected, release = Event(), Event()
    original_store = app.memory_log.store_decision

    def delayed_store(**kwargs):
        if kwargs['rating'] == 'Underweight':
            selected.set()
            assert release.wait(5), 'test did not release projection'
        original_store(**kwargs)

    app.memory_log.store_decision = delayed_store
    first = {'final_rating': 'Underweight', 'final_trade_decision': 'Underweight',
             'evidence_quality': {'status': 'limited'}}
    second = {'final_rating': 'Hold', 'final_trade_decision': 'Hold',
              'evidence_quality': {'status': 'limited'}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(app.record_decision, 'DOCN', '2026-11-04', first)
        assert selected.wait(5)
        b = pool.submit(app.record_decision, 'DOCN', '2026-11-04', second)
        try:
            b.result(timeout=.2)
        except TimeoutError:
            pass
        finally:
            release.set()
        a.result(timeout=5)
        b.result(timeout=5)
    records = list_records(app.config)
    latest = max(records, key=lambda r: r['sequence'])
    entries = app.memory_log.load_entries()
    assert len(entries) == 1
    assert entries[0]['decision_id'] == latest['decision_id']
    assert entries[0]['rating'] == 'Hold'


def test_published_rerun_cannot_replace_settled_memory(tmp_path):
    from hashlib import sha256

    from tradingagents.memory.log import TradingMemoryLog
    from tradingagents.memory.publication import record_root

    app, _ = graph_and_state(tmp_path)
    app.memory_log = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    app._log_state = lambda *args: None
    first = {'final_rating': 'Underweight', 'final_trade_decision': 'Underweight',
             'evidence_quality': {'status': 'limited'}}
    second = {'final_rating': 'Hold', 'final_trade_decision': 'Hold',
              'evidence_quality': {'status': 'limited'}}
    app.record_decision('DOCN', '2026-11-04', first)
    original_id = app.memory_log.load_entries()[0]['decision_id']
    original_path = record_root(app.config) / 'records' / f'{original_id}.json'
    digest = sha256(original_path.read_bytes()).hexdigest()
    assert app.memory_log.update_with_outcome('DOCN', '2026-11-04', .01, .005, 5,
                                              'Original settled lesson')
    app.record_decision('DOCN', '2026-11-04', second)
    entries = app.memory_log.load_entries()
    assert len(list_records(app.config)) == 2 and len(entries) == 1
    assert entries[0]['decision_id'] == original_id
    assert entries[0]['reflection'] == 'Original settled lesson'
    assert not entries[0]['pending']
    assert sha256(original_path.read_bytes()).hexdigest() == digest


def test_review_summary_survives_log_and_publication_replay(tmp_path):
    """A resumed terminal checkpoint may lack presentation fields added after publication."""
    from copy import deepcopy

    from tradingagents.reporting import evidence_snapshot

    app, state = graph_and_state(tmp_path)
    app.record_decision('DOCN', '2026-11-04', state)
    original = list_records(app.config)[0]
    saved = deepcopy(state['executive_summary'])
    assert saved['status'] == 'review'
    displayed = app.save_reports(state, 'DOCN', tmp_path / 'review-export', html=False).read_text()
    opening = displayed.split('## Executive summary', 1)[1].split('## Table of contents', 1)[0]
    assert 'REVIEW' in opening
    assert 'executive_summary' not in evidence_snapshot(state)
    # Recreate a retry from a checkpoint without in-memory report enrichment.
    del state['executive_summary']
    app.record_decision('DOCN', '2026-11-04', state)
    assert state['executive_summary'] == saved
    retained = json.loads(next(tmp_path.rglob('full_states_log_*.json')).read_text())
    assert retained['executive_summary'] == saved
    assert list_records(app.config) == [original]


@pytest.mark.parametrize('timeout', [False, True])
def test_editorial_outcome_is_logged_but_never_changes_publication_or_replays(tmp_path, timeout):
    from tradingagents.memory.log import TradingMemoryLog
    from tradingagents.memory.publication import load_evidence

    app, state = graph_and_state(tmp_path)
    state.update(
        evidence_quality={'status': 'limited', 'checks': [], 'scope': 'selected fundamentals'},
        final_rating='Underweight', final_trade_decision='Rating: Underweight\nCapital spending weighs on margins.',
        market_report='Market analysts describe a weaker trend.',
        investment_plan='The research manager questions capacity costs.',
        trader_investment_plan='Sell gradually.', decision_context={}, target_validation={},
        risk_debate_state={**state['risk_debate_state'], 'neutral_history': 'Rebound risk complicates a reduction.'},
    )
    app.memory_log = TradingMemoryLog({'memory_log_path': str(tmp_path / 'memory.md')})
    calls = []

    class EditorialModel:
        def with_structured_output(self, schema, **kwargs):
            return self

        def invoke(self, prompt, **kwargs):
            # The decision and evidence must already be durable before inference.
            record = list_records(app.config)[0]
            calls.append((record, load_evidence(app.config, record)))
            if timeout:
                raise TimeoutError('sensitive provider detail')
            return {'sentences': [
                {'text': 'The market analyst reports a weaker trend.', 'sections': ['1_analysts']},
                {'text': 'The research manager questions the cost of building capacity.', 'sections': ['2_research']},
                {'text': 'The trader proposes a gradual reduction given the risk of a rebound.',
                 'sections': ['3_trading', '4_risk']},
                {'text': 'The portfolio manager weighs margin pressure against limited evidence.',
                 'sections': ['5_portfolio', '6_evidence']},
            ]}

    app.deep_thinking_llm = EditorialModel()
    app.record_decision('DOCN', '2026-11-04', state)
    pub = list_records(app.config)[0]
    assert calls == [(pub, load_evidence(app.config, pub))]
    saved = json.loads(next(tmp_path.rglob('full_states_log_*.json')).read_text())
    summary = saved['executive_summary']
    assert summary['status'] == ('unavailable' if timeout else 'completed')
    assert summary == state['executive_summary']
    assert 'executive_summary' not in load_evidence(app.config, pub)
    assert 'sensitive provider detail' not in json.dumps(summary)
    if not timeout:
        assert summary['sentences'][1] not in pub['canonical_decision']
    assert app.memory_log.load_entries()[0]['rating'] == 'Underweight'
    for current in [state, saved]:
        destination = app.save_reports(current, 'DOCN', tmp_path / 'export')
        for path in (destination, destination.with_suffix('.html')):
            text = path.read_text()
            if timeout:
                assert 'editorial generation or validation failed' in text
                assert 'lower-than-normal allocation' in text
            else:
                assert all(line in text for line in summary['sentences'])
    del state['executive_summary']
    app.record_decision('DOCN', '2026-11-04', state)
    assert state['executive_summary'] == summary
    assert calls == [(pub, load_evidence(app.config, pub))]
    assert list_records(app.config) == [pub]
