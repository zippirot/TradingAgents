"""A bounded research decision card; model prose never supplies factual authority."""
from __future__ import annotations

import re
from datetime import date
from html import escape

from tradingagents.agents.rating import RATINGS_5_TIER, normalized_evidence_quality, run_rating
from tradingagents.agents.shared_valuation import prepare_shared_valuation
from tradingagents.agents.valuation import TargetResult, validate_target
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.memory.thesis import (
    condition_role_label,
    condition_status_label,
    observe_conditions,
)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _text(value, limit=240):
    if not isinstance(value, str):
        return ''
    cleaned = ' '.join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + '… [truncated]'


def _plain_horizon(value):
    """Accept a narrow complete value, never prose or language keyword filters."""
    if not isinstance(value, str) or len(value) > 120:
        return None
    value = ' '.join(value.split())
    if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        try:
            date.fromisoformat(value)
            return value
        except ValueError:
            return None
    duration = re.fullmatch(r'([1-9][0-9]{0,3})(?:\s*(?:[-–—]|to)\s*([1-9][0-9]{0,3}))?\s+(?:days?|weeks?|months?)', value, re.I)
    if duration and (duration[2] is None or int(duration[2]) >= int(duration[1])):
        return value
    return None


def _trader(value):
    if not isinstance(value, str):
        return 'unavailable'
    # Read only explicit proposal labels, never quoted targets or reasoning.
    labels = re.findall(r'(?im)^\s*(?:\*\*)?Action(?:\*\*)?\s*:\s*(?:\*\*)?(Buy|Hold|Sell)\b', value[:12000])
    labels += re.findall(r'(?im)^\s*FINAL TRANSACTION PROPOSAL:\s*(?:\*\*)?(Buy|Hold|Sell)\b', value[:12000])
    values = {label.title() for label in labels}
    return next(iter(values)) if len(values) == 1 else 'conflicting or unavailable'


