import base64
import hashlib
import importlib.util
import json
import socket
import sys
from contextlib import nullcontext, suppress
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "docs/reviews/valuation-reference-proof-tools"
for name in ("pilot", "live_adapter"):
    spec = importlib.util.spec_from_file_location("a7_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    globals()[name] = module
    if name == "pilot":
        sys.modules["pilot"] = module
pilot = sys.modules["a7_pilot"]
live_adapter = sys.modules["a7_live_adapter"]


class Request:
    def __init__(self, payload, host="openrouter.ai", path="/api/v1/chat/completions", method="POST"):
        self.url = type("URL", (), {"host": host, "path": path, "scheme": "https"})()
        self.method = method
        self.headers = {"authorization": "Bearer fake"}
        self.content = json.dumps(payload).encode()


class Response:
    def __init__(self, data, status=200):
        self.status_code = status
        self.is_closed = True
        self.data = data
    def json(self):
        return self.data


@pytest.mark.unit
def test_wire_guard_reserves_before_send_and_settles_valid_usage(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.A}, max_calls=2)
    wire = live_adapter.OpenRouterWireGuard(budget, {pilot.A: {"input_per_token": "0.000001",
        "output_per_token": "0.000005", "cache_read_per_token": "0", "cache_write_per_token": "0"}}, max_output_tokens=100, kind="run", allowed_resolved_models={pilot.A: {pilot.A}})
    request = Request({"model": pilot.A, "max_tokens": 100, "messages": [{"role": "user", "content": "hi"}]})
    ticket = wire.before(request)
    assert ledger.committed_usd() > 0
    wire.after(ticket, Response({"model": pilot.A, "usage": {"prompt_tokens": 30, "completion_tokens": 10,
        "cost": 0.00008}}))
    assert ledger.committed_usd() == pilot.Decimal("0.00008")


@pytest.mark.unit
def test_wire_guard_rejects_unapproved_model_addon_and_missing_cap(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.A}, max_calls=2)
    wire = live_adapter.OpenRouterWireGuard(budget, {pilot.A: {"input_per_token": "0.000001",
        "output_per_token": "0.000005", "cache_read_per_token": "0", "cache_write_per_token": "0"}}, max_output_tokens=100, kind="run", allowed_resolved_models={pilot.A: {pilot.A}})
    for payload in ({"model": "openai/wrong", "max_tokens": 100},
                    {"model": pilot.A, "max_tokens": 100, "plugins": [{"id": "web"}]},
                    {"model": pilot.A, "max_tokens": 101}):
        with pytest.raises((RuntimeError, ValueError)):
            wire.before(Request(payload))
    assert ledger.committed_usd() == 0


@pytest.mark.unit
def test_unknown_response_cost_keeps_full_reservation(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.B_QUICK}, max_calls=2)
    wire = live_adapter.OpenRouterWireGuard(budget, {pilot.B_QUICK: {"input_per_token": "0.000002",
        "output_per_token": "0.000010", "cache_read_per_token": "0", "cache_write_per_token": "0"}}, max_output_tokens=100, kind="run", allowed_resolved_models={pilot.B_QUICK: {pilot.B_QUICK}})
    ticket = wire.before(Request({"model": pilot.B_QUICK, "max_tokens": 100, "messages": []}))
    reserved = ledger.committed_usd()
    wire.after(ticket, Response({"model": pilot.B_QUICK, "usage": {"prompt_tokens": 10}}, status=200))
    assert ledger.committed_usd() == reserved
    assert any(e["type"] == "unknown" for e in ledger.events())


@pytest.mark.unit
def test_proof_attempt_claim_is_separate_and_consumed_on_failure(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "part_a_proof.jsonl")
    proof = live_adapter.ProofAttemptLedger(ledger, ceiling_usd="10", max_attempts=2)
    proof.claim("A")
    with pytest.raises(RuntimeError, match="already claimed"):
        proof.claim("A")
    with pytest.raises(RuntimeError, match="go-ahead"):
        proof.claim("B")
    proof.claim("B", part_b_go_ahead=True)
    assert [e["phase"] for e in ledger.events() if e["type"] == "attempt_claim"] == ["A", "B"]


