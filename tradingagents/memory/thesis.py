"""Bounded advisory thesis continuity, stored only in immutable publications.

Proposals and assumptions are model research, never verified evidence or rules.
Observation consumes canonical evidence; no function changes a recommendation.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from tradingagents.dataflows.financial_evidence import ADDITIVE_METRICS, EvidencePackage


class ThesisCondition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    kind: Literal['metric', 'price_level', 'event'] = 'metric'
    metric: str | None = Field(default=None, min_length=1, max_length=120)
    metric_definition: str | None = Field(default=None, min_length=1, max_length=500)
    period_start: date | None = None
    period_end: date | None = None
    comparator: Literal['>=', '>', '<=', '<', '=='] | None = None
    threshold: Decimal | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    basis: str | None = Field(default=None, min_length=1, max_length=80)
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    description: str | None = Field(default=None, min_length=1, max_length=500)
    confirming_evidence: str | None = Field(default=None, min_length=1, max_length=500)
    expiry: date
    rationale: str = Field(min_length=1, max_length=1000)
    thesis_role: Literal['supports_thesis', 'reconsideration_trigger', 'unspecified'] = Field(
        default='unspecified', description='Unvalidated research intent: supports_thesis means the result, if met, supports the rating given now; reconsideration_trigger means reconsider that rating if met; or unspecified. Under Underweight or Sell, a result that is good for the company is a reconsideration_trigger, and so is an event that could cut either way.')

    @model_validator(mode='after')
    def dates(self):
        if self.kind == 'metric':
            required = ('metric', 'metric_definition', 'period_end', 'comparator', 'threshold', 'unit', 'basis')
            if any(getattr(self, field) is None for field in required):
                raise ValueError('metric condition requires metric, definition, period, comparison, unit and basis')
            if any(getattr(self, field) is not None for field in ('currency', 'description', 'confirming_evidence')):
                raise ValueError('metric condition has nonmetric fields')
            if self.period_start and self.period_start > self.period_end:
                raise ValueError('reversed condition period')
            if self.expiry < self.period_end:
                raise ValueError('condition expires before its measurement period')
        elif self.kind == 'price_level':
            if self.comparator is None or self.threshold is None or not self.threshold.is_finite() or self.threshold <= 0 or self.currency is None:
                raise ValueError('price level requires positive threshold, comparator and quote currency')
            if any(getattr(self, field) is not None for field in ('metric', 'metric_definition', 'period_start', 'period_end', 'unit', 'basis', 'description', 'confirming_evidence')):
                raise ValueError('price level has incompatible metric or event fields')
        else:
            if not self.description or not self.description.strip() or not self.confirming_evidence or not self.confirming_evidence.strip():
                raise ValueError('event requires description and confirming evidence')
            if any(getattr(self, field) is not None for field in ('metric', 'metric_definition', 'period_start', 'period_end', 'comparator', 'threshold', 'unit', 'basis', 'currency')):
                raise ValueError('event cannot contain a threshold, comparison or metric fields')
        return self


def _row_data(condition):
    # Historical metric snapshots and their hashes use precisely this old shape.
    if condition.kind == 'metric':
        return condition.model_dump(mode='json', exclude={'kind', 'currency', 'description', 'confirming_evidence'})
    return condition.model_dump(mode='json', exclude_none=True)


# Only spelling/case/spacing aliases of existing canonical labels. This is not
# fuzzy matching: issuer-defined or adjusted scopes remain distinct.
_METRIC_LABELS = {" ".join(name.split()).casefold(): name for name in (
    *ADDITIVE_METRICS, 'Gross Margin', 'Diluted EPS', 'Total Assets', 'Current Assets',
    'Cash and Equivalents', 'Total Liabilities', 'Current Liabilities',
    'Stockholders Equity', 'Total Borrowings',
)}


def _package(value):
    try:
        return EvidencePackage.model_validate(value)
    except (ValidationError, ValueError, TypeError):
        return None


def _normalize_condition(condition, package=None):
    if condition.kind != 'metric':
        return condition, {}
    updates = {}
    for field in ('metric', 'metric_definition'):
        value = getattr(condition, field)
        canonical = _METRIC_LABELS.get(' '.join(value.split()).casefold())
        if canonical is not None and canonical != value:
            updates[field] = canonical
    if condition.unit.strip().casefold() in ('%', 'percent'):
        updates['unit'] = 'percent'
    # GAAP is jurisdiction-dependent. Only the existing validated SEC US-GAAP
    # package scope authorizes this alias; IFRS/adjusted bases never normalize.
    if (package is not None and package.scope == 'SEC US-GAAP statements'
            and condition.basis.strip().casefold() == 'gaap'):
        updates['basis'] = 'US-GAAP'
    updates = {k:v for k,v in updates.items() if getattr(condition,k) != v}
    return condition.model_copy(update=updates), {k:getattr(condition,k) for k in updates}


def _exact_threshold(threshold):
    # Tuple normalization is exact even beyond Decimal's default context
    # precision (no normalize()).
    sign, digits, exponent = threshold.as_tuple()
    digits = list(digits)
    if not any(digits):
        return [0, [0], 0]
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    return [sign, digits, exponent]


def _id(condition):
    # Measurement identity excludes explanatory prose.
    payload = {k:v for k,v in _row_data(condition).items() if k not in {'rationale', 'thesis_role'}}
    if condition.threshold is None:
        return 'condition-' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    payload['threshold'] = _exact_threshold(condition.threshold)
    return 'condition-' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]


def _content_key(row):
    """What a condition tests, ignoring its ID-bearing definition text and expiry."""
    item = _condition(row)
    threshold = None if item.threshold is None else repr(_exact_threshold(item.threshold))
    if item.kind == 'metric':
        return ('metric', item.metric, item.period_start, item.period_end, item.comparator, threshold, item.unit, item.basis)
    if item.kind == 'price_level':
        return ('price_level', item.comparator, threshold, item.currency)
    return ('event', _event_wording(item.description))


def _event_wording(description):
    """One event's wording, with only known-safe rewrites. Anything else stays a separate row."""
    text = ' '.join(description.casefold().replace('’', "'").split()).rstrip('.')
    text = re.sub(r'(?<=[^\W\d_])-(?=[^\W\d_])', ' ', text).replace('capacity financing', 'capacity funding')
    return re.sub(r'^disclosure of how (.+) (?:was|were) settled or refinanced$',
                  r'disclosure of settlement or refinancing of \1', text)


