#!/usr/bin/env python3
"""Prepare and apply one hash-bound Flowwweb SWARM rollback snapshot.

This deliberately is not a general plugin installer.  It exists because the
Codex plugin CLI selects the current marketplace version but cannot select an
exact prior package.  The helper snapshots only the Flowwweb marketplace and
enablement sections, materializes an exact verified release package, and
restores those bounded sections after checking that all unrelated config bytes
are unchanged.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_package import installed_file_hashes, validate_plugin_manifest

import verify_plugin_install


SCHEMA = "swarm-flowwweb-rollback-v1"
MARKETPLACE = "flowwweb"
PLUGIN = "swarm"
MARKETPLACE_SECTION = "marketplaces.flowwweb"
PLUGIN_SECTION = 'plugins."swarm@flowwweb"'
PERSONAL_SECTION = 'plugins."swarm@personal"'
TARGET_SECTIONS = (MARKETPLACE_SECTION, PLUGIN_SECTION)
TABLE_RE = re.compile(r"(?m)^\[([^\]\r\n]+)\][^\r\n]*(?:\r?\n|$)")


class RollbackError(ValueError):
    """A fail-closed snapshot or restore error."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _section_ranges(text: str) -> dict[str, tuple[int, int]]:
    matches = list(TABLE_RE.finditer(text))
    ranges: dict[str, tuple[int, int]] = {}
    for index, match in enumerate(matches):
        name = match.group(1)
        if name in ranges:
            raise RollbackError(f"duplicate config section: {name}")
        ranges[name] = (match.start(), matches[index + 1].start() if index + 1 < len(matches) else len(text))
    return ranges


def _section_bytes(config: bytes) -> tuple[str, dict[str, bytes]]:
    try:
        text = config.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RollbackError("config.toml must be UTF-8") from error
    ranges = _section_ranges(text)
    missing = [name for name in TARGET_SECTIONS if name not in ranges]
    if missing:
        raise RollbackError(f"missing Flowwweb selection section(s): {missing}")
    return text, {
        name: text[start:end].encode("utf-8")
        for name, (start, end) in ranges.items()
        if name in (*TARGET_SECTIONS, PERSONAL_SECTION)
    }


def _guard_digest(text: str) -> str:
    ranges = _section_ranges(text)
    missing = [name for name in TARGET_SECTIONS if name not in ranges]
    if missing:
        raise RollbackError(f"missing Flowwweb selection section(s): {missing}")
    guarded = text
    for name in sorted(TARGET_SECTIONS, key=lambda item: ranges[item][0], reverse=True):
        start, end = ranges[name]
        guarded = guarded[:start] + f"[SWARM-ROLLBACK-TARGET:{name}]\n" + guarded[end:]
    return _sha256(guarded.encode("utf-8"))


def _replace_sections(text: str, replacements: dict[str, bytes]) -> bytes:
    ranges = _section_ranges(text)
    for name in TARGET_SECTIONS:
        if name not in ranges or name not in replacements:
            raise RollbackError(f"cannot replace missing selection section: {name}")
    updated = text
    for name in sorted(TARGET_SECTIONS, key=lambda item: ranges[item][0], reverse=True):
        start, end = ranges[name]
        try:
            replacement = replacements[name].decode("utf-8")
        except UnicodeDecodeError as error:
            raise RollbackError("snapshot selection section is not UTF-8") from error
        if not replacement.endswith(("\n", "\r")):
            replacement += "\n"
        updated = updated[:start] + replacement + updated[end:]
    return updated.encode("utf-8")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _rollback_marketplace_section(marketplace_root: Path) -> bytes:
    return (
        f"[{MARKETPLACE_SECTION}]\n"
        'source_type = "local"\n'
        f"source = {_toml_string(str(marketplace_root.resolve()))}\n\n"
    ).encode("utf-8")


def _encode_sections(sections: dict[str, bytes]) -> dict[str, str]:
    return {name: base64.b64encode(contents).decode("ascii") for name, contents in sections.items()}


def _decode_sections(sections: object) -> dict[str, bytes]:
    if not isinstance(sections, dict):
        raise RollbackError("snapshot selection sections are invalid")
    decoded: dict[str, bytes] = {}
    for name in TARGET_SECTIONS:
        value = sections.get(name)
        if not isinstance(value, str):
            raise RollbackError(f"snapshot selection section is missing: {name}")
        try:
            decoded[name] = base64.b64decode(value, validate=True)
        except ValueError as error:
            raise RollbackError(f"snapshot selection section is invalid: {name}") from error
    return decoded


