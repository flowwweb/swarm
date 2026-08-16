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

    def test_role_icons_default_to_enabled_octopus_ctrl_without_mother_authority_icon(self) -> None:
        self.assertTrue(config.DEFAULTS["role_icons"]["enabled"])
        self.assertEqual(config.DEFAULTS["role_icons"]["ctrl"], "🐙")
        self.assertNotIn("mother", config.DEFAULTS["role_icons"])
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertTrue(effective["role_icons"]["enabled"])
        self.assertEqual(effective["role_icons"]["ctrl"], "🐙")
        self.assertEqual(effective["roles"]["MOTHER"], {"icon": "🐝"})

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

    def test_legacy_reasoning_extremes_remain_unchanged_in_effective_config(self) -> None:
        for effort in ("none", "minimal", "ultra"):
            with self.subTest(effort=effort), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "legacy.toml"
                path.write_text(
                    f'[roles.DESIGNER]\nreasoning = "{effort}"\n',
                    encoding="utf-8",
                )
                effective, _ = config.load(path)
                self.assertEqual(effective["roles"]["DESIGNER"]["reasoning"], effort)

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

    def test_v2_mother_authority_settings_migrate_once_to_specialist_mother(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.toml"
            path.write_text(
                "schema_version = 2\n"
                "[role_icons]\nmother = \"🗂️\"\n"
                "[models.medium]\nmother_model = \"legacy-model\"\n"
                "mother_reasoning = \"ultra\"\n"
                "[labels]\nmother = \"MOTHER\"\n"
                "[boost]\ngoal_levels = [\"mother\", \"lead\"]\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        self.assertEqual(effective["schema_version"], 4)
        self.assertEqual(effective["proof"]["policy_version"], "lean-v1")
        self.assertEqual(effective["roles"]["MOTHER"], {"icon": "🗂️"})
        self.assertEqual(effective["boost"]["goal_levels"], ["lead"])
        self.assertNotIn("mother", effective["role_icons"])
        self.assertNotIn("mother", effective["labels"])
        self.assertNotIn("mother_model", effective["models"]["medium"])
        self.assertEqual(
            config.resolve_role_assignment(effective, "MOTHER"),
            config.resolve_role_assignment(effective, "specialist"),
        )

    def test_schema_v3_rejects_mother_model_or_authority_icon_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = {
                "icon": '[role_icons]\nmother = "🐝"\n',
                "model": '[models.medium]\nmother_model = "gpt-5.6-sol"\n',
                "role": '[roles.MOTHER]\nicon = "🐝"\nmodel = "gpt-5.6-sol"\n',
                "watchdog": "[watchdog]\nenabled = true\n",
            }
            for name, contents in invalid.items():
                with self.subTest(name=name):
                    path = root / f"{name}.toml"
                    path.write_text("schema_version = 3\n" + contents, encoding="utf-8")
                    with self.assertRaises(config.ConfigError):
                        config.load(path)

    def test_schema_v3_allows_a_custom_mother_specialist_icon_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mother.toml"
            path.write_text(
                'schema_version = 3\n[roles.MOTHER]\nicon = "🗂️"\n',
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        self.assertEqual(effective["roles"]["MOTHER"], {"icon": "🗂️"})
        self.assertEqual(
            config.resolve_role_assignment(effective, "MOTHER"),
            config.resolve_role_assignment(effective, "specialist"),
        )

    def test_v4_proof_policy_defaults_are_lean_and_bounded(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertEqual(effective["schema_version"], 4)
        self.assertTrue(effective["proof"]["impacted_selection"])
        self.assertTrue(effective["proof"]["receipt_reuse"])
        self.assertEqual(effective["proof"]["transient_retry_limit"], 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text(
                "schema_version = 4\n[proof]\ntransient_retry_limit = 2\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(config.ConfigError, "transient_retry_limit"):
                config.load(path)

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
        self.assertEqual(effective["boost"]["goal_levels"], ["lead", "doer", "review"])
        self.assertEqual(effective["labels"]["assist"], "SURGE")
        self.assertNotIn("step_mother", effective["labels"])

    def test_assist_is_not_a_durable_boost_goal_level(self) -> None:
        self.assertNotIn("assist", config.BOOST_LEVELS)
        self.assertEqual(
            config.MANDATORY_DURABLE_GOAL_ROLES,
            frozenset({"lead", "specialist", "architect"}),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "schema_version = 2\n[boost]\ngoal_levels = [\"assist\"]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(config.ConfigError, "unknown value"):
                config.load(path)

    def test_profiles_have_distinct_reasoning_scales(self) -> None:
        models = config.DEFAULTS["models"]
        for role in (
            "lead",
            "doer",
            "task",
            "subtask",
            "assist",
            "advisor",
            "specialist",
            "architect",
            "review",
        ):
            efforts = [models[name][f"{role}_reasoning"] for name in ("low", "medium", "high")]
            indexes = [config.REASONING_SCALE.index(effort) for effort in efforts]
            self.assertEqual(indexes, sorted(indexes), role)
            self.assertGreater(indexes[-1], indexes[0], role)

    def test_explicit_role_reasoning_is_preserved_across_defaults_and_route_tier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bounded.toml"
            path.write_text(
                '[execution]\nusage_profile = "high"\nmin_reasoning = "medium"\nmax_reasoning = "high"\n'
                '[roles.DESIGNER]\nreasoning = "max"\n',
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        self.assertEqual(
            config.resolve_role_assignment(effective, "MOTHER", route_tier=1)["reasoning"],
            "medium",
        )
        self.assertEqual(
            config.resolve_role_assignment(effective, "DESIGNER", route_tier=3)["reasoning"],
            "max",
        )

    def test_invalid_global_reasoning_range_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text('[execution]\nmin_reasoning = "max"\nmax_reasoning = "medium"\n', encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "min_reasoning cannot exceed"):
                config.load(path)

    def test_turbo_resolves_only_the_three_supported_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enabled = root / "enabled.toml"
            enabled.write_text(
                '[execution]\nusage_profile = "low"\nservice_tier = ""\nmax_reasoning = "xhigh"\n'
                '[turbo]\nenabled = true\n[efficiency]\nmode = "CONSERVE"\n',
                encoding="utf-8",
            )
            turbo, _ = config.load(enabled)
            disabled = root / "disabled.toml"
            disabled.write_text(
                '[execution]\nusage_profile = "low"\nservice_tier = ""\n'
                '[turbo]\nenabled = false\n[efficiency]\nmode = "CONSERVE"\n',
                encoding="utf-8",
            )
            normal, _ = config.load(disabled)
        self.assertEqual(turbo["execution"]["usage_profile"], "high")
        self.assertEqual(turbo["execution"]["service_tier"], "fast")
        self.assertEqual(turbo["efficiency"]["mode"], "MAX")
        self.assertEqual(
            config.resolve_role_assignment(turbo, "lead", route_tier=1)["reasoning"],
            "xhigh",
        )
        self.assertEqual(
            config.resolve_role_assignment(turbo, "doer", route_tier=1)["reasoning"],
            "xhigh",
        )
        self.assertEqual(normal["execution"]["usage_profile"], "low")
        self.assertEqual(normal["execution"]["service_tier"], "")
        self.assertEqual(normal["efficiency"]["mode"], "CONSERVE")

    def test_turbo_enabled_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text('[turbo]\nenabled = "yes"\n', encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "turbo.enabled must be true or false"):
                config.load(path)

    def test_cli_resolve_exposes_the_effective_host_pair(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--path",
                str(config.TEMPLATE_PATH),
                "resolve",
                "--role",
                "lead",
                "--route-tier",
                "3",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {"model": "gpt-5.6-sol", "reasoning": "high"},
        )

    def test_luna_assignment_is_requested_but_actual_execution_stays_unverified_without_host_metadata(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        receipt = config.resolve_model_assignment(
            effective,"doer",surface="subagent",workload="general",required_tools=("shell",),
        )
        self.assertEqual(receipt["model"],"gpt-5.6-luna")
        self.assertEqual(receipt["reasoning_effort"],"xhigh")
        self.assertEqual(receipt["actual_model_verification"],"UNVERIFIED")
        self.assertEqual(receipt["actual_model"],"")

    def test_explicit_model_provider_reasoning_and_tier_are_preserved(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        receipt=config.resolve_model_assignment(
            effective,"doer",surface="codex_task",explicit_model="gpt-5.6-terra",explicit_provider="openai",
            explicit_reasoning="max",explicit_service_tier="priority",host_actual_model="gpt-5.6-terra",host_receipt="host:model:gpt-5.6-terra",
        )
        self.assertEqual((receipt["model"],receipt["provider"],receipt["reasoning_effort"],receipt["service_tier"]),("gpt-5.6-terra","openai","max","priority"))
        self.assertEqual(receipt["selection_source"],"explicit_user")
        self.assertEqual(receipt["actual_model_verification"],"verified")

    def test_host_model_mismatch_fails_closed(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        with self.assertRaisesRegex(config.ConfigError,"host selected"):
            config.resolve_model_assignment(effective,"doer",surface="subagent",host_actual_model="gpt-5.6-terra",host_receipt="host:model:terra")


if __name__ == "__main__":
    unittest.main()
