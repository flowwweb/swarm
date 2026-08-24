from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPOSITORY_ROOT / "skills" / "swarm" / "scripts" / "swarm_plugin_rollback.py"
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
import build_package

SPEC = importlib.util.spec_from_file_location("swarm_plugin_rollback_tested", SCRIPT_PATH)
assert SPEC and SPEC.loader
rollback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollback)


class PluginRollbackTests(unittest.TestCase):
    def make_plugin(self, parent: Path) -> Path:
        root = parent / "plugin"
        files = {
            ".codex-plugin/plugin.json": '{"name":"swarm","version":"0.4.2+codex.old","skills":"./skills/"}\n',
            "skills/swarm/SKILL.md": "# SWARM\n",
            "skills/swarm/assets/swarm-config.toml": '[execution]\nfast_mode = false\n\n[proof]\npolicy_version = "lean-v1"\n',
            "skills/swarm/references/review-contract.md": "# Review\n",
            "skills/swarm/references/task-contract.md": "# Task\n",
            "skills/swarm/runtime/core.py": "# runtime\n",
        }
        for relative, contents in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "SWARM tests"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        return root

    @staticmethod
    def write_config(path: Path, flow_source: str = "C:/current") -> bytes:
        contents = (
            'model = "gpt-test"\n\n'
            "[marketplaces.flowwweb]\n"
            'source_type = "local"\n'
            f"source = {json.dumps(flow_source)}\n\n"
            '[plugins."swarm@flowwweb"]\n'
            "enabled = true\n\n"
            '[plugins."swarm@personal"]\n'
            "enabled = true\n\n"
            "[unrelated]\n"
            'preserve = "exact"\n'
        ).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return contents

    def prepare(self, root: Path) -> tuple[Path, Path, Path, dict[str, object]]:
        plugin = self.make_plugin(root)
        package = root / "swarm.zip"
        build_package.write_package(plugin, package)
        config = root / "codex" / "config.toml"
        self.write_config(config)
        snapshot = root / "snapshot"
        manifest = rollback.prepare_snapshot(
            config,
            package,
            snapshot,
            ["python", "C:/rollback/console/server.py", "--port", "4791"],
        )
        return config, package, snapshot, manifest

    def test_restore_is_hash_bound_atomic_and_preserves_personal_and_unrelated_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _package, snapshot, manifest = self.prepare(root)
            before = config.read_bytes()

            receipt = rollback.restore_snapshot(snapshot, config.parent)

            after = config.read_bytes()
            self.assertNotEqual(before, after)
            parsed = tomllib.loads(after.decode("utf-8"))
            self.assertEqual(parsed["marketplaces"]["flowwweb"]["source"], str((snapshot / "marketplace").resolve()))
            self.assertIn('[plugins."swarm@personal"]\nenabled = true', after.decode("utf-8"))
            self.assertIn('[unrelated]\npreserve = "exact"', after.decode("utf-8"))
            cache = config.parent / "plugins" / "cache" / "flowwweb" / "swarm" / manifest["version"]
            self.assertEqual(build_package.installed_file_hashes(cache), manifest["files"])
            self.assertEqual(receipt["cache_action"], "restored")
            self.assertEqual(receipt["launch_argv"][-1], "4791")
            self.assertEqual(len((snapshot / "rollback-log.jsonl").read_text(encoding="utf-8").splitlines()), 1)

            replay = rollback.restore_snapshot(snapshot, config.parent)
            self.assertEqual(replay["cache_action"], "unchanged")
            self.assertEqual(len((snapshot / "rollback-log.jsonl").read_text(encoding="utf-8").splitlines()), 2)

    def test_unrelated_or_personal_selection_change_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _package, snapshot, _manifest = self.prepare(root)
            contents = config.read_text(encoding="utf-8").replace('preserve = "exact"', 'preserve = "changed"')
            config.write_text(contents, encoding="utf-8")
            with self.assertRaisesRegex(rollback.RollbackError, "unrelated config bytes changed"):
                rollback.restore_snapshot(snapshot, config.parent)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _package, snapshot, _manifest = self.prepare(root)
            contents = config.read_text(encoding="utf-8").replace(
                '[plugins."swarm@personal"]\nenabled = true',
                '[plugins."swarm@personal"]\nenabled = false',
            )
            config.write_text(contents, encoding="utf-8")
            with self.assertRaisesRegex(rollback.RollbackError, "unrelated config bytes changed|personal"):
                rollback.restore_snapshot(snapshot, config.parent)

    def test_snapshot_content_change_and_conflicting_cache_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _package, snapshot, manifest = self.prepare(root)
            skill = snapshot / "marketplace" / "plugins" / "swarm" / "skills" / "swarm" / "SKILL.md"
            skill.write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(rollback.RollbackError, "hash mismatch"):
                rollback._verify_snapshot(snapshot)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, _package, snapshot, manifest = self.prepare(root)
            cache = config.parent / "plugins" / "cache" / "flowwweb" / "swarm" / manifest["version"]
            cache.mkdir(parents=True)
            (cache / "unexpected.txt").write_text("conflict\n", encoding="utf-8")
            config_digest = hashlib.sha256(config.read_bytes()).hexdigest()
            with self.assertRaisesRegex(rollback.RollbackError, "conflicts"):
                rollback.restore_snapshot(snapshot, config.parent)
            self.assertEqual(hashlib.sha256(config.read_bytes()).hexdigest(), config_digest)

    def test_missing_or_duplicate_authority_sections_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plugin = self.make_plugin(root)
            package = root / "swarm.zip"
            build_package.write_package(plugin, package)
            config = root / "config.toml"
            config.write_text('[plugins."swarm@flowwweb"]\nenabled = true\n', encoding="utf-8")
            with self.assertRaisesRegex(rollback.RollbackError, "missing Flowwweb"):
                rollback.prepare_snapshot(config, package, root / "snapshot", ["python"])

    def test_local_read_mirror_must_match_authoritative_package_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plugin = self.make_plugin(root)
            authority = root / "authority" / "swarm.zip"
            authority.parent.mkdir()
            build_package.write_package(plugin, authority)
            read_copy = root / "read-copy" / "swarm.zip"
            read_copy.parent.mkdir()
            read_copy.write_bytes(authority.read_bytes())
            read_copy.with_name(read_copy.name + ".sha256").write_bytes(
                authority.with_name(authority.name + ".sha256").read_bytes()
            )
            config = root / "config.toml"
            self.write_config(config)
            rollback.prepare_snapshot(config, read_copy, root / "snapshot", ["python"], authority)

            read_copy.write_bytes(read_copy.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "checksum|archive"):
                rollback.prepare_snapshot(config, read_copy, root / "bad-snapshot", ["python"], authority)


if __name__ == "__main__":
    unittest.main()