def _condition(row):
    return ThesisCondition.model_validate({k:v for k,v in row.items()
                                          if k not in {'condition_id', 'condition_aliases', 'original_labels'}})


def _valid_id(value):
    return (isinstance(value, str) and len(value) == 34 and value.startswith('condition-')
            and all(c in '0123456789abcdef' for c in value[10:]))


def _conditions(values, *, preserve_ids=False, package=None, quote_currency=None):
    accepted, warnings, by_measurement = [], [], {}
    if not isinstance(values, (list, tuple)):
        return [], ['Invalid advisory conditions: expected a list']
    if not preserve_ids and len(values) > 8:
        warnings.append(f'{len(values) - 8} additional conditions stated but not retained: new proposal limit is eight')
    # The proposal bound does not truncate conditions already retained on disk.
    considered = values if preserve_ids else values[:8]
    for index, item in enumerate(considered):
        try:
            payload = dict(item)
            # A completed close has one currency, the instrument's. Leaving it out is not a reason to lose the level.
            if (not preserve_ids and quote_currency and payload.get('kind') == 'price_level'
                    and payload.get('currency') is None):
                payload['currency'] = quote_currency
                warnings.append(f'Condition at index {index}: quote currency was not stated; the validated quote '
                                f'currency {quote_currency} was used.')
            # An event can cut either way, and a look at it either way is what a reconsideration trigger asks for.
            if (not preserve_ids and payload.get('kind') == 'event'
                    and payload.get('thesis_role') in (None, 'unspecified')):
                payload['thesis_role'] = 'reconsideration_trigger'
                warnings.append('Role check: no role was given for the event '
                                f'"{_prompt_display(payload.get("description"), 80)}"; it is filed as a '
                                'reconsideration trigger, since an event that can cut either way prompts a fresh look.')
            condition, originals = _normalize_condition(_condition(payload), package)
            if not preserve_ids and condition.thesis_role == 'unspecified':
                name = condition.metric or condition.description or f'{condition.comparator} {condition.threshold} {condition.currency}'
                raise ValueError(f'{name[:120]} needs thesis_role supports_thesis or reconsideration_trigger')
            if condition.kind == 'price_level' and not preserve_ids and condition.currency != quote_currency:
                raise ValueError('price level currency does not match a validated instrument quote currency')
            saved_originals = payload.get('original_labels', {}) if preserve_ids else {}
            if isinstance(saved_originals, dict):
                originals = {**{k:v for k,v in saved_originals.items()
                              if k in ('metric', 'metric_definition', 'unit', 'basis')
                              and isinstance(v, str) and len(v) <= 500}, **originals}
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
                row = {**_row_data(condition), 'condition_id':identifier}
                if originals:
                    row['original_labels'] = originals
                by_measurement[key] = row
                accepted.append(row)
            aliases = [v for v in aliases if v != row['condition_id']]
            if aliases:
                row['condition_aliases'] = aliases[:8]
                warnings.append(f'Condition {row["condition_id"]} aliases: ' + ', '.join(aliases[:8]))
        except (ValidationError, ValueError, TypeError) as exc:
            reason = (exc.errors()[0]['msg'] if isinstance(exc, ValidationError) else str(exc))[:300]
            warnings.append(f'Condition at index {index} stated but not retained: {reason}')
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
    package = _package(state.get('financial_evidence'))
    rows, _ = _conditions((prior or {}).get('conditions', []), preserve_ids=True, package=package)
    extraction = state.get('filing_fact_extraction')
    precision = extraction.get('rounding_quantum_by_fact', {}) if isinstance(extraction, dict) else {}
    precision = precision if isinstance(precision, dict) else {}
    observations = []
    for row in rows:
        condition = _condition(row)
        observation = {**row, 'status':'unobserved' if condition.kind != 'metric' else 'unknown',
                       'reason':'Compatible canonical evidence unavailable',
                       'observed_value':None, 'observed_date':None, 'fact_ids':[], 'source_ids':[]}
        observations.append(observation)
        if condition.kind == 'event':
            observation['reason'] = 'Open question; confirming evidence not automatically matched'
            continue
        if condition.kind == 'price_level':
            observation['reason'] = 'Dated compatible completed close unavailable'
            try:
                from tradingagents.dataflows.vendors.yahoo.price_observation import (
                    validate_price_observation,
                )
                ticker = state.get('company_of_interest') or state.get('ticker')
                asof = state.get('trade_date') or (str(package.as_of) if package else None)
                quote = validate_price_observation(state.get('price_observation'), ticker, asof)
                if quote['currency'] != condition.currency or quote['session_status'] != 'completed':
                    continue
                if condition.expiry < date.fromisoformat(str(asof)):
                    observation['reason'] = 'Condition expired; no current compliance conclusion'
                    continue
                value = Decimal(quote['close'])
                met = {'>=': value >= condition.threshold, '>': value > condition.threshold,
                       '<=': value <= condition.threshold, '<': value < condition.threshold,
                       '==': value == condition.threshold}[condition.comparator]
                observation.update(status='met' if met else 'breached', observed_value=str(value),
                                   observed_date=quote['session_date'],
                                   reason='Validated completed close satisfies advisory condition' if met else
                                          'Validated completed close does not satisfy advisory condition')
            except (ValueError, TypeError, KeyError):
                pass
            continue
        analysis_date = package.as_of if package else None
        if analysis_date is None and state.get('trade_date'):
            with suppress(TypeError, ValueError):
                analysis_date = date.fromisoformat(str(state['trade_date']))
        if analysis_date is not None and condition.period_end > analysis_date:
            observation['reason'] = 'Period not yet reported; measurement period ends after analysis date'
            continue
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


