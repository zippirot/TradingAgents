"""Every convertible note the latest primary filing states as outstanding, with its conversion terms.

Read by code from the filing's own sentences: principal still outstanding, maturity, conversion price and
any capped call bought with the note. A term the filing states two ways is left out, never chosen.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from tradingagents.dataflows.filing_terms import latest_primary, notes_unit_context
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

_DATE = r"([A-Z][a-z]+\s+\d{1,2},\s*\d{4})"
_NAME = r"(20\d{2}) Convertible Notes"
_OUTSTANDING = (
    re.compile(r"The outstanding\s*\$\s*([\d,]+)\s+of aggregate principal amount of\s+(?:the\s+)?" + _NAME
               + r"\s+will mature on\s+" + _DATE),
    re.compile(r"\$\s*([\d,]+)\s+aggregate principal amount of\s+(?:the\s+)?" + _NAME
               + r"\s+remained outstanding with a maturity date of\s+" + _DATE),
)
_PRICE = re.compile(r"conversion price of (?:approximately\s*)?\$\s*([\d,]+(?:\.\d+)?)", re.I)
_ROW = re.compile(_NAME + r"\s*\|\s*[\d.]+\s*\|\s*\|\s*\$\s*\|\s*([\d,]+(?:\.\d+)?)")
_STRIKE = re.compile(r"(20\d{2}) Capped Calls have an initial strike price of \$\s*([\d,]+(?:\.\d+)?) per share")
_CAP = re.compile(r"(20\d{2}) Capped Calls have an initial cap price of \$\s*([\d,]+(?:\.\d+)?) per share")
_EXPIRES = re.compile(r"(20\d{2}) Capped Calls expire on " + _DATE)
_SENTENCE = re.compile(r"(?<=[.;])\s+(?=[A-Z(“\"])")
_SCALE = {"USD thousands": 1000}


def _number(text):
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _day(text):
    try:
        return datetime.strptime(" ".join(text.split()), "%B %d, %Y").date()
    except ValueError:
        return None


def _one(values):
    """The single value every statement agrees on, with where it was read; otherwise nothing."""
    return values[0] if values and len({value for value, _ in values}) == 1 else (None, None)


def discover_convertibles(package: DisclosurePackage, as_of: date) -> list[dict]:
    document = latest_primary(package, as_of)
    if document is None:
        return []
    blocks = [block for block in document.blocks if not block.truncated]
    stated, prices, strikes, caps, expiries = {}, {}, {}, {}, {}
    for block in blocks:
        text = " ".join(block.text.split())
        for pattern in _OUTSTANDING:
            for found in pattern.finditer(text):
                stated.setdefault(found.group(2), []).append(
                    ((_number(found.group(1)), _day(found.group(3))), block.locator))
        for found in _ROW.finditer(text):
            if "conversion price" in text.lower():
                prices.setdefault(found.group(1), []).append((_number(found.group(2)), block.locator))
        for sentence in _SENTENCE.split(text):
            years = set(re.findall(_NAME, sentence))
            if len(years) == 1 and "|" not in sentence:
                for found in _PRICE.finditer(sentence):
                    prices.setdefault(next(iter(years)), []).append((_number(found.group(1)), block.locator))
        for pattern, store, read in ((_STRIKE, strikes, _number), (_CAP, caps, _number), (_EXPIRES, expiries, _day)):
            for found in pattern.finditer(text):
                store.setdefault(found.group(1), []).append((read(found.group(2)), block.locator))
    records = []
    for year, found in sorted(stated.items()):
        (terms, locator) = _one(found)
        if terms is None or None in terms or terms[0] <= 0 or terms[1] < as_of:
            continue
        context = notes_unit_context(document, locator)
        scale = _SCALE.get(context[0]) if context else None
        if scale is None:
            continue
        price, price_locator = _one(prices.get(year, []))
        (strike, strike_locator), (cap, _), (expires, _) = (_one(store.get(year, [])) for store in (strikes, caps, expiries))
        capped = None
        # A capped call is only read as the note's own when its strike is the note's conversion price.
        if None not in (price, strike, cap, expires) and strike == price and cap > strike and expires >= as_of:
            capped = {"strike": str(strike), "cap": str(cap), "expires": expires.isoformat(), "locator": strike_locator}
        records.append({
            "name": f"{year} Convertible Notes", "principal": str(terms[0] * scale), "currency": "USD",
            "as_of": document.filing.report_date.isoformat(), "maturity_date": terms[1].isoformat(),
            "conversion_price": None if price is None or price <= 0 else str(price), "capped_call": capped,
            "locator": locator, "conversion_price_locator": price_locator, "source_id": document.source_id,
        })
    return records
