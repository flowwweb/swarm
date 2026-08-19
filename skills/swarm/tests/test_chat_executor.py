from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skills.swarm.runtime.chat_executor import (
    ChatGPTBridgeRegistry,
    ChatGPTBridgeManifest,
    ChatGPTBridgeTransport,
    ChatExecutorBlocker,
    ChatExecutorCapability,
    ChatExecutorCommandMode,
    ChatExecutorPolicy,
    ChatExecutorRequest,
    ChatExecutorResponse,
    ChatExecutorRoute,
    ChatExecutorWorkspaceLocation,
    ChatExecutorWriteMode,
    choose_chat_executor,
    execute_chat_task,
)
from skills.swarm.runtime.chat_relay import (
    ChatRelayContextPacket,
    ChatRelayOffloadLevel,
    ChatRelayPolicy,
    ChatRelayPurpose,
    ChatRelayTransportReceipt,
    build_chat_relay_context,
)
from skills.swarm.runtime.core import Swarm


def executor_request(**changes: object) -> ChatExecutorRequest:
    values: dict[str, object] = {
        "purpose": ChatRelayPurpose.TESTING,
        "consequence_tier": "T1",
        "prompt_digest": sha256(b"local MCP task").hexdigest(),
        "local_boundary": True,
    }
    values.update(changes)
    return ChatExecutorRequest(**values)  # type: ignore[arg-type]


def executor_capability(**changes: object) -> ChatExecutorCapability:
    values: dict[str, object] = {
        "connected": True,
        "provider": "cccc",
        "receipt": "mcp-capability-receipt",
        "workspace_scope": "C:/workspace/project",
        "read_tools": True,
        "write_tools": True,
        "command_tools": True,
        "artifact_tools": True,
        "user_confirmed": True,
        "observed_model": "GPT-5.6 Luna",
        "observed_effort": "Extra High",
    }
    values.update(changes)
    return ChatExecutorCapability(**values)  # type: ignore[arg-type]


class FakeExecutor:
    def __init__(self, capability: ChatExecutorCapability) -> None:
        self.host = capability
        self.sent: list[str] = []
        self.selections: list[tuple[str, str, ChatExecutorWriteMode, ChatExecutorCommandMode]] = []
        self.response = ChatExecutorResponse(
            text="host completed the bounded task",
            host_receipt="mcp-execution-receipt",
            observed_model=self.host.observed_model,
            observed_effort=self.host.observed_effort,
            changed_paths=("src/app.ts",),
        )

    def capability(self) -> ChatExecutorCapability:
        return self.host

    def execute_task(
        self,
        prompt: str,
        *,
        model: str,
        effort: str,
        write_mode: ChatExecutorWriteMode,
        command_mode: ChatExecutorCommandMode,
    ) -> ChatExecutorResponse:
        self.sent.append(prompt)
        self.selections.append((model, effort, write_mode, command_mode))
        return self.response


