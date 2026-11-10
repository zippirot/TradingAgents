"""Deterministic endpoint outcomes beside immutable research publications.

Each decision has one locked, atomically replaced companion. A resolved endpoint
is never fetched again; shorter windows and rotating prompt memory cannot hide
longer pending windows. No reflection or other model call occurs here.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.files import locked, replace_file
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.memory.publication import load_evidence, load_record, record_root, scan_records
from tradingagents.memory.settlement import (
    PricePass,
    SettlementCoverageError,
    _by_day,
    calendar_exit_date,
    fetch_outcome,
)

ZERO_REASON = 'No eligible instrument sessions on three post-horizon checks'
# Bounded, dated proof, not a perpetual exchange-calendar approximation.
# SPY listing: https://www.ssga.com/us/en/institutional/etfs/state-street-spdr-sp-500-etf-trust-spy
# Closures: https://www.nyse.com/trade/hours-calendars (2026 column, checked 2026-11-07).
_SPY_CLOSED_2026 = {'2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03',
                    '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07',
                    '2026-11-26', '2026-12-25'}


def _now():
    from tradingagents.source_replay import current_session, source_now

    return source_now(UTC) if current_session() else datetime.now(UTC)


def _aware(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError('Known-at time requires timezone')
    return stamp.astimezone(UTC)


def _entry_cutoff(record, zone=None):
    cutoff = date.fromisoformat(record['requested_as_of'])
    if record['evaluation_mode'] == 'prospective':
        from zoneinfo import ZoneInfo
        if not zone:
            raise ValueError('Instrument timezone unavailable for publication-session cutoff')
        cutoff = max(cutoff, _aware(record['published_at']).astimezone(ZoneInfo(zone)).date())
    return cutoff


def _validate_retry_endpoint(endpoint, original, record):
    status = endpoint['status']
    if status not in {original['status'], 'resolved', 'unresolvable'}:
        raise ValueError('endpoint status')
    if original['status'] == 'ineligible' and status != 'ineligible':
        raise ValueError('ineligible endpoint')
    checks = endpoint.get('zero_checks', [])
    if not isinstance(checks, list) or len(checks) > 3:
        raise ValueError('zero-coverage checks')
    if len(checks) == 3 and status != 'unresolvable':
        raise ValueError('Third zero check must establish terminal status')
    if status == 'resolved' and checks:
        raise ValueError('Resolved endpoint retains active zero checks')
    if status != 'resolved' and any(key in endpoint for key in ('outcome', 'resolved_at', 'coincident_with')):
        raise ValueError('Nonpriced endpoint carries a priced outcome')
    recorded = record.get('published_at') or record.get('imported_at')
    knowledge_floor = _aware(recorded) if recorded else datetime.combine(
        date.fromisoformat(record['requested_as_of']), datetime.min.time(), UTC)
    seen, previous = set(), None
    for check in checks:
        if check.get('zero_source', 'well_formed_empty_history') not in {
                'well_formed_empty_history', 'yahoo_explicit_window_no_data'}:
            raise ValueError('Unknown zero-coverage source')
        identity = str(UUID(check['pass_id']))
        stamp = _aware(check['checked_at'])
        cutoff = _entry_cutoff(record, check['instrument_timezone'])
        first = date.fromisoformat(check['reference_entry_date'])
        last = date.fromisoformat(check['reference_exit_date'])
        if (stamp < knowledge_floor or identity in seen
                or (previous is not None and (stamp.date() - previous.date()).days < 14)
                or first <= cutoff or last < first
                or date.fromisoformat(check['window_start']) > cutoff
                or date.fromisoformat(check['window_end_exclusive']) <= last
                or date.fromisoformat(check['window_end_exclusive']) > stamp.date()):
            raise ValueError('zero-coverage check identity or dates')
        kind, count = endpoint_group_key(original)
        if kind == 'calendar_months':
            if last < calendar_exit_date(first, count):
                raise ValueError('nominal calendar horizon')
        elif type(check['reference_sessions']) is not int or check['reference_sessions'] < count + 1:
            raise ValueError('nominal session horizon')
        seen.add(identity)
        previous = stamp
    terminal = endpoint.get('terminal')
    if status == 'unresolvable':
        if original['status'] != 'pending' or not isinstance(terminal, dict):
            raise ValueError('terminal endpoint')
        known = _aware(terminal['known_at'])
        if known < knowledge_floor:
            raise ValueError('Terminal knowledge precedes publication')
        reason = terminal['reason']
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 240:
            raise ValueError('terminal reason')
        if terminal['kind'] == 'zero_coverage':
            if len(checks) != 3 or reason != ZERO_REASON or known < previous:
                raise ValueError('terminal zero-coverage evidence')
        elif terminal['kind'] == 'calendar_mismatch':
            proof = terminal['proof']
            first, last = (date.fromisoformat(proof[k]) for k in ('entry_date', 'exit_date'))
            if (original.get('benchmark_alignment') != 'exact_sessions'
                    or original['benchmark'] != 'SPY' or proof['calendar_id'] != 'nyse-arca-spy-2026'
                    or proof['closed_date'] not in _SPY_CLOSED_2026
                    or proof['closed_date'] not in {str(first), str(last)}
                    or first <= _entry_cutoff(record, proof['instrument_timezone'])
                    or last <= first or last >= known.date()):
                raise ValueError('terminal calendar evidence')
        else:
            raise ValueError('terminal classification')
    elif terminal is not None:
        raise ValueError('nonterminal endpoint has terminal assertion')
    history = endpoint.get('terminal_history', [])
    if not isinstance(history, list):
        raise ValueError('terminal history')
    last_reopened = None
    for item in history:
        known, reopened = _aware(item['known_at']), _aware(item['reopened_at'])
        if (item['kind'] != 'zero_coverage' or item['reason'] != ZERO_REASON
                or known < knowledge_floor or reopened < known
                or (last_reopened is not None and known < last_reopened)):
            raise ValueError('terminal reopen history')
        last_reopened = reopened
    if last_reopened is not None and (
            (terminal and _aware(terminal['known_at']) < last_reopened)
            or any(_aware(check['checked_at']) < last_reopened for check in checks)):
        raise ValueError('Retry evidence predates manual reopen')
    if original['status'] == 'ineligible' and (checks or history or terminal):
        raise ValueError('ineligible retry metadata')


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def endpoint_group_key(endpoint: dict) -> tuple[str, int]:
    """Group by declared horizon, never a calendar window's realized bar count."""
    kind = endpoint.get('horizon_type', 'trading_sessions')
    count = endpoint.get('calendar_months') if kind == 'calendar_months' else endpoint.get('holding_days')
    if kind not in {'calendar_months', 'trading_sessions'} or type(count) is not int or count <= 0:
        raise ValueError('Invalid declared endpoint horizon')
    return kind, count


