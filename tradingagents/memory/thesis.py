"""Bounded advisory thesis continuity, stored only in immutable publications.

Proposals and assumptions are model research, never verified evidence or rules.
Observation consumes canonical evidence; no function changes a recommendation.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from tradingagents.dataflows.financial_evidence import EvidencePackage


class ThesisCondition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    metric: str = Field(min_length=1, max_length=120)
    metric_definition: str = Field(min_length=1, max_length=500)
    period_start: date | None = None
    period_end: date
    comparator: Literal['>=', '>', '<=', '<', '==']
    threshold: Decimal
    unit: str = Field(min_length=1, max_length=40)
    basis: str = Field(min_length=1, max_length=80)
    expiry: date
    rationale: str = Field(min_length=1, max_length=1000)
    thesis_role: Literal['supports_thesis', 'reconsideration_trigger', 'unspecified'] = Field(
        default='unspecified', description='Unvalidated research intent: a condition supporting the current thesis, a trigger to reconsider it, or unspecified. Never infer intent from comparator or rating.')

    @model_validator(mode='after')
    def dates(self):
        if self.period_start and self.period_start > self.period_end:
            raise ValueError('reversed condition period')
        if self.expiry < self.period_end:
            raise ValueError('condition expires before its measurement period')
        return self


def _id(condition):
    # Measurement identity excludes explanatory prose. Tuple normalization is
    # exact even beyond Decimal's default context precision (no normalize()).
    payload = condition.model_dump(mode='json', exclude={'rationale', 'thesis_role'})
    sign, digits, exponent = condition.threshold.as_tuple()
    digits = list(digits)
    if not any(digits):
        sign, digits, exponent = 0, [0], 0
    else:
        while digits[-1] == 0:
            digits.pop()
            exponent += 1
    payload['threshold'] = [sign, digits, exponent]
    return 'condition-' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]


def _condition(row):
    return ThesisCondition.model_validate({k:v for k,v in row.items()
                                          if k not in {'condition_id', 'condition_aliases'}})


def _valid_id(value):
    return (isinstance(value, str) and len(value) == 34 and value.startswith('condition-')
            and all(c in '0123456789abcdef' for c in value[10:]))


def _conditions(values, *, preserve_ids=False):
    accepted, warnings, by_measurement = [], [], {}
    if not isinstance(values, (list, tuple)):
        return [], ['Invalid advisory conditions: expected a list']
    if len(values) > 8:
        warnings.append('Advisory condition limit reached; only first eight considered')
    for index, item in enumerate(values[:8]):
        try:
            payload = dict(item)
            condition = _condition(payload)
            key = _id(condition)
            identifier = payload.get('condition_id') if preserve_ids else None
            identifier = identifier if _valid_id(identifier) else key
            aliases = payload.get('condition_aliases', []) if preserve_ids else []
            aliases = [v for v in aliases[:8] if _valid_id(v)] if isinstance(aliases, list) else []
            if key in by_measurement:
                row = by_measurement[key]
                if row.get('thesis_role') != condition.thesis_role:
                    row['thesis_role'] = 'unspecified'
                    warnings.append('Conflicting roles for an equivalent measurement; thesis role unspecified.')
                aliases = list(dict.fromkeys([*row.get('condition_aliases', []), identifier, *aliases]))
                warnings.append(f'Equivalent advisory measurement coalesced into {row["condition_id"]}.')
            else:
                row = {**condition.model_dump(mode='json'), 'condition_id':identifier}
                by_measurement[key] = row
                accepted.append(row)
            aliases = [v for v in aliases if v != row['condition_id']]
            if aliases:
                row['condition_aliases'] = aliases[:8]
                warnings.append(f'Condition {row["condition_id"]} aliases: ' + ', '.join(aliases[:8]))
        except (ValidationError, ValueError, TypeError):
            warnings.append(f'Invalid advisory condition at index {index}; retained only in raw diagnostics')
    return accepted, warnings


def _matches(row, dispositions):
    identities = {row['condition_id'], *row.get('condition_aliases', [])}
    return [d for d in dispositions if isinstance(d, dict) and isinstance(d.get('condition_id'), str)
            and d['condition_id'] in identities]


def _ambiguous(matches):
    return (any(d.get('disposition') not in ('kept', 'overridden', 'retired') for d in matches)
            or len({d.get('condition_id') for d in matches}) != len(matches)
            or len({d.get('disposition') for d in matches}) > 1)



def _gross_margin(condition, package, precision):
    if condition.unit != 'percent' or condition.basis != 'US-GAAP' or condition.period_start is None:
        raise ValueError('Gross Margin requires percent, US-GAAP and an explicit duration period')
    if not 80 <= (condition.period_end - condition.period_start).days + 1 <= 100:
        raise ValueError('Gross Margin condition requires a comparable quarterly duration')
    groups = [[fact for fact in package.facts if fact.value is not None and
               (fact.metric, fact.period_start, fact.period_end, fact.basis) ==
               (metric, condition.period_start, condition.period_end, condition.basis)]
              for metric in ('Gross Profit', 'Revenue')]
    if any(len(group) != 1 for group in groups):
        raise ValueError('Gross Margin inputs missing or competing; observation unresolved')
    profit, revenue = (group[0] for group in groups)
    if profit.unit != revenue.unit or len(profit.unit) != 3 or not profit.unit.isupper():
        raise ValueError('Gross Margin input currency mismatch')
    bounds = []
    for fact in (profit, revenue):
        try:
            quantum = Decimal(str(precision.get(fact.fact_id, '0')))
            if not quantum.is_finite() or quantum < 0:
                raise ValueError('Invalid rounding quantum')
            value, allowance = Fraction(fact.value), Fraction(quantum) / 2
            bounds.append((value - allowance, value + allowance))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError('Gross Margin source precision invalid') from exc
    if bounds[1][0] <= 0:
        raise ValueError('Gross Margin requires positive revenue throughout its rounding interval')
    ratios = [100 * numerator / denominator for numerator in bounds[0] for denominator in bounds[1]]
    return Fraction(profit.value) * 100 / Fraction(revenue.value), min(ratios), max(ratios), [profit, revenue]


def _number_text(value):
    if isinstance(value, Fraction):
        with localcontext() as context:
            context.prec = 50
            return str(Decimal(value.numerator) / Decimal(value.denominator))
    return str(value)

def observe_conditions(prior: dict | None, state: dict) -> list[dict]:
    """Evaluate exact same metric/period/unit/basis; rounding overlap is unknown.

    metric_definition must equal the canonical metric label; specialized
    subsets cannot borrow consolidated facts. No parsing of model narrative creates facts.
    """
    rows, _ = _conditions((prior or {}).get('conditions', []), preserve_ids=True)
    try:
        package = EvidencePackage.model_validate(state.get('financial_evidence'))
    except (ValidationError, ValueError, TypeError):
        package = None
    extraction = state.get('filing_fact_extraction')
    precision = extraction.get('rounding_quantum_by_fact', {}) if isinstance(extraction, dict) else {}
    precision = precision if isinstance(precision, dict) else {}
    observations = []
    for row in rows:
        condition = _condition(row)
        observation = {**row, 'status':'unknown', 'reason':'Compatible canonical evidence unavailable',
                       'observed_value':None, 'observed_date':None, 'fact_ids':[], 'source_ids':[]}
        observations.append(observation)
        if condition.metric_definition != condition.metric:
            observation['reason'] = 'Unsupported metric definition; canonical metric scope must match exactly'
            continue
        if package is None:
            continue
        if condition.expiry < package.as_of:
            observation['reason'] = 'Condition expired; no current compliance conclusion'
            continue
        if condition.metric == 'Gross Margin':
            try:
                value, low, high, matches = _gross_margin(condition, package, precision)
            except ValueError as exc:
                observation['reason'] = str(exc)
                continue
            observation.update(observed_value=_number_text(value), observed_date=str(condition.period_end),
                               fact_ids=[fact.fact_id for fact in matches],
                               input_fact_ids=[fact.fact_id for fact in matches],
                               source_ids=sorted({source for fact in matches for source in fact.source_ids}),
                               formula_id='gross_margin_percent_v1')
        else:
            matches = [fact for fact in package.facts if fact.value is not None and
                       (fact.metric, fact.period_start, fact.period_end, fact.unit, fact.basis) ==
                       (condition.metric, condition.period_start, condition.period_end, condition.unit, condition.basis)]
            if not matches:
                continue
            if len({fact.value for fact in matches}) != 1:
                observation['reason'] = 'Competing compatible canonical values; observation unresolved'
                continue
            observation.update(observed_value=str(matches[0].value), observed_date=str(condition.period_end),
                               fact_ids=[fact.fact_id for fact in matches],
                               source_ids=sorted({s for fact in matches for s in fact.source_ids}))
            bounds = []
            for fact in matches:
                try:
                    quantum = Decimal(str(precision.get(fact.fact_id, '0')))
                    if not quantum.is_finite() or quantum < 0:
                        raise ValueError('Invalid source precision')
                    bounds.append((fact.value - quantum / 2, fact.value + quantum / 2))
                except (InvalidOperation, ValueError, TypeError):
                    bounds = []
                    break
            if not bounds:
                observation['reason'] = 'Source precision invalid; observation unresolved'
                continue
            low, high = min(b[0] for b in bounds), max(b[1] for b in bounds)
        threshold = condition.threshold
        comparisons = {
            '>=': (low >= threshold, high < threshold), '>': (low > threshold, high <= threshold),
            '<=': (high <= threshold, low > threshold), '<': (high < threshold, low >= threshold),
            '==': (low == high == threshold, high < threshold or low > threshold),
        }
        met, breached = comparisons[condition.comparator]
        observation['status'] = 'met' if met else 'breached' if breached else 'unknown'
        observation['reason'] = ('Compatible canonical value satisfies advisory condition' if met else
                                 'Compatible canonical value does not satisfy the recorded comparison' if breached else
                                 'Source rounding interval overlaps threshold; no definite conclusion')
        observation['value_interval'] = [_number_text(low), _number_text(high)]
    return observations


def _texts(value, count, length):
    return [item[:length] for item in value[:count] if isinstance(item, str)] if isinstance(value, list) else []


def prepare_thesis(candidate, prior, canonical_rating, asof, run_id) -> dict:
    """Prepare an idempotent JSON proposal; publication supplies its known-at time."""
    UUID(run_id)
    date.fromisoformat(asof)
    candidate = candidate if isinstance(candidate, dict) else {}
    prior = prior if isinstance(prior, dict) else {}
    prior_conditions, warnings = _conditions(prior.get('conditions', []), preserve_ids=True)
    proposed = candidate.get('conditions')
    if proposed is None:
        conditions = prior_conditions
    else:
        conditions, proposal_warnings = _conditions(proposed)
        warnings.extend(proposal_warnings)
        if proposal_warnings and not conditions and proposed != []:
            conditions = prior_conditions
            warnings.append('Malformed optional conditions; prior advisory conditions retained')
    previous_by_key = {_id(_condition(row)): row for row in prior_conditions}
    for row in conditions:
        previous = previous_by_key.get(_id(_condition(row)))
        if previous is not None:
            row['condition_id'] = previous['condition_id']
            if row.get('thesis_role') == 'unspecified':
                row['thesis_role'] = previous.get('thesis_role', 'unspecified')
            if previous.get('condition_aliases'):
                row['condition_aliases'] = list(previous['condition_aliases'])
    dispositions = candidate.get('dispositions', [])
    dispositions = dispositions[:8] if isinstance(dispositions, list) else []
    preserved = []
    retired = set()
    for previous in prior_conditions:
        identifier = previous['condition_id']
        matches = _matches(previous, dispositions)
        if _ambiguous(matches):
            preserved.append(previous)
            warnings.append(f'Ambiguous duplicate dispositions for {identifier}; prior condition retained')
        elif matches and matches[0].get('disposition') == 'retired':
            retired.add(identifier)
        elif matches and matches[0].get('disposition') == 'kept':
            preserved.append(previous)
            if not any(c['condition_id'] == identifier for c in conditions):
                warnings.append(f'Kept condition {identifier} omitted from proposal; prior condition retained')
    # Preserve explicit keeps before adding new proposals; bound remains eight.
    combined = {row['condition_id']: row for row in preserved}
    for row in conditions:
        if row['condition_id'] not in retired:
            if row['condition_id'] in combined and row.get('thesis_role', 'unspecified') != 'unspecified':
                prior_role = combined[row['condition_id']].get('thesis_role', 'unspecified')
                combined[row['condition_id']] = {**combined[row['condition_id']], 'thesis_role': row['thesis_role']}
                if prior_role != row['thesis_role']:
                    warnings.append(f"Condition {row['condition_id']} role explicitly proposed for this version; prior observations retain their original interpretation.")
            else:
                combined.setdefault(row['condition_id'], row)
    if len(combined) > 8:
        warnings.append('Condition limit reached after preserving prior conditions; additional proposals omitted')
    conditions = list(combined.values())[:8]
    prior_rows = []
    active = {row['condition_id'] for row in conditions}
    for row in prior.get('observations', [])[:8]:
        previous = next((c for c in prior_conditions if row.get('condition_id') in {c['condition_id'], *c.get('condition_aliases', [])}), row)
        matches = _matches(previous, dispositions)
        supplied = matches[0] if matches and not _ambiguous(matches) else {}
        disposition = supplied.get('disposition')
        if disposition not in ('kept', 'overridden', 'retired'):
            disposition = 'kept' if previous.get('condition_id') in active else 'superseded'
        reason = supplied.get('reason') or candidate.get('disposition_reason')
        reason = reason[:1000] if isinstance(reason, str) and reason.strip() else 'reason not supplied'
        prior_rows.append({**row, 'disposition':disposition, 'disposition_reason':reason,
                           **({'alias_dispositions': [
                               {'condition_id':d.get('condition_id'), 'disposition':d.get('disposition'),
                                'reason':d.get('reason', '')[:1000] if isinstance(d.get('reason', ''), str) else 'reason not supplied'}
                               for d in matches]} if len(matches) > 1 or previous.get('condition_aliases') else {})})
    rationale = candidate.get('rationale')
    return {
        'schema_version':1, 'version_id':str(uuid5(NAMESPACE_URL, 'research-thesis:' + run_id)),
        'parent_version_id':prior.get('version_id'), 'run_id':run_id, 'as_of':asof,
        'authority':'candidate_advisory', 'canonical_rating':canonical_rating,
        'recommendation_disposition':'retained' if prior.get('canonical_rating') == canonical_rating else 'changed' if prior else 'initial',
        'rationale':rationale[:3000] if isinstance(rationale, str) else 'rationale not supplied',
        'assumptions':_texts(candidate.get('assumptions'), 8, 500),
        'assumptions_authority':'unverified research assumptions',
        'evidence_refs':_texts(candidate.get('evidence_refs'), 16, 200),
        'evidence_refs_authority':'unverified candidate references; not canonical evidence',
        'conditions':conditions, 'prior_conditions':prior_rows, 'warnings':warnings,
    }


def load_latest_thesis(config, ticker, known_at):
    """Read latest actually published thesis, regardless of pending outcomes.

    Missing legacy thesis stays None. Corrupt records/snapshots raise visibly;
    an older thesis is never silently resurrected after a newer publication.
    """
    from tradingagents.memory.publication import list_records, load_evidence
    if isinstance(known_at, datetime):
        cutoff = known_at
    elif isinstance(known_at, date) or len(str(known_at)) == 10:
        cutoff = datetime.combine(date.fromisoformat(str(known_at)), time.max, UTC)
    else:
        cutoff = datetime.fromisoformat(str(known_at).replace('Z', '+00:00'))
    if cutoff.tzinfo is None:
        raise ValueError('Thesis known_at requires timezone')
    eligible = []
    for record in list_records(config, ticker):
        stamp = record.get('published_at') or record.get('imported_at')
        if stamp and datetime.fromisoformat(stamp.replace('Z', '+00:00')) <= cutoff:
            eligible.append(record)
    if not eligible:
        return None
    record = max(eligible, key=lambda row: (datetime.fromisoformat((row.get('published_at') or row.get('imported_at')).replace('Z', '+00:00')), row['sequence']))
    thesis = load_evidence(config, record).get('thesis')
    if thesis is None:
        return None
    if not isinstance(thesis, dict) or thesis.get('schema_version') != 1 or not thesis.get('version_id'):
        raise ValueError('Invalid published thesis snapshot')
    return {**thesis, 'publication_id':record['decision_id'], 'published_at':record.get('published_at'),
            'authority': 'candidate_advisory' if record.get('published_at') else 'legacy_unknown'}


def _display(value, limit=300):
    from html import escape
    text = ' '.join(str(value if value is not None else 'unknown').split())
    truncated = len(text) > limit
    if truncated:
        text = text[:limit]
    # Flatten line breaks and escape markup so research prose cannot create
    # report headings, HTML, or additional table columns.
    text = escape(text, quote=True).replace('|', '&#124;')
    for marker in ('\\', '`', '*', '_', '[', ']'):
        text = text.replace(marker, '\\' + marker)
    return text + (' [truncated]' if truncated else '')


def condition_role_label(row):
    return {'supports_thesis': 'Supports current thesis',
            'reconsideration_trigger': 'Reconsideration trigger'}.get(row.get('thesis_role'), 'Unspecified thesis role')


def condition_status_label(row):
    """Separate observed predicate truth from the model's advisory thesis intent."""
    status = row.get('status', 'unknown')
    role = row.get('thesis_role', 'unspecified')
    if role == 'supports_thesis':
        return {'met': 'Support condition met', 'breached': 'Support condition breached'}.get(status, 'Support condition unknown')
    if role == 'reconsideration_trigger':
        return {'met': 'Reconsideration trigger met', 'breached': 'Reconsideration trigger not met'}.get(status, 'Reconsideration trigger unknown')
    return {'met': 'Comparison satisfied; thesis role unspecified',
            'breached': 'Comparison not satisfied; thesis role unspecified'}.get(status, 'Comparison unknown; thesis role unspecified')


