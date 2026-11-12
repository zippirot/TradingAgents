"""Borrowings and leases from the filer's own declared liabilities, when tagged totals do not give them.

The filed calculation tree lists every liability line on the balance sheet and the filing's figures prove
the list adds up. A borrowing category with no line in a list that adds up is nil by the filer's own
arithmetic, which is the "explicitly exhaustive inventory" a missing tag can never be.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from tradingagents.dataflows.filed_instance import (
    InstanceError,
    current_asset_lines,
    financing_lines,
    investing_lines,
    liability_lines,
)
from tradingagents.dataflows.financial_evidence import (
    EvidencePackage,
    FinancialFact,
    SourceRecord,
    _derived,
    derive_shares_from_cover,
    derive_shares_outstanding,
)

FACE = "Balance Sheet Liability ["
_CLASS_AXIS = "us-gaap:StatementClassOfStockAxis"
BORROWINGS_FORMULA = "face_borrowings_v1"
COMBINED_BORROWINGS = "Total Borrowings Including Finance Leases"

_BORROWING = frozenset({
    "DebtCurrent", "ShortTermBorrowings", "CommercialPaper", "OtherShortTermBorrowings",
    "ShortTermBankLoansAndNotesPayable", "NotesAndLoansPayableCurrent", "NotesPayableCurrent",
    "LinesOfCreditCurrent", "LineOfCredit", "LongTermLineOfCredit",
    "LongTermDebt", "LongTermDebtCurrent", "LongTermDebtNoncurrent", "OtherLongTermDebtCurrent",
    "OtherLongTermDebtNoncurrent", "LongTermNotesPayable", "NotesPayable", "LongTermNotesAndLoans",
    "SeniorNotes", "SeniorLongTermNotes", "UnsecuredDebtCurrent", "UnsecuredLongTermDebt",
    "SecuredDebtCurrent", "SecuredLongTermDebt", "ConvertibleDebtCurrent", "ConvertibleDebtNoncurrent",
    "ConvertibleNotesPayableCurrent", "ConvertibleLongTermNotesPayable",
    "NotesAndLoansPayable", "SecuredDebt", "UnsecuredDebt",
})
# Debt the filer states together with its finance (capital) leases.
_BORROWING_WITH_FINANCE_LEASES = frozenset({
    "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent",
    "DebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
})
# A filer's own line whose whole name says debt together with finance leases (Tesla), and nothing else.
_OWN_DEBT_WITH_FINANCE_LEASES = re.compile(r"^(?:LongTerm)?DebtAndFinanceLeases(?:Current|Noncurrent)?$")
_LEASES = {
    "finance": ("FinanceLeaseLiability", "FinanceLeaseLiabilityCurrent", "FinanceLeaseLiabilityNoncurrent"),
    "operating": ("OperatingLeaseLiability", "OperatingLeaseLiabilityCurrent", "OperatingLeaseLiabilityNoncurrent"),
}
_LEASE_METRICS = {
    "finance": ("Finance Lease Liabilities", "Current Finance Lease Liabilities", "Noncurrent Finance Lease Liabilities"),
    "operating": ("Operating Lease Liabilities", "Current Operating Lease Liabilities",
                  "Noncurrent Operating Lease Liabilities"),
}
_LEASE_NAMES = frozenset(name for names in _LEASES.values() for name in names)
# A face line that reads like debt or a lease but that code has not classified stops the derivation.
_DEBT_LIKE = re.compile(r"Debt|Borrow|Notes?Payable|NotesAndLoans|CommercialPaper|Lines?OfCredit|Loans?Payable|"
                        r"BankLoans|FinanceLease|CapitalLease|OperatingLease|Financing(?:Obligation|Arrangement)|"
                        r"EquipmentFinanc", re.I)
_EQUIPMENT = re.compile(r"EquipmentFinanc|Financing(?:Obligation|Arrangement)", re.I)


def face_metric(concept: str) -> str:
    return f"{FACE}{concept}]"


def _concept(fact: FinancialFact) -> str:
    return fact.metric[len(FACE):-1]


def _name(concept: str) -> str:
    return concept.split(":", 1)[-1]


def classify(concept: str) -> str:
    """borrowing, borrowing_with_finance_leases, lease, other, or unclassified (debt-like, not understood)."""
    prefix, name = concept.split(":", 1) if ":" in concept else ("", concept)
    if prefix == "us-gaap":
        if name in _BORROWING:
            return "borrowing"
        if name in _BORROWING_WITH_FINANCE_LEASES:
            return "borrowing_with_finance_leases"
        if name in _LEASE_NAMES:
            return "lease"
    elif _OWN_DEBT_WITH_FINANCE_LEASES.match(name):
        return "borrowing_with_finance_leases"
    return "unclassified" if _DEBT_LIKE.search(name) else "other"


def _rounding_unit(values) -> Decimal:
    """The unit the figures are stated in: the largest power of ten that divides every nonzero one."""
    unit = Decimal(1)
    amounts = [abs(Decimal(v)) for v in values if v]
    while amounts and unit < 10**9 and all(v % (unit * 10) == 0 for v in amounts):
        unit *= 10
    return unit


def closes_on(total: FinancialFact, lines_sum: Decimal, values) -> bool:
    """Whether a list summing to ``lines_sum`` is this total. A filed total has to match exactly. A total that was
    itself derived from rounded figures (the filed total less equity) may differ by three of the lines' units,
    and never by more than five thousandths of one percent of the total."""
    if total.value == lines_sum:
        return True
    allowed = min(3 * _rounding_unit(values), abs(total.value) * Decimal("0.00005"))
    return total.origin == "derived" and abs(total.value - lines_sum) <= allowed


def derive_face_borrowings(inputs: tuple[FinancialFact, ...]) -> FinancialFact:
    """Borrowings as the borrowing lines of a liabilities list that adds up to total liabilities.

    ``inputs`` is total liabilities followed by every face line. The total proves the list complete; a
    debt-like line code does not understand stops the derivation rather than being left out of it.
    """
    if len(inputs) < 2 or len({f.fact_id for f in inputs}) != len(inputs):
        raise ValueError("face borrowings need total liabilities and its lines")
    total, *lines = inputs
    if total.metric != "Total Liabilities" or any(not f.metric.startswith(FACE) for f in lines):
        raise ValueError("face borrowings inputs have the wrong roles")
    if any(f.value is None or f.period_start is not None for f in inputs) or any(f.origin != "reported" for f in lines):
        raise ValueError("face borrowings need filed balances")
    if len({(f.unit, f.cik, f.basis, f.as_of, f.period_end) for f in inputs}) != 1:
        raise ValueError("incompatible unit, issuer, basis, vintage or date")
    if not closes_on(total, sum((f.value for f in lines), Decimal(0)), [f.value for f in lines]):
        raise ValueError("the face lines do not add up to total liabilities")
    kinds = {f.fact_id: classify(_concept(f)) for f in lines}
    if "unclassified" in kinds.values():
        names = sorted(_concept(f) for f in lines if kinds[f.fact_id] == "unclassified")
        raise ValueError("a debt-like face line is not classified: " + ", ".join(names))
    combined = any(kind == "borrowing_with_finance_leases" for kind in kinds.values())
    value = sum((f.value for f in lines if kinds[f.fact_id].startswith("borrowing")), Decimal(0))
    if value < 0:
        raise ValueError("face borrowings are negative")
    return _derived(inputs, None, total.period_end, value, BORROWINGS_FORMULA,
                    metric=COMBINED_BORROWINGS if combined else "Total Borrowings")


def with_face_liabilities(package: EvidencePackage, facts, calculation, *, url: str, content_hash: str,
                          accession: str, form: str, filed_date, retrieved_at) -> tuple[EvidencePackage, list[str]]:
    """The package with the filed liability lines, borrowings derived from them, and lease balances.

    Returns the package unchanged, with the reason, when the filed data does not establish the lines.
    """
    balances = [f for f in package.facts if f.metric == "Total Assets" and f.value is not None and f.period_start is None]
    if not balances:
        return package, ["no balance-sheet date"]
    end = max(f.period_end for f in balances)
    totals = [f for f in package.facts if f.metric == "Total Liabilities" and f.value is not None
              and f.period_start is None and f.period_end == end]
    if not totals:
        return package, [f"total liabilities unavailable at {end}"]
    try:
        lines, stated = liability_lines(facts, calculation, end)
    except InstanceError as exc:
        return package, [f"filed liabilities sum not established: {exc}"]
    total = next((f for f in totals if f.value == stated), None) or next(
        (f for f in totals if closes_on(f, stated, [line.value for line in lines])), None)
    if total is None:
        return package, [f"filed liabilities sum {stated} differs from total liabilities at {end}"]
    source_id = "sec-instance-" + hashlib.sha256(f"{url}:{content_hash}".encode()).hexdigest()
    source = SourceRecord(source_id=source_id, cik=package.cik, url=url, filed_date=filed_date,
                          retrieved_at=retrieved_at, content_hash=content_hash,
                          locator="filed XBRL instance and filing structure", accession=accession, form=form)

    def filed(metric, value, locator):
        identity = hashlib.sha256(json.dumps([package.cik, metric, str(value), str(end), source_id]).encode()).hexdigest()
        return FinancialFact(fact_id=identity, metric=metric, value=value, unit="USD", cik=package.cik, period_end=end,
                             as_of=package.as_of, source_ids=(source_id,), locator=locator)

    added = [filed(face_metric(line.concept), line.value,
                   f"{line.concept} at {end}; declared under {' > '.join(line.path) or 'the filed total'}")
             for line in lines]
    notes = []
    try:
        added.append(derive_face_borrowings((total, *added)))
    except ValueError as exc:
        notes.append(f"borrowings not derived from the filed lines: {exc}")
    known = {f.metric for f in package.facts if f.value is not None and f.period_start is None and f.period_end == end}
    consolidated = {}
    for fact in facts:
        if fact.end == end and fact.start is None and not fact.dimensions and fact.unit == "USD" \
                and fact.concept.startswith("us-gaap:"):
            consolidated.setdefault(fact.name, set()).add(fact.value)
    for kind, names in _LEASES.items():
        if known & set(_LEASE_METRICS[kind]):
            continue                                              # tagged facts already give this category
        for name, metric in zip(names, _LEASE_METRICS[kind], strict=True):
            values = consolidated.get(name, set())
            if len(values) == 1:
                added.append(filed(metric, next(iter(values)), f"us-gaap:{name} at {end} in the filed instance"))
    if "Common Shares Outstanding" not in known:
        added += _filed_shares(facts, end, filed)
    existing = {f.fact_id for f in package.facts}
    added = [f for f in added if f.fact_id not in existing]
    sources = package.sources if any(s.source_id == source_id for s in package.sources) else (*package.sources, source)
    return EvidencePackage(cik=package.cik, as_of=package.as_of, scope=package.scope, warnings=package.warnings,
                           facts=(*package.facts, *added), sources=sources), notes


_CASH_LINE = "CashAndCashEquivalentsAtCarryingValue"
_CURRENT_SECURITIES = frozenset({
    "ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    "AvailableForSaleSecuritiesCurrent", "DebtSecuritiesAvailableForSaleExcludingAccruedInterestCurrent",
    "DebtSecuritiesCurrent", "EquitySecuritiesFvNiCurrent", "HeldToMaturitySecuritiesCurrent",
})
CURRENT_SECURITIES = "Current Marketable Securities"


_INCLUSIVE_CASH = "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"


def _is_cash_line(name: str) -> bool:
    return name == "Cash" or name.startswith("CashAndCashEquivalents") or name == _INCLUSIVE_CASH


def with_face_cash(package: EvidencePackage, facts, calculation, *, url: str, content_hash: str,
                   accession: str, form: str, filed_date, retrieved_at) -> tuple[EvidencePackage, list[str]]:
    """The package with cash as the filer's own balance sheet states it, when no tagged cash figure was read.

    The figure is the one cash line of the filer's declared current-assets sum, which has to hold at the
    filed figures. A line the filer presents together with restricted cash is used and said to include it.
    """
    balances = [f for f in package.facts if f.metric == "Total Assets" and f.value is not None and f.period_start is None]
    if not balances:
        return package, []
    end = max(f.period_end for f in balances)
    if any(f.metric == "Cash and Equivalents" and f.value is not None and f.period_start is None
           and f.period_end == end for f in package.facts):
        return package, []
    try:
        lines, _ = current_asset_lines(facts, calculation, end)
    except InstanceError as exc:
        return package, [f"cash not read from the filed balance sheet: current assets sum not established: {exc}"]
    found = [line for line in lines if _is_cash_line(line.concept.split(":", 1)[-1])]
    if not found:
        return package, []
    if len(found) != 1 or found[0].value < 0:
        return package, ["cash not read from the filed balance sheet: more than one line of the filed current assets "
                         "could be cash, or the line is negative"]
    line = found[0]
    inclusive = line.concept.split(":", 1)[-1] == _INCLUSIVE_CASH
    source_id = "sec-instance-" + hashlib.sha256(f"{url}:{content_hash}".encode()).hexdigest()
    source = SourceRecord(source_id=source_id, cik=package.cik, url=url, filed_date=filed_date,
                          retrieved_at=retrieved_at, content_hash=content_hash,
                          locator="filed XBRL instance and filing structure", accession=accession, form=form)
    identity = hashlib.sha256(json.dumps([package.cik, "Cash and Equivalents", str(line.value), str(end), source_id]).encode()).hexdigest()
    fact = FinancialFact(fact_id=identity, metric="Cash and Equivalents", value=line.value, unit="USD", cik=package.cik,
                         period_end=end, as_of=package.as_of, source_ids=(source_id,),
                         locator=f"{line.concept} at {end}; the cash line of us-gaap:AssetsCurrent, whose filed sum holds"
                                 + ("; the filer presents this line together with restricted cash, so it includes "
                                    "restricted cash it does not state separately" if inclusive else ""))
    sources = package.sources if any(s.source_id == source_id for s in package.sources) else (*package.sources, source)
    notes = [f"cash at {end} is the balance-sheet line the filer presents with restricted cash; it includes restricted "
             "cash the filer does not state separately"] if inclusive else []
    return EvidencePackage(cik=package.cik, as_of=package.as_of, scope=package.scope, warnings=package.warnings,
                           facts=(*package.facts, fact), sources=sources), notes


def with_current_securities(package: EvidencePackage, facts, calculation, *, url: str, content_hash: str,
                            accession: str, form: str, filed_date, retrieved_at) -> tuple[EvidencePackage, list[str]]:
    """The package with the investments the filer itself presents within current assets, as one figure.

    They count only as lines of the filer's declared current-assets sum, which has to hold at the filed
    figures and has to carry the package's own cash figure as its cash line. A filer that presents no such
    line gets no figure and no note.
    """
    cashes = [f for f in package.facts if f.metric == "Cash and Equivalents" and f.value is not None
              and f.period_start is None and f.unit == "USD"]
    if not cashes:
        return package, []
    end = max(f.period_end for f in cashes)
    cash = {f.value for f in cashes if f.period_end == end}
    if any(f.metric == CURRENT_SECURITIES and f.period_end == end for f in package.facts):
        return package, []
    try:
        lines, _ = current_asset_lines(facts, calculation, end)
    except InstanceError as exc:
        return package, [f"filed current assets sum not established: {exc}"]
    securities = [line for line in lines if line.concept.split(":", 1)[-1] in _CURRENT_SECURITIES]
    if not securities:
        return package, []
    filed_cash = {line.value for line in lines if line.concept.split(":", 1)[-1] == _CASH_LINE}
    if len(cash) != 1 or filed_cash != cash:
        return package, [f"current investments not counted: the cash line of the filed current assets is not the "
                         f"cash figure used at {end}"]
    if any(line.value < 0 for line in securities):
        return package, ["current investments not counted: a filed investment line is negative"]
    source_id = "sec-instance-" + hashlib.sha256(f"{url}:{content_hash}".encode()).hexdigest()
    source = SourceRecord(source_id=source_id, cik=package.cik, url=url, filed_date=filed_date,
                          retrieved_at=retrieved_at, content_hash=content_hash,
                          locator="filed XBRL instance and filing structure", accession=accession, form=form)
    value = sum((line.value for line in securities), Decimal(0))
    identity = hashlib.sha256(json.dumps([package.cik, CURRENT_SECURITIES, str(value), str(end), source_id]).encode()).hexdigest()
    fact = FinancialFact(fact_id=identity, metric=CURRENT_SECURITIES, value=value, unit="USD", cik=package.cik,
                         period_end=end, as_of=package.as_of, source_ids=(source_id,),
                         locator=" + ".join(line.concept for line in securities)
                                 + f" at {end}; declared within us-gaap:AssetsCurrent, whose filed sum holds")
    sources = package.sources if any(s.source_id == source_id for s in package.sources) else (*package.sources, source)
    return EvidencePackage(cik=package.cik, as_of=package.as_of, scope=package.scope, warnings=package.warnings,
                           facts=(*package.facts, fact), sources=sources), []


def _filed_shares(facts, end, filed) -> list[FinancialFact]:
    """Common shares outstanding at the balance date as the filing states them, when no tagged total gave them.

    In order: the balance-sheet count; the cover-page count when it is dated the balance date itself; the
    balance-sheet count stated for the filer's one class on the class-of-stock axis; shares issued less
    treasury shares. Last, for a filer that states its count only on the cover: the cover count dated
    shortly after the balance date, when the filing's own average share count for the period agrees with it.
    """
    def shares(concept, class_axis=False):
        rows = [f for f in facts if f.concept == concept and f.start is None and f.end == end and f.unit == "shares"
                and ((len(f.dimensions) == 1 and f.dimensions[0][0] == _CLASS_AXIS) if class_axis else not f.dimensions)]
        if class_axis and len({f.dimensions for f in rows}) != 1:
            return None              # no class stated, or more than one class: not one company-wide count
        values = {f.value for f in rows}
        return next(iter(values)) if len(values) == 1 else None

    def fact(metric, value, locator):
        made = filed(metric, value, locator)
        return made.model_copy(update={"unit": "shares"})

    # A count split along any axis but the class of stock (a segment, a subsidiary) is never the company's count.
    for concept, class_axis, how in (("us-gaap:CommonStockSharesOutstanding", False, "in the filed instance"),
                                     ("dei:EntityCommonStockSharesOutstanding", False, "on the cover, dated the balance date"),
                                     ("us-gaap:CommonStockSharesOutstanding", True,
                                      "for the filer's one class of stock, in the filed instance")):
        value = shares(concept, class_axis)
        if value is not None and value > 0:
            return [fact("Common Shares Outstanding", value, f"{concept} at {end} {how}")]
    issued, treasury = shares("us-gaap:CommonStockSharesIssued"), shares("us-gaap:TreasuryStockCommonShares")
    if issued is not None and treasury is not None:
        parts = [fact("Common Shares Issued", issued, f"us-gaap:CommonStockSharesIssued at {end} in the filed instance"),
                 fact("Treasury Shares", treasury, f"us-gaap:TreasuryStockCommonShares at {end} in the filed instance")]
        try:
            return [*parts, derive_shares_outstanding(tuple(parts))]
        except ValueError:
            return []
    return _cover_shares(facts, end, fact)


def _cover_shares(facts, end, fact) -> list[FinancialFact]:
    """The cover-page count dated after the balance date, checked against the period's average count."""
    plain = [f for f in facts if f.unit == "shares" and not f.dimensions]
    covers = {(f.end, f.value) for f in plain if f.concept == "dei:EntityCommonStockSharesOutstanding"
              and f.start is None and f.end > end}
    averages = {(f.start, f.value) for f in plain if f.start is not None and f.end == end
                and f.concept == "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic"}
    if len(covers) != 1 or not averages:
        return []
    (dated, count), = covers
    start = max(start for start, _ in averages)          # the shortest period ending on the balance date
    values = [value for begun, value in averages if begun == start]
    if len(values) != 1:
        return []
    cover = fact("Cover Shares Outstanding", count,
                 f"dei:EntityCommonStockSharesOutstanding on the cover, dated {dated}").model_copy(update={"period_end": dated})
    average = fact("Weighted Average Basic Shares", values[0],
                   f"us-gaap:WeightedAverageNumberOfSharesOutstandingBasic for {start} to {end} in the filed instance"
                   ).model_copy(update={"period_start": start})
    try:
        return [cover, average, derive_shares_from_cover((cover, average))]
    except ValueError:
        return []


