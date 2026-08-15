from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SERVER = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("swarm_console_tested", SERVER)
assert SPEC and SPEC.loader
console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console)


class SwarmConsoleTests(unittest.TestCase):
    def test_new_console_copy_is_swarm_first(self) -> None:
        static = (Path(__file__).resolve().parents[1] / "static")
        index = (static / "index.html").read_text(encoding="utf-8")
        app = (static / "app.js").read_text(encoding="utf-8")
        self.assertIn('aria-label="SWARM summary metrics"', index)
        self.assertIn('<span>🐙</span>', index)
        self.assertIn('id="controller-filter"', index)
        self.assertIn('aria-label="Swarm"', index)
        self.assertIn("Keep new SWARM owners visible", app)
        self.assertIn('document.visibilityState === "visible"', app)
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.codex_home = self.root / "codex"
        self.codex_home.mkdir()
        self.config = self.root / "swarm" / "config.toml"
        self.config.parent.mkdir()
        source = console.PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-config.toml"
        self.config.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.database = self.codex_home / "state_5.sqlite"
        self.connection = sqlite3.connect(self.database)
        self.connection.executescript(
            """
            CREATE TABLE threads (
              id TEXT PRIMARY KEY, title TEXT, cwd TEXT, created_at INTEGER,
              updated_at INTEGER, created_at_ms INTEGER, updated_at_ms INTEGER,
              model TEXT, reasoning_effort TEXT, tokens_used INTEGER, archived INTEGER,
              git_origin_url TEXT, git_branch TEXT, thread_source TEXT,
              agent_nickname TEXT, agent_role TEXT, is_pinned INTEGER
            );
            CREATE TABLE thread_spawn_edges (
              parent_thread_id TEXT, child_thread_id TEXT, status TEXT
            );
            """
        )
        now = 2_000_000_000_000
        rows = [
            ("root", "🐙CTRL - Ship console", "C:/work/alpha", now, now, "gpt-5.6-sol", "high", 100),
            ("lead", "🧭LEAD - Console", "C:/work/alpha", now, now, "gpt-5.6-terra", "medium", 200),
            ("task", "🔨DEV - Local API", "C:/work/alpha", now, now, "gpt-5.6-luna", "xhigh", 300),
            ("review", "🔍REVIEW - Console proof", "C:/work/alpha", now, now, "gpt-5.6-sol", "high", 150),
            ("unsafe", "Please do this\nwith secret prompt text", "C:/private/path", now, now, "gpt", "low", 999),
        ]
        for thread_id, title, cwd, created, updated, model, effort, tokens in rows:
            self.connection.execute(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (thread_id, title, cwd, created // 1000, updated // 1000, created, updated,
                 model, effort, tokens, 0, "", "main", "", "", "", 0),
            )
        self.connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [("root", "lead", "open"), ("lead", "task", "open"), ("lead", "review", "closed")],
        )
        self.connection.commit()
        self.connection.close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_overview_is_safe_and_hierarchical(self) -> None:
        overview = console.build_overview(self.codex_home, self.config)
        ids = {node["id"] for node in overview["nodes"]}
        self.assertIn("lead", ids)
        self.assertIn("task", ids)
        self.assertIn("review", ids)
        self.assertNotIn("unsafe", ids)
        self.assertIn("root", ids)
        self.assertEqual(overview["analytics"]["tasks"], 4)
        self.assertEqual(overview["analytics"]["tokens"], 750)
        self.assertTrue(all(project["id"].startswith("project:") for project in overview["projects"]))
        self.assertFalse(any("C:/" in json.dumps(item) for item in overview["projects"]))
        self.assertIn({"source": "lead", "target": "task"}, overview["links"])
        self.assertIn({"source": "root", "target": "lead"}, overview["links"])
        ctrl = next(node for node in overview["nodes"] if node["id"] == "root")
        self.assertEqual((ctrl["role"], ctrl["icon"]), ("ctrl", "🐙"))
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "review")["status"], "done")
        self.assertGreaterEqual(overview["observation_window_ms"], 24 * 60 * 60 * 1000)
        self.assertEqual(overview["controllers"][0]["id"], "root")
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "task")["controller_ids"], ["root"])
        self.assertLess(overview["performance"]["data_bytes"], overview["performance"]["budget"]["data_bytes"])
        self.assertEqual(overview["performance"]["budget"]["cache_hit_ms"], 5)

    def test_parent_ctrl_scope_keeps_nested_ctrl_tree_together(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("child-ctrl", "🐙CTRL - Nested recovery", "C:/work/alpha", now // 1000, now, now, now,
                 "gpt-5.6-sol", "high", 40, 0, "", "main", "", "", "", 0),
                ("child-doer", "🔨DEV - Nested repair", "C:/work/alpha", now // 1000, now, now, now,
                 "gpt-5.6-luna", "high", 20, 0, "", "main", "", "", "", 0),
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [("lead", "child-ctrl", "open"), ("child-ctrl", "child-doer", "open")],
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        controllers = {item["id"]: item for item in overview["controllers"]}
        by_id = {node["id"]: node for node in overview["nodes"]}
        self.assertEqual(controllers["root"]["nodes"], 6)
        self.assertEqual(controllers["child-ctrl"]["nodes"], 2)
        self.assertEqual(by_id["child-ctrl"]["controller_ids"], ["root", "child-ctrl"])
        self.assertEqual(by_id["child-doer"]["controller_ids"], ["root", "child-ctrl"])
        self.assertEqual(by_id["lead"]["controller_ids"], ["root"])
        self.assertIn("not the authoritative runtime workflow graph", overview["claim_limits"][1])

    def _handler(self, peer: str, host: str, *, origin: str = "", token: str = "secret"):
        handler = object.__new__(console.Handler)
        handler.client_address = (peer, 41000)
        handler.headers = Message()
        handler.headers["Host"] = host
        if origin:
            handler.headers["Origin"] = origin
        if token:
            handler.headers["X-Swarm-Token"] = token
        handler.server = SimpleNamespace(app=SimpleNamespace(token="secret", config_path=self.config))
        return handler

    def test_remote_peer_cannot_acquire_token_or_write_through_localhost_host(self) -> None:
        handler = self._handler("192.0.2.44", "localhost", token="secret")
        self.assertTrue(handler._host_allowed())
        self.assertFalse(handler._peer_is_loopback())
        self.assertFalse(handler._authorized_write())
        self.assertEqual(handler._bootstrap_payload()["token"], "")
        self.assertEqual(handler._bootstrap_payload()["config_path"], "")
        self.assertTrue(handler._bootstrap_payload()["read_only"])
        self.assertTrue(handler._config_payload()["read_only"])
        self.assertEqual(handler._config_payload()["path"], "")

    def test_write_requires_loopback_peer_allowed_host_origin_and_token(self) -> None:
        self.assertFalse(self._handler("127.0.0.1", "evil.example")._host_allowed())
        self.assertFalse(self._handler("127.0.0.1", "localhost", origin="http://evil.example")._authorized_write())
        self.assertFalse(self._handler("127.0.0.1", "localhost:4788", origin="http://localhost:9999")._authorized_write())
        self.assertFalse(self._handler("127.0.0.1", "localhost", token="wrong")._authorized_write())
        self.assertTrue(self._handler("127.0.0.1", "localhost")._authorized_write())
        self.assertTrue(self._handler("127.0.0.1", "localhost:4788", origin="http://localhost:4788")._authorized_write())
        self.assertTrue(self._handler("127.0.0.1", "192.168.1.10")._host_allowed())

    def test_portal_open_claim_uses_visible_presence_and_bounded_ttl(self) -> None:
        app = console.App(self.codex_home, self.config)
        with mock.patch.object(console.time, "monotonic", return_value=10.0):
            self.assertTrue(app.claim_portal_open()["should_open"])
        with mock.patch.object(console.time, "monotonic", return_value=20.0):
            self.assertEqual(app.claim_portal_open()["reason"], "recent_claim")
            app.mark_presence()
        with mock.patch.object(console.time, "monotonic", return_value=80.0):
            app.mark_presence()
        with mock.patch.object(console.time, "monotonic", return_value=100.0):
            self.assertEqual(app.claim_portal_open()["reason"], "active_tab")
        with mock.patch.object(console.time, "monotonic", return_value=231.0):
            self.assertTrue(app.claim_portal_open()["should_open"])

    def test_hidden_tab_presence_is_cheap_authenticated_and_stops_on_close(self) -> None:
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('document.visibilityState === "hidden"', app)
        self.assertIn('api("/api/presence", { method: "POST" })', app)
        self.assertIn("60_000", app)
        self.assertLess(len(json.dumps({"ok": True}, separators=(",", ":")).encode()), 16)

    def test_overview_cache_rebuilds_only_after_a_host_or_config_change(self) -> None:
        app = console.App(self.codex_home, self.config)
        first = app.overview()
        self.assertIs(first, app.overview())
        self.config.write_text(self.config.read_text(encoding="utf-8") + "\n# updated\n", encoding="utf-8")
        self.assertIsNot(first, app.overview())

    def test_valid_config_update_is_validated_and_backed_up(self) -> None:
        result = console.update_config(self.config, {"monitoring.heartbeat_minutes": 45})
        self.assertEqual(result["settings"]["monitoring"]["heartbeat_minutes"], 45)
        self.assertTrue(self.config.with_suffix(".toml.swarm-console.bak").exists())

    def test_role_icon_controls_preserve_boolean_and_custom_ctrl(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertIn("role_icons.enabled", before["editable"])
        self.assertIn("role_icons.ctrl", before["editable"])
        result = console.update_config(
            self.config,
            {"role_icons.enabled": False, "role_icons.ctrl": "🕹️"},
        )
        self.assertFalse(result["settings"]["role_icons"]["enabled"])
        self.assertEqual(result["settings"]["role_icons"]["ctrl"], "🕹️")

    def test_historical_mother_title_is_a_specialist_under_a_virtual_ctrl_root(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("mother", "🐝MOTHER - Historical route", "C:/work/beta", now // 1000, now, now, now,
                 "gpt-5.6-sol", "high", 20, 0, "", "main", "", "", "", 0),
                ("specialist", "💻DEV - Historical implementation", "C:/work/beta", now // 1000, now, now, now,
                 "gpt-5.6-luna", "high", 30, 0, "", "main", "", "", "", 0),
            ],
        )
        connection.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("mother", "specialist", "open"))
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        mother = next(node for node in overview["nodes"] if node["id"] == "mother")
        virtual_ctrl = next(
            node for node in overview["nodes"] if node["virtual"] and node["project"] == "beta"
        )
        self.assertEqual((mother["role"], mother["role_label"], mother["icon"]), ("specialist", "MOTHER", "🐝"))
        self.assertEqual((virtual_ctrl["role"], virtual_ctrl["role_label"], virtual_ctrl["icon"]), ("ctrl", "CTRL", "🐙"))
        self.assertIn({"source": virtual_ctrl["id"], "target": "mother"}, overview["links"])
        self.assertNotIn("mother", overview["analytics"]["roles"])

    def test_historical_mother_uses_its_configured_specialist_icon(self) -> None:
        self.config.write_text(
            'schema_version = 3\n[roles.MOTHER]\nicon = "🗂️"\n', encoding="utf-8"
        )
        _, effective, _ = console.load_config(self.config)
        mother = console._role_from_title(
            "🐝MOTHER - Historical route",
            effective["labels"],
            effective["role_icons"],
            effective["roles"],
        )
        self.assertEqual((mother["role"], mother["icon"], mother["title"]), ("specialist", "🗂️", "🗂️MOTHER - Historical route"))

    def test_monitoring_copy_is_alert_only_without_a_watchdog_surface(self) -> None:
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("Optional alert-only sensor", app)
        self.assertNotIn("watchdog", app.casefold())
        self.assertNotIn("watchdog", console.EDITABLE_SETTINGS)

    def test_visible_role_titles_are_normalized_by_icon_setting(self) -> None:
        _, enabled, _ = console.load_config(self.config)
        lead = console._role_from_title("LEAD - Console", enabled["labels"], enabled["role_icons"])
        self.assertEqual(lead["title"], "🧭LEAD - Console")
        duplicate = console._role_from_title("🧭🧭LEAD - Console", enabled["labels"], enabled["role_icons"])
        wrong = console._role_from_title("🔥CTRL - Ship console", enabled["labels"], enabled["role_icons"])
        repeated = console._role_from_title("🐙🐙CTRL - Ship console", enabled["labels"], enabled["role_icons"])
        developer = console._role_from_title("🔥DEV - Renderer", enabled["labels"], enabled["role_icons"])
        mother = console._role_from_title("🐝MOTHER - Historical route", enabled["labels"], enabled["role_icons"], enabled["roles"])
        self.assertEqual(duplicate["title"], "🧭LEAD - Console")
        self.assertEqual(wrong["title"], "🐙CTRL - Ship console")
        self.assertEqual(repeated["title"], "🐙CTRL - Ship console")
        self.assertEqual(developer["title"], "💻DEV - Renderer")
        self.assertEqual((mother["role"], mother["title"]), ("specialist", "🐝MOTHER - Historical route"))
        console.update_config(self.config, {"role_icons.enabled": False})
        _, disabled, _ = console.load_config(self.config)
        ctrl = console._role_from_title("🐙CTRL - Ship console", disabled["labels"], disabled["role_icons"])
        self.assertEqual(ctrl["title"], "CTRL - Ship console")
        self.assertEqual(ctrl["icon"], "")

    def test_usage_saver_toggle_uses_validated_config_api(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertFalse(before["settings"]["execution"]["usage_saver"])
        self.assertIn("execution.usage_saver", before["editable"])

        result = console.update_config(self.config, {"execution.usage_saver": True})
        self.assertTrue(result["settings"]["execution"]["usage_saver"])

    def test_portal_start_setting_defaults_on_and_can_be_disabled(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertTrue(before["settings"]["console"]["open_on_start"])
        self.assertIn("console.open_on_start", before["editable"])
        result = console.update_config(self.config, {"console.open_on_start": False})
        self.assertFalse(result["settings"]["console"]["open_on_start"])

    def test_usage_saver_rejects_non_boolean_without_writing(self) -> None:
        before = self.config.read_bytes()
        with self.assertRaisesRegex(console.ConsoleError, "must be a boolean"):
            console.update_config(self.config, {"execution.usage_saver": "yes"})
        self.assertEqual(self.config.read_bytes(), before)

    def test_usage_saver_has_one_console_control(self) -> None:
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertEqual(index.count('id="usage-saver-toggle"'), 1)
        self.assertIn('"execution.usage_saver": desired', app)

    def test_console_ui_fixture_is_structurally_valid(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "console-ui.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(set(fixture), {"bootstrap", "config", "overview"})
        self.assertFalse(fixture["config"]["settings"]["execution"]["usage_saver"])
        self.assertIn("execution.usage_saver", fixture["config"]["editable"])
        self.assertTrue(fixture["config"]["settings"]["console"]["open_on_start"])
        self.assertIn("console.open_on_start", fixture["config"]["editable"])

    def test_hierarchy_omits_explanatory_metadata_surfaces(self) -> None:
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("stage-legend", index)
        self.assertNotIn("claim-note", index)
        self.assertNotIn("Recent means", index)

    def test_invalid_config_update_preserves_source(self) -> None:
        before = self.config.read_bytes()
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"portfolio.max_active_tasks": 0})
        self.assertEqual(self.config.read_bytes(), before)

    def test_non_editable_setting_is_rejected(self) -> None:
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"feedback.destination": "https://example.invalid"})

    def test_recovery_attempt_count_is_a_fixed_invariant_not_a_console_control(self) -> None:
        self.assertNotIn("recovery.max_attempts", console.EDITABLE_SETTINGS)
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('"recovery.max_attempts"', app)
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"recovery.max_attempts": 0})


if __name__ == "__main__":
    unittest.main()
