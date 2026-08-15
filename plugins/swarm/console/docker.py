#!/usr/bin/env python3
"""Launch the SWARM Console Compose project."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "docker-compose.yml"
CONFIG_SCRIPT = HERE.parent / "skills" / "swarm" / "scripts" / "swarm_config.py"


def _resolve_config_path() -> Path:
    spec=importlib.util.spec_from_file_location("swarm_docker_config",CONFIG_SCRIPT)
    if not spec or not spec.loader: raise RuntimeError(f"could not load SWARM config resolver: {CONFIG_SCRIPT}")
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.resolve_config_path().expanduser().resolve()


def _set_container_user(environment: dict[str, str]) -> None:
    """Match the host identity on POSIX so bind-mounted settings stay writable."""
    if "SWARM_CONTAINER_USER" in environment:
        return
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if callable(getuid) and callable(getgid):
        uid = getuid()
        gid = getgid()
        if uid > 0 and gid > 0:
            environment["SWARM_CONTAINER_USER"] = f"{uid}:{gid}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "down", "config"), nargs="?", default="up")
    parser.add_argument("--detach", action="store_true", help="run the container in the background")
    args = parser.parse_args()
    if not shutil.which("docker"):
        print("SWARM Console Docker error: docker command not found", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment.setdefault("SWARM_CODEX_HOME",str(Path.home() / ".codex"))
    selected_config=_resolve_config_path()
    environment["SWARM_CONFIG_HOME"]=str(selected_config.parent)
    environment["SWARM_CONTAINER_CONFIG_PATH"]=f"/data/swarm/{selected_config.name}"
    _set_container_user(environment)
    if args.action == "up":
        config_home = selected_config.parent
        config_home.mkdir(parents=True, exist_ok=True)
        environment["SWARM_CONFIG_HOME"] = str(config_home)

    command = ["docker", "compose", "-f", str(COMPOSE)]
    if args.action == "up":
        command.extend(("up", "--build"))
        if args.detach:
            command.append("--detach")
    elif args.action == "down":
        command.append("down")
    else:
        command.extend(("config", "--quiet"))
    try:
        return subprocess.run(command, cwd=HERE.parent, env=environment, check=False).returncode
    except OSError as exc:
        print(f"SWARM Console Docker error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
