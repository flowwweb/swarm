from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_plugin_install.py"
BUILDER_PATH = REPOSITORY_ROOT / "scripts" / "build_package.py"

SPEC = importlib.util.spec_from_file_location("verify_plugin_install_host_contracts", VERIFIER_PATH)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
BUILDER_SPEC = importlib.util.spec_from_file_location("build_package_host_contracts", BUILDER_PATH)
assert BUILDER_SPEC and BUILDER_SPEC.loader
builder = importlib.util.module_from_spec(BUILDER_SPEC)
sys.modules[BUILDER_SPEC.name] = builder
BUILDER_SPEC.loader.exec_module(builder)


class HostContractTests(unittest.TestCase):
    def test_host_manifests_share_one_canonical_skill_and_version(self) -> None:
        codex = json.loads((REPOSITORY_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        claude = json.loads((REPOSITORY_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        gemini = json.loads((REPOSITORY_ROOT / "gemini-extension.json").read_text(encoding="utf-8"))
        codex_marketplace = json.loads((REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        marketplace = json.loads((REPOSITORY_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))

        for manifest in (codex, claude, gemini):
            self.assertEqual(manifest["name"], "swarm")
            self.assertEqual(manifest["version"], codex["version"])
            self.assertTrue(manifest["description"])
        self.assertEqual(codex["skills"], "./skills/")
        self.assertEqual(claude["skills"], "./skills/")
        self.assertEqual(marketplace["name"], "flowwweb")
        self.assertEqual(marketplace["owner"], {"name": "Flowwweb"})
        self.assertEqual(marketplace["plugins"], [{"name": "swarm", "source": "./"}])
        self.assertEqual(codex_marketplace["plugins"][0]["source"], {"source": "local", "path": "./plugins/swarm"})

    def test_codex_marketplace_mirror_matches_the_complete_product_surface(self) -> None:
        mirror = REPOSITORY_ROOT / "plugins" / "swarm"
        source = verifier.source_file_hashes(REPOSITORY_ROOT)
        canonical = {
            relative: hashlib.sha256(
                builder.canonical_worktree_bytes(
                    REPOSITORY_ROOT,
                    relative,
                    (REPOSITORY_ROOT / relative).read_bytes(),
                )
            ).hexdigest()
            for relative in source
        }
        self.assertEqual(
            canonical,
            verifier.installed_file_hashes(mirror),
        )
        verifier.validate_plugin_manifest(mirror)

    def test_no_duplicate_agent_skill_is_tracked_or_present_in_the_source_tree(self) -> None:
        duplicate = REPOSITORY_ROOT / ".agents" / "skills" / "swarm"
        self.assertFalse(duplicate.exists())
        tracked = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "ls-files", ".agents/skills/swarm"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        self.assertEqual(tracked, "")

    def test_agent_skill_installer_copies_declared_canonical_surface_and_refuses_source_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "consumer"
            project.mkdir()
            count = verifier.install_agent_skill(project)
            installed = project / ".agents" / "skills" / "swarm"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertEqual(count, len(verifier._declared_skill_file_hashes(REPOSITORY_ROOT / "skills" / "swarm")))
            self.assertEqual(
                hashlib.sha256((installed / "SKILL.md").read_bytes()).hexdigest(),
                hashlib.sha256((REPOSITORY_ROOT / "skills" / "swarm" / "SKILL.md").read_bytes()).hexdigest(),
            )
            self.assertFalse((installed / "tests").exists())
            self.assertFalse((installed / "evals").exists())
            self.assertEqual(
                verifier._skill_file_hashes(installed),
                verifier._declared_skill_file_hashes(REPOSITORY_ROOT / "skills" / "swarm"),
            )
            with self.assertRaisesRegex(ValueError, "duplicate skill"):
                verifier.install_agent_skill(REPOSITORY_ROOT)
            with self.assertRaisesRegex(ValueError, "already exists"):
                verifier.install_agent_skill(project)

    def test_agent_skill_installer_rejects_reparse_ancestors_before_directory_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for ancestor_relative in (Path(".agents"), Path(".agents") / "skills"):
                with self.subTest(ancestor=ancestor_relative):
                    project = Path(temporary) / ancestor_relative.name
                    project.mkdir()
                    unsafe = project / ancestor_relative
                    unsafe.mkdir(parents=True)
                    destination = project / ".agents" / "skills" / "swarm"
                    with mock.patch.object(
                        verifier,
                        "_is_reparse_path",
                        side_effect=lambda path, unsafe=unsafe: path == unsafe,
                    ), self.assertRaisesRegex(ValueError, "link or junction"):
                        verifier.install_agent_skill(project)
                    self.assertFalse(destination.exists())

    def test_readme_labels_host_contracts_without_runtime_or_release_claims(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Manifest and marketplace structure only", readme)
        self.assertIn("Manifest and skill-layout structure only", readme)
        self.assertIn("Copy and file-hash parity when the command succeeds", readme)
        self.assertIn("do not prove a host installation, activation, prompt loading, agent behavior, marketplace availability, or an external release", readme)
        self.assertNotIn("cross-host certified", readme.lower())

    def test_readme_keeps_one_clear_three_lane_hierarchy(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(1, readme.count("```mermaid"))
        self.assertEqual(3, readme.count(" LEAD<br/>gpt-5.6-terra"))
        self.assertEqual(9, readme.count("<br/>gpt-5.6-luna"))
        self.assertIn("CTRL<br/>gpt-5.6-sol · high", readme)
        self.assertNotIn("MOTHER", readme)


if __name__ == "__main__":
    unittest.main()
