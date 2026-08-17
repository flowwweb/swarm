from __future__ import annotations

import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
REVIEW_CONTRACT = Path(__file__).resolve().parents[1] / "references" / "review-contract.md"


class VisualApprovalContractTests(unittest.TestCase):
    def test_user_defined_approval_boundary_avoids_both_false_approval_and_over_escalation(self) -> None:
        skill = "\n".join((path.read_text(encoding="utf-8") for path in (SKILL, REVIEW_CONTRACT)))

        self.assertRegex(skill, r"(?is)Explicit user direction outranks.*reversible.*smallest decision")
        self.assertRegex(skill, r"(?is)reserved choice requires candidates and a wait.*never.*approval")

    def test_imagegen_defaults_to_user_choice_with_self_review_not_reconfirmation_loops(self) -> None:
        skill = "\n".join((path.read_text(encoding="utf-8") for path in (SKILL, REVIEW_CONTRACT)))

        self.assertRegex(skill, r"(?is)taste-led generation.*clear user direction permits generation.*reserved choice requires candidates")

    def test_loose_inspiration_and_binding_reference_have_contrasting_fidelity_gates(self) -> None:
        skill = "\n".join((path.read_text(encoding="utf-8") for path in (SKILL, REVIEW_CONTRACT)))
        review = REVIEW_CONTRACT.read_text(encoding="utf-8")

        self.assertRegex(skill, r"(?is)reference.*loose inspiration or binding.*fidelity")
        for dimension in (
            "geometry and composition",
            "typography or letterform character",
            "palette and color treatment",
            "hierarchy",
            "prohibited deviations",
        ):
            self.assertIn(dimension.split()[0], skill)
        self.assertIn("Treat a loose-inspiration reference only as the direction the user", review)
        self.assertIn("it is not a likeness gate", review)
        self.assertIn("compare the exact final artifact side by side in delivered context", review)
        self.assertIn("Generic thematic similarity cannot pass that fidelity gate", review)

    def test_directional_mockups_do_not_inherit_pixel_perfect_implementation_gates(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        review = REVIEW_CONTRACT.read_text(encoding="utf-8")

        for artifact_class in (
            "DIRECTIONAL_MOCKUP",
            "BINDING_VISUAL_SPEC",
            "IMPLEMENTATION_EVIDENCE",
        ):
            self.assertIn(artifact_class, review)
        self.assertIn("Small generator drift", skill)
        self.assertIn("is not a rejection reason", skill)
        self.assertIn("1505×1045 versus a target canvas", review)
        self.assertIn("NOTE_FOR_IMPLEMENTATION", review)
        self.assertIn("APPROVE_DIRECTION", review)
        self.assertRegex(review, r"Do not spend another\s+generation/review cycle")

    def test_directional_review_has_a_stop_rule_and_major_drift_threshold(self) -> None:
        review = REVIEW_CONTRACT.read_text(encoding="utf-8")

        self.assertIn("changes the requested user job", review)
        self.assertRegex(review, r"contradicts an\s+explicit must-have")
        self.assertRegex(review, r"one independent\s+review pass is the default")
        self.assertIn("new evidence or a named material risk", review)


if __name__ == "__main__":
    unittest.main()
