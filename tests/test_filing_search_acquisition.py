import hashlib
import json

from tradingagents.dataflows.vendors import sec_documents as docs


def submissions():
    rows = [
        ("10-K", "2026-02-20", "2025-12-31", "0001582961-26-000001", "annual.htm", ""),
        ("10-Q", "2026-08-05", "2026-06-30", "0001582961-26-000002", "quarter.htm", ""),
        ("8-K", "2026-08-05", "2026-08-05", "0001582961-26-000003", "earnings.htm", "2.02"),
        ("8-K", "2026-09-01", "2026-09-01", "0001582961-26-000004", "financing.htm", "2.03"),
        ("10-Q", "2026-11-05", "2026-09-30", "0001582961-26-000005", "future.htm", ""),
    ]
    names = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument", "items")
    return {"cik": "0001582961", "filings": {"recent": dict(zip(names, zip(*rows, strict=True), strict=True)), "files": []}}



def expanded_submissions():
    data = submissions()
    recent = {key: list(value) for key, value in data["filings"]["recent"].items()}
    additions = [
        ("10-Q", "2026-05-05", "2026-03-31", "0001582961-26-000006", "prior.htm", ""),
        ("424B5", "2026-10-28", "2026-10-28", "0001582961-26-000007", "prospectus.htm", ""),
        ("8-K", "2026-11-02", "2026-11-02", "0001582961-26-000008", "atm.htm", "1.01"),
    ]
    for row in additions:
        for key, value in zip(recent, row, strict=True):
            recent[key].append(value)
    data["filings"]["recent"] = recent
    return data


def test_search_selection_has_prior_quarter_prospectus_and_report_period_events():
    chosen, gaps = docs.select_search_filings(
        expanded_submissions(), "0001582961", "2026-11-06"
    )
    names = {filing.primary_document for filing in chosen}
    assert {"annual.htm", "quarter.htm", "future.htm", "prospectus.htm", "atm.htm"} <= names
    assert not gaps
    # Nov 2 event precedes Nov 5 filing but follows Sep 30 report period.
    assert "atm.htm" in names


def test_full_acquisition_keeps_late_blocks_and_pins_bounded_hash(monkeypatch):
    data = expanded_submissions()
    monkeypatch.setattr(docs, "cik_for", lambda _: "0001582961")
    html = "<h2>Other</h2>" + ("<p>" + "x" * 120 + "</p>") * 600 + "<h2>Leases</h2><p>Not-yet-started capacity.</p>"
    seen = []

    def fetch(self, url):
        seen.append(url)
        text = json.dumps(data) if "submissions" in url else html
        return {
            "text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "retrieved_at": "2026-11-06T00:00:00+00:00", "url": url,
        }

    monkeypatch.setattr(docs.DocumentClient, "fetch", fetch)
    bounded = docs.get_filing_evidence("DOCN", "2026-11-06")
    full = docs.get_filing_search_evidence(
        "DOCN", "2026-11-06", bounded_package=bounded,
    )
    assert full is not bounded
    assert any("Not-yet-started capacity" in b.text for d in full.documents for b in d.blocks)
    assert {d.content_hash for d in full.documents} == {hashlib.sha256(html.encode()).hexdigest()}
    assert all(d.filing.filed_date <= full.as_of for d in full.documents)
    assert len(full.documents) > len(bounded.documents)
    matching = next(d for d in full.documents if d.url == bounded.documents[0].url)
    assert len(matching.blocks) > len(bounded.documents[0].blocks)


def test_changed_bounded_source_is_rejected(monkeypatch):
    data = submissions()
    monkeypatch.setattr(docs, "cik_for", lambda _: "0001582961")
    changed = False

    def fetch(self, url):
        text = json.dumps(data) if "submissions" in url else ("<p>changed</p>" if changed else "<p>original</p>")
        return {
            "text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "retrieved_at": "2026-11-06T00:00:00+00:00", "url": url,
        }

    monkeypatch.setattr(docs.DocumentClient, "fetch", fetch)
    bounded = docs.get_filing_evidence("DOCN", "2026-10-19")
    changed = True
    full = docs.get_filing_search_evidence("DOCN", "2026-10-19", bounded_package=bounded)
    assert not any(d.url in {b.url for b in bounded.documents} for d in full.documents)
    assert any("content changed" in gap for gap in full.gaps)


def test_selection_limit_lists_each_omitted_accession_and_url():
    chosen, gaps = docs.select_search_filings(expanded_submissions(), "0001582961", "2026-11-06", limit=3)
    omitted = "0001582961-26-000007"
    assert len(chosen) == 3
    assert any(omitted in gap and "https://" in gap for gap in gaps)

def test_search_selection_excludes_future_prospectus_and_filing():
    chosen, _ = docs.select_search_filings(expanded_submissions(), "0001582961", "2026-10-19")
    names = {filing.primary_document for filing in chosen}
    assert "prospectus.htm" not in names
    assert "atm.htm" not in names
    assert "future.htm" not in names
    assert "quarter.htm" in names

