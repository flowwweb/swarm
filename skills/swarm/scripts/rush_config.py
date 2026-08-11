#!/usr/bin/env python3
"""Load and validate SWARM global TOML settings (with legacy RUSH fallback)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


SWARM_DEFAULT_PATH = Path.home() / ".agents" / "swarm" / "config.toml"
RUSH_LEGACY_PATH = Path.home() / ".agents" / "rush" / "config.toml"
DEFAULT_PATH = Path(os.environ.get("SWARM_CONFIG_PATH", SWARM_DEFAULT_PATH))
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "swarm-config.toml"
PLUGIN_MANIFEST_PATH = Path(__file__).resolve().parents[3] / ".codex-plugin" / "plugin.json"

def resolve_config_path(explicit: Path|None=None) -> Path:
    """One canonical resolver: explicit SWARM path, then existing legacy RUSH."""
    if explicit is not None:
        return explicit.expanduser()
    swarm=Path(os.environ.get("SWARM_CONFIG_PATH", SWARM_DEFAULT_PATH)).expanduser()
    if "SWARM_CONFIG_PATH" in os.environ or swarm.exists():
        return swarm
    legacy=Path(os.environ.get("RUSH_CONFIG_PATH", RUSH_LEGACY_PATH)).expanduser()
    return legacy if legacy.exists() else swarm

DEFAULTS: dict[str, Any] = {
    "schema_version": 2,
    "portfolio": {
        "max_active_tasks": 4,
        "default_parallel_tasks": 3,
        "reuse_existing_tasks": True,
    },
    "role_icons": {
        "enabled": True,
        "ctrl": "🐙",
        "mother": "⚡",
        "lead": "🧭",
        "review": "🔎",
        "fallback": "📋",
        "doer_choices": [
            "🔨", "💻", "✏️", "🎨", "📚", "📊",
            "🔌", "🧪", "✅", "📝", "🔀", "🚀",
        ],
    },
    "execution": {
        "usage_profile": "medium",
        "service_tier": "",
        "usage_saver": False,
    },
    "efficiency": {"mode":"BALANCED", "doer_wip_limit":3},
    "hive": {"enabled": True, "cleanup_strategy":"adaptive", "retention_strategy":"adaptive", "worker_strategy":"warm_when_useful", "archive_behavior":"provenance"},
    "boost": {
        "enabled": True,
        "strategies": [
            "durable_goal",
            "closeout_first",
            "hands_off",
            "spark_simple_work",
        ],
        "plan_at_remaining_percent": 5,
        "decide_at_remaining_percent": 2,
        "launch_at_remaining_percent": 1,
        "goal_levels": ["mother", "lead", "doer", "review"],
        "spark_model": "gpt-5.3-codex-spark",
    },
    "models": {
        "high": {
            "mother_model": "gpt-5.6-sol", "mother_reasoning": "medium",
            "lead_model": "gpt-5.6-sol", "lead_reasoning": "medium",
            "doer_model": "gpt-5.6-luna",
            "doer_reasoning": "xhigh",
            "task_model": "gpt-5.6-luna", "task_reasoning": "high",
            "subtask_model": "gpt-5.6-luna", "subtask_reasoning": "high",
            "assist_model": "gpt-5.6-sol", "assist_reasoning": "medium",
            "review_model": "gpt-5.6-sol", "review_reasoning": "medium",
            "advisor_model": "gpt-5.6-sol", "advisor_reasoning": "medium",
            "architect_model": "gpt-5.6-sol", "architect_reasoning": "medium",
        },
        "medium": {
            "mother_model": "gpt-5.6-sol", "mother_reasoning": "medium",
            "lead_model": "gpt-5.6-sol", "lead_reasoning": "medium",
            "doer_model": "gpt-5.6-luna",
            "doer_reasoning": "xhigh",
            "task_model": "gpt-5.6-luna", "task_reasoning": "high",
            "subtask_model": "gpt-5.6-luna", "subtask_reasoning": "high",
            "assist_model": "gpt-5.6-sol", "assist_reasoning": "medium",
            "review_model": "gpt-5.6-sol", "review_reasoning": "medium",
            "advisor_model": "gpt-5.6-sol", "advisor_reasoning": "medium",
            "architect_model": "gpt-5.6-sol", "architect_reasoning": "medium",
        },
        "low": {
            "mother_model": "gpt-5.6-sol", "mother_reasoning": "medium",
            "lead_model": "gpt-5.6-sol", "lead_reasoning": "medium",
            "doer_model": "gpt-5.6-luna",
            "doer_reasoning": "xhigh",
            "task_model": "gpt-5.6-luna", "task_reasoning": "high",
            "subtask_model": "gpt-5.6-luna", "subtask_reasoning": "high",
            "assist_model": "gpt-5.6-sol", "assist_reasoning": "medium",
            "review_model": "gpt-5.6-sol", "review_reasoning": "medium",
            "advisor_model": "gpt-5.6-sol", "advisor_reasoning": "medium",
            "architect_model": "gpt-5.6-sol", "architect_reasoning": "medium",
        },
    },
    "model_capabilities": {
        "gpt-5.6-sol": {
            "provider": "openai",
            "workloads": ["general", "large_goal", "review"],
            "tools": ["shell", "web", "computer_use", "image_input"],
        },
        "gpt-5.6-terra": {
            "provider": "openai",
            "workloads": ["simple", "general", "large_goal", "review"],
            "tools": ["shell", "web", "computer_use", "image_input"],
        },
        "gpt-5.6-luna": {
            "provider": "openai",
            "workloads": ["simple", "general", "large_goal"],
            "tools": ["shell", "web", "computer_use", "image_input"],
        },
        "gpt-5.3-codex-spark": {
            "provider": "openai",
            "workloads": ["simple"],
            "tools": ["shell", "web"],
        },
    },
    "roles": {},
    "labels": {
        "mother": "MOTHER",
        "lead": "LEAD",
        "doer": "DOER",
        "task": "TASK",
        "subtask": "SUBTASK",
        "assist": "ASSIST",
        "advisor": "ADVISOR",
        "architect": "ARCHITECT",
        "review": "REVIEW",
    },
    "coordination": {
        "allow_coordinators": True,
        "coordinator_min_children": 2,
        "preferred_lane_width": 3,
        "ctrl_direct_horizon_minutes": 20,
    },
    "subagents": {
        "enabled": True,
        "max_per_task": 8,
        "allowed_for": ["exploration", "implementation", "testing", "review"],
    },
    "review": {
        "task_enabled": True,
        "max_parallel_tasks": 3,
        "scale_when_queue_reaches": 2,
    },
    "monitoring": {"heartbeat_minutes": 30, "heartbeat_enabled": True, "default_review_horizon_minutes": 30, "max_review_horizon_minutes": 60, "small_task_review_horizon_minutes": 15},
    "recovery": {
        "max_attempts": 1,
        "stall_after_updates": 2,
    },
    "lifecycle": {
        "pin_created_tasks": False,
        "archive_completed_tasks": True,
    },
    "hygiene": {"no_review_archive_delay": 0, "low_review_retention": 7, "high_review_retention": 30, "stale_task_archive_delay": 1, "completed_task_retention": 30, "pinned_item_policy": "manual"},
    "feedback": {
        "enabled": True,
        "include_diagnostics": True,
        "prompt_on_close": False,
        "destination": "",
    },
}

ALLOWED_SUBAGENT_WORK = {"exploration", "implementation", "testing", "review"}
BOOST_STRATEGIES = {"durable_goal", "closeout_first", "hands_off", "spark_simple_work"}
BOOST_LEVELS = {"mother", "lead", "doer", "review"}
# These role goals are a fixed operating invariant, independent of Boost.
MANDATORY_DURABLE_GOAL_ROLES = frozenset({"mother", "lead", "architect"})
MODEL_WORKLOADS = {"simple", "general", "large_goal", "review"}
MODEL_CAPABILITY_KEYS = {"provider", "workloads", "tools"}
USAGE_PROFILES = {"high", "medium", "low"}
REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
ROLE_OVERRIDE_KEYS = {"icon", "model", "reasoning"}
LEGACY_PORTFOLIO_KEYS = {"title_prefix"}


class ConfigError(Exception):
    pass


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _expect_keys(data: dict[str, Any], allowed: set[str], location: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"unknown setting(s) in {location}: {', '.join(unknown)}")


def _expect_table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a TOML table")
    return value


def _bounded_int(data: dict[str, Any], key: str, low: int, high: int, location: str) -> None:
    if key not in data:
        return
    value = data[key]
    if not _is_int(value) or not low <= value <= high:
        raise ConfigError(f"{location}.{key} must be an integer from {low} to {high}")


def _boolean(data: dict[str, Any], key: str, location: str) -> None:
    if key in data and not isinstance(data[key], bool):
        raise ConfigError(f"{location}.{key} must be true or false")


def _short_text(
    data: dict[str, Any], key: str, location: str, *, allow_empty: bool = False
) -> None:
    if key not in data:
        return
    value = data[key]
    if (
        not isinstance(value, str)
        or value != value.strip()
        or (not value and not allow_empty)
        or len(value) > 24
        or any(character in value for character in "\r\n\t")
    ):
        empty_rule = "empty or a " if allow_empty else "a non-empty "
        raise ConfigError(
            f"{location}.{key} must be {empty_rule}trimmed single-line string up to 24 characters"
        )


def _short_text_list(data: dict[str, Any], key: str, location: str) -> None:
    if key not in data:
        return
    values = data[key]
    if not isinstance(values, list) or not 1 <= len(values) <= 12:
        raise ConfigError(f"{location}.{key} must contain 1 to 12 emojis")
    for value in values:
        if (
            not isinstance(value, str)
            or value != value.strip()
            or not value
            or len(value) > 24
            or any(character in value for character in "\r\n\t")
        ):
            raise ConfigError(
                f"{location}.{key} values must be trimmed single-line strings up to 24 characters"
            )
    if len(values) != len(set(values)):
        raise ConfigError(f"{location}.{key} cannot contain duplicates")


def _model_name(data: dict[str, Any], key: str, location: str) -> None:
    if key not in data:
        return
    value = data[key]
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 64
        or any(character in value for character in "\r\n\t")
    ):
        raise ConfigError(
            f"{location}.{key} must be a trimmed single-line model name up to 64 characters"
        )


def _reasoning_effort(data: dict[str, Any], key: str, location: str) -> None:
    if key in data and data[key] not in REASONING_EFFORTS:
        allowed = ", ".join(sorted(REASONING_EFFORTS))
        raise ConfigError(f"{location}.{key} must be one of: {allowed}")


def _feedback_destination(data: dict[str, Any]) -> None:
    if "destination" not in data:
        return
    value = data["destination"]
    if (
        not isinstance(value, str)
        or value != value.strip()
        or len(value) > 512
        or any(character in value for character in "\r\n\t")
    ):
        raise ConfigError(
            "feedback.destination must be empty or a trimmed single-line string up to 512 characters"
        )


def validate(raw: dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        raise ConfigError("the config root must be a TOML table")
    _expect_keys(raw, set(DEFAULTS), "root")
    schema_version = raw.get("schema_version", 1)
    if not _is_int(schema_version) or schema_version not in {1, 2}:
        raise ConfigError("schema_version must be 1 or 2")

    portfolio = _expect_table(raw, "portfolio")
    _expect_keys(
        portfolio,
        set(DEFAULTS["portfolio"]) | LEGACY_PORTFOLIO_KEYS,
        "portfolio",
    )
    _bounded_int(portfolio, "max_active_tasks", 1, 12, "portfolio")
    _bounded_int(portfolio, "default_parallel_tasks", 1, 8, "portfolio")
    _boolean(portfolio, "reuse_existing_tasks", "portfolio")
    if "title_prefix" in portfolio:
        _short_text(portfolio, "title_prefix", "portfolio", allow_empty=True)

    role_icons = _expect_table(raw, "role_icons")
    _expect_keys(
        role_icons,
        set(DEFAULTS["role_icons"]),
        "role_icons",
    )
    _boolean(role_icons, "enabled", "role_icons")
    for key in ("ctrl", "mother", "lead", "review", "fallback"):
        _short_text(role_icons, key, "role_icons")
    _short_text_list(role_icons, "doer_choices", "role_icons")

    execution = _expect_table(raw, "execution")
    _expect_keys(execution, set(DEFAULTS["execution"]), "execution")
    if "usage_profile" in execution and execution["usage_profile"] not in USAGE_PROFILES:
        raise ConfigError("execution.usage_profile must be high, medium, or low")
    _short_text(execution, "service_tier", "execution", allow_empty=True)
    _boolean(execution, "usage_saver", "execution")
    efficiency = _expect_table(raw, "efficiency")
    _expect_keys(efficiency, set(DEFAULTS["efficiency"]), "efficiency")
    if "mode" in efficiency and efficiency["mode"] not in {"CONSERVE","BALANCED","FAST","MAX"}: raise ConfigError("efficiency.mode must be CONSERVE, BALANCED, FAST, or MAX")
    _bounded_int(efficiency, "doer_wip_limit", 1, 8, "efficiency")

    hive = _expect_table(raw, "hive")
    _expect_keys(hive, set(DEFAULTS["hive"]), "hive")
    _boolean(hive, "enabled", "hive")
    for key, allowed in {"cleanup_strategy":{"adaptive"}, "retention_strategy":{"adaptive"}, "worker_strategy":{"warm_when_useful"}, "archive_behavior":{"provenance"}}.items():
        if key in hive and hive[key] not in allowed: raise ConfigError(f"hive.{key} has unsupported value")

    boost = _expect_table(raw, "boost")
    _expect_keys(boost, set(DEFAULTS["boost"]), "boost")
    _boolean(boost, "enabled", "boost")
    if "strategies" in boost:
        strategies = boost["strategies"]
        if not isinstance(strategies, list) or not strategies or not all(
            isinstance(item, str) for item in strategies
        ):
            raise ConfigError("boost.strategies must be a non-empty array of strings")
        unknown = sorted(set(strategies) - BOOST_STRATEGIES)
        if unknown:
            raise ConfigError(f"boost.strategies has unknown value(s): {', '.join(unknown)}")
        if len(strategies) != len(set(strategies)):
            raise ConfigError("boost.strategies cannot contain duplicates")
    for key in (
        "plan_at_remaining_percent",
        "decide_at_remaining_percent",
        "launch_at_remaining_percent",
    ):
        _bounded_int(boost, key, 1, 100, "boost")
    if "goal_levels" in boost:
        levels = boost["goal_levels"]
        if not isinstance(levels, list) or not levels or not all(
            isinstance(item, str) for item in levels
        ):
            raise ConfigError("boost.goal_levels must be a non-empty array of strings")
        unknown = sorted(set(levels) - BOOST_LEVELS)
        if unknown:
            raise ConfigError(f"boost.goal_levels has unknown value(s): {', '.join(unknown)}")
        if len(levels) != len(set(levels)):
            raise ConfigError("boost.goal_levels cannot contain duplicates")
    _model_name(boost, "spark_model", "boost")

    plan_at = boost.get(
        "plan_at_remaining_percent", DEFAULTS["boost"]["plan_at_remaining_percent"]
    )
    decide_at = boost.get(
        "decide_at_remaining_percent", DEFAULTS["boost"]["decide_at_remaining_percent"]
    )
    launch_at = boost.get(
        "launch_at_remaining_percent", DEFAULTS["boost"]["launch_at_remaining_percent"]
    )
    if not plan_at > decide_at > launch_at:
        raise ConfigError(
            "boost thresholds must satisfy plan_at_remaining_percent > "
            "decide_at_remaining_percent > launch_at_remaining_percent"
        )

    models = _expect_table(raw, "models")
    _expect_keys(models, set(DEFAULTS["models"]), "models")
    for profile, defaults in DEFAULTS["models"].items():
        values = models.get(profile, {})
        if not isinstance(values, dict):
            raise ConfigError(f"models.{profile} must be a TOML table")
        _expect_keys(values, set(defaults), f"models.{profile}")
        for role in ("mother", "lead", "doer", "task", "subtask", "assist", "review", "advisor", "architect"):
            _model_name(values, f"{role}_model", f"models.{profile}")
            _reasoning_effort(values, f"{role}_reasoning", f"models.{profile}")

    model_capabilities = _expect_table(raw, "model_capabilities")
    folded_models: set[str] = set()
    for model, values in model_capabilities.items():
        if (
            not isinstance(model, str)
            or model != model.strip()
            or not model
            or len(model) > 64
            or any(character in model for character in "\r\n\t")
        ):
            raise ConfigError(
                "model_capabilities keys must be trimmed single-line model names up to 64 characters"
            )
        folded = model.casefold()
        if folded in folded_models:
            raise ConfigError("model_capabilities cannot contain case-insensitive duplicates")
        folded_models.add(folded)
        if not isinstance(values, dict) or not values:
            raise ConfigError(f"model_capabilities.{model} must be a non-empty TOML table")
        _expect_keys(values, MODEL_CAPABILITY_KEYS, f"model_capabilities.{model}")
        if model not in DEFAULTS["model_capabilities"]:
            missing = sorted(MODEL_CAPABILITY_KEYS - set(values))
            if missing:
                raise ConfigError(
                    f"model_capabilities.{model} is missing required setting(s): {', '.join(missing)}"
                )
        _model_name(values, "provider", f"model_capabilities.{model}")
        if "workloads" in values:
            workloads = values["workloads"]
            if not isinstance(workloads, list) or not workloads or not all(
                isinstance(item, str) for item in workloads
            ):
                raise ConfigError(
                    f"model_capabilities.{model}.workloads must be a non-empty array of strings"
                )
            unknown = sorted(set(workloads) - MODEL_WORKLOADS)
            if unknown:
                raise ConfigError(
                    f"model_capabilities.{model}.workloads has unknown value(s): {', '.join(unknown)}"
                )
            if len(workloads) != len(set(workloads)):
                raise ConfigError(f"model_capabilities.{model}.workloads cannot contain duplicates")
        if "tools" in values:
            tools = values["tools"]
            if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools):
                raise ConfigError(f"model_capabilities.{model}.tools must be an array of strings")
            if len(tools) > 32:
                raise ConfigError(f"model_capabilities.{model}.tools cannot contain more than 32 values")
            for tool in tools:
                if (
                    tool != tool.strip()
                    or not tool
                    or len(tool) > 64
                    or any(character in tool for character in "\r\n\t")
                ):
                    raise ConfigError(
                        f"model_capabilities.{model}.tools values must be trimmed single-line strings up to 64 characters"
                    )
            if len(tools) != len(set(tools)):
                raise ConfigError(f"model_capabilities.{model}.tools cannot contain duplicates")

    roles = _expect_table(raw, "roles")
    folded_roles: set[str] = set()
    for role, values in roles.items():
        if (
            not isinstance(role, str)
            or role != role.strip()
            or not role
            or len(role) > 24
            or any(character in role for character in "\r\n\t")
        ):
            raise ConfigError("roles keys must be trimmed single-line role names up to 24 characters")
        folded = role.casefold()
        if folded in folded_roles:
            raise ConfigError("roles cannot contain case-insensitive duplicates")
        folded_roles.add(folded)
        if not isinstance(values, dict) or not values:
            raise ConfigError(f"roles.{role} must be a non-empty TOML table")
        _expect_keys(values, ROLE_OVERRIDE_KEYS, f"roles.{role}")
        _short_text(values, "icon", f"roles.{role}")
        _model_name(values, "model", f"roles.{role}")
        _reasoning_effort(values, "reasoning", f"roles.{role}")

    labels = _expect_table(raw, "labels")
    _expect_keys(labels, set(DEFAULTS["labels"]), "labels")
    for key in DEFAULTS["labels"]:
        _short_text(labels, key, "labels")
    effective_labels = {
        key: labels.get(key, DEFAULTS["labels"][key]).casefold()
        for key in DEFAULTS["labels"]
    }
    if len(set(effective_labels.values())) != len(effective_labels):
        raise ConfigError("hierarchy labels must be distinct")

    coordination = _expect_table(raw, "coordination")
    _expect_keys(coordination, set(DEFAULTS["coordination"]), "coordination")
    _boolean(coordination, "allow_coordinators", "coordination")
    _bounded_int(coordination, "coordinator_min_children", 2, 8, "coordination")
    _bounded_int(coordination, "preferred_lane_width", 1, 8, "coordination")
    _bounded_int(coordination, "ctrl_direct_horizon_minutes", 1, 60, "coordination")

    subagents = _expect_table(raw, "subagents")
    _expect_keys(subagents, set(DEFAULTS["subagents"]), "subagents")
    _boolean(subagents, "enabled", "subagents")
    _bounded_int(subagents, "max_per_task", 0, 8, "subagents")
    if "allowed_for" in subagents:
        allowed_for = subagents["allowed_for"]
        if not isinstance(allowed_for, list) or not all(isinstance(item, str) for item in allowed_for):
            raise ConfigError("subagents.allowed_for must be an array of strings")
        unknown = sorted(set(allowed_for) - ALLOWED_SUBAGENT_WORK)
        if unknown:
            raise ConfigError(f"subagents.allowed_for has unknown value(s): {', '.join(unknown)}")
        if len(allowed_for) != len(set(allowed_for)):
            raise ConfigError("subagents.allowed_for cannot contain duplicates")

    review = _expect_table(raw, "review")
    _expect_keys(review, set(DEFAULTS["review"]), "review")
    _boolean(review, "task_enabled", "review")
    _bounded_int(review, "max_parallel_tasks", 1, 8, "review")
    _bounded_int(review, "scale_when_queue_reaches", 2, 8, "review")

    monitoring = _expect_table(raw, "monitoring")
    _expect_keys(monitoring, set(DEFAULTS["monitoring"]), "monitoring")
    _bounded_int(monitoring, "heartbeat_minutes", 1, 120, "monitoring")
    _boolean(monitoring, "heartbeat_enabled", "monitoring")
    _bounded_int(monitoring, "default_review_horizon_minutes", 1, 60, "monitoring")
    _bounded_int(monitoring, "max_review_horizon_minutes", 1, 60, "monitoring")
    _bounded_int(monitoring, "small_task_review_horizon_minutes", 1, 20, "monitoring")
    small=monitoring.get("small_task_review_horizon_minutes",15); default=monitoring.get("default_review_horizon_minutes",30); maximum=monitoring.get("max_review_horizon_minutes",60)
    if not small<=default<=maximum: raise ConfigError("monitoring review horizons must satisfy small <= default <= maximum")
    if coordination.get("ctrl_direct_horizon_minutes",20)>maximum: raise ConfigError("coordination.ctrl_direct_horizon_minutes cannot exceed monitoring maximum review horizon")

    recovery = _expect_table(raw, "recovery")
    _expect_keys(recovery, set(DEFAULTS["recovery"]), "recovery")
    if recovery.get("max_attempts", DEFAULTS["recovery"]["max_attempts"]) != 1:
        raise ConfigError("recovery.max_attempts must be exactly 1")
    _bounded_int(recovery, "stall_after_updates", 1, 5, "recovery")

    lifecycle = _expect_table(raw, "lifecycle")
    _expect_keys(lifecycle, set(DEFAULTS["lifecycle"]), "lifecycle")
    _boolean(lifecycle, "pin_created_tasks", "lifecycle")
    _boolean(lifecycle, "archive_completed_tasks", "lifecycle")

    hygiene = _expect_table(raw, "hygiene")
    _expect_keys(hygiene, set(DEFAULTS["hygiene"]), "hygiene")
    for key in ("no_review_archive_delay", "low_review_retention", "high_review_retention", "stale_task_archive_delay", "completed_task_retention"):
        _bounded_int(hygiene, key, 0, 3650, "hygiene")
    if "pinned_item_policy" in hygiene and hygiene["pinned_item_policy"] not in {"manual", "project_close"}:
        raise ConfigError("hygiene.pinned_item_policy must be manual or project_close")

    feedback = _expect_table(raw, "feedback")
    _expect_keys(feedback, set(DEFAULTS["feedback"]), "feedback")
    _boolean(feedback, "enabled", "feedback")
    _boolean(feedback, "include_diagnostics", "feedback")
    _boolean(feedback, "prompt_on_close", "feedback")
    _feedback_destination(feedback)

    effective_max = portfolio.get("max_active_tasks", DEFAULTS["portfolio"]["max_active_tasks"])
    effective_parallel = portfolio.get(
        "default_parallel_tasks", DEFAULTS["portfolio"]["default_parallel_tasks"]
    )
    if effective_parallel > effective_max:
        raise ConfigError("portfolio.default_parallel_tasks cannot exceed portfolio.max_active_tasks")


def merge(raw: dict[str, Any]) -> dict[str, Any]:
    effective = deepcopy(DEFAULTS)
    normalized = deepcopy(raw)
    normalized.get("portfolio", {}).pop("title_prefix", None)

    def merge_table(target: dict[str, Any], updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge_table(target[key], value)
            else:
                target[key] = deepcopy(value)

    merge_table(effective, normalized)
    return effective


def normalize_legacy_task_role(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept legacy role settings while exposing only the DOER model."""
    normalized = deepcopy(raw)
    legacy = normalized.get("schema_version", 1) == 1
    role_icons = normalized.get("role_icons", {})
    if legacy and isinstance(role_icons, dict):
        role_icons.pop("step_mother", None)
    if isinstance(role_icons, dict) and "task_choices" in role_icons:
        role_icons.setdefault("doer_choices", role_icons.pop("task_choices"))
    boost = normalized.get("boost", {})
    if legacy and isinstance(boost, dict) and isinstance(boost.get("goal_levels"), list):
        levels = ["doer" if level == "task" else level for level in boost["goal_levels"]]
        # Legacy STEP MOTHER was a coordinator, never durable ASSIST ownership.
        levels = [level for level in levels if level not in {"step_mother", "assist"}]
        boost["goal_levels"] = list(dict.fromkeys(levels)) or deepcopy(DEFAULTS["boost"]["goal_levels"])
    for profile in normalized.get("models", {}).values():
        if legacy and isinstance(profile, dict):
            for suffix in ("model", "reasoning"):
                legacy = f"task_{suffix}"
                profile.setdefault(f"doer_{suffix}", profile.pop(legacy, None)) if legacy in profile else None
    labels = normalized.get("labels", {})
    if legacy and isinstance(labels, dict) and "step_mother" in labels:
        legacy_step = labels.pop("step_mother")
        if legacy_step != "STEP MOTHER":
            labels.setdefault("assist", legacy_step)
    if legacy and isinstance(labels, dict) and "task" in labels:
        legacy_label = labels.pop("task")
        if legacy_label != "TASK":
            labels.setdefault("doer", legacy_label)
    normalized["schema_version"] = 2
    return normalized


