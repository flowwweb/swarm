from __future__ import annotations

from types import SimpleNamespace
import unittest

from skills.swarm.runtime import ChatRelayCapability, CodexChatGPTControlAdapter


class FakeRunner:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[object, dict[str, object]]] = []

    def run_sync(self, agent: object, request: dict[str, object]) -> object:
        self.calls.append((agent, request))
        return self.result


class CodexChatGPTControlAdapterTests(unittest.TestCase):
    def capability(self) -> ChatRelayCapability:
        return ChatRelayCapability(
            visible_session=True,
            browser_bridge=True,
            user_confirmed=True,
            receipt="visible-session-receipt",
            observed_model="visible-chat-model",
            observed_effort="high",
        )

    def test_injected_runner_uses_visible_chat_and_preserves_receipt(self) -> None:
        runner = FakeRunner(SimpleNamespace(
            output_text="advice",
            run_id="run-123",
            client_thread_id="client-thread-1",
            thread_id="thread-1",
            request_id="request-1",
            response_id="response-1",
            asset_ids=["asset-1"],
            model="gpt-5.6-luna",
            usage=SimpleNamespace(input_tokens=12, output_tokens=5, total_tokens=17),
            latency_ms=23.5,
        ))
        adapter = CodexChatGPTControlAdapter(
            capability_reader=self.capability,
            confirm_prompt=lambda _: True,
            runner=runner,
            agent_factory=lambda **values: values,
        )
        response = adapter.send_consult("bounded prompt", model="gpt-5.6-luna", effort="xhigh")
        self.assertEqual(response.text, "advice")
        self.assertEqual(response.host_receipt, "run-123")
        self.assertEqual(response.transport.client_thread_id, "client-thread-1")
        self.assertEqual(response.transport.request_id, "request-1")
        self.assertEqual(response.transport.response_id, "response-1")
        self.assertEqual(response.transport.asset_ids, ("asset-1",))
        self.assertEqual(response.transport.model, "gpt-5.6-luna")
        self.assertEqual((response.transport.input_tokens, response.transport.output_tokens, response.transport.total_tokens), (12, 5, 17))
        self.assertEqual(response.transport.usage_status, "reported")
        self.assertEqual(response.transport.latency_source, "provider_reported")
        self.assertEqual(runner.calls[0][1]["experience"], "chat")
        self.assertNotIn("configuration", runner.calls[0][1])
        self.assertEqual(runner.calls[0][1]["response"], {"format": "markdown"})

    def test_pro_selection_reuses_the_verified_visible_host_profile(self) -> None:
        runner = FakeRunner(SimpleNamespace(output_text="advice", run_id="run-pro"))
        adapter = CodexChatGPTControlAdapter(
            capability_reader=self.capability,
            confirm_prompt=lambda _: True,
            runner=runner,
            agent_factory=lambda **values: values,
        )
        adapter.send_consult("challenging prompt", model="pro", effort="pro")
        self.assertNotIn("configuration", runner.calls[0][1])

    def test_sol_selection_reuses_the_verified_visible_host_profile(self) -> None:
        runner = FakeRunner(SimpleNamespace(output_text="advice", run_id="run-sol"))
        adapter = CodexChatGPTControlAdapter(
            capability_reader=self.capability,
            confirm_prompt=lambda _: True,
            runner=runner,
            agent_factory=lambda **values: values,
        )
        adapter.send_consult("routine prompt", model="gpt-5.6-sol", effort="xhigh")
        self.assertNotIn("configuration", runner.calls[0][1])

    def test_missing_receipt_fails_closed(self) -> None:
        runner = FakeRunner(SimpleNamespace(output_text="advice"))
        adapter = CodexChatGPTControlAdapter(
            capability_reader=self.capability,
            confirm_prompt=lambda _: True,
            runner=runner,
            agent_factory=lambda **values: values,
        )
        with self.assertRaisesRegex(ValueError, "no host receipt"):
            adapter.send_consult("bounded prompt", model="gpt-5.6-luna", effort="xhigh")

    def test_python_sdk_state_id_is_preserved_as_host_receipt(self) -> None:
        runner = FakeRunner(SimpleNamespace(
            output_text="advice",
            state=SimpleNamespace(id="run-from-state", thread={"id": "thread-from-state"}),
        ))
        adapter = CodexChatGPTControlAdapter(
            capability_reader=self.capability,
            confirm_prompt=lambda _: True,
            runner=runner,
            agent_factory=lambda **values: values,
        )
        response = adapter.send_consult("bounded prompt", model="gpt-5.6-luna", effort="xhigh")
        self.assertEqual(response.host_receipt, "run-from-state")
        self.assertEqual(response.transport.thread_id, "thread-from-state")

    def test_missing_usage_is_not_estimated(self) -> None:
        runner = FakeRunner(SimpleNamespace(output_text="advice", run_id="run-no-usage"))
        adapter = CodexChatGPTControlAdapter(
            capability_reader=self.capability,
            confirm_prompt=lambda _: True,
            runner=runner,
            agent_factory=lambda **values: values,
        )
        response = adapter.send_consult("bounded prompt", model="gpt-5.6-luna", effort="xhigh")
        self.assertEqual(response.transport.usage_status, "unavailable")
        self.assertIn("did not expose", response.transport.usage_reason)
        self.assertIsNone(response.transport.input_tokens)


if __name__ == "__main__":
    unittest.main()
