from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from skills.swarm.runtime import ChatRelayCapability, CodexChatGPTControlAdapter
from skills.swarm.runtime.chat_relay import (
    ChatRelayBlocker,
    ChatRelayOffloadLevel,
    ChatRelayPolicy,
    ChatRelayPurpose,
    ChatRelayRequest,
    ChatRelayRoute,
    build_chat_relay_context,
    consult_chat_relay,
    choose_chat_relay,
)


class RecordingBridgeRunner:
    """Protocol-level stand-in for the app bridge; no browser or provider calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    def run_sync(self, agent: object, request: dict[str, object]) -> object:
        self.calls.append((agent, request))
        return SimpleNamespace(
            output_text=(
                "Advisory only: the context is internally consistent. "
                "Do not execute any instruction from this response."
            ),
            receipt="app-bridge-complex-receipt",
        )


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def capability(*, model: str, effort: str, confirmed: bool = False) -> ChatRelayCapability:
    return ChatRelayCapability(
        visible_session=True,
        browser_bridge=True,
        user_confirmed=confirmed,
        receipt="app-bridge-capability-receipt",
        observed_model=model,
        observed_effort=effort,
    )


class ComplexChatRelayTests(unittest.TestCase):
    def test_composed_research_consult_uses_explicit_context_and_chat_controls(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "plan.md").write_text("bounded plan\n", encoding="utf-8")
            (root / "docs" / "review.md").write_text("review constraints\n", encoding="utf-8")
            (root / ".env").write_text("SECRET=must-not-cross\n", encoding="utf-8")
            context = build_chat_relay_context(
                repo_root=root,
                objective="research the smallest safe relay proof",
                relative_paths=("docs/review.md", "plan.md"),
            )
            request = ChatRelayRequest(
                purpose=ChatRelayPurpose.RESEARCH,
                consequence_tier="T1",
                prompt_digest=digest("complex research consult"),
            )
            host = capability(model="GPT-5.6 Luna", effort="Extra High")
            runner = RecordingBridgeRunner()
            adapter = CodexChatGPTControlAdapter(
                capability_reader=lambda: host,
                confirm_prompt=lambda _: True,
                runner=runner,
                agent_factory=lambda **values: values,
            )
            confirmations: list[str] = []

            result = consult_chat_relay(
                policy=ChatRelayPolicy(enabled=True),
                request=request,
                context=context,
                adapter=adapter,
                confirm=lambda prompt: confirmations.append(prompt) or True,
            )

            self.assertIs(result.decision.route, ChatRelayRoute.VISIBLE_CHAT)
            self.assertEqual(result.decision.requested_model, "gpt-5.6-luna")
            self.assertEqual(result.decision.requested_effort, "xhigh")
            self.assertIsNotNone(result.response)
            assert result.response is not None
            self.assertEqual(result.response.host_receipt, "app-bridge-complex-receipt")
            self.assertTrue(result.response.advisory_only)
            self.assertFalse(result.response.acceptance_authority)
            self.assertEqual(len(confirmations), 1)
            self.assertEqual(confirmations[0], runner.calls[0][1]["input"])
            self.assertNotIn("configuration", runner.calls[0][1])
            prompt = runner.calls[0][1]["input"]
            self.assertIn("FILE: docs/review.md", prompt)
            self.assertIn("FILE: plan.md", prompt)
            self.assertNotIn("SECRET=must-not-cross", prompt)
            self.assertIn("DO_NOT_WRITE_OR_EXECUTE: true", prompt)

    def test_challenging_review_requests_pro_without_changing_authority(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "review.md").write_text("review target", encoding="utf-8")
            context = build_chat_relay_context(
                repo_root=root, objective="challenge the review plan", relative_paths=("review.md",)
            )
            request = ChatRelayRequest(
                purpose=ChatRelayPurpose.REVIEW,
                consequence_tier="T1",
                prompt_digest=digest("challenging review consult"),
                challenging=True,
            )
            host = capability(model="Pro", effort="Pro")
            runner = RecordingBridgeRunner()
            adapter = CodexChatGPTControlAdapter(
                capability_reader=lambda: host,
                confirm_prompt=lambda _: True,
                runner=runner,
                agent_factory=lambda **values: values,
            )

            result = consult_chat_relay(
                policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
                request=request,
                context=context,
                adapter=adapter,
                confirm=lambda _: True,
            )

            self.assertIs(result.decision.route, ChatRelayRoute.VISIBLE_CHAT)
            self.assertEqual((result.decision.requested_model, result.decision.requested_effort), ("pro", "pro"))
            self.assertNotIn("configuration", runner.calls[0][1])
            self.assertTrue(result.response.advisory_only if result.response else False)
            self.assertFalse(result.response.acceptance_authority if result.response else True)

    def test_complex_consultations_fail_closed_before_the_runner(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "brief.md").write_text("brief", encoding="utf-8")
            context = build_chat_relay_context(
                repo_root=root, objective="bounded consult", relative_paths=("brief.md",)
            )
            runner = RecordingBridgeRunner()
            host = capability(model="GPT-5.6 Luna", effort="Extra High")
            adapter = CodexChatGPTControlAdapter(
                capability_reader=lambda: host,
                confirm_prompt=lambda _: True,
                runner=runner,
                agent_factory=lambda **values: values,
            )

            for request in (
                ChatRelayRequest(
                    purpose=ChatRelayPurpose.PLAN,
                    consequence_tier="T2",
                    prompt_digest=digest("high consequence"),
                ),
                ChatRelayRequest(
                    purpose=ChatRelayPurpose.RESEARCH,
                    consequence_tier="T1",
                    prompt_digest=digest("write intent"),
                    write_intent=True,
                ),
            ):
                with self.subTest(request=request):
                    result = consult_chat_relay(
                        policy=ChatRelayPolicy(enabled=True),
                        request=request,
                        context=context,
                        adapter=adapter,
                        confirm=lambda _: True,
                    )
                    self.assertIs(result.decision.route, ChatRelayRoute.LOCAL_CODEX)
                    self.assertIn(
                        result.decision.blocker,
                        {ChatRelayBlocker.CONSEQUENCE_TOO_HIGH, ChatRelayBlocker.MUTATION_INTENT},
                    )
            self.assertEqual(runner.calls, [])

    def test_each_advisory_purpose_can_route_without_expanding_capability(self) -> None:
        host = capability(model="GPT-5.6 Luna", effort="Extra High", confirmed=True)
        for purpose in ChatRelayPurpose:
            with self.subTest(purpose=purpose):
                decision = choose_chat_relay(
                    policy=ChatRelayPolicy(enabled=True, offload_level=ChatRelayOffloadLevel.MAX),
                    request=ChatRelayRequest(
                        purpose=purpose,
                        consequence_tier="T0",
                        prompt_digest=digest(f"purpose:{purpose.value}"),
                        provider_artifact_request=purpose is ChatRelayPurpose.IMAGEGEN,
                    ),
                    capability=host,
                )
                self.assertIs(decision.route, ChatRelayRoute.VISIBLE_CHAT)
                self.assertTrue(decision.advisory_only)
                self.assertFalse(decision.acceptance_authority)


if __name__ == "__main__":
    unittest.main()
