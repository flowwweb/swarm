"""Safe, deterministic SWARM skill catalog and inheritance rules.

This module contains no installation or provider authority.  The console uses
it only to validate metadata, match a task to approved skills, and classify a
skill as inherited, available to install, blocked, or irrelevant.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SKILL_CATALOG_VERSION = 1
SKILL_SCOPE_TYPES = {"global", "project", "ctrl"}
SKILL_PROFILES = {"default", "discovery", "debug", "testing", "verification", "web_qa", "design"}
PROFILE_SKILL_IDS = {
    "default": {"find-skills", "systematic-debugging", "test-driven-development", "verification-before-completion", "webapp-testing", "frontend-design"},
    "discovery": {"find-skills"},
    "debug": {"systematic-debugging", "verification-before-completion"},
    "testing": {"test-driven-development", "verification-before-completion", "webapp-testing"},
    "verification": {"verification-before-completion"},
    "web_qa": {"webapp-testing", "verification-before-completion"},
    "design": {"frontend-design"},
}
APPROVED_REVIEW_STATES = {"approved", "built_in"}


SKILL_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "skill_id": "find-skills",
        "source_repo": "vercel-labs/skills",
        "source_path": "skills/find-skills",
        "source_ref": "main",
        "source_version": "main",
        "review_status": "candidate",
        "installed": False,
        "builtin": False,
        "allowed_roles": ["CTRL", "LEAD", "RESEARCHER"],
        "allowed_task_kinds": ["DISCOVERY", "GENERAL"],
    },
    {
        "skill_id": "systematic-debugging",
        "source_repo": "obra/superpowers",
        "source_path": "skills/systematic-debugging",
        "source_ref": "main",
        "source_version": "main",
        "review_status": "candidate",
        "installed": False,
        "builtin": False,
        "allowed_roles": ["LEAD", "DOER", "REVIEW"],
        "allowed_task_kinds": ["DEBUG", "GENERAL"],
    },
    {
        "skill_id": "test-driven-development",
        "source_repo": "obra/superpowers",
        "source_path": "skills/test-driven-development",
        "source_ref": "main",
        "source_version": "main",
        "review_status": "candidate",
        "installed": False,
        "builtin": False,
        "allowed_roles": ["LEAD", "DOER", "REVIEW"],
        "allowed_task_kinds": ["CODE", "TESTING"],
    },
    {
        "skill_id": "verification-before-completion",
        "source_repo": "obra/superpowers",
        "source_path": "skills/verification-before-completion",
        "source_ref": "main",
        "source_version": "main",
        "review_status": "candidate",
        "installed": False,
        "builtin": False,
        "allowed_roles": ["CTRL", "LEAD", "REVIEW"],
        "allowed_task_kinds": ["VERIFICATION", "CODE", "GENERAL"],
    },
    {
        "skill_id": "webapp-testing",
        "source_repo": "anthropics/skills",
        "source_path": "skills/webapp-testing",
        "source_ref": "main",
        "source_version": "main",
        "review_status": "candidate",
        "installed": False,
        "builtin": False,
        "allowed_roles": ["LEAD", "DOER", "REVIEW"],
        "allowed_task_kinds": ["WEB_QA", "TESTING"],
    },
    {
        "skill_id": "frontend-design",
        "source_repo": "anthropics/skills",
        "source_path": "skills/frontend-design",
        "source_ref": "main",
        "source_version": "main",
        "review_status": "candidate",
        "installed": False,
        "builtin": False,
        "allowed_roles": ["DESIGNER", "LEAD", "DOER"],
        "allowed_task_kinds": ["DESIGN", "WEB"],
    },
    {
        "skill_id": "swarm",
        "source_repo": "flowwweb/swarm",
        "source_path": "skills/swarm",
        "source_ref": "bundled",
        "source_version": "bundled",
        "review_status": "built_in",
        "installed": True,
        "builtin": True,
        "allowed_roles": ["CTRL", "LEAD", "DOER", "REVIEW", "DESIGNER", "RESEARCHER"],
        "allowed_task_kinds": ["GENERAL", "DISCOVERY", "CODE", "TESTING", "VERIFICATION", "WEB_QA", "DESIGN", "WEB", "DEBUG"],
    },
    {
        "skill_id": "product-qc",
        "source_repo": "flowwweb/product-qc",
        "source_path": "skills/product-qc",
        "source_ref": "bundled",
        "source_version": "bundled",
        "review_status": "built_in",
        "installed": True,
        "builtin": True,
        "allowed_roles": ["CTRL", "LEAD", "REVIEW", "DOER"],
        "allowed_task_kinds": ["VERIFICATION", "TESTING", "WEB_QA", "GENERAL"],
    },
)


def validate_scope(scope_type: Any, scope_id: Any) -> tuple[str, str]:
    if not isinstance(scope_type, str) or scope_type not in SKILL_SCOPE_TYPES:
        raise ValueError("skill scope must be global, project, or ctrl")
    if not isinstance(scope_id, str) or not scope_id.strip() or len(scope_id) > 256:
        raise ValueError("skill scope id must be non-empty text up to 256 characters")
    scope_id = scope_id.strip()
    if scope_type == "global" and scope_id != "global":
        raise ValueError("global skill scope id must be global")
    return scope_type, scope_id


def validate_profile(value: Any) -> str:
    if not isinstance(value, str) or value not in SKILL_PROFILES:
        raise ValueError("skill profile is not allowlisted")
    return value


def validate_preferred_ids(value: Any, known_ids: set[str]) -> list[str]:
    if not isinstance(value, list) or len(value) > 16 or any(not isinstance(item, str) for item in value):
        raise ValueError("preferred skill ids must be a list of up to 16 strings")
    result = list(dict.fromkeys(value))
    unknown = sorted(set(result) - known_ids)
    if unknown:
        raise ValueError(f"unknown skill id(s): {', '.join(unknown)}")
    return result


def seed_rows(now_ms: int) -> list[dict[str, Any]]:
    rows = []
    for seed in SKILL_SEEDS:
        row = deepcopy(seed)
        row.update({
            "popularity": {"status": "informational", "value": "unknown"},
            "audit": {"status": "not_checked_in_this_runtime", "informational": True},
            "last_checked_ms": 0,
            "updated_at_ms": now_ms,
        })
        rows.append(row)
    return rows


def is_relevant(skill: dict[str, Any], role: str | None, task_kind: str | None) -> bool:
    if role and role.upper() not in set(skill.get("allowed_roles") or []):
        return False
    if task_kind and task_kind.upper() not in set(skill.get("allowed_task_kinds") or []):
        return False
    return True


def is_authority_safe(skill: dict[str, Any]) -> bool:
    """Reject catalog metadata that attempts to grant an extra capability."""
    return not any(skill.get(key) for key in ("authority", "permissions", "capabilities"))


def resolve(
    catalog: list[dict[str, Any]],
    global_scope: dict[str, Any] | None,
    project_scope: dict[str, Any] | None,
    ctrl_scope: dict[str, Any] | None,
    *,
    role: str | None = None,
    task_kind: str | None = None,
    global_enabled: bool = True,
    global_profile: str = "default",
    global_preferred: list[str] | None = None,
) -> dict[str, Any]:
    settings = {
        "inheritance_enabled": global_enabled,
        "profile": validate_profile(global_profile),
        "preferred_ids": list(global_preferred or []),
    }
    for overlay in (project_scope, ctrl_scope):
        if not overlay:
            continue
        if overlay.get("inheritance_enabled") is not None:
            settings["inheritance_enabled"] = bool(overlay["inheritance_enabled"])
        if overlay.get("profile"):
            settings["profile"] = validate_profile(overlay["profile"])
        if overlay.get("preferred_ids") is not None:
            settings["preferred_ids"] = list(overlay["preferred_ids"])

    skills = []
    for skill in sorted(catalog, key=lambda item: str(item.get("skill_id", ""))):
        relevant = is_relevant(skill, role, task_kind)
        authority_safe = is_authority_safe(skill)
        approved = authority_safe and (bool(skill.get("builtin")) or skill.get("review_status") in APPROVED_REVIEW_STATES)
        installed = bool(skill.get("installed"))
        selected = bool(skill.get("builtin")) or (
            skill["skill_id"] in settings["preferred_ids"]
            and skill["skill_id"] in PROFILE_SKILL_IDS[settings["profile"]]
        )
        inherited = bool(settings["inheritance_enabled"] and relevant and approved and installed and selected)
        if inherited:
            status = "inherited"
        elif relevant and not authority_safe:
            status = "blocked_authority"
        elif relevant and not approved:
            status = "blocked_unreviewed"
        elif relevant and not selected:
            status = "not_selected"
        elif relevant and not installed and approved:
            status = "available_to_install"
        else:
            status = "not_relevant"
        skills.append({
            "skill_id": skill["skill_id"],
            "source": {
                "repo": skill["source_repo"],
                "path": skill["source_path"],
                "ref": skill["source_ref"],
                "version": skill["source_version"],
            },
            "review_status": skill["review_status"],
            "installed": installed,
            "builtin": bool(skill.get("builtin")),
            "relevant": relevant,
            "status": status,
            "preferred": skill["skill_id"] in settings["preferred_ids"],
            "selected": selected,
            "popularity": skill.get("popularity", {"status": "informational", "value": "unknown"}),
            "audit": skill.get("audit", {"status": "unknown", "informational": True}),
            "authority_safe": authority_safe,
            "last_checked_ms": int(skill.get("last_checked_ms") or 0),
        })
    return {
        "catalog_version": SKILL_CATALOG_VERSION,
        "settings": settings,
        "skills": skills,
        "claim_limit": "Matching is deterministic and read-only. Skills never grant tools, credentials, host authority, or installation permission.",
    }
