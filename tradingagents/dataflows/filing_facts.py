"""Verify bounded filing-table selections against source text.

Selections identify cells; they cannot supply values, scales, signs, dates or
precision. Unsupported layouts remain explicit gaps. This is not a general
financial table reader and does not make prose a source of verified arithmetic.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, SourceRecord
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage

Metric = Literal[
    "Stockholders Equity",
    "Equity Common Stock Issuance Value",
    "Equity Stock Repurchases/Retirements",
    "Equity Award Tax Withholding",
    "Equity Dividends",
    "Equity Conversion of Debt",
    "Employee Stock Purchase Plan Issuance Value",
    "Net Income",
    "Equity Share-based Compensation",
    "Other Comprehensive Income Attributable to Parent",
    "Equipment Financing Obligations",
    "Finance Lease and Equipment Obligations",
    "Total Borrowings",
    "Equipment Financing Principal Payments",
    "Operating Income",
    "Operating Cash Flow",
    "Adjusted Net Income",
    "Adjusted EBITDA",
    "Adjusted Operating Income",
    "Adjusted Free Cash Flow",
    "Management Share-based Compensation Adjustment",
    "Management Depreciation and Amortization Adjustment",
    "Management Interest Adjustment",
    "Management Tax Adjustment",
    "Management Restructuring Adjustment",
    "Management Acquisition Cost Adjustment",
    "Management Capital Expenditure Adjustment",
    "Management Software Development Adjustment",
    "Management Financing Principal Adjustment",
]


class FilingCellSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    locator: str
    metric: Metric
    row_index: int = Field(ge=0, le=2000)
    column_index: int = Field(ge=1, le=30)


class EquityTableCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    locator: str
    column_index: int
    period_start: date | None = None
    period_end: date | None = None
    opening_fact_id: str | None = None
    closing_fact_id: str | None = None
    signed_components: tuple[tuple[str, Literal[1]], ...] = ()
    unmapped_rows: tuple[int, ...] = ()
    omitted_rows: tuple[int, ...] = ()
    gaps: tuple[str, ...] = ()
    complete: bool = False


class AdjustedTableCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    locator: str
    column_index: int
    period_start: date | None = None
    period_end: date | None = None
    gaap_fact_id: str | None = None
    adjusted_fact_id: str | None = None
    signed_components: tuple[tuple[str, Literal[1]], ...] = ()
    unmapped_rows: tuple[int, ...] = ()
    omitted_rows: tuple[int, ...] = ()
    gaps: tuple[str, ...] = ()
    complete: bool = False


class FilingFactsResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence: EvidencePackage
    rounding_quantum_by_fact: dict[str, Decimal]
    equity_coverage: tuple[EquityTableCoverage, ...]
    adjusted_coverage: tuple[AdjustedTableCoverage, ...] = ()
    gaps: tuple[str, ...]


def _normal(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


_ALIASES = {
    "Equity Common Stock Issuance Value": (
        "Issuance of common stock",
        "Issuance of common stock net of issuance costs",
        "Common stock issued net of issuance costs",
    ),
    "Equity Stock Repurchases/Retirements": (
        "Repurchases and retirement of common stock",
        "Repurchases of common stock",
        "Repurchase and retirement of common stock",
        "Common stock repurchases",
    ),
    "Equity Award Tax Withholding": (
        "Tax withholding related to net share settlement of equity awards",
        "Shares withheld for taxes",
        "Tax withholding on equity awards",
    ),
    "Equity Dividends": ("Dividends declared", "Cash dividends declared", "Common stock dividends"),
    "Equity Conversion of Debt": (
        "Conversion of convertible debt",
        "Common stock issued upon conversion of debt",
        "Conversion of convertible notes",
    ),
    "Employee Stock Purchase Plan Issuance Value": (
        "Issuance of common stock under employee stock purchase plan",
        "Employee stock purchase plan",
    ),
    "Net Income": (
        "Net income",
        "Net income (loss)",
        "Net loss",
        "Net income attributable to parent",
    ),
    "Equity Share-based Compensation": (
        "Share-based compensation",
        "Stock-based compensation",
        "Share based compensation expense",
    ),
    "Other Comprehensive Income Attributable to Parent": (
        "Other comprehensive income",
        "Other comprehensive income (loss)",
        "Other comprehensive loss",
        "Other comprehensive income attributable to parent",
    ),
    "Total Borrowings": ("Total borrowings",),
    "Equipment Financing Principal Payments": (
        "Principal payments on equipment financing obligations",
        "Repayments of equipment financing obligations",
    ),
    "Equipment Financing Obligations": (
        "Equipment financing obligations",
        "Equipment financing liabilities",
    ),
    "Finance Lease and Equipment Obligations": (
        "Finance lease and equipment financing obligations",
        "Finance lease and equipment obligations",
        "Finance lease liabilities and equipment financing obligations",
    ),
}
_ADJUSTED_ALIASES = {
    "Net Income": ("Net income", "Net income (loss)", "Net loss"),
    "Operating Income": ("Operating income", "Operating income (loss)", "Operating loss"),
    "Operating Cash Flow": ("Net cash provided by operating activities", "Operating cash flow"),
    "Adjusted Net Income": ("Adjusted net income", "Adjusted net income (loss)"),
    "Adjusted EBITDA": ("Adjusted EBITDA",),
    "Adjusted Operating Income": ("Adjusted operating income", "Adjusted operating income (loss)"),
    "Adjusted Free Cash Flow": ("Adjusted free cash flow",),
    "Management Share-based Compensation Adjustment": (
        "Share-based compensation",
        "Stock-based compensation",
    ),
    "Management Depreciation and Amortization Adjustment": ("Depreciation and amortization",),
    "Management Interest Adjustment": (
        "Interest expense",
        "Interest expense, net",
        "Interest adjustment",
    ),
    "Management Tax Adjustment": (
        "Tax adjustment",
        "Income tax expense",
        "Income tax expense (benefit)",
        "Tax effect of adjustments",
    ),
    "Management Restructuring Adjustment": ("Restructuring costs", "Restructuring expenses"),
    "Management Acquisition Cost Adjustment": ("Acquisition costs", "Acquisition-related costs"),
    "Management Capital Expenditure Adjustment": ("Capital expenditures",),
    "Management Software Development Adjustment": ("Capitalized software development costs",),
    "Management Financing Principal Adjustment": (
        "Financing principal payments",
        "Principal payments on equipment financing obligations",
    ),
}
_ADJUSTED_LABELS = {
    _normal(label): metric for metric, aliases in _ADJUSTED_ALIASES.items() for label in aliases
}
_ADJUSTED_PAIRS = {
    ("Net Income", "Adjusted Net Income"),
    ("Net Income", "Adjusted EBITDA"),
    ("Operating Income", "Adjusted Operating Income"),
    ("Operating Cash Flow", "Adjusted Free Cash Flow"),
}
_GAAP_BASES = {base for base, _ in _ADJUSTED_PAIRS}
_ADJUSTED_MEASURES = {adjusted for _, adjusted in _ADJUSTED_PAIRS}
_MANAGEMENT_ROLES = {metric for metric in _ADJUSTED_ALIASES if metric.startswith("Management ")}


def _adjusted_context(block):
    section = _normal(block.section)
    return "reconciliation" in section and ("nongaap" in section or "adjusted" in section)


_LABELS = {_normal(label): metric for metric, aliases in _ALIASES.items() for label in aliases}
_OBLIGATIONS = {
    "Equipment Financing Obligations",
    "Finance Lease and Equipment Obligations",
    "Total Borrowings",
}
_REDUCTIONS = {
    "Equity Stock Repurchases/Retirements",
    "Equity Award Tax Withholding",
    "Equity Dividends",
}
_TOTAL_HEADERS = {
    _normal(s)
    for s in (
        "Total stockholders equity",
        "Total shareholders equity",
        "Total equity attributable to parent",
    )
}
_MONTHS = {
    name.lower(): number
    for number in range(1, 13)
    for name in (calendar.month_name[number], calendar.month_abbr[number])
}
_DATE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{4})\b",
    re.I,
)


def _dates(text):
    found = []
    for match in _DATE.finditer(text):
        value = match.group()
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                parsed = date.fromisoformat(value)
            else:
                month, day, year = value.replace(",", "").replace(".", "").split()
                parsed = date(int(year), _MONTHS[month.lower()], int(day))
        except (ValueError, KeyError):
            continue
        found.append(parsed)
    return found


def _rows(block):
    return [
        [cell.strip() for cell in row.strip().split("|")]
        for row in block.text.split(";")
        if row.strip()
    ]


def _metric(label, block=None):
    if block is not None and _adjusted_context(block):
        return _ADJUSTED_LABELS.get(_normal(label))
    if re.match(r"^(?:balance|balances)\s+(?:at|as of)\b", label, re.I) and len(_dates(label)) == 1:
        return "Stockholders Equity"
    return _LABELS.get(_normal(label))


def _equity_context(block):
    text = _normal(block.section)
    return (
        "equity" in text and ("changes" in text or "stockholder" in text or "shareholder" in text)
    ) and "cashflow" not in text


def _scale(block, rows):
    # Units must be present in the source table heading/caption, not supplied
    # by a model or inferred from the number of trailing zeroes in a value.
    heading = " ".join(row[0] for row in rows if len(row) == 1) + " " + block.section
    scales = set()
    for word, factor in (("thousands", 1000), ("millions", 1000000), ("billions", 1000000000)):
        if re.search(r"\b" + word + r"\b", heading, re.I):
            scales.add(factor)
    if not scales and re.search(r"\b(?:actual|whole)\s+(?:US\s+)?dollars\b", heading, re.I):
        scales.add(1)
    if len(scales) != 1:
        raise ValueError("missing or ambiguous source scale")
    if not re.search(r"\b(?:USD|US dollars|U\.S\. dollars)\b", heading, re.I):
        raise ValueError("source heading does not establish US-dollar currency")
    if re.search(
        r"\b(?:EUR|CAD|AUD|GBP|JPY|CNY|euros?|Canadian dollars?|Australian dollars?|yen|yuan|pounds?)\b",
        heading,
        re.I,
    ):
        raise ValueError("source heading has mixed or unsupported currency")
    return Decimal(scales.pop())


def _number(cell, scale):
    value = cell.strip()
    if not re.fullmatch(r"(?:\(?-?\$?\s*\d+(?:,\d{3})*(?:\.\d+)?\)?)", value):
        raise ValueError("missing or unsupported numeric source cell")
    if ("(" in value) != (")" in value):
        raise ValueError("unbalanced numeric parentheses")
    negative = value.startswith("(")
    cleaned = value.strip("()").replace("$", "").replace(",", "").replace(" ", "")
    if negative and cleaned.startswith("-"):
        raise ValueError("ambiguous numeric sign")
    if len(cleaned.replace(".", "").lstrip("-")) > 40:
        raise ValueError("numeric source cell exceeds supported precision")
    places = len(cleaned.partition(".")[2])
    with localcontext() as context:
        context.prec = 60
        number = Decimal(cleaned) * (-1 if negative else 1)
        return number * scale, scale * Decimal(10) ** -places


def _duration(block, rows, column_end=None):
    # An explicit single duration caption; multiple span headings need a
    # richer layout parser and are rejected rather than aligned by guesswork.
    caption = " ".join(row[0] for row in rows if len(row) == 1) + " " + block.section
    matches = re.findall(r"\b(three|six|nine|twelve|3|6|9|12)\s+months?\s+ended\b", caption, re.I)
    if not matches and re.search(r"\byear ended\b", caption, re.I):
        matches = ["twelve"]
    ends = _dates(caption)
    if len(matches) != 1 or len(ends) > 1 or (not ends and column_end is None):
        raise ValueError("missing or ambiguous dated duration caption")
    if column_end is not None and ends and ends[0] != column_end:
        raise ValueError("duration caption conflicts with selected dated column")
    count = {"three": 3, "six": 6, "nine": 9, "twelve": 12}.get(matches[0].lower())
    count = count if count is not None else int(matches[0])
    end = column_end if column_end is not None else ends[0]
    if end.day != calendar.monthrange(end.year, end.month)[1]:
        raise ValueError("unsupported non-month-end duration")
    month_index = end.year * 12 + end.month - count
    start = date(month_index // 12, month_index % 12 + 1, 1)
    return start, end


def _total_header(rows):
    matches = [
        (r, c)
        for r, row in enumerate(rows)
        for c, cell in enumerate(row)
        if c and _normal(cell) in _TOTAL_HEADERS
    ]
    if len(matches) != 1:
        raise ValueError("missing or ambiguous total-equity column")
    return matches[0]


def _dated_column(rows, selection):
    row = rows[selection.row_index]
    candidates = []
    for header in rows[: selection.row_index]:
        if len(header) != len(row):
            continue
        dates = [_dates(cell) for cell in header[1:]]
        if dates and all(
            len(value) == 1 and _DATE.fullmatch(cell.strip())
            for value, cell in zip(dates, header[1:], strict=True)
        ):
            candidates.append(dates[selection.column_index - 1][0])
    if len(candidates) != 1:
        raise ValueError("missing or ambiguous aligned dated column header")
    return candidates[0]


def _period(block, rows, selection):
    if _adjusted_context(block):
        if selection.metric not in _ADJUSTED_ALIASES:
            raise ValueError("unsupported adjusted-reconciliation role")
        return _duration(block, rows, column_end=_dated_column(rows, selection))
    if selection.metric == "Equipment Financing Principal Payments":
        if not re.search(r"\b(?:cash flows?|financing)\b", block.section, re.I) or _equity_context(
            block
        ):
            raise ValueError("equipment principal requires a cash-flow/financing source section")
        return _duration(block, rows, column_end=_dated_column(rows, selection))
    if selection.metric in _OBLIGATIONS:
        if selection.metric == "Total Borrowings" and (
            not re.search(r"\b(?:debt|borrowings)\b", block.section, re.I)
            or re.search(
                r"\b(?:equity|securities|investment|receivables?|leases?|short[- ]term|long[- ]term)\b",
                block.section,
                re.I,
            )
        ):
            raise ValueError(
                "total borrowings require an unqualified debt/borrowings source section"
            )
        if selection.metric == "Total Borrowings" and re.search(
            r"\b(?:leases?|leasing|equipment)\b", block.section + " " + block.text, re.I
        ):
            # A footnote after the total can change its instrument perimeter.
            # This bounded parser cannot establish disjointness from absence
            # of an inclusion statement or by interpreting exclusion prose.
            raise ValueError("borrowings instrument perimeter is ambiguous with leases/equipment")
        context = (
            block.section + " " + " ".join(" ".join(row) for row in rows[: selection.row_index])
        )
        if re.search(
            r"\b(?:current|noncurrent|non-current|long-term)\s+(?:liabilities|portion|obligations)\b",
            context,
            re.I,
        ):
            raise ValueError(
                "obligation source has current/noncurrent scope; total perimeter is unverified"
            )
        return None, _dated_column(rows, selection)
    if not _equity_context(block):
        raise ValueError("source section is not an equity movement statement")
    header_row, total_column = _total_header(rows)
    if selection.column_index != total_column or selection.row_index <= header_row:
        raise ValueError("selection is not the source total-equity column")
    if len(rows[selection.row_index]) != len(rows[header_row]):
        raise ValueError("equity row/header column alignment differs")
    start, end = _duration(block, rows)
    if selection.metric == "Stockholders Equity":
        balance_date = _dates(rows[selection.row_index][0])
        if len(balance_date) != 1 or balance_date[0] not in (start - timedelta(days=1), end):
            raise ValueError("balance date is not the selected period opening or closing")
        return None, balance_date[0]
    return start, end


def discover_filing_cells(disclosures: DisclosurePackage) -> tuple[FilingCellSelection, ...]:
    """Propose only known row roles; every proposal still passes verification."""
    selections = []
    for document in disclosures.documents[:8]:
        for block in document.blocks[:2000]:
            rows = _rows(block)
            for index, row in enumerate(rows[:2001]):
                metric = _metric(row[0], block)
                if not metric:
                    continue
                if (
                    _adjusted_context(block)
                    or metric in _OBLIGATIONS
                    or metric == "Equipment Financing Principal Payments"
                ):
                    columns = range(1, min(len(row), 31))
                else:
                    try:
                        _, column = _total_header(rows)
                    except ValueError:
                        continue
                    columns = (column,)
                selections.extend(
                    FilingCellSelection(
                        source_id=document.source_id,
                        locator=block.locator,
                        metric=metric,
                        row_index=index,
                        column_index=column,
                    )
                    for column in columns
                )
                if len(selections) >= 128:
                    return tuple(selections[:128])
    return tuple(selections)


def verify_filing_cells(disclosures: DisclosurePackage, selections) -> FilingFactsResult:
    selections = tuple(selections)
    gaps = [
        f"{document.source_id}: {gap}"
        for document in disclosures.documents
        for gap in document.gaps
    ]
    if len(selections) > 128:
        gaps.append("Filing cell selection limit reached")
        selections = selections[:128]
    duplicates = {
        d.source_id
        for d in disclosures.documents
        if sum(other.source_id == d.source_id for other in disclosures.documents) > 1
    }
    if duplicates:
        gaps.append("duplicate filing source identifiers")
    documents = {d.source_id: d for d in disclosures.documents if d.source_id not in duplicates}
    facts, sources, quantum, accepted = {}, {}, {}, {}
    for selection in selections:
        try:
            document = documents.get(selection.source_id)
            if document is None:
                raise ValueError("unknown filing source")
            if (
                document.filing.cik != disclosures.cik
                or document.filing.filed_date > disclosures.as_of
            ):
                raise ValueError("filing issuer or cutoff mismatch")
            matches = [b for b in document.blocks if b.locator == selection.locator]
            if len(matches) != 1:
                raise ValueError("unknown or ambiguous source block")
            block = matches[0]
            if getattr(block, "truncated", False):
                raise ValueError("selected source block is truncated")
            rows = _rows(block)
            if selection.row_index >= len(rows) or selection.column_index >= len(
                rows[selection.row_index]
            ):
                raise ValueError("source cell index outside table")
            if _metric(rows[selection.row_index][0], block) != selection.metric:
                raise ValueError("source row label does not establish selected role")
            scale = _scale(block, rows)
            value, rounding = _number(rows[selection.row_index][selection.column_index], scale)
            start, end = _period(block, rows, selection)
            if end > disclosures.as_of:
                raise ValueError("source period exceeds analysis cutoff")
            if selection.metric in _REDUCTIONS and value > 0:
                raise ValueError("equity reduction lacks an explicit negative source sign")
            locator = f"{block.locator}/row-{selection.row_index}/column-{selection.column_index}"
            identity = hashlib.sha256(
                f"{document.source_id}:{document.content_hash}:{locator}:{selection.metric}:{start}:{end}".encode()
            ).hexdigest()
            source_id = "filing-cell-" + identity
            source = SourceRecord(
                source_id=source_id,
                cik=disclosures.cik,
                url=document.url,
                filed_date=document.filing.filed_date,
                retrieved_at=document.retrieved_at,
                content_hash=document.content_hash,
                locator=locator + "; units and dated headers in " + block.locator,
                accession=document.filing.accession,
                form=document.filing.form,
            )
            fact = FinancialFact(
                fact_id=identity,
                metric=selection.metric,
                value=value,
                unit="USD",
                cik=disclosures.cik,
                period_start=start,
                period_end=end,
                as_of=disclosures.as_of,
                basis="management-adjusted"
                if _adjusted_context(block) and selection.metric not in _GAAP_BASES
                else "US-GAAP",
                source_ids=(source_id,),
                locator=locator,
            )
            sources[source_id], facts[identity], quantum[identity] = source, fact, rounding
            accepted[
                (document.source_id, block.locator, selection.row_index, selection.column_index)
            ] = fact
        except (ValueError, TypeError) as exc:
            gaps.append(
                f"{selection.source_id}/{selection.locator}/row-{selection.row_index}: {exc}"
            )
    coverage = []
    for document in disclosures.documents[:8]:
        for block in document.blocks[:2000]:
            if not _equity_context(block) or _adjusted_context(block):
                continue
            rows = _rows(block)
            try:
                header, column = _total_header(rows)
            except ValueError:
                continue
            local_gaps, missing, unknown = _table_source_gaps(document, block), [], []
            if document.source_id in duplicates:
                local_gaps.append("duplicate filing source identifier")
            opening, closing, components = [], [], []
            opening_rows, closing_rows, movement_rows = [], [], []
            try:
                start, end = _duration(block, rows)
                scale = _scale(block, rows)
            except ValueError as exc:
                start = end = None
                scale = None
                local_gaps.append(str(exc))
            for index, row in enumerate(rows[header + 1 :], header + 1):
                if len(row) <= column:
                    if len(row) > 1:
                        unknown.append(index)
                    continue
                fact = accepted.get((document.source_id, block.locator, index, column))
                role = _metric(row[0], block)
                if role == "Stockholders Equity" and fact is not None:
                    if start and fact.period_end == start - timedelta(days=1):
                        opening.append(fact.fact_id)
                        opening_rows.append(index)
                    elif end and fact.period_end == end:
                        closing.append(fact.fact_id)
                        closing_rows.append(index)
                    continue
                if fact is not None:
                    components.append((fact.fact_id, 1))
                    movement_rows.append(index)
                    continue
                try:
                    amount, _ = _number(row[column], scale or Decimal(1))
                    if amount == 0:
                        continue
                except ValueError:
                    pass
                if role:
                    missing.append(index)
                else:
                    unknown.append(index)
            if len(opening) != 1 or len(closing) != 1:
                local_gaps.append("Equity table needs one verified opening and closing balance")
            if len(opening_rows) == len(closing_rows) == 1 and (
                opening_rows[0] >= closing_rows[0]
                or any(not opening_rows[0] < row < closing_rows[0] for row in movement_rows)
            ):
                local_gaps.append("Equity movement rows do not lie between opening and closing")
            if missing:
                local_gaps.append("Nonzero or unavailable equity rows were not verified")
            if unknown:
                local_gaps.append("Equity table contains unmapped movements")
            complete = not (local_gaps or missing or unknown)
            coverage.append(
                EquityTableCoverage(
                    source_id=document.source_id,
                    locator=block.locator,
                    column_index=column,
                    period_start=start,
                    period_end=end,
                    opening_fact_id=opening[0] if len(opening) == 1 else None,
                    closing_fact_id=closing[0] if len(closing) == 1 else None,
                    signed_components=tuple(components),
                    unmapped_rows=tuple(unknown),
                    omitted_rows=tuple(missing),
                    gaps=tuple(local_gaps),
                    complete=complete,
                )
            )
    adjusted_coverage = _adjusted_coverage(disclosures, accepted, duplicates)
    gaps.extend(
        f"{c.source_id}/{c.locator}: {g}" for c in (*coverage, *adjusted_coverage) for g in c.gaps
    )
    return FilingFactsResult(
        evidence=EvidencePackage(
            cik=disclosures.cik,
            as_of=disclosures.as_of,
            scope="Verified selected SEC filing-table cells",
            facts=tuple(facts.values()),
            sources=tuple(sources.values()),
            warnings=tuple(dict.fromkeys(gaps)),
        ),
        rounding_quantum_by_fact=quantum,
        equity_coverage=tuple(coverage),
        adjusted_coverage=tuple(adjusted_coverage),
        gaps=tuple(dict.fromkeys(gaps)),
    )


def _adjusted_coverage(disclosures, accepted, duplicates):
    """Enumerate source rows independently of caller-selected adjustment cells."""
    coverage = []
    for document in disclosures.documents[:8]:
        for block in document.blocks[:2000]:
            if not _adjusted_context(block):
                continue
            rows = _rows(block)
            headers = [
                (index, row)
                for index, row in enumerate(rows)
                if len(row) > 1 and all(_DATE.fullmatch(cell) for cell in row[1:])
            ]
            columns = range(1, len(headers[0][1])) if len(headers) == 1 else (1,)
            for column in columns:
                local_gaps = _table_source_gaps(document, block)
                if document.source_id in duplicates:
                    local_gaps.append("duplicate filing source identifier")
                start = end = None
                try:
                    if len(headers) != 1:
                        raise ValueError("missing or ambiguous aligned dated column header")
                    end = _dates(headers[0][1][column])[0]
                    start, end = _duration(block, rows, column_end=end)
                    scale = _scale(block, rows)
                except ValueError as exc:
                    scale = None
                    local_gaps.append(str(exc))
                bases, adjusted, components = [], [], []
                base_rows, adjusted_rows, component_rows = [], [], []
                missing, unknown = [], []
                header_index = headers[0][0] if len(headers) == 1 else -1
                for index, row in enumerate(rows):
                    if index <= header_index or len(row) <= 1:
                        continue
                    role = _metric(row[0], block)
                    fact = accepted.get((document.source_id, block.locator, index, column))
                    if fact is not None:
                        if role in _GAAP_BASES:
                            bases.append(fact)
                            base_rows.append(index)
                        elif role in _ADJUSTED_MEASURES:
                            adjusted.append(fact)
                            adjusted_rows.append(index)
                        elif role in _MANAGEMENT_ROLES:
                            components.append((fact.fact_id, 1))
                            component_rows.append(index)
                        else:
                            unknown.append(index)
                        continue
                    try:
                        value, _ = _number(row[column], scale or Decimal(1))
                        if value == 0 and role not in _GAAP_BASES | _ADJUSTED_MEASURES:
                            continue
                    except (ValueError, IndexError):
                        pass
                    if role:
                        missing.append(index)
                    else:
                        unknown.append(index)
                if len(bases) != 1 or len(adjusted) != 1:
                    local_gaps.append(
                        "Adjusted table needs one unambiguous GAAP base and adjusted measure"
                    )
                elif (bases[0].metric, adjusted[0].metric) not in _ADJUSTED_PAIRS:
                    local_gaps.append("Unsupported GAAP base and adjusted measure pair")
                elif base_rows[0] >= adjusted_rows[0] or any(
                    not base_rows[0] < index < adjusted_rows[0] for index in component_rows
                ):
                    local_gaps.append(
                        "Adjustment rows must lie between GAAP base and adjusted measure"
                    )
                if not components:
                    local_gaps.append("No verified management adjustments")
                if missing:
                    local_gaps.append("Nonzero or unavailable adjustment rows were omitted")
                if unknown:
                    local_gaps.append("Unmapped source reconciliation rows")
                coverage.append(
                    AdjustedTableCoverage(
                        source_id=document.source_id,
                        locator=block.locator,
                        column_index=column,
                        period_start=start,
                        period_end=end,
                        gaap_fact_id=bases[0].fact_id if len(bases) == 1 else None,
                        adjusted_fact_id=adjusted[0].fact_id if len(adjusted) == 1 else None,
                        signed_components=tuple(components),
                        omitted_rows=tuple(missing),
                        unmapped_rows=tuple(unknown),
                        gaps=tuple(local_gaps),
                        complete=not local_gaps,
                    )
                )
    return coverage


def _table_source_gaps(document, block):
    # Global excerpt bounds may omit unrelated sections while retaining this
    # whole table. Preserve those warnings in the result, but only actual
    # partial blocks and source/parser failures prevent local table coverage.
    gaps = [g for g in document.gaps if not g.startswith("Document text limit reached;")]
    if getattr(block, "truncated", False):
        gaps.append("Source table block is truncated")
    return gaps
