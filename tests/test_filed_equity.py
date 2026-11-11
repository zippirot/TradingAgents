"""Plan L2: the equity reconciliation as the filer tagged it. It either closes or establishes nothing.

Baseline 2026-11-11: no development company had a usable equity-movement table.
"""
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tradingagents.dataflows.filed_equity import check_filed_equity, roll_forward, with_filed_equity
from tradingagents.dataflows.filed_instance import (
    InstanceError,
    Structure,
    parse_instance,
    parse_structure,
)
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord

END, START, BEFORE, CUT, CIK = date(2026, 9, 30), date(2026, 7, 1), date(2026, 6, 30), date(2026, 11, 11), "0000789019"
ROLE = "http://example.com/role/StatementOfStockholdersEquity"
AXIS = "us-gaap:StatementEquityComponentsAxis"


def _context(name, period, member=None, axis=AXIS):
    segment = (f'<segment><xbrldi:explicitMember dimension="{axis}">{member}</xbrldi:explicitMember></segment>' if member else "")
    return f'<context id="{name}"><entity><identifier scheme="x">1</identifier>{segment}</entity><period>{period}</period></context>'


def _instance(rows, decimals="0"):
    """rows: (concept, value, when, member or None, axis). ``when`` is 'open', 'close' or 'period'."""
    periods = {"open": f"<instant>{BEFORE}</instant>", "close": f"<instant>{END}</instant>",
               "period": f"<startDate>{START}</startDate><endDate>{END}</endDate>"}
    contexts, facts = {}, []
    for concept, value, when, member, axis in rows:
        key = f"{when}-{member or 'all'}-{axis}".replace(":", "_")
        contexts[key] = _context(key, periods[when], member, axis or AXIS)
        facts.append(f'<{concept} contextRef="{key}" unitRef="usd" decimals="{decimals}">{value}</{concept}>')
    return parse_instance(f"""<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2026"
        xmlns:co="http://example.com/2026" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">{''.join(contexts.values())}
        <unit id="usd"><measure>iso4217:USD</measure></unit>{''.join(facts)}</xbrl>""".encode())


SIDES = {"us-gaap:NetIncomeLoss": "credit", "us-gaap:DividendsCommonStockCash": "debit",
         "us-gaap:StockRepurchasedAndRetiredDuringPeriodValue": "debit",
         "us-gaap:StockIssuedDuringPeriodValueNewIssues": "credit", "us-gaap:StockholdersEquity": "credit",
         "us-gaap:OtherComprehensiveIncomeLossNetOfTax": "credit"}


def _structure(sides=SIDES, statement=True):
    shown = {concept: frozenset({ROLE}) for concept in (*sides, "us-gaap:StockholdersEquityOther")}
    titles = {ROLE: "0004 - Statement - Consolidated Statements of Stockholders' Equity"}
    return Structure({}, dict(sides), shown, titles if statement else {}, titles)


def r(concept, value, when="period", member=None, axis=None):
    return (f"us-gaap:{concept}", value, when, member, axis)


TOTAL_COLUMN = [r("StockholdersEquity", 1000, "open"), r("StockholdersEquity", 1130, "close"), r("NetIncomeLoss", 200),
                r("DividendsCommonStockCash", 50), r("StockRepurchasedAndRetiredDuringPeriodValue", 20)]


def test_a_total_column_closes_with_each_movement_signed_by_its_own_tag():
    forward = roll_forward(_instance(TOTAL_COLUMN), _structure(), END)
    assert (forward.start, forward.opening, forward.closing) == (START, 1000, 1130)
    (component,) = forward.components
    assert component.member == "total" and sorted(sign for _, sign in component.movements) == [-1, -1, 1]


def test_a_reconciliation_that_does_not_close_establishes_nothing():
    missing = [row for row in TOTAL_COLUMN if "Dividends" not in row[0]]
    with pytest.raises(InstanceError):
        roll_forward(_instance(missing), _structure(), END)
    # A movement whose tag does not say which way it runs cannot be signed.
    sides = {key: value for key, value in SIDES.items() if "Dividends" not in key}
    structure = Structure({}, sides, _structure().presentation | {"us-gaap:DividendsCommonStockCash": frozenset({ROLE})},
                          _structure().statements, _structure().titles)
    with pytest.raises(InstanceError):
        roll_forward(_instance(TOTAL_COLUMN), structure, END)
    with pytest.raises(InstanceError, match="no reconciliation"):
        roll_forward(_instance(TOTAL_COLUMN), Structure({}, SIDES, {}, {}, {}), END)


def test_a_movement_the_filer_splits_along_another_axis_belongs_to_the_total_column():
    rows = [r("StockholdersEquity", 1000, "open"), r("StockholdersEquity", 1700, "close"), r("NetIncomeLoss", 200),
            r("StockIssuedDuringPeriodValueNewIssues", 500, "period", "co:PublicOfferingMember", "us-gaap:SubsidiarySaleOfStockAxis")]
    (component,) = roll_forward(_instance(rows), _structure(), END).components
    assert len(component.movements) == 2
    # The same split that merely repeats a movement already in the total column does not close, so it is not used.
    repeat = [*TOTAL_COLUMN, r("NetIncomeLoss", 200, "period", "co:PublicOfferingMember", "us-gaap:SubsidiarySaleOfStockAxis")]
    assert len(roll_forward(_instance(repeat), _structure(), END).components[0].movements) == 3


