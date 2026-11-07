"""Build 2 paid-send boundaries exercised offline; fixtures carry no authority."""
import dataclasses
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_valuation_reference_live_adapter import (
    Request,
    Response,
    live_adapter as live,
    pilot,
)


def spec():
    return live.CliSpec("DOCN", "2026-11-06", pilot.B_DEEP, pilot.A, 3, 16384,
                        analysis_timezone="America/New_York", analysis_cutoff_utc="2026-11-07T04:59:59.999999+00:00",
                        proof_scope=live.BUILD2_SCOPE)


@pytest.mark.parametrize("changed", [{"ticker": "MSFT"}, {"depth": 1}, {"quick_model": pilot.A},
                                     {"max_output_tokens": 32768}, {"max_tool_rounds": 3},
                                     {"analysis_timezone": "UTC"}, {"context_cap": 20000}])
def test_fixed_build2_scope(changed):
    spec().validate()
    with pytest.raises(ValueError):
        dataclasses.replace(spec(), **changed).validate()

SOURCE = Path(__file__).resolve().parents[1]
def harness():
    obj = importlib.util.spec_from_file_location("build2_test_runner", SOURCE / "docs/reviews/valuation-build2-proof-tools/live_cli.py")
    mod = importlib.util.module_from_spec(obj)
    obj.loader.exec_module(mod)
    return mod


def fixture(tmp_path, monkeypatch):
    h = harness()
    ledger = pilot.PilotLedger(tmp_path / "fresh.jsonl")
    monkeypatch.setattr(h, "LEDGER", ledger.path)
    monkeypatch.setattr(h.live, "BUILD2_LEDGER", ledger.path)
    now = datetime(2026, 11, 7, 6, tzinfo=UTC)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    monkeypatch.setattr(h, "datetime", Clock)
    chart = tmp_path / "chart.json"
    chart.write_text(json.dumps({"chart":{"result":[{"meta":{"symbol":"DOCN","currency":"USD",
        "exchangeTimezoneName":"America/New_York","currentTradingPeriod":{"regular":{
            "start":1793975400, "end":1793998800}}}}]}}))
    cal = tmp_path / "calendar.html"
    cal.write_text("NYSE core trading hours regular session 9:30-16:00 ET")
    def source(p,url):
        return {"path":str(p),"sha256":h.sha(p),"url":url,"http_status":200,"retrieved_at":now.isoformat()}
    session = {"session_date":"2026-11-06","regular_close_utc":"2026-11-06T21:00:00+00:00",
               "observed_at": now.isoformat(),"nyse-calendar":source(cal,"https://www.nyse.com/trade/hours-calendars"),
               "docn-chart":source(chart,"https://query1.finance.yahoo.com/v8/finance/chart/DOCN?interval=1d&range=1d")}
    pricing = {"prompt":"0.000004","completion":"0.000015","input_cache_write_1h":"0.000016"}
    metadata = {"observed_at":(now-timedelta(seconds=5)).isoformat(),
                "results":{**{m:{"endpoints":[{"name": m+"-20261101", "pricing":pricing}]} for m in h.MODELS},
                           "key":{"limit_remaining":"40","usage":"2.00"}}}
    path = tmp_path / "provider.json"
    path.write_text(json.dumps(metadata))
    receipt = h.provider(path)
    old = pilot.PilotLedger(tmp_path / "old.jsonl")
    old.append({"type":"reserve","ticket":"historic","usd":"3.5"})
    candidate = {"worktree_root":str(tmp_path), "candidate_head":"a"*40, "reviewed_provider":receipt,"old_ledgers":{str(old.path):h.sha(old.path)},
                 "prior_unknown_reserved_usd":"3.5","prior_committed_exposure_usd":"3.5"}
    return h, ledger, session, receipt, candidate, old


