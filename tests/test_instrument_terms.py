"""Offline, source-bound convertible note extraction."""

import hashlib
from datetime import date
from decimal import Decimal

from tradingagents.dataflows.instrument_terms import discover_convertible_terms
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)

MATURITY = "The outstanding $ 312,322 of aggregate principal amount of 2026 Convertible Notes will mature on December 1, 2026 unless earlier converted, redeemed, or repurchased."
ELECTION = "Upon conversion of the 2026 Convertible Notes, the Company will pay or deliver, as the case may be, cash, shares of common stock or a combination of cash and shares of common stock, at the Company’s election."
PRICE = "equivalent to an initial conversion price of approximately $ 178.51 per share"
PLAN = "We plan to repurchase, repay, acquire or otherwise settle the remaining outstanding principal of our 2026 Convertible Notes by using cash on hand and cash generated from our operations."


def package(*, maturity=MATURITY, election=ELECTION, older=False, wrong_issuer=False, future=False):
    cik = "0000000001"
    accession = "0000000001-26-000001"
    url = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/quarter.htm"
    filing = FilingReference(cik="0000000002" if wrong_issuer else cik,
        accession=accession, form="10-Q", filed_date="2026-11-08" if future else "2026-11-03",
        report_date="2026-09-30", primary_document="quarter.htm", items="", url=url)
    blocks = (
        SourceBlock(locator="block-90", section="Document", text="NOTES TO CONDENSED CONSOLIDATED FINANCIAL STATEMENTS\n(in thousands, except share and per share amounts)"),
        SourceBlock(locator="table-180", section="Note 7. Debt", text="Principal | $ | 312,322", currency="USD", currency_locator="inline XBRL unitRef usd"),
        SourceBlock(locator="block-204", section="Document", text="Each $1 of principal of the 2026 Convertible Notes is " + PRICE + ", subject to adjustment."),
        SourceBlock(locator="block-205", section="Document", text=maturity + " " + election),
        SourceBlock(locator="block-430", section="Document", text=PLAN),
    )
    doc = FilingDocument(source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(),
        filing=filing, url=url, retrieved_at="2026-11-07T12:00:00Z", content_hash="a" * 64, blocks=blocks)
    documents = (doc,)
    if older:
        old = doc.model_copy(update={"filing": filing.model_copy(update={"report_date": date(2026, 6, 30), "filed_date": date(2026, 8, 3), "accession": "0000000001-26-000000"}), "blocks": blocks})
        documents = (old, doc)
    return DisclosurePackage(cik=cik, as_of="2026-11-07", documents=documents, selected_accessions=(accession,))


def test_docn_2026_notes_record_has_principal_maturity_price_election_and_plan():
    (record,) = discover_convertible_terms(package(), date(2026, 11, 7))
    assert record.name == "2026 Convertible Notes"
    assert record.principal_outstanding == Decimal("312322")
    assert record.principal_unit == "USD thousands"
    assert record.as_of == date(2026, 9, 30)
    assert record.maturity_date == date(2026, 12, 1)
    assert record.conversion_price == Decimal("178.51")
    assert "Company’s election" in record.settlement_election
    assert record.stated_plan == PLAN
    assert record.locator == "block-205"
    assert record.conversion_price_locator == "block-204"
    assert record.stated_plan_locator == "block-430"
    assert record.unit_locator == "block-90"
    assert record.content_hash == "a" * 64


def test_principal_without_maturity_yields_no_record():
    assert discover_convertible_terms(package(maturity=MATURITY.split(" will mature")[0] + "."), date(2026, 11, 7)) == ()


def test_maturity_before_as_of_yields_no_record():
    p = package().model_copy(update={"as_of": date(2027, 1, 1)})
    assert discover_convertible_terms(p, date(2027, 1, 1)) == ()


def test_2030_notes_sentence_does_not_bleed_into_2026_record():
    text = MATURITY + " Upon conversion of the 2030 Convertible Notes, the Company may settle in cash."
    (record,) = discover_convertible_terms(package(maturity=text, election=""), date(2026, 11, 7))
    assert record.settlement_election is None


def test_2030_conversion_price_in_same_block_does_not_bleed():
    p = package()
    d = p.documents[0]
    blocks = tuple(
        block.model_copy(update={"text": "The 2030 Convertible Notes have an equivalent to an initial conversion price of approximately $ 40.00 per share. The 2026 Convertible Notes remain outstanding."})
        if block.locator == "block-204" else block for block in d.blocks
    )
    p = p.model_copy(update={"documents": (d.model_copy(update={"blocks": blocks}),)})
    (record,) = discover_convertible_terms(p, date(2026, 11, 7))
    assert record.conversion_price is None


