"""Offline guards for the future document-access proof; no network or credentials."""
import dataclasses
import hashlib
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.test_valuation_reference_live_adapter import Request, live_adapter, pilot

HARNESS = Path(__file__).resolve().parents[1] / "docs/reviews/document-access-proof-tools/live_cli.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("document_access_proof", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def approval(tmp_path):
    old = tmp_path / "old.jsonl"
    old_ledger = pilot.PilotLedger(old)
    old_ledger.append({"type": "reserve", "ticket": "unknown", "usd": "2.5",
                       "scope": "proof:Build1", "model": pilot.A, "kind": "run"})
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    now = datetime.now(UTC)
    # Known completed Wednesday regular session. Only account/endpoint
    # freshness follows the process clock in these synthetic receipts.
    completed_close = datetime(2026, 11, 4, 21, tzinfo=UTC)
    session_date = completed_close.date().isoformat()
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir()
    pricing = {"prompt": "0.000001", "completion": "0.000005",
               "input_cache_read": "0", "input_cache_write": "0"}
    metadata_rates = {model: {
        "input_per_token": pricing["prompt"], "output_per_token": pricing["completion"],
        "cache_read_per_token": "0", "cache_write_per_token": "0",
    } for model in (pilot.A, pilot.B_DEEP)}
    for index, ticker in enumerate(("DOCN", "MSFT", "CAT")):
        metadata = {
            "observed_at": (now - timedelta(seconds=3-index)).isoformat(),
            "results": {
                pilot.A: {"endpoints": [{"name": pilot.A, "pricing": pricing}]},
                pilot.B_DEEP: {"endpoints": [{"name": pilot.B_DEEP, "pricing": pricing}]},
                "key": {"limit_remaining": "100"},
            },
        }
        (receipt_root / f"{ticker}.json").write_text(json.dumps(metadata))
    return {
        "approval_id": "fresh-document-access", "approved_at_recorded": now.isoformat(),
        "user_instruction": "Explicit fresh approval fixture", "phase": "DocumentAccess",
        "attempts": 3, "tickers": ["DOCN", "MSFT", "CAT"],
        "analysis_date": session_date,
        "quick_model": pilot.B_DEEP, "deep_model": pilot.A, "depth": 3,
        "max_output_tokens": 16384, "max_tool_rounds": 4,
        "analysts": ["market", "social", "news", "fundamentals"],
        "llm_max_retries": 0, "audit_max_attempts": 2,
        "candidate_head": "a" * 40, "worktree_root": str(candidate),
        "repository_origin": "https://example.invalid/repo.git",
        "ledger_path": str(tmp_path / "new.jsonl"),
        "machine": {"cpu": "Apple M1 Pro", "ram_bytes": 17179869184},
        "ceiling_usd": "12", "per_attempt_ceiling_usd": "4",
        "max_calls_per_attempt": 60,
        "old_ledgers": {str(old): hashlib.sha256(old.read_bytes()).hexdigest()},
        "prior_committed_exposure_usd": "2.5", "prior_unknown_reserved_usd": "2.5",
        "runner_sha256": "b" * 64, "provider_metadata_sha256": "c" * 64,
        "candidate_sha256": "d" * 64,
        "receipt_refresh_policy": "per_attempt_local_receipt_v1",
        "receipt_root": str(receipt_root),
        "approved_route_rate_caps": metadata_rates,
        "resolved_model_ids": {pilot.A: [pilot.A], pilot.B_DEEP: [pilot.B_DEEP]},
        "session": {"session_date": session_date,
                    "regular_close_utc": completed_close.isoformat()},
    }


def test_candidate_gate_requires_clean_document_b_branch(monkeypatch):
    harness = load_harness()
    environment = {"branch": "codex/document-access-a", "clean": True}
    monkeypatch.setattr(harness, "assert_environment", lambda: environment)
    read_calls = []

    class CandidateInputReached(Exception):
        pass

    def read_input(_path):
        read_calls.append(True)
        raise CandidateInputReached

    monkeypatch.setattr(harness, "read_json", read_input)
    with pytest.raises(RuntimeError, match="clean committed B candidate"):
        harness._candidate_and_approval("DOCN")
    assert not read_calls
    environment["branch"] = "codex/document-access-b"
    environment["clean"] = False
    with pytest.raises(RuntimeError, match="clean committed B candidate"):
        harness._candidate_and_approval("DOCN")
    assert not read_calls
    environment["clean"] = True
    with pytest.raises(CandidateInputReached):
        harness._candidate_and_approval("DOCN")
    assert len(read_calls) == 1


