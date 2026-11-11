"""Plan L6b: a filer that reports no total-liabilities line, and one with outside interests.

Baseline 2026-11-11: WMT, INTC and LLY failed core_statements and balance_sheet for want of a Total
Liabilities fact; RTX's balance left a residual equal to its noncontrolling and temporary equity.
"""
from datetime import date
from decimal import Decimal

import pytest

from tradingagents.agents.accounting_checks import (
    check_assets_equal_filed_total,
    check_balance_sheet_with_interests,
)
from tradingagents.agents.evidence_validation import (
    latest_balance_check,
    validate_calculation_lineage,
)
from tradingagents.dataflows.financial_evidence import (
    LIABILITIES_AND_EQUITY,
    NONCONTROLLING,
    TOTAL_EQUITY,
    EvidencePackage,
    FinancialFact,
    SourceRecord,
    derive_total_liabilities,
    temporary_equity_metric,
)
from tradingagents.dataflows.vendors import sec_edgar

END, CUT = date(2026, 7, 31), date(2026, 11, 11)
REDEEMABLE = temporary_equity_metric("RedeemableNoncontrollingInterestEquityCarryingAmount")


def _fact(metric, value, tag=None):
    tag = tag or metric.replace(" ", "")
    return FinancialFact(fact_id=f"f-{metric}", metric=metric, value=Decimal(value), unit="USD", cik="0000104169",
                         period_end=END, as_of=CUT, source_ids=(f"s-{metric}",),
                         locator=f"us-gaap/{tag}/USD/instant/{END}/2026-08-28")


def _package(*facts):
    sources = tuple(SourceRecord(source_id=s, cik="0000104169", url="https://data.sec.gov/x", filed_date=date(2026, 8, 28),
                                 retrieved_at="2026-11-11T00:00:00+00:00", content_hash="0" * 64, locator="x",
                                 accession="0000104169-26-000001", form="10-Q")
                    for f in facts for s in f.source_ids if f.origin == "reported")
    return EvidencePackage(cik="0000104169", as_of=CUT, facts=facts, sources=sources)


ASSETS, TOTAL = _fact("Total Assets", "293914"), _fact(LIABILITIES_AND_EQUITY, "293914")
EQUITY, PARENT = _fact(TOTAL_EQUITY, "104506"), _fact("Stockholders Equity", "98238", "StockholdersEquity")
TEMP, NCI = _fact(REDEEMABLE, "293"), _fact(NONCONTROLLING, "6268")


def test_total_liabilities_is_the_filed_total_less_all_equity_and_is_replayable():
    derived = derive_total_liabilities((TOTAL, EQUITY, TEMP))
    assert derived.value == Decimal("189115") and derived.origin == "derived" and derived.metric == "Total Liabilities"
    assert derived.input_fact_ids == (TOTAL.fact_id, EQUITY.fact_id, TEMP.fact_id)
    package = _package(ASSETS, TOTAL, EQUITY, TEMP, NCI, PARENT, derived)
    assert validate_calculation_lineage(package) == []
    # The balance check for a derived total compares the two filed totals, not the derivation with itself.
    check = latest_balance_check(package)
    assert check.status == "pass" and check.method == "assets_equals_liabilities_and_equity_total_v1"
    assert check.input_fact_ids == (ASSETS.fact_id, TOTAL.fact_id)
    # Tampering with the derived value is caught by the replay.
    forged = derived.model_copy(update={"value": Decimal("1")})
    assert validate_calculation_lineage(_package(ASSETS, TOTAL, EQUITY, TEMP, forged)) != []


