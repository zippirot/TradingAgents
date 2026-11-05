"""Optional pre-debate scenarios, calculated with the final valuation engine.

Forecasts and multiples remain model assumptions. This record never determines
an actionable rating, a final target, or the evidence gate's verdict.
"""
from __future__ import annotations

import json
import re
from html import escape

from pydantic import ValidationError

from tradingagents.agents.valuation import EVRevenueTarget, PETarget, validate_target
from tradingagents.agents.valuation_outlooks import grounded_outlooks
from tradingagents.dataflows.financial_evidence import EvidencePackage

MAX_PAYLOAD = 48000
SCOPE = "Selected US SEC-filer fundamentals"


def _record(status, requests=(), rows=(), reasons=()):
    return {"status": status, "requests": list(requests), "rows": list(rows), "reasons": list(reasons)}


def _parse(report):
    matches = re.findall(r"```valuation_scenarios\s*\n(.*?)\n```", report, re.S)
    if len(matches) != 1 or len(matches[0]) > MAX_PAYLOAD:
        raise ValueError("Scenario block missing, duplicated or oversized")
    return json.loads(matches[0])


def _comparable(request, result):
    common = (request.method, result.unit, result.valuation_period_start,
              result.valuation_period_end, result.accounting_basis)
    if isinstance(request, EVRevenueTarget):
        return (*common, request.revenue_fact_id, request.shares_fact_id,
                request.cash_fact_id, request.perimeter,
                tuple(sorted((k, tuple(sorted(v))) for k, v in request.obligation_ids_by_category.items())))
    return (*common, request.eps_fact_id, request.eps_basis, request.forecast is not None)


def prepare_shared_valuation(state, requests=None):
    """Calculate optional inputs without modifying state or making external calls.

    Supplying saved requests replays calculations for publication. Stored prices
    and status strings are never used as inputs to this boundary.
    """
    quality = state.get("evidence_quality") or {}
    if (quality.get("status") not in {"sufficient", "limited"}
            or quality.get("scope") != SCOPE or state.get("asset_type", "stock") != "stock"):
        return _record("not_applicable", reasons=("Shared valuation scenarios do not apply to this evidence scope.",))
    try:
        package = EvidencePackage.model_validate(state.get("financial_evidence"))
        if str(package.as_of) != state.get("trade_date"):
            raise ValueError("Financial evidence date differs from this run")
        if requests is None:
            validation = state.get("financial_claim_validation") or {}
            report = validation.get("raw_report", "")
            if not isinstance(report, str):
                raise ValueError("Original fundamentals report unavailable")
            requests = _parse(report)
        # Apply the same collection limits to parsed and replayed requests.
        if not isinstance(requests, list) or len(requests) > 3:
            raise ValueError("Scenario inputs must be a list of at most three rows")
        if len(json.dumps(requests)) > MAX_PAYLOAD:
            raise ValueError("Scenario input payload oversized")
        if not requests:
            raise ValueError("No supported scenario inputs were supplied")
        names = [r.get("name") for r in requests if isinstance(r, dict)]
        valid_names = [n.strip() for n in names if isinstance(n, str)]
        if len(valid_names) != len(set(valid_names)):
            raise ValueError("Scenario names must be distinct")
    except (ValidationError, ValueError, TypeError, OverflowError):
        return _record("unavailable", reasons=("Shared scenario inputs or canonical evidence are missing, malformed, duplicated or oversized.",))

    outlooks = grounded_outlooks(state)
    rows, reasons, comparisons = [], [], []
    for index, row in enumerate(requests, 1):
        try:
            if not isinstance(row, dict) or set(row) != {"name", "request"}:
                raise ValueError("Expected name and request fields")
            name = row["name"]
            if not isinstance(name, str) or not name.strip() or len(name) > 80:
                raise ValueError("Scenario name missing or oversized")
            raw = row["request"]
            if not isinstance(raw, dict):
                raise ValueError("Scenario request malformed")
            if raw.get("method") == "ev_revenue":
                request = EVRevenueTarget.model_validate(raw)
                if len(request.scenarios) != 1 or request.scenarios[0].weight != 1:
                    raise ValueError("Shared EV/revenue rows require one independent scenario with weight=1")
            elif raw.get("method") == "pe":
                request = PETarget.model_validate(raw)
            else:
                raise ValueError("Unsupported scenario valuation method")
            result = validate_target(request, package, outlooks)
            if result.status != "supported":
                reasons.append(f"Row {index} omitted: " + "; ".join(result.reasons))
                continue
            comparisons.append(_comparable(request, result))
            rows.append({"name": name.strip(), "request": request.model_dump(mode="json"),
                         "result": result.model_dump(mode="json")})
        except ValidationError:
            reasons.append(f"Row {index} omitted: malformed valuation request")
        except (ValueError, TypeError, ArithmeticError) as exc:
            reasons.append(f"Row {index} omitted: {exc}")
    if comparisons and any(key != comparisons[0] for key in comparisons[1:]):
        return _record("unavailable", requests, reasons=("Scenario rows use incomparable methods, periods, bases or capital inputs; table omitted.",))
    status = ("partial" if reasons else "available") if rows else "unavailable"
    return _record(status, requests, rows, reasons)


def _cell(value):
    return escape(" ".join(str(value).split())).replace("|", r"\|")


def render_shared_valuation(record):
    """Render a freshly calculated record; callers must replay persisted inputs."""
    if not record or record.get("status") == "not_applicable":
        return ""
    lines = ["### Shared valuation scenarios — conditional research inputs", "",
             "Forecasts and multiples are assumptions, not verified predictions. These are independent scenarios, not a final price target or probability-weighted forecast.", ""]
    rows = record.get("rows") or []
    if rows:
        lines += ["Scenario | Method | Period | Conditional price", "--- | --- | --- | ---"]
        for row in rows:
            result = row["result"]
            lines.append(" | ".join(_cell(v) for v in (row["name"], {"pe": "P/E", "ev_revenue": "EV/revenue"}[result["method"]],
                f"{result['valuation_period_start']} to {result['valuation_period_end']}",
                f"{result['target']} {result['unit']}")))
        if any(row["result"]["method"] == "ev_revenue" or row["request"].get("forecast") for row in rows):
            lines += ["", "Future-period scenario values are not discounted to today."]
        for row in rows:
            result = row["result"]
            lines += ["", f"**{_cell(row['name'])} — inputs and assumptions**", "",
                      "Source fact IDs: " + ", ".join(_cell(v) for v in result["input_fact_ids"]), ""]
            if result["method"] == "ev_revenue":
                s = result["scenario_results"][0]
                lines.append(f"Revenue {s['revenue']} × multiple {s['multiple']} = enterprise value {s['enterprise_value']}; less net obligations {result['net_obligations']} = equity {s['equity_value']}; divided by {result['shares_outstanding']} common shares = {s['price']}.")
                lines.append(f"Capital snapshot: {result['capital_snapshot_date']}.")
            else:
                lines.append(f"{_cell(result['eps_basis'])} EPS {result['earnings_value']} × multiple {result['multiple']} = {result['target']}; {_cell(result['accounting_basis'])}.")
            lines.append("")
            lines += ["- " + _cell(v) for v in result["assumptions"] if not v.startswith("Scenario weights and valuation multiples")]
            lines += ["- Limitation: " + _cell(v) for v in result["warnings"]]
    if record.get("status") == "partial":
        lines += ["", "Partial table: some proposed scenarios could not be calculated."]
    lines += ["- " + _cell(v) for v in record.get("reasons", [])]
    return "\n".join(lines)
