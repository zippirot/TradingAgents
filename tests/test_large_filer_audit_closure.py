"""Closure of the 2026-11-11 independent audit (run 27d78f8f) of the large-filer build."""
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tests.test_face_liabilities import (
    BASE,
    CIK,
    CUT,
    END,
    FIN,
    FLOW_BASE,
    P_START,
    UNIT,
    WHERE,
    _flow_instance,
    _package,
    _share_fact,
    _shares,
    calculation,
)
from tests.test_filed_equity import _instance, _structure, r
from tests.test_non_reliance_notice import QUARTER, _document
from tradingagents.agents.evidence_validation import disclosure_coverage_check
from tradingagents.dataflows.face_liabilities import financing_principal, with_financing_lines
from tradingagents.dataflows.filed_equity import roll_forward
from tradingagents.dataflows.filed_instance import InstanceError, parse_calculation, parse_instance
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord
from tradingagents.dataflows.vendors import sec_documents as docs

N_CIK, N_CUT, N_END = "0001582961", date(2026, 10, 19), date(2026, 6, 30)


def _scored(accession):
    """Evidence whose balance-date figures are sourced from the named filing."""
    fact = FinancialFact(fact_id="a", metric="Total Assets", value=Decimal(1), unit="USD", cik=N_CIK, period_end=N_END,
                         as_of=N_CUT, source_ids=("s",), locator="x")
    source = SourceRecord(source_id="s", cik=N_CIK, url="https://data.sec.gov/x", filed_date=date(2026, 8, 5),
                          retrieved_at=datetime(2026, 10, 19, tzinfo=UTC), content_hash="0" * 64, locator="x", form="10-Q",
                          accession=accession)
    return EvidencePackage(cik=N_CIK, as_of=N_CUT, facts=(fact,), sources=(source,))


def _coverage(evidence, *documents):
    return disclosure_coverage_check(evidence, docs.DisclosurePackage(cik=N_CIK, as_of=N_CUT, documents=documents))


def test_f1_only_an_amendment_whose_figures_are_the_ones_scored_clears_a_non_reliance_notice():
    notice = _document("8-K", date(2026, 9, 10), date(2026, 9, 10), "0001582961-26-000009", "4.02")
    amended = _document("10-Q/A", date(2026, 9, 25), N_END, "0001582961-26-000011")
    # An amendment is on file, but the scored figures still come from the original report: not a verified correction.
    blocked = _coverage(_scored(QUARTER[3]), _document(*QUARTER), notice, amended)
    assert blocked["status"] == "unavailable" and "0001582961-26-000009" in blocked["message"]
    # The scored figures come from the amended report itself: the restatement is what is being assessed.
    assert _coverage(_scored("0001582961-26-000011"), _document(*QUARTER), notice, amended)["status"] == "pass"
    # A notice issued after the annual report still in the package covers that report, even if the
    # quarterly report was issued later.
    annual = _document("10-K", date(2026, 2, 20), date(2025, 12, 31), "0001582961-26-000001")
    between = _document("8-K", date(2026, 7, 1), date(2026, 7, 1), "0001582961-26-000008", "4.02")
    assert _coverage(_scored(QUARTER[3]), annual, _document(*QUARTER), between)["status"] == "unavailable"
    # Issued before every periodic report in the package: it cannot cover any of them.
    early = _document("8-K", date(2026, 1, 15), date(2026, 1, 15), "0001582961-26-000000", "4.02")
    assert _coverage(_scored(QUARTER[3]), annual, _document(*QUARTER), early)["status"] == "pass"


def test_f2_a_declared_financing_line_that_is_filed_but_cannot_be_read_leaves_the_list_incomplete():
    children = ["us-gaap:RepaymentsOfLongTermDebt", "us-gaap:PaymentsOfDividends",
                "co:ProceedsFromEquipmentFinancing", "co:RepaymentsOfEquipmentFinancing"]
    readable = [(FIN, -500), ("us-gaap:RepaymentsOfLongTermDebt", -350), ("us-gaap:PaymentsOfDividends", -150)]
    # The two equipment lines are filed for the period only split across two axes at once; they offset, so
    # the readable lines still equal the total.
    two_axes = ('<context id="ytd2"><entity><identifier scheme="x">1</identifier><segment>'
                '<xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">co:AMember</xbrldi:explicitMember>'
                '<xbrldi:explicitMember dimension="us-gaap:DebtInstrumentAxis">co:BMember</xbrldi:explicitMember></segment></entity>'
                f'<period><startDate>{P_START}</startDate><endDate>{END}</endDate></period></context>'
                '<co:ProceedsFromEquipmentFinancing contextRef="ytd2" unitRef="usd" decimals="0">75</co:ProceedsFromEquipmentFinancing>'
                '<co:RepaymentsOfEquipmentFinancing contextRef="ytd2" unitRef="usd" decimals="0">-75</co:RepaymentsOfEquipmentFinancing>')
    package, notes = with_financing_lines(_package(*FLOW_BASE), parse_instance(_flow_instance(readable, two_axes)),
                                          parse_calculation(calculation({FIN: children})), **WHERE)
    assert any("not established" in note for note in notes) and financing_principal(package, P_START, END) == {}
    # The same declared lines with nothing filed for the period are nil by the filer's arithmetic, as before.
    clean, _ = with_financing_lines(_package(*FLOW_BASE), parse_instance(_flow_instance(readable)),
                                    parse_calculation(calculation({FIN: children})), **WHERE)
    assert "equipment" in financing_principal(clean, P_START, END)


