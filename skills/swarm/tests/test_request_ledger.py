from __future__ import annotations
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import AcceptanceContract, CtrlFeedEventKind, CtrlFeedMessage, CtrlFeedPart, CtrlMode, CtrlSurfaceKind, LaneKind, RequestDue, RequestState, ReviewEvidence, ReviewScope, ReviewStrategy, Role, Swarm, Task, TaskState, WatchdogBinding, WatchdogRouteRole, Worker, derive_workflow_graph
from runtime.request_ledger import RequestStore

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"swarm_contract.py"; SPEC=importlib.util.spec_from_file_location("ledger_contract",SCRIPT); bridge=importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name]=bridge; SPEC.loader.exec_module(bridge)
def task(identity="T"): return Task(identity,"D","creator",1,{},subagent_receipt=f"host:thread:{identity}",lane_kind=LaneKind.NON_CODE,acceptance_contract=AcceptanceContract.empty(),owning_lead_id="L",goal_id=f"goal-{identity}")
def swarm(root):
    value=Swarm(); value.add_lead(Role.CTRL,"L"); value.add_worker(Role.LEAD,Worker("D","L",1)); value.attach_request_store(root); return value
def event(value,task_id,request_ids,suffix,kind,proof_prefix="evd",proof_override=""):
    proof=proof_override or f"{proof_prefix}-proof_{suffix}000"; evidence=f"proof-{suffix}"; receipt=f"evt-event_{suffix}000"
    value.register_ctrl_evidence(Role.DOER,task_id,evidence,"test",f"{suffix}.txt"); value.surface_ctrl_evidence(Role.CTRL,evidence,surface_kind=CtrlSurfaceKind.INLINE_RECEIPT,caption="Current proof.",claim_limit="Local only.",surface_receipt=proof)
    value.register_ctrl_feed_event(Role.CTRL,task_id,receipt,kind,(proof,),tuple(sorted(request_ids))); value.publish_ctrl_feed(Role.CTRL,CtrlFeedMessage(f"msg-event_{suffix}000",((CtrlFeedPart.OUTCOME,"Outcome."),(CtrlFeedPart.PROOF,"Proof.")),(proof,),task_id,f"srf-event_{suffix}000",receipt)); return receipt,proof
def accepted(value,identity="T"):
    staged=value.stage_request_task(Role.CTRL,task(identity)); decision,_=event(value,identity,(staged.request_id,),f"accept{identity}",CtrlFeedEventKind.DECISION,"usr"); view=bridge.register(value,staged.id,decision,accepted_at=1,due=RequestDue("due-accept",2)); value.activate_accepted_task(Role.LEAD,identity,view.record.id); return view

