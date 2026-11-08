"""Golden kind-less publications emitted by the confirmed pre-R4 publisher.

The fixtures contain only synthetic test facts. Their manifest pins BASE
78e3611ffb3fd6d8672acc2c15f54489cc258ae6 output, independently of current
serialization and publication code.
"""

import hashlib
import json
from pathlib import Path

import pytest

from tests.test_thesis import margin_state
from tradingagents.memory import publication, thesis

ROOT = Path(__file__).parent / 'fixtures' / 'thesis_legacy_metric'
BASE = '78e3611ffb3fd6d8672acc2c15f54489cc258ae6'


def _fixture():
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['base_commit'] == BASE
    return {'results_dir': str(ROOT)}, manifest


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def test_existing_publications_without_kind_load_as_metric():
    config, manifest = _fixture()
    records = publication.list_records(config, 'DOCN')
    assert [row['decision_id'] for row in records] == [
        item['decision_id'] for item in manifest['records']]
    for record, expected in zip(records, manifest['records'], strict=True):
        assert publication.load_record(config, expected['decision_id']) == record
        saved = publication.load_evidence(config, record)['thesis']
        assert saved['version_id'] == expected['thesis_version_id']
        assert saved['parent_version_id'] == expected['parent_version_id']
        assert len(saved['conditions']) == 1
        assert 'kind' not in saved['conditions'][0]
        assert thesis._condition(saved['conditions'][0]).kind == 'metric'
    assert thesis.load_latest_thesis(config, 'DOCN', '2026-11-04T21:30:00Z')['version_id'] == manifest['records'][0]['thesis_version_id']
    assert thesis.load_latest_thesis(config, 'DOCN', '2026-11-04T22:00:00Z')['version_id'] == manifest['records'][1]['thesis_version_id']


def test_legacy_publication_hashes_unchanged():
    config, manifest = _fixture()
    before = {name: hashlib.sha256((ROOT / 'publications' / name).read_bytes()).hexdigest()
              for name in manifest['files']}
    assert before == manifest['files']
    for record, expected in zip(publication.list_records(config, 'DOCN'), manifest['records'], strict=True):
        assert record['record_sha256'] == expected['record_sha256']
        assert record['evidence_snapshot']['sha256'] == expected['evidence_sha256']
        publication.load_evidence(config, record)
    after = {name: hashlib.sha256((ROOT / 'publications' / name).read_bytes()).hexdigest()
             for name in manifest['files']}
    assert after == before


def test_legacy_metric_condition_ids_and_dispositions_unchanged():
    config, manifest = _fixture()
    records = publication.list_records(config, 'DOCN')
    for record, expected in zip(records, manifest['records'], strict=True):
        saved = publication.load_evidence(config, record)['thesis']
        row = saved['conditions'][0]
        parsed = thesis._condition(row)
        assert row['condition_id'] == expected['condition_id']
        assert row['condition_aliases'] == expected['condition_aliases']
        assert thesis._id(parsed) == expected['legacy_measurement_id']
        assert _digest(thesis._row_data(parsed)) == expected['metric_dump_sha256']
        assert [(item['condition_id'], item['disposition'], item['disposition_reason'])
                for item in saved['prior_conditions']] == [tuple(item) for item in expected['prior_dispositions']]

    prior = publication.load_evidence(config, records[-1])['thesis']
    observed = thesis.observe_conditions(prior, margin_state())
    assert observed[0]['condition_id'] == manifest['records'][-1]['condition_id']
    context = thesis.render_prior_thesis({**prior, 'observations': observed})
    assert manifest['records'][-1]['condition_id'] in context
    carried = thesis.prepare_thesis(
        {'conditions': None, 'dispositions': [
            {'condition_id': prior['conditions'][0]['condition_aliases'][0],
             'disposition': 'kept', 'reason': 'Retain the same synthetic measurement'}]},
        {**prior, 'observations': observed}, 'Hold', '2026-11-05',
        '33333333-3333-4333-8333-333333333333',
        financial_evidence=margin_state()['financial_evidence'])
    assert carried['conditions'][0]['condition_id'] == manifest['records'][-1]['condition_id']
    assert carried['conditions'][0]['condition_aliases'] == manifest['records'][-1]['condition_aliases']
    assert carried['prior_conditions'][0]['disposition'] == 'kept'


def test_fault_injection_default_kind_would_break_legacy_identity(monkeypatch):
    """Process-only negative control; this is not a defect in current output."""
    config, manifest = _fixture()
    row = publication.load_evidence(config, publication.list_records(config, 'DOCN')[0])['thesis']['conditions'][0]
    parsed = thesis._condition(row)
    original = thesis._row_data
    monkeypatch.setattr(thesis, '_row_data', lambda condition: {**original(condition), 'kind': 'metric'})
    with pytest.raises(AssertionError):
        assert thesis._id(parsed) == manifest['records'][0]['legacy_measurement_id']
