"""Scoped retained market inputs for factual review, with no retrieval calls."""
import hashlib
import json
from datetime import datetime

from tradingagents.agents.valuation_reference_flow import (
    render_valuation_reference,
    render_vendor_expectations,
    replay_valuation_reference,
    validate_vendor_expectations,
)
from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation


def _stamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Market source timestamp requires timezone')
    return parsed


def _rendered_rows(sources, rendered, record, prefix, kind, state):
    """Small individually citable rows retain the section's basis and dates."""
    digest = hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()
    header = f"Ticker {state['company_of_interest']}; analysis date {state['trade_date']}. "
    if prefix == 'valuation-reference':
        header += ('Reproduced valuation reference; equity value / trailing revenue, '
                   'retrospective filings known by the analysis cutoff; not forward EV/revenue. ')
    else:
        header += (f"Vendor consensus, unverified; retrieved {record.get('retrieved_at')}; "
                   f"vendor as-of {record.get('vendor_as_of') or 'unknown'}. ")
    table_heading = ''
    source_id = prefix + '-' + digest
    for index, line in enumerate(rendered.splitlines()):
        if not line.strip() or line.startswith('---'):
            continue
        if ' | ' in line and any(word in line for word in ['TTM revenue period', 'Analyst count']):
            table_heading = line
        locator = f'line-{index + 1}'
        sources[(source_id, locator)] = {
            'source_id': source_id, 'locator': locator,
            'text': header + (table_heading + '\n' if table_heading and line != table_heading else '') + line,
            'url': '', 'known_at': record.get('retrieved_at') or state['trade_date'],
            'kind': kind, 'truncated': False,
        }


def market_sources(state):
    """Reproduce and expose existing source data without granting new authority."""
    sources, gaps = {}, []
    cutoff_text = state.get('market_observation_cutoff') or (state.get('analysis_clock') or {}).get('cutoff_utc')
    clock_cutoff = (state.get('analysis_clock') or {}).get('cutoff_utc')
    if cutoff_text and clock_cutoff:
        try:
            cutoff_text = min(_stamp(cutoff_text), _stamp(clock_cutoff)).isoformat()
        except (ValueError, TypeError):
            return {}, ['Retained market source cutoff is invalid.']
    if state.get('price_observation') is not None:
        try:
            price = validate_price_observation(state['price_observation'], state['company_of_interest'], state['trade_date'])
            if cutoff_text:
                raw = price['raw_source']
                observed = min(_stamp(raw['retrieved_at']), _stamp(raw.get('observation_cutoff') or raw['retrieved_at']))
                if observed > _stamp(cutoff_text):
                    raise ValueError('Retained market observation exceeds run cutoff')
            locator = 'completed-close-' + price['session_date']
            text = (f"{price['ticker']} completed close {price['close']} {price['currency']} on "
                    f"{price['session_date']}; analysis date {price['as_of']}; "
                    f"adjustment basis {price['adjustment_basis']}. {price['coverage_note']}")
            sources[(price['source_id'], locator)] = {
                'source_id': price['source_id'], 'locator': locator, 'text': text,
                'url': price['url'], 'known_at': price['session_date'],
                'kind': 'validated retained market observation', 'truncated': False,
            }
        except (ValueError, TypeError, KeyError, OverflowError):
            gaps.append('Retained completed price could not be validated for this run.')
    if state.get('valuation_reference') is not None:
        try:
            record = replay_valuation_reference(state, state['valuation_reference'])
            if record.get('status') not in {'unavailable', 'not_applicable'}:
                _rendered_rows(sources, render_valuation_reference(record), record,
                               'valuation-reference', 'reproduced valuation reference', state)
            elif record.get('status') == 'unavailable':
                gaps.append('Retained valuation reference is unavailable.')
        except (ValueError, TypeError, KeyError, ArithmeticError):
            gaps.append('Retained valuation reference could not be reproduced from scoped sources.')
    if state.get('vendor_expectations') is not None:
        try:
            record = validate_vendor_expectations(state)
            if record.get('status') in {'available', 'partial'}:
                _rendered_rows(sources, render_vendor_expectations(record), record,
                               'vendor-expectations', 'attributed vendor output', state)
            else:
                gaps.append('Retained vendor expectations are unavailable or invalid for this run.')
        except (ValueError, TypeError, KeyError):
            gaps.append('Retained vendor expectations could not be validated for this run.')
    return sources, gaps
