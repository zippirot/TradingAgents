"""A bounded research decision card; model prose never supplies factual authority."""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from decimal import Decimal

from tradingagents.agents.case_reference import action_reading, research_rating
from tradingagents.agents.issuer_events import financing_sensitivities
from tradingagents.agents.rating import (
    RATINGS_5_TIER,
    normalized_evidence_quality,
    run_rating,
)
from tradingagents.agents.scenario_decision import (
    LABEL as SCENARIO_LABEL,
    render as render_scenario_decision,
    summarize as summarize_scenarios,
)
from tradingagents.agents.shared_valuation import annotate_disputed_cases, replay_cases
from tradingagents.agents.valuation import TargetResult, validate_target
from tradingagents.agents.valuation_cases import (
    MULTIPLE_CONSTRUCTION,
    CaseSelection,
    obligation_bases,
)
from tradingagents.agents.valuation_comparison import display_number, display_value
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.memory.thesis import (
    condition_role_label,
    condition_status_label,
    observe_conditions,
    visible_warnings,
)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _text(value, limit=240):
    if not isinstance(value, str):
        return ''
    cleaned = ' '.join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + '… [truncated]'


def _condition_metric(row):
    if row.get('kind') == 'price_level':
        return f"Completed close ({row.get('currency') or row.get('quote_currency') or 'currency unknown'})"
    return row.get('metric') or row.get('description') or 'Unnamed measurement'


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


DECISION_HORIZON_CONTRACT = 'decision_horizon_v1'


def decision_horizon(state: dict) -> dict:
    """Only an explicit PM field establishes the fresh decision horizon."""
    pm = _mapping(_mapping(state.get('unvalidated_outputs')).get('portfolio_manager'))
    structured = _mapping(pm.get('structured'))
    fresh = pm.get('contract_version') == DECISION_HORIZON_CONTRACT
    plain = _plain_horizon(structured.get('time_horizon'))
    if fresh and not structured:
        fallback = pm.get('fallback')
        labels = re.findall(r'(?im)^\s*(?:\*\*)?Time Horizon(?:\*\*)?:\s*([^\r\n]+)', fallback[:12000] if isinstance(fallback, str) else '')
        if len(labels) == 1:
            plain = _plain_horizon(labels[0])
    if plain:
        months = pm.get('configured_horizon_months')
        if fresh and type(months) is int and months > 0:
            default = f'{months} months'
            reason = _text(structured.get('horizon_reason'), 1200)
            if not structured:
                reasons = re.findall(r'(?im)^\s*(?:\*\*)?Horizon Reason(?:\*\*)?:\s*([^\r\n]+)', pm.get('fallback', '')[:12000])
                reason = _text(reasons[0], 1200) if len(reasons) == 1 else ''
            same = re.fullmatch(rf'{months}\s+months?', plain, re.I) is not None
            if not same and reason:
                return {'text': f'{plain} (PM override: {reason})', 'value': plain, 'status': 'explicit',
                        'authority': 'Portfolio Manager horizon override; unvalidated model reasoning'}
            return {'text': f'{default} (configured default)', 'value': default, 'status': 'explicit',
                    'authority': 'configured decision horizon' if same else 'PM supplied a different horizon without a reason; configured default applied'}
        return {'text': plain, 'status': 'explicit', 'authority': 'Portfolio Manager stated horizon; unvalidated model text'}
    if fresh:
        return {'text': 'incomplete — explicit decision horizon required', 'status': 'incomplete',
                'authority': 'no horizon inferred from forecast periods or valuation dates'}
    return {'text': 'unknown (legacy decision)', 'status': 'legacy_unknown',
            'authority': 'unstructured horizon retained in diagnostics; no horizon inferred' if structured.get('time_horizon') else 'no horizon inferred from forecast periods'}


def horizon_incomplete(state: dict) -> bool:
    return decision_horizon(state)['status'] == 'incomplete'


