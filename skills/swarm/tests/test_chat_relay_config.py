from __future__ import annotations

from hashlib import sha256
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skills.swarm.runtime import (
    ChatRelayCapability,
    ChatRelayOffloadLevel,
    ChatRelayPolicy,
    ChatRelayPurpose,
    ChatRelayRequest,
    ChatRelayRoute,
    ChatRelayRoutingMode,
    InvariantError,
    Swarm,
)


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "swarm_config.py"
SPEC = importlib.util.spec_from_file_location("swarm_chat_relay_config_tested", SCRIPT)
assert SPEC and SPEC.loader
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


class ChatRelayConfigTests(unittest.TestCase):
    def test_chat_relay_is_dormant_by_default(self) -> None:
        effective, exists = config.load(config.TEMPLATE_PATH)
        self.assertTrue(exists)
        self.assertEqual(
            effective["chat_relay"],
            {
                "enabled": False,
                "provider": "codex-chatgpt-control",
                "surface": "chat",
                "mode": "consult",
                "routing_mode": "auto",
                "offload_level": "balanced",
                "default_model": "gpt-5.6-luna",
                "default_effort": "xhigh",
                "challenging_model": "pro",
                "challenging_effort": "pro",
                "executor_enabled": False,
                "executor_write_mode": "read_only",
                "executor_command_mode": "none",
                "executor_require_confirmation": True,
            },
        )

    def test_chat_relay_accepts_only_visible_chat_consult(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            enabled = root / "enabled.toml"
            enabled.write_text(
                '[chat_relay]\nenabled = true\nprovider = "local-bridge"\n',
                encoding="utf-8",
            )
            effective, _ = config.load(enabled)
            self.assertTrue(effective["chat_relay"]["enabled"])
            self.assertEqual(effective["chat_relay"]["surface"], "chat")
            self.assertEqual(effective["chat_relay"]["mode"], "consult")
            self.assertEqual(effective["chat_relay"]["routing_mode"], "auto")
            self.assertEqual(effective["chat_relay"]["offload_level"], "balanced")
            self.assertEqual(effective["chat_relay"]["default_model"], "gpt-5.6-luna")
            self.assertEqual(effective["chat_relay"]["default_effort"], "xhigh")
            self.assertEqual(effective["chat_relay"]["challenging_model"], "pro")
            self.assertEqual(effective["chat_relay"]["challenging_effort"], "pro")

            invalid = root / "invalid.toml"
            invalid.write_text('[chat_relay]\nsurface = "work"\n', encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "chat_relay.surface must be chat"):
                config.load(invalid)

    def test_explicit_relay_profiles_survive_merge_and_runtime_load(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.toml"
            path.write_text(
                "[execution]\n"
                "usage_saver = true\n"
                "[chat_relay]\n"
                "enabled = true\n"
                "default_model = \"pro\"\n"
                "default_effort = \"high\"\n"
                "challenging_model = \"gpt-5.6-luna\"\n"
                "challenging_effort = \"xhigh\"\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
            swarm = Swarm.from_config(effective)

        self.assertTrue(swarm.usage_saver)
        self.assertEqual(
            (
                swarm.chat_relay_policy.default_model,
                swarm.chat_relay_policy.default_effort,
                swarm.chat_relay_policy.challenging_model,
                swarm.chat_relay_policy.challenging_effort,
            ),
            ("pro", "high", "gpt-5.6-luna", "xhigh"),
        )
        decision = swarm.select_chat_relay(
            ChatRelayRequest(
                purpose=ChatRelayPurpose.PLAN,
                consequence_tier="T0",
                prompt_digest=sha256(b"configured profile").hexdigest(),
            ),
            ChatRelayCapability(
                visible_session=True,
                browser_bridge=True,
                user_confirmed=True,
                receipt="configured-profile-receipt",
                observed_model="Pro",
                observed_effort="High",
            ),
        )
        self.assertIs(decision.route, ChatRelayRoute.VISIBLE_CHAT)
        self.assertEqual((decision.requested_model, decision.requested_effort), ("pro", "high"))

    def test_offload_level_is_a_four_stop_routing_policy(self) -> None:
        base = dict(
            purpose=ChatRelayPurpose.REVIEW,
            consequence_tier="T1",
            prompt_digest=sha256(b"level").hexdigest(),
            challenging=True,
        )
        host = ChatRelayCapability(
            visible_session=True,
            browser_bridge=True,
            user_confirmed=True,
            receipt="level-receipt",
            observed_model="Pro",
            observed_effort="Pro",
        )
        for level, expected in (
            (ChatRelayOffloadLevel.LIGHT, ChatRelayRoute.LOCAL_CODEX),
            (ChatRelayOffloadLevel.BALANCED, ChatRelayRoute.LOCAL_CODEX),
            (ChatRelayOffloadLevel.HIGH, ChatRelayRoute.LOCAL_CODEX),
            (ChatRelayOffloadLevel.MAX, ChatRelayRoute.VISIBLE_CHAT),
        ):
            with self.subTest(level=level):
                decision = Swarm(chat_relay_policy=ChatRelayPolicy(enabled=True, offload_level=level)).select_chat_relay(
                    ChatRelayRequest(**base), host
                )
                self.assertIs(decision.route, expected)

    def test_routing_mode_accepts_auto_local_and_cloud(self) -> None:
        with TemporaryDirectory() as directory:
            for mode in ("auto", "always_local", "always_cloud"):
                path = Path(directory) / f"{mode}.toml"
                path.write_text(f"[chat_relay]\nrouting_mode = \"{mode}\"\n", encoding="utf-8")
                effective, _ = config.load(path)
                self.assertEqual(effective["chat_relay"]["routing_mode"], mode)
        self.assertEqual(ChatRelayPolicy.from_config({}).routing_mode, ChatRelayRoutingMode.AUTO)

    def test_invalid_routing_mode_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text('[chat_relay]\nrouting_mode = "cloud"\n', encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "chat_relay.routing_mode"):
                config.load(path)

    def test_invalid_relay_profile_does_not_silently_fall_back_to_defaults(self) -> None:
        cases = (
            ("default_model", "unknown-model", "chat_relay.default_model must be one of: gpt-5.6-luna, gpt-5.6-sol, pro"),
            ("challenging_model", "unknown-model", "chat_relay.challenging_model must be one of: gpt-5.6-luna, gpt-5.6-sol, pro"),
            ("default_effort", "extreme", "chat_relay.default_effort has an unsupported reasoning level"),
            ("challenging_effort", "extreme", "chat_relay.challenging_effort has an unsupported reasoning level"),
        )
        for key, value, message in cases:
            with self.subTest(key=key), TemporaryDirectory() as directory:
                path = Path(directory) / "invalid.toml"
                path.write_text(f'[chat_relay]\n{key} = "{value}"\n', encoding="utf-8")
                with self.assertRaisesRegex(config.ConfigError, message):
                    config.load(path)

    def test_swarm_from_config_owns_the_relay_policy(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "enabled.toml"
            path.write_text(
                "[execution]\nusage_saver = true\n[chat_relay]\nenabled = true\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
            swarm = Swarm.from_config(effective)
            self.assertTrue(swarm.usage_saver)
            self.assertTrue(swarm.chat_relay_policy.enabled)

    def test_swarm_from_config_loads_the_separate_executor_policy(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "executor.toml"
            path.write_text(
                "[chat_relay]\n"
                "enabled = true\n"
                "executor_enabled = true\n"
                "executor_write_mode = \"workspace\"\n"
                "executor_command_mode = \"safe\"\n"
                "executor_require_confirmation = false\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
            swarm = Swarm.from_config(effective)

        self.assertTrue(swarm.chat_executor_policy.enabled)
        self.assertEqual(swarm.chat_executor_policy.write_mode.value, "workspace")
        self.assertEqual(swarm.chat_executor_policy.command_mode.value, "safe")
        self.assertFalse(swarm.chat_executor_policy.require_confirmation)

    def test_usage_saver_is_typed_in_runtime_state(self) -> None:
        with self.assertRaises(InvariantError):
            Swarm(usage_saver="yes")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
