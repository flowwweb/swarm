from __future__ import annotations

from hashlib import sha256
import unittest

from skills.swarm.runtime.core import (
    AttemptCostReceipt,
    CustodyMutation,
    HostCustodyReceipt,
    InvariantError,
    MaterialStateKind,
    MaterialStateReceipt,
    ReassessmentChoice,
    ReassessmentRoute,
    Role,
    RetryOutcome,
    RetryTopologyAction,
    Swarm,
    Task,
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
        self.assertEqual(swarm.retry_topology_ledger.last_good_checkpoint, first)


if __name__ == "__main__":
    unittest.main()