@pytest.mark.unit
def test_frozen_vendor_replay_requires_exact_request_and_seeds_clean_start(tmp_path):
    files = {}
    request = {"name": "route_to_vendor:get_stock_data", "args": ("DOCN", "2026-10-01", "2026-11-05"), "kwargs": {}}
    key = pilot.manifest_hash(request)
    for domain in pilot.DOMAINS:
        if domain == "memory":
            content = b"same memory\n"
        elif domain == "prior_publication":
            content = json.dumps({"files": {"records/example.json": base64.b64encode(b"retained\n").decode()}}).encode()
        elif domain == "prices_indicators":
            content = json.dumps({key: "fixed OHLCV"}).encode()
        else:
            content = b"{}"
        path = tmp_path / f"{domain}.json"
        path.write_bytes(content)
        files[domain] = {"path": path.name, "sha256": hashlib.sha256(content).hexdigest()}
    manifest = {"ticker": "DOCN", "analysis_date": "2026-11-05",
                "cutoff_utc": "2026-11-06T06:59:59+00:00", "depth": 2,
                "source_version": "source", "prompt_version": "prompt", "tool_limit": 4,
                "context_cap": 65536, "analysts": ["market", "social", "news", "fundamentals"],
                "reviewer": {"model_id": "reviewer/exact", "settings": {"temperature": 0}},
                "files": files}
    gateway = pilot.FrozenSourceGateway(manifest, tmp_path, tmp_path / "peers")
    replay = live_adapter.FrozenVendorReplay(gateway)
    assert replay.lookup("prices_indicators", "route_to_vendor:get_stock_data", request["args"], {}) == "fixed OHLCV"
    with pytest.raises(RuntimeError, match="Uncaptured"):
        replay.lookup("prices_indicators", "route_to_vendor:get_stock_data", ("AAPL",), {})
    from tradingagents.agents import context, tools
    from tradingagents.dataflows.vendors import sec_edgar
    with replay.installed():
        assert tools.route_to_vendor("get_stock_data", *request["args"]) == "fixed OHLCV"
        with pytest.raises(RuntimeError, match="Uncaptured"):
            sec_edgar.cik_for("DOCN")
        with pytest.raises(RuntimeError, match="Uncaptured"):
            context.resolve_instrument_identity("DOCN")
    work = tmp_path / "work"
    live_adapter.install_starting_snapshot(gateway, work)
    assert (work / "memory/trading_memory.md").read_bytes() == b"same memory\n"
    assert (work / "results/publications/records/example.json").read_bytes() == b"retained\n"
    with pytest.raises(FileExistsError):
        live_adapter.install_starting_snapshot(gateway, work)


@pytest.mark.unit
def test_cli_config_verifies_exact_models_depth_and_retries():
    spec = live_adapter.CliSpec("DOCN", "2026-11-05", pilot.B_QUICK, pilot.B_DEEP, 2, 8192, analysis_cutoff_utc="2026-11-06T06:59:59+00:00", market_observation_cutoff="2026-11-05T22:00:00+00:00", context_cap=65536)
    config = {"llm_provider": "openrouter", "quick_think_llm": pilot.B_QUICK,
              "deep_think_llm": pilot.B_DEEP, "backend_url": "https://openrouter.ai/api/v1",
              "max_debate_rounds": 2, "max_risk_discuss_rounds": 2, "max_tool_rounds": 4,
              "max_tokens": 8192, "llm_max_retries": 0, "analysis_timezone": "America/Denver"}
    config["analysis_cutoff_utc"] = "2026-11-06T06:59:59+00:00"
    live_adapter.verify_cli_config(config, spec)
    with pytest.raises(RuntimeError, match="llm_max_retries"):
        live_adapter.verify_cli_config({**config, "llm_max_retries": 2}, spec)