class ChatExecutorTests(unittest.TestCase):
    def test_executor_is_disabled_and_cannot_be_used_by_default(self) -> None:
        decision = choose_chat_executor(
            policy=ChatExecutorPolicy(),
            relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
            request=executor_request(write_intent=True),
            capability=executor_capability(),
        )
        self.assertIs(decision.route, ChatExecutorRoute.LOCAL_CODEX)
        self.assertIs(decision.blocker, ChatExecutorBlocker.DISABLED)

    def test_executor_requires_a_local_boundary_and_exact_scope(self) -> None:
        policy = ChatExecutorPolicy(enabled=True)
        relay = ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX)
        no_boundary = choose_chat_executor(
            policy=policy,
            relay_policy=relay,
            request=executor_request(local_boundary=False),
            capability=executor_capability(),
        )
        self.assertIs(no_boundary.blocker, ChatExecutorBlocker.LOCAL_BOUNDARY_REQUIRED)
        no_scope = choose_chat_executor(
            policy=policy,
            relay_policy=relay,
            request=executor_request(),
            capability=executor_capability(workspace_scope=""),
        )
        self.assertIs(no_scope.blocker, ChatExecutorBlocker.WORKSPACE_SCOPE_REQUIRED)

    def test_read_only_executor_cannot_edit_or_run_commands(self) -> None:
        policy = ChatExecutorPolicy(enabled=True)
        relay = ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX)
        write = choose_chat_executor(
            policy=policy,
            relay_policy=relay,
            request=executor_request(write_intent=True),
            capability=executor_capability(),
        )
        self.assertIs(write.route, ChatExecutorRoute.LOCAL_CODEX)
        self.assertIs(write.blocker, ChatExecutorBlocker.WRITE_CAPABILITY_REQUIRED)
        command = choose_chat_executor(
            policy=ChatExecutorPolicy(enabled=True),
            relay_policy=relay,
            request=executor_request(command_intent=True),
            capability=executor_capability(),
        )
        self.assertIs(command.route, ChatExecutorRoute.LOCAL_CODEX)
        self.assertIs(command.blocker, ChatExecutorBlocker.COMMAND_CAPABILITY_REQUIRED)

    def test_mutating_and_command_work_uses_provider_tools_at_selected_level(self) -> None:
        policy = ChatExecutorPolicy(
            enabled=True,
            write_mode=ChatExecutorWriteMode.WORKSPACE,
            command_mode=ChatExecutorCommandMode.SAFE,
        )
        request = executor_request(write_intent=True, command_intent=True)
        high = choose_chat_executor(
            policy=policy,
            relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.HIGH),
            request=request,
            capability=executor_capability(),
        )
        self.assertIs(high.route, ChatExecutorRoute.CHATGPT_MCP)
        missing_tool = choose_chat_executor(
            policy=policy,
            relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
            request=request,
            capability=executor_capability(command_tools=False),
        )
        self.assertIs(missing_tool.blocker, ChatExecutorBlocker.COMMAND_CAPABILITY_REQUIRED)
        allowed = choose_chat_executor(
            policy=policy,
            relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
            request=request,
            capability=executor_capability(),
        )
        self.assertIs(allowed.route, ChatExecutorRoute.CHATGPT_MCP)
        self.assertEqual(allowed.workspace_scope, "C:/workspace/project")

    def test_cloud_actor_can_route_without_a_local_boundary(self) -> None:
        policy = ChatExecutorPolicy(
            enabled=True,
            write_mode=ChatExecutorWriteMode.WORKSPACE,
            command_mode=ChatExecutorCommandMode.SAFE,
            require_confirmation=False,
        )
        request = executor_request(
            local_boundary=False,
            workspace_location=ChatExecutorWorkspaceLocation.CLOUD,
            purpose=ChatRelayPurpose.IMPLEMENTATION,
            write_intent=True,
            command_intent=True,
        )
        decision = choose_chat_executor(
            policy=policy,
            relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
            request=request,
            capability=executor_capability(workspace_location=ChatExecutorWorkspaceLocation.CLOUD),
        )
        self.assertIs(decision.route, ChatExecutorRoute.CHATGPT_MCP)
        self.assertIs(decision.workspace_location, ChatExecutorWorkspaceLocation.CLOUD)

    def test_cloud_request_rejects_a_local_actor(self) -> None:
        request = executor_request(
            local_boundary=False,
            workspace_location=ChatExecutorWorkspaceLocation.CLOUD,
        )
        decision = choose_chat_executor(
            policy=ChatExecutorPolicy(enabled=True),
            relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
            request=request,
            capability=executor_capability(),
        )
        self.assertIs(decision.route, ChatExecutorRoute.LOCAL_CODEX)
        self.assertIs(decision.blocker, ChatExecutorBlocker.WORKSPACE_LOCATION_REQUIRED)

    def test_cloud_task_envelope_preserves_remote_location(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "brief.md").write_text("cloud task", encoding="utf-8")
            context = build_chat_relay_context(repo_root=root, objective="cloud task", relative_paths=("brief.md",))
            adapter = FakeExecutor(executor_capability(workspace_location=ChatExecutorWorkspaceLocation.CLOUD))
            result = execute_chat_task(
                policy=ChatExecutorPolicy(enabled=True, require_confirmation=False),
                relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
                request=executor_request(
                    local_boundary=False,
                    workspace_location=ChatExecutorWorkspaceLocation.CLOUD,
                    purpose=ChatRelayPurpose.RESEARCH,
                ),
                context=context,
                adapter=adapter,
            )
        self.assertIs(result.decision.route, ChatExecutorRoute.CHATGPT_MCP)
        self.assertIn("WORKSPACE_LOCATION: cloud", adapter.sent[0])
        self.assertIn("REQUESTED_WORKSPACE_LOCATION: cloud", adapter.sent[0])

    def test_max_does_not_make_t4_local(self) -> None:
        policy = ChatExecutorPolicy(
            enabled=True,
            write_mode=ChatExecutorWriteMode.WORKSPACE,
            command_mode=ChatExecutorCommandMode.SAFE,
        )
        decision = choose_chat_executor(
            policy=policy,
            relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
            request=executor_request(consequence_tier="T4", write_intent=True, command_intent=True),
            capability=executor_capability(),
        )
        self.assertIs(decision.route, ChatExecutorRoute.CHATGPT_MCP)

    def test_max_routes_the_full_provider_capability_matrix_and_preserves_receipts(self) -> None:
        policy = ChatExecutorPolicy(
            enabled=True,
            write_mode=ChatExecutorWriteMode.WORKSPACE,
            command_mode=ChatExecutorCommandMode.SAFE,
            require_confirmation=False,
        )
        relay = ChatRelayPolicy(
            enabled=True,
            provider="cccc",
            offload_level=ChatRelayOffloadLevel.MAX,
            challenging_model="pro",
            challenging_effort="pro",
        )
        provider = FakeExecutor(executor_capability(observed_model="Pro", observed_effort="Pro"))
        provider.response = ChatExecutorResponse(
            text="provider completed the requested capability",
            host_receipt="matrix-execution-receipt",
            observed_model="Pro",
            observed_effort="Pro",
            changed_paths=("src/app.ts",),
            transport=ChatRelayTransportReceipt(
                transport="remote_mcp",
                request_id="matrix-request",
                response_id="matrix-response",
                asset_ids=("matrix-asset",),
                model="pro",
                input_tokens=120,
                output_tokens=80,
                total_tokens=200,
                usage_status="reported",
                usage_reason="",
            ),
        )
        matrix = (
            executor_request(purpose=ChatRelayPurpose.RESEARCH, challenging=True),
            executor_request(purpose=ChatRelayPurpose.IMPLEMENTATION, write_intent=True, challenging=True),
            executor_request(purpose=ChatRelayPurpose.COMMAND, command_intent=True, challenging=True),
            executor_request(purpose=ChatRelayPurpose.TESTING, command_intent=True, challenging=True),
            executor_request(purpose=ChatRelayPurpose.IMAGEGEN, artifact_production=True, challenging=True),
            executor_request(
                purpose=ChatRelayPurpose.REVIEW,
                consequence_tier="T4",
                write_intent=True,
                command_intent=True,
                artifact_production=True,
                challenging=True,
            ),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "brief.md").write_text("full capability matrix", encoding="utf-8")
            context = build_chat_relay_context(repo_root=root, objective="matrix", relative_paths=("brief.md",))
            for request in matrix:
                with self.subTest(purpose=request.purpose, tier=request.consequence_tier):
                    result = execute_chat_task(
                        policy=policy,
                        relay_policy=relay,
                        request=request,
                        context=context,
                        adapter=provider,
                    )
                    self.assertIs(result.decision.route, ChatExecutorRoute.CHATGPT_MCP)
                    self.assertIsNotNone(result.response)
                    assert result.response is not None
                    self.assertEqual(result.response.host_receipt, "matrix-execution-receipt")
                    self.assertEqual(result.response.transport.total_tokens, 200)
                    self.assertEqual(result.response.transport.asset_ids, ("matrix-asset",))
        self.assertEqual(len(provider.sent), len(matrix))
        self.assertTrue(all("SWARM_REMAINS_ACCEPTANCE_OWNER: true" in prompt for prompt in provider.sent))

    def test_capability_derives_advertised_tool_names(self) -> None:
        capability = executor_capability(tool_capabilities=frozenset())
        self.assertEqual(
            capability.tool_capabilities,
            frozenset({"workspace.read", "workspace.write", "command.safe", "artifact.create"}),
        )

    def test_registry_can_represent_a_connected_provider_with_no_tools(self) -> None:
        adapter = FakeExecutor(
            executor_capability(
                read_tools=False,
                write_tools=False,
                command_tools=False,
                artifact_tools=False,
                tool_capabilities=frozenset(),
            )
        )
        actor = ChatGPTBridgeRegistry().register(adapter)
        self.assertEqual(actor.tool_capabilities, frozenset())

    def test_registry_exposes_external_provider_as_a_swarm_actor(self) -> None:
        adapter = FakeExecutor(executor_capability(transport=ChatGPTBridgeTransport.BROWSER_DELIVERY))
        registry = ChatGPTBridgeRegistry()
        actor = registry.register(adapter)
        self.assertEqual(actor.actor_id, "cccc")
        self.assertEqual(actor.provider, "cccc")
        self.assertIs(actor.transport, ChatGPTBridgeTransport.BROWSER_DELIVERY)
        self.assertIs(registry.provider(actor.actor_id), adapter)

    def test_registry_persists_and_discovers_credential_free_bridge_manifest(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "chatgpt-bridges.json"
            adapter = FakeExecutor(executor_capability())
            registry = ChatGPTBridgeRegistry(path)
            manifest = ChatGPTBridgeManifest(
                provider_id="cccc",
                actor_id="cccc",
                transport=ChatGPTBridgeTransport.REMOTE_MCP,
                workspace_scope="C:/workspace/project",
                tool_capabilities=frozenset({"workspace.read", "workspace.write", "command.safe"}),
                endpoint="https://bridge.example/mcp",
            )
            registry.register(adapter, manifest=manifest, persist=True)
            stored = path.read_text(encoding="utf-8")
            discovered = ChatGPTBridgeRegistry(path).discover()
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].endpoint, "https://bridge.example/mcp")
        self.assertNotIn("mcp-execution-receipt", stored)
        self.assertNotIn("GPT-5.6", stored)

    def test_registry_persists_cloud_workspace_location(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "chatgpt-bridges.json"
            adapter = FakeExecutor(executor_capability(workspace_location=ChatExecutorWorkspaceLocation.CLOUD))
            registry = ChatGPTBridgeRegistry(path)
            registry.register(adapter, persist=True)
            discovered = ChatGPTBridgeRegistry(path).discover()
        self.assertEqual(discovered[0].workspace_location, ChatExecutorWorkspaceLocation.CLOUD)

    def test_swarm_can_route_through_registered_provider_without_bundling_it(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "brief.md").write_text("route me", encoding="utf-8")
            context = build_chat_relay_context(repo_root=root, objective="route me", relative_paths=("brief.md",))
            adapter = FakeExecutor(executor_capability())
            swarm = Swarm(
                chat_relay_policy=ChatRelayPolicy(
                    enabled=True,
                    provider="cccc",
                    offload_level=ChatRelayOffloadLevel.MAX,
                ),
                chat_executor_policy=ChatExecutorPolicy(
                    enabled=True,
                    write_mode=ChatExecutorWriteMode.WORKSPACE,
                    command_mode=ChatExecutorCommandMode.SAFE,
                ),
            )
            actor = swarm.register_chatgpt_provider(adapter)
            result = swarm.execute_registered_chatgpt_task(
                executor_request(write_intent=True, command_intent=True, task_id="registered-1"),
                context,
                actor_id=actor.actor_id,
            )
        self.assertIs(result.decision.route, ChatExecutorRoute.CHATGPT_MCP)
        self.assertIsNotNone(result.response)

    def test_execution_uses_host_receipt_and_preserves_acceptance_boundary(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "brief.md").write_text("run the bounded test", encoding="utf-8")
            context = build_chat_relay_context(
                repo_root=root,
                objective="run the bounded test",
                relative_paths=("brief.md",),
            )
            adapter = FakeExecutor(executor_capability())
            result = execute_chat_task(
                policy=ChatExecutorPolicy(
                    enabled=True,
                    write_mode=ChatExecutorWriteMode.WORKSPACE,
                    command_mode=ChatExecutorCommandMode.SAFE,
                ),
                relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
                request=executor_request(write_intent=True, command_intent=True, task_id="task-1"),
                context=context,
                adapter=adapter,
            )
        self.assertIs(result.decision.route, ChatExecutorRoute.CHATGPT_MCP)
        self.assertIsNotNone(result.response)
        assert result.response is not None
        self.assertFalse(result.decision.acceptance_authority)
        self.assertFalse(result.response.acceptance_authority)
        self.assertEqual(result.response.host_receipt, "mcp-execution-receipt")
        self.assertEqual(result.response.changed_paths, ("src/app.ts",))
        self.assertIn("ALLOW_WORKSPACE_WRITES: true", adapter.sent[0])
        self.assertIn("ALLOW_SAFE_COMMANDS: true", adapter.sent[0])

    def test_confirmation_callback_covers_the_exact_executor_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "brief.md").write_text("confirm me", encoding="utf-8")
            context = build_chat_relay_context(repo_root=root, objective="confirm", relative_paths=("brief.md",))
            adapter = FakeExecutor(executor_capability(user_confirmed=False))
            confirmations: list[str] = []
            result = execute_chat_task(
                policy=ChatExecutorPolicy(enabled=True, require_confirmation=True),
                relay_policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.HIGH),
                request=executor_request(purpose=ChatRelayPurpose.RESEARCH),
                context=context,
                adapter=adapter,
                confirm=lambda prompt: confirmations.append(prompt) or True,
            )
        self.assertIs(result.decision.route, ChatExecutorRoute.CHATGPT_MCP)
        self.assertEqual(confirmations, adapter.sent)


if __name__ == "__main__":
    unittest.main()
