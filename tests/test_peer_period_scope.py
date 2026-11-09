"""Peer extraction ignores ambiguous periods outside its valuation window."""

from datetime import UTC, date, datetime

import pytest

from tests.test_price_observation import install as install_price
from tradingagents.agents.valuation_reference import calculate_peer_statistics
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import sec_edgar
from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation


def companyfacts(monkeypatch, tmp_path, *, conflicting_end="2015-12-31", conflicting_tag="Assets"):
    quarters = [("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
                ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30")]
    revenue = [{"start": start, "end": end, "val": 100, "filed": "2026-11-06",
                "form": "10-Q", "accn": f"revenue-{end}"} for start, end in quarters]
    assets = [{"end": "2015-12-31", "val": 50, "filed": "2016-02-01", "form": "10-K"},
              {"end": "2026-09-30", "val": 500, "filed": "2026-11-06", "form": "10-Q"}]
    filed = "2016-02-01" if conflicting_end.startswith("2015") else "2026-11-06"
    conflict = {"end": conflicting_end, "val": 99,
                "filed": filed,
                "form": "10-K" if conflicting_end.startswith("2015") else "10-Q"}
    if conflicting_tag == "Assets" and conflicting_end not in {row["end"] for row in assets}:
        assets.append({"end": conflicting_end, "val": 50, "filed": filed, "form": conflict["form"]})
    if conflicting_tag == "Revenues":
        conflict["start"] = "2026-07-01"
    gaap = {
        "Assets": {"units": {"USD": assets, **({"EUR": [conflict]} if conflicting_tag == "Assets" else {})}},
        "Revenues": {"units": {"USD": revenue, **({"EUR": [conflict]} if conflicting_tag == "Revenues" else {})}},
        "CommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-09-30", "val": 10,
            "filed": "2026-11-06", "form": "10-Q"}]}},
    }
    if conflicting_tag == "GrossProfit":
        gaap["GrossProfit"] = {"units": {
            "USD": [{**conflict, "start": "2026-07-01", "val": 50}],
            "EUR": [{**conflict, "start": "2026-07-01"}],
        }}
    if conflicting_tag == "CommonStockSharesOutstanding":
        gaap["CommonStockSharesOutstanding"]["units"]["EUR"] = [conflict]
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


def test_peer_ambiguity_in_unused_metric_keeps_peer(monkeypatch, tmp_path):
    from tradingagents.agents.valuation_reference_flow import _fetch_peer

    companyfacts(monkeypatch, tmp_path, conflicting_end="2023-12-31")
    install_price(monkeypatch, now="2026-11-07T22:00:00+00:00",
                  dates=("2026-09-30", "2026-11-05", "2026-11-06"), closes=(80, 84, 85),
                  metadata={"symbol": "SUBJECT"})
    subject_quote = get_price_observation("SUBJECT", "2026-11-07", date(2026, 9, 30))
    install_price(monkeypatch, now="2026-11-07T22:00:00+00:00",
                  dates=("2026-09-30", "2026-11-05", "2026-11-06"), closes=(80, 84, 85),
                  metadata={"symbol": "PEER"})
    state = {"company_of_interest": "SUBJECT", "trade_date": "2026-11-07", "asset_type": "stock",
             "price_observation": subject_quote, "issuer_identity": {"cik": "0000000002"}}
    peer = _fetch_peer("PEER", state)
    assert peer["status"] == "available", peer
    assert all(f["metric"] != "Total Assets" for f in peer["package"]["facts"])
    gap = "Total Assets ambiguous at 2023-12-31; not used for peer statistics"
    assert gap in peer["package"]["warnings"]
    result = calculate_peer_statistics(peer["package"], peer["issuer_identity"], peer["price_observation"],
                                       ticker="PEER", completed_cutoff=date(2026, 11, 6))
    assert result["status"] == "available", result
    assert gap in result["evidence_gaps"]


