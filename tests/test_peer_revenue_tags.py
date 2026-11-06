"""Reported revenue aliases retain definition and tag preference."""
import pytest

from tradingagents.dataflows.vendors import sec_edgar


@pytest.mark.parametrize("peer_mode", [False, True])
@pytest.mark.parametrize("preferred", [False, True])
def test_reported_tax_inclusive_revenue_is_peer_only_and_never_added(monkeypatch, tmp_path, preferred, peer_mode):
    ends = [("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
            ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30")]
    records = [{"start": start, "end": end, "val": 100, "filed": "2026-11-05",
                "form": "10-Q", "accn": "0001086222-26-000100"} for start, end in ends]
    gaap = {
        "Assets": {"units": {"USD": [{"end": "2026-09-30", "val": 500, "filed": "2026-11-05", "form": "10-Q"}]}},
        "RevenueFromContractWithCustomerIncludingAssessedTax": {"units": {"USD": records}},
    }
    if preferred:
        gaap["RevenueFromContractWithCustomerExcludingAssessedTax"] = {
            "units": {"USD": [{**records[-1], "val": 110}]}}
    monkeypatch.setattr(sec_edgar, "cik_for", lambda ticker: "0001086222")
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(sec_edgar, "_cached_json", lambda *args: {"cik": 1086222, "facts": {"us-gaap": gaap}})
    package = (sec_edgar.get_financial_evidence("AKAM", "2026-11-05", peer_revenue_definitions=True)
               if peer_mode else sec_edgar.get_financial_evidence("AKAM", "2026-11-05"))
    revenue = [f for f in package.facts if f.metric == "Revenue" and f.origin == "reported" and f.value is not None]
    assert len(revenue) == (4 if peer_mode else 1 if preferred else 0)
    if not revenue:
        return
    latest = next(f for f in revenue if str(f.period_end) == "2026-09-30")
    assert latest.value == (110 if preferred else 100)
    assert ("ExcludingAssessedTax" if preferred else "IncludingAssessedTax") in latest.locator
