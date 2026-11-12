"""MSFT run 5bc202c4: about $44bn of short-term investments was "not reported" beside $20bn of cash.

The filer's own balance sheet says which investments are current: they are lines of its declared
current-assets sum, and that sum has to hold at the filed figures.
"""
from decimal import Decimal

from tests.test_face_liabilities import BASE, END, WHERE, _package, calculation, instance
from tradingagents.agents.accounting_checks import check_cash_plus_marketable_securities
from tradingagents.dataflows.face_liabilities import with_current_securities
from tradingagents.dataflows.filed_instance import parse_calculation, parse_instance

TREE = {"us-gaap:AssetsCurrent": ["us-gaap:CashCashEquivalentsAndShortTermInvestments", "us-gaap:AccountsReceivableNetCurrent"],
        "us-gaap:CashCashEquivalentsAndShortTermInvestments": ["us-gaap:CashAndCashEquivalentsAtCarryingValue",
                                                               "us-gaap:ShortTermInvestments"]}
FILED = [("us-gaap:AssetsCurrent", 700), ("us-gaap:CashCashEquivalentsAndShortTermInvestments", 320),
         ("us-gaap:CashAndCashEquivalentsAtCarryingValue", 100), ("us-gaap:ShortTermInvestments", 220),
         ("us-gaap:AccountsReceivableNetCurrent", 380)]


def _widen(lines=FILED, tree=TREE):
    return with_current_securities(_package(*BASE), parse_instance(instance(lines)), parse_calculation(calculation(tree)), **WHERE)


def test_short_term_investments_in_the_filed_current_assets_sum_are_counted_beside_cash():
    package, notes = _widen()
    assert notes == []
    liquidity = check_cash_plus_marketable_securities(package)
    assert liquidity.status == "pass" and liquidity.result == Decimal(320)
    fact = next(f for f in package.facts if f.metric == "Current Marketable Securities")
    assert "us-gaap:ShortTermInvestments" in fact.locator and fact.period_end == END


def test_nothing_is_counted_when_the_sum_does_not_hold_or_cash_is_not_the_filed_cash_line():
    broken = [(c, 250 if c == "us-gaap:ShortTermInvestments" else v) for c, v in FILED]
    package, notes = _widen(broken)
    assert "current assets" in notes[0] and check_cash_plus_marketable_securities(package).status == "unavailable"
    other_cash = [(c, 90 if c.endswith("AtCarryingValue") else 230 if c == "us-gaap:ShortTermInvestments" else v) for c, v in FILED]
    package, notes = _widen(other_cash)
    assert "cash" in notes[0] and check_cash_plus_marketable_securities(package).status == "unavailable"


def test_a_filer_that_presents_no_current_investments_gets_no_figure_and_no_note():
    tree = {"us-gaap:AssetsCurrent": ["us-gaap:CashAndCashEquivalentsAtCarryingValue", "us-gaap:AccountsReceivableNetCurrent"]}
    lines = [("us-gaap:AssetsCurrent", 480), ("us-gaap:CashAndCashEquivalentsAtCarryingValue", 100),
             ("us-gaap:AccountsReceivableNetCurrent", 380)]
    package, notes = _widen(lines, tree)
    assert notes == [] and not any(f.metric == "Current Marketable Securities" for f in package.facts)


def test_validation_keeps_a_figure_established_from_the_filed_structure():
    from tradingagents.dataflows.vendors.sec_edgar import confirm_current_marketable_securities

    package, _ = _widen()
    candidate = next(f for f in package.facts if f.metric == "Cash and Equivalents").model_copy(update={
        "fact_id": "candidate", "metric": "Unclassified Marketable Securities [ShortTermInvestments]", "value": Decimal(220)})
    package = package.model_copy(update={"facts": (*package.facts, candidate)})
    kept = confirm_current_marketable_securities(package, None)
    assert check_cash_plus_marketable_securities(kept).result == Decimal(320)
