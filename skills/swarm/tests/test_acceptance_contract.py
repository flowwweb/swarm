from pathlib import Path
from hashlib import sha256
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import AcceptanceContract, ArtifactFileEvidence, ArtifactIdentity, ArtifactParityReceipt, ChangedSurface, ChangedSurfaceKind, CtrlSurfaceKind, DelegatedEvidence, DelegatedReceiptVerdict, DelegatedReturnReceipt, DelegationContract, DependencyReach, GateReceipt, IncidentLedger, InvariantError, LaneKind, ProofClaim, ProofClass, ProofInputs, ProofOutcome, RepoProofCapabilities, ReviewEvidence, ReviewScope, ReviewStrategy, Role, RuntimeSignal, Swarm, Task, TaskState, WatchdogReceipt, WatchdogRouteRole, WatchdogScope, WatchdogSignal, Worker, WorkerState, plan_proof


def delegation(task_id, owner, artifact, *, path=None):
    path=path or f"artifacts/{task_id}.receipt"
    return DelegationContract(task_id,f"Return the exact {task_id} artifact.",owner,(path,),artifact,(path,),(ProofClass.SOURCE,),60)


def delegated_accept(swarm, task_id):
    task=swarm.tasks[task_id]; contract=task.delegation_contract
    if contract is None or task.delegated_return_receipts: return
    file=ArtifactFileEvidence(contract.artifact_paths[0],1,sha256(task_id.encode()).hexdigest()); parity=ArtifactParityReceipt.from_files(contract.artifact,(file,))
    evidence=DelegatedEvidence(f"evidence-{task_id}",ProofClass.SOURCE,contract.artifact.key(),sha256(f"proof-{task_id}".encode()).hexdigest(),"Source contract test only.")
    receipt=DelegatedReturnReceipt(f"return-{task_id}",task_id,contract.owner_id,DelegatedReceiptVerdict.ACCEPT,contract.artifact,"Exact delegated test return.",(evidence,),parity,(),1)
    swarm.record_delegated_return(Role.DOER,task_id,receipt,actor_id=contract.owner_id)


class AcceptanceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.artifact_path=Path(self.temp.name)/"artifact.txt"; self.artifact_path.write_text("version-1",encoding="utf-8"); self.artifact=ArtifactIdentity.capture("route","sha-1","release",root=self.temp.name,paths=("artifact.txt",))
        self.swarm=Swarm(); self.swarm.add_lead(Role.CTRL,"lead"); self.swarm.add_worker(Role.LEAD,Worker("builder","lead",1))
        task=Task("route","builder","author",1,{},subagent_receipt="host:thread:route",lane_kind=LaneKind.CODE,owning_lead_id="lead",acceptance_contract=AcceptanceContract(self.artifact,("typecheck","test","build"),observation_root=self.temp.name),delegation_contract=delegation("route","builder",self.artifact,path="artifact.txt"))
        self.swarm.assign(Role.LEAD,task); self.swarm.consult_incidents(Role.LEAD,"route",IncidentLedger(self.temp.name),artifact="route",scope="routing",actor_id="lead")

    def tearDown(self): self.temp.cleanup()

    def receipt(self, gate, outcome=ProofOutcome.PASS, artifact=None):
        artifact=artifact or self.artifact
        return GateReceipt(gate,artifact,outcome,("invented-never-run",),artifact.observables,artifact.observables,0 if outcome is ProofOutcome.PASS else None)

    def run_gate(self, gate, script="pass"):
        return self.swarm.run_gate(Role.LEAD,"route",gate,(sys.executable,"-c",script),cwd=self.temp.name,actor_id="lead")

    def acceptance(self, artifact=None):
        delegated_accept(self.swarm,"route")
        return ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,self.artifact if artifact is None else artifact,receipt=(("acceptance","review:route"),),scope=ReviewScope.ACCEPTANCE)

    def pass_gates(self):
        for gate in ("typecheck","test","build"): self.run_gate(gate)

    def test_external_timeout_and_runtime_fail_remain_open(self):
        self.run_gate("typecheck"); self.swarm.record_gate_receipt(Role.LEAD,"route",self.receipt("test",ProofOutcome.TIMEOUT),actor_id="lead"); self.run_gate("build","raise SystemExit(3)")
        self.assertEqual(self.swarm.open_gates("route"),("test","build"))
        with self.assertRaisesRegex(InvariantError,"PASS receipts"): self.swarm.review(Role.REVIEW,"route",self.acceptance(),True)

    def test_runtime_timeout_is_truthful_and_remains_open(self):
        receipt = self.swarm.run_gate(
            Role.LEAD,
            "route",
            "typecheck",
            (sys.executable, "-c", "import time; time.sleep(2)"),
            cwd=self.temp.name,
            actor_id="lead",
            timeout_seconds=1,
        )
        self.assertEqual(receipt.outcome, ProofOutcome.TIMEOUT)
        self.assertEqual(receipt.attempts, (ProofOutcome.TIMEOUT,))
        self.assertIn("typecheck", self.swarm.open_gates("route"))

    def test_runtime_timeout_terminates_descendant_processes(self):
        marker=Path(self.temp.name)/"late-child.txt"
        child=f"import time; from pathlib import Path; time.sleep(1.5); Path({str(marker)!r}).write_text('leaked',encoding='utf-8')"
        parent=f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(5)"
        receipt=self.swarm.run_gate(Role.LEAD,"route","typecheck",(sys.executable,"-c",parent),cwd=self.temp.name,actor_id="lead",timeout_seconds=1)
        self.assertEqual(receipt.outcome,ProofOutcome.TIMEOUT)
        time.sleep(1)
        self.assertFalse(marker.exists())

    def test_v2_gate_requires_exact_argv_and_policy_drift_reopens(self):
        commands=(("contracts-fast",(sys.executable,"-c","pass")),("impacted-tests",(sys.executable,"-c","pass")))
        capabilities=RepoProofCapabilities(gate_commands=commands)
        inputs=ProofInputs(self.artifact,(ChangedSurface(ChangedSurfaceKind.RUNTIME,("artifact.txt",)),),dependency_reach=DependencyReach(("focused",),known=True),repo_capabilities=capabilities,policy_version="policy-one")
        first=plan_proof(inputs); self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=first)
        with self.assertRaisesRegex(InvariantError,"argv must match"):
            self.run_gate("contracts-fast","raise SystemExit(0)")
        self.swarm.run_gate(Role.LEAD,"route","contracts-fast",commands[0][1],cwd=self.temp.name,actor_id="lead")
        self.assertNotIn("contracts-fast",self.swarm.open_gates("route"))
        second=plan_proof(ProofInputs(self.artifact,inputs.changed_surfaces,dependency_reach=inputs.dependency_reach,repo_capabilities=capabilities,policy_version="policy-two"))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=second)
        self.assertIn("contracts-fast",self.swarm.open_gates("route"))
        wrong_environment=RepoProofCapabilities(gate_commands=commands,environment_fingerprint="0"*64)
        foreign=plan_proof(ProofInputs(self.artifact,inputs.changed_surfaces,dependency_reach=inputs.dependency_reach,repo_capabilities=wrong_environment,policy_version="foreign"))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=foreign)
        with self.assertRaisesRegex(InvariantError,"environment does not match"):
            self.swarm.run_gate(Role.LEAD,"route","contracts-fast",commands[0][1],cwd=self.temp.name,actor_id="lead")

    def test_gate_executes_only_the_exact_planned_environment_snapshot(self):
        key="SWARM_ENV_PROBE"
        original=os.environ.get(key)
        commands=(("contracts-fast",(sys.executable,"-c","pass")),)
        plan=plan_proof(ProofInputs(self.artifact,(ChangedSurface(ChangedSurfaceKind.DOCS,("artifact.txt",)),),dependency_reach=DependencyReach(known=True),repo_capabilities=RepoProofCapabilities(gate_commands=commands)))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=plan)
        try:
            os.environ[key]="changed-after-planning"
            with self.assertRaisesRegex(InvariantError,"environment does not match"):
                self.swarm.run_gate(Role.LEAD,"route","contracts-fast",commands[0][1],cwd=self.temp.name,actor_id="lead")
        finally:
            if original is None: os.environ.pop(key,None)
            else: os.environ[key]=original

    def test_failed_gate_stops_only_its_declared_dependants(self):
        commands=(("contracts-fast",(sys.executable,"-c","raise SystemExit(3)")),("impacted-tests",(sys.executable,"-c","pass")))
        plan=plan_proof(ProofInputs(self.artifact,(ChangedSurface(ChangedSurfaceKind.RUNTIME,("artifact.txt",)),),dependency_reach=DependencyReach(("focused",),known=True),repo_capabilities=RepoProofCapabilities(gate_commands=commands)))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=plan)
        self.swarm.run_gate(Role.LEAD,"route","contracts-fast",commands[0][1],cwd=self.temp.name,actor_id="lead")
        with self.assertRaisesRegex(InvariantError,"dependencies remain open"):
            self.swarm.run_gate(Role.LEAD,"route","impacted-tests",commands[1][1],cwd=self.temp.name,actor_id="lead")

    def test_plan_revision_adopts_unchanged_gate_and_opens_only_broadened_closure(self):
        command=(sys.executable,"-c","pass")
        capabilities=RepoProofCapabilities(gate_commands=(("contracts-fast",command),("impacted-tests",command),("contracts-full",command)))
        surfaces=(ChangedSurface(ChangedSurfaceKind.RUNTIME,("artifact.txt",)),)
        first=self.swarm.plan_proof(ProofInputs(self.artifact,surfaces,dependency_reach=DependencyReach(("focused",),known=True),repo_capabilities=capabilities))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=first)
        for gate in ("contracts-fast","impacted-tests"):
            self.swarm.run_gate(Role.LEAD,"route",gate,command,cwd=self.temp.name,actor_id="lead")
        revised=self.swarm.revise_proof_plan(Role.LEAD,"route",ProofInputs(self.artifact,surfaces,dependency_reach=DependencyReach(("focused",),known=True),runtime_signals=(RuntimeSignal("selector-disagreement","focused"),),repo_capabilities=capabilities),actor_id="lead")
        self.assertNotEqual(first.plan_digest,revised.plan_digest)
        self.assertEqual(self.swarm.open_gates("route"),("contracts-full",))
        self.assertTrue(self.swarm.tasks["route"].gate_receipts["contracts-fast"].adopted)
        snapshot=self.swarm.proof_snapshot("route")
        self.assertEqual(snapshot["metrics"]["adopted"],1)

    def test_declared_claim_without_matching_current_proof_stays_open(self):
        plan=plan_proof(ProofInputs(self.artifact,(ChangedSurface(ChangedSurfaceKind.DOCS,("artifact.txt",)),),declared_claims=(ProofClaim("physical device",ProofClass.DEVICE),),dependency_reach=DependencyReach(known=True)))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=plan)
        self.assertEqual(self.swarm.open_claims("route"),("physical device",))

    def test_proof_snapshot_exposes_current_plan_without_inventing_external_truth(self):
        command=(sys.executable,"-c","pass")
        capabilities=RepoProofCapabilities(gate_commands=(("contracts-fast",command),))
        plan=plan_proof(ProofInputs(self.artifact,(ChangedSurface(ChangedSurfaceKind.DOCS,("artifact.txt",)),),declared_claims=(ProofClaim("human approval",ProofClass.HUMAN),),dependency_reach=DependencyReach(known=True),repo_capabilities=capabilities))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=plan)
        self.swarm.run_gate(Role.LEAD,"route","contracts-fast",command,cwd=self.temp.name,actor_id="lead")
        snapshot=self.swarm.proof_snapshot("route")
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["tier"],"T4")
        self.assertEqual(next(gate for gate in snapshot["gates"] if gate["id"]=="contracts-fast")["status"],"PASS")
        self.assertEqual(next(claim for claim in snapshot["claims"] if claim["name"]=="human approval")["status"],"UNVERIFIED")
        self.assertGreater(snapshot["metrics"]["open"],0)

    def test_external_device_claim_stays_open_without_isolated_host_verifier(self):
        command=(sys.executable,"-c","pass")
        capabilities=RepoProofCapabilities(gate_commands=(("contracts-fast",command),("contracts-full",command),("package-integrity",command),("release-parity",command)))
        plan=plan_proof(ProofInputs(self.artifact,(ChangedSurface(ChangedSurfaceKind.DOCS,("artifact.txt",)),),declared_claims=(ProofClaim("physical device",ProofClass.DEVICE),),dependency_reach=DependencyReach(known=True),repo_capabilities=capabilities))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=plan)
        for gate in ("contracts-fast","contracts-full","package-integrity","release-parity"):
            self.swarm.run_gate(Role.LEAD,"route",gate,command,cwd=self.temp.name,actor_id="lead")
        device_gate=next(gate.id for gate in plan.gates if gate.proof_class is ProofClass.DEVICE)
        with self.assertRaisesRegex(InvariantError,"isolated host verifier"):
            self.swarm._record_host_external_proof(Role.LEAD,"route",device_gate,actor_id="lead",evidence_digest="1"*64,observed_at=int(time.time()),host_signature="forged")
        with self.assertRaisesRegex(InvariantError,"isolated host verifier"):
            self.swarm._record_host_external_proof(Role.LEAD,"route",device_gate,actor_id="lead",evidence_digest="2"*64,observed_at=int(time.time()),host_signature="")
        self.assertEqual(self.swarm.open_gates("route"),(device_gate,))
        self.assertEqual(self.swarm.open_claims("route"),("physical device",))

    def test_external_freshness_expiry_reopens_browser_gate(self):
        command=(sys.executable,"-c","pass")
        capabilities=RepoProofCapabilities(gate_commands=(("contracts-fast",command),("impacted-tests",command),("console-browser",command)))
        plan=plan_proof(ProofInputs(self.artifact,(ChangedSurface(ChangedSurfaceKind.VISUAL,("artifact.txt",)),),dependency_reach=DependencyReach(("focused",),known=True),repo_capabilities=capabilities))
        self.swarm.tasks["route"].acceptance_contract=AcceptanceContract(self.artifact,observation_root=self.temp.name,proof_plan=plan)
        for gate in ("contracts-fast","impacted-tests"):
            self.swarm.run_gate(Role.LEAD,"route",gate,command,cwd=self.temp.name,actor_id="lead")
        receipt=self.swarm.run_gate(Role.LEAD,"route","console-browser",command,cwd=self.temp.name,actor_id="lead")
        self.assertNotIn("console-browser",self.swarm.open_gates("route"))
        object.__setattr__(receipt,"finished_at",int(time.time())-86401)
        self.assertIn("console-browser",self.swarm.open_gates("route"))

    def test_stale_artifact_receipt_and_review_fail_closed(self):
        stale=ArtifactIdentity("route","sha-old","release")
        with self.assertRaisesRegex(InvariantError,"artifact does not match"): self.swarm.record_gate_receipt(Role.LEAD,"route",self.receipt("typecheck",artifact=stale),actor_id="lead")
        self.pass_gates()
        with self.assertRaisesRegex(InvariantError,"artifact does not match"): self.swarm.review(Role.REVIEW,"route",self.acceptance(stale),True)

    def test_changed_observable_artifact_state_reopens_its_gate(self):
        self.run_gate("typecheck"); self.artifact_path.write_text("version-2",encoding="utf-8")
        self.assertEqual(self.swarm.open_gates("route"),("typecheck","test","build"))

    def test_fabricated_never_run_receipts_cannot_close_or_complete(self):
        for gate in ("typecheck","test","build"):
            fabricated=self.receipt(gate); self.swarm.record_gate_receipt(Role.LEAD,"route",fabricated,actor_id="lead")
            self.swarm.tasks["route"].gate_receipts[gate]=fabricated; self.swarm.tasks["route"].unverified_gate_receipts[gate]=fabricated
        self.assertEqual(self.swarm.open_gates("route"),("typecheck","test","build"))
        with self.assertRaisesRegex(InvariantError,"PASS receipts"): self.swarm.review(Role.REVIEW,"route",self.acceptance(),True)

    def test_public_receipt_init_cannot_set_runtime_authority(self):
        artifact=self.artifact
        with self.assertRaises(TypeError): GateReceipt("typecheck",artifact,ProofOutcome.PASS,("invented",),artifact.observables,artifact.observables,0,_authority=object())

    def test_gate_mutation_is_captured_and_fails_closed(self):
        receipt=self.run_gate("typecheck","from pathlib import Path; Path('artifact.txt').write_text('changed',encoding='utf-8')")
        self.assertEqual(receipt.outcome,ProofOutcome.FAIL); self.assertNotEqual(receipt.before,receipt.after)
        self.assertIn("typecheck",self.swarm.open_gates("route"))

    def test_portable_identity_excludes_local_root(self):
        with tempfile.TemporaryDirectory() as other_root:
            (Path(other_root)/"artifact.txt").write_text("version-1",encoding="utf-8"); other=ArtifactIdentity.capture("route","sha-1","release",root=other_root,paths=("artifact.txt",))
            self.assertEqual(other,self.artifact); self.assertEqual(other.key(),self.artifact.key())
            self.assertNotIn(self.temp.name,self.artifact.key()); self.assertNotIn(self.temp.name,repr(self.artifact))
            self.assertNotIn(other_root,other.key()); self.assertNotIn(other_root,repr(other))

    def test_directory_observation_is_rejected(self):
        with self.assertRaisesRegex(InvariantError,"explicit files"):
            ArtifactIdentity.capture("route","sha-1","release",root=self.temp.name,paths=(".",))

    def test_noisy_output_is_not_captured_or_stored(self):
        receipt=self.run_gate("typecheck","import sys; print('x'*1000000); sys.stderr.write('y'*1000000)")
        self.assertEqual(receipt.outcome,ProofOutcome.PASS); self.assertFalse(hasattr(receipt,"stdout_digest")); self.assertFalse(hasattr(receipt,"stderr_digest"))

    def test_observed_artifact_key_round_trips_exactly(self):
        self.assertEqual(self.swarm._artifact(self.artifact.key()),self.artifact)

    def test_source_only_review_cannot_set_final_acceptance(self):
        self.pass_gates(); source=ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,self.artifact,scope=ReviewScope.SOURCE_SEMANTICS)
        self.swarm.review(Role.REVIEW,"route",source,True)
        self.assertFalse(self.swarm.tasks["route"].review_passed)
        with self.assertRaisesRegex(InvariantError,"exact-artifact acceptance"): self.swarm.complete(Role.LEAD,"route",True,True,1,actor_id="lead")

    def test_legacy_passed_true_fails_closed(self):
        with self.assertRaisesRegex(InvariantError,"legacy passed=True"): self.swarm.review(Role.REVIEW,"route","independent",True)

    def test_exact_pass_allows_lead_lane_completion(self):
        self.pass_gates(); self.swarm.review(Role.REVIEW,"route",self.acceptance(),True); self.swarm.complete(Role.LEAD,"route",True,True,1,actor_id="lead")
        self.assertEqual(self.swarm.tasks["route"].state,TaskState.COMPLETE)

    def test_forced_state_cannot_bypass_complete_project_or_ctrl_acceptance(self):
        task=self.swarm.tasks["route"]; task.review_passed=True; task.reviewer="independent"; task.state=TaskState.COMPLETE
        with self.assertRaisesRegex(InvariantError,"direct CTRL-bound"): self.swarm.complete(Role.CTRL,"route",True,True,1,actor_id="CTRL")
        self.assertFalse(self.swarm.project_complete(Role.CTRL,True,True))
        self.swarm.register_ctrl_evidence(Role.LEAD,"route","receipt","proof","receipt.txt")
        self.swarm.surface_ctrl_evidence(Role.CTRL,"receipt",surface_kind=CtrlSurfaceKind.INLINE_RECEIPT,caption="Forced state has no acceptance receipt.",claim_limit="Runtime contract proof only.",surface_receipt="chat:receipt:forced")
        with self.assertRaisesRegex(InvariantError,"completed exact-artifact acceptance"): self.swarm.ctrl_event("ACCEPTANCE","route",1,outcome="Accepted.",evidence_id="receipt")

    def test_explicit_empty_contract_supports_non_code_tasks_without_boolean_bypass(self):
        copy_artifact=ArtifactIdentity("copy","v1","non-artifact")
        other=Task("copy","builder","author",1,{},subagent_receipt="host:thread:copy",lane_kind=LaneKind.NON_CODE,owning_lead_id="lead",acceptance_contract=AcceptanceContract.empty(),delegation_contract=delegation("copy","builder",copy_artifact))
        self.swarm.assign(Role.LEAD,other)
        evidence=ReviewEvidence(ReviewStrategy.LIGHT,"copy-review",True,None,receipt=(("acceptance","review:copy"),),scope=ReviewScope.ACCEPTANCE)
        delegated_accept(self.swarm,"copy")
        self.swarm.review(Role.REVIEW,"copy",evidence,True); self.swarm.complete(Role.LEAD,"copy",True,True,2,actor_id="lead")
        self.assertEqual(self.swarm.tasks["copy"].state,TaskState.COMPLETE)

    def test_omitted_contract_is_not_an_implicit_bypass(self):
        missing_artifact=ArtifactIdentity("missing-contract","v1","non-artifact")
        other=Task("missing-contract","builder","author",1,{},subagent_receipt="host:thread:missing",delegation_contract=delegation("missing-contract","builder",missing_artifact))
        self.swarm.assign(Role.LEAD,other)
        evidence=ReviewEvidence(ReviewStrategy.LIGHT,"copy-review",True,None,receipt=(("acceptance","review:missing"),),scope=ReviewScope.ACCEPTANCE)
        delegated_accept(self.swarm,"missing-contract")
        with self.assertRaisesRegex(InvariantError,"explicit acceptance contract"): self.swarm.review(Role.REVIEW,"missing-contract",evidence,True)

    def test_code_and_artifact_lanes_reject_empty_contracts(self):
        with self.assertRaisesRegex(InvariantError,"only for NON_CODE"):
            self.swarm.assign(Role.LEAD,Task("code-empty","builder","author",1,{},subagent_receipt="host:thread:code",lane_kind=LaneKind.CODE,acceptance_contract=AcceptanceContract.empty()))
        with self.assertRaisesRegex(InvariantError,"at least one named gate"):
            self.swarm.assign(Role.LEAD,Task("code-zero-gates","builder","author",1,{},subagent_receipt="host:thread:zero",lane_kind=LaneKind.CODE,acceptance_contract=AcceptanceContract(ArtifactIdentity("code","v1","acceptance"),())))
        with self.assertRaisesRegex(InvariantError,"only for NON_CODE"):
            self.swarm.assign(Role.LEAD,Task("other-empty","builder","author",1,{},subagent_receipt="host:thread:other",lane_kind=LaneKind.OTHER,acceptance_contract=AcceptanceContract.empty()))
        late_artifact=ArtifactIdentity("late-artifact","v1","non-artifact")
        noncode=Task("late-artifact","builder","author",1,{},subagent_receipt="host:thread:late",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty(),delegation_contract=delegation("late-artifact","builder",late_artifact))
        self.swarm.assign(Role.LEAD,noncode)
        with self.assertRaisesRegex(InvariantError,"artifact-producing lanes"): self.swarm.add_artifact(Role.DOER,"late-artifact",ArtifactIdentity("late","v1","work"))
        self.swarm.add_artifact(Role.DOER,"route",ArtifactIdentity("route-source","v1","work")); self.swarm.tasks["route"].acceptance_contract=AcceptanceContract.empty()
        with self.assertRaisesRegex(InvariantError,"only for NON_CODE"): self.swarm.review(Role.REVIEW,"route",ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,None,receipt=(("acceptance","bad"),),scope=ReviewScope.ACCEPTANCE),True)

    def test_assign_and_reuse_bind_worker_lead_identity(self):
        assigned_artifact=ArtifactIdentity("auto","v1","acceptance")
        assigned=Task("auto-bind","builder","author",1,{},subagent_receipt="host:thread:auto",lane_kind=LaneKind.OTHER,acceptance_contract=AcceptanceContract(assigned_artifact,()),delegation_contract=delegation("auto-bind","builder",assigned_artifact))
        self.swarm.assign(Role.LEAD,assigned); self.assertEqual(assigned.owning_lead_id,"lead")
        mismatch_artifact=ArtifactIdentity("bad","v1","acceptance")
        mismatch=Task("bad-bind","builder","author",1,{},subagent_receipt="host:thread:bad",lane_kind=LaneKind.OTHER,owning_lead_id="other",acceptance_contract=AcceptanceContract(mismatch_artifact,()),delegation_contract=delegation("bad-bind","builder",mismatch_artifact))
        with self.assertRaisesRegex(InvariantError,"match the assigned worker lead"): self.swarm.assign(Role.LEAD,mismatch)
        self.swarm.workers["builder"].state=WorkerState.WARM; self.swarm.workers["builder"].context={"affinity":2,"architecture":{}}
        reuse_artifact=ArtifactIdentity("reuse","v1","acceptance")
        reuse=Task("reuse-bind","new","author",1,{},subagent_receipt="host:thread:reuse",lane_kind=LaneKind.OTHER,owning_lead_id="other",acceptance_contract=AcceptanceContract(reuse_artifact,()),delegation_contract=delegation("reuse-bind","new",reuse_artifact))
        with self.assertRaisesRegex(InvariantError,"match the assigned worker lead"): self.swarm.reuse_warm(Role.LEAD,reuse,architecture={},affinity=1)

    def test_lane_actor_identity_is_bound(self):
        with self.assertRaisesRegex(InvariantError,"bound owning LEAD"): self.swarm.record_gate_receipt(Role.LEAD,"route",self.receipt("typecheck"),actor_id="other-lead")
        self.pass_gates(); self.swarm.review(Role.REVIEW,"route",self.acceptance(),True)
        with self.assertRaisesRegex(InvariantError,"bound owning LEAD"): self.swarm.complete(Role.LEAD,"route",True,True,1,actor_id="other-lead")
        with self.assertRaisesRegex(InvariantError,"direct CTRL-bound"): self.swarm.complete(Role.CTRL,"route",True,True,1,actor_id="CTRL")

    def test_watchdog_receipt_cannot_enter_gate_review_or_acceptance(self):
        alert=WatchdogReceipt("route","goal","lead",WatchdogScope.OUTCOME_INTEGRITY,WatchdogSignal.BLOCKER,"0"*64,"provider outage","lead",((WatchdogRouteRole.CTRL,"CTRL"),),1)
        with self.assertRaisesRegex(InvariantError,"watchdog alerts carry no authority"):
            self.swarm.record_gate_receipt(Role.LEAD,"route",alert,actor_id="lead")
        with self.assertRaisesRegex(InvariantError,"watchdog alerts carry no review authority"):
            self.swarm.review(Role.REVIEW,"route",alert,True)
        self.assertFalse(self.swarm.project_complete(Role.CTRL,True,True))


if __name__=="__main__": unittest.main()
