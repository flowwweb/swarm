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
        app.usage_history.assert_called_once_with(hours=24, include_verified_yield=False)
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
        usage = mcp._compact_usage({"items": [{"bucket_ms": i, "delta_tokens": 1} for i in range(300)],
                                   "total_tokens": 300, "window": {"after_ms": 0, "before_ms": 300},
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

    def test_compacted_usage_passes_actual_reader_without_losing_window_deltas(self):
        script = ("import fs from 'node:fs'; "
                  "import {usageView} from './skills/swarm/assets/ui/swarm-usage.mjs'; "
                  "const inputs=JSON.parse(fs.readFileSync(0,'utf8')); "
                  "console.log(JSON.stringify(inputs.map(value=>usageView(value,24))));")
        inputs = []
        for count in (0, 256, 257, 4097):
            items = [{"bucket_ms": 10 + i * 3, "delta_tokens": i % 7} for i in range(count)]
            view = {"ok": True, "hours": 24, "status": "partial" if count else "no_data",
                    "window": {"after_ms": 10, "before_ms": 13000}, "items": items,
                    "total_tokens": sum(row["delta_tokens"] for row in items),
                    "coverage": {"observed_threads": 1, "expected_threads": 2}}
            compact = mcp._compact_usage(view)
            self.assertEqual(compact, mcp._compact_usage(view))
            self.assertEqual(sum(row["delta_tokens"] for row in compact["items"]), view["total_tokens"])
            self.assertEqual(len(compact["items"]), min(count, 256))
            if count <= 256:
                self.assertEqual(compact["items"], items)
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
            items = [{"bucket_ms": 10 + i * 3, "delta_tokens": i % 7} for i in range(count)]
            return {"ok": True, "hours": 24, "status": status or ("partial" if count else "no_data"),
                    "window": {"after_ms": 10, "before_ms": 13000}, "items": items,
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