def test_mixed_note_block_does_not_take_2030_price_after_2026_mention():
    p = package()
    d = p.documents[0]
    blocks = tuple(
        block.model_copy(update={"text": "The 2026 Convertible Notes remain outstanding; the 2030 Convertible Notes have an equivalent to an initial conversion price of approximately $ 40.00 per share."})
        if block.locator == "block-204" else block for block in d.blocks
    )
    p = p.model_copy(update={"documents": (d.model_copy(update={"blocks": blocks}),)})
    (record,) = discover_convertible_terms(p, date(2026, 11, 7))
    assert record.conversion_price is None


def test_conflicting_2026_prices_omit_optional_price():
    p = package()
    d = p.documents[0]
    second = SourceBlock(locator="block-206", section="Document", text="The 2026 Convertible Notes are equivalent to an initial conversion price of approximately $ 190.00 per share.")
    p = p.model_copy(update={"documents": (d.model_copy(update={"blocks": (*d.blocks, second)}),)})
    (record,) = discover_convertible_terms(p, date(2026, 11, 7))
    assert record.conversion_price is None
    assert record.conversion_price_locator is None


def test_wrong_issuer_future_filing_and_missing_unit_are_unavailable():
    assert discover_convertible_terms(package(wrong_issuer=True), date(2026, 11, 7)) == ()
    assert discover_convertible_terms(package(future=True), date(2026, 11, 7)) == ()
    p = package()
    d = p.documents[0]
    p = p.model_copy(update={"documents": (d.model_copy(update={"blocks": d.blocks[1:]}),)})
    assert discover_convertible_terms(p, date(2026, 11, 7)) == ()


def test_latest_primary_without_maturity_does_not_fall_back_to_older_vintage():
    p = package()
    current = p.documents[0]
    older_url = current.url.replace("000000000126000001", "000000000126000000")
    older_filing = current.filing.model_copy(update={
        "accession": "0000000001-26-000000", "url": older_url,
        "filed_date": date(2026, 8, 3), "report_date": date(2026, 6, 30),
    })
    older = current.model_copy(update={
        "filing": older_filing, "url": older_url,
        "source_id": "sec-document-" + hashlib.sha256(older_url.encode()).hexdigest(),
    })
    newer_blocks = tuple(
        block.model_copy(update={"text": "No principal terms disclosed."})
        if block.locator == "block-205" else block for block in current.blocks
    )
    newer = current.model_copy(update={"blocks": newer_blocks})
    p = p.model_copy(update={
        "documents": (older, newer),
        "selected_accessions": (older_filing.accession, current.filing.accession),
    })
    assert discover_convertible_terms(p, date(2026, 11, 7)) == ()


def test_tied_latest_primary_accessions_are_ambiguous_in_either_order():
    p = package()
    first = p.documents[0]
    second_url = first.url.replace("000000000126000001", "000000000126000002")
    second_filing = first.filing.model_copy(update={
        "accession": "0000000001-26-000002", "url": second_url,
    })
    second = first.model_copy(update={
        "filing": second_filing, "url": second_url,
        "source_id": "sec-document-" + hashlib.sha256(second_url.encode()).hexdigest(),
        "content_hash": "b" * 64,
    })
    for documents in ((first, second), (second, first)):
        tied = p.model_copy(update={
            "documents": documents,
            "selected_accessions": (first.filing.accession, second_filing.accession),
        })
        assert discover_convertible_terms(tied, date(2026, 11, 7)) == ()


def test_package_cutoff_must_match_requested_as_of():
    assert discover_convertible_terms(package(), date(2026, 11, 6)) == ()


def test_conflicting_current_principal_or_truncated_unit_cannot_be_accepted():
    p = package()
    doc = p.documents[0]
    conflict = SourceBlock(locator='block-conflict', section='Document', text=MATURITY.replace('312,322', '999,999'))
    bad = p.model_copy(update={'documents': (doc.model_copy(update={'blocks': (*doc.blocks, conflict)}),)})
    assert discover_convertible_terms(bad, date(2026, 11, 7)) == ()
    blocks = (doc.blocks[0].model_copy(update={'truncated': True}), *doc.blocks[1:])
    bad = p.model_copy(update={'documents': (doc.model_copy(update={'blocks': blocks}),)})
    assert discover_convertible_terms(bad, date(2026, 11, 7)) == ()
