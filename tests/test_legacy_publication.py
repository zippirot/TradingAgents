"""Legacy evidence may be measured without inventing past publication metadata."""
import pytest

from tradingagents.memory import publication


def legacy():
    return {'ticker': 'DOCN', 'date': '2026-10-19', 'rating': 'Underweight',
            'decision': 'Rating: Underweight\nReduce exposure.', 'pending': False,
            'raw': '+6.9%', 'alpha': '+6.9%', 'holding': '5d', 'resolved': '2026-10-27',
            'reflection': 'Five days do not establish the three-month thesis.'}


def test_legacy_import_is_repeat_safe_and_never_acquires_publication_time(tmp_path):
    config = {'results_dir': str(tmp_path)}
    entry = legacy()
    record = publication.import_legacy_entry(config, entry, source_label='trading_memory.md',
                                              source_sha256='a' * 64)
    assert record['published_at'] is None
    assert record['imported_at']
    assert record['evaluation_mode'] == 'legacy'
    assert record['eligibility']['prospective'] is False
    assert record['evidence_status'] == 'unvalidated'
    assert record['legacy_import']['publication_time'] == 'unknown'
    assert record['endpoints']['5_sessions']['status'] == 'pending'
    assert publication.import_legacy_entry(config, entry, source_label='trading_memory.md',
                                            source_sha256='a' * 64) == record
    assert publication.load_evidence(config, record)['legacy_reported_outcome']['alpha'] == '+6.9%'
    assert len(publication.list_records(config)) == 1


def test_legacy_without_recorded_decision_cannot_be_imported(tmp_path):
    entry = legacy()
    entry['decision'] = ''
    with pytest.raises(ValueError, match='recorded decision'):
        publication.import_legacy_entry({'results_dir': str(tmp_path)}, entry,
                                         source_label='memory.md', source_sha256='a' * 64)
