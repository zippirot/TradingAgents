"""Plan L1: borrowings and leases from the filer's own declared liabilities list.

Baseline 2026-11-11: every development company failed obligation_perimeter because each tags debt
differently and a missing category is never assumed nil.
"""
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tradingagents.agents.accounting_checks import calculate_obligations
from tradingagents.agents.evidence_validation import (
    cash_flow_checks,
    obligation_checks,
    obligation_verdict,
    validate_calculation_lineage,
)
from tradingagents.dataflows.face_liabilities import (
    COMBINED_BORROWINGS,
    classify,
    derive_face_borrowings,
    financing_principal,
    with_face_liabilities,
    with_financing_lines,
)
from tradingagents.dataflows.filed_instance import (
    InstanceError,
    liability_lines,
    parse_calculation,
    parse_instance,
)
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord

END, CUT, CIK = date(2026, 9, 30), date(2026, 11, 11), "0000789019"


def instance(lines, extra=""):
    """A small filed instance: undimensioned balances at END, plus anything in ``extra``."""
    facts = "".join(f'<{name} contextRef="now" unitRef="usd" decimals="0">{value}</{name}>' for name, value in lines)
    return f"""<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2026"
      xmlns:co="http://example.com/2026" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:dei="http://xbrl.sec.gov/dei/2026">
      <context id="now"><entity><identifier scheme="x">1</identifier></entity><period><instant>{END}</instant></period></context>
      <context id="old"><entity><identifier scheme="x">1</identifier></entity><period><instant>2025-12-31</instant></period></context>
      <context id="seg_a"><entity><identifier scheme="x">1</identifier><segment>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">co:AMember</xbrldi:explicitMember></segment></entity>
        <period><instant>{END}</instant></period></context>
      <context id="seg_b"><entity><identifier scheme="x">1</identifier><segment>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">co:BMember</xbrldi:explicitMember></segment></entity>
        <period><instant>{END}</instant></period></context>
      <unit id="usd"><measure>iso4217:USD</measure></unit>{facts}{extra}</xbrl>""".encode()


def calculation(tree):
    locs = "".join(f'<link:loc xlink:label="{c}" xlink:href="x.xsd#{c.replace(":", "_")}"/>'
                   for c in {c for parent, children in tree.items() for c in (parent, *children)})
    arcs = "".join(f'<link:calculationArc xlink:from="{parent}" xlink:to="{child}" weight="1" order="{i}"/>'
                   for parent, children in tree.items() for i, child in enumerate(children))
    return f"""<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
      <link:calculationLink xlink:role="http://example.com/role/BalanceSheet">{locs}{arcs}</link:calculationLink>
      </link:linkbase>""".encode()


TREE = {"us-gaap:Liabilities": ["us-gaap:LiabilitiesCurrent", "us-gaap:LongTermDebtNoncurrent", "us-gaap:OtherLiabilitiesNoncurrent"],
        "us-gaap:LiabilitiesCurrent": ["us-gaap:AccountsPayableCurrent", "us-gaap:LongTermDebtCurrent",
                                       "us-gaap:CommercialPaper"]}
FILED = [("us-gaap:Liabilities", 1000), ("us-gaap:LiabilitiesCurrent", 300), ("us-gaap:AccountsPayableCurrent", 250),
         ("us-gaap:LongTermDebtCurrent", 50), ("us-gaap:LongTermDebtNoncurrent", 400), ("us-gaap:OtherLiabilitiesNoncurrent", 300)]


def _fact(metric, value):
    return FinancialFact(fact_id=f"f-{metric}", metric=metric, value=Decimal(value), unit="USD", cik=CIK, period_end=END,
                         as_of=CUT, source_ids=("s",), locator="us-gaap/x")


def _package(*facts):
    source = SourceRecord(source_id="s", cik=CIK, url="https://data.sec.gov/x", filed_date=date(2026, 10, 28),
                          retrieved_at=datetime(2026, 11, 11, tzinfo=UTC), content_hash="0" * 64, locator="x",
                          accession="0000789019-26-000001", form="10-Q")
    return EvidencePackage(cik=CIK, as_of=CUT, facts=facts, sources=(source,))


def _widen(package, lines=FILED, tree=TREE, extra=""):
    return with_face_liabilities(package, parse_instance(instance(lines, extra)), parse_calculation(calculation(tree)),
                                 url="https://www.sec.gov/Archives/edgar/data/789019/1/x_htm.xml", content_hash="1" * 64,
                                 accession="0000789019-26-000001", form="10-Q", filed_date=date(2026, 10, 28),
                                 retrieved_at=datetime(2026, 11, 11, tzinfo=UTC))


