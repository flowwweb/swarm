from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "swarm_config.py"
SPEC = importlib.util.spec_from_file_location("swarm_config_tested", SCRIPT)
assert SPEC and SPEC.loader
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


class SwarmConfigTests(unittest.TestCase):
    def test_canonical_path_and_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); canonical=root / "swarm.toml"; override=root / "custom.toml"
            with mock.patch.object(config,"SWARM_DEFAULT_PATH",canonical), mock.patch.dict(config.os.environ,{},clear=True):
                self.assertEqual(config.resolve_config_path(),canonical)
                self.assertEqual(config.resolve_config_path(override),override)
    def test_usage_saver_is_off_in_defaults_and_template(self) -> None:
        self.assertFalse(config.DEFAULTS["execution"]["usage_saver"])
        effective, exists = config.load(config.TEMPLATE_PATH)
        self.assertTrue(exists)
        self.assertFalse(effective["execution"]["usage_saver"])

    def test_role_icons_default_to_enabled_octopus_ctrl(self) -> None:
        self.assertTrue(config.DEFAULTS["role_icons"]["enabled"])
        self.assertEqual(config.DEFAULTS["role_icons"]["ctrl"], "🐙")
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertTrue(effective["role_icons"]["enabled"])
        self.assertEqual(effective["role_icons"]["ctrl"], "🐙")

    def test_role_icons_accept_custom_ctrl_and_disabled_contrast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom = root / "custom.toml"
            custom.write_text('[role_icons]\nctrl = "🕹️"\n', encoding="utf-8")
            custom_effective, _ = config.load(custom)
            self.assertTrue(custom_effective["role_icons"]["enabled"])
            self.assertEqual(custom_effective["role_icons"]["ctrl"], "🕹️")
            self.assertEqual(
                config.feedback_diagnostics(custom_effective, True)["ctrl_icon"],
                "🕹️",
            )

            disabled = root / "disabled.toml"
            disabled.write_text("[role_icons]\nenabled = false\n", encoding="utf-8")
            disabled_effective, _ = config.load(disabled)
            self.assertFalse(disabled_effective["role_icons"]["enabled"])
            diagnostics = config.feedback_diagnostics(disabled_effective, True)
            self.assertEqual(diagnostics["emoji_system"], "disabled")
            self.assertEqual(diagnostics["ctrl_icon"], "")

    def test_role_icons_enabled_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text('[role_icons]\nenabled = "no"\n', encoding="utf-8")
            with self.assertRaisesRegex(
                config.ConfigError,
                "role_icons.enabled must be true or false",
            ):
                config.load(path)

    def test_existing_config_without_usage_saver_merges_off(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[execution]\nusage_profile = "low"\n', encoding="utf-8")
            effective, exists = config.load(path)
        self.assertTrue(exists)
        self.assertEqual(effective["execution"]["usage_profile"], "low")
        self.assertFalse(effective["execution"]["usage_saver"])

    def test_usage_saver_accepts_only_a_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enabled = root / "enabled.toml"
            enabled.write_text("[execution]\nusage_saver = true\n", encoding="utf-8")
            effective, _ = config.load(enabled)
            self.assertTrue(effective["execution"]["usage_saver"])

            invalid = root / "invalid.toml"
            invalid.write_text('[execution]\nusage_saver = "sometimes"\n', encoding="utf-8")
            with self.assertRaisesRegex(
                config.ConfigError,
                "execution.usage_saver must be true or false",
            ):
                config.load(invalid)

    def test_archive_completed_tasks_defaults_on_and_can_opt_out(self) -> None:
        self.assertTrue(config.DEFAULTS["lifecycle"]["archive_completed_tasks"])
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertTrue(effective["lifecycle"]["archive_completed_tasks"])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "[lifecycle]\narchive_completed_tasks = false\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        self.assertFalse(effective["lifecycle"]["archive_completed_tasks"])

    def test_recovery_requires_exactly_one_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for attempts in (0, 2):
                path = Path(directory) / f"{attempts}.toml"
                path.write_text(f"[recovery]\nmax_attempts = {attempts}\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    config.ConfigError, "recovery.max_attempts must be exactly 1"
                ):
                    config.load(path)

    def test_review_horizon_defaults_are_bounded_and_legacy_configs_merge(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertEqual(effective["monitoring"]["small_task_review_horizon_minutes"], 15)
        self.assertEqual(effective["monitoring"]["default_review_horizon_minutes"], 30)
        self.assertEqual(effective["monitoring"]["max_review_horizon_minutes"], 60)
        self.assertEqual(effective["coordination"]["ctrl_direct_horizon_minutes"], 20)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.toml"
            path.write_text("schema_version = 2\n[monitoring]\nheartbeat_minutes = 45\n", encoding="utf-8")
            legacy, _ = config.load(path)
        self.assertEqual(legacy["monitoring"]["heartbeat_minutes"], 45)
        self.assertEqual(legacy["monitoring"]["default_review_horizon_minutes"], 30)

    def test_review_horizon_order_and_direct_bound_are_enforced(self) -> None:
        invalid = (
            "[monitoring]\nsmall_task_review_horizon_minutes = 20\ndefault_review_horizon_minutes = 10\n",
            "[coordination]\nctrl_direct_horizon_minutes = 60\n[monitoring]\nmax_review_horizon_minutes = 30\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, contents in enumerate(invalid):
                path = Path(directory) / f"invalid-{index}.toml"
                path.write_text(contents, encoding="utf-8")
                with self.assertRaises(config.ConfigError):
                    config.load(path)

    def test_legacy_task_role_settings_normalize_to_doer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "[role_icons]\ntask_choices = [\"🔨\"]\n"
                "[boost]\ngoal_levels = [\"task\"]\n"
                "[models.medium]\ntask_model = \"gpt-5.6-luna\"\n"
                "task_reasoning = \"high\"\n"
                "[labels]\ntask = \"WORKER\"\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        self.assertEqual(effective["boost"]["goal_levels"], ["doer"])
        self.assertEqual(effective["models"]["medium"]["doer_reasoning"], "high")
        self.assertEqual(effective["labels"]["doer"], "WORKER")
        self.assertIn("doer_choices", effective["role_icons"])
        self.assertEqual(effective["labels"]["task"], "TASK")

    def test_legacy_step_mother_normalizes_to_assist_and_cli_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "schema_version = 1\n"
                "[role_icons]\nstep_mother = \"🗂️\"\n"
                "[boost]\ngoal_levels = [\"step_mother\"]\n"
                "[labels]\nstep_mother = \"SURGE\"\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--path", str(path), "show", "--json"],
                capture_output=True,
                check=False,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        effective = json.loads(completed.stdout)["settings"]
        self.assertEqual(effective["boost"]["goal_levels"], ["mother", "lead", "doer", "review"])
        self.assertEqual(effective["labels"]["assist"], "SURGE")
        self.assertNotIn("step_mother", effective["labels"])

    def test_assist_is_not_a_durable_boost_goal_level(self) -> None:
        self.assertNotIn("assist", config.BOOST_LEVELS)
        self.assertEqual(
            config.MANDATORY_DURABLE_GOAL_ROLES,
            frozenset({"mother", "lead", "specialist", "architect"}),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "schema_version = 2\n[boost]\ngoal_levels = [\"assist\"]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(config.ConfigError, "unknown value"):
                config.load(path)

    def test_every_named_role_has_an_explicit_profile_pair(self) -> None:
        roles = {
            "mother": ("gpt-5.6-sol", "medium"),
            "architect": ("gpt-5.6-sol", "medium"),
            "lead": ("gpt-5.6-sol", "medium"),
            "advisor": ("gpt-5.6-sol", "medium"),
            "doer": ("gpt-5.6-luna", "xhigh"),
            "task": ("gpt-5.6-luna", "high"),
            "subtask": ("gpt-5.6-luna", "high"),
            "assist": ("gpt-5.6-sol", "medium"),
            "review": ("gpt-5.6-sol", "medium"),
        }
        for profile in config.DEFAULTS["models"].values():
            for role, (model, reasoning) in roles.items():
                self.assertEqual(profile[f"{role}_model"], model)
                self.assertEqual(profile[f"{role}_reasoning"], reasoning)


if __name__ == "__main__":
    unittest.main()