def test_exhibit_limit_reports_each_omitted_url(monkeypatch):
    monkeypatch.setattr(docs, "cik_for", lambda _: "0001582961")
    data = submissions()
    links = "".join(f'<a href="ex99{i}.htm">Exhibit 99.{i}</a>' for i in range(1, 7))
    fetched = []

    def fetch(self, url):
        fetched.append(url)
        text = json.dumps(data) if "submissions" in url else (
            links if url.endswith(("earnings.htm", "financing.htm")) else "<p>Exhibit text.</p>"
        )
        return {
            "text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "retrieved_at": "2026-10-19T00:00:00+00:00", "url": url,
        }

    monkeypatch.setattr(docs.DocumentClient, "fetch", fetch)
    package = docs.get_filing_search_evidence("DOCN", "2026-10-19")
    assert any("ex995.htm" in gap and "0001582961-26-000003" in gap for gap in package.gaps)
    assert any("ex996.htm" in gap and "0001582961-26-000003" in gap for gap in package.gaps)
    assert not any(url.endswith("ex995.htm") for url in fetched)

def test_unsupported_exhibit_link_is_explicit_gap(monkeypatch):
    monkeypatch.setattr(docs, "cik_for", lambda _: "0001582961")
    data = submissions()

    def fetch(self, url):
        text = json.dumps(data) if "submissions" in url else (
            '<a href="ex991.pdf">Exhibit 99.1</a>' if url.endswith("earnings.htm")
            else "<p>Filing text.</p>"
        )
        return {
            "text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "retrieved_at": "2026-10-19T00:00:00+00:00", "url": url,
        }

    monkeypatch.setattr(docs.DocumentClient, "fetch", fetch)
    package = docs.get_filing_search_evidence("DOCN", "2026-10-19")
    assert any(
        "0001582961-26-000003" in gap and "ex991.pdf" in gap
        for gap in package.gaps
    )


def test_full_search_streams_large_issuer_filing_under_its_own_finite_byte_budget(monkeypatch, tmp_path):
    metadata = {"cik": "0001582961", "filings": {"files": [], "recent": {
        "form": ["10-Q"], "filingDate": ["2026-08-05"], "reportDate": ["2026-06-30"],
        "accessionNumber": ["0001582961-26-000002"], "primaryDocument": ["large.htm"], "items": [""],
    }}}
    # JPM's retained annual filing is 12,927,444 UTF-8 bytes. Exercise the real
    # streaming reader above that observed size, not a stub bypassing its cap.
    body = ("<!--" + " " * 12_927_444 + "--><p>Capacity commitment retained.</p>").encode()
    monkeypatch.setattr(docs, "cik_for", lambda _: "0001582961")
    monkeypatch.setattr(docs, "_user_agent", lambda: "fixture@example.invalid")
    monkeypatch.setattr(docs, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    class Response:
        status_code = 200
        def __init__(self, raw):
            self.raw = raw
        def raise_for_status(self):
            pass
        def iter_content(self, chunk_size):
            for i in range(0, len(self.raw), chunk_size):
                yield self.raw[i:i + chunk_size]
        def close(self):
            pass
    monkeypatch.setattr(docs.requests, "get", lambda url, **kwargs:
        Response(json.dumps(metadata).encode() if "submissions" in url else body))
    full = docs.get_filing_search_evidence("JPM", "2026-11-06")
    assert len(full.documents) == 1
    assert any("Capacity commitment retained" in block.text for block in full.documents[0].blocks)
    # The bounded brief can transport a large primary while retaining its
    # separate 40k-document and 120k-package extracted-text limits.
    bounded = docs.get_filing_evidence("JPM", "2026-11-06")
    assert len(bounded.documents) == 1
    assert any("Capacity commitment retained" in block.text for block in bounded.documents[0].blocks)
    assert sum(len(block.text) for doc in bounded.documents for block in doc.blocks) <= 120_000
    import pytest

    from tradingagents.dataflows.errors import VendorUnavailableError

    with pytest.raises(VendorUnavailableError, match="byte limit"):
        monkeypatch.setattr(docs.requests, "get", lambda *a, **k: Response(b"x" * 16_000_001))
        docs.DocumentClient(max_bytes=16_000_000).fetch(
            "https://www.sec.gov/Archives/edgar/data/1582961/000158296126000002/too-big.htm"
        )


def test_prior_quarter_rpo_transport_accepts_large_primary_with_bounded_extraction(
    monkeypatch, tmp_path,
):
    metadata = {"cik": "0001582961", "filings": {"files": [], "recent": {
        "form": ["10-Q", "10-Q"],
        "filingDate": ["2026-10-28", "2026-08-05"],
        "reportDate": ["2026-09-30", "2026-06-30"],
        "accessionNumber": ["0001582961-26-000003", "0001582961-26-000002"],
        "primaryDocument": ["current.htm", "prior.htm"],
        "items": ["", ""],
    }}}
    body = ("<!--" + " " * 2_600_000 + "--><p>Remaining performance obligations were $123 million.</p>").encode()
    monkeypatch.setattr(docs, "cik_for", lambda _: "0001582961")
    monkeypatch.setattr(docs, "_user_agent", lambda: "fixture@example.invalid")
    monkeypatch.setattr(docs, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    calls = []

    class Response:
        status_code = 200

        def __init__(self, raw):
            self.raw = raw

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            for start in range(0, len(self.raw), chunk_size):
                yield self.raw[start:start + chunk_size]

        def close(self):
            pass

    def get(url, **kwargs):
        calls.append(url)
        return Response(json.dumps(metadata).encode() if "submissions" in url else body)

    monkeypatch.setattr(docs.requests, "get", get)
    package = docs.get_prior_quarter_evidence("DOCN", "2026-11-06", "2026-09-30")
    assert len(package.documents) == 1
    assert package.documents[0].filing.report_date.isoformat() == "2026-06-30"
    assert any("Remaining performance obligations" in block.text
               for block in package.documents[0].blocks)
    assert sum(len(block.text) for block in package.documents[0].blocks) <= 40_000
    assert len(calls) == 2
