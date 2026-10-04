from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
NEW_TITLE = "<project emoji> <project>"
LEGACY_TITLE = "🐙CTRL - <project> - <detailed descriptor>"


class CtrlBootstrapContractTests(unittest.TestCase):
    def test_post_goal_title_verification_preserves_latest_user_preference(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        hierarchy = (SKILL_ROOT / "references/hierarchy.md").read_text(encoding="utf-8")
        step_zero = skill.split("**Step 0, never defer:**", 1)[1].split("After the Step 0 custody check", 1)[0]
        self.assertRegex(step_zero, r"(?s)After creating or updating the durable goal.*freshly read.*exact task's.*display title before dispatch")
        self.assertIn("full goal text is not display-name authority", step_zero)
        self.assertRegex(step_zero, r"(?s)Preserve an explicit user title;.*repair only an authorized generated-title mismatch.*verify the result.*failed rename incomplete")
        self.assertRegex(step_zero, r"(?s)expressly requested `👑 Portfolio`\s+stays exactly that")
        self.assertIn("CTRL/LEAD/DOER remain internal roles, not display prefixes", step_zero)
        self.assertIn("[SKILL.md Step 0](../SKILL.md#start)", hierarchy)
        self.assertIn("do not override host display names", hierarchy)
        for text in (skill, hierarchy):
            self.assertNotIn("<role emoji><PROFESSION> LEAD -", text)
            self.assertNotIn("<role emoji><PROFESSION> DOER -", text)

    def test_step_zero_precedes_all_substantive_work(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("**Step 0, never defer:**", skill)
        self.assertIn(NEW_TITLE, skill)
        step_zero = skill.split("**Step 0, never defer:**", 1)[1].split("After the Step 0 custody check", 1)[0]
        self.assertIn("take over an existing CTRL includes naming the current task", " ".join(step_zero.split()))
        self.assertIn("`set_thread_title`", step_zero)
        self.assertRegex(step_zero, r"(?is)Completion requires the returned task ID and title to\s+match")
        self.assertRegex(step_zero, r"(?is)Verify the successor title\s+again before declaring handover complete")
        self.assertRegex(step_zero, r"(?is)Preserve an\s+explicit custom title")
        self.assertIn("do not ask the user to repeat it", step_zero)
        self.assertIn("After the Step 0 custody check, always ask and capture both intake answers before routing", skill)
        self.assertLess(skill.index("After the Step 0 custody check, always ask and capture both intake answers before routing"), skill.index("Then inspect or create exactly one matching durable goal"))
        self.assertIn("leave naming incomplete", step_zero)
        self.assertLess(skill.index("**Step 0, never defer:**"), skill.index("Then inspect or create exactly one matching durable goal"))

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
                if path.name == "task-contract.md":
                    self.assertIn("[SKILL.md Step 0](../SKILL.md#start)", text)
                else:
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

    def test_project_icons_do_not_inherit_the_default_octopus(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        config = (SKILL_ROOT / "references/config.md").read_text(encoding="utf-8")
        normalized = " ".join(skill.split())
        self.assertIn('default `role_icons.ctrl = "🐙"` is not an explicit user icon choice', normalized)
        self.assertIn("🐙 belongs to SWARM", normalized)
        self.assertIn("use `role_icons.fallback`; do not default every project to 🐙", normalized)
        for title in ("🐟 Nemo", "📐 Blüprint", "⚓ Helm", "🐙 SWARM"):
            self.assertIn(title, skill)
        self.assertNotIn("🐙 <objective>", skill + config)

    def test_authorized_icon_only_repair_preserves_custody_and_explicit_choices(self) -> None:
        skill = " ".join((SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("replace only its leading emoji; preserve the rest of the title exactly", skill)
        self.assertIn("Explicit user icon choices, naming exceptions and icon opt-outs remain protected", skill)
        self.assertIn("Do not infer icon-repair authority from pinning alone", skill)
        self.assertIn("Preserve existing pin and placement state", skill)
        payload = json.loads((SKILL_ROOT / "evals/evals.json").read_text(encoding="utf-8"))
        repair = next(entry for entry in payload["evals"] if entry["id"] == 96)
        for title in ("🐟 Nemo", "📐 Blüprint design desk", "👑 Helm", "🐙 SWARM"):
            self.assertIn(title, repair["expected_output"])
        self.assertIn("default configuration is not an explicit octopus preference", repair["expected_output"])
        self.assertIn("preserve pins, order, identity and topology", repair["expected_output"])


if __name__ == "__main__":
    unittest.main()
