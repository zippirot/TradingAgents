"""Cash for filers whose balance sheet states it under a line the tag reader does not look for.

Chevron files its own line (cvx:CashAndCashEquivalentsExcludingTimeDeposits); Procter & Gamble and GE
present "cash, cash equivalents and restricted cash" as their one balance-sheet cash line. Each is a line
of the filer's declared current-assets sum, and that sum has to hold at the filed figures.
"""
from decimal import Decimal

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


def test_borrowings_from_a_complete_filed_list_stand_when_separately_tagged_pieces_overlap_it():
    # Applied Materials: the balance sheet's short-term line already holds the current portion of long-term
    # debt, which is also tagged on its own in a note. The filed list adds up, so it is the total.
    from tests.test_face_liabilities import _fact, _widen
    from tradingagents.agents.evidence_validation import obligation_checks

    tree = {"us-gaap:Liabilities": ["us-gaap:ShortTermBorrowings", "us-gaap:LongTermDebtNoncurrent", "us-gaap:OtherLiabilitiesNoncurrent"]}
    filed = [("us-gaap:Liabilities", 1000), ("us-gaap:ShortTermBorrowings", 130), ("us-gaap:LongTermDebtNoncurrent", 520),
             ("us-gaap:OtherLiabilitiesNoncurrent", 350)]
    tagged = (*BASE, _fact("Short-term Borrowings", 130), _fact("Current Long-term Borrowings", 120),
              _fact("Noncurrent Long-term Borrowings", 520))
    package, _ = _widen(_package(*tagged), lines=filed, tree=tree)
    total = next(f for f in package.facts if f.metric == "Total Borrowings")
    assert total.value == 650
    first = obligation_checks(package)[0]          # net debt on borrowings only
    assert first.status == "pass" and total.fact_id in first.input_fact_ids and first.result == 650 - 100


def test_a_filed_list_closes_on_a_derived_total_within_rounding_and_on_a_filed_total_only_exactly():
    # Thermo Fisher: lines in millions sum to 59,337; total liabilities derived from rounded figures is 59,338.
    from tests.test_face_liabilities import TREE, _fact, _widen
    from tradingagents.dataflows.face_liabilities import closes_on

    million = 10**6
    lines = [("us-gaap:Liabilities", 59337), ("us-gaap:LiabilitiesCurrent", 14811), ("us-gaap:AccountsPayableCurrent", 12203),
             ("us-gaap:LongTermDebtCurrent", 2608), ("us-gaap:LongTermDebtNoncurrent", 38500),
             ("us-gaap:OtherLiabilitiesNoncurrent", 6026)]
    lines = [(name, value * million) for name, value in lines]
    source = _fact("Liabilities and Equity", 110000 * million)
    derived = _fact("Total Liabilities", 59338 * million).model_copy(
        update={"origin": "derived", "formula_id": "x", "input_fact_ids": (source.fact_id,)})
    base = tuple(f for f in BASE if f.metric != "Total Liabilities")
    package, notes = _widen(_package(*base, source, derived), lines=lines, tree=TREE)
    assert not any("differs from total liabilities" in note for note in notes)
    assert any(f.metric == "Total Borrowings" and f.value == 41108 * million for f in package.facts)
    values = [value for _, value in lines]
    assert closes_on(derived, Decimal(59337 * million), values)
    assert not closes_on(derived.model_copy(update={"value": Decimal(59341 * million)}), Decimal(59337 * million), values)
    assert not closes_on(_fact("Total Liabilities", 59338 * million), Decimal(59337 * million), values)   # filed: exact or nothing
