from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]


class LeanCiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("select_ci_scope", ROOT / "scripts" / "select_ci_scope.py")
        assert spec and spec.loader
        cls.selector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.selector)

    def test_package_integration_builds_once_outside_os_matrix(self) -> None:
        workflow=(ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("python -m unittest skills.swarm.tests.test_release_package"),1)
        self.assertEqual(workflow.count("python scripts/build_package.py"),1)
        self.assertIn("name: Build immutable package",workflow)
        self.assertIn("name: Verify package / ${{ matrix.os }}",workflow)
        self.assertIn("name: swarm-release-candidate",workflow)
        self.assertIn('output "$RUNNER_TEMP/swarm-release.zip"',workflow)
        self.assertNotIn("--output dist/swarm-release.zip",workflow)

    def test_release_consumes_validated_bytes_without_rebuild(self) -> None:
        workflow=(ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("Download the exact validated package",workflow)
        self.assertNotIn("scripts/build_package.py",workflow)
        self.assertIn("subject-path:",workflow)
        self.assertIn("Select release browser proof from changed surfaces",workflow)
        self.assertIn("gh release list --exclude-drafts --exclude-pre-releases",workflow)
        self.assertIn("needs.scope.outputs.console_ui_required == 'true'",workflow)

    def test_console_browser_proof_is_pinned_and_path_scoped(self) -> None:
        workflow=(ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        package=(ROOT / "console" / "package.json").read_text(encoding="utf-8")
        self.assertIn('"playwright": "1.62.1"',package)
        self.assertIn('cache-dependency-path: console/package-lock.json',workflow)
        self.assertIn('working-directory: console',workflow)
        self.assertIn("if: inputs.console_ui_required",workflow)
        self.assertIn("npm run test:ui",workflow)
        self.assertFalse((ROOT / ".github" / "workflows" / "console-ui.yml").exists())

    def test_changed_surface_selection_is_minimum_sufficient_and_fail_broad(self) -> None:
        select = self.selector.select_scope
        self.assertEqual(select(("README.md",)), {
            "console_ui_required": False, "platform_required": False, "package_required": False,
        })
        self.assertEqual(select(("console/static/app.js",)), {
            "console_ui_required": True, "platform_required": False, "package_required": False,
        })
        self.assertEqual(select(("skills/swarm/runtime/core.py",)), {
            "console_ui_required": False, "platform_required": True, "package_required": True,
        })
        self.assertEqual(select(("unexpected/new-surface.bin",)), {
            "console_ui_required": True, "platform_required": True, "package_required": True,
        })

    def test_default_branch_forces_full_graph_and_ci_passes_scope_outputs(self) -> None:
        self.assertEqual(self.selector.select_scope(("README.md",), full=True), {
            "console_ui_required": True, "platform_required": True, "package_required": True,
        })
        workflow=(ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("package_required: ${{ needs.scope.outputs.package_required == 'true' }}", workflow)

    def test_deleted_paths_remain_in_the_proof_selection_diff(self) -> None:
        completed = type("Completed", (), {"stdout": "skills/swarm/runtime/core.py\n"})()
        with patch.object(self.selector.subprocess, "run", return_value=completed) as run:
            self.assertEqual(
                self.selector.changed_paths(ROOT, "base", "head"),
                ("skills/swarm/runtime/core.py",),
            )
        self.assertIn("--diff-filter=ACDMRTUXB", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
