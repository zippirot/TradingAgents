"""Cutoff-bound equity-value/revenue reference arithmetic from retained evidence.

Historical closes and split coverage are acquired and authenticated upstream.
This module checks their bounded projection and never fetches market data.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, localcontext
from html import escape

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.agents.evidence_validation import (
    _select_compatible_fact,
    validate_calculation_lineage,
)
from tradingagents.dataflows.financial_evidence import EvidencePackage, FinancialFact, derive_ttm
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation


class HistoricalPrice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    ticker: str
    quarter_end: date
    session_date: date
    session_status: str
    close: Decimal
    currency: str
    source_id: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: str
    adjustment_basis: str
    split_basis_date: date


class SplitAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    session_date: date
    ratio: Decimal
    source_id: str


class SplitHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticker: str
    coverage_complete: bool
    coverage_start: date
    coverage_end: date
    split_basis_date: date
    source_id: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    splits: tuple[SplitAction, ...]


def _unavailable(reason: str) -> dict:
    return {"status": "unavailable", "reason": reason, "rows": []}


def _number(value: Decimal) -> str:
    return format(value, "f")


def _sources(package: EvidencePackage, fact: FinancialFact) -> list[dict]:
    ids = set(fact.source_ids)
    for parent in fact.input_fact_ids:
        original = next((f for f in package.facts if f.fact_id == parent), None)
        if original:
            ids.update(original.source_ids)
    return [
        {"source_id": s.source_id, "filed_date": str(s.filed_date), "url": s.url}
        for s in package.sources if s.source_id in ids
    ]


def _identity(package: EvidencePackage, issuer_identity: dict, ticker: str) -> str:
    symbol = normalize_symbol(ticker)
    if not isinstance(issuer_identity, dict) or (
        issuer_identity.get("ticker") != symbol
        or issuer_identity.get("cik") != package.cik
        or issuer_identity.get("as_of") != str(package.as_of)
        or issuer_identity.get("source") != "SEC issuer map"
    ):
        raise ValueError("SEC issuer identity does not bind ticker and facts")
    return symbol


def _validated_package(package) -> EvidencePackage:
    # Revalidate even a model_copy-updated instance; Pydantic otherwise trusts it.
    package = EvidencePackage.model_validate(
        package.model_dump(mode="json") if isinstance(package, EvidencePackage) else package
    )
    failures = validate_calculation_lineage(package)
    if failures:
        raise ValueError("Invalid financial calculation lineage: " + failures[0])
    return package


def _selected(package: EvidencePackage, facts: list[FinancialFact]) -> FinancialFact | None:
    facts = [f for f in facts if f.value is not None]
    return _select_compatible_fact(package, facts)


def _quarters(package: EvidencePackage, metric: str, currency: str) -> dict[date, FinancialFact | None]:
    grouped: dict[tuple[date, date], list[FinancialFact]] = {}
    for f in package.facts:
        if f.metric != metric or f.unit != currency or f.period_start is None or f.value is None:
            continue
        duration = (f.period_end - f.period_start).days + 1
        if 60 <= duration <= 115:
            grouped.setdefault((f.period_start, f.period_end), []).append(f)
    result = {}
    for (_, end), candidates in grouped.items():
        result[end] = _selected(package, candidates)
    return result


def _ttm_at(package: EvidencePackage, quarter_end: date, metric: str, currency: str, *, positive=True) -> FinancialFact | None:
    quarters = _quarters(package, metric, currency)
    earlier = sorted((end for end in quarters if end <= quarter_end), reverse=True)
    if not earlier or earlier[0] != quarter_end or len(earlier) < 4:
        return None
    selected = [quarters[end] for end in earlier[:4]]
    if any(f is None for f in selected):
        return None
    try:
        result = derive_ttm(selected)
    except (ValueError, ArithmeticError):
        return None
    return result if result.value is not None and (not positive or result.value > 0) else None


def _shares_at(package: EvidencePackage, day: date) -> FinancialFact | None:
    return _selected(package, [
        f for f in package.facts
        if f.metric == "Common Shares Outstanding" and f.period_start is None
        and f.period_end == day and f.unit == "shares" and f.value is not None and f.value > 0
    ])


def _latest_shares(package: EvidencePackage, day: date) -> FinancialFact | None:
    dates = sorted({
        f.period_end for f in package.facts
        if f.metric == "Common Shares Outstanding" and f.period_start is None
        and f.period_end <= day and f.unit == "shares" and f.value is not None and f.value > 0
    }, reverse=True)
    for when in dates:
        selected = _shares_at(package, when)
        if selected is not None:
            return selected
    return None


def _latest_ttm(package: EvidencePackage, day: date, currency: str, metric: str = "Revenue") -> FinancialFact | None:
    for end in sorted((e for e in _quarters(package, metric, currency) if e <= day), reverse=True):
        fact = _ttm_at(package, end, metric, currency)
        if fact is not None:
            return fact
    return None


def _lineage(package: EvidencePackage, fact: FinancialFact) -> dict:
    return {
        "fact_id": fact.fact_id,
        "period_start": str(fact.period_start),
        "period_end": str(fact.period_end),
        "input_fact_ids": list(fact.input_fact_ids),
        "source_ids": list(fact.source_ids),
        "sources": _sources(package, fact),
    }



def _revenue_tax_definitions(package, fact):
    locators = [source.locator for source in package.sources if source.source_id in fact.source_ids]
    return {kind for kind in ("IncludingAssessedTax", "ExcludingAssessedTax")
            if any("RevenueFromContractWithCustomer" + kind in locator for locator in locators)}


def _stats(values: list[Decimal]) -> dict:
    ordered = sorted(values)
    middle = len(ordered) // 2
    with localcontext() as ctx:
        ctx.prec = 60
        median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {"low": _number(ordered[0]), "median": _number(median), "high": _number(ordered[-1]), "count": len(ordered)}


def calculate_own_history(package, issuer_identity: dict, prices, split_history, *, ticker: str, current_multiple=None) -> dict:
    """Retrospective quarter-end equity value / TTM revenue, never a backtest."""
    try:
        package = _validated_package(package)
        ticker = _identity(package, issuer_identity, ticker)
        history = SplitHistory.model_validate(split_history)
        if history.ticker != ticker or not history.coverage_complete or history.split_basis_date != package.as_of:
            raise ValueError("Complete split coverage through analysis cutoff unavailable")
        if history.coverage_end < history.split_basis_date or history.coverage_start > history.coverage_end:
            raise ValueError("Split coverage does not span price basis")
        if not re.fullmatch(r"[0-9a-f]{64}", history.content_hash):
            raise ValueError("Invalid retained split source hash")
        actions = sorted(history.splits, key=lambda item: item.session_date)
        if len({s.session_date for s in actions}) != len(actions) or any(
            s.ratio <= 0 or not history.coverage_start <= s.session_date <= history.coverage_end
            or s.source_id != history.source_id for s in actions
        ):
            raise ValueError("Invalid or duplicate split actions")
        records = [HistoricalPrice.model_validate(p) for p in prices]
        if len(records) > 24:
            raise ValueError("Historical price input exceeds 24 quarters")
        if not records:
            raise ValueError("Historical prices unavailable")
        if len({p.quarter_end for p in records}) != len(records):
            raise ValueError("Duplicate historical quarter-end price")
        if history.coverage_start > min(p.quarter_end for p in records):
            raise ValueError("Split coverage does not reach oldest quarter")
        rows, reasons = [], []
        for p in sorted(records, key=lambda item: item.quarter_end):
            if (p.ticker != ticker or p.quarter_end > package.as_of or p.split_basis_date != history.split_basis_date
                or p.session_status != "completed" or p.adjustment_basis != "historical_split_adjusted"
                or p.currency not in {"USD", "EUR", "GBP", "CAD", "AUD", "JPY"}
                or p.source_id != history.source_id or p.content_hash != history.content_hash
                or not p.source_url.startswith("https://")):
                reasons.append(f"{p.quarter_end}: invalid completed price, identity, or split basis")
                continue
            if p.close <= 0 or p.session_date > p.quarter_end or (p.quarter_end - p.session_date).days > 7:
                reasons.append(f"{p.quarter_end}: completed close unavailable within seven days")
                continue
            shares = _shares_at(package, p.quarter_end)
            ttm = _ttm_at(package, p.quarter_end, "Revenue", p.currency)
            if shares is None or ttm is None:
                reasons.append(f"{p.quarter_end}: exact quarter-end shares or compatible TTM revenue unavailable")
                continue
            with localcontext() as ctx:
                ctx.prec = 60
                factor = Decimal(1)
                applied = []
                for action in actions:
                    if p.quarter_end < action.session_date <= history.split_basis_date:
                        factor *= action.ratio
                        applied.append({"session_date": str(action.session_date), "ratio": _number(action.ratio), "source_id": action.source_id})
                adjusted_shares = shares.value * factor
                multiple = p.close * adjusted_shares / ttm.value
            rows.append({
                "quarter_end": str(p.quarter_end), "status": "available",
                "basis": "equity_value / trailing_revenue",
                "multiple": _number(multiple), "equity_value": _number(p.close * adjusted_shares), "equity_value_unit": p.currency,
                "close": _number(p.close), "currency": p.currency, "price_unit": p.currency + "/share", "price_session": str(p.session_date),
                "price_source_id": p.source_id, "price_source_hash": p.content_hash, "price_source_url": p.source_url,
                "share_date": str(shares.period_end), "shares": _number(shares.value), "share_unit": "shares",
                "adjusted_shares": _number(adjusted_shares), "split_factor": _number(factor),
                "split_basis_date": str(history.split_basis_date), "applied_splits": applied,
                "share_fact": _lineage(package, shares), "revenue": _number(ttm.value), "revenue_unit": p.currency,
                "revenue_fact": _lineage(package, ttm),
            })
        if len(rows) < 4:
            return {**_unavailable("Fewer than four usable own-history quarters"), "excluded": reasons, "usable_quarters": len(rows)}
        multiples = [Decimal(row["multiple"]) for row in rows]
        statistics = _stats(multiples)
        position = {"status": "unavailable", "reason": "Current source-only equity/revenue multiple unavailable"}
        if current_multiple is not None:
            current = Decimal(str(current_multiple))
            if not current.is_finite() or current <= 0:
                raise ValueError("Current equity/revenue multiple must be finite and positive")
            position = {"status": "available", "multiple": _number(current),
                        "relative_to_range": "below" if current < min(multiples) else "above" if current > max(multiples) else "within",
                        "quarters_at_or_below": sum(value <= current for value in multiples),
                        "quarters": len(multiples)}
        return {
            "status": "available", "reason": None, "ticker": ticker,
            "basis": "equity_value / trailing_revenue",
            "label": "Retrospective series from filings available by the analysis cutoff; not a point-in-time backtest",
            "as_of": str(package.as_of), "split_basis_date": str(history.split_basis_date),
            "split_source_id": history.source_id, "split_source_hash": history.content_hash,
            "statistics": statistics, "current_position": position, "rows": rows, "excluded": reasons,
        }
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return _unavailable(str(exc))


def calculate_peer_statistics(package, issuer_identity: dict, price_observation, *, ticker: str, completed_cutoff: date, peer_cover_shares=None, include_quality=False) -> dict:
    """Current peer equity/revenue; growth and margin fail independently."""
    try:
        package = _validated_package(package)
        ticker = _identity(package, issuer_identity, ticker)
        cutoff = date.fromisoformat(str(completed_cutoff))
        if cutoff > package.as_of:
            raise ValueError("Peer completed cutoff exceeds analysis date")
        quote = validate_price_observation(price_observation, ticker, package.as_of)
        if quote["session_status"] != "completed":
            raise ValueError("Completed peer price required")
        session = date.fromisoformat(quote["session_date"])
        if session != cutoff:
            raise ValueError("Peer session does not match subject canonical completed-session cutoff")
        shares = _latest_shares(package, session)
        cover = None
        if shares is None and peer_cover_shares is not None:
            from tradingagents.dataflows.vendors.peer_shares import replay_peer_cover_shares
            cover = replay_peer_cover_shares(peer_cover_shares, package.cik, str(package.as_of), str(session))
        if shares is None and cover is None:
            raise ValueError("Usable verified outstanding shares unavailable")
        share_date = shares.period_end if shares is not None else date.fromisoformat(cover["share_date"])
        share_value = shares.value if shares is not None else Decimal(cover["shares"])
        share_lineage = _lineage(package, shares) if shares is not None else {
            "origin": "conditional_peer_calculation", "formula_id": "sum_disjoint_equivalent_cover_classes",
            "fact_id": cover["source_id"], "period_start": None, "period_end": cover["share_date"],
            "input_fact_ids": [row["locator"] for row in cover["components"]],
            "source_ids": [cover["source_id"]], "sources": [cover["source"]],
            "components": cover["components"], "rights_quote": cover["rights_quote"],
        }
        if (not quote["coverage_complete"] or date.fromisoformat(quote["coverage_start"]) > share_date
            or date.fromisoformat(quote["coverage_end"]) < session):
            raise ValueError("Split coverage does not span peer share date to price")
        if any(share_date < date.fromisoformat(item["session_date"]) <= package.as_of
               and Decimal(item["ratio"]) != 1 for item in quote["splits"]):
            raise ValueError("Peer share and price split bases incompatible")
        currency = quote["currency"]
        ttm = _latest_ttm(package, session, currency)
        if ttm is None:
            raise ValueError("Compatible verified TTM revenue unavailable")
        revenue_tax_definitions = _revenue_tax_definitions(package, ttm)
        if len(revenue_tax_definitions) > 1:
            raise ValueError("Compatible revenue tax definitions unavailable across TTM quarters")
        with localcontext() as ctx:
            ctx.prec = 60
            close = Decimal(quote["close"])
            equity = close * share_value
            multiple = equity / ttm.value
        # Fiscal quarter dates can vary around leap days. Use the fourth preceding
        # discrete quarter instead of a calendar-date guess.
        ends = sorted((end for end in _quarters(package, "Revenue", currency) if end < ttm.period_end), reverse=True)
        previous = _ttm_at(package, ends[3], "Revenue", currency) if len(ends) >= 4 else None
        growth = {"status": "unavailable", "reason": "Prior compatible four-quarter revenue unavailable"}
        if previous and previous.value > 0:
            previous_tax_definitions = _revenue_tax_definitions(package, previous)
            if (len(previous_tax_definitions) > 1 or
                    (revenue_tax_definitions and previous_tax_definitions
                     and revenue_tax_definitions != previous_tax_definitions)):
                growth = {"status": "unavailable", "reason": "Prior/current revenue tax definitions differ"}
            else:
                with localcontext() as ctx:
                    ctx.prec = 60
                    growth = {"status": "available", "percent": _number(100 * (ttm.value / previous.value - 1)),
                              "prior_revenue": _number(previous.value), "prior_revenue_fact": _lineage(package, previous)}
        gross = _ttm_at(package, ttm.period_end, "Gross Profit", currency, positive=False)
        margin = {"status": "unavailable", "reason": "Compatible same-period gross profit unavailable"}
        if gross and gross.period_start == ttm.period_start and gross.period_end == ttm.period_end:
            with localcontext() as ctx:
                ctx.prec = 60
                margin = {"status": "available", "percent": _number(100 * gross.value / ttm.value),
                          "gross_profit": _number(gross.value), "gross_profit_fact": _lineage(package, gross)}
        share_quality = cover["quality"] if cover else "reported_statement_date"
        conditional_assumptions = cover["pricing_assumptions"] if cover else []
        if include_quality and cover is None and share_date != ttm.period_end:
            share_quality = "lower_quality_dated_statement"
            conditional_assumptions = [
                f"Reported shares measured {share_date} held constant through the {ttm.period_end} revenue-period end "
                f"and {session} completed price; intervening capital changes are not resolved."
            ]
        result = {
            "status": "available", "reason": None, "ticker": ticker, "cik": package.cik,
            "as_of": str(package.as_of), "basis": "equity_value / trailing_revenue",
            "currency": currency, "price_session": str(session), "close": quote["close"], "price_unit": currency + "/share",
            "price_source_id": quote["source_id"], "price_source_hash": quote["content_hash"],
            "share_date": str(share_date), "shares": _number(share_value), "share_unit": "shares",
            "share_quality": share_quality,
            "conditional_assumptions": conditional_assumptions,
            "share_fact": share_lineage, "revenue": _number(ttm.value), "revenue_unit": currency,
            "revenue_definition": ("Reported revenue including assessed tax" if any(
                "RevenueFromContractWithCustomerIncludingAssessedTax" in source.locator
                for source in package.sources if source.source_id in ttm.source_ids
            ) else "Reported revenue; retained source tags define the accounting basis"),
            "revenue_fact": _lineage(package, ttm), "equity_value": _number(equity),
            "multiple": _number(multiple), "equity_value_unit": currency, "trailing_revenue_growth": growth, "gross_margin": margin,
        }
        if quote.get("price_fallback"):
            result["price_fallback"] = quote["price_fallback"]
        if not include_quality and cover is None:
            for field in ("share_quality", "conditional_assumptions", "revenue_definition"):
                result.pop(field, None)
        return result
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return _unavailable(str(exc))



def calculate_peer_share_diagnostic(package, issuer_identity, peer_cover_shares, *, ticker,
                                    as_of, completed_cutoff, revenue_currency, reason):
    """Retain usable dated source cells without manufacturing a missing quote."""
    from tradingagents.dataflows.vendors.peer_shares import replay_peer_cover_shares

    package = _validated_package(package)
    ticker = _identity(package, issuer_identity, ticker)
    if str(package.as_of) != as_of:
        raise ValueError("Peer diagnostic financial cutoff mismatch")
    cover = replay_peer_cover_shares(peer_cover_shares, package.cik, as_of, completed_cutoff)
    ttm = _latest_ttm(package, date.fromisoformat(completed_cutoff), revenue_currency)
    if ttm is None:
        raise ValueError("Compatible verified TTM revenue unavailable")
    if len(_revenue_tax_definitions(package, ttm)) > 1:
        raise ValueError("Compatible revenue tax definitions unavailable across TTM quarters")
    return {
        "status": "incomplete", "ticker": ticker, "cik": package.cik,
        "reason": "Completed same-session price unavailable: " + str(reason)[:300],
        "basis": "Dated peer source diagnostic; no valuation multiple",
        "share_quality": cover["quality"], "share_date": cover["share_date"],
        "shares": cover["shares"], "share_unit": "shares",
        "conditional_assumptions": cover["pricing_assumptions"],
        "share_fact": {"source_ids": [cover["source_id"]], "sources": [cover["source"]],
                       "components": cover["components"], "rights_quote": cover["rights_quote"]},
        "revenue": _number(ttm.value), "revenue_unit": revenue_currency,
        "revenue_fact": _lineage(package, ttm), "multiple": None, "price_session": None,
    }


def peer_range(peers: list[dict], *, include_quality=False) -> dict:
    """Separate reference distribution from a final validated peer snapshot."""
    if len(peers) > 5:
        return _unavailable("Peer reference exceeds five issuers")
    try:
        values = [Decimal(p["multiple"]) for p in peers if p.get("status") == "available" and p.get("basis") == "equity_value / trailing_revenue"]
        if any(not value.is_finite() or value <= 0 for value in values):
            raise ValueError("Invalid peer multiple")
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        return _unavailable(str(exc))
    if not values:
        return _unavailable("No usable peer multiples")
    lower = [p["ticker"] for p in peers if p.get("status") == "available"
             and p.get("share_quality") in {"lower_quality_dated_cover", "lower_quality_dated_statement"}]
    result = {"status": "available", "basis": "equity_value / trailing_revenue", "statistics": _stats(values)}
    if include_quality or lower:
        result.update(lower_quality_tickers=lower,
                      quality_label=("Reference range including conditional dated-share rows: " + ", ".join(lower)
                                     if lower else "Reference range from reported statement-date shares"))
    if include_quality and any("including assessed tax" in p.get("revenue_definition", "").lower() for p in peers):
        result["quality_label"] += "; reported revenue tax/accounting comparability is not established"
    return result


def render_own_history(record: dict) -> str:
    lines = ["### Own valuation history", ""]
    if record.get("status") != "available":
        return "\n".join(lines + ["Unavailable: " + escape(str(record.get("reason", "No history")))])
    s = record["statistics"]
    lines += [
        escape(record["label"]) + ".",
        f"Equity value / trailing revenue: low {s['low']}×, median {s['median']}×, high {s['high']}× across {s['count']} quarters.",
        f"Split-adjusted price basis through {escape(record['split_basis_date'])}; source {escape(record['split_source_id'])}.",
        "", "Quarter | Completed close | Share date | Revenue period | Multiple | Sources",
        "--- | --- | --- | --- | ---: | ---",
    ]
    for row in record["rows"][:24]:
        period = row["revenue_fact"]["period_start"] + " to " + row["revenue_fact"]["period_end"]
        sources = ", ".join(row["revenue_fact"]["source_ids"] + row["share_fact"]["source_ids"] + [row["price_source_id"]])
        cells = [row["quarter_end"], row["price_session"], row["share_date"], period, row["multiple"] + "×", sources]
        lines.append(" | ".join(escape(str(cell)).replace("|", "&#124;") for cell in cells))
    position = record.get("current_position") or {}
    if position.get("status") == "available":
        lines.extend(["", f"Today: {escape(position['multiple'])}×, {escape(position['relative_to_range'])} historical range ({position['quarters_at_or_below']} of {position['quarters']} quarters at or below)."] )
    return "\n".join(lines)


def render_peer_statistics(record: dict) -> str:
    if record.get("status") != "available":
        return "Unavailable: " + escape(str(record.get("reason", "No peer statistics")))
    growth, margin = record["trailing_revenue_growth"], record["gross_margin"]
    return (
        f"{escape(record['ticker'])}: equity value / trailing revenue {escape(record['multiple'])}× "
        f"at completed close {escape(record['price_session'])}; shares {escape(record['share_date'])}; "
        f"revenue {escape(record['revenue_fact']['period_start'])} to {escape(record['revenue_fact']['period_end'])}; "
        f"growth {escape(growth.get('percent', 'unavailable'))}%; "
        f"gross margin {escape(margin.get('percent', 'unavailable'))}%."
    )
