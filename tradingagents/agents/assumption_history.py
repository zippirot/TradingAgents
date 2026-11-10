"""Display-only changes against a verified publication available at this run's cutoff."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError

from tradingagents.agents.shared_valuation import _label_capital_estimates, replay_cases
from tradingagents.agents.valuation import EVRevenueTarget, PETarget
from tradingagents.agents.valuation_cases import RevenueCase
from tradingagents.dataflows.date_window import resolve_analysis_cutoff
from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage


def _stamp(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("Publication cutoff requires timezone")
    return stamp


def _number(value):
    text = format(Decimal(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _why(exc):
    if isinstance(exc, ValidationError) and exc.errors():
        first = exc.errors()[0]
        return ".".join(str(part) for part in first["loc"]) + ": " + first["msg"]
    return str(exc) or type(exc).__name__


def _fields(record, unusable=None):
    """Comparable fields per retained case. One unusable case is named in ``unusable`` and skipped."""
    requests = record.get("requests", [])
    if not isinstance(requests, list) or len(requests) > 3:
        raise ValueError("Invalid retained case list")
    values = []
    names = set()
    for index, item in enumerate(requests):
        try:
            values.append(_case_fields(item, names))
        except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError) as exc:
            if unusable is None:
                raise
            name = item.get("name") if isinstance(item, dict) else None
            unusable.append({"scenario": name.strip()[:80] if isinstance(name, str) and name.strip() else f"case {index + 1}",
                             "reason": _why(exc)[:240]})
    return values


def _case_fields(item, names):
    name, raw = item["name"].strip(), item["request"]
    if not name or len(name) > 80 or name in names:
        raise ValueError("Invalid retained case name")
    names.add(name)
    role = item.get("scenario_role")
    if role is not None and (not isinstance(role, str) or not role.strip()):
        raise ValueError("Invalid retained scenario role")
    role = role.strip().casefold() if role is not None else None
    method = raw.get("method")
    if method == "revenue_case":
        # A capital value retained without its label is priced as the analyst's estimate; compare it the same way.
        request = RevenueCase.model_validate(_label_capital_estimates(raw, 0, []))
        forecast = request.forecast
        fields = {"multiple": f"{_number(request.multiple)}× {request.multiple_basis} / {request.multiple_period}",
                  "share_basis": f"{_number(request.capital.closing_shares.value)} shares "
                                 f"({request.capital.closing_shares.assumption}; {request.capital.valuation_date})"}
    elif method == "pe":
        request = PETarget.model_validate(raw)
        forecast = request.forecast
        fields = {"multiple": _number(request.multiple), "share_basis": request.eps_fact_id}
    elif method == "ev_revenue":
        request = EVRevenueTarget.model_validate(raw)
        if len(request.scenarios) != 1:
            raise ValueError("Shared legacy row must have one scenario")
        forecast = request.scenarios[0].forecast
        fields = {"multiple": _number(request.scenarios[0].multiple),
                  "share_basis": request.shares_fact_id}
    else:
        raise ValueError("Unsupported retained case")
    period = None
    if forecast is not None:
        fields.update(forecast=f"{_number(forecast.value)} {forecast.unit}; {forecast.basis}; {forecast.kind}",
                      period=f"{forecast.period_start} to {forecast.period_end}")
        period = (str(forecast.period_start), str(forecast.period_end))
    return {"name": name, "key": (method, period, role), "fields": fields}


def _case_changes(previous, effective):
    old_groups, new_groups = defaultdict(list), defaultdict(list)
    for item in previous:
        old_groups[item["key"]].append(item)
    for item in effective:
        new_groups[item["key"]].append(item)
    rows = []
    for key in sorted(old_groups.keys() | new_groups.keys(), key=str):
        old, new = old_groups[key], new_groups[key]
        if len(old) == len(new) == 1:
            for field in ("forecast", "multiple", "share_basis"):
                before = old[0]["fields"].get(field, "not present")
                after = new[0]["fields"].get(field, "not present")
                if before != after:
                    rows.append({"scenario": new[0]["name"], "field": field,
                                 "previous": before, "current": after})
            continue
        for item in old:
            rows.append({"scenario": item["name"], "field": "case",
                         "previous": "present", "current": "dropped"})
        for item in new:
            rows.append({"scenario": item["name"], "field": "case",
                         "previous": "not present", "current": "added"})
    return rows


def _filings(state):
    raw = state.get("filing_evidence")
    if raw is None:
        return None
    package = DisclosurePackage.model_validate(raw)
    return {(d.filing.accession, str(d.filing.filed_date)) for d in package.documents}


def prior_publication(config: dict, ticker: str, current: dict):
    """The last directional publication of an earlier run known at this run's cutoff, with its label, or None."""
    from tradingagents.memory.publication import list_records

    clock = current.get("analysis_clock") or resolve_analysis_cutoff(
        str(current["trade_date"]), config.get("analysis_timezone", "America/Denver"))
    cutoff = min(_stamp(clock["cutoff_utc"]), datetime.now(UTC))
    identity = current.get("run_id")
    marker = current.get("publication_record") or {}
    if marker.get("published_at"):
        cutoff = min(cutoff, _stamp(marker["published_at"]))
    records = list_records(config, ticker)
    own = next((r for r in records if r["decision_id"] == identity), None)
    prior = []
    for record in records:
        stamp = record.get("published_at")
        if (not record["eligibility"]["directional"] or not stamp
                or record["decision_id"] == identity or _stamp(stamp) > cutoff):
            continue
        if own and (_stamp(stamp), record["sequence"]) >= (_stamp(own["published_at"]), own["sequence"]):
            continue
        prior.append(record)
    if not prior:
        return None
    record = max(prior, key=lambda r: (_stamp(r["published_at"]), r["sequence"]))
    label = record["requested_as_of"]
    if str(current.get("trade_date")) == label:
        label = f"{_stamp(record['published_at']).astimezone(UTC):%Y-%m-%d %H:%M} UTC ({record['decision_id'][:8]})"
    return record, label


