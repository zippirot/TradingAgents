"""Deterministic endpoint outcomes beside immutable research publications.

Each decision has one locked, atomically replaced companion. A resolved endpoint
is never fetched again; shorter windows and rotating prompt memory cannot hide
longer pending windows. No reflection or other model call occurs here.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path

from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.files import locked, replace_file
from tradingagents.memory.publication import list_records, load_evidence, load_record, record_root
from tradingagents.memory.settlement import fetch_outcome


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _initial(record: dict) -> dict:
    return {
        'schema_version': 1, 'decision_id': record['decision_id'],
        'publication_sha256': record['record_sha256'],
        'thesis_version_id': record['thesis_version_id'],
        'evaluation_mode': record['evaluation_mode'],
        'endpoints': {name: dict(endpoint) for name, endpoint in record['endpoints'].items()},
    }


def _validate_price_outcome(outcome: dict, record: dict, endpoint: dict) -> None:
    if (outcome['ticker'] != record['ticker'] or outcome['benchmark'] != endpoint['benchmark']
            or outcome['holding_days'] != endpoint['holding_days']):
        raise ValueError('Outcome identity does not match publication endpoint')
    for key in ('entry', 'exit', 'benchmark_entry', 'benchmark_exit'):
        price = outcome[key]['price']
        if isinstance(price, bool) or not math.isfinite(price) or price <= 0:
            raise ValueError('Outcome price is unavailable')
        date.fromisoformat(outcome[key]['date'])
    if (outcome['entry']['date'] >= outcome['exit']['date']
            or outcome['resolution_date'] != outcome['exit']['date']
            or outcome['benchmark_entry']['date'] > outcome['entry']['date']
            or outcome['benchmark_exit']['date'] > outcome['exit']['date']):
        raise ValueError('Outcome price dates do not match endpoint')
    raw = outcome['exit']['price'] / outcome['entry']['price'] - 1
    benchmark = outcome['benchmark_exit']['price'] / outcome['benchmark_entry']['price'] - 1
    for key, expected in (('raw_return', raw), ('benchmark_return', benchmark), ('alpha_return', raw - benchmark)):
        if not math.isclose(outcome[key], expected, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Outcome return does not match recorded prices')
    if not outcome['price_source'] or not outcome['price_adjustment']:
        raise ValueError('Outcome price provenance unavailable')


def load_outcomes(config: dict, record: dict) -> dict:
    """Read a verified companion, or the publication's original pending state.

    Missing/corrupt publication or corrupt existing outcomes raise; none are
    silently replaced by empty state. No file is created merely by reading.
    """
    canonical = load_record(config, record['decision_id'])
    if canonical != record:
        raise ValueError('Outcome publication integrity failure')
    initial = _initial(record)
    path = record_root(config) / 'outcomes' / f"{record['decision_id']}.json"
    if not path.exists():
        return initial
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        payload = {k: v for k, v in saved.items() if k != 'outcomes_sha256'}
        if saved['outcomes_sha256'] != _digest(payload):
            raise ValueError('checksum')
        if any(saved[key] != value for key, value in initial.items() if key != 'endpoints'):
            raise ValueError('identity')
        if saved['endpoints'].keys() != initial['endpoints'].keys():
            raise ValueError('endpoints')
        for name, endpoint in saved['endpoints'].items():
            original = initial['endpoints'][name]
            if any(endpoint[key] != value for key, value in original.items() if key != 'status'):
                raise ValueError('endpoint policy')
            if endpoint['status'] not in {original['status'], 'resolved'}:
                raise ValueError('endpoint status')
            if endpoint['status'] == 'resolved':
                if original['status'] == 'ineligible':
                    raise ValueError('ineligible endpoint')
                _validate_price_outcome(endpoint['outcome'], record, original)
                if datetime.fromisoformat(endpoint['resolved_at']).utcoffset() is None:
                    raise ValueError('resolution time')
        return saved
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Outcome integrity failure: {record['decision_id']}") from exc


def _write(path: Path, companion: dict) -> None:
    payload = {k: v for k, v in companion.items() if k != 'outcomes_sha256'}
    payload['outcomes_sha256'] = _digest(payload)
    replace_file(path, lambda temp: Path(temp).write_text(_json(payload) + '\n', encoding='utf-8'), strict=True)


def settle_publications(config: dict, ticker: str | None = None, wait: bool = True) -> dict:
    """Settle each due endpoint once; return settled IDs and visible failures.

    A stock/benchmark's current daily bar may be provisional. Exclude today's
    bars conservatively via prices_before; a later pass can resolve the window.
    Historical simulations use their as-of cutoff, explicitly separate from
    prospective records which also respect actual publication time.
    """
    result = {'settled': [], 'failed': []}
    for record in list_records(config, ticker):
        if not record['eligibility']['directional']:
            continue
        decision_id = record['decision_id']
        root = record_root(config) / 'outcomes'
        root.mkdir(parents=True, exist_ok=True)
        path = root / f'{decision_id}.json'
        try:
            with locked(path, wait=wait) as acquired:
                if not acquired:
                    continue
                companion = load_outcomes(config, record)
                load_evidence(config, record)
                for name, endpoint in sorted(companion['endpoints'].items(), key=lambda item: item[1]['holding_days']):
                    if endpoint['status'] != 'pending':
                        continue
                    try:
                        before = get_current_date()
                        outcome = fetch_outcome(
                            record['ticker'], record['requested_as_of'], endpoint['holding_days'],
                            endpoint['benchmark'],
                            published_at=record['published_at'] if record['evaluation_mode'] == 'prospective' else None,
                            prices_before=before,
                        )
                        if outcome is None:
                            continue
                        _validate_price_outcome(outcome, record, endpoint)
                        if outcome['resolution_date'] >= before:
                            continue
                    except Exception as exc:
                        result['failed'].append((decision_id, f'{name}: prices unavailable ({type(exc).__name__})'))
                        continue
                    companion['endpoints'][name] = {
                        **endpoint, 'status': 'resolved', 'outcome': outcome,
                        'resolved_at': datetime.now(UTC).isoformat(),
                    }
                    _write(path, companion)
                    result['settled'].append((decision_id, name))
        except Exception as exc:
            result['failed'].append((decision_id, f'Outcome persistence unavailable ({type(exc).__name__})'))
    return result
