"""Compact source-bound history from validated retained SEC documents.

Retained blocks are source data, never instructions. Only narrow dated patterns
become facts here; the existing KPI comparison validates current RPO amounts.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from tradingagents.agents.document_access import validated_document_corpus
from tradingagents.agents.kpi_comparisons import compare_rpo
from tradingagents.dataflows.filing_facts import _number, _rows, _scale


def _primary_at(corpus, period):
    if any(doc.filing.form in {"10-Q/A", "10-K/A"} and doc.filing.report_date == period
           for doc in corpus.documents):
        return None
    docs = [doc for doc in corpus.documents if doc.filing.form in {"10-Q", "10-K"}
            and doc.url == doc.filing.url and doc.filing.report_date == period]
    return docs[0] if len(docs) == 1 else None


def _one_document(corpus, doc):
    return corpus.model_copy(update={"documents": (doc,),
                                     "selected_accessions": (doc.filing.accession,)})


def _source(doc, block):
    return f"{doc.source_id}/{block.locator}"


def _note_unit(doc, block):
    """Accept only the note header's immediately following thousands caption."""
    index = next((i for i, item in enumerate(doc.blocks) if item.locator == block.locator), -1)
    notes = [i for i, item in enumerate(doc.blocks[:index]) if re.fullmatch(
        r"NOTES TO (?:CONDENSED )?CONSOLIDATED FINANCIAL STATEMENTS", item.text, re.I)]
    if index < 2 or len(notes) != 1 or notes[0] + 1 >= index:
        return None
    unit = doc.blocks[notes[0] + 1]
    if not re.fullmatch(r"\(in thousands, except (?:share|share and per share) amounts\)", unit.text, re.I):
        return None
    return unit


def _unique_block(corpus, pattern, forms):
    found = [(doc, block, match) for doc in corpus.documents if doc.filing.form in forms
             for block in doc.blocks if not block.truncated
             for match in [re.search(pattern, block.text, re.I)] if match]
    return found[0] if len(found) == 1 else None


def _dated_amount(text, expected):
    try:
        return datetime.strptime(text, "%B %d, %Y").date() == expected
    except ValueError:
        return False


_QUARTER_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_YEAR_AGO = re.compile(
    r"\bRPO was (\$[\d,]+ million) in the (first|second|third|fourth) quarter of (\d{4})\.", re.I)


def _year_ago_match(text, current_period):
    match = _YEAR_AGO.search(text)
    quarter = (current_period.month - 1) // 3 + 1
    if (match and _QUARTER_WORDS[match.group(2).lower()] == quarter
            and int(match.group(3)) == current_period.year - 1):
        return match
    return None


def _reporting_currency(doc):
    declarations = [match.group() for block in doc.blocks if not block.truncated
                    for match in re.finditer(
                        r"The reporting currency of the Company is[^.]*\.", block.text, re.I)]
    if len(declarations) != 1:
        return None
    return ("USD" if re.fullmatch(
        r"The reporting currency of the Company is the United States dollar \([“\"]USD[”\"]\)\.",
        declarations[0], re.I) else None)


def _conflicting_currency_declaration(doc):
    return (any(re.search(r"\breporting currency of the Company is\b", block.text, re.I)
                for block in doc.blocks)
            and _reporting_currency(doc) != "USD")


