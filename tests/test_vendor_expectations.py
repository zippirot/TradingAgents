from datetime import UTC, datetime

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo.expectations import (
    VendorExpectations,
    compare_guidance_consensus,
    get_vendor_expectations,
)

NOW = datetime(2026, 11, 5, 18, tzinfo=UTC)


class FakeTicker:
    def __init__(self, symbol):
        assert symbol == "DOCN"

    def get_revenue_estimate(self):
        return pd.DataFrame(
            {
                "numberOfAnalysts": [9],
                "avg": [210_000_000],
                "low": [205_000_000],
                "high": [215_000_000],
                "currency": ["USD"],
            },
            index=["0q"],
        )

    def get_earnings_estimate(self):
        return pd.DataFrame(
            {
                "numberOfAnalysts": [8],
                "avg": [0.45],
                "low": [0.40],
                "high": [0.49],
                "currency": ["USD"],
                "methodology": ["normalized"],
            },
            index=["0q"],
        )

    def get_analyst_price_targets(self):
        return {"low": 35, "mean": 42, "high": 50}

    def get_earnings_history(self):
        return pd.DataFrame(
            {
                "epsEstimate": [0.42],
                "epsActual": [0.46],
                "epsDifference": [0.04],
                "surprisePercent": [9.5],
                "methodology": ["normalized"],
            },
            index=pd.to_datetime(["2026-09-30"]),
        )

    def get_eps_revisions(self):
        return pd.DataFrame(
            {
                "upLast7days": [2],
                "downLast7days": [1],
                "upLast30days": [4],
                "downLast30days": [2],
                "methodology": ["normalized"],
            },
            index=["0q"],
        )


@pytest.mark.unit
def test_live_reads_typed_partial_vendor_data_without_claiming_comparability(monkeypatch):
    import tradingagents.dataflows.vendors.yahoo.expectations as module

    monkeypatch.setattr(module.yf, "Ticker", FakeTicker)
    result = get_vendor_expectations("docn", "2026-11-05", observed_at=NOW)
    assert result.status == "available"
    assert result.label == "vendor consensus, unverified"
    assert result.retrieved_at == NOW
    assert result.vendor_as_of is None
    assert result.estimates[0].period_code == "0q"
    assert result.estimates[0].period_start is None
    assert result.estimates[0].period_end is None
    assert result.estimates[0].currency == "USD"
    assert result.estimates[0].unit == "USD"
    assert result.estimates[1].basis == "normalized"
    assert result.price_targets[0].currency is None
    assert result.surprises[0].period_end == "2026-09-30"
    assert result.snapshot_hash
    assert VendorExpectations.model_validate(result.model_dump(mode="json")) == result
    comparison = compare_guidance_consensus(
        {
            "metric": "revenue",
            "period_start": "2026-10-01",
            "period_end": "2026-12-31",
            "currency": "USD",
            "unit": "USD",
            "basis": "gaap",
            "guidance_low": "200000000",
        },
        result,
    )
    assert comparison["status"] == "unavailable"


@pytest.mark.unit
def test_historical_blocks_live_fetch_and_accepts_only_original_snapshot(monkeypatch):
    import tradingagents.dataflows.vendors.yahoo.expectations as module

    monkeypatch.setattr(module.yf, "Ticker", FakeTicker)
    original = get_vendor_expectations("DOCN", "2026-11-05", observed_at=NOW)
    monkeypatch.setattr(module.yf, "Ticker", lambda _: pytest.fail("historical fetch"))
    missing = get_vendor_expectations(
        "DOCN", "2026-11-06", observed_at=datetime(2026, 11, 8, tzinfo=UTC)
    )
    assert missing.status == "unavailable"
    replay = get_vendor_expectations(
        "DOCN",
        "2026-11-05",
        observed_at=datetime(2026, 11, 8, tzinfo=UTC),
        retained_snapshot=original.model_dump(mode="json"),
    )
    assert replay == original
    tampered = original.model_dump(mode="json")
    tampered["estimates"][0]["average"] = "999"
    assert (
        get_vendor_expectations(
            "DOCN",
            "2026-11-05",
            observed_at=datetime(2026, 11, 8, tzinfo=UTC),
            retained_snapshot=tampered,
        ).status
        == "unavailable"
    )
    assert (
        get_vendor_expectations(
            "OTHER",
            "2026-11-05",
            observed_at=datetime(2026, 11, 8, tzinfo=UTC),
            retained_snapshot=original.model_dump(mode="json"),
        ).status
        == "unavailable"
    )