BASE = (_fact("Total Assets", 5000), _fact("Total Liabilities", 1000), _fact("Cash and Equivalents", 100))


def test_the_filed_list_gives_every_line_and_a_line_left_out_this_period_is_nil_by_arithmetic():
    lines, total = liability_lines(parse_instance(instance(FILED)), parse_calculation(calculation(TREE)), END)
    assert total == 1000 and sum(line.value for line in lines) == 1000
    # CommercialPaper is declared under current liabilities and not filed this period: the sum holds without it.
    assert [line.concept.split(":")[1] for line in lines] == [
        "AccountsPayableCurrent", "LongTermDebtCurrent", "LongTermDebtNoncurrent", "OtherLiabilitiesNoncurrent"]
    assert lines[0].path == ("us-gaap:Liabilities", "us-gaap:LiabilitiesCurrent")


def test_a_declared_sum_that_does_not_hold_establishes_nothing():
    broken = [(name, 260 if name.endswith("AccountsPayableCurrent") else value) for name, value in FILED]
    with pytest.raises(InstanceError, match="does not hold"):
        liability_lines(parse_instance(instance(broken)), parse_calculation(calculation(TREE)), END)
    with pytest.raises(InstanceError, match="no declared balance-sheet sum"):
        liability_lines(parse_instance(instance(FILED)), parse_calculation(calculation({"us-gaap:Assets": ["us-gaap:Cash"]})), END)
    package, notes = _widen(_package(*BASE), lines=broken)
    assert package.facts == BASE and "not established" in notes[0]


def test_a_line_filed_only_by_segment_is_summed_and_still_has_to_close():
    split = [row for row in FILED if not row[0].endswith("LongTermDebtNoncurrent")]
    members = ('<us-gaap:LongTermDebtNoncurrent contextRef="seg_a" unitRef="usd" decimals="0">150</us-gaap:LongTermDebtNoncurrent>'
               '<us-gaap:LongTermDebtNoncurrent contextRef="seg_b" unitRef="usd" decimals="0">250</us-gaap:LongTermDebtNoncurrent>')
    lines, _ = liability_lines(parse_instance(instance(split, members)), parse_calculation(calculation(TREE)), END)
    assert {line.concept: line.value for line in lines}["us-gaap:LongTermDebtNoncurrent"] == 400
    short = members.replace(">250<", ">200<")
    with pytest.raises(InstanceError, match="does not hold"):
        liability_lines(parse_instance(instance(split, short)), parse_calculation(calculation(TREE)), END)


def test_borrowings_are_the_borrowing_lines_and_the_perimeter_states_what_is_not_presented():
    leases = ('<us-gaap:FinanceLeaseLiability contextRef="now" unitRef="usd" decimals="0">70</us-gaap:FinanceLeaseLiability>'
              '<us-gaap:OperatingLeaseLiability contextRef="now" unitRef="usd" decimals="0">30</us-gaap:OperatingLeaseLiability>'
              '<us-gaap:OperatingLeaseLiability contextRef="old" unitRef="usd" decimals="0">99</us-gaap:OperatingLeaseLiability>')
    package, notes = _widen(_package(*BASE), extra=leases)
    assert notes == [] and validate_calculation_lineage(package) == []
    borrowings = next(f for f in package.facts if f.metric == "Total Borrowings")
    assert borrowings.value == 450 and borrowings.origin == "derived" and len(borrowings.input_fact_ids) == 5
    results = obligation_checks(package)
    assert [r.status for r in results] == ["pass", "pass", "pass"]
    assert [r.result for r in results] == [350, 420, 450]
    assert results[-1].message.endswith("equipment not presented in the filed liabilities list")
    # Without lease balances in the filing the wider perimeters stay unavailable and say which category.
    bare, _ = _widen(_package(*BASE))
    statuses = obligation_checks(bare)
    assert [r.status for r in statuses] == ["pass", "unavailable", "unavailable"]
    assert "finance leases not stated in the 10-Q for 2026-09-30 (0000789019-26-000001)" in statuses[1].message
    assert "finance leases, operating leases not stated" in statuses[2].message and "no figure is assumed" in statuses[2].message
    # A forged borrowings figure fails the replay.
    forged = tuple(f.model_copy(update={"value": Decimal(1)}) if f.metric == "Total Borrowings" else f for f in package.facts)
    assert validate_calculation_lineage(EvidencePackage(cik=CIK, as_of=CUT, facts=forged, sources=package.sources)) != []


