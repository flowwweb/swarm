import unittest
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import AcceptanceContract, ArtifactIdentity, CtrlMode, HorizonAction, InvariantError, LaneKind, Role, SubagentException, Swarm, Task, ctrl_mode


class OperatingModelTests(unittest.TestCase):
    def test_direct_mode_is_the_only_ctrl_mutation_exception(self):
        root=Path(__file__).resolve().parents[1]
        skill="\n".join((root / name).read_text(encoding="utf-8") for name in ("SKILL.md", "references/hierarchy.md"))
        hierarchy=(Path(__file__).resolve().parents[1] / "references" / "hierarchy.md").read_text(encoding="utf-8")
        self.assertRegex(skill,r"(?is)CTRL_DIRECT.*only one low-risk atomic outcome.*otherwise use.*CTRL_DELEGATED")
        self.assertRegex(skill,r"(?is)failed capacity.*continue direct bounded owner work.*never grants external")
        self.assertIn("Every `CTRL_DELEGATED` and non-CTRL SWARM task delegates",hierarchy)

    def test_ctrl_direct_is_exact_and_every_failed_predicate_delegates(self):
        base=dict(outcomes=1,mutable_surfaces=1,cross_lane_dependency=False,risk=1,measurable_minutes=20,direct_horizon_minutes=20)
        self.assertEqual(ctrl_mode(**base),CtrlMode.DIRECT)
        for change in ({"outcomes":2},{"mutable_surfaces":2},{"cross_lane_dependency":True},{"risk":2},{"measurable_minutes":21}):
            self.assertEqual(ctrl_mode(**{**base,**change}),CtrlMode.DELEGATED)
        swarm=Swarm(); direct=Task("direct","CTRL","CTRL",1,{},risk=1,subagent_exception=SubagentException.WHOLE_TASK_COST,subagent_exception_reason="atomic work is shorter than delegation",lane_kind=LaneKind.CODE,acceptance_contract=AcceptanceContract(ArtifactIdentity("direct","v1","acceptance"),("contract",)))
        swarm.start_ctrl_direct(Role.CTRL,direct,outcomes=1,mutable_surfaces=1,cross_lane_dependency=False,measurable_minutes=10)
        swarm.add_artifact(Role.CTRL,"direct",ArtifactIdentity("direct","v1","work"))
        with self.assertRaisesRegex(InvariantError,"hire a LEAD"): swarm.start_ctrl_direct(Role.CTRL,Task("large","CTRL","CTRL",1,{},risk=2,subagent_exception=SubagentException.WHOLE_TASK_COST,subagent_exception_reason="candidate"),outcomes=1,mutable_surfaces=1,cross_lane_dependency=False,measurable_minutes=10)

    def test_subagent_capacity_never_materializes_visible_topology(self):
        swarm=Swarm()
        swarm.start_atomic(Role.CTRL,Task("internal","helper","CTRL",1,{},subagent_receipt="host:thread:internal"))
        self.assertIn("helper",swarm.workers)
        self.assertNotIn("helper",swarm.topology)
        self.assertEqual(swarm.topology,set())

    def tracked(self):
        swarm=Swarm(); swarm.tasks["T"]=Task("T","worker","CTRL",1,{})
        swarm.propose_milestone(Role.DOER,"T",goal_id="goal",milestone="test passes",proof_kind="test",horizon_minutes=15,now=10)
        return swarm

    def test_activity_only_cannot_be_a_milestone_contract(self):
        swarm=Swarm(); swarm.tasks["T"]=Task("T","worker","CTRL",1,{})
        with self.assertRaisesRegex(InvariantError,"measurable proof kind"):
            swarm.propose_milestone(Role.DOER,"T",goal_id="goal",milestone="still working",proof_kind="activity",horizon_minutes=15,now=0)

    def test_one_event_no_early_poll_and_raw_evidence_required(self):
        swarm=self.tracked(); self.assertEqual(swarm.scheduled_wakeups,{"T":25})
        self.assertEqual(swarm.review_horizon(Role.CTRL,"T",now=24),HorizonAction.OBSERVE)
        with self.assertRaisesRegex(InvariantError,"raw evidence"): swarm.review_horizon(Role.CTRL,"T",now=25)
        self.assertEqual(swarm.scheduled_wakeups["T"],25)
        self.assertEqual(swarm.review_horizon(Role.CTRL,"T",now=25,raw_evidence="diff",reorientation="inspect failing test"),HorizonAction.REORIENT)

    def test_latency_reschedules_once_and_success_schedules_or_closes(self):
        swarm=self.tracked()
        self.assertEqual(swarm.review_horizon(Role.CTRL,"T",now=25,latency_audit="setup completed at due time"),HorizonAction.OBSERVE)
        self.assertEqual(swarm.scheduled_wakeups["T"],40)
        self.assertEqual(swarm.review_horizon(Role.CTRL,"T",now=40,raw_evidence="tests pass",milestone_met=True,next_milestone="render",next_horizon_minutes=10),HorizonAction.OBSERVE)
        self.assertEqual(swarm.scheduled_wakeups["T"],50)
        self.assertEqual(swarm.review_horizon(Role.CTRL,"T",now=50,raw_evidence="render accepted",milestone_met=True,close_goal=True),HorizonAction.OBSERVE)
        self.assertFalse(swarm.tasks["T"].active_goal)

    def test_ctrl_owned_miss_ladder_and_lost_event_recovery(self):
        swarm=self.tracked()
        with self.assertRaises(InvariantError): swarm.review_horizon(Role.MOTHER,"T",now=25,raw_evidence="fail")
        self.assertEqual(swarm.review_horizon(Role.CTRL,"T",now=25,raw_evidence="test failure",reorientation="fix fixture"),HorizonAction.REORIENT)
        self.assertEqual(swarm.scheduled_wakeups["T"],40)
        self.assertEqual(swarm.review_horizon(Role.CTRL,"T",now=40,raw_evidence="same failure",independent_review="review:R1"),HorizonAction.REVIEW)
        self.assertEqual(swarm.scheduled_wakeups["T"],55)
        self.assertEqual(swarm.review_horizon(Role.CTRL,"T",now=55,raw_evidence="same failure"),HorizonAction.SUPERVISOR)
        self.assertEqual(swarm.scheduled_wakeups["T"],70)
        del swarm.scheduled_wakeups["T"]
        self.assertEqual(swarm.recover_lost_wakeup(Role.CTRL,"T",now=60),70)
        self.assertEqual(swarm.recover_lost_wakeup(Role.CTRL,"T",now=61),70)

    def test_ctrl_heartbeat_recovers_its_own_lost_wakeup(self):
        swarm=Swarm(); swarm.tasks["CTRL"]=Task("CTRL","controller","CTRL",1,{})
        swarm.propose_milestone(Role.CTRL,"CTRL",goal_id="control",milestone="accepted result",proof_kind="integration",horizon_minutes=15,now=10)
        del swarm.scheduled_wakeups["CTRL"]
        self.assertEqual(swarm.heartbeat(Role.CTRL,"CTRL",meaningful_progress=False,recent_ctrl_feed=()),"CTRL:watchdog-recovered:25")
        with self.assertRaises(InvariantError): swarm.heartbeat(Role.MOTHER,"CTRL",meaningful_progress=False,recent_ctrl_feed=())

    def test_versioned_amendment_and_successor_preserve_history(self):
        swarm=self.tracked()
        swarm.amend_objective(Role.CTRL,"T",version=2,authority="user",reason="new requirement",requirements_delta="add export",new_baseline="v2 brief",prior_miss_relevance="all remain relevant")
        with self.assertRaises(InvariantError): swarm.amend_objective(Role.CTRL,"T",version=2,authority="user",reason="reset",requirements_delta="none",new_baseline="v2",prior_miss_relevance="erase")
        swarm.tasks["N"]=Task("N","worker2","CTRL",1,{},goal_id="new-goal")
        swarm.link_successor(Role.CTRL,"T","N",evidence="distinct project brief")
        self.assertEqual(swarm.tasks["N"].milestone_history[-1][1],"SUCCESSOR")

    def test_architect_event_updates_only_when_map_is_invalidated(self):
        swarm=self.tracked()
        swarm.architecture_event(Role.ARCHITECT,"T",goal_id="architecture",accepted_change="artifact v1",invalidates_map=False,receipt="checked contracts")
        self.assertEqual(swarm.tasks["T"].architecture_receipts[-1][1],"NO_IMPACT")
        swarm.architecture_event(Role.ARCHITECT,"T",goal_id="architecture",accepted_change="contract v2",invalidates_map=True,receipt="diff",decision_or_blocker="gate integration until adapter lands")
        self.assertEqual(swarm.tasks["T"].architecture_map_version,1)
        with self.assertRaises(InvariantError): swarm.architecture_event(Role.LEAD,"T",goal_id="architecture",accepted_change="x",invalidates_map=False,receipt="x")

    def test_free_role_specialist_keeps_an_independent_versioned_ledger(self):
        swarm=self.tracked()
        swarm.specialist_event(Role.SPECIALIST,"T",specialist_id="auth-architecture",profession="ARCHITECT",goal_id="auth",accepted_change="auth v2",invalidates_map=True,receipt="contract diff",decision_or_blocker="gate rollout")
        swarm.specialist_event(Role.SPECIALIST,"T",specialist_id="data-architecture",profession="ARCHITECT",goal_id="data",accepted_change="schema v2",invalidates_map=False,receipt="schema contract")
        self.assertEqual(swarm.tasks["T"].specialist_professions,{"auth-architecture":"ARCHITECT","data-architecture":"ARCHITECT"})
        self.assertEqual(swarm.tasks["T"].specialist_map_versions,{"auth-architecture":1,"data-architecture":0})
        swarm.specialist_event(Role.SPECIALIST,"T",specialist_id="novel",profession="ETHNOGRAPHER",goal_id="research",accepted_change="field note",invalidates_map=False,receipt="source")

    def test_builtin_professions_include_developer_without_limiting_free_roles(self):
        from runtime.core import BUILT_IN_SPECIALISTS
        self.assertEqual(BUILT_IN_SPECIALISTS,{"ARCHITECT","ENGINEER","DEVELOPER","DESIGNER","RESEARCHER","ANALYST","STRATEGIST"})


if __name__ == "__main__": unittest.main()
