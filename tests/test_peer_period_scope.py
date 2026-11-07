"""Peer extraction ignores ambiguous periods outside its valuation window."""

from datetime import UTC, date, datetime

import pytest

from tests.test_price_observation import install as install_price
from tradingagents.agents.valuation_reference import calculate_peer_statistics
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import sec_edgar
from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation


def companyfacts(monkeypatch, tmp_path, *, conflicting_end="2015-12-31"):
    quarters = [("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
                ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30")]
    revenue = [{"start": start, "end": end, "val": 100, "filed": "2026-11-06",
                "form": "10-Q", "accn": f"revenue-{end}"} for start, end in quarters]
    assets = [{"end": "2015-12-31", "val": 50, "filed": "2016-02-01", "form": "10-K"},
              {"end": "2026-09-30", "val": 500, "filed": "2026-11-06", "form": "10-Q"}]
    conflict = {"end": conflicting_end, "val": 99,
                "filed": "2016-02-01" if conflicting_end.startswith("2015") else "2026-11-06",
                "form": "10-K" if conflicting_end.startswith("2015") else "10-Q"}
    gaap = {
        "Assets": {"units": {"USD": assets, "EUR": [conflict]}},
        "Revenues": {"units": {"USD": revenue}},
        "CommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-09-30", "val": 10,
            "filed": "2026-11-06", "form": "10-Q"}]}},
    }
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: "0000000001")
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(sec_edgar, "_cached_json", lambda *args: {"cik": 1, "facts": {"us-gaap": gaap}})


def test_ambiguity_in_an_old_period_does_not_exclude_the_peer(monkeypatch, tmp_path):
    companyfacts(monkeypatch, tmp_path)
    install_price(monkeypatch, now="2026-11-07T22:00:00+00:00",
                  dates=("2026-09-30", "2026-11-05", "2026-11-06"), closes=(80, 84, 85),
                  metadata={"symbol": "PEER"})
    package = sec_edgar.get_financial_evidence("PEER", "2026-11-07",
        peer_revenue_definitions=True, period_floor=date(2023, 11, 7))
    quote = get_price_observation("PEER", "2026-11-07", date(2026, 9, 30))
    result = calculate_peer_statistics(package,
        {"ticker": "PEER", "cik": package.cik, "as_of": "2026-11-07", "source": "SEC issuer map"},
        quote, ticker="PEER", completed_cutoff=date(2026, 11, 6))
    assert result["status"] == "available", result
    assert all(f.period_end >= date(2023, 11, 7) for f in package.facts if f.value is not None)
    with pytest.raises(VendorUnavailableError, match="ambiguous"):
        sec_edgar.get_financial_evidence("PEER", "2026-11-07")


def test_ambiguity_inside_the_window_still_excludes(monkeypatch, tmp_path):
    companyfacts(monkeypatch, tmp_path, conflicting_end="2026-09-30")
    with pytest.raises(VendorUnavailableError, match="ambiguous"):
        sec_edgar.get_financial_evidence("PEER", "2026-11-07",
            peer_revenue_definitions=True, period_floor=date(2023, 11, 7))


def test_peer_fetch_passes_three_calendar_year_floor(monkeypatch):
    from tests.test_valuation_reference import fixture
    from tradingagents.agents.valuation_reference_flow import _fetch_peer
    from tradingagents.dataflows.vendors.yahoo import price_observation

    package, _ = fixture(cik="0000000001", ticker="PEER")
    session_meta = {"currentTradingPeriod": {"regular": {"end": datetime(2026, 10, 19, 21, tzinfo=UTC)}}}
    install_price(monkeypatch, now="2026-10-19T22:00:00+00:00",
                  dates=("2026-09-30", "2026-10-19"), metadata={"symbol": "DOCN", **session_meta})
    subject_quote = get_price_observation("DOCN", "2026-10-19", date(2026, 9, 30))
    install_price(monkeypatch, now="2026-10-19T22:00:00+00:00",
                  dates=("2026-09-30", "2026-10-19"), metadata={"symbol": "PEER", **session_meta})
    peer_quote = get_price_observation("PEER", "2026-10-19", date(2026, 9, 30))
    calls = []
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: package.cik)
    monkeypatch.setattr(sec_edgar, "get_financial_evidence",
                    lambda *args, **kwargs: calls.append((args, kwargs)) or package)
    monkeypatch.setattr(price_observation, "get_price_observation", lambda *args: peer_quote)
    state = {"company_of_interest": "DOCN", "trade_date": "2026-10-19", "asset_type": "stock",
             "price_observation": subject_quote, "issuer_identity": {"cik": "0001582961"}}
    result = _fetch_peer("PEER", state)
    assert result["status"] == "available", result
    assert calls == [(("PEER", "2026-10-19"),
                      {"peer_revenue_definitions": True, "period_floor": date(2023, 10, 19)})]