def test_debt_stated_with_finance_leases_is_one_figure_and_gives_no_borrowings_only_total():
    tree = {"us-gaap:Liabilities": ["us-gaap:ShortTermBorrowings", "us-gaap:LongTermDebtAndCapitalLeaseObligations",
                                    "us-gaap:OtherLiabilitiesNoncurrent"]}
    filed = [("us-gaap:Liabilities", 1000), ("us-gaap:ShortTermBorrowings", 100),
             ("us-gaap:LongTermDebtAndCapitalLeaseObligations", 600), ("us-gaap:OtherLiabilitiesNoncurrent", 300)]
    lease = '<us-gaap:OperatingLeaseLiability contextRef="now" unitRef="usd" decimals="0">30</us-gaap:OperatingLeaseLiability>'
    package, _ = _widen(_package(*BASE), lines=filed, tree=tree, extra=lease)
    assert next(f for f in package.facts if f.metric == COMBINED_BORROWINGS).value == 700
    results = obligation_checks(package)
    assert [r.status for r in results] == ["unavailable", "pass", "pass"]
    assert "no borrowings-only total" in results[0].message
    assert "finance leases within borrowings as the filer states them" in results[2].message and results[2].result == 630


def test_a_debt_like_line_code_does_not_understand_stops_the_derivation():
    assert [classify(c) for c in ("us-gaap:CommercialPaper", "us-gaap:LongTermDebtAndCapitalLeaseObligations",
                                  "us-gaap:OperatingLeaseLiabilityNoncurrent", "us-gaap:AccountsPayableCurrent",
                                  "co:VendorFinancingObligationCurrent", "us-gaap:LoansPayableToBankNoncurrent")] == [
        "borrowing", "borrowing_with_finance_leases", "lease", "other", "unclassified", "unclassified"]
    tree = {"us-gaap:Liabilities": ["us-gaap:LongTermDebtNoncurrent", "co:VendorFinancingObligationCurrent"]}
    filed = [("us-gaap:Liabilities", 1000), ("us-gaap:LongTermDebtNoncurrent", 400), ("co:VendorFinancingObligationCurrent", 600)]
    package, notes = _widen(_package(*BASE), lines=filed, tree=tree)
    assert "not classified" in notes[0] and not any(f.metric == "Total Borrowings" for f in package.facts)
    assert obligation_checks(package)[0].status == "unavailable"
    with pytest.raises(ValueError, match="do not add up"):
        derive_face_borrowings((_fact("Total Liabilities", 999), *[f for f in package.facts if f.metric.startswith("Balance Sheet Liability [")]))


def test_a_category_cannot_be_both_stated_and_settled():
    package = _package(*BASE, _fact("Total Borrowings", 450), _fact("Equipment Financing Obligations", 5),
                       _fact("Finance Lease Liabilities", 70), _fact("Operating Lease Liabilities", 30))
    groups = {"borrowings": ("f-Total Borrowings",), "finance_leases": ("f-Finance Lease Liabilities",),
              "equipment": ("f-Equipment Financing Obligations",), "operating_leases": ("f-Operating Lease Liabilities",)}
    results = calculate_obligations(package, groups, "f-Cash and Equivalents", settled={"equipment": "not presented"})
    assert [r.status for r in results] == ["pass", "unavailable", "unavailable"]
    assert [r.status for r in calculate_obligations(package, groups, "f-Cash and Equivalents")] == ["pass"] * 3


# ---- L3: principal paid over the period, from the filed financing cash flows ----

P_START = date(2026, 1, 1)


def _flow_instance(lines, extra=""):
    facts = "".join(f'<{name} contextRef="ytd" unitRef="usd" decimals="0">{value}</{name}>' for name, value in lines)
    context = (f'<context id="ytd"><entity><identifier scheme="x">1</identifier></entity><period>'
               f'<startDate>{P_START}</startDate><endDate>{END}</endDate></period></context>')
    return instance([], context + facts + extra)


def _flow(metric, value):
    return FinancialFact(fact_id=f"f-{metric}", metric=metric, value=Decimal(value), unit="USD", cik=CIK,
                         period_start=P_START, period_end=END, as_of=CUT, source_ids=("s",), locator="us-gaap/x")


