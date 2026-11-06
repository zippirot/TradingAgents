import hashlib
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

PILOT = Path(__file__).resolve().parents[1] / "docs/reviews/valuation-reference-proof-tools/pilot.py"
spec = importlib.util.spec_from_file_location("valuation_reference_pilot", PILOT)
pilot = importlib.util.module_from_spec(spec)

sys.modules[spec.name] = pilot
spec.loader.exec_module(pilot)


DOMAINS = ("sec_facts", "sec_filings", "prices_indicators", "consensus", "news_social",
           "default_peers", "memory", "prior_publication")


def fixture_manifest(tmp_path):
    files = {}
    for domain in DOMAINS:
        path = tmp_path / f"{domain}.json"
        path.write_text(json.dumps({"domain": domain, "as_of": "2026-11-05"}))
        files[domain] = {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"ticker": "DOCN", "analysis_date": "2026-11-05", "cutoff_utc": "2026-11-06T06:59:59+00:00",
            "depth": 2, "source_version": "abc123", "prompt_version": "def456",
            "analysts": ["market", "social", "news", "fundamentals"],
            "tool_limit": 4, "context_cap": 65536, "files": files,
            "reviewer": {"model_id": "reviewer/exact", "settings": {"temperature": 0, "max_tokens": 2048}}}


def fake_state():
    return {"trade_date": "2026-11-05", "company_of_interest": "DOCN",
            "shared_source_brief": "[V1] Revenue 100", "canonical_financial_context": "[F1] Revenue 100",
            "financial_calculations": [{"method": "ttm_revenue", "value": 100}],
            "valuation_reference_brief": "[V1] multiple 3", "market_report": "Market [V1]",
            "investment_plan": "Plan [V1]", "trader_investment_plan": "Trade [V1]",
            "final_trade_decision": "Decision [V1]", "advisory_audit": {"status": "bad"},
            "financial_claim_validation": {"raw_report": "```financial_claims\n[]\n```", "fact_ids": []},
            "disclosure_evidence": {"extraction": {"claims": [], "rejected": []}},
            "valuation_reference": {"peers": {"proposal": {"status": "available", "peers": []},
                                               "accepted": []}},
            "run_metrics": {"model_calls": 4, "debate_length": 100}}


@pytest.mark.unit
def test_manifest_rejects_missing_domain_and_changed_file(tmp_path):
    manifest = fixture_manifest(tmp_path)
    assert pilot.validate_manifest(manifest, tmp_path)
    bad = {**manifest, "files": {k: v for k, v in manifest["files"].items() if k != "news_social"}}
    with pytest.raises(ValueError, match="news_social"):
        pilot.validate_manifest(bad, tmp_path)
    (tmp_path / "consensus.json").write_text("changed")
    with pytest.raises(ValueError, match="consensus"):
        pilot.validate_manifest(manifest, tmp_path)


@pytest.mark.unit
def test_runner_requires_distinct_approved_budget_and_blocks_duplicate_launch(tmp_path):
    manifest = fixture_manifest(tmp_path)
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    with pytest.raises(ValueError, match="approved"):
        pilot.PilotRunner(manifest, tmp_path, ledger, approval=None)
    approval = pilot.Approval(approved_manifest_sha256=pilot.manifest_hash(manifest),
                              ceiling_usd="12.00", reviewer_model_id="reviewer/exact",
                              reviewer_max_calls=6)
    runner = pilot.PilotRunner(manifest, tmp_path, ledger, approval)
    with pytest.raises(RuntimeError, match="fixed A B B A A B order"):
        runner.run_slot(pilot.SLOTS[1], lambda s, guard: {})
    slot = pilot.SLOTS[0]
    def run(s, guard):
        ticket = guard.reserve(s.quick_model, "1.00", kind="run")
        guard.settle(ticket, "0.25")
        return {"state": fake_state(), "common_hash": pilot.manifest_hash(manifest),
                "request_hashes": {"peer:DOCN:AKAM": "a" * 64},
                "scope": {"ticker": "DOCN", "analysis_date": "2026-11-05", "depth": 2,
                          "analysts": manifest["analysts"], "tool_limit": 4, "context_cap": 65536,
                          "quick_model": s.quick_model, "deep_model": s.deep_model,
                          "llm_max_retries": 0},
                "memory_hash": manifest["files"]["memory"]["sha256"],
                "prior_publication_hash": manifest["files"]["prior_publication"]["sha256"],
                "model_calls": 1, "cost_usd": "0.25", "completed": True}
    result = runner.run_slot(slot, run)
    assert result["status"] == "complete"
    with pytest.raises(RuntimeError, match="already claimed"):
        runner.run_slot(slot, run)
    assert ledger.committed_usd() == pilot.Decimal("0.25")