def _condition_line(row):
    start = row.get('period_start')
    period = f"{start} to {row.get('period_end', 'unknown')}" if start else row.get('period_end', 'unknown')
    return (f"{_display(row.get('condition_id'), 100)}: {_display(row.get('metric'), 120)}; "
            f"period {_display(period, 50)}; {_display(row.get('comparator'), 10)} "
            f"{_display(row.get('threshold'), 100)} {_display(row.get('unit'), 40)}; "
            f"basis {_display(row.get('basis'), 80)}; expires {_display(row.get('expiry'), 20)}; "
            f"role {_display(condition_role_label(row), 40)} (unvalidated research intent)")


def _bounded_rows(value):
    rows = value if isinstance(value, list) else []
    return [row for row in rows[:8] if isinstance(row, dict)], max(0, len(rows) - 8)


def render_prior_thesis(prior) -> str:
    """Compact PM context with exact condition IDs for disposition references."""
    if not isinstance(prior, dict):
        return 'Prior advisory thesis unavailable; legacy prose has unknown authority.'
    lines = ['Prior thesis conditions are advisory, not binding; they cannot force a rating.',
             f"Version: {_display(prior.get('version_id'), 100)}; prior rating: {_display(prior.get('canonical_rating'), 40)}."]
    rows, omitted = _bounded_rows(prior.get('observations', prior.get('conditions', [])))
    for row in rows:
        lines.append(f"- {_condition_line(row)}; {_display(condition_status_label(row), 100)}; "
                     f"observed {_display(row.get('observed_value'), 100)} on {_display(row.get('observed_date'), 20)}. "
                     f"Observation: {_display(row.get('reason', 'observation unavailable'))}.")
    if not rows:
        lines.append('No structured prior conditions available.')
    if omitted:
        lines.append(f'{omitted} additional conditions omitted from this bounded display.')
    if prior.get('rationale'):
        lines.append('Prior rationale (unvalidated research, not verified evidence): ' + _display(prior['rationale']))
    return '\n'.join(lines)


