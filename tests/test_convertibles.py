"""Every outstanding convertible note is read from the filing by code, whatever year it carries."""
import hashlib
from datetime import date

from tradingagents.dataflows.convertibles import discover_convertibles
from tradingagents.dataflows.vendors.sec_documents import (
    DisclosurePackage,
    FilingDocument,
    FilingReference,
    SourceBlock,
)

HEAD = "NOTES TO CONDENSED CONSOLIDATED FINANCIAL STATEMENTS\n(in thousands, except share and per share amounts)"
TABLE = ("| | | ; | Initial Conversion Rate per $1,000 Principal | | Initial Conversion Price (In whole $) | | "
         "Initial Number of Shares (In thousands) ; 2030 Convertible Notes | 25.5317 | | $ | 39.17 | | | 15,957")
MET = ("During the three months ended September 30, 2026, the circumstances allowing holders to convert the 2030 "
       "Convertible Notes were met since the last reported sale price exceeded 130% of the conversion price of $39.17 "
       "for each of at least 20 trading days. Therefore, the 2030 Convertible Notes have been convertible since April 1, 2026.")
LEFT = "As of September 30, 2026, $153,172 aggregate principal amount of the 2030 Convertible Notes remained outstanding with a maturity date of August 15, 2030."
CALLS = ("In connection with the issuance of the 2030 Convertible Notes, the Company entered into capped call transactions "
         "(“2030 Capped Calls”). The 2030 Capped Calls have an initial strike price of $39.17 per share, which corresponds "
         "to the initial conversion price of the 2030 Convertible Notes. The 2030 Capped Calls have an initial cap price of "
         "$66.51 per share. The 2030 Capped Calls expire on August 15, 2030, unless exercised or called prior to that date.")
OLD = ("Each $1 of principal of the 2026 Convertible Notes will initially be convertible into 5.6018 shares, which is "
       "equivalent to an initial conversion price of approximately $178.51 per share, subject to adjustment as set forth "
       "in the indenture governing the 2026 Convertible Notes.")
OLD_LEFT = "The outstanding $312,322 of aggregate principal amount of 2026 Convertible Notes will mature on December 1, 2026 unless earlier converted, redeemed, or repurchased."


def package(*texts, head=HEAD):
    cik, accession = "0000000001", "0000000001-26-000001"
    url = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/quarter.htm"
    filing = FilingReference(cik=cik, accession=accession, form="10-Q", filed_date="2026-11-03",
                             report_date="2026-09-30", primary_document="quarter.htm", items="", url=url)
    blocks = [SourceBlock(locator="block-90", section="Document", text=head),
              SourceBlock(locator="table-91", section="Debt", text="Principal | $ | 1", currency="USD",
                          currency_locator="inline XBRL unitRef usd")]
    blocks += [SourceBlock(locator=f"block-{100 + i}", section="Document", text=text) for i, text in enumerate(texts)]
    doc = FilingDocument(source_id="sec-document-" + hashlib.sha256(url.encode()).hexdigest(), filing=filing, url=url,
                         retrieved_at="2026-11-07T12:00:00Z", content_hash="a" * 64, blocks=tuple(blocks))
    return DisclosurePackage(cik=cik, as_of="2026-11-07", documents=(doc,), selected_accessions=(accession,))


def read(*texts, **kw):
    return discover_convertibles(package(*texts, **kw), date(2026, 11, 7))


def test_both_notes_are_read_with_their_own_terms_and_the_capped_call_stays_with_its_note():
    old, new = read(TABLE, MET, LEFT, CALLS, OLD, OLD_LEFT)
    assert (old["name"], old["principal"], old["maturity_date"], old["conversion_price"]) == (
        "2026 Convertible Notes", "312322000", "2026-12-01", "178.51")
    assert old["capped_call"] is None
    assert (new["name"], new["principal"], new["maturity_date"], new["conversion_price"]) == (
        "2030 Convertible Notes", "153172000", "2030-08-15", "39.17")
    assert new["conversion_rate"] == "25.5317" and old["conversion_rate"] is None
    assert new["capped_call"] == {"strike": "39.17", "cap": "66.51", "expires": "2030-08-15", "locator": "block-103"}
    assert new["locator"] == "block-102" and new["as_of"] == "2026-09-30"


def test_a_note_named_for_any_year_is_read_the_same_way():
    text = (LEFT + " " + MET).replace("2030 Convertible", "2031 Convertible").replace("$39.17", "$12.50")
    (note,) = read(text)
    assert (note["name"], note["conversion_price"], note["capped_call"]) == ("2031 Convertible Notes", "12.50", None)


def test_a_term_stated_two_ways_is_left_out_not_chosen():
    (note,) = read(LEFT, MET, MET.replace("$39.17", "$41.00"), CALLS)
    assert note["conversion_price"] is None and note["capped_call"] is None
    assert read(LEFT, LEFT.replace("153,172", "150,000")) == []


def test_a_capped_call_with_another_strike_is_not_treated_as_the_notes_offset():
    (note,) = read(LEFT, MET, CALLS.replace("strike price of $39.17", "strike price of $45.00"))
    assert note["conversion_price"] == "39.17" and note["capped_call"] is None


def test_a_matured_note_a_missing_scale_and_a_company_without_notes_give_nothing():
    assert read(OLD_LEFT.replace("December 1, 2026", "June 1, 2026")) == []
    assert read(LEFT, MET, head="NOTES TO CONDENSED CONSOLIDATED FINANCIAL STATEMENTS") == []
    assert read("The Company has no debt outstanding.") == []
