from __future__ import annotations

import json
import hashlib
import io
import importlib.util
from unittest.mock import patch, Mock
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "swarm_mcp.py"


spec = importlib.util.spec_from_file_location("swarm_mcp", SERVER)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


def call(process: subprocess.Popen[str], request: dict) -> dict:
    assert process.stdin and process.stdout
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    return json.loads(process.stdout.readline())


def image_sources(markup: str) -> list[str | None]:
    """Read actual image elements; bundled JavaScript strings are not images."""
    sources = []
    class Images(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "img":
                sources.append(dict(attrs).get("src"))
    parser = Images()
    parser.feed(markup)
    return sources


class SwarmMCPTests(unittest.TestCase):
    def _unit_fixture(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console import server
        from console.tests.test_console import SwarmConsoleTests
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        projection = mcp.SwarmProjection()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=Mock())
        role = next(r for r in projection._app.builtin_role_manifests if r["id"] == "architect")
        request = dict(kind="LAB", template_id="research", name="Interface Lab", objective="Resolve a bounded question",
            project_id="project:alpha", ctrl_id="ctrl-a", request_id="native-unit",
            coordinator_role={"id": role["id"], "version": role["version"]})
        return server, fixture, projection, request

    def test_native_unit_prepare_create_readback_restart_uses_existing_connector(self):
        server, fixture, projection, request = self._unit_fixture()
        app = projection._app
        sent = []
        @contextmanager
        def session(cwd, **kwargs):
            responses = [{"thread": {"id": "native-unit-task", "cwd": str(cwd)}}, {"turn": {"id": "unit-turn"}}]
            yield sent.append, lambda predicate: {"id": sent[-1]["id"], "result": responses.pop(0)}
        app.auto_bridge.command_session = session
        with patch.object(app, "_auto_scope"):
            prepared = projection.call("swarm_unit_prepare", request)
            competing = projection.call("swarm_unit_prepare", {**request, "request_id": "later-unit"})
            self.assertEqual(prepared["status"], "PREPARED")
            self.assertEqual(sent, [])
            self.assertEqual(app.progress_ledger.replay()["task_creation_bindings"], {})
            result = projection.call("swarm_unit_create", prepared["submission"])
            stale = projection.call("swarm_unit_create", competing["submission"])
        self.assertEqual(stale["status"], "NOT_DISPATCHED")
        self.assertEqual([r["method"] for r in sent], ["thread/start", "turn/start"])
        self.assertEqual(result["status"], "RESULT")
        self.assertEqual(result["command_digest"], prepared["command_digest"])
        self.assertFalse(result["work_completed"])
        self.assertEqual(result["readback"]["state"], "KNOWN")
        self.assertEqual(result["readback"]["role_manifest_ref"]["manifest_id"], request["coordinator_role"]["id"])
        self.assertEqual(result["readback"]["role_manifest_ref"]["manifest_version"], request["coordinator_role"]["version"])
        self.assertLessEqual(result["readback"]["creation_event"]["event_seq"], result["readback"]["cursor"]["event_seq"])
        unit = result["readback"]["unit"]
        self.assertEqual((unit["task_id"], unit["project_id"], unit["ctrl_id"], unit["work_unit"]["kind"]),
                         ("native-unit-task", "project:alpha", "ctrl-a", "LAB"))
        self.assertIsNone(unit["work_unit"]["goal_id"])
        self.assertEqual(unit["outcome_acceptance"], "UNKNOWN")
        self.assertEqual(app.unit_catalog_projection("LAB")["instances"], [unit])
        retained = app.progress_ledger._state.path.read_bytes()
        restarted = server.App(fixture.codex_home, fixture.config, auto_bridge=Mock())
        projection._app = restarted
        replay = projection.call("swarm_unit_create", prepared["submission"])
        self.assertEqual(replay["status"], "REPLAY")
        self.assertEqual(replay["readback"], result["readback"])
        self.assertEqual(restarted.progress_ledger._state.path.read_bytes(), retained)
        self.assertEqual(restarted.auto_bridge.mock_calls, [])
        self.assertNotIn(prepared["submission"]["instruction"].encode(), retained)
        self.assertEqual(len(restarted.progress_ledger.replay()["task_creation_bindings"]), 1)
        # A later read failure cannot erase the exact retained dispatch receipt.
        with patch.object(restarted, "unit_catalog_projection", side_effect=server.ConsoleError("private/path")):
            unreadable = projection.call("swarm_unit_create", prepared["submission"])
        self.assertEqual(unreadable["status"], "REPLAY")
        self.assertEqual(unreadable["command_digest"], prepared["command_digest"])
        self.assertEqual(unreadable["readback"], {"state": "UNAVAILABLE", "unit": None, "cursor": None})
        self.assertNotIn("private/path", json.dumps(unreadable))

    def test_native_unit_uncertain_creation_replays_without_new_actor(self):
        server, fixture, projection, request = self._unit_fixture()
        app = projection._app
        sent = []
        @contextmanager
        def session(cwd, **kwargs):
            def receive(predicate):
                raise TimeoutError("unknown thread/start delivery")
            yield sent.append, receive
        app.auto_bridge.command_session = session
        with patch.object(app, "_auto_scope"):
            prepared = projection.call("swarm_unit_prepare", {**request, "kind": "FACTORY", "template_id": "software"})
            result = projection.call("swarm_unit_create", prepared["submission"])
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["readback"], {"state": "PENDING", "unit": None, "cursor": None})
        self.assertFalse(result["work_completed"])
        self.assertEqual([r["method"] for r in sent], ["thread/start"])
        retained = app.progress_ledger._state.path.read_bytes()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=Mock())
        replay = projection.call("swarm_unit_create", prepared["submission"])
        self.assertEqual(replay["status"], "PENDING")
        self.assertIsNone(replay["readback"]["unit"])
        self.assertEqual(projection._app.progress_ledger._state.path.read_bytes(), retained)
        self.assertEqual(projection._app.progress_ledger.replay()["task_creation_bindings"], {})
        self.assertEqual(projection._app.auto_bridge.mock_calls, [])

    def test_native_unit_rejects_unbound_and_stale_inputs_without_dispatch(self):
        server, fixture, projection, request = self._unit_fixture()
        app = projection._app
        with patch.object(app, "_auto_scope", side_effect=server.ConsoleError("missing exact authority")):
            self.assertEqual(projection.call("swarm_unit_prepare", request)["state"], "REJECTED")
        with patch.object(app, "_auto_scope"):
            stale_role = {**request, "coordinator_role": {"id": "architect", "version": "builtin:stale"}}
            self.assertEqual(projection.call("swarm_unit_prepare", stale_role)["state"], "CONFLICT")
            prepared = projection.call("swarm_unit_prepare", request)
        for change in ({"acknowledge": False}, {"acknowledge": 1}, {"path": "elsewhere"}):
            with self.assertRaises(mcp.MCPError):
                projection.call("swarm_unit_create", {**prepared["submission"], **change})
        payload = prepared["submission"]
        for change in ({"instruction": "different"}, {"envelope": {**payload["envelope"], "root_digest": "f" * 64}},
                       {"envelope": {**payload["envelope"], "task_creation": None}}):
            self.assertEqual(projection.call("swarm_unit_create", {**payload, **change})["state"], "REJECTED")
        with patch.object(server.time, "time", return_value=payload["envelope"]["expires_at_ms"] / 1000 + 1), patch.object(app, "_auto_scope"):
            stale = projection.call("swarm_unit_create", payload)
        self.assertEqual(stale["status"], "NOT_DISPATCHED")
        self.assertIsNone(stale["readback"]["unit"])
        self.assertEqual(app.progress_ledger.replay()["connector_receipts"], {})
        self.assertEqual(app.auto_bridge.mock_calls, [])

    def test_native_unit_tools_wire_rejection_and_visibility(self):
        server, fixture, projection, request = self._unit_fixture()
        for name in ("swarm_unit_prepare", "swarm_unit_create"):
            spec = next(tool for tool in mcp.TOOLS if tool["name"] == name)
            self.assertEqual(spec["_meta"]["ui"]["visibility"], ["app"])
            self.assertEqual(spec["annotations"]["readOnlyHint"], name == "swarm_unit_prepare")
        request["coordinator_role"]["version"] = "builtin:stale"
        wire = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "swarm_unit_prepare", "arguments": request}}
        with patch.object(mcp.SwarmProjection, "_load_app", return_value=projection._app), \
             patch.object(projection._app, "_auto_scope"), \
             patch.object(sys, "stdin", io.StringIO(json.dumps(wire))), \
             patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve(telemetry_path=fixture.root / "unit-wire.jsonl")
        result = json.loads(output.getvalue())["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["state"], "CONFLICT")
        self.assertNotIn(request["objective"], (fixture.root / "unit-wire.jsonl").read_text())

    def test_ticket_read_failure_is_not_reported_as_failed_save(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console.server import ConsoleError
        projection = mcp.SwarmProjection()
        app = Mock()
        projection._app = app
        read = {"operation": "read", "project_id": "project:alpha"}
        for reason in ("work assignment requires its exact acceptance contract", "private/path: malformed record"):
            with self.subTest(reason=reason):
                app.project_ticket_command.side_effect = ConsoleError(reason)
                result = projection.call("swarm_project_tickets", read)
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "TICKET_READ_FAILED")
                self.assertIn("could not be read", result["message"])
                self.assertIn("not been changed", result["message"])
                self.assertNotIn("saved", result["message"])
                self.assertNotIn(reason, json.dumps(result))
        write = {**read, "operation": "update", "expected_digest": "sha256:" + "0" * 64,
                 "acknowledge": True, "collection": "tasks", "record_id": "task-a", "changes": {"label": "Task"}}
        result = projection.call("swarm_project_tickets", write)
        self.assertEqual(result["code"], "TICKET_REJECTED")
        self.assertIn("could not be saved", result["message"])

    def test_current_milestone_compaction_preserves_exact_basis_without_borrowing_project_progress(self):
        milestone = {"state": "KNOWN", "reason": None, "name": "Milestone", "source": "ledger_active_task_manifest",
            "cursor": {"event_seq": 3}, "milestone_id": "m", "task_id": "t", "project_id": "p", "ctrl_id": "c",
            "scope_version": 1, "manifest_identity": {"manifest_digest": "a" * 64}, "event_cursor": {"event_seq": 2},
            "observed_at_ms": 100, "as_of_ms": 1000, "freshness": "CURRENT",
            "measurement": {"state": "KNOWN", "percent": 25},
            "estimate": {"state": "KNOWN", "minutes": 60, "deadline_ms": None}, "private": "not-public"}
        result = mcp._compact_progress_scope({"scope": {"project_id": "p"}, "progress": 99, "current_milestone": milestone})
        self.assertEqual(result["current_milestone"], {k: v for k, v in milestone.items() if k != "private"})
        self.assertEqual(result["current_milestone"]["measurement"]["percent"], 25)
        unknown = {"state": "UNKNOWN", "reason": "STALE_MILESTONE", "name": None, "cursor": {"event_seq": 3}}
        result = mcp._compact_progress_scope({"progress": 99, "current_milestone": unknown})
        self.assertEqual(result["current_milestone"], unknown)
        self.assertNotIn("measurement", result["current_milestone"])

    def test_native_role_variants_preserve_exact_readback_without_admitting_media(self):
        variants = [{"id": "command", "asset_digest": "a" * 64, "structural_roles": ["CTRL"]}]
        role = {"id": "producer", "active_version": "builtin:exact", "avatar_variants": variants,
                "avatar": {"url": "https://unadmitted.example/private.png"}, "versions": ["private"]}
        value = mcp._native_roles({"cursor": {"event_seq": 1}, "roles": [role]})
        self.assertEqual(value["roles"][0]["avatar_variants"], variants)
        self.assertIsNone(value["roles"][0]["avatar"])
        self.assertNotIn("private", json.dumps(value))

    def test_native_role_media_uses_exact_canonical_inventory_and_withholds_invalid_bytes(self):
        import base64
        import copy
        sys.path.insert(0, str(ROOT))
        from runtime.progress_events import load_builtin_role_avatar_assets
        assets = load_builtin_role_avatar_assets(ROOT / "assets" / "role-avatars")
        roles = [{"id": role_id, "name": role_id, "active_version": "builtin:fixture",
                  "avatar_asset_digest": item["source"]["sha256"]} for role_id, item in assets.items()]
        projection = {"cursor": {"event_seq": 1}, "roles": roles}
        with patch.object(mcp, "_projects_asset", side_effect=AssertionError("list is icon-only")):
            roster = mcp._native_roles(projection, assets)
        self.assertEqual(len(roster["roles"]), 24)
        self.assertTrue(all(row["avatar"] is None and row["avatar_choices"] == [] for row in roster["roles"]))
        bridge = mcp.SwarmProjection()
        bridge._app = Mock(builtin_role_avatar_assets=assets)
        bridge._app.role_manifest_projection.return_value = projection
        for selected in roles:
            value = bridge.call("swarm_role_read", {"role_id": selected["id"]})
            self.assertEqual(value["cursor"], projection["cursor"])
            self.assertEqual(len(value["roles"]), 1)
            role = value["roles"][0]
            avatar = role["avatar"]
            self.assertEqual(avatar["digest"], role["avatar_asset_digest"])
            self.assertEqual(avatar["manifest_version"], role["active_version"])
            self.assertEqual(avatar["role_id"], role["id"])
            self.assertEqual((avatar["width"], avatar["height"]), (256, 256))
            self.assertEqual(avatar["media_type"], "image/webp")
            self.assertEqual(role["avatar_choices"], [{key: avatar[key] for key in ("id", "label", "role_id", "manifest_version", "digest")}])
            raw = base64.b64decode(avatar["url"].removeprefix("data:image/webp;base64,"), validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), avatar["render_digest"])
            self.assertEqual(avatar["render_digest"], assets[role["id"]]["derivatives"][(256, "webp")]["sha256"])
            self.assertLess(len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()), 262144)
        wires = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {
            "name": "swarm_role_read", "arguments": args}} for i, args in enumerate([{}] + [{"role_id": r["id"]} for r in roles])]
        # The actual serve() size gate must accept the roster and every selected detail.
        with patch.object(mcp.SwarmProjection, "_load_app", return_value=bridge._app), \
             patch.object(mcp, "_telemetry"), patch.object(sys, "stdin", io.StringIO("\n".join(map(json.dumps, wires)))), \
             patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            self.assertEqual(mcp.serve(), 0)
        results = [json.loads(line)["result"] for line in output.getvalue().splitlines()]
        self.assertEqual(len(results), 25)
        self.assertTrue(all(result["isError"] is False for result in results))
        self.assertEqual(results[0]["structuredContent"], roster)
        for result in results[1:]:
            self.assertEqual(len(result["structuredContent"]["roles"]), 1)
        selected = roles[0]
        foreign = {**selected, "avatar_asset_digest": "a" * 64}
        read = mcp._native_roles({"cursor": {}, "roles": [foreign]}, assets, selected["id"])["roles"][0]
        self.assertIsNone(read["avatar"], "never display canonical media as a different retained selection")
        self.assertEqual(read["avatar_choices"][0]["digest"], selected["avatar_asset_digest"])
        with patch.object(mcp, "_projects_asset", side_effect=mcp.MCPError("changed bytes")):
            withheld = mcp._native_roles(projection, assets, selected["id"])
        self.assertTrue(all(row["avatar"] is None and row["avatar_choices"] == [] for row in withheld["roles"]))
        for change in ({"path": "../../private.webp"}, {"bytes": 32769}, {"format": "svg"}, {"sha256": "unknown"}):
            bad = copy.deepcopy(assets)
            bad[selected["id"]]["derivatives"][(256, "webp")].update(change)
            with patch.object(mcp, "_projects_asset") as reader:
                self.assertEqual(mcp._native_role_choices(selected, bad), [])
                reader.assert_not_called()
        for role_id in ("unadmitted-custom", "../producer", "Producer", "critic"):
            with self.subTest(role_id=role_id), self.assertRaises(mcp.MCPError):
                bridge.call("swarm_role_read", {"role_id": role_id})
            self.assertEqual(mcp._native_role_choices({**selected, "id": role_id}, assets), [])
        with self.assertRaises(mcp.MCPError):
            mcp._native_roles({"cursor": {}, "roles": [selected, selected]}, assets, selected["id"])
        self.assertEqual(bridge._app.role_manifest_command.mock_calls, [])

    def test_native_usage_call_refreshes_samples_and_restarts_through_real_app(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console import server
        from console.tests.test_console import SwarmConsoleTests
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        bridge = Mock()
        projection = mcp.SwarmProjection()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=bridge)
        now = int(server.time.time()) // 60 * 60
        view = {"nodes": [{"id": "a", "title": "Alpha", "project_id": "project:alpha", "tokens": 100},
                          {"id": "b", "title": "Beta", "project_id": "project:beta", "tokens": 200}], "links": []}
        with patch.object(server, "build_overview", return_value=view), \
             patch.object(server, "observation_fingerprint", return_value="baseline") as fingerprint, \
             patch.object(server, "_codex_jsonl_token_counts", return_value={}) as scan, \
             patch.object(server.time, "time", return_value=now) as clock, \
             patch.object(server.App, "observe_once", side_effect=AssertionError("no observer")), \
             patch.object(server.App, "evaluate_auto_once", side_effect=AssertionError("no Auto")):
            first = projection.call("swarm_usage", {"project_id": "project:alpha", "hours": 1})
            self.assertEqual(first["status"], "no_data")
            self.assertEqual(first["dashboard"]["scope"], first["scope"])
            self.assertEqual(first["dashboard"]["window"], {k: first["window"][k] for k in ("after_ms", "before_ms")})
            self.assertEqual(first["dashboard"]["counters"]["active_agents"]["state"], "UNKNOWN", "missing host observation is not zero")
            self.assertEqual(first["items"], [])
            projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=bridge)
            again = projection.call("swarm_usage", {"hours": 1})
            self.assertEqual(again["status"], "no_data")
            self.assertEqual(scan.call_count, 1, "restart reuses the retained bucket")
            clock.return_value = now + 60
            fingerprint.return_value = "advanced"
            view["nodes"][0]["tokens"] = 125
            view["nodes"][1]["tokens"] = 210
            alpha = projection.call("swarm_usage", {"project_id": "project:alpha", "hours": 1})
            total = projection.call("swarm_usage", {"hours": 1})
            self.assertEqual(alpha["total_tokens"], 25)
            self.assertEqual(total["total_tokens"], 35, "project reads preserve global sampling coverage")
            self.assertEqual(scan.call_count, 2)
            self.assertEqual(alpha["scope"], {"type": "project", "project_id": "project:alpha"})
            with self.assertRaises(server.ConsoleError):
                projection.call("swarm_usage", {"project_id": "foreign", "hours": 1})
            self.assertEqual(scan.call_count, 2)
            self.assertEqual(bridge.mock_calls, [])

    def test_native_hives_keep_exact_project_ctrl_unit_and_snapshot_identity(self):
        def agent(identity, project="p", ctrl="ctrl", role="DOER", parent="KNOWN"):
            return {"id": identity, "project_id": project, "ctrl_id": ctrl, "structural_role": role,
                "display_name": identity, "parent_relation": {"state": parent},
                "hierarchy_membership": "BOUND", "manifest_identity": {"manifest_digest": identity},
                "private_path": "SECRET", "progress": 100}
        root = agent("ctrl", role="CTRL", parent="ROOT")
        unit = agent("unit")
        unit["work_unit"] = {"kind": "LAB", "goal_id": "goal", "parent_goal_id": "parent", "parent_unit_task_id": None}
        foreign = agent("foreign", project="other")
        sibling = agent("sibling", ctrl="other-ctrl")
        orphan = agent("orphan", parent="UNKNOWN")
        invalid = agent("invalid")
        invalid["hierarchy_membership"] = "INVALID"
        independent = {"id": "looks-like-ctrl", "title": "CTRL", "node_kind": "independent_host_task"}
        nodes = [root, unit, foreign, sibling, orphan, invalid]
        edges = [{"id": f"e-{node['id']}", "source": "ctrl", "target": node["id"]} for node in [unit, foreign, sibling, invalid]]
        topology = {"state": "PARTIAL", "cursor": {"digest": "exact", "ledger": {"event_seq": 17}},
                    "nodes": nodes, "agent_edges": edges, "independent_nodes": [independent]}
        app = Mock()
        app.overview.return_value = {"topology": topology}
        projection = mcp.SwarmProjection()
        projection._app = app
        before = json.dumps(topology, sort_keys=True)
        result = projection.call("swarm_status", {"project_id": "p"})["hives"]
        app.overview.assert_called_once_with("p")
        self.assertEqual(result["cursor"], topology["cursor"])
        self.assertEqual(result["state"], "PARTIAL")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["execution_authority"])
        self.assertEqual(len(result["items"]), 1)
        hive = result["items"][0]
        self.assertEqual((hive["project_id"], hive["ctrl_id"]), ("p", "ctrl"))
        self.assertEqual([row["id"] for row in hive["agents"]], ["ctrl", "unit"])
        self.assertEqual(hive["units"], [{"task_id": "unit", "project_id": "p", "ctrl_id": "ctrl",
            "manifest_identity": unit["manifest_identity"], "work_unit": unit["work_unit"]}])
        self.assertEqual(hive["agent_edges"], [edges[0]])
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn('"progress"', json.dumps(result))
        self.assertEqual(json.dumps(topology, sort_keys=True), before)
        self.assertEqual(mcp._compact_hives(json.loads(before)), result)

    def test_native_hives_withhold_missing_ambiguous_or_unbound_topology(self):
        for value in (None, {}, {"cursor": None}, {"state": "KNOWN", "cursor": {}, "nodes": [{"id": "x"}, {"id": "x"}]},
                      {"state": "KNOWN", "cursor": {}, "nodes": [{}] * 257}):
            with self.subTest(value=value):
                result = mcp._compact_hives(value)
                self.assertEqual(result["state"], "UNKNOWN")
                self.assertEqual(result["items"], [])
        self.assertEqual(mcp._compact_hives({"state": "EMPTY", "cursor": {"digest": "empty"},
            "nodes": [], "agent_edges": []})["items"], [])
        observed_only = mcp._compact_hives({"state": "KNOWN", "cursor": {"digest": "observed"},
            "nodes": [], "agent_edges": [], "independent_count": 3})
        self.assertEqual((observed_only["state"], observed_only["reason"], observed_only["items"]),
                         ("UNKNOWN", "NO_BOUND_CTRL", []))

    def test_native_hives_malformed_fields_fail_closed_through_production_status(self):
        node = {"id": "ctrl", "project_id": "p", "ctrl_id": "ctrl", "structural_role": "CTRL",
                "parent_relation": {"state": "ROOT"}}
        cases = [{"state": ["KNOWN"], "nodes": [node]},
                 {"state": "KNOWN", "nodes": [{**node, "parent_relation": None}]},
                 {"state": "KNOWN", "nodes": [node], "agent_edges": [{"id": "e", "source": [], "target": "ctrl"}]},
                 {"state": "KNOWN", "nodes": [{**node, "structural_role": ["CTRL"]}]},
                 {"state": "KNOWN", "nodes": [{**node, "id": []}]},
                 {"state": "KNOWN", "nodes": [node], "agent_edges": [None]}]
        app = Mock()
        projection = mcp.SwarmProjection()
        projection._app = app
        for case in cases:
            with self.subTest(case=case):
                app.overview.return_value = {"topology": {"cursor": {"digest": "bound"}, **case}}
                result = projection.call("swarm_status", {"project_id": "p"})
                self.assertEqual(result["hives"]["state"], "UNKNOWN")
                self.assertEqual(result["hives"]["items"], [])

    def test_execution_binding_tool_schema_is_closed_and_not_a_dispatch_tool(self):
        specs = [tool for tool in mcp.TOOLS if tool["name"] == "swarm_project_ticket_execution"]
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertEqual(spec["_meta"]["ui"]["visibility"], ["model", "app"])
        self.assertEqual(spec["inputSchema"]["properties"]["operation"]["enum"], ["read", "bind", "estimate_read", "estimate"])
        self.assertFalse(spec["inputSchema"]["additionalProperties"])
        read = {"operation": "read", "project_id": "project:alpha", "record_id": "ticket-goal"}
        mcp._validate_arguments(spec, read)
        for changes in ({"operation": "start"}, {"completed": True}, {"instruction": "run"},
                        {"attempt": True}, {"expected_ledger_revision": "1"}, {"membership": "OWNER"},
                        {"acknowledge": False}):
            with self.subTest(changes=changes), self.assertRaises(mcp.MCPError):
                mcp._validate_arguments(spec, {**read, **changes})

    def test_ticket_estimate_schema_and_existing_dispatch_keep_exact_request(self):
        import threading
        from types import SimpleNamespace
        spec = next(t for t in mcp.TOOLS if t["name"] == "swarm_project_ticket_execution")
        request = {"operation": "estimate", "project_id": "project:alpha", "record_id": "ticket", "reference_id": "ref",
            "operation_id": "estimate-1", "expected_ledger_revision": 7, "expected_estimate_revision": 0,
            "acknowledge": True, "actor": "User label", "reason": "Refined scope",
            "estimate": {"estimate_minutes": 60, "remaining_minutes": 30, "original_target_ms": None}}
        mcp._validate_arguments(spec, request)
        for changes in ({"expected_estimate_revision": True}, {"actor": ""}, {"estimate": []}, {"completed": True}):
            with self.subTest(changes=changes), self.assertRaises(mcp.MCPError):
                mcp._validate_arguments(spec, {**request, **changes})
        dispatch = Mock(return_value={"ok": True, "status": "APPENDED", "operation": "estimate"})
        app = SimpleNamespace(write_lock=threading.RLock(), project_ticket_execution_command=dispatch)
        projection = mcp.SwarmProjection()
        with patch.object(projection, "_load_app", return_value=app):
            result = projection.call("swarm_project_ticket_execution", request)
        self.assertEqual(result["status"], "APPENDED")
        dispatch.assert_called_once_with(request)

    def test_model_ticket_discovery_and_wire_commands_keep_existing_authority(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console.server import App
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture("alpha")), encoding="utf-8")
        transport = Mock()
        app = App(fixture.codex_home, fixture.config, auto_bridge=transport)

        def wire(method, params):
            request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            with patch.object(mcp.SwarmProjection, "_load_app", return_value=app), \
                 patch.object(sys, "stdin", io.StringIO(json.dumps(request))), \
                 patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                self.assertEqual(mcp.serve(telemetry_path=fixture.root / "ticket-wire.jsonl"), 0)
            return json.loads(output.getvalue())["result"]

        def ticket(arguments):
            return wire("tools/call", {"name": "swarm_project_tickets", "arguments": arguments})

        tools = wire("tools/list", {})["tools"]
        spec = next(t for t in tools if t["name"] == "swarm_project_tickets")
        self.assertEqual(spec["_meta"]["ui"]["visibility"], ["model", "app"])
        self.assertEqual(sum(t["name"] == spec["name"] for t in tools), 1)
        self.assertEqual(spec["inputSchema"]["properties"]["operation"]["enum"], ["read", "create", "update", "migrate_legacy", "allocate_ids"])
        for tool in tools:
            if tool["name"] in {"swarm_role_read", "swarm_role_save", "swarm_library_read", "swarm_flow_save", "swarm_flow_assign",
                                "swarm_settings_read", "swarm_settings_save"}:
                self.assertEqual(tool["_meta"]["ui"]["visibility"], ["app"])
        read = {"operation": "read", "project_id": "project:alpha"}
        initial = ticket(read)
        self.assertFalse(initial["isError"])
        create = {**read, "operation": "create", "expected_digest": initial["structuredContent"]["source_digest"],
                  "acknowledge": True, "collection": "goals", "record_id": "model-ticket",
                  "changes": {"label": "Wire goal"}, "project_code": "TEST"}
        before = brief.read_bytes()
        for change in ({"acknowledge": False}, {"acknowledge": 1}, {"path": "elsewhere"},
                       {"project_id": "foreign-project"}, {"operation": "execute"}):
            self.assertTrue(ticket({**create, **change})["isError"], change)
            self.assertEqual(brief.read_bytes(), before)
            self.assertFalse(app.progress_ledger._state.path.exists())
        saved = ticket(create)
        self.assertFalse(saved["isError"])
        record = next(r for r in saved["structuredContent"]["records"] if r["id"] == "model-ticket")
        self.assertEqual(record["display_id"], "TEST-1")
        source_bytes, ledger_bytes = brief.read_bytes(), app.progress_ledger._state.path.read_bytes()
        app = App(fixture.codex_home, fixture.config, auto_bridge=transport)
        self.assertTrue(ticket(create)["structuredContent"]["replayed"])
        self.assertEqual(brief.read_bytes(), source_bytes)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_bytes)
        # The existing command admits project_code only on create. An update carrying it fails the
        # exact-field check before any digest comparison: REJECTED, not CONFLICT, and no write.
        update = {key: value for key, value in create.items() if key != "project_code"}
        update.update(operation="update", changes={"label": "Updated wire goal"})
        malformed = ticket({**update, "project_code": "TEST"})
        self.assertTrue(malformed["isError"])
        self.assertEqual(malformed["structuredContent"]["state"], "REJECTED")
        self.assertEqual(brief.read_bytes(), source_bytes)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_bytes)
        # A well-formed update whose expected_digest predates the create is a stale CAS: CONFLICT, no write.
        rejected = ticket(update)
        self.assertTrue(rejected["isError"])
        self.assertEqual(rejected["structuredContent"]["state"], "CONFLICT")
        self.assertEqual(rejected["structuredContent"]["code"], "SOURCE_CONFLICT")
        self.assertEqual(brief.read_bytes(), source_bytes)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_bytes)
        update["expected_digest"] = saved["structuredContent"]["source_digest"]
        edited = ticket(update)
        self.assertFalse(edited["isError"])
        app = App(fixture.codex_home, fixture.config, auto_bridge=transport)
        row = next(r for r in ticket(read)["structuredContent"]["records"] if r["id"] == "model-ticket")
        self.assertEqual((row["label"], row["display_id"]), ("Updated wire goal", "TEST-1"))
        # A saved host root does not authorize a brief naming another project.
        brief.write_text(markdown_fixture(project_fixture("foreign")), encoding="utf-8")
        foreign = brief.read_bytes()
        self.assertTrue(ticket(read)["isError"])
        self.assertTrue(ticket({**update, "expected_digest": edited["structuredContent"]["source_digest"]})["isError"])
        self.assertEqual(brief.read_bytes(), foreign)
        self.assertEqual(app.progress_ledger._state.path.read_bytes(), ledger_bytes)
        self.assertEqual(transport.mock_calls, [])

    def test_native_project_alias_and_legacy_migration_use_production_app(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console import server
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture, views
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        native = "0f6d3f1e-7a2b-4c58-9e11-2b7d1c0a9f33"
        host_state = fixture.codex_home / server.HOST_STATE_FILENAME
        host_state.write_text(json.dumps({
            server.HOST_STATE_PROJECTS_KEY: {native: {"id": native, "name": "alpha", "createdAt": 1, "updatedAt": 2,
                                                     "rootPaths": [str(fixture.root / ".." / fixture.alpha_root.name)]}},
            server.HOST_STATE_PROJECT_MAP_KEY: {"local:" + str(fixture.codex_home.resolve()): {native: "project:alpha"}},
        }), encoding="utf-8")
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture(native, milestones=["Ship the alias", {"id": "m-typed", "state": "active"}])),
                         encoding="utf-8")
        host_bytes, database_bytes, original = host_state.read_bytes(), fixture.database.read_bytes(), brief.read_bytes()
        transport = Mock()
        projection = mcp.SwarmProjection()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=transport)
        read = {"operation": "read", "project_id": native}
        rejected = projection.call("swarm_project_tickets", read)
        self.assertEqual((rejected["ok"], rejected["state"], rejected["project_id"]), (False, "REJECTED", native))
        self.assertEqual(brief.read_bytes(), original)  # Reads never migrate legacy strings.
        _, digest = views.parse_project_brief_markdown(original.decode("utf-8"))
        migrate = {"operation": "migrate_legacy", "project_id": native, "expected_digest": digest, "acknowledge": True}
        for change in ({"acknowledge": False}, {"acknowledge": 1}):
            with self.subTest(change=change), self.assertRaises(mcp.MCPError):
                projection.call("swarm_project_tickets", {**migrate, **change})
        self.assertEqual(projection.call("swarm_project_tickets", {**migrate, "collection": "milestones"})["state"], "REJECTED")
        self.assertEqual(projection.call("swarm_project_tickets", {**migrate, "expected_digest": "sha256:" + "0" * 64})["state"], "CONFLICT")
        self.assertEqual(brief.read_bytes(), original)
        migrated = projection.call("swarm_project_tickets", migrate)
        self.assertEqual((migrated["ok"], migrated["project_id"], migrated["migration"]["counts"]),
                         (True, "project:alpha", {"milestones": 1, "ranked_outcomes": 0}))
        legacy = next(row for row in migrated["records"] if row["label"] == "Ship the alias")
        self.assertEqual((legacy["kind"], legacy["declared_state"], legacy["display_id"]), ("milestone", None, None))
        self.assertEqual(next(row for row in migrated["records"] if row["id"] == "m-typed")["declared_state"], "active")
        self.assertEqual(views.read_brief_content(fixture.alpha_root, migrated["migration"]["history"]), original)
        self.assertEqual(projection.call("swarm_project_tickets", migrate)["state"], "CONFLICT")
        again = projection.call("swarm_project_tickets", {**migrate, "expected_digest": migrated["source_digest"]})
        self.assertEqual((again["source_digest"], again["migration"]["counts"]), (migrated["source_digest"], {"milestones": 0, "ranked_outcomes": 0}))
        current = projection.call("swarm_project_tickets", read)
        self.assertEqual((current["source_digest"], current["records"]), (migrated["source_digest"], migrated["records"]))
        self.assertEqual(projection.call("swarm_project_tickets", {**read, "project_id": "project:alpha"})["records"], current["records"])
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=transport)
        self.assertEqual(projection.call("swarm_project_tickets", read)["source_digest"], migrated["source_digest"])
        self.assertEqual(views.parse_project_brief_markdown(brief.read_text(encoding="utf-8"))[0]["project"]["id"], native)
        self.assertEqual((host_state.read_bytes(), fixture.database.read_bytes()), (host_bytes, database_bytes))
        self.assertFalse(projection._app.progress_ledger._state.path.exists())
        self.assertEqual(transport.mock_calls, [])

    def test_ticket_write_uncertainty_is_typed_and_reserved_identity_survives_restart(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console import server
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture("alpha")), encoding="utf-8")
        transport = Mock()
        projection = mcp.SwarmProjection()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=transport)
        read = {"operation": "read", "project_id": "project:alpha"}
        request = {**read, "operation": "create", "acknowledge": True, "collection": "goals",
                   "record_id": "reserved-first", "changes": {"label": "Proof goal"}, "project_code": "TEST",
                   "expected_digest": projection.call("swarm_project_tickets", read)["source_digest"]}
        before = brief.read_bytes()
        module = sys.modules[server.mutate_project_tickets.__module__]
        with patch.object(module, "_replace_brief_bytes", side_effect=OSError("private/path/SWARM.md")):
            result = projection.call("swarm_project_tickets", request)
        self.assertEqual((result["ok"], result["state"], result["code"]),
                         (False, "REJECTED", "SOURCE_WRITE_UNCERTAIN"))
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(brief.read_bytes(), before)
        ledger_path = projection._app.progress_ledger._state.path
        reserved = ledger_path.read_bytes()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=transport)
        saved = projection.call("swarm_project_tickets", request)
        self.assertEqual(next(r for r in saved["records"] if r["id"] == "reserved-first")["display_id"], "TEST-1")
        self.assertEqual(sum(r["id"] == "reserved-first" for r in saved["records"]), 1)
        self.assertEqual(ledger_path.read_bytes(), reserved)
        second = {**request, "record_id": "reserved-second", "expected_digest": saved["source_digest"]}
        with patch.object(module, "_replace_brief_bytes", side_effect=OSError("private/path")):
            self.assertEqual(projection.call("swarm_project_tickets", second)["code"], "SOURCE_WRITE_UNCERTAIN")
        reserved = ledger_path.read_bytes()
        edited = projection.call("swarm_project_tickets", {**read, "operation": "update", "acknowledge": True,
            "collection": "goals", "record_id": "reserved-first", "expected_digest": saved["source_digest"],
            "changes": {"label": "Another author's edit"}})
        source = brief.read_bytes()
        projection._app = server.App(fixture.codex_home, fixture.config, auto_bridge=transport)
        retry = {**second, "expected_digest": edited["source_digest"]}
        self.assertEqual(projection.call("swarm_project_tickets", retry)["code"], "RECORD_ID_RESERVED")
        self.assertEqual(brief.read_bytes(), source)
        self.assertEqual(ledger_path.read_bytes(), reserved)
        fresh = projection.call("swarm_project_tickets", {**retry, "record_id": "fresh-third"})
        self.assertEqual(next(r for r in fresh["records"] if r["id"] == "fresh-third")["display_id"], "TEST-3")
        self.assertEqual(transport.mock_calls, [])

    def test_ticket_tool_real_app_prefix_retry_reload_and_no_dispatch(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console.server import App
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture("alpha")), encoding="utf-8")
        transport = Mock()
        projection = mcp.SwarmProjection()
        projection._app = App(fixture.codex_home, fixture.config, auto_bridge=transport)
        read = {"operation": "read", "project_id": "project:alpha"}
        initial = projection.call("swarm_project_tickets", read)
        request = {**read, "operation": "create", "expected_digest": initial["source_digest"],
                   "acknowledge": True, "collection": "goals", "record_id": "proof-ticket", "changes": {"label": "Proof goal"}}
        before = brief.read_bytes()
        self.assertEqual(projection.call("swarm_project_tickets", request)["code"], "PROJECT_CODE_REQUIRED")
        self.assertEqual(brief.read_bytes(), before)
        self.assertFalse(projection._app.progress_ledger._state.path.exists())
        request["project_code"] = "abcd"
        result = projection.call("swarm_project_tickets", request)
        self.assertTrue(result["ok"])
        self.assertEqual(next(r for r in result["records"] if r["id"] == "proof-ticket")["display_id"], "ABCD-1")
        saved = brief.read_bytes()
        ledger = projection._app.progress_ledger._state.path.read_bytes()
        projection._app = App(fixture.codex_home, fixture.config, auto_bridge=transport)
        self.assertTrue(projection.call("swarm_project_tickets", request)["replayed"])
        self.assertEqual(brief.read_bytes(), saved)
        self.assertEqual(projection._app.progress_ledger._state.path.read_bytes(), ledger)
        self.assertEqual(projection.call("swarm_project_tickets", {**request, "changes": {"label": "Changed"}})["state"], "CONFLICT")
        self.assertEqual(projection.call("swarm_project_tickets", {**request, "project_code": "ABCDE"})["code"], "PROJECT_CODE_INVALID")
        self.assertEqual(projection.call("swarm_project_tickets", {**request, "acknowledge": True, "collection": "blocks", "record_id": "orphan",
            "expected_digest": result["source_digest"]})["state"], "REJECTED")
        self.assertEqual(brief.read_bytes(), saved)
        self.assertEqual(projection._app.progress_ledger._state.path.read_bytes(), ledger)
        self.assertEqual(transport.mock_calls, [])

    def test_native_roles_use_existing_authority_replay_and_no_host_dispatch(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console.server import App
        from console.tests.test_console import SwarmConsoleTests
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        bridge = Mock()
        projection = mcp.SwarmProjection()
        projection._app = App(fixture.codex_home, fixture.config, auto_bridge=bridge)
        ledger_path = projection._app.progress_ledger._state.path
        retained = lambda: ledger_path.read_bytes() if ledger_path.exists() else None
        before = retained()
        current = projection.call("swarm_role_read", {})
        self.assertEqual(current["scope"], "global-definitions")
        self.assertEqual(len(current["roles"]), 24)
        self.assertEqual(retained(), before)
        self.assertNotIn("critic", {r["id"] for r in current["roles"]})
        self.assertTrue(all(r["avatar"] is None for r in current["roles"]))
        detail = projection.call("swarm_role_read", {"role_id": "producer"})
        self.assertEqual(detail["cursor"], current["cursor"])
        role = detail["roles"][0]
        # Native media is independently revalidated and bound to this active role version.
        server_role = next(r for r in projection._app.role_manifest_projection()["roles"] if r["id"] == role["id"])
        self.assertEqual(server_role["avatar"]["state"], "AVAILABLE")
        self.assertEqual(role["avatar_asset_digest"], server_role["avatar_asset_digest"])
        self.assertEqual(role.get("avatar_variants"), server_role.get("avatar_variants"))
        self.assertEqual(role["avatar"]["state"], "AVAILABLE")
        self.assertEqual(role["avatar"]["digest"], role["avatar_asset_digest"])
        self.assertEqual(role["avatar"]["manifest_version"], role["active_version"])
        self.assertTrue(role["avatar"]["url"].startswith("data:image/webp;base64,"))
        self.assertNotIn("versions", role)
        self.assertNotIn("source_event_ids", role)
        manifest = {k: role[k] for k in ("name", "purpose", "owns", "instructions", "boundaries", "default_skills", "specializations", "avatar_asset_digest", "avatar_variants", "accent", "lucide_icon") if k in role}
        manifest["purpose"] = "Produce an independently checked result."
        request = {"command": "ROLE_MANIFEST_REVISE", "role_id": role["id"], "manifest": manifest,
                   "expected_active_version": role["active_version"], "event_id": "native-role-one",
                   "dedupe_key": "native-role-one", "provenance": "hq-roles-editor",
                   "observed_at_ms": 1000, "acknowledge": True}
        saved = projection.call("swarm_role_save", request)
        self.assertTrue(saved["ok"])
        updated = next(r for r in saved["roles"] if r["id"] == role["id"])
        self.assertEqual(updated["purpose"], manifest["purpose"])
        self.assertEqual(updated.get("avatar_variants"), manifest.get("avatar_variants"))
        self.assertEqual(updated["active_version"], saved["receipt"]["active_version"])
        self.assertNotEqual(updated["active_version"], role["active_version"])
        self.assertIsNone(updated["avatar"])
        preview = projection.call("swarm_role_read", {"role_id": role["id"]})["roles"][0]["avatar"]
        self.assertEqual(preview["manifest_version"], updated["active_version"])
        self.assertEqual(preview["render_digest"], role["avatar"]["render_digest"])
        written = retained()
        projection._app = App(fixture.codex_home, fixture.config, auto_bridge=bridge)
        replay = projection.call("swarm_role_save", request)
        self.assertTrue(replay["ok"])
        self.assertEqual(replay["receipt"]["status"], "unchanged")
        self.assertEqual(replay["roles"], saved["roles"])
        self.assertEqual(retained(), written)
        self.assertEqual(projection.call("swarm_role_read", {"role_id": role["id"]})["roles"][0]["avatar"], preview)
        self.assertEqual(retained(), written)
        stale = {**request, "event_id": "native-role-two", "dedupe_key": "native-role-two"}
        self.assertEqual(projection.call("swarm_role_save", stale)["state"], "CONFLICT")
        changed_identity = {**request, "manifest": {**manifest, "purpose": "Conflicting retry"}}
        self.assertEqual(projection.call("swarm_role_save", changed_identity)["state"], "CONFLICT")
        self.assertEqual(retained(), written)
        for extra in ({"acknowledge": False}, {"acknowledge": 1}, {"command": "ROLE_ASSIGNMENT_BOUND"}, {"project_id": "foreign"}):
            with self.subTest(extra=extra), self.assertRaises(mcp.MCPError):
                projection.call("swarm_role_save", {**request, **extra})
        with self.assertRaises(mcp.MCPError):
            projection.call("swarm_role_save", {k: v for k, v in request.items() if k != "acknowledge"})
        rejected = {**stale, "expected_active_version": updated["active_version"],
                    "manifest": {**manifest, "avatar_asset_digest": "0" * 64}}
        self.assertEqual(projection.call("swarm_role_save", rejected)["state"], "REJECTED")
        self.assertEqual(retained(), written)
        self.assertEqual(bridge.mock_calls, [])
        wire = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "swarm_role_save", "arguments": stale}}
        with patch.object(mcp.SwarmProjection, "_load_app", return_value=projection._app), patch.object(sys, "stdin", io.StringIO(json.dumps(wire))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve(telemetry_path=fixture.root / "roles-wire.jsonl")
        outcome = json.loads(output.getvalue())["result"]
        self.assertTrue(outcome["isError"])
        self.assertEqual(outcome["structuredContent"]["state"], "CONFLICT")
        self.assertNotIn(manifest["purpose"], (fixture.root / "roles-wire.jsonl").read_text())
        custom = {k: v for k, v in request.items() if k != "expected_active_version"}
        custom.update(command="ROLE_MANIFEST_CREATE", role_id="native-scribe",
                      event_id="native-role-create", dedupe_key="native-role-create",
                      manifest={**manifest, "name": "Native Scribe", "specializations": []})
        created = projection.call("swarm_role_save", custom)
        self.assertTrue(created["ok"])
        self.assertEqual(len(created["roles"]), 25)
        self.assertEqual(next(r for r in created["roles"] if r["id"] == "native-scribe")["source"], "custom")
        before_critic = retained()
        self.assertEqual(projection.call("swarm_role_save", {**custom, "role_id": "Critic",
            "event_id": "native-critic", "dedupe_key": "native-critic"})["state"], "REJECTED")
        self.assertEqual(retained(), before_critic)
        reset = {k: v for k, v in request.items() if k != "manifest"}
        reset.update(command="ROLE_MANIFEST_RESET", expected_active_version=updated["active_version"],
                     event_id="native-role-reset", dedupe_key="native-role-reset")
        restored = projection.call("swarm_role_save", reset)
        self.assertTrue(restored["ok"])
        self.assertEqual(next(r for r in restored["roles"] if r["id"] == role["id"])["active_version"], role["active_version"])
        final = retained()
        self.assertTrue(projection.call("swarm_role_save", reset)["ok"])
        self.assertEqual(retained(), final)
        self.assertEqual(projection._app.role_manifest_projection()["assignments"], [])
        self.assertEqual(bridge.mock_calls, [])

    def test_native_roles_wire_rejects_invalid_arguments_before_loading_authority(self):
        projection = mcp.SwarmProjection()
        with patch.object(projection, "_load_app", side_effect=AssertionError("must not load")):
            for name, args in [("swarm_role_read", {"path": "private"}), ("swarm_role_read", {"role_id": None}),
                               ("swarm_role_read", {"role_id": " "}), ("swarm_role_save", {}),
                               ("swarm_role_save", {"command": "ROLE_MANIFEST_RESET", "acknowledge": True})]:
                with self.subTest(name=name, args=args), self.assertRaises(mcp.MCPError):
                    projection.call(name, args)
        tools = {t["name"]: t for t in mcp.TOOLS}
        for name in ["swarm_role_read", "swarm_role_save"]:
            self.assertEqual(tools[name]["_meta"]["ui"]["visibility"], ["app"])
        self.assertTrue(tools["swarm_role_read"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["swarm_role_save"]["annotations"]["readOnlyHint"])

    def test_library_mcp_save_readback_restart_and_invalid_write(self):
        sys.path.insert(0, str(mcp.REPO_ROOT))
        from console.server import App
        from console.tests.test_console import SwarmConsoleTests
        from console.tests.test_project_model_views import project_fixture, markdown_fixture
        fixture = SwarmConsoleTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        brief = fixture.alpha_root / "SWARM.md"
        brief.write_text(markdown_fixture(project_fixture("alpha")), encoding="utf-8")
        bridge = Mock()
        app = App(fixture.codex_home, fixture.config, auto_bridge=bridge)
        projection = mcp.SwarmProjection()
        projection._app = app
        scope = {"project_id":"project:alpha", "kind":"ROLE"}
        initial = projection.call("swarm_library_read", scope)
        self.assertEqual(len(initial["inventory"]["roles"]), 24)
        saved = projection.call("swarm_flow_save", {"project_id":"project:alpha",
            "expected_digest":initial["source_digest"], "definition":initial["starter"], "acknowledge":True})
        role = next(r for r in initial["inventory"]["roles"] if r["id"] == "manager")
        flow = saved["definitions"][0]
        assignment = dict(version=1, subject_kind="ROLE", subject_id="manager", subject_version=role["active_version"],
            ctrl_id=None, flow_id=flow["id"], flow_version=flow["version"], flow_digest=flow["digest"],
            label="My manager", notes="Planning note", repeat_count=2)
        request = dict(project_id="project:alpha", expected_digest=saved["source_digest"], acknowledge=True, assignment=assignment)
        assigned = projection.call("swarm_flow_assign", request)
        before = brief.read_bytes()
        projection._app = App(fixture.codex_home, fixture.config, auto_bridge=bridge)
        readback = projection.call("swarm_library_read", scope)
        self.assertEqual(readback["assignments"], assigned["assignments"])
        self.assertEqual(readback["source_digest"], assigned["source_digest"])
        self.assertEqual(projection.call("swarm_flow_assign", request)["state"], "CONFLICT")
        for change in ({"acknowledge":False}, {"acknowledge":1}, {"path":"elsewhere"}):
            with self.assertRaises(mcp.MCPError):
                projection.call("swarm_flow_assign", {**request, **change})
        rejected = projection.call("swarm_flow_assign", {**request, "expected_digest":assigned["source_digest"],
            "assignment":{**assignment, "version":2, "repeat_count":0}})
        self.assertEqual(rejected["state"], "REJECTED")
        self.assertFalse(rejected["ok"])
        self.assertEqual(brief.read_bytes(), before)
        self.assertEqual(bridge.mock_calls, [])
        # The real MCP wire marks conflicts as errors and retains structured scope.
        wire = {"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{"name":"swarm_flow_assign", "arguments":request}}
        with patch.object(mcp.SwarmProjection, "_load_app", return_value=projection._app), patch.object(sys, "stdin", io.StringIO(json.dumps(wire))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve(telemetry_path=fixture.root / "mcp-test.jsonl")
        result = json.loads(output.getvalue())["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["state"], "CONFLICT")
        self.assertEqual(result["structuredContent"]["project_id"], "project:alpha")
        event = json.loads((fixture.root / "mcp-test.jsonl").read_text().splitlines()[-1])
        self.assertFalse(event["success"])
        self.assertNotIn("Planning note", json.dumps(event))

        wire["params"]["arguments"] = {**request, "expected_digest":assigned["source_digest"],
            "assignment":{**assignment, "version":2, "label":"\ud800"}}
        with patch.object(mcp.SwarmProjection, "_load_app", return_value=projection._app), patch.object(sys, "stdin", io.StringIO(json.dumps(wire))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve(telemetry_path=fixture.root / "mcp-test.jsonl")
        result = json.loads(output.getvalue())["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["state"], "REJECTED")
        self.assertEqual(brief.read_bytes(), before)
        self.assertNotIn("ud800", (fixture.root / "mcp-test.jsonl").read_text())

    def test_existing_settings_unavailable_is_not_promoted_to_library_error(self):
        app = Mock()
        app.config_projection.return_value = {"ok": False, "state": "UNAVAILABLE"}
        wire = {"jsonrpc":"2.0", "id":1, "method":"tools/call",
            "params":{"name":"swarm_settings_read", "arguments":{}}}
        with tempfile.TemporaryDirectory() as directory, patch.object(mcp.SwarmProjection, "_load_app", return_value=app), patch.object(sys, "stdin", io.StringIO(json.dumps(wire))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve(telemetry_path=Path(directory) / "events.jsonl")
        result = json.loads(output.getvalue())["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"], {"ok":False, "state":"UNAVAILABLE"})

    @contextmanager
    def support_resource(self, root, body):
        """Exercise the real pinned image admission with an isolated template."""
        names = list(mcp.PROJECTS_ASSETS)
        files = {names[0]: ('<!doctype html><style>__CSS__</style><body>' + body + '<script type="module">__SCRIPT__</script></body>').encode(),
                 names[1]: b'body{color:black}', names[2]: b'.swarm-settings{color:white}'}
        for name, _, digest in mcp.PROJECTS_SUPPORT_IMAGES.values():
            files[name] = (mcp.REPO_ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)
        for name, _, digest, size in mcp.PROJECTS_PUBLIC_IMAGES.values():
            files[name] = (mcp.REPO_ROOT / name).read_bytes()
            self.assertEqual(len(files[name]), size)
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)
        for name, payload in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        pins = {name: hashlib.sha256(files[name]).hexdigest() for name in names}
        path, digest, _ = self.hq_export(root)
        with patch.object(mcp, 'REPO_ROOT', root), patch.dict(mcp.PROJECTS_ASSETS, pins, clear=True):
            yield mcp.HQApp(path, digest, projects=True)

    def test_original_wordmark_uses_existing_public_delivery(self):
        expected = ("skills/swarm/assets/swarm-wordmark.png",
                    "https://flowwweb.com/brand/swarm/swarm-wordmark.png",
                    "306c1549fa5195e0211d9d062fccdfc1b1241de3eda82c97ed8cb42ecdbcf6d2", 423870)
        self.assertEqual(mcp.PROJECTS_PUBLIC_IMAGES["__WORDMARK__"], expected)
        self.assertNotIn("__WORDMARK__", mcp.PROJECTS_SUPPORT_IMAGES)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.support_resource(root, '<img alt="SWARM" src="__WORDMARK__">') as app:
                before = app.path.read_bytes()
                resource = app.resource()['contents'][0]
                self.assertIn('<img alt="SWARM" src="' + expected[1] + '">', resource['text'])
                self.assertEqual(image_sources(resource['text']), [expected[1]])
                self.assertEqual(app.path.read_bytes(), before)
                self.assertEqual(hashlib.sha256((root / expected[0]).read_bytes()).hexdigest(), expected[2])
                (root / expected[0]).write_bytes(b'changed')
                with self.assertRaises(mcp.MCPError):
                    app.resource()

    def test_support_exact_images_admitted_without_snapshot_write(self):
        import base64
        self.assertEqual(mcp.PROJECTS_SUPPORT_IMAGES["__PROFILE_MASCOT__"],
                         ("console/static/swarm-mascot-512.png", "image/png",
                          "247fc2a02b5505c13815d78c4cce8765b893f51b70cf9167d1e2d43350209666"))
        self.assertEqual(mcp.PROJECTS_SUPPORT_IMAGES["__FLOWWWEB_LOGO_DARK__"],
                         ("skills/swarm/assets/ui/brand/flowwweb-lockup-v2-dark.svg", "image/svg+xml",
                          "cbc1bb458ab73cf7ac89972e7f087ae93a9a65902b1a4926b05484eaa90e9a11"))
        self.assertEqual(mcp.PROJECTS_SUPPORT_IMAGES["__FLOWWWEB_LOGO__"][2],
                         "57253bfef4d4f26c399dbb1d5fb2f258d663b52d31dd1414ab7c9cfef808d7b3")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = ''.join('<img src="' + token + '">' for token in mcp.PROJECTS_SUPPORT_IMAGES)
            with self.support_resource(root, body) as app:
                before = app.path.read_bytes()
                rendered = app.resource()['contents'][0]['text']
                for token, (name, mime, _) in mcp.PROJECTS_SUPPORT_IMAGES.items():
                    self.assertNotIn(token, rendered)
                    self.assertIn('data:' + mime + ';base64,' + base64.b64encode((root / name).read_bytes()).decode(), rendered)
                self.assertLessEqual(len(rendered.encode()), 1179648)
                self.assertEqual(before, app.path.read_bytes())
                self.assertEqual(app.uri, 'ui://swarm/hq/' + hashlib.sha256(rendered.encode()).hexdigest() + '.html')

    def test_support_missing_changed_and_oversized_images_fail_closed(self):
        for token, (name, _, _) in mcp.PROJECTS_SUPPORT_IMAGES.items():
            for failure in ('missing', 'changed', 'oversized'):
                with self.subTest(token=token, failure=failure), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    with self.support_resource(root, '<img src="' + token + '">') as app:
                        target = root / name
                        if failure == 'missing':
                            target.unlink()
                        else:
                            target.write_bytes(b'changed' if failure == 'changed' else b'x' * 524289)
                        with self.assertRaises((OSError, mcp.MCPError)):
                            app.resource()

    def test_support_unknown_badge_and_expanded_resource_limit_fail_closed(self):
        for body, error in (('<img src="__ROADTO1M_LOGO__">', 'unadmitted placeholder'),
                            ('<img src="__FLOWWWEB_LOGO__">' * 224, 'exceeds its bound')):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(mcp.MCPError, error):
                    with self.support_resource(Path(directory), body):
                        self.fail('Invalid resource was admitted')

    def test_compact_badge_uses_exact_public_url_and_only_resource_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.support_resource(Path(directory), '<footer><img src="__ROADTO1M_COMPACT__"></footer>') as app:
                resource = app.resource()['contents'][0]
                name, url, digest, _ = mcp.PROJECTS_COMPACT_BADGE
                self.assertIn('<footer><img src="' + url + '"></footer>', resource['text'])
                self.assertNotIn('__ROADTO1M_COMPACT__', resource['text'])
                self.assertNotIn('data:image/png;base64,', resource['text'])
                self.assertEqual(resource['_meta']['ui']['csp'], {'connectDomains': [], 'resourceDomains': ['https://flowwweb.com']})
                self.assertLessEqual(len(resource['text'].encode()), 1179648)
                # Remote provenance does not relax the ordinary inline image cap.
                with self.assertRaises(mcp.MCPError):
                    mcp._projects_asset(name, digest)

    def test_compact_badge_local_provenance_missing_or_changed_withholds_resource(self):
        for failure in ('missing', 'same_size_changed', 'short', 'growing'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.support_resource(root, '<img src="__ROADTO1M_COMPACT__">') as app:
                    name, _, _, size = mcp.PROJECTS_COMPACT_BADGE
                    target = root / name
                    if failure == 'missing':
                        target.unlink()
                    else:
                        target.write_bytes(b'x' * (size + {'same_size_changed': 0, 'short': -1, 'growing': 1}[failure]))
                    with self.assertRaises((OSError, mcp.MCPError)):
                        app.resource()

    def test_portrait_public_admission_preserves_exact_local_provenance_and_alt(self):
        token = '__SUPPORT_PORTRAIT__'
        name, url, digest, size = mcp.PROJECTS_PUBLIC_IMAGES[token]
        self.assertEqual(url, 'https://flowwweb.com/brand/swarm/support-caricature-light-20261024-18b223c6.webp')
        for failure in (None, 'missing', 'changed', 'short', 'growing'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.support_resource(root, '<img src="' + token + '" alt="Portrait unavailable">') as app:
                    target = root / name
                    before = target.read_bytes()
                    self.assertEqual(hashlib.sha256(before).hexdigest(), digest)
                    if failure:
                        if failure == 'missing':
                            target.unlink()
                        else:
                            target.write_bytes(b'x' * (size + {'changed': 0, 'short': -1, 'growing': 1}[failure]))
                        with self.assertRaises((OSError, mcp.MCPError)):
                            app.resource()
                    else:
                        resource = app.resource()['contents'][0]
                        self.assertIn('<img src="' + url + '" alt="Portrait unavailable">', resource['text'])
                        self.assertEqual(image_sources(resource['text']), [url])
                        self.assertEqual(resource['_meta']['ui']['csp'],
                                         {'connectDomains': [], 'resourceDomains': ['https://flowwweb.com']})
                        self.assertEqual(before, target.read_bytes())

    def test_selected_project_preserves_retained_ticket_fields_only_in_its_scope(self):
        row = {"id": "host-task", "project_id": "project-a", "state": "active",
               "display_id": "SWRM-1", "label": "Retained task name", "private": "omit"}
        view = {"overview_metrics": {"accepted_scope_id": "project-a", "accepted_cursor": {"digest": "bound"}},
                "progress": {"task_identity": {"digest": "ledger-bound"}, "projects": {
                    "project-a": {"tasks": [row]}, "project-b": {"tasks": [{**row, "project_id": "project-b"}]}}}}
        view["progress"]["all_projects"] = {"tasks": [row]}
        view["progress"]["controllers"] = {"ctrl-a": {"tasks": [row]}}
        result = mcp._compact_overview(view)
        self.assertEqual(result["progress"]["projects"]["project-a"]["tasks"], [{k: v for k, v in row.items() if k != "private"}])
        self.assertNotIn("tasks", result["progress"]["projects"]["project-b"])
        self.assertEqual(result["progress"]["task_identity"], {"digest": "ledger-bound"})
        for selected in ("project-a", "all"):
            view["overview_metrics"]["accepted_scope_id"] = selected
            compact = mcp._compact_overview(view)["progress"]
            for aggregate in (compact["all_projects"], compact["controllers"]["ctrl-a"]):
                self.assertEqual(aggregate["tasks"], [{k: v for k, v in row.items() if k not in {"private", "display_id", "label"}}])
        view["overview_metrics"]["accepted_scope_id"] = "all"
        self.assertTrue(all("tasks" not in scope for scope in mcp._compact_overview(view)["progress"]["projects"].values()))

    def test_projects_shell_composes_settings_without_rewriting_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest, _ = self.hq_export(Path(directory))
            before = path.read_bytes()
            app = mcp.HQApp(path, digest, projects=True)
            rendered = app.render()
            self.assertIn('id="all-projects"', rendered)
            self.assertIn('id="settings"', rendered)
            self.assertIn(mcp.PROJECTS_PUBLIC_IMAGES['__WORDMARK__'][1], rendered)
            self.assertNotIn('__WORDMARK__', rendered)
            self.assertNotIn('__SCRIPT__', rendered)
            self.assertEqual(rendered.count('data-swarm-mcp-sdk='), 1)
            self.assertLessEqual(len(rendered.encode()), 1179648)
            self.assertEqual(app.uri, 'ui://swarm/hq/' + hashlib.sha256(rendered.encode()).hexdigest() + '.html')
            self.assertEqual(path.read_bytes(), before)
            key = next(iter(mcp.PROJECTS_ASSETS))
            with patch.dict(mcp.PROJECTS_ASSETS, {key: '0' * 64}), self.assertRaisesRegex(mcp.MCPError, 'identity mismatch'):
                app.render()

    def test_settings_bridge_uses_existing_config_authority_and_exact_retry(self):
        projection = mcp.SwarmProjection()
        app = Mock()
        projection._app = app
        scope = {"kind": "project", "project_id": "project-a", "accepted_cursor": "cursor-a"}
        app.config_projection.return_value = {"scope": scope, "revision": "a" * 64}
        self.assertEqual(projection.call("swarm_settings_read", {"scope": scope}), app.config_projection.return_value)
        app.config_projection.assert_called_once_with(scope)
        request = {"scope": scope, "expected_revision": "a" * 64, "acknowledge": True,
                   "text": '[execution]\nfast_mode = true\n', "operation_id": "settings-one"}
        app.update_config_source.return_value = {"accepted": True, "receipt": {"operation_id": "settings-one"}}
        self.assertEqual(projection.call("swarm_settings_save", request), app.update_config_source.return_value)
        projection.call("swarm_settings_save", dict(request))
        self.assertEqual(app.update_config_source.call_count, 2)
        self.assertEqual(app.update_config_source.call_args_list[0], app.update_config_source.call_args_list[1])
        for patch_value in ({"acknowledge": False}, {"acknowledge": 1}, {"scope": "global"}, {"operation_id": ""}, {"extra": True}):
            with self.subTest(patch_value=patch_value), self.assertRaises(mcp.MCPError):
                projection.call("swarm_settings_save", {**request, **patch_value})
        self.assertEqual(app.update_config_source.call_count, 2)
        app.update_config_source.side_effect = ValueError("stale revision")
        with self.assertRaisesRegex(ValueError, "stale revision"):
            projection.call("swarm_settings_save", request)

    def hq_export(self, root, **changes):
        html = '<!doctype html><title>Contract fixture only</title>'
        value = {"status": "READY_SOURCE_BOUND_SPACE_HTML_NOT_PUBLISHED", "html": html,
                 "html_sha256": hashlib.sha256(html.encode()).hexdigest(), "size_bytes": len(html.encode()),
                 "snapshot_digest": "sha256:" + "1" * 64, "approval_verified": False, "destination": None}
        value.update(changes)
        path = root / "export.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest(), value

    def test_hq_resource_read_accepts_protocol_meta_and_reports_only_stale_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest, _ = self.hq_export(Path(directory))
            app = mcp.HQApp(path, digest)
            expected = app.uri[len("ui://swarm/hq/"):-len(".html")]
            stale = "a" * 64
            cases = [
                {"uri": app.uri},
                {"uri": app.uri, "_meta": {"progressToken": "META-SECRET", "openai/widget": {"nested": [1]}}},
                {"uri": app.uri, "_meta": {}},
                {"uri": app.uri, "_meta": None},
                {"uri": app.uri, "_meta": "META-SECRET"},
                {"uri": app.uri, "_meta": ["META-SECRET"]},
                {"uri": app.uri, "FIELD-SECRET": 1},
                {"_meta": {}},
                {"uri": 7},
                {"uri": f"ui://swarm/hq/{stale}.html", "_meta": {"progressToken": "META-SECRET"}},
                {"uri": f"ui://swarm/hq/{stale.upper()}.html"},
                {"uri": f"ui://swarm/hq/{stale}.html?URI-SECRET"},
                {"uri": "file:///URI-SECRET"},
            ]
            lines = [json.dumps({"jsonrpc": "2.0", "id": index, "method": "resources/read", "params": params})
                     for index, params in enumerate(cases)]
            before = path.read_bytes()
            with patch.object(mcp.SwarmProjection, "_load_app", side_effect=AssertionError("no host load")), \
                    patch.object(mcp, "_telemetry", side_effect=AssertionError("no telemetry write")), \
                    patch.object(sys, "stdin", io.StringIO("\n".join(lines))), \
                    patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                self.assertEqual(mcp.serve(hq_app=app), 0)
            rows = {row["id"]: row for row in map(json.loads, output.getvalue().splitlines())}
            self.assertEqual(len(rows), len(cases))
            served = rows[0]["result"]
            self.assertEqual(served["contents"][0]["uri"], app.uri)
            self.assertEqual(hashlib.sha256(served["contents"][0]["text"].encode()).hexdigest(), expected)
            for index in (1, 2):
                self.assertEqual(rows[index]["result"], served)
            for index in (3, 4, 5, 6, 7, 8):
                self.assertEqual(rows[index]["error"], {"code": -32602, "message": "invalid HQ resource request"})
            self.assertEqual(rows[9]["error"], {"code": -32602, "message": "stale HQ resource identity",
                                                "data": {"expected_sha256": expected, "received_sha256": stale}})
            for index in (10, 11, 12):
                self.assertEqual(rows[index]["error"], {"code": -32602, "message": "unknown HQ resource"})
            errors = "".join(json.dumps(rows[index]) for index in range(3, len(cases)))
            for secret in ("META-SECRET", "FIELD-SECRET", "URI-SECRET", "progressToken", "openai/widget", stale.upper()):
                self.assertNotIn(secret, errors)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])

        unbound = {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                   "params": {"uri": f"ui://swarm/hq/{'b' * 64}.html", "_meta": {}}}
        with patch.object(mcp, "_telemetry", side_effect=AssertionError("no telemetry write")), \
                patch.object(sys, "stdin", io.StringIO(json.dumps(unbound))), \
                patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            self.assertEqual(mcp.serve(), 0)
        self.assertEqual(json.loads(output.getvalue())["error"], {"code": -32602, "message": "unknown HQ resource"})

    def test_hq_settings_style_requires_exact_safe_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest, _ = self.hq_export(root)
            name = "skills/swarm/assets/ui/swarm-settings.css"
            css = root / name
            css.parent.mkdir(parents=True)
            css.write_text(".swarm-settings{color:white}", encoding="utf-8")
            with patch.object(mcp, "REPO_ROOT", root), patch.dict(mcp.PROJECTS_ASSETS, {name: "0" * 64}):
                with self.assertRaisesRegex(mcp.MCPError, "identity mismatch"):
                    mcp.HQApp(path, digest)
            payload = b".swarm-settings{color:white}</style><script>alert(1)</script>"
            css.write_bytes(payload)
            with patch.object(mcp, "REPO_ROOT", root), patch.dict(mcp.PROJECTS_ASSETS, {name: hashlib.sha256(payload).hexdigest()}):
                with self.assertRaisesRegex(mcp.MCPError, "stylesheet cannot be embedded"):
                    mcp.HQApp(path, digest)

    def test_hq_resource_uses_exact_export_without_host_access_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest, value = self.hq_export(Path(directory))
            app = mcp.HQApp(path, digest)
            requests = [("initialize", {}), ("tools/list", {}), ("resources/list", {}),
                        ("resources/read", {"uri": app.uri}), ("tools/call", {"name": "swarm_hq_view"}),
                        ("resources/read", {"uri": "file:///private"}),
                        ("tools/call", {"name": "swarm_hq_view", "arguments": {"path": "private"}})]
            lines = [json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) for i, (method, params) in enumerate(requests)]
            before = path.read_bytes()
            with patch.object(mcp.SwarmProjection, "_load_app", side_effect=AssertionError("no host load")), patch.object(mcp, "_telemetry", side_effect=AssertionError("no telemetry write")), patch.object(sys, "stdin", io.StringIO("\n".join(lines))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                self.assertEqual(mcp.serve(hq_app=app), 0)
            rows = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertIn("resources", rows[0]["result"]["capabilities"])
            self.assertEqual(rows[1]["result"]["tools"][:14], list(mcp.TOOLS))
            self.assertEqual(len(rows[1]["result"]["tools"]), 15)
            tool = rows[1]["result"]["tools"][-1]
            self.assertEqual(tool["name"], "swarm_hq_view")
            self.assertEqual(tool["_meta"], {"ui": {"resourceUri": app.uri}, "openai/ui": {"entrypoints": [{"type": "global"}, {"type": "thread"}]}})
            self.assertEqual(rows[2]["result"]["resources"][0]["uri"], app.uri)
            resource = rows[3]["result"]["contents"][0]
            self.assertTrue(resource["text"].startswith(value["html"]))
            self.assertIn('data-swarm-mcp-sdk="' + mcp.HQ_SDK_SHA256, resource["text"])
            settings_name = "skills/swarm/assets/ui/swarm-settings.css"
            css = (mcp.REPO_ROOT / settings_name).read_text(encoding="utf-8")
            self.assertEqual(resource["text"].count('data-swarm-settings-css="'), 1)
            self.assertIn('<style data-swarm-settings-css="' + mcp.PROJECTS_ASSETS[settings_name] + '">' + css + '</style>', resource["text"])
            self.assertLess(resource["text"].index('data-swarm-settings-css='), resource["text"].index('data-swarm-mcp-sdk='))
            served_digest = hashlib.sha256(resource["text"].encode()).hexdigest()
            self.assertEqual(app.uri, f"ui://swarm/hq/{served_digest}.html")
            # The Page/export cap remains 256 KiB; the separate adapted MCP resource is bounded at 1 MiB.
            self.assertGreater(len(resource["text"].encode()), 262144)
            self.assertLessEqual(len(resource["text"].encode()), 1048576)
            self.assertEqual(resource["mimeType"], "text/html;profile=mcp-app")
            self.assertEqual(resource["_meta"]["ui"]["csp"], {"connectDomains": [], "resourceDomains": []})
            self.assertEqual(rows[4]["result"]["structuredContent"]["snapshot_digest"], value["snapshot_digest"])
            self.assertFalse(rows[4]["result"]["structuredContent"]["approval_verified"])
            self.assertFalse(rows[4]["result"]["structuredContent"]["live"])
            self.assertEqual(rows[4]["result"]["structuredContent"]["served_html_sha256"], served_digest)
            self.assertEqual(rows[4]["result"]["structuredContent"]["refresh"], "PINNED_SNAPSHOT_REEXPORT_REQUIRED")
            self.assertEqual(rows[5]["error"]["code"], -32602)
            self.assertTrue(rows[6]["result"]["isError"])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_hq_sdk_and_resource_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest, _ = self.hq_export(root)
            app = mcp.HQApp(path, digest)
            sdk = root / "sdk.js"
            sdk.write_bytes(b"changed")
            with patch.object(mcp, "HQ_SDK_PATH", sdk), self.assertRaisesRegex(mcp.MCPError, "SDK changed"):
                app.resource()
            with patch.object(mcp, "HQ_SDK_PATH", root / "missing.js"), self.assertRaises(OSError):
                app.result()
            sdk.write_bytes(b"</script>")
            with patch.object(mcp, "HQ_SDK_PATH", sdk), patch.object(mcp, "HQ_SDK_SHA256", hashlib.sha256(sdk.read_bytes()).hexdigest()), self.assertRaisesRegex(mcp.MCPError, "embedded"):
                app.resource()

    def test_hq_changed_missing_and_invalid_exports_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest, value = self.hq_export(root)
            app = mcp.HQApp(path, digest)
            with self.assertRaises(mcp.MCPError):
                mcp.HQApp(path, "wrong")
            path.write_text("changed", encoding="utf-8")
            with self.assertRaises(mcp.MCPError):
                app.resource()
            for changes in ({"html_sha256": "0" * 64}, {"size_bytes": 1}, {"approval_verified": True},
                            {"destination": "invented"}, {"snapshot_digest": "missing"},
                            {"status": "READY"}, {"html": "x" * 262145}):
                with self.subTest(changes=list(changes)):
                    path, digest, _ = self.hq_export(root, **changes)
                    with self.assertRaises(mcp.MCPError):
                        mcp.HQApp(path, digest)
            path.unlink()
            with self.assertRaises(OSError):
                app.result()

    def test_hq_optional_capability_does_not_change_default_tools_or_resources(self):
        requests = [{"jsonrpc": "2.0", "id": i, "method": method} for i, method in enumerate(("initialize", "tools/list", "resources/list"))]
        with patch.object(sys, "stdin", io.StringIO("\n".join(map(json.dumps, requests)))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            mcp.serve()
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertNotIn("resources", rows[0]["result"]["capabilities"])
        self.assertEqual(rows[1]["result"]["tools"], list(mcp.TOOLS))
        self.assertEqual(rows[2]["result"], {"resources": []})

    def test_all_projection_tools_use_existing_app(self) -> None:
        app = Mock()
        app.overview.return_value = {"nodes": [{"id": "task", "secret": "excluded"}], "projects": []}
        app.project_roster.return_value = {"projects": [{"id": "project"}], "current_work": {"state": "KNOWN", "available": True, "project_ids": ["project"], "projects": [{"id": "project"}], "controllers": [{"id": "ctrl"}]}}
        app.usage_history.return_value = {"hours": 24, "coverage": "local"}
        projection = mcp.SwarmProjection()
        projection._app = app
        self.assertEqual(projection.call("swarm_status", {"project_id": " project "})["nodes"], [{"id": "task"}])
        app.overview.assert_called_once_with("project")
        roster = projection.call("swarm_projects", {})
        self.assertEqual(roster["current_work"]["controllers"], [{"id": "ctrl"}])
        self.assertEqual(projection.call("swarm_usage", {})["coverage"], "local")
        app.usage_history.assert_called_once_with(hours=24, include_verified_yield=False)
        self.assertEqual(app.refresh_native_observation.call_args_list,
                         [unittest.mock.call(), unittest.mock.call(), unittest.mock.call(sample_usage=True)])
        app.refresh_native_observation.reset_mock()
        for name, arguments in [("unknown", {}), ("swarm_status", {"project_id": ""}), ("swarm_status", {"project_id": None}), ("swarm_usage", {"hours": True}), ("swarm_usage", {"hours": 2}), ("swarm_projects", {"unexpected": 1})]:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(mcp.MCPError):
                projection.call(name, arguments)
        app.refresh_native_observation.assert_not_called()

    def test_compact_roster_preserves_observation_without_paths_or_icon_authority(self):
        row = {"id": "p", "name": "Saved project", "activity_status": "unknown",
            "root_binding": {"status": "KNOWN", "availability": "MISSING",
                "source": "codex.project_roots", "value": "PRIVATE_PATH"},
            "provenance": {"source": "codex.projects+codex.project_roots",
                "machine_ownership": "UNKNOWN", "archive_state": "UNKNOWN"},
            "logo": {"status": "KNOWN", "artifact": "https://untrusted.invalid/icon.png"}}
        result = mcp._compact_roster({"projects": [row], "cursor": {"digest": "retained"}})
        projected = result["projects"][0]
        self.assertEqual(projected["root_binding"]["availability"], "MISSING")
        self.assertEqual(projected["provenance"], row["provenance"])
        self.assertEqual(projected["logo"], {"status": "UNKNOWN", "artifact": None})
        self.assertNotIn("PRIVATE_PATH", json.dumps(result))
        self.assertNotIn("https://", json.dumps(result))
        self.assertEqual(result["cursor"], {"digest": "retained"})

    def test_stdio_invalid_requests_recover_and_errors_are_redacted(self) -> None:
        requests = ['{', '[]', 'null', '1', '{"jsonrpc":"2.0","id":[],"method":"tools/list"}']
        requests += [json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) for i, method, params in [
            (1, "initialize", []), (2, "tools/call", {"name": "swarm_status", "arguments": []}),
            (3, "tools/call", {"name": "swarm_status"}), (4, "tools/call", {"name": "swarm_projects"}),
            (5, "tools/call", {"name": "swarm_usage"}), (6, "tools/list", {}),
        ]]
        app = Mock()
        app.overview.side_effect = RuntimeError("SECRET credential path")
        app.project_roster.return_value = {"current_work": {}}
        app.usage_history.return_value = {"hours": 24}
        with tempfile.TemporaryDirectory() as directory, patch.object(mcp.SwarmProjection, "_load_app", return_value=app), patch.object(sys, "stdin", io.StringIO("\n".join(requests))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            telemetry = Path(directory) / "telemetry.jsonl"
            self.assertEqual(mcp.serve(telemetry_path=telemetry), 0)
            rows = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(rows[0]["error"]["code"], -32700)
            self.assertTrue(rows[7]["result"]["isError"])
            self.assertFalse(rows[8]["result"]["isError"])
            self.assertFalse(rows[9]["result"]["isError"])
            self.assertEqual(len(rows[-1]["result"]["tools"]), 14)
            self.assertNotIn("SECRET", output.getvalue() + telemetry.read_text())

    def test_output_cap_and_scratch_validation(self) -> None:
        usage = mcp._compact_usage({"items": [{"bucket_ms": i*60000, "delta_tokens": 1} for i in range(300)],
                                   "total_tokens": 300, "window": {"after_ms": 0, "before_ms": 300*60000},
                                   "task_history": {"items": ["detail"], "status": "PARTIAL"}, "verified_yield": {"detail": "omitted"}})
        self.assertEqual(len(usage["items"]), 256)
        self.assertTrue(usage["truncated"])
        self.assertEqual(usage["task_history"], {"status": "PARTIAL"})
        self.assertNotIn("verified_yield", usage)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, arguments in [("probe_write_file", {"name": "../outside", "content": "x"}), ("probe_write_file", {"content": "x" * 4097})]:
                with self.assertRaises(mcp.MCPError):
                    mcp._probe(root, name, arguments)
            (root / "probe.txt").write_text("x" * 4097)
            with self.assertRaises(mcp.MCPError):
                mcp._probe(root, "probe_read_file", {})
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "swarm_usage"}}
            with patch.object(mcp.SwarmProjection, "call", return_value={"large": "x" * 262144}), patch.object(sys, "stdin", io.StringIO(json.dumps(request))), patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                mcp.serve(telemetry_path=root / "telemetry.jsonl")
                self.assertTrue(json.loads(output.getvalue())["result"]["isError"])
                self.assertLess(len(output.getvalue()), 1024)

    def test_usage_continuity_raw_compacted_and_omitted_runs(self):
        from console.server import TOKEN_SAMPLE_SECONDS
        self.assertEqual(TOKEN_SAMPLE_SECONDS * 1000, 60000)  # Bind the projection decoder to the existing store cadence.
        def compact(times):
            original = {"ok":True,"hours":720,"status":"partial", "scope":{"type":"project","project_id":"alpha"},
                "window":{"after_ms":0,"before_ms":30*86400000}, "coverage":{"observed_threads":1,"expected_threads":2},
                "items":[{"bucket_ms":t,"delta_tokens":1} for t in times], "total_tokens":len(times)}
            before = json.dumps(original,sort_keys=True)
            result = mcp._compact_usage(original)
            self.assertEqual(json.dumps(original,sort_keys=True),before)
            self.assertEqual(result,mcp._compact_usage(original))
            for key in ("scope","window","coverage","status","total_tokens"):
                self.assertEqual(result[key],original[key])
            return result
        rows=compact([0,60000,180000])["items"]
        self.assertEqual([r["connect_from_previous"] for r in rows],[False,True,False])
        self.assertEqual([r["bucket_start_ms"] for r in rows],[0,60000,180000])
        self.assertEqual(compact([0])["items"][0]["connect_from_previous"],False)
        times=[i*60000 for i in range(300)]+[(i+301)*60000 for i in range(300)]
        result=compact(times); rows=result["items"]
        self.assertEqual(len(rows),256)
        self.assertEqual(sum(r["delta_tokens"] for r in rows),600)
        self.assertEqual(sum(not r["connect_from_previous"] for r in rows),2)
        self.assertTrue(all(not (r["bucket_start_ms"] < 300*60000 < r["bucket_ms"]) for r in rows))
        for previous,row in zip(rows,rows[1:]):
            self.assertEqual(row["connect_from_previous"],row["bucket_start_ms"]-previous["bucket_ms"]==60000)
        result=compact([i*120000 for i in range(257)])
        self.assertEqual(len(result["items"]),256)
        self.assertTrue(all(not r["connect_from_previous"] for r in result["items"]))
        self.assertEqual(result["items"][0]["bucket_ms"],120000)
        self.assertEqual(result["series_aggregation"]["omitted_input_count"],1)
        self.assertEqual(result["series_aggregation"]["omitted_tokens"],1)
        self.assertEqual(sum(r["delta_tokens"] for r in result["items"])+result["series_aggregation"]["omitted_tokens"],257)
        self.assertTrue(result["truncated"])
        for count in (3,257):
            with self.subTest(count=count),self.assertRaises(mcp.MCPError):
                mcp._compact_usage({"items":[{"bucket_ms":i*60000,"delta_tokens":-1 if i==1 else 1} for i in range(count)],
                    "total_tokens":count,"window":{"after_ms":0,"before_ms":30*86400000}})

    def test_compacted_usage_passes_actual_reader_without_losing_window_deltas(self):
        script = ("import fs from 'node:fs'; "
                  "import {usageView} from './skills/swarm/assets/ui/swarm-usage.mjs'; "
                  "const inputs=JSON.parse(fs.readFileSync(0,'utf8')); "
                  "console.log(JSON.stringify(inputs.map(value=>usageView(value,24))));")
        inputs = []
        for count in (0, 256, 257, 4097):
            items = [{"bucket_ms": 10 + i * 60000, "delta_tokens": i % 7} for i in range(count)]
            view = {"ok": True, "hours": 24, "status": "partial" if count else "no_data",
                    "window": {"after_ms": 10, "before_ms": 4097*60000}, "items": items,
                    "total_tokens": sum(row["delta_tokens"] for row in items),
                    "coverage": {"observed_threads": 1, "expected_threads": 2}}
            compact = mcp._compact_usage(view)
            self.assertEqual(compact, mcp._compact_usage(view))
            self.assertEqual(sum(row["delta_tokens"] for row in compact["items"]), view["total_tokens"])
            self.assertEqual(len(compact["items"]), min(count, 256))
            if count <= 256:
                self.assertEqual(compact["items"], [{**row,"bucket_start_ms":row["bucket_ms"],"connect_from_previous":i>0}
                                                   for i,row in enumerate(items)])
            else:
                self.assertEqual(compact["series_aggregation"]["input_count"], count)
                self.assertEqual(compact["items"][-1]["bucket_ms"], items[-1]["bucket_ms"])
                self.assertTrue(all(row["bucket_ms"] in {item["bucket_ms"] for item in items} for row in compact["items"]))
            inputs.append(compact)
        run = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT.parents[1],
                             input=json.dumps(inputs), text=True, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        for original, rendered in zip(inputs, json.loads(run.stdout)):
            self.assertEqual(rendered["total"], original["total_tokens"] if original["items"] else None)
            self.assertEqual(rendered["coverage"], original["coverage"])
            self.assertEqual(rendered["window"], original["window"])
            self.assertEqual(rendered["status"], original["status"])

    def test_project_usage_forwards_exact_scope_only_when_requested(self):
        spec = next(tool for tool in mcp.TOOLS if tool["name"] == "swarm_usage")
        self.assertEqual(spec["inputSchema"]["properties"]["project_id"], {"type": "string"})
        self.assertFalse(spec["inputSchema"]["additionalProperties"])
        app = Mock()
        projection = mcp.SwarmProjection()
        projection._app = app
        app.usage_history.return_value = {"hours": 168, "scope": {"type": "all-projects"}}
        self.assertEqual(projection.call("swarm_usage", {"hours": 168})["scope"], {"type": "all-projects"})
        app.usage_history.assert_called_once_with(hours=168, include_verified_yield=False)
        for arguments, hours in (({"project_id": " project-a "}, 24), ({"project_id": "project-a", "hours": 720}, 720)):
            with self.subTest(arguments=arguments):
                app.usage_history.reset_mock()
                app.usage_history.return_value = {"hours": hours, "scope": {"type": "project", "project_id": "project-a"}}
                result = projection.call("swarm_usage", arguments)
                app.usage_history.assert_called_once_with(project_id="project-a", hours=hours, include_verified_yield=False)
                self.assertEqual(result["scope"], {"type": "project", "project_id": "project-a"})
        app.usage_history.reset_mock()
        for arguments in ({"project_id": ""}, {"project_id": "   "}, {"project_id": None}, {"project_id": 7},
                          {"project_id": ["project-a"]}, {"project_id": "project-a", "ctrl_id": "ctrl-a"},
                          {"project_id": "project-a", "hours": 2}, {"project_id": "project-a", "hours": True}):
            with self.subTest(arguments=arguments), self.assertRaises(mcp.MCPError):
                projection.call("swarm_usage", arguments)
        app.usage_history.assert_not_called()
        for returned in ({"type": "project", "project_id": "project-b"}, {"type": "all-projects"},
                         {"type": "project", "project_id": " project-a "}, "project-a", None):
            with self.subTest(returned=returned):
                app.usage_history.return_value = {"hours": 24, **({} if returned is None else {"scope": returned})}
                with self.assertRaisesRegex(mcp.MCPError, "scope mismatch"):
                    projection.call("swarm_usage", {"project_id": "project-a"})

    def test_project_usage_compaction_passes_scoped_reader_and_rejects_leakage(self):
        script = ("import fs from 'node:fs'; "
                  "import {usageView} from './skills/swarm/assets/ui/swarm-usage.mjs'; "
                  "const cases=JSON.parse(fs.readFileSync(0,'utf8')); "
                  "console.log(JSON.stringify(cases.map(([value,project])=>{try{return {ok:true,view:project===null?usageView(value,24):usageView(value,24,project)};}catch{return {ok:false};}})));")

        def view(count, scope, status=None):
            items = [{"bucket_ms": 10 + i * 60000, "delta_tokens": i % 7} for i in range(count)]
            return {"ok": True, "hours": 24, "status": status or ("partial" if count else "no_data"),
                    "window": {"after_ms": 10, "before_ms": 257*60000}, "items": items,
                    "total_tokens": sum(row["delta_tokens"] for row in items),
                    "coverage": {"observed_threads": 1, "expected_threads": 2}, "scope": scope}

        project_a = {"type": "project", "project_id": "project-a"}
        everyone = {"type": "all-projects"}
        cases = [(view(0, project_a), "project-a", True), (view(257, project_a), "project-a", True),
                 (view(257, project_a, "ok"), "project-a", True),
                 (view(257, {"type": "project", "project_id": "project-b"}), "project-a", False),
                 (view(257, everyone), "project-a", False), (view(257, project_a), None, False),
                 (view(257, everyone), None, True)]
        compacted = []
        for value, project, _ in cases:
            compact = mcp._compact_usage(value)
            self.assertEqual(compact["scope"], value["scope"])
            self.assertEqual(sum(row["delta_tokens"] for row in compact["items"]), value["total_tokens"])
            compacted.append([compact, project])
        run = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT.parents[1],
                             input=json.dumps(compacted), text=True, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        for (value, project, accepted), rendered in zip(cases, json.loads(run.stdout)):
            with self.subTest(project=project, scope=value["scope"], count=len(value["items"])):
                self.assertEqual(rendered["ok"], accepted)
                if accepted:
                    self.assertEqual(rendered["view"]["total"], value["total_tokens"] if value["items"] else None)
                    self.assertEqual(rendered["view"]["window"], value["window"])
                    self.assertEqual(rendered["view"]["status"], value["status"])
                    self.assertEqual(rendered["view"]["coverage"], value["coverage"])

    def test_usage_aggregation_does_not_hide_invalid_observations(self):
        for field, value in (("bucket_ms", 0), ("bucket_ms", 9999), ("bucket_ms", True),
                             ("delta_tokens", -1), ("delta_tokens", True)):
            rows = [{"bucket_ms": i, "delta_tokens": 1} for i in range(257)]
            rows[10][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(mcp.MCPError):
                mcp._compact_usage({"items": rows, "total_tokens": 257,
                                    "window": {"after_ms": 0, "before_ms": 300}})
        with self.assertRaises(mcp.MCPError):
            mcp._compact_usage({"items": [{"bucket_ms": i, "delta_tokens": 1} for i in range(257)],
                                "total_tokens": 256, "window": {"after_ms": 0, "before_ms": 300}})

    def test_probe_read_write_delete_are_local_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen(
                [sys.executable, str(SERVER), "--stdio", "--probe-root", str(root), "--telemetry", str(root / "telemetry.jsonl")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
            )
            try:
                initialized = call(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
                self.assertEqual(initialized["result"]["serverInfo"]["name"], "swarm-mcp")
                listed = call(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                names = {tool["name"] for tool in listed["result"]["tools"]}
                self.assertTrue({"probe_read_file", "probe_write_file", "probe_delete_file"} <= names)
                written = call(process, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "probe_write_file", "arguments": {"name": "probe.txt", "content": "ok"}}})
                self.assertFalse(written["result"]["isError"])
                self.assertEqual((root / "probe.txt").read_text(encoding="utf-8"), "ok")
                read = call(process, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "probe_read_file", "arguments": {"name": "probe.txt"}}})
                self.assertIn('"content":"ok"', read["result"]["content"][0]["text"])
                deleted = call(process, {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "probe_delete_file", "arguments": {"name": "probe.txt"}}})
                self.assertFalse(deleted["result"]["isError"])
                self.assertFalse((root / "probe.txt").exists())
                self.assertGreaterEqual(len((root / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()), 3)
            finally:
                if process.stdin:
                    process.stdin.close()
                if process.stdout:
                    process.stdout.close()
                process.kill()
                process.wait(timeout=5)



if __name__ == "__main__":
    unittest.main()
