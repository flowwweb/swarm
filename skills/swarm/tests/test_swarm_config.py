from __future__ import annotations

from copy import deepcopy
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
    def test_profession_registry_matches_runtime_order_and_labels(self) -> None:
        from skills.swarm.runtime.core import BUILT_IN_PROFESSIONS, PROFESSION_GROUPS
        self.assertEqual(config.PROFESSION_GROUPS,PROFESSION_GROUPS)
        self.assertEqual(config.BUILT_IN_PROFESSIONS,BUILT_IN_PROFESSIONS)
        self.assertEqual(len(BUILT_IN_PROFESSIONS), 24)
        self.assertNotIn("mother", BUILT_IN_PROFESSIONS)

    def test_profession_specialist_and_structural_specialist_use_separate_namespaces(self) -> None:
        effective,_=config.load(config.TEMPLATE_PATH)
        structural=config.resolve_role_assignment(effective,"specialist")
        profession=config.resolve_profession_assignment(effective,"specialist",domain="maritime",truth_surface="COLREG interpretation")
        self.assertEqual(profession["profession_id"],"specialist")
        self.assertEqual(profession["authority"],"none")
        self.assertTrue(structural["model"])
        with self.assertRaisesRegex(config.ConfigError,"named domain and truth surface"):
            config.resolve_profession_assignment(effective,"specialist")

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

    def test_console_is_opt_in_and_does_not_open_localhost_by_default(self) -> None:
        self.assertFalse(config.DEFAULTS["console"]["open_on_start"])
        effective, exists = config.load(config.TEMPLATE_PATH)
        self.assertTrue(exists)
        self.assertFalse(effective["console"]["open_on_start"])

    def test_doer_wip_limit_is_the_bounded_direct_owner_capacity_signal(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertEqual(effective["efficiency"]["doer_wip_limit"], 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text("[efficiency]\ndoer_wip_limit = 9\n", encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "doer_wip_limit"):
                config.load(path)

    def test_spark_is_fail_closed_by_default_and_uses_xhigh(self) -> None:
        self.assertFalse(config.DEFAULTS["boost"]["spark_enabled"])
        self.assertEqual(config.DEFAULTS["boost"]["spark_reasoning"], "xhigh")
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertFalse(effective["boost"]["spark_enabled"])
        self.assertEqual(effective["boost"]["spark_reasoning"], "xhigh")
        self.assertEqual(config.SPARK_WORKLOAD, "simple")
        self.assertEqual(config.SPARK_SAFE_TOOLS, frozenset({"shell"}))

    def test_existing_chat_relay_settings_are_validated_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "[chat_relay]\nenabled = true\nprovider = \"codex-chatgpt-control\"\n"
                "surface = \"chat\"\nmode = \"consult\"\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        self.assertEqual(
            effective["chat_relay"],
            {
                "enabled": True,
                "provider": "codex-chatgpt-control",
                "surface": "chat",
                "mode": "consult",
            },
        )

    def test_role_icons_default_to_enabled_octopus_ctrl_without_profession_authority_icons(self) -> None:
        self.assertTrue(config.DEFAULTS["role_icons"]["enabled"])
        self.assertEqual(config.DEFAULTS["role_icons"]["ctrl"], "🐙")
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertTrue(effective["role_icons"]["enabled"])
        self.assertEqual(effective["role_icons"]["ctrl"], "🐙")
        self.assertEqual(set(effective["professions"]),set(config.BUILT_IN_PROFESSIONS))
        self.assertEqual(effective["roles"],{})

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
                self.assertEqual(effective["professions"]["designer"]["reasoning"], effort)

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

    def test_automation_mode_defaults_standard_and_migrates_legacy_archive_toggle(self) -> None:
        self.assertEqual(config.DEFAULTS["automation"]["mode"], "standard")
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertEqual(effective["automation"]["mode"], "standard")
        self.assertNotIn("archive_completed_tasks", effective["lifecycle"])

        with tempfile.TemporaryDirectory() as directory:
            legacy = Path(directory) / "legacy.toml"
            legacy.write_text(
                "[lifecycle]\narchive_completed_tasks = false\n",
                encoding="utf-8",
            )
            migrated, _ = config.load(legacy)
            explicit = Path(directory) / "explicit.toml"
            explicit.write_text(
                '[automation]\nmode = "standard"\n[lifecycle]\narchive_completed_tasks = false\n',
                encoding="utf-8",
            )
            preferred, _ = config.load(explicit)
        self.assertEqual(migrated["automation"]["mode"], "manual")
        self.assertEqual(preferred["automation"]["mode"], "standard")
        self.assertNotIn("archive_completed_tasks", migrated["lifecycle"])

    def test_automation_mode_rejects_unknown_values_and_bad_legacy_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.toml"
            invalid.write_text('[automation]\nmode = "sometimes"\n', encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "automation.mode must be standard or manual"):
                config.load(invalid)
            legacy = root / "legacy.toml"
            legacy.write_text('[lifecycle]\narchive_completed_tasks = "yes"\n', encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "legacy lifecycle.archive_completed_tasks must be true or false"):
                config.load(legacy)

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

    def test_retired_profession_config_is_not_migrated_registered_or_routable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = {
                "icon": '[role_icons]\nretired = "x"\n',
                "model": '[models.medium]\nretired_model = "gpt-5.6-sol"\n',
                "role": '[roles.LegacyCoordinator]\nicon = "x"\nmodel = "gpt-5.6-sol"\n',
                "watchdog": "[watchdog]\nenabled = true\n",
            }
            for name, contents in invalid.items():
                with self.subTest(name=name):
                    path = root / f"{name}.toml"
                    path.write_text("schema_version = 3\n" + contents, encoding="utf-8")
                    with self.assertRaises(config.ConfigError):
                        config.load(path)
        with self.assertRaises(config.ConfigError):
            config.resolve_profession_id("MOTHER")
        with self.assertRaises(config.ConfigError):
            config.resolve_role_assignment(config.DEFAULTS, "MOTHER")

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

    def test_v4_partial_config_merges_proof_defaults_before_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"partial.toml"
            path.write_text("schema_version = 4\n[execution]\nusage_profile = \"low\"\n",encoding="utf-8")
            effective,_=config.load(path)
        self.assertEqual(effective["proof"],config.DEFAULTS["proof"])

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

    def test_unknown_legacy_step_role_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "schema_version = 1\n"
                "[role_icons]\nstep_coordinator = \"x\"\n"
                "[boost]\ngoal_levels = [\"step_coordinator\"]\n"
                "[labels]\nstep_coordinator = \"SURGE\"\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--path", str(path), "show", "--json"],
                capture_output=True,
                check=False,
                text=True,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unknown setting", completed.stderr)

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
            "ctrl",
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

    def test_high_profile_requests_max_for_every_builtin_role(self) -> None:
        high = config.DEFAULTS["models"]["high"]
        roles = ("ctrl", "lead", "doer", "task", "subtask", "assist", "advisor", "specialist", "architect", "review")
        self.assertTrue(all(high[f"{role}_reasoning"] == "max" for role in roles))

    def test_task_event_log_limit_is_small_bounded_and_configurable(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertEqual(effective["logging"]["task_event_limit"], 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text("[logging]\ntask_event_limit = 300\n", encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "logging.task_event_limit"):
                config.load(path)

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
            config.resolve_role_assignment(effective, "Manager", route_tier=1)["reasoning"],
            "high",
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
                '[execution]\nusage_profile = "low"\nmax_reasoning = "xhigh"\n'
                '[turbo]\nenabled = true\n[efficiency]\nmode = "CONSERVE"\n',
                encoding="utf-8",
            )
            turbo, _ = config.load(enabled)
            disabled = root / "disabled.toml"
            disabled.write_text(
                '[execution]\nusage_profile = "low"\n'
                '[turbo]\nenabled = false\n[efficiency]\nmode = "CONSERVE"\n',
                encoding="utf-8",
            )
            normal, _ = config.load(disabled)
        self.assertEqual(turbo["execution"]["usage_profile"], "high")
        self.assertFalse(turbo["execution"]["fast_mode"])
        self.assertNotIn("service_tier", turbo["execution"])
        self.assertEqual(turbo["efficiency"]["mode"], "MAX")
        turbo_receipt=config.resolve_model_assignment(turbo,"ctrl",surface="codex_task")
        self.assertFalse(turbo_receipt["requested_fast_mode"])
        self.assertIsNone(turbo_receipt["requested_service_tier"])
        self.assertEqual(
            config.resolve_role_assignment(turbo, "lead", route_tier=1)["reasoning"],
            "xhigh",
        )
        self.assertEqual(
            config.resolve_role_assignment(turbo, "doer", route_tier=1)["reasoning"],
            "xhigh",
        )
        self.assertEqual(normal["execution"]["usage_profile"], "low")
        self.assertFalse(normal["execution"]["fast_mode"])
        self.assertNotIn("service_tier", normal["execution"])
        self.assertEqual(normal["efficiency"]["mode"], "CONSERVE")

    def test_turbo_enabled_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text('[turbo]\nenabled = "yes"\n', encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "turbo.enabled must be true or false"):
                config.load(path)

    def test_fast_mode_defaults_off_and_must_be_boolean(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        receipt = config.resolve_model_assignment(effective,"ctrl",surface="codex_task")
        self.assertFalse(effective["execution"]["fast_mode"])
        self.assertNotIn("service_tier", effective["execution"])
        self.assertFalse(receipt["requested_fast_mode"])
        self.assertIsNone(receipt["requested_service_tier"])
        self.assertEqual(receipt["fast_mode_status"],"OFF")
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"invalid.toml"
            path.write_text('[execution]\nfast_mode = "yes"\n',encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError,"execution.fast_mode must be true or false"):
                config.load(path)

    def test_fast_mode_propagates_to_authority_levels_professions_and_subagent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"fast.toml"
            path.write_text("[execution]\nfast_mode = true\n",encoding="utf-8")
            effective,_=config.load(path)
        cases=[(role,"codex_task") for role in ("ctrl","lead","doer")]
        cases.extend((profession,"codex_task") for profession in config.BUILT_IN_PROFESSIONS)
        cases.append(("doer","subagent"))
        for role,surface in cases:
            with self.subTest(role=role,surface=surface):
                receipt=config.resolve_model_assignment(effective,role,surface=surface)
                self.assertTrue(receipt["requested_fast_mode"])
                self.assertEqual(receipt["requested_service_tier"],"fast")
                self.assertEqual(receipt["service_tier_selection_source"],"fast_mode")
                self.assertEqual(receipt["fast_mode_status"],"UNAVAILABLE")
        reviewer=config.resolve_model_assignment(effective,"reviewer",surface="codex_task")
        doer=config.resolve_model_assignment(effective,"doer",surface="codex_task")
        self.assertEqual(reviewer["model"],doer["model"])

    def test_fast_mode_changes_only_host_request_not_model_or_reasoning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"fast.toml"
            path.write_text('[execution]\nfast_mode = true\n',encoding="utf-8")
            effective,_=config.load(path)
        baseline=config.resolve_model_assignment(effective,"lead",surface="codex_task")
        self.assertEqual(baseline["requested_service_tier"],"fast")
        self.assertTrue(baseline["requested_fast_mode"])
        control=deepcopy(effective)
        control["execution"]["fast_mode"]=False
        standard=config.resolve_model_assignment(control,"lead",surface="codex_task")
        self.assertIsNone(standard["requested_service_tier"])
        self.assertEqual((baseline["model"],baseline["reasoning_effort"]),(standard["model"],standard["reasoning_effort"]))

    def test_legacy_fast_aliases_migrate_to_one_boolean_without_retaining_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service=root/"service.toml"
            service.write_text('[execution]\nservice_tier = "fast"\n',encoding="utf-8")
            migrated_service,_=config.load(service)
            efficiency=root/"efficiency.toml"
            efficiency.write_text('[efficiency]\nmode = "FAST"\n',encoding="utf-8")
            migrated_efficiency,_=config.load(efficiency)
            explicit=root/"explicit.toml"
            explicit.write_text(
                '[execution]\nfast_mode = false\nservice_tier = "priority"\n'
                '[efficiency]\nmode = "FAST"\n',encoding="utf-8",
            )
            explicit_effective,_=config.load(explicit)
            neutral=root/"neutral.toml"
            neutral.write_text('[execution]\nservice_tier = "flex"\n',encoding="utf-8")
            neutral_effective,_=config.load(neutral)
            current=root/"current.toml"
            current.write_text('[execution]\ncurrent_mode = "FAST"\n',encoding="utf-8")
            migrated_current,_=config.load(current)
            root_alias=root/"root-alias.toml"
            root_alias.write_text('fast_mode = true\ncurrent_mode = "FAST"\n',encoding="utf-8")
            migrated_root,_=config.load(root_alias)
        self.assertTrue(migrated_service["execution"]["fast_mode"])
        self.assertTrue(migrated_efficiency["execution"]["fast_mode"])
        self.assertEqual(migrated_efficiency["efficiency"]["mode"],"BALANCED")
        self.assertFalse(explicit_effective["execution"]["fast_mode"])
        self.assertEqual(explicit_effective["efficiency"]["mode"],"BALANCED")
        self.assertFalse(neutral_effective["execution"]["fast_mode"])
        self.assertTrue(migrated_current["execution"]["fast_mode"])
        self.assertTrue(migrated_root["execution"]["fast_mode"])
        for effective in (migrated_service,migrated_efficiency,explicit_effective,neutral_effective,migrated_current,migrated_root):
            self.assertNotIn("service_tier",effective["execution"])

    def test_legacy_fast_conflict_and_unknown_mode_fail_visibly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            conflict=root/"conflict.toml"
            conflict.write_text('[execution]\nservice_tier = "fast"\ncurrent_mode = "STANDARD"\n',encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError,"legacy Fast controls conflict"):
                config.load(conflict)
            unknown=root/"unknown.toml"
            unknown.write_text('[execution]\ncurrent_mode = "QUICK"\n',encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError,"FAST, STANDARD, or DEFAULT"):
                config.load(unknown)

    def test_legacy_service_tier_must_be_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"invalid.toml"
            path.write_text('[execution]\nservice_tier = true\n',encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError,"legacy execution.service_tier must be text"):
                config.load(path)

    def test_template_exposes_exactly_one_fast_control(self) -> None:
        text=config.TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertEqual(text.count("fast_mode = false"),1)
        self.assertNotIn("service_tier",text)
        self.assertNotIn('mode = "FAST"',text)

    def test_exact_host_response_receipt_confirms_fast_or_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"fast.toml"
            path.write_text("[execution]\nfast_mode = true\n",encoding="utf-8")
            effective,_=config.load(path)
        for tier in ("fast","priority"):
            with self.subTest(tier=tier):
                receipt=config.resolve_model_assignment(
                    effective,"reviewer",surface="codex_task",host_actual_service_tier=tier,
                    host_service_tier_receipt=f"host:response:resp_test:service_tier:{tier}",
                )
                self.assertEqual(receipt["actual_service_tier"],tier)
                self.assertEqual(receipt["actual_service_tier_verification"],"verified")
                self.assertEqual(receipt["fast_mode_status"],"ACTIVE")

    def test_absent_or_conflicting_host_tier_never_claims_fast_active(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"fast.toml"
            path.write_text("[execution]\nfast_mode = true\n",encoding="utf-8")
            effective,_=config.load(path)
        missing=config.resolve_model_assignment(effective,"lead",surface="codex_task")
        conflicting=config.resolve_model_assignment(
            effective,"lead",surface="codex_task",host_actual_service_tier="default",
            host_service_tier_receipt="host:response:resp_default:service_tier:default",
        )
        self.assertEqual(missing["fast_mode_status"],"UNAVAILABLE")
        self.assertIsNone(missing["actual_service_tier"])
        self.assertEqual(conflicting["fast_mode_status"],"UNAVAILABLE")
        self.assertEqual(conflicting["model"],missing["model"])
        with self.assertRaisesRegex(config.ConfigError,"does not match"):
            config.resolve_model_assignment(
                effective,"lead",surface="codex_task",host_actual_service_tier="priority",
                host_service_tier_receipt="host:response:resp_bad:service_tier:default",
            )

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
            {"model": "gpt-5.6-terra", "reasoning": "high"},
        )

    def test_default_hierarchy_requests_sol_ctrl_terra_lead_and_luna_workers(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertEqual(config.resolve_role_assignment(effective, "ctrl")["model"], "gpt-5.6-sol")
        self.assertEqual(config.resolve_role_assignment(effective, "lead")["model"], "gpt-5.6-terra")
        self.assertEqual(config.resolve_role_assignment(effective, "doer")["model"], "gpt-5.6-luna")
        self.assertEqual(config.resolve_role_assignment(effective, "subtask")["model"], "gpt-5.6-luna")

    def test_luna_assignment_is_requested_but_actual_execution_stays_unverified_without_host_metadata(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        receipt = config.resolve_model_assignment(
            effective,"doer",surface="subagent",workload="general",required_tools=("shell",),
        )
        self.assertEqual(receipt["model"],"gpt-5.6-luna")
        self.assertEqual(receipt["reasoning_effort"],"xhigh")
        self.assertEqual(receipt["actual_model_verification"],"UNVERIFIED")
        self.assertEqual(receipt["actual_model"],"")

    def test_explicit_model_provider_and_reasoning_are_preserved_without_tier_authority(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        receipt=config.resolve_model_assignment(
            effective,"doer",surface="codex_task",explicit_model="gpt-5.6-terra",explicit_provider="openai",
            explicit_reasoning="max",host_actual_model="gpt-5.6-terra",host_receipt="host:model:gpt-5.6-terra",
        )
        self.assertEqual(
            (receipt["model"],receipt["provider"],receipt["reasoning_effort"],receipt["requested_service_tier"]),
            ("gpt-5.6-terra","openai","max",None),
        )
        self.assertNotIn("service_tier",receipt)
        self.assertEqual(receipt["selection_source"],"explicit_user")
        self.assertEqual(receipt["actual_model_verification"],"verified")

    def test_host_model_mismatch_fails_closed(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        with self.assertRaisesRegex(config.ConfigError,"host selected"):
            config.resolve_model_assignment(effective,"doer",surface="subagent",host_actual_model="gpt-5.6-terra",host_receipt="host:model:terra")

    def test_spark_assignment_requires_explicit_opt_in_and_routes_simple_shell_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spark.toml"
            path.write_text(
                "[boost]\nspark_enabled = true\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        receipt = config.resolve_spark_assignment(
            effective,
            "doer",
            surface="subagent",
            required_tools=("shell",),
        )
        self.assertEqual(receipt["model"], "gpt-5.3-codex-spark")
        self.assertEqual(receipt["reasoning_effort"], "xhigh")
        self.assertEqual(receipt["actual_model_verification"], "UNVERIFIED")
        self.assertEqual(receipt["spark_usage_status"], "requested_unverified")
        self.assertFalse(receipt["spark_usage_countable"])

        disabled, _ = config.load(config.TEMPLATE_PATH)
        with self.assertRaisesRegex(config.ConfigError, "disabled by boost.spark_enabled"):
            config.resolve_spark_assignment(
                disabled,
                "doer",
                surface="subagent",
                required_tools=("shell",),
            )

    def test_spark_rejects_tools_outside_its_low_risk_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spark.toml"
            path.write_text("[boost]\nspark_enabled = true\n", encoding="utf-8")
            effective, _ = config.load(path)
        for tool in ("web", "computer_use", "image_input"):
            with self.subTest(tool=tool), self.assertRaisesRegex(
                config.ConfigError, rf"unsupported tool.*{tool}"
            ):
                config.resolve_spark_assignment(
                    effective,
                    "doer",
                    surface="subagent",
                    required_tools=(tool,),
                )

    def test_spark_reasoning_is_configurable_but_must_be_model_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spark.toml"
            path.write_text(
                "[boost]\nspark_enabled = true\nspark_reasoning = \"medium\"\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        receipt = config.resolve_spark_assignment(
            effective,
            "doer",
            surface="codex_task",
            required_tools=("shell",),
        )
        self.assertEqual(receipt["reasoning_effort"], "medium")

    def test_spark_host_receipt_makes_usage_countable_only_when_model_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spark.toml"
            path.write_text("[boost]\nspark_enabled = true\n", encoding="utf-8")
            effective, _ = config.load(path)
        receipt = config.resolve_spark_assignment(
            effective,
            "doer",
            surface="subagent",
            required_tools=("shell",),
            host_actual_model="gpt-5.3-codex-spark",
            host_receipt="host:model:gpt-5.3-codex-spark",
            require_host_verification=True,
        )
        self.assertEqual(receipt["actual_model_verification"], "verified")
        self.assertEqual(receipt["spark_usage_status"], "verified")
        self.assertTrue(receipt["spark_usage_countable"])

    def test_spark_verification_guard_fails_closed_without_host_metadata(self) -> None:
        effective, _ = config.load(config.TEMPLATE_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spark.toml"
            path.write_text("[boost]\nspark_enabled = true\n", encoding="utf-8")
            effective, _ = config.load(path)
        with self.assertRaisesRegex(config.ConfigError, "host execution receipt required"):
            config.resolve_spark_assignment(
                effective,
                "doer",
                surface="subagent",
                required_tools=("shell",),
                require_host_verification=True,
            )

    def test_spark_cli_emits_a_receipt_and_rejects_disabled_default(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--path",
                str(config.TEMPLATE_PATH),
                "spark",
                "--role",
                "doer",
                "--surface",
                "subagent",
                "--required-tool",
                "shell",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("disabled by boost.spark_enabled", completed.stderr)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spark.toml"
            path.write_text("[boost]\nspark_enabled = true\n", encoding="utf-8")
            guarded = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--path",
                    str(path),
                    "spark",
                    "--role",
                    "doer",
                    "--surface",
                    "subagent",
                    "--required-tool",
                    "shell",
                    "--require-host-verification",
                ],
                capture_output=True,
                check=False,
                text=True,
            )
        self.assertEqual(guarded.returncode, 2)
        self.assertIn("host execution receipt required", guarded.stderr)


if __name__ == "__main__":
    unittest.main()
