"""A filing's own structured data: every tagged fact, and the arithmetic the filer declared for its statements.

``companyfacts`` drops every fact that carries a dimension and says nothing about which facts sit on the
face of a statement. The filed XBRL instance holds all facts, and the calculation linkbase holds the filer's
own summation tree (liabilities = the lines beneath it). Together they give an inventory of a statement
total that is complete by the filer's declaration and checked by arithmetic, which a missing tag never is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

_XBRLI = "http://www.xbrl.org/2003/instance"
_LINK = "http://www.xbrl.org/2003/linkbase"
_XLINK = "http://www.w3.org/1999/xlink"
_XBRLDI = "http://xbrl.org/2006/xbrldi"
MAX_BYTES = 40_000_000


class InstanceError(ValueError):
    """The filed data could not be read as described; nothing is inferred from it."""


@dataclass(frozen=True)
class InstanceFact:
    concept: str                      # "us-gaap:Liabilities", or the filer's own prefix
    value: Decimal
    unit: str
    start: date | None
    end: date
    dimensions: tuple[tuple[str, str], ...]
    decimals: int | None

    @property
    def name(self) -> str:
        return self.concept.split(":", 1)[-1]


def _local(tag: str) -> tuple[str, str]:
    namespace, _, name = tag[1:].partition("}") if tag.startswith("{") else ("", "", tag)
    return namespace, name


def parse_instance(raw: bytes) -> tuple[InstanceFact, ...]:
    """Every numeric fact in a filed XBRL instance document, dimensions included."""
    if len(raw) > MAX_BYTES:
        raise InstanceError("instance document exceeds the size limit")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise InstanceError(f"instance document is not well-formed: {exc}") from exc
    prefixes = {}
    for match in re.finditer(rb'xmlns:([A-Za-z0-9_.-]+)="([^"]+)"', raw[:200_000]):
        prefixes.setdefault(match.group(2).decode(), match.group(1).decode())
    contexts, units = {}, {}
    for context in root.iter(f"{{{_XBRLI}}}context"):
        period = context.find(f"{{{_XBRLI}}}period")
        if period is None:
            continue
        instant, start, end = (period.findtext(f"{{{_XBRLI}}}{key}") for key in ("instant", "startDate", "endDate"))
        try:
            dates = (None, date.fromisoformat(instant.strip())) if instant else (
                date.fromisoformat(start.strip()), date.fromisoformat(end.strip()))
        except (AttributeError, ValueError):
            continue
        members = tuple(sorted((member.get("dimension", ""), (member.text or "").strip())
                               for member in context.iter(f"{{{_XBRLDI}}}explicitMember")))
        typed = any(True for _ in context.iter(f"{{{_XBRLDI}}}typedMember"))
        contexts[context.get("id")] = (*dates, members + ((("typed", "typed"),) if typed else ()))
    for unit in root.iter(f"{{{_XBRLI}}}unit"):
        measures = [(m.text or "").strip().split(":")[-1] for m in unit.iter(f"{{{_XBRLI}}}measure")]
        divide = unit.find(f"{{{_XBRLI}}}divide")
        units[unit.get("id")] = "/".join(measures) if divide is not None else (measures[0] if measures else "")
    facts = []
    for element in root:
        namespace, name = _local(element.tag)
        reference = element.get("contextRef")
        if namespace in (_XBRLI, _LINK) or reference not in contexts or element.get("unitRef") is None:
            continue
        try:
            value = Decimal((element.text or "").strip())
        except InvalidOperation:
            continue
        if not value.is_finite():
            continue
        decimals = element.get("decimals")
        start, end, dimensions = contexts[reference]
        facts.append(InstanceFact(
            concept=f"{prefixes.get(namespace, namespace)}:{name}", value=value, unit=units.get(element.get("unitRef"), ""),
            start=start, end=end, dimensions=dimensions,
            decimals=int(decimals) if decimals and decimals.lstrip("-").isdigit() else None))
    return tuple(facts)


def parse_calculation(raw: bytes) -> dict[str, dict[str, tuple[tuple[str, Decimal], ...]]]:
    """The filer's declared sums: for each statement role, each parent's children and their weights."""
    if len(raw) > MAX_BYTES:
        raise InstanceError("calculation linkbase exceeds the size limit")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise InstanceError(f"calculation linkbase is not well-formed: {exc}") from exc
    roles = {}
    for link in root.iter(f"{{{_LINK}}}calculationLink"):
        labels = {}
        for locator in link.iter(f"{{{_LINK}}}loc"):
            fragment = (locator.get(f"{{{_XLINK}}}href") or "").rsplit("#", 1)[-1]
            prefix, _, name = fragment.partition("_")
            labels[locator.get(f"{{{_XLINK}}}label")] = f"{prefix}:{name}"
        tree = {}
        for arc in link.iter(f"{{{_LINK}}}calculationArc"):
            parent, child = labels.get(arc.get(f"{{{_XLINK}}}from")), labels.get(arc.get(f"{{{_XLINK}}}to"))
            try:
                weight, order = Decimal(arc.get("weight", "1")), Decimal(arc.get("order", "0"))
            except InvalidOperation:
                continue
            if parent and child:
                tree.setdefault(parent, []).append((order, child, weight))
        role = link.get(f"{{{_XLINK}}}role") or ""
        merged = roles.setdefault(role, {})
        for parent, children in tree.items():
            merged[parent] = tuple((child, weight) for _, child, weight in sorted(children, key=lambda row: row[0]))
    return roles


@dataclass(frozen=True)
class Line:
    concept: str
    value: Decimal
    decimals: int | None
    path: tuple[str, ...]             # the declared parents above this line, outermost first


_EQUITY_SIDE = re.compile(
    r"^(StockholdersEquity|MinorityInterest|PartnersCapital|MembersEquity|CommitmentsAndContingencies|"
    r"TemporaryEquity|RedeemableNoncontrollingInterest|.*Redeemable.*|.*TemporaryEquity.*|.*Mezzanine.*)")


def _undimensioned(facts, end, unit="USD"):
    """Each concept's consolidated figure at ``end``.

    A face line some filers state only split along one axis (a debt line by business, say) is taken as the
    sum of that axis's members. The declared sum above it is then checked, so a split that overlaps or
    omits a member fails rather than passing as a total.
    """
    values, split = {}, {}
    for fact in facts:
        if fact.end != end or fact.start is not None or fact.unit != unit:
            continue
        if not fact.dimensions:
            known = values.get(fact.concept)
            if known is not None and known.value != fact.value:
                raise InstanceError(f"{fact.concept} is stated twice with different values at {end}")
            values[fact.concept] = fact
        elif len(fact.dimensions) == 1:
            axis, member = fact.dimensions[0]
            split.setdefault(fact.concept, {}).setdefault(axis, {})[member] = fact
    for concept, axes in split.items():
        if concept in values or len(axes) != 1:
            continue
        members = list(next(iter(axes.values())).values())
        decimals = [fact.decimals for fact in members]
        values[concept] = InstanceFact(concept, sum((fact.value for fact in members), Decimal(0)), unit, None, end, (),
                                       None if None in decimals else min(decimals))
    return values


def _tolerance(parent, children):
    """Half a unit of the coarsest rounding among the figures, for each figure in the sum."""
    known = [fact.decimals for fact in (parent, *children) if fact.decimals is not None]
    if len(known) != len(children) + 1:
        return Decimal(0)
    return Decimal(10) ** -min(known) * (len(children) + 1) / 2


def liability_lines(facts, calculation, end: date) -> tuple[tuple[Line, ...], Decimal]:
    """Every liability line the filer declares on its balance sheet at ``end``, and their total.

    The lines come from the filer's own calculation tree, walked to its leaves. Each declared sum is checked
    against the filed figures, so a line the filer left out this period is shown by arithmetic to be nil
    rather than assumed so. Raises when the tree cannot be found or a declared sum does not hold.
    """
    values = _undimensioned(facts, end)
    for tree in calculation.values():
        if "us-gaap:Liabilities" in tree and "us-gaap:Liabilities" in values:
            roots, total = ("us-gaap:Liabilities",), values["us-gaap:Liabilities"].value
            break
        if "us-gaap:LiabilitiesAndStockholdersEquity" in tree and "us-gaap:LiabilitiesAndStockholdersEquity" in values:
            children = tree["us-gaap:LiabilitiesAndStockholdersEquity"]
            if any(weight != 1 for _, weight in children):
                raise InstanceError("the filed total carries a subtracted line; liabilities cannot be separated")
            _check(values, "us-gaap:LiabilitiesAndStockholdersEquity", children)
            roots = tuple(child for child, _ in children if not _EQUITY_SIDE.match(child.split(":", 1)[-1]))
            total = sum((values[child].value for child in roots if child in values), Decimal(0))
            break
    else:
        raise InstanceError("no declared balance-sheet sum for liabilities was found")
    lines = []

    def walk(concept, path, sign):
        children = tree.get(concept)
        if children and concept in values:
            _check(values, concept, children)
            for child, weight in children:
                walk(child, (*path, concept), sign * weight)
            return
        if concept in values:
            fact = values[concept]
            lines.append(Line(concept, fact.value * sign, fact.decimals, path))

    for root in roots:
        walk(root, (), Decimal(1))
    if not lines:
        raise InstanceError("the declared liabilities sum has no filed lines")
    return tuple(lines), total


def _check(values, parent, children):
    present = [(values[child], weight) for child, weight in children if child in values]
    if not present:
        return
    stated = values[parent]
    residual = sum((fact.value * weight for fact, weight in present), Decimal(0)) - stated.value
    if abs(residual) > _tolerance(stated, [fact for fact, _ in present]):
        raise InstanceError(f"declared sum for {parent} does not hold at the filed figures (residual {residual})")