def _within_horizon(start, day, horizon):
    if day <= start:
        return False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", horizon):
        return day <= date.fromisoformat(horizon)
    values = [int(n) for n in re.findall(r"\d+", horizon)]
    if not values:
        return False

    def end(n):
        if "month" in horizon.lower():
            year, month = divmod(start.year * 12 + start.month - 1 + n, 12)
            return date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))
        return start + timedelta(days=n * (7 if "week" in horizon.lower() else 1))

    return (len(values) == 1 or day >= end(values[0])) and day <= end(values[-1])


def final_request(state):
    pm = _mapping(_mapping(state.get("unvalidated_outputs")).get("portfolio_manager"))
    cached = _mapping(state.get("target_validation")).get("request")
    if pm.get("case_contract") or _mapping(cached).get("method") == "case" or _mapping(pm.get("valuation_request")).get("method") == "case":
        return pm.get("valuation_request")
    return cached


def validate_final_case(state, request, cases=None):
    """Resolve final identity against freshly replayed active inputs."""
    try:
        package = EvidencePackage.model_validate(state.get("financial_evidence"))
        cutoff = state.get("trade_date")
        case_contract = _mapping(_mapping(state.get("unvalidated_outputs")).get("portfolio_manager")).get("case_contract")
        if (cutoff is not None or case_contract or _mapping(request).get("method") == "case") and str(package.as_of) != cutoff:
            raise ValueError("Financial evidence date differs from analysis date")
        if horizon_incomplete(state):
            raise ValueError("Explicit decision horizon missing or invalid; decision incomplete, valuation unavailable.")
        if not isinstance(request, dict) or request.get("method") != "case":
            legacy = validate_target(request, package, grounded_outlooks(state))
            if (legacy.status == "supported" and legacy.decision_use.final_target_eligible and
                    (state.get("unvalidated_outputs") or {}).get("portfolio_manager", {}).get("case_contract")):
                raise ValueError("No active valuation case selected by identity and version")
            return legacy
        if not request.get("rerating_assumption"):
            raise ValueError("Explicit rerating assumption or 'none' required")
        selection = CaseSelection.model_validate(request)
        if decision_horizon(state)["status"] != "explicit":
            raise ValueError("Explicit decision horizon required for case adoption")
        if cases is None:
            cases = replay_cases(state)
        row = next((r for r in cases["rows"] if (r["case_id"], r["version"]) ==
                    (selection.case_id, selection.version)), None)
        if not row or row["diagnostic_only"]:
            raise ValueError("Unknown, stale or ineligible case ID/version")
        result = TargetResult.model_validate(row["result"])
        if not result.decision_use.final_target_eligible:
            raise ValueError("Selected case does not meet final suitability")
        assumption = selection.rerating_assumption.strip()
        if not assumption:
            raise ValueError("Blank rerating assumption")
        if assumption.casefold() == "none":
            if selection.decision_date:
                raise ValueError("Decision date requires a substantive rerating assumption")
            return result.model_copy(update={"decision_date": None, "rerating_assumption": None})
        if not selection.decision_date:
            raise ValueError("Rerating assumption requires a decision date")
        horizon = decision_horizon(state)
        if not _within_horizon(package.as_of, selection.decision_date, horizon.get("value", horizon["text"])):
            raise ValueError("Decision date outside the stated decision horizon")
        if result.multiple_assumption_date is None:
            raise ValueError("Dated link requires a dated multiple")
        comparison = row.get("comparison") or {}
        if comparison.get("status") != "available":
            raise ValueError("Dated link needs a comparable completed close: " + str(comparison.get("reason") or "unavailable"))
        capital = row["request"].get("capital")
        if capital and date.fromisoformat(capital["valuation_date"]) > selection.decision_date:
            used = [capital["closing_shares"]]
            if row["request"]["multiple_basis"] != "equity":
                obligations = capital["obligations"]
                categories = obligation_bases(obligations)[row["request"]["multiple_basis"]]
                used.extend([capital["cash"], *(obligations[k] for k in categories)])
            if any(v["assumption"] != "unchanged_from_snapshot" for v in used):
                raise ValueError("Projected capital occurs after the decision date")
        return result.model_copy(update={"decision_date": selection.decision_date, "rerating_assumption": assumption})
    except (ValueError, TypeError, OverflowError) as exc:
        return TargetResult(status="unsupported", reasons=(str(exc).split("\n")[0],))


