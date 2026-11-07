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
from uuid import NAMESPACE_URL, UUID, uuid5

from tradingagents.agents.rating import RATINGS_5_TIER, normalized_evidence_quality, run_rating
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.files import locked, replace_file
from tradingagents.dataflows.symbols import crypto_base, normalize_symbol
from tradingagents.reporting import evidence_snapshot

_SCHEMA = 1

EVALUATION_PROTOCOL = {'version': 1,
 'primary_selection': 'first eligible ticker/as-of publication',
 'direction_mapping': {'Buy': 1, 'Overweight': 1, 'Hold': 0, 'Underweight': -1, 'Sell': -1},
 'prospective_descriptive_minimum': {'resolved_primary': 30, 'issuers': 3, 'analysis_dates': 10},
 'engineering_frozen_minimum': {'pairs': 4, 'issuers': 2, 'holdout_dates': 2},
 'metrics': ['coverage',
             'directional_excess_hit_rate',
             'mean_excess_return',
             'median_excess_return',
             'forecast_error',
             'scenario_envelope_coverage'],
 'performance_limit': 'Counts are disclosure thresholds, not statistical power guarantees; overlapping '
                      'horizons and issuer dependence remain. Historical LLM hindsight contamination '
                      'prevents clean skill inference.',
 'calibration': 'unavailable without defined mutually exclusive outcome events',
 'cost_policy': 'gross security/benchmark returns only; no portfolio P&L or assumed execution costs'}

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


def scan_records(config: dict, ticker: str | None = None) -> dict:
    """Read verified records for a listing, reporting damaged files in this scan.

    Never use this partial view to choose a publication sequence, primary, or
    revision link. Canonical writes and exact reads use the strict readers.
    """
    selected_ticker = normalize_symbol(ticker) if ticker is not None else None
    records, skipped = [], []
    for path in (record_root(config) / 'records').glob('*.json'):
        try:
            record = _checked_record(path)
            _scan_usable_record(record)
            if selected_ticker is None or record['ticker'] == selected_ticker:
                records.append(record)
        except (OSError, UnicodeError, ValueError, TypeError, AttributeError, KeyError) as exc:
            skipped.append({'path': path.name, 'reason': type(exc).__name__})
    return {'records': sorted(records, key=lambda r: r['sequence']),
            'skipped': sorted(skipped, key=lambda item: item['path'])}


def _scan_usable_record(record: dict) -> None:
    """Check fields needed to sort, list, and settle a scanned publication."""
    if (type(record.get('sequence')) is not int or record['sequence'] < 1
            or not isinstance(record.get('ticker'), str) or not record['ticker']
            or not isinstance(record.get('benchmark'), str) or not record['benchmark']
            or not isinstance(record.get('canonical_rating'), str)
            or record.get('evaluation_mode') not in {'prospective', 'historical', 'legacy'}
            or 'thesis_version_id' not in record):
        raise ValueError('Unusable publication record')
    normalize_symbol(record['ticker'])
    date.fromisoformat(record['requested_as_of'])
    if record['evaluation_mode'] == 'prospective':
        published = datetime.fromisoformat(record['published_at'])
        if published.utcoffset() is None:
            raise ValueError('Unusable publication timestamp')
    eligibility = record.get('eligibility')
    if (not isinstance(eligibility, dict)
            or type(eligibility.get('directional')) is not bool
            or type(eligibility.get('primary')) is not bool):
        raise ValueError('Unusable publication eligibility')
    endpoints = record.get('endpoints')
    if not isinstance(endpoints, dict) or not endpoints:
        raise ValueError('Unusable publication endpoints')
    for endpoint in endpoints.values():
        if (not isinstance(endpoint, dict)
                or endpoint.get('status') not in {'pending', 'ineligible'}
                or not isinstance(endpoint.get('benchmark'), str) or not endpoint['benchmark']
                or ('exit_policy' in endpoint and not isinstance(endpoint['exit_policy'], str))):
            raise ValueError('Unusable publication endpoint')
        kind = endpoint.get('horizon_type', 'trading_sessions')
        count = endpoint.get('calendar_months') if kind == 'calendar_months' else endpoint.get('holding_days')
        if kind not in {'trading_sessions', 'calendar_months'} or type(count) is not int or count < 1:
            raise ValueError('Unusable publication horizon')


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
    mode = state.get('evaluation_mode', 'prospective')
    if mode not in {'prospective', 'historical'}:
        raise ValueError('Publication evaluation mode must be prospective or historical')
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
        'evaluation_mode_requested': mode,
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
    if state.get('analysis_clock'):
        payload['analysis_clock'] = state['analysis_clock']
    return _store_payload(config, payload, snapshot)


