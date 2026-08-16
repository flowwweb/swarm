#!/usr/bin/env python3
"""Select the smallest CI proof graph for an exact Git diff."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path, PurePosixPath


ZERO_SHA = "0" * 40


def _matches(path: str, prefixes: tuple[str, ...], exact: tuple[str, ...] = ()) -> bool:
    return path in exact or any(path.startswith(prefix) for prefix in prefixes)


def select_scope(paths: tuple[str, ...], *, full: bool = False) -> dict[str, bool]:
    """Return monotonic proof requirements; unknown surfaces fail broad."""
    if full or not paths:
        return {"console_ui_required": True, "platform_required": True, "package_required": True}

    console_ui = False
    platform = False
    package = False
    known = True
    for raw in paths:
        path = PurePosixPath(raw.replace("\\", "/")).as_posix().lstrip("./")
        if not path or path.startswith("plugins/swarm/"):
            # Generated mirror parity is checked in the fast tier; canonical paths
            # select the expensive proof that produced the mirror.
            continue
        if _matches(path, ("console/static/",), (
            "console/tests/test_console_ui.mjs",
            "console/package.json",
            "console/package-lock.json",
            "skills/swarm/assets/swarm-wordmark.png",
        )):
            console_ui = True
        if _matches(path, ("console/",), ()):
            platform = platform or path in {
                "console/server.py", "console/launcher.py", "console/docker.py",
                "console/Dockerfile", "console/docker-compose.yml",
            }
        if _matches(path, (".github/workflows/",), ()) or path in {
            "scripts/select_ci_scope.py", "scripts/run_test_tier.py",
            "scripts/build_package.py", "skills/swarm/scripts/verify_plugin_install.py",
            "skills/swarm/tests/test_release_package.py", ".codex-plugin/plugin.json",
            ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
            ".agents/plugins/marketplace.json", "gemini-extension.json",
            "skills/swarm/runtime/core.py", "skills/swarm/runtime/__init__.py",
            "skills/swarm/scripts/swarm_config.py", "skills/swarm/assets/swarm-config.toml",
        }:
            platform = True
            package = True
        elif _matches(path, (
            "skills/swarm/", "console/", "docs/", "scripts/",
        ), ()) or path in {
            "README.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE",
            ".gitignore", ".gitattributes", ".dockerignore",
        }:
            pass
        else:
            known = False

    if not known:
        return {"console_ui_required": True, "platform_required": True, "package_required": True}
    return {
        "console_ui_required": console_ui,
        "platform_required": platform,
        "package_required": package,
    }


def changed_paths(root: Path, base: str, head: str) -> tuple[str, ...]:
    if not base or base == ZERO_SHA or not head:
        return ()
    completed = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=ACDMRTUXB", base, head, "--"],
        check=True, capture_output=True, text=True,
    )
    return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = () if args.full else changed_paths(root, args.base, args.head)
    scope = select_scope(paths, full=args.full or not paths)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8", newline="\n") as handle:
            for key, value in scope.items():
                handle.write(f"{key}={'true' if value else 'false'}\n")
    print(json.dumps({"paths": paths, **scope}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
