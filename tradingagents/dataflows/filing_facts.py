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
    "Equity Incentive Plan Issuance Net of Withholding",
    "Net Income Attributable to Common Stockholders",
    "Finance Lease and Financing Arrangement Principal Payments",
    "Equipment Financing Principal Payments",
    "Equipment Financing Acquisition Payments",
    "Equipment Financing Proceeds",
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
        "Issuance of common stock in connection with follow-on public offering, net of underwriter discounts and issuance costs",
    ),
    "Equity Stock Repurchases/Retirements": (
        "Repurchases and retirement of common stock",
        "Repurchases of common stock",
        "Repurchase and retirement of common stock",
        "Common stock repurchases",
        "Repurchase and retirement of common stock including related costs",
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
        "Issuance of common stock in connection with induced conversion of 2030 Convertible Notes, net of transaction costs and tax",
    ),
    "Employee Stock Purchase Plan Issuance Value": (
        "Issuance of common stock under employee stock purchase plan",
        "Employee stock purchase plan",
        "Issuance of common stock under employee stock purchase plan, net of taxes withheld",
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
    "Total Borrowings": ("Total borrowings", "Carrying value of debt"),
    "Equipment Financing Acquisition Payments": (
        "Acquisition of equipment under financing arrangements",
    ),
    "Equipment Financing Proceeds": ("Proceeds from financing arrangements",),
    "Equity Incentive Plan Issuance Net of Withholding": (
        "Issuance of common stock under equity incentive plan, net of taxes withheld",
    ),
    "Net Income Attributable to Common Stockholders": (
        "Net income attributable to common stockholders",
        "Net loss attributable to common stockholders",
    ),
    "Finance Lease and Financing Arrangement Principal Payments": (
        "Principal repayments of finance leases and financing arrangements",
    ),
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
        "Total present value of finance lease liabilities and equipment financing obligations",
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
    rows = [
        [cell.strip() for cell in row.strip().split("|")]
        for row in block.text.split(";")
        if row.strip()
    ]
    # SEC display tables use spacer cells and isolated currency symbols.
    # Normalize only source-resolved inline-XBRL tables with this padded shape;
    # retain every row index and every actual value, including missing dashes.
    if not getattr(block, "currency_locator", None) or not any(row.count("") >= 3 for row in rows):
        return rows
    compact = []
    for row in rows:
        cells = [cell for cell in row if cell and cell != "$"]
        if cells and not row[0]:
            cells.insert(0, "")
        compact.append(cells or [""])
    for index, row in enumerate(compact):
        if (
            len(row) == 6
            and row[0] == ""
            and _normal(row[1]) == "commonstock"
            and _normal(row[-1]) == "total"
        ):
            following = compact[index + 1] if index + 1 < len(compact) else []
            if [_normal(cell) for cell in following] == ["", "shares", "amount"]:
                if (
                    _normal(row[2]) != "additionalpaidincapital"
                    or not _normal(row[3]).startswith("accumulatedothercomprehensive")
                    or not _normal(row[4]).startswith("retainedearnings")
                ):
                    continue
                compact[index] = [
                    "Movement",
                    "Common Stock Shares",
                    "Common Stock Amount",
                    *row[2:-1],
                    "Total Stockholders Equity",
                ]
                compact[index + 1] = [""]
    # One shared month/day and an explicitly aligned year row. Do not flatten
    # multiple duration groups or infer fiscal calendars from filing dates.
    duration_rows = [
        (i, row)
        for i, row in enumerate(compact)
        if len(row) == 2
        and row[0] == ""
        and re.fullmatch(r"(Three|Six|Nine|Twelve) Months Ended ([A-Za-z]+ \d{1,2}),", row[1], re.I)
    ]
    if len(duration_rows) == 1:
        index, row = duration_rows[0]
        following = compact[index + 1] if index + 1 < len(compact) else []
        if (
            len(following) >= 2
            and following[0] == ""
            and all(re.fullmatch(r"\d{4}", cell) for cell in following[1:])
        ):
            match = re.fullmatch(
                r"(Three|Six|Nine|Twelve) Months Ended ([A-Za-z]+ \d{1,2}),", row[1], re.I
            )
            compact[index] = [match.group(1) + " Months Ended"]
            compact[index + 1] = [
                "Cash Flow",
                *(match.group(2) + ", " + year for year in following[1:]),
            ]
    return compact


_PV_LABEL = _normal(
    "Total present value of finance lease liabilities and equipment financing obligations"
)


def _present_value_roles(rows, row_index):
    row = rows[row_index]
    if _normal(row[0]) != _PV_LABEL or len(row) != 4:
        return {}
    headers = [
        header
        for header in rows[:row_index]
        if len(header) == 4
        and [_normal(cell) for cell in header]
        == ["", "financeleases", "equipmentfinancingobligations", "total"]
    ]
    return (
        {2: "Equipment Financing Obligations", 3: "Finance Lease and Equipment Obligations"}
        if len(headers) == 1
        else {}
    )


def _cell_metric(rows, index, column, block):
    if _normal(rows[index][0]) == _PV_LABEL:
        return _present_value_roles(rows, index).get(column)
    return _metric(rows[index][0], block)


def _equity_period(block, rows):
    try:
        return _duration(block, rows)
    except ValueError:
        # The supported sparse statement explicitly starts and ends with dated
        # balance rows. Those dates bound every intervening movement.
        caption = block.section + " " + " ".join(row[0] for row in rows if len(row) == 1)
        if not getattr(block, "currency_locator", None) or re.search(
            r"\b(?:months?|year)\s+ended\b", caption, re.I
        ):
            raise
        balances = [
            (i, _dates(row[0]))
            for i, row in enumerate(rows)
            if _metric(row[0], block) == "Stockholders Equity"
        ]
        if len(balances) != 2 or any(len(dates) != 1 for _, dates in balances):
            raise ValueError("equity table has ambiguous opening/closing period anchors") from None
        start = balances[0][1][0] + timedelta(days=1)
        end = balances[1][1][0]
        if not 60 <= (end - start).days + 1 <= 400:
            raise ValueError("unsupported equity opening/closing interval") from None
        return start, end


def _primary_financing_period(block, start, end):
    # The comparison year is not the period described by the ensuing drivers.
    opening = block.text.split(", compared to", 1)[0].split(". The change", 1)[0]
    dates = _dates(opening)
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    word = {3: "three", 6: "six", 9: "nine", 12: "twelve"}.get(months)
    return (
        not block.truncated
        and word is not None
        and dates == [end]
        and start.day == 1
        and re.search(r"^Net cash (?:provided by|used in) financing activities", opening)
        and re.search(r"\b" + word + r" months ended\b", opening, re.I)
    )


def _rounded_prose_amount(text, phrase, value, end):
    # Supported source grammar is the single current-period driver sentence,
    # after the opening cash-flow comparison. Complex period qualifications
    # remain unclassified rather than borrowing the opening sentence's date.
    marker = ". The change was primarily driven by "
    if text.count(marker) != 1:
        return False
    drivers = text.split(marker, 1)[1]
    if re.search(
        r"\b(?:prior|previous|comparative|comparison|last)[ -]?(?:year|period)?\b", drivers, re.I
    ):
        return False
    if any(d != end for d in _dates(drivers)):
        return False
    temporal_years = re.findall(
        r"\b(?:in|during|for)\s+(?:the\s+(?:year|period)\s+)?(20\d{2})\b", drivers, re.I
    )
    if any(int(year) != end.year for year in temporal_years):
        return False
    # A new sentence can introduce another temporal subject. Decimal points
    # in source amounts do not delimit sentences.
    if re.search(r"\.\s+[A-Za-z]", drivers):
        return False
    text = drivers
    matches = list(re.finditer(r"\$([0-9]+(?:\.[0-9]+)?) million " + phrase, text, re.I))
    if len(matches) != 1:
        return False
    amount, quantum = _number(matches[0].group(1), Decimal(1000000))
    return abs(abs(value) - amount) <= quantum / 2


def _equipment_principal_definition(document, start, end, value):
    phrase = r"of principal repayments for finance leases and financing arrangements for data center equipment"
    matches = [
        block
        for block in document.blocks
        if _primary_financing_period(block, start, end)
        and _rounded_prose_amount(block.text, phrase, value, end)
    ]
    if len(matches) != 1:
        raise ValueError("combined principal equipment scope amount/period is not established")
    return matches[0]


def _equipment_pair_definition(document, start, end, value):
    scope = [
        block
        for block in document.blocks
        if _primary_financing_period(block, start, end)
        and _rounded_prose_amount(block.text, r"from equipment financing arrangements", value, end)
    ]
    relation = [
        block
        for block in document.blocks
        if not block.truncated
        and re.search(
            r"cash payments for the acquisition of equipment under financing arrangements "
            r"\(for which we received an equivalent amount of proceeds discussed below",
            block.text,
            re.I,
        )
        and _dates(block.text)[:1] == [end]
        and re.search(r"nine months ended", block.text, re.I)
        and start == date(end.year, 1, 1)
        and end.month == 9
        and end.day == 30
    ]
    if len(scope) != 1 or len(relation) != 1:
        raise ValueError("equipment acquisition/proceeds relationship amount/period is unavailable")
    return [
        (relation[0], "equipment financing acquisition/proceeds definition"),
        (scope[0], "equipment financing proceeds amount/period definition"),
    ]


def _borrowings_definition(document, block, rows, selection, end, scale, value):
    # Narrow complete instrument inventory. No generic debt-total alias and no
    # zero inferred from a missing/dash cell.
    def unique(phrase):
        found = [b for b in document.blocks if not b.truncated and phrase in b.text]
        if len(found) != 1:
            raise ValueError("complete borrowings perimeter source is unavailable")
        return found[0]

    intro = unique("net carrying amount of the Company’s debt consisted of the following")
    facility = unique("once borrowed and repaid, cannot be reborrowed")
    repaid = unique("repaid the $500,000 outstanding principal of its Term Loan Facility")
    undrawn = unique(
        "No drawdowns have been made under the Company’s letters of credit and the Revolving Facility"
    )
    if end not in _dates(undrawn.text) or end not in _dates(repaid.text):
        raise ValueError("borrowings facility scope date is not the selected date")
    if not re.search(r"On March 27, 2026, the Company repaid", repaid.text) or end < date(
        2026, 3, 27
    ):
        raise ValueError("unsupported term-loan repayment date")
    indexed = {_normal(row[0]): row for row in rows}
    total_index = next((i for i, r in enumerate(rows) if _normal(r[0]) == "totalobligations"), None)
    if total_index is None:
        raise ValueError("missing complete debt obligations row")
    instruments = [r for r in rows[:total_index] if r[0] and len(r) > 1]
    if (
        not instruments
        or sum(row[0] == "Term Loan Facility" for row in instruments) != 1
        or len({row[0] for row in instruments}) != len(instruments)
        or any(selection.column_index >= len(row) for row in rows if len(row) > 1)
        or any(
            not re.fullmatch(r"(?:20\d{2} Convertible Notes|Term Loan Facility)", r[0])
            for r in instruments
        )
    ):
        raise ValueError("unmapped or misaligned borrowing instrument")
    col = selection.column_index
    amounts = []
    for row in instruments:
        if row[0] == "Term Loan Facility" and row[col] in ("—", "–", "-"):
            amounts.append(Decimal(0))  # Explicit full repayment and no reborrow above.
        else:
            amounts.append(_number(row[col], scale)[0])

    def amount(label):
        row = indexed.get(_normal(label))
        if row is None:
            raise ValueError("missing debt carrying-value reconciliation row")
        return _number(row[col], scale)[0]

    total = amount("Total obligations")
    if sum(amounts) != total or total + amount("Unamortized debt issuance costs") != value:
        raise ValueError("debt instruments do not reconcile to carrying value")
    if -amount("Less: Debt, current") + amount("Debt, long-term") != value:
        raise ValueError("debt current/noncurrent carrying values do not reconcile")
    return [(b, "borrowings perimeter definition") for b in (intro, facility, repaid, undrawn)]


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
    if not re.search(r"\b(?:USD|US dollars|U\.S\. dollars)\b", heading, re.I) and (
        getattr(block, "currency", None) != "USD" or not getattr(block, "currency_locator", None)
    ):
        raise ValueError("source heading or inline-XBRL cells do not establish US-dollar currency")
    if getattr(block, "currency", None) not in (None, "USD"):
        raise ValueError("source inline-XBRL currency conflicts with USD heading")
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
    if selection.metric in {
        "Equipment Financing Principal Payments",
        "Equipment Financing Acquisition Payments",
        "Equipment Financing Proceeds",
        "Finance Lease and Financing Arrangement Principal Payments",
    }:
        if not re.search(r"\b(?:cash flows?|financing)\b", block.section, re.I) or _equity_context(
            block
        ):
            raise ValueError("equipment principal requires a cash-flow/financing source section")
        return _duration(block, rows, column_end=_dated_column(rows, selection))
    if selection.metric in _OBLIGATIONS:
        if (
            _present_value_roles(rows, selection.row_index).get(selection.column_index)
            == selection.metric
        ):
            matches = re.findall(r"as of ([A-Za-z]+ \d{1,2}, \d{4})", block.section, re.I)
            if len(matches) != 1 or len(_dates(matches[0])) != 1:
                raise ValueError("present-value obligations require an exact source as-of caption")
            return None, _dates(matches[0])[0]
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
    start, end = _equity_period(block, rows)
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
                    or metric
                    in {
                        "Equipment Financing Principal Payments",
                        "Equipment Financing Acquisition Payments",
                        "Equipment Financing Proceeds",
                        "Finance Lease and Financing Arrangement Principal Payments",
                    }
                ):
                    columns = range(1, min(len(row), 31))
                else:
                    try:
                        _, column = _total_header(rows)
                    except ValueError:
                        continue
                    columns = (column,)
                if _normal(row[0]) == _PV_LABEL:
                    roles = _present_value_roles(rows, index)
                    selections.extend(
                        FilingCellSelection(
                            source_id=document.source_id,
                            locator=block.locator,
                            metric=role,
                            row_index=index,
                            column_index=column,
                        )
                        for column, role in roles.items()
                    )
                    continue
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
            if (
                _cell_metric(rows, selection.row_index, selection.column_index, block)
                != selection.metric
            ):
                raise ValueError("source row label does not establish selected role")
            scale = _scale(block, rows)
            value, rounding = _number(rows[selection.row_index][selection.column_index], scale)
            start, end = _period(block, rows, selection)
            if end > disclosures.as_of:
                raise ValueError("source period exceeds analysis cutoff")
            if selection.metric in _REDUCTIONS and value > 0:
                raise ValueError("equity reduction lacks an explicit negative source sign")
            locator = f"{block.locator}/row-{selection.row_index}/column-{selection.column_index}"
            definitions = []
            if selection.metric == "Finance Lease and Financing Arrangement Principal Payments":
                try:
                    definition = _equipment_principal_definition(document, start, end, value)
                    locator += "; equipment scope: " + definition.locator
                    definitions = [(definition, "finance/equipment principal definition")]
                except ValueError as exc:
                    gaps.append(f"{document.source_id}/{block.locator}: {exc}")
            elif selection.metric in {
                "Equipment Financing Acquisition Payments",
                "Equipment Financing Proceeds",
            }:
                definitions = _equipment_pair_definition(document, start, end, value)
                locator += "; equipment financing scope: " + definitions[0][0].locator
            elif (
                selection.metric == "Total Borrowings"
                and _normal(rows[selection.row_index][0]) == "carryingvalueofdebt"
            ):
                definitions = _borrowings_definition(
                    document, block, rows, selection, end, scale, value
                )
                locator += "; borrowings scope: " + ", ".join(d.locator for d, _ in definitions)
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
                locator=locator
                + "; units and dated headers in "
                + block.locator
                + (
                    "; " + block.currency_locator
                    if getattr(block, "currency_locator", None)
                    else ""
                ),
                accession=document.filing.accession,
                form=document.filing.form,
            )
            definition_sources = []
            for definition, kind in definitions:
                definition_id = (
                    "filing-definition-"
                    + hashlib.sha256(
                        f"{document.source_id}:{document.content_hash}:{definition.locator}:{kind}".encode()
                    ).hexdigest()
                )
                definition_sources.append(
                    SourceRecord(
                        source_id=definition_id,
                        cik=disclosures.cik,
                        url=document.url,
                        filed_date=document.filing.filed_date,
                        retrieved_at=document.retrieved_at,
                        content_hash=document.content_hash,
                        locator=definition.locator + "; " + kind,
                        accession=document.filing.accession,
                        form=document.filing.form,
                    )
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
                source_ids=(source_id, *(item.source_id for item in definition_sources)),
                locator=locator,
            )
            sources[source_id], facts[identity], quantum[identity] = source, fact, rounding
            for definition_source in definition_sources:
                sources[definition_source.source_id] = definition_source
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
                start, end = _equity_period(block, rows)
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
