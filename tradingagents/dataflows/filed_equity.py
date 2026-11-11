"""The statement of stockholders' equity as the filer tagged it, reconciled opening to closing.

Every movement the filer shows in that statement is a tagged fact, and each tag says whether it adds to or
takes from equity. Opening balance plus those movements either equals the closing balance or it does not.
When it does, the movements are complete and correctly signed by arithmetic; nothing is mapped by name.
Filers that show a total column reconcile on it; filers that show only components (common stock, retained
earnings, other comprehensive income, noncontrolling interests) reconcile each component and the
components must add up to total equity at both dates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations

from tradingagents.dataflows.filed_instance import (
    InstanceError,
    InstanceFact,
    Structure,
    most_precise,
)

_AXIS = "us-gaap:StatementEquityComponentsAxis"
_TOTALS = ("us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "us-gaap:StockholdersEquity")
_BALANCES = frozenset((*_TOTALS, "us-gaap:MinorityInterest"))
_EQUITY_TITLE = re.compile(r"equity|shareholders|stockholders|deficit|capital", re.I)
_NOT_EQUITY_TITLE = re.compile(r"balance sheet|financial position|financial condition|parenthetical|income|operations|"
                               r"cash flow|earnings", re.I)
TOTAL = "total"


@dataclass(frozen=True)
class Component:
    member: str                                         # the equity component, or "total"
    opening: InstanceFact
    closing: InstanceFact
    movements: tuple[tuple[InstanceFact, int], ...]     # each filed movement with its sign on equity


@dataclass(frozen=True)
class RollForward:
    start: date
    end: date
    total_concept: str
    opening: Decimal
    closing: Decimal
    components: tuple[Component, ...]


def equity_roles(structure: Structure) -> tuple[str, ...]:
    """Where the filing reconciles equity: its statement of equity, or the note that does so when there is none."""
    def named(titles):
        return tuple(role for role, title in titles.items()
                     if _EQUITY_TITLE.search(title) and not _NOT_EQUITY_TITLE.search(title))
    statements = named(structure.statements)
    if statements:
        return statements
    totals = set(_TOTALS)
    return tuple(role for role in named(structure.titles)
                 if any(role in structure.presentation.get(total, ()) for total in totals))


def _tolerance(facts) -> Decimal:
    known = [fact.decimals for fact in facts if fact.decimals is not None]
    if len(known) != len(facts):
        return Decimal(0)
    return Decimal(10) ** -min(known) * len(facts) / 2


def _closes(opening, closing, movements):
    total = opening.value + sum((fact.value * sign for fact, sign in movements), Decimal(0))
    return abs(total - closing.value) <= _tolerance([opening, closing, *(fact for fact, _ in movements)])


def roll_forward(facts, structure: Structure, end: date) -> RollForward:
    """The equity reconciliation for the shortest filed period ending at ``end`` that closes.

    Raises ``InstanceError`` when no period reconciles; a reconciliation that does not close is never
    returned as a partial result.
    """
    roles = equity_roles(structure)
    if not roles:
        raise InstanceError("no reconciliation of stockholders' equity is declared in the filing")
    shown = {concept for concept, where in structure.presentation.items() if where & set(roles)}
    money = [fact for fact in facts if fact.unit == "USD"]
    starts = sorted({fact.start for fact in money if fact.start is not None and fact.end == end
                     and fact.concept in shown}, reverse=True)
    reasons = []
    for start in starts:
        try:
            return _for_period(money, structure, shown, start, end)
        except InstanceError as exc:
            reasons.append(f"{start} to {end}: {exc}")
    raise InstanceError("; ".join(reasons) or "no equity movements are filed for a period ending at the balance date")


def _for_period(money, structure, shown, start, end) -> RollForward:
    before = start - timedelta(days=1)

    def balance(concept, when, dimensions=()):
        return most_precise(f for f in money if f.concept == concept and f.start is None and f.end == when
                            and f.dimensions == dimensions)

    total_concept = next((c for c in _TOTALS if c in shown and balance(c, end) and balance(c, before)), None)
    if total_concept is None:
        raise InstanceError("opening or closing total equity is not filed")
    opening, closing = balance(total_concept, before), balance(total_concept, end)
    period = [f for f in money if (f.start, f.end) == (start, end) and f.concept in shown and f.concept not in _BALANCES]

    def signed(selected):
        """Each distinct movement among ``selected`` with its sign; None when one is ambiguous."""
        groups = {}
        for fact in selected:
            groups.setdefault((fact.concept, fact.dimensions), []).append(fact)
        rows = []
        for (concept, _dimensions), group in groups.items():
            fact, side = most_precise(group), structure.balance.get(concept)
            if fact is None or side is None:
                return None
            rows.append((fact, 1 if side == "credit" else -1))
        return tuple(rows)

    # A total column, first as filed and then with movements the filer splits along another axis (an
    # offering, an acquisition, a conversion) instead of stating in the total column.
    plain = [f for f in period if not f.dimensions]
    elsewhere = [f for f in period if len(f.dimensions) == 1 and f.dimensions[0][0] != _AXIS]
    for selected in (plain, plain + elsewhere):
        whole = signed(selected)
        if whole and _closes(opening, closing, whole):
            return RollForward(start, end, total_concept, opening.value, closing.value,
                               (Component(TOTAL, opening, closing, whole),))
    # Otherwise each component of equity, which must add up to total equity at both dates.
    paired = {}
    for member in {f.dimensions[0][1] for f in money if len(f.dimensions) == 1 and f.dimensions[0][0] == _AXIS}:
        ends = []
        for when in (before, end):
            found = [most_precise(f for f in money if f.concept == concept and f.start is None and f.end == when
                                  and f.dimensions == ((_AXIS, member),)) for concept in sorted(_BALANCES)]
            found = [fact for fact in found if fact is not None]
            ends.append(found[0] if found and len({fact.value for fact in found}) == 1 else None)
        if None not in ends:
            paired[member] = tuple(ends)
    if not paired or len(paired) > 14:
        raise InstanceError("no total column reconciles and equity components are not filed at both dates")
    for size in range(1, len(paired) + 1):
        for chosen in combinations(sorted(paired), size):
            pairs = [paired[m] for m in chosen]
            if (abs(sum((p[0].value for p in pairs), Decimal(0)) - opening.value) > _tolerance([opening, *(p[0] for p in pairs)])
                    or abs(sum((p[1].value for p in pairs), Decimal(0)) - closing.value)
                    > _tolerance([closing, *(p[1] for p in pairs)])):
                continue
            components = []
            for member in chosen:
                first, last = paired[member]
                movements = signed([f for f in period if f.dimensions == ((_AXIS, member),)])
                if movements is None or not _closes(first, last, movements):
                    raise InstanceError(f"{member} does not reconcile from {before} to {end}")
                components.append(Component(member, first, last, movements))
            if not any(component.movements for component in components):
                raise InstanceError("no movements are filed for the equity components")
            return RollForward(start, end, total_concept, opening.value, closing.value, tuple(components))
    raise InstanceError("equity components do not add up to total equity at both dates")


# ---- the reconciliation as package facts, and the check recomputed from them ----

OPENING, CLOSING, MOVEMENT, ROUNDING = "Equity Opening [", "Equity Closing [", "Equity Movement [", "Equity Reconciliation Rounding"
METHOD = "opening_equity_plus_filed_movements_v1"


def with_filed_equity(package, facts, structure, *, url, content_hash, accession, form, filed_date, retrieved_at):
    """The package with the filed equity reconciliation, or unchanged with the reason it was not established."""
    import hashlib
    import json

    from tradingagents.dataflows.financial_evidence import (
        EvidencePackage,
        FinancialFact,
        SourceRecord,
    )

    balances = [f for f in package.facts if f.metric == "Total Assets" and f.value is not None and f.period_start is None]
    if not balances:
        return package, ["no balance-sheet date"]
    end = max(f.period_end for f in balances)
    try:
        forward = roll_forward(facts, structure, end)
    except InstanceError as exc:
        return package, [f"filed equity reconciliation not established: {exc}"]
    stated = {f.value for f in package.facts if f.period_start is None and f.period_end == end and f.value is not None
              and f.metric in ("Stockholders Equity", "Total Equity Including Noncontrolling Interests")}
    if forward.closing not in stated:
        return package, [f"filed closing equity {forward.closing} is not the balance sheet's equity at {end}"]
    source_id = "sec-instance-" + hashlib.sha256(f"{url}:{content_hash}".encode()).hexdigest()
    source = SourceRecord(source_id=source_id, cik=package.cik, url=url, filed_date=filed_date, retrieved_at=retrieved_at,
                          content_hash=content_hash, locator="filed XBRL instance and filing structure",
                          accession=accession, form=form)

    def filed(metric, value, start, when, locator):
        identity = hashlib.sha256(json.dumps([package.cik, metric, str(value), str(start), str(when), source_id]).encode()).hexdigest()
        return FinancialFact(fact_id=identity, metric=metric, value=value, unit="USD", cik=package.cik, period_start=start,
                             period_end=when, as_of=package.as_of, source_ids=(source_id,), locator=locator)

    before, added, used = forward.start - timedelta(days=1), [], []
    for component in forward.components:
        label = component.member
        added.append(filed(f"{OPENING}{label}]", component.opening.value, None, before, f"{component.opening.concept} at {before}"))
        added.append(filed(f"{CLOSING}{label}]", component.closing.value, None, forward.end, f"{component.closing.concept} at {forward.end}"))
        used += [component.opening, component.closing]
        for fact, sign in component.movements:
            where = "; ".join(member for _, member in fact.dimensions) or "total column"
            added.append(filed(f"{MOVEMENT}{fact.concept} | {label} | {where}]", fact.value * sign, forward.start, forward.end,
                               f"{fact.concept} filed as {fact.value}, {'adds to' if sign > 0 else 'takes from'} equity"))
            used.append(fact)
    decimals = [fact.decimals for fact in used]
    if None in decimals:
        return package, ["filed equity figures do not state their rounding"]
    added.append(filed(ROUNDING, Decimal(10) ** -min(decimals), None, forward.end,
                       "coarsest rounding the filing states for the reconciled equity figures"))
    existing = {f.fact_id for f in package.facts}
    added = [f for f in added if f.fact_id not in existing]
    sources = package.sources if any(s.source_id == source_id for s in package.sources) else (*package.sources, source)
    return EvidencePackage(cik=package.cik, as_of=package.as_of, scope=package.scope, warnings=package.warnings,
                           facts=(*package.facts, *added), sources=sources), []


def check_filed_equity(package):
    """Recompute the filed equity reconciliation from the package's facts; None when the package holds none."""
    from tradingagents.agents.accounting_checks import Calculation

    balances = [f for f in package.facts if f.metric == "Total Assets" and f.value is not None and f.period_start is None]
    end = max((f.period_end for f in balances), default=None)
    closings = [f for f in package.facts if f.metric.startswith(CLOSING) and f.period_end == end and f.value is not None]
    rounding = [f for f in package.facts if f.metric == ROUNDING and f.period_end == end and f.value is not None]
    if end is None or not closings:
        return None
    ids = []

    def unavailable(message):
        return Calculation(method=METHOD, status="unavailable", input_fact_ids=tuple(ids),
                           reason_code="filed_reconciliation_incomplete", message=message)

    if len(rounding) != 1 or rounding[0].value <= 0:
        return unavailable("Filed equity reconciliation lacks its stated rounding")
    quantum, result, expected, worst = rounding[0].value, Decimal(0), Decimal(0), Decimal(0)
    movements = [f for f in package.facts if f.metric.startswith(MOVEMENT) and f.period_end == end and f.value is not None]
    starts = {f.period_start for f in movements}
    if len(starts) != 1 or None in starts:
        return unavailable("Filed equity movements do not share one period")
    before = next(iter(starts)) - timedelta(days=1)
    for closing in closings:
        label = closing.metric[len(CLOSING):-1]
        opening = [f for f in package.facts if f.metric == f"{OPENING}{label}]" and f.period_end == before and f.value is not None]
        parts = [f for f in movements if f.metric.split(" | ")[1:2] == [label]]
        if len(opening) != 1 or len({f.unit for f in (closing, opening[0], *parts)}) != 1:
            return unavailable(f"Filed equity component {label} lacks one opening balance")
        ids += [opening[0].fact_id, closing.fact_id, *(f.fact_id for f in parts)]
        total = opening[0].value + sum((f.value for f in parts), Decimal(0))
        result, expected = result + total, expected + closing.value
        tolerance = quantum * (len(parts) + 2) / 2
        if abs(total - closing.value) > tolerance:
            return Calculation(method=METHOD, status="fail", result=total, expected=closing.value, residual=total - closing.value,
                               tolerance=tolerance, unit=closing.unit, input_fact_ids=tuple(ids), reason_code="material_residual",
                               message=f"Filed equity component {label} does not reconcile")
        worst = max(worst, tolerance)
    if not any(f.metric.startswith(MOVEMENT) for f in package.facts if f.fact_id in ids):
        return unavailable("Filed equity reconciliation has no movements")
    stated = [f for f in package.facts if f.period_start is None and f.period_end == end and f.value is not None
              and f.metric in ("Stockholders Equity", "Total Equity Including Noncontrolling Interests")]
    tolerance = quantum * (len(closings) + 1) / 2
    match = next((f for f in stated if abs(f.value - expected) <= tolerance), None)
    if match is None:
        return Calculation(method=METHOD, status="fail", result=expected, unit=closings[0].unit, input_fact_ids=tuple(ids),
                           reason_code="material_residual",
                           message="Filed equity components do not add up to the balance sheet's equity")
    ids.append(match.fact_id)
    return Calculation(method=METHOD, status="pass", result=result, expected=expected, residual=result - expected,
                       tolerance=max(worst, tolerance), unit=closings[0].unit, input_fact_ids=tuple(dict.fromkeys(ids)),
                       reason_code="reconciled",
                       message=f"Opening equity plus every movement in the filed statement equals closing equity "
                               f"({before} to {end}; {len(closings)} component{'s' if len(closings) != 1 else ''})")
