#!/usr/bin/env python3
"""Local SWARM settings, hierarchy, and analytics console."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import hmac
import importlib.util
import ipaddress
import json
import math
import mimetypes
import os
import queue
import re
import secrets
import shutil
import sqlite3
import stat as stat_module
import subprocess
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
from typing import Any, NamedTuple
from urllib.parse import parse_qs, unquote, urlparse


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
CONSOLE_ROOT = Path(__file__).resolve().parent
SWARM_SKILL_ROOT = PLUGIN_ROOT / "skills" / "swarm"
if str(SWARM_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SWARM_SKILL_ROOT))

from runtime.progress_events import (  # noqa: E402
    MAX_FEED_SCAN_BYTES,
    MAX_PULSE_BYTES,
    MAX_PULSE_FILES,
    PULSE_ROOT,
    ProgressLedger,
    ProgressEventError,
    ProgressPulseEvent,
    build_role_manifest,
    load_builtin_role_manifests,
    role_material_event,
    validate_progress_pulse,
)
from runtime.execution_adapters import (  # noqa: E402
    CodexAppServerAdapter,
    ExecutionConfigGeneration,
    ExecutionDispatchLedger,
    ExecutionDispatchState,
    ExecutionFailureKind,
    ExecutionReservation,
)
from runtime.core import ArtifactIdentity  # noqa: E402

INSTANCE_ID = hashlib.sha256(str(CONSOLE_ROOT.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
CONFIG_SCRIPT = PLUGIN_ROOT / "skills" / "swarm" / "scripts" / "swarm_config.py"
DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
DEFAULT_CONFIG_PATH = Path.home() / ".agents" / "swarm" / "config.toml"
DEFAULT_PORT = 4788
MAX_BODY_BYTES = 64 * 1024
PORTAL_PRESENCE_TTL_SECONDS = 150
MIN_OBSERVATION_WINDOW_MS = 24 * 60 * 60 * 1000
OBSERVATION_HEARTBEAT_WINDOWS = 48
CONSOLE_STATE_PATH_ENV = "SWARM_CONSOLE_STATE_PATH"
CONSOLE_STATE_DIR_ENV = "SWARM_CONSOLE_DATA_DIR"
CONSOLE_STATE_FILENAME = "console-state.sqlite3"
TOKEN_SAMPLE_SECONDS = 60
AUTO_BRIDGE_TIMEOUT_SECONDS = 60
AUTO_CTRL_OVERRIDE_KEY = "_auto"
AUTO_PURPOSE = "swarm-auto-continuation"
NOTIFICATION_SEEN_KEY_PREFIX = "notification_seen_v1"
NOTIFICATION_UNREAD_LIMIT = 128
NOTIFICATION_RECENT_SEEN_LIMIT = 64
RUN_LOG_LIMIT = 200
PROJECT_VIEW_MAX_BYTES = 512 * 1024
PROJECT_VIEW_RENDERERS = {
    "canvas": frozenset({"network", "spatial", "freeform"}),
    "table": frozenset({"entities", "records", "log"}),
    "timeline": frozenset({"ordered", "sessions", "milestones"}),
    "gallery": frozenset({"grid", "list"}),
    "compare": frozenset({"single", "side_by_side"}),
    "document": frozenset({"blocks"}),
}
PROJECT_VIEW_ACTIONS = frozenset({
    "open_artifact", "open_entity", "send_feedback",
})
TOKEN_RETENTION_DAYS = 30
TOKEN_SOURCE_SQLITE = "host_reported_cumulative_delta"
TOKEN_SOURCE_CODEX_JSONL = "codex_jsonl_token_count"
TOKEN_JSONL_SCAN_FILE_LIMIT = 4096
PROGRESS_FRESHNESS_WINDOWS = 2
PROGRESS_RECEIPTS_PER_TASK = 128
DIAGNOSTIC_RETENTION_DAYS = 7
DIAGNOSTIC_FRESH_SECONDS = TOKEN_SAMPLE_SECONDS * 5
HEALTH_INCIDENT_RETENTION_DAYS = 90
HEALTH_SUSTAIN_SECONDS = 300
HEALTH_RECOVERY_SECONDS = 600
HEALTH_COOLDOWN_SECONDS = 900
CONSOLE_LOG_PATH_ENV = "SWARM_CONSOLE_LOG_PATH"
HEALTH_STATES = frozenset({"HEALTHY", "DEGRADED", "PRESSURED", "CRITICAL", "UNKNOWN"})
HEALTH_THRESHOLDS = {
    "cpu_degraded": 85.0,
    "cpu_critical": 95.0,
    "cpu_recover": 75.0,
    "memory_degraded": 80.0,
    "memory_critical": 90.0,
    "memory_recover": 70.0,
    "disk_degraded_bytes": 10 * 1024**3,
    "disk_critical_bytes": 5 * 1024**3,
    "disk_recover_bytes": 8 * 1024**3,
}
MEDIA_MAX_HASH_BYTES = 64 * 1024 * 1024
MAX_PROOF_EVENT_FILES = 1024
PROOF_EVENT_SCAN_STATE_KEY = "proof_event_scan_state_v2"
PROOF_FEED_CURSOR_KEY = "proof_feed_cursor_v1"
PROOF_EVENT_PREFIX_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789-._"
PROOF_EVENT_PRIVATE_FIELDS = frozenset({
    "prompt", "prompts", "response", "responses", "message", "messages",
    "tool_call", "tool_calls", "tool_output", "tool_outputs",
    "credential", "credentials", "cookie", "cookies",
    "provider_cookie", "provider_cookies", "provider_data", "provider_payload",
})
PROOF_EVENT_ROOT = Path("swarm") / "proof-events"
PROOF_MEDIA_ROOT = Path("swarm") / "proof-media"
ROLE_COMMAND_FIELDS = frozenset({
    "command", "role_id", "event_id", "dedupe_key", "expected_active_version",
    "manifest", "provenance", "observed_at_ms",
})
CTRL_OVERRIDE_FIELDS: dict[str, type] = {
    "model": str,
    "reasoning": str,
}
MEDIA_KINDS = frozenset({"imagegen", "image", "mockup", "preview", "screenshot", "browser", "recording"})
MEDIA_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"})
MEDIA_TYPES = frozenset({
    "image/png", "image/jpeg", "image/webp", "image/gif", "video/mp4", "video/webm",
})
OVERVIEW_METRIC_FIELDS = (
    "active_projects", "active_lanes", "actionable_items", "oldest_wait",
    "admitted_milestones", "admitted_proof", "completed", "total", "percent", "trend",
    "window", "used_tokens", "remaining_tokens", "burn_rate_series", "coverage",
)
OVERVIEW_WAIT_STATES = frozenset({
    "WAITING", "WAITING_DEPENDENCY", "WAITING_EXTERNAL", "USER_PAUSED", "KEEP_OUT",
    "NEEDS_AUTHORITY", "STALLED", "BLOCKED",
})
OVERVIEW_COMPLETED_STATES = frozenset({"VERIFIED", "ACCEPTED"})

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/swarm-icon-64.png": ("swarm-icon-64.png", "image/png"),
    "/assets/swarm-mascot-512.png": ("swarm-mascot-512.png", "image/png"),
    "/assets/swarm-offline-disconnected.png": ("swarm-offline-disconnected.png", "image/png"),
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
    "execution.fast_mode": bool,
    "execution.min_reasoning": str,
    "execution.max_reasoning": str,
    "execution.usage_saver": bool,
    "skills.inheritance_enabled": bool,
    "skills.default_profile": str,
    "logging.task_event_limit": int,
    "console.open_on_start": bool,
    "console.project_progress_feed_enabled": bool,
    "console.project_progress_feed_lines": int,
    "chat_relay.enabled": bool,
    "automation.mode": str,
    "boost.enabled": bool,
    "boost.spark_enabled": bool,
    "boost.spark_model": str,
    "boost.spark_reasoning": str,
    "coordination.allow_coordinators": bool,
    "coordination.coordinator_min_children": int,
    "coordination.preferred_lane_width": int,
    "subagents.enabled": bool,
    "subagents.max_per_task": int,
    "review.task_enabled": bool,
    "review.max_parallel_tasks": int,
    "review.scale_when_queue_reaches": int,
    "monitoring.heartbeat_minutes": int,
    "monitoring.auto_health_enabled": bool,
    "recovery.stall_after_updates": int,
    "lifecycle.pin_created_tasks": bool,
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


NOTIFICATION_RULES: dict[str, tuple[str, bool, str, str]] = {
    "BLOCKER": ("critical", True, "projects", "This task is waiting on an exact user, safety, or external release."),
    "MILESTONE_COMPLETED": ("info", False, "projects", "A whole-milestone acceptance receipt has been admitted."),
    "REVIEW_REQUESTED": ("warning", True, "review", "Independent review is required for this artifact."),
    "REVIEW_COMPLETED": ("info", False, "review", "An independent-review receipt has been admitted."),
}

RUN_LOG_SUMMARIES: dict[str, str] = {
    "BLOCK_CREATED": "Work was added.",
    "SCOPE_REVISED": "Scope was revised.",
    "STATE_CHANGED": "Work state changed.",
    "CURRENT_ACTION_CHANGED": "The current action changed.",
    "PROOF_ADMITTED": "Proof was admitted.",
    "PROOF_INVALIDATED": "Proof was invalidated.",
    "ETA_CHANGED": "The delivery estimate changed.",
    "WAIT_CHANGED": "A wait condition changed.",
    "REWORK_REQUESTED": "Rework was requested.",
    "USER_STEERING_ACCEPTED": "User direction was admitted.",
    "LIVENESS_STALE": "Work needs attention.",
    "LIVENESS_RECOVERED": "Work resumed.",
    "RETRY_STARTED": "A recovery attempt started.",
    "TAKEOVER_STARTED": "Custody transfer started.",
    "ACCEPTED": "Outcome accepted.",
}


def _notification_identity(principal_id: str, item: dict[str, Any]) -> str:
    return _auto_digest({
        "principal_id": principal_id,
        "project_id": item["project_id"],
        "ctrl_id": item["ctrl_id"],
        "source_event_id": item["source_event_id"],
        "source_event_digest": item["source_event_digest"],
        "kind": item["kind"],
        "revision": item["revision"],
    })


class AutoBridgeResult(NamedTuple):
    ok: bool
    thread_id: str = ""
    turn_id: str = ""
    event_digest: str = ""
    failure_kind: str = ""
    transient: bool = False
    turn_started: bool = False
    terminal: bool = False
    reachable: bool = False


def _auto_id(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ConsoleError(f"{label} must be a safe identifier")
    text = value.strip()
    if not text or len(text) > 256 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@+-]*", text):
        raise ConsoleError(f"{label} must be a safe identifier")
    return text


def _auto_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CodexStdioBridge:
    """One bounded private Codex App Server JSONL session; no result prose is retained."""

    def __init__(self, process_factory: Any = subprocess.Popen):
        self._process_factory = process_factory
        self.adapter = CodexAppServerAdapter()

    @staticmethod
    def _result_id(message: dict[str, Any], kind: str) -> str:
        result = message.get("result") if isinstance(message.get("result"), dict) else {}
        nested = result.get(kind) if isinstance(result.get(kind), dict) else {}
        return str(result.get(f"{kind}Id") or nested.get("id") or "")

    def _session(self, cwd: Path, transact: Any) -> AutoBridgeResult:
        process: Any = None
        inbox: queue.Queue[object] = queue.Queue()
        try:
            process = self._process_factory(
                list(self.adapter.entrypoint), cwd=str(cwd), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                encoding="utf-8", shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if process.stdin is None or process.stdout is None:
                raise OSError("Codex App Server stdio is unavailable")

            def read_messages() -> None:
                try:
                    for line in process.stdout:
                        try:
                            message = json.loads(line)
                            if isinstance(message, dict): inbox.put(message)
                        except (json.JSONDecodeError, UnicodeDecodeError): pass
                finally:
                    inbox.put(None)

            threading.Thread(target=read_messages, name="swarm-auto-app-server-jsonl", daemon=True).start()
            deadline = time.monotonic() + AUTO_BRIDGE_TIMEOUT_SECONDS
            pending: list[dict[str, Any]] = []

            def send(message: dict[str, object]) -> None:
                process.stdin.write(json.dumps(message, ensure_ascii=True, separators=(",", ":")) + "\n")
                process.stdin.flush()

            def receive(predicate: Any) -> dict[str, Any]:
                while True:
                    match = next((index for index, item in enumerate(pending) if predicate(item)), None)
                    if match is not None: return pending.pop(match)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: raise TimeoutError("Codex App Server did not reach a terminal event")
                    message = inbox.get(timeout=remaining)
                    if message is None: raise OSError("Codex App Server closed its JSONL stream")
                    if predicate(message): return message
                    if message.get("method") == "turn/completed" or "id" in message:
                        if len(pending) >= 64: raise OSError("Codex App Server exceeded the bounded control-event buffer")
                        pending.append(message)

            send(self.adapter.initialize_request("swarm-console-auto", request_id=0))
            initialized = receive(lambda item: item.get("id") == 0)
            if initialized.get("error") is not None: return AutoBridgeResult(False, failure_kind="INITIALIZE_FAILED", transient=True)
            send(self.adapter.initialized_notification())
            return transact(send, receive)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)

    def run(
        self, *, cwd: Path, instruction: str, thread_id: str = "",
        retain_ids: Any = None,
    ) -> AutoBridgeResult:
        resolved_thread, resolved_turn = thread_id, ""
        turn_requested = False
        try:
            def transact(send: Any, receive: Any) -> AutoBridgeResult:
                nonlocal resolved_thread, resolved_turn, turn_requested
                send({"method": "thread/resume" if thread_id else "thread/start", "id": 1, "params": {"threadId": thread_id} if thread_id else {"cwd": str(cwd)}})
                thread_message = receive(lambda item: item.get("id") == 1)
                if thread_message.get("error") is not None: return AutoBridgeResult(False, failure_kind="THREAD_UNAVAILABLE", transient=True)
                resolved_thread = thread_id or self._result_id(thread_message, "thread")
                if not resolved_thread: return AutoBridgeResult(False, failure_kind="MISSING_THREAD")
                if retain_ids is not None: retain_ids(resolved_thread, "", True)
                turn_requested = True
                send({"method": "turn/start", "id": 2, "params": {"threadId": resolved_thread, "input": [{"type": "text", "text": instruction}], "cwd": str(cwd)}})
                turn_message = receive(lambda item: item.get("id") == 2)
                if turn_message.get("error") is not None: return AutoBridgeResult(False, resolved_thread, failure_kind="TURN_START_FAILED", transient=True)
                resolved_turn = self._result_id(turn_message, "turn")
                if not resolved_turn: return AutoBridgeResult(False, resolved_thread, failure_kind="MISSING_TURN", turn_started=True)
                if retain_ids is not None: retain_ids(resolved_thread, resolved_turn, True)
                terminal = receive(lambda item: item.get("method") == "turn/completed")
                event = self.adapter.translate_event(terminal)
                status = event.status.casefold()
                ok = status in {"completed", "complete"}
                return AutoBridgeResult(ok, event.thread_id or resolved_thread, event.turn_id or resolved_turn, event.evidence_digest, "" if ok else "TURN_FAILED", False, True, True, True)

            return self._session(cwd, transact)
        except (ConsoleError, OSError, TimeoutError, queue.Empty, subprocess.SubprocessError):
            return AutoBridgeResult(False, resolved_thread, resolved_turn, failure_kind="TRANSPORT_UNAVAILABLE", transient=True, turn_started=turn_requested)

    def reconcile(self, *, cwd: Path, thread_id: str, turn_id: str) -> AutoBridgeResult:
        """Read one retained App Server turn; never starts or resumes work."""
        thread_id = _auto_id(thread_id, "thread_id")
        turn_id = "" if not turn_id else _auto_id(turn_id, "turn_id")
        try:
            def transact(send: Any, receive: Any) -> AutoBridgeResult:
                send({"method": "thread/read", "id": 1, "params": {"threadId": thread_id, "includeTurns": True}})
                message = receive(lambda item: item.get("id") == 1)
                if message.get("error") is not None: return AutoBridgeResult(False, thread_id, turn_id, failure_kind="TURN_UNREACHABLE", transient=True, turn_started=True)
                result = message.get("result") if isinstance(message.get("result"), dict) else {}
                thread = result.get("thread") if isinstance(result.get("thread"), dict) else result
                turns = thread.get("turns") if isinstance(thread, dict) else []
                resolved_turn = turn_id
                if not resolved_turn:
                    candidates = [item for item in turns if isinstance(item, dict) and str(item.get("id") or "")]
                    if not candidates:
                        return AutoBridgeResult(False, thread_id, failure_kind="TURN_NOT_FOUND", transient=True, turn_started=True, reachable=True)
                    if len(candidates) != 1:
                        return AutoBridgeResult(False, thread_id, failure_kind="TURN_ID_AMBIGUOUS", transient=True, turn_started=True, reachable=True)
                    retained = candidates[0]
                else:
                    retained = next((item for item in turns if isinstance(item, dict) and str(item.get("id") or "") == resolved_turn), None)
                if retained is None: return AutoBridgeResult(False, thread_id, resolved_turn, failure_kind="TURN_UNREACHABLE", transient=True, turn_started=True, reachable=True)
                resolved_turn = str(retained.get("id") or resolved_turn)
                status = str(retained.get("status") or "").casefold()
                digest = _auto_digest({"thread_id": thread_id, "turn_id": resolved_turn, "status": status})
                if status in {"completed", "complete", "interrupted", "failed"}:
                    ok = status in {"completed", "complete"}
                    return AutoBridgeResult(ok, thread_id, resolved_turn, digest, "" if ok else "TURN_FAILED", False, True, True, True)
                return AutoBridgeResult(False, thread_id, resolved_turn, digest, "TURN_ACTIVE", True, True, False, True)

            return self._session(cwd, transact)
        except (OSError, TimeoutError, queue.Empty, subprocess.SubprocessError):
            return AutoBridgeResult(False, thread_id, turn_id, failure_kind="TURN_UNREACHABLE", transient=True, turn_started=True)


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


def _remove_toml_setting(text: str, dotted_key: str) -> str:
    """Remove one legacy persisted key without changing other config text."""
    section, key = dotted_key.split(".", 1)
    lines = text.splitlines()
    section_re = re.compile(rf"^\s*\[{re.escape(section)}\]\s*(?:#.*)?$")
    any_section_re = re.compile(r"^\s*\[[^]]+\]\s*(?:#.*)?$")
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=.*$")
    start = next((i for i, line in enumerate(lines) if section_re.match(line)), None)
    if start is None:
        return text
    end = next((i for i in range(start + 1, len(lines)) if any_section_re.match(lines[i])), len(lines))
    lines = [line for index, line in enumerate(lines) if not (start < index < end and key_re.match(line))]
    return "\n".join(lines) + "\n"


def _remove_toml_root_setting(text: str, key: str) -> str:
    """Remove one legacy root scalar without touching identically named table keys."""
    lines = text.splitlines()
    any_section_re = re.compile(r"^\s*\[[^]]+\]\s*(?:#.*)?$")
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=.*$")
    first_section = next((index for index, line in enumerate(lines) if any_section_re.match(line)), len(lines))
    lines = [line for index, line in enumerate(lines) if not (index < first_section and key_re.match(line))]
    return "\n".join(lines) + "\n"


def _toml_setting_value(text: str, dotted_key: str) -> str | None:
    """Read one simple scalar setting for bounded legacy migration decisions."""
    section, key = dotted_key.split(".", 1)
    lines = text.splitlines()
    section_re = re.compile(rf"^\s*\[{re.escape(section)}\]\s*(?:#.*)?$")
    any_section_re = re.compile(r"^\s*\[[^]]+\]\s*(?:#.*)?$")
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.*?)\s*(?:#.*)?$")
    start = next((i for i, line in enumerate(lines) if section_re.match(line)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if any_section_re.match(lines[i])), len(lines))
    for line in lines[start + 1 : end]:
        match = key_re.match(line)
        if match:
            return match.group(1)
    return None


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
        if dotted_key == "console.project_progress_feed_lines" and not 1 <= value <= 10:
            raise ConsoleError("console.project_progress_feed_lines must be between 1 and 10")

    module, effective, exists = load_config(config_path)
    if exists:
        text = config_path.read_text(encoding="utf-8")
    else:
        text = (PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-config.toml").read_text(
            encoding="utf-8"
        )
    had_fast_mode = _toml_setting_value(text, "execution.fast_mode") is not None
    had_automation_mode = _toml_setting_value(text, "automation.mode") is not None
    legacy_efficiency = _toml_setting_value(text, "efficiency.mode")
    text = _remove_toml_setting(text, "execution.service_tier")
    text = _remove_toml_setting(text, "execution.current_mode")
    text = _remove_toml_root_setting(text, "fast_mode")
    text = _remove_toml_root_setting(text, "current_mode")
    text = _remove_toml_setting(text, "lifecycle.archive_completed_tasks")
    if legacy_efficiency in {'"FAST"', "'FAST'"}:
        text = _replace_toml_setting(text, "efficiency.mode", "BALANCED")
    if not had_fast_mode:
        text = _replace_toml_setting(text, "execution.fast_mode", bool(effective["execution"]["fast_mode"]))
    if not had_automation_mode:
        text = _replace_toml_setting(text, "automation.mode", effective["automation"]["mode"])
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
    result = redacted_config_snapshot(config_path)
    config_digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
    result["mutation_receipt"] = {
        "accepted": True,
        "changed_keys": sorted(changes),
        "config_digest": config_digest,
        "revision": config_digest,
        "source": "swarm_console_atomic_config_write",
        "claim_limit": "This receipt confirms only the canonical local SWARM config write; it does not prove browser rendering or host execution behavior.",
    }
    return result


def restore_config_defaults(config_path: Path) -> dict[str, Any]:
    """Restore the packaged config through the canonical validator, atomically."""
    module = load_config_module()
    source = PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-config.toml"
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConsoleError(f"could not read packaged SWARM defaults: {exc}") from exc
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


def console_state_path(codex_home: Path, config_path: Path) -> Path:
    explicit = os.environ.get(CONSOLE_STATE_PATH_ENV, "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    data_dir = os.environ.get(CONSOLE_STATE_DIR_ENV, "").strip()
    if data_dir:
        return (Path(data_dir).expanduser() / CONSOLE_STATE_FILENAME).resolve()
    return (config_path.parent / CONSOLE_STATE_FILENAME).resolve()


def _trusted_proof_roots(codex_home: Path) -> tuple[Path, Path] | None:
    base = codex_home.expanduser().resolve()
    swarm_root = base / "swarm"
    event_root = base / PROOF_EVENT_ROOT
    media_root = base / PROOF_MEDIA_ROOT
    for path in (swarm_root, event_root, media_root):
        if path.exists() and path.resolve() != path:
            return None
    return event_root, media_root


def proof_storage_stats(codex_home: Path) -> dict[str, int]:
    roots = _trusted_proof_roots(codex_home)
    if roots is None:
        return {"bytes": 0, "files": 0, "events": 0, "media": 0}
    result = {"bytes": 0, "files": 0, "events": 0, "media": 0}
    for label, root in zip(("events", "media"), roots):
        if not root.is_dir():
            continue
        for path in root.iterdir():
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_file() or resolved.parent != root:
                    continue
                result["bytes"] += resolved.stat().st_size
                result["files"] += 1
                result[label] += 1
            except OSError:
                continue
    return result


def clear_proof_storage(codex_home: Path) -> dict[str, int]:
    roots = _trusted_proof_roots(codex_home)
    if roots is None:
        raise ConsoleError("proof evidence store is not a trusted directory")
    before = proof_storage_stats(codex_home)
    deleted = 0
    for root in roots:
        if not root.is_dir():
            continue
        for path in list(root.iterdir()):
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_file() or resolved.parent != root:
                    continue
                resolved.unlink()
                deleted += 1
            except OSError as exc:
                raise ConsoleError("proof history could not be cleared completely") from exc
    after = proof_storage_stats(codex_home)
    return {
        "files_deleted": deleted,
        "bytes_before": before["bytes"],
        "bytes_after": after["bytes"],
    }


def _safe_metadata_text(value: Any, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConsoleError(f"{label} must be non-empty text")
    value = value.strip()
    if "\x00" in value or "\r" in value or "\n" in value or len(value) > maximum:
        raise ConsoleError(f"{label} contains unsafe or oversized text")
    return value


def _safe_proof_copy(value: Any, label: str) -> str:
    copy = _safe_metadata_text(value, label, maximum=512)
    internal_markers = ("localhost", "host acceptance", "hidden usage", "usage consumed", "developer instruction")
    if any(marker in copy.casefold() for marker in internal_markers):
        raise ConsoleError(f"proof {label} must use plain project language")
    return copy


def _media_signature(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            head = stream.read(32)
    except OSError as exc:
        raise ConsoleError("proof media could not be read") from exc
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "video/mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    raise ConsoleError("proof media signature is not allowlisted")


def _media_metadata(
    locator: str,
    supplied_digest: str = "",
    *,
    allowed_root: Path | None = None,
    supplied_size: int | None = None,
    supplied_media_type: str = "",
) -> dict[str, Any]:
    path = Path(locator).expanduser()
    try:
        resolved = path.resolve(strict=True)
        stat = resolved.stat()
    except OSError as exc:
        raise ConsoleError("proof media is unavailable") from exc
    if not resolved.is_file() or stat.st_size <= 0 or stat.st_size > MEDIA_MAX_HASH_BYTES:
        raise ConsoleError("proof media exceeds the delivery guard")
    if allowed_root is not None:
        root = allowed_root.expanduser().resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ConsoleError("proof media must stay inside the configured evidence store")
    media_type = _media_signature(resolved)
    guessed_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    if guessed_type not in MEDIA_TYPES or media_type != guessed_type:
        raise ConsoleError("proof media extension does not match its content")
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    current_digest = digest.hexdigest()
    expected_digest = supplied_digest.strip().casefold()
    if expected_digest and (
        not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
        or not secrets.compare_digest(current_digest, expected_digest)
    ):
        raise ConsoleError("proof media digest does not match its receipt")
    if supplied_size is not None and int(supplied_size) != stat.st_size:
        raise ConsoleError("proof media size does not match its receipt")
    if supplied_media_type and supplied_media_type != media_type:
        raise ConsoleError("proof media type does not match its receipt")
    return {
        "path": str(resolved),
        "mtime_ns": stat.st_mtime_ns,
        "size_bytes": stat.st_size,
        "digest": current_digest,
        "media_type": media_type,
    }


def _is_reparse_point(path: Path) -> bool:
    """Fail closed for symlinks and Windows reparse points such as junctions."""
    try:
        metadata = path.lstat()
    except OSError:
        return True
    reparse_flag = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)


class DiagnosticsCollector:
    """Collect cheap host telemetry without reading prompts or invoking models."""

    def __init__(self, codex_home: Path, console_state_path: Path, now_fn: Any = time.time):
        self.codex_home = codex_home.resolve()
        self.console_state_path = console_state_path.resolve()
        self.now_fn = now_fn

    def _storage_sizes(self) -> dict[str, Any]:
        paths = {
            "db_bytes": self.console_state_path,
            "wal_bytes": self.console_state_path.with_name(self.console_state_path.name + "-wal"),
            "shm_bytes": self.console_state_path.with_name(self.console_state_path.name + "-shm"),
        }
        log_path = Path(os.environ.get(CONSOLE_LOG_PATH_ENV, "").strip() or self.console_state_path.parent / "console.log")
        paths["log_bytes"] = log_path
        result = {key: 0 for key in paths}
        result["log_path"] = str(log_path)
        for key, path in paths.items():
            try:
                result[key] = int(path.stat().st_size) if path.is_file() else 0
            except OSError:
                result[key] = 0
        return result

    @staticmethod
    def _docker_status() -> dict[str, Any]:
        base = {
            "available": False,
            "status": "unavailable",
            "container_count": 0,
            "footprint_bytes": None,
            "footprint_status": "not_collected",
            "source": "docker_cli_read_only",
            "unavailable_reason": "Docker CLI did not return a readable container list.",
            "recommended_action": "Keep container metrics unavailable until the host Docker CLI is available.",
        }
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=swarm-console", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return base
        if result.returncode != 0:
            base["unavailable_reason"] = "Docker CLI returned a non-zero status."
            base["status"] = "error"
            return base
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        base.update({"available": True, "status": "running" if names else "available", "container_count": len(names)})
        return base

    @staticmethod
    def _windows_resources() -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Read CPU and memory through Win32 when optional psutil is absent."""
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", wintypes.DWORD), ("memory_load", wintypes.DWORD),
                    ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            def system_times() -> tuple[int, int, int]:
                idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
                if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                    raise OSError("GetSystemTimes failed")
                value = lambda item: (int(item.dwHighDateTime) << 32) | int(item.dwLowDateTime)
                return value(idle), value(kernel), value(user)

            before = system_times()
            time.sleep(0.05)
            after = system_times()
            idle_delta = max(0, after[0] - before[0])
            total_delta = max(0, (after[1] - before[1]) + (after[2] - before[2]))
            cpu_percent = None if not total_delta else round(max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / total_delta)), 1)
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                raise OSError("GlobalMemoryStatusEx failed")
            return (
                {"available": cpu_percent is not None, "percent": cpu_percent, "source": "win32"},
                {
                    "available": True,
                    "percent": float(status.memory_load),
                    "used_bytes": int(status.total_physical - status.available_physical),
                    "total_bytes": int(status.total_physical),
                    "source": "win32",
                },
            )
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    def collect(self) -> dict[str, Any]:
        sampled_at_ms = int(self.now_fn() * 1000)
        cpu: dict[str, Any] = {
            "available": False,
            "percent": None,
            "source": "unavailable",
            "unavailable_reason": "No supported CPU sampler returned a value.",
            "recommended_action": "Keep CPU load unavailable until a supported host sampler returns a value.",
        }
        memory: dict[str, Any] = {
            "available": False,
            "percent": None,
            "used_bytes": None,
            "total_bytes": None,
            "source": "unavailable",
            "unavailable_reason": "No supported memory sampler returned a value.",
            "recommended_action": "Keep memory load unavailable until a supported host sampler returns a value.",
        }
        network: dict[str, Any] = {
            "available": False,
            "rx_bytes": None,
            "tx_bytes": None,
            "errors": None,
            "source": "unavailable",
            "unavailable_reason": "No readable network counters were returned.",
            "recommended_action": "Keep network totals unavailable until readable host counters exist.",
        }
        try:
            import psutil  # type: ignore
        except (ImportError, OSError):
            psutil = None
        if psutil is not None:
            try:
                cpu_percent = psutil.cpu_percent(interval=None)
                if cpu_percent is not None:
                    cpu.update({"available": True, "percent": float(cpu_percent), "source": "psutil"})
            except (OSError, AttributeError, ValueError, RuntimeError):
                pass
            try:
                virtual_memory = psutil.virtual_memory()
                memory.update({
                    "available": True,
                    "percent": float(virtual_memory.percent),
                    "used_bytes": int(virtual_memory.used),
                    "total_bytes": int(virtual_memory.total),
                    "source": "psutil",
                })
            except (OSError, AttributeError, TypeError, ValueError, RuntimeError):
                pass
            try:
                counters = psutil.net_io_counters()
                if counters is not None:
                    network.update({
                        "available": True,
                        "rx_bytes": int(counters.bytes_recv),
                        "tx_bytes": int(counters.bytes_sent),
                        "errors": int(counters.errin + counters.errout),
                        "source": "psutil",
                    })
                else:
                    network["unavailable_reason"] = "psutil returned no network counters."
            except (OSError, AttributeError, TypeError, ValueError, RuntimeError):
                pass
        if not cpu["available"] or not memory["available"]:
            fallback = self._windows_resources()
            if fallback is not None:
                fallback_cpu, fallback_memory = fallback
                if not cpu["available"]:
                    cpu = fallback_cpu
                if not memory["available"]:
                    memory = fallback_memory
        for metric in (cpu, memory, network):
            if metric.get("available"):
                metric["observed_at_ms"] = sampled_at_ms
        try:
            disk = shutil.disk_usage(self.codex_home)
            disks = [{
                "mount": str(self.codex_home.anchor or self.codex_home),
                "free_bytes": int(disk.free),
                "total_bytes": int(disk.total),
                "percent": round((disk.used / disk.total) * 100, 2) if disk.total else None,
                "available": True,
                "source": "shutil.disk_usage",
                "observed_at_ms": sampled_at_ms,
            }]
        except OSError:
            disks = [{
                "mount": str(self.codex_home.anchor or self.codex_home),
                "available": False,
                "source": "unavailable",
                "unavailable_reason": "The diagnostics root disk could not be read.",
                "recommended_action": "Keep disk capacity unavailable until the diagnostics root is readable.",
            }]
        console_storage = self._storage_sizes()
        console_storage.update({"source": "console_state_files", "observed_at_ms": sampled_at_ms})
        docker = self._docker_status()
        if docker.get("available"):
            docker["observed_at_ms"] = sampled_at_ms
        return {
            "sampled_at_ms": sampled_at_ms,
            "cpu": cpu,
            "memory": memory,
            "disks": disks,
            "docker": docker,
            "network": network,
            "console_storage": console_storage,
        }


def _diagnostic_freshness(observed_at_ms: Any, now_ms: int) -> dict[str, Any]:
    if not isinstance(observed_at_ms, int) or observed_at_ms <= 0:
        return {"state": "no_data", "age_seconds": None, "sampled_at_ms": None}
    age_seconds = max(0, (int(now_ms) - observed_at_ms) // 1000)
    return {
        "state": "fresh" if age_seconds <= DIAGNOSTIC_FRESH_SECONDS else "stale",
        "age_seconds": age_seconds,
        "sampled_at_ms": observed_at_ms,
    }


def _diagnostic_availability(payload: dict[str, Any]) -> dict[str, Any]:
    groups: list[tuple[str, str, dict[str, Any] | None]] = [
        ("cpu", "CPU", payload.get("cpu") if isinstance(payload.get("cpu"), dict) else None),
        ("memory", "memory", payload.get("memory") if isinstance(payload.get("memory"), dict) else None),
        ("containers", "containers", payload.get("docker") if isinstance(payload.get("docker"), dict) else None),
        ("network", "network", payload.get("network") if isinstance(payload.get("network"), dict) else None),
    ]
    disks = payload.get("disks") if isinstance(payload.get("disks"), list) else []
    disk = next((item for item in disks if isinstance(item, dict) and item.get("available")), None)
    disk_reason = next((item for item in disks if isinstance(item, dict)), None)
    groups.append(("disk", "disk", disk or disk_reason))
    available: list[str] = []
    unavailable: list[dict[str, Any]] = []
    for group, label, metric in groups:
        if metric and metric.get("available"):
            available.append(group)
            continue
        metric = metric or {}
        unavailable.append({
            "group": group,
            "label": label,
            "reason": str(metric.get("unavailable_reason") or "No observed value was returned."),
            "action": str(metric.get("recommended_action") or "Keep this source unavailable until it returns a readable value."),
        })
    if not available:
        status = "no_data" if not payload.get("sampled_at_ms") else "unavailable"
    elif unavailable:
        status = "partial"
    else:
        status = "complete"
    unavailable_labels = ", ".join(item["label"] for item in unavailable)
    return {
        "status": status,
        "available_groups": available,
        "unavailable_groups": unavailable,
        "summary": "All configured sources observed." if not unavailable else f"Unavailable sources: {unavailable_labels}.",
    }


def _diagnostic_record_for_response(record: dict[str, Any], now_ms: int) -> dict[str, Any]:
    response = copy.deepcopy(record)
    sampled_at_ms = response.get("sampled_at_ms")
    payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
    response["source_timestamp_ms"] = sampled_at_ms if isinstance(sampled_at_ms, int) and sampled_at_ms > 0 else None
    response["freshness"] = _diagnostic_freshness(sampled_at_ms, now_ms)
    for key in ("cpu", "memory", "docker", "network"):
        metric = payload.get(key)
        if isinstance(metric, dict):
            metric["freshness"] = _diagnostic_freshness(
                metric.get("observed_at_ms") if metric.get("available") else None,
                now_ms,
            )
    disks = payload.get("disks")
    if isinstance(disks, list):
        for disk in disks:
            if isinstance(disk, dict):
                disk["freshness"] = _diagnostic_freshness(
                    disk.get("observed_at_ms") if disk.get("available") else None,
                    now_ms,
                )
    payload["freshness"] = response["freshness"]
    payload["availability"] = _diagnostic_availability(payload)
    response["payload"] = payload
    return response


def _diagnostic_no_data(now_ms: int) -> dict[str, Any]:
    return {
        "sampled_at_ms": None,
        "source_timestamp_ms": None,
        "health_state": "UNKNOWN",
        "reasons": [],
        "freshness": _diagnostic_freshness(None, now_ms),
        "payload": {
            "sampled_at_ms": None,
            "freshness": _diagnostic_freshness(None, now_ms),
            "availability": {
                "status": "no_data",
                "available_groups": [],
                "unavailable_groups": [{
                    "group": "host",
                    "label": "host diagnostics",
                    "reason": "No diagnostics sample has been recorded yet.",
                    "action": "Start or resume the local observer; no host value is inferred here.",
                }],
                "summary": "No diagnostics sample recorded.",
            },
        },
    }


def assess_health(sample: dict[str, Any]) -> dict[str, Any]:
    """Classify a sample; this function has no I/O and no host authority."""
    reasons: list[dict[str, Any]] = []
    known_metric = False

    def add_reason(code: str, kind: str, scope: str, severity: str, recommendation: str, constraints: list[str]) -> None:
        reasons.append({
            "code": code,
            "kind": kind,
            "scope": scope,
            "severity": severity,
            "request_type": "cleanup_review" if kind == "disk" else "capacity_review" if kind in {"cpu", "memory"} else "diagnostics_review",
            "recommendation": recommendation,
            "constraints": constraints,
        })

    cpu_percent = sample.get("cpu", {}).get("percent")
    if isinstance(cpu_percent, (int, float)):
        known_metric = True
        if cpu_percent >= HEALTH_THRESHOLDS["cpu_critical"]:
            add_reason("cpu_critical", "cpu", "host", "CRITICAL", "Review sustained CPU pressure and reduce only new SWARM scheduling concurrency.", ["Do not kill processes or change power settings."])
        elif cpu_percent >= HEALTH_THRESHOLDS["cpu_degraded"]:
            add_reason("cpu_degraded", "cpu", "host", "DEGRADED", "Review sustained CPU pressure and capacity before scheduling more work.", ["Do not kill processes or change power settings."])

    memory_percent = sample.get("memory", {}).get("percent")
    if isinstance(memory_percent, (int, float)):
        known_metric = True
        if memory_percent >= HEALTH_THRESHOLDS["memory_critical"]:
            add_reason("memory_critical", "memory", "host", "CRITICAL", "Review sustained memory pressure and reduce only new SWARM scheduling concurrency.", ["Do not kill processes or infer cleanup targets."])
        elif memory_percent >= HEALTH_THRESHOLDS["memory_degraded"]:
            add_reason("memory_degraded", "memory", "host", "DEGRADED", "Review sustained memory pressure before scheduling more work.", ["Do not kill processes or infer cleanup targets."])

    for disk in sample.get("disks", []):
        free_bytes = disk.get("free_bytes")
        if not isinstance(free_bytes, (int, float)):
            continue
        known_metric = True
        scope = str(disk.get("mount") or "host")[:128]
        if free_bytes < HEALTH_THRESHOLDS["disk_critical_bytes"]:
            add_reason("disk_critical", "disk", scope, "CRITICAL", "Request a guarded cleanup review for exact stale or rebuildable targets.", ["No broad Docker prune.", "No user documents, dirty/current worktrees, active logs, databases, or live-process references.", "Copy-verify-remove retained artifacts and prove free space before and after."])
        elif free_bytes < HEALTH_THRESHOLDS["disk_degraded_bytes"]:
            add_reason("disk_degraded", "disk", scope, "PRESSURED", "Request a guarded cleanup review for exact stale or rebuildable targets.", ["No broad Docker prune.", "No user documents, dirty/current worktrees, active logs, databases, or live-process references.", "Copy-verify-remove retained artifacts and prove free space before and after."])

    severity_rank = {"CRITICAL": 3, "PRESSURED": 2, "DEGRADED": 1}
    if reasons:
        state = max((reason["severity"] for reason in reasons), key=severity_rank.__getitem__)
    elif known_metric:
        state = "HEALTHY"
    else:
        state = "UNKNOWN"
    digest = hashlib.sha256(json.dumps(reasons, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"state": state, "reasons": reasons, "evidence_digest": digest}


class ConsoleStore:
    """Small console-owned persistence layer; host state remains read-only."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS token_cursors (
                    thread_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    cumulative_tokens INTEGER NOT NULL,
                    sampled_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS token_samples (
                    bucket_ms INTEGER NOT NULL,
                    sampled_at_ms INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    cumulative_tokens INTEGER NOT NULL,
                    delta_tokens INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (bucket_ms, thread_id)
                );
                CREATE INDEX IF NOT EXISTS token_samples_project_bucket
                    ON token_samples(project_id, bucket_ms);
                CREATE TABLE IF NOT EXISTS eta_forecasts (
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    eta_start_ms INTEGER,
                    eta_end_ms INTEGER,
                    confidence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    last_progress_at_ms INTEGER,
                    last_calculated_at_ms INTEGER NOT NULL,
                    trigger TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    PRIMARY KEY (task_id, revision)
                );
                CREATE INDEX IF NOT EXISTS eta_forecasts_latest
                    ON eta_forecasts(task_id, revision DESC);
                CREATE TABLE IF NOT EXISTS proof_media (
                    evidence_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    locator TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    claim_limit TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    receipt TEXT NOT NULL,
                    surface_kind TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    mtime_ns INTEGER,
                    size_bytes INTEGER,
                    digest TEXT,
                    registered_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS proof_media_project_updated
                    ON proof_media(project_id, updated_at_ms DESC);
                CREATE TABLE IF NOT EXISTS proof_event_receipts (
                    event_name TEXT PRIMARY KEY,
                    event_mtime_ns INTEGER NOT NULL,
                    event_size INTEGER NOT NULL,
                    event_digest TEXT,
                    status TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    task_id TEXT,
                    project_id TEXT,
                    media_digest TEXT,
                    observed_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ctrl_overrides (
                    ctrl_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    fields_json TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_catalog (
                    skill_id TEXT PRIMARY KEY,
                    source_repo TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    popularity_json TEXT NOT NULL,
                    audit_json TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    installed INTEGER NOT NULL DEFAULT 0,
                    builtin INTEGER NOT NULL DEFAULT 0,
                    allowed_roles_json TEXT NOT NULL,
                    allowed_task_kinds_json TEXT NOT NULL,
                    last_checked_ms INTEGER NOT NULL DEFAULT 0,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_scope_overlays (
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    inheritance_enabled INTEGER,
                    profile TEXT NOT NULL,
                    preferred_ids_json TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    PRIMARY KEY(scope_type, scope_id)
                );
                CREATE TABLE IF NOT EXISTS task_heartbeats (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    last_material_at_ms INTEGER,
                    last_liveness_at_ms INTEGER NOT NULL,
                    scheduled_wake_at_ms INTEGER,
                    scheduled_wake_consumed INTEGER NOT NULL DEFAULT 0,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_progress_state (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    unit_kind TEXT NOT NULL,
                    total_units INTEGER NOT NULL,
                    completed_units INTEGER NOT NULL,
                    basis TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    pulse_receipt TEXT NOT NULL,
                    pulse_observed_at_ms INTEGER NOT NULL,
                    pulse_state TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_progress_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    previous_plan_id TEXT,
                    unit_id TEXT NOT NULL,
                    unit_kind TEXT NOT NULL,
                    total_units INTEGER NOT NULL,
                    completed_units INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    accepted_at_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS task_progress_receipts_task_time
                    ON task_progress_receipts(task_id, observed_at_ms DESC);
                CREATE TABLE IF NOT EXISTS task_progress_plans (
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    first_observed_at_ms INTEGER NOT NULL,
                    PRIMARY KEY(task_id, plan_id)
                );
                CREATE TABLE IF NOT EXISTS task_progress_pulse_files (
                    event_name TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    pulse_receipt TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pulse_state TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS diagnostic_samples (
                    sampled_at_ms INTEGER PRIMARY KEY,
                    health_state TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS health_incidents (
                    incident_key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    state TEXT NOT NULL,
                    first_seen_ms INTEGER NOT NULL,
                    last_seen_ms INTEGER NOT NULL,
                    healthy_since_ms INTEGER,
                    cooldown_until_ms INTEGER,
                    request_id TEXT,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS health_requests (
                    request_id TEXT PRIMARY KEY,
                    incident_key TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    claimed_at_ms INTEGER,
                    resolved_at_ms INTEGER,
                    resolution_receipt TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS execution_config_generations (
                    generation_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    changed_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_dispatch_state (
                    reservation_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE,
                    snapshot_json TEXT NOT NULL,
                    snapshot_digest TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_event_receipts (
                    event_digest TEXT PRIMARY KEY,
                    retained_at_ms INTEGER NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS health_requests_open_dedupe
                    ON health_requests(dedupe_key)
                    WHERE status IN ('OPEN', 'CLAIMED', 'IN_PROGRESS');
                CREATE INDEX IF NOT EXISTS diagnostic_samples_time
                    ON diagnostic_samples(sampled_at_ms DESC);
                CREATE INDEX IF NOT EXISTS health_incidents_state
                    ON health_incidents(state, updated_at_ms DESC);
                CREATE INDEX IF NOT EXISTS health_requests_status
                    ON health_requests(status, created_at_ms DESC);
                """
            )
            execution_receipt_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(execution_event_receipts)").fetchall()
            }
            for name, definition in {
                "event_kind": "TEXT NOT NULL DEFAULT 'EXECUTION_EVENT'",
                "identity": "TEXT NOT NULL DEFAULT ''",
                "payload_json": "TEXT NOT NULL DEFAULT '{}'",
                "payload_digest": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in execution_receipt_columns:
                    connection.execute(f"ALTER TABLE execution_event_receipts ADD COLUMN {name} {definition}")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS execution_event_identity "
                "ON execution_event_receipts(event_kind, identity) WHERE identity != ''"
            )
            connection.execute("DROP TABLE IF EXISTS auto_ctrl_state")
            eta_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(eta_forecasts)").fetchall()
            }
            for name, definition in {
                "baseline_eta_start_ms": "INTEGER",
                "baseline_eta_end_ms": "INTEGER",
                "baseline_confidence": "INTEGER",
                "delta_from_baseline_ms": "INTEGER",
                "progress_basis_json": "TEXT",
                "last_material_heartbeat_at_ms": "INTEGER",
                "reason_code": "TEXT",
                "short_reason": "TEXT",
                "receipt_source": "TEXT",
                "previous_forecast_json": "TEXT",
                "current_forecast_json": "TEXT",
            }.items():
                if name not in eta_columns:
                    connection.execute(f"ALTER TABLE eta_forecasts ADD COLUMN {name} {definition}")
            proof_receipt_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(proof_event_receipts)").fetchall()
            }
            for name in ("event_digest", "task_id", "project_id", "media_digest"):
                if name not in proof_receipt_columns:
                    connection.execute(f"ALTER TABLE proof_event_receipts ADD COLUMN {name} TEXT")
            connection.execute(
                """
                UPDATE proof_event_receipts
                   SET task_id = COALESCE(task_id, (
                           SELECT media.task_id FROM proof_media media
                           WHERE media.evidence_id = proof_event_receipts.evidence_id
                       )),
                       project_id = COALESCE(project_id, (
                           SELECT media.project_id FROM proof_media media
                           WHERE media.evidence_id = proof_event_receipts.evidence_id
                       )),
                       media_digest = COALESCE(media_digest, (
                           SELECT media.digest FROM proof_media media
                           WHERE media.evidence_id = proof_event_receipts.evidence_id
                       ))
                 WHERE status = 'IMPORTED'
                """
            )
            progress_plan_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(task_progress_plans)").fetchall()
            }
            if "project_id" not in progress_plan_columns:
                connection.execute("ALTER TABLE task_progress_plans ADD COLUMN project_id TEXT")
            if not connection.in_transaction:
                connection.execute("BEGIN IMMEDIATE")
            conflicting_plan_binding = connection.execute(
                """
                WITH plan_bindings(task_id, project_id, plan_id) AS (
                    SELECT task_id, project_id, plan_id FROM task_progress_receipts
                    UNION ALL
                    SELECT task_id, project_id, plan_id FROM task_progress_state
                    UNION ALL
                    SELECT task_id, project_id, plan_id FROM task_progress_plans
                    WHERE project_id IS NOT NULL AND project_id != ''
                )
                SELECT task_id, plan_id
                FROM plan_bindings
                GROUP BY task_id, plan_id
                HAVING COUNT(DISTINCT project_id) > 1
                LIMIT 1
                """
            ).fetchone()
            if conflicting_plan_binding is not None:
                raise ConsoleError(
                    "progress plan history has conflicting project identity for "
                    f"task {conflicting_plan_binding['task_id']} plan {conflicting_plan_binding['plan_id']}"
                )
            historical_plans = connection.execute(
                """
                WITH plan_history(task_id, project_id, plan_id, first_seen_at_ms) AS (
                    SELECT task_id, project_id, plan_id,
                           MIN(observed_at_ms, accepted_at_ms)
                    FROM task_progress_receipts
                    UNION ALL
                    SELECT task_id, project_id, plan_id, observed_at_ms
                    FROM task_progress_state
                )
                SELECT task_id, project_id, plan_id, MIN(first_seen_at_ms) AS first_seen_at_ms
                FROM plan_history
                GROUP BY task_id, project_id, plan_id
                ORDER BY task_id, plan_id
                """
            ).fetchall()
            for plan in historical_plans:
                existing_plan = connection.execute(
                    "SELECT project_id, first_observed_at_ms FROM task_progress_plans WHERE task_id = ? AND plan_id = ?",
                    (plan["task_id"], plan["plan_id"]),
                ).fetchone()
                if existing_plan is None:
                    connection.execute(
                        "INSERT INTO task_progress_plans(task_id, project_id, plan_id, first_observed_at_ms) VALUES (?, ?, ?, ?)",
                        (plan["task_id"], plan["project_id"], plan["plan_id"], int(plan["first_seen_at_ms"])),
                    )
                else:
                    existing_project = existing_plan["project_id"]
                    if existing_project not in (None, "", plan["project_id"]):
                        raise ConsoleError("progress plan history conflicts with its existing project binding")
                    connection.execute(
                        "UPDATE task_progress_plans SET project_id = ?, first_observed_at_ms = MIN(first_observed_at_ms, ?) WHERE task_id = ? AND plan_id = ?",
                        (plan["project_id"], int(plan["first_seen_at_ms"]), plan["task_id"], plan["plan_id"]),
                    )
            from skills_catalog import seed_rows
            for seed in seed_rows(int(time.time() * 1000)):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO skill_catalog(
                        skill_id, source_repo, source_path, source_ref, source_version,
                        popularity_json, audit_json, review_status, installed, builtin,
                        allowed_roles_json, allowed_task_kinds_json, last_checked_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        seed["skill_id"], seed["source_repo"], seed["source_path"], seed["source_ref"],
                        seed["source_version"], json.dumps(seed["popularity"], separators=(",", ":")),
                        json.dumps(seed["audit"], separators=(",", ":")), seed["review_status"],
                        int(bool(seed["installed"])), int(bool(seed["builtin"])),
                        json.dumps(seed["allowed_roles"], separators=(",", ":")),
                        json.dumps(seed["allowed_task_kinds"], separators=(",", ":")),
                        int(seed["last_checked_ms"]), int(seed["updated_at_ms"]),
                    ),
                )
            connection.execute(
                "UPDATE proof_media SET disposition='PENDING', receipt='legacy:available', "
                "surface_kind='available_media' WHERE disposition IN ('AVAILABLE', 'SURFACED')"
            )
            connection.commit()

    @staticmethod
    def _execution_payload(payload: dict[str, Any]) -> tuple[str, str]:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_execution_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize one intact legacy mode field without changing generation identity."""
        normalized = dict(payload)
        if "fast_mode" in normalized and "service_tier" in normalized:
            raise ConsoleError("execution config generation has competing mode authorities")
        if "fast_mode" not in normalized:
            legacy_tier = normalized.pop("service_tier", None)
            if legacy_tier not in {"default", "flex", "fast", "priority"}:
                raise ConsoleError("legacy execution config service tier is invalid")
            normalized["fast_mode"] = legacy_tier in {"fast", "priority"}
        return normalized

    @staticmethod
    def _validate_execution_reservation_advance(retained: dict[str, Any], incoming: dict[str, Any]) -> None:
        """Reject stale or regressive reservation snapshots before the retained CAS write."""
        for field in ("reservation_id", "task_id", "owner_id"):
            if retained.get(field) != incoming.get(field):
                raise ConsoleError("execution reservation conflicts with retained identity")
        retained_artifact = json.dumps(retained.get("artifact"), sort_keys=True, separators=(",", ":"))
        incoming_artifact = json.dumps(incoming.get("artifact"), sort_keys=True, separators=(",", ":"))
        if retained_artifact != incoming_artifact:
            raise ConsoleError("execution reservation conflicts with retained identity")
        if bool(retained.get("host_completed")) and not bool(incoming.get("host_completed")):
            next_turn = (
                str(incoming.get("state") or "") == "active"
                and str(incoming.get("generation_id") or "") != str(retained.get("generation_id") or "")
                and str(incoming.get("request_digest") or "") != str(retained.get("request_digest") or "")
            )
            if not next_turn:
                raise ConsoleError("execution reservation cannot regress host completion")
        if int(incoming.get("retry_count") or 0) < int(retained.get("retry_count") or 0):
            raise ConsoleError("execution reservation cannot regress retry count")
        retained_receipt = str(retained.get("material_receipt_id") or "")
        if retained_receipt and str(incoming.get("material_receipt_id") or "") != retained_receipt:
            raise ConsoleError("execution reservation cannot replace retained material receipt")
        allowed_states = {
            "queued": {"queued", "deferred", "active", "unverified", "material_receipt"},
            "deferred": {"deferred", "active", "unverified", "material_receipt"},
            "active": {"active", "checkpointed", "material_receipt", "unverified"},
            "checkpointed": {"checkpointed", "active", "material_receipt", "unverified"},
            "unverified": {"unverified", "active", "checkpointed", "material_receipt"},
            "material_receipt": {"material_receipt", "independent_review"},
            "independent_review": {"independent_review", "complete"},
            "complete": {"complete"},
        }
        retained_state = str(retained.get("state") or "")
        incoming_state = str(incoming.get("state") or "")
        if incoming_state == "independent_review":
            retained_material = str(retained.get("material_receipt_id") or "")
            if retained_state != "material_receipt" or not retained_material:
                raise ConsoleError("independent review requires a retained exact material receipt")
            if (
                str(incoming.get("material_receipt_id") or "") != retained_material
                or str(incoming.get("generation_id") or "") != str(retained.get("generation_id") or "")
            ):
                raise ConsoleError("independent review conflicts with retained material receipt binding")
        if incoming_state == "complete" and retained_state not in {"independent_review", "complete"}:
            raise ConsoleError("completed execution reservation requires retained independent review")
        if incoming_state not in allowed_states.get(retained_state, set()):
            raise ConsoleError("execution reservation state cannot move backward or skip a gate")
        if incoming_state in {"material_receipt", "independent_review", "complete"} and not str(incoming.get("material_receipt_id") or ""):
            raise ConsoleError("execution reservation acceptance state requires a retained material receipt")
        if incoming_state == "complete" and not bool(incoming.get("host_completed")):
            raise ConsoleError("completed execution reservation requires consumed host completion")

    def persist_execution_ledger(self, ledger: ExecutionDispatchLedger, *, now_ms: int) -> None:
        """Persist only typed queue identities/digests; raw request or tool content is never accepted."""
        if not isinstance(ledger, ExecutionDispatchLedger) or not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
            raise ConsoleError("execution ledger persistence requires typed state and nonnegative time")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            for generation in ledger.generations:
                payload = {
                    "generation_id": generation.generation_id,
                    "fast_mode": generation.fast_mode,
                    "model": generation.model,
                    "effort": generation.effort,
                    "changed_at_ms": generation.changed_at_ms,
                    "host_receipt_id": generation.host_receipt_id,
                }
                encoded, digest = self._execution_payload(payload)
                existing = connection.execute(
                    "SELECT payload_json, payload_digest FROM execution_config_generations WHERE generation_id = ?",
                    (generation.generation_id,),
                ).fetchone()
                if existing is not None and str(existing["payload_digest"]) != digest:
                    retained = json.loads(str(existing["payload_json"]))
                    _, retained_digest = self._execution_payload(retained)
                    if retained_digest != str(existing["payload_digest"]):
                        raise ConsoleError("execution config generation digest mismatch")
                    if self._canonical_execution_generation_payload(retained) != payload:
                        raise ConsoleError("execution config generation conflicts with retained identity")
                    updated = connection.execute(
                        """
                        UPDATE execution_config_generations
                        SET payload_json = ?, payload_digest = ?, changed_at_ms = ?
                        WHERE generation_id = ? AND payload_digest = ?
                        """,
                        (encoded, digest, generation.changed_at_ms, generation.generation_id, retained_digest),
                    )
                    if updated.rowcount != 1:
                        raise ConsoleError("execution config generation normalization lost retained custody")
                elif existing is None:
                    connection.execute(
                        "INSERT INTO execution_config_generations(generation_id, payload_json, payload_digest, changed_at_ms) VALUES (?, ?, ?, ?)",
                        (generation.generation_id, encoded, digest, generation.changed_at_ms),
                    )
            for reservation in ledger.reservations:
                snapshot = reservation.snapshot()
                encoded, digest = self._execution_payload(snapshot)
                existing = connection.execute(
                    "SELECT task_id, snapshot_json, snapshot_digest, updated_at_ms "
                    "FROM execution_dispatch_state WHERE reservation_id = ?",
                    (reservation.reservation_id,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO execution_dispatch_state(reservation_id, task_id, snapshot_json, snapshot_digest, updated_at_ms) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (reservation.reservation_id, reservation.task_id, encoded, digest, reservation.updated_at_ms),
                    )
                    continue
                retained = json.loads(str(existing["snapshot_json"]))
                _, retained_digest = self._execution_payload(retained)
                if retained_digest != str(existing["snapshot_digest"]):
                    raise ConsoleError("execution reservation snapshot digest mismatch")
                retained_at_ms = int(existing["updated_at_ms"])
                if reservation.updated_at_ms < retained_at_ms:
                    raise ConsoleError("stale execution reservation snapshot cannot replace retained state")
                if reservation.updated_at_ms == retained_at_ms:
                    if digest == retained_digest:
                        continue
                    raise ConsoleError("equal-time execution reservation snapshot conflicts with retained digest")
                self._validate_execution_reservation_advance(retained, snapshot)
                updated = connection.execute(
                    """
                    UPDATE execution_dispatch_state
                    SET task_id = ?, snapshot_json = ?, snapshot_digest = ?, updated_at_ms = ?
                    WHERE reservation_id = ? AND task_id = ? AND snapshot_digest = ? AND updated_at_ms = ?
                    """,
                    (
                        reservation.task_id, encoded, digest, reservation.updated_at_ms,
                        reservation.reservation_id, str(existing["task_id"]), retained_digest, retained_at_ms,
                    ),
                )
                if updated.rowcount != 1:
                    raise ConsoleError("execution reservation persistence lost retained custody")
            for event_digest in ledger.event_digests:
                connection.execute(
                    "INSERT OR IGNORE INTO execution_event_receipts(event_digest, retained_at_ms) VALUES (?, ?)",
                    (event_digest, now_ms),
                )
            connection.commit()

    def load_execution_ledger(self) -> ExecutionDispatchLedger:
        """Restore retained reservations and dedupe receipts without replaying host work."""
        with self._lock, closing(self._connect()) as connection:
            generation_rows = connection.execute(
                "SELECT payload_json, payload_digest FROM execution_config_generations ORDER BY changed_at_ms, generation_id"
            ).fetchall()
            reservation_rows = connection.execute(
                "SELECT snapshot_json, snapshot_digest FROM execution_dispatch_state ORDER BY reservation_id"
            ).fetchall()
            event_rows = connection.execute(
                "SELECT event_digest FROM execution_event_receipts ORDER BY event_digest"
            ).fetchall()
        try:
            generations = []
            for row in generation_rows:
                payload = json.loads(str(row["payload_json"]))
                _, digest = self._execution_payload(payload)
                if digest != str(row["payload_digest"]):
                    raise ConsoleError("execution config generation digest mismatch")
                payload = self._canonical_execution_generation_payload(payload)
                generations.append(ExecutionConfigGeneration(**payload))
            reservations = []
            for row in reservation_rows:
                payload = json.loads(str(row["snapshot_json"]))
                _, digest = self._execution_payload(payload)
                if digest != str(row["snapshot_digest"]):
                    raise ConsoleError("execution reservation snapshot digest mismatch")
                reservations.append(ExecutionReservation.from_snapshot(payload))
            return ExecutionDispatchLedger(
                generations=tuple(generations),
                reservations=tuple(reservations),
                event_digests=tuple(str(row["event_digest"]) for row in event_rows),
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise ConsoleError(f"execution ledger restore failed closed: {error}") from error

    @staticmethod
    def _auto_payload(payload: dict[str, Any]) -> tuple[str, str]:
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _auto_settings(fields: dict[str, Any], *, ctrl_id: str, project_id: str) -> dict[str, Any]:
        raw = fields.get(AUTO_CTRL_OVERRIDE_KEY)
        if raw is None: return {"project_id": project_id, "enabled": False, "stop_after_turn": False}
        if not isinstance(raw, dict) or set(raw) != {"project_id", "enabled", "stop_after_turn"}:
            raise ConsoleError("retained CTRL Auto settings are invalid")
        retained_project = _auto_id(raw.get("project_id"), "project_id")
        if retained_project != project_id: raise ConsoleConflict("CTRL Auto state is bound to a different project")
        if not isinstance(raw.get("enabled"), bool) or not isinstance(raw.get("stop_after_turn"), bool):
            raise ConsoleError("retained CTRL Auto settings are invalid")
        return dict(raw)

    @staticmethod
    def _auto_binding(reservation: ExecutionReservation) -> dict[str, str] | None:
        if reservation.artifact.purpose != AUTO_PURPOSE:
            return None
        binding = dict(reservation.artifact.observables)
        required = {"ctrl_id", "project_id", "goal_id", "task_id", "request_id", "observed_turn_id", "decision_digest", "route_digest", "next_operation"}
        return binding if required <= set(binding) else None

    def _auto_active(self, ledger: ExecutionDispatchLedger | None = None) -> list[tuple[ExecutionReservation, dict[str, str]]]:
        ledger = ledger or self.load_execution_ledger()
        return [
            (item, binding) for item in ledger.reservations
            if (binding := self._auto_binding(item)) is not None
            and item.state is ExecutionDispatchState.ACTIVE and not item.host_completed
        ]

    @classmethod
    def _retain_auto_event(
        cls, connection: sqlite3.Connection, *, event_kind: str, identity: str,
        payload: dict[str, Any], now_ms: int,
    ) -> bool:
        encoded, digest = cls._auto_payload(payload)
        retained = connection.execute(
            "SELECT payload_digest FROM execution_event_receipts WHERE event_kind = ? AND identity = ?",
            (event_kind, identity),
        ).fetchone()
        if retained is not None:
            if str(retained["payload_digest"]) != digest:
                raise ConsoleConflict("Auto receipt identity conflicts with retained content")
            return False
        connection.execute(
            "INSERT INTO execution_event_receipts(event_digest, retained_at_ms, event_kind, identity, payload_json, payload_digest) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (digest, now_ms, event_kind, identity, encoded, digest),
        )
        return True

    def auto_status(self, ctrl_id: str, project_id: str) -> dict[str, Any]:
        ctrl_id = _auto_id(ctrl_id, "ctrl_id")
        project_id = _auto_id(project_id, "project_id")
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT revision, fields_json, updated_at_ms FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,)).fetchone()
            fields = {} if row is None else json.loads(str(row["fields_json"]))
            settings = self._auto_settings(fields, ctrl_id=ctrl_id, project_id=project_id)
            receipt_rows = connection.execute(
                "SELECT event_kind, payload_json FROM execution_event_receipts "
                "WHERE event_kind IN ('AUTO_DECISION', 'AUTO_OUTCOME', 'AUTO_RELEASE') "
                "ORDER BY retained_at_ms DESC, event_kind DESC LIMIT 128"
            ).fetchall()
        active = [(item, binding) for item, binding in self._auto_active() if binding["ctrl_id"] == ctrl_id and binding["project_id"] == project_id]
        if len(active) > 1:
            raise ConsoleError("multiple retained Auto continuation leases fail closed")
        latest = None
        for receipt_row in receipt_rows:
            payload = json.loads(str(receipt_row["payload_json"]))
            if payload.get("ctrl_id") == ctrl_id and payload.get("project_id") == project_id:
                latest = payload; break
        reservation, binding = active[0] if active else (None, {})
        disposition = {} if latest is None else latest.get("disposition") or {}
        result = {
            "ctrl_id": ctrl_id, "project_id": project_id, **settings, "in_flight": reservation is not None,
            "revision": 0 if row is None else int(row["revision"]), "goal_id": binding.get("goal_id", ""),
            "request_id": binding.get("request_id", ""), "observed_turn_id": binding.get("observed_turn_id", ""),
            "decision_digest": binding.get("decision_digest", ""), "reservation_id": "" if reservation is None else reservation.reservation_id,
            "thread_id": "" if reservation is None else reservation.host_thread_id, "turn_id": "" if reservation is None else reservation.host_turn_id,
            "last_disposition": str(disposition.get("disposition") or ""), "updated_at_ms": 0 if row is None else int(row["updated_at_ms"]),
        }
        for key in ("next_operation", "next_owner", "next_route", "release_condition", "responsible_authority"):
            result[key] = str(disposition.get(key) or "")
        result["phase"] = "STOPPING" if result["stop_after_turn"] else "RUNNING" if result["in_flight"] else "IDLE" if result["enabled"] else "OFF"
        result["attention"] = None
        if reservation is not None:
            result["attention"] = {"kind": "IN_FLIGHT_OUTCOME_UNVERIFIED", "reason": "reconcile the retained host thread and turn before any new dispatch", "recovery_authority": ctrl_id}
        elif result["last_disposition"] in {"WAIT_USER", "TERMINAL_BLOCKED"}:
            result["attention"] = {"kind": result["last_disposition"], "reason": result["release_condition"], "recovery_authority": result["responsible_authority"]}
        result["claim_limit"] = "Auto host completion is not material progress, proof, review, or acceptance."
        return result

    def enabled_auto_states(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT ctrl_id, fields_json FROM ctrl_overrides ORDER BY ctrl_id"
            ).fetchall()
        states = []
        for row in rows:
            fields = json.loads(str(row["fields_json"]))
            raw = fields.get(AUTO_CTRL_OVERRIDE_KEY)
            if isinstance(raw, dict) and isinstance(raw.get("project_id"), str):
                state = self.auto_status(str(row["ctrl_id"]), str(raw["project_id"]))
                if state["enabled"] or state["in_flight"]:
                    states.append(state)
        return states

    def set_auto(
        self, ctrl_id: str, project_id: str, *, enabled: bool, request_id: str, now_ms: int,
    ) -> dict[str, Any]:
        ctrl_id = _auto_id(ctrl_id, "ctrl_id")
        project_id = _auto_id(project_id, "project_id")
        request_id = _auto_id(request_id, "request_id")
        if not isinstance(enabled, bool) or not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
            raise ConsoleError("Auto command requires boolean enabled and nonnegative time")
        payload = {"ctrl_id": ctrl_id, "project_id": project_id, "enabled": enabled, "request_id": request_id}
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT revision, fields_json FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,)).fetchone()
            fields = {} if row is None else json.loads(str(row["fields_json"]))
            current = self._auto_settings(fields, ctrl_id=ctrl_id, project_id=project_id)
            fresh = self._retain_auto_event(
                connection, event_kind="AUTO_COMMAND", identity=request_id, payload=payload, now_ms=now_ms,
            )
            if fresh:
                revision = (0 if row is None else int(row["revision"])) + 1
                in_flight = any(binding["ctrl_id"] == ctrl_id for _, binding in self._auto_active())
                fields[AUTO_CTRL_OVERRIDE_KEY] = {"project_id": project_id, "enabled": enabled, "stop_after_turn": bool(in_flight and not enabled)}
                connection.execute(
                    "INSERT INTO ctrl_overrides(ctrl_id, revision, fields_json, updated_at_ms) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(ctrl_id) DO UPDATE SET revision=excluded.revision, fields_json=excluded.fields_json, updated_at_ms=excluded.updated_at_ms",
                    (ctrl_id, revision, json.dumps(fields, sort_keys=True), now_ms),
                )
            connection.commit()
        return {**self.auto_status(ctrl_id, project_id), "replayed": not fresh}

    def claim_auto_dispatch(
        self, decision: dict[str, Any], generation: ExecutionConfigGeneration, *, now_ms: int,
    ) -> dict[str, Any]:
        required = {
            "ctrl_id", "project_id", "goal_id", "task_id", "owner_id", "request_id",
            "observed_turn_id", "decision_digest", "route_digest", "instruction_digest",
            "next_operation", "request_bytes",
        }
        if set(decision) != required:
            raise ConsoleError("Auto decision has an invalid exact schema")
        values = {
            key: _auto_id(value, key) for key, value in decision.items()
            if not key.endswith("digest") and key != "request_bytes"
        }
        digests = {
            key: str(decision[key]).casefold()
            for key in ("decision_digest", "route_digest", "instruction_digest")
        }
        if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in digests.values()):
            raise ConsoleError("Auto decision digests must be SHA-256")
        request_bytes = decision["request_bytes"]
        if not isinstance(request_bytes, int) or isinstance(request_bytes, bool) or not 0 < request_bytes <= 16_384:
            raise ConsoleError("Auto instruction must be a positive bounded UTF-8 payload")
        if not isinstance(generation, ExecutionConfigGeneration):
            raise ConsoleError("Auto dispatch requires a typed current execution generation")
        identity = _auto_digest((values["goal_id"], values["request_id"], values["observed_turn_id"], digests["decision_digest"]))
        payload = {**values, **digests, "request_bytes": request_bytes, "idempotency_key": identity}
        reservation_id = f"auto-{identity}"
        with self._lock:
            state = self.auto_status(values["ctrl_id"], values["project_id"])
            if not state["enabled"] or state["stop_after_turn"]:
                return {"claimed": False, "reason": "AUTO_OFF", "idempotency_key": identity}
            ledger = self.load_execution_ledger()
            if self._auto_active(ledger): return {"claimed": False, "reason": "IN_FLIGHT", "idempotency_key": identity}
            existing = next((item for item in ledger.reservations if item.reservation_id == reservation_id), None)
            artifact = ArtifactIdentity(
                f"auto:{values['project_id']}:{values['goal_id']}", digests["decision_digest"], AUTO_PURPOSE,
                tuple(sorted((key, str(value)) for key, value in {
                    **{key: values[key] for key in ("ctrl_id", "project_id", "goal_id", "task_id", "request_id", "observed_turn_id", "next_operation")},
                    "decision_digest": digests["decision_digest"], "route_digest": digests["route_digest"],
                }.items())),
            )
            if existing is not None:
                if existing.artifact != artifact:
                    raise ConsoleConflict("Auto dispatch identity conflicts with retained content")
                return {"claimed": False, "reason": "REPLAY", "idempotency_key": identity}
            latest = ledger.latest_generation
            if latest is None:
                ledger.observe_generation(generation)
            elif latest.generation_id != generation.generation_id and generation.changed_at_ms > latest.changed_at_ms:
                ledger.observe_generation(generation)
            ledger.reserve(reservation_id, f"auto-operation-{identity}", values["owner_id"], artifact, observed_at_ms=now_ms)
            ledger.dispatch(reservation_id, digests["instruction_digest"], request_bytes, observed_at_ms=now_ms)
            self.persist_execution_ledger(ledger, now_ms=now_ms)
            with closing(self._connect()) as connection:
                self._retain_auto_event(connection, event_kind="AUTO_DISPATCH", identity=identity, payload=payload, now_ms=now_ms)
                connection.commit()
        return {"claimed": True, "reservation_id": reservation_id, "idempotency_key": identity}

    def retain_auto_host_ids(
        self, reservation_id: str, thread_id: str, turn_id: str, submission_started: bool = False, *, now_ms: int,
    ) -> None:
        reservation_id = _auto_id(reservation_id, "reservation_id")
        thread_id = _auto_id(thread_id, "thread_id")
        turn_id = "" if not turn_id else _auto_id(turn_id, "turn_id")
        if not isinstance(submission_started, bool):
            raise ConsoleError("Auto host receipt requires a boolean submission state")
        with self._lock:
            ledger = self.load_execution_ledger()
            reservation = ledger.reservation(reservation_id)
            if self._auto_binding(reservation) is None or reservation.state is not ExecutionDispatchState.ACTIVE:
                raise ConsoleConflict("Auto host IDs require the exact active execution reservation")
            if reservation.host_thread_id and reservation.host_thread_id != thread_id:
                raise ConsoleConflict("Auto host thread conflicts with the retained execution receipt")
            if turn_id and reservation.host_turn_id and reservation.host_turn_id != turn_id:
                raise ConsoleConflict("Auto host turn conflicts with the retained execution receipt")
            reservation.host_thread_id = thread_id
            reservation.host_turn_id = turn_id or reservation.host_turn_id
            reservation.updated_at_ms = now_ms
            self.persist_execution_ledger(ledger, now_ms=now_ms)
            binding = self._auto_binding(reservation) or {}
            payload = {"ctrl_id": binding.get("ctrl_id"), "project_id": binding.get("project_id"), "reservation_id": reservation_id, "thread_id": thread_id, "turn_id": turn_id, "submission_started": submission_started}
            with closing(self._connect()) as connection:
                phase = "turn" if turn_id else "submission" if submission_started else "thread"
                self._retain_auto_event(connection, event_kind="AUTO_HOST_IDS", identity=f"{reservation_id}:{phase}", payload=payload, now_ms=now_ms)
                connection.commit()

    def retain_auto_control(self, event_kind: str, identity: str, payload: dict[str, Any], *, now_ms: int) -> bool:
        if event_kind not in {"AUTO_DECISION", "AUTO_RECONCILE"}: raise ConsoleError("Auto control receipt kind is invalid")
        with self._lock, closing(self._connect()) as connection:
            fresh = self._retain_auto_event(connection, event_kind=event_kind, identity=identity, payload=payload, now_ms=now_ms)
            connection.commit()
        return fresh

    def finish_auto_dispatch(self, reservation_id: str, *, result: AutoBridgeResult, disposition: dict[str, Any] | None, now_ms: int) -> dict[str, Any]:
        reservation_id = _auto_id(reservation_id, "reservation_id")
        if not isinstance(result, AutoBridgeResult):
            raise ConsoleError("Auto completion requires a typed bridge result")
        if (not result.ok or not result.terminal) and (not isinstance(disposition, dict) or disposition.get("disposition") not in {"RETRY_SAME", "TRY_ALTERNATE", "WAIT_USER", "TERMINAL_BLOCKED"}):
            raise ConsoleError("Auto outcome requires one canonical durable disposition")
        with self._lock:
            ledger = self.load_execution_ledger()
            reservation = ledger.reservation(reservation_id)
            binding = self._auto_binding(reservation)
            if binding is None or reservation.state is not ExecutionDispatchState.ACTIVE:
                raise ConsoleConflict("Auto outcome does not match a retained active execution reservation")
            if result.thread_id:
                if reservation.host_thread_id and reservation.host_thread_id != result.thread_id:
                    raise ConsoleConflict("Auto outcome thread conflicts with retained execution state")
                reservation.host_thread_id = result.thread_id
            if result.turn_id:
                if reservation.host_turn_id and reservation.host_turn_id != result.turn_id:
                    raise ConsoleConflict("Auto outcome turn conflicts with retained execution state")
                reservation.host_turn_id = result.turn_id
            if result.terminal:
                event = CodexAppServerAdapter().translate_event({
                    "method": "turn/completed",
                    "params": {"threadId": reservation.host_thread_id, "turnId": reservation.host_turn_id, "status": "completed" if result.ok else "failed"},
                })
                ledger.observe_event(reservation_id, event, observed_at_ms=now_ms)
            elif not result.turn_started:
                ledger.fail_transport(reservation_id, ExecutionFailureKind.TIMEOUT, observed_at_ms=now_ms)
            reservation.updated_at_ms = now_ms
            self.persist_execution_ledger(ledger, now_ms=now_ms)
            payload = {"ctrl_id": binding["ctrl_id"], "project_id": binding["project_id"], "reservation_id": reservation_id,
                "thread_id": reservation.host_thread_id, "turn_id": reservation.host_turn_id,
                "bridge": {"ok": result.ok, "failure_kind": result.failure_kind, "turn_started": result.turn_started, "terminal": result.terminal, "reachable": result.reachable},
                "disposition": disposition or {}, "material_progress": False}
            with closing(self._connect()) as connection:
                outcome_phase = "terminal" if result.terminal else "uncertain" if result.turn_started else "prestart"
                self._retain_auto_event(connection, event_kind="AUTO_OUTCOME", identity=f"{reservation_id}:{outcome_phase}", payload=payload, now_ms=now_ms)
                if reservation.host_completed or reservation.state is not ExecutionDispatchState.ACTIVE:
                    row = connection.execute("SELECT revision, fields_json FROM ctrl_overrides WHERE ctrl_id = ?", (binding["ctrl_id"],)).fetchone()
                    fields = {} if row is None else json.loads(str(row["fields_json"]))
                    settings = self._auto_settings(fields, ctrl_id=binding["ctrl_id"], project_id=binding["project_id"])
                    if settings["stop_after_turn"]:
                        settings = {**settings, "enabled": False, "stop_after_turn": False}
                        fields[AUTO_CTRL_OVERRIDE_KEY] = settings
                        connection.execute("UPDATE ctrl_overrides SET fields_json = ?, updated_at_ms = ? WHERE ctrl_id = ?", (json.dumps(fields, sort_keys=True), now_ms, binding["ctrl_id"]))
                connection.commit()
        return {**self.auto_status(binding["ctrl_id"], binding["project_id"]), "disposition_receipt": disposition}

    def release_auto_dispatch(
        self, ctrl_id: str, project_id: str, reservation_id: str, *, request_id: str,
        recovery_authority: str, release_condition: str, now_ms: int,
    ) -> dict[str, Any]:
        ctrl_id = _auto_id(ctrl_id, "ctrl_id")
        project_id = _auto_id(project_id, "project_id")
        reservation_id = _auto_id(reservation_id, "reservation_id")
        request_id = _auto_id(request_id, "request_id")
        if _auto_id(recovery_authority, "recovery_authority") != ctrl_id:
            raise ConsoleError("Auto release requires the exact current CTRL recovery authority")
        release_condition = str(release_condition or "").strip()
        if not release_condition or len(release_condition) > 256 or any(char in release_condition for char in "\r\n\x00"):
            raise ConsoleError("Auto release requires one bounded exact release condition")
        with self._lock:
            ledger = self.load_execution_ledger()
            reservation = ledger.reservation(reservation_id)
            binding = self._auto_binding(reservation)
            if binding is None or binding["ctrl_id"] != ctrl_id or binding["project_id"] != project_id or reservation.state is not ExecutionDispatchState.ACTIVE:
                raise ConsoleConflict("Auto release does not match the retained active lease")
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT event_kind, payload_json FROM execution_event_receipts "
                    "WHERE event_kind IN ('AUTO_OUTCOME', 'AUTO_RECONCILE') ORDER BY retained_at_ms DESC"
                ).fetchall()
            latest_host_read = next(
                (payload for row in rows if (payload := json.loads(str(row["payload_json"]))).get("reservation_id") == reservation_id),
                None,
            )
            bridge = latest_host_read.get("bridge") if isinstance(latest_host_read, dict) and isinstance(latest_host_read.get("bridge"), dict) else {}
            failure_kind = str(latest_host_read.get("failure_kind") or bridge.get("failure_kind") or "") if latest_host_read else ""
            if failure_kind not in {"TURN_NOT_FOUND", "TURN_UNREACHABLE"} or not (
                latest_host_read.get("turn_started") is True or bridge.get("turn_started") is True
            ):
                raise ConsoleConflict("Auto release requires a retained unreachable-turn reconciliation receipt")
            ledger.fail_transport(reservation_id, ExecutionFailureKind.TIMEOUT, observed_at_ms=now_ms)
            self.persist_execution_ledger(ledger, now_ms=now_ms)
            disposition = {"disposition": "WAIT_USER", "next_operation": "RECONCILE_OR_AUTHORIZE_NEW_OPERATION", "next_owner": ctrl_id, "next_route": "", "release_condition": release_condition, "responsible_authority": ctrl_id}
            payload = {"ctrl_id": ctrl_id, "project_id": project_id, "reservation_id": reservation_id, "request_id": request_id, "disposition": disposition, "material_progress": False}
            with closing(self._connect()) as connection:
                self._retain_auto_event(connection, event_kind="AUTO_RELEASE", identity=request_id, payload=payload, now_ms=now_ms)
                connection.commit()
        return {**self.auto_status(ctrl_id, project_id), "release_receipt": request_id}

    def _retention_cutoff(self, now_ms: int) -> int:
        return now_ms - TOKEN_RETENTION_DAYS * 24 * 60 * 60 * 1000

    def _record_eta_receipt(
        self,
        connection: sqlite3.Connection,
        payload: dict[str, Any],
        *,
        observed_task_id: str,
        observed_project_id: str,
        now_ms: int,
    ) -> bool:
        """Persist a bound task-owner report as planning input; never infer authority or ETA."""
        if payload.get("receipt_type") != "swarm_task_owner_forecast":
            return False
        if "authority" in payload:
            return False
        source = _safe_metadata_text(payload.get("source"), "ETA receipt source", maximum=256)
        receipt = _safe_metadata_text(payload.get("receipt"), "ETA receipt", maximum=512)
        task_id = _safe_metadata_text(payload.get("task_id"), "ETA task id", maximum=256)
        project_id = _safe_metadata_text(payload.get("project_id"), "ETA project id", maximum=256)
        if task_id != observed_task_id or project_id != observed_project_id:
            return False
        baseline = payload.get("baseline")
        current = payload.get("current")
        if not isinstance(baseline, dict) or not isinstance(current, dict):
            return False
        for label, value in (("baseline", baseline), ("current", current)):
            if not {"eta_start_ms", "eta_end_ms", "confidence"}.issubset(value):
                return False
            if any(value[key] is not None and (not isinstance(value[key], int) or isinstance(value[key], bool)) for key in ("eta_start_ms", "eta_end_ms")):
                return False
            if not isinstance(value["confidence"], int) or isinstance(value["confidence"], bool) or not 0 <= value["confidence"] <= 100:
                return False
        progress_basis = current.get("progress_basis")
        if not isinstance(progress_basis, dict) or not any(
            isinstance(progress_basis.get(key), list) and progress_basis.get(key)
            for key in ("milestones", "checkpoints", "receipts")
        ):
            return False
        plan_units = progress_basis.get("plan_units")
        if plan_units is not None:
            receipts = progress_basis.get("receipts")
            if (
                not isinstance(plan_units, dict)
                or not isinstance(receipts, list)
                or not receipts
                or any(not isinstance(item, str) or not item.strip() for item in receipts)
            ):
                return False
            total_units = plan_units.get("total_units")
            completed_units = plan_units.get("completed_units")
            observed_at_ms = plan_units.get("observed_at_ms")
            raw_basis = plan_units.get("basis")
            plan_id = plan_units.get("plan_id")
            unit_id = plan_units.get("unit_id")
            unit_kind = plan_units.get("unit_kind")
            if (
                not isinstance(total_units, int)
                or isinstance(total_units, bool)
                or total_units <= 0
                or not isinstance(completed_units, int)
                or isinstance(completed_units, bool)
                or not 0 <= completed_units <= total_units
                or not isinstance(observed_at_ms, int)
                or isinstance(observed_at_ms, bool)
                or not 0 < observed_at_ms <= now_ms
                or not isinstance(raw_basis, str)
                or not raw_basis.strip()
                or len(raw_basis.strip()) > 128
                or any(character in raw_basis for character in "\r\n\t")
                or not isinstance(plan_id, str)
                or not plan_id.strip()
                or len(plan_id.strip()) > 128
                or any(character in plan_id for character in "\r\n\t")
                or not isinstance(unit_id, str)
                or not unit_id.strip()
                or len(unit_id.strip()) > 128
                or any(character in unit_id for character in "\r\n\t")
                or not isinstance(unit_kind, str)
                or not unit_kind.strip()
                or len(unit_kind.strip()) > 64
                or any(character in unit_kind for character in "\r\n\t")
            ):
                return False
            progress_basis = {
                **progress_basis,
                "plan_units": {
                    "total_units": total_units,
                    "completed_units": completed_units,
                    "basis": raw_basis.strip(),
                    "observed_at_ms": observed_at_ms,
                    "plan_id": plan_id.strip(),
                    "unit_id": unit_id.strip(),
                    "unit_kind": unit_kind.strip(),
                },
            }
        reason_code = payload.get("reason_code")
        if reason_code not in {
            "scope_discovered", "dependency", "failed_proof", "environment",
            "underestimated_complexity", "owner_capacity_change", "material_progress",
            "state_change", "completion", "heartbeat_stale",
        }:
            return False
        status = current.get("status")
        if status not in {"planned", "in_progress", "blocked", "complete"}:
            return False
        short_reason = _safe_metadata_text(payload.get("short_reason"), "ETA reason", maximum=256)
        current_public = {
            "eta_start_ms": current["eta_start_ms"], "eta_end_ms": current["eta_end_ms"],
            "confidence": current["confidence"], "status": status,
            "progress_basis": progress_basis,
        }
        latest = connection.execute(
            "SELECT * FROM eta_forecasts WHERE task_id = ? ORDER BY revision DESC LIMIT 1", (task_id,)
        ).fetchone()
        baseline_start = baseline["eta_start_ms"] if latest is None else latest["baseline_eta_start_ms"]
        baseline_end = baseline["eta_end_ms"] if latest is None else latest["baseline_eta_end_ms"]
        baseline_confidence = baseline["confidence"] if latest is None else latest["baseline_confidence"]
        if latest is not None and (
            baseline["eta_start_ms"] != baseline_start
            or baseline["eta_end_ms"] != baseline_end
            or baseline["confidence"] != baseline_confidence
        ):
            raise ConsoleError("ETA report baseline conflicts with the stored task baseline")
        signature = json.dumps(
            (
                "swarm-task-owner-report-v1",
                {"eta_start_ms": baseline_start, "eta_end_ms": baseline_end, "confidence": baseline_confidence},
                current_public,
                reason_code,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        if latest is not None and str(latest["signature"]) == signature:
            return False
        previous = None if latest is None else json.loads(latest["current_forecast_json"] or "{}")
        delta = None if baseline_end is None or current["eta_end_ms"] is None else int(current["eta_end_ms"]) - int(baseline_end)
        connection.execute(
            """
            INSERT INTO eta_forecasts(
                task_id, project_id, revision, eta_start_ms, eta_end_ms,
                confidence, status, reason, last_progress_at_ms,
                last_calculated_at_ms, trigger, signature,
                baseline_eta_start_ms, baseline_eta_end_ms, baseline_confidence,
                delta_from_baseline_ms, progress_basis_json,
                last_material_heartbeat_at_ms, reason_code, short_reason, receipt_source,
                previous_forecast_json, current_forecast_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id, project_id, 1 if latest is None else int(latest["revision"]) + 1,
                current["eta_start_ms"], current["eta_end_ms"], current["confidence"], status,
                short_reason, current.get("last_progress_at_ms"), now_ms, "task_owner_report", signature,
                baseline_start, baseline_end, baseline_confidence, delta,
                json.dumps(progress_basis, separators=(",", ":")), now_ms, reason_code, short_reason,
                f"{source}:{receipt}", json.dumps(previous, separators=(",", ":")),
                json.dumps(current_public, separators=(",", ":")),
            ),
        )
        connection.execute(
            "UPDATE task_heartbeats SET last_material_at_ms = ?, updated_at_ms = ? WHERE task_id = ?",
            (now_ms, now_ms, task_id),
        )
        return True

    def _record_progress_pulse(
        self,
        connection: sqlite3.Connection,
        event: ProgressPulseEvent,
        *,
        now_ms: int,
    ) -> str:
        """Apply one validated local pulse without granting it host authority."""
        if event.observed_at_ms > now_ms:
            raise ConsoleError("progress pulse observation time is in the future")
        connection.execute(
            """
            INSERT INTO task_heartbeats(
                task_id, project_id, last_material_at_ms, last_liveness_at_ms,
                scheduled_wake_at_ms, scheduled_wake_consumed, updated_at_ms
            ) VALUES (?, ?, NULL, ?, NULL, 0, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                project_id=excluded.project_id,
                last_liveness_at_ms=MAX(task_heartbeats.last_liveness_at_ms, excluded.last_liveness_at_ms),
                updated_at_ms=MAX(task_heartbeats.updated_at_ms, excluded.updated_at_ms)
            """,
            (event.task_id, event.project_id, event.observed_at_ms, now_ms),
        )
        progress = event.progress
        if progress is None:
            return "heartbeat"
        progress_digest = hashlib.sha256(json.dumps(
            {
                "task_id": event.task_id,
                "project_id": event.project_id,
                "receipt_id": progress.receipt_id,
                "plan_id": progress.plan_id,
                "previous_plan_id": progress.previous_plan_id,
                "unit_id": progress.unit_id,
                "unit_kind": progress.unit_kind,
                "total_units": progress.total_units,
                "completed_units": progress.completed_units,
                "basis": progress.basis,
                "observed_at_ms": progress.observed_at_ms,
                "source": progress.source,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        existing_receipt = connection.execute(
            "SELECT * FROM task_progress_receipts WHERE receipt_id = ?",
            (progress.receipt_id,),
        ).fetchone()
        if existing_receipt is not None:
            if str(existing_receipt["payload_digest"]) != progress_digest:
                raise ConsoleError("progress receipt conflicts with a previously accepted receipt")
            latest_material = connection.execute(
                "SELECT receipt_id, pulse_observed_at_ms FROM task_progress_state WHERE task_id = ?",
                (event.task_id,),
            ).fetchone()
            if (
                latest_material is not None
                and str(latest_material["receipt_id"]) == progress.receipt_id
                and event.observed_at_ms > int(latest_material["pulse_observed_at_ms"])
            ):
                connection.execute(
                    "UPDATE task_progress_state SET pulse_receipt = ?, pulse_observed_at_ms = ?, pulse_state = ?, updated_at_ms = MAX(updated_at_ms, ?) WHERE task_id = ?",
                    (event.pulse_receipt, event.observed_at_ms, event.state, now_ms, event.task_id),
                )
                return "heartbeat"
            return "duplicate"
        latest = connection.execute(
            "SELECT * FROM task_progress_state WHERE task_id = ?",
            (event.task_id,),
        ).fetchone()
        if latest is None:
            if progress.previous_plan_id is not None:
                raise ConsoleError("initial progress plan cannot claim a previous plan")
            prior_plan = connection.execute(
                "SELECT project_id FROM task_progress_plans WHERE task_id = ? AND plan_id = ?",
                (event.task_id, progress.plan_id),
            ).fetchone()
            if prior_plan is not None:
                raise ConsoleError("progress plan identity was already used for this task")
        else:
            if str(latest["project_id"]) != event.project_id:
                raise ConsoleError("progress pulse project conflicts with the stored task target")
            current_plan = str(latest["plan_id"])
            connection.execute(
                "INSERT OR IGNORE INTO task_progress_plans(task_id, project_id, plan_id, first_observed_at_ms) VALUES (?, ?, ?, ?)",
                (event.task_id, event.project_id, current_plan, int(latest["observed_at_ms"])),
            )
            connection.execute(
                "UPDATE task_progress_plans SET project_id = ? WHERE task_id = ? AND plan_id = ? AND (project_id IS NULL OR project_id = '')",
                (event.project_id, event.task_id, current_plan),
            )
            if progress.plan_id == current_plan:
                if progress.previous_plan_id is not None:
                    raise ConsoleError("same-plan progress cannot declare a plan revision")
                if (
                    progress.unit_id != str(latest["unit_id"])
                    or progress.unit_kind != str(latest["unit_kind"])
                    or progress.total_units != int(latest["total_units"])
                ):
                    raise ConsoleError("progress unit identity or declared total conflicts with the stored plan")
                if progress.completed_units <= int(latest["completed_units"]):
                    raise ConsoleError("a unique material receipt must advance completed units monotonically")
                if progress.observed_at_ms < int(latest["observed_at_ms"]):
                    raise ConsoleError("progress observation cannot regress its high-water")
            else:
                if progress.previous_plan_id != current_plan:
                    raise ConsoleError("a new progress plan requires an explicit previous_plan_id revision")
                if progress.observed_at_ms <= int(latest["observed_at_ms"]):
                    raise ConsoleError("a progress plan revision must advance the task observation high-water")
                prior_plan = connection.execute(
                    "SELECT project_id FROM task_progress_plans WHERE task_id = ? AND plan_id = ?",
                    (event.task_id, progress.plan_id),
                ).fetchone()
                if prior_plan is not None:
                    raise ConsoleError("progress plan identity was already used for this task")
        connection.execute(
            "INSERT OR IGNORE INTO task_progress_plans(task_id, project_id, plan_id, first_observed_at_ms) VALUES (?, ?, ?, ?)",
            (event.task_id, event.project_id, progress.plan_id, progress.observed_at_ms),
        )
        connection.execute(
            """
            INSERT INTO task_progress_receipts(
                receipt_id, task_id, project_id, plan_id, previous_plan_id,
                unit_id, unit_kind, total_units, completed_units, observed_at_ms,
                source, payload_digest, accepted_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                progress.receipt_id, event.task_id, event.project_id, progress.plan_id,
                progress.previous_plan_id, progress.unit_id, progress.unit_kind,
                progress.total_units, progress.completed_units, progress.observed_at_ms,
                progress.source, progress_digest, now_ms,
            ),
        )
        connection.execute(
            """
            INSERT INTO task_progress_state(
                task_id, project_id, plan_id, unit_id, unit_kind, total_units,
                completed_units, basis, observed_at_ms, source, receipt_id,
                pulse_receipt, pulse_observed_at_ms, pulse_state, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                project_id=excluded.project_id,
                plan_id=excluded.plan_id,
                unit_id=excluded.unit_id,
                unit_kind=excluded.unit_kind,
                total_units=excluded.total_units,
                completed_units=excluded.completed_units,
                basis=excluded.basis,
                observed_at_ms=excluded.observed_at_ms,
                source=excluded.source,
                receipt_id=excluded.receipt_id,
                pulse_receipt=excluded.pulse_receipt,
                pulse_observed_at_ms=excluded.pulse_observed_at_ms,
                pulse_state=excluded.pulse_state,
                updated_at_ms=excluded.updated_at_ms
            """,
            (
                event.task_id, event.project_id, progress.plan_id, progress.unit_id,
                progress.unit_kind, progress.total_units, progress.completed_units,
                progress.basis, progress.observed_at_ms, progress.source,
                progress.receipt_id, event.pulse_receipt, event.observed_at_ms,
                event.state, now_ms,
            ),
        )
        connection.execute(
            """
            DELETE FROM task_progress_receipts
            WHERE rowid IN (
                SELECT rowid FROM task_progress_receipts
                WHERE task_id = ?
                ORDER BY observed_at_ms DESC, accepted_at_ms DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (event.task_id, PROGRESS_RECEIPTS_PER_TASK),
        )
        connection.execute(
            "UPDATE task_heartbeats SET last_material_at_ms = MAX(COALESCE(last_material_at_ms, 0), ?), updated_at_ms = MAX(updated_at_ms, ?) WHERE task_id = ?",
            (progress.observed_at_ms, now_ms, event.task_id),
        )
        return "advanced"

    @staticmethod
    def _record_progress_pulse_file(
        connection: sqlite3.Connection,
        event_name: str,
        event: ProgressPulseEvent | None,
        *,
        digest: str,
        status: str,
        now_ms: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO task_progress_pulse_files(
                event_name, task_id, project_id, pulse_receipt, payload_digest,
                status, pulse_state, observed_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_name) DO UPDATE SET
                task_id=excluded.task_id,
                project_id=excluded.project_id,
                pulse_receipt=excluded.pulse_receipt,
                payload_digest=excluded.payload_digest,
                status=excluded.status,
                pulse_state=excluded.pulse_state,
                observed_at_ms=excluded.observed_at_ms,
                updated_at_ms=excluded.updated_at_ms
            """,
            (
                event_name,
                "" if event is None else event.task_id,
                "" if event is None else event.project_id,
                "" if event is None else event.pulse_receipt,
                digest,
                status,
                "" if event is None else event.state,
                0 if event is None else event.observed_at_ms,
                now_ms,
            ),
        )

    def ingest_progress_pulses(self, codex_home: Path, overview: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
        """Ingest bounded local sidecars for exact observed non-subagent tasks."""
        expected_swarm_root = codex_home.resolve() / "swarm"
        expected_pulse_root = codex_home.resolve() / PULSE_ROOT
        swarm_root = expected_swarm_root.resolve()
        pulse_root = expected_pulse_root.resolve()
        result: dict[str, Any] = {"advanced": 0, "heartbeats": 0, "duplicates": 0, "rejected": 0, "eta_reports": {}}
        if swarm_root != expected_swarm_root or pulse_root != expected_pulse_root or not pulse_root.is_dir():
            return result
        nodes = {
            str(node.get("id")): node
            for node in overview.get("nodes", [])
            if not node.get("virtual") and not node.get("is_subagent") and node.get("id") and node.get("project_id")
        }
        for index, event_path in enumerate(pulse_root.iterdir()):
            if index >= MAX_PULSE_FILES:
                break
            if event_path.suffix.casefold() != ".json":
                continue
            event: ProgressPulseEvent | None = None
            digest = ""
            try:
                resolved = event_path.resolve(strict=True)
                stat = resolved.stat()
                if not resolved.is_file() or resolved.parent != pulse_root or stat.st_size <= 0 or stat.st_size > MAX_PULSE_BYTES:
                    raise ConsoleError("progress pulse file violates the path or size guard")
                encoded = resolved.read_bytes()
                digest = hashlib.sha256(encoded.rstrip(b"\r\n")).hexdigest()
                event = validate_progress_pulse(json.loads(encoded.decode("utf-8")))
                expected_name = hashlib.sha256(event.task_id.encode("utf-8")).hexdigest() + ".json"
                node = nodes.get(event.task_id)
                if resolved.name != expected_name or node is None or str(node.get("project_id")) != event.project_id:
                    raise ConsoleError("progress pulse target is not an exact observed non-subagent task/project")
                with self._lock, closing(self._connect()) as connection:
                    prior = connection.execute(
                        "SELECT payload_digest, status, observed_at_ms FROM task_progress_pulse_files WHERE event_name = ?",
                        (resolved.name,),
                    ).fetchone()
                    if prior is not None and str(prior["payload_digest"]) == event.digest and str(prior["status"]) == "IMPORTED":
                        outcome = "duplicate"
                    else:
                        if prior is not None and event.observed_at_ms < int(prior["observed_at_ms"]):
                            raise ConsoleError("progress pulse file cannot regress its observed high-water")
                        outcome = self._record_progress_pulse(connection, event, now_ms=now_ms)
                        if event.eta_report is not None:
                            self._record_eta_receipt(
                                connection,
                                event.eta_report,
                                observed_task_id=event.task_id,
                                observed_project_id=event.project_id,
                                now_ms=now_ms,
                            )
                    self._record_progress_pulse_file(connection, resolved.name, event, digest=event.digest, status="IMPORTED", now_ms=now_ms)
                    connection.commit()
                if event.eta_report is not None:
                    result["eta_reports"][event.task_id] = event.eta_report
                if outcome == "advanced":
                    result["advanced"] += 1
                elif outcome == "heartbeat":
                    result["heartbeats"] += 1
                else:
                    result["duplicates"] += 1
            except (ConsoleError, ProgressEventError, OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, sqlite3.Error):
                result["rejected"] += 1
                try:
                    with self._lock, closing(self._connect()) as connection:
                        self._record_progress_pulse_file(connection, event_path.name, event, digest=digest, status="REJECTED", now_ms=now_ms)
                        connection.commit()
                except (OSError, sqlite3.Error):
                    pass
        return result

    def latest_progress(self) -> dict[str, dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM task_progress_state ORDER BY task_id").fetchall()
        return {
            str(row["task_id"]): {
                "project_id": row["project_id"],
                "progress_basis": {
                    "receipts": [row["receipt_id"]],
                    "plan_units": {
                        "plan_id": row["plan_id"],
                        "unit_id": row["unit_id"],
                        "unit_kind": row["unit_kind"],
                        "total_units": int(row["total_units"]),
                        "completed_units": int(row["completed_units"]),
                        "basis": row["basis"],
                        "observed_at_ms": int(row["observed_at_ms"]),
                    },
                },
                "receipt_source": f"instruction_only_local_sidecar:{row['source']}",
                "pulse_receipt": row["pulse_receipt"],
                "pulse_observed_at_ms": int(row["pulse_observed_at_ms"]),
                "pulse_state": row["pulse_state"],
                "claim_limit": "Validated local task-owner instruction sidecar only; not native host, user, progress, review, or acceptance authority.",
            }
            for row in rows
        }

    def observe_overview(self, overview: dict[str, Any], *, now_ms: int, trigger: str, heartbeat_minutes: int, codex_home: Path | None = None) -> None:
        nodes = [node for node in overview.get("nodes", []) if not node.get("virtual")]
        node_by_id = {str(node["id"]): node for node in nodes}
        # Filesystem discovery and JSONL parsing can be slow on a large sessions
        # tree. Complete one bounded shared scan before taking the SQLite lock so
        # passive readers remain responsive.
        jsonl_counts = (
            {}
            if codex_home is None
            else _codex_jsonl_token_counts(codex_home, set(node_by_id))
        )
        dependencies: dict[str, list[str]] = {}
        for link in overview.get("links", []):
            dependencies.setdefault(str(link["target"]), []).append(str(link["source"]))
        with self._lock, closing(self._connect()) as connection:
            bucket_ms = now_ms - (now_ms % (TOKEN_SAMPLE_SECONDS * 1000))
            for node in nodes:
                thread_id = _safe_metadata_text(str(node["id"]), "thread id", maximum=256)
                project_id = str(node.get("project_id") or "").strip()
                if project_id:
                    project_id = _safe_metadata_text(project_id, "project id", maximum=256)
                sqlite_cumulative = max(0, int(node.get("tokens") or 0))
                jsonl_cumulative = jsonl_counts.get(thread_id)
                cumulative = max(sqlite_cumulative, jsonl_cumulative or 0)
                source = TOKEN_SOURCE_CODEX_JSONL if jsonl_cumulative is not None and jsonl_cumulative >= sqlite_cumulative else TOKEN_SOURCE_SQLITE
                prior = connection.execute(
                    "SELECT cumulative_tokens FROM token_cursors WHERE thread_id = ?",
                    (thread_id,),
                ).fetchone()
                previous_high_water = 0 if prior is None else max(0, int(prior["cumulative_tokens"]))
                delta = 0 if prior is None else max(0, cumulative - previous_high_water)
                high_water = max(previous_high_water, cumulative)
                connection.execute(
                    """
                    INSERT INTO token_cursors(thread_id, project_id, cumulative_tokens, sampled_at_ms)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(thread_id) DO UPDATE SET
                        project_id=excluded.project_id,
                        cumulative_tokens=excluded.cumulative_tokens,
                        sampled_at_ms=excluded.sampled_at_ms
                    """,
                    (thread_id, project_id, high_water, now_ms),
                )
                connection.execute(
                    """
                    INSERT INTO token_samples(
                        bucket_ms, sampled_at_ms, project_id, thread_id,
                        cumulative_tokens, delta_tokens, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(bucket_ms, thread_id) DO UPDATE SET
                        sampled_at_ms=excluded.sampled_at_ms,
                        project_id=excluded.project_id,
                        cumulative_tokens=MAX(token_samples.cumulative_tokens, excluded.cumulative_tokens),
                        delta_tokens=token_samples.delta_tokens + excluded.delta_tokens,
                        source=CASE
                            WHEN token_samples.source = ? OR excluded.source = ?
                            THEN ?
                            ELSE ?
                        END
                    """,
                    (
                        bucket_ms,
                        now_ms,
                        project_id,
                        thread_id,
                        high_water,
                        delta,
                        source,
                        TOKEN_SOURCE_CODEX_JSONL,
                        TOKEN_SOURCE_CODEX_JSONL,
                        TOKEN_SOURCE_CODEX_JSONL,
                        TOKEN_SOURCE_SQLITE,
                    ),
                )

                updated_at = int(node.get("updated_at") or 0) or None
                status = str(node.get("status") or "quiet")
                dependency_ids = dependencies.get(thread_id, [])
                blocked_dependency = any(
                    str(node_by_id.get(dependency, {}).get("status")) not in {"done", "archived"}
                    for dependency in dependency_ids
                )
                connection.execute(
                    """
                    INSERT INTO task_heartbeats(
                        task_id, project_id, last_material_at_ms, last_liveness_at_ms,
                        scheduled_wake_at_ms, scheduled_wake_consumed, updated_at_ms
                    ) VALUES (?, ?, NULL, ?, NULL, 0, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        project_id=excluded.project_id,
                        last_liveness_at_ms=excluded.last_liveness_at_ms,
                        updated_at_ms=excluded.updated_at_ms
                    """,
                    (thread_id, project_id, now_ms, now_ms),
                )
                if project_id and not node.get("is_subagent") and isinstance(node.get("eta_report"), dict):
                    self._record_eta_receipt(
                        connection,
                        node["eta_report"],
                        observed_task_id=thread_id,
                        observed_project_id=project_id,
                        now_ms=now_ms,
                    )
            connection.execute(
                "DELETE FROM token_samples WHERE bucket_ms < ?",
                (self._retention_cutoff(now_ms),),
            )
            connection.commit()

    def latest_forecasts(self, project_id: str | None = None) -> dict[str, dict[str, Any]]:
        query = """
            SELECT forecast.* FROM eta_forecasts forecast
            JOIN (
                SELECT task_id, MAX(revision) revision
                FROM eta_forecasts GROUP BY task_id
            ) latest ON latest.task_id = forecast.task_id AND latest.revision = forecast.revision
        """
        args: tuple[Any, ...] = ()
        if project_id:
            query += " WHERE forecast.project_id = ?"
            args = (project_id,)
        query += " ORDER BY forecast.task_id"
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(query, args).fetchall()
        return {
            str(row["task_id"]): {
                "project_id": row["project_id"],
                "revision": int(row["revision"]),
                "eta_start_ms": row["eta_start_ms"],
                "eta_end_ms": row["eta_end_ms"],
                "confidence": int(row["confidence"]),
                "status": row["status"],
                "reason": row["reason"],
                "last_progress_at_ms": row["last_progress_at_ms"],
                "last_calculated_at_ms": int(row["last_calculated_at_ms"]),
                "trigger": row["trigger"],
                "baseline_eta_start_ms": row["baseline_eta_start_ms"],
                "baseline_eta_end_ms": row["baseline_eta_end_ms"],
                "baseline_confidence": row["baseline_confidence"],
                "delta_from_baseline_ms": row["delta_from_baseline_ms"],
                "progress_basis": json.loads(row["progress_basis_json"] or "{}"),
                "last_material_heartbeat_at_ms": row["last_material_heartbeat_at_ms"],
                "reason_code": row["reason_code"] or "unknown",
                "short_reason": row["short_reason"] or row["reason"],
                "receipt_source": row["receipt_source"] or "host_overview",
                "previous": json.loads(row["previous_forecast_json"] or "null"),
                "current": json.loads(row["current_forecast_json"] or "null"),
                "claim_limit": "Observed task-owner planning report only; it does not prove host/user authority, acceptance, or task progress.",
            }
            for row in rows
        }

    def skill_catalog(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM skill_catalog ORDER BY skill_id").fetchall()
        return [
            {
                "skill_id": row["skill_id"],
                "source_repo": row["source_repo"],
                "source_path": row["source_path"],
                "source_ref": row["source_ref"],
                "source_version": row["source_version"],
                "popularity": json.loads(row["popularity_json"]),
                "audit": json.loads(row["audit_json"]),
                "review_status": row["review_status"],
                "installed": bool(row["installed"]),
                "builtin": bool(row["builtin"]),
                "allowed_roles": json.loads(row["allowed_roles_json"]),
                "allowed_task_kinds": json.loads(row["allowed_task_kinds_json"]),
                "last_checked_ms": int(row["last_checked_ms"]),
            }
            for row in rows
        ]

    def skill_scope(self, scope_type: str, scope_id: str) -> dict[str, Any] | None:
        from skills_catalog import validate_scope
        validate_scope(scope_type, scope_id)
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM skill_scope_overlays WHERE scope_type = ? AND scope_id = ?",
                (scope_type, scope_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "scope_type": row["scope_type"],
            "scope_id": row["scope_id"],
            "revision": int(row["revision"]),
            "inheritance_enabled": None if row["inheritance_enabled"] is None else bool(row["inheritance_enabled"]),
            "profile": row["profile"],
            "preferred_ids": json.loads(row["preferred_ids_json"]),
            "updated_at_ms": int(row["updated_at_ms"]),
        }

    def update_skill_scope(
        self,
        scope_type: str,
        scope_id: str,
        changes: dict[str, Any],
        *,
        expected_revision: int,
        now_ms: int,
    ) -> dict[str, Any]:
        from skills_catalog import validate_preferred_ids, validate_profile, validate_scope
        validate_scope(scope_type, scope_id)
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise ConsoleError("expected_revision must be a non-negative integer")
        if not isinstance(changes, dict) or not changes or set(changes) - {"inheritance_enabled", "profile", "preferred_ids"}:
            raise ConsoleError("skill scope changes are limited to inheritance_enabled, profile, and preferred_ids")
        catalog = self.skill_catalog()
        known_ids = {item["skill_id"] for item in catalog}
        current = self.skill_scope(scope_type, scope_id)
        revision = 0 if current is None else current["revision"]
        if revision != expected_revision:
            raise ConsoleConflict("skill scope changed; reload before saving")
        candidate = {
            "inheritance_enabled": None if current is None else current["inheritance_enabled"],
            "profile": "default" if current is None else current["profile"],
            "preferred_ids": [] if current is None else current["preferred_ids"],
        }
        if "inheritance_enabled" in changes and not isinstance(changes["inheritance_enabled"], bool):
            raise ConsoleError("inheritance_enabled must be a boolean")
        if "inheritance_enabled" in changes:
            candidate["inheritance_enabled"] = changes["inheritance_enabled"]
        if "profile" in changes:
            candidate["profile"] = validate_profile(changes["profile"])
        if "preferred_ids" in changes:
            candidate["preferred_ids"] = validate_preferred_ids(changes["preferred_ids"], known_ids)
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO skill_scope_overlays(
                    scope_type, scope_id, revision, inheritance_enabled, profile, preferred_ids_json, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_type, scope_id) DO UPDATE SET
                    revision=excluded.revision,
                    inheritance_enabled=excluded.inheritance_enabled,
                    profile=excluded.profile,
                    preferred_ids_json=excluded.preferred_ids_json,
                    updated_at_ms=excluded.updated_at_ms
                """,
                (
                    scope_type, scope_id, revision + 1,
                    None if candidate["inheritance_enabled"] is None else int(candidate["inheritance_enabled"]),
                    candidate["profile"], json.dumps(candidate["preferred_ids"], separators=(",", ":")), now_ms,
                ),
            )
            connection.commit()
        return self.skill_scope(scope_type, scope_id) or {}

    def reset_skill_scope(self, scope_type: str, scope_id: str, *, expected_revision: int) -> bool:
        from skills_catalog import validate_scope
        validate_scope(scope_type, scope_id)
        current = self.skill_scope(scope_type, scope_id)
        revision = 0 if current is None else current["revision"]
        if revision != expected_revision:
            raise ConsoleConflict("skill scope changed; reload before resetting")
        with self._lock, closing(self._connect()) as connection:
            deleted = connection.execute(
                "DELETE FROM skill_scope_overlays WHERE scope_type = ? AND scope_id = ?",
                (scope_type, scope_id),
            ).rowcount
            connection.commit()
        return bool(deleted)

    @staticmethod
    def _public_proof_row(row: sqlite3.Row) -> dict[str, Any]:
        public_fields = (
            "evidence_id", "task_id", "project_id", "kind", "caption",
            "claim_limit", "disposition", "surface_kind", "media_type",
            "size_bytes", "digest", "registered_at_ms", "updated_at_ms",
        )
        return {field: row[field] for field in public_fields}

    def proof_feed(self, *, project_id: str | None = None, task_id: str | None = None) -> list[dict[str, Any]]:
        conditions: list[str] = ["disposition = 'PENDING'"]
        args: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            args.append(project_id)
        if task_id:
            conditions.append("task_id = ?")
            args.append(task_id)
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM proof_media WHERE " + " AND ".join(conditions)
                + " ORDER BY updated_at_ms DESC, evidence_id DESC",
                tuple(args),
            ).fetchall()
        return [self._public_proof_row(row) for row in rows]

    @staticmethod
    def _proof_feed_identity(connection: sqlite3.Connection) -> tuple[str, bool]:
        columns = (
            "evidence_id", "task_id", "project_id", "kind", "locator", "caption",
            "claim_limit", "disposition", "receipt", "surface_kind", "media_type",
            "mtime_ns", "size_bytes", "digest", "registered_at_ms", "updated_at_ms",
        )
        rows = connection.execute(
            "SELECT " + ", ".join(columns)
            + " FROM proof_media WHERE disposition='PENDING' ORDER BY evidence_id"
        ).fetchall()
        material = [[row[column] for column in columns] for row in rows]
        identity = hashlib.sha256(
            json.dumps(material, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return identity, bool(rows)

    @staticmethod
    def _stored_proof_cursor(connection: sqlite3.Connection) -> tuple[int, str | None]:
        row = connection.execute(
            "SELECT value FROM store_metadata WHERE key = ?",
            (PROOF_FEED_CURSOR_KEY,),
        ).fetchone()
        if row is None:
            return 0, None
        try:
            state = json.loads(str(row["value"]))
        except (json.JSONDecodeError, TypeError, ValueError):
            return 0, None
        if not isinstance(state, dict):
            return 0, None
        sequence = state.get("sequence")
        sequence = sequence if isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 0 else 0
        identity = state.get("identity")
        identity = identity if isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{64}", identity) else None
        return sequence, identity

    @staticmethod
    def _persist_proof_cursor(connection: sqlite3.Connection, sequence: int, identity: str) -> None:
        connection.execute(
            "INSERT INTO store_metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (
                PROOF_FEED_CURSOR_KEY,
                json.dumps(
                    {"sequence": sequence, "identity": identity},
                    ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                ),
            ),
        )

    def _advance_proof_cursor(self, connection: sqlite3.Connection) -> dict[str, Any]:
        identity, has_rows = self._proof_feed_identity(connection)
        prior_sequence, prior_identity = self._stored_proof_cursor(connection)
        sequence = prior_sequence
        if prior_identity != identity:
            sequence = prior_sequence + 1 if has_rows or prior_identity is not None else prior_sequence
            self._persist_proof_cursor(connection, sequence, identity)
        return {"sequence": sequence, "identity": identity}

    def proof_cursor(self) -> dict[str, Any]:
        """Return a stable proof-feed cursor without mutating the read path."""
        with self._lock, closing(self._connect()) as connection:
            identity, has_rows = self._proof_feed_identity(connection)
            prior_sequence, prior_identity = self._stored_proof_cursor(connection)
        sequence = prior_sequence
        if prior_identity != identity:
            sequence = prior_sequence + 1 if has_rows or prior_identity is not None else prior_sequence
        return {"sequence": sequence, "identity": identity}

    def proof_sequence(self) -> int:
        """Return the UI-compatible sequence from the durable proof cursor."""
        return int(self.proof_cursor()["sequence"])

    def proof_media_item(self, evidence_id: str, digest: str, *, allowed_root: Path | None = None) -> dict[str, Any]:
        evidence_id = _safe_metadata_text(evidence_id, "evidence_id", maximum=256)
        digest = _safe_metadata_text(digest, "digest", maximum=64).casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ConsoleError("proof media digest must be a SHA-256 hex digest")
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM proof_media WHERE evidence_id=? AND disposition='PENDING'",
                (evidence_id,),
            ).fetchone()
        if row is None or row["media_type"] not in MEDIA_TYPES or not str(row["media_type"]).startswith(("image/", "video/")):
            raise ConsoleError("registered proof media was not found")
        if str(row["digest"] or "").casefold() != digest:
            raise ConsoleError("proof media digest does not match the registered evidence")
        path = Path(str(row["locator"])).expanduser()
        try:
            resolved = path.resolve(strict=True)
            stat = resolved.stat()
        except OSError as exc:
            raise ConsoleError("registered proof media is unavailable") from exc
        if not resolved.is_file() or stat.st_size > MEDIA_MAX_HASH_BYTES:
            raise ConsoleError("registered proof media exceeds the delivery guard")
        if row["size_bytes"] is not None and int(row["size_bytes"]) != stat.st_size:
            raise ConsoleError("registered proof media changed since registration")
        current = _media_metadata(str(resolved), digest, allowed_root=allowed_root)
        if current["digest"] != digest:
            raise ConsoleError("registered proof media digest no longer matches the file")
        return {
            "path": resolved,
            "media_type": str(row["media_type"]),
            "size_bytes": int(stat.st_size),
            "digest": digest,
            "evidence_id": evidence_id,
        }

    def proof_snapshot(self, task_id: str) -> dict[str, Any]:
        media = self.proof_feed(task_id=task_id)
        return {
            "available": bool(media),
            "state": "MEDIA_AVAILABLE" if media else "UNAVAILABLE",
            "task_id": task_id,
            "media": media,
            "claim_limit": "Available for review; acceptance is recorded separately.",
        }

    def record_proof_media(
        self,
        payload: dict[str, Any],
        *,
        now_ms: int,
        allowed_root: Path | None = None,
    ) -> dict[str, Any]:
        evidence_id = _safe_metadata_text(payload.get("evidence_id"), "evidence_id", maximum=256)
        task_id = _safe_metadata_text(payload.get("task_id"), "task_id", maximum=256)
        project_id = _safe_metadata_text(payload.get("project_id"), "project_id", maximum=256)
        kind = _safe_metadata_text(payload.get("kind"), "kind", maximum=64).casefold()
        locator = _safe_metadata_text(payload.get("locator"), "locator", maximum=4096)
        disposition = _safe_metadata_text(payload.get("disposition"), "disposition", maximum=32).upper()
        if payload.get("source") != "CtrlEvidence":
            raise ConsoleError("proof media must name CtrlEvidence as its source")
        if kind not in MEDIA_KINDS or Path(locator).suffix.casefold() not in MEDIA_EXTENSIONS:
            raise ConsoleError("proof media kind or file extension is not allowlisted")
        if disposition != "PENDING":
            raise ConsoleError("console registration may only make proof available for review")
        caption = _safe_proof_copy(payload.get("caption", "Proof media"), "caption")
        claim_limit = _safe_proof_copy(payload.get("claim_limit", "Available for review; acceptance is recorded separately."), "scope")
        receipt = _safe_metadata_text(payload.get("receipt", "ctrl-evidence:registered"), "receipt")
        surface_kind = "available_media"
        supplied_size = payload.get("size_bytes")
        if supplied_size is not None and (not isinstance(supplied_size, int) or isinstance(supplied_size, bool)):
            raise ConsoleError("proof media size must be an integer")
        metadata = _media_metadata(
            locator,
            str(payload.get("digest", "")),
            allowed_root=allowed_root,
            supplied_size=supplied_size,
            supplied_media_type=str(payload.get("media_type", "")),
        )
        if metadata["media_type"] not in MEDIA_TYPES:
            raise ConsoleError("proof media type is not allowlisted")
        with self._lock, closing(self._connect()) as connection:
            existing = connection.execute(
                "SELECT * FROM proof_media WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
            values = {
                "task_id": task_id,
                "project_id": project_id,
                "kind": kind,
                "locator": metadata["path"],
                "caption": caption,
                "claim_limit": claim_limit,
                "disposition": disposition,
                "receipt": receipt,
                "surface_kind": surface_kind,
                "media_type": metadata["media_type"],
                "mtime_ns": metadata["mtime_ns"],
                "size_bytes": metadata["size_bytes"],
                "digest": metadata["digest"],
            }
            if existing is not None:
                immutable_fields = tuple(values)
                if any(existing[field] != values[field] for field in immutable_fields):
                    raise ConsoleError("evidence_id already names a different immutable proof receipt")
                return self._public_proof_row(existing)
            connection.execute(
                """
                INSERT INTO proof_media(
                    evidence_id, task_id, project_id, kind, locator, caption,
                    claim_limit, disposition, receipt, surface_kind, media_type,
                    mtime_ns, size_bytes, digest, registered_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    task_id,
                    project_id,
                    kind,
                    metadata["path"],
                    caption,
                    claim_limit,
                    disposition,
                    receipt,
                    surface_kind,
                    metadata["media_type"],
                    metadata["mtime_ns"],
                    metadata["size_bytes"],
                    metadata["digest"],
                    now_ms,
                    now_ms,
                ),
            )
            self._advance_proof_cursor(connection)
            connection.commit()
            row = connection.execute("SELECT * FROM proof_media WHERE evidence_id=?", (evidence_id,)).fetchone()
        return self._public_proof_row(row)

    def _proof_event_receipts(self) -> dict[str, dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT receipts.event_name, receipts.event_mtime_ns,
                       receipts.event_size, receipts.event_digest, receipts.status,
                       receipts.evidence_id, receipts.task_id, receipts.project_id,
                       receipts.media_digest,
                       media.evidence_id IS NOT NULL AS media_present
                  FROM proof_event_receipts receipts
             LEFT JOIN proof_media media ON media.evidence_id = receipts.evidence_id
                """
            ).fetchall()
        return {
            str(row["event_name"]): {
                "mtime_ns": int(row["event_mtime_ns"]),
                "size": int(row["event_size"]),
                "event_digest": str(row["event_digest"] or ""),
                "status": str(row["status"]),
                "evidence_id": str(row["evidence_id"]),
                "task_id": str(row["task_id"] or ""),
                "project_id": str(row["project_id"] or ""),
                "media_digest": str(row["media_digest"] or ""),
                "media_present": bool(row["media_present"]),
            }
            for row in rows
        }

    def _proof_event_scan_queue(self) -> list[str]:
        start_token = "P:" if os.name == "nt" else "D:0"
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT value FROM store_metadata WHERE key=?",
                (PROOF_EVENT_SCAN_STATE_KEY,),
            ).fetchone()
        if row is None:
            return [start_token]
        try:
            value = json.loads(str(row["value"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return [start_token]
        if not isinstance(value, list) or len(value) > 16384:
            return [start_token]
        queue = [str(token) for token in value]
        if any(
            (
                token.startswith(("P:", "E:"))
                and any(character not in PROOF_EVENT_PREFIX_ALPHABET for character in token[2:])
            )
            or (token.startswith("D:") and not token[2:].isdigit())
            or not token.startswith(("P:", "E:", "D:"))
            for token in queue
        ):
            return [start_token]
        if (os.name == "nt" and any(token.startswith("D:") for token in queue)) or (
            os.name != "nt" and any(token.startswith("P:") for token in queue)
        ):
            return [start_token]
        return queue or [start_token]

    def _set_proof_event_scan_queue(self, queue: list[str]) -> None:
        value = json.dumps(queue, separators=(",", ":"))
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO store_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                WHERE store_metadata.value != excluded.value
                """,
                (PROOF_EVENT_SCAN_STATE_KEY, value),
            )
            connection.commit()

    @staticmethod
    def _proof_event_prefix_matches(event_root: Path, prefix: str, limit: int) -> list[Path]:
        """Return at most limit native-filtered matches without walking the directory."""
        if os.name != "nt":
            raise OSError("bounded native proof-event traversal is unavailable on this host")
        import ctypes
        from ctypes import wintypes

        class FindData(ctypes.Structure):
            _fields_ = [
                ("attributes", wintypes.DWORD),
                ("creation_time", wintypes.FILETIME),
                ("last_access_time", wintypes.FILETIME),
                ("last_write_time", wintypes.FILETIME),
                ("file_size_high", wintypes.DWORD),
                ("file_size_low", wintypes.DWORD),
                ("reserved0", wintypes.DWORD),
                ("reserved1", wintypes.DWORD),
                ("file_name", wintypes.WCHAR * 260),
                ("alternate_file_name", wintypes.WCHAR * 14),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        find_first = kernel32.FindFirstFileExW
        find_first.argtypes = [
            wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        find_first.restype = wintypes.HANDLE
        find_next = kernel32.FindNextFileW
        find_next.argtypes = [wintypes.HANDLE, ctypes.POINTER(FindData)]
        find_next.restype = wintypes.BOOL
        find_close = kernel32.FindClose
        find_close.argtypes = [wintypes.HANDLE]
        find_close.restype = wintypes.BOOL
        data = FindData()
        pattern = str(event_root / f"{prefix}*.json")
        handle = find_first(pattern, 1, ctypes.byref(data), 0, None, 2)
        invalid_handle = ctypes.c_void_p(-1).value
        if handle == invalid_handle:
            error = ctypes.get_last_error()
            if error in (2, 18):
                return []
            raise OSError(error, "native proof-event enumeration failed", pattern)
        matches: list[Path] = []
        try:
            while len(matches) < limit:
                name = str(data.file_name)
                if name not in (".", ".."):
                    matches.append(event_root / name)
                if len(matches) >= limit or not find_next(handle, ctypes.byref(data)):
                    break
        finally:
            find_close(handle)
        return sorted(matches, key=lambda path: path.name.casefold())

    @staticmethod
    def _proof_event_linux_batch(
        event_root: Path,
        offset: int,
        limit: int,
    ) -> tuple[list[Path], int, bool, int]:
        """Read a bounded Linux directory batch and retain its native cursor."""
        if not sys.platform.startswith("linux"):
            raise OSError("bounded native proof-event traversal is unavailable on this host")
        import ctypes

        class Dirent(ctypes.Structure):
            _fields_ = [
                ("d_ino", ctypes.c_ulong),
                ("d_off", ctypes.c_long),
                ("d_reclen", ctypes.c_ushort),
                ("d_type", ctypes.c_ubyte),
                ("d_name", ctypes.c_char * 256),
            ]

        libc = ctypes.CDLL(None, use_errno=True)
        opendir = libc.opendir
        opendir.argtypes = [ctypes.c_char_p]
        opendir.restype = ctypes.c_void_p
        readdir = libc.readdir
        readdir.argtypes = [ctypes.c_void_p]
        readdir.restype = ctypes.POINTER(Dirent)
        seekdir = libc.seekdir
        seekdir.argtypes = [ctypes.c_void_p, ctypes.c_long]
        seekdir.restype = None
        telldir = libc.telldir
        telldir.argtypes = [ctypes.c_void_p]
        telldir.restype = ctypes.c_long
        closedir = libc.closedir
        closedir.argtypes = [ctypes.c_void_p]
        closedir.restype = ctypes.c_int

        directory = opendir(os.fsencode(event_root))
        if not directory:
            error = ctypes.get_errno()
            raise OSError(error, "native proof-event directory open failed", str(event_root))
        matches: list[Path] = []
        enumerated = 0
        exhausted = False
        try:
            if offset:
                seekdir(directory, offset)
            while enumerated < limit:
                ctypes.set_errno(0)
                entry = readdir(directory)
                if not entry:
                    error = ctypes.get_errno()
                    if error:
                        raise OSError(error, "native proof-event enumeration failed", str(event_root))
                    exhausted = True
                    break
                name_bytes = bytes(entry.contents.d_name).split(b"\0", 1)[0]
                name = os.fsdecode(name_bytes)
                if name in (".", ".."):
                    continue
                enumerated += 1
                if name.endswith(".json"):
                    matches.append(event_root / name)
            next_offset = int(telldir(directory))
            if next_offset < 0:
                error = ctypes.get_errno()
                raise OSError(error, "native proof-event cursor read failed", str(event_root))
        finally:
            closedir(directory)
        return sorted(matches, key=lambda path: path.name.casefold()), next_offset, exhausted, enumerated

    def _bounded_linux_proof_event_paths(
        self,
        event_root: Path,
    ) -> tuple[list[Path], bool, int, list[str]]:
        queue = self._proof_event_scan_queue()
        checked_tokens = 0
        while queue and checked_tokens < MAX_PROOF_EVENT_FILES + 2:
            token = queue.pop(0)
            checked_tokens += 1
            kind, value = token[:1], token[2:]
            if kind == "E":
                exact_values = [value]
                while (
                    queue
                    and queue[0].startswith("E:")
                    and len(exact_values) < MAX_PROOF_EVENT_FILES
                ):
                    exact_values.append(queue.pop(0)[2:])
                paths = [
                    event_root / f"{exact_value}.json"
                    for exact_value in exact_values
                    if (event_root / f"{exact_value}.json").is_file()
                ]
                return paths, bool(queue), len(exact_values), queue
            if kind != "D":
                continue
            matches, next_offset, exhausted, enumerated = self._proof_event_linux_batch(
                event_root,
                int(value),
                MAX_PROOF_EVENT_FILES + 1,
            )
            continuation = queue + ([] if exhausted else [f"D:{next_offset}"])
            if len(matches) > MAX_PROOF_EVENT_FILES:
                exact = [f"E:{path.stem}" for path in matches]
                return [], True, enumerated, exact + continuation
            if matches:
                return matches, bool(continuation), enumerated, continuation
            if not exhausted:
                return [], True, enumerated, continuation
        return [], bool(queue), 0, queue

    def _bounded_proof_event_paths(self, event_root: Path) -> tuple[list[Path], bool, int, list[str]]:
        if os.name != "nt":
            return self._bounded_linux_proof_event_paths(event_root)
        queue = self._proof_event_scan_queue()
        checked_tokens = 0
        while queue and checked_tokens < len(PROOF_EVENT_PREFIX_ALPHABET) + 2:
            token = queue.pop(0)
            checked_tokens += 1
            kind, prefix = token[:1], token[2:]
            if kind == "E":
                path = event_root / f"{prefix}.json"
                return ([path] if path.is_file() else []), bool(queue), int(path.is_file()), queue
            matches = self._proof_event_prefix_matches(
                event_root,
                prefix,
                MAX_PROOF_EVENT_FILES + 1,
            )
            if len(matches) > MAX_PROOF_EVENT_FILES:
                if len(prefix) >= 255:
                    raise OSError("proof-event prefix cannot be partitioned safely")
                children = ([f"E:{prefix}"] if prefix else []) + [
                    f"P:{prefix}{character}" for character in PROOF_EVENT_PREFIX_ALPHABET
                ]
                return [], True, len(matches), children + queue
            if matches:
                return matches, bool(queue), len(matches), queue
        return [], bool(queue), 0, queue

    def _bind_legacy_proof_event_receipt(
        self,
        event_name: str,
        *,
        event_digest: str,
        task_id: str,
        project_id: str,
        media_digest: str,
    ) -> None:
        """Bind nullable pre-contract fields once; never alter an existing binding."""
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE proof_event_receipts
                   SET event_digest=COALESCE(NULLIF(event_digest, ''), ?),
                       task_id=COALESCE(NULLIF(task_id, ''), ?),
                       project_id=COALESCE(NULLIF(project_id, ''), ?),
                       media_digest=COALESCE(NULLIF(media_digest, ''), ?)
                 WHERE event_name=? AND status='IMPORTED'
                   AND (event_digest IS NULL OR event_digest='' OR event_digest=?)
                   AND (task_id IS NULL OR task_id='' OR task_id=?)
                   AND (project_id IS NULL OR project_id='' OR project_id=?)
                   AND (media_digest IS NULL OR media_digest='' OR media_digest=?)
                """,
                (
                    event_digest, task_id, project_id, media_digest, event_name,
                    event_digest, task_id, project_id, media_digest,
                ),
            )
            row = connection.execute(
                "SELECT event_digest, task_id, project_id, media_digest FROM proof_event_receipts WHERE event_name=?",
                (event_name,),
            ).fetchone()
            if row is None or tuple(str(value or "") for value in row) != (
                event_digest, task_id, project_id, media_digest,
            ):
                connection.rollback()
                raise ConsoleError("legacy proof event receipt conflicts with immutable evidence")
            connection.commit()

    def _record_proof_event_receipt(
        self,
        event_name: str,
        *,
        mtime_ns: int,
        size: int,
        status: str,
        evidence_id: str,
        event_digest: str,
        task_id: str,
        project_id: str,
        media_digest: str,
        now_ms: int,
    ) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO proof_event_receipts(
                    event_name, event_mtime_ns, event_size, event_digest, status,
                    evidence_id, task_id, project_id, media_digest, observed_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_name) DO NOTHING
                """,
                (
                    event_name, mtime_ns, size, event_digest, status,
                    evidence_id, task_id, project_id, media_digest, now_ms,
                ),
            )
            row = connection.execute(
                "SELECT * FROM proof_event_receipts WHERE event_name=?",
                (event_name,),
            ).fetchone()
            expected = (
                mtime_ns, size, event_digest, status, evidence_id,
                task_id, project_id, media_digest,
            )
            actual = (
                int(row["event_mtime_ns"]), int(row["event_size"]),
                str(row["event_digest"] or ""), str(row["status"]),
                str(row["evidence_id"]), str(row["task_id"] or ""),
                str(row["project_id"] or ""), str(row["media_digest"] or ""),
            )
            if actual != expected:
                connection.rollback()
                raise ConsoleError("proof event filename is permanently bound to different evidence")
            connection.commit()

    def reconcile_proof_events(self, codex_home: Path, overview: dict[str, Any], *, now_ms: int) -> dict[str, int]:
        """Reconcile one bounded immutable proof-event pass without reading task messages."""
        expected_swarm_root = codex_home.resolve() / "swarm"
        expected_event_root = codex_home.resolve() / PROOF_EVENT_ROOT
        expected_media_root = codex_home.resolve() / PROOF_MEDIA_ROOT
        swarm_root = expected_swarm_root.resolve()
        event_root = expected_event_root.resolve()
        media_root = expected_media_root.resolve()
        if swarm_root != expected_swarm_root or event_root != expected_event_root or media_root != expected_media_root:
            return {"imported": 0, "duplicates": 0, "rejected": 0, "retryable": 1, "capped": 0, "enumerated": 0}
        if not event_root.is_dir() or not media_root.is_dir():
            return {"imported": 0, "duplicates": 0, "rejected": 0, "retryable": 0, "capped": 0, "enumerated": 0}
        nodes = {
            str(node.get("id")): node
            for node in overview.get("nodes", [])
            if not node.get("virtual") and node.get("id") and node.get("project_id")
        }
        receipts = self._proof_event_receipts()
        imported = 0
        duplicates = 0
        rejected = 0
        retryable = 0
        try:
            event_paths, capped_pass, enumerated, next_scan_queue = self._bounded_proof_event_paths(event_root)
        except OSError:
            return {
                "imported": 0, "duplicates": 0, "rejected": 0,
                "retryable": 1, "capped": 0, "enumerated": 0,
            }
        capped = int(capped_pass)
        for event_path in event_paths:
            event_stat: os.stat_result | None = None
            evidence_id = ""
            task_id = ""
            project_id = ""
            event_digest = ""
            media_digest = ""
            try:
                resolved_event = event_path.resolve(strict=True)
                event_stat = resolved_event.stat()
                if not resolved_event.is_file() or not resolved_event.is_relative_to(event_root) or event_stat.st_size > 16 * 1024:
                    continue
                event_bytes = resolved_event.read_bytes()
                if len(event_bytes) != event_stat.st_size:
                    raise OSError("proof event changed while being read")
                event_digest = hashlib.sha256(event_bytes).hexdigest()
                receipt = receipts.get(resolved_event.name)
                if receipt is not None:
                    if (
                        receipt["mtime_ns"] != event_stat.st_mtime_ns
                        or receipt["size"] != event_stat.st_size
                        or (receipt["event_digest"] and receipt["event_digest"] != event_digest)
                    ):
                        rejected += 1
                        continue
                    if receipt["status"] == "REJECTED":
                        rejected += 1
                        continue
                    if receipt["status"] == "IMPORTED" and receipt["event_digest"] and receipt["media_present"]:
                        duplicates += 1
                        continue
                event = json.loads(event_bytes.decode("utf-8"))
                if not isinstance(event, dict) or event.get("schema_version") != 1 or event.get("source") != "CtrlEvidence":
                    raise ConsoleError("proof event envelope is invalid")
                if PROOF_EVENT_PRIVATE_FIELDS.intersection(key.casefold() for key in event):
                    raise ConsoleError("proof event includes prohibited private content")
                evidence_id = _safe_metadata_text(event.get("evidence_id"), "evidence_id", maximum=256)
                task_id = _safe_metadata_text(event.get("task_id"), "task_id", maximum=256)
                node = nodes.get(task_id)
                observed_project_id = str(node["project_id"]) if node is not None else observed_task_project_id(codex_home, task_id)
                if observed_project_id is None:
                    retryable += 1
                    continue
                project_id = observed_project_id
                relative = Path(_safe_metadata_text(event.get("locator"), "locator", maximum=512))
                if relative.is_absolute() or ".." in relative.parts:
                    raise ConsoleError("proof event locator escapes the evidence store")
                locator = (swarm_root / relative).resolve(strict=True)
                payload = {
                    **event,
                    "task_id": task_id,
                    "project_id": project_id,
                    "locator": str(locator),
                    "disposition": "PENDING",
                    "receipt": f"proof-event:{resolved_event.stem}",
                    "surface_kind": "available_media",
                }
                metadata = _media_metadata(
                    str(locator),
                    str(event.get("digest", "")),
                    allowed_root=media_root,
                    supplied_size=event.get("size_bytes"),
                    supplied_media_type=str(event.get("media_type", "")),
                )
                media_digest = str(metadata["digest"])
                if receipt is not None:
                    bound = (
                        receipt["evidence_id"], receipt["task_id"],
                        receipt["project_id"], receipt["media_digest"],
                    )
                    current = (evidence_id, task_id, project_id, media_digest)
                    if receipt["event_digest"]:
                        if bound != current:
                            raise ConsoleError("proof event receipt identity changed")
                    else:
                        if (
                            receipt["evidence_id"] != evidence_id
                            or (receipt["task_id"] and receipt["task_id"] != task_id)
                            or (receipt["project_id"] and receipt["project_id"] != project_id)
                            or (receipt["media_digest"] and receipt["media_digest"] != media_digest)
                        ):
                            raise ConsoleError("legacy proof event receipt cannot be bound safely")
                        self._bind_legacy_proof_event_receipt(
                            resolved_event.name,
                            event_digest=event_digest,
                            task_id=task_id,
                            project_id=project_id,
                            media_digest=media_digest,
                        )
                self.record_proof_media(payload, now_ms=now_ms, allowed_root=media_root)
                if receipt is None:
                    self._record_proof_event_receipt(
                        resolved_event.name,
                        mtime_ns=event_stat.st_mtime_ns,
                        size=event_stat.st_size,
                        status="IMPORTED",
                        evidence_id=evidence_id,
                        event_digest=event_digest,
                        task_id=task_id,
                        project_id=project_id,
                        media_digest=media_digest,
                        now_ms=now_ms,
                    )
                    imported += 1
                elif receipt["media_present"]:
                    duplicates += 1
                else:
                    imported += 1
            except (OSError, sqlite3.Error):
                retryable += 1
                continue
            except (ConsoleError, ValueError, TypeError, json.JSONDecodeError) as exc:
                if isinstance(exc.__cause__, OSError):
                    retryable += 1
                    continue
                if event_stat is not None:
                    try:
                        self._record_proof_event_receipt(
                            event_path.name,
                            mtime_ns=event_stat.st_mtime_ns,
                            size=event_stat.st_size,
                            status="REJECTED",
                            evidence_id=evidence_id,
                            event_digest=event_digest,
                            task_id=task_id,
                            project_id=project_id,
                            media_digest=media_digest,
                            now_ms=now_ms,
                        )
                        rejected += 1
                    except ConsoleError:
                        rejected += 1
                    except sqlite3.Error:
                        retryable += 1
                continue
        try:
            self._set_proof_event_scan_queue(next_scan_queue)
        except sqlite3.Error:
            retryable += 1
        return {
            "imported": imported,
            "duplicates": duplicates,
            "rejected": rejected,
            "retryable": retryable,
            "capped": capped,
            "enumerated": enumerated,
        }

    def ingest_proof_events(self, codex_home: Path, overview: dict[str, Any], *, now_ms: int) -> int:
        """Compatibility wrapper returning only newly imported proof events."""
        return self.reconcile_proof_events(codex_home, overview, now_ms=now_ms)["imported"]

    def token_history(
        self,
        *,
        project_id: str | None = None,
        thread_ids: set[str] | frozenset[str] | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        cutoff = int(time.time() * 1000) - max(1, min(24 * 30, int(hours))) * 60 * 60 * 1000
        conditions = ["bucket_ms >= ?"]
        args: list[Any] = [cutoff]
        if project_id:
            conditions.append("project_id = ?")
            args.append(project_id)
        if thread_ids is not None:
            safe_thread_ids = tuple(sorted(set(thread_ids)))
            if not safe_thread_ids:
                return []
            placeholders = ",".join("?" for _ in safe_thread_ids)
            conditions.append(f"thread_id IN ({placeholders})")
            args.extend(safe_thread_ids)
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT bucket_ms, SUM(delta_tokens) delta_tokens, "
                "GROUP_CONCAT(DISTINCT source) sources FROM token_samples WHERE "
                + " AND ".join(conditions)
                + " GROUP BY bucket_ms ORDER BY bucket_ms",
                tuple(args),
            ).fetchall()
        return [
            {
                "bucket_ms": int(row["bucket_ms"]),
                "delta_tokens": int(row["delta_tokens"]),
                "source": (
                    TOKEN_SOURCE_CODEX_JSONL
                    if TOKEN_SOURCE_CODEX_JSONL in str(row["sources"] or "").split(",")
                    else TOKEN_SOURCE_SQLITE
                ),
            }
            for row in rows
        ]

    def token_sample_series(
        self,
        *,
        project_id: str,
        thread_ids: set[str] | frozenset[str] | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Return bounded task-bound token deltas for ledger projections."""
        cutoff = int(time.time() * 1000) - max(1, min(24 * 30, int(hours))) * 60 * 60 * 1000
        conditions = ["bucket_ms >= ?", "project_id = ?"]
        args: list[Any] = [cutoff, project_id]
        if thread_ids is not None:
            safe_thread_ids = tuple(sorted(set(thread_ids)))
            if not safe_thread_ids:
                return []
            placeholders = ",".join("?" for _ in safe_thread_ids)
            conditions.append(f"thread_id IN ({placeholders})")
            args.extend(safe_thread_ids)
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT bucket_ms, thread_id, delta_tokens FROM token_samples WHERE "
                + " AND ".join(conditions)
                + " ORDER BY bucket_ms, thread_id",
                tuple(args),
            ).fetchall()
        return [{
            "observed_at_ms": int(row["bucket_ms"]),
            "task_id": str(row["thread_id"]),
            "tokens": int(row["delta_tokens"]),
        } for row in rows]

    def token_sample_thread_count(
        self,
        *,
        project_id: str | None = None,
        thread_ids: set[str] | frozenset[str] | None = None,
        hours: int = 24,
    ) -> int:
        cutoff = int(time.time() * 1000) - max(1, min(24 * 30, int(hours))) * 60 * 60 * 1000
        conditions = ["bucket_ms >= ?"]
        args: list[Any] = [cutoff]
        if project_id:
            conditions.append("project_id = ?")
            args.append(project_id)
        if thread_ids is not None:
            safe_thread_ids = tuple(sorted(set(thread_ids)))
            if not safe_thread_ids:
                return 0
            placeholders = ",".join("?" for _ in safe_thread_ids)
            conditions.append(f"thread_id IN ({placeholders})")
            args.extend(safe_thread_ids)
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(DISTINCT thread_id) FROM token_samples WHERE " + " AND ".join(conditions),
                tuple(args),
            ).fetchone()
        return int(row[0])

    def latest_diagnostics(self) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM diagnostic_samples ORDER BY sampled_at_ms DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "sampled_at_ms": int(row["sampled_at_ms"]),
            "health_state": row["health_state"],
            "reasons": json.loads(row["reasons_json"]),
            "payload": json.loads(row["payload_json"]),
        }

    def diagnostics_history(self, *, limit: int = 120) -> list[dict[str, Any]]:
        limit = max(1, min(1000, int(limit)))
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM diagnostic_samples ORDER BY sampled_at_ms DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{
            "sampled_at_ms": int(row["sampled_at_ms"]),
            "health_state": row["health_state"],
            "reasons": json.loads(row["reasons_json"]),
            "payload": json.loads(row["payload_json"]),
        } for row in rows]

    def record_diagnostics(
        self,
        sample: dict[str, Any],
        *,
        now_ms: int,
        auto_enabled: bool,
        sustain_seconds: int = HEALTH_SUSTAIN_SECONDS,
        recovery_seconds: int = HEALTH_RECOVERY_SECONDS,
        cooldown_seconds: int = HEALTH_COOLDOWN_SECONDS,
    ) -> dict[str, Any]:
        assessment = assess_health(sample)
        reasons = assessment["reasons"]
        active_keys = {
            f"{reason['kind']}:{reason['scope']}:{reason['code']}": reason for reason in reasons
        }
        payload_json = json.dumps(sample, sort_keys=True, separators=(",", ":"))
        reasons_json = json.dumps(reasons, sort_keys=True, separators=(",", ":"))
        now_ms = int(now_ms)
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO diagnostic_samples(sampled_at_ms, health_state, reasons_json, payload_json) VALUES (?, ?, ?, ?)",
                (now_ms, assessment["state"], reasons_json, payload_json),
            )
            connection.execute(
                "DELETE FROM diagnostic_samples WHERE sampled_at_ms < ?",
                (now_ms - DIAGNOSTIC_RETENTION_DAYS * 24 * 60 * 60 * 1000,),
            )
            request_ids: list[str] = []
            for incident_key, reason in active_keys.items():
                row = connection.execute(
                    "SELECT * FROM health_incidents WHERE incident_key = ?", (incident_key,)
                ).fetchone()
                if row is None:
                    first_seen_ms = now_ms
                    state = "OBSERVING"
                    cooldown_until_ms = None
                    healthy_since_ms = None
                    request_id = None
                    connection.execute(
                        """
                        INSERT INTO health_incidents(
                            incident_key, kind, scope, severity, state, first_seen_ms,
                            last_seen_ms, healthy_since_ms, cooldown_until_ms, request_id, updated_at_ms
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (incident_key, reason["kind"], reason["scope"], reason["severity"], state,
                         first_seen_ms, now_ms, healthy_since_ms, cooldown_until_ms, request_id, now_ms),
                    )
                else:
                    first_seen_ms = int(row["first_seen_ms"])
                    state = str(row["state"])
                    cooldown_until_ms = row["cooldown_until_ms"]
                    healthy_since_ms = None
                    request_id = row["request_id"]
                    if state in {"RECOVERED", "COOLDOWN"}:
                        if cooldown_until_ms and now_ms < int(cooldown_until_ms):
                            state = "COOLDOWN"
                        else:
                            first_seen_ms = now_ms
                            state = "OBSERVING"
                            cooldown_until_ms = None
                            request_id = None
                    connection.execute(
                        """
                        UPDATE health_incidents SET kind=?, scope=?, severity=?, state=?,
                            first_seen_ms=?, last_seen_ms=?, healthy_since_ms=?, cooldown_until_ms=?,
                            request_id=?, updated_at_ms=? WHERE incident_key=?
                        """,
                        (reason["kind"], reason["scope"], reason["severity"], state, first_seen_ms,
                         now_ms, healthy_since_ms, cooldown_until_ms, request_id, now_ms, incident_key),
                    )
                sustained = now_ms - first_seen_ms >= max(1, int(sustain_seconds)) * 1000
                if state == "COOLDOWN":
                    continue
                if auto_enabled and sustained:
                    state = "OPEN"
                    connection.execute(
                        "UPDATE health_incidents SET state=?, updated_at_ms=? WHERE incident_key=?",
                        (state, now_ms, incident_key),
                    )
                    open_request = connection.execute(
                        """
                        SELECT request_id FROM health_requests
                        WHERE incident_key=? AND status IN ('OPEN', 'CLAIMED', 'IN_PROGRESS')
                        ORDER BY created_at_ms DESC LIMIT 1
                        """,
                        (incident_key,),
                    ).fetchone()
                    if open_request:
                        request_ids.append(str(open_request["request_id"]))
                    else:
                        request_id = f"health:{incident_key}:{first_seen_ms}"
                        request_payload = {
                            "incident_id": incident_key,
                            "request_id": request_id,
                            "request_type": reason["request_type"],
                            "severity": reason["severity"],
                            "scope": reason["scope"],
                            "evidence_digest": assessment["evidence_digest"],
                            "recommended_action": reason["recommendation"],
                            "constraints": reason["constraints"],
                            "expires_at_ms": now_ms + 24 * 60 * 60 * 1000,
                            "claim_limit": "Advisory only; active CTRL must use normal host task APIs.",
                        }
                        connection.execute(
                            """
                            INSERT INTO health_requests(
                                request_id, incident_key, dedupe_key, request_type, severity, scope,
                                evidence_digest, payload_json, status, created_at_ms
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
                            """,
                            (request_id, incident_key, incident_key, reason["request_type"], reason["severity"],
                             reason["scope"], assessment["evidence_digest"],
                             json.dumps(request_payload, sort_keys=True, separators=(",", ":")), now_ms),
                        )
                        connection.execute(
                            "UPDATE health_incidents SET request_id=?, cooldown_until_ms=?, updated_at_ms=? WHERE incident_key=?",
                            (request_id, now_ms + max(1, int(cooldown_seconds)) * 1000, now_ms, incident_key),
                        )
                        request_ids.append(request_id)

            current_keys = set(active_keys)
            incident_rows = connection.execute("SELECT * FROM health_incidents").fetchall()
            for row in incident_rows:
                incident_key = str(row["incident_key"])
                if incident_key in current_keys or row["state"] in {"RECOVERED", "COOLDOWN"}:
                    continue
                healthy_since_ms = row["healthy_since_ms"] or now_ms
                state = str(row["state"])
                if now_ms - int(healthy_since_ms) >= max(1, int(recovery_seconds)) * 1000:
                    state = "RECOVERED"
                    connection.execute(
                        """
                        UPDATE health_requests SET status='RECOVERED', resolved_at_ms=?, resolution_receipt=?
                        WHERE incident_key=? AND status IN ('OPEN', 'CLAIMED', 'IN_PROGRESS')
                        """,
                        (now_ms, "auto-health:healthy-window", incident_key),
                    )
                    cooldown_until_ms = now_ms + max(1, int(cooldown_seconds)) * 1000
                else:
                    state = "RECOVERING"
                    cooldown_until_ms = row["cooldown_until_ms"]
                connection.execute(
                    """
                    UPDATE health_incidents SET state=?, healthy_since_ms=?, cooldown_until_ms=?,
                        updated_at_ms=? WHERE incident_key=?
                    """,
                    (state, int(healthy_since_ms), cooldown_until_ms, now_ms, incident_key),
                )
            connection.execute(
                "DELETE FROM health_incidents WHERE updated_at_ms < ? AND state='RECOVERED'",
                (now_ms - HEALTH_INCIDENT_RETENTION_DAYS * 24 * 60 * 60 * 1000,),
            )
            connection.execute(
                "DELETE FROM health_requests WHERE created_at_ms < ? AND status IN ('RESOLVED', 'REJECTED', 'RECOVERED')",
                (now_ms - HEALTH_INCIDENT_RETENTION_DAYS * 24 * 60 * 60 * 1000,),
            )
            connection.commit()
        return {
            "sampled_at_ms": now_ms,
            "state": assessment["state"],
            "reasons": reasons,
            "evidence_digest": assessment["evidence_digest"],
            "request_ids": sorted(set(request_ids)),
            "auto_enabled": bool(auto_enabled),
        }

    def health_incidents(self, *, state: str | None = None) -> list[dict[str, Any]]:
        allowed = {"OBSERVING", "OPEN", "CLAIMED", "IN_PROGRESS", "RECOVERING", "COOLDOWN", "RECOVERED"}
        if state and state not in allowed:
            raise ConsoleError("invalid health incident state")
        query = "SELECT * FROM health_incidents"
        args: tuple[Any, ...] = ()
        if state:
            query += " WHERE state = ?"
            args = (state,)
        query += " ORDER BY updated_at_ms DESC"
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(query, args).fetchall()
        return [dict(row) for row in rows]

    def health_requests(self, *, status: str | None = None) -> list[dict[str, Any]]:
        allowed = {"OPEN", "CLAIMED", "IN_PROGRESS", "RESOLVED", "REJECTED", "RECOVERED"}
        if status and status not in allowed:
            raise ConsoleError("invalid health request status")
        query = "SELECT * FROM health_requests"
        args: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            args = (status,)
        query += " ORDER BY created_at_ms DESC"
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(query, args).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def claim_health_request(self, request_id: str, *, now_ms: int) -> dict[str, Any]:
        request_id = _safe_metadata_text(request_id, "request_id", maximum=512)
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute(
                "UPDATE health_requests SET status='CLAIMED', claimed_at_ms=? WHERE request_id=? AND status='OPEN'",
                (int(now_ms), request_id),
            )
            row = connection.execute("SELECT * FROM health_requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ConsoleError("health request not found")
            if cursor.rowcount != 1:
                raise ConsoleConflict(f"health request is already {row['status'].lower()}")
            connection.commit()
        return {**dict(row), "payload": json.loads(row["payload_json"])}

    def resolve_health_request(self, request_id: str, *, outcome: str, receipt: str, now_ms: int) -> dict[str, Any]:
        request_id = _safe_metadata_text(request_id, "request_id", maximum=512)
        outcome = _safe_metadata_text(outcome, "outcome", maximum=16).upper()
        if outcome not in {"RESOLVED", "REJECTED"}:
            raise ConsoleError("health request outcome must be RESOLVED or REJECTED")
        receipt = _safe_metadata_text(receipt or "console:manual-resolution", "receipt", maximum=512)
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute(
                "UPDATE health_requests SET status=?, resolved_at_ms=?, resolution_receipt=? WHERE request_id=? AND status IN ('OPEN', 'CLAIMED', 'IN_PROGRESS')",
                (outcome, int(now_ms), receipt, request_id),
            )
            row = connection.execute("SELECT * FROM health_requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ConsoleError("health request not found")
            if cursor.rowcount != 1:
                raise ConsoleConflict(f"health request is already {row['status'].lower()}")
            connection.commit()
        return {**dict(row), "payload": json.loads(row["payload_json"])}

    def get_ctrl_override(self, ctrl_id: str) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,)).fetchone()
        fields = {} if row is None else json.loads(row["fields_json"])
        return {
            "ctrl_id": ctrl_id,
            "revision": 0 if row is None else int(row["revision"]),
            "override": {key: value for key, value in fields.items() if key in CTRL_OVERRIDE_FIELDS},
        }

    def update_ctrl_override(self, ctrl_id: str, fields: dict[str, Any], *, expected_revision: int, now_ms: int) -> dict[str, Any]:
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise ConsoleError("expected_revision must be a nonnegative integer")
        if not fields or set(fields) - set(CTRL_OVERRIDE_FIELDS):
            raise ConsoleError("override fields must use the canonical model and reasoning keys")
        for key, value in fields.items():
            if not isinstance(value, CTRL_OVERRIDE_FIELDS[key]) or "\n" in value or len(value) > 128:
                raise ConsoleError(f"override {key} is invalid")
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,)).fetchone()
            current_revision = 0 if row is None else int(row["revision"])
            if current_revision != expected_revision:
                raise ConsoleConflict(f"CTRL override revision conflict; expected {expected_revision}, current {current_revision}")
            current_fields = {} if row is None else json.loads(row["fields_json"])
            current = {key: value for key, value in current_fields.items() if key in CTRL_OVERRIDE_FIELDS}
            current.update(fields)
            if AUTO_CTRL_OVERRIDE_KEY in current_fields:
                current[AUTO_CTRL_OVERRIDE_KEY] = current_fields[AUTO_CTRL_OVERRIDE_KEY]
            revision = current_revision + 1
            connection.execute(
                "INSERT INTO ctrl_overrides(ctrl_id, revision, fields_json, updated_at_ms) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(ctrl_id) DO UPDATE SET revision=excluded.revision, fields_json=excluded.fields_json, updated_at_ms=excluded.updated_at_ms",
                (ctrl_id, revision, json.dumps(current, sort_keys=True), now_ms),
            )
            connection.commit()
        return {"ctrl_id": ctrl_id, "revision": revision, "override": current}

    def reset_ctrl_override(self, ctrl_id: str, *, expected_revision: int) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT revision, fields_json FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,)).fetchone()
            current_revision = 0 if row is None else int(row["revision"])
            if expected_revision != current_revision:
                raise ConsoleConflict(f"CTRL override revision conflict; expected {expected_revision}, current {current_revision}")
            retained_fields = {} if row is None else json.loads(str(row["fields_json"]))
            if AUTO_CTRL_OVERRIDE_KEY in retained_fields:
                connection.execute(
                    "UPDATE ctrl_overrides SET revision = 0, fields_json = ? WHERE ctrl_id = ?",
                    (json.dumps({AUTO_CTRL_OVERRIDE_KEY: retained_fields[AUTO_CTRL_OVERRIDE_KEY]}, sort_keys=True), ctrl_id),
                )
            else:
                connection.execute("DELETE FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,))
            connection.commit()
        return {"ctrl_id": ctrl_id, "revision": 0, "override": {}, "reset": True}

    @staticmethod
    def _notification_seen_key(principal_id: str, ctrl_id: str, project_id: str) -> str:
        return f"{NOTIFICATION_SEEN_KEY_PREFIX}:{_auto_digest([principal_id, ctrl_id, project_id])}"

    @staticmethod
    def _notification_seen_state(
        row: sqlite3.Row | None, *, principal_id: str, ctrl_id: str, project_id: str,
    ) -> dict[str, Any]:
        scope_digest = _auto_digest([principal_id, ctrl_id, project_id])
        if row is None:
            return {"schema_version": 1, "receipts": []}
        try:
            state = json.loads(str(row["value"]))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ConsoleError("notification seen state is invalid") from error
        if (
            not isinstance(state, dict) or set(state) != {"schema_version", "receipts"}
            or state.get("schema_version") != 1 or not isinstance(state.get("receipts"), list)
        ):
            raise ConsoleError("notification seen state is invalid")
        identities: set[str] = set()
        for receipt in state["receipts"]:
            if not isinstance(receipt, dict) or set(receipt) != {
                "notification_id", "scope_digest", "source_event_id", "source_event_digest", "seen_at_ms",
            }:
                raise ConsoleError("notification seen receipt is invalid")
            notification_id, source_event_digest = receipt["notification_id"], receipt["source_event_digest"]
            if (
                receipt["scope_digest"] != scope_digest
                or not isinstance(notification_id, str) or not re.fullmatch(r"[0-9a-f]{64}", notification_id)
                or not isinstance(source_event_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", source_event_digest)
                or receipt["source_event_id"] != _auto_id(receipt["source_event_id"], "notification source event")
                or notification_id in identities
                or not isinstance(receipt["seen_at_ms"], int) or isinstance(receipt["seen_at_ms"], bool)
                or receipt["seen_at_ms"] < 1
            ):
                raise ConsoleError("notification seen receipt identity is invalid")
            identities.add(notification_id)
        return state

    @staticmethod
    def _current_notification_seen(
        receipts: list[dict[str, Any]], items: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        current = {receipt["notification_id"]: receipt for receipt in receipts if receipt["notification_id"] in items}
        if any(
            receipt["source_event_id"] != items[identity]["source_event_id"]
            or receipt["source_event_digest"] != items[identity]["source_event_digest"]
            for identity, receipt in current.items()
        ):
            raise ConsoleError("notification seen receipt conflicts with retained source evidence")
        return current

    def notification_seen(
        self, *, principal_id: str, ctrl_id: str, project_id: str, items: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        key = self._notification_seen_key(principal_id, ctrl_id, project_id)
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT value FROM store_metadata WHERE key = ?", (key,)).fetchone()
            state = self._notification_seen_state(
                row, principal_id=principal_id, ctrl_id=ctrl_id, project_id=project_id,
            )
        return list(self._current_notification_seen(state["receipts"], items).values())

    def mark_notifications_seen(
        self, *, principal_id: str, ctrl_id: str, project_id: str,
        items: dict[str, dict[str, Any]], notification_ids: list[str], now_ms: int,
    ) -> dict[str, Any]:
        key = self._notification_seen_key(principal_id, ctrl_id, project_id)
        scope_digest = key.rsplit(":", 1)[-1]
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT value FROM store_metadata WHERE key = ?", (key,)).fetchone()
            state = self._notification_seen_state(
                row, principal_id=principal_id, ctrl_id=ctrl_id, project_id=project_id,
            )
            receipts = self._current_notification_seen(state["receipts"], items)
            pruned = len(state["receipts"]) - len(receipts)
            unknown = [identity for identity in notification_ids if identity not in items]
            if unknown:
                connection.rollback()
                raise ConsoleError("notification id is not current in the requested CTRL/project scope")
            added = 0
            for identity in notification_ids:
                item = items[identity]
                retained = receipts.get(identity)
                if retained is not None:
                    continue
                receipts[identity] = {
                    "notification_id": identity, "scope_digest": scope_digest,
                    "source_event_id": item["source_event_id"],
                    "source_event_digest": item["source_event_digest"], "seen_at_ms": now_ms,
                }
                added += 1
            ordered = sorted(
                receipts.values(), key=lambda receipt: (receipt["seen_at_ms"], receipt["notification_id"]), reverse=True,
            )
            next_state = {**state, "receipts": ordered}
            if added or pruned:
                connection.execute(
                    "INSERT INTO store_metadata(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(next_state, ensure_ascii=True, sort_keys=True, separators=(",", ":"))),
                )
            connection.commit()
        return {"acknowledged": len(notification_ids), "newly_seen": added, "pruned": pruned}

    def clear_history(self) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            before = self.storage_stats()
            deleted = {}
            for table in (
                "token_samples", "token_cursors", "eta_forecasts", "task_progress_state",
                "task_progress_receipts", "task_progress_plans", "task_progress_pulse_files", "proof_media", "proof_event_receipts", "store_metadata",
                "diagnostic_samples", "health_incidents", "health_requests",
            ):
                deleted[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                connection.execute(f"DELETE FROM {table}")
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            after = self.storage_stats()
        return {"ok": True, "deleted": deleted, "bytes_before": before["bytes"], "bytes_after": after["bytes"]}

    def reset_overrides(self) -> int:
        with self._lock, closing(self._connect()) as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM ctrl_overrides").fetchone()[0])
            connection.execute("DELETE FROM ctrl_overrides")
            connection.commit()
        return count

    def storage_stats(self) -> dict[str, Any]:
        paths = [self.path, self.path.with_name(self.path.name + "-wal"), self.path.with_name(self.path.name + "-shm")]
        size = sum(path.stat().st_size for path in paths if path.exists())
        with self._lock, closing(self._connect()) as connection:
            counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "token_samples", "eta_forecasts", "task_progress_state", "task_progress_receipts", "task_progress_plans",
                    "task_progress_pulse_files", "proof_media", "proof_event_receipts", "ctrl_overrides",
                    "diagnostic_samples", "health_incidents", "health_requests",
                )
            }
        return {
            "path": str(self.path),
            "bytes": size,
            "retention_days": TOKEN_RETENTION_DAYS,
            "diagnostic_retention_days": DIAGNOSTIC_RETENTION_DAYS,
            "health_incident_retention_days": HEALTH_INCIDENT_RETENTION_DAYS,
            "counts": counts,
        }


class ConsoleConflict(ConsoleError):
    """Optimistic-concurrency conflict for a per-CTRL overlay."""


def state_database(codex_home: Path) -> Path:
    candidates = (codex_home / "state_5.sqlite", codex_home / "sqlite" / "state_5.sqlite")
    return next((path for path in candidates if path.exists()), candidates[0])


def goals_database(codex_home: Path) -> Path:
    return codex_home / "goals_1.sqlite"


def _readonly_connection(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise ConsoleError(f"Codex state database not found: {path}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 2000")
    return connection


def active_goal_thread_ids(codex_home: Path, *, observed_after_ms: int) -> set[str]:
    database = goals_database(codex_home)
    if not database.is_file():
        return set()
    try:
        with closing(_readonly_connection(database)) as connection:
            return {
                str(row["thread_id"])
                for row in connection.execute(
                    "SELECT thread_id FROM thread_goals WHERE status='active' AND updated_at_ms>=?",
                    (observed_after_ms,),
                ).fetchall()
            }
    except (sqlite3.Error, OSError, ConsoleError):
        return set()


def observed_task_project_id(codex_home: Path, task_id: str) -> str | None:
    """Resolve one exact unarchived task to its observed project without reading messages."""
    try:
        with closing(_readonly_connection(state_database(codex_home))) as connection:
            thread_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(threads)").fetchall()
            }
            project_id_projection = "project_id" if "project_id" in thread_columns else "'' AS project_id"
            projects, project_roots = _host_project_catalog(connection)
            seen: set[str] = set()
            current_id: str | None = task_id
            while current_id and current_id not in seen:
                seen.add(current_id)
                row = connection.execute(
                    f"SELECT cwd, {project_id_projection} FROM threads WHERE id=? AND archived=0",
                    (current_id,),
                ).fetchone()
                if row is None:
                    return None
                project, state = _canonical_project_binding(row, projects, project_roots)
                if project is not None:
                    return str(project["id"])
                if state in {"stale", "conflicted"}:
                    return None
                parent = connection.execute(
                    "SELECT parent_thread_id FROM thread_spawn_edges WHERE child_thread_id=?",
                    (current_id,),
                ).fetchone()
                current_id = str(parent["parent_thread_id"]) if parent is not None else None
    except (sqlite3.Error, OSError, ConsoleError):
        return None
    return None


def observation_fingerprint(codex_home: Path, config_path: Path) -> tuple[tuple[str, int, int], ...]:
    """Return only cheap local metadata needed to invalidate a console snapshot."""
    database = state_database(codex_home)
    goals = goals_database(codex_home)
    paths = (
        database,
        database.with_name(f"{database.name}-wal"),
        goals,
        goals.with_name(f"{goals.name}-wal"),
        config_path,
    )
    fingerprint: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            stat = path.stat()
            fingerprint.append((path.name, stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            fingerprint.append((path.name, 0, 0))
    return tuple(fingerprint)


def progress_pulse_fingerprint(codex_home: Path) -> tuple[tuple[str, int, int], ...]:
    """Return bounded metadata for the latest local progress sidecars."""
    expected_root = codex_home.resolve() / PULSE_ROOT
    try:
        pulse_root = expected_root.resolve(strict=True)
        if pulse_root != expected_root or not pulse_root.is_dir():
            return (("untrusted", 0, 0),)
        root_stat = pulse_root.stat()
    except (FileNotFoundError, OSError):
        return (("missing", 0, 0),)

    entries: list[tuple[str, int, int]] = []
    try:
        for index, path in enumerate(pulse_root.iterdir()):
            if index >= MAX_PULSE_FILES:
                entries.append(("limit-reached", MAX_PULSE_FILES, 0))
                break
            try:
                resolved = path.resolve(strict=True)
                stat = resolved.stat()
                if resolved.parent != pulse_root or not resolved.is_file():
                    entries.append((path.name, -1, -1))
                else:
                    entries.append((resolved.name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                entries.append((path.name, -1, -1))
    except OSError:
        return (("unavailable", 0, 0),)
    return ((pulse_root.name, root_stat.st_mtime_ns, root_stat.st_size), *sorted(entries))


def _epoch_ms(milliseconds: Any, seconds: Any) -> int:
    if milliseconds:
        return int(milliseconds)
    if not seconds:
        return 0
    value = int(seconds)
    return value if value > 10**12 else value * 1000


def _codex_jsonl_token_counts(codex_home: Path, thread_ids: set[str]) -> dict[str, int]:
    """Bound one shared sessions walk to requested threads; retain counts only."""
    sessions = codex_home / "sessions"
    requested = {thread_id for thread_id in thread_ids if thread_id}
    if not sessions.is_dir() or not requested:
        return {}
    highest: dict[str, int] = {}
    candidates: list[tuple[str, Path]] = []
    try:
        for visited, path in enumerate(sessions.rglob("*.jsonl"), start=1):
            if visited > TOKEN_JSONL_SCAN_FILE_LIMIT:
                break
            if not path.is_file():
                continue
            thread_id = next((item for item in requested if item in path.name), None)
            if thread_id is not None:
                candidates.append((thread_id, path))
    except OSError:
        return {}
    for thread_id, path in candidates:
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if '"token_count"' not in line or '"total_token_usage"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if record.get("type") != "event_msg":
                        continue
                    payload = record.get("payload")
                    if not isinstance(payload, dict) or payload.get("type") != "token_count":
                        continue
                    info = payload.get("info")
                    usage = info.get("total_token_usage") if isinstance(info, dict) else None
                    if not isinstance(usage, dict):
                        continue
                    total = usage.get("total_tokens")
                    if not isinstance(total, int) or total < 0:
                        input_tokens = usage.get("input_tokens")
                        output_tokens = usage.get("output_tokens")
                        input_tokens = input_tokens if isinstance(input_tokens, int) and input_tokens >= 0 else 0
                        output_tokens = output_tokens if isinstance(output_tokens, int) and output_tokens >= 0 else 0
                        total = input_tokens + output_tokens
                    highest[thread_id] = max(highest.get(thread_id, 0), total)
        except (OSError, UnicodeError):
            continue
    return highest


def _codex_jsonl_token_count(codex_home: Path, thread_id: str) -> int | None:
    """Compatibility wrapper for focused callers; observation uses the shared scan."""
    return _codex_jsonl_token_counts(codex_home, {thread_id}).get(thread_id)


def _normalized_project_path(value: Any) -> str:
    path = str(value or "").strip().replace("\\", "/")
    if path.casefold().startswith("//?/unc/"):
        path = f"//{path[8:]}"
    elif path.casefold().startswith("//?/"):
        path = path[4:]
    path = path.rstrip("/")
    prefix = "//" if path.startswith("//") else ""
    return f"{prefix}{re.sub(r'/+', '/', path[len(prefix):])}".casefold()


def _project_order_key(project: dict[str, Any]) -> tuple[Any, ...]:
    ordering = project.get("ordering") if isinstance(project.get("ordering"), dict) else {}
    position = ordering.get("position")
    created_at_ms = ordering.get("created_at_ms")
    return (
        0 if isinstance(position, int) and not isinstance(position, bool) else 1,
        position if isinstance(position, int) and not isinstance(position, bool) else 0,
        created_at_ms if isinstance(created_at_ms, int) and not isinstance(created_at_ms, bool) else 0,
        str(project.get("name") or "").casefold(),
        str(project.get("id") or ""),
    )


def _host_project_catalog(
    connection: sqlite3.Connection,
) -> tuple[dict[str, dict[str, Any]], tuple[tuple[str, str], ...]]:
    """Read canonical host projects without inventing identity from task metadata."""
    tables = {
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "projects" not in tables:
        return {}, ()
    project_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(projects)").fetchall()
    }
    ordering_columns = tuple(
        column for column in ("position", "created_at_ms", "updated_at_ms") if column in project_columns
    )
    selected_columns = ", ".join(("id", "name", *ordering_columns))
    projects: dict[str, dict[str, Any]] = {}
    for row in connection.execute(f"SELECT {selected_columns} FROM projects").fetchall():
        project_id = str(row["id"] or "").strip()
        name = str(row["name"] or "").strip()
        if not project_id or not name:
            continue
        ordering = {
            column: row[column]
            if column in ordering_columns
            and isinstance(row[column], int) and not isinstance(row[column], bool)
            else None
            for column in ("position", "created_at_ms", "updated_at_ms")
        }
        projects[project_id] = {
            "id": project_id,
            "name": name,
            "ordering": ordering,
        }
    if "project_roots" not in tables:
        return projects, ()
    roots = tuple(
        sorted(
            (
                (_normalized_project_path(row["path"]), str(row["project_id"]))
                for row in connection.execute("SELECT project_id, path FROM project_roots").fetchall()
                if str(row["project_id"] or "") in projects and _normalized_project_path(row["path"])
            ),
            key=lambda item: (-len(item[0]), item[0], item[1]),
        )
    )
    return projects, roots


def _canonical_project_binding(
    row: sqlite3.Row,
    projects: dict[str, dict[str, Any]],
    project_roots: tuple[tuple[str, str], ...],
) -> tuple[dict[str, Any] | None, str]:
    project_id = str(row["project_id"] or "").strip()
    if project_id:
        return (projects.get(project_id), "direct" if project_id in projects else "stale")
    cwd = _normalized_project_path(row["cwd"])
    matches = [
        (root, bound_project_id)
        for root, bound_project_id in project_roots
        if cwd == root or cwd.startswith(f"{root}/")
    ]
    if not matches:
        return None, "unbound"
    longest = len(matches[0][0])
    project_ids = {project_id for root, project_id in matches if len(root) == longest}
    if len(project_ids) != 1:
        return None, "conflicted"
    return projects[next(iter(project_ids))], "root"


def _thread_project_bindings(
    rows: dict[str, sqlite3.Row],
    parent_by_child: dict[str, str],
    projects: dict[str, dict[str, Any]],
    project_roots: tuple[tuple[str, str], ...],
) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    blocked: set[str] = set()
    for thread_id, row in rows.items():
        project, state = _canonical_project_binding(row, projects, project_roots)
        if project is not None:
            bindings[thread_id] = project
        elif state in {"stale", "conflicted"}:
            blocked.add(thread_id)
    for thread_id in rows:
        if thread_id in bindings or thread_id in blocked:
            continue
        seen = {thread_id}
        parent = parent_by_child.get(thread_id)
        while parent and parent not in seen:
            seen.add(parent)
            if parent in blocked:
                break
            if parent in bindings:
                bindings[thread_id] = bindings[parent]
                break
            parent = parent_by_child.get(parent)
    return bindings


HOST_CTRL_CLASSIFICATION_SOURCES = frozenset({
    "host_threads.agent_role",
    "host_thread_spawn_edges.subagent",
})


def _controller_classification(
    row: sqlite3.Row,
    *,
    structural_host_ctrl: bool = False,
) -> dict[str, str | None]:
    """Classify CTRL from persisted role or fresh project-bound host spawn evidence."""
    if str(row["agent_role"] or "").strip().casefold() == "ctrl":
        return {
            "controller_classification": "swarm_ctrl",
            "controller_classification_source": "host_threads.agent_role",
        }
    if structural_host_ctrl:
        return {
            "controller_classification": "swarm_ctrl",
            "controller_classification_source": "host_thread_spawn_edges.subagent",
        }
    return {
        "controller_classification": "unavailable",
        "controller_classification_source": None,
    }


def _is_host_confirmed_ctrl(controller: dict[str, Any]) -> bool:
    return (
        controller.get("controller_classification") == "swarm_ctrl"
        and controller.get("controller_classification_source") in HOST_CTRL_CLASSIFICATION_SOURCES
    )


def _role_from_title(
    title: str,
    labels: dict[str, str],
    role_icons: dict[str, Any],
    professions: dict[str, Any] | None = None,
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
        else:
            upper = role_label.upper()
            profession_override=next((value for name,value in (professions or {}).items() if name.casefold()==role_label.casefold() and isinstance(value,dict)),{})
            preferred = str(profession_override.get("icon","")) or next(
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
    project_name: str = "",
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
    artifact = " ".join(path_tokens) or "Assigned task"
    artifact = re.sub(r"(?i)\bgate\s*(\d+)\b", r"Gate \1", artifact).strip().title()[:48]
    if controller:
        artifact = project_name or "Unbound work"
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
    active_goal_ids = active_goal_thread_ids(codex_home, observed_after_ms=observed_after_ms)
    with closing(_readonly_connection(database)) as connection:
        host_tables = {
            str(row["name"])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        project_inventory_available = "projects" in host_tables
        thread_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(threads)").fetchall()
        }
        agent_path_projection = "agent_path" if "agent_path" in thread_columns else "'' AS agent_path"
        project_id_projection = "project_id" if "project_id" in thread_columns else "'' AS project_id"
        host_project_catalog, project_roots = _host_project_catalog(connection)
        goal_placeholders = ",".join("?" for _ in active_goal_ids)
        goal_clause = f" OR id IN ({goal_placeholders})" if active_goal_ids else ""
        rows = connection.execute(
            f"""
            SELECT id, title, cwd, created_at, updated_at, created_at_ms, updated_at_ms,
                   model, reasoning_effort, tokens_used, archived, git_origin_url,
                   git_branch, thread_source, agent_nickname, agent_role, is_pinned,
                   {agent_path_projection}, {project_id_projection}
            FROM threads
            WHERE (
                updated_at_ms >= ?
                OR (updated_at_ms IS NULL AND updated_at >= ?)
                {goal_clause}
              )
            """,
            (observed_after_ms, observed_after_ms // 1000, *sorted(active_goal_ids)),
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
                row["title"], labels, config["role_icons"], config["professions"]
            )
        )
    }
    parent_by_child = {edge["child_thread_id"]: edge["parent_thread_id"] for edge in edge_rows}
    edge_status = {edge["child_thread_id"]: edge["status"] for edge in edge_rows}
    raw_children: dict[str, list[str]] = {}
    for edge in edge_rows:
        raw_children.setdefault(edge["parent_thread_id"], []).append(edge["child_thread_id"])
    project_bindings = _thread_project_bindings(
        all_rows, parent_by_child, host_project_catalog, project_roots
    )
    host_projects: dict[str, dict[str, Any]] = {
        project_id: {
            "id": project_id,
            "name": project["name"],
            "goal_label": project["name"],
            "label_source": "host_projects.name",
            "ordering": dict(project.get("ordering") or {}),
            "observed_threads": 0,
            "active_threads": 0,
            "updated_at": 0,
        }
        for project_id, project in host_project_catalog.items()
    }
    for thread_id, project in project_bindings.items():
        row = all_rows[thread_id]
        inventory = host_projects[project["id"]]
        inventory["observed_threads"] += 1
        inventory["active_threads"] += _status(row, edge_status.get(thread_id), heartbeat, now_ms) == "active"
        inventory["updated_at"] = max(
            inventory["updated_at"], _epoch_ms(row["updated_at_ms"], row["updated_at"])
        )
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
    structural_controller_ids = {
        parent
        for parent, child_ids in raw_children.items()
        if parent in fresh_ids
        and parent not in parent_by_child
        and not bool(all_rows[parent]["archived"])
        and parent in project_bindings
        and any(
            child in fresh_ids
            and edge_status.get(child) == "open"
            and not bool(all_rows[child]["archived"])
            and str(all_rows[child]["thread_source"] or "").strip().casefold()
            in {"subagent", "internal_subagent"}
            and project_bindings.get(child, {}).get("id") == project_bindings[parent]["id"]
            for child in child_ids
            if child in all_rows
        )
    }
    root_candidate_ids = {
        parent
        for parent, child_ids in raw_children.items()
        if parent in all_rows
        and parent not in parent_by_child
        and (parent not in parsed_titles or parsed_titles[parent]["role"] == "ctrl")
        and any(
            child in fresh_ids
            for child in child_ids
            if child in all_rows
        )
    }
    recent_parsed_ids = recent_ids.intersection(parsed_titles)
    controller_seed_ids = {
        thread_id
        for thread_id in recent_parsed_ids
        if parsed_titles[thread_id]["role"] == "ctrl"
    }.union(root_candidate_ids.intersection(recent_ids)).union(active_goal_ids.intersection(all_rows))
    descendant_ids: set[str] = set()
    traversed_ids: set[str] = set(controller_seed_ids)
    queue = list(controller_seed_ids)
    while queue:
        parent = queue.pop()
        for child in raw_children.get(parent, []):
            if child in traversed_ids:
                continue
            traversed_ids.add(child)
            if child in recent_ids and (
                child in parsed_titles or child in fresh_ids
            ):
                descendant_ids.add(child)
            queue.append(child)
    # A formatted title is classification evidence, not a spawn receipt. Admit
    # controllers and tasks reached through their observed host spawn tree, plus
    # fresh, safely classified standalone tasks without a fabricated parent.
    standalone_task_ids = {
        thread_id
        for thread_id in fresh_ids
        if thread_id in parsed_titles
        and thread_id not in parent_by_child
        and parsed_titles[thread_id]["role"] in {"doer", "lead", "review", "architect"}
    }
    included_ids = controller_seed_ids.union(descendant_ids).union(standalone_task_ids)
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
    connected_ids = set(controller_seed_ids.intersection(included_ids)).union(standalone_task_ids)
    queue = list(connected_ids)
    while queue:
        parent = queue.pop()
        for child in raw_children.get(parent, []):
            if child in included_ids and child not in connected_ids:
                connected_ids.add(child)
                queue.append(child)
    included_ids.intersection_update(connected_ids)
    parsed: dict[str, dict[str, str]] = {}
    for thread_id in included_ids:
        observed_role = parsed_titles.get(thread_id)
        if thread_id in controller_seed_ids and (
            observed_role is None or observed_role["role"] != "ctrl"
        ):
            project = project_bindings.get(thread_id)
            observed_role = _generic_agent_role(
                all_rows[thread_id], config["role_icons"], controller=True,
                project_name=project["name"] if project is not None else "",
            )
        parsed[thread_id] = observed_role or _generic_agent_role(
            all_rows[thread_id], config["role_icons"], controller=False
        )

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
        project_binding = project_bindings.get(thread_id)
        project_key = project_binding["id"] if project_binding is not None else ""
        project_name = project_binding["name"] if project_binding is not None else ""
        created_ms = _epoch_ms(row["created_at_ms"], row["created_at"])
        updated_ms = _epoch_ms(row["updated_at_ms"], row["updated_at"])
        project = None
        if project_binding is not None:
            project = projects.setdefault(
                project_key,
                {
                    "id": project_key,
                    "name": project_name,
                    "goal_label": project_name,
                    "label_source": "host_projects.name",
                    "ordering": dict(project_binding.get("ordering") or {}),
                    "nodes": 0,
                    "tokens": 0,
                    "active": 0,
                },
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
            "archived": bool(row["archived"]),
            "surface": str(row["thread_source"] or "task").strip().casefold() or "task",
            "is_subagent": str(row["thread_source"] or "").strip().casefold() in {"subagent", "internal_subagent"},
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
        if project is not None:
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
        if node["role"] == "ctrl" or thread_id in standalone_task_ids:
            continue
        unattached_task_ids.append(thread_id)

    for thread_id in unattached_task_ids:
        node = nodes.pop(thread_id)
        if node["project_id"]:
            project = projects[node["project_id"]]
            project["nodes"] -= 1
            project["tokens"] -= node["tokens"]
            project["active"] -= node["status"] == "active"

    for thread_id, node in nodes.items():
        parent = parent_by_child.get(thread_id)
        node["parent_id"] = parent if parent in nodes else None

    for project_key, inventory in host_projects.items():
        project = projects.setdefault(
            project_key,
            {
                "id": inventory["id"],
                "name": inventory["name"],
                "goal_label": inventory["goal_label"],
                "label_source": inventory["label_source"],
                "ordering": dict(inventory.get("ordering") or {}),
                "nodes": 0,
                "tokens": 0,
                "active": 0,
            },
        )
        project["observed_threads"] = inventory["observed_threads"]
        project["active_threads"] = inventory["active_threads"]
        project["updated_at"] = inventory["updated_at"]

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
                "archived": bool(controller.get("archived", False)),
                "archive_source": "host_threads.archived",
                **_controller_classification(
                    all_rows[controller_id],
                    structural_host_ctrl=controller_id in structural_controller_ids,
                ),
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
        "project_inventory": {
            "state": "KNOWN" if project_inventory_available else "UNKNOWN",
            "available": project_inventory_available,
            "source": "host_projects",
            "claim_limit": (
                "Saved project identity is available only when the canonical host projects table is present; "
                "absence is unavailable, not an empty project inventory."
            ),
        },
        "nodes": sorted(nodes.values(), key=lambda node: (node["project"], node["created_at"] or 0)),
        "links": links,
        "roots": roots,
        "controllers": sorted(controllers, key=lambda item: (-item["updated_at"], -item["nodes"], item["artifact"])),
        "projects": sorted(projects.values(), key=_project_order_key),
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
            "Subagent grouping uses host thread-source metadata plus observed spawn edges; it is a display relationship, not an authoritative runtime workflow graph.",
            "Spawn edges are shown as delegated relationships; waits-for and review dependencies are not inferred without runtime receipts.",
            "Controller scopes are observed host descendants, not the authoritative runtime workflow graph.",
            "Proof plans appear only from validated runtime snapshots; absent snapshots stay unavailable and never inherit host task status.",
            "Host task observation includes recently updated archived rows so authoritative navigation visibility can preserve archive state.",
            "Recent active durable goals are read by thread ID only to identify CTRL scopes; objective text is never read or surfaced.",
            "Project navigation includes only canonical host project records and their exact root or thread bindings; task titles, repository labels, cwd leaves, worktree names, and lane labels never create projects.",
            "Unbound tasks remain visible in all-task and hierarchy views without acquiring a project scope.",
            "Unformatted delegated lanes use the existing active-freshness boundary; older lanes are counted, not expanded.",
            "Older descendant lanes are omitted from the graph and counted on their CTRL scope.",
            "Visible-tab refreshes reuse the local snapshot until the host database, its WAL, or config changes.",
            f"Visible overview refreshes and a lightweight hidden-tab ping preserve portal presence; a closed tab expires after {PORTAL_PRESENCE_TTL_SECONDS} seconds.",
            "Active means recently updated within two heartbeat windows, not guaranteed CPU work.",
            "Tokens are local cumulative thread tokens, not billing or remaining quota.",
            "Usage history prefers local Codex JSONL token_count totals and falls back to the SQLite threads.tokens_used high-water aggregate; prompts, responses, tools, and credentials are not retained.",
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
    def __init__(
        self, codex_home: Path, config_path: Path, state_path: Path | None = None,
        *, auto_bridge: Any | None = None, project_view_resolver: Any | None = None,
    ):
        self.codex_home = codex_home.resolve()
        self.config_path = config_path.resolve()
        self.store = ConsoleStore(state_path or console_state_path(self.codex_home, self.config_path))
        self.progress_ledger = ProgressLedger(self.codex_home)
        self.auto_bridge = auto_bridge or CodexStdioBridge()
        self.project_view_resolver = project_view_resolver or self._default_project_view_resolver
        self.builtin_role_manifests = load_builtin_role_manifests(
            SWARM_SKILL_ROOT / "roles", STATIC_ROOT / "swarm-offline-disconnected.png"
        )
        self.diagnostics_collector = DiagnosticsCollector(self.codex_home, self.store.path)
        self.token = secrets.token_urlsafe(24)
        self.write_lock = threading.Lock()
        self.overview_lock = threading.RLock()
        self.overview_refresh_lock = threading.Lock()
        self.progress_pulse_lock = threading.Lock()
        self.presence_lock = threading.Lock()
        self.proof_lock = threading.Lock()
        self._overview_fingerprint: tuple[tuple[str, int, int], ...] | None = None
        self._overview: dict[str, Any] | None = None
        self._view: dict[str, Any] | None = None
        self._overview_revision = 0
        self._view_fingerprint: int | None = None
        self._view_store_generation = -1
        self._store_generation = 0
        self._last_presence_at: float | None = None
        self._last_open_claim_at: float | None = None
        self._last_observed_fingerprint: tuple[tuple[str, int, int], ...] | None = None
        self._progress_pulse_fingerprint: tuple[tuple[str, int, int], ...] | None = None
        self._project_view_cache: dict[str, dict[str, Any]] = {}
        self._observer_stop = threading.Event()
        self._observer_thread: threading.Thread | None = None

    def _auto_project_root(self, project_id: str) -> Path:
        return self._canonical_project_root(project_id, "Auto")

    def _canonical_project_root(self, project_id: str, purpose: str = "Project view") -> Path:
        database = state_database(self.codex_home)
        with closing(sqlite3.connect(database)) as connection:
            row = connection.execute(
                "SELECT path FROM project_roots WHERE project_id = ? ORDER BY position LIMIT 1",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ConsoleError(f"{purpose} requires a canonical host project root")
        root = Path(str(row[0]))
        if not root.is_absolute():
            raise ConsoleError(f"{purpose} project root must be an absolute host path")
        return root

    @staticmethod
    def _project_view_digest(value: Any) -> str:
        digest = str(value or "").strip().casefold()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ConsoleError("project view digest must be an exact sha256 reference")
        return digest

    @staticmethod
    def _project_view_text(value: Any, label: str, maximum: int = 128) -> str:
        text = str(value or "").strip()
        if not text or len(text.encode("utf-8")) > maximum or any(ord(character) < 32 for character in text):
            raise ConsoleError(f"project view {label} is invalid")
        return text

    @classmethod
    def _project_view_ref(cls, value: Any) -> str:
        ref = cls._project_view_text(value, "source reference", 512)
        if not re.fullmatch(r"project://[A-Za-z0-9._~:/-]+", ref):
            raise ConsoleError("project view source reference must be opaque project data")
        return ref

    @staticmethod
    def _root_project_view_link(root: Path) -> tuple[str, dict[str, str] | None]:
        path = root / "SWARM.md"
        try:
            if not path.is_file() or path.stat().st_size > PROJECT_VIEW_MAX_BYTES:
                return "absent", None
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return "invalid", None
        documents: list[Any] = []
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                documents.append(json.loads(stripped))
            except json.JSONDecodeError:
                return "invalid", None
        for block in re.findall(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE):
            try:
                documents.append(json.loads(block))
            except json.JSONDecodeError:
                return "invalid", None
        link_items: list[Any] = []
        for document in documents:
            if isinstance(document, dict) and isinstance(document.get("links"), list):
                candidates = [
                    item for item in document["links"]
                    if isinstance(item, dict) and str(item.get("rel") or "").strip() == "project_views"
                ]
                if candidates and document.get("schema_version") != 1:
                    return "invalid", None
                link_items.extend(candidates)
        if not link_items:
            return "absent", None
        if len(link_items) != 1:
            return "invalid", None
        item = link_items[0]
        if set(item) != {"rel", "ref", "digest"}:
            return "invalid", None
        try:
            return "present", {
                "ref": App._project_view_ref(item.get("ref")),
                "digest": App._project_view_digest(item.get("digest")),
            }
        except ConsoleError:
            return "invalid", None

    def _resolve_project_view_bytes(self, project_id: str, ref: str, digest: str) -> bytes:
        if self.project_view_resolver is None:
            raise ConsoleError("project view source resolver is unavailable")
        resolved = self.project_view_resolver(project_id, ref, digest)
        if isinstance(resolved, str):
            resolved = resolved.encode("utf-8")
        if not isinstance(resolved, bytes) or not resolved or len(resolved) > PROJECT_VIEW_MAX_BYTES:
            raise ConsoleError("project view source is unavailable or exceeds the delivery guard")
        if "sha256:" + hashlib.sha256(resolved).hexdigest() != digest:
            raise ConsoleError("project view source digest does not match")
        return resolved

    def _default_project_view_resolver(self, project_id: str, ref: str, digest: str) -> bytes:
        parsed = urlparse(ref)
        expected_project = project_id[8:] if project_id.casefold().startswith("project:") else project_id
        try:
            has_port = parsed.port is not None
        except ValueError as exc:
            raise ConsoleError("project view source reference belongs to another project") from exc
        if (
            parsed.scheme != "project" or parsed.netloc != expected_project or parsed.params
            or parsed.query or parsed.fragment or parsed.username or parsed.password or has_port
        ):
            raise ConsoleError("project view source reference belongs to another project")
        decoded = unquote(parsed.path)
        parts = [part for part in decoded.split("/") if part]
        if (
            not parts or parsed.path != "/" + "/".join(parts)
            or any(part in {".", ".."} or "\\" in part or ":" in part for part in parts)
        ):
            raise ConsoleError("project view source reference contains traversal")
        root_path = self._canonical_project_root(project_id)
        try:
            root_metadata = root_path.lstat()
            root_attributes = getattr(root_metadata, "st_file_attributes", 0)
            if root_path.is_symlink() or root_attributes & getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise ConsoleError("project view source cannot traverse a reparse point")
            root = root_path.resolve(strict=True)
            target = root.joinpath(*parts)
            resolved = target.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ConsoleError("project view source resolves outside the canonical project root")
            relative = resolved.relative_to(root)
            current = root
            for part in relative.parts:
                current = current / part
                metadata = current.lstat()
                attributes = getattr(metadata, "st_file_attributes", 0)
                if current.is_symlink() or attributes & getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    raise ConsoleError("project view source cannot traverse a reparse point")
            raw = self._read_project_view_handle(root, resolved)
        except ConsoleError:
            raise
        except OSError as exc:
            raise ConsoleError("project view source is unavailable") from exc
        if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
            raise ConsoleError("project view source digest does not match")
        return raw

    @staticmethod
    def _read_project_view_handle(root: Path, path: Path) -> bytes:
        if os.name != "nt":
            raise ConsoleError("secure project view source reads are unavailable on this host")
        import ctypes
        import msvcrt
        from ctypes import wintypes

        class FileInformation(ctypes.Structure):
            _fields_ = [
                ("attributes", wintypes.DWORD), ("creation_time", wintypes.FILETIME),
                ("last_access_time", wintypes.FILETIME), ("last_write_time", wintypes.FILETIME),
                ("volume_serial", wintypes.DWORD), ("size_high", wintypes.DWORD),
                ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                ("file_index_high", wintypes.DWORD), ("file_index_low", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        create_file.restype = wintypes.HANDLE
        get_information = kernel32.GetFileInformationByHandle
        get_information.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInformation)]
        get_information.restype = wintypes.BOOL
        get_final_path = kernel32.GetFinalPathNameByHandleW
        get_final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        get_final_path.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        handle = create_file(
            str(path), 0x80000000, 0x00000001, None, 3,
            0x00200000 | 0x08000000, None,
        )
        invalid_handle = wintypes.HANDLE(-1).value
        if handle == invalid_handle:
            raise ConsoleError("project view source is unavailable")
        descriptor: int | None = None
        try:
            information = FileInformation()
            if not get_information(handle, ctypes.byref(information)):
                raise ConsoleError("project view source identity is unavailable")
            if information.attributes & (0x00000010 | 0x00000400):
                raise ConsoleError("project view source cannot be a directory or reparse point")
            size = (int(information.size_high) << 32) | int(information.size_low)
            if size <= 0 or size > PROJECT_VIEW_MAX_BYTES:
                raise ConsoleError("project view source is unavailable or exceeds the delivery guard")
            buffer = ctypes.create_unicode_buffer(32768)
            length = get_final_path(handle, buffer, len(buffer), 0)
            if not length or length >= len(buffer):
                raise ConsoleError("project view source identity is unavailable")
            final_path = buffer.value
            if final_path.startswith("\\\\?\\UNC\\"):
                final_path = "\\\\" + final_path[8:]
            elif final_path.startswith("\\\\?\\"):
                final_path = final_path[4:]
            root_name = os.path.normcase(os.path.abspath(str(root)))
            final_name = os.path.normcase(os.path.abspath(final_path))
            try:
                if os.path.commonpath((root_name, final_name)) != root_name:
                    raise ConsoleError("project view source resolves outside the canonical project root")
            except ValueError as exc:
                raise ConsoleError("project view source resolves outside the canonical project root") from exc
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            handle = invalid_handle
            chunks = []
            remaining = size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    raise ConsoleError("project view source changed while it was retained")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ConsoleError("project view source changed while it was retained")
            return b"".join(chunks)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            elif handle != invalid_handle:
                close_handle(handle)

    @classmethod
    def _project_view_sources(cls, view: dict[str, Any], default_kind: str) -> list[dict[str, str]]:
        sources = view.get("sources")
        if isinstance(sources, list):
            normalized = []
            for source in sources:
                if not isinstance(source, dict) or set(source) != {"kind", "ref", "digest"}:
                    raise ConsoleError("project view sources must use the exact typed source contract")
                normalized.append({
                    "kind": cls._project_view_text(source.get("kind"), "source kind", 64),
                    "ref": cls._project_view_ref(source.get("ref")),
                    "digest": cls._project_view_digest(source.get("digest")),
                })
        else:
            refs = view.get("source_refs")
            digests = view.get("source_digests")
            if not isinstance(refs, list) or not isinstance(digests, list) or len(refs) != len(digests):
                raise ConsoleError("project view source references and digests must align")
            normalized = [
                {"kind": default_kind, "ref": cls._project_view_ref(ref), "digest": cls._project_view_digest(digest)}
                for ref, digest in zip(refs, digests, strict=True)
            ]
        if not normalized or len(normalized) > 16:
            raise ConsoleError("project view must have one to sixteen sources")
        return normalized

    @classmethod
    def _project_view_definition(
        cls, view: Any, *, expected_id: str, renderer: str, mode: str, source_kind: str,
    ) -> dict[str, Any]:
        if not isinstance(view, dict):
            raise ConsoleError("project view definition must be an object")
        view_id = cls._project_view_text(view.get("id"), "id")
        label = cls._project_view_text(view.get("label"), "label", 256)
        actual_renderer = cls._project_view_text(view.get("renderer"), "renderer", 32)
        actual_mode = cls._project_view_text(view.get("mode"), "mode", 32)
        if actual_renderer not in PROJECT_VIEW_RENDERERS:
            raise ConsoleError("project view renderer is not registered")
        if actual_mode not in PROJECT_VIEW_RENDERERS[actual_renderer]:
            raise ConsoleError("project view mode is not registered")
        if (view_id, label, actual_renderer, actual_mode) != (expected_id, "Screens" if renderer == "gallery" else "Map", renderer, mode):
            raise ConsoleError("project UI view does not match the bounded Screens and Map contract")
        actions = view.get("allowed_actions", [])
        if not isinstance(actions, list) or len(actions) > 16 or any(action not in PROJECT_VIEW_ACTIONS for action in actions):
            raise ConsoleError("project view action is not registered")
        return {
            "id": view_id,
            "label": label,
            "renderer": actual_renderer,
            "mode": actual_mode,
            "sources": cls._project_view_sources(view, source_kind),
            "allowed_actions": list(dict.fromkeys(actions)),
        }

    @staticmethod
    def _project_view_json(raw: bytes, label: str) -> dict[str, Any]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ConsoleError(f"project view {label} source must be bounded JSON") from exc
        if not isinstance(value, dict):
            raise ConsoleError(f"project view {label} source must be an object")
        return value

    def _project_view_screens(self, project_id: str, raw: bytes) -> list[dict[str, Any]]:
        source = self._project_view_json(raw, "Screens")
        if source.get("project_id") not in {None, project_id}:
            raise ConsoleError("project view Screens source belongs to another project")
        nodes = source.get("nodes")
        if not isinstance(nodes, list) or len(nodes) > 256:
            raise ConsoleError("project view Screens source must contain bounded nodes")
        proof = {
            (str(item.get("evidence_id") or ""), str(item.get("digest") or "").casefold()): item
            for item in self.store.proof_feed(project_id=project_id)
            if str(item.get("media_type") or "").startswith("image/")
        }
        screens: list[dict[str, Any]] = []
        identities: set[str] = set()
        for node in nodes:
            if not isinstance(node, dict) or node.get("node_kind") != "screen_state":
                continue
            screen_id = self._project_view_text(node.get("screen_id"), "screen id")
            state_id = self._project_view_text(node.get("state_id"), "state id")
            identity = f"{screen_id}/{state_id}"
            if identity in identities:
                raise ConsoleError("project view screen identities must be unique")
            identities.add(identity)
            evidence: list[dict[str, Any]] = []
            evidence_seen: set[tuple[str, str]] = set()
            candidates = []
            for field in ("design_alternatives", "implementation_evidence"):
                values = node.get(field, [])
                if not isinstance(values, list) or len(values) > 64:
                    raise ConsoleError("project view evidence bindings must be bounded lists")
                candidates.extend(values)
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    raise ConsoleError("project view evidence binding must be an object")
                artifact_id = self._project_view_text(candidate.get("artifact_id"), "artifact id", 256)
                evidence_id = self._project_view_text(candidate.get("evidence_id") or artifact_id, "evidence id", 256)
                digest = self._project_view_digest(candidate.get("digest"))[7:]
                registered = proof.get((evidence_id, digest))
                if registered is None:
                    raise ConsoleError("project view evidence binding is not retained at its exact digest")
                key = (evidence_id, digest)
                if key in evidence_seen:
                    continue
                evidence_seen.add(key)
                device = str(candidate.get("device") or "").strip().casefold()
                if device and device not in {"desktop", "tablet", "mobile"}:
                    raise ConsoleError("project view evidence device is unsupported")
                evidence.append({
                    **registered,
                    "artifact_id": artifact_id,
                    "alternative_id": str(candidate.get("alternative_id") or "").strip() or None,
                    "label": str(candidate.get("label") or registered.get("caption") or "Artifact")[:256],
                    "device": device if device in {"desktop", "tablet", "mobile"} else None,
                })
            screens.append({
                "id": identity,
                "screen_id": screen_id,
                "state_id": state_id,
                "label": self._project_view_text(node.get("label") or identity, "screen label", 256),
                "status": self._project_view_text(node.get("coverage_state") or "UNKNOWN", "coverage state", 64),
                "evidence": evidence,
                "devices": [device for device in ("desktop", "tablet", "mobile") if any(item["device"] == device for item in evidence)],
                "alternative_count": len({item["alternative_id"] for item in evidence if item["alternative_id"]}),
            })
        return screens

    @classmethod
    def _project_view_graph(cls, raw: bytes, screens: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ConsoleError("project view Map source must be UTF-8") from exc
        lowered = text.casefold()
        if any(token in lowered for token in ("javascript:", "data:", "vbscript:", "file:", "blob:", "click ", "href ", "<script")):
            raise ConsoleError("project view Map source contains executable links")
        nodes: dict[str, str] = {}
        edges: list[dict[str, str]] = []
        try:
            graph = json.loads(text)
        except json.JSONDecodeError:
            graph = None
        if isinstance(graph, dict):
            graph_nodes = graph.get("nodes")
            graph_edges = graph.get("edges")
            if not isinstance(graph_nodes, list) or not isinstance(graph_edges, list) or len(graph_nodes) > 256 or len(graph_edges) > 512:
                raise ConsoleError("project view Map JSON is invalid")
            for node in graph_nodes:
                if not isinstance(node, dict):
                    raise ConsoleError("project view Map node is invalid")
                node_id = cls._project_view_text(node.get("id"), "Map node id")
                nodes[node_id] = cls._project_view_text(node.get("label") or node_id, "Map node label", 256)
            for edge in graph_edges:
                if not isinstance(edge, dict):
                    raise ConsoleError("project view Map edge is invalid")
                source = cls._project_view_text(edge.get("source"), "Map edge source")
                target = cls._project_view_text(edge.get("target"), "Map edge target")
                if source not in nodes or target not in nodes:
                    raise ConsoleError("project view Map edge names an unknown node")
                edges.append({"source": source, "target": target})
        else:
            header_pattern = re.compile(r"(?:flowchart|graph)\s+(?:TB|TD|BT|RL|LR)", re.IGNORECASE)
            node_pattern = re.compile(r"([A-Za-z][A-Za-z0-9_.:-]{0,127})(?:\s*\[\s*\"([^\"]{1,256})\"\s*\])?")
            header_seen = False
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("%%"):
                    continue
                if header_pattern.fullmatch(stripped):
                    if header_seen or nodes:
                        raise ConsoleError("project view Map source has more than one flowchart header")
                    header_seen = True
                    continue
                if not header_seen:
                    raise ConsoleError("project view Map source must begin with a bounded Mermaid flowchart")
                safe_line = re.sub(r"<br\s*/?>", " · ", stripped, flags=re.IGNORECASE)
                if "<" in safe_line:
                    raise ConsoleError("project view Map labels cannot contain markup")
                parts = safe_line.split("-->")
                if len(parts) > 129:
                    raise ConsoleError("project view Map edge chain is too large")
                segments: list[str] = []
                for index, part in enumerate(parts):
                    segment = part.strip()
                    if index and segment.startswith("|"):
                        labelled = re.fullmatch(r"\|[^|\r\n]{1,256}\|\s*(.+)", segment)
                        if labelled is None:
                            raise ConsoleError("project view Map edge label is invalid")
                        segment = labelled.group(1).strip()
                    segments.append(segment)
                matches = [node_pattern.fullmatch(segment) for segment in segments]
                if any(match is None for match in matches):
                    raise ConsoleError("project view Map contains unsupported Mermaid syntax")
                ids = []
                for match in matches:
                    if match is None:  # guarded above; keep malformed input fail-closed
                        raise ConsoleError("project view Map contains unsupported Mermaid syntax")
                    node_id = match.group(1)
                    label = (match.group(2) or nodes.get(node_id) or node_id).strip()
                    if node_id in nodes and nodes[node_id] != label:
                        raise ConsoleError("project view Map node labels conflict")
                    nodes[node_id] = label
                    ids.append(node_id)
                edges.extend({"source": source, "target": target} for source, target in zip(ids, ids[1:], strict=False))
                if len(nodes) > 256 or len(edges) > 512:
                    raise ConsoleError("project view Map source exceeds the graph bound")
            if not header_seen or not nodes:
                raise ConsoleError("project view Map source has no safe nodes")
        screen_keys = {screen["id"]: screen["id"] for screen in screens}
        for screen in screens:
            screen_keys.setdefault(screen["screen_id"], screen["id"])
        return {
            "nodes": [
                {"id": node_id, "label": label, "screen_key": screen_keys.get(node_id)}
                for node_id, label in nodes.items()
            ],
            "edges": edges,
        }

    @classmethod
    def _project_view_requirements(cls, manifest: dict[str, Any]) -> dict[str, Any] | None:
        contract = manifest.get("screen_group_requirements")
        if contract is None:
            return None
        if not isinstance(contract, dict) or contract.get("contract_id") != "screen.groups.requirements.v1" or contract.get("version") != "1.0.0":
            raise ConsoleError("project view requirement contract is unsupported")
        states = {"KNOWN_SATISFIED", "PARTIAL", "MISSING", "UNKNOWN"}
        devices = {"desktop", "tablet", "mobile"}
        binding_names = {
            "accepted_artifact_refs", "candidate_or_observed_artifact_refs", "unregistered_artifact_refs",
            "implementation_evidence_refs", "browser_proof_refs",
        }

        def requirement(value: Any, *, shared: bool = False) -> dict[str, Any]:
            if not isinstance(value, dict):
                raise ConsoleError("project view requirement must be an object")
            requirement_id = cls._project_view_text(value.get("requirement_id"), "requirement id", 256)
            label = cls._project_view_text(value.get("short_label"), "requirement label", 256)
            required = value.get("required")
            target_devices = value.get("target_devices")
            state = value.get("derived_state")
            bindings = value.get("bindings")
            if not isinstance(required, bool) or not isinstance(target_devices, list) or not target_devices or len(target_devices) > 3:
                raise ConsoleError("project view requirement targets are invalid")
            if len(set(target_devices)) != len(target_devices) or any(device not in devices for device in target_devices):
                raise ConsoleError("project view requirement device is unsupported")
            if state not in states or not isinstance(bindings, dict) or not set(bindings).issubset(binding_names):
                raise ConsoleError("project view requirement state or bindings are invalid")
            normalized_bindings: dict[str, list[dict[str, Any]]] = {}
            for name in binding_names:
                refs = bindings.get(name, [])
                if not isinstance(refs, list) or len(refs) > 64:
                    raise ConsoleError("project view requirement bindings must be bounded lists")
                normalized_refs = []
                for ref in refs:
                    if not isinstance(ref, dict) or not set(ref).issubset({"record_id", "artifact_id", "digest", "bytes", "disposition", "selection_status", "approval_status", "manifest_id", "manifest_version", "kind", "status"}):
                        raise ConsoleError("project view requirement binding has unknown fields")
                    normalized_ref = {
                        "record_id": cls._project_view_text(ref.get("record_id"), "requirement record id", 256),
                        "digest": cls._project_view_digest(ref.get("digest")),
                    }
                    if ref.get("artifact_id") is not None:
                        normalized_ref["artifact_id"] = cls._project_view_text(ref.get("artifact_id"), "requirement artifact id", 256)
                    for optional in ("bytes", "disposition", "selection_status", "approval_status", "manifest_id", "manifest_version", "kind", "status"):
                        if optional in ref:
                            normalized_ref[optional] = copy.deepcopy(ref[optional])
                    normalized_refs.append(normalized_ref)
                normalized_bindings[name] = normalized_refs
            missing_devices = value.get("missing_target_devices", [])
            if "missing" in value:
                missing = value["missing"]
                if not isinstance(missing, list) or len(missing) > 64 or any(not isinstance(item, str) or not item.strip() for item in missing):
                    raise ConsoleError("project view requirement missing reasons are invalid")
            else:
                missing = []
            if not isinstance(missing_devices, list) or len(set(missing_devices)) != len(missing_devices) or any(device not in devices for device in missing_devices):
                raise ConsoleError("project view requirement missing devices are invalid")
            normalized = {
                "requirement_id": requirement_id,
                "short_label": label,
                "required": required,
                "target_devices": list(target_devices),
                "acceptance_criterion": cls._project_view_text(value.get("acceptance_criterion"), "requirement criterion", 4096),
                "bindings": normalized_bindings,
                "derived_state": state,
                "reason": cls._project_view_text(value.get("reason"), "requirement reason", 4096),
                "missing_target_devices": list(missing_devices),
                "missing": list(missing),
            }
            if shared:
                applies = value.get("applies_to_group_ids")
                if not isinstance(applies, list) or not applies:
                    raise ConsoleError("shared project view requirement must name groups")
                normalized["applies_to_group_ids"] = [cls._project_view_text(item, "requirement group id", 256) for item in applies]
            return normalized

        shared_values = contract.get("shared_requirements")
        group_values = contract.get("groups")
        if not isinstance(shared_values, list) or not isinstance(group_values, list) or len(shared_values) != 1 or len(group_values) != 6:
            raise ConsoleError("project view requirements must contain six groups and one shared requirement")
        shared = [requirement(item, shared=True) for item in shared_values]
        shared_ids = {item["requirement_id"] for item in shared}
        groups = []
        group_ids: set[str] = set()
        requirement_ids = set(shared_ids)
        for order, value in enumerate(group_values):
            if not isinstance(value, dict):
                raise ConsoleError("project view requirement group must be an object")
            group_id = cls._project_view_text(value.get("group_id"), "requirement group id", 256)
            if group_id in group_ids:
                raise ConsoleError("project view requirement group identities must be unique")
            group_ids.add(group_id)
            node_ids = value.get("node_ids")
            inherited = value.get("shared_requirement_ids")
            values = value.get("requirements")
            if not isinstance(node_ids, list) or not node_ids or len(node_ids) > 64 or not isinstance(inherited, list) or not isinstance(values, list) or not values:
                raise ConsoleError("project view requirement group is incomplete")
            normalized_requirements = [requirement(item) for item in values]
            for item in normalized_requirements:
                if item["requirement_id"] in requirement_ids:
                    raise ConsoleError("project view requirement identities must be unique")
                requirement_ids.add(item["requirement_id"])
            normalized_inherited = [cls._project_view_text(item, "shared requirement id", 256) for item in inherited]
            if any(item not in shared_ids for item in normalized_inherited):
                raise ConsoleError("project view group names an unknown shared requirement")
            groups.append({
                "group_id": group_id,
                "label": cls._project_view_text(value.get("label"), "requirement group label", 256),
                "order": order,
                "node_ids": [cls._project_view_text(item, "requirement node id", 256) for item in node_ids],
                "shared_requirement_ids": normalized_inherited,
                "requirements": normalized_requirements,
                "counts_by_state": {
                    state: sum(item["derived_state"] == state for item in normalized_requirements)
                    + sum(item["derived_state"] == state for item in shared if item["requirement_id"] in normalized_inherited)
                    for state in ("KNOWN_SATISFIED", "PARTIAL", "MISSING", "UNKNOWN")
                },
            })
        if len(requirement_ids) != 31 or any(set(item.get("applies_to_group_ids", [])) != group_ids for item in shared):
            raise ConsoleError("project view requirements must bind exactly thirty-one requirements across six groups")
        binding = manifest.get("projection_binding")
        if not isinstance(binding, dict) or set(binding) != {"accepted_scope_id", "accepted_cursor", "status", "reason"}:
            raise ConsoleError("project view requirement projection binding is invalid")
        if binding["status"] not in {"KNOWN", "PARTIAL", "UNKNOWN"}:
            raise ConsoleError("project view requirement projection status is unsupported")
        if binding["accepted_scope_id"] is not None:
            cls._project_view_text(binding["accepted_scope_id"], "accepted scope id", 256)
        if binding["accepted_cursor"] is not None and not isinstance(binding["accepted_cursor"], dict):
            raise ConsoleError("project view accepted cursor is invalid")
        counts = Counter(item["derived_state"] for item in shared)
        counts.update(item["derived_state"] for group in groups for item in group["requirements"])
        return {
            "contract_id": contract["contract_id"],
            "version": contract["version"],
            "projection_binding": copy.deepcopy(binding),
            "shared_requirements": shared,
            "groups": groups,
            "requirement_count": len(requirement_ids),
            "counts_by_state": {state: counts.get(state, 0) for state in ("KNOWN_SATISFIED", "PARTIAL", "MISSING", "UNKNOWN")},
        }

    def _project_ui_page_token(self, payload: dict[str, Any] | None = None, token: str | None = None) -> dict[str, Any] | str:
        secret = self.token.encode("utf-8")
        if payload is not None:
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            signature = hmac.new(secret, raw, hashlib.sha256).digest()
            return base64.urlsafe_b64encode(raw + b"." + signature).decode("ascii").rstrip("=")
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise ConsoleError("project UI agent page token is invalid")
        try:
            decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            if len(decoded) < 34 or decoded[-33:-32] != b".":
                raise ValueError("shape")
            raw, signature = decoded[:-33], decoded[-32:]
            if not hmac.compare_digest(signature, hmac.new(secret, raw, hashlib.sha256).digest()):
                raise ValueError("signature")
            value = json.loads(raw)
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConsoleError("project UI agent page token is invalid") from exc
        if not isinstance(value, dict):
            raise ConsoleError("project UI agent page token is invalid")
        return value

    def project_ui_agent_read(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ConsoleError("project UI agent request must be an object")
        operations = {
            "project_views.list_projects_with_manifests", "project_views.get_normalized_manifest",
            "project_views.list_screen_groups", "project_views.get_screen_group",
            "project_views.list_requirements", "project_views.list_missing_requirements",
            "project_views.get_graph_identity", "project_views.get_evidence_identities",
            "project_views.get_artifact_identities",
        }
        allowed_fields = {
            "contract_id", "version", "operation", "project_id", "accepted_scope_id", "accepted_cursor",
            "page_size", "page_token", "group_id", "requirement_id", "requirement_state", "required", "target_device",
            "requested_operations",
        }
        if not set(payload).issubset(allowed_fields):
            raise ConsoleError("project UI agent request contains an unknown field")
        if payload.get("contract_id") != "project.ui.agent_read.v1" or payload.get("version") != "1.0.0":
            raise ConsoleError("project UI agent capability is unsupported")
        operation = payload.get("operation")
        requested = payload.get("requested_operations", [operation])
        if (
            operation not in operations or not isinstance(requested, list) or operation not in requested
            or len(requested) != len(set(requested)) or any(item not in operations for item in requested)
        ):
            raise ConsoleError("project UI agent capability is unsupported")
        common = {"contract_id", "version", "operation", "project_id", "accepted_scope_id", "accepted_cursor", "requested_operations"}
        paged = {"page_size", "page_token"}
        operation_fields = {
            "project_views.list_projects_with_manifests": {"project_id"} | paged,
            "project_views.get_normalized_manifest": set(),
            "project_views.list_screen_groups": paged,
            "project_views.get_screen_group": {"group_id"},
            "project_views.list_requirements": {"group_id", "requirement_state", "required", "target_device"} | paged,
            "project_views.list_missing_requirements": {"group_id", "target_device"} | paged,
            "project_views.get_graph_identity": set(),
            "project_views.get_evidence_identities": {"group_id", "requirement_id"} | paged,
            "project_views.get_artifact_identities": {"group_id", "requirement_id"} | paged,
        }
        if not set(payload).issubset(common | operation_fields[operation]):
            raise ConsoleError("project UI agent request contains a field unsupported by this operation")
        page_size = payload.get("page_size", 25)
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise ConsoleError("project UI agent page size must be between one and one hundred")
        project_id = str(payload.get("project_id") or "").strip()
        if operation == "project_views.list_projects_with_manifests":
            if any(field in payload for field in ("accepted_scope_id", "accepted_cursor", "group_id", "requirement_id", "requirement_state", "required", "target_device")):
                raise ConsoleError("project UI agent project listing has incompatible filters")
            projects = []
            for project in self._navigation_payload(self._host_overview())["projects"]:
                if project_id and project["id"] != project_id:
                    continue
                candidate = self._project_view_projection(project["id"])
                if candidate and candidate.get("requirements"):
                    projects.append({
                        "project_id": project["id"], "manifest_id": candidate["identity"]["manifest_id"],
                        "manifest_version": candidate["identity"]["manifest_version"], "manifest_digest": candidate["identity"]["manifest_digest"],
                        "conditional_tabs": [candidate["tab"]], "projection_binding": candidate["requirements"]["projection_binding"],
                    })
            data = projects
            aggregate_digests = sorted({
                digest for project in projects
                for digest in [project["manifest_digest"]]
            })
            context_projection = {
                "project_id": "*",
                "identity": {"manifest_id": "project-view-catalog", "manifest_version": 1, "source_digests": aggregate_digests},
                "requirements": {"projection_binding": [project["projection_binding"] for project in projects]},
            }
        else:
            projection = self._project_view_projection(project_id) if project_id else None
            if not project_id or projection is None or projection.get("requirements") is None:
                raise ConsoleError("project UI agent project projection is unavailable")
            context_projection = projection
            binding = projection["requirements"]["projection_binding"]
            if (
                binding.get("status") == "UNKNOWN" or binding.get("accepted_scope_id") is None
                or binding.get("accepted_cursor") is None or "accepted_scope_id" not in payload
                or "accepted_cursor" not in payload
            ):
                raise ConsoleError("project UI agent projection binding is unavailable")
            if payload.get("accepted_scope_id") != binding.get("accepted_scope_id") or payload.get("accepted_cursor") != binding.get("accepted_cursor"):
                raise ConsoleError("project UI agent request has a stale cursor")
            groups = projection["requirements"]["groups"]
            shared = projection["requirements"]["shared_requirements"]
            requirements = [
                {**item, "group_id": "shared"} for item in shared
            ] + [
                {**item, "group_id": group["group_id"]} for group in groups for item in group["requirements"]
            ]
            group_id = payload.get("group_id")
            requirement_id = payload.get("requirement_id")
            if group_id is not None and group_id not in {group["group_id"] for group in groups}:
                raise ConsoleError("project UI agent group is unknown")
            if requirement_id is not None and requirement_id not in {item["requirement_id"] for item in requirements}:
                raise ConsoleError("project UI agent requirement is unknown")
            if operation == "project_views.get_normalized_manifest":
                data = {key: copy.deepcopy(projection[key]) for key in ("identity", "tab", "modes", "screens", "map", "requirements")}
            elif operation == "project_views.list_screen_groups":
                data = [{
                    "group_id": group["group_id"], "label": group["label"], "order": group["order"], "node_ids": group["node_ids"],
                    "requirement_counts": copy.deepcopy(group["counts_by_state"]),
                } for group in groups]
            elif operation == "project_views.get_screen_group":
                data = next((copy.deepcopy(group) for group in groups if group["group_id"] == group_id), None)
                if data is None:
                    raise ConsoleError("project UI agent group is unknown")
            elif operation in {"project_views.list_requirements", "project_views.list_missing_requirements"}:
                data = requirements
                if group_id is not None:
                    data = [item for item in data if item["group_id"] == group_id]
                if operation.endswith("list_missing_requirements"):
                    data = [item for item in data if item["derived_state"] in {"MISSING", "PARTIAL", "UNKNOWN"}]
                if payload.get("requirement_state") is not None:
                    if payload["requirement_state"] not in {"KNOWN_SATISFIED", "PARTIAL", "MISSING", "UNKNOWN"}:
                        raise ConsoleError("project UI agent requirement state is unknown")
                    data = [item for item in data if item["derived_state"] == payload["requirement_state"]]
                if payload.get("required") is not None:
                    if not isinstance(payload["required"], bool):
                        raise ConsoleError("project UI agent required filter must be boolean")
                    data = [item for item in data if item["required"] is payload["required"]]
                if payload.get("target_device") is not None:
                    if payload["target_device"] not in {"desktop", "tablet", "mobile"}:
                        raise ConsoleError("project UI agent target device is unknown")
                    data = [item for item in data if payload["target_device"] in item["target_devices"]]
            elif operation == "project_views.get_graph_identity":
                data = {"kind": "graph", "source_digests": projection["identity"]["source_digests"], "node_ids": [item["id"] for item in projection["map"]["nodes"]]}
            else:
                selected = requirements
                if group_id is not None:
                    selected = [item for item in selected if item["group_id"] == group_id]
                if requirement_id is not None:
                    selected = [item for item in selected if item["requirement_id"] == requirement_id]
                if operation == "project_views.get_evidence_identities":
                    names = ("implementation_evidence_refs", "browser_proof_refs")
                    data = [{**ref, "kind": name, "requirement_id": item["requirement_id"]} for item in selected for name in names for ref in item["bindings"][name]]
                else:
                    names = ("accepted_artifact_refs", "candidate_or_observed_artifact_refs", "unregistered_artifact_refs")
                    data = [{**ref, "status": name, "requirement_id": item["requirement_id"]} for item in selected for name in names for ref in item["bindings"][name]]

        identity = context_projection.get("identity", {})
        binding = context_projection.get("requirements", {}).get("projection_binding")
        filters = {key: payload[key] for key in ("group_id", "requirement_id", "requirement_state", "required", "target_device") if key in payload}
        context = {
            "operation": operation, "project_id": project_id, "manifest_id": identity.get("manifest_id"),
            "manifest_version": identity.get("manifest_version"), "source_digests": identity.get("source_digests", []),
            "projection_binding": binding, "filters": filters,
        }
        context_digest = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        offset = 0
        if payload.get("page_token") is not None:
            token_payload = self._project_ui_page_token(token=payload["page_token"])
            if (
                token_payload.get("context_digest") != context_digest
                or isinstance(token_payload.get("offset"), bool)
                or not isinstance(token_payload.get("offset"), int)
                or token_payload["offset"] < 0
            ):
                raise ConsoleError("project UI agent page token has a stale cursor")
            offset = token_payload["offset"]
        if isinstance(data, list):
            page = data[offset:offset + page_size]
            next_token = self._project_ui_page_token({"context_digest": context_digest, "offset": offset + page_size}) if offset + page_size < len(data) else None
        else:
            if payload.get("page_token") is not None:
                raise ConsoleError("project UI agent get operation does not accept a page token")
            page, next_token = data, None
        return {
            "contract_id": "project.ui.agent_read.v1", "version": "1.0.0", "operation": operation,
            "project_id": project_id or None, "manifest_identity": copy.deepcopy(identity),
            "projection_binding": copy.deepcopy(binding), "data": copy.deepcopy(page), "next_page_token": next_token,
        }

    def _normalize_project_view(self, project_id: str, manifest_bytes: bytes, manifest_digest: str) -> dict[str, Any]:
        manifest = self._project_view_json(manifest_bytes, "manifest")
        if manifest.get("manifest_type") != "swarm.project_views" or manifest.get("schema_version") != 1:
            raise ConsoleError("project view manifest type or schema is unsupported")
        if manifest.get("project_id") != project_id:
            raise ConsoleError("project view manifest belongs to another project")
        manifest_id = self._project_view_text(manifest.get("manifest_id"), "manifest id")
        version = manifest.get("manifest_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ConsoleError("project view manifest version must be positive")
        tab = manifest.get("project_tab")
        if not isinstance(tab, dict) or tab.get("id") != "tab.project.ui" or tab.get("visibility") != "conditional":
            raise ConsoleError("project view manifest must declare one conditional UI tab")
        label = self._project_view_text(tab.get("label"), "tab label", 64)
        if label != "UI":
            raise ConsoleError("project view tab label must be UI")
        modes = tab.get("modes")
        expected_modes = ["view.project.ui.screens", "view.project.ui.map"]
        if modes != expected_modes:
            raise ConsoleError("project view UI tab must expose exactly Screens and Map")
        views = manifest.get("views")
        if not isinstance(views, list) or len(views) > 64:
            raise ConsoleError("project view manifest views must be bounded")
        for candidate in views:
            if not isinstance(candidate, dict):
                raise ConsoleError("project view manifest view is invalid")
            renderer = str(candidate.get("renderer") or "")
            mode = str(candidate.get("mode") or "")
            if renderer not in PROJECT_VIEW_RENDERERS or mode not in PROJECT_VIEW_RENDERERS[renderer]:
                raise ConsoleError("project view manifest includes an unknown renderer or mode")
        by_id = {str(view.get("id") or ""): view for view in views}
        screens_view = self._project_view_definition(
            by_id.get(expected_modes[0]), expected_id=expected_modes[0], renderer="gallery", mode="grid", source_kind="coverage.screens",
        )
        map_view = self._project_view_definition(
            by_id.get(expected_modes[1]), expected_id=expected_modes[1], renderer="canvas", mode="network", source_kind="graph.mermaid",
        )
        resolved: dict[tuple[str, str], bytes] = {}
        digest_by_ref: dict[str, str] = {}
        for view in (screens_view, map_view):
            for source in view["sources"]:
                if source["ref"] in digest_by_ref:
                    if digest_by_ref[source["ref"]] != source["digest"]:
                        raise ConsoleError("project view source reference has conflicting digests")
                    raise ConsoleError("project view source reference is duplicated")
                digest_by_ref[source["ref"]] = source["digest"]
                key = (source["ref"], source["digest"])
                if key not in resolved:
                    resolved[key] = self._resolve_project_view_bytes(project_id, *key)
        screens_source = next((source for source in screens_view["sources"] if source["kind"] == "coverage.screens"), None)
        map_source = next((source for source in map_view["sources"] if source["kind"] in {"graph.mermaid", "graph.json"}), None)
        if screens_source is None or map_source is None:
            raise ConsoleError("project view Screens or Map source kind is unsupported")
        screens = self._project_view_screens(project_id, resolved[(screens_source["ref"], screens_source["digest"])])
        graph = self._project_view_graph(resolved[(map_source["ref"], map_source["digest"])], screens)
        requirements = self._project_view_requirements(manifest)
        return {
            "schema_version": 1,
            "project_id": project_id,
            "tab": {"id": "ui", "label": label},
            "modes": [{"id": "screens", "label": "Screens"}, {"id": "map", "label": "Map"}],
            "screens": screens,
            "map": graph,
            "requirements": requirements,
            "identity": {
                "manifest_id": manifest_id,
                "manifest_version": version,
                "manifest_digest": manifest_digest,
                "source_digests": [
                    source["digest"] for view in (screens_view, map_view) for source in view["sources"]
                ],
            },
            "claim_limit": "Project UI is a read-only digest-bound projection; actions and acceptance remain separate authority.",
        }

    def _project_view_projection(self, project_id: str) -> dict[str, Any] | None:
        try:
            root = self._canonical_project_root(project_id)
        except (ConsoleError, OSError, sqlite3.Error):
            return copy.deepcopy(self._project_view_cache.get(project_id))
        status, link = self._root_project_view_link(root)
        if status == "absent":
            self._project_view_cache.pop(project_id, None)
            return None
        if status != "present" or link is None:
            return copy.deepcopy(self._project_view_cache.get(project_id))
        try:
            manifest_bytes = self._resolve_project_view_bytes(project_id, link["ref"], link["digest"])
            projection = self._normalize_project_view(project_id, manifest_bytes, link["digest"])
        except (ConsoleError, OSError, UnicodeError, ValueError, TypeError, sqlite3.Error):
            return copy.deepcopy(self._project_view_cache.get(project_id))
        self._project_view_cache[project_id] = projection
        return copy.deepcopy(projection)

    def _auto_scope(self, ctrl_id: str, project_id: str) -> dict[str, Any]:
        overview = self._host_overview()
        navigation = self._navigation_payload(overview)
        ctrl = next((item for item in navigation["controllers"] if item["id"] == ctrl_id), None)
        project = next((item for item in navigation["projects"] if item["id"] == project_id), None)
        if (
            ctrl is None or ctrl.get("project_id") != project_id
            or not _is_host_confirmed_ctrl(ctrl)
            or ctrl.get("visibility") != "visible"
            or project is None or ctrl_id not in project.get("ctrl_ids", [])
        ):
            raise ConsoleError("Auto requires a current host-confirmed CTRL/project binding")
        return overview

    def auto_status(self, ctrl_id: str, project_id: str) -> dict[str, Any]:
        self._auto_scope(ctrl_id, project_id)
        return {"ok": True, **self.store.auto_status(ctrl_id, project_id)}

    def auto_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ConsoleError("Auto command requires a bounded object")
        command = str(payload.get("command") or "").strip().upper()
        base = {"command", "ctrl_id", "project_id", "request_id"}
        release = base | {"reservation_id", "recovery_authority", "release_condition"}
        if command not in {"ENABLE", "DISABLE", "RELEASE_UNREACHABLE"} or set(payload) != (release if command == "RELEASE_UNREACHABLE" else base):
            raise ConsoleError("Auto command must be ENABLE, DISABLE, or an exact RELEASE_UNREACHABLE request")
        ctrl_id = _auto_id(payload.get("ctrl_id"), "ctrl_id")
        project_id = _auto_id(payload.get("project_id"), "project_id")
        self._auto_scope(ctrl_id, project_id)
        if command == "RELEASE_UNREACHABLE":
            return {"ok": True, **self.store.release_auto_dispatch(
                ctrl_id, project_id, payload.get("reservation_id"),
                request_id=_auto_id(payload.get("request_id"), "request_id"),
                recovery_authority=str(payload.get("recovery_authority") or ""),
                release_condition=str(payload.get("release_condition") or ""),
                now_ms=int(time.time() * 1000),
            )}
        result = self.store.set_auto(
            ctrl_id, project_id, enabled=command == "ENABLE",
            request_id=_auto_id(payload.get("request_id"), "request_id"),
            now_ms=int(time.time() * 1000),
        )
        return {"ok": True, **result}

    @staticmethod
    def _auto_instruction(candidate: dict[str, Any]) -> str:
        return (
            "SWARM Auto continuation. Inspect the durable objective and admitted evidence for "
            f"goal {candidate['goal_id']} and task {candidate['task_id']}. Advance exactly one "
            f"retained operation {candidate['disposition']['next_operation']} through owner "
            f"{candidate['disposition']['next_owner']} and route {candidate['disposition']['next_route']}. "
            "Preserve exact custody, user keep-out, and authority gates. Return only a material receipt "
            "or one exact safety, authority, or external release condition."
        )

    @staticmethod
    def _auto_rubric(
        receipt: dict[str, Any], result: dict[str, Any], lifecycle: dict[str, Any], disposition: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = [
            value for value in (
                receipt.get("receipt_id"), result.get("event_id"), lifecycle.get("event_id"),
                lifecycle.get("release_receipt_id"),
            ) if isinstance(value, str) and value
        ]
        return {
            "authority_ready": lifecycle.get("lifecycle_state") not in {"USER_PAUSED", "KEEP_OUT", "NEEDS_AUTHORITY"},
            "dependencies_ready": lifecycle.get("lifecycle_state") != "WAITING",
            "user_keep_out": lifecycle.get("lifecycle_state") == "KEEP_OUT",
            "recovery": disposition["disposition"], "safety": "GATED" if disposition["disposition"] == "WAIT_USER" else "ELIGIBLE",
            "critical_path_unblock": True,
            "outcome_value": 1, "confidence": "LOW", "remaining_effort": None,
            "proof_strength": min(3, len(tuple(result.get("evidence_receipt_ids") or ()))),
            "risk": "UNKNOWN", "evidence_refs": list(dict.fromkeys(evidence)),
        }

    def _auto_lifecycle_events(self) -> tuple[list[dict[str, Any]], bool]:
        records, truncated = self.progress_ledger._bounded_tail_records()
        events = [
            {**dict(record["event"]), "event_seq": int(record["event_seq"]), "event_digest": str(record["event_digest"])}
            for record in records
            if record.get("_record_type") == "REQUEST_LIFECYCLE" and isinstance(record.get("event"), dict)
        ]
        return events, truncated

    def _auto_candidate(
        self, state: dict[str, Any], overview: dict[str, Any], projection: dict[str, Any],
    ) -> dict[str, Any] | None:
        ctrl_id = state["ctrl_id"]
        project_id = state["project_id"]
        task_ids = {
            str(node["id"])
            for node in overview.get("nodes", [])
            if node.get("project_id") == project_id and ctrl_id in node.get("controller_ids", [])
        }
        candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        cursor = int(projection.get("cursor", {}).get("event_seq") or 0)
        lifecycle_events, lifecycle_truncated = self._auto_lifecycle_events()
        for receipt_id, retained in projection.get("expected_receipts", {}).items():
            if not isinstance(retained, dict):
                continue
            receipt = retained.get("receipt")
            result = retained.get("result")
            if not isinstance(receipt, dict) or not isinstance(result, dict) or receipt.get("task_id") not in task_ids:
                continue
            if result.get("status") == "MATCHED":
                continue
            if result.get("status") != "ATTENTION" and cursor < int(receipt.get("due_generation") or 0):
                continue
            observed_event_id = str(result.get("event_id") or "")
            observed_lifecycle = next(
                (event for event in lifecycle_events if event.get("event_id") == observed_event_id), None,
            )
            if observed_lifecycle is None:
                continue
            request_identity = (observed_lifecycle.get("request_id"), observed_lifecycle.get("stage_id"))
            related = [
                event for event in lifecycle_events
                if (event.get("request_id"), event.get("stage_id")) == request_identity
            ]
            lifecycle = max(related, key=lambda item: int(item["event_seq"]))
            if lifecycle_truncated and lifecycle.get("lifecycle_state") in {"STALLED", "BLOCKED"}:
                continue
            state_name = str(lifecycle.get("lifecycle_state") or "")
            permitted = list(dict.fromkeys(str(route) for route in lifecycle.get("permitted_route_ids") or ()))
            failed_routes = list(dict.fromkeys(
                str(route) for event in related if event.get("lifecycle_state") == "STALLED"
                for route in event.get("route_receipt_ids") or ()
            ))
            failed_turns = list(dict.fromkeys(
                str(turn) for event in related if event.get("lifecycle_state") == "STALLED"
                for turn in event.get("failed_goal_turn_receipt_ids") or ()
            ))
            observed_turn_id = str(result.get("event_id") or f"cursor-{cursor}")
            observed_route = str(result.get("route_digest") or "")
            release_authority = str(lifecycle.get("release_authority") or "")
            release_receipt = str(lifecycle.get("release_receipt_id") or "")
            record = lifecycle.get("record") if isinstance(lifecycle.get("record"), dict) else {}
            release_condition = str(record.get("next_due_event") or "")
            retry_action = str(result.get("retry_action") or "")
            alternate = sorted(set(permitted) - set(failed_routes))
            if state_name == "BLOCKED" and len(set(failed_routes)) >= 3 and len(set(failed_turns)) >= 3 and permitted and set(permitted) <= set(failed_routes) and release_authority and release_receipt:
                disposition = {
                    "disposition": "TERMINAL_BLOCKED", "next_operation": "WAIT_FOR_RETAINED_RELEASE",
                    "next_owner": release_authority, "next_route": "",
                    "release_condition": release_condition or f"release receipt {release_receipt}",
                    "responsible_authority": release_authority,
                }
            elif state_name in {"USER_PAUSED", "KEEP_OUT", "NEEDS_AUTHORITY", "WAITING"}:
                authority = release_authority or ctrl_id
                disposition = {
                    "disposition": "WAIT_USER", "next_operation": "WAIT_FOR_RETAINED_RELEASE",
                    "next_owner": authority, "next_route": "",
                    "release_condition": release_condition or f"retained {state_name} release for {receipt_id}",
                    "responsible_authority": authority,
                }
            elif retry_action in {"REASSESS_ROOT_CAUSE", "STOP_REPEATED_TACTIC"} and alternate:
                disposition = {
                    "disposition": "TRY_ALTERNATE", "next_operation": f"EXECUTE_PERMITTED_ROUTE:{alternate[0]}",
                    "next_owner": str(receipt["owner_id"]), "next_route": alternate[0],
                    "release_condition": "", "responsible_authority": "",
                }
            elif retry_action == "CONTINUE" and observed_route:
                reason = str(result.get("reason") or "FAILED").replace("_", "-")
                disposition = {
                    "disposition": "RETRY_SAME", "next_operation": f"CORRECT-{reason}-AND-RETRY-ONCE",
                    "next_owner": str(receipt["owner_id"]), "next_route": observed_route,
                    "release_condition": "", "responsible_authority": "",
                }
            else:
                authority = release_authority or ctrl_id
                disposition = {
                    "disposition": "WAIT_USER", "next_operation": "AUTHORIZE_DISTINCT_PERMITTED_ROUTE",
                    "next_owner": authority, "next_route": "",
                    "release_condition": release_condition or "retain one exact permitted recovery route",
                    "responsible_authority": authority,
                }
            rubric = self._auto_rubric(receipt, result, lifecycle, disposition)
            operation_route = disposition["next_route"] or disposition["release_condition"]
            route_digest = _auto_digest({"operation": disposition["next_operation"], "route": operation_route})
            decision_digest = _auto_digest({
                "receipt_id": receipt_id, "result_event": result.get("event_id"),
                "result_digest": result.get("event_digest"), "lifecycle_event": lifecycle.get("event_id"),
                "disposition": disposition, "ctrl_id": ctrl_id, "project_id": project_id,
            })
            candidate = {
                "ctrl_id": ctrl_id, "project_id": project_id,
                "goal_id": receipt["goal_id"], "task_id": receipt["task_id"],
                "owner_id": str(receipt["owner_id"]), "request_id": receipt["receipt_id"],
                "observed_turn_id": observed_turn_id, "decision_digest": decision_digest,
                "route_digest": route_digest, "disposition": disposition, "rubric": rubric,
            }
            instruction = self._auto_instruction(candidate)
            candidate["instruction"] = instruction
            candidate["instruction_digest"] = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
            confidence = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[rubric["confidence"]]
            recovery = {"TRY_ALTERNATE": 0, "RETRY_SAME": 1, "WAIT_USER": 2, "TERMINAL_BLOCKED": 3}[disposition["disposition"]]
            key = (
                not rubric["authority_ready"], not rubric["dependencies_ready"], rubric["user_keep_out"],
                recovery, {"ELIGIBLE": 0, "GATED": 1}[rubric["safety"]],
                not rubric["critical_path_unblock"], -rubric["outcome_value"], confidence,
                float("inf") if rubric["remaining_effort"] is None else rubric["remaining_effort"][1],
                str(receipt_id),
            )
            candidates.append((key, candidate))
        return min(candidates, default=((), None), key=lambda item: item[0])[1]

    def _auto_generation(self) -> ExecutionConfigGeneration:
        _, effective, exists = load_config(self.config_path)
        execution = effective.get("execution") if isinstance(effective.get("execution"), dict) else {}
        changed_at_ms = int(self.config_path.stat().st_mtime_ns // 1_000_000) if exists else 0
        payload = {"fast_mode": bool(execution.get("fast_mode", False)), "changed_at_ms": changed_at_ms}
        digest = _auto_digest(payload)
        return ExecutionConfigGeneration(f"swarm-config-{digest}", payload["fast_mode"], "", "", changed_at_ms, f"config:{digest}")

    def evaluate_auto_once(self, overview: dict[str, Any] | None = None) -> dict[str, Any]:
        states = self.store.enabled_auto_states()
        if not states:
            return {"dispatched": False, "reason": "AUTO_CLOSED"}
        overview = overview or self._host_overview()
        projection = self.progress_ledger.replay()
        for state in states:
            self._auto_scope(state["ctrl_id"], state["project_id"])
            if state["in_flight"]:
                if not state["thread_id"]:
                    return {"dispatched": False, "reason": "UNREACHABLE_IN_FLIGHT", "state": state}
                result = self.auto_bridge.reconcile(
                    cwd=self._auto_project_root(state["project_id"]),
                    thread_id=state["thread_id"], turn_id=state["turn_id"],
                )
                if result.turn_id and not state["turn_id"]:
                    self.store.retain_auto_host_ids(
                        state["reservation_id"], result.thread_id, result.turn_id, True,
                        now_ms=int(time.time() * 1000),
                    )
                if not result.terminal:
                    payload = {
                        "ctrl_id": state["ctrl_id"], "project_id": state["project_id"],
                        "reservation_id": state["reservation_id"], "thread_id": result.thread_id,
                        "turn_id": result.turn_id, "failure_kind": result.failure_kind,
                        "reachable": result.reachable, "turn_started": result.turn_started,
                        "material_progress": False,
                    }
                    self.store.retain_auto_control(
                        "AUTO_RECONCILE", f"{state['reservation_id']}:{_auto_digest(payload)}",
                        payload, now_ms=int(time.time() * 1000),
                    )
                    reason = "IN_FLIGHT" if result.failure_kind == "TURN_ACTIVE" else "UNREACHABLE_IN_FLIGHT"
                    return {"dispatched": False, "reason": reason, "state": self.store.auto_status(state["ctrl_id"], state["project_id"])}
                disposition = None if result.ok else {
                    "disposition": "WAIT_USER", "next_operation": "ADMIT_TERMINAL_FAILURE_BEFORE_RETRY",
                    "next_owner": state["ctrl_id"], "next_route": "",
                    "release_condition": "admit the retained terminal host failure into Ledger",
                    "responsible_authority": state["ctrl_id"],
                }
                completed = self.store.finish_auto_dispatch(
                    state["reservation_id"], result=result, disposition=disposition, now_ms=int(time.time() * 1000),
                )
                return {"dispatched": False, "reason": "RECONCILED", "state": completed}
            if not state["enabled"] or state["stop_after_turn"]:
                continue
            candidate = self._auto_candidate(state, overview, projection)
            if candidate is None:
                continue
            if candidate["disposition"]["disposition"] in {"WAIT_USER", "TERMINAL_BLOCKED"}:
                payload = {
                    "ctrl_id": candidate["ctrl_id"], "project_id": candidate["project_id"],
                    "decision_digest": candidate["decision_digest"],
                    "disposition": candidate["disposition"], "rubric": candidate["rubric"],
                    "material_progress": False,
                }
                fresh = self.store.retain_auto_control(
                    "AUTO_DECISION", candidate["decision_digest"], payload,
                    now_ms=int(time.time() * 1000),
                )
                retained = {**self.store.auto_status(state["ctrl_id"], state["project_id"]), "replayed": not fresh}
                return {"dispatched": False, "reason": candidate["disposition"]["disposition"], "state": retained}
            project_root = self._auto_project_root(state["project_id"])
            decision = {key: candidate[key] for key in (
                "ctrl_id", "project_id", "goal_id", "task_id", "owner_id", "request_id",
                "observed_turn_id", "decision_digest", "route_digest", "instruction_digest",
            )}
            decision["next_operation"] = candidate["disposition"]["next_operation"]
            decision["request_bytes"] = len(candidate["instruction"].encode("utf-8"))
            claim = self.store.claim_auto_dispatch(decision, self._auto_generation(), now_ms=int(time.time() * 1000))
            if not claim["claimed"]:
                return {"dispatched": False, **claim}
            result = AutoBridgeResult(False, failure_kind="TRANSPORT_UNAVAILABLE", transient=True)
            retained_thread_id = ""
            for attempt in range(3):
                try:
                    result = self.auto_bridge.run(
                        cwd=project_root, instruction=candidate["instruction"],
                        thread_id=retained_thread_id,
                        retain_ids=lambda thread_id, turn_id, submission_started: self.store.retain_auto_host_ids(
                            claim["reservation_id"], thread_id, turn_id, submission_started,
                            now_ms=int(time.time() * 1000),
                        ),
                    )
                except (ConsoleError, OSError, RuntimeError):
                    result = AutoBridgeResult(False, failure_kind="TRANSPORT_UNAVAILABLE", transient=True)
                retained_thread_id = result.thread_id or retained_thread_id
                if result.ok or result.turn_started or not result.transient:
                    break
                if attempt < 2:
                    jitter = int(candidate["decision_digest"][:4], 16) % 100 / 1000
                    time.sleep(0.25 * (2**attempt) + jitter)
            disposition = None
            if not result.ok:
                if result.turn_started:
                    disposition = {
                        "disposition": "WAIT_USER", "next_operation": "RECONCILE_RETAINED_HOST_TURN",
                        "next_owner": state["ctrl_id"], "next_route": "",
                        "release_condition": "confirm the retained host turn outcome before another turn/start",
                        "responsible_authority": state["ctrl_id"],
                    }
                else:
                    disposition = {
                        "disposition": "WAIT_USER", "next_operation": "RESTORE_APP_SERVER_TRANSPORT",
                        "next_owner": state["ctrl_id"], "next_route": "",
                        "release_condition": "restore the private Codex App Server transport",
                        "responsible_authority": state["ctrl_id"],
                    }
            completed = self.store.finish_auto_dispatch(claim["reservation_id"], result=result, disposition=disposition, now_ms=int(time.time() * 1000))
            return {"dispatched": True, "bridge_ok": result.ok, "state": completed}
        return {"dispatched": False, "reason": "NO_DUE_DECISION"}

    def _host_overview(self, *, refresh: bool = False) -> dict[str, Any]:
        with self.overview_lock:
            if self._overview is not None and not refresh:
                return self._overview
        with self.overview_refresh_lock:
            fingerprint = observation_fingerprint(self.codex_home, self.config_path)
            with self.overview_lock:
                if self._overview is not None and self._overview_fingerprint == fingerprint:
                    return self._overview
            overview = build_overview(self.codex_home, self.config_path)
            fingerprint = observation_fingerprint(self.codex_home, self.config_path)
            with self.overview_lock:
                self._overview_fingerprint = fingerprint
                self._overview = overview
                self._overview_revision += 1
                return overview

    def _ingest_progress_pulses_if_changed(self, overview: dict[str, Any]) -> dict[str, Any]:
        """Import changed bounded sidecars without running token or diagnostic observation."""
        fingerprint = progress_pulse_fingerprint(self.codex_home)
        with self.progress_pulse_lock:
            if fingerprint == self._progress_pulse_fingerprint:
                return {"advanced": 0, "heartbeats": 0, "duplicates": 0, "rejected": 0, "eta_reports": {}}
            try:
                result = self.store.ingest_progress_pulses(
                    self.codex_home,
                    overview,
                    now_ms=int(time.time() * 1000),
                )
            except (OSError, sqlite3.Error):
                result = {"advanced": 0, "heartbeats": 0, "duplicates": 0, "rejected": 1, "eta_reports": {}}
            # Only a rejection-free bounded pass is safe to suppress. A late
            # host observation or transient store failure must retry the same
            # unchanged sidecar on the next read.
            if not result["rejected"]:
                self._progress_pulse_fingerprint = fingerprint
            if result["advanced"] or result["heartbeats"] or result["eta_reports"]:
                with self.overview_lock:
                    self._store_generation += 1
            return result

    def _ingest_proof_events_if_changed(self, overview: dict[str, Any] | None = None) -> dict[str, int]:
        """Advance one durable bounded proof-event reconciliation pass."""
        empty = {
            "imported": 0, "duplicates": 0, "rejected": 0,
            "retryable": 0, "capped": 0, "enumerated": 0,
        }
        if overview is None:
            try:
                overview = self._host_overview()
            except (ConsoleError, OSError, sqlite3.Error):
                return {**empty, "retryable": 1}
        with self.proof_lock:
            try:
                result = self.store.reconcile_proof_events(
                    self.codex_home,
                    overview,
                    now_ms=int(time.time() * 1000),
                )
            except (OSError, sqlite3.Error):
                result = {**empty, "retryable": 1}
            return result

    @staticmethod
    def _receipt_backed_progress(node: dict[str, Any]) -> dict[str, Any] | None:
        eta = node.get("eta")
        if not isinstance(eta, dict) or eta.get("trigger") != "task_owner_report":
            return None
        progress_basis = eta.get("progress_basis")
        if not isinstance(progress_basis, dict):
            return None
        plan_units = progress_basis.get("plan_units")
        receipts = progress_basis.get("receipts")
        receipt_source = eta.get("receipt_source")
        if (
            not isinstance(plan_units, dict)
            or not isinstance(receipts, list)
            or not receipts
            or any(not isinstance(item, str) or not item.strip() for item in receipts)
            or not isinstance(receipt_source, str)
            or not receipt_source.strip()
        ):
            return None
        total_units = plan_units.get("total_units")
        completed_units = plan_units.get("completed_units")
        observed_at_ms = plan_units.get("observed_at_ms")
        basis = plan_units.get("basis")
        plan_id = plan_units.get("plan_id")
        unit_id = plan_units.get("unit_id")
        unit_kind = plan_units.get("unit_kind")
        if (
            not isinstance(total_units, int)
            or isinstance(total_units, bool)
            or total_units <= 0
            or not isinstance(completed_units, int)
            or isinstance(completed_units, bool)
            or not 0 <= completed_units <= total_units
            or not isinstance(observed_at_ms, int)
            or isinstance(observed_at_ms, bool)
            or observed_at_ms <= 0
            or not isinstance(basis, str)
            or not basis.strip()
            or not isinstance(plan_id, str)
            or not plan_id.strip()
            or not isinstance(unit_id, str)
            or not unit_id.strip()
            or not isinstance(unit_kind, str)
            or not unit_kind.strip()
        ):
            return None
        return {
            "percent": round(completed_units * 100 / total_units, 2),
            "total_units": total_units,
            "completed_units": completed_units,
            "basis": basis.strip(),
            "plan_id": plan_id.strip(),
            "unit_id": unit_id.strip(),
            "unit_kind": unit_kind.strip(),
            "observed_at_ms": observed_at_ms,
            "source": (
                eta.get("progress_source")
                if isinstance(eta.get("progress_source"), str) and eta.get("progress_source").strip()
                else "task_owner_report"
            ),
            "receipt_count": len(receipts),
            "claim_limit": (
                "Derived server-side from validated receipt-backed plan units bound to an observed "
                "task-owner planning report or local instruction sidecar; this does not prove native "
                "host/user authority, acceptance, or task progress."
            ),
        }

    @staticmethod
    def _progress_for_nodes(
        nodes: list[dict[str, Any]],
        scope: dict[str, Any],
        *,
        measure_nodes: list[dict[str, Any]] | None = None,
        now_ms: int | None = None,
        stale_after_ms: int = 60 * 60 * 1000,
        empty_measure_reason: str | None = None,
    ) -> dict[str, Any]:
        tasks = [
            node for node in nodes
            if not node.get("virtual") and not node.get("is_subagent") and node.get("role") != "ctrl"
        ]
        task_items: list[dict[str, Any]] = []
        for node in tasks:
            eta = node.get("eta") if isinstance(node.get("eta"), dict) else {}
            proof = node.get("proof_snapshot") if isinstance(node.get("proof_snapshot"), dict) else {}
            media = proof.get("media") if isinstance(proof.get("media"), list) else []
            latest_proof = media[0] if media and isinstance(media[0], dict) else {}
            blocked = node.get("status") == "blocked" or eta.get("status") == "blocked"
            progress = App._receipt_backed_progress(node)
            task_items.append({
                "id": node["id"],
                "project_id": node.get("project_id"),
                "state": node.get("status", "unknown"),
                "blocked": blocked,
                "blocker": eta.get("reason") if blocked else None,
                "latest_proof_receipt": latest_proof.get("evidence_id"),
                "progress": progress,
                "progress_display": f"{progress['percent']:g}%" if progress else "Unmeasured",
            })
        completed = sum(item["state"] in {"done", "archived", "complete"} for item in task_items)
        blocked = sum(bool(item["blocked"]) for item in task_items)
        direct_ctrl_authority = measure_nodes is not None
        progress_nodes = tasks if measure_nodes is None else [
            node for node in measure_nodes
            if not node.get("virtual") and not node.get("is_subagent")
        ]
        measured = [
            progress for node in progress_nodes
            if (progress := App._receipt_backed_progress(node)) is not None
        ]
        aggregate = None
        if not progress_nodes:
            unmeasured_reason = empty_measure_reason or ("missing_ctrl_measure" if direct_ctrl_authority else "no_tasks")
        elif len(measured) != len(progress_nodes):
            unmeasured_reason = "missing_receipt_backed_units"
        elif (
            len({(item["plan_id"], item["unit_kind"]) for item in measured}) != 1
            or len({item["unit_id"] for item in measured}) != len(measured)
        ):
            unmeasured_reason = "heterogeneous_plan_units"
        else:
            total_units = sum(item["total_units"] for item in measured)
            completed_units = sum(item["completed_units"] for item in measured)
            aggregate = {
                "percent": round(completed_units * 100 / total_units, 2),
                "total_units": total_units,
                "completed_units": completed_units,
                "basis": (
                    measured[0]["basis"]
                    if len({item["basis"] for item in measured}) == 1
                    else "Receipt-backed plan units"
                ),
                "plan_id": measured[0]["plan_id"],
                "unit_kind": measured[0]["unit_kind"],
                "unit_ids": sorted(item["unit_id"] for item in measured),
                "observed_at_ms": min(item["observed_at_ms"] for item in measured),
                "source": (
                    measured[0]["source"]
                    if len({item["source"] for item in measured}) == 1
                    else "mixed_validated_task_owner_reports"
                ),
                "receipt_count": sum(item["receipt_count"] for item in measured),
                "authority": "direct_ctrl_receipt" if direct_ctrl_authority else "task_receipts",
                "claim_limit": (
                    "Derived server-side only from compatible validated direct CTRL plan units; "
                    "subordinate task units are not included and this observed planning measure is "
                    "not acceptance or host/user authority."
                    if direct_ctrl_authority
                    else "Derived server-side only from compatible validated receipt-backed plan units; "
                    "this observed planning measure is not acceptance or host/user authority."
                ),
            }
            unmeasured_reason = None
        observed_at_ms = aggregate["observed_at_ms"] if aggregate else None
        freshness_now = observed_at_ms if now_ms is None else now_ms
        age_ms = None if observed_at_ms is None else max(0, int(freshness_now) - int(observed_at_ms))
        freshness = {
            "state": (
                "unavailable"
                if observed_at_ms is None
                else "stale" if age_ms is not None and age_ms > stale_after_ms else "fresh"
            ),
            "observed_at_ms": observed_at_ms,
            "age_ms": age_ms,
            "stale_after_ms": stale_after_ms,
            "source": aggregate["source"] if aggregate else None,
        }
        return {
            "scope": scope,
            "status": "no_tasks" if not task_items and not progress_nodes else "observed",
            "counts": {"tasks": len(task_items), "completed": completed, "blocked": blocked},
            "tasks": task_items,
            "progress": aggregate,
            "progress_display": f"{aggregate['percent']:g}%" if aggregate else "Unmeasured",
            "measurement_status": "measured" if aggregate else "unmeasured",
            "measurement_authority": "direct_ctrl_receipt" if direct_ctrl_authority else "task_receipts",
            "unmeasured_reason": unmeasured_reason,
            "freshness": freshness,
            "claim_limit": (
                "Observed non-subagent task counts plus compatible receipt-backed plan units only; "
                "status, token volume, elapsed time, and proof counts never fabricate percentage."
            ),
        }

    @classmethod
    def _progress_payload(cls, view: dict[str, Any]) -> dict[str, Any]:
        nodes = list(view.get("nodes", []))
        nodes_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
        now_ms = int(time.time() * 1000)
        stale_after_ms = max(1, int(view.get("heartbeat_minutes") or 30)) * PROGRESS_FRESHNESS_WINDOWS * 60_000
        visible_controllers = [
            controller for controller in view.get("controllers", [])
            if _is_host_confirmed_ctrl(controller)
            and not controller.get("archived", False)
            and (node := nodes_by_id.get(str(controller.get("id")))) is not None
            and not node.get("virtual")
            and not node.get("is_subagent")
            and str(node.get("project_id")) == str(controller.get("project_id"))
        ]
        controller_nodes = {
            str(controller["id"]): nodes_by_id[str(controller["id"])]
            for controller in visible_controllers
        }
        project_summaries = {
            str(project["id"]): cls._progress_for_nodes(
                [node for node in nodes if node.get("project_id") == project["id"]],
                {"type": "project", "project_id": project["id"]},
                measure_nodes=[
                    controller_nodes[str(controller["id"])]
                    for controller in visible_controllers
                    if str(controller.get("project_id")) == str(project["id"])
                ],
                now_ms=now_ms,
                stale_after_ms=stale_after_ms,
            )
            for project in view.get("projects", [])
        }
        controller_summaries = {}
        for controller in view.get("controllers", []):
            controller_id = str(controller["id"])
            controller_node = nodes_by_id.get(controller_id)
            classified_node = controller_nodes.get(controller_id)
            controller_summaries[controller_id] = cls._progress_for_nodes(
                [
                    node for node in nodes
                    if node.get("id") == controller["id"]
                    or controller["id"] in node.get("controller_ids", [])
                ],
                {"type": "ctrl", "ctrl_id": controller["id"], "project_id": controller.get("project_id")},
                measure_nodes=[classified_node] if classified_node is not None else [],
                now_ms=now_ms,
                stale_after_ms=stale_after_ms,
                empty_measure_reason=(
                    "unclassified_ctrl"
                    if classified_node is None
                    and controller_node is not None
                    and cls._receipt_backed_progress(controller_node) is not None
                    else None
                ),
            )
        return {
            "all_projects": cls._progress_for_nodes(
                nodes,
                {"type": "all-projects"},
                measure_nodes=list(controller_nodes.values()),
                now_ms=now_ms,
                stale_after_ms=stale_after_ms,
            ),
            "projects": project_summaries,
            "controllers": controller_summaries,
            "claim_limit": "Progress is a read-only projection of observed host tasks; it is not runtime authority.",
        }

    def _project_view(self, overview: dict[str, Any], project_id: str | None) -> dict[str, Any]:
        if not project_id or project_id.casefold() in {"all", "all-projects"}:
            return overview
        view = copy.deepcopy(overview)
        ctrl_scope = project_id.casefold().startswith("ctrl:")
        selected_ctrl_id = project_id[5:] if ctrl_scope else ""
        if ctrl_scope and not selected_ctrl_id:
            raise ConsoleError("project_id ctrl alias must name an observed host CTRL")
        selected_controller = next(
            (controller for controller in view.get("controllers", []) if controller.get("id") == selected_ctrl_id),
            None,
        ) if ctrl_scope else None
        if ctrl_scope and selected_controller is None:
            raise ConsoleError("project_id ctrl alias must name an observed host CTRL")
        selected_project_id = (
            str(selected_controller.get("project_id") or "")
            if selected_controller is not None else project_id
        )
        nodes = [
            node for node in view["nodes"]
            if (
                (selected_ctrl_id in node.get("controller_ids", []) or node.get("id") == selected_ctrl_id)
                if ctrl_scope else node.get("project_id") == selected_project_id
            )
        ]
        node_ids = {node["id"] for node in nodes}
        view["nodes"] = nodes
        view["links"] = [
            link for link in view["links"]
            if link["source"] in node_ids and link["target"] in node_ids
        ]
        view["roots"] = [node_id for node_id in view["roots"] if node_id in node_ids]
        view["controllers"] = [
            controller for controller in view["controllers"]
            if (
                controller.get("id") == selected_ctrl_id
                if ctrl_scope else controller.get("project_id") == selected_project_id
            )
        ]
        view["projects"] = [
            project for project in view["projects"] if project.get("id") == selected_project_id
        ]
        view["analytics"] = {
            **view["analytics"],
            "swarms": len(view["roots"]),
            "tasks": sum(not node.get("virtual") for node in nodes),
            "tokens": sum(int(node.get("tokens") or 0) for node in nodes if not node.get("virtual")),
            "status": dict(Counter(node["status"] for node in nodes if not node.get("virtual"))),
            "models": dict(Counter(
                node.get("model")
                for node in nodes
                if not node.get("virtual") and node.get("model") not in {None, "", "unknown"}
            )),
            "roles": dict(Counter(
                node.get("role", "unknown") for node in nodes if not node.get("virtual")
            )),
        }
        history = (
            self.store.token_history(project_id=selected_project_id, thread_ids=node_ids)
            if ctrl_scope else self.store.token_history(project_id=selected_project_id)
        )
        view["token_history"] = history
        view["analytics"]["burn_rate"] = {
            "tokens_per_minute": history[-1]["delta_tokens"] if history else 0,
            "history": history,
            "source": "codex_jsonl_token_count_or_sqlite_high_water",
            "token_field": "Codex JSONL token_count total/input+output, SQLite threads.tokens_used fallback",
            "label": "Local token-count aggregate; not billing.",
        }
        view["progress"] = self._progress_payload(view)
        view["navigation"] = App._navigation_payload(view)
        view["overview_metrics"] = self._overview_metrics(
            view,
            scope_id=selected_ctrl_id if ctrl_scope else selected_project_id,
            scope_type="ctrl" if ctrl_scope else "project",
        )
        view["project_view"] = None if ctrl_scope else self._project_view_projection(selected_project_id)
        return view

    def _observed_scope(
        self,
        *,
        project_id: str | None = None,
        ctrl_id: str | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], set[str] | None, dict[str, Any]]:
        overview = self._host_overview()
        if project_id and project_id.casefold().startswith("ctrl:"):
            alias_ctrl_id = project_id[5:]
            if not alias_ctrl_id:
                raise ConsoleError("project_id ctrl alias must name an observed host CTRL")
            if ctrl_id and ctrl_id != alias_ctrl_id:
                raise ConsoleError("project_id ctrl alias conflicts with ctrl_id")
            ctrl_id = alias_ctrl_id
            project_id = None
        project_id = None if not project_id or project_id.casefold() in {"all", "all-projects"} else project_id
        ctrl_id = ctrl_id or None
        nodes = [node for node in overview.get("nodes", []) if not node.get("virtual")]
        project_ids = {str(node.get("project_id")) for node in nodes if node.get("project_id")}
        if project_id is not None and project_id not in project_ids:
            raise ConsoleError("project_id must name an observed project")
        ctrl = None
        if ctrl_id:
            ctrl = next((node for node in nodes if node.get("id") == ctrl_id and node.get("role") == "ctrl"), None)
            if ctrl is None:
                raise ConsoleError("ctrl_id must name an observed host CTRL")
            if project_id is not None and ctrl.get("project_id") != project_id:
                raise ConsoleError("ctrl_id does not belong to project_id")
            nodes = [node for node in nodes if ctrl_id in node.get("controller_ids", [])]
            scope = {"type": "ctrl", "ctrl_id": ctrl_id, "project_id": ctrl.get("project_id")}
            return overview, nodes, {str(node["id"]) for node in nodes}, scope
        if project_id is not None:
            nodes = [node for node in nodes if node.get("project_id") == project_id]
            return overview, nodes, {str(node["id"]) for node in nodes}, {"type": "project", "project_id": project_id}
        return overview, nodes, None, {"type": "all-projects"}

    @staticmethod
    def _portfolio_yield(projects: list[dict[str, Any]], *, series_limit: int = 96) -> dict[str, Any]:
        committed_values = [item.get("committed_scope_weight") for item in projects]
        committed = (
            sum(int(value) for value in committed_values)
            if projects and all(value is not None for value in committed_values)
            else None
        )
        gross = sum(int(item["gross_admitted_delta"]) for item in projects)
        invalidated = sum(int(item["invalidated_delta"]) for item in projects)
        tokens = sum(int(item["observed_tokens"]) for item in projects)
        net_points = (
            round((gross - invalidated) * 100 / committed, 4)
            if committed is not None and committed > 0 else None
        )
        measured = bool(projects) and all(item["measurement_state"] == "MEASURED" for item in projects)
        no_activity = bool(projects) and all(item["measurement_state"] == "NO_TOKEN_ACTIVITY" for item in projects)
        state = "MEASURED" if measured else ("NO_TOKEN_ACTIVITY" if no_activity else "UNMEASURED")
        points: dict[int, dict[str, Any]] = {}
        for project in projects:
            for source in project["series"]:
                point = points.setdefault(int(source["observed_at_ms"]), {
                    "observed_at_ms": int(source["observed_at_ms"]),
                    "scope_versions": [],
                    "scope_start": False,
                    "gross_admitted_delta": 0,
                    "invalidated_delta": 0,
                    "observed_tokens": 0,
                    "material_sequences": [],
                    "material_digests": [],
                })
                point["scope_versions"].append({
                    "project_id": project["scope"]["project_id"],
                    "scope_version": source["scope_version"],
                })
                point["scope_start"] = point["scope_start"] or bool(source["scope_start"])
                point["gross_admitted_delta"] += int(source["gross_admitted_delta"])
                point["invalidated_delta"] += int(source["invalidated_delta"])
                point["observed_tokens"] += int(source["observed_tokens"])
                if source["material_sequence"] is not None:
                    point["material_sequences"].append(source["material_sequence"])
                    point["material_digests"].append(source["material_digest"])
        cumulative_gross = cumulative_invalidated = cumulative_tokens = 0
        series = []
        for point in sorted(points.values(), key=lambda item: item["observed_at_ms"]):
            cumulative_gross += point["gross_admitted_delta"]
            cumulative_invalidated += point["invalidated_delta"]
            cumulative_tokens += point["observed_tokens"]
            cumulative_points = (
                round((cumulative_gross - cumulative_invalidated) * 100 / committed, 4)
                if committed is not None and committed > 0 else None
            )
            series.append({
                **point,
                "scope_versions": sorted(point["scope_versions"], key=lambda item: item["project_id"]),
                "material_sequences": sorted(point["material_sequences"]),
                "material_digests": sorted(set(point["material_digests"])),
                "net_scope_points": cumulative_points,
                "yield_per_100k": (
                    round(cumulative_points * 100_000 / cumulative_tokens, 4)
                    if cumulative_points is not None and cumulative_tokens > 0 else None
                ),
            })
        latest_event = max(
            (int(item["freshness"]["event_observed_at_ms"]) for item in projects if item["freshness"]["event_observed_at_ms"] is not None),
            default=None,
        )
        latest_token = max(
            (int(item["freshness"]["token_sampled_at_ms"]) for item in projects if item["freshness"]["token_sampled_at_ms"] is not None),
            default=None,
        )
        return {
            "scope": {"type": "portfolio", "id": "portfolio"},
            "scope_version": None,
            "committed_scope_weight": committed,
            "gross_admitted_delta": gross,
            "invalidated_delta": invalidated,
            "net_scope_points": net_points,
            "observed_tokens": tokens,
            "yield_per_100k": (
                round(net_points * 100_000 / tokens, 4)
                if state == "MEASURED" and net_points is not None and tokens > 0 else None
            ),
            "measurement_state": state,
            "confidence": (
                "HIGH" if measured and all(item["confidence"] == "HIGH" for item in projects)
                else ("PARTIAL" if projects else "UNKNOWN")
            ),
            "freshness": {"event_observed_at_ms": latest_event, "token_sampled_at_ms": latest_token},
            "rework_drag": (
                round(invalidated * 100 / committed, 4)
                if committed is not None and committed > 0 else None
            ),
            "series": series[-series_limit:],
            "series_truncated": len(series) > series_limit,
        }

    def _verified_yield(
        self,
        *,
        nodes: list[dict[str, Any]],
        scope: dict[str, Any],
        hours: int,
        now_ms: int,
    ) -> dict[str, Any]:
        if scope["type"] == "ctrl":
            return {
                "schema_version": 1,
                "measurement_state": "UNMEASURED",
                "reason": "CTRL-scoped proof weighting is not a canonical ProgressLedger denominator.",
                "portfolio": None, "projects": [], "tasks": [], "owners": [], "attention_items": [],
                "claim_limit": "Select a project or portfolio scope; CTRL token filtering is not used to invent proof weight.",
            }
        project_ids = sorted({str(node["project_id"]) for node in nodes if node.get("project_id")})
        after_ms = max(0, now_ms - hours * 60 * 60 * 1000)
        projections = []
        for observed_project_id in project_ids:
            task_ids = {str(node["id"]) for node in nodes if node.get("project_id") == observed_project_id}
            samples = self.store.token_sample_series(
                project_id=observed_project_id, thread_ids=task_ids, hours=hours,
            )
            projections.append(self.progress_ledger.project_verified_yield(
                observed_project_id, samples,
                observed_after_ms=after_ms, observed_before_ms=now_ms,
            ))
        projects = [projection["project"] for projection in projections]
        return {
            "schema_version": 1,
            "formula": "net admitted current-scope points per 100,000 observed local tokens",
            "window": {"after_ms": after_ms, "before_ms": now_ms, "hours": hours},
            "portfolio": self._portfolio_yield(projects),
            "projects": projects,
            "tasks": [item for projection in projections for item in projection["tasks"]],
            "owners": [item for projection in projections for item in projection["owners"]],
            "attention_items": sorted(
                [item for projection in projections for item in projection["attention_items"]],
                key=lambda item: (item["material_sequence"], item["id"]), reverse=True,
            ),
            "claim_limit": (
                "Derived from the canonical material ledger and persisted local token deltas. It is not completion, "
                "billing, quality, agent ranking, or proof acceptance; unread state remains client display state."
            ),
        }

    def usage_history(
        self,
        *,
        project_id: str | None = None,
        ctrl_id: str | None = None,
        hours: int = 24,
        target_reset_at_ms: int | None = None,
        remaining_token_budget: int | None = None,
    ) -> dict[str, Any]:
        if isinstance(hours, bool) or hours not in {1, 12, 24}:
            raise ConsoleError("hours must be one of 1, 12, or 24")
        if target_reset_at_ms is not None and (
            isinstance(target_reset_at_ms, bool)
            or not isinstance(target_reset_at_ms, int)
            or target_reset_at_ms <= 0
        ):
            raise ConsoleError("target_reset_at_ms must be a positive integer")
        if remaining_token_budget is not None and (
            isinstance(remaining_token_budget, bool)
            or not isinstance(remaining_token_budget, int)
            or remaining_token_budget < 0
        ):
            raise ConsoleError("remaining_token_budget must be a non-negative integer")
        _, nodes, thread_ids, scope = self._observed_scope(project_id=project_id, ctrl_id=ctrl_id)
        project_filter = scope.get("project_id") if scope.get("type") == "project" else None
        history = self.store.token_history(project_id=project_filter, thread_ids=thread_ids, hours=hours)
        coverage_thread_ids = {str(node["id"]) for node in nodes}
        observed_threads = self.store.token_sample_thread_count(
            project_id=project_filter, thread_ids=coverage_thread_ids, hours=hours,
        )
        expected_threads = len(nodes)
        total_tokens = sum(int(item["delta_tokens"]) for item in history)
        elapsed_ms = max(0, history[-1]["bucket_ms"] - history[0]["bucket_ms"]) if history else 0
        rate = round(total_tokens / (elapsed_ms / 60_000), 2) if elapsed_ms > 0 else None
        sampled_at_ms = int(history[-1]["bucket_ms"]) if history else None
        now_ms = int(time.time() * 1000)
        usage_now = {
            "status": "observed" if history else "no_data",
            "tokens": total_tokens if history else None,
            "rate_tokens_per_minute": rate,
            "window_hours": hours,
            "sampled_at_ms": sampled_at_ms,
            "source": "persisted_local_token_deltas" if history else None,
        }
        missing_inputs = []
        if remaining_token_budget is None:
            missing_inputs.append("remaining_token_budget")
        if target_reset_at_ms is None:
            missing_inputs.append("target_reset_at_ms")
        if not history:
            missing_inputs.append("usage_history")
        if rate is None or rate <= 0:
            missing_inputs.append("positive_observed_rate")
        if target_reset_at_ms is not None and target_reset_at_ms <= now_ms:
            missing_inputs.append("future_target_reset")
        forecast = {
            "status": "no_data",
            "estimated": False,
            "remaining_token_budget": remaining_token_budget,
            "target_reset_at_ms": target_reset_at_ms,
            "observed_tokens": total_tokens if history else None,
            "observed_rate_tokens_per_minute": rate,
            "remaining_tokens": None,
            "exhaustion_at_ms": None,
            "exhausts_before_reset": None,
            "missing_inputs": sorted(set(missing_inputs)),
            "source": "observed_local_token_rate" if history else None,
            "claim_limit": (
                "Estimate uses persisted local token deltas in the selected window plus an explicit "
                "remaining token budget and reset target; it is not provider billing, quota, or a discovered limit."
            ),
        }
        if not missing_inputs:
            remaining_tokens = int(remaining_token_budget)
            exhaustion_at_ms = (
                now_ms
                if remaining_tokens == 0
                else now_ms + int((remaining_tokens / float(rate)) * 60_000)
            )
            forecast.update({
                "status": "estimated",
                "estimated": True,
                "remaining_tokens": remaining_tokens,
                "exhaustion_at_ms": exhaustion_at_ms,
                "exhausts_before_reset": exhaustion_at_ms <= int(target_reset_at_ms),
                "missing_inputs": [],
            })
        status = "no_data" if not history else (
            "partial" if expected_threads is not None and observed_threads < expected_threads else "ok"
        )
        verified_yield = self._verified_yield(nodes=nodes, scope=scope, hours=hours, now_ms=now_ms)
        return {
            "ok": True,
            "status": status,
            "scope": scope,
            "hours": hours,
            "items": history,
            "total_tokens": total_tokens,
            "elapsed_ms": elapsed_ms,
            "tokens_per_minute": rate,
            "usage_now": usage_now,
            "forecast": forecast,
            "coverage": {"observed_threads": observed_threads, "expected_threads": expected_threads},
            "status_claim": {
                "no_data": "No persisted host-reported samples were found in this scope and time window.",
                "partial": "Some observed scope threads have no persisted sample in this time window.",
                "ok": "Persisted samples cover every observed thread in this scope.",
            },
            "source": "codex_jsonl_token_count_or_sqlite_high_water",
            "token_field": "Codex JSONL token_count total/input+output, SQLite threads.tokens_used fallback",
            "label": "Local token-count aggregate; not billing.",
            "usage_consumed": False,
            "verified_yield": verified_yield,
            "claim_limit": "Aggregated token deltas and time only; prompts, responses, tools, credentials, and billing are excluded.",
        }

    def progress_summary(self, *, project_id: str | None = None, ctrl_id: str | None = None) -> dict[str, Any]:
        _, _, _, scope = self._observed_scope(project_id=project_id, ctrl_id=ctrl_id)
        progress = self.overview().get("progress", {})
        if scope["type"] == "ctrl":
            summary = progress.get("controllers", {}).get(scope["ctrl_id"])
        elif scope["type"] == "project":
            summary = progress.get("projects", {}).get(scope["project_id"])
        else:
            summary = progress.get("all_projects")
        if not isinstance(summary, dict):
            summary = self._progress_for_nodes([], scope, measure_nodes=[])
        return {"ok": True, **copy.deepcopy(summary)}

    def skill_settings(
        self,
        *,
        project_id: str | None = None,
        ctrl_id: str | None = None,
        role: str | None = None,
        task_kind: str | None = None,
    ) -> dict[str, Any]:
        from skills_catalog import resolve
        _, nodes, _, scope = self._observed_scope(project_id=project_id, ctrl_id=ctrl_id)
        del nodes
        _, effective, _ = load_config(self.config_path)
        global_scope = self.store.skill_scope("global", "global")
        project_scope = None
        ctrl_scope = None
        if scope["type"] == "project":
            project_scope = self.store.skill_scope("project", scope["project_id"])
        elif scope["type"] == "ctrl":
            ctrl_scope = self.store.skill_scope("ctrl", scope["ctrl_id"])
            if scope.get("project_id"):
                project_scope = self.store.skill_scope("project", scope["project_id"])
        skills_config = effective.get("skills", {})
        result = resolve(
            self.store.skill_catalog(), global_scope, project_scope, ctrl_scope,
            role=role, task_kind=task_kind,
            global_enabled=bool(skills_config.get("inheritance_enabled", True)),
            global_profile=str(skills_config.get("default_profile", "default")),
            global_preferred=(global_scope or {}).get("preferred_ids", []),
        )
        result.update({
            "ok": True,
            "scope": scope,
            "overlays": {
                "global": global_scope,
                "project": project_scope,
                "ctrl": ctrl_scope,
            },
            "installation": {"allowed": False, "claim_limit": "This console does not install skills."},
        })
        return result

    def update_skill_settings(
        self,
        scope_type: str,
        scope_id: str,
        changes: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        from skills_catalog import validate_scope
        validate_scope(scope_type, scope_id)
        if scope_type == "project":
            self._observed_scope(project_id=scope_id)
        elif scope_type == "ctrl":
            self._observed_scope(ctrl_id=scope_id)
        return self.store.update_skill_scope(
            scope_type, scope_id, changes,
            expected_revision=expected_revision,
            now_ms=int(time.time() * 1000),
        )

    def reset_skill_settings(self, scope_type: str, scope_id: str, expected_revision: int) -> bool:
        from skills_catalog import validate_scope
        validate_scope(scope_type, scope_id)
        if scope_type == "project":
            self._observed_scope(project_id=scope_id)
        elif scope_type == "ctrl":
            self._observed_scope(ctrl_id=scope_id)
        return self.store.reset_skill_scope(scope_type, scope_id, expected_revision=expected_revision)

    @staticmethod
    def _navigation_payload(view: dict[str, Any]) -> dict[str, Any]:
        controllers = [
            {
                "id": controller["id"],
                "project_id": controller.get("project_id", ""),
                "title": controller.get("title", "CTRL"),
                "status": str(controller.get("status", "unknown") or "unknown").strip().casefold(),
                "archived": bool(controller.get("archived", False)),
                "archive_source": controller.get("archive_source"),
                "controller_classification": controller.get("controller_classification", "unavailable"),
                "controller_classification_source": controller.get("controller_classification_source"),
                "status_source": "host_threads.updated_at_ms",
                "visibility": (
                    "hidden"
                    if controller.get("archived", False)
                    or controller.get("controller_classification") != "swarm_ctrl"
                    else "visible"
                ),
                "updated_at": controller.get("updated_at"),
            }
            for controller in view.get("controllers", [])
        ]
        authoritative_controllers = [
            controller for controller in controllers
            if _is_host_confirmed_ctrl(controller)
        ]
        visible_controllers = [controller for controller in authoritative_controllers if not controller["archived"]]
        active_controllers = [controller for controller in visible_controllers if controller["status"] == "active"]
        projects = []
        for project in view.get("projects", []):
            project_id = str(project.get("id", ""))
            all_project_controllers = [
                controller for controller in authoritative_controllers
                if controller["project_id"] == project_id
            ]
            project_controllers = [controller for controller in all_project_controllers if not controller["archived"]]
            ctrl_ids = [controller["id"] for controller in project_controllers]
            active_ids = [controller["id"] for controller in project_controllers if controller["status"] == "active"]
            project_archived = bool(all_project_controllers) and not bool(project_controllers)
            project_nodes = [
                node for node in view.get("nodes", [])
                if node.get("project_id") == project_id and not node.get("virtual")
            ]
            stalled = any(
                controller["status"] in {"stalled", "blocked"}
                for controller in project_controllers
            ) or any(
                str(node.get("status") or "").casefold() in {"stalled", "blocked"}
                for node in project_nodes
            )
            active = bool(active_ids)
            status = "active" if active else ("stalled" if stalled else "inactive")
            projects.append({
                "id": project_id,
                "name": project.get("name", project_id),
                "goal_label": project.get("goal_label", project.get("name", project_id)),
                "label_source": project.get("label_source", "unknown"),
                "ordering": dict(project.get("ordering") or {}),
                "active_ctrl_id": active_ids[0] if active_ids else None,
                "active_ctrl": active,
                "ctrl_ids": ctrl_ids,
                "project_eligibility": "swarm_ctrl" if ctrl_ids else "no_ctrl",
                "eligibility_source": (
                    "+".join(sorted({
                        str(controller["controller_classification_source"])
                        for controller in all_project_controllers
                    }))
                    if all_project_controllers
                    else "unavailable"
                ),
                "archived": project_archived,
                "archive_source": (
                    "host_threads.archived"
                    if all_project_controllers
                    else "unavailable"
                ),
                "visibility": "hidden" if project_archived else "visible",
                "status": status,
                "status_facts": {
                    "active": active,
                    "stalled": stalled,
                    "inactive": not active and not stalled,
                    "source": "host CTRL classification+host_threads.archived+host_threads.updated_at_ms",
                },
                "status_source": "host_threads.updated_at_ms",
                "task_count": len(project_nodes),
            })
        projects.sort(key=_project_order_key)
        raw_project_inventory = view.get("project_inventory")
        if (
            isinstance(raw_project_inventory, dict)
            and raw_project_inventory.get("state") == "KNOWN"
            and raw_project_inventory.get("available") is True
        ):
            project_inventory = {
                "state": "KNOWN",
                "available": True,
                "source": str(raw_project_inventory.get("source") or "host_projects"),
                "claim_limit": str(
                    raw_project_inventory.get("claim_limit")
                    or "Saved project identity is sourced from the canonical host projects table."
                ),
            }
        else:
            project_inventory = {
                "state": "UNKNOWN",
                "available": False,
                "source": "host_projects",
                "claim_limit": (
                    "Saved project identity is unavailable; an empty navigation list is not a known empty "
                    "canonical project inventory."
                ),
            }
        return {
            "active_ctrl_id": active_controllers[0]["id"] if active_controllers else None,
            "active_ctrl_ids": [controller["id"] for controller in active_controllers],
            "controllers": controllers,
            "projects": projects,
            "project_inventory": project_inventory,
            "claim_limit": (
                "Current Work eligibility requires persisted host agent_role=ctrl or fresh, open, project-bound host "
                "spawn evidence to an actual subagent. Titles and runtime status never establish CTRL identity. Legacy, "
                "stale, closed, or unbound rows fail closed as no_ctrl. Saved project inventory is sourced only from the host "
                "projects table; task metadata cannot create a project, and status facts remain read-only observation."
            ),
        }

    @staticmethod
    def _current_work_inventory(
        navigation: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Return the exact visible, non-archived CTRL inventory used by navigation."""
        project_inventory = navigation.get("project_inventory")
        projects = navigation.get("projects")
        controllers = navigation.get("controllers")
        if (
            not isinstance(project_inventory, dict)
            or project_inventory.get("state") != "KNOWN"
            or project_inventory.get("available") is not True
            or not isinstance(projects, list)
            or not isinstance(controllers, list)
            or any(not isinstance(project, dict) for project in projects)
            or any(not isinstance(controller, dict) for controller in controllers)
        ):
            return [], [], False

        eligible_projects: list[dict[str, Any]] = []
        project_ctrl_ids: dict[str, set[str]] = {}
        for project in projects:
            project_id = project.get("id")
            raw_ctrl_ids = project.get("ctrl_ids")
            if (
                not isinstance(project_id, str)
                or not project_id
                or project.get("visibility") != "visible"
                or project.get("archived") is not False
                or project.get("project_eligibility") != "swarm_ctrl"
                or not isinstance(raw_ctrl_ids, list)
                or not raw_ctrl_ids
                or any(not isinstance(ctrl_id, str) or not ctrl_id for ctrl_id in raw_ctrl_ids)
                or project_id in project_ctrl_ids
            ):
                continue
            project_ctrl_ids[project_id] = set(raw_ctrl_ids)
            eligible_projects.append(project)

        eligible_controllers: list[dict[str, Any]] = []
        seen_controller_ids: set[str] = set()
        for controller in controllers:
            controller_id = controller.get("id")
            project_id = controller.get("project_id")
            if (
                not isinstance(controller_id, str)
                or not controller_id
                or controller_id in seen_controller_ids
                or not isinstance(project_id, str)
                or project_id not in project_ctrl_ids
                or controller_id not in project_ctrl_ids[project_id]
                or controller.get("visibility") != "visible"
                or controller.get("archived") is not False
                or not _is_host_confirmed_ctrl(controller)
            ):
                continue
            seen_controller_ids.add(controller_id)
            eligible_controllers.append(controller)

        if any(
            ctrl_id not in seen_controller_ids
            for ctrl_ids in project_ctrl_ids.values()
            for ctrl_id in ctrl_ids
        ):
            return [], [], False
        return eligible_projects, eligible_controllers, True

    def _overview_metrics(
        self,
        view: dict[str, Any],
        *,
        scope_id: str,
        scope_type: str = "all",
    ) -> dict[str, Any]:
        """Project four cards from one host view and one opaque snapshot cursor."""
        scope_id = str(scope_id or "all").strip() or "all"
        if scope_type not in {"all", "project", "ctrl"}:
            scope_type = "all"

        def field_state(known: bool, partial: bool = False) -> str:
            if not known:
                return "UNKNOWN"
            return "PARTIAL" if partial else "KNOWN"

        navigation = view.get("navigation") if isinstance(view.get("navigation"), dict) else {}
        navigation_projects = navigation.get("projects") if isinstance(navigation.get("projects"), list) else None
        navigation_controllers = navigation.get("controllers") if isinstance(navigation.get("controllers"), list) else None
        current_work_projects, current_work_controllers, current_work_known = self._current_work_inventory(navigation)
        selected_controller = None
        if scope_type == "ctrl" and current_work_known:
            selected_controller = next(
                (item for item in current_work_controllers if item.get("id") == scope_id),
                None,
            )
        selected_project_id = (
            str(selected_controller.get("project_id") or "")
            if isinstance(selected_controller, dict) else scope_id if scope_type == "project" else None
        )

        active_work = {"active_projects": None, "active_lanes": None}
        active_states_known = False
        active_states_partial = False
        scope_inventory_known = current_work_known and (scope_type != "ctrl" or selected_controller is not None)
        if scope_inventory_known:
            active_states_known = True
            if scope_type == "all":
                selected_projects = list(current_work_projects)
                selected_controllers = list(current_work_controllers)
            elif scope_type == "project":
                selected_projects = [
                    project for project in current_work_projects
                    if project.get("id") == selected_project_id
                ]
                selected_controllers = [
                    controller for controller in current_work_controllers
                    if controller.get("project_id") == selected_project_id
                ]
            else:
                selected_projects = [
                    project for project in current_work_projects
                    if project.get("id") == selected_project_id
                ]
                selected_controllers = [selected_controller] if isinstance(selected_controller, dict) else []
            project_statuses = []
            for project in selected_projects:
                status = str(project.get("status") or "").casefold() if isinstance(project, dict) else ""
                if status not in {"active", "stalled", "inactive"}:
                    active_states_partial = True
                project_statuses.append(status)
            controller_statuses = []
            for controller in selected_controllers:
                status = str(controller.get("status") or "").casefold() if isinstance(controller, dict) else ""
                if status not in {"active", "stalled", "inactive", "idle", "quiet", "done"}:
                    active_states_partial = True
                controller_statuses.append(status)
            active_work = {
                "active_projects": sum(status == "active" for status in project_statuses),
                "active_lanes": sum(status == "active" for status in controller_statuses),
            }
        active_state = field_state(active_states_known, active_states_partial)

        ledger_projection: dict[str, Any] | None = None
        ledger_partial = False
        try:
            candidate = self.progress_ledger.replay()
            if (
                not isinstance(candidate, dict)
                or not isinstance(candidate.get("cursor"), dict)
                or not isinstance(candidate.get("scopes"), dict)
                or not isinstance(candidate.get("blocks"), dict)
            ):
                raise ProgressEventError("overview metrics Ledger projection is invalid")
            ledger_projection = candidate
            ledger_partial = bool(candidate.get("topology_conflicts"))
        except (AttributeError, OSError, ProgressEventError, TypeError, ValueError):
            ledger_projection = None

        selected_blocks: list[dict[str, Any]] = []
        block_input_partial = False
        if ledger_projection is not None:
            scopes = ledger_projection["scopes"]
            for raw_block in ledger_projection["blocks"].values():
                if not isinstance(raw_block, dict):
                    block_input_partial = True
                    continue
                project_id = str(raw_block.get("project_id") or "")
                if not project_id:
                    block_input_partial = True
                    continue
                if selected_project_id is not None and project_id != selected_project_id:
                    continue
                if scope_type == "ctrl" and raw_block.get("ctrl_id") != scope_id:
                    continue
                scope_version = scopes.get(project_id)
                if not isinstance(scope_version, int) or isinstance(scope_version, bool) or scope_version <= 0:
                    block_input_partial = True
                    continue
                if raw_block.get("scope_version") != scope_version:
                    continue
                if raw_block.get("lifecycle_state") == "TOMBSTONED":
                    continue
                if (
                    not isinstance(raw_block.get("block_id"), str)
                    or not raw_block.get("block_id")
                    or not isinstance(raw_block.get("lifecycle_state"), str)
                    or not isinstance(raw_block.get("flags"), list)
                    or not isinstance(raw_block.get("observed_at_ms"), int)
                    or isinstance(raw_block.get("observed_at_ms"), bool)
                ):
                    block_input_partial = True
                selected_blocks.append(raw_block)

        attention = {"actionable_items": None, "oldest_wait": None}
        attention_states = {"actionable_items": "UNKNOWN", "oldest_wait": "UNKNOWN"}
        if selected_blocks:
            wait_blocks = [
                block for block in selected_blocks
                if str(block.get("lifecycle_state") or "").casefold().upper() in OVERVIEW_WAIT_STATES
                or any(
                    str(flag).casefold() in {"blocked", "stalled"}
                    for flag in (block.get("flags") if isinstance(block.get("flags"), list) else [])
                )
            ]
            attention["actionable_items"] = len(wait_blocks)
            oldest = min(
                wait_blocks,
                key=lambda block: (
                    block.get("observed_at_ms") if isinstance(block.get("observed_at_ms"), int) else 0,
                    str(block.get("block_id") or ""),
                ),
                default=None,
            )
            if oldest is not None:
                attention["oldest_wait"] = {
                    "reason": str(oldest.get("lifecycle_state") or "Waiting"),
                    "block_id": str(oldest.get("block_id") or ""),
                    "observed_at_ms": oldest.get("observed_at_ms"),
                }
            attention_partial = ledger_partial or block_input_partial
            attention_states = {
                "actionable_items": field_state(True, attention_partial),
                "oldest_wait": field_state(True, attention_partial),
            }

        progress = {
            "admitted_milestones": None,
            "admitted_proof": None,
            "completed": None,
            "total": None,
            "percent": None,
            "trend": [],
        }
        progress_states = {field: "UNKNOWN" for field in (
            "admitted_milestones", "admitted_proof", "completed", "total", "percent", "trend",
        )}
        if selected_blocks:
            progress_partial = ledger_partial or block_input_partial
            completed_blocks = [
                block for block in selected_blocks
                if str(block.get("lifecycle_state") or "").upper() in OVERVIEW_COMPLETED_STATES
            ]
            milestone_ids = {
                str(block.get("milestone_id")) for block in completed_blocks if str(block.get("milestone_id") or "")
            }
            admitted_values = [block.get("admitted_proof_weight") for block in selected_blocks]
            committed_values = [block.get("committed_weight") for block in selected_blocks]
            admitted_values_valid = all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in admitted_values
            )
            committed_values_valid = all(
                value is None
                or (isinstance(value, int) and not isinstance(value, bool) and value > 0)
                for value in committed_values
            )
            if not admitted_values_valid or not committed_values_valid:
                progress_partial = True
            admitted = sum(admitted_values) if admitted_values_valid else None
            denominator = (
                sum(committed_values)
                if committed_values
                and all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in committed_values)
                else None
            )
            progress.update({
                "admitted_milestones": len(milestone_ids),
                "admitted_proof": admitted,
                "completed": len(completed_blocks),
                "total": len(selected_blocks),
            })
            for field in ("admitted_milestones", "admitted_proof", "completed", "total"):
                progress_states[field] = (
                    "UNKNOWN"
                    if field == "admitted_proof" and admitted is None
                    else field_state(True, progress_partial)
                )
            if denominator is not None and admitted is not None and admitted <= denominator:
                progress["percent"] = round(admitted * 100 / denominator, 2)
                progress_states["percent"] = field_state(True, progress_partial)
            elif progress_partial:
                progress_states["percent"] = "PARTIAL"

        usage = {
            "window": None,
            "used_tokens": None,
            "remaining_tokens": None,
            "burn_rate_series": [],
            "coverage": None,
        }
        usage_states = {field: "UNKNOWN" for field in (
            "window", "used_tokens", "remaining_tokens", "burn_rate_series", "coverage",
        )}
        history = view.get("token_history")
        valid_history = isinstance(history, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("bucket_ms"), int) and not isinstance(item.get("bucket_ms"), bool)
            and isinstance(item.get("delta_tokens"), int) and not isinstance(item.get("delta_tokens"), bool)
            and item.get("delta_tokens") >= 0
            for item in history
        )
        coverage_observed: int | None = None
        expected_thread_ids = {
            str(node.get("id")) for node in view.get("nodes", [])
            if isinstance(node, dict) and node.get("id") and not node.get("virtual")
        }
        if valid_history and history:
            usage.update({
                "window": "24h",
                "used_tokens": sum(int(item["delta_tokens"]) for item in history),
                "burn_rate_series": [
                    {"observed_at_ms": int(item["bucket_ms"]), "tokens": int(item["delta_tokens"])}
                    for item in history
                ],
            })
            usage_states["window"] = "KNOWN"
            usage_states["used_tokens"] = "KNOWN"
            usage_states["burn_rate_series"] = "KNOWN"
            if expected_thread_ids:
                try:
                    project_filter = selected_project_id if selected_project_id is not None else None
                    coverage_observed = self.store.token_sample_thread_count(
                        project_id=project_filter, thread_ids=expected_thread_ids, hours=24,
                    )
                except (AttributeError, OSError, sqlite3.Error, TypeError, ValueError):
                    coverage_observed = None
                if coverage_observed is not None:
                    usage["coverage"] = (
                        "complete" if coverage_observed >= len(expected_thread_ids) else "partial"
                    )
                    usage_states["coverage"] = (
                        "KNOWN" if coverage_observed >= len(expected_thread_ids) else "PARTIAL"
                    )

        metrics_without_cursor = {
            "active_work": active_work,
            "needs_attention": attention,
            "verified_progress": progress,
            "usage": usage,
        }
        cursor_basis = {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "ledger_cursor": ledger_projection.get("cursor") if ledger_projection is not None else None,
            "selected_blocks": sorted(
                (
                    str(block.get("project_id") or ""),
                    str(block.get("ctrl_id") or ""),
                    str(block.get("block_id") or ""),
                    block.get("latest_event_seq"),
                    block.get("latest_event_digest"),
                    block.get("lifecycle_state"),
                    block.get("committed_weight"),
                    block.get("admitted_proof_weight"),
                )
                for block in selected_blocks
            ),
            "navigation": {
                "project_inventory": navigation.get("project_inventory"),
                "projects": navigation_projects,
                "controllers": navigation_controllers,
            },
            "token_history": history if valid_history else None,
            "coverage_observed": coverage_observed,
            "metrics": metrics_without_cursor,
        }
        cursor_digest = hashlib.sha256(
            json.dumps(cursor_basis, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "schema_version": 1,
            "accepted_scope_id": scope_id,
            "accepted_cursor": {"type": "overview_metrics_v1", "scope_id": scope_id, "digest": cursor_digest},
            **metrics_without_cursor,
            "field_state": {
                "active_projects": active_state,
                "active_lanes": active_state,
                "actionable_items": attention_states["actionable_items"],
                "oldest_wait": attention_states["oldest_wait"],
                "admitted_milestones": progress_states["admitted_milestones"],
                "admitted_proof": progress_states["admitted_proof"],
                "completed": progress_states["completed"],
                "total": progress_states["total"],
                "percent": progress_states["percent"],
                "trend": progress_states["trend"],
                "window": usage_states["window"],
                "used_tokens": usage_states["used_tokens"],
                "remaining_tokens": "UNKNOWN",
                "burn_rate_series": usage_states["burn_rate_series"],
                "coverage": usage_states["coverage"],
            },
            "source": "one_host_view_plus_canonical_progress_ledger_plus_persisted_token_samples",
            "claim_limit": (
                "All four cards share one accepted scope and opaque snapshot cursor. UNKNOWN means the selected "
                "authoritative receipt set is absent or invalid; zero is emitted only when the retained source "
                "establishes an empty count. Usage is local observation, not provider quota or billing."
            ),
        }

    def _decorate_overview(self, base: dict[str, Any]) -> dict[str, Any]:
        view = copy.deepcopy(base)
        forecasts = self.store.latest_forecasts()
        progress_states = self.store.latest_progress()
        for node in view["nodes"]:
            node["eta"] = forecasts.get(node["id"])
            progress_state = progress_states.get(node["id"])
            if progress_state is not None and progress_state.get("project_id") == node.get("project_id") and not node.get("is_subagent"):
                if node["eta"] is None:
                    node["eta"] = {}
                node["eta"].update({
                    "trigger": "task_owner_report",
                    "progress_basis": progress_state["progress_basis"],
                    "receipt_source": progress_state["receipt_source"],
                    "progress_source": "instruction_only_local_sidecar",
                    "last_material_heartbeat_at_ms": progress_state["progress_basis"]["plan_units"]["observed_at_ms"],
                    "pulse_observed_at_ms": progress_state["pulse_observed_at_ms"],
                    "pulse_state": progress_state["pulse_state"],
                    "claim_limit": progress_state["claim_limit"],
                })
            if node["eta"] is not None:
                node["eta"]["eta_source"] = "task_owner_report" if node["id"] in forecasts else None
                node["eta"]["eta_observed_at_ms"] = node["eta"].get("last_calculated_at_ms")
                node["eta"]["heartbeat_at_ms"] = node["eta"].get("last_material_heartbeat_at_ms")
            node["proof_snapshot"] = self.store.proof_snapshot(node["id"])
        history = self.store.token_history()
        view["token_history"] = history
        latest_delta = history[-1]["delta_tokens"] if history else 0
        view["analytics"]["burn_rate"] = {
            "tokens_per_minute": latest_delta,
            "history": history,
            "source": "codex_jsonl_token_count_or_sqlite_high_water",
            "token_field": "Codex JSONL token_count total/input+output, SQLite threads.tokens_used fallback",
            "label": "Local token-count aggregate; not billing.",
        }
        view["progress"] = self._progress_payload(view)
        view["navigation"] = self._navigation_payload(view)
        view["overview_metrics"] = self._overview_metrics(view, scope_id="all", scope_type="all")
        return view

    def overview(self, project_id: str | None = None) -> dict[str, Any]:
        # Never call _host_overview while holding overview_lock. The refresh
        # path owns overview_refresh_lock before publishing under overview_lock.
        overview = self._host_overview()
        self._ingest_progress_pulses_if_changed(overview)
        with self.overview_lock:
            if (
                self._view is None
                or self._view_fingerprint != self._overview_revision
                or self._view_store_generation != self._store_generation
            ):
                self._view = self._decorate_overview(self._overview or {})
                self._view_fingerprint = self._overview_revision
                self._view_store_generation = self._store_generation
            return self._project_view(self._view, project_id)

    def observe_once(self, trigger: str = "heartbeat") -> None:
        overview = self._host_overview(refresh=trigger in {"startup", "state_change"})
        now_ms = int(time.time() * 1000)
        heartbeat_minutes = max(1, int(overview.get("heartbeat_minutes") or 30))
        observed = copy.deepcopy(overview)
        pulse_result = self._ingest_progress_pulses_if_changed(observed)
        eta_reports = pulse_result.get("eta_reports", {})
        for node in observed.get("nodes", []):
            report = eta_reports.get(str(node.get("id")))
            if report is not None and not node.get("virtual") and not node.get("is_subagent"):
                node["eta_report"] = report
        self.store.observe_overview(
            observed,
            now_ms=now_ms,
            trigger=trigger,
            heartbeat_minutes=heartbeat_minutes,
            codex_home=self.codex_home,
        )
        self._ingest_proof_events_if_changed(observed)
        try:
            self.evaluate_auto_once(observed)
        except (ConsoleError, OSError, sqlite3.Error, ValueError, TypeError):
            # Auto is opt-in and fail-closed; host observation must stay available.
            pass
        try:
            sample = self.diagnostics_collector.collect()
            self.store.record_diagnostics(
                sample,
                now_ms=int(sample["sampled_at_ms"]),
                auto_enabled=self._auto_health_enabled(),
            )
        except (ConsoleError, OSError, sqlite3.Error, ValueError, TypeError):
            # Diagnostics are advisory and must never make host observation fail.
            pass
        self._last_observed_fingerprint = observation_fingerprint(self.codex_home, self.config_path)
        with self.overview_lock:
            self._store_generation += 1

    def _observer_loop(self) -> None:
        while not self._observer_stop.wait(TOKEN_SAMPLE_SECONDS):
            try:
                fingerprint = observation_fingerprint(self.codex_home, self.config_path)
                trigger = "state_change" if fingerprint != self._last_observed_fingerprint else "heartbeat"
                self.observe_once(trigger)
            except (ConsoleError, OSError, sqlite3.Error):
                # The host state may be temporarily unavailable; retain the last safe snapshot.
                continue

    def start_observer(self) -> None:
        if self._observer_thread and self._observer_thread.is_alive():
            return
        try:
            self.observe_once("startup")
        except (ConsoleError, OSError, sqlite3.Error):
            # A fresh console may start before Codex has created its state DB.
            # The next heartbeat will retry without blocking the localhost service.
            pass
        self._observer_stop.clear()
        self._observer_thread = threading.Thread(
            target=self._observer_loop,
            name="swarm-console-observer",
            daemon=True,
        )
        self._observer_thread.start()

    def stop_observer(self) -> None:
        self._observer_stop.set()
        if self._observer_thread:
            self._observer_thread.join(timeout=2)

    def profile_presentation(self) -> dict[str, Any]:
        """Expose only the canonical local console presentation asset."""
        avatar_path = STATIC_ROOT / "swarm-icon-64.png"
        avatar = None
        try:
            if not _is_reparse_point(avatar_path) and avatar_path.is_file():
                avatar = {
                    "url": "/swarm-icon-64.png",
                    "alt": "SWARM console",
                    "media_type": "image/png",
                    "digest": hashlib.sha256(avatar_path.read_bytes()).hexdigest(),
                }
        except OSError:
            avatar = None
        return {
            "ok": True,
            "schema_version": 1,
            "state": "KNOWN" if avatar is not None else "PARTIAL",
            "profile": {
                "display_name": "SWARM",
                "avatar": avatar,
                "source": "canonical_console_static_asset",
            },
            "field_state": {
                "display_name": "KNOWN",
                "avatar": "KNOWN" if avatar is not None else "UNKNOWN",
            },
            "claim_limit": (
                "Presentation-only console branding. This response does not identify a user or expose account "
                "identity, credentials, provider data, configuration secrets, or authorization material."
            ),
        }

    def proof_feed(self, *, project_id: str | None = None, task_id: str | None = None) -> list[dict[str, Any]]:
        self._ingest_proof_events_if_changed()
        return self.store.proof_feed(project_id=project_id, task_id=task_id)

    @staticmethod
    def _proof_reconciliation_status(reconciliation: dict[str, int]) -> str:
        return "partial" if any(
            reconciliation.get(field, 0) for field in ("rejected", "retryable", "capped")
        ) else "available"

    def _proof_feed_projection(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        empty_cursor = {"sequence": None, "identity": None}
        try:
            reconciliation = self._ingest_proof_events_if_changed()
            items = self.store.proof_feed(project_id=project_id, task_id=task_id)
            cursor = self.store.proof_cursor()
        except (AttributeError, ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
            return {
                "ok": True,
                "status": "unavailable",
                "sequence": None,
                "proof_cursor": empty_cursor,
                "items": [],
                "claim_limit": "Proof store unavailable; no conclusion about proof presence or acceptance is emitted.",
            }
        return {
            "ok": True,
            "status": self._proof_reconciliation_status(reconciliation),
            "sequence": cursor["sequence"],
            "proof_cursor": cursor,
            "items": items,
            "claim_limit": (
                "Proof media is retained independently of review annotations; partial means the bounded proof "
                "reconciliation had rejected, capped, or retryable input, and availability is not acceptance."
            ),
        }

    def _proof_items_for_scope(
        self,
        project_id: str,
        *,
        overview: dict[str, Any],
        task_ids: set[str] | None = None,
        ctrl_id: str | None = None,
        agent_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        """Surface independently retained proof media without Ledger/review filtering."""
        reconciliation = self._ingest_proof_events_if_changed(overview)
        items = self.store.proof_feed(project_id=project_id)
        cursor = self.store.proof_cursor()
        node_by_id = {
            str(node.get("id")): node for node in overview.get("nodes", [])
            if isinstance(node, dict) and node.get("id")
        }
        selected: list[dict[str, Any]] = []
        for item in items:
            item_task_id = str(item.get("task_id") or "")
            if task_ids is not None and item_task_id not in task_ids:
                continue
            node = node_by_id.get(item_task_id)
            if ctrl_id is not None and (
                node is None
                or item_task_id != ctrl_id and ctrl_id not in node.get("controller_ids", [])
            ):
                continue
            if agent_id is not None and item_task_id != agent_id:
                continue
            selected.append(item)
        return selected, self._proof_reconciliation_status(reconciliation), cursor

    def _project_progress_scope(
        self,
        project_id: str,
    ) -> dict[str, dict[str, dict[str, str]]]:
        """Bind the Ledger projection to host-confirmed project and CTRL task custody."""
        overview, host_nodes, _, _ = self._observed_scope(project_id=project_id)
        navigation = self._navigation_payload(overview)
        project = next((
            item for item in navigation.get("projects", [])
            if item.get("id") == project_id
            and item.get("project_eligibility") == "swarm_ctrl"
            and item.get("visibility") == "visible"
            and item.get("archived") is False
        ), None)
        if project is None:
            raise ConsoleError("PROJECT_SCOPE_UNAVAILABLE")
        ctrl_ids = tuple(project.get("ctrl_ids") or ())
        if not ctrl_ids or any(not isinstance(ctrl_id, str) or not ctrl_id for ctrl_id in ctrl_ids):
            raise ConsoleError("CTRL_SCOPE_UNAVAILABLE")
        ctrl_tasks: dict[str, dict[str, dict[str, str]]] = {ctrl_id: {} for ctrl_id in ctrl_ids}
        for node in host_nodes:
            if not isinstance(node, dict) or node.get("virtual") or not node.get("id"):
                continue
            task_id = str(node["id"])
            memberships = [
                ctrl_id for ctrl_id in ctrl_ids
                if task_id == ctrl_id or ctrl_id in node.get("controller_ids", [])
            ]
            if not memberships:
                continue
            if len(memberships) != 1 or node.get("project_id") != project_id:
                raise ConsoleError("MIXED_SCOPE_REJECTED")
            ctrl_tasks[memberships[0]][task_id] = {
                "task_name": str(node.get("artifact") or node.get("title") or task_id),
                "role": str(node.get("role_label") or node.get("role") or ""),
            }
        if any(not tasks for tasks in ctrl_tasks.values()):
            raise ConsoleError("CTRL_SCOPE_UNAVAILABLE")
        return ctrl_tasks

    def project_progress_feed(self, project_id: str, *, after_cursor: int = 0) -> dict[str, Any]:
        """Build one lazy project feed snapshot from canonical material events."""
        if not isinstance(project_id, str) or not project_id.strip():
            raise ConsoleError("project_id is required")
        try:
            _, config, _ = load_config(self.config_path)
            enabled = bool(config["console"]["project_progress_feed_enabled"])
            limit = int(config["console"]["project_progress_feed_lines"])
            if not enabled:
                return {
                    "ok": True,
                    "enabled": False,
                    "limit": limit,
                    "project_id": project_id.strip(),
                    "cursor": {"event_seq": after_cursor, "event_id": None, "event_digest": None},
                    "items": [],
                    "proof_items": [],
                    "proof_cursor": {"sequence": None, "identity": None},
                    "proof_status": "disabled",
                    "stale_cursor": False,
                    "transport": {"snapshot": "disabled", "incremental": "disabled", "http_stream": "UNVERIFIED"},
                    "producer": {"status": "typed_runtime_transition_only", "native_host_transport": "UNVERIFIED"},
                    "claim_limit": "Feed delivery is disabled; canonical progress audit history and execution liveness are retained independently.",
                }
            snapshot = {
                "ok": True,
                "enabled": True,
                **self.progress_ledger.feed_snapshot(project_id.strip(), limit=limit, after_cursor=after_cursor),
            }
            snapshot["proof_items"] = []
            snapshot["proof_cursor"] = {"sequence": None, "identity": None}
            snapshot["proof_status"] = "unavailable"
            snapshot["proof_source"] = "independently_retained_ctrl_evidence"
            if hasattr(self, "store"):
                try:
                    overview = self._host_overview()
                    (
                        snapshot["proof_items"],
                        snapshot["proof_status"],
                        snapshot["proof_cursor"],
                    ) = self._proof_items_for_scope(
                        project_id.strip(), overview=overview,
                    )
                except (AttributeError, ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
                    snapshot["proof_items"] = []
                    snapshot["proof_cursor"] = {"sequence": None, "identity": None}
                    snapshot["proof_status"] = "unavailable"
            return snapshot
        except (KeyError, TypeError, ValueError, ProgressEventError) as error:
            raise ConsoleError(str(error)) from error

    def measurable_progress(self, project_id: str) -> dict[str, Any]:
        """Return one atomic host-bound completion and Active/Queue projection."""
        if not isinstance(project_id, str) or not project_id.strip():
            raise ConsoleError("project_id is required")
        normalized_project_id = project_id.strip()
        try:
            return {
                "ok": True,
                **self.progress_ledger.project_progress_queue_bundle(
                    normalized_project_id,
                    self._project_progress_scope(normalized_project_id),
                ),
            }
        except (ConsoleError, ProgressEventError) as error:
            reason = str(error) if str(error) in {
                "PROJECT_SCOPE_UNAVAILABLE", "CTRL_SCOPE_UNAVAILABLE", "MIXED_SCOPE_REJECTED",
            } else "RESYNC_REQUIRED"
            return {
                "ok": True,
                **ProgressLedger.unknown_project_progress_bundle(normalized_project_id, reason),
            }

    def role_manifest_projection(self) -> dict[str, Any]:
        try:
            return {"ok": True, **self.progress_ledger.project_role_manifests(self.builtin_role_manifests)}
        except ProgressEventError as error:
            raise ConsoleError(str(error)) from error

    def _strict_run_log_records(self) -> tuple[list[dict[str, Any]], bool]:
        """Read one stable, validated Ledger tail; skipped/corrupt records fail closed."""
        path = self.progress_ledger._state.path

        def window() -> tuple[int, bytes]:
            if not path.exists():
                return 0, b""
            size = path.stat().st_size
            start = max(0, size - MAX_FEED_SCAN_BYTES)
            with path.open("rb") as handle:
                handle.seek(start)
                return start, handle.read(MAX_FEED_SCAN_BYTES)

        before = window()
        records, truncated = self.progress_ledger._bounded_tail_records()
        after = window()
        if before != after:
            raise ConsoleError("run log source Ledger changed during read; retry")
        start, payload = before
        lines = payload.splitlines()
        if start and lines:
            lines = lines[1:]
        if len(lines) != len(records):
            raise ConsoleError("run log source Ledger is corrupt")
        sequences: list[int] = []
        for line, record in zip(lines, records, strict=True):
            try:
                raw = json.loads(line)
                sequence = raw["event_seq"]
                if (
                    not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0
                    or sequence != record["event_seq"]
                    or raw["event_digest"] != record["event_digest"]
                ):
                    raise ValueError
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                raise ConsoleError("run log source Ledger is corrupt") from error
            sequences.append(sequence)
        if sequences and sequences != list(range(sequences[0], sequences[-1] + 1)):
            raise ConsoleError("run log source Ledger sequence is not contiguous")
        return records, truncated

    def run_log(
        self,
        ctrl_id: str,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        after_cursor: int = 0,
    ) -> dict[str, Any]:
        """Project a bounded user-relevant run log from retained typed Ledger events."""
        ctrl_id = _auto_id(ctrl_id, "ctrl_id")
        project_id = _auto_id(project_id, "project_id") if project_id is not None else None
        agent_id = _auto_id(agent_id, "agent_id") if agent_id is not None else None
        if not isinstance(after_cursor, int) or isinstance(after_cursor, bool) or after_cursor < 0:
            raise ConsoleError("after_cursor must be a non-negative Ledger sequence")

        overview, nodes, _, scope = self._observed_scope(project_id=project_id, ctrl_id=ctrl_id)
        navigation = self._navigation_payload(overview)
        controller = next((item for item in navigation["controllers"] if item["id"] == ctrl_id), None)
        resolved_project_id = str(scope.get("project_id") or "")
        project = next(
            (item for item in navigation["projects"] if item["id"] == resolved_project_id), None,
        )
        if (
            controller is None or controller.get("project_id") != resolved_project_id
            or not _is_host_confirmed_ctrl(controller)
            or controller.get("visibility") != "visible"
            or project is None or ctrl_id not in project.get("ctrl_ids", [])
        ):
            raise ConsoleError("run log requires a current host-confirmed CTRL/project binding")

        node_by_id = {str(node["id"]): node for node in nodes}
        records, source_truncated = self._strict_run_log_records()
        if records:
            oldest_sequence = int(records[0]["event_seq"])
            newest_sequence = int(records[-1]["event_seq"])
            if after_cursor > newest_sequence:
                raise ConsoleError("after_cursor is newer than the retained Ledger")
        else:
            oldest_sequence = newest_sequence = 0
            if after_cursor:
                raise ConsoleError("after_cursor is outside the retained Ledger")
        stale_cursor = bool(source_truncated and after_cursor and after_cursor < oldest_sequence)

        candidates: list[dict[str, Any]] = []
        identities: dict[str, str] = {}
        for record in records:
            event = record.get("_event")
            if event is None or event.ctrl_id != ctrl_id:
                continue
            if event.project_id != resolved_project_id:
                continue
            if event.task_id not in node_by_id:
                continue
            if agent_id is not None and agent_id not in {event.task_id, event.owner_id}:
                continue
            kind = event.event_kind.value
            summary = RUN_LOG_SUMMARIES.get(kind)
            if summary is None:
                continue
            event_digest = str(record["event_digest"])
            prior_digest = identities.setdefault(event.event_id, event_digest)
            if prior_digest != event_digest:
                raise ConsoleError("run log source Ledger contains a conflicting event identity")
            node = node_by_id.get(event.task_id, {})
            evidence_refs = list(dict.fromkeys([
                event.event_id,
                event_digest,
                *event.proof_receipt_ids,
                *event.weight_basis_receipt_ids,
                *event.invalidated_receipt_ids,
                *event.steering_receipt_ids,
                *([event.dispatch_receipt_id] if event.dispatch_receipt_id else []),
                *([event.completion_receipt_id] if event.completion_receipt_id else []),
                *event.cost_receipt_ids,
                *event.release_receipt_ids,
            ]))[:12]
            candidates.append({
                "event_id": event.event_id,
                "event_digest": event_digest,
                "event_seq": int(record["event_seq"]),
                "observed_at_ms": event.observed_at_ms,
                "kind": kind,
                "status": event.lifecycle_state.value,
                "project_id": resolved_project_id,
                "ctrl_id": ctrl_id,
                "task_id": event.task_id,
                "owner_id": event.owner_id,
                "agent_id": event.task_id,
                "structural_role": node.get("role"),
                "profession": node.get("worker_role"),
                "summary": summary,
                "evidence_refs": evidence_refs,
                "action_target": {
                    "view": "review" if kind in {"PROOF_ADMITTED", "PROOF_INVALIDATED"} else "projects",
                    "project_id": resolved_project_id,
                    "ctrl_id": ctrl_id,
                    "task_id": event.task_id,
                    "subject_id": event.block_id,
                },
            })
        candidates.sort(key=lambda item: (item["event_seq"], item["event_id"]))
        if not after_cursor or stale_cursor:
            page_truncated = len(candidates) > RUN_LOG_LIMIT
            items = candidates[-RUN_LOG_LIMIT:]
            next_cursor = newest_sequence
        else:
            pending = [item for item in candidates if item["event_seq"] > after_cursor]
            page_truncated = len(pending) > RUN_LOG_LIMIT
            items = pending[:RUN_LOG_LIMIT]
            next_cursor = items[-1]["event_seq"] if page_truncated and items else newest_sequence
        proof_items: list[dict[str, Any]] = []
        proof_cursor: dict[str, Any] = {"sequence": None, "identity": None}
        proof_status = "unavailable"
        try:
            proof_items, proof_status, proof_cursor = self._proof_items_for_scope(
                resolved_project_id,
                overview=overview,
                task_ids=set(node_by_id),
                ctrl_id=ctrl_id,
                agent_id=agent_id,
            )
        except (AttributeError, ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
            pass
        return {
            "ok": True,
            "schema_version": 1,
            "scope": {
                "ctrl_id": ctrl_id,
                "project_id": resolved_project_id,
                "agent_id": agent_id,
            },
            "items": items,
            "cursor": {"after_event_seq": after_cursor, "next_event_seq": next_cursor},
            "proof_items": proof_items,
            "proof_cursor": proof_cursor,
            "proof_status": proof_status,
            "retention": {
                "limit": RUN_LOG_LIMIT,
                "returned": len(items),
                "page_truncated": page_truncated,
                "source_scan_truncated": source_truncated,
                "stale_cursor": stale_cursor,
                "oldest_retained_event_seq": oldest_sequence or None,
            },
            "source": "canonical_ledger_typed_material_events",
            "claim_limit": (
                "This is a bounded read-only projection of retained typed Ledger events; it excludes raw prompts, "
                "model reasoning, terminal output, secrets, and non-material activity. Independently retained proof "
                "media is surfaced in proof_items with its own cursor; review annotations never hide availability, "
                "and availability is not acceptance."
            ),
        }

    @staticmethod
    def _notification_principal() -> str:
        return f"local:{INSTANCE_ID}"

    def _notification_items(self, ctrl_id: str, project_id: str) -> tuple[list[dict[str, Any]], bool]:
        _, nodes, _, _ = self._observed_scope(project_id=project_id, ctrl_id=ctrl_id)
        task_ids = {str(node["id"]) for node in nodes}
        records, truncated = self.progress_ledger._bounded_tail_records()
        principal_id = self._notification_principal()
        candidates: list[dict[str, Any]] = []
        event_digests: dict[str, set[str]] = {}
        for record in records:
            event = record.get("_event")
            if (
                event is None or event.project_id != project_id or event.ctrl_id != ctrl_id
                or event.task_id not in task_ids
            ):
                continue
            event_digest = str(record["event_digest"])
            event_digests.setdefault(event.event_id, set()).add(event_digest)
            kind = None
            if event.lifecycle_state.value == "WAITING_EXTERNAL" and "blocked" in event.flags:
                kind = "BLOCKER"
            elif (
                event.event_kind.value == "ACCEPTED" and event.lifecycle_state.value == "ACCEPTED"
                and event.block_id == event.milestone_id and event.parent_block_id is None
                and "MILESTONE_ACCEPTANCE" in event.proof_required_classes
                and event.committed_weight is not None
                and event.admitted_proof_weight == event.committed_weight
                and event.proof_receipt_ids
            ):
                kind = "MILESTONE_COMPLETED"
            elif (
                event.event_kind.value == "STATE_CHANGED" and event.lifecycle_state.value == "REVIEW"
                and "INDEPENDENT_REVIEW" in event.proof_required_classes
            ):
                kind = "REVIEW_REQUESTED"
            elif (
                event.event_kind.value == "PROOF_ADMITTED"
                and event.lifecycle_state.value in {"VERIFIED", "ACCEPTED"}
                and "INDEPENDENT_REVIEW" in event.proof_required_classes
                and event.admitted_proof_weight > 0 and event.proof_receipt_ids
            ):
                kind = "REVIEW_COMPLETED"
            if kind is None:
                continue
            severity, requires_action, view, sentence = NOTIFICATION_RULES[kind]
            evidence_refs = list(dict.fromkeys([
                event.event_id, event_digest, *event.proof_receipt_ids, *event.release_receipt_ids,
            ]))[:10]
            item = {
                "id": "", "kind": kind, "severity": severity, "requires_action": requires_action,
                "project_id": project_id, "ctrl_id": ctrl_id, "task_id": event.task_id,
                "subject_id": event.block_id, "owner_id": event.owner_id,
                "revision": event.scope_version, "source_event_id": event.event_id,
                "source_event_digest": event_digest, "material_sequence": int(record["event_seq"]),
                "observed_at_ms": event.observed_at_ms, "sentence": sentence,
                "action_target": {
                    "view": view, "project_id": project_id, "ctrl_id": ctrl_id,
                    "task_id": event.task_id, "subject_id": event.block_id,
                },
                "evidence_refs": evidence_refs,
            }
            item["id"] = _notification_identity(principal_id, item)
            candidates.append(item)
        conflicted = {event_id for event_id, digests in event_digests.items() if len(digests) > 1}
        items = {
            item["id"]: item for item in candidates if item["source_event_id"] not in conflicted
        }
        return sorted(
            items.values(), key=lambda item: (item["material_sequence"], item["id"]), reverse=True,
        ), truncated

    def notification_feed(self, ctrl_id: str, project_id: str) -> dict[str, Any]:
        ctrl_id = _auto_id(ctrl_id, "ctrl_id")
        project_id = _auto_id(project_id, "project_id")
        items, source_truncated = self._notification_items(ctrl_id, project_id)
        principal_id = self._notification_principal()
        current = {item["id"]: item for item in items}
        seen = self.store.notification_seen(
            principal_id=principal_id, ctrl_id=ctrl_id, project_id=project_id, items=current,
        )
        seen_ids = {receipt["notification_id"] for receipt in seen}
        unread = [item for item in items if item["id"] not in seen_ids]
        recent_seen = []
        for receipt in sorted(
            seen, key=lambda value: (value["seen_at_ms"], value["notification_id"]), reverse=True,
        ):
            item = current.get(receipt["notification_id"])
            if item is None:
                continue
            if (
                receipt["source_event_id"] != item["source_event_id"]
                or receipt["source_event_digest"] != item["source_event_digest"]
            ):
                raise ConsoleError("notification seen receipt conflicts with retained source evidence")
            recent_seen.append({**item, "seen_at_ms": receipt["seen_at_ms"]})
            if len(recent_seen) == NOTIFICATION_RECENT_SEEN_LIMIT:
                break
        return {
            "ok": True, "schema_version": 1, "principal_id": principal_id,
            "ctrl_id": ctrl_id, "project_id": project_id,
            "unread": unread[:NOTIFICATION_UNREAD_LIMIT], "recent_seen": recent_seen,
            "retention": {
                "seen_basis": "current_eligible_ledger_projection",
                "seen_count": len(seen),
                "unread_limit": NOTIFICATION_UNREAD_LIMIT,
                "recent_seen_limit": NOTIFICATION_RECENT_SEEN_LIMIT,
                "unread_truncated": len(unread) > NOTIFICATION_UNREAD_LIMIT,
                "seen_truncated": len(seen) > NOTIFICATION_RECENT_SEEN_LIMIT,
                "source_scan_truncated": source_truncated,
            },
            "source": "canonical_ledger_material_events",
            "claim_limit": (
                "Notifications link to authoritative surfaces only; they do not execute work, grant approval, "
                "or infer state from prose. Approval and asset classes remain absent until typed Ledger events exist."
            ),
        }

    def mark_notifications_seen(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or set(payload) != {"ctrl_id", "project_id", "notification_ids"}:
            raise ConsoleError("notification acknowledgement requires exact CTRL, project, and notification IDs")
        ctrl_id = _auto_id(payload.get("ctrl_id"), "ctrl_id")
        project_id = _auto_id(payload.get("project_id"), "project_id")
        notification_ids = payload.get("notification_ids")
        if (
            not isinstance(notification_ids, list) or not 1 <= len(notification_ids) <= 64
            or any(not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity) for identity in notification_ids)
            or len(notification_ids) != len(set(notification_ids))
        ):
            raise ConsoleError("notification_ids must be 1-64 unique SHA-256 identities")
        items, _ = self._notification_items(ctrl_id, project_id)
        principal_id = self._notification_principal()
        result = self.store.mark_notifications_seen(
            principal_id=principal_id, ctrl_id=ctrl_id, project_id=project_id,
            items={item["id"]: item for item in items}, notification_ids=notification_ids,
            now_ms=int(time.time() * 1000),
        )
        return {"ok": True, **result, "feed": self.notification_feed(ctrl_id, project_id)}

    def _require_role_avatar(self, digest: str) -> None:
        if digest in {item["avatar_asset_digest"] for item in self.builtin_role_manifests}:
            return
        root = self.codex_home / PROOF_MEDIA_ROOT
        if _is_reparse_point(root) or not root.is_dir():
            raise ConsoleError("role avatar digest is not retained in immutable Assets storage")
        try:
            resolved_root = root.resolve(strict=True)
        except OSError as error:
            raise ConsoleError("role avatar digest is not retained in immutable Assets storage") from error
        if _is_reparse_point(resolved_root):
            raise ConsoleError("role avatar digest is not retained in immutable Assets storage")
        candidates = sorted(root.glob(f"{digest}.*"))
        if len(candidates) != 1:
            raise ConsoleError("role avatar digest is not retained in immutable Assets storage")
        candidate = candidates[0]
        if _is_reparse_point(candidate):
            raise ConsoleError("role avatar digest is not retained in immutable Assets storage")
        try:
            resolved_candidate = candidate.resolve(strict=True)
            if not resolved_candidate.is_relative_to(resolved_root) or _is_reparse_point(resolved_candidate):
                raise ConsoleError("role avatar digest is not retained in immutable Assets storage")
            _media_metadata(str(resolved_candidate), digest, allowed_root=resolved_root)
        except (ConsoleError, OSError) as error:
            raise ConsoleError("role avatar digest is not retained in immutable Assets storage") from error

    def role_manifest_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        unknown = set(payload) - ROLE_COMMAND_FIELDS
        if unknown:
            raise ConsoleError(f"role manifest command contains unsupported field(s): {', '.join(sorted(unknown))}")
        command, role_id = str(payload.get("command") or ""), str(payload.get("role_id") or "")
        if command not in {"ROLE_MANIFEST_CREATE", "ROLE_MANIFEST_REVISE", "ROLE_MANIFEST_RESET"}:
            raise ConsoleError("role manifest command is invalid")
        try:
            projection = self.progress_ledger.project_role_manifests(self.builtin_role_manifests)
            current = next((item for item in projection["roles"] if item["id"] == role_id), None)
            builtins = {item["id"]: item for item in self.builtin_role_manifests}
            provenance = _safe_metadata_text(payload.get("provenance"), "provenance", maximum=256)
            if command == "ROLE_MANIFEST_RESET":
                if role_id not in builtins:
                    raise ProgressEventError("only a built-in role can be reset")
                manifest = builtins[role_id]
            else:
                source = "user_override" if role_id in builtins else "custom"
                manifest = build_role_manifest(role_id, payload.get("manifest"), source, [provenance])
                if manifest["id"].casefold() == "critic":
                    raise ProgressEventError("Critic is retained as history and cannot be established as a current role")
            event = role_material_event(
                command, event_id=payload.get("event_id"), dedupe_key=payload.get("dedupe_key"),
                role_id=role_id, manifest=manifest,
                expected_active_version=payload.get("expected_active_version"), assignment_task_id=None,
                provenance=provenance, observed_at_ms=payload.get("observed_at_ms"),
            )
            if current and event["event_id"] in current["source_event_ids"]:
                result = self.progress_ledger.append(event)
            else:
                expected = payload.get("expected_active_version")
                if command == "ROLE_MANIFEST_CREATE" and current is not None:
                    raise ConsoleConflict("role manifest create cannot replace an existing role")
                if command != "ROLE_MANIFEST_CREATE" and (current is None or expected != current["active_version"]):
                    raise ProgressEventError("role manifest expected active version is stale")
                self._require_role_avatar(manifest["avatar_asset_digest"])
                result = self.progress_ledger.append(event)
            receipt = {
                **result, "command": command, "role_id": role_id,
                "active_version": manifest["version"], "event_id": event["event_id"],
            }
            return {"ok": True, "receipt": receipt, "projection": self.progress_ledger.project_role_manifests(self.builtin_role_manifests)}
        except ProgressEventError as error:
            if any(word in str(error) for word in ("stale", "conflicts", "already bound")):
                raise ConsoleConflict(str(error)) from error
            raise ConsoleError(str(error)) from error

    def bind_role_assignment(
        self, task_id: str, role_id: str, event_id: str, dedupe_key: str,
        provenance: str, observed_at_ms: int,
    ) -> dict[str, Any]:
        try:
            projection = self.progress_ledger.project_role_manifests(self.builtin_role_manifests)
            role = next((item for item in projection["roles"] if item["id"] == role_id), None)
            if role is None:
                raise ProgressEventError("role assignment references an unknown role")
            existing = next((item for item in projection["assignments"] if item["task_id"] == task_id), None)
            if existing:
                if (existing["role_id"], existing["manifest_version"]) == (role_id, role["active_version"]):
                    return {"status": "unchanged", **existing}
                raise ProgressEventError("task role assignment is already bound")
            manifest = {key: value for key, value in next(item for item in role["versions"] if item["active"]).items() if key != "active"}
            return self.progress_ledger.append(role_material_event(
                "ROLE_ASSIGNMENT_BOUND", event_id=event_id, dedupe_key=dedupe_key,
                role_id=role_id, manifest=manifest, expected_active_version=role["active_version"],
                assignment_task_id=task_id, provenance=provenance, observed_at_ms=observed_at_ms,
            ))
        except ProgressEventError as error:
            raise ConsoleError(str(error)) from error

    def proof_media_item(self, evidence_id: str, digest: str) -> dict[str, Any]:
        return self.store.proof_media_item(
            evidence_id,
            digest,
            allowed_root=self.codex_home / PROOF_MEDIA_ROOT,
        )

    def proof_cursor(self) -> dict[str, Any]:
        self._ingest_proof_events_if_changed()
        return self.store.proof_cursor()

    def proof_sequence(self) -> int:
        return int(self.proof_cursor()["sequence"])

    def register_proof(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = _safe_metadata_text(payload.get("task_id"), "task_id", maximum=256)
        overview = self._host_overview()
        node = next(
            (
                item for item in overview.get("nodes", [])
                if str(item.get("id")) == task_id and not item.get("virtual") and item.get("project_id")
            ),
            None,
        )
        if node is None:
            raise ConsoleError("proof media requires an observed task")
        safe_payload = {
            **payload,
            "task_id": task_id,
            "project_id": str(node["project_id"]),
            "disposition": "PENDING",
            "receipt": f"ctrl-evidence:registered:{task_id}",
        }
        result = self.store.record_proof_media(
            safe_payload,
            now_ms=int(time.time() * 1000),
            allowed_root=self.codex_home / PROOF_MEDIA_ROOT,
        )
        try:
            self.observe_once("proof")
        except (ConsoleError, OSError, sqlite3.Error):
            pass
        with self.overview_lock:
            self._store_generation += 1
        return result

    def storage(self) -> dict[str, Any]:
        storage = self.store.storage_stats()
        proof = proof_storage_stats(self.codex_home)
        return {
            **storage,
            "database_bytes": storage["bytes"],
            "proof_bytes": proof["bytes"],
            "proof_files": proof["files"],
            "bytes": storage["bytes"] + proof["bytes"],
        }

    def diagnostics(self) -> dict[str, Any]:
        stats = self.storage()
        try:
            load_config(self.config_path)
            config_valid = True
        except ConsoleError:
            config_valid = False
        now_ms = int(time.time() * 1000)
        stored_latest = self.store.latest_diagnostics()
        latest = _diagnostic_no_data(now_ms) if stored_latest is None else _diagnostic_record_for_response(stored_latest, now_ms)
        return {
            "ok": True,
            "service": "swarm-console",
            "host_metadata_read_only": True,
            "config_valid": config_valid,
            "storage": {
                "path": stats["path"],
                "bytes": stats["bytes"],
                "retention_days": stats["retention_days"],
            },
            "latest": latest,
            "health": {
                "auto_enabled": self._auto_health_enabled(),
                "incidents": self.store.health_incidents(),
                "open_requests": self.store.health_requests(status="OPEN"),
            },
            "usage_consumed": False,
            "usage_source": "Console diagnostics does not collect model usage.",
        }

    def _auto_health_enabled(self) -> bool:
        try:
            _, effective, _ = load_config(self.config_path)
            return bool(effective.get("monitoring", {}).get("auto_health_enabled", False))
        except ConsoleError:
            return False

    def diagnostics_history(self, limit: int = 120) -> list[dict[str, Any]]:
        now_ms = int(time.time() * 1000)
        return [
            _diagnostic_record_for_response(record, now_ms)
            for record in self.store.diagnostics_history(limit=limit)
        ]

    def health_incidents(self, state: str | None = None) -> list[dict[str, Any]]:
        return self.store.health_incidents(state=state)

    def health_requests(self, status: str | None = None) -> list[dict[str, Any]]:
        return self.store.health_requests(status=status)

    def health_settings(self) -> dict[str, Any]:
        return {
            "enabled": self._auto_health_enabled(),
            "default": False,
            "thresholds": {
                "cpu_degraded_percent": HEALTH_THRESHOLDS["cpu_degraded"],
                "cpu_critical_percent": HEALTH_THRESHOLDS["cpu_critical"],
                "memory_degraded_percent": HEALTH_THRESHOLDS["memory_degraded"],
                "memory_critical_percent": HEALTH_THRESHOLDS["memory_critical"],
                "disk_degraded_free_bytes": HEALTH_THRESHOLDS["disk_degraded_bytes"],
                "disk_critical_free_bytes": HEALTH_THRESHOLDS["disk_critical_bytes"],
                "sustain_seconds": HEALTH_SUSTAIN_SECONDS,
                "recovery_seconds": HEALTH_RECOVERY_SECONDS,
                "cooldown_seconds": HEALTH_COOLDOWN_SECONDS,
            },
            "claim_limit": "Auto Health creates advisory requests only; active CTRL owns task creation through host APIs.",
        }

    def update_health_settings(self, enabled: Any) -> dict[str, Any]:
        if not isinstance(enabled, bool):
            raise ConsoleError("enabled must be a boolean")
        with self.write_lock:
            result = update_config(self.config_path, {"monitoring.auto_health_enabled": enabled})
        with self.overview_lock:
            self._overview_fingerprint = None
            self._view_fingerprint = None
        return {"enabled": enabled, "config": result}

    def claim_health_request(self, request_id: str) -> dict[str, Any]:
        return self.store.claim_health_request(request_id, now_ms=int(time.time() * 1000))

    def resolve_health_request(self, request_id: str, outcome: str, receipt: str) -> dict[str, Any]:
        return self.store.resolve_health_request(
            request_id,
            outcome=outcome,
            receipt=receipt,
            now_ms=int(time.time() * 1000),
        )

    def _ctrl_context(self, ctrl_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        ctrl_id = _safe_metadata_text(ctrl_id, "ctrl_id", maximum=256)
        node = next(
            (item for item in self._host_overview()["nodes"] if item["id"] == ctrl_id and item["role"] == "ctrl"),
            None,
        )
        if node is None:
            raise ConsoleError("CTRL id must be an observed host CTRL")
        module, effective, _ = load_config(self.config_path)
        return module, effective, self.store.get_ctrl_override(ctrl_id)

    def ctrl_settings(self, ctrl_id: str) -> dict[str, Any]:
        module, effective, overlay = self._ctrl_context(ctrl_id)
        global_assignment = module.resolve_role_assignment(effective, "ctrl")
        override = overlay["override"]
        try:
            assignment = module.resolve_role_assignment(
                effective,
                "ctrl",
                explicit_model=override.get("model"),
                explicit_reasoning=override.get("reasoning"),
            )
        except Exception as exc:
            raise ConsoleError(f"CTRL override is not valid for the canonical resolver: {exc}") from exc
        return {
            "ctrl_id": overlay["ctrl_id"],
            "revision": overlay["revision"],
            "customized": bool(override),
            "global_defaults": {
                "model": global_assignment["model"],
                "reasoning": global_assignment["reasoning"],
            },
            "override": override,
            "effective": {
                "model": assignment["model"],
                "reasoning": assignment["reasoning"],
            },
            "editable_fields": sorted(CTRL_OVERRIDE_FIELDS),
            "reset_semantics": "Delete the per-CTRL overlay to inherit global defaults.",
        }

    def update_ctrl_settings(self, ctrl_id: str, changes: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        module, effective, overlay = self._ctrl_context(ctrl_id)
        candidate = {**overlay["override"], **changes}
        try:
            module.resolve_role_assignment(
                effective,
                "ctrl",
                explicit_model=candidate.get("model"),
                explicit_reasoning=candidate.get("reasoning"),
            )
        except Exception as exc:
            raise ConsoleError(f"CTRL override is not valid for the canonical resolver: {exc}") from exc
        result = self.store.update_ctrl_override(
            ctrl_id,
            changes,
            expected_revision=expected_revision,
            now_ms=int(time.time() * 1000),
        )
        with self.overview_lock:
            self._store_generation += 1
        return self.ctrl_settings(result["ctrl_id"])

    def reset_ctrl_settings(self, ctrl_id: str, expected_revision: int) -> dict[str, Any]:
        self._ctrl_context(ctrl_id)
        result = self.store.reset_ctrl_override(ctrl_id, expected_revision=expected_revision)
        with self.overview_lock:
            self._store_generation += 1
        return {**self.ctrl_settings(ctrl_id), "reset": result["reset"]}

    def clear_history(self) -> dict[str, Any]:
        with self.write_lock, self.proof_lock:
            proof = clear_proof_storage(self.codex_home)
            result = self.store.clear_history()
        with self.overview_lock:
            self._store_generation += 1
        return {**result, "proof": proof}

    def restore_defaults(self) -> dict[str, Any]:
        with self.write_lock:
            config = restore_config_defaults(self.config_path)
            reset_count = self.store.reset_overrides()
        with self.overview_lock:
            self._store_generation += 1
            self._overview_fingerprint = None
            self._view_fingerprint = None
        return {"config": config, "ctrl_overrides_reset": reset_count}

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


class Handler(BaseHTTPRequestHandler):
    server: SwarmHTTPServer
    _response_committed = False

    def send_response(self, code: int, message: str | None = None) -> None:
        self._response_committed = False
        super().send_response(code, message)

    def end_headers(self) -> None:
        # Once header flushing begins, a second HTTP response is never valid.
        self._response_committed = True
        super().end_headers()

    @staticmethod
    def _client_disconnected(error: OSError) -> bool:
        return (
            isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError))
            or getattr(error, "winerror", None) in {10053, 10054}
        )

    def _post_commit_disconnect(self, error: OSError) -> bool:
        return self._response_committed and self._client_disconnected(error)
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

    def _peer_is_trusted_local(self) -> bool:
        if self._peer_is_loopback():
            return True
        if os.environ.get("SWARM_CONSOLE_DOCKER_LOOPBACK") != "1":
            return False
        peer = str(self.client_address[0]).split("%", 1)[0]
        try:
            return ipaddress.ip_address(peer).is_private
        except ValueError:
            return False

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        except OSError as error:
            if self._post_commit_disconnect(error):
                return
            raise

    def _registered_media(self, item: dict[str, Any]) -> None:
        path = item["path"]
        with path.open("rb") as stream:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", item["media_type"])
            self.send_header("Content-Length", str(item["size_bytes"]))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                self.wfile.write(chunk)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _payload(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ConsoleError("invalid content length") from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ConsoleError("request body must be 1-65536 bytes")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ConsoleError("request body must be a JSON object")
        return payload

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
            self._peer_is_trusted_local()
            and self._same_origin()
            and secrets.compare_digest(self.headers.get("X-Swarm-Token", ""), self.server.app.token)
        )

    def _authorized_auto(self) -> bool:
        return (
            self._peer_is_loopback()
            and self._same_origin()
            and secrets.compare_digest(self.headers.get("X-Swarm-Token", ""), self.server.app.token)
        )

    def _bootstrap_payload(self) -> dict[str, Any]:
        local = self._peer_is_trusted_local()
        return {
            "ok": True,
            "token": self.server.app.token if local else "",
            "config_path": str(self.server.app.config_path) if local else "",
            "local_only": local,
            "read_only": not local,
        }

    def _config_payload(self) -> dict[str, Any]:
        payload = redacted_config_snapshot(self.server.app.config_path)
        if not self._peer_is_trusted_local():
            payload["path"] = ""
            payload["read_only"] = True
        return payload

    def do_GET(self) -> None:  # noqa: N802
        self._response_committed = False
        if not self._host_allowed():
            self._error(HTTPStatus.FORBIDDEN, "SWARM Console accepts requests from this device only")
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
        try:
            if path == "/healthz":
                static_ready = all((STATIC_ROOT / filename).is_file() for filename, _ in STATIC_FILES.values())
                asset_ready = all(asset_path.is_file() for asset_path, _ in STATIC_ASSETS.values())
                ready = static_ready and asset_ready
                self._json(
                    HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ok": ready, "service": "swarm-console", "instance_id": INSTANCE_ID},
                )
                return
            if path == "/api/bootstrap":
                self._json(HTTPStatus.OK, self._bootstrap_payload())
                return
            if path == "/api/profile":
                self._json(HTTPStatus.OK, self.server.app.profile_presentation())
                return
            if path == "/api/auto":
                if not self._authorized_auto():
                    self._error(HTTPStatus.FORBIDDEN, "Auto status requires local same-origin authorization")
                    return
                self._json(
                    HTTPStatus.OK,
                    self.server.app.auto_status(query.get("ctrl_id", ""), query.get("project_id", "")),
                )
                return
            if path == "/api/notifications":
                if not self._authorized_write():
                    self._error(HTTPStatus.FORBIDDEN, "notification feed requires local same-origin authorization")
                    return
                if set(query) != {"ctrl_id", "project_id"}:
                    self._error(HTTPStatus.BAD_REQUEST, "notification feed requires exact ctrl_id and project_id")
                    return
                self._json(
                    HTTPStatus.OK,
                    self.server.app.notification_feed(query["ctrl_id"], query["project_id"]),
                )
                return
            if path == "/api/run-log":
                if not self._authorized_write():
                    self._error(HTTPStatus.FORBIDDEN, "run log requires local same-origin authorization")
                    return
                allowed = {"ctrl_id", "project_id", "agent_id", "after_cursor"}
                if "ctrl_id" not in query or not set(query).issubset(allowed):
                    self._error(HTTPStatus.BAD_REQUEST, "run log requires ctrl_id and bounded filters")
                    return
                try:
                    after_cursor = int(query.get("after_cursor", "0"))
                except ValueError as exc:
                    raise ConsoleError("after_cursor must be a non-negative Ledger sequence") from exc
                self._json(
                    HTTPStatus.OK,
                    self.server.app.run_log(
                        query["ctrl_id"],
                        project_id=query.get("project_id"),
                        agent_id=query.get("agent_id"),
                        after_cursor=after_cursor,
                    ),
                )
                return
            if path == "/api/overview":
                self.server.app.mark_presence()
                self._json(
                    HTTPStatus.OK,
                    self.server.app.overview(query.get("project_id")),
                )
                return
            if path == "/api/usage-history":
                try:
                    hours = int(query.get("hours", "24"))
                except ValueError as exc:
                    raise ConsoleError("hours must be one of 1, 12, or 24") from exc
                try:
                    target_reset_at_ms = (
                        int(query["target_reset_at_ms"])
                        if "target_reset_at_ms" in query
                        else None
                    )
                    remaining_token_budget = (
                        int(query["remaining_token_budget"])
                        if "remaining_token_budget" in query
                        else None
                    )
                except ValueError as exc:
                    raise ConsoleError(
                        "target_reset_at_ms and remaining_token_budget must be integers"
                    ) from exc
                self._json(
                    HTTPStatus.OK,
                    self.server.app.usage_history(
                        project_id=query.get("project_id"),
                        ctrl_id=query.get("ctrl_id"),
                        hours=hours,
                        target_reset_at_ms=target_reset_at_ms,
                        remaining_token_budget=remaining_token_budget,
                    ),
                )
                return
            if path == "/api/progress":
                self._json(
                    HTTPStatus.OK,
                    self.server.app.progress_summary(
                        project_id=query.get("project_id"),
                        ctrl_id=query.get("ctrl_id"),
                    ),
                )
                return
            if path == "/api/project-progress-feed":
                try:
                    after_cursor = int(query.get("after_cursor", "0"))
                except ValueError as exc:
                    raise ConsoleError("after_cursor must be a nonnegative integer") from exc
                if after_cursor < 0:
                    raise ConsoleError("after_cursor must be a nonnegative integer")
                self._json(
                    HTTPStatus.OK,
                    self.server.app.project_progress_feed(
                        query.get("project_id", ""),
                        after_cursor=after_cursor,
                    ),
                )
                return
            if path == "/api/project-progress":
                self._json(
                    HTTPStatus.OK,
                    self.server.app.measurable_progress(query.get("project_id", "")),
                )
                return
            if path == "/api/role-manifests":
                self._json(HTTPStatus.OK, self.server.app.role_manifest_projection())
                return
            if path == "/api/skills":
                self._json(
                    HTTPStatus.OK,
                    self.server.app.skill_settings(
                        project_id=query.get("project_id"),
                        ctrl_id=query.get("ctrl_id"),
                        role=query.get("role"),
                        task_kind=query.get("task_kind"),
                    ),
                )
                return
            if path == "/api/proof-feed":
                self._json(
                    HTTPStatus.OK,
                    self.server.app._proof_feed_projection(
                        project_id=query.get("project_id"),
                        task_id=query.get("task_id"),
                    ),
                )
                return
            if path.startswith("/api/proof-media/"):
                if self.headers.get("Origin") and not self._same_origin():
                    self._error(HTTPStatus.FORBIDDEN, "same-origin proof media request required")
                    return
                evidence_id = unquote(path[len("/api/proof-media/") :]).strip("/")
                item = self.server.app.proof_media_item(evidence_id, query.get("digest", ""))
                self._registered_media(item)
                return
            if path == "/api/storage":
                self._json(HTTPStatus.OK, {"ok": True, **self.server.app.storage()})
                return
            if path == "/api/diagnostics":
                self._json(HTTPStatus.OK, self.server.app.diagnostics())
                return
            if path == "/api/diagnostics/history":
                self._json(HTTPStatus.OK, {
                    "ok": True,
                    "items": self.server.app.diagnostics_history(int(query.get("limit", "120"))),
                    "usage_consumed": False,
                })
                return
            if path == "/api/health/incidents":
                self._json(HTTPStatus.OK, {
                    "ok": True,
                    "items": self.server.app.health_incidents(query.get("state")),
                    "usage_consumed": False,
                })
                return
            if path == "/api/health/requests":
                self._json(HTTPStatus.OK, {
                    "ok": True,
                    "items": self.server.app.health_requests(query.get("status")),
                    "usage_consumed": False,
                })
                return
            if path == "/api/health/settings":
                self._json(HTTPStatus.OK, {"ok": True, **self.server.app.health_settings()})
                return
            if path == "/api/ctrl-settings":
                ctrl_id = query.get("ctrl_id", "")
                if not ctrl_id:
                    self._error(HTTPStatus.BAD_REQUEST, "ctrl_id is required")
                    return
                self._json(HTTPStatus.OK, {"ok": True, **self.server.app.ctrl_settings(ctrl_id)})
                return
            if path == "/api/presence":
                self._json(HTTPStatus.OK, self.server.app.presence())
                return
            if path == "/api/config":
                self._json(HTTPStatus.OK, self._config_payload())
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
            if self._response_committed:
                if isinstance(exc, OSError) and self._client_disconnected(exc):
                    return
                raise
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        self._response_committed = False
        if not self._host_allowed():
            self._error(HTTPStatus.FORBIDDEN, "invalid console host")
            return
        if not self._peer_is_trusted_local():
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
            self._json(HTTPStatus.OK, {"ok": True, "proof_sequence": self.server.app.proof_sequence()})
            return
        if path == "/api/launch-claim":
            self._json(HTTPStatus.OK, self.server.app.claim_portal_open())
            return
        try:
            if path == "/api/config":
                payload = self._payload()
                changes = payload.get("changes")
                if not isinstance(changes, dict):
                    raise ConsoleError("changes must be an object")
                with self.server.app.write_lock:
                    result = update_config(self.server.app.config_path, changes)
                self._json(HTTPStatus.OK, {"ok": True, **result})
                return
            if path == "/api/auto":
                if not self._authorized_auto():
                    self._error(HTTPStatus.FORBIDDEN, "Auto command requires strict loopback authorization")
                    return
                with self.server.app.write_lock:
                    result = self.server.app.auto_command(self._payload())
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/notifications/seen":
                with self.server.app.write_lock:
                    result = self.server.app.mark_notifications_seen(self._payload())
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/role-manifests/commands":
                with self.server.app.write_lock:
                    result = self.server.app.role_manifest_command(self._payload())
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/skills/inheritance":
                payload = self._payload()
                result = self.server.app.update_skill_settings(
                    payload.get("scope_type"), payload.get("scope_id"),
                    payload.get("changes"), payload.get("expected_revision"),
                )
                self._json(HTTPStatus.OK, {"ok": True, "overlay": result})
                return
            if path == "/api/skills/inheritance/reset":
                payload = self._payload()
                result = self.server.app.reset_skill_settings(
                    payload.get("scope_type"), payload.get("scope_id"), payload.get("expected_revision"),
                )
                self._json(HTTPStatus.OK, {"ok": True, "reset": result})
                return
            if path == "/api/evidence":
                result = self.server.app.register_proof(self._payload())
                self._json(HTTPStatus.OK, {"ok": True, "proof": result})
                return
            if path == "/api/health/settings":
                payload = self._payload()
                self._json(HTTPStatus.OK, {"ok": True, **self.server.app.update_health_settings(payload.get("enabled"))})
                return
            if path.startswith("/api/health/requests/") and path.endswith("/claim"):
                request_id = path[len("/api/health/requests/") : -len("/claim")].strip("/")
                self._json(HTTPStatus.OK, {"ok": True, **self.server.app.claim_health_request(request_id)})
                return
            if path.startswith("/api/health/requests/") and path.endswith("/resolve"):
                request_id = path[len("/api/health/requests/") : -len("/resolve")].strip("/")
                payload = self._payload()
                self._json(HTTPStatus.OK, {
                    "ok": True,
                    **self.server.app.resolve_health_request(
                        request_id, payload.get("outcome", ""), payload.get("receipt", "")
                    ),
                })
                return
            if path == "/api/ctrl-settings":
                payload = self._payload()
                ctrl_id = payload.get("ctrl_id")
                changes = payload.get("changes")
                expected_revision = payload.get("expected_revision")
                if not isinstance(changes, dict):
                    raise ConsoleError("changes must be an object")
                result = self.server.app.update_ctrl_settings(ctrl_id, changes, expected_revision)
                self._json(HTTPStatus.OK, {"ok": True, **result})
                return
            if path == "/api/ctrl-settings/reset":
                payload = self._payload()
                result = self.server.app.reset_ctrl_settings(
                    payload.get("ctrl_id"), payload.get("expected_revision")
                )
                self._json(HTTPStatus.OK, {"ok": True, **result})
                return
            if path in {"/api/logs/clear", "/api/storage/clear"}:
                self._json(HTTPStatus.OK, self.server.app.clear_history())
                return
            if path == "/api/settings/restore":
                self._json(HTTPStatus.OK, {"ok": True, **self.server.app.restore_defaults()})
                return
            self._error(HTTPStatus.NOT_FOUND, "not found")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, f"invalid JSON: {exc}")
        except ConsoleConflict as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except ConsoleError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except (OSError, sqlite3.Error) as exc:
            if self._response_committed:
                if isinstance(exc, OSError) and self._client_disconnected(exc):
                    return
                raise
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--open", action="store_true", help="open the console in the default browser")
    return parser.parse_args()


def static_bundle_advisory(static_root: Path = STATIC_ROOT) -> str | None:
    required = {filename for filename, _ in STATIC_FILES.values()}
    missing = sorted(filename for filename in required if not (static_root / filename).is_file())
    if not missing:
        return None
    return "SWARM Console cache is stale or incomplete; reinstall the current SWARM plugin or start from its active cache."


def main() -> int:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        print("SWARM Console only supports loopback or Docker's 0.0.0.0 bind", file=sys.stderr)
        return 2
    advisory = static_bundle_advisory()
    if advisory:
        print(advisory, file=sys.stderr)
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
    app.start_observer()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop_observer()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