def _case_groups(rows, scenario=None):
    """Displayed case inventory and its range.

    When the Portfolio Manager's answer on the priced cases is usable, a case it rejected stays listed but
    leaves the range; otherwise every priced case, flagged or not, is in the range.
    """
    rejected = {(case["case_id"], case["version"]) for case in _mapping(scenario).get("cases", ())
                if _mapping(scenario).get("status") == "addressed" and case.get("disposition") == "rejected"}
    groups = {}
    for row in rows:
        result, request = row["result"], row["request"]
        if row["diagnostic_only"] or not result["decision_use"]["final_target_eligible"]:
            continue
        if request["method"] == "revenue_case":
            clock = MULTIPLE_CONSTRUCTION
            basis = request["multiple_basis"] + " / revenue (" + clock + ")"
            share_basis = "closing common shares"
            share_ref = tuple(request["capital"]["closing_shares"]["fact_ids"])
            # The analyst's period word no longer changes the printed label, but still keeps ranges apart.
            period_word = request["multiple_period"]
        else:
            basis, share_basis = "forward P/E", request["eps_basis"] + " EPS"
            share_ref = (request["eps_fact_id"],)
            period_word = ""
        key = (result["valuation_period_start"], result["valuation_period_end"], basis, share_basis,
               share_ref, result["accounting_basis"], result["unit"], period_word)
        group = groups.setdefault(key, {"period_start": key[0], "period_end": key[1], "multiple_basis": basis,
            "share_basis": share_basis, "accounting_basis": key[5], "unit": key[6], "cases": []})
        capital = request.get("capital") or {}
        fixed = [k for k,v in {**capital.get("obligations", {}),
                 **{k:capital[k] for k in ("closing_shares","cash") if k in capital}}.items()
                 if v["assumption"] == "unchanged_from_snapshot"]
        group["cases"].append({"case_id": row["case_id"], "version": row["version"], "name": row["name"],
                               **({'disputed_by': row['disputed_by']} if row.get('disputed_by') else {}),
                               **({'dispute_note': row['dispute_note']} if row.get('dispute_note') else {}),
                               **({'manager_rejected': True} if (row["case_id"], row["version"]) in rejected else {}),
                               "value": result["target"], "unchanged_from_snapshot": fixed})
        comparison = row.get("comparison") or {}
        if comparison.get("status") == "available":
            group["completed_close"] = {k: comparison["price"][k] for k in ("close", "session_date", "currency")}
    for group in groups.values():
        # Flagged cases stay in the range: one surviving case shown alone would misstate the spread.
        values = [Decimal(c["value"]) for c in group["cases"] if not c.get("manager_rejected")]
        group.update(low=str(min(values)) if values else None, high=str(max(values)) if values else None)
        if "completed_close" in group and values:
            close = Decimal(group["completed_close"]["close"])
            group["close_position"] = "below" if close < min(values) else "above" if close > max(values) else "at" if len(values) == 1 else "within"
    return list(groups.values())


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
    request = final_request(state)
    target = TargetResult(status='unsupported', reasons=('Canonical evidence or supported valuation request unavailable.',))
    replayed = replay_cases(state) if eligible else {"status": "unavailable", "rows": []}
    replayed = annotate_disputed_cases(state, replayed)
    if eligible:
        target = validate_final_case(state, request, replayed)
    selected = isinstance(request, dict) and request.get("method") == "case" and target.status == "supported"
    adopted_disputes = (next((list(row.get('disputed_by') or []) for row in replayed.get('rows', [])
                              if (row.get('case_id'), row.get('version')) ==
                              (request.get('case_id'), request.get('version'))), []) if selected else [])
    supported_scenarios = sum(not row.get("diagnostic_only") and (_mapping(row.get('result')).get('status') == 'supported'
                               and _mapping(_mapping(row.get('result')).get('decision_use')).get('suitability') == 'conditional')
                              for row in replayed.get('rows', []) if isinstance(row, dict))
    scenario = summarize_scenarios(state, replayed) if eligible else {'status': 'not_applicable', 'cases': [], 'problems': []}
    if not eligible:
        basis, note = 'insufficient evidence', 'Current canonical evidence does not support a completed research conclusion.'
    elif selected and target.decision_use.final_target_eligible:
        basis, note = 'valuation', 'Conditional valuation arithmetic is available; assumptions and the rating remain research judgments.'
    elif scenario.get('range'):
        basis, note = 'conditional scenarios', 'The rating is checked against the scenario cases the Portfolio Manager accepted; they are assumptions with subjective weights, not a price target or a demonstrated expected return.'
    else:
        basis, note = 'risk assessment', 'The rating is a research risk opinion without a supported final valuation; it does not establish a demonstrated expected return.'
    originals = _mapping(state.get('unvalidated_outputs'))
    horizon = decision_horizon(state)
    if (not selected and horizon['status'] != 'incomplete' and target.decision_date is not None
            and _mapping(originals.get('portfolio_manager')).get('contract_version') != DECISION_HORIZON_CONTRACT):
        horizon = {'text': str(target.decision_date), 'status': 'explicit', 'authority': 'explicit conditional decision date; forecast period is separate'}
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
    for observed in observations:
        matches = [d for d in dispositions if isinstance(d, dict) and d.get('condition_id') == observed['condition_id']]
        supplied = matches[0] if len(matches) == 1 else {}
        disposition = supplied.get('disposition')
        if disposition not in {'kept', 'overridden', 'retired', 'superseded'}:
            disposition = 'not supplied'
        condition_rows.append({'metric': _text(_condition_metric(observed), 100),
                               **{key: observed.get(key) for key in ('kind', 'comparator', 'threshold', 'unit', 'quote_currency')},
                               'condition_id': observed['condition_id'], 'status': observed['status'],
                               'thesis_role': observed.get('thesis_role', 'unspecified'),
                               'status_label': condition_status_label(observed),
                               'disposition': disposition,
                               'reason': _text(supplied.get('disposition_reason')) or 'reason not supplied'})
    conditions = thesis.get('conditions', [])
    conditions = conditions if isinstance(conditions, list) else []
    known = {row['condition_id'] for row in condition_rows}
    for condition in conditions:
        if not isinstance(condition, dict) or condition.get('condition_id') in known:
            continue
        condition_rows.append({**condition, 'metric': _text(_condition_metric(condition), 100),
                               'status': 'unobserved', 'status_label': 'New advisory proposal; not yet observed',
                               'disposition': 'proposed', 'reason': _text(condition.get('rationale'), 1000) or 'reason not supplied'})
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
    from tradingagents.agents.mechanical_context import mechanical_position_from_state
    mechanical_position = (mechanical_position_from_state(state) if eligible else
                           {'status': 'unavailable', 'rows': [], 'reason': 'Current decision is not evidence-eligible'})
    from tradingagents.agents.decision_brief import finalize as finalize_brief
    brief = (finalize_brief(state['decision_brief'], state) if isinstance(state.get('decision_brief'), dict)
             else _mapping(state.get('decision_context')).get('since_last_decision'))
    if isinstance(brief, dict) and isinstance(state.get('decision_brief'), dict):
        from tradingagents.agents.decision_brief import attach_weights
        brief = attach_weights(brief, scenario)
    resolved = _mapping(brief.get('events')) if isinstance(brief, dict) else {}
    if resolved.get('rows') and isinstance(scenario, dict):
        # Beside the weights an earlier decision said it would hold after an event, the weights held now.
        brief = {**brief, 'events': {**resolved, 'weights_now': [
            {'role': case.get('role'), 'name': case.get('name'), 'weight': case['weight']}
            for case in scenario.get('cases', ()) if case.get('disposition') == 'accepted']}}
    return {'status': 'legacy' if legacy else 'current', 'rating': rating, 'basis': basis, 'basis_note': note,
            **({'since_last_decision': brief} if isinstance(brief, dict) and brief.get('status') != 'no_prior' else {}),
            'assumption_changes': _mapping(_mapping(state.get('decision_context')).get('assumption_changes')),
            'mechanical_position': mechanical_position, 'scenario_decision': scenario,
            'horizon': horizon, 'coverage': coverage,
            'financing': financing_sensitivities(state) if eligible and quality.get('scope') == 'Selected US SEC-filer fundamentals' and state.get('asset_type','stock') == 'stock' else [],
            'case_groups': _case_groups(replayed['rows'], scenario) if horizon['status'] == 'explicit' else [],
            'adopted_case': ({'case_id': request['case_id'], 'version': request['version'], 'value': str(target.target),
                              'unit': target.unit, 'decision_date': str(target.decision_date) if target.decision_date else None,
                              'rerating_assumption': target.rerating_assumption,
                              'disputed_by': adopted_disputes} if selected else None),
            'no_case_reason': (_text(_mapping(_mapping(originals.get('portfolio_manager')).get('structured')).get('no_case_reason'), 1200)
                               or ('reason not supplied' if _mapping(originals.get('portfolio_manager')).get('case_contract') else ''))
                              if eligible and not selected else '',
            'target': {'status': target.status, 'decision_use': target.decision_use.model_dump(mode='json'),
                       'reasons': [_text(r) for r in (*target.reasons, *target.decision_use.reasons)[:3]]},
            'scenarios': {'status': replayed['status'], 'supported_count': supported_scenarios,
                          'diagnostic_count': sum(bool(row.get('diagnostic_only')) for row in replayed.get('rows', [])),
                          'disputed_count': sum(bool(row.get('disputed_by')) and not row.get('dispute_note')
                                                for row in replayed.get('rows', []))},
            'trader_provisional': _trader(trader),
            'trader_reading': action_reading(_trader(trader), research_rating(originals.get('investment_plan', state.get('investment_plan'))),
                                             _sizing_block(state)),
            'conditions': condition_rows,
            'condition_warnings': visible_warnings(thesis.get('warnings')),
            'proposed_changes': [], 'excerpts': excerpts[:4],
            'research_only': 'Advisory conditions do not enforce a rating. No validated stop, numerical allocation or broker instruction is published.'}