def test_filed_totals_that_disagree_fail_and_wrong_roles_do_not_derive():
    short = _fact("Total Assets", "293000")
    derived = derive_total_liabilities((TOTAL, EQUITY, TEMP))
    # With no known source rounding a nonzero residual is not assessed; either way it never passes.
    assert latest_balance_check(_package(short, TOTAL, EQUITY, TEMP, PARENT, derived)).status == "unavailable"
    assert check_assets_equal_filed_total(_package(short, TOTAL), short.fact_id, TOTAL.fact_id, {short.fact_id: 1, TOTAL.fact_id: 1}).status == "fail"
    for inputs in ((EQUITY, TOTAL), (TOTAL, NCI), (TOTAL, EQUITY, NCI), (TOTAL,), (TOTAL, EQUITY, TEMP, TEMP)):
        with pytest.raises(ValueError):
            derive_total_liabilities(inputs)


def test_reported_liabilities_with_outside_interests_balance_on_consolidated_equity():
    liabilities = _fact("Total Liabilities", "189115", "Liabilities")
    package = _package(ASSETS, liabilities, PARENT, EQUITY, TEMP, NCI)
    check = latest_balance_check(package)
    assert check.status == "pass" and check.method == "assets_equals_liabilities_temporary_and_total_equity_v1"
    # Leaving the temporary balance out no longer balances.
    assert check_balance_sheet_with_interests(package, ASSETS.fact_id, liabilities.fact_id, EQUITY.fact_id, (),
                                              dict.fromkeys((ASSETS.fact_id, liabilities.fact_id, EQUITY.fact_id), 1)).status == "fail"
    # A filer with no outside interests keeps the original identity.
    plain_equity = _fact("Stockholders Equity", "104799", "StockholdersEquity")
    assert latest_balance_check(_package(ASSETS, liabilities, plain_equity)).method == "assets_equals_liabilities_plus_equity_v1"


def _records(*facts):
    return {f.fact_id: f for f in facts}


def _data(extra=None):
    return {"facts": {"us-gaap": {"Assets": {"units": {"USD": [{"end": str(END), "val": 1}]}}}, **(extra or {})}}


def test_nothing_is_derived_when_equity_may_be_incomplete():
    derive = derive_total_liabilities
    end = str(END)
    assert sec_edgar._derived_total_liabilities(_data(), _records(TOTAL, EQUITY, TEMP, NCI), end, derive).value == Decimal("189115")
    # The parent's equity alone, with a noncontrolling balance in the filing: not all equity.
    assert sec_edgar._derived_total_liabilities(_data(), _records(TOTAL, PARENT, NCI), end, derive) is None
    # The parent's equity with no outside balance anywhere is all equity.
    assert sec_edgar._derived_total_liabilities(_data(), _records(TOTAL, PARENT), end, derive).value == Decimal("195676")
    # "Stockholders Equity" filled from the consolidated tag is not relied on as the parent's.
    mapped = _fact("Stockholders Equity", "104506", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
    assert sec_edgar._derived_total_liabilities(_data(), _records(TOTAL, mapped), end, derive) is None
    # A temporary or outside-equity balance under a tag code does not read, standard or the filer's own.
    own = {"wmt": {"RedeemablePreferredInterestOfSubsidiary": {"units": {"USD": [{"end": end, "val": 5}]}}}}
    assert sec_edgar._derived_total_liabilities(_data(own), _records(TOTAL, EQUITY), end, derive) is None
    # The same concept at another date, or as a flow over a period, says nothing about this balance sheet.
    other = {"wmt": {"RedeemablePreferredInterestOfSubsidiary": {"units": {"USD": [
        {"end": "2025-07-31", "val": 5}, {"start": "2026-05-01", "end": end, "val": 5}]}}}}
    assert sec_edgar._derived_total_liabilities(_data(other), _records(TOTAL, EQUITY), end, derive) is not None
    # No filed total, or two temporary balances that may overlap.
    assert sec_edgar._derived_total_liabilities(_data(), _records(EQUITY, TEMP), end, derive) is None
    second = _fact(temporary_equity_metric("TemporaryEquityCarryingAmountAttributableToParent"), "10")
    assert sec_edgar._derived_total_liabilities(_data(), _records(TOTAL, EQUITY, TEMP, second), end, derive) is None
