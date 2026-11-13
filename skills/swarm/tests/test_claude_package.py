import io
import json
import sys
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import build_package


class ClaudePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        files = list((ROOT / "hosts/claude").rglob("*")) + list((ROOT / "skills/swarm/runtime").rglob("*"))
        files.append(ROOT / "skills/swarm/scripts/swarm_contract.py")
        blobs = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in files
                 if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
        cls.snapshot = build_package.GitSnapshot("candidate", "candidate", "1.0.34", {}, {}, blobs)

    def test_package_is_repeatable_and_uses_canonical_snapshot(self):
        first, metadata = build_package._build_claude_snapshot_bytes(self.snapshot)
        second, _ = build_package._build_claude_snapshot_bytes(self.snapshot)
        self.assertEqual(first, second)
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            names = set(archive.namelist())
            self.assertEqual(archive.read("skills/swarm/runtime/core.py"), self.snapshot.blobs["skills/swarm/runtime/core.py"])
            self.assertEqual(json.loads(archive.read(".claude-plugin/plugin.json"))["name"], "swarm")
            self.assertNotIn(".mcp.json", names)
            self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
            self.assertEqual(set(metadata["files"]), names - {"swarm-package.json"})

    def test_missing_native_entrypoint_fails(self):
        blobs = dict(self.snapshot.blobs)
        del blobs["hosts/claude/skills/swarm/SKILL.md"]
        with self.assertRaises(ValueError):
            build_package._build_claude_snapshot_bytes(replace(self.snapshot, blobs=blobs))


if __name__ == "__main__":
    unittest.main()