def load(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return deepcopy(DEFAULTS), False
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc
    normalized = normalize_legacy_task_role(raw)
    validate(normalized)
    return merge(normalized), True


def _plugin_version() -> str:
    try:
        manifest = json.loads(PLUGIN_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    version = manifest.get("version")
    return version if isinstance(version, str) and version else "unknown"


def feedback_diagnostics(effective: dict[str, Any], exists: bool) -> dict[str, Any]:
    """Return a shareable snapshot without paths, destinations, credentials, or project data."""
    return {
        "rush_version": _plugin_version(),
        "config_schema_version": effective["schema_version"],
        "config_exists": exists,
        "usage_profile": effective["execution"]["usage_profile"],
        "service_tier": effective["execution"]["service_tier"],
        "max_active_tasks": effective["portfolio"]["max_active_tasks"],
        "default_parallel_tasks": effective["portfolio"]["default_parallel_tasks"],
        "preferred_lane_width": effective["coordination"]["preferred_lane_width"],
        "emoji_system": "role" if effective["role_icons"]["enabled"] else "disabled",
        "ctrl_icon": effective["role_icons"]["ctrl"] if effective["role_icons"]["enabled"] else "",
        "review_task_enabled": effective["review"]["task_enabled"],
        "heartbeat_minutes": effective["monitoring"]["heartbeat_minutes"],
        "subagents_enabled": effective["subagents"]["enabled"],
        "boost_enabled": effective["boost"]["enabled"],
        "boost_strategies": effective["boost"]["strategies"],
        "feedback_destination_configured": bool(effective["feedback"]["destination"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default = resolve_config_path()
    parser.add_argument("--path", type=Path, default=default, help="SWARM config path; legacy RUSH path remains readable")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("path", help="print the global config path")
    show = subparsers.add_parser("show", help="print effective settings")
    show.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    feedback = subparsers.add_parser("feedback", help="print privacy-safe feedback diagnostics")
    feedback.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    subparsers.add_parser("validate", help="validate the config")
    subparsers.add_parser("init", help="create the default config if it is missing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path: Path = args.path.expanduser().resolve()
    try:
        if args.command == "path":
            print(path)
            return 0
        if args.command == "init":
            if path.exists():
                print(f"SWARM config already exists: {path}")
                return 0
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TEMPLATE_PATH, path)
            print(f"Created SWARM config: {path}")
            return 0

        effective, exists = load(path)
        if args.command == "validate":
            source = "file" if exists else "built-in defaults (file missing)"
            print(f"SWARM config valid: {path} [{source}]")
            return 0
        if args.command == "feedback":
            diagnostics = feedback_diagnostics(effective, exists)
            if args.json:
                print(json.dumps(diagnostics, indent=2))
            else:
                print("SWARM feedback diagnostics")
                print(json.dumps(diagnostics, indent=2))
            return 0
        if args.json:
            print(json.dumps({"path": str(path), "exists": exists, "settings": effective}, indent=2))
        else:
            print(f"SWARM config: {path}")
            print(f"Source: {'file' if exists else 'built-in defaults (file missing)'}")
            print(json.dumps(effective, indent=2))
        return 0
    except ConfigError as exc:
        print(f"SWARM config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
