"""One source-linked quarter-over-quarter RPO comparison; no demand inference."""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal, localcontext

from tradingagents.dataflows.vendors import sec_documents
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage


def _primary(package: DisclosurePackage):
    originals = [doc for doc in package.documents if doc.filing.form in {'10-Q', '10-K'}
                 and doc.url == doc.filing.url and doc.filing.report_date]
    if not originals:
        raise ValueError('Primary quarterly snapshot unavailable')
    latest = max(doc.filing.report_date for doc in originals)
    selected = [doc for doc in originals if doc.filing.report_date == latest]
    if len(selected) != 1:
        raise ValueError('Competing primary filings for the same report period')
    doc = selected[0]
    if any(other.filing.form in {'10-Q/A', '10-K/A'} and other.filing.report_date == latest
           for other in package.documents):
        raise ValueError('Amended quarter requires resolved RPO scope; comparison unavailable')
    filing = doc.filing
    expected = (f'https://www.sec.gov/Archives/edgar/data/{int(package.cik)}/'
                f"{filing.accession.replace('-', '')}/{filing.primary_document}")
    if (filing.cik != package.cik or filing.filed_date > package.as_of or latest > package.as_of
            or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', filing.accession)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:htm|html|xml)', filing.primary_document, re.I)
            or doc.url != expected
            or doc.source_id != 'sec-document-' + hashlib.sha256(doc.url.encode()).hexdigest()
            or not re.fullmatch(r'[0-9a-f]{64}', doc.content_hash)):
        raise ValueError('RPO source issuer, cutoff or filing identity mismatch')
    # A selected amendment or failed primary cannot disappear just because its
    # download failed. Prior-quarter packages select only the relevant originals.
    present = {source.filing.accession for source in package.documents}
    if any(accession not in present for accession in package.selected_accessions):
        raise ValueError('Selected filing coverage is incomplete; RPO amendment scope unavailable')
    return doc


def _fact(doc, as_of):
    facts = [fact for fact in doc.rpo_facts if fact.period_end == doc.filing.report_date]
    if len(facts) != 1:
        raise ValueError('Exact current-period RPO fact missing or competing')
    fact = facts[0]
    if fact.character_start < 0 or fact.character_end - fact.character_start != len(fact.exact_html):
        raise ValueError('RPO source span mismatch')
    parsed, gaps = sec_documents.extract_rpo_facts(
        fact.unit_html + fact.context_html + fact.exact_html, doc.filing.cik, str(as_of))
    fields = ('metric', 'locator', 'value', 'currency', 'period_end', 'recognition_start',
              'display_value', 'scale', 'decimals', 'context_id', 'unit_id')
    if gaps or len(parsed) != 1 or any(getattr(parsed[0], key) != getattr(fact, key) for key in fields):
        raise ValueError('RPO numeric value or definition does not match retained source spans')
    return fact


def _source(doc, fact):
    return {'source_id': doc.source_id, 'url': doc.url, 'content_hash': doc.content_hash,
            'known_at': str(doc.filing.filed_date), 'accession': doc.filing.accession,
            'fact': fact.model_dump(mode='json')}


