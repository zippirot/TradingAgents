"""Attempt coverage reuses run logs, without recording private provider errors."""
import json
from contextlib import nullcontext
from uuid import uuid4

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


def graph(tmp_path):
    app = object.__new__(TradingAgentsGraph)
    app.config = {'results_dir': str(tmp_path)}
    app.checkpoint_scope = lambda *args: nullcontext(None)
    return app


def events(tmp_path):
    lines = (tmp_path/'DOCN/2026-11-04/message_tool.log').read_text().splitlines()
    return [json.loads(line.split('[Evaluation Attempt] ', 1)[1]) for line in lines]


def test_failed_and_resumed_attempts_are_retained_without_extra_publications(tmp_path):
    app = graph(tmp_path)
    app._run_graph = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('SECRET provider URL'))
    with pytest.raises(RuntimeError, match='SECRET'):
        app.propagate('DOCN', '2026-11-04')
    identity = str(uuid4())
    expected = {'publication_record': {'decision_id': identity}}
    app._run_graph = lambda *a, **k: (expected, 'Hold')
    assert app.propagate('DOCN', '2026-11-04') == (expected, 'Hold')
    rows = events(tmp_path)
    assert [r['event'] for r in rows] == ['started', 'failed', 'started', 'completed']
    assert rows[0]['attempt_id'] == rows[1]['attempt_id']
    assert rows[2]['attempt_id'] == rows[3]['attempt_id'] != rows[0]['attempt_id']
    assert rows[1]['error_type'] == 'RuntimeError'
    assert rows[3]['decision_id'] == identity
    assert 'SECRET' not in str(rows)
    assert all(r['recorded_at'].endswith('+00:00') for r in rows)
    assert not (tmp_path/'publications').exists()
