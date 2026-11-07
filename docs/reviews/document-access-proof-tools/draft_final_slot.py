"""Offline CAT-only candidate and approval drafts; never claim or run an attempt."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import live_cli
from pilot import PilotLedger


def _write_draft(path: Path, value: dict) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write("\n")
    path.chmod(0o600)


def draft(original_path: Path, metadata_path: Path, output_dir: Path) -> tuple[Path, Path]:
    environment = live_cli.assert_environment()
    if environment["branch"] != "codex/document-access-b" or not environment["clean"]:
        raise RuntimeError("Draft requires a clean committed B candidate")
    if original_path.resolve() == live_cli.APPROVAL.resolve():
        raise ValueError("Archive the original approval before drafting; active approval is read-only")
    original = live_cli.read_json(original_path)
    live_cli.live_adapter._validate_document_access_approval(original)
    if "final_slot_amendment" in original:
        raise ValueError("Original approval must precede any CAT amendment")
    metadata = live_cli.read_json(metadata_path)
    rates = live_cli.live_adapter.conservative_route_rates(metadata, live_cli.MODEL_IDS)
    aliases = {
        name: sorted(values) for name, values in
        live_cli.live_adapter.resolved_model_ids(metadata, live_cli.MODEL_IDS).items()
    }
    if rates != original["approved_route_rate_caps"] or aliases != original["resolved_model_ids"]:
        raise ValueError("Draft endpoint route differs from original approved caps or IDs")
    prior = live_cli.prior_ledger_snapshot()
    for key in ("old_ledgers", "prior_committed_exposure_usd", "prior_unknown_reserved_usd"):
        if original[key] != prior[key]:
            raise ValueError("Historical ledgers changed")
    source_candidate = live_cli.read_json(live_cli.CANDIDATE)
    candidate = {
        **source_candidate, "branch": environment["branch"], "head": environment["head"],
        "module_hashes": {
            name: item["sha256"] for name, item in environment["modules"].items()
        },
        "runner_sha256": live_cli.sha(Path(live_cli.__file__)),
        "provider_metadata_path": str(metadata_path.resolve()),
        "provider_metadata_sha256": live_cli.sha(metadata_path),
        "reviewed_route_rates": rates, "resolved_model_ids": aliases,
        "authority": "DRAFT ONLY; no CAT attempt or spending authority",
    }
    ledger = PilotLedger(live_cli.LEDGER)
    prefix = ledger.path.read_bytes()
    amendment = {
        "schema_version": 1, "ticker": "CAT",
        "original_approval_path": str(original_path.resolve()),
        "original_approval_sha256": live_cli.sha(original_path),
        "original_approval_digest": live_cli.live_adapter.manifest_hash(original),
        "ledger_prefix_bytes": len(prefix),
        "ledger_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
    }
    if output_dir.is_symlink():
        raise ValueError("Draft output directory is unsafe")
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    candidate_path = output_dir / "cat-candidate-draft.json"
    approval_path = output_dir / "cat-approval-draft.json"
    if candidate_path.exists() or approval_path.exists():
        raise FileExistsError("Draft output already exists")
    _write_draft(candidate_path, candidate)
    approval = {
        **original, "approval_id": "", "approved_at_recorded": "",
        "user_instruction": "", "candidate_head": environment["head"],
        "candidate_sha256": live_cli.sha(candidate_path),
        "runner_sha256": candidate["runner_sha256"],
        "provider_metadata_sha256": candidate["provider_metadata_sha256"],
        "final_slot_amendment": amendment,
    }
    provisional = {
        **approval, "approval_id": "unissued-draft",
        "approved_at_recorded": datetime.now(UTC).isoformat(),
        "user_instruction": "DRAFT; not user approval",
    }
    live_cli.live_adapter._validate_document_access_approval(provisional)
    live_cli.live_adapter._document_final_slot_amendment(provisional, ledger)
    _write_draft(approval_path, approval)
    return candidate_path, approval_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-approval", type=Path, required=True)
    parser.add_argument("--provider-metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    candidate, approval = draft(
        args.original_approval, args.provider_metadata, args.output_dir,
    )
    print(json.dumps({"candidate_draft": str(candidate), "approval_draft": str(approval),
                      "paid_calls": 0, "attempt_claimed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
