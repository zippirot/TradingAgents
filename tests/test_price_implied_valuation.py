"""Independent price-implied rows from retained source evidence."""
import json
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_price_observation import install
from tests.test_valuation import evidence
from tradingagents.agents.output_validation import enforce_publication
from tradingagents.agents.valuation_comparison import (
    price_implied_valuation,
    render_price_implied_valuation,
)
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, derive_ttm
from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation

STATE = Path("/Users/zipp/Developer/tradingagents-market-evidence-20261105/private/inputs/retained/DOCN/full_states_log_2026-11-05.json")


def retained_state():
    if not STATE.exists():
        pytest.skip("Private DOCN proof input is not present")
    return json.loads(STATE.read_text())


@pytest.mark.unit
def test_docn_source_only_rows_reconcile_without_model_target():
    state = retained_state()
    assert state["valuation_price_comparison"]["status"] == "unavailable"
    state.pop("target_validation", None)
    row = price_implied_valuation(state)
    assert row["status"] == "available", row
    assert [r["status"] for r in row["rows"]] == ["available"] * 3
    assert Decimal(row["equity_value_usd"]) == Decimal("9907699422.7679359695384")
    assert Decimal(row["trailing_revenue_usd"]) == Decimal("1102671000")
    assert [r["net_obligations_usd"] for r in row["rows"]] == ["-204466000", "719133000", "1385744000"]
    assert row["management_revenue_guidance_range_usd"] == ["1208000000", "1211000000"]
    assert row["guided_diluted_weighted_average_shares_range"] == ["128000000", "129000000"]
    assert row["growth_floor_percent"] == "60"
    assert "What the price implies" in render_price_implied_valuation(row)
    assert "conditional" in render_price_implied_valuation(row).lower()


@pytest.mark.unit
def test_bad_issuer_and_missing_obligation_leave_no_false_ratios():
    state = retained_state()
    state["issuer_identity"]["ticker"] = "AAPL"
    assert price_implied_valuation(state)["status"] == "unavailable"
    state = retained_state()
    state["financial_evidence"]["facts"] = [f for f in state["financial_evidence"]["facts"] if "Operating Lease Liabilities" not in f["metric"]]
    row = price_implied_valuation(state)
    assert row["status"] == "available"
    assert row["rows"][0]["status"] == "available"
    assert row["rows"][2]["status"] == "unavailable"


