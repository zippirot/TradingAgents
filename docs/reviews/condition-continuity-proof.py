"""Offline reprocessing of retained PM output into a disposable condition store.

This is not a new live baseline. It leaves every original input/publication byte
unchanged and executes the current condition preparation/publication/export path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(root):
    return {str(p.relative_to(root)): sha(p) for p in root.rglob('*') if p.is_file()}


def denied(*args, **kwargs):
    raise AssertionError('Offline condition proof forbids network connections')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--state-sha256', required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--original-publications', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if sha(args.state) != args.state_sha256:
        raise ValueError('Retained state differs from the declared input')
    if args.output.exists() or any(p.is_symlink() for p in (args.output, *args.output.parents)):
        raise ValueError('Proof destination must be new and must not traverse symlinks')
    args.output.mkdir(parents=True, mode=0o700)
    original_hashes = files(args.original_publications)
    state = json.loads(args.state.read_text())
    original_conditions = deepcopy(state['thesis']['conditions'])
    prior_ids = {row['condition_id'] for row in state['prior_thesis']['conditions']}
    raw = deepcopy(state['thesis_candidate'])
    assert len(prior_ids) == 4 and len(raw['conditions']) == 8
    # Discard the changed behavior's cached outputs, not its retained raw inputs.
    for key in ('publication_record', 'publication_versions', 'thesis',
                'thesis_version_id', 'decision_context', 'final_trade_decision'):
        state.pop(key, None)
    with patch.object(socket.socket, 'connect', denied), patch.object(socket, 'create_connection', denied):
        from tradingagents.agents.output_validation import enforce_publication
        from tradingagents.comparison_snapshot import clone_starting_snapshot
        from tradingagents.dataflows.config import run_config
        from tradingagents.memory import publication, thesis
        from tradingagents.memory.log import TradingMemoryLog
        from tradingagents.reporting import write_report_tree

        config = clone_starting_snapshot(args.snapshot, args.output / 'store')
        # Same recorded analysis identity preserves the advisory response scope.
        # This independent pre-publication store contains no record for that ID;
        # the real original publication is never removed or overwritten.
        try:
            publication.load_record(config, state['run_id'])
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Pre-publication proof store already has this analysis')
        with run_config(config):
            state.update(enforce_publication(state, publication_config=config))
            conditions = state['thesis']['conditions']
            kinds = [row.get('kind', 'metric') for row in conditions]
            assert len(conditions) == 12 and prior_ids <= {r['condition_id'] for r in conditions}
            assert kinds.count('price_level') == kinds.count('event') == 2
            assert state['thesis_candidate'] == raw
            record = publication.publish(config, state, 'DOCN', state['trade_date'])
            state['publication_record'] = {k: record[k] for k in ('decision_id', 'published_at', 'record_sha256')}
            memory = TradingMemoryLog(config)
            memory.store_decision('DOCN', state['trade_date'], state['final_trade_decision'],
                                  rating=state['final_rating'], decision_id=record['decision_id'])
            report = write_report_tree(state, 'DOCN', args.output / 'reports',
                                      publication_config=config)
            loaded = thesis.load_latest_thesis(config, 'DOCN', record['published_at'])
            assert loaded['conditions'] == conditions
            observed = thesis.observe_conditions(loaded, state)
            assert len(observed) == 12
            context = thesis.render_prior_thesis({**loaded, 'observations': observed})
            assert all(row['condition_id'] in context for row in conditions)
            assert len([e for e in memory.load_entries() if e.get('decision_id') == record['decision_id']]) == 1
            decision = (report.parent / '5_portfolio/decision.md').read_text()
            assert sum(line.startswith('- Reconsideration trigger') for line in decision.splitlines()) == 12
    assert sha(args.state) == args.state_sha256
    assert files(args.original_publications) == original_hashes
    receipt = {'proof': 'offline current-code processing of a retained live PM response',
               'input_state': str(args.state), 'input_sha256': args.state_sha256,
               'analysis_identity': state['run_id'],
               'original_retained_conditions': len(original_conditions),
               'new_proposal_conditions': len(raw['conditions']), 'kept_prior_conditions': len(prior_ids),
               'corrected_retained_conditions': len(conditions), 'price_conditions': kinds.count('price_level'),
               'event_conditions': kinds.count('event'), 'all_prior_ids_preserved': True,
               'next_run_observations': len(observed), 'next_prompt_contains_all_ids': True,
               'memory_link_count': 1, 'rating': state['final_rating'],
               'original_publication_files_unchanged': len(original_hashes),
               'new_record': {**{k: record[k] for k in ('decision_id', 'record_sha256')},
                              'evidence_snapshot': record['evidence_snapshot']},
               'report_files': files(args.output / 'reports'), 'network_connections_denied': True,
               'limitations': ['Provider response is retained, not a new live call.',
                   'The isolated variant reuses its recorded analysis ID so advisory response scopes stay intact.',
                   'It does not change any real original publication or establish a fresh same-SHA paid baseline.']}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
