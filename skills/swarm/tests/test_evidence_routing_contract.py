from pathlib import Path
import unittest


class EvidenceRoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    def test_visual_lane_must_reconcile_generated_artifacts_before_idle(self):
        self.assertIn("Before a visual-producing lane can finish or go idle", self.skill)
        self.assertIn("surface every material taste-valid candidate exactly once", self.skill)

    def test_visual_self_review_binds_to_exact_final_deliverable(self):
        self.assertIn("Bind that self-review to the exact final deliverable", self.skill)
        self.assertIn("inspect the file that will actually be surfaced or accepted", self.skill)
        self.assertIn("An intermediate preview, composite, source, filename, manifest, or transformation receipt cannot prove the final artifact", self.skill)
        self.assertIn("A worker link, folder path, or silent generated file is not delivery", self.skill)

    def test_contract_preserves_compact_ctrl_stream(self):
        self.assertIn("default to one compact, reserved, natural line", self.skill)
        self.assertIn("Suppress duplicate or decorative evidence", self.skill)


if __name__ == "__main__":
    unittest.main()