def synthetic_state(monkeypatch):
    base = evidence()
    source = base.sources[0].model_copy(update={"filed_date": date(2026, 10, 5)})
    facts = list(base.facts)
    facts.append(FinancialFact(fact_id="assets", metric="Total Assets", value=3000, unit="USD",
                               cik=base.cik, period_end="2026-06-30", as_of=base.as_of,
                               source_ids=("s",), locator="synthetic/assets"))
    quarters = []
    for i, (start, end) in enumerate((("2025-10-01", "2025-12-31"),
                                      ("2026-01-01", "2026-03-31"),
                                      ("2026-04-01", "2026-06-30"),
                                      ("2026-07-01", "2026-09-30"))):
        quarters.append(FinancialFact(fact_id=f"q{i}", metric="Revenue", value=250,
                                      unit="USD", cik=base.cik, period_start=start,
                                      period_end=end, as_of=base.as_of,
                                      source_ids=("s",), locator=f"synthetic/q{i}"))
    facts.extend(quarters)
    facts.append(derive_ttm(quarters))
    package = EvidencePackage(cik=base.cik, as_of=base.as_of, facts=tuple(facts), sources=(source,))
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-06-30", "2026-10-19"), closes=(18, 20),
            metadata={"currentTradingPeriod": {"regular": {
                "end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    quote = get_price_observation("DOCN", "2026-10-19", "2026-06-30")
    assert quote["status"] == "available"
    return {"asset_type": "stock", "company_of_interest": "DOCN", "trade_date": "2026-10-19",
            "issuer_identity": {"ticker": "DOCN", "cik": base.cik, "as_of": "2026-10-19", "source": "SEC issuer map"},
            "price_observation": quote, "financial_evidence": package.model_dump(mode="json")}


@pytest.mark.unit
def test_source_only_arithmetic_and_independent_unavailable_rows(monkeypatch):
    state = synthetic_state(monkeypatch)
    result = price_implied_valuation(state)
    assert result["status"] == "available"
    assert result["equity_value_usd"] == "2000"
    assert result["trailing_revenue_usd"] == "1000"
    assert [r["net_obligations_usd"] for r in result["rows"]] == ["100", "130", "160"]
    assert [Decimal(r["ratios"]["trailing_revenue"]) for r in result["rows"]] == [
        Decimal("2.1"), Decimal("2.13"), Decimal("2.16")]
    assert all("guidance_range" not in r["ratios"] for r in result["rows"])
    state["financial_evidence"]["facts"] = [f for f in state["financial_evidence"]["facts"]
                                             if "Operating Lease Liabilities" not in f["metric"]]
    partial = price_implied_valuation(state)
    assert partial["status"] == "available" and partial["equity_value_usd"] == "2000"
    assert [r["status"] for r in partial["rows"]] == ["available", "available", "unavailable"]


@pytest.mark.unit
def test_wrong_issuer_tampered_price_and_nonstock_cannot_publish_numbers(monkeypatch):
    state = synthetic_state(monkeypatch)
    state["issuer_identity"]["ticker"] = "AAPL"
    assert price_implied_valuation(state)["status"] == "unavailable"
    state = synthetic_state(monkeypatch)
    state["price_observation"]["currency"] = "EUR"
    assert price_implied_valuation(state)["status"] == "unavailable"
    state = synthetic_state(monkeypatch)
    state["asset_type"] = "crypto"
    assert price_implied_valuation(state)["status"] == "not_applicable"


@pytest.mark.unit
def test_valid_source_quote_with_incompatible_split_or_currency_is_unavailable(monkeypatch):
    state = synthetic_state(monkeypatch)
    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-06-30", "2026-10-19"), closes=(18, 20), splits=(0, 2),
            metadata={"currentTradingPeriod": {"regular": {
                "end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    state["price_observation"] = get_price_observation("DOCN", "2026-10-19", "2026-06-30")
    assert state["price_observation"]["status"] == "available"
    assert "split" in price_implied_valuation(state)["reason"].lower()

    install(monkeypatch, now="2026-10-19T22:00:00+00:00",
            dates=("2026-06-30", "2026-10-19"), closes=(18, 20), metadata={
                "currency": "EUR", "currentTradingPeriod": {"regular": {
                    "end": datetime.fromisoformat("2026-10-19T21:00:00+00:00")}}})
    state["price_observation"] = get_price_observation("DOCN", "2026-10-19", "2026-06-30")
    assert state["price_observation"]["status"] == "available"
    assert "currency" in price_implied_valuation(state)["reason"].lower()


@pytest.mark.unit
def test_publication_shows_one_independent_section_without_a_model_target(monkeypatch):
    state = synthetic_state(monkeypatch)
    state.update(evidence_quality={"status": "limited"}, final_rating="Hold",
                 target_validation={"status": "unsupported", "request": None})
    updated = enforce_publication(state)
    assert updated["price_implied_valuation"]["status"] == "available"
    assert updated["target_validation"]["status"] == "unsupported"
    assert updated["final_trade_decision"].count("### What the price implies") == 1
    assert "Dated equity value" in updated["final_trade_decision"]


@pytest.mark.unit
def test_review_displays_unavailable_section_without_actionable_multiples():
    updated = enforce_publication({"evidence_quality": {"status": "insufficient", "checks": []},
                                   "asset_type": "stock", "final_rating": "Buy"})
    assert updated["price_implied_valuation"]["status"] == "unavailable"
    assert "### What the price implies" in updated["final_trade_decision"]
    assert "Unavailable" in updated["final_trade_decision"]
    assert updated["final_rating"] == "REVIEW"


@pytest.mark.unit
def test_nonpositive_numerators_and_missing_revenue_are_independent(monkeypatch):
    state = synthetic_state(monkeypatch)
    for fact in state["financial_evidence"]["facts"]:
        if fact["fact_id"] == "cash":
            fact["value"] = "10000"
    result = price_implied_valuation(state)
    assert result["status"] == "available" and result["equity_value_usd"] == "2000"
    assert all(r["status"] == "unavailable" and "Nonpositive" in r["reason"] for r in result["rows"])

    state = synthetic_state(monkeypatch)
    state["financial_evidence"]["facts"] = [f for f in state["financial_evidence"]["facts"]
                                             if f["metric"] != "Revenue"]
    result = price_implied_valuation(state)
    assert result["status"] == "available" and result["trailing_revenue_usd"] is None
    assert all(r["status"] == "available" and "trailing_revenue" not in r["ratios"] for r in result["rows"])


@pytest.mark.unit
def test_without_source_growth_floor_no_conditional_upper_is_present():
    state = retained_state()
    for package in state["disclosure_evidence"]["packages"]:
        for doc in package["documents"]:
            doc["blocks"] = [block for block in doc["blocks"] if block["locator"] != "block-4"]
    result = price_implied_valuation(state)
    assert result["status"] == "available" and result["growth_floor_percent"] is None
    assert all("growth_floor_conditional_upper" not in row["ratios"] for row in result["rows"])


@pytest.mark.unit
def test_missing_reported_shares_keeps_only_explicit_guided_share_sensitivity():
    state = retained_state()
    state["financial_evidence"]["facts"] = [f for f in state["financial_evidence"]["facts"]
                                             if f["metric"] != "Common Shares Outstanding"]
    result = price_implied_valuation(state)
    assert result["status"] == "available" and result["equity_value_usd"] is None
    assert result["shares"] is None
    assert all(row["status"] == "unavailable" for row in result["rows"])
    assert all("guided_diluted_weighted_average_share_sensitivity" in row for row in result["rows"])
    rendered = render_price_implied_valuation(result)
    assert "reported outstanding shares unavailable" in rendered
    assert "conditional sensitivity, not current shares outstanding" in rendered


@pytest.mark.unit
def test_rendered_guidance_uses_retained_periods_not_a_hardcoded_year():
    record = price_implied_valuation(retained_state())
    record = deepcopy(record)
    record["management_revenue_guidance_period"] = "full year 2027"
    record["guided_share_period"] = "fourth quarter ending December 31, 2027"
    record["growth_floor_period"] = "2028"
    record["analysis_year"] = 2027
    rendered = render_price_implied_valuation(record)
    assert "full year 2027 management guidance" in rendered
    assert "Conditional 2028 upper" in rendered
    assert "fourth quarter ending December 31, 2027" in rendered
    assert "2026 guidance" not in rendered and "2027 growth floor" not in rendered


@pytest.mark.unit
def test_legacy_report_adds_distinct_current_unavailable_assessment_once():
    from tradingagents.reporting import prepare_report_state

    legacy = {"asset_type": "stock", "final_trade_decision": "Legacy decision\n\n### What the price implies\nOriginal model prose"}
    first = prepare_report_state(legacy)
    second = prepare_report_state(first)
    assert first["final_trade_decision"] == second["final_trade_decision"]
    assert first["final_trade_decision"].count("### Current price-implied assessment") == 1
    assert "Legacy evidence was not validated" in first["final_trade_decision"]
    assert legacy["final_trade_decision"] == "Legacy decision\n\n### What the price implies\nOriginal model prose"
