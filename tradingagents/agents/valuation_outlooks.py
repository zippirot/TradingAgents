"""Convert source-grounded annual management disclosures into valuation inputs.

This adapter replays extraction against canonical filing blocks. It does not
trust the analyst's cached claim verdict or invent a fiscal calendar, currency,
EPS share basis, or accounting definition. Unsupported outlooks remain absent;
the valuation validator reports same-period outlook unavailable.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext

from pydantic import ValidationError

from tradingagents.agents.valuation import GroundedOutlook
from tradingagents.dataflows.disclosure_discovery import discover_disclosures
from tradingagents.dataflows.disclosure_evidence import parse_disclosure_report
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage


def _period(text):
    explicit = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})\s+(?:to|through|–|-)\s+(\d{4}-\d{2}-\d{2})", text.strip(), re.I
    )
    if explicit:
        start, end = (date.fromisoformat(value) for value in explicit.groups())
    elif match := re.fullmatch(r"calendar year\s+(\d{4})", text.strip(), re.I):
        year = int(match.group(1))
        start, end = date(year, 1, 1), date(year, 12, 31)
    elif match := re.fullmatch(
        r"(?:twelve|12) months (?:ending|ended)\s+([A-Za-z]+ \d{1,2}, \d{4})", text.strip(), re.I
    ):
        end = datetime.strptime(match.group(1), "%B %d, %Y").date()
        prior_day = min(end.day, calendar.monthrange(end.year - 1, end.month)[1])
        start = date(end.year - 1, end.month, prior_day) + timedelta(days=1)
    else:
        return None
    return (start, end) if 330 <= (end - start).days + 1 <= 400 else None


def _metric(text):
    return {
        "revenue": "Revenue",
        "revenues": "Revenue",
        "total revenue": "Revenue",
        "total revenues": "Revenue",
        "basic eps": "Basic EPS",
        "basic earnings per share": "Basic EPS",
        "diluted eps": "Diluted EPS",
        "diluted earnings per share": "Diluted EPS",
    }.get(" ".join(text.lower().split()))


def _basis(quote):
    adjusted = bool(re.search(r"\b(?:non[- ]GAAP|management[- ]adjusted|adjusted)\b", quote, re.I))
    # Exclude non-GAAP before checking for an independent GAAP claim.
    gaap_text = re.sub(r"\bnon[- ]GAAP\b", "", quote, flags=re.I)
    gaap = bool(re.search(r"\b(?:US[- ]GAAP|U\.S\. GAAP|GAAP)\b", gaap_text, re.I))
    if adjusted == gaap:
        return None
    return "management-adjusted" if adjusted else "US-GAAP"


def _unit(claim, context, metric):
    # Dollar signs alone do not establish which currency the issuer means.
    currency_text = re.sub(r"\bU\.?S\.? dollars\b", "USD", context, flags=re.I)
    currencies = set(re.findall(r"\b(?:USD|EUR|GBP|CAD|AUD|JPY|CHF)\b", currency_text))
    if len(currencies) != 1:
        return None
    currency = currencies.pop()
    unit = claim.unit.lower()
    unit = re.sub(r"\bu\.?s\.? dollars\b", "", unit)
    unit = re.sub(r"\b(?:usd|eur|gbp|cad|aud|jpy|chf)\b", "", unit)
    unit = " ".join(unit.split()).strip()
    if metric == "Revenue":
        scale = {
            "": Decimal(1),
            "dollars": Decimal(1),
            "thousand": Decimal(1000),
            "thousands": Decimal(1000),
            "million": Decimal(1000000),
            "millions": Decimal(1000000),
            "billion": Decimal(1000000000),
            "billions": Decimal(1000000000),
        }.get(unit)
        return (currency, scale) if scale is not None else None
    if unit in {"per share", "/share", "/shares"}:
        return currency + "/shares", Decimal(1)
    return None


def _grounded(state: dict) -> tuple[tuple[GroundedOutlook, ...], tuple[str, ...]]:
    """Replay both claim paths against uniquely matched, complete source blocks.

    The raw disclosure extraction is read from the financial claim record when
    the gate has replaced fundamentals prose with its canonical summary.
    Canonical document SourceRecords must already be in financial_evidence.
    """
    try:
        package = EvidencePackage.model_validate(state.get("financial_evidence"))
        disclosures = DisclosurePackage.model_validate(state.get("filing_evidence"))
        if (
            package.cik != disclosures.cik
            or package.as_of != disclosures.as_of
            or str(package.as_of) != state.get("trade_date")
        ):
            return (), ()
        validation = state.get("financial_claim_validation") or {}
        report = validation.get("raw_report") if isinstance(validation, dict) else None
        report = report if isinstance(report, str) else state.get("fundamentals_report", "")
        if not isinstance(report, str):
            report = ""
        counts = {}
        for doc in disclosures.documents:
            counts[doc.source_id] = counts.get(doc.source_id, 0) + 1
        source_counts = {}
        for source in package.sources:
            source_counts[source.source_id] = source_counts.get(source.source_id, 0) + 1
        sources = {source.source_id: source for source in package.sources}
        blocks, documents, valid_docs = {}, {}, []
        for doc in disclosures.documents:
            source = sources.get(doc.source_id)
            if counts[doc.source_id] != 1 or source_counts.get(doc.source_id) != 1 or source is None:
                continue
            if (
                doc.filing.cik != package.cik
                or doc.filing.filed_date > package.as_of
                or (
                    source.cik,
                    source.url,
                    source.content_hash,
                    source.filed_date,
                    source.accession,
                    source.form,
                )
                != (
                    doc.filing.cik,
                    doc.url,
                    doc.content_hash,
                    doc.filing.filed_date,
                    doc.filing.accession,
                    doc.filing.form,
                )
            ):
                continue
            block_counts = {}
            for block in doc.blocks:
                block_counts[block.locator] = block_counts.get(block.locator, 0) + 1
            valid_blocks = []
            for block in doc.blocks:
                if block_counts[block.locator] == 1 and not block.truncated:
                    blocks[(doc.source_id, block.locator)] = block.section + "\n" + block.text
                    documents[(doc.source_id, block.locator)] = doc
                    valid_blocks.append(block)
            valid_docs.append(doc.model_copy(update={"blocks": tuple(valid_blocks)}))
        verified = disclosures.model_copy(update={"documents": tuple(valid_docs)})
        extraction = parse_disclosure_report(report, blocks, packages=(verified,))
        discovered = discover_disclosures((verified,))
        results = {}
        for claim in (*extraction.claims, *discovered.claims):
            if claim.kind not in {"guidance", "ambition"} or claim.comparator != "exact":
                continue
            source_text = blocks[(claim.source_id, claim.locator)]
            period = _period(claim.period)
            if period is None and (match := re.fullmatch(r"full year ((?:19|20)\d{2})", claim.period, re.I)):
                years = set(re.findall(r"\bcalendar year ((?:19|20)\d{2})\b", source_text, re.I))
                if years == {match.group(1)}:
                    period = _period(f"calendar year {match.group(1)}")
            metric, period, basis = (
                _metric(claim.metric),
                period,
                _basis(source_text),
            )
            if metric is None or period is None or basis is None or period[1] <= package.as_of:
                continue
            unit = _unit(claim, source_text, metric)
            if unit is None:
                continue
            doc = documents[(claim.source_id, claim.locator)]
            with localcontext() as context:
                context.prec = 60
                low = claim.value * unit[1]
                high = (claim.upper_value if claim.upper_value is not None else claim.value) * unit[
                    1
                ]
            identity = hashlib.sha256(
                json.dumps(
                    [
                        doc.source_id,
                        doc.content_hash,
                        claim.locator,
                        claim.model_dump(mode="json"),
                        str(period[0]),
                        str(period[1]),
                    ],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            result = GroundedOutlook(
                record_id="outlook-" + identity,
                source_ids=(doc.source_id,),
                metric=metric,
                unit=unit[0],
                period_start=period[0],
                period_end=period[1],
                basis=basis,
                low=low,
                high=high,
                kind=claim.kind,
            )
            results[result.record_id] = (result, doc.filing.filed_date)
        groups = {}
        for result, filed_date in results.values():
            key = (
                result.metric,
                result.unit,
                result.basis,
                result.period_start,
                result.period_end,
                result.kind,
            )
            groups.setdefault(key, []).append((result, filed_date))
        selected, warnings = [], []
        for key, group in groups.items():
            latest_date = max(filed_date for _, filed_date in group)
            latest = [result for result, filed_date in group if filed_date == latest_date]
            if len({(result.low, result.high) for result in latest}) != 1:
                warnings.append(
                    f"Conflicting same-date {key[5]} {key[0]} outlook ranges for "
                    f"{key[3]} to {key[4]} ({key[1]}, {key[2]}) filed {latest_date}; "
                    "no grounded outlook selected."
                )
                continue  # same-vintage conflicting ranges are not a grounded interval
            selected.append((min(latest, key=lambda result: result.record_id), latest_date))
        # Match the valuation input bound; prefer current filings if the source
        # supplies many distinct annual horizons. No older range overrides it.
        selected.sort(
            key=lambda item: (item[1], item[0].period_end, item[0].record_id), reverse=True
        )
        return tuple(result for result, _ in selected[:30]), tuple(sorted(warnings))
    except (ValidationError, ValueError, TypeError, ArithmeticError):
        return (), ()


def grounded_outlooks(state: dict) -> tuple[GroundedOutlook, ...]:
    """Return source-validated, precisely dated annual management outlooks."""
    return _grounded(state)[0]


def grounded_outlook_warnings(state: dict) -> tuple[str, ...]:
    """Return stable diagnostics for conflicting latest-date source ranges."""
    return _grounded(state)[1]