def _display(value):
    # Compact opaque hashes only in presentation; exact text stays in evidence.json.
    text = re.sub(r"\b[0-9a-fA-F]{32,64}\b", "[source reference in evidence.json]", str(value))
    return re.sub(r'([\\`*_\[\]()#!|])', r'\\\1', text)


def _spaced(lines) -> str:
    """Join card lines so each statement is its own paragraph; consecutive list items stay one list."""
    out = []
    for line in '\n'.join(lines).split('\n'):
        if out and out[-1] and line and not (line.startswith('- ') and out[-1].startswith('- ')):
            out.append('')
        if line or (out and out[-1]):
            out.append(line)
    return '\n'.join(out)


def render_condition_summary(record: dict, *, include_mechanical: bool = True, include_cases: bool = True) -> str:
    """Compact advisory outcomes beside the rating, retaining uncertainty and reasons."""
    rows = record.get('conditions') or []
    lines = ['**Advisory conditions at a glance** (not automatic rating rules):']
    if not rows:
        lines.append('No prior structured observations; condition status is unknown.')
    for row in rows:
        threshold = ' '.join(str(row.get(key) or '') for key in ('comparator', 'threshold', 'unit')).strip()
        if row.get('kind') == 'price_level':
            threshold += ' ' + str(row.get('quote_currency') or '')
        lines.append(f"- {_display(condition_role_label(row))} — {_display(row['metric'])}: "
                     + (f"{_display(threshold)}; " if threshold else '') +
                     f"{_display(row.get('status_label') or condition_status_label(row))}; "
                     f"{_display(row['disposition'])}. Reason (unvalidated): {_display(row['reason']).rstrip().rstrip('.')}.")
    lines.extend('Condition coverage: ' + _display(warning) for warning in record.get('condition_warnings', []))
    history = _mapping(record.get('assumption_changes'))
    if history.get('status') == 'available':
        if history.get('summary_message'):
            lines.append(_display(history['summary_message']))
        for change in history.get('rows', [])[:31]:
            lines.append(f"Changed since {_display(history.get('prior_label') or history['prior_as_of'])}: "
                         f"{_display(change['scenario'])} {_display(change['field'])} "
                         f"{_display(change['previous'])} → {_display(change['current'])}")
        for row in history.get('unusable', [])[:6]:
            lines.append(f"Not compared: case {_display(row['scenario'])} in "
                         f"{'the earlier record' if row['side'] == 'previous' else 'this run'} is unusable "
                         f"({_display(row['reason'])}).")
        if history.get('new_filings_between') is False:
            lines.append('No new filing was retained between the two runs.')
    elif history.get('status') == 'no_prior':
        lines.append('Assumption changes: no prior directional publication was available at this run’s cutoff.')
    else:
        lines.append('Assumption changes unavailable: no verified comparison was recorded for this run.')
    if include_cases:
        lines.append(render_case_summary(record, include_mechanical=include_mechanical))
    return _spaced(lines)