def endpoint_label(endpoint: dict) -> str:
    kind, count = endpoint_group_key(endpoint)
    return f'{count} calendar months' if kind == 'calendar_months' else f'{count} sessions'


def endpoint_sort_key(endpoint: dict) -> tuple[int, int]:
    kind, count = endpoint_group_key(endpoint)
    return (count * 21, 1) if kind == 'calendar_months' else (count, 0)


def _window_id(outcome):
    return _digest({key: outcome[key] for key in ('ticker', 'benchmark', 'price_adjustment')} |
                   {'entry':outcome['entry']['date'], 'exit':outcome['exit']['date'],
                    'benchmark_entry':outcome['benchmark_entry']['date'],
                    'benchmark_exit':outcome['benchmark_exit']['date']})


def _initial(record: dict) -> dict:
    return {
        'schema_version': 1, 'decision_id': record['decision_id'],
        'publication_sha256': record['record_sha256'],
        'thesis_version_id': record['thesis_version_id'],
        'evaluation_mode': record['evaluation_mode'],
        'endpoints': {name: dict(endpoint) for name, endpoint in record['endpoints'].items()},
    }


def _validate_price_outcome(outcome: dict, record: dict, endpoint: dict) -> None:
    kind, count = endpoint_group_key(endpoint)
    # The producer's explanatory label is optional in older companions, but
    # a supplied label must not claim a different execution/entry policy.
    if ('entry_policy' in outcome
            and outcome['entry_policy'] != 'first valid close strictly after cutoff_date'):
        raise ValueError('Outcome entry policy does not match supported price observation')
    if (outcome['ticker'] != record['ticker'] or outcome['benchmark'] != endpoint['benchmark']
            or type(outcome['holding_days']) is not int or outcome['holding_days'] < 1
            or (kind == 'trading_sessions' and outcome['holding_days'] != count)):
        raise ValueError('Outcome identity does not match publication endpoint')
    if kind == 'calendar_months':
        nominal = calendar_exit_date(date.fromisoformat(outcome['entry']['date']), count)
        if (outcome.get('calendar_months') != count or outcome.get('horizon_type') != kind
                or outcome.get('nominal_exit_date') != str(nominal)
                or date.fromisoformat(outcome['exit']['date']) < nominal
                or outcome.get('exit_policy') != endpoint['exit_policy']):
            raise ValueError('Calendar outcome does not match declared endpoint')
    if (endpoint.get('benchmark_alignment') == 'exact_sessions'
            and (outcome['benchmark_entry']['date'] != outcome['entry']['date']
                 or outcome['benchmark_exit']['date'] != outcome['exit']['date'])):
        raise ValueError('Exact benchmark endpoint dates unavailable')
    if outcome.get('observation_window_id') and outcome['observation_window_id'] != _window_id(outcome):
        raise ValueError('Outcome observation window identity mismatch')
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
            _validate_retry_endpoint(endpoint, original, record)
            if endpoint['status'] == 'resolved':
                if original['status'] == 'ineligible':
                    raise ValueError('ineligible endpoint')
                _validate_price_outcome(endpoint['outcome'], record, original)
                if datetime.fromisoformat(endpoint['resolved_at']).utcoffset() is None:
                    raise ValueError('resolution time')
                aliases = endpoint.get('coincident_with', [])
                if not isinstance(aliases, list) or len(aliases) > len(saved['endpoints']):
                    raise ValueError('coincident endpoint metadata')
                for alias in aliases:
                    other = saved['endpoints'].get(alias)
                    if (alias == name or not other or other['status'] != 'resolved'
                            or _window_id(other['outcome']) != _window_id(endpoint['outcome'])):
                        raise ValueError('coincident endpoint window mismatch')
        return saved
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Outcome integrity failure: {record['decision_id']}") from exc


