"""Check a source or installed SWARM package on loopback using isolated test state."""
from __future__ import annotations

import argparse
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import urllib.request

from build_package import validate_plugin_manifest


def check(root: Path) -> dict:
    root = root.resolve()
    manifest = validate_plugin_manifest(root)
    spec = importlib.util.spec_from_file_location("swarm_device_launcher", root / "console/launcher.py")
    if spec is None or spec.loader is None:
        raise ValueError("launcher unavailable")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    console = launcher.console_server
    module, config, _ = console.load_config(root / "skills/swarm/assets/swarm-benchmark.toml")
    assignment = module.resolve_model_assignment(config, "doer", surface="codex_task")
    if (assignment["model"], assignment["reasoning_effort"]) != ("gpt-6.1-sol", "xhigh"):
        raise ValueError("benchmark assignment drift")
    def unexpected_spawn(*_):
        raise ValueError("running server was not reused")

    opens = []
    with tempfile.TemporaryDirectory(prefix="swarm-smoke-") as directory:
        home = Path(directory)
        config_path = home / "config.toml"
        config_path.write_text('[console]\nauto_start = true\nopen_on_start = true\n', encoding="utf-8")
        with closing(sqlite3.connect(home / "state_5.sqlite")) as db:
            db.execute("CREATE TABLE threads(id TEXT PRIMARY KEY, archived INTEGER)")
            db.executemany("INSERT INTO threads VALUES (?, 0)", [("smoke-a",), ("smoke-b",)])
            db.commit()
        for restart in (False, True):
            app = console.App(home, config_path)
            server = console.SwarmHTTPServer(("127.0.0.1", 0), console.Handler, app)
            server.daemon_threads = False  # Join request handlers before removing isolated SQLite state.
            app.http_server = server
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            port = server.server_address[1]
            try:
                for resource in ("/", "/app.js", "/styles.css"):
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}{resource}", timeout=5) as response:
                        if response.status != 200 or not response.read():
                            raise ValueError(f"empty static resource: {resource}")
                def launch(task):
                    return launcher.ensure_portal(config_path=config_path, codex_home=home,
                        port=port, task_id=task,
                        spawn_server=unexpected_spawn,
                        open_browser=lambda url, **_: opens.append(url) or True)
                first = launch("smoke-a")
                if first["opened"] != (not restart):
                    raise ValueError("task claim did not survive restart")
                if launch("smoke-a")["reason"] != "task_already_claimed":
                    raise ValueError("repeated task opened again")
                if not restart:
                    new_task = launch("smoke-b")
                    if not new_task["opened"]:
                        raise ValueError(f"new task did not get its own claim: {new_task}")
                if launch("missing")["ok"]:
                    raise ValueError("unknown task received a browser claim")
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)
                if worker.is_alive():
                    raise RuntimeError("smoke server did not stop")
    if len(opens) != 2:
        raise ValueError("browser dispatch count differs from distinct tasks")
    return {"status": "PASS", "version": manifest["version"], "plugin_root": str(root),
            "checks": ["manifest and shipped icons", "benchmark assignment", "live loopback static files",
                       "server reuse", "distinct task claims", "claim retained across restart", "unknown task rejected"],
            "browser_open_dispatches": len(opens),
            "claim_limit": "Isolated synthetic host metadata. No real browser, agent topology or provider execution."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(check(args.plugin_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