def equipment_presented(package: EvidencePackage, end) -> bool:
    """Whether the filed liabilities list carries an equipment-financing line."""
    return any(f.metric.startswith(FACE) and f.period_end == end and _EQUIPMENT.search(_name(_concept(f)))
               for f in package.facts)


def has_face_inventory(package: EvidencePackage, end) -> bool:
    return any(f.origin == "derived" and f.formula_id == BORROWINGS_FORMULA and f.period_end == end
               for f in package.facts)


# ---- financing cash flows for the period: the same reading, for principal paid ----

FINANCING = "Cash Flow Financing Line ["
INVESTING = "Cash Flow Investing Line ["
# Purchases of property, plant and equipment as filers tag the one capital-spending line.
_CAPITAL_SPENDING = frozenset({"PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
                               "PaymentsToAcquireOtherPropertyPlantAndEquipment", "PaymentsToAcquireOtherProductiveAssets"})
_LEASE_PRINCIPAL = frozenset({"FinanceLeasePrincipalPayments", "RepaymentsOfLongTermCapitalLeaseObligations"})
_DEBT_WITH_LEASE_PRINCIPAL = frozenset({"RepaymentsOfDebtAndCapitalLeaseObligations",
                                        "RepaymentsOfLongTermDebtAndCapitalSecurities"})