def prepare_thesis(candidate, prior, canonical_rating, asof, run_id, *, financial_evidence=None,
                   price_observation=None, ticker=None) -> dict:
    """Prepare an idempotent JSON proposal; publication supplies its known-at time."""
    UUID(run_id)
    date.fromisoformat(asof)
    candidate = candidate if isinstance(candidate, dict) else {}
    prior = prior if isinstance(prior, dict) else {}
    package = _package(financial_evidence)
    quote_currency = None
    if price_observation is not None and ticker:
        try:
            from tradingagents.dataflows.vendors.yahoo.price_observation import (
                validate_price_observation,
            )
            quote_currency = validate_price_observation(price_observation, ticker, asof)['currency']
        except (ValueError, TypeError, KeyError):
            pass
    prior_conditions, warnings = _conditions(prior.get('conditions', []), preserve_ids=True, package=package)
    proposed = candidate.get('conditions')
    if proposed is None:
        conditions = prior_conditions
    else:
        conditions, proposal_warnings = _conditions(proposed, package=package, quote_currency=quote_currency)
        warnings.extend(proposal_warnings)
        warnings.extend('Role check: ' + line for line in role_conflicts(canonical_rating, conditions))
        if proposal_warnings and not conditions and proposed != []:
            conditions = prior_conditions
            warnings.append('Malformed optional conditions; prior advisory conditions retained')
    previous_by_key = {_id(_condition(row)): row for row in prior_conditions}
    for row in conditions:
        previous = previous_by_key.get(_id(_condition(row)))
        if previous is not None:
            row['condition_id'] = previous['condition_id']
            if previous.get('condition_aliases'):
                row['condition_aliases'] = list(previous['condition_aliases'])
    dispositions = candidate.get('dispositions', [])
    dispositions = dispositions if isinstance(dispositions, list) else []
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
    # Bound new proposals independently; explicit keeps must not consume their slots.
    combined = {row['condition_id']: row for row in preserved}
    kept_by_content = {_content_key(row): row['condition_id'] for row in preserved}
    for row in conditions:
        if row['condition_id'] not in retired:
            kept_id = kept_by_content.get(_content_key(row))
            if kept_id is not None and kept_id != row['condition_id']:
                kept = combined[kept_id]
                aliases = list(dict.fromkeys([*kept.get('condition_aliases', []), row['condition_id']]))[:8]
                combined[kept_id] = {**kept, 'condition_aliases': aliases, 'thesis_role': row['thesis_role']}
                if kept.get('thesis_role', 'unspecified') != row['thesis_role']:
                    warnings.append(f"Condition {kept_id} role set by this version’s proposal; prior observations retain their original interpretation.")
            elif row['condition_id'] in combined:
                prior_role = combined[row['condition_id']].get('thesis_role', 'unspecified')
                combined[row['condition_id']] = {**combined[row['condition_id']], 'thesis_role': row['thesis_role']}
                if prior_role != row['thesis_role']:
                    warnings.append(f"Condition {row['condition_id']} role set by this version’s proposal; prior observations retain their original interpretation.")
            else:
                combined.setdefault(row['condition_id'], row)
    conditions = list(combined.values())
    prior_rows = []
    active = {row['condition_id'] for row in conditions}
    for row in prior.get('observations', []):
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
        from tradingagents.dataflows.date_window import resolve_analysis_cutoff
        cutoff = datetime.fromisoformat(resolve_analysis_cutoff(
            str(known_at), config.get('analysis_timezone', 'America/Denver'))['cutoff_utc'])
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
    text = ' '.join(str(value if value is not None else 'unknown').split())
    truncated = len(text) > limit
    if truncated:
        text = text[:limit]
    # Flatten line breaks and escape markdown so research prose cannot create
    # report headings or additional table columns. HTML export escapes once.
    for marker in ('\\', '`', '*', '_', '[', ']'):
        text = text.replace(marker, '\\' + marker)
    text = text.replace('|', r'\|')
    return text + (' [truncated]' if truncated else '')


