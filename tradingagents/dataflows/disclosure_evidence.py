"""Bounded, source-grounded disclosure records; never an assertion of coverage.

The analyst proposes records. Code checks their quotations and numeric tokens
against retrieved blocks. Semantic interpretation still requires the accounting
and claim checks; matching text alone does not make arbitrary prose verified.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DisclosureComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    quote: str = Field(min_length=1, max_length=600)
    value: Decimal = Field(ge=0)
    unit: Literal["%"]
    basis_locator: str = Field(min_length=1, max_length=256)


class DisclosureClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    source_id: str = Field(min_length=1, max_length=128)
    locator: str = Field(min_length=1, max_length=256)
    metric: str = Field(min_length=1, max_length=160)
    value: Decimal
    upper_value: Decimal | None = None
    comparator: Literal["exact", "at_least", "central_estimate"] = "exact"
    tolerance_percent: Decimal | None = Field(default=None, gt=0, lt=100)
    unit: str = Field(min_length=1, max_length=80)
    period: str = Field(min_length=1, max_length=160)
    kind: Literal["historical", "guidance", "ambition"]
    quote: str = Field(min_length=1, max_length=2400)
    value_quote: str | None = Field(default=None, min_length=1, max_length=1200)
    definition: str | None = Field(default=None, min_length=1, max_length=2400)

    period_locator: str | None = Field(default=None, min_length=1, max_length=256)
    definition_locator: str | None = Field(default=None, min_length=1, max_length=256)
    comparison: DisclosureComparison | None = None

    @model_validator(mode="after")
    def range_order(self):
        if self.comparator == "central_estimate":
            if self.tolerance_percent is None or self.upper_value is not None or not self.value_quote:
                raise ValueError("central estimate needs its explicit tolerance/value span and no invented upper bound")
        elif self.tolerance_percent is not None:
            raise ValueError("tolerance belongs only to a central estimate")
        if self.comparator == "at_least" and self.upper_value is not None:
            raise ValueError("a lower-bound disclosure cannot have an invented upper bound")
        if self.value_quote and not self.period_locator:
            raise ValueError("a qualified value span requires explicit period context")
        if self.upper_value is not None and self.upper_value < self.value:
            raise ValueError("disclosed range is reversed")
        return self


class DisclosureResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    claims: tuple[DisclosureClaim, ...] = ()
    rejected: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _numbers(text: str) -> set[Decimal]:
    # Match complete tokens, preserving sign and decimal scale. No arithmetic or
    # interpretation of a nearby year as a monetary value is performed here.
    tokens = re.findall(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w.])", text)
    return {Decimal(token.replace(",", "")) for token in tokens}


def _value_has_unit(claim: DisclosureClaim) -> bool:
    # A reporting year elsewhere in the sentence cannot become a monetary value.
    number = r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w.])"
    unit = re.escape(claim.unit)
    if claim.unit[-1].isalnum():
        unit += r"(?!\w)"
    tail = r"\s*(?:\$\s*)?" + unit
    for match in re.finditer(number, claim.quote):
        value = Decimal(match.group().replace(",", ""))
        if value != claim.value:
            continue
        after = claim.quote[match.end() :]
        if claim.upper_value is None:
            if re.match(tail, after, re.I):
                return True
            if re.search(unit + r"\s*\$?\s*$", claim.quote[: match.start()], re.I):
                return True
        else:
            second = re.match(
                r"\s*(?:" + unit + r")?\s*(?:to|through|[-–—])\s*\$?\s*(" + number + r")" + tail, after, re.I
            )
            if second and Decimal(second.group(1).replace(",", "")) == claim.upper_value:
                return True
    return _single_column_table(claim)


def _single_column_table(claim: DisclosureClaim) -> bool:
    # Scale may live in a heading only for this supported, explicitly aligned
    # shape. A multi-period header is not a single dated value column.
    if "\n" in claim.quote and claim.upper_value is None:
        heading, table = claim.quote.split("\n", 1)
        rows = [row.strip() for row in table.split(";")]
        header = rows[0].split("|")
        matching = [
            row.split("|")
            for row in rows[1:]
            if row.split("|")[0].strip().casefold() == claim.metric.casefold()
        ]
        if (
            _phrase(heading, claim.unit)
            and len(header) == 2
            and header[1].strip().casefold() == claim.period.casefold()
            and len(matching) == 1
            and len(matching[0]) == 2
            and re.fullmatch(r"\$?\s*[-+]?\d[\d,]*(?:\.\d+)?", matching[0][1].strip())
            and _numbers(matching[0][1]) == {claim.value}
        ):
            return True
    return False


def _local_amount_subject(claim: DisclosureClaim) -> bool:
    """Accept only an explicit, narrow metric-to-amount link.

    Mere presence in one sentence cannot bind Revenue to a number whose local
    subject is EBITDA. Unsupported prose stays unvalidated; callers can quote a
    narrower exact span rather than asking this parser to infer sentence meaning.
    """
    text = re.sub(re.escape(claim.period), " ", claim.quote, flags=re.I)
    metric = re.search(re.escape(claim.metric), text, re.I)
    amounts = list(re.finditer(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?", text))
    if metric is None:
        return False
    amounts = [amount for amount in amounts if amount.end() <= metric.start() or amount.start() >= metric.end()]
    if not amounts:
        return False
    # First amount is the lower value in supported prose ranges. Date numbers
    # have already been removed, and the caller checks all remaining values.
    amount = amounts[0]
    if amount.start() >= metric.end():
        link = text[metric.end():amount.start()]
    elif amount.end() <= metric.start():
        link = text[amount.end():metric.start()]
    else:
        return False
    link = re.sub(re.escape(claim.unit), " ", link, flags=re.I)
    link = re.sub(r"\bU\.S\.", "US", link, flags=re.I)
    words = re.findall(r"[a-z]+", link.casefold())
    connectors = {
        "is", "are", "was", "were", "be", "been", "being", "at", "of",
        "approximately", "about", "around", "between", "to", "guidance",
        "forecast", "forecasted", "target", "ambition", "expected", "expects",
        "expect", "we", "our", "for", "the", "in", "will", "would",
        "estimated", "estimate", "range", "ranges", "from", "a", "an",
        "least", "exceeding", "exceed", "over", "under", "up", "as",
        "reported", "totaled", "totalled", "amounted", "reach", "reached",
        "usd", "us", "dollars", "dollar",
    }
    return all(word in connectors for word in words)


def _unambiguous_association(claim: DisclosureClaim, period_external: bool = False) -> bool:
    """Reject a bag of matching tokens drawn from different source claims.

    The prose contract is one metric, one declared period and one amount/range
    in a single clause. More complex comparisons must use a narrower exact
    source quote or the supported aligned two-column table shape.
    """
    if "|" in claim.quote or "\n" in claim.quote:
        return _single_column_table(claim)
    prose = re.sub(r"\bU\.S\.", "US", claim.quote, flags=re.I)
    if ";" in prose or re.search(r"[.!?]\s+\S", prose):
        return False
    remaining = claim.quote
    for field in ((claim.metric,) if period_external else (claim.metric, claim.period)):
        left = r"(?<!\w)" if field[0].isalnum() else ""
        right = r"(?!\w)" if field[-1].isalnum() else ""
        pattern = left + re.escape(field) + right
        if len(re.findall(pattern, remaining, re.I)) != 1:
            return False
        remaining = re.sub(pattern, " ", remaining, flags=re.I)
    expected = {claim.value}
    if claim.upper_value is not None:
        expected.add(claim.upper_value)
    # Dates inside the declared period have been removed. Extra numeric
    # amounts or years make association ambiguous; never pick by membership.
    return _numbers(remaining) == expected and _local_amount_subject(claim)


def _phrase(text: str, phrase: str) -> bool:
    left = r"(?<!\w)" if phrase[0].isalnum() else ""
    right = r"(?!\w)" if phrase[-1].isalnum() else ""
    return bool(re.search(left + re.escape(phrase) + right, text, re.I))


def validate_disclosure_claims(
    claims: list[DisclosureClaim], blocks: dict[tuple[str, str], str], *, packages=()
) -> DisclosureResult:
    """Ground up to 32 proposed records in immutable source/locator text.

    Rejections are visible and do not erase the raw research. Undisclosed KPI
    definitions are warnings, rather than a reason to invent one or fail every
    other metric. This function cannot establish document coverage.
    """
    if len(claims) > 32:
        raise ValueError("at most 32 disclosure records may be extracted")
    from tradingagents.dataflows.disclosure_context import collapse_quote_packages, validate_context

    try:
        packages = collapse_quote_packages(packages)
    except ValueError as exc:
        return DisclosureResult(rejected=tuple(
            f"record {index}: {exc} ({claim.source_id}, {claim.locator})"
            for index, claim in enumerate(claims)))
    accepted, rejected, warnings = [], [], []
    for index, claim in enumerate(claims):
        text = blocks.get((claim.source_id, claim.locator))
        period_external, definition_external, context_error = validate_context(claim, blocks, packages)
        reason = None
        numeric = claim.model_copy(update={"quote": claim.value_quote}) if claim.value_quote else claim
        plus_bound = any(Decimal(m.replace(",", "")) == claim.value
                         for m in re.findall(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*%\+", numeric.quote))
        # Quotation containment alone must not allow a numeric qualifier to be
        # cut off at the boundary (e.g. source 60%+ quoted as exact 60%).
        cuts_percent_plus = bool(text is not None and claim.quote.rstrip().endswith('%')
                                 and re.search(re.escape(claim.quote) + r"\s*\+", text))
        if cuts_percent_plus:
            reason = "quotation omits the immediately following percent-plus qualifier"
        elif (claim.comparator == "at_least") != plus_bound:
            reason = "lower-bound comparator must match explicit percent-plus source language"
        elif context_error:
            reason = context_error
        elif text is None:
            reason = "source or locator unavailable"
        elif claim.quote not in text:
            reason = "quotation is not an exact retrieved source span"
        elif not all(
            _phrase(numeric.quote, field) for field in ((claim.metric, claim.unit) if period_external else (claim.metric, claim.unit, claim.period))
        ):
            reason = "metric, unit or period is not present in the quoted span"
        elif claim.value not in _numbers(numeric.quote) or (
            claim.upper_value is not None and claim.upper_value not in _numbers(numeric.quote)
        ):
            reason = "numeric value is not present in the quoted span"
        elif not _value_has_unit(numeric):
            reason = "numeric value is not explicitly associated with the asserted unit"
        elif not _unambiguous_association(numeric, period_external):
            reason = "metric, period and value lack an unambiguous local association"
        elif claim.definition and not definition_external and claim.definition not in text:
            reason = "definition is not an exact retrieved source span"
        else:
            ambition = bool(
                re.search(r"\b(ambition|aspiration|aspire|aspirational)\b", numeric.quote, re.I)
            )
            guidance = bool(
                re.search(
                    r"\b(guidance|outlook|expects?|expected|forecasts?|projected|targets?|plans?|estimates?|anticipates?|aims?|will|would|could)\b",
                    numeric.quote,
                    re.I,
                )
            )
            if period_external and claim.kind == "guidance":
                guidance = True
            if claim.kind == "ambition" and not ambition:
                reason = "ambition classification lacks explicit source language"
            elif claim.kind == "guidance" and (not guidance or ambition):
                reason = "guidance classification lacks unambiguous source language"
            elif claim.kind == "historical" and (ambition or guidance):
                reason = "forward-looking disclosure cannot be classified as historical"
        if reason:
            rejected.append(f"record {index}: {reason} ({claim.source_id}, {claim.locator})")
            continue
        if claim.definition is None:
            warnings.append(f"{claim.metric}: definition not extracted; retain the quoted wording")
        if claim not in accepted:
            accepted.append(claim)
    return DisclosureResult(
        claims=tuple(accepted), rejected=tuple(rejected), warnings=tuple(warnings)
    )


def parse_disclosure_report(report: str, blocks: dict[tuple[str, str], str], *, packages=()) -> DisclosureResult:
    """Parse one bounded model extraction; missing/malformed output stays unvalidated."""
    matches = re.findall(r"```disclosures\s*\n(.*?)\n```", report, re.S)
    if len(matches) != 1 or len(matches[0]) > 48000:
        return DisclosureResult(rejected=("Missing, duplicate or oversized disclosure extraction",))
    try:
        raw = json.loads(matches[0])
        if not isinstance(raw, list) or len(raw) > 32:
            raise ValueError("expected up to 32 records")
    except (ValueError, TypeError):
        return DisclosureResult(rejected=("Malformed disclosure extraction",))
    claims, original_indices, rejected = [], [], []
    for index, item in enumerate(raw):
        try:
            claims.append(DisclosureClaim.model_validate(item))
            original_indices.append(index)
        except (ValueError, TypeError):
            rejected.append((index, f"record {index}: malformed disclosure record"))
    checked = validate_disclosure_claims(claims, blocks, packages=packages)
    for reason in checked.rejected:
        match = re.match(r"record (\d+):", reason)
        index = original_indices[int(match[1])]
        rejected.append((index, f"record {index}:" + reason[match.end():]))
    return DisclosureResult(
        claims=checked.claims,
        rejected=tuple(reason for _, reason in sorted(rejected)),
        warnings=checked.warnings,
    )
