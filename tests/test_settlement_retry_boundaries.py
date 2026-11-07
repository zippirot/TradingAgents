"""Adversarial offline proof for publication settlement retry boundaries."""

import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pandas as pd
import pytest

from tradingagents.memory import publication, publication_outcomes as outcomes, settlement


def _record(config, monkeypatch, *, ticker='DOCN', mode='historical'):
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 1, 6, 22, tzinfo=UTC))
    state = {'run_id': str(uuid4()), 'final_rating': 'Hold', 'final_trade_decision': 'Hold',
             'evaluation_mode': mode, 'evidence_quality': {'status': 'limited'}}
    return publication.publish(config, state, ticker, '2026-01-05')


def _series(dates, *, zone='America/New_York', base=100):
    return pd.Series([float(base + i) for i in range(len(dates))],
                     index=pd.DatetimeIndex(dates, tz=zone))


def _feed(monkeypatch, values):
    calls = []

    def fetch(symbol, start, end):
        calls.append(symbol)
        value = values[symbol]
        if isinstance(value, Exception):
            raise value
        dates = value.index.tz_localize(None) if value.index.tz is not None else value.index
        result = value[(dates >= start) & (dates < end)].copy()
        result.attrs.update(value.attrs)
        result.attrs.update(settlement_request_start=start, settlement_request_end=end)
        return result

    monkeypatch.setattr(settlement, 'get_settlement_closes', fetch)
    monkeypatch.setattr(settlement, 'get_closes', fetch)
    return calls


def _clock(monkeypatch, stamp=datetime(2026, 2, 2, 22, tzinfo=UTC)):
    current = [stamp]
    monkeypatch.setattr(outcomes, '_now', lambda: current[0])
    monkeypatch.setattr(outcomes, 'get_current_date', lambda: current[0].date().isoformat())
    return current


def _checks(config, row, name='5_sessions'):
    return outcomes.load_outcomes(config, row)['endpoints'][name].get('zero_checks', [])


def _verified_empty(zone='America/New_York'):
    empty = _series([], zone=zone)
    empty.attrs['settlement_verified_empty'] = True
    return empty


def _mature_benchmark():
    return _series(pd.bdate_range('2026-01-01', '2026-11-06'), base=400)


