"""Offline-qualified A7 pilot contracts. No network or model client lives here.

A paid executor must inject a source-frozen callback and reserve every model
request through BudgetGuard. Approval is task-specific data, never inherited
from an older proof ledger. These helpers cannot certify a source capture hook.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

A = "openai/gpt-6.1-terra-pro"
B_QUICK = "openai/gpt-6.1-sol"
B_DEEP = "anthropic/claude-opus-5.5"
DOMAINS = ("sec_facts", "sec_filings", "prices_indicators", "consensus",
           "news_social", "default_peers", "memory", "prior_publication")
ORDER = ("A", "B", "B", "A", "A", "B")


@dataclass(frozen=True)
class Slot:
    name: str
    setup: str
    quick_model: str
    deep_model: str
    depth: int = 2


SLOTS = tuple(Slot(f"run-{i+1:02d}", setup, A if setup == "A" else B_QUICK,
                   A if setup == "A" else B_DEEP) for i, setup in enumerate(ORDER))


@dataclass(frozen=True)
class Approval:
    approved_manifest_sha256: str
    ceiling_usd: str
    reviewer_model_id: str
    reviewer_max_calls: int


def manifest_hash(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_manifest(manifest: dict, root: Path) -> bool:
    """Verify every frozen source and seed against its retained bytes."""
    if not isinstance(manifest, dict) or manifest.get("depth") != 2:
        raise ValueError("Comparison manifest requires depth 2")
    if not all(manifest.get(k) for k in ("ticker", "analysis_date", "cutoff_utc", "source_version",
                                               "prompt_version", "tool_limit", "context_cap")):
        raise ValueError("Comparison manifest is missing fixed run settings")
    if manifest.get("analysts") != ["market", "social", "news", "fundamentals"]:
        raise ValueError("Comparison analysts differ from the fixed four")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Frozen source files are missing")
    for domain in DOMAINS:
        item = files.get(domain)
        if not isinstance(item, dict):
            raise ValueError(f"Missing frozen {domain}")
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid frozen {domain}")
        candidate = root / path
        file = candidate.resolve()
        if (not file.is_relative_to(root.resolve()) or not file.is_file()
                or any(part.is_symlink() for part in (candidate, *candidate.parents))):
            raise ValueError(f"Missing or unsafe frozen {domain}")
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Hash mismatch for frozen {domain}")
    reviewer = manifest.get("reviewer")
    if not isinstance(reviewer, dict) or not reviewer.get("model_id") or not isinstance(reviewer.get("settings"), dict) or not reviewer["settings"]:
        raise ValueError("Named reviewer model and fixed settings are required")
    return True


class PilotLedger:
    """Task-specific append-only reservations; unknown costs stay reserved."""
    def __init__(self, path: Path):
        self.path = path

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def append(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @contextmanager
    def budget_lock(self):
        """Separate lock for concurrent model requests within a claimed slot."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(".budget.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def committed_usd(self) -> Decimal:
        events = self.events()
        return (sum((Decimal(e["usd"]) for e in events if e["type"] in ("reserve", "settle")), Decimal(0))
                - sum((Decimal(e["usd"]) for e in events if e["type"] == "release"), Decimal(0)))

    def committed_scope_usd(self, scope: str) -> Decimal:
        events = self.events()
        tickets = {e["ticket"] for e in events if e["type"] == "reserve" and e.get("scope") == scope}
        return (sum((Decimal(e["usd"]) for e in events if e["type"] in ("reserve", "settle")
                     and e.get("ticket") in tickets), Decimal(0))
                - sum((Decimal(e["usd"]) for e in events if e["type"] == "release"
                       and e.get("ticket") in tickets), Decimal(0)))


