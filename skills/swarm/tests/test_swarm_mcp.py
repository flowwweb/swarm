from __future__ import annotations

import json
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
            self.assertEqual(len(rows[-1]["result"]["tools"]), 3)
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