@pytest.mark.unit
def test_capture_gateway_writes_content_addressed_sources_and_rejects_drift(tmp_path):
    capture = live_adapter.FrozenSourceCapture(tmp_path / "frozen")
    args = ("DOCN", "2026-11-05")
    capture.record("sec_facts", "get_financial_evidence", args, {}, {"cik": "1400000"})
    with pytest.raises(ValueError, match="different source data"):
        capture.record("sec_facts", "get_financial_evidence", args, {}, {"cik": "changed"})
    files = capture.write(memory=b"seed", prior_publication={"files": {}})
    assert set(files) == set(pilot.DOMAINS)
    raw = (tmp_path / "frozen/sec_facts.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == files["sec_facts"]["sha256"]
    with pytest.raises(FileExistsError):
        capture.write(memory=b"seed", prior_publication={"files": {}})


@pytest.mark.unit
def test_actual_cli_entry_requires_prior_phase_claim(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "proof.jsonl")
    spec = live_adapter.CliSpec("DOCN", "2026-11-05", pilot.A, pilot.A, 1, 8192)
    claim = live_adapter.ExecutionClaim("proof", "A")
    with pytest.raises(RuntimeError, match="claim"):
        live_adapter.verify_execution_claim(claim, ledger, spec)
    live_adapter.ProofAttemptLedger(ledger, ceiling_usd="10", max_attempts=2).claim("A")
    live_adapter.verify_execution_claim(claim, ledger, spec)
    live_adapter.start_execution(claim, ledger, spec)
    with pytest.raises(RuntimeError, match="already started"):
        live_adapter.start_execution(claim, ledger, spec)
    bad = pilot.BudgetGuard(ledger, pilot.Decimal("11"), allowed_models={pilot.A},
                            max_calls=40, scope="proof:A", allowed_kinds={"run"})
    with pytest.raises(RuntimeError, match="budget"):
        live_adapter.verify_budget_binding(claim, bad, spec, None)


@pytest.mark.unit
def test_pilot_receipt_uses_actual_wire_and_source_evidence(tmp_path):
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    slot = pilot.SLOTS[0]
    ledger.append({"type": "slot_claim", "slot": slot.name})
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.A},
                               max_calls=4, scope=slot.name)
    ticket = budget.reserve(pilot.A, "0.5", kind="run")
    budget.settle(ticket, "0.2")
    manifest = {"cutoff_utc": "2026-11-05T22:00:00+00:00",
                "files": {"memory": {"sha256": "a" * 64},
                           "prior_publication": {"sha256": "b" * 64}},
                "analysts": ["market", "social", "news", "fundamentals"], "context_cap": 65536}
    spec = live_adapter.CliSpec("DOCN", "2026-11-05", pilot.A, pilot.A, 2, 8192, analysis_cutoff_utc="2026-11-06T06:59:59+00:00", market_observation_cutoff="2026-11-05T22:00:00+00:00", context_cap=65536)
    result = {"state": {"trade_date": "2026-11-05", "company_of_interest": "DOCN"},
              "model_calls": 1, "request_hashes": {"peer:abc": "c" * 64},
              "source_calls": [{"domain": "sec_facts", "response_sha256": "d" * 64}]}
    receipt = live_adapter.build_pilot_receipt(manifest, spec, slot.name, result, ledger)
    assert receipt["cost_usd"] == "0.2"
    assert receipt["model_calls"] == 1 and receipt["scope"]["depth"] == 2


@pytest.mark.unit
def test_cli_adapter_reads_real_saved_state_after_successful_click_exit(tmp_path, monkeypatch):
    ledger = pilot.PilotLedger(tmp_path / "proof.jsonl")
    live_adapter.ProofAttemptLedger(ledger, ceiling_usd="10", max_attempts=2).claim("A")
    spec = live_adapter.CliSpec("DOCN", "2026-11-05", pilot.A, pilot.A, 1, 8192)
    proof_budget = pilot.BudgetGuard(ledger, pilot.Decimal("10"), allowed_models={pilot.A},
                                     max_calls=40, scope="proof:A", allowed_kinds={"run"},
                                     scope_ceiling=pilot.Decimal("10"))
    wire = type("Wire", (), {"max_output_tokens": 8192, "context_cap": None,
                             "rates": {pilot.A: (1, 1)},
                             "allow_unfrozen_sources": True,
                             "request_count": 1, "budget": proof_budget})()
    monkeypatch.setattr(live_adapter, "configure_isolated_env", lambda *a, **kw: None)
    monkeypatch.setattr(live_adapter, "install_starting_snapshot", lambda *a: None)
    monkeypatch.setattr(live_adapter, "verify_cli_config", lambda *a: None)
    monkeypatch.setattr(live_adapter, "checked_cli_config", lambda *a: nullcontext())
    monkeypatch.setattr(live_adapter, "installed_http_guard", lambda *a: nullcontext())
    def cli_main(*a, **kw):
        path = tmp_path / "results/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-05.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"company_of_interest": "DOCN", "trade_date": "2026-11-05",
            "run_metrics": {"research_rounds_completed": 1, "risk_rounds_completed": 1, "model_calls": 1},
            "market_report": "m", "sentiment_report": "s", "news_report": "n",
            "fundamentals_report": "f", "advisory_audit": {"status": "completed with zero findings"}}))
        raise SystemExit(0)
    monkeypatch.setattr(live_adapter.runpy, "run_module", cli_main)
    result = live_adapter.execute_cli(spec, tmp_path, wire, None, openrouter_key="fake",
        sec_user_agent="offline-test", claim=live_adapter.ExecutionClaim("proof", "A"))
    assert result["state"]["company_of_interest"] == "DOCN"
    assert result["model_calls"] == 1


