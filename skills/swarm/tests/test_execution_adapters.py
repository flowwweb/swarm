from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import unittest

from skills.swarm.runtime import (
    AcceptanceContract,
    AdapterCapability,
    AdapterCapabilityMatrix,
    AdapterCapabilityState,
    AdapterEvent,
    AdapterPlanStatus,
    AdapterRegistry,
    ArtifactIdentity,
    CodexAppServerAdapter,
    ContinuationSnapshot,
    CtrlMode,
    DelegatedReceiptVerdict,
    DelegatedReturnReceipt,
    ExecutionAdapter,
    ExecutionAdapterRequest,
    ExecutionConfigGeneration,
    ExecutionDispatchLedger,
    ExecutionDispatchState,
    ExecutionFailureKind,
    ExecutionReservation,
    ExecutionRoute,
    HostCapacityEvidence,
    HostTaskCapacity,
    InvariantError,
    LaneKind,
    LaneMaterialization,
    ProfessionAssignment,
    ReviewEvidence,
    ReviewScope,
    ReviewStrategy,
    Role,
    RoutingEconomics,
    RoutingEvidenceBasis,
    Swarm,
    Task,
    TaskState,
    WorkRoutingFacts,
    WorkSize,
    Worker,
    HostServiceTierReceipt,
    ServiceTierTruth,
    TopologyMaterializationPlan,
    route_execution,
)


