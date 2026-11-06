"""Dated cover shares are conditional peer inputs, never EPS denominators."""
import hashlib
from copy import deepcopy

import pytest

from tradingagents.dataflows.vendors.peer_shares import replay_peer_cover_shares


def source(*, members=("A", "B"), values=(100, 20), day="2026-10-22"):
    rights = ("The rights of the holders of Class A and Class B common stock are identical, except with respect to voting and conversion. "
              "Shares of the Company's Class B common stock are convertible into an equivalent number of shares of the Company's Class A common stock. "
              "Class A common stock and Class B common stock are referred to, collectively, as common stock.")
    contexts, cells = [], []
    for i, (member, value) in enumerate(zip(members, values, strict=True)):
        dimension = (f'<xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">'
                     f'us-gaap:CommonClass{member}Member</xbrldi:explicitMember></xbrli:segment>') if member else ""
        contexts.append(f'<xbrli:context id="c{i}"><xbrli:entity><xbrli:identifier>1477333</xbrli:identifier>{dimension}</xbrli:entity>'
                        f'<xbrli:period><xbrli:instant>{day}</xbrli:instant></xbrli:period></xbrli:context>')
        cells.append(f'<ix:nonFraction id="f{i}" name="dei:EntityCommonStockSharesOutstanding" contextRef="c{i}" unitRef="shares" scale="0" decimals="INF">{value}</ix:nonFraction>')
    html = "".join(contexts) + '<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>' + "".join(cells) + rights
    url = "https://www.sec.gov/Archives/edgar/data/1477333/000147733326000061/cloud-20260930.htm"
    return {"filing": {"cik": "0001477333", "accession": "0001477333-26-000061", "form": "10-Q",
                       "filed_date": "2026-11-05", "report_date": "2026-09-30", "primary_document": "cloud-20260930.htm",
                       "items": "", "url": url},
            "source": {"url": url, "text": html, "retrieved_at": "2026-11-06T00:00:00+00:00",
                       "content_hash": hashlib.sha256(html.encode()).hexdigest()}}


def rehash(raw):
    raw["source"]["content_hash"] = hashlib.sha256(raw["source"]["text"].encode()).hexdigest()
    return raw


def test_dated_cover_classes_require_explicit_common_economic_basis():
    result = replay_peer_cover_shares(source(), "0001477333", "2026-11-05", "2026-11-05")
    assert result["shares"] == "120"
    assert result["share_date"] == "2026-10-22"
    assert result["quality"] == "lower_quality_dated_cover"
    assert len(result["components"]) == 2
    assert "voting" in result["rights_quote"]
    assert result["pricing_assumptions"]
    assert all(row["context_html"] and row["exact_html"] for row in result["components"])


@pytest.mark.parametrize("change", ["hash", "issuer", "future_date", "future_filing", "class", "conflict", "rights", "unit", "weighted", "url"])
def test_cover_share_uncertainty_cannot_be_silently_accepted(change):
    raw = deepcopy(source())
    if change == "hash":
        raw["source"]["text"] += "mutated"
    elif change == "issuer":
        raw["source"]["text"] = raw["source"]["text"].replace(">1477333<", ">999999<")
        rehash(raw)
    elif change == "future_date":
        raw = source(day="2026-11-06")
    elif change == "future_filing":
        raw["filing"]["filed_date"] = "2026-11-06"
    elif change == "class":
        raw = source(members=("A", "C"))
    elif change == "conflict":
        raw = source(members=("A", "A"), values=(100, 101))
    elif change == "rights":
        raw["source"]["text"] = raw["source"]["text"].replace("are identical", "are different")
        rehash(raw)
    elif change == "unit":
        raw["source"]["text"] = raw["source"]["text"].replace("xbrli:shares", "iso4217:USD")
        rehash(raw)
    elif change == "weighted":
        raw["source"]["text"] = raw["source"]["text"].replace("dei:EntityCommonStockSharesOutstanding", "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic")
        rehash(raw)
    elif change == "url":
        raw["source"]["url"] = "https://example.org/fake"
    with pytest.raises(ValueError):
        replay_peer_cover_shares(raw, "0001477333", "2026-11-05", "2026-11-05")


