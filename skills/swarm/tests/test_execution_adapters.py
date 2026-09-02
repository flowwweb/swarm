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
    ChatGPTRouteStatus,
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
    HostChatGPTCapability,
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
    HQAutoGrant,
    HQAuthorizationReceipt,
    HQCommandAction,
    HQCommandEnvelope,
    HQDispatchMaterial,
    HQRootObservation,
    HQTargetIntent,
    ServiceTierTruth,
    TopologyMaterializationPlan,
    UniversalHQConnector,
    route_execution,
)
from skills.swarm.runtime.progress_events import Ledger, build_task_manifest, load_builtin_role_manifests


class FakeCodexTransport:
    def __init__(self, responses=None, reconciliations=None):
        self.responses = list(responses or ())
        self.reconciliations = list(reconciliations or ())
        self.calls = []
        self.reconcile_calls = []

    def request(self, method, params):
        expected = {
            "thread/start": {"cwd"},
            "thread/resume": {"threadId"},
            "turn/start": {"threadId", "input", "cwd"},
            "turn/steer": {"threadId", "expectedTurnId", "input"},
        }
        if method not in expected or set(params) != expected[method]:
            raise AssertionError(f"wrong App Server schema for {method}: {params!r}")
        if method.startswith("turn/"):
            items = params["input"]
            if not isinstance(items, list) or len(items) != 1 or set(items[0]) != {"type", "text", "text_elements"} or items[0]["type"] != "text" or items[0]["text_elements"] != []:
                raise AssertionError("turn input must match the installed text UserInput schema")
        self.calls.append((method, dict(params)))
        if self.responses:
            return dict(self.responses.pop(0))
        if method in {"thread/start", "thread/resume"}:
            thread_id = str(params.get("threadId") or "thread-1")
            return {"thread": {"id": thread_id}, "cwd": "C:/work/project-a"}
        if method == "turn/steer":
            return {"turnId": params["expectedTurnId"]}
        return {"turn": {"id": "turn-1"}}

    def reconcile(self, command_id, action, target_thread_id):
        self.reconcile_calls.append((command_id, action, target_thread_id))
        return self.reconciliations.pop(0) if self.reconciliations else None


class FakeHQAuthorizationVerifier:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.calls = []

    def verify(self, authorization, envelope, now_ms):
        self.calls.append((authorization, envelope.command_id, now_ms))
        return self.accepted


class FakeHQMaterialResolver:
    def __init__(self, material):
        self.material = material
        self.calls = []

    def resolve(self, envelope):
        self.calls.append(envelope.command_id)
        return self.material


class FakeHQRootVerifier:
    def __init__(self, *, canonical_cwd=None, root_digest=None, accepted=True):
        self.canonical_cwd = canonical_cwd
        self.root_digest = root_digest
        self.accepted = accepted
        self.calls = []

    def observe(self, cwd):
        self.calls.append(("observe", cwd))
        root_digest = self.root_digest or ("a" * 64 if cwd == "C:/work/project-a" else "b" * 64)
        return HQRootObservation("root-observation", self.canonical_cwd or cwd, root_digest)

    def verify(self, observation, envelope):
        self.calls.append(("verify", observation.receipt_id, envelope.command_id))
        return self.accepted


