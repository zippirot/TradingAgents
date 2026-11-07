"""Offline qualification of the one post-Trader paid continuation."""

import importlib
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "docs/reviews/valuation-build2-proof-tools"


def load_module(monkeypatch):
    monkeypatch.syspath_prepend(str(MODULES))
    return importlib.import_module("continue_cli")


def ledger_setup(tmp_path, monkeypatch):
    c = load_module(monkeypatch)
    h = c.h
    ledger = h.PilotLedger(tmp_path / "continued.jsonl")
    monkeypatch.setattr(h, "LEDGER", ledger.path)
    receipt = {
        "rates": {
            m: {
                "input_per_token": "0.000001",
                "output_per_token": "0.00001",
                "cache_read_per_token": "0",
                "cache_write_per_token": "0",
            }
            for m in h.MODELS
        },
        "aliases": {m: [m] for m in h.MODELS},
        "observed_at": "2026-11-06T22:00:00+00:00",
        "remaining_usd": "50",
    }
    old = h.PilotLedger(tmp_path / "old.jsonl")
    old.append({"type": "reserve", "ticket": "old", "usd": "12.037824"})
    candidate = {
        "clean": True,
        "candidate_head": "a" * 40,
        "old_ledgers": {str(old.path): h.sha(old.path)},
        "prior_unknown_reserved_usd": "12.037824",
        "prior_committed_exposure_usd": "12.037824",
    }
    candidate.update(
        user_approval_sha256=c.APPROVAL_SHA,
        native_qualification_sha256=c.NATIVE_QUALIFICATION_SHA,
        checkpoint_id=c.CHECKPOINT,
        thread=c.THREAD,
        application_head=c.APPLICATION_HEAD,
        config=h.CONFIG,
    )
    for name in h.ATTEMPTS:
        ledger.append(
            {
                "type": "attempt_claim",
                "phase": name,
                "provider_receipt": receipt,
                "approval_record": candidate,
            }
        )
        ledger.append(
            {
                "type": "attempt_end",
                "name": name,
                "execution": "failed",
                "error_type": "BudgetStoppedError",
            }
        )
    rows = ledger.events()
    ledger.path.write_bytes(b"")
    for e in rows[:-1]:
        ledger.append(e)
    ledger.append(
        {"type": "reserve", "ticket": "unknown", "scope": "proof:Build2-DOCN-2", "usd": "7.698176"}
    )
    ledger.append(
        {"type": "reserve", "ticket": "billed", "scope": "proof:Build2-DOCN-1", "usd": "14"}
    )
    ledger.append({"type": "settle", "ticket": "billed", "usd": "13.3059199"})
    ledger.append({"type": "release", "ticket": "billed", "usd": "14"})
    ledger.append(rows[-1])
    monkeypatch.setattr(c, "PREFIX_BYTES", ledger.path.stat().st_size)
    monkeypatch.setattr(c, "PREFIX_SHA", h.sha(ledger.path))
    return c, ledger, candidate, {**receipt, "observed_at": datetime.now(UTC).isoformat()}


def test_continuation_claim_holds_and_no_second_launch(tmp_path, monkeypatch):
    c, ledger, candidate, receipt = ledger_setup(tmp_path, monkeypatch)
    prefix = ledger.path.read_bytes()
    for bad in (
        {**receipt, "remaining_usd": "31.73"},
        {**receipt, "observed_at": "2026-11-06T21:00:00+00:00"},
    ):
        with pytest.raises(ValueError):
            c.claim(ledger, candidate, candidate["candidate_head"], bad)
    with pytest.raises(ValueError, match="reviewed"):
        c.claim(ledger, candidate, "b" * 40, receipt)
    assert ledger.path.read_bytes() == prefix
    modified = prefix.replace(b"7.698176", b"0.000000")
    ledger.path.write_bytes(modified)
    with pytest.raises(ValueError, match="ledger changed"):
        c.claim(ledger, candidate, candidate["candidate_head"], receipt)
    ledger.path.write_bytes(prefix)
    claim = c.claim(ledger, candidate, candidate["candidate_head"], receipt)
    assert ledger.path.read_bytes().startswith(prefix)
    assert ledger.committed_usd() == Decimal("21.00409590")
    budget = c.ContinuationBudget(ledger, candidate, receipt, claim)
    budget.reserve(c.h.A, "12", kind="run")
    assert ledger.committed_usd() == Decimal("33.00409590")
    with pytest.raises(RuntimeError, match="cap"):
        budget.reserve(c.h.A, "0.01", kind="run")
    with pytest.raises(ValueError, match="already consumed"):
        c.claim(ledger, candidate, candidate["candidate_head"], receipt)
    ledger.append({"type": "continuation_end", "name": c.NAME, "execution": "failed"})
    with pytest.raises(RuntimeError, match="open authorized"):
        budget.reserve(c.h.A, "0.01", kind="run")


