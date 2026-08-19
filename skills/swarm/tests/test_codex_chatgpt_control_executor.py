from __future__ import annotations

from types import SimpleNamespace
import unittest

from skills.swarm.runtime import (
    ChatExecutorCapability,
    ChatExecutorCommandMode,
    ChatExecutorTransportError,
    ChatExecutorWriteMode,
    ChatGPTBridgeTransport,
    CodexChatGPTControlExecutor,
)


class FakeRunner:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[object, dict[str, object]]] = []

    def run_sync(self, agent: object, request: dict[str, object]) -> object:
        self.calls.append((agent, request))
        return self.result


class CodexChatGPTControlExecutorTests(unittest.TestCase):
    def capability(self) -> ChatExecutorCapability:
        return ChatExecutorCapability(
            connected=True,
            provider="cccc",
            actor_id="cccc-local",
            transport=ChatGPTBridgeTransport.REMOTE_MCP,
            receipt="capability-receipt",
            workspace_scope="C:/workspace/project",
            read_tools=True,
            write_tools=True,
            command_tools=True,
            artifact_tools=True,
            user_confirmed=True,
            observed_model="Pro",
            observed_effort="Pro",
        )

    def test_executor_maps_external_run_to_swarm_receipt_and_usage(self) -> None:
        runner = FakeRunner(SimpleNamespace(
            output_text="implemented and tested",
            run_id="run-executor-1",
            changed_paths=["src/app.ts"],
            client_thread_id="client-1",
            thread_id="thread-1",
            request_id="request-1",
            response_id="response-1",
            assets=[{"id": "asset-1"}],
            model="pro",
            usage=SimpleNamespace(input_tokens=120, output_tokens=80, total_tokens=200),
            latency_ms=42,
        ))
        executor = CodexChatGPTControlExecutor(
            capability_reader=self.capability,
            runner=runner,
            agent_factory=lambda **values: values,
            tool_builder=lambda tools: [{"tool": name} for name in sorted(tools)],
        )

        response = executor.execute_task(
            "SWARM task envelope",
            model="pro",
            effort="pro",
            write_mode=ChatExecutorWriteMode.WORKSPACE,
            command_mode=ChatExecutorCommandMode.SAFE,
        )

        self.assertEqual(response.text, "implemented and tested")
        self.assertEqual(response.host_receipt, "run-executor-1")
        self.assertEqual(response.changed_paths, ("src/app.ts",))
        self.assertEqual(response.transport.asset_ids, ("asset-1",))
        self.assertEqual(response.transport.total_tokens, 200)
        self.assertEqual(response.transport.latency_source, "provider_reported")
        agent, request = runner.calls[0]
        self.assertIn("provider-advertised tools", agent["instructions"])
        self.assertEqual(len(request["tools"]), 4)
        self.assertNotIn("configuration", request)

    def test_executor_rejects_an_unreceipted_provider_result(self) -> None:
        runner = FakeRunner(SimpleNamespace(output_text="changed something"))
        executor = CodexChatGPTControlExecutor(
            capability_reader=self.capability,
            runner=runner,
            agent_factory=lambda **values: values,
        )

        with self.assertRaises(ChatExecutorTransportError):
            executor.execute_task(
                "SWARM task envelope",
                model="pro",
                effort="pro",
                write_mode=ChatExecutorWriteMode.WORKSPACE,
                command_mode=ChatExecutorCommandMode.SAFE,
            )


if __name__ == "__main__":
    unittest.main()