def compare_rpo(current: DisclosurePackage, prior: DisclosurePackage) -> dict:
    """Compare exact point-in-time RPO totals on matching issuer and source scope.

    Complete source packages remain machine-readable; callers should render the
    compact text instead of duplicating documents into research prompts.
    """
    result = {
        'status': 'unavailable', 'method': 'quarterly_rpo_change_v1',
        'current_value': None, 'prior_value': None, 'absolute_change': None,
        'percentage_change': None, 'currency': None, 'sources': {},
        'source_packages': {'current': current.model_dump(mode='json'), 'prior': prior.model_dump(mode='json')},
    }
    try:
        if current.cik != prior.cik or current.as_of != prior.as_of:
            raise ValueError('RPO comparison issuer or analysis cutoff mismatch')
        current_doc, prior_doc = _primary(current), _primary(prior)
        if not 60 <= (current_doc.filing.report_date - prior_doc.filing.report_date).days <= 120:
            raise ValueError('RPO periods are not immediately comparable quarterly snapshots')
        current_fact, prior_fact = _fact(current_doc, current.as_of), _fact(prior_doc, prior.as_of)
        if (current_fact.currency != prior_fact.currency or current_fact.metric != prior_fact.metric
                or (current_fact.recognition_start is None) != (prior_fact.recognition_start is None)):
            raise ValueError('RPO currency or consolidated recognition definition differs')
        if prior_fact.value <= 0:
            raise ValueError('Prior RPO must be positive for a percentage comparison')
        with localcontext() as context:
            context.prec = 50
            delta = current_fact.value - prior_fact.value
            percentage = (current_fact.value / prior_fact.value - Decimal(1)) * 100
        result.update(status='pass', reason='Comparable reported RPO source values',
                      current_value=str(current_fact.value), prior_value=str(prior_fact.value),
                      absolute_change=str(delta), percentage_change=str(percentage), currency=current_fact.currency,
                      current_period=str(current_fact.period_end), prior_period=str(prior_fact.period_end),
                      sources={'current': _source(current_doc, current_fact), 'prior': _source(prior_doc, prior_fact)})
        result['text'] = (
            f'Remaining performance obligations: {prior_fact.value:,.0f} {prior_fact.currency} '
            f'at {prior_fact.period_end} → {current_fact.value:,.0f} {current_fact.currency} at {current_fact.period_end}. '
            f'Derived quarter-over-quarter change: {delta:+,.0f} {current_fact.currency} ({percentage:+.2f}%). '
            'Reported values share the same consolidated recognition scope. '
            'The calculation does not establish the cause of the change or imply deteriorating demand.'
        )
    except (ValueError, ArithmeticError, TypeError) as exc:
        result['reason'] = str(exc)
        result['text'] = 'RPO comparison unavailable: ' + str(exc) + '. Missing comparisons are not zero.'
    return result


def retrieve_rpo_comparison(ticker: str, current: DisclosurePackage) -> dict:
    """Acquire only a missing RPO source/comparator using existing bounded SEC paths."""
    prior = DisclosurePackage(cik=current.cik, as_of=current.as_of,
                              gaps=('Prior quarter has not been retrieved',))
    supplemented = current
    if not any(doc.rpo_facts or any(re.search(r'remaining performance obligations?', block.text, re.I)
                                   for block in doc.blocks) for doc in current.documents):
        result = compare_rpo(current, prior)
        result.update(reason='No RPO fact or mention found in the bounded retrieved excerpts; company disclosure coverage is incomplete',
                      text='RPO comparison unavailable: no RPO fact or mention found in the bounded retrieved excerpts; company disclosure coverage is incomplete. No extra retrieval requested.')
        return result
    try:
        # Inspect amendments before the current-source helper narrows documents.
        doc = _primary(current)
        try:
            _fact(doc, current.as_of)
        except ValueError:
            supplemented = sec_documents.get_current_quarter_rpo_evidence(current)
            doc = _primary(supplemented)
            _fact(doc, current.as_of)
        candidates = [source for source in current.documents if source.filing.report_date
                      and source.filing.form in {'10-Q', '10-K'}
                      and 60 <= (doc.filing.report_date - source.filing.report_date).days <= 120]
        if candidates:
            prior_date = max(source.filing.report_date for source in candidates)
            documents = tuple(source for source in current.documents if source.filing.report_date == prior_date)
            existing = current.model_copy(update={'documents': documents,
                'selected_accessions': tuple(dict.fromkeys(source.filing.accession for source in documents))})
            try:
                _fact(_primary(existing), current.as_of)
                prior = existing
            except ValueError:
                pass
        if not prior.documents:
            prior = sec_documents.get_prior_quarter_evidence(ticker, str(current.as_of), str(doc.filing.report_date))
        return compare_rpo(supplemented, prior)
    except Exception as exc:
        result = compare_rpo(supplemented, prior)
        # Exceptions may contain provider URLs or credentials; preserve bounded type.
        result.update(reason=f'RPO source acquisition unavailable ({type(exc).__name__})',
                      text=f'RPO comparison unavailable: source acquisition failed ({type(exc).__name__}); missing values are not zero.')
        return result


def replay_rpo_comparison(record, *, cik, as_of):
    """Recompute retained pre-analyst source packages, never accept saved prose."""
    try:
        sources = record['source_packages']
        current = DisclosurePackage.model_validate(sources['current'])
        prior = DisclosurePackage.model_validate(sources['prior'])
        if current.cik != cik or str(current.as_of) != str(as_of):
            raise ValueError('RPO comparison differs from source brief issuer or cutoff')
        return compare_rpo(current, prior)
    except (KeyError, TypeError, ValueError):
        return {'status': 'unavailable', 'reason': 'Retained RPO source packages unavailable or scope invalid',
                'sources': {}, 'text': 'RPO comparison unavailable: retained source packages unavailable or scope invalid. Missing comparisons are not zero.'}
