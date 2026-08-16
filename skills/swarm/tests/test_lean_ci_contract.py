from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class LeanCiContractTests(unittest.TestCase):
    def test_package_integration_builds_once_outside_os_matrix(self) -> None:
        workflow=(ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("python -m unittest skills.swarm.tests.test_release_package"),1)
        self.assertEqual(workflow.count("python scripts/build_package.py"),1)
        self.assertIn("name: Build immutable package",workflow)
        self.assertIn("name: Verify package / ${{ matrix.os }}",workflow)
        self.assertIn("name: swarm-release-candidate",workflow)

    def test_release_consumes_validated_bytes_without_rebuild(self) -> None:
        workflow=(ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("Download the exact validated package",workflow)
        self.assertNotIn("scripts/build_package.py",workflow)
        self.assertIn("subject-path:",workflow)
        self.assertIn("Select release browser proof from changed surfaces",workflow)
        self.assertIn("needs.scope.outputs.console_ui_required == 'true'",workflow)

    def test_console_browser_proof_is_pinned_and_path_scoped(self) -> None:
        workflow=(ROOT / ".github" / "workflows" / "console-ui.yml").read_text(encoding="utf-8")
        package=(ROOT / "console" / "package.json").read_text(encoding="utf-8")
        self.assertIn('"playwright": "1.62.1"',package)
        self.assertIn('cache-dependency-path: console/package-lock.json',workflow)
        self.assertIn('working-directory: console',workflow)
        self.assertIn('paths:',workflow)
        validation=(ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn("if: inputs.console_ui_required",validation)
        self.assertIn("npm run test:ui",validation)


if __name__ == "__main__":
    unittest.main()