def test_peer_ambiguity_in_revenue_still_excludes(monkeypatch, tmp_path):
    companyfacts(monkeypatch, tmp_path, conflicting_end="2026-09-30", conflicting_tag="Revenues")
    with pytest.raises(VendorUnavailableError, match="Revenues at 2026-09-30"):
        sec_edgar.get_financial_evidence("PEER", "2026-11-07",
            peer_revenue_definitions=True, period_floor=date(2023, 11, 7))


@pytest.mark.parametrize("tag", ["GrossProfit", "CommonStockSharesOutstanding"])
def test_peer_ambiguity_in_other_consumed_metrics_still_excludes(monkeypatch, tmp_path, tag):
    companyfacts(monkeypatch, tmp_path, conflicting_end="2026-09-30", conflicting_tag=tag)
    with pytest.raises(VendorUnavailableError, match=f"{tag} at 2026-09-30"):
        sec_edgar.get_financial_evidence("PEER", "2026-11-07",
            peer_revenue_definitions=True, period_floor=date(2023, 11, 7))


def test_subject_ambiguity_still_raises(monkeypatch, tmp_path):
    companyfacts(monkeypatch, tmp_path, conflicting_end="2023-12-31")
    with pytest.raises(VendorUnavailableError, match="Assets at 2023-12-31"):
        sec_edgar.get_financial_evidence("PEER", "2026-11-07")


def test_peer_gap_is_visible_in_reference_brief(monkeypatch):
    from tests.test_valuation_reference_flow import flow_fixture
    from tradingagents.agents import valuation_reference_flow as flow

    state, config, _, _ = flow_fixture(monkeypatch)
    monkeypatch.setattr(flow, "default_peer_selection", lambda *args: {
        "kind": "previous", "status": "available", "reason": None,
        "peers": [{"ticker": "AKAM", "reason": "Prior cloud comparison"}],
    })
    record = flow.acquire_reference_inputs(state, config)["valuation_reference"]
    gap = "Total Assets ambiguous at 2023-12-31; not used for peer statistics"
    assert record["peers"]["accepted"]
    record["peers"]["accepted"][0]["statistics"]["evidence_gaps"] = [gap]
    assert f"Evidence gap: {gap}." in flow.render_valuation_reference(record)


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


def test_recorded_nbis_old_ambiguous_year_is_excluded_and_disclosed(monkeypatch, tmp_path):
    from tests.docn_workflow_fixture import source_json

    mapping = source_json('issuer-map.json.gz')
    raw = source_json('raw-companyfacts-nbis.json.gz')
    monkeypatch.setattr(sec_edgar, 'get_config', lambda: {'data_cache_dir': str(tmp_path)})
    monkeypatch.setattr(sec_edgar, '_cached_json',
                        lambda url, name: mapping if name == 'company_tickers.json' else raw)
    package = sec_edgar.get_financial_evidence('NBIS', '2026-11-07', peer_revenue_definitions=True,
                                               period_floor=date(2023, 11, 7))
    assert 'Revenues ambiguous at 2023-12-31; period excluded; not used for peer statistics' in package.warnings
    # NBIS files annually, so there are no quarters to form trailing revenue from.
    assert not [f for f in package.facts if f.metric == 'Revenue' and f.value is not None
                and 60 <= (f.period_end - f.period_start).days <= 115]


def _annual_conflict(monkeypatch, tmp_path, end):
    """The NBIS shape: one annual revenue period reported in two currencies."""
    companyfacts(monkeypatch, tmp_path)
    gaap = sec_edgar._cached_json()["facts"]["us-gaap"]
    gaap["Revenues"]["units"]["USD"].append({"start": f"{end[:4]}-01-01", "end": end, "val": 400,
                                             "filed": "2026-02-01", "form": "10-K", "accn": "usd"})
    gaap["Revenues"]["units"]["RUB"] = [{"start": f"{end[:4]}-01-01", "end": end, "val": 30000,
                                         "filed": "2026-02-01", "form": "10-K", "accn": "rub"}]
    monkeypatch.setattr(sec_edgar, "_cached_json", lambda *args: {"cik": 1, "facts": {"us-gaap": gaap}})