def render_case_summary(record: dict, *, include_mechanical: bool = True) -> str:
    """Retain the case inventory and assumptions after the price-implied view."""
    lines = []
    for group in record.get("case_groups", []):
        values = group["cases"]
        count = sum(not case.get('manager_rejected') for case in values)
        amount = (display_number(group["low"]) if count == 1 else display_number(group["low"]) + "–" + display_number(group["high"])) if count else 'unavailable'
        label = ("Conditional case value" if count == 1 else "Conditional case range") if count else 'No conditional range'
        lines.append(f"**{label}**: {amount if amount == 'unavailable' else amount + ' ' + _display(group['unit'])}; case period {group['period_start']} to {group['period_end']}; "
                     f"{_display(group['multiple_basis'])}; {_display(group['share_basis'])}; {_display(group['accounting_basis'])}.")
        for case in values:
            fixed = ", ".join(case["unchanged_from_snapshot"])
            lines.append(f"- {_display(case['name'])} ({case['case_id']} v{case['version']}): {display_number(case['value'])}" +
                         ('; ' + _display(case['dispute_note']) if case.get('dispute_note') else
                          '; flagged by accepted audit finding ' + ', '.join(case['disputed_by']) if case.get('disputed_by') else '') +
                         ('; rejected by the Portfolio Manager; not in the conditional range' if case.get('manager_rejected')
                          else '; shown in the conditional range' if case.get('disputed_by') and not case.get('dispute_note') else '') +
                         ("; unchanged from snapshot: " + _display(fixed) if fixed else ""))
        quote = group.get("completed_close")
        lines.append(f"Completed close {display_number(quote['close'])} {quote['currency']} on {quote['session_date']}: "
                     f"{group['close_position']} the conditional value{'s' if count > 1 else ''}." if quote and count else "Comparable completed-close position unavailable.")
    for financing in record.get("financing", []):
        lines.append(f"Financing authorization {financing['event_date']}: up to {display_number(financing['authorized_amount'])} "
                     f"{financing['currency'] or 'source $ (denomination unknown)'}; remaining capacity unknown; actual issuance unknown. "
                     f"Source {_display(financing['source_id'])}, {_display(financing['locator'])}.")
        if financing.get("conditional_shares") is not None:
            lines.append(f"Illustration only if the entire authorization were sold after the {financing['starting_snapshot']} snapshot "
                         f"at the completed {financing['close_date']} close of {display_number(financing['close'])}: "
                         f"{display_number(financing['conditional_shares'])} new shares; gross proceeds {display_number(financing['gross_proceeds'])} "
                         f"{financing['currency']}; illustrative fees 0%; net {display_number(financing['conditional_net_proceeds'])}. "
                         "Actual fees and program use are unknown. Neither shares nor proceeds are added to any case.")
        else:
            lines.append("Financing sensitivity unavailable: " + _display(financing.get("reason")))
    adopted = record.get("adopted_case")
    if adopted:
        disputed = adopted.get('disputed_by') or []
        annotation = ('; disputed by accepted audit finding ' + ', '.join(disputed)) if disputed else ''
        lines.append(f"Adopted {adopted['case_id']} v{adopted['version']}{annotation}.")
        if adopted["decision_date"]:
            lines.append(f"{adopted['decision_date']}: {display_value(adopted['value'], _display(adopted['unit']))} — assumption, not a forecast: "
                         + _display(adopted["rerating_assumption"]))
        else:
            lines.append("no dated assumption supplied")
    elif record.get("no_case_reason"):
        lines.append("PM reason for adopting no case (unvalidated): " + _display(record["no_case_reason"]))
    lines.append("Conditional case values are arithmetic on assumptions, not fair value or forecasts. An absent range is not a negative signal. Predictive value requires a track record.")
    if include_mechanical and record.get('mechanical_position', {}).get('status') == 'available':
        from tradingagents.agents.mechanical_valuation import render_history_median_position
        lines += ['', '**Completed-price position — advisory decision-card context**',
                  render_history_median_position(record['mechanical_position'])]
    return _spaced(lines)