FLOW_BASE = (*BASE, _flow("Operating Cash Flow", 900), _flow("Capital Expenditure", 300), _flow("Financing Cash Flow", -500))
FIN = "us-gaap:NetCashProvidedByUsedInFinancingActivities"
WHERE = {"url": "https://www.sec.gov/Archives/edgar/data/789019/1/x_htm.xml", "content_hash": "1" * 64,
         "accession": "0000789019-26-000001", "form": "10-Q", "filed_date": date(2026, 10, 28),
         "retrieved_at": datetime(2026, 11, 11, tzinfo=UTC)}


def _flows(children, filed, package=FLOW_BASE, extra=""):
    tree = calculation({FIN: children})
    return with_financing_lines(_package(*package), parse_instance(_flow_instance([(FIN, -500), *filed], extra)),
                                parse_calculation(tree), **WHERE)


def test_a_complete_financing_list_settles_equipment_principal_for_that_period_only():
    children = ["us-gaap:RepaymentsOfLongTermDebt", "us-gaap:PaymentsOfDividends", "us-gaap:FinanceLeasePrincipalPayments"]
    # The linkbase weights outflows as subtractions in real filings; here each figure is filed as signed cash.
    package, notes = _flows(children, [("us-gaap:RepaymentsOfLongTermDebt", -300), ("us-gaap:PaymentsOfDividends", -150),
                                       ("us-gaap:FinanceLeasePrincipalPayments", -50)])
    assert not any("financing" in note for note in notes) and financing_principal(package, P_START, END) == {
        "equipment": "not presented in the filed financing cash flows for the period"}
    assert financing_principal(package, date(2026, 7, 1), END) == {}           # another period is not settled by this one
    _results, check, _warnings = cash_flow_checks(package)
    assert check["status"] == "pass" and check["message"].endswith(
        "equipment principal not presented in the filed financing cash flows for the period")
    lease = next(f for f in package.facts if f.metric == "Finance Lease Principal Payments")
    assert lease.value == 50 and (lease.period_start, lease.period_end) == (P_START, END)


def test_lease_principal_not_stated_in_a_complete_period_list_is_reported_and_no_figure_is_assumed():
    """User decision 2026-11-11 (plan Amendment 3): pass on what the filing presents."""
    children = ["us-gaap:RepaymentsOfLongTermDebt", "us-gaap:PaymentsOfDividends"]
    package, _ = _flows(children, [("us-gaap:RepaymentsOfLongTermDebt", -350), ("us-gaap:PaymentsOfDividends", -150)])
    results, check, _warnings = cash_flow_checks(package)
    assert check["status"] == "pass" and "finance leases principal not stated for the period" in check["message"]
    assert "no figure is assumed" in check["message"]
    assert results[0].status == "pass" and results[1].status == "unavailable"      # no principal figure was invented
    assert not any(f.metric == "Finance Lease Principal Payments" for f in package.facts)
    # Lease principal the filer states inside its debt repayments is settled by that statement.
    combined, _ = _flows(["us-gaap:RepaymentsOfDebtAndCapitalLeaseObligations", "us-gaap:PaymentsOfDividends"],
                         [("us-gaap:RepaymentsOfDebtAndCapitalLeaseObligations", -350), ("us-gaap:PaymentsOfDividends", -150)])
    assert cash_flow_checks(combined)[1]["status"] == "pass"
    assert "finance leases principal within debt repayments as the filer states them" in cash_flow_checks(combined)[1]["message"]
    # Without a financing list that adds up, the old rule stands.
    assert cash_flow_checks(_package(*FLOW_BASE))[1]["status"] == "unavailable"