def test_two_explicit_attempts_shared_cap_history_and_no_resume(tmp_path, monkeypatch):
    h, ledger, session, receipt, candidate, old = fixture(tmp_path, monkeypatch)
    first, second = h.ATTEMPTS
    def claim(name, cap, report=receipt):
        return h.claim(name, cap, candidate, session, report, ledger)
    with pytest.raises(RuntimeError, match="sequence"):
        claim(second, "10")
    for report in ({**receipt, "observed_at":"2026-11-06T19:05:00+00:00"},
                   {**receipt, "remaining_usd":"24.5"}):
        with pytest.raises(ValueError):
            claim(first, "22", report)
    assert not ledger.events()
    authority = claim(first,"22")
    budget = h.LinkedBudget(ledger, Decimal("24"), candidate=candidate, scope="proof:"+first,
                            allowed_models=h.MODELS, allowed_kinds={"run"}, max_calls=64, scope_ceiling=Decimal("22"))
    h.live.verify_budget_binding(authority,budget,spec(),None)
    # Final candidate-machine recheck also consumes a mismatched launch.
    monkeypatch.setattr(h.live,"build2_machine",lambda:["Apple M2 Pro","34359738368"])
    with pytest.raises(RuntimeError, match="root or runtime changed"):
        h.live.start_execution(authority,ledger,spec())
    with pytest.raises(RuntimeError, match="already started"):
        h.live.start_execution(authority,ledger,spec())
    budget.reserve(pilot.A, "4.25", kind="run")  # unknown hold
    with pytest.raises(RuntimeError, match="sequence"):
        claim(first,"5")
    with pytest.raises(RuntimeError, match="sequence"):
        claim(second,"12")
    ledger.append({"type":"attempt_end","name":first,"execution":"failed"})
    fresh = {**receipt,"observed_at":"2026-11-07T05:59:59+00:00"}
    with pytest.raises(ValueError, match="remaining Build2"):
        claim(second,"20",fresh)
    with pytest.raises(ValueError, match="headroom"):
        claim(second,"19", {**fresh, "remaining_usd":"26.50"})
    with pytest.raises(RuntimeError, match="sequence"):
        claim(second,"19")
    claim(second,"19",fresh)
    for name in (first,second,"Build2-DOCN-3"):
        with pytest.raises((RuntimeError,ValueError)):
            claim(name,"1",fresh)
    assert ledger.committed_usd() == Decimal("4.25")
    old.append({"type":"unknown","ticket":"historic"})
    with pytest.raises(ValueError, match="Historical proof ledger changed"):
        budget.reserve(pilot.A,"1",kind="run")


def test_wrong_machine_no_qualification(tmp_path,monkeypatch):
    h = harness()
    monkeypatch.setattr(h.subprocess, "check_output", lambda *a, **kw: "Apple M1 Pro\n17179869184\n")
    with pytest.raises(RuntimeError, match="Machine 2"):
        h.environment()


def test_failed_credentials_still_count_before_setup(tmp_path, monkeypatch):
    h,ledger,session,receipt,candidate,_ = fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(h,"PRIVATE",tmp_path)
    monkeypatch.setattr(h,"RECEIPTS",tmp_path)
    monkeypatch.setattr(h,"provider",lambda path:receipt)
    monkeypatch.setattr(h,"verify_candidate",lambda:candidate)
    name=h.ATTEMPTS[0]
    h.create(tmp_path/(name+".session.json"),session)
    with pytest.raises(FileNotFoundError):
        h.run(name,"18",tmp_path/"nonexistent-not-a-key")
    events=ledger.events()
    assert [e["type"] for e in events] == ["allowance","attempt_claim","attempt_end"]
    assert events[-1]["execution"]=="failed" and events[-1]["reserved_sends"] == 0
    with pytest.raises(RuntimeError, match="no reuse"):
        h.run(name,"18",tmp_path/"nonexistent-not-a-key")


