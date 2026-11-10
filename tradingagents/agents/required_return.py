"""The yearly return required from a stock, and a case value brought back to the analysis date.

One stated assumption: the 10-year Treasury yield retrieved for the run plus a fixed premium.
Everything here is arithmetic on that assumption; nothing is a forecast.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

SERIES = "DGS10"
DEFAULT_PREMIUM = Decimal("0.05")
MAX_PREMIUM = Decimal("0.30")


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def premium_from_config(config) -> Decimal | None:
    """The configured premium as a fraction, or None when the setting is unusable."""
    value = (config or {}).get("required_return_premium", DEFAULT_PREMIUM)
    premium = None if isinstance(value, bool) else _decimal(value)
    return premium if premium is not None and 0 <= premium <= MAX_PREMIUM else None


def fetch_required_return(as_of: str, config) -> dict:
    """Retrieve the yield as known on ``as_of`` and add the premium. Never assumes a yield."""
    premium = premium_from_config(config)
    if premium is None:
        return {"status": "unavailable", "reason": "required_return_premium must be a fraction between 0 and 0.30"}
    vendors = {name.strip() for name in str((config or {}).get("data_vendors", {}).get("macro_data", "")).split(",")}
    if "fred" not in vendors:
        return {"status": "unavailable", "reason": "No Treasury yield source is configured; no other vendor was used"}
    try:
        from tradingagents.dataflows.vendors.fred import latest_observation
        from tradingagents.source_replay import external_input

        # Recorded with the run's other outside inputs, so a replayed comparison reads the same yield.
        point = external_input("fred.latest_observation", {"series_id": SERIES, "as_of": as_of},
                               lambda: latest_observation(SERIES, as_of))
    except Exception as exc:  # a missing key or an unreachable source leaves the return unstated, never assumed
        return {"status": "unavailable", "reason": f"The 10-year Treasury yield could not be retrieved ({type(exc).__name__})"}
    return required_return_record(point, premium, as_of)


def required_return_record(point, premium: Decimal, as_of: str) -> dict:
    """Validate one retrieved yield observation and state the required return built on it."""
    percent = _decimal((point or {}).get("value"))
    observed = str((point or {}).get("date") or "")
    try:
        usable = percent is not None and Decimal(0) <= percent <= Decimal(25) and date.fromisoformat(observed) <= date.fromisoformat(as_of)
    except ValueError:
        usable = False
    if not usable:
        return {"status": "unavailable", "reason": f"No usable 10-year Treasury yield was published by {as_of}"}
    risk_free = percent / 100
    return {"schema_version": 1, "status": "available", "series": SERIES, "source": "FRED",
            "observation_date": observed, "as_of": as_of, "risk_free_rate": str(risk_free),
            "premium": str(premium), "rate": str(risk_free + premium)}


def rate_from_state(state) -> Decimal | None:
    record = state.get("required_return") if isinstance(state, dict) or hasattr(state, "get") else None
    if not isinstance(record, dict) or record.get("status") != "available":
        return None
    rate = _decimal(record.get("rate"))
    return rate if rate is not None and Decimal(0) <= rate <= Decimal(1) else None


def value_today(price, analysis_date, period_end, rate) -> Decimal | None:
    """``price`` at ``period_end`` brought back to ``analysis_date`` at a yearly ``rate``; None when not computable."""
    price, rate = _decimal(price), _decimal(rate)
    try:
        days = (date.fromisoformat(str(period_end)) - date.fromisoformat(str(analysis_date))).days
    except ValueError:
        return None
    if price is None or rate is None or price <= 0 or rate < 0 or days < 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        return price / (1 + rate) ** (Decimal(days) / Decimal(365))


def render_required_return(record) -> str:
    if not isinstance(record, dict) or record.get("status") is None:
        return ""
    numbers = [_decimal(record.get(key)) for key in ("rate", "risk_free_rate", "premium")]
    if record["status"] != "available" or None in numbers or rate_from_state({"required_return": record}) is None:
        reason = record.get("reason") if record["status"] != "available" else "the saved record is not usable"
        return f"Required return unavailable: {reason or 'not recorded'}. No value today or sizing rule is stated."
    return (f"Required return {Decimal(record['rate']) * 100:.2f}% a year: 10-year Treasury yield "
            f"{Decimal(record['risk_free_rate']) * 100:.2f}% ({record['source']} {record['series']}, {record['observation_date']}) "
            f"plus a fixed premium of {Decimal(record['premium']) * 100:.2f} points. A stated assumption, not a forecast.")