def test_obligations_pass_on_borrowings_from_a_list_that_adds_up_and_say_what_is_not_stated():
    bare, _ = _widen(_package(*BASE))
    results = obligation_checks(bare)
    assert [r.status for r in results] == ["pass", "unavailable", "unavailable"]       # the wider perimeters stay unavailable
    verdict = obligation_verdict(bare, results)
    assert verdict["status"] == "pass" and verdict["message"].startswith("Obligations as the filing presents them: borrowings established")
    assert "Finance leases, operating leases not stated in the 10-Q for 2026-09-30 (0000789019-26-000001)" in verdict["message"]
    assert "no figure is assumed" in verdict["message"] and "other liability lines, which total 550 USD" in verdict["message"]
    # No list that adds up: nothing passes on borrowings alone.
    tagged = _package(*BASE, _fact("Long-term Borrowings (including current)", 450), _fact("Short-term Borrowings", 0))
    plain = obligation_checks(tagged)
    assert plain[0].status == "pass" and obligation_verdict(tagged, plain)["status"] == "unavailable"
    # A debt-like line code does not understand leaves borrowings unestablished, so the check does not pass.
    tree = {"us-gaap:Liabilities": ["us-gaap:LongTermDebtNoncurrent", "co:VendorFinancingObligationCurrent"]}
    filed = [("us-gaap:Liabilities", 1000), ("us-gaap:LongTermDebtNoncurrent", 400), ("co:VendorFinancingObligationCurrent", 600)]
    odd, _ = _widen(_package(*BASE), lines=filed, tree=tree)
    assert obligation_verdict(odd, obligation_checks(odd))["status"] == "unavailable"
    # Everything stated: the verdict is the widest perimeter, as before.
    leases = ('<us-gaap:FinanceLeaseLiability contextRef="now" unitRef="usd" decimals="0">70</us-gaap:FinanceLeaseLiability>'
              '<us-gaap:OperatingLeaseLiability contextRef="now" unitRef="usd" decimals="0">30</us-gaap:OperatingLeaseLiability>')
    full, _ = _widen(_package(*BASE), extra=leases)
    assert obligation_verdict(full, obligation_checks(full))["message"].startswith("Declared dated obligation perimeter")


INV = "us-gaap:NetCashProvidedByUsedInInvestingActivities"


def test_the_investing_list_gives_capital_spending_and_shows_what_is_not_separately_presented():
    tree = calculation({FIN: ["us-gaap:RepaymentsOfLongTermDebt"],
                        INV: ["us-gaap:PaymentsToAcquireOtherPropertyPlantAndEquipment", "us-gaap:PaymentsToAcquireEquipmentOnLease"]})
    filed = [(FIN, -500), ("us-gaap:RepaymentsOfLongTermDebt", -500), (INV, -400),
             ("us-gaap:PaymentsToAcquireOtherPropertyPlantAndEquipment", -300), ("us-gaap:PaymentsToAcquireEquipmentOnLease", -100)]
    base = (*BASE, _flow("Operating Cash Flow", 900), _flow("Financing Cash Flow", -500), _flow("Investing Cash Flow", -400),
            _flow("Equipment on Lease Payments", 100))
    package, notes = with_financing_lines(_package(*base), parse_instance(_flow_instance(filed)), parse_calculation(tree), **WHERE)
    capex = next(f for f in package.facts if f.metric == "Capital Expenditure")
    assert notes == [] and capex.value == 300 and "PaymentsToAcquireOtherPropertyPlantAndEquipment" in capex.locator
    _results, check, warnings = cash_flow_checks(package)
    assert check["status"] == "pass" and any("equipment leased to others" in w for w in warnings)
    # The same payments with no investing list that adds up keep the original block.
    _results, blocked, _ = cash_flow_checks(_package(*base, _flow("Capital Expenditure", 300)))
    assert blocked["status"] == "unavailable" and "gross acquisition/proceeds bridge" in blocked["message"]


def test_a_list_that_does_not_add_up_or_carries_an_equipment_like_line_settles_nothing():
    children = ["us-gaap:RepaymentsOfLongTermDebt", "us-gaap:PaymentsOfDividends"]
    short, notes = _flows(children, [("us-gaap:RepaymentsOfLongTermDebt", -300), ("us-gaap:PaymentsOfDividends", -150)])
    assert "not established" in notes[0] and financing_principal(short, P_START, END) == {}
    mismatch, notes = _flows(children, [("us-gaap:RepaymentsOfLongTermDebt", -350), ("us-gaap:PaymentsOfDividends", -150)],
                             package=(*FLOW_BASE[:-1], _flow("Financing Cash Flow", -499)))
    assert "do not add up" in notes[0]
    odd = ["us-gaap:RepaymentsOfLongTermDebt", "co:PaymentsToAcquireEquipmentFinancingActivities", "us-gaap:FinanceLeasePrincipalPayments"]
    package, _ = _flows(odd, [("us-gaap:RepaymentsOfLongTermDebt", -300), ("co:PaymentsToAcquireEquipmentFinancingActivities", -150),
                              ("us-gaap:FinanceLeasePrincipalPayments", -50)])
    assert financing_principal(package, P_START, END) == {}
    # The filer's own equipment line in a list that adds up is counted as equipment principal, not left unread.
    paid = next(f for f in package.facts if f.metric == "Equipment Financing Principal Payments")
    assert paid.value == 150 and "co:PaymentsToAcquireEquipmentFinancingActivities" in paid.locator
    assert cash_flow_checks(package)[1]["status"] == "pass"