@pytest.mark.unit
def test_caught_uncaptured_rpo_source_invalidates_complete_cli_state(tmp_path, monkeypatch):
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    approval = pilot.Approval("offline-manifest", "2", "reviewer/offline", 6)
    slot = pilot.SLOTS[0]
    ledger.append({"type": "slot_claim", "slot": slot.name,
                   "manifest_hash": approval.approved_manifest_sha256})
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.A},
                               max_calls=64, scope=slot.name, allowed_kinds={"run"})
    spec = live_adapter.CliSpec("DOCN", "2026-11-05", pilot.A, pilot.A, 2, 8192,
        analysis_cutoff_utc="2026-11-06T06:59:59+00:00",
        market_observation_cutoff="2026-11-05T22:00:00+00:00", context_cap=65536)
    wire = type("Wire", (), {"max_output_tokens": 8192, "context_cap": 65536,
                             "rates": {pilot.A: (1, 1)}, "allow_unfrozen_sources": False,
                             "request_count": 1, "budget": budget})()
    class Gateway:
        fetch_peer = None
        request_hashes = {}
        def common(self, domain):
            return b"" if domain == "memory" else b'{"files":{}}' if domain == "prior_publication" else b"{}"
    replay = live_adapter.FrozenVendorReplay(Gateway())
    (tmp_path / "run").mkdir()
    monkeypatch.setattr(live_adapter, "configure_isolated_env", lambda *a, **kw: None)
    monkeypatch.setattr(live_adapter, "install_starting_snapshot", lambda *a: None)
    monkeypatch.setattr(live_adapter, "verify_cli_config", lambda *a: None)
    monkeypatch.setattr(live_adapter, "checked_cli_config", lambda *a: nullcontext())
    monkeypatch.setattr(live_adapter, "installed_http_guard", lambda *a: nullcontext())
    def cli_main(*a, **kw):
        from tradingagents.dataflows.vendors import sec_documents
        with suppress(RuntimeError):
            sec_documents.get_current_quarter_rpo_evidence(None)
        path = tmp_path / "run/results/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-05.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"company_of_interest": "DOCN", "trade_date": "2026-11-05",
            "market_observation_cutoff": spec.market_observation_cutoff,
            "analysis_clock": {"cutoff_utc": spec.analysis_cutoff_utc},
            "run_metrics": {"research_rounds_completed": 2, "risk_rounds_completed": 2, "model_calls": 1},
            "market_report": "m", "sentiment_report": "s", "news_report": "n",
            "fundamentals_report": "f", "advisory_audit": {"status": "completed with zero findings"}}))
        raise SystemExit(0)
    monkeypatch.setattr(live_adapter.runpy, "run_module", cli_main)
    with pytest.raises(RuntimeError, match="Uncaptured frozen source"):
        live_adapter.execute_cli(spec, tmp_path / "run", wire, replay, openrouter_key="fake",
            sec_user_agent="offline-test", claim=live_adapter.ExecutionClaim("comparison", slot.name),
            approval=approval)
    assert len(replay.violations) == 1


@pytest.mark.unit
def test_frozen_network_gate_denies_unrouted_socket_and_curl():
    gate = live_adapter.NetworkGate()
    with (live_adapter.installed_network_gate(gate), socket.socket() as sock,
          pytest.raises(RuntimeError, match="Uncaptured network")):
        sock.connect(("127.0.0.1", 9))
    assert gate.violations == ["unrouted_socket"]


@pytest.mark.unit
def test_conservative_route_rates_cover_expensive_endpoint_long_context_and_cache():
    metadata = {"results": {pilot.B_QUICK: {"endpoints": [
        {"pricing": {"prompt": "0.000001", "completion": "0.000005",
                     "input_cache_write": "0.000002", "overrides": [
                         {"prompt": "0.000002", "completion": "0.000007"}]}},
        {"pricing": {"prompt": "0.000004", "completion": "0.000020",
                     "input_cache_write_1h": "0.000010", "overrides": [
                         {"prompt": "0.000008", "completion": "0.000030"}]}}
    ]}}}
    rates = live_adapter.conservative_route_rates(metadata, {pilot.B_QUICK})[pilot.B_QUICK]
    assert rates["input_per_token"] == "0.000008"
    assert rates["output_per_token"] == "0.000030"
    assert rates["cache_write_per_token"] == "0.000010"
    metadata["results"][pilot.B_QUICK]["endpoints"][0]["name"] = "OpenAI | openai/gpt-6.1-sol-20260929"
    assert "openai/gpt-6.1-sol-20260929" in live_adapter.resolved_model_ids(
        metadata, {pilot.B_QUICK})[pilot.B_QUICK]