def _store_payload(config: dict, payload: dict, snapshot: dict) -> dict:
    decision_id, ticker, asof = payload['run_id'], payload['ticker'], payload['requested_as_of']
    rating, quality = payload['canonical_rating'], payload['evidence_status']
    decision, benchmark = payload['canonical_decision'], payload['benchmark']
    legacy = bool(payload.get('legacy_import'))
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
        directional = rating in RATINGS_5_TIER and bool(decision) and (legacy or quality in {'limited', 'sufficient'})
        primary = directional and not any(r['eligibility']['primary'] for r in previous)
        local_date = get_current_date()
        prospective = not legacy and payload.get('evaluation_mode_requested') == 'prospective' and directional
        # Continuous crypto sessions need the established last-available benchmark
        # close policy. Select only for new records; existing publications above
        # retain their immutable declared alignment.
        is_crypto = payload.get('asset_type') == 'crypto' or crypto_base(ticker) is not None
        benchmark_alignment = 'asof' if is_crypto else 'exact_sessions'
        record = {
            **payload, 'schema_version': _SCHEMA, 'decision_id': decision_id,
            'payload_sha256': payload_hash, 'published_at': None if legacy else now.isoformat(),
            **({'imported_at': now.isoformat()} if legacy else {}),
            'publication_date_local': None if legacy else local_date,
            'publication_date_basis': ('unknown legacy publication date' if legacy else
                                       'host local date (same policy as requested research date); not an exchange session'),
            'sequence': max((r['sequence'] for r in records), default=0) + 1,
            'previous_decision_id': previous[-1]['decision_id'] if previous else None,
            'evaluation_mode': 'legacy' if legacy else payload['evaluation_mode_requested'],
            'eligibility': {
                'directional': directional, 'primary': primary, 'prospective': prospective,
                'reason': ('legacy recorded research; unknown publication time' if legacy else
                           'canonical research publication' if directional else
                           'REVIEW, incomplete decision or unvalidated legacy evidence'),
            },
            'evaluation_protocol': json.loads(_json(EVALUATION_PROTOCOL)),
            'endpoints': {
                (f'{count}_sessions' if kind == 'trading_sessions' else f'{count}_calendar_months'): {
                    'horizon_type': kind,
                    'holding_days': count if kind == 'trading_sessions' else None,
                    'calendar_months': count if kind == 'calendar_months' else None,
                    'status': 'pending' if directional else 'ineligible', 'benchmark': benchmark,
                    'benchmark_alignment': benchmark_alignment,
                    'exit_policy': ('nth_session_after_entry' if kind == 'trading_sessions' else
                                    'first_completed_session_on_or_after_nominal_date'),
                    'entry_policy': ('first valid close after recorded as-of date; legacy publication time unknown' if legacy else
                                     'first valid close strictly after publication/as-of session'),
                } for kind, count in [('trading_sessions', 5), ('trading_sessions', 21),
                                      ('trading_sessions', 63), ('calendar_months', 3), ('calendar_months', 6)]},
        }
        record['record_sha256'] = _digest(record)
        snapshot_path = root / record['evidence_snapshot']['path']
        if snapshot_path.exists():
            load_evidence(config, record)
        else:
            _write(snapshot_path, snapshot)
        _write(path, record)
        return record


def runtime_versions() -> dict:
    """Fingerprint installed source, including prompts, without storing local paths.

    Unlike a Git HEAD alone this also describes an uncommitted candidate or an
    installed package. Call at invocation start and preserve through checkpoints.
    """
    package = Path(__file__).resolve().parents[1]
    code, prompts = hashlib.sha256(), hashlib.sha256()
    for path in sorted(package.rglob('*.py')):
        relative = path.relative_to(package).as_posix()
        entry = relative.encode() + b'\0' + path.read_bytes() + b'\0'
        code.update(entry)
        if relative.startswith('agents/'):
            prompts.update(entry)
    return {'code': 'sha256:' + code.hexdigest(),
            'prompt': 'sha256:' + prompts.hexdigest(), 'schema': _SCHEMA}


def import_legacy_entry(config: dict, entry: dict, *, source_label: str, source_sha256: str) -> dict:
    """Explicitly import a recorded legacy decision for separately labeled scoring.

    This reads no user file and changes no original memory. The caller supplies
    a parsed existing entry and its file provenance. Rounded legacy outcomes are
    retained as reported, never substituted for measured endpoint prices.
    """
    from tradingagents.memory.settlement import resolve_benchmark

    if not entry.get('decision') or entry.get('rating') not in RATINGS_5_TIER:
        raise ValueError('Legacy import requires a recorded decision and recognized rating')
    if (not source_label or len(source_label) > 256 or len(source_sha256) != 64
            or any(c not in '0123456789abcdef' for c in source_sha256)):
        raise ValueError('Legacy source label and SHA256 are required')
    ticker = normalize_symbol(entry['ticker'])
    asof = date.fromisoformat(entry['date']).isoformat()
    decision = entry['decision']
    identity = {'ticker': ticker, 'date': asof, 'rating': entry['rating'], 'decision': decision}
    decision_id = str(uuid5(NAMESPACE_URL, 'tradingagents:legacy:' + _digest(identity)))
    existing = record_root(config) / 'records' / f'{decision_id}.json'
    if existing.exists():
        record = load_record(config, decision_id)
        load_evidence(config, record)
        return record
    snapshot = {
        'schema_version': 1, 'quality_status': 'unvalidated',
        'legacy_reported_outcome': {k: entry.get(k) for k in ('raw', 'alpha', 'holding', 'resolved')},
        'legacy_source': {'label': source_label, 'sha256': source_sha256},
    }
    snapshot_hash = _digest(snapshot)
    payload = {
        'run_id': decision_id, 'ticker': ticker, 'requested_as_of': asof,
        'canonical_rating': entry['rating'], 'evidence_status': 'unvalidated',
        'canonical_decision': decision[:12000], 'decision_truncated': len(decision) > 12000,
        'decision_sha256': hashlib.sha256(decision.encode('utf-8')).hexdigest(),
        'rating_basis': 'legacy recorded rating; evidence not revalidated; research only',
        'evidence_snapshot': {'sha256': snapshot_hash, 'path': f'evidence/{snapshot_hash}.json'},
        'source_references': [{'label': source_label, 'sha256': source_sha256}],
        'run_settings': {}, 'configuration_sha256': None,
        'versions': {'code': None, 'prompt': None, 'schema': None}, 'thesis_version_id': None,
        'benchmark': resolve_benchmark(ticker, config),
        'target_sha256': None, 'scenarios_sha256': None,
        'legacy_import': {'publication_time': 'unknown',
                          'benchmark_basis': 'declared on import; original benchmark provenance unavailable'},
    }
    return _store_payload(config, payload, snapshot)
