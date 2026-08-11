from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
NEW_TITLE = "🐙CTRL - <objective>"
LEGACY_TITLE = "🐙CTRL - <project> - <detailed descriptor>"


class CtrlBootstrapContractTests(unittest.TestCase):
    def test_step_zero_precedes_all_substantive_work(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("**Step 0, never defer:**", skill)
        self.assertIn(NEW_TITLE, skill)
        self.assertIn("Verify successful title and pin receipts", skill)
        self.assertIn("before durable-goal inspection", skill)
        self.assertIn("any other tool work", skill)
        self.assertIn("truthful internal CTRL identity", skill)
        self.assertLess(skill.index("**Step 0, never defer:**"), skill.index("After Step 0"))

    def test_public_contracts_use_new_title_and_reject_legacy_title(self) -> None:
        contract_paths = (
            PLUGIN_ROOT / "README.md",
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "references" / "hierarchy.md",
            SKILL_ROOT / "references" / "task-contract.md",
            SKILL_ROOT / "references" / "config.md",
        )
        for path in contract_paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn(NEW_TITLE, text)
                self.assertNotIn(LEGACY_TITLE, text)

    def test_intake_evals_contrast_receipted_step_zero_with_late_rename(self) -> None:
        payload = json.loads((SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        intake = {entry["id"]: entry for entry in payload["evals"] if entry["id"] in {72, 73, 76}}
        self.assertEqual(set(intake), {72, 73, 76})
        for entry in intake.values():
            self.assertIn(NEW_TITLE, entry["expected_output"])
            self.assertNotIn(LEGACY_TITLE, entry["expected_output"])
        self.assertIn("Start implementing", intake[72]["prompt"])
        self.assertIn("plans to rename itself CTRL afterward", intake[76]["prompt"])
        self.assertIn("Fail the intake contract", intake[76]["expected_output"])


if __name__ == "__main__":
    unittest.main()
