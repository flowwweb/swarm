#!/usr/bin/env python3
"""Local SWARM settings, hierarchy, and analytics console."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import webbrowser
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
CONFIG_SCRIPT = PLUGIN_ROOT / "skills" / "swarm" / "scripts" / "swarm_config.py"
DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
DEFAULT_CONFIG_PATH = Path.home() / ".agents" / "swarm" / "config.toml"
DEFAULT_PORT = 4788
MAX_BODY_BYTES = 64 * 1024
PORTAL_PRESENCE_TTL_SECONDS = 150
CHAT_RELAY_USAGE_LOG_NAME = "chat-relay-usage.json"
CHAT_RELAY_USAGE_MAX_EVENTS = 100
MIN_OBSERVATION_WINDOW_MS = 24 * 60 * 60 * 1000
OBSERVATION_HEARTBEAT_WINDOWS = 48

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/swarm-favicon.svg": ("swarm-favicon.svg", "image/svg+xml"),
}
PWA_MANIFEST = {
    "id": "/",
    "name": "SWARM Console",
    "short_name": "SWARM",
    "description": "Local SWARM control and analytics console",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#02071f",
    "theme_color": "#02071f",
    "icons": [
        {
            "src": "/swarm-favicon.svg",
            "sizes": "128x128",
            "type": "image/svg+xml",
            "purpose": "any",
        }
    ],
}
SERVICE_WORKER_SOURCE = r'''const CACHE_NAME = "swarm-console-shell-v1";
const SHELL_PATHS = [
  "/",
  "/index.html",
  "/app.js",
  "/styles.css",
  "/manifest.webmanifest",
  "/swarm-favicon.svg",
  "/assets/swarm-wordmark.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_PATHS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  const cacheable = request.method === "GET"
    && url.origin === self.location.origin
    && !url.pathname.startsWith("/api/")
    && ["document", "script", "style", "image", "manifest"].includes(request.destination);
  if (!cacheable) return;

  event.respondWith(
    fetch(request).then((response) => {
      if (response.ok) {
        caches.open(CACHE_NAME).then((cache) => cache.put(request, response.clone()));
      }
      return response;
    }).catch(() => caches.match(request).then((cached) => {
      if (cached) return cached;
      return request.mode === "navigate" ? caches.match("/") : Response.error();
    })),
  );
});
'''
GENERATED_STATIC_FILES = {
    "/manifest.webmanifest": (
        (json.dumps(PWA_MANIFEST, indent=2, ensure_ascii=True) + "\n").encode("utf-8"),
        "application/manifest+json; charset=utf-8",
    ),
    "/sw.js": (SERVICE_WORKER_SOURCE.encode("utf-8"), "text/javascript; charset=utf-8"),
}
STATIC_ASSETS = {
    "/assets/swarm-wordmark.png": (
        PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-wordmark.png",
        "image/png",
    ),
}

EDITABLE_SETTINGS: dict[str, type] = {
    "portfolio.max_active_tasks": int,
    "portfolio.default_parallel_tasks": int,
    "portfolio.reuse_existing_tasks": bool,
    "execution.usage_profile": str,
    "execution.service_tier": str,
    "execution.min_reasoning": str,
    "execution.max_reasoning": str,
    "execution.usage_saver": bool,
    "chat_relay.enabled": bool,
    "chat_relay.routing_mode": str,
    "chat_relay.offload_level": str,
    "chat_relay.default_model": str,
    "chat_relay.default_effort": str,
    "chat_relay.challenging_model": str,
    "chat_relay.challenging_effort": str,
    "chat_relay.executor_enabled": bool,
    "chat_relay.executor_write_mode": str,
    "chat_relay.executor_command_mode": str,
    "chat_relay.executor_require_confirmation": bool,
    "logging.task_event_limit": int,
    "console.open_on_start": bool,
    "boost.enabled": bool,
    "coordination.allow_coordinators": bool,
    "coordination.coordinator_min_children": int,
    "coordination.preferred_lane_width": int,
    "subagents.enabled": bool,
    "subagents.max_per_task": int,
    "review.task_enabled": bool,
    "review.max_parallel_tasks": int,
    "review.scale_when_queue_reaches": int,
    "monitoring.heartbeat_minutes": int,
    "recovery.stall_after_updates": int,
    "lifecycle.pin_created_tasks": bool,
    "lifecycle.archive_completed_tasks": bool,
    "feedback.enabled": bool,
    "feedback.include_diagnostics": bool,
    "feedback.prompt_on_close": bool,
    "labels.lead": str,
    "labels.doer": str,
    "labels.review": str,
    "role_icons.enabled": bool,
    "role_icons.ctrl": str,
    "role_icons.lead": str,
    "role_icons.review": str,
    "role_icons.fallback": str,
}


class ConsoleError(RuntimeError):
    """Expected, user-visible console failure."""


def load_config_module() -> Any:
    spec = importlib.util.spec_from_file_location("swarm_console_config", CONFIG_SCRIPT)
    if not spec or not spec.loader:
        raise ConsoleError(f"could not load SWARM config validator: {CONFIG_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_config(config_path: Path) -> tuple[Any, dict[str, Any], bool]:
    module = load_config_module()
    try:
        effective, exists = module.load(config_path)
    except Exception as exc:  # ConfigError is owned by the loaded module.
        raise ConsoleError(str(exc)) from exc
    return module, effective, exists

def resolve_config_path(config_path: Path|None=None) -> Path:
    return load_config_module().resolve_config_path(config_path)


def redacted_config_snapshot(config_path: Path) -> dict[str, Any]:
    _, effective, exists = load_config(config_path)
    safe = json.loads(json.dumps(effective))
    destination = safe.get("feedback", {}).get("destination", "")
    if "feedback" in safe:
        safe["feedback"]["destination"] = ""
        safe["feedback"]["destination_configured"] = bool(destination)
    return {
        "exists": exists,
        "path": str(config_path),
        "settings": safe,
        "editable": sorted(EDITABLE_SETTINGS),
    }


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise ConsoleError(f"unsupported setting value: {type(value).__name__}")


def _replace_toml_setting(text: str, dotted_key: str, value: Any) -> str:
    section, key = dotted_key.split(".", 1)
    lines = text.splitlines()
    section_re = re.compile(rf"^\s*\[{re.escape(section)}\]\s*(?:#.*)?$")
    any_section_re = re.compile(r"^\s*\[[^]]+\]\s*(?:#.*)?$")
    key_re = re.compile(rf"^(\s*){re.escape(key)}\s*=.*$")
    start = next((i for i, line in enumerate(lines) if section_re.match(line)), None)
    rendered = f"{key} = {_toml_value(value)}"

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend((f"[{section}]", rendered))
        return "\n".join(lines) + "\n"

    end = next(
        (i for i in range(start + 1, len(lines)) if any_section_re.match(lines[i])),
        len(lines),
    )
    for index in range(start + 1, end):
        match = key_re.match(lines[index])
        if match:
            lines[index] = f"{match.group(1)}{rendered}"
            return "\n".join(lines) + "\n"

    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, rendered)
    return "\n".join(lines) + "\n"


def update_config(config_path: Path, changes: dict[str, Any]) -> dict[str, Any]:
    if not changes:
        raise ConsoleError("no settings changed")
    if len(changes) > 32:
        raise ConsoleError("too many settings in one update")

    for dotted_key, value in changes.items():
        expected = EDITABLE_SETTINGS.get(dotted_key)
        if not expected:
            raise ConsoleError(f"setting is not editable here: {dotted_key}")
        if expected is int and (not isinstance(value, int) or isinstance(value, bool)):
            raise ConsoleError(f"{dotted_key} must be an integer")
        if expected is bool and not isinstance(value, bool):
            raise ConsoleError(f"{dotted_key} must be a boolean")
        if expected is str and not isinstance(value, str):
            raise ConsoleError(f"{dotted_key} must be text")

    module, _, exists = load_config(config_path)
    if exists:
        text = config_path.read_text(encoding="utf-8")
    else:
        text = (PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-config.toml").read_text(
            encoding="utf-8"
        )
    for dotted_key, value in changes.items():
        text = _replace_toml_setting(text, dotted_key, value)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=config_path.parent, delete=False
        ) as handle:
            handle.write(text)
            temporary = Path(handle.name)
        module.load(temporary)
        if config_path.exists():
            shutil.copy2(config_path, config_path.with_suffix(".toml.swarm-console.bak"))
        os.replace(temporary, config_path)
        temporary = None
    except Exception as exc:
        raise ConsoleError(str(exc)) from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)
    return redacted_config_snapshot(config_path)


def state_database(codex_home: Path) -> Path:
    candidates = (codex_home / "state_5.sqlite", codex_home / "sqlite" / "state_5.sqlite")
    return next((path for path in candidates if path.exists()), candidates[0])


def chat_relay_usage_path(config_path: Path) -> Path:
    return config_path.resolve().parent / CHAT_RELAY_USAGE_LOG_NAME


def read_chat_relay_usage(path: Path) -> dict[str, Any]:
    empty = {"schema_version": 2, "events": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = empty
    raw_events = payload.get("events", []) if isinstance(payload, dict) and payload.get("schema_version") == 2 else []
    events: list[dict[str, Any]] = []
    if isinstance(raw_events, list):
        for raw in raw_events[-CHAT_RELAY_USAGE_MAX_EVENTS:]:
            if not isinstance(raw, dict) or not all(isinstance(raw.get(key), str) for key in (
                "recorded_at", "task_id", "purpose", "model", "effort", "host_receipt",
                "transport", "client_thread_id", "thread_id", "request_id", "response_id",
                "latency_source", "usage_status", "usage_reason",
            )):
                continue
            if raw["usage_status"] not in {"reported", "partial", "unavailable"}:
                continue
            if not all(raw.get(key) is None or isinstance(raw.get(key), int) and not isinstance(raw.get(key), bool) and raw.get(key) >= 0 for key in ("input_tokens", "output_tokens", "total_tokens")):
                continue
            if raw.get("latency_ms") is not None and (
                isinstance(raw.get("latency_ms"), bool)
                or not isinstance(raw.get("latency_ms"), (int, float))
                or raw.get("latency_ms") < 0
            ):
                continue
            if not isinstance(raw.get("asset_ids"), list) or not all(isinstance(item, str) and item for item in raw["asset_ids"]):
                continue
            events.append({key: raw[key] for key in (
                "recorded_at", "task_id", "purpose", "model", "effort", "host_receipt",
                "transport", "client_thread_id", "thread_id", "request_id", "response_id",
                "asset_ids", "latency_ms", "latency_source", "input_tokens", "output_tokens", "total_tokens",
                "usage_status", "usage_reason",
            )})
    task_ids = {event["task_id"] for event in events if event["task_id"]}
    reported_events = [event for event in events if event["usage_status"] == "reported"]
    partial_events = [event for event in events if event["usage_status"] == "partial"]
    return {
        "schema_version": 2,
        "consultations": len(events),
        "routed_tasks": len(task_ids),
        "reported_usage_consultations": len(reported_events),
        "partial_usage_consultations": len(partial_events),
        "unavailable_usage_consultations": len(events) - len(reported_events) - len(partial_events),
        "reported_input_tokens": sum(event["input_tokens"] or 0 for event in events),
        "reported_output_tokens": sum(event["output_tokens"] or 0 for event in events),
        "reported_total_tokens": sum(event["total_tokens"] or 0 for event in events),
        "savings_status": "unavailable",
        "legacy_estimates_discarded": isinstance(payload, dict) and payload.get("schema_version") == 1,
        "events": events[-20:],
        "claim_limit": "No savings claim: this ledger records provider usage only and has no equivalent local baseline.",
    }


def _readonly_connection(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise ConsoleError(f"Codex state database not found: {path}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 2000")
    return connection


def observation_fingerprint(codex_home: Path, config_path: Path) -> tuple[tuple[str, int, int], ...]:
    """Return only cheap local metadata needed to invalidate a console snapshot."""
    database = state_database(codex_home)
    paths = (database, database.with_name(f"{database.name}-wal"), config_path)
    fingerprint: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            stat = path.stat()
            fingerprint.append((path.name, stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            fingerprint.append((path.name, 0, 0))
    return tuple(fingerprint)


def _epoch_ms(milliseconds: Any, seconds: Any) -> int:
    if milliseconds:
        return int(milliseconds)
    if not seconds:
        return 0
    value = int(seconds)
    return value if value > 10**12 else value * 1000


def _project_identity(row: sqlite3.Row) -> tuple[str, str]:
    origin = (row["git_origin_url"] or "").rstrip("/")
    if origin:
        slug = origin.rsplit("/", 1)[-1]
        if slug.endswith(".git"):
            slug = slug[:-4]
        authority = f"origin:{origin.casefold()}"
        return f"project:{hashlib.sha256(authority.encode()).hexdigest()[:16]}", slug or "Repository"
    cwd = (row["cwd"] or "").replace("\\?\\", "").rstrip("\\/")
    name = re.split(r"[\\/]", cwd)[-1] if cwd else "Local"
    authority = f"cwd:{cwd.casefold()}"
    return f"project:{hashlib.sha256(authority.encode()).hexdigest()[:16]}", name or "Local"


def _role_from_title(
    title: str,
    labels: dict[str, str],
    role_icons: dict[str, Any],
    roles: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    if not title or len(title) > 180 or "\n" in title or "\r" in title:
        return None
    match = re.match(r"^(?P<head>.{1,48}?)\s*(?:-|—|·)\s*(?P<artifact>.{1,120})$", title)
    if not match:
        return None
    head = match.group("head").strip()
    artifact = match.group("artifact").strip().rstrip("…")
    configured = sorted(
        ((kind, str(label)) for kind, label in labels.items() if label),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    role_kind = "doer"
    role_label = ""
    role_start = -1
    for kind, label in configured:
        found = head.casefold().rfind(label.casefold())
        if found >= 0 and not head[found + len(label) :].strip():
            role_kind, role_label, role_start = ("doer" if kind == "task" else kind), label, found
            break
    if not role_label:
        role_match = re.search(r"([A-Z][A-Z0-9 /&]{1,23})$", head)
        if not role_match:
            return None
        role_label = role_match.group(1).strip()
        role_start = role_match.start(1)
        upper = role_label.upper()
        if upper == "CTRL":
            role_kind = "ctrl"
        elif upper == "MOTHER":
            role_kind = "specialist"
        elif upper == "LEAD":
            role_kind = "lead"
        elif upper == "DOER":
            role_kind = "doer"
        elif upper == "REVIEW":
            role_kind = "review"
    icon = ""
    if role_icons["enabled"]:
        if role_kind in {"ctrl", "lead", "review"}:
            icon = str(role_icons[role_kind])
        elif role_kind == "specialist" and role_label.casefold() == "mother":
            mother = next(
                (
                    value
                    for name, value in (roles or {}).items()
                    if name.casefold() == "mother" and isinstance(value, dict)
                ),
                {},
            )
            icon = str(mother.get("icon", "🐝"))
        else:
            upper = role_label.upper()
            preferred = next(
                (
                    value
                    for marker, value in (
                        (("DEV", "ENGINEER", "CODE"), "💻"),
                        (("DESIGN", "ART"), "🎨"),
                        (("TEST", "QA", "REVIEW"), "🧪"),
                        (("BUILD", "IMPLEMENT"), "🔨"),
                        (("RESEARCH", "DOC"), "📚"),
                    )
                    if any(token in upper for token in marker)
                ),
                str(role_icons["fallback"]),
            )
            choices = {str(value) for value in role_icons.get("doer_choices", [])}
            icon = preferred if preferred in choices else str(role_icons["fallback"])
    return {
        "role": role_kind,
        "role_label": role_label,
        "icon": icon,
        "artifact": artifact,
        "title": f"{icon}{role_label} - {artifact}",
    }


def _status(row: sqlite3.Row, edge_status: str | None, heartbeat_minutes: int, now_ms: int) -> str:
    if row["archived"]:
        return "archived"
    if edge_status == "closed":
        return "done"
    updated_ms = _epoch_ms(row["updated_at_ms"], row["updated_at"])
    if updated_ms and now_ms - updated_ms <= heartbeat_minutes * 2 * 60_000:
        return "active"
    return "quiet"


def _generic_agent_role(
    row: sqlite3.Row,
    role_icons: dict[str, Any],
    *,
    controller: bool = False,
) -> dict[str, str]:
    """Represent an observed child without exposing its prompt-like host title."""
    nickname = str(row["agent_nickname"] or "").strip()
    path_name = str(row["agent_path"] or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    safe_path = re.sub(r"[^A-Za-z0-9_-]", "", path_name).strip()[:80]
    path_tokens = [token for token in re.split(r"[_-]+", safe_path) if token]
    role_suffixes = {"architect", "designer", "dev", "developer", "lead", "researcher", "review", "reviewer"}
    while path_tokens and path_tokens[-1].casefold() in role_suffixes:
        path_tokens.pop()
    path_tokens = [token for token in path_tokens if not re.fullmatch(r"[0-9a-f]{6,}", token, re.I)]
    if len(path_tokens) > 2:
        path_tokens = [path_tokens[0], path_tokens[-1]]
    artifact = " ".join(path_tokens) or "Task"
    artifact = re.sub(r"(?i)\bgate\s*(\d+)\b", r"Gate \1", artifact).strip().title()[:48]
    if controller:
        artifact = "Current SWARM"
    worker = re.sub(r"[^A-Za-z0-9 _-]", "", nickname).strip()[:48] if "\n" not in nickname else ""
    role = "ctrl" if controller else "doer"
    role_label = "CTRL" if controller else "AGENT"
    if not controller:
        path_key = safe_path.casefold()
        if "lead" in path_key:
            role, role_label = "lead", "LEAD"
        elif "review" in path_key:
            role, role_label = "review", "REVIEW"
        elif any(marker in path_key for marker in ("developer", " dev", "dev ")):
            role_label = "DEV"
        elif "architect" in path_key:
            role_label = "ARCHITECT"
    icon = ""
    if role_icons["enabled"]:
        icon = str(role_icons[role]) if role in {"ctrl", "lead", "review"} else str(role_icons["fallback"])
    return {
        "role": role,
        "role_label": role_label,
        "icon": icon,
        "artifact": artifact,
        "worker": worker,
        "title": f"{icon}{role_label} - {artifact}",
    }


def build_overview(codex_home: Path, config_path: Path) -> dict[str, Any]:
    started_at = time.perf_counter()
    _, config, _ = load_config(config_path)
    labels = config["labels"]
    heartbeat = int(config["monitoring"]["heartbeat_minutes"])
    database = state_database(codex_home)
    now_ms = int(time.time() * 1000)
    observation_window_ms = max(
        MIN_OBSERVATION_WINDOW_MS,
        heartbeat * OBSERVATION_HEARTBEAT_WINDOWS * 60_000,
    )
    observed_after_ms = now_ms - observation_window_ms
    with closing(_readonly_connection(database)) as connection:
        thread_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(threads)").fetchall()
        }
        agent_path_projection = "agent_path" if "agent_path" in thread_columns else "'' AS agent_path"
        rows = connection.execute(
            f"""
            SELECT id, title, cwd, created_at, updated_at, created_at_ms, updated_at_ms,
                   model, reasoning_effort, tokens_used, archived, git_origin_url,
                   git_branch, thread_source, agent_nickname, agent_role, is_pinned,
                   {agent_path_projection}
            FROM threads
            WHERE archived = 0
              AND (
                updated_at_ms >= ?
                OR (updated_at_ms IS NULL AND updated_at >= ?)
              )
            """,
            (observed_after_ms, observed_after_ms // 1000),
        ).fetchall()
        edge_rows = connection.execute(
            """
            SELECT parent_thread_id, child_thread_id, status
            FROM thread_spawn_edges
            """
        ).fetchall()

    all_rows = {row["id"]: row for row in rows}
    parsed_titles = {
        thread_id: role
        for thread_id, row in all_rows.items()
        if (
            role := _role_from_title(
                row["title"], labels, config["role_icons"], config["roles"]
            )
        )
    }
    parent_by_child = {edge["child_thread_id"]: edge["parent_thread_id"] for edge in edge_rows}
    edge_status = {edge["child_thread_id"]: edge["status"] for edge in edge_rows}
    raw_children: dict[str, list[str]] = {}
    for edge in edge_rows:
        raw_children.setdefault(edge["parent_thread_id"], []).append(edge["child_thread_id"])
    recent_ids = {
        thread_id
        for thread_id, row in all_rows.items()
        if _epoch_ms(row["updated_at_ms"], row["updated_at"]) >= observed_after_ms
    }
    fresh_after_ms = now_ms - heartbeat * 2 * 60_000
    fresh_ids = {
        thread_id
        for thread_id, row in all_rows.items()
        if _epoch_ms(row["updated_at_ms"], row["updated_at"]) >= fresh_after_ms
    }
    root_candidate_ids = {
        parent
        for parent, child_ids in raw_children.items()
        if parent in all_rows
        and parent not in parent_by_child
        and any(
            child in fresh_ids
            and str(all_rows[child]["agent_path"] or "").replace("\\", "/").startswith("/root/")
            for child in child_ids
            if child in all_rows
        )
    }
    recent_parsed_ids = recent_ids.intersection(parsed_titles)
    controller_seed_ids = {
        thread_id
        for thread_id in recent_parsed_ids
        if parsed_titles[thread_id]["role"] == "ctrl"
    }.union(root_candidate_ids.intersection(recent_ids))
    descendant_ids: set[str] = set()
    traversed_ids: set[str] = set(controller_seed_ids)
    queue = list(controller_seed_ids)
    while queue:
        parent = queue.pop()
        for child in raw_children.get(parent, []):
            if child in traversed_ids:
                continue
            traversed_ids.add(child)
            child_path = (
                str(all_rows[child]["agent_path"] or "").replace("\\", "/")
                if child in all_rows else ""
            )
            if child in recent_ids and (
                child in parsed_titles or (child in fresh_ids and child_path.startswith("/root/"))
            ):
                descendant_ids.add(child)
            queue.append(child)
    # A formatted title is classification evidence, not a spawn receipt. Admit
    # only controllers and tasks reached through their observed host spawn tree.
    included_ids = controller_seed_ids.union(descendant_ids)
    # Agent replacement preserves the task identity expressed by its lane path.
    # Keep the latest worker receipt instead of turning replacement into a new node.
    latest_by_task: dict[tuple[str, str], str] = {}
    superseded_ids: set[str] = set()
    for thread_id in included_ids:
        if thread_id in parsed_titles or thread_id in controller_seed_ids:
            continue
        lane_path = str(all_rows[thread_id]["agent_path"] or "").replace("\\", "/").casefold()
        if not lane_path.startswith("/root/"):
            continue
        owner = thread_id
        seen: set[str] = set()
        while owner in parent_by_child and owner not in seen:
            seen.add(owner)
            owner = parent_by_child[owner]
            if owner in controller_seed_ids:
                break
        key = (owner, lane_path)
        previous = latest_by_task.get(key)
        if previous is None:
            latest_by_task[key] = thread_id
            continue
        previous_updated = _epoch_ms(all_rows[previous]["updated_at_ms"], all_rows[previous]["updated_at"])
        current_updated = _epoch_ms(all_rows[thread_id]["updated_at_ms"], all_rows[thread_id]["updated_at"])
        if current_updated >= previous_updated:
            superseded_ids.add(previous)
            latest_by_task[key] = thread_id
        else:
            superseded_ids.add(thread_id)
    included_ids.difference_update(superseded_ids)
    connected_ids = set(controller_seed_ids.intersection(included_ids))
    queue = list(connected_ids)
    while queue:
        parent = queue.pop()
        for child in raw_children.get(parent, []):
            if child in included_ids and child not in connected_ids:
                connected_ids.add(child)
                queue.append(child)
    included_ids.intersection_update(connected_ids)
    parsed = {
        thread_id: parsed_titles.get(thread_id) or _generic_agent_role(
            all_rows[thread_id],
            config["role_icons"],
            controller=thread_id in root_candidate_ids,
        )
        for thread_id in included_ids
    }

    nodes: dict[str, dict[str, Any]] = {}
    projects: dict[str, dict[str, Any]] = {}
    for thread_id, role in parsed.items():
        row = all_rows[thread_id]
        delegated_task = role["role"] != "ctrl"
        worker_role = role["role_label"] if delegated_task else ""
        visible_role_label = "TASK" if delegated_task else role["role_label"]
        visible_icon = (
            str(config["role_icons"]["fallback"])
            if delegated_task and config["role_icons"]["enabled"]
            else role["icon"]
        )
        project_key, project_name = _project_identity(row)
        created_ms = _epoch_ms(row["created_at_ms"], row["created_at"])
        updated_ms = _epoch_ms(row["updated_at_ms"], row["updated_at"])
        project = projects.setdefault(
            project_key,
            {"id": project_key, "name": project_name, "nodes": 0, "tokens": 0, "active": 0},
        )
        status = _status(row, edge_status.get(thread_id), heartbeat, now_ms)
        node = {
            "id": thread_id,
            **role,
            "role_label": visible_role_label,
            "icon": visible_icon,
            "title": f"{visible_icon}{visible_role_label} - {role['artifact']}",
            "worker_role": worker_role,
            "project_id": project_key,
            "project": project_name,
            "status": status,
            "model": row["model"] or "unknown",
            "reasoning": row["reasoning_effort"] or "unknown",
            "tokens": int(row["tokens_used"] or 0),
            "created_at": created_ms,
            "updated_at": updated_ms,
            "age_ms": max(0, now_ms - created_ms) if created_ms else None,
            "quiet_ms": max(0, now_ms - updated_ms) if updated_ms else None,
            "branch": row["git_branch"] or "",
            "pinned": bool(row["is_pinned"]),
            "virtual": False,
            "worker": role.get("worker") or re.sub(
                r"[^A-Za-z0-9 _-]", "", str(row["agent_nickname"] or "")
            ).strip()[:48],
            "proof_snapshot": {
                "available": False,
                "state": "UNAVAILABLE",
                "claim_limit": "Proof state unavailable; host activity is not proof.",
            },
        }
        nodes[thread_id] = node
        project["nodes"] += 1
        project["tokens"] += node["tokens"]
        project["active"] += status == "active"

    links: list[dict[str, str]] = []
    unattached_task_ids: list[str] = []
    for thread_id, node in list(nodes.items()):
        parent = parent_by_child.get(thread_id)
        if parent in nodes:
            links.append({"source": parent, "target": thread_id, "relationship": "delegated"})
            continue
        if node["role"] == "ctrl":
            continue
        unattached_task_ids.append(thread_id)

    for thread_id in unattached_task_ids:
        node = nodes.pop(thread_id)
        project = projects[node["project_id"]]
        project["nodes"] -= 1
        project["tokens"] -= node["tokens"]
        project["active"] -= node["status"] == "active"
        if project["nodes"] == 0:
            projects.pop(node["project_id"])

    incoming = {link["target"] for link in links}
    roots = [node_id for node_id in nodes if node_id not in incoming]
    children: dict[str, list[str]] = {}
    for link in links:
        children.setdefault(link["source"], []).append(link["target"])

    # The host gives us spawn edges, not an authoritative SWARM runtime graph.
    # A controller scope is therefore only an observed, read-only descendant set.
    controller_ids_by_node: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    controllers: list[dict[str, Any]] = []
    for controller_id, controller in nodes.items():
        if controller["role"] != "ctrl":
            continue
        queue = [controller_id]
        descendants: set[str] = set()
        while queue:
            node_id = queue.pop()
            if node_id in descendants:
                continue
            descendants.add(node_id)
            queue.extend(children.get(node_id, []))
        for node_id in descendants:
            controller_ids_by_node[node_id].append(controller_id)
        observed_descendants: set[str] = set()
        raw_queue = list(raw_children.get(controller_id, []))
        while raw_queue:
            node_id = raw_queue.pop()
            if node_id in observed_descendants:
                continue
            observed_descendants.add(node_id)
            raw_queue.extend(raw_children.get(node_id, []))
        controllers.append(
            {
                "id": controller_id,
                "title": controller["title"],
                "artifact": controller["artifact"],
                "project_id": controller["project_id"],
                "project": controller["project"],
                "status": controller["status"],
                "virtual": controller["virtual"],
                "nodes": len(descendants),
                "active": sum(nodes[node_id]["status"] == "active" for node_id in descendants),
                "updated_at": max((nodes[node_id]["updated_at"] or 0) for node_id in descendants),
                "older_lanes_omitted": sum(
                    node_id not in nodes and node_id not in superseded_ids
                    for node_id in observed_descendants
                ),
            }
        )
    controller_rank = {
        item["id"]: index
        for index, item in enumerate(sorted(controllers, key=lambda item: (-item["nodes"], item["artifact"])))
    }
    for node_id, node in nodes.items():
        node["controller_ids"] = sorted(
            controller_ids_by_node[node_id], key=lambda controller_id: controller_rank[controller_id]
        )
    model_counts = Counter(
        node["model"] for node in nodes.values() if not node["virtual"] and node["model"] != "unknown"
    )
    role_counts = Counter(node["role"] for node in nodes.values() if not node["virtual"])
    status_counts = Counter(node["status"] for node in nodes.values() if not node["virtual"])
    total_tokens = sum(node["tokens"] for node in nodes.values() if not node["virtual"])
    overview = {
        "generated_at": datetime.now(UTC).isoformat(),
        "heartbeat_minutes": heartbeat,
        "observation_window_ms": observation_window_ms,
        "nodes": sorted(nodes.values(), key=lambda node: (node["project"], node["created_at"] or 0)),
        "links": links,
        "roots": roots,
        "controllers": sorted(controllers, key=lambda item: (-item["updated_at"], -item["nodes"], item["artifact"])),
        "projects": sorted(projects.values(), key=lambda item: (-item["active"], item["name"])),
        "analytics": {
            "swarms": len(roots),
            "tasks": sum(1 for node in nodes.values() if not node["virtual"]),
            "tokens": total_tokens,
            "status": dict(status_counts),
            "models": dict(model_counts),
            "roles": dict(role_counts),
        },
        "claim_limits": [
            "Task nodes are derived from observed Codex spawn edges and safe agent-path metadata; worker names stay inside their task node.",
            "Spawn edges are shown as delegated relationships; waits-for and review dependencies are not inferred without runtime receipts.",
            "Controller scopes are observed host descendants, not the authoritative runtime workflow graph.",
            "Proof plans appear only from validated runtime snapshots; absent snapshots stay unavailable and never inherit host task status.",
            "Only unarchived host tasks updated within the current observation window are shown.",
            "Unformatted delegated lanes use the existing active-freshness boundary; older lanes are counted, not expanded.",
            "Older descendant lanes are omitted from the graph and counted on their CTRL scope.",
            "Visible-tab refreshes reuse the local snapshot until the host database, its WAL, or config changes.",
            f"Visible overview refreshes and a lightweight hidden-tab ping preserve portal presence; a closed tab expires after {PORTAL_PRESENCE_TTL_SECONDS} seconds.",
            "Active means recently updated within two heartbeat windows, not guaranteed CPU work.",
            "Tokens are host-reported cumulative thread tokens, not billing or remaining quota.",
            "Only title metadata needed to recognize SWARM naming is read; message bodies, previews, rollout content, credentials, and the logs database are not.",
        ],
        "source": database.name,
    }
    data_bytes = len(json.dumps(overview, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    overview["performance"] = {
        "snapshot_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "data_bytes": data_bytes,
        "refresh_seconds": 30,
        "budget": {"cache_hit_ms": 5, "data_bytes": 262_144},
    }
    return overview


class SwarmHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], app: "App"):
        super().__init__(address, handler)
        self.app = app


class App:
    def __init__(self, codex_home: Path, config_path: Path):
        self.codex_home = codex_home.resolve()
        self.config_path = config_path.resolve()
        self.token = secrets.token_urlsafe(24)
        self.write_lock = threading.Lock()
        self.overview_lock = threading.Lock()
        self.presence_lock = threading.Lock()
        self._overview_fingerprint: tuple[tuple[str, int, int], ...] | None = None
        self._overview: dict[str, Any] | None = None
        self._last_presence_at: float | None = None
        self._last_open_claim_at: float | None = None

    def overview(self) -> dict[str, Any]:
        fingerprint = observation_fingerprint(self.codex_home, self.config_path)
        with self.overview_lock:
            if self._overview is not None and self._overview_fingerprint == fingerprint:
                return self._overview
            overview = build_overview(self.codex_home, self.config_path)
            self._overview_fingerprint = observation_fingerprint(self.codex_home, self.config_path)
            self._overview = overview
            return overview

    def mark_presence(self) -> None:
        with self.presence_lock:
            self._last_presence_at = time.monotonic()

    def presence(self) -> dict[str, Any]:
        with self.presence_lock:
            now = time.monotonic()
            age = None if self._last_presence_at is None else max(0.0, now - self._last_presence_at)
            return {
                "ok": True,
                "fresh": age is not None and age <= PORTAL_PRESENCE_TTL_SECONDS,
                "age_seconds": None if age is None else round(age, 2),
                "ttl_seconds": PORTAL_PRESENCE_TTL_SECONDS,
            }

    def claim_portal_open(self) -> dict[str, Any]:
        with self.presence_lock:
            now = time.monotonic()
            presence_fresh = (
                self._last_presence_at is not None
                and now - self._last_presence_at <= PORTAL_PRESENCE_TTL_SECONDS
            )
            claim_fresh = (
                self._last_open_claim_at is not None
                and now - self._last_open_claim_at <= PORTAL_PRESENCE_TTL_SECONDS
            )
            should_open = not presence_fresh and not claim_fresh
            if should_open:
                self._last_open_claim_at = now
            return {
                "ok": True,
                "should_open": should_open,
                "reason": "open" if should_open else ("active_tab" if presence_fresh else "recent_claim"),
                "ttl_seconds": PORTAL_PRESENCE_TTL_SECONDS,
            }

    def chat_relay_usage(self) -> dict[str, Any]:
        return read_chat_relay_usage(chat_relay_usage_path(self.config_path))

    def clear_chat_relay_usage(self) -> dict[str, Any]:
        chat_relay_usage_path(self.config_path).unlink(missing_ok=True)
        return self.chat_relay_usage()


class Handler(BaseHTTPRequestHandler):
    server: SwarmHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[swarm-console] {self.address_string()} {fmt % args}\n")

    def _host_allowed(self) -> bool:
        host = (urlparse(f"//{self.headers.get('Host', '')}").hostname or "").casefold()
        if host == "localhost":
            return True
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return False
        return True

    def _peer_is_loopback(self) -> bool:
        peer = str(self.client_address[0]).split("%", 1)[0]
        try:
            return ipaddress.ip_address(peer).is_loopback
        except ValueError:
            return False

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            # Keep loopback CLI callers viable; browser writes always send Origin.
            return True
        parsed = urlparse(origin)
        requested = urlparse(f"//{self.headers.get('Host', '')}")
        try:
            origin_port = parsed.port or 80
            requested_port = requested.port or 80
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and (parsed.hostname or "").casefold() == (requested.hostname or "").casefold()
            and origin_port == requested_port
        )

    def _authorized_write(self) -> bool:
        return (
            self._peer_is_loopback()
            and self._same_origin()
            and secrets.compare_digest(self.headers.get("X-Swarm-Token", ""), self.server.app.token)
        )

    def _bootstrap_payload(self) -> dict[str, Any]:
        local = self._peer_is_loopback()
        return {
            "ok": True,
            "token": self.server.app.token if local else "",
            "config_path": str(self.server.app.config_path) if local else "",
            "local_only": local,
            "read_only": not local,
        }

    def _config_payload(self) -> dict[str, Any]:
        payload = redacted_config_snapshot(self.server.app.config_path)
        if not self._peer_is_loopback():
            payload["path"] = ""
            payload["read_only"] = True
        return payload

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_allowed():
            self._error(HTTPStatus.FORBIDDEN, "SWARM Console accepts localhost or numeric IP hosts only")
            return
        path = urlparse(self.path).path
        try:
            if path == "/healthz":
                self._json(HTTPStatus.OK, {"ok": True, "service": "swarm-console"})
                return
            if path == "/api/bootstrap":
                self._json(HTTPStatus.OK, self._bootstrap_payload())
                return
            if path == "/api/overview":
                self.server.app.mark_presence()
                self._json(
                    HTTPStatus.OK,
                    self.server.app.overview(),
                )
                return
            if path == "/api/presence":
                self._json(HTTPStatus.OK, self.server.app.presence())
                return
            if path == "/api/config":
                self._json(HTTPStatus.OK, self._config_payload())
                return
            if path == "/api/chat-relay-usage":
                self._json(HTTPStatus.OK, self.server.app.chat_relay_usage())
                return
            asset = STATIC_ASSETS.get(path)
            if asset:
                asset_path, content_type = asset
                body = asset_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
                return
            generated = GENERATED_STATIC_FILES.get(path)
            if generated:
                body, content_type = generated
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                )
                self.end_headers()
                self.wfile.write(body)
                return
            static = STATIC_FILES.get(path)
            if not static:
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            filename, content_type = static
            body = (STATIC_ROOT / filename).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(body)
        except ConsoleError as exc:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        except (OSError, sqlite3.Error) as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_allowed():
            self._error(HTTPStatus.FORBIDDEN, "invalid console host")
            return
        if not self._peer_is_loopback():
            self._error(HTTPStatus.FORBIDDEN, "remote console access is read-only")
            return
        if not self._same_origin():
            self._error(HTTPStatus.FORBIDDEN, "local same-origin request required")
            return
        if not self._authorized_write():
            self._error(HTTPStatus.FORBIDDEN, "invalid console write token")
            return
        path = urlparse(self.path).path
        if path == "/api/presence":
            self.server.app.mark_presence()
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if path == "/api/launch-claim":
            self._json(HTTPStatus.OK, self.server.app.claim_portal_open())
            return
        if path == "/api/chat-relay-usage/clear":
            self._json(HTTPStatus.OK, self.server.app.clear_chat_relay_usage())
            return
        if path != "/api/config":
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "invalid content length")
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body must be 1-65536 bytes")
            return
        try:
            payload = json.loads(self.rfile.read(length))
            changes = payload.get("changes") if isinstance(payload, dict) else None
            if not isinstance(changes, dict):
                raise ConsoleError("changes must be an object")
            with self.server.app.write_lock:
                result = update_config(self.server.app.config_path, changes)
            self._json(HTTPStatus.OK, {"ok": True, **result})
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, f"invalid JSON: {exc}")
        except ConsoleError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except OSError as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--open", action="store_true", help="open the console in the default browser")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        print("SWARM Console only supports loopback or Docker's 0.0.0.0 bind", file=sys.stderr)
        return 2
    app = App(args.codex_home, resolve_config_path(args.config))
    server = SwarmHTTPServer((args.host, args.port), Handler, app)
    display_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    url = f"http://{display_host}:{args.port}"
    print(f"SWARM Console: {url}")
    print(f"Codex metadata: {state_database(app.codex_home)} [read-only]")
    print(f"SWARM config: {app.config_path} [validated writes]")
    if args.open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
