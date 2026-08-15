#!/usr/bin/env python3
"""Synchronize the exact Codex marketplace plugin from the canonical source."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath

from build_package import (
    _is_reparse_path,
    _tracked_product_paths,
    canonical_worktree_bytes,
    installed_file_hashes,
    is_git_repository_root,
    source_file_hashes,
    validate_plugin_manifest,
)


MIRROR_RELATIVE = Path("plugins") / "swarm"


@dataclass(frozen=True)
class SourceSnapshot:
    files: dict[str, str]
    payloads: dict[str, bytes]
    observations: dict[str, str]


def _expected_source(root: Path) -> SourceSnapshot:
    observations = source_file_hashes(root)
    tracked = _tracked_product_paths(root)
    if set(observations) != tracked:
        missing = sorted(tracked - set(observations))
        unexpected = sorted(set(observations) - tracked)
        raise ValueError(
            "canonical product surface differs from tracked files: "
            f"missing={missing}, unexpected={unexpected}"
        )
    payloads: dict[str, bytes] = {}
    files: dict[str, str] = {}
    for relative, observation in observations.items():
        payload = (root / PurePosixPath(relative)).read_bytes()
        if hashlib.sha256(payload).hexdigest() != observation:
            raise ValueError(f"canonical product file changed during mirror snapshot: {relative}")
        canonical = canonical_worktree_bytes(root, relative, payload)
        payloads[relative] = canonical
        files[relative] = hashlib.sha256(canonical).hexdigest()
    validate_plugin_manifest(root, files)
    return SourceSnapshot(files, payloads, observations)


def _expected_files(root: Path) -> dict[str, str]:
    return _expected_source(root).files


def _safe_destination(root: Path) -> Path:
    root = root.resolve()
    if not is_git_repository_root(root):
        raise ValueError(f"source must be the repository root: {root}")
    destination = (root / MIRROR_RELATIVE).resolve()
    if destination != root / MIRROR_RELATIVE:
        raise ValueError(f"plugin mirror escapes the repository: {destination}")
    plugins_root = root / "plugins"
    for candidate in (plugins_root, destination):
        if candidate.exists() and _is_reparse_path(candidate):
            raise ValueError(f"plugin mirror contains a link or junction: {candidate}")
    return destination


def _compare(expected: dict[str, str], actual: dict[str, str]) -> None:
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(
        path for path in expected.keys() & actual.keys() if expected[path] != actual[path]
    )
    if missing or extra or changed:
        raise ValueError(
            f"plugin mirror drift: missing={missing}, extra={extra}, changed={changed}"
        )


def check_mirror(root: Path) -> int:
    root = root.resolve()
    destination = _safe_destination(root)
    expected = _expected_files(root)
    actual = installed_file_hashes(destination)
    validate_plugin_manifest(destination, actual)
    _compare(expected, actual)
    return len(expected)


def write_mirror(root: Path) -> int:
    root = root.resolve()
    destination = _safe_destination(root)
    snapshot = _expected_source(root)
    expected = snapshot.files
    destination.mkdir(parents=True, exist_ok=True)

    for relative, expected_hash in expected.items():
        source = root / PurePosixPath(relative)
        target = destination / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        parent = target.parent
        while parent != root:
            if _is_reparse_path(parent):
                raise ValueError(f"plugin mirror contains a link or junction: {parent}")
            parent = parent.parent
        observed = source.read_bytes()
        if hashlib.sha256(observed).hexdigest() != snapshot.observations[relative]:
            raise ValueError(f"canonical product file changed during mirror sync: {relative}")
        payload = snapshot.payloads[relative]
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ValueError(f"canonical product snapshot is invalid: {relative}")
        temporary = target.with_name(target.name + ".swarm-sync.tmp")
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    actual = installed_file_hashes(destination)
    for relative in sorted(actual.keys() - expected.keys(), reverse=True):
        (destination / PurePosixPath(relative)).unlink()
    for directory, _, _ in os.walk(destination, topdown=False):
        candidate = Path(directory)
        if candidate != destination and not any(candidate.iterdir()):
            candidate.rmdir()

    return check_mirror(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="fail when the tracked mirror drifts")
    action.add_argument("--write", action="store_true", help="synchronize the tracked mirror")
    args = parser.parse_args()
    try:
        count = check_mirror(args.source) if args.check else write_mirror(args.source)
    except ValueError as error:
        parser.error(str(error))
    verb = "verified" if args.check else "synchronized"
    print(f"{verb} {count} product files in {(args.source.resolve() / MIRROR_RELATIVE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
