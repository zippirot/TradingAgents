"""Source-compatible earnings expectations and aligned observed price windows."""

import hashlib
from copy import deepcopy

import pytest

from tradingagents.agents import event_comparison as events
from tradingagents.dataflows.vendors.yahoo import price_observation as prices

CONFIG = {"data_vendors": {"core_stock_apis": "yfinance"}}


def state():
    documents = []
    sources = []
    for day, accession, text in [
        (
            "2026-08-03",
            "0001582961-26-000001",
            "US-GAAP Revenue guidance is 90 to 100 million USD for 2026-07-01 to 2026-09-30.",
        ),
        ("2026-11-03", "0001582961-26-000002", "Third quarter results."),
    ]:
        url = f"https://www.sec.gov/Archives/edgar/data/1582961/{accession.replace('-', '')}/release.htm"
        ident = "sec-document-" + hashlib.sha256(url.encode()).hexdigest()
        digest = hashlib.sha256(text.encode()).hexdigest()
        filing = {
            "cik": "0001582961",
            "accession": accession,
            "form": "8-K",
            "filed_date": day,
            "report_date": day,
            "primary_document": "release.htm",
            "items": "2.02",
            "url": url,
        }
        documents.append(
            {
                "source_id": ident,
                "filing": filing,
                "url": url,
                "retrieved_at": "2026-11-04T22:00:00Z",
                "content_hash": digest,
                "blocks": [{"locator": "block-1", "section": "Earnings", "text": text}],
            }
        )
        sources.append(
            {
                "source_id": ident,
                "cik": "0001582961",
                "url": url,
                "filed_date": day,
                "retrieved_at": "2026-11-04T22:00:00Z",
                "content_hash": digest,
                "locator": "document",
                "accession": accession,
                "form": "8-K",
            }
        )
    claim = {
        "source_id": documents[0]["source_id"],
        "locator": "block-1",
        "metric": "Revenue",
        "value": "90",
        "upper_value": "100",
        "unit": "million USD",
        "period": "2026-07-01 to 2026-09-30",
        "kind": "guidance",
        "quote": documents[0]["blocks"][0]["text"],
    }
    fact = {
        "fact_id": "actual",
        "metric": "Revenue",
        "value": "110000000",
        "unit": "USD",
        "basis": "US-GAAP",
        "cik": "0001582961",
        "as_of": "2026-11-04",
        "period_start": "2026-07-01",
        "period_end": "2026-09-30",
        "source_ids": [sources[1]["source_id"]],
        "locator": "release-result",
    }
    return {
        "company_of_interest": "DOCN",
        "issuer_identity": {
            "ticker": "DOCN",
            "cik": "0001582961",
            "as_of": "2026-11-04",
            "source": "SEC issuer map",
        },
        "trade_date": "2026-11-04",
        "evidence_quality": {"status": "limited"},
        "financial_evidence": {
            "cik": "0001582961",
            "as_of": "2026-11-04",
            "facts": [fact],
            "sources": sources,
        },
        "filing_evidence": {
            "cik": "0001582961",
            "as_of": "2026-11-04",
            "documents": documents,
            "selected_accessions": [d["filing"]["accession"] for d in documents],
        },
        "disclosure_evidence": {"extraction": {"claims": [claim]}},
    }


def price(ticker, before="100", after="90", dates=("2026-11-02", "2026-11-04")):
    raw = {
        "ticker": ticker,
        "as_of": "2026-11-04",
        "capital_snapshot_date": "2026-10-27",
        "retrieved_at": "2026-11-04T22:00:00+00:00",
        "history_start": "2026-10-20",
        "history_end_exclusive": "2026-11-05",
        "auto_adjust": False,
        "actions": True,
        "interval": "1d",
        "adjustment_verification": None,
        "metadata": {
            "symbol": ticker,
            "currency": "USD",
            "exchangeTimezoneName": "America/New_York",
            "regular_end": "2026-11-04T21:00:00+00:00",
        },
        "bars": [
            {"timestamp": day + "T00:00:00-05:00", "close": value, "stock_splits": "0"}
            for day, value in zip(dates, (before, after), strict=True)
        ],
    }
    return prices._project(raw)


