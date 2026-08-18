from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CtrlOrchestrationContractTests(unittest.TestCase):
    def text(self, *relative: str) -> str:
        return "\n".join((ROOT / item).read_text(encoding="utf-8") for item in relative)

    def test_ctrl_owns_orchestration_and_substantive_work_routes_to_a_lane(self) -> None:
        doctrine = self.text(
            "SKILL.md",
            "references/hierarchy.md",
            "references/config.md",
        )
        self.assertIn("CTRL is the orchestrator, not the default worker", doctrine)
        self.assertIn("substantive artifact-producing work", doctrine)
        self.assertIn("code edits, generated media, or provider/device/deploy actions", doctrine)
        self.assertIn("LEAD-owned lane", doctrine)
        self.assertIn("bounded DOER", doctrine)
        self.assertIn("final composed acceptance", doctrine)
        self.assertIn("typed capacity exception", doctrine)
        self.assertIn("affected gates `UNVERIFIED`", doctrine)

    def test_direct_work_is_a_narrow_exception_and_capacity_fallback_is_explicit(self) -> None:
        doctrine = self.text("SKILL.md", "references/hierarchy.md", "references/config.md")
        self.assertIn("existing `CTRL_DIRECT` safe-work predicate", doctrine)
        self.assertIn("never silently fall through to worker execution", doctrine)
        self.assertIn("not a standing waiver for silent worker execution", doctrine)
        self.assertIn("Explicit user direction", doctrine)
        self.assertIn("not a project, brand, route,", doctrine)
        self.assertIn("screen-specific rule", doctrine)

    def test_policy_is_intent_driven_and_not_a_project_template(self) -> None:
        doctrine = self.text(
            "SKILL.md",
            "references/hierarchy.md",
            "references/config.md",
        )
        self.assertIn("qualifying host lane capacity", doctrine)
        self.assertIn("routing fact", doctrine)
        self.assertIn("actual work", doctrine)
        self.assertIn("Record the exact host capacity observation", doctrine)


if __name__ == "__main__":
    unittest.main()
