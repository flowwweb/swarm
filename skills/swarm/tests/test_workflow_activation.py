"""Exercise the plugin's native startup hook with actual hook events."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class WorkflowActivationTests(unittest.TestCase):
    def test_startup_and_subagents_receive_the_canonical_workflow_pointer(self):
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        hooks = json.loads((ROOT / manifest["hooks"]).read_text(encoding="utf-8"))["hooks"]
        with tempfile.TemporaryDirectory() as directory:
            self.check_events(manifest, hooks, Path(directory))

    def check_events(self, manifest, hooks, directory):
        telemetry = directory / "telemetry.jsonl"
        environment = {**os.environ, "PLUGIN_ROOT": str(ROOT), "SWARM_MCP_TELEMETRY_PATH": str(telemetry)}
        for event in ("SessionStart", "SubagentStart"):
            handler = hooks[event][0]["hooks"][0]
            self.assertEqual(handler["type"], "command")
            self.assertIn('"${PLUGIN_ROOT}/hooks/activate.py"', handler["command"])
            command = shlex.split(handler["commandWindows"])
            self.assertEqual(command[0], "python")
            completed = subprocess.run(
                [sys.executable, "-B", *command[1:]],
                input=json.dumps({"hook_event_name": event, "source": "startup", "session_id": "private-session", "prompt": "SECRET"}),
                text=True, capture_output=True, check=True, cwd=ROOT.parent, env=environment,
            )
            output = json.loads(completed.stdout)["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], event)
            self.assertIn(str(ROOT / "skills/swarm/SKILL.md"), output["additionalContext"])
            self.assertIn("assigned role", output["additionalContext"])
            self.assertIn("opt-outs", output["additionalContext"])
            self.assertLess(len(output["additionalContext"]), 1000)
        records = [json.loads(line) for line in telemetry.read_text().splitlines()]
        self.assertEqual([row["hook_event"] for row in records], ["SessionStart", "SubagentStart"])
        self.assertTrue(all(row["success"] and row["plugin_version"] == manifest["version"] for row in records))
        self.assertNotIn("SECRET", telemetry.read_text())
        self.assertNotIn("private-session", telemetry.read_text())
        projection = subprocess.run([sys.executable, "-B", "-c",
            "import sys,json; sys.path.insert(0,sys.argv[1]); import swarm_mcp; print(json.dumps(swarm_mcp._device_status()))",
            str(ROOT / "skills/swarm/scripts")], env=environment, text=True, capture_output=True, check=True)
        status = json.loads(projection.stdout)
        self.assertEqual(status["activation_status"], "OBSERVED_HOOK_OUTPUT")
        self.assertEqual(len(status["activation_receipts"]), 2)
        self.assertEqual(status["host"], records[0]["host"])
        unavailable = subprocess.run([sys.executable, "-B", str(ROOT / "hooks/activate.py")],
            input='{"hook_event_name":"SessionStart"}', text=True, capture_output=True, check=True,
            env={**environment, "SWARM_MCP_TELEMETRY_PATH": str(directory)})
        self.assertIn("additionalContext", unavailable.stdout)
        self.assertIn("telemetry unavailable", unavailable.stderr)
        rejected = subprocess.run(
            [sys.executable, "-B", str(ROOT / "hooks/activate.py")],
            input='{"hook_event_name":"PreToolUse"}', text=True, capture_output=True,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(rejected.stdout, "")


if __name__ == "__main__":
    unittest.main()
