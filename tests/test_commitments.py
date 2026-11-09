"""Offline uncommenced lease commitments."""

from datetime import date
from decimal import Decimal

from tests.test_instrument_terms import package
from tradingagents.dataflows.commitments import discover_lease_commitments
from tradingagents.dataflows.vendors.sec_documents import SourceBlock

NOTE = "As of September 30, 2026, the Company had $ 2,955,158 of estimated undiscounted fixed payment obligations primarily for leases of co-location space at data center facilities that have not yet commenced and were not included in the condensed consolidated balance sheets. These leases are scheduled to commence between November 2026 and June 2028, and have a weighted-average lease term of 11.1 years."
MDNA = "As of September 30, 2026, we had $2,955.2 million of estimated undiscounted fixed payment obligations primarily for leases of co-location space at data center facilities that have not yet commenced and were not included in the condensed consolidated balance sheets. These leases are scheduled to commence between November 2026 and June 2028."


def lease_package(*, note=NOTE, mdna=None):
    p = package()
    d = p.documents[0]
    blocks = (*d.blocks, SourceBlock(locator="block-218", section="Document", text=note))
    if mdna:
        blocks += (SourceBlock(locator="block-450", section="MD&A", text=mdna),)
    return p.model_copy(update={"documents": (d.model_copy(update={"blocks": blocks}),)})


def test_docn_uncommenced_lease_record():
    (record,) = discover_lease_commitments(lease_package(), date(2026, 11, 7))
    assert record.undiscounted_amount == Decimal("2955158")
    assert record.unit == "USD thousands"
    assert record.as_of == date(2026, 9, 30)
    assert record.commencement_start == "2026-11"
    assert record.commencement_end == "2028-06"
    assert record.weighted_average_term_years == Decimal("11.1")
    assert "co-location" in record.nature
    assert record.quote == NOTE
    assert record.locator == "block-218"


def test_notes_and_mdna_variants_deduplicate_to_one_record():
    (record,) = discover_lease_commitments(lease_package(mdna=MDNA), date(2026, 11, 7))
    assert record.undiscounted_amount == Decimal("2955158")
    assert record.locator == "block-218"


def test_amount_without_not_yet_commenced_phrase_yields_no_record():
    assert discover_lease_commitments(lease_package(note=NOTE.replace("that have not yet commenced", "that have commenced")), date(2026, 11, 7)) == ()


def test_rounded_amount_outside_interval_is_not_deduplicated():
    records = discover_lease_commitments(lease_package(mdna=MDNA.replace("2,955.2", "2,955.3")), date(2026, 11, 7))
    assert len(records) == 2
    assert records[1].unit == "USD millions"
    assert records[1].unit_locator == "block-450"


def test_two_decimal_millions_uses_narrower_rounding_interval():
    assert len(discover_lease_commitments(lease_package(mdna=MDNA.replace("2,955.2", "2,955.16")), date(2026, 11, 7))) == 1
    assert len(discover_lease_commitments(lease_package(mdna=MDNA.replace("2,955.2", "2,955.20")), date(2026, 11, 7))) == 2
    assert len(discover_lease_commitments(lease_package(mdna=MDNA.replace("2,955.2", "2,955.15")), date(2026, 11, 7))) == 2


def test_different_weighted_lease_terms_are_not_duplicates():
    mdna = MDNA + " These leases have a weighted-average lease term of 12.1 years."
    assert len(discover_lease_commitments(lease_package(mdna=mdna), date(2026, 11, 7))) == 2
