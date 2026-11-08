"""Offline disposable DOCN decision-page render metrics; private prose is never output."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from html import unescape
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tradingagents.agents.decision_context import _display
from tradingagents.reporting import write_report_tree

BASE_COMMIT = '82703a98b9726692ced53d761a643e7772494bde'
POINTER = Path('/tmp/r4-private-publication-baseline-path.txt')
STATE_ROOT = Path.home() / '.tradingagents/logs/DOCN/TradingAgentsStrategy_logs'
FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/docn_2026_11_07'
BASELINE_METADATA = Path('/tmp/r3-decision-page-baseline-82703a98.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deny_network(*args, **kwargs):
    raise AssertionError('offline proof blocked a network connection')


def _source() -> tuple[Path, dict, Path]:
    manifest_path = Path(POINTER.read_text().strip())
    manifest = json.loads(manifest_path.read_text())
    source = Path(manifest['results_dir']) / 'publications'
    expected = manifest['original_files_sha256']
    assert expected and all(_sha(source / name) == digest for name, digest in expected.items())
    original = Path(manifest['original_source'])
    assert all(_sha(original / name) == digest for name, digest in expected.items())
    return source, expected, manifest_path


def _record(source: Path, short: str) -> tuple[dict, Path, Path]:
    matches = list((source / 'records').glob(f'{short}-*.json'))
    assert len(matches) == 1
    path = matches[0]
    record = json.loads(path.read_text())
    assert record['decision_id'] == str(UUID(path.stem))
    evidence = source / record['evidence_snapshot']['path']
    assert evidence.is_file()
    return record, path, evidence


def _line_metrics(decision: str, state: dict) -> dict:
    lines = decision.splitlines()
    pm = state['unvalidated_outputs']['portfolio_manager']['structured']
    def plain(text):
        for _ in range(3):
            text = unescape(text)
        return re.sub(r'\\([\\`*_\[\]()#!|])', r'\1', text)
    pm_summary = pm['executive_summary']
    summary_lines = [i for i, line in enumerate(lines, 1)
                     if pm_summary in line or _display(pm_summary) in line]
    placeholder_lines = [i for i, line in enumerate(lines, 1)
                         if re.search(r'\*\*Executive Summary\*\*:\s*Model recommendation', line)]
    change_lines = [i for i, line in enumerate(lines, 1) if line.startswith('Changed since ')]
    condition_start = next((i for i, line in enumerate(lines)
                            if '**Advisory conditions at a glance**' in line), None)
    if condition_start is None:
        condition_lines = []
    else:
        condition_end = next((i for i in range(condition_start + 1, len(lines))
                              if lines[i] and not lines[i].startswith('- ')), len(lines))
        condition_lines = [line for line in lines[condition_start + 1:condition_end]
                           if line.startswith('- ')]
    conditions = state['thesis']['conditions']
    threshold_matches = []
    for index, row in enumerate(conditions):
        threshold = str(row.get('threshold', ''))
        comparator = str(row.get('comparator', ''))
        # The first advisory block retains source order. A condition counts
        # only when its own row shows both comparator and threshold.
        line = condition_lines[index] if index < len(condition_lines) else ''
        threshold_matches.append(bool(threshold and comparator and
                                      threshold in plain(line) and comparator in plain(line)))
    return {
        'decision_line_count': len(lines),
        'pm_summary_line_numbers': summary_lines,
        'pm_summary_first_40_lines': bool(summary_lines and min(summary_lines) <= 40),
        'placeholder_summary_line_numbers': placeholder_lines,
        'material_change_line_numbers': change_lines,
        'material_change_line_count': len(change_lines),
        'incompatible_method_summary_line_count': sum('Prior publication used a different valuation method' in line for line in lines),
        'carried_condition_count': len(conditions),
        'main_condition_block_line_count': len(condition_lines),
        'main_condition_threshold_match_count': sum(threshold_matches),
        'main_condition_threshold_matches': threshold_matches,
    }


def _amendment_source(source: Path) -> dict:
    record, record_path, evidence_path = _record(source, '16416b7e')
    state_path = STATE_ROOT / 'full_states_log_2026-11-07_16416b7e.json'
    state_available = state_path.is_file()
    state = json.loads(state_path.read_text()) if state_available else None
    evidence = json.loads(evidence_path.read_text())
    fixture_paths = sorted(FIXTURE.glob('16416b7e-*'))
    return {
        'record_path': str(record_path), 'record_sha256': _sha(record_path),
        'evidence_path': str(evidence_path), 'evidence_sha256': _sha(evidence_path),
        'state_path': str(state_path), 'state_available': state_available,
        'state_sha256': _sha(state_path) if state_available else None,
        'record_keys': sorted(record), 'evidence_keys': sorted(evidence),
        'state_keys': sorted(state) if state is not None else None,
        'fixture_files': [{'path': str(path), 'sha256': _sha(path)} for path in fixture_paths],
    }


def render(mode: str, report_dir: Path | None = None) -> dict:
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if mode == 'baseline':
        assert commit == BASE_COMMIT, 'baseline must use the exact pre-R3 source commit'
        assert not BASELINE_METADATA.exists(), 'baseline metadata already exists; do not overwrite it'
    source, expected, manifest_path = _source()
    record, record_path, evidence_path = _record(source, 'cfae95e9')
    state_path = STATE_ROOT / 'full_states_log_2026-11-07_cfae95e9.json'
    assert state_path.is_file()
    state_hash = _sha(state_path)
    state = json.loads(state_path.read_text())
    assert state['run_id'] == record['decision_id']
    assert state['publication_record']['record_sha256'] == record['record_sha256']
    with tempfile.TemporaryDirectory(prefix='r3-decision-page-proof-') as temporary:
        root = Path(temporary)
        copied = root / 'results' / 'publications'
        shutil.copytree(source, copied)
        copied_before = {name: _sha(copied / name) for name in expected}
        with patch.object(socket.socket, 'connect', side_effect=_deny_network), \
             patch.object(socket.socket, 'connect_ex', side_effect=_deny_network), \
             patch('socket.create_connection', side_effect=_deny_network):
            output = root / 'report'
            write_report_tree(state, 'DOCN', output, publication_config={'results_dir': str(root / 'results')})
        copied_after = {name: _sha(copied / name) for name in expected}
        assert copied_before == copied_after == expected, 'publication copy changed during render'
        decision_path = output / '5_portfolio' / 'decision.md'
        metrics = _line_metrics(decision_path.read_text(), state)
        report_hashes = {name: _sha(output / name) for name in (
            '5_portfolio/decision.md', 'complete_report.md', 'complete_report.html',
            'diagnostics.json', 'evidence.json', 'executive_summary.json')}
        if report_dir is not None:
            # Only a new disposable destination; never merge or replace a tree.
            shutil.copytree(output, report_dir)
    assert _sha(state_path) == state_hash
    assert all(_sha(source / name) == digest for name, digest in expected.items())
    original = Path(json.loads(manifest_path.read_text())['original_source'])
    assert all(_sha(original / name) == digest for name, digest in expected.items())
    result = {
        'mode': mode, 'source_commit': commit,
        'proof_type': 'retained_state_offline_disposable_verified_publication_render',
        'private_prose_in_output': False, 'network_connections_denied': True,
        'input_hashes': {'full_state_sha256': state_hash,
                         'publication_record_sha256': _sha(record_path),
                         'publication_evidence_sha256': _sha(evidence_path),
                         'private_store_manifest_sha256': _sha(manifest_path)},
        'publication_id': record['decision_id'],
        'private_store_file_count': len(expected),
        'original_and_disposable_publications_unchanged': True,
        'metrics': metrics, 'rendered_sha256': report_hashes,
        'amendment_16416b7e': _amendment_source(source),
        'limitations': [
            'This is a current renderer projection of a sealed historical publication, not a new publication or live model run.',
            'The retained source may have fields that candidate validation presents differently; immutable evidence and publication bytes stay unchanged.',
            'Generated export timestamps can change full report hashes independently of semantic changes.',
        ],
    }
    if mode == 'candidate':
        baseline = json.loads(BASELINE_METADATA.read_text())
        assert baseline['source_commit'] == BASE_COMMIT
        assert baseline['input_hashes'] == result['input_hashes'], 'candidate inputs differ from baseline'
        result['baseline_metrics'] = baseline['metrics']
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('baseline', 'candidate'))
    parser.add_argument('--report-dir', type=Path, help='New disposable directory for manual HTML/clipboard proof; contains private research.')
    arguments = parser.parse_args()
    result = render(arguments.mode, arguments.report_dir)
    if arguments.mode == 'baseline':
        with BASELINE_METADATA.open('x') as output:
            json.dump(result, output, indent=2, sort_keys=True)
            output.write('\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
