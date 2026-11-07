"""Portable source-backed checks for management guidance valuation ranges."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

import pytest

from tests.test_disclosure_context import mutate_block, recorded_package
from tests.test_price_observation import install
from tradingagents.agents.valuation_comparison import (
    price_implied_valuation,
    render_price_implied_valuation,
)
from tradingagents.dataflows.financial_evidence import (
    EvidencePackage,
    FinancialFact,
    SourceRecord,
    derive_ttm,
)
from tradingagents.dataflows.vendors.yahoo.price_observation import get_price_observation


def six(value):
    return Decimal(value).quantize(Decimal("0.000001"))


def source_state(monkeypatch):
    disclosure = recorded_package()
    doc = disclosure.documents[0]
    source = SourceRecord(
        source_id=doc.source_id, cik=disclosure.cik, url=doc.url,
        filed_date=doc.filing.filed_date, retrieved_at=doc.retrieved_at,
        content_hash=doc.content_hash, locator="document",
        accession=doc.filing.accession, form=doc.filing.form,
    )
    synthetic_facts_source = SourceRecord(
        source_id="synthetic-financials", cik=disclosure.cik,
        url="https://example.test/synthetic-financials", filed_date="2026-11-03",
        retrieved_at="2026-11-04T20:00:00+00:00", content_hash="f" * 64,
        locator="synthetic", accession="synthetic-2026-11-03", form="10-Q",
    )
    facts = []

    def instant(identifier, metric, value, unit="USD"):
        facts.append(FinancialFact(
            fact_id=identifier, metric=metric, value=value, unit=unit,
            cik=disclosure.cik, period_end="2026-09-30", as_of=disclosure.as_of,
            source_ids=(synthetic_facts_source.source_id,), locator=f"synthetic/{identifier}",
        ))

    instant("assets", "Total Assets", 4_000_000_000)
    instant("shares", "Common Shares Outstanding", 100_000_000, "shares")
    instant("borrowings", "Total Borrowings", 200_000_000)
    instant("finance", "Finance Lease and Equipment Obligations", 30_000_000)
    instant("operating", "Operating Lease Liabilities", 40_000_000)
    instant("cash", "Cash and Equivalents", 100_000_000)
    quarters = []
    for i, (start, end) in enumerate((
        ("2025-10-01", "2025-12-31"),
        ("2026-01-01", "2026-03-31"),
        ("2026-04-01", "2026-06-30"),
        ("2026-07-01", "2026-09-30"),
    )):
        quarters.append(FinancialFact(
            fact_id=f"revenue-{i}", metric="Revenue", value=250_000_000,
            unit="USD", cik=disclosure.cik, period_start=start, period_end=end,
            as_of=disclosure.as_of, source_ids=(synthetic_facts_source.source_id,),
            locator=f"synthetic/revenue-{i}",
        ))
    facts.extend(quarters)
    facts.append(derive_ttm(quarters))
    evidence = EvidencePackage(cik=disclosure.cik, as_of=disclosure.as_of,
                               sources=(source, synthetic_facts_source), facts=tuple(facts))
    install(monkeypatch, now="2026-11-04T22:00:00+00:00",
            dates=("2026-09-30", "2026-11-04"), closes=(18, 20),
            metadata={"currentTradingPeriod": {"regular": {
                "end": datetime.fromisoformat("2026-11-04T21:00:00+00:00")}}})
    quote = get_price_observation("DOCN", "2026-11-04", "2026-09-30")
    assert quote["status"] == "available", quote
    return {
        "asset_type": "stock", "company_of_interest": "DOCN", "trade_date": "2026-11-04",
        "issuer_identity": {"ticker": "DOCN", "cik": disclosure.cik,
                            "as_of": "2026-11-04", "source": "SEC issuer map"},
        "price_observation": quote, "financial_evidence": evidence.model_dump(mode="json"),
        "disclosure_evidence": {"packages": [disclosure.model_dump(mode="json")]},
    }


def _guidance_values(state):
    result = price_implied_valuation(state)
    return (result["management_revenue_guidance_range_usd"],
            result["guided_diluted_weighted_average_shares_range"],
            result["growth_floor_percent"])


def _excerpt(package, locators):
    copy = deepcopy(package)
    copy["documents"][0]["blocks"] = [
        block for block in copy["documents"][0]["blocks"] if block["locator"] in locators]
    return copy


@pytest.mark.unit
@pytest.mark.parametrize("copies", ["full", "excerpt", "repeat_excerpt"])
@pytest.mark.parametrize("reverse", [False, True])
def test_consistent_repeated_source_preserves_guidance(monkeypatch, copies, reverse):
    state = source_state(monkeypatch)
    full = state["disclosure_evidence"]["packages"][0]
    excerpt = _excerpt(full, {"block-24", "block-4", "block-44", "block-46"})
    repeated = full if copies == "full" else excerpt
    packages = [full, repeated] if copies != "repeat_excerpt" else [full, excerpt, excerpt]
    state["disclosure_evidence"]["packages"] = list(reversed(packages)) if reverse else packages
    assert _guidance_values(state) == (["1208000000", "1211000000"],
                                       ["128000000", "129000000"], "60")


@pytest.mark.unit
@pytest.mark.parametrize("change", ["text", "section", "currency", "hash", "filing_cik",
                                    "filing_form", "package_cik", "package_cutoff"])
@pytest.mark.parametrize("bad_first", [False, True])
def test_conflicting_repeated_source_stays_invalid_after_matching_copy(monkeypatch, change, bad_first):
    state = source_state(monkeypatch)
    full = state["disclosure_evidence"]["packages"][0]
    bad = _excerpt(full, {"block-46"})
    doc = bad["documents"][0]
    if change in {"text", "section"}:
        doc["blocks"][0][change] += " conflicting"
    elif change == "currency":
        doc["blocks"][0]["currency"] = "EUR"
    elif change == "hash":
        doc["content_hash"] = "0" * 64
    elif change == "package_cik":
        bad["cik"] = "0000000000"
    elif change == "package_cutoff":
        bad["as_of"] = "2026-11-03"
    else:
        doc["filing"][change.removeprefix("filing_")] = "0000000000" if change == "filing_cik" else "10-Q"
    state["disclosure_evidence"]["packages"] = ([bad, full, deepcopy(full)] if bad_first
                                                    else [full, bad, deepcopy(full)])
    assert _guidance_values(state) == (None, None, None)


@pytest.mark.unit
def test_persisted_claims_do_not_supply_missing_or_forged_guidance(monkeypatch):
    state = source_state(monkeypatch)
    original = state["disclosure_evidence"]["packages"][0]
    state["disclosure_evidence"]["packages"] = [_excerpt(original, {"block-24"})]
    state["disclosure_evidence"]["deterministic_extraction"] = {
        "claims": [{"metric": "Total revenue", "value": "999", "period": "full year 2026"}]}
    assert _guidance_values(state) == (None, None, None)


@pytest.mark.unit
def test_quarterly_revenue_cannot_replace_missing_full_year_guidance(monkeypatch):
    state = source_state(monkeypatch)
    package = state["disclosure_evidence"]["packages"][0]
    state["disclosure_evidence"]["packages"] = [_excerpt(package, {
        "block-42", "block-43", "block-44", "block-45", "block-4"})]
    result = price_implied_valuation(state)
    assert result["management_revenue_guidance_range_usd"] is None


@pytest.mark.unit
def test_source_discovered_guidance_uses_both_denominator_and_share_bounds(monkeypatch):
    state = source_state(monkeypatch)
    state["target_validation"] = {"status": "unsupported", "request": None}
    result = price_implied_valuation(state)
    assert result["status"] == "available"
    assert result["management_revenue_guidance_range_usd"] == ["1208000000", "1211000000"]
    assert result["guided_diluted_weighted_average_shares_range"] == ["128000000", "129000000"]
    assert (result["management_revenue_guidance_period"], result["growth_floor_period"],
            result["guided_share_period"]) == (
                "full year 2026", "2027", "fourth quarter ending December 31, 2026")
    assert result["growth_floor_percent"] == "60"
    assert {ref["locator"] for ref in result["disclosure_references"].values()} == {
        "block-46", "block-44", "block-4"}
    assert [row["net_obligations_usd"] for row in result["rows"]] == [
        "100000000", "130000000", "170000000"]
    borrowings = result["rows"][0]
    assert Decimal(borrowings["numerator_usd"]) == 2_100_000_000
    assert [six(x) for x in borrowings["ratios"]["guidance_range"]] == [
        six(Decimal(2100) / Decimal(1211)), six(Decimal(2100) / Decimal(1208))]
    assert six(borrowings["ratios"]["growth_floor_conditional_upper"]) == six(
        Decimal(2100) / Decimal("1932.8"))
    sensitivity = borrowings["guided_diluted_weighted_average_share_sensitivity"]
    assert [Decimal(x) for x in sensitivity["numerator_range_usd"]] == [
        2_660_000_000, 2_680_000_000]
    assert [six(x) for x in sensitivity["ratios"]["guidance_range"]] == [
        six(Decimal(2660) / Decimal(1211)), six(Decimal(2680) / Decimal(1208))]
    assert six(sensitivity["ratios"]["growth_floor_conditional_upper"]) == six(
        Decimal(2680) / Decimal("1932.8"))
    text = render_price_implied_valuation(result)
    assert "full year 2026" in text and "2027 conditional upper" in text
    assert "not current shares outstanding" in text


@pytest.mark.unit
def test_source_identity_mismatch_withholds_guidance_but_keeps_trailing(monkeypatch):
    state = source_state(monkeypatch)
    source = state["financial_evidence"]["sources"][0]
    source["content_hash"] = "0" * 64
    result = price_implied_valuation(state)
    assert result["status"] == "available"
    assert result["trailing_revenue_usd"] == "1000000000"
    assert result["management_revenue_guidance_range_usd"] is None
    assert result["guided_diluted_weighted_average_shares_range"] is None
    assert result["growth_floor_percent"] is None
    assert all("guidance_range" not in row["ratios"] for row in result["rows"])

    state = source_state(monkeypatch)
    state["disclosure_evidence"]["packages"][0]["cik"] = "0000000000"
    result = price_implied_valuation(state)
    assert result["status"] == "available"
    assert result["management_revenue_guidance_range_usd"] is None
    assert result["guided_diluted_weighted_average_shares_range"] is None


@pytest.mark.unit
def test_nonpositive_revenue_and_unsupported_growth_do_not_publish_ratios(monkeypatch):
    state = source_state(monkeypatch)
    state["financial_evidence"]["facts"] = [
        fact for fact in state["financial_evidence"]["facts"] if fact["metric"] != "Revenue"]
    result = price_implied_valuation(state)
    assert result["trailing_revenue_usd"] is None
    assert all("trailing_revenue" not in row["ratios"] for row in result["rows"])
    assert all("guidance_range" in row["ratios"] for row in result["rows"])

    state = source_state(monkeypatch)
    package = recorded_package()
    block = next(block for block in package.documents[0].blocks if block.locator == "block-4")
    package = mutate_block(package, "block-4", text=block.text.replace("60%+", "0%+"))
    state["disclosure_evidence"] = {"packages": [package.model_dump(mode="json")]}
    result = price_implied_valuation(state)
    assert result["growth_floor_percent"] is None
    assert all("growth_floor_conditional_upper" not in row["ratios"] for row in result["rows"])
    assert all("guidance_range" in row["ratios"] for row in result["rows"])

    state = source_state(monkeypatch)
    package = recorded_package()
    revenue = next(block for block in package.documents[0].blocks if block.locator == "block-46")
    package = mutate_block(package, "block-46",
                           text=revenue.text.replace("$1.208 to $1.211", "$0 to $0"))
    shares = next(block for block in package.documents[0].blocks if block.locator == "block-44")
    package = mutate_block(package, "block-44",
                           text=shares.text.replace("128 to 129", "0 to 0"))
    state["disclosure_evidence"] = {"packages": [package.model_dump(mode="json")]}
    result = price_implied_valuation(state)
    assert result["management_revenue_guidance_range_usd"] is None
    assert result["guided_diluted_weighted_average_shares_range"] is None
    assert all("guidance_range" not in row["ratios"] for row in result["rows"])
    assert all("guided_diluted_weighted_average_share_sensitivity" not in row for row in result["rows"])
