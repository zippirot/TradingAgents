"""Plan L4: an Item 4.02 non-reliance notice is always selected, and a retrieved one changes the verdict."""
from datetime import UTC, date, datetime
from decimal import Decimal

from tests.test_sec_documents import submissions
from tradingagents.agents.evidence_validation import disclosure_coverage_check
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord
from tradingagents.dataflows.vendors import sec_documents as docs

CIK, CUT, END = "0001582961", date(2026, 10, 19), date(2026, 6, 30)


def _with(*rows):
    data = submissions()
    recent = {key: list(values) for key, values in data["filings"]["recent"].items()}
    for row in rows:
        for key, value in zip(("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument", "items"), row, strict=True):
            recent[key].append(value)
    data["filings"]["recent"] = recent
    return data


NOTICE = ("8-K", "2026-09-10", "2026-09-10", "0001582961-26-000009", "notice.htm", "4.02")


def test_a_non_reliance_notice_is_selected_and_survives_the_filing_limit():
    chosen, gaps = docs.select_filings(_with(NOTICE), CIK, str(CUT))
    assert "notice.htm" in [f.primary_document for f in chosen] and not gaps
    noise = [("8-K", f"2026-09-{day:02d}", f"2026-09-{day:02d}", f"0001582961-26-0001{day:02d}", f"other{day}.htm", "8.01")
             for day in range(11, 19)]
    crowded, gaps = docs.select_filings(_with(NOTICE, *noise), CIK, str(CUT))
    assert "notice.htm" in [f.primary_document for f in crowded] and len(crowded) == 6
    assert not any("non-reliance" in gap for gap in gaps)


def test_events_left_out_by_item_code_are_accounted_for_by_name():
    votes = ("8-K", "2026-09-12", "2026-09-12", "0001582961-26-000010", "votes.htm", "5.07")
    chosen, _ = docs.select_filings(_with(votes), CIK, str(CUT))
    left = docs.unselected_events(_with(votes), CIK, str(CUT), chosen)
    assert left == ["0001582961-26-000010 8-K items 5.07 filed 2026-09-12: not selected; item codes outside "
                    "earnings, financing, agreements, other events and non-reliance"]
    assert docs.unselected_events(submissions(), CIK, str(CUT), docs.select_filings(submissions(), CIK, str(CUT))[0]) == []


def _evidence():
    fact = FinancialFact(fact_id="a", metric="Total Assets", value=Decimal(1), unit="USD", cik=CIK, period_end=END,
                         as_of=CUT, source_ids=("s",), locator="x")
    source = SourceRecord(source_id="s", cik=CIK, url="https://data.sec.gov/x", filed_date=date(2026, 8, 5),
                          retrieved_at=datetime(2026, 10, 19, tzinfo=UTC), content_hash="0" * 64, locator="x", form="10-Q")
    return EvidencePackage(cik=CIK, as_of=CUT, facts=(fact,), sources=(source,))


def _document(form, filed, report, accession, items="", blocks=True):
    filing = docs.FilingReference(cik=CIK, accession=accession, form=form, filed_date=filed, report_date=report,
                                  primary_document="d.htm", items=items,
                                  url=f"https://www.sec.gov/Archives/edgar/data/1582961/{accession.replace('-', '')}/d.htm")
    block = docs.SourceBlock(locator="block-1", section="Cover", text="text") if blocks else None
    return docs.FilingDocument(source_id="sec-document-" + accession, filing=filing, url=filing.url,
                               retrieved_at=datetime(2026, 10, 19, tzinfo=UTC), content_hash="0" * 64,
                               blocks=(block,) if block else ())


def _coverage(*documents):
    package = docs.DisclosurePackage(cik=CIK, as_of=CUT, documents=documents)
    return disclosure_coverage_check(_evidence(), package)


QUARTER = ("10-Q", date(2026, 8, 5), END, "0001582961-26-000002")


def test_a_retrieved_notice_after_the_scored_filing_stops_the_check():
    assert _coverage(_document(*QUARTER))["status"] == "pass"
    notice = _document("8-K", date(2026, 9, 10), date(2026, 9, 10), "0001582961-26-000009", "4.02")
    blocked = _coverage(_document(*QUARTER), notice)
    assert blocked["status"] == "unavailable"
    assert "0001582961-26-000009" in blocked["message"] and "Item 4.02" in blocked["message"] and "10-Q for 2026-06-30" in blocked["message"]
    # An amendment on file does not clear it while the scored figures still come from the original report;
    # the clearing case is in tests/test_large_filer_audit_closure.py (audit F1).
    amended = _document("10-Q/A", date(2026, 9, 25), END, "0001582961-26-000011")
    assert _coverage(_document(*QUARTER), notice, amended)["status"] == "unavailable"


def test_a_notice_issued_before_the_scored_filing_cannot_cover_it():
    earlier = _document("8-K", date(2026, 7, 15), date(2026, 7, 15), "0001582961-26-000008", "4.02")
    assert _coverage(_document(*QUARTER), earlier)["status"] == "pass"


def test_a_filing_recorded_with_no_excerpt_is_covered_and_one_left_out_is_not():
    late = _document("8-K", date(2026, 9, 1), date(2026, 9, 1), "0001582961-26-000004", "8.01", blocks=False)
    package = docs.DisclosurePackage(cik=CIK, as_of=CUT, documents=(_document(*QUARTER), late), gaps=(
        "0001582961-26-000004: Document text limit reached; package text limit 120000 reached; retrieved and recorded "
        "with no excerpt (model package only; extraction and search read the full filing)",))
    assert disclosure_coverage_check(_evidence(), package)["status"] == "pass"
    dropped = package.model_copy(update={"gaps": ("Document count limit reached; coverage incomplete",)})
    assert disclosure_coverage_check(_evidence(), dropped)["status"] == "unavailable"
