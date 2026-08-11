from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import EvidenceDisposition, InvariantError, Role, Swarm, Task, TaskState, WithholdBasis, WorkerState


class EvidenceRoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    def setUp(self):
        self.swarm = Swarm()
        self.swarm.start_atomic(Role.CTRL, Task("covers", "artist", "CTRL", 1, {}))

    def accept(self):
        self.swarm.review(Role.REVIEW, "covers", "independent", True)
        self.swarm.complete(Role.MOTHER, "covers", True, True, 1)

    def test_worker_produces_ten_images_but_ctrl_only_links_folder_is_rejected(self):
        for index in range(10):
            self.swarm.register_ctrl_evidence(Role.DOER, "covers", f"cover-{index}", "ImageGen", f"cover-{index}.png")
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "cover-folder", "inventory", "covers/", material=False)
        self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-folder", caption="Folder inventory for ten generated covers.", claim_limit="This link does not display or approve any cover.")
        self.swarm.review(Role.REVIEW, "covers", "independent", True)
        with self.assertRaisesRegex(InvariantError, "open CTRL evidence acceptance failure"):
            self.swarm.complete(Role.MOTHER, "covers", True, True, 1)
        with self.assertRaisesRegex(InvariantError, "before phase advance"):
            self.swarm.advance_ctrl_phase(Role.CTRL, "implementation")
        self.assertEqual(len(self.swarm.ctrl_feed_due(Role.CTRL)), 10)
        self.swarm.tasks["covers"].state = TaskState.COMPLETE
        self.swarm.tasks["covers"].completed_at = 1
        self.swarm.workers["artist"].state = WorkerState.RETIRED
        self.swarm.workers["artist"].task_ids.clear()
        self.assertFalse(self.swarm.archive_eligible(self.swarm.tasks["covers"]))

    def test_ctrl_embeds_each_material_candidate_once_as_generated_is_accepted(self):
        for index in range(10):
            evidence_id = f"cover-{index}"
            self.swarm.register_ctrl_evidence(Role.DOER, "covers", evidence_id, "ImageGen", f"cover-{index}.png")
            self.swarm.surface_ctrl_evidence(Role.CTRL, evidence_id, caption=f"Generated cover option {index + 1}.", claim_limit="Concept art only; user selection and production admission remain open.")
        self.assertEqual(self.swarm.ctrl_feed_due(Role.CTRL), ())
        self.swarm.advance_ctrl_phase(Role.CTRL, "implementation")
        self.accept()
        self.assertEqual(self.swarm.tasks["covers"].state, TaskState.COMPLETE)
        self.assertTrue(all(item.disposition == EvidenceDisposition.SURFACED and item.receipt.startswith("surface:") for item in self.swarm.ctrl_evidence_ledger.values()))

    def test_objective_defect_with_explicit_withholding_reason_is_accepted(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "broken-cover", "mockup", "broken-cover.png")
        receipt = self.swarm.withhold_ctrl_evidence(Role.CTRL, "broken-cover", basis=WithholdBasis.OBJECTIVE_DEFECT, reason="The output contains six heroes instead of the required four.")
        self.assertEqual(receipt, "withheld:objective-defect:broken-cover")
        self.accept()
        self.assertEqual(self.swarm.tasks["covers"].state, TaskState.COMPLETE)

    def test_duplicate_reembedding_is_rejected(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "cover-1", "preview", "cover-1.png")
        self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-1", caption="Generated cover option 1.", claim_limit="Unapproved preview.")
        with self.assertRaisesRegex(InvariantError, "surfaced exactly once"):
            self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-1", caption="Generated cover option 1 again.", claim_limit="Unapproved preview.")

    def test_live_feed_doctrine_requires_prompt_surface_and_receipts(self):
        self.assertIn("CTRL is the live human review feed", self.skill)
        self.assertIn("At the next safe message boundary", self.skill)
        self.assertIn("never silently accumulate steerable results for a final batch", self.skill)
        self.assertIn("CTRL evidence ledger", self.skill)
        self.assertIn("open acceptance failure", self.skill)
        self.assertIn("do not accept or archive its producing lane or begin a later CTRL phase", self.skill)

    def test_visual_self_review_binds_to_exact_final_deliverable(self):
        self.assertIn("Bind that self-review to the exact final deliverable", self.skill)
        self.assertIn("inspect the file that will actually be surfaced or accepted", self.skill)
        self.assertIn("An intermediate preview, composite, source, filename, manifest, or transformation receipt cannot prove the final artifact", self.skill)
        self.assertIn("A worker final, artifact path, folder link, manifest row, or silent generated file is provenance, not delivery", self.skill)

    def test_contract_preserves_compact_ctrl_stream(self):
        self.assertIn("Keep non-visual coordination clean and compact", self.skill)
        self.assertIn("default to one reserved natural line", self.skill)
        self.assertIn("Suppress duplicate re-embedding and decorative evidence", self.skill)


if __name__ == "__main__":
    unittest.main()
