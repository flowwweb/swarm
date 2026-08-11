from __future__ import annotations

import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


class VisualApprovalContractTests(unittest.TestCase):
    def test_user_defined_approval_boundary_avoids_both_false_approval_and_over_escalation(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")

        self.assertIn("Explicit user direction outranks every SWARM default", skill)
        self.assertIn("Resolve ordinary ambiguity locally", skill)
        self.assertIn("Escalate only the smallest decision", skill)
        self.assertIn(
            "when the user delegates taste or selection, the owner decides",
            skill,
        )
        self.assertIn(
            "when the user reserves it, present candidates and wait",
            skill,
        )
        self.assertIn("approval comes only from the designated authority", skill)
        self.assertIn("Never convert a candidate, reviewer preference, silence, or “best available” judgment into approval", skill)
        self.assertIn("do not infer neighboring approval", skill)


if __name__ == "__main__":
    unittest.main()