@pytest.mark.unit
def test_unknown_empty_and_instrument_outage_never_start_zero_streak(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    clock = _clock(monkeypatch)
    values = {'DOCN': _series([]), 'SPY': _mature_benchmark()}
    _feed(monkeypatch, values)
    for instrument in (_series([]), RuntimeError('provider secret'), _series(['2026-01-06'], base=0)):
        values['DOCN'] = instrument
        result = outcomes.settle_publications(cfg, pass_id=str(uuid4()))
        assert not _checks(cfg, row)
        assert result['failed'] and not result['terminal']
        clock[0] += timedelta(days=14)


@pytest.mark.unit
def test_benchmark_outage_does_not_count_zero_or_block_another_benchmark(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    first = _record(cfg, monkeypatch)
    cfg['benchmark_ticker'] = 'QQQ'
    second = _record(cfg, monkeypatch, ticker='NVDA')
    cfg.pop('benchmark_ticker')
    clock = _clock(monkeypatch)
    values = {'DOCN': _verified_empty(), 'NVDA': _series(pd.bdate_range('2026-01-06', '2026-02-02')),
              'SPY': RuntimeError('benchmark secret'), 'QQQ': _mature_benchmark()}
    assert first['benchmark'] == 'SPY' and second['benchmark'] == 'QQQ'
    _feed(monkeypatch, values)
    result = outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert not _checks(cfg, first)
    assert result['failed']
    assert (second['decision_id'], '5_sessions') in result['settled']
    clock[0] += timedelta(days=14)
    values['SPY'] = _mature_benchmark()
    outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert len(_checks(cfg, first)) == 1
    clock[0] += timedelta(days=14)
    values['SPY'] = RuntimeError('benchmark still unavailable')
    outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert len(_checks(cfg, first)) == 1


@pytest.mark.unit
def test_duplicate_pass_and_positive_price_clear_durable_streak(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    clock = _clock(monkeypatch)
    values = {'DOCN': _verified_empty(), 'SPY': _mature_benchmark()}
    _feed(monkeypatch, values)
    same = str(uuid4())
    outcomes.settle_publications(cfg, pass_id=same)
    assert len(_checks(cfg, row)) == 1
    clock[0] += timedelta(days=14)
    outcomes.settle_publications(cfg, pass_id=same)
    assert len(_checks(cfg, row)) == 1
    values['DOCN'] = _series(['2026-01-06'])
    values['SPY'] = RuntimeError('benchmark unavailable')
    result = outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert result['failed']
    assert _checks(cfg, row) == []
    values['SPY'] = _mature_benchmark()
    values['DOCN'] = _verified_empty()
    outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert len(_checks(cfg, row)) == 1


@pytest.mark.unit
def test_mature_instrument_rows_clear_zero_streak_even_when_benchmark_fails(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    clock = _clock(monkeypatch)
    values = {'DOCN': _verified_empty(), 'SPY': _mature_benchmark()}
    _feed(monkeypatch, values)
    outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert len(_checks(cfg, row)) == 1
    clock[0] += timedelta(days=14)
    values['DOCN'] = _series(pd.bdate_range('2026-01-06', periods=8))
    values['SPY'] = RuntimeError('benchmark unavailable')
    result = outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert result['failed'] and not result['terminal']
    assert _checks(cfg, row) == []


@pytest.mark.unit
def test_concurrent_distinct_passes_on_one_day_count_at_most_once(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    _clock(monkeypatch)
    _feed(monkeypatch, {'DOCN': _verified_empty(), 'SPY': _mature_benchmark()})
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: outcomes.settle_publications(cfg, pass_id=str(uuid4())), range(3)))
    assert all(not result['terminal'] for result in results)
    checks = _checks(cfg, row)
    assert len(checks) == 1
    assert len({check['pass_id'] for check in checks}) == 1


@pytest.mark.unit
def test_prospective_empty_without_instrument_timezone_cannot_count(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch, mode='prospective')
    _clock(monkeypatch)
    _feed(monkeypatch, {'DOCN': _verified_empty(zone=None), 'SPY': _mature_benchmark()})
    result = outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert not _checks(cfg, row)
    assert result['failed'] and not result['terminal']


@pytest.mark.unit
def test_terminal_is_not_fetched_and_reopen_preserves_prior_visibility(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    clock = _clock(monkeypatch, datetime(2026, 11, 7, 22, tzinfo=UTC))
    values = {'DOCN': _verified_empty(), 'SPY': _mature_benchmark()}
    calls = _feed(monkeypatch, values)
    for _ in range(3):
        outcomes.settle_publications(cfg, pass_id=str(uuid4()))
        clock[0] += timedelta(days=14)
    terminal_time = clock[0] - timedelta(days=14)
    saved = outcomes.load_outcomes(cfg, row)
    assert saved['endpoints']['5_sessions']['status'] == 'unresolvable'
    terminal = copy.deepcopy(saved['endpoints']['5_sessions']['terminal'])
    calls.clear()
    outcomes.settle_publications(cfg, pass_id=str(uuid4()))
    assert calls == []  # all endpoints terminal after the same three checks
    reopened = outcomes.reopen_endpoint(cfg, row['decision_id'], '5_sessions')
    assert reopened['endpoints']['5_sessions']['status'] == 'pending'
    assert reopened['endpoints']['5_sessions']['zero_checks'] == []
    assert reopened['endpoints']['5_sessions']['terminal_history'][0]['reason'] == terminal['reason']
    assert all(reopened['endpoints'][n] == saved['endpoints'][n] for n in saved['endpoints'] if n != '5_sessions')
    assert 'unresolvable' in outcomes.render_outcome_summary(cfg, as_of=terminal_time.isoformat())
    values['DOCN'] = _series(pd.bdate_range('2026-01-06', '2026-11-06'))
    assert (row['decision_id'], '5_sessions') in outcomes.settle_publications(cfg)['settled']


@pytest.mark.unit
def test_tampered_terminal_protocol_rejected_on_read_and_write(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    clock = _clock(monkeypatch)
    _feed(monkeypatch, {'DOCN': _verified_empty(), 'SPY': _mature_benchmark()})
    for _ in range(3):
        outcomes.settle_publications(cfg, pass_id=str(uuid4()))
        clock[0] += timedelta(days=14)
    original = outcomes.load_outcomes(cfg, row)
    path = publication.record_root(cfg) / 'outcomes' / f"{row['decision_id']}.json"
    cases = [
        {'status': 'unresolvable', 'terminal': {'kind': 'zero_coverage', 'reason': 'invented',
                                               'known_at': clock[0].isoformat()}},
        {'status': 'unresolvable', 'terminal': {'kind': 'zero_coverage',
                                               'reason': outcomes.ZERO_REASON,
                                               'known_at': '2026-03-01T00:00:00'}},
        {'status': 'unresolvable', 'terminal': {'kind': 'zero_coverage',
                                               'reason': outcomes.ZERO_REASON,
                                               'known_at': '2026-01-01T00:00:00+00:00'}},
        {'status': 'pending', 'terminal': original['endpoints']['5_sessions']['terminal']},
    ]
    for edits in cases:
        bad = copy.deepcopy(original)
        bad['endpoints']['5_sessions'].update(edits)
        with pytest.raises(ValueError):
            outcomes._write(path, bad)
        payload = {k: v for k, v in bad.items() if k != 'outcomes_sha256'}
        checksum = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        path.write_text(json.dumps({**payload, 'outcomes_sha256': checksum}), encoding='utf-8')
        with pytest.raises(ValueError):
            outcomes.load_outcomes(cfg, row)
        outcomes._write(path, original)

    reopened = outcomes.reopen_endpoint(cfg, row['decision_id'], '5_sessions')
    bad = copy.deepcopy(reopened)
    bad['endpoints']['5_sessions']['terminal_history'][0]['known_at'] = '2026-01-01T00:00:00+00:00'
    with pytest.raises(ValueError):
        outcomes._write(path, bad)
    payload = {k: v for k, v in bad.items() if k != 'outcomes_sha256'}
    checksum = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    path.write_text(json.dumps({**payload, 'outcomes_sha256': checksum}), encoding='utf-8')
    with pytest.raises(ValueError):
        outcomes.load_outcomes(cfg, row)


@pytest.mark.parametrize('edit', ['pending_with_three_checks', 'terminal_with_priced_outcome'])
def test_terminal_combinations_rejected_before_persisting(tmp_path, monkeypatch, edit):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    clock = _clock(monkeypatch)
    _feed(monkeypatch, {'DOCN': _verified_empty(), 'SPY': _mature_benchmark()})
    for _ in range(3):
        outcomes.settle_publications(cfg)
        clock[0] += timedelta(days=14)
    companion = outcomes.load_outcomes(cfg, row)
    endpoint = companion['endpoints']['5_sessions']
    if edit == 'pending_with_three_checks':
        endpoint['status'] = 'pending'
        endpoint.pop('terminal')
    else:
        endpoint['outcome'] = {'raw_return': 1.0}
    path = publication.record_root(cfg) / 'outcomes' / f"{row['decision_id']}.json"
    with pytest.raises(ValueError):
        outcomes._write(path, companion)
    payload = {key: value for key, value in companion.items() if key != 'outcomes_sha256'}
    checksum = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    path.write_text(json.dumps({**payload, 'outcomes_sha256': checksum}))
    with pytest.raises(ValueError):
        outcomes.load_outcomes(cfg, row)


def test_documented_module_maintenance_reopens_only_selected_endpoint(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    from pathlib import Path

    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    clock = _clock(monkeypatch)
    _feed(monkeypatch, {'DOCN': _verified_empty(), 'SPY': _mature_benchmark()})
    for _ in range(3):
        outcomes.settle_publications(cfg)
        clock[0] += timedelta(days=14)
    before = outcomes.load_outcomes(cfg, row)
    record_path = publication.record_root(cfg) / 'records' / f"{row['decision_id']}.json"
    immutable = record_path.read_bytes()
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([
        sys.executable, '-m', 'tradingagents.memory.publication_outcomes', 'reopen',
        '--results-dir', str(tmp_path), '--decision-id', row['decision_id'],
        '--endpoint', '5_sessions'], cwd=root, capture_output=True, text=True, check=True,
        env={**os.environ, 'PYTHONPATH': str(root), 'TRADINGAGENTS_NO_UPDATE_CHECK': '1'})
    response = json.loads(completed.stdout)
    assert response['status'] == 'pending' and response['endpoint'] == '5_sessions'
    after = outcomes.load_outcomes(cfg, row)
    assert after['endpoints']['5_sessions']['zero_checks'] == []
    assert all(after['endpoints'][name] == before['endpoints'][name]
               for name in before['endpoints'] if name != '5_sessions')
    assert record_path.read_bytes() == immutable


def test_resolved_outcome_cannot_retain_active_zero_checks(tmp_path, monkeypatch):
    cfg = {'results_dir': str(tmp_path)}
    row = _record(cfg, monkeypatch)
    clock = _clock(monkeypatch)
    values = {'DOCN': _verified_empty(), 'SPY': _mature_benchmark()}
    _feed(monkeypatch, values)
    outcomes.settle_publications(cfg)
    stale = copy.deepcopy(_checks(cfg, row))
    clock[0] += timedelta(days=14)
    values['DOCN'] = _series(pd.bdate_range('2026-01-06', '2026-11-06'))
    outcomes.settle_publications(cfg)
    companion = outcomes.load_outcomes(cfg, row)
    endpoint = companion['endpoints']['5_sessions']
    assert endpoint['status'] == 'resolved' and endpoint['zero_checks'] == []
    endpoint['zero_checks'] = stale
    path = publication.record_root(cfg) / 'outcomes' / f"{row['decision_id']}.json"
    with pytest.raises(ValueError):
        outcomes._write(path, companion)
    payload = {k: v for k, v in companion.items() if k != 'outcomes_sha256'}
    checksum = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    path.write_text(json.dumps({**payload, 'outcomes_sha256': checksum}))
    with pytest.raises(ValueError):
        outcomes.load_outcomes(cfg, row)