class ExecutionAdapterTests(unittest.TestCase):
    instruction = "Implement the exact bounded adapter artifact."

    def routing(self):
        return route_execution(
            facts=WorkRoutingFacts(size=WorkSize.MEDIUM, bounded=True, low_risk=True, mutable_surface_count=1),
            economics=RoutingEconomics(
                20, 60, 0, 0, 0, 0, 0,
                RoutingEvidenceBasis.CONSERVATIVE_ASSUMPTION,
                assumptions=("bounded source-only startup estimate",),
            ),
            capacity=HostCapacityEvidence(HostTaskCapacity.AVAILABLE, True, "host:capacity:adapter-task"),
            accountable_owner="lead-a",
            lead_owner="lead-a",
        )

    def request(self, *, adapter_id=CodexAppServerAdapter.ADAPTER_ID, required=("thread.start", "turn.start", "swarm.routing")):
        return ExecutionAdapterRequest(
            "adapter-request-1",
            adapter_id,
            "task-adapter",
            "lead-a",
            "C:/work/swarm",
            ArtifactIdentity.exact_tree(
                "adapter",
                "a" * 40,
                "execution",
                artifact_digest="b" * 64,
                path_manifest_digest="c" * 64,
            ),
            sha256(self.instruction.encode("utf-8")).hexdigest(),
            required,
            self.routing(),
            model="gpt-5.6",
            approval_policy="on-request",
            sandbox="workspace-write",
        )

    def test_capability_matrix_is_truthful_and_explicit(self) -> None:
        matrix = CodexAppServerAdapter().matrix
        self.assertEqual(matrix.state_for("thread.start"), AdapterCapabilityState.NATIVE)
        self.assertEqual(matrix.state_for("swarm.routing"), AdapterCapabilityState.ENFORCED)
        self.assertEqual(matrix.state_for("swarm.topology_dispatch"), AdapterCapabilityState.INSTRUCTION_ONLY)
        self.assertEqual(matrix.state_for("model.instructions"), AdapterCapabilityState.INSTRUCTION_ONLY)
        self.assertEqual(matrix.state_for("review.acceptance"), AdapterCapabilityState.UNSUPPORTED)
        self.assertEqual(matrix.state_for("host.task_mutation"), AdapterCapabilityState.UNSUPPORTED)
        self.assertEqual(matrix.state_for("not-declared"), AdapterCapabilityState.UNSUPPORTED)

    def test_codex_adapter_consumes_topology_packet_as_instruction_only_and_never_emits_host_call(self) -> None:
        plan = TopologyMaterializationPlan((
            LaneMaterialization("ctrl", Role.CTRL, "Ship", icon="🐙"),
            LaneMaterialization(
                "doer",
                Role.DOER,
                "Adapter",
                "ctrl",
                ProfessionAssignment("developer"),
                "💻",
                artifact_id="adapter",
                direct_production=True,
            ),
        ))
        packet = Swarm().topology_dispatch_preflight("ctrl", "thread-ctrl").prepare(plan, ready_lane_ids=("doer",))
        adapter_plan = CodexAppServerAdapter().plan_topology_dispatch(packet)
        self.assertEqual(adapter_plan.status, AdapterPlanStatus.BLOCKED)
        self.assertIn("instruction-only", adapter_plan.blocker)
        self.assertIn("UNVERIFIED", adapter_plan.claim_limit)

    def test_adapter_is_optional_and_missing_or_disabled_never_falls_back(self) -> None:
        request = self.request()
        missing = AdapterRegistry().plan(request)
        self.assertEqual(missing.status, AdapterPlanStatus.DISABLED)
        self.assertIn("not configured", missing.blocker)
        disabled = AdapterRegistry((CodexAppServerAdapter(enabled=False),)).plan(request)
        self.assertEqual(disabled.status, AdapterPlanStatus.DISABLED)
        self.assertIn("disabled", disabled.blocker)

    def test_required_instruction_only_or_unsupported_capability_fails_closed(self) -> None:
        adapter = CodexAppServerAdapter()
        for capability, label in (("model.instructions", "instruction-only"), ("review.acceptance", "unsupported"), ("missing", "unsupported")):
            with self.subTest(capability=capability):
                plan = adapter.plan(self.request(required=(capability,)))
                self.assertEqual(plan.status, AdapterPlanStatus.BLOCKED)
                self.assertIn(label, plan.blocker)

    def test_native_codex_wire_messages_require_exact_ready_plan_and_instruction_digest(self) -> None:
        adapter = CodexAppServerAdapter()
        request = self.request()
        plan = adapter.plan(request)
        self.assertEqual(plan.status, AdapterPlanStatus.READY)
        self.assertEqual(adapter.initialize_request("SWARM"), {"method": "initialize", "id": 0, "params": {"clientInfo": {"name": "SWARM", "title": "SWARM", "version": "1"}}})
        self.assertEqual(adapter.thread_request(plan, request)["method"], "thread/start")
        self.assertEqual(adapter.thread_request(plan, request, thread_id="thread-1")["method"], "thread/resume")
        turn = adapter.turn_request(plan, request, thread_id="thread-1", instruction=self.instruction)
        self.assertEqual(turn["method"], "turn/start")
        self.assertEqual(turn["params"]["threadId"], "thread-1")
        with self.assertRaisesRegex(InvariantError, "instruction.*digest"):
            adapter.turn_request(plan, request, thread_id="thread-1", instruction="different")
        with self.assertRaisesRegex(InvariantError, "exact request"):
            adapter.thread_request(plan, replace(request, task_id="different-task"))

    def test_events_store_only_safe_identity_status_and_digest(self) -> None:
        event = CodexAppServerAdapter().translate_event(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {"id": "item-1", "status": "completed", "text": "sensitive response body"},
                },
            }
        )
        self.assertEqual((event.thread_id, event.turn_id, event.item_id, event.status), ("thread-1", "turn-1", "item-1", "completed"))
        self.assertEqual(len(event.evidence_digest), 64)
        self.assertNotIn("sensitive", repr(event))
        self.assertNotIn(self.instruction, repr(self.request()))

    def test_hard_blocked_routing_cannot_be_wrapped_by_an_adapter(self) -> None:
        with self.assertRaisesRegex(InvariantError, "hard-blocked"):
            replace(self.request(), routing=replace(self.routing(), route=ExecutionRoute.HARD_BLOCKED))

    def test_provider_neutral_adapter_uses_the_same_request_contract(self) -> None:
        matrix = AdapterCapabilityMatrix(
            "local-runner",
            "local-provider",
            True,
            (
                AdapterCapability("execute", AdapterCapabilityState.NATIVE, "local protocol", "Starts one execution only."),
                AdapterCapability("swarm.routing", AdapterCapabilityState.ENFORCED, "SWARM request", "Owner and route are exact."),
            ),
        )
        adapter = ExecutionAdapter(matrix, entrypoint=("local-runner", "serve"), protocol="jsonl")
        request = self.request(adapter_id="local-runner", required=("execute", "swarm.routing"))
        plan = AdapterRegistry((adapter,)).plan(request)
        self.assertEqual((plan.status, plan.entrypoint, plan.protocol), (AdapterPlanStatus.READY, ("local-runner", "serve"), "jsonl"))


class ExecutionDispatchLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = ArtifactIdentity("queue-artifact", "rev-1", "exact queue result")

    @staticmethod
    def generation(identity: str, tier: str, changed_at: int) -> ExecutionConfigGeneration:
        return ExecutionConfigGeneration(identity, tier in {"fast", "priority"}, "gpt-5.6", "high", changed_at, f"host:config:{identity}")

    def ledger(self, tier: str = "default") -> ExecutionDispatchLedger:
        ledger = ExecutionDispatchLedger()
        ledger.observe_generation(self.generation(f"generation-{tier}", tier, 10))
        ledger.reserve("reservation-1", "queue-task", "worker", self.artifact, observed_at_ms=11)
        return ledger

    def accepted_runtime(self) -> Swarm:
        runtime = Swarm()
        runtime.add_lead(Role.CTRL, "lead")
        runtime.add_worker(Role.LEAD, Worker("worker", "lead", 1))
        task = Task(
            "queue-task", "worker", "creator", 1, {},
            subagent_receipt="host:thread:queue-task", ctrl_mode=CtrlMode.DIRECT,
            lane_kind=LaneKind.OTHER, owning_lead_id="lead",
            acceptance_contract=AcceptanceContract(self.artifact, ()),
        )
        runtime.assign(Role.LEAD, task)
        plan = task.acceptance_contract.proof_plan
        self.assertIsNotNone(plan)
        runtime.review(
            Role.REVIEW,
            task.id,
            ReviewEvidence(
                ReviewStrategy.LIGHT, "reviewer", True, self.artifact,
                receipt=(("acceptance", "review:queue-task"),),
                scope=ReviewScope.ACCEPTANCE,
                plan_digest=plan.plan_digest,
            ),
            True,
        )
        return runtime

    def material_receipt(self) -> DelegatedReturnReceipt:
        return DelegatedReturnReceipt(
            "receipt-queue-task", "queue-task", "worker", DelegatedReceiptVerdict.ACCEPT,
            self.artifact, "Exact bounded material result.", observed_at=20,
        )

    @staticmethod
    def host_event(status: str, *, thread_id: str = "thread", turn_id: str = "turn", marker: str = "event") -> AdapterEvent:
        return CodexAppServerAdapter().translate_event({
            "method": f"turn/{status}",
            "params": {"threadId": thread_id, "turnId": turn_id, "status": status, "marker": marker},
        })

    def test_fast_to_standard_checkpoints_running_work_and_next_turn_resolves_fresh_generation(self) -> None:
        ledger = self.ledger("fast")
        active = ledger.dispatch("reservation-1", "a" * 64, 1000, observed_at_ms=12)
        self.assertEqual((active.requested_service_tier, active.requested_model), ("fast", "gpt-5.6"))
        self.assertEqual((ledger.latest_generation.fast_mode, ledger.latest_generation.host_features), (True, {"fast_mode": True}))
        ledger.observe_generation(self.generation("generation-standard", "default", 20))
        self.assertEqual(active.requested_service_tier, "fast")
        self.assertEqual(active.next_generation_id, "generation-standard")
        ledger.checkpoint("reservation-1", observed_at_ms=21)
        resumed = ledger.dispatch("reservation-1", "b" * 64, 900, observed_at_ms=22)
        self.assertEqual((resumed.requested_service_tier, resumed.generation_id), ("default", "generation-standard"))
        self.assertEqual(resumed.service_tier_truth, ServiceTierTruth.UNVERIFIED)

    def test_standard_to_fast_resolves_at_dispatch_without_model_change(self) -> None:
        ledger = self.ledger("default")
        ledger.defer("reservation-1", observed_at_ms=11)
        ledger.observe_generation(self.generation("generation-fast", "fast", 20))
        active = ledger.dispatch("reservation-1", "c" * 64, 800, observed_at_ms=21)
        self.assertEqual((active.requested_service_tier, active.requested_model, active.requested_effort), ("fast", "gpt-5.6", "high"))
        self.assertTrue(active.requested_fast_mode)

    def test_checkpoint_invalidates_stale_request_metadata_and_restart_retry_uses_latest_generation(self) -> None:
        ledger = self.ledger("fast")
        record = ledger.dispatch("reservation-1", "d" * 64, 900, observed_at_ms=12)
        ledger.observe_generation(self.generation("generation-standard", "default", 13))
        ledger.checkpoint("reservation-1", observed_at_ms=14)
        self.assertEqual((record.generation_id, record.requested_service_tier, record.requested_model), ("", "", ""))
        resumed = ledger.dispatch("reservation-1", "e" * 64, 800, observed_at_ms=15)
        self.assertEqual((resumed.generation_id, resumed.requested_service_tier), ("generation-standard", "default"))
        ledger.fail_transport("reservation-1", ExecutionFailureKind.BAD_REQUEST, observed_at_ms=16, http_status=400, detail="Bad Request")
        restored = ExecutionDispatchLedger(generations=ledger.generations, reservations=(ExecutionReservation.from_snapshot(resumed.snapshot()),))
        retried = restored.retry_smaller(
            "reservation-1", ContinuationSnapshot("f" * 64, 800, 600, 17), "a" * 64, 550, observed_at_ms=18,
        )
        self.assertEqual((retried.requested_service_tier, retried.requested_fast_mode), ("default", False))

    def test_execution_config_generations_are_strictly_monotonic_and_identity_bound(self) -> None:
        ledger = self.ledger("default")
        with self.assertRaisesRegex(InvariantError, "stale or ambiguously ordered"):
            ledger.observe_generation(self.generation("generation-stale", "fast", 10))
        with self.assertRaisesRegex(InvariantError, "identity conflicts"):
            ledger.observe_generation(self.generation("generation-default", "fast", 10))

    def test_unavailable_or_conflicting_served_tier_stays_unverified(self) -> None:
        ledger = self.ledger("fast")
        active = ledger.dispatch("reservation-1", "e" * 64, 600, observed_at_ms=12)
        event = self.host_event("completed", marker="unverified")
        ledger.observe_event("reservation-1", event, observed_at_ms=13)
        self.assertEqual((active.actual_service_tier, active.service_tier_truth), ("", ServiceTierTruth.UNVERIFIED))
        other = self.ledger("fast")
        request = other.dispatch("reservation-1", "1" * 64, 600, observed_at_ms=12)
        other.observe_event(
            "reservation-1",
            self.host_event("completed", marker="conflicting"),
            observed_at_ms=13,
            served_tier=HostServiceTierReceipt(request.request_digest, "default", "host:response:tier", 13),
        )
        self.assertEqual(request.service_tier_truth, ServiceTierTruth.UNVERIFIED)
        confirmed = self.ledger("fast")
        confirmed_request = confirmed.dispatch("reservation-1", "3" * 64, 600, observed_at_ms=12)
        confirmed.observe_event(
            "reservation-1",
            self.host_event("completed", marker="confirmed"),
            observed_at_ms=13,
            served_tier=CodexAppServerAdapter.translate_service_tier_receipt(
                {"id": 7, "result": {"service_tier": "priority"}},
                request_digest=confirmed_request.request_digest,
                observed_at_ms=13,
            ),
        )
        self.assertEqual((confirmed_request.actual_service_tier, confirmed_request.service_tier_truth), ("priority", ServiceTierTruth.CONFIRMED))

    def test_host_completion_material_receipt_independent_review_and_complete_are_distinct(self) -> None:
        ledger = self.ledger()
        record = ledger.dispatch("reservation-1", "3" * 64, 500, observed_at_ms=12)
        with self.assertRaisesRegex(InvariantError, "host observation"):
            ledger.observe_event(
                "reservation-1",
                AdapterEvent("turn/completed", "thread", "turn", status="completed", evidence_digest="4" * 64),
                observed_at_ms=12,
            )
        event = self.host_event("completed", marker="pipeline")
        self.assertTrue(ledger.observe_event("reservation-1", event, observed_at_ms=13))
        self.assertFalse(ledger.observe_event("reservation-1", event, observed_at_ms=14))
        self.assertEqual(record.state, ExecutionDispatchState.ACTIVE)
        material = self.material_receipt()
        ledger.record_material_receipt("reservation-1", material, observed_at_ms=20)
        self.assertIs(ledger.record_material_receipt("reservation-1", material, observed_at_ms=20), record)
        self.assertFalse(ledger.observe_event("reservation-1", event, observed_at_ms=20))
        runtime = self.accepted_runtime()
        ledger.record_independent_review("reservation-1", runtime, observed_at_ms=21)
        self.assertEqual(record.state, ExecutionDispatchState.INDEPENDENT_REVIEW)
        runtime.complete(Role.LEAD, "queue-task", True, True, 22, actor_id="lead")
        ledger.record_complete("reservation-1", runtime, observed_at_ms=22)
        self.assertEqual((record.state, runtime.tasks["queue-task"].state), (ExecutionDispatchState.COMPLETE, TaskState.COMPLETE))

    def test_silence_empty_unreadable_timeout_and_bad_request_never_complete(self) -> None:
        for index, kind in enumerate((ExecutionFailureKind.SILENCE, ExecutionFailureKind.EMPTY, ExecutionFailureKind.UNREADABLE, ExecutionFailureKind.TIMEOUT, ExecutionFailureKind.BAD_REQUEST)):
            with self.subTest(kind=kind):
                ledger = self.ledger()
                record = ledger.dispatch("reservation-1", f"{index + 5:x}" * 64, 500, observed_at_ms=12)
                kwargs = {"http_status": 400, "detail": "Bad Request"} if kind is ExecutionFailureKind.BAD_REQUEST else {}
                ledger.fail_transport("reservation-1", kind, observed_at_ms=13, **kwargs)
                self.assertEqual(record.state, ExecutionDispatchState.UNVERIFIED)
                self.assertEqual(record.reservation_id, "reservation-1")

    def test_known_bad_request_turns_remain_unverified_without_retaining_payload_content(self) -> None:
        for index, turn_id in enumerate(("01a03196-367f-7940-8ed7-c803d591409d", "01a0320d-a579-7570-96c0-ed7f60bb2a0e")):
            with self.subTest(turn_id=turn_id):
                ledger = self.ledger()
                record = ledger.dispatch("reservation-1", f"{index + 6:x}" * 64, 1000, observed_at_ms=12)
                event = self.host_event("error", turn_id=turn_id, marker=f"failure-{index}")
                ledger.observe_event("reservation-1", event, observed_at_ms=13)
                self.assertEqual((record.state, record.failure_kind, record.host_turn_id), (ExecutionDispatchState.UNVERIFIED, ExecutionFailureKind.HOST_FAILED, turn_id))
                self.assertNotIn("detail", repr(record))

    def test_bad_request_retains_reservation_and_allows_only_one_fresh_smaller_retry(self) -> None:
        ledger = self.ledger()
        record = ledger.dispatch("reservation-1", "a" * 64, 1200, observed_at_ms=12)
        ledger.fail_transport("reservation-1", ExecutionFailureKind.BAD_REQUEST, observed_at_ms=13, http_status=400, detail="Bad Request")
        snapshot = ContinuationSnapshot("b" * 64, 1200, 700, 14)
        retried = ledger.retry_smaller("reservation-1", snapshot, "c" * 64, 650, observed_at_ms=15)
        self.assertIs(retried, record)
        self.assertEqual((retried.retry_count, retried.request_bytes, retried.snapshot_digest), (1, 650, "b" * 64))
        ledger.fail_transport("reservation-1", ExecutionFailureKind.BAD_REQUEST, observed_at_ms=16, http_status=400, detail="Bad Request")
        with self.assertRaisesRegex(InvariantError, "only one"):
            ledger.retry_smaller("reservation-1", ContinuationSnapshot("d" * 64, 650, 400, 17), "e" * 64, 350, observed_at_ms=18)

    def test_duplicate_dispatch_and_direct_user_keep_out_fail_closed(self) -> None:
        ledger = self.ledger()
        with self.assertRaisesRegex(InvariantError, "keep-out"):
            ledger.dispatch("reservation-1", "f" * 64, 500, observed_at_ms=12, direct_user_keep_out=True)
        ledger.dispatch("reservation-1", "f" * 64, 500, observed_at_ms=13)
        with self.assertRaisesRegex(InvariantError, "duplicate dispatch"):
            ledger.dispatch("reservation-1", "1" * 64, 400, observed_at_ms=14)


if __name__ == "__main__":
    unittest.main()
