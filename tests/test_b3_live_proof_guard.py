
"""New B3 proof authority is one shot and independent of all earlier ledgers."""
import dataclasses
import hashlib
import json
import os
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from tests.test_valuation_reference_live_adapter import Request, live_adapter, pilot


@contextmanager
def restored_harness_process_state():
    """A harness test may rebuild imported defaults and delete env keys."""
    import importlib

    import yfinance.cache as yf_cache

    names = ("tradingagents.default_config", "cli.run", "cli.selections", "cli.main",
             "tradingagents.graph.trading_graph")
    modules = [importlib.import_module(name) for name in names]
    defaults = [(module, module.DEFAULT_CONFIG) for module in modules]
    environment = os.environ
    before = dict(environment)
    locations = [(getattr(yf_cache, name), getattr(yf_cache, name)._cache_dir)
                 for name in ("_TzDBManager", "_CookieDBManager", "_ISINDBManager")]
    # Restore direct mutation/deletion, not merely keys set through monkeypatch.
    try:
        yield
    finally:
        environment.clear()
        environment.update(before)
        for module, config in defaults:
            module.DEFAULT_CONFIG = config
        for manager, location in locations:
            manager.set_location(location)


@pytest.fixture(autouse=True)
def isolated_harness_process_state():
    with restored_harness_process_state():
        yield


