from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


LAUNCHER = Path(__file__).resolve().parents[1] / "launcher.py"
SPEC = importlib.util.spec_from_file_location("swarm_console_launcher_tested", LAUNCHER)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def test_task_identity_reaches_existing_claim_and_chrome_gets_new_tab(self) -> None:
        self._write_setting()
        claims = []
        browser = mock.Mock()
        browser.open.return_value = True
        def fetch(url, **kwargs):
            if url.endswith("healthz"):
                return self._matching_health()
            if url.endswith("bootstrap"):
                return {"token": "token"}
            claims.append((url, kwargs))
            return {"should_open": True}
        with mock.patch.object(launcher, "_chrome_browser", return_value=browser):
            result = launcher.ensure_portal(config_path=self.config, codex_home=self.codex_home,
                task_id="exact-task", fetch_json=fetch)
        self.assertTrue(result["opened"])
        self.assertEqual(claims, [("http://127.0.0.1:4788/api/launch-claim?task_id=exact-task", {"token": "token", "method": "POST"})])
        browser.open.assert_called_once_with("http://127.0.0.1:4788", new=2)

    def test_missing_chrome_does_not_consume_task_claim(self) -> None:
        self._write_setting()
        with mock.patch.object(launcher, "_chrome_browser", side_effect=OSError("Chrome unavailable")):
            result = launcher.ensure_portal(config_path=self.config, codex_home=self.codex_home,
                task_id="exact-task", fetch_json=lambda url: self._matching_health())
        self.assertFalse(result["opened"])
        self.assertEqual(result["reason"], "browser_launch_failed")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config.toml"
        self.codex_home = self.root / "codex"
        self.codex_home.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_setting(self, *, auto_start: bool = True, open_on_start: bool = True) -> None:
        self.config.write_text(
            "schema_version = 4\n[console]\n"
            f"auto_start = {str(auto_start).lower()}\n"
            f"open_on_start = {str(open_on_start).lower()}\n",
            encoding="utf-8",
        )

    @staticmethod
    def _matching_health() -> dict[str, object]:
        return {
            "ok": True,
            "instance_id": launcher.console_server.INSTANCE_ID,
            "build_id": launcher.console_server.SERVER_BUILD_ID,
        }

    def test_setting_off_never_probes_starts_or_opens(self) -> None:
        self._write_setting(auto_start=False)
        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=lambda *_args, **_kwargs: self.fail("disabled launcher probed server"),
            spawn_server=lambda *_args: self.fail("disabled launcher started server"),
            open_browser=lambda *_args, **_kwargs: self.fail("disabled launcher opened browser"),
        )
        self.assertEqual(result["reason"], "disabled")

    def test_browser_setting_off_still_reuses_hq_without_opening_a_tab(self) -> None:
        self._write_setting(open_on_start=False)

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz") and url.startswith("http://127.0.0.1:4788"):
                return self._matching_health()
            self.fail(f"browser-disabled launcher requested {url}")

        result = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            spawn_server=lambda *_args: self.fail("existing HQ was not reused"),
            open_browser=lambda *_args, **_kwargs: self.fail("browser-disabled launcher opened a tab"),
        )
        self.assertEqual(result["reason"], "browser_disabled")
        self.assertEqual(result["url"], "http://127.0.0.1:4788")

    def test_enabled_launcher_fails_closed_before_server_or_browser_when_assets_are_missing(self) -> None:
        self._write_setting()
        with mock.patch.object(launcher, "CONSOLE_ROOT", self.root / "missing-console"):
            result = launcher.ensure_portal(
                config_path=self.config,
                codex_home=self.codex_home,
                fetch_json=lambda *_args, **_kwargs: self.fail("asset preflight probed server"),
                spawn_server=lambda *_args: self.fail("asset preflight started server"),
                open_browser=lambda *_args, **_kwargs: self.fail("asset preflight opened browser"),
            )
        self.assertEqual(result["reason"], "console_assets_missing")
        self.assertEqual(result["missing"], ("index.html", "app.js", "styles.css"))

    def test_live_server_and_fresh_presence_skip_open(self) -> None:
        self._write_setting()
        calls: list[str] = []

        def fetch(url: str, **_kwargs):
            calls.append(url)
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return self._matching_health()
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

    def test_repeated_autostart_reuses_the_persisted_server_without_a_second_spawn(self) -> None:
        self._write_setting(open_on_start=False)
        running = False
        spawns: list[int] = []

        def fetch(url: str, **_kwargs):
            if not url.endswith("healthz"):
                self.fail(f"browser-disabled autostart requested {url}")
            if running and url.startswith("http://127.0.0.1:4788"):
                return self._matching_health()
            raise OSError("not running")

        def spawn(_config: Path, _codex_home: Path, port: int) -> int:
            nonlocal running
            running = True
            spawns.append(port)
            return 2468

        first = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            spawn_server=spawn,
            open_browser=lambda *_args, **_kwargs: self.fail("browser-disabled autostart opened a tab"),
            sleep=lambda _seconds: None,
        )
        second = launcher.ensure_portal(
            config_path=self.config,
            codex_home=self.codex_home,
            fetch_json=fetch,
            spawn_server=spawn,
            open_browser=lambda *_args, **_kwargs: self.fail("browser-disabled autostart opened a tab"),
            sleep=lambda _seconds: None,
        )

        self.assertEqual(spawns, [4788])
        self.assertEqual(first["reason"], "browser_disabled")
        self.assertEqual(second["reason"], "browser_disabled")
        self.assertEqual(second["url"], "http://127.0.0.1:4788")

    def test_missing_server_starts_once_and_stale_presence_opens_once(self) -> None:
        self._write_setting()
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
                    return self._matching_health()
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
        self._write_setting()
        spawned = False
        spawns: list[int] = []
        opens: list[str] = []

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": "stale-cache-root"}
                if url.startswith("http://127.0.0.1:4789") and spawned:
                    return self._matching_health()
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

    def test_same_root_old_build_is_not_reused(self) -> None:
        self._write_setting(open_on_start=False)
        spawned = False
        spawns: list[int] = []

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {
                        "ok": True,
                        "instance_id": launcher.console_server.INSTANCE_ID,
                        "build_id": "0" * 16,
                    }
                if url.startswith("http://127.0.0.1:4789") and spawned:
                    return self._matching_health()
                raise OSError("not running")
            self.fail(f"browser-disabled launcher requested {url}")

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
            open_browser=lambda *_args, **_kwargs: self.fail("browser-disabled launcher opened a tab"),
            sleep=lambda _seconds: None,
        )
        self.assertEqual(spawns, [4789])
        self.assertEqual(result["reason"], "browser_disabled")
        self.assertEqual(result["url"], "http://127.0.0.1:4789")

    def test_matching_console_on_fallback_port_is_reused(self) -> None:
        self._write_setting()

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": "stale-cache-root"}
                if url.startswith("http://127.0.0.1:4789"):
                    return self._matching_health()
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
        self._write_setting()
        spawned = False
        spawns: list[int] = []

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return {"ok": True, "instance_id": "stale-cache-root"}
                if url.startswith("http://127.0.0.1:4789"):
                    raise ValueError("another local service returned HTML")
                if url.startswith("http://127.0.0.1:4790") and spawned:
                    return self._matching_health()
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
        self._write_setting()

        def fetch(url: str, **_kwargs):
            if url.endswith("healthz"):
                if url.startswith("http://127.0.0.1:4788"):
                    return self._matching_health()
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
