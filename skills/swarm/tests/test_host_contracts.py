from __future__ import annotations

import hashlib
import importlib.util
import json
import re
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
    def test_codex_manifest_is_the_only_agent_host_manifest(self) -> None:
        codex = json.loads((REPOSITORY_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        codex_marketplace = json.loads((REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))

        self.assertEqual(codex["name"], "swarm")
        self.assertTrue(codex["version"])
        self.assertTrue(codex["description"])
        self.assertEqual(codex["skills"], "./skills/")
        self.assertEqual(codex_marketplace["plugins"][0]["source"], {"source": "local", "path": "./plugins/swarm"})
        for relative in (
            Path(".claude-plugin") / "plugin.json",
            Path(".claude-plugin") / "marketplace.json",
            Path("gemini-extension.json"),
        ):
            self.assertFalse((REPOSITORY_ROOT / relative).exists(), relative.as_posix())

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
        readme = re.sub(r"\s+", " ", (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("Codex-native scope", readme)
        self.assertIn("Codex is the only agent host", readme)
        self.assertIn("external service boundary", readme)
        self.assertNotIn("claude plugin marketplace", readme.lower())
        self.assertNotIn("gemini extensions install", readme.lower())
        self.assertNotIn("cross-host certified", readme.lower())

    def test_readme_keeps_one_bounded_optional_lane_hierarchy(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(1, readme.count("```mermaid"))
        self.assertEqual(1, readme.count("PROFESSION LEAD<br/>"))
        self.assertEqual(1, readme.count("PROFESSION DOER<br/>"))
        self.assertIn("🐙<br/>CTRL", readme)
        self.assertIn("CTRL_DIRECT<br/>No separate lane", readme)
        self.assertIn("SUBAGENT<br/>No durable ownership", readme)
        self.assertIn("The branches are choices, not a roster to pre-create", readme)
        self.assertIn("The Codex host owns model, service-tier, and reasoning selection", readme)
        self.assertIn("diagram label is never proof of execution", readme)
        self.assertNotIn("MOTHER", readme)

    def test_readme_has_one_global_config_path_and_defers_to_schema_authority(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("`~/.agents/swarm/config.toml`", readme)
        self.assertIn("swarm_config.py init", readme)
        self.assertIn("swarm_config.py validate", readme)
        self.assertIn("swarm_config.py show", readme)
        self.assertIn("skills/swarm/references/config.md", readme)
        self.assertIn("authority; a README excerpt is not", readme)
        self.assertRegex(readme, r"Config never overrides\s+an explicit user choice")
        self.assertRegex(readme, r"Fast or automation preferences become active only when the relevant\s+host/runtime receipt confirms them")


if __name__ == "__main__":
    unittest.main()
