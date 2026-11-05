"""Read-only publication evaluation distinguishes horizons, attempts and known-at time."""

from copy import deepcopy
from datetime import datetime
from uuid import uuid4

import pytest

from tradingagents import backtest
from tradingagents.memory import publication, publication_outcomes as outcomes


def publish(
    config, monkeypatch, ticker="DOCN", day="2026-01-01", rating="Buy", mode="prospective", **extra
):
    monkeypatch.setattr(
        publication, "_utcnow", lambda: datetime.fromisoformat(day + "T22:00:00+00:00")
    )
    monkeypatch.setattr(publication, "get_current_date", lambda: day)
    state = {
        "run_id": str(uuid4()),
        "final_rating": rating,
        "final_trade_decision": "Canonical research",
        "evidence_quality": {"status": "limited" if rating != "REVIEW" else "insufficient"},
        "evaluation_mode": mode,
        "publication_versions": {"code": "code-v1", "prompt": "prompt-v1", "schema": 1},
        **extra,
    }
    return publication.publish(config, state, ticker, day)


def resolve(
    config, record, name="5_sessions", *, alpha=0.03, resolved_at="2026-02-01T00:00:00+00:00"
):
    companion = outcomes.load_outcomes(config, record)
    endpoint = companion["endpoints"][name]
    outcome = {
        "ticker": record["ticker"],
        "benchmark": endpoint["benchmark"],
        "holding_days": endpoint["holding_days"],
        "entry": {"date": "2026-01-02", "price": 100.0},
        "exit": {"date": "2026-01-09", "price": (1 + 0.02 + alpha) * 100},
        "benchmark_entry": {"date": "2026-01-02", "price": 100.0},
        "benchmark_exit": {"date": "2026-01-09", "price": 102.0},
        "raw_return": 0.02 + alpha,
        "benchmark_return": 0.02,
        "alpha_return": alpha,
        "resolution_date": "2026-01-09",
        "price_source": "frozen fixture",
        "price_adjustment": "adjusted close",
        "horizon_type": endpoint.get("horizon_type", "trading_sessions"),
        "calendar_months": None,
        "nominal_exit_date": None,
        "benchmark_alignment": endpoint.get("benchmark_alignment", "asof"),
        "exit_policy": endpoint.get("exit_policy", "nth_session_after_entry"),
    }
    companion["endpoints"][name] = {
        **endpoint,
        "status": "resolved",
        "resolved_at": resolved_at,
        "outcome": outcome,
    }
    (publication.record_root(config) / "outcomes").mkdir(exist_ok=True)
    outcomes._write(
        publication.record_root(config) / "outcomes" / f"{record['decision_id']}.json", companion
    )


def test_primary_revision_review_pending_and_known_at_are_separate(tmp_path, monkeypatch):
    config = {"results_dir": str(tmp_path), "benchmark_ticker": "SPY"}
    primary = publish(config, monkeypatch)
    publish(config, monkeypatch, rating="Sell")
    publish(config, monkeypatch, ticker="NVDA", rating="REVIEW")
    resolve(config, primary)
    early = backtest.evaluate_publications(config, "2026-01-15T00:00:00Z")
    assert early["coverage"]["publications"] == 3 and early["coverage"]["primary"] == 1
    assert early["coverage"]["revisions"] == 1 and early["coverage"]["review_or_ineligible"] == 1
    assert all(group["resolved"] == 0 for group in early["groups"])
    report = backtest.evaluate_publications(config, "2026-03-01T00:00:00Z")
    short = next(group for group in report["groups"] if group["horizon"] == ["trading_sessions", 5])
    assert short["resolved"] == 1 and short["directional_excess_hit_rate"] == 1
    assert short["distributions"]["excess"]["mean"] == pytest.approx(0.03)
    assert short["sample_adequacy"]["met"] is False
    assert "not a portfolio" in backtest.render_publication_evaluation(report)
    assert "3 calendar months" in backtest.render_publication_evaluation(report)


