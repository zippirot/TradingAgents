"""Bounded issuer-event expectations and observed returns, never causal inference."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from zoneinfo import ZoneInfo

from tradingagents.agents.issuer_events import issuer_supplement
from tradingagents.agents.valuation_outlooks import _basis, _metric, _unit
from tradingagents.dataflows.disclosure_evidence import DisclosureClaim, validate_disclosure_claims
from tradingagents.dataflows.financial_evidence import EvidencePackage
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
from tradingagents.dataflows.vendors.yahoo.price_observation import (
    get_price_observation,
    validate_price_observation,
)

# Chosen before prices are requested. This is a partial business comparison,
# not a claim that leverage, margins or AI exposure are equivalent.
_PEERS = {
    "DOCN": ("AKAM", "Akamai offers cloud computing infrastructure; business mix and scale differ.")
}


def _empty(reason):
    return {
        "status": "unavailable",
        "reason": reason,
        "event": None,
        "guidance": {
            "status": "unavailable",
            "rows": [],
            "reason": "Compatible prior same-period guidance unavailable",
        },
        "consensus": {
            "status": "unavailable",
            "reason": "No typed, timestamped consensus source is configured; news/model assertions are not consensus",
        },
        "reaction": {
            "status": "unavailable",
            "reason": "Eligible event unavailable",
            "returns": {},
        },
    }


def _document_matches(doc, source):
    return (
        source is not None
        and doc.source_id == "sec-document-" + hashlib.sha256(doc.url.encode()).hexdigest()
        and (
            doc.filing.cik,
            doc.url,
            doc.content_hash,
            doc.filing.filed_date,
            doc.filing.accession,
            doc.filing.form,
        )
        == (
            source.cik,
            source.url,
            source.content_hash,
            source.filed_date,
            source.accession,
            source.form,
        )
    )


def _guidance(state, package, disclosures, event_day):
    source_map = {s.source_id: s for s in package.sources}
    eligible_ids = {
        row["source_id"]
        for row in issuer_supplement({}, disclosures, cik=package.cik, as_of=str(package.as_of))[
            "events"
        ]
    }
    duplicated = {
        doc.source_id
        for doc in disclosures.documents
        if sum(other.source_id == doc.source_id for other in disclosures.documents) > 1
    }
    documents = {
        doc.source_id: doc
        for doc in disclosures.documents
        if doc.source_id in eligible_ids
        and doc.source_id not in duplicated
        and _document_matches(doc, source_map.get(doc.source_id))
        and doc.filing.cik == package.cik
    }
    blocks = {
        (doc.source_id, b.locator): b.section + "\n" + b.text
        for doc in documents.values()
        for b in doc.blocks
        if not b.truncated and sum(other.locator == b.locator for other in doc.blocks) == 1
    }
    candidates = (state.get("disclosure_evidence") or {}).get("extraction", {}).get("claims", [])
    proposals = []
    for row in candidates[:32] if isinstance(candidates, list) else []:
        try:
            proposals.append(DisclosureClaim.model_validate(row))
        except (ValueError, TypeError):
            continue
    accepted = validate_disclosure_claims(proposals, blocks, packages=(disclosures,)).claims
    comparisons = []
    for claim in accepted:
        doc = documents.get(claim.source_id)
        if (
            doc is None
            or claim.kind != "guidance"
            or claim.comparator != "exact"
            or not 0 < (event_day - doc.filing.filed_date).days <= 400
        ):
            continue
        explicit = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", claim.period)
        if not explicit:
            continue  # No guessed fiscal calendar or period mapping.
        start, end = (date.fromisoformat(value) for value in explicit.groups())
        if not start <= end <= event_day:
            continue
        metric, basis = _metric(claim.metric), _basis(claim.quote)
        unit = _unit(claim, blocks[(claim.source_id, claim.locator)], metric) if metric else None
        if metric is None or basis is None or unit is None:
            continue
        actual = [
            fact
            for fact in package.facts
            if fact.origin == "reported"
            and fact.value is not None
            and (fact.metric, fact.period_start, fact.period_end, fact.unit, fact.basis)
            == (metric, start, end, unit[0], basis)
            and fact.source_ids
            and all(
                source_map[sid].filed_date <= event_day and source_map[sid].filed_date >= end
                for sid in fact.source_ids
            )
        ]
        if not actual or len({fact.value for fact in actual}) != 1:
            continue
        value = actual[0].value
        precision = (state.get("filing_fact_extraction") or {}).get("rounding_quantum_by_fact", {})
        try:
            quanta = [Decimal(str(precision.get(f.fact_id, "0"))) for f in actual]
            if any(not q.is_finite() or q < 0 for q in quanta):
                continue
        except (InvalidOperation, TypeError, ValueError, AttributeError):
            continue
        with localcontext() as context:
            context.prec = 60
            low = claim.value * unit[1]
            high = (claim.upper_value if claim.upper_value is not None else claim.value) * unit[1]
            above = value - high
            below = value - low
            actual_low = value - max(quanta) / 2
            actual_high = value + max(quanta) / 2
        position = (
            "above_range"
            if actual_low > high
            else "below_range"
            if actual_high < low
            else "within_range"
            if actual_low >= low and actual_high <= high
            else "rounding_overlap_unknown"
        )
        comparisons.append(
            {
                "metric": metric,
                "period_start": str(start),
                "period_end": str(end),
                "unit": unit[0],
                "basis": basis,
                "actual": str(value),
                "guidance_low": str(low),
                "guidance_high": str(high),
                "position": position,
                "actual_rounding_interval": [str(actual_low), str(actual_high)],
                "difference_from_lower": str(below),
                "difference_from_upper": str(above),
                "actual_fact_ids": [f.fact_id for f in actual],
                "actual_sources": [
                    source_map[sid].model_dump(mode="json")
                    for sid in sorted({sid for f in actual for sid in f.source_ids})
                ],
                "guidance_source": source_map[doc.source_id].model_dump(mode="json"),
                "guidance_claim": claim.model_dump(mode="json"),
            }
        )
    # Use the last pre-event guidance vintage, never silently choose conflicting ranges.
    grouped = {}
    for row in comparisons:
        key = (row["metric"], row["period_start"], row["period_end"], row["unit"], row["basis"])
        grouped.setdefault(key, []).append(row)
    rows = []
    for group in grouped.values():
        newest = max(r["guidance_source"]["filed_date"] for r in group)
        latest = [r for r in group if r["guidance_source"]["filed_date"] == newest]
        if len({(r["guidance_low"], r["guidance_high"], r["actual"]) for r in latest}) == 1:
            rows.append(latest[0])
    return {
        "status": "available" if rows else "unavailable",
        "rows": rows[:8],
        "reason": "Actuals compared with compatible pre-event guidance; no consensus inferred"
        if rows
        else "No source-validated pre-event guidance and actuals share explicit period, currency and accounting basis",
    }


def _configured_yahoo(config):
    chain = config.get("tool_vendors", {}).get("get_stock_data") or config.get(
        "data_vendors", {}
    ).get("core_stock_apis", "")
    return "yfinance" in {name.strip() for name in str(chain).split(",")}


def _reaction(ticker, as_of, event_day, config, saved_reaction=None):
    peer = _PEERS.get(ticker)
    symbols = list(dict.fromkeys([ticker, "SPY", *([peer[0]] if peer else [])]))
    result = {
        "status": "unavailable",
        "returns": {},
        "symbols_selected_before_fetch": symbols,
        "peer_rationale": peer[1] if peer else "No predetermined peer supported for this issuer",
        "window_policy": "Last common completed close before filing date to latest common completed close on/before cutoff, at most14 calendar days after filing; intraday event time unknown",
        "reason": "Configured dated-close provider unavailable",
    }
    if not _configured_yahoo(config):
        return result
    cutoff = min(as_of, event_day + timedelta(days=14))
    records = {}
    gaps = []
    for symbol in symbols:
        try:
            record = (
                get_price_observation(symbol, str(cutoff), str(event_day - timedelta(days=7)))
                if saved_reaction is None
                else saved_reaction.get("price_observations", {}).get(symbol, {})
            )
            if record.get("status") != "available":
                raise ValueError("Provider price unavailable")
            records[symbol] = validate_price_observation(record, symbol, str(cutoff))
        except Exception:
            gaps.append(f"{symbol}: price unavailable")
    result["coverage_gaps"] = gaps
    result["price_observations"] = records
    if ticker not in records or "SPY" not in records:
        result["reason"] = (
            "Stock or broad benchmark price unavailable; aligned comparison not computed"
        )
        return result
    bars = {}
    for symbol, record in records.items():
        if record["currency"] != "USD":
            result["reason"] = "Comparison currency unsupported or mismatched"
            return result
        zone = ZoneInfo(record["exchange_timezone"])
        rows = {}
        for row in record["raw_source"]["bars"]:
            session = str(datetime.fromisoformat(row["timestamp"]).astimezone(zone).date())
            if session <= record["session_date"]:
                rows[session] = Decimal(row["close"])
        bars[symbol] = rows
    common = set.intersection(*(set(rows) for rows in bars.values()))
    before = [day for day in common if day < str(event_day)]
    after = [day for day in common if str(event_day) <= day <= str(cutoff)]
    if not before or not after:
        result["reason"] = (
            "No common completed before/after sessions; unmatched dates cannot form a comparison"
        )
        return result
    start, end = max(before), max(after)
    if (event_day - date.fromisoformat(start)).days > 7 or (
        cutoff - date.fromisoformat(end)
    ).days > 7:
        result["reason"] = "Aligned event-window prices stale"
        return result
    for record in records.values():
        if any(start < split["session_date"] <= str(cutoff) for split in record["splits"]):
            result["reason"] = (
                "Split-adjustment basis incompatible with event window; no reconstructed return"
            )
            return result
    for symbol, rows in bars.items():
        with localcontext() as context:
            context.prec = 50
            percent = (rows[end] / rows[start] - 1) * 100
        result["returns"][symbol] = {
            "percent": str(percent),
            "start_close": str(rows[start]),
            "end_close": str(rows[end]),
        }
    result.update(
        status="available" if not gaps else "partial",
        reason="Observed aligned price changes, not causal attribution",
        start_session=start,
        end_session=end,
    )
    return result


def prepare_event_comparison(state, config, *, saved_record=None):
    """Canonical gate caller only; renderer never retrieves or repairs sources."""
    result = _empty("Eligible verified earnings event unavailable")
    try:
        if (state.get("evidence_quality") or {}).get("status") not in {"sufficient", "limited"}:
            return result
        package = EvidencePackage.model_validate(state.get("financial_evidence"))
        disclosures = DisclosurePackage.model_validate(state.get("filing_evidence"))
        ticker = normalize_symbol(state["company_of_interest"])
        as_of = date.fromisoformat(state["trade_date"])
        if package.as_of != as_of or disclosures.as_of != as_of or package.cik != disclosures.cik:
            return result
        binding = {
            "ticker": ticker,
            "cik": package.cik,
            "as_of": str(as_of),
            "source": "SEC issuer map",
        }
        if state.get("issuer_identity") != binding:
            return _empty("Issuer binding unavailable or mismatched; event comparison not computed")
        supplement = issuer_supplement(
            state.get("news_coverage", {}), disclosures, cik=package.cik, as_of=str(as_of)
        )
        eligible = [
            event for event in supplement["events"] if "2.02" in re.split(r"[,\s]+", event["items"])
        ]
        if not eligible:
            return result
        event = max(eligible, key=lambda item: (item["known_at"], item["url"]))
        event_day = date.fromisoformat(event["known_at"])
        result.update(
            status="available",
            retrieval_policy={"configured_yahoo": _configured_yahoo(config)},
            issuer_identity=binding,
            reason="Source-backed event comparison; individual coverage limits retained",
            event={**event, "date_basis": "SEC filing date; precise earnings-release time unknown"},
        )
        result["guidance"] = _guidance(state, package, disclosures, event_day)
        result["reaction"] = _reaction(
            ticker,
            as_of,
            event_day,
            config,
            None if saved_record is None else (saved_record.get("reaction") or {}),
        )
    except (ValueError, TypeError, KeyError) as exc:
        return _empty(f"Event comparison unavailable ({type(exc).__name__})")
    return result


def replay_event_comparison(state, record):
    """No-network replay: recalculate every projection, reject saved tampering."""
    if not isinstance(record, dict):
        raise ValueError("Event comparison record missing")
    policy = record.get("retrieval_policy", {})
    if record.get("status") == "available" and (
        set(policy) != {"configured_yahoo"} or type(policy["configured_yahoo"]) is not bool
    ):
        raise ValueError("Event comparison retrieval policy missing or invalid")
    config = {
        "data_vendors": {"core_stock_apis": "yfinance" if policy.get("configured_yahoo") else ""}
    }
    rebuilt = prepare_event_comparison(state, config, saved_record=record)
    if rebuilt != record:
        raise ValueError("Event comparison does not match canonical sources and retained prices")
    return rebuilt


def render_event_comparison(record):
    """Pure compact report/decision context; no retrieval and no causal claim."""
    if not isinstance(record, dict) or record.get("status") != "available":
        return "Event comparison unavailable; no surprise or reaction inferred."
    event = record["event"]
    guidance = record["guidance"]
    reaction = record["reaction"]
    lines = [
        f"Event comparison — SEC filing date {event['known_at']}; precise event time unknown. Source: {event['url']}"
    ]
    for row in guidance["rows"]:
        lines.append(
            f"- {row['metric']} ({row['basis']}, {row['period_start']} to {row['period_end']}): actual {row['actual']} {row['unit']}; prior guidance {row['guidance_low']}–{row['guidance_high']} {row['unit']}; {row['position'].replace('_', ' ')}. Guidance known {row['guidance_source']['filed_date']}."
        )
    if not guidance["rows"]:
        lines.append("Prior guidance comparison unavailable: " + guidance["reason"] + ".")
    lines.append("Consensus unavailable: " + record["consensus"]["reason"] + ".")
    if reaction["status"] in {"available", "partial"}:
        lines.append(
            f"Observed price window {reaction['start_session']} to {reaction['end_session']} (completed common sessions; not causal attribution):"
        )
        lines.extend(
            f"- {symbol}: {Decimal(item['percent']):+.2f}%."
            for symbol, item in reaction["returns"].items()
        )
    else:
        lines.append("Market-window comparison unavailable: " + reaction["reason"] + ".")
    lines.append("Peers selected before returns: " + reaction.get("peer_rationale", "unavailable"))
    lines.extend("Coverage: " + gap for gap in reaction.get("coverage_gaps", []))
    return "\n".join(lines)
