"""Run-fixes allowance uses new authority, never historical remaining budgets."""
import dataclasses
import hashlib
import subprocess

import pytest

from tests.test_b3_live_proof_guard import approval
from tests.test_valuation_reference_live_adapter import Request, live_adapter, pilot


def record(tmp_path, monkeypatch):
    result = approval(tmp_path, monkeypatch)
    old = tmp_path / "old-ledger.jsonl"
    old.write_text('{"type":"old_immutable_authority"}\n')
    result.update(phase="Build1", attempts=2, ceiling_usd="24", phase_ceiling_usd="12",
                  quick_model=pilot.B_DEEP, deep_model=pilot.A,
                  authorized_builds=["Build1"], analysts=["market", "social", "news", "fundamentals"],
                  llm_max_retries=0, machine={"cpu": "Apple M1 Pro", "ram_bytes": 17179869184},
                  repository_origin="https://github.com/offline/fixture.git",
                  supersedes_unused_authority=True,
                  old_ledgers={str(old): hashlib.sha256(old.read_bytes()).hexdigest()})
    subprocess.run(["git", "remote", "add", "origin", result["repository_origin"]],
                   cwd=result["worktree_root"], check=True)
    return result


def scope(tmp_path, monkeypatch):
    r = record(tmp_path, monkeypatch)
    ledger = pilot.PilotLedger(tmp_path / "run-fixes-proof-ledger.jsonl")
    digest = live_adapter.claim_run_fixes_proof(ledger, r)
    spec = live_adapter.CliSpec("DOCN", r["analysis_date"], pilot.B_DEEP, pilot.A, 1, 16384,
                                proof_scope="run-fixes:Build1")
    claim = live_adapter.ExecutionClaim("proof", "Build1", digest)
    guard = pilot.BudgetGuard(ledger, pilot.Decimal("24"), allowed_models={pilot.A, pilot.B_DEEP},
                             max_calls=40, scope="proof:Build1", allowed_kinds={"run"},
                             scope_ceiling=pilot.Decimal("12"))
    return r, ledger, spec, claim, guard


def test_claim_new_marker_cannot_reclaim_or_start_twice(tmp_path, monkeypatch):
    r, ledger, spec, claim, guard = scope(tmp_path, monkeypatch)
    monkeypatch.setattr(live_adapter, "_verify_run_fixes_machine", lambda: None)
    assert ledger.events()[0]["type"] == "allowance"
    assert ledger.events()[0]["aggregate_ceiling_usd"] == "24"
    live_adapter.verify_budget_binding(claim, guard, spec, None)
    live_adapter.start_execution(claim, ledger, spec)
    with pytest.raises(RuntimeError, match="already started"):
        live_adapter.start_execution(claim, ledger, spec)
    with pytest.raises(RuntimeError):
        live_adapter.claim_run_fixes_proof(ledger, r)


@pytest.mark.parametrize("field,value", [
    ("phase", "Build2"), ("authorized_builds", ["Build1", "Build2"]),
    ("ceiling_usd", "36"), ("phase_ceiling_usd", "24"), ("attempts", 3),
    ("quick_model", pilot.A), ("llm_max_retries", 1), ("depth", 2),
    ("max_output_tokens", 8192), ("max_tool_rounds", 5), ("analysts", ["market"]),
    ("supersedes_unused_authority", False),
])
def test_wrong_authority_never_creates_ledger(tmp_path, monkeypatch, field, value):
    r = record(tmp_path, monkeypatch)
    r[field] = value
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    with pytest.raises((RuntimeError, ValueError)):
        live_adapter.claim_run_fixes_proof(ledger, r)
    assert not ledger.path.exists()


def test_old_ledger_change_or_reuse_is_rejected_without_mutation(tmp_path, monkeypatch):
    r = record(tmp_path, monkeypatch)
    from pathlib import Path
    old = Path(next(iter(r["old_ledgers"])))
    before = old.read_bytes()
    with pytest.raises((RuntimeError, ValueError)):
        live_adapter.claim_run_fixes_proof(pilot.PilotLedger(old), r)
    assert old.read_bytes() == before
    old.write_text(before.decode() + '{}\n')
    new = pilot.PilotLedger(tmp_path / "new.jsonl")
    with pytest.raises((RuntimeError, ValueError)):
        live_adapter.claim_run_fixes_proof(new, r)
    assert not new.path.exists()


