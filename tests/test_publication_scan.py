"""Tolerant publication listings never weaken canonical publication identity."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tradingagents.memory import publication


def _state():
    return {
        'run_id': str(uuid4()),
        'final_rating': 'Underweight',
        'final_trade_decision': 'Rating: Underweight. Reduce exposure.',
        'evidence_quality': {'status': 'limited'},
    }


def test_tolerant_scan_is_local_and_publication_history_remains_strict(tmp_path, monkeypatch):
    config = {'results_dir': str(tmp_path), 'benchmark_ticker': 'SPY'}
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 11, 4, 22, tzinfo=UTC))
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    state = _state()
    primary = publication.publish(config, state, 'DOCN', '2026-11-04')
    state['run_id'] = str(uuid4())
    unaffected = publication.publish(config, state, 'OTHER', '2026-11-04')
    path = publication.record_root(config) / 'records' / f"{primary['decision_id']}.json"
    original = path.read_bytes()
    path.write_text('{"unknown": ', encoding='utf-8')

    scan = publication.scan_records(config)
    assert scan['records'] == [unaffected]
    assert scan['skipped'] == [{'path': path.name, 'reason': 'JSONDecodeError'}]
    assert publication.scan_records(config, ticker='OTHER') == scan
    with pytest.raises(json.JSONDecodeError):
        publication.load_record(config, primary['decision_id'])
    with pytest.raises(json.JSONDecodeError):
        publication.list_records(config, ticker='OTHER')

    state['run_id'] = str(uuid4())
    with pytest.raises(json.JSONDecodeError):
        publication.publish(config, state, 'DOCN', '2026-11-04')
    assert not (path.parent / f"{state['run_id']}.json").exists()

    path.write_bytes(original)
    revision = publication.publish(config, state, 'DOCN', '2026-11-04')
    records = publication.list_records(config)
    assert [record['sequence'] for record in records] == [1, 2, 3]
    assert sum(record['eligibility']['primary'] for record in records if record['ticker'] == 'DOCN') == 1
    assert revision['previous_decision_id'] == primary['decision_id']
    assert publication.scan_records(config) == {'records': records, 'skipped': []}


def test_scan_reports_checksum_failure_and_does_not_cache_it(tmp_path, monkeypatch):
    config = {'results_dir': str(tmp_path), 'benchmark_ticker': 'SPY'}
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 11, 4, 22, tzinfo=UTC))
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    state = _state()
    record = publication.publish(config, state, 'DOCN', '2026-11-04')
    path = publication.record_root(config) / 'records' / f"{record['decision_id']}.json"
    original = path.read_bytes()
    damaged = json.loads(original)
    damaged['canonical_rating'] = 'Buy'
    path.write_text(json.dumps(damaged), encoding='utf-8')
    assert publication.scan_records(config)['skipped'] == [{'path': path.name, 'reason': 'ValueError'}]
    path.write_bytes(original)
    assert publication.scan_records(config) == {'records': [record], 'skipped': []}


@pytest.mark.parametrize('damage', [
    lambda record: record.pop('sequence'),
    lambda record: record.update(sequence='first'),
    lambda record: record.pop('ticker'),
    lambda record: record.update(eligibility={}),
    lambda record: record.update(endpoints={}),
    lambda record: record['endpoints']['5_sessions'].pop('benchmark'),
])
def test_scan_omits_hash_valid_unusable_record_per_file(tmp_path, monkeypatch, damage):
    config = {'results_dir': str(tmp_path), 'benchmark_ticker': 'SPY'}
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 11, 4, 22, tzinfo=UTC))
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    valid = publication.publish(config, _state(), 'OTHER', '2026-11-04')
    stray = {**valid, 'decision_id': str(uuid4())}
    stray['endpoints'] = {name: dict(endpoint) for name, endpoint in valid['endpoints'].items()}
    stray['eligibility'] = dict(valid['eligibility'])
    damage(stray)
    stray['record_sha256'] = publication._digest({key: value for key, value in stray.items()
                                                  if key != 'record_sha256'})
    path = publication.record_root(config) / 'records' / f"{stray['decision_id']}.json"
    path.write_text(json.dumps(stray), encoding='utf-8')

    scan = publication.scan_records(config, ticker='OTHER')
    assert scan['records'] == [valid]
    assert scan['skipped'] == [{'path': path.name, 'reason': 'ValueError'}]


def test_scan_includes_old_publication_without_new_endpoint_policy_fields(tmp_path, monkeypatch):
    config = {'results_dir': str(tmp_path), 'benchmark_ticker': 'SPY'}
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 11, 4, 22, tzinfo=UTC))
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    record = publication.publish(config, _state(), 'DOCN', '2026-11-04')
    old = dict(record)
    old.pop('evaluation_protocol')
    old['endpoints'] = {
        name: {key: value for key, value in endpoint.items()
               if key in {'holding_days', 'status', 'benchmark', 'entry_policy'}}
        for name, endpoint in old['endpoints'].items() if name.endswith('_sessions')
    }
    old['record_sha256'] = publication._digest({key: value for key, value in old.items()
                                                if key != 'record_sha256'})
    path = publication.record_root(config) / 'records' / f"{record['decision_id']}.json"
    path.write_text(json.dumps(old), encoding='utf-8')

    assert publication.scan_records(config) == {'records': [old], 'skipped': []}