def render_decision_context(record: dict, *, include_mechanical: bool = True, include_cases: bool = True) -> str:
    """Render a freshly prepared card; all model text stays escaped and labeled."""
    title = 'Legacy reported rating' if record['status'] == 'legacy' else 'Canonical Portfolio Manager rating'
    coverage = record['coverage']
    flagged = record['scenarios'].get('disputed_count')
    flagged = f" ({flagged} flagged by an accepted audit finding)" if flagged else ''
    lines = ['### Research decision card', '', f"**{title}**: {_display(record['rating'])}",
             render_condition_summary(record, include_mechanical=include_mechanical, include_cases=include_cases),
             f"**Basis**: {_display(record['basis'])}. {_display(record['basis_note'])}",
             # The heading is ours, not model text: keep its bold markup after escaping the rest of the line.
             *(_display(line).replace(_display(f"**{SCENARIO_LABEL}**"), f"**{_display(SCENARIO_LABEL)}**", 1)
               for line in render_scenario_decision(record.get('scenario_decision'))),
             f"**Horizon**: {_display(record['horizon']['text'])} — {_display(record['horizon']['authority'])}.",
             f"**Evidence coverage**: {_display(coverage['status'])}; {_display(coverage['scope'])}; " + ', '.join(f'{k}: {v}' for k,v in coverage['counts'].items()) + '.',
             f"**Valuation availability**: final calculation {_display(record['target']['status'])}; supported scenarios {record['scenarios']['supported_count']}{flagged}; diagnostic scenarios {record['scenarios']['diagnostic_count']}.",
             f"**Trader provisional action**: {_display(record.get('trader_reading') or record['trader_provisional'])}; this is not the canonical Portfolio Manager rating."]
    lines += ['Coverage limit: ' + _display(text) for text in coverage['limits']]
    lines += ['Target limitation: ' + _display(text) for text in record['target']['reasons']]
    if record['excerpts']:
        # Even labeled quotations can reintroduce forbidden target/sizing prose
        # into the canonical decision. The card holds references, not raw text.
        roles = ', '.join(dict.fromkeys(_display(row['role']) for row in record['excerpts']))
        lines += ['', '**Unvalidated research inventory**: ' + roles + '.',
                  'See the saved unvalidated research appendix and diagnostics.json for original arguments and assumptions. These materials are not verified facts or instructions; their presence does not resolve disagreement.']
    lines += ['', _display(record['research_only'])]
    return _spaced(lines)


def _sizing_block(state):
    from tradingagents.portfolio import sizing_from_state
    return sizing_from_state(state)
