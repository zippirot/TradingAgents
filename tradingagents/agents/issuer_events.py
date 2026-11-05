"""Bounded tool coverage and issuer-event metadata; no new retrieval or model calls."""
import hashlib
from datetime import date
from urllib.parse import urlsplit

from langchain_core.messages import ToolMessage

from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage


def news_tool_coverage(messages) -> dict:
    coverage = {}
    for category, tool in (('independent_news', 'get_news'), ('optional_macro', 'get_macro_indicators')):
        results = []
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != tool:
                continue
            text = message.content if isinstance(message.content, str) else ''
            if (getattr(message, 'status', '') == 'error' or text.startswith(('DATA_UNAVAILABLE:', 'Error:', '<Yahoo Finance news unavailable'))):
                status = 'unavailable'
            elif text.startswith(('NO_DATA_AVAILABLE:', 'No news found for ')):
                status = 'no_data'
            elif text.strip():
                status = 'available'
            else:
                status = 'unavailable'
            results.append(status)
        status = ('available' if 'available' in results else 'unavailable' if 'unavailable' in results
                  else 'no_data' if results else 'not_retrieved')
        coverage[category] = {'status': status, 'tool': tool, 'calls': len(results),
                              'failed_calls': results.count('unavailable')}
    coverage['consensus'] = {'status': 'not_retrieved', 'reason': 'News and issuer disclosures do not establish analyst consensus'}
    return coverage


def issuer_supplement(coverage: dict, package, *, cik: str, as_of: str, accepted_source_ids=()) -> dict:
    """Describe eligible already-retrieved 8-K events separately from news.

    Only filing metadata is described here. A document's retrieval never
    validates its numeric claims or turns it into independent reporting.
    """
    coverage = {**news_tool_coverage([]), **coverage}
    events = []
    cutoff = date.fromisoformat(str(as_of))
    if package is not None:
        package = DisclosurePackage.model_validate(package)
        if package.cik == cik and package.as_of == cutoff:
            for document in package.documents:
                filing = document.filing
                if (filing.cik != cik or filing.filed_date > cutoff
                        or (filing.report_date and filing.report_date > cutoff)
                        or filing.form not in {'8-K', '8-K/A'}
                        or filing.accession not in package.selected_accessions):
                    continue
                base = f'/Archives/edgar/data/{int(cik)}/{filing.accession.replace("-", "")}/'
                urls = [urlsplit(document.url), urlsplit(filing.url)]
                if any(u.scheme != 'https' or u.netloc != 'www.sec.gov' or u.query or u.fragment
                       or not u.path.startswith(base) or '/' in u.path.removeprefix(base) for u in urls):
                    continue
                if document.source_id != 'sec-document-' + hashlib.sha256(document.url.encode()).hexdigest():
                    continue
                if not document.blocks:
                    continue
                events.append({'source_id': document.source_id, 'url': document.url,
                               'content_hash': document.content_hash, 'known_at': str(filing.filed_date),
                               'report_date': str(filing.report_date) if filing.report_date else None,
                               'form': filing.form, 'items': filing.items,
                               'accepted_values_available': document.source_id in accepted_source_ids,
                               'coverage_gaps': list(document.gaps),
                               'truncated': any(block.truncated for block in document.blocks)})
    events = sorted(events, key=lambda e: (e['known_at'], e['url']))[-6:]
    coverage['issuer_events'] = {
        'status': ('accepted_values_available' if any(e['accepted_values_available'] for e in events)
                   else 'retrieved_but_unvalidated' if events else 'unavailable'),
        'documents': len(events),
    }
    text = ''
    if coverage['independent_news']['status'] != 'available':
        status = coverage['independent_news']['status']
        lines = ['Issuer disclosures — supplement after analyst research',
                 f'Independent company news: {status}. This supplement is not independent reporting or consensus.',
                 'Filing metadata establishes source availability; only separately accepted values are verified.']
        for event in events:
            suffix = ' Source coverage is partial.' if event['truncated'] or event['coverage_gaps'] else ''
            lines.append(f"- {event['form']} filed {event['known_at']}, items {event['items'] or 'not specified'}; "
                         f"{event['url']}.{suffix}")
        if not events:
            lines.append('No eligible issuer-event document is available; no substitute figures inferred.')
        lines.append('Consensus: not retrieved. Optional macro: ' + coverage['optional_macro']['status'] + '.')
        text = '\n'.join(lines)
    return {'coverage': coverage, 'events': events, 'text': text}