def _prompt_display(value, limit=300):
    text = ' '.join(str(value if value is not None else 'unknown').split())
    return text[:limit] + (' [truncated]' if len(text) > limit else '')


# Measures where a higher figure is plainly good news for the company. Direction is read for these only.
_GOOD_WHEN_HIGHER = frozenset(name.casefold() for name in (
    'Revenue', 'Gross Profit', 'Gross Margin', 'Operating Income', 'Operating Margin', 'Net Income', 'Net Margin',
    'Operating Cash Flow', 'Remaining Performance Obligations', 'Diluted EPS', 'Basic EPS'))


def role_conflicts(rating, conditions) -> list[str]:
    """New conditions filed as supporting a rating that their own direction speaks against. Roles are not changed."""
    bearish, bullish = rating in ('Sell', 'Underweight'), rating in ('Buy', 'Overweight')
    found = []
    for row in conditions if isinstance(conditions, (list, tuple)) else ():
        if not isinstance(row, dict) or row.get('thesis_role') != 'supports_thesis' or row.get('kind', 'metric') != 'metric':
            continue
        metric, comparator = row.get('metric'), row.get('comparator')
        if not isinstance(metric, str) or ' '.join(metric.split()).casefold() not in _GOOD_WHEN_HIGHER:
            continue
        higher = comparator in ('>=', '>')
        if (bearish and higher) or (bullish and comparator in ('<=', '<')):
            stated = ' '.join(str(row.get(key)) for key in ('comparator', 'threshold', 'unit') if row.get(key) is not None)
            found.append(f"{_prompt_display(metric, 120)} {stated} is filed as supporting the {rating} rating, but a "
                         f"{'higher' if higher else 'lower'} {_prompt_display(metric, 120)} is "
                         f"{'good' if higher else 'bad'} news for the company.")
    return found


