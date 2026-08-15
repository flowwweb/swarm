#!/usr/bin/env python3
"""Build a reproducible, source-verified SWARM plugin archive.

The package contains every tracked product file selected by ``source_file_hashes``
and one generated metadata record.  That one policy is also used by the install
verifier so a release and an installed tree cannot silently disagree about their
surface area.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable


PACKAGE_METADATA_PATH = "swarm-package.json"
PACKAGING_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
    }
)
PACKAGING_IGNORED_FILE_NAMES = frozenset({".DS_Store", ".coverage", "Thumbs.db"})
PACKAGING_IGNORED_SUFFIXES = frozenset({".log", ".pyc", ".pyo", ".sqlite", ".sqlite3"})
DEVELOPMENT_ONLY_PATHS = frozenset(
    {
        "docs/friction-audit.md",
        "scripts/sync_plugin_mirror.py",
    }
)
DEVELOPMENT_ONLY_DIRECTORIES = frozenset(
    {
        ".github",
        "console/tests",
        "plugins",
        "skills/swarm/evals",
        "skills/swarm/tests",
    }
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}
)


def normalise_relative_path(path: Path | str) -> str:
    """Return an OS-independent safe POSIX archive name or reject aliases."""
    value = path.as_posix() if isinstance(path, Path) else path
    if not value or "\\" in value or value.startswith("/"):
        raise ValueError(f"unsafe package path: {value}")
    parts = value.split("/")
    if any(
        not part
        or part in {".", ".."}
        or any(ord(character) < 32 or character in '<>:"\\|?*' for character in part)
        for part in parts
    ):
        raise ValueError(f"unsafe package path: {value}")
    for part in parts:
        if part[-1] in {".", " "}:
            raise ValueError(f"unsafe Windows alias in package path: {value}")
        device = part.split(".", 1)[0].upper()
        if device in WINDOWS_RESERVED_NAMES:
            raise ValueError(f"unsafe Windows device path: {value}")
    return PurePosixPath(*parts).as_posix()


def windows_collision_key(name: str) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in name.split("/"))


def validate_canonical_paths(paths: object, context: str) -> list[str]:
    """Validate one canonical cross-platform path set for build and verification."""
    canonical: list[str] = []
    exact: set[str] = set()
    windows_keys: set[tuple[str, ...]] = set()
    for raw_path in paths:
        if not isinstance(raw_path, str):
            raise ValueError(f"{context} contains a non-string path")
        safe_name = normalise_relative_path(raw_path)
        if raw_path != safe_name:
            raise ValueError(f"{context} contains an unsafe path: {raw_path}")
        if safe_name in exact:
            raise ValueError(f"{context} contains a duplicate path: {safe_name}")
        collision_key = windows_collision_key(safe_name)
        if collision_key in windows_keys:
            raise ValueError(f"{context} has a Windows-normalized collision: {safe_name}")
        exact.add(safe_name)
        windows_keys.add(collision_key)
        canonical.append(safe_name)
    return canonical


def _source_included(relative: Path) -> bool:
    """Clean-checkout packaging exclusions; never use this for installed parity."""
    archive_name = normalise_relative_path(relative)
    parts = PurePosixPath(archive_name).parts
    if any(part in PACKAGING_IGNORED_DIRECTORIES for part in parts[:-1]):
        return False
    if archive_name in DEVELOPMENT_ONLY_PATHS or any(
        archive_name == directory or archive_name.startswith(directory + "/")
        for directory in DEVELOPMENT_ONLY_DIRECTORIES
    ):
        return False
    name = parts[-1]
    if archive_name == PACKAGE_METADATA_PATH or name in PACKAGING_IGNORED_FILE_NAMES:
        return False
    return Path(name).suffix.lower() not in PACKAGING_IGNORED_SUFFIXES


def _installed_included(relative: Path) -> bool:
    """Installed trees may ignore only host metadata generated after installation."""
    archive_name = normalise_relative_path(relative)
    parts = PurePosixPath(archive_name).parts
    return not (
        ".git" in parts[:-1]
        or "__pycache__" in parts[:-1]
        or archive_name == PACKAGE_METADATA_PATH
    )


def _is_reparse_path(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    if path.is_symlink() or bool(junction and junction()):
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & 0x0400)


def _file_hashes(root: Path, included: Callable[[Path], bool]) -> dict[str, str]:
    """Hash a policy-selected tree and reject links/junctions before traversal."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"plugin root does not exist: {root}")

    files: dict[str, str] = {}
    for directory, directories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        kept_directories: list[str] = []
        for name in directories:
            candidate = directory_path / name
            relative = candidate.relative_to(root)
            if _is_reparse_path(candidate):
                raise ValueError(f"unsafe link or junction in plugin tree: {relative.as_posix()}")
            if not included(relative / "placeholder"):
                continue
            kept_directories.append(name)
        directories[:] = kept_directories

        for name in filenames:
            candidate = directory_path / name
            relative = candidate.relative_to(root)
            if _is_reparse_path(candidate) or not candidate.is_file():
                raise ValueError(f"unsafe non-regular file in plugin tree: {relative.as_posix()}")
            if not included(relative):
                continue
            archive_name = normalise_relative_path(relative)
            files[archive_name] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return dict(sorted(files.items()))