def install(monkeypatch, records=None):
    records = records or {
        "DOCN": price("DOCN"),
        "SPY": price("SPY", after="102"),
        "AKAM": price("AKAM", after="101"),
    }
    calls = []
    monkeypatch.setattr(
        events,
        "get_price_observation",
        lambda ticker, *args: calls.append(ticker) or records[ticker],
    )
    return calls


def test_beat_guidance_can_coexist_with_negative_observed_window(monkeypatch):
    calls = install(monkeypatch)
    result = events.prepare_event_comparison(state(), CONFIG)
    assert result["guidance"]["rows"][0]["position"] == "above_range"
    assert result["guidance"]["rows"][0]["difference_from_upper"] == "10000000"
    assert result["reaction"]["returns"]["DOCN"]["percent"] == "-10.0"
    assert (
        result["reaction"]["start_session"] == "2026-11-02"
        and result["reaction"]["end_session"] == "2026-11-04"
    )
    assert calls == ["DOCN", "SPY", "AKAM"]
    assert result["consensus"]["status"] == "unavailable"
    text = events.render_event_comparison(result)
    assert "not causal attribution" in text and "AKAM" in text


@pytest.mark.parametrize(
    "fault", ["period", "basis", "late_guidance", "late_actual", "unverified_consensus"]
)
def test_mismatched_expectations_cannot_become_surprise(monkeypatch, fault):
    install(monkeypatch)
    s = state()
    if fault == "period":
        s["financial_evidence"]["facts"][0]["period_start"] = "2026-04-01"
    elif fault == "basis":
        s["financial_evidence"]["facts"][0]["basis"] = "management-adjusted"
    elif fault == "late_guidance":
        s["filing_evidence"]["documents"][0]["filing"]["filed_date"] = "2026-11-03"
        s["financial_evidence"]["sources"][0]["filed_date"] = "2026-11-03"
    elif fault == "late_actual":
        s["financial_evidence"]["sources"][1]["filed_date"] = "2026-11-04"
    else:
        s["consensus"] = {
            "value": "80",
            "as_of": "2020-01-01",
            "period": "2026-Q3",
            "verified": True,
        }
    result = events.prepare_event_comparison(s, CONFIG)
    if fault != "unverified_consensus":
        assert not result["guidance"]["rows"]
    assert result["consensus"]["status"] == "unavailable"


def test_provider_failure_no_unconfigured_vendor_and_date_alignment(monkeypatch):
    records = {
        "DOCN": price("DOCN"),
        "SPY": {"status": "unavailable", "reason": "failed"},
        "AKAM": price("AKAM"),
    }
    install(monkeypatch, records)
    assert events.prepare_event_comparison(state(), CONFIG)["reaction"]["status"] == "unavailable"
    calls = install(monkeypatch)
    assert (
        events.prepare_event_comparison(state(), {"data_vendors": {"core_stock_apis": "other"}})[
            "reaction"
        ]["status"]
        == "unavailable"
    )
    assert not calls
    records = {
        "DOCN": price("DOCN"),
        "SPY": price("SPY", dates=("2026-11-01", "2026-11-04")),
        "AKAM": price("AKAM"),
    }
    install(monkeypatch, records)
    assert events.prepare_event_comparison(state(), CONFIG)["reaction"]["status"] == "unavailable"


def test_split_and_future_event_are_unavailable(monkeypatch):
    calls = install(monkeypatch)
    s = state()
    s["trade_date"] = "2026-11-02"
    assert events.prepare_event_comparison(s, CONFIG)["status"] == "unavailable" and not calls
    record = price("DOCN")
    raw = deepcopy(record["raw_source"])
    raw["bars"][1]["stock_splits"] = "2"
    install(monkeypatch, {"DOCN": prices._project(raw), "SPY": price("SPY"), "AKAM": price("AKAM")})
    assert events.prepare_event_comparison(state(), CONFIG)["reaction"]["status"] == "unavailable"


