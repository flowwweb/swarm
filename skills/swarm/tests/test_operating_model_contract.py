import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import AcceptanceContract, ArtifactIdentity, CtrlMode, Depth, InvariantError, LaneKind, Role, SubagentException, Swarm, Task, WatchdogBinding, WatchdogEvidence, WatchdogRouteRole, WatchdogScope, WatchdogSignal, Worker, ctrl_mode


def digest(value:str)->str: return hashlib.sha256(value.encode()).hexdigest()


class OperatingModelTests(unittest.TestCase):
    def test_direct_mode_is_exact(self):
        base=dict(outcomes=1,mutable_surfaces=1,cross_lane_dependency=False,risk=1,measurable_minutes=20,direct_horizon_minutes=20)
        self.assertEqual(ctrl_mode(**base),CtrlMode.DIRECT)
        for change in ({"outcomes":2},{"mutable_surfaces":2},{"cross_lane_dependency":True},{"risk":2},{"measurable_minutes":21}):
            self.assertEqual(ctrl_mode(**{**base,**change}),CtrlMode.DELEGATED)
        swarm=Swarm(); direct=Task("direct","CTRL","CTRL",1,{},risk=1,subagent_exception=SubagentException.WHOLE_TASK_COST,subagent_exception_reason="atomic work is shorter than delegation",lane_kind=LaneKind.CODE,acceptance_contract=AcceptanceContract(ArtifactIdentity("direct","v1","acceptance"),("contract",)))
        swarm.start_ctrl_direct(Role.CTRL,direct,outcomes=1,mutable_surfaces=1,cross_lane_dependency=False,measurable_minutes=10)
        swarm.add_artifact(Role.CTRL,"direct",ArtifactIdentity("direct","v1","work"))

    def ctrl_binding(self)->WatchdogBinding:
        return WatchdogBinding(
            Role.CTRL,"CTRL",
            ((WatchdogRouteRole.CTRL,"CTRL"),(WatchdogRouteRole.HUMAN,"HUMAN")),
            ((WatchdogRouteRole.REVIEW,"INDEPENDENT_REVIEW"),(WatchdogRouteRole.HUMAN,"HUMAN")),
        )

    def tracked(self, *, bound:bool=True)->Swarm:
        swarm=Swarm(); swarm.tasks["T"]=Task("T","CTRL","CTRL",1,{})
        swarm.propose_milestone(Role.CTRL,"T",goal_id="goal",milestone="test passes",proof_kind="test",horizon_minutes=15,now=10,watchdog=self.ctrl_binding() if bound else None)
        return swarm

    def lead_tracked(self)->Swarm:
        swarm=Swarm(); swarm.add_lead(Role.CTRL,"lead"); swarm.add_worker(Role.LEAD,Worker("worker","lead",1)); swarm.tasks["T"]=Task("T","worker","CTRL",1,{},owning_lead_id="lead")
        binding=WatchdogBinding(Role.LEAD,"lead",((WatchdogRouteRole.LEAD,"lead"),(WatchdogRouteRole.CTRL,"CTRL")),((WatchdogRouteRole.CTRL,"CTRL"),(WatchdogRouteRole.HUMAN,"HUMAN")))
        swarm.propose_milestone(Role.LEAD,"T",goal_id="goal",milestone="proof",proof_kind="test",horizon_minutes=15,now=0,watchdog=binding); return swarm

    def evidence(self, scope:WatchdogScope, signal:WatchdogSignal, text:str="observed evidence", owner_integrity:bool=False)->WatchdogEvidence:
        return WatchdogEvidence("T","goal","CTRL",scope,signal,digest(text),text,owner_integrity)

    def test_unbound_goal_has_no_watchdog_surface(self):
        swarm=self.tracked(bound=False)
        self.assertEqual(swarm.scheduled_wakeups,{})
        with self.assertRaisesRegex(InvariantError,"unbound goal"):
            swarm.watchdog_check("T",observer_role=WatchdogRouteRole.CTRL,observer_id="CTRL",now=25,evidence=self.evidence(WatchdogScope.TRAJECTORY,WatchdogSignal.CLEAR))
        self.assertEqual(swarm.tasks["T"].watchdog_receipts,[])

    def test_binding_rejects_missing_self_cyclic_and_fabricated_routes(self):
        integrity=((WatchdogRouteRole.CTRL,"CTRL"),(WatchdogRouteRole.HUMAN,"HUMAN"))
        with self.assertRaisesRegex(InvariantError,"ordinary and owner-integrity routes"):
            WatchdogBinding(Role.LEAD,"lead",(),integrity)
        with self.assertRaisesRegex(InvariantError,"first be heard"):
            WatchdogBinding(Role.LEAD,"lead",((WatchdogRouteRole.CTRL,"CTRL"),),integrity)
        with self.assertRaisesRegex(InvariantError,"skip the watched owner"):
            WatchdogBinding(Role.LEAD,"lead",((WatchdogRouteRole.LEAD,"lead"),),((WatchdogRouteRole.LEAD,"lead"),))
        with self.assertRaisesRegex(InvariantError,"acyclic"):
            WatchdogBinding(Role.LEAD,"lead",((WatchdogRouteRole.LEAD,"lead"),(WatchdogRouteRole.CTRL,"lead")),integrity)
        swarm=Swarm(); swarm.add_lead(Role.CTRL,"lead"); swarm.tasks["T"]=Task("T","worker","CTRL",1,{},owning_lead_id="lead")
        fabricated=WatchdogBinding(Role.LEAD,"lead",((WatchdogRouteRole.LEAD,"lead"),),((WatchdogRouteRole.REVIEW,"invented"),))
        with self.assertRaisesRegex(InvariantError,"fabricated"):
            swarm.propose_milestone(Role.LEAD,"T",goal_id="goal",milestone="proof",proof_kind="test",horizon_minutes=15,now=0,watchdog=fabricated)

    def test_ctrl_binding_requires_independent_review_then_human(self):
        with self.assertRaisesRegex(InvariantError,"independent REVIEW then HUMAN"):
            WatchdogBinding(Role.CTRL,"CTRL",((WatchdogRouteRole.CTRL,"CTRL"),),((WatchdogRouteRole.HUMAN,"HUMAN"),))

    def test_exact_three_scopes_emit_only_declared_signals(self):
        swarm=self.tracked()
        cases=((WatchdogScope.TRAJECTORY,WatchdogSignal.CLEAR,False),(WatchdogScope.FLOW_INTEGRITY,WatchdogSignal.ATTENTION,False),(WatchdogScope.OUTCOME_INTEGRITY,WatchdogSignal.BLOCKER,True))
        for index,(scope,signal,owner_integrity) in enumerate(cases):
            observer=(WatchdogRouteRole.REVIEW,"INDEPENDENT_REVIEW") if owner_integrity else (WatchdogRouteRole.CTRL,"CTRL")
            receipt=swarm.watchdog_check("T",observer_role=observer[0],observer_id=observer[1],now=25+index*15,evidence=self.evidence(scope,signal,f"evidence-{index}",owner_integrity))
            self.assertEqual(receipt.signal,signal)
            expected=self.ctrl_binding().owner_integrity_route if owner_integrity else self.ctrl_binding().alert_route
            self.assertEqual(receipt.alert_route,() if signal is WatchdogSignal.CLEAR else expected)
        self.assertEqual(set(WatchdogScope),{WatchdogScope.TRAJECTORY,WatchdogScope.FLOW_INTEGRITY,WatchdogScope.OUTCOME_INTEGRITY})
        self.assertEqual(set(WatchdogSignal),{WatchdogSignal.CLEAR,WatchdogSignal.ATTENTION,WatchdogSignal.BLOCKER})

    def test_wrong_scope_observer_and_evidence_fail_closed(self):
        swarm=self.tracked()
        with self.assertRaisesRegex(InvariantError,"due evidence"):
            swarm.watchdog_check("T",observer_role=WatchdogRouteRole.CTRL,observer_id="CTRL",now=24,evidence=self.evidence(WatchdogScope.TRAJECTORY,WatchdogSignal.CLEAR))
        with self.assertRaisesRegex(InvariantError,"selected bound route"):
            swarm.watchdog_check("T",observer_role=WatchdogRouteRole.REVIEW,observer_id="INDEPENDENT_REVIEW",now=25,evidence=self.evidence(WatchdogScope.TRAJECTORY,WatchdogSignal.CLEAR))
        wrong=WatchdogEvidence("other","goal","CTRL",WatchdogScope.TRAJECTORY,WatchdogSignal.CLEAR,digest("wrong"),"wrong")
        with self.assertRaisesRegex(InvariantError,"outside its bound"):
            swarm.watchdog_check("T",observer_role=WatchdogRouteRole.CTRL,observer_id="CTRL",now=25,evidence=wrong)
        with self.assertRaisesRegex(InvariantError,"must match the evidence"):
            WatchdogEvidence("T","goal","CTRL",WatchdogScope.TRAJECTORY,WatchdogSignal.CLEAR,digest("different"),"evidence")

    def test_identical_evidence_severity_and_decision_owner_dedupes(self):
        swarm=self.tracked(); evidence=self.evidence(WatchdogScope.FLOW_INTEGRITY,WatchdogSignal.ATTENTION,"same")
        first=swarm.watchdog_check("T",observer_role=WatchdogRouteRole.CTRL,observer_id="CTRL",now=25,evidence=evidence)
        due=swarm.scheduled_wakeups["T"]
        with self.assertRaisesRegex(InvariantError,"due evidence"): swarm.watchdog_check("T",observer_role=WatchdogRouteRole.CTRL,observer_id="CTRL",now=25,evidence=evidence)
        second=swarm.watchdog_check("T",observer_role=WatchdogRouteRole.CTRL,observer_id="CTRL",now=due,evidence=evidence)
        self.assertIs(first,second); self.assertEqual(len(swarm.tasks["T"].watchdog_receipts),1); self.assertEqual(swarm.scheduled_wakeups["T"],due+15)

    def test_alerted_collapse_requires_two_runtime_alerts_owner_context_and_ctrl_decision(self):
        swarm=self.lead_tracked(); first=WatchdogEvidence("T","goal","lead",WatchdogScope.TRAJECTORY,WatchdogSignal.BLOCKER,digest("outage"),"outage")
        swarm.watchdog_check("T",observer_role=WatchdogRouteRole.LEAD,observer_id="lead",now=15,evidence=first)
        with self.assertRaisesRegex(InvariantError,"owner-heard"): swarm.collapse(Role.CTRL,"lead")
        with self.assertRaisesRegex(InvariantError,"two distinct comparable"): swarm.watchdog_owner_context(Role.LEAD,"T",actor_id="lead",evidence_digests=(first.evidence_digest,),cause="provider outage",uncertainty="provider recovery unknown",same_constraints_counterfactual="same owner after recovery",smallest_reversible_response="wait one horizon",reversal_condition="provider recovers")
        second=WatchdogEvidence("T","goal","lead",WatchdogScope.TRAJECTORY,WatchdogSignal.ATTENTION,digest("outage-continued"),"outage-continued")
        swarm.watchdog_check("T",observer_role=WatchdogRouteRole.LEAD,observer_id="lead",now=30,evidence=second)
        args=dict(evidence_digests=(first.evidence_digest,second.evidence_digest),cause="provider outage",uncertainty="provider recovery unknown",same_constraints_counterfactual="same owner after recovery",smallest_reversible_response="pause lane",reversal_condition="revisit next horizon")
        with self.assertRaisesRegex(InvariantError,"exact watched owner"): swarm.watchdog_owner_context(Role.LEAD,"T",actor_id="other",**args)
        urgent=swarm.watchdog_owner_context(Role.LEAD,"T",actor_id="lead",urgent_safety=True,**args)
        with self.assertRaisesRegex(InvariantError,"temporary"): swarm.authorize_watchdog_change(Role.CTRL,urgent,target_kind="collapse",target_id="lead",expected_benefit=5,total_change_cost=3)
        context=swarm.watchdog_owner_context(Role.LEAD,"T",actor_id="lead",**args)
        decision=swarm.authorize_watchdog_change(Role.CTRL,context,target_kind="collapse",target_id="lead",expected_benefit=5,total_change_cost=3)
        self.assertEqual(swarm.collapse(Role.CTRL,"lead",watchdog_review=decision),Depth.ATOMIC)

    def test_ordinary_lead_alert_is_heard_by_lead_and_owner_integrity_bypasses_it(self):
        swarm=Swarm(); swarm.add_lead(Role.CTRL,"lead"); swarm.tasks["T"]=Task("T","worker","CTRL",1,{},owning_lead_id="lead")
        binding=WatchdogBinding(Role.LEAD,"lead",((WatchdogRouteRole.LEAD,"lead"),(WatchdogRouteRole.CTRL,"CTRL")),((WatchdogRouteRole.CTRL,"CTRL"),(WatchdogRouteRole.HUMAN,"HUMAN")))
        swarm.propose_milestone(Role.LEAD,"T",goal_id="goal",milestone="proof",proof_kind="test",horizon_minutes=15,now=0,watchdog=binding)
        ordinary=WatchdogEvidence("T","goal","lead",WatchdogScope.TRAJECTORY,WatchdogSignal.ATTENTION,digest("slow"),"slow")
        heard=swarm.watchdog_check("T",observer_role=WatchdogRouteRole.LEAD,observer_id="lead",now=15,evidence=ordinary)
        self.assertEqual(heard.decision_owner,"lead"); self.assertEqual(heard.alert_route[0],(WatchdogRouteRole.LEAD,"lead"))
        integrity=WatchdogEvidence("T","goal","lead",WatchdogScope.OUTCOME_INTEGRITY,WatchdogSignal.BLOCKER,digest("authority"),"authority",True)
        bypassed=swarm.watchdog_check("T",observer_role=WatchdogRouteRole.CTRL,observer_id="CTRL",now=30,evidence=integrity)
        self.assertEqual(bypassed.decision_owner,"CTRL"); self.assertNotIn("lead",{identity for _,identity in bypassed.alert_route})

    def test_external_outage_alert_cannot_mutate_owner_or_topology(self):
        swarm=self.tracked(); before=(swarm.tasks["T"].state,swarm.tasks["T"].owner,set(swarm.topology),dict(swarm.workers),dict(swarm.leases))
        receipt=swarm.watchdog_check("T",observer_role=WatchdogRouteRole.CTRL,observer_id="CTRL",now=25,evidence=self.evidence(WatchdogScope.TRAJECTORY,WatchdogSignal.BLOCKER,"provider outage"))
        after=(swarm.tasks["T"].state,swarm.tasks["T"].owner,set(swarm.topology),dict(swarm.workers),dict(swarm.leases))
        self.assertEqual(before,after); self.assertEqual(receipt.decision_owner,"CTRL"); self.assertEqual(swarm.scheduled_wakeups["T"],40)

    def test_versioned_amendment_remains_ctrl_only(self):
        swarm=self.tracked(bound=False)
        swarm.amend_objective(Role.CTRL,"T",version=2,authority="user",reason="new requirement",requirements_delta="add export",new_baseline="v2 brief",prior_miss_relevance="all remain relevant")
        with self.assertRaises(InvariantError): swarm.amend_objective(Role.SPECIALIST,"T",version=3,authority="manager",reason="override",requirements_delta="none",new_baseline="v3",prior_miss_relevance="none")

    def test_mother_is_a_specialist_profession_and_watchdog_is_not_a_role(self):
        from runtime.core import BUILT_IN_SPECIALISTS
        self.assertIn("MOTHER",BUILT_IN_SPECIALISTS); self.assertNotIn("WATCHDOG",BUILT_IN_SPECIALISTS)
        self.assertFalse(hasattr(Role,"MOTHER")); self.assertFalse(hasattr(Role,"WATCHDOG"))


if __name__ == "__main__": unittest.main()