def source_file_hashes(root: Path) -> dict[str, str]:
    return _file_hashes(root, _source_included)


def installed_file_hashes(root: Path) -> dict[str, str]:
    return _file_hashes(root, _installed_included)


def validate_plugin_manifest(root: Path, files: dict[str, str] | None = None) -> dict[str, object]:
    """Require a usable manifest and declared skills tree on a product surface."""
    root = root.resolve()
    manifest_path = root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skills = manifest["skills"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"invalid plugin manifest: {manifest_path}") from error
    if not isinstance(skills, str) or not skills:
        raise ValueError("plugin manifest skills must be a non-empty relative path")
    skills_relative = Path(skills)
    normalise_relative_path(skills_relative)
    skills_root = (root / skills_relative).resolve()
    try:
        skills_root.relative_to(root)
    except ValueError as error:
        raise ValueError("plugin manifest skills path escapes the plugin root") from error
    if not skills_root.is_dir():
        raise ValueError(f"plugin manifest skills path does not exist: {skills}")
    surface = files if files is not None else installed_file_hashes(root)
    if not any(path.startswith(normalise_relative_path(skills_relative).rstrip("/") + "/") for path in surface):
        raise ValueError(f"plugin manifest skills path has no shipped files: {skills}")
    return manifest


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git verification failed: {' '.join(arguments)}: {detail}")
    return completed.stdout


def _git_bytes(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments], capture_output=True, check=False
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise ValueError(f"git verification failed: {' '.join(arguments)}: {detail}")
    return completed.stdout


def is_git_repository_root(root: Path) -> bool:
    """Return whether ``root`` is exactly a usable Git worktree top level."""
    root = root.resolve()
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode:
        return False
    return Path(completed.stdout.strip()).resolve() == root


def _tracked_product_paths(root: Path) -> set[str]:
    tracked = _git(root, "ls-files", "-z").split("\0")
    paths: set[str] = set()
    for name in tracked:
        if not name:
            continue
        relative = Path(name)
        archive_name = normalise_relative_path(relative)
        if _source_included(relative):
            paths.add(archive_name)
    return paths


@dataclass(frozen=True)
class GitSnapshot:
    commit: str
    tree: str
    version: str
    files: dict[str, str]
    blob_ids: dict[str, str]
    blobs: dict[str, bytes]


def _snapshot_manifest(blobs: dict[str, bytes], files: dict[str, str]) -> str:
    try:
        manifest = json.loads(blobs[".codex-plugin/plugin.json"].decode("utf-8"))
        skills = manifest["skills"]
        version = manifest["version"]
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise ValueError("captured plugin manifest is invalid") from error
    if not isinstance(version, str) or not version:
        raise ValueError("captured plugin manifest version must be a non-empty string")
    if not isinstance(skills, str) or not skills:
        raise ValueError("captured plugin manifest skills must be a non-empty relative path")
    skills_path = normalise_relative_path(Path(skills)).rstrip("/") + "/"
    if not any(path.startswith(skills_path) for path in files):
        raise ValueError(f"captured plugin manifest skills path has no shipped files: {skills}")
    return version


def _capture_snapshot(root: Path, commit: str, tree: str) -> GitSnapshot:
    """Read each package blob once from a single immutable commit/tree snapshot."""
    files: dict[str, str] = {}
    blob_ids: dict[str, str] = {}
    blobs: dict[str, bytes] = {}
    for entry in _git_bytes(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not entry:
            continue
        try:
            header, raw_path = entry.split(b"\t", 1)
            mode, object_type, object_id = header.decode("ascii").split(" ")
            relative = Path(raw_path.decode("utf-8", "surrogateescape"))
        except ValueError as error:
            raise ValueError("git HEAD tree contains an invalid entry") from error
        archive_name = normalise_relative_path(relative)
        if not _source_included(relative):
            continue
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"unsupported tracked source entry: {archive_name} ({mode} {object_type})")
        blob = _git_bytes(root, "cat-file", "blob", object_id)
        blob_ids[archive_name] = object_id
        blobs[archive_name] = blob
        files[archive_name] = hashlib.sha256(blob).hexdigest()
    validate_canonical_paths(
        [*files, PACKAGE_METADATA_PATH], "captured source snapshot and generated metadata"
    )
    files = dict(sorted(files.items()))
    return GitSnapshot(
        commit,
        tree,
        _snapshot_manifest(blobs, files),
        files,
        dict(sorted(blob_ids.items())),
        blobs,
    )


