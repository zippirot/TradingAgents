"""Deterministic, source-bound convertible note terms from a validated corpus."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from tradingagents.dataflows.filing_terms import latest_primary, notes_unit_context
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

_MATURITY = re.compile(
    r"The outstanding\s*\$\s*([\d,]+)\s+of aggregate principal amount of\s+"
    r"2026 Convertible Notes\s+will mature on\s+([A-Z][a-z]+\s+\d{1,2},\s*\d{4})",
    re.I,
)
_PRICE = re.compile(
    r"2026 Convertible Notes(?:(?!\.\s+[A-Z]|20\d{2} Convertible Notes).){0,350}?"
    r"equivalent to an initial conversion price of approximately"
    r"\s*\$\s*([\d,]+(?:\.\d+)?)\s+per share", re.I,
)
_ELECTION = re.compile(
    r"Upon conversion of the 2026 Convertible Notes,\s+the Company will pay or deliver,"
    r"\s+as the case may be,\s+cash, shares of common stock or a combination of cash and shares of common stock,"
    r"\s+at the Company[’']s election\.", re.I,
)
_PLAN = re.compile(
    r"We plan to repurchase, repay, acquire or otherwise settle the remaining outstanding principal"
    r" of our 2026 Convertible Notes by using cash on hand and cash generated from our operations\.", re.I,
)


class ConvertibleNoteRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    principal_outstanding: Decimal
    principal_unit: str
    as_of: date
    maturity_date: date
    conversion_price: Decimal | None
    settlement_election: str | None
    stated_plan: str | None
    source_id: str
    source_url: str
    locator: str
    unit_locator: str
    currency_locator: str
    conversion_price_locator: str | None
    settlement_election_locator: str | None
    stated_plan_locator: str | None
    content_hash: str
    filed_date: date


def discover_convertible_terms(package: DisclosurePackage, as_of: date) -> tuple[ConvertibleNoteRecord, ...]:
    document = latest_primary(package, as_of)
    if document is None:
        return ()
    filing = document.filing
    candidates = []
    for block in document.blocks:
        if block.truncated:
            continue
        match = _MATURITY.search(block.text)
        if match is None:
            continue
        context = notes_unit_context(document, block.locator)
        if context is None:
            continue
        try:
            maturity = datetime.strptime(match.group(2), "%B %d, %Y").date()
        except ValueError:
            continue
        if maturity < as_of:
            continue
        candidates.append((block, match, context, maturity))
    if not candidates or len({(match.group(1).replace(",", ""), maturity, context[0])
                              for _, match, context, maturity in candidates}) != 1:
        return ()
    for block, match, context, maturity in candidates[:1]:
        price = election = plan = None
        price_locator = election_locator = plan_locator = None
        prices = []
        for candidate in document.blocks:
            if candidate.truncated:
                continue
            text = candidate.text
            if "2026 Convertible Notes" not in text:
                continue
            prices.extend(
                (Decimal(found.group(1).replace(",", "")), candidate.locator)
                for found in _PRICE.finditer(text)
            )
            if election is None:
                found = _ELECTION.search(text)
                if found:
                    election = found.group(0)
                    election_locator = candidate.locator
            if plan is None:
                found = _PLAN.search(text)
                if found:
                    plan = found.group(0)
                    plan_locator = candidate.locator
        if prices and len({value for value, _ in prices}) == 1:
            price, price_locator = prices[0]
        return (ConvertibleNoteRecord(
            name="2026 Convertible Notes", principal_outstanding=Decimal(match.group(1).replace(",", "")),
            principal_unit=context[0], as_of=filing.report_date, maturity_date=maturity,
            conversion_price=price, settlement_election=election, stated_plan=plan,
            source_id=document.source_id, source_url=document.url, locator=block.locator,
            unit_locator=context[1], currency_locator=context[2],
            conversion_price_locator=price_locator, settlement_election_locator=election_locator,
            stated_plan_locator=plan_locator, content_hash=document.content_hash, filed_date=filing.filed_date,
        ),)
    return ()