def render_retained_kpi_history(state) -> str:
    """Render verified RPO quarters and explicitly dated older observations."""
    corpus = validated_document_corpus(state)
    if corpus is None:
        return ""
    periods = sorted({doc.filing.report_date for doc in corpus.documents
                      if doc.filing.form == "10-Q" and doc.url == doc.filing.url
                      and doc.filing.report_date})
    if len(periods) < 2:
        return ""
    current, prior = _primary_at(corpus, periods[-1]), _primary_at(corpus, periods[-2])
    if current is None or prior is None:
        return ""
    comparison = compare_rpo(_one_document(corpus, current), _one_document(corpus, prior))
    if comparison["status"] != "pass" or comparison["currency"] != "USD":
        return ""
    lines = ["Remaining performance obligations (RPO) history:"]
    year_ago = _unique_block(corpus, _YEAR_AGO.pattern, {"8-K"})
    if year_ago:
        doc, block, match = year_ago
        if _year_ago_match(block.text, periods[-1]):
            lines.append(f"{match.group(2).lower()} quarter of {match.group(3)} "
                         f"{match.group(1)} ({_source(doc, block)}).")
    years = sorted({doc.filing.report_date for doc in corpus.documents
                    if doc.filing.form == "10-K" and doc.filing.report_date
                    and doc.filing.report_date < periods[-1]})
    if years:
        annual = _primary_at(corpus, years[-1])
        if annual:
            fiscal = _unique_block(_one_document(corpus, annual),
                r"As of ([A-Z][a-z]+ \d{1,2}, \d{4}), the aggregate transaction price allocated to the remaining performance obligations.*?\b(?:is|was) \$([\d,]+)\b",
                {"10-K"})
            if fiscal:
                doc, block, match = fiscal
                unit = _note_unit(doc, block)
                if unit and _reporting_currency(doc) == "USD" and _dated_amount(match.group(1), years[-1]):
                    value = Decimal(match.group(2).replace(",", "")) * 1000
                    lines.append(f"FY{years[-1].year} {value:,.0f} USD ({_source(doc, block)}; "
                                 f"unit {unit.locator}).")
    for label, doc, value, source in (
        ("prior", prior, comparison["prior_value"], comparison["sources"]["prior"]),
        ("current", current, comparison["current_value"], comparison["sources"]["current"]),
    ):
        period = doc.filing.report_date
        lines.append(f"{period.isoformat()} {Decimal(value):,.0f} USD "
                     f"({source['source_id']}/{source['fact']['locator']}; {label}).")
    next_year = _unique_block(_one_document(corpus, current),
        r"As of ([A-Z][a-z]+ \d{1,2}, \d{4}), the Company expects to recognize \$([\d,]+) of its remaining performance obligations as revenue over the next 12 months",
        {"10-Q"})
    if next_year:
        doc, block, match = next_year
        source = comparison["sources"]["current"]
        if (_note_unit(doc, block) and _dated_amount(match.group(1), periods[-1])
                and source["source_id"] == doc.source_id and source["fact"]["currency"] == "USD"
                and not _conflicting_currency_declaration(doc)):
            amount = Decimal(match.group(2).replace(",", "")) * 1000
            if 0 <= amount <= Decimal(comparison["current_value"]):
                lines.append(f"Next 12 months {amount:,.0f} USD ({_source(doc, block)}).")
    recast = _unique_block(corpus,
        r"RPO amount represents all contracts regardless of the duration of their original expected term\. Prior periods have been recast to conform",
        {"8-K"})
    if recast:
        doc, block, _ = recast
        lines.append(f"RPO prior periods recast to include all contracts ({_source(doc, block)}).")
    return " ".join(lines)


def _millions(value):
    return f"${value / Decimal(1_000_000):,.1f}M"


def render_lease_maturities(state) -> str:
    """Render only source-supported total-column maturity amounts."""
    corpus = validated_document_corpus(state)
    if corpus is None:
        return ""
    periods = sorted({doc.filing.report_date for doc in corpus.documents
                      if doc.filing.form == "10-Q" and doc.filing.report_date})
    if not periods:
        return ""
    doc = _primary_at(corpus, periods[-1])
    if doc is None:
        return ""
    caption = (r"Maturities of finance lease liabilities and equipment financing obligations as of "
               + re.escape(periods[-1].strftime("%B %d, %Y")) + r" were as follows:")
    blocks = [block for block in doc.blocks if not block.truncated
              and re.search(caption, block.section, re.I)]
    if len(blocks) != 1:
        return ""
    block = blocks[0]
    try:
        rows = _rows(block)
        if sum(row == ["", "Finance Leases", "Equipment Financing Obligations", "Total"] for row in rows) != 1:
            return ""
        scale = _scale(block, rows)
        labels = {
            "Total undiscounted finance lease liabilities and equipment financing obligations": "total",
            "Less: Imputed interest": "interest",
            "Total present value of finance lease liabilities and equipment financing obligations": "present value",
        }
        amounts = {}
        for row in rows:
            if row:
                key = row[0] if re.fullmatch(r"20\d{2}", row[0]) else labels.get(row[0])
            else:
                key = None
            if key:
                if key in amounts or len(row) != 4:
                    return ""
                amounts[key] = _number(row[3], scale)[0]
        if not amounts or ("interest" in amounts and amounts["interest"] >= 0):
            return ""
        if (all(key in amounts for key in ("total", "interest", "present value"))
                and amounts["total"] + amounts["interest"] != amounts["present value"]):
            return ""
        years = sorted(key for key in amounts if re.fullmatch(r"20\d{2}", key))
        pieces = [f"{year} {_millions(amounts[year])}" for year in years]
        if "total" in amounts:
            pieces.append(f"total {_millions(amounts['total'])}")
        if "interest" in amounts:
            pieces.append(f"less imputed interest {_millions(-amounts['interest'])}")
        if "present value" in amounts:
            pieces.append(f"present value {_millions(amounts['present value'])}")
        return ("Finance lease and equipment maturities (undiscounted, include imputed interest): "
                + "; ".join(pieces) + f" ({_source(doc, block)}). Scheduled payments are not principal.")
    except (ValueError, ArithmeticError):
        return ""
