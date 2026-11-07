"""Offline-qualified, fresh-authority document-access live proof harness.

Default and --qualify perform local reads only. --run is a separately approved
one-ticker attempt. Each failed start consumes its claim; there is no resume.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
ROOT = Path("/Users/zipp/Developer/tradingagents-document-access-20261106")
WT = ROOT / "build-a"
PRIVATE = ROOT / "private"
PRIOR = Path("/Users/zipp/Developer/tradingagents-valuation-range-20261106/private")
PRIOR_LEDGERS = (
    PRIOR / "run-fixes-proof-ledger.jsonl",
    PRIOR / "run-fixes-build1-attempt2-proof-ledger.jsonl",
    PRIOR / "run-fixes-build1-attempt3-proof-ledger.jsonl",
)
APPROVAL = PRIVATE / "document-access-proof-approval.json"
CANDIDATE = PRIVATE / "document-access-proof-candidate.json"
LEDGER = PRIVATE / "document-access-proof-ledger.jsonl"
RUNTIME = PRIVATE / "document-access-live"
sys.path[:0] = [str(WT), str(WT / "docs/reviews/valuation-reference-proof-tools")]

import live_adapter  # noqa: E402
from pilot import B_DEEP, A, BudgetGuard, PilotLedger  # noqa: E402

TICKERS = live_adapter.DOCUMENT_PROOF_TICKERS
MODEL_IDS = {A, B_DEEP}
ANALYSTS = ["market", "social", "news", "fundamentals"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Missing or unsafe local input: {path}")
    result = json.loads(path.read_text())
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return result


def git(*args) -> str:
    return subprocess.check_output(["git", *args], cwd=WT, text=True).strip()


def assert_environment() -> dict:
    live_adapter._verify_run_fixes_machine()
    interpreter = Path(os.path.abspath(sys.executable))
    if not interpreter.is_relative_to(WT / ".venv"):
        raise RuntimeError("Use the task-local build-a interpreter on M1")
    modules = {}
    for name in ("tradingagents", "cli.main", "tradingagents.graph.trading_graph",
                 "tradingagents.agents.document_access",
                 "tradingagents.agents.evidence_validation",
                 "tradingagents.graph.setup",
                 "tradingagents.dataflows.filing_search",
                 "tradingagents.dataflows.vendors.sec_documents",
                 "live_adapter", "pilot"):
        path = Path(importlib.import_module(name).__file__).resolve()
        if not path.is_relative_to(WT.resolve()):
            raise RuntimeError(f"Imported module {name} differs from build-a")
        modules[name] = {"path": str(path), "sha256": sha(path)}
    if Path(git("rev-parse", "--show-toplevel")).resolve() != WT.resolve():
        raise RuntimeError("Git root differs from build-a")
    return {
        "interpreter": str(interpreter), "modules": modules,
        "branch": git("branch", "--show-current"), "head": git("rev-parse", "HEAD"),
        "origin": git("remote", "get-url", "origin"),
        "clean": not bool(git("status", "--porcelain")),
        "machine": {"cpu": "Apple M1 Pro", "ram_bytes": 17179869184},
    }


def prior_ledger_snapshot() -> dict:
    hashes = {}
    exposure = Decimal(0)
    unknown = Decimal(0)
    for path in PRIOR_LEDGERS:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Prior proof ledger missing or unsafe: {path}")
        hashes[str(path)] = sha(path)
        ledger = PilotLedger(path)
        events = ledger.events()
        settled = {event["ticket"] for event in events if event.get("type") == "settle"}
        exposure += ledger.committed_usd()
        unknown += sum((Decimal(event["usd"]) for event in events
                        if event.get("type") == "reserve" and event["ticket"] not in settled), Decimal(0))
    return {
        "old_ledgers": hashes,
        "prior_committed_exposure_usd": str(exposure),
        "prior_unknown_reserved_usd": str(unknown),
        "authority": "Historical exposure linked only; no historical headroom is reused.",
    }


def prior_wire_sample() -> dict:
    """Historical depth-one body sizes only; not a depth-three cost promise."""
    events = PilotLedger(PRIOR_LEDGERS[-1]).events()
    requests = [event for event in events if event.get("type") == "request_meta"]
    settled = [event for event in events if event.get("type") == "settle"]
    return {
        "source": str(PRIOR_LEDGERS[-1]), "source_sha256": sha(PRIOR_LEDGERS[-1]),
        "depth": 1, "requests": len(requests),
        "serialized_body_bytes": sum(event["body_bytes"] for event in requests),
        "max_body_bytes": max((event["body_bytes"] for event in requests), default=0),
        "max_input_bound_tokens": max((event["input_bound_tokens"] for event in requests), default=0),
        "settled_usd": str(sum((Decimal(event["usd"]) for event in settled), Decimal(0))),
        "limit": "Historical depth-one workload; new depth-three requests and fresh endpoint rates are unknown.",
    }


def qualification() -> dict:
    environment = assert_environment()
    old = prior_ledger_snapshot()
    return {
        "label": "Offline qualification only; no live source, model, account, or rate observation",
        "paid_calls": 0, "source_calls": 0, "attempt_claimed": False,
        "environment": environment, "prior": old, "prior_wire_sample": prior_wire_sample(),
        "proposal": {
            "tickers": list(TICKERS), "attempts": 3, "one_attempt_per_ticker": True,
            "analysis_date": "Must be fixed by fresh approval after completed session",
            "quick_model": B_DEEP, "deep_model": A, "depth": 3,
            "analysts": ANALYSTS, "max_tool_rounds": 4,
            "max_output_tokens": 16384, "llm_max_retries": 0,
            "audit_max_attempts": 2, "automatic_retry": False,
            "ceiling_usd": "Requires measured conservative envelope and fresh user approval",
            "max_calls_per_attempt": "Requires measured envelope and fresh user approval",
        },
        "ready_for_paid_run": False,
        "remaining_gates": [
            "Clean committed candidate and exact module origins",
            "Fresh account/endpoint model ID and conservative route-rate receipt",
            "Conservative three-attempt cost envelope reviewed by root",
            "Fresh user approval bound to exact candidate, runner, prior ledgers and budget",
            "Per-ticker completed-session receipt and credentials supplied only after approval",
        ],
    }


def _candidate_and_approval(ticker: str) -> tuple[dict, dict]:
    environment = assert_environment()
    if environment["branch"] != "codex/document-access-b" or not environment["clean"]:
        raise RuntimeError("Document proof needs a clean committed B candidate")
    candidate = read_json(CANDIDATE)
    approval = read_json(APPROVAL)
    live_adapter._validate_document_access_approval(approval)
    if (approval["candidate_sha256"] != sha(CANDIDATE)
            or candidate.get("runner_sha256") != sha(Path(__file__))
            or approval["runner_sha256"] != sha(Path(__file__))
            or candidate.get("head") != environment["head"]
            or approval["candidate_head"] != environment["head"]
            or approval["worktree_root"] != str(WT)
            or approval["ledger_path"] != str(LEDGER)
            or approval["receipt_root"] != str(PRIVATE / "document-access-receipts")
            or approval["repository_origin"] != environment["origin"]
            or candidate.get("module_hashes") != {
                name: item["sha256"] for name, item in environment["modules"].items()
            }):
        raise RuntimeError("Fresh approval/candidate/source hash binding differs")
    prior = prior_ledger_snapshot()
    for name in ("old_ledgers", "prior_committed_exposure_usd", "prior_unknown_reserved_usd"):
        if approval[name] != prior[name] or candidate.get(name) != prior[name]:
            raise RuntimeError("Prior ledger or unknown hold changed")
    metadata_path = Path(candidate.get("provider_metadata_path", ""))
    metadata = read_json(metadata_path)
    if (sha(metadata_path) != candidate.get("provider_metadata_sha256")
            or approval["provider_metadata_sha256"] != sha(metadata_path)):
        raise RuntimeError("Fresh provider metadata bytes differ")
    rates = live_adapter.conservative_route_rates(metadata, MODEL_IDS)
    aliases = live_adapter.resolved_model_ids(metadata, MODEL_IDS)
    if (rates != candidate.get("reviewed_route_rates")
            or rates != approval["approved_route_rate_caps"]
            or {name: sorted(ids) for name, ids in aliases.items()} != candidate.get("resolved_model_ids")
            or candidate.get("resolved_model_ids") != approval["resolved_model_ids"]):
        raise RuntimeError("Provider models or conservative rates differ from reviewed candidate")
    if approval["analysis_date"] != candidate.get("analysis_date") or ticker not in TICKERS:
        raise RuntimeError("Ticker or analysis date differs from approved candidate")
    return approval, candidate


def _write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


class DocumentBudgetGuard(BudgetGuard):
    """Recheck linked historical holds before every paid reservation."""
    def __init__(self, *args, approval_record: dict, **kwargs):
        self.approval_record = approval_record
        super().__init__(*args, **kwargs)

    def reserve(self, *args, **kwargs):
        live_adapter._document_access_prior_exposure(self.approval_record)
        return super().reserve(*args, **kwargs)


def assess_document_feature_proof(state: dict, work: Path, ticker: str) -> dict:
    """Check observed feature evidence; missing observations are proof-incomplete."""
    from tradingagents.agents.audit_evidence import _validated_rows
    from tradingagents.agents.document_access import (
        retained_search_packages,
        validated_document_corpus,
    )
    from tradingagents.agents.document_questions import (
        lookup_document_questions,
        render_document_followups,
    )
    from tradingagents.agents.transcript_access import validated_transcript_record

    checks = {}
    hashes = {}
    def result(name, passed, detail):
        checks[name] = {"status": "pass" if passed else "missing", "detail": detail}

    corpus = None
    try:
        corpus = validated_document_corpus(state)
        docs = corpus.documents if corpus else ()
        selected = set(corpus.selected_accessions) if corpus else set()
        represented = {doc.filing.accession for doc in docs}
        complete = bool(docs) and bool(selected) and selected <= represented and all(
            doc.blocks and not any(block.truncated for block in doc.blocks) for doc in docs
        )
        gap_text = " ".join(corpus.gaps).lower() if corpus else ""
        complete = complete and not any(
            marker in gap_text for marker in ("byte limit", "document count limit", "full source extraction limit")
        )
        result("full_filing_corpus", complete,
               f"{len(docs)} documents; {len(selected)} selected accessions; {len(corpus.gaps) if corpus else 0} gaps")
        if corpus:
            hashes["document_corpus"] = (state.get("document_sources") or {}).get("corpus_hash")
    except (ValueError, TypeError, KeyError) as exc:
        result("full_filing_corpus", False, type(exc).__name__)

    try:
        packages = retained_search_packages(state)
        trace = state.get("document_search_trace") or {}
        hits = {
            entry.get("role") for entry in trace.values()
            if isinstance(entry, dict) and entry.get("status") == "ok" and entry.get("passages")
        }
        filing_hits = sum(len(package.documents) for package in packages)
        result("analyst_passage_delivery", bool(packages) and {"fundamentals", "news"} <= hits,
               f"{filing_hits} retained package documents; roles {sorted(hits)}")
        hashes["search_passages"] = sorted(
            p["passage_hash"] for entry in trace.values() if isinstance(entry, dict)
            for p in entry.get("passages", []) if isinstance(p, dict) and p.get("passage_hash")
        )
    except (ValueError, TypeError, KeyError) as exc:
        result("analyst_passage_delivery", False, type(exc).__name__)

    positive_transcript_observed = False
    unavailable_transcript_reason = ""
    try:
        transcript = validated_transcript_record(state)
        positive_transcript_observed = transcript is not None
        wrapper = state.get("transcript_sources") or {}
        if transcript:
            result("dated_transcript_or_continuation", True, "SEC date and vendor source verified")
            hashes["transcript_source"] = wrapper["source_hash"]
            hashes["transcript_date_pin"] = wrapper["date_evidence"]["content_hash"]
        elif (ticker in {"MSFT", "CAT"} and wrapper.get("status") == "unavailable"
              and isinstance(wrapper.get("reason"), str) and wrapper["reason"].strip()):
            unavailable_transcript_reason = wrapper["reason"]
            result("dated_transcript_or_continuation", False,
                   "Explicit unavailability must appear in the report")
        else:
            result("dated_transcript_or_continuation", False, "Dated transcript not observed")
    except (ValueError, TypeError, KeyError) as exc:
        result("dated_transcript_or_continuation", False, type(exc).__name__)

    try:
        followups = state.get("document_followups")
        if followups:
            lookup_document_questions(state)  # revalidate exact retained answers
        rows = followups.get("results", []) if isinstance(followups, dict) else []
        found = [row for row in rows if row.get("status") == "found" and row.get("passages")]
        result("debate_followups", bool(rows) and bool(found),
               f"{len(rows)} questions; {len(found)} with retained passages")
        if followups:
            hashes["followup_record"] = followups.get("record_hash")
    except (ValueError, TypeError, KeyError) as exc:
        result("debate_followups", False, type(exc).__name__)

    macro_rows = _validated_rows(state, "news", "audit_news_tool_evidence")
    macros = [row for row in macro_rows if row.get("tool_name") == "get_macro_indicators"]
    dated = [row for row in macros if row.get("status") == "success"
             and not row.get("truncated")
             and row.get("excerpt", "").startswith("## FRED:")
             and "- Window:" in row.get("excerpt", "")
             and f" to {state.get('trade_date')}" in row.get("excerpt", "")
             and "**Latest:**" in row.get("excerpt", "")
             and "DATA_UNAVAILABLE:" not in row.get("excerpt", "")
             and "No observations" not in row.get("excerpt", "")]
    gaps = [row for row in macros if "DATA_UNAVAILABLE:" in row.get("excerpt", "")
            or "No observations" in row.get("excerpt", "")]
    positive_macro_observed = bool(dated)
    result("dated_macro_or_gap", positive_macro_observed or ticker in {"MSFT", "CAT"} and bool(gaps),
           f"{len(dated)} dated values; {len(gaps)} explicit gaps; {len(macros)} calls")
    hashes["macro_outputs"] = [row["output_sha256"] for row in macros]

    report_root = work / "results" / "reports"
    reports = list(report_root.glob(f"{ticker}_*/complete_report.md")) if report_root.is_dir() else []
    summary_text = ""
    if len(reports) == 1:
        root = reports[0].parent
        files = [root / "complete_report.md", root / "5_portfolio" / "decision.md",
                 root / "6_evidence" / "summary.md", root / "evidence.json"]
        if all(path.is_file() and not path.is_symlink() for path in files):
            hashes["report_files"] = {str(path.relative_to(work)): sha(path) for path in files}
            decision = files[1].read_text()
            summary = files[2].read_text()
            summary_text = summary
            from tradingagents.reporting import prepare_report_state

            prepared = prepare_report_state(state)
            rendered = (render_document_followups(prepared, prepared.get("final_trade_decision", ""))
                        if prepared.get("document_followups") else "")
            report_ok = bool(rendered) and rendered in decision and "Document searches" in summary
            result("rendered_report", report_ok,
                   "decision follow-ups and evidence search summary present" if report_ok else
                   "follow-up or search result absent from rendered report")
        else:
            result("rendered_report", False, "required report artifact missing")
    else:
        result("rendered_report", False, f"{len(reports)} complete reports found")

    if unavailable_transcript_reason:
        continued = (unavailable_transcript_reason in summary_text
                     and bool(str(state.get("final_trade_decision") or "").strip()))
        result("dated_transcript_or_continuation", continued,
               "Explicit unavailable reason rendered and final decision reached" if continued
               else "Unavailable reason absent from report or final decision missing")

    state_log = work / "results" / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{state.get('trade_date')}.json"
    persisted = False
    if state_log.is_file() and not state_log.is_symlink():
        try:
            saved = read_json(state_log)
            fields = (
                "company_of_interest", "trade_date", "analysis_clock", "issuer_identity",
                "document_sources", "document_search_trace", "transcript_sources",
                "document_followups", "audit_news_tool_evidence",
                "price_observation", "final_trade_decision",
            )
            persisted = all(key in saved and saved[key] == state.get(key) for key in fields)
            debate = saved.get("investment_debate_state") or {}
            actual_debate = state.get("investment_debate_state") or {}
            retained_debate_fields = (
                "document_questions", "count", "bull_history", "bear_history",
                "history", "current_response",
            )
            persisted = persisted and bool(debate.get("document_questions")) and all(
                key not in actual_debate or debate.get(key) == actual_debate[key]
                for key in retained_debate_fields
            )
            if persisted:
                hashes["saved_state"] = sha(state_log)
        except (ValueError, TypeError, KeyError):
            persisted = False
    result("saved_state", persisted,
           "run scope, sources, questions and decision persisted" if persisted
           else "saved scope, sources, questions or decision missing")
    return {
        "status": "complete" if checks and all(item["status"] == "pass" for item in checks.values()) else "incomplete",
        "checks": checks, "source_and_report_hashes": hashes,
        "positive_transcript_observed": positive_transcript_observed,
        "positive_macro_observed": positive_macro_observed,
        "missing_live_observations": ( ([] if positive_transcript_observed else ["vendor_transcript"])
                                       + ([] if positive_macro_observed else ["dated_macro_value"]) ),
        "interpretation": "Observed source delivery only; model claims remain subject to canonical evidence checks.",
    }



def run(ticker: str, credentials_path: Path) -> dict:
    approval, candidate = _candidate_and_approval(ticker)
    work = RUNTIME / ticker
    job = PRIVATE / f"document-access-proof-{ticker}.job.json"
    if RUNTIME.is_symlink() or work.is_symlink() or job.is_symlink():
        raise RuntimeError("Unsafe proof runtime or job path")
    if work.exists() or job.exists() or any(
        event.get("type") == "attempt_claim" and event.get("ticker") == ticker
        for event in PilotLedger(LEDGER).events()
    ):
        raise RuntimeError("Ticker attempt already has artifacts; no automatic retry or resume")
    if credentials_path.is_symlink() or credentials_path.stat().st_mode & 0o077:
        raise RuntimeError("Credential file permissions are unsafe")
    auth = read_json(credentials_path)
    if not all(auth.get(name) for name in ("OPENROUTER_API_KEY", "SEC_EDGAR_USER_AGENT", "FRED_API_KEY", "ALPHA_VANTAGE_API_KEY")):
        raise RuntimeError("Approved credentials unavailable")
    spec = live_adapter.CliSpec(
        ticker, approval["analysis_date"], B_DEEP, A, 3, 16384,
        max_tool_rounds=4, proof_scope=live_adapter.DOCUMENT_PROOF_SCOPE,
    )
    # Claim before source/model activity. A failed start remains a consumed attempt.
    ledger = PilotLedger(LEDGER)
    digest = live_adapter.claim_document_access_proof(ledger, approval, ticker)
    record = {"status": "starting", "ticker": ticker,
              "started_at": datetime.now(UTC).isoformat(), "approval_sha256": digest}
    try:
        record.update(
            candidate_sha256=sha(CANDIDATE), runner_sha256=sha(Path(__file__)),
            candidate=candidate, spec=dataclasses.asdict(spec), workdir=str(work),
            ledger=str(LEDGER), automatic_retry=False,
        )
        claim = live_adapter.ExecutionClaim("proof", live_adapter.DOCUMENT_PROOF_PREFIX + ticker, digest)
        receipt_event = next(event for event in reversed(ledger.events())
                             if event.get("type") == "provider_receipt" and event.get("ticker") == ticker)
        if sha(Path(receipt_event["path"])) != receipt_event["sha256"]:
            raise RuntimeError("Claimed per-attempt provider receipt changed")
        rates = receipt_event["rates"]
        aliases = {model: set(values) for model, values in receipt_event["resolved_model_ids"].items()}
        record["provider_receipt_sha256"] = receipt_event["sha256"]
        budget = DocumentBudgetGuard(
            ledger, Decimal(approval["ceiling_usd"]), approval_record=approval, allowed_models=MODEL_IDS,
            max_calls=approval["max_calls_per_attempt"],
            scope=f"proof:DocumentAccess:{ticker}", allowed_kinds={"run"},
            scope_ceiling=Decimal(approval["per_attempt_ceiling_usd"]),
        )
        wire = live_adapter.OpenRouterWireGuard(
            budget, rates, max_output_tokens=16384, kind="run",
            allow_unfrozen_sources=True, allowed_resolved_models=aliases,
            serialize_paid_requests=True,
        )
        _write_new(job, record)
        work.mkdir(mode=0o700, parents=True)
        receipt = live_adapter.execute_cli(
            spec, work, wire, None, openrouter_key=auth["OPENROUTER_API_KEY"],
            sec_user_agent=auth["SEC_EDGAR_USER_AGENT"], claim=claim,
            source_credentials={
                "FRED_API_KEY": auth["FRED_API_KEY"],
                "ALPHA_VANTAGE_API_KEY": auth["ALPHA_VANTAGE_API_KEY"],
            },
        )
        record["execution_status"] = "complete"
        _write_new(work / "cli-receipt.json", receipt)
        try:
            proof = assess_document_feature_proof(receipt["state"], work, ticker)
        except Exception as exc:
            proof = {"status": "incomplete", "checks": {
                "feature_assessment": {"status": "missing", "detail": type(exc).__name__}
            }, "source_and_report_hashes": {}}
        _write_new(work / "document-proof-assessment.json", proof)
        record["proof_status"] = proof["status"]
        record["status"] = "proof_complete" if proof["status"] == "complete" else "proof_incomplete"
    except BaseException as exc:
        record.update(
            status="proof_incomplete" if record.get("execution_status") == "complete" else "failed",
            proof_status="incomplete", error_type=type(exc).__name__,
        )
        ledger.append({"type": "attempt_failed_start" if record.get("execution_status") != "complete"
                       else "attempt_proof_incomplete", "ticker": ticker,
                       "error_type": type(exc).__name__, "approval_sha256": digest})
        raise
    finally:
        settled = {e["ticket"] for e in ledger.events() if e.get("type") == "settle"}
        record.update(
            finished_at=datetime.now(UTC).isoformat(),
            committed_usd=str(ledger.committed_usd()),
            unknown_reservations=[
                e["ticket"] for e in ledger.events()
                if e.get("type") == "reserve" and e["ticket"] not in settled
            ],
        )
        try:
            temporary = job.with_suffix(".tmp")
            _write_new(temporary, record)
            temporary.replace(job)
        except OSError:
            ledger.append({"type": "attempt_job_unavailable", "ticker": ticker,
                           "status": record["status"], "approval_sha256": digest})
    return {"status": record["status"], "ticker": ticker, "job": str(job)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--qualify", action="store_true", help="offline local qualification (default)")
    group.add_argument("--run", choices=TICKERS, help="one paid ticker attempt after fresh approval")
    parser.add_argument("--credentials", type=Path, help="private credentials file for an approved run")
    args = parser.parse_args(argv)
    if args.run:
        if args.credentials is None:
            raise RuntimeError("--run requires fresh approval and explicit private credentials")
        print(json.dumps(run(args.run, args.credentials), indent=2))
    else:
        if args.credentials is not None:
            raise ValueError("Credentials are not read during offline qualification")
        print(json.dumps(qualification(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