@pytest.mark.parametrize("kind", ["before_checkpoint", "old_role", "source", "wrong_model"])
def test_no_transport_outside_post_trader_scope(tmp_path, monkeypatch, kind):
    c, ledger, can, receipt = ledger_setup(tmp_path, monkeypatch)
    auth = c.claim(ledger, can, can["candidate_head"], receipt)
    wire = c.ContinuationWire(c.ContinuationBudget(ledger, can, receipt, auth), receipt)
    wire.checkpoint_verified = kind != "before_checkpoint"
    monkeypatch.setattr(
        "langgraph.config.get_config",
        lambda: {
            "metadata": {"langgraph_node": "Market Analyst" if kind == "old_role" else c.RISK[0]}
        },
    )
    request = httpx.Request(
        "POST",
        "https://example.invalid/source"
        if kind == "source"
        else "https://openrouter.ai/api/v1/chat/completions",
        json={
            "model": c.h.A if kind == "wrong_model" else c.h.B_DEEP,
            "max_tokens": 16384,
            "messages": [],
        },
    )
    with pytest.raises(RuntimeError):
        wire.before(request)
    assert wire.request_count == 0 and wire.roles == []


def test_both_bounded_fallbacks_fit_the_same_wire_budget(tmp_path, monkeypatch):
    c, ledger, can, receipt = ledger_setup(tmp_path, monkeypatch)
    auth = c.claim(ledger, can, can["candidate_head"], receipt)
    wire = c.ContinuationWire(c.ContinuationBudget(ledger, can, receipt, auth), receipt)
    wire.checkpoint_verified = True
    sent = []

    def transport(request):
        assert ledger.events()[-1]["type"] == "continuation_role"
        sent.append(request)
        model = json.loads(request.content)["model"]
        return httpx.Response(
            200,
            json={
                "model": model,
                "provider": "offline",
                "choices": [],
                "usage": {"prompt_tokens": 25, "completion_tokens": 12, "cost": 0.0002},
            },
        )

    with (
        httpx.Client(transport=httpx.MockTransport(transport)) as client,
        c.live.installed_http_guard(wire),
    ):
        for node in [*c.RISK, c.AUDIT, c.AUDIT, c.PM, c.PM]:
            monkeypatch.setattr(
                "langgraph.config.get_config",
                lambda node=node: {"metadata": {"langgraph_node": node}},
            )
            client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": c.h.B_DEEP if node in c.RISK else c.h.A,
                    "max_tokens": 16384,
                    "messages": [],
                },
            )
        with pytest.raises(RuntimeError, match="role or order"):
            client.post("https://openrouter.ai/api/v1/chat/completions", json={"model": c.h.A})
    assert len(sent) == 13 and c.h.accounting(ledger, c.NAME)["usage_covered_sends"] == 13