def prepare_decision_context(state: dict) -> dict:
    """Recalculate availability; inventory research without copying raw narrative.

    There is no decision policy here: the Portfolio Manager remains canonical,
    and advisory conditions cannot enforce or replace its rating.
    """
    quality = normalized_evidence_quality(state)
    legacy = state.get('evidence_quality') is None
    rating = run_rating(state)
    if rating not in (*RATINGS_5_TIER, 'REVIEW'):
        rating = 'REVIEW'
    eligible = not legacy and quality.get('status') in {'sufficient', 'limited'} and rating != 'REVIEW'
    saved = _mapping(state.get('target_validation'))
    request = saved.get('request')
    target = TargetResult(status='unsupported', reasons=('Canonical evidence or supported valuation request unavailable.',))
    if eligible:
        try:
            package = EvidencePackage.model_validate(state.get('financial_evidence'))
            if str(package.as_of) != state.get('trade_date'):
                raise ValueError('Evidence date differs from analysis date')
            target = validate_target(request, package, grounded_outlooks(state))
        except (ValueError, TypeError):
            target = TargetResult(status='unsupported', reasons=('Canonical financial evidence unavailable.',))
    scenarios = _mapping(state.get('shared_valuation_scenarios'))
    replayed = prepare_shared_valuation(state, scenarios.get('requests', [])) if eligible else {'status': 'unavailable', 'rows': []}
    supported_scenarios = sum((_mapping(row.get('result')).get('status') == 'supported'
                               and _mapping(_mapping(row.get('result')).get('decision_use')).get('suitability') == 'conditional')
                              for row in replayed.get('rows', []) if isinstance(row, dict))
    if not eligible:
        basis, note = 'insufficient evidence', 'Current canonical evidence does not support a completed research conclusion.'
    elif target.status == 'supported' and target.decision_use.final_target_eligible:
        basis, note = 'valuation', 'Conditional valuation arithmetic is available; assumptions and the rating remain research judgments.'
    else:
        basis, note = 'risk assessment', 'The rating is a research risk opinion without a supported final valuation; it does not establish a demonstrated expected return.'
    originals = _mapping(state.get('unvalidated_outputs'))
    structured = _mapping(_mapping(originals.get('portfolio_manager')).get('structured'))
    if target.decision_date is not None:
        horizon = {'text': str(target.decision_date), 'authority': 'explicit conditional decision date; forecast period is separate'}
    elif plain := _plain_horizon(structured.get('time_horizon')):
        horizon = {'text': plain, 'authority': 'Portfolio Manager stated horizon; unvalidated model text'}
    elif structured.get('time_horizon'):
        horizon = {'text': 'not specified', 'authority': 'unstructured horizon retained in diagnostics; no horizon inferred'}
    else:
        horizon = {'text': 'not specified', 'authority': 'no horizon inferred from forecast periods'}
    checks = quality.get('checks', [])
    checks = checks if isinstance(checks, list) else []
    counts = {kind: sum(isinstance(c, dict) and c.get('status') == kind for c in checks)
              for kind in ('pass', 'fail', 'unavailable', 'not_applicable')}
    coverage = {'status': 'legacy/unvalidated' if legacy else quality.get('status', 'unavailable'),
                'scope': _text(quality.get('scope'), 120) or 'not specified', 'counts': counts,
                'limits': [_text(c.get('message')) for c in checks[:40] if isinstance(c, dict)
                           and c.get('status') in {'fail', 'unavailable'}][:3]}
    thesis = _mapping(state.get('thesis'))
    prior = _mapping(state.get('prior_thesis'))
    dispositions = thesis.get('prior_conditions', [])
    dispositions = dispositions if isinstance(dispositions, list) else []
    observations = observe_conditions(prior, state if eligible else {})
    condition_rows = []
    for observed in observations[:8]:
        matches = [d for d in dispositions[:8] if isinstance(d, dict) and d.get('condition_id') == observed['condition_id']]
        supplied = matches[0] if len(matches) == 1 else {}
        disposition = supplied.get('disposition')
        if disposition not in {'kept', 'overridden', 'retired', 'superseded'}:
            disposition = 'not supplied'
        condition_rows.append({'metric': _text(observed.get('metric'), 100),
                               'condition_id': observed['condition_id'], 'status': observed['status'],
                               'thesis_role': observed.get('thesis_role', 'unspecified'),
                               'status_label': condition_status_label(observed),
                               'disposition': disposition,
                               'reason': _text(supplied.get('disposition_reason')) or 'reason not supplied'})
    conditions = thesis.get('conditions', [])
    conditions = conditions if isinstance(conditions, list) else []
    changes = [_text(f"{condition_role_label(c)}: {c.get('metric', 'condition')} {c.get('comparator', '')} {c.get('threshold', '')} {c.get('unit', '')}; period {c.get('period_end', 'unspecified')}")
               for c in conditions[:3] if isinstance(c, dict)]
    excerpts = []
    assumptions = thesis.get('assumptions', [])
    if isinstance(assumptions, list):
        excerpts.extend({'role': 'Thesis assumption', 'diagnostic_reference': f'thesis.assumptions[{index}]'}
                        for index, text in enumerate(assumptions[:2]) if _text(text))
    debate_path = ('unvalidated_outputs.investment_debate_state' if originals.get('investment_debate_state')
                   else 'investment_debate_state')
    debate = _mapping(originals.get('investment_debate_state') or state.get('investment_debate_state'))
    for role, key in (('Bull argument', 'bull_history'), ('Bear argument', 'bear_history')):
        if _text(debate.get(key)):
            excerpts.append({'role': role, 'diagnostic_reference': f'{debate_path}.{key}'})
    trader = originals.get('trader_investment_plan', state.get('trader_investment_plan'))
    return {'status': 'legacy' if legacy else 'current', 'rating': rating, 'basis': basis, 'basis_note': note,
            'horizon': horizon, 'coverage': coverage,
            'target': {'status': target.status, 'decision_use': target.decision_use.model_dump(mode='json'),
                       'reasons': [_text(r) for r in (*target.reasons, *target.decision_use.reasons)[:3]]},
            'scenarios': {'status': replayed['status'], 'supported_count': supported_scenarios,
                          'diagnostic_count': len(replayed.get('rows', [])) - supported_scenarios},
            'trader_provisional': _trader(trader), 'conditions': condition_rows,
            'proposed_changes': changes, 'excerpts': excerpts[:4],
            'research_only': 'Advisory conditions do not enforce a rating. No validated stop, numerical allocation or broker instruction is published.'}


