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
class Structure:
    """What the filing says about its own tags: declared sums, which side each tag sits on, and where it is shown."""
    calculation: dict[str, dict[str, tuple[tuple[str, Decimal], ...]]]
    balance: dict[str, str]                       # concept -> "credit" or "debit"
    presentation: dict[str, frozenset[str]]       # concept -> statement and note roles that show it
    statements: dict[str, str]                    # role -> its title, for the primary statements only
    titles: dict[str, str]                        # role -> its title, for every statement and note


def parse_structure(raw: bytes) -> Structure:
    """Read SEC's ``MetaLinks.json`` for one filing: the same linkbases, already resolved per tag."""
    import json

    if len(raw) > MAX_BYTES:
        raise InstanceError("filing structure exceeds the size limit")
    try:
        instances = json.loads(raw)["instance"]
        (body,) = instances.values()
        tags, reports = body["tag"], body["report"]
    except (ValueError, KeyError, TypeError) as exc:
        raise InstanceError("filing structure is not readable or covers more than one document") from exc
    calculation, balance, presentation = {}, {}, {}
    for key, tag in tags.items():
        concept = key.replace("_", ":", 1)
        if tag.get("crdr") in ("credit", "debit"):
            balance[concept] = tag["crdr"]
        presentation[concept] = frozenset(tag.get("presentation") or ())
        for role, arc in (tag.get("calculation") or {}).items():
            parent = (arc or {}).get("parentTag")
            if not parent:
                continue
            try:
                weight, order = Decimal(str(arc.get("weight", 1))), Decimal(str(arc.get("order", 0)))
            except InvalidOperation:
                continue
            calculation.setdefault(role, {}).setdefault(parent.replace("_", ":", 1), []).append((order, concept, weight))
    resolved = {role: {parent: tuple((child, weight) for _, child, weight in sorted(children, key=lambda row: (row[0], row[1])))
                       for parent, children in tree.items()} for role, tree in calculation.items()}
    statements = {report["role"]: str(report.get("longName") or "") for report in reports.values()
                  if report.get("groupType") == "statement" and not report.get("subGroupType") and report.get("role")}
    titles = {report["role"]: str(report.get("longName") or "") for report in reports.values() if report.get("role")}
    return Structure(resolved, balance, presentation, statements, titles)


def most_precise(facts):
    """One figure from repeats of the same fact: the least rounded, or None when equally precise repeats differ.

    A filing often repeats a balance in running text rounded to billions; that is the same fact, less exactly.
    """
    facts = list(facts)
    if not facts:
        return None
    finest = max((fact.decimals if fact.decimals is not None else 10**6) for fact in facts)
    best = [fact for fact in facts if (fact.decimals if fact.decimals is not None else 10**6) == finest]
    return best[0] if len({fact.value for fact in best}) == 1 else None


@dataclass(frozen=True)
class Line:
    concept: str
    value: Decimal
    decimals: int | None
    path: tuple[str, ...]             # the declared parents above this line, outermost first


_EQUITY_SIDE = re.compile(
    r"^(StockholdersEquity|MinorityInterest|PartnersCapital|MembersEquity|CommitmentsAndContingencies|"
    r"TemporaryEquity|RedeemableNoncontrollingInterest|.*Redeemable.*|.*TemporaryEquity.*|.*Mezzanine.*)")


def _undimensioned(facts, end, unit="USD", start=None):
    """Each concept's consolidated figure at ``end``, or over ``start`` to ``end`` when a period is given.

    A face line some filers state only split along one axis (a debt line by business, say) is taken as the
    sum of that axis's members. The declared sum above it is then checked, so a split that overlaps or
    omits a member fails rather than passing as a total.
    """
    repeats, split, filed = {}, {}, set()
    for fact in facts:
        if fact.end != end or fact.start != start or fact.unit != unit:
            continue
        filed.add(fact.concept)
        if not fact.dimensions:
            repeats.setdefault(fact.concept, []).append(fact)
        elif len(fact.dimensions) == 1:
            axis, member = fact.dimensions[0]
            split.setdefault(fact.concept, {}).setdefault(axis, {})[member] = fact
    # A concept whose equally precise repeats disagree is left out, so any declared sum that needs it fails.
    values = _Values({concept: best for concept, group in repeats.items() if (best := most_precise(group)) is not None})
    split = {concept: axes for concept, axes in split.items() if concept not in repeats}
    for concept, axes in split.items():
        if len(axes) != 1:
            continue
        members = list(next(iter(axes.values())).values())
        decimals = [fact.decimals for fact in members]
        values[concept] = InstanceFact(concept, sum((fact.value for fact in members), Decimal(0)), unit, start, end, (),
                                       None if None in decimals else min(decimals))
    # Filed for this date or period, but with no consolidated figure code can read (repeats that disagree, or
    # a split along more than one axis). A declared sum that names such a line is not a complete list: the
    # other lines adding up does not show this one is nil.
    values.unreadable = frozenset(filed - values.keys())
    return values