@pytest.mark.unit
def test_budget_reservation_unknown_cost_remains_committed(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    guard = pilot.BudgetGuard(ledger, pilot.Decimal("1"), allowed_models={"openai/gpt-6.1-terra-pro"},
                              max_calls=1)
    guard.reserve("openai/gpt-6.1-terra-pro", "0.75", kind="run")
    with pytest.raises(RuntimeError, match="cap"):
        guard.reserve("openai/gpt-6.1-terra-pro", "0.50", kind="run")
    assert ledger.committed_usd() == pilot.Decimal("0.75")


@pytest.mark.unit
def test_blind_review_omits_model_and_internal_audit_but_keeps_evidence(tmp_path):
    runs = [{"slot": slot.name, "setup": slot.setup, "state": fake_state(), "status": "complete"}
            for slot in pilot.SLOTS]
    inputs, mapping = pilot.prepare_blinded_reviews(runs)
    assert len(inputs) == 6 and len(mapping) == 6
    assert set(mapping.values()) == {slot.name for slot in pilot.SLOTS}
    assert len({r["opaque_id"] for r in inputs}) == 6
    for item in inputs:
        dumped = json.dumps(item)
        assert "advisory_audit" not in dumped and "openai/gpt" not in dumped
        assert "[V1]" in dumped and "canonical_financial_context" in dumped
        assert "setup" not in dumped and "slot" not in dumped


@pytest.mark.unit
def test_summary_zero_submissions_failures_and_confounded_runs_have_no_ranking():
    runs = []
    for slot in pilot.SLOTS:
        state = fake_state()
        runs.append({"slot": slot.name, "setup": slot.setup, "state": state,
                     "status": "complete", "common_hash": "a" * 64,
                     "request_hashes": {"peer:DOCN:AKAM": "b" * 64},
                     "memory_hash": "c" * 64, "prior_publication_hash": "d" * 64,
                     "model_calls": 4, "cost_usd": "0.50", "review_score": 3})
    summary = pilot.summarize_runs(runs)
    assert summary["controlled_comparison"] is True
    assert summary["runs"][0]["financial_acceptance_rate"] == "N/A"
    assert summary["spreads"]["A"]["cost_usd"] == ["0.50", "0.50"]
    assert summary["winner"] is None
    runs[2]["common_hash"] = "e" * 64
    assert pilot.summarize_runs(runs)["controlled_comparison"] is False
    runs[2]["status"] = "failed"
    assert pilot.summarize_runs(runs)["controlled_comparison"] is False


@pytest.mark.unit
def test_run_scope_and_peer_replay_are_enforced(tmp_path):
    manifest = fixture_manifest(tmp_path)
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    approval = pilot.Approval(pilot.manifest_hash(manifest), "5", "reviewer/exact", 6)
    runner = pilot.PilotRunner(manifest, tmp_path, ledger, approval)
    def wrong_scope(slot, guard):
        ticket = guard.reserve(slot.quick_model, "1", kind="run")
        guard.settle(ticket, "0.2")
        return {"state": fake_state(), "common_hash": pilot.manifest_hash(manifest),
                "memory_hash": manifest["files"]["memory"]["sha256"],
                "prior_publication_hash": manifest["files"]["prior_publication"]["sha256"],
                "request_hashes": {"peer:DOCN:AKAM": "a" * 64},
                "scope": {"ticker": "AAPL", "analysis_date": "2026-11-05", "depth": 2,
                          "analysts": manifest["analysts"], "tool_limit": 4, "context_cap": 65536,
                          "quick_model": slot.quick_model, "deep_model": slot.deep_model,
                          "llm_max_retries": 0},
                "model_calls": 1, "cost_usd": "0.2", "completed": True}
    with pytest.raises(ValueError, match="scope"):
        runner.run_slot(pilot.SLOTS[0], wrong_scope)
    assert ledger.events()[-1]["status"] == "failed"


@pytest.mark.unit
def test_guard_call_limit_survives_recreation_and_failed_cost_keeps_reservation(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    one = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.A}, max_calls=1)
    one.reserve(pilot.A, "1", kind="run")
    later = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.A}, max_calls=1)
    with pytest.raises(RuntimeError, match="call cap"):
        later.reserve(pilot.A, "0.1", kind="run")
    assert ledger.committed_usd() == pilot.Decimal("1")


