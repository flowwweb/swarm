from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skills.swarm.runtime import Swarm
from skills.swarm.runtime.chat_relay import (
    ChatRelayBlocker,
    ChatRelayCapability,
    ChatRelayConsultation,
    ChatRelayContextPacket,
    ChatRelayOffloadLevel,
    ChatRelayPolicy,
    ChatRelayPurpose,
    ChatRelayResponse,
    ChatRelayRequest,
    ChatRelayRoute,
    ChatRelayRoutingMode,
    build_chat_relay_context,
    consult_chat_relay,
    choose_chat_relay,
)


def request(*, tier: str = "T0", write: bool = False, artifact: bool = False) -> ChatRelayRequest:
    return ChatRelayRequest(
        purpose=ChatRelayPurpose.PLAN,
        consequence_tier=tier,
        prompt_digest=hashlib.sha256(b"bounded consultation").hexdigest(),
        write_intent=write,
        artifact_production=artifact,
    )


def capability(
    *,
    session: bool = True,
    bridge: bool = True,
    confirmed: bool = True,
    model: str = "GPT-5.6 Luna",
    effort: str = "Extra High",
) -> ChatRelayCapability:
    return ChatRelayCapability(
        visible_session=session,
        browser_bridge=bridge,
        user_confirmed=confirmed,
        receipt="visible-chat-test-receipt",
        observed_model=model,
        observed_effort=effort,
    )


class FakeAdapter:
    def __init__(self, host: ChatRelayCapability) -> None:
        self.host = host
        self.sent: list[str] = []
        self.selections: list[tuple[str, str]] = []
        self.response_model = host.observed_model

    def capability(self) -> ChatRelayCapability:
        return self.host

    def send_consult(self, prompt: str, *, model: str, effort: str) -> ChatRelayResponse:
        self.sent.append(prompt)
        self.selections.append((model, effort))
        return ChatRelayResponse(
            text="advisory response",
            host_receipt="visible-chat-response-receipt",
            observed_model=self.response_model,
            observed_effort=self.host.observed_effort,
        )