@pytest.mark.unit
@pytest.mark.parametrize("mapped", [False, True], ids=["unmapped", "mapped-filer"])
def test_real_cli_graph_offline_capture_and_wire_drill(tmp_path, monkeypatch, mapped):
    """Run cli.main and the real graph with scripted model, source and HTTP boundaries."""
    import httpx

    from tests import test_graph_end_to_end as graph_fixture
    from tests.test_graph_end_to_end import ScriptedModel, _Client
    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.graph import trading_graph

    date = "2026-10-19" if mapped else "2026-01-09"
    market_cutoff = "2026-10-19T22:00:00+00:00" if mapped else "2026-01-09T22:00:00+00:00"
    if mapped:
        from tests.test_evidence_gate import complete_evidence
        from tests.test_valuation_reference import fixture as reference_fixture
        from tests.test_valuation_reference_flow import flow_fixture
        from tradingagents.dataflows.vendors.yahoo import reference_history
        from tradingagents.dataflows.vendors.yahoo.expectations import VendorExpectations
        facts, docs = complete_evidence()
        historical_facts, _ = reference_fixture(cik=docs.cik)
        additions = tuple(f.model_copy(update={"source_ids": (facts.sources[0].source_id,),
                                               "cik": docs.cik, "as_of": facts.as_of})
                          for f in historical_facts.facts if f.metric in
                          {"Revenue", "Gross Profit", "Common Shares Outstanding"})
        facts = facts.model_copy(update={"facts": tuple(f for f in facts.facts if f.metric != "Revenue") + additions})
        _, _, _, quotes = flow_fixture(monkeypatch)
        history_fn = reference_history.get_reference_history
        peer_packages = {ticker: reference_fixture(cik=cik, ticker=ticker)[0]
                         for ticker, cik in (("AKAM", "0001000001"), ("MSFT", "0001000002"))}
        revenue = next(f for f in facts.facts if f.metric == "Revenue")
        claim = {"kind": revenue.origin, "fact_id": revenue.fact_id, "metric": revenue.metric,
                 "value": str(revenue.value), "unit": revenue.unit,
                 "period_start": str(revenue.period_start), "period_end": str(revenue.period_end)}
        valid_report = ("Report.\n```financial_claims\n" + json.dumps([claim]) +
                        "\n```\n```disclosures\n[]\n```\n```peers\n" +
                        json.dumps([{"ticker": "MSFT", "reason": "Comparable cloud business"}]) + "\n```")
        monkeypatch.setattr(graph_fixture, "ARGS", {**graph_fixture.ARGS, "symbol": "DOCN",
            "ticker": "DOCN", "curr_date": date, "start_date": "2026-10-12", "end_date": date})

    class WiredModel(ScriptedModel):
        def _count(self):
            super()._count()
            transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
                "model": pilot.A, "usage": {"prompt_tokens": 10, "completion_tokens": 10,
                                             "cost": 0.0001}}))
            with httpx.Client(transport=transport) as client:
                client.send(httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions",
                    json={"model": pilot.A, "max_tokens": 8192,
                          "messages": [{"role": "user", "content": "offline scripted model"}]}))

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            result = super()._generate(messages, stop, run_manager, **kwargs)
            if mapped and not result.generations[0].message.tool_calls and any(
                "financial_claims" in str(message.content) for message in messages
            ):
                result.generations[0].message.content = valid_report
            return result

    model = WiredModel(structured=False)
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **kw: _Client(model))
    ticker = "DOCN" if mapped else "NVDA"
    spec = live_adapter.CliSpec(ticker, date, pilot.A, pilot.A, 2, 8192,
        analysis_cutoff_utc="2026-10-20T05:59:59+00:00" if mapped else "2026-01-10T06:59:59+00:00",
        market_observation_cutoff=market_cutoff, context_cap=65536)
    class Gateway:
        request_hashes = {}
        fetch_peer = None
        def common(self, domain):
            return b"" if domain == "memory" else b'{"files":{}}' if domain == "prior_publication" else b"{}"
        def peer(self, *a):
            if not mapped:
                raise RuntimeError("No peer was captured")
            symbol, cutoff = a
            package = peer_packages[symbol]
            value = {"status": "available", "package": package.model_dump(mode="json"),
                     "issuer_identity": {"ticker": symbol, "cik": package.cik,
                                         "as_of": date, "source": "SEC issuer map"},
                     "price_observation": quotes[symbol]}
            data = json.dumps(value).encode()
            key = "peer:" + pilot.manifest_hash({"ticker": symbol, "cutoff_utc": cutoff})
            peer_root = tmp_path / "peer-cache"
            peer_root.mkdir(exist_ok=True)
            (peer_root / f"{key}.json").write_bytes(data)
            self.request_hashes[key] = hashlib.sha256(data).hexdigest()
            return data
    capture = live_adapter.FrozenSourceCapture(tmp_path / "frozen")
    class CapturingReplay(live_adapter.FrozenVendorReplay):
        def lookup(self, domain, name, args, kwargs):
            self.calls.append({"domain": domain, "name": name,
                               "request_hash": live_adapter.source_request_hash(name, args, kwargs)})
            if name == "resolve_instrument_identity":
                value = {"company_name": "NVIDIA"}
                capture.record(domain, name, args, kwargs, value)
                return value
            if name == "cik_for":
                value = docs.cik if mapped else None
                capture.record(domain, name, args, kwargs, value)
                return value
            if name in {"get_financial_evidence", "get_filing_evidence"}:
                if mapped:
                    value = (facts if name == "get_financial_evidence" else docs).model_dump(mode="json")
                    capture.record(domain, name, args, kwargs, value)
                    return value
                capture.record(domain, name, args, kwargs,
                               {"__error__": "VendorUnavailableError", "message": "offline fixture has no SEC package"})
                raise VendorUnavailableError("offline fixture has no SEC package")
            if name == "get_price_observation":
                value = quotes[args[0]] if mapped else {"status": "unavailable", "reason": "offline price fixture"}
                capture.record(domain, name, args, kwargs, value)
                return value
            if name == "get_reference_history" and mapped:
                value = history_fn(*args, **kwargs)
                capture.record(domain, name, args, kwargs, value)
                return value
            if name == "get_vendor_expectations" and mapped:
                value = VendorExpectations(status="unavailable", reason="Offline consensus fixture",
                                           ticker=args[0], requested_as_of=args[1]).model_dump(mode="json")
                capture.record(domain, name, args, kwargs, value)
                return value
            if name == "default_peer_selection":
                value = {"kind": "previous", "status": "available", "reason": None,
                         "peers": [{"ticker": "AKAM", "reason": "Prior cloud comparison"}]} if mapped else {
                         "kind": "previous", "status": "available", "peers": [], "reason": "No prior set"}
                capture.record(domain, name, args, kwargs, value)
                return value
            value = "offline " + name
            capture.record(domain, name, args, kwargs, value)
            return value
    replay = CapturingReplay(Gateway())
    ledger = pilot.PilotLedger(tmp_path / "comparison.jsonl")
    approval = pilot.Approval("offline-manifest", "2", "reviewer/offline", 6)
    ledger.append({"type": "slot_claim", "slot": pilot.SLOTS[0].name,
                   "manifest_hash": approval.approved_manifest_sha256})
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.A},
                               max_calls=64, scope=pilot.SLOTS[0].name, allowed_kinds={"run"})
    wire = live_adapter.OpenRouterWireGuard(budget, {pilot.A: {
        "input_per_token": "0.0000001", "output_per_token": "0.0000001",
        "cache_read_per_token": "0", "cache_write_per_token": "0"}},
        max_output_tokens=8192, kind="run", allowed_resolved_models={pilot.A: {pilot.A}},
        context_cap=65536)
    result = live_adapter.execute_cli(spec, tmp_path / "run", wire, replay,
        openrouter_key="fake", sec_user_agent="offline-test",
        claim=live_adapter.ExecutionClaim("comparison", pilot.SLOTS[0].name), approval=approval)
    assert result["state"]["company_of_interest"] == ticker
    assert result["model_calls"] > 10
    assert result["state"]["market_observation_cutoff"] == market_cutoff
    files = capture.write(memory=b"", prior_publication={"files": {}})
    manifest = {"ticker": ticker, "analysis_date": date, "cutoff_utc": market_cutoff,
                "depth": 2, "source_version": "offline", "prompt_version": "offline",
                "tool_limit": 4, "context_cap": 65536,
                "analysts": ["market", "social", "news", "fundamentals"],
                "reviewer": {"model_id": "reviewer/offline", "settings": {"temperature": 0}},
                "files": files}
    frozen_gateway = pilot.FrozenSourceGateway(manifest, tmp_path / "frozen", tmp_path / "peer-cache")
    frozen_replay = live_adapter.FrozenVendorReplay(frozen_gateway)
    second_ledger = pilot.PilotLedger(tmp_path / "second-comparison.jsonl")
    second_ledger.append({"type": "slot_claim", "slot": pilot.SLOTS[0].name,
                          "manifest_hash": approval.approved_manifest_sha256})
    second_budget = pilot.BudgetGuard(second_ledger, pilot.Decimal("2"), allowed_models={pilot.A},
                                     max_calls=64, scope=pilot.SLOTS[0].name, allowed_kinds={"run"})
    second_wire = live_adapter.OpenRouterWireGuard(second_budget, {pilot.A: {
        "input_per_token": "0.0000001", "output_per_token": "0.0000001",
        "cache_read_per_token": "0", "cache_write_per_token": "0"}},
        max_output_tokens=8192, kind="run", allowed_resolved_models={pilot.A: {pilot.A}},
        context_cap=65536)
    replay_result = live_adapter.execute_cli(spec, tmp_path / "replay-run", second_wire, frozen_replay,
        openrouter_key="fake", sec_user_agent="offline-test",
        claim=live_adapter.ExecutionClaim("comparison", pilot.SLOTS[0].name), approval=approval)
    assert replay_result["model_calls"] == result["model_calls"]
    assert replay_result["state"]["trade_date"] == date
    if mapped:
        assert result["state"]["valuation_reference"]["phase"] == "final"
        assert result["state"]["valuation_reference"]["own_history"]["status"] == "available"
        assert {p["ticker"] for p in result["state"]["valuation_reference"]["peers"]["accepted"]} == {"MSFT"}
        assert len(frozen_gateway.request_hashes) == 2