def test_peer_cover_fallback_is_conditional_and_does_not_change_history(monkeypatch):
    from datetime import datetime

    from tests.test_price_observation import install
    from tests.test_valuation_reference import fixture
    from tradingagents.agents.valuation_reference import calculate_peer_statistics, peer_range
    from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation
    package, identity = fixture(cik="0001477333", ticker="NET")
    package = package.model_copy(update={"facts": tuple(f for f in package.facts if f.metric != "Common Shares Outstanding")})
    raw = source(day="2026-10-15")
    raw["filing"]["filed_date"] = "2026-10-19"
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-10-15", "2026-10-19"), closes=(18, 20),
            metadata={"symbol": "NET", "currentTradingPeriod": {"regular": {"end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = get_price_observation("NET", "2026-10-19", "2026-10-15")
    strict = calculate_peer_statistics(package, identity, quote, ticker="NET", completed_cutoff="2026-10-19")
    assert strict["status"] == "unavailable"
    row = calculate_peer_statistics(package, identity, quote, ticker="NET", completed_cutoff="2026-10-19", peer_cover_shares=raw)
    assert row["status"] == "available", row
    assert row["share_date"] == "2026-10-15"
    assert row["share_quality"] == "lower_quality_dated_cover"
    assert row["conditional_assumptions"]
    assert row["shares"] == "120"
    from tests.test_valuation_reference import historical
    from tradingagents.agents.valuation_reference import calculate_own_history
    prices, splits = historical()
    for price in prices:
        price["ticker"] = "NET"
    splits["ticker"] = "NET"
    assert calculate_own_history(package, identity, prices, splits, ticker="NET")["status"] == "unavailable"
    assert peer_range([row])["lower_quality_tickers"] == ["NET"]
    assert "including conditional" in peer_range([row])["quality_label"]


def test_newest_after_completed_measurement_can_use_one_older_eligible_filing(monkeypatch):
    import json

    from tradingagents.dataflows.vendors import peer_shares
    newest = source(day="2026-11-05")
    older = source(day="2026-08-03")
    older["filing"].update(accession="0001477333-26-000054", filed_date="2026-08-06",
                            report_date="2026-06-30", primary_document="cloud-20260630.htm")
    oldurl = "https://www.sec.gov/Archives/edgar/data/1477333/000147733326000054/cloud-20260630.htm"
    older["filing"]["url"] = older["source"]["url"] = oldurl
    metadata = {"cik": 1477333, "filings": {"recent": {
        "form": ["10-Q", "10-Q"], "filingDate": ["2026-11-05", "2026-08-06"],
        "reportDate": ["2026-09-30", "2026-06-30"],
        "accessionNumber": ["0001477333-26-000061", "0001477333-26-000054"],
        "primaryDocument": ["cloud-20260930.htm", "cloud-20260630.htm"]}}}
    calls = []
    class Client:
        def __init__(self, **kwargs):
            pass
        def fetch(self, url):
            calls.append(url)
            if "/submissions/" in url:
                return {"text": json.dumps(metadata)}
            return older["source"] if url == oldurl else newest["source"]
    monkeypatch.setattr(peer_shares, "DocumentClient", Client)
    raw = peer_shares.get_peer_cover_shares("0001477333", "2026-11-05", "2026-11-04")
    assert raw["filing"]["accession"] == "0001477333-26-000054"
    assert len(calls) == 3


def test_explicit_tax_definitions_cannot_be_mixed_in_one_peer_ttm(monkeypatch):
    from datetime import datetime

    from tests.test_price_observation import install
    from tests.test_valuation_reference import fixture
    from tradingagents.agents.valuation_reference import calculate_peer_statistics
    from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation
    package, identity = fixture()
    facts, sources = [], list(package.sources)
    for fact in package.facts:
        if fact.metric == "Revenue":
            sid = "revenue-" + fact.fact_id
            tag = ("RevenueFromContractWithCustomerIncludingAssessedTax"
                   if str(fact.period_end) == "2026-09-30" else "RevenueFromContractWithCustomerExcludingAssessedTax")
            sources.append(package.sources[0].model_copy(update={"source_id": sid, "locator": "us-gaap/" + tag}))
            fact = fact.model_copy(update={"source_ids": (sid,), "locator": "us-gaap/" + tag})
        facts.append(fact)
    package = package.model_copy(update={"facts": tuple(facts), "sources": tuple(sources)})
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-09-30", "2026-10-19"), closes=(18, 20),
            metadata={"currentTradingPeriod": {"regular": {"end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = get_price_observation("DOCN", "2026-10-19", "2026-09-30")
    row = calculate_peer_statistics(package, identity, quote, ticker="DOCN", completed_cutoff="2026-10-19", include_quality=True)
    assert row["status"] == "unavailable"
    assert "tax definitions" in row["reason"]


def test_growth_is_independently_unavailable_across_explicit_tax_definition_change(monkeypatch):
    from datetime import datetime

    from tests.test_price_observation import install
    from tests.test_valuation_reference import fixture
    from tradingagents.agents.valuation_reference import calculate_peer_statistics
    from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation
    package, identity = fixture()
    facts, sources = [], list(package.sources)
    for fact in package.facts:
        if fact.metric == "Revenue":
            sid = "revenue-" + fact.fact_id
            tag = ("RevenueFromContractWithCustomerIncludingAssessedTax"
                   if str(fact.period_end) > "2025-09-30" else "RevenueFromContractWithCustomerExcludingAssessedTax")
            sources.append(package.sources[0].model_copy(update={"source_id": sid, "locator": "us-gaap/" + tag}))
            fact = fact.model_copy(update={"source_ids": (sid,), "locator": "us-gaap/" + tag})
        facts.append(fact)
    package = package.model_copy(update={"facts": tuple(facts), "sources": tuple(sources)})
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-09-30", "2026-10-19"), closes=(18, 20),
            metadata={"currentTradingPeriod": {"regular": {"end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = get_price_observation("DOCN", "2026-10-19", "2026-09-30")
    row = calculate_peer_statistics(package, identity, quote, ticker="DOCN", completed_cutoff="2026-10-19", include_quality=True)
    assert row["status"] == "available"
    assert row["trailing_revenue_growth"]["status"] == "unavailable"
    assert "tax definitions" in row["trailing_revenue_growth"]["reason"]


@pytest.mark.parametrize("missing_price", [False, True])
def test_peer_fetch_and_replay_keep_cover_dates_conditional(monkeypatch, missing_price):
    from datetime import datetime

    from tests.test_price_observation import install
    from tests.test_valuation_reference import fixture
    from tests.test_valuation_reference_flow import block, flow_fixture
    from tradingagents.agents import valuation_reference_flow as flow
    from tradingagents.dataflows.vendors import peer_shares, sec_edgar
    from tradingagents.dataflows.vendors.yahoo import price_observation
    real_price = price_observation.get_price_observation
    state, config, _, _ = flow_fixture(monkeypatch)
    package, _ = fixture(cik="0001477333", ticker="NET")
    package = package.model_copy(update={"facts": tuple(f for f in package.facts if f.metric != "Common Shares Outstanding")})
    raw = source(day="2026-10-15")
    raw["filing"]["filed_date"] = "2026-10-19"
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-10-15", "2026-10-19"), closes=(18, 20),
            metadata={"symbol": "NET", "currentTradingPeriod": {"regular": {"end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = ({"status": "unavailable", "ticker": "NET", "as_of": "2026-10-19",
              "reason": "Fixture same-session close absent"} if missing_price
             else real_price("NET", "2026-10-19", "2026-10-15"))
    monkeypatch.setattr(sec_edgar, "cik_for", lambda *a: "0001477333")
    monkeypatch.setattr(sec_edgar, "get_financial_evidence", lambda *a, **kw: package)
    monkeypatch.setattr(peer_shares, "get_peer_cover_shares", lambda *a: raw)
    requested_dates = []
    monkeypatch.setattr(price_observation, "get_price_observation",
                        lambda ticker, asof, capital: requested_dates.append(str(capital)) or quote)
    state.update(flow.acquire_reference_inputs(state, config))
    state["financial_claim_validation"] = {"raw_report": block('[{"ticker":"NET","reason":"Network infrastructure"}]')}
    updated = flow.finalize_peer_reference(state, config)
    record = updated["valuation_reference"]
    assert record["schema_version"] == 2
    assert requested_dates == ["2026-10-15"]
    if missing_price:
        assert not record["peers"]["accepted"] and not record["peers"]["rejected"]
        diagnostic = record["peers"]["incomplete"][0]["statistics"]
        assert diagnostic["shares"] == "120" and diagnostic["share_date"] == "2026-10-15"
        assert diagnostic["multiple"] is None and record["peers"]["range"]["status"] == "unavailable"
        assert "Fixture same-session close absent" in diagnostic["reason"]
        assert "A valid same-session completed price is unavailable" in updated["valuation_reference_brief"]
        assert "Multiple unavailable; excluded from the peer range" in updated["valuation_reference_brief"]
        assert "excluded from the peer range" in updated["valuation_reference_brief"]
    else:
        assert record["peers"]["accepted"][0]["statistics"]["share_quality"] == "lower_quality_dated_cover"
        assert record["peers"]["range"]["lower_quality_tickers"] == ["NET"]
        assert "Lower-quality conditional row" in updated["valuation_reference_brief"]
        assert "including conditional dated-share rows" in updated["valuation_reference_brief"]
    monkeypatch.setattr(peer_shares, "get_peer_cover_shares", lambda *a: pytest.fail("replay cannot fetch"))
    assert flow.replay_valuation_reference(state, record) == record
    assert record["subject"]["shares"] == "10"


def test_different_statement_share_date_is_lower_quality_only_for_new_peers(monkeypatch):
    from datetime import date, datetime

    from tests.test_price_observation import install
    from tests.test_valuation_reference import fixture
    from tradingagents.agents.valuation_reference import calculate_peer_statistics, peer_range
    from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation
    package, identity = fixture()
    package = package.model_copy(update={"facts": tuple(
        f for f in package.facts
        if not (f.metric == "Common Shares Outstanding" and f.period_end == date(2026, 9, 30))
    )})
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-06-30", "2026-10-19"), closes=(18, 20),
            metadata={"currentTradingPeriod": {"regular": {"end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = get_price_observation("DOCN", "2026-10-19", "2026-06-30")
    legacy = calculate_peer_statistics(package, identity, quote, ticker="DOCN", completed_cutoff="2026-10-19")
    assert legacy["status"] == "available" and "share_quality" not in legacy
    row = calculate_peer_statistics(package, identity, quote, ticker="DOCN", completed_cutoff="2026-10-19", include_quality=True)
    assert row["status"] == "available"
    assert row["share_date"] == "2026-06-30" and row["revenue_fact"]["period_end"] == "2026-09-30"
    assert row["share_quality"] == "lower_quality_dated_statement"
    assert "held constant" in row["conditional_assumptions"][0]
    assert row["multiple"] == legacy["multiple"]
    assert peer_range([row], include_quality=True)["lower_quality_tickers"] == ["DOCN"]


def test_missing_quote_diagnostic_cannot_publish_mixed_tax_revenue():
    from tests.test_valuation_reference import fixture
    from tradingagents.agents.valuation_reference import calculate_peer_share_diagnostic
    package, identity = fixture(cik="0001477333", ticker="NET")
    facts, sources = [], list(package.sources)
    for fact in package.facts:
        if fact.metric == "Revenue":
            sid = "revenue-" + fact.fact_id
            tag = ("RevenueFromContractWithCustomerIncludingAssessedTax"
                   if str(fact.period_end) == "2026-09-30" else "RevenueFromContractWithCustomerExcludingAssessedTax")
            sources.append(package.sources[0].model_copy(update={"source_id": sid, "locator": "us-gaap/" + tag}))
            fact = fact.model_copy(update={"source_ids": (sid,), "locator": "us-gaap/" + tag})
        facts.append(fact)
    package = package.model_copy(update={"facts": tuple(facts), "sources": tuple(sources)})
    cover = source(day="2026-10-15")
    cover["filing"]["filed_date"] = "2026-10-19"
    with pytest.raises(ValueError, match="tax definitions"):
        calculate_peer_share_diagnostic(
            package, identity, cover, ticker="NET", as_of="2026-10-19",
            completed_cutoff="2026-10-19", revenue_currency="USD",
            reason="Missing same-session close",
        )