def _write(path: Path, companion: dict) -> None:
    record = load_record({'results_dir': str(path.parent.parent.parent)}, companion['decision_id'])
    initial = _initial(record)
    if any(companion[key] != value for key, value in initial.items() if key != 'endpoints'):
        raise ValueError('Outcome publication identity mismatch')
    if companion['endpoints'].keys() != initial['endpoints'].keys():
        raise ValueError('Outcome endpoint identity mismatch')
    for name, endpoint in companion['endpoints'].items():
        original = initial['endpoints'][name]
        if any(endpoint[key] != value for key, value in original.items() if key != 'status'):
            raise ValueError('Outcome endpoint policy mismatch')
        _validate_retry_endpoint(endpoint, original, record)
    payload = {k: v for k, v in companion.items() if k != 'outcomes_sha256'}
    payload['outcomes_sha256'] = _digest(payload)
    replace_file(path, lambda temp: Path(temp).write_text(_json(payload) + '\n', encoding='utf-8'), strict=True)


class _OutcomeWriteError(Exception):
    def __init__(self, error_type):
        self.error_type = error_type
        super().__init__(error_type)


def _persist(path, companion):
    try:
        _write(path, companion)
    except Exception as exc:
        # Do not let another sibling write commit this failed in-memory update.
        raise _OutcomeWriteError(type(exc).__name__) from exc


def _due(endpoint, now, pass_id):
    checks = endpoint.get('zero_checks', [])
    return not checks or (pass_id not in {c['pass_id'] for c in checks}
                          and (now.date() - _aware(checks[-1]['checked_at']).date()).days >= 14)


