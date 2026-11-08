"""Offline, disposable R4 continuity proof. Prints hashes and counts, never private prose.

Run from this checkout with the project virtualenv. This is a scripted proof using
retained files and a stub portfolio-manager response, not a live model/vendor run.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import socket
import sys
import tempfile
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pytest import MonkeyPatch

from tests.test_portfolio_valuation import state as portfolio_state
from tests.test_price_observation import install as install_price_fixture
from tests.test_thesis import condition, state as financial_state
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.schemas import PortfolioDecision
from tradingagents.dataflows.vendors.yahoo import price_observation as prices
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.memory import publication, thesis
from tradingagents.memory.log import TradingMemoryLog

POINTER = Path('/tmp/r4-private-publication-baseline-path.txt')
FULL_STATE = Path.home() / '.tradingagents/logs/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-07_cfae95e9.json'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deny_network(*args, **kwargs):
    raise AssertionError('offline proof blocked network access')


def _private_baseline() -> tuple[Path, dict, str, str, dict]:
    manifest_path = Path(POINTER.read_text().strip())
    manifest = json.loads(manifest_path.read_text())
    source = Path(manifest['results_dir']) / 'publications'
    expected = manifest['original_files_sha256']
    assert expected and all(_sha(source / relative) == digest for relative, digest in expected.items())
    assert FULL_STATE.is_file()
    # The short label is never treated as an ID. Resolve and check the UUID in
    # the retained copy, then match the exact original terminal state marker.
    matches = list((source / 'records').glob('cfae95e9-*.json'))
    assert len(matches) == 1
    recent_id = str(UUID(matches[0].stem))
    original_state = json.loads(FULL_STATE.read_text())
    assert original_state['run_id'] == recent_id
    assert original_state['publication_record']['decision_id'] == recent_id
    previous = list((source / 'records').glob('913554d4-*.json'))
    assert len(previous) == 1
    first_id = str(UUID(previous[0].stem))
    return source, expected, first_id, recent_id, original_state


def _copy_record(source: Path, destination: Path, identity: str) -> dict:
    record_path = source / 'records' / f'{identity}.json'
    record = json.loads(record_path.read_text())
    evidence_path = source / record['evidence_snapshot']['path']
    for original in (record_path, evidence_path):
        target = destination / original.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    return record


def _graph_view(config: dict) -> TradingAgentsGraph:
    # record_decision is the production method; full graph construction would
    # create provider clients, which this offline proof expressly excludes.
    graph = object.__new__(TradingAgentsGraph)
    graph.config = config
    graph.memory_log = TradingMemoryLog(config)
    graph.run_settings = lambda: {'version': 'offline-proof'}
    return graph


def _same_day_sequence(root: Path, source: Path, first_id: str, recent_id: str,
                       state: dict) -> dict:
    config = {'results_dir': str(root / 'results'),
              'memory_log_path': str(root / 'memory' / 'trading_memory.md')}
    copied = Path(config['results_dir']) / 'publications'
    first = _copy_record(source, copied, first_id)
    latest = _copy_record(source, copied, recent_id)
    before = {identity: _sha(copied / 'records' / f'{identity}.json')
              for identity in (first_id, recent_id)}
    graph = _graph_view(config)
    graph.memory_log.store_decision('DOCN', '2026-11-07', first['canonical_decision'],
                                    first['canonical_rating'], first_id)
    captured_first = graph.memory_log.get_pending_entries()
    assert len(captured_first) == 1 and captured_first[0]['decision_id'] == first_id
    graph.record_decision('DOCN', '2026-11-07', dict(state))
    entries = graph.memory_log.load_entries()
    assert len(entries) == 1 and entries[0]['pending']
    assert entries[0]['decision_id'] == recent_id
    assert entries[0]['rating'] == latest['canonical_rating']
    assert not graph.memory_log.update_with_outcome(
        'DOCN', '2026-11-07', .01, .005, 5, 'stale scripted lesson',
        expected_entry=captured_first[0])
    memory_path = Path(config['memory_log_path'])
    retry_hash = _sha(memory_path)
    graph.record_decision('DOCN', '2026-11-07', dict(state))
    assert _sha(memory_path) == retry_hash
    assert len(graph.memory_log.load_entries()) == 1
    after = {identity: _sha(copied / 'records' / f'{identity}.json')
             for identity in (first_id, recent_id)}
    assert before == after
    assert len(publication.list_records(config)) == 2
    linked_thesis = thesis.load_latest_thesis(config, 'DOCN', datetime(2026, 11, 8, 1, tzinfo=UTC))
    assert linked_thesis is not None
    assert linked_thesis['publication_id'] == recent_id
    assert linked_thesis['version_id'] == latest['thesis_version_id']
    return {'first_publication_id': first_id, 'latest_publication_id': recent_id,
            'pending_entries': len(entries), 'memory_link_matches_latest': True,
            'stale_settlement_rejected': True, 'retry_memory_sha256': retry_hash,
            'record_sha256_before': before, 'record_sha256_after': after,
            'retained_thesis_matches_latest': True}


def _settlement_orderings(root: Path, first_id: str, recent_id: str) -> dict:
    # These use the real log's lock, conditional update and atomic replacement.
    prior = root / 'settled-first.md'
    settled_first = TradingMemoryLog({'memory_log_path': str(prior)})
    settled_first.store_decision('DOCN', '2026-11-07', 'Rating: Underweight',
                                 'Underweight', first_id)
    captured = settled_first.get_pending_entries()[0]
    assert settled_first.update_with_outcome(
        'DOCN', '2026-11-07', .01, .005, 5, 'scripted original lesson', expected_entry=captured)
    settled_hash = _sha(prior)
    settled_first.store_decision('DOCN', '2026-11-07', 'Rating: Hold', 'Hold', recent_id)
    assert _sha(prior) == settled_hash
    assert len(settled_first.load_entries()) == 1
    assert settled_first.load_entries()[0]['decision_id'] == first_id
    assert not settled_first.load_entries()[0]['pending']

    replacement = root / 'replacement-first.md'
    replacement_first = TradingMemoryLog({'memory_log_path': str(replacement)})
    replacement_first.store_decision('DOCN', '2026-11-07', 'Rating: Underweight',
                                     'Underweight', first_id)
    stale = replacement_first.get_pending_entries()[0]
    replacement_first.store_decision('DOCN', '2026-11-07', 'Rating: Hold', 'Hold', recent_id)
    assert not replacement_first.update_with_outcome(
        'DOCN', '2026-11-07', .01, .005, 5, 'scripted stale lesson', expected_entry=stale)
    current = replacement_first.get_pending_entries()[0]
    assert current['decision_id'] == recent_id
    assert replacement_first.update_with_outcome(
        'DOCN', '2026-11-07', .02, .006, 5, 'scripted current lesson', expected_entry=current)
    assert len(replacement_first.load_entries()) == 1
    assert replacement_first.load_entries()[0]['decision_id'] == recent_id
    assert not replacement_first.load_entries()[0]['pending']
    return {'settled_first_count': 1, 'settled_first_original_retained': True,
            'replacement_first_count': 1, 'replacement_first_stale_rejected': True,
            'settled_first_memory_sha256': settled_hash,
            'replacement_first_memory_sha256': _sha(replacement)}


def _three_kinds(root: Path) -> dict:
    now = datetime(2026, 11, 4, 22, tzinfo=UTC)
    with MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(publication, '_utcnow', lambda: now)
        monkeypatch.setattr(publication, 'get_current_date', lambda: '2026-11-04')
        install_price_fixture(monkeypatch, now='2026-11-04T22:00:00+00:00')
        quote = prices.get_price_observation('DOCN', '2026-11-04')
        event = {'kind': 'event', 'description': '<script>Settlement announced</script>',
                 'confirming_evidence': '8-K reporting note settlement',
                 'expiry': '2027-01-31', 'rationale': 'Open question'}
        proposal = {'rationale': 'Scripted research', 'conditions': [
            condition(), {'kind': 'price_level', 'comparator': '>=', 'threshold': '85',
                          'currency': 'USD', 'expiry': '2026-12-31', 'rationale': 'Watch close'},
            event, {**event, 'confirming_evidence': ''}]}
        model = MagicMock()
        model.with_structured_output.return_value.invoke.return_value = PortfolioDecision(
            rating='Hold', executive_summary='Wait', investment_thesis='Pending evidence',
            thesis_candidate=proposal)
        input_state = {**portfolio_state(), **financial_state('99'),
                       'company_of_interest': 'DOCN', 'trade_date': '2026-11-04',
                       'price_observation': quote}
        pm = create_portfolio_manager(model)(input_state)
        model.with_structured_output.return_value.invoke.assert_called_once()
        model.invoke.assert_not_called()
        run = {**input_state, **pm, 'run_id': str(uuid4()),
               'evidence_quality': {'status': 'limited'},
               'canonical_financial_context': 'Accepted Revenue 99 USD'}
        run.update(enforce_publication(run))
        kinds = [row.get('kind', 'metric') for row in run['thesis']['conditions']]
        assert kinds == ['metric', 'price_level', 'event']
        assert 'stated but not retained' in run['final_trade_decision']
        config = {'results_dir': str(root / 'three-kinds')}
        record = publication.publish(config, run, 'DOCN', '2026-11-04')
        loaded = thesis.load_latest_thesis(config, 'DOCN', now)
        assert loaded['publication_id'] == record['decision_id']
        assert [row.get('kind', 'metric') for row in loaded['conditions']] == kinds
        observed = thesis.observe_conditions(loaded, run)
        statuses = [row['status'] for row in observed]
        assert statuses == ['breached', 'met', 'unobserved']
        context = thesis.render_prior_thesis({**loaded, 'observations': observed})
        assert 'completed close' in context and '8-K reporting note settlement' in context
        assert '<script>Settlement announced</script>' in context
        assert '&lt;script&gt;' not in context
        return {'pm_stub_calls': 1, 'condition_kinds': kinds,
                'observed_statuses': statuses,
                'rejected_conditions': len(proposal['conditions']) - len(kinds),
                'publication_id': record['decision_id'],
                'publication_record_sha256': record['record_sha256'],
                'next_run_context_sha256': hashlib.sha256(context.encode()).hexdigest(),
                'next_run_context_plain_text': True}


def main() -> None:
    source, expected, first_id, recent_id, state = _private_baseline()
    full_state_hash = _sha(FULL_STATE)
    baseline_manifest_hash = _sha(Path(POINTER.read_text().strip()))
    with nullcontext(tempfile.mkdtemp(prefix='r4-memory-continuity-proof-')) as temporary:
        root = Path(temporary)
        with patch.object(socket.socket, 'connect', side_effect=_deny_network), \
             patch.object(socket.socket, 'connect_ex', side_effect=_deny_network), \
             patch('socket.create_connection', side_effect=_deny_network):
            sequence = _same_day_sequence(root, source, first_id, recent_id, state)
            ordering = _settlement_orderings(root, first_id, recent_id)
            kinds = _three_kinds(root)
            all_records = publication.list_records({'results_dir': str(source.parent)})
            baseline = json.loads(Path(POINTER.read_text().strip()).read_text())
            baselines = {row['decision_id']: row for row in baseline['records']}
            legacy_conditions = 0
            for record in all_records:
                evidence = publication.load_evidence({'results_dir': str(source.parent)}, record)
                previous = baselines[record['decision_id']]
                assert record['record_sha256'] == previous['record_sha256']
                assert record['evidence_snapshot']['sha256'] == previous['evidence_sha256']
                conditions = evidence.get('thesis', {}).get('conditions', [])
                assert len(conditions) == len(previous['conditions'])
                for condition, old in zip(conditions, previous['conditions'], strict=True):
                    parsed = thesis._condition(condition)
                    assert parsed.kind == 'metric'
                    assert condition['condition_id'] == old['condition_id']
                    assert thesis._id(parsed) == old['legacy_measurement_id']
                    assert condition.get('condition_aliases', []) == old['aliases']
                    serialized = json.dumps(thesis._row_data(parsed), sort_keys=True)
                    assert hashlib.sha256(serialized.encode()).hexdigest() == old['metric_dump_sha256']
                    legacy_conditions += 1
        assert all(_sha(source / relative) == digest for relative, digest in expected.items())
        assert _sha(FULL_STATE) == full_state_hash
    print(json.dumps({
        'proof_type': 'scripted_offline_disposable_store',
        'disposable_evidence_root': str(root),
        'live_model_or_vendor_calls': 0,
        'network_sockets_denied': True,
        'private_baseline_manifest_sha256': baseline_manifest_hash,
        'private_baseline_file_count': len(expected),
        'private_publications_loaded': len(all_records),
        'legacy_condition_ids_aliases_and_serialization_matched': legacy_conditions,
        'original_full_state_sha256': full_state_hash,
        'private_inputs_unchanged': True,
        'same_day_sequence': sequence,
        'settlement_orderings': ordering,
        'three_condition_kinds': kinds,
        'limitations': [
            '09:10 decision is seeded from its retained publication because its full terminal state was unavailable.',
            '16:41 record_decision replays the retained terminal state against a disposable copy of its immutable publication.',
            'PM output and price history are synthetic fixtures; this is not live provider or model behavior.',
        ],
    }, sort_keys=True))


if __name__ == '__main__':
    main()
