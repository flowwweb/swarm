from __future__ import annotations

import importlib.util
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
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
        self.assertIn('src="/assets/swarm-wordmark.png"', index)
        for view in ("overview", "hierarchy", "kanban", "diagnostics", "settings"):
            self.assertIn(f'id="tab-{view}"', index)
            self.assertIn(f'id="view-{view}"', index)
        self.assertIn('id="project-navigation"', index)
        self.assertIn('id="scope-context"', index)
        self.assertIn("function renderProjectNavigation()", app)
        self.assertIn("function renderHierarchy()", app)
        self.assertIn("function renderKanban()", app)
        self.assertIn("function renderDiagnostics()", app)
        self.assertIn("function renderSettings()", app)
        self.assertIn("function publicLabel(value", app)
        self.assertIn(r'.replace(/\blocalhost\b/gi, "console")', app)
        self.assertIn('const label = rawLabel.localeCompare(group.label', app)
        self.assertIn("if (!group.standalone) options.push", app)
        self.assertIn("Health and capacity", index)
        self.assertNotIn("localhost", index.casefold())
        self.assertNotIn("hidden usage", index.casefold())
        self.assertNotIn("do not consume task or model usage", index.casefold())
        self.assertNotIn("Awaiting v3 direction", index)
        self.assertNotIn('id="controller-filter"', index)
        self.assertNotIn('aria-label="Graph"', index)
        self.assertEqual(index.count('id="view-title"'), 1)

    def test_wordmark_uses_exact_existing_asset_route(self) -> None:
        asset, content_type = console.STATIC_ASSETS["/assets/swarm-wordmark.png"]
        self.assertEqual(asset, console.PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-wordmark.png")
        self.assertEqual(content_type, "image/png")
        self.assertTrue(asset.is_file())
        self.assertGreater(asset.stat().st_size, 100_000)

    def test_console_uses_compact_swarm_favicon_not_wordmark(self) -> None:
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        favicon = (console.STATIC_ROOT / "swarm-favicon.svg").read_text(encoding="utf-8")
        self.assertIn('<link rel="icon" type="image/svg+xml" href="/swarm-favicon.svg" />', index)
        self.assertNotIn('rel="icon" href="/assets/swarm-wordmark.png"', index)
        self.assertEqual(console.STATIC_FILES["/swarm-favicon.svg"], ("swarm-favicon.svg", "image/svg+xml"))
        self.assertIn('viewBox="0 0 128 128"', favicon)
        self.assertIn('linearGradient id="coral"', favicon)

    def test_console_uses_flowwweb_swarm_tokens_without_lime_controls(self) -> None:
        css = (console.STATIC_ROOT / "styles.css").read_text(encoding="utf-8").casefold()
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        for token in ("#030712", "#46dfd0", "#ff7449"):
            self.assertIn(token, css)
        for stale in ("#a8ff4f", "168,255,79", "#8ef2c2"):
            self.assertNotIn(stale, css)
        self.assertIn(".toggle-row input", css)
        self.assertIn("accent-color:var(--cyan)", css)
        for removed in ("One CTRL", "RAPID UNIFIED", "LIVE HIERARCHY", "Observed pulse"):
            self.assertNotIn(removed, index)
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
        self.assertIn({"source": "lead", "target": "task", "relationship": "delegated"}, overview["links"])
        self.assertIn({"source": "root", "target": "lead", "relationship": "delegated"}, overview["links"])
        observed_edges = {("root", "lead"), ("lead", "task"), ("lead", "review")}
        self.assertTrue(all((link["source"], link["target"]) in observed_edges for link in overview["links"]))
        ctrl = next(node for node in overview["nodes"] if node["id"] == "root")
        self.assertEqual((ctrl["role"], ctrl["icon"]), ("ctrl", "🐙"))
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "review")["status"], "done")
        self.assertGreaterEqual(overview["observation_window_ms"], 24 * 60 * 60 * 1000)
        self.assertEqual(overview["controllers"][0]["id"], "root")
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "task")["controller_ids"], ["root"])
        self.assertTrue(all(node["role_label"] == "TASK" for node in overview["nodes"] if node["role"] != "ctrl"))
        self.assertEqual(next(node for node in overview["nodes"] if node["id"] == "review")["worker_role"], "REVIEW")
        self.assertEqual(ctrl["proof_snapshot"]["state"], "UNAVAILABLE")
        self.assertIn("host activity is not proof", ctrl["proof_snapshot"]["claim_limit"].lower())
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
        self.assertTrue(any("not the authoritative runtime workflow graph" in claim for claim in overview["claim_limits"]))

    def test_ctrl_includes_unlabelled_host_descendants_without_exposing_prompt_title(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.execute("ALTER TABLE threads ADD COLUMN agent_path TEXT")
        raw_title = "<codex_delegation>\nprivate task instructions\n</codex_delegation>"
        connection.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("generic-child", raw_title, "C:/work/alpha", now // 1000, now // 1000, now, now,
             "gpt-5.6-terra", "high", 25, 0, "", "main", "subagent", "Lovelace", "", 0, "/root/generic_child"),
        )
        connection.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("root", "generic-child", "open"))
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        child = next(node for node in overview["nodes"] if node["id"] == "generic-child")
        self.assertEqual((child["role"], child["role_label"], child["worker_role"], child["artifact"], child["worker"]), ("doer", "TASK", "AGENT", "Generic Child", "Lovelace"))
        self.assertEqual(child["surface"], "subagent")
        self.assertTrue(child["is_subagent"])
        self.assertEqual(child["parent_id"], "root")
        self.assertEqual(child["reasoning"], "high")
        self.assertNotIn("private task instructions", json.dumps(overview))
        self.assertIn({"source": "root", "target": "generic-child", "relationship": "delegated"}, overview["links"])

    def test_unformatted_agent_tree_uses_project_name_without_exposing_private_titles(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.execute("ALTER TABLE threads ADD COLUMN agent_path TEXT")
        columns = "id,title,cwd,created_at,updated_at,created_at_ms,updated_at_ms,model,reasoning_effort,tokens_used,archived,git_origin_url,git_branch,thread_source,agent_nickname,agent_role,is_pinned,agent_path"
        connection.executemany(
            f"INSERT INTO threads ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("plain-root", "A long user request that must never render\nwith private detail", "C:/work/current", now // 1000, now // 1000, now, now, "gpt-5.6-sol", "high", 10, 0, "", "main", "", "", "", 0, ""),
                ("plain-lead", "<codex_delegation>private lead prompt</codex_delegation>", "C:/work/current", now // 1000, now // 1000, now, now, "gpt-5.6-terra", "high", 10, 0, "", "main", "subagent", "Carson", "", 0, "/root/portal_lead"),
                ("plain-lead-replacement", "<codex_delegation>replacement prompt</codex_delegation>", "C:/work/current", now // 1000, now // 1000, now, now + 1, "gpt-5.6-terra", "high", 10, 0, "", "main", "subagent", "Darwin", "", 0, "/root/portal_lead"),
                ("old-child", "<codex_delegation>old prompt</codex_delegation>", "C:/work/current", 1, 1, 1_000, 1_000, "gpt-5.6-terra", "high", 10, 0, "", "main", "subagent", "Old", "", 0, "/root/old_lane"),
            ],
        )
        connection.executemany(
            "INSERT INTO thread_spawn_edges VALUES (?,?,?)",
            [("plain-root", "plain-lead", "closed"), ("plain-root", "plain-lead-replacement", "open"), ("plain-root", "old-child", "closed")],
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        root = next(node for node in overview["nodes"] if node["id"] == "plain-root")
        lead = next(node for node in overview["nodes"] if node["id"] == "plain-lead-replacement")
        controller = next(item for item in overview["controllers"] if item["id"] == "plain-root")
        self.assertEqual((root["role_label"], root["artifact"]), ("CTRL", "current"))
        self.assertEqual((lead["role"], lead["role_label"], lead["worker_role"], lead["artifact"], lead["worker"]), ("lead", "TASK", "LEAD", "Portal", "Darwin"))
        self.assertNotIn("plain-lead", {node["id"] for node in overview["nodes"]})
        self.assertEqual(controller["older_lanes_omitted"], 1)
        self.assertNotIn("private lead prompt", json.dumps(overview))
        self.assertNotIn("old prompt", json.dumps(overview))

    def test_unformatted_fresh_spawn_tree_is_an_observed_controller_without_agent_path(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.execute("ALTER TABLE threads ADD COLUMN agent_path TEXT")
        columns = "id,title,cwd,created_at,updated_at,created_at_ms,updated_at_ms,model,reasoning_effort,tokens_used,archived,git_origin_url,git_branch,thread_source,agent_nickname,agent_role,is_pinned,agent_path"
        connection.executemany(
            f"INSERT INTO threads ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("plain-project-root", "private user objective", "C:/work/nemo", now // 1000, now // 1000, now, now, "gpt-5.6-sol", "high", 10, 0, "https://github.com/flowwweb/nemo.git", "main", "", "", "", 0, ""),
                ("plain-project-child", "<codex_delegation>private child prompt</codex_delegation>", "C:/work/nemo", now // 1000, now // 1000, now, now, "gpt-5.6-terra", "high", 5, 0, "https://github.com/flowwweb/nemo.git", "main", "subagent", "Turing", "", 0, ""),
            ],
        )
        connection.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("plain-project-root", "plain-project-child", "open"))
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        by_id = {node["id"]: node for node in overview["nodes"]}
        self.assertEqual((by_id["plain-project-root"]["role"], by_id["plain-project-root"]["artifact"]), ("ctrl", "nemo"))
        self.assertEqual((by_id["plain-project-child"]["artifact"], by_id["plain-project-child"]["worker"]), ("Assigned Task", "Turing"))
        self.assertNotIn("private user objective", json.dumps(overview))
        self.assertNotIn("private child prompt", json.dumps(overview))

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

    def test_docker_bridge_peer_is_local_only_when_explicitly_enabled(self) -> None:
        handler = self._handler("172.18.0.1", "127.0.0.1:4788", origin="http://127.0.0.1:4788")
        self.assertFalse(handler._peer_is_trusted_local())
        with mock.patch.dict(console.os.environ, {"SWARM_CONSOLE_DOCKER_LOOPBACK": "1"}):
            self.assertTrue(handler._peer_is_trusted_local())
            self.assertTrue(handler._authorized_write())
            self.assertFalse(handler._bootstrap_payload()["read_only"])

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
        self.assertIn("proof_sequence", app)
        self.assertIn("60_000", app)
        self.assertLess(len(json.dumps({"ok": True, "proof_sequence": 0}, separators=(",", ":")).encode()), 48)

    def test_overview_cache_rebuilds_when_the_observer_reports_a_host_change(self) -> None:
        app = console.App(self.codex_home, self.config)
        first = app.overview()
        self.assertIs(first, app.overview())
        self.config.write_text(self.config.read_text(encoding="utf-8") + "\n# updated\n", encoding="utf-8")
        app.observe_once("state_change")
        self.assertIsNot(first, app.overview())

    def test_recent_active_goal_identifies_ctrl_without_reading_objective_text(self) -> None:
        goals = sqlite3.connect(self.codex_home / "goals_1.sqlite")
        goals.execute(
            "CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY, goal_id TEXT, objective TEXT, status TEXT, token_budget INTEGER, tokens_used INTEGER, time_used_seconds INTEGER, created_at_ms INTEGER, updated_at_ms INTEGER)"
        )
        goals.execute(
            "INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)",
            ("unsafe", "goal-1", "private objective must never render", "active", None, 0, 0, 2_000_000_000_000, 2_000_000_000_000),
        )
        goals.commit()
        goals.close()

        overview = console.build_overview(self.codex_home, self.config)
        node = next(node for node in overview["nodes"] if node["id"] == "unsafe")
        self.assertEqual((node["role"], node["artifact"]), ("ctrl", "path"))
        self.assertNotIn("private objective", json.dumps(overview))

    def test_goal_database_change_invalidates_cached_overview(self) -> None:
        goals = sqlite3.connect(self.codex_home / "goals_1.sqlite")
        goals.execute(
            "CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY, goal_id TEXT, objective TEXT, status TEXT, token_budget INTEGER, tokens_used INTEGER, time_used_seconds INTEGER, created_at_ms INTEGER, updated_at_ms INTEGER)"
        )
        goals.commit()
        goals.close()
        app = console.App(self.codex_home, self.config)
        first = app.overview()
        goals = sqlite3.connect(self.codex_home / "goals_1.sqlite")
        goals.execute(
            "INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)",
            ("unsafe", "goal-2", "private", "active", None, 0, 0, 2_000_000_000_000, 2_000_000_000_000),
        )
        goals.commit()
        goals.close()
        app.observe_once("state_change")
        self.assertIsNot(first, app.overview())

    def test_console_store_survives_restart_and_clamps_counter_resets(self) -> None:
        path = self.root / "console" / "console-state.sqlite3"
        now = int(time.time() * 1000)
        overview = {
            "heartbeat_minutes": 30,
            "nodes": [{
                "id": "thread-1", "project_id": "project:alpha", "tokens": 100,
                "status": "active", "updated_at": now,
            }],
            "links": [],
        }
        store = console.ConsoleStore(path)
        store.observe_overview(overview, now_ms=now, trigger="startup", heartbeat_minutes=30)
        overview["nodes"][0]["tokens"] = 100
        store.observe_overview(overview, now_ms=now + 61_000, trigger="heartbeat", heartbeat_minutes=30)
        overview["nodes"][0]["tokens"] = 90
        store.observe_overview(overview, now_ms=now + 122_000, trigger="heartbeat", heartbeat_minutes=30)
        store.observe_overview(overview, now_ms=now + 183_000, trigger="heartbeat", heartbeat_minutes=30)
        overview["nodes"][0]["tokens"] = 130
        store.observe_overview(overview, now_ms=now + 244_000, trigger="state_change", heartbeat_minutes=30)
        restarted = console.ConsoleStore(path)
        history = restarted.token_history(hours=24)
        self.assertEqual(sum(item["delta_tokens"] for item in history), 30)
        self.assertEqual(restarted.storage_stats()["counts"]["token_samples"], 5)
        connection = sqlite3.connect(path)
        try:
            cursor = connection.execute(
                "SELECT cumulative_tokens FROM token_cursors WHERE thread_id='thread-1'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(cursor[0], 130)

    def test_codex_jsonl_token_counts_are_high_water_deduped(self) -> None:
        session = self.codex_home / "sessions" / "2026" / "08" / "22" / "rollout-thread-1.jsonl"
        session.parent.mkdir(parents=True)

        def append_event(usage: dict[str, int]) -> None:
            with session.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "type": "event_msg",
                    "payload": {"type": "token_count", "info": {"total_token_usage": usage}},
                }) + "\n")

        append_event({"input_tokens": 8, "output_tokens": 4})
        store = console.ConsoleStore(self.root / "console" / "console-state.sqlite3")
        overview = {
            "heartbeat_minutes": 30,
            "nodes": [{
                "id": "thread-1", "project_id": "project:alpha", "tokens": 0,
                "status": "active", "updated_at": 2_000_000_000_000,
            }],
            "links": [],
        }
        store.observe_overview(
            overview, now_ms=2_000_000_000_000, trigger="startup", heartbeat_minutes=30,
            codex_home=self.codex_home,
        )
        append_event({"input_tokens": 10, "output_tokens": 8, "total_tokens": 18})
        append_event({"input_tokens": 9, "output_tokens": 6, "total_tokens": 15})
        store.observe_overview(
            overview, now_ms=2_000_000_061_000, trigger="heartbeat", heartbeat_minutes=30,
            codex_home=self.codex_home,
        )
        store.observe_overview(
            overview, now_ms=2_000_000_122_000, trigger="heartbeat", heartbeat_minutes=30,
            codex_home=self.codex_home,
        )

        history = store.token_history(hours=24)
        self.assertEqual(sum(item["delta_tokens"] for item in history), 6)
        self.assertEqual({item["source"] for item in history}, {"codex_jsonl_token_count"})
        connection = sqlite3.connect(self.root / "console" / "console-state.sqlite3")
        try:
            cursor = connection.execute(
                "SELECT cumulative_tokens FROM token_cursors WHERE thread_id='thread-1'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(cursor[0], 18)

    def test_active_standalone_task_remains_visible_without_ctrl_or_parent(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("standalone", "🔨DEV - Standalone task", "C:/work/standalone", now // 1000, now, now, now,
             "gpt-5.6-luna", "high", 12, 0, "", "main", "", "", "", 0),
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        standalone = next(node for node in overview["nodes"] if node["id"] == "standalone")
        self.assertEqual(standalone["role_label"], "TASK")
        self.assertIsNone(standalone["parent_id"])
        self.assertEqual(standalone["controller_ids"], [])
        self.assertEqual(next(project for project in overview["projects"] if project["id"] == standalone["project_id"])["nodes"], 1)

    def test_usage_history_validates_project_and_ctrl_scopes_without_observing(self) -> None:
        app = console.App(self.codex_home, self.config)
        overview = {
            "nodes": [
                {"id": "ctrl-a", "project_id": "project:a", "role": "ctrl", "virtual": False, "controller_ids": ["ctrl-a"]},
                {"id": "task-a", "project_id": "project:a", "role": "doer", "virtual": False, "controller_ids": ["ctrl-a"]},
                {"id": "ctrl-b", "project_id": "project:b", "role": "ctrl", "virtual": False, "controller_ids": ["ctrl-b"]},
            ],
        }
        history = [{"bucket_ms": 1, "delta_tokens": 7, "source": "host_reported_cumulative_delta"}]
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(app.store, "token_history", return_value=history) as token_history, \
             mock.patch.object(app.store, "token_sample_thread_count", return_value=1), \
             mock.patch.object(app, "observe_once", side_effect=AssertionError("usage observation")):
            result = app.usage_history(project_id="ctrl:ctrl-a", hours=24)
            all_projects = app.usage_history(hours=24)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage"], {"observed_threads": 1, "expected_threads": 2})
        self.assertEqual(all_projects["status"], "partial")
        self.assertEqual(all_projects["coverage"], {"observed_threads": 1, "expected_threads": 3})
        self.assertEqual(result["total_tokens"], 7)
        self.assertEqual(set(result["status_claim"]), {"no_data", "partial", "ok"})
        token_history.assert_has_calls([
            mock.call(project_id=None, thread_ids={"ctrl-a", "task-a"}, hours=24),
            mock.call(project_id=None, thread_ids=None, hours=24),
        ])
        self.assertEqual(token_history.call_count, 2)
        with mock.patch.object(app, "_host_overview", return_value=overview):
            with self.assertRaises(console.ConsoleError):
                app.usage_history(project_id="missing", hours=24)
            with self.assertRaises(console.ConsoleError):
                app.usage_history(project_id="project:a", ctrl_id="ctrl-b", hours=24)
            with self.assertRaises(console.ConsoleError):
                app.usage_history(hours=2)

    def test_usage_forecast_requires_explicit_inputs_and_observed_rate(self) -> None:
        app = console.App(self.codex_home, self.config)
        overview = {
            "nodes": [
                {"id": "ctrl-a", "project_id": "project:a", "role": "ctrl", "virtual": False, "controller_ids": ["ctrl-a"]},
            ],
        }
        one_hour_history = [
            {"bucket_ms": 1_000_000, "delta_tokens": 200, "source": "codex_jsonl_token_count"},
            {"bucket_ms": 1_060_000, "delta_tokens": 100, "source": "codex_jsonl_token_count"},
        ]
        twelve_hour_history = [
            {"bucket_ms": 800_000, "delta_tokens": 100, "source": "codex_jsonl_token_count"},
            {"bucket_ms": 1_100_000, "delta_tokens": 100, "source": "codex_jsonl_token_count"},
        ]
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(
                 app.store,
                 "token_history",
                 side_effect=[one_hour_history, one_hour_history, twelve_hour_history],
             ), \
             mock.patch.object(app.store, "token_sample_thread_count", return_value=1), \
             mock.patch.object(console.time, "time", return_value=1_100):
            missing = app.usage_history(hours=1)
            one_hour = app.usage_history(
                hours=1,
                target_reset_at_ms=2_000_000,
                remaining_token_budget=600,
            )
            twelve_hours = app.usage_history(
                hours=12,
                target_reset_at_ms=2_000_000,
                remaining_token_budget=600,
            )
        self.assertEqual(missing["forecast"]["status"], "no_data")
        self.assertEqual(missing["forecast"]["exhaustion_at_ms"], None)
        self.assertEqual(
            missing["forecast"]["missing_inputs"],
            ["remaining_token_budget", "target_reset_at_ms"],
        )
        self.assertEqual(one_hour["usage_now"]["tokens"], 300)
        self.assertEqual(one_hour["usage_now"]["sampled_at_ms"], 1_060_000)
        self.assertEqual(one_hour["forecast"]["status"], "estimated")
        self.assertEqual(one_hour["forecast"]["remaining_token_budget"], 600)
        self.assertEqual(one_hour["forecast"]["remaining_tokens"], 600)
        self.assertEqual(one_hour["forecast"]["exhaustion_at_ms"], 1_220_000)
        self.assertTrue(one_hour["forecast"]["exhausts_before_reset"])
        self.assertEqual(twelve_hours["forecast"]["remaining_token_budget"], 600)
        self.assertEqual(twelve_hours["forecast"]["remaining_tokens"], 600)
        self.assertNotEqual(one_hour["tokens_per_minute"], twelve_hours["tokens_per_minute"])
        self.assertNotEqual(
            one_hour["forecast"]["exhaustion_at_ms"],
            twelve_hours["forecast"]["exhaustion_at_ms"],
        )
        self.assertIn("not provider billing", one_hour["forecast"]["claim_limit"])

    def test_usage_forecast_stays_no_data_without_history_or_positive_rate(self) -> None:
        app = console.App(self.codex_home, self.config)
        overview = {"nodes": []}
        with mock.patch.object(app, "_host_overview", return_value=overview), \
             mock.patch.object(app.store, "token_history", return_value=[]), \
             mock.patch.object(app.store, "token_sample_thread_count", return_value=0), \
             mock.patch.object(console.time, "time", return_value=1_000):
            result = app.usage_history(
                hours=24,
                target_reset_at_ms=2_000_000,
                remaining_token_budget=600,
            )
        self.assertEqual(result["usage_now"]["status"], "no_data")
        self.assertIsNone(result["usage_now"]["tokens"])
        self.assertEqual(result["forecast"]["status"], "no_data")
        self.assertIn("usage_history", result["forecast"]["missing_inputs"])
        self.assertIn("positive_observed_rate", result["forecast"]["missing_inputs"])
        with self.assertRaises(console.ConsoleError):
            app.usage_history(hours=24, remaining_token_budget=-1)

    def test_progress_summary_aggregates_only_compatible_receipt_backed_units(self) -> None:
        def measured(
            task_id: str,
            completed: int,
            basis: str = "accepted milestones",
            *,
            plan_id: str = "plan-alpha",
            unit_kind: str = "milestone",
            include_identity: bool = True,
        ) -> dict[str, object]:
            plan_units: dict[str, object] = {
                "total_units": 4,
                "completed_units": completed,
                "basis": basis,
                "observed_at_ms": 1_000 + completed,
            }
            if include_identity:
                plan_units.update({
                    "plan_id": plan_id,
                    "unit_id": f"unit-{task_id}",
                    "unit_kind": unit_kind,
                })
            return {
                "id": task_id,
                "project_id": "project:a",
                "role": "doer",
                "status": "active",
                "virtual": False,
                "is_subagent": False,
                "controller_ids": ["ctrl-a"],
                "eta": {
                    "trigger": "task_owner_report",
                    "receipt_source": f"owner:{task_id}:receipt-{task_id}",
                    "progress_basis": {
                        "receipts": [f"receipt-{task_id}"],
                        "plan_units": plan_units,
                    },
                },
                "proof_snapshot": {"media": []},
            }

        summary = console.App._progress_for_nodes(
            [measured("one", 1), measured("two", 3, basis="reviewed checkpoints")],
            {"type": "ctrl", "ctrl_id": "ctrl-a", "project_id": "project:a"},
        )
        self.assertEqual(summary["progress"]["percent"], 50.0)
        self.assertEqual(summary["progress"]["completed_units"], 4)
        self.assertEqual(summary["progress"]["total_units"], 8)
        self.assertEqual(summary["measurement_status"], "measured")
        self.assertEqual(summary["progress"]["plan_id"], "plan-alpha")
        self.assertEqual(summary["progress"]["unit_kind"], "milestone")
        self.assertEqual(summary["progress"]["unit_ids"], ["unit-one", "unit-two"])
        self.assertEqual(summary["progress"]["basis"], "Receipt-backed plan units")
        self.assertEqual(summary["tasks"][0]["progress"]["source"], "task_owner_report")
        self.assertIn("does not prove", summary["tasks"][0]["progress"]["claim_limit"])
        payload = console.App._progress_payload({
            "nodes": [measured("one", 1), measured("two", 3, basis="reviewed checkpoints")],
            "projects": [{"id": "project:a"}],
            "controllers": [{"id": "ctrl-a", "project_id": "project:a"}],
        })
        self.assertEqual(payload["projects"]["project:a"]["progress"]["percent"], 50.0)
        self.assertEqual(payload["controllers"]["ctrl-a"]["progress"]["percent"], 50.0)

        missing = console.App._progress_for_nodes(
            [measured("one", 1), {**measured("two", 3), "eta": {}}],
            {"type": "project", "project_id": "project:a"},
        )
        self.assertIsNone(missing["progress"])
        self.assertEqual(missing["progress_display"], "Unmeasured")
        self.assertEqual(missing["unmeasured_reason"], "missing_receipt_backed_units")

        heterogeneous = console.App._progress_for_nodes(
            [measured("one", 1), measured("two", 3, plan_id="plan-beta")],
            {"type": "project", "project_id": "project:a"},
        )
        self.assertIsNone(heterogeneous["progress"])
        self.assertEqual(heterogeneous["unmeasured_reason"], "heterogeneous_plan_units")

        missing_identity = console.App._progress_for_nodes(
            [measured("one", 1), measured("two", 3, include_identity=False)],
            {"type": "project", "project_id": "project:a"},
        )
        self.assertIsNone(missing_identity["progress"])
        self.assertEqual(missing_identity["unmeasured_reason"], "missing_receipt_backed_units")

    def test_progress_summary_never_uses_unbound_measurement_or_task_status_as_percentage(self) -> None:
        nodes = [
            {"id": "done", "project_id": "project:a", "role": "doer", "status": "done", "virtual": False, "is_subagent": False, "controller_ids": ["ctrl-a"], "proof_snapshot": {"media": [{"evidence_id": "proof-1"}]}},
            {"id": "blocked", "project_id": "project:a", "role": "doer", "status": "quiet", "virtual": False, "is_subagent": False, "controller_ids": ["ctrl-a"], "eta": {"status": "blocked", "reason": "Dependency is not complete."}, "proof_snapshot": {"media": []}},
            {"id": "forged", "project_id": "project:a", "role": "doer", "status": "active", "virtual": False, "is_subagent": False, "controller_ids": ["ctrl-a"], "progress_measurement": {"total_units": 4, "completed_units": 4, "basis": "caller", "observed_at_ms": 1}},
            {"id": "subagent", "project_id": "project:a", "role": "doer", "status": "done", "virtual": False, "is_subagent": True, "controller_ids": ["ctrl-a"]},
        ]
        summary = console.App._progress_for_nodes(nodes, {"type": "ctrl", "ctrl_id": "ctrl-a", "project_id": "project:a"})
        self.assertEqual(summary["counts"], {"tasks": 3, "completed": 1, "blocked": 1})
        self.assertEqual(summary["tasks"][0]["latest_proof_receipt"], "proof-1")
        self.assertEqual(summary["tasks"][1]["blocker"], "Dependency is not complete.")
        self.assertIsNone(summary["tasks"][2]["progress"])
        self.assertIsNone(summary["progress"])
        self.assertEqual(summary["progress_display"], "Unmeasured")
        self.assertIn("status, token volume, elapsed time", summary["claim_limit"])

    def test_console_usage_route_is_read_only_and_has_no_host_mutation_authority(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('if path == "/api/usage-history":', source)
        self.assertIn('query["target_reset_at_ms"]', source)
        self.assertIn('query["remaining_token_budget"]', source)
        self.assertNotIn('query["token_limit"]', source)
        self.assertIn('if path == "/api/progress":', source)
        for rejected in ("USER_CUSTODY_OPERATIONS", "prepare_user_mutation", "user_custody_receipts"):
            self.assertNotIn(rejected, source)

    def test_eta_heartbeat_without_task_owner_report_never_creates_forecast(self) -> None:
        path = self.root / "console" / "eta.sqlite3"
        now = int(time.time() * 1000)
        overview = {
            "heartbeat_minutes": 1,
            "nodes": [{
                "id": "quiet-task", "project_id": "project:alpha", "tokens": 2,
                "status": "quiet", "updated_at": now - 120_000,
            }],
            "links": [],
        }
        store = console.ConsoleStore(path)
        store.observe_overview(overview, now_ms=now, trigger="startup", heartbeat_minutes=1)
        store.observe_overview(overview, now_ms=now + 61_000, trigger="heartbeat", heartbeat_minutes=1)
        self.assertEqual(store.latest_forecasts(), {})

    def test_elapsed_time_and_token_volume_never_create_eta(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "eta-signals.sqlite3")
        now = int(time.time() * 1000)
        store.observe_overview({
            "heartbeat_minutes": 30,
            "nodes": [
                {"id": "new-task", "project_id": "project:alpha", "tokens": 20, "status": "active", "created_at": now - 20 * 60_000, "updated_at": now},
                {"id": "deep-task", "project_id": "project:alpha", "tokens": 20_000, "status": "active", "created_at": now - 4 * 60 * 60_000, "updated_at": now},
            ],
            "links": [],
        }, now_ms=now, trigger="startup", heartbeat_minutes=30)
        self.assertEqual(store.latest_forecasts(), {})

    def test_read_only_console_views_do_not_observe_or_record_usage(self) -> None:
        app = console.App(self.codex_home, self.config)
        with mock.patch.object(app, "observe_once", side_effect=AssertionError("write path")):
            diagnostics = app.diagnostics()
            overview = app.overview()
        self.assertFalse(diagnostics["usage_consumed"])
        self.assertNotIn("tokens", diagnostics)
        self.assertIn("token_history", overview)

    def test_clear_history_does_not_delete_ctrl_overlays(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "scoped.sqlite3")
        now = int(time.time() * 1000)
        store.update_ctrl_override("ctrl-1", {"reasoning": "high"}, expected_revision=0, now_ms=now)
        store.observe_overview({
            "heartbeat_minutes": 30,
            "nodes": [{"id": "task-1", "project_id": "project:alpha", "tokens": 3, "status": "active", "updated_at": now}],
            "links": [],
        }, now_ms=now, trigger="startup", heartbeat_minutes=30)
        result = store.clear_history()
        self.assertTrue(result["ok"])
        self.assertEqual(store.get_ctrl_override("ctrl-1")["revision"], 1)
        self.assertEqual(store.storage_stats()["counts"]["token_samples"], 0)

    def test_proof_feed_exposes_available_media_without_fabricating_surface(self) -> None:
        media_path = self.root / "proof.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
        store = console.ConsoleStore(self.root / "console" / "proof.sqlite3")
        base = {
            "source": "CtrlEvidence", "evidence_id": "evidence-1", "task_id": "task-1",
            "project_id": "project:alpha", "kind": "screenshot", "locator": str(media_path),
            "caption": "Screenshot proof", "claim_limit": "Local screenshot only.",
            "receipt": "proof-event:evidence-1", "surface_kind": "available_media",
        }
        item = store.record_proof_media({**base, "disposition": "PENDING"}, now_ms=1)
        self.assertEqual(item["evidence_id"], "evidence-1")
        feed_item = store.proof_feed(project_id="project:alpha")[0]
        self.assertEqual(feed_item["media_type"], "image/png")
        self.assertEqual(feed_item["disposition"], "PENDING")
        self.assertNotIn("locator", feed_item)
        self.assertEqual(store.proof_sequence(), 1)
        with self.assertRaises(console.ConsoleError):
            store.record_proof_media({**base, "disposition": "SURFACED"}, now_ms=2)
        with self.assertRaises(console.ConsoleError):
            store.record_proof_media({**base, "caption": "Changed", "disposition": "PENDING"}, now_ms=3)
        with self.assertRaisesRegex(console.ConsoleError, "plain project language"):
            store.record_proof_media({**base, "evidence_id": "internal-copy", "caption": "Localhost proof", "disposition": "PENDING"}, now_ms=4)

    def test_store_migration_normalizes_available_rows_but_preserves_withheld(self) -> None:
        media_path = self.root / "legacy.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\nlegacy")
        database = self.root / "console" / "legacy.sqlite3"
        store = console.ConsoleStore(database)
        item = store.record_proof_media({
            "source": "CtrlEvidence", "evidence_id": "legacy-proof", "task_id": "task-1",
            "project_id": "project:alpha", "kind": "screenshot", "locator": str(media_path),
            "caption": "Legacy proof", "claim_limit": "Available for review.",
            "receipt": "legacy:caller", "disposition": "PENDING",
        }, now_ms=1)
        connection = sqlite3.connect(database)
        try:
            connection.execute("UPDATE proof_media SET disposition='SURFACED', surface_kind='inline_image' WHERE evidence_id='legacy-proof'")
            connection.execute(
                "INSERT INTO proof_media(evidence_id, task_id, project_id, kind, locator, caption, claim_limit, disposition, receipt, surface_kind, media_type, mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms) "
                "SELECT 'available-proof', task_id, project_id, kind, locator, 'Available proof', claim_limit, 'AVAILABLE', 'legacy:available', 'available_media', media_type, mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms FROM proof_media WHERE evidence_id='legacy-proof'"
            )
            connection.execute(
                "INSERT INTO proof_media(evidence_id, task_id, project_id, kind, locator, caption, claim_limit, disposition, receipt, surface_kind, media_type, mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms) "
                "SELECT 'withheld-proof', task_id, project_id, kind, locator, 'Withheld proof', claim_limit, 'WITHHELD', 'ctrl:withheld', 'withheld', media_type, mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms FROM proof_media WHERE evidence_id='legacy-proof'"
            )
            connection.commit()
        finally:
            connection.close()
        migrated = {entry["evidence_id"]: entry for entry in console.ConsoleStore(database).proof_feed()}
        self.assertEqual(migrated["legacy-proof"]["evidence_id"], item["evidence_id"])
        self.assertEqual(migrated["legacy-proof"]["disposition"], "PENDING")
        self.assertEqual(migrated["legacy-proof"]["surface_kind"], "available_media")
        self.assertEqual(migrated["available-proof"]["disposition"], "PENDING")
        self.assertEqual(migrated["available-proof"]["surface_kind"], "available_media")
        connection = sqlite3.connect(database)
        try:
            withheld = connection.execute(
                "SELECT disposition, receipt, surface_kind FROM proof_media WHERE evidence_id='withheld-proof'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(withheld, ("WITHHELD", "ctrl:withheld", "withheld"))
        self.assertNotIn("withheld-proof", {item["evidence_id"] for item in console.ConsoleStore(database).proof_feed()})

    def test_project_view_scopes_burn_history_and_navigation(self) -> None:
        app = console.App(self.codex_home, self.config)
        overview = {
            "nodes": [
                {"id": "ctrl-a", "project_id": "project:a", "role": "ctrl", "status": "active", "virtual": False, "tokens": 10},
                {"id": "task-a", "project_id": "project:a", "role": "doer", "status": "active", "virtual": False, "tokens": 20},
                {"id": "ctrl-b", "project_id": "project:b", "role": "ctrl", "status": "active", "virtual": False, "tokens": 30},
            ],
            "links": [],
            "roots": ["ctrl-a", "ctrl-b"],
            "controllers": [
                {"id": "ctrl-a", "project_id": "project:a", "title": "CTRL - Alpha", "status": "active", "updated_at": 2, "archived": False, "archive_source": "host_threads.archived", "controller_classification": "swarm_ctrl", "controller_classification_source": "host_threads.agent_role"},
                {"id": "ctrl-b", "project_id": "project:b", "title": "CTRL - Beta", "status": "active", "updated_at": 1, "archived": False, "archive_source": "host_threads.archived", "controller_classification": "swarm_ctrl", "controller_classification_source": "host_threads.agent_role"},
            ],
            "projects": [
                {"id": "project:a", "name": "Alpha", "goal_label": "Alpha goal", "label_source": "working_directory"},
                {"id": "project:b", "name": "Beta", "goal_label": "Beta goal", "label_source": "working_directory"},
            ],
            "analytics": {"swarms": 2},
        }
        with mock.patch.object(app.store, "token_history", return_value=[{"bucket_ms": 1, "delta_tokens": 7, "source": "host_reported_cumulative_delta"}]) as history:
            view = app._project_view(overview, "project:a")
        history.assert_called_once_with(project_id="project:a")
        self.assertEqual(view["token_history"][0]["delta_tokens"], 7)
        self.assertEqual(view["analytics"]["burn_rate"]["history"][0]["delta_tokens"], 7)
        self.assertEqual(view["navigation"]["active_ctrl_id"], "ctrl-a")
        self.assertEqual(view["navigation"]["projects"][0]["goal_label"], "Alpha goal")
        self.assertEqual(view["navigation"]["projects"][0]["task_count"], 2)

    def test_navigation_eligibility_uses_persisted_ctrl_and_archive_authority(self) -> None:
        now = int(time.time() * 1000)
        quiet = now - 2 * 60 * 60 * 1000
        connection = sqlite3.connect(self.database)
        connection.execute("UPDATE threads SET agent_role='ctrl' WHERE id='root'")
        rows = [
            ("ctrl-idle", "🐙CTRL - Idle", "C:/work/idle", quiet, quiet, 0, "ctrl"),
            ("ctrl-stalled", "🐙CTRL - Stalled", "C:/work/stalled", quiet, quiet, 0, "ctrl"),
            ("ctrl-archived", "🐙CTRL - Archived", "C:/work/archived", now, now, 1, "ctrl"),
            ("legacy-title", "🐙CTRL - Legacy", "C:/work/legacy", now, now, 0, ""),
            ("no-ctrl", "🔨DEV - Standalone", "C:/work/noctrl", now, now, 0, "doer"),
        ]
        for thread_id, title, cwd, created, updated, archived, agent_role in rows:
            connection.execute(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (thread_id, title, cwd, created // 1000, updated // 1000, created, updated,
                 "gpt-5.6-luna", "high", 0, archived, "", "main", "", "", agent_role, 0),
            )
        connection.commit()
        connection.close()

        production = console.build_overview(self.codex_home, self.config)
        stalled_controller = next(
            item for item in production["controllers"] if item["id"] == "ctrl-stalled"
        )
        stalled_controller["status"] = "blocked"
        navigation = console.App._navigation_payload(production)
        project_ids = {project["name"]: project["id"] for project in production["projects"]}
        by_project = {item["id"]: item for item in navigation["projects"]}
        by_controller = {item["id"]: item for item in navigation["controllers"]}
        idle = by_project[project_ids["idle"]]
        stalled = by_project[project_ids["stalled"]]
        archived = by_project[project_ids["archived"]]
        legacy = by_project[project_ids["legacy"]]
        no_ctrl = by_project[project_ids["noctrl"]]
        self.assertEqual(idle["project_eligibility"], "swarm_ctrl")
        self.assertEqual(idle["ctrl_ids"], ["ctrl-idle"])
        self.assertEqual(stalled["project_eligibility"], "swarm_ctrl")
        self.assertEqual(stalled["ctrl_ids"], ["ctrl-stalled"])
        self.assertEqual(no_ctrl["project_eligibility"], "no_ctrl")
        self.assertFalse(no_ctrl["archived"])
        self.assertEqual(archived["visibility"], "hidden")
        self.assertTrue(archived["archived"])
        self.assertEqual(archived["project_eligibility"], "no_ctrl")
        self.assertEqual(legacy["project_eligibility"], "no_ctrl")
        self.assertEqual(legacy["eligibility_source"], "unavailable")
        self.assertEqual(legacy["ctrl_ids"], [])
        self.assertEqual(by_controller["ctrl-idle"]["controller_classification"], "swarm_ctrl")
        self.assertEqual(by_controller["ctrl-idle"]["visibility"], "visible")
        self.assertEqual(by_controller["ctrl-archived"]["visibility"], "hidden")
        self.assertEqual(by_controller["legacy-title"]["controller_classification"], "unavailable")
        self.assertEqual(by_controller["legacy-title"]["visibility"], "hidden")
        self.assertNotIn("ctrl-archived", navigation["active_ctrl_ids"])

    def test_proof_media_delivery_requires_registered_surface_and_current_digest(self) -> None:
        media_path = self.root / "proof.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
        store = console.ConsoleStore(self.root / "console" / "delivery.sqlite3")
        base = {
            "source": "CtrlEvidence", "evidence_id": "evidence-delivery", "task_id": "task-1",
            "project_id": "project:alpha", "kind": "screenshot", "locator": str(media_path),
            "caption": "Screenshot proof", "claim_limit": "Local screenshot only.",
            "receipt": "proof-event:evidence-delivery", "surface_kind": "available_media", "disposition": "PENDING",
        }
        registered = store.record_proof_media(base, now_ms=2)
        item = store.proof_media_item("evidence-delivery", registered["digest"])
        self.assertEqual(item["media_type"], "image/png")
        self.assertEqual(item["size_bytes"], len(b"\x89PNG\r\n\x1a\nproof"))
        other_root = self.root / "other-proof-root"
        other_root.mkdir()
        with self.assertRaisesRegex(console.ConsoleError, "configured evidence store"):
            store.proof_media_item("evidence-delivery", registered["digest"], allowed_root=other_root)
        with self.assertRaises(console.ConsoleError):
            store.proof_media_item("evidence-delivery", "0" * 64)
        media_path.write_bytes(b"changed")
        with self.assertRaises(console.ConsoleError):
            store.proof_media_item("evidence-delivery", registered["digest"])

    def test_proof_event_ingestion_derives_project_and_enforces_media_root(self) -> None:
        swarm_root = self.codex_home / "swarm"
        media_root = swarm_root / "proof-media"
        event_root = swarm_root / "proof-events"
        media_root.mkdir(parents=True)
        event_root.mkdir(parents=True)
        media = media_root / "proof.png"
        media.write_bytes(b"\x89PNG\r\n\x1a\nproof")
        digest = hashlib.sha256(media.read_bytes()).hexdigest()
        event = {
            "schema_version": 1,
            "source": "CtrlEvidence",
            "evidence_id": "event-proof",
            "task_id": "task-1",
            "kind": "screenshot",
            "locator": "proof-media/proof.png",
            "caption": "Observed settings screen",
            "claim_limit": "Available for review; acceptance is recorded separately.",
            "digest": digest,
            "size_bytes": media.stat().st_size,
            "media_type": "image/png",
            "disposition": "PENDING",
        }
        (event_root / "event.json").write_text(json.dumps(event), encoding="utf-8")
        store = console.ConsoleStore(self.root / "console" / "events.sqlite3")
        overview = {"nodes": [{"id": "task-1", "project_id": "project:alpha", "virtual": False}]}
        self.assertEqual(store.ingest_proof_events(self.codex_home, overview, now_ms=9), 1)
        item = store.proof_feed(project_id="project:alpha")[0]
        self.assertEqual(item["task_id"], "task-1")
        self.assertEqual(item["disposition"], "PENDING")
        event["evidence_id"] = "outside"
        event["locator"] = "../outside.png"
        (event_root / "outside.json").write_text(json.dumps(event), encoding="utf-8")
        with mock.patch.object(console, "_media_metadata", wraps=console._media_metadata) as metadata:
            self.assertEqual(store.ingest_proof_events(self.codex_home, overview, now_ms=10), 0)
        metadata.assert_not_called()
        self.assertEqual(len(store.proof_feed()), 1)

    def test_clear_history_removes_proof_files_and_prevents_reimport(self) -> None:
        swarm_root = self.codex_home / "swarm"
        media_root = swarm_root / "proof-media"
        event_root = swarm_root / "proof-events"
        media_root.mkdir(parents=True)
        event_root.mkdir(parents=True)
        media = media_root / "proof.png"
        media.write_bytes(b"\x89PNG\r\n\x1a\nproof")
        digest = hashlib.sha256(media.read_bytes()).hexdigest()
        (event_root / "event.json").write_text(json.dumps({
            "schema_version": 1, "source": "CtrlEvidence", "evidence_id": "clear-proof",
            "task_id": "task", "kind": "screenshot", "locator": "proof-media/proof.png",
            "caption": "Task proof", "claim_limit": "Available for review.", "digest": digest,
            "size_bytes": media.stat().st_size, "media_type": "image/png", "disposition": "PENDING",
        }), encoding="utf-8")
        app = console.App(self.codex_home, self.config, self.root / "console" / "clear.sqlite3")
        overview = console.build_overview(self.codex_home, self.config)
        self.assertEqual(app.store.ingest_proof_events(self.codex_home, overview, now_ms=1), 1)
        self.assertGreater(app.storage()["proof_bytes"], 0)
        result = app.clear_history()
        self.assertEqual(result["proof"]["files_deleted"], 2)
        self.assertEqual(app.storage()["proof_bytes"], 0)
        self.assertEqual(app.store.proof_feed(), [])
        self.assertEqual(app.store.ingest_proof_events(self.codex_home, overview, now_ms=2), 0)

    def test_proof_event_can_resolve_project_level_task_from_host_metadata(self) -> None:
        database = self.codex_home / "state_5.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO threads(id, title, cwd, archived, git_origin_url) VALUES (?, ?, ?, ?, ?)",
                ("project-task", "Project task", str(self.root / "flowwweb" / "swarm"), 0, ""),
            )
            connection.commit()
        finally:
            connection.close()
        expected, _ = console._project_identity({"cwd": str(self.root / "flowwweb" / "swarm"), "git_origin_url": ""})
        self.assertEqual(console.observed_task_project_id(self.codex_home, "project-task"), expected)
        self.assertIsNone(console.observed_task_project_id(self.codex_home, "missing"))

    @staticmethod
    def _health_sample(*, cpu: float = 10.0, memory: float = 20.0, free_bytes: int = 20 * 1024**3) -> dict:
        return {
            "sampled_at_ms": 1,
            "cpu": {"available": True, "percent": cpu, "source": "test"},
            "memory": {"available": True, "percent": memory, "used_bytes": 1, "total_bytes": 2, "source": "test"},
            "disks": [{"mount": "C:\\", "free_bytes": free_bytes, "total_bytes": 30 * 1024**3, "percent": 30, "available": True}],
            "docker": {"available": False, "status": "unavailable"},
            "network": {"available": False, "source": "test"},
            "console_storage": {"db_bytes": 1, "wal_bytes": 0, "shm_bytes": 0, "log_bytes": 0},
        }

    def test_diagnostics_preserve_independent_sources_and_report_partial_freshness(self) -> None:
        now_ms = 2_000_000_000_000
        psutil_stub = SimpleNamespace(
            cpu_percent=lambda interval=None: 37.5,
            virtual_memory=lambda: SimpleNamespace(percent=62.0, used=620, total=1_000),
            net_io_counters=lambda: (_ for _ in ()).throw(OSError("network counters unavailable")),
        )
        docker_unavailable = {
            "available": False,
            "status": "unavailable",
            "container_count": 0,
            "source": "docker_cli_read_only",
            "unavailable_reason": "Docker CLI is not available.",
            "recommended_action": "Keep container metrics unavailable.",
        }
        collector = console.DiagnosticsCollector(self.codex_home, self.root / "console" / "state.sqlite3", now_fn=lambda: now_ms / 1000)
        with mock.patch.dict(sys.modules, {"psutil": psutil_stub}), mock.patch.object(
            console.DiagnosticsCollector, "_docker_status", return_value=docker_unavailable,
        ):
            sample = collector.collect()

        self.assertEqual(sample["cpu"]["percent"], 37.5)
        self.assertEqual(sample["memory"]["percent"], 62.0)
        self.assertFalse(sample["network"]["available"])
        self.assertEqual(sample["cpu"]["source"], "psutil")
        self.assertEqual(sample["cpu"]["observed_at_ms"], now_ms)
        self.assertTrue(sample["disks"][0]["available"])
        response = console._diagnostic_record_for_response(
            {"sampled_at_ms": now_ms, "health_state": "HEALTHY", "reasons": [], "payload": sample},
            now_ms + 60_000,
        )
        self.assertEqual(response["source_timestamp_ms"], now_ms)
        self.assertEqual(response["freshness"]["state"], "fresh")
        self.assertEqual(response["payload"]["availability"]["status"], "partial")
        self.assertEqual(
            {item["group"] for item in response["payload"]["availability"]["unavailable_groups"]},
            {"containers", "network"},
        )

    def test_diagnostics_no_sample_is_grouped_and_explicitly_unverified(self) -> None:
        app = console.App(self.codex_home, self.config)
        result = app.diagnostics()
        latest = result["latest"]
        self.assertEqual(latest["health_state"], "UNKNOWN")
        self.assertEqual(latest["freshness"]["state"], "no_data")
        self.assertEqual(latest["payload"]["availability"]["status"], "no_data")
        self.assertEqual(latest["payload"]["availability"]["unavailable_groups"][0]["group"], "host")
        self.assertFalse(result["usage_consumed"])

    def test_health_classification_persistence_sustain_dedupe_and_recovery(self) -> None:
        self.assertEqual(console.assess_health({})["state"], "UNKNOWN")
        self.assertEqual(console.assess_health(self._health_sample())["state"], "HEALTHY")
        path = self.root / "console" / "health.sqlite3"
        store = console.ConsoleStore(path)
        pressured = self._health_sample(free_bytes=4 * 1024**3)
        first = store.record_diagnostics(pressured, now_ms=1_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(first["request_ids"], [])
        second = store.record_diagnostics(pressured, now_ms=301_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(len(second["request_ids"]), 1)
        repeated = store.record_diagnostics(pressured, now_ms=302_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(repeated["request_ids"], second["request_ids"])
        restarted = console.ConsoleStore(path)
        self.assertEqual(len(restarted.health_requests(status="OPEN")), 1)
        recovering = restarted.record_diagnostics(self._health_sample(), now_ms=303_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(recovering["request_ids"], [])
        recovered = restarted.record_diagnostics(self._health_sample(), now_ms=904_000, auto_enabled=True, sustain_seconds=300, recovery_seconds=600)
        self.assertEqual(recovered["request_ids"], [])
        self.assertEqual(restarted.health_requests()[0]["status"], "RECOVERED")
        self.assertEqual(restarted.health_incidents()[0]["state"], "RECOVERED")

    def test_auto_health_off_has_no_request_and_claim_is_single_winner(self) -> None:
        path = self.root / "console" / "health-off.sqlite3"
        store = console.ConsoleStore(path)
        sample = self._health_sample(free_bytes=4 * 1024**3)
        store.record_diagnostics(sample, now_ms=1_000, auto_enabled=False, sustain_seconds=1)
        store.record_diagnostics(sample, now_ms=3_000, auto_enabled=False, sustain_seconds=1)
        self.assertEqual(store.health_requests(), [])
        store.record_diagnostics(sample, now_ms=5_000, auto_enabled=True, sustain_seconds=1)
        request_id = store.health_requests(status="OPEN")[0]["request_id"]
        store.claim_health_request(request_id, now_ms=6_000)
        with self.assertRaises(console.ConsoleConflict):
            store.claim_health_request(request_id, now_ms=7_000)

    def test_diagnostics_reads_are_pure_and_clear_preserves_ctrl_overlay(self) -> None:
        app = console.App(self.codex_home, self.config)
        with mock.patch.object(app, "observe_once", side_effect=AssertionError("usage path")):
            result = app.diagnostics()
            history = app.diagnostics_history()
        self.assertFalse(result["usage_consumed"])
        self.assertEqual(history, [])
        store = console.ConsoleStore(self.root / "console" / "health-clear.sqlite3")
        store.update_ctrl_override("ctrl-1", {"reasoning": "high"}, expected_revision=0, now_ms=1)
        store.record_diagnostics(self._health_sample(), now_ms=1, auto_enabled=False)
        store.clear_history()
        self.assertEqual(store.diagnostics_history(), [])
        self.assertEqual(store.health_incidents(), [])
        self.assertEqual(store.get_ctrl_override("ctrl-1")["revision"], 1)

    def test_ctrl_overlay_requires_revision_and_can_reset_to_global(self) -> None:
        store = console.ConsoleStore(self.root / "console" / "overrides.sqlite3")
        now = int(time.time() * 1000)
        updated = store.update_ctrl_override(
            "ctrl-1", {"model": "gpt-5.6-sol"}, expected_revision=0, now_ms=now
        )
        self.assertEqual(updated["revision"], 1)
        with self.assertRaises(console.ConsoleConflict):
            store.update_ctrl_override("ctrl-1", {"reasoning": "high"}, expected_revision=0, now_ms=now)
        self.assertTrue(store.reset_ctrl_override("ctrl-1", expected_revision=1)["reset"])
        self.assertEqual(store.get_ctrl_override("ctrl-1")["revision"], 0)

    def test_valid_config_update_is_validated_and_backed_up(self) -> None:
        result = console.update_config(self.config, {"monitoring.heartbeat_minutes": 45})
        self.assertEqual(result["settings"]["monitoring"]["heartbeat_minutes"], 45)
        self.assertTrue(self.config.with_suffix(".toml.swarm-console.bak").exists())

    def test_auto_health_setting_defaults_off_and_uses_canonical_validator(self) -> None:
        _, effective, _ = console.load_config(self.config)
        self.assertFalse(effective["monitoring"]["auto_health_enabled"])
        result = console.update_config(self.config, {"monitoring.auto_health_enabled": True})
        self.assertTrue(result["settings"]["monitoring"]["auto_health_enabled"])
        with self.assertRaises(console.ConsoleError):
            console.update_config(self.config, {"monitoring.auto_health_enabled": "true"})

    def test_restore_defaults_is_canonical_and_keeps_a_backup(self) -> None:
        console.update_config(self.config, {"monitoring.heartbeat_minutes": 45})
        result = console.restore_config_defaults(self.config)
        self.assertEqual(result["settings"]["monitoring"]["heartbeat_minutes"], 30)
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

    def test_formatted_tree_without_controller_scope_is_not_given_a_virtual_ctrl(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("specialist-parent", "🧩SPECIALIST - Historical route", "C:/work/beta", now // 1000, now, now, now,
                 "gpt-5.6-sol", "high", 20, 0, "", "main", "", "", "", 0),
                ("specialist", "💻DEV - Historical implementation", "C:/work/beta", now // 1000, now, now, now,
                 "gpt-5.6-luna", "high", 30, 0, "", "main", "", "", "", 0),
            ],
        )
        connection.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("specialist-parent", "specialist", "open"))
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        ids = {node["id"] for node in overview["nodes"]}
        self.assertNotIn("specialist-parent", ids)
        self.assertNotIn("specialist", ids)
        self.assertFalse(any(node["virtual"] for node in overview["nodes"]))
        self.assertFalse(any(link["target"] in {"specialist-parent", "specialist"} for link in overview["links"]))

    def test_standalone_formatted_task_without_spawn_edge_is_visible_at_project_level(self) -> None:
        now = 2_000_000_000_000
        connection = sqlite3.connect(self.database)
        connection.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("orphan-task", "💻DEV - Title-only task", "C:/work/beta", now // 1000, now, now, now,
             "gpt-5.6-terra", "high", 30, 0, "", "main", "", "", "", 0),
        )
        connection.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("unformatted", "Ordinary user conversation", "C:/work/beta", now // 1000, now, now, now,
             "gpt-5.6-terra", "high", 30, 0, "", "main", "", "", "", 0),
        )
        connection.commit()
        connection.close()

        overview = console.build_overview(self.codex_home, self.config)
        orphan = next(node for node in overview["nodes"] if node["id"] == "orphan-task")
        self.assertEqual(orphan["project"], "beta")
        self.assertIsNone(orphan["parent_id"])
        self.assertEqual(orphan["controller_ids"], [])
        self.assertNotIn("unformatted", {node["id"] for node in overview["nodes"]})
        self.assertFalse(any("orphan-task" in (link["source"], link["target"]) for link in overview["links"]))
        self.assertFalse(any(node["virtual"] for node in overview["nodes"]))
        self.assertEqual(next(project for project in overview["projects"] if project["id"] == orphan["project_id"])["nodes"], 1)

    def test_health_copy_is_product_facing_without_a_watchdog_surface(self) -> None:
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("Automatic care", app)
        self.assertIn("Keep this device healthy", app)
        self.assertIn("Starts with a review", app)
        self.assertNotIn("never model work", app.casefold())
        self.assertNotIn("passive monitoring", app.casefold())
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
        legacy_title = console._role_from_title("🐝MOTHER - Historical route", enabled["labels"], enabled["role_icons"], enabled["professions"])
        self.assertEqual(duplicate["title"], "🧭LEAD - Console")
        self.assertEqual(wrong["title"], "🐙CTRL - Ship console")
        self.assertEqual(repeated["title"], "🐙CTRL - Ship console")
        self.assertEqual(developer["title"], "💻DEV - Renderer")
        self.assertEqual((legacy_title["role"], legacy_title["title"]), ("doer", "📋MOTHER - Historical route"))
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

    def test_spark_small_work_lane_is_off_by_default_and_configurable(self) -> None:
        before = console.redacted_config_snapshot(self.config)
        self.assertFalse(before["settings"]["boost"]["spark_enabled"])
        self.assertEqual(before["settings"]["boost"]["spark_reasoning"], "xhigh")
        self.assertIn("boost.spark_enabled", before["editable"])
        self.assertIn("boost.spark_reasoning", before["editable"])
        result = console.update_config(
            self.config,
            {"boost.spark_enabled": True, "boost.spark_reasoning": "medium"},
        )
        self.assertTrue(result["settings"]["boost"]["spark_enabled"])
        self.assertEqual(result["settings"]["boost"]["spark_reasoning"], "medium")

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

    def test_spark_has_one_bounded_settings_control(self) -> None:
        index = (console.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        app = (console.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('id="usage-saver-toggle"', index)
        self.assertEqual(app.count("settingToggle('boost.spark_enabled'"), 1)
        self.assertIn("Use Spark for safe small tasks", app)
        self.assertIn("Spark handles quick, low-risk work", app)
        self.assertNotIn("No browser, web lookup, ImageGen", app)
        self.assertNotIn("saveUsageSaver", app)

    def test_console_ui_fixture_is_structurally_valid(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "console-ui.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(set(fixture), {"bootstrap", "config", "overview", "proofFeed", "usageHistory", "diagnostics", "diagnosticHistory", "healthSettings", "storage", "ctrlSettings"})
        self.assertFalse(fixture["config"]["settings"]["execution"]["usage_saver"])
        self.assertIn("execution.usage_saver", fixture["config"]["editable"])
        self.assertTrue(fixture["config"]["settings"]["console"]["open_on_start"])
        self.assertIn("console.open_on_start", fixture["config"]["editable"])
        self.assertIn("boost.spark_enabled", fixture["config"]["editable"])
        self.assertEqual(fixture["config"]["settings"]["boost"]["spark_reasoning"], "xhigh")

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