def _pending_status(record, endpoint, prices, now):
    """Classify observed facts; None and elapsed time establish no terminal state."""
    ticker = record['ticker']
    kind, count = endpoint_group_key(endpoint)
    earliest_cutoff = date.fromisoformat(record['requested_as_of'])
    if record['evaluation_mode'] == 'prospective':
        # Earliest possible publication-local date across supported timezones.
        # This proves only impossibility of maturity, never an entry or return.
        earliest_cutoff = max(earliest_cutoff, (_aware(record['published_at']) - timedelta(hours=12)).date())
    earliest_entry = earliest_cutoff + timedelta(days=1)
    earliest_exit = (calendar_exit_date(earliest_entry, count) if kind == 'calendar_months'
                     else earliest_entry + timedelta(days=count))
    if earliest_exit >= date.fromisoformat(prices.before):
        return 'immature', 'Await maturity', None
    if ticker not in prices.prices:
        return 'retryable', 'Price window was not established', None
    stock, cutoff, before = prices.instrument(record)
    if not stock.empty:
        nominal = (calendar_exit_date(stock.index[0], count) if kind == 'calendar_months'
                   else stock.index[0] + timedelta(days=count))
        if nominal >= before:
            return 'immature', 'Await maturity', None
        complete = ((stock.index >= nominal).any() if kind == 'calendar_months' else len(stock) > count)
        if not complete:
            return 'retryable', 'Insufficient completed instrument sessions; coverage remains unresolved', None
        exit_day = stock[stock.index >= nominal].index[0] if kind == 'calendar_months' else stock.index[count]
        benchmark = _by_day(prices.get(endpoint['benchmark']))
        benchmark = benchmark[benchmark.index < before]
        if (endpoint.get('benchmark_alignment') == 'exact_sessions' and not benchmark.empty
                and benchmark.index[0] <= stock.index[0] and benchmark.index[-1] >= exit_day):
            missing = [day.strftime('%Y-%m-%d') for day in (stock.index[0], exit_day)
                       if day not in benchmark.index]
            known_closed = next((day for day in missing if endpoint['benchmark'] == 'SPY'
                                 and day in _SPY_CLOSED_2026), None)
            if known_closed:
                return 'terminal', f'Exact benchmark sessions unavailable: SPY exchange closed on {known_closed}', {
                    'kind': 'calendar_mismatch', 'known_at': now.isoformat(),
                    'proof': {'entry_date': stock.index[0].strftime('%Y-%m-%d'),
                              'exit_date': exit_day.strftime('%Y-%m-%d'),
                              'closed_date': known_closed, 'calendar_id': 'nyse-arca-spy-2026',
                              'instrument_timezone': str(prices.get(ticker).index.tz)},
                }
        return 'retryable', 'Exact benchmark price window unavailable; original alignment retained', None
    raw = prices.get(ticker)
    if (not raw.empty or raw.attrs.get('settlement_verified_empty') is not True
            or raw.attrs.get('settlement_request_start') != prices.starts[ticker].strftime('%Y-%m-%d')
            or raw.attrs.get('settlement_request_end') != prices.before):
        return 'retryable', 'Instrument zero coverage was not verified', None
    benchmark = _by_day(prices.get(endpoint['benchmark']))
    benchmark = benchmark[(benchmark.index > cutoff) & (benchmark.index < before)]
    if benchmark.empty:
        return 'retryable', 'Benchmark nominal horizon unavailable', None
    first = benchmark.index[0]
    if kind == 'calendar_months':
        target = calendar_exit_date(first, count)
        eligible = benchmark[benchmark.index >= target]
        if eligible.empty:
            return ('immature' if target >= before else 'retryable'), 'Benchmark nominal horizon not complete', None
        last, sessions = eligible.index[0], len(benchmark)
    else:
        if len(benchmark) <= count:
            earliest = first + timedelta(days=count)
            return ('immature' if earliest >= before else 'retryable'), 'Benchmark nominal horizon not complete', None
        last, sessions = benchmark.index[count], len(benchmark)
    return 'zero', 'Verified zero eligible instrument sessions after nominal horizon', {
        'checked_at': now.isoformat(), 'window_start': raw.attrs['settlement_request_start'],
        'window_end_exclusive': prices.before, 'reference_entry_date': first.strftime('%Y-%m-%d'),
        'reference_exit_date': last.strftime('%Y-%m-%d'), 'reference_sessions': sessions,
        'instrument_timezone': str(raw.index.tz) if raw.index.tz is not None else None,
        'zero_source': raw.attrs.get('settlement_zero_source', 'well_formed_empty_history'),
    }


def _clear_observed_zero_checks(record, endpoint, prices, path, companion):
    cached = prices.prices.get(record['ticker'])
    if (endpoint.get('zero_checks') and cached is not None and not isinstance(cached, Exception)
            and not prices.instrument(record)[0].empty):
        endpoint['zero_checks'] = []
        _persist(path, companion)


