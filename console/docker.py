#!/usr/bin/env python3
"""Launch the RUSH Console Compose project with portable host paths."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "docker-compose.yml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "down", "config"), nargs="?", default="up")
    parser.add_argument("--detach", action="store_true", help="run the container in the background")
    args = parser.parse_args()
    if not shutil.which("docker"):
        print("RUSH Console Docker error: docker command not found", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment.setdefault("RUSH_CODEX_HOME", str(Path.home() / ".codex"))
    environment.setdefault("RUSH_CONFIG_HOME", str(Path.home() / ".agents" / "rush"))
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
        print(f"RUSH Console Docker error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
