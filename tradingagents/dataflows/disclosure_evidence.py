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


class DisclosureClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    source_id: str = Field(min_length=1, max_length=128)
    locator: str = Field(min_length=1, max_length=256)
    metric: str = Field(min_length=1, max_length=160)
    value: Decimal
    upper_value: Decimal | None = None
    unit: str = Field(min_length=1, max_length=80)
    period: str = Field(min_length=1, max_length=160)
    kind: Literal["historical", "guidance", "ambition"]
    quote: str = Field(min_length=1, max_length=2400)
    definition: str | None = Field(default=None, min_length=1, max_length=2400)

    @model_validator(mode="after")
    def range_order(self):
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
                r"\s*(?:to|through|[-–—])\s*\$?\s*(" + number + r")" + tail, after, re.I
            )
            if second and Decimal(second.group(1).replace(",", "")) == claim.upper_value:
                return True
    # A simple two-column table may put scale in its heading. Accept only
    # an unambiguous metric row and a single dated value column; broader
    # tables need explicit column extraction rather than guessed alignment.
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
            and _phrase(header[1], claim.period)
            and len(matching) == 1
            and len(matching[0]) == 2
            and _numbers(matching[0][1]) == {claim.value}
        ):
            return True
    return False


def _phrase(text: str, phrase: str) -> bool:
    left = r"(?<!\w)" if phrase[0].isalnum() else ""
    right = r"(?!\w)" if phrase[-1].isalnum() else ""
    return bool(re.search(left + re.escape(phrase) + right, text, re.I))


def validate_disclosure_claims(
    claims: list[DisclosureClaim], blocks: dict[tuple[str, str], str]
) -> DisclosureResult:
    """Ground up to 32 proposed records in immutable source/locator text.

    Rejections are visible and do not erase the raw research. Undisclosed KPI
    definitions are warnings, rather than a reason to invent one or fail every
    other metric. This function cannot establish document coverage.
    """
    if len(claims) > 32:
        raise ValueError("at most 32 disclosure records may be extracted")
    accepted, rejected, warnings = [], [], []
    for index, claim in enumerate(claims):
        text = blocks.get((claim.source_id, claim.locator))
        reason = None
        if text is None:
            reason = "source or locator unavailable"
        elif claim.quote not in text:
            reason = "quotation is not an exact retrieved source span"
        elif not all(
            _phrase(claim.quote, field) for field in (claim.metric, claim.unit, claim.period)
        ):
            reason = "metric, unit or period is not present in the quoted span"
        elif claim.value not in _numbers(claim.quote) or (
            claim.upper_value is not None and claim.upper_value not in _numbers(claim.quote)
        ):
            reason = "numeric value is not present in the quoted span"
        elif not _value_has_unit(claim):
            reason = "numeric value is not explicitly associated with the asserted unit"
        elif claim.definition and claim.definition not in text:
            reason = "definition is not an exact retrieved source span"
        else:
            ambition = bool(
                re.search(r"\b(ambition|aspiration|aspire|aspirational)\b", claim.quote, re.I)
            )
            guidance = bool(
                re.search(
                    r"\b(guidance|outlook|expects?|expected|forecasts?|projected|targets?|plans?|estimates?|anticipates?|aims?|will|would|could)\b",
                    claim.quote,
                    re.I,
                )
            )
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


def parse_disclosure_report(report: str, blocks: dict[tuple[str, str], str]) -> DisclosureResult:
    """Parse one bounded model extraction; missing/malformed output stays unvalidated."""
    matches = re.findall(r"```disclosures\s*\n(.*?)\n```", report, re.S)
    if len(matches) != 1 or len(matches[0]) > 48000:
        return DisclosureResult(rejected=("Missing, duplicate or oversized disclosure extraction",))
    try:
        raw = json.loads(matches[0])
        if not isinstance(raw, list) or len(raw) > 32:
            raise ValueError("expected up to 32 records")
        claims = [DisclosureClaim.model_validate(item) for item in raw]
    except (ValueError, TypeError):
        return DisclosureResult(rejected=("Malformed disclosure extraction",))
    return validate_disclosure_claims(claims, blocks)