def settle_publications(config: dict, ticker: str | None = None, wait: bool = True, *, pass_id=None) -> dict:
    """One pass shares full bounded prices and persists each verified transition."""
    pass_id = str(UUID(pass_id)) if pass_id else str(uuid4())
    now = _now()
    before = min(get_current_date(), now.date().isoformat())
    scan = scan_records(config, ticker)
    result = {'settled': [], 'failed': [], 'immature': [], 'terminal': [],
              'deferred': [], 'skipped': scan['skipped']}
    records = [r for r in scan['records'] if r['eligibility']['directional']]
    # Independently validate companions before a symbol can enter the shared plan.
    prepared = []
    for record in records:
        try:
            saved = load_outcomes(config, record)
            prepared.append((record, saved))
        except Exception as exc:
            result['failed'].append((record['decision_id'], f'Outcome persistence unavailable ({type(exc).__name__})'))
    prices = PricePass([r for r, c in prepared if any(e['status'] == 'pending' for e in c['endpoints'].values())], before)
    prepared.sort(key=lambda pair: not any(e['status'] == 'pending' and _due(e, now, pass_id)
                                           for e in pair[1]['endpoints'].values()))
    for record, _ in prepared:
        decision_id = record['decision_id']
        root = record_root(config) / 'outcomes'
        root.mkdir(parents=True, exist_ok=True)
        path = root / f'{decision_id}.json'
        try:
            with locked(path, wait=wait) as acquired:
                if not acquired:
                    continue
                companion = load_outcomes(config, record)
                evidence_checked, evidence_error = False, None
                ordered = sorted(companion['endpoints'].items(),
                                 key=lambda item: (not _due(item[1], now, pass_id), endpoint_sort_key(item[1])))
                for name, endpoint in ordered:
                    if endpoint['status'] == 'unresolvable':
                        result['terminal'].append((decision_id, name))
                        continue
                    if endpoint['status'] != 'pending':
                        continue
                    if not _due(endpoint, now, pass_id):
                        cached = prices.prices.get(record['ticker'])
                        if cached is None or isinstance(cached, Exception) or prices.instrument(record)[0].empty:
                            result['deferred'].append((decision_id, name))
                            continue
                    try:
                        policy = {'benchmark_alignment': endpoint['benchmark_alignment']} if 'benchmark_alignment' in endpoint else {}
                        if endpoint.get('calendar_months'):
                            policy['calendar_months'] = endpoint['calendar_months']
                        outcome = fetch_outcome(
                            record['ticker'], record['requested_as_of'], endpoint['holding_days'], endpoint['benchmark'],
                            published_at=record['published_at'] if record['evaluation_mode'] == 'prospective' else None,
                            prices_before=before, price_fetcher=prices.window, **policy)
                    except SettlementCoverageError:
                        outcome = None
                    except Exception as exc:
                        _clear_observed_zero_checks(record, endpoint, prices, path, companion)
                        result['failed'].append((decision_id, f'{name}: prices unavailable ({type(exc).__name__})'))
                        continue
                    try:
                        _clear_observed_zero_checks(record, endpoint, prices, path, companion)
                        if outcome is None:
                            status, reason, proof = _pending_status(record, endpoint, prices, now)
                            if status == 'zero':
                                if _due(endpoint, now, pass_id):
                                    endpoint['zero_checks'] = [*endpoint.get('zero_checks', []), {**proof, 'pass_id': pass_id}]
                                    if len(endpoint['zero_checks']) == 3:
                                        endpoint.update(status='unresolvable', terminal={
                                            'kind': 'zero_coverage', 'reason': ZERO_REASON, 'known_at': now.isoformat()})
                                    _persist(path, companion)
                                if endpoint['status'] == 'unresolvable':
                                    result['terminal'].append((decision_id, name))
                                else:
                                    result['failed'].append((decision_id, f'{name}: {reason}; retry scheduled'))
                            elif status == 'terminal':
                                endpoint.update(status='unresolvable', terminal={**proof, 'reason': reason})
                                _persist(path, companion)
                                result['terminal'].append((decision_id, name))
                            elif status == 'immature':
                                result['immature'].append((decision_id, name))
                            else:
                                result['failed'].append((decision_id, f'{name}: {reason}'))
                            continue
                        _validate_price_outcome(outcome, record, endpoint)
                        if outcome['resolution_date'] >= before:
                            result['immature'].append((decision_id, name))
                            continue
                        if not evidence_checked:
                            evidence_checked = True
                            try:
                                load_evidence(config, record)
                            except Exception as exc:
                                evidence_error = exc
                        if evidence_error is not None:
                            raise ValueError('Retained publication evidence unavailable') from evidence_error
                        if endpoint.get('zero_checks'):
                            endpoint['zero_checks'] = []
                        outcome = {**outcome, 'observation_window_id': _window_id(outcome)}
                        coincident = [other for other, saved in companion['endpoints'].items()
                                      if saved['status'] == 'resolved' and _window_id(saved['outcome']) == outcome['observation_window_id']]
                        companion['endpoints'][name] = {**endpoint, 'status': 'resolved', 'outcome': outcome,
                                                       'resolved_at': now.isoformat(), 'coincident_with': coincident}
                        _persist(path, companion)
                        result['settled'].append((decision_id, name))
                    except _OutcomeWriteError:
                        raise
                    except Exception as exc:
                        result['failed'].append((decision_id, f'{name}: outcome unavailable ({type(exc).__name__})'))
        except _OutcomeWriteError as exc:
            result['failed'].append((decision_id, f'Outcome persistence unavailable ({exc.error_type})'))
        except Exception as exc:
            result['failed'].append((decision_id, f'Outcome persistence unavailable ({type(exc).__name__})'))
    return result


