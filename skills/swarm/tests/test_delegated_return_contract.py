from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import (
    AcceptanceContract, ArtifactFileEvidence, ArtifactIdentity, ArtifactParityReceipt,
    CtrlSurfaceKind, DelegatedEvidence, DelegatedReceiptVerdict, DelegatedReturnReceipt,
    DelegatedSignal, DelegationBlockerKind, DelegationContract, DelegationRecoveryAction,
    InvariantError, LaneKind, ProfessionAssignment, ProofClass, ReviewEvidence, ReviewScope,
    ReviewStrategy, Role, Swarm, Task, TaskState, VisualOwnership, VisualReviewContract,
    VisualReviewReceipt, VisualSubstrateState, WorkKind, Worker,
)


class DelegatedReturnContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.path=self.root/"artifact.txt"; self.path.write_text("accepted bytes",encoding="utf-8")
        self.artifact=ArtifactIdentity.capture("delegated","sha-1","handoff",root=self.temp.name,paths=("artifact.txt",))
        self.swarm=Swarm(); self.swarm.add_lead(Role.CTRL,"lead"); self.swarm.add_worker(Role.LEAD,Worker("worker","lead",1))

    def tearDown(self) -> None: self.temp.cleanup()

    def contract(self, *, proof_classes=(ProofClass.SOURCE,ProofClass.STATIC), visual=None, due_at=10) -> DelegationContract:
        return DelegationContract("task","Implement the exact delegated artifact.","worker",("artifact.txt",),self.artifact,("artifact.txt",),proof_classes,due_at,visual_review=visual)

    def assign(self, *, contract=None, work_kind=WorkKind.GENERAL, visual_ownership=VisualOwnership.PRODUCT_EXPERIENCE, profession=None) -> Task:
        task=Task("task","worker","creator",1,{},subagent_receipt="host:thread:task",lane_kind=LaneKind.OTHER,owning_lead_id="lead",acceptance_contract=AcceptanceContract(self.artifact,()),delegation_contract=contract,work_kind=work_kind,visual_ownership=visual_ownership,profession_assignment=profession)
        self.swarm.assign(Role.LEAD,task); return task

    def parity(self, *, path="artifact.txt") -> ArtifactParityReceipt:
        data=self.path.read_bytes(); file=ArtifactFileEvidence(path,len(data),sha256(data).hexdigest())
        return ArtifactParityReceipt.from_files(self.artifact,(file,))

    def evidence(self, proof_classes) -> tuple[DelegatedEvidence,...]:
        return tuple(DelegatedEvidence(f"evidence-{index}",proof_class,self.artifact.key(),sha256(proof_class.value.encode()).hexdigest(),f"{proof_class.value} only.") for index,proof_class in enumerate(proof_classes,1))

    def receipt(self, *, verdict=DelegatedReceiptVerdict.ACCEPT, proof_classes=(ProofClass.SOURCE,ProofClass.STATIC), parity=True, visual=None, dirty=("artifact.txt",), receipt_id="return-1", blocker_kind=None, first_blocker="", remaining=False) -> DelegatedReturnReceipt:
        resolved_parity=self.parity() if parity is True else None if parity is False else parity
        return DelegatedReturnReceipt(receipt_id,"task","worker",verdict,self.artifact,"Bounded readable owner return.",self.evidence(proof_classes),resolved_parity,dirty,12,blocker_kind,first_blocker,remaining,visual)

    def test_assignment_requires_exact_delegated_deliverable_owner_custody_proof_and_return_contract(self) -> None:
        with self.assertRaisesRegex(InvariantError,"delegated tasks require an exact deliverable"):
            self.assign(contract=None)

    def test_created_dispatch_commentary_timeout_silence_and_in_progress_are_not_receipts(self) -> None:
        task=self.assign(contract=self.contract())
        for signal in DelegatedSignal:
            with self.subTest(signal=signal), self.assertRaisesRegex(InvariantError,"are not delegated return receipts"):
                self.swarm.record_delegated_return(Role.DOER,"task",signal,actor_id="worker")
        with self.assertRaisesRegex(InvariantError,"are not delegated return receipts"):
            self.swarm.record_delegated_return(Role.DOER,"task",None,actor_id="worker")
        with self.assertRaisesRegex(InvariantError,"nonempty readable text"):
            DelegatedReturnReceipt("empty","task","worker",DelegatedReceiptVerdict.ACCEPT,self.artifact,"   ")
        self.assertEqual(task.state,TaskState.ACTIVE); self.assertEqual(task.delegated_return_receipts,[])

    def test_exact_readable_accept_advances_only_to_review_and_requires_independent_acceptance(self) -> None:
        task=self.assign(contract=self.contract())
        self.swarm.record_delegated_return(Role.DOER,"task",self.receipt(),actor_id="worker")
        self.assertEqual(task.state,TaskState.REVIEW); self.assertFalse(task.review_passed)
        with self.assertRaisesRegex(InvariantError,"exact-artifact acceptance"):
            self.swarm.complete(Role.LEAD,"task",True,True,20,actor_id="lead")
        review=ReviewEvidence(ReviewStrategy.LIGHT,"reviewer",True,self.artifact,receipt=(("acceptance","review:task"),),scope=ReviewScope.ACCEPTANCE)
        self.swarm.review(Role.REVIEW,"task",review,True); self.swarm.complete(Role.LEAD,"task",True,True,20,actor_id="lead")
        self.assertEqual(task.state,TaskState.COMPLETE)

    def test_reject_and_blocked_are_readable_but_never_advance_acceptance(self) -> None:
        task=self.assign(contract=self.contract())
        with self.assertRaisesRegex(InvariantError,"remaining in-scope work cannot be classified as an external blocker"):
            self.receipt(verdict=DelegatedReceiptVerdict.BLOCKED,parity=False,proof_classes=(),dirty=(),blocker_kind=DelegationBlockerKind.EXTERNAL_STATE,first_blocker="Implementation remains unfinished.",remaining=True)
        blocked=self.receipt(verdict=DelegatedReceiptVerdict.BLOCKED,parity=False,proof_classes=(),dirty=(),blocker_kind=DelegationBlockerKind.IN_SCOPE_WORK,first_blocker="Implementation remains unfinished.",remaining=True)
        self.swarm.record_delegated_return(Role.DOER,"task",blocked,actor_id="worker")
        self.assertEqual(task.state,TaskState.WAITING)
        review=ReviewEvidence(ReviewStrategy.LIGHT,"reviewer",True,self.artifact,receipt=(("acceptance","review:task"),),scope=ReviewScope.ACCEPTANCE)
        with self.assertRaisesRegex(InvariantError,"delegated ACCEPT"):
            self.swarm.review(Role.REVIEW,"task",review,True)

    def test_proof_classes_never_promote_across_source_static_browser_auth_provider_payment_or_live_claims(self) -> None:
        required=(ProofClass.SOURCE,ProofClass.STATIC,ProofClass.LOCAL_INTEGRATION,ProofClass.BROWSER_LOCAL,ProofClass.AUTH,ProofClass.PROVIDER,ProofClass.PAYMENT,ProofClass.DEPLOYED,ProofClass.DEVICE,ProofClass.HUMAN)
        self.assign(contract=self.contract(proof_classes=required))
        with self.assertRaisesRegex(InvariantError,"proof:STATIC"):
            self.swarm.record_delegated_return(Role.DOER,"task",self.receipt(proof_classes=(ProofClass.SOURCE,)),actor_id="worker")
        accepted=self.receipt(proof_classes=required,receipt_id="return-complete")
        self.swarm.record_delegated_return(Role.DOER,"task",accepted,actor_id="worker")
        self.assertEqual(self.swarm.delegation_due("task",now=12).evidence_debt,())

    def test_due_event_surfaces_debt_reorients_same_owner_once_then_routes_existing_review_without_duplication(self) -> None:
        task=self.assign(contract=self.contract(due_at=10)); before=(set(self.swarm.topology),set(self.swarm.workers))
        first=self.swarm.delegation_due("task",now=10)
        self.assertEqual(first.action,DelegationRecoveryAction.REORIENT_OWNER); self.assertEqual(first.evidence_debt[0],"readable_return_receipt"); self.assertIn("missing",first.first_blocker)
        failed=ReviewEvidence(ReviewStrategy.LIGHT,"existing-review",True,self.artifact,findings=("evidence missing",),scope=ReviewScope.SOURCE_SEMANTICS)
        self.swarm.review(Role.REVIEW,"task",failed,False)
        second=self.swarm.delegation_due("task",now=11,existing_review_owner="existing-review")
        self.assertEqual(second.action,DelegationRecoveryAction.ROUTE_EXISTING_REVIEW); self.assertEqual(second.review_owner,"existing-review")
        self.assertEqual(before,(set(self.swarm.topology),set(self.swarm.workers))); self.assertEqual(task.delegation_reorientations,1)

    def test_visual_accept_requires_every_surface_reference_direct_evidence_no_omission_and_real_substrate(self) -> None:
        visual_contract=VisualReviewContract(("desktop","mobile"),("spacing-24","logo-v3"),("references/mockup.png",))
        self.assign(contract=self.contract(proof_classes=(ProofClass.BROWSER_LOCAL,),visual=visual_contract),work_kind=WorkKind.IMAGEGEN,profession=ProfessionAssignment("designer"))
        for identity in ("desktop-proof","mobile-proof"):
            self.swarm.register_ctrl_evidence(Role.DOER,"task",identity,"screenshot",f"{identity}.png")
            self.swarm.surface_ctrl_evidence(Role.CTRL,identity,surface_kind=CtrlSurfaceKind.INLINE_IMAGE,caption=f"{identity} exact final surface.",claim_limit="Local browser visual only.",surface_receipt=f"chat:{identity}")
        incomplete=VisualReviewReceipt(("desktop","mobile"),("spacing-24","logo-v3"),("references/mockup.png",),(("desktop","desktop-proof"),("mobile","mobile-proof")),(("mobile","footer omitted"),),VisualSubstrateState.FALLBACK)
        with self.assertRaisesRegex(InvariantError,"visual_substrate:fallback"):
            self.swarm.record_delegated_return(Role.DOER,"task",self.receipt(proof_classes=(ProofClass.BROWSER_LOCAL,),visual=incomplete),actor_id="worker")
        complete=VisualReviewReceipt(("desktop","mobile"),("spacing-24","logo-v3"),("references/mockup.png",),(("desktop","desktop-proof"),("mobile","mobile-proof")),(),VisualSubstrateState.REAL)
        self.swarm.record_delegated_return(Role.DOER,"task",self.receipt(proof_classes=(ProofClass.BROWSER_LOCAL,),visual=complete,receipt_id="visual-accept"),actor_id="worker")
        self.assertEqual(self.swarm.tasks["task"].state,TaskState.REVIEW)

    def test_ambiguous_owner_dirty_escape_and_artifact_path_parity_fail_closed(self) -> None:
        self.assign(contract=self.contract())
        with self.assertRaisesRegex(InvariantError,"exact task, owner, and artifact"):
            self.swarm.record_delegated_return(Role.DOER,"task",self.receipt(),actor_id="other")
        with self.assertRaisesRegex(InvariantError,"escapes the assigned boundary"):
            self.swarm.record_delegated_return(Role.DOER,"task",self.receipt(dirty=("outside.txt",)),actor_id="worker")
        bad_file=ArtifactFileEvidence("different.txt",len(self.path.read_bytes()),sha256(self.path.read_bytes()).hexdigest())
        bad_parity=ArtifactParityReceipt.from_files(self.artifact,(bad_file,))
        with self.assertRaisesRegex(InvariantError,"path/count/hash parity"):
            self.swarm.record_delegated_return(Role.DOER,"task",self.receipt(parity=bad_parity),actor_id="worker")
        with self.assertRaisesRegex(InvariantError,"count or byte total"):
            ArtifactParityReceipt(self.artifact.key(),(bad_file,),2,bad_file.byte_count,"0"*64)
        for unsafe in ("../escape.txt","C:escape.txt","C:/escape.txt","\\\\server\\share\\proof.txt"):
            with self.subTest(unsafe=unsafe), self.assertRaisesRegex(InvariantError,"declared relative boundary"):
                ArtifactFileEvidence(unsafe,1,"0"*64)

    def test_policy_contract_rejects_activity_promotions_and_requires_visual_and_claim_class_proof(self) -> None:
        root=Path(__file__).resolve().parents[1]
        task=(root/"references"/"task-contract.md").read_text(encoding="utf-8")
        review=(root/"references"/"review-contract.md").read_text(encoding="utf-8")
        monitoring=(root/"references"/"monitoring.md").read_text(encoding="utf-8")
        self.assertRegex(task,r"(?is)creation, dispatch success, commentary, timeout, silence.*in-progress state.*never return\s+evidence")
        self.assertRegex(task,r"(?is)ACCEPT.*independent\s+review.*REJECT.*BLOCKED.*Neither can advance acceptance")
        self.assertRegex(review,r"(?is)every requested viewport, route, state, and artifact\s+surface.*binding reference token and asset.*directly reviewable evidence.*every\s+omission")
        self.assertRegex(review,r"(?is)Source, static, local, browser, authenticated, provider, payment, deployed,\s*device, and human claims are disjoint")
        self.assertRegex(monitoring,r"(?is)full evidence-debt list and its first\s+concrete blocker.*Reorient the same owner\s+at most once.*already-existing independent review\s+owner")
        self.assertRegex(monitoring,r"(?is)Never create a duplicate\s*CTRL or LEAD.*never relabel unfinished in-scope work as an external blocker")


if __name__ == "__main__": unittest.main()
