"""Display-only changes against a verified publication available at this run's cutoff."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingagents.agents.shared_valuation import replay_cases
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


def _fields(record):
    requests = record.get("requests", [])
    if not isinstance(requests, list) or len(requests) > 3:
        raise ValueError("Invalid retained case list")
    values = {}
    for item in requests:
        name, raw = item["name"].strip(), item["request"]
        if not name or len(name) > 80 or name in values:
            raise ValueError("Invalid retained case name")
        method = raw.get("method")
        if method == "revenue_case":
            request = RevenueCase.model_validate(raw)
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
        if forecast is not None:
            fields.update(forecast=f"{_number(forecast.value)} {forecast.unit}; {forecast.basis}; {forecast.kind}",
                          period=f"{forecast.period_start} to {forecast.period_end}")
        values[name] = fields
    return values


def _horizon(state):
    horizon = state.get("horizon") or (state.get("decision_context") or {}).get("horizon") or {}
    return horizon.get("text") if horizon.get("status") == "explicit" else "unavailable"


def _filings(state):
    raw = state.get("filing_evidence")
    if raw is None:
        return None
    package = DisclosurePackage.model_validate(raw)
    return {(d.filing.accession, str(d.filing.filed_date)) for d in package.documents}


def assumption_changes(config: dict, ticker: str, current: dict) -> dict:
    """Compute once at fresh finalization; exports only render the saved result.

    Strict publication/evidence reads prevent a corrupt recent record from
    silently reviving an older comparison. No narrative supplies financial facts.
    """
    from tradingagents.memory.publication import list_records, load_evidence

    result = {"status": "unavailable", "prior_decision_id": None, "prior_as_of": None,
              "new_filings_between": None, "rows": []}
    try:
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
            return {**result, "status": "no_prior"}
        record = max(prior, key=lambda r: (_stamp(r["published_at"]), r["sequence"]))
        snapshot = load_evidence(config, record)
        result.update(prior_decision_id=record["decision_id"], prior_as_of=record["requested_as_of"])
        previous = _fields(snapshot.get("shared_valuation_scenarios") or {})
        effective = _fields(replay_cases(current))
        rows = []
        for name in sorted(previous.keys() | effective.keys()):
            old, new = previous.get(name, {}), effective.get(name, {})
            for field in ("multiple", "forecast", "period", "share_basis"):
                a, b = old.get(field, "not present"), new.get(field, "not present")
                if a != b:
                    rows.append({"scenario": name, "field": field, "previous": a, "current": b})
        if _horizon(snapshot) != _horizon(current):
            rows.append({"scenario": "Decision", "field": "horizon",
                         "previous": _horizon(snapshot), "current": _horizon(current)})
        old_filings, new_filings = _filings(snapshot), _filings(current)
        return {**result, "status": "available", "rows": rows,
                "new_filings_between": (bool(new_filings - old_filings)
                                        if old_filings is not None and new_filings is not None else None)}
    except (ValueError, TypeError, KeyError, AttributeError, OSError, ArithmeticError) as exc:
        return {**result, "reason": f"Prior-publication comparison unavailable ({type(exc).__name__})"}