# Any financing cash-flow line that names equipment, property and plant, or a financed purchase. Such a line
# among financing cash flows is payment on something bought on credit, whatever the filer calls it.
_EQUIPMENT_PRINCIPAL = re.compile(r"Equipment|PropertyPlant|Financed|Financing(?:Obligation|Arrangement)|"
                                  r"VendorFinanc|SupplierFinanc", re.I)


def _statement_period(package):
    """The filed cash-flow period ending at the latest balance date: the longest reported one."""
    balances = [f for f in package.facts if f.metric == "Total Assets" and f.value is not None and f.period_start is None]
    end = max((f.period_end for f in balances), default=None)
    starts = [f.period_start for f in package.facts if f.metric == "Operating Cash Flow" and f.origin == "reported"
              and f.value is not None and f.period_start is not None and f.period_end == end]
    return (min(starts), end) if starts else (None, end)


def with_financing_lines(package: EvidencePackage, facts, calculation, *, url: str, content_hash: str,
                         accession: str, form: str, filed_date, retrieved_at) -> tuple[EvidencePackage, list[str]]:
    """The package with the filed financing lines for the statement period and any finance-lease principal."""
    start, end = _statement_period(package)
    if start is None:
        return package, ["no filed cash-flow period"]
    totals = [f for f in package.facts if f.metric == "Financing Cash Flow" and f.value is not None
              and f.period_start == start and f.period_end == end]
    try:
        lines, stated = financing_lines(facts, calculation, start, end)
    except InstanceError as exc:
        return package, [f"filed financing sum not established: {exc}"]
    if not any(f.value == stated for f in totals) or sum((line.value for line in lines), Decimal(0)) != stated:
        return package, [f"filed financing lines do not add up to financing cash flow for {start} to {end}"]
    source_id = "sec-instance-" + hashlib.sha256(f"{url}:{content_hash}".encode()).hexdigest()
    source = SourceRecord(source_id=source_id, cik=package.cik, url=url, filed_date=filed_date,
                          retrieved_at=retrieved_at, content_hash=content_hash,
                          locator="filed XBRL instance and filing structure", accession=accession, form=form)

    def filed(metric, value, locator):
        identity = hashlib.sha256(json.dumps([package.cik, metric, str(value), str(start), str(end), source_id]).encode()).hexdigest()
        return FinancialFact(fact_id=identity, metric=metric, value=value, unit="USD", cik=package.cik, period_start=start,
                             period_end=end, as_of=package.as_of, source_ids=(source_id,), locator=locator)

    added = [filed(f"{FINANCING}{line.concept}]", line.value, f"{line.concept} for {start} to {end}, signed as cash")
             for line in lines]
    have = any(f.metric == "Finance Lease Principal Payments" and f.value is not None and f.period_start == start
               and f.period_end == end for f in package.facts)
    if not have:
        stated_principal = {fact.value for fact in facts if fact.concept == "us-gaap:FinanceLeasePrincipalPayments"
                            and (fact.start, fact.end) == (start, end) and not fact.dimensions and fact.unit == "USD"}
        if len(stated_principal) == 1:
            added.append(filed("Finance Lease Principal Payments", abs(next(iter(stated_principal))),
                               f"us-gaap:FinanceLeasePrincipalPayments for {start} to {end} in the filed instance"))
    # A filer's own financing line for property, equipment or a financing obligation is what it paid on things
    # bought on credit. The list it sits in adds up to financing cash flow, so the line is read as that payment.
    if not any(f.metric == "Equipment Financing Principal Payments" and f.value is not None and f.period_start == start
               and f.period_end == end for f in package.facts):
        named = [line for line in lines if _EQUIPMENT_PRINCIPAL.search(line.concept.split(":", 1)[-1])]
        if named and all(line.value <= 0 for line in named):
            added.append(filed("Equipment Financing Principal Payments", -sum((line.value for line in named), Decimal(0)),
                               " + ".join(line.concept for line in named)
                               + f" for {start} to {end}: the filed financing cash-flow lines for property, equipment "
                                 "or a financing obligation, stated as payments"))
    # The investing section, read the same way: it shows where capital spending is stated and what is not.
    notes = []
    try:
        invested, invested_total = investing_lines(facts, calculation, start, end)
        stated_investing = {f.value for f in package.facts if f.metric == "Investing Cash Flow" and f.value is not None
                            and f.period_start == start and f.period_end == end}
        if invested_total in stated_investing and sum((line.value for line in invested), Decimal(0)) == invested_total:
            added += [filed(f"{INVESTING}{line.concept}]", line.value,
                            f"{line.concept} for {start} to {end}, signed as cash") for line in invested]
            spending = [line for line in invested if line.concept.split(":", 1)[-1] in _CAPITAL_SPENDING]
            have_capex = any(f.metric == "Capital Expenditure" and f.value is not None and f.period_start == start
                             and f.period_end == end for f in package.facts)
            if not have_capex and len(spending) == 1 and spending[0].value <= 0:
                added.append(filed("Capital Expenditure", -spending[0].value,
                                   f"{spending[0].concept} for {start} to {end} in the filed investing cash flows"))
        else:
            notes.append(f"filed investing lines do not add up to investing cash flow for {start} to {end}")
    except InstanceError as exc:
        notes.append(f"filed investing sum not established: {exc}")
    existing = {f.fact_id for f in package.facts}
    added = [f for f in added if f.fact_id not in existing]
    sources = package.sources if any(s.source_id == source_id for s in package.sources) else (*package.sources, source)
    return EvidencePackage(cik=package.cik, as_of=package.as_of, scope=package.scope, warnings=package.warnings,
                           facts=(*package.facts, *added), sources=sources), notes


