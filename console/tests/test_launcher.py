from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parents[1] / "launcher.py"
SPEC = importlib.util.spec_from_file_location("swarm_console_launcher_tested", LAUNCHER)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config.toml"
        self.codex_home = self.root / "codex"
        self.codex_home.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_setting(self, enabled: bool) -> None:
        self.config.write_text(f"schema_version = 3\n[console]\nopen_on_start = {str(enabled).lower()}\n", encoding="utf-8")

    def test_setting_off_never_probes_starts_or_opens(self) -> None:
        self._write_setting(False)
        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=lambda *_args, **_kwargs: self.fail("disabled launcher probed server"),
            spawn_server=lambda *_args: self.fail("disabled launcher started server"),
            open_browser=lambda *_args, **_kwargs: self.fail("disabled launcher opened browser"),
        )
        self.assertEqual(result["reason"], "disabled")

    def test_live_server_and_fresh_presence_skip_open(self) -> None:
        self._write_setting(True)
        calls: list[str] = []

        def fetch(url: str, **_kwargs):
            calls.append(url)
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": launcher.console_server.INSTANCE_ID}
                raise OSError("not running")
            if url.endswith("bootstrap"):
                return {"token": "token"}
            return {"should_open": False, "reason": "active_tab"}

        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            spawn_server=lambda *_args: self.fail("existing server was not reused"),
            open_browser=lambda *_args, **_kwargs: self.fail("fresh tab opened duplicate"),
        )
        self.assertEqual(result["reason"], "active_tab")
        self.assertEqual(len(calls), 3)

    def test_missing_server_starts_once_and_stale_presence_opens_once(self) -> None:
        self._write_setting(True)
        health_calls = 0
        opens: list[str] = []
        spawns: list[int] = []

        def fetch(url: str, **_kwargs):
            nonlocal health_calls
            if url.endswith("healthz"):
                health_calls += 1
                if health_calls == 1:
                    raise OSError("not running")
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": launcher.console_server.INSTANCE_ID}
                raise OSError("not running")
            if url.endswith("bootstrap"):
                return {"token": "token"}
            return {"should_open": True, "reason": "open"}

        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            spawn_server=lambda *_args: spawns.append(2468) or 2468,
            open_browser=lambda url, **_kwargs: opens.append(url) or True,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(spawns, [2468])
        self.assertEqual(opens, ["http://127.0.0.1:4788"])
        self.assertTrue(result["opened"])

    def test_stale_cache_server_uses_next_free_port(self) -> None:
        self._write_setting(True)
        spawned = False
        spawns: list[int] = []
        opens: list[str] = []

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": "stale-cache-root"}
                if url.startswith("http://127.0.0.1:4789") and spawned:
                    return {"ok": True, "instance_id": launcher.console_server.INSTANCE_ID}
                raise OSError("not running")
            if url.endswith("bootstrap"):
                return {"token": "token"}
            return {"should_open": True, "reason": "open"}

        def spawn(_config: Path, _codex_home: Path, port: int) -> int:
            nonlocal spawned
            spawned = True
            spawns.append(port)
            return 2468

        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            spawn_server=spawn,
            open_browser=lambda url, **_kwargs: opens.append(url) or True,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(spawns, [4789])
        self.assertEqual(opens, ["http://127.0.0.1:4789"])
        self.assertTrue(result["opened"])

    def test_matching_console_on_fallback_port_is_reused(self) -> None:
        self._write_setting(True)

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": "stale-cache-root"}
                if url.startswith("http://127.0.0.1:4789"):
                    return {"ok": True, "instance_id": launcher.console_server.INSTANCE_ID}
            if url.endswith("bootstrap"):
                return {"token": "token"}
            return {"should_open": False, "reason": "active_tab"}

        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            spawn_server=lambda *_args: self.fail("matching fallback server was not reused"),
            open_browser=lambda *_args, **_kwargs: self.fail("fresh tab opened duplicate"),
        )
        self.assertEqual(result["reason"], "active_tab")
        self.assertEqual(result["url"], "http://127.0.0.1:4789")

    def test_non_json_service_is_not_treated_as_a_free_port(self) -> None:
        self._write_setting(True)
        spawned = False
        spawns: list[int] = []

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": "stale-cache-root"}
                if url.startswith("http://127.0.0.1:4789"):
                    raise ValueError("another local service returned HTML")
                if url.startswith("http://127.0.0.1:4790") and spawned:
                    return {"ok": True, "instance_id": launcher.console_server.INSTANCE_ID}
                raise OSError("not running")
            if url.endswith("bootstrap"):
                return {"token": "token"}
            return {"should_open": True, "reason": "open"}

        def spawn(_config: Path, _codex_home: Path, port: int) -> int:
            nonlocal spawned
            spawned = True
            spawns.append(port)
            return 2468

        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            spawn_server=spawn,
            open_browser=lambda *_args, **_kwargs: True,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(spawns, [4790])
        self.assertEqual(result["url"], "http://127.0.0.1:4790")

    def test_browser_failure_is_reported_without_raising(self) -> None:
        self._write_setting(True)

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": launcher.console_server.INSTANCE_ID}
                raise OSError("not running")
            if url.endswith("bootstrap"):
                return {"token": "token"}
            return {"should_open": True, "reason": "open"}

        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            open_browser=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("no browser")),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "browser_launch_failed")


if __name__ == "__main__":
    unittest.main()
