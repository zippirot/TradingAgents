"""CAT-shaped US-GAAP income facts keep consolidated and parent scopes distinct."""

from decimal import Decimal

import pytest

from tradingagents.dataflows import financial_evidence
from tradingagents.dataflows.vendors import sec_edgar

CIK = "0000018230"
ACCESSION = "0000018230-26-000057"
END = "2026-09-30"
FILED = "2026-11-04"


def _row(start, value, *, accession=ACCESSION, filed=FILED):
    return {
        "start": start, "end": END, "val": value, "filed": filed,
        "form": "10-Q", "accn": accession, "fy": 2026, "fp": "Q3",
    }


def _cat_excerpt():
    # Minimal public CompanyFacts records, preserving the reported periods,
    # signed NCI and common-stockholder numerator as distinct definitions.
    return {"cik": 18230, "facts": {"us-gaap": {
        "ProfitLoss": {"units": {"USD": [
            _row("2026-07-01", 3_286_000_000),
            _row("2026-01-01", 9_427_000_000),
        ]}},
        "NetIncomeLossAttributableToNoncontrollingInterest": {"units": {"USD": [
            _row("2026-07-01", -1_000_000),
            _row("2026-01-01", -2_000_000),
        ]}},
        "NetIncomeLossAvailableToCommonStockholdersBasic": {"units": {"USD": [
            _row("2026-07-01", 3_287_000_000),
            _row("2026-01-01", 9_429_000_000),
        ]}},
    }}}


def _package(monkeypatch, tmp_path, data):
    monkeypatch.setattr(sec_edgar, "cik_for", lambda _: CIK)
    monkeypatch.setattr(sec_edgar, "_cached_json", lambda *_: data)
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    return sec_edgar.get_financial_evidence("CAT", "2026-11-06")


@pytest.mark.unit
def test_cat_public_excerpt_derives_parent_income_with_both_source_ids(monkeypatch, tmp_path):
    package = _package(monkeypatch, tmp_path, _cat_excerpt())
    derived = [f for f in package.facts if f.metric == "Net Income" and f.value is not None]
    assert {(str(f.period_start), f.value) for f in derived} == {
        ("2026-07-01", Decimal(3_287_000_000)),
        ("2026-01-01", Decimal(9_429_000_000)),
    }
    assert all(f.origin == "derived" and f.formula_id == "consolidated_profit_less_nci_v1"
               and len(f.input_fact_ids) == len(f.source_ids) == 2 for f in derived)
    assert {f.metric for f in package.facts} >= {
        "Consolidated Profit (Loss)",
        "Net Income Attributable to Noncontrolling Interests",
        "Basic Earnings Numerator",
    }
    assert all(package.facts[[x.fact_id for x in package.facts].index(f.input_fact_ids[0])].metric
               == "Consolidated Profit (Loss)" for f in derived)


@pytest.mark.unit
@pytest.mark.parametrize("alter", [
    "missing_nci", "unit", "period", "accession", "filing_date",
])
def test_cat_income_bridge_rejects_nonidentical_source_context(monkeypatch, tmp_path, alter):
    data = _cat_excerpt()
    for tag in data["facts"]["us-gaap"].values():
        tag["units"]["USD"] = tag["units"]["USD"][:1]
    nci = data["facts"]["us-gaap"]["NetIncomeLossAttributableToNoncontrollingInterest"]
    if alter == "missing_nci":
        del data["facts"]["us-gaap"]["NetIncomeLossAttributableToNoncontrollingInterest"]
    elif alter == "unit":
        nci["units"]["EUR"] = nci["units"].pop("USD")
    elif alter == "period":
        for row in nci["units"]["USD"]:
            row["start"] = "2026-07-02"
    elif alter == "accession":
        for row in nci["units"]["USD"]:
            row["accn"] = "0000018230-26-000999"
    elif alter == "filing_date":
        for row in nci["units"]["USD"]:
            row["filed"] = "2026-11-05"
    package = _package(monkeypatch, tmp_path, data)
    assert not any(f.metric == "Net Income" and f.value is not None for f in package.facts)
    assert any(f.metric == "Basic Earnings Numerator" and f.value == 3_287_000_000
               for f in package.facts)


