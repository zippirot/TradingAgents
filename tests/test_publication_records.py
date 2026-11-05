"""Immutable publication identity and recovery using actual local files."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tradingagents.memory import publication


@pytest.fixture
def config(tmp_path):
    return {'results_dir': str(tmp_path), 'api_key': 'PRIVATE', 'benchmark_ticker': 'SPY'}


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 11, 4, 22, tzinfo=UTC))
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
    return {
        'run_id': str(uuid4()), 'final_rating': 'Underweight',
        'final_trade_decision': 'Rating: Underweight\nAccepted evidence supports reduced exposure.',
        'evidence_quality': {'status': 'limited'},
        'financial_evidence': {'schema_version': 1, 'sources': [{'source_id': 'SEC', 'content_hash': 'a' * 64}]},
        'run_settings': {'version': '1.0', 'deep_think_llm': 'test/model', 'api_key': 'PRIVATE'},
        'publication_versions': {'code': 'abc123', 'prompt': 'signature1', 'schema': 1},
        'unvalidated_outputs': {'portfolio': 'PRIVATE'},
        'portfolio_context': 'PRIVATE',
    }


def test_repeat_publish_and_reload_keep_identity_time_and_source_snapshot(config, state, monkeypatch):
    record = publication.publish(config, state, 'DOCN', '2026-11-04')
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 11, 5, tzinfo=UTC))
    assert publication.publish(config, copy.deepcopy(state), 'DOCN', '2026-11-04') == record
    assert publication.load_record(config, record['decision_id']) == record
    assert record['published_at'] == '2026-11-04T22:00:00+00:00'
    assert record['eligibility']['prospective'] is True
    assert record['eligibility']['primary'] is True
    assert record['endpoints']['5_sessions']['status'] == 'pending'
    assert record['endpoints']['63_sessions']['benchmark'] == 'SPY'
    assert record['source_references'] == [{'source_id': 'SEC', 'content_hash': 'a' * 64}]
    assert publication.load_evidence(config, record)['financial_evidence'] == state['financial_evidence']
    from pathlib import Path
    assert all('PRIVATE' not in p.read_text() for p in Path(config['results_dir']).rglob('*.json'))


def test_analysis_clock_is_retained_only_for_new_clocked_publications(config, state):
    old = publication.publish(config, state, 'DOCN', '2026-11-04')
    assert 'analysis_clock' not in old
    assert publication.publish(config, copy.deepcopy(state), 'DOCN', '2026-11-04') == old
    state['run_id'] = str(uuid4())
    state['analysis_clock'] = {'analysis_timezone': 'America/Denver',
                               'cutoff_utc': '2026-11-05T06:59:59.999999+00:00'}
    new = publication.publish(config, state, 'DOCN', '2026-11-04')
    assert new['analysis_clock'] == state['analysis_clock']
    assert publication.load_record(config, new['decision_id']) == new


def test_changed_payload_with_same_run_cannot_rewrite_publication(config, state):
    first = publication.publish(config, state, 'DOCN', '2026-11-04')
    state['final_trade_decision'] += ' Changed.'
    with pytest.raises(ValueError, match='already published'):
        publication.publish(config, state, 'DOCN', '2026-11-04')
    assert publication.load_record(config, first['decision_id']) == first


def test_review_does_not_consume_primary_and_revisions_link_without_extra_samples(config, state):
    state['final_rating'] = 'REVIEW'
    review = publication.publish(config, state, 'DOCN', '2026-11-04')
    state['run_id'], state['final_rating'] = str(uuid4()), 'Underweight'
    primary = publication.publish(config, state, 'DOCN', '2026-11-04')
    state['run_id'], state['final_rating'] = str(uuid4()), 'Hold'
    revision = publication.publish(config, state, 'DOCN', '2026-11-04')
    assert review['eligibility']['directional'] is False
    assert primary['previous_decision_id'] == review['decision_id']
    assert primary['eligibility']['primary'] is True
    assert revision['previous_decision_id'] == primary['decision_id']
    assert revision['eligibility']['primary'] is False
    assert len(publication.list_records(config)) == 3


def test_historical_record_never_invents_past_publication(config, state):
    state["evaluation_mode"] = "historical"
    record = publication.publish(config, state, 'DOCN', '2026-10-19')
    assert record['published_at'].startswith('2026-11-04')
    assert record['eligibility']['prospective'] is False
    assert record['evaluation_mode'] == 'historical'
    assert record['requested_as_of'] == '2026-10-19'


def test_concurrent_same_day_runs_have_one_primary_and_linear_versions(config, state):
    def publish(_):
        own = {**state, 'run_id': str(uuid4())}
        return publication.publish(config, own, 'DOCN', '2026-11-04')
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(publish, range(8)))
    assert sum(r['eligibility']['primary'] for r in records) == 1
    assert len({r['previous_decision_id'] for r in records if r['previous_decision_id']}) == 7
    assert len(publication.list_records(config)) == 8


def test_failed_record_write_is_visible_and_retry_reuses_snapshot(config, state, monkeypatch):
    write = publication.replace_file
    def fail_record(path, callback, **kwargs):
        if path.parent.name == 'records':
            raise OSError('disk failure')
        return write(path, callback, **kwargs)
    monkeypatch.setattr(publication, 'replace_file', fail_record)
    with pytest.raises(OSError, match='disk failure'):
        publication.publish(config, state, 'DOCN', '2026-11-04')
    assert publication.list_records(config) == []
    monkeypatch.setattr(publication, 'replace_file', write)
    record = publication.publish(config, state, 'DOCN', '2026-11-04')
    assert publication.load_record(config, record['decision_id']) == record
    assert len(list((publication.record_root(config) / 'evidence').glob('*.json'))) == 1


def test_corrupt_record_and_missing_snapshot_are_visible(config, state):
    record = publication.publish(config, state, 'DOCN', '2026-11-04')
    root = publication.record_root(config)
    snapshot = root / record['evidence_snapshot']['path']
    snapshot.unlink()
    with pytest.raises(FileNotFoundError):
        publication.load_evidence(config, record)
    path = root / 'records' / (record['decision_id'] + '.json')
    changed = json.loads(path.read_text())
    changed['canonical_rating'] = 'Buy'
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='integrity'):
        publication.list_records(config)


@pytest.mark.parametrize('run_id', ['', '../../escape', 'not-a-uuid'])
def test_invalid_identity_cannot_escape_results(config, state, run_id):
    state['run_id'] = run_id
    with pytest.raises(ValueError, match='run_id'):
        publication.publish(config, state, 'DOCN', '2026-11-04')


def test_local_today_stays_prospective_after_utc_rollover(config, state, monkeypatch):
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 11, 5, 3, tzinfo=UTC))
    record = publication.publish(config, state, 'DOCN', '2026-11-04')
    assert record['evaluation_mode'] == 'prospective'
    assert record['published_at'] == '2026-11-05T03:00:00+00:00'
    assert record['publication_date_local'] == '2026-11-04'


def test_live_run_crossing_midnight_keeps_actual_publication_cutoff(config, state, monkeypatch):
    state['evaluation_mode'] = 'prospective'
    monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-05')
    monkeypatch.setattr(publication, '_utcnow', lambda: datetime(2026, 11, 5, 8, tzinfo=UTC))
    record = publication.publish(config, state, 'DOCN', '2026-11-04')
    assert record['evaluation_mode'] == 'prospective'
    assert record['eligibility']['prospective'] is True


def test_explicit_simulation_today_is_never_prospective(config, state):
    state['evaluation_mode'] = 'historical'
    record = publication.publish(config, state, 'DOCN', '2026-11-04')
    assert record['evaluation_mode'] == 'historical'
    assert record['eligibility']['prospective'] is False