class UnavailableHQMaterialResolver:
    def __init__(self):
        self.calls = []

    def resolve(self, envelope):
        self.calls.append(envelope.command_id)
        raise AssertionError("transient dispatch material is unavailable after restart")


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
        self.assertEqual(turn["params"]["input"], [{"type": "text", "text": self.instruction, "text_elements": []}])
        with self.assertRaisesRegex(AssertionError, "installed text UserInput schema"):
            FakeCodexTransport().request("turn/start", {"threadId": "thread-1", "input": [{"type": "text", "text": self.instruction}], "cwd": "C:/work/project-a"})
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

    def test_chatgpt_routing_uses_only_exact_host_observed_capabilities(self) -> None:
        registry = AdapterRegistry()
        chat = HostChatGPTCapability("chat", "host-chat", "receipt-chat")
        image = HostChatGPTCapability("image", "host-imagegen", "receipt-image")
        work = HostChatGPTCapability("work", "host-work", "receipt-work", "workspace-alpha")

        disabled = registry.plan_chatgpt("chat", (chat,), enabled=False)
        self.assertEqual((disabled.status, disabled.adapter_id), (ChatGPTRouteStatus.FALLBACK, CodexAppServerAdapter.ADAPTER_ID))
        missing = registry.plan_chatgpt("image", (), enabled=True)
        self.assertEqual(missing.status, ChatGPTRouteStatus.FALLBACK)
        self.assertIn("local Codex", missing.reason)
        ready = registry.plan_chatgpt("image", (chat, image), enabled=True)
        self.assertEqual((ready.status, ready.adapter_id, ready.capability_receipt_id), (ChatGPTRouteStatus.READY, "host-imagegen", "receipt-image"))
        bounded_work = registry.plan_chatgpt("work", (work,), enabled=True, workspace_id="workspace-alpha")
        self.assertEqual((bounded_work.status, bounded_work.workspace_id), (ChatGPTRouteStatus.READY, "workspace-alpha"))
        wrong_workspace = registry.plan_chatgpt("work", (work,), enabled=True, workspace_id="workspace-beta")
        self.assertEqual(wrong_workspace.status, ChatGPTRouteStatus.FALLBACK)

    def test_chatgpt_routing_preserves_explicit_model_and_reasoning_or_falls_back(self) -> None:
        registry = AdapterRegistry()
        fixed = HostChatGPTCapability("chat", "host-chat", "receipt-fixed")
        selectable = HostChatGPTCapability(
            "chat", "host-chat-selectable", "receipt-selectable",
            supports_model_selection=True, supports_reasoning_selection=True,
        )
        fallback = registry.plan_chatgpt("chat", (fixed,), enabled=True, explicit_model="user-model")
        self.assertEqual(fallback.status, ChatGPTRouteStatus.FALLBACK)
        ready = registry.plan_chatgpt(
            "chat", (selectable,), enabled=True,
            explicit_model="user-model", explicit_reasoning="high",
        )
        self.assertEqual((ready.model, ready.reasoning), ("user-model", "high"))

    def test_chatgpt_routing_rejects_ambiguous_or_untyped_host_claims(self) -> None:
        registry = AdapterRegistry()
        with self.assertRaisesRegex(InvariantError, "typed host capabilities"):
            registry.plan_chatgpt("chat", (object(),), enabled=True)
        with self.assertRaisesRegex(InvariantError, "distinct"):
            registry.plan_chatgpt(
                "chat",
                (
                    HostChatGPTCapability("chat", "duplicate", "receipt-a"),
                    HostChatGPTCapability("chat", "duplicate", "receipt-b"),
                ),
                enabled=True,
            )

    @staticmethod
    def connector(transport, material, *, verified=True, enabled=True, root_verifier=None):
        return UniversalHQConnector(
            CodexAppServerAdapter(enabled=enabled, transport=transport),
            authorization_verifier=FakeHQAuthorizationVerifier(verified),
            material_resolver=FakeHQMaterialResolver(material),
            root_verifier=root_verifier or FakeHQRootVerifier(),
        )

    @staticmethod
    def explicit(envelope):
        return HQAuthorizationReceipt(f"auth-{envelope.command_id}", envelope.digest, envelope.project_id, envelope.root_digest, envelope.ctrl_id, (envelope.action,), envelope.expires_at_ms)

    def test_new_thread_sequence_uses_real_cwd_and_authorized_input(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Materialize one authorized lane.")
        envelope = HQCommandEnvelope("hq-new", "key-new", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100, task_creation={"independent_host_task": True})
        transport = FakeCodexTransport()
        connector = self.connector(transport, material)
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory))
            result = connector.execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            retained = ledger.replay()["connector_receipts"]["key-new"]["receipts"][-1]
            unavailable = UnavailableHQMaterialResolver()
            restarted = UniversalHQConnector(
                CodexAppServerAdapter(transport=transport),
                authorization_verifier=FakeHQAuthorizationVerifier(False),
                material_resolver=unavailable,
                root_verifier=FakeHQRootVerifier(accepted=False),
            )
            replay = restarted.execute(envelope, self.explicit(envelope), Ledger(Path(directory)), now_ms=101, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual((result.status, result.thread_id, result.turn_id), ("RESULT", "thread-1", "turn-1"))
            self.assertEqual(
                (replay.status, replay.command_digest, replay.thread_id, replay.turn_id, replay.observed_root_digest),
                ("REPLAY", retained["command_digest"], retained["thread_id"], retained["turn_id"], retained["observed_root_digest"]),
            )
            self.assertEqual(transport.calls, [
                ("thread/start", {"cwd": material.cwd}),
                ("turn/start", {"threadId": "thread-1", "input": material.input_items(), "cwd": material.cwd}),
            ])
            self.assertEqual(transport.reconcile_calls, [])
            self.assertEqual(unavailable.calls, [])
            replayed = Ledger(Path(directory)).replay()
            self.assertNotIn(material.instruction, repr(replayed))
            self.assertEqual([item["status"] for item in replayed["connector_receipts"]["key-new"]["receipts"]], ["COMMAND", "ACKNOWLEDGED", "RESULT"])
            self.assertEqual(ledger.project_task_creation_bindings()["bindings"], [])

    def test_bound_new_thread_creation_is_digest_immutable_and_reconciles_once(self) -> None:
        import tempfile
        from pathlib import Path
        repository = Path(__file__).resolve().parents[3]
        role = next(item for item in load_builtin_role_manifests(
            repository / "skills" / "swarm" / "roles",
            repository / "skills" / "swarm" / "assets" / "role-avatars",
        ) if item["id"] == "developer")
        task = build_task_manifest(
            manifest_id="task-manifest:pending", task_id="discarded-after-validation", task_name="Bound task",
            project_id="project-a", ctrl_id="ctrl-a",
        )
        task_draft = {key: value for key, value in task.items() if key not in {"task_id", "manifest_digest"}}
        contract = {
            "role_manifest": role, "task_manifest_draft": task_draft, "parent_task_id": None,
            "topology_manifest_receipt_id": "topology-receipt", "task_receipt_id": "task-receipt",
            "milestone_receipts": [], "block_receipts": [],
            "explicit_empty_work_receipt_id": "explicit-empty-receipt", "independent_host_task": False,
        }
        material = HQDispatchMaterial("C:/work/project-a", b"Create one role-bound task.")
        envelope = HQCommandEnvelope(
            "hq-bound", "key-bound", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64,
            "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100,
            task_creation=contract,
        )
        retained_digest = envelope.digest
        contract["task_manifest_draft"]["task_name"] = "Caller mutation"
        contract["role_manifest"]["id"] = "wrong"
        self.assertEqual(envelope.digest, retained_digest)
        self.assertEqual(envelope.task_creation_contract()["task_manifest_draft"]["task_name"], "Bound task")

        transport = FakeCodexTransport([
            {"threadId": "thread-unpredictable-9", "cwd": "C:/work/project-a"},
            {"threadId": "thread-unpredictable-9"},
        ], reconciliations=[{"threadId": "thread-unpredictable-9", "turnId": "turn-1", "cwd": "C:/work/project-a"}])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root)
            first = self.connector(transport, material).execute(
                envelope, self.explicit(envelope), ledger, now_ms=2,
                observed_project_id="project-a", observed_root_digest="a" * 64,
            )
            self.assertEqual((first.status, first.attention), ("PENDING", "HOST_TURN_OUTCOME_PENDING"))
            self.assertEqual(ledger.project_task_creation_bindings()["bindings"], [])

            changed_contract = envelope.task_creation_contract()
            changed_contract["task_receipt_id"] = "changed-receipt"
            changed = HQCommandEnvelope(
                "hq-bound", "key-bound", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64,
                "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100,
                task_creation=changed_contract,
            )
            with self.assertRaisesRegex(InvariantError, "reservation conflicts"):
                self.connector(transport, material).execute(
                    changed, self.explicit(changed), Ledger(root), now_ms=3,
                    observed_project_id="project-a", observed_root_digest="a" * 64,
                )
            self.assertEqual(Ledger(root).project_task_creation_bindings()["bindings"], [])

            restarted = UniversalHQConnector(
                CodexAppServerAdapter(transport=transport),
                authorization_verifier=FakeHQAuthorizationVerifier(False),
                material_resolver=UnavailableHQMaterialResolver(), root_verifier=FakeHQRootVerifier(),
            )
            completed = restarted.execute(
                envelope, self.explicit(envelope), Ledger(root), now_ms=3,
                observed_project_id="project-a", observed_root_digest="a" * 64,
            )
            self.assertEqual((completed.status, completed.thread_id), ("RESULT", "thread-unpredictable-9"))
            replay = restarted.execute(
                envelope, self.explicit(envelope), Ledger(root), now_ms=4,
                observed_project_id="project-a", observed_root_digest="a" * 64,
            )
            self.assertEqual(replay.status, "REPLAY")
            projection = Ledger(root).project_task_creation_bindings("project-a")
            self.assertEqual(len(projection["bindings"]), 1)
            self.assertEqual(projection["bindings"][0]["task_id"], "thread-unpredictable-9")
            persisted_task = Ledger(root).project_identity_manifests(
                "project-a", "ctrl-a", load_builtin_role_manifests(
                    repository / "skills" / "swarm" / "roles",
                    repository / "skills" / "swarm" / "assets" / "role-avatars",
                ),
            )["tasks"][0]["manifest"]
            self.assertEqual(persisted_task["task_id"], "thread-unpredictable-9")
            self.assertNotIn("discarded-after-validation", (root / "swarm" / "progress-ledger.jsonl").read_text(encoding="utf-8"))
            self.assertEqual([item["status"] for item in Ledger(root).replay()["connector_receipts"]["key-bound"]["receipts"]], ["COMMAND", "ACKNOWLEDGED", "RESULT"])

        for action, intent in (
            (HQCommandAction.TASK, HQTargetIntent.EXISTING_THREAD),
            (HQCommandAction.AUTO, HQTargetIntent.EXISTING_THREAD),
            (HQCommandAction.LOCAL_HQ, HQTargetIntent.LOCAL),
        ):
            with self.subTest(action=action), self.assertRaisesRegex(InvariantError, "creation contract"):
                HQCommandEnvelope(
                    f"bad-{action.value}", f"bad-key-{action.value}", action, "project-a", "a" * 64,
                    "ctrl-a" if action is not HQCommandAction.LOCAL_HQ else "", intent,
                    "thread-1" if intent is HQTargetIntent.EXISTING_THREAD else "", material.digest,
                    0, 1, 100, task_creation={"independent_host_task": True},
                )
        with self.assertRaisesRegex(InvariantError, "requires one explicit"):
            HQCommandEnvelope(
                "missing", "missing-key", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64,
                "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100,
            )
        prebound = envelope.task_creation_contract()
        prebound["task_manifest_draft"]["task_id"] = "caller-guessed-host-id"
        with self.assertRaisesRegex(InvariantError, "canonical JSON"):
            HQCommandEnvelope(
                "prebound", "prebound-key", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64,
                "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100,
                task_creation=prebound,
            )

    def test_thread_start_response_cannot_fabricate_turn_completion(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Start a thread before a turn.")
        envelope = HQCommandEnvelope("hq-thread-only", "key-thread-only", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100, task_creation={"independent_host_task": True})
        transport = FakeCodexTransport([{"threadId": "thread-1", "turnId": "turn-fabricated", "cwd": "C:/work/project-a"}])
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory))
            result = self.connector(transport, material).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual((result.status, result.attention), ("PENDING", "HOST_THREAD_OUTCOME_PENDING"))
            self.assertEqual(tuple(call[0] for call in transport.calls), ("thread/start",))
            self.assertEqual([item["status"] for item in ledger.replay()["connector_receipts"]["key-thread-only"]["receipts"]], ["COMMAND"])

    def test_existing_task_resumes_then_starts_turn_and_repair_steers(self) -> None:
        import tempfile
        from pathlib import Path
        for action, methods in ((HQCommandAction.AUTO, ("thread/resume", "turn/start")), (HQCommandAction.TASK, ("thread/resume", "turn/start")), (HQCommandAction.REPAIR, ("thread/resume", "turn/steer"))):
            material = HQDispatchMaterial("C:/work/project-a", f"Execute {action.value}.".encode())
            envelope = HQCommandEnvelope(f"hq-{action.value}", f"key-{action.value}", action, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100, target_turn_id="turn-active" if action is HQCommandAction.REPAIR else "")
            transport = FakeCodexTransport()
            authorization = HQAutoGrant("grant-existing", "project-a", "a" * 64, "ctrl-a", (HQCommandAction.AUTO,), 100) if action is HQCommandAction.AUTO else self.explicit(envelope)
            with tempfile.TemporaryDirectory() as directory:
                result = self.connector(transport, material).execute(envelope, authorization, Ledger(Path(directory)), now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual(result.status, "RESULT")
            self.assertEqual(tuple(call[0] for call in transport.calls), methods)
            self.assertEqual(transport.calls[-1][1]["input"], material.input_items())
            if action is HQCommandAction.REPAIR:
                self.assertEqual(transport.calls[-1][1], {"threadId": "thread-1", "expectedTurnId": "turn-active", "input": material.input_items()})

    def test_dispatch_material_and_host_authorization_fail_before_reservation(self) -> None:
        import tempfile
        from pathlib import Path
        authorized = HQDispatchMaterial("C:/work/project-a", b"Authorized input")
        supplied = HQDispatchMaterial("C:/work/project-a", b"Different input")
        envelope = HQCommandEnvelope("hq-guard", "key-guard", HQCommandAction.TASK, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", authorized.digest, 0, 1, 100)
        for material, verified in ((supplied, True), (authorized, False)):
            transport = FakeCodexTransport()
            with tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(Path(directory))
                with self.assertRaises(InvariantError):
                    self.connector(transport, material, verified=verified).execute(envelope, self.explicit(envelope), ledger, now_ms=1, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual((transport.calls, transport.reconcile_calls), ([], []))
                self.assertFalse((Path(directory) / ".swarm" / "progress-events.jsonl").exists())

    def test_dispatch_cwd_requires_host_observed_canonical_root_before_reservation(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Bind the canonical workspace root.")
        envelope = HQCommandEnvelope("hq-root", "key-root", HQCommandAction.TASK, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100)
        verifiers = (
            FakeHQRootVerifier(canonical_cwd="C:/work/other"),
            FakeHQRootVerifier(root_digest="b" * 64),
            FakeHQRootVerifier(accepted=False),
        )
        for verifier in verifiers:
            transport = FakeCodexTransport()
            with tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(Path(directory))
                with self.assertRaisesRegex(InvariantError, "authorized canonical root"):
                    self.connector(transport, material, root_verifier=verifier).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual(transport.calls, [])
                self.assertFalse((Path(directory) / ".swarm" / "progress-events.jsonl").exists())

    def test_host_identity_aliases_types_and_repair_target_fail_without_false_result(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Reject conflicting host identity.")
        cases = (
            (
                HQCommandEnvelope("hq-alias", "key-alias", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100, task_creation={"independent_host_task": True}),
                [{"threadId": "thread-1", "thread": {"id": "thread-2"}, "cwd": "C:/work/project-a"}],
                ["COMMAND"],
            ),
            (
                HQCommandEnvelope("hq-type", "key-type", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100, task_creation={"independent_host_task": True}),
                [{"thread": {"id": 7}, "cwd": "C:/work/project-a"}],
                ["COMMAND"],
            ),
            (
                HQCommandEnvelope("hq-turn-alias", "key-turn-alias", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 100, task_creation={"independent_host_task": True}),
                [{"thread": {"id": "thread-1"}, "cwd": "C:/work/project-a"}, {"turnId": "turn-1", "turn": {"id": "turn-2"}}],
                ["COMMAND", "ACKNOWLEDGED"],
            ),
            (
                HQCommandEnvelope("hq-repair-target", "key-repair-target", HQCommandAction.REPAIR, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100, target_turn_id="turn-active"),
                [{"threadId": "thread-1", "cwd": "C:/work/project-a"}, {"turnId": "turn-other"}],
                ["COMMAND", "ACKNOWLEDGED"],
            ),
        )
        for envelope, responses, expected_statuses in cases:
            with self.subTest(command=envelope.command_id), tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(Path(directory))
                result = self.connector(FakeCodexTransport(responses), material).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual(result.status, "PENDING")
                receipts = ledger.replay()["connector_receipts"][envelope.idempotency_key]["receipts"]
                self.assertEqual([item["status"] for item in receipts], expected_statuses)
                self.assertNotIn("RESULT", [item["status"] for item in receipts])

    def test_thread_response_cwd_is_required_root_bound_and_conflict_free(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Bind the returned host thread root.")
        envelope = HQCommandEnvelope("hq-thread-root", "key-thread-root", HQCommandAction.TASK, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100)
        invalid = (
            {"threadId": "thread-1"},
            {"threadId": "thread-1", "cwd": "C:/work/other"},
            {"cwd": "C:/work/project-a", "thread": {"id": "thread-1", "cwd": "C:/work/other"}},
            {"threadId": "thread-1", "cwd": 7},
        )
        for response in invalid:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(Path(directory))
                transport = FakeCodexTransport([response])
                result = self.connector(transport, material).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual((result.status, result.attention), ("PENDING", "HOST_THREAD_OUTCOME_PENDING"))
                self.assertEqual(tuple(call[0] for call in transport.calls), ("thread/resume",))
                self.assertEqual([item["status"] for item in ledger.replay()["connector_receipts"]["key-thread-root"]["receipts"]], ["COMMAND"])
        with tempfile.TemporaryDirectory() as directory:
            nested = FakeCodexTransport([
                {"thread": {"id": "thread-1", "cwd": "C:/work/project-a"}},
                {"turn": {"id": "turn-1"}},
            ])
            result = self.connector(nested, material).execute(envelope, self.explicit(envelope), Ledger(Path(directory)), now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual(result.status, "RESULT")

    def test_reconcile_and_repair_require_root_bound_host_thread_without_false_result(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Reconcile only a root-bound thread.")
        for index, reconciliation in enumerate((
            {"threadId": "thread-1", "turnId": "turn-1"},
            {"threadId": "thread-1", "turnId": "turn-1", "cwd": "C:/work/other"},
            {"threadId": "thread-1", "turnId": "turn-1", "cwd": "C:/work/project-a", "thread": {"id": "thread-1", "cwd": "C:/work/other"}},
        )):
            envelope = HQCommandEnvelope(f"hq-reconcile-root-{index}", f"key-reconcile-root-{index}", HQCommandAction.TASK, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100)
            transport = FakeCodexTransport([{"threadId": "thread-1"}], reconciliations=[reconciliation])
            with self.subTest(reconciliation=reconciliation), tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(Path(directory))
                first = self.connector(transport, material).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual(first.status, "PENDING")
                replay = self.connector(transport, material).execute(envelope, self.explicit(envelope), Ledger(Path(directory)), now_ms=3, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual(replay.status, "ATTENTION")
                receipts = Ledger(Path(directory)).replay()["connector_receipts"][envelope.idempotency_key]["receipts"]
                self.assertEqual([item["status"] for item in receipts], ["COMMAND"])
        repair = HQCommandEnvelope("hq-repair-root", "key-repair-root", HQCommandAction.REPAIR, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100, target_turn_id="turn-active")
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory))
            transport = FakeCodexTransport([{"threadId": "thread-1", "cwd": "C:/work/other"}])
            result = self.connector(transport, material).execute(repair, self.explicit(repair), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual((result.status, result.attention), ("PENDING", "HOST_THREAD_OUTCOME_PENDING"))
            self.assertEqual(tuple(call[0] for call in transport.calls), ("thread/resume",))
            self.assertEqual([item["status"] for item in ledger.replay()["connector_receipts"]["key-repair-root"]["receipts"]], ["COMMAND"])

    def test_repair_reconciliation_requires_the_exact_target_turn_before_ack(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Reconcile the exact active repair turn.")
        cases = (
            ({"threadId": "thread-1", "cwd": "C:/work/project-a"}, "ATTENTION", ["COMMAND"]),
            ({"threadId": "thread-1", "turnId": "turn-other", "cwd": "C:/work/project-a"}, "ATTENTION", ["COMMAND"]),
            ({"threadId": "thread-1", "turnId": "turn-active", "cwd": "C:/work/project-a"}, "RESULT", ["COMMAND", "ACKNOWLEDGED", "RESULT"]),
        )
        for index, (reconciliation, expected_status, expected_receipts) in enumerate(cases):
            envelope = HQCommandEnvelope(f"hq-repair-reconcile-{index}", f"key-repair-reconcile-{index}", HQCommandAction.REPAIR, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100, target_turn_id="turn-active")
            transport = FakeCodexTransport([{"threadId": "thread-1"}], reconciliations=[reconciliation])
            with self.subTest(reconciliation=reconciliation), tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(Path(directory))
                first = self.connector(transport, material).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual(first.status, "PENDING")
                replay = self.connector(transport, material).execute(envelope, self.explicit(envelope), Ledger(Path(directory)), now_ms=3, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual(replay.status, expected_status)
                receipts = Ledger(Path(directory)).replay()["connector_receipts"][envelope.idempotency_key]["receipts"]
                self.assertEqual([item["status"] for item in receipts], expected_receipts)
                if expected_status == "RESULT":
                    self.assertEqual((replay.thread_id, replay.turn_id), ("thread-1", "turn-active"))

    def test_authorization_is_host_verified_scoped_and_has_no_public_minter(self) -> None:
        import tempfile
        from pathlib import Path
        import skills.swarm.runtime as runtime
        self.assertFalse(hasattr(runtime, "host_hq_authorization"))
        material = HQDispatchMaterial("C:/work/project-a", b"Verify exact authority.")
        self.assertNotIn(material.instruction, repr(material))
        envelope = HQCommandEnvelope("hq-auth", "key-auth", HQCommandAction.TASK, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 10)
        valid = self.explicit(envelope)
        invalid = (
            replace(valid, project_id="project-b"),
            replace(valid, root_digest="c" * 64),
            replace(valid, ctrl_id="ctrl-b"),
            replace(valid, expires_at_ms=1),
        )
        for receipt in invalid:
            transport = FakeCodexTransport()
            resolver = FakeHQMaterialResolver(material)
            connector = UniversalHQConnector(CodexAppServerAdapter(transport=transport), authorization_verifier=FakeHQAuthorizationVerifier(), material_resolver=resolver, root_verifier=FakeHQRootVerifier())
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(InvariantError):
                    connector.execute(envelope, receipt, Ledger(Path(directory)), now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
                self.assertEqual((transport.calls, resolver.calls), ([], []))

    def test_auto_grant_is_scoped_reusable_authorization_only_for_auto(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Continue automatically.")
        envelope = HQCommandEnvelope("hq-auto", "key-auto", HQCommandAction.AUTO, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100)
        grant = HQAutoGrant("grant-1", "project-a", "a" * 64, "ctrl-a", (HQCommandAction.AUTO,), 100)
        with tempfile.TemporaryDirectory() as directory:
            result = self.connector(FakeCodexTransport(), material).execute(envelope, grant, Ledger(Path(directory)), now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual(result.status, "RESULT")
        wrong = replace(envelope, project_id="project-b")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(InvariantError, "scope conflicts"):
                self.connector(FakeCodexTransport(), material).execute(wrong, grant, Ledger(Path(directory)), now_ms=2, observed_project_id="project-b", observed_root_digest="a" * 64)

    def test_disabled_and_local_paths_never_call_codex_transport(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Bounded command")
        for action, intent, thread, expected in ((HQCommandAction.TASK, HQTargetIntent.EXISTING_THREAD, "thread-1", "UNSUPPORTED"), (HQCommandAction.LOCAL_HQ, HQTargetIntent.LOCAL, "", "LOCAL_PLAN")):
            envelope = HQCommandEnvelope(f"hq-{action.value}", f"key-{action.value}", action, "project-a", "a" * 64, "ctrl-a" if action is not HQCommandAction.LOCAL_HQ else "", intent, thread, material.digest, 0, 1, 100)
            transport = FakeCodexTransport()
            with tempfile.TemporaryDirectory() as directory:
                result = self.connector(transport, material, enabled=False).execute(envelope, self.explicit(envelope), Ledger(Path(directory)), now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual(result.status, expected)
            self.assertEqual((transport.calls, transport.reconcile_calls), ([], []))

    def test_ambiguous_turn_is_pending_and_restart_reconciles_without_redispatch(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Start then reconcile.")
        envelope = HQCommandEnvelope("hq-pending", "key-pending", HQCommandAction.MANUAL_AGENT, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.NEW_THREAD, "", material.digest, 0, 1, 2, task_creation={"independent_host_task": True})
        transport = FakeCodexTransport([
            {"thread": {"id": "thread-1"}, "cwd": "C:/work/project-a"},
            {"threadId": "thread-1"},
        ], reconciliations=[{"threadId": "thread-1", "turnId": "turn-9", "cwd": "C:/work/project-a"}])
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory))
            first = self.connector(transport, material).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual((first.status, first.attention), ("PENDING", "HOST_TURN_OUTCOME_PENDING"))
            restarted = Ledger(Path(directory))
            unavailable = UnavailableHQMaterialResolver()
            restarted_connector = UniversalHQConnector(
                CodexAppServerAdapter(transport=transport),
                authorization_verifier=FakeHQAuthorizationVerifier(False),
                material_resolver=unavailable,
                root_verifier=FakeHQRootVerifier(),
            )
            second = restarted_connector.execute(envelope, self.explicit(envelope), restarted, now_ms=3, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual((second.status, second.turn_id), ("RESULT", "turn-9"))
            self.assertEqual(tuple(call[0] for call in transport.calls), ("thread/start", "turn/start"))
            self.assertEqual(transport.reconcile_calls, [("hq-pending", "MANUAL_AGENT", "thread-1")])
            self.assertEqual(unavailable.calls, [])
            self.assertEqual([item["status"] for item in restarted.replay()["connector_receipts"]["key-pending"]["receipts"]], ["COMMAND", "ACKNOWLEDGED", "RESULT"])

    def test_retained_command_reconciliation_rejects_changed_binding_without_material(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Retain exact command identity.")
        envelope = HQCommandEnvelope("hq-retained", "key-retained", HQCommandAction.TASK, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 2)
        transport = FakeCodexTransport([
            {"threadId": "thread-1", "cwd": "C:/work/project-a"},
            {"threadId": "thread-1"},
        ])
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory))
            first = self.connector(transport, material).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual(first.status, "PENDING")
            before = ledger.replay()["cursor"]
            unavailable = UnavailableHQMaterialResolver()
            restarted = UniversalHQConnector(
                CodexAppServerAdapter(transport=transport),
                authorization_verifier=FakeHQAuthorizationVerifier(False),
                material_resolver=unavailable,
                root_verifier=FakeHQRootVerifier(accepted=False),
            )
            changed = replace(envelope, payload_digest="b" * 64)
            with self.assertRaisesRegex(InvariantError, "reservation conflicts"):
                restarted.execute(changed, self.explicit(envelope), Ledger(Path(directory)), now_ms=3, observed_project_id="project-a", observed_root_digest="a" * 64)
            with self.assertRaisesRegex(InvariantError, "observed project root conflicts"):
                restarted.execute(envelope, self.explicit(envelope), Ledger(Path(directory)), now_ms=3, observed_project_id="project-a", observed_root_digest="b" * 64)
            changed_key = replace(envelope, idempotency_key="key-other")
            with self.assertRaisesRegex(InvariantError, "authorization expired"):
                restarted.execute(changed_key, self.explicit(changed_key), Ledger(Path(directory)), now_ms=3, observed_project_id="project-a", observed_root_digest="a" * 64)
            after = Ledger(Path(directory)).replay()
            self.assertEqual(after["cursor"], before)
            self.assertEqual(set(after["connector_receipts"]), {"key-retained"})
            self.assertEqual(unavailable.calls, [])
            self.assertEqual(len(transport.calls), 2)

    def test_atomic_replay_race_reconciles_without_duplicate_dispatch(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Race one exact reservation.")
        envelope = HQCommandEnvelope("hq-race", "key-race", HQCommandAction.TASK, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100)
        transport = FakeCodexTransport(reconciliations=[{"threadId": "thread-1", "turnId": "turn-race", "cwd": "C:/work/project-a"}])
        with tempfile.TemporaryDirectory() as directory:
            retained = Ledger(Path(directory))

            class RacingLedger:
                raced = False

                def replay(self):
                    return retained.replay()

                def reserve_connector_command(self, command, *, expected_revision):
                    if not self.raced:
                        self.raced = True
                        retained.reserve_connector_command(command, expected_revision=expected_revision)
                    return retained.reserve_connector_command(command, expected_revision=expected_revision)

                def append_connector_receipt(self, receipt):
                    return retained.append_connector_receipt(receipt)

            result = self.connector(transport, material).execute(envelope, self.explicit(envelope), RacingLedger(), now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual((result.status, result.turn_id), ("RESULT", "turn-race"))
            self.assertEqual(transport.calls, [])
            self.assertEqual(transport.reconcile_calls, [("hq-race", "TASK", "thread-1")])
            self.assertEqual([item["status"] for item in retained.replay()["connector_receipts"]["key-race"]["receipts"]], ["COMMAND", "ACKNOWLEDGED", "RESULT"])

    def test_unreconciled_or_conflicting_host_response_stays_non_success(self) -> None:
        import tempfile
        from pathlib import Path
        material = HQDispatchMaterial("C:/work/project-a", b"Remain truthful.")
        envelope = HQCommandEnvelope("hq-truth", "key-truth", HQCommandAction.TASK, "project-a", "a" * 64, "ctrl-a", HQTargetIntent.EXISTING_THREAD, "thread-1", material.digest, 0, 1, 100)
        transport = FakeCodexTransport([{"threadId": "thread-other"}])
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory))
            result = self.connector(transport, material).execute(envelope, self.explicit(envelope), ledger, now_ms=2, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual(result.status, "PENDING")
            self.assertEqual([item["status"] for item in ledger.replay()["connector_receipts"]["key-truth"]["receipts"]], ["COMMAND"])
            replay = self.connector(transport, material).execute(envelope, self.explicit(envelope), Ledger(Path(directory)), now_ms=3, observed_project_id="project-a", observed_root_digest="a" * 64)
            self.assertEqual((replay.status, replay.attention), ("PENDING", "HOST_OUTCOME_PENDING"))
            self.assertEqual(len(transport.calls), 1)


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
