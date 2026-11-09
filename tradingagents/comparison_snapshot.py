"""Private, verified pre-run copies of comparison memory and source stores."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath

_VERSION = 1
_STORE_DIRS = ("publications", "cache", "memory")


def _no_symlinks(path: Path) -> None:
    """Reject links in existing path components, including the root itself."""
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"symlink traversal is not allowed: {component}")


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _check_destination(destination: Path, sources: tuple[Path, ...]) -> None:
    _no_symlinks(destination)
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    absolute = destination.absolute()
    for source in sources:
        root = source.absolute()
        if _within(absolute, root) or _within(root, absolute):
            raise ValueError(f"destination overlaps source: {destination}")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_files(config: dict) -> list[tuple[Path, str]]:
    roots = {
        "publications": Path(config["results_dir"]) / "publications",
        "cache": Path(config["data_cache_dir"]),
    }
    memory = Path(config["memory_log_path"])
    for path in (*roots.values(), memory):
        _no_symlinks(path)
    files: list[tuple[Path, str]] = []
    for label, root in roots.items():
        if not root.exists():
            continue
        if not root.is_dir():
            raise ValueError(f"store is not a directory: {root}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"symlink traversal is not allowed: {path}")
            if not path.is_dir() and not path.is_file():
                raise ValueError(f"unsupported store entry: {path}")
            if path.is_file():
                files.append((path, f"{label}/{path.relative_to(root).as_posix()}"))
    if memory.exists():
        if not memory.is_file():
            raise ValueError(f"memory store is not a file: {memory}")
        files.append((memory, "memory/memory.md"))
    return sorted(files, key=lambda item: item[1])


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _copy_file(source: Path, target: Path, *, readonly: bool) -> None:
    _private_directory(target.parent)
    with source.open("rb") as input_file, target.open("xb") as output_file:
        shutil.copyfileobj(input_file, output_file)
    os.utime(target, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
    target.chmod(0o400 if readonly else 0o600)


def capture_starting_snapshot(config: dict, destination: Path) -> dict:
    """Capture the pre-baseline stores; return a content-hash manifest.

    The snapshot contains only publications, cache and the memory log. Existing
    destinations and paths that could recursively copy a source are refused.
    """
    destination = Path(destination)
    publications = Path(config["results_dir"]) / "publications"
    cache = Path(config["data_cache_dir"])
    memory = Path(config["memory_log_path"])
    _check_destination(destination, (publications, cache, memory))
    original = _source_files(config)
    signatures = {
        relative: (source.stat().st_size, source.stat().st_mtime_ns, _hash_file(source))
        for source, relative in original
    }
    manifest = {"version": _VERSION, "files": []}
    try:
        _private_directory(destination)
        for label in _STORE_DIRS:
            _private_directory(destination / label)
        for source, relative in original:
            target = destination / relative
            _copy_file(source, target, readonly=True)
            size, mtime_ns, digest = signatures[relative]
            if target.stat().st_size != size or _hash_file(target) != digest:
                raise ValueError(f"source changed during snapshot: {relative}")
            manifest["files"].append({
                "path": relative, "size": size, "mtime_ns": mtime_ns, "sha256": digest,
            })
        current = _source_files(config)
        if [(path, relative) for path, relative in current] != original:
            raise ValueError("source file set changed during snapshot")
        for source, relative in original:
            size, mtime_ns, digest = signatures[relative]
            if (source.stat().st_size, source.stat().st_mtime_ns, _hash_file(source)) != (size, mtime_ns, digest):
                raise ValueError(f"source changed during snapshot: {relative}")
        manifest_path = destination / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
        manifest_path.chmod(0o400)
        return manifest
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        raise


def _verified_manifest(snapshot: Path) -> dict:
    _no_symlinks(snapshot)
    if not snapshot.is_dir():
        raise ValueError(f"snapshot is missing: {snapshot}")
    for path in snapshot.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError(f"unsafe snapshot entry: {path}")
    try:
        manifest = json.loads((snapshot / "manifest.json").read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("snapshot manifest is missing or invalid") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"version", "files"} or manifest["version"] != _VERSION or not isinstance(manifest["files"], list):
        raise ValueError("invalid snapshot manifest")
    expected = {"manifest.json"}
    for row in manifest["files"]:
        if not isinstance(row, dict) or set(row) != {"path", "size", "mtime_ns", "sha256"}:
            raise ValueError("invalid snapshot file entry")
        relative = row["path"]
        if not isinstance(relative, str):
            raise ValueError("invalid snapshot path")
        parts = PurePosixPath(relative).parts
        if (not parts or parts[0] not in _STORE_DIRS or any(part in (".", "..") for part in parts)
                or (parts[0] == "memory" and relative != "memory/memory.md")
                or len(parts) < 2 or PurePosixPath(relative).as_posix() != relative or relative in expected):
            raise ValueError("invalid snapshot path")
        expected.add(relative)
        if (not isinstance(row["size"], int) or row["size"] < 0
                or not isinstance(row["mtime_ns"], int) or row["mtime_ns"] < 0
                or not isinstance(row["sha256"], str) or len(row["sha256"]) != 64):
            raise ValueError("invalid snapshot file metadata")
        path = snapshot / relative
        if not path.is_file() or path.stat().st_size != row["size"] or _hash_file(path) != row["sha256"]:
            raise ValueError(f"snapshot file is missing or changed: {relative}")
    actual = {path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()}
    if actual != expected:
        raise ValueError("snapshot file set is incomplete or changed")
    return manifest


def clone_starting_snapshot(snapshot: Path, destination: Path) -> dict:
    """Create a separate writable run store and return its config overrides."""
    snapshot, destination = Path(snapshot), Path(destination)
    _check_destination(destination, (snapshot,))
    manifest = _verified_manifest(snapshot)
    try:
        _private_directory(destination)
        for label in _STORE_DIRS:
            _private_directory(destination / label)
        for row in manifest["files"]:
            relative = row["path"]
            source = snapshot / relative
            target = destination / relative
            _copy_file(source, target, readonly=False)
            if _hash_file(target) != row["sha256"] or target.stat().st_mtime_ns != row["mtime_ns"]:
                raise ValueError(f"snapshot changed during clone: {relative}")
        return {
            "results_dir": str(destination),
            "data_cache_dir": str(destination / "cache"),
            "memory_log_path": str(destination / "memory" / "memory.md"),
        }
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        raise