def test_hold_and_corrupt_records_are_not_directional_successes(tmp_path, monkeypatch):
    config = {"results_dir": str(tmp_path), "benchmark_ticker": "SPY"}
    record = publish(config, monkeypatch, rating="Hold")
    resolve(config, record)
    report = backtest.evaluate_publications(config, "2026-03-01")
    short = next(group for group in report["groups"] if group["horizon"] == ["trading_sessions", 5])
    assert short["directional_excess_hit_rate"] is None and short["directional_n"] == 0
    path = publication.record_root(config) / "outcomes" / f"{record['decision_id']}.json"
    path.write_text("{}")
    before = path.read_bytes()
    damaged = backtest.evaluate_publications(config, "2026-03-01")
    assert damaged["integrity_errors"] and not damaged["observations"]
    assert path.read_bytes() == before


def test_historical_and_prospective_observations_never_pool(tmp_path, monkeypatch):
    config = {"results_dir": str(tmp_path), "benchmark_ticker": "SPY"}
    first = publish(config, monkeypatch)
    second = publish(config, monkeypatch, ticker="NVDA", mode="historical")
    resolve(config, first)
    resolve(config, second, alpha=-0.02)
    report = backtest.evaluate_publications(config, "2026-03-01")
    assert {g["evaluation_mode"] for g in report["groups"]} == {"historical", "prospective"}
    assert all(g["resolved"] <= 1 for g in report["groups"])


def frozen_reports():
    baseline = {"publications": [], "observations": []}
    current = deepcopy(baseline)
    protocol = {
        "schema_version": 1,
        "evaluation_mode": "historical",
        "development_dates": ["2025-01-01"],
        "holdout_dates": ["2025-02-01", "2025-03-01"],
        "baseline_versions": {"code": "base", "prompt": "base-p", "schema": 1},
        "current_versions": {"code": "current", "prompt": "current-p", "schema": 1},
        "pairs": [],
    }
    for index, (ticker, day) in enumerate(
        [
            ("DOCN", "2025-01-01"),
            ("NVDA", "2025-02-01"),
            ("DOCN", "2025-03-01"),
            ("NVDA", "2025-03-01"),
        ]
    ):
        digest = str(index) * 64
        protocol["pairs"].append({"ticker": ticker, "as_of": day, "frozen_input_sha256": digest})
        for report, version, direction in [(baseline, "baseline", 1), (current, "current", -1)]:
            publication = {
                "decision_id": f"{version}-{index}",
                "ticker": ticker,
                "as_of": day,
                "sequence": index,
                "primary": True,
                "directional": True,
                "evaluation_mode": "historical",
                "versions": protocol[version + "_versions"],
                "frozen_input_sha256": digest,
            }
            report["publications"].append(publication)
            report["observations"].append(
                {
                    **publication,
                    "horizon": ["trading_sessions", 5],
                    "benchmark": "SPY",
                    "benchmark_alignment": "exact_sessions",
                    "exit_policy": "nth_session_after_entry",
                    "entry_date": day,
                    "exit_date": day,
                    "direction": direction,
                    "excess_return": -0.03,
                    "raw_return": -0.01,
                    "benchmark_return": 0.02,
                }
            )
    return baseline, current, protocol


def test_frozen_pairing_requires_identity_disjoint_dates_and_versions():
    baseline, current, protocol = frozen_reports()
    result = backtest.compare_frozen_publication_evaluations(baseline, current, protocol)
    assert result["engineering_minimum"]["met"] and result["matched_pairs"] == 4
    assert result["comparisons"][0]["directional_hit_rate_delta"] == 1
    assert result["performance_claim"] == "unproven"
    for fault in ("overlap", "hash", "version", "duplicate"):
        a, b, p = deepcopy(baseline), deepcopy(current), deepcopy(protocol)
        if fault == "overlap":
            p["development_dates"].append("2025-02-01")
        elif fault == "hash":
            b["publications"][0]["frozen_input_sha256"] = "f" * 64
        elif fault == "version":
            b["publications"][0]["versions"]["code"] = "other"
        else:
            p["pairs"].append(deepcopy(p["pairs"][0]))
        result = backtest.compare_frozen_publication_evaluations(a, b, p)
        assert result["status"] == "unavailable" and result["reasons"]


