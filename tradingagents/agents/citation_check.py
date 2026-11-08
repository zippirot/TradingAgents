"""Display-only check of PM numeric citations against the retained canonical brief."""
from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from html import escape

from tradingagents.agents.evidence_presentation import evidence_references

_ID = re.compile(r'(?<![A-Za-z0-9])([FCKD]\d+)(?![A-Za-z0-9])')
_NUMBER = re.compile(
    r'(?<![\w.])\$?\s*([+-]?\d[\d,]*(?:\.\d+)?)\s*'
    r'(million|billion|thousand|percent|bn|m|b|%)?(?!\w)', re.I,
)
_DIRECT = re.compile(r'^- \[([FC]\d+)\] [^:\n]+: (.+)$', re.M)
_REFERENCE = re.compile(r'^- ([KD]\d+): source_id ([^;\n]+);', re.M)


def _decimal(value: object) -> Decimal | None:
    try:
        number = Decimal(str(value).replace(',', ''))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _canonical_values(state: Mapping) -> dict[str, list[tuple[Decimal, str]]]:
    brief = state.get('canonical_financial_context') or ''
    if not isinstance(brief, str):
        return {}
    values: dict[str, list[tuple[Decimal, str]]] = {}
    for label, tail in _DIRECT.findall(brief):
        # F rows: metric: amount unit; ...
        # C rows: method: status; amount unit; ...
        fields = tail.split(';')
        field = fields[0] if label.startswith('F') else fields[1] if len(fields) > 1 else ''
        match = re.match(r'\s*([+-]?\d[\d,]*(?:\.\d+)?)\s+([^;\n]+)', field)
        if match and (number := _decimal(match[1])) is not None:
            unit = match[2].replace('(rounded for display)', '').strip()
            values.setdefault(label, []).append((number, unit))
    references = dict(_REFERENCE.findall(evidence_references(brief)))
    disclosure = state.get('disclosure_evidence') or {}
    if not isinstance(disclosure, dict):
        return values
    extraction = disclosure.get('extraction') or {}
    claims = (extraction.get('claims') or []) if isinstance(extraction, dict) else []
    comparisons = disclosure.get('kpi_comparisons') or []
    for label, source_id in references.items():
        if label.startswith('D'):
            for claim in claims:
                if not isinstance(claim, dict) or claim.get('source_id') != source_id:
                    continue
                if (number := _decimal(claim.get('value'))) is not None:
                    item = (number, str(claim.get('unit') or ''))
                    if item not in values.setdefault(label, []):
                        values[label].append(item)
        elif label.startswith('K'):
            for comparison in comparisons:
                if not isinstance(comparison, dict) or comparison.get('status') != 'pass':
                    continue
                sources = comparison.get('sources') or {}
                for role in ('current', 'prior'):
                    source = sources.get(role) or {}
                    if (source.get('source_id') == source_id
                            and (number := _decimal(comparison.get(f'{role}_value'))) is not None):
                        item = (number, str(comparison.get('currency') or ''))
                        if item not in values.setdefault(label, []):
                            values[label].append(item)
    return values


def _numbers(sentence: str) -> list[tuple[Decimal, str]]:
    parsed = []
    for match in _NUMBER.finditer(sentence):
        if (number := _decimal(match[1])) is not None:
            parsed.append((number, (match[2] or '').lower()))
    return parsed


def _matches(sentence_numbers: list[tuple[Decimal, str]], value: Decimal, unit: str) -> bool:
    def exact_or_display(stated: Decimal, exact: Decimal, quantum: Decimal) -> bool:
        if stated == exact:
            return True
        try:
            return stated == exact.quantize(quantum)
        except InvalidOperation:
            return False

    normalized_unit = unit.casefold()
    percent = normalized_unit in {'percent', '%'}
    canonical_scale = (Decimal(1_000_000_000) if 'billion' in normalized_unit else
                       Decimal(1_000_000) if 'million' in normalized_unit else
                       Decimal(1000) if 'thousand' in normalized_unit else Decimal(1))
    canonical_base = value * canonical_scale
    for stated, suffix in sentence_numbers:
        if percent:
            if suffix in {'%', 'percent'} and exact_or_display(stated, value, Decimal('0.01')):
                return True
            continue
        scale = {'thousand': Decimal(1000), 'm': Decimal(1_000_000),
                 'million': Decimal(1_000_000), 'b': Decimal(1_000_000_000),
                 'bn': Decimal(1_000_000_000), 'billion': Decimal(1_000_000_000)}.get(suffix)
        if scale is None:
            if suffix not in {'%', 'percent'} and stated in {value, canonical_base}:
                return True
        elif exact_or_display(stated, canonical_base / scale, Decimal('0.1')):
            return True
    return False


def _sentences(text: object) -> list[str]:
    if not isinstance(text, str):
        return []
    return [part.strip() for part in re.split(r'(?<=[.!?])\s+(?=[A-Z$])|\n+', text)
            if part.strip()]


def check_pm_citations(state: Mapping) -> dict:
    """Return a nonbinding PM citation summary; never change the source state."""
    pm = (state.get('unvalidated_outputs') or {}).get('portfolio_manager') or {}
    structured = pm.get('structured') or {}
    canonical = _canonical_values(state)
    matched = checked = uncited = citation_only = 0
    mismatches = []
    unresolved = []
    for field in ('executive_summary', 'investment_thesis'):
        for sentence in _sentences(structured.get(field)):
            labels = list(dict.fromkeys(_ID.findall(sentence)))
            if not labels:
                uncited += 1
                continue
            stated = _numbers(sentence)
            if not stated:
                citation_only += 1
                continue
            for label in labels:
                options = canonical.get(label)
                if not options:
                    if label not in unresolved:
                        unresolved.append(label)
                    continue
                checked += 1
                if any(_matches(stated, value, unit) for value, unit in options):
                    matched += 1
                else:
                    mismatches.append({
                        'field': field, 'citation_id': label, 'sentence': sentence,
                        'canonical_value': ', '.join(f'{value} {unit}'.strip()
                                                   for value, unit in options),
                    })
    return {'matched': matched, 'checked': checked, 'uncited_sentences': uncited,
            'citation_only_sentences': citation_only,
            'mismatches': mismatches, 'unresolved_citations': unresolved}


def render_pm_citation_check(result: Mapping) -> str:
    """Render a bounded report section; callers may place it on the card."""
    lines = [f"PM citation check: {result['matched']} of {result['checked']} cited figures matched",
             f"Uncited sentences: {result['uncited_sentences']} (not checked).",
             f"Citation-only sentences: {result.get('citation_only_sentences', 0)} (not checked)."]
    for item in result.get('mismatches', []):
        lines.append(f"- {item['citation_id']}: {escape(item['sentence'])} "
                     f"Canonical value: {escape(item['canonical_value'])}.")
    if result.get('unresolved_citations'):
        labels = ', '.join(result['unresolved_citations'])
        lines.append(f"Citations without a numeric canonical value: {labels} (not checked).")
    return '\n'.join(lines)
