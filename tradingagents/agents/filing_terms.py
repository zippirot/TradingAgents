"""Source-only note and lease records from the pinned full filing corpus."""
from datetime import date

from tradingagents.agents.document_access import validated_document_corpus
from tradingagents.dataflows.commitments import discover_lease_commitments
from tradingagents.dataflows.instrument_terms import discover_convertible_terms


def prepare_filing_terms(state):
    corpus = validated_document_corpus(state)
    notes = discover_convertible_terms(corpus, date.fromisoformat(state['trade_date'])) if corpus else ()
    leases = discover_lease_commitments(corpus, date.fromisoformat(state['trade_date'])) if corpus else ()
    return {'filing_terms_evidence': {
        'corpus_hash': (state.get('document_sources') or {}).get('corpus_hash') if corpus else None,
        'notes': [record.model_dump(mode='json') for record in notes],
        'leases': [record.model_dump(mode='json') for record in leases],
    }}


def _text(value):
    return ' '.join(str(value).split())


def render_filing_terms(state):
    retained = state.get('filing_terms_evidence')
    if retained is None:  # Older saved states cannot invent newly extracted facts.
        return ''
    expected = prepare_filing_terms(state)['filing_terms_evidence']
    if retained != expected:
        raise ValueError('Retained filing terms differ from pinned source corpus')
    lines = []
    for record in expected['notes']:
        line = (f"- Instrument terms (source-bound): {record['name']}; principal outstanding "
                f"{record['principal_outstanding']} {record['principal_unit']} as of {record['as_of']}; "
                f"matures {record['maturity_date']}")
        if record.get('conversion_price') is not None:
            line += f"; initial conversion price approximately {record['conversion_price']} {record['principal_unit'].split()[0]}/share ({record['conversion_price_locator']})"
        if record.get('settlement_election'):
            line += f"; settlement election: {_text(record['settlement_election'])} ({record['settlement_election_locator']})"
        if record.get('stated_plan'):
            line += f"; stated plan: {_text(record['stated_plan'])} ({record['stated_plan_locator']}). Management statement of intent, not a completed transaction"
        line += (f". Source: {record['source_url']}; source_id {record['source_id']}; {record['locator']}; "
                 f"units {record['unit_locator']}, currency {record['currency_locator']}; "
                 f"filed {record['filed_date']}; hash {record['content_hash']}.")
        lines.append(line)
    for record in expected['leases']:
        line = (f"- Uncommenced lease commitments (source-bound): {record['undiscounted_amount']} {record['unit']} "
                f"as of {record['as_of']}; commencement {record['commencement_start']} to {record['commencement_end']}")
        if record.get('weighted_average_term_years') is not None:
            line += f"; weighted-average lease term {record['weighted_average_term_years']} years"
        line += (f"; {_text(record['nature'])}. Undiscounted future payments over the lease terms; "
                 'not a present-value liability; not included in the balance sheet or in any enterprise-value perimeter above. '
                 f"Source: {record['source_url']}; source_id {record['source_id']}; {record['locator']}; "
                 f"units {record['unit_locator']}; filed {record['filed_date']}; hash {record['content_hash']}.")
        lines.append(line)
    return '\n'.join(lines)
