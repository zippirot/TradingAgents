"""Real CLI boundary for the November 5 proof and A7 pilot.

No credentials, approval, prices or network calls are embedded here. Calling
code must supply fresh route rates and task-specific budget authority.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import runpy
import socket
import subprocess
import sys
import threading
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import patch

from pilot import (
    B_DEEP,
    B_QUICK,
    DOMAINS,
    SLOTS,
    A,
    Approval,
    BudgetGuard,
    FrozenSourceGateway,
    PilotLedger,
    manifest_hash,
)

DOCUMENT_PROOF_SCOPE = "document-access:BuildB"
DOCUMENT_PROOF_TICKERS = ("DOCN", "MSFT", "CAT")
DOCUMENT_PROOF_PREFIX = "DocumentAccess-"

EXTRA_A_PIN_REASON = (
    "User-approved temporary peer pin for accepted-row live proof; "
    "business comparability is not established."
)


def _rate(value: str) -> Decimal:
    rate = Decimal(str(value))
    if not rate.is_finite() or rate < 0:
        raise ValueError("Route price must be a finite nonnegative decimal")
    return rate


def source_request_hash(name: str, args: tuple, kwargs: dict) -> str:
    """Canonicalize dated vendor arguments without changing their meaning."""
    def encode(value):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"Unsupported frozen source argument: {type(value).__name__}")
    payload = json.dumps({"name": name, "args": args, "kwargs": kwargs},
                         sort_keys=True, separators=(",", ":"), default=encode)
    return hashlib.sha256(payload.encode()).hexdigest()


def conservative_route_rates(metadata: dict, model_ids: set[str]) -> dict:
    """Cover every listed endpoint and long-context/cache override."""
    results = metadata.get("results") if isinstance(metadata, dict) else None
    if not isinstance(results, dict):
        raise ValueError("Provider metadata is missing model results")
    output = {}
    for model in model_ids:
        entry = results.get(model)
        endpoints = entry.get("endpoints") if isinstance(entry, dict) else None
        if not isinstance(endpoints, list) or not endpoints:
            raise ValueError("Approved model has no served endpoint metadata")
        maxima = {key: Decimal(0) for key in ("prompt", "completion", "input_cache_read",
                                                 "input_cache_write", "input_cache_write_1h")}
        for endpoint in endpoints:
            pricing = endpoint.get("pricing") if isinstance(endpoint, dict) else None
            if not isinstance(pricing, dict):
                raise ValueError("Endpoint pricing unavailable")
            tiers = [pricing, *(pricing.get("overrides") or [])]
            for tier in tiers:
                if not isinstance(tier, dict) or "prompt" not in tier or "completion" not in tier:
                    raise ValueError("Endpoint pricing tier incomplete")
                for key in maxima:
                    if key in tier:
                        maxima[key] = max(maxima[key], _rate(tier[key]))
        output[model] = {"input_per_token": str(maxima["prompt"]),
                         "output_per_token": str(maxima["completion"]),
                         "cache_read_per_token": str(maxima["input_cache_read"]),
                         "cache_write_per_token": str(max(maxima["input_cache_write"],
                                                          maxima["input_cache_write_1h"]))}
    return output


def resolved_model_ids(metadata: dict, model_ids: set[str]) -> dict[str, set[str]]:
    """Enumerate only exact model IDs and dated aliases in retained metadata."""
    results = metadata.get("results") if isinstance(metadata, dict) else None
    if not isinstance(results, dict):
        raise ValueError("Provider metadata is missing model results")
    output = {}
    for model in model_ids:
        entry = results.get(model)
        endpoints = entry.get("endpoints") if isinstance(entry, dict) else None
        if not isinstance(endpoints, list) or not endpoints:
            raise ValueError("Approved model has no served endpoint metadata")
        aliases = {model}
        for endpoint in endpoints:
            name = endpoint.get("name") if isinstance(endpoint, dict) else None
            candidate = str(name).split(" | ")[-1]
            if candidate.startswith(model + "-") and candidate[len(model) + 1:].isdigit():
                aliases.add(candidate)
        output[model] = aliases
    return output


class BudgetStoppedError(RuntimeError):
    """A stopped proof budget never authorizes another send."""


class OpenRouterWireGuard:
    """Intercept serialized HTTP requests before transmission, without retries."""
    def __init__(self, budget: BudgetGuard, route_rates: dict, *, max_output_tokens: int, kind: str,
                 network_gate: NetworkGate | None = None, allow_unfrozen_sources: bool = False,
                 allowed_resolved_models: dict[str, set[str]] | None = None,
                 context_cap: int | None = None, serialize_paid_requests: bool = False):
        if kind not in {"run", "review"} or type(max_output_tokens) is not int or max_output_tokens <= 0:
            raise ValueError("Invalid request scope")
        self.budget, self.max_output_tokens, self.kind = budget, max_output_tokens, kind
        self.network_gate = network_gate
        self.allow_unfrozen_sources = allow_unfrozen_sources
        if context_cap is not None and (type(context_cap) is not int or context_cap <= max_output_tokens):
            raise ValueError("Declared context cap must exceed output cap")
        self.context_cap = context_cap
        self.rates = {}
        for model, rates in route_rates.items():
            required = {"input_per_token", "output_per_token", "cache_read_per_token", "cache_write_per_token"}
            if not isinstance(rates, dict) or set(rates) != required:
                raise ValueError("Route rates must name input, output and cache prices")
            self.rates[model] = (max(_rate(rates[key]) for key in
                                     ("input_per_token", "cache_read_per_token", "cache_write_per_token")),
                                 _rate(rates["output_per_token"]))
        if not self.rates or set(self.rates) != budget.allowed_models:
            raise ValueError("Fresh route rates must cover exactly the approved models")
        self.allowed_resolved_models = allowed_resolved_models
        if (not isinstance(allowed_resolved_models, dict) or set(allowed_resolved_models) != set(self.rates)
                or any(not isinstance(ids, set) or model not in ids for model, ids in allowed_resolved_models.items())):
            raise ValueError("Exact verified resolved model IDs are required")
        self.request_count = 0
        self.stopped = False
        if type(serialize_paid_requests) is not bool or (serialize_paid_requests and (
                kind != "run" or (budget.scope not in {"proof:B3", "proof:Build1"} and
                budget.scope not in {f"proof:DocumentAccess:{ticker}" for ticker in DOCUMENT_PROOF_TICKERS}))):
            raise ValueError("Paid-request serialization is only approved for B3 and Build1 proofs")
        self.serialize_paid_requests = serialize_paid_requests
        self._paid_turn_lock = threading.Lock()

    @contextmanager
    def paid_turn(self, request):
        locked = self.serialize_paid_requests and request.url.host == "openrouter.ai"
        if locked:
            self._paid_turn_lock.acquire()
        try:
            yield
        finally:
            if locked:
                self._paid_turn_lock.release()

    @asynccontextmanager
    async def async_paid_turn(self, request):
        locked = self.serialize_paid_requests and request.url.host == "openrouter.ai"
        if locked:
            # A nonblocking acquire keeps both HTTPX generations on one permit.
            # Cancellation while waiting cannot acquire later and leak the lock.
            while not self._paid_turn_lock.acquire(blocking=False):
                await asyncio.sleep(0.01)
        try:
            yield
        finally:
            if locked:
                self._paid_turn_lock.release()

    def before(self, request):
        if request.url.host != "openrouter.ai":
            if self.network_gate is not None and self.network_gate.peer_capture_allowed():
                return None
            if request.headers.get("authorization"):
                if self.network_gate is not None:
                    self.network_gate.record_violation("authenticated_non_openrouter_http")
                raise RuntimeError("Authenticated non-OpenRouter HTTP request blocked")
            if self.allow_unfrozen_sources:
                return None
            if self.network_gate is not None:
                self.network_gate.record_violation("unfrozen_http_source")
            raise RuntimeError("Unfrozen HTTP source request blocked")
        if (request.url.scheme != "https" or request.url.path != "/api/v1/chat/completions"
                or request.method != "POST"):
            raise RuntimeError("Unexpected OpenRouter route")
        if self.stopped:
            raise BudgetStoppedError("Proof budget is stopped; no further send is authorized")
        body = request.content
        if not isinstance(body, bytes):
            raise ValueError("Serialized request bytes unavailable")
        payload = json.loads(body)
        model = payload.get("model")
        if model not in self.rates:
            raise RuntimeError("Unapproved serialized model")
        if payload.get("plugins") or payload.get("web_search_options") or payload.get("provider"):
            raise RuntimeError("Unbudgeted request add-on or route override")
        caps = [payload[key] for key in ("max_tokens", "max_completion_tokens") if key in payload]
        if not caps or any(type(cap) is not int or cap != self.max_output_tokens for cap in caps):
            raise RuntimeError("Serialized output cap differs from approved cap")
        if payload.get("stream"):
            raise RuntimeError("Streaming usage cannot be settled here")
        messages, tools = payload.get("messages"), payload.get("tools", [])
        if not isinstance(messages, list) or not isinstance(tools, list):
            raise RuntimeError("Serialized messages/tools are invalid")
        # One UTF-8 byte per possible input token plus conservative framing.
        input_bound = len(body) + 1024 + 64 * len(messages) + 256 * len(tools)
        if self.context_cap is not None and input_bound + self.max_output_tokens > self.context_cap:
            raise RuntimeError("Serialized request exceeds declared context cap")
        input_rate, output_rate = self.rates[model]
        upper = input_bound * input_rate + self.max_output_tokens * output_rate
        try:
            ticket = self.budget.reserve(model, str(upper), kind=self.kind)
        except RuntimeError as exc:
            self.stopped = True
            self.budget.ledger.append({"type": "budget_stop", "scope": self.budget.scope})
            raise BudgetStoppedError("Proof budget cap reached; no further send is authorized") from exc
        self.request_count += 1
        self.budget.ledger.append({"type": "request_meta", "ticket": ticket, "model": model,
                                   "body_sha256": hashlib.sha256(body).hexdigest(),
                                   "body_bytes": len(body), "input_bound_tokens": input_bound,
                                   "max_output_tokens": self.max_output_tokens})
        return ticket

    def after(self, ticket, response):
        if ticket is None:
            return
        if response.status_code >= 400 or not response.is_closed:
            self.budget.ledger.append({"type": "unknown", "ticket": ticket,
                                       "status": response.status_code})
            return
        try:
            data = response.json()
            reservation = next(e for e in self.budget.ledger.events()
                               if e.get("ticket") == ticket and e["type"] == "reserve")
            if data.get("model") not in self.allowed_resolved_models[reservation["model"]]:
                raise ValueError("Resolved model differs")
            usage = data["usage"]
            prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
            if (type(prompt) is not int or type(completion) is not int or prompt < 0 or completion < 0
                    or completion > self.max_output_tokens):
                raise ValueError("Usage invalid or beyond cap")
            cost = Decimal(str(usage["cost"]))
            if not cost.is_finite() or cost < 0 or cost > Decimal(reservation["usd"]):
                raise ValueError("Billed cost unknown or beyond reservation")
            self.budget.settle(ticket, str(cost))
            self.budget.ledger.append({"type": "response_meta", "ticket": ticket,
                                       "model": data["model"], "provider": data.get("provider"),
                                       "finish_reasons": [choice.get("finish_reason") for choice in data.get("choices", [])
                                                          if isinstance(choice, dict)],
                                       "prompt_tokens": prompt, "completion_tokens": completion,
                                       "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                                       "cache_read_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                                       "cost_usd": str(cost)})
        except (KeyError, TypeError, ValueError, InvalidOperation, StopIteration, json.JSONDecodeError) as exc:
            self.budget.ledger.append({"type": "unknown", "ticket": ticket,
                                       "status": response.status_code, "reason": type(exc).__name__})

    def failed(self, ticket, error: BaseException):
        if ticket is not None:
            self.budget.ledger.append({"type": "unknown", "ticket": ticket,
                                       "reason": type(error).__name__})


@contextmanager
def installed_http_guard(wire: OpenRouterWireGuard):
    """Patch both client generations used by this repository's OpenRouter SDK."""
    with ExitStack() as stack:
        for module_name in ("httpx", "httpx2"):
            module = __import__(module_name)
            sync = module.Client.send
            async_send = module.AsyncClient.send

            def guarded_sync(client, request, *args, _send=sync, **kwargs):
                with wire.paid_turn(request):
                    ticket = wire.before(request)
                    try:
                        if wire.network_gate is None:
                            response = _send(client, request, *args, **kwargs)
                        else:
                            with wire.network_gate.model_request() if ticket is not None else wire.network_gate.peer_capture():
                                response = _send(client, request, *args, **kwargs)
                        if wire.serialize_paid_requests and ticket is not None and not response.is_closed:
                            response.read()
                        wire.after(ticket, response)
                        return response
                    except BaseException as exc:
                        wire.failed(ticket, exc)
                        raise

            async def guarded_async(client, request, *args, _send=async_send, **kwargs):
                async with wire.async_paid_turn(request):
                    ticket = wire.before(request)
                    try:
                        if wire.network_gate is None:
                            response = await _send(client, request, *args, **kwargs)
                        else:
                            with wire.network_gate.model_request() if ticket is not None else wire.network_gate.peer_capture():
                                response = await _send(client, request, *args, **kwargs)
                        if wire.serialize_paid_requests and ticket is not None and not response.is_closed:
                            await response.aread()
                        wire.after(ticket, response)
                        return response
                    except BaseException as exc:
                        wire.failed(ticket, exc)
                        raise

            stack.enter_context(patch.object(module.Client, "send", guarded_sync))
            stack.enter_context(patch.object(module.AsyncClient, "send", guarded_async))
        yield