class RequestLedgerTests(unittest.TestCase):
    def test_restart_audit_preserves_identity_history_and_reports_orphan(self):
        with tempfile.TemporaryDirectory() as temp:
            first=swarm(Path(temp)); view=accepted(first); result,proof=event(first,"T",(view.record.id,),"result",CtrlFeedEventKind.RESULT); first.advance_request(Role.LEAD,view.record.id,result,RequestDue("due-result",3))
            fresh=swarm(Path(temp)); audit=fresh.request_audit(4); self.assertEqual(audit.unresolved_ids,(view.record.id,)); self.assertEqual(audit.orphaned_ids,(view.record.id,)); self.assertIn(proof,audit.records[0].evidence_receipts)
            self.assertFalse(fresh.project_complete(Role.CTRL,True,True)); self.assertEqual(fresh.request_watchdog_evidence(4),())
    def test_fresh_runtime_advances_from_persisted_cursor_without_feed_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); first=swarm(root); view=accepted(first); blocker,_=event(first,"T",(view.record.id,),"beforestop",CtrlFeedEventKind.BLOCKER); blocked=first.block_request(Role.LEAD,view.record.id,blocker,RequestDue("due-stop",3)); floor=blocked.record.last_event.feed_sequence
            fresh=swarm(root); fresh.tasks["T"]=task(); fresh.workers["D"].task_ids.add("T"); self.assertEqual(fresh.request_feed_sequence_floor,floor); self.assertFalse(fresh.ctrl_feed_messages)
            resume,_=event(fresh,"T",(view.record.id,),"afterstart",CtrlFeedEventKind.DECISION,"usr"); opened=fresh.resume_request(Role.CTRL,view.record.id,resume,RequestDue("due-restart",4)); self.assertGreater(opened.record.last_event.feed_sequence,floor); self.assertNotIn(blocker,{item.event_receipt for item in fresh.ctrl_feed_messages})
            review_receipt="rev-proof_restartproof000"; review=ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,None,receipt=(("acceptance",review_receipt),),scope=ReviewScope.ACCEPTANCE); fresh.review(Role.REVIEW,"T",review,True)
            progress,_=event(fresh,"T",(view.record.id,),"restartproof",CtrlFeedEventKind.RESULT,"rev"); fresh.advance_request(Role.LEAD,view.record.id,progress,RequestDue("due-final",5)); fresh.complete(Role.LEAD,"T",True,True,6,actor_id="L"); acceptance,_=event(fresh,"T",(view.record.id,),"restartdone",CtrlFeedEventKind.ACCEPTANCE,proof_override=review_receipt); fresh.complete_request(Role.LEAD,view.record.id,acceptance,review_receipt); self.assertFalse(fresh.request_audit(7).unresolved_ids)
    def test_provisional_is_reserved_nonrunnable_and_rollback_needs_live_blocker(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); staged=value.stage_request_task(Role.CTRL,task()); self.assertEqual(value.tasks["T"].state,TaskState.REQUEST_PENDING); self.assertTrue(staged.request_id.startswith("req-"))
            with self.assertRaises(Exception): value.activate_accepted_task(Role.LEAD,"T",staged.request_id)
            blocker,_=event(value,"T",(staged.request_id,),"stageblock",CtrlFeedEventKind.BLOCKER); rolled=value.rollback_request_stage(Role.CTRL,staged.id,blocker); self.assertEqual(rolled.state.value,"ROLLED_BACK"); self.assertEqual(value.tasks["T"].state,TaskState.BACKLOG)
    def test_existing_task_is_unbound_until_exact_accepted_activation(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); first=accepted(value); self.assertIn("T",value.workers["D"].task_ids)
            staged=value.stage_request_task(Role.CTRL,value.tasks["T"]); self.assertEqual(value.tasks["T"].state,TaskState.REQUEST_PENDING); self.assertNotIn("T",value.workers["D"].task_ids)
            decision,_=event(value,"T",(staged.request_id,),"reaccept",CtrlFeedEventKind.DECISION,"usr"); second=bridge.register(value,staged.id,decision,accepted_at=2,due=RequestDue("due-reaccept",4))
            value.tasks["T"].owner="missing"
            with self.assertRaises(Exception): value.activate_accepted_task(Role.LEAD,"T",second.record.id)
            self.assertEqual(value.tasks["T"].state,TaskState.REQUEST_PENDING); self.assertEqual(value.request_audit(0).unresolved_ids,(first.record.id,second.record.id))
    def test_stage_and_accept_revalidate_safe_current_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); unsafe=task(); unsafe.goal_id="bad/path"
            with self.assertRaises(Exception): value.stage_request_task(Role.CTRL,unsafe)
            self.assertEqual(value.request_audit(0).sequence,0)
            staged=value.stage_request_task(Role.CTRL,task()); value.tasks["T"].goal_id="goal-changed"
            decision,_=event(value,"T",(staged.request_id,),"changed",CtrlFeedEventKind.DECISION,"usr")
            with self.assertRaises(Exception): bridge.register(value,staged.id,decision,accepted_at=1,due=RequestDue("due-changed",2))
            audit=value.request_audit(0); self.assertEqual(audit.provisional_stage_ids,(staged.id,)); self.assertFalse(audit.records)
            for index,secret in enumerate(("AKIA1234567890ABCDEF","ASIA1234567890ABCDEF","wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")):
                credential=task(f"C{index}"); credential.goal_id=secret
                with self.assertRaises(Exception): value.stage_request_task(Role.CTRL,credential)
    def test_atomic_stage_failure_leaves_disk_and_runtime_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); original=value.request_store.state.replace_bytes_unlocked
            def fail(_payload): raise OSError("injected write failure")
            value.request_store.state.replace_bytes_unlocked=fail
            with self.assertRaisesRegex(OSError,"injected write failure"): value.stage_request_task(Role.CTRL,task())
            self.assertNotIn("T",value.tasks)
            value.request_store.state.replace_bytes_unlocked=original; self.assertEqual(value.request_audit(0).sequence,0)
    def test_two_attached_writers_preserve_both_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); first=swarm(root); second=swarm(root)
            one=first.stage_request_task(Role.CTRL,task("A")); two=second.stage_request_task(Role.CTRL,task("B"))
            audit=first.request_audit(0); self.assertEqual(set(audit.provisional_stage_ids),{one.id,two.id}); self.assertEqual(audit.sequence,2)
    def test_shared_proof_requires_separate_transitions(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); a=accepted(value); staged=value.stage_request_task(Role.CTRL,task()); decision,_=event(value,"T",(staged.request_id,),"accept2",CtrlFeedEventKind.DECISION,"usr"); b=bridge.register(value,staged.id,decision,accepted_at=2,due=RequestDue("due-second",4)); value.activate_accepted_task(Role.LEAD,"T",b.record.id)
            receipt,_=event(value,"T",(a.record.id,b.record.id),"shared",CtrlFeedEventKind.RESULT); value.advance_request(Role.LEAD,a.record.id,receipt,RequestDue("due-a",5)); middle=value.request_audit(0); self.assertEqual(middle.records[1].evidence_receipts,b.record.evidence_receipts)
            value.advance_request(Role.LEAD,b.record.id,receipt,RequestDue("due-b",5)); after=value.request_audit(0); self.assertGreater(after.sequence,middle.sequence); self.assertEqual(after.records[0].evidence_receipts[-1],after.records[1].evidence_receipts[-1])
    def test_shared_block_and_completion_never_mass_transition(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); a=accepted(value); staged=value.stage_request_task(Role.CTRL,value.tasks["T"]); decision,_=event(value,"T",(staged.request_id,),"jointaccept",CtrlFeedEventKind.DECISION,"usr"); b=bridge.register(value,staged.id,decision,accepted_at=2,due=RequestDue("due-joint",4)); value.activate_accepted_task(Role.LEAD,"T",b.record.id)
            blocker,_=event(value,"T",(a.record.id,b.record.id),"jointblock",CtrlFeedEventKind.BLOCKER); value.block_request(Role.LEAD,a.record.id,blocker,RequestDue("due-a-block",5)); self.assertEqual(value.request_audit(0).records[1].state,RequestState.OPEN); value.block_request(Role.LEAD,b.record.id,blocker,RequestDue("due-b-block",5))
            for record,suffix in ((a,"aresume"),(b,"bresume")):
                resume,_=event(value,"T",(record.record.id,),suffix,CtrlFeedEventKind.DECISION,"usr"); value.resume_request(Role.CTRL,record.record.id,resume,RequestDue(f"due-{suffix}",6))
            review_receipt="rev-proof_joint000"; review=ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,None,receipt=(("acceptance",review_receipt),),scope=ReviewScope.ACCEPTANCE); value.review(Role.REVIEW,"T",review,True); progress,_=event(value,"T",(a.record.id,b.record.id),"joint",CtrlFeedEventKind.RESULT,"rev")
            value.advance_request(Role.LEAD,a.record.id,progress,RequestDue("due-a-final",7)); value.advance_request(Role.LEAD,b.record.id,progress,RequestDue("due-b-final",7)); value.complete(Role.LEAD,"T",True,True,8,actor_id="L"); acceptance,_=event(value,"T",(a.record.id,b.record.id),"jointdone",CtrlFeedEventKind.ACCEPTANCE,proof_override=review_receipt)
            value.complete_request(Role.LEAD,a.record.id,acceptance,review_receipt); self.assertEqual(value.request_audit(0).records[1].state,RequestState.OPEN); value.complete_request(Role.LEAD,b.record.id,acceptance,review_receipt); self.assertFalse(value.request_audit(0).unresolved_ids)
    def test_block_refresh_resume_preserves_history_and_rejects_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); view=accepted(value); blocker,_=event(value,"T",(view.record.id,),"block1",CtrlFeedEventKind.BLOCKER); blocked=value.block_request(Role.LEAD,view.record.id,blocker,RequestDue("due-block",3)); self.assertEqual(blocked.record.state,RequestState.BLOCKED)
            with self.assertRaises(Exception): value.refresh_blocked_request(Role.LEAD,view.record.id,blocker,RequestDue("due-refresh",4))
            later,_=event(value,"T",(view.record.id,),"block2",CtrlFeedEventKind.BLOCKER); value.refresh_blocked_request(Role.LEAD,view.record.id,later,RequestDue("due-refresh",5)); resume,_=event(value,"T",(view.record.id,),"resume",CtrlFeedEventKind.DECISION,"usr"); opened=value.resume_request(Role.CTRL,view.record.id,resume,RequestDue("due-resume",6)); self.assertEqual(opened.record.state,RequestState.OPEN); self.assertIn(blocker,opened.record.transition_receipts)
    def test_initial_accept_is_not_progress_and_events_due_and_proof_advance(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); view=accepted(value); self.assertEqual(value.request_audit(2).unsurfaced_ids,(view.record.id,))
            progress,proof=event(value,"T",(view.record.id,),"progress",CtrlFeedEventKind.RESULT); value.advance_request(Role.LEAD,view.record.id,progress,RequestDue("due-progress",5))
            with self.assertRaises(Exception): value.advance_request(Role.LEAD,view.record.id,progress,RequestDue("due-replay",6))
            earlier,_=event(value,"T",(view.record.id,),"earlier",CtrlFeedEventKind.RESULT)
            with self.assertRaises(Exception): value.advance_request(Role.LEAD,view.record.id,earlier,RequestDue("due-earlier",5))
            repeated="evt-event_repeat000"; value.register_ctrl_feed_event(Role.CTRL,"T",repeated,CtrlFeedEventKind.RESULT,(proof,),(view.record.id,)); value.publish_ctrl_feed(Role.CTRL,CtrlFeedMessage("msg-event_repeat000",((CtrlFeedPart.OUTCOME,"Outcome."),(CtrlFeedPart.PROOF,"Proof.")),(proof,),"T","srf-event_repeat000",repeated))
            with self.assertRaises(Exception): value.advance_request(Role.LEAD,view.record.id,repeated,RequestDue("due-repeat",6))
            audit=value.request_audit(5); self.assertEqual(audit.unsurfaced_ids,()); self.assertEqual(audit.idle_ids,(view.record.id,))
    def test_noncompliant_feed_and_illegal_transition_table_leave_disk_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); view=accepted(value); result,_=event(value,"T",(view.record.id,),"badfeed",CtrlFeedEventKind.RESULT); current=value.ctrl_feed_messages[-1]; value.ctrl_feed_messages[-1]=CtrlFeedMessage(current.id,tuple(reversed(current.parts)),current.proof_receipts,current.task_id,current.surface_receipt,current.event_receipt)
            before=value.request_audit(0).sequence
            cases=(
                ("stage-role",lambda:value.stage_request_task(Role.LEAD,task("X"))),
                ("accept-unknown",lambda:value.accept_request(Role.CTRL,"stg-999999999999","evt-missing_000",accepted_at=1,due=RequestDue("due-x",9))),
                ("activate-unknown",lambda:value.activate_accepted_task(Role.LEAD,"T","req-999999999999")),
                ("rollback-unknown",lambda:value.rollback_request_stage(Role.CTRL,"stg-999999999999","evt-missing_000")),
                ("advance-owner",lambda:value.advance_request(Role.CTRL,view.record.id,result,RequestDue("due-owner",9))),
                ("block-kind",lambda:value.block_request(Role.LEAD,view.record.id,result,RequestDue("due-kind",9))),
                ("refresh-prior",lambda:value.refresh_blocked_request(Role.LEAD,view.record.id,result,RequestDue("due-refresh",9))),
                ("resume-prior",lambda:value.resume_request(Role.CTRL,view.record.id,result,RequestDue("due-resume",9))),
                ("supersede-role",lambda:value.supersede_request(Role.LEAD,view.record.id,"req-999999999999",result)),
                ("cancel-role",lambda:value.cancel_request(Role.LEAD,view.record.id,result)),
                ("complete-feed",lambda:value.complete_request(Role.LEAD,view.record.id,result,"rev-missing_000")),
            )
            for name,operation in cases:
                with self.subTest(name=name),self.assertRaises(Exception): operation()
                self.assertEqual(value.request_audit(0).sequence,before)
    def test_corrupt_stage_record_link_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); value=swarm(root); accepted(value)
            path=root/".codex"/"swarm"/"requests.json"
            payload=json.loads(path.read_text(encoding="utf-8")); next(iter(payload["stages"].values()))["owner"]="other"
            path.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True),encoding="utf-8")
            with self.assertRaises(Exception): value.request_audit(0)
    def test_corrupt_event_cursor_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); value=swarm(root); accepted(value); path=root/".codex"/"swarm"/"requests.json"; payload=json.loads(path.read_text(encoding="utf-8")); next(iter(payload["requests"].values()))["last_event"]["feed_sequence"]=0; path.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True),encoding="utf-8")
            with self.assertRaises(Exception): value.request_audit(0)
    def test_collapse_guard_prevents_partial_worker_and_topology_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); accepted(value); value.add_worker(Role.LEAD,Worker("D2","L",2)); before=(value.workers["D2"].state,dict(value.workers["D2"].archive),set(value.topology),dict(value.hive))
            with self.assertRaises(Exception): value.collapse(Role.CTRL,"L")
            self.assertEqual((value.workers["D2"].state,value.workers["D2"].archive,value.topology,value.hive),before)
    def test_request_watchdog_requires_exact_live_non_ctrl_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); view=accepted(value); task_value=value.tasks["T"]
            task_value.watchdog_binding=WatchdogBinding(Role.LEAD,"L",((WatchdogRouteRole.LEAD,"L"),(WatchdogRouteRole.CTRL,"CTRL")),((WatchdogRouteRole.CTRL,"CTRL"),(WatchdogRouteRole.HUMAN,"HUMAN")))
            evidence=value.request_watchdog_evidence(2); self.assertEqual(len(evidence),1); self.assertEqual(evidence[0].watched_owner,"L")
            task_value.watchdog_binding=WatchdogBinding(Role.LEAD,"other",((WatchdogRouteRole.LEAD,"other"),(WatchdogRouteRole.CTRL,"CTRL")),((WatchdogRouteRole.CTRL,"CTRL"),(WatchdogRouteRole.HUMAN,"HUMAN")))
            self.assertEqual(value.request_watchdog_evidence(2),())
            value.topology.clear(); audit=value.request_audit(2); self.assertIn(view.record.id,audit.orphaned_ids); self.assertEqual(tuple(item.request_id for item in audit.integrity_signals),(view.record.id,)); self.assertEqual(value.request_watchdog_evidence(2),())
    def test_read_only_missing_store_and_enabled_unattached_mode_fail_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"absent"; result=bridge.request_bridge({"operation":"audit","repo_root":str(root),"now":0}); self.assertFalse(result["attached"]); self.assertFalse(root.exists()); self.assertFalse(hasattr(RequestStore,"mutate"))
            with self.assertRaises(ValueError): bridge.request_bridge({"operation":"list","repo_root":"relative"})
            with self.assertRaises(Exception): Swarm().enable_request_continuity("relative")
            enabled=Swarm(request_continuity_enabled=True); enabled.tasks["T"]=task()
            with self.assertRaises(Exception): enabled.stale(Role.CTRL,"T","blocked")
            self.assertEqual(enabled.tasks["T"].state,TaskState.ACTIVE)
    def test_completion_requires_live_review_task_and_request_bound_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); view=accepted(value); review_receipt="rev-proof_review000"; review=ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,None,receipt=(("acceptance",review_receipt),),scope=ReviewScope.ACCEPTANCE); value.review(Role.REVIEW,"T",review,True)
            proof_event,_=event(value,"T",(view.record.id,),"review",CtrlFeedEventKind.RESULT,"rev"); value.advance_request(Role.LEAD,view.record.id,proof_event,RequestDue("due-review",5)); value.complete(Role.LEAD,"T",True,True,6,actor_id="L"); acceptance,_=event(value,"T",(view.record.id,),"acceptance",CtrlFeedEventKind.ACCEPTANCE,proof_override=review_receipt); done=value.complete_request(Role.LEAD,view.record.id,acceptance,review_receipt); self.assertEqual(done.record.state,RequestState.COMPLETED); self.assertFalse(value.request_audit(7).unresolved_ids)
    def test_completed_record_goal_outcome_route_and_stage_drift_fail_live_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); value=swarm(root); view=accepted(value); review_receipt="rev-proof_drift000"; review=ReviewEvidence(ReviewStrategy.LIGHT,"independent",True,None,receipt=(("acceptance",review_receipt),),scope=ReviewScope.ACCEPTANCE); value.review(Role.REVIEW,"T",review,True); progress,_=event(value,"T",(view.record.id,),"drift",CtrlFeedEventKind.RESULT,"rev"); value.advance_request(Role.LEAD,view.record.id,progress,RequestDue("due-drift",5)); value.complete(Role.LEAD,"T",True,True,6,actor_id="L"); acceptance,_=event(value,"T",(view.record.id,),"driftdone",CtrlFeedEventKind.ACCEPTANCE,proof_override=review_receipt); value.complete_request(Role.LEAD,view.record.id,acceptance,review_receipt)
            path=root/".codex"/"swarm"/"requests.json"; canonical=path.read_bytes(); self.assertTrue(value.project_complete(Role.CTRL,True,True))
            for name,change in (
                ("goal",lambda record,stage:record.update(goal_id="goal-drifted")),
                ("outcome",lambda record,stage:record.update(outcome_digest="0"*64)),
                ("route",lambda record,stage:record.update(accepting_route=["L","INDEPENDENT_REVIEW","OTHER"])),
                ("owner-link",lambda record,stage:(record.update(accepted_owner="OTHER"),stage.update(owner="OTHER"))),
            ):
                with self.subTest(name=name):
                    payload=json.loads(canonical); record=next(iter(payload["requests"].values())); stage=next(iter(payload["stages"].values())); change(record,stage); path.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True),encoding="utf-8"); tampered=path.read_bytes(); audit=value.request_audit(7); self.assertIn(view.record.id,audit.orphaned_ids); self.assertFalse(value.project_complete(Role.CTRL,True,True)); self.assertEqual(path.read_bytes(),tampered)
            for name,change in (("stage-contract",lambda stage:stage.update(contract_digest="0"*64)),("stage-task",lambda stage:stage.update(task_id="OTHER"))):
                with self.subTest(name=name):
                    payload=json.loads(canonical); change(next(iter(payload["stages"].values()))); path.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True),encoding="utf-8"); tampered=path.read_bytes()
                    with self.assertRaises(Exception): value.request_audit(7)
                    self.assertFalse(value.project_complete(Role.CTRL,True,True)); self.assertEqual(path.read_bytes(),tampered)
    def test_corrupt_state_and_serialized_mutation_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); value=swarm(root); path=root/".codex"/"swarm"/"requests.json"; path.write_text("{",encoding="utf-8")
            with self.assertRaises(Exception): value.request_audit(0)
            with self.assertRaises(ValueError): bridge.request_bridge({"operation":"accept","repo_root":str(root)})
            self.assertEqual(path.read_text(encoding="utf-8"),"{")
    def test_graph_is_safe_and_terminal_history_does_not_grant_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            value=swarm(Path(temp)); view=accepted(value); graph=derive_workflow_graph(value); self.assertIn(f"request:{view.record.id}",{node.id for node in graph.nodes}); self.assertNotIn("goal-T",graph.canonical_bytes().decode()); self.assertFalse(value.project_complete(Role.CTRL,True,True))

if __name__=="__main__": unittest.main()
