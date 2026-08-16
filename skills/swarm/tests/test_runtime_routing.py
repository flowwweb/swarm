from __future__ import annotations

import unittest

from skills.swarm.runtime import (
    ExecutionRoute,
    HandsOffEventKind,
    HostCapacityEvidence,
    HostTaskCapacity,
    InvariantError,
    RoutingEconomics,
    RoutingEvidenceBasis,
    UsageCapacitySnapshot,
    WatchdogScope,
    WatchdogSignal,
    WorkRoutingFacts,
    WorkSize,
    hands_off_interrupt,
    route_execution,
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
    def test_small_and_medium_bounded_work_use_normal_subagent_when_task_economics_do_not_win(self) -> None:
        for size in (WorkSize.SMALL, WorkSize.MEDIUM):
            with self.subTest(size=size):
                decision = route_execution(facts=facts(size), economics=economics(savings=20, overhead=60), capacity=AVAILABLE, accountable_owner="lead-a")
                self.assertEqual(decision.route, ExecutionRoute.NORMAL_SUBAGENT)
                self.assertFalse(decision.subagent_authoritative)

    def test_parallel_savings_choose_task_lane_with_ctrl_lead_doer_authority(self) -> None:
        decision = route_execution(facts=facts(independent_work=True), economics=economics(savings=100, overhead=60), capacity=AVAILABLE, accountable_owner="lead-a", lead_owner="lead-a")
        self.assertEqual(decision.route, ExecutionRoute.NORMAL_TASK)
        self.assertEqual(decision.authority_chain, ("CTRL", "LEAD", "DOER"))

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
        clear=usage_watchdog_evidence(task_id="task-a",goal_id="goal-a",watched_owner="lead-a",current=same,previous=prior)
        self.assertEqual(clear.scope,WatchdogScope.FLOW_INTEGRITY)
        self.assertEqual(clear.signal,WatchdogSignal.CLEAR)
        crossed=UsageCapacitySnapshot(5,HostTaskCapacity.USAGE_LIMITED,"lead-a","host:usage:5-limited",3)
        attention=usage_watchdog_evidence(task_id="task-a",goal_id="goal-a",watched_owner="lead-a",current=crossed,previous=same)
        self.assertEqual(attention.signal,WatchdogSignal.ATTENTION)
        blocked=usage_watchdog_evidence(task_id="task-a",goal_id="goal-a",watched_owner="lead-a",current=crossed,previous=same,viable_routes=0)
        self.assertEqual(blocked.signal,WatchdogSignal.BLOCKER)

    def test_hands_off_mode_ignores_routine_evidence_and_interrupts_true_boundaries(self) -> None:
        for kind in (HandsOffEventKind.ROUTINE_STATUS,HandsOffEventKind.MODEL_MESSAGE,HandsOffEventKind.TASK_MESSAGE):
            self.assertFalse(hands_off_interrupt(kind))
        self.assertFalse(hands_off_interrupt(HandsOffEventKind.USAGE_SIGNAL))
        self.assertTrue(hands_off_interrupt(HandsOffEventKind.USAGE_SIGNAL,hard_blocked=True))
        for kind in (HandsOffEventKind.USER_DIRECTION,HandsOffEventKind.MATERIAL_HANDOFF_REVIEW,HandsOffEventKind.STOPPING_CONDITION,HandsOffEventKind.HUMAN_AUTHORITY_BLOCKER):
            self.assertTrue(hands_off_interrupt(kind))


if __name__ == "__main__":
    unittest.main()
