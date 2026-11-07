"""Supplemental acquisition uses trusted retained URLs and a local fake transport."""
import hashlib
from copy import deepcopy
from unittest.mock import Mock

from tests.test_filing_facts import package
from tradingagents.ground_truth import _source_index
from tradingagents.ground_truth_sources import acquire_sources


def source_state():
    retained = package("Revenue | 10", section="Statement").model_dump(mode="json")
    retained["as_of"] = "2026-11-06"
    retained["documents"][0]["blocks"][0]["truncated"] = True
    return {"run_id": "run-1", "company_of_interest": "DOCN", "trade_date": "2026-11-06",
            "issuer_identity": {"cik": "0001582961"}, "filing_evidence": retained}


def fake_transport(monkeypatch):
    from tradingagents.dataflows.vendors import sec_documents
    body = "<h2>Income statement</h2><p>Revenue was 123 million USD.</p>"
    client = Mock()
    client.requests = 0
    def fetch(url):
        client.requests += 1
        return {"url": url, "text": body, "content_hash": hashlib.sha256(body.encode()).hexdigest(),
                "retrieved_at": "2026-11-07T00:00:00Z"}
    client.fetch.side_effect = fetch
    constructor = Mock(return_value=client)
    monkeypatch.setattr(sec_documents, "DocumentClient", constructor)
    return constructor, client


def test_disabled_or_frozen_path_never_creates_transport(monkeypatch):
    constructor, client = fake_transport(monkeypatch)
    assert acquire_sources(source_state(), {}) == {}
    frozen = {**source_state(), "publication_record": {"decision_id": "frozen"}}
    assert acquire_sources(frozen, {"ground_truth_audit": True}) == {}
    constructor.assert_not_called()
    client.fetch.assert_not_called()


def test_trusted_fetch_is_bounded_and_preserved_for_offline_replay(monkeypatch):
    constructor, client = fake_transport(monkeypatch)
    original = source_state()
    prior = deepcopy(original)
    update = acquire_sources(original, {"ground_truth_audit": True})
    assert original == prior
    constructor.assert_called_once_with(max_bytes=2_500_000, max_requests=2, max_seconds=30)
    assert client.fetch.call_count == 1
    docs = update["ground_truth_source_documents"]
    assert len(docs) == 1 and "123 million" in str(docs[0]["blocks"])
    assert docs[0]["source_id"].startswith("ground-truth-sec-")
    merged = {**original, **update}
    assert any(key[0] == docs[0]["source_id"] for key in _source_index(merged)[0])
    again = acquire_sources(merged, {"ground_truth_audit": True})
    assert again == update
    assert client.fetch.call_count == 1


def test_foreign_or_untrusted_sources_and_intraday_unknown_are_rejected(monkeypatch):
    constructor, client = fake_transport(monkeypatch)
    for change in ("foreign", "untrusted", "cutoff"):
        s = source_state()
        doc = s["filing_evidence"]["documents"][0]
        if change == "foreign":
            doc["filing"]["cik"] = "0000000001"
        elif change == "untrusted":
            doc["url"] = "https://example.invalid/filing.htm"
        else:
            doc["filing"]["filed_date"] = "2026-11-06"
            s["analysis_clock"] = {"cutoff_utc": "2026-11-06T01:00:00Z"}
        result = acquire_sources(s, {"ground_truth_audit": True})
        assert not result["ground_truth_source_documents"]
        assert result["ground_truth_source_acquisition"]["limits"]
    constructor.assert_not_called()
    client.fetch.assert_not_called()


def test_only_two_newest_candidates_can_fetch_and_failures_are_visible(monkeypatch):
    _, client = fake_transport(monkeypatch)
    s = source_state()
    doc = s["filing_evidence"]["documents"][0]
    docs = []
    for number in range(4):
        new = deepcopy(doc)
        new["source_id"] = f"retained-{number}"
        new["url"] = new["url"].replace("filing.htm", f"filing{number}.htm")
        new["filing"]["filed_date"] = f"2026-08-{number + 1:02d}"
        docs.append(new)
    s["filing_evidence"]["documents"] = docs
    client.fetch.side_effect = RuntimeError("secret provider response")
    result = acquire_sources(s, {"ground_truth_audit": True})
    assert client.fetch.call_count == 2
    record = result["ground_truth_source_acquisition"]
    assert record["status"] == "unavailable"
    assert record["limits"] and record["error_categories"]
    assert "secret" not in str(result)


def test_supplemental_fetch_respects_fractional_and_exhausted_remaining_deadline(monkeypatch):
    constructor, client = fake_transport(monkeypatch)
    result = acquire_sources(source_state(), {"ground_truth_audit": True, "ground_truth_max_seconds": 0})
    constructor.assert_not_called()
    assert result["ground_truth_source_acquisition"]["status"] == "unavailable"
    assert result["ground_truth_source_acquisition"]["requests"] == 0
    result = acquire_sources(source_state(), {"ground_truth_audit": True, "ground_truth_max_seconds": 0.5})
    assert constructor.call_args.kwargs["max_seconds"] == 0.5
    assert client.fetch.call_count == 1
    assert result["ground_truth_source_acquisition"]["bounds"]["max_seconds"] == 0.5
