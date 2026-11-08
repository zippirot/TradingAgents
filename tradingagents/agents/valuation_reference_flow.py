"""Acquire and retain source reference points around the analyst boundary."""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from tradingagents.dataflows.symbols import normalize_symbol

MAX_PEERS = 5
MAX_PEER_BLOCK = 4096
FENCE = chr(96) * 3


def _peer_rows(value, subject, *, pins=False):
    if not isinstance(value, list) or len(value) > MAX_PEERS:
        raise ValueError("Peer set must be a list of at most five tickers")
    rows, seen = [], set()
    for item in value:
        if pins and isinstance(item, str):
            item = {"ticker": item, "reason": "User-pinned comparison"}
        if not isinstance(item, dict) or set(item) != {"ticker", "reason"}:
            raise ValueError("Each peer needs only ticker and reason")
        ticker, reason = item["ticker"], item["reason"]
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,14}", ticker):
            raise ValueError("Peer ticker is invalid")
        ticker = normalize_symbol(ticker)
        if ticker == normalize_symbol(subject):
            raise ValueError("The subject cannot be its own peer")
        if ticker in seen:
            raise ValueError("Peer tickers must be unique")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
            raise ValueError("Peer reason must be nonempty and at most 300 characters")
        seen.add(ticker)
        rows.append({"ticker": ticker, "reason": reason.strip()})
    return rows


def parse_peer_proposal(report, subject):
    """Parse one bounded, untrusted model proposal; this never verifies a peer."""
    try:
        if not isinstance(report, str):
            raise ValueError("Fundamentals report is unavailable")
        matches = re.findall(FENCE + r"peers\s*\n(.*?)\n" + FENCE, report, re.S)
        if len(matches) != 1 or len(matches[0]) > MAX_PEER_BLOCK:
            raise ValueError("Exactly one bounded peers block is required")
        rows = _peer_rows(json.loads(matches[0]), subject)
        return {"status": "available", "reason": None, "peers": rows}
    except (ValueError, TypeError) as exc:
        return {"status": "unavailable", "reason": str(exc), "peers": []}


def _pinned_rows(value, subject):
    if not isinstance(value, list) or len(value) > MAX_PEERS:
        raise ValueError("Pinned peer set must be a list of at most five tickers")
    rows, rejected, seen = [], [], set()
    for index, item in enumerate(value, 1):
        try:
            row = _peer_rows([item], subject, pins=True)[0]
            if row["ticker"] in seen:
                raise ValueError("Duplicate pinned peer ticker")
            seen.add(row["ticker"])
            rows.append(row)
        except (ValueError, TypeError) as exc:
            ticker = item.get("ticker") if isinstance(item, dict) else item
            rejected.append({"ticker": str(ticker)[:24] if isinstance(ticker, str) else f"pin entry {index}",
                             "reason": str(exc), "selection_reason": "User-pinned comparison"})
    return rows, rejected


def peer_selection_fingerprint(config):
    """Content, including an environment-selected pin file, changes checkpoint identity."""
    import hashlib

    path = config.get("valuation_peers_file") or os.environ.get("TRADINGAGENTS_PEERS_FILE")
    if not path:
        return "none"
    try:
        with Path(path).expanduser().open("rb") as handle:
            content = handle.read(32769)
        return hashlib.sha256(content).hexdigest()
    except OSError:
        return "unreadable"


def default_peer_selection(state, config):
    """Read user pins first, otherwise the latest eligible publication snapshot."""
    from tradingagents.memory.publication import list_records, load_evidence

    subject = normalize_symbol(state["company_of_interest"])
    pinned_file = config.get("valuation_peers_file") or os.environ.get("TRADINGAGENTS_PEERS_FILE")
    if pinned_file:
        try:
            with Path(pinned_file).expanduser().open("rb") as handle:
                data = handle.read(32769)
            if len(data) > 32768:
                raise ValueError("Peers file exceeds 32 KiB")
            pins = json.loads(data)
            if not isinstance(pins, dict):
                raise ValueError("Peers file must map subject tickers to lists")
            normalized = {}
            for key, value in pins.items():
                symbol = normalize_symbol(key)
                if symbol in normalized:
                    raise ValueError("Duplicate subject ticker in peers file")
                normalized[symbol] = value
            pins = normalized
            if subject in pins:
                peers, rejected = _pinned_rows(pins[subject], subject)
                return {"kind": "user-pinned", "status": "available", "reason": None,
                        "peers": peers, "rejected": rejected}
        except (OSError, ValueError, TypeError) as exc:
            return {"kind": "user-pinned", "status": "unavailable", "reason": str(exc), "peers": []}
    empty = {"kind": "previous", "status": "available", "peers": [],
             "reason": "No prior published peer set at this cutoff"}
    if not config.get("results_dir"):
        return empty
    try:
        cutoff = state.get("market_observation_cutoff") or (state.get("analysis_clock") or {}).get("cutoff_utc")
        cutoff = datetime.fromisoformat(str(cutoff).replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            raise ValueError("Peer publication cutoff needs a timezone")
        eligible = []
        for record in list_records(config, subject):
            stamp = record.get("published_at") or record.get("imported_at")
            if not stamp or record.get("decision_id") == state.get("run_id"):
                continue
            published = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if published.tzinfo is None:
                raise ValueError("Peer publication time is missing a timezone")
            if published <= cutoff:
                eligible.append((published, record["sequence"], record))
        if not eligible:
            return empty
        record = max(eligible, key=lambda row: row[:2])[2]
        snapshot = load_evidence(config, record)
        rows = ((snapshot.get("valuation_reference") or {}).get("peers") or {}).get("accepted") or []
        values = [{"ticker": row["ticker"], "reason": row["reason"]} for row in rows]
        return {**empty, "reason": None, "peers": _peer_rows(values, subject),
                "publication_id": record["decision_id"]}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"kind": "previous", "status": "unavailable", "reason": str(exc), "peers": []}


