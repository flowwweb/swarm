from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


SERVER = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("rush_console_tested", SERVER)
assert SPEC and SPEC.loader
console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console)


class RushConsoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.codex_home = self.root / "codex"
        self.codex_home.mkdir()
        self.config = self.root / "rush" / "config.toml"
        self.config.parent.mkdir()
        source = console.PLUGIN_ROOT / "skills" / "rush" / "assets" / "rush-config.toml"
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
            ("root", "Unformatted project request", "C:/work/alpha", now, now, "gpt-5.6-sol", "high", 100),
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
        self.assertNotIn("root", ids)
        self.assertEqual(overview["analytics"]["tasks"], 3)
        self.assertEqual(overview["analytics"]["tokens"], 650)
        self.assertTrue(all(project["id"].startswith("project:") for project in overview["projects"]))
        self.assertFalse(any("C:/" in json.dumps(item) for item in overview["projects"]))
        self.assertIn({"source": "lead", "target": "task"}, overview["links"])
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "review")["status"], "done")

    def test_valid_config_update_is_validated_and_backed_up(self) -> None:
        result = console.update_config(self.config, {"monitoring.heartbeat_minutes": 45})
        self.assertEqual(result["settings"]["monitoring"]["heartbeat_minutes"], 45)
        self.assertTrue(self.config.with_suffix(".toml.rush-console.bak").exists())

    def test_usage_saver_toggle_uses_validated_config_api(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertFalse(before["settings"]["execution"]["usage_saver"])
        self.assertIn("execution.usage_saver", before["editable"])

        result = console.update_config(self.config, {"execution.usage_saver": True})
        self.assertTrue(result["settings"]["execution"]["usage_saver"])

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

    def test_invalid_config_update_preserves_source(self) -> None:
        before = self.config.read_bytes()
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"portfolio.max_active_tasks": 0})
        self.assertEqual(self.config.read_bytes(), before)

    def test_non_editable_setting_is_rejected(self) -> None:
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"feedback.destination": "https://example.invalid"})


if __name__ == "__main__":
    unittest.main()
