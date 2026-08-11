from __future__ import annotations

import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
REVIEW_CONTRACT = Path(__file__).resolve().parents[1] / "references" / "review-contract.md"


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

    def test_imagegen_defaults_to_user_choice_with_self_review_not_reconfirmation_loops(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")

        self.assertIn("For ImageGen and other taste-led generative visuals", skill)
        self.assertIn("default to user selection", skill)
        self.assertIn("a clear direction is permission to generate", skill)
        self.assertIn("Use self-review to remove objective prompt violations", skill)
        self.assertIn("generate stronger separate alternatives before presentation", skill)
        self.assertIn("Do not hide or reject a taste-valid candidate solely because an agent prefers another", skill)
        self.assertIn("unless selection was delegated", skill)

    def test_loose_inspiration_and_binding_reference_have_contrasting_fidelity_gates(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        review = REVIEW_CONTRACT.read_text(encoding="utf-8")

        self.assertIn("Classify each supplied visual reference", skill)
        self.assertIn("as loose inspiration or explicitly binding", skill)
        self.assertIn("never promote inspiration into authority or weaken a binding reference into a mood cue", skill)
        self.assertIn("Before generating against a binding reference, write a short fidelity checklist", skill)
        for dimension in (
            "geometry and composition",
            "typography or letterform character",
            "palette and color treatment",
            "hierarchy",
            "prohibited deviations",
        ):
            self.assertIn(dimension, skill)
        self.assertIn("inspect the file that will actually be surfaced or accepted", skill)
        self.assertIn("by placing it beside the binding reference", skill)
        self.assertIn("in its delivered format and context", skill)
        self.assertIn("inspect every checklist dimension", skill)
        self.assertIn("Generic thematic, mood, or vibe similarity cannot pass binding-reference fidelity", skill)
        self.assertIn("A loose-inspiration reference guides only the direction the user assigned to it", skill)
        self.assertIn("carries no counterfeit fidelity claim", skill)
        self.assertIn("Treat a loose-inspiration reference only as the direction the user", review)
        self.assertIn("it is not a likeness gate", review)
        self.assertIn("compare the exact final artifact side by side in delivered context", review)
        self.assertIn("Generic thematic similarity cannot pass that fidelity gate", review)


if __name__ == "__main__":
    unittest.main()
