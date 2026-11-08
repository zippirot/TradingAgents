"""Pre-baseline stores stay isolated across comparison attempts."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from tradingagents.comparison_snapshot import capture_starting_snapshot, clone_starting_snapshot


def _config(root: Path) -> dict:
    return {
        "results_dir": str(root / "live-results"),
        "data_cache_dir": str(root / "live-cache"),
        "memory_log_path": str(root / "live-memory" / "memory.md"),
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_comparison_uses_prebaseline_snapshot_and_leaves_live_store_untouched(tmp_path):
    config = _config(tmp_path)
    memory = Path(config["memory_log_path"])
    publication = Path(config["results_dir"]) / "publications" / "outcomes" / "a.json"
    cache = Path(config["data_cache_dir"]) / "vendor" / "bar.json"
    for path, data in ((memory, b"old lesson"), (publication, b'{"old":true}'), (cache, b"old cache")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    os.utime(cache, ns=(1_700_000_000_123_456_789, 1_700_000_000_123_456_789))
    # Analysis output belongs outside the captured publication store.
    (Path(config["results_dir"]) / "baseline-only.txt").write_text("ignore")
    cache_hash, cache_mtime = _sha(cache), cache.stat().st_mtime_ns

    snapshot = tmp_path / "comparison-start"
    manifest = capture_starting_snapshot(config, snapshot)
    assert manifest["version"] == 1
    assert all("baseline-only" not in row["path"] for row in manifest["files"])
    assert not (snapshot / "baseline-only.txt").exists()

    baseline = clone_starting_snapshot(snapshot, tmp_path / "baseline" / "comparison-run")
    Path(baseline["memory_log_path"]).write_text("baseline lesson")
    (Path(baseline["results_dir"]) / "publications" / "outcomes" / "new.json").write_text("new")
    (Path(baseline["data_cache_dir"]) / "vendor" / "bar.json").write_text("new cache")
    candidate = clone_starting_snapshot(snapshot, tmp_path / "candidate" / "comparison-run")

    assert Path(candidate["memory_log_path"]).read_bytes() == b"old lesson"
    assert (Path(candidate["results_dir"]) / "publications" / "outcomes" / "a.json").read_bytes() == b'{"old":true}'
    assert not (Path(candidate["results_dir"]) / "publications" / "outcomes" / "new.json").exists()
    candidate_cache = Path(candidate["data_cache_dir"]) / "vendor" / "bar.json"
    assert _sha(candidate_cache) == cache_hash
    assert candidate_cache.stat().st_mtime_ns == cache_mtime
    assert _sha(cache) == cache_hash and cache.stat().st_mtime_ns == cache_mtime
    assert memory.read_bytes() == b"old lesson" and publication.read_bytes() == b'{"old":true}'
    assert not os.access(snapshot / "memory" / "memory.md", os.W_OK) or (snapshot / "memory" / "memory.md").stat().st_mode & 0o222 == 0


@pytest.mark.parametrize("damage", ["tamper", "missing", "extra"])
def test_clone_rejects_incomplete_or_tampered_snapshot(tmp_path, damage):
    config = _config(tmp_path)
    memory = Path(config["memory_log_path"])
    memory.parent.mkdir()
    memory.write_text("old")
    snapshot = tmp_path / "snapshot"
    capture_starting_snapshot(config, snapshot)
    if damage == "tamper":
        stored = snapshot / "memory" / "memory.md"
        stored.chmod(0o600)
        stored.write_text("bad")
    elif damage == "missing":
        (snapshot / "memory" / "memory.md").unlink()
    else:
        (snapshot / "cache" / "extra").write_text("bad")
    destination = tmp_path / "clone"
    with pytest.raises(ValueError):
        clone_starting_snapshot(snapshot, destination)
    assert not destination.exists()


def test_capture_rejects_overlap_and_symlink_traversal(tmp_path):
    config = _config(tmp_path)
    cache = Path(config["data_cache_dir"])
    cache.mkdir()
    with pytest.raises(ValueError):
        capture_starting_snapshot(config, cache / "snapshot")
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        capture_starting_snapshot(config, tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()


def test_clone_rejects_manifest_escape_and_destination_inside_snapshot(tmp_path):
    config = _config(tmp_path)
    memory = Path(config["memory_log_path"])
    memory.parent.mkdir()
    memory.write_text("old")
    snapshot = tmp_path / "snapshot"
    capture_starting_snapshot(config, snapshot)
    with pytest.raises(ValueError):
        clone_starting_snapshot(snapshot, snapshot / "clone")
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][0]["path"] = "memory/../../escape"
    manifest_path.chmod(0o600)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        clone_starting_snapshot(snapshot, tmp_path / "clone")
    assert not (tmp_path / "clone").exists()


def test_empty_stores_produce_writable_empty_clone(tmp_path):
    config = _config(tmp_path)
    snapshot = tmp_path / "snapshot"
    manifest = capture_starting_snapshot(config, snapshot)
    assert manifest["files"] == []
    clone = clone_starting_snapshot(snapshot, tmp_path / "clone")
    assert Path(clone["results_dir"]).is_dir()
    assert (Path(clone["results_dir"]) / "publications").is_dir()
    assert Path(clone["data_cache_dir"]).is_dir()
    memory = Path(clone["memory_log_path"])
    memory.write_text("new")
    assert not Path(config["memory_log_path"]).exists()
