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
        runner = FakeRunner(SimpleNamespace(output_text="advice", run_id="run-123"))
        adapter = CodexChatGPTControlAdapter(
            capability_reader=self.capability,
            confirm_prompt=lambda _: True,
            runner=runner,
            agent_factory=lambda **values: values,
        )
        response = adapter.send_consult("bounded prompt", model="gpt-5.6-luna", effort="xhigh")
        self.assertEqual(response.text, "advice")
        self.assertEqual(response.host_receipt, "run-123")
        self.assertEqual(runner.calls[0][1]["experience"], "chat")
        self.assertEqual(
            runner.calls[0][1]["configuration"],
            {"modelVersion": "GPT-5.6 Luna", "intelligence": "Extra High"},
        )
        self.assertEqual(runner.calls[0][1]["response"], {"format": "markdown"})

    def test_pro_selection_uses_visible_chat_intelligence_control(self) -> None:
        runner = FakeRunner(SimpleNamespace(output_text="advice", run_id="run-pro"))
        adapter = CodexChatGPTControlAdapter(
            capability_reader=self.capability,
            confirm_prompt=lambda _: True,
            runner=runner,
            agent_factory=lambda **values: values,
        )
        adapter.send_consult("challenging prompt", model="pro", effort="pro")
        self.assertEqual(runner.calls[0][1]["configuration"], {"intelligence": "Pro"})

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


if __name__ == "__main__":
    unittest.main()
