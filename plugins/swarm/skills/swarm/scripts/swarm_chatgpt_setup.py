#!/usr/bin/env python3
"""Configure a single-project SWARM upstream for the pinned external Codexify bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "swarm_mcp.py"
DEFAULT_CODEXIFY_CONFIG = Path.home() / ".codexify" / "codexify.config.json"
BRIDGE_VERSION = "1.3.0"
# Windows x64 executable from the checksum-verified upstream v1.3.0 archive.
BRIDGE_SHA256 = "4570d3e9a0359bcd56cfcdd59c79ce6ac1045d5d28b1bb1192350ae9c798440c"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Codexify config must contain a JSON object")
    return value


def _desired(config: dict, *, project_root: Path) -> dict:
    result = dict(config)
    existing_root = result.get("workDir")
    if existing_root is not None and (
        not isinstance(existing_root, str)
        or not Path(existing_root).is_absolute()
        or Path(existing_root).resolve() != project_root
    ):
        raise ValueError("Existing workDir differs; use a separate config for this project")
    if result.get("multiProject", False) is not False:
        raise ValueError("Existing multiProject scope conflicts; use a separate config")
    imports = result.get("codexMcp", {})
    if not isinstance(imports, dict) or any(imports.get(key, False) is not False for key in ("enabled", "useCli")):
        raise ValueError("Existing Codex MCP import conflicts; use a separate config")
    servers = result.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be an object")
    upstream = {
        "command": sys.executable,
        "args": [str(SCRIPT), "--stdio"],
        "cwd": str(project_root),
        "mode": "catalog",
        "tools": ["swarm_status", "swarm_projects", "swarm_usage"],
    }
    if "swarm" in servers and servers["swarm"] != upstream:
        raise ValueError("Existing swarm upstream differs; use a separate config")
    result.update({
        "workDir": str(project_root), "multiProject": False,
        "codexMcp": {**imports, "enabled": False, "useCli": False},
        "mcpServers": {**servers, "swarm": upstream},
    })
    return result


def configure(path: Path, project_root: Path, *, write: bool) -> dict:
    project_root = project_root.expanduser().resolve()
    if not project_root.is_dir():
        raise ValueError(f"project root does not exist: {project_root}")
    config = _desired(_load(path), project_root=project_root)
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".swarm.tmp")
        # Exclusive creation preserves an interrupted or concurrent writer's file.
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(path)
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CODEXIFY_CONFIG)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--bridge", help="explicit path to verified Codexify 1.3.0 executable")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write the scoped config; never create credentials")
    mode.add_argument("--check", action="store_true", help="check bootstrap prerequisites without writing")
    args = parser.parse_args(argv)
    bridge = shutil.which(str(Path(args.bridge).expanduser())) if args.bridge else shutil.which("codexify")
    path = args.config.expanduser().resolve()
    errors = []
    version_ok = False
    if bridge:
        try:
            with Path(bridge).open("rb") as stream:
                version_ok = hashlib.file_digest(stream, "sha256").hexdigest() == BRIDGE_SHA256
        except OSError:
            pass
    if not version_ok:
        errors.append("Verified Codexify 1.3.0 Windows x64 executable missing or checksum differs")
    if not SCRIPT.is_file():
        errors.append("SWARM adapter missing")
    config = {}
    try:
        config = configure(path, args.project_root, write=False)
    except (OSError, ValueError) as exc:
        # Do not echo parser details: an existing config may contain credentials.
        errors.append(str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else "Config unreadable or invalid JSON")
    tunnel = config.get("openaiTunnel")
    print(json.dumps({
        "bridge": "codexify", "bridge_found": bool(bridge), "bridge_path": bridge,
        "required_version": BRIDGE_VERSION, "version_verified": version_ok,
        "verification": "pinned_windows_x64_sha256",
        "adapter_exists": SCRIPT.is_file(), "config": str(path),
        "project_root": str(args.project_root.expanduser().resolve()),
        "write_requested": args.write, "bootstrap_ready": not errors, "errors": errors,
        "tunnel_reference_present": isinstance(tunnel, dict) and bool(tunnel.get("tunnelId") and tunnel.get("apiKeyRef")),
        "doctor": {"status": "not_run", "command": [bridge or "codexify", "doctor", "--config", str(path), "--json"]},
        "connector_status": "unverified",
        "start_status": "not_started; configure native tunnel credentials before starting",
    }, sort_keys=True))
    if errors:
        return 2
    if args.write:
        try:
            configure(path, args.project_root, write=True)
        except (OSError, ValueError):
            print("Config write failed; existing config was not replaced by this operation.", file=sys.stderr)
            return 2
        print(f"Configured {path}. Credentials and tunnel connection remain externally managed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