def test_components_reconcile_one_by_one_and_must_add_up_to_total_equity():
    rows = [r("StockholdersEquity", 1000, "open"), r("StockholdersEquity", 1130, "close"),
            r("StockholdersEquity", 400, "open", "us-gaap:CommonStockMember"), r("StockholdersEquity", 380, "close", "us-gaap:CommonStockMember"),
            r("StockholdersEquity", 600, "open", "us-gaap:RetainedEarningsMember"), r("StockholdersEquity", 750, "close", "us-gaap:RetainedEarningsMember"),
            r("StockRepurchasedAndRetiredDuringPeriodValue", 20, "period", "us-gaap:CommonStockMember"),
            r("NetIncomeLoss", 200, "period", "us-gaap:RetainedEarningsMember"),
            r("DividendsCommonStockCash", 50, "period", "us-gaap:RetainedEarningsMember")]
    forward = roll_forward(_instance(rows), _structure(), END)
    assert sorted(c.member for c in forward.components) == ["us-gaap:CommonStockMember", "us-gaap:RetainedEarningsMember"]
    broken = [row if "Dividends" not in row[0] else r("DividendsCommonStockCash", 40, "period", "us-gaap:RetainedEarningsMember") for row in rows]
    with pytest.raises(InstanceError, match="does not reconcile"):
        roll_forward(_instance(broken), _structure(), END)


def test_a_figure_repeated_at_coarser_rounding_is_the_same_fact_and_equal_precision_conflicts_are_not_used():
    structure = _structure()
    exact = _instance(TOTAL_COLUMN)
    coarse = _instance([r("StockholdersEquity", 1100, "close")], decimals="-2")
    assert roll_forward((*exact, *coarse), structure, END).closing == 1130
    clash = _instance([r("NetIncomeLoss", 210)])
    with pytest.raises(InstanceError):
        roll_forward((*exact, *clash), structure, END)


def _package(equity="1130"):
    def fact(metric, value):
        return FinancialFact(fact_id=f"f-{metric}", metric=metric, value=Decimal(value), unit="USD", cik=CIK, period_end=END,
                             as_of=CUT, source_ids=("s",), locator="us-gaap/x")
    source = SourceRecord(source_id="s", cik=CIK, url="https://data.sec.gov/x", filed_date=date(2026, 10, 28),
                          retrieved_at=datetime(2026, 11, 11, tzinfo=UTC), content_hash="0" * 64, locator="x",
                          accession="0000789019-26-000001", form="10-Q")
    return EvidencePackage(cik=CIK, as_of=CUT, facts=(fact("Total Assets", 5000), fact("Stockholders Equity", equity)), sources=(source,))


WHERE = {"url": "https://www.sec.gov/Archives/edgar/data/789019/1/x_htm.xml", "content_hash": "1" * 64,
         "accession": "0000789019-26-000001", "form": "10-Q", "filed_date": date(2026, 10, 28),
         "retrieved_at": datetime(2026, 11, 11, tzinfo=UTC)}


def test_the_check_is_recomputed_from_the_package_and_catches_a_changed_figure():
    assert check_filed_equity(_package()) is None
    package, notes = with_filed_equity(_package(), _instance(TOTAL_COLUMN), _structure(), **WHERE)
    check = check_filed_equity(package)
    assert notes == [] and check.status == "pass" and check.method == "opening_equity_plus_filed_movements_v1"
    assert (check.result, check.expected) == (1130, 1130) and "f-Stockholders Equity" in check.input_fact_ids
    changed = tuple(f.model_copy(update={"value": f.value + 30}) if f.metric.startswith("Equity Movement [us-gaap:NetIncomeLoss") else f
                    for f in package.facts)
    assert check_filed_equity(EvidencePackage(cik=CIK, as_of=CUT, facts=changed, sources=package.sources)).status == "fail"
    # A reconciliation whose closing balance is not the balance sheet's equity is not attached at all.
    other, why = with_filed_equity(_package(equity="999"), _instance(TOTAL_COLUMN), _structure(), **WHERE)
    assert other.facts == _package(equity="999").facts and "not the balance sheet" in why[0]
    unclosed, why = with_filed_equity(_package(), _instance(TOTAL_COLUMN[:-1]), _structure(), **WHERE)
    assert check_filed_equity(unclosed) is None and "not established" in why[0]


def test_the_structure_file_gives_sums_sides_and_statement_titles():
    raw = json.dumps({"instance": {"x.htm": {
        "report": {"R4": {"role": ROLE, "longName": "0004 - Statement - Statements of Stockholders' Equity", "groupType": "statement"},
                   "R5": {"role": ROLE + "P", "longName": "0005 - Statement - Balance Sheets (Parenthetical)",
                          "groupType": "statement", "subGroupType": "parenthetical"}},
        "tag": {"us-gaap_Liabilities": {"crdr": "credit", "presentation": ["r"], "calculation": {
                    "r": {"parentTag": "us-gaap_LiabilitiesAndStockholdersEquity", "weight": 1.0, "order": 1.0}}},
                "us-gaap_TreasuryStockValue": {"crdr": "debit", "presentation": [ROLE], "calculation": {
                    "r": {"parentTag": "us-gaap_StockholdersEquity", "weight": -1.0, "order": 2.0}}}}}}}).encode()
    structure = parse_structure(raw)
    assert structure.calculation["r"]["us-gaap:LiabilitiesAndStockholdersEquity"] == (("us-gaap:Liabilities", Decimal("1.0")),)
    assert structure.calculation["r"]["us-gaap:StockholdersEquity"] == (("us-gaap:TreasuryStockValue", Decimal("-1.0")),)
    assert structure.balance["us-gaap:TreasuryStockValue"] == "debit" and list(structure.statements) == [ROLE]
    with pytest.raises(InstanceError):
        parse_structure(b"{}")
