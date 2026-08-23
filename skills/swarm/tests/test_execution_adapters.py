from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import unittest

from skills.swarm.runtime import (
    AdapterCapability,
    AdapterCapabilityMatrix,
    AdapterCapabilityState,
    AdapterPlanStatus,
    AdapterRegistry,
    ArtifactIdentity,
    CodexAppServerAdapter,
    ExecutionAdapter,
    ExecutionAdapterRequest,
    ExecutionRoute,
    HostCapacityEvidence,
    HostTaskCapacity,
    InvariantError,
    LaneMaterialization,
    ProfessionAssignment,
    Role,
    RoutingEconomics,
    RoutingEvidenceBasis,
    Swarm,
    WorkRoutingFacts,
    WorkSize,
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


if __name__ == "__main__":
    unittest.main()