class _Values(dict):
    unreadable: frozenset = frozenset()


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
        elif concept in values.unreadable:
            raise InstanceError(f"{concept} is filed but not readable as a consolidated figure")
        else:
            # A subtotal the filer declares but did not file: the lines beneath it are still the filer's lines.
            for child, weight in children or ():
                walk(child, (*path, concept), sign * weight)

    for root in roots:
        walk(root, (), Decimal(1))
    if not lines:
        raise InstanceError("the declared liabilities sum has no filed lines")
    return tuple(lines), total


def _check(values, parent, children):
    hidden = [child for child, _ in children if child in getattr(values, "unreadable", ())]
    if hidden:
        raise InstanceError(f"declared under {parent} and filed, but not readable as a consolidated figure: "
                            + ", ".join(sorted(hidden)))
    present = [(values[child], weight) for child, weight in children if child in values]
    if not present:
        return
    stated = values[parent]
    residual = sum((fact.value * weight for fact, weight in present), Decimal(0)) - stated.value
    if abs(residual) > _tolerance(stated, [fact for fact, _ in present]):
        raise InstanceError(f"declared sum for {parent} does not hold at the filed figures (residual {residual})")


_FINANCING = ("us-gaap:NetCashProvidedByUsedInFinancingActivities",
              "us-gaap:NetCashProvidedByUsedInFinancingActivitiesContinuingOperations")


_INVESTING = ("us-gaap:NetCashProvidedByUsedInInvestingActivities",
              "us-gaap:NetCashProvidedByUsedInInvestingActivitiesContinuingOperations")


def cash_flow_lines(facts, calculation, start: date, end: date, roots) -> tuple[tuple[Line, ...], Decimal]:
    """Every line the filer declares under one cash-flow section for ``start`` to ``end``, signed as cash.

    The same reading as ``liability_lines``: the filer's declared sum, walked to its leaves and checked
    against the filed figures.
    """
    values = _undimensioned(facts, end, start=start)
    for tree in calculation.values():
        root = next((concept for concept in roots if concept in tree and concept in values), None)
        if root is not None:
            break
    else:
        raise InstanceError("no declared sum for this cash-flow section was found")
    lines = []

    def walk(concept, path, sign):
        children = tree.get(concept)
        if children and concept in values:
            _check(values, concept, children)
            for child, weight in children:
                walk(child, (*path, concept), sign * weight)
        elif concept in values:
            lines.append(Line(concept, values[concept].value * sign, values[concept].decimals, path))
        elif concept in values.unreadable:
            raise InstanceError(f"{concept} is filed but not readable as a consolidated figure")
        else:
            # A subtotal the filer declares but did not file: the lines beneath it are still the filer's lines.
            for child, weight in children or ():
                walk(child, (*path, concept), sign * weight)

    walk(root, (), Decimal(1))
    if not lines:
        raise InstanceError("the declared cash-flow sum has no filed lines")
    return tuple(lines), values[root].value


def current_asset_lines(facts, calculation, end: date) -> tuple[tuple[Line, ...], Decimal]:
    """Every line the filer declares within current assets at ``end``, checked the same way."""
    try:
        return cash_flow_lines(facts, calculation, None, end, ("us-gaap:AssetsCurrent",))
    except InstanceError as exc:
        raise InstanceError(str(exc).replace("cash-flow section", "current assets").replace("cash-flow", "current assets")) from exc


def financing_lines(facts, calculation, start: date, end: date) -> tuple[tuple[Line, ...], Decimal]:
    """Every financing cash-flow line the filer declares for the period, and their total."""
    return cash_flow_lines(facts, calculation, start, end, _FINANCING)


def investing_lines(facts, calculation, start: date, end: date) -> tuple[tuple[Line, ...], Decimal]:
    """Every investing cash-flow line the filer declares for the period, and their total."""
    return cash_flow_lines(facts, calculation, start, end, _INVESTING)
