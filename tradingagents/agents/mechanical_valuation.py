
"""Source-only, model-independent equity/revenue reference sensitivities.

Every publication must recompute this projection from canonical state. It adds
neither accepted evidence nor a target, rating, gate, model call, or data fetch.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext
from html import escape

LABEL = "Mechanical sensitivity from reference ranges, not a forecast"
BASIS = "equity value / revenue"
MAX_ROWS = 162


def _decimal(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a valuation number")
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError("Positive finite valuation inputs required")
    return number


def _text(value):
    text = format(Decimal(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _block(label, reason):
    return {"label": label, "status": "unavailable", "reason": reason,
            "outlooks": [], "rows": []}


def _record(status="unavailable", reason=None):
    return {"schema_version": 1, "label": LABEL, "status": status,
            "reason": reason, "price": None, "reference_blocks": {},
            "blocks": {"management": _block("Source-bound management guidance", reason),
                       "vendor": _block("vendor consensus, unverified", reason)}}


def _reference_blocks(reference):
    history = reference.get("own_history") or {}
    peers = reference.get("peers") or {}
    result = {}
    for group, source in (("own_history", history), ("peers", peers)):
        rows = []
        if group == "peers" and len(peers.get("accepted") or []) < 3:
            for peer in peers.get("accepted") or []:
                stats = peer["statistics"]
                if stats.get("status") == "available":
                    if stats.get("basis", "equity_value / trailing_revenue") != "equity_value / trailing_revenue":
                        raise ValueError("Peer multiple basis is not equity value / revenue")
                    rows.append({"group": group, "name": peer["ticker"],
                                 "multiple": _text(_decimal(stats["multiple"])),
                                 "basis": BASIS, "source": deepcopy(stats)})
            reason = "Fewer than three accepted peers; individual sensitivities only, no peer low/median/high."
        else:
            container = history if group == "own_history" else peers.get("range") or {}
            stats = container.get("statistics")
            if container.get("basis", "equity_value / trailing_revenue") != "equity_value / trailing_revenue":
                raise ValueError("Reference multiple basis is not equity value / revenue")
            if source.get("status", "available") == "available" and container.get("status") == "available" and stats:
                for name in ("low", "median", "high"):
                    rows.append({"group": group, "name": name,
                                 "multiple": _text(_decimal(stats[name])),
                                 "basis": BASIS, "source": deepcopy(source)})
            reason = source.get("reason") or container.get("reason")
        result[group] = {"status": "available" if rows else "unavailable",
                         "reason": reason, "rows": rows}
    return result


def _management_outlooks(source):
    interval = source.get("management_revenue_guidance_range_usd")
    references = source.get("disclosure_references") or {}
    result = []
    if interval:
        low, high = map(_decimal, interval)
        if high < low:
            raise ValueError("Inverted management revenue range")
        common = {"kind": "management", "period": source["management_revenue_guidance_period"],
                  "period_start": None, "period_end": None,
                  "horizon": source["management_revenue_guidance_period"],
                  "currency": "USD", "unit": "USD", "accounting_basis": "unknown",
                  "source_references": [references["revenue"]],
                  "qualification": "Source-bound guidance; fiscal dates and accounting comparability unverified."}
        for name, revenue in (("guidance low", low), ("guidance high", high)):
            result.append({**deepcopy(common), "label": name, "revenue": _text(revenue)})
        growth = source.get("growth_floor_percent")
        if growth:
            growth = _decimal(growth)
            result.append({**deepcopy(common), "label": "at the guidance floor",
                           "revenue": _text(low * (1 + growth / 100)),
                           "period": source["growth_floor_period"],
                           "horizon": source["growth_floor_period"],
                           "base_revenue": _text(low),
                           "base_period": common["period"], "growth_floor_percent": _text(growth),
                           "source_references": [references["revenue"], references["growth_floor"]],
                           "qualification": "At the guidance floor applied to the base guidance low, held fixed; not a lower bound on future share price."})
    return result


def _vendor_outlooks(vendor):
    result, reasons, periods = [], [], set()
    # Annual relative codes are retained literally; never infer a fiscal calendar.
    for estimate in vendor.get("estimates") or []:
        if estimate.get("metric") != "revenue" or estimate.get("period_code") not in {"0y", "+1y"}:
            continue
        code = estimate["period_code"]
        if code in periods:
            raise ValueError("Duplicated annual vendor revenue period")
        periods.add(code)
        if estimate.get("currency") != "USD" or estimate.get("unit") != "USD":
            reasons.append("Vendor revenue currency/unit compatibility unknown or incompatible; no price calculated.")
            continue
        low, average, high = (estimate.get(k) for k in ("low", "average", "high"))
        present = [_decimal(v) for v in (low, average, high) if v is not None]
        if present != sorted(present):
            reasons.append("Vendor estimate range is inconsistent; no price calculated.")
            continue
        code = estimate["period_code"]
        relative = "next fiscal year" if code == "+1y" else "current fiscal year"
        start, end = estimate.get("period_start"), estimate.get("period_end")
        period = f"{start} to {end}" if start and end else f"vendor {relative} ({code}), dates unverified"
        for name, value in (("low", low), ("average", average), ("high", high)):
            if value is None:
                continue
            result.append({"kind": "vendor", "label": "vendor " + name,
                           "revenue": _text(_decimal(value)), "period": period,
                           "period_code": code, "period_start": start, "period_end": end,
                           "horizon": period, "currency": "USD", "unit": "USD",
                           "accounting_basis": estimate.get("basis") or "unknown",
                           "source_references": [{"source": vendor.get("source"),
                               "snapshot_hash": vendor.get("snapshot_hash"),
                               "retrieved_at": vendor.get("retrieved_at"),
                               "vendor_as_of": vendor.get("vendor_as_of")}],
                           "qualification": "vendor consensus, unverified; fiscal dates unverified when absent; never accepted evidence."})
    return result, reasons


def _share_bases(source):
    shares = []
    if source.get("shares"):
        reported = source["shares"]
        shares.append({"kind": "outstanding", "value": _text(_decimal(reported["value"])),
                       "date": reported["date"], "period": None,
                       "fact_id": reported["fact_id"], "source_ids": reported["source_ids"]})
    guided = source.get("guided_diluted_weighted_average_shares_range")
    if guided:
        low, high = map(_decimal, guided)
        if high < low:
            raise ValueError("Inverted guided share range")
        for name, value in (("low", low), ("high", high)):
            shares.append({"kind": "guided diluted weighted average", "point": name,
                           "value": _text(value), "date": None,
                           "period": source.get("guided_share_period"),
                           "source_reference": source["disclosure_references"]["guided_shares"],
                           "qualification": "Period-weighted sensitivity; not a forecast year-end count."})
    return shares


def _rows(outlooks, references, shares, price):
    result = []
    for outlook in outlooks:
        for reference in references:
            for share in shares:
                revenue, multiple, count = map(_decimal, (outlook["revenue"], reference["multiple"], share["value"]))
                conditional = revenue * multiple / count
                reasons = []
                if not outlook["period_start"] or not outlook["period_end"]:
                    reasons.append("Explicit fiscal period dates unknown; horizons cannot be pooled.")
                if outlook["accounting_basis"] == "unknown":
                    reasons.append("Revenue accounting basis unknown; comparability unverified.")
                if share["kind"] == "guided diluted weighted average":
                    reasons.append("Guided weighted-average share period is distinct from outstanding shares and may differ from the revenue period.")
                if outlook["kind"] == "vendor":
                    reasons.append("Vendor estimates remain unverified; never a verified decision range.")
                result.append({"basis": BASIS, "reference": {k: deepcopy(v) for k, v in reference.items() if k != "source"},
                               "outlook": deepcopy(outlook), "shares": deepcopy(share),
                               "conditional_price": _text(conditional), "currency": "USD",
                               "price_change_percent": _text((conditional / _decimal(price["close"]) - 1) * 100),
                               "completed_price_date": price["session_date"],
                               "decision_comparable": not reasons,
                               "comparability_reasons": reasons,
                               "fixed_assumptions": [
                                   "Equity multiple: revenue × multiple ÷ shares; no obligation deduction.",
                                   "Reference multiple held fixed; historical/peer business comparability and future rerating unverified.",
                                   "Share basis held fixed; no forecast capital changes or distributions.",
                                   "Future-period arithmetic is undiscounted; price change is not annualized or dividend inclusive."]})
    return result


def mechanical_valuation_grid(state):
    """Recompute from canonical source projections; no model inputs or mutation."""
    from tradingagents.agents.valuation_comparison import price_implied_valuation
    from tradingagents.agents.valuation_reference import _validated_package
    from tradingagents.agents.valuation_reference_flow import (
        replay_valuation_reference,
        validate_vendor_expectations,
    )

    if state.get("asset_type", "stock") != "stock":
        return _record("not_applicable", "Mechanical stock sensitivities do not apply to this asset.")
    quality = state.get("evidence_quality") or {}
    if quality.get("scope") not in {None, "Selected US SEC-filer fundamentals"}:
        return _record("not_applicable", "Mechanical stock sensitivities do not apply to this evidence scope.")
    result = _record()
    try:
        _validated_package(state.get("financial_evidence"))
        source = price_implied_valuation(state)
        if source.get("status") != "available":
            raise ValueError(source.get("reason") or "Canonical completed price/capital unavailable")
        references = replay_valuation_reference(state, state.get("valuation_reference"))
        result["reference_blocks"] = _reference_blocks(references)
        result["price"] = deepcopy(source["price"])
        refrows = [row for block in result["reference_blocks"].values() for row in block["rows"]]
        shares = _share_bases(source)
        if not refrows:
            raise ValueError("No independently available own-history or peer reference multiple.")
        if not shares:
            raise ValueError("No source-grounded share basis available.")
        with localcontext() as context:
            context.prec = 60
            management = _management_outlooks(source)
            vendor = validate_vendor_expectations(state)
            try:
                vendor_outlooks, vendor_reasons = _vendor_outlooks(vendor) if vendor.get("status") in {"available", "partial"} else ([], [])
            except (ValueError, TypeError, KeyError, ArithmeticError):
                vendor_outlooks, vendor_reasons = [], ["Vendor revenue inputs invalid; management block remains independently available."]
            for key, outlooks, reason in (
                ("management", management, "No source-bound management revenue outlook available."),
                ("vendor", vendor_outlooks, "; ".join(vendor_reasons) or vendor.get("reason") or "No eligible annual vendor revenue estimate available."),
            ):
                block = result["blocks"][key]
                block["outlooks"] = outlooks
                block["rows"] = _rows(outlooks, refrows, shares, result["price"])
                block["status"] = "available" if block["rows"] else "unavailable"
                block["reason"] = None if block["rows"] else reason
        if sum(len(b["rows"]) for b in result["blocks"].values()) > MAX_ROWS:
            raise ValueError("Mechanical sensitivity exceeds bounded row limit.")
        result["status"] = "available" if any(b["rows"] for b in result["blocks"].values()) else "unavailable"
        result["reason"] = None if result["status"] == "available" else "No eligible revenue outlook available."
        return result
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return _record(reason=str(exc)[:400])


def validate_mechanical_valuation_grid(state, record):
    """Reject persisted projections altered independently of their source state."""
    fresh = mechanical_valuation_grid(state)
    if record != fresh:
        raise ValueError("Mechanical valuation projection differs from canonical sources")
    return fresh


def _cell(value):
    return escape(" ".join(str(value).split())).replace("|", "&#124;")



def _view_identity(outlook):
    if outlook["kind"] == "vendor":
        return "vendor-" + outlook["period_code"]
    return ("management-growth-floor" if outlook["label"] == "at the guidance floor"
            else "management-guidance")


def _interval(values):
    values = list(values)
    return [_text(min(values)), _text(max(values))] if values else None


def _compact_basis(rows):
    if not rows:
        return None
    prices = [_decimal(row["conditional_price"]) for row in rows]
    returns = [Decimal(row["price_change_percent"]) for row in rows]
    median = [row for row in rows if row["reference"]["group"] == "own_history"
              and row["reference"]["name"] == "median"]
    share = rows[0]["shares"]
    return {
        "kind": share["kind"], "shares_range": _interval(_decimal(row["shares"]["value"]) for row in rows),
        "date": share["date"], "period": share["period"],
        "price_range": _interval(prices), "return_range": _interval(returns),
        "median_price_range": _interval(_decimal(row["conditional_price"]) for row in median),
        "median_return_range": _interval(Decimal(row["price_change_percent"]) for row in median),
        "source_shares": sorted({str(row["shares"]): deepcopy(row["shares"]) for row in rows}.values(),
                                key=lambda source: (source.get("point", ""), source["value"])),
        "comparability_reasons": sorted({reason for row in rows for reason in row["comparability_reasons"]}),
        "decision_comparable": all(row["decision_comparable"] for row in rows),
    }


def compact_mechanical_valuation_grid(record):
    """Pure UI projection; original schema-one cells and validation are unchanged.

    Intervals are envelopes of retained calculated cells, not pooled horizons or
    fair-value estimates. Source endpoints are never replaced by a midpoint.
    """
    if not record:
        return {"schema_version": 1, "status": "unavailable", "reason": "No mechanical source projection",
                "label": LABEL, "price": None, "blocks": {}}
    compact = {"schema_version": 1, "status": record["status"], "reason": record.get("reason"),
               "label": record.get("label", LABEL), "price": deepcopy(record.get("price")), "blocks": {}}
    for key, block in record.get("blocks", {}).items():
        result = {"label": block["label"], "status": block["status"],
                  "reason": block.get("reason"), "reference_groups": []}
        groups = {}
        for row in block["rows"]:
            reference = row["reference"]
            individual = reference["group"] == "peers" and reference["name"] not in {"low", "median", "high"}
            identity = (reference["group"], reference["name"] if individual else "range")
            groups.setdefault(identity, []).append(row)
        for group, name in sorted(groups, key=lambda key: (key[0] != "own_history", key[1])):
            rows = groups[(group, name)]
            grouped = {"group": group, "name": name, "basis": BASIS,
                       "label": ("Own-history reference sensitivities" if group == "own_history"
                                 else "Peer reference sensitivities" + (f" — {name} individually" if name != "range" else "")),
                       "reference_multiple_range": _interval(_decimal(row["reference"]["multiple"]) for row in rows),
                       "rows": []}
            views = {}
            for row in rows:
                views.setdefault(_view_identity(row["outlook"]), []).append(row)
            order = {"management-guidance": 0, "management-growth-floor": 1, "vendor-0y": 2, "vendor-+1y": 3}
            for identity in sorted(views, key=lambda key: (order.get(key, 4), key)):
                values = views[identity]
                outlooks = sorted({str(row["outlook"]): row["outlook"] for row in values}.values(),
                                  key=lambda outlook: (outlook["label"], outlook["revenue"]))
                first = outlooks[0]
                sources = list({str(source): deepcopy(source) for outlook in outlooks
                                for source in outlook["source_references"]}.values())
                view = {
                    "view_id": identity, "label": ("management guidance range" if identity == "management-guidance"
                            else "at the guidance floor" if identity == "management-growth-floor"
                            else "vendor revenue range"),
                    "revenue_range": _interval(_decimal(outlook["revenue"]) for outlook in outlooks),
                    "revenue_average": next((outlook["revenue"] for outlook in outlooks if outlook["label"] == "vendor average"), None),
                    "period": first["period"], "horizon": first["horizon"],
                    "period_start": first["period_start"], "period_end": first["period_end"],
                    "accounting_basis": first["accounting_basis"], "source_references": sources,
                    "source_outlooks": deepcopy(outlooks),
                    "qualifications": sorted({outlook["qualification"] for outlook in outlooks}),
                    "reported_shares": _compact_basis([row for row in values if row["shares"]["kind"] == "outstanding"]),
                    "guided_shares": _compact_basis([row for row in values if row["shares"]["kind"] == "guided diluted weighted average"]),
                }
                grouped["rows"].append(view)
            result["reference_groups"].append(grouped)
        compact["blocks"][key] = result
    return compact


def history_median_position(record):
    """Compare completed price with exact history-median sensitivities only.

    A numerical position does not establish source-period comparability or
    decision authority. Vendor and management views remain distinct.
    """
    compact = compact_mechanical_valuation_grid(record)
    result = {"schema_version": 1, "status": compact["status"], "price": deepcopy(compact["price"]),
              "rows": [], "reason": compact.get("reason"),
              "qualification": "Conditional arithmetic only; not a forecast, target or recommendation. Unknown fiscal/accounting comparability remains unknown."}
    if not compact.get("price") or compact["status"] == "not_applicable":
        return result
    observed = _decimal(compact["price"]["close"])
    for block_key, block in compact["blocks"].items():
        for group in block["reference_groups"]:
            if group["group"] != "own_history":
                continue
            for view in group["rows"]:
                for field in ("reported_shares", "guided_shares"):
                    basis = view[field]
                    if not basis or not basis["median_price_range"]:
                        continue
                    low, high = map(_decimal, basis["median_price_range"])
                    position = ("equal" if low == high == observed else "below" if observed < low
                                else "above" if observed > high else "within")
                    result["rows"].append({
                        "view_id": view["view_id"], "label": view["label"], "source_block": block_key,
                        "share_basis": basis["kind"], "share_date": basis["date"], "share_period": basis["period"],
                        "shares_range": deepcopy(basis["shares_range"]),
                        "price_interval": deepcopy(basis["median_price_range"]), "position": position,
                        "period": view["period"], "horizon": view["horizon"],
                        "source_references": deepcopy(view["source_references"]),
                        "decision_comparable": basis["decision_comparable"],
                        "comparability_reasons": deepcopy(basis["comparability_reasons"]),
                        "qualifications": deepcopy(view["qualifications"]),
                    })
    if not result["rows"]:
        result.update(status="unavailable", reason="Own-history median sensitivity unavailable; no position inferred.")
    else:
        result["status"], result["reason"] = "available", None
    return result


def _display_interval(values):
    from tradingagents.agents.valuation_comparison import display_number
    if not values:
        return "unavailable"
    low, high = values
    return display_number(low) if Decimal(low) == Decimal(high) else f"{display_number(low)}–{display_number(high)}"


def render_history_median_position(summary):
    """Short code-computed summary; stable view IDs are references, not evidence verdicts."""
    if not summary or summary.get("status") == "not_applicable":
        return ""
    if summary.get("status") != "available":
        return "History-median position unavailable: " + str(summary.get("reason") or "No canonical summary")
    lines = ["History-median sensitivity position — conditional arithmetic, not a forecast or recommendation.",
             f"Completed close {_display_interval([summary['price']['close']] * 2)} {summary['price']['currency']}, {summary['price']['session_date']}."]
    for row in summary["rows"]:
        if row["source_block"] == "vendor":
            label = "Vendor consensus, unverified; " + row["horizon"].removeprefix("vendor ")
        elif row["view_id"] == "management-growth-floor":
            label = "At the guidance floor, " + row["horizon"]
        else:
            label = "Management guidance, " + row["horizon"]
        share = ("reported shares as of " + row["share_date"] if row["share_basis"] == "outstanding"
                 else "guided diluted weighted-average shares for " + str(row["share_period"]))
        lines.append(f"- {label}; {share}: the close is {row['position']} the history-median sensitivity of {_display_interval(row['price_interval'])} USD.")
    lines += ["Intervals hold the historical median multiple and stated share basis fixed; undiscounted, price-only changes. Fiscal/accounting comparability may be unknown; guided weighted averages are not year-end shares. Vendor rows are unverified and separate. Full exact cells, dates and sources: evidence.json."]
    return "\n".join(lines)


def _compact_cell_text(cell, *, history):
    if not cell:
        return "Unavailable — no source-grounded share basis"
    text = _display_interval(cell["price_range"]) + " USD / " + _display_interval(cell["return_range"]) + "%"
    if history and cell["median_price_range"]:
        text += "; **history median " + _display_interval(cell["median_price_range"]) + " USD**"
    label = ("outstanding, measured " + cell["date"] if cell["kind"] == "outstanding"
             else "guided weighted average, " + str(cell["period"]))
    return text + "; shares " + _display_interval(cell["shares_range"]) + " (" + _cell(label) + ")"


def render_mechanical_valuation_grid(record):
    """Compact report projection; complete exact cells and lineage stay in evidence."""
    compact = compact_mechanical_valuation_grid(record)
    if compact["status"] == "not_applicable":
        return ""
    lines = ["### " + LABEL, "",
             "Separate reference groups and revenue horizons; no pooled price range. Returns are price changes against the completed close, not annualized or dividend-inclusive returns. Future values are undiscounted.", ""]
    if compact["price"]:
        price = compact["price"]
        lines += [f"Completed close: {_display_interval([price['close']] * 2)} {_cell(price['currency'])} on {_cell(price['session_date'])}.", ""]
    if compact["reason"]:
        lines += ["Unavailable: " + _cell(compact["reason"]), ""]
    for block in compact["blocks"].values():
        lines += ["#### " + _cell(block["label"]), ""]
        if not block["reference_groups"]:
            lines += ["Unavailable: " + _cell(block["reason"]), ""]
        for group in block["reference_groups"]:
            lines += ["##### " + _cell(group["label"]), "",
                      f"{BASIS}; reference multiple {_display_interval(group['reference_multiple_range'])}×.", "",
                      "Revenue view / period / horizon | Reported outstanding shares | Guided diluted weighted-average shares",
                      "--- | --- | ---"]
            for view in group["rows"]:
                label = f"{view['label']}: {_display_interval(view['revenue_range'])} USD; {view['period']}; horizon {view['horizon']}"
                if view["revenue_average"]:
                    label += "; vendor average " + _display_interval([view["revenue_average"]] * 2) + " USD"
                lines.append(_cell(label) + " | " + _compact_cell_text(view["reported_shares"], history=group["group"] == "own_history")
                             + " | " + _compact_cell_text(view["guided_shares"], history=group["group"] == "own_history"))
            lines.append("")
        # Show each source view's conditions once, regardless of reference groups.
        views = {view["view_id"]: view for group in block["reference_groups"] for view in group["rows"]}
        for view in views.values():
            if view["view_id"] == "management-growth-floor":
                outlook = view["source_outlooks"][0]
                lines += ["At the guidance floor: base revenue " + _display_interval([outlook["base_revenue"]] * 2)
                          + " USD, " + _cell(outlook["base_period"]) + "; growth floor "
                          + _cell(outlook["growth_floor_percent"]) + "%; base guidance low held fixed, not a lower bound on future share price."]
        lines += [""]
    lines += ["Held fixed: reference multiples and stated share bases; equity revenue × multiple ÷ shares, with no obligation deduction. No future capital changes or distributions are assumed. Guided diluted weighted averages are not a forecast year-end count.",
              "Conditional arithmetic only. Fiscal dates, accounting definitions, business comparability and future rerating may be unknown; no decision range is inferred. Vendor estimates remain unverified.",
              "Full exact cells, source_id references, share dates, periods, definitions and assumptions remain in evidence.json."]
    return "\n".join(lines)