def test_document_spec_is_exact_and_old_depth_scope_stays_closed():
    spec = live_adapter.CliSpec(
        "DOCN", "2026-11-06", pilot.B_DEEP, pilot.A, 3, 16384,
        max_tool_rounds=4, proof_scope=live_adapter.DOCUMENT_PROOF_SCOPE,
    )
    spec.validate()
    for changed in (
        {"ticker": "AAPL"}, {"depth": 2}, {"max_output_tokens": 8192},
        {"max_tool_rounds": 5}, {"quick_model": pilot.A},
        {"proof_scope": None},
    ):
        with pytest.raises(ValueError):
            dataclasses.replace(spec, **changed).validate()


def test_three_unique_claims_preserve_old_unknown_hold_without_stacking(tmp_path):
    record = approval(tmp_path)
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    for ticker in ("DOCN", "MSFT", "CAT"):
        digest = live_adapter.claim_document_access_proof(ledger, record, ticker)
        assert digest == live_adapter.manifest_hash(record)
    assert sum(event["type"] == "attempt_claim" for event in ledger.events()) == 3
    assert ledger.events()[0]["prior_unknown_reserved_usd"] == "2.5"
    assert ledger.committed_usd() == 0
    with pytest.raises(RuntimeError):
        live_adapter.claim_document_access_proof(ledger, record, "DOCN")
    with pytest.raises(ValueError, match="fresh ledger"):
        live_adapter.claim_document_access_proof(
            pilot.PilotLedger(tmp_path / "another.jsonl"), record, "DOCN"
        )
    record["old_ledgers"][next(iter(record["old_ledgers"]))] = "0" * 64
    with pytest.raises(ValueError):
        live_adapter.claim_document_access_proof(pilot.PilotLedger(tmp_path / "another.jsonl"), record, "DOCN")


def amended_cat_record(tmp_path):
    original = approval(tmp_path)
    original["ceiling_usd"] = "72"
    original["per_attempt_ceiling_usd"] = "24"
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    for ticker in ("DOCN", "MSFT"):
        live_adapter.claim_document_access_proof(ledger, original, ticker)
        ledger.append({"type": "execution_start", "name": f"DocumentAccess-{ticker}", "ticker": ticker})
        ledger.append({"type": "attempt_failed_start", "ticker": ticker})
    archived = tmp_path / "original-approval.json"
    archived.write_text(json.dumps(original))
    prefix = ledger.path.read_bytes()
    amended = {**original, "approval_id": "fresh-CAT-only", "candidate_head": "b" * 40}
    amended["final_slot_amendment"] = {
        "schema_version": 1, "ticker": "CAT",
        "original_approval_path": str(archived),
        "original_approval_sha256": hashlib.sha256(archived.read_bytes()).hexdigest(),
        "original_approval_digest": live_adapter.manifest_hash(original),
        "ledger_prefix_bytes": len(prefix),
        "ledger_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
    }
    return original, amended, ledger, archived


def test_cat_final_slot_amendment_preserves_original_allowance_and_claims(tmp_path):
    original, amended, ledger, archived = amended_cat_record(tmp_path)
    digest = live_adapter.claim_document_access_proof(ledger, amended, "CAT")
    events = ledger.events()
    assert digest == live_adapter.manifest_hash(amended)
    assert len([e for e in events if e["type"] == "allowance"]) == 1
    assert [e["ticker"] for e in events if e["type"] == "attempt_claim"] == ["DOCN", "MSFT", "CAT"]
    assert [e["approval_sha256"] for e in events if e["type"] == "attempt_claim"] == [
        live_adapter.manifest_hash(original), live_adapter.manifest_hash(original), digest,
    ]
    assert sum(e["type"] == "final_slot_amendment" for e in events) == 1
    spec = live_adapter.CliSpec(
        "CAT", amended["analysis_date"], pilot.B_DEEP, pilot.A, 3, 16384,
        max_tool_rounds=4, proof_scope=live_adapter.DOCUMENT_PROOF_SCOPE,
    )
    live_adapter.verify_execution_claim(
        live_adapter.ExecutionClaim("proof", "DocumentAccess-CAT", digest), ledger, spec,
    )
    with pytest.raises((ValueError, RuntimeError)):
        live_adapter.claim_document_access_proof(ledger, amended, "CAT")
    with pytest.raises((ValueError, RuntimeError)):
        live_adapter.claim_document_access_proof(ledger, amended, "DOCN")
    archived.write_text(archived.read_text() + " ")
    with pytest.raises(ValueError, match="original approval bytes changed"):
        live_adapter.verify_execution_claim(
            live_adapter.ExecutionClaim("proof", "DocumentAccess-CAT", digest), ledger, spec,
        )