def investing_names(package: EvidencePackage, start, end) -> list[str] | None:
    """Names of the filed investing lines for exactly this period when they add up to investing cash flow, else None."""
    lines = [f for f in package.facts if f.metric.startswith(INVESTING) and f.value is not None
             and f.period_start == start and f.period_end == end]
    totals = {f.value for f in package.facts if f.metric == "Investing Cash Flow" and f.value is not None
              and f.period_start == start and f.period_end == end}
    if not lines or sum((f.value for f in lines), Decimal(0)) not in totals:
        return None
    return [f.metric[len(INVESTING):-1].split(":", 1)[-1] for f in lines]


def financing_principal(package: EvidencePackage, start, end) -> dict[str, str]:
    """What a complete filed financing list settles about principal paid over the period, with the basis.

    Empty unless the package holds financing lines that add up to financing cash flow for exactly this
    period. A period-end balance never settles what was paid during the period; only this list does.
    """
    lines = [f for f in package.facts if f.metric.startswith(FINANCING) and f.value is not None
             and f.period_start == start and f.period_end == end]
    totals = {f.value for f in package.facts if f.metric == "Financing Cash Flow" and f.value is not None
              and f.period_start == start and f.period_end == end}
    if not lines or sum((f.value for f in lines), Decimal(0)) not in totals:
        return {}
    names = [f.metric[len(FINANCING):-1].split(":", 1)[-1] for f in lines]
    settled = {}
    if not any(_EQUIPMENT_PRINCIPAL.search(name) for name in names):
        settled["equipment"] = "not presented in the filed financing cash flows for the period"
    if any(name in _DEBT_WITH_LEASE_PRINCIPAL for name in names) and not any(name in _LEASE_PRINCIPAL for name in names):
        settled["finance_leases"] = "within debt repayments as the filer states them"
    return settled