def review_saved_output(payload: dict, budget: BudgetGuard, *, wire: OpenRouterWireGuard,
                        api_key: str, reviewer_model: str, settings: dict, client=None) -> dict:
    """One guarded, nonstream blind review with a fixed JSON scoring contract."""
    if (wire.budget is not budget or wire.kind != "review" or set(wire.rates) != {reviewer_model}
            or settings != {"temperature": 0, "max_tokens": 4096}
            or wire.max_output_tokens != 4096 or budget.allowed_kinds != {"review"}
            or budget.allowed_models != {reviewer_model} or budget.scope != "reviews"
            or not api_key):
        raise ValueError("Reviewer request differs from fixed approved settings")
    if (not isinstance(payload, dict) or not all(key in payload for key in
            ("opaque_id", "evidence", "analysis", "debates", "rubric"))):
        raise ValueError("Blind reviewer payload is incomplete")
    import httpx2
    own_client = client is None
    if own_client:
        client = httpx2.Client(timeout=120)
    body = {"model": reviewer_model, "temperature": 0, "max_tokens": 4096,
            "stream": False, "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": (
                    "You are a blind evidence reviewer. Score 0 to 5 using only the supplied "
                    "rubric and retained evidence. Corroborate substantive claims with specific "
                    "source labels, check calculations and contradictions. Do not use stock outcome, "
                    "writing style, or any run audit verdict. Return only JSON with integer score "
                    "and a list of concise findings.")},
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ]}
    before = wire.request_count
    try:
        with installed_http_guard(wire):
            response = client.post("https://openrouter.ai/api/v1/chat/completions",
                                   headers={"Authorization": f"Bearer {api_key}"}, json=body)
        response.raise_for_status()
        if wire.request_count != before + 1 or budget.outstanding:
            raise RuntimeError("Reviewer call count or provider settlement unverified")
        data = response.json()
        parsed = json.loads(data["choices"][0]["message"]["content"])
        score, findings = parsed["score"], parsed["findings"]
        if (type(score) is not int or not 0 <= score <= 5 or not isinstance(findings, list)
                or len(findings) > 20 or any(not isinstance(item, str) or not item.strip()
                                              or len(item) > 1000 for item in findings)):
            raise ValueError("Reviewer score or findings invalid")
        settled = [event for event in budget.ledger.events()
                   if event.get("type") == "response_meta" and event.get("model") in
                   wire.allowed_resolved_models[reviewer_model]]
        if not settled:
            raise RuntimeError("Reviewer provider cost missing")
        return {"model_id": reviewer_model, "settings": dict(settings), "score": score,
                "findings": findings, "cost_usd": settled[-1]["cost_usd"]}
    finally:
        if own_client:
            client.close()


class NetworkGate:
    """Deny unexpected direct network traffic during a frozen CLI run."""
    def __init__(self):
        self.local = threading.local()
        self.violations: list[str] = []

    def record_violation(self, reason: str):
        self.violations.append(reason)

    def peer_capture_allowed(self) -> bool:
        return getattr(self.local, "mode", None) == "peer"

    @contextmanager
    def _allow(self, mode):
        previous = getattr(self.local, "mode", None)
        self.local.mode = mode
        try:
            yield
        finally:
            self.local.mode = previous

    def peer_capture(self):
        return self._allow("peer")

    def model_request(self):
        return self._allow("model")


@contextmanager
def installed_network_gate(gate: NetworkGate):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    def checked_connect(sock, address):
        if getattr(gate.local, "mode", None) not in {"model", "peer"}:
            gate.record_violation("unrouted_socket")
            raise RuntimeError("Uncaptured network connection blocked")
        return original_connect(sock, address)
    def checked_connect_ex(sock, address):
        if getattr(gate.local, "mode", None) not in {"model", "peer"}:
            gate.record_violation("unrouted_socket")
            raise RuntimeError("Uncaptured network connection blocked")
        return original_connect_ex(sock, address)
    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, "connect", checked_connect))
        stack.enter_context(patch.object(socket.socket, "connect_ex", checked_connect_ex))
        try:
            import curl_cffi.requests as curl_requests
        except ImportError:
            curl_requests = None
        if curl_requests is not None:
            original_curl = curl_requests.Session.request
            def checked_curl(session, *args, **kwargs):
                if not gate.peer_capture_allowed():
                    gate.record_violation("unrouted_curl")
                    raise RuntimeError("Uncaptured curl source request blocked")
                return original_curl(session, *args, **kwargs)
            stack.enter_context(patch.object(curl_requests.Session, "request", checked_curl))
        yield


class ProofAttemptLedger:
    """New Part A/B proof authority; never reads the historical DOCN ledger."""
    def __init__(self, ledger: PilotLedger, *, ceiling_usd: str, max_attempts: int):
        ceiling = Decimal(ceiling_usd)
        if not ceiling.is_finite() or ceiling <= 0 or ceiling > Decimal("10") or max_attempts != 2:
            raise ValueError("The proof ceiling and two-attempt authority must be explicit")
        self.ledger, self.ceiling = ledger, ceiling

    def claim(self, phase: str, *, part_b_go_ahead: bool = False,
              phase_ceiling_usd: str | None = None):
        if phase not in {"A", "B"}:
            raise ValueError("Unknown proof phase")
        if phase == "B" and not part_b_go_ahead:
            raise RuntimeError("Part B requires its later explicit go-ahead")
        phase_ceiling = Decimal(phase_ceiling_usd) if phase_ceiling_usd is not None else self.ceiling
        if not phase_ceiling.is_finite() or phase_ceiling <= 0 or phase_ceiling > self.ceiling:
            raise ValueError("Invalid proof phase budget")
        with self.ledger.budget_lock():
            events = self.ledger.events()
            claims = [e for e in events if e["type"] == "attempt_claim"]
            if any(e["phase"] == phase for e in claims):
                raise RuntimeError("Proof phase already claimed; failed attempts count")
            if (sum(e["phase"] in {"A", "B"} for e in claims) >= 2
                    or (phase == "B" and not any(e["phase"] == "A" for e in claims))):
                raise RuntimeError("Proof attempt sequence or cap reached")
            if self.ledger.committed_usd() >= self.ceiling:
                raise RuntimeError("Proof spending ceiling reached")
            self.ledger.append({"type": "attempt_claim", "phase": phase,
                                "ceiling_usd": str(self.ceiling),
                                "phase_ceiling_usd": str(phase_ceiling)})

    def claim_extra_a(self, approval_record: dict) -> str:
        """Consume the one explicitly approved extra Part A attempt."""
        required = {"approval_id", "approved_at_recorded", "user_response",
                    "prior_decision_fingerprint", "phase", "additional_attempts",
                    "phase_ceiling_usd", "aggregate_ceiling_usd", "temporary_peers",
                    "scope", "part_b_authorized", "comparison_authorized"}
        if not isinstance(approval_record, dict) or set(approval_record) != required:
            raise ValueError("Extra A approval record is incomplete")
        try:
            approved_at = datetime.fromisoformat(approval_record["approved_at_recorded"])
            valid = (isinstance(approval_record["approval_id"], str)
                     and bool(approval_record["approval_id"].strip())
                     and approved_at.tzinfo is not None
                     and isinstance(approval_record["scope"], str)
                     and bool(approval_record["scope"].strip())
                     and re.fullmatch(r"[0-9a-f]{64}", approval_record["prior_decision_fingerprint"])
                     and approval_record["user_response"] == "Approved"
                     and approval_record["phase"] == "A-extra"
                     and type(approval_record["additional_attempts"]) is int
                     and approval_record["additional_attempts"] == 1
                     and Decimal(approval_record["phase_ceiling_usd"]) == Decimal("3.85")
                     and Decimal(approval_record["aggregate_ceiling_usd"]) == self.ceiling == Decimal("10")
                     and approval_record["temporary_peers"] == ["MSFT", "ORCL"]
                     and approval_record["part_b_authorized"] is False
                     and approval_record["comparison_authorized"] is False)
        except (ValueError, TypeError, KeyError, InvalidOperation):
            valid = False
        if not valid:
            raise ValueError("Extra A approval record differs from explicit user approval")
        digest = manifest_hash(approval_record)
        with self.ledger.budget_lock():
            events = self.ledger.events()
            if not any(e["type"] == "attempt_claim" and e.get("phase") == "A" for e in events) or not any(
                e["type"] == "execution_start" and e.get("kind") == "proof" and e.get("name") == "A"
                for e in events
            ):
                raise RuntimeError("Extra A requires the original A proof execution")
            if any(e["type"] == "attempt_claim" and e.get("phase") == "A2" for e in events):
                raise RuntimeError("Extra A already claimed; failed attempts count")
            if self.ledger.committed_usd() + Decimal("3.85") > self.ceiling:
                raise RuntimeError("Original proof aggregate budget has insufficient headroom")
            self.ledger.append({"type": "attempt_claim", "phase": "A2",
                                "ceiling_usd": str(self.ceiling), "phase_ceiling_usd": "3.85",
                                "approval_sha256": digest,
                                "approval_id": approval_record["approval_id"],
                                "approved_pins": ["MSFT", "ORCL"]})
        return digest