MAX_REFERENCE_BRIEF = 18000


def _unavailable(reason):
    return {"status": "unavailable", "reason": str(reason)[:400]}


def _scope(state):
    from datetime import UTC

    cutoff = state.get("market_observation_cutoff") or (state.get("analysis_clock") or {}).get("cutoff_utc")
    if cutoff:
        parsed = datetime.fromisoformat(str(cutoff).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Reference observation cutoff needs a timezone")
        cutoff = parsed.astimezone(UTC).isoformat()
    return {
        "ticker": normalize_symbol(state["company_of_interest"]),
        "as_of": str(state["trade_date"]),
        "asset_type": state.get("asset_type", "stock"),
        "observation_cutoff": cutoff,
    }


def _package(state):
    from tradingagents.dataflows.financial_evidence import EvidencePackage, add_period_calculations

    package = add_period_calculations(EvidencePackage.model_validate(state["financial_evidence"]))
    scope = _scope(state)
    if str(package.as_of) != scope["as_of"] or state.get("issuer_identity") != {
        "ticker": scope["ticker"], "as_of": scope["as_of"], "cik": package.cik, "source": "SEC issuer map"
    }:
        raise ValueError("Reference financial package issuer or cutoff mismatch")
    return package


def _quarters(package):
    from datetime import timedelta

    revenue_ends = {f.period_end for f in package.facts if f.metric == "Revenue"
                    and f.period_start is not None and f.value is not None
                    and 60 <= (f.period_end - f.period_start).days + 1 <= 115}
    # Request the revenue quarter even when shares are missing. Its unavailable
    # reason must survive into the reference section instead of silently vanishing.
    ends = {day for day in revenue_ends if day >= package.as_of - timedelta(days=1830)}
    return [str(day) for day in sorted(ends)[-24:]]


def _subject(state):
    from tradingagents.agents.valuation_reference import calculate_peer_statistics
    from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation

    try:
        scope = _scope(state)
        saved = state.get("price_observation") or {}
        if saved.get("status") != "available":
            raise ValueError(saved.get("reason") or "Canonical completed close unavailable")
        quote = validate_price_observation(saved, scope["ticker"], scope["as_of"])
        return calculate_peer_statistics(_package(state), state["issuer_identity"], quote,
                                         ticker=scope["ticker"], completed_cutoff=quote["session_date"])
    except (ValueError, KeyError, TypeError) as exc:
        return _unavailable(exc)


def _canonical_quote(state):
    from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation

    quote = state.get("price_observation") or {}
    if quote.get("status") != "available":
        raise ValueError(quote.get("reason") or "Canonical completed close unavailable")
    scope = _scope(state)
    return validate_price_observation(quote, scope["ticker"], scope["as_of"])


def _fetch_peer(ticker, state):
    from tradingagents.dataflows.errors import VendorError
    from tradingagents.dataflows.financial_evidence import add_period_calculations
    from tradingagents.dataflows.vendors import sec_edgar
    from tradingagents.dataflows.vendors.yahoo.price_observation import (
        completed_price_scope,
        get_price_observation,
    )

    try:
        scope, subject = _scope(state), _canonical_quote(state)
        cik = sec_edgar.cik_for(ticker)
        if not cik:
            raise ValueError("Peer is not identified in the SEC issuer map")
        if cik == (state.get("issuer_identity") or {}).get("cik"):
            raise ValueError("Peer resolves to the subject issuer under another ticker")
        as_of = date.fromisoformat(scope["as_of"])
        try:
            period_floor = as_of.replace(year=as_of.year - 3)
        except ValueError:  # February 29 has no anniversary in a non-leap year.
            period_floor = as_of.replace(year=as_of.year - 3, day=28)
        package = add_period_calculations(sec_edgar.get_financial_evidence(
            ticker, scope["as_of"], peer_revenue_definitions=True, period_floor=period_floor))
        if package.cik != cik or str(package.as_of) != scope["as_of"]:
            raise ValueError("Peer financial issuer or cutoff mismatch")
        dates = [f.period_end for f in package.facts if f.metric == "Common Shares Outstanding"
                 and f.period_start is None and f.value is not None and f.value > 0
                 and str(f.period_end) <= subject["session_date"]]
        cover = None
        if not dates:
            from tradingagents.dataflows.vendors.peer_shares import (
                get_peer_cover_shares,
                replay_peer_cover_shares,
            )
            cover = get_peer_cover_shares(cik, scope["as_of"], subject["session_date"])
            selected = replay_peer_cover_shares(cover, cik, scope["as_of"], subject["session_date"])
            dates = [date.fromisoformat(selected["share_date"])]
        with completed_price_scope(state):
            quote = get_price_observation(ticker, scope["as_of"], max(dates))
        return {"status": "available", "package": package.model_dump(mode="json"),
                "issuer_identity": {"ticker": ticker, "cik": cik, "as_of": scope["as_of"], "source": "SEC issuer map"},
                "price_observation": quote, "peer_cover_shares": cover}
    except (VendorError, ValueError, KeyError, TypeError) as exc:
        return _unavailable(exc)


def _peer_set(selection, state, sources, *, include_quality=False, minimum_range_peers=1):
    from tradingagents.agents.valuation_reference import calculate_peer_statistics, peer_range
    from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation

    accepted, rejected, incomplete = [], list(selection.get("rejected") or []), []
    dated_price_diagnostics = []
    for row in _peer_rows(selection.get("peers", []), state["company_of_interest"]):
        ticker, raw = row["ticker"], sources.get(row["ticker"]) or {}
        try:
            if raw.get("status") != "available":
                raise ValueError(raw.get("reason") or "Retained peer sources unavailable")
            subject = _canonical_quote(state)
            if raw["issuer_identity"].get("cik") == (state.get("issuer_identity") or {}).get("cik"):
                raise ValueError("Peer resolves to the subject issuer under another ticker")
            quote = validate_price_observation(raw["price_observation"], ticker, state["trade_date"])
            if quote["currency"] != subject["currency"]:
                raise ValueError("Peer currency differs from the subject completed price currency")
            if (include_quality and quote.get("price_fallback")
                    and quote["session_date"] < subject["session_date"]):
                diagnostic = calculate_peer_statistics(
                    raw["package"], raw["issuer_identity"], quote, ticker=ticker,
                    completed_cutoff=quote["session_date"], peer_cover_shares=raw.get("peer_cover_shares"),
                    include_quality=True)
                if diagnostic["status"] != "available":
                    raise ValueError(diagnostic["reason"])
                dated_price_diagnostics.append({**row, "statistics": diagnostic})
                continue
            statistics = calculate_peer_statistics(raw["package"], raw["issuer_identity"], quote,
                                                    ticker=ticker, completed_cutoff=subject["session_date"],
                                                    peer_cover_shares=raw.get("peer_cover_shares"), include_quality=include_quality)
            if statistics["status"] != "available":
                raise ValueError(statistics["reason"])
            accepted.append({**row, "statistics": statistics})
        except (ValueError, KeyError, TypeError) as exc:
            failed_quote = raw.get("price_observation") or {}
            if (include_quality and raw.get("status") == "available" and raw.get("peer_cover_shares")
                    and failed_quote.get("status") == "unavailable"
                    and failed_quote.get("ticker") == ticker and failed_quote.get("as_of") == state["trade_date"]):
                from tradingagents.agents.valuation_reference import calculate_peer_share_diagnostic
                try:
                    subject = _canonical_quote(state)
                    if raw["issuer_identity"].get("cik") == (state.get("issuer_identity") or {}).get("cik"):
                        raise ValueError("Peer resolves to the subject issuer")
                    diagnostic = calculate_peer_share_diagnostic(
                        raw["package"], raw["issuer_identity"], raw["peer_cover_shares"], ticker=ticker,
                        as_of=state["trade_date"], completed_cutoff=subject["session_date"],
                        revenue_currency=subject["currency"], reason=failed_quote.get("reason") or str(exc))
                    incomplete.append({**row, "statistics": diagnostic})
                    continue
                except (ValueError, KeyError, TypeError):
                    pass
            rejected.append({**row, "reason": str(exc)[:400], "selection_reason": row["reason"]})
    result = {"kind": "user-pinned" if selection["kind"] == "user-pinned" else "model-selected",
            "status": selection["status"], "reason": selection.get("reason"),
            "requested": selection.get("peers", []), "accepted": accepted, "rejected": rejected,
            "range": peer_range([row["statistics"] for row in accepted], include_quality=include_quality),
            "qualification": "Data checks do not establish business comparability; selection reasons are unverified"}
    if minimum_range_peers > 1 and len(accepted) < minimum_range_peers:
        result["range"] = _unavailable("Fewer than three accepted same-session peers; individual multiples only")
    if include_quality:
        result["incomplete"] = incomplete
    if dated_price_diagnostics:
        result["dated_price_diagnostics"] = dated_price_diagnostics
    return result


def _history(state, raw, subject):
    from tradingagents.agents.valuation_reference import calculate_own_history
    from tradingagents.dataflows.vendors.yahoo.reference_history import replay_reference_history

    if raw.get("status") != "available":
        return _unavailable(raw.get("reason") or "Historical price source unavailable")
    package = _package(state)
    prices, splits = replay_reference_history(raw, state["company_of_interest"], state["trade_date"], _quarters(package))
    if raw.get("observation_cutoff") != _scope(state)["observation_cutoff"]:
        raise ValueError("Historical price cutoff differs from this run")
    result = calculate_own_history(package, state["issuer_identity"], prices, splits,
                                   ticker=state["company_of_interest"],
                                   current_multiple=subject.get("multiple") if subject["status"] == "available" else None)
    priced = {row["quarter_end"] for row in prices}
    result["excluded"] = [*result.get("excluded", []), *[
        day + ": completed quarter-end close unavailable within seven days"
        for day in _quarters(package) if day not in priced]]
    return result


def _assemble(state, record):
    """Recompute projections from retained source inputs; no network or model."""
    from copy import deepcopy

    result = deepcopy(record)
    if result.get("status") == "not_applicable":
        return result
    result["subject"] = _subject(state)
    result["own_history"] = _history(state, result["raw_sources"]["history"], result["subject"])
    result["default_peers"] = _peer_set(result["default_selection"], state, result["raw_sources"]["peers"],
                                        include_quality=result.get("schema_version", 1) >= 2,
                                        minimum_range_peers=3 if result.get("schema_version", 1) >= 3 else 1)
    result["peers"] = _peer_set(result["selection"], state, result["raw_sources"]["peers"],
                                        include_quality=result.get("schema_version", 1) >= 2,
                                        minimum_range_peers=3 if result.get("schema_version", 1) >= 3 else 1)
    old = [row["ticker"] for row in result["default_peers"]["requested"]]
    new = [row["ticker"] for row in result["peers"]["requested"]]
    result["changes"] = {"added": [t for t in new if t not in old], "removed": [t for t in old if t not in new]}
    return result


def replay_valuation_reference(state, record):
    """Reject altered scope, derived values or flattened historical projections."""
    if not isinstance(record, dict) or record.get("schema_version") not in {1, 2, 3} or record.get("scope") != _scope(state):
        raise ValueError("Retained valuation reference differs from run scope")
    try:
        replay = _assemble(state, record)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Retained valuation reference sources invalid: " + str(exc)) from exc
    if replay != record:
        raise ValueError("Retained valuation reference projection differs from canonical sources")
    return replay


def acquire_reference_inputs(state, config):
    """Before analysts: retain own history, default peers and labeled expectations."""
    from tradingagents.dataflows.vendors.yahoo.expectations import (
        VendorExpectations,
        get_vendor_expectations,
    )
    from tradingagents.dataflows.vendors.yahoo.reference_history import get_reference_history

    scope = _scope(state)
    acquisition = state.get("evidence_acquisition") or {}
    if scope["asset_type"] != "stock" or acquisition.get("status") != "ready":
        record = {"schema_version": 1, "scope": scope, "status": "not_applicable", "phase": "preanalyst",
                  "reason": acquisition.get("reason") or "Verified US stock financial inputs unavailable"}
        return {"valuation_reference": record, "valuation_reference_brief": render_valuation_reference(record)}
    chain = config.get("tool_vendors", {}).get("get_stock_data") or config.get("data_vendors", {}).get("core_stock_apis", "")
    configured = "yfinance" in {item.strip() for item in str(chain).split(",")}
    history = _unavailable("Configured historical close provider unavailable")
    try:
        ends = _quarters(_package(state))
        if configured and len(ends) >= 4:
            history = get_reference_history(scope["ticker"], scope["as_of"], ends,
                                            observation_cutoff=scope["observation_cutoff"])
        elif configured:
            history = _unavailable("Fewer than four reported revenue quarters available")
    except (ValueError, TypeError, KeyError) as exc:
        history = _unavailable(exc)
    selection = default_peer_selection(state, config)
    sources = {row["ticker"]: _fetch_peer(row["ticker"], state) if configured else
               _unavailable("Configured completed price provider unavailable") for row in selection["peers"]}
    consensus = (get_vendor_expectations(scope["ticker"], scope["as_of"],
                 analysis_timezone=(state.get("analysis_clock") or {}).get("timezone") or
                 config.get("analysis_timezone", "America/Denver")) if configured else
                 VendorExpectations(status="unavailable", ticker=scope["ticker"], requested_as_of=scope["as_of"],
                                    reason="Configured Yahoo expectations provider unavailable"))
    record = {"schema_version": 3, "scope": scope, "status": "available", "phase": "preanalyst",
              "default_selection": selection, "selection": selection, "configured_yahoo": configured,
              "raw_sources": {"history": history, "peers": sources}}
    record = _assemble(state, record)
    update = {"valuation_reference": record, "vendor_expectations": consensus.model_dump(mode="json")}
    update["valuation_reference_brief"] = shared_valuation_reference({**state, **update})
    return update


def finalize_peer_reference(state, config):
    """After fundamentals: validate a proposal; authoritative pins remain unchanged."""
    from copy import deepcopy

    saved = state.get("valuation_reference")
    if not isinstance(saved, dict):
        return {}
    record = deepcopy(replay_valuation_reference(state, saved))
    if record.get("status") == "not_applicable" or record.get("phase") == "final":
        return {}
    report = (state.get("financial_claim_validation") or {}).get("raw_report") or state.get("fundamentals_report", "")
    proposal = parse_peer_proposal(report, state["company_of_interest"])
    record["proposal"] = proposal
    if record["selection"]["kind"] != "user-pinned" and proposal["status"] == "available":
        record["selection"] = {"kind": "model-selected", **proposal}
        for row in proposal["peers"]:
            if row["ticker"] not in record["raw_sources"]["peers"]:
                record["raw_sources"]["peers"][row["ticker"]] = (_fetch_peer(row["ticker"], state) if record["configured_yahoo"] else
                    _unavailable("Configured completed price provider unavailable"))
    record["phase"] = "final"
    record = _assemble(state, record)
    update = {"valuation_reference": record}
    update["valuation_reference_brief"] = shared_valuation_reference({**state, **update})
    return update


def _cell(value):
    from html import escape
    return escape(str(value)).replace("|", "&#124;").replace("\n", " ")


def _number(value):
    from tradingagents.agents.valuation_comparison import display_number
    return display_number(value) if value is not None else "unavailable"


def render_valuation_reference(record):
    """Compact, independently available reference rows; full lineage stays retained."""
    lines = ["#### Valuation reference points", ""]
    if record.get("status") in {"not_applicable", "unavailable"}:
        return "\n".join(lines + ["Unavailable: " + _cell(record.get("reason"))])
    subject, history = record["subject"], record["own_history"]
    if subject["status"] == "available":
        lines.append(f"Current equity value / trailing revenue: {_number(subject['multiple'])}×; "
                     f"completed close {_cell(subject['price_session'])}; shares measured {_cell(subject['share_date'])}; "
                     f"revenue {_cell(subject['revenue_fact']['period_start'])} to {_cell(subject['revenue_fact']['period_end'])}.")
    else:
        lines.append("Current equity value / trailing revenue unavailable: " + _cell(subject["reason"]))
    if history["status"] == "available":
        stats = history["statistics"]
        lines += ["", "Own history — equity value / trailing revenue: "
                  f"low {_number(stats['low'])}×, median {_number(stats['median'])}×, high {_number(stats['high'])}× "
                  f"across {stats['count']} quarters.",
                  _cell(history["label"]) + ".",
                  "Price and shares reconciled to split basis " + _cell(history["split_basis_date"]) + ".",
                  "Quarter / completed session | Share date | TTM revenue period | Multiple | Filing dates",
                  "--- | --- | --- | ---: | ---"]
        for row in history["rows"]:
            filed = sorted({s["filed_date"] for key in ("share_fact", "revenue_fact") for s in row[key]["sources"]})
            lines.append(f"{row['quarter_end']} / {row['price_session']} | {row['share_date']} | "
                         f"{row['revenue_fact']['period_start']} to {row['revenue_fact']['period_end']} | "
                         f"{_number(row['multiple'])}× | {', '.join(filed)}")
        lines.append("")
        position = history.get("current_position", {})
        if position.get("status") == "available":
            lines.append(f"Today is {_cell(position['relative_to_range'])} the history range; "
                         f"{position['quarters_at_or_below']} of {position['quarters']} quarters at or below today's multiple.")
        lines.append("History source_id " + _cell(history["split_source_id"]) + "; complete fact and source lineage retained.")
    else:
        lines.append("Own history unavailable: " + _cell(history["reason"]))
    for reason in history.get("excluded", [])[:24]:
        lines.append("Excluded " + _cell(reason) + ".")
    peers = record["peers"]
    lines += ["", "Peers — " + peers["kind"] + ". " + peers["qualification"] + "."]
    if record["phase"] == "preanalyst":
        lines.append("Default peer statistics available before analysts; new proposed peers apply from the debate onward.")
    elif not record["default_peers"]["accepted"]:
        lines.append("No validated default peers before analysts; this run's peers apply from the debate onward.")
    if peers.get("reason"):
        lines.append(_cell(peers["reason"]))
    for row in peers["accepted"]:
        stats = row["statistics"]
        growth, margin = stats["trailing_revenue_growth"], stats["gross_margin"]
        growth_text = _number(growth.get("percent")) + ("%" if growth.get("percent") is not None else "")
        margin_text = _number(margin.get("percent")) + ("%" if margin.get("percent") is not None else "")
        lines.append(f"- {_cell(row['ticker'])}: {_cell(row['reason'])}. Equity value / trailing revenue "
                     f"{_number(stats['multiple'])}×; growth {growth_text}; "
                     f"gross margin {margin_text}; completed close {stats['price_session']}; "
                     f"share date {stats['share_date']}; revenue {stats['revenue_fact']['period_start']} to {stats['revenue_fact']['period_end']}.")
        lines.append("  Revenue definition: " + _cell(stats.get("revenue_definition", "See retained source tags")) + ".")
        for gap in stats.get("evidence_gaps", []):
            lines.append("  Evidence gap: " + _cell(gap) + ".")
        if stats.get("share_quality") in {"lower_quality_dated_cover", "lower_quality_dated_statement"}:
            share_label = ("dated cover shares" if stats["share_quality"] == "lower_quality_dated_cover"
                           else "statement shares dated differently from the revenue-period end")
            lines.append("  Lower-quality conditional row: " + share_label + ", not same-date capitalization. " +
                         _cell("; ".join(stats["conditional_assumptions"])))
        if stats.get("price_fallback"):
            fallback = stats["price_fallback"]
            lines.append("  Price fallback: " + _cell(fallback["reason"]) + "; latest completed session " +
                         _cell(fallback["latest_completed_session_date"]) + ".")
        for cell in (growth, margin):
            if cell["status"] != "available":
                lines.append("  Unavailable: " + _cell(cell["reason"]))
        sources = {s["source_id"]: s for key in ("share_fact", "revenue_fact") for s in stats[key]["sources"]}
        lines.extend("  source_id " + _cell(s["source_id"]) + "; filed " + _cell(s["filed_date"]) + "; " + _cell(s["url"])
                     for s in sources.values())
    for row in peers.get("dated_price_diagnostics", []):
        stats = row["statistics"]
        fallback = stats["price_fallback"]
        lines.append(f"- {_cell(row['ticker'])}: dated price diagnostic; {_cell(row['reason'])}. "
                     f"Equity value / trailing revenue {_number(stats['multiple'])}×; completed close "
                     f"{_cell(stats['price_session'])}; shares measured {_cell(stats['share_date'])}; "
                     f"revenue {_cell(stats['revenue_fact']['period_start'])} to {_cell(stats['revenue_fact']['period_end'])}. "
                     "Different price session; excluded from the same-session peer range.")
        lines.append("  Revenue definition: " + _cell(stats["revenue_definition"]) + ".")
        lines.append("  Price fallback: " + _cell(fallback["reason"]) + "; latest completed session " +
                     _cell(fallback["latest_completed_session_date"]) + ".")
        lines.append("  " + _cell("; ".join(stats.get("conditional_assumptions", []))))
        sources = {s["source_id"]: s for key in ("share_fact", "revenue_fact") for s in stats[key]["sources"]}
        lines.extend("  source_id " + _cell(s["source_id"]) + "; filed " + _cell(s["filed_date"]) +
                     "; " + _cell(s["url"]) for s in sources.values())
    for row in peers.get("incomplete", []):
        stats = row["statistics"]
        lines.append(f"- {_cell(row['ticker'])}: lower-quality incomplete peer row. " +
                     _cell(row["reason"]) + f". Shares {_number(stats['shares'])}, measured {stats['share_date']}; " +
                     "A valid same-session completed price is unavailable. Multiple unavailable; excluded from the peer range.")
        lines.append("  " + _cell("; ".join(stats["conditional_assumptions"])))
        for source in stats["share_fact"]["sources"]:
            lines.append("  source_id " + _cell(source["source_id"]) + "; filed " +
                         _cell(source["filed_date"]) + "; " + _cell(source["url"]))
    if not peers["accepted"]:
        lines.append("Peer table unavailable: no peers passed the source checks.")
    for row in peers["rejected"]:
        lines.append("- Excluded " + _cell(row["ticker"]) + ": " + _cell(row["reason"]))
    lines.append("")
    if peers["range"]["status"] == "available":
        stats = peers["range"]["statistics"]
        lines.append(f"Separate peer range: {_number(stats['low'])}× / {_number(stats['median'])}× / {_number(stats['high'])}× "
                     f"(low / median / high; {stats['count']} peers; equity value / trailing revenue).")
        lines.append(_cell(peers["range"].get("quality_label", "Retained reference range")) + ".")
    elif record.get("schema_version", 1) >= 3 and peers["accepted"]:
        lines.append("Fewer than three accepted same-session peers; shown individually, without a pooled reference range.")
    if record["changes"]["added"] or record["changes"]["removed"]:
        lines.append("Changes from default: added " + _cell(", ".join(record["changes"]["added"]) or "none") +
                     "; removed " + _cell(", ".join(record["changes"]["removed"]) or "none") + ". Earlier default statistics remain retained.")
    if (record.get("proposal") or {}).get("status") == "unavailable":
        lines.append("Peer proposal unavailable; default preserved: " + _cell(record["proposal"]["reason"]))
    lines.append("Reference ranges describe observed valuations; they do not establish fair value.")
    return "\n".join(lines)


def render_vendor_expectations(record):
    lines = ["#### Management guidance versus vendor consensus, unverified", ""]
    if not isinstance(record, dict) or record.get("status") == "unavailable":
        return "\n".join(lines + ["Consensus unavailable: " + _cell((record or {}).get("reason") or "No retained vendor expectations")])
    lines += ["Retrieved " + _cell(record.get("retrieved_at")) + "; vendor as-of " +
              _cell(record.get("vendor_as_of") or "unknown") + ". Retrieval time alone does not establish freshness.",
              "Metric / vendor period | Average | Low | High | Analyst count | Currency / unit / basis",
              "--- | ---: | ---: | ---: | ---: | ---"]
    for row in record.get("estimates", [])[:8]:
        lines.append(" | ".join([_cell(row["metric"] + " / " + row["period_code"]),
            *[_number(row.get(key)) for key in ("average", "low", "high")],
            _cell(row.get("analyst_count") if row.get("analyst_count") is not None else "unknown"),
            _cell(" / ".join(row.get(key) or "unknown" for key in ("currency", "unit", "basis")))]))
    lines.append("")
    for row in record.get("price_targets", [])[:1]:
        lines.append("Vendor price targets, unverified: low " + _number(row.get("low")) +
                     ", mean " + _number(row.get("mean")) + ", high " + _number(row.get("high")) +
                     "; currency and horizon " + _cell(row.get("currency") or "unknown") + ".")
    for row in record.get("surprises", [])[:4]:
        lines.append("Vendor EPS surprise " + _cell(row["period_end"]) + ": estimate " + _number(row.get("estimate")) +
                     ", actual " + _number(row.get("actual")) + ", difference " + _number(row.get("difference")) +
                     "; vendor surprise field " + _number(row.get("surprise_percent")) + " (vendor units unverified).")
    for row in record.get("revisions", [])[:4]:
        lines.append("Vendor EPS revisions " + _cell(row["period_code"]) + ": " +
                     ", ".join(key.replace("_", " ") + " " + _cell(row.get(key) if row.get(key) is not None else "unknown")
                               for key in ("up_last_7_days", "down_last_7_days", "up_last_30_days", "down_last_30_days")) + ".")
    lines.append("Management guidance remains separately source-labeled above. No difference is calculated without matching explicit fiscal dates, metric, currency, unit and accounting basis. Unknown dimensions are not comparable.")
    lines.append("Current consensus is not evidence of pre-event expectations. Vendor/model judgments never become accepted evidence.")
    return "\n".join(lines)


def shared_valuation_reference(state):
    from tradingagents.agents.valuation_comparison import (
        price_implied_valuation,
        render_price_implied_valuation,
    )

    components = [render_price_implied_valuation(price_implied_valuation(state)),
                  render_valuation_reference(state["valuation_reference"]),
                  render_guidance_consensus(state)]
    lines, used = [], 0
    for component in components:
        for line in component.splitlines():
            if used + len(line) + 1 > MAX_REFERENCE_BRIEF - 120:
                lines.append("Bounded valuation context: additional rows omitted; complete typed inputs and lineage remain retained.")
                return "\n".join(lines)
            lines.append(line)
            used += len(line) + 1
    return "\n".join(lines)


def validate_vendor_expectations(state):
    """Typed, hash-bound replay only; vendor content remains unverified evidence."""
    from datetime import UTC
    from zoneinfo import ZoneInfo

    from pydantic import ValidationError

    from tradingagents.dataflows.vendors.yahoo.expectations import VendorExpectations, _hash

    record = None
    try:
        raw = state.get("vendor_expectations")
        if not isinstance(raw, dict):
            raise ValueError("No retained vendor expectations")
        record = VendorExpectations.model_validate(raw)
        if record.ticker != normalize_symbol(state["company_of_interest"]) or str(record.requested_as_of) != state["trade_date"]:
            raise ValueError("Vendor expectations ticker or analysis cutoff mismatch")
        if record.status == "unavailable" and record.snapshot_hash is None:
            return record.model_dump(mode="json")
        if record.snapshot_hash != _hash(record):
            raise ValueError("Vendor expectations snapshot hash mismatch")
        stamp = record.retrieved_at
        zone = ZoneInfo((state.get("analysis_clock") or {}).get("timezone") or "America/Denver")
        if (stamp is None or stamp.tzinfo is None or stamp.astimezone(zone).date() != record.requested_as_of
            or stamp > datetime.now(UTC)):
            raise ValueError("Vendor expectations original retrieval cutoff unavailable or mismatched")
        cutoff = (state.get("analysis_clock") or {}).get("cutoff_utc")
        if cutoff and stamp > datetime.fromisoformat(cutoff.replace("Z", "+00:00")):
            raise ValueError("Vendor expectations retrieved after analysis cutoff")
        return record.model_dump(mode="json")
    except (ValueError, TypeError, KeyError) as exc:
        reason = ("Retained vendor expectations are invalid" if isinstance(exc, ValidationError)
                  else str(exc))
        try:
            ticker = normalize_symbol(state["company_of_interest"])
            requested_as_of = state["trade_date"]
            same_scope = (record is not None and record.ticker == ticker
                          and str(record.requested_as_of) == requested_as_of)
            unavailable = VendorExpectations(
                status="unavailable", reason=reason[:400], ticker=ticker,
                requested_as_of=requested_as_of,
                retrieved_at=record.retrieved_at if same_scope else None,
                vendor_as_of=record.vendor_as_of if same_scope else None,
            )
            return unavailable.model_dump(mode="json")
        except (ValueError, TypeError, KeyError):
            return {**_unavailable("Vendor expectations cannot be tied to the analysis scope"),
                    "label": "vendor consensus, unverified"}


def render_guidance_consensus(state):
    from tradingagents.agents.valuation_comparison import price_implied_valuation
    from tradingagents.agents.valuation_outlooks import grounded_outlooks
    from tradingagents.dataflows.vendors.yahoo.expectations import compare_guidance_consensus

    record = validate_vendor_expectations(state)
    vendor_lines = render_vendor_expectations(record).splitlines()
    lines = vendor_lines[:2]
    outlooks = grounded_outlooks(state)
    if not any(outlook.kind == "guidance" and outlook.metric == "Revenue" for outlook in outlooks):
        # Reuse the source-only statement already validated for the price-implied
        # section. Keep its stated period; do not invent explicit fiscal dates or
        # an accounting basis merely to make a vendor comparison possible.
        source = price_implied_valuation(state)
        interval = source.get("management_revenue_guidance_range_usd")
        if interval:
            period = source.get("management_revenue_guidance_period") or f"full year {source['analysis_year']}"
            reference = source["disclosure_references"]["revenue"]
            lines += [f"Management revenue guidance ({_cell(period)}): "
                      f"{_number(interval[0])}–{_number(interval[1])} USD; source-bound management statement, not an observed result. "
                      f"source_id {_cell(reference['source_id'])}; {_cell(reference['locator'])}.",
                      "Guidance/consensus difference unavailable: matching explicit fiscal dates, currency, units and accounting basis are not established for both records. No period or basis is inferred.", ""]
        else:
            lines += ["Management revenue guidance unavailable from source-only discovery; no compatible row is inferred.", ""]
    lines.extend(vendor_lines[2:])
    for outlook in outlooks:
        if outlook.kind != "guidance":
            continue
        metric = "revenue" if outlook.metric == "Revenue" else "eps"
        # EPS share definitions are not interchangeable. The vendor must declare
        # basic/diluted explicitly; the current free tables do not.
        if metric == "eps":
            lines.append("Guidance " + _cell(outlook.metric) + " versus consensus unavailable: vendor EPS share definition unknown.")
            continue
        guidance = {"metric": metric, "period_start": str(outlook.period_start), "period_end": str(outlook.period_end),
                    "currency": outlook.unit, "unit": outlook.unit, "basis": outlook.basis,
                    "low": str(outlook.low), "high": str(outlook.high)}
        compared = compare_guidance_consensus(guidance, record)
        lines.append(f"Source guidance {_cell(outlook.metric)}, {outlook.period_start} to {outlook.period_end}: "
                     f"{_number(outlook.low)}–{_number(outlook.high)} {_cell(outlook.unit)}, {_cell(outlook.basis)}; "
                     "source_id " + _cell(", ".join(outlook.source_ids)) + ".")
        if compared["status"] == "comparable":
            lines.append("Dimension-comparable vendor consensus, unverified: average " +
                         _number(compared["consensus_average"]) + "; difference from guidance midpoint " +
                         _number(compared["difference"]) + " " + _cell(outlook.unit) + ".")
        else:
            lines.append("Guidance/consensus difference unavailable: " + _cell(compared["reason"]))
    return "\n".join(lines)
