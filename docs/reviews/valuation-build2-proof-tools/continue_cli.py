"""One authorized continuation of the second DOCN proof's exact native checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import live_cli as h

live = h.live
NAME = live.BUILD2_CONTINUATION
ORIGINAL = h.PRIVATE / h.ATTEMPTS[1]
WORK = h.PRIVATE / NAME
APPLICATION_HEAD = "486586ab94f5a395f80ecc4bc31a6a9a42f14406"
NATIVE_QUALIFICATION_SHA = "0e4439917743e0a64ecfc28d0d594454b661b38a144cf95429f442704e87404a"
APPROVAL_SHA = "6f1c041352f03204fff7ec25aba37029cfb21bac793e33bdf5819689c4cad0e0"
PREFIX_BYTES = 65407
PREFIX_SHA = "abb1f1170b0bc74cb32ac17dfe1968aca97c0fbf5d739d63dae6a3494832e65e"
SECOND_SHA = "dcb0a3f7dfc4fc275e5eb940093e2f601bc63af70273b382ae6f86a40ca11163"
INPUT_SHA = "2a7494503539a196311bae2633ba7332dce884087eceff6981890a3b0afee0c7"
THREAD = "37bef10be0404049"
CHECKPOINT = "1f1da76d-ce97-670a-800c-324363d6c577"
RUN_ID = "b7e2f75f-98c8-48b2-a09f-633c88319c44"
RISK = ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst") * 3
AUDIT = "Advisory Audit"
PM = "Portfolio Manager"


def prior_prefix(ledger, *, unused):
    if h.safe(ledger.path) != h.LEDGER:
        raise ValueError("Original Build2 ledger required")
    raw = ledger.path.read_bytes()
    prefix = raw[:PREFIX_BYTES]
    if hashlib.sha256(prefix).hexdigest() != PREFIX_SHA or unused and len(raw) != PREFIX_BYTES:
        raise ValueError("Original two-attempt ledger changed or continuation already consumed")
    events = [json.loads(line) for line in prefix.splitlines()]
    if [e["phase"] for e in events if e["type"] == "attempt_claim"] != list(h.ATTEMPTS) or (
        events[-1]["type"],
        events[-1]["name"],
        events[-1]["execution"],
        events[-1]["error_type"],
    ) != ("attempt_end", h.ATTEMPTS[1], "failed", "BudgetStoppedError"):
        raise ValueError("Expected terminal second attempt missing")
    return next(e for e in events if e.get("phase") == h.ATTEMPTS[1])


def input_hashes(root):
    paths = [root / "cli_prefs.json"]
    for folder in ("cache", "memory"):
        for path in (root / folder).rglob("*"):
            h.safe(path)
            if path.is_file():
                if path.name.endswith("-wal") and path.stat().st_size:
                    raise ValueError(
                        "Uncheckpointed SQLite WAL; snapshot is not the approved input"
                    )
                if not path.name.endswith(("-shm", "-wal")):
                    paths.append(path)
    result = {str(path.relative_to(root)): h.sha(path) for path in paths}
    if h.manifest_hash(result) != INPUT_SHA:
        raise ValueError("Checkpoint, CLI preferences or retained source cache changed")
    return result


def qualification():
    prior = prior_prefix(h.PilotLedger(h.LEDGER), unused=True)
    if h.sha(h.PRIVATE / "build2-second-candidate.json") != SECOND_SHA:
        raise ValueError("Original second candidate changed")
    if h.sha(h.PRIVATE / "build2-continuation-user-approval.json") != APPROVAL_SHA:
        raise ValueError("Explicit continuation approval receipt differs")
    original = h.read(h.PRIVATE / "build2-second-candidate.json")
    native = h.ROOT / "evidence/continuation-native-offline.json"
    if h.sha(native) != NATIVE_QUALIFICATION_SHA or h.read(native)["status"] != "passed":
        raise ValueError("Native checkpoint qualification differs")
    if h.sha(h.FROZEN) != original["second_slot"]["original_candidate_sha256"]:
        raise ValueError("Original first candidate receipt changed")
    env = h.environment()
    if (
        prior["approval_record"] != original
        or original["candidate_head"] != APPLICATION_HEAD
        or any(
            env[k] != original[k]
            for k in (
                "config",
                "machine",
                "old_ledgers",
                "inputs",
                "worktree_root",
                "repository_origin",
                "setup_sha256",
                "interpreter",
                "python_version",
                "module_origins",
                "dependency_manifest_sha256",
                "prior_unknown_reserved_usd",
                "prior_committed_exposure_usd",
            )
        )
    ):
        raise ValueError(
            "Original model, application, historical holds or runtime constraints changed"
        )
    subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            APPLICATION_HEAD,
            "HEAD",
            "--",
            "cli",
            "tradingagents",
            "requirements.txt",
            "pyproject.toml",
        ],
        cwd=h.WT,
        check=True,
    )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", APPLICATION_HEAD, "HEAD"], cwd=h.WT, check=True
    )
    return {
        **env,
        "runtime_inputs": input_hashes(ORIGINAL),
        "continuation_runner_sha256": h.sha(Path(__file__).resolve()),
        "second_candidate_sha256": SECOND_SHA,
        "terminal_ledger_sha256": PREFIX_SHA,
        "user_approval_sha256": APPROVAL_SHA,
        "saved_session": prior["session"],
        "thread": THREAD,
        "checkpoint_id": CHECKPOINT,
        "application_head": APPLICATION_HEAD,
        "native_qualification_sha256": NATIVE_QUALIFICATION_SHA,
    }


def claim(ledger, candidate, reviewed_head, receipt):
    if not candidate["clean"] or candidate["candidate_head"] != reviewed_head:
        raise ValueError("Explicit clean reviewed continuation HEAD required")
    now = datetime.now(UTC)
    observed = live._b3_aware_time(receipt["observed_at"], now)
    if observed < now - timedelta(minutes=10):
        raise ValueError("Fresh continuation provider receipt required")
    with ledger.budget_lock():
        prior = prior_prefix(ledger, unused=True)
        original = prior["approval_record"]
        if (
            candidate.get("user_approval_sha256") != APPROVAL_SHA
            or candidate.get("native_qualification_sha256") != NATIVE_QUALIFICATION_SHA
            or candidate.get("checkpoint_id") != CHECKPOINT
            or candidate.get("thread") != THREAD
            or candidate.get("application_head") != APPLICATION_HEAD
            or candidate.get("config") != h.CONFIG
            or any(
                candidate.get(k) != original[k]
                for k in (
                    "old_ledgers",
                    "prior_committed_exposure_usd",
                    "prior_unknown_reserved_usd",
                )
            )
        ):
            raise ValueError("Continuation receipt or preserved authority differs")
        previous = prior["provider_receipt"]
        if (
            observed <= datetime.fromisoformat(previous["observed_at"])
            or receipt["aliases"] != previous["aliases"]
            or any(
                h.money(receipt["rates"][m][k]) > h.money(v)
                for m in h.MODELS
                for k, v in previous["rates"][m].items()
            )
        ):
            raise ValueError("Fresh continuation receipt exceeds prior price/alias envelope")
        committed = ledger.committed_usd()
        outstanding = sum(map(h.money, h.holds(ledger).values()), Decimal(0))
        if committed + 12 > 36 or h.money(receipt["remaining_usd"]) < 12 + outstanding + h.money(
            candidate["prior_unknown_reserved_usd"]
        ):
            raise ValueError(
                "Insufficient aggregate authority or account headroom after unknown holds"
            )
        digest = h.manifest_hash(candidate)
        ledger.append(
            {
                "type": "continuation_claim",
                "name": NAME,
                "approval_sha256": digest,
                "user_approval_sha256": APPROVAL_SHA,
                "candidate": candidate,
                "provider_receipt": receipt,
                "ceiling_usd": "36",
                "scope_ceiling_usd": "12",
                "previous_committed_usd": str(committed),
                "previous_unknown_usd": str(outstanding),
                "terminal_prefix_bytes": PREFIX_BYTES,
                "terminal_prefix_sha256": PREFIX_SHA,
            }
        )
    return live.ExecutionClaim("continuation", NAME, digest)


class ContinuationBudget(h.LinkedBudget):
    def __init__(self, ledger, candidate, receipt, authority):
        self.authority = authority
        self.receipt = receipt
        super().__init__(
            ledger,
            Decimal(36),
            candidate=candidate,
            allowed_models=h.MODELS,
            allowed_kinds={"run"},
            scope="proof:" + NAME,
            scope_ceiling=Decimal(12),
            max_calls=13,
        )

    def reserve(self, *args, **kwargs):
        prior_prefix(self.ledger, unused=False)
        events = self.ledger.events()
        claims = [e for e in events if e["type"] == "continuation_claim"]
        if (
            len(claims) != 1
            or claims[0].get("name") != NAME
            or claims[0]["approval_sha256"] != self.authority.approval_sha256
            or self.authority
            != live.ExecutionClaim("continuation", NAME, h.manifest_hash(self.candidate))
            or claims[0]["candidate"] != self.candidate
            or claims[0]["provider_receipt"] != self.receipt
            or claims[0]["user_approval_sha256"] != APPROVAL_SHA
            or any(e["type"] == "continuation_end" for e in events)
        ):
            raise RuntimeError("Continuation budget is not bound to an open authorized claim")
        return super().reserve(*args, **kwargs)


class ContinuationWire(live.OpenRouterWireGuard):
    def __init__(self, budget, receipt):
        super().__init__(
            budget,
            receipt["rates"],
            max_output_tokens=16384,
            kind="run",
            serialize_paid_requests=True,
            network_gate=live.NetworkGate(),
            allowed_resolved_models={m: set(v) for m, v in receipt["aliases"].items()},
        )
        self.roles = []
        self.checkpoint_verified = False

    def before(self, request):
        if request.url.host != "openrouter.ai":
            self.stopped = True
            self.network_gate.record_violation("source_http")
            raise RuntimeError("No source HTTP during native checkpoint continuation")
        from langgraph.config import get_config

        node = (get_config().get("metadata") or {}).get("langgraph_node")
        i = len(self.roles)
        if i < len(RISK):
            permitted = (RISK[i],)
        elif i == len(RISK):
            permitted = (AUDIT,)
        else:
            # From the existing application, one bounded audit retry and one
            # free-text PM fallback are possible on the original model tiers.
            if self.roles[-1] == AUDIT:
                permitted = (AUDIT, PM) if self.roles.count(AUDIT) == 1 else (PM,)
            else:
                permitted = (PM,) if self.roles.count(PM) == 1 else ()
        if (
            not self.checkpoint_verified
            or node not in permitted
            or json.loads(request.content).get("model") != (h.B_DEEP if node in RISK else h.A)
        ):
            self.stopped = True
            raise RuntimeError("Model send outside verified continuation role or order")
        ticket = super().before(request)
        self.roles.append(node)
        self.budget.ledger.append({"type": "continuation_role", "ticket": ticket, "node": node})
        return ticket


def _retained(value):
    """A saved record without the fields derived again from retained evidence on every replay.

    The 2026-11-10 decision-basis build replaced the blanket funding warning on each
    revenue case with a computed status and added each case's position against the
    company's own valuation history. Everything else must still match exactly.
    """
    if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
        return value
    rows = []
    for row in value["rows"]:
        if isinstance(row, dict) and isinstance(row.get("result"), dict):
            result = dict(row["result"])
            result["warnings"] = [w for w in result.get("warnings") or [] if not str(w).startswith("Funding ")]
            row = {k: v for k, v in row.items() if k not in {"funding", "reference_position"}} | {"result": result}
        rows.append(row)
    return {**{k: v for k, v in value.items() if k != "reference_history"}, "rows": rows}


def verify_snapshot(snapshot, thread):
    state = snapshot.values
    if (
        thread != THREAD
        or snapshot.next != (RISK[0],)
        or snapshot.metadata.get("step") != 12
        or snapshot.config["configurable"]["checkpoint_id"] != CHECKPOINT
        or state.get("run_id") != RUN_ID
        or state.get("company_of_interest") != "DOCN"
        or state.get("trade_date") != "2026-11-06"
        or state["investment_debate_state"]["count"] != 6
        or state["risk_debate_state"]["count"] != 0
        or not state.get("trader_investment_plan")
        or Decimal(str(state["price_observation"]["close"])) != Decimal("72.4800033569336")
    ):
        raise RuntimeError("Native checkpoint does not identify the approved post-trader state")
    return state


def run_graph(work, spec, wire, session):
    from cli.run import _build_run_config
    from cli.stats_handler import StatsCallbackHandler
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    live.fresh_default_config()
    prefs = h.read(work / "cli_prefs.json")
    config = _build_run_config(prefs, checkpoint=True)
    live.verify_cli_config(config, spec)
    observer = StatsCallbackHandler()
    with (
        live.installed_network_gate(wire.network_gate),
        live.installed_http_guard(wire),
        live.one_document_audit_attempt(spec),
    ):
        graph = TradingAgentsGraph(
            prefs["analysts"], config=config, debug=True, callbacks=[observer]
        )
        # Match CLI observer initialization while leaving the retained graph state intact.
        graph._initial_run_metrics()
        try:
            thread = graph.begin_checkpoint("DOCN", spec.analysis_date, "stock", None)
            args = graph.propagator.get_graph_args(callbacks=[observer])
            args["config"]["configurable"] = {"thread_id": thread}
            snapshot = graph.graph.get_state(args["config"])
            saved = verify_snapshot(snapshot, thread)
            prior_calls = saved["run_metrics"]["model_calls"]
            if graph.checkpoint_input({}) is not None:
                raise RuntimeError("Native graph would start fresh")
            wire.checkpoint_verified = True
            for _ in graph.stream_run(None, **args):
                pass
            wire.checkpoint_verified = False
            complete = graph.graph.get_state(args["config"])
            final = dict(complete.values)
            metrics = final["run_metrics"]
            if (
                complete.next
                or wire.roles
                not in [list(RISK) + n * [AUDIT] + m * [PM] for n in (1, 2) for m in (1, 2)]
                or metrics["model_calls"] != prior_calls + wire.request_count
                or (metrics["research_rounds_completed"], metrics["risk_rounds_completed"])
                != (3, 3)
                or metrics["model_call_scope"] != "partial_observed"
                or any(
                    _retained(final[k]) != _retained(saved[k])
                    for k in (
                        "run_id",
                        "analysis_clock",
                        "market_observation_cutoff",
                        "price_observation",
                        "shared_valuation_scenarios",
                        "financial_evidence",
                        "document_search_trace",
                        "shared_source_brief",
                        "issuer_identity",
                        "filing_evidence",
                        "document_sources",
                        "transcript_sources",
                    )
                )
                or any(
                    final["unvalidated_outputs"].get(k) != saved[k]
                    for k in (
                        "market_report",
                        "sentiment_report",
                        "news_report",
                        "fundamentals_report",
                        "investment_debate_state",
                        "investment_plan",
                        "trader_investment_plan",
                    )
                )
                or wire.network_gate.violations
            ):
                raise RuntimeError(
                    "Continuation role, retained inputs, native completion or accounting differs"
                )
            price = live.verify_document_access_completed_state(final, spec, {"session": session})
            graph.record_decision("DOCN", spec.analysis_date, final)
            report = graph.save_reports(final, "DOCN", html=True)
            if not report.is_file() or wire.network_gate.violations:
                raise RuntimeError("Private proof report unavailable or unexpected source request")
            state_path = (
                work / "results/DOCN/TradingAgentsStrategy_logs/full_states_log_2026-11-06.json"
            )
            return {
                "state": h.read(state_path),
                "price_observation_verification": price,
                "roles": wire.roles,
                "graph_checkpoint_model_call_baseline": prior_calls,
                "graph_model_calls": metrics["model_calls"],
                "graph_model_call_scope": metrics["model_call_scope"],
            }
        finally:
            graph.end_checkpoint()


def verify_launch_head(expected):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=h.WT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=h.WT)
    if head != expected or dirty:
        raise RuntimeError("Continuation candidate changed after claim")


def run(reviewed_head, credentials):
    candidate = qualification()
    if h.safe(WORK).exists():
        raise RuntimeError("Continuation already has a work directory")
    receipt = h.provider(h.RECEIPTS / (NAME + ".provider.json"))
    ledger = h.PilotLedger(h.LEDGER)
    authority = claim(ledger, candidate, reviewed_head, receipt)
    result = {"execution": "failed", "feature_proof": "incomplete"}
    try:
        WORK.mkdir(mode=0o700)
        for filename, digest in candidate["runtime_inputs"].items():
            target = h.safe(WORK / filename)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(h.safe(ORIGINAL / filename), target)
            if h.sha(target) != digest:
                raise ValueError("Copied continuation input differs")
        (WORK / "memory").mkdir(mode=0o700, exist_ok=True)
        input_hashes(WORK)
        if h.safe(credentials).stat().st_mode & 0o077:
            raise ValueError("Private credential permissions required")
        key = h.read(credentials).get("OPENROUTER_API_KEY")
        session = candidate["saved_session"]
        spec = live.CliSpec(
            "DOCN",
            session["session_date"],
            h.B_DEEP,
            h.A,
            3,
            16384,
            analysis_timezone="America/New_York",
            analysis_cutoff_utc=live.build2_cutoff(session),
            proof_scope=live.BUILD2_SCOPE,
        )
        for k in list(os.environ):
            if k.startswith(("LANGCHAIN_", "LANGSMITH_", "OTEL_")) or k == "OPENAI_LOG":
                del os.environ[k]
        os.environ["LANGSMITH_TRACING"] = "false"
        live.configure_isolated_env(
            spec, WORK, openrouter_key=key, sec_user_agent="", claim=authority
        )
        budget = ContinuationBudget(ledger, candidate, receipt, authority)
        verify_launch_head(candidate["candidate_head"])
        wire = ContinuationWire(budget, receipt)
        old = Path.cwd()
        try:
            os.chdir(WORK)
            with open(os.devnull, "w") as null, redirect_stdout(null), redirect_stderr(null):
                logging.disable(logging.CRITICAL)
                try:
                    cli = run_graph(WORK, spec, wire, session)
                finally:
                    logging.disable(logging.NOTSET)
        finally:
            os.chdir(old)
        result["execution"] = "complete"
        h.create(WORK / "cli-receipt.json", cli)
        assessment = h.assess(cli["state"], WORK)
        h.create(WORK / "assessment.json", assessment)
        result["feature_proof"] = assessment["status"]
    except BaseException as exc:
        result["error_type"] = type(exc).__name__
        raise
    finally:
        result.update(h.accounting(ledger, NAME))
        ledger.append({"type": "continuation_end", "name": NAME, **result})
        if WORK.is_dir():
            h.create(WORK / "continuation-result.json", result)
    return result


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    op = p.add_mutually_exclusive_group()
    op.add_argument("--qualify", action="store_true")
    op.add_argument("--run", action="store_true")
    p.add_argument("--candidate")
    p.add_argument("--credentials", type=Path)
    args = p.parse_args()
    if args.run:
        if not args.candidate or not args.credentials:
            p.error("Explicit candidate and credentials required")
        try:
            result = run(args.candidate, args.credentials)
        except Exception as exc:
            print(json.dumps({"execution": "failed", "error_type": type(exc).__name__}))
            return 1
    else:
        if args.credentials or args.candidate:
            p.error("Offline qualification requires no credentials or candidate argument")
        result = qualification()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
