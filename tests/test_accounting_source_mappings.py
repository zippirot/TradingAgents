"""Retained public SEC lease tables keep dates, scope and component distinctions."""
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.dataflows.filing_facts import discover_filing_cells, verify_filing_cells
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)

FIXTURE = Path(__file__).parent / "fixtures/document_access/accounting_source_msft.json"

def source_package(change=None):
    raw = json.loads(FIXTURE.read_text())
    blocks = [SourceBlock.model_validate(b) for b in raw["blocks"] if b["locator"] != "block-44"]
    if change:
        blocks = [change(b) for b in blocks]
    filing = FilingReference(cik="0000789019", accession="0001193125-26-436133", form="10-Q",
        filed_date="2026-10-28", report_date="2026-09-30", primary_document="msft-20260930.htm",
        items="", url=raw["url"])
    doc = FilingDocument(source_id="sec-document-" + hashlib.sha256(raw["url"].encode()).hexdigest(),
        filing=filing, url=raw["url"], retrieved_at=raw["retrieved_at"],
        content_hash=raw["content_hash"], blocks=tuple(blocks))
    return DisclosurePackage(cik=filing.cik, as_of="2026-11-06", documents=(doc,))

def extract(data):
    return verify_filing_cells(data, discover_filing_cells(data))

def test_retained_msft_lease_totals_and_financing_cash_keep_distinct_source_scope():
    result = extract(source_package())
    facts = {(f.metric, f.period_end): f for f in result.evidence.facts}
    assert facts["Finance Lease Liabilities", date(2026, 9, 30)].value == Decimal("70973000000")
    assert facts["Operating Lease Liabilities", date(2026, 9, 30)].value == Decimal("27477000000")
    cash = facts["Finance Lease Principal Payments", date(2026, 9, 30)]
    assert cash.value == Decimal("1000000000")
    assert cash.period_start == date(2026, 7, 1)
    assert all("Equipment" not in f.metric for f in result.evidence.facts)
    assert all(s.content_hash == json.loads(FIXTURE.read_text())["content_hash"] for s in result.evidence.sources)

@pytest.mark.parametrize("change", [
    lambda b: b.model_copy(update={"section": "Unrelated liabilities"}) if b.locator == "block-248" else b,
    lambda b: b.model_copy(update={"text": b.text.replace("65,968", "64,968")}) if b.locator == "block-248" else b,
    lambda b: b.model_copy(update={"truncated": True}) if b.locator == "block-248" else b,
])
def test_lease_total_needs_context_complete_components_and_intact_source(change):
    result = extract(source_package(change))
    assert not any(f.metric == "Finance Lease Liabilities" and f.period_end == date(2026, 9, 30)
                   for f in result.evidence.facts)

@pytest.mark.parametrize("change", [
    lambda b: b.model_copy(update={"text": b.text.replace("Cash paid for amounts included in the measurement of lease liabilities:", "Other supplemental information:")}),
    lambda b: b.model_copy(update={"text": b.text.replace("Three Months Ended September 30,", "Six Months Ended June 30, and Three Months Ended September 30,")}),
    lambda b: b.model_copy(update={"text": b.text.replace("Financing cash flows from finance leases", "Operating cash flows from finance leases")}),
    lambda b: b.model_copy(update={"currency": "EUR", "currency_locator": "inline XBRL EUR"}),
])
def test_principal_requires_explicit_lease_cash_payment_context_and_dated_columns(change):
    result = extract(source_package(lambda b: change(b) if b.locator == "block-246" else b))
    assert not any(f.metric == "Finance Lease Principal Payments" for f in result.evidence.facts)


@pytest.mark.parametrize("cell, expected", [("—", Decimal("0")), ("", None)])
def test_cash_paid_dash_is_sourced_zero_but_blank_is_unavailable(cell, expected):
    data = source_package(lambda b: b.model_copy(update={
        "text": b.text.replace("1,000", cell)
    }) if b.locator == "block-246" else b)
    facts = [f for f in extract(data).evidence.facts
             if f.metric == "Finance Lease Principal Payments"
             and f.period_end == date(2026, 9, 30)]
    if expected is None:
        assert not facts
    else:
        assert len(facts) == 1 and facts[0].value == expected


def test_lease_total_reconciliation_uses_printed_decimal_precision():
    def finer(block):
        if block.locator != "block-248":
            return block
        return block.model_copy(update={"text": block.text.replace("5,005", "5,005.000")
            .replace("65,968", "65,968.000").replace("70,973", "70,973.010")})
    facts = extract(source_package(finer)).evidence.facts
    assert not any(f.metric == "Finance Lease Liabilities" and f.period_end == date(2026, 9, 30)
                   for f in facts)