class ChatRelayTests(unittest.TestCase):
    def test_disabled_relay_falls_back_without_host_call(self) -> None:
        decision = choose_chat_relay(
            policy=ChatRelayPolicy(), request=request(), capability=capability()
        )
        self.assertIs(decision.route, ChatRelayRoute.LOCAL_CODEX)
        self.assertIs(decision.blocker, ChatRelayBlocker.DISABLED)
        self.assertTrue(decision.advisory_only)
        self.assertFalse(decision.acceptance_authority)

    def test_swarm_runtime_owns_relay_policy_and_route(self) -> None:
        swarm = Swarm(chat_relay_policy=ChatRelayPolicy(enabled=True))
        decision = swarm.select_chat_relay(request(), capability())
        self.assertIs(decision.route, ChatRelayRoute.VISIBLE_CHAT)
        self.assertEqual(swarm.chat_relay_policy.provider, "codex-chatgpt-control")

    def test_confirmed_bounded_consult_uses_visible_chat(self) -> None:
        decision = choose_chat_relay(
            policy=ChatRelayPolicy(enabled=True), request=request(), capability=capability()
        )
        self.assertIs(decision.route, ChatRelayRoute.VISIBLE_CHAT)
        self.assertIsNone(decision.blocker)
        self.assertEqual(decision.observed_model, "GPT-5.6 Luna")
        self.assertEqual(decision.observed_effort, "Extra High")
        self.assertTrue(decision.advisory_only)
        self.assertFalse(decision.acceptance_authority)
        self.assertEqual((decision.requested_model, decision.requested_effort), ("gpt-5.6-luna", "xhigh"))

    def test_challenging_consult_requests_pro_profile(self) -> None:
        decision = choose_chat_relay(
            policy=ChatRelayPolicy(enabled=True),
            request=ChatRelayRequest(
                purpose=ChatRelayPurpose.PLAN,
                consequence_tier="T1",
                prompt_digest=hashlib.sha256(b"challenging consultation").hexdigest(),
                challenging=True,
            ),
            capability=capability(model="Pro", effort="Pro"),
        )
        self.assertIs(decision.route, ChatRelayRoute.VISIBLE_CHAT)
        self.assertEqual((decision.requested_model, decision.requested_effort), ("pro", "pro"))

    def test_visible_gpt_sol_profile_matches_the_current_chat_surface(self) -> None:
        decision = choose_chat_relay(
            policy=ChatRelayPolicy(enabled=True, default_model="gpt-5.6-sol"),
            request=request(),
            capability=capability(model="GPT-5.6 Sol", effort="Extra High"),
        )
        self.assertIs(decision.route, ChatRelayRoute.VISIBLE_CHAT)
        self.assertEqual(decision.requested_model, "gpt-5.6-sol")

    def test_missing_host_capabilities_fall_back(self) -> None:
        cases = (
            ("session", capability(session=False), ChatRelayBlocker.VISIBLE_SESSION_REQUIRED),
            ("bridge", capability(bridge=False), ChatRelayBlocker.BROWSER_BRIDGE_REQUIRED),
            ("confirmation", capability(confirmed=False), ChatRelayBlocker.USER_CONFIRMATION_REQUIRED),
            ("config", ChatRelayCapability(True, True, True, "receipt"), ChatRelayBlocker.HOST_CONFIG_REQUIRED),
        )
        for label, host, blocker in cases:
            with self.subTest(label=label):
                decision = choose_chat_relay(
                    policy=ChatRelayPolicy(enabled=True), request=request(), capability=host
                )
                self.assertIs(decision.route, ChatRelayRoute.LOCAL_CODEX)
                self.assertIs(decision.blocker, blocker)

    def test_mismatched_visible_profile_falls_back_before_send(self) -> None:
        host = capability()
        mismatched = ChatRelayCapability(
            visible_session=host.visible_session,
            browser_bridge=host.browser_bridge,
            user_confirmed=host.user_confirmed,
            receipt=host.receipt,
            observed_model="Pro",
            observed_effort="Pro",
        )
        decision = choose_chat_relay(
            policy=ChatRelayPolicy(enabled=True), request=request(), capability=mismatched
        )
        self.assertIs(decision.route, ChatRelayRoute.LOCAL_CODEX)
        self.assertIs(decision.blocker, ChatRelayBlocker.HOST_CONFIG_REQUIRED)
        self.assertIn("do not match", decision.reason)

    def test_mutation_and_high_consequence_work_stay_local(self) -> None:
        for item in (
            (request(write=True), ChatRelayBlocker.MUTATION_INTENT),
            (request(artifact=True), ChatRelayBlocker.MUTATION_INTENT),
            (request(tier="T2"), ChatRelayBlocker.CONSEQUENCE_TOO_HIGH),
        ):
            with self.subTest(blocker=item[1]):
                decision = choose_chat_relay(
                    policy=ChatRelayPolicy(enabled=True), request=item[0], capability=capability()
                )
                self.assertIs(decision.route, ChatRelayRoute.LOCAL_CODEX)
                self.assertIs(decision.blocker, item[1])

    def test_local_boundary_stays_local_in_every_routing_mode(self) -> None:
        boundary_request = ChatRelayRequest(
            purpose=ChatRelayPurpose.PLAN,
            consequence_tier="T0",
            prompt_digest=hashlib.sha256(b"bounded consultation").hexdigest(),
            local_boundary=True,
        )
        for mode in ChatRelayRoutingMode:
            with self.subTest(mode=mode):
                decision = choose_chat_relay(
                    policy=ChatRelayPolicy(enabled=True, routing_mode=mode),
                    request=boundary_request,
                    capability=capability(),
                )
                self.assertIs(decision.route, ChatRelayRoute.LOCAL_CODEX)
                self.assertIs(decision.blocker, ChatRelayBlocker.LOCAL_BOUNDARY_REQUIRED)

    def test_explicit_routing_modes_are_predictable(self) -> None:
        local = choose_chat_relay(
            policy=ChatRelayPolicy(enabled=True, routing_mode=ChatRelayRoutingMode.ALWAYS_LOCAL),
            request=request(),
            capability=capability(),
        )
        self.assertIs(local.route, ChatRelayRoute.LOCAL_CODEX)
        self.assertIs(local.blocker, ChatRelayBlocker.ROUTING_MODE_LOCAL)

        cloud = choose_chat_relay(
            policy=ChatRelayPolicy(
                enabled=True,
                routing_mode=ChatRelayRoutingMode.ALWAYS_CLOUD,
                offload_level=ChatRelayOffloadLevel.LIGHT,
            ),
            request=request(tier="T1"),
            capability=capability(),
        )
        self.assertIs(cloud.route, ChatRelayRoute.VISIBLE_CHAT)

    def test_routing_mode_is_separate_from_consult_authority(self) -> None:
        self.assertEqual(ChatRelayPolicy.from_config({"routing_mode": "always_cloud"}).routing_mode, ChatRelayRoutingMode.ALWAYS_CLOUD)
        with self.assertRaises(ValueError):
            ChatRelayPolicy(routing_mode="cloud")  # type: ignore[arg-type]

    def test_surface_and_mode_are_fixed_to_visible_chat_consult(self) -> None:
        with self.assertRaises(ValueError):
            ChatRelayPolicy(surface="work")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ChatRelayPolicy(mode="execute")

    def test_context_packet_reads_only_explicit_safe_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.md").write_text("bounded plan", encoding="utf-8")
            (root / "ignored.txt").write_text("not selected", encoding="utf-8")
            packet = build_chat_relay_context(
                repo_root=root,
                objective="review the bounded plan",
                relative_paths=("plan.md",),
            )
            self.assertIsInstance(packet, ChatRelayContextPacket)
            self.assertIn("FILE: plan.md", packet.render())
            self.assertNotIn("ignored.txt", packet.render())
            self.assertEqual(len(packet.digest), 64)

    def test_context_packet_rejects_escape_and_sensitive_paths(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.md").write_text("safe", encoding="utf-8")
            (root / ".env").write_text("SECRET=do-not-send", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_chat_relay_context(
                    repo_root=root, objective="inspect", relative_paths=("../safe.md",)
                )
            with self.assertRaises(ValueError):
                build_chat_relay_context(
                    repo_root=root, objective="inspect", relative_paths=(".env",)
                )

    def test_adapter_send_is_reachable_only_after_route_approval(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.md").write_text("bounded plan", encoding="utf-8")
            context = build_chat_relay_context(
                repo_root=root, objective="review", relative_paths=("plan.md",)
            )
            adapter = FakeAdapter(capability())
            result = consult_chat_relay(
                policy=ChatRelayPolicy(enabled=True),
                request=request(),
                context=context,
                adapter=adapter,
            )
            self.assertIsInstance(result, ChatRelayConsultation)
            self.assertIs(result.decision.route, ChatRelayRoute.VISIBLE_CHAT)
            self.assertIsNotNone(result.response)
            self.assertEqual(len(adapter.sent), 1)
            self.assertEqual(adapter.selections, [("gpt-5.6-luna", "xhigh")])
            self.assertIn("SWARM_ADVISORY_CONSULT_V1", adapter.sent[0])
            self.assertIn("plan.md", adapter.sent[0])

    def test_adapter_is_not_called_when_capability_falls_back(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.md").write_text("bounded plan", encoding="utf-8")
            context = build_chat_relay_context(
                repo_root=root, objective="review", relative_paths=("plan.md",)
            )
            adapter = FakeAdapter(capability(confirmed=False))
            result = consult_chat_relay(
                policy=ChatRelayPolicy(enabled=True),
                request=request(),
                context=context,
                adapter=adapter,
            )
            self.assertIs(result.decision.route, ChatRelayRoute.LOCAL_CODEX)
            self.assertIsNone(result.response)
            self.assertEqual(adapter.sent, [])

    def test_confirmation_covers_the_exact_rendered_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.md").write_text("bounded plan", encoding="utf-8")
            context = build_chat_relay_context(
                repo_root=root, objective="review", relative_paths=("plan.md",)
            )
            adapter = FakeAdapter(capability(confirmed=False))
            confirmations: list[str] = []
            result = consult_chat_relay(
                policy=ChatRelayPolicy(enabled=True),
                request=request(),
                context=context,
                adapter=adapter,
                confirm=lambda prompt: confirmations.append(prompt) or True,
            )
            self.assertIs(result.decision.route, ChatRelayRoute.VISIBLE_CHAT)
            self.assertEqual(confirmations, adapter.sent)
            self.assertIn("DO_NOT_WRITE_OR_EXECUTE: true", confirmations[0])

    def test_adapter_configuration_drift_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.md").write_text("bounded plan", encoding="utf-8")
            context = build_chat_relay_context(
                repo_root=root, objective="review", relative_paths=("plan.md",)
            )
            adapter = FakeAdapter(capability())
            adapter.response_model = "different-visible-model"
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                consult_chat_relay(
                    policy=ChatRelayPolicy(enabled=True),
                    request=request(),
                    context=context,
                    adapter=adapter,
                )

    def test_non_advisory_response_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot own acceptance"):
            ChatRelayResponse(
                text="unsafe",
                host_receipt="visible-chat-response-receipt",
                observed_model="GPT-5.6 Luna",
                observed_effort="Extra High",
                advisory_only=False,
            )


if __name__ == "__main__":
    unittest.main()
