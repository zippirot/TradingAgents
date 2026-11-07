"""Literal coverage of one retained input field, without financial authority."""
import hashlib
import json
from datetime import date

from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component


def context_sources(state):
    """Expose the complete retained brief only for claims about that input field."""
    brief = state.get('shared_source_brief')
    if brief is None:
        return {}, []
    try:
        if not isinstance(brief, str) or not brief.strip():
            raise ValueError('No usable retained brief')
        run_id = state.get('run_id')
        if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 256:
            raise ValueError('Brief needs a run identity')
        ticker = normalize_symbol(state['company_of_interest'])
        safe_ticker_component(ticker)
        as_of = str(date.fromisoformat(state['trade_date']))
    except (ValueError, TypeError, KeyError):
        return {}, ['Retained brief context cannot be tied to this run.']
    field_hash = hashlib.sha256(brief.encode('utf-8')).hexdigest()
    identity = {'run_id': run_id, 'ticker': ticker, 'as_of': as_of, 'field_sha256': field_hash,
                'cik': (state.get('issuer_identity') or {}).get('cik'),
                'analysis_cutoff_utc': (state.get('analysis_clock') or {}).get('cutoff_utc')}
    source_id = 'brief-context-' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    coverage = {**identity, 'field': 'shared_source_brief', 'characters': len(brief),
                'full_text_included': True, 'complete_retained_field': True}
    record = {'source_id': source_id, 'locator': 'shared_source_brief/full-retained-text',
              'text': brief, 'url': '', 'known_at': as_of,
              'kind': 'retained report context; no financial authority', 'truncated': False,
              'coverage': coverage,
              'scope': ('This is the exact retained input field. It supports claims about what the brief '
                        'contains, including synonymous wording. It does not establish which input a '
                        'particular analyst received or completeness of upstream source selection. '
                        'Financial and rating claims require independently validated primary evidence.')}
    if len(json.dumps(record, ensure_ascii=False)) > 24000:
        return {}, ['The complete retained shared_source_brief exceeds the 24000-character source packet; '
                    'brief-content and absence claims cannot be established from a truncated excerpt.']
    return {(source_id, record['locator']): record}, []