def approval(tmp_path, monkeypatch):
    now = datetime(2026, 11, 5, 23, tzinfo=UTC)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    monkeypatch.setattr(live_adapter, "datetime", Clock)
    chart = tmp_path / "live-chart.json"
    chart.write_text(json.dumps({"chart": {"result": [{"meta": {
        "symbol": "DOCN", "currency": "USD", "exchangeTimezoneName": "America/New_York",
        "currentTradingPeriod": {"regular": {
            "start": int(datetime(2026, 11, 5, 14, 30, tzinfo=UTC).timestamp()),
            "end": int(datetime(2026, 11, 5, 21, tzinfo=UTC).timestamp())}}}}]}}))
    calendar = tmp_path / "calendar.html"
    calendar.write_text("<html>NYSE 2026 official calendar: Core Trading Session 9:30 a.m. to 4:00 p.m.</html>")
    def receipt(path, url):
        return {"path": str(path), "url": url, "http_status": 200,
                "retrieved_at": "2026-11-05T22:00:00+00:00",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    worktree = tmp_path / "candidate"
    worktree.mkdir()
    subprocess.run(["git", "init", "-q", str(worktree)], check=True)
    (worktree / "source.py").write_text("# offline proof candidate\n")
    subprocess.run(["git", "add", "source.py"], cwd=worktree, check=True)
    subprocess.run(["git", "-c", "user.name=Offline Fixture", "-c",
                    "user.email=offline@example.invalid", "commit", "-qm", "Offline fixture"],
                   cwd=worktree, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip()
    return {
        "approval_id": "new-b3-one-shot", "approved_at_recorded": "2026-11-05T22:00:00+00:00",
        "user_instruction": "Authorize one all-four-analyst lowest-depth DOCN live proof after the actual US close, at most $3, then stop.", "phase": "B3", "attempts": 1, "ceiling_usd": "3",
        "ticker": "DOCN", "analysis_date": "2026-11-05", "quick_model": pilot.A,
        "deep_model": pilot.A, "depth": 1, "max_output_tokens": 16384,
        "max_tool_rounds": 4, "candidate_head": head, "worktree_root": str(worktree),
        "session": {"session_date": "2026-11-05", "observed_at": "2026-11-05T22:00:00+00:00",
                    "regular_close_utc": "2026-11-05T21:00:00+00:00",
                    "nyse-calendar": receipt(calendar, "https://www.nyse.com/trade/hours-calendars"),
                    "docn-chart": receipt(chart, "https://query1.finance.yahoo.com/v8/finance/chart/DOCN?interval=1d&range=1d")}
    }


def claim_scope(tmp_path, monkeypatch):
    record = approval(tmp_path, monkeypatch)
    ledger = pilot.PilotLedger(tmp_path / "new-b3-only.jsonl")
    digest = live_adapter.claim_b3_proof(ledger, record)
    spec = live_adapter.CliSpec("DOCN", "2026-11-05", pilot.A, pilot.A, 1, 16384, max_tool_rounds=4)
    claim = live_adapter.ExecutionClaim("proof", "B3", approval_sha256=digest)
    guard = pilot.BudgetGuard(ledger, pilot.Decimal("3"), allowed_models={pilot.A},
                             max_calls=40, scope="proof:B3", allowed_kinds={"run"},
                             scope_ceiling=pilot.Decimal("3"))
    return record, ledger, spec, claim, guard


def test_b3_claim_starts_only_once_and_unknown_cost_stays_reserved(tmp_path, monkeypatch):
    record, ledger, spec, claim, guard = claim_scope(tmp_path, monkeypatch)
    live_adapter.verify_budget_binding(claim, guard, spec, None)
    live_adapter.start_execution(claim, ledger, spec)
    # An execution failure is never permission for a second start or claim.
    with pytest.raises(RuntimeError, match="already started"):
        live_adapter.start_execution(claim, ledger, spec)
    with pytest.raises(RuntimeError, match="fresh empty"):
        live_adapter.claim_b3_proof(ledger, record)
    wire = live_adapter.OpenRouterWireGuard(guard, {pilot.A: {
        "input_per_token": "0.000001", "output_per_token": "0.000005",
        "cache_read_per_token": "0", "cache_write_per_token": "0"}},
        max_output_tokens=16384, kind="run", allowed_resolved_models={pilot.A: {pilot.A}})
    ticket = wire.before(Request({"model": pilot.A, "max_tokens": 16384, "messages": []}))
    reserved = ledger.committed_usd()
    wire.failed(ticket, TimeoutError())
    assert ledger.committed_usd() == reserved > 0
    with pytest.raises(RuntimeError, match="budget cap"):
        guard.reserve(pilot.A, "3", kind="run")
    assert sum(e["type"] == "reserve" for e in ledger.events()) == 1


@pytest.mark.parametrize("field,value", [
    ("ticker", "NET"), ("depth", 2), ("ceiling_usd", "3.01"), ("attempts", 2),
    ("quick_model", pilot.B_QUICK), ("max_output_tokens", 16385),
    ("approved_at_recorded", "2026-11-05T22:00:00"),
    ("approved_at_recorded", "2026-11-06T23:00:00+00:00"),
])
def test_b3_wrong_authority_cannot_claim(tmp_path, monkeypatch, field, value):
    record = approval(tmp_path, monkeypatch)
    record[field] = value
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    with pytest.raises((ValueError, RuntimeError)):
        live_adapter.claim_b3_proof(ledger, record)
    assert ledger.events() == []


@pytest.mark.parametrize("mutate", [
    lambda r: r["session"].update(regular_close_utc="2026-11-06T21:00:00+00:00"),
    lambda r: r["session"].update(regular_close_utc="2026-11-05T16:00:00"),
    lambda r: r["session"]["docn-chart"].update(sha256="b" * 64),
    lambda r: r["session"]["docn-chart"].update(retrieved_at="2026-11-06T22:00:00+00:00"),
    lambda r: r["session"]["docn-chart"].update(http_status=429),
    lambda r: r["session"]["docn-chart"].update(url="https://fake.test/chart/DOCN"),
    lambda r: r["session"].update(session_date="2026-11-04"),
])
def test_b3_after_close_receipt_must_match_retained_source_and_real_clock(tmp_path, monkeypatch, mutate):
    record = approval(tmp_path, monkeypatch)
    mutate(record)
    ledger = pilot.PilotLedger(tmp_path / "new.jsonl")
    with pytest.raises((ValueError, RuntimeError)):
        live_adapter.claim_b3_proof(ledger, record)
    assert ledger.events() == []


def test_b3_claim_rejects_old_nonempty_ledger_and_replayed_approval(tmp_path, monkeypatch):
    record = approval(tmp_path, monkeypatch)
    ledger = pilot.PilotLedger(tmp_path / "old.jsonl")
    ledger.append({"type": "attempt_claim", "phase": "A"})
    before = ledger.path.read_bytes()
    with pytest.raises(RuntimeError, match="fresh empty"):
        live_adapter.claim_b3_proof(ledger, record)
    assert ledger.path.read_bytes() == before


@pytest.mark.parametrize("changes", [
    {"ticker": "NET"}, {"depth": 2}, {"extra_peer_pins": ("MSFT", "ORCL")},
    {"analysis_date": "2026-11-04"}, {"max_output_tokens": 8192}, {"max_tool_rounds": 5},
    {"analysis_cutoff_utc": "2026-11-05T17:00:00+00:00"},
    {"market_observation_cutoff": "2026-11-05T17:00:00+00:00"},
    {"context_cap": 100000}, {"analysis_timezone": "UTC"},
])
def test_b3_execution_scope_cannot_drift(tmp_path, monkeypatch, changes):
    _, ledger, spec, claim, guard = claim_scope(tmp_path, monkeypatch)
    with pytest.raises((RuntimeError, ValueError)):
        live_adapter.verify_budget_binding(claim, guard, dataclasses.replace(spec, **changes), None)
    with pytest.raises(RuntimeError):
        live_adapter.start_execution(dataclasses.replace(claim, approval_sha256="b" * 64), ledger, spec)
    assert not any(e["type"] == "execution_start" for e in ledger.events())


def test_b3_revalidates_after_close_source_at_execution_and_cli_retries_zero(tmp_path, monkeypatch):
    record, ledger, spec, claim, guard = claim_scope(tmp_path, monkeypatch)
    Path = __import__("pathlib").Path
    Path(record["session"]["docn-chart"]["path"]).write_text("{}")
    with pytest.raises((RuntimeError, ValueError)):
        live_adapter.start_execution(claim, ledger, spec)
    assert not any(e["type"] == "execution_start" for e in ledger.events())
    live_adapter.configure_isolated_env(spec, tmp_path / "isolated", openrouter_key="fake-key", sec_user_agent="fake-contact")
    config = live_adapter.fresh_default_config()
    assert int(config["llm_max_retries"]) == 0

def serial_wire(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "serialization-only.jsonl")
    guard = pilot.BudgetGuard(ledger, pilot.Decimal("3"), allowed_models={pilot.A},
                             max_calls=40, scope="proof:B3", allowed_kinds={"run"},
                             scope_ceiling=pilot.Decimal("3"))
    wire = live_adapter.OpenRouterWireGuard(guard, {pilot.A: {
        "input_per_token": "0.0016", "output_per_token": "0",
        "cache_read_per_token": "0", "cache_write_per_token": "0"}},
        max_output_tokens=100, kind="run", allowed_resolved_models={pilot.A: {pilot.A}},
        serialize_paid_requests=True)
    return ledger, wire


def paid_request():
    return Request({"model": pilot.A, "max_tokens": 100, "messages": []})


def paid_response():
    from tests.test_valuation_reference_live_adapter import Response
    return Response({"model": pilot.A, "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.1}})


def test_b3_serializes_across_sync_async_clients_before_reservation(tmp_path, monkeypatch):
    import asyncio
    import threading

    import httpx
    import httpx2

    ledger, wire = serial_wire(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def send(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return paid_response()
    async def async_send(*args, **kwargs):
        return paid_response()
    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx2.AsyncClient, "send", async_send)
    async def run():
        with live_adapter.installed_http_guard(wire):
            first = asyncio.create_task(asyncio.to_thread(httpx.Client.send, object(), paid_request()))
            assert await asyncio.to_thread(entered.wait, 3)
            second = asyncio.create_task(httpx2.AsyncClient.send(object(), paid_request()))
            await asyncio.sleep(0.03)  # The event loop must remain responsive while the sync turn holds the permit.
            assert sum(e["type"] == "reserve" for e in ledger.events()) == 1
            release.set()
            await asyncio.wait_for(asyncio.gather(first, second), 3)
    asyncio.run(run())
    assert ledger.committed_usd() == pilot.Decimal("0.2")
    assert sum(e["type"] == "reserve" for e in ledger.events()) == 2


def test_b3_cancelling_async_waiter_does_not_leak_permit_or_reserve(tmp_path, monkeypatch):
    import asyncio
    import threading

    import httpx
    import httpx2

    ledger, wire = serial_wire(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def send(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return paid_response()
    async def async_send(*args, **kwargs):
        return paid_response()
    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx2.AsyncClient, "send", async_send)
    async def run():
        with live_adapter.installed_http_guard(wire):
            first = asyncio.create_task(asyncio.to_thread(httpx.Client.send, object(), paid_request()))
            assert await asyncio.to_thread(entered.wait, 3)
            waiter = asyncio.create_task(httpx2.AsyncClient.send(object(), paid_request()))
            await asyncio.sleep(0.03)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert sum(e["type"] == "reserve" for e in ledger.events()) == 1
            release.set()
            await first
            await asyncio.wait_for(httpx2.AsyncClient.send(object(), paid_request()), 3)
    asyncio.run(run())
    assert ledger.committed_usd() == pilot.Decimal("0.2")


@pytest.mark.parametrize("cancel", [False, True])
def test_b3_failed_async_turn_releases_permit_without_refunding_unknown_cost(tmp_path, monkeypatch, cancel):
    import asyncio

    import httpx

    ledger, wire = serial_wire(tmp_path)
    entered = asyncio.Event()
    async def send(*args, **kwargs):
        entered.set()
        if cancel:
            await asyncio.Event().wait()
        raise TimeoutError()
    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    async def run():
        with live_adapter.installed_http_guard(wire):
            pending = asyncio.create_task(httpx.AsyncClient.send(object(), paid_request()))
            await entered.wait()
            if cancel:
                pending.cancel()
            with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
                await pending
            held = ledger.committed_usd()
            assert held > 0 and any(e["type"] == "unknown" for e in ledger.events())
            # No permit leak: a following request reaches the guard, which fails
            # on the retained unknown reservation rather than silently refunding it.
            with pytest.raises(RuntimeError, match="budget cap"):
                await asyncio.wait_for(httpx.AsyncClient.send(object(), paid_request()), 3)
            assert ledger.committed_usd() == held
    asyncio.run(run())


def test_serialization_is_restricted_to_new_b3_proof(tmp_path):
    ledger, wire = serial_wire(tmp_path)
    guard = pilot.BudgetGuard(ledger, pilot.Decimal("3"), allowed_models={pilot.A},
                             max_calls=40, scope="proof:A", allowed_kinds={"run"},
                             scope_ceiling=pilot.Decimal("3"))
    with pytest.raises(ValueError, match="B3"):
        live_adapter.OpenRouterWireGuard(guard, {pilot.A: {
            "input_per_token": "0.001", "output_per_token": "0",
            "cache_read_per_token": "0", "cache_write_per_token": "0"}},
            max_output_tokens=100, kind="run", allowed_resolved_models={pilot.A: {pilot.A}},
            serialize_paid_requests=True)


@pytest.mark.parametrize("dirty", [False, True])
def test_b3_start_requires_actual_clean_approved_candidate(tmp_path, monkeypatch, dirty):
    from pathlib import Path
    record, ledger, spec, claim, _ = claim_scope(tmp_path, monkeypatch)
    worktree = Path(record["worktree_root"])
    (worktree / "source.py").write_text("# changed after approval\n")
    if not dirty:
        subprocess.run(["git", "add", "source.py"], cwd=worktree, check=True)
        subprocess.run(["git", "-c", "user.name=Offline Fixture", "-c",
                        "user.email=offline@example.invalid", "commit", "-qm", "Changed fixture"],
                       cwd=worktree, check=True)
    with pytest.raises(RuntimeError, match="clean.*approved candidate HEAD"):
        live_adapter.start_execution(claim, ledger, spec)
    assert sum(e["type"] == "execution_start" for e in ledger.events()) == 1
    subprocess.run(["git", "reset", "--hard", record["candidate_head"]], cwd=worktree,
                   check=True, capture_output=True)
    with pytest.raises(RuntimeError, match="already started"):
        live_adapter.start_execution(claim, ledger, spec)

def test_harness_failure_restores_full_environment_and_imported_defaults(tmp_path):
    from cli import selections
    from tradingagents import default_config

    before_environment = dict(os.environ)
    before_environment_object = os.environ
    before_defaults = default_config.DEFAULT_CONFIG
    before_cli_defaults = selections.DEFAULT_CONFIG
    spec = live_adapter.CliSpec("DOCN", "2026-11-05", pilot.A, pilot.A, 1, 16384)
    with pytest.raises(RuntimeError, match="simulated failed proof"), restored_harness_process_state():
        live_adapter.configure_isolated_env(
            spec, tmp_path / "failed-proof", openrouter_key="fake-key",
            sec_user_agent="fake-contact")
        rebuilt = live_adapter.fresh_default_config()
        assert rebuilt["llm_provider"] == "openrouter"
        assert int(rebuilt["llm_max_retries"]) == 0
        raise RuntimeError("simulated failed proof")
    assert os.environ is before_environment_object
    assert dict(os.environ) == before_environment
    assert default_config.DEFAULT_CONFIG is before_defaults
    assert selections.DEFAULT_CONFIG is before_cli_defaults