@pytest.mark.unit
def test_direct_net_income_tag_wins_over_available_bridge(monkeypatch, tmp_path):
    data = _cat_excerpt()
    data["facts"]["us-gaap"]["NetIncomeLoss"] = {"units": {
        "USD": [_row("2026-07-01", 3_280_000_000), _row("2026-01-01", 9_420_000_000)]
    }}
    package = _package(monkeypatch, tmp_path, data)
    income = [f for f in package.facts if f.metric == "Net Income" and f.value is not None]
    assert {(str(f.period_start), f.value, f.origin) for f in income} == {
        ("2026-07-01", Decimal(3_280_000_000), "reported"),
        ("2026-01-01", Decimal(9_420_000_000), "reported"),
    }


@pytest.mark.unit
def test_bridge_helper_rejects_changed_source_snapshot(monkeypatch, tmp_path):
    package = _package(monkeypatch, tmp_path, _cat_excerpt())
    profit = next(f for f in package.facts if f.metric == "Consolidated Profit (Loss)"
                  and str(f.period_start) == "2026-07-01")
    nci = next(f for f in package.facts
               if f.metric == "Net Income Attributable to Noncontrolling Interests"
               and str(f.period_start) == "2026-07-01")
    sources = {s.source_id: s for s in package.sources}
    changed = sources[nci.source_ids[0]].model_copy(update={"content_hash": "f" * 64})
    with pytest.raises(ValueError, match="source vintage"):
        financial_evidence.derive_parent_net_income(
            profit, nci, sources[profit.source_ids[0]], changed,
        )


def test_source_integrity_replays_parent_bridge_and_rejects_changed_result(monkeypatch, tmp_path):
    from tradingagents.agents.evidence_validation import validate_calculation_lineage
    package = _package(monkeypatch, tmp_path, _cat_excerpt())
    assert validate_calculation_lineage(package) == []
    income = next(f for f in package.facts if f.metric == "Net Income" and f.value is not None)
    changed = income.model_copy(update={"value": income.value + Decimal("1")})
    forged = package.model_copy(update={"facts": tuple(changed if f.fact_id == income.fact_id else f
                                                       for f in package.facts)})
    assert validate_calculation_lineage(forged)


def test_accepted_brief_shows_source_reconciled_parent_income_as_derived(monkeypatch, tmp_path):
    from tradingagents.agents.evidence_validation import canonical_accounting_context
    package = _package(monkeypatch, tmp_path, _cat_excerpt())
    brief = canonical_accounting_context(package, [])
    assert "Net Income: 3287000000 USD; 2026-07-01 to 2026-09-30; US-GAAP; derived" in brief
    assert "Consolidated Profit (Loss)" in brief
    assert "Net Income Attributable to Noncontrolling Interests" in brief
    assert "Net Income: unavailable" not in brief


def test_bridge_helper_rejects_fact_period_relabeling_against_source_locator(monkeypatch, tmp_path):
    package = _package(monkeypatch, tmp_path, _cat_excerpt())
    profit = next(f for f in package.facts if f.metric == "Consolidated Profit (Loss)"
                  and str(f.period_start) == "2026-07-01")
    nci = next(f for f in package.facts
               if f.metric == "Net Income Attributable to Noncontrolling Interests"
               and str(f.period_start) == "2026-07-01")
    sources = {s.source_id: s for s in package.sources}
    from datetime import date
    with pytest.raises(ValueError, match="source tags"):
        financial_evidence.derive_parent_net_income(
            profit.model_copy(update={"period_start": date(2026, 7, 2)}),
            nci.model_copy(update={"period_start": date(2026, 7, 2)}),
            sources[profit.source_ids[0]], sources[nci.source_ids[0]],
        )