def test_real_http_audit_retry_reserves_each_send_before_transport(tmp_path, monkeypatch):
    import httpx

    import tradingagents.graph.setup as setup
    h,ledger,_,receipt,candidate,_=fixture(tmp_path,monkeypatch)
    budget=h.LinkedBudget(ledger,Decimal("24"),candidate=candidate,allowed_models=h.MODELS,max_calls=64,
                          scope="proof:"+h.ATTEMPTS[0],allowed_kinds={"run"},scope_ceiling=Decimal("19"))
    wire=h.live.OpenRouterWireGuard(budget,receipt["rates"],max_output_tokens=16384,kind="run",
                    serialize_paid_requests=True,allowed_resolved_models={m:set(v) for m,v in receipt["aliases"].items()})
    calls=[]
    def send(request):
        assert [e["type"] for e in ledger.events()][-2:] == ["reserve","request_meta"]
        calls.append(request)
        if len(calls)==1:
            return httpx.Response(502,json={"error":{"message":"upstream error"}})
        return httpx.Response(200,json={"id":"gen-offline","model":pilot.A+"-20261101","provider":"offline",
            "choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"{}"}}],
            "usage":{"prompt_tokens":85,"completion_tokens":12,"cost":0.0008}})
    url="https://openrouter.ai/api/v1/chat/completions"
    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        class Model:
            def with_structured_output(self,*args,**kwargs): return self
            def invoke(self,prompt):
                response=client.post(url,json={"model":pilot.A,"max_tokens":16384,
                    "messages":[{"role":"user","content":"offline audit"}]},headers={"Authorization":"Bearer offline-token"})
                response.raise_for_status()
                raise ValueError("simulated structured parse failure")
        with h.live.installed_http_guard(wire), h.live.one_document_audit_attempt(spec()):
            record=setup.create_advisory_audit(Model(),deep_model_id=pilot.A,quick_model_id=pilot.B_DEEP,
                                        sdk_retries_disabled=True)({})["advisory_audit"]
    report=h.accounting(ledger,h.ATTEMPTS[0])
    assert len(calls)==len(record["attempts"])==report["reserved_sends"]==2
    assert len(report["unknown_reservations"])==report["usage_covered_sends"]==1
    assert "offline-token" not in ledger.path.read_text() and "Authorization" not in ledger.path.read_text()
    with pytest.raises(RuntimeError,match="modality"):
        wire.before(Request({"model":pilot.A,"models":[pilot.A],"messages":[],"max_tokens":16384}))


def test_natural_case_proof_reports_empty_and_proves_real_card_from_fixture(tmp_path, monkeypatch):
    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state
    from tests.test_valuation_comparison import state as market
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_decision_context,
    )
    from tradingagents.agents.shared_valuation import prepare_shared_valuation
    h=harness()
    inputs={**state([revenue_case()]),**market(monkeypatch)}
    inputs.update(final_rating="Hold",unvalidated_outputs={"portfolio_manager":{
        "case_contract":1,"contract_version":"decision_horizon_v1","valuation_request":None,
        "structured":{"time_horizon":"3-6 months","no_case_reason":"Uncertain multiple"}}})
    inputs["shared_valuation_scenarios"]=prepare_shared_valuation(inputs)
    assert inputs["shared_valuation_scenarios"]["rows"],inputs["shared_valuation_scenarios"]
    p=tmp_path/"results/reports/DOCN_fixture/5_portfolio/decision.md"
    p.parent.mkdir(parents=True)
    (p.parents[1]/"evidence.json").write_text("{}")
    (p.parents[1]/"complete_report.md").write_text("Fixture only")
    def check():
        inputs["decision_context"]=prepare_decision_context(inputs)
        p.write_text(render_decision_context(inputs["decision_context"],include_mechanical=False))
        return h.assess(inputs,tmp_path)
    result=check()
    assert result["status"]=="complete",result["checks"]
    row=inputs["shared_valuation_scenarios"]["rows"][0]
    pm={"method":"case","case_id":row["case_id"],"version":1,"rerating_assumption":"none"}
    inputs["unvalidated_outputs"]["portfolio_manager"]["valuation_request"]=pm
    inputs["target_validation"]={"request":pm}
    result=check()
    assert result["status"]=="complete" and result["adopted_case"]["decision_date"] is None
    inputs["financial_claim_validation"]["raw_report"]=state([])["financial_claim_validation"]["raw_report"]
    inputs["shared_valuation_scenarios"]=prepare_shared_valuation(inputs)
    result=check()
    assert result["status"]=="incomplete" and not result["verified_cases"]


def test_bad_model_alias_usage_keeps_full_hold_and_blocks_next_send(tmp_path,monkeypatch):
    h,ledger,_,receipt,candidate,_=fixture(tmp_path,monkeypatch)
    budget=h.LinkedBudget(ledger,Decimal("24"),candidate=candidate,allowed_models=h.MODELS,max_calls=64,
                          scope="proof:"+h.ATTEMPTS[0],allowed_kinds={"run"},scope_ceiling=Decimal("19"))
    wire=h.live.OpenRouterWireGuard(budget,receipt["rates"],max_output_tokens=16384,kind="run",
              serialize_paid_requests=True,allowed_resolved_models={m:set(v) for m,v in receipt["aliases"].items()})
    request=Request({"model":pilot.A, "messages":[{"role":"user","content":"offline"}], "max_tokens":16384})
    ticket=wire.before(request)
    reserved=ledger.committed_usd()
    with pytest.raises(h.live.BudgetStoppedError):
        wire.after(ticket,Response({"model":"wrong-model","usage":{"prompt_tokens":100,"completion_tokens":20,"cost":0.001}}))
    with pytest.raises(h.live.BudgetStoppedError):
        wire.before(request)
    assert ledger.committed_usd()==reserved and not any(e["type"]=="settle" for e in ledger.events())


