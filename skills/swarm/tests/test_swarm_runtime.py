from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import AcceptanceContract, ArtifactIdentity, ArtifactJustification, ArtifactProvenance, ContextPackage, CorrectionDecision, CtrlSurfaceKind, DedupDecision, Depth, EfficiencyMode, HiveRecord, HiveStatus, InvariantError, LaneKind, ReviewEvidence, ReviewScope, ReviewStrategy, ReviewValue, Role, SubagentException, Swarm, Task as RuntimeTask, TaskState, TopologyFacts, VersionedReference, Worker, WorkerState, choose_depth, correction_decision, initial_tier

def Task(*args, **kwargs):
 kwargs.setdefault("subagent_receipt",f"host:thread:{args[0]}")
 kwargs.setdefault("lane_kind",LaneKind.OTHER); kwargs.setdefault("owning_lead_id","L")
 kwargs.setdefault("acceptance_contract",AcceptanceContract(ArtifactIdentity(f"task-{args[0]}","v1","acceptance"),()))
 return RuntimeTask(*args,**kwargs)

def topology(*, objective="ship artifact", artifacts=(ArtifactIdentity("artifact","v1","work"),), surfaces=("artifact",), route="CTRL", lanes=("owner",), edges=(), integration=False, portfolio=False, architecture=False):
 return TopologyFacts(objective,artifacts,surfaces,route,lanes,edges,integration,portfolio,architecture)

