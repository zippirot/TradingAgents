"""Build D run archives retain exact publication-bound Ground Truth recovery."""
import json
from copy import deepcopy

import pytest

from tests.test_publication_graph import graph_and_state
from tradingagents.graph.trading_graph import _recover_logged_ground_truth, _state_log_path

RUN_A = '11111111-1111-4111-8111-111111111111'
RUN_B = '22222222-2222-4222-8222-222222222222'
DATE = '2026-11-04'
RECORD = {'run_id': RUN_A, 'record_sha256': 'publication-A'}
AUDIT_FIELDS = {
    'ground_truth_audit': {'record_sha256': 'audit-A', 'status': 'partial'},
    'ground_truth_prepublication': {'record_sha256': 'pre-A'},
    'ground_truth_reassessment': {'status': 'completed', 'original_decision': 'Original A reasoning.'},
    'ground_truth_execution': {'requests': 2, 'budget_tokens': 300, 'elapsed_seconds': 4.0},
    'ground_truth_source_documents': [{'source_id': 'retained-A'}],
    'ground_truth_source_acquisition': {'status': 'completed', 'record_sha256': 'sources-A'},
}


def snapshot(run_id=RUN_A, publication_hash='publication-A'):
    return {'run_id': run_id, 'publication_record': {'record_sha256': publication_hash}, **deepcopy(AUDIT_FIELDS)}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_older_same_day_run_recovers_its_archive_instead_of_latest_other_run(tmp_path):
    config = {'results_dir': str(tmp_path)}
    save(_state_log_path(config, 'DOCN', DATE, RUN_A), snapshot())
    latest = snapshot(RUN_B, 'publication-B')
    latest['ground_truth_audit']['record_sha256'] = 'audit-B'
    save(_state_log_path(config, 'DOCN', DATE), latest)
    recovered = _recover_logged_ground_truth(config, 'DOCN', DATE, RECORD)
    assert recovered == AUDIT_FIELDS
    assert recovered['ground_truth_audit']['record_sha256'] == 'audit-A'


def test_legacy_date_snapshot_remains_available_only_when_run_archive_is_absent(tmp_path):
    config = {'results_dir': str(tmp_path)}
    assert not _state_log_path(config, 'DOCN', DATE, RUN_A).exists()
    save(_state_log_path(config, 'DOCN', DATE), snapshot())
    assert _recover_logged_ground_truth(config, 'DOCN', DATE, RECORD) == AUDIT_FIELDS


@pytest.mark.parametrize('failure', ['wrong_run', 'wrong_publication', 'corrupt'])
def test_existing_invalid_archive_fails_closed_without_using_matching_daily_snapshot(tmp_path, failure):
    config = {'results_dir': str(tmp_path)}
    save(_state_log_path(config, 'DOCN', DATE), snapshot())
    archive = _state_log_path(config, 'DOCN', DATE, RUN_A)
    if failure == 'corrupt':
        archive.write_text('{')
    elif failure == 'wrong_run':
        # A truncated filename prefix is never sufficient publication identity.
        save(archive, snapshot('11111111-2222-4222-8222-222222222222'))
    else:
        save(archive, snapshot(publication_hash='different-publication'))
    assert _recover_logged_ground_truth(config, 'DOCN', DATE, RECORD) == {}


def test_state_archives_keep_ground_truth_and_build_d_projection_fields_together(tmp_path):
    app, state = graph_and_state(tmp_path)
    state.update(run_id=RUN_A, publication_record={'record_sha256': 'publication-A'}, **deepcopy(AUDIT_FIELDS))
    new_fields = {
        'document_followup_judgments': {'status': 'completed', 'questions': []},
        'prompt_evidence_references': [{'source_id': 'reference-A'}],
        'filing_terms_evidence': {'status': 'available'},
        'model_call_metadata': [{'stage': 'fixture', 'model': 'synthetic'}],
    }
    state.update(deepcopy(new_fields))
    app._log_state(DATE, state)
    daily = _state_log_path(app.config, 'DOCN', DATE)
    archive = _state_log_path(app.config, 'DOCN', DATE, RUN_A)
    assert daily.read_bytes() == archive.read_bytes()
    saved = json.loads(archive.read_text())
    for key, value in {**AUDIT_FIELDS, **new_fields}.items():
        assert saved[key] == value
    assert saved['run_id'] == RUN_A and saved['publication_record']['record_sha256'] == 'publication-A'
    assert _recover_logged_ground_truth(app.config, 'DOCN', DATE, RECORD) == AUDIT_FIELDS