def compare_cases(snapshot: dict, current: dict) -> dict:
    """Field-level case changes; a case unusable on either side is named and only that case is left out."""
    skipped_before, skipped_now = [], []
    previous = _fields(snapshot.get("shared_valuation_scenarios") or {}, skipped_before)
    effective = _fields(replay_cases(current), skipped_now)
    old_methods = {item["key"][0] for item in previous}
    new_methods = {item["key"][0] for item in effective}
    different_method = bool(old_methods and new_methods and old_methods != new_methods)
    rows = [] if different_method else _case_changes(previous, effective)
    unusable = ([{"side": "previous", **row} for row in skipped_before]
                + [{"side": "current", **row} for row in skipped_now])
    if unusable:
        # A case missing from one side for being unreadable is not evidence that it was added or dropped.
        rows = [row for row in rows if row["field"] != "case"]
    return {"rows": rows, "unusable": unusable,
            **({"summary_message": "Prior publication used a different valuation method; "
                                   "field-level comparison not shown"} if different_method else {})}


def assumption_changes(config: dict, ticker: str, current: dict) -> dict:
    """Compute once at fresh finalization; exports only render the saved result.

    Strict publication/evidence reads prevent a corrupt recent record from
    silently reviving an older comparison. No narrative supplies financial facts.
    """
    from tradingagents.memory.publication import load_evidence

    result = {"status": "unavailable", "comparison_version": 2, "prior_decision_id": None, "prior_as_of": None,
              "new_filings_between": None, "rows": []}
    try:
        found = prior_publication(config, ticker, current)
        if found is None:
            return {**result, "status": "no_prior"}
        record, label = found
        snapshot = load_evidence(config, record)
        result.update(prior_decision_id=record["decision_id"], prior_as_of=record["requested_as_of"],
                      prior_label=label)
        cases = compare_cases(snapshot, current)
        old_filings, new_filings = _filings(snapshot), _filings(current)
        return {**result, "status": "available", "rows": cases["rows"],
                **({"unusable": cases["unusable"]} if cases["unusable"] else {}),
                **({"summary_message": cases["summary_message"]} if "summary_message" in cases else {}),
                "new_filings_between": (bool(new_filings - old_filings)
                                        if old_filings is not None and new_filings is not None else None)}
    except (ValueError, TypeError, KeyError, AttributeError, OSError, ArithmeticError) as exc:
        return {**result, "reason": f"Prior-publication comparison unavailable ({type(exc).__name__})"}
