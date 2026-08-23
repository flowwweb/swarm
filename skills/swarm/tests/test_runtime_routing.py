from __future__ import annotations

import unittest

from skills.swarm.runtime import (
    ExecutionRoute,
    HandsOffEventKind,
    HostCapacityEvidence,
    HostTaskCapacity,
    InvariantError,
    LeadBottleneckReason,
    LeadCapacityEvidence,
    Role,
    RoutingEconomics,
    RoutingEvidenceBasis,
    UsageCapacitySnapshot,
    WatchdogScope,
    WatchdogSignal,
    WatchdogBinding,
    WatchdogRouteRole,
    Swarm,
    StructuralAssignmentKind,
    StructuralAuthority,
    SubagentOutcome,
    SubordinateBoundaryFacts,
    Task,
    VisualOwnership,
    WorkRoutingFacts,
    WorkKind,
    WorkSize,
    decide_doer_recruitment,
    hands_off_interrupt,
    route_execution,
    select_structural_assignment,
    subagent_leaf_return,
    usage_watchdog_evidence,
)


def economics(*, savings: int = 0, overhead: int = 60) -> RoutingEconomics:
    return RoutingEconomics(
        savings, overhead, 0, 0, 0, 0, 0,
        RoutingEvidenceBasis.CONSERVATIVE_ASSUMPTION,
        assumptions=("no comparable host sample; conservative startup bound",),
    )


def facts(size: WorkSize = WorkSize.SMALL, **changes: object) -> WorkRoutingFacts:
    values = dict(size=size, bounded=True, low_risk=True, mutable_surface_count=1)
    values.update(changes)
    return WorkRoutingFacts(**values)


AVAILABLE = HostCapacityEvidence(HostTaskCapacity.AVAILABLE, True, "host:capacity:task-and-subagent")