@pytest.mark.unit
def test_six_blind_reviews_use_fixed_model_and_durable_no_relaunch(tmp_path):
    manifest = fixture_manifest(tmp_path)
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    approval = pilot.Approval(pilot.manifest_hash(manifest), "6", "reviewer/exact", 6)
    runner = pilot.PilotRunner(manifest, tmp_path, ledger, approval)
    for slot in pilot.SLOTS:
        (tmp_path / f"{slot.name}.json").write_text(json.dumps(
            {"slot": slot.name, "setup": slot.setup, "state": fake_state(), "status": "complete"}))
    seen = []
    def review(payload, guard):
        assert "slot" not in json.dumps(payload) and "setup" not in json.dumps(payload)
        ticket = guard.reserve("reviewer/exact", "0.50", kind="review")
        guard.settle(ticket, "0.20")
        seen.append(payload["opaque_id"])
        return {"model_id": "reviewer/exact", "settings": manifest["reviewer"]["settings"],
                "score": 3, "findings": [], "cost_usd": "0.20"}
    scores = runner.run_reviews(review)
    assert len(scores) == len(seen) == 6
    assert {s["slot"] for s in scores} == {s.name for s in pilot.SLOTS}
    assert ledger.committed_usd() == pilot.Decimal("1.20")
    with pytest.raises(RuntimeError, match="already claimed"):
        runner.run_reviews(review)


@pytest.mark.unit
def test_gateway_replays_same_peer_bytes_across_runs_and_rejects_scope_drift(tmp_path):
    manifest = fixture_manifest(tmp_path)
    calls = []
    def capture(request):
        calls.append(request)
        return json.dumps({"ticker": request["ticker"], "filing": "2026-11-04"}).encode()
    root = tmp_path / "peers"
    first = pilot.FrozenSourceGateway(manifest, tmp_path, root, capture)
    data = first.peer("AKAM", manifest["cutoff_utc"])
    second = pilot.FrozenSourceGateway(manifest, tmp_path, root)
    assert second.peer("AKAM", manifest["cutoff_utc"]) == data
    assert first.request_hashes == second.request_hashes
    assert len(calls) == 1
    with pytest.raises(ValueError, match="scope"):
        second.peer("AKAM", "2026-11-07T00:00:00+00:00")
    with pytest.raises(ValueError, match="not captured"):
        second.peer("NET", manifest["cutoff_utc"])
    assert first.common("sec_facts") == (tmp_path / "sec_facts.json").read_bytes()