def test_exact_continuation_runner_on_private_checkpoint_with_mock_sdk_http(tmp_path, monkeypatch):
    """Optional Machine 2 drill; a copied ledger and fake transport, never a live claim."""
    import shutil
    import subprocess

    c = load_module(monkeypatch)
    if not c.ORIGINAL.exists():
        pytest.skip("Machine 2 native proof input unavailable")
    # A subprocess isolates the runner's normal environment and SDK initialization.
    result = subprocess.run(
        [sys.executable, __file__, str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-5000:]
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["usage_scope"] == "partial_observed" and summary["usage_observed_calls"] == 12
    assert summary["roles"] == [*c.RISK, c.AUDIT, c.AUDIT, c.PM]
    assert summary["feature_proof"] == "complete" and summary["source_unchanged"]
    shutil.rmtree(tmp_path / "clone")


def private_drill(tmp):
    import subprocess
    from contextlib import ExitStack

    sys.path[:0] = [str(MODULES), str(ROOT)]
    import continue_cli as c
    import httpx2
    from langgraph.config import get_config

    h = c.h
    original_ledger = h.LEDGER
    ledger = tmp / "copied-ledger.jsonl"
    original_ledger_sha = h.sha(original_ledger)
    ledger.write_bytes(original_ledger.read_bytes()[: c.PREFIX_BYTES])
    original_hashes = c.input_hashes(c.ORIGINAL)
    tail = c.prior_prefix(h.PilotLedger(original_ledger), unused=False)
    fresh = {
        **tail["provider_receipt"],
        "observed_at": datetime.now(UTC).isoformat(),
        "remaining_usd": "100",
    }
    fake = tmp / "fixture-credentials.json"
    fake.write_text(json.dumps({"OPENROUTER_API_KEY": "offline-transport-fixture"}))
    fake.chmod(0o600)
    # The receipt is the exact approved Build2 environment. Its hash and the
    # private input hashes are checked again by qualification() below. A later
    # checkout cannot satisfy live_cli.environment()'s original worktree guard.
    second_candidate = h.PRIVATE / "build2-second-candidate.json"
    if h.sha(second_candidate) != c.SECOND_SHA:
        raise ValueError("Original second candidate changed")
    fixture_environment = {**h.read(second_candidate), "clean": True}
    performed = []

    original_subprocess_run = subprocess.run
    provenance_commands = (
        ["git", "diff", "--quiet", c.APPLICATION_HEAD, "HEAD", "--", "cli", "tradingagents",
         "requirements.txt", "pyproject.toml"],
        ["git", "merge-base", "--is-ancestor", c.APPLICATION_HEAD, "HEAD"],
    )

    def offline_provenance(command, *args, **kwargs):
        # These two live checkout checks are inapplicable to this copied-ledger
        # fixture. Accept only their exact calls; leave every other subprocess
        # and the runner's private hash, authorization and budget checks live.
        if not args and kwargs == {"cwd": h.WT, "check": True} and command in provenance_commands:
            return subprocess.CompletedProcess(command, 0)
        return original_subprocess_run(command, *args, **kwargs)

    def transport(module):
        def send(_transport, request):
            node = get_config()["metadata"]["langgraph_node"]
            assert node in {*c.RISK, c.AUDIT, c.PM}
            performed.append(node)
            payload = json.loads(request.content)
            if node in c.RISK:
                output = "Offline synthetic risk reasoning."
            elif node == c.AUDIT:
                output = {} if performed.count(node) == 1 else {"findings": []}
                if performed.count(node) == 1:
                    output = {"findings": [{"type": "invalid-fixture"}]}
            else:
                output = {
                    "rating": "Hold",
                    "executive_summary": "Offline summary",
                    "investment_thesis": "Offline thesis",
                    "time_horizon": "3 months",
                    "no_case_reason": "Uncertain multiple",
                }
            msg = {
                "role": "assistant",
                "content": output if isinstance(output, str) else json.dumps(output),
            }
            reason = "stop"
            if payload.get("tools") and isinstance(output, dict):
                fn = payload["tools"][0]["function"]["name"]
                msg.update(
                    content=None,
                    tool_calls=[
                        {
                            "id": "offline",
                            "type": "function",
                            "function": {"name": fn, "arguments": json.dumps(output)},
                        }
                    ],
                )
                reason = "tool_calls"
            body = {
                "id": "gen-offline",
                "object": "chat.completion",
                "created": 1780000000,
                "model": payload["model"],
                "provider": "offline",
                "choices": [{"index": 0, "finish_reason": reason, "message": msg}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 12,
                    "total_tokens": 112,
                    "cost": 0.0002,
                },
            }
            return module.Response(
                200, headers={"content-type": "application/json"}, content=json.dumps(body).encode()
            )

        return send

    import socket

    from curl_cffi import requests as curl

    def deny(*args, **kwargs):
        raise AssertionError("Unmocked network transport in offline drill")

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    current_signature = TradingAgentsGraph._run_signature

    def frozen_build2_signature(graph, *args, **kwargs):
        # This is a historical Build2 proof against an exact private checkpoint,
        # already isolated from live checkout provenance above. B changes the
        # pre-analyst brief and intentionally gives fresh runs a different ID.
        # Keep the original graph-shape token ONLY inside this offline fixture;
        # every native checkpoint ID, pending-node and retained-input assertion
        # below remains live. This does not assert current B resume compatibility.
        return current_signature(graph, *args, **kwargs).replace(
            "shared_source_brief=4", "shared_source_brief=3").replace("|operational_delivery=1", "")

    with ExitStack() as stack:
        stack.enter_context(patch.object(TradingAgentsGraph, "_run_signature", frozen_build2_signature))
        for module in (httpx, httpx2):
            stack.enter_context(
                patch.object(module.HTTPTransport, "handle_request", transport(module))
            )
        stack.enter_context(patch.object(socket, "getaddrinfo", deny))
        for obj, names in (
            (socket.socket, ("connect", "connect_ex")),
            (curl.Session, ("request",)),
            (curl.AsyncSession, ("request",)),
        ):
            for name in names:
                stack.enter_context(patch.object(obj, name, deny))
        for obj, k, v in (
            (h, "LEDGER", ledger),
            (c, "WORK", tmp / "clone"),
            (h, "environment", lambda: fixture_environment),
            (h, "provider", lambda path: fresh),
            (c, "verify_launch_head", lambda head: None),
            (subprocess, "run", offline_provenance),
        ):
            stack.enter_context(patch.object(obj, k, v))
        with patch.object(
            sys,
            "argv",
            [
                str(c.__file__),
                "--run",
                "--candidate",
                fixture_environment["candidate_head"],
                "--credentials",
                str(fake),
            ],
        ):
            assert c.main() == 0
        result = h.read(c.WORK / "continuation-result.json")
        receipt = h.read(c.WORK / "cli-receipt.json")
        metrics = receipt["state"]["run_metrics"]
        summary = {
            "roles": performed,
            "usage_scope": metrics["token_usage_scope"],
            "usage_observed_calls": metrics["token_usage_observed_calls"],
            "feature_proof": result["feature_proof"],
            "source_unchanged": c.input_hashes(c.ORIGINAL) == original_hashes
            and h.sha(original_ledger) == original_ledger_sha,
        }
        (tmp / "summary.json").write_text(json.dumps(summary))
    return summary


if __name__ == "__main__":
    print(json.dumps(private_drill(Path(sys.argv[1])), indent=2))
