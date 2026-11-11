"""Cohort eligibility and split are mechanical and reproducible."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "large_filer_cohort", Path(__file__).resolve().parents[1] / "scripts" / "large_filer_cohort.py")
cohort = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cohort)

ONE = b'<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" contextRef="c-3" unitRef="shares">7</ix:nonFraction>'
TWO = ONE + ONE.replace(b"c-3", b"c-4")


def _submissions(sic="7372", forms=("8-K", "10-Q", "10-K"), dates=("2026-11-05", "2026-10-28", "2026-07-30")):
    return {"cik": "789019", "sic": sic, "filings": {"recent": {
        "form": list(forms), "filingDate": list(dates), "accessionNumber": [f"0000000000-26-00000{i}" for i in range(len(forms))],
        "primaryDocument": [f"d{i}.htm" for i in range(len(forms))], "reportDate": ["", "2026-09-30", "2026-06-30"]}}}


def test_one_cover_share_count_in_the_latest_periodic_report_is_eligible():
    asked = []
    decision = cohort.assess(_submissions(), "2026-11-11", lambda url: asked.append(url) or ONE)
    assert decision["eligible"] and decision["form"] == "10-Q" and decision["cover_share_counts"] == 1
    assert asked == ["https://www.sec.gov/Archives/edgar/data/789019/000000000026000001/d1.htm"]
    # The same count repeated in one context is still one class.
    assert cohort.cover_classes(ONE + ONE) == 1


def test_financials_foreign_filers_multiple_classes_and_unknowns_are_skipped_with_a_reason():
    def fetch(_url):
        raise AssertionError("no filing is opened when metadata already decides")
    assert "financial" in cohort.assess(_submissions(sic="6021"), "2026-11-11", fetch)["basis"]
    assert cohort.assess(_submissions(sic=""), "2026-11-11", fetch)["basis"] == "SIC unknown"
    assert not cohort.assess(_submissions(forms=("20-F", "6-K", "10-K")), "2026-11-11", fetch)["eligible"]
    assert not cohort.assess(_submissions(forms=("8-K", "10-K", "10-K")), "2026-11-11", fetch)["eligible"]
    assert "more than one class" in cohort.assess(_submissions(), "2026-11-11", lambda _u: TWO)["basis"]
    assert "ambiguous" in cohort.assess(_submissions(), "2026-11-11", lambda _u: b"<html/>")["basis"]
    # A report filed after the cutoff is not the basis.
    assert cohort.assess(_submissions(), "2026-10-01", lambda _u: ONE)["form"] == "10-K"


def test_the_split_puts_named_anchors_in_development_and_fills_by_salted_hash():
    tickers = ["NVDA", "AAPL", "MSFT", "WMT", "XOM", "ORCL", "COST", "HD", "PG", "JNJ", "CAT", "KO", "PEP"]
    development, held_out = cohort.split(tickers, {t: i for i, t in enumerate(tickers)})
    assert development[:3] == ["MSFT", "CAT", "WMT"] and len(development) == 10 and len(held_out) == 3
    assert not set(development) & set(held_out)
    assert cohort.split(tickers, {t: i for i, t in enumerate(tickers)}) == (development, held_out)