def _display(value):
    # Compact opaque hashes only in presentation; exact text stays in evidence.json.
    text = escape(re.sub(r"\b[0-9a-fA-F]{32,64}\b", "[source reference in evidence.json]", str(value)))
    return re.sub(r'([\\`*_\[\]()#!|])', r'\\\1', text)


def render_condition_summary(record: dict) -> str:
    """Compact advisory outcomes beside the rating, retaining uncertainty and reasons."""
    rows = record.get('conditions') or []
    lines = ['**Advisory conditions at a glance** (not automatic rating rules):']
    if not rows:
        lines.append('No prior structured observations; condition status is unknown.')
    for row in rows:
        lines.append(f"- {_display(condition_role_label(row))} — {_display(row['metric'])}: "
                     f"{_display(row.get('status_label') or condition_status_label(row))}; "
                     f"{_display(row['disposition'])}. Reason (unvalidated): {_display(row['reason'])}.")
    return '\n'.join(lines)


def render_decision_context(record: dict) -> str:
    """Render a freshly prepared card; all model text stays escaped and labeled."""
    title = 'Legacy reported rating' if record['status'] == 'legacy' else 'Canonical Portfolio Manager rating'
    coverage = record['coverage']
    lines = ['### Research decision card', '', f"**{title}**: {_display(record['rating'])}",
             render_condition_summary(record),
             f"**Basis**: {_display(record['basis'])}. {_display(record['basis_note'])}",
             f"**Horizon**: {_display(record['horizon']['text'])} — {_display(record['horizon']['authority'])}.",
             f"**Evidence coverage**: {_display(coverage['status'])}; {_display(coverage['scope'])}; " + ', '.join(f'{k}: {v}' for k,v in coverage['counts'].items()) + '.',
             f"**Valuation availability**: final calculation {_display(record['target']['status'])}; supported scenarios {record['scenarios']['supported_count']}; diagnostic scenarios {record['scenarios']['diagnostic_count']}.",
             f"**Trader provisional action**: {_display(record['trader_provisional'])}; this is not the canonical Portfolio Manager rating."]
    lines += ['Coverage limit: ' + _display(text) for text in coverage['limits']]
    lines += ['Target limitation: ' + _display(text) for text in record['target']['reasons']]
    lines += ['', '**Advisory condition disposition**:']
    if not record['conditions']:
        lines.append('No prior structured condition observations available; no binding rule inferred.')
    for row in record['conditions']:
        lines.append(f"- {_display(row['metric'])}: {_display(row.get('status_label') or condition_status_label(row))}; {_display(row['disposition'])}. Reason (unvalidated): {_display(row['reason'])}.")
    if record['proposed_changes']:
        lines += ['', '**Advisory conditions — unvalidated research proposals**:']
        lines += ['- ' + _display(text) for text in record['proposed_changes']]
    if record['excerpts']:
        # Even labeled quotations can reintroduce forbidden target/sizing prose
        # into the canonical decision. The card holds references, not raw text.
        roles = ', '.join(dict.fromkeys(_display(row['role']) for row in record['excerpts']))
        lines += ['', '**Unvalidated research inventory**: ' + roles + '.',
                  'See the saved unvalidated research appendix and evidence.json diagnostics for original arguments and assumptions. These materials are not verified facts or instructions; their presence does not resolve disagreement.']
    lines += ['', _display(record['research_only'])]
    return '\n'.join(lines)
