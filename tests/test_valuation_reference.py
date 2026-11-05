"""Retrospective equity/revenue and current peer reference invariants."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal

import pytest

from tests.test_price_observation import install
from tradingagents.agents.valuation_reference import (
    calculate_own_history,
    calculate_peer_statistics,
    peer_range,
    render_own_history,
)
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord
from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation

ENDS = (
    ("2024-10-01", "2024-12-31"), ("2025-01-01", "2025-03-31"),
    ("2025-04-01", "2025-06-30"), ("2025-07-01", "2025-09-30"),
    ("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
    ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30"),
)


def fixture(cik="0001582961", ticker="DOCN"):
    source = SourceRecord(source_id="sec", cik=cik, url="https://www.sec.gov/test",
                          filed_date="2026-10-01", retrieved_at="2026-10-19T22:00:00Z",
                          content_hash="a" * 64, locator="fixture", form="10-Q")
    facts = []
    for i, (start, end) in enumerate(ENDS):
        for metric, value, unit in (
            ("Revenue", 100 + i * 10, "USD"),
            ("Gross Profit", 50 + i * 5, "USD"),
            ("Common Shares Outstanding", 10, "shares"),
        ):
            facts.append(FinancialFact(
                fact_id=f"{metric}-{i}", metric=metric, value=value, unit=unit, cik=cik,
                period_start=start if metric != "Common Shares Outstanding" else None,
                period_end=end, as_of="2026-10-19", source_ids=("sec",), locator=f"fixture/{i}",
            ))
    package = EvidencePackage(cik=cik, as_of="2026-10-19", sources=(source,), facts=tuple(facts))
    identity = {"ticker": ticker, "cik": cik, "as_of": "2026-10-19", "source": "SEC issuer map"}
    return package, identity


def historical():
    dates = [end for _, end in ENDS[3:]]
    prices = [
        {"ticker": "DOCN", "quarter_end": end, "session_date": end, "session_status": "completed",
         "close": "20", "currency": "USD", "source_id": "yahoo-history",
         "content_hash": "b" * 64, "source_url": "https://query2.finance.yahoo.com/chart/DOCN",
         "adjustment_basis": "historical_split_adjusted", "split_basis_date": "2026-10-19"}
        for end in dates
    ]
    split = {"ticker": "DOCN", "coverage_complete": True, "coverage_start": "2024-12-31",
             "coverage_end": "2026-10-19", "split_basis_date": "2026-10-19",
             "source_id": "yahoo-history", "content_hash": "b" * 64, "splits": []}
    return prices, split


@pytest.mark.unit
def test_history_reconciles_exact_quarter_shares_ttm_and_split_basis():
    package, identity = fixture()
    prices, split = historical()
    split["splits"] = [{"session_date": "2026-01-15", "ratio": "2", "source_id": "yahoo-history"}]
    result = calculate_own_history(package, identity, prices, split, ticker="DOCN", current_multiple="1")
    assert result["status"] == "available", result
    assert result["current_position"]["status"] == "available"
    assert result["statistics"]["count"] == 5
    assert Decimal(result["rows"][0]["revenue"]) == 460
    assert Decimal(result["rows"][0]["adjusted_shares"]) == 20
    assert abs(Decimal(result["rows"][0]["multiple"]) - Decimal(400) / 460) < Decimal("1e-27")
    assert result["rows"][-1]["adjusted_shares"] == "10"
    assert result["rows"][0]["share_date"] == "2025-09-30"
    assert result["rows"][0]["revenue_fact"]["input_fact_ids"]
    assert result["rows"][0]["revenue_fact"]["sources"][0]["filed_date"] == "2026-10-01"
    assert "not a point-in-time backtest" in render_own_history(result)
    assert peer_range([{"status": "available", "basis": "equity_value / trailing_revenue", "multiple": "2"}])["statistics"]["median"] == "2"


@pytest.mark.unit
def test_history_rejects_cover_date_shares_short_series_and_uncovered_split():
    package, identity = fixture()
    prices, split = historical()
    facts = tuple(f for f in package.facts if f.fact_id != "Common Shares Outstanding-3")
    facts += (FinancialFact(fact_id="cover", metric="Common Shares Outstanding", value=10,
                            unit="shares", cik=package.cik, period_end="2025-10-15",
                            as_of=package.as_of, source_ids=("sec",), locator="cover"),)
    package = package.model_copy(update={"facts": facts})
    result = calculate_own_history(package, identity, prices, split, ticker="DOCN")
    assert result["status"] == "available"
    assert result["statistics"]["count"] == 4
    assert any("exact quarter-end shares" in reason for reason in result["excluded"])
    assert calculate_own_history(package, identity, prices[:3], split, ticker="DOCN")["status"] == "unavailable"
    split["coverage_start"] = "2026-01-01"
    assert "Split coverage" in calculate_own_history(package, identity, prices, split, ticker="DOCN")["reason"]


@pytest.mark.unit
def test_history_rejects_future_basis_and_ambiguous_revenue():
    package, identity = fixture()
    prices, split = historical()
    split["split_basis_date"] = "2026-11-01"
    assert calculate_own_history(package, identity, prices, split, ticker="DOCN")["status"] == "unavailable"
    split["split_basis_date"] = "2026-10-19"
    original = next(f for f in package.facts if f.fact_id == "Revenue-3")
    conflict = original.model_copy(update={"fact_id": "conflict", "value": Decimal(999)})
    package = package.model_copy(update={"facts": (*package.facts, conflict)})
    result = calculate_own_history(package, identity, prices, split, ticker="DOCN")
    assert result["status"] == "unavailable"
    assert result["usable_quarters"] == 1


@pytest.mark.unit
def test_peer_current_multiple_growth_margin_and_split_rejection(monkeypatch):
    package, identity = fixture()
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-09-30", "2026-10-19"), closes=(18, 20),
            metadata={"currentTradingPeriod": {"regular": {
                "end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = get_price_observation("DOCN", "2026-10-19", "2026-09-30")
    result = calculate_peer_statistics(package, identity, quote, ticker="DOCN", completed_cutoff=date(2026, 10, 19))
    assert result["status"] == "available", result
    assert Decimal(result["equity_value"]) == 200
    assert Decimal(result["revenue"]) == 620
    assert abs(Decimal(result["multiple"]) - Decimal(200) / 620) < Decimal("1e-27")
    assert result["trailing_revenue_growth"]["status"] == "available"
    assert result["gross_margin"]["percent"] == "50"
    assert calculate_peer_statistics(package, identity, quote, ticker="DOCN", completed_cutoff=date(2026, 10, 16))["status"] == "unavailable"

    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-09-30", "2026-10-19"), closes=(18, 20), splits=(0, 2),
            metadata={"currentTradingPeriod": {"regular": {
                "end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    split_quote = get_price_observation("DOCN", "2026-10-19", "2026-09-30")
    assert "split" in calculate_peer_statistics(package, identity, split_quote, ticker="DOCN", completed_cutoff=date(2026, 10, 19))["reason"].lower()


@pytest.mark.unit
def test_peer_missing_margin_is_independent_and_wrong_issuer_fails(monkeypatch):
    package, identity = fixture()
    package = package.model_copy(update={"facts": tuple(f for f in package.facts if f.metric != "Gross Profit")})
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-09-30", "2026-10-19"), closes=(18, 20),
            metadata={"currentTradingPeriod": {"regular": {
                "end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = get_price_observation("DOCN", "2026-10-19", "2026-09-30")
    result = calculate_peer_statistics(package, identity, quote, ticker="DOCN", completed_cutoff=date(2026, 10, 19))
    assert result["status"] == "available" and result["gross_margin"]["status"] == "unavailable"
    wrong = deepcopy(identity)
    wrong["ticker"] = "AAPL"
    assert calculate_peer_statistics(package, wrong, quote, ticker="DOCN", completed_cutoff=date(2026, 10, 19))["status"] == "unavailable"


@pytest.mark.unit
def test_peer_negative_gross_margin_and_missing_growth_are_separate(monkeypatch):
    package, identity = fixture()
    facts = []
    for f in package.facts:
        if f.metric == "Revenue" and f.period_end <= date(2025, 9, 30):
            continue
        if f.metric == "Gross Profit":
            f = f.model_copy(update={"value": Decimal(-5)})
        facts.append(f)
    package = package.model_copy(update={"facts": tuple(facts)})
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-09-30", "2026-10-19"), closes=(18, 20),
            metadata={"currentTradingPeriod": {"regular": {
                "end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = get_price_observation("DOCN", "2026-10-19", "2026-09-30")
    result = calculate_peer_statistics(package, identity, quote, ticker="DOCN", completed_cutoff=date(2026, 10, 19))
    assert result["status"] == "available", result
    assert result["trailing_revenue_growth"]["status"] == "unavailable"
    assert Decimal(result["gross_margin"]["percent"]) < 0


@pytest.mark.unit
def test_history_rejects_tampered_filing_cutoff_and_price_ticker():
    package, identity = fixture()
    prices, split = historical()
    prices[0]["ticker"] = "AAPL"
    result = calculate_own_history(package, identity, prices, split, ticker="DOCN")
    assert result["status"] == "available"
    assert result["statistics"]["count"] == 4
    assert "identity" in result["excluded"][0]
    prices[0]["ticker"] = "DOCN"
    late = package.sources[0].model_copy(update={"filed_date": date(2026, 10, 20)})
    tampered = package.model_copy(update={"sources": (late,)})
    result = calculate_own_history(tampered, identity, prices, split, ticker="DOCN")
    assert result["status"] == "unavailable"
    assert "filing cutoff" in result["reason"]
