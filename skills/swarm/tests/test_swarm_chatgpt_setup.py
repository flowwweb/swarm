from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "swarm_chatgpt_setup.py"
spec = importlib.util.spec_from_file_location("swarm_chatgpt_setup", SCRIPT)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_scoped_config_preserves_existing_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "config.json"
            original = {"openaiTunnel": {"tunnelId": "keep", "apiKeyRef": "env:KEEP"}, "mcpServers": {"existing": {"command": "keep"}}}
            path.write_text(json.dumps(original), encoding="utf-8")
            preview = setup.configure(path, root, write=False)
            self.assertEqual(json.loads(path.read_text()), original)
            self.assertEqual(preview["workDir"], str(root))
            self.assertIs(preview["multiProject"], False)
            self.assertEqual(preview["codexMcp"], {"enabled": False, "useCli": False})
            self.assertEqual(preview["openaiTunnel"], original["openaiTunnel"])
            self.assertEqual(preview["mcpServers"]["existing"], original["mcpServers"]["existing"])
            swarm = preview["mcpServers"]["swarm"]
            self.assertEqual(swarm["mode"], "catalog")
            self.assertEqual(swarm["tools"], ["swarm_status", "swarm_projects", "swarm_usage"])
            self.assertEqual(setup.configure(path, root, write=True), preview)
            self.assertEqual(setup.configure(path, root, write=True), preview)

    def test_conflicting_scope_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "config.json"
            for config in ({"workDir": str(root.parent)}, {"multiProject": True}, {"codexMcp": {"enabled": True}}, {"codexMcp": {"useCli": True}}, {"mcpServers": {"swarm": {"command": "different"}}}, {"mcpServers": []}):
                with self.subTest(config=config):
                    before = json.dumps(config)
                    path.write_text(before, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        setup.configure(path, root, write=True)
                    self.assertEqual(path.read_text(), before)

    def test_explicit_bridge_hash_controls_check_and_no_secrets_are_printed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bridge = root / "codexify.exe"
            bridge.write_bytes(b"test executable")
            path = root / "config.json"
            path.write_text(json.dumps({"openaiTunnel": {"tunnelId": "private-id", "apiKeyRef": "env:PRIVATE_KEY"}}))
            argv = ["--project-root", directory, "--config", str(path), "--bridge", str(bridge), "--check"]
            with patch.object(setup.shutil, "which", return_value=str(bridge)), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(setup.main(argv), 2)
            with patch.object(setup.shutil, "which", return_value=str(bridge)), patch.object(setup, "BRIDGE_SHA256", setup.hashlib.sha256(bridge.read_bytes()).hexdigest()), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(setup.main(argv), 0)
            report = json.loads(output.getvalue())
            self.assertTrue(report["version_verified"])
            self.assertTrue(report["tunnel_reference_present"])
            self.assertNotIn("private-id", output.getvalue())
            self.assertNotIn("PRIVATE_KEY", output.getvalue())

    def test_missing_bridge_check_fails_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent.json"
            with patch.object(setup.shutil, "which", return_value=None), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(setup.main(["--project-root", directory, "--config", str(path), "--check"]), 2)
            report = json.loads(output.getvalue())
            self.assertFalse(report["bootstrap_ready"])
            self.assertEqual(report["doctor"]["status"], "not_run")
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
