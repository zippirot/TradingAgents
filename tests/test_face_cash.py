"""Cash for filers whose balance sheet states it under a line the tag reader does not look for.

Chevron files its own line (cvx:CashAndCashEquivalentsExcludingTimeDeposits); Procter & Gamble and GE
present "cash, cash equivalents and restricted cash" as their one balance-sheet cash line. Each is a line
of the filer's declared current-assets sum, and that sum has to hold at the filed figures.
"""
from tests.test_face_liabilities import BASE, END, WHERE, _package, calculation, instance
from tradingagents.dataflows.face_liabilities import with_face_cash
from tradingagents.dataflows.filed_instance import parse_calculation, parse_instance

NO_CASH = tuple(f for f in BASE if f.metric != "Cash and Equivalents")


def _widen(cash_line, lines=None, package=NO_CASH, extra_children=()):
    tree = {"us-gaap:AssetsCurrent": [cash_line, "us-gaap:AccountsReceivableNetCurrent", *extra_children]}
    filed = lines or [("us-gaap:AssetsCurrent", 700), (cash_line, 320), ("us-gaap:AccountsReceivableNetCurrent", 380)]
    return with_face_cash(_package(*package), parse_instance(instance(filed)), parse_calculation(calculation(tree)), **WHERE)


def _cash(package):
    return [f for f in package.facts if f.metric == "Cash and Equivalents" and f.value is not None]


def test_the_filers_own_cash_line_in_its_current_assets_is_read_as_cash():
    package, notes = _widen("co:CashAndCashEquivalentsExcludingTimeDeposits")
    (cash,) = _cash(package)
    assert notes == [] and cash.value == 320 and cash.period_end == END and cash.unit == "USD"
    assert "co:CashAndCashEquivalentsExcludingTimeDeposits" in cash.locator and cash.origin == "reported"


def test_a_cash_line_presented_with_restricted_cash_is_used_and_said_to_include_it():
    package, notes = _widen("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")
    (cash,) = _cash(package)
    assert cash.value == 320 and "includes restricted cash" in cash.locator
    assert len(notes) == 1 and "includes restricted cash" in notes[0]


def test_nothing_is_read_when_cash_is_already_known_the_sum_fails_or_two_lines_could_be_cash():
    assert _widen("co:CashAndCashEquivalentsExcludingTimeDeposits", package=BASE)[0].facts == _package(*BASE).facts
    broken = [("us-gaap:AssetsCurrent", 700), ("co:CashAndCashEquivalentsX", 300), ("us-gaap:AccountsReceivableNetCurrent", 380)]
    package, notes = _widen("co:CashAndCashEquivalentsX", lines=broken)
    assert _cash(package) == [] and "not established" in notes[0]
    two = [("us-gaap:AssetsCurrent", 700), ("co:CashAndCashEquivalentsA", 200), ("us-gaap:AccountsReceivableNetCurrent", 380),
           ("co:CashAndCashEquivalentsB", 120)]
    package, notes = _widen("co:CashAndCashEquivalentsA", lines=two, extra_children=("co:CashAndCashEquivalentsB",))
    assert _cash(package) == [] and "more than one" in notes[0]
    assert _cash(_widen("us-gaap:InventoryNet")[0]) == []      # no cash line at all: nothing, and no note


def test_debt_lines_three_large_filers_use_are_classified_and_an_unknown_one_still_stops():
    from tradingagents.dataflows.face_liabilities import classify

    assert classify("us-gaap:NotesAndLoansPayable") == "borrowing"                                      # Coca-Cola
    assert classify("us-gaap:LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities") == "borrowing_with_finance_leases"  # Chevron
    for own in ("tsla:LongTermDebtAndFinanceLeasesCurrent", "tsla:LongTermDebtAndFinanceLeasesNoncurrent",
                "co:DebtAndFinanceLeases"):                                                             # Tesla's own lines
        assert classify(own) == "borrowing_with_finance_leases"
    # A filer's own debt-like line with any other name is still not guessed at.
    assert classify("co:LongTermDebtAndOtherFinancing") == "unclassified"
    assert classify("co:DebtAndFinanceLeasesOfVariableInterestEntities") == "unclassified"
