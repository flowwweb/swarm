from pathlib import Path
from hashlib import sha256
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import AcceptanceContract, ArtifactFileEvidence, ArtifactIdentity, ArtifactParityReceipt, DelegatedEvidence, DelegatedReceiptVerdict, DelegatedReturnReceipt, DelegationContract, IncidentLedger, LaneKind, ProofClass, ReviewEvidence, ReviewScope, ReviewStrategy, Role, Swarm, Task, Worker, derive_workflow_graph


def delegation(task_id:str, owner:str, artifact:ArtifactIdentity, path:str) -> DelegationContract:
    return DelegationContract(task_id,f"Return the exact {task_id} workflow artifact.",owner,(path,),artifact,(path,),(ProofClass.SOURCE,),60)


def delegated_accept(swarm:Swarm, task_id:str) -> None:
    task=swarm.tasks[task_id]; contract=task.delegation_contract
    file=ArtifactFileEvidence(contract.artifact_paths[0],1,sha256(task_id.encode()).hexdigest()); parity=ArtifactParityReceipt.from_files(contract.artifact,(file,))
    evidence=DelegatedEvidence(f"evidence-{task_id}",ProofClass.SOURCE,contract.artifact.key(),sha256(f"proof-{task_id}".encode()).hexdigest(),"Source contract test only.")
    swarm.record_delegated_return(Role.DOER,task_id,DelegatedReturnReceipt(f"return-{task_id}",task_id,contract.owner_id,DelegatedReceiptVerdict.ACCEPT,contract.artifact,"Exact workflow test return.",(evidence,),parity,(),1),actor_id=contract.owner_id)