def test_after_close_receipt_file_hash_session_and_weekend_clock(tmp_path,monkeypatch):
    h,ledger,session,receipt,candidate,_=fixture(tmp_path,monkeypatch)
    assert h.live.build2_cutoff(session)=="2026-11-07T04:59:59.999999+00:00"
    assert h.live.build2_cutoff({**session,"observed_at":"2026-11-06T21:20:00+00:00"})=="2026-11-06T21:20:00+00:00"
    for changed in ({"session_date":"2026-11-05"}, {"regular_close_utc":"2026-11-07T21:00:00+00:00"},
                    {"nyse-calendar":{**session["nyse-calendar"],"retrieved_at":"2026-11-06T23:59:00+00:00"}},
                    {"docn-chart":{**session["docn-chart"],"sha256":"0"*64}}):
        with pytest.raises(ValueError):
            h.claim(h.ATTEMPTS[0],"18",candidate,{**session,**changed},receipt,ledger)
    assert not ledger.events()


def test_fresh_rates_do_not_accept_unbudgeted_charge(tmp_path,monkeypatch):
    h,ledger,_,_,_,_=fixture(tmp_path,monkeypatch)
    p=tmp_path/"provider.json"
    data=json.loads(p.read_bytes())
    data["results"][pilot.A]["endpoints"][0]["pricing"]["overrides"] = [
        {"min_prompt_tokens": 272000, "prompt": "0.000008", "completion": "0.000025"}
    ]
    p.write_text(json.dumps(data))
    rates = h.provider(p)["rates"][pilot.A]
    assert Decimal(rates["input_per_token"]) == Decimal("0.000008")
    assert Decimal(rates["output_per_token"]) == Decimal("0.000025")
    data["results"][pilot.A]["endpoints"][0]["pricing"]["request"]="0.001"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="nonzero pricing component"):
        h.provider(p)
    assert not ledger.events()


def test_one_matching_row_cannot_mask_two_incorrect_published_case_prices(tmp_path, monkeypatch):
    from copy import deepcopy

    from tests.test_case_valuation import revenue_case
    from tests.test_shared_valuation import state
    from tests.test_valuation_comparison import state as market
    from tradingagents.agents import decision_context
    from tradingagents.agents.shared_valuation import prepare_shared_valuation

    cases = [{**revenue_case(), "name": name} for name in ("Low", "Middle", "High")]
    inputs = {**state(cases), **market(monkeypatch), "final_rating": "Hold",
              "unvalidated_outputs": {"portfolio_manager": {"case_contract": 1,
              "contract_version": "decision_horizon_v1", "valuation_request": None,
              "structured": {"time_horizon": "3-6 months", "no_case_reason": "Uncertain multiple"}}}}
    inputs["shared_valuation_scenarios"] = prepare_shared_valuation(inputs)
    card = decision_context.prepare_decision_context(inputs)
    rows = card["case_groups"][0]["cases"]
    assert len(rows) == 3
    for row in rows[1:]:
        row["value"] = "999"
    inputs["decision_context"] = card
    monkeypatch.setattr(decision_context, "prepare_decision_context", lambda _: deepcopy(card))
    report = tmp_path / "results/reports/DOCN_fixture"
    (report / "5_portfolio").mkdir(parents=True)
    (report / "evidence.json").write_text("{}")
    (report / "complete_report.md").write_text("Synthetic proof fixture")
    (report / "5_portfolio/decision.md").write_text(decision_context.render_decision_context(card))
    result = harness().assess(inputs, tmp_path)
    assert result["status"] == "incomplete"
    assert [r["case_id"] for r in result["verified_cases"]] == [rows[0]["case_id"]]
    assert [r["case_id"] for r in result["mismatched_cases"]] == [r["case_id"] for r in rows[1:]]