def _files_digest(files: dict[str, str]) -> str:
    return _sha256(_json_bytes(dict(sorted(files.items()))))


def _atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.swarm-{os.getpid()}-{time.time_ns()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _safe_extract(package: Path, destination: Path) -> tuple[dict[str, str], dict[str, object]]:
    expected, _raw_metadata, metadata = verify_plugin_install._package_metadata(package)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(package) as archive:
        for relative in expected:
            target = destination / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(relative) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    actual = installed_file_hashes(destination)
    validate_plugin_manifest(destination, actual)
    if actual != expected:
        raise RollbackError("extracted rollback cache does not match the package manifest")
    return expected, metadata


def _verify_snapshot(snapshot: Path) -> dict[str, object]:
    manifest_path = snapshot / "rollback-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RollbackError("rollback manifest is missing or invalid") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise RollbackError("rollback manifest schema is invalid")
    if manifest.get("marketplace") != MARKETPLACE or manifest.get("plugin") != PLUGIN:
        raise RollbackError("rollback manifest authority is not swarm@flowwweb")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
        raise RollbackError("rollback file manifest is invalid")
    source = snapshot / "marketplace" / "plugins" / PLUGIN
    actual = installed_file_hashes(source)
    validate_plugin_manifest(source, actual)
    if actual != files or _files_digest(actual) != manifest.get("files_digest"):
        raise RollbackError("rollback cache snapshot hash mismatch")
    marketplace = snapshot / "marketplace" / ".agents" / "plugins" / "marketplace.json"
    try:
        marketplace_data = json.loads(marketplace.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RollbackError("rollback marketplace is missing or invalid") from error
    if marketplace_data.get("name") != MARKETPLACE:
        raise RollbackError("rollback marketplace identity is invalid")
    return manifest


def _authority_checksum(package: Path) -> str:
    sidecar = package.with_name(package.name + ".sha256")
    try:
        line = sidecar.read_text(encoding="ascii")
    except (FileNotFoundError, UnicodeDecodeError) as error:
        raise RollbackError("authoritative package checksum sidecar is missing or invalid") from error
    expected_suffix = f"  {package.name}\n"
    if not line.endswith(expected_suffix):
        raise RollbackError("authoritative package checksum sidecar is invalid")
    digest = line[: -len(expected_suffix)]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RollbackError("authoritative package checksum sidecar is invalid")
    return digest


def prepare_snapshot(
    config: Path,
    package: Path,
    output: Path,
    launch_argv: list[str],
    package_authority: Path | None = None,
) -> dict[str, object]:
    if output.exists():
        raise RollbackError("rollback snapshot destination already exists")
    if not launch_argv or not all(isinstance(value, str) and value for value in launch_argv):
        raise RollbackError("launch command must be a non-empty argv list")
    config_bytes = config.read_bytes()
    text, current_sections = _section_bytes(config_bytes)
    personal_digest = _sha256(current_sections[PERSONAL_SECTION]) if PERSONAL_SECTION in current_sections else None
    staging = output.with_name(f".{output.name}.swarm-{os.getpid()}-{time.time_ns()}.tmp")
    if staging.exists():
        raise RollbackError("rollback staging path already exists")
    try:
        plugin_root = staging / "marketplace" / "plugins" / PLUGIN
        files, metadata = _safe_extract(package.resolve(), plugin_root)
        package_digest = _sha256(package.read_bytes())
        authority = package_authority.resolve() if package_authority else package.resolve()
        if package_authority and package_digest != _authority_checksum(authority):
            raise RollbackError("package read mirror does not match the authoritative checksum")
        marketplace_data = {
            "name": MARKETPLACE,
            "interface": {"displayName": "Flowwweb rollback"},
            "plugins": [{
                "name": PLUGIN,
                "source": {"source": "local", "path": f"./plugins/{PLUGIN}"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }],
        }
        _atomic_write(staging / "marketplace" / ".agents" / "plugins" / "marketplace.json", _json_bytes(marketplace_data))
        rollback_sections = {
            MARKETPLACE_SECTION: _rollback_marketplace_section(staging / "marketplace"),
            PLUGIN_SECTION: current_sections[PLUGIN_SECTION],
        }
        version = metadata.get("version")
        if not isinstance(version, str) or not version:
            raise RollbackError("release package version is invalid")
        manifest: dict[str, object] = {
            "schema": SCHEMA,
            "marketplace": MARKETPLACE,
            "plugin": PLUGIN,
            "version": version,
            "package_path": str(authority),
            "package_sha256": package_digest,
            "source_commit": metadata.get("commit"),
            "source_tree": metadata.get("tree"),
            "files": dict(sorted(files.items())),
            "files_digest": _files_digest(files),
            "selection": {
                "config_path": str(config.resolve()),
                "config_sha256": _sha256(config_bytes),
                "unrelated_guard_digest": _guard_digest(text),
                "personal_section_sha256": personal_digest,
                "captured_sections": _encode_sections({name: current_sections[name] for name in TARGET_SECTIONS}),
                "rollback_sections": _encode_sections(rollback_sections),
            },
            "launch_argv": launch_argv,
        }
        _atomic_write(staging / "rollback-manifest.json", _json_bytes(manifest))
        staging.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, output)
        manifest = _verify_snapshot(output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _copy_cache_atomic(source: Path, target: Path, expected: dict[str, str]) -> str:
    if target.exists():
        try:
            actual = installed_file_hashes(target)
            validate_plugin_manifest(target, actual)
        except (OSError, ValueError) as error:
            raise RollbackError("existing rollback cache path conflicts with the snapshot") from error
        if actual != expected:
            raise RollbackError("existing rollback cache path conflicts with the snapshot")
        return "unchanged"
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.swarm-{os.getpid()}-{time.time_ns()}.tmp")
    if staging.exists():
        raise RollbackError("rollback cache staging path already exists")
    try:
        shutil.copytree(source, staging)
        actual = installed_file_hashes(staging)
        validate_plugin_manifest(staging, actual)
        if actual != expected:
            raise RollbackError("staged rollback cache hash mismatch")
        os.replace(staging, target)
        return "restored"
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def restore_snapshot(snapshot: Path, codex_home: Path) -> dict[str, object]:
    snapshot = snapshot.resolve()
    manifest = _verify_snapshot(snapshot)
    selection = manifest.get("selection")
    if not isinstance(selection, dict):
        raise RollbackError("rollback selection receipt is invalid")
    config = codex_home.resolve() / "config.toml"
    config_before = config.read_bytes()
    text, sections = _section_bytes(config_before)
    if _guard_digest(text) != selection.get("unrelated_guard_digest"):
        raise RollbackError("unrelated config bytes changed; refusing bounded restore")
    personal_digest = _sha256(sections[PERSONAL_SECTION]) if PERSONAL_SECTION in sections else None
    if personal_digest != selection.get("personal_section_sha256"):
        raise RollbackError("swarm@personal selection changed; refusing restore")
    expected = manifest["files"]
    assert isinstance(expected, dict)
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise RollbackError("rollback version is invalid")
    cache_target = codex_home.resolve() / "plugins" / "cache" / MARKETPLACE / PLUGIN / version
    cache_action = _copy_cache_atomic(snapshot / "marketplace" / "plugins" / PLUGIN, cache_target, expected)
    replacements = _decode_sections(selection.get("rollback_sections"))
    # The staging directory name is intentionally replaced after publication.
    marketplace = snapshot / "marketplace"
    replacements[MARKETPLACE_SECTION] = _rollback_marketplace_section(marketplace)
    config_after = _replace_sections(text, replacements)
    _atomic_write(config, config_after)
    receipt = {
        "schema": SCHEMA,
        "operation": "restore",
        "marketplace": MARKETPLACE,
        "plugin": PLUGIN,
        "version": version,
        "config_path": str(config),
        "config_before_sha256": _sha256(config_before),
        "config_after_sha256": _sha256(config_after),
        "cache_path": str(cache_target),
        "cache_action": cache_action,
        "files_digest": manifest["files_digest"],
        "launch_argv": manifest.get("launch_argv"),
        "recorded_at_ms": time.time_ns() // 1_000_000,
    }
    log = snapshot / "rollback-log.jsonl"
    with log.open("ab") as handle:
        handle.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    return receipt


def _command(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--package", type=Path, required=True)
    prepare.add_argument("--package-authority", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--launch-argv-json", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--snapshot", type=Path, required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--snapshot", type=Path, required=True)
    restore.add_argument("--codex-home", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            launch_argv = json.loads(args.launch_argv_json)
            if not isinstance(launch_argv, list):
                raise RollbackError("launch command must be a JSON array")
            result = prepare_snapshot(
                args.config.resolve(),
                args.package.resolve(),
                args.output.absolute(),
                launch_argv,
                args.package_authority,
            )
        elif args.action == "verify":
            result = _verify_snapshot(args.snapshot.resolve())
        else:
            result = restore_snapshot(args.snapshot.resolve(), args.codex_home.resolve())
    except (RollbackError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        parser.exit(2, f"error: {str(error)[:500]}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_command())
