"""Fresh bounded B3 context shared only by the named decision roles."""
from tradingagents.agents.mechanical_valuation import (
    history_median_position,
    mechanical_valuation_grid,
    render_history_median_position,
    render_mechanical_valuation_grid,
)

MAX_MECHANICAL_CONTEXT = 12000


def mechanical_position_from_state(state):
    """Recompute advisory position without trusting saved projections."""
    if state.get("asset_type", "stock") != "stock":
        return {"status": "not_applicable", "rows": [], "reason": "Stock sensitivities only"}
    if (state.get("evidence_quality") or {}).get("status") not in {"sufficient", "limited"}:
        return {"status": "unavailable", "rows": [], "reason": "Current validated financial evidence unavailable"}
    return history_median_position(mechanical_valuation_grid(state))


def mechanical_role_context(state):
    """Every eligible role sees the same canonical view; no network or model."""
    if state.get("asset_type", "stock") != "stock" or not isinstance(state.get("valuation_reference"), dict):
        return ""
    if (state.get("evidence_quality") or {}).get("status") not in {"sufficient", "limited"}:
        return "Shared mechanical valuation context unavailable: current validated financial evidence unavailable."
    grid = mechanical_valuation_grid(state)
    if grid.get("status") == "not_applicable":
        return ""
    summary = render_history_median_position(history_median_position(grid))
    compact = render_mechanical_valuation_grid(grid)
    text = ("Shared mechanical valuation context — source-only conditional calculations\n"
            + summary + "\n\n" + compact +
            "\nUse these code-computed figures rather than recalculating them. Cite the revenue view, horizon "
            "and share basis; dispute specific revenue, multiple and share assumptions. Vendor values/dates "
            "remain unverified. These sensitivities do not validate a target, expected return or rating; "
            "final claim and valuation validation remain authoritative.")
    if len(text) > MAX_MECHANICAL_CONTEXT:
        return ("Shared mechanical valuation context unavailable: compact source view exceeds the bounded "
                "context limit; no partial grid or inferred position supplied.")
    return text
