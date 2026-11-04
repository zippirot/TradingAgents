"""Exact SEC values and filing-context preservation at the vendor boundary."""
from copy import deepcopy

import pytest

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import sec_edgar as sec


def fact(value=281123456, **updates):
    result = {"val": value, "start": "2026-04-01", "end": "2026-06-30",
              "filed": "2026-08-04", "form": "10-Q", "accn": "0001628280-26-052556"}
    result.update(updates)
    return result


def dataset(rows, unit="USD"):
    return {"Revenues": {"units": {unit: rows}}}


def test_exact_precision_reaches_existing_statement_tool(monkeypatch):
    monkeypatch.setattr(sec, "cik_for", lambda ticker: "0001582961")
    monkeypatch.setattr(sec, "_cached_json", lambda *a: {"facts": {"us-gaap": dataset([fact()])}})
    report = sec.get_income_statement("DOCN", "quarterly", "2026-10-19")
    assert "Revenue,281.123456" in report


def test_selected_record_retains_filing_tag_unit_and_period_without_mutation():
    data = dataset([fact()])
    original = deepcopy(data)
    records = sec._as_of_records(data, ("Revenues",), "2026-10-19", ((60, 115),))
    selected = records[("2026-06-30", 0)]
    assert selected == {**fact(), "tag": "Revenues", "unit": "USD"}
    selected["val"] = 0
    assert data == original


def test_later_restatement_cannot_leak_into_earlier_record():
    data = dataset([fact(), fact(999, filed="2026-11-02", accn="later")])
    early = sec._as_of_records(data, ("Revenues",), "2026-10-19", ((60, 115),))
    late = sec._as_of_records(data, ("Revenues",), "2026-11-03", ((60, 115),))
    assert early[("2026-06-30", 0)]["val"] == 281123456
    assert late[("2026-06-30", 0)]["accn"] == "later"


def test_mixed_currency_row_is_not_relabelled_as_one_currency():
    data = dataset([fact()])
    data["Revenues"]["units"]["EUR"] = [fact(100, end="2025-06-30", start="2025-04-01")]
    with pytest.raises(VendorUnavailableError, match="unit"):
        sec._as_of(data, ("Revenues",), "2026-10-19", ((60, 115),))


@pytest.mark.parametrize("bad", [
    {"segment": {"axis": "ProductAxis", "value": "Cloud"}},
    {"dimensions": {"ProductAxis": "Cloud"}},
    {"val": float("nan")}, {"val": float("inf")}, {"val": True},
    {"start": "invalid"}, {"filed": "invalid"}, {"end": "2027-01-01"},
])
def test_invalid_or_dimensioned_values_do_not_replace_consolidated_fact(bad):
    data = dataset([fact(), fact(**bad)])
    records = sec._as_of_records(data, ("Revenues",), "2026-10-19", ((60, 115),))
    assert records[("2026-06-30", 0)]["val"] == 281123456


def test_same_filing_conflicting_periods_are_explicitly_ambiguous():
    data = dataset([fact(), fact(999, start="2026-03-31")])
    with pytest.raises(VendorUnavailableError, match="ambiguous"):
        sec._as_of_records(data, ("Revenues",), "2026-10-19", ((60, 115),))


def test_zero_is_retained_as_a_fact_not_missing():
    data = dataset([fact(0)])
    records = sec._as_of_records(data, ("Revenues",), "2026-10-19", ((60, 115),))
    assert records[("2026-06-30", 0)]["val"] == 0


def test_original_docn_disclosures_reach_statement_tools(monkeypatch):
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parent / "fixtures/docn_2026q2/companyfacts.json").read_text())
    monkeypatch.setattr(sec, "cik_for", lambda ticker: "0001582961")
    monkeypatch.setattr(sec, "_cached_json", lambda *a: data)
    balance = sec.get_balance_sheet("DOCN", "quarterly", "2026-10-19")
    cash = sec.get_cashflow("DOCN", "quarterly", "2026-10-19")
    income = sec.get_income_statement("DOCN", "quarterly", "2026-10-19")
    assert "Long-term Borrowings (including current)" in balance and "921.053" in balance
    assert "Finance Lease Liabilities" in balance and "409.834" in balance
    assert "Operating Lease Liabilities" in balance and "479.087" in balance
    assert "Common Stock Issuance Proceeds" in cash and "887.888" in cash
    assert "Noncash Finance Lease Additions" in cash and "414.902" in cash
    assert "Software Development Payments" in cash and "11.785" in cash
    assert "Diluted Earnings Numerator" in income and "36.827" in income
    assert "Weighted Average Diluted Shares (shares)" in income and "126548000" in income
