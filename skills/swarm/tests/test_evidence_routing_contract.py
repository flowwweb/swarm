from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import CtrlSurfaceKind, EvidenceDisposition, InvariantError, Role, Swarm, Task, TaskState, WithholdBasis, WorkerState


class EvidenceRoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    def setUp(self):
        self.swarm = Swarm()
        self.swarm.start_atomic(Role.CTRL, Task("covers", "artist", "CTRL", 1, {}, subagent_receipt="host:artist"))

    def accept(self):
        self.swarm.review(Role.REVIEW, "covers", "independent", True)
        self.swarm.complete(Role.MOTHER, "covers", True, True, 1)

    def test_worker_produces_ten_images_but_ctrl_only_links_folder_is_rejected(self):
        for index in range(10):
            self.swarm.register_ctrl_evidence(Role.DOER, "covers", f"cover-{index}", "ImageGen", f"cover-{index}.png")
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "cover-folder", "inventory", "covers/", material=False)
        with self.assertRaisesRegex(InvariantError, "inline proof surface kind"):
            self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-folder", surface_kind="path", caption="Folder inventory for ten generated covers.", claim_limit="This link does not display or approve any cover.", surface_receipt="chat:folder")
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
            self.swarm.surface_ctrl_evidence(Role.CTRL, evidence_id, surface_kind=CtrlSurfaceKind.INLINE_IMAGE, caption=f"Generated cover option {index + 1}.", claim_limit="Concept art only; user selection and production admission remain open.", surface_receipt=f"chat:image:{index}")
        self.assertEqual(self.swarm.ctrl_feed_due(Role.CTRL), ())
        self.swarm.advance_ctrl_phase(Role.CTRL, "implementation")
        self.accept()
        self.assertEqual(self.swarm.tasks["covers"].state, TaskState.COMPLETE)
        self.assertTrue(all(item.disposition == EvidenceDisposition.SURFACED and item.receipt.startswith("chat:image:") for item in self.swarm.ctrl_evidence_ledger.values()))

    def test_objective_defect_with_explicit_withholding_reason_is_accepted(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "broken-cover", "mockup", "broken-cover.png")
        receipt = self.swarm.withhold_ctrl_evidence(Role.CTRL, "broken-cover", basis=WithholdBasis.OBJECTIVE_DEFECT, reason="The output contains six heroes instead of the required four.")
        self.assertEqual(receipt, "withheld:objective-defect:broken-cover")
        self.accept()
        self.assertEqual(self.swarm.tasks["covers"].state, TaskState.COMPLETE)

    def test_duplicate_reembedding_is_rejected(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "cover-1", "preview", "cover-1.png")
        self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-1", surface_kind=CtrlSurfaceKind.INLINE_IMAGE, caption="Generated cover option 1.", claim_limit="Unapproved preview.", surface_receipt="chat:image:1")
        with self.assertRaisesRegex(InvariantError, "surfaced exactly once"):
            self.swarm.surface_ctrl_evidence(Role.CTRL, "cover-1", surface_kind=CtrlSurfaceKind.INLINE_IMAGE, caption="Generated cover option 1 again.", claim_limit="Unapproved preview.", surface_receipt="chat:image:1-again")

    def test_surface_requires_external_receipt_and_accepts_compact_nonvisual_proof(self):
        self.swarm.register_ctrl_evidence(Role.DOER, "covers", "metrics", "proof", "metrics.json")
        with self.assertRaisesRegex(InvariantError, "external surface receipt"):
            self.swarm.surface_ctrl_evidence(Role.CTRL, "metrics", surface_kind=CtrlSurfaceKind.INLINE_TABLE, caption="Routing improved.", claim_limit="Local run only.", surface_receipt="")
        receipt=self.swarm.surface_ctrl_evidence(Role.CTRL, "metrics", surface_kind=CtrlSurfaceKind.INLINE_TABLE, caption="12 routes: 12 passed, p95 81 ms.", claim_limit="Local API proof only.", surface_receipt="chat:table:metrics")
        self.assertEqual(receipt,"chat:table:metrics")

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
        self.assertIn("CTRL emits a human review event only when", self.skill)
        self.assertIn("If none changed, emit nothing", self.skill)
        self.assertIn("internal telemetry, not CTRL feed events", self.skill)
        self.assertIn("Suppress duplicate re-embedding and decorative evidence", self.skill)

    def test_ctrl_feed_is_human_readable_and_proof_first(self):
        self.assertIn("Lead with what is now true for the user", self.skill)
        self.assertIn("surface the smallest decisive proof inline", self.skill)
        self.assertIn("they never replace the visible result", self.skill)
        self.assertIn("a fresh representative screenshot or recording is mandatory", self.skill)
        self.assertIn("show a compact evidence excerpt or before/after table", self.skill)

    def test_progress_reply_cannot_degrade_into_orchestration_narration(self):
        self.assertIn("outcome achieved since the last surfaced event; decisive proof; what remains unproved or failed; next material checkpoint", self.skill)
        self.assertIn("Do not lead with ARCHITECT, LEAD, REVIEW, task inventory, file counts, import counts, or a tool run", self.skill)
        self.assertIn("An architecture event is feed-worthy only when it changes the product contract or blocks/clears implementation", self.skill)
        self.assertIn("A message that contains only coordination status is a SWARM contract violation", self.skill)

    def test_every_swarm_task_delegates_by_default_with_narrow_exceptions(self):
        self.assertIn("Every SWARM task, especially CTRL, delegates at least one bounded outcome-critical", self.skill)
        self.assertIn("Task size, convenience, CTRL status, or preference to work directly are not exceptions", self.skill)
        self.assertIn("This visible-lane threshold never waives default internal-subagent delegation", self.skill)
        self.assertNotIn("Default to CTRL working directly or one atomic owner", self.skill)


if __name__ == "__main__":
    unittest.main()
