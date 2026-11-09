"""Uncommenced lease payment commitments stated in a validated filing corpus."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from tradingagents.dataflows.filing_terms import latest_primary, notes_unit_context
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

_AMOUNT = re.compile(
    r"As of ([A-Z][a-z]+ \d{1,2}, \d{4}),\s+(?:the Company|we) had\s*\$\s*"
    r"([\d,]+(?:\.\d+)?)\s*(million)?\s+of estimated undiscounted fixed payment obligations"
    r" primarily for leases of co-location space at data center facilities that have not yet commenced"
    r" and were not included in the condensed consolidated balance sheets\.", re.I,
)
_DATES = re.compile(r"These leases are scheduled to commence between ([A-Z][a-z]+ \d{4}) and ([A-Z][a-z]+ \d{4})", re.I)
_TERM = re.compile(r"weighted-average lease term of ([\d.]+) years", re.I)


class LeaseCommitmentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    undiscounted_amount: Decimal
    unit: str
    as_of: date
    commencement_start: str
    commencement_end: str
    weighted_average_term_years: Decimal | None
    nature: str
    quote: str
    source_id: str
    source_url: str
    locator: str
    unit_locator: str
    currency_locator: str
    content_hash: str
    filed_date: date


def discover_lease_commitments(package: DisclosurePackage, as_of: date) -> tuple[LeaseCommitmentRecord, ...]:
    document = latest_primary(package, as_of)
    if document is None:
        return ()
    records = []
    for block in document.blocks:
        if block.truncated:
            continue
        text = block.text
        amount_match = _AMOUNT.search(text)
        dates_match = _DATES.search(text)
        if not amount_match or not dates_match:
            continue
        try:
            reported = datetime.strptime(amount_match.group(1), "%B %d, %Y").date()
            start = datetime.strptime(dates_match.group(1), "%B %Y").strftime("%Y-%m")
            end = datetime.strptime(dates_match.group(2), "%B %Y").strftime("%Y-%m")
        except ValueError:
            continue
        if reported != document.filing.report_date or reported > as_of or start > end:
            continue
        context = notes_unit_context(document, block.locator)
        if context is None:
            continue
        millions = bool(amount_match.group(3))
        unit = "USD millions" if millions else context[0]
        value = Decimal(amount_match.group(2).replace(",", ""))
        term_match = _TERM.search(text)
        records.append(LeaseCommitmentRecord(
            undiscounted_amount=value, unit=unit, as_of=reported,
            commencement_start=start, commencement_end=end,
            weighted_average_term_years=Decimal(term_match.group(1)) if term_match else None,
            nature="Estimated undiscounted fixed payment obligations primarily for uncommenced co-location data center leases",
            quote=text.strip(), source_id=document.source_id, source_url=document.url,
            locator=block.locator, unit_locator=block.locator if millions else context[1],
            currency_locator=context[2],
            content_hash=document.content_hash, filed_date=document.filing.filed_date,
        ))
    # Use the precision actually displayed by the MD&A amount. For example,
    # 2,955.2 million represents [2,955.15, 2,955.25) million.
    precise = [record for record in records if record.unit == "USD thousands"]
    retained = list(precise)
    for record in records:
        if record.unit != "USD millions":
            continue
        quantum = Decimal(1).scaleb(record.undiscounted_amount.as_tuple().exponent)
        lower = (record.undiscounted_amount - quantum / 2) * 1000
        upper = (record.undiscounted_amount + quantum / 2) * 1000
        if any(
            item.as_of == record.as_of and item.commencement_start == record.commencement_start
            and item.commencement_end == record.commencement_end and item.nature == record.nature
            and (item.weighted_average_term_years is None
                 or record.weighted_average_term_years is None
                 or item.weighted_average_term_years == record.weighted_average_term_years)
            and lower <= item.undiscounted_amount < upper for item in precise
        ):
            continue
        retained.append(record)
    return tuple(retained)