class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.s=Swarm(); self.s.add_lead(Role.CTRL,"L"); self.s.add_worker(Role.LEAD,Worker("D","L",1)); self.s.assign(Role.LEAD,Task("A","D","author",1,{},subagent_receipt="host:thread:A"))
 def accept(self, task_id="A", reviewer="independent"):
  evidence=ReviewEvidence(ReviewStrategy.LIGHT,reviewer,True,self.s.tasks[task_id].acceptance_contract.artifact,receipt=(("acceptance",f"review:{task_id}"),),scope=ReviewScope.ACCEPTANCE)
  self.s.review(Role.REVIEW,task_id,evidence,True)
 def test_authority_lanes_and_lifecycle(self):
  self.s.add_lead(Role.CTRL,"bad"); self.assertIn("bad",self.s.topology)
  with self.assertRaises(InvariantError): self.s.change_architecture(Role.LEAD,{})
  with self.assertRaises(InvariantError): self.s.change_architecture(Role.SPECIALIST,{"unauthorized":2})
  with self.assertRaises(InvariantError): self.s.architecture_event(Role.SPECIALIST,"A",goal_id="architecture",accepted_change="change",invalidates_map=True,receipt="receipt",decision_or_blocker="decision")
  self.s.specialist_event(Role.SPECIALIST,"A",specialist_id="manager",profession="MANAGER",goal_id="coordinate",accepted_change="advice",invalidates_map=False,receipt="advice-receipt")
  with self.assertRaises(InvariantError): self.s.specialist_event(Role.LEAD,"A",specialist_id="manager-2",profession="MANAGER",goal_id="coordinate",accepted_change="proposal",invalidates_map=True,receipt="receipt",decision_or_blocker="change")
  with self.assertRaises(InvariantError): self.s.stale(Role.SPECIALIST,"A","manager decision")
  self.assertEqual(self.s.architecture_version,1); self.assertEqual(self.s.tasks["A"].state,TaskState.ACTIVE)
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
  self.accept(); self.s.complete(Role.LEAD,"A",True,True,10,actor_id="L")
  with self.assertRaises(InvariantError): self.s.ctrl_event("HEARTBEAT","A")
 def test_lease(self):
  self.s.lease(Role.CTRL,"repo","L")
  with self.assertRaises(InvariantError): self.s.lease(Role.CTRL,"repo","other")
 def test_adaptive_depth_and_collapse(self):
  self.assertEqual(choose_depth(topology()),Depth.ATOMIC)
  self.assertEqual(choose_depth(topology(artifacts=tuple(ArtifactIdentity("landing",f"v{i}","variant") for i in range(10)))),Depth.ATOMIC)
  portfolio=topology(artifacts=(ArtifactIdentity("repo-a","v1","release"),ArtifactIdentity("repo-b","v1","release"),ArtifactIdentity("repo-c","v1","release")),surfaces=("repo-a","repo-b","repo-c"),route="portfolio acceptance",lanes=("A","B","C"),edges=(("A","B"),("B","C")),integration=True,portfolio=True)
  self.assertEqual(choose_depth(portfolio),Depth.WORKSTREAM)
  self.assertEqual(choose_depth(TopologyFacts(**{**portfolio.__dict__,"architecture_gate":True})),Depth.PROJECT)
  self.s.tasks["A"].state=TaskState.COMPLETE
  self.assertEqual(self.s.collapse(Role.CTRL,"L"),Depth.ATOMIC)
 def test_hygiene_archives_not_deletes_and_preserves_stale_provenance(self):
  self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0
  self.s.workers["D"].task_ids.discard("A")
  self.s.tasks["A"].review_value=ReviewValue.NONE
  self.s.stale(Role.LEAD,"A","superseded contract",now=0,superseded_by="B",promote=["race evidence"])
  with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"): self.s.groom(Role.CTRL,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
  self.assertEqual(self.s.tasks["A"].state,TaskState.STALE); self.assertEqual(self.s.tasks["A"].superseded_by,"B"); self.assertEqual(self.s.tasks["A"].promoted,["race evidence"])
  self.s.tasks["A"].review_value=ReviewValue.PINNED; self.assertEqual(self.s.groom(Role.CTRL,9,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}),[])
 def test_stale_dependency_and_archived_safety(self):
  self.s.assign(Role.LEAD,Task("B","D","author",1,{})); self.s.stale(Role.LEAD,"A","replaced",now=0); self.s.wait(Role.DOER,"B","A")
  self.assertEqual(self.s.groom(Role.CTRL,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}),[])
  self.s.tasks["B"].state=TaskState.COMPLETE; self.s.workers["D"].task_ids.clear()
  with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
   self.s.groom(Role.CTRL,5,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
  self.s.change_architecture(Role.ARCHITECT,{"a":2}); self.assertEqual(self.s.tasks["A"].state,TaskState.STALE)
 def test_review_is_candidate_before_acceptance(self):
  self.accept(); self.assertEqual(self.s.tasks["A"].state,TaskState.REVIEW)
  self.s.complete(Role.LEAD,"A",True,True,7,actor_id="L"); self.assertEqual(self.s.tasks["A"].completed_at,7)
 def test_intelligence_artifacts_and_completion_gates(self):
  self.s.set_intelligence_floor(Role.ARCHITECT,"A",3); self.s.complexity_mismatch(Role.DOER,"A",3); self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("proof","v1","work"),"risk survives compression")
  self.assertEqual(self.s.discover("proof"),["A"]); self.assertIn("risk survives compression",self.s.tasks["A"].findings); self.assertFalse(self.s.project_complete(Role.CTRL,True,True))
 def test_efficiency_uses_value_not_capacity(self):
  self.assertFalse(self.s.should_spawn(independent=False,critical_path=True)); self.assertFalse(self.s.should_spawn(independent=True,critical_path=True,duplicate_artifact="proof")); self.assertTrue(self.s.should_spawn(independent=True,critical_path=True))
  self.assertEqual(initial_tier(risk=3,uncertainty=2,blast_radius=2),3); self.assertEqual(self.s.review_depth(4),"adversarial"); self.s.record_telemetry("auth","DOER",3,"accepted",model="m",attempts=1,productive=2,overhead=1); self.assertEqual(self.s.telemetry["productive"],2); self.assertNotIn("host_usage",self.s.telemetry_events[-1])
  self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("identity","v1","work")); self.assertEqual(self.s.dedup("identity@v1:work"),DedupDecision.REUSE); self.assertEqual(self.s.dedup("identity@v1:work",verification=True),DedupDecision.EXECUTE); self.assertEqual(self.s.route(family="auth",risk=3,uncertainty=2,blast_radius=2,architect_floor=2,historical_floor=3),3); self.assertEqual(self.s.context_decision(affinity=2,bloat=False,stale=False,stalls=0),"reuse"); self.assertEqual(self.s.context_decision(affinity=2,bloat=True,stale=False,stalls=0),"retire")
 def test_stale_clock_and_unresolved_completion(self):
  self.s.change_architecture(Role.ARCHITECT,{"x":2},now=90); self.s.groom(Role.CTRL,100,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":30}); self.assertEqual(self.s.tasks["A"].state,TaskState.STALE); self.assertFalse(self.s.project_complete(Role.CTRL,True,True))
 def test_archived_only_collapses_and_missing_replacement_blocks_complete(self):
  self.s.stale(Role.LEAD,"A","gone",now=0,superseded_by="MISSING"); self.s.workers["D"].task_ids.discard("A")
  with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
   self.s.groom(Role.CTRL,2,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
  self.assertFalse(self.s.project_complete(Role.CTRL,True,True)); self.assertEqual(self.s.collapse(Role.CTRL,"L"),Depth.ATOMIC)
 def test_bounded_context_spine(self):
  with self.assertRaises(InvariantError): ContextPackage.build(goal="g",architecture={},dependencies=[],artifacts=[],acceptance=["a"],history=[str(i) for i in range(1000)],budget=1)
  package=ContextPackage.build(goal="g",architecture={"a":1},dependencies=["d"],artifacts=["x"],acceptance=[],history=[str(i) for i in range(1000)],budget=1); self.assertEqual(package.goal,"g"); self.assertEqual(package.history,())
 def test_context_signal_executes_retirement_and_transfer(self):
  self.s.add_worker(Role.LEAD,Worker("R","L",2)); package=ContextPackage.build(goal="g",architecture={},dependencies=[],artifacts=[],acceptance=[],history=[],budget=1); self.s.package_context(Role.LEAD,"D",package); self.s.workers["D"].context["bloat"]=True
  self.assertEqual(self.s.context_decision(worker_id="D",replacement="R"),"retire"); self.assertEqual(self.s.workers["D"].state,WorkerState.RETIRED); self.assertEqual(self.s.tasks["A"].owner,"R")
 def test_context_drops_obsolete_versions(self):
  p=ContextPackage.build(goal="g",architecture={"contract":2},dependencies=[VersionedReference("contract",1,"dependency"),VersionedReference("contract",2,"dependency")],artifacts=[],acceptance=[],history=[],budget=2); self.assertEqual(p.dependencies,("contract:v2",))
 def test_restore_and_keyed_archive_telemetry(self):
  self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0; self.s.workers["D"].task_ids.discard("A")
  with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
   self.s.groom(Role.CTRL,31,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
  self.assertEqual(self.s.tasks["A"].state,TaskState.COMPLETE)
 def test_zero_completion_timestamp_has_real_archive_duration(self):
  self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0; self.s.workers["D"].task_ids.discard("A")
  with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"): self.s.groom(Role.CTRL,100,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
  self.assertEqual(self.s.tasks["A"].state,TaskState.COMPLETE)
 def test_modes_and_family_preserve_floors(self):
  tiers=[Swarm(mode=m).route(family="security",risk=1,uncertainty=1,blast_radius=1,architect_floor=2,historical_floor=1) for m in EfficiencyMode]
  self.assertTrue(all(t>=2 for t in tiers)); self.assertGreaterEqual(tiers[-1],tiers[0]); self.assertEqual(Swarm(mode=EfficiencyMode.MAX).review_depth(1),"standard")
 def test_high_risk_review_requires_canonical_strategy(self):
  self.s.tasks["A"].risk=4
  with self.assertRaises(InvariantError): self.s.review(Role.REVIEW,"A","independent",True,"standard")
  adversarial=ReviewEvidence(ReviewStrategy.ADVERSARIAL,"independent",True,ArtifactIdentity("review","v1","adversarial"),("attack path",))
  self.s.review(Role.REVIEW,"A",adversarial,True); self.assertFalse(self.s.tasks["A"].review_passed); self.assertEqual(self.s.tasks["A"].review_strategy,"adversarial")
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
  with self.assertRaises(InvariantError): self.s.add_artifact(Role.DOER,"B",ArtifactIdentity("canonical","v2","verification"),source="missing@v1:work",justification=ArtifactJustification.VERIFICATION)
  self.s.add_artifact(Role.DOER,"B",ArtifactIdentity("canonical","v2","verification"),source="canonical@v1:work",justification=ArtifactJustification.VERIFICATION,provenance=ArtifactProvenance("verify-1","canonical@v1:work")); self.assertIn("canonical@v2:verification",self.s.tasks["B"].artifacts)
 def test_assign_registers_artifact_identity(self):
  self.s.assign(Role.LEAD,Task("B","D","author",1,{},artifacts={"canon@v1:work":"B"}))
  with self.assertRaises(InvariantError): self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("canon","v1","work"))
 def test_assignment_and_storage_share_justified_provenance_rules(self):
  primary=ArtifactIdentity("canonical","v1","work")
  self.s.assign(Role.LEAD,Task("B","D","author",1,{},artifacts={primary:"B"}))
  with self.assertRaises(InvariantError): self.s.add_artifact(Role.DOER,"A",primary)
  verification=ArtifactIdentity("canonical","v2","verification")
  self.s.assign(Role.LEAD,Task("C","D","author",1,{},artifacts={verification:"canonical@v1:work"},artifact_justifications={verification.key():ArtifactJustification.VERIFICATION},artifact_provenance={verification.key():ArtifactProvenance("verify-1","canonical@v1:work")}))
  uncertainty=ArtifactIdentity("canonical","v3","uncertainty")
  self.s.add_artifact(Role.DOER,"A",uncertainty,source="canonical@v1:work",justification=ArtifactJustification.UNCERTAINTY,provenance=ArtifactProvenance("uncertain-1","canonical@v1:work"))
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
  self.s.workers["D"].context["affinity"]=1; self.accept(); self.s.complete(Role.LEAD,"A",True,True,1,actor_id="L"); self.assertEqual(self.s.workers["D"].state,WorkerState.WARM)
  with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"): self.s.groom(Role.CTRL,2,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}); self.assertEqual(self.s.tasks["A"].state,TaskState.COMPLETE); self.assertEqual(self.s.workers["D"].state,WorkerState.WARM)
  self.s.add_worker(Role.LEAD,Worker("R","L",2)); self.s.assign(Role.LEAD,Task("B","D","author",1,{})); lesson=HiveRecord("handoff",content="use migration seam",source="worker",source_version="1",provenance={"task":"B"})
  self.s.retire(Role.LEAD,"D","R",lessons=[lesson],now=3); self.assertEqual(self.s.workers["D"].state,WorkerState.RETIRED); self.assertEqual(self.s.tasks["B"].owner,"R"); self.assertIn("handoff",self.s.hive)
  self.s.hive["handoff"].retention="expired"; self.s.groom_hive(Role.CTRL,4); self.s.groom_hive(Role.CTRL,5); self.s.groom_hive(Role.CTRL,6); self.assertEqual(self.s.hive["handoff"].status,HiveStatus.PURGED); self.assertEqual(self.s.hive["handoff"].provenance,{"task":"B"})
 def test_heartbeat_recovery_and_wait_resume(self):
  self.s.tasks["A"].active_goal=True; self.s.tasks["A"].goal_id="g"; self.s.tasks["A"].milestone="proof"; self.s.tasks["A"].review_horizon_minutes=30
  self.assertIsNone(self.s.heartbeat(Role.CTRL,"A",meaningful_progress=False,recent_ctrl_feed=())); self.assertNotIn("A",self.s.scheduled_wakeups)
  self.s.assign(Role.LEAD,Task("B","D","author",1,{})); self.s.wait(Role.DOER,"B","A"); self.assertIsNone(self.s.heartbeat(Role.CTRL,"B",meaningful_progress=False,recent_ctrl_feed=())); self.accept(reviewer="review"); self.s.complete(Role.LEAD,"A",True,True,1,actor_id="L"); self.assertEqual(self.s.tasks["B"].state,TaskState.ACTIVE)
  with self.assertRaises(InvariantError): self.s.heartbeat(Role.LEAD,"B",meaningful_progress=False,recent_ctrl_feed=())
  with self.assertRaises(InvariantError): self.s.heartbeat(Role.SPECIALIST,"B",meaningful_progress=False,recent_ctrl_feed=())
  self.s.recover(Role.CTRL,"B","accountable diagnosis")
 def test_archive_and_contention_are_fail_closed(self):
  self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0; self.s.tasks["A"].active_goal=True; self.assertEqual(self.s.groom(Role.CTRL,2,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}),[]); self.assertFalse(self.s.should_spawn(independent=True,critical_path=True,contention=True))
 def test_atomic_and_warm_routes_are_executable(self):
  atomic=Swarm()
  with self.assertRaisesRegex(InvariantError,"subagent receipt"): atomic.start_atomic(Role.CTRL,RuntimeTask("missing","M","creator",1,{}))
  with self.assertRaisesRegex(InvariantError,"caller-declared host thread"): atomic.start_atomic(Role.CTRL,RuntimeTask("fake","F","creator",1,{},subagent_receipt="unverified:any-string"))
  atomic.start_atomic(Role.CTRL,Task("T","D","creator",1,{},subagent_receipt="host:thread:T")); self.assertEqual(set(atomic.workers),{"D"}); self.assertEqual(atomic.tasks["T"].owner,"D")
  with self.assertRaisesRegex(InvariantError,"authority, profession, or retired role identity"): atomic.start_atomic(Role.CTRL,Task("drift","CTRL","creator",1,{},subagent_receipt="host:thread:drift"))
  with self.assertRaisesRegex(InvariantError,"authority, profession, or retired role identity"): atomic.start_atomic(Role.CTRL,Task("normalized-drift"," ctrl ","creator",1,{},subagent_receipt="host:thread:normalized-drift"))
  self.assertFalse(hasattr(Role,"MOTHER"))
  with self.assertRaisesRegex(InvariantError,"retired role identity"): atomic.start_atomic(Role.CTRL,Task("drift-mother","MOTHER","creator",1,{},subagent_receipt="host:thread:drift-mother"))
  with self.assertRaisesRegex(InvariantError,"reserved sensor identity"): atomic.start_atomic(Role.CTRL,Task("drift-watchdog","WATCHDOG","creator",1,{},subagent_receipt="host:thread:drift-watchdog"))
  with self.assertRaisesRegex(InvariantError,"authority, profession, or retired role identity"): self.s.add_worker(Role.LEAD,Worker("LEAD","L",2))
  self.s.workers["D"].state=WorkerState.WARM; self.s.workers["D"].context={"affinity":2,"architecture":{"auth":2}}; reused=self.s.reuse_warm(Role.LEAD,Task("R","new","creator",1,{},subagent_receipt="host:thread:R"),architecture={"auth":2},affinity=2); self.assertEqual(reused,"D")
  self.assertIsNone(self.s.reuse_warm(Role.LEAD,Task("N","new","creator",1,{},subagent_receipt="host:thread:N"),architecture={"auth":3},affinity=2))
 def test_only_doer_mutates_artifacts(self):
  self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("owned","v1","work"))
  for controller in (Role.CTRL,Role.LEAD):
   with self.assertRaises(InvariantError): self.s.add_artifact(controller,"A",ArtifactIdentity(f"blocked-{controller.value.lower()}","v1","work"))
 def test_assignment_blocks_substantive_work_without_delegation_contract(self):
  blocked=RuntimeTask("blocked","D","creator",1,{})
  with self.assertRaisesRegex(InvariantError,"subagent receipt"): self.s.assign(Role.LEAD,blocked)
  self.assertNotIn("blocked",self.s.tasks)
 def test_duplicate_lane_rejected(self):
  with self.assertRaises(InvariantError): self.s.add_worker(Role.LEAD,Worker("D2","L",1))
 def test_archive_rejects_every_live_owner_state_until_release(self):
  for state in (WorkerState.SPAWNED,WorkerState.ACTIVE,WorkerState.WARM,WorkerState.DRAINING):
   self.s.workers["D"].state=state; self.s.workers["D"].task_ids.add("A"); self.s.tasks["A"].state=TaskState.COMPLETE; self.s.tasks["A"].completed_at=0
   self.assertEqual(self.s.groom(Role.CTRL,1,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1}),[])
  self.s.workers["D"].task_ids.discard("A")
  with self.assertRaisesRegex(InvariantError,"no host-pinned trust root or IPC verifier"):
   self.s.groom(Role.CTRL,1,{"no_review_archive_delay":0,"low_review_retention":2,"high_review_retention":3,"stale_task_archive_delay":1})
 def test_context_cost_includes_full_canonical_package(self):
  p=ContextPackage.build(goal="g",architecture={"a":1,"b":2},dependencies=["d"],artifacts=[],acceptance=["accept"],history=[],budget=4)
  self.assertEqual(p.transfer_cost,5) # goal, acceptance, two architecture entries, admitted dependency
 def test_hop_receipts_are_bounded_and_proportional(self):
  atomic=Swarm(); atomic.start_atomic(Role.CTRL,Task("T","D","c",1,{},subagent_receipt="host:thread:T")); self.assertEqual(atomic.tasks["T"].topology_receipt,("CTRL","DOER","atomic:isolated"))
  portfolio=topology(lanes=("A","B","C"),edges=(("A","B"),("B","C")),integration=True,portfolio=True)
  self.assertEqual(choose_depth(portfolio),Depth.WORKSTREAM); self.assertEqual(choose_depth(TopologyFacts(**{**portfolio.__dict__,"architecture_gate":True})),Depth.PROJECT)
 def test_typed_justification_and_bounded_machine_receipts(self):
  self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("canon","v1","work"))
  with self.assertRaises(InvariantError): self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("canon","v2","verification"),source="canon@v1:work",justification="verification")
  for _ in range(70): self.s.record_telemetry("task","DOER",1,"ok")
  self.assertLessEqual(len(self.s.events),64); self.assertLessEqual(len(self.s.telemetry_events),64)
 def test_configured_task_event_log_keeps_only_recent_metadata(self):
  self.s.task_event_limit=8
  for index in range(12): self.s._record("events",("RECOVERY",f"task-{index}"))
  self.assertEqual(len(self.s.events),8)
  self.assertEqual(self.s.events[0],("RECOVERY","task-4"))
  self.s.task_event_limit=0
  before=tuple(self.s.events)
  with self.assertRaisesRegex(InvariantError,"task event limit"): self.s._record("events",("RECOVERY","invalid"))
  self.assertEqual(tuple(self.s.events),before)
 def test_scope_discipline_blocks_only_material_invariant_findings(self):
  before=(len(self.s.tasks),len(self.s.workers),len(self.s.events),self.s.tasks["A"].state)
  self.assertFalse(self.s.scope_finding(Role.DOER,"A","nice-to-have",material=False)); self.assertEqual(before,(len(self.s.tasks),len(self.s.workers),len(self.s.events),self.s.tasks["A"].state))
  self.assertTrue(self.s.scope_finding(Role.DOER,"A","review invariant missing",material=True)); self.assertTrue(self.s.tasks["A"].correction_pending); self.assertEqual(self.s.tasks["A"].state,TaskState.WAITING)
 def test_heartbeat_does_not_recover_or_adapt_work(self):
  self.s.tasks["A"].active_goal=True; self.s.tasks["A"].goal_id="g"; self.s.tasks["A"].milestone="proof"
  before=(self.s.tasks["A"].state,self.s.tasks["A"].owner,set(self.s.topology)); self.assertIsNone(self.s.heartbeat(Role.CTRL,"A",meaningful_progress=False,recent_ctrl_feed=())); self.assertEqual(before,(self.s.tasks["A"].state,self.s.tasks["A"].owner,set(self.s.topology)))
 def test_disabled_hive_is_removed_from_prebuilt_context(self):
  record=HiveRecord("prior",content="useful",source="decision")
  package=ContextPackage.build(goal="g",architecture={},dependencies=[],artifacts=[],acceptance=[],history=[],budget=2,hive=[record])
  self.assertEqual(package.hive,("prior",)); self.s.hive[record.id]=record; self.s.hive_enabled=False; self.s.package_context(Role.LEAD,"D",package)
  self.assertEqual(self.s.workers["D"].context["hive"],()); self.assertEqual(self.s.workers["D"].context["transfer_cost"],1)
 def test_duplicate_provenance_is_globally_rejected(self):
  self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("source","v1","work"))
  self.s.assign(Role.LEAD,Task("B","D","author",1,{})); first=ArtifactProvenance("receipt-1","source@v1:work")
  self.s.add_artifact(Role.DOER,"B",ArtifactIdentity("source","v2","verification"),source="source@v1:work",justification=ArtifactJustification.VERIFICATION,provenance=first)
  with self.assertRaises(InvariantError): self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("source","v3","uncertainty"),source="source@v1:work",justification=ArtifactJustification.UNCERTAINTY,provenance=first)
  self.s.add_artifact(Role.DOER,"A",ArtifactIdentity("source","v4","uncertainty"),source="source@v1:work",justification=ArtifactJustification.UNCERTAINTY,provenance=ArtifactProvenance("receipt-2","source@v1:work"))
 def test_mode_depth_shapes_do_not_manufacture_hierarchy(self):
  self.assertEqual(choose_depth(topology()),Depth.ATOMIC)
  portfolio=topology(lanes=("A","B"),edges=(("A","B"),),integration=True,portfolio=True)
  self.assertEqual(choose_depth(portfolio),Depth.WORKSTREAM)
  self.assertEqual(choose_depth(TopologyFacts(**{**portfolio.__dict__,"architecture_gate":True})),Depth.PROJECT)
  self.assertEqual(Depth.PROJECT.value,"CTRL_SPECIALIST_LEADS_DOERS")
  with self.assertRaises(TypeError): choose_depth(portfolio,mode=EfficiencyMode.MAX)
 def test_identity_not_keyword_similarity_controls_reuse(self):
  migration=topology(objective="migrate plugin",artifacts=(ArtifactIdentity("plugin/swarm","v1","migration"),),surfaces=("plugin/swarm",),route="plugin CTRL")
  landing=topology(objective="redesign landing",artifacts=(ArtifactIdentity("flowwweb/landing","v1","design"),),surfaces=("flowwweb/landing",),route="landing CTRL")
  self.assertFalse(migration.same_ownership_route(landing))
  self.assertTrue(migration.same_ownership_route(topology(objective="migrate plugin",artifacts=(ArtifactIdentity("plugin/swarm","v1","migration"),),surfaces=("plugin/swarm",),route="plugin CTRL")))
 def test_correction_cost_preserves_progress_and_reopens_only_material_authority(self):
  self.assertEqual(correction_decision(material=False,expected_future_cost=2,correction_cost=1),CorrectionDecision.FIX_FORWARD)
  self.assertEqual(correction_decision(material=False,expected_future_cost=1,correction_cost=2),CorrectionDecision.CONTINUE)
  self.assertEqual(correction_decision(material=True,ownership_failure=True,expected_future_cost=5,correction_cost=1),CorrectionDecision.REOPEN_TOPOLOGY)
  self.assertEqual(correction_decision(material=True,ownership_failure=True,expected_future_cost=0,correction_cost=100),CorrectionDecision.REOPEN_TOPOLOGY)
  self.assertEqual(correction_decision(material=True,ownership_failure=True,expected_future_cost=-1,correction_cost=-1),CorrectionDecision.REOPEN_TOPOLOGY)
  self.assertEqual(correction_decision(material=True,expected_future_cost=5,correction_cost=1),CorrectionDecision.FIX_FORWARD)
 def test_correction_incident_consumes_one_fix_forward_without_retry_loop(self):
  facts={"material":False,"expected_future_cost":5,"correction_cost":1}
  self.assertEqual(self.s.correction("wording-1",**facts),CorrectionDecision.FIX_FORWARD)
  self.assertEqual(self.s.correction("wording-1",**facts),CorrectionDecision.CONTINUE)
  self.assertEqual(self.s.correction("wording-2",**facts),CorrectionDecision.FIX_FORWARD)
  material={"material":True,"expected_future_cost":5,"correction_cost":1}
  self.assertEqual(self.s.correction("risk-1",**material),CorrectionDecision.FIX_FORWARD)
  self.assertEqual(self.s.correction("risk-1",**material),CorrectionDecision.ESCALATE)
  boundary={"material":True,"ownership_failure":True,"expected_future_cost":0,"correction_cost":100}
  self.assertEqual(self.s.correction("owner-collision",**boundary),CorrectionDecision.REOPEN_TOPOLOGY)
  self.assertEqual(self.s.correction("owner-collision",**boundary),CorrectionDecision.REOPEN_TOPOLOGY)
  bounded=Swarm(); bounded.correction_receipts={f"old-{index}":None for index in range(64)}
  self.assertEqual(bounded.correction("new-minor",**facts),CorrectionDecision.CONTINUE)
  self.assertEqual(bounded.correction("new-material",**material),CorrectionDecision.ESCALATE)
  self.assertEqual(len(bounded.correction_receipts),64)
 def test_ctrl_events_are_semantic_and_bounded(self):
  self.s.register_ctrl_evidence(Role.DOER,"A","proof","test","proof.txt")
  with self.assertRaises(InvariantError): self.s.ctrl_event("REVIEW_FAIL","A",1,outcome="Blocked",evidence_id="proof",next_checkpoint="Fix it")
  self.s.surface_ctrl_evidence(Role.CTRL,"proof",surface_kind=CtrlSurfaceKind.INLINE_EXCERPT,caption="One receipt mismatch.",claim_limit="Local proof only.",surface_receipt="chat:excerpt:1")
  rendered=self.s.ctrl_event("REVIEW_FAIL","A",1,outcome="Routing acceptance is blocked.",evidence_id="proof",next_checkpoint="Correct the receipt fixture.")
  self.assertIn("Routing acceptance is blocked.",rendered); self.assertIn("Proof: One receipt mismatch.",rendered); self.assertIn("Claim limit: Local proof only.",rendered); self.assertIn("Next: Correct the receipt fixture.",rendered)
  for event in ("PROGRESS","HEARTBEAT","RECOVERY"):
   with self.assertRaises(InvariantError): self.s.ctrl_event(event,"A")
  self.assertIsNotNone(self.s.ctrl_event("DEADLOCK","A",2,outcome="Routing is blocked.",evidence_id="proof",next_checkpoint="Remove the ownership cycle."))
  self.assertIsNotNone(self.s.ctrl_event("RESULT","A",3,outcome="Routing proof passed.",evidence_id="proof"))
  self.assertIsNotNone(self.s.ctrl_event("DECISION","A",4,outcome="Use the canonical transaction.",evidence_id="proof"))
  self.assertIsNone(self.s.ctrl_event("raw-label","A"))
 def test_ctrl_event_receipt_suppresses_unchanged_and_rearms_on_material_revision(self):
  self.s.register_ctrl_evidence(Role.DOER,"A","proof","test","proof.txt")
  self.s.surface_ctrl_evidence(Role.CTRL,"proof",surface_kind=CtrlSurfaceKind.INLINE_RECEIPT,caption="Verified receipt.",claim_limit="Local only.",surface_receipt="chat:receipt:1")
  args=dict(outcome="Receipt verified.",evidence_id="proof",next_checkpoint="Run browser proof.")
  self.assertIsNotNone(self.s.ctrl_event("HANDOFF","A","evidence-1",**args))
  self.assertIsNone(self.s.ctrl_event("HANDOFF","A","evidence-1",**args))
  self.assertIsNotNone(self.s.ctrl_event("HANDOFF","A","evidence-2",**args))
  self.accept(); self.s.complete(Role.LEAD,"A",True,True,1,actor_id="L")
  self.assertIsNotNone(self.s.ctrl_event("ACCEPTANCE","A","accepted",outcome="Routing accepted.",evidence_id="proof"))
if __name__ == "__main__": unittest.main()