@pytest.mark.unit
def test_partial_failure_and_exact_comparison_require_all_dimensions(monkeypatch):
    import tradingagents.dataflows.vendors.yahoo.expectations as module

    class Partial(FakeTicker):
        def get_earnings_estimate(self):
            raise RuntimeError("Yahoo failed")

    monkeypatch.setattr(module.yf, "Ticker", Partial)
    result = get_vendor_expectations("DOCN", "2026-11-05", observed_at=NOW)
    assert result.status == "partial"
    assert len(result.estimates) == 1
    assert result.estimates[0].metric == "revenue"
    row = result.model_dump(mode="json")
    row["estimates"][0].update(
        {"period_start": "2026-10-01", "period_end": "2026-12-31", "basis": "gaap"}
    )
    # A modified snapshot has no valid hash, but the comparison helper is pure and dimension-bound.
    guidance = {
        "metric": "revenue",
        "period_start": "2026-10-01",
        "period_end": "2026-12-31",
        "currency": "USD",
        "unit": "USD",
        "basis": "gaap",
        "guidance_low": "200000000",
        "guidance_high": "220000000",
    }
    assert compare_guidance_consensus(guidance, row)["status"] == "comparable"
    row["estimates"][0]["basis"] = None
    assert compare_guidance_consensus(guidance, row)["status"] == "unavailable"


@pytest.mark.unit
def test_analysis_zone_day_allows_same_local_day_after_utc_midnight(monkeypatch):
    import tradingagents.dataflows.vendors.yahoo.expectations as module

    monkeypatch.setattr(module.yf, "Ticker", FakeTicker)
    observed = datetime(2026, 11, 6, 2, tzinfo=UTC)  # Nov 5, 19:00 Denver
    current = get_vendor_expectations(
        "DOCN", "2026-11-05", observed_at=observed, analysis_timezone="America/Denver"
    )
    assert current.status == "available"
    monkeypatch.setattr(module.yf, "Ticker", lambda _: pytest.fail("historical fetch"))
    historical = get_vendor_expectations(
        "DOCN", "2026-11-05", observed_at=observed, analysis_timezone="UTC"
    )
    assert historical.status == "unavailable"
    with pytest.raises(ValueError, match="timezone"):
        get_vendor_expectations("DOCN", "2026-11-05", observed_at=datetime(2026, 11, 5, 18))


@pytest.mark.unit
def test_bad_numbers_and_missing_sections_are_visible(monkeypatch):
    import tradingagents.dataflows.vendors.yahoo.expectations as module

    class Malformed(FakeTicker):
        def get_revenue_estimate(self):
            return pd.DataFrame(
                {
                    "numberOfAnalysts": [-2],
                    "avg": [float("nan")],
                    "low": [-1],
                    "high": [205_000_000],
                    "currency": ["USD"],
                },
                index=["0q"],
            )

        def get_analyst_price_targets(self):
            return {"low": -5, "mean": float("nan"), "high": 50}

        def get_earnings_history(self):
            return pd.DataFrame()

        def get_eps_revisions(self):
            raise RuntimeError("vendor broken")

    monkeypatch.setattr(module.yf, "Ticker", Malformed)
    result = get_vendor_expectations("DOCN", "2026-11-05", observed_at=NOW)
    assert result.status == "partial"
    assert result.estimates[0].analyst_count is None
    assert result.estimates[0].average is None
    assert result.estimates[0].low is None
    assert result.price_targets[0].low is None
    assert result.price_targets[0].mean is None
    assert result.section_reasons["surprises"] == "Yahoo returned no usable data"
    assert "failed" in result.section_reasons["revisions"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value",
    [
        ("period_end", "2027-03-31"),
        ("metric", "eps"),
        ("currency", "EUR"),
        ("unit", "USD/share"),
        ("basis", "normalized"),
    ],
)
def test_guidance_comparison_rejects_each_mismatched_dimension(field, value):
    guidance = {
        "metric": "revenue",
        "period_start": "2026-10-01",
        "period_end": "2026-12-31",
        "currency": "USD",
        "unit": "USD",
        "basis": "gaap",
        "guidance_low": "200",
        "guidance_high": "220",
    }
    estimate = {
        **{
            key: guidance[key]
            for key in ("metric", "period_start", "period_end", "currency", "unit", "basis")
        },
        "average": "215",
    }
    estimate[field] = value
    source = {"status": "available", "estimates": [estimate]}
    assert compare_guidance_consensus(guidance, source)["status"] == "unavailable"
