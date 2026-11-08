"""Bounded tool coverage and issuer-event metadata; no new retrieval or model calls."""
import hashlib
import re
from datetime import date, datetime
from decimal import Decimal
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
            elif 'Coverage: degraded: search_fallback, headlines_only' in text.split('### ', 1)[0]:
                status = 'degraded'
            elif text.strip():
                status = 'available'
            else:
                status = 'unavailable'
            results.append(status)
        status = ('degraded' if 'degraded' in results else 'available' if 'available' in results else 'unavailable' if 'unavailable' in results
                  else 'no_data' if results else 'not_retrieved')
        coverage[category] = {'status': status, 'tool': tool, 'calls': len(results),
                              'failed_calls': results.count('unavailable')}
        if 'degraded' in results:
            coverage[category]['reason'] = 'search_fallback, headlines_only'
    coverage['consensus'] = {'status': 'not_retrieved', 'reason': 'News and issuer disclosures do not establish analyst consensus'}
    return coverage


def issuer_supplement(coverage: dict, package, *, cik: str, as_of: str, accepted_source_ids=()) -> dict:
    """Describe eligible already-retrieved 8-K events separately from news.

    Filing metadata and narrowly recognized authorization records are separate.
    Retrieval alone never validates other claims or creates independent reporting.
    """
    coverage = {**news_tool_coverage([]), **coverage}
    events = []
    financing = []
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
                financing.extend(_financing_records(document, cutoff))
                events.append({'source_id': document.source_id, 'url': document.url,
                               'content_hash': document.content_hash, 'known_at': str(filing.filed_date),
                               'report_date': str(filing.report_date) if filing.report_date else None,
                               'form': filing.form, 'items': filing.items,
                               'accepted_values_available': (document.source_id in accepted_source_ids
                                   or any(r['source_id'] == document.source_id for r in financing)),
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
    financing_text = '\n'.join(
        f"- Financing authorization: at-the-market share-sale program; agreement date {r['event_date']}; "
        f"up to {r['authorized_amount']} "
        + (f"{r['currency']} (explicit source denomination). " if r['currency']
           else "source $; denomination unknown. ")
        + "Authorized capacity does not establish issuance; remaining capacity and actual issuance are unknown. "
        f"Source: {r['url']}, {r['locator']}; filed {r['known_at']}; hash {r['content_hash']}. "
        f"Complete source statement: {r['quote']}"
        for r in financing
    )
    return {'coverage': coverage, 'events': events, 'text': text,
            'financing_records': financing, 'financing_text': financing_text}


def _financing_records(document, cutoff):
    """Recognize only an explicit dated ATM authorization, never usage or dilution.

    A dollar symbol alone does not establish denomination. Only an explicit
    local agreement-currency statement can populate currency; retain its source.
    No FX conversion or model interpretation enters the complete paragraph.
    """
    records = []
    for block in document.blocks:
        text = block.text
        if block.truncated or not re.search(r'“?at-the-market”?[”"]? offering program', text, re.I):
            continue
        event = re.match(r'On ([A-Z][a-z]+ \d{1,2}, \d{4}), the Company entered into an equity distribution agreement\b', text)
        amounts = list(re.finditer(r'aggregate offering price of up to \$(\d+(?:\.\d+)?) (million|billion)\b', text, re.I))
        if not event or len(amounts) != 1 or not re.search(r'\bto sell shares of common stock\b', text, re.I):
            continue
        try:
            day = datetime.strptime(event[1], '%B %d, %Y').date()
        except ValueError:
            continue
        if day > cutoff or day > document.filing.filed_date:
            continue
        amount = Decimal(amounts[0][1]) * (Decimal(10) ** (9 if amounts[0][2].lower() == 'billion' else 6))
        if amount <= 0:
            continue
        denominations = list(re.finditer(
            r'All dollar amounts in this agreement are in (U\.S\. dollars|Canadian dollars|Australian dollars)\.', text))
        currency, currency_source = None, None
        if len(denominations) == 1:
            denomination = denominations[0]
            currency = {'U.S. dollars': 'USD', 'Canadian dollars': 'CAD',
                        'Australian dollars': 'AUD'}[denomination[1]]
            currency_source = {'source_id': document.source_id, 'locator': block.locator,
                               'quote': denomination[0]}
        records.append({'type': 'at_the_market_program', 'event_date': str(day),
            'authorized_amount': str(amount), 'source_unit': '$', 'currency': currency,
            'currency_source': currency_source, 'amount_comparator': 'up_to',
            'issuance': None, 'remaining_capacity': None, 'source_id': document.source_id,
            'url': document.url, 'content_hash': document.content_hash, 'locator': block.locator,
            'known_at': str(document.filing.filed_date), 'quote': text})
    return records


def financing_sensitivities(state):
    """Re-extract accepted authorizations; never add hypothetical issuance to cases."""
    from decimal import localcontext

    from tradingagents.agents.valuation_comparison import comparable_quote
    from tradingagents.dataflows.financial_evidence import EvidencePackage

    try:
        package = EvidencePackage.model_validate(state.get("financial_evidence"))
        if str(package.as_of) != state.get("trade_date") or (state.get("issuer_identity") or {}).get("cik") != package.cik:
            return []
        records = issuer_supplement({}, state.get("filing_evidence"), cik=package.cik,
                                    as_of=str(package.as_of))["financing_records"]
    except (ValueError, TypeError):
        return []
    result = []
    for record in records:
        row = {key: record[key] for key in ("event_date", "authorized_amount", "currency", "remaining_capacity",
                                             "issuance", "source_id", "locator", "known_at")}
        result.append(row)
        try:
            if record["currency"] is None:
                raise ValueError("Agreement denomination unknown")
            snapshot = max((f.period_end for f in package.facts if f.metric == "Common Shares Outstanding"
                            and f.origin == "reported" and f.period_start is None and f.value and f.value > 0), default=None)
            if snapshot is None or snapshot >= date.fromisoformat(record["event_date"]):
                raise ValueError("Starting snapshot may already include issuance; no incremental calculation")
            quote = comparable_quote(state, package, record["currency"] + "/shares", snapshot)
            if quote["session_date"] < record["known_at"]:
                raise ValueError("Completed close predates financing disclosure")
            with localcontext() as ctx:
                ctx.prec = 60
                gross = Decimal(record["authorized_amount"])
                row.update(close=quote["close"], close_date=quote["session_date"], gross_proceeds=str(gross),
                           fee_assumption_percent="0", conditional_net_proceeds=str(gross),
                           conditional_shares=str(gross / Decimal(quote["close"])), starting_snapshot=str(snapshot))
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            row["reason"] = str(exc)
    return result
