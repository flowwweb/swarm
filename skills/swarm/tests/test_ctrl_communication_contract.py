from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import (
    CorrectionDecision, CtrlProgressMeasure, CtrlProjectPulse, CtrlPulseProof,
    CtrlPulseReason, CtrlSurfaceKind, InvariantError, ProofClass, Swarm,
    TaskState, WorkKind, audit_ctrl_project_pulses, correction_decision,
)


ROOT=Path(__file__).resolve().parents[1]
PLUGIN_ROOT=ROOT.parents[1]/"plugins"/"swarm"/"skills"/"swarm"


class CtrlCommunicationContractTests(unittest.TestCase):
    def proof(self, receipt="proof-source", proof_class=ProofClass.SOURCE, surface=CtrlSurfaceKind.INLINE_RECEIPT):
        return CtrlPulseProof(receipt,proof_class,"Focused source contract passed.","Source proof only.",surface)

    def pulse(self, **changes):
        values=dict(
            project_id="swarm", ctrl_id="ctrl-main", state=TaskState.ACTIVE,
            reason=CtrlPulseReason.MATERIAL_CHANGE, progress=CtrlProgressMeasure(),
            latest_material="The communication contract is reviewable.",
            update_receipt="update-1", next_action="Run focused contract proof.",
            proofs=(self.proof(),),
        )
        values.update(changes)
        return CtrlProjectPulse(**values)

    def test_progress_is_receipt_backed_or_explicitly_unmeasured(self):
        unknown=CtrlProgressMeasure()
        self.assertIsNone(unknown.percent)
        self.assertEqual(unknown.label,"Unmeasured")
        measured=CtrlProgressMeasure(3,4,"Three of four accepted milestones.",( "milestone-1","milestone-2","milestone-3"),100)
        self.assertEqual(measured.percent,75)
        self.assertEqual(measured.label,"75%")
        with self.assertRaisesRegex(InvariantError,"declared total"):
            CtrlProgressMeasure(6,4,"Guessed progress.",( "guess",),100)
        with self.assertRaisesRegex(InvariantError,"cannot carry guessed"):
            CtrlProgressMeasure(basis="Feels nearly done.")

    def test_compact_pulse_separates_human_summary_from_exact_audit_receipts(self):
        pulse=self.pulse(progress=CtrlProgressMeasure(1,2,"One of two accepted checks.",( "check-1",),101))
        human=pulse.human_view()
        self.assertEqual(human["progress"]["percent"],50)
        self.assertEqual(human["latest_proof"],"Focused source contract passed.")
        self.assertNotIn("update-1",str(human))
        self.assertEqual(pulse.audit_receipts,("update-1","check-1","proof-source"))
        self.assertEqual(pulse.proof_classes,(ProofClass.SOURCE,))
        self.assertNotIn(ProofClass.BROWSER_LOCAL,pulse.proof_classes)

    def test_filler_raw_logs_and_unchanged_heartbeats_do_not_enter_the_pulse(self):
        current=self.pulse()
        with self.assertRaisesRegex(InvariantError,"one bounded human-readable line"):
            self.pulse(latest_material="Still working.\nraw tool log")
        replay=replace(current,update_receipt="update-2",reason=CtrlPulseReason.BOUNDED_DUE)
        audit=audit_ctrl_project_pulses((replay,),previous=(current,))
        self.assertEqual(audit.violations,("swarm:unchanged-heartbeat",))
        self.assertFalse(audit.compliant)

    def test_visual_pulse_surfaces_highest_signal_first_and_every_remaining_visual(self):
        hero=CtrlPulseProof("visual-hero",ProofClass.BROWSER_LOCAL,"Desktop result.","Local browser only.",CtrlSurfaceKind.INLINE_IMAGE)
        narrow=CtrlPulseProof("visual-narrow",ProofClass.BROWSER_LOCAL,"Narrow result.","Local browser only.",CtrlSurfaceKind.INLINE_COMPARISON)
        pulse=self.pulse(work_kind=WorkKind.DESIGN,proofs=(hero,narrow),primary_visual_receipt="visual-hero",gallery_visual_receipts=("visual-narrow",),omissions=("Authenticated state not exercised.",))
        self.assertEqual(pulse.human_view()["primary_visual"],"visual-hero")
        self.assertEqual(pulse.human_view()["gallery_count"],1)
        with self.assertRaisesRegex(InvariantError,"directly surfaced inline visual proof"):
            self.pulse(work_kind=WorkKind.DESIGN,proofs=(self.proof(),))
        with self.assertRaisesRegex(InvariantError,"highest-signal visual first"):
            self.pulse(work_kind=WorkKind.DESIGN,proofs=(hero,narrow),primary_visual_receipt="visual-narrow",gallery_visual_receipts=("visual-hero",))

    def test_blocked_or_stale_pulse_requires_first_concrete_blocker(self):
        with self.assertRaisesRegex(InvariantError,"first concrete blocker"):
            self.pulse(state=TaskState.STALE)
        blocked=self.pulse(state=TaskState.WAITING,first_blocker="Independent receipt is missing.")
        self.assertEqual(blocked.human_view()["first_blocker"],"Independent receipt is missing.")

    def test_material_finding_gets_one_local_fix_while_nits_do_not_loop(self):
        self.assertEqual(correction_decision(material=False,expected_future_cost=9,correction_cost=1),CorrectionDecision.CONTINUE)
        self.assertEqual(correction_decision(material=True,expected_future_cost=9,correction_cost=1),CorrectionDecision.FIX_FORWARD)
        swarm=Swarm()
        facts=dict(material=True,expected_future_cost=9,correction_cost=1)
        self.assertEqual(swarm.correction("same-material-finding",**facts),CorrectionDecision.FIX_FORWARD)
        self.assertEqual(swarm.correction("same-material-finding",**facts),CorrectionDecision.ESCALATE)
        self.assertEqual(correction_decision(material=True,authority_failure=True),CorrectionDecision.REOPEN_TOPOLOGY)

    def test_compact_policy_profile_preserves_product_edge_visual_proof_and_role_continuity(self):
        skill=(ROOT/"SKILL.md").read_text(encoding="utf-8")
        task=(ROOT/"references"/"task-contract.md").read_text(encoding="utf-8")
        review=(ROOT/"references"/"review-contract.md").read_text(encoding="utf-8")
        monitoring=(ROOT/"references"/"monitoring.md").read_text(encoding="utf-8")
        combined="\n".join((skill,task,review,monitoring)).lower()
        for phrase in (
            "reuse, delete, or consolidate", "temporary higher reasoning",
            "root-cause question", "distinctive product edge", "unmeasured",
            "original objective", "profession and authority", "desktop and narrow",
            "source diff, path, or filename is not visual proof",
            "in progress is not done", "blocked` is not accepted",
        ):
            self.assertIn(phrase,combined)
        self.assertIn("source/static/local is not browser/deployed/human",skill.lower())
        self.assertIn("unchanged work stays quiet",monitoring.lower())

    def test_canonical_and_plugin_policy_surfaces_are_identical(self):
        for relative in (
            "SKILL.md", "runtime/core.py", "runtime/__init__.py",
            "references/task-contract.md", "references/review-contract.md",
            "references/monitoring.md",
        ):
            self.assertEqual((ROOT/relative).read_text(encoding="utf-8"),(PLUGIN_ROOT/relative).read_text(encoding="utf-8"),relative)


if __name__=="__main__":
    unittest.main()