def test_f3_a_filer_with_outside_interests_is_not_reconciled_on_the_parents_equity():
    # Parent equity is filed at both dates and its movements happen to add up, but the filing also carries
    # consolidated equity at the balance date: the total column is consolidated, so this is the wrong owner.
    rows = [r("StockholdersEquity", 1000, "open"), r("StockholdersEquity", 1130, "close"), r("NetIncomeLoss", 200),
            r("DividendsCommonStockCash", 50), r("StockRepurchasedAndRetiredDuringPeriodValue", 20),
            r("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", 1190, "close")]
    with pytest.raises(InstanceError, match="noncontrolling"):
        roll_forward(_instance(rows), _structure(), END)
    minority = [*rows[:5], r("MinorityInterest", 60, "close")]
    with pytest.raises(InstanceError, match="noncontrolling"):
        roll_forward(_instance(minority), _structure(), END)
    assert roll_forward(_instance(rows[:5]), _structure(), END).total_concept == "us-gaap:StockholdersEquity"


def test_f4_a_share_count_split_along_an_axis_that_is_not_the_class_of_stock_is_not_the_companys_count():
    assert _shares(UNIT + _share_fact("us-gaap:CommonStockSharesOutstanding", 880, "seg_a"))[0] == []
    class_axis = ('<context id="cls"><entity><identifier scheme="x">1</identifier><segment>'
                  '<xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonStockMember</xbrldi:explicitMember>'
                  f'</segment></entity><period><instant>{END}</instant></period></context>')
    (one_class,), _ = _shares(UNIT + class_axis + _share_fact("us-gaap:CommonStockSharesOutstanding", 880, "cls"))
    assert one_class.value == 880
    # A cover count dated the balance date is used ahead of a class-axis count.
    (cover,), _ = _shares(UNIT + class_axis + _share_fact("us-gaap:CommonStockSharesOutstanding", 880, "cls")
                          + _share_fact("dei:EntityCommonStockSharesOutstanding", 879))
    assert cover.value == 879 and BASE and CIK and CUT


def test_f7_the_reason_names_the_input_that_is_actually_missing():
    from tests.test_face_liabilities import _fact, _widen
    from tradingagents.agents.evidence_validation import obligation_checks, obligation_verdict

    # No unrestricted cash: the reason says so instead of naming lease categories (held-out PG).
    no_cash, _ = _widen(_package(*BASE[:2]))
    results = obligation_checks(no_cash)
    assert all(r.status == "unavailable" for r in results)
    assert "unrestricted cash at 2026-09-30 is not established" in obligation_verdict(no_cash, results)["message"]
    # Two sourced borrowings totals that disagree: neither is used and the reason says so (held-out AMAT).
    widened, _ = _widen(_package(*BASE, _fact("Total Borrowings", 470)))
    verdict = obligation_verdict(widened, obligation_checks(widened))
    assert verdict["status"] == "unavailable" and "sourced borrowings totals disagree at 2026-09-30 (450, 470)" in verdict["message"]


def test_f3_consolidated_equity_equals_the_parents_only_where_no_outside_interest_is_filed():
    from tests.test_filed_equity import WHERE as EQUITY_WHERE, _package as equity_package
    from tradingagents.dataflows.filed_equity import check_filed_equity, with_filed_equity

    name = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    rows = [r(name, 1000, "open"), r(name, 1130, "close"), r("NetIncomeLoss", 200),
            r("DividendsCommonStockCash", 50), r("StockRepurchasedAndRetiredDuringPeriodValue", 20)]
    structure = _structure({**dict(_structure().balance), f"us-gaap:{name}": "credit"})
    # The package holds equity only under the parent's tag, at the same value, and no outside interest is filed.
    package, notes = with_filed_equity(equity_package(), _instance(rows), structure, **EQUITY_WHERE)
    assert notes == [] and check_filed_equity(package).status == "pass"
    # With a noncontrolling balance filed, the parent's tag is another owner's figure.
    package, notes = with_filed_equity(equity_package(), _instance([*rows, r("MinorityInterest", 60, "close")]),
                                       structure, **EQUITY_WHERE)
    assert "same ownership basis" in notes[0] and check_filed_equity(package) is None


def test_a_financing_line_for_financed_property_and_equipment_is_not_missed():
    """Found by the independent recomputation: NVDA's cash-flow check passed with
    nvda:PaymentsForFinancedPropertyPlantAndEquipmentAndIntangibleAssetsFinancingActivities among its financing lines."""
    from tests.test_face_liabilities import _flows
    from tradingagents.agents.evidence_validation import cash_flow_checks

    for name in ("co:PaymentsForFinancedPropertyPlantAndEquipmentAndIntangibleAssetsFinancingActivities",
                 "co:PrincipalPaymentsOnPropertyPlantAndEquipmentFinancing"):
        package, _ = _flows(["us-gaap:RepaymentsOfLongTermDebt", name],
                            [("us-gaap:RepaymentsOfLongTermDebt", -350), (name, -150)])
        assert financing_principal(package, P_START, END) == {}
        check = cash_flow_checks(package)[1]
        assert check["status"] == "unavailable" and name in check["message"]