class WorkflowGraphTests(unittest.TestCase):
    def task(self, task_id:str, owner:str, lead:str)->Task:
        artifact=ArtifactIdentity(f"workflow-{task_id}","v1","non-artifact"); path=f"artifacts/{task_id}.receipt"
        return Task(task_id,owner,"author",1,{},subagent_receipt=f"host:thread:{task_id}",lane_kind=LaneKind.NON_CODE,owning_lead_id=lead,acceptance_contract=AcceptanceContract.empty(),delegation_contract=delegation(task_id,owner,artifact,path))

    def two_lanes(self, reverse:bool=False)->Swarm:
        swarm=Swarm()
        leads=("beta","alpha") if reverse else ("alpha","beta")
        for lead in leads: swarm.add_lead(Role.CTRL,lead)
        workers=(("worker-b","beta",2),("worker-a","alpha",1)) if reverse else (("worker-a","alpha",1),("worker-b","beta",2))
        for worker,lead,lane in workers:
            swarm.add_worker(Role.LEAD,Worker(worker,lead,lane)); swarm.assign(Role.LEAD,self.task(worker[-1].upper(),worker,lead))
        return swarm

    def test_projection_is_deterministic_and_independent_lanes_gain_no_dependency(self):
        first=derive_workflow_graph(self.two_lanes()); second=derive_workflow_graph(self.two_lanes(reverse=True))
        self.assertEqual(first,second)
        self.assertEqual(first.canonical_bytes(),second.canonical_bytes()); self.assertEqual(first.digest(),second.digest()); self.assertEqual(len(first.digest()),64)
        self.assertFalse(any(edge.kind=="waits_for" for edge in first.edges))
        self.assertTrue(all(node.acceptance=="UNVERIFIED" for node in first.nodes))

    def test_transfer_projects_only_current_owner_without_ghost_ownership(self):
        swarm=Swarm(); swarm.add_lead(Role.CTRL,"lead")
        swarm.add_worker(Role.LEAD,Worker("old","lead",1)); swarm.add_worker(Role.LEAD,Worker("new","lead",2)); swarm.assign(Role.LEAD,self.task("T","old","lead"))
        swarm.retire(Role.LEAD,"old","new")
        graph=derive_workflow_graph(swarm); ownership={(edge.source,edge.target) for edge in graph.edges if edge.kind=="owns"}
        self.assertIn(("worker:new","task:T"),ownership); self.assertNotIn(("worker:old","task:T"),ownership)

    def test_missing_dependency_and_cycle_diagnostics_are_stable(self):
        swarm=self.two_lanes(); swarm.tasks["A"].waiting_on="B"; swarm.tasks["B"].waiting_on="A"
        cycled=derive_workflow_graph(swarm)
        self.assertEqual(cycled.diagnostics,("dependency-cycle:A->B->A",))
        swarm.tasks["B"].waiting_on="missing"
        missing=derive_workflow_graph(swarm)
        self.assertEqual(missing.diagnostics,("missing-dependency:B:missing",))

    def test_recorded_manager_profession_is_separate_from_authority_and_watchdog_is_never_a_node(self):
        swarm=self.two_lanes(); swarm.specialist_event(Role.SPECIALIST,"A",specialist_id="manager",profession="MANAGER",goal_id="coordinate",accepted_change="lane brief",invalidates_map=False,receipt="receipt")
        graph=derive_workflow_graph(swarm); kinds={node.id:node.kind for node in graph.nodes}
        self.assertEqual(kinds["specialist:manager"],"MANAGER")
        self.assertNotIn("WATCHDOG",kinds.values()); self.assertFalse(any(node.id.startswith("watchdog:") for node in graph.nodes))

    def test_graph_never_reobserves_artifact_after_recorded_pass(self):
        with tempfile.TemporaryDirectory() as root:
            artifact_path=Path(root)/"artifact.txt"; artifact_path.write_text("version-1",encoding="utf-8")
            artifact=ArtifactIdentity.capture("route","sha-1","release",root=root,paths=("artifact.txt",))
            swarm=Swarm(); swarm.add_lead(Role.CTRL,"lead"); swarm.add_worker(Role.LEAD,Worker("builder","lead",1))
            task=Task("route","builder","author",1,{},subagent_receipt="host:thread:route",lane_kind=LaneKind.CODE,owning_lead_id="lead",acceptance_contract=AcceptanceContract(artifact,("test",),observation_root=root),delegation_contract=delegation("route","builder",artifact,"artifact.txt"))
            swarm.assign(Role.LEAD,task); swarm.consult_incidents(Role.LEAD,"route",IncidentLedger(root),artifact="route",scope="routing",actor_id="lead")
            before=derive_workflow_graph(swarm); self.assertEqual(next(node for node in before.nodes if node.kind=="GATE").state,"UNVERIFIED"); self.assertEqual(swarm.open_gates("route"),("test",))
            swarm.run_gate(Role.LEAD,"route","test",(sys.executable,"-c","pass"),cwd=root,actor_id="lead")
            review=ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,artifact,receipt=(("acceptance","review:route"),),scope=ReviewScope.ACCEPTANCE)
            delegated_accept(swarm,"route")
            swarm.review(Role.REVIEW,"route",review,True)
            passed=derive_workflow_graph(swarm)
            artifact_path.write_text("version-2",encoding="utf-8")
            changed=derive_workflow_graph(swarm)
            self.assertEqual(passed,changed); self.assertEqual(passed.digest(),changed.digest())
            self.assertEqual(next(node for node in changed.nodes if node.id=="task:route").acceptance,"UNVERIFIED")
            kinds={node.kind for node in changed.nodes}; self.assertTrue({"ARTIFACT","GATE","REVIEW"}<=kinds)
            gate=next(node for node in changed.nodes if node.kind=="GATE"); self.assertEqual(gate.state,"PASS")
            edges={edge.kind for edge in changed.edges}; self.assertTrue({"accepts_artifact","has_gate","has_review"}<=edges)
            self.assertEqual(swarm.open_gates("route"),("test",))
            rendered=repr(changed); self.assertNotIn(root,rendered); self.assertNotIn("artifact.txt",rendered); self.assertNotIn(sys.executable,rendered); self.assertNotIn("-c",rendered)


if __name__ == "__main__": unittest.main()