@pytest.mark.unit
def test_real_openrouter_sdk_request_shape_under_guard(tmp_path, monkeypatch):
    import httpx2

    from tradingagents.default_config import build_default_config
    from tradingagents.llm_clients.factory import create_tier_client
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-fake")
    ledger = pilot.PilotLedger(tmp_path / "sdk.jsonl")
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.A}, max_calls=2)
    seen = []
    def answer(request):
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json={"id": "chatcmpl-offline", "object": "chat.completion",
            "created": 1, "model": pilot.A,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001}})
    client = httpx2.Client(transport=httpx2.MockTransport(answer))
    config = build_default_config()
    config.update(llm_provider="openrouter", quick_think_llm=pilot.A, deep_think_llm=pilot.A,
                  backend_url="https://openrouter.ai/api/v1", max_tokens=8192, llm_max_retries=0)
    wire = live_adapter.OpenRouterWireGuard(budget, {pilot.A: {
        "input_per_token": "0.0000001", "output_per_token": "0.0000001",
        "cache_read_per_token": "0", "cache_write_per_token": "0"}},
        max_output_tokens=8192, kind="run", allowed_resolved_models={pilot.A: {pilot.A}})
    with live_adapter.installed_http_guard(wire):
        model = create_tier_client(config, "quick", http_client=client).get_llm()
        assert model.invoke("hello").content == "hello"
    assert wire.request_count == 1
    assert seen[0]["model"] == pilot.A and seen[0].get("stream") is not True