def equipment_like_financing(package: EvidencePackage, start, end) -> list[str]:
    """Financing lines for the period that read like equipment financing and that code does not classify."""
    return sorted(f.metric[len(FINANCING):-1] for f in package.facts
                  if f.metric.startswith(FINANCING) and f.period_start == start and f.period_end == end
                  and _EQUIPMENT_PRINCIPAL.search(f.metric[len(FINANCING):-1].split(":", 1)[-1]))


def other_liabilities(package: EvidencePackage, end) -> Decimal | None:
    """The filed liability lines that are neither borrowings nor leases, summed: where an unstated lease would sit."""
    lines = [f for f in package.facts if f.metric.startswith(FACE) and f.period_end == end and f.value is not None]
    if not lines:
        return None
    return sum((f.value for f in lines if classify(_concept(f)) == "other"), Decimal(0))


def financing_list_complete(package: EvidencePackage, start, end) -> bool:
    """Whether the package holds financing lines that add up to financing cash flow for exactly this period."""
    lines = [f for f in package.facts if f.metric.startswith(FINANCING) and f.value is not None
             and f.period_start == start and f.period_end == end]
    totals = {f.value for f in package.facts if f.metric == "Financing Cash Flow" and f.value is not None
              and f.period_start == start and f.period_end == end}
    return bool(lines) and sum((f.value for f in lines), Decimal(0)) in totals
