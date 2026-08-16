#!/usr/bin/env python3
"""Verify a complete installed SWARM plugin against source or a release ZIP."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
from build_package import (
    PACKAGE_METADATA_PATH,
    proof_policy_digest,
    _installed_included,
    _is_reparse_path,
    _source_included,
    normalise_relative_path,
    installed_file_hashes,
    is_git_repository_root,
    release_identity,
    source_file_hashes,
    validate_plugin_manifest,
    validate_canonical_paths,
)


def declared_files(plugin_root: Path) -> dict[str, str]:
    """The shared, full product surface (kept for callers of the former API)."""
    files = installed_file_hashes(plugin_root)
    validate_plugin_manifest(plugin_root, files)
    return files


def _compare(expected: dict[str, str], actual: dict[str, str]) -> int:
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(path for path in expected.keys() & actual.keys() if expected[path] != actual[path])
    if missing or extra or changed:
        raise ValueError(f"plugin tree mismatch: missing={missing}, extra={extra}, changed={changed}")
    return len(expected)


def verify(source: Path, installed: Path) -> int:
    source_files = (
        release_identity(source).files
        if is_git_repository_root(source)
        else source_file_hashes(source)
    )
    validate_plugin_manifest(source, source_files)
    return _compare(source_files, declared_files(installed))


def _skill_file_hashes(root: Path) -> dict[str, str]:
    """Hash one complete portable skill tree, rejecting links before copying it."""
    if not root.is_dir():
        raise ValueError("canonical skill directory is missing")
    files: dict[str, str] = {}
    for directory, directories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        kept_directories: list[str] = []
        for name in directories:
            candidate = directory_path / name
            if _is_reparse_path(candidate):
                raise ValueError("canonical skill contains a link or junction")
            kept_directories.append(name)
        directories[:] = kept_directories
        for name in filenames:
            candidate = directory_path / name
            if _is_reparse_path(candidate) or not candidate.is_file():
                raise ValueError("canonical skill contains a non-regular file")
            relative = normalise_relative_path(candidate.relative_to(root))
            files[relative] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if "SKILL.md" not in files:
        raise ValueError("canonical skill is missing SKILL.md")
    return dict(sorted(files.items()))


def _declared_skill_file_hashes(root: Path) -> dict[str, str]:
    """Hash only the canonical skill files selected by the package policy."""
    root = root.resolve()
    try:
        root.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise ValueError("canonical skill must be inside the SWARM repository") from error
    if not root.is_dir():
        raise ValueError("canonical skill directory is missing")

    files: dict[str, str] = {}
    for directory, directories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        kept_directories: list[str] = []
        for name in directories:
            candidate = directory_path / name
            if _is_reparse_path(candidate):
                raise ValueError("canonical skill contains a link or junction")
            repository_relative = candidate.relative_to(REPOSITORY_ROOT)
            if _source_included(repository_relative / "placeholder"):
                kept_directories.append(name)
        directories[:] = kept_directories
        for name in filenames:
            candidate = directory_path / name
            if _is_reparse_path(candidate) or not candidate.is_file():
                raise ValueError("canonical skill contains a non-regular file")
            repository_relative = candidate.relative_to(REPOSITORY_ROOT)
            if not _source_included(repository_relative):
                continue
            relative = normalise_relative_path(candidate.relative_to(root))
            files[relative] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if "SKILL.md" not in files:
        raise ValueError("canonical skill is missing SKILL.md")
    return dict(sorted(files.items()))


def _assert_safe_destination_ancestors(project: Path, destination: Path) -> None:
    """Reject existing reparse points before creating anything below the project."""
    for ancestor in (
        project,
        project / ".agents",
        project / ".agents" / "skills",
        destination,
    ):
        if (ancestor.exists() or ancestor.is_symlink()) and _is_reparse_path(ancestor):
            raise ValueError("Agent Skills destination parent contains a link or junction")


def install_agent_skill(project_root: Path) -> int:
    """Copy the declared canonical skill surface to one external project location."""
    source = (REPOSITORY_ROOT / "skills" / "swarm").resolve()
    project = project_root.absolute()
    if not project.is_dir():
        raise ValueError("project root does not exist")
    if _is_reparse_path(project):
        raise ValueError("Agent Skills destination parent contains a link or junction")
    try:
        project.resolve().relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("refusing to create a duplicate skill inside the SWARM repository")
    destination = project / ".agents" / "skills" / "swarm"
    _assert_safe_destination_ancestors(project, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Agent Skills destination already exists; refusing to overwrite it")
    source_files = _declared_skill_file_hashes(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_destination_ancestors(project, destination)
    try:
        destination.mkdir()
        for relative in source_files:
            source_file = source / relative
            destination_file = destination / relative
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            if _is_reparse_path(destination_file.parent):
                raise ValueError("Agent Skills destination parent contains a link or junction")
            shutil.copy2(source_file, destination_file)
        copied_files = _skill_file_hashes(destination)
    except Exception:
        if destination.exists() and not _is_reparse_path(destination):
            shutil.rmtree(destination)
        raise
    return _compare(source_files, copied_files)


LOWER_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")


def _verify_checksum_sidecar(package: Path, package_bytes: bytes) -> None:
    sidecar = package.with_name(package.name + ".sha256")
    try:
        contents = sidecar.read_bytes()
    except FileNotFoundError as error:
        raise ValueError(f"package checksum sidecar is missing: {sidecar.name}") from error
    actual = hashlib.sha256(package_bytes).hexdigest()
    expected = f"{actual}  {package.name}\n".encode("ascii")
    if contents != expected:
        raise ValueError(f"package checksum sidecar is invalid or stale: {sidecar.name}")


def _validate_metadata(metadata: object) -> tuple[dict[str, str], dict[str, object]]:
    if not isinstance(metadata, dict) or metadata.get("schema") not in {"swarm-package-v1", "swarm-package-v2"}:
        raise ValueError("package metadata schema is invalid")
    version = metadata.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("package metadata version is invalid")
    for field in ("commit", "tree"):
        if not isinstance(metadata.get(field), str) or not LOWER_HEX_40.fullmatch(metadata[field]):
            raise ValueError(f"package metadata {field} is invalid")
    files = metadata.get("files")
    if not isinstance(files, dict):
        raise ValueError("package metadata file manifest is invalid")
    expected: dict[str, str] = {}
    validate_canonical_paths(files, "package metadata")
    for path, digest in files.items():
        if not isinstance(path, str) or not isinstance(digest, str) or not LOWER_HEX_64.fullmatch(digest):
            raise ValueError("package metadata file manifest is invalid")
        safe_name = normalise_relative_path(path)
        if safe_name != path or not _installed_included(Path(safe_name)):
            raise ValueError(f"package metadata has unsafe product path: {path}")
        expected[safe_name] = digest
    if metadata["schema"] == "swarm-package-v2":
        planner_version = metadata.get("planner_version")
        policy_digest = metadata.get("policy_digest")
        if not isinstance(planner_version, str) or not planner_version.strip():
            raise ValueError("package metadata planner version is invalid")
        if not isinstance(policy_digest, str) or not LOWER_HEX_64.fullmatch(policy_digest):
            raise ValueError("package metadata policy digest is invalid")
        if policy_digest != proof_policy_digest(expected):
            raise ValueError("package metadata policy digest does not match its file manifest")
    return dict(sorted(expected.items())), metadata


def _package_metadata(package: Path) -> tuple[dict[str, str], bytes, dict[str, object]]:
    package_bytes = package.read_bytes()
    _verify_checksum_sidecar(package, package_bytes)
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        entries = archive.infolist()
        names = validate_canonical_paths(
            [entry.orig_filename for entry in entries], "package archive"
        )
        if names.count(PACKAGE_METADATA_PATH) != 1:
            raise ValueError(f"package must contain exactly one {PACKAGE_METADATA_PATH}")
        try:
            raw = archive.read(PACKAGE_METADATA_PATH)
        except KeyError as error:
            raise ValueError(f"package is missing {PACKAGE_METADATA_PATH}") from error
        try:
            metadata = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ValueError("package metadata is invalid") from error
        expected, metadata = _validate_metadata(metadata)
        archive_files: dict[str, str] = {}
        for entry in entries:
            if entry.is_dir():
                raise ValueError(f"package contains unexpected directory entry: {entry.filename}")
            unix_type = (entry.external_attr >> 16) & 0o170000
            if entry.external_attr & 0x0400 or unix_type not in {0, 0o100000}:
                raise ValueError(f"package contains link or reparse entry: {entry.filename}")
            raw_name = entry.orig_filename
            safe_name = normalise_relative_path(raw_name)
            if raw_name != safe_name:
                raise ValueError(f"package contains unsafe archive path: {raw_name}")
            if safe_name == PACKAGE_METADATA_PATH:
                continue
            if not _installed_included(Path(safe_name)):
                raise ValueError(f"package contains unexpected non-product file: {safe_name}")
            if safe_name in archive_files:
                raise ValueError(f"package contains duplicate file: {safe_name}")
            archive_files[safe_name] = hashlib.sha256(archive.read(entry)).hexdigest()
    _compare(expected, archive_files)
    return expected, raw, metadata


def verify_package(package: Path, installed: Path) -> int:
    """Verify an installed tree against the exact product manifest in a release ZIP."""
    expected, raw_metadata, metadata = _package_metadata(package)
    installed_files = declared_files(installed)
    installed_manifest = validate_plugin_manifest(installed, installed_files)
    if metadata["version"] != installed_manifest.get("version"):
        raise ValueError("package metadata version does not match installed manifest")
    count = _compare(expected, installed_files)
    installed_metadata = installed / PACKAGE_METADATA_PATH
    if installed_metadata.exists() and installed_metadata.read_bytes() != raw_metadata:
        raise ValueError("installed package metadata differs from the release package")
    return count


def _cli_error(error: Exception, paths: list[Path]) -> str:
    """Keep expected CLI failures bounded and avoid echoing local checkout roots."""
    message = str(error).replace("\r", " ").replace("\n", " ")
    for path in paths:
        try:
            message = message.replace(str(path.resolve()), "<plugin>")
        except OSError:
            pass
    return message[:500]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("installed", nargs="?", type=Path)
    parser.add_argument("--install-agent-skill", metavar="PROJECT", type=Path)
    source_or_package = parser.add_mutually_exclusive_group()
    source_or_package.add_argument("--source", type=Path)
    source_or_package.add_argument("--package", type=Path)
    args = parser.parse_args()
    try:
        if args.install_agent_skill:
            if args.installed or args.package or args.source:
                parser.error("--install-agent-skill cannot be combined with verification arguments")
            count = install_agent_skill(args.install_agent_skill)
            surface = "canonical Agent Skills files"
        elif not args.installed:
            parser.error("installed is required for verification")
        elif args.package:
            count = verify_package(args.package.resolve(), args.installed.resolve())
            surface = "release package"
        else:
            count = verify(args.source.resolve(), args.installed.resolve())
            surface = "source product"
    except (ValueError, zipfile.BadZipFile, OSError) as error:
        parser.exit(2, f"error: {_cli_error(error, [path for path in [args.installed, args.package or args.source, args.install_agent_skill] if path])}\n")
    action = "installed" if args.install_agent_skill else "verified"
    print(f"{action} {count} {surface}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