def test_cat_amendment_rejects_budget_mutation_and_advanced_prefix(tmp_path):
    _, amended, ledger, _ = amended_cat_record(tmp_path)
    changed = {**amended, "ceiling_usd": "73"}
    with pytest.raises(ValueError, match="budget or original scope"):
        live_adapter.claim_document_access_proof(ledger, changed, "CAT")
    changed = {**amended, "max_calls_per_attempt": 61}
    with pytest.raises(ValueError, match="budget or original scope"):
        live_adapter.claim_document_access_proof(ledger, changed, "CAT")
    ledger.append({"type": "unexpected"})
    with pytest.raises(ValueError, match="advanced before claim"):
        live_adapter.claim_document_access_proof(ledger, amended, "CAT")
    assert len([e for e in ledger.events() if e["type"] == "allowance"]) == 1
    assert len([e for e in ledger.events() if e["type"] == "attempt_claim"]) == 2


def test_cat_draft_never_creates_authority_or_claim(tmp_path, monkeypatch):
    import sys

    harness = load_harness()
    monkeypatch.setitem(sys.modules, "live_cli", harness)
    source = HARNESS.with_name("draft_final_slot.py")
    spec = importlib.util.spec_from_file_location("cat_draft", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original, _, ledger, archived = amended_cat_record(tmp_path)
    candidate_source = tmp_path / "old-candidate.json"
    candidate_source.write_text(json.dumps({"analysis_date": original["analysis_date"]}))
    metadata_path = Path(original["receipt_root"]) / "CAT.json"
    monkeypatch.setattr(harness, "CANDIDATE", candidate_source)
    monkeypatch.setattr(harness, "LEDGER", ledger.path)
    monkeypatch.setattr(harness, "assert_environment", lambda: {
        "branch": "codex/document-access-b", "clean": True,
        "head": "b" * 40, "modules": {},
    })
    monkeypatch.setattr(harness, "prior_ledger_snapshot", lambda: {
        key: original[key] for key in (
            "old_ledgers", "prior_committed_exposure_usd", "prior_unknown_reserved_usd"
        )
    })
    before = ledger.path.read_bytes()
    candidate_path, approval_path = module.draft(
        archived, metadata_path, tmp_path / "drafts",
    )
    candidate = json.loads(candidate_path.read_text())
    approval_draft = json.loads(approval_path.read_text())
    assert candidate["head"] == "b" * 40
    assert approval_draft["candidate_sha256"] == hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    assert approval_draft["approval_id"] == approval_draft["user_instruction"] == ""
    with pytest.raises(ValueError):
        live_adapter._validate_document_access_approval(approval_draft)
    assert ledger.path.read_bytes() == before
    with pytest.raises(FileExistsError):
        module.draft(archived, metadata_path, tmp_path / "drafts")


def test_document_price_accepts_canonical_postclose_missing_close_only(monkeypatch):
    from copy import deepcopy

    from tests.test_price_observation import install
    from tradingagents.dataflows.vendors.yahoo import price_observation as prices

    install(monkeypatch, now="2026-11-04T22:00:00+00:00", closes=(84, None))
    price = prices.get_price_observation("DOCN", "2026-11-04")
    spec = live_adapter.CliSpec(
        "DOCN", "2026-11-04", pilot.B_DEEP, pilot.A, 3, 16384,
        max_tool_rounds=4, proof_scope=live_adapter.DOCUMENT_PROOF_SCOPE,
    )
    record = {"session": {"regular_close_utc": "2026-11-04T21:00:00+00:00"}}
    verified = live_adapter.verify_document_access_completed_state(
        {"price_observation": price}, spec, record,
    )
    assert verified["selected_session_date"] == "2026-11-03"
    assert verified["requested_session_date"] == "2026-11-04"
    assert verified["price_fallback"]["missing_completed_session_dates"] == ["2026-11-04"]
    changed = deepcopy(price)
    changed["price_fallback"]["reason"] = "unexplained"
    with pytest.raises(ValueError):
        live_adapter.verify_document_access_completed_state({"price_observation": changed}, spec, record)
    changed = deepcopy(price)
    changed.pop("price_fallback")
    with pytest.raises(ValueError):
        live_adapter.verify_document_access_completed_state({"price_observation": changed}, spec, record)
    changed = deepcopy(price)
    changed["raw_source"]["bars"][-1]["close"] = "85"
    with pytest.raises(ValueError):
        live_adapter.verify_document_access_completed_state({"price_observation": changed}, spec, record)
    with pytest.raises(RuntimeError, match="post-close"):
        live_adapter.verify_document_access_completed_state(
            {"price_observation": price}, spec,
            {"session": {"regular_close_utc": "2026-11-04T23:00:00+00:00"}},
        )
    with pytest.raises(ValueError):
        live_adapter.verify_document_access_completed_state(
            {"price_observation": price},
            dataclasses.replace(spec, ticker="MSFT"), record,
        )
    changed = deepcopy(price)
    changed["raw_source"]["bars"][-1]["timestamp"] = "2026-11-05T16:00:00-05:00"
    with pytest.raises(ValueError):
        live_adapter.verify_document_access_completed_state(
            {"price_observation": changed}, spec, record,
        )
    install(monkeypatch, now="2026-11-04T20:00:00+00:00", closes=(84, None))
    partial = prices.get_price_observation("DOCN", "2026-11-04")
    with pytest.raises(RuntimeError, match="post-close"):
        live_adapter.verify_document_access_completed_state(
            {"price_observation": partial}, spec, record,
        )


def test_document_wire_scope_serializes_and_keeps_unknown_reservation(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "wire.jsonl")
    budget = pilot.BudgetGuard(
        ledger, pilot.Decimal("12"), allowed_models={pilot.A, pilot.B_DEEP},
        max_calls=1, scope="proof:DocumentAccess:DOCN", allowed_kinds={"run"},
        scope_ceiling=pilot.Decimal("4"),
    )
    rates = {model: {
        "input_per_token": "0", "output_per_token": "0.0001",
        "cache_read_per_token": "0", "cache_write_per_token": "0",
    } for model in (pilot.A, pilot.B_DEEP)}
    wire = live_adapter.OpenRouterWireGuard(
        budget, rates, max_output_tokens=16384, kind="run",
        allowed_resolved_models={model: {model} for model in rates},
        serialize_paid_requests=True,
    )
    ticket = wire.before(Request({"model": pilot.A, "max_tokens": 16384, "messages": []}))
    wire.failed(ticket, TimeoutError())
    assert ledger.committed_usd() > 0
    with pytest.raises(live_adapter.BudgetStoppedError):
        wire.before(Request({"model": pilot.A, "max_tokens": 16384, "messages": []}))


def test_offline_qualification_and_run_gate_never_use_credentials(monkeypatch):
    harness = load_harness()
    monkeypatch.setattr(harness, "assert_environment", lambda: {"clean": False})
    monkeypatch.setattr(harness, "prior_ledger_snapshot", lambda: {
        "old_ledgers": {}, "prior_committed_exposure_usd": "0",
        "prior_unknown_reserved_usd": "0",
    })
    monkeypatch.setattr(harness, "prior_wire_sample", lambda: {"requests": 0})
    qualified = harness.qualification()
    assert qualified["paid_calls"] == qualified["source_calls"] == 0
    assert not qualified["attempt_claimed"] and not qualified["ready_for_paid_run"]
    with pytest.raises(RuntimeError, match="fresh approval"):
        harness.main(["--run", "DOCN"])



def test_linked_old_ledger_change_blocks_new_reservation(tmp_path):
    harness = load_harness()
    record = approval(tmp_path)
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    guard = harness.DocumentBudgetGuard(
        ledger, pilot.Decimal("12"), approval_record=record,
        allowed_models={pilot.A, pilot.B_DEEP}, max_calls=1,
        scope="proof:DocumentAccess:DOCN", allowed_kinds={"run"},
        scope_ceiling=pilot.Decimal("4"),
    )
    old = Path(next(iter(record["old_ledgers"])))
    with old.open("a") as handle:
        handle.write('{"type":"unknown","ticket":"unknown"}\n')
    with pytest.raises(ValueError, match="ledger changed"):
        guard.reserve(pilot.A, "1", kind="run")
    assert not ledger.path.exists()


def test_document_scope_refuses_unapproved_cutoff_or_audit_retry(monkeypatch):
    spec = live_adapter.CliSpec(
        "DOCN", "2026-11-06", pilot.B_DEEP, pilot.A, 3, 16384,
        max_tool_rounds=4, proof_scope=live_adapter.DOCUMENT_PROOF_SCOPE,
    )
    with pytest.raises(ValueError):
        dataclasses.replace(spec, analysis_cutoff_utc="2026-11-06T20:00:00+00:00").validate()
    import tradingagents.graph.setup as setup_module
    observed = []
    def factory(llm, *, deep_model_id, quick_model_id, sdk_retries_disabled):
        observed.append(sdk_retries_disabled)
        return lambda state: {}
    monkeypatch.setattr(setup_module, "create_advisory_audit", factory)
    with live_adapter.one_document_audit_attempt(spec):
        setup_module.create_advisory_audit(
            object(), deep_model_id=pilot.A, quick_model_id=pilot.B_DEEP,
            sdk_retries_disabled=True,
        )
    assert observed == [True]



def test_document_advisory_audit_allows_one_application_retry(monkeypatch):
    import tradingagents.graph.setup as setup_module

    spec = live_adapter.CliSpec(
        "DOCN", "2026-11-06", pilot.B_DEEP, pilot.A, 3, 16384,
        max_tool_rounds=4, proof_scope=live_adapter.DOCUMENT_PROOF_SCOPE,
    )

    class FailingAuditModel:
        calls = 0

        def with_structured_output(self, *_args, **_kwargs):
            return self

        def invoke(self, _prompt):
            self.calls += 1
            raise RuntimeError("temporary audit failure")

    model = FailingAuditModel()
    with live_adapter.one_document_audit_attempt(spec):
        node = setup_module.create_advisory_audit(
            model, deep_model_id=pilot.A, quick_model_id=pilot.B_DEEP,
            sdk_retries_disabled=True,
        )
    record = node({})["advisory_audit"]
    assert model.calls == 2
    assert len(record["attempts"]) == 2
    assert record["retry_policy"] == "one application retry; SDK retries disabled"


def test_document_claim_binds_wire_and_consumes_start_once(tmp_path, monkeypatch):
    import subprocess

    record = approval(tmp_path)
    wt = Path(record["worktree_root"])
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    (wt / "source.py").write_text("# offline candidate\n")
    subprocess.run(["git", "add", "source.py"], cwd=wt, check=True)
    subprocess.run([
        "git", "-c", "user.name=Offline", "-c", "user.email=offline@example.invalid",
        "commit", "-qm", "candidate",
    ], cwd=wt, check=True)
    subprocess.run(["git", "remote", "add", "origin", record["repository_origin"]], cwd=wt, check=True)
    record["candidate_head"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=wt, text=True
    ).strip()
    ledger = pilot.PilotLedger(tmp_path / "fresh.jsonl")
    record["ledger_path"] = str(ledger.path)
    digest = live_adapter.claim_document_access_proof(ledger, record, "DOCN")
    spec = live_adapter.CliSpec(
        "DOCN", record["analysis_date"], pilot.B_DEEP, pilot.A, 3, 16384,
        max_tool_rounds=4, proof_scope=live_adapter.DOCUMENT_PROOF_SCOPE,
    )
    claim = live_adapter.ExecutionClaim("proof", "DocumentAccess-DOCN", digest)
    budget = pilot.BudgetGuard(
        ledger, pilot.Decimal("12"), allowed_models={pilot.A, pilot.B_DEEP},
        max_calls=60, scope="proof:DocumentAccess:DOCN", allowed_kinds={"run"},
        scope_ceiling=pilot.Decimal("4"),
    )
    live_adapter.verify_budget_binding(claim, budget, spec, None)
    monkeypatch.setattr(live_adapter, "_verify_run_fixes_machine", lambda: None)
    live_adapter.start_execution(claim, ledger, spec)
    with pytest.raises(RuntimeError, match="already started"):
        live_adapter.start_execution(claim, ledger, spec)
    with pytest.raises(RuntimeError):
        live_adapter.verify_budget_binding(
            claim, pilot.BudgetGuard(
                ledger, pilot.Decimal("12"), allowed_models={pilot.A, pilot.B_DEEP},
                max_calls=61, scope="proof:DocumentAccess:DOCN", allowed_kinds={"run"},
                scope_ceiling=pilot.Decimal("4"),
            ), spec, None,
        )



def test_each_attempt_requires_new_receipt_and_unknown_headroom(tmp_path):
    record = approval(tmp_path)
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    live_adapter.claim_document_access_proof(ledger, record, "DOCN")
    root = Path(record["receipt_root"])
    msft = root / "MSFT.json"
    stale = json.loads(msft.read_text())
    stale["observed_at"] = json.loads((root / "DOCN.json").read_text())["observed_at"]
    msft.write_text(json.dumps(stale))
    with pytest.raises(ValueError, match="refreshed"):
        live_adapter.claim_document_access_proof(ledger, record, "MSFT")
    assert not any(e.get("type") == "attempt_claim" and e.get("ticker") == "MSFT" for e in ledger.events())
    stale["observed_at"] = datetime.now(UTC).isoformat()
    stale["results"]["key"]["limit_remaining"] = "4"
    msft.write_text(json.dumps(stale))
    with pytest.raises(ValueError, match="headroom"):
        live_adapter.claim_document_access_proof(ledger, record, "MSFT")
    assert not any(e.get("type") == "attempt_claim" and e.get("ticker") == "MSFT" for e in ledger.events())


def test_feature_assessment_never_calls_missing_features_complete(tmp_path):
    harness = load_harness()
    state = {"company_of_interest": "DOCN", "trade_date": "2026-11-06"}
    proof = harness.assess_document_feature_proof(state, tmp_path, "DOCN")
    assert proof["status"] == "incomplete"
    assert all(row["status"] == "missing" for row in proof["checks"].values())
    assert proof["source_and_report_hashes"]["macro_outputs"] == []


def _offline_run_fixture(tmp_path, monkeypatch):
    harness = load_harness()
    record = approval(tmp_path)
    monkeypatch.setattr(harness, "_candidate_and_approval", lambda ticker: (record, {"head": "a" * 40}))
    monkeypatch.setattr(harness, "PRIVATE", tmp_path)
    monkeypatch.setattr(harness, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(harness, "LEDGER", Path(record["ledger_path"]))
    candidate = tmp_path / "candidate.json"
    candidate.write_text("{}")
    monkeypatch.setattr(harness, "CANDIDATE", candidate)
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({
        "OPENROUTER_API_KEY": "dummy-openrouter",
        "SEC_EDGAR_USER_AGENT": "offline@example.invalid",
        "FRED_API_KEY": "dummy-fred",
        "ALPHA_VANTAGE_API_KEY": "dummy-av",
    }))
    auth.chmod(0o600)
    return harness, auth


def test_generic_cli_success_is_recorded_as_proof_incomplete(tmp_path, monkeypatch):
    harness, auth = _offline_run_fixture(tmp_path, monkeypatch)
    calls = []
    def fake_cli(*args, **kwargs):
        calls.append(kwargs["source_credentials"])
        return {"state": {"company_of_interest": "DOCN", "trade_date": "2026-11-06"},
                "model_calls": 0}
    monkeypatch.setattr(harness.live_adapter, "execute_cli", fake_cli)
    output = harness.run("DOCN", auth)
    assert output["status"] == "proof_incomplete"
    job = json.loads(Path(output["job"]).read_text())
    assert job["execution_status"] == "complete"
    assert job["proof_status"] == "incomplete"
    assert calls == [{"FRED_API_KEY": "dummy-fred", "ALPHA_VANTAGE_API_KEY": "dummy-av"}]
    assert "dummy" not in json.dumps(job)
    assert json.loads((tmp_path / "runtime" / "DOCN" / "document-proof-assessment.json").read_text())["status"] == "incomplete"


def test_setup_failure_after_claim_has_terminal_event_and_failed_job(tmp_path, monkeypatch):
    harness, auth = _offline_run_fixture(tmp_path, monkeypatch)
    def fail_wire(*args, **kwargs):
        raise RuntimeError("offline wire setup failure")
    monkeypatch.setattr(harness.live_adapter, "OpenRouterWireGuard", fail_wire)
    with pytest.raises(RuntimeError, match="wire setup"):
        harness.run("DOCN", auth)
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    events = ledger.events()
    assert any(e["type"] == "attempt_claim" for e in events)
    assert any(e["type"] == "attempt_failed_start" for e in events)
    job = json.loads((tmp_path / "document-access-proof-DOCN.job.json").read_text())
    assert job["status"] == "failed" and job["proof_status"] == "incomplete"


def test_document_source_credentials_are_isolated_and_old_scopes_reject_them(tmp_path, monkeypatch):
    import os

    from tests.test_b3_live_proof_guard import restored_harness_process_state

    spec = live_adapter.CliSpec(
        "DOCN", "2026-11-06", pilot.B_DEEP, pilot.A, 3, 16384,
        max_tool_rounds=4, proof_scope=live_adapter.DOCUMENT_PROOF_SCOPE,
    )
    with restored_harness_process_state():
        monkeypatch.setenv("UNRELATED_API_KEY", "ambient")
        monkeypatch.setenv("FRED_API_KEY", "ambient-fred")
        live_adapter.configure_isolated_env(
            spec, tmp_path / "document", openrouter_key="dummy",
            sec_user_agent="offline@example.invalid",
            source_credentials={"FRED_API_KEY": "authorized-fred",
                                "ALPHA_VANTAGE_API_KEY": "authorized-av"},
        )
        assert os.getenv("UNRELATED_API_KEY") is None
        assert os.getenv("FRED_API_KEY") == "authorized-fred"
        assert os.getenv("ALPHA_VANTAGE_API_KEY") == "authorized-av"
    old = live_adapter.CliSpec("DOCN", "2026-11-06", pilot.A, pilot.A, 1, 16384)
    with pytest.raises(ValueError, match="reserved"):
        live_adapter.configure_isolated_env(
            old, tmp_path / "old", openrouter_key="dummy",
            sec_user_agent="offline@example.invalid",
            source_credentials={"FRED_API_KEY": "dummy", "ALPHA_VANTAGE_API_KEY": "dummy"},
        )



def test_feature_assessment_accepts_real_retained_source_and_rendered_artifacts(tmp_path, monkeypatch):
    from tests.test_transcript_access import state_with_sec_corpus, transcript_record
    from tradingagents.agents.audit_evidence import retain_tool_outputs
    from tradingagents.agents.document_access import merge_search_traces, run_document_search
    from tradingagents.agents.document_questions import (
        lookup_document_questions,
        parse_document_questions,
        render_document_followups,
    )
    from tradingagents.agents.transcript_access import prepare_transcript_sources
    from tradingagents.dataflows.filing_search import corpus_hash

    harness = load_harness()
    state, corpus = state_with_sec_corpus()
    corpus = corpus.model_copy(update={"selected_accessions": (corpus.documents[0].filing.accession,)})
    state["document_sources"]["corpus"] = corpus.model_dump(mode="json")
    state["document_sources"]["corpus_hash"] = corpus_hash(corpus)
    monkeypatch.setattr(
        "tradingagents.agents.transcript_access.vendor_transcript.get_latest_transcript_evidence",
        lambda *args, **kwargs: transcript_record(corpus),
    )
    state.update(prepare_transcript_sources(state, {"fundamentals", "news"}))
    trace = {}
    for role, query in (("fundamentals", "conference"), ("news", "DigitalOcean")):
        update = run_document_search(state, query, role=role, call_id=role + "-1")
        trace = merge_search_traces(trace, update["document_search_trace"])
    state["document_search_trace"] = trace
    state["investment_debate_state"] = {
        "document_questions": {
            "bull": parse_document_questions(
                '```document_questions\n["conference call"]\n```', "bull"
            ),
            "bear": parse_document_questions(
                '```document_questions\n["DigitalOcean"]\n```', "bear"
            ),
        }
    }
    state.update(lookup_document_questions(state))
    state["audit_news_tool_evidence"] = retain_tool_outputs(
        "news", "DOCN", "2026-11-06", [{
            "name": "get_macro_indicators", "arguments": {"indicator": "cpi"},
            "tool_call_id": "macro-1",
            "content": "## FRED: CPI\n- Window: 2025-11-06 to 2026-11-06\n**Latest:** 100",
        }],
    )
    state["final_trade_decision"] = "Rating: Hold"
    state["price_observation"] = {"status": "available"}
    report = tmp_path / "results" / "reports" / "DOCN_offline"
    (report / "5_portfolio").mkdir(parents=True)
    (report / "6_evidence").mkdir()
    (report / "complete_report.md").write_text("offline complete report")
    (report / "5_portfolio" / "decision.md").write_text(
        state["final_trade_decision"] + "\n" +
        render_document_followups(state, state["final_trade_decision"])
    )
    (report / "6_evidence" / "summary.md").write_text("Document searches")
    (report / "evidence.json").write_text(json.dumps({"document_sources": state["document_sources"]}))
    state_log = tmp_path / "results" / "DOCN" / "TradingAgentsStrategy_logs"
    state_log.mkdir(parents=True)
    (state_log / "full_states_log_2026-11-06.json").write_text(json.dumps(state))
    proof = harness.assess_document_feature_proof(state, tmp_path, "DOCN")
    assert proof["status"] == "complete", [k for k, v in proof["checks"].items() if v["status"] != "pass"]
    assert all(row["status"] == "pass" for row in proof["checks"].values())
    assert len(proof["source_and_report_hashes"]["report_files"]) == 4
    persisted = state_log / "full_states_log_2026-11-06.json"
    saved = json.loads(persisted.read_text())
    saved.pop("document_followups")
    persisted.write_text(json.dumps(saved))
    incomplete = harness.assess_document_feature_proof(state, tmp_path, "DOCN")
    assert incomplete["checks"]["saved_state"]["status"] == "missing"
    assert incomplete["status"] == "incomplete"



def test_unavailable_transcript_requires_valid_reason_report_and_final_decision(tmp_path):
    from tests.test_transcript_access import state_with_sec_corpus
    from tradingagents.agents import transcript_access as access

    harness = load_harness()
    state, corpus = state_with_sec_corpus()
    state["company_of_interest"] = "MSFT"
    state["document_sources"]["ticker"] = "MSFT"
    state["final_trade_decision"] = "Rating: Hold"
    reason = "SEC filing lacks an explicit call date"
    state["transcript_sources"] = access._wrapper(
        access._scope(state), corpus, status="unavailable", reason=reason,
    )
    report = tmp_path / "results" / "reports" / "MSFT_offline"
    (report / "6_evidence").mkdir(parents=True)
    (report / "5_portfolio").mkdir()
    (report / "complete_report.md").write_text("Offline report")
    (report / "5_portfolio" / "decision.md").write_text("Rating: Hold")
    (report / "evidence.json").write_text("{}")
    summary = report / "6_evidence" / "summary.md"
    summary.write_text(f"Document searches\nVendor transcript unavailable: {reason}")
    proof = harness.assess_document_feature_proof(state, tmp_path, "MSFT")
    assert proof["checks"]["dated_transcript_or_continuation"]["status"] == "pass"
    assert proof["positive_transcript_observed"] is False
    assert "vendor_transcript" in proof["missing_live_observations"]
    summary.write_text("Document searches")
    proof = harness.assess_document_feature_proof(state, tmp_path, "MSFT")
    assert proof["checks"]["dated_transcript_or_continuation"]["status"] == "missing"
    summary.write_text(f"Document searches\nVendor transcript unavailable: {reason}")
    state["final_trade_decision"] = ""
    proof = harness.assess_document_feature_proof(state, tmp_path, "MSFT")
    assert proof["checks"]["dated_transcript_or_continuation"]["status"] == "missing"
    state["final_trade_decision"] = "Rating: Hold"
    state["transcript_sources"] = access._wrapper(
        access._scope(state), corpus, status="unavailable", reason="",
    )
    proof = harness.assess_document_feature_proof(state, tmp_path, "MSFT")
    assert proof["checks"]["dated_transcript_or_continuation"]["status"] == "missing"
    state["company_of_interest"] = "DOCN"
    state["document_sources"]["ticker"] = "DOCN"
    state["transcript_sources"] = access._wrapper(
        access._scope(state), corpus, status="unavailable", reason=reason,
    )
    proof = harness.assess_document_feature_proof(state, tmp_path, "DOCN")
    assert proof["checks"]["dated_transcript_or_continuation"]["status"] == "missing"


def test_docn_macro_gap_is_not_positive_observation(tmp_path):
    from tradingagents.agents.audit_evidence import retain_tool_outputs

    harness = load_harness()
    state = {
        "company_of_interest": "DOCN", "trade_date": "2026-11-06",
        "audit_news_tool_evidence": retain_tool_outputs(
            "news", "DOCN", "2026-11-06", [{
                "name": "get_macro_indicators", "arguments": {"indicator": "cpi"},
                "tool_call_id": "macro-gap",
                "content": "## FRED: CPI\n- Window: 2025-11-06 to 2026-11-06\nDATA_UNAVAILABLE: No observations",
            }],
        ),
    }
    proof = harness.assess_document_feature_proof(state, tmp_path, "DOCN")
    assert proof["checks"]["dated_macro_or_gap"]["status"] == "missing"
    assert proof["positive_macro_observed"] is False
    assert "dated_macro_value" in proof["missing_live_observations"]


def test_fresh_endpoint_price_increase_requires_new_approval(tmp_path):
    record = approval(tmp_path)
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    path = Path(record["receipt_root"]) / "DOCN.json"
    metadata = json.loads(path.read_text())
    metadata["results"][pilot.A]["endpoints"][0]["pricing"]["prompt"] = "0.000002"
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="price exceeds"):
        live_adapter.claim_document_access_proof(ledger, record, "DOCN")
    assert not ledger.path.exists()