def reopen_endpoint(config, decision_id, endpoint_name):
    """Explicit local maintenance: reopen only a verified zero-coverage terminal."""
    record = load_record(config, decision_id)
    path = record_root(config) / 'outcomes' / f'{decision_id}.json'
    with locked(path):
        companion = load_outcomes(config, record)
        endpoint = companion['endpoints'][endpoint_name]
        terminal = endpoint.get('terminal') or {}
        if endpoint['status'] != 'unresolvable' or terminal.get('kind') != 'zero_coverage':
            raise ValueError('Only zero-coverage terminal endpoints can be manually reopened')
        now = _now()
        if now < _aware(terminal['known_at']):
            raise ValueError('Reopen time precedes terminal knowledge')
        endpoint['terminal_history'] = [*endpoint.get('terminal_history', []),
                                        {**terminal, 'reopened_at': now.isoformat()}]
        endpoint.pop('terminal')
        endpoint.update(status='pending', zero_checks=[])
        _write(path, companion)
        return companion


def _summary_cutoff(as_of: str | None, timezone_name: str = 'America/Denver') -> datetime | None:
    if as_of is None:
        return None
    if len(as_of) == 10:
        from tradingagents.dataflows.date_window import resolve_analysis_cutoff
        return datetime.fromisoformat(resolve_analysis_cutoff(as_of, timezone_name)['cutoff_utc'])
    cutoff = datetime.fromisoformat(as_of)
    if cutoff.utcoffset() is None:
        raise ValueError('Summary timestamp must include a timezone')
    return cutoff.astimezone(UTC)