@pytest.mark.unit
def test_docn_rpo_supplement_and_prior_are_frozen_and_replayed(tmp_path):
    from tradingagents.agents.kpi_comparisons import retrieve_rpo_comparison
    from tradingagents.dataflows.vendors.sec_documents import DisclosurePackage
    root = Path(__file__).resolve().parent / "fixtures"
    current = DisclosurePackage.model_validate(json.loads(
        (root / "docn_2026q3/rpo_context.json").read_text())["package"])
    prior = DisclosurePackage.model_validate(json.loads(
        (root / "docn_2026q2/prior_quarter_rpo.json").read_text())["package"])
    missing = current.model_copy(update={"documents": (
        current.documents[0].model_copy(update={"rpo_facts": ()}),)})
    capture = live_adapter.FrozenSourceCapture(tmp_path / "frozen")
    capture.record("sec_filings", "get_current_quarter_rpo_evidence", (missing,), {}, current)
    capture.record("sec_filings", "get_prior_quarter_evidence",
                   ("DOCN", "2026-11-04", "2026-09-30"), {}, prior)
    files = capture.write(memory=b"", prior_publication={"files": {}})
    manifest = {"ticker": "DOCN", "analysis_date": "2026-11-04",
                "cutoff_utc": "2026-11-04T22:00:00+00:00", "depth": 2,
                "source_version": "offline", "prompt_version": "offline", "tool_limit": 4,
                "context_cap": 65536, "analysts": ["market", "social", "news", "fundamentals"],
                "reviewer": {"model_id": "reviewer/offline", "settings": {"temperature": 0}},
                "files": files}
    replay = live_adapter.FrozenVendorReplay(pilot.FrozenSourceGateway(
        manifest, tmp_path / "frozen", tmp_path / "peers"))
    with replay.installed():
        result = retrieve_rpo_comparison("DOCN", missing)
    assert result["status"] == "pass"
    assert result["current_value"] == "799707000"
    assert result["prior_value"] == "893828000"
    assert {call["name"] for call in replay.calls} == {
        "get_current_quarter_rpo_evidence", "get_prior_quarter_evidence"}


