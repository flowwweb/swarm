from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import ArtifactIdentity, ContextPackage, DedupDecision, Depth, EfficiencyMode, HiveRecord, HiveStatus, InvariantError, ReviewEvidence, ReviewStrategy, ReviewValue, Role, Swarm, Task, TaskState, VersionedReference, Worker, WorkerState, choose_depth, initial_tier

class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.s=Swarm(); self.s.add_lead(Role.MOTHER,"L"); self.s.add_worker(Role.LEAD,Worker("D","L",1)); self.s.assign(Role.LEAD,Task("A","D","author",1,{}))
 def test_authority_lanes_and_lifecycle(self):
  with self.assertRaises(InvariantError): self.s.add_lead(Role.CTRL,"bad")
  with self.assertRaises(InvariantError): self.s.change_architecture(Role.LEAD,{})
  self.s.add_worker(Role.LEAD,Worker("D2","L",2)); self.s.add_worker(Role.LEAD,Worker("R","L",3))
  with self.assertRaises(InvariantError): self.s.add_worker(Role.LEAD,Worker("D4","L",1))
  self.s.retire(Role.LEAD,"D","R"); self.assertEqual(self.s.workers["D"].state,WorkerState.RETIRED); self.assertEqual(self.s.tasks["A"].owner,"R")
 def test_wip_expert_wait_deadlock_and_recovery(self):
  self.s.assign(Role.LEAD,Task("B","D","author",1,{})); self.s.assign(Role.LEAD,Task("C","D","author",1,{}))
  with self.assertRaises(InvariantError): self.s.assign(Role.LEAD,Task("D","D","author",1,{}))
  self.s.expert(Role.DOER,"A"); self.assertEqual(self.s.tasks["A"].owner,"D")
  self.s.wait(Role.DOER,"A","B"); self.s.wait(Role.DOER,"B","A"); self.assertIn(("DEADLOCK","B"),self.s.events)
  self.s.recover(Role.LEAD,"A","new evidence")
  with self.assertRaises(InvariantError): self.s.recover(Role.LEAD,"A","new evidence")
 def test_versions_review_completion_and_ctrl(self):
  self.s.change_architecture(Role.ARCHITECT,{"auth":2}); self.assertEqual(self.s.tasks["A"].state,TaskState.STALE)
  self.s.tasks["A"].state=TaskState.ACTIVE
  with self.assertRaises(InvariantError): self.s.review(Role.REVIEW,"A","author",True)
  self.s.review(Role.REVIEW,"A","independent",False,"missing proof"); self.assertEqual(self.s.tasks["A"].findings,["missing proof"])
  self.s.review(Role.REVIEW,"A","independent",True); self.s.complete(Role.MOTHER,"A",True,True,10)
  self.assertIsNone(self.s.ctrl_event("HEARTBEAT","A")); self.assertIn("review fail",self.s.ctrl_event("REVIEW_FAIL","A"))
 def test_lease(self):
  self.s.lease(Role.MOTHER,"repo","L")
  with self.assertRaises(InvariantError): self.s.lease(Role.MOTHER,"repo","other")
 def test_adaptive_depth_and_collapse(self):
  self.assertEqual(choose_depth(scope=1),Depth.ATOMIC)
  self.assertEqual(choose_depth(scope=2,independent_tasks=1),Depth.SIMPLE)
  self.assertEqual(choose_depth(scope=3,independent_tasks=2,useful_parallelism=2),Depth.WORKSTREAM)
  self.assertEqual(choose_depth(scope=5,architecture_impact=True,independent_tasks=3,specialisations=2),Depth.PROJECT)
  self.s.tasks["A"].state=TaskState.COMPLETE
  self.assertEqual(self.s.collapse(Role.MOTHER,"L"),Depth.ATOMIC)
 def test_hygiene_archives_not_deletes_and_preserves_stale_provenance(self):
  self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0
  self.s.tasks["A"].review_value=ReviewValue.NONE
  self.s.stale(Role.LEAD,"A","superseded contract",now=0,superseded_by="B",promote=["race evidence"])
  self.assertEqual(self.s.groom(Role.MOTHER,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}),["A"])
  self.assertEqual(self.s.tasks["A"].state,TaskState.ARCHIVED_STALE); self.assertEqual(self.s.tasks["A"].superseded_by,"B"); self.assertEqual(self.s.tasks["A"].promoted,["race evidence"])
  self.s.tasks["A"].review_value=ReviewValue.PINNED; self.assertEqual(self.s.groom(Role.MOTHER,9,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}),[])
 def test_stale_dependency_and_archived_safety(self):
  self.s.assign(Role.LEAD,Task("B","D","author",1,{})); self.s.stale(Role.LEAD,"A","replaced",now=0); self.s.wait(Role.DOER,"B","A")
  self.assertEqual(self.s.groom(Role.MOTHER,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}),[])
  self.s.tasks["B"].state=TaskState.COMPLETE; self.s.groom(Role.MOTHER,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}); self.s.change_architecture(Role.ARCHITECT,{"a":2}); self.assertEqual(self.s.tasks["A"].state,TaskState.ARCHIVED_STALE)
 def test_review_is_candidate_before_acceptance(self):
  self.s.review(Role.REVIEW,"A","independent",True); self.assertEqual(self.s.tasks["A"].state,TaskState.REVIEW)
  self.s.complete(Role.MOTHER,"A",True,True,7); self.assertEqual(self.s.tasks["A"].completed_at,7)
 def test_intelligence_artifacts_and_completion_gates(self):
  self.s.set_intelligence_floor(Role.ARCHITECT,"A",3); self.s.complexity_mismatch(Role.DOER,"A",3); self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("proof","v1","work"),"risk survives compression")
  self.assertEqual(self.s.discover("proof"),["A"]); self.assertIn("risk survives compression",self.s.tasks["A"].findings); self.assertFalse(self.s.project_complete(Role.MOTHER,True,True))
 def test_efficiency_uses_value_not_capacity(self):
  self.assertFalse(self.s.should_spawn(independent=False,critical_path=True)); self.assertFalse(self.s.should_spawn(independent=True,critical_path=True,duplicate_artifact="proof")); self.assertTrue(self.s.should_spawn(independent=True,critical_path=True))
  self.assertEqual(initial_tier(risk=3,uncertainty=2,blast_radius=2),3); self.assertEqual(self.s.review_depth(4),"adversarial"); self.s.record_telemetry("auth","DOER",3,"accepted",model="m",attempts=1,productive=2,overhead=1); self.assertEqual(self.s.telemetry["productive"],2); self.assertNotIn("host_usage",self.s.telemetry_events[-1])
  self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("identity","v1","work")); self.assertEqual(self.s.dedup("identity@v1:work"),DedupDecision.REUSE); self.assertEqual(self.s.dedup("identity@v1:work",verification=True),DedupDecision.EXECUTE); self.assertEqual(self.s.route(family="auth",risk=3,uncertainty=2,blast_radius=2,architect_floor=2,historical_floor=3),3); self.assertEqual(self.s.context_decision(affinity=2,bloat=False,stale=False,stalls=0),"reuse"); self.assertEqual(self.s.context_decision(affinity=2,bloat=True,stale=False,stalls=0),"retire")
 def test_stale_clock_and_unresolved_completion(self):
  self.s.change_architecture(Role.ARCHITECT,{"x":2},now=90); self.s.groom(Role.MOTHER,100,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":30}); self.assertEqual(self.s.tasks["A"].state,TaskState.STALE); self.assertFalse(self.s.project_complete(Role.MOTHER,True,True))
 def test_archived_only_collapses_and_missing_replacement_blocks_complete(self):
  self.s.stale(Role.LEAD,"A","gone",now=0,superseded_by="MISSING"); self.s.groom(Role.MOTHER,2,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}); self.assertFalse(self.s.project_complete(Role.MOTHER,True,True)); self.assertEqual(self.s.collapse(Role.MOTHER,"L"),Depth.ATOMIC)
 def test_bounded_context_spine(self):
  with self.assertRaises(InvariantError): ContextPackage.build(goal="g",architecture={},dependencies=[],artifacts=[],acceptance=["a"],history=[str(i) for i in range(1000)],budget=1)
  package=ContextPackage.build(goal="g",architecture={"a":1},dependencies=["d"],artifacts=["x"],acceptance=[],history=[str(i) for i in range(1000)],budget=1); self.assertEqual(package.goal,"g"); self.assertEqual(package.history,())
 def test_context_signal_executes_retirement_and_transfer(self):
  self.s.add_worker(Role.LEAD,Worker("R","L",2)); package=ContextPackage.build(goal="g",architecture={},dependencies=[],artifacts=[],acceptance=[],history=[],budget=1); self.s.package_context(Role.LEAD,"D",package); self.s.workers["D"].context["bloat"]=True
  self.assertEqual(self.s.context_decision(worker_id="D",replacement="R"),"retire"); self.assertEqual(self.s.workers["D"].state,WorkerState.RETIRED); self.assertEqual(self.s.tasks["A"].owner,"R")
 def test_context_drops_obsolete_versions(self):
  p=ContextPackage.build(goal="g",architecture={"contract":2},dependencies=[VersionedReference("contract",1,"dependency"),VersionedReference("contract",2,"dependency")],artifacts=[],acceptance=[],history=[],budget=2); self.assertEqual(p.dependencies,("contract:v2",))
 def test_restore_and_keyed_archive_telemetry(self):
  self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0; self.s.groom(Role.MOTHER,31,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
  self.assertIsInstance(self.s.telemetry["archive_reasons"],dict); self.s.restore(Role.MOTHER,"A","needed"); self.assertEqual(self.s.tasks["A"].state,TaskState.ACTIVE); self.assertEqual(self.s.telemetry["restores"],1)
 def test_zero_completion_timestamp_has_real_archive_duration(self):
  self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0
  self.s.groom(Role.MOTHER,100,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
  self.assertEqual(self.s.telemetry["completion_to_archive"]["A"],100); self.assertEqual(self.s.telemetry["age_buckets"]["aged"],1)
 def test_modes_and_family_preserve_floors(self):
  tiers=[Swarm(mode=m).route(family="security",risk=1,uncertainty=1,blast_radius=1,architect_floor=2,historical_floor=1) for m in EfficiencyMode]
  self.assertTrue(all(t>=2 for t in tiers)); self.assertGreaterEqual(tiers[-1],tiers[0]); self.assertEqual(Swarm(mode=EfficiencyMode.MAX).review_depth(1),"standard")
 def test_high_risk_review_requires_canonical_strategy(self):
  self.s.tasks["A"].risk=4
  with self.assertRaises(InvariantError): self.s.review(Role.REVIEW,"A","independent",True,"standard")
  adversarial=ReviewEvidence(ReviewStrategy.ADVERSARIAL,"independent",True,ArtifactIdentity("review","v1","adversarial"),("attack path",))
  self.s.review(Role.REVIEW,"A",adversarial,True); self.assertTrue(self.s.tasks["A"].review_passed); self.assertEqual(self.s.tasks["A"].review_strategy,"adversarial")
  self.s.tasks["A"].review_passed=False; self.s.tasks["A"].risk=5
  with self.assertRaises(InvariantError): self.s.review(Role.REVIEW,"A","independent",True,"adversarial")
  with self.assertRaises(InvariantError): self.s.review(Role.REVIEW,"A",ReviewEvidence(ReviewStrategy.SPECIALIST,"independent",True,None),True)
  specialist=ReviewEvidence(ReviewStrategy.SPECIALIST,"independent",True,ArtifactIdentity("review","v2","specialist"),("security finding",),(("specialist","security"),))
  self.s.review(Role.REVIEW,"A",specialist,True); self.assertEqual(self.s.tasks["A"].review_strategy,"specialist")
 def test_architecture_and_security_review_floors_are_authoritative(self):
  self.s.tasks["A"].risk=3; self.s.tasks["A"].architecture_review_floor=ReviewStrategy.ADVERSARIAL; self.s.tasks["A"].security_review_floor=ReviewStrategy.SPECIALIST
  adversarial=ReviewEvidence(ReviewStrategy.ADVERSARIAL,"independent",True,ArtifactIdentity("review","v1","adversarial"))
  with self.assertRaises(InvariantError): self.s.review(Role.REVIEW,"A",adversarial,True)
  specialist=ReviewEvidence(ReviewStrategy.SPECIALIST,"independent",True,ArtifactIdentity("review","v2","specialist"),("security reviewed",),(("specialist","security"),))
  self.s.review(Role.REVIEW,"A",specialist,True); self.assertEqual(self.s.tasks["A"].review_strategy,"specialist")
 def test_artifact_dedup_requires_justified_distinct_provenance(self):
  self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("canonical","v1","work"))
  self.s.assign(Role.LEAD,Task("B","D","author",1,{}))
  with self.assertRaises(InvariantError): self.s.add_artifact(Role.DOER,"B",ArtifactIdentity("canonical","v1","work"))
  self.s.add_artifact(Role.DOER,"B",ArtifactIdentity("canonical","v2","verification"),source="canonical@v1:work",justification="verification"); self.assertIn("canonical@v2:verification",self.s.tasks["B"].artifacts)
 def test_assign_registers_artifact_identity(self):
  self.s.assign(Role.LEAD,Task("B","D","author",1,{},artifacts={"canon@v1:work":"B"}))
  with self.assertRaises(InvariantError): self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("canon","v1","work"))
 def test_assignment_and_storage_share_justified_provenance_rules(self):
  primary=ArtifactIdentity("canonical","v1","work")
  self.s.assign(Role.LEAD,Task("B","D","author",1,{},artifacts={primary:"B"}))
  with self.assertRaises(InvariantError): self.s.add_artifact(Role.DOER,"A",primary)
  verification=ArtifactIdentity("canonical","v2","verification")
  self.s.assign(Role.LEAD,Task("C","D","author",1,{},artifacts={verification:"canonical@v1:work"},artifact_justifications={verification.key():"verification"}))
  uncertainty=ArtifactIdentity("canonical","v3","uncertainty")
  self.s.add_artifact(Role.DOER,"A",uncertainty,source="canonical@v1:work",justification="uncertainty")
  self.assertIn(verification.key(),self.s.artifact_index); self.assertIn(uncertainty.key(),self.s.artifact_index)
 def test_hive_reuses_truth_and_filters_stale_bounded_hydration(self):
  with self.assertRaises(InvariantError): self.s.remember(Role.DOER,HiveRecord("noise",content="status update",source="task",value="noise"),1)
  with self.assertRaises(InvariantError): self.s.remember(Role.DOER,HiveRecord("repo",content="copied",source="repository"),1)
  current=HiveRecord("current",content="auth constraint",source="decision",source_version="2",applicability={"auth":2})
  stale=HiveRecord("stale",content="auth old",source="decision",source_version="1",applicability={"auth":1})
  self.s.remember(Role.DOER,current,1); self.s.remember(Role.DOER,stale,1)
  hydrated=self.s.hydrate_hive("auth",{"auth":2},1,2); self.assertEqual([r.id for r in hydrated],["current"]); self.assertEqual(self.s.telemetry["hive_hydration_count"],1)
  package=ContextPackage.build(goal="g",architecture={"auth":2},dependencies=[],artifacts=[],acceptance=[],history=[],hive=hydrated,budget=2); self.assertEqual(package.hive,("current",))
 def test_hive_warm_retirement_and_provenance_cleanup(self):
  self.s.workers["D"].context["affinity"]=1; self.s.tasks["A"].review_passed=True; self.s.tasks["A"].reviewer="independent"; self.s.complete(Role.MOTHER,"A",True,True,1); self.assertEqual(self.s.workers["D"].state,WorkerState.WARM)
  self.s.groom(Role.MOTHER,2,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}); self.assertEqual(self.s.tasks["A"].state,TaskState.ARCHIVED); self.assertEqual(self.s.workers["D"].state,WorkerState.WARM)
  self.s.add_worker(Role.LEAD,Worker("R","L",2)); self.s.assign(Role.LEAD,Task("B","D","author",1,{})); lesson=HiveRecord("handoff",content="use migration seam",source="worker",source_version="1",provenance={"task":"B"})
  self.s.retire(Role.LEAD,"D","R",lessons=[lesson],now=3); self.assertEqual(self.s.workers["D"].state,WorkerState.RETIRED); self.assertEqual(self.s.tasks["B"].owner,"R"); self.assertIn("handoff",self.s.hive)
  self.s.hive["handoff"].retention="expired"; self.s.groom_hive(Role.MOTHER,4); self.s.groom_hive(Role.MOTHER,5); self.s.groom_hive(Role.MOTHER,6); self.assertEqual(self.s.hive["handoff"].status,HiveStatus.PURGED); self.assertEqual(self.s.hive["handoff"].provenance,{"task":"B"})
 def test_heartbeat_truth_table_latch_and_wait_resume(self):
  self.assertIsNone(self.s.heartbeat(Role.MOTHER,"A",meaningful_progress=True)); self.assertEqual(self.s.heartbeat(Role.MOTHER,"A",meaningful_progress=False),"A:stall/actionable"); self.assertIsNone(self.s.heartbeat(Role.MOTHER,"A",meaningful_progress=False)); self.assertIsNone(self.s.heartbeat(Role.MOTHER,"A",meaningful_progress=True)); self.assertIsNotNone(self.s.heartbeat(Role.MOTHER,"A",meaningful_progress=False))
  self.s.assign(Role.LEAD,Task("B","D","author",1,{})); self.s.wait(Role.DOER,"B","A"); self.assertIsNone(self.s.heartbeat(Role.MOTHER,"B",meaningful_progress=False)); self.s.tasks["A"].review_passed=True; self.s.tasks["A"].reviewer="review"; self.s.complete(Role.MOTHER,"A",True,True,1); self.assertEqual(self.s.tasks["B"].state,TaskState.ACTIVE)
  with self.assertRaises(InvariantError): self.s.heartbeat(Role.LEAD,"B",meaningful_progress=False)
 def test_archive_and_contention_are_fail_closed(self):
  self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0; self.s.tasks["A"].active_goal=True; self.assertEqual(self.s.groom(Role.MOTHER,2,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}),[]); self.assertFalse(self.s.should_spawn(independent=True,critical_path=True,contention=True))
 def test_atomic_simple_and_warm_routes_are_executable(self):
  atomic=Swarm(); atomic.start_atomic(Role.CTRL,Task("T","D","creator",1,{})); self.assertEqual(set(atomic.workers),{"D"}); self.assertEqual(atomic.tasks["T"].owner,"D")
  with self.assertRaises(InvariantError): atomic.start_atomic(Role.MOTHER,Task("U","E","creator",1,{}))
  simple=Swarm(); simple.start_simple(Role.MOTHER,Task("S","M","creator",1,{})); self.assertEqual(simple.workers["M"].lead,"MOTHER")
  self.s.workers["D"].state=WorkerState.WARM; self.s.workers["D"].context={"affinity":2,"architecture":{"auth":2}}; reused=self.s.reuse_warm(Role.LEAD,Task("R","new","creator",1,{}),architecture={"auth":2},affinity=2); self.assertEqual(reused,"D")
  self.assertIsNone(self.s.reuse_warm(Role.LEAD,Task("N","new","creator",1,{}),architecture={"auth":3},affinity=2))
 def test_duplicate_lane_rejected(self):
  with self.assertRaises(InvariantError): self.s.add_worker(Role.LEAD,Worker("D2","L",1))
if __name__ == "__main__": unittest.main()
