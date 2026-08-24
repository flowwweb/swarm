#!/usr/bin/env python3
"""Load and validate SWARM global TOML settings."""

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
DEFAULT_PATH = Path(os.environ.get("SWARM_CONFIG_PATH", SWARM_DEFAULT_PATH))
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "swarm-config.toml"
PLUGIN_MANIFEST_PATH = Path(__file__).resolve().parents[3] / ".codex-plugin" / "plugin.json"

def resolve_config_path(explicit: Path|None=None) -> Path:
    """Resolve an explicit path or the canonical SWARM config location."""
    if explicit is not None:
        return explicit.expanduser()
    return Path(os.environ.get("SWARM_CONFIG_PATH", SWARM_DEFAULT_PATH)).expanduser()

DEFAULTS: dict[str, Any] = {
    "schema_version": 4,
    "portfolio": {
        "max_active_tasks": 4,
        "default_parallel_tasks": 3,
        "reuse_existing_tasks": True,
    },
    "role_icons": {
        "enabled": True,
        "ctrl": "🐙",
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
        "fast_mode": False,
        "usage_saver": False,
        "min_reasoning": "none",
        "max_reasoning": "ultra",
    },
    "console": {"open_on_start": False},
    "automation": {"mode": "standard"},
    "skills": {"inheritance_enabled": True, "default_profile": "default"},
    "logging": {"task_event_limit": 64},
    "proof": {
        "policy_version": "lean-v1",
        "impacted_selection": True,
        "receipt_reuse": True,
        "gate_timeout_seconds": 120,
        "browser_freshness_seconds": 86400,
        "provider_freshness_seconds": 3600,
        "transient_retry_limit": 1,
    },
    "turbo": {"enabled": False},
    "efficiency": {"mode":"BALANCED", "doer_wip_limit":3},
    "goals": {"use_goals": True},
    "hive": {"enabled": True, "cleanup_strategy":"adaptive", "retention_strategy":"adaptive", "worker_strategy":"warm_when_useful", "archive_behavior":"provenance"},
    "chat_relay": {
        "enabled": False,
        "provider": "codex-chatgpt-control",
        "surface": "chat",
        "mode": "consult",
    },
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
        "goal_levels": ["lead", "doer", "review"],
        "spark_model": "gpt-5.3-codex-spark",
        "spark_reasoning": "xhigh",
        "spark_enabled": False,
    },
    "models": {
        "high": {
            "ctrl_model": "gpt-5.6-sol", "ctrl_reasoning": "max",
            "lead_model": "gpt-5.6-terra", "lead_reasoning": "max",
            "doer_model": "gpt-5.6-luna",
            "doer_reasoning": "max",
            "task_model": "gpt-5.6-luna", "task_reasoning": "max",
            "subtask_model": "gpt-5.6-luna", "subtask_reasoning": "max",
            "assist_model": "gpt-5.6-sol", "assist_reasoning": "max",
            "review_model": "gpt-5.6-sol", "review_reasoning": "max",
            "advisor_model": "gpt-5.6-sol", "advisor_reasoning": "max",
            "specialist_model": "gpt-5.6-sol", "specialist_reasoning": "max",
            "architect_model": "gpt-5.6-sol", "architect_reasoning": "max",
        },
        "medium": {
            "ctrl_model": "gpt-5.6-sol", "ctrl_reasoning": "medium",
            "lead_model": "gpt-5.6-terra", "lead_reasoning": "medium",
            "doer_model": "gpt-5.6-luna",
            "doer_reasoning": "xhigh",
            "task_model": "gpt-5.6-luna", "task_reasoning": "high",
            "subtask_model": "gpt-5.6-luna", "subtask_reasoning": "high",
            "assist_model": "gpt-5.6-sol", "assist_reasoning": "medium",
            "review_model": "gpt-5.6-sol", "review_reasoning": "medium",
            "advisor_model": "gpt-5.6-sol", "advisor_reasoning": "medium",
            "specialist_model": "gpt-5.6-sol", "specialist_reasoning": "medium",
            "architect_model": "gpt-5.6-sol", "architect_reasoning": "medium",
        },
        "low": {
            "ctrl_model": "gpt-5.6-sol", "ctrl_reasoning": "low",
            "lead_model": "gpt-5.6-terra", "lead_reasoning": "low",
            "doer_model": "gpt-5.6-luna",
            "doer_reasoning": "medium",
            "task_model": "gpt-5.6-luna", "task_reasoning": "low",
            "subtask_model": "gpt-5.6-luna", "subtask_reasoning": "low",
            "assist_model": "gpt-5.6-sol", "assist_reasoning": "low",
            "review_model": "gpt-5.6-sol", "review_reasoning": "low",
            "advisor_model": "gpt-5.6-sol", "advisor_reasoning": "low",
            "specialist_model": "gpt-5.6-sol", "specialist_reasoning": "low",
            "architect_model": "gpt-5.6-sol", "architect_reasoning": "low",
        },
    },
    "model_capabilities": {
        "gpt-5.6-sol": {
            "provider": "openai",
            "workloads": ["general", "large_goal", "review"],
            "tools": ["shell", "web", "computer_use", "image_input"],
            "reasoning": ["low", "medium", "high", "xhigh", "max", "ultra"],
        },
        "gpt-5.6-terra": {
            "provider": "openai",
            "workloads": ["simple", "general", "large_goal", "review"],
            "tools": ["shell", "web", "computer_use", "image_input"],
            "reasoning": ["low", "medium", "high", "xhigh", "max", "ultra"],
        },
        "gpt-5.6-luna": {
            "provider": "openai",
            "workloads": ["simple", "general", "large_goal"],
            "tools": ["shell", "web", "computer_use", "image_input"],
            "reasoning": ["low", "medium", "high", "xhigh", "max"],
        },
        "gpt-5.3-codex-spark": {
            "provider": "openai",
            "workloads": ["simple"],
            "tools": ["shell"],
            "reasoning": ["low", "medium", "high", "xhigh"],
        },
    },
    "roles": {},
    "professions": {},
    "labels": {
        "lead": "LEAD",
        "doer": "DOER",
        "task": "TASK",
        "subtask": "SUBTASK",
        "assist": "ASSIST",
        "advisor": "ADVISOR",
        "architect": "ARCHITECT",
        "specialist": "SPECIALIST",
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
    "monitoring": {"heartbeat_minutes": 30, "default_review_horizon_minutes": 30, "max_review_horizon_minutes": 60, "small_task_review_horizon_minutes": 15, "auto_health_enabled": False},
    "recovery": {
        "max_attempts": 1,
        "stall_after_updates": 2,
    },
    "lifecycle": {
        "pin_created_tasks": True,
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
BOOST_LEVELS = {"lead", "doer", "review"}
SPARK_SAFE_TOOLS = frozenset({"shell"})
SPARK_WORKLOAD = "simple"
# These role goals are a fixed operating invariant, independent of Boost.
MANDATORY_DURABLE_GOAL_ROLES = frozenset({"lead", "specialist", "architect"})
MODEL_WORKLOADS = {"simple", "general", "large_goal", "review"}
MODEL_CAPABILITY_REQUIRED_KEYS = {"provider", "workloads", "tools"}
MODEL_CAPABILITY_KEYS = MODEL_CAPABILITY_REQUIRED_KEYS | {"reasoning"}
USAGE_PROFILES = {"high", "medium", "low"}
REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
REASONING_SCALE = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
ROLE_OVERRIDE_KEYS = {"icon", "model", "reasoning"}
STRUCTURAL_CONFIG_ROLES = frozenset({"ctrl", "lead", "doer", "task", "subtask", "assist", "review", "advisor", "specialist", "architect"})
FAST_SERVICE_TIERS = frozenset({"fast", "priority"})
PROFESSION_GROUPS = (
    ("Direction", (("manager", "Manager"), ("strategist", "Strategist"))),
    ("Discovery", (("researcher", "Researcher"), ("analyst", "Analyst"), ("specialist", "Specialist"), ("inventor", "Inventor"))),
    ("Creation", (("architect", "Architect"), ("designer", "Designer"), ("artist", "Artist"), ("writer", "Writer"), ("developer", "Dev"), ("producer", "Producer"))),
    ("Assurance", (("tester", "Tester"), ("critic", "Critic"), ("security", "Security"), ("auditor", "Auditor"), ("legal", "Legal"), ("reviewer", "Reviewer"))),
    ("Delivery", (("operator", "Operator"), ("marketer", "Marketer"), ("support", "Support"))),
    ("Foundation", (("accountant", "Accountant"), ("recruiter", "Recruiter"), ("educator", "Educator"))),
)
BUILT_IN_PROFESSIONS = {
    profession_id: label
    for _, professions in PROFESSION_GROUPS
    for profession_id, label in professions
}
PROFESSION_ALIASES = {
    "product_manager": "manager", "project_manager": "manager", "planner": "manager",
    "data_analyst": "analyst", "financial_analyst": "analyst",
    "content_strategist": "strategist", "social_strategist": "strategist", "sales_strategist": "strategist",
    "brand_strategist": "strategist", "security_engineer": "security", "support_specialist": "support",
    "dev": "developer",
}

def resolve_profession_id(value: str) -> str:
    key = str(value).strip().casefold().replace(" ", "_")
    resolved = PROFESSION_ALIASES.get(key, key)
    if resolved not in BUILT_IN_PROFESSIONS:
        raise ConfigError(f"unknown profession: {key}")
    return resolved
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
    if not _is_int(schema_version) or schema_version not in {1, 2, 3, 4}:
        raise ConfigError("schema_version must be 1, 2, 3, or 4")

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
    for key in ("ctrl", "lead", "review", "fallback"):
        _short_text(role_icons, key, "role_icons")
    _short_text_list(role_icons, "doer_choices", "role_icons")

    execution = _expect_table(raw, "execution")
    _expect_keys(execution, set(DEFAULTS["execution"]), "execution")
    if "usage_profile" in execution and execution["usage_profile"] not in USAGE_PROFILES:
        raise ConfigError("execution.usage_profile must be high, medium, or low")
    _boolean(execution, "fast_mode", "execution")
    _boolean(execution, "usage_saver", "execution")
    _reasoning_effort(execution, "min_reasoning", "execution")
    _reasoning_effort(execution, "max_reasoning", "execution")
    minimum = execution.get("min_reasoning", DEFAULTS["execution"]["min_reasoning"])
    maximum = execution.get("max_reasoning", DEFAULTS["execution"]["max_reasoning"])
    if REASONING_SCALE.index(minimum) > REASONING_SCALE.index(maximum):
        raise ConfigError("execution.min_reasoning cannot exceed execution.max_reasoning")
    console = _expect_table(raw, "console")
    _expect_keys(console, set(DEFAULTS["console"]), "console")
    _boolean(console, "open_on_start", "console")
    automation = _expect_table(raw, "automation")
    _expect_keys(automation, set(DEFAULTS["automation"]), "automation")
    if automation.get("mode", DEFAULTS["automation"]["mode"]) not in {"standard", "manual"}:
        raise ConfigError("automation.mode must be standard or manual")
    skills = _expect_table(raw, "skills")
    _expect_keys(skills, set(DEFAULTS["skills"]), "skills")
    _boolean(skills, "inheritance_enabled", "skills")
    if skills.get("default_profile", DEFAULTS["skills"]["default_profile"]) not in {
        "default", "discovery", "debug", "testing", "verification", "web_qa", "design"
    }:
        raise ConfigError("skills.default_profile is not allowlisted")
    logging = _expect_table(raw, "logging")
    _expect_keys(logging, set(DEFAULTS["logging"]), "logging")
    _bounded_int(logging, "task_event_limit", 8, 256, "logging")
    proof = _expect_table(raw, "proof")
    _expect_keys(proof, set(DEFAULTS["proof"]), "proof")
    _short_text(proof, "policy_version", "proof")
    _boolean(proof, "impacted_selection", "proof")
    _boolean(proof, "receipt_reuse", "proof")
    _bounded_int(proof, "gate_timeout_seconds", 1, 3600, "proof")
    _bounded_int(proof, "browser_freshness_seconds", 0, 604800, "proof")
    _bounded_int(proof, "provider_freshness_seconds", 0, 86400, "proof")
    _bounded_int(proof, "transient_retry_limit", 0, 1, "proof")
    turbo = _expect_table(raw, "turbo")
    _expect_keys(turbo, set(DEFAULTS["turbo"]), "turbo")
    _boolean(turbo, "enabled", "turbo")
    efficiency = _expect_table(raw, "efficiency")
    _expect_keys(efficiency, set(DEFAULTS["efficiency"]), "efficiency")
    if "mode" in efficiency and efficiency["mode"] not in {"CONSERVE","BALANCED","MAX"}: raise ConfigError("efficiency.mode must be CONSERVE, BALANCED, or MAX")
    _bounded_int(efficiency, "doer_wip_limit", 1, 8, "efficiency")

    goals = _expect_table(raw, "goals")
    _expect_keys(goals, set(DEFAULTS["goals"]), "goals")
    _boolean(goals, "use_goals", "goals")

    hive = _expect_table(raw, "hive")
    _expect_keys(hive, set(DEFAULTS["hive"]), "hive")
    _boolean(hive, "enabled", "hive")
    for key, allowed in {"cleanup_strategy":{"adaptive"}, "retention_strategy":{"adaptive"}, "worker_strategy":{"warm_when_useful"}, "archive_behavior":{"provenance"}}.items():
        if key in hive and hive[key] not in allowed: raise ConfigError(f"hive.{key} has unsupported value")

    chat_relay = _expect_table(raw, "chat_relay")
    _expect_keys(chat_relay, set(DEFAULTS["chat_relay"]), "chat_relay")
    _boolean(chat_relay, "enabled", "chat_relay")
    for key in ("provider", "surface", "mode"):
        _short_text(chat_relay, key, "chat_relay")
    if chat_relay.get("surface", DEFAULTS["chat_relay"]["surface"]) != "chat":
        raise ConfigError("chat_relay.surface must be chat")
    if chat_relay.get("mode", DEFAULTS["chat_relay"]["mode"]) != "consult":
        raise ConfigError("chat_relay.mode must be consult")

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
    _reasoning_effort(boost, "spark_reasoning", "boost")
    _boolean(boost, "spark_enabled", "boost")

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
        for role in ("ctrl", "lead", "doer", "task", "subtask", "assist", "review", "advisor", "specialist", "architect"):
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
            missing = sorted(MODEL_CAPABILITY_REQUIRED_KEYS - set(values))
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
        if "reasoning" in values:
            efforts = values["reasoning"]
            if not isinstance(efforts, list) or not efforts:
                raise ConfigError(f"model_capabilities.{model}.reasoning must be a non-empty array")
            unknown = sorted(set(efforts) - REASONING_EFFORTS)
            if unknown:
                raise ConfigError(
                    f"model_capabilities.{model}.reasoning has unknown value(s): {', '.join(unknown)}"
                )
            if len(efforts) != len(set(efforts)):
                raise ConfigError(f"model_capabilities.{model}.reasoning cannot contain duplicates")
            indexes = [REASONING_SCALE.index(effort) for effort in efforts]
            if indexes != sorted(indexes):
                raise ConfigError(f"model_capabilities.{model}.reasoning must be ordered")

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
        normalized_role=folded.replace(" ","_")
        if normalized_role not in STRUCTURAL_CONFIG_ROLES:
            raise ConfigError(f"roles.{role} is not a structural authority role; use professions.{role}")
        if not isinstance(values, dict) or not values:
            raise ConfigError(f"roles.{role} must be a non-empty TOML table")
        _expect_keys(values, ROLE_OVERRIDE_KEYS, f"roles.{role}")
        _short_text(values, "icon", f"roles.{role}")
        _model_name(values, "model", f"roles.{role}")
        _reasoning_effort(values, "reasoning", f"roles.{role}")

    professions=_expect_table(raw,"professions")
    folded_professions:set[str]=set()
    for profession,values in professions.items():
        if not isinstance(profession,str) or profession!=profession.strip() or not profession or len(profession)>32 or any(character in profession for character in "\r\n\t"):
            raise ConfigError("professions keys must be trimmed single-line names up to 32 characters")
        profession_id=resolve_profession_id(profession)
        if profession_id in folded_professions: raise ConfigError("professions cannot contain aliases for the same profession")
        folded_professions.add(profession_id)
        if not isinstance(values,dict) or not values: raise ConfigError(f"professions.{profession} must be a non-empty TOML table")
        _expect_keys(values,ROLE_OVERRIDE_KEYS,f"professions.{profession}")
        _short_text(values,"icon",f"professions.{profession}"); _model_name(values,"model",f"professions.{profession}"); _reasoning_effort(values,"reasoning",f"professions.{profession}")
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
    _bounded_int(monitoring, "default_review_horizon_minutes", 1, 60, "monitoring")
    _bounded_int(monitoring, "max_review_horizon_minutes", 1, 60, "monitoring")
    _bounded_int(monitoring, "small_task_review_horizon_minutes", 1, 20, "monitoring")
    _boolean(monitoring, "auto_health_enabled", "monitoring")
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
    """Migrate legacy structural task settings without creating professions."""
    normalized = deepcopy(raw)
    schema_version = normalized.get("schema_version", 1)
    legacy = schema_version == 1
    role_icons = normalized.get("role_icons", {})
    if isinstance(role_icons, dict) and "task_choices" in role_icons:
        role_icons.setdefault("doer_choices", role_icons.pop("task_choices"))
    boost = normalized.get("boost", {})
    if legacy and isinstance(boost, dict) and isinstance(boost.get("goal_levels"), list):
        levels = ["doer" if level == "task" else level for level in boost["goal_levels"]]
        levels = [level for level in levels if level != "assist"]
        boost["goal_levels"] = list(dict.fromkeys(levels)) or deepcopy(DEFAULTS["boost"]["goal_levels"])
    for profile in normalized.get("models", {}).values():
        if legacy and isinstance(profile, dict):
            for suffix in ("model", "reasoning"):
                legacy = f"task_{suffix}"
                profile.setdefault(f"doer_{suffix}", profile.pop(legacy, None)) if legacy in profile else None
    labels = normalized.get("labels", {})
    if legacy and isinstance(labels, dict) and "task" in labels:
        legacy_label = labels.pop("task")
        if legacy_label != "TASK":
            labels.setdefault("doer", legacy_label)

    roles=normalized.get("roles",{})
    professions=normalized.setdefault("professions",{})
    if isinstance(roles,dict) and isinstance(professions,dict):
        for role in tuple(roles):
            normalized_role=str(role).strip().casefold().replace(" ","_")
            if normalized_role in STRUCTURAL_CONFIG_ROLES: continue
            try: profession_id=resolve_profession_id(str(role))
            except ConfigError: continue
            professions.setdefault(profession_id,roles.pop(role))

    execution=normalized.setdefault("execution",{})
    legacy_fast_signals=[]
    canonical_fast_mode=isinstance(execution,dict) and "fast_mode" in execution
    root_fast_mode=normalized.pop("fast_mode",None)
    if root_fast_mode is not None:
        if not isinstance(root_fast_mode,bool):
            raise ConfigError("legacy root fast_mode must be true or false")
        legacy_fast_signals.append(("root.fast_mode",root_fast_mode))
    root_current_mode=normalized.pop("current_mode",None)
    if root_current_mode is not None:
        if not isinstance(root_current_mode,str) or root_current_mode.upper() not in {"FAST","STANDARD","DEFAULT"}:
            raise ConfigError("legacy root current_mode must be FAST, STANDARD, or DEFAULT")
        legacy_fast_signals.append(("root.current_mode",root_current_mode.upper()=="FAST"))
    if isinstance(execution,dict) and "current_mode" in execution:
        legacy_current_mode=execution.pop("current_mode")
        if not isinstance(legacy_current_mode,str) or legacy_current_mode.upper() not in {"FAST","STANDARD","DEFAULT"}:
            raise ConfigError("legacy execution.current_mode must be FAST, STANDARD, or DEFAULT")
        legacy_fast_signals.append(("execution.current_mode",legacy_current_mode.upper()=="FAST"))
    if isinstance(execution,dict) and "service_tier" in execution:
        legacy_service_tier=execution.pop("service_tier")
        if not isinstance(legacy_service_tier,str):
            raise ConfigError("legacy execution.service_tier must be text")
        if legacy_service_tier not in FAST_SERVICE_TIERS | {"default","flex"}:
            raise ConfigError("legacy execution.service_tier must be default, flex, fast, or priority")
        legacy_fast_signals.append(("execution.service_tier",legacy_service_tier in FAST_SERVICE_TIERS))
    efficiency=normalized.get("efficiency",{})
    if isinstance(efficiency,dict) and efficiency.get("mode")=="FAST":
        efficiency["mode"]="BALANCED"
        legacy_fast_signals.append(("efficiency.mode",True))
    if isinstance(execution,dict) and not canonical_fast_mode and legacy_fast_signals:
        values={value for _,value in legacy_fast_signals}
        if len(values)!=1:
            raise ConfigError("legacy Fast controls conflict; set execution.fast_mode explicitly")
        execution["fast_mode"]=values.pop()

    lifecycle=normalized.get("lifecycle",{})
    automation=normalized.get("automation")
    if automation is None:
        automation={}
        normalized["automation"]=automation
    if isinstance(lifecycle,dict) and "archive_completed_tasks" in lifecycle:
        legacy_archive=lifecycle.pop("archive_completed_tasks")
        if not isinstance(legacy_archive,bool):
            raise ConfigError("legacy lifecycle.archive_completed_tasks must be true or false")
        if isinstance(automation,dict) and "mode" not in automation:
            automation["mode"]="standard" if legacy_archive else "manual"

    normalized["schema_version"] = 4
    return normalized


def load(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return apply_turbo(deepcopy(DEFAULTS)), False
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc
    normalized = normalize_legacy_task_role(raw)
    validate(normalized)
    return apply_turbo(merge(normalized)), True


def apply_turbo(effective: dict[str, Any]) -> dict[str, Any]:
    """Resolve Turbo usage/efficiency controls without changing Fast mode."""
    if effective["turbo"]["enabled"]:
        effective["execution"]["usage_profile"] = "high"
        effective["efficiency"]["mode"] = "MAX"
    return effective


def resolve_profession_assignment(
    effective:dict[str,Any], profession:str, *, domain:str="", truth_surface:str="",
) -> dict[str,str]:
    """Resolve perspective metadata without granting structural authority."""
    profession_id=resolve_profession_id(profession)
    domain=domain.strip(); truth_surface=truth_surface.strip()
    if profession_id=="specialist" and (not domain or not truth_surface):
        raise ConfigError("Specialist profession requires a named domain and truth surface")
    override=next((value for name,value in effective["professions"].items() if resolve_profession_id(name)==profession_id),{})
    return {"profession_id":profession_id,"label":BUILT_IN_PROFESSIONS[profession_id],"domain":domain,"truth_surface":truth_surface,"icon":str(override.get("icon","")),"authority":"none"}


def resolve_role_assignment(
    effective: dict[str, Any], role: str, *, route_tier: int = 2,
    explicit_model: str | None = None, explicit_reasoning: str | None = None,
) -> dict[str, str]:
    """Resolve a host model/thinking pair and clamp thinking to global bounds."""
    if not isinstance(role, str) or not role.strip():
        raise ConfigError("role must be a non-empty string")
    if not _is_int(route_tier) or not 1 <= route_tier <= 3:
        raise ConfigError("route_tier must be 1, 2, or 3")
    normalized_role=role.strip().casefold().replace(" ","_")
    profession_id=""
    if normalized_role in STRUCTURAL_CONFIG_ROLES:
        role_key=normalized_role
    else:
        profession_id=resolve_profession_id(role)
        role_key="doer"
    profile_name = effective["execution"]["usage_profile"]
    profile = effective["models"][profile_name]
    model_key, reasoning_key = f"{role_key}_model", f"{role_key}_reasoning"
    def matches(custom_role:str)->bool:
        if custom_role.casefold()==role.casefold(): return True
        if not profession_id: return False
        try: return resolve_profession_id(custom_role)==profession_id
        except ConfigError: return False
    override_table=effective["roles"] if not profession_id else effective["professions"]
    custom_override=next((override for custom_role,override in override_table.items() if matches(custom_role)),None)
    if model_key not in profile or reasoning_key not in profile:
        if custom_override is None:
            raise ConfigError(f"role has no configured model pair: {role}")
        model_key, reasoning_key = "doer_model", "doer_reasoning"
    model, preferred = profile[model_key], profile[reasoning_key]
    reasoning_is_explicit = explicit_reasoning is not None
    if custom_override is not None:
        model = custom_override.get("model", model)
        preferred = custom_override.get("reasoning", preferred)
        reasoning_is_explicit = reasoning_is_explicit or "reasoning" in custom_override
    if explicit_model is not None:
        _model_name({"model": explicit_model}, "model", "explicit assignment")
        model = explicit_model
    if explicit_reasoning is not None:
        _reasoning_effort({"reasoning": explicit_reasoning}, "reasoning", "explicit assignment")
        preferred = explicit_reasoning
    low = REASONING_SCALE.index(effective["execution"]["min_reasoning"])
    high = REASONING_SCALE.index(effective["execution"]["max_reasoning"])
    capability = effective["model_capabilities"].get(model)
    if capability is None:
        raise ConfigError(f"selected model has no declared capabilities: {model}")
    supported = capability.get("reasoning")
    supported_indexes = (
        [REASONING_SCALE.index(effort) for effort in supported]
        if supported
        else list(range(len(REASONING_SCALE)))
    )
    allowed = [index for index in supported_indexes if low <= index <= high]
    if not allowed:
        raise ConfigError(
            f"global reasoning range has no declared supported value for model: {model}"
        )
    if reasoning_is_explicit:
        if supported and preferred not in supported:
            raise ConfigError(f"explicit reasoning is not declared for model {model}: {preferred}")
        selected = REASONING_SCALE.index(preferred)
    elif effective["turbo"]["enabled"]:
        selected = allowed[-1]
    else:
        selected = REASONING_SCALE.index(preferred) + (route_tier - 2)
        selected = min(allowed, key=lambda index: (abs(index - selected), index))
    return {"model": model, "reasoning": REASONING_SCALE[selected]}


def resolve_model_assignment(
    effective: dict[str, Any], role: str, *, surface: str, route_tier: int = 2,
    workload: str = "general", required_tools: tuple[str, ...] = (),
    explicit_model: str | None = None, explicit_reasoning: str | None = None,
    explicit_provider: str | None = None,
    host_actual_model: str | None = None, host_receipt: str | None = None,
    host_actual_service_tier: str | None = None,
    host_service_tier_receipt: str | None = None,
) -> dict[str, Any]:
    """Resolve requested controls without claiming unreported host execution."""
    if surface not in {"codex_task", "subagent"}: raise ConfigError("surface must be codex_task or subagent")
    if workload not in MODEL_WORKLOADS: raise ConfigError(f"unknown workload: {workload}")
    if not isinstance(required_tools, tuple) or any(not isinstance(tool, str) or not tool.strip() for tool in required_tools): raise ConfigError("required_tools must be a tuple of non-empty strings")
    if (host_actual_model is None) != (host_receipt is None): raise ConfigError("actual model verification requires both host model and receipt")
    if (host_actual_service_tier is None) != (host_service_tier_receipt is None): raise ConfigError("actual service-tier verification requires both host tier and response receipt")
    assignment=resolve_role_assignment(effective, role, route_tier=route_tier, explicit_model=explicit_model, explicit_reasoning=explicit_reasoning)
    capability=effective["model_capabilities"][assignment["model"]]
    provider=capability["provider"]
    if explicit_provider is not None and explicit_provider != provider: raise ConfigError(f"explicit provider {explicit_provider} does not match model provider {provider}")
    if workload not in capability["workloads"]: raise ConfigError(f"model {assignment['model']} does not declare workload: {workload}")
    missing=sorted(set(required_tools)-set(capability["tools"]))
    if missing: raise ConfigError(f"model {assignment['model']} does not declare required tool(s): {', '.join(missing)}")
    if host_actual_model is not None:
        if not isinstance(host_receipt,str) or not host_receipt.strip(): raise ConfigError("host model receipt must be exact and non-empty")
        if host_actual_model != assignment["model"]: raise ConfigError(f"host selected {host_actual_model}, requested {assignment['model']}")
    normalized_role=role.strip().casefold().replace(" ","_")
    if normalized_role in STRUCTURAL_CONFIG_ROLES:
        custom=next((value for name,value in effective["roles"].items() if name.casefold()==role.casefold()),{})
    else:
        profession_id=resolve_profession_id(role)
        custom=next((value for name,value in effective["professions"].items() if resolve_profession_id(name)==profession_id),{})
    explicit=any(value is not None for value in (explicit_model, explicit_reasoning, explicit_provider)) or any(key in custom for key in ("model","reasoning"))
    if effective["execution"]["fast_mode"]:
        requested_service_tier="fast"
        service_tier_source="fast_mode"
    else:
        requested_service_tier=""
        service_tier_source="host_default"
    requested_fast_mode=requested_service_tier in FAST_SERVICE_TIERS
    if host_actual_service_tier is not None:
        _short_text({"service_tier":host_actual_service_tier},"service_tier","host response")
        if not isinstance(host_service_tier_receipt,str) or not host_service_tier_receipt.strip():
            raise ConfigError("host service-tier response receipt must be exact and non-empty")
        prefix="host:response:"; marker=":service_tier:"
        if not host_service_tier_receipt.startswith(prefix) or marker not in host_service_tier_receipt[len(prefix):]:
            raise ConfigError("host service-tier receipt must bind response id and actual service tier")
        response_id,receipt_tier=host_service_tier_receipt[len(prefix):].rsplit(marker,1)
        if not response_id.strip() or receipt_tier!=host_actual_service_tier:
            raise ConfigError("host service-tier receipt does not match the actual service tier")
        actual_service_tier_verification="verified"
        fast_mode_status="ACTIVE" if host_actual_service_tier in FAST_SERVICE_TIERS else ("UNAVAILABLE" if requested_fast_mode else "OFF")
    else:
        actual_service_tier_verification="UNVERIFIED"
        fast_mode_status="UNAVAILABLE" if requested_fast_mode else "OFF"
    return {
        "surface":surface,"model":assignment["model"],"provider":provider,"reasoning_effort":assignment["reasoning"],
        "requested_fast_mode":requested_fast_mode,"requested_service_tier":requested_service_tier or None,
        "service_tier_selection_source":service_tier_source,
        "actual_service_tier":host_actual_service_tier,"actual_service_tier_verification":actual_service_tier_verification,
        "host_service_tier_receipt":host_service_tier_receipt,"fast_mode_status":fast_mode_status,
        "service_tier_claim_limit":"Request preference only; Fast mode is active only when an exact host response receipt reports fast or priority.",
        "selection_source":"explicit_user" if explicit else "configured_default",
        "actual_model":host_actual_model or "","actual_model_verification":"verified" if host_actual_model is not None else "UNVERIFIED",
        "host_model_receipt":host_receipt or "",
    }


def resolve_spark_assignment(
    effective: dict[str, Any], role: str, *, surface: str,
    required_tools: tuple[str, ...] = (), route_tier: int = 1,
    explicit_reasoning: str | None = None,
    host_actual_model: str | None = None, host_receipt: str | None = None,
    require_host_verification: bool = False,
) -> dict[str, Any]:
    """Resolve the opt-in Spark lane and reject work outside its safe scope."""
    boost = effective["boost"]
    if not boost["spark_enabled"]:
        raise ConfigError("Spark routing is disabled by boost.spark_enabled")
    if "spark_simple_work" not in boost["strategies"]:
        raise ConfigError("Spark routing requires boost.strategies to include spark_simple_work")
    if not isinstance(required_tools, tuple):
        raise ConfigError("required_tools must be a tuple of non-empty strings")
    unsupported = sorted(set(required_tools) - SPARK_SAFE_TOOLS)
    if unsupported:
        raise ConfigError(
            "Spark is limited to simple shell-only work; unsupported tool(s): "
            + ", ".join(unsupported)
        )
    receipt = resolve_model_assignment(
        effective,
        role,
        surface=surface,
        route_tier=route_tier,
        workload=SPARK_WORKLOAD,
        required_tools=required_tools,
        explicit_model=boost["spark_model"],
        explicit_reasoning=explicit_reasoning or boost["spark_reasoning"],
        host_actual_model=host_actual_model,
        host_receipt=host_receipt,
    )
    verified = receipt["actual_model_verification"] == "verified"
    if require_host_verification and not verified:
        raise ConfigError(
            "Spark host execution receipt required; routing is not countable without "
            "host_actual_model and host_receipt"
        )
    receipt["spark_usage_status"] = "verified" if verified else "requested_unverified"
    receipt["spark_usage_countable"] = verified
    return receipt


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
        "swarm_version": _plugin_version(),
        "config_schema_version": effective["schema_version"],
        "config_exists": exists,
        "usage_profile": effective["execution"]["usage_profile"],
        "fast_mode": effective["execution"]["fast_mode"],
        "automation_mode": effective["automation"]["mode"],
        "min_reasoning": effective["execution"]["min_reasoning"],
        "max_reasoning": effective["execution"]["max_reasoning"],
        "turbo_enabled": effective["turbo"]["enabled"],
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
        "spark_enabled": effective["boost"]["spark_enabled"],
        "spark_model": effective["boost"]["spark_model"],
        "spark_reasoning": effective["boost"]["spark_reasoning"],
        "spark_workload": SPARK_WORKLOAD,
        "spark_safe_tools": sorted(SPARK_SAFE_TOOLS),
        "feedback_destination_configured": bool(effective["feedback"]["destination"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default = resolve_config_path()
    parser.add_argument("--path", type=Path, default=default, help="SWARM config path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("path", help="print the global config path")
    show = subparsers.add_parser("show", help="print effective settings")
    show.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    feedback = subparsers.add_parser("feedback", help="print privacy-safe feedback diagnostics")
    feedback.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    resolve = subparsers.add_parser("resolve", help="resolve one role model and reasoning pair")
    resolve.add_argument("--role", required=True, help="configured SWARM role name")
    resolve.add_argument(
        "--route-tier",
        type=int,
        choices=(1, 2, 3),
        default=2,
        help="task route tier from 1 (light) to 3 (deep)",
    )
    assign = subparsers.add_parser("assign", help="emit one task or subagent model-assignment receipt")
    assign.add_argument("--role", required=True)
    assign.add_argument("--surface", required=True, choices=("codex_task", "subagent"))
    assign.add_argument("--route-tier", type=int, choices=(1, 2, 3), default=2)
    assign.add_argument("--workload", choices=tuple(sorted(MODEL_WORKLOADS)), default="general")
    assign.add_argument("--required-tool", action="append", default=[])
    assign.add_argument("--explicit-model")
    assign.add_argument("--explicit-reasoning", choices=tuple(REASONING_SCALE))
    assign.add_argument("--explicit-provider")
    assign.add_argument("--host-actual-model")
    assign.add_argument("--host-receipt")
    spark = subparsers.add_parser("spark", help="emit a bounded Spark model-assignment receipt")
    spark.add_argument("--role", required=True)
    spark.add_argument("--surface", required=True, choices=("codex_task", "subagent"))
    spark.add_argument("--route-tier", type=int, choices=(1, 2, 3), default=1)
    spark.add_argument("--required-tool", action="append", default=[])
    spark.add_argument("--explicit-reasoning", choices=tuple(REASONING_SCALE))
    spark.add_argument("--host-actual-model")
    spark.add_argument("--host-receipt")
    spark.add_argument("--require-host-verification", action="store_true")
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
        if args.command == "resolve":
            print(
                json.dumps(
                    resolve_role_assignment(
                        effective,
                        args.role,
                        route_tier=args.route_tier,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.command == "assign":
            print(json.dumps(resolve_model_assignment(
                effective,args.role,surface=args.surface,route_tier=args.route_tier,workload=args.workload,
                required_tools=tuple(args.required_tool),explicit_model=args.explicit_model,explicit_reasoning=args.explicit_reasoning,
                explicit_provider=args.explicit_provider,
                host_actual_model=args.host_actual_model,host_receipt=args.host_receipt,
            ),indent=2))
            return 0
        if args.command == "spark":
            print(json.dumps(resolve_spark_assignment(
                effective,
                args.role,
                surface=args.surface,
                route_tier=args.route_tier,
                required_tools=tuple(args.required_tool),
                explicit_reasoning=args.explicit_reasoning,
                host_actual_model=args.host_actual_model,
                host_receipt=args.host_receipt,
                require_host_verification=args.require_host_verification,
            ), indent=2))
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