@pytest.mark.unit
def test_review_callback_makes_one_guarded_json_call(tmp_path):
    import httpx2
    ledger = pilot.PilotLedger(tmp_path / "reviews.jsonl")
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.B_DEEP},
                               max_calls=6, scope="reviews", allowed_kinds={"review"})
    wire = live_adapter.OpenRouterWireGuard(budget, {pilot.B_DEEP: {
        "input_per_token": "0.0000001", "output_per_token": "0.0000001",
        "cache_read_per_token": "0", "cache_write_per_token": "0"}},
        max_output_tokens=4096, kind="review",
        allowed_resolved_models={pilot.B_DEEP: {pilot.B_DEEP}})
    seen = []
    def answer(request):
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json={"model": pilot.B_DEEP,
            "choices": [{"message": {"content": json.dumps({"score": 4,
                "findings": ["Claim [FACT-1] is corroborated by the retained filing."]})}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 60, "cost": 0.0001}})
    client = httpx2.Client(transport=httpx2.MockTransport(answer))
    result = live_adapter.review_saved_output({"opaque_id": "blind", "evidence": {"filing": "FACT-1"},
        "analysis": {"fundamentals_report": "Revenue [FACT-1]"}, "debates": {},
        "rubric": {"score_basis": "evidence", "scale": "0–5"}}, budget,
        wire=wire, api_key="offline-fake", reviewer_model=pilot.B_DEEP,
        settings={"temperature": 0, "max_tokens": 4096}, client=client)
    assert result["score"] == 4 and len(result["findings"]) == 1
    assert result["model_id"] == pilot.B_DEEP
    assert budget.calls == 1 and not budget.outstanding
    assert seen[0]["temperature"] == 0 and seen[0]["max_tokens"] == 4096
    assert seen[0].get("stream") is not True and "reasoning" not in seen[0]


@pytest.mark.unit
def test_review_callback_rejects_invalid_score_after_one_paid_call(tmp_path):
    import httpx2
    ledger = pilot.PilotLedger(tmp_path / "reviews-invalid.jsonl")
    budget = pilot.BudgetGuard(ledger, pilot.Decimal("2"), allowed_models={pilot.B_DEEP},
                               max_calls=6, scope="reviews", allowed_kinds={"review"})
    wire = live_adapter.OpenRouterWireGuard(budget, {pilot.B_DEEP: {
        "input_per_token": "0.0000001", "output_per_token": "0.0000001",
        "cache_read_per_token": "0", "cache_write_per_token": "0"}},
        max_output_tokens=4096, kind="review",
        allowed_resolved_models={pilot.B_DEEP: {pilot.B_DEEP}})
    def answer(request):
        return httpx2.Response(200, json={"model": pilot.B_DEEP,
            "choices": [{"message": {"content": '{"score": 8, "findings": []}'}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20, "cost": 0.00001}})
    client = httpx2.Client(transport=httpx2.MockTransport(answer))
    payload = {"opaque_id": "blind", "evidence": {}, "analysis": {}, "debates": {}, "rubric": {}}
    with pytest.raises(ValueError, match="score or findings"):
        live_adapter.review_saved_output(payload, budget, wire=wire, api_key="offline-fake",
            reviewer_model=pilot.B_DEEP, settings={"temperature": 0, "max_tokens": 4096},
            client=client)
    assert budget.calls == 1 and not budget.outstanding


@pytest.mark.unit
def test_isolation_disables_dotenv_and_moves_yfinance_cache(tmp_path, monkeypatch):
    import yfinance as yf
    locations = []
    monkeypatch.setattr(yf, "set_tz_cache_location", locations.append)
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated")
    spec = live_adapter.CliSpec("DOCN", "2026-11-05", pilot.A, pilot.A, 1, 8192)
    live_adapter.configure_isolated_env(spec, tmp_path, openrouter_key="offline-fake",
                                        sec_user_agent="offline-agent")
    assert live_adapter.os.environ["PYTHON_DOTENV_DISABLED"] == "1"
    assert "OPENAI_API_KEY" not in live_adapter.os.environ
    assert locations == [str(tmp_path / "cache/yfinance")]
