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


class SwarmMCPTests(unittest.TestCase):
    def test_projects_shell_composes_settings_without_rewriting_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest, _ = self.hq_export(Path(directory))
            before = path.read_bytes()
            app = mcp.HQApp(path, digest, projects=True)
            rendered = app.render()
            self.assertIn('id="all-projects"', rendered)
            self.assertIn('id="settings"', rendered)
            self.assertIn('data:image/png;base64,', rendered)
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
            self.assertEqual(rows[1]["result"]["tools"][:5], list(mcp.TOOLS))
            self.assertEqual(len(rows[1]["result"]["tools"]), 6)
            tool = rows[1]["result"]["tools"][-1]
            self.assertEqual(tool["name"], "swarm_hq_view")
            self.assertEqual(tool["_meta"], {"ui": {"resourceUri": app.uri}, "openai/ui": {"entrypoints": [{"type": "global"}]}})
            self.assertEqual(rows[2]["result"]["resources"][0]["uri"], app.uri)
            resource = rows[3]["result"]["contents"][0]
            self.assertTrue(resource["text"].startswith(value["html"]))
            self.assertIn('data-swarm-mcp-sdk="' + mcp.HQ_SDK_SHA256, resource["text"])
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
        app.usage_history.assert_called_once_with(hours=24)
        for name, arguments in [("unknown", {}), ("swarm_status", {"project_id": ""}), ("swarm_status", {"project_id": None}), ("swarm_usage", {"hours": True}), ("swarm_usage", {"hours": 2}), ("swarm_projects", {"unexpected": 1})]:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(mcp.MCPError):
                projection.call(name, arguments)

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
            self.assertEqual(len(rows[-1]["result"]["tools"]), 5)
            self.assertNotIn("SECRET", output.getvalue() + telemetry.read_text())

    def test_output_cap_and_scratch_validation(self) -> None:
        usage = mcp._compact_usage({"items": list(range(300)), "task_history": {"items": ["detail"], "status": "PARTIAL"}, "verified_yield": {"detail": "omitted"}})
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
