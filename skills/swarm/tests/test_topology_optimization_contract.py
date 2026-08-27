from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import unittest

from skills.swarm.runtime.core import (
    ArtifactIdentity,
    AttemptCostReceipt,
    ControlPathFailure,
    ControlPathFailureKind,
    ControlPathRecoveryAction,
    ControlPathState,
    ControlPathTruth,
    CustodyMutation,
    DelegationContract,
    HostCustodyReceipt,
    InvariantError,
    MaterialStateKind,
    MaterialStateReceipt,
    ProofClass,
    ReassessmentChoice,
    ReassessmentRoute,
    RecoveryCause,
    Role,
    RetryOutcome,
    RetryTopologyAction,
    RetryTopologyLedger,
    Swarm,
    Task,
    TaskState,
    Worker,
    WorkerState,
    WatchdogSignal,
)


def digest(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


class TopologyOptimizationContractTests(unittest.TestCase):
    def observe(self, swarm: Swarm, **overrides: object):
        facts = {
            "action": "retry-read",
            "target": "thread-42",
            "outcome": RetryOutcome.TIMEOUT,
            "blocker_code": "host-timeout",
        }
        facts.update(overrides)
        return swarm.retry_topology_decision(**facts)

    def receipt(self, kind: MaterialStateKind, revision: int) -> MaterialStateReceipt:
        return MaterialStateReceipt(kind, "owned-surface", digest(f"revision-{revision}"), revision)

    def control_receipt(self, kind: MaterialStateKind, revision: int, failure: ControlPathFailure, **bindings: str) -> MaterialStateReceipt:
        expected = {
            "failure_identity": failure.signature_digest,
            "task_id": failure.task_id,
            "dispatch_receipt_id": failure.dispatch_receipt_id,
            "candidate": failure.artifact.content_address(),
        }
        expected.update(bindings)
        return MaterialStateReceipt(kind, "owned-surface", digest(f"control-revision-{revision}"), revision, **expected)

    def delegated_swarm(self) -> tuple[Swarm, ArtifactIdentity]:
        artifact = ArtifactIdentity("control-candidate", "candidate-1", "source")
        contract = DelegationContract(
            "task-a",
            "Return one exact control-path receipt.",
            "owner-a",
            ("skills/swarm/runtime",),
            artifact,
            ("skills/swarm/runtime/core.py",),
            (ProofClass.SOURCE,),
            100,
        )
        task = Task(
            "task-a",
            "owner-a",
            "lead-a",
            1,
            {},
            reviewer="review-a",
            delegation_contract=contract,
            subagent_receipt="host:thread:task-a",
        )
        ready = Task("task-b", "owner-b", "lead-b", 1, {})
        return Swarm(tasks={task.id: task, ready.id: ready}), artifact

    def control_failure(self, artifact: ArtifactIdentity, **overrides: object) -> ControlPathFailure:
        facts = {
            "task_id": "task-a",
            "owner_id": "owner-a",
            "dispatch_receipt_id": "host:thread:task-a",
            "completion_receipt_id": "host:turn:empty-1",
            "kind": ControlPathFailureKind.EMPTY_COMPLETION,
            "worktree": "work/swarm-source",
            "artifact": artifact,
            "artifact_paths": ("skills/swarm/runtime/core.py",),
            "failed_route": "read-thread",
            "observed_at_ms": 10,
        }
        facts.update(overrides)
        return ControlPathFailure(**facts)

    def test_second_equivalent_attempt_stops_tactic_and_cosmetic_narration_cannot_reset(self) -> None:
        swarm = Swarm()
        first = self.observe(swarm, narration="Trying the read again")
        second = self.observe(swarm, narration="A fresher sounding retry description")
        self.assertEqual(first.action, RetryTopologyAction.CONTINUE)
        self.assertEqual(second.action, RetryTopologyAction.REASSESS_ROOT_CAUSE)
        self.assertEqual(second.equivalent_attempts, 2)
        self.assertEqual(first.signature_digest, second.signature_digest)
        self.assertFalse(second.material_progress)
        self.assertEqual(second.reassessment.reasoning_kind, "higher_root_cause_topology")
        self.assertFalse(second.reassessment.model_call_required)
        self.assertFalse(second.reassessment.may_change_model_provider_tier)

    def test_material_artifact_dependency_proof_or_state_receipt_resets_the_tactic(self) -> None:
        for kind in MaterialStateKind:
            with self.subTest(kind=kind):
                swarm = Swarm()
                self.observe(swarm, material_receipt=self.receipt(kind, 1))
                self.observe(swarm)
                reset = self.observe(swarm, material_receipt=self.receipt(kind, 2))
                self.assertEqual(reset.action, RetryTopologyAction.CONTINUE)
                self.assertEqual(reset.equivalent_attempts, 1)
                self.assertTrue(reset.material_progress)
                self.assertEqual(swarm.retry_topology_ledger.last_good_checkpoint, self.receipt(kind, 2))

    def test_failure_transport_outcomes_never_infer_progress(self) -> None:
        for outcome in (RetryOutcome.EMPTY, RetryOutcome.TIMEOUT, RetryOutcome.HTTP_400, RetryOutcome.MISSING_THREAD):
            with self.subTest(outcome=outcome):
                swarm = Swarm()
                decision = self.observe(swarm, outcome=outcome, blocker_code=outcome.value.lower())
                self.assertFalse(decision.material_progress)
                self.assertIsNone(swarm.retry_topology_ledger.last_good_checkpoint)

    def test_user_pause_or_direct_control_suppresses_intervention(self) -> None:
        for flag in ("user_paused", "user_controlled"):
            with self.subTest(flag=flag):
                swarm = Swarm()
                decision = self.observe(swarm, **{flag: True})
                self.assertEqual(decision.action, RetryTopologyAction.USER_CONTROLLED)
                self.assertEqual(decision.equivalent_attempts, 0)
                self.assertEqual(self.observe(swarm).action, RetryTopologyAction.CONTINUE)

    def test_known_cost_receipts_are_retained_and_missing_tokens_stay_unknown(self) -> None:
        swarm = Swarm()
        known = AttemptCostReceipt("cost-known", token_count=321, latency_ms=900)
        unknown = AttemptCostReceipt("cost-unknown", token_count=None, latency_ms=1200)
        first = self.observe(swarm, cost_receipt=known)
        second = self.observe(swarm, action="inspect-index", cost_receipt=unknown)
        no_receipt = self.observe(swarm, action="alternate-read")
        self.assertEqual((first.token_count, first.latency_ms), (321, 900))
        self.assertEqual((second.token_count, second.latency_ms), (None, 1200))
        self.assertEqual((no_receipt.token_count, no_receipt.latency_ms), (None, None))
        self.assertEqual(swarm.retry_topology_ledger.cost_receipts[known.receipt_id], known)
        self.assertEqual(swarm.retry_topology_ledger.cost_receipts[unknown.receipt_id], unknown)
        with self.assertRaisesRegex(InvariantError, "conflicts"):
            self.observe(swarm, cost_receipt=AttemptCostReceipt("cost-known", token_count=322, latency_ms=900))

    def test_exactly_one_typed_reassessment_must_choose_a_material_change(self) -> None:
        swarm = Swarm()
        self.observe(swarm)
        pending = self.observe(swarm)
        same = ReassessmentChoice(ReassessmentRoute.DIFFERENT_BOUNDED_ROUTE, "retry-read", "thread-42")
        with self.assertRaisesRegex(InvariantError, "materially different"):
            swarm.choose_retry_reassessment(same)
        chosen = ReassessmentChoice(ReassessmentRoute.DIFFERENT_BOUNDED_ROUTE, "read-inventory", "thread-42")
        self.assertEqual(swarm.choose_retry_reassessment(chosen), chosen)
        with self.assertRaisesRegex(InvariantError, "already consumed"):
            swarm.choose_retry_reassessment(chosen)
        after = self.observe(swarm, action="read-inventory")
        self.assertEqual(after.action, RetryTopologyAction.CONTINUE)
        self.assertIsNotNone(pending.reassessment)

    def test_repeated_reassessment_is_rejected_until_new_material_state(self) -> None:
        swarm = Swarm()
        checkpoint = self.receipt(MaterialStateKind.STATE, 1)
        self.observe(swarm, material_receipt=checkpoint)
        self.observe(swarm)
        swarm.choose_retry_reassessment(ReassessmentChoice(ReassessmentRoute.CONSOLIDATE, "consolidate-read", "thread-42", checkpoint))
        stopped = self.observe(swarm)
        self.assertEqual(stopped.action, RetryTopologyAction.STOP_REPEATED_TACTIC)
        reset = self.observe(swarm, material_receipt=self.receipt(MaterialStateKind.PROOF, 3))
        self.assertEqual(reset.action, RetryTopologyAction.CONTINUE)
        self.assertTrue(reset.material_progress)

    def test_interleaved_equivalent_tactics_cannot_evade_the_threshold(self) -> None:
        swarm = Swarm()
        a1 = self.observe(swarm, action="route-a")
        b1 = self.observe(swarm, action="route-b")
        a2 = self.observe(swarm, action="route-a")
        b2 = self.observe(swarm, action="route-b")
        self.assertEqual((a1.action, b1.action), (RetryTopologyAction.CONTINUE, RetryTopologyAction.CONTINUE))
        self.assertEqual(a2.action, RetryTopologyAction.REASSESS_ROOT_CAUSE)
        self.assertEqual(b2.action, RetryTopologyAction.STOP_REPEATED_TACTIC)

    def test_recover_and_correction_paths_automatically_use_the_single_ledger(self) -> None:
        recovery = Swarm(tasks={"task-a": Task("task-a", "lead", "ctrl", 1, {})})
        recovery.recover(Role.CTRL, "task-a", "same transport")
        with self.assertRaisesRegex(InvariantError, "REASSESS_ROOT_CAUSE"):
            recovery.recover(Role.CTRL, "task-a", "same transport")
        self.assertEqual(recovery.events.count(("RECOVERY", "task-a")), 1)
        self.assertIn(("REASSESS_ROOT_CAUSE", "task-a"), recovery.events)

        correction = Swarm()
        facts = {"material": True, "expected_future_cost": 9, "correction_cost": 1}
        self.assertEqual(correction.correction("same-incident", **facts).value, "FIX_FORWARD")
        self.assertEqual(correction.correction("same-incident", **facts).value, "ESCALATE")
        self.assertEqual(correction.telemetry_events[-1]["kind"], "retry_topology_reassessment")
        with self.assertRaisesRegex(InvariantError, "repeated correction tactic stopped"):
            correction.correction("same-incident", **facts)

    def test_consolidation_and_human_external_routes_fail_closed_without_bound_receipts(self) -> None:
        swarm = Swarm()
        checkpoint = self.receipt(MaterialStateKind.PROOF, 1)
        self.observe(swarm, material_receipt=checkpoint)
        self.observe(swarm)
        fabricated = self.receipt(MaterialStateKind.PROOF, 2)
        with self.assertRaisesRegex(InvariantError, "last-good checkpoint"):
            swarm.choose_retry_reassessment(ReassessmentChoice(ReassessmentRoute.CONSOLIDATE, "consolidate", "thread-42", fabricated))
        with self.assertRaisesRegex(InvariantError, "host custody receipt"):
            ReassessmentChoice(ReassessmentRoute.HUMAN_EXTERNAL_STATE_CHANGE, "wait-human", "thread-42")

    def test_human_external_receipt_must_bind_pending_target_and_cannot_bypass_ledger_throat(self) -> None:
        swarm = Swarm()
        self.observe(swarm)
        pending = self.observe(swarm).reassessment
        unrelated = HostCustodyReceipt("usr-other-0001", CustodyMutation.STATE, "other-target", digest("other"), 1)
        object.__setattr__(unrelated, "_authority", swarm._custody_capability)
        swarm.host_custody_receipts[unrelated.receipt] = unrelated
        choice = ReassessmentChoice(ReassessmentRoute.HUMAN_EXTERNAL_STATE_CHANGE, "wait-human", "other-target", host_custody_receipt=unrelated)
        with self.assertRaisesRegex(InvariantError, "pending action and target"):
            swarm.choose_retry_reassessment(choice)

        expected = swarm.retry_topology_ledger.host_binding_digest(
            pending,
            ReassessmentChoice(
                ReassessmentRoute.HUMAN_EXTERNAL_STATE_CHANGE,
                "wait-human",
                "thread-42",
                host_custody_receipt=HostCustodyReceipt("usr-placeholder-0001", CustodyMutation.STATE, "thread-42", digest("placeholder"), 1),
            ),
        )
        fabricated = HostCustodyReceipt("usr-fabricated-0001", CustodyMutation.STATE, "thread-42", expected, 1)
        fabricated_choice = ReassessmentChoice(ReassessmentRoute.HUMAN_EXTERNAL_STATE_CHANGE, "wait-human", "thread-42", host_custody_receipt=fabricated)
        with self.assertRaisesRegex(InvariantError, "current host authority"):
            swarm.retry_topology_ledger._choose_reassessment(fabricated_choice, host_authority=True)

    def test_stale_material_receipt_cannot_replace_last_good_checkpoint(self) -> None:
        swarm = Swarm()
        latest = self.receipt(MaterialStateKind.STATE, 5)
        self.observe(swarm, material_receipt=latest)
        with self.assertRaisesRegex(InvariantError, "high-water"):
            self.observe(swarm, material_receipt=self.receipt(MaterialStateKind.STATE, 4))
        self.assertEqual(swarm.retry_topology_ledger.last_good_checkpoint, latest)

    def test_newer_timestamp_on_unchanged_material_digest_is_not_progress(self) -> None:
        swarm = Swarm()
        first = MaterialStateReceipt(MaterialStateKind.PROOF, "proof-set", digest("unchanged"), 10)
        liveness_only = MaterialStateReceipt(MaterialStateKind.PROOF, "proof-set", digest("unchanged"), 20)
        self.observe(swarm, material_receipt=first)
        second = self.observe(swarm, material_receipt=liveness_only)
        self.assertFalse(second.material_progress)
        self.assertEqual(second.action, RetryTopologyAction.REASSESS_ROOT_CAUSE)
        self.assertEqual(swarm.retry_topology_ledger.last_good_checkpoint, liveness_only)
        changed_but_older = MaterialStateReceipt(MaterialStateKind.PROOF, "proof-set", digest("changed"), 15)
        with self.assertRaisesRegex(InvariantError, "high-water"):
            self.observe(swarm, material_receipt=changed_but_older)
        self.assertEqual(swarm.retry_topology_ledger.last_good_checkpoint, liveness_only)

    def test_empty_completion_is_unverified_and_uses_one_different_same_owner_route(self) -> None:
        swarm, artifact = self.delegated_swarm()
        task = swarm.tasks["task-a"]
        decision = swarm.resolve_control_path_failure(
            Role.CTRL,
            self.control_failure(artifact),
            same_owner_route="read-inventory",
            safely_resumable=True,
        )
        self.assertEqual(decision.failure_state, ControlPathState.CONTROL_PATH_FAILURE)
        self.assertEqual(decision.state, ControlPathState.RECOVERING)
        self.assertEqual(decision.truth, ControlPathTruth.UNVERIFIED)
        self.assertEqual(decision.action, ControlPathRecoveryAction.SAME_OWNER_DIFFERENT_ROUTE)
        self.assertEqual(decision.recovery_route, "read-inventory")
        self.assertEqual(task.owner, "owner-a")
        self.assertEqual(task.state.value, "ACTIVE")
        self.assertEqual(task.delegation_contract.artifact, artifact)
        self.assertIsNone(swarm.retry_topology_ledger.last_good_checkpoint)
        self.assertEqual(swarm.events.count(("CONTROL_PATH_FAILURE", "task-a")), 1)

    def test_silent_retry_and_cosmetic_paraphrase_are_one_no_poll_decision(self) -> None:
        swarm, artifact = self.delegated_swarm()
        failure = self.control_failure(artifact, kind=ControlPathFailureKind.SILENCE, narration="No readable output")
        first = swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="read-inventory", safely_resumable=True)
        replay = swarm.resolve_control_path_failure(Role.CTRL, replace(failure, narration="The turn was silent again"), same_owner_route="another-route", safely_resumable=True)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.failure.signature_digest, first.failure.signature_digest)
        self.assertEqual(replay.recovery_route, "read-inventory")
        self.assertEqual(swarm.events.count(("CONTROL_PATH_FAILURE", "task-a")), 1)

    def test_disjoint_ready_work_remains_movable_when_authority_is_needed(self) -> None:
        swarm, artifact = self.delegated_swarm()
        decision = swarm.resolve_control_path_failure(
            Role.CTRL,
            self.control_failure(artifact),
            successor_prohibited=True,
            replacement_prohibited=True,
            responsible_authority="host-user",
            disjoint_ready_task_ids=("task-b",),
        )
        self.assertEqual(decision.action, ControlPathRecoveryAction.NEEDS_AUTHORITY)
        self.assertTrue(decision.needs_authority)
        self.assertEqual(decision.disjoint_ready_task_ids, ("task-b",))
        self.assertEqual(swarm.tasks["task-b"].state.value, "ACTIVE")
        self.assertNotIn(("BLOCKED", "task-a"), swarm.events)

    def test_only_existing_authorized_exact_owner_can_receive_handoff(self) -> None:
        swarm, artifact = self.delegated_swarm()
        with self.assertRaisesRegex(InvariantError, "existing authorized exact independent owner"):
            swarm.resolve_control_path_failure(Role.CTRL, self.control_failure(artifact), authorized_handoff_owner="new-owner")
        decision = swarm.resolve_control_path_failure(Role.CTRL, self.control_failure(artifact), authorized_handoff_owner="review-a")
        self.assertEqual(decision.action, ControlPathRecoveryAction.AUTHORIZED_OWNER_HANDOFF)
        self.assertEqual(decision.handoff_owner, "review-a")
        self.assertEqual(swarm.tasks["task-a"].owner, "owner-a")

    def test_needs_authority_is_immediate_exact_and_requires_both_keep_outs(self) -> None:
        swarm, artifact = self.delegated_swarm()
        failure = self.control_failure(artifact)
        with self.assertRaisesRegex(InvariantError, "successor/replacement keep-out"):
            swarm.resolve_control_path_failure(Role.CTRL, failure, successor_prohibited=True)
        decision = swarm.resolve_control_path_failure(Role.CTRL, failure, successor_prohibited=True, replacement_prohibited=True, responsible_authority="host-user")
        self.assertEqual(decision.action, ControlPathRecoveryAction.NEEDS_AUTHORITY)
        self.assertEqual(decision.failure.task_id, "task-a")
        self.assertEqual(decision.failure.worktree, "work/swarm-source")
        self.assertEqual(decision.failure.artifact_paths, ("skills/swarm/runtime/core.py",))
        self.assertEqual(decision.failure.completion_receipt_id, "host:turn:empty-1")
        self.assertIn(("NEEDS_AUTHORITY", "task-a"), swarm.events)

    def test_direct_user_keep_out_beats_peer_closeout_or_available_routes(self) -> None:
        swarm, artifact = self.delegated_swarm()
        swarm.tasks["task-a"].user_custody_required = True
        decision = swarm.resolve_control_path_failure(
            Role.CTRL,
            self.control_failure(artifact, narration="peer requested generic closeout"),
            same_owner_route="read-inventory",
            safely_resumable=True,
            authorized_handoff_owner="review-a",
        )
        self.assertEqual(decision.action, ControlPathRecoveryAction.USER_KEEP_OUT)
        self.assertEqual(decision.recovery_route, "")
        self.assertEqual(decision.handoff_owner, "")
        self.assertEqual(swarm.tasks["task-a"].owner, "owner-a")
        with self.assertRaisesRegex(InvariantError, "derived from durable task custody"):
            swarm.resolve_control_path_failure(Role.CTRL, replace(self.control_failure(artifact), completion_receipt_id="host:turn:empty-2"), user_keep_out=False)

    def test_new_durable_keep_out_supersedes_retained_recovery_without_recounting_failure(self) -> None:
        swarm, artifact = self.delegated_swarm()
        failure = self.control_failure(artifact)
        first = swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="read-inventory", safely_resumable=True)
        self.assertEqual((first.action, first.equivalent_failures), (ControlPathRecoveryAction.SAME_OWNER_DIFFERENT_ROUTE, 1))
        swarm.tasks["task-a"].user_pinned = True
        controlled = swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="alternate-route", safely_resumable=True)
        self.assertEqual((controlled.action, controlled.equivalent_failures), (ControlPathRecoveryAction.USER_KEEP_OUT, 1))
        self.assertFalse(controlled.replayed)
        replay = swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="ignored-route", safely_resumable=True)
        self.assertEqual(replay.action, ControlPathRecoveryAction.USER_KEEP_OUT)
        self.assertTrue(replay.replayed)
        snapshot = swarm.retry_topology_ledger.control_path_snapshot()
        self.assertEqual(RetryTopologyLedger.from_control_path_snapshot(snapshot).control_path_snapshot(), snapshot)

    def test_materially_different_control_route_is_not_blocked_by_retry_anti_loop(self) -> None:
        swarm, artifact = self.delegated_swarm()
        self.observe(swarm)
        self.observe(swarm)
        decision = swarm.resolve_control_path_failure(
            Role.CTRL,
            self.control_failure(artifact),
            same_owner_route="read-inventory",
            safely_resumable=True,
        )
        self.assertEqual(decision.action, ControlPathRecoveryAction.SAME_OWNER_DIFFERENT_ROUTE)

    def test_new_host_or_material_receipt_permits_reentry_without_rebinding(self) -> None:
        swarm, artifact = self.delegated_swarm()
        first_failure = self.control_failure(artifact)
        first = swarm.resolve_control_path_failure(Role.CTRL, first_failure, successor_prohibited=True, replacement_prohibited=True, responsible_authority="host-user")
        material = self.control_receipt(MaterialStateKind.PROOF, 1, first_failure)
        reentered = swarm.resolve_control_path_failure(
            Role.CTRL,
            first_failure,
            same_owner_route="read-inventory",
            safely_resumable=True,
            material_receipt=material,
        )
        self.assertFalse(first.replayed)
        self.assertFalse(reentered.replayed)
        self.assertTrue(reentered.material_reentry)
        self.assertEqual(reentered.action, ControlPathRecoveryAction.SAME_OWNER_DIFFERENT_ROUTE)
        with self.assertRaisesRegex(InvariantError, "conflicts"):
            swarm.resolve_control_path_failure(
                Role.CTRL,
                replace(first_failure, worktree="work/other-source"),
                successor_prohibited=True,
                replacement_prohibited=True,
                responsible_authority="host-user",
                material_receipt=self.control_receipt(MaterialStateKind.PROOF, 2, replace(first_failure, worktree="work/other-source")),
            )
        self.assertEqual(swarm.retry_topology_ledger.last_good_checkpoint, material)
        newer_host = swarm.resolve_control_path_failure(
            Role.CTRL,
            self.control_failure(artifact, completion_receipt_id="host:turn:empty-2", observed_at_ms=20),
            successor_prohibited=True,
            replacement_prohibited=True,
            responsible_authority="host-user",
        )
        self.assertFalse(newer_host.replayed)
        with self.assertRaisesRegex(InvariantError, "conflicts"):
            swarm.resolve_control_path_failure(
                Role.CTRL,
                replace(first_failure, worktree="work/other-source"),
                successor_prohibited=True,
                replacement_prohibited=True,
                responsible_authority="host-user",
            )

    def test_control_material_reentry_requires_exact_failure_task_dispatch_and_candidate(self) -> None:
        swarm, artifact = self.delegated_swarm()
        failure = self.control_failure(artifact)
        swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="read-inventory", safely_resumable=True)
        before = swarm.retry_topology_ledger.control_path_snapshot(), tuple(swarm.events)
        for binding in (
            {"failure_identity": digest("other-failure")},
            {"task_id": "task-elsewhere"},
            {"dispatch_receipt_id": "host:thread:elsewhere"},
            {"candidate": digest("other-candidate")},
        ):
            with self.subTest(binding=binding):
                unrelated = self.control_receipt(MaterialStateKind.PROOF, 9, failure, **binding)
                with self.assertRaisesRegex(InvariantError, "exact failure, task, dispatch, and candidate"):
                    swarm.resolve_control_path_failure(
                        Role.CTRL,
                        failure,
                        material_receipt=unrelated,
                        same_owner_route="alternate-route",
                        safely_resumable=True,
                    )
                self.assertEqual((swarm.retry_topology_ledger.control_path_snapshot(), tuple(swarm.events)), before)
        matching = self.control_receipt(MaterialStateKind.PROOF, 10, failure)
        resumed = swarm.resolve_control_path_failure(Role.CTRL, failure, material_receipt=matching, same_owner_route="alternate-route", safely_resumable=True)
        self.assertTrue(resumed.material_reentry)
        self.assertEqual(swarm.retry_topology_ledger.last_good_checkpoint, matching)

    def test_review_transport_failure_preserves_producer_green_billing_lock_and_global_readiness(self) -> None:
        routed, artifact = self.delegated_swarm()
        candidate = routed.tasks["task-a"]
        candidate.state = TaskState.REVIEW
        candidate.handoff_active = True
        candidate.evidence.append("producer-green")
        routed.workers["manager"] = Worker("manager", "ctrl", 0, WorkerState.WARM)
        manager_ready = Task("manager-ready", "manager", "ctrl", 1, {})
        routed.tasks[manager_ready.id] = manager_ready
        billing = Task("billing", "billing-owner", "lead-b", 1, {}, state=TaskState.WAITING, waiting_on="billing-authority")
        routed.tasks[billing.id] = billing
        handoff = routed.resolve_control_path_failure(
            Role.CTRL,
            self.control_failure(artifact, completion_receipt_id="host:turn:review-empty", failed_route="review-thread"),
            authorized_handoff_owner="review-a",
            disjoint_ready_task_ids=("manager-ready", "task-b"),
        )
        self.assertEqual(handoff.action, ControlPathRecoveryAction.AUTHORIZED_OWNER_HANDOFF)
        self.assertEqual((candidate.state, candidate.review_passed, candidate.acceptance_review_receipt), (TaskState.REVIEW, False, None))
        self.assertEqual((billing.state, billing.waiting_on), (TaskState.WAITING, "billing-authority"))
        self.assertEqual(routed.workers["manager"].state, WorkerState.WARM)
        self.assertEqual(handoff.disjoint_ready_task_ids, ("manager-ready", "task-b"))
        self.assertEqual(routed.tasks["manager-ready"].state, TaskState.ACTIVE)
        self.assertEqual(routed.tasks["task-b"].state, TaskState.ACTIVE)
        self.assertNotIn(("BLOCKED", "task-a"), routed.events)

        needs_authority, artifact = self.delegated_swarm()
        needs_authority.tasks["task-a"].reviewer = None
        decision = needs_authority.resolve_control_path_failure(
            Role.CTRL,
            self.control_failure(artifact, completion_receipt_id="host:turn:review-silent", kind=ControlPathFailureKind.SILENCE, failed_route="review-thread"),
            successor_prohibited=True,
            replacement_prohibited=True,
            responsible_authority="review-authority",
            disjoint_ready_task_ids=("task-b",),
        )
        self.assertEqual(decision.action, ControlPathRecoveryAction.NEEDS_AUTHORITY)
        self.assertEqual(decision.truth, ControlPathTruth.UNVERIFIED)
        self.assertEqual(decision.failure.artifact, artifact)
        self.assertEqual(needs_authority.tasks["task-b"].state, TaskState.ACTIVE)
        self.assertNotIn(("BLOCKED", "task-a"), needs_authority.events)

    def test_recovery_taxonomy_is_edge_scoped_and_attention_precedes_blocked(self) -> None:
        for cause, edge, release in (
            (RecoveryCause.ENVIRONMENT_RESOURCE, "disk-growing-commands", "C-free-at-least-1GiB"),
            (RecoveryCause.DEPENDENCY, "artifact-review", "producer-artifact-frozen"),
            (RecoveryCause.EXTERNAL_SERVICE, "provider-check", "provider-readable"),
        ):
            with self.subTest(cause=cause):
                swarm, artifact = self.delegated_swarm()
                waiting = swarm.resolve_control_path_failure(
                    Role.CTRL,
                    self.control_failure(artifact, cause=cause, affected_edges=(edge,)),
                    release_condition=release,
                    disjoint_ready_task_ids=("task-b",),
                )
                self.assertEqual((waiting.state, waiting.action, waiting.signal), (ControlPathState.WAITING, ControlPathRecoveryAction.WAIT_FOR_RELEASE, WatchdogSignal.ATTENTION))
                self.assertEqual(waiting.failure.affected_edges, (edge,))
                self.assertEqual(waiting.release_condition, release)
                self.assertEqual(swarm.tasks["task-b"].state, TaskState.ACTIVE)
                self.assertNotIn(("BLOCKED", "task-a"), swarm.events)

    def test_terminal_blocked_requires_bounded_failure_and_exact_release_authority(self) -> None:
        swarm, artifact = self.delegated_swarm()
        first = self.control_failure(artifact, cause=RecoveryCause.USER_AUTHORITY, affected_edges=("billing-release",))
        recovering = swarm.resolve_control_path_failure(
            Role.CTRL,
            first,
            same_owner_route="read-inventory",
            safely_resumable=True,
            disjoint_ready_task_ids=("task-b",),
        )
        self.assertEqual((recovering.state, recovering.action, recovering.signal), (ControlPathState.RECOVERING, ControlPathRecoveryAction.SAME_OWNER_DIFFERENT_ROUTE, WatchdogSignal.ATTENTION))
        with self.assertRaisesRegex(InvariantError, "derived from retained route and goal-turn history"):
            swarm.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-2", failed_route="read-inventory", observed_at_ms=20), recovery_exhausted=True, release_condition="billing-owner-approves", responsible_authority="billing-owner")
        rerouted = swarm.resolve_control_path_failure(
            Role.CTRL,
            replace(first, completion_receipt_id="host:turn:empty-2", failed_route="read-inventory", observed_at_ms=20),
            authorized_handoff_owner="review-a",
        )
        self.assertEqual((rerouted.state, rerouted.action), (ControlPathState.RECOVERING, ControlPathRecoveryAction.AUTHORIZED_OWNER_HANDOFF))
        snapshot = swarm.retry_topology_ledger.control_path_snapshot()
        swarm.retry_topology_ledger = RetryTopologyLedger.from_control_path_snapshot(snapshot)
        replay = swarm.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-2", failed_route="read-inventory", observed_at_ms=20))
        self.assertTrue(replay.replayed)
        with self.assertRaisesRegex(InvariantError, "conflicts"):
            swarm.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-2", failed_route="other-route", observed_at_ms=20))
        blocked = swarm.resolve_control_path_failure(
            Role.CTRL,
            replace(first, completion_receipt_id="host:turn:empty-3", failed_route="handoff-review-a", observed_at_ms=30),
            release_condition="billing-owner-approves",
            responsible_authority="billing-owner",
            release_receipt_id="host:release:billing-1",
            disjoint_ready_task_ids=("task-b",),
        )
        self.assertTrue(blocked.terminal_blocked)
        self.assertEqual((blocked.state, blocked.signal, blocked.equivalent_failures), (ControlPathState.BLOCKED, WatchdogSignal.BLOCKER, 3))
        self.assertEqual((blocked.release_condition, blocked.responsible_authority), ("billing-owner-approves", "billing-owner"))
        self.assertEqual(blocked.release_receipt_id, "host:release:billing-1")
        self.assertEqual(blocked.permitted_routes, ("handoff-review-a", "read-inventory"))
        self.assertEqual(swarm.tasks["task-b"].state, TaskState.ACTIVE)
        self.assertEqual(swarm.tasks["task-a"].state, TaskState.ACTIVE)

    def test_repeated_transport_failure_stalls_for_reassessment_and_material_change_clears_it(self) -> None:
        swarm, artifact = self.delegated_swarm()
        first = self.control_failure(artifact)
        swarm.resolve_control_path_failure(Role.CTRL, first, successor_prohibited=True, replacement_prohibited=True, responsible_authority="host-user")
        stalled = swarm.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-2", observed_at_ms=20))
        self.assertEqual((stalled.state, stalled.action, stalled.root_cause_reassessment), (ControlPathState.STALLED, ControlPathRecoveryAction.ROOT_CAUSE_REASSESSMENT, True))
        changed_failure = replace(first, completion_receipt_id="host:turn:empty-3", observed_at_ms=30)
        changed = self.control_receipt(MaterialStateKind.STATE, 1, changed_failure)
        recovering = swarm.resolve_control_path_failure(
            Role.CTRL,
            changed_failure,
            same_owner_route="alternate-readable-receipt",
            safely_resumable=True,
            material_receipt=changed,
        )
        self.assertEqual((recovering.state, recovering.action, recovering.equivalent_failures), (ControlPathState.RECOVERING, ControlPathRecoveryAction.SAME_OWNER_DIFFERENT_ROUTE, 1))
        self.assertEqual(recovering.last_good_checkpoint, changed)

    def test_deterministic_route_order_uses_same_owner_before_handoff_and_eta_requires_receipt(self) -> None:
        swarm, artifact = self.delegated_swarm()
        failure = self.control_failure(artifact, cause=RecoveryCause.OWNER_CAPACITY)
        known = AttemptCostReceipt("cost-route", token_count=20, latency_ms=50, failure_identity=failure.signature_digest, operation=failure.failed_route, attempt=1)
        selected = swarm.resolve_control_path_failure(
            Role.CTRL,
            failure,
            same_owner_route="alternate-readable-receipt",
            safely_resumable=True,
            authorized_handoff_owner="review-a",
            eta_range_ms=(50, 100),
            eta_receipt_id="cost-route",
            cost_receipt=known,
        )
        self.assertEqual((selected.action, selected.route_rank, selected.recovery_route), (ControlPathRecoveryAction.SAME_OWNER_DIFFERENT_ROUTE, 0, "alternate-readable-receipt"))
        self.assertEqual(selected.permitted_routes, ("alternate-readable-receipt", "handoff-review-a"))
        self.assertEqual(selected.route_score_basis, ("expected_progress", "authority", "risk", "latency", "tokens", "coordination"))
        self.assertEqual((selected.eta_range_ms, selected.eta_receipt_id), ((50, 100), "cost-route"))
        with self.assertRaisesRegex(InvariantError, "ETA must bind"):
            other, other_artifact = self.delegated_swarm()
            other.resolve_control_path_failure(Role.CTRL, self.control_failure(other_artifact), same_owner_route="alternate-readable-receipt", safely_resumable=True, eta_range_ms=(1, 2), eta_receipt_id="missing")

    def test_control_path_cost_receipt_cannot_be_misattributed(self) -> None:
        swarm, artifact = self.delegated_swarm()
        failure = self.control_failure(artifact)
        for receipt in (
            AttemptCostReceipt("wrong-failure", token_count=1, failure_identity=digest("other-failure"), operation=failure.failed_route, attempt=1),
            AttemptCostReceipt("wrong-operation", latency_ms=2, failure_identity=failure.signature_digest, operation="other-route", attempt=1),
            AttemptCostReceipt("wrong-attempt", failure_identity=failure.signature_digest, operation=failure.failed_route, attempt=2),
        ):
            with self.subTest(receipt=receipt.receipt_id), self.assertRaisesRegex(InvariantError, "exact failure identity, operation, and attempt"):
                swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="read-inventory", safely_resumable=True, cost_receipt=receipt)
        unknown = AttemptCostReceipt("unknown-bound", failure_identity=failure.signature_digest, operation=failure.failed_route, attempt=1)
        accepted = swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="read-inventory", safely_resumable=True, cost_receipt=unknown)
        self.assertEqual((accepted.token_count, accepted.latency_ms), (None, None))

    def test_rejected_material_and_cost_conflict_is_a_strict_ledger_noop(self) -> None:
        swarm, artifact = self.delegated_swarm()
        first = self.control_failure(artifact)
        retained = self.control_receipt(MaterialStateKind.PROOF, 1, first)
        swarm.resolve_control_path_failure(Role.CTRL, first, same_owner_route="read-inventory", safely_resumable=True, material_receipt=retained)
        swarm.retry_topology_ledger._retain_cost(AttemptCostReceipt("conflict-cost", token_count=1))
        before = (
            swarm.retry_topology_ledger.last_good_checkpoint,
            swarm.retry_topology_ledger.control_path_snapshot(),
            dict(swarm.retry_topology_ledger.cost_receipts),
            dict(swarm.retry_topology_ledger._control_path_decisions),
            dict(swarm.retry_topology_ledger._control_path_receipts),
        )
        failure = replace(first, completion_receipt_id="host:turn:empty-2", failed_route="read-inventory", observed_at_ms=20)
        for receipt, message in (
            (AttemptCostReceipt("wrong-material-cost", token_count=9, failure_identity=digest("other-failure"), operation=failure.failed_route, attempt=1), "exact failure identity, operation, and attempt"),
            (AttemptCostReceipt("conflict-cost", token_count=9, failure_identity=failure.signature_digest, operation=failure.failed_route, attempt=1), "identity conflicts"),
        ):
            with self.subTest(receipt=receipt.receipt_id), self.assertRaisesRegex(InvariantError, message):
                swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="alternate-readable-receipt", safely_resumable=True, material_receipt=self.control_receipt(MaterialStateKind.STATE, 2, failure), cost_receipt=receipt)
            after = (
                swarm.retry_topology_ledger.last_good_checkpoint,
                swarm.retry_topology_ledger.control_path_snapshot(),
                dict(swarm.retry_topology_ledger.cost_receipts),
                dict(swarm.retry_topology_ledger._control_path_decisions),
                dict(swarm.retry_topology_ledger._control_path_receipts),
            )
            self.assertEqual(after, before)

    def test_terminal_blocked_requires_nonempty_distinct_exhausted_route_inventory(self) -> None:
        zero_routes, artifact = self.delegated_swarm()
        first = self.control_failure(artifact, cause=RecoveryCause.USER_AUTHORITY)
        zero_routes.resolve_control_path_failure(Role.CTRL, first, successor_prohibited=True, replacement_prohibited=True, responsible_authority="host-user")
        zero_routes.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-2", observed_at_ms=20))
        empty_inventory = zero_routes.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-3", observed_at_ms=30), release_condition="host-authorizes-route", responsible_authority="host-user")
        self.assertEqual((empty_inventory.state, empty_inventory.action), (ControlPathState.STALLED, ControlPathRecoveryAction.ROOT_CAUSE_REASSESSMENT))
        self.assertNotIn(("BLOCKED", "task-a"), zero_routes.events)

        repeated, artifact = self.delegated_swarm()
        first = self.control_failure(artifact, cause=RecoveryCause.USER_AUTHORITY)
        repeated.resolve_control_path_failure(Role.CTRL, first, same_owner_route="read-inventory", safely_resumable=True)
        repeated.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-2", failed_route="read-inventory", observed_at_ms=20))
        repeated_route = repeated.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-3", failed_route="read-inventory", observed_at_ms=30), release_condition="host-authorizes-route", responsible_authority="host-user")
        self.assertEqual((repeated_route.state, repeated_route.action), (ControlPathState.STALLED, ControlPathRecoveryAction.ROOT_CAUSE_REASSESSMENT))
        self.assertNotIn(("BLOCKED", "task-a"), repeated.events)

    def test_retry_ledger_rejects_raw_caller_custody_boolean(self) -> None:
        ledger = RetryTopologyLedger()
        _, artifact = self.delegated_swarm()
        before = ledger.control_path_snapshot()
        with self.assertRaisesRegex(InvariantError, "internal typed task-custody proof"):
            ledger.control_path_failure(self.control_failure(artifact), custody_proof=False)
        self.assertEqual(ledger.control_path_snapshot(), before)

    def test_control_path_snapshot_restores_exact_decision_cost_checkpoint_and_replay_conflicts(self) -> None:
        swarm, artifact = self.delegated_swarm()
        failure = self.control_failure(artifact)
        material = self.control_receipt(MaterialStateKind.PROOF, 1, failure)
        cost = AttemptCostReceipt("cost-snapshot", token_count=13, latency_ms=21, failure_identity=failure.signature_digest, operation=failure.failed_route, attempt=1)
        first = swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="read-inventory", safely_resumable=True, material_receipt=material, cost_receipt=cost)
        snapshot = swarm.retry_topology_ledger.control_path_snapshot()
        json.dumps(snapshot)
        restored = RetryTopologyLedger.from_control_path_snapshot(snapshot)
        self.assertEqual(restored.control_path_snapshot(), snapshot)
        self.assertEqual(restored.last_good_checkpoint, material)
        self.assertEqual(restored.cost_receipts["cost-snapshot"], cost)
        swarm.retry_topology_ledger = restored
        replay = swarm.resolve_control_path_failure(Role.CTRL, failure, same_owner_route="read-inventory", safely_resumable=True, material_receipt=material, cost_receipt=cost)
        self.assertTrue(replay.replayed)
        self.assertEqual((replay.action, replay.token_count, replay.latency_ms), (first.action, 13, 21))
        before = restored.control_path_snapshot()
        with self.assertRaisesRegex(InvariantError, "conflicts"):
            swarm.resolve_control_path_failure(Role.CTRL, replace(failure, failed_route="other-route"), same_owner_route="read-inventory", safely_resumable=True)
        self.assertEqual(restored.control_path_snapshot(), before)

    def test_material_reentry_snapshot_retains_completion_decision_bindings(self) -> None:
        swarm, artifact = self.delegated_swarm()
        first_failure = self.control_failure(artifact)
        first = swarm.resolve_control_path_failure(Role.CTRL, first_failure, same_owner_route="read-inventory", safely_resumable=True)
        reentry_failure = replace(first_failure, completion_receipt_id="host:turn:empty-2", failed_route="read-inventory", observed_at_ms=20)
        material = self.control_receipt(MaterialStateKind.PROOF, 1, reentry_failure)
        reentered = swarm.resolve_control_path_failure(Role.CTRL, reentry_failure, authorized_handoff_owner="review-a", material_receipt=material)
        self.assertTrue(reentered.material_reentry)
        self.assertEqual(reentered.equivalent_failures, 1)

        snapshot = swarm.retry_topology_ledger.control_path_snapshot()
        json.dumps(snapshot)
        restored = RetryTopologyLedger.from_control_path_snapshot(snapshot)
        self.assertEqual(restored.control_path_snapshot(), snapshot)
        self.assertEqual(restored.last_good_checkpoint, material)
        swarm.retry_topology_ledger = restored

        replay = swarm.resolve_control_path_failure(Role.CTRL, first_failure, same_owner_route="read-inventory", safely_resumable=True)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.action, first.action)
        before_conflict = restored.control_path_snapshot()
        with self.assertRaisesRegex(InvariantError, "conflicts"):
            swarm.resolve_control_path_failure(Role.CTRL, replace(first_failure, failed_route="other-route"), same_owner_route="read-inventory", safely_resumable=True)
        self.assertEqual(restored.control_path_snapshot(), before_conflict)

        continued = swarm.resolve_control_path_failure(
            Role.CTRL,
            replace(reentry_failure, completion_receipt_id="host:turn:empty-3", failed_route="handoff-review-a", observed_at_ms=30),
            same_owner_route="alternate-readable-receipt",
            safely_resumable=True,
        )
        self.assertEqual(continued.action, ControlPathRecoveryAction.SAME_OWNER_DIFFERENT_ROUTE)
        self.assertEqual(continued.equivalent_failures, 2)

    def test_control_path_goal_turn_observation_must_advance_before_mutation(self) -> None:
        swarm, artifact = self.delegated_swarm()
        first = self.control_failure(artifact)
        swarm.resolve_control_path_failure(Role.CTRL, first, same_owner_route="read-inventory", safely_resumable=True)
        swarm.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-2", failed_route="read-inventory", observed_at_ms=20), authorized_handoff_owner="review-a")
        before = swarm.retry_topology_ledger.control_path_snapshot()
        with self.assertRaisesRegex(InvariantError, "observation high-water"):
            swarm.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-3", failed_route="handoff-review-a", observed_at_ms=15), release_condition="host-release", responsible_authority="host-user", release_receipt_id="host:release:1")
        self.assertEqual(swarm.retry_topology_ledger.control_path_snapshot(), before)

    def test_terminal_blocked_requires_bound_external_release_receipt(self) -> None:
        swarm, artifact = self.delegated_swarm()
        first = self.control_failure(artifact, cause=RecoveryCause.USER_AUTHORITY)
        swarm.resolve_control_path_failure(Role.CTRL, first, same_owner_route="read-inventory", safely_resumable=True)
        swarm.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-2", failed_route="read-inventory", observed_at_ms=20), authorized_handoff_owner="review-a")
        without_receipt = swarm.resolve_control_path_failure(Role.CTRL, replace(first, completion_receipt_id="host:turn:empty-3", failed_route="handoff-review-a", observed_at_ms=30), release_condition="host-release", responsible_authority="host-user")
        self.assertEqual((without_receipt.state, without_receipt.action), (ControlPathState.STALLED, ControlPathRecoveryAction.ROOT_CAUSE_REASSESSMENT))
        self.assertFalse(without_receipt.terminal_blocked)

    def test_historical_blocked_remains_blocked_without_rewriting_audit_history(self) -> None:
        self.assertEqual(ControlPathState.from_historical("BLOCKED"), ControlPathState.BLOCKED)


if __name__ == "__main__":
    unittest.main()
