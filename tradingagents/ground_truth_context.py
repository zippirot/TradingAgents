"""Literal coverage of one retained input field, without financial authority."""
import hashlib
import json
import re
from datetime import date

from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component


def context_sources(state):
    """Expose the exact brief's vocabulary, scoped to its recorded run."""
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
                'cik': (state.get('issuer_identity') or {}).get('cik')}
    source_id = 'brief-context-' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    tokens = sorted(set(re.findall(r'\b[^\W\d_]+\b', brief.casefold())))
    coverage = {**identity, 'field': 'shared_source_brief', 'characters': len(brief),
                'token_index_complete': True, 'full_text_included': False, 'tokens': tokens}
    text = ('Retained shared_source_brief context coverage. The following casefolded word-token index '
            'covers every character of this exact retained field. Literal word absence cannot establish '
            'absence of synonymous facts. This does not establish which input a particular analyst received '
            'or whether upstream source selection was complete. This record supplies no financial authority.\n'
            + json.dumps(coverage, sort_keys=True, ensure_ascii=False))
    record = {'source_id': source_id, 'locator': 'shared_source_brief/full-retained-token-index',
              'text': text, 'url': '', 'known_at': as_of,
              'kind': 'retained report context; no financial authority', 'truncated': False,
              'coverage': {key: value for key, value in coverage.items() if key != 'tokens'}}
    return {(source_id, record['locator']): record}, []