def role_feedback(rating, conditions) -> str:
    """What to send back to the manager once, or '' when the roles can stand."""
    found = role_conflicts(rating, conditions)
    if not found:
        return ''
    return ('Condition roles: ' + ' '.join(found) + ' supports_thesis means the result supports the rating you give '
            'now; a result that would argue for a different rating is a reconsideration_trigger. Resubmit the complete '
            'decision with each of these relabelled or its comparison reversed, or say in its rationale why that '
            'result supports the rating.')


def visible_warnings(warnings) -> list[str]:
    """The proposal warnings a reader of the decision card needs: a lost condition or a questioned role."""
    return [str(w) for w in warnings or [] if isinstance(w, str)
            and ('stated but not retained' in w or w.startswith('Role check: '))]


def condition_role_label(row):
    return {'supports_thesis': 'Supports the current rating',
            'reconsideration_trigger': 'Reconsideration trigger'}.get(row.get('thesis_role'), 'Unspecified thesis role')


def condition_status_label(row):
    """Separate observed predicate truth from the model's advisory thesis intent."""
    status = row.get('status', 'unknown')
    if status == 'unobserved':
        return 'Unobserved; advisory question remains open'
    role = row.get('thesis_role', 'unspecified')
    if role == 'supports_thesis':
        return {'met': 'Support condition met', 'breached': 'Support condition breached'}.get(status, 'Support condition unknown')
    if role == 'reconsideration_trigger':
        return {'met': 'Reconsideration trigger met', 'breached': 'Reconsideration trigger not met'}.get(status, 'Reconsideration trigger unknown')
    return {'met': 'Comparison satisfied; thesis role unspecified',
            'breached': 'Comparison not satisfied; thesis role unspecified'}.get(status, 'Comparison unknown; thesis role unspecified')


def _condition_line(row, display=_display):
    if row.get('kind') == 'event':
        return (f"{display(row.get('condition_id'), 100)}: event {display(row.get('description'), 500)}; "
                f"confirming evidence {display(row.get('confirming_evidence'), 500)}; "
                f"expires {display(row.get('expiry'), 20)}; role {display(condition_role_label(row), 40)} "
                '(unvalidated research intent)')
    if row.get('kind') == 'price_level':
        return (f"{display(row.get('condition_id'), 100)}: completed close "
                f"{display(row.get('comparator'), 10)} {display(row.get('threshold'), 100)} "
                f"{display(row.get('currency'), 10)}; expires {display(row.get('expiry'), 20)}; "
                f"role {display(condition_role_label(row), 40)} (unvalidated research intent)")
    start = row.get('period_start')
    period = f"{start} to {row.get('period_end', 'unknown')}" if start else row.get('period_end', 'unknown')
    return (f"{display(row.get('condition_id'), 100)}: {display(row.get('metric'), 120)}; "
            f"period {display(period, 50)}; {display(row.get('comparator'), 10)} "
            f"{display(row.get('threshold'), 100)} {display(row.get('unit'), 40)}; "
            f"basis {display(row.get('basis'), 80)}; expires {display(row.get('expiry'), 20)}; "
            f"role {display(condition_role_label(row), 40)} (unvalidated research intent)")