def _working_clean_blob_ids(root: Path) -> dict[str, str]:
    """Hash product files as Git would store them, applying configured clean filters."""
    paths = _file_hashes(root, _source_included)
    blobs: dict[str, str] = {}
    for archive_name in paths:
        candidate = root / PurePosixPath(archive_name)
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "hash-object",
                "--filters",
                f"--path={archive_name}",
                "--stdin",
            ],
            input=candidate.read_bytes(),
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            detail = completed.stderr.decode("utf-8", "replace").strip()
            raise ValueError(
                f"git verification failed: hash-object --path={archive_name}: {detail}"
            )
        object_id = completed.stdout.decode("ascii", "strict").strip()
        if not object_id:
            raise ValueError(f"git returned no content hash for tracked source file: {archive_name}")
        blobs[archive_name] = object_id
    return blobs


def release_identity(root: Path) -> GitSnapshot:
    """Reject a non-clean/non-repository source and return immutable Git identity."""
    root = root.resolve()
    top_level = Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    if top_level != root:
        raise ValueError(f"source must be the repository root: {root}")
    commit = _git(root, "rev-parse", "HEAD").strip()
    tree = _git(root, "rev-parse", f"{commit}^{{tree}}").strip()
    snapshot = _capture_snapshot(root, commit, tree)
    untracked = [
        line[3:]
        for line in _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
        if line.startswith("?? ")
    ]
    if untracked:
        raise ValueError(f"source repository has untracked files: {untracked}")

    files = _working_clean_blob_ids(root)
    tracked = _tracked_product_paths(root)
    if set(files) != tracked:
        missing = sorted(tracked - set(files))
        unexpected = sorted(set(files) - tracked)
        raise ValueError(
            f"source package surface differs from tracked files: missing={missing}, unexpected={unexpected}"
        )
    if files != snapshot.blob_ids:
        missing = sorted(set(snapshot.files) - set(files))
        unexpected = sorted(set(files) - set(snapshot.files))
        changed = sorted(
            path
            for path in set(files) & set(snapshot.files)
            if files[path] != snapshot.blob_ids[path]
        )
        raise ValueError(
            "source bytes differ from HEAD after configured clean filters: "
            f"missing={missing}, unexpected={unexpected}, changed={changed}"
        )

    return snapshot


def package_metadata(root: Path) -> dict[str, object]:
    snapshot = release_identity(root)
    return {
        "schema": "swarm-package-v1",
        "version": snapshot.version,
        "commit": snapshot.commit,
        "tree": snapshot.tree,
        "files": snapshot.files,
    }


def _metadata_bytes(metadata: dict[str, object]) -> bytes:
    return (json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _build_snapshot_bytes(snapshot: GitSnapshot) -> tuple[bytes, dict[str, object]]:
    metadata = {
        "schema": "swarm-package-v1",
        "version": snapshot.version,
        "commit": snapshot.commit,
        "tree": snapshot.tree,
        "files": snapshot.files,
    }
    import io

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
        for archive_name in metadata["files"]:
            info = zipfile.ZipInfo(archive_name, date_time=ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, snapshot.blobs[archive_name])
        info = zipfile.ZipInfo(PACKAGE_METADATA_PATH, date_time=ZIP_TIMESTAMP)
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        archive.writestr(info, _metadata_bytes(metadata))
    return payload.getvalue(), metadata


def build_package_bytes(root: Path) -> tuple[bytes, dict[str, object]]:
    """Build deterministic ZIP bytes from one validated immutable Git snapshot."""
    return _build_snapshot_bytes(release_identity(root))


def write_package(root: Path, output: Path, verify_repeat: bool = False) -> tuple[str, int]:
    root = root.resolve()
    output = output.resolve()
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("package output must be outside the source repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = release_identity(root)
    first, metadata = _build_snapshot_bytes(snapshot)
    if verify_repeat:
        second, _ = _build_snapshot_bytes(snapshot)
        if first != second:
            raise ValueError("repeated package build was not byte-identical")
    output.write_bytes(first)
    checksum = hashlib.sha256(first).hexdigest()
    output.with_name(output.name + ".sha256").write_bytes(
        f"{checksum}  {output.name}\n".encode("ascii")
    )
    return checksum, len(metadata["files"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-repeat", action="store_true", help="build twice and require identical ZIP bytes")
    args = parser.parse_args()
    try:
        checksum, count = write_package(args.source, args.output, args.verify_repeat)
    except ValueError as error:
        parser.error(str(error))
    print(f"built {args.output.resolve()} ({count} files, sha256 {checksum})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