class FrozenSourceGateway:
    """Content-addressed offline replay for common inputs and cutoff-bound peer lookups.

    The CLI adapter must route every source read here. Only peer lookups can
    invoke the injected capture callback; no automatic network fallback exists.
    """
    def __init__(self, manifest: dict, inputs_root: Path, peer_root: Path,
                 fetch_peer: Callable[[dict], bytes] | None = None):
        validate_manifest(manifest, inputs_root)
        self.manifest, self.inputs_root, self.peer_root, self.fetch_peer = manifest, inputs_root, peer_root, fetch_peer
        self.request_hashes: dict[str, str] = {}

    def common(self, domain: str) -> bytes:
        if domain not in DOMAINS:
            raise ValueError("Unfrozen source domain")
        item = self.manifest["files"][domain]
        data = (self.inputs_root / item["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Frozen common input changed")
        return data

    def peer(self, ticker: str, cutoff_utc: str) -> bytes:
        if not re.fullmatch(r"[A-Z][A-Z0-9.^=-]{0,31}", ticker) or cutoff_utc != self.manifest["cutoff_utc"]:
            raise ValueError("Peer request scope differs from fixed cutoff")
        request = {"ticker": ticker, "cutoff_utc": cutoff_utc}
        key = "peer:" + manifest_hash(request)
        path = self.peer_root / f"{key}.json"
        if self.peer_root.is_symlink():
            raise ValueError("Unsafe peer replay directory")
        self.peer_root.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.is_symlink():
                raise ValueError("Unsafe peer replay file")
            data = path.read_bytes()
        else:
            if self.fetch_peer is None:
                raise ValueError("Peer request was not captured")
            data = self.fetch_peer(request)
            if not isinstance(data, bytes):
                raise ValueError("Peer capture must return raw retained bytes")
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        digest = hashlib.sha256(data).hexdigest()
        if key in self.request_hashes and self.request_hashes[key] != digest:
            raise ValueError("Repeated peer source bytes differ")
        self.request_hashes[key] = digest
        return data


class BudgetGuard:
    def __init__(self, ledger: PilotLedger, ceiling: Decimal, *, allowed_models: set[str], max_calls: int,
                 scope: str = "all", allowed_kinds: set[str] | None = None,
                 scope_ceiling: Decimal | None = None):
        if not ceiling.is_finite() or ceiling <= 0 or max_calls < 1:
            raise ValueError("Invalid approved budget")
        self.ledger, self.ceiling, self.allowed_models = ledger, ceiling, allowed_models
        self.max_calls = max_calls
        self.scope = scope
        if scope_ceiling is not None and (not scope_ceiling.is_finite() or scope_ceiling <= 0
                                          or scope_ceiling > ceiling):
            raise ValueError("Invalid scope budget cap")
        self.scope_ceiling = scope_ceiling
        self.allowed_kinds = allowed_kinds or {"run", "review"}
        self.calls = 0
        self.outstanding: set[str] = set()

    def reserve(self, model_id: str, upper_usd: str, *, kind: str) -> str:
        if model_id not in self.allowed_models or kind not in self.allowed_kinds:
            raise RuntimeError("Unapproved model or request kind")
        upper = Decimal(upper_usd)
        if not upper.is_finite() or upper <= 0:
            raise ValueError("Invalid request reservation")
        with self.ledger.budget_lock():
            prior_calls = sum(e["type"] == "reserve" and (self.scope == "all" or e.get("scope") == self.scope)
                              for e in self.ledger.events())
            if prior_calls >= self.max_calls:
                raise RuntimeError("Request call cap reached")
            if self.ledger.committed_usd() + upper > self.ceiling:
                raise RuntimeError("Comparison budget cap reached")
            if (self.scope_ceiling is not None and
                    self.ledger.committed_scope_usd(self.scope) + upper > self.scope_ceiling):
                raise RuntimeError("Request scope cap reached")
            ticket = secrets.token_hex(16)
            self.ledger.append({"type": "reserve", "ticket": ticket, "model": model_id, "scope": self.scope,
                                "kind": kind, "usd": str(upper)})
        self.outstanding.add(ticket)
        self.calls += 1
        return ticket

    def settle(self, ticket: str, actual_usd: str) -> None:
        if ticket not in self.outstanding:
            raise RuntimeError("Unknown or already settled reservation")
        actual = Decimal(actual_usd)
        with self.ledger.budget_lock():
            events = self.ledger.events()
            reservation = next((e for e in events if e.get("ticket") == ticket and e["type"] == "reserve"), None)
            if reservation is None or any(e.get("ticket") == ticket and e["type"] == "settle" for e in events):
                raise RuntimeError("Unknown or already settled reservation")
            upper = Decimal(reservation["usd"])
            if not actual.is_finite() or actual < 0 or actual > upper:
                raise ValueError("Invalid actual cost; reservation retained")
            self.ledger.append({"type": "settle", "ticket": ticket, "usd": str(actual)})
            self.ledger.append({"type": "release", "ticket": ticket, "usd": str(upper)})
        self.outstanding.remove(ticket)


class PilotRunner:
    """Durable one-shot slot claims with injected execution; no automatic retry."""
    def __init__(self, manifest: dict, inputs_root: Path, ledger: PilotLedger, approval: Approval | None):
        validate_manifest(manifest, inputs_root)
        if approval is None or approval.approved_manifest_sha256 != manifest_hash(manifest):
            raise ValueError("A distinct approved comparison manifest and budget are required")
        ceiling = Decimal(approval.ceiling_usd)
        if (not ceiling.is_finite() or ceiling <= 0 or approval.reviewer_model_id != manifest["reviewer"]["model_id"]
                or approval.reviewer_max_calls != 6):
            raise ValueError("Invalid approved comparison budget or reviewer")
        self.manifest, self.ledger, self.approval, self.ceiling = manifest, ledger, approval, ceiling

    def run_slot(self, slot: Slot, execute_run: Callable[[Slot, BudgetGuard], dict]) -> dict:
        if slot not in SLOTS:
            raise ValueError("Unknown comparison slot")
        lock_path = self.ledger.path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            events = self.ledger.events()
            if any(e.get("slot") == slot.name and e["type"] == "slot_claim" for e in events):
                raise RuntimeError("Slot already claimed; inspect and recover without relaunch")
            for preceding in SLOTS[:SLOTS.index(slot)]:
                if not any(e.get("slot") == preceding.name and e["type"] == "slot_end" for e in events):
                    raise RuntimeError("Comparison slots must follow the fixed A B B A A B order")
            self.ledger.append({"type": "slot_claim", "slot": slot.name, "setup": slot.setup,
                                "manifest_hash": manifest_hash(self.manifest)})
            guard = BudgetGuard(self.ledger, self.ceiling,
                                allowed_models={slot.quick_model, slot.deep_model}, max_calls=64,
                                scope=slot.name, allowed_kinds={"run"})
            try:
                result = execute_run(slot, guard)
                if not isinstance(result, dict) or not isinstance(result.get("state"), dict):
                    raise ValueError("Executor did not return saved state")
                if result.get("common_hash") != manifest_hash(self.manifest):
                    raise ValueError("Run common-input hash differs from approved manifest")
                if result.get("memory_hash") != self.manifest["files"]["memory"]["sha256"] or result.get("prior_publication_hash") != self.manifest["files"]["prior_publication"]["sha256"]:
                    raise ValueError("Starting memory or prior publication differs")
                if not isinstance(result.get("request_hashes"), dict):
                    raise ValueError("Missing per-request source hashes")
                if not all(isinstance(k, str) and k and isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
                           for k, v in result["request_hashes"].items()):
                    raise ValueError("Invalid per-request source hash")
                expected_scope = {"ticker": self.manifest["ticker"], "analysis_date": self.manifest["analysis_date"],
                                  "depth": 2, "analysts": self.manifest["analysts"],
                                  "tool_limit": self.manifest["tool_limit"], "context_cap": self.manifest["context_cap"],
                                  "quick_model": slot.quick_model, "deep_model": slot.deep_model,
                                  "llm_max_retries": 0}
                if result.get("scope") != expected_scope:
                    raise ValueError("Actual run scope differs from approved comparison scope")
                if result["state"].get("trade_date") != self.manifest["analysis_date"] or result["state"].get("company_of_interest") != self.manifest["ticker"]:
                    raise ValueError("Saved state differs from approved comparison scope")
                if not result.get("completed") or result.get("model_calls") != guard.calls or guard.outstanding:
                    raise ValueError("Run completion, request count or cost settlement unverified")
                result = {**result, "slot": slot.name, "setup": slot.setup, "status": "complete"}
                destination = self.ledger.path.parent / f"{slot.name}.json"
                with destination.open("x") as handle:
                    json.dump(result, handle, sort_keys=True)
                self.ledger.append({"type": "slot_end", "slot": slot.name, "status": "complete"})
                return result
            except BaseException as exc:
                self.ledger.append({"type": "slot_end", "slot": slot.name, "status": "failed",
                                    "error_type": type(exc).__name__})
                raise

    def run_reviews(self, review: Callable[[dict, BudgetGuard], dict]) -> list[dict]:
        """One blinded review call per completed run, without relaunch on failure."""
        lock_path = self.ledger.path.with_suffix(".lock")
        with lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            runs = []
            for slot in SLOTS:
                path = self.ledger.path.parent / f"{slot.name}.json"
                if not path.is_file():
                    raise ValueError("Six complete saved runs required")
                runs.append(json.loads(path.read_text()))
            inputs, mapping = prepare_blinded_reviews(runs)
            mapping_path = self.ledger.path.parent / "blind-mapping.json"
            if mapping_path.exists():
                raise RuntimeError("Reviews already claimed; inspect saved results without relaunch")
            fd = os.open(mapping_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(mapping, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            self.ledger.append({"type": "reviews_claim", "manifest_hash": manifest_hash(self.manifest),
                                "reviewer_model": self.approval.reviewer_model_id,
                                "reviewer_settings": self.manifest["reviewer"]["settings"]})
            scores = []
            for payload in inputs:
                opaque = payload["opaque_id"]
                self.ledger.append({"type": "review_claim", "opaque_id": opaque,
                                    "payload_sha256": manifest_hash(payload)})
                guard = BudgetGuard(self.ledger, self.ceiling,
                                    allowed_models={self.approval.reviewer_model_id}, max_calls=6,
                                    scope="reviews", allowed_kinds={"review"})
                before = guard.calls
                try:
                    result = review(payload, guard)
                    if (not isinstance(result, dict) or result.get("model_id") != self.approval.reviewer_model_id
                            or result.get("settings") != self.manifest["reviewer"]["settings"]
                            or not isinstance(result.get("score"), (int, float))
                            or not 0 <= result["score"] <= 5
                            or guard.calls != before + 1 or guard.outstanding):
                        raise ValueError("Reviewer model, settings, score or settlement unverified")
                    saved = {"opaque_id": opaque, "score": result["score"],
                             "findings": result.get("findings", []),
                             "model_id": result["model_id"], "settings": result["settings"],
                             "cost_usd": result.get("cost_usd"),
                             "truncations": payload["truncations"]}
                    path = self.ledger.path.parent / f"review-{opaque}.json"
                    with path.open("x") as handle:
                        json.dump(saved, handle, sort_keys=True)
                    self.ledger.append({"type": "review_end", "opaque_id": opaque, "status": "complete"})
                    scores.append({"slot": mapping[opaque], **saved})
                except BaseException as exc:
                    self.ledger.append({"type": "review_end", "opaque_id": opaque, "status": "failed",
                                        "error_type": type(exc).__name__})
                    raise
            return scores


REVIEW_FIELD_CAP = 18000


def _redact(text: object, field: str, truncations: list[str]) -> str:
    value = text if isinstance(text, str) else json.dumps(text, sort_keys=True, default=str)
    if len(value) > REVIEW_FIELD_CAP:
        truncations.append(field)
        value = value[:REVIEW_FIELD_CAP] + "\n[Reviewer field truncated at declared cap]"
    value = re.sub(r"(?:openai|anthropic)/[A-Za-z0-9._-]+", "[model withheld]", value, flags=re.I)
    value = re.sub(r"\bsetup\s+[AB]\b", "[setup withheld]", value, flags=re.I)
    clean, in_audit = [], False
    for line in value.splitlines():
        heading = re.match(r"^(#{1,6})\s+", line)
        if heading:
            in_audit = bool(re.search(r"audit|reviewer findings", line, flags=re.I))
        if in_audit or re.search(
            r"\baudit(?:or)?\b|\baudit (?:finding|status|verdict)\b|"
            r"\bfindings?\b.*\b(?:upheld|rejected|confirmed|dismissed)\b",
            line, flags=re.I,
        ):
            continue
        clean.append(line)
    return "\n".join(clean)


def _model_outputs(state: dict) -> tuple[dict, dict]:
    """Original model prose; publication fields are deterministic renderings."""
    originals = state.get("unvalidated_outputs")
    if not isinstance(originals, dict):
        originals = None
    roles = ("market_report", "sentiment_report", "news_report", "fundamentals_report",
             "investment_plan", "trader_investment_plan", "final_trade_decision")
    analysis = {}
    for role in roles:
        if role == "fundamentals_report":
            validation = state.get("financial_claim_validation") or {}
            raw = validation.get("raw_report") if isinstance(validation, dict) else None
            if isinstance(raw, str):
                analysis[role] = raw
                continue
        analysis[role] = (originals.get(role) if originals is not None else state.get(role)) or ""
    if originals is not None and not analysis["final_trade_decision"]:
        manager = originals.get("portfolio_manager") or {}
        if isinstance(manager, dict):
            analysis["final_trade_decision"] = manager.get("fallback") or manager.get("structured") or ""
    debates = {}
    for key in ("investment_debate_state", "risk_debate_state"):
        value = originals.get(key) if originals is not None else state.get(key)
        debates[key] = value if isinstance(value, dict) else {}
    return analysis, debates


def prepare_blinded_reviews(runs: list[dict]) -> tuple[list[dict], dict[str, str]]:
    if len(runs) != 6 or {r.get("slot") for r in runs} != {s.name for s in SLOTS} or any(r.get("status") != "complete" for r in runs):
        raise ValueError("Six complete comparison runs are required before review")
    required_contexts = ("shared_source_brief", "canonical_financial_context", "valuation_reference_brief")
    contexts = (*required_contexts,
                "financial_calculations", "disclosure_evidence")
    roles = ("market_report", "sentiment_report", "news_report", "fundamentals_report",
             "investment_plan", "trader_investment_plan", "final_trade_decision")
    inputs, mapping = [], {}
    for run in runs:
        state = run.get("state")
        if not isinstance(state, dict) or not all(state.get(key) for key in required_contexts):
            raise ValueError("Saved run lacks retained reviewer evidence")
        opaque = secrets.token_hex(12)
        mapping[opaque] = run["slot"]
        truncations = []
        model_analysis, model_debates = _model_outputs(state)
        debates = {}
        for key in ("investment_debate_state", "risk_debate_state"):
            value = model_debates[key]
            debates[key] = {k: _redact(v, f"{key}.{k}", truncations)
                            for k, v in value.items() if k == "history" or k.endswith("_history")}
        inputs.append({"opaque_id": opaque,
                       "evidence": {k: _redact(state.get(k), k, truncations) for k in contexts},
                       "analysis": {k: _redact(model_analysis.get(k), k, truncations) for k in roles},
                       "debates": debates,
                       "truncations": truncations, "field_cap_characters": REVIEW_FIELD_CAP,
                       "rubric": {"scale": "0–5", "score_basis": "Substantive claims corroborated by retained evidence and calculations, reconciliation of numbers, and accurate citation of source labels; report unsupported or contradictory examples with cited evidence labels.",
                                  "limits": "Evidence absence means unsupported by supplied material, not proof no source exists. Do not use stock outcome, writing style, or the run's own audit verdict."}})
    secrets.SystemRandom().shuffle(inputs)
    return inputs, mapping


def _counts(state: dict) -> dict:
    validation = state.get("financial_claim_validation") or {}
    raw = validation.get("raw_report") if isinstance(validation, dict) else None
    matches = re.findall(r"```financial_claims\s*\n(.*?)\n```", raw or "", re.S) if isinstance(raw, str) else []
    financial_submitted = financial_accepted = financial_rejected = financial_deduplicated = None
    if len(matches) == 1:
        try:
            rows = json.loads(matches[0])
            if isinstance(rows, list) and len(rows) <= 32:
                financial_submitted = sum(not (isinstance(r, dict) and r.get("kind") == "hypothesis") for r in rows)
                fact_ids = validation.get("fact_ids")
                reasons = validation.get("reasons")
                if isinstance(fact_ids, list) and isinstance(reasons, list):
                    financial_accepted = len(fact_ids)
                    financial_rejected = sum(bool(re.fullmatch(r"Claim \d+:.*", str(reason))) for reason in reasons)
                    residual = financial_submitted - financial_accepted - financial_rejected
                    if residual >= 0:
                        financial_deduplicated = residual
                    else:
                        financial_accepted = financial_rejected = None
        except (TypeError, ValueError):
            pass
    extraction = ((state.get("disclosure_evidence") or {}).get("extraction") or {})
    # Publication replaces fundamentals_report with canonical context. The
    # original structured extraction survives in financial_claim_validation.
    disclosure_raw = raw
    blocks = re.findall(r"```disclosures\s*\n(.*?)\n```", disclosure_raw or "", re.S) if isinstance(disclosure_raw, str) else []
    disclosure_submitted = disclosure_accepted = disclosure_rejected = None
    if len(blocks) == 1:
        try:
            rows = json.loads(blocks[0])
            if isinstance(rows, list) and len(rows) <= 32:
                disclosure_submitted = len(rows)
                claims, rejected = extraction.get("claims"), extraction.get("rejected")
                if (isinstance(claims, list) and isinstance(rejected, list)
                        and all(re.fullmatch(r"record \d+:.*", str(reason)) for reason in rejected)):
                    disclosure_accepted, disclosure_rejected = len(claims), len(rejected)
                    if disclosure_accepted + disclosure_rejected != disclosure_submitted:
                        disclosure_accepted = disclosure_rejected = None
        except (TypeError, ValueError):
            pass
    return {"financial_submitted": financial_submitted,
            "financial_accepted": financial_accepted, "financial_rejected": financial_rejected,
            "financial_deduplicated": financial_deduplicated,
            "financial_acceptance_rate": (str(Decimal(financial_accepted) / financial_submitted)
                                          if financial_submitted and financial_accepted is not None else "N/A"),
            "disclosure_submitted": disclosure_submitted,
            "disclosure_accepted": disclosure_accepted, "disclosure_rejected": disclosure_rejected,
            "disclosure_acceptance_rate": (str(Decimal(disclosure_accepted) / disclosure_submitted)
                                           if disclosure_submitted and disclosure_accepted is not None else "N/A")}


def _reference_ids(brief: str) -> set[str]:
    """Use labels actually printed in the valuation brief, including source IDs."""
    ids = set(re.findall(r"\[([A-Za-z][A-Za-z0-9:._-]{1,127})\]", brief))
    ids.update(re.findall(r"\bsource_id\s+([A-Za-z][A-Za-z0-9:._-]{1,127})", brief))
    ids.update(re.findall(r"\bfact\s+([A-Za-z][A-Za-z0-9:._-]{1,127})", brief))
    return ids


def _used_reference_ids(labels: set[str], text: str) -> list[str]:
    return sorted(label for label in labels if re.search(
        r"(?<![\w:])" + re.escape(label) + r"(?![\w:])", text))


def summarize_runs(runs: list[dict]) -> dict:
    """Descriptive pilot table only; confounded/incomplete runs cannot be ranked."""
    by_slot = {r.get("slot"): r for r in runs}
    complete = len(runs) == 6 and set(by_slot) == {s.name for s in SLOTS} and all(
        by_slot[s.name].get("status") == "complete" and by_slot[s.name].get("setup") == s.setup for s in SLOTS)
    common = {r.get("common_hash") for r in runs}
    memory = {r.get("memory_hash") for r in runs}
    prior = {r.get("prior_publication_hash") for r in runs}
    request_seen, request_conflict = {}, False
    for run in runs:
        for key, digest in (run.get("request_hashes") or {}).items():
            if key in request_seen and request_seen[key] != digest:
                request_conflict = True
            request_seen[key] = digest
    reviewed = all(r.get("review_score") is not None for r in runs)
    review_truncated = any(r.get("review_truncations") for r in runs)
    controlled = (complete and reviewed and not review_truncated and
                  all(len(group) == 1 and None not in group for group in (common, memory, prior))
                  and not request_conflict)
    rows = []
    for slot in SLOTS:
        run = by_slot.get(slot.name) or {}
        state = run.get("state") or {}
        counts = _counts(state) if run.get("status") == "complete" else {}
        source = str(state.get("valuation_reference_brief") or "")
        labels = _reference_ids(source)
        model_analysis, model_debates = _model_outputs(state)
        debate_text = "\n".join(str(model_debates[k]) for k in ("investment_debate_state", "risk_debate_state"))
        decision_text = "\n".join(str(model_analysis[k]) for k in
                                  ("investment_plan", "trader_investment_plan", "final_trade_decision"))
        debate_citations = _used_reference_ids(labels, debate_text)
        decision_citations = _used_reference_ids(labels, decision_text)
        peers = ((state.get("valuation_reference") or {}).get("peers") or {})
        proposal = ((state.get("valuation_reference") or {}).get("proposal") or {})
        proposed = {p.get("ticker") for p in proposal.get("peers", []) if isinstance(p, dict)}
        accepted = {p.get("ticker") for p in peers.get("accepted", []) if isinstance(p, dict)}
        rows.append({"slot": slot.name, "setup": slot.setup, "status": run.get("status", "missing"),
                     **counts, "valid_peer_proposed": bool(proposed & accepted),
                     "valid_debate_citation_count": len(debate_citations),
                     "valid_decision_citation_count": len(decision_citations),
                     "model_calls": run.get("model_calls"),
                     "cost_usd": run.get("cost_usd"), "review_score": run.get("review_score"),
                     "failure": run.get("failure")})
    spreads = {}
    for setup in ("A", "B"):
        group = [r for r in rows if r["setup"] == setup and r["status"] == "complete"]
        spreads[setup] = {}
        for metric in ("financial_acceptance_rate", "disclosure_acceptance_rate",
                       "valid_debate_citation_count", "valid_decision_citation_count",
                       "model_calls", "cost_usd", "review_score"):
            try:
                values = [Decimal(str(r[metric])) for r in group]
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
            if len(values) == 3:
                spreads[setup][metric] = [str(min(values)), str(max(values))]
    measure_assessment = {}
    for metric in set(spreads["A"]) & set(spreads["B"]):
        left = [Decimal(v) for v in spreads["A"][metric]]
        right = [Decimal(v) for v in spreads["B"][metric]]
        width = max(left[1] - left[0], right[1] - right[0])
        left_values = [Decimal(str(r[metric])) for r in rows if r["setup"] == "A" and r["status"] == "complete"]
        right_values = [Decimal(str(r[metric])) for r in rows if r["setup"] == "B" and r["status"] == "complete"]
        gap = abs(sum(left_values) / 3 - sum(right_values) / 3)
        measure_assessment[metric] = ("descriptive only" if not controlled else
                                      "inconclusive" if width > gap else "pilot only")
    reasons = []
    if not complete:
        reasons.append("Incomplete or failed six-run sequence")
    if not reviewed:
        reasons.append("Six blinded reviewer scores are not saved")
    if review_truncated:
        reasons.append("At least one blinded reviewer input was truncated")
    if any(len(group) != 1 or None in group for group in (common, memory, prior)):
        reasons.append("Common input or starting-state hashes differ")
    if request_conflict:
        reasons.append("Repeated source request hashes differ")
    return {"controlled_comparison": controlled, "reasons": reasons, "runs": rows,
            "spreads": spreads, "measure_assessment": measure_assessment, "winner": None,
            "interpretation": "One-ticker, one-date pilot; no composite winner or statistical significance claim."}
