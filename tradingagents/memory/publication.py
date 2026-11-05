"""Immutable research publications in the existing results tree.

The record is authoritative; date-based state, prompt memory and rendered reports
are projections. Endpoint outcomes belong in separate companions, never updates
to these records. A failed projection can retry using the original run identity.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from tradingagents.agents.rating import RATINGS_5_TIER, normalized_evidence_quality, run_rating
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.files import locked, replace_file
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.reporting import evidence_snapshot

_SCHEMA = 1
_SETTINGS = (
    'version', 'llm_provider', 'deep_think_provider', 'deep_think_llm',
    'quick_think_provider', 'quick_think_llm', 'analysts', 'max_debate_rounds',
    'max_risk_discuss_rounds', 'output_language', 'data_vendors', 'tool_vendors',
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _identity(value) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('publication run_id must be a UUID') from exc


def record_root(config: dict) -> Path:
    return Path(config['results_dir']) / 'publications'


def _write(path: Path, value: dict) -> None:
    replace_file(path, lambda temp: Path(temp).write_text(_json(value) + '\n', encoding='utf-8'), strict=True)


def _checked_record(path: Path) -> dict:
    record = json.loads(path.read_text(encoding='utf-8'))
    checksum = record.get('record_sha256')
    payload = {k: v for k, v in record.items() if k != 'record_sha256'}
    if (record.get('schema_version') != _SCHEMA or checksum != _digest(payload)
            or _identity(record.get('decision_id')) != path.stem):
        raise ValueError(f'Publication integrity failure: {path.name}')
    return record


def load_record(config: dict, decision_id: str) -> dict:
    """Read an exact publication; a missing/corrupt record is an error."""
    return _checked_record(record_root(config) / 'records' / f'{_identity(decision_id)}.json')


def list_records(config: dict, ticker: str | None = None) -> list[dict]:
    """Read all publications, including REVIEW and revisions, or fail visibly."""
    records = [_checked_record(p) for p in (record_root(config) / 'records').glob('*.json')]
    if ticker is not None:
        records = [r for r in records if r['ticker'] == normalize_symbol(ticker)]
    return sorted(records, key=lambda r: r['sequence'])


def load_evidence(config: dict, record: dict) -> dict:
    """Read the content-addressed snapshot, verifying its recorded hash."""
    ref = record['evidence_snapshot']
    digest = ref['sha256']
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Evidence integrity failure: invalid snapshot digest')
    path = record_root(config) / 'evidence' / f'{digest}.json'
    if ref['path'] != f'evidence/{digest}.json':
        raise ValueError('Evidence integrity failure: invalid snapshot path')
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    if _digest(snapshot) != digest:
        raise ValueError('Evidence integrity failure: snapshot content changed')
    return snapshot


def _sources(snapshot: dict) -> list[dict]:
    found = {}
    def visit(value):
        if isinstance(value, dict):
            if 'source_id' in value and 'content_hash' in value:
                ref = {k: value[k] for k in ('source_id', 'content_hash', 'url', 'locator') if k in value}
                found[_json(ref)] = ref
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
    visit(snapshot)
    return [found[k] for k in sorted(found)]


def publish(config: dict, state: dict, ticker: str, asof: str) -> dict:
    """Commit one canonical record, preserving identity on retries/re-exports.

    The graph supplies a fresh UUID for an actual invocation and checkpoints it.
    Calling again with that UUID and different canonical content fails rather
    than silently revising history. A genuinely new run supplies a new UUID.
    Only allowlisted run settings and existing canonical evidence are retained;
    raw model diagnostics and portfolio context are not duplicated here.
    """
    decision_id = _identity(state.get('run_id'))
    asof = date.fromisoformat(str(asof)).isoformat()
    ticker = normalize_symbol(ticker)
    snapshot = evidence_snapshot(state)
    snapshot.pop('raw_diagnostics', None)
    snapshot_hash = _digest(snapshot)
    settings = {k: state.get('run_settings', {}).get(k) for k in _SETTINGS
                if k in state.get('run_settings', {})}
    versions = state.get('publication_versions') or {}
    decision = state.get('final_trade_decision') or ''
    rating = run_rating(state)
    quality = normalized_evidence_quality(state).get('status', 'unvalidated')
    from tradingagents.memory.settlement import resolve_benchmark
    benchmark = resolve_benchmark(ticker, config)
    payload = {
        'run_id': decision_id, 'ticker': ticker, 'requested_as_of': asof,
        'asset_type': state.get('asset_type', 'stock'),
        'canonical_rating': rating, 'evidence_status': quality,
        'canonical_decision': decision[:12000], 'decision_truncated': len(decision) > 12000,
        'decision_sha256': hashlib.sha256(decision.encode('utf-8')).hexdigest(),
        'rating_basis': 'canonical publication; research opinion, not an executed position',
        'evidence_snapshot': {'sha256': snapshot_hash, 'path': f'evidence/{snapshot_hash}.json'},
        'source_references': _sources(snapshot),
        'run_settings': settings, 'configuration_sha256': _digest(settings),
        'versions': {key: versions.get(key) for key in ('code', 'prompt', 'schema')},
        'thesis_version_id': state.get('thesis_version_id'),
        'benchmark': benchmark,
        'target_sha256': _digest(state['target_validation']) if state.get('target_validation') else None,
        'scenarios_sha256': _digest(state['shared_valuation_scenarios']) if state.get('shared_valuation_scenarios') else None,
    }
    payload_hash = _digest(payload)
    root = record_root(config)
    for directory in ('records', 'evidence'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    # One short results-tree lock orders same-day versions and primary selection.
    with locked(root / 'publication'):
        path = root / 'records' / f'{decision_id}.json'
        if path.exists():
            existing = _checked_record(path)
            if existing['payload_sha256'] != payload_hash:
                raise ValueError('run_id already published with different canonical content')
            load_evidence(config, existing)
            return existing
        records = list_records(config)
        previous = [r for r in records if r['ticker'] == ticker and r['requested_as_of'] == asof]
        now = _utcnow()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('Publication time must have a timezone')
        now = now.astimezone(UTC)
        directional = rating in RATINGS_5_TIER and bool(decision) and quality in {'limited', 'sufficient'}
        primary = directional and not any(r['eligibility']['primary'] for r in previous)
        local_date = get_current_date()
        prospective = asof == local_date and directional
        record = {
            **payload, 'schema_version': _SCHEMA, 'decision_id': decision_id,
            'payload_sha256': payload_hash, 'published_at': now.isoformat(),
            'publication_date_local': local_date,
            'publication_date_basis': 'host local date (same policy as requested research date); not an exchange session',
            'sequence': max((r['sequence'] for r in records), default=0) + 1,
            'previous_decision_id': previous[-1]['decision_id'] if previous else None,
            'evaluation_mode': 'prospective' if asof == local_date else 'historical',
            'eligibility': {
                'directional': directional, 'primary': primary, 'prospective': prospective,
                'reason': ('canonical research publication' if directional else
                           'REVIEW, incomplete decision or unvalidated legacy evidence'),
            },
            'endpoints': {f'{days}_sessions': {
                'holding_days': days, 'status': 'pending' if directional else 'ineligible',
                'benchmark': benchmark,
                'entry_policy': 'first valid close strictly after publication/as-of session',
            } for days in (5, 21, 63)},
        }
        record['record_sha256'] = _digest(record)
        snapshot_path = root / record['evidence_snapshot']['path']
        if snapshot_path.exists():
            load_evidence(config, record)
        else:
            _write(snapshot_path, snapshot)
        _write(path, record)
        return record
