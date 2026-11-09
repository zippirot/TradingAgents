"""Run the graph over a grid of tickers and dates, and score what came back.

One run yields one decision, so it cannot say whether the system decides well.
This runs the same machinery over many (ticker, date) cells and reads the
aggregate. The memory log is the results table: every run already records its
rating and later settles it with realized and alpha return against the
instrument's regional benchmark, so there is nothing to record separately.

Scope: this evaluates decision quality. It is not a portfolio simulator, and
must not grow one. Turning a rating into a filled order needs a quantity, a fill
price and a cash ledger, none of which the system has; inventing them here would
put an execution model behind an evaluation tool. Cells are therefore
independent, and a portfolio, when given, is the same standing book for every
cell rather than a position carried forward.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from tradingagents.agents.rating import RATING_REVIEW, run_rating
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.memory import TradingMemoryLog
from tradingagents.memory.log import is_trading_entry

logger = logging.getLogger(__name__)


def iter_grid(start_date: str, end_date: str, every_n_days: int = 1) -> list[str]:
    """Analysis dates from ``start_date``, never past today.

    A future date has no outcome to settle against, and the graph rejects one, so
    the grid stops at the present rather than producing cells that cannot score.
    """
    start, end = _canonical(start_date), _canonical(end_date)
    if every_n_days < 1:
        raise ValueError("every_n_days must be at least 1")
    if end < start:
        raise ValueError(f"the grid ends before it starts: {end_date} is before {start_date}")

    last = min(end, datetime.strptime(get_current_date(), "%Y-%m-%d"))
    dates, cursor = [], start
    while cursor <= last:
        dates.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=every_n_days)
    return dates


def _canonical(date: str) -> datetime:
    """Parse a grid bound, rejecting anything the run date would also reject."""
    try:
        parsed = datetime.strptime(str(date), "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"grid dates must be in YYYY-MM-DD format, got {date!r}") from exc
    if parsed.strftime("%Y-%m-%d") != str(date):
        raise ValueError(f"grid dates must be in YYYY-MM-DD format, got {date!r}")
    return parsed


def _alpha(entry: dict) -> float | None:
    """Alpha return of a settled entry, or None when it has not settled.

    The log stores it as a percentage rounded to one decimal, so aggregates here
    are accurate to 0.1 of a percentage point, not to the raw quote.
    """
    text = (entry.get("alpha") or "").strip().rstrip("%")
    try:
        return float(text) / 100
    except ValueError:
        return None


@dataclass
class BacktestResult:
    run_id: str
    log_path: Path
    cells_run: int = 0
    skipped: int = 0
    failures: list[tuple[str, str, str]] = field(default_factory=list)
    settlement_failures: list[tuple[str, str]] = field(default_factory=list)
    incomplete: list[tuple[str, str, str]] = field(default_factory=list)
    prior_quality: list[tuple[str, str, str]] = field(default_factory=list)


# What each rating claims will happen, so an outcome can be scored against it.
# Hold claims no direction, so nothing about alpha proves it right or wrong.
_DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


@dataclass
class RatingScore:
    count: int
    hit_rate: float | None
    mean_alpha: float


@dataclass
class BacktestSummary:
    resolved: int
    pending: int
    by_rating: dict[str, RatingScore]
    unscored: int = 0
    holding: str = ""
    incomplete: int = 0
    incomplete_details: list[tuple[str, str, str]] = field(default_factory=list)
    publication_evaluation: dict | None = None

    def render(self) -> str:
        lines = [
            f"Resolved cells: {self.resolved} · pending: {self.pending}"
            + (f" · unscored: {self.unscored}" if self.unscored else "")
            + (f" · incomplete REVIEW: {self.incomplete}" if self.incomplete else "")
        ]
        for rating, score in self.by_rating.items():
            called = (
                f"called the direction {score.hit_rate:.0%}"
                if score.hit_rate is not None
                else "no direction claimed"
            )
            lines.append(
                f"- {rating}: n={score.count}, {called}, "
                f"mean alpha {score.mean_alpha:+.2%} vs the benchmark"
            )
        lines.append("")
        if self.pending:
            lines.append("Pending cells are not scored above; re-run to settle them.")
        if self.incomplete:
            lines.append(
                "Incomplete REVIEW cells are unscored and are retried only on an explicit backtest launch/resume."
            )
            lines.extend(
                f"- {ticker} {date}: {reason}" for ticker, date, reason in self.incomplete_details
            )
        lines.append(
            f"Alpha is measured over {self.holding} from the first close after each analysis date. "
            "One model sampling per cell, and text feeds are not archived, so "
            "these figures are indicative rather than repeatable."
        )
        if self.publication_evaluation is not None:
            lines.insert(0, "Legacy memory-log summary (its recorded window only):")
            lines.extend(["", render_publication_evaluation(self.publication_evaluation)])
        return "\n".join(lines)


def run_backtest(
    tickers: list[str],
    dates: list[str],
    config: dict,
    asset_type: str = "stock",
    portfolio=None,
    selected_analysts=("market", "social", "news", "fundamentals"),
    run_id: str | None = None,
    progress: Callable[[int, int, str, str], None] | None = None,
) -> BacktestResult:
    """Analyze every ticker on every date, into a memory log of this run's own.

    The live log stays untouched: a sweep would otherwise flood the context that
    real runs read back. Cells already in this run's log are skipped, so an
    interrupted sweep resumes by being run again. ``progress(done, total,
    ticker, date)`` is called before each cell that runs.
    """
    # run_id becomes a path segment, so it is validated like a ticker: an
    # absolute or dotted value would otherwise place the run outside results_dir.
    run_id = safe_ticker_component(run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    run_dir = Path(config["results_dir"]) / "backtest" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_config = {
        **config,
        "results_dir": str(run_dir),
        "memory_log_path": str(run_dir / "trading_memory.md"),
        "evaluation_mode": "historical",
    }

    graph = TradingAgentsGraph(selected_analysts, config=run_config)
    result = BacktestResult(run_id=run_id, log_path=Path(run_config["memory_log_path"]))
    done = {
        (e["ticker"], e["date"]) for e in graph.memory_log.load_entries() if is_trading_entry(e)
    }
    prior = _saved_reviews(run_dir)
    for entry in graph.memory_log.load_entries():
        if not is_trading_entry(entry):
            prior.setdefault(
                (entry["ticker"], entry["date"]), "Legacy REVIEW: no trading decision recorded"
            )

    # A ticker or date given twice is one cell, run and settled once.
    tickers, dates = list(dict.fromkeys(tickers)), list(dict.fromkeys(dates))
    cells = [(ticker, date) for ticker in tickers for date in dates]
    todo = [cell for cell in cells if cell not in done]
    result.skipped = len(cells) - len(todo)
    for index, (ticker, date) in enumerate(todo, 1):
        if (ticker, date) in prior:
            result.prior_quality.append((ticker, date, prior[(ticker, date)]))
        if progress:
            progress(index, len(todo), ticker, date)
        try:
            state, _ = graph.propagate(ticker, date, asset_type, portfolio=portfolio)
            result.cells_run += 1
            if run_rating(state) == RATING_REVIEW:
                result.incomplete.append((ticker, date, _quality_reason(state)))
        except Exception as exc:  # one unreachable vendor must not end the sweep
            logger.warning("Backtest cell %s %s failed: %s", ticker, date, exc)
            result.failures.append((ticker, date, str(exc)))

    # Settlement runs at the start of the next run for a ticker, so each ticker's
    # last cell would stay pending without this pass.
    for ticker in tickers:
        try:
            graph.settle_pending(ticker)
        except Exception as exc:  # reflection calls an LLM; one failure is not the sweep's
            logger.warning("Settling %s failed: %s", ticker, exc)
            result.settlement_failures.append((ticker, str(exc)))
    return result


def _quality_reason(state: dict) -> str:
    quality = state.get("evidence_quality") or {}
    if not isinstance(quality, dict):
        quality = {}
    checks = quality.get("checks") or []
    if not isinstance(checks, list):
        checks = []
    reasons = quality.get("reasons") or [
        check.get("message", "")
        for check in checks
        if isinstance(check, dict) and check.get("status") in {"fail", "unavailable"}
    ]
    if isinstance(reasons, list):
        reasons = [reason for reason in reasons if isinstance(reason, str) and reason]
        if reasons:
            return "; ".join(dict.fromkeys(reasons))
    return "Research incomplete / REVIEW: no trading decision recorded"


def _saved_reviews(run_dir: Path) -> dict[tuple[str, str], str]:
    """Read existing full-state artifacts; never create a completion database."""
    reviews = {}
    for path in run_dir.glob("*/TradingAgentsStrategy_logs/full_states_log_*.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                continue
            ticker, date = state.get("company_of_interest"), state.get("trade_date")
            if not isinstance(ticker, str) or not isinstance(date, str):
                continue
            if (
                safe_ticker_component(ticker) != path.parent.parent.name
                or path.name != f"full_states_log_{date}.json"
            ):
                continue
            if not isinstance(state.get("evidence_quality", {}), dict):
                # The explicit saved rating remains usable; malformed optional
                # detail cannot crash reading an otherwise identifiable REVIEW.
                state = {**state, "evidence_quality": {}}
            if run_rating(state) == RATING_REVIEW:
                reviews[(ticker, date)] = _quality_reason(state)
        except (OSError, ValueError, TypeError):
            logger.warning("Saved backtest quality could not be read: %s", path)
    return reviews


def summarize(source: BacktestResult | str | Path) -> BacktestSummary:
    """Score the settled decisions of a backtest, or of a memory log at a path, by rating."""
    if isinstance(source, BacktestResult):
        path = source.log_path  # a run whose cells all failed wrote no log: nothing to score
    elif Path(source).is_file():
        path = Path(source)
    else:
        raise FileNotFoundError(f"no memory log at {source}")
    entries = TradingMemoryLog({"memory_log_path": str(path)}).load_entries()
    # A decision with no readable rating has no direction, so it can neither
    # count for nor against the system; it is reported as unscored instead.
    resolved = [(e, _alpha(e)) for e in entries if not e["pending"] and is_trading_entry(e)]
    resolved = [(e, a) for e, a in resolved if a is not None]
    by_rating: dict[str, RatingScore] = {}
    for rating in dict.fromkeys(e["rating"] for e, _ in resolved):
        alphas = [a for e, a in resolved if e["rating"] == rating]
        direction = _DIRECTION.get(rating, 0)
        by_rating[rating] = RatingScore(
            count=len(alphas),
            hit_rate=(sum(a * direction > 0 for a in alphas) / len(alphas)) if direction else None,
            mean_alpha=sum(alphas) / len(alphas),
        )
    completed = {(e["ticker"], e["date"]) for e in entries if is_trading_entry(e)}
    incomplete = _saved_reviews(path.parent)
    for entry in entries:
        if not is_trading_entry(entry):
            incomplete.setdefault(
                (entry["ticker"], entry["date"]), "Legacy REVIEW: no trading decision recorded"
            )
    if isinstance(source, BacktestResult):
        incomplete.update({(ticker, date): reason for ticker, date, reason in source.incomplete})
    incomplete = {cell: reason for cell, reason in incomplete.items() if cell not in completed}
    unscored = len(incomplete)
    # Report the window the outcomes were actually measured over, from the log.
    windows = {
        f"{e['holding'][:-1]} trading days"
        for e, _ in resolved
        if (e.get("holding") or "").endswith("d")
    }
    return BacktestSummary(
        resolved=len(resolved),
        pending=sum(is_trading_entry(e) for e in entries) - len(resolved),
        by_rating=by_rating,
        unscored=unscored,
        holding=", ".join(sorted(windows)) or "the configured window",
        incomplete=len(incomplete),
        incomplete_details=[(*cell, reason) for cell, reason in sorted(incomplete.items())],
        publication_evaluation=evaluate_publications({"results_dir": str(path.parent)})
        if (path.parent / "publications").is_dir()
        else None,
    )


# Versioned publications are a separate read-only evaluation surface. Legacy
# memory-log scoring above is retained for compatibility, never silently mixed.
def _evaluation_digest(value):
    import hashlib

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _distribution(values):
    """Linear-interpolated descriptive quantiles; no independence/significance claim."""
    import math

    ordered = sorted(values)
    if not ordered:
        return dict.fromkeys(("mean", "min", "p25", "median", "p75", "max"))

    def quantile(p):
        position = (len(ordered) - 1) * p
        left = math.floor(position)
        right = math.ceil(position)
        return ordered[left] + (ordered[right] - ordered[left]) * (position - left)

    return {
        "mean": sum(ordered) / len(ordered),
        "min": ordered[0],
        "p25": quantile(0.25),
        "median": quantile(0.5),
        "p75": quantile(0.75),
        "max": ordered[-1],
    }


def _frozen_inputs(snapshot):
    """Hash retained upstream source identities, not changed derived conclusions."""
    sources = set()
    for source in (snapshot.get("financial_evidence") or {}).get("sources", []):
        if source.get("url") and source.get("content_hash"):
            sources.add((source["url"], source["content_hash"]))
    for document in (snapshot.get("filing_evidence") or {}).get("documents", []):
        if document.get("url") and document.get("content_hash"):
            sources.add((document["url"], document["content_hash"]))
    price = snapshot.get("price_observation") or {}
    if price.get("status") == "available":
        sources.add((price["url"], price["content_hash"]))
    return _evaluation_digest(sorted(sources)) if sources else None


def _evaluation_attempts(config, cutoff):
    from datetime import UTC
    from uuid import UUID

    attempts = {}
    errors = []
    times = []
    prefix = "[Evaluation Attempt] "
    logs_without_markers = 0
    for path in sorted(Path(config["results_dir"]).glob("*/*/message_tool.log")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            if not any(line.startswith(prefix) for line in lines):
                logs_without_markers += 1
            for line in lines:
                if not line.startswith(prefix):
                    continue
                try:
                    row = json.loads(line[len(prefix) :])
                    UUID(row["attempt_id"])
                    if row["schema_version"] != 1 or row["event"] not in {
                        "started",
                        "completed",
                        "failed",
                    }:
                        raise ValueError("marker")
                    _canonical(row["requested_as_of"])
                    if not isinstance(row["ticker"], str) or not row["ticker"]:
                        raise ValueError("ticker")
                    stamp = datetime.fromisoformat(row["recorded_at"])
                    if stamp.utcoffset() is None:
                        raise ValueError("Attempt timestamp requires timezone")
                    stamp = stamp.astimezone(UTC)
                    if stamp > cutoff:
                        continue
                    row["recorded_at"] = stamp.isoformat()
                    group = attempts.setdefault(row["attempt_id"], [])
                    if group and any(
                        row[key] != group[0][key] for key in ("ticker", "requested_as_of")
                    ):
                        raise ValueError("identity")
                    group.append(row)
                    times.append(row["recorded_at"])
                except (KeyError, ValueError, TypeError, AttributeError):
                    errors.append(
                        {
                            "file": str(path.relative_to(config["results_dir"])),
                            "reason": "Malformed attempt marker",
                        }
                    )
        except (OSError, UnicodeError):
            errors.append(
                {
                    "file": str(path.relative_to(config["results_dir"])),
                    "reason": "Attempt log unreadable",
                }
            )
    counts = {"started": 0, "completed": 0, "failed": 0, "in_progress": 0}
    for rows in attempts.values():
        starts = [r for r in rows if r["event"] == "started"]
        ends = [r for r in rows if r["event"] != "started"]
        if (
            len(starts) != 1
            or len(ends) > 1
            or (ends and ends[0]["recorded_at"] < starts[0]["recorded_at"])
        ):
            errors.append(
                {
                    "attempt_id": rows[0]["attempt_id"],
                    "reason": "Incomplete or conflicting attempt lifecycle",
                }
            )
            continue
        counts["started"] += 1
        counts[ends[0]["event"] if ends else "in_progress"] += 1
    return {
        "status": "available" if attempts else "unavailable",
        **counts,
        "errors": errors,
        "failure_rate": counts["failed"] / counts["started"] if counts["started"] else None,
        "failure_rate_denominator": "valid started attempts visible at cutoff",
        "logs_without_markers": logs_without_markers,
        "coverage_completeness": "partial_or_legacy_unknown"
        if errors or logs_without_markers or counts["in_progress"] or not attempts
        else "recorded_markers_only",
        "coverage_start": min(times, default=None),
        "coverage_end": max(times, default=None),
        "note": "Attempt markers are execution coverage, not independent investment samples; older logs may lack failure history.",
    }


def evaluate_publications(config, known_at=None):
    """Read immutable publications/outcomes only; never settle, fetch or call models."""
    from datetime import UTC

    from tradingagents.memory import publication
    from tradingagents.memory.publication_outcomes import (
        _known_by,
        _summary_cutoff,
        endpoint_group_key,
        endpoint_label,
        load_outcomes,
        terminal_at,
    )

    cutoff = _summary_cutoff(
        str(known_at) if known_at is not None else datetime.now(UTC).isoformat()
    )
    report = {
        "schema_version": 1,
        "known_at": cutoff.isoformat(),
        "coverage": {
            "publications": 0,
            "primary": 0,
            "revisions": 0,
            "review_or_ineligible": 0,
            "without_predeclared_protocol": 0,
            "protocol_available": 0,
        },
        "groups": [],
        "observations": [],
        "terminal_outcomes": [],
        "publications": [],
        "integrity_errors": [],
        "calibration": {
            "status": "unavailable",
            "reason": "No defined mutually exclusive outcome events; scenario weights are not calibration data",
        },
        "limitations": [
            "Gross security/benchmark/excess returns only; not a portfolio P&L, drawdown or net-cost model.",
            "Overlapping horizons and issuer dependence prevent treating pooled horizons as independent samples.",
            "Historical LLM outcome knowledge may contaminate replay/holdout results; historical results do not establish investment skill.",
            "Sample minimums are descriptive disclosure thresholds, not statistical power guarantees.",
        ],
    }
    groups = {}
    retained = []
    paths = sorted((publication.record_root(config) / "records").glob("*.json"))
    for path in paths:
        try:
            record = publication.load_record(config, path.stem)
            if not _known_by(record.get("published_at") or record.get("imported_at"), cutoff):
                continue
            coverage = report["coverage"]
            coverage["publications"] += 1
            primary = record["eligibility"]["primary"]
            directional = record["eligibility"]["directional"]
            coverage[
                "primary" if primary else "revisions" if directional else "review_or_ineligible"
            ] += 1
            protocol = record.get("evaluation_protocol")
            protocol_present = isinstance(protocol, dict) and bool(protocol)
            prospective_predeclaration = bool(
                protocol_present
                and record["evaluation_mode"] == "prospective"
                and record.get("published_at")
            )
            if protocol_present:
                coverage["protocol_available"] += 1
            if not prospective_predeclaration:
                coverage["without_predeclared_protocol"] += 1
            snapshot = publication.load_evidence(config, record)
            companion = load_outcomes(config, record)
            publication_row = {
                "decision_id": record["decision_id"],
                "ticker": record["ticker"],
                "as_of": record["requested_as_of"],
                "evaluation_mode": record["evaluation_mode"],
                "primary": primary,
                "directional": directional,
                "versions": record["versions"],
                "frozen_input_sha256": _frozen_inputs(snapshot),
                "protocol_version": protocol.get("version") if isinstance(protocol, dict) else None,
                "protocol_prospectively_predeclared": prospective_predeclaration,
                "canonical_rating": record["canonical_rating"],
                "sequence": record["sequence"],
            }
            report["publications"].append(publication_row)
            retained.append((record, snapshot))
            for name, endpoint in companion["endpoints"].items():
                horizon = endpoint_group_key(endpoint)
                policy = (
                    record["evaluation_mode"],
                    *horizon,
                    endpoint["benchmark"],
                    endpoint.get("benchmark_alignment", "asof"),
                    endpoint.get("exit_policy", "nth_session_after_entry"),
                    publication_row["protocol_version"],
                )
                group = groups.setdefault(
                    policy,
                    {
                        "evaluation_mode": record["evaluation_mode"],
                        "horizon": list(horizon),
                        "horizon_label": endpoint_label(endpoint),
                        "benchmark": endpoint["benchmark"],
                        "benchmark_alignment": policy[4],
                        "exit_policy": policy[5],
                        "protocol_version": policy[6],
                        "primary": 0,
                        "resolved": 0,
                        "pending": 0,
                        "unresolvable": 0,
                        "revisions": 0,
                        "review_or_ineligible": 0,
                        "_rows": [],
                    },
                )
                if not primary:
                    group["revisions" if directional else "review_or_ineligible"] += 1
                    continue
                group["primary"] += 1
                terminal = terminal_at(endpoint, cutoff)
                if terminal:
                    group['unresolvable'] += 1
                    report['terminal_outcomes'].append({
                        'decision_id': record['decision_id'], 'endpoint': name,
                        'reason': terminal['reason'], 'known_at': terminal['known_at']})
                    continue
                outcome = endpoint.get("outcome")
                resolved = (
                    endpoint["status"] == "resolved"
                    and _known_by(endpoint["resolved_at"], cutoff)
                    and outcome["resolution_date"] <= cutoff.date().isoformat()
                )
                if not resolved:
                    group["pending"] += 1
                    continue
                row = {
                    **publication_row,
                    "endpoint": name,
                    "horizon": list(horizon),
                    "horizon_label": endpoint_label(endpoint),
                    "benchmark": endpoint["benchmark"],
                    "benchmark_alignment": group["benchmark_alignment"],
                    "exit_policy": group["exit_policy"],
                    "raw_return": outcome["raw_return"],
                    "benchmark_return": outcome["benchmark_return"],
                    "excess_return": outcome["alpha_return"],
                    "entry_date": outcome["entry"]["date"],
                    "exit_date": outcome["exit"]["date"],
                    "resolved_at": endpoint["resolved_at"],
                    "observation_window_id": outcome.get("observation_window_id"),
                    "direction": _DIRECTION.get(record["canonical_rating"], 0),
                }
                group["_rows"].append(row)
                group["resolved"] += 1
                report["observations"].append(row)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            report["integrity_errors"].append(
                {"decision_id": path.stem, "error_type": type(exc).__name__}
            )
    for _, group in sorted(groups.items(), key=lambda item: str(item[0])):
        rows = group.pop("_rows")
        directional = [row for row in rows if row["direction"]]
        group.update(
            direction_mapping=dict(_DIRECTION),
            directional_n=len(directional),
            directional_excess_hit_rate=sum(
                row["direction"] * row["excess_return"] > 0 for row in directional
            )
            / len(directional)
            if directional
            else None,
            distributions={
                label: _distribution([row[key] for row in rows])
                for label, key in [
                    ("raw", "raw_return"),
                    ("benchmark", "benchmark_return"),
                    ("excess", "excess_return"),
                ]
            },
        )
        issuers = len({r["ticker"] for r in rows})
        dates = len({r["as_of"] for r in rows})
        group["sample_adequacy"] = {
            "resolved_primary": len(rows),
            "issuers": issuers,
            "analysis_dates": dates,
            "minimum": {"resolved_primary": 30, "issuers": 3, "analysis_dates": 10},
            "met": len(rows) >= 30 and issuers >= 3 and dates >= 10,
            "meaning": "descriptive threshold only; no statistical power or investment-edge guarantee",
        }
        report["groups"].append(group)
    report["forecast_evaluation"] = _evaluate_forecasts(retained)
    report["attempts"] = _evaluation_attempts(config, cutoff)
    return report


def _forecast_groups(snapshot):
    """Supported requests only; scenario envelopes are not confidence intervals."""
    from tradingagents.agents.valuation import EVRevenueTarget, PETarget
    from tradingagents.dataflows.financial_evidence import EvidencePackage

    requests = []
    target = snapshot.get("target_validation") or {}
    if target.get("status") == "supported" and target.get("request"):
        requests.append(("canonical target", target["request"]))
    for row in (snapshot.get("shared_valuation_scenarios") or {}).get("rows", []):
        if (
            not row.get("diagnostic_only")
            and (row.get("result") or {}).get("status") == "supported"
        ):
            requests.append((row.get("name", "scenario"), row.get("request")))
    if not requests:
        return {}
    try:
        package = EvidencePackage.model_validate(snapshot.get("financial_evidence"))
    except (ValueError, TypeError):
        return {}
    groups = {}
    for label, raw in requests:
        try:
            if raw["method"] == "ev_revenue":
                request = EVRevenueTarget.model_validate(raw)
                forecasts = [
                    (f"{label}: {row.name}", "Revenue", row.forecast) for row in request.scenarios
                ]
            else:
                request = PETarget.model_validate(raw)
                forecasts = [
                    (
                        label,
                        "Basic EPS" if request.eps_basis == "basic" else "Diluted EPS",
                        request.forecast,
                    )
                ]
            for name, metric, forecast in forecasts:
                if forecast is None or forecast.period_end <= package.as_of:
                    continue
                key = (
                    package.cik,
                    forecast.period_start,
                    forecast.period_end,
                    forecast.unit,
                    forecast.basis,
                )
                key = (key[0], metric, *key[1:])
                row = {"label": name, "value": str(forecast.value), "kind": forecast.kind}
                current = groups.setdefault(key, [])
                if not any(
                    existing["value"] == row["value"] and existing["kind"] == row["kind"]
                    for existing in current
                ):
                    current.append(row)
        except (ValueError, TypeError, KeyError):
            continue
    return groups


def _evaluate_forecasts(retained):
    from decimal import Decimal, localcontext

    from tradingagents.dataflows.financial_evidence import EvidencePackage

    actual_packages = []
    for record, snapshot in retained:
        try:
            actual_packages.append(
                (record, EvidencePackage.model_validate(snapshot.get("financial_evidence")))
            )
        except (ValueError, TypeError):
            continue
    rows = []
    for record, snapshot in retained:
        if not record["eligibility"]["primary"]:
            continue
        for key, forecasts in _forecast_groups(snapshot).items():
            cik, metric, start, end, unit, basis = key
            row = {
                "decision_id": record["decision_id"],
                "ticker": record["ticker"],
                "evaluation_mode": record["evaluation_mode"],
                "metric": metric,
                "period_start": str(start),
                "period_end": str(end),
                "unit": unit,
                "basis": basis,
                "forecasts": forecasts,
                "status": "pending",
                "reason": "Later compatible canonical reported actual unavailable",
            }
            candidates = []
            stamp = record.get("published_at") or record.get("imported_at")
            for later, package in actual_packages:
                later_stamp = later.get("published_at") or later.get("imported_at")
                if (
                    later["ticker"] != record["ticker"]
                    or package.cik != cik
                    or later_stamp <= stamp
                ):
                    continue
                sources = {source.source_id: source for source in package.sources}
                facts = [
                    fact
                    for fact in package.facts
                    if fact.origin == "reported"
                    and fact.value is not None
                    and (fact.metric, fact.period_start, fact.period_end, fact.unit, fact.basis)
                    == (metric, start, end, unit, basis)
                    and fact.source_ids
                    and all(
                        end <= sources[sid].filed_date <= package.as_of for sid in fact.source_ids
                    )
                ]
                if facts:
                    candidates.append((later_stamp, later, facts))
            if candidates:
                _, later, facts = min(candidates, key=lambda item: (item[0], item[1]["sequence"]))
                if len({fact.value for fact in facts}) != 1:
                    row.update(
                        status="unavailable",
                        reason="Conflicting first reported actuals; no hindsight selection",
                    )
                else:
                    actual = facts[0].value
                    values = [Decimal(f["value"]) for f in forecasts]
                    with localcontext() as context:
                        context.prec = 60
                        errors = [
                            {
                                "label": forecast["label"],
                                "error": str(value - actual),
                                "percentage_error": str((value - actual) / abs(actual) * 100)
                                if actual
                                else None,
                            }
                            for forecast, value in zip(forecasts, values, strict=True)
                        ]
                    row.update(
                        status="resolved",
                        reason="Earliest later compatible reported actual; error is forecast minus actual",
                        actual=str(actual),
                        actual_publication_id=later["decision_id"],
                        actual_fact_ids=[f.fact_id for f in facts],
                        actual_source_ids=sorted({sid for f in facts for sid in f.source_ids}),
                        errors=errors,
                        scenario_envelope={
                            "low": str(min(values)),
                            "high": str(max(values)),
                            "covered": min(values) <= actual <= max(values),
                            "interpretation": "scenario range, not a calibrated probability interval",
                        },
                    )
            rows.append(row)
    return {
        "rows": rows,
        "resolved": sum(row["status"] == "resolved" for row in rows),
        "pending": sum(row["status"] == "pending" for row in rows),
        "unavailable": sum(row["status"] == "unavailable" for row in rows),
    }


def render_publication_evaluation(report):
    coverage = report["coverage"]
    lines = [
        "Versioned publication evaluation (gross outcomes; not a portfolio simulator).",
        f"Known at {report['known_at']}; publications {coverage['publications']}, primary {coverage['primary']}, revisions {coverage['revisions']}, REVIEW/ineligible {coverage['review_or_ineligible']}.",
        f"Integrity failures: {len(report['integrity_errors'])}; protocol available: {coverage.get('protocol_available', 'not recorded')}; prospective predeclaration unestablished: {coverage['without_predeclared_protocol']}.",
        "Legacy/historical protocols are applied at import/replay; their presence does not establish predeclaration before the original decision or historical outcomes.",
    ]
    for group in report["groups"]:
        mean = group["distributions"]["excess"]["mean"]
        hit = group["directional_excess_hit_rate"]
        lines.append(
            f"- {group['evaluation_mode']}; {group['horizon_label']}; {group['benchmark']} ({group['benchmark_alignment']}): resolved {group['resolved']}, pending {group['pending']}, unresolvable {group.get('unresolvable', 0)}; "
            + (f"mean excess {mean:+.2%}" if mean is not None else "mean excess unavailable")
            + (
                f"; directional hit rate {hit:.1%}"
                if hit is not None
                else "; no scored directional calls"
            )
            + (
                "; descriptive minimum met."
                if group["sample_adequacy"]["met"]
                else "; below descriptive sample minimum."
            )
        )
    forecasts = report["forecast_evaluation"]
    lines.append(
        f"Forecast groups: resolved {forecasts['resolved']}, pending {forecasts['pending']}, unavailable {forecasts['unavailable']}; scenario envelopes are not probability intervals."
    )
    attempts = report["attempts"]
    lines.append(
        "Execution failure history unavailable where legacy logs lack attempt markers."
        if attempts["status"] == "unavailable"
        else f"Execution attempts: started {attempts['started']}, completed {attempts['completed']}, failed {attempts['failed']}, in progress {attempts['in_progress']}; not investment samples."
    )
    lines.append("Probability calibration unavailable: " + report["calibration"]["reason"] + ".")
    lines.extend(report["limitations"])
    return "\n".join(lines)


def compare_frozen_publication_evaluations(baseline, current, protocol):
    """Compare prespecified first daily records on identical retained inputs.

    This does not run either pipeline. The caller freezes version/input manifests
    before scoring and supplies both read-only evaluation reports. No re-selection
    of dates, revisions or best-performing samples occurs here.
    """
    result = {
        "status": "unavailable",
        "matched_pairs": 0,
        "comparisons": [],
        "reasons": [],
        "performance_claim": "unproven",
        "protocol": protocol,
        "limitations": [
            "Frozen historical holdout is engineering evidence, not clean investment-skill evidence; LLM hindsight may remain.",
            "Raw market returns for identical windows are shared observations, not pipeline-specific portfolio returns.",
        ],
    }
    try:
        if protocol["schema_version"] != 1 or protocol["evaluation_mode"] not in {
            "historical",
            "prospective",
        }:
            raise ValueError("Unsupported frozen comparison protocol")
        development = set(protocol["development_dates"])
        holdout = set(protocol["holdout_dates"])
        if not development or not holdout or development & holdout:
            raise ValueError("Development and holdout dates must be nonempty and disjoint")
        for day in development | holdout:
            _canonical(day)
        pairs = protocol["pairs"]
        keys = [(p["ticker"], p["as_of"]) for p in pairs]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate requested comparison pairs; no best-of reruns")
        if "engineering_cells" in baseline or "engineering_cells" in current:
            return _compare_engineering_cells(
                baseline, current, protocol, development, holdout, result
            )
        matched = []
        for pair in pairs:
            if pair["as_of"] not in development | holdout:
                raise ValueError("Pair date is outside predeclared development/holdout sets")
            digest = pair["frozen_input_sha256"]
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Frozen input manifest hash required")
            selected = []
            for name, report in [("baseline", baseline), ("current", current)]:
                versions = protocol[name + "_versions"]
                if set(versions) != {"code", "prompt", "schema"} or any(
                    v is None or v == "" for v in versions.values()
                ):
                    raise ValueError("Exact code/prompt/schema fingerprints required")
                candidates = [
                    p
                    for p in report["publications"]
                    if (p["ticker"], p["as_of"], p["evaluation_mode"])
                    == (pair["ticker"], pair["as_of"], protocol["evaluation_mode"])
                ]
                primary = [p for p in candidates if p["primary"]]
                if len(primary) > 1:
                    raise ValueError("Competing primary observations")
                if not primary:
                    reviews = [p for p in candidates if not p["directional"]]
                    if not reviews:
                        raise ValueError(
                            "Requested frozen pair missing; no substitute date or revision"
                        )
                    primary = [min(reviews, key=lambda p: p["sequence"])]
                chosen = primary[0]
                if chosen["versions"] != versions or chosen["frozen_input_sha256"] != digest:
                    raise ValueError("Frozen input or version fingerprint mismatch")
                selected.append(chosen)
            matched.append((pair, *selected))
        result["matched_pairs"] = len(matched)
        issuers = len({p["ticker"] for p, _, _ in matched})
        holdout_dates = len({p["as_of"] for p, _, _ in matched if p["as_of"] in holdout})
        result["engineering_minimum"] = {
            "pairs": len(matched),
            "issuers": issuers,
            "holdout_dates": holdout_dates,
            "minimum": {"pairs": 4, "issuers": 2, "holdout_dates": 2},
            "met": len(matched) >= 4 and issuers >= 2 and holdout_dates >= 2,
        }
        result["coverage"] = {
            name: {
                "directional": sum(p[index]["directional"] for p in matched),
                "review_or_ineligible": sum(not p[index]["directional"] for p in matched),
            }
            for name, index in [("baseline", 1), ("current", 2)]
        }
        groups = {}
        missing = []
        for pair, left, right in matched:
            left_rows = [
                row for row in baseline["observations"] if row["decision_id"] == left["decision_id"]
            ]
            right_rows = [
                row for row in current["observations"] if row["decision_id"] == right["decision_id"]
            ]

            def key(row):
                return (
                    *row["horizon"],
                    row["benchmark"],
                    row["benchmark_alignment"],
                    row["exit_policy"],
                )

            left_map = {key(row): row for row in left_rows}
            right_map = {key(row): row for row in right_rows}
            if len(left_map) != len(left_rows) or len(right_map) != len(right_rows):
                raise ValueError("Duplicate horizon observations in one frozen publication")
            for horizon in left_map.keys() | right_map.keys():
                a, b = left_map.get(horizon), right_map.get(horizon)
                if (
                    not a
                    or not b
                    or (a["entry_date"], a["exit_date"]) != (b["entry_date"], b["exit_date"])
                ):
                    missing.append(
                        {
                            "ticker": pair["ticker"],
                            "as_of": pair["as_of"],
                            "horizon": list(horizon),
                            "reason": "Pending/ineligible or different policy/session windows; not paired",
                        }
                    )
                    continue
                if any(
                    abs(a[field] - b[field]) > 1e-9
                    for field in ("raw_return", "benchmark_return", "excess_return")
                ):
                    raise ValueError("Same frozen price window has conflicting outcomes")
                partition = "holdout" if pair["as_of"] in holdout else "development"
                groups.setdefault((partition, *horizon), []).append((a, b))
        for key, rows in sorted(groups.items(), key=lambda item: str(item[0])):
            directions = [(a, b) for a, b in rows if a["direction"] and b["direction"]]
            metrics = {}
            for name, index in [("baseline", 0), ("current", 1)]:
                scored = [pair[index] for pair in directions]
                metrics[name] = {
                    "n": len(rows),
                    "directional_paired_n": len(scored),
                    "directional_hit_rate": sum(
                        r["direction"] * r["excess_return"] > 0 for r in scored
                    )
                    / len(scored)
                    if scored
                    else None,
                    "excess_distribution": _distribution(
                        [pair[index]["excess_return"] for pair in rows]
                    ),
                }
            delta = (
                (
                    metrics["current"]["directional_hit_rate"]
                    - metrics["baseline"]["directional_hit_rate"]
                )
                if directions
                else None
            )
            result["comparisons"].append(
                {
                    "partition": key[0],
                    "horizon": list(key[1:3]),
                    "benchmark": key[3],
                    "benchmark_alignment": key[4],
                    "exit_policy": key[5],
                    **metrics,
                    "directional_hit_rate_delta": delta,
                }
            )
        result.update(
            status="available",
            unpaired_horizons=missing,
            integrity_coverage={
                "baseline": len(baseline.get("integrity_errors", [])),
                "current": len(current.get("integrity_errors", [])),
            },
        )
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        result["reasons"].append(str(exc))
        result["comparisons"] = []
    return result


def _compare_engineering_cells(baseline, current, protocol, development, holdout, result):
    """Deterministic extraction replay, explicitly without research publications."""
    import re

    cells = []
    for pair in protocol["pairs"]:
        if pair["as_of"] not in development | holdout or not re.fullmatch(
            "[0-9a-f]{64}", pair["frozen_input_sha256"]
        ):
            raise ValueError("Engineering pair outside frozen manifest")
        selected = []
        for name, report in [("baseline", baseline), ("current", current)]:
            versions = protocol[name + "_versions"]
            if set(versions) != {"code", "prompt", "schema"} or any(
                v is None or v == "" for v in versions.values()
            ):
                raise ValueError("Exact engineering code/prompt/schema fingerprints required")
            candidates = [
                row
                for row in report["engineering_cells"]
                if (row["ticker"], row["as_of"]) == (pair["ticker"], pair["as_of"])
            ]
            if len(candidates) != 1:
                raise ValueError("Missing or duplicate engineering pair; no best-of reruns")
            cell = candidates[0]
            if (
                cell["versions"] != versions
                or cell["frozen_input_sha256"] != pair["frozen_input_sha256"]
            ):
                raise ValueError("Engineering input/version fingerprint mismatch")
            if (
                cell["status"] not in {"available", "unavailable"}
                or type(cell["accepted_fact_count"]) is not int
                or cell["accepted_fact_count"] < 0
                or not isinstance(cell["invariant_violations"], list)
                or any(not isinstance(v, str) for v in cell["invariant_violations"])
                or not all(
                    re.fullmatch("[0-9a-f]{64}", cell[field])
                    for field in ("output_sha256", "repeat_output_sha256")
                )
            ):
                raise ValueError("Malformed engineering measurement")
            selected.append(cell)
        left, right = selected
        cells.append(
            {
                "ticker": pair["ticker"],
                "as_of": pair["as_of"],
                "partition": "holdout" if pair["as_of"] in holdout else "development",
                "baseline_status": left["status"],
                "current_status": right["status"],
                "accepted_fact_count_delta": right["accepted_fact_count"]
                - left["accepted_fact_count"],
                "baseline_output_sha256": left["output_sha256"],
                "current_output_sha256": right["output_sha256"],
                "reproducible": all(
                    row["output_sha256"] == row["repeat_output_sha256"] for row in selected
                ),
                "current_invariant_violations": right["invariant_violations"],
            }
        )
    issuers = len({row["ticker"] for row in cells})
    holdout_dates = len({row["as_of"] for row in cells if row["partition"] == "holdout"})
    result.update(
        status="available",
        matched_pairs=len(cells),
        engineering_cells=cells,
        reproducible=all(row["reproducible"] for row in cells),
        current_invariants_pass=all(not row["current_invariant_violations"] for row in cells),
        engineering_minimum={
            "pairs": len(cells),
            "issuers": issuers,
            "holdout_dates": holdout_dates,
            "minimum": {"pairs": 4, "issuers": 2, "holdout_dates": 2},
            "met": len(cells) >= 4 and issuers >= 2 and holdout_dates >= 2,
        },
        coverage={
            name: {
                "available": sum(row[name + "_status"] == "available" for row in cells),
                "unavailable": sum(row[name + "_status"] == "unavailable" for row in cells),
            }
            for name in ("baseline", "current")
        },
        metric_interpretation="Fact-count changes describe evidence visibility, not investment improvement; no opinion or outcome was synthesized.",
    )
    return result
