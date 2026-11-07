"""Atomic per-run recovery for the optional audit's unpublished work."""
import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from tradingagents.dataflows.files import locked, replace_file
from tradingagents.dataflows.symbols import safe_ticker_component

_RECOVERY_KEY = '_ground_truth_recovery_binding'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _path(state, config):
    run_id = state.get('run_id')
    if not config.get('results_dir') or not isinstance(run_id, str) or not run_id:
        return None
    return (Path(config['results_dir']) / safe_ticker_component(state['company_of_interest'])
            / 'TradingAgentsStrategy_logs' / ('ground_truth_progress_' + _digest(run_id) + '.json'))


def checkpoint(state, config, *, reserve=False):
    """Persist actual progress, or conservatively reserve the unknown audit pass."""
    path = _path(state, config)
    if path is None or _RECOVERY_KEY not in state:
        return True  # Public standalone flow helpers have no durable run context.
    snapshot = deepcopy({key: value for key, value in state.items()
                         if key not in {'messages', 'publication_record'}})
    if reserve:
        from tradingagents.ground_truth import (
            DEFAULT_MAX_REQUESTS,
            DEFAULT_MAX_SECONDS,
            DEFAULT_MAX_TOKENS,
            _positive,
        )
        snapshot['ground_truth_execution'] = {
            'requests': _positive(config, 'ground_truth_max_requests', DEFAULT_MAX_REQUESTS, 512),
            'elapsed_seconds': _positive(config, 'ground_truth_max_seconds', DEFAULT_MAX_SECONDS, 7200),
            'budget_tokens': _positive(config, 'ground_truth_max_tokens', DEFAULT_MAX_TOKENS, 20_000_000),
        }
        snapshot['ground_truth_recovery_limit'] = 'An interrupted audit has unknown usage; the remaining allowance was reserved.'
    payload = {'schema_version': 1, 'run_id': state['run_id'], 'binding': state[_RECOVERY_KEY], 'state': snapshot}
    payload['sha256'] = _digest(payload)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        replace_file(path, lambda temp: Path(temp).write_text(json.dumps(payload, default=str), encoding='utf-8'), strict=True)
    except OSError:
        return False
    return True


def restore(state, config):
    """Restore a matching candidate while retaining spent authority on changes."""
    from tradingagents.ground_truth_display import build_report_inventory
    binding = _digest({'inventory': build_report_inventory(state)['digest'],
                       'versions': state.get('publication_versions')})
    state[_RECOVERY_KEY] = binding
    path = _path(state, config)
    if path is None or not path.exists():
        return
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        body = {key: value for key, value in saved.items() if key != 'sha256'}
        if (saved.get('schema_version') != 1 or saved.get('run_id') != state['run_id']
                or saved.get('sha256') != _digest(body) or not isinstance(saved.get('state'), dict)):
            raise ValueError('invalid recovery record')
    except (OSError, ValueError, TypeError):
        from tradingagents.ground_truth import (
            DEFAULT_MAX_REQUESTS,
            DEFAULT_MAX_SECONDS,
            DEFAULT_MAX_TOKENS,
            _positive,
        )
        state['ground_truth_execution'] = {
            'requests': _positive(config, 'ground_truth_max_requests', DEFAULT_MAX_REQUESTS, 512),
            'elapsed_seconds': _positive(config, 'ground_truth_max_seconds', DEFAULT_MAX_SECONDS, 7200),
            'budget_tokens': _positive(config, 'ground_truth_max_tokens', DEFAULT_MAX_TOKENS, 20_000_000),
        }
        state['ground_truth_reassessment'] = {'status': 'unavailable', 'reason': 'Recovery record unavailable. Recommendation needs review.'}
        return
    if saved['binding'] == binding:
        state.update(saved['state'])
        from tradingagents.memory.publication import load_record
        try:
            published = load_record(config, state['run_id'])
        except FileNotFoundError:
            published = None
        if published is not None:
            state['publication_record'] = {key: published[key] for key in (
                'decision_id', 'published_at', 'record_sha256')}
        marker = state.get('ground_truth_reassessment')
        if isinstance(marker, dict) and marker.get('status') != 'completed':
            marker['status'] = 'unavailable'
            marker['reason'] = 'An interrupted reassessment has an unknown outcome. Recommendation needs review.'
    else:
        previous = saved['state']
        if previous.get('ground_truth_execution'):
            state['ground_truth_execution'] = previous['ground_truth_execution']
        if previous.get('ground_truth_reassessment'):
            state['ground_truth_reassessment'] = {
                'status': 'unavailable',
                'reason': 'The report changed after the run consumed its reassessment. Recommendation needs review.'}


@contextmanager
def run_scope(state, config):
    """Serialize opted-in finalization only for the same run's sidecar."""
    path = _path(state, config)
    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        yield


def has_progress(state, config):
    path = _path(state, config)
    return path is not None and path.is_file()