def forecast_publications(tmp_path, monkeypatch, *, actual_changes=None):
    from tests.test_valuation import ev_request, evidence
    from tradingagents.agents.valuation import validate_target

    config = {"results_dir": str(tmp_path), "benchmark_ticker": "SPY"}
    package = evidence()
    low = ev_request()
    high = ev_request()
    high["scenarios"][0]["forecast"]["value"] = "1400"
    rows = [
        {
            "name": name,
            "request": request,
            "result": validate_target(request, package).model_dump(mode="json"),
        }
        for name, request in [("low", low), ("high", high)]
    ]
    first = publish(
        config,
        monkeypatch,
        day="2026-10-19",
        financial_evidence=package.model_dump(mode="json"),
        shared_valuation_scenarios={"rows": rows, "status": "available"},
    )
    source = package.sources[0].model_copy(
        update={"filed_date": __import__("datetime").date(2028, 2, 1)}
    )
    fact = package.facts[0].model_copy(
        update={
            "period_start": __import__("datetime").date(2027, 1, 1),
            "period_end": __import__("datetime").date(2027, 12, 31),
            "as_of": __import__("datetime").date(2028, 2, 2),
            "value": __import__("decimal").Decimal("1300"),
            **(actual_changes or {}),
        }
    )
    actual = package.model_copy(
        update={
            "as_of": __import__("datetime").date(2028, 2, 2),
            "sources": (source,),
            "facts": (fact,),
        }
    )
    later = publish(
        config, monkeypatch, day="2028-02-02", financial_evidence=actual.model_dump(mode="json")
    )
    return config, first, later


def test_forecast_error_and_scenario_envelope_require_known_later_actual(tmp_path, monkeypatch):
    config, first, later = forecast_publications(tmp_path, monkeypatch)
    pending = backtest.evaluate_publications(config, "2027-12-31")["forecast_evaluation"]
    assert pending["pending"] == 1 and pending["resolved"] == 0
    result = backtest.evaluate_publications(config, "2028-03-01")["forecast_evaluation"]
    assert result["resolved"] == 1
    row = result["rows"][0]
    assert (
        row["actual_publication_id"] == later["decision_id"]
        and row["decision_id"] == first["decision_id"]
    )
    assert [r["error"] for r in row["errors"]] == ["-100", "100"]
    assert row["scenario_envelope"]["covered"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"unit": "EUR"},
        {"basis": "management-adjusted"},
        {"origin": "derived", "formula_id": "untrusted", "input_fact_ids": ("missing",)},
    ],
)
def test_incompatible_actual_cannot_settle_forecast(tmp_path, monkeypatch, change):
    config, _, _ = forecast_publications(tmp_path, monkeypatch, actual_changes=change)
    result = backtest.evaluate_publications(config, "2028-03-01")["forecast_evaluation"]
    assert result["pending"] == 1 and result["resolved"] == 0