@pytest.mark.parametrize("changes", [
    {"proof_scope": None}, {"extra_peer_pins": ("MSFT", "ORCL")},
    {"analysis_cutoff_utc": "2026-11-05T23:00:00+00:00"},
    {"market_observation_cutoff": "2026-11-05T23:00:00+00:00"},
    {"max_tokens": 8192},
])
def test_split_scope_cannot_drift(tmp_path, monkeypatch, changes):
    _, ledger, spec, claim, guard = scope(tmp_path, monkeypatch)
    if "max_tokens" in changes:
        changes = {"max_output_tokens": changes["max_tokens"]}
    with pytest.raises((ValueError, RuntimeError)):
        live_adapter.verify_budget_binding(claim, guard, dataclasses.replace(spec, **changes), None)
    assert not any(e["type"] == "execution_start" for e in ledger.events())


def test_budget_stop_is_sticky_and_unknown_reservation_never_refunded(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "offline.jsonl")
    guard = pilot.BudgetGuard(ledger, pilot.Decimal("24"), allowed_models={pilot.A}, max_calls=40,
                             scope="proof:Build1", allowed_kinds={"run"}, scope_ceiling=pilot.Decimal("12"))
    wire = live_adapter.OpenRouterWireGuard(guard, {pilot.A: {
        "input_per_token": "0", "output_per_token": "1", "cache_read_per_token": "0",
        "cache_write_per_token": "0"}}, max_output_tokens=7, kind="run",
        allowed_resolved_models={pilot.A: {pilot.A}}, serialize_paid_requests=True)
    request = Request({"model": pilot.A, "max_tokens": 7, "messages": []})
    ticket = wire.before(request)
    wire.failed(ticket, TimeoutError())
    assert ledger.committed_usd() == 7
    with pytest.raises(live_adapter.BudgetStoppedError):
        wire.before(request)
    # Even a later settlement cannot turn a guard stop into renewed send authority.
    guard.settle(ticket, "0")
    with pytest.raises(live_adapter.BudgetStoppedError):
        wire.before(request)
    assert wire.request_count == 1
    assert sum(e["type"] == "reserve" for e in ledger.events()) == 1


def test_split_cli_config_requires_zero_retries_and_exact_tiers(tmp_path, monkeypatch):
    from tests.test_b3_live_proof_guard import restored_harness_process_state
    _, _, spec, _, _ = scope(tmp_path, monkeypatch)
    with restored_harness_process_state():
        live_adapter.configure_isolated_env(spec, tmp_path / "isolated", openrouter_key="fake",
                                            sec_user_agent="offline-contact")
        config = live_adapter.fresh_default_config()
        live_adapter.verify_cli_config(config, spec)
        assert int(config["llm_max_retries"]) == 0
        assert config["quick_think_llm"] == pilot.B_DEEP
        assert config["deep_think_llm"] == pilot.A
        with pytest.raises(RuntimeError):
            live_adapter.verify_cli_config({**config, "llm_max_retries": 1}, spec)


@pytest.mark.parametrize("failure", ["origin", "dirty", "head", "machine"])
def test_start_consumes_attempt_before_candidate_runtime_failure(tmp_path, monkeypatch, failure):
    from pathlib import Path
    r, ledger, spec, claim, _ = scope(tmp_path, monkeypatch)
    def machine():
        if failure == "machine":
            raise RuntimeError("wrong machine")
    monkeypatch.setattr(live_adapter, "_verify_run_fixes_machine", machine)
    wt = Path(r["worktree_root"])
    if failure == "origin":
        subprocess.run(["git", "remote", "set-url", "origin", "https://wrong.invalid/repo"], cwd=wt, check=True)
    if failure in {"dirty", "head"}:
        (wt / "source.py").write_text("changed\n")
        if failure == "head":
            subprocess.run(["git", "add", "source.py"], cwd=wt, check=True)
            subprocess.run(["git", "-c", "user.name=Offline", "-c", "user.email=offline@example.invalid",
                            "commit", "-qm", "changed"], cwd=wt, check=True)
    with pytest.raises(RuntimeError):
        live_adapter.start_execution(claim, ledger, spec)
    assert sum(e["type"] == "execution_start" for e in ledger.events()) == 1
    with pytest.raises(RuntimeError, match="already started"):
        live_adapter.start_execution(claim, ledger, spec)


