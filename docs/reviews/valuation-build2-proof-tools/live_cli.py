"""Machine 2 only: explicit Build2 DOCN attempts, one fresh $24 aggregate allowance."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import logging
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
SOURCE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(SOURCE), str(SOURCE / "docs/reviews/valuation-reference-proof-tools")]
# Bind these helpers to the selected checkout before importing them.
import live_adapter as live  # noqa: E402
from pilot import B_DEEP, A, BudgetGuard, PilotLedger, manifest_hash  # noqa: E402

ROOT = live.BUILD2_ROOT
WT = ROOT / "source"
PRIVATE = ROOT / "private"
OLD = PRIVATE / "prior-ledgers"
LEDGER = live.BUILD2_LEDGER
FROZEN = PRIVATE / "build2-candidate.json"
RECEIPTS = PRIVATE / "build2-receipts"
MODELS = {A, B_DEEP}
ATTEMPTS = live.BUILD2_ATTEMPTS
BASE = "3d1b8f329f53b98daaecf05df4e522bc5491c87c"
MANIFEST_SHA = "0cdbc71411770efdb61a3eb1f758feeb446b1726e0ae77a21c50b5cc78fda613"
CONFIG = {"models": {"quick": B_DEEP, "deep": A}, "depth": 3,
          "analysts": ["market", "social", "news", "fundamentals"],
          "timezone": "America/New_York", "output_cap": 16384, "max_tool_rounds": 4,
          "sdk_retries": 0, "audit_max_attempts": 2, "max_wire_calls": 64,
          "ticker": "DOCN", "ceiling_usd": "24", "attempt_ids": list(ATTEMPTS)}


def safe(path):
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError(f"Unsafe path: {path}")
    return path


def sha(path):
    return hashlib.sha256(safe(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(safe(path).read_bytes())


def create(path, record):
    safe(path)
    with path.open("x") as out:
        json.dump(record, out, sort_keys=True, indent=2)
        out.flush()
        os.fsync(out.fileno())


def money(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid monetary value")
    return result


def holds(ledger):
    events = ledger.events()
    settled = {e["ticket"] for e in events if e["type"] == "settle"}
    return {e["ticket"]: e["usd"] for e in events if e["type"] == "reserve" and e["ticket"] not in settled}


def history():
    manifest = OLD / "manifest.json"
    if sha(manifest) != MANIFEST_SHA:
        raise ValueError("Historical ledger manifest differs from verified transfer")
    old = {str(OLD / name): digest for name, digest in read(manifest)["copies_sha256"].items()}
    total, unknown = Decimal(0), Decimal(0)
    for name, digest in old.items():
        if sha(Path(name)) != digest:
            raise ValueError("Historical ledger bytes differ")
        ledger = PilotLedger(Path(name))
        total += ledger.committed_usd()
        unknown += sum(map(money, holds(ledger).values()), Decimal(0))
    return {"old_ledgers": old, "prior_committed_exposure_usd": str(total),
            "prior_unknown_reserved_usd": str(unknown)}


def environment():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=WT, text=True).strip()
    cpu, ram = live.build2_machine()
    if (WT != SOURCE or Path(sys.prefix) != WT / ".venv" or git("rev-parse", "--show-toplevel") != str(WT)
            or git("branch", "--show-current") != "codex/valuation-cases-build2-a3"
            or git("remote", "get-url", "origin") != "https://github.com/zippirot/TradingAgents.git"):
        raise RuntimeError("Build2 worktree, origin, branch or interpreter differs")
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=WT, check=True)
    dependencies = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        dependencies[name] = [dist.version, hashlib.sha256((dist.read_text("RECORD") or "").encode()).hexdigest()]
    origins = {}
    for name in ("cli", "tradingagents", "pilot", "live_adapter", "openai", "httpx", "httpx2",
                 "langchain_openai", "langgraph.graph"):
        path = Path(importlib.util.find_spec(name).origin).resolve()
        base = WT if name in {"cli", "tradingagents", "pilot", "live_adapter"} else WT / ".venv"
        if not path.is_relative_to(base):
            raise RuntimeError(f"Wrong loaded module: {name}")
        origins[name] = str(path)
    setup = ROOT / "evidence/setup.json"
    inputs = {str(PRIVATE / Path(k).name): v for k, v in read(setup)["plans_inputs_sha256"].items()}
    if not all(sha(Path(k)) == v for k, v in inputs.items()):
        raise RuntimeError("Transferred build inputs differ")
    return {"machine": [cpu, ram], "worktree_root": str(WT), "candidate_head": git("rev-parse", "HEAD"),
            "repository_origin": git("remote", "get-url", "origin"), "tree": git("rev-parse", "HEAD^{tree}"), "clean": not bool(git("status", "--porcelain")),
            "runner_sha256": sha(Path(__file__).resolve()), "module_origins": origins,
            "interpreter": sys.executable, "python_version": sys.version,
            "dependency_manifest_sha256": manifest_hash(dependencies), "setup_sha256": sha(setup),
            "inputs": inputs, "config": CONFIG, **history()}


def provider(path):
    data = read(path)
    rates = live.conservative_route_rates(data, MODELS)
    aliases = live.resolved_model_ids(data, MODELS)
    # This proof sends text only. Refuse unaccounted nonzero pricing components.
    for model in MODELS:
        for endpoint in data["results"][model]["endpoints"]:
            pricing = endpoint["pricing"]
            for tier in [pricing, *(pricing.get("overrides") or [])]:
                for key, value in tier.items():
                    if key in {"prompt", "completion", "input_cache_read", "input_cache_write",
                               "input_cache_write_1h", "overrides", "min_context", "min_context_length",
                               "context_length", "min_prompt_tokens", "threshold", "from_tokens",
                               # Text-only wire rejects hosted search, images and audio.
                               "web_search", "image", "audio", "input_audio_cache", "audio_output"}:
                        continue
                    if value is not None and money(value) != 0:
                        raise ValueError(f"Unsupported nonzero pricing component: {key}")
        if any(money(rates[model][key]) <= 0 for key in ("input_per_token", "output_per_token")):
            raise ValueError("Missing positive text route prices")
    key = data["results"]["key"]
    return {"sha256": sha(path), "observed_at": data["observed_at"],
            "rates": rates, "aliases": {k: sorted(v) for k,v in aliases.items()},
            "usage_usd": str(money(key["usage"])), "remaining_usd": str(money(key["limit_remaining"]))}


def freeze():
    candidate = environment()
    if not candidate["clean"] or candidate["candidate_head"] == BASE:
        raise RuntimeError("Freeze needs a clean committed Build2 candidate")
    candidate["reviewed_provider"] = provider(RECEIPTS / "reviewed.provider.json")
    now = datetime.now(UTC)
    if live._b3_aware_time(candidate["reviewed_provider"]["observed_at"], now) < now - timedelta(minutes=10):
        raise ValueError("Refresh reviewed provider metadata before freezing")
    create(FROZEN, candidate)
    return {"candidate_sha256": sha(FROZEN), "candidate_head": candidate["candidate_head"]}


def verify_candidate():
    candidate = read(FROZEN)
    reviewed = provider(RECEIPTS / "reviewed.provider.json")
    if candidate != {**environment(), "reviewed_provider": reviewed} or not candidate["clean"]:
        raise RuntimeError("Frozen Build2 source, inputs, dependencies, history or rates changed")
    return candidate


def claim(name, cap, candidate, session, receipt, ledger):
    if name not in ATTEMPTS or safe(ledger.path) != LEDGER:
        raise ValueError("Wrong attempt or ledger")
    cap = money(cap)
    if not 0 < cap <= 24:
        raise ValueError("Invalid per-attempt ceiling")
    now = datetime.now(UTC)
    observed = live._b3_aware_time(receipt["observed_at"], now)
    if observed < now - timedelta(minutes=10):
        raise ValueError("Stale per-attempt provider receipt")
    live._validate_after_close_receipt({"session": session, "analysis_date": session["session_date"]}, now, weekend=True)
    if any(live._b3_aware_time(t, now) < now - timedelta(minutes=10)
           for t in (session["observed_at"], session["nyse-calendar"]["retrieved_at"], session["docn-chart"]["retrieved_at"])):
        raise ValueError("Stale session receipt")
    reviewed = candidate["reviewed_provider"]
    if (receipt["aliases"] != reviewed["aliases"] or any(
            money(receipt["rates"][m][k]) > money(v)
            for m in MODELS for k, v in reviewed["rates"][m].items())):
        raise ValueError("Fresh served model or prices differ from reviewed envelope")
    digest = manifest_hash(candidate)
    with ledger.budget_lock():
        events = ledger.events()
        attempts = [e for e in events if e["type"] == "attempt_claim"]
        idx = ATTEMPTS.index(name)
        if ([e["phase"] for e in attempts] != list(ATTEMPTS[:idx])
                or (events and [e.get("approval_sha256") for e in events if e["type"] == "allowance"] != [digest])
                or (idx and (not any(e["type"] == "attempt_end" and e["name"] == ATTEMPTS[0] for e in events)
                             or observed <= datetime.fromisoformat(attempts[0]["provider_receipt"]["observed_at"])))):
            raise RuntimeError("Attempt sequence, prior completion or frozen allowance differs; no resume")
        current_unknown = sum(map(money, holds(ledger).values()), Decimal(0))
        if cap + ledger.committed_usd() > 24:
            raise ValueError("Requested attempt cap exceeds remaining Build2 authority")
        if money(receipt["remaining_usd"]) < cap + current_unknown + money(candidate["prior_unknown_reserved_usd"]):
            raise ValueError("Account headroom cannot cover this attempt and unknown holds")
        if not events:
            ledger.append({"type": "allowance", "approval_sha256": digest, "ceiling_usd": "24",
                           "prior_unknown_reserved_usd": candidate["prior_unknown_reserved_usd"],
                           "old_ledgers": candidate["old_ledgers"], "attempts": 2})
        ledger.append({"type": "attempt_claim", "phase": name, "ticker": "DOCN", "attempt_cap_usd": str(cap),
                       "approval_sha256": digest, "approval_record": candidate, "provider_receipt": receipt,
                       "session": session, "analysis_date": session["session_date"]})
    return live.ExecutionClaim("proof", name, digest)


class LinkedBudget(BudgetGuard):
    def __init__(self, *args, candidate, **kwargs):
        super().__init__(*args, **kwargs)
        self.candidate = candidate

    def reserve(self, *args, **kwargs):
        live._document_access_prior_exposure(self.candidate)
        return super().reserve(*args, **kwargs)


def accounting(ledger, name):
    events = ledger.events()
    tickets = {e["ticket"] for e in events if e["type"] == "reserve" and e["scope"] == "proof:" + name}
    responses = [e for e in events if e["type"] == "response_meta" and e["ticket"] in tickets]
    unknown = holds(ledger)
    return {"attempt": name, "aggregate_committed_usd": str(ledger.committed_usd()),
            "attempt_committed_usd": str(ledger.committed_scope_usd("proof:" + name)),
            "unknown_reservations": {k:v for k,v in unknown.items() if k in tickets},
            "reserved_sends": len(tickets), "usage_covered_sends": len(responses),
            "observed_prompt_tokens": sum(e["prompt_tokens"] for e in responses),
            "observed_completion_tokens": sum(e["completion_tokens"] for e in responses),
            "observed_billed_usd": str(sum((money(e["cost_usd"]) for e in responses), Decimal(0)))}


def assess(state, work):
    """Evidence-only check: replay raw inputs, independently price and inspect on-disk card."""
    from tradingagents.agents.audit_pass import prepare_audit_dispositions
    from tradingagents.agents.decision_context import (
        prepare_decision_context,
        render_condition_summary,
    )
    from tradingagents.agents.shared_valuation import prepare_shared_valuation, replay_cases

    saved = state.get("shared_valuation_scenarios") or {}
    analyst = prepare_shared_valuation(state)
    replay = replay_cases(state)
    card = prepare_decision_context(state)
    original_card = state.get("decision_context") or {}
    pm = (state.get("unvalidated_outputs") or {}).get("portfolio_manager") or {}
    request = pm.get("valuation_request")
    selected = card.get("adopted_case")
    reports = list((work / "results/reports").glob("DOCN_*/5_portfolio/decision.md"))
    decision = safe(reports[0]).read_text() if len(reports) == 1 else ""
    report_hashes = {}
    if decision:
        for path in (reports[0], reports[0].parents[1] / "evidence.json",
                     reports[0].parents[1] / "complete_report.md"):
            report_hashes[str(path.relative_to(work))] = sha(path)
    checks = {"analyst_provenance": analyst["requests"] == saved.get("analyst_requests", saved.get("requests")),
              "replayed_cases_and_revisions": saved == replay,
              "current_card": all(card.get(k) == original_card.get(k) for k in
                                  ("basis", "horizon", "case_groups", "adopted_case", "no_case_reason")),
              "explicit_horizon": card["horizon"]["status"] == "explicit",
              "rendered_cases": bool(card["case_groups"]) and
                                render_condition_summary(card, include_mechanical=False) in decision}
    price = state.get("price_observation") or {}
    verified = []
    mismatched = []
    expected_ids = set()
    published = [(g, c) for g in card["case_groups"] for c in g["cases"]]
    for row in replay["rows"]:
        req, priced = row["request"], row["result"]
        if req["method"] != "revenue_case" or row["diagnostic_only"] or priced["status"] != "supported":
            continue
        cap = req["capital"]
        basis = req["multiple_basis"]
        amounts = {k: Decimal(v["value"]) for k,v in cap["obligations"].items()}
        categories = {"borrowings_only": ["borrowings"], "finance_equipment": ["borrowings",
                      *(["finance_equipment"] if "finance_equipment" in amounts else ["finance_leases", "equipment"])]}
        categories["all_leases"] = [*categories["finance_equipment"], "operating_leases"]
        with localcontext() as ctx:
            ctx.prec = 60
            equity = Decimal(req["forecast"]["value"]) * Decimal(req["multiple"])
            if basis != "equity":
                equity -= sum(amounts[k] for k in categories[basis]) - Decimal(cap["cash"]["value"])
            per_share = equity / Decimal(cap["closing_shares"]["value"])
        period_clock = ("trailing at the future valuation date" if req["multiple_period"] == "trailing"
                        else "forward from the analysis date")
        identity = (row["case_id"], row["version"])
        expected_ids.add(identity)
        matches = [(g, c) for g, c in published if (c["case_id"], c["version"]) == identity]
        evidence = {"case_id": row["case_id"], "version": row["version"], "per_share": str(per_share),
                    "basis": basis, "period_end": cap["valuation_date"], "source_ids": priced["input_fact_ids"]}
        if len(matches) != 1:
            mismatched.append({**evidence, "differences": ["missing or duplicate published identity"]})
            continue
        group, case = matches[0]
        comparison = row.get("comparison") or {}
        close_available = comparison.get("status") == "available"
        expected_close = {k: price.get(k) for k in ("close", "currency", "session_date")}
        row_checks = {
            "price": per_share > 0 and Decimal(priced["target"]) == per_share and Decimal(case["value"]) == per_share,
            "name": case["name"] == row["name"],
            "period": req["forecast"]["period_start"] == group["period_start"]
                      and req["forecast"]["period_end"] == cap["valuation_date"] == group["period_end"],
            "basis": group["multiple_basis"] == basis + " / revenue (" + period_clock + ")"
                     and group["share_basis"] == "closing common shares"
                     and group["accounting_basis"] == req["forecast"]["basis"] and group["unit"] == priced["unit"],
            "completed_close": (comparison.get("price") == group.get("completed_close") == expected_close
                                if close_available else comparison.get("status") == "unavailable"
                                and group.get("completed_close") is None),
        }
        differences = [field for field, valid in row_checks.items() if not valid]
        if differences:
            mismatched.append({**evidence, "differences": differences})
        else:
            verified.append({**evidence, "completed_close_compared": close_available})
    for _, case in published:
        if (case["case_id"], case["version"]) not in expected_ids:
            mismatched.append({"case_id": case["case_id"], "version": case["version"],
                               "differences": ["unexpected published identity"]})
    checks["positive_sourced_pricing_and_completed_close"] = (
        not mismatched and any(c["completed_close_compared"] for c in verified)
    )
    checks["pm_selection"] = request == (state.get("target_validation") or {}).get("request")
    if selected:
        checks["pm_selection"] &= bool(request and card["basis"] == "valuation"
            and (selected["case_id"], selected["version"]) == (request.get("case_id"), request.get("version")))
        dated = selected.get("decision_date")
        checks["dated_assumption"] = bool(
            (dated and dated == request.get("decision_date") and selected["rerating_assumption"]
             and "assumption, not a forecast" in decision)
            or (not dated and request.get("rerating_assumption", "").strip().casefold() == "none"
                and "no dated assumption supplied" in decision))
    else:
        reason = (pm.get("structured") or {}).get("no_case_reason")
        checks["pm_selection"] &= (request is None and isinstance(reason, str) and bool(reason.strip())
                                   and card["no_case_reason"] != "reason not supplied" and card["basis"] == "risk assessment")
        checks["dated_assumption"] = "assumption, not a forecast:" not in render_condition_summary(card)
    dispositions = prepare_audit_dispositions(state)
    return {"status": "complete" if all(checks.values()) else "incomplete", "checks": checks,
            "verified_cases": verified, "mismatched_cases": mismatched, "revision": saved.get("revision_status", "not observed"),
            "adopted_case": selected, "no_case_reason": card["no_case_reason"], "report_hashes": report_hashes,
            "scenario_reasons": replay["reasons"], "financing": card.get("financing", []), "A1_RPO_caveat_in_shared_brief":
            "does not establish the cause" in str(state.get("shared_source_brief", "")),
            "A2_dispositions": {k:dispositions[k] for k in ("answered_count", "unanswered_count", "rejected_responses")}}


def run(name, cap, credentials):
    candidate = verify_candidate()
    ledger = PilotLedger(LEDGER)
    work = safe(PRIVATE / name)
    if work.exists():
        raise RuntimeError("Prior attempt artifacts exist; no reuse")
    receipt = provider(RECEIPTS / f"{name}.provider.json")
    session = read(RECEIPTS / f"{name}.session.json")
    authority = claim(name, cap, candidate, session, receipt, ledger)
    result = {"execution": "failed", "feature_proof": "incomplete"}
    try:
        work.mkdir(mode=0o700)
        spec = live.CliSpec("DOCN", session["session_date"], B_DEEP, A, 3, 16384,
                            analysis_timezone="America/New_York", analysis_cutoff_utc=live.build2_cutoff(session),
                            proof_scope=live.BUILD2_SCOPE)
        if not credentials.is_absolute() or safe(credentials).stat().st_mode & 0o077:
            raise ValueError("Private credentials file required")
        auth = read(credentials)
        names = ("OPENROUTER_API_KEY", "SEC_EDGAR_USER_AGENT", "FRED_API_KEY", "ALPHA_VANTAGE_API_KEY")
        if any(not isinstance(auth.get(k), str) or not auth[k].strip() for k in names):
            raise ValueError("Missing approved credential")
        budget = LinkedBudget(ledger, Decimal(24), candidate=candidate, allowed_models=MODELS,
                              scope=f"proof:{name}", max_calls=64, allowed_kinds={"run"}, scope_ceiling=money(cap))
        wire = live.OpenRouterWireGuard(budget, receipt["rates"], max_output_tokens=16384, kind="run",
                                        serialize_paid_requests=True, allow_unfrozen_sources=True,
                                        allowed_resolved_models={m:set(v) for m,v in receipt["aliases"].items()})
        verify_candidate()
        for env_key in list(os.environ):
            if env_key.startswith(("LANGCHAIN_", "LANGSMITH_", "OTEL_")) or env_key == "OPENAI_LOG":
                del os.environ[env_key]
        os.environ["LANGSMITH_TRACING"] = "false"
        # Console/library diagnostics can contain private provider URLs. Ledger, state
        # and report are the evidence; never retain raw HTTP/CLI logs or headers.
        with open(os.devnull, "w") as null, redirect_stdout(null), redirect_stderr(null):
            logging.disable(logging.CRITICAL)
            try:
                cli = live.execute_cli(spec, work, wire, None, claim=authority, openrouter_key=auth[names[0]],
                                       sec_user_agent=auth[names[1]], source_credentials={k:auth[k] for k in names[2:]})
            finally:
                logging.disable(logging.NOTSET)
        result["execution"] = "complete"
        create(work / "cli-receipt.json", cli)
        proof = assess(cli["state"], work)
        create(work / "assessment.json", proof)
        result["feature_proof"] = proof["status"]
        result["price_observation_verification"] = cli["price_observation_verification"]
    except BaseException as exc:
        result["error_type"] = type(exc).__name__
        raise
    finally:
        result.update(accounting(ledger, name))
        ledger.append({"type": "attempt_end", "name": name, **result})
        if work.is_dir():
            create(work / "attempt-result.json", result)
    return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--qualify", action="store_true")
    action.add_argument("--freeze", action="store_true")
    action.add_argument("--run", choices=ATTEMPTS)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--attempt-cap")
    args = parser.parse_args()
    if args.run:
        if not (args.credentials and args.attempt_cap):
            parser.error("--run requires explicit --attempt-cap and --credentials")
        try:
            result = run(args.run, args.attempt_cap, args.credentials)
        except Exception as exc:
            # Do not echo arbitrary SDK or vendor exception messages.
            print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "attempt": args.run}))
            return 1
    else:
        if args.credentials or args.attempt_cap:
            parser.error("No credentials or budget outside explicit --run")
        result = freeze() if args.freeze else {"qualification": "offline", "network_calls": 0, **environment()}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
