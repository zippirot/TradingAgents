"""Point-in-time safe, unverified Yahoo analyst expectations.

Yahoo's public estimate tables use relative period codes, not explicit fiscal
start/end dates. They are retained as given and cannot by themselves be
compared with dated management guidance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from pydantic import BaseModel, Field

from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import yf_retry

LABEL = "vendor consensus, unverified"
SOURCE = "Yahoo Finance via yfinance"


class Estimate(BaseModel):
    metric: Literal["revenue", "eps"]
    period_code: str
    period_start: str | None = None
    period_end: str | None = None
    currency: str | None = None
    unit: str | None = None
    basis: str | None = None
    analyst_count: int | None = None
    average: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None


class PriceTarget(BaseModel):
    period_start: str | None = None
    period_end: str | None = None
    currency: str | None = None
    unit: str | None = None
    low: Decimal | None = None
    mean: Decimal | None = None
    high: Decimal | None = None
    median: Decimal | None = None


class Surprise(BaseModel):
    metric: Literal["eps"] = "eps"
    period_end: str
    currency: str | None = None
    unit: str | None = None
    basis: str | None = None
    estimate: Decimal | None = None
    actual: Decimal | None = None
    difference: Decimal | None = None
    surprise_percent: Decimal | None = None


class Revision(BaseModel):
    metric: Literal["eps"] = "eps"
    period_code: str
    period_start: str | None = None
    period_end: str | None = None
    basis: str | None = None
    currency: str | None = None
    unit: Literal["analyst count"] = "analyst count"
    up_last_7_days: int | None = None
    down_last_7_days: int | None = None
    up_last_30_days: int | None = None
    down_last_30_days: int | None = None


class VendorExpectations(BaseModel):
    status: Literal["available", "partial", "unavailable"]
    reason: str | None = None
    label: Literal["vendor consensus, unverified"] = LABEL
    source: Literal["Yahoo Finance via yfinance"] = SOURCE
    ticker: str
    requested_as_of: date
    retrieved_at: datetime | None = None
    vendor_as_of: datetime | None = None
    snapshot_hash: str | None = None
    estimates: list[Estimate] = Field(default_factory=list)
    price_targets: list[PriceTarget] = Field(default_factory=list)
    surprises: list[Surprise] = Field(default_factory=list)
    revisions: list[Revision] = Field(default_factory=list)
    section_reasons: dict[str, str] = Field(default_factory=dict)


def _hash(record: VendorExpectations) -> str:
    payload = record.model_dump(mode="json", exclude={"snapshot_hash"})
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _number(value) -> Decimal | None:
    if isinstance(value, Mapping):
        value = value.get("raw")
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _nonnegative(value) -> Decimal | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _positive(value) -> Decimal | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _count(value) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number >= 0 and number == int(number) else None


def _text(value) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("raw") or value.get("fmt")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _rows(value):
    if not isinstance(value, pd.DataFrame) or value.empty:
        return []
    return [(str(index), row) for index, row in value.iterrows()]


def _unavailable(ticker: str, as_of: date, reason: str) -> VendorExpectations:
    return VendorExpectations(
        status="unavailable", reason=reason, ticker=ticker, requested_as_of=as_of
    )


def get_vendor_expectations(
    ticker: str,
    as_of: date | str,
    *,
    observed_at: datetime | None = None,
    analysis_timezone: str = "America/Denver",
    retained_snapshot: Mapping | None = None,
) -> VendorExpectations:
    """Read current Yahoo estimates or replay a hash-checked original snapshot.

    ``as_of`` is an analysis calendar date in ``analysis_timezone``. A date
    before the local observation date is historical. Yahoo has no point-in-time estimate history, so a
    historical request never contacts it. ``observed_at`` allows a caller to
    capture the precise observation instant; absent it, UTC now is used.
    """
    canonical = normalize_symbol(ticker)
    requested = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    observed = observed_at or datetime.now(UTC)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must include a timezone")
    observed = observed.astimezone(UTC)
    zone = ZoneInfo(analysis_timezone)
    observed_day = observed.astimezone(zone).date()

    if retained_snapshot is not None:
        try:
            replay = VendorExpectations.model_validate(retained_snapshot)
            timestamp = replay.retrieved_at
            if (
                replay.ticker == canonical
                and replay.requested_as_of == requested
                and replay.status != "unavailable"
                and timestamp is not None
                and timestamp.tzinfo is not None
                and timestamp.astimezone(zone).date() <= requested
                and timestamp <= observed
                and replay.snapshot_hash == _hash(replay)
            ):
                return replay
        except (ValueError, TypeError, AttributeError):
            pass
        return _unavailable(
            canonical,
            requested,
            "Retained vendor snapshot failed ticker, cutoff, timestamp or hash validation",
        )

    if requested < observed_day:
        return _unavailable(
            canonical,
            requested,
            "Historical Yahoo expectations unavailable: no retained point-in-time snapshot",
        )
    if requested > observed_day:
        return _unavailable(canonical, requested, "Analysis date is after the observation date")

    results = {}
    failures = []
    section_reasons = {}
    for name, method in (
        ("revenue", "get_revenue_estimate"),
        ("eps", "get_earnings_estimate"),
        ("targets", "get_analyst_price_targets"),
        ("surprises", "get_earnings_history"),
        ("revisions", "get_eps_revisions"),
    ):
        try:
            results[name] = yf_retry(
                lambda method=method: getattr(yf.Ticker(canonical), method)(), max_retries=0
            )
        except Exception as exc:  # one failed Yahoo field does not erase the others
            failures.append(f"{name}: {type(exc).__name__}")
            section_reasons[name] = f"Yahoo request failed: {type(exc).__name__}"
            results[name] = None

    estimates = []
    for metric in ("revenue", "eps"):
        for period, row in _rows(results[metric]):
            if period not in {"0q", "+1q", "0y", "+1y"} or all(
                _number(row.get(k)) is None for k in ("avg", "low", "high")
            ):
                continue
            currency = _text(row.get("currency"))
            unit = f"{currency}/share" if metric == "eps" and currency else currency
            estimates.append(
                Estimate(
                    metric=metric,
                    period_code=period,
                    currency=currency,
                    unit=unit,
                    basis=_text(row.get("methodology")) if metric == "eps" else None,
                    analyst_count=_count(row.get("numberOfAnalysts")),
                    average=(_nonnegative if metric == "revenue" else _number)(row.get("avg")),
                    low=(_nonnegative if metric == "revenue" else _number)(row.get("low")),
                    high=(_nonnegative if metric == "revenue" else _number)(row.get("high")),
                )
            )

    targets = []
    raw_targets = results["targets"]
    if isinstance(raw_targets, Mapping) and any(
        _positive(raw_targets.get(k)) is not None for k in ("low", "mean", "high", "median")
    ):
        targets.append(
            PriceTarget(
                low=_positive(raw_targets.get("low")),
                mean=_positive(raw_targets.get("mean")),
                high=_positive(raw_targets.get("high")),
                median=_positive(raw_targets.get("median")),
            )
        )

    surprises = []
    for period, row in _rows(results["surprises"])[-4:]:
        try:
            period_end = date.fromisoformat(period[:10]).isoformat()
        except ValueError:
            continue
        surprises.append(
            Surprise(
                period_end=period_end,
                basis=_text(row.get("methodology")),
                estimate=_number(row.get("epsEstimate")),
                actual=_number(row.get("epsActual")),
                difference=_number(row.get("epsDifference")),
                surprise_percent=_number(row.get("surprisePercent")),
            )
        )

    revisions = []
    for period, row in _rows(results["revisions"]):
        if period not in {"0q", "+1q", "0y", "+1y"}:
            continue
        revisions.append(
            Revision(
                period_code=period,
                basis=_text(row.get("methodology")),
                currency=_text(row.get("currency")),
                up_last_7_days=_count(row.get("upLast7days")),
                down_last_7_days=_count(row.get("downLast7days")),
                up_last_30_days=_count(row.get("upLast30days")),
                down_last_30_days=_count(row.get("downLast30days")),
            )
        )

    for name, present in (
        ("revenue", any(row.metric == "revenue" for row in estimates)),
        ("eps", any(row.metric == "eps" for row in estimates)),
        ("targets", bool(targets)),
        ("surprises", bool(surprises)),
        ("revisions", bool(revisions)),
    ):
        if not present and name not in section_reasons:
            section_reasons[name] = "Yahoo returned no usable data"
    have = bool(estimates or targets or surprises or revisions)
    status = "partial" if have and section_reasons else "available" if have else "unavailable"
    reason = "; ".join(failures) if failures else None
    if not have and reason is None:
        reason = "Yahoo returned no analyst expectations"
    record = VendorExpectations(
        status=status,
        reason=reason,
        ticker=canonical,
        requested_as_of=requested,
        retrieved_at=observed,
        estimates=estimates,
        price_targets=targets,
        surprises=surprises,
        revisions=revisions,
        section_reasons=section_reasons,
    )
    record.snapshot_hash = _hash(record)
    return record


def compare_guidance_consensus(
    guidance: Mapping,
    expectations: VendorExpectations | Mapping,
) -> dict:
    """Compare only explicitly equal fiscal dates, metric, currency, unit, and basis."""
    source = (
        expectations.model_dump(mode="json")
        if isinstance(expectations, VendorExpectations)
        else expectations
    )
    required = ("metric", "period_start", "period_end", "currency", "unit", "basis")
    if not isinstance(guidance, Mapping) or not isinstance(source, Mapping):
        return {"status": "unavailable", "reason": "Missing structured guidance or consensus"}
    rows = source.get("estimates") or []
    if source.get("status") not in ("available", "partial"):
        return {"status": "unavailable", "reason": source.get("reason") or "Consensus unavailable"}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if not all(
            guidance.get(key) and row.get(key) and guidance[key] == row[key] for key in required
        ):
            continue
        average = _number(row.get("average"))
        low = _number(guidance.get("guidance_low", guidance.get("low")))
        high = _number(guidance.get("guidance_high", guidance.get("high")))
        if average is None or low is None or high is None:
            continue
        midpoint = (low + high) / 2
        return {
            "status": "comparable",
            "label": LABEL,
            "source": SOURCE,
            "retrieved_at": source.get("retrieved_at"),
            "vendor_as_of": source.get("vendor_as_of"),
            "dimensions": {key: row[key] for key in required},
            "consensus_average": str(average),
            "guidance_midpoint": str(midpoint),
            "difference": str(average - midpoint),
        }
    return {
        "status": "unavailable",
        "reason": "No consensus estimate matches explicit fiscal period, metric, currency, unit and accounting basis",
    }