def test_budget_stop_blocks_second_http_send_even_after_audit_retry_boundary(tmp_path, monkeypatch):
    import httpx

    from tradingagents.agents.audit_pass import create_advisory_audit
    ledger = pilot.PilotLedger(tmp_path / "offline-http.jsonl")
    guard = pilot.BudgetGuard(ledger, pilot.Decimal("24"), allowed_models={pilot.A}, max_calls=40,
                             scope="proof:Build1", allowed_kinds={"run"}, scope_ceiling=pilot.Decimal("12"))
    wire = live_adapter.OpenRouterWireGuard(guard, {pilot.A: {
        "input_per_token": "0", "output_per_token": "1", "cache_read_per_token": "0",
        "cache_write_per_token": "0"}}, max_output_tokens=13, kind="run",
        allowed_resolved_models={pilot.A: {pilot.A}}, serialize_paid_requests=True)
    sends = []
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **kw: sends.append(a))
    class Audit:
        calls = 0
        def with_structured_output(self, *a, **kw):
            return self
        def invoke(self, prompt):
            self.calls += 1
            with httpx.Client() as client:
                return client.send(httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions",
                    json={"model": pilot.A, "max_tokens": 13, "messages": []}))
    model = Audit()
    with live_adapter.installed_http_guard(wire):
        result = create_advisory_audit(model, deep_model_id=pilot.A, quick_model_id=pilot.A,
                                      sdk_retries_disabled=True)({})["advisory_audit"]
    assert result["error_category"] == "budget_stopped"
    assert model.calls == 1
    assert not sends
    assert not any(e["type"] == "reserve" for e in ledger.events())


def test_completed_price_must_be_revalidated_and_match_actual_session(tmp_path, monkeypatch):
    from tradingagents.dataflows.vendors.yahoo import price_observation
    r, _, spec, _, _ = scope(tmp_path, monkeypatch)
    price = {"status": "available", "session_status": "completed", "session_date": spec.analysis_date,
             "raw_source": {"observation_cutoff": "2026-11-05T22:00:00+00:00"}}
    calls = []
    def checked(record, ticker, as_of):
        calls.append((record, ticker, as_of))
        return record
    monkeypatch.setattr(price_observation, "validate_price_observation", checked)
    live_adapter.verify_run_fixes_completed_state({"price_observation": price}, spec, r)
    assert calls == [(price, "DOCN", spec.analysis_date)]
    with pytest.raises(RuntimeError):
        live_adapter.verify_run_fixes_completed_state({"price_observation": {**price, "session_date": "2026-11-04"}}, spec, r)


@pytest.mark.parametrize("url,allowed", [
    ("https://query1.finance.yahoo.com/v8/finance/chart/DOCN?interval=1d&range=1d", True),
    ("https://query2.finance.yahoo.com/v8/finance/chart/DOCN?interval=1d&range=1d", True),
    ("https://query2.finance.yahoo.com.evil.test/v8/finance/chart/DOCN?interval=1d&range=1d", False),
    ("https://query2.finance.yahoo.com/v8/finance/chart/MSFT?interval=1d&range=1d", False),
])
def test_close_receipt_allows_only_exact_standard_docn_chart_endpoints(tmp_path, monkeypatch, url, allowed):
    r = record(tmp_path, monkeypatch)
    r["session"]["docn-chart"]["url"] = url
    ledger = pilot.PilotLedger(tmp_path / "endpoint-fixture-ledger.jsonl")
    if allowed:
        live_adapter.claim_run_fixes_proof(ledger, r)
        assert ledger.events()[1]["type"] == "attempt_claim"
    else:
        with pytest.raises(ValueError):
            live_adapter.claim_run_fixes_proof(ledger, r)
        assert not ledger.path.exists()