def test_harness_imports_helpers_from_its_checkout_without_live_authority(tmp_path):
    """A checkout away from M1 must import without using M1's helper source."""
    import shutil
    import subprocess
    import sys

    checkout = tmp_path / "checkout"
    tools = checkout / "docs/reviews"
    harness_dir = tools / "document-access-proof-tools"
    helper_dir = tools / "valuation-reference-proof-tools"
    harness_dir.mkdir(parents=True)
    helper_dir.mkdir()
    shutil.copy2(HARNESS, harness_dir / "live_cli.py")
    original_helpers = HARNESS.parents[1] / "valuation-reference-proof-tools"
    for name in ("live_adapter.py", "pilot.py"):
        shutil.copy2(original_helpers / name, helper_dir / name)
    probe = (
        "import pathlib,runpy,sys; "
        "data=runpy.run_path(sys.argv[1],run_name='portability_probe'); "
        "root=pathlib.Path(sys.argv[1]).resolve().parents[3]; "
        "assert pathlib.Path(data['live_adapter'].__file__).is_relative_to(root); "
        "assert pathlib.Path(sys.modules['pilot'].__file__).is_relative_to(root); "
        "assert data['WT'] != root; "
        "assert not list(root.rglob('*.jsonl'))"
    )
    subprocess.run([sys.executable, "-I", "-c", probe, str(harness_dir / "live_cli.py")],
                   cwd=tmp_path, check=True, capture_output=True, text=True)
