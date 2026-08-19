from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skills.swarm.runtime.chat_executor import (
    ChatExecutorBlocker,
    ChatExecutorCapability,
    ChatExecutorCommandMode,
    ChatExecutorPolicy,
    ChatExecutorRequest,
    ChatExecutorResponse,
    ChatExecutorRoute,
    ChatExecutorWriteMode,
    choose_chat_executor,
    execute_chat_task,
)
from skills.swarm.runtime.chat_relay import (
    ChatRelayContextPacket,
    ChatRelayOffloadLevel,
    ChatRelayPolicy,
    ChatRelayPurpose,
    build_chat_relay_context,
)


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
        return ChatExecutorResponse(
            text="host completed the bounded task",
            host_receipt="mcp-execution-receipt",
            observed_model=self.host.observed_model,
            observed_effort=self.host.observed_effort,
            changed_paths=("src/app.ts",),
        )


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

    def test_mutating_and_command_work_requires_max_and_reported_tools(self) -> None:
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
        self.assertIs(high.blocker, ChatExecutorBlocker.OFFLOAD_LEVEL_SELECTION)
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