def _condition_rows(value):
    rows = value if isinstance(value, list) else []
    return [row for row in rows if isinstance(row, dict)]


def render_prior_thesis(prior) -> str:
    """Compact PM context with exact condition IDs for disposition references."""
    if not isinstance(prior, dict):
        return 'Prior advisory thesis unavailable; legacy prose has unknown authority.'
    lines = ['Prior thesis conditions are advisory, not binding; they cannot force a rating.',
             f"Version: {_prompt_display(prior.get('version_id'), 100)}; prior rating: {_prompt_display(prior.get('canonical_rating'), 40)}."]
    rows = _condition_rows(prior.get('observations', prior.get('conditions', [])))
    for row in rows:
        lines.append(f"- {_condition_line(row, _prompt_display)}; {_prompt_display(condition_status_label(row), 100)}; "
                     f"observed {_prompt_display(row.get('observed_value'), 100)} on {_prompt_display(row.get('observed_date'), 20)}. "
                     f"Observation: {_prompt_display(row.get('reason', 'observation unavailable'))}.")
    if not rows:
        lines.append('No structured prior conditions available.')
    if prior.get('rationale'):
        lines.append('Prior rationale (unvalidated research, not verified evidence): ' + _prompt_display(prior['rationale'], 1000))
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
             'Rationale (unvalidated research): ' + _display(thesis.get('rationale', 'rationale not supplied'), 1000)]
    assumptions = thesis.get('assumptions')
    if isinstance(assumptions, list):
        lines.extend('- Assumption (unvalidated research): ' + _display(item) for item in assumptions[:8])
        if len(assumptions) > 8:
            lines.append(f'{len(assumptions)-8} additional assumptions omitted.')
    rows = _condition_rows(thesis.get('conditions'))
    lines.append('Current proposed advisory conditions (unvalidated research):')
    lines.extend('- ' + _condition_line(row) for row in rows)
    if not rows:
        lines.append('No current structured conditions.')
    rows = _condition_rows(thesis.get('prior_conditions'))
    if rows:
        lines.append('Prior condition observations and dispositions:')
    for row in rows:
        lines.append(f"- {_condition_line(row)}; {_display(condition_status_label(row), 100)}; "
                     f"observed {_display(row.get('observed_value'), 100)} on {_display(row.get('observed_date'), 20)}; "
                     f"disposition {_display(row.get('disposition', 'unknown'), 30)}. "
                     f"Reason (unvalidated research): {_display(row.get('disposition_reason') or 'reason not supplied')}.")
    warnings = thesis.get('warnings')
    if isinstance(warnings, list):
        visible = [warning for warning in warnings if isinstance(warning, str) and 'stated but not retained' in warning]
        visible.extend(warning for warning in warnings if warning not in visible)
        lines.extend('Coverage: ' + _display(warning) for warning in visible[:8])
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
        # This exact canonical projection stores fact context while keeping the
        # model narrative in diagnostics. It supplies no legacy thesis to quote.
        if (decision.startswith("**Rating**: ")
                and "**Executive Summary**: Model recommendation; financial evidence and valuation coverage are shown below." in decision
                and "**Investment Thesis — canonical evidence**:" in decision
                and decision.rstrip().endswith("Original model narrative is retained separately in evidence.json diagnostics.")
                and "Thesis continuity — advisory, not binding." not in decision):
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
    quoted = _prompt_display(entry['decision'], 2300)
    if len(quoted) > 2500:
        quoted = quoted[:2480] + ' [truncated]'
    return (f'Legacy decision labelled {labelled_date}: publication time unknown; '
            'binding authority unestablished; unvalidated legacy research, not a hard rule.\n'
            f'> DECISION: {quoted}')
