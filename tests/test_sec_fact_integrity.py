"""Exact SEC values and filing-context preservation at the vendor boundary."""

from copy import deepcopy

import pytest

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import sec_edgar as sec


def fact(value=281123456, **updates):
    result = {
        "val": value,
        "start": "2026-04-01",
        "end": "2026-06-30",
        "filed": "2026-08-04",
        "form": "10-Q",
        "accn": "0001628280-26-052556",
    }
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


@pytest.mark.parametrize(
    "bad",
    [
        {"segment": {"axis": "ProductAxis", "value": "Cloud"}},
        {"dimensions": {"ProductAxis": "Cloud"}},
        {"val": float("nan")},
        {"val": float("inf")},
        {"val": True},
        {"start": "invalid"},
        {"filed": "invalid"},
        {"end": "2027-01-01"},
    ],
)
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

    data = json.loads(
        (Path(__file__).parent / "fixtures/docn_2026q2/companyfacts.json").read_text()
    )
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


def test_later_filing_cannot_silently_change_the_period_start():
    data = dataset([fact(), fact(999, start="2026-04-02", filed="2026-09-01")])
    with pytest.raises(VendorUnavailableError, match="ambiguous"):
        sec._as_of_records(data, ("Revenues",), "2026-10-19", ((60, 115),))


@pytest.mark.parametrize("data", [{"Revenues": [1]}, {"Revenues": {"units": [1]}}])
def test_malformed_fact_container_fails_as_vendor_error(data):
    with pytest.raises(VendorUnavailableError):
        sec._as_of_records(data, ("Revenues",), "2026-10-19", ((60, 115),))


def test_structured_evidence_exposes_exact_docn_facts_and_sources(monkeypatch):
    import json
    from pathlib import Path

    from tradingagents.dataflows.financial_evidence import EvidencePackage

    data = json.loads(
        (Path(__file__).parent / "fixtures/docn_2026q2/companyfacts.json").read_text()
    )
    monkeypatch.setattr(sec, "cik_for", lambda ticker: "0001582961")
    monkeypatch.setattr(sec, "_cached_json", lambda *a: data)
    package = sec.get_financial_evidence("DOCN", "2026-10-19")
    assert EvidencePackage.model_validate_json(package.model_dump_json()) == package
    debt = [
        f
        for f in package.facts
        if f.metric == "Long-term Borrowings (including current)"
        and str(f.period_end) == "2026-06-30"
    ]
    assert len(debt) == 1 and debt[0].value == 921053000
    assert debt[0].locator.startswith("us-gaap/LongTermDebt/")
    source = {s.source_id: s for s in package.sources}[debt[0].source_ids[0]]
    assert source.accession and str(source.filed_date) <= "2026-10-19"
    assert len(source.content_hash) == 64
    assert len({f.period_end for f in package.facts}) <= 17
    missing = [f for f in package.facts if f.value is None]
    assert all(f.missing_reason for f in missing)


def test_docn_tool_view_is_bounded_with_valid_references_and_latest_metrics(monkeypatch):
    import json
    from pathlib import Path

    from tradingagents.dataflows.financial_evidence import EvidencePackage, bounded_evidence_view

    data = json.loads(
        (Path(__file__).parent / "fixtures/docn_2026q2/companyfacts.json").read_text()
    )
    monkeypatch.setattr(sec, "cik_for", lambda ticker: "0001582961")
    monkeypatch.setattr(sec, "_cached_json", lambda *a: data)
    package = sec.get_financial_evidence("DOCN", "2026-10-19")
    view = bounded_evidence_view(package)
    assert len(view.model_dump_json()) <= 64000
    assert {f.metric for f in view.facts} == {f.metric for f in package.facts}
    assert len(view.facts) < len(package.facts)
    assert any("bounded" in w for w in view.warnings)
    assert EvidencePackage.model_validate_json(view.model_dump_json()) == view


def test_bounded_view_retains_reconciliation_warning_inputs(monkeypatch):
    import json
    import re
    from pathlib import Path

    from tradingagents.dataflows.financial_evidence import bounded_evidence_view

    data = json.loads(
        (Path(__file__).parent / "fixtures/docn_2026q2/companyfacts.json").read_text()
    )
    monkeypatch.setattr(sec, "cik_for", lambda ticker: "0001582961")
    monkeypatch.setattr(sec, "_cached_json", lambda *a: data)
    view = bounded_evidence_view(sec.get_financial_evidence("DOCN", "2026-10-19"))
    ids = {fact.fact_id for fact in view.facts}
    for warning in view.warnings:
        assert set(re.findall(r"\b[0-9a-f]{64}\b", warning)) <= ids


def test_docn_equity_movements_keep_statement_specific_values(monkeypatch):
    import json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).parent / "fixtures/docn_2026q2/companyfacts.json").read_text()
    )
    monkeypatch.setattr(sec, "cik_for", lambda ticker: "0001582961")
    monkeypatch.setattr(sec, "_cached_json", lambda *a: data)
    package = sec.get_financial_evidence("DOCN", "2026-10-19")
    expected = {
        "Other Comprehensive Income Attributable to Parent": -796000,
        "Employee Stock Purchase Plan Issuance Value": 2494000,
    }
    for metric, value in expected.items():
        found = [
            fact
            for fact in package.facts
            if fact.metric == metric
            and str(fact.period_start) == "2026-01-01"
            and str(fact.period_end) == "2026-06-30"
        ]
        assert len(found) == 1 and found[0].value == value
