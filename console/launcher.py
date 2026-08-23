#!/usr/bin/env python3
"""Start or reuse the local SWARM portal without blocking SWARM work."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable


CONSOLE_ROOT = Path(__file__).resolve().parent
SERVER_PATH = CONSOLE_ROOT / "server.py"
SPEC = importlib.util.spec_from_file_location("swarm_console_launcher_server", SERVER_PATH)
assert SPEC and SPEC.loader
console_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console_server)
PORT_SCAN_LIMIT = 10


def _request_json(url: str, *, token: str = "", method: str = "GET") -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Swarm-Token"] = token
    request = urllib.request.Request(url, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=0.45) as response:  # noqa: S310 - fixed loopback URL
        return json.loads(response.read())


def _spawn_server(config_path: Path, codex_home: Path, port: int) -> int:
    command = [
        sys.executable,
        str(SERVER_PATH),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--config", str(config_path),
        "--codex-home", str(codex_home),
    ]
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs).pid


def ensure_portal(
    *,
    config_path: Path,
    codex_home: Path,
    port: int = console_server.DEFAULT_PORT,
    fetch_json: Callable[..., dict[str, Any]] = _request_json,
    spawn_server: Callable[[Path, Path, int], int] = _spawn_server,
    open_browser: Callable[..., bool] = webbrowser.open,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Reuse only this console instance and open when no tab has fresh presence."""
    _, effective, _ = console_server.load_config(config_path)
    if not effective["console"]["open_on_start"]:
        return {"ok": True, "enabled": False, "opened": False, "reason": "disabled"}

    selected_port: int | None = None
    free_port: int | None = None
    for candidate_port in range(port, min(65_536, port + PORT_SCAN_LIMIT)):
        candidate_url = f"http://127.0.0.1:{candidate_port}"
        try:
            health = fetch_json(f"{candidate_url}/healthz")
        except (ValueError, urllib.error.HTTPError):
            continue
        except (OSError, urllib.error.URLError):
            if free_port is None:
                free_port = candidate_port
            continue
        if health.get("ok") is True and health.get("instance_id") == console_server.INSTANCE_ID:
            selected_port = candidate_port
            break

    pid: int | None = None
    if selected_port is None:
        if free_port is None:
            return {
                "ok": False,
                "enabled": True,
                "opened": False,
                "reason": "server_port_unavailable",
                "port": port,
            }
        selected_port = free_port
        try:
            pid = spawn_server(config_path, codex_home, selected_port)
        except OSError as exc:
            return {"ok": False, "enabled": True, "opened": False, "reason": "server_start_failed", "error": str(exc)}
        ready_url = f"http://127.0.0.1:{selected_port}/healthz"
        for _ in range(12):
            sleep(0.15)
            try:
                health = fetch_json(ready_url)
            except (OSError, ValueError, urllib.error.URLError):
                continue
            if health.get("ok") is True and health.get("instance_id") == console_server.INSTANCE_ID:
                break
        else:
            return {
                "ok": False,
                "enabled": True,
                "opened": False,
                "reason": "server_not_ready",
                "pid": pid,
                "port": selected_port,
            }

    url = f"http://127.0.0.1:{selected_port}"
    try:
        bootstrap = fetch_json(f"{url}/api/bootstrap")
        claim = fetch_json(f"{url}/api/launch-claim", token=bootstrap["token"], method="POST")
        if not claim["should_open"]:
            return {"ok": True, "enabled": True, "opened": False, "reason": claim["reason"], "url": url, "pid": pid}
        opened = bool(open_browser(url, new=2))
        return {"ok": opened, "enabled": True, "opened": opened, "reason": "open" if opened else "browser_declined", "url": url, "pid": pid}
    except (KeyError, OSError, ValueError, urllib.error.URLError) as exc:
        return {"ok": False, "enabled": True, "opened": False, "reason": "browser_launch_failed", "url": url, "pid": pid, "error": str(exc)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=console_server.DEFAULT_PORT)
    parser.add_argument("--codex-home", type=Path, default=console_server.DEFAULT_CODEX_HOME)
    parser.add_argument("--config", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = ensure_portal(
        config_path=console_server.resolve_config_path(args.config),
        codex_home=args.codex_home.expanduser(),
        port=args.port,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