def _known_by(timestamp: str | None, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    if not timestamp:
        return False
    known = datetime.fromisoformat(timestamp)
    if known.utcoffset() is None:
        raise ValueError('Recorded known-at timestamp must include a timezone')
    return known <= cutoff


def _summary_cell(value) -> str:
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def terminal_at(endpoint, cutoff=None):
    """The one terminal assertion visible before an explicit manual reopen."""
    terminal = endpoint.get('terminal')
    if terminal and _known_by(terminal['known_at'], cutoff):
        return terminal
    if cutoff is not None:
        for saved in reversed(endpoint.get('terminal_history', [])):
            if _known_by(saved['known_at'], cutoff) and cutoff < _aware(saved['reopened_at']):
                return saved
    return None


def render_outcome_summary(
    config: dict, ticker: str | None = None, as_of: str | None = None,
    *, limit: int | None = None,
) -> str:
    """Render known primary observations and ineligible coverage, never revise them.

    Dates mean the end of that calendar day in the configured analysis timezone;
    aware timestamps give an exact cutoff.
    Legacy publications become visible only at their recorded import time. An
    outcome must have been persisted by the cutoff as well as have its price
    window elapsed. Thus a later retrieval never becomes a retrospective lesson.
    ``limit`` bounds tabled publications for prompts; coverage still includes
    every visible record. Revisions are retained in coverage but are not samples.
    """
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError('Summary limit must be a positive integer')
    timezone_name = config.get('analysis_timezone', 'America/Denver')
    cutoff = _summary_cutoff(as_of, timezone_name)
    # Session dates remain separate from the analysis clock. A completed price
    # window dated tomorrow cannot be pulled into an evening-local-day replay.
    if as_of is not None:
        if len(as_of) == 10:
            analysis_day = date.fromisoformat(as_of)
        else:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                zone = ZoneInfo(timezone_name)
            except (ZoneInfoNotFoundError, ValueError):
                zone = UTC
            analysis_day = cutoff.astimezone(zone).date()
    scan = scan_records(config, ticker)
    records = [record for record in scan['records']
               if _known_by(record.get('published_at') or record.get('imported_at'), cutoff)]
    primary = [record for record in records if record['eligibility']['primary']]
    ineligible = [record for record in records if not record['eligibility']['directional']]
    revisions = len(records) - len(primary) - len(ineligible)
    tabled = [record for record in records if record['eligibility']['primary']
              or not record['eligibility']['directional']]
    lines = [
        '### Recommendation outcome horizons',
        '',
        f'Coverage: {len(records)} publications; {len(primary)} primary eligible observations; '
        f'{len(ineligible)} ineligible; {revisions} revisions excluded from independent samples.',
        'Gross security and benchmark returns describe price windows, not portfolio P&L. '
        'Underweight is a relative research opinion, not an executed short position.',
        'Trading-session and calendar-month diagnostics are distinct: 63 sessions is not three calendar months. '
        'A short-window result does not settle a longer investment thesis. Coincident windows are not independent samples.',
    ]
    if as_of is not None:
        lines.append(f'Known-at cutoff: {_summary_cell(cutoff.isoformat())}. '
                     'Outcomes recorded after this cutoff remain pending in this view.')
    if scan['skipped']:
        lines.append(f"Integrity omissions: {len(scan['skipped'])} unreadable publication file(s) skipped in this scan.")
    if limit is not None and len(tabled) > limit:
        lines.append(f'Showing latest {limit} of {len(tabled)} tabled publications; '
                     'earlier records remain in coverage above.')
        tabled = tabled[-limit:]
    if not tabled:
        lines.extend(['', 'No primary or ineligible publications are visible at this cutoff.'])
        return '\n'.join(lines)
    lines.append('')
    for index, record in enumerate(tabled, 1):
        published = record.get('published_at') or 'unknown (legacy publication time not recorded)'
        alignment = {endpoint.get('benchmark_alignment', 'asof')
                     for endpoint in record['endpoints'].values()}
        policy_note = (' Benchmark alignment: asof (last valid benchmark close on or before each instrument endpoint).'
                       if 'asof' in alignment else '')
        if any('benchmark_alignment' not in endpoint for endpoint in record['endpoints'].values()):
            policy_note += ' Legacy default policy; alignment was not explicitly recorded.'
        lines.append(
            f"- D{index}: {_summary_cell(record['ticker'])}, as-of {_summary_cell(record['requested_as_of'])}, "
            f"{_summary_cell(record['canonical_rating'])}, {_summary_cell(record['evaluation_mode'])}; "
            f"decision {_summary_cell(record['decision_id'])}; published {_summary_cell(published)}." + policy_note
        )
    lines.extend(['', 'Decision | Horizon | Status | Gross security return | Gross benchmark return | Excess return | Price window',
                  '--- | --- | --- | --- | --- | --- | ---'])
    for index, record in enumerate(tabled, 1):
        try:
            companion = load_outcomes(config, record)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            lines.append(f'D{index} | — | outcome integrity unavailable ({type(exc).__name__}) | — | — | — | —')
            continue
        for endpoint in sorted(companion['endpoints'].values(), key=endpoint_sort_key):
            status = endpoint['status']
            outcome = endpoint.get('outcome')
            terminal = terminal_at(endpoint, cutoff)
            if terminal:
                status = 'unresolvable'
            elif status == 'unresolvable':
                status = 'pending'
            if status == 'resolved' and (not _known_by(endpoint['resolved_at'], cutoff)
                    or (cutoff is not None and outcome['resolution_date'] > analysis_day.isoformat())):
                status = 'pending'
            if status == 'unresolvable':
                values = ['—', '—', '—', f"{_summary_cell(terminal['reason'])}; known at {_summary_cell(terminal['known_at'])}"]
            elif status == 'resolved':
                values = [f"{outcome['raw_return']:+.2%}",
                          f"{_summary_cell(endpoint['benchmark'])} {outcome['benchmark_return']:+.2%}",
                          f"{outcome['alpha_return']:+.2%}",
                          f"{outcome['entry']['date']} → {outcome['exit']['date']}"
                          + (f"; benchmark dates {outcome['benchmark_entry']['date']} → {outcome['benchmark_exit']['date']}"
                             if endpoint.get('benchmark_alignment', 'asof') == 'asof' else '')
                          + (f"; nominal {outcome['nominal_exit_date']}" if outcome.get('calendar_months') else '')
                          + (f"; same window as {', '.join(endpoint['coincident_with'])}" if endpoint.get('coincident_with') else '')]
            else:
                values = ['—'] * 4
            lines.append(f"D{index} | {endpoint_label(endpoint)} | {status} | " + ' | '.join(values))
    return '\n'.join(lines)


_RIGHT_WHEN = {'Buy': 1, 'Overweight': 1, 'Underweight': -1, 'Sell': -1}
_RATING_ORDER = ('Buy', 'Overweight', 'Hold', 'Underweight', 'Sell')
FEW_CALLS = 10


def scorecard(config: dict, ticker: str | None = None, as_of: str | None = None) -> dict:
    """Count settled primary outcomes by rating and horizon, for one ticker and for all tickers.

    The same known-at rules as the outcome table apply: an outcome recorded after the
    cutoff stays pending. Revisions and ineligible records are never samples. A call is
    right when its excess return over the benchmark has the sign its rating implies;
    Hold has no direction and is not scored.
    """
    timezone_name = config.get('analysis_timezone', 'America/Denver')
    cutoff = _summary_cutoff(as_of, timezone_name)
    analysis_day = None
    if as_of is not None:
        if len(as_of) == 10:
            analysis_day = date.fromisoformat(as_of)
        else:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                zone = ZoneInfo(timezone_name)
            except (ZoneInfoNotFoundError, ValueError):
                zone = UTC
            analysis_day = cutoff.astimezone(zone).date()
    scan = scan_records(config)
    own = normalize_symbol(ticker) if ticker else None
    groups, settled, pending, unreadable = {}, 0, 0, 0
    for record in scan['records']:
        if (not record['eligibility']['primary']
                or not _known_by(record.get('published_at') or record.get('imported_at'), cutoff)):
            continue
        try:
            companion = load_outcomes(config, record)
        except (OSError, ValueError, KeyError, TypeError):
            unreadable += 1
            continue
        for endpoint in companion['endpoints'].values():
            outcome = endpoint.get('outcome')
            known = (endpoint['status'] == 'resolved' and _known_by(endpoint['resolved_at'], cutoff)
                     and (cutoff is None or outcome['resolution_date'] <= analysis_day.isoformat()))
            if not known:
                pending += endpoint['status'] in {'pending', 'resolved'} and not terminal_at(endpoint, cutoff)
                continue
            settled += 1
            sign = _RIGHT_WHEN.get(record['canonical_rating'])
            for scope in ((record['ticker'], 'All tickers') if record['ticker'] == own else ('All tickers',)):
                group = groups.setdefault((scope, record['canonical_rating'], endpoint_label(endpoint)),
                                          {'order': endpoint_sort_key(endpoint), 'alphas': [], 'right': 0})
                group['alphas'].append(outcome['alpha_return'])
                group['right'] += bool(sign and outcome['alpha_return'] * sign > 0)

    def position(item):
        (scope, rating, _label), group = item
        return (scope == 'All tickers', _RATING_ORDER.index(rating) if rating in _RATING_ORDER else 9, group['order'])
    rows = [{'scope': scope, 'rating': rating, 'horizon': label, 'calls': len(group['alphas']),
             'right': group['right'] if rating in _RIGHT_WHEN else None,
             'average_excess': sum(group['alphas']) / len(group['alphas'])}
            for (scope, rating, label), group in sorted(groups.items(), key=position)]
    return {'ticker': own, 'rows': rows, 'settled': settled, 'pending': pending,
            'unreadable': unreadable + len(scan['skipped'])}


def render_scorecard(card: dict) -> str:
    """Plain summary of settled calls; pending windows are a count, never a row."""
    if not card['rows'] and not card['pending'] and not card['unreadable']:
        return ''  # no recommendation on record: nothing to say
    lines = ['### Track record (settled outcomes only)', '']
    if not card['rows']:
        lines.append('No settled outcome yet; nothing can be concluded about past calls.')
    else:
        lines += ['A call is right when its excess return over the benchmark has the sign its rating implies; '
                  'Hold is not scored. Gross price-window returns, not portfolio results.', '',
                  'Scope | Rating | Horizon | Calls | Right vs benchmark | Average excess | Reading',
                  '--- | --- | --- | --- | --- | --- | ---']
        for row in card['rows']:
            right = 'not scored' if row['right'] is None else f"{row['right']} of {row['calls']}"
            lines.append(f"{_summary_cell(row['scope'])} | {_summary_cell(row['rating'])} | {row['horizon']} | "
                         f"{row['calls']} | {right} | {row['average_excess']:+.2%} | "
                         + ('too few to conclude' if row['calls'] < FEW_CALLS else 'sample of ten or more'))
    lines += ['', f"{card['pending']} outcome window(s) pending across all tickers; they are not results."]
    if card['unreadable']:
        lines.append(f"{card['unreadable']} outcome record(s) could not be read and are not counted.")
    return '\n'.join(lines)


def _maintenance(argv=None):
    """Explicit maintenance invocation; never defaults to a live results tree."""
    import argparse

    parser = argparse.ArgumentParser(description='Maintain a verified local outcome companion')
    commands = parser.add_subparsers(dest='command', required=True)
    reopen = commands.add_parser('reopen', help='Reopen one zero-coverage terminal endpoint')
    reopen.add_argument('--results-dir', required=True)
    reopen.add_argument('--decision-id', required=True)
    reopen.add_argument('--endpoint', required=True)
    args = parser.parse_args(argv)
    companion = reopen_endpoint({'results_dir': args.results_dir}, args.decision_id, args.endpoint)
    endpoint = companion['endpoints'][args.endpoint]
    print(json.dumps({'decision_id': args.decision_id, 'endpoint': args.endpoint,
                      'status': endpoint['status'],
                      'reopened_at': endpoint['terminal_history'][-1]['reopened_at']}))


if __name__ == '__main__':
    _maintenance()
