"""Percentages an analyst states next to the two figures they come from, recomputed by code.

Only two shapes are checked, both where the figures sit in the same sentence as the percentage:
"from A to B ... up/down P%" and "B is P% below/above A" (A may be a dated close the same report lists).
A sentence that does not fit exactly is left alone: a missed slip costs less than a wrong correction.
"""
from __future__ import annotations

import re

_NUM = r"\$?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?([MBK]|million|billion|thousand)?(?![\d%×x])"
_PCT = r"(\d+(?:\.\d+)?)\s?%"
_APPROX = r"(?:about|roughly|approximately|around|nearly|some|~)?\s*"
_DATE = r"(\d{4}-\d{2}-\d{2})"
_FROM_TO = re.compile(rf"\bfrom\s+{_NUM}\s+(?:\([^)]*\)\s+)?to\s+{_NUM}", re.I)
_CHANGE = re.compile(
    rf"(?:\b(?:up|down|rose|fell|grew|gained|lost|dropped|declined|increased|decreased|rise|fall|gain|drop|decline|"
    rf"increase|decrease|change)\b\s+(?:of\s+|by\s+)?{_APPROX}{_PCT})"
    rf"|(?:{_PCT}\s+(?:increase|decline|drop|rise|gain|fall|decrease|change)\b)", re.I)
_SUBJECT = re.compile(rf"{_NUM}\s+is\s+(?={_APPROX}{_PCT}\s+(?:below|above))", re.I)
# A number that names an indicator ("the 200 SMA", "the 50-day average") is a label, not a value.
_LABEL = r"(?!\s*-?\s*(?:SMA|EMA|DMA|WMA|VWMA|MA|day|week|month|session|quarter|year)\b)"
_RELATIVE = re.compile(rf"{_APPROX}{_PCT}\s+(below|above)\s+(?:the|its|a)?\s*(?:{_DATE}|{_NUM}{_LABEL})", re.I)
_DATED = (re.compile(rf"{_DATE}:\s+{_NUM}"), re.compile(rf"{_NUM}\s+\(?(?:on\s+)?{_DATE}\)?"))
LIMIT = 5


def _value(text, unit=None):
    return float(text.replace(",", "")), (unit or "").lower()[:1]


def _dated(text):
    """Closes the report lists against a date, where a date has exactly one value."""
    found = {}
    for match in _DATED[0].finditer(text):
        found.setdefault(match.group(1), set()).add(_value(match.group(2))[0])
    for match in _DATED[1].finditer(text):
        found.setdefault(match.group(3), set()).add(_value(match.group(1))[0])
    return {day: next(iter(values)) for day, values in found.items() if len(values) == 1}


def _off(stated, computed):
    return abs(stated - computed) > max(0.5, 0.1 * abs(computed))


def check_percentages(text) -> list[dict]:
    """Each stated percentage that the sentence's own two figures do not give, with the recomputed value."""
    if not isinstance(text, str) or not text.strip():
        return []
    dated, findings = _dated(text), []
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'*-])|\n+", text):
        pairs, changes = list(_FROM_TO.finditer(sentence)), list(_CHANGE.finditer(sentence))
        if len(pairs) == 1 and len(changes) == 1 and len(re.findall(_PCT, sentence)) == 1:
            (start, unit_a), (end, unit_b) = _value(*pairs[0].group(1, 2)), _value(*pairs[0].group(3, 4))
            stated = float(changes[0].group(1) or changes[0].group(2))
            if unit_a == unit_b and start > 0 and start != end:
                computed = abs(end / start - 1) * 100
                if _off(stated, computed):
                    findings.append({"quote": sentence.strip()[:240], "stated": stated, "computed": round(computed, 1),
                                     "basis": f"{pairs[0].group(1)} to {pairs[0].group(3)}"})
        subject = _SUBJECT.search(sentence)
        if subject and not subject.group(2):
            price = _value(subject.group(1))[0]
            for match in _RELATIVE.finditer(sentence, subject.end()):
                stated, side, day, number, unit = match.groups()
                reference = dated.get(day) if day else (None if unit else _value(number)[0])
                if not reference or reference <= 0:
                    continue
                computed = (reference - price if side.lower() == "below" else price - reference) / reference * 100
                if computed > 0 and _off(float(stated), computed):
                    findings.append({"quote": sentence.strip()[:240], "stated": float(stated),
                                     "computed": round(computed, 1),
                                     "basis": f"{price:g} against {reference:g}" + (f" ({day})" if day else "")})
    return findings[:LIMIT]


def arithmetic_note(text) -> str:
    """A labelled block for the end of a report, or '' when nothing was found."""
    findings = check_percentages(text)
    if not findings:
        return ""
    lines = ["", "", "**Arithmetic check (by code, not a model).** These stated percentages do not match the figures "
             "in the same sentence. If a percentage refers to something else, disregard the line."]
    lines += [f"- Stated {row['stated']:g}%; {row['basis']} gives {row['computed']:g}%. Sentence: \"{row['quote']}\""
              for row in findings]
    return "\n".join(lines)
