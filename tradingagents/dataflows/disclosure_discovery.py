"""Small deterministic release patterns, all passed through the public validator.

This supplements model proposals, never repairs an invalid proposed record or
claims complete disclosure coverage. Source quotes/locators remain unchanged.
"""
from __future__ import annotations

import re
from decimal import Decimal

from tradingagents.dataflows.disclosure_context import (
    _HEADING,
    central_estimate_clause,
    lower_bound_clause,
    outlook_period,
    qualified_value_spans,
)
from tradingagents.dataflows.disclosure_evidence import (
    DisclosureClaim,
    DisclosureResult,
    validate_disclosure_claims,
)
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

_NUMBER = r'\d[\d,]*(?:\.\d+)?'


def _decimal(value):
    return Decimal(value.replace(',', ''))


def _amount(span):
    """The supported span itself supplies metric, value/range and unit."""
    match = re.fullmatch(
        r'(?P<metric>.+?) (?:was|were|of|ended the quarter at|in the range of|is expected to be) '
        r'(?:approximately )?\$?(?P<value>' + _NUMBER + r')(?P<first_percent>%)?'
        r'(?: to \$?(?P<upper>' + _NUMBER + r'))?\s*'
        r'(?P<unit>million shares|million|billion|thousand|%)(?: of revenue)?\.?', span, re.I)
    if not match:
        return None
    if match['first_percent'] and match['unit'] != '%':
        return None
    return {'metric': match['metric'], 'value': _decimal(match['value']),
            'upper_value': _decimal(match['upper']) if match['upper'] else None,
            'unit': match['unit']}


def discover_disclosures(packages) -> DisclosureResult:
    packages = tuple(DisclosurePackage.model_validate(p) for p in packages)
    blocks = {(d.source_id, b.locator): b.section + '\n' + b.text
              for p in packages for d in p.documents for b in d.blocks}
    proposed = []
    for package in packages:
        for doc in package.documents:
            heading = None
            period, kind = None, None
            note = next((b for b in doc.blocks if re.fullmatch(
                r'\(1\)\s*All growth rates are year-over-year unless otherwise specified\.', b.text, re.I)), None)
            definitions = {doc.blocks[i - 1].text.strip(): b for i, b in enumerate(doc.blocks) if i}
            for block in doc.blocks:
                text = block.text.lstrip('•- ').strip()
                historical = _HEADING.fullmatch(text)
                outlook = outlook_period(text)
                if historical or outlook:
                    heading = block
                    period = historical['period'] if historical else outlook
                    kind = 'historical' if historical else 'guidance'
                    continue
                lower = lower_bound_clause(text)
                if lower:
                    proposed.append({'source_id': doc.source_id, 'locator': block.locator,
                        'metric': lower['metric'], 'value': _decimal(lower['value']), 'unit': '%', 'period': lower['year'],
                        'kind': 'guidance', 'quote': lower['quote'], 'comparator': 'at_least'})
                if heading is None:
                    continue
                if not block.text.lstrip().startswith(('•', '- ')):
                    heading = None
                    continue
                # A complete qualified sentence may contain multiple separately
                # supported values; each retains the same full source statement.
                central = central_estimate_clause(text)
                sentence = text if central else re.split(r'(?<=[.!?])\s+', text)[0]
                spans = qualified_value_spans(sentence, kind)
                if not spans:
                    spans = (text,) if kind == 'guidance' else ()
                for span in spans:
                    fields = _amount(span)
                    if fields is None:
                        continue
                    data = dict(source_id=doc.source_id, locator=block.locator,
                        period=period, kind=kind, quote=sentence if kind == 'historical' else text,
                        value_quote=span if span != (sentence if kind == 'historical' else text) else None,
                        period_locator=heading.locator, **fields)
                    if central:
                        data.update(comparator="central_estimate", tolerance_percent=_decimal(central["tolerance"]))
                    growth = re.match(r", an (?:increase|decrease) of (" + _NUMBER + r")%", sentence[len(span):])
                    if kind == 'historical' and growth and note:
                        data['comparison'] = {'quote': growth[0], 'value': _decimal(growth[1]),
                                                  'unit': '%', 'basis_locator': note.locator}
                    proposed.append(data)
                if kind == 'historical':
                    # Existing simple highlighted revenue and AI ARR contract,
                    # including its explicitly referenced comparison/definition.
                    for match in re.finditer(
                        r'(?P<quote>(?P<metric>Revenue|AI Customer ARR) was \$(?P<value>' + _NUMBER
                        + r') (?P<unit>million|billion)), an (?:increase|decrease) of (?P<growth>'
                        + _NUMBER + r')%', text, re.I):
                        definition = definitions.get(match['metric'])
                        data = {'source_id': doc.source_id, 'locator': block.locator,
                            'metric': match['metric'], 'value': _decimal(match['value']), 'unit': match['unit'],
                            'period': period, 'kind': kind, 'quote': match['quote'], 'period_locator': heading.locator}
                        if definition:
                            data.update(definition=definition.text, definition_locator=definition.locator)
                        if note:
                            data['comparison'] = {'quote': match[0][len(match['quote']):],
                                'value': _decimal(match['growth']), 'unit': '%', 'basis_locator': note.locator}
                        proposed.append(data)
    # Stable source order; one finite extraction batch, with explicit coverage.
    parsed, malformed = [], []
    for index, proposal in enumerate(proposed[:32]):
        try:
            parsed.append(DisclosureClaim.model_validate(proposal))
        except (ValueError, TypeError):
            malformed.append(
                f"discovered record {index} at {proposal['locator']}: malformed disclosure record; not accepted"
            )
    checked = validate_disclosure_claims(parsed, blocks, packages=packages)
    warnings = list(checked.warnings)
    if len(proposed) > 32:
        warnings.append('Deterministic disclosure discovery bounded at 32 proposed records; later patterns not evaluated')
    if not proposed:
        warnings.append('No supported deterministic release pattern found; disclosure coverage remains incomplete')
    return DisclosureResult(claims=checked.claims, rejected=(*malformed, *checked.rejected), warnings=tuple(warnings))
