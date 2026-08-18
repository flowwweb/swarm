from __future__ import annotations

import unittest
from pathlib import Path

from skills.swarm.runtime import (
    CapacityException,
    HostCapacity,
    LaneResourceLock,
    LaneSpec,
    LaneType,
    ParallelismReason,
    ResourceLockType,
    WorkLedgerStage,
    new_work_ledger,
    plan_parallel_lanes,
)


def lane(identity: str, *, surface: str, ledger: str = "") -> LaneSpec:
    return LaneSpec(
        identity,
        LaneType.CODE,
        f"objective-{identity}",
        f"owner-{identity}",
        (surface,),
        (f"proof-{identity}",),
        ledger_id=ledger or f"ledger-{identity}",
    )


class ParallelismTests(unittest.TestCase):
    def test_policy_is_generic_and_ledger_is_not_a_second_authority(self) -> None:
        root = Path(__file__).resolve().parents[1]
        doctrine = (root / "references" / "hierarchy.md").read_text(encoding="utf-8")
        self.assertIn("lane type is descriptive and does not create a category-specific queue", doctrine)
        self.assertIn("WORK_LEDGER", doctrine)
        self.assertIn("REQUEST -> ASSIGNED", doctrine)
        self.assertIn("typed pending/blocked record", doctrine)
        self.assertNotIn("design slot", doctrine.casefold())

    def test_independent_lanes_are_in_one_parallel_group(self) -> None:
        plan = plan_parallel_lanes(
            (lane("a", surface="surface-a"), lane("b", surface="surface-b")),
            (HostCapacity("default", 2, 0, "host observed two units", "one unit releases"),),
        )
        self.assertEqual(plan.parallel_groups, (("a", "b"),))
        self.assertEqual(plan.decision_for("a").reason, ParallelismReason.INDEPENDENT)
        self.assertEqual(plan.decision_for("b").reason, ParallelismReason.INDEPENDENT)

    def test_shared_surface_is_serialized_without_serializing_other_lane_types(self) -> None:
        same = plan_parallel_lanes(
            (lane("a", surface="shared"), lane("b", surface="shared")),
            (HostCapacity("default", 2, 0, "host observed two units", "one unit releases"),),
        )
        self.assertEqual(same.parallel_groups, (("a",), ("b",)))
        self.assertEqual(same.decision_for("b").reason, ParallelismReason.SHARED_SURFACE)
        independent = plan_parallel_lanes(
            (
                lane("code", surface="repo-code"),
                LaneSpec("research", LaneType.RESEARCH, "research", "researcher", ("notes",), ("sources",)),
            ),
            (HostCapacity("default", 2, 0, "host observed two units", "one unit releases"),),
        )
        self.assertEqual(independent.parallel_groups, (("code", "research"),))

    def test_active_shared_surface_and_explicit_proof_dependency_do_not_run_now(self) -> None:
        active = lane("active", surface="shared")
        waiting = lane("waiting", surface="shared")
        active_plan = plan_parallel_lanes(
            (waiting,),
            (HostCapacity("default", 3, 1, "one lane is active", "active lane closes"),),
            active=(active,),
        )
        self.assertEqual(active_plan.parallel_groups, ())
        self.assertEqual(active_plan.decision_for("waiting").parallel_group, None)
        self.assertEqual(active_plan.decision_for("waiting").blocking_lane_ids, ("active",))

        dependency = LaneSpec(
            "dependent",
            LaneType.QA,
            "verify output",
            "qa-owner",
            ("qa-surface",),
            ("qa-proof",),
            proof_dependencies=("producer",),
        )
        producer = lane("producer", surface="producer-surface")
        dependency_plan = plan_parallel_lanes(
            (producer, dependency),
            (HostCapacity("default", 2, 0, "two units observed", "one unit releases"),),
        )
        self.assertEqual(dependency_plan.parallel_groups, (("producer",), ("dependent",)))
        self.assertEqual(dependency_plan.decision_for("dependent").reason, ParallelismReason.PROOF_DEPENDENCY)

    def test_explicit_provider_lock_serializes_only_matching_lock(self) -> None:
        locked = LaneResourceLock(ResourceLockType.PROVIDER, "provider-a")
        plan = plan_parallel_lanes(
            (
                lane("a", surface="surface-a"),
                LaneSpec("b", LaneType.PAYMENT, "payment", "owner-b", ("surface-b",), ("proof-b",), resource_locks=(locked,)),
                LaneSpec("c", LaneType.PAYMENT, "payment-2", "owner-c", ("surface-c",), ("proof-c",), resource_locks=(locked,)),
            ),
            (HostCapacity("default", 3, 0, "host observed three units", "one unit releases"),),
        )
        self.assertEqual(plan.parallel_groups, (("a", "b"), ("c",)))
        self.assertEqual(plan.decision_for("c").reason, ParallelismReason.EXCLUSIVE_LOCK)

    def test_capacity_full_is_typed_and_records_host_release_condition(self) -> None:
        blocked = lane("blocked", surface="surface-b", ledger="work-42")
        plan = plan_parallel_lanes(
            (blocked,),
            (HostCapacity("default", 1, 1, "host reports one active lane", "active lane reaches terminal receipt"),),
        )
        self.assertEqual(plan.parallel_groups, ())
        self.assertEqual(len(plan.pending), 1)
        pending = plan.pending[0]
        self.assertEqual(pending.exception, CapacityException.CAPACITY_FULL)
        self.assertEqual(pending.ledger_id, "work-42")
        self.assertIn("active lane", pending.host_observation)
        self.assertIn("terminal", pending.next_release_condition)
        self.assertEqual(plan.decision_for("blocked").pending, pending)

    def test_one_work_ledger_identity_carries_request_to_progress_block_and_close(self) -> None:
        record = new_work_ledger("work-42", "finish the bounded outcome", "lead-42")
        assigned = record.transition(WorkLedgerStage.ASSIGNED)
        progress = assigned.transition(WorkLedgerStage.PROGRESS)
        blocked = progress.transition(
            WorkLedgerStage.BLOCKED,
            host_observation="host capacity is full",
            next_release_condition="a lane releases its capacity receipt",
        )
        resumed = blocked.transition(WorkLedgerStage.PROGRESS)
        accepted = resumed.transition(WorkLedgerStage.ACCEPTED, proof_receipt="proof-42")
        closed = accepted.transition(WorkLedgerStage.CLOSED, proof_receipt="proof-42")
        self.assertEqual({item.id for item in (record, assigned, progress, blocked, resumed, accepted, closed)}, {"work-42"})
        self.assertEqual(closed.history, (
            WorkLedgerStage.REQUEST,
            WorkLedgerStage.ASSIGNED,
            WorkLedgerStage.PROGRESS,
            WorkLedgerStage.BLOCKED,
            WorkLedgerStage.PROGRESS,
            WorkLedgerStage.ACCEPTED,
            WorkLedgerStage.CLOSED,
        ))
        with self.assertRaises(ValueError):
            record.transition(WorkLedgerStage.ACCEPTED, proof_receipt="")


if __name__ == "__main__":
    unittest.main()