class RuntimeRoutingTests(unittest.TestCase):
    def test_structural_authority_is_exact_and_lead_depth_is_evidence_driven(self) -> None:
        self.assertEqual(tuple(item.value for item in StructuralAuthority), ("CTRL", "LEAD", "DOER"))
        self.assertNotIn("REVIEW", StructuralAuthority.__members__)
        self.assertNotIn("WATCHDOG", StructuralAuthority.__members__)
        nested = select_structural_assignment(
            parent=StructuralAuthority.LEAD,
            boundary=SubordinateBoundaryFacts(heartbeat_obligation=True),
        )
        self.assertEqual((nested.kind, nested.child), (StructuralAssignmentKind.NESTED_LEAD, StructuralAuthority.LEAD))
        direct = select_structural_assignment(parent=StructuralAuthority.LEAD, boundary=SubordinateBoundaryFacts())
        self.assertEqual((direct.kind, direct.child), (StructuralAssignmentKind.LEAD_DIRECT, None))
        doer = select_structural_assignment(parent=StructuralAuthority.LEAD, boundary=SubordinateBoundaryFacts(), delegate_artifact=True)
        self.assertEqual((doer.kind, doer.child), (StructuralAssignmentKind.DOER, StructuralAuthority.DOER))

    def test_small_bounded_work_can_use_a_normal_subagent_when_task_economics_do_not_win(self) -> None:
        decision = route_execution(facts=facts(WorkSize.SMALL), economics=economics(savings=20, overhead=60), capacity=AVAILABLE, accountable_owner="lead-a")
        self.assertEqual(decision.route, ExecutionRoute.NORMAL_SUBAGENT)
        self.assertFalse(decision.subagent_authoritative)

    def test_medium_bounded_work_opens_a_visible_task_even_when_task_economics_do_not_win(self) -> None:
        decision = route_execution(facts=facts(WorkSize.MEDIUM), economics=economics(savings=20, overhead=60), capacity=AVAILABLE, accountable_owner="lead-a", lead_owner="lead-a")
        self.assertEqual(decision.route, ExecutionRoute.NORMAL_TASK)
        self.assertEqual(decision.authority_chain, ("CTRL", "LEAD", "DOER"))

    def test_parallel_savings_choose_task_lane_with_ctrl_lead_doer_authority(self) -> None:
        decision = route_execution(facts=facts(independent_work=True), economics=economics(savings=100, overhead=60), capacity=AVAILABLE, accountable_owner="lead-a", lead_owner="lead-a")
        self.assertEqual(decision.route, ExecutionRoute.NORMAL_TASK)
        self.assertEqual(decision.authority_chain, ("CTRL", "LEAD", "DOER"))

    def test_each_substantive_lane_fact_requires_a_visible_senior_task(self) -> None:
        for durable_fact in ("user_visible_delivery", "cross_lane_dependency", "material_heartbeat_obligation"):
            with self.subTest(durable_fact=durable_fact):
                decision = route_execution(
                    facts=facts(**{durable_fact: True}),
                    economics=economics(savings=20, overhead=60),
                    capacity=AVAILABLE,
                    accountable_owner="lead-a",
                    lead_owner="lead-a",
                )
                self.assertEqual(decision.route, ExecutionRoute.NORMAL_TASK)
                self.assertEqual(decision.authority_chain, ("CTRL", "LEAD", "DOER"))
                self.assertIn("visible senior task", decision.reason)

    def test_multi_surface_or_independent_review_requires_a_visible_lane(self) -> None:
        for routing_fact in ({"mutable_surface_count": 2}, {"independent_review": True}):
            with self.subTest(routing_fact=routing_fact):
                decision = route_execution(
                    facts=facts(**routing_fact),
                    economics=economics(savings=20, overhead=60),
                    capacity=AVAILABLE,
                    accountable_owner="lead-a",
                    lead_owner="lead-a",
                )
                self.assertEqual(decision.route, ExecutionRoute.NORMAL_TASK)
                self.assertEqual(decision.authority_chain, ("CTRL", "LEAD", "DOER"))

    def test_small_bounded_low_risk_one_surface_without_durable_facts_stays_non_authoritative(self) -> None:
        decision = route_execution(
            facts=facts(WorkSize.SMALL),
            economics=economics(savings=20, overhead=60),
            capacity=AVAILABLE,
            accountable_owner="lead-a",
        )
        self.assertEqual(decision.route, ExecutionRoute.NORMAL_SUBAGENT)
        self.assertEqual(decision.authority_chain, ("lead-a", "SUBAGENT"))
        self.assertFalse(decision.subagent_authoritative)

    def test_recursive_or_recruiting_work_never_routes_to_a_hidden_subagent(self) -> None:
        for flag in ("may_need_recruitment", "requires_recursive_delegation"):
            with self.subTest(flag=flag):
                decision = route_execution(
                    facts=facts(**{flag: True}),
                    economics=economics(savings=0, overhead=100),
                    capacity=AVAILABLE,
                    accountable_owner="lead-a",
                    lead_owner="lead-a",
                )
                self.assertEqual(decision.route, ExecutionRoute.NORMAL_TASK)
                blocked = route_execution(
                    facts=facts(**{flag: True}),
                    economics=economics(savings=0, overhead=100),
                    capacity=HostCapacityEvidence(HostTaskCapacity.REJECTED, True, "host:error:task rejected"),
                    accountable_owner="lead-a",
                    immutable_checkpoint="sha256:abc",
                    resumption_marker="resume:visible-owner",
                    affected_gates=("acceptance",),
                )
                self.assertEqual(blocked.route, ExecutionRoute.HARD_BLOCKED)
                self.assertIn("hidden subagent fallback is prohibited", blocked.reason)

    def test_subagent_is_a_leaf_and_returns_typed_visible_task_promotion(self) -> None:
        complete = subagent_leaf_return(accountable_parent="lead-a")
        self.assertEqual(complete.outcome, SubagentOutcome.COMPLETE)
        self.assertFalse(complete.may_delegate)
        self.assertFalse(complete.may_handoff)
        self.assertFalse(complete.may_own_heartbeat)
        self.assertFalse(complete.may_accept)
        promoted = subagent_leaf_return(
            accountable_parent="lead-a",
            needs_decomposition=True,
            remaining_deliverable="Implement the remaining API and tests.",
            custody_boundary=("src/api.py", "tests/test_api.py"),
            required_proof=("LOCAL_UNIT", "SOURCE_STATIC"),
            reason="The work now needs an independently resumable owner.",
        )
        self.assertEqual(promoted.outcome, SubagentOutcome.PROMOTE_TO_VISIBLE_TASK)
        self.assertEqual(promoted.accountable_parent, "lead-a")
        with self.assertRaisesRegex(InvariantError, "exact remaining deliverable"):
            subagent_leaf_return(accountable_parent="lead-a", may_need_recruitment=True)

    def test_doer_recruitment_uses_direct_wip_ready_queue_or_typed_critical_path_debt(self) -> None:
        saturated = decide_doer_recruitment(LeadCapacityEvidence(3, 7, 1, 0, 3, 1000, "capacity:lead-a"))
        self.assertTrue(saturated.recruit_doer)
        self.assertEqual(saturated.reason, LeadBottleneckReason.WIP_SATURATED_READY_QUEUE)
        delegated_is_excluded = decide_doer_recruitment(LeadCapacityEvidence(2, 99, 1, 0, 3, 1000, "capacity:lead-a"))
        self.assertFalse(delegated_is_excluded.recruit_doer)
        blocked_only = decide_doer_recruitment(LeadCapacityEvidence(3, 0, 0, 4, 3, 1000, "capacity:lead-a"))
        self.assertFalse(blocked_only.recruit_doer)
        critical = decide_doer_recruitment(LeadCapacityEvidence(1, 0, 1, 0, 3, 1000, "capacity:lead-a", forecast_slippage_ms=120, critical_path_receipt="forecast:lead-a:rev-2"))
        self.assertTrue(critical.recruit_doer)
        self.assertEqual(critical.reason, LeadBottleneckReason.RECEIPT_CRITICAL_PATH)

    def test_root_ctrl_small_general_work_can_use_a_subagent_but_medium_work_opens_a_task(self) -> None:
        decision = route_execution(
            facts=facts(),
            economics=economics(savings=20, overhead=60),
            capacity=AVAILABLE,
            accountable_owner="CTRL",
            lead_owner="lead-a",
        )
        self.assertEqual(decision.route, ExecutionRoute.NORMAL_SUBAGENT)
        medium = route_execution(
            facts=facts(WorkSize.MEDIUM),
            economics=economics(savings=20, overhead=60),
            capacity=AVAILABLE,
            accountable_owner="CTRL",
            lead_owner="lead-a",
        )
        self.assertEqual(medium.route, ExecutionRoute.NORMAL_TASK)
        self.assertEqual(medium.authority_chain, ("CTRL", "LEAD", "DOER"))
        blocked = HostCapacityEvidence(HostTaskCapacity.REJECTED, True, "host:error:task rejected")
        no_visible_task = route_execution(
            facts=facts(WorkSize.MEDIUM),
            economics=economics(savings=20, overhead=60),
            capacity=blocked,
            accountable_owner="CTRL",
        )
        self.assertEqual(no_visible_task.route, ExecutionRoute.HARD_BLOCKED)
        self.assertIn("no permitted task", no_visible_task.reason)

    def test_product_design_and_image_generation_require_a_designer_lane(self) -> None:
        for work_kind in (WorkKind.DESIGN, WorkKind.IMAGEGEN):
            with self.subTest(work_kind=work_kind), self.assertRaisesRegex(InvariantError, "Designer profession"):
                route_execution(facts=facts(work_kind=work_kind), economics=economics(), capacity=AVAILABLE, accountable_owner="lead-a", lead_owner="lead-a")
            decision = route_execution(
                facts=facts(work_kind=work_kind),
                economics=economics(),
                capacity=AVAILABLE,
                accountable_owner="lead-a",
                lead_owner="lead-a",
                assigned_profession="DESIGNER",
            )
            self.assertEqual(decision.route, ExecutionRoute.NORMAL_TASK)
            self.assertIn("durable", decision.reason)

    def test_expressive_image_generation_requires_artist_not_designer(self) -> None:
        expressive=facts(work_kind=WorkKind.IMAGEGEN,visual_ownership=VisualOwnership.EXPRESSIVE_ART)
        with self.assertRaisesRegex(InvariantError,"Artist profession"):
            route_execution(facts=expressive,economics=economics(),capacity=AVAILABLE,accountable_owner="lead-a",lead_owner="lead-a",assigned_profession="DESIGNER")
        decision=route_execution(facts=expressive,economics=economics(),capacity=AVAILABLE,accountable_owner="lead-a",lead_owner="lead-a",assigned_profession="ARTIST")
        self.assertEqual(decision.route,ExecutionRoute.NORMAL_TASK)

    def test_visual_work_never_falls_back_to_a_subagent_when_task_creation_is_unavailable(self) -> None:
        blocked = HostCapacityEvidence(HostTaskCapacity.REJECTED, True, "host:error:task rejected")
        decision = route_execution(
            facts=facts(work_kind=WorkKind.IMAGEGEN),
            economics=economics(),
            capacity=blocked,
            accountable_owner="CTRL",
            assigned_profession="DESIGNER",
        )
        self.assertEqual(decision.route, ExecutionRoute.HARD_BLOCKED)
        self.assertIn("visual work", decision.reason)

    def test_large_or_interruption_prone_single_surface_work_requires_task_without_speedup(self) -> None:
        cases=(facts(WorkSize.LARGE),facts(WorkSize.MEDIUM,interruption_safe_resumption=True))
        for case in cases:
            with self.subTest(case=case):
                decision=route_execution(facts=case,economics=economics(savings=0,overhead=100),capacity=AVAILABLE,accountable_owner="lead-a",lead_owner="lead-a")
                self.assertEqual(decision.route,ExecutionRoute.NORMAL_TASK)
                self.assertIn("durable",decision.reason)

    def test_delegated_task_cannot_bypass_lead(self) -> None:
        with self.assertRaisesRegex(InvariantError,"CTRL -> LEAD -> DOER"):
            route_execution(facts=facts(WorkSize.LARGE),economics=economics(),capacity=AVAILABLE,accountable_owner="doer-a",lead_owner="CTRL")

    def test_capacity_fallback_is_non_authoritative_and_leaves_gates_unverified(self) -> None:
        limited=HostCapacityEvidence(HostTaskCapacity.USAGE_LIMITED,True,"host:error:task usage limit reached")
        decision=route_execution(
            facts=facts(WorkSize.LARGE),economics=economics(),capacity=limited,accountable_owner="lead-a",
            immutable_checkpoint="sha256:abc",resumption_marker="resume:task-lane@safe-boundary",affected_gates=("independent-review","acceptance"),
        )
        self.assertEqual(decision.route,ExecutionRoute.DEGRADED_SUBAGENT)
        self.assertFalse(decision.subagent_authoritative)
        self.assertEqual(decision.unverified_gates,("independent-review","acceptance"))
        self.assertTrue(decision.immutable_checkpoint)
        self.assertTrue(decision.resumption_marker)

    def test_no_permitted_structure_is_hard_blocked(self) -> None:
        blocked=HostCapacityEvidence(HostTaskCapacity.REJECTED,False,"host:error:task rejected and subagents unavailable")
        decision=route_execution(facts=facts(WorkSize.LARGE),economics=economics(),capacity=blocked,accountable_owner="lead-a")
        self.assertEqual(decision.route,ExecutionRoute.HARD_BLOCKED)

    def test_changed_route_is_deferred_until_safe_boundary(self) -> None:
        current=route_execution(facts=facts(),economics=economics(),capacity=AVAILABLE,accountable_owner="lead-a")
        deferred=route_execution(facts=facts(WorkSize.LARGE),economics=economics(),capacity=AVAILABLE,accountable_owner="lead-a",lead_owner="lead-a",current=current,safe_boundary=False)
        self.assertEqual(deferred.route,ExecutionRoute.NORMAL_SUBAGENT)
        self.assertEqual(deferred.pending_route,ExecutionRoute.NORMAL_TASK)
        applied=route_execution(facts=facts(WorkSize.LARGE),economics=economics(),capacity=AVAILABLE,accountable_owner="lead-a",lead_owner="lead-a",current=current,safe_boundary=True)
        self.assertEqual(applied.route,ExecutionRoute.NORMAL_TASK)

    def test_usage_watchdog_is_silent_until_material_change_and_blocks_only_without_route(self) -> None:
        prior=UsageCapacitySnapshot(10,HostTaskCapacity.AVAILABLE,"lead-a","host:usage:10",1)
        same=UsageCapacitySnapshot(9,HostTaskCapacity.AVAILABLE,"lead-a","host:usage:9",2)
        clear=usage_watchdog_evidence(task_id="task-a",goal_id="goal-a",watched_role=Role.LEAD,watched_owner="lead-a",current=same,previous=prior)
        self.assertEqual(clear.scope,WatchdogScope.FLOW_INTEGRITY)
        self.assertEqual(clear.signal,WatchdogSignal.CLEAR)
        crossed=UsageCapacitySnapshot(5,HostTaskCapacity.USAGE_LIMITED,"lead-a","host:usage:5-limited",3)
        attention=usage_watchdog_evidence(task_id="task-a",goal_id="goal-a",watched_role=Role.LEAD,watched_owner="lead-a",current=crossed,previous=same)
        self.assertEqual(attention.signal,WatchdogSignal.ATTENTION)
        blocked=usage_watchdog_evidence(task_id="task-a",goal_id="goal-a",watched_role=Role.LEAD,watched_owner="lead-a",current=crossed,previous=same,viable_routes=0)
        self.assertEqual(blocked.signal,WatchdogSignal.BLOCKER)

    def test_usage_watchdog_rejects_specialist_and_architect_bindings(self) -> None:
        snapshot=UsageCapacitySnapshot(10,HostTaskCapacity.AVAILABLE,"lead-a","host:usage:10",1)
        for role in (Role.SPECIALIST,Role.ARCHITECT):
            with self.subTest(role=role), self.assertRaisesRegex(InvariantError,"only to an accountable LEAD"):
                usage_watchdog_evidence(task_id="task-a",goal_id="goal-a",watched_role=role,watched_owner="specialist-a",current=snapshot)

    def test_usage_watchdog_cannot_enter_specialist_or_architect_bound_goals(self) -> None:
        snapshot=UsageCapacitySnapshot(5,HostTaskCapacity.USAGE_LIMITED,"spec","host:usage:5-limited",1)
        for role,owner,profession,route_role in (
            (Role.SPECIALIST,"spec","RESEARCHER",WatchdogRouteRole.SPECIALIST),
            (Role.ARCHITECT,"architect","ARCHITECT",WatchdogRouteRole.ARCHITECT),
        ):
            with self.subTest(role=role):
                swarm=Swarm(); task=Task("task-a","worker","CTRL",1,{},specialist_professions={owner:profession})
                swarm.tasks[task.id]=task
                binding=WatchdogBinding(role,owner,((route_role,owner),(WatchdogRouteRole.CTRL,"CTRL")),((WatchdogRouteRole.CTRL,"CTRL"),(WatchdogRouteRole.HUMAN,"HUMAN")))
                swarm.propose_milestone(role,task.id,goal_id="goal-a",milestone="capacity",proof_kind="dependency",horizon_minutes=15,now=0,watchdog=binding)
                evidence=usage_watchdog_evidence(task_id=task.id,goal_id="goal-a",watched_role=Role.LEAD,watched_owner=owner,current=snapshot)
                with self.assertRaisesRegex(InvariantError,"actual WatchdogBinding role to be LEAD"):
                    swarm.watchdog_check(task.id,observer_role=route_role,observer_id=owner,now=15,evidence=evidence)

    def test_hands_off_mode_ignores_routine_evidence_and_interrupts_true_boundaries(self) -> None:
        for kind in (HandsOffEventKind.ROUTINE_STATUS,HandsOffEventKind.MODEL_MESSAGE,HandsOffEventKind.TASK_MESSAGE):
            self.assertFalse(hands_off_interrupt(kind))
        self.assertFalse(hands_off_interrupt(HandsOffEventKind.USAGE_SIGNAL))
        self.assertTrue(hands_off_interrupt(HandsOffEventKind.USAGE_SIGNAL,hard_blocked=True))
        for kind in (HandsOffEventKind.USER_DIRECTION,HandsOffEventKind.MATERIAL_HANDOFF_REVIEW,HandsOffEventKind.STOPPING_CONDITION,HandsOffEventKind.HUMAN_AUTHORITY_BLOCKER):
            self.assertTrue(hands_off_interrupt(kind))


if __name__ == "__main__":
    unittest.main()