def test_source_rounding_overlap_cannot_claim_a_beat(monkeypatch):
    install(monkeypatch)
    s = state()
    s["financial_evidence"]["facts"][0]["value"] = "100000001"
    s["filing_fact_extraction"] = {"rounding_quantum_by_fact": {"actual": "1000"}}
    result = events.prepare_event_comparison(s, CONFIG)
    assert result["guidance"]["rows"][0]["position"] == "rounding_overlap_unknown"


@pytest.mark.parametrize(
    "tamper", [None, "return", "event", "cutoff", "price", "peer", "missing_reaction"]
)
def test_replay_is_offline_and_rejects_changed_projections(monkeypatch, tamper):
    install(monkeypatch)
    s = state()
    record = events.prepare_event_comparison(s, CONFIG)
    if tamper == "missing_reaction":
        record["reaction"] = None
    elif tamper == "return":
        record["reaction"]["returns"]["DOCN"]["percent"] = "99"
    elif tamper == "event":
        record["event"]["known_at"] = "2026-11-02"
    elif tamper == "cutoff":
        s["trade_date"] = "2026-11-03"
    elif tamper == "price":
        record["reaction"]["price_observations"]["DOCN"]["close"] = "99"
    elif tamper == "peer":
        record["reaction"]["symbols_selected_before_fetch"] = ["DOCN", "SPY", "MSFT"]
    monkeypatch.setattr(
        events, "get_price_observation", lambda *a: pytest.fail("network during replay")
    )
    if tamper:
        with pytest.raises(ValueError):
            events.replay_event_comparison(s, record)
    else:
        assert events.replay_event_comparison(s, record) == record


def test_unavailable_reaction_replays_without_network(monkeypatch):
    install(
        monkeypatch,
        {"DOCN": price("DOCN"), "SPY": {"status": "unavailable"}, "AKAM": price("AKAM")},
    )
    s = state()
    record = events.prepare_event_comparison(s, CONFIG)
    monkeypatch.setattr(
        events, "get_price_observation", lambda *a: pytest.fail("network during replay")
    )
    assert events.replay_event_comparison(s, record) == record


def test_offline_replay_preserves_unconfigured_provider_policy(monkeypatch):
    install(monkeypatch)
    s = state()
    record = events.prepare_event_comparison(s, {"data_vendors": {"core_stock_apis": "other"}})
    assert record["retrieval_policy"] == {"configured_yahoo": False}
    monkeypatch.setattr(
        events, "get_price_observation", lambda *a: pytest.fail("network during replay")
    )
    assert events.replay_event_comparison(s, record) == record


def test_guidance_source_mutation_and_duplicate_identity_fail_closed(monkeypatch):
    install(monkeypatch)
    for duplicate in (False, True):
        s = state()
        if duplicate:
            s["filing_evidence"]["documents"].append(deepcopy(s["filing_evidence"]["documents"][0]))
        else:
            s["filing_evidence"]["documents"][0]["content_hash"] = "f" * 64
        result = events.prepare_event_comparison(s, CONFIG)
        assert not result["guidance"]["rows"]


def test_wrong_ticker_cannot_combine_other_issuer_event_and_prices(monkeypatch):
    calls = install(monkeypatch)
    s = state()
    s["company_of_interest"] = "AAPL"
    result = events.prepare_event_comparison(s, CONFIG)
    assert result["status"] == "unavailable"
    assert "issuer" in result["reason"].lower()
    assert not calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("ticker", "AAPL"),
        ("cik", "0000320193"),
        ("as_of", "2026-11-03"),
        ("source", "model assertion"),
    ],
)
def test_issuer_binding_cannot_be_relabelled_or_reused_at_another_cutoff(monkeypatch, field, value):
    calls = install(monkeypatch)
    s = state()
    s["issuer_identity"][field] = value
    assert events.prepare_event_comparison(s, CONFIG)["status"] == "unavailable"
    assert not calls


def test_missing_legacy_identity_is_unavailable_and_replays_offline(monkeypatch):
    calls = install(monkeypatch)
    s = state()
    s.pop("issuer_identity")
    record = events.prepare_event_comparison(s, CONFIG)
    assert record["status"] == "unavailable" and not calls
    monkeypatch.setattr(
        events, "get_price_observation", lambda *a: pytest.fail("network during replay")
    )
    assert events.replay_event_comparison(s, record) == record