def test_peer_ambiguous_old_period_is_excluded_not_fatal(monkeypatch, tmp_path):
    _annual_conflict(monkeypatch, tmp_path, "2023-12-31")
    package = sec_edgar.get_financial_evidence("PEER", "2026-11-07", peer_revenue_definitions=True,
                                               period_floor=date(2023, 11, 7))
    gap = "Revenues ambiguous at 2023-12-31; period excluded; not used for peer statistics"
    assert gap in package.warnings
    assert not [f for f in package.facts if f.metric == "Revenue" and str(f.period_end) == "2023-12-31"]
    assert len([f for f in package.facts if f.metric == "Revenue" and f.period_start is not None
                and str(f.period_end) >= "2025-12-31"]) >= 4


def test_peer_ambiguity_inside_statistics_window_is_not_dropped(monkeypatch, tmp_path):
    _annual_conflict(monkeypatch, tmp_path, "2025-12-31")
    with pytest.raises(VendorUnavailableError, match="Revenues at 2025-12-31"):
        sec_edgar.get_financial_evidence("PEER", "2026-11-07", peer_revenue_definitions=True,
                                         period_floor=date(2023, 11, 7))


def test_subject_issuer_ambiguity_still_raises(monkeypatch, tmp_path):
    _annual_conflict(monkeypatch, tmp_path, "2023-12-31")
    with pytest.raises(VendorUnavailableError, match="Revenues at 2023-12-31"):
        sec_edgar.get_financial_evidence("PEER", "2026-11-07", period_floor=date(2023, 11, 7))


def test_excluded_period_is_disclosed_in_peer_brief(monkeypatch, tmp_path):
    _annual_conflict(monkeypatch, tmp_path, "2023-12-31")
    install_price(monkeypatch, now="2026-11-07T22:00:00+00:00",
                  dates=("2026-09-30", "2026-11-05", "2026-11-06"), closes=(80, 84, 85), metadata={"symbol": "PEER"})
    package = sec_edgar.get_financial_evidence("PEER", "2026-11-07", peer_revenue_definitions=True,
                                               period_floor=date(2023, 11, 7))
    quote = get_price_observation("PEER", "2026-11-07", date(2026, 9, 30))
    result = calculate_peer_statistics(package, {"ticker": "PEER", "cik": package.cik, "as_of": "2026-11-07",
                                                 "source": "SEC issuer map"},
                                       quote, ticker="PEER", completed_cutoff=date(2026, 11, 6))
    assert result["status"] == "available", result
    assert "Revenues ambiguous at 2023-12-31; period excluded; not used for peer statistics" in result["evidence_gaps"]


def test_annual_only_peer_is_not_blamed_on_an_ambiguous_period(monkeypatch, tmp_path):
    """The Nebius case: 20-F filer, no quarterly revenue, one conflicting year."""
    companyfacts(monkeypatch, tmp_path)
    gaap = sec_edgar._cached_json()["facts"]["us-gaap"]
    gaap["Revenues"]["units"] = {
        "USD": [{"start": "2023-01-01", "end": "2023-12-31", "val": 98, "filed": "2026-04-30", "form": "20-F", "accn": "a"},
                {"start": "2025-01-01", "end": "2025-12-31", "val": 530, "filed": "2026-04-30", "form": "20-F", "accn": "b"}],
        "RUB": [{"start": "2023-01-01", "end": "2023-12-31", "val": 800, "filed": "2024-04-26", "form": "20-F", "accn": "c"}]}
    monkeypatch.setattr(sec_edgar, "_cached_json", lambda *args: {"cik": 1, "facts": {"us-gaap": gaap}})
    package = sec_edgar.get_financial_evidence("PEER", "2026-11-07", peer_revenue_definitions=True,
                                               period_floor=date(2023, 11, 7))
    assert "Revenues ambiguous at 2023-12-31; period excluded; not used for peer statistics" in package.warnings
    assert [str(f.period_end) for f in package.facts if f.metric == "Revenue" and f.value is not None] == ["2025-12-31"]