def _b3_aware_time(value, now):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.astimezone(UTC) > now:
        raise ValueError("B3 proof needs observed, aware timestamps no later than now")
    return parsed.astimezone(UTC)


def _validate_b3_approval(record):
    """Validate the new authority and retained close receipt; never fetch."""
    required = {"approval_id", "approved_at_recorded", "user_instruction", "phase",
                "attempts", "ceiling_usd", "ticker", "analysis_date", "quick_model",
                "deep_model", "depth", "max_output_tokens", "max_tool_rounds",
                "candidate_head", "worktree_root", "session"}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError("B3 approval record is incomplete")
    now = datetime.now(UTC)
    _b3_aware_time(record["approved_at_recorded"], now)
    if (not isinstance(record["approval_id"], str) or not record["approval_id"].strip()
            or not isinstance(record["user_instruction"], str) or not record["user_instruction"].strip()
            or record["phase"] != "B3" or type(record["attempts"]) is not int or record["attempts"] != 1
            or Decimal(record["ceiling_usd"]) != Decimal("3")
            or record["ticker"] != "DOCN" or record["quick_model"] != A or record["deep_model"] != A
            or type(record["depth"]) is not int or record["depth"] != 1
            or type(record["max_output_tokens"]) is not int or not 1 <= record["max_output_tokens"] <= 16384
            or type(record["max_tool_rounds"]) is not int or not 1 <= record["max_tool_rounds"] <= 4
            or not isinstance(record["candidate_head"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", record["candidate_head"])):
        raise ValueError("B3 approval differs from the one-attempt three-dollar DOCN authority")
    worktree = Path(record["worktree_root"])
    if not worktree.is_absolute() or worktree.is_symlink() or not worktree.is_dir():
        raise ValueError("B3 proof needs its explicit existing worktree root")
    return _validate_after_close_receipt(record, now)


def _validate_after_close_receipt(record, now):
    """Validate retained close metadata against the actual clock; no fetch."""
    from zoneinfo import ZoneInfo

    analysis_date = date.fromisoformat(record["analysis_date"])
    if now.astimezone(ZoneInfo("America/New_York")).date() != analysis_date:
        raise ValueError("B3 proof must use the current New York session date")
    session = record["session"]
    if not isinstance(session, dict) or session.get("session_date") != str(analysis_date):
        raise ValueError("B3 session date differs from the approved analysis date")
    _b3_aware_time(session["observed_at"], now)
    close = _b3_aware_time(session["regular_close_utc"], now)
    if close.astimezone(ZoneInfo("America/New_York")).date() != analysis_date or now <= close:
        raise ValueError("B3 proof must start after the observed regular close")
    retained = {}
    for name, urls in (
        ("nyse-calendar", {"https://www.nyse.com/trade/hours-calendars"}),
        ("docn-chart", {
            "https://query1.finance.yahoo.com/v8/finance/chart/DOCN?interval=1d&range=1d",
            "https://query2.finance.yahoo.com/v8/finance/chart/DOCN?interval=1d&range=1d",
        }),
    ):
        source = session[name]
        if (not isinstance(source, dict) or source.get("url") not in urls
                or type(source.get("http_status")) is not int or source["http_status"] != 200):
            raise ValueError("B3 requires successful retained official calendar and source metadata")
        observed = _b3_aware_time(source["retrieved_at"], now)
        if observed < close or observed.astimezone(ZoneInfo("America/New_York")).date() != analysis_date:
            raise ValueError("B3 close metadata must be observed after this session's close")
        path = Path(source["path"])
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or not 1 <= path.stat().st_size <= 2_000_000):
            raise ValueError("B3 source receipt path is missing or unsafe")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != source["sha256"]:
            raise ValueError("B3 retained close source hash differs")
        retained[name] = payload
    meta = json.loads(retained["docn-chart"])["chart"]["result"][0]["meta"]
    regular = meta["currentTradingPeriod"]["regular"]
    if (meta.get("symbol") != "DOCN" or meta.get("currency") != "USD"
            or meta.get("exchangeTimezoneName") != "America/New_York"
            or type(regular.get("start")) is not int or type(regular.get("end")) is not int
            or not 0 < regular["end"] - regular["start"] <= 8 * 3600
            or datetime.fromtimestamp(regular["end"], UTC) != close
            or datetime.fromtimestamp(regular["start"], UTC).astimezone(
                ZoneInfo("America/New_York")).date() != analysis_date):
        raise ValueError("B3 retained provider regular session differs from the close receipt")
    return record


def _verify_run_fixes_machine():
    cpu = subprocess.check_output(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    ram = int(subprocess.check_output(["/usr/sbin/sysctl", "-n", "hw.memsize"], text=True))
    if (cpu, ram) != ("Apple M1 Pro", 17179869184):
        raise RuntimeError("Build1 proof must execute on the approved Machine 1")


def _validate_run_fixes_approval(record):
    """Fresh $24 allowance, $12 Build1 only; old unused authority is superseded."""
    required = {"approval_id", "approved_at_recorded", "user_instruction", "phase", "attempts",
                "ceiling_usd", "phase_ceiling_usd", "ticker", "analysis_date", "quick_model",
                "deep_model", "depth", "max_output_tokens", "max_tool_rounds", "candidate_head",
                "worktree_root", "session", "old_ledgers", "authorized_builds", "analysts",
                "llm_max_retries", "machine", "repository_origin", "supersedes_unused_authority"}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError("Run-fixes approval record is incomplete")
    now = datetime.now(UTC)
    _b3_aware_time(record["approved_at_recorded"], now)
    if (not isinstance(record["approval_id"], str) or not record["approval_id"].strip()
            or not isinstance(record["user_instruction"], str) or not record["user_instruction"].strip()
            or record["phase"] != "Build1" or type(record["attempts"]) is not int or record["attempts"] != 2
            or Decimal(record["ceiling_usd"]) != Decimal("24")
            or Decimal(record["phase_ceiling_usd"]) != Decimal("12")
            or record["authorized_builds"] != ["Build1"]
            or record["supersedes_unused_authority"] is not True
            or record["ticker"] != "DOCN" or record["quick_model"] != B_DEEP or record["deep_model"] != A
            or type(record["depth"]) is not int or record["depth"] != 1
            or type(record["max_output_tokens"]) is not int or record["max_output_tokens"] != 16384
            or type(record["max_tool_rounds"]) is not int or record["max_tool_rounds"] != 4
            or type(record["llm_max_retries"]) is not int or record["llm_max_retries"] != 0
            or record["analysts"] != ["market", "social", "news", "fundamentals"]
            or record["machine"] != {"cpu": "Apple M1 Pro", "ram_bytes": 17179869184}
            or not isinstance(record["repository_origin"], str) or not record["repository_origin"]
            or not isinstance(record["candidate_head"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", record["candidate_head"])):
        raise ValueError("Run-fixes approval differs from the $24/two-attempt split-model authority")
    worktree = Path(record["worktree_root"])
    if not worktree.is_absolute() or worktree.is_symlink() or not worktree.is_dir():
        raise ValueError("Run-fixes needs its explicit existing worktree root")
    historical = record["old_ledgers"]
    if not isinstance(historical, dict) or not historical:
        raise ValueError("Historical authority hashes are required")
    for name, digest in historical.items():
        path = Path(name)
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("Historical authority ledger changed")
    return _validate_after_close_receipt(record, now)


def claim_run_fixes_proof(ledger: PilotLedger, approval_record: dict) -> str:
    """One Build1 claim on the fresh allowance; Build2 requires later authority."""
    _validate_run_fixes_approval(approval_record)
    if str(ledger.path.resolve()) in approval_record["old_ledgers"]:
        raise RuntimeError("Historical authority cannot be reused")
    digest = manifest_hash(approval_record)
    with ledger.budget_lock():
        if ledger.events():
            raise RuntimeError("Run-fixes needs a fresh ledger; failed attempts count")
        ledger.append({"type": "allowance", "approval_sha256": digest,
                       "aggregate_ceiling_usd": "24", "attempts": 2,
                       "per_build_ceiling_usd": "12", "authorized_builds": ["Build1"],
                       "supersedes_unused_authority": True,
                       "old_ledgers": approval_record["old_ledgers"]})
        ledger.append({"type": "attempt_claim", "phase": "Build1", "ceiling_usd": "24",
                       "phase_ceiling_usd": "12", "approval_sha256": digest,
                       "approval_record": approval_record})
    return digest


def _verify_run_fixes_execution(claim, entry, spec):
    record = _validate_run_fixes_approval(entry["approval_record"])
    expected = ("DOCN", record["analysis_date"], B_DEEP, A, 1, 16384, 4)
    actual = (spec.ticker, spec.analysis_date, spec.quick_model, spec.deep_model,
              spec.depth, spec.max_output_tokens, spec.max_tool_rounds)
    if (claim.approval_sha256 != entry.get("approval_sha256")
            or manifest_hash(record) != entry["approval_sha256"] or actual != expected
            or spec.proof_scope != "run-fixes:Build1" or spec.extra_peer_pins is not None
            or spec.analysis_cutoff_utc is not None or spec.market_observation_cutoff is not None
            or spec.context_cap is not None or spec.analysis_timezone != "America/Denver"
            or entry.get("ceiling_usd") != "24" or entry.get("phase_ceiling_usd") != "12"):
        raise RuntimeError("Build1 proof execution differs from its fresh approved authority")
    spec.validate()


def verify_run_fixes_completed_state(state, spec, record):
    """Recheck the canonical completed price from retained source, never fetch."""
    from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation

    price = validate_price_observation(state.get("price_observation"), spec.ticker, spec.analysis_date)
    close = datetime.fromisoformat(record["session"]["regular_close_utc"])
    observed = datetime.fromisoformat(price["raw_source"]["observation_cutoff"])
    if (price.get("status") != "available" or price.get("session_status") != "completed"
            or price.get("session_date") != spec.analysis_date or observed < close):
        raise RuntimeError("Build1 requires the actual analysis-date completed close")



def verify_document_access_completed_state(state, spec, record):
    """Accept only a canonical completed close or an explicit missing-close fallback."""
    from tradingagents.dataflows.vendors.yahoo.price_observation import validate_price_observation

    price = validate_price_observation(state.get("price_observation"), spec.ticker, spec.analysis_date)
    close = datetime.fromisoformat(record["session"]["regular_close_utc"])
    observed = datetime.fromisoformat(
        price["raw_source"].get("observation_cutoff") or price["raw_source"]["retrieved_at"]
    )
    if (close.tzinfo is None or observed.tzinfo is None or observed < close
            or price.get("status") != "available"
            or price.get("session_status") != "completed"):
        raise RuntimeError("Document proof requires a canonical post-close price observation")
    if price.get("session_date") == spec.analysis_date:
        if price.get("price_fallback"):
            raise RuntimeError("Current-session close must not carry a fallback")
        return {"requested_session_date": spec.analysis_date,
                "selected_session_date": price["session_date"],
                "observation_cutoff": observed.isoformat(), "price_fallback": None}
    fallback = price.get("price_fallback")
    if (not isinstance(fallback, dict)
            or fallback.get("reason")
            != "Latest completed session has no close; using last valid completed session"
            or fallback.get("latest_completed_session_date") != spec.analysis_date
            or fallback.get("selected_session_date") != price.get("session_date")
            or spec.analysis_date not in fallback.get("missing_completed_session_dates", [])):
        raise RuntimeError("Document proof prior close lacks explicit analysis-date fallback")
    return {"requested_session_date": spec.analysis_date,
            "selected_session_date": price["session_date"],
            "observation_cutoff": observed.isoformat(), "price_fallback": fallback}



def claim_b3_proof(ledger: PilotLedger, approval_record: dict) -> str:
    """Claim the separately authorized one-shot B3 proof on a new empty ledger."""
    _validate_b3_approval(approval_record)
    digest = manifest_hash(approval_record)
    with ledger.budget_lock():
        if ledger.events():
            raise RuntimeError("B3 requires a fresh empty ledger; no retry or historical authority reuse")
        ledger.append({"type": "attempt_claim", "phase": "B3", "ceiling_usd": "3",
                       "phase_ceiling_usd": "3", "approval_sha256": digest,
                       "approval_record": approval_record})
    return digest


def _verify_b3_execution(claim, entry, spec):
    try:
        record = _validate_b3_approval(entry["approval_record"])
        expected = ("DOCN", record["analysis_date"], A, A, 1,
                    record["max_output_tokens"], record["max_tool_rounds"])
        actual = (spec.ticker, spec.analysis_date, spec.quick_model, spec.deep_model,
                  spec.depth, spec.max_output_tokens, spec.max_tool_rounds)
        if (claim.approval_sha256 != entry.get("approval_sha256")
                or manifest_hash(record) != entry["approval_sha256"] or actual != expected
                or spec.extra_peer_pins is not None
                or spec.analysis_cutoff_utc is not None or spec.market_observation_cutoff is not None
                or spec.context_cap is not None or spec.analysis_timezone != "America/Denver"
                or entry.get("ceiling_usd") != "3" or entry.get("phase_ceiling_usd") != "3"):
            raise ValueError("B3 execution differs from its approved scope")
        spec.validate()
    except (KeyError, TypeError, ValueError, InvalidOperation, OSError, IndexError) as exc:
        raise RuntimeError("B3 proof approval, close receipt or execution scope is invalid") from exc


@dataclass(frozen=True)
class ExecutionClaim:
    kind: str
    name: str
    approval_sha256: str | None = None


def verify_execution_claim(claim: ExecutionClaim, ledger: PilotLedger, spec: CliSpec):
    events = ledger.events()
    if claim.kind == "proof" and claim.name.startswith(DOCUMENT_PROOF_PREFIX):
        ticker = claim.name[len(DOCUMENT_PROOF_PREFIX):]
        entry = next((e for e in events if e.get("type") == "attempt_claim"
                      and e.get("phase") == claim.name), None)
        if ticker not in DOCUMENT_PROOF_TICKERS or entry is None:
            raise RuntimeError("Document-access attempt claim missing")
        record = _validate_document_access_approval(entry["approval_record"])
        expected = (ticker, record["analysis_date"], B_DEEP, A, 3, 16384, 4)
        actual = (spec.ticker, spec.analysis_date, spec.quick_model, spec.deep_model,
                  spec.depth, spec.max_output_tokens, spec.max_tool_rounds)
        allowance = [e for e in events if e.get("type") == "allowance"]
        if (claim.approval_sha256 != entry.get("approval_sha256")
                or ledger.path.resolve() != Path(record["ledger_path"]).resolve()
                or manifest_hash(record) != claim.approval_sha256
                or len(allowance) != 1
                or allowance[0].get("approval_sha256") != (
                    _document_final_slot_amendment(record, ledger, claimed=True)
                    if record.get("final_slot_amendment") and ticker == "CAT"
                    else claim.approval_sha256)
                or actual != expected or spec.proof_scope != DOCUMENT_PROOF_SCOPE
                or spec.extra_peer_pins is not None or spec.context_cap is not None
                or spec.analysis_timezone != "America/Denver"):
            raise RuntimeError("Document-access proof execution differs from approved scope")
        spec.validate()
        return
    if claim.kind == "proof":
        entry = next((e for e in events if e["type"] == "attempt_claim"
                      and e.get("phase") == claim.name), None)
        if claim.name == "Build1":
            if entry is None:
                raise RuntimeError("Fresh Build1 proof attempt claim is missing")
            allowance = [e for e in events if e["type"] == "allowance"]
            if (len(allowance) != 1 or allowance[0].get("approval_sha256") != claim.approval_sha256
                    or sum(e["type"] == "attempt_claim" for e in events) != 1):
                raise RuntimeError("Build1 allowance marker or attempt count differs")
            _verify_run_fixes_execution(claim, entry, spec)
            return
        if claim.name == "B3":
            if entry is None:
                raise RuntimeError("Separate B3 proof attempt claim is missing")
            _verify_b3_execution(claim, entry, spec)
            return
        if (claim.name not in {"A", "A2", "B"} or entry is None or spec.depth != 1
                or (claim.name == "A2" and (
                    claim.approval_sha256 != entry.get("approval_sha256")
                    or spec.extra_peer_pins != tuple(entry.get("approved_pins", []))
                    or spec.ticker != "DOCN" or spec.analysis_date != "2026-11-05"
                    or spec.analysis_cutoff_utc is not None
                    or spec.market_observation_cutoff is not None))
                or (claim.name != "A2" and (claim.approval_sha256 is not None
                    or spec.extra_peer_pins is not None))):
            raise RuntimeError("Separate proof attempt claim is missing or mismatched")
    elif claim.kind == "comparison":
        slot = next((slot for slot in SLOTS if slot.name == claim.name), None)
        if (slot is None or not any(e["type"] == "slot_claim" and e.get("slot") == claim.name for e in events)
                or (spec.quick_model, spec.deep_model, spec.depth) !=
                (slot.quick_model, slot.deep_model, slot.depth)):
            raise RuntimeError("Approved A7 slot claim is missing or mismatched")
    else:
        raise RuntimeError("Unknown execution claim")


def verify_budget_binding(claim: ExecutionClaim, budget: BudgetGuard,
                          spec: CliSpec, approval: Approval | None):
    """Tie the wire guard to the exact prior claim, not a caller-made cap."""
    verify_execution_claim(claim, budget.ledger, spec)
    if budget.allowed_models != {spec.quick_model, spec.deep_model} or budget.allowed_kinds != {"run"}:
        raise RuntimeError("Wire budget model or kind differs from claimed CLI scope")
    events = budget.ledger.events()
    if claim.kind == "proof":
        entry = next(e for e in events if e["type"] == "attempt_claim" and e.get("phase") == claim.name)
        if claim.name.startswith(DOCUMENT_PROOF_PREFIX):
            record = _validate_document_access_approval(entry["approval_record"])
            if (approval is not None or budget.scope != f"proof:DocumentAccess:{spec.ticker}"
                    or budget.ceiling != Decimal(record["ceiling_usd"])
                    or budget.scope_ceiling != Decimal(record["per_attempt_ceiling_usd"])
                    or budget.max_calls != record["max_calls_per_attempt"]):
                raise RuntimeError("Document-access wire budget differs from fresh authority")
            return
        if (approval is not None or budget.scope != f"proof:{claim.name}"
                or budget.ceiling != Decimal(entry["ceiling_usd"])
                or budget.scope_ceiling != Decimal(entry["phase_ceiling_usd"])
                or budget.max_calls > 64):
            raise RuntimeError("Proof wire budget exceeds or differs from claimed authority")
    else:
        entry = next(e for e in events if e["type"] == "slot_claim" and e.get("slot") == claim.name)
        if (approval is None or entry.get("manifest_hash") != approval.approved_manifest_sha256
                or budget.scope != claim.name or budget.ceiling != Decimal(approval.ceiling_usd)
                or budget.scope_ceiling is not None or budget.max_calls > 64):
            raise RuntimeError("A7 wire budget differs from approved slot and ceiling")


def start_execution(claim: ExecutionClaim, ledger: PilotLedger, spec: CliSpec):
    """Consume a claim exactly once before any CLI work, including failed starts."""
    with ledger.budget_lock():
        verify_execution_claim(claim, ledger, spec)
        if any(e["type"] == "execution_start" and e.get("kind") == claim.kind
               and e.get("name") == claim.name for e in ledger.events()):
            raise RuntimeError("Execution claim already started; no duplicate CLI launch")
        event = {"type": "execution_start", "kind": claim.kind,
                 "name": claim.name, "ticker": spec.ticker,
                 "analysis_date": spec.analysis_date, "depth": spec.depth,
                 "approval_sha256": claim.approval_sha256}
        if claim.kind == "proof" and (claim.name in {"B3", "Build1"} or claim.name.startswith(DOCUMENT_PROOF_PREFIX)):
            entry = next(e for e in ledger.events() if e["type"] == "attempt_claim" and e.get("phase") == claim.name)
            record = entry["approval_record"]
            worktree = Path(record["worktree_root"])
            event.update(worktree_root=str(worktree), approved_candidate_head=record["candidate_head"])
            # A legitimate start consumes the attempt even if its candidate
            # subsequently fails the final check. No CLI/paid call precedes it.
            ledger.append(event)
            if claim.name == "Build1" or claim.name.startswith(DOCUMENT_PROOF_PREFIX):
                _verify_run_fixes_machine()
                origin = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=worktree, text=True).strip()
                if origin != record["repository_origin"]:
                    raise RuntimeError("Build1 candidate repository origin differs")
                top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=worktree, text=True).strip()
                if Path(top).resolve() != worktree.resolve():
                    raise RuntimeError("Build1 candidate worktree root differs")
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip()
            dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=worktree, text=True)
            if head != record["candidate_head"] or dirty:
                raise RuntimeError("B3 proof worktree must be clean at the approved candidate HEAD")
            ledger.append({"type": "candidate_verified", "kind": "proof", "name": claim.name,
                           "worktree_root": str(worktree), "head": head, "clean": True})
            return
        ledger.append(event)


@dataclass(frozen=True)
class CliSpec:
    ticker: str
    analysis_date: str
    quick_model: str
    deep_model: str
    depth: int
    max_output_tokens: int
    max_tool_rounds: int = 4
    analysis_timezone: str = "America/Denver"
    analysis_cutoff_utc: str | None = None
    market_observation_cutoff: str | None = None
    context_cap: int | None = None
    extra_peer_pins: tuple[str, str] | None = None
    proof_scope: str | None = None

    def validate(self):
        if (not self.ticker or not self.ticker.isupper() or self.depth not in (1, 2, 3)
                or self.max_output_tokens <= 0 or self.max_tool_rounds <= 0):
            raise ValueError("Invalid fixed CLI scope")
        date.fromisoformat(self.analysis_date)
        for cutoff in (self.analysis_cutoff_utc, self.market_observation_cutoff):
            if cutoff is not None and datetime.fromisoformat(cutoff).tzinfo is None:
                raise ValueError("CLI cutoff must include timezone")
        if self.depth == 2 and (self.analysis_cutoff_utc is None or self.market_observation_cutoff is None):
            raise ValueError("A7 requires frozen analysis and market cutoffs")
        if self.depth == 2 and (type(self.context_cap) is not int or self.context_cap <= self.max_output_tokens):
            raise ValueError("A7 requires a declared context cap above the output cap")
        if self.market_observation_cutoff is not None and datetime.fromisoformat(
            self.market_observation_cutoff
        ).astimezone(UTC) > datetime.now(UTC):
            raise ValueError("Frozen market observation cutoff cannot be in the future")
        expected_models = (B_DEEP, A) if self.proof_scope == "run-fixes:Build1" else (A, A)
        if self.proof_scope not in {None, "run-fixes:Build1", DOCUMENT_PROOF_SCOPE}:
            raise ValueError("Unknown CLI proof scope")
        if self.proof_scope == DOCUMENT_PROOF_SCOPE:
            if (self.ticker not in DOCUMENT_PROOF_TICKERS or self.depth != 3
                    or (self.quick_model, self.deep_model) != (B_DEEP, A)
                    or self.max_output_tokens != 16384 or self.max_tool_rounds != 4
                    or self.extra_peer_pins is not None or self.context_cap is not None
                    or self.analysis_cutoff_utc is not None
                    or self.market_observation_cutoff is not None):
                raise ValueError("Document-access proof scope differs")
        elif self.depth == 3:
            raise ValueError("Depth 3 is reserved for document-access proof")
        if self.depth == 1 and (self.quick_model, self.deep_model) != expected_models:
            raise ValueError("Proof model tiers differ from the declared authority")
        if self.extra_peer_pins is not None and (
            self.depth != 1 or self.ticker != "DOCN" or self.extra_peer_pins != ("MSFT", "ORCL")
        ):
            raise ValueError("Extra A pins must be exactly MSFT and ORCL for DOCN")
        if self.depth == 2 and (self.quick_model, self.deep_model) not in {(A, A), (B_QUICK, B_DEEP)}:
            raise ValueError("A7 CLI models must match setup A or B exactly")


def verify_cli_config(config: dict, spec: CliSpec):
    spec.validate()
    expected = {"llm_provider": "openrouter", "quick_think_llm": spec.quick_model,
                "deep_think_llm": spec.deep_model, "backend_url": "https://openrouter.ai/api/v1",
                "max_debate_rounds": spec.depth, "max_risk_discuss_rounds": spec.depth,
                "max_tool_rounds": spec.max_tool_rounds, "max_tokens": spec.max_output_tokens,
                "llm_max_retries": 0, "analysis_timezone": spec.analysis_timezone}
    if spec.analysis_cutoff_utc is not None:
        expected["analysis_cutoff_utc"] = spec.analysis_cutoff_utc
    for key, value in expected.items():
        actual = config.get(key)
        if str(actual).lower() != str(value).lower():
            raise RuntimeError(f"Actual CLI {key} differs from fixed proof scope")
    if any(config.get(f"{tier}_think_provider") not in (None, "openrouter") for tier in ("quick", "deep")):
        raise RuntimeError("CLI tier provider override differs from OpenRouter")
    if any(config.get(f"{tier}_think_backend_url") for tier in ("quick", "deep")):
        raise RuntimeError("CLI tier backend override differs from fixed route")


def configure_isolated_env(spec: CliSpec, work: Path, *, openrouter_key: str, sec_user_agent: str,
                           claim: ExecutionClaim | None = None, ledger: PilotLedger | None = None,
                           source_credentials: dict[str, str] | None = None):
    """Set the actual CLI env without reading user preferences or mutating them."""
    spec.validate()
    if not openrouter_key or not sec_user_agent or work.is_symlink():
        raise ValueError("Proof workdir or required credentials invalid")
    if spec.proof_scope == DOCUMENT_PROOF_SCOPE:
        if (not isinstance(source_credentials, dict)
                or set(source_credentials) != {"FRED_API_KEY", "ALPHA_VANTAGE_API_KEY"}
                or any(not isinstance(value, str) or not value for value in source_credentials.values())):
            raise ValueError("Document proof needs exactly the approved macro/transcript credentials")
    elif source_credentials is not None:
        raise ValueError("Additional source credentials are reserved for document proof")
    if spec.extra_peer_pins is not None:
        if claim is None or ledger is None:
            raise ValueError("Extra A pins require the approved A2 execution claim")
        verify_execution_claim(claim, ledger, spec)
    for name in list(os.environ):
        if name.startswith("TRADINGAGENTS_") or name.endswith("_API_KEY"):
            del os.environ[name]
    values = {
        "PYTHON_DOTENV_DISABLED": "1",
        "OPENROUTER_API_KEY": openrouter_key, "SEC_EDGAR_USER_AGENT": sec_user_agent,
        "TRADINGAGENTS_RESULTS_DIR": str(work / "results"),
        "TRADINGAGENTS_CACHE_DIR": str(work / "cache"),
        "TRADINGAGENTS_MEMORY_LOG_PATH": str(work / "memory/trading_memory.md"),
        "TRADINGAGENTS_PREFS_PATH": str(work / "cli_prefs.json"),
        "TRADINGAGENTS_LLM_PROVIDER": "openrouter",
        "TRADINGAGENTS_QUICK_THINK_LLM": spec.quick_model,
        "TRADINGAGENTS_DEEP_THINK_LLM": spec.deep_model,
        "TRADINGAGENTS_LLM_BACKEND_URL": "https://openrouter.ai/api/v1",
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS": str(spec.depth),
        "TRADINGAGENTS_MAX_RISK_ROUNDS": str(spec.depth),
        "TRADINGAGENTS_MAX_TOOL_ROUNDS": str(spec.max_tool_rounds),
        "TRADINGAGENTS_MAX_TOKENS": str(spec.max_output_tokens),
        "TRADINGAGENTS_LLM_MAX_RETRIES": "0",
        "TRADINGAGENTS_ANALYSIS_TIMEZONE": spec.analysis_timezone,
        "TRADINGAGENTS_NO_UPDATE_CHECK": "1",
    }
    if spec.analysis_cutoff_utc is not None:
        values["TRADINGAGENTS_ANALYSIS_CUTOFF_UTC"] = spec.analysis_cutoff_utc
    os.environ.update(values)
    if source_credentials is not None:
        os.environ.update(source_credentials)
    for path in (work / "results", work / "cache", work / "memory"):
        path.mkdir(parents=True, exist_ok=True)
    if spec.extra_peer_pins is not None:
        pins_path = work / "approved-peer-pins.json"
        rows = [{"ticker": ticker, "reason": EXTRA_A_PIN_REASON}
                for ticker in spec.extra_peer_pins]
        with pins_path.open("x") as handle:
            json.dump({spec.ticker: rows}, handle, sort_keys=True)
        os.environ["TRADINGAGENTS_PEERS_FILE"] = str(pins_path)
    import yfinance as yf
    tz_cache = work / "cache/yfinance"
    tz_cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(tz_cache))


def fresh_default_config() -> dict:
    """Rebuild imported config references after isolation env is installed."""
    from tradingagents import default_config
    rebuilt = default_config.build_default_config()
    default_config.DEFAULT_CONFIG = rebuilt
    for name in ("cli.run", "cli.selections", "cli.main", "tradingagents.graph.trading_graph"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "DEFAULT_CONFIG"):
            module.DEFAULT_CONFIG = rebuilt
    return rebuilt


def install_starting_snapshot(gateway: FrozenSourceGateway, work: Path):
    """Copy the same retained memory/publication tree into each fresh workdir."""
    memory = gateway.common("memory")
    memory_path = work / "memory/trading_memory.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    with memory_path.open("xb") as handle:
        handle.write(memory)
    publications = json.loads(gateway.common("prior_publication"))
    if not isinstance(publications, dict) or set(publications) != {"files"} or not isinstance(publications["files"], dict):
        raise ValueError("Prior-publication snapshot shape invalid")
    root = work / "results/publications"
    root.mkdir(parents=True, exist_ok=True)
    for relative, encoded in publications["files"].items():
        if not isinstance(relative, str) or not isinstance(encoded, str):
            raise ValueError("Invalid publication seed entry")
        destination = root / relative
        if not destination.resolve().is_relative_to(root.resolve()) or destination.is_symlink():
            raise ValueError("Unsafe publication seed path")
        content = base64.b64decode(encoded, validate=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(content)


class FrozenVendorReplay:
    """Strict request-keyed replay for every non-model CLI source entrypoint."""
    def __init__(self, gateway: FrozenSourceGateway):
        self.gateway = gateway
        self.calls: list[dict] = []
        self.violations: list[dict] = []

    def lookup(self, domain: str, name: str, args: tuple, kwargs: dict):
        try:
            key = source_request_hash(name, args, kwargs)
            content = json.loads(self.gateway.common(domain))
        except Exception as exc:
            self.violations.append({"domain": domain, "name": name, "reason": type(exc).__name__})
            raise
        if not isinstance(content, dict) or key not in content:
            self.violations.append({"domain": domain, "name": name, "request_hash": key})
            raise RuntimeError(f"Uncaptured frozen source request: {domain}/{name}/{key}")
        self.calls.append({"domain": domain, "name": name, "request_hash": key,
                           "response_sha256": manifest_hash(content[key])})
        value = content[key]
        if isinstance(value, dict) and set(value) == {"__error__", "message"}:
            from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
            if value["__error__"] == "VendorUnavailableError":
                raise VendorUnavailableError(str(value["message"]))
            if value["__error__"] == "NoMarketDataError":
                raise NoMarketDataError(str(args[0]), detail=str(value["message"]))
            raise ValueError("Unrecognized frozen vendor error")
        return value

    @contextmanager
    def installed(self):
        from tradingagents.agents import context, event_comparison, tools, valuation_reference_flow
        from tradingagents.agents.analysts import sentiment_analyst
        from tradingagents.dataflows.financial_evidence import EvidencePackage
        from tradingagents.dataflows.vendors import sec_documents, sec_edgar
        from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
        from tradingagents.dataflows.vendors.yahoo import (
            expectations,
            price_observation,
            reference_history,
        )
        from tradingagents.graph import trading_graph

        def replay(domain, name, restore=lambda value: value):
            return lambda *args, **kwargs: restore(self.lookup(domain, name, args, kwargs))

        def route(name, *args, **kwargs):
            domain = ("prices_indicators" if name in {"get_stock_data", "get_indicators"}
                      else "sec_facts" if name in {"get_fundamentals", "get_balance_sheet",
                                                  "get_cashflow", "get_income_statement"}
                      else "news_social")
            return self.lookup(domain, "route_to_vendor:" + name, args, kwargs)

        def peer(ticker, state):
            cutoff = valuation_reference_flow._scope(state)["observation_cutoff"]
            try:
                data = self.gateway.peer(ticker, cutoff)
            except Exception as exc:
                self.violations.append({"domain": "peer", "name": str(ticker),
                                        "reason": type(exc).__name__})
                raise
            value = json.loads(data)
            if not isinstance(value, dict) or value.get("status") not in {"available", "unavailable"}:
                raise ValueError("Retained peer response shape invalid")
            return value

        def default_selection(state, config):
            scope = valuation_reference_flow._scope(state)
            return self.lookup("default_peers", "default_peer_selection",
                               (scope["ticker"], scope["as_of"], scope["observation_cutoff"]), {})

        with ExitStack() as stack:
            bindings = [
                (tools, "route_to_vendor", route),
                (tools, "build_verified_market_snapshot", replay("prices_indicators", "build_verified_market_snapshot")),
                (sentiment_analyst, "fetch_stocktwits_messages", replay("news_social", "fetch_stocktwits_messages")),
                (sentiment_analyst, "fetch_reddit_posts", replay("news_social", "fetch_reddit_posts")),
                (tools, "build_financial_evidence", replay("sec_facts", "get_financial_evidence", EvidencePackage.model_validate)),
                (tools, "build_filing_evidence", replay("sec_filings", "get_filing_evidence", DisclosurePackage.model_validate)),
                (context, "resolve_instrument_identity", replay("prices_indicators", "resolve_instrument_identity")),
                (trading_graph, "resolve_instrument_identity", replay("prices_indicators", "resolve_instrument_identity")),
                (sec_edgar, "cik_for", replay("sec_facts", "cik_for")),
                (sec_edgar, "get_financial_evidence", replay("sec_facts", "get_financial_evidence", EvidencePackage.model_validate)),
                (sec_documents, "get_filing_evidence", replay("sec_filings", "get_filing_evidence", DisclosurePackage.model_validate)),
                (sec_documents, "get_current_quarter_rpo_evidence",
                 replay("sec_filings", "get_current_quarter_rpo_evidence", DisclosurePackage.model_validate)),
                (sec_documents, "get_prior_quarter_evidence",
                 replay("sec_filings", "get_prior_quarter_evidence", DisclosurePackage.model_validate)),
                (price_observation, "get_price_observation", replay("prices_indicators", "get_price_observation")),
                (event_comparison, "get_price_observation", replay("prices_indicators", "get_price_observation")),
                (reference_history, "get_reference_history", replay("prices_indicators", "get_reference_history")),
                (expectations, "get_vendor_expectations", replay("consensus", "get_vendor_expectations", expectations.VendorExpectations.model_validate)),
                (valuation_reference_flow, "_fetch_peer", peer),
                (valuation_reference_flow, "default_peer_selection", default_selection),
            ]
            for module, attr, replacement in bindings:
                stack.enter_context(patch.object(module, attr, replacement))
            yield


class FrozenSourceCapture:
    """Build request-keyed common source files before model runs."""
    def __init__(self, root: Path):
        self.root = root
        self.entries = {domain: {} for domain in DOMAINS
                        if domain not in {"memory", "prior_publication"}}

    def record(self, domain: str, name: str, args: tuple, kwargs: dict, value):
        if domain not in self.entries:
            raise ValueError("Unknown capturable source domain")
        key = source_request_hash(name, args, kwargs)
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        normalized = json.loads(json.dumps(value, sort_keys=True, default=str))
        if key in self.entries[domain] and self.entries[domain][key] != normalized:
            raise ValueError("Repeated capture request produced different source data")
        self.entries[domain][key] = normalized
        return value

    def call(self, domain: str, name: str, args: tuple, kwargs: dict, producer):
        return self.record(domain, name, args, kwargs, producer(*args, **kwargs))

    def write(self, *, memory: bytes, prior_publication: dict) -> dict:
        if not isinstance(memory, bytes) or not isinstance(prior_publication, dict):
            raise ValueError("Starting memory and publication snapshots are required")
        self.root.mkdir(parents=True, exist_ok=True)
        values = {domain: json.dumps(self.entries[domain], sort_keys=True, separators=(",", ":")).encode()
                  for domain in self.entries}
        values["memory"] = memory
        values["prior_publication"] = json.dumps(prior_publication, sort_keys=True,
                                                  separators=(",", ":")).encode()
        files = {}
        for domain, data in values.items():
            path = self.root / f"{domain}.json"
            with path.open("xb") as handle:
                handle.write(data)
            files[domain] = {"path": path.name, "sha256": hashlib.sha256(data).hexdigest()}
        return files


@contextmanager
def checked_cli_config(spec: CliSpec):
    import cli.run
    original = cli.run._build_run_config
    def checked(*args, **kwargs):
        config = original(*args, **kwargs)
        verify_cli_config(config, spec)
        return config
    with patch.object(cli.run, "_build_run_config", checked):
        yield


@contextmanager
def frozen_market_cutoff(spec: CliSpec):
    if spec.market_observation_cutoff is None:
        yield
        return
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    original = TradingAgentsGraph.create_run_state
    expected = datetime.fromisoformat(spec.market_observation_cutoff).astimezone(UTC).isoformat()
    def fixed(graph, *args, **kwargs):
        state = original(graph, *args, **kwargs)
        if state.get("trade_date") != spec.analysis_date or state.get("company_of_interest") != spec.ticker:
            raise RuntimeError("Graph starting state differs from frozen comparison scope")
        state["market_observation_cutoff"] = expected
        return state
    with patch.object(TradingAgentsGraph, "create_run_state", fixed):
        yield


@contextmanager
def one_document_audit_attempt(spec: CliSpec):
    """Document proof keeps the application retry bound at two model calls."""
    if spec.proof_scope != DOCUMENT_PROOF_SCOPE:
        yield
        return
    import tradingagents.graph.setup as setup_module

    original = setup_module.create_advisory_audit

    def one_attempt(llm, *, deep_model_id, quick_model_id, sdk_retries_disabled=False):
        if not sdk_retries_disabled:
            raise RuntimeError("Document proof requires zero SDK retries")
        return original(
            llm, deep_model_id=deep_model_id, quick_model_id=quick_model_id,
            sdk_retries_disabled=True,
        )

    with patch.object(setup_module, "create_advisory_audit", one_attempt):
        yield


@contextmanager
def counted_editorial_boundary(wire: OpenRouterWireGuard):
    """Mark the post-metrics editorial call without excluding it from wire cost."""
    import tradingagents.graph.trading_graph as graph_module

    original = graph_module.generate_summary
    intervals = []

    def counted(*args, **kwargs):
        before = wire.request_count
        try:
            return original(*args, **kwargs)
        finally:
            intervals.append((before, wire.request_count))

    with patch.object(graph_module, "generate_summary", counted):
        yield intervals


def verify_cli_model_calls(metrics: dict, depth: int, physical_calls: int,
                           editorial_intervals: list[tuple[int, int]]) -> int:
    """Reconcile immutable research metrics with every budgeted wire request."""
    research_calls = metrics.get("model_calls")
    if editorial_intervals:
        valid_boundary = (len(editorial_intervals) == 1
                          and editorial_intervals[0][0] == research_calls
                          and editorial_intervals[0][1] == physical_calls)
    else:
        valid_boundary = research_calls == physical_calls
    if (metrics.get("research_rounds_completed") != depth
            or metrics.get("risk_rounds_completed") != depth
            or type(research_calls) is not int or research_calls < 0
            or type(physical_calls) is not int or physical_calls < research_calls
            or not valid_boundary):
        raise RuntimeError("Actual CLI rounds/model-call count differs from wire evidence")
    return physical_calls - research_calls


def execute_cli(spec: CliSpec, work: Path, wire: OpenRouterWireGuard,
                source_replay: FrozenVendorReplay | None, *, openrouter_key: str,
                sec_user_agent: str, claim: ExecutionClaim,
                approval: Approval | None = None,
                source_credentials: dict[str, str] | None = None):
    """Run the real CLI under exact source, HTTP, config and isolated-path hooks."""
    if wire.max_output_tokens != spec.max_output_tokens or set(wire.rates) != {spec.quick_model, spec.deep_model}:
        raise ValueError("Wire guard differs from actual CLI model/cap scope")
    if wire.context_cap != spec.context_cap:
        raise ValueError("Wire context cap differs from declared CLI scope")
    if claim.kind == "comparison" and (source_replay is None or wire.allow_unfrozen_sources):
        raise ValueError("A7 requires frozen sources and no unfrozen source allowance")
    if claim.kind == "proof" and (source_replay is not None or not wire.allow_unfrozen_sources):
        raise ValueError("Live proof requires real bounded sources, not A7 fixtures")
    if claim.kind == "proof" and (claim.name in {"B3", "Build1"} or claim.name.startswith(DOCUMENT_PROOF_PREFIX)) and not wire.serialize_paid_requests:
        raise ValueError("B3 proof requires serialized paid requests at its unchanged output cap")
    verify_budget_binding(claim, wire.budget, spec, approval)
    start_execution(claim, wire.budget.ledger, spec)
    configure_isolated_env(spec, work, openrouter_key=openrouter_key,
                           sec_user_agent=sec_user_agent, claim=claim, ledger=wire.budget.ledger,
                           source_credentials=source_credentials)
    if source_replay is not None:
        install_starting_snapshot(source_replay.gateway, work)
    DEFAULT_CONFIG = fresh_default_config()
    verify_cli_config(DEFAULT_CONFIG, spec)
    argv = ["cli.main", "--ticker", spec.ticker, "--date", spec.analysis_date,
            "--analysts", "market,social,news,fundamentals", "--save", "--html", "--show", "--checkpoint"]
    old_argv, old_cwd = sys.argv, Path.cwd()
    gate = NetworkGate() if source_replay is not None else None
    wire.network_gate = gate
    original_peer_fetch = source_replay.gateway.fetch_peer if source_replay is not None else None
    if original_peer_fetch is not None:
        def scoped_peer_capture(request):
            with gate.peer_capture():
                return original_peer_fetch(request)
        source_replay.gateway.fetch_peer = scoped_peer_capture
    try:
        sys.argv = argv
        os.chdir(work)
        with ExitStack() as stack:
            stack.enter_context(checked_cli_config(spec))
            stack.enter_context(frozen_market_cutoff(spec))
            stack.enter_context(one_document_audit_attempt(spec))
            editorial_intervals = stack.enter_context(counted_editorial_boundary(wire))
            if source_replay is not None:
                stack.enter_context(source_replay.installed())
                stack.enter_context(installed_network_gate(gate))
            stack.enter_context(installed_http_guard(wire))
            try:
                runpy.run_module("cli.main", run_name="__main__")
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    raise
        if source_replay is not None and (source_replay.violations or gate.violations):
            raise RuntimeError("Uncaptured frozen source access occurred during CLI run")
        state_path = (work / "results" / spec.ticker / "TradingAgentsStrategy_logs" /
                      f"full_states_log_{spec.analysis_date}.json")
        state = json.loads(state_path.read_text())
        if state.get("company_of_interest") != spec.ticker or state.get("trade_date") != spec.analysis_date:
            raise RuntimeError("Actual saved CLI state differs from fixed run scope")
        if spec.market_observation_cutoff is not None and state.get("market_observation_cutoff") != datetime.fromisoformat(
            spec.market_observation_cutoff
        ).astimezone(UTC).isoformat():
            raise RuntimeError("Saved market observation cutoff differs from frozen comparison input")
        if spec.analysis_cutoff_utc is not None and (state.get("analysis_clock") or {}).get("cutoff_utc") != spec.analysis_cutoff_utc:
            raise RuntimeError("Saved analysis cutoff differs from frozen comparison input")
        metrics = state.get("run_metrics") or {}
        # Published run metrics stop before editorial generation. The wire
        # ledger still counts and budgets every physical editorial request.
        editorial_calls = verify_cli_model_calls(metrics, spec.depth, wire.request_count,
                                                 editorial_intervals)
        if not all(state.get(key) for key in ("market_report", "sentiment_report", "news_report",
                                                 "fundamentals_report", "advisory_audit")):
            raise RuntimeError("Saved CLI output is missing an analyst or audit pass")
        if spec.extra_peer_pins is not None:
            peers = ((state.get("valuation_reference") or {}).get("peers") or {})
            requested = peers.get("requested") or []
            if (peers.get("kind") != "user-pinned" or
                    requested != [{"ticker": ticker, "reason": EXTRA_A_PIN_REASON}
                                  for ticker in spec.extra_peer_pins]):
                raise RuntimeError("Actual CLI pinned peer scope differs from approved extra proof")
        price_verification = None
        if claim.kind == "proof" and (claim.name == "Build1" or claim.name.startswith(DOCUMENT_PROOF_PREFIX)):
            entry = next(e for e in wire.budget.ledger.events()
                         if e["type"] == "attempt_claim" and e.get("phase") == claim.name)
            if claim.name.startswith(DOCUMENT_PROOF_PREFIX):
                price_verification = verify_document_access_completed_state(
                    state, spec, entry["approval_record"]
                )
            else:
                verify_run_fixes_completed_state(state, spec, entry["approval_record"])
        return {"state": state, "model_calls": wire.request_count,
                "editorial_model_calls": editorial_calls,
                "price_observation_verification": price_verification,
                "pin_file_sha256": (hashlib.sha256((work / "approved-peer-pins.json").read_bytes()).hexdigest()
                                    if spec.extra_peer_pins is not None else None),
                "reasoning_settings": {key: DEFAULT_CONFIG.get(key) for key in
                                       ("openai_reasoning_effort", "anthropic_effort")},
                "source_calls": source_replay.calls if source_replay is not None else [],
                "request_hashes": source_replay.gateway.request_hashes if source_replay is not None else {}}
    finally:
        if source_replay is not None:
            source_replay.gateway.fetch_peer = original_peer_fetch
        sys.argv = old_argv
        os.chdir(old_cwd)


def build_pilot_receipt(manifest: dict, spec: CliSpec, slot_name: str,
                        cli_result: dict, ledger: PilotLedger) -> dict:
    """Derive the A7 callback receipt from actual saved CLI and wire records."""
    slot = next((slot for slot in SLOTS if slot.name == slot_name), None)
    if slot is None or (spec.quick_model, spec.deep_model, spec.depth) != (
        slot.quick_model, slot.deep_model, slot.depth
    ):
        raise ValueError("CLI spec differs from claimed A7 slot")
    if manifest.get("cutoff_utc") != spec.market_observation_cutoff:
        raise ValueError("CLI market cutoff differs from frozen A7 manifest")
    if manifest.get("context_cap") != spec.context_cap:
        raise ValueError("CLI context cap differs from frozen A7 manifest")
    state = cli_result["state"]
    events = ledger.events()
    tickets = {e["ticket"] for e in events if e["type"] == "reserve" and e.get("scope") == slot_name}
    cost = (sum((Decimal(e["usd"]) for e in events if e["type"] in {"reserve", "settle"}
                 and e.get("ticket") in tickets), Decimal(0))
            - sum((Decimal(e["usd"]) for e in events if e["type"] == "release"
                   and e.get("ticket") in tickets), Decimal(0)))
    if len(tickets) != cli_result["model_calls"]:
        raise ValueError("Saved model calls differ from paid request records")
    source_calls = cli_result["source_calls"]
    if not isinstance(source_calls, list) or not source_calls:
        raise ValueError("Frozen source calls are not recorded")
    return {"state": state, "common_hash": manifest_hash(manifest),
            "memory_hash": manifest["files"]["memory"]["sha256"],
            "prior_publication_hash": manifest["files"]["prior_publication"]["sha256"],
            "request_hashes": cli_result["request_hashes"],
            "source_call_hashes": source_calls,
            "reasoning_settings": cli_result.get("reasoning_settings"),
            "response_routes": [e for e in events if e["type"] == "response_meta"
                                and e.get("ticket") in tickets],
            "scope": {"ticker": spec.ticker, "analysis_date": spec.analysis_date,
                      "depth": spec.depth, "analysts": manifest["analysts"],
                      "tool_limit": spec.max_tool_rounds, "context_cap": spec.context_cap,
                      "quick_model": spec.quick_model, "deep_model": spec.deep_model,
                      "llm_max_retries": 0},
            "model_calls": cli_result["model_calls"], "cost_usd": str(cost), "completed": True}


def _document_access_prior_exposure(record):
    """Link historical reservations, including unknown holds, without reusing authority."""
    historical = record.get("old_ledgers")
    if not isinstance(historical, dict) or not historical:
        raise ValueError("Historical proof ledgers are required")
    committed = Decimal(0)
    unknown = Decimal(0)
    for name, digest in historical.items():
        path = Path(name)
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("Historical proof ledger changed")
        ledger = PilotLedger(path)
        events = ledger.events()
        settled = {event["ticket"] for event in events if event.get("type") == "settle"}
        committed += ledger.committed_usd()
        unknown += sum((Decimal(event["usd"]) for event in events
                        if event.get("type") == "reserve" and event["ticket"] not in settled), Decimal(0))
    if (committed != Decimal(record.get("prior_committed_exposure_usd", "-1"))
            or unknown != Decimal(record.get("prior_unknown_reserved_usd", "-1"))):
        raise ValueError("Historical committed or unknown exposure differs")
    return committed, unknown


def _document_final_slot_amendment(record, ledger=None, *, claimed=False):
    """Verify a single CAT rebind without resetting the original allowance."""
    amendment = record.get("final_slot_amendment")
    if not isinstance(amendment, dict) or set(amendment) != {
        "schema_version", "ticker", "original_approval_path",
        "original_approval_sha256", "original_approval_digest",
        "ledger_prefix_bytes", "ledger_prefix_sha256",
    } or amendment["schema_version"] != 1 or amendment["ticker"] != "CAT":
        raise ValueError("Final-slot amendment schema differs")
    path = Path(amendment["original_approval_path"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Archived original approval missing or unsafe")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != amendment["original_approval_sha256"]:
        raise ValueError("Archived original approval bytes changed")
    original = json.loads(raw)
    if not isinstance(original, dict) or "final_slot_amendment" in original:
        raise ValueError("Archived approval is not an original document authority")
    _validate_document_access_approval(original)
    old_digest = manifest_hash(original)
    if old_digest != amendment["original_approval_digest"]:
        raise ValueError("Archived original approval digest differs")
    mutable = {
        "approval_id", "approved_at_recorded", "user_instruction",
        "candidate_head", "candidate_sha256", "runner_sha256",
        "provider_metadata_sha256",
    }
    if (any(record[key] != original[key] for key in original if key not in mutable)
            or record["candidate_head"] == original["candidate_head"]
            or record["ceiling_usd"] != "72"
            or record["per_attempt_ceiling_usd"] != "24"
            or type(amendment["ledger_prefix_bytes"]) is not int
            or amendment["ledger_prefix_bytes"] <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", amendment["ledger_prefix_sha256"])):
        raise ValueError("Final-slot amendment changed budget or original scope")
    if ledger is None:
        return old_digest
    if ledger.path.is_symlink() or not ledger.path.is_file():
        raise ValueError("Original document ledger missing")
    data = ledger.path.read_bytes()
    length = amendment["ledger_prefix_bytes"]
    prefix = data[:length]
    if (len(prefix) != length or not prefix.endswith(b"\n")
            or hashlib.sha256(prefix).hexdigest() != amendment["ledger_prefix_sha256"]):
        raise ValueError("Original document ledger prefix changed")
    prefix_events = [json.loads(line) for line in prefix.splitlines() if line.strip()]
    allowance = [event for event in prefix_events if event.get("type") == "allowance"]
    claims = [event for event in prefix_events if event.get("type") == "attempt_claim"]
    if (len(allowance) != 1
            or allowance[0].get("approval_sha256") != old_digest
            or allowance[0].get("ceiling_usd") != "72"
            or allowance[0].get("attempts") != 3
            or [(event.get("ticker"), event.get("approval_sha256")) for event in claims]
            != [("DOCN", old_digest), ("MSFT", old_digest)]
            or any(event.get("approval_record") != original for event in claims)
            or any(event.get("type") == "final_slot_amendment" for event in prefix_events)
            or any(not any(e.get("type") == "execution_start"
                           and e.get("name") == DOCUMENT_PROOF_PREFIX + ticker
                           for e in prefix_events)
                   for ticker in ("DOCN", "MSFT"))
            or any(not any(e.get("type") in {"attempt_failed_start", "attempt_proof_incomplete"}
                           and e.get("ticker") == ticker for e in prefix_events)
                   for ticker in ("DOCN", "MSFT"))):
        raise ValueError("Final-slot amendment original two attempts differ")
    tail = [json.loads(line) for line in data[length:].splitlines() if line.strip()]
    if not claimed:
        if tail:
            raise ValueError("Final-slot amendment ledger advanced before claim")
    elif (len(tail) < 3 or tail[0] != {
            "type": "final_slot_amendment", "ticker": "CAT",
            "original_approval_sha256": amendment["original_approval_sha256"],
            "original_approval_digest": old_digest,
            "ledger_prefix_bytes": length,
            "ledger_prefix_sha256": amendment["ledger_prefix_sha256"],
            "new_approval_sha256": manifest_hash(record),
        } or tail[1].get("type") != "provider_receipt"
          or tail[1].get("ticker") != "CAT"
          or tail[1].get("approval_sha256") != manifest_hash(record)
          or tail[2].get("type") != "attempt_claim"
          or tail[2].get("ticker") != "CAT"
          or tail[2].get("approval_sha256") != manifest_hash(record)
          or sum(e.get("type") == "final_slot_amendment" for e in tail) != 1
          or sum(e.get("type") == "attempt_claim" for e in tail) != 1):
        raise ValueError("Final-slot amendment ledger chain differs")
    return old_digest


def _validate_document_access_approval(record):
    """Exact three-attempt document proof authority; no historical allowance is inherited."""
    required = {
        "approval_id", "approved_at_recorded", "user_instruction", "phase", "attempts",
        "tickers", "analysis_date", "quick_model", "deep_model", "depth",
        "max_output_tokens", "max_tool_rounds", "analysts", "llm_max_retries",
        "audit_max_attempts", "candidate_head", "worktree_root", "repository_origin", "ledger_path",
        "machine", "ceiling_usd", "per_attempt_ceiling_usd", "max_calls_per_attempt",
        "old_ledgers", "prior_committed_exposure_usd", "prior_unknown_reserved_usd",
        "runner_sha256", "provider_metadata_sha256", "candidate_sha256", "session",
        "receipt_refresh_policy", "receipt_root", "approved_route_rate_caps", "resolved_model_ids",
    }
    amended = isinstance(record, dict) and "final_slot_amendment" in record
    if not isinstance(record, dict) or set(record) != (required | {"final_slot_amendment"} if amended else required):
        raise ValueError("Document-access approval record is incomplete")
    now = datetime.now(UTC)
    _b3_aware_time(record["approved_at_recorded"], now)
    ceiling = Decimal(record["ceiling_usd"])
    attempt = Decimal(record["per_attempt_ceiling_usd"])
    if (not isinstance(record["approval_id"], str) or not record["approval_id"].strip()
            or not isinstance(record["user_instruction"], str) or not record["user_instruction"].strip()
            or record["phase"] != "DocumentAccess" or record["attempts"] != 3
            or record["tickers"] != list(DOCUMENT_PROOF_TICKERS)
            or record["quick_model"] != B_DEEP or record["deep_model"] != A
            or record["depth"] != 3 or record["max_output_tokens"] != 16384
            or record["max_tool_rounds"] != 4
            or record["analysts"] != ["market", "social", "news", "fundamentals"]
            or record["llm_max_retries"] != 0 or record["audit_max_attempts"] != 2
            or record["receipt_refresh_policy"] != "per_attempt_local_receipt_v1"
            or type(record["max_calls_per_attempt"]) is not int
            or not 1 <= record["max_calls_per_attempt"] <= 128
            or not ceiling.is_finite() or not attempt.is_finite()
            or ceiling <= 0 or attempt <= 0 or attempt * 3 > ceiling
            or record["machine"] != {"cpu": "Apple M1 Pro", "ram_bytes": 17179869184}
            or not re.fullmatch(r"[0-9a-f]{40}", record["candidate_head"])
            or not re.fullmatch(r"[0-9a-f]{64}", record["candidate_sha256"])
            or not re.fullmatch(r"[0-9a-f]{64}", record["runner_sha256"])
            or not re.fullmatch(r"[0-9a-f]{64}", record["provider_metadata_sha256"])):
        raise ValueError("Document-access proof scope or budget differs")
    worktree = Path(record["worktree_root"])
    ledger_path = Path(record["ledger_path"])
    receipt_root = Path(record["receipt_root"])
    if not worktree.is_absolute() or worktree.is_symlink() or not worktree.is_dir():
        raise ValueError("Document-access worktree is unsafe")
    if not ledger_path.is_absolute() or ledger_path.is_symlink():
        raise ValueError("Document-access ledger path is unsafe")
    if not receipt_root.is_absolute() or receipt_root.is_symlink():
        raise ValueError("Document-access receipt root is unsafe")
    if not isinstance(record["repository_origin"], str) or not record["repository_origin"]:
        raise ValueError("Document-access repository origin missing")
    date.fromisoformat(record["analysis_date"])
    session = record["session"]
    if not isinstance(session, dict) or session.get("session_date") != record["analysis_date"]:
        raise ValueError("Document-access session differs")
    close = datetime.fromisoformat(session["regular_close_utc"])
    from zoneinfo import ZoneInfo

    approved_at = datetime.fromisoformat(record["approved_at_recorded"]).astimezone(UTC)
    if (close.tzinfo is None or close > now or close > approved_at
            or close.astimezone(ZoneInfo("America/New_York")).date()
            != date.fromisoformat(record["analysis_date"])):
        raise ValueError("Document-access proof requires observed completed session")
    caps = record["approved_route_rate_caps"]
    aliases = record["resolved_model_ids"]
    if (not isinstance(caps, dict) or set(caps) != {A, B_DEEP}
            or not isinstance(aliases, dict) or set(aliases) != {A, B_DEEP}):
        raise ValueError("Approved document route rates or model IDs missing")
    for model in (A, B_DEEP):
        if (set(caps[model]) != {"input_per_token", "output_per_token",
                                "cache_read_per_token", "cache_write_per_token"}
                or any(not Decimal(str(value)).is_finite() or Decimal(str(value)) < 0
                       for value in caps[model].values())
                or model not in aliases[model] or not all(
                    isinstance(value, str) for value in aliases[model]
                )):
            raise ValueError("Approved document endpoint rates or aliases malformed")
    _document_access_prior_exposure(record)
    if amended:
        _document_final_slot_amendment(record)
    return record


def _document_access_attempt_receipt(record: dict, ticker: str, ledger: PilotLedger) -> dict:
    """Verify one newly observed read-only account/endpoint receipt before a claim."""
    path = Path(record["receipt_root"]) / f"{ticker}.json"
    if ticker not in DOCUMENT_PROOF_TICKERS or path.is_symlink() or not path.is_file():
        raise ValueError("Per-attempt provider receipt missing or unsafe")
    raw = path.read_bytes()
    metadata = json.loads(raw)
    observed = datetime.fromisoformat(metadata["observed_at"])
    now = datetime.now(UTC)
    if observed.tzinfo is None or not now - timedelta(minutes=10) <= observed <= now:
        raise ValueError("Per-attempt provider receipt is not fresh")
    prior = [event for event in ledger.events() if event.get("type") == "provider_receipt"]
    if prior and observed <= max(datetime.fromisoformat(event["observed_at"]) for event in prior):
        raise ValueError("Per-attempt provider receipt was not refreshed")
    rates = conservative_route_rates(metadata, {A, B_DEEP})
    aliases = resolved_model_ids(metadata, {A, B_DEEP})
    for model in (A, B_DEEP):
        if (sorted(aliases[model]) != record["resolved_model_ids"][model]
                or any(Decimal(rates[model][key]) > Decimal(record["approved_route_rate_caps"][model][key])
                       for key in rates[model])):
            raise ValueError("Served model or endpoint price exceeds approved envelope")
    account = metadata["results"].get("key")
    if not isinstance(account, dict) or account.get("limit_remaining") is None:
        raise ValueError("Fresh account headroom unavailable")
    remaining = Decimal(str(account["limit_remaining"]))
    events = ledger.events()
    settled = {event["ticket"] for event in events if event.get("type") == "settle"}
    new_unknown = sum((Decimal(event["usd"]) for event in events if event.get("type") == "reserve"
                       and event["ticket"] not in settled), Decimal(0))
    prior_unknown = Decimal(record["prior_unknown_reserved_usd"])
    required = Decimal(record["per_attempt_ceiling_usd"]) + new_unknown + prior_unknown
    if not remaining.is_finite() or remaining < required:
        raise ValueError("Fresh account headroom cannot cover attempt and unknown holds")
    return {
        "type": "provider_receipt", "ticker": ticker, "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "observed_at": observed.isoformat(), "rates": rates,
        "resolved_model_ids": {model: sorted(values) for model, values in aliases.items()},
        "limit_remaining_usd": str(remaining), "required_headroom_usd": str(required),
        "approval_sha256": manifest_hash(record),
    }


def claim_document_access_proof(ledger: PilotLedger, approval_record: dict, ticker: str) -> str:
    """Claim one ticker once in the shared new ledger, preserving failed attempts."""
    record = _validate_document_access_approval(approval_record)
    if (ticker not in DOCUMENT_PROOF_TICKERS
            or str(ledger.path.resolve()) in record["old_ledgers"]
            or ledger.path.is_symlink()
            or ledger.path.resolve() != Path(record["ledger_path"]).resolve()):
        raise ValueError("Document-access ticker or fresh ledger differs")
    digest = manifest_hash(record)
    with ledger.budget_lock():
        events = ledger.events()
        allowance = [event for event in events if event["type"] == "allowance"]
        if record.get("final_slot_amendment"):
            if ticker != "CAT":
                raise RuntimeError("Amended document authority permits CAT only")
            old_digest = _document_final_slot_amendment(record, ledger)
            if len(allowance) != 1 or allowance[0].get("approval_sha256") != old_digest:
                raise RuntimeError("Original document allowance differs")
        elif events and (len(allowance) != 1 or allowance[0].get("approval_sha256") != digest):
            raise RuntimeError("Document-access allowance differs")
        claims = [event for event in ledger.events() if event["type"] == "attempt_claim"]
        if (len(claims) >= 3 or any(event.get("ticker") == ticker for event in claims)
                or any(event.get("phase") not in
                       {DOCUMENT_PROOF_PREFIX + item for item in DOCUMENT_PROOF_TICKERS}
                       for event in claims)):
            raise RuntimeError("Document-access attempt already claimed or cap reached")
        receipt = _document_access_attempt_receipt(record, ticker, ledger)
        if not events:
            ledger.append({"type": "allowance", "approval_sha256": digest,
                           "ceiling_usd": record["ceiling_usd"], "attempts": 3,
                           "old_ledgers": record["old_ledgers"],
                           "prior_committed_exposure_usd": record["prior_committed_exposure_usd"],
                           "prior_unknown_reserved_usd": record["prior_unknown_reserved_usd"]})
        if record.get("final_slot_amendment"):
            amendment = record["final_slot_amendment"]
            ledger.append({
                "type": "final_slot_amendment", "ticker": "CAT",
                "original_approval_sha256": amendment["original_approval_sha256"],
                "original_approval_digest": old_digest,
                "ledger_prefix_bytes": amendment["ledger_prefix_bytes"],
                "ledger_prefix_sha256": amendment["ledger_prefix_sha256"],
                "new_approval_sha256": digest,
            })
        ledger.append(receipt)
        ledger.append({"type": "attempt_claim", "phase": DOCUMENT_PROOF_PREFIX + ticker,
                       "ticker": ticker, "ceiling_usd": record["ceiling_usd"],
                       "phase_ceiling_usd": record["per_attempt_ceiling_usd"],
                       "approval_sha256": digest, "approval_record": record})
    return digest
