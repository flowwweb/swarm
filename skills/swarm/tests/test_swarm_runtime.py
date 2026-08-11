from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import Depth, InvariantError, Role, Swarm, Task, TaskState, Worker, WorkerState, choose_depth

class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.s=Swarm(); self.s.add_lead(Role.MOTHER,"L"); self.s.add_worker(Role.LEAD,Worker("D","L",1)); self.s.assign(Role.LEAD,Task("A","D","author",1,{}))
 def test_authority_lanes_and_lifecycle(self):
  with self.assertRaises(InvariantError): self.s.add_lead(Role.CTRL,"bad")
  with self.assertRaises(InvariantError): self.s.change_architecture(Role.LEAD,{})
  self.s.add_worker(Role.LEAD,Worker("D2","L",2)); self.s.add_worker(Role.LEAD,Worker("D3","L",3))
  with self.assertRaises(InvariantError): self.s.add_worker(Role.LEAD,Worker("D4","L",1))
  self.s.retire(Role.LEAD,"D"); self.assertEqual(self.s.workers["D"].state,WorkerState.RETIRED); self.assertTrue(self.s.workers["D"].archive["tasks"])
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
  self.s.review(Role.REVIEW,"A","independent",True); self.s.complete(Role.MOTHER,"A",True,True)
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
if __name__ == "__main__": unittest.main()
