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

from tradingagents.dataflows.filed_instance import InstanceError, financing_lines, liability_lines
from tradingagents.dataflows.financial_evidence import (
    EvidencePackage,
    FinancialFact,
    SourceRecord,
    _derived,
)

FACE = "Balance Sheet Liability ["
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
})
# Debt the filer states together with its finance (capital) leases.
_BORROWING_WITH_FINANCE_LEASES = frozenset({
    "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent",
    "DebtAndCapitalLeaseObligations",
})
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
    return "unclassified" if _DEBT_LIKE.search(name) else "other"


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
    if sum((f.value for f in lines), Decimal(0)) != total.value:
        raise ValueError("the face lines do not add up to total liabilities")
    kinds = {f.fact_id: classify(_concept(f)) for f in lines}
    if "unclassified" in kinds.values():
        raise ValueError("a debt-like face line is not classified")
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
    total = next((f for f in totals if f.value == stated), None)
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
    existing = {f.fact_id for f in package.facts}
    added = [f for f in added if f.fact_id not in existing]
    sources = package.sources if any(s.source_id == source_id for s in package.sources) else (*package.sources, source)
    return EvidencePackage(cik=package.cik, as_of=package.as_of, scope=package.scope, warnings=package.warnings,
                           facts=(*package.facts, *added), sources=sources), notes


def equipment_presented(package: EvidencePackage, end) -> bool:
    """Whether the filed liabilities list carries an equipment-financing line."""
    return any(f.metric.startswith(FACE) and f.period_end == end and _EQUIPMENT.search(_name(_concept(f)))
               for f in package.facts)


def has_face_inventory(package: EvidencePackage, end) -> bool:
    return any(f.origin == "derived" and f.formula_id == BORROWINGS_FORMULA and f.period_end == end
               for f in package.facts)


# ---- financing cash flows for the period: the same reading, for principal paid ----

FINANCING = "Cash Flow Financing Line ["
_LEASE_PRINCIPAL = frozenset({"FinanceLeasePrincipalPayments", "RepaymentsOfLongTermCapitalLeaseObligations"})
_DEBT_WITH_LEASE_PRINCIPAL = frozenset({"RepaymentsOfDebtAndCapitalLeaseObligations",
                                        "RepaymentsOfLongTermDebtAndCapitalSecurities"})
_EQUIPMENT_PRINCIPAL = re.compile(r"EquipmentFinanc|Financing(?:Obligation|Arrangement)|VendorFinanc|SupplierFinanc", re.I)


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
    existing = {f.fact_id for f in package.facts}
    added = [f for f in added if f.fact_id not in existing]
    sources = package.sources if any(s.source_id == source_id for s in package.sources) else (*package.sources, source)
    return EvidencePackage(cik=package.cik, as_of=package.as_of, scope=package.scope, warnings=package.warnings,
                           facts=(*package.facts, *added), sources=sources), []


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
