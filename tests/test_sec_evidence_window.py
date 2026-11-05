"""Bounded companyfacts selection validates only the eligible evidence window."""

from copy import deepcopy

import pytest

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import sec_edgar as sec


def row(year, quarter=1, *, annual=False, **updates):
    start = f"{year}-01-01" if annual else f"{year}-{(quarter - 1) * 3 + 1:02d}-01"
    end = f"{year}-12-31" if annual else f"{year}-{quarter * 3:02d}-{'30' if quarter in (2, 3) else '31'}"
    return dict(val=100, start=start, end=end, filed=f"{year + 1}-02-01",
                form="10-K" if annual else "10-Q", accn=f"{year}-{quarter}", **updates)


def install(monkeypatch, rows, conflicting, **extra_units):
    facts = {"Revenues": {"units": {"USD": rows, "EUR": [conflicting], **extra_units}}}
    monkeypatch.setattr(sec, "cik_for", lambda ticker: "0000000001")
    monkeypatch.setattr(sec, "_cached_json", lambda *args: {"cik": 1, "facts": {"us-gaap": facts}})
    return facts


@pytest.mark.parametrize("annual", [False, True])
def test_discarded_historical_ambiguity_does_not_abort_current_evidence(monkeypatch, annual):
    rows = ([row(y, annual=True) for y in range(2020, 2026)] if annual else
            [row(2020)] + [row(y, q) for y in range(2023, 2026) for q in range(1, 5)])
    facts = install(monkeypatch, rows, deepcopy(rows[0]))
    package = sec.get_financial_evidence("TEST", "2026-11-04")
    revenue = [f for f in package.facts if f.metric == "Revenue" and f.value is not None]
    assert revenue
    assert all(str(f.period_end) != rows[0]["end"] for f in revenue)
    assert all(f.unit == "USD" for f in revenue)
    # The legacy all-history selector remains strict.
    spans = ((300, 400),) if annual else ((60, 115),)
    with pytest.raises(VendorUnavailableError, match="period or unit ambiguous"):
        sec._as_of_records(facts, ("Revenues",), "2026-11-04", spans)


@pytest.mark.parametrize("annual", [False, True])
def test_ambiguity_inside_selected_window_still_fails(monkeypatch, annual):
    rows = [row(2025, annual=annual)]
    install(monkeypatch, rows, deepcopy(rows[0]))
    with pytest.raises(VendorUnavailableError, match="period or unit ambiguous"):
        sec.get_financial_evidence("TEST", "2026-11-04")


def test_ineligible_newer_rows_cannot_displace_eligible_ambiguous_period(monkeypatch):
    old = row(2020)
    future_filed = [dict(row(y, q), filed="2027-01-01")
                    for y in range(2023, 2026) for q in range(1, 5)]
    segmented = [dict(row(y, q), segment={"axis": "member"})
                 for y in range(2023, 2026) for q in range(1, 5)]
    install(monkeypatch, [old, *future_filed, *segmented], deepcopy(old))
    with pytest.raises(VendorUnavailableError, match="period or unit ambiguous"):
        sec.get_financial_evidence("TEST", "2026-11-04")


def test_nonannual_filings_cannot_displace_eligible_annual_ambiguity(monkeypatch):
    old = row(2020, annual=True)
    unsupported = [dict(row(y, annual=True), form="10-Q") for y in range(2021, 2026)]
    install(monkeypatch, [old, *unsupported], deepcopy(old))
    with pytest.raises(VendorUnavailableError, match="period or unit ambiguous"):
        sec.get_financial_evidence("TEST", "2026-11-04")


def test_selected_same_date_value_conflict_still_fails(monkeypatch):
    current = row(2025)
    facts = install(monkeypatch, [current, dict(current, val=999)], current)
    facts["Revenues"]["units"].pop("EUR")
    with pytest.raises(VendorUnavailableError, match="SEC fact ambiguous"):
        sec.get_financial_evidence("TEST", "2026-11-04")