@pytest.mark.unit
def test_review_failure_retains_cost_and_does_not_relaunch(tmp_path):
    manifest = fixture_manifest(tmp_path)
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    approval = pilot.Approval(pilot.manifest_hash(manifest), "3", "reviewer/exact", 6)
    runner = pilot.PilotRunner(manifest, tmp_path, ledger, approval)
    for slot in pilot.SLOTS:
        (tmp_path / f"{slot.name}.json").write_text(json.dumps(
            {"slot": slot.name, "setup": slot.setup, "state": fake_state(), "status": "complete"}))
    def review(payload, guard):
        guard.reserve("reviewer/exact", "0.75", kind="review")
        raise TimeoutError("provider timeout after request")
    with pytest.raises(TimeoutError):
        runner.run_reviews(review)
    assert ledger.committed_usd() == pilot.Decimal("0.75")
    assert any(e.get("type") == "review_end" and e.get("status") == "failed" for e in ledger.events())
    with pytest.raises(RuntimeError, match="already claimed"):
        runner.run_reviews(review)


@pytest.mark.unit
def test_concurrent_reservations_cannot_cross_budget_or_request_cap(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    guard = pilot.BudgetGuard(ledger, pilot.Decimal("1"), allowed_models={pilot.A}, max_calls=4)
    def reserve(_):
        try:
            return guard.reserve(pilot.A, "0.30", kind="run")
        except RuntimeError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        tickets = list(pool.map(reserve, range(24)))
    assert sum(ticket is not None for ticket in tickets) == 3
    assert ledger.committed_usd() == pilot.Decimal("0.90")


@pytest.mark.unit
def test_separate_proof_phase_caps_share_one_aggregate_ledger(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "proof.jsonl")
    a = pilot.BudgetGuard(ledger, pilot.Decimal("10"), allowed_models={pilot.A},
                          max_calls=40, scope="proof:A", scope_ceiling=pilot.Decimal("5"))
    b = pilot.BudgetGuard(ledger, pilot.Decimal("10"), allowed_models={pilot.A},
                          max_calls=40, scope="proof:B", scope_ceiling=pilot.Decimal("5"))
    a.reserve(pilot.A, "4.9", kind="run")
    with pytest.raises(RuntimeError, match="scope cap"):
        a.reserve(pilot.A, "0.2", kind="run")
    b.reserve(pilot.A, "4.9", kind="run")
    assert ledger.committed_usd() == pilot.Decimal("9.8")


@pytest.mark.unit
def test_primary_metrics_use_real_structured_counts_and_reference_ids():
    state = fake_state()
    state["financial_claim_validation"] = {
        "raw_report": "```financial_claims\n[{\"fact_id\":\"f1\"},{\"fact_id\":\"f1\"},{\"fact_id\":\"bad\"}]\n```\n```disclosures\n[{\"source_id\":\"sec1\"},{\"bad\":1}]\n```",
        "fact_ids": ["f1"], "reasons": ["Claim 2: unavailable canonical fact"]}
    state["fundamentals_report"] = "Canonical checked facts only; raw extraction replaced"
    state["disclosure_evidence"] = {"extraction": {
        "claims": [{"source_id": "sec1"}], "rejected": ["record 1: malformed disclosure record"],
        "warnings": ["definition unavailable"]}}
    state["valuation_reference"] = {"proposal": {"peers": [{"ticker": "AKAM", "reason": "same"}]},
                                    "peers": {"accepted": [{"ticker": "AKAM"}]}}
    state["valuation_reference_brief"] = "Peer source_id sec:akam:2026 and fact f_rev_q3"
    state["investment_debate_state"] = {"bull_history": "The sec:akam:2026 valuation matters."}
    state["final_trade_decision"] = "Uses f_rev_q3."
    counts = pilot._counts(state)
    assert counts["financial_submitted"] == 3
    assert counts["financial_accepted"] == 1
    assert counts["financial_rejected"] == 1
    assert counts["financial_deduplicated"] == 1
    assert counts["disclosure_submitted"] == 2
    assert counts["disclosure_accepted"] == 1
    assert counts["disclosure_rejected"] == 1
    runs = [{"slot": slot.name, "setup": slot.setup, "status": "complete", "state": state,
             "common_hash": "a" * 64, "memory_hash": "b" * 64, "prior_publication_hash": "c" * 64,
             "request_hashes": {}, "model_calls": 4, "cost_usd": "1", "review_score": 3}
            for slot in pilot.SLOTS]
    row = pilot.summarize_runs(runs)["runs"][0]
    assert row["valid_peer_proposed"] is True
    assert row["valid_debate_citation_count"] == 1
    assert row["valid_decision_citation_count"] == 1


@pytest.mark.unit
def test_structural_extraction_failure_is_unavailable_not_one_rejection():
    state = fake_state()
    state["financial_claim_validation"] = {"raw_report": "bad", "fact_ids": [],
                                            "reasons": ["Missing, duplicate or oversized material financial claim extraction"]}
    state["fundamentals_report"] = "bad"
    state["disclosure_evidence"] = {"extraction": {"claims": [],
        "rejected": ["Missing, duplicate or oversized disclosure extraction"]}}
    counts = pilot._counts(state)
    assert counts["financial_submitted"] is None and counts["financial_acceptance_rate"] == "N/A"
    assert counts["disclosure_submitted"] is None and counts["disclosure_rejected"] is None


@pytest.mark.unit
def test_blind_review_marks_truncation_and_strips_audit_section():
    state = fake_state()
    state["final_trade_decision"] = "# Decision\nUse [V1].\n## Advisory audit findings\nAudit found three errors.\n## Thesis\n" + "x" * 19000
    runs = [{"slot": slot.name, "setup": slot.setup, "status": "complete", "state": state}
            for slot in pilot.SLOTS]
    inputs, _ = pilot.prepare_blinded_reviews(runs)
    assert all("final_trade_decision" in item["truncations"] for item in inputs)
    assert all("Audit found" not in item["analysis"]["final_trade_decision"] for item in inputs)
    assert all("[Reviewer field truncated" in item["analysis"]["final_trade_decision"] for item in inputs)


@pytest.mark.unit
def test_saved_publication_canonical_labels_do_not_count_as_model_citations():
    state = fake_state()
    state["valuation_reference_brief"] = "Peer source_id sec:akam:2026 and fact f_rev_q3"
    state["investment_debate_state"] = {"bull_history": "Canonical source_id sec:akam:2026"}
    state["investment_plan"] = "Canonical fact f_rev_q3"
    state["trader_investment_plan"] = "Canonical fact f_rev_q3"
    state["final_trade_decision"] = "Canonical fact f_rev_q3"
    state["financial_claim_validation"]["raw_report"] = "Original fundamentals without citation"
    state["unvalidated_outputs"] = {
        "investment_debate_state": {"bull_history": "Original bull argument without citation"},
        "risk_debate_state": {"history": "Original risk argument without citation"},
        "investment_plan": "Original manager plan without citation",
        "trader_investment_plan": "Original trader proposal without citation",
        "final_trade_decision": "Original portfolio decision without citation",
    }
    runs = [{"slot": slot.name, "setup": slot.setup, "status": "complete", "state": state,
             "common_hash": "a" * 64, "memory_hash": "b" * 64, "prior_publication_hash": "c" * 64,
             "request_hashes": {}, "model_calls": 4, "cost_usd": "1", "review_score": 3}
            for slot in pilot.SLOTS]
    row = pilot.summarize_runs(runs)["runs"][0]
    assert row["valid_debate_citation_count"] == 0
    assert row["valid_decision_citation_count"] == 0
    inputs, _ = pilot.prepare_blinded_reviews(runs)
    for item in inputs:
        assert "Original manager plan" in item["analysis"]["investment_plan"]
        assert "Original trader proposal" in item["analysis"]["trader_investment_plan"]
        assert "Original portfolio decision" in item["analysis"]["final_trade_decision"]
        assert "Canonical fact f_rev_q3" not in str(item["analysis"])
        assert "Original bull argument" in str(item["debates"])
        assert "Original fundamentals" in item["analysis"]["fundamentals_report"]