def render_thesis(thesis) -> str:
    """Near-decision advisory display; no narrative becomes a verified target."""
    if not isinstance(thesis, dict):
        return 'Advisory thesis unavailable.'
    lines = ['Thesis continuity — advisory, not binding.',
             f"Version: {_display(thesis.get('version_id'), 100)}; parent: {_display(thesis.get('parent_version_id'), 100)}.",
             f"Canonical rating: {_display(thesis.get('canonical_rating'), 40)}; "
             f"recommendation {_display(thesis.get('recommendation_disposition'), 40)}.",
             'Rationale, assumptions, proposed conditions and departure reasons are unvalidated research, '
             'not verified evidence, authoritative price targets or position-sizing instructions.',
             'Rationale (unvalidated research): ' + _display(thesis.get('rationale', 'rationale not supplied'))]
    assumptions = thesis.get('assumptions')
    if isinstance(assumptions, list):
        lines.extend('- Assumption (unvalidated research): ' + _display(item) for item in assumptions[:8])
        if len(assumptions) > 8:
            lines.append(f'{len(assumptions)-8} additional assumptions omitted.')
    rows, omitted = _bounded_rows(thesis.get('conditions'))
    lines.append('Current proposed advisory conditions (unvalidated research):')
    lines.extend('- ' + _condition_line(row) for row in rows)
    if not rows:
        lines.append('No current structured conditions.')
    if omitted:
        lines.append(f'{omitted} additional conditions omitted from this bounded display.')
    rows, omitted = _bounded_rows(thesis.get('prior_conditions'))
    if rows:
        lines.append('Prior condition observations and dispositions:')
    for row in rows:
        lines.append(f"- {_condition_line(row)}; {_display(condition_status_label(row), 100)}; "
                     f"observed {_display(row.get('observed_value'), 100)} on {_display(row.get('observed_date'), 20)}; "
                     f"disposition {_display(row.get('disposition', 'unknown'), 30)}. "
                     f"Reason (unvalidated research): {_display(row.get('disposition_reason') or 'reason not supplied')}.")
    if omitted:
        lines.append(f'{omitted} additional prior conditions omitted from this bounded display.')
    warnings = thesis.get('warnings')
    if isinstance(warnings, list):
        lines.extend('Coverage: ' + _display(warning) for warning in warnings[:8])
    return '\n'.join(lines)


def legacy_thesis_context(entries, ticker, asof, *, historical=False) -> str:
    """Quote legacy memory without inventing its publication time or authority."""
    if historical:
        return ''
    cutoff = date.fromisoformat(asof)
    eligible = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('ticker') != ticker or entry.get('decision_id'):
            continue
        decision = entry.get('decision')
        if not isinstance(decision, str) or not decision.strip():
            continue
        try:
            labelled_date = date.fromisoformat(entry.get('date', ''))
        except (TypeError, ValueError):
            continue
        if labelled_date <= cutoff:
            eligible.append((labelled_date, entry))
    if not eligible:
        return ''
    labelled_date, entry = max(eligible, key=lambda pair: pair[0])
    quoted = _display(entry['decision'], 2300)
    if len(quoted) > 2500:
        quoted = quoted[:2480] + ' [truncated]'
    return (f'Legacy decision labelled {labelled_date}: publication time unknown; '
            'binding authority unestablished; unvalidated legacy research, not a hard rule.\n'
            f'> DECISION: {quoted}')
