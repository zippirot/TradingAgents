"""A filer whose recent filing list has no annual report (Exxon files hundreds of other forms a year).

SEC splits a long filing history into a recent list and older archive files. When the recent list holds no
10-K filed by the analysis date, the older files are read, newest first, until one does.
"""
import json

from tradingagents.dataflows.vendors.sec_documents import with_older_annual

CIK = "0000034088"
COLUMNS = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument", "items")


def _columns(rows):
    return {name: [row[i] for row in rows] for i, name in enumerate(COLUMNS)}


def _submissions(rows, files=()):
    return {"cik": CIK, "filings": {"recent": _columns(rows), "files": [{"name": name} for name in files]}}


class _Client:
    def __init__(self, archives):
        self.archives, self.asked = archives, []

    def fetch(self, url):
        self.asked.append(url)
        return {"text": json.dumps(self.archives[url.rsplit("/", 1)[-1]])}


Q = ("10-Q", "2026-10-30", "2026-09-30", "0000034088-26-000090", "q.htm", "")
K = ("10-K", "2026-02-18", "2025-12-31", "0000034088-26-000010", "k.htm", "")
OLD = ("8-K", "2025-11-01", "2025-11-01", "0000034088-25-000070", "e.htm", "8.01")


def test_older_archives_are_read_until_an_annual_report_is_found():
    client = _Client({"a-001.json": _columns([OLD]), "a-002.json": _columns([K]), "a-003.json": _columns([OLD])})
    merged = with_older_annual(client, _submissions([Q], ("a-001.json", "a-002.json", "a-003.json")), "2026-11-11")
    assert merged["filings"]["recent"]["form"] == ["10-Q", "8-K", "10-K"]
    assert [url.rsplit("/", 1)[-1] for url in client.asked] == ["a-001.json", "a-002.json"]     # stops once found
    assert client.asked[0] == "https://data.sec.gov/submissions/a-001.json"


def test_nothing_is_fetched_when_the_recent_list_already_has_one_or_there_is_no_archive():
    client = _Client({})
    with_annual = _submissions([Q, K], ("a-001.json",))
    assert with_older_annual(client, with_annual, "2026-11-11") is with_annual
    bare = _submissions([Q])
    assert with_older_annual(client, bare, "2026-11-11") is bare and client.asked == []
    # A 10-K filed after the analysis date does not count as having one.
    later = _submissions([Q, ("10-K", "2026-12-01", "2026-09-30", "x", "k.htm", "")], ("a-001.json",))
    client = _Client({"a-001.json": _columns([K])})
    assert with_older_annual(client, later, "2026-11-11")["filings"]["recent"]["form"][-1] == "10-K" and client.asked


def test_a_debt_tag_stated_in_several_currencies_gives_nothing_and_no_longer_stops_the_whole_read(monkeypatch, tmp_path):
    # PepsiCo tags current long-term debt in USD, EUR and CAD at one date: a breakdown by currency, not a total.
    import pytest

    from tests.test_sec_income_bridge import _cat_excerpt, _package, _row
    from tradingagents.dataflows.errors import VendorUnavailableError

    def instant(value):
        return {key: item for key, item in _row(None, value).items() if key != "start"}

    data = _cat_excerpt()
    data["facts"]["us-gaap"]["LongTermDebtCurrent"] = {"units": {"USD": [instant(13)], "EUR": [instant(10)]}}
    package = _package(monkeypatch, tmp_path, data)
    assert not any(f.metric == "Current Long-term Borrowings" and f.value is not None for f in package.facts)
    assert "Current Long-term Borrowings ambiguous at 2026-09-30; tag not used" in package.warnings
    # A core figure stated in two currencies still stops the read.
    data["facts"]["us-gaap"]["ProfitLoss"]["units"]["EUR"] = data["facts"]["us-gaap"]["ProfitLoss"]["units"]["USD"]
    with pytest.raises(VendorUnavailableError, match="ambiguous"):
        _package(monkeypatch, tmp_path, data)