# ---- share counts and valuation for filers read this way ----

def _shares(extra):
    package, _ = _widen(_package(*BASE), extra=extra)
    return [f for f in package.facts if f.metric == "Common Shares Outstanding"], package


def _share_fact(concept, value, context="now", unit="sh"):
    return f'<{concept} contextRef="{context}" unitRef="{unit}" decimals="0">{value}</{concept}>'


UNIT = '<unit id="sh"><measure>shares</measure></unit>'


def test_shares_come_from_the_balance_date_as_the_filing_states_them():
    (direct,), _ = _shares(UNIT + _share_fact("us-gaap:CommonStockSharesOutstanding", 900))
    assert direct.value == 900 and direct.unit == "shares" and direct.origin == "reported"
    # A count along the class-of-stock axis is covered in tests/test_large_filer_audit_closure.py (audit F4).
    (derived,), package = _shares(UNIT + _share_fact("us-gaap:CommonStockSharesIssued", 1000)
                                  + _share_fact("us-gaap:TreasuryStockCommonShares", 150))
    assert derived.value == 850 and derived.formula_id == "shares_issued_less_treasury_v1"
    assert validate_calculation_lineage(package) == []
    # A cover count dated after the balance date is another date; two classes along one axis are not one count.
    assert _shares(UNIT + _share_fact("dei:EntityCommonStockSharesOutstanding", 870, "old"))[0] == []
    assert _shares(UNIT + _share_fact("us-gaap:CommonStockSharesOutstanding", 500, "seg_a")
                   + _share_fact("us-gaap:CommonStockSharesOutstanding", 400, "seg_b"))[0] == []
    # A tagged count already in the package is left alone.
    held = _package(*BASE, FinancialFact(fact_id="sh", metric="Common Shares Outstanding", value=Decimal(7), unit="shares",
                                         cik=CIK, period_end=END, as_of=CUT, source_ids=("s",), locator="us-gaap/x"))
    kept, _ = _widen(held, extra=UNIT + _share_fact("us-gaap:CommonStockSharesOutstanding", 900))
    assert [f.value for f in kept.facts if f.metric == "Common Shares Outstanding"] == [7]


def test_a_filers_own_line_named_only_for_its_leases_is_a_lease():
    """DOCN's filings before mid-2026 state `docn:FinanceLeaseLiabilities`; every past-date DOCN run stopped at
    REVIEW on it (2026-11-13). Boundary: the whole name must be the lease liability, singular or plural, with an
    optional Current or Noncurrent; any other own debt-like line still stops the derivation."""
    from tradingagents.dataflows.face_liabilities import classify

    for name in ("docn:FinanceLeaseLiabilities", "abc:FinanceLeaseLiabilitiesCurrent", "abc:OperatingLeaseLiabilitiesNoncurrent",
                 "abc:FinanceLeaseLiability"):
        assert classify(name) == "lease", name
    assert classify("abc:FinanceLeaseAndOtherFinancingLiabilities") == "unclassified"
    assert classify("abc:EquipmentFinancingLiabilities") == "unclassified"


def test_a_filers_own_line_combining_finance_leases_and_equipment_financing_is_not_a_borrowing():
    """DOCN's filings before mid-2026 (user decision 2026-11-13) state
    `docn:FinanceLeaseLiabilitiesAndEquipmentFinancingObligationsNoncurrent`. It is leases and equipment
    financing, not borrowings, so borrowings can be derived from the other lines. Boundary: the whole name must
    be exactly that pair, with an optional Current or Noncurrent."""
    from tradingagents.dataflows.face_liabilities import classify

    for name in ("docn:FinanceLeaseLiabilitiesAndEquipmentFinancingObligationsNoncurrent",
                 "docn:FinanceLeaseLiabilitiesAndEquipmentFinancingObligationsCurrent",
                 "abc:FinanceLeaseLiabilityAndEquipmentFinancingObligations"):
        assert classify(name) == "lease", name
    assert classify("abc:DebtAndEquipmentFinancingObligations") == "unclassified"