def test_existing_attempt_markers_count_failures_not_extra_investment_samples(tmp_path):
    import json

    config = {"results_dir": str(tmp_path)}
    path = tmp_path / "DOCN" / "2026-01-01" / "message_tool.log"
    path.parent.mkdir(parents=True)
    common = {"schema_version": 1, "ticker": "DOCN", "requested_as_of": "2026-01-01"}
    first, second = str(uuid4()), str(uuid4())
    rows = [
        {**common, "attempt_id": first, "event": "started", "recorded_at": "2026-01-01T20:00:00Z"},
        {
            **common,
            "attempt_id": first,
            "event": "failed",
            "recorded_at": "2026-01-01T21:00:00Z",
            "error_type": "RuntimeError",
        },
        {**common, "attempt_id": second, "event": "started", "recorded_at": "2026-01-02T20:00:00Z"},
        {
            **common,
            "attempt_id": second,
            "event": "completed",
            "recorded_at": "2026-01-02T21:00:00Z",
        },
    ]
    path.write_text("\n".join("[Evaluation Attempt] " + json.dumps(row) for row in rows))
    report = backtest.evaluate_publications(config, "2026-01-02T20:30:00Z")
    assert report["attempts"]["started"] == 2 and report["attempts"]["failed"] == 1
    assert report["attempts"]["in_progress"] == 1 and report["coverage"]["publications"] == 0
    path.write_text(path.read_text() + "\n[Evaluation Attempt] {bad")
    assert backtest.evaluate_publications(config, "2026-01-03")["attempts"]["errors"]


def test_legacy_summary_keeps_existing_values_and_adds_publication_view(tmp_path, monkeypatch):
    config = {"results_dir": str(tmp_path), "benchmark_ticker": "SPY"}
    publish(config, monkeypatch)
    path = tmp_path / "trading_memory.md"
    path.write_text("")
    summary = backtest.summarize(path)
    assert summary.resolved == 0 and summary.publication_evaluation["coverage"]["publications"] == 1
    assert "Versioned publication evaluation" in summary.render()


def test_frozen_engineering_cells_compare_without_inventing_opinions_or_outcomes():
    _, _, protocol = frozen_reports()
    baseline = {"engineering_cells": []}
    current = {"engineering_cells": []}
    for pair in protocol["pairs"]:
        for name, report, count in [("baseline", baseline, 5), ("current", current, 7)]:
            report["engineering_cells"].append(
                {
                    **pair,
                    "versions": protocol[name + "_versions"],
                    "status": "available",
                    "accepted_fact_count": count,
                    "output_sha256": "a" * 64,
                    "repeat_output_sha256": "a" * 64,
                    "invariant_violations": [],
                }
            )
    result = backtest.compare_frozen_publication_evaluations(baseline, current, protocol)
    assert result["status"] == "available" and result["engineering_minimum"]["met"]
    assert result["reproducible"] and result["current_invariants_pass"]
    assert result["engineering_cells"][0]["accepted_fact_count_delta"] == 2
    assert result["comparisons"] == [] and result["performance_claim"] == "unproven"
    current["engineering_cells"][0]["repeat_output_sha256"] = "b" * 64
    result = backtest.compare_frozen_publication_evaluations(baseline, current, protocol)
    assert not result["reproducible"]


def test_attempt_timestamp_validation_and_mixed_offsets(tmp_path):
    import json

    path = tmp_path / "DOCN" / "2026-01-01" / "message_tool.log"
    path.parent.mkdir(parents=True)
    common = {
        "schema_version": 1,
        "ticker": "DOCN",
        "requested_as_of": "2026-01-01",
        "attempt_id": str(uuid4()),
    }
    rows = [
        {**common, "event": "started", "recorded_at": "2026-01-01T22:00:00+02:00"},
        {**common, "event": "failed", "recorded_at": "2026-01-01T19:00:00-02:00"},
        {**common, "attempt_id": str(uuid4()), "event": "started", "recorded_at": None},
    ]
    path.write_text("\n".join("[Evaluation Attempt] " + json.dumps(row) for row in rows))
    report = backtest.evaluate_publications({"results_dir": str(tmp_path)}, "2026-01-02")
    assert report["attempts"]["failed"] == 1
    assert report["attempts"]["failure_rate"] == 1
    assert (
        report["attempts"]["errors"]
        and report["attempts"]["coverage_completeness"] == "partial_or_legacy_unknown"
    )
