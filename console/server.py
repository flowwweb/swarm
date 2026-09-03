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
import tomllib
import webbrowser
import uuid
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
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))
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
    load_builtin_role_avatar_assets,
    load_builtin_role_manifests,
    resolve_role_avatar,
    resolve_role_lucide_icon,
    role_manifest_reference,
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
from project_model_views import (  # noqa: E402
    ProjectModelError,
    parse_project_brief_markdown,
    project_schema1_views,
)

INSTANCE_ID = hashlib.sha256(str(CONSOLE_ROOT.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
SERVER_BUILD_ID = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
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
PROJECT_BRIEF_MARKER = "swarm-project-brief:schema=1"
PROJECT_BRIEF_REQUIRED_FIELDS = frozenset({
    "schema_version", "updated_at", "project", "users_outcomes", "objective", "repo",
    "authority", "milestones", "decisions", "ownership", "proof_acceptance", "risks_blockers", "links",
})
PROJECT_SETTING_FIELDS = frozenset({"inheritance_enabled", "profile", "preferred_ids"})
PROJECT_VIEW_RENDERERS = {
    "canvas": frozenset({"network", "spatial", "freeform"}),
    "table": frozenset({"entities", "records", "log"}),
    "timeline": frozenset({"ordered", "sessions", "milestones"}),
    "gallery": frozenset({"grid", "list"}),
    "compare": frozenset({"single", "side_by_side"}),
    "document": frozenset({"blocks"}),
}
PROJECT_VIEW_SOURCE_KINDS = frozenset({
    "coverage.screens", "graph.json", "graph.mermaid", "document.blocks", "document.text", "events.timeline",
})
PROJECT_VIEW_ACTIONS = frozenset({
    "open_artifact", "open_entity", "request_review", "send_feedback",
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
HEALTH_CHECK_STATUSES = frozenset({"PASS", "WARN", "FAIL", "UNKNOWN"})
AUTO_REPAIR_SETTING_KEY = "monitoring.auto_health_enabled"
AUTO_REPAIR_LABEL = "Auto fix"
AUTO_REPAIR_HELP = "SWARM attempts to recover from issues automatically. This may start repair tasks and increase usage."
CONFIG_CONTRACT_VERSION = 1
CONFIG_EVENT_KIND = "CONFIG_MUTATION"
CONFIG_TRANSACTION_PREPARED = "PREPARED"
CONFIG_TRANSACTION_COMMITTED = "COMMITTED"
CONFIG_TRANSACTION_ABORTED = "ABORTED"
CONFIG_TEXT_MAX_BYTES = MAX_BODY_BYTES
CONFIG_PRIVATE_PATHS = frozenset({"feedback.destination"})
CONFIG_PRIVATE_SEGMENTS = frozenset({
    "secret", "secrets", "token", "password", "credential", "credentials",
    "api_key", "apikey", "private_key", "privatekey",
})
CONFIG_DEPRECATED_PATHS = frozenset({
    "fast_mode", "current_mode", "execution.service_tier", "execution.current_mode",
    "lifecycle.archive_completed_tasks", "portfolio.title_prefix", "role_icons.task_choices",
})
CONFIG_DEPRECATED_VALUES = frozenset({("efficiency.mode", "FAST")})
CONFIG_INTERNAL_PATHS = frozenset({"schema_version", "recovery.max_attempts"})
CONFIG_HIGH_VALUE_PATHS = frozenset({
    "automation.mode", "execution.fast_mode", "execution.usage_profile",
    "execution.min_reasoning", "execution.max_reasoning", "execution.usage_saver",
    "monitoring.auto_health_enabled", "lifecycle.task_lifetime_hours",
    "role_icons.enabled", "console.auto_start", "console.open_on_start", "console.project_progress_feed_enabled",
    "console.project_progress_feed_lines",
})
CONFIG_RESTART_PATHS = frozenset({"console.open_on_start"})
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
ASSET_STATUSES = frozenset({"queued", "generating", "validating", "ready", "failed", "cancelled"})
ASSET_ACTIVE_STATUSES = frozenset({"queued", "generating", "validating"})
ASSET_TERMINAL_STATUSES = frozenset({"ready", "failed", "cancelled"})
ASSET_GENERATION_TRANSITIONS = {
    "queued": frozenset({"generating", "failed"}),
    "generating": frozenset({"generating", "validating", "failed"}),
    "validating": frozenset({"validating", "failed"}),
    "ready": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
ASSET_ERROR_CLASSES = frozenset({
    "PROVIDER_UNAVAILABLE", "VALIDATION_FAILED", "MISSING_OUTPUT",
    "AUTHORIZATION_DENIED", "RUNTIME_UNAVAILABLE", "UNKNOWN_FAILURE",
})
ASSET_EVENT_KIND = "ASSET_TRANSITION"
ASSET_EVENT_CURSOR_KEY = "asset_event_cursor_v1"
ASSET_RETENTION_POLICY = "manual/unconfigured"
ASSET_MAX_JSON_BYTES = 16 * 1024
ASSET_PRESENTATION_FIELDS = frozenset({"display_name", "kind", "description"})
ASSET_JOB_METADATA_FIELDS = frozenset({"provider", "model", "mode", "option", "attempt"})
ASSET_PROVENANCE_FIELDS = frozenset({"source", "receipt", "parent_asset_id", "admission"})
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
    "/assets/swarm-guided-tour-slide1.png": ("swarm-guided-tour-slide1.png", "image/png"),
    "/assets/swarm-guided-tour-role-group.png": ("swarm-guided-tour-role-group.png", "image/png"),
    "/assets/swarm-guided-tour-project-tool.png": ("swarm-guided-tour-project-tool.png", "image/png"),
    "/assets/swarm-offline-disconnected.png": ("swarm-offline-disconnected.png", "image/png"),
    "/assets/swarm-offline-disconnected.webp": ("swarm-offline-disconnected.webp", "image/webp"),
    "/assets/swarm-state-mascot-concerned.png": ("swarm-state-mascot-concerned.png", "image/png"),
    "/assets/swarm-state-mascot-concerned.webp": ("swarm-state-mascot-concerned.webp", "image/webp"),
    "/assets/support-caricature-light.webp": ("support-caricature-light.webp", "image/webp"),
}
STATIC_ASSETS = {
    "/assets/swarm-wordmark.png": (
        PLUGIN_ROOT / "skills" / "swarm" / "assets" / "swarm-wordmark.png",
        "image/png",
    ),
}

# Populated from the canonical config module after its loader is available.  It
# remains a compatibility view for the older changes-based helper; it is not a
# second schema or defaults table.
EDITABLE_SETTINGS: dict[str, type] = {}


class ConsoleError(RuntimeError):
    """Expected, user-visible console failure."""


class NotAcceptableError(ConsoleError):
    """The requested representation set excludes every supported image type."""


def _preferred_image_media_type(accept: str) -> str:
    value = str(accept or "").strip().casefold()
    if not value:
        return "image/png"
    supported = ("image/avif", "image/webp", "image/png")
    quality: dict[str, tuple[int, float]] = {media_type: (-1, 0.0) for media_type in supported}
    for item in value.split(","):
        parts = [part.strip() for part in item.split(";")]
        media_range = parts[0]
        q = 1.0
        for parameter in parts[1:]:
            if parameter.startswith("q="):
                try:
                    q = float(parameter[2:])
                except ValueError:
                    q = 0.0
        if not 0.0 <= q <= 1.0:
            q = 0.0
        for media_type in supported:
            if media_range == media_type:
                specificity = 2
            elif media_range == "image/*":
                specificity = 1
            elif media_range == "*/*":
                specificity = 0
            else:
                continue
            retained_specificity, retained_q = quality[media_type]
            if specificity > retained_specificity:
                quality[media_type] = (specificity, q)
            elif specificity == retained_specificity:
                quality[media_type] = (specificity, max(retained_q, q))
    choices = [media_type for media_type in supported if quality[media_type][1] > 0]
    if not choices:
        raise NotAcceptableError("no acceptable role avatar image format")
    return max(
        choices,
        key=lambda media_type: (
            quality[media_type][1], quality[media_type][0], -supported.index(media_type)
        ),
    )


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
                ["codex", "app-server", "--listen", "stdio://"], cwd=str(cwd), stdin=subprocess.PIPE,
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


def _config_leaf_items(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten canonical TOML leaves without inventing schema entries."""
    if not isinstance(value, dict):
        return [(prefix, value)] if prefix else []
    leaves: list[tuple[str, Any]] = []
    for key in sorted(value):
        child = f"{prefix}.{key}" if prefix else str(key)
        leaves.extend(_config_leaf_items(value[key], child))
    return leaves


def _config_value_at(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _config_private_path(dotted_path: str) -> bool:
    normalized = dotted_path.casefold()
    if normalized in CONFIG_PRIVATE_PATHS:
        return True
    return bool(set(normalized.split(".")) & CONFIG_PRIVATE_SEGMENTS)


def _config_internal_path(dotted_path: str) -> bool:
    return dotted_path in CONFIG_INTERNAL_PATHS


def _config_classification(dotted_path: str) -> tuple[str, str | None]:
    if _config_private_path(dotted_path):
        return "unsupported", "Private values are retained only through immutable opaque placeholders."
    if _config_internal_path(dotted_path):
        return "internal", "Schema metadata or a fixed SWARM invariant is not a user setting."
    return "exposed", None


def _config_type(value: Any, dotted_path: str, module: Any | None = None) -> str:
    if _config_private_path(dotted_path):
        return "secret"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, str):
        return "enum" if _config_allowed_enum(dotted_path, module=module) else "string"
    return "string"


def _config_allowed_enum(dotted_path: str, *, module: Any | None = None) -> list[str] | None:
    """Expose enum values only when the canonical module exports the set."""
    try:
        module = module or load_config_module()
    except ConsoleError:
        return None
    normalized = dotted_path.casefold()
    if normalized == "execution.usage_profile":
        values = getattr(module, "USAGE_PROFILES", None)
    elif normalized.endswith("_reasoning") or normalized.endswith(".reasoning"):
        values = getattr(module, "REASONING_SCALE", None)
    elif normalized == "boost.strategies" or normalized.endswith(".workloads"):
        values = getattr(module, "BOOST_STRATEGIES", None) if normalized == "boost.strategies" else getattr(module, "MODEL_WORKLOADS", None)
    elif normalized == "boost.goal_levels":
        values = getattr(module, "BOOST_LEVELS", None)
    elif normalized == "subagents.allowed_for":
        values = getattr(module, "ALLOWED_SUBAGENT_WORK", None)
    else:
        values = None
    if isinstance(values, (set, frozenset, tuple, list)) and all(isinstance(item, str) for item in values):
        return sorted(set(values))
    return None


def _config_section(dotted_path: str) -> str:
    root = dotted_path.split(".", 1)[0]
    if dotted_path in CONFIG_HIGH_VALUE_PATHS:
        return "Essentials"
    if root == "execution":
        return "Execution"
    if root in {"models", "model_capabilities"}:
        return "Models & reasoning"
    if root in {"lifecycle", "coordination", "subagents", "review", "recovery", "goals", "hive"}:
        return "Tasks & handoffs"
    if root in {"roles", "professions", "labels"}:
        return "Roles & agents"
    if root in {"role_icons", "console", "chat_relay"}:
        return "Interface"
    if root in {"portfolio", "boost", "turbo", "efficiency"}:
        return "Usage"
    if root in {"proof", "monitoring", "logging"}:
        return "Logs & diagnostics"
    if root == "feedback":
        return "Integrations & paths"
    return "Advanced"


def _config_label_help(dotted_path: str) -> tuple[str, str]:
    labels = {
        "automation.mode": ("Auto mode", "Keep eligible SWARM lifecycle actions automatic or require manual confirmation."),
        "execution.fast_mode": ("Speed", "Request the canonical Fast service for newly resolved work."),
        "execution.usage_profile": ("Usage profile", "Select the canonical relative model and reasoning profile."),
        "execution.min_reasoning": ("Minimum reasoning", "Set the global reasoning floor applied to new work."),
        "execution.max_reasoning": ("Maximum reasoning", "Set the global reasoning ceiling applied to new work."),
        "execution.usage_saver": ("Usage saver · Experimental", "Reduce coordination churn and model usage when smart routing can safely do so."),
        "monitoring.auto_health_enabled": ("Auto fix", AUTO_REPAIR_HELP),
        "lifecycle.task_lifetime_hours": ("Task life", "Choose how long a task may remain in one continuity window."),
        "role_icons.enabled": ("Emoji use", "Use the canonical role emoji in SWARM task titles."),
        "console.auto_start": ("Start HQ automatically", "Start or reuse the local HQ when a CTRL starts."),
        "console.open_on_start": ("Open HQ on start", "Open HQ in the browser when a CTRL starts and no recent HQ tab is present."),
        "console.project_progress_feed_enabled": ("Project progress feed", "Show the on-demand project progress feed."),
        "console.project_progress_feed_lines": ("Progress feed lines", "Bound the number of material project feed lines."),
    }
    if dotted_path in labels:
        return labels[dotted_path]
    leaf = dotted_path.rsplit(".", 1)[-1].replace("_", " ").strip()
    return leaf[:1].upper() + leaf[1:], f"Canonical SWARM setting: {dotted_path}."


def _canonical_editable_settings() -> dict[str, type]:
    """Build the legacy compatibility map from DEFAULTS, never from a copy."""
    try:
        module = load_config_module()
        defaults = module.DEFAULTS
    except (ConsoleError, AttributeError, TypeError):
        return {}
    result: dict[str, type] = {}
    for dotted_path, value in _config_leaf_items(defaults):
        if len(dotted_path.split(".")) != 2:
            continue
        classification, _ = _config_classification(dotted_path)
        if classification == "exposed":
            result[dotted_path] = type(value)
    return result


EDITABLE_SETTINGS = _canonical_editable_settings()


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
    module, effective, exists = load_config(config_path)
    safe, _ = _config_redacted_settings(effective)
    return {
        "schema_version": int(getattr(module, "DEFAULTS", {}).get("schema_version", 0)),
        "exists": exists,
        "path": str(config_path),
        "settings": safe,
        "editable": sorted(EDITABLE_SETTINGS),
    }


def _config_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _config_bytes(path: Path, *, fallback: Path) -> tuple[bytes, bool]:
    try:
        if path.exists():
            return path.read_bytes(), True
        return fallback.read_bytes(), False
    except (OSError, ValueError) as exc:
        raise ConsoleError("canonical SWARM config source is unreadable") from exc


def _config_reject_deprecated(raw: dict[str, Any]) -> None:
    for dotted_path in sorted(CONFIG_DEPRECATED_PATHS):
        if _config_value_present(raw, dotted_path):
            raise ConsoleError(f"deprecated config setting is not accepted by Edit config: {dotted_path}")
    for dotted_path, value in sorted(CONFIG_DEPRECATED_VALUES):
        if _config_value_at(raw, dotted_path) == value:
            raise ConsoleError(
                f"deprecated config value is not accepted by Edit config: {dotted_path}={value}"
            )


def _config_value_present(value: Any, dotted_path: str) -> bool:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _config_parse_text(
    module: Any,
    text: str,
    *,
    scope_type: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(text, str):
        raise ConsoleError("config text must be a string")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ConsoleError("config text must be valid UTF-8") from exc
    if len(encoded) > CONFIG_TEXT_MAX_BYTES:
        raise ConsoleError("config text exceeds the 65536-byte editor limit")
    if "\x00" in text:
        raise ConsoleError("config text contains an unsafe NUL character")
    try:
        raw = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, TypeError, ValueError) as exc:
        raise ConsoleError(f"config TOML is invalid: {str(exc)[:256]}") from exc
    if not isinstance(raw, dict):
        raise ConsoleError("config TOML must contain a table")
    _config_reject_deprecated(raw)
    canonical_schema = getattr(module, "DEFAULTS", {}).get("schema_version")
    declared_schema = raw.get("schema_version")
    if scope_type == "global":
        if declared_schema != canonical_schema:
            raise ConsoleError("config schema_version must match the canonical schema")
    elif declared_schema is not None and declared_schema != canonical_schema:
        raise ConsoleError("project config schema_version must match the canonical schema")
    validation_raw = copy.deepcopy(raw)
    if scope_type == "project" and "schema_version" not in validation_raw:
        validation_raw["schema_version"] = canonical_schema
    try:
        normalized = module.normalize_legacy_task_role(validation_raw)
        module.validate(normalized)
        effective = module.apply_turbo(module.merge(normalized))
    except Exception as exc:  # ConfigError is owned by the loaded canonical module.
        raise ConsoleError(f"config validation failed: {str(exc)[:256]}") from exc
    return raw, normalized, effective


def _config_scalar_literal(literal: str) -> Any:
    try:
        parsed = tomllib.loads(f"value = {literal}\n")
    except (tomllib.TOMLDecodeError, TypeError, ValueError):
        return None
    return parsed.get("value")


def _config_value_bounds(line: str, equal_index: int) -> tuple[int, int] | None:
    start = equal_index + 1
    while start < len(line) and line[start] in " \t":
        start += 1
    if start >= len(line):
        return None
    if line.startswith('"""', start) or line.startswith("'''", start):
        delimiter = line[start : start + 3]
        end = line.find(delimiter, start + 3)
        if end < 0:
            return None
        return start, end + 3
    if line[start] in {'"', "'"}:
        delimiter = line[start]
        index = start + 1
        escaped = False
        while index < len(line):
            character = line[index]
            if delimiter == '"' and escaped:
                escaped = False
            elif delimiter == '"' and character == "\\":
                escaped = True
            elif character == delimiter:
                return start, index + 1
            index += 1
        return None
    index = start
    while index < len(line) and line[index] != "#":
        index += 1
    end = index
    while end > start and line[end - 1] in " \t":
        end -= 1
    return start, end


def _config_key_path(raw_key: str) -> str:
    """Normalize bare or quoted TOML key components for redaction only."""
    parts: list[str] = []
    current: list[str] = []
    quote = ""
    escaped = False
    for character in raw_key:
        if quote:
            current.append(character)
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            continue
        if character in {'"', "'"}:
            quote = character
            current.append(character)
        elif character == ".":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    parts.append("".join(current).strip())
    decoded: list[str] = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"}:
            try:
                parsed = tomllib.loads(f"{part} = true\n")
                part = str(next(iter(parsed)))
            except (tomllib.TOMLDecodeError, TypeError, ValueError):
                part = part[1:-1]
        decoded.append(part)
    return ".".join(decoded)


def _config_private_entries(text: str) -> dict[str, dict[str, Any]]:
    section = ""
    entries: dict[str, dict[str, Any]] = {}
    offset = 0
    for line_number, raw_line in enumerate(text.splitlines(keepends=True)):
        line = raw_line.rstrip("\r\n")
        section_match = re.match(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$", line)
        if section_match:
            section = _config_key_path(section_match.group(1))
            offset += len(raw_line)
            continue
        key_match = re.match(
            r"^\s*((?:[A-Za-z0-9_-]+|\"(?:\\.|[^\"])*\"|'[^']+')(?:\s*\.\s*(?:[A-Za-z0-9_-]+|\"(?:\\.|[^\"])*\"|'[^']+'))*)\s*=",
            line,
        )
        if not key_match:
            offset += len(raw_line)
            continue
        key_path = _config_key_path(key_match.group(1))
        dotted_path = f"{section}.{key_path}" if section else key_path
        if not _config_private_path(dotted_path):
            offset += len(raw_line)
            continue
        equal_index = line.find("=", key_match.start(1) + len(key_match.group(1)))
        bounds = _config_value_bounds(line, equal_index)
        if bounds is not None:
            start, end = bounds
            if dotted_path in entries:
                raise ConsoleError(f"private config setting is duplicated: {dotted_path}")
            entries[dotted_path] = {
                "line_number": line_number,
                "line": line,
                "start": start,
                "end": end,
                "literal": line[start:end],
                "offset": offset + start,
            }
        offset += len(raw_line)
    return entries


def _config_opaque_token(dotted_path: str, revision: str) -> str:
    return f"__SWARM_OPAQUE_V1__:{dotted_path}:{revision}"


def _config_redacted_text(text: str, revision: str) -> tuple[str, list[dict[str, str]]]:
    entries = _config_private_entries(text)
    replacements: dict[int, list[tuple[int, int, str]]] = {}
    placeholders: list[dict[str, str]] = []
    for dotted_path, entry in entries.items():
        value = _config_scalar_literal(str(entry["literal"]))
        if value in (None, ""):
            continue
        token = _config_opaque_token(dotted_path, revision)
        replacements.setdefault(int(entry["line_number"]), []).append(
            (int(entry["start"]), int(entry["end"]), json.dumps(token, ensure_ascii=False))
        )
        placeholders.append({
            "kind": "opaque",
            "path": dotted_path,
            "token": token,
            "value_type": "string",
            "revision": revision,
        })
    if not replacements:
        return text, placeholders
    lines = text.splitlines(keepends=True)
    for line_number, line_replacements in replacements.items():
        line = lines[line_number]
        for start, end, replacement in sorted(line_replacements, reverse=True):
            lines[line_number] = line[:start] + replacement + line[end:]
            line = lines[line_number]
    return "".join(lines), sorted(placeholders, key=lambda item: item["path"])


def _config_resolve_opaque_text(submitted: str, current: str, revision: str) -> str:
    current_entries = _config_private_entries(current)
    submitted_entries = _config_private_entries(submitted)
    replacements: dict[int, list[tuple[int, int, str]]] = {}
    for dotted_path, current_entry in current_entries.items():
        current_value = _config_scalar_literal(str(current_entry["literal"]))
        submitted_entry = submitted_entries.get(dotted_path)
        if current_value not in (None, ""):
            token = _config_opaque_token(dotted_path, revision)
            if submitted_entry is None or _config_scalar_literal(str(submitted_entry["literal"])) != token:
                raise ConsoleError(f"private setting {dotted_path} must retain its current opaque placeholder")
            replacements.setdefault(int(submitted_entry["line_number"]), []).append(
                (int(submitted_entry["start"]), int(submitted_entry["end"]), str(current_entry["literal"]))
            )
        elif submitted_entry is not None:
            submitted_value = _config_scalar_literal(str(submitted_entry["literal"]))
            if submitted_value not in (None, ""):
                raise ConsoleError(f"private setting {dotted_path} cannot be added through Edit config")
    for dotted_path, submitted_entry in submitted_entries.items():
        if dotted_path not in current_entries:
            submitted_value = _config_scalar_literal(str(submitted_entry["literal"]))
            if submitted_value not in (None, ""):
                raise ConsoleError(f"private setting {dotted_path} cannot be added through Edit config")
    reserved_tokens = set(re.findall(r"__SWARM_OPAQUE_V1__:[A-Za-z0-9_.-]+:[0-9a-f]{64}", submitted))
    expected_tokens = {
        _config_opaque_token(path, revision)
        for path, entry in current_entries.items()
        if _config_scalar_literal(str(entry["literal"])) not in (None, "")
    }
    if reserved_tokens - expected_tokens:
        raise ConsoleError("config contains an unbound opaque placeholder")
    if not replacements:
        return submitted
    lines = submitted.splitlines(keepends=True)
    for line_number, line_replacements in replacements.items():
        line = lines[line_number]
        for start, end, replacement in sorted(line_replacements, reverse=True):
            lines[line_number] = line[:start] + replacement + line[end:]
            line = lines[line_number]
    return "".join(lines)


def _config_redacted_settings(effective: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bool]]:
    safe = copy.deepcopy(effective)
    configured: dict[str, bool] = {}
    for dotted_path, _ in _config_leaf_items(effective):
        if not _config_private_path(dotted_path):
            continue
        value = _config_value_at(effective, dotted_path)
        configured[dotted_path] = bool(value)
        target = safe
        parts = dotted_path.split(".")
        for part in parts[:-1]:
            if not isinstance(target, dict) or part not in target:
                break
            target = target[part]
        else:
            if isinstance(target, dict):
                target[parts[-1]] = ""
    if isinstance(safe.get("feedback"), dict) and "feedback.destination" in configured:
        safe["feedback"]["destination_configured"] = configured["feedback.destination"]
    return safe, configured


def _config_scope_revision(
    scope_type: str,
    project_id: str | None,
    cursor: dict[str, Any] | None,
    global_revision: str,
    overlay_text: str,
) -> str:
    return _auto_digest({
        "contract_version": CONFIG_CONTRACT_VERSION,
        "scope_type": scope_type,
        "project_id": project_id,
        "accepted_cursor": cursor,
        "global_revision": global_revision,
        "overlay_digest": _config_sha256(overlay_text.encode("utf-8")),
    })


def _config_changed_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    paths = {path for path, _ in _config_leaf_items(before)} | {path for path, _ in _config_leaf_items(after)}
    return sorted(
        path for path in paths
        if _config_value_at(before, path) != _config_value_at(after, path)
        and path != "schema_version"
    )


def _config_merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial project TOML overlay without copying global values."""
    result = copy.deepcopy(base)

    def merge_table(target: dict[str, Any], updates: dict[str, Any], prefix: str = "") -> None:
        for key, value in updates.items():
            dotted_path = f"{prefix}.{key}" if prefix else str(key)
            if dotted_path == "schema_version":
                continue
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge_table(target[key], value, dotted_path)
            else:
                target[key] = copy.deepcopy(value)

    merge_table(result, overlay)
    return result


def _config_public_value(value: Any, *, private: bool, known: bool = True) -> Any:
    if private:
        if not known:
            return {"state": "unknown"}
        return {"state": "configured" if bool(value) else "empty"}
    return copy.deepcopy(value) if known else None


def _config_descriptor_rows(
    module: Any,
    defaults: dict[str, Any],
    effective: dict[str, Any],
    *,
    global_raw: dict[str, Any],
    overlay_raw: dict[str, Any] | None,
    revision: str,
    scope_type: str,
    values_known: bool,
) -> list[dict[str, Any]]:
    paths = {
        path
        for path, _ in _config_leaf_items(defaults)
    } | {
        path
        for path, _ in _config_leaf_items(effective)
    }
    rows: list[dict[str, Any]] = []
    for dotted_path in sorted(paths):
        classification, reason = _config_classification(dotted_path)
        private = _config_private_path(dotted_path)
        default_value = _config_value_at(defaults, dotted_path)
        current_value = _config_value_at(effective, dotted_path)
        sample_value = default_value if default_value is not None else current_value
        enum_values = _config_allowed_enum(dotted_path, module=module)
        if overlay_raw is not None and _config_value_present(overlay_raw, dotted_path):
            source = "project_override"
        elif _config_value_present(global_raw, dotted_path):
            source = "global"
        else:
            source = "canonical_default"
        label, help_text = _config_label_help(dotted_path)
        rows.append({
            "key": dotted_path,
            "section": _config_section(dotted_path),
            "label": label,
            "help": help_text,
            "type": _config_type(sample_value, dotted_path, module),
            "default": _config_public_value(default_value, private=private),
            "current": _config_public_value(current_value, private=private, known=values_known),
            "allowed_enum": enum_values,
            "allowed_range": None,
            "advanced": dotted_path not in CONFIG_HIGH_VALUE_PATHS,
            "restart_required": dotted_path in CONFIG_RESTART_PATHS,
            "reload_required": True,
            "reload_requirement": "next_scheduled_operation",
            "scope": "global_or_project",
            "sensitivity": "private" if private else "normal",
            "revision": revision,
            "classification": classification,
            "reason": reason,
            "source": source,
            "editable": classification == "exposed",
            "value_state": "KNOWN" if values_known else "UNKNOWN",
        })
    return rows


def _atomic_config_write(path: Path, data: bytes, module: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        module.load(temporary)
        if path.exists():
            shutil.copy2(path, path.with_suffix(".toml.swarm-console.bak"))
        os.replace(temporary, path)
        temporary = None
    except Exception as exc:
        raise ConsoleError(str(exc)[:256]) from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)


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


def _canonical_config_defaults_text(module: Any) -> str:
    """Read the one canonical packaged source used by revisioned reset."""
    source = Path(
        getattr(module, "TEMPLATE_PATH", SWARM_SKILL_ROOT / "assets" / "swarm-config.toml")
    )
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConsoleError(f"could not read packaged SWARM defaults: {exc}") from exc
    try:
        _config_parse_text(module, text, scope_type="global")
    except ConsoleError:
        raise
    except Exception as exc:
        raise ConsoleError(f"canonical SWARM defaults are invalid: {str(exc)[:256]}") from exc
    return text


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


def _asset_json_bytes(value: Any, label: str) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ConsoleError(f"{label} must be JSON data") from exc
    if len(encoded.encode("utf-8")) > ASSET_MAX_JSON_BYTES:
        raise ConsoleError(f"{label} exceeds the asset metadata guard")
    return encoded


def _asset_id(value: Any, label: str) -> str:
    return _auto_id(value, label)


def _asset_time(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConsoleError(f"{label} must be a nonnegative integer")
    return value


def _asset_optional_text(value: Any, label: str, *, maximum: int = 512) -> str:
    if value in (None, ""):
        return ""
    return _safe_metadata_text(value, label, maximum=maximum)


def _asset_presentation(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not set(value).issubset(ASSET_PRESENTATION_FIELDS):
        raise ConsoleError("asset presentation has unsupported fields")
    display_name = _safe_metadata_text(value.get("display_name"), "asset presentation display_name", maximum=256)
    kind = _asset_id(value.get("kind"), "asset presentation kind").casefold()
    description = _asset_optional_text(value.get("description"), "asset presentation description", maximum=1024)
    result = {"display_name": display_name, "kind": kind}
    if description:
        result["description"] = description
    return result


def _asset_job_metadata(value: Any) -> dict[str, Any]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict) or not set(value).issubset(ASSET_JOB_METADATA_FIELDS):
        raise ConsoleError("asset job metadata has unsupported fields")
    result: dict[str, Any] = {}
    for key in sorted(value):
        item = value[key]
        if key == "attempt":
            if not isinstance(item, int) or isinstance(item, bool) or item < 1:
                raise ConsoleError("asset job metadata attempt must be a positive integer")
            result[key] = item
        else:
            result[key] = _asset_id(item, f"asset job metadata {key}")
    return result


def _asset_provenance(value: Any, label: str = "asset provenance") -> dict[str, str]:
    if not isinstance(value, dict) or not set(value).issubset(ASSET_PROVENANCE_FIELDS):
        raise ConsoleError(f"{label} has unsupported fields")
    source = _asset_id(value.get("source"), f"{label} source")
    result = {"source": source}
    for key in ("receipt", "parent_asset_id", "admission"):
        if value.get(key) not in (None, ""):
            result[key] = _asset_id(value[key], f"{label} {key}")
    return result


def _asset_request_summary(value: Any) -> str:
    return _safe_metadata_text(value, "asset request_summary", maximum=1024)


def _asset_progress(value: Any, provenance: Any) -> tuple[float | None, str | None]:
    if value is None:
        if provenance not in (None, ""):
            raise ConsoleError("measured progress provenance requires measured progress")
        return None, None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
        raise ConsoleError("measured_progress must be a finite number between 0 and 1")
    return float(value), _asset_id(provenance, "measured_progress provenance")


def _asset_error_class(value: Any) -> str:
    error_class = _asset_id(value, "asset error_class").upper()
    if error_class not in ASSET_ERROR_CLASSES:
        raise ConsoleError("asset error_class is not allowlisted")
    return error_class


def _asset_status_label(status: str) -> str:
    return {
        "queued": "Queued",
        "generating": "Generating",
        "validating": "Validating",
        "ready": "Ready",
        "failed": "Failed",
        "cancelled": "Cancelled",
    }.get(status, "Unavailable")


def _asset_timestamp_text(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


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


def _health_check(
    check_id: str,
    status: str,
    summary: str,
    *,
    observed_at_ms: int,
    evidence: tuple[str, ...] = (),
    recommended_action: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = str(status).strip().upper()
    if status not in HEALTH_CHECK_STATUSES:
        raise ValueError(f"unsupported health check status: {status}")
    result = {
        "id": check_id,
        "status": status,
        "summary": summary,
        "observed_at_ms": int(observed_at_ms),
        "evidence": list(evidence),
        "recommended_action": recommended_action,
    }
    if details:
        result["details"] = copy.deepcopy(details)
    return result


def _server_identity_paths() -> tuple[Path | None, Path | None]:
    """Resolve the retained source/mirror pair without comparing a file to itself."""
    current = Path(__file__).resolve()
    current_parent = current.parent
    package_root = current_parent.parent
    if (
        package_root.name.casefold() == "swarm"
        and package_root.parent.name.casefold() == "plugins"
    ):
        source_root = package_root.parent.parent
        source_server = source_root / "console" / "server.py"
        return (source_server if (source_root / ".git").exists() else None), current
    mirror_server = package_root / "plugins" / "swarm" / "console" / "server.py"
    return (current if (package_root / ".git").exists() else None), mirror_server


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
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    logical_asset_id TEXT NOT NULL,
                    parent_revision_id TEXT,
                    project_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    presentation_json TEXT NOT NULL,
                    request_summary TEXT NOT NULL,
                    job_metadata_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    generation_job_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    locator TEXT,
                    media_type TEXT,
                    size_bytes INTEGER,
                    digest TEXT,
                    measured_progress REAL,
                    measured_progress_provenance TEXT,
                    error_class TEXT,
                    retry_eligible INTEGER NOT NULL DEFAULT 0,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    trashed_at_ms INTEGER,
                    trashed_by TEXT,
                    revision INTEGER NOT NULL,
                    last_operation_id TEXT NOT NULL,
                    last_event_sequence INTEGER NOT NULL DEFAULT 0,
                    last_event_identity TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS assets_project_idempotency
                    ON assets(project_id, idempotency_key);
                CREATE INDEX IF NOT EXISTS assets_project_updated
                    ON assets(project_id, trashed_at_ms, updated_at_ms DESC, asset_id DESC);
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
                    config_text TEXT NOT NULL DEFAULT '',
                    config_revision INTEGER NOT NULL DEFAULT 0,
                    config_updated_at_ms INTEGER NOT NULL DEFAULT 0,
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
                    retained_at_ms INTEGER NOT NULL,
                    config_commit_state TEXT NOT NULL DEFAULT 'COMMITTED',
                    config_transaction_json TEXT NOT NULL DEFAULT '{}'
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
                "config_commit_state": "TEXT NOT NULL DEFAULT 'COMMITTED'",
                "config_transaction_json": "TEXT NOT NULL DEFAULT '{}'",
            }.items():
                if name not in execution_receipt_columns:
                    connection.execute(f"ALTER TABLE execution_event_receipts ADD COLUMN {name} {definition}")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS execution_event_identity "
                "ON execution_event_receipts(event_kind, identity) WHERE identity != ''"
            )
            overlay_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(skill_scope_overlays)").fetchall()
            }
            for name, definition in {
                "config_text": "TEXT NOT NULL DEFAULT ''",
                "config_revision": "INTEGER NOT NULL DEFAULT 0",
                "config_updated_at_ms": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in overlay_columns:
                    connection.execute(f"ALTER TABLE skill_scope_overlays ADD COLUMN {name} {definition}")
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
                "SELECT event_digest FROM execution_event_receipts WHERE event_kind = 'EXECUTION_EVENT' ORDER BY event_digest"
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

    def config_overlay(self, project_id: str) -> dict[str, Any] | None:
        """Read the config namespace of the existing project overlay row."""
        project_id = _safe_metadata_text(project_id, "project_id", maximum=256)
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT config_text, config_revision, config_updated_at_ms "
                "FROM skill_scope_overlays WHERE scope_type = 'project' AND scope_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        text = row["config_text"]
        if not isinstance(text, str) or len(text.encode("utf-8")) > CONFIG_TEXT_MAX_BYTES:
            raise ConsoleError("retained project config overlay is unreadable")
        revision = row["config_revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise ConsoleError("retained project config overlay revision is invalid")
        updated_at_ms = row["config_updated_at_ms"]
        if not isinstance(updated_at_ms, int) or isinstance(updated_at_ms, bool) or updated_at_ms < 0:
            raise ConsoleError("retained project config overlay timestamp is invalid")
        return {
            "project_id": project_id,
            "text": text,
            "config_revision": int(revision),
            "updated_at_ms": int(updated_at_ms),
        }

    @classmethod
    def _config_encoded_payload(cls, payload: dict[str, Any]) -> tuple[str, str]:
        def contains_config_text(value: Any) -> bool:
            if isinstance(value, dict):
                return any(
                    key in {"text", "config_text", "raw_text", "raw_config"}
                    or contains_config_text(child)
                    for key, child in value.items()
                )
            if isinstance(value, list):
                return any(contains_config_text(child) for child in value)
            return False

        if not isinstance(payload, dict) or contains_config_text(payload):
            raise ConsoleError("config audit payload cannot contain config text")
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def _retain_config_event_unlocked(
        cls,
        connection: sqlite3.Connection,
        *,
        operation_id: str,
        payload: dict[str, Any],
        now_ms: int,
    ) -> bool:
        encoded, digest = cls._config_encoded_payload(payload)
        retained = connection.execute(
            "SELECT payload_digest, config_commit_state FROM execution_event_receipts "
            "WHERE event_kind = ? AND identity = ?",
            (CONFIG_EVENT_KIND, operation_id),
        ).fetchone()
        if retained is not None:
            if str(retained["payload_digest"]) != digest:
                raise ConsoleConflict("config operation identity conflicts with retained audit content")
            if str(retained["config_commit_state"] or CONFIG_TRANSACTION_COMMITTED) != CONFIG_TRANSACTION_COMMITTED:
                raise ConsoleConflict("config operation is not committed")
            return False
        connection.execute(
            "INSERT INTO execution_event_receipts(event_digest, retained_at_ms, event_kind, identity, payload_json, payload_digest) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (digest, now_ms, CONFIG_EVENT_KIND, operation_id, encoded, digest),
        )
        return True

    @classmethod
    def _validate_config_transaction(cls, transaction: dict[str, Any]) -> str:
        required = {
            "operation_id", "before_revision", "after_revision", "source_path",
            "source_existed", "rollback_path", "rollback_digest",
        }
        if not isinstance(transaction, dict) or set(transaction) != required:
            raise ConsoleError("config transaction metadata is invalid")
        for key in ("before_revision", "after_revision"):
            if not isinstance(transaction[key], str) or not re.fullmatch(r"[0-9a-f]{64}", transaction[key]):
                raise ConsoleError("config transaction revision metadata is invalid")
        if transaction["operation_id"] != _auto_id(transaction["operation_id"], "operation_id"):
            raise ConsoleError("config transaction operation metadata is invalid")
        for key in ("source_path", "rollback_path"):
            if not isinstance(transaction[key], str) or not transaction[key] or "\x00" in transaction[key]:
                raise ConsoleError("config transaction path metadata is invalid")
        if not isinstance(transaction["source_existed"], bool):
            raise ConsoleError("config transaction existence metadata is invalid")
        if not isinstance(transaction["rollback_digest"], str):
            raise ConsoleError("config transaction rollback metadata is invalid")
        if transaction["rollback_digest"] and not re.fullmatch(r"[0-9a-f]{64}", transaction["rollback_digest"]):
            raise ConsoleError("config transaction rollback metadata is invalid")
        if transaction["source_existed"] and not transaction["rollback_digest"]:
            raise ConsoleError("config transaction requires a rollback digest")
        if not transaction["source_existed"] and transaction["rollback_digest"]:
            raise ConsoleError("config transaction cannot retain a nonexistent source")
        return json.dumps(transaction, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    def prepare_config_event(
        self,
        operation_id: str,
        payload: dict[str, Any],
        *,
        transaction: dict[str, Any],
        now_ms: int,
    ) -> str:
        operation_id = _safe_metadata_text(operation_id, "operation_id", maximum=256)
        if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
            raise ConsoleError("config audit timestamp is invalid")
        encoded, digest = self._config_encoded_payload(payload)
        transaction_json = self._validate_config_transaction(transaction)
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            retained = connection.execute(
                "SELECT payload_digest, config_commit_state, config_transaction_json "
                "FROM execution_event_receipts WHERE event_kind = ? AND identity = ?",
                (CONFIG_EVENT_KIND, operation_id),
            ).fetchone()
            if retained is not None:
                if str(retained["payload_digest"]) != digest:
                    connection.rollback()
                    raise ConsoleConflict("config operation identity conflicts with retained audit content")
                state = str(retained["config_commit_state"] or CONFIG_TRANSACTION_COMMITTED)
                if state == CONFIG_TRANSACTION_COMMITTED:
                    connection.commit()
                    return CONFIG_TRANSACTION_COMMITTED
                if state == CONFIG_TRANSACTION_ABORTED:
                    connection.rollback()
                    raise ConsoleConflict("config operation was aborted; use a new operation_id")
                if state != CONFIG_TRANSACTION_PREPARED or str(retained["config_transaction_json"] or "{}") != transaction_json:
                    connection.rollback()
                    raise ConsoleConflict("config transaction identity conflicts with retained content")
                connection.commit()
                return CONFIG_TRANSACTION_PREPARED
            connection.execute(
                "INSERT INTO execution_event_receipts("
                "event_digest, retained_at_ms, event_kind, identity, payload_json, payload_digest, "
                "config_commit_state, config_transaction_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    digest, now_ms, CONFIG_EVENT_KIND, operation_id, encoded, digest,
                    CONFIG_TRANSACTION_PREPARED, transaction_json,
                ),
            )
            connection.commit()
        return CONFIG_TRANSACTION_PREPARED

    def pending_config_events(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT identity, payload_digest, config_transaction_json "
                "FROM execution_event_receipts WHERE event_kind = ? AND config_commit_state = ? "
                "ORDER BY retained_at_ms, identity",
                (CONFIG_EVENT_KIND, CONFIG_TRANSACTION_PREPARED),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                transaction = json.loads(str(row["config_transaction_json"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ConsoleError("retained config transaction is unreadable") from exc
            self._validate_config_transaction(transaction)
            result.append({
                "operation_id": str(row["identity"]),
                "payload_digest": str(row["payload_digest"]),
                "transaction": transaction,
            })
        return result

    def abort_config_event(self, operation_id: str) -> bool:
        operation_id = _safe_metadata_text(operation_id, "operation_id", maximum=256)
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT config_commit_state FROM execution_event_receipts "
                "WHERE event_kind = ? AND identity = ?",
                (CONFIG_EVENT_KIND, operation_id),
            ).fetchone()
            if row is None:
                connection.commit()
                return False
            state = str(row["config_commit_state"] or CONFIG_TRANSACTION_COMMITTED)
            if state == CONFIG_TRANSACTION_COMMITTED:
                connection.commit()
                return False
            if state == CONFIG_TRANSACTION_ABORTED:
                connection.commit()
                return False
            if state != CONFIG_TRANSACTION_PREPARED:
                connection.rollback()
                raise ConsoleError("retained config transaction state is invalid")
            connection.execute(
                "UPDATE execution_event_receipts SET config_commit_state = ?, config_transaction_json = '{}' "
                "WHERE event_kind = ? AND identity = ?",
                (CONFIG_TRANSACTION_ABORTED, CONFIG_EVENT_KIND, operation_id),
            )
            connection.commit()
        return True

    def config_event(self, operation_id: str) -> dict[str, Any] | None:
        operation_id = _safe_metadata_text(operation_id, "operation_id", maximum=256)
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload_json, payload_digest FROM execution_event_receipts "
                "WHERE event_kind = ? AND identity = ? AND config_commit_state = ?",
                (CONFIG_EVENT_KIND, operation_id, CONFIG_TRANSACTION_COMMITTED),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ConsoleError("retained config audit event is unreadable") from exc
        if not isinstance(payload, dict):
            raise ConsoleError("retained config audit event is invalid")
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != str(row["payload_digest"]):
            raise ConsoleError("retained config audit event digest is invalid")
        return payload

    def retain_config_event(
        self,
        operation_id: str,
        payload: dict[str, Any],
        *,
        now_ms: int,
    ) -> bool:
        operation_id = _safe_metadata_text(operation_id, "operation_id", maximum=256)
        if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
            raise ConsoleError("config audit timestamp is invalid")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            encoded, digest = self._config_encoded_payload(payload)
            retained = connection.execute(
                "SELECT payload_digest, config_commit_state FROM execution_event_receipts "
                "WHERE event_kind = ? AND identity = ?",
                (CONFIG_EVENT_KIND, operation_id),
            ).fetchone()
            if retained is None:
                connection.execute(
                    "INSERT INTO execution_event_receipts(event_digest, retained_at_ms, event_kind, identity, payload_json, payload_digest) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (digest, now_ms, CONFIG_EVENT_KIND, operation_id, encoded, digest),
                )
                fresh = True
            else:
                if str(retained["payload_digest"]) != digest:
                    connection.rollback()
                    raise ConsoleConflict("config operation identity conflicts with retained audit content")
                state = str(retained["config_commit_state"] or CONFIG_TRANSACTION_COMMITTED)
                if state == CONFIG_TRANSACTION_PREPARED:
                    connection.execute(
                        "UPDATE execution_event_receipts SET config_commit_state = ?, config_transaction_json = '{}' "
                        "WHERE event_kind = ? AND identity = ?",
                        (CONFIG_TRANSACTION_COMMITTED, CONFIG_EVENT_KIND, operation_id),
                    )
                    fresh = True
                elif state == CONFIG_TRANSACTION_COMMITTED:
                    fresh = False
                else:
                    connection.rollback()
                    raise ConsoleConflict("config operation was aborted; use a new operation_id")
            connection.commit()
        return fresh

    def update_config_overlay(
        self,
        project_id: str,
        text: str,
        *,
        expected_config_revision: int,
        operation_id: str,
        audit_payload: dict[str, Any],
        now_ms: int,
    ) -> dict[str, Any]:
        project_id = _safe_metadata_text(project_id, "project_id", maximum=256)
        operation_id = _safe_metadata_text(operation_id, "operation_id", maximum=256)
        if not isinstance(text, str) or len(text.encode("utf-8")) > CONFIG_TEXT_MAX_BYTES:
            raise ConsoleError("project config text is invalid or oversized")
        if not isinstance(expected_config_revision, int) or isinstance(expected_config_revision, bool) or expected_config_revision < 0:
            raise ConsoleError("project config revision is invalid")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            retained_event = connection.execute(
                "SELECT payload_json, payload_digest FROM execution_event_receipts "
                "WHERE event_kind = ? AND identity = ?",
                (CONFIG_EVENT_KIND, operation_id),
            ).fetchone()
            if retained_event is not None:
                try:
                    retained_payload = json.loads(str(retained_event["payload_json"]))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    connection.rollback()
                    raise ConsoleError("retained config audit event is unreadable") from exc
                retained_encoded = json.dumps(retained_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                audit_encoded = json.dumps(audit_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                if hashlib.sha256(retained_encoded.encode("utf-8")).hexdigest() != hashlib.sha256(audit_encoded.encode("utf-8")).hexdigest():
                    connection.rollback()
                    raise ConsoleConflict("config operation identity conflicts with retained audit content")
                connection.commit()
                return self.config_overlay(project_id) or {
                    "project_id": project_id, "text": "", "config_revision": 0, "updated_at_ms": 0,
                }
            row = connection.execute(
                "SELECT config_text, config_revision FROM skill_scope_overlays "
                "WHERE scope_type = 'project' AND scope_id = ?",
                (project_id,),
            ).fetchone()
            current_text = "" if row is None else str(row["config_text"] or "")
            current_revision = 0 if row is None else int(row["config_revision"])
            if current_revision != expected_config_revision:
                connection.rollback()
                raise ConsoleConflict("project config overlay changed; reload before saving")
            next_revision = current_revision + (1 if current_text != text else 0)
            if row is None:
                connection.execute(
                    "INSERT INTO skill_scope_overlays("
                    "scope_type, scope_id, revision, inheritance_enabled, profile, preferred_ids_json, updated_at_ms, "
                    "config_text, config_revision, config_updated_at_ms) VALUES (?, ?, 0, NULL, ?, ?, ?, ?, ?, ?)",
                    (
                        "project", project_id, "default", "[]", now_ms,
                        text, next_revision, now_ms,
                    ),
                )
            else:
                connection.execute(
                    "UPDATE skill_scope_overlays SET config_text = ?, config_revision = ?, config_updated_at_ms = ? "
                    "WHERE scope_type = 'project' AND scope_id = ?",
                    (text, next_revision, now_ms, project_id),
                )
            self._retain_config_event_unlocked(
                connection, operation_id=operation_id, payload=audit_payload, now_ms=now_ms,
            )
            connection.commit()
        return self.config_overlay(project_id) or {
            "project_id": project_id, "text": text, "config_revision": next_revision, "updated_at_ms": now_ms,
        }

    def reset_config_overlay(
        self,
        project_id: str,
        *,
        expected_config_revision: int,
        operation_id: str,
        audit_payload: dict[str, Any],
        now_ms: int,
    ) -> dict[str, Any] | None:
        project_id = _safe_metadata_text(project_id, "project_id", maximum=256)
        operation_id = _safe_metadata_text(operation_id, "operation_id", maximum=256)
        if not isinstance(expected_config_revision, int) or isinstance(expected_config_revision, bool) or expected_config_revision < 0:
            raise ConsoleError("project config revision is invalid")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            retained_event = connection.execute(
                "SELECT payload_json FROM execution_event_receipts WHERE event_kind = ? AND identity = ?",
                (CONFIG_EVENT_KIND, operation_id),
            ).fetchone()
            if retained_event is not None:
                try:
                    retained_payload = json.loads(str(retained_event["payload_json"]))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    connection.rollback()
                    raise ConsoleError("retained config audit event is unreadable") from exc
                if retained_payload != audit_payload:
                    connection.rollback()
                    raise ConsoleConflict("config operation identity conflicts with retained audit content")
                connection.commit()
                return self.config_overlay(project_id)
            row = connection.execute(
                "SELECT config_text, config_revision FROM skill_scope_overlays "
                "WHERE scope_type = 'project' AND scope_id = ?",
                (project_id,),
            ).fetchone()
            current_text = "" if row is None else str(row["config_text"] or "")
            current_revision = 0 if row is None else int(row["config_revision"])
            if current_revision != expected_config_revision:
                connection.rollback()
                raise ConsoleConflict("project config overlay changed; reload before resetting")
            next_revision = current_revision + (1 if current_text else 0)
            if row is not None and current_text:
                connection.execute(
                    "UPDATE skill_scope_overlays SET config_text = '', config_revision = ?, config_updated_at_ms = ? "
                    "WHERE scope_type = 'project' AND scope_id = ?",
                    (next_revision, now_ms, project_id),
                )
            self._retain_config_event_unlocked(
                connection, operation_id=operation_id, payload=audit_payload, now_ms=now_ms,
            )
            connection.commit()
        return self.config_overlay(project_id)

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

    @staticmethod
    def _asset_cursor_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
        sequence = payload.get("event_sequence")
        identity = payload.get("event_digest")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ConsoleError("asset event cursor is invalid")
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise ConsoleError("asset event identity is invalid")
        return {"sequence": sequence, "identity": identity}

    @staticmethod
    def _asset_event_cursor_unlocked(connection: sqlite3.Connection) -> dict[str, Any]:
        row = connection.execute(
            "SELECT value FROM store_metadata WHERE key = ?",
            (ASSET_EVENT_CURSOR_KEY,),
        ).fetchone()
        if row is not None:
            try:
                state = json.loads(str(row["value"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                state = None
            if isinstance(state, dict):
                sequence = state.get("sequence")
                identity = state.get("identity")
                if (
                    isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 0
                    and (identity is None or re.fullmatch(r"[0-9a-f]{64}", str(identity)))
                ):
                    return {"sequence": sequence, "identity": identity}
        rows = connection.execute(
            "SELECT payload_json FROM execution_event_receipts WHERE event_kind = ?",
            (ASSET_EVENT_KIND,),
        ).fetchall()
        latest: tuple[int, str] | None = None
        for item in rows:
            try:
                payload = json.loads(str(item["payload_json"]))
                cursor = ConsoleStore._asset_cursor_from_payload(payload)
            except (ConsoleError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if latest is None or cursor["sequence"] > latest[0]:
                latest = (cursor["sequence"], cursor["identity"])
        return {"sequence": 0 if latest is None else latest[0], "identity": None if latest is None else latest[1]}

    def asset_event_cursor(self) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            return self._asset_event_cursor_unlocked(connection)

    @staticmethod
    def _append_asset_event(
        connection: sqlite3.Connection,
        *,
        asset_id: str,
        logical_asset_id: str,
        project_id: str,
        action: str,
        from_status: str | None,
        to_status: str,
        operation_id: str,
        generation_job_id: str,
        revision: int,
        observed_at_ms: int,
        measured_progress: float | None = None,
        measured_progress_provenance: str | None = None,
        error_class: str | None = None,
        retry_eligible: bool = False,
        trashed_at_ms: int | None = None,
        trashed_by: str | None = None,
        content_digest: str | None = None,
        content_media_type: str | None = None,
    ) -> dict[str, Any]:
        identity = f"{asset_id}:{action}:{operation_id}:{revision}"
        _safe_metadata_text(identity, "asset event identity", maximum=1024)
        event_fields = {
            "schema_version": 1,
            "record_type": "ASSET_TRANSITION",
            "event_kind": ASSET_EVENT_KIND,
            "event_id": identity,
            "asset_id": asset_id,
            "logical_asset_id": logical_asset_id,
            "project_id": project_id,
            "action": action,
            "from_status": from_status,
            "to_status": to_status,
            "operation_id": operation_id,
            "generation_job_id": generation_job_id,
            "revision": revision,
            "observed_at_ms": observed_at_ms,
            "measured_progress": measured_progress,
            "measured_progress_provenance": measured_progress_provenance,
            "error_class": error_class,
            "retry_eligible": bool(retry_eligible),
            "trashed_at_ms": trashed_at_ms,
            "trashed_by": trashed_by,
            "content_digest": content_digest,
            "content_media_type": content_media_type,
        }
        existing = connection.execute(
            "SELECT payload_json, payload_digest FROM execution_event_receipts WHERE event_kind = ? AND identity = ?",
            (ASSET_EVENT_KIND, identity),
        ).fetchone()
        if existing is not None:
            try:
                retained = json.loads(str(existing["payload_json"]))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ConsoleError("retained asset event is unreadable") from exc
            if not isinstance(retained, dict):
                raise ConsoleError("retained asset event is invalid")
            retained_without_cursor = dict(retained)
            retained_without_cursor.pop("event_sequence", None)
            retained_without_cursor.pop("event_digest", None)
            if retained_without_cursor != event_fields:
                raise ConsoleConflict("asset event identity conflicts with retained content")
            digest = str(existing["payload_digest"] or "")
            retained_digest_payload = dict(retained)
            retained_digest_payload.pop("event_digest", None)
            if not re.fullmatch(r"[0-9a-f]{64}", digest) or _auto_digest(retained_digest_payload) != digest:
                raise ConsoleError("retained asset event digest is invalid")
            retained["event_digest"] = digest
            return ConsoleStore._asset_cursor_from_payload(retained)

        prior = ConsoleStore._asset_event_cursor_unlocked(connection)
        sequence = int(prior["sequence"]) + 1
        payload = {**event_fields, "event_sequence": sequence}
        digest = _auto_digest(payload)
        payload["event_digest"] = digest
        encoded = _asset_json_bytes(payload, "asset event")
        connection.execute(
            "INSERT INTO execution_event_receipts(event_digest, retained_at_ms, event_kind, identity, payload_json, payload_digest) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (digest, observed_at_ms, ASSET_EVENT_KIND, identity, encoded, digest),
        )
        cursor = {"sequence": sequence, "identity": digest}
        connection.execute(
            "INSERT INTO store_metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (ASSET_EVENT_CURSOR_KEY, json.dumps(cursor, ensure_ascii=True, sort_keys=True, separators=(",", ":"))),
        )
        return cursor

    @staticmethod
    def _asset_row_json(row: sqlite3.Row, field: str) -> dict[str, Any]:
        try:
            value = json.loads(str(row[field]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ConsoleError(f"asset {field} is unreadable") from exc
        if not isinstance(value, dict):
            raise ConsoleError(f"asset {field} is invalid")
        return value

    def _asset_preview(self, row: sqlite3.Row, *, allowed_root: Path | None) -> dict[str, Any]:
        status = str(row["status"] or "")
        if status != "ready":
            return {
                "state": "NOT_READY",
                "url": None,
                "reason": "The asset file is not published until generation reaches ready.",
            }
        locator = str(row["locator"] or "")
        digest = str(row["digest"] or "").casefold()
        media_type = str(row["media_type"] or "")
        if not locator or not re.fullmatch(r"[0-9a-f]{64}", digest) or media_type not in MEDIA_TYPES or allowed_root is None:
            return {
                "state": "UNAVAILABLE",
                "url": None,
                "reason": "Ready asset provenance is incomplete; no file URL is published.",
            }
        try:
            metadata = _media_metadata(
                locator,
                digest,
                allowed_root=allowed_root,
                supplied_size=None if row["size_bytes"] is None else int(row["size_bytes"]),
                supplied_media_type=media_type,
            )
        except (ConsoleError, OSError, TypeError, ValueError):
            return {
                "state": "UNAVAILABLE",
                "url": None,
                "reason": "The retained asset file or provenance no longer validates.",
            }
        return {
            "state": "AVAILABLE",
            "url": f"/api/assets/{row['asset_id']}/preview?digest={digest}",
            "media_type": metadata["media_type"],
            "size_bytes": metadata["size_bytes"],
        }

    def _public_asset_row(self, row: sqlite3.Row, *, allowed_root: Path | None = None) -> dict[str, Any]:
        status = str(row["status"] or "").casefold()
        if status not in ASSET_STATUSES:
            raise ConsoleError("asset status is invalid")
        presentation = self._asset_row_json(row, "presentation_json")
        job_metadata = self._asset_row_json(row, "job_metadata_json")
        provenance = self._asset_row_json(row, "provenance_json")
        created_at_ms = int(row["created_at_ms"])
        updated_at_ms = int(row["updated_at_ms"])
        cursor = {
            "sequence": int(row["last_event_sequence"] or 0),
            "identity": str(row["last_event_identity"] or "") or None,
        }
        if cursor["sequence"] and (
            cursor["identity"] is None or not re.fullmatch(r"[0-9a-f]{64}", str(cursor["identity"]))
        ):
            raise ConsoleError("asset event cursor is invalid")
        storage_state = "BOUND" if row["locator"] else "NOT_PUBLISHED"
        if status == "ready" and self._asset_preview(row, allowed_root=allowed_root)["state"] != "AVAILABLE":
            storage_state = "UNAVAILABLE"
        trashed_at_ms = None if row["trashed_at_ms"] is None else int(row["trashed_at_ms"])
        return {
            "asset_id": str(row["asset_id"]),
            "project_id": str(row["project_id"]),
            "presentation": {
                "display_name": str(presentation["display_name"]),
                "kind": str(presentation["kind"]),
                "description": str(presentation.get("description") or ""),
                "status": status,
                "status_label": _asset_status_label(status),
                "created_at": _asset_timestamp_text(created_at_ms),
                "updated_at": _asset_timestamp_text(updated_at_ms),
            },
            "technical": {
                "advanced_debug": True,
                "asset_id": str(row["asset_id"]),
                "logical_asset_id": str(row["logical_asset_id"]),
                "parent_revision_id": row["parent_revision_id"],
                "revision": int(row["revision"]),
                "status": status,
                "created_at_ms": created_at_ms,
                "updated_at_ms": updated_at_ms,
                "generation_job_id": str(row["generation_job_id"]),
                "operation_id": str(row["operation_id"]),
                "request_summary": str(row["request_summary"]),
                "job_metadata": job_metadata,
                "provenance": provenance,
                "digest": str(row["digest"] or "") or None,
                "media_type": str(row["media_type"] or "") or None,
                "size_bytes": None if row["size_bytes"] is None else int(row["size_bytes"]),
                "storage": {"state": storage_state, "path": None, "path_redacted": bool(row["locator"])},
                "measured_progress": row["measured_progress"],
                "measured_progress_provenance": row["measured_progress_provenance"],
                "error_class": row["error_class"],
                "retry_eligible": bool(row["retry_eligible"]),
                "idempotency_key": str(row["idempotency_key"]),
            },
            "preview": self._asset_preview(row, allowed_root=allowed_root),
            "trash": {
                "trashed": trashed_at_ms is not None,
                "trashed_at": None if trashed_at_ms is None else _asset_timestamp_text(trashed_at_ms),
                "trashed_at_ms": trashed_at_ms,
                "trashed_by": row["trashed_by"],
            },
            "event_cursor": cursor,
            "retention_policy": ASSET_RETENTION_POLICY,
            "claim_limit": (
                "Asset identity, state, lineage, and file provenance are server-owned. Presentation omits private paths; "
                "a preview URL is emitted only after the exact retained file validates. Trash is reversible soft state; "
                "purge is unavailable because no scheduled retention authority is configured."
            ),
        }

    def asset_list(
        self,
        *,
        project_id: str | None = None,
        projection: str = "active",
        allowed_root: Path | None = None,
    ) -> list[dict[str, Any]]:
        if projection not in {"active", "trash"}:
            raise ConsoleError("asset projection must be active or trash")
        conditions = ["trashed_at_ms IS NULL" if projection == "active" else "trashed_at_ms IS NOT NULL"]
        args: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            args.append(_asset_id(project_id, "project_id"))
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM assets WHERE " + " AND ".join(conditions)
                + " ORDER BY created_at_ms DESC, asset_id DESC",
                tuple(args),
            ).fetchall()
        return [self._public_asset_row(row, allowed_root=allowed_root) for row in rows]

    def asset_item(self, asset_id: str, *, allowed_root: Path | None = None) -> dict[str, Any]:
        asset_id = _asset_id(asset_id, "asset_id")
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            raise ConsoleError("asset was not found")
        return self._public_asset_row(row, allowed_root=allowed_root)

    def asset_media_item(self, asset_id: str, digest: str, *, allowed_root: Path) -> dict[str, Any]:
        asset_id = _asset_id(asset_id, "asset_id")
        digest = _safe_metadata_text(digest, "asset digest", maximum=64).casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ConsoleError("asset digest must be a SHA-256 hex digest")
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE asset_id = ? AND status = 'ready'",
                (asset_id,),
            ).fetchone()
        if row is None or str(row["digest"] or "").casefold() != digest:
            raise ConsoleError("ready asset was not found")
        preview = self._asset_preview(row, allowed_root=allowed_root)
        if preview.get("state") != "AVAILABLE":
            raise ConsoleError("ready asset file is unavailable")
        return {
            "path": Path(str(row["locator"])),
            "media_type": str(preview["media_type"]),
            "size_bytes": int(preview["size_bytes"]),
            "digest": digest,
            "asset_id": asset_id,
        }

    def asset_event_feed(
        self,
        *,
        project_id: str | None = None,
        after_sequence: int = 0,
        limit: int = 64,
    ) -> dict[str, Any]:
        if not isinstance(after_sequence, int) or isinstance(after_sequence, bool) or after_sequence < 0:
            raise ConsoleError("asset event after_sequence must be a nonnegative integer")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 128:
            raise ConsoleError("asset event limit must be between 1 and 128")
        project_filter = None if project_id in (None, "") else _asset_id(project_id, "project_id")
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT payload_json FROM execution_event_receipts WHERE event_kind = ?",
                (ASSET_EVENT_KIND,),
            ).fetchall()
            cursor = self._asset_event_cursor_unlocked(connection)
        items: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
                item_cursor = self._asset_cursor_from_payload(payload)
            except (ConsoleError, TypeError, ValueError, json.JSONDecodeError):
                raise ConsoleError("asset event ledger is unreadable")
            if project_filter is not None and payload.get("project_id") != project_filter:
                continue
            if item_cursor["sequence"] <= after_sequence:
                continue
            item = dict(payload)
            item.pop("event_digest", None)
            items.append({**item, "cursor": item_cursor})
        items.sort(key=lambda item: int(item["cursor"]["sequence"]))
        return {
            "status": "available",
            "project_id": project_id,
            "after_sequence": after_sequence,
            "cursor": cursor,
            "items": items[:limit],
            "retention_policy": ASSET_RETENTION_POLICY,
            "claim_limit": "Asset transition events are typed local receipts from the existing console event ledger; they are not model summaries or progress percentage evidence.",
        }

    def reserve_asset_generation(self, payload: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ConsoleError("asset generation request must be an object")
        project_id = _asset_id(payload.get("project_id"), "project_id")
        asset_id = _asset_id(payload.get("asset_id") or f"asset-{uuid.uuid4()}", "asset_id")
        logical_asset_id = _asset_id(payload.get("logical_asset_id") or asset_id, "logical_asset_id")
        parent_revision_id = payload.get("parent_revision_id")
        if parent_revision_id not in (None, ""):
            parent_revision_id = _asset_id(parent_revision_id, "parent_revision_id")
        generation_job_id = _asset_id(payload.get("generation_job_id"), "generation_job_id")
        operation_id = _asset_id(payload.get("operation_id"), "operation_id")
        idempotency_key = _asset_id(payload.get("idempotency_key"), "idempotency_key")
        request_summary = _asset_request_summary(payload.get("request_summary"))
        presentation = _asset_presentation(payload.get("presentation"))
        job_metadata = _asset_job_metadata(payload.get("job_metadata"))
        provenance = _asset_provenance(payload.get("provenance"))
        now_ms = _asset_time(now_ms, "asset created_at_ms")
        canonical = {
            "asset_id": asset_id,
            "logical_asset_id": logical_asset_id,
            "parent_revision_id": parent_revision_id,
            "project_id": project_id,
            "generation_job_id": generation_job_id,
            "operation_id": operation_id,
            "idempotency_key": idempotency_key,
            "request_summary": request_summary,
            "presentation": presentation,
            "job_metadata": job_metadata,
            "provenance": provenance,
        }
        request_digest = _auto_digest(canonical)
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM assets WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if str(existing["request_digest"]) != request_digest:
                    connection.rollback()
                    raise ConsoleConflict("asset idempotency key conflicts with retained generation request")
                connection.commit()
                return self._public_asset_row(existing)
            identity = connection.execute(
                "SELECT asset_id, request_digest FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            if identity is not None:
                connection.rollback()
                raise ConsoleConflict("asset_id already names a different retained asset")
            if parent_revision_id is not None:
                parent = connection.execute(
                    "SELECT asset_id, project_id, logical_asset_id FROM assets WHERE asset_id = ?",
                    (parent_revision_id,),
                ).fetchone()
                if (
                    parent is None
                    or str(parent["project_id"]) != project_id
                    or str(parent["logical_asset_id"]) != logical_asset_id
                    or parent_revision_id == asset_id
                ):
                    connection.rollback()
                    raise ConsoleError("asset parent_revision_id must be a retained revision in the requested logical asset")
            revision = 1
            cursor = self._append_asset_event(
                connection,
                asset_id=asset_id,
                logical_asset_id=logical_asset_id,
                project_id=project_id,
                action="reserve",
                from_status=None,
                to_status="queued",
                operation_id=operation_id,
                generation_job_id=generation_job_id,
                revision=revision,
                observed_at_ms=now_ms,
            )
            connection.execute(
                """
                INSERT INTO assets(
                    asset_id, logical_asset_id, parent_revision_id, project_id,
                    idempotency_key, request_digest, presentation_json, request_summary,
                    job_metadata_json, provenance_json, status, generation_job_id,
                    operation_id, locator, media_type, size_bytes, digest,
                    measured_progress, measured_progress_provenance, error_class,
                    retry_eligible, created_at_ms, updated_at_ms, trashed_at_ms,
                    trashed_by, revision, last_operation_id, last_event_sequence,
                    last_event_identity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id, logical_asset_id, parent_revision_id, project_id,
                    idempotency_key, request_digest, _asset_json_bytes(presentation, "asset presentation"),
                    request_summary, _asset_json_bytes(job_metadata, "asset job metadata"),
                    _asset_json_bytes(provenance, "asset provenance"), "queued", generation_job_id,
                    operation_id, None, None, None, None, None, None, None, 0,
                    now_ms, now_ms, None, None, revision, operation_id,
                    cursor["sequence"], cursor["identity"],
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            raise ConsoleError("asset reservation was written but could not be re-read")
        return self._public_asset_row(row)

    @staticmethod
    def _asset_expected_revision(value: Any) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ConsoleError("asset expected_revision must be a positive integer")
        return value

    def _asset_transition(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        operation_id: str,
        target_status: str,
        action: str,
        now_ms: int,
        measured_progress: float | None = None,
        measured_progress_provenance: str | None = None,
        error_class: str | None = None,
        retry_eligible: bool = False,
        allow_cancel: bool = False,
    ) -> dict[str, Any]:
        asset_id = _asset_id(asset_id, "asset_id")
        expected_revision = self._asset_expected_revision(expected_revision)
        operation_id = _asset_id(operation_id, "operation_id")
        target_status = _asset_id(target_status, "asset status").casefold()
        action = _asset_id(action, "asset transition action").casefold()
        now_ms = _asset_time(now_ms, "asset updated_at_ms")
        if target_status not in ASSET_STATUSES:
            raise ConsoleError("asset status is unsupported")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise ConsoleError("asset was not found")
            current_status = str(row["status"] or "").casefold()
            same_progress = (
                (row["measured_progress"] is None and measured_progress is None)
                or (
                    row["measured_progress"] is not None
                    and measured_progress is not None
                    and float(row["measured_progress"]) == float(measured_progress)
                )
            )
            same_progress_provenance = (row["measured_progress_provenance"] or None) == (measured_progress_provenance or None)
            if (
                str(row["last_operation_id"] or "") == operation_id
                and current_status == target_status
                and (target_status not in {"generating", "validating"} or (same_progress and same_progress_provenance))
                and (target_status != "failed" or (
                    str(row["error_class"] or "") == str(error_class or "")
                    and bool(row["retry_eligible"]) == bool(retry_eligible)
                ))
            ):
                connection.commit()
                return self._public_asset_row(row)
            if int(row["revision"]) != expected_revision:
                connection.rollback()
                raise ConsoleConflict("asset changed; reload before applying this transition")
            if target_status not in ASSET_GENERATION_TRANSITIONS.get(current_status, frozenset()):
                if not (allow_cancel and target_status == "cancelled" and current_status in ASSET_ACTIVE_STATUSES):
                    connection.rollback()
                    raise ConsoleError(f"asset transition {current_status}->{target_status} is not allowed")
            if target_status in {"generating", "validating"} and str(row["operation_id"]) != operation_id:
                connection.rollback()
                raise ConsoleConflict("asset transition operation does not match the retained generation operation")
            revision = int(row["revision"]) + 1
            cursor = self._append_asset_event(
                connection,
                asset_id=asset_id,
                logical_asset_id=str(row["logical_asset_id"]),
                project_id=str(row["project_id"]),
                action=action,
                from_status=current_status,
                to_status=target_status,
                operation_id=operation_id,
                generation_job_id=str(row["generation_job_id"]),
                revision=revision,
                observed_at_ms=now_ms,
                measured_progress=measured_progress,
                measured_progress_provenance=measured_progress_provenance,
                error_class=error_class,
                retry_eligible=retry_eligible,
                trashed_at_ms=None if row["trashed_at_ms"] is None else int(row["trashed_at_ms"]),
                trashed_by=row["trashed_by"],
            )
            updated_write = connection.execute(
                """
                UPDATE assets
                   SET status = ?, measured_progress = ?, measured_progress_provenance = ?,
                       error_class = ?, retry_eligible = ?, updated_at_ms = ?, revision = ?,
                       last_operation_id = ?, last_event_sequence = ?, last_event_identity = ?
                 WHERE asset_id = ? AND revision = ?
                """,
                (
                    target_status, measured_progress, measured_progress_provenance,
                    error_class, int(bool(retry_eligible)), now_ms, revision, operation_id,
                    cursor["sequence"], cursor["identity"], asset_id, expected_revision,
                ),
            )
            if updated_write.rowcount != 1:
                connection.rollback()
                raise ConsoleConflict("asset transition lost retained revision custody")
            connection.commit()
            updated = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if updated is None:
            raise ConsoleError("asset transition was written but could not be re-read")
        return self._public_asset_row(updated)

    def advance_asset_generation(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        operation_id: str,
        status: str,
        now_ms: int,
        measured_progress: Any = None,
        measured_progress_provenance: Any = None,
    ) -> dict[str, Any]:
        status = _asset_id(status, "asset status").casefold()
        if status not in {"generating", "validating"}:
            raise ConsoleError("asset generation transition must target generating or validating")
        progress, provenance = _asset_progress(measured_progress, measured_progress_provenance)
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT measured_progress, measured_progress_provenance FROM assets WHERE asset_id = ?", (_asset_id(asset_id, "asset_id"),)).fetchone()
        if row is None:
            raise ConsoleError("asset was not found")
        if progress is None and measured_progress is None:
            progress = row["measured_progress"]
            provenance = row["measured_progress_provenance"]
        return self._asset_transition(
            asset_id,
            expected_revision=expected_revision,
            operation_id=operation_id,
            target_status=status,
            action="generation",
            now_ms=now_ms,
            measured_progress=progress,
            measured_progress_provenance=provenance,
        )

    def fail_asset_generation(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        operation_id: str,
        error_class: str,
        retry_eligible: bool,
        now_ms: int,
    ) -> dict[str, Any]:
        if not isinstance(retry_eligible, bool):
            raise ConsoleError("asset retry_eligible must be boolean")
        return self._asset_transition(
            asset_id,
            expected_revision=expected_revision,
            operation_id=operation_id,
            target_status="failed",
            action="failure",
            now_ms=now_ms,
            error_class=_asset_error_class(error_class),
            retry_eligible=retry_eligible,
        )

    def cancel_asset_generation(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        operation_id: str,
        now_ms: int,
    ) -> dict[str, Any]:
        return self._asset_transition(
            asset_id,
            expected_revision=expected_revision,
            operation_id=operation_id,
            target_status="cancelled",
            action="cancel",
            now_ms=now_ms,
            allow_cancel=True,
        )

    def admit_asset_file(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        operation_id: str,
        locator: str,
        digest: str,
        provenance: dict[str, Any],
        now_ms: int,
        allowed_root: Path,
    ) -> dict[str, Any]:
        asset_id = _asset_id(asset_id, "asset_id")
        expected_revision = self._asset_expected_revision(expected_revision)
        operation_id = _asset_id(operation_id, "operation_id")
        locator = _safe_metadata_text(locator, "asset locator", maximum=4096)
        admitted_provenance = _asset_provenance(provenance, "asset admission provenance")
        if "admission" not in admitted_provenance:
            raise ConsoleError("asset admission provenance requires an admission receipt")
        digest = _safe_metadata_text(digest, "asset digest", maximum=64).casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ConsoleError("asset digest must be a SHA-256 hex digest")
        try:
            metadata = _media_metadata(locator, digest, allowed_root=allowed_root)
        except (ConsoleError, OSError) as exc:
            raise ConsoleError("asset file admission failed closed") from exc
        now_ms = _asset_time(now_ms, "asset updated_at_ms")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise ConsoleError("asset was not found")
            if (
                str(row["last_operation_id"] or "") == operation_id
                and str(row["status"] or "") == "ready"
            ):
                if str(row["digest"] or "") != metadata["digest"] or str(row["locator"] or "") != metadata["path"]:
                    connection.rollback()
                    raise ConsoleConflict("asset ready operation conflicts with retained file binding")
                connection.commit()
                return self._public_asset_row(row, allowed_root=allowed_root)
            if int(row["revision"]) != expected_revision:
                connection.rollback()
                raise ConsoleConflict("asset changed; reload before admitting its file")
            if str(row["operation_id"]) != operation_id or str(row["status"] or "") != "validating":
                connection.rollback()
                raise ConsoleError("asset file admission requires the retained validating operation")
            revision = int(row["revision"]) + 1
            cursor = self._append_asset_event(
                connection,
                asset_id=asset_id,
                logical_asset_id=str(row["logical_asset_id"]),
                project_id=str(row["project_id"]),
                action="admit",
                from_status="validating",
                to_status="ready",
                operation_id=operation_id,
                generation_job_id=str(row["generation_job_id"]),
                revision=revision,
                observed_at_ms=now_ms,
                measured_progress=None if row["measured_progress"] is None else float(row["measured_progress"]),
                measured_progress_provenance=row["measured_progress_provenance"],
                content_digest=metadata["digest"],
                content_media_type=metadata["media_type"],
            )
            updated_write = connection.execute(
                """
                UPDATE assets
                   SET status = 'ready', provenance_json = ?, locator = ?, media_type = ?,
                       size_bytes = ?, digest = ?, error_class = NULL, retry_eligible = 0,
                       updated_at_ms = ?, revision = ?, last_operation_id = ?,
                       last_event_sequence = ?, last_event_identity = ?
                 WHERE asset_id = ? AND revision = ?
                """,
                (
                    _asset_json_bytes(admitted_provenance, "asset admission provenance"), metadata["path"],
                    metadata["media_type"], metadata["size_bytes"], metadata["digest"], now_ms,
                    revision, operation_id, cursor["sequence"], cursor["identity"], asset_id, expected_revision,
                ),
            )
            if updated_write.rowcount != 1:
                connection.rollback()
                raise ConsoleConflict("asset ready admission lost retained revision custody")
            connection.commit()
            updated = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if updated is None:
            raise ConsoleError("asset ready admission was written but could not be re-read")
        return self._public_asset_row(updated, allowed_root=allowed_root)

    def retry_asset_generation(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        operation_id: str,
        generation_job_id: str,
        now_ms: int,
    ) -> dict[str, Any]:
        asset_id = _asset_id(asset_id, "asset_id")
        expected_revision = self._asset_expected_revision(expected_revision)
        operation_id = _asset_id(operation_id, "operation_id")
        generation_job_id = _asset_id(generation_job_id, "generation_job_id")
        now_ms = _asset_time(now_ms, "asset updated_at_ms")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise ConsoleError("asset was not found")
            if str(row["last_operation_id"] or "") == operation_id and str(row["status"] or "") == "queued":
                if str(row["generation_job_id"]) != generation_job_id:
                    connection.rollback()
                    raise ConsoleConflict("asset retry operation conflicts with retained generation job")
                connection.commit()
                return self._public_asset_row(row)
            if int(row["revision"]) != expected_revision:
                connection.rollback()
                raise ConsoleConflict("asset changed; reload before retrying generation")
            if str(row["status"] or "") != "failed" or not bool(row["retry_eligible"]):
                connection.rollback()
                raise ConsoleError("asset retry is unavailable for this retained failure")
            if operation_id == str(row["operation_id"]):
                connection.rollback()
                raise ConsoleError("asset retry requires a new operation_id")
            revision = int(row["revision"]) + 1
            cursor = self._append_asset_event(
                connection,
                asset_id=asset_id,
                logical_asset_id=str(row["logical_asset_id"]),
                project_id=str(row["project_id"]),
                action="retry",
                from_status="failed",
                to_status="queued",
                operation_id=operation_id,
                generation_job_id=generation_job_id,
                revision=revision,
                observed_at_ms=now_ms,
            )
            updated_write = connection.execute(
                """
                UPDATE assets
                   SET status = 'queued', generation_job_id = ?, operation_id = ?,
                       locator = NULL, media_type = NULL, size_bytes = NULL, digest = NULL,
                       measured_progress = NULL, measured_progress_provenance = NULL,
                       error_class = NULL, retry_eligible = 0, updated_at_ms = ?, revision = ?,
                       last_operation_id = ?, last_event_sequence = ?, last_event_identity = ?
                 WHERE asset_id = ? AND revision = ?
                """,
                (
                    generation_job_id, operation_id, now_ms, revision, operation_id,
                    cursor["sequence"], cursor["identity"], asset_id, expected_revision,
                ),
            )
            if updated_write.rowcount != 1:
                connection.rollback()
                raise ConsoleConflict("asset retry lost retained revision custody")
            connection.commit()
            updated = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if updated is None:
            raise ConsoleError("asset retry was written but could not be re-read")
        return self._public_asset_row(updated)

    def trash_asset(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        trashed_by: str,
        operation_id: str,
        now_ms: int,
    ) -> dict[str, Any]:
        return self._trash_restore_asset(
            asset_id,
            expected_revision=expected_revision,
            actor=trashed_by,
            operation_id=operation_id,
            now_ms=now_ms,
            trash=True,
        )

    def restore_asset(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        restored_by: str,
        operation_id: str,
        now_ms: int,
    ) -> dict[str, Any]:
        return self._trash_restore_asset(
            asset_id,
            expected_revision=expected_revision,
            actor=restored_by,
            operation_id=operation_id,
            now_ms=now_ms,
            trash=False,
        )

    def _trash_restore_asset(
        self,
        asset_id: str,
        *,
        expected_revision: int,
        actor: str,
        operation_id: str,
        now_ms: int,
        trash: bool,
    ) -> dict[str, Any]:
        asset_id = _asset_id(asset_id, "asset_id")
        expected_revision = self._asset_expected_revision(expected_revision)
        actor = _asset_id(actor, "asset actor")
        operation_id = _asset_id(operation_id, "asset operation_id")
        now_ms = _asset_time(now_ms, "asset updated_at_ms")
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise ConsoleError("asset was not found")
            is_trashed = row["trashed_at_ms"] is not None
            if str(row["last_operation_id"] or "") == operation_id and is_trashed == trash:
                connection.commit()
                return self._public_asset_row(row)
            if int(row["revision"]) != expected_revision:
                connection.rollback()
                raise ConsoleConflict("asset changed; reload before changing trash state")
            if is_trashed == trash:
                connection.commit()
                return self._public_asset_row(row)
            revision = int(row["revision"]) + 1
            trashed_at_ms = now_ms if trash else None
            trashed_by = actor if trash else None
            cursor = self._append_asset_event(
                connection,
                asset_id=asset_id,
                logical_asset_id=str(row["logical_asset_id"]),
                project_id=str(row["project_id"]),
                action="trash" if trash else "restore",
                from_status=str(row["status"]),
                to_status=str(row["status"]),
                operation_id=operation_id,
                generation_job_id=str(row["generation_job_id"]),
                revision=revision,
                observed_at_ms=now_ms,
                measured_progress=None if row["measured_progress"] is None else float(row["measured_progress"]),
                measured_progress_provenance=row["measured_progress_provenance"],
                error_class=row["error_class"],
                retry_eligible=bool(row["retry_eligible"]),
                trashed_at_ms=trashed_at_ms,
                trashed_by=trashed_by,
            )
            updated_write = connection.execute(
                """
                UPDATE assets
                   SET trashed_at_ms = ?, trashed_by = ?, updated_at_ms = ?, revision = ?,
                       last_operation_id = ?, last_event_sequence = ?, last_event_identity = ?
                 WHERE asset_id = ? AND revision = ?
                """,
                (
                    trashed_at_ms, trashed_by, now_ms, revision, operation_id,
                    cursor["sequence"], cursor["identity"], asset_id, expected_revision,
                ),
            )
            if updated_write.rowcount != 1:
                connection.rollback()
                raise ConsoleConflict("asset trash mutation lost retained revision custody")
            connection.commit()
            updated = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if updated is None:
            raise ConsoleError("asset trash mutation was written but could not be re-read")
        return self._public_asset_row(updated)

    def purge_assets(self, *, project_id: str | None = None) -> dict[str, Any]:
        if project_id not in (None, ""):
            _asset_id(project_id, "project_id")
        raise ConsoleError(f"asset purge is unavailable; retention_policy={ASSET_RETENTION_POLICY}")

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

    def prepare_health_repair(
        self,
        checks: list[dict[str, Any]],
        *,
        scope: str,
        acknowledge: bool,
        dry_run: bool,
        now_ms: int,
    ) -> dict[str, Any]:
        """Return one sanitized manual repair request; dry runs never persist or dispatch work."""
        if not isinstance(checks, list) or not checks:
            raise ConsoleError("repair requires at least one health check")
        if not isinstance(acknowledge, bool) or not isinstance(dry_run, bool):
            raise ConsoleError("acknowledge and dry_run must be booleans")
        if not dry_run and not acknowledge:
            raise ConsoleError("consequential repair preparation requires acknowledgement")
        scope = _safe_metadata_text(scope or "all", "scope", maximum=256)
        safe_checks: list[dict[str, Any]] = []
        for check in checks:
            if not isinstance(check, dict):
                raise ConsoleError("repair check must be an object")
            check_id = _safe_metadata_text(check.get("id"), "check_id", maximum=128)
            status = str(check.get("status") or "").strip().upper()
            if check_id is None or status not in HEALTH_CHECK_STATUSES:
                raise ConsoleError("repair check identity or status is invalid")
            if status == "PASS":
                raise ConsoleError("repair requires a non-PASS health check")
            evidence = check.get("evidence")
            if not isinstance(evidence, list) or any(
                not isinstance(item, str) or not item or len(item) > 128 for item in evidence
            ):
                raise ConsoleError("repair evidence must contain safe local pointers")
            safe_checks.append({
                "id": check_id,
                "status": status,
                "summary": _safe_metadata_text(check.get("summary"), "summary", maximum=512) or "",
                "evidence": list(dict.fromkeys(evidence))[:16],
                "recommended_action": _safe_metadata_text(
                    check.get("recommended_action"), "recommended_action", maximum=512
                ) or "Review the check manually.",
            })
        safe_checks.sort(key=lambda item: item["id"])
        material = {"scope": scope, "checks": safe_checks}
        digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        dedupe_key = f"manual-repair:{digest}"
        incident_key = f"manual-repair:{scope}:{digest[:32]}"
        payload = {
            "request_type": "diagnostics_repair",
            "scope": scope,
            "check_ids": [item["id"] for item in safe_checks],
            "checks": safe_checks,
            "dry_run": dry_run,
            "persistence": "preview_only" if dry_run else "health_requests",
            "acknowledged": acknowledge,
            "acknowledgement_required": True,
            "auto_dispatch": False,
            "dispatch_status": "NOT_DISPATCHED",
            "claim_limit": (
                "This request is a sanitized diagnostic handoff only. It does not edit source, config, databases, "
                "host tasks, listener/package state, secrets, providers, or execution authority."
            ),
        }
        now_ms = int(now_ms)
        request_id = f"health:manual:{digest[:32]}"
        if dry_run:
            return {
                "request_id": request_id,
                "incident_key": incident_key,
                "dedupe_key": dedupe_key,
                "request_type": "diagnostics_repair",
                "severity": "critical" if any(item["status"] == "FAIL" for item in safe_checks) else "warning",
                "scope": scope,
                "evidence_digest": digest,
                "payload": payload,
                "status": "PREVIEW",
                "previewed_at_ms": now_ms,
                "persistent": False,
                "deduplicated": False,
            }
        with self._lock, closing(self._connect()) as connection:
            existing = connection.execute(
                "SELECT * FROM health_requests WHERE dedupe_key=? AND status IN ('OPEN', 'CLAIMED', 'IN_PROGRESS')",
                (dedupe_key,),
            ).fetchone()
            if existing is not None:
                return {
                    **dict(existing),
                    "payload": json.loads(existing["payload_json"]),
                    "persistent": True,
                    "deduplicated": True,
                }
            if connection.execute(
                "SELECT 1 FROM health_requests WHERE request_id=?", (request_id,)
            ).fetchone() is not None:
                request_id = f"{request_id}:{now_ms}"
            connection.execute(
                """
                INSERT INTO health_requests(
                    request_id, incident_key, dedupe_key, request_type, severity, scope,
                    evidence_digest, payload_json, status, created_at_ms
                ) VALUES (?, ?, ?, 'diagnostics_repair', ?, ?, ?, ?, 'OPEN', ?)
                """,
                (
                    request_id,
                    incident_key,
                    dedupe_key,
                    "critical" if any(item["status"] == "FAIL" for item in safe_checks) else "warning",
                    scope,
                    digest,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    now_ms,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM health_requests WHERE request_id=?", (request_id,)
            ).fetchone()
        return {
            **dict(row),
            "payload": json.loads(row["payload_json"]),
            "persistent": True,
            "deduplicated": False,
        }

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

    def reset_ctrl_override(
        self,
        ctrl_id: str,
        *,
        expected_revision: int,
        operation_id: str,
        audit_payload: dict[str, Any],
        now_ms: int,
    ) -> dict[str, Any]:
        ctrl_id = _safe_metadata_text(ctrl_id, "ctrl_id", maximum=256)
        operation_id = _safe_metadata_text(operation_id, "operation_id", maximum=256)
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise ConsoleError("CTRL override revision is invalid")
        if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
            raise ConsoleError("config audit timestamp is invalid")
        _, audit_digest = self._config_encoded_payload(audit_payload)
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            retained_event = connection.execute(
                "SELECT payload_digest, config_commit_state FROM execution_event_receipts "
                "WHERE event_kind = ? AND identity = ?",
                (CONFIG_EVENT_KIND, operation_id),
            ).fetchone()
            if retained_event is not None:
                if str(retained_event["payload_digest"]) != audit_digest:
                    connection.rollback()
                    raise ConsoleConflict("config operation identity conflicts with retained audit content")
                state = str(retained_event["config_commit_state"] or CONFIG_TRANSACTION_COMMITTED)
                if state == CONFIG_TRANSACTION_COMMITTED:
                    connection.commit()
                    return {"ctrl_id": ctrl_id, "revision": 0, "override": {}, "reset": True, "replayed": True}
                connection.rollback()
                raise ConsoleConflict("config CTRL reset is not committed")
            row = connection.execute(
                "SELECT revision, fields_json FROM ctrl_overrides WHERE ctrl_id = ?",
                (ctrl_id,),
            ).fetchone()
            current_revision = 0 if row is None else int(row["revision"])
            if expected_revision != current_revision:
                connection.rollback()
                raise ConsoleConflict(
                    f"CTRL override revision conflict; expected {expected_revision}, current {current_revision}"
                )
            retained_fields = {} if row is None else json.loads(str(row["fields_json"]))
            if AUTO_CTRL_OVERRIDE_KEY in retained_fields:
                connection.execute(
                    "UPDATE ctrl_overrides SET revision = 0, fields_json = ?, updated_at_ms = ? WHERE ctrl_id = ?",
                    (
                        json.dumps({AUTO_CTRL_OVERRIDE_KEY: retained_fields[AUTO_CTRL_OVERRIDE_KEY]}, sort_keys=True),
                        now_ms,
                        ctrl_id,
                    ),
                )
            elif row is not None:
                connection.execute("DELETE FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,))
            self._retain_config_event_unlocked(
                connection, operation_id=operation_id, payload=audit_payload, now_ms=now_ms,
            )
            connection.commit()
        return {"ctrl_id": ctrl_id, "revision": 0, "override": {}, "reset": True, "replayed": False}

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

    def storage_stats(self) -> dict[str, Any]:
        paths = [self.path, self.path.with_name(self.path.name + "-wal"), self.path.with_name(self.path.name + "-shm")]
        size = sum(path.stat().st_size for path in paths if path.exists())
        with self._lock, closing(self._connect()) as connection:
            counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                "token_samples", "eta_forecasts", "task_progress_state", "task_progress_receipts", "task_progress_plans",
                    "task_progress_pulse_files", "proof_media", "assets", "proof_event_receipts", "ctrl_overrides",
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
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    bindings: dict[str, dict[str, Any]] = {}
    states: dict[str, str] = {}
    blocked: set[str] = set()
    for thread_id, row in rows.items():
        project, state = _canonical_project_binding(row, projects, project_roots)
        states[thread_id] = state
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
                states[thread_id] = "open_spawn_parent"
                break
            parent = parent_by_child.get(parent)
    return bindings, states


HOST_CTRL_CLASSIFICATION_SOURCES = frozenset({
    "host_threads.agent_role",
    "host_thread_spawn_edges.subagent",
})
TOPOLOGY_TERMINAL_STATES = frozenset({"ACCEPTED", "TOMBSTONED", "VERIFIED"})
TOPOLOGY_TIER = {"CTRL": 0, "LEAD": 1, "DOER": 2}
INDEPENDENT_HOST_PRESENTATION = {
    "manifest_id": "builtin:independent-host-task",
    "manifest_version": "1",
    "display_name": "Independent task",
    "title": "Codex task",
    "lucide_icon": "circle-user-round",
    "avatar": {"state": "ANONYMOUS", "variant_id": "neutral", "asset_digest": None},
    "profession": None,
    "structural_role": None,
    "swarm_authority": False,
}
TOPOLOGY_ACTIVITY_LABELS = {
    "BLOCK_CREATED": "Work started",
    "STATE_CHANGED": "State changed",
    "CURRENT_ACTION_CHANGED": "Current action updated",
    "PROGRESS_MEASURED": "Progress measured",
    "PROOF_ADMITTED": "Proof admitted",
    "WAIT_CHANGED": "Wait state changed",
    "REWORK_REQUESTED": "Rework requested",
    "RETRY_STARTED": "Retry started",
    "TAKEOVER_STARTED": "Takeover started",
    "ACCEPTED": "Work accepted",
}


def _topology_id(kind: str, *parts: str) -> str:
    encoded = json.dumps([kind, *parts], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"{kind}:{hashlib.sha256(encoded).hexdigest()}"


def _topology_activity_text(event_kind: str, lifecycle_state: str) -> str | None:
    label = TOPOLOGY_ACTIVITY_LABELS.get(event_kind)
    if label is None or not re.fullmatch(r"[A-Z][A-Z_]{1,31}", lifecycle_state):
        return None
    return f"{label} · {lifecycle_state.replace('_', ' ').title()}"[:64]


def _topology_payload(state: str, *, reason: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": state,
        "loading": state == "LOADING",
        "empty": True,
        "nodes": [],
        "tasks": [],
        "agent_edges": [],
        "task_edges": [],
        "independent_nodes": [],
        "host_edges": [],
        "independent_count": 0,
        "roots": [],
        "orphans": [],
        "hiddenTaskCount": 0,
        "cursor": None,
        "reason": reason,
        "authority": {"execution_authority": False},
    }


def _topology_cursor(payload: dict[str, Any], ledger_cursor: Any) -> dict[str, Any]:
    basis = {key: value for key, value in payload.items() if key != "cursor"}
    digest = hashlib.sha256(json.dumps(
        {"projection": basis, "ledger_cursor": ledger_cursor},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {"type": "overview_topology_v1", "digest": f"sha256:{digest}", "ledger": copy.deepcopy(ledger_cursor)}


def _controller_classification(
    row: sqlite3.Row,
    *,
    structural_host_ctrl: bool = False,
) -> dict[str, str | None]:
    """Classify CTRL from persisted role or bounded project-bound host spawn evidence."""
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


def _is_observed_ctrl_for_projection(controller: dict[str, Any]) -> bool:
    return (
        controller.get("controller_classification") == "swarm_ctrl"
        and controller.get("controller_classification_source") in HOST_CTRL_CLASSIFICATION_SOURCES
    )


def _is_authoritative_ctrl_for_execution(controller: dict[str, Any]) -> bool:
    return (
        controller.get("controller_classification") == "swarm_ctrl"
        and controller.get("controller_classification_source") == "host_threads.agent_role"
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
    parents_by_child: dict[str, set[str]] = {}
    statuses_by_child: dict[str, set[str]] = {}
    raw_children: dict[str, list[str]] = {}
    for edge in edge_rows:
        parent_id = str(edge["parent_thread_id"])
        child_id = str(edge["child_thread_id"])
        parents_by_child.setdefault(child_id, set()).add(parent_id)
        statuses_by_child.setdefault(child_id, set()).add(str(edge["status"] or "").strip().casefold())
        raw_children.setdefault(parent_id, []).append(child_id)
    parent_by_child = {
        child_id: next(iter(parent_ids))
        for child_id, parent_ids in parents_by_child.items()
        if len(parent_ids) == 1 and len(statuses_by_child.get(child_id, ())) == 1
    }
    edge_status = {
        child_id: next(iter(statuses_by_child[child_id]))
        for child_id in parent_by_child
    }
    open_parent_by_child = {
        child_id: parent_id for child_id, parent_id in parent_by_child.items()
        if edge_status.get(child_id) == "open"
    }
    project_bindings, project_binding_states = _thread_project_bindings(
        all_rows, open_parent_by_child, host_project_catalog, project_roots
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
    structural_controller_ids = {
        parent
        for parent, child_ids in raw_children.items()
        if parent in recent_ids
        and parent not in parents_by_child
        and not bool(all_rows[parent]["archived"])
        and str(all_rows[parent]["thread_source"] or "").strip().casefold()
        not in {"subagent", "internal_subagent"}
        and parent in project_bindings
        and any(
            child in recent_ids
            and parents_by_child.get(child) == {parent}
            and statuses_by_child.get(child) == {"open"}
            and edge_status.get(child) == "open"
            and not bool(all_rows[child]["archived"])
            and str(all_rows[child]["thread_source"] or "").strip().casefold()
            in {"subagent", "internal_subagent"}
            and project_bindings.get(child, {}).get("id") == project_bindings[parent]["id"]
            for child in set(child_ids)
            if child in all_rows
        )
    }
    root_candidate_ids = {
        parent
        for parent, child_ids in raw_children.items()
        if parent in all_rows
        and parent not in parents_by_child
        and (parent not in parsed_titles or parsed_titles[parent]["role"] == "ctrl")
        and any(
            child in recent_ids
            for child in child_ids
            if child in all_rows
        )
    }
    recent_parsed_ids = recent_ids.intersection(parsed_titles)
    controller_seed_ids = {
        thread_id
        for thread_id in recent_parsed_ids
        if parsed_titles[thread_id]["role"] == "ctrl"
    }.union(root_candidate_ids.intersection(recent_ids)).union(structural_controller_ids).union(
        active_goal_ids.intersection(all_rows)
    )
    included_ids = {
        thread_id for thread_id, row in all_rows.items()
        if not bool(row["archived"])
    }
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
            "project_binding_state": project_binding_states.get(thread_id, "unbound").upper(),
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
    for thread_id, node in list(nodes.items()):
        parent = open_parent_by_child.get(thread_id)
        if parent in nodes:
            links.append({
                "source": parent, "target": thread_id, "relationship": "delegated",
                "status": edge_status[thread_id],
            })
            continue

    for thread_id, node in nodes.items():
        parent = open_parent_by_child.get(thread_id)
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
        last_activity_at = max(
            (nodes[node_id]["updated_at"] or 0 for node_id in descendants),
            default=0,
        )
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
                "active_now": controller["status"] == "active",
                "recently_active": (
                    controller["status"] != "active"
                    and bool(last_activity_at)
                    and last_activity_at >= observed_after_ms
                ),
                "activity_status": (
                    "active"
                    if controller["status"] == "active"
                    else "recently_active"
                    if last_activity_at and last_activity_at >= observed_after_ms
                    else "inactive"
                ),
                "last_activity_at": last_activity_at or None,
                "activity_source": "host_threads.updated_at_ms+host_thread_spawn_edges.status",
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
        for index, item in enumerate(sorted(controllers, key=lambda item: (-item["nodes"], item["artifact"], item["id"])))
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
        "topology": _topology_payload("LOADING"),
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
        "controllers": sorted(controllers, key=lambda item: (-item["updated_at"], -item["nodes"], item["artifact"], item["id"])),
        "projects": sorted(projects.values(), key=_project_order_key),
        "analytics": {
            "swarms": len(roots),
            "tasks": sum(1 for node in nodes.values() if not node["virtual"]),
            "independent_count": 0,
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
            "Active means the observed CTRL host row was updated within two heartbeat windows; recently_active means its bounded host scope has activity within the 24-hour observation window. Neither proves CPU work.",
            "Tokens are local cumulative thread tokens, not billing or remaining quota.",
            "Usage history prefers local Codex JSONL token_count totals and falls back to the SQLite threads.tokens_used high-water aggregate; prompts, responses, tools, and credentials are not retained.",
            "Only title metadata needed to recognize SWARM naming is read; message bodies, previews, rollout content, credentials, and the logs database are not.",
            "Host titles never grant SWARM role or execution authority; without an exact admitted manifest join, a current task uses the shared neutral independent-host presentation.",
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
        self.builtin_role_avatar_assets = load_builtin_role_avatar_assets(
            SWARM_SKILL_ROOT / "assets" / "role-avatars"
        )
        self.builtin_role_manifests = load_builtin_role_manifests(
            SWARM_SKILL_ROOT / "roles",
            SWARM_SKILL_ROOT / "assets" / "role-avatars",
            avatar_assets=self.builtin_role_avatar_assets,
        )
        self.diagnostics_collector = DiagnosticsCollector(self.codex_home, self.store.path)
        self.token = secrets.token_urlsafe(24)
        self.write_lock = threading.Lock()
        self._recover_config_transactions()
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

    def _canonical_project_identities(self, project_id: str) -> frozenset[str]:
        self._canonical_project_root(project_id)
        database = state_database(self.codex_home)
        with closing(sqlite3.connect(database)) as connection:
            rows = connection.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,)).fetchall()
            if len(rows) != 1:
                raise ConsoleError("Project view requires one canonical saved project identity")
            name = str(rows[0][1] or "").strip()
            if not name:
                raise ConsoleError("Project view canonical saved project name is unavailable")
            duplicates = connection.execute("SELECT COUNT(*) FROM projects WHERE name = ?", (name,)).fetchone()[0]
        if duplicates != 1:
            raise ConsoleError("Project view canonical saved project name is ambiguous")
        return frozenset({project_id, name})

    def _asset_project_scope(self, project_id: Any) -> Path:
        """Bind an asset request to exactly one saved host project and root."""
        project_id = _asset_id(project_id, "project_id")
        database = state_database(self.codex_home)
        with closing(_readonly_connection(database)) as connection:
            projects = connection.execute(
                "SELECT id, name FROM projects WHERE id = ?",
                (project_id,),
            ).fetchall()
            roots = connection.execute(
                "SELECT path FROM project_roots WHERE project_id = ? ORDER BY position",
                (project_id,),
            ).fetchall()
        if len(projects) != 1 or not str(projects[0]["name"] or "").strip():
            raise ConsoleError("PROJECT_SCOPE_UNAVAILABLE")
        if len(roots) != 1:
            raise ConsoleError("PROJECT_ROOT_AMBIGUOUS")
        raw_root = roots[0]["path"]
        if not isinstance(raw_root, str) or not self._project_path_is_absolute(raw_root):
            raise ConsoleError("PROJECT_ROOT_UNAVAILABLE")
        return Path(raw_root)

    @staticmethod
    def _host_project_text(value: Any, maximum: int) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
            return None
        return value

    @staticmethod
    def _project_path_is_absolute(value: str) -> bool:
        try:
            path = Path(value)
        except (TypeError, ValueError, OSError):
            return False
        return path.is_absolute() or bool(re.match(r"^[A-Za-z]:[\\/]", value)) or value.startswith(("//", "\\\\"))

    def _host_project_records(
        self,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None, dict[str, set[str]]]:
        """Read the host saved-project tables without creating a local registry."""
        database = state_database(self.codex_home)
        with closing(_readonly_connection(database)) as connection:
            tables = {
                str(row["name"])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "projects" not in tables:
                return "UNKNOWN", [], None, {}
            project_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(projects)").fetchall()
            }
            if not {"id", "name"}.issubset(project_columns):
                return "UNKNOWN", [], None, {}
            selected = ["id", "name"]
            selected.extend(column for column in ("position", "created_at_ms", "updated_at_ms") if column in project_columns)
            project_rows = connection.execute(
                "SELECT " + ", ".join(selected) + " FROM projects"
            ).fetchall()
            records: list[dict[str, Any]] = []
            inventory_state = "KNOWN"
            for row in project_rows:
                project_id = self._host_project_text(row["id"], 256)
                display_name = self._host_project_text(row["name"], 256)
                if project_id is None or display_name is None:
                    inventory_state = "PARTIAL"
                    continue
                ordering = {
                    column: (
                        row[column]
                        if column in project_columns
                        and isinstance(row[column], int)
                        and not isinstance(row[column], bool)
                        else None
                    )
                    for column in ("position", "created_at_ms", "updated_at_ms")
                }
                records.append({
                    "id": project_id,
                    "name": display_name,
                    "display_name": display_name,
                    "ordering": ordering,
                    "_root_rows": [],
                })
            records_by_id = {record["id"]: record for record in records}
            root_owners: dict[str, set[str]] = {}
            if "project_roots" not in tables:
                inventory_state = "PARTIAL"
            else:
                root_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(project_roots)").fetchall()
                }
                if not {"project_id", "path"}.issubset(root_columns):
                    inventory_state = "PARTIAL"
                else:
                    root_select = ["project_id", "path"]
                    if "position" in root_columns:
                        root_select.append("position")
                    for row in connection.execute(
                        "SELECT " + ", ".join(root_select) + " FROM project_roots"
                    ).fetchall():
                        project_id = self._host_project_text(row["project_id"], 256)
                        raw_path = self._host_project_text(row["path"], 4096)
                        if project_id not in records_by_id or raw_path is None:
                            inventory_state = "PARTIAL"
                            continue
                        normalized = _normalized_project_path(raw_path)
                        absolute = bool(normalized) and self._project_path_is_absolute(raw_path)
                        if not absolute:
                            inventory_state = "PARTIAL"
                        root_row = {
                            "path": raw_path,
                            "normalized": normalized if absolute else "",
                            "position": (
                                int(row["position"])
                                if "position" in root_columns
                                and isinstance(row["position"], int)
                                and not isinstance(row["position"], bool)
                                else 0
                            ),
                            "valid": absolute,
                        }
                        records_by_id[project_id]["_root_rows"].append(root_row)
                        if absolute:
                            root_owners.setdefault(normalized, set()).add(project_id)
            records.sort(key=_project_order_key)
            cursor_basis = {
                "schema_version": 1,
                "projects": [
                    {
                        "id": record["id"],
                        "name": record["name"],
                        "ordering": record["ordering"],
                        "roots": [
                            {
                                "position": root["position"],
                                "path": root["normalized"],
                                "valid": root["valid"],
                            }
                            for root in sorted(
                                record["_root_rows"],
                                key=lambda item: (item["position"], item["normalized"], item["path"]),
                            )
                        ],
                    }
                    for record in records
                ],
                "project_roots_table": "project_roots" in tables,
            }
            cursor = {
                "type": "codex_project_roster_v1",
                "digest": _auto_digest(cursor_basis),
            }
            return inventory_state, records, cursor, root_owners

    @staticmethod
    def _project_root_availability(root: Path) -> str:
        try:
            if not root.exists():
                return "MISSING"
            if not root.is_dir():
                return "INVALID"
            if _is_reparse_point(root):
                return "INVALID"
        except OSError:
            return "UNKNOWN"
        return "AVAILABLE"

    @classmethod
    def _project_root_binding(
        cls,
        record: dict[str, Any],
        root_owners: dict[str, set[str]],
    ) -> dict[str, Any]:
        rows = list(record.get("_root_rows") or [])
        valid_rows = [row for row in rows if row.get("valid") and row.get("normalized")]
        if not rows:
            return {
                "status": "UNKNOWN", "value": None, "normalized": None,
                "availability": "UNKNOWN", "source": "codex.project_roots",
                "claim_limit": "The host saved project has no canonical root binding.",
            }
        if len(valid_rows) != len(rows):
            return {
                "status": "INVALID", "value": None, "normalized": None,
                "availability": "INVALID", "source": "codex.project_roots",
                "claim_limit": "The host project root binding contains an invalid path.",
            }
        normalized = {str(row["normalized"]) for row in valid_rows}
        if len(normalized) != 1:
            return {
                "status": "AMBIGUOUS", "value": None, "normalized": None,
                "availability": "UNKNOWN", "source": "codex.project_roots",
                "claim_limit": "The host saved project has more than one canonical root; identity is withheld.",
            }
        normalized_root = next(iter(normalized))
        if len(root_owners.get(normalized_root, set())) != 1:
            return {
                "status": "AMBIGUOUS", "value": None, "normalized": None,
                "availability": "UNKNOWN", "source": "codex.project_roots",
                "claim_limit": "The canonical root is shared by multiple saved projects; identity is withheld.",
            }
        selected = sorted(valid_rows, key=lambda row: (row["position"], row["path"]))[0]
        root = Path(str(selected["path"]))
        return {
            "status": "KNOWN",
            "value": str(selected["path"]),
            "normalized": normalized_root,
            "availability": cls._project_root_availability(root),
            "source": "codex.project_roots",
            "claim_limit": "The root string is read from the canonical Codex saved-project binding; filesystem availability is reported separately.",
        }

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
    def _project_view_link_from_text(text: str) -> tuple[str, dict[str, str] | None]:
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

    @staticmethod
    def _root_project_view_link(root: Path) -> tuple[str, dict[str, str] | None]:
        path = root / "SWARM.md"
        try:
            if not path.is_file() or path.stat().st_size > PROJECT_VIEW_MAX_BYTES:
                return "absent", None
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return "invalid", None
        return App._project_view_link_from_text(text)

    @staticmethod
    def _project_brief_from_text(
        text: str,
        *,
        project_id: str,
        display_name: str,
    ) -> tuple[str, str | None, str]:
        """Validate the canonical schema-1 SWARM.md brief without returning its contents."""
        if PROJECT_BRIEF_MARKER not in text:
            return "INVALID", None, "schema marker is missing"

        def reject_constant(value: str) -> None:
            raise ValueError(f"non-finite JSON constant: {value}")

        def finite_json(value: Any) -> bool:
            if isinstance(value, float):
                return math.isfinite(value)
            if isinstance(value, list):
                return all(finite_json(item) for item in value)
            if isinstance(value, dict):
                return all(
                    isinstance(key, str) and finite_json(item)
                    for key, item in value.items()
                )
            return True

        documents: list[dict[str, Any]] = []
        blocks = re.findall(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if len(blocks) != 1:
            return (
                "AMBIGUOUS" if len(blocks) > 1 else "INVALID",
                None,
                "the root does not contain exactly one canonical project brief",
            )
        for block in blocks:
            try:
                document = json.loads(block, parse_constant=reject_constant)
            except (TypeError, ValueError, json.JSONDecodeError):
                return "INVALID", None, "the brief JSON is invalid"
            if isinstance(document, dict) and PROJECT_BRIEF_REQUIRED_FIELDS.issubset(document):
                documents.append(document)
        if len(documents) != 1:
            return (
                "AMBIGUOUS" if len(documents) > 1 else "INVALID",
                None,
                "the root does not contain exactly one canonical project brief",
            )
        document = documents[0]
        if (
            not isinstance(document.get("schema_version"), int)
            or isinstance(document.get("schema_version"), bool)
            or document.get("schema_version") != 1
            or not finite_json(document)
        ):
            return "INVALID", None, "the project brief schema is unsupported"
        if not isinstance(document.get("updated_at"), str) or not document["updated_at"].strip():
            return "INVALID", None, "the project brief timestamp is invalid"
        for field in ("project", "objective", "repo", "authority", "ownership", "proof_acceptance"):
            if not isinstance(document.get(field), dict):
                return "INVALID", None, f"the project brief field {field} is invalid"
        for field in ("users_outcomes", "milestones", "decisions", "risks_blockers", "links"):
            if not isinstance(document.get(field), list):
                return "INVALID", None, f"the project brief field {field} is invalid"
        project = document["project"]
        brief_id = App._host_project_text(project.get("id"), 256)
        purpose = App._host_project_text(project.get("purpose"), 4096)
        if brief_id is None or purpose is None:
            return "INVALID", None, "the project brief identity is invalid"
        if brief_id.casefold() not in {project_id.casefold(), display_name.casefold()}:
            return "INVALID", None, "the project brief belongs to another saved project"
        digest = "sha256:" + hashlib.sha256(
            json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return "KNOWN", digest, ""

    def _project_manifest_projection(
        self,
        record: dict[str, Any],
        root_binding: dict[str, Any],
    ) -> dict[str, Any]:
        manifest = {
            "status": "UNAVAILABLE",
            "path": "SWARM.md",
            "digest": None,
            "source": "project_root/SWARM.md",
        }
        project_view = {
            "status": "UNAVAILABLE",
            "available": False,
            "manifest_status": "UNKNOWN",
            "manifest_digest": None,
            "identity": None,
        }
        artifact = {
            "status": "UNKNOWN",
            "kind": None,
            "id": None,
            "version": None,
            "digest": None,
            "source_digests": [],
        }
        logo = {
            "status": "UNKNOWN",
            "artifact": None,
            "source": "canonical_project_manifest_schema_v1",
            "claim_limit": "No canonical project logo binding is retained; no fallback logo is synthesized.",
        }
        if root_binding.get("status") != "KNOWN":
            return {
                "project_id": record["id"],
                "display_name": record["display_name"],
                "root": root_binding.get("value"),
                "root_binding": root_binding,
                "manifest": manifest,
                "project_view": project_view,
                "logo": logo,
                "artifact": artifact,
            }
        if root_binding.get("availability") != "AVAILABLE":
            manifest["status"] = "UNAVAILABLE"
            project_view["status"] = "UNAVAILABLE"
            project_view["manifest_status"] = "UNAVAILABLE"
            return {
                "project_id": record["id"],
                "display_name": record["display_name"],
                "root": root_binding.get("value"),
                "root_binding": root_binding,
                "manifest": manifest,
                "project_view": project_view,
                "logo": logo,
                "artifact": artifact,
            }

        root = Path(str(root_binding["value"]))
        path = root / "SWARM.md"
        try:
            if not path.exists():
                manifest["status"] = "MISSING"
                project_view["status"] = "ABSENT"
                project_view["manifest_status"] = "ABSENT"
                return {
                    "project_id": record["id"],
                    "display_name": record["display_name"],
                    "root": root_binding.get("value"),
                    "root_binding": root_binding,
                    "manifest": manifest,
                    "project_view": project_view,
                    "logo": logo,
                    "artifact": artifact,
                }
            if _is_reparse_point(path) or not path.is_file():
                raise ConsoleError("project manifest is not a regular file")
            if path.stat().st_size > PROJECT_VIEW_MAX_BYTES:
                raise ConsoleError("project manifest exceeds the delivery guard")
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            manifest["status"] = "MISSING"
            project_view["status"] = "ABSENT"
            project_view["manifest_status"] = "ABSENT"
            return {
                "project_id": record["id"],
                "display_name": record["display_name"],
                "root": root_binding.get("value"),
                "root_binding": root_binding,
                "manifest": manifest,
                "project_view": project_view,
                "logo": logo,
                "artifact": artifact,
            }
        except (ConsoleError, OSError, UnicodeError):
            manifest["status"] = "INVALID"
            project_view["status"] = "INVALID"
            project_view["manifest_status"] = "INVALID"
            return {
                "project_id": record["id"],
                "display_name": record["display_name"],
                "root": root_binding.get("value"),
                "root_binding": root_binding,
                "manifest": manifest,
                "project_view": project_view,
                "logo": logo,
                "artifact": artifact,
            }

        brief_status, brief_digest, _ = self._project_brief_from_text(
            text,
            project_id=record["id"],
            display_name=record["display_name"],
        )
        manifest["status"] = brief_status
        manifest["digest"] = brief_digest
        link_status, link = self._project_view_link_from_text(text)
        project_view["manifest_status"] = brief_status if brief_status != "KNOWN" else link_status.upper()
        project_view["manifest_digest"] = link.get("digest") if link else None
        if brief_status != "KNOWN":
            project_view["status"] = "INVALID"
        elif link_status == "absent":
            project_view["status"] = "ABSENT"
        elif link_status == "invalid":
            project_view["status"] = "INVALID"
        else:
            try:
                manifest_bytes = self._resolve_project_view_bytes(
                    record["id"], link["ref"], link["digest"],
                )
                projection = self._normalize_project_view(
                    record["id"], manifest_bytes, link["digest"],
                )
                identity = projection.get("identity") if isinstance(projection, dict) else None
                if not isinstance(identity, dict):
                    raise ConsoleError("project view identity is unavailable")
                project_view.update({
                    "status": "KNOWN",
                    "available": True,
                    "identity": copy.deepcopy(identity),
                })
                source_digests = identity.get("source_digests")
                artifact.update({
                    "status": "KNOWN",
                    "kind": "swarm.project_views",
                    "id": identity.get("manifest_id"),
                    "version": identity.get("manifest_version"),
                    "digest": identity.get("manifest_digest"),
                    "source_digests": list(source_digests) if isinstance(source_digests, list) else [],
                })
            except (ConsoleError, OSError, UnicodeError, ValueError, TypeError, sqlite3.Error):
                project_view["status"] = "UNAVAILABLE"
        return {
            "project_id": record["id"],
            "display_name": record["display_name"],
            "root": root_binding.get("value"),
            "root_binding": root_binding,
            "manifest": manifest,
            "project_view": project_view,
            "logo": logo,
            "artifact": artifact,
        }

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
        expected_projects = self._canonical_project_identities(project_id)
        try:
            has_port = parsed.port is not None
        except ValueError as exc:
            raise ConsoleError("project view source reference belongs to another project") from exc
        if (
            parsed.scheme != "project" or parsed.netloc not in expected_projects or parsed.params
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
        if any(source["kind"] not in PROJECT_VIEW_SOURCE_KINDS for source in normalized):
            raise ConsoleError("project view source kind is not registered")
        if len({source["ref"] for source in normalized}) != len(normalized):
            raise ConsoleError("project view source reference is duplicated")
        return normalized

    @classmethod
    def _project_view_definition(cls, view: Any) -> dict[str, Any]:
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
        default_source_kinds = {
            ("gallery", "grid"): "coverage.screens",
            ("canvas", "network"): "graph.mermaid",
            ("document", "blocks"): "document.blocks",
            ("timeline", "milestones"): "events.timeline",
        }
        default_source_kind = default_source_kinds.get((actual_renderer, actual_mode), "application.json")
        actions = view.get("allowed_actions", [])
        if not isinstance(actions, list) or len(actions) > 16 or any(action not in PROJECT_VIEW_ACTIONS for action in actions):
            raise ConsoleError("project view action is not registered")
        return {
            "id": view_id,
            "label": label,
            "renderer": actual_renderer,
            "mode": actual_mode,
            "sources": cls._project_view_sources(view, default_source_kind),
            "allowed_actions": list(dict.fromkeys(actions)),
        }

    @classmethod
    def _project_view_source_catalog(
        cls, manifest: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[tuple[str, str, str], dict[str, Any]]]:
        raw_sources = manifest.get("sources")
        if raw_sources is None:
            return [], {}
        if not isinstance(raw_sources, dict) or not raw_sources or len(raw_sources) > 128:
            raise ConsoleError("project view source catalog must be a bounded object")
        normalized: list[dict[str, Any]] = []
        by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
        refs: dict[str, tuple[str, str]] = {}
        source_ids: set[str] = set()

        def add_ref(kind: str, ref_value: Any, digest_value: Any) -> dict[str, str]:
            ref = cls._project_view_ref(ref_value)
            digest = cls._project_view_digest(digest_value)
            if ref in refs:
                previous_kind, previous_digest = refs[ref]
                if previous_digest != digest:
                    raise ConsoleError("project view source reference has conflicting digests")
                raise ConsoleError("project view source reference is duplicated")
            refs[ref] = (kind, digest)
            return {"kind": kind, "ref": ref, "digest": digest}

        for raw_id, raw_source in raw_sources.items():
            source_id = cls._project_view_text(raw_id, "source id", 256)
            if source_id in source_ids:
                raise ConsoleError("project view source identities must be unique")
            source_ids.add(source_id)
            if not isinstance(raw_source, dict) or not {"kind", "ref", "digest"}.issubset(raw_source):
                raise ConsoleError("project view source declaration is incomplete")
            kind = cls._project_view_text(raw_source.get("kind"), "source kind", 64)
            if kind not in PROJECT_VIEW_SOURCE_KINDS:
                raise ConsoleError("project view source kind is not registered")
            source = add_ref(kind, raw_source.get("ref"), raw_source.get("digest"))
            source_record: dict[str, Any] = {"id": source_id, **source}
            canonical_ref = raw_source.get("canonical_text_ref")
            canonical_digest = raw_source.get("canonical_text_digest")
            if canonical_ref is not None or canonical_digest is not None:
                if kind != "document.blocks" or canonical_ref is None or canonical_digest is None:
                    raise ConsoleError("project view canonical text binding is invalid")
                canonical = add_ref("document.text", canonical_ref, canonical_digest)
                canonical["id"] = f"{source_id}.canonical_text"
                source_record["canonical_text"] = canonical
            identity = (source["kind"], source["ref"], source["digest"])
            if identity in by_identity:
                raise ConsoleError("project view source declaration is duplicated")
            by_identity[identity] = source_record
            normalized.append(source_record)
        return normalized, by_identity

    @classmethod
    def _project_view_binding(cls, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ConsoleError("project view projection binding is invalid")
        required = {"accepted_scope_id", "accepted_cursor", "status", "reason"}
        if not required.issubset(value) or value.get("status") not in {"KNOWN", "PARTIAL", "UNKNOWN"}:
            raise ConsoleError("project view projection binding is invalid")
        scope_id = value.get("accepted_scope_id")
        if scope_id is not None:
            scope_id = cls._project_view_text(scope_id, "accepted scope id", 256)
        cursor = value.get("accepted_cursor")
        if cursor is not None and not isinstance(cursor, dict):
            raise ConsoleError("project view accepted cursor is invalid")
        binding = {
            "accepted_scope_id": scope_id,
            "accepted_cursor": copy.deepcopy(cursor),
            "status": value["status"],
            "reason": cls._project_view_text(value.get("reason"), "projection binding reason", 4096),
        }
        for key in ("source_manifest_id", "source_manifest_version", "source_manifest_digest", "unknown_policy"):
            if key in value:
                if key.endswith("_id") or key == "unknown_policy":
                    binding[key] = cls._project_view_text(value[key], f"projection binding {key}", 4096)
                elif key.endswith("_version"):
                    if not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < 1:
                        raise ConsoleError("project view projection binding version is invalid")
                    binding[key] = value[key]
                else:
                    binding[key] = cls._project_view_digest(value[key])
        return binding

    @staticmethod
    def _project_view_json(raw: bytes, label: str) -> dict[str, Any]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ConsoleError(f"project view {label} source must be bounded JSON") from exc
        if not isinstance(value, dict):
            raise ConsoleError(f"project view {label} source must be an object")
        return value

    @classmethod
    def _project_view_document(cls, raw: bytes) -> dict[str, Any]:
        source = cls._project_view_json(raw, "document")
        allowed = {"schema_version", "document_id", "version", "title", "snapshot_at", "canonical_text_ref", "blocks"}
        if not set(source).issubset(allowed) or source.get("schema_version") != 1:
            raise ConsoleError("project view document schema is unsupported")
        document_id = cls._project_view_text(source.get("document_id"), "document id")
        version = source.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ConsoleError("project view document version must be positive")
        canonical_text_ref = None
        if source.get("canonical_text_ref") is not None:
            canonical_text_ref = cls._project_view_ref(source.get("canonical_text_ref"))
        blocks = source.get("blocks")
        if not isinstance(blocks, list) or not blocks or len(blocks) > 128:
            raise ConsoleError("project view document blocks must be bounded")
        normalized: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, dict):
                raise ConsoleError("project view document block is invalid")
            block_type = cls._project_view_text(block.get("type"), "document block type", 32)
            if block_type == "heading":
                if set(block) != {"type", "level", "text"} or block.get("level") not in {2, 3, 4}:
                    raise ConsoleError("project view document heading is invalid")
                normalized.append({"type": block_type, "level": block["level"], "text": cls._project_view_text(block.get("text"), "document heading", 512)})
            elif block_type == "paragraph":
                if set(block) != {"type", "text"}:
                    raise ConsoleError("project view document paragraph is invalid")
                normalized.append({"type": block_type, "text": cls._project_view_text(block.get("text"), "document paragraph", 4096)})
            elif block_type == "list":
                items = block.get("items")
                if set(block) != {"type", "items"} or not isinstance(items, list) or not items or len(items) > 64:
                    raise ConsoleError("project view document list is invalid")
                normalized.append({"type": block_type, "items": [cls._project_view_text(item, "document list item", 1024) for item in items]})
            else:
                raise ConsoleError("project view document block type is unsupported")
        return {
            "schema_version": 1,
            "document_id": document_id,
            "version": version,
            "title": cls._project_view_text(source.get("title"), "document title", 256),
            "snapshot_at": cls._project_view_text(source.get("snapshot_at"), "document snapshot", 64),
            **({"canonical_text_ref": canonical_text_ref} if canonical_text_ref is not None else {}),
            "blocks": normalized,
        }

    @classmethod
    def _project_view_timeline(cls, raw: bytes) -> dict[str, Any]:
        source = cls._project_view_json(raw, "timeline")
        if set(source) != {"schema_version", "timeline_id", "version", "snapshot_at", "title", "events"} or source.get("schema_version") != 1:
            raise ConsoleError("project view timeline schema is unsupported")
        version = source.get("version")
        events = source.get("events")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ConsoleError("project view timeline version must be positive")
        if not isinstance(events, list) or not events or len(events) > 256:
            raise ConsoleError("project view timeline events must be bounded")
        normalized: list[dict[str, Any]] = []
        ids: set[str] = set()
        sequences: set[int] = set()
        for event in events:
            allowed = {"id", "label", "sequence", "status", "summary", "exit_criteria"}
            if not isinstance(event, dict) or set(event) != allowed:
                raise ConsoleError("project view timeline event is invalid")
            event_id = cls._project_view_text(event.get("id"), "timeline event id")
            sequence = event.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or not 0 <= sequence <= 1_000_000:
                raise ConsoleError("project view timeline identity or sequence is invalid")
            if event_id in ids or sequence in sequences:
                raise ConsoleError("project view timeline identity or sequence is invalid")
            ids.add(event_id)
            sequences.add(sequence)
            normalized.append({
                "id": event_id,
                "label": cls._project_view_text(event.get("label"), "timeline event label", 256),
                "sequence": sequence,
                "status": cls._project_view_text(event.get("status"), "timeline event status", 64),
                "summary": cls._project_view_text(event.get("summary"), "timeline event summary", 2048),
                "exit_criteria": cls._project_view_text(event.get("exit_criteria"), "timeline exit criteria", 2048),
            })
        normalized.sort(key=lambda item: (item["sequence"], item["id"]))
        return {
            "schema_version": 1,
            "timeline_id": cls._project_view_text(source.get("timeline_id"), "timeline id"),
            "version": version,
            "snapshot_at": cls._project_view_text(source.get("snapshot_at"), "timeline snapshot", 64),
            "title": cls._project_view_text(source.get("title"), "timeline title", 256),
            "events": normalized,
        }

    def _project_view_screens(self, project_id: str, raw: bytes) -> list[dict[str, Any]]:
        source = self._project_view_json(raw, "Screens")
        if source.get("project_id") is not None and source.get("project_id") not in self._canonical_project_identities(project_id):
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
    def _project_view_graph(
        cls, raw: bytes, screens: list[dict[str, Any]], *, require_screen_refs: bool = True,
    ) -> dict[str, Any]:
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
            required_graph = {"schema_version", "flowchart_id", "version", "nodes", "edges"}
            allowed_graph = required_graph | {"title", "authority"}
            if not required_graph.issubset(graph) or not set(graph).issubset(allowed_graph) or type(graph.get("schema_version")) is not int or graph["schema_version"] != 1:
                raise ConsoleError("project view Map JSON schema is unsupported")
            flowchart_id = cls._project_view_text(graph.get("flowchart_id"), "flowchart id")
            version = graph.get("version")
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise ConsoleError("project view Map version must be positive")
            graph_nodes = graph.get("nodes")
            graph_edges = graph.get("edges")
            if not isinstance(graph_nodes, list) or not isinstance(graph_edges, list) or len(graph_nodes) > 256 or len(graph_edges) > 512:
                raise ConsoleError("project view Map JSON is invalid")
            screen_identities = {screen["id"] for screen in screens}
            aliases: dict[str, set[str]] = {}
            for screen in screens:
                aliases.setdefault(screen["screen_id"], set()).add(screen["id"])
            normalized_nodes: dict[str, dict[str, Any]] = {}
            for node in graph_nodes:
                allowed_node = {"id", "label", "screen_ref", "parent_id", "group_id", "type", "visibility", "order", "layout"}
                if not isinstance(node, dict) or not set(node).issubset(allowed_node):
                    raise ConsoleError("project view Map node is invalid")
                node_id = cls._project_view_text(node.get("id"), "Map node id")
                if node_id in normalized_nodes:
                    raise ConsoleError("project view Map node identities must be unique")
                screen_ref = node.get("screen_ref")
                screen_key = None
                if screen_ref is not None:
                    screen_ref = cls._project_view_text(screen_ref, "Map screen ref")
                    candidates = {screen_ref} if screen_ref in screen_identities else aliases.get(screen_ref, set())
                    if len(candidates) != 1:
                        raise ConsoleError("project view Map screen ref is unknown or ambiguous")
                    screen_key = next(iter(candidates))
                node_type = cls._project_view_text(node.get("type") or "screen", "Map node type", 64)
                if require_screen_refs and screen_key is None and node_type not in {"group", "container"}:
                    raise ConsoleError("project view Map screen node requires an exact screen ref")
                visibility = cls._project_view_text(node.get("visibility") or "visible", "Map node visibility", 32)
                if visibility not in {"visible", "hidden", "conditional"}:
                    raise ConsoleError("project view Map node visibility is unsupported")
                order = node.get("order", 0)
                if not isinstance(order, int) or isinstance(order, bool) or not 0 <= order <= 10_000:
                    raise ConsoleError("project view Map node order is invalid")
                layout = node.get("layout")
                if layout is not None:
                    if not isinstance(layout, dict) or not set(layout).issubset({"x", "y", "width", "height"}) or any(
                        not isinstance(value, (int, float)) or isinstance(value, bool) or not -100_000 <= value <= 100_000
                        for value in layout.values()
                    ):
                        raise ConsoleError("project view Map node layout is invalid")
                normalized_nodes[node_id] = {
                    "id": node_id,
                    "label": cls._project_view_text(node.get("label") or node_id, "Map node label", 256),
                    "screen_key": screen_key,
                    "parent_id": node.get("parent_id"),
                    "group_id": node.get("group_id"),
                    "type": node_type,
                    "visibility": visibility,
                    "order": order,
                    **({"layout": layout} if layout is not None else {}),
                }
            for node in normalized_nodes.values():
                for field in ("parent_id", "group_id"):
                    if node[field] is not None:
                        node[field] = cls._project_view_text(node[field], f"Map node {field}")
                        if node[field] not in normalized_nodes or node[field] == node["id"]:
                            raise ConsoleError("project view Map grouping reference is invalid")
            edge_ids: set[str] = set()
            normalized_edges: list[dict[str, Any]] = []
            for edge in graph_edges:
                allowed_edge = {"id", "source", "target", "label", "type", "condition"}
                if not isinstance(edge, dict) or not set(edge).issubset(allowed_edge):
                    raise ConsoleError("project view Map edge is invalid")
                edge_id = cls._project_view_text(edge.get("id"), "Map edge id")
                if edge_id in edge_ids:
                    raise ConsoleError("project view Map edge identities must be unique")
                edge_ids.add(edge_id)
                source = cls._project_view_text(edge.get("source"), "Map edge source")
                target = cls._project_view_text(edge.get("target"), "Map edge target")
                if source not in normalized_nodes or target not in normalized_nodes:
                    raise ConsoleError("project view Map edge names an unknown node")
                normalized_edges.append({
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    **{
                        field: cls._project_view_text(edge[field], f"Map edge {field}", 256)
                        for field in ("label", "type", "condition") if edge.get(field) is not None
                    },
                })
            return {
                "schema_version": 1,
                "flowchart_id": flowchart_id,
                "version": version,
                **({"title": cls._project_view_text(graph.get("title"), "Map title", 256)} if graph.get("title") is not None else {}),
                "nodes": list(normalized_nodes.values()),
                "edges": normalized_edges,
            }
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
                if candidate:
                    projection_binding = candidate.get("projection_binding")
                    if projection_binding is None and candidate.get("requirements"):
                        projection_binding = candidate["requirements"]["projection_binding"]
                    projects.append({
                        "project_id": project["id"], "manifest_id": candidate["identity"]["manifest_id"],
                        "manifest_version": candidate["identity"]["manifest_version"], "manifest_digest": candidate["identity"]["manifest_digest"],
                        "conditional_tabs": [candidate["tab"]], "projection_binding": copy.deepcopy(projection_binding),
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
            if not project_id or projection is None:
                raise ConsoleError("project UI agent project projection is unavailable")
            context_projection = projection

            def require_requirements() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
                contract = projection.get("requirements")
                if not isinstance(contract, dict):
                    raise ConsoleError("project UI agent screen requirements are unavailable")
                binding = contract["projection_binding"]
                if (
                    binding.get("status") == "UNKNOWN" or binding.get("accepted_scope_id") is None
                    or binding.get("accepted_cursor") is None or "accepted_scope_id" not in payload
                    or "accepted_cursor" not in payload
                ):
                    raise ConsoleError("project UI agent projection binding is unavailable")
                if payload.get("accepted_scope_id") != binding.get("accepted_scope_id") or payload.get("accepted_cursor") != binding.get("accepted_cursor"):
                    raise ConsoleError("project UI agent request has a stale cursor")
                groups = contract["groups"]
                shared = contract["shared_requirements"]
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
                return binding, groups, requirements

            if operation == "project_views.get_normalized_manifest":
                if projection.get("requirements") is not None:
                    require_requirements()
                data = {
                    key: copy.deepcopy(projection[key])
                    for key in (
                        "identity", "tab", "modes", "views", "source_bindings", "screens", "map",
                        "requirements", "projection_binding", "authority", "claim_limit",
                    )
                }
            else:
                binding, groups, requirements = require_requirements()
                group_id = payload.get("group_id")
                requirement_id = payload.get("requirement_id")
                if operation == "project_views.list_screen_groups":
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
        binding = context_projection.get("projection_binding")
        if binding is None:
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
        if manifest.get("project_id") not in self._canonical_project_identities(project_id):
            raise ConsoleError("project view manifest belongs to another project")
        manifest_id = self._project_view_text(manifest.get("manifest_id"), "manifest id")
        manifest_digest = self._project_view_digest(manifest_digest)
        version = manifest.get("manifest_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ConsoleError("project view manifest version must be positive")
        registry = manifest.get("renderer_registry")
        if registry is not None:
            if not isinstance(registry, dict) or not isinstance(registry.get("registered"), list):
                raise ConsoleError("project view renderer registry is invalid")
            registered = registry["registered"]
            if (
                any(not isinstance(item, str) for item in registered)
                or len(registered) != len(set(registered))
                or set(registered) != set(PROJECT_VIEW_RENDERERS)
            ):
                raise ConsoleError("project view renderer registry is not the six registered renderers")
            if registry.get("unknown_renderer_behavior") not in (None, "FAIL_CLOSED") or registry.get("executable_components") not in (None, False):
                raise ConsoleError("project view renderer registry is not fail closed")
        tab = manifest.get("project_tab")
        if not isinstance(tab, dict) or tab.get("id") != "tab.project.ui" or tab.get("visibility") != "conditional":
            raise ConsoleError("project view manifest must declare one conditional project tab")
        tab_id = self._project_view_text(tab.get("id"), "tab id", 256)
        label = self._project_view_text(tab.get("label"), "tab label", 64)
        modes = tab.get("modes")
        if (
            not isinstance(modes, list) or not modes or len(modes) > 16
            or any(not isinstance(mode_id, str) or not mode_id.strip() for mode_id in modes)
            or len(set(modes)) != len(modes)
        ):
            raise ConsoleError("project view tab modes must be a bounded unique list")
        views = manifest.get("views")
        if not isinstance(views, list) or len(views) > 64:
            raise ConsoleError("project view manifest views must be bounded")
        definitions: dict[str, dict[str, Any]] = {}
        for candidate in views:
            if not isinstance(candidate, dict):
                raise ConsoleError("project view manifest view is invalid")
            definition = self._project_view_definition(candidate)
            if definition["id"] in definitions:
                raise ConsoleError("project view identities must be unique")
            definitions[definition["id"]] = definition
        if len(modes) != len(definitions) or any(mode_id not in definitions for mode_id in modes):
            raise ConsoleError("project view tab must list every declared view exactly once")

        catalog, catalog_by_identity = self._project_view_source_catalog(manifest)
        resolved: dict[tuple[str, str], bytes] = {}
        source_bindings: list[dict[str, Any]] = []
        source_digests: list[str] = []

        def resolve(source: dict[str, str]) -> bytes:
            key = (source["ref"], source["digest"])
            if key not in resolved:
                resolved[key] = self._resolve_project_view_bytes(project_id, *key)
            return resolved[key]

        if catalog:
            for source in catalog:
                resolve(source)
                binding = {key: source[key] for key in ("id", "kind", "ref", "digest")}
                source_bindings.append(binding)
                source_digests.append(source["digest"])
                if source.get("canonical_text") is not None:
                    canonical = source["canonical_text"]
                    resolve(canonical)
                    binding["canonical_text"] = copy.deepcopy(canonical)
                    source_bindings.append({
                        "id": canonical["id"],
                        "kind": canonical["kind"], "ref": canonical["ref"], "digest": canonical["digest"],
                    })
                    source_digests.append(canonical["digest"])

        selected_views = [definitions[mode_id] for mode_id in modes]
        used_refs: dict[str, str] = {}
        bound_views: list[dict[str, Any]] = []
        for view in selected_views:
            sources: list[dict[str, Any]] = []
            for source in view["sources"]:
                if catalog:
                    declared = catalog_by_identity.get((source["kind"], source["ref"], source["digest"]))
                    if declared is None:
                        raise ConsoleError("project view source is not declared by the manifest catalog")
                    bound = {"source_id": declared["id"], **source}
                else:
                    bound = dict(source)
                previous_digest = used_refs.get(bound["ref"])
                if previous_digest is not None:
                    if previous_digest != bound["digest"]:
                        raise ConsoleError("project view source reference has conflicting digests")
                    raise ConsoleError("project view source reference is duplicated")
                used_refs[bound["ref"]] = bound["digest"]
                resolve(bound)
                sources.append(bound)
            if len(sources) != 1:
                raise ConsoleError("project view renderer requires exactly one typed source")
            bound_views.append({**view, "sources": sources})

        screens: list[dict[str, Any]] = []
        screens_view = next((view for view in bound_views if (view["renderer"], view["mode"]) == ("gallery", "grid")), None)
        if screens_view is not None:
            screens_source = next((source for source in screens_view["sources"] if source["kind"] == "coverage.screens"), None)
            if screens_source is None or len(screens_view["sources"]) != 1:
                raise ConsoleError("project view Screens source kind is unsupported")
            screens = self._project_view_screens(project_id, resolved[(screens_source["ref"], screens_source["digest"])])

        projected_views: list[dict[str, Any]] = []
        canonical_map: dict[str, Any] | None = None
        for view in bound_views:
            source = view["sources"][0]
            raw = resolved[(source["ref"], source["digest"])]
            renderer_mode = (view["renderer"], view["mode"])
            if renderer_mode == ("gallery", "grid") and source["kind"] == "coverage.screens":
                content = {"screens": screens}
            elif renderer_mode == ("canvas", "network") and source["kind"] in {"graph.mermaid", "graph.json"}:
                require_screen_refs = False
                if source["kind"] == "graph.json":
                    graph_source = self._project_view_json(raw, "Map")
                    graph_nodes = graph_source.get("nodes")
                    require_screen_refs = isinstance(graph_nodes, list) and any(
                        isinstance(node, dict) and "screen_ref" in node for node in graph_nodes
                    )
                graph = self._project_view_graph(
                    raw, screens, require_screen_refs=require_screen_refs,
                )
                content = {"graph": graph}
                if canonical_map is None and any(node.get("screen_key") for node in graph.get("nodes", [])):
                    canonical_map = graph
            elif renderer_mode == ("document", "blocks") and source["kind"] == "document.blocks":
                document = self._project_view_document(raw)
                declared = catalog_by_identity.get((source["kind"], source["ref"], source["digest"])) if catalog else None
                canonical = declared.get("canonical_text") if declared else None
                if canonical is not None:
                    if document.get("canonical_text_ref") != canonical["ref"]:
                        raise ConsoleError("project view document canonical text reference does not match")
                    content = {
                        "document": document,
                        "canonical_text": {"ref": canonical["ref"], "digest": canonical["digest"]},
                    }
                else:
                    content = {"document": document}
            elif renderer_mode == ("timeline", "milestones") and source["kind"] == "events.timeline":
                content = {"timeline": self._project_view_timeline(raw)}
            else:
                raise ConsoleError("project view renderer mode or source kind is not supported by the shared projection")
            projected_views.append({
                "id": view["id"], "label": view["label"], "renderer": view["renderer"], "mode": view["mode"],
                "sources": [
                    {key: source[key] for key in ("source_id", "kind", "ref", "digest") if key in source}
                    for source in view["sources"]
                ],
                "allowed_actions": view["allowed_actions"], "content": content,
                "snapshot_only": renderer_mode in {("document", "blocks"), ("timeline", "milestones")},
            })
        requirements = self._project_view_requirements(manifest)
        binding = self._project_view_binding(manifest.get("projection_binding"))
        if not catalog:
            source_bindings = [
                {"kind": source["kind"], "ref": source["ref"], "digest": source["digest"]}
                for view in bound_views for source in view["sources"]
            ]
            source_digests = [source["digest"] for view in bound_views for source in view["sources"]]
        tab_output = {"id": tab_id.rsplit(".", 1)[-1], "label": label}
        if catalog:
            tab_output["manifest_id"] = tab_id
            tab_output["visibility"] = tab["visibility"]
        modes_output = []
        for view in projected_views:
            mode = {"id": view["id"].rsplit(".", 1)[-1], "label": view["label"]}
            if catalog:
                mode.update({"view_id": view["id"], "renderer": view["renderer"], "mode": view["mode"]})
            modes_output.append(mode)
        return {
            "schema_version": 1,
            "project_id": project_id,
            "tab": tab_output,
            "modes": modes_output,
            "views": projected_views,
            "source_bindings": source_bindings,
            "screens": screens,
            "map": canonical_map or {"nodes": [], "edges": []},
            "requirements": requirements,
            "projection_binding": copy.deepcopy(binding),
            "identity": {
                "manifest_id": manifest_id,
                "manifest_version": version,
                "manifest_digest": manifest_digest,
                "source_digests": source_digests,
            },
            "authority": {
                "kind": "project_manifest",
                "project_metadata_only": True,
                "runtime_status_authority": "existing_ledger_and_accepted_event_projections",
                "snapshot_views": [
                    view["id"] for view in projected_views if view["snapshot_only"]
                ],
            },
            "claim_limit": "Project Workspace is a read-only digest-bound snapshot; plan and timeline content is not runtime status authority, and Ledger plus accepted event projections remain authoritative.",
        }

    def _project_view_projection(
        self,
        project_id: str,
        project_briefs: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        def last_accepted() -> dict[str, Any] | None:
            cached = self._project_view_cache.get(project_id)
            if not isinstance(cached, dict):
                return None
            projection = copy.deepcopy(cached)
            projection["status"] = "STALE_LAST_ACCEPTED"
            return projection

        try:
            root = self._canonical_project_root(project_id)
        except (ConsoleError, OSError, sqlite3.Error):
            return last_accepted()
        try:
            raw_brief = self._read_project_view_handle(root, root / "SWARM.md")
            brief_text = raw_brief.decode("utf-8")
        except (ConsoleError, OSError, UnicodeError):
            return last_accepted()
        status, link = self._project_view_link_from_text(brief_text)
        if status == "absent":
            try:
                model, source_digest = parse_project_brief_markdown(brief_text)
                model_project_id = str(model["project"]["id"]).strip()
                if model_project_id.casefold() not in {
                    identity.casefold() for identity in self._canonical_project_identities(project_id)
                }:
                    raise ProjectModelError("project brief belongs to another saved project")
                if not model.get("proposed_lens_ids"):
                    self._project_view_cache.pop(project_id, None)
                    return None
                briefs = project_briefs if isinstance(project_briefs, dict) else self._project_briefs_projection()
                if briefs.get("state") != "KNOWN" or not briefs.get("available") or not isinstance(briefs.get("cursor"), dict):
                    raise ProjectModelError("accepted project briefs cursor is unavailable")
                matches = [
                    item for item in briefs.get("projects", [])
                    if isinstance(item, dict) and item.get("project_id") == project_id
                ]
                if len(matches) != 1 or matches[0].get("status") != "KNOWN" or matches[0].get("digest") != source_digest:
                    raise ProjectModelError("project brief projection is stale or mixed-scope")
                binding = {
                    "project_id": project_id,
                    "model_project_id": model_project_id,
                    "canonical_root": str(root.resolve()),
                    "brief_bytes_digest": "sha256:" + hashlib.sha256(raw_brief).hexdigest(),
                    "source_digest": source_digest,
                    "project_briefs_cursor": copy.deepcopy(briefs["cursor"]),
                    "locator": None,
                }
                projection = project_schema1_views(
                    model,
                    ArtifactIdentity(f"project-brief:{project_id}", source_digest, "schema-1-project-model"),
                    PROJECT_VIEW_RENDERERS,
                    PROJECT_VIEW_ACTIONS,
                    runtime_project_id=project_id,
                    projection_binding=binding,
                )
                if not projection.get("views"):
                    self._project_view_cache.pop(project_id, None)
                    return None
            except (ProjectModelError, ConsoleError, OSError, UnicodeError, ValueError, TypeError, sqlite3.Error):
                return last_accepted()
            self._project_view_cache[project_id] = projection
            return copy.deepcopy(projection)
        if status != "present" or link is None:
            return last_accepted()
        try:
            manifest_bytes = self._resolve_project_view_bytes(project_id, link["ref"], link["digest"])
            projection = self._normalize_project_view(project_id, manifest_bytes, link["digest"])
        except (ConsoleError, OSError, UnicodeError, ValueError, TypeError, sqlite3.Error):
            return last_accepted()
        self._project_view_cache[project_id] = projection
        return copy.deepcopy(projection)

    def _auto_scope(self, ctrl_id: str, project_id: str) -> dict[str, Any]:
        overview = self._host_overview()
        navigation = self._navigation_payload(overview)
        ctrl = next((item for item in navigation["controllers"] if item["id"] == ctrl_id), None)
        project = next((item for item in navigation["projects"] if item["id"] == project_id), None)
        if (
            ctrl is None or ctrl.get("project_id") != project_id
            or not _is_authoritative_ctrl_for_execution(ctrl)
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
            if _is_observed_ctrl_for_projection(controller)
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
        navigation = App._navigation_payload(overview)
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
        if isinstance(view.get("topology"), dict):
            view["topology"] = self._scope_topology_projection(
                view["topology"], selected_project_id, selected_ctrl_id if ctrl_scope else None,
            )
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
            "independent_count": sum(
                node.get("node_kind") == "independent_host_task" for node in nodes
            ),
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
        view["navigation"] = navigation
        view["overview_metrics"] = self._overview_metrics(
            view,
            scope_id=selected_ctrl_id if ctrl_scope else selected_project_id,
            scope_type="ctrl" if ctrl_scope else "project",
        )
        view["project_view"] = None if ctrl_scope else self._project_view_projection(
            selected_project_id,
            view.get("project_briefs"),
        )
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
                "active_now": bool(controller.get("active_now", controller.get("status") == "active")),
                "recently_active": bool(controller.get("recently_active", False)),
                "activity_status": str(
                    controller.get("activity_status")
                    or ("active" if controller.get("status") == "active" else "inactive")
                ).strip().casefold(),
                "last_activity_at": controller.get("last_activity_at", controller.get("updated_at")),
                "activity_source": controller.get(
                    "activity_source", "host_threads.updated_at_ms+host_thread_spawn_edges.status"
                ),
            }
            for controller in view.get("controllers", [])
        ]
        authoritative_controllers = [
            controller for controller in controllers
            if _is_observed_ctrl_for_projection(controller)
        ]
        visible_controllers = [controller for controller in authoritative_controllers if not controller["archived"]]
        active_controllers = [controller for controller in visible_controllers if controller["status"] == "active"]
        recently_active_controllers = [
            controller for controller in visible_controllers
            if controller["activity_status"] == "recently_active"
        ]
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
            recently_active_ids = [
                controller["id"] for controller in project_controllers
                if controller["activity_status"] == "recently_active"
            ]
            unavailable_candidate_ids = [
                controller["id"] for controller in controllers
                if controller.get("project_id") == project_id
                and not controller.get("archived", False)
                and not _is_observed_ctrl_for_projection(controller)
            ]
            project_nodes = [
                node for node in view.get("nodes", [])
                if node.get("project_id") == project_id and not node.get("virtual")
            ]
            active_project_nodes = [node for node in project_nodes if node.get("status") == "active"]
            independent_nodes = [
                node for node in project_nodes if node.get("node_kind") == "independent_host_task"
            ]
            activity_times = [controller.get("last_activity_at") for controller in project_controllers]
            activity_times.extend(node.get("updated_at") for node in project_nodes)
            last_activity_at = max(
                (value for value in activity_times if isinstance(value, int) and not isinstance(value, bool)),
                default=None,
            )
            stalled = any(
                controller["status"] in {"stalled", "blocked"}
                for controller in project_controllers
            ) or any(
                str(node.get("status") or "").casefold() in {"stalled", "blocked"}
                for node in project_nodes
            )
            active = bool(active_ids or active_project_nodes)
            status = "active" if active else ("stalled" if stalled else "inactive")
            projects.append({
                "id": project_id,
                "name": project.get("name", project_id),
                "goal_label": project.get("goal_label", project.get("name", project_id)),
                "label_source": project.get("label_source", "unknown"),
                "ordering": dict(project.get("ordering") or {}),
                "active_ctrl_id": active_ids[0] if active_ids else None,
                "active_ctrl": active,
                "active_ctrl_ids": active_ids,
                "recently_active_ctrl_ids": recently_active_ids,
                "active_now_count": len(active_project_nodes),
                "recently_active_count": len(recently_active_ids),
                "last_activity_at": last_activity_at,
                "activity_status": (
                    "active"
                    if active
                    else "recently_active"
                    if recently_active_ids
                    else "unknown"
                    if unavailable_candidate_ids
                    else "inactive"
                ),
                "activity_facts": {
                    "active_now": active,
                    "recently_active": bool(recently_active_ids),
                    "unknown": bool(unavailable_candidate_ids) and not active and not recently_active_ids,
                    "inactive": not active and not recently_active_ids and not unavailable_candidate_ids,
                    "active_now_count": len(active_project_nodes),
                    "recently_active_count": len(recently_active_ids),
                    "last_activity_at": last_activity_at,
                    "unknown_controller_ids": unavailable_candidate_ids,
                    "unknown_reason": (
                        "One or more project-bound host CTRL candidates lacked an accepted persisted role or "
                        "unambiguous structural classification."
                        if unavailable_candidate_ids else None
                    ),
                    "source": "host_threads.updated_at_ms+host_thread_spawn_edges.status",
                },
                "ctrl_ids": ctrl_ids,
                "project_eligibility": "swarm_ctrl" if ctrl_ids else "host_tasks" if project_nodes else "no_ctrl",
                "eligibility_source": (
                    "+".join(sorted({
                        str(controller["controller_classification_source"])
                        for controller in all_project_controllers
                    }))
                    if all_project_controllers
                    else "unavailable"
                ),
                "archived": False,
                "archive_source": "host_projects",
                "visibility": "visible",
                "status": status,
                "status_facts": {
                    "active": active,
                    "stalled": stalled,
                    "inactive": not active and not stalled,
                    "source": "host manifest admission+host_threads.archived+host_threads.updated_at_ms",
                },
                "status_source": "host_threads.updated_at_ms",
                "task_count": len(project_nodes),
                "independent_count": len(independent_nodes),
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
            "recently_active_ctrl_ids": [controller["id"] for controller in recently_active_controllers],
            "controllers": controllers,
            "projects": projects,
            "project_inventory": project_inventory,
            "claim_limit": (
                "Current Work eligibility requires persisted host agent_role=ctrl or bounded, open, project-bound host "
                "spawn evidence to an actual subagent. Titles and runtime status never establish CTRL identity. "
                "The structural projection may retain a recent open, project-bound host edge for activity display, "
                "but it never grants Auto or execution authority. Closed, ambiguous, or unbound rows fail closed as no_ctrl. Saved project inventory is sourced only from the host "
                "projects table; task metadata cannot create a project, and status facts remain read-only observation."
            ),
        }

    @staticmethod
    def _current_work_inventory(
        navigation: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        """Return the exact visible host-work inventory used by navigation."""
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
                or project.get("project_eligibility") not in {"swarm_ctrl", "host_tasks"}
                or not isinstance(raw_ctrl_ids, list)
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
                or not _is_observed_ctrl_for_projection(controller)
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

    def _topology_projection(self, view: dict[str, Any]) -> dict[str, Any]:
        """Join immutable manifests to observed edges and current Ledger blocks."""
        try:
            ledger = self.progress_ledger.replay()
            collections = (ledger.get("agent_manifests"), ledger.get("task_manifests"))
            if not all(isinstance(collection, dict) for collection in collections):
                raise ProgressEventError("identity manifest projection is invalid")
            creation_bindings = ledger.get("task_creation_bindings")
            if not isinstance(creation_bindings, dict):
                raise ProgressEventError("task creation binding projection is invalid")
            creation_by_task = {
                str(binding["task_id"]): binding
                for binding in creation_bindings.values()
                if isinstance(binding, dict)
            }
            if len(creation_by_task) != len(creation_bindings):
                raise ProgressEventError("task creation bindings are incomplete or ambiguous")
            scopes: set[tuple[str, str]] = set()
            for collection in collections:
                for state in collection.values():
                    if not isinstance(state, dict):
                        raise ProgressEventError("identity manifest state is invalid")
                    manifest = state.get("versions", {}).get(state.get("active_version"))
                    if not isinstance(manifest, dict):
                        raise ProgressEventError("identity manifest active version is invalid")
                    scopes.add((str(manifest.get("project_id") or ""), str(manifest.get("ctrl_id") or "")))
            source_nodes = {str(node.get("id") or ""): node for node in view.get("nodes", [])}
            observed_ctrl_ids = {
                str(controller.get("id") or "")
                for controller in view.get("controllers", [])
                if _is_observed_ctrl_for_projection(controller)
            }
            agents: dict[str, dict[str, Any]] = {}
            task_manifests: list[dict[str, Any]] = []
            creation_parent_edges: dict[str, dict[str, Any]] = {}
            rejected_bindings = 0

            for project_id, ctrl_id in sorted(scopes):
                identity = self.progress_ledger.project_identity_manifests(
                    project_id, ctrl_id, self.builtin_role_manifests,
                )
                for row in identity.get("agents", []):
                    manifest = row.get("manifest") if isinstance(row, dict) else None
                    agent_id = str(manifest.get("agent_id") or "") if isinstance(manifest, dict) else ""
                    host = source_nodes.get(agent_id)
                    structural_role = str(manifest.get("structural_role") or "") if isinstance(manifest, dict) else ""
                    exact_host_binding = (
                        isinstance(manifest, dict)
                        and row.get("binding_state") == "KNOWN"
                        and host is not None
                        and str(host.get("project_id") or "") == project_id
                        and structural_role in TOPOLOGY_TIER
                        and (structural_role != "CTRL" or agent_id in observed_ctrl_ids)
                        and agent_id not in agents
                    )
                    if not exact_host_binding:
                        rejected_bindings += 1
                        continue
                    agents[agent_id] = {
                        "record_type": "AGENT",
                        "id": agent_id,
                        "agent_id": agent_id,
                        "project_id": project_id,
                        "ctrl_id": ctrl_id,
                        "display_name": manifest["display_name"],
                        "title": manifest["title"],
                        "profession": manifest["profession"],
                        "profession_label": row.get("profession_label"),
                        "structural_role": structural_role,
                        "tier": TOPOLOGY_TIER[structural_role],
                        "source_order": None,
                        "sibling_order": None,
                        "depth": None,
                        "lucide_icon": row.get("resolved_lucide_icon"),
                        "avatar": copy.deepcopy(row.get("resolved_avatar")),
                        "accent": row.get("resolved_accent"),
                        "manifest_identity": {
                            "state": "KNOWN",
                            "manifest_id": manifest["manifest_id"],
                            "manifest_version": manifest["manifest_version"],
                            "manifest_digest": manifest["manifest_digest"],
                            "role_manifest_ref": copy.deepcopy(manifest["role_manifest_ref"]),
                        },
                        "parent_relation": {
                            "state": "UNKNOWN", "parent_agent_id": None,
                            "candidate_parent_ids": [], "reason": "MISSING_PARENT",
                        },
                        "hierarchy_membership": "UNBOUND",
                        "royal_line": False,
                        "children_ids": [],
                        "task_ids": [],
                        "visibleTaskCount": 0,
                        "hiddenTaskCount": 0,
                        "ports": [],
                        "input_port_ids": [],
                        "output_port_ids": [],
                        "activity": {
                            "status": str(host.get("status") or "UNKNOWN").upper(),
                            "online": host.get("status") == "active",
                            "observed_at_ms": host.get("updated_at") or None,
                            "source": "host_threads.updated_at_ms",
                            "execution_authority": False,
                        },
                        "live_projection": {
                            "state": "UNKNOWN", "status": None, "mini_update": None,
                            "context_rows": [], "event_cursor": None,
                            "reason": "MISSING_BOUND_EVENT_RECEIPT",
                        },
                        "detail_target": {
                            "agent_id": agent_id, "project_id": project_id, "ctrl_id": ctrl_id,
                        },
                    }
                for row in identity.get("tasks", []):
                    manifest = row.get("manifest") if isinstance(row, dict) else None
                    task_id = str(manifest.get("task_id") or "") if isinstance(manifest, dict) else ""
                    binding = creation_by_task.get(task_id)
                    if isinstance(manifest, dict) and row.get("binding_state") == "KNOWN" and binding is not None:
                        role_ref = binding.get("role_manifest_ref")
                        role_state = ledger.get("role_manifests", {}).get(
                            role_ref.get("manifest_id") if isinstance(role_ref, dict) else None,
                        )
                        role = (
                            role_state.get("versions", {}).get(role_ref.get("manifest_version"))
                            if isinstance(role_state, dict) and isinstance(role_ref, dict) else None
                        )
                        host = source_nodes.get(task_id)
                        structural_role = {
                            "CTRL_BOUNDED": "CTRL", "LEAD_SINGLE": "LEAD", "DOER_SINGLE": "DOER",
                        }.get(str(manifest.get("role_scope") or ""))
                        exact = (
                            host is not None
                            and str(host.get("project_id") or "") == project_id
                            and binding.get("project_id") == project_id
                            and role is not None
                            and role_manifest_reference(role) == role_ref
                            and structural_role in TOPOLOGY_TIER
                            and (structural_role != "CTRL" or task_id in observed_ctrl_ids)
                            and task_id not in agents
                        )
                        if not exact:
                            rejected_bindings += 1
                            continue
                        admitted = frozenset(item["asset_digest"] for item in role.get("avatar_variants", []))
                        agents[task_id] = {
                            "record_type": "AGENT", "id": task_id, "agent_id": task_id,
                            "project_id": project_id, "ctrl_id": ctrl_id,
                            "display_name": manifest["task_name"], "title": manifest["task_name"],
                            "profession": role["id"], "profession_label": role["name"],
                            "structural_role": structural_role, "tier": TOPOLOGY_TIER[structural_role],
                            "source_order": None, "sibling_order": None, "depth": None,
                            "lucide_icon": resolve_role_lucide_icon(role),
                            "avatar": resolve_role_avatar(
                                role, structural_role=structural_role, variant_id="canonical",
                                admitted_asset_digests=admitted,
                            ),
                            "accent": role["accent"],
                            "manifest_identity": {
                                "state": "KNOWN", "identity_kind": "TASK_CREATION_BINDING",
                                "manifest_id": manifest["manifest_id"],
                                "manifest_version": manifest["manifest_version"],
                                "manifest_digest": manifest["manifest_digest"],
                                "role_manifest_ref": copy.deepcopy(role_ref),
                                "binding_event_id": binding["event_id"],
                                "binding_event_digest": binding["event_digest"],
                            },
                            "creation_binding": {
                                "state": "KNOWN", "operation_id": binding["operation_id"],
                                "parent_edge": copy.deepcopy(binding["parent_edge"]),
                                "receipts": copy.deepcopy(binding["receipts"]),
                            },
                            "initial_work": {
                                "state": "KNOWN" if manifest["blocks"] else "EXPLICIT_EMPTY",
                                "milestones": copy.deepcopy(manifest["milestones"]),
                                "blocks": copy.deepcopy(manifest["blocks"]),
                            },
                            "parent_relation": {
                                "state": "UNKNOWN", "parent_agent_id": None,
                                "candidate_parent_ids": [], "reason": "MISSING_PARENT",
                            },
                            "hierarchy_membership": "UNBOUND", "royal_line": False,
                            "children_ids": [], "task_ids": [], "visibleTaskCount": 0,
                            "hiddenTaskCount": 0, "ports": [], "input_port_ids": [], "output_port_ids": [],
                            "activity": {
                                "status": str(host.get("status") or "UNKNOWN").upper(),
                                "online": host.get("status") == "active",
                                "observed_at_ms": host.get("updated_at") or None,
                                "source": "host_threads.updated_at_ms", "execution_authority": False,
                            },
                            "live_projection": {
                                "state": "UNKNOWN", "status": None, "mini_update": None,
                                "context_rows": [], "event_cursor": None,
                                "reason": "MISSING_BOUND_EVENT_RECEIPT",
                            },
                            "detail_target": {"agent_id": task_id, "project_id": project_id, "ctrl_id": ctrl_id},
                        }
                        creation_parent_edges[task_id] = binding["parent_edge"]
                    elif isinstance(manifest, dict) and row.get("binding_state") == "KNOWN":
                        task_manifests.append(manifest)
                    else:
                        rejected_bindings += 1

            for order, agent in enumerate(sorted(
                agents.values(),
                key=lambda item: (
                    item["project_id"], item["ctrl_id"], item["tier"],
                    str(item["display_name"]).casefold(), item["agent_id"],
                ),
            )):
                agent["source_order"] = order

            independent_nodes: dict[str, dict[str, Any]] = {}
            for order, host in enumerate(sorted(
                (node for node_id, node in source_nodes.items() if node_id not in agents),
                key=lambda node: (
                    str(node.get("project_id") or ""), int(node.get("updated_at") or 0),
                    str(node.get("id") or ""),
                ),
            )):
                node_id = str(host["id"])
                independent_nodes[node_id] = {
                    "record_type": "HOST_TASK",
                    "node_kind": "independent_host_task",
                    "id": node_id,
                    "agent_id": node_id,
                    "project_id": str(host.get("project_id") or ""),
                    "project_binding_state": str(host.get("project_binding_state") or "UNBOUND"),
                    "status": str(host.get("status") or "UNKNOWN").upper(),
                    "updated_at": host.get("updated_at"),
                    "source_order": order,
                    "presentation": copy.deepcopy(INDEPENDENT_HOST_PRESENTATION),
                    "ports": [], "input_port_ids": [], "output_port_ids": [],
                    "detail_target": {"surface": "agent_detail", "agent_id": node_id},
                    "actions": {"open_detail": True, "edit_manifest": False, "role_actions": False},
                    "execution_authority": False,
                    "swarm_authority": False,
                }

            parent_observations: dict[str, list[tuple[str, str]]] = {}
            for link in view.get("links", []):
                if not isinstance(link, dict):
                    rejected_bindings += 1
                    continue
                source, target = str(link.get("source") or ""), str(link.get("target") or "")
                if target in agents and target not in creation_parent_edges:
                    parent_observations.setdefault(target, []).append((
                        source, str(link.get("status") or "").strip().casefold(),
                    ))
            for task_id, parent_edge in creation_parent_edges.items():
                if parent_edge["state"] == "BOUND":
                    parent_observations[task_id] = [(parent_edge["parent_task_id"], "open")]

            provisional: dict[str, str] = {}
            for agent_id, agent in agents.items():
                observations = parent_observations.get(agent_id, [])
                candidates = sorted({source for source, _ in observations})
                statuses = {status for _, status in observations}
                relation = agent["parent_relation"]
                relation["candidate_parent_ids"] = candidates
                if not candidates and agent["structural_role"] == "CTRL":
                    relation.update({"state": "ROOT", "reason": None})
                    agent["hierarchy_membership"] = "ROOT"
                elif len(candidates) == 1 and statuses == {"open"}:
                    parent_id = candidates[0]
                    parent = agents.get(parent_id)
                    if (
                        parent is not None
                        and parent_id != agent_id
                        and (parent["project_id"], parent["ctrl_id"]) == (agent["project_id"], agent["ctrl_id"])
                    ):
                        provisional[agent_id] = parent_id
                    else:
                        relation["reason"] = "UNBOUND_OR_CROSS_SCOPE_PARENT"
                        rejected_bindings += 1
                elif len(candidates) > 1:
                    relation["reason"] = "AMBIGUOUS_PARENT"
                    rejected_bindings += 1
                else:
                    relation["reason"] = "UNSUPPORTED_EDGE_STATUS"
                    rejected_bindings += 1

            cycle_nodes: set[str] = set()
            for start in provisional:
                path: list[str] = []
                positions: dict[str, int] = {}
                current = start
                while current in provisional and current not in positions:
                    positions[current] = len(path)
                    path.append(current)
                    current = provisional[current]
                if current in positions:
                    cycle_nodes.update(path[positions[current]:])
            cycle_descendants = set(cycle_nodes)
            changed = True
            while changed:
                changed = False
                for child_id, parent_id in provisional.items():
                    if parent_id in cycle_descendants and child_id not in cycle_descendants:
                        cycle_descendants.add(child_id)
                        changed = True
            for agent_id in cycle_descendants:
                provisional.pop(agent_id, None)
                agents[agent_id]["parent_relation"].update({
                    "reason": "CYCLE" if agent_id in cycle_nodes else "ANCESTOR_CYCLE",
                    "state": "UNKNOWN",
                })
                agents[agent_id]["hierarchy_membership"] = "INVALID"
            rejected_bindings += len(cycle_descendants)

            agent_edges: list[dict[str, Any]] = []
            children: dict[str, list[str]] = {}
            for child_id, parent_id in provisional.items():
                child, parent = agents[child_id], agents[parent_id]
                child["parent_relation"].update({
                    "state": "KNOWN", "parent_agent_id": parent_id, "reason": None,
                })
                child["hierarchy_membership"] = "CHILD"
                child["royal_line"] = parent["structural_role"] == "CTRL"
                children.setdefault(parent_id, []).append(child_id)
            for parent_id, child_ids in children.items():
                child_ids.sort(key=lambda item: (agents[item]["source_order"], item))
                agents[parent_id]["children_ids"] = child_ids
                for sibling_order, child_id in enumerate(child_ids):
                    agents[child_id]["sibling_order"] = sibling_order
                    edge_id = _topology_id("agent-edge", parent_id, child_id)
                    agent_edges.append({
                        "id": edge_id, "edge_kind": "AGENT_CHILD",
                        "source": parent_id, "target": child_id,
                        "source_port_id": _topology_id("agent-child-output", parent_id, child_id),
                        "target_port_id": _topology_id("agent-parent-input", child_id, parent_id),
                        "execution_authority": False,
                    })

            roots = sorted(
                (agent_id for agent_id, agent in agents.items() if agent["parent_relation"]["state"] == "ROOT"),
                key=lambda item: (agents[item]["source_order"], item),
            )
            queue = [(root_id, 0) for root_id in roots]
            while queue:
                agent_id, depth = queue.pop(0)
                agents[agent_id]["depth"] = depth
                queue.extend((child_id, depth + 1) for child_id in children.get(agent_id, []))

            blocks = ledger.get("blocks", {})
            scope_versions = ledger.get("scopes", {})
            if not isinstance(blocks, dict) or not isinstance(scope_versions, dict):
                raise ProgressEventError("task ownership projection is invalid")
            valid_tasks_by_owner: dict[str, list[dict[str, Any]]] = {}
            valid_task_bindings: dict[str, dict[str, Any]] = {}
            agent_ids = set(agents)
            for manifest in task_manifests:
                task_id = str(manifest["task_id"])
                if task_id in agent_ids:
                    rejected_bindings += 1
                    continue
                scope_version = int(scope_versions.get(manifest["project_id"], 0) or 0)
                defined_blocks = {str(block["block_id"]) for block in manifest.get("blocks", [])}
                current = [
                    block for block in blocks.values()
                    if isinstance(block, dict)
                    and block.get("project_id") == manifest["project_id"]
                    and block.get("ctrl_id") == manifest["ctrl_id"]
                    and block.get("task_id") == task_id
                    and int(block.get("scope_version") or 0) == scope_version
                    and block.get("lifecycle_state") not in TOPOLOGY_TERMINAL_STATES
                ]
                if not current:
                    continue
                owners = {str(block.get("owner_id") or "") for block in current}
                owner_id = next(iter(owners)) if len(owners) == 1 else ""
                owner = agents.get(owner_id)
                exact = (
                    scope_version > 0
                    and owner is not None
                    and owner["hierarchy_membership"] != "INVALID"
                    and (owner["project_id"], owner["ctrl_id"]) == (manifest["project_id"], manifest["ctrl_id"])
                    and all(str(block.get("block_id") or "") in defined_blocks for block in current)
                )
                if not exact:
                    rejected_bindings += 1
                    continue
                current.sort(key=lambda block: (int(block.get("latest_event_seq") or 0), str(block.get("block_id") or "")))
                states = sorted({str(block.get("lifecycle_state") or "UNKNOWN") for block in current})
                latest = current[-1]
                task = {
                    "record_type": "TASK",
                    "id": task_id,
                    "task_id": task_id,
                    "task_name": manifest["task_name"],
                    "project_id": manifest["project_id"],
                    "ctrl_id": manifest["ctrl_id"],
                    "owning_agent_id": owner_id,
                    "state": states[0] if len(states) == 1 else "MIXED",
                    "manifest_identity": {
                        "state": "KNOWN", "manifest_id": manifest["manifest_id"],
                        "manifest_version": manifest["manifest_version"],
                        "manifest_digest": manifest["manifest_digest"],
                    },
                    "presentation_priority": int(manifest["policy"]["presentation_priority"]),
                    "order": None,
                    "ports": [],
                    "input_port_ids": [],
                    "output_port_ids": [],
                    "event_cursor": {
                        "event_seq": latest.get("latest_event_seq"),
                        "event_id": latest.get("latest_event_id"),
                        "event_digest": latest.get("latest_event_digest"),
                    },
                    "execution_authority": False,
                }
                measured = [block for block in current if block.get("committed_weight") is not None]
                denominator = sum(int(block.get("committed_weight") or 0) for block in measured)
                if len(measured) == len(current) and denominator > 0:
                    task["progress"] = round(
                        sum(int(block.get("admitted_proof_weight") or 0) for block in measured) * 100 / denominator, 2,
                    )
                valid_tasks_by_owner.setdefault(owner_id, []).append(task)
                valid_task_bindings[task_id] = {
                    "task": task,
                    "block_ids": {str(block.get("block_id") or "") for block in current},
                }

            tasks: list[dict[str, Any]] = []
            task_edges: list[dict[str, Any]] = []
            for owner_id, owner_tasks in valid_tasks_by_owner.items():
                owner_tasks.sort(key=lambda task: (task["presentation_priority"], task["task_id"]))
                visible = owner_tasks[:3]
                agents[owner_id]["task_ids"] = [task["task_id"] for task in visible]
                agents[owner_id]["visibleTaskCount"] = len(visible)
                agents[owner_id]["hiddenTaskCount"] = len(owner_tasks) - len(visible)
                for order, task in enumerate(visible):
                    task["order"] = order
                    tasks.append(task)
                    edge_id = _topology_id("task-edge", owner_id, task["task_id"])
                    task_edges.append({
                        "id": edge_id, "edge_kind": "AGENT_TASK_OWNERSHIP",
                        "source": owner_id, "target": task["task_id"],
                        "source_port_id": _topology_id("agent-task-output", owner_id, task["task_id"]),
                        "target_port_id": _topology_id("task-owner-input", task["task_id"], owner_id),
                        "execution_authority": False,
                    })
            tasks.sort(key=lambda task: (agents[task["owning_agent_id"]]["source_order"], task["order"], task["task_id"]))

            host_edges: list[dict[str, Any]] = []
            host_records = {**agents, **independent_nodes}
            for link in view.get("links", []):
                if not isinstance(link, dict) or str(link.get("status") or "").casefold() != "open":
                    continue
                source_id, target_id = str(link.get("source") or ""), str(link.get("target") or "")
                if target_id not in independent_nodes or source_id not in host_records:
                    continue
                if source_id in agents and agents[source_id]["hierarchy_membership"] == "INVALID":
                    continue
                edge_id = _topology_id("host-edge", source_id, target_id)
                host_edges.append({
                    "id": edge_id, "edge_kind": "HOST_SPAWN",
                    "source": source_id, "target": target_id,
                    "source_port_id": _topology_id("host-spawn-output", source_id, target_id),
                    "target_port_id": _topology_id("host-parent-input", target_id, source_id),
                    "execution_authority": False,
                    "swarm_authority": False,
                })

            activity_by_owner: dict[str, list[dict[str, Any]]] = {}
            for project_id in sorted({
                task["project_id"] for owner_tasks in valid_tasks_by_owner.values() for task in owner_tasks
            }):
                feed = self.progress_ledger.feed_snapshot(project_id, limit=10)
                for item in feed.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    binding = valid_task_bindings.get(str(item.get("task_id") or ""))
                    owner_id = str(item.get("owner_id") or "")
                    text = _topology_activity_text(
                        str(item.get("event_kind") or ""), str(item.get("lifecycle_state") or ""),
                    )
                    if (
                        binding is None or text is None or owner_id not in agents
                        or binding["task"]["owning_agent_id"] != owner_id
                        or str(item.get("block_id") or "") not in binding["block_ids"]
                    ):
                        continue
                    cursor = {
                        "event_seq": item.get("event_seq"),
                        "event_id": item.get("event_id"),
                        "event_digest": item.get("event_digest"),
                    }
                    if not all(cursor.values()):
                        continue
                    task = binding["task"]
                    activity_by_owner.setdefault(owner_id, []).append({
                        "text": text,
                        "identity": {
                            "agent_id": owner_id,
                            "agent_manifest_id": agents[owner_id]["manifest_identity"]["manifest_id"],
                            "task_id": task["task_id"],
                            "task_manifest_id": task["manifest_identity"]["manifest_id"],
                            "role_manifest_id": agents[owner_id]["manifest_identity"]["role_manifest_ref"]["manifest_id"],
                            "role_manifest_version": agents[owner_id]["manifest_identity"]["role_manifest_ref"]["manifest_version"],
                        },
                        "event_kind": item["event_kind"],
                        "lifecycle_state": item["lifecycle_state"],
                        "observed_at_ms": item.get("observed_at_ms"),
                        "event_cursor": cursor,
                    })
            for owner_id, rows in activity_by_owner.items():
                rows.sort(
                    key=lambda row: (
                        int(row["event_cursor"]["event_seq"] or 0),
                        str(row["event_cursor"]["event_id"] or ""),
                    ),
                    reverse=True,
                )
                retained = rows[:3 if agents[owner_id]["structural_role"] == "CTRL" else 1]
                latest = retained[0]
                agents[owner_id]["live_projection"] = {
                    "state": "KNOWN",
                    "status": latest["lifecycle_state"],
                    "mini_update": latest["text"],
                    "context_rows": retained,
                    "event_cursor": latest["event_cursor"],
                    "reason": None,
                }

            records: dict[str, dict[str, Any]] = {
                **agents, **independent_nodes, **{task["id"]: task for task in tasks},
            }
            for edge in [*agent_edges, *task_edges, *host_edges]:
                source, target = records[edge["source"]], records[edge["target"]]
                source["ports"].append({
                    "id": edge["source_port_id"], "direction": "output",
                    "edge_kind": edge["edge_kind"], "edge_id": edge["id"],
                })
                source["output_port_ids"].append(edge["source_port_id"])
                target["ports"].append({
                    "id": edge["target_port_id"], "direction": "input",
                    "edge_kind": edge["edge_kind"], "edge_id": edge["id"],
                })
                target["input_port_ids"].append(edge["target_port_id"])
            for record in records.values():
                record["ports"].sort(key=lambda port: (port["direction"], port["edge_kind"], port["edge_id"]))
                record["input_port_ids"].sort()
                record["output_port_ids"].sort()
                record["port_count"] = len(record["ports"])

            def recursive(agent_id: str) -> dict[str, Any]:
                node = copy.deepcopy(agents[agent_id])
                node["children"] = [recursive(child_id) for child_id in children.get(agent_id, [])]
                return node

            orphan_ids = sorted(
                (
                    agent_id for agent_id, agent in agents.items()
                    if agent["parent_relation"]["state"] == "UNKNOWN"
                    and agent["hierarchy_membership"] != "INVALID"
                ),
                key=lambda item: (agents[item]["source_order"], item),
            )
            payload = {
                "schema_version": 1,
                "state": "PARTIAL" if rejected_bindings or orphan_ids else "KNOWN",
                "loading": False,
                "empty": not agents and not tasks and not independent_nodes,
                "nodes": sorted(agents.values(), key=lambda agent: (agent["source_order"], agent["agent_id"])),
                "tasks": tasks,
                "agent_edges": sorted(agent_edges, key=lambda edge: (agents[edge["source"]]["source_order"], agents[edge["target"]]["source_order"], edge["id"])),
                "task_edges": sorted(task_edges, key=lambda edge: (agents[edge["source"]]["source_order"], records[edge["target"]]["order"], edge["id"])),
                "independent_nodes": sorted(
                    independent_nodes.values(),
                    key=lambda node: (node["project_id"], node["source_order"], node["id"]),
                ),
                "host_edges": sorted(host_edges, key=lambda edge: (edge["source"], edge["target"], edge["id"])),
                "independent_count": len(independent_nodes),
                "roots": [recursive(agent_id) for agent_id in roots],
                "orphans": [recursive(agent_id) for agent_id in orphan_ids],
                "hiddenTaskCount": sum(agent["hiddenTaskCount"] for agent in agents.values()),
                "cursor": None,
                "reason": "MISSING_OR_CONFLICTING_BINDING" if rejected_bindings or orphan_ids else None,
                "ordering": {
                    "agents": "manifest_tier_display_name_then_agent_id",
                    "tasks": "manifest_presentation_priority_then_task_id",
                    "tiers": ["CTRL", "LEAD", "DOER"],
                    "max_visible_tasks_per_agent": 3,
                },
                "authority": {"execution_authority": False},
            }
            if not agents and not independent_nodes:
                payload["state"] = "UNKNOWN" if rejected_bindings else "EMPTY"
            payload["cursor"] = _topology_cursor(payload, ledger.get("cursor"))
            return payload
        except (ProgressEventError, KeyError, TypeError, ValueError):
            unknown = _topology_payload("UNKNOWN", reason="INVALID_OR_UNAVAILABLE_MANIFEST_LEDGER")
            unknown["loading"] = False
            return unknown

    @staticmethod
    def _scope_topology_projection(
        topology: dict[str, Any], project_id: str, root_agent_id: str | None = None,
    ) -> dict[str, Any]:
        if topology.get("state") == "LOADING":
            return copy.deepcopy(topology)
        scoped = copy.deepcopy(topology)
        project_nodes = [node for node in topology.get("nodes", []) if node.get("project_id") == project_id]
        allowed_ids = {node["id"] for node in project_nodes}
        if root_agent_id is not None:
            descendants = {root_agent_id}
            changed = True
            while changed:
                changed = False
                for edge in topology.get("agent_edges", []):
                    if edge.get("source") in descendants and edge.get("target") not in descendants:
                        descendants.add(edge["target"])
                        changed = True
            allowed_ids.intersection_update(descendants)
        nodes = [node for node in project_nodes if node["id"] in allowed_ids]
        node_ids = {node["id"] for node in nodes}
        tasks = [task for task in topology.get("tasks", []) if task.get("owning_agent_id") in node_ids]
        task_ids = {task["id"] for task in tasks}
        independent_nodes = [
            node for node in topology.get("independent_nodes", [])
            if node.get("project_id") == project_id
        ]
        independent_ids = {node["id"] for node in independent_nodes}
        if root_agent_id is not None:
            reachable = {root_agent_id}
            changed = True
            while changed:
                changed = False
                for edge in topology.get("host_edges", []):
                    if edge.get("source") in reachable and edge.get("target") not in reachable:
                        reachable.add(edge["target"])
                        changed = True
            independent_nodes = [node for node in independent_nodes if node["id"] in reachable]
            independent_ids = {node["id"] for node in independent_nodes}
        agent_edges = [
            edge for edge in topology.get("agent_edges", [])
            if edge.get("source") in node_ids and edge.get("target") in node_ids
        ]
        task_edges = [
            edge for edge in topology.get("task_edges", [])
            if edge.get("source") in node_ids and edge.get("target") in task_ids
        ]
        host_edges = [
            edge for edge in topology.get("host_edges", [])
            if edge.get("source") in node_ids | independent_ids
            and edge.get("target") in independent_ids
        ]
        children: dict[str, list[str]] = {}
        for edge in agent_edges:
            children.setdefault(edge["source"], []).append(edge["target"])
        by_id = {node["id"]: node for node in nodes}

        def recursive(agent_id: str) -> dict[str, Any]:
            node = copy.deepcopy(by_id[agent_id])
            node["children"] = [recursive(child_id) for child_id in children.get(agent_id, [])]
            return node

        root_ids = [node["id"] for node in nodes if node.get("parent_relation", {}).get("state") == "ROOT"]
        orphan_ids = [
            node["id"] for node in nodes
            if node.get("parent_relation", {}).get("state") == "UNKNOWN"
            and node.get("hierarchy_membership") != "INVALID"
        ]
        invalid_ids = [
            node["id"] for node in nodes
            if node.get("hierarchy_membership") == "INVALID"
        ]
        partial = bool(orphan_ids or invalid_ids)
        scoped.update({
            "nodes": nodes, "tasks": tasks, "agent_edges": agent_edges, "task_edges": task_edges,
            "independent_nodes": independent_nodes, "host_edges": host_edges,
            "independent_count": len(independent_nodes),
            "roots": [recursive(agent_id) for agent_id in root_ids],
            "orphans": [recursive(agent_id) for agent_id in orphan_ids],
            "hiddenTaskCount": sum(int(node.get("hiddenTaskCount") or 0) for node in nodes),
            "empty": not nodes and not tasks and not independent_nodes,
            "state": "EMPTY" if not nodes and not tasks and not independent_nodes else "PARTIAL" if partial else "KNOWN",
            "reason": "MISSING_OR_CONFLICTING_BINDING" if partial else None,
            "cursor": None,
        })
        ledger_cursor = (topology.get("cursor") or {}).get("ledger")
        scoped["cursor"] = _topology_cursor(scoped, ledger_cursor)
        return scoped

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
        progress = self._progress_payload(view)
        view["navigation"] = self._navigation_payload(view)
        view["overview_metrics"] = self._overview_metrics(view, scope_id="all", scope_type="all")
        view["topology"] = self._topology_projection(view)
        admitted = {node["id"]: node for node in view["topology"].get("nodes", [])}
        for node in view.get("nodes", []):
            identity = admitted.get(node["id"])
            if identity is None:
                node.update({
                    "node_kind": "independent_host_task",
                    "role": "independent", "role_label": "TASK", "worker_role": "",
                    "icon": "", "title": INDEPENDENT_HOST_PRESENTATION["title"],
                    "artifact": INDEPENDENT_HOST_PRESENTATION["title"], "worker": "",
                    "presentation": copy.deepcopy(INDEPENDENT_HOST_PRESENTATION),
                    "manifest_identity": None, "profession": None, "structural_role": None,
                    "controller_ids": [],
                    "detail_target": {"surface": "agent_detail", "agent_id": node["id"]},
                    "actions": {"open_detail": True, "edit_manifest": False, "role_actions": False},
                    "execution_authority": False, "swarm_authority": False,
                })
            else:
                node.update({
                    "node_kind": "swarm_agent",
                    "role": identity["structural_role"].casefold(),
                    "role_label": identity["structural_role"],
                    "icon": identity["lucide_icon"],
                    "title": identity["title"], "artifact": identity["title"], "worker": "",
                    "presentation": {
                        "display_name": identity["display_name"], "title": identity["title"],
                        "lucide_icon": identity["lucide_icon"], "avatar": copy.deepcopy(identity["avatar"]),
                    },
                    "manifest_identity": copy.deepcopy(identity["manifest_identity"]),
                    "profession": identity["profession"],
                    "structural_role": identity["structural_role"],
                    "detail_target": copy.deepcopy(identity["detail_target"]),
                    "actions": {"open_detail": True, "edit_manifest": True, "role_actions": True},
                    "execution_authority": False, "swarm_authority": False,
                })
        admitted_ids = set(admitted)
        view["controllers"] = [
            controller for controller in view.get("controllers", [])
            if controller.get("id") in admitted_ids
            and admitted[controller["id"]]["structural_role"] == "CTRL"
        ]
        for link in view.get("links", []):
            link["relationship"] = (
                "delegated" if link.get("source") in admitted_ids and link.get("target") in admitted_ids
                else "host_spawn"
            )
            link["execution_authority"] = False
        view["roots"] = [controller["id"] for controller in view["controllers"]]
        for project in view.get("projects", []):
            project_nodes = [node for node in view["nodes"] if node.get("project_id") == project["id"]]
            project["nodes"] = len(project_nodes)
            project["task_count"] = len(project_nodes)
            project["independent_count"] = sum(
                node.get("node_kind") == "independent_host_task" for node in project_nodes
            )
            project["active"] = sum(node.get("status") == "active" for node in project_nodes)
        view["analytics"]["tasks"] = sum(not node.get("virtual") for node in view["nodes"])
        view["analytics"]["independent_count"] = sum(
            node.get("node_kind") == "independent_host_task" for node in view["nodes"]
        )
        view["analytics"]["roles"] = dict(Counter(
            node.get("role", "unknown") for node in view["nodes"] if not node.get("virtual")
        ))
        view["progress"] = progress
        view["navigation"] = self._navigation_payload(view)
        view["overview_metrics"] = self._overview_metrics(view, scope_id="all", scope_type="all")
        view["project_briefs"] = self._project_briefs_projection()
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

    @staticmethod
    def _project_identity_unavailable(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": record["id"],
            "display_name": record["display_name"],
            "root": None,
            "root_binding": {
                "status": "UNKNOWN",
                "value": None,
                "normalized": None,
                "availability": "UNKNOWN",
                "source": "codex.project_roots",
                "claim_limit": "The canonical host project root is unavailable; project identity is withheld.",
            },
            "manifest": {
                "status": "UNAVAILABLE",
                "path": "SWARM.md",
                "digest": None,
                "source": "project_root/SWARM.md",
            },
            "project_view": {
                "status": "UNAVAILABLE",
                "available": False,
                "manifest_status": "UNKNOWN",
                "manifest_digest": None,
                "identity": None,
            },
            "logo": {
                "status": "UNKNOWN",
                "artifact": None,
                "source": "canonical_project_manifest_schema_v1",
                "claim_limit": "No canonical project logo binding is retained; no fallback logo is synthesized.",
            },
            "artifact": {
                "status": "UNKNOWN",
                "kind": None,
                "id": None,
                "version": None,
                "digest": None,
                "source_digests": [],
            },
        }

    def _project_identity(
        self,
        record: dict[str, Any],
        root_owners: dict[str, set[str]],
    ) -> dict[str, Any]:
        root_binding = self._project_root_binding(record, root_owners)
        try:
            return self._project_manifest_projection(record, root_binding)
        except (AttributeError, ConsoleError, OSError, UnicodeError, sqlite3.Error, TypeError, ValueError):
            return self._project_identity_unavailable(record)

    def _project_briefs_projection(self) -> dict[str, Any]:
        unavailable = {
            "state": "UNKNOWN", "available": False, "cursor": None, "projects": [],
            "source": "codex_host_projects_and_project_roots+project_root/SWARM.md",
            "claim_limit": (
                "Saved-project or root-brief identity is unavailable; no brief content or inferred project "
                "identity is emitted."
            ),
        }
        try:
            state, records, cursor, root_owners = self._host_project_records()
        except (ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
            return unavailable
        if state == "UNKNOWN" or cursor is None:
            return unavailable
        projects = []
        for record in records:
            identity = self._project_identity(record, root_owners)
            manifest = identity.get("manifest") if isinstance(identity.get("manifest"), dict) else {}
            projects.append({
                "project_id": record["id"],
                "display_name": record["display_name"],
                "root_binding_status": (identity.get("root_binding") or {}).get("status", "UNKNOWN"),
                "status": manifest.get("status", "UNAVAILABLE"),
                "digest": manifest.get("digest"),
                "path": manifest.get("path", "SWARM.md"),
                "source": manifest.get("source", "project_root/SWARM.md"),
            })
        projection_cursor = {
            "type": "project_briefs_v1",
            "digest": _auto_digest({"host_cursor": cursor, "projects": projects}),
        }
        return {
            "state": state, "available": state == "KNOWN", "cursor": projection_cursor,
            "projects": projects,
            "source": "codex_host_projects_and_project_roots+project_root/SWARM.md",
            "claim_limit": (
                "Digest-bound root briefs are concise intent only; Ledger state, tasks, progress, proof, "
                "listener state, and execution authority are not copied or inferred."
            ),
        }

    @staticmethod
    def _project_navigation_fallback(record: dict[str, Any]) -> dict[str, Any]:
        """Keep roster enumeration real when the activity view is unavailable."""
        return {
            "id": record["id"],
            "name": record["display_name"],
            "goal_label": record["display_name"],
            "label_source": "codex.projects.name",
            "ordering": dict(record.get("ordering") or {}),
            "active_ctrl_id": None,
            "active_ctrl": False,
            "ctrl_ids": [],
            "project_eligibility": "unknown",
            "eligibility_source": "activity_view_unavailable",
            "archived": False,
            "archive_source": "codex.projects",
            "visibility": "visible",
            "status": "unknown",
            "status_facts": {
                "active": None,
                "stalled": None,
                "inactive": None,
                "source": "activity_view_unavailable",
            },
            "status_source": "unavailable",
            "task_count": None,
        }

    def project_roster(self) -> dict[str, Any]:
        """Project the host saved-project roster and exact local identity bindings."""
        unavailable = {
            "ok": True,
            "schema_version": 1,
            "state": "UNKNOWN",
            "available": False,
            "cursor": None,
            "projects": [],
            "current_work": {
                "state": "UNKNOWN",
                "available": False,
                "project_ids": [],
                "projects": [],
                "controllers": [],
            },
            "source": "codex_host_projects_and_project_roots",
            "claim_limit": (
                "The canonical Codex saved-project inventory is unavailable; an empty list is not a known "
                "empty project roster."
            ),
        }
        try:
            inventory_state, records, cursor, root_owners = self._host_project_records()
        except (ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
            return unavailable
        if inventory_state == "UNKNOWN" or cursor is None:
            return unavailable

        try:
            overview = self._host_overview(refresh=True)
            navigation = self._navigation_payload(overview) if isinstance(overview, dict) else None
        except (ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
            navigation = None
        navigation = navigation if isinstance(navigation, dict) else {}
        navigation_by_id = {
            str(item.get("id")): item
            for item in navigation.get("projects", [])
            if isinstance(item, dict) and item.get("id")
        }
        projects: list[dict[str, Any]] = []
        records_by_id = {record["id"]: record for record in records}
        for record in records:
            project = copy.deepcopy(
                navigation_by_id.get(record["id"], self._project_navigation_fallback(record))
            )
            identity = self._project_identity(record, root_owners)
            project.update({
                "id": record["id"],
                "name": record["display_name"],
                "display_name": record["display_name"],
                "ordering": dict(record.get("ordering") or {}),
                "root": identity.get("root"),
                "root_status": (identity.get("root_binding") or {}).get("status", "UNKNOWN"),
                "manifest": copy.deepcopy(identity.get("manifest")),
                "project_view": copy.deepcopy(identity.get("project_view")),
                "logo": copy.deepcopy(identity.get("logo")),
                "artifact": copy.deepcopy(identity.get("artifact")),
                "identity": identity,
                "current_work": False,
            })
            projects.append(project)
        projects.sort(key=_project_order_key)

        current_projects, current_controllers, current_work_known = self._current_work_inventory(navigation)
        current_project_ids = [
            str(project.get("id"))
            for project in current_projects
            if isinstance(project, dict) and str(project.get("id") or "") in records_by_id
        ]
        current_project_id_set = set(current_project_ids)
        for project in projects:
            project["current_work"] = project["id"] in current_project_id_set
        current_state = "UNKNOWN" if not current_work_known else inventory_state
        current_work = {
            "state": current_state,
            "available": current_state == "KNOWN",
            "project_ids": current_project_ids,
            "projects": [
                copy.deepcopy(project)
                for project in projects
                if project["id"] in current_project_id_set
            ],
            "controllers": copy.deepcopy(current_controllers) if current_work_known else [],
            "source": "existing_navigation_current_work_inventory",
            "claim_limit": (
                "Current Work is the existing navigation subset: visible, non-archived saved projects with a "
                "complete observed CTRL inventory. It is not a second roster."
            ),
        }
        state_claim = (
            "The host saved-project inventory and root bindings are complete for this cursor."
            if inventory_state == "KNOWN"
            else "The host saved-project inventory is partial; listed rows are detected records, but completeness is not claimed."
        )
        return {
            "ok": True,
            "schema_version": 1,
            "state": inventory_state,
            "available": inventory_state == "KNOWN",
            "cursor": copy.deepcopy(cursor),
            "projects": projects,
            "current_work": current_work,
            "source": "codex_host_projects_and_project_roots",
            "claim_limit": (
                f"{state_claim} Project rows come only from the canonical host projects table; task metadata, "
                "cwd, worktree names, and titles cannot create pseudo-projects."
            ),
        }

    def _require_saved_project(
        self,
        project_id: Any,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, set[str]]]:
        project_id = self._host_project_text(project_id, 256)
        if project_id is None:
            raise ConsoleError("project_id must identify one canonical saved project")
        try:
            inventory_state, records, cursor, root_owners = self._host_project_records()
        except (ConsoleError, OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise ConsoleError("canonical saved project inventory is unavailable") from exc
        if inventory_state != "KNOWN" or cursor is None:
            raise ConsoleError("canonical saved project inventory is unavailable or partial")
        record = next((item for item in records if item["id"] == project_id), None)
        if record is None:
            raise ConsoleError("project_id is not a canonical saved project")
        root_binding = self._project_root_binding(record, root_owners)
        if root_binding.get("status") != "KNOWN":
            raise ConsoleError("project settings require one unambiguous canonical project root")
        return record, cursor, root_owners

    @staticmethod
    def _config_scope(scope: Any, *, require_cursor: bool = False) -> dict[str, Any]:
        if not isinstance(scope, dict) or not isinstance(scope.get("type"), str):
            raise ConsoleError("config scope must identify global or one saved project")
        scope_type = scope["type"].strip().casefold()
        if scope_type == "global":
            if set(scope) != {"type"}:
                raise ConsoleError("global config scope must contain only type=global")
            return {"type": "global"}
        if scope_type != "project":
            raise ConsoleError("config scope type must be global or project")
        required = {"type", "project_id"}
        if require_cursor:
            required.add("accepted_cursor")
        allowed = required if require_cursor else required | {"accepted_cursor"}
        if set(scope) != required and set(scope) != allowed:
            raise ConsoleError("project config scope requires exact project_id and accepted_cursor fields")
        project_id = _safe_metadata_text(scope.get("project_id"), "project_id", maximum=256)
        result: dict[str, Any] = {"type": "project", "project_id": project_id}
        if "accepted_cursor" in scope:
            cursor = scope.get("accepted_cursor")
            if (
                not isinstance(cursor, dict)
                or set(cursor) != {"type", "digest"}
                or cursor.get("type") != "codex_project_roster_v1"
                or not isinstance(cursor.get("digest"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", cursor["digest"])
            ):
                raise ConsoleError("accepted_cursor must be the exact project roster cursor")
            result["accepted_cursor"] = copy.deepcopy(cursor)
        return result

    def _config_scope_binding(
        self,
        scope: Any,
        *,
        require_cursor: bool = False,
    ) -> dict[str, Any]:
        normalized = self._config_scope(scope, require_cursor=require_cursor)
        if normalized["type"] == "global":
            return {
                "scope": normalized,
                "record": None,
                "cursor": None,
                "root_binding": None,
            }
        record, cursor, root_owners = self._require_saved_project(normalized["project_id"])
        if "accepted_cursor" in normalized and normalized["accepted_cursor"] != cursor:
            raise ConsoleConflict("project roster changed; reload before saving config")
        root_binding = self._project_root_binding(record, root_owners)
        if root_binding.get("status") != "KNOWN":
            raise ConsoleError("config requires one unambiguous canonical project root")
        return {
            "scope": {
                "type": "project",
                "project_id": record["id"],
                "accepted_cursor": copy.deepcopy(cursor),
            },
            "record": record,
            "cursor": cursor,
            "root_binding": root_binding,
        }

    @staticmethod
    def _config_redacted_source_text(text: str, revision: str) -> tuple[str, list[dict[str, str]]]:
        try:
            return _config_redacted_text(text, revision)
        except (ConsoleError, TypeError, ValueError):
            # A malformed source may not be safely tokenized.  Returning no
            # editor text is safer than accidentally returning a private value.
            return "", []

    def _config_global_state(self, module: Any) -> dict[str, Any]:
        fallback = Path(getattr(module, "TEMPLATE_PATH", SWARM_SKILL_ROOT / "assets" / "swarm-config.toml"))
        raw_bytes, exists = _config_bytes(self.config_path, fallback=fallback)
        revision = _config_sha256(raw_bytes)
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            text = ""
            parse_error = f"config source is not valid UTF-8: {str(exc)[:160]}"
            raw: dict[str, Any] = {}
            effective = copy.deepcopy(module.DEFAULTS)
            effective = module.apply_turbo(effective)
            return {
                "state": "INVALID",
                "error": parse_error,
                "module": module,
                "global_raw": raw,
                "global_effective": effective,
                "global_text": text,
                "global_exists": exists,
                "global_revision": revision,
                "source_kind": "global_config_file" if exists else "packaged_config_template",
                "source_path": str(self.config_path),
            }
        try:
            raw, _, effective = _config_parse_text(module, text, scope_type="global")
            state = "KNOWN"
            error = None
        except ConsoleError as exc:
            try:
                parsed = tomllib.loads(text)
                raw = parsed if isinstance(parsed, dict) else {}
            except (tomllib.TOMLDecodeError, TypeError, ValueError):
                raw = {}
            effective = copy.deepcopy(module.DEFAULTS)
            effective = module.apply_turbo(effective)
            state = "INVALID"
            error = str(exc)[:256]
        return {
            "state": state,
            "error": error,
            "module": module,
            "global_raw": raw,
            "global_effective": effective,
            "global_text": text,
            "global_exists": exists,
            "global_revision": revision,
            "source_kind": "global_config_file" if exists else "packaged_config_template",
            "source_path": str(self.config_path),
        }

    def _config_state(self, scope: Any, *, require_cursor: bool = False) -> dict[str, Any]:
        binding = self._config_scope_binding(scope, require_cursor=require_cursor)
        module = load_config_module()
        global_state = self._config_global_state(module)
        scope_type = binding["scope"]["type"]
        if scope_type == "global":
            raw_text = global_state["global_text"]
            revision = global_state["global_revision"]
            return {
                **global_state,
                "scope": binding["scope"],
                "project_id": None,
                "cursor": None,
                "record": None,
                "root_binding": None,
                "overlay_raw": None,
                "overlay_text": "",
                "overlay_revision": 0,
                "raw_text": raw_text,
                "revision": revision,
                "effective": copy.deepcopy(global_state["global_effective"]),
                "values_known": global_state["state"] == "KNOWN",
                "source_kind": global_state["source_kind"],
                "source_path": global_state["source_path"],
            }

        record = binding["record"]
        cursor = binding["cursor"]
        overlay = self.store.config_overlay(record["id"])
        overlay_text = "" if overlay is None else str(overlay.get("text") or "")
        overlay_raw: dict[str, Any] = {}
        effective = copy.deepcopy(global_state["global_effective"])
        state = global_state["state"]
        error = global_state["error"]
        overlay_revision = 0 if overlay is None else int(overlay["config_revision"])
        if state == "KNOWN" and overlay_text:
            try:
                overlay_raw, overlay_normalized, _ = _config_parse_text(
                    module, overlay_text, scope_type="project",
                )
                effective = _config_merge_overlay(effective, overlay_normalized)
                effective = module.apply_turbo(effective)
                module.validate(copy.deepcopy(effective))
            except ConsoleError as exc:
                state = "INVALID"
                error = str(exc)[:256]
                try:
                    parsed = tomllib.loads(overlay_text)
                    overlay_raw = parsed if isinstance(parsed, dict) else {}
                except (tomllib.TOMLDecodeError, TypeError, ValueError):
                    overlay_raw = {}
        elif overlay_text:
            try:
                parsed = tomllib.loads(overlay_text)
                overlay_raw = parsed if isinstance(parsed, dict) else {}
            except (tomllib.TOMLDecodeError, TypeError, ValueError):
                overlay_raw = {}
        revision = _config_scope_revision(
            "project", record["id"], cursor, global_state["global_revision"], overlay_text,
        )
        return {
            **global_state,
            "state": state,
            "error": error,
            "scope": binding["scope"],
            "project_id": record["id"],
            "cursor": cursor,
            "record": record,
            "root_binding": binding["root_binding"],
            "overlay_raw": overlay_raw,
            "overlay_text": overlay_text,
            "overlay_revision": overlay_revision,
            "raw_text": overlay_text,
            "revision": revision,
            "effective": effective,
            "values_known": state == "KNOWN",
            "source_kind": "project_skill_scope_overlay",
            "source_path": None,
        }

    def _config_projection_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        module = state["module"]
        defaults = copy.deepcopy(module.DEFAULTS)
        defaults_effective = module.apply_turbo(defaults)
        redacted_text, placeholders = self._config_redacted_source_text(
            state["raw_text"], state["revision"],
        )
        safe_effective, _ = _config_redacted_settings(state["effective"])
        safe_global, _ = _config_redacted_settings(state["global_effective"])
        overlay_raw = state.get("overlay_raw") if state["scope"]["type"] == "project" else None
        descriptors = _config_descriptor_rows(
            module,
            defaults_effective,
            state["effective"],
            global_raw=state["global_raw"],
            overlay_raw=overlay_raw,
            revision=state["revision"],
            scope_type=state["scope"]["type"],
            values_known=bool(state["values_known"]),
        )
        overridden_paths = sorted(
            path
            for path, _ in _config_leaf_items(overlay_raw or {})
            if path != "schema_version"
        )
        descriptor_paths = [row["key"] for row in descriptors]
        inherited_paths = [path for path in descriptor_paths if path not in overridden_paths]
        validation = {
            "state": "KNOWN" if state["state"] == "KNOWN" else "UNKNOWN",
            "status": "VALID" if state["state"] == "KNOWN" else "INVALID",
            "schema_version": defaults_effective.get("schema_version"),
            "errors": [] if state["state"] == "KNOWN" else [state["error"] or "config source is invalid"],
        }
        scope = copy.deepcopy(state["scope"])
        project = None
        if state["scope"]["type"] == "project":
            project = {
                "id": state["record"]["id"],
                "display_name": state["record"]["display_name"],
                "root": state["root_binding"].get("value"),
                "root_binding": copy.deepcopy(state["root_binding"]),
            }
        warning = (
            "This project has no config overrides; it inherits global values."
            if state["scope"]["type"] == "project" and not overridden_paths
            else "Project overrides stop following global changes for the listed paths; all other paths continue inheriting global values."
            if state["scope"]["type"] == "project"
            else "Global values are the canonical defaults for all saved projects unless a project overlay overrides a path."
        )
        return {
            "ok": True,
            "contract_version": CONFIG_CONTRACT_VERSION,
            "schema_version": int(defaults_effective.get("schema_version", 0)),
            "config_schema_version": int(defaults_effective.get("schema_version", 0)),
            "state": state["state"],
            "available": state["state"] == "KNOWN",
            "scope": scope,
            "project": project,
            "source": state["source_kind"],
            "source_kind": state["source_kind"],
            "source_path": state["source_path"],
            "path": state["source_path"],
            "exists": bool(state["global_exists"]),
            "revision": state["revision"],
            "global_revision": state["global_revision"],
            "text": redacted_text,
            "editable_text": redacted_text,
            "opaque_placeholders": placeholders,
            "validation": validation,
            "settings": safe_effective,
            "effective_settings": safe_effective,
            "global_settings": safe_global,
            "overridden_paths": overridden_paths,
            "inherited_paths": inherited_paths,
            "inheritance": {
                "project_overlay": state["scope"]["type"] == "project",
                "global_revision": state["global_revision"],
                "warning": warning,
            },
            "descriptors": descriptors,
            "editable": [row["key"] for row in descriptors if row["editable"]],
            "write_contract": {
                "endpoint": "/api/config",
                "reset_endpoint": "/api/config/reset",
                "method": "POST",
                "scope_field": "scope",
                "expected_revision_field": "expected_revision",
                "acknowledgement_field": "acknowledge",
                "operation_id_field": "operation_id",
                "text_field": "text",
                "project_cursor_field": "scope.accepted_cursor",
                "reset_project_only": False,
            },
            "reset_contract": {
                "global": {
                    "endpoint": "/api/settings/restore",
                    "scope": {"type": "global"},
                    "effect": "Restore only the canonical packaged global TOML source; project overlays and CTRL overrides remain unchanged.",
                    "requires": ["expected_revision", "acknowledge", "operation_id"],
                },
                "project": {
                    "endpoint": "/api/config/reset",
                    "effect": "Remove only this saved project's config overlay; global values and CTRL overrides remain unchanged.",
                    "requires": ["expected_revision", "acknowledge", "operation_id", "scope.accepted_cursor"],
                },
                "ctrl": {
                    "endpoint": "/api/ctrl-settings/reset",
                    "effect": "Remove only this observed CTRL's model/reasoning overlay; global and project values remain unchanged.",
                    "requires": ["expected_revision", "acknowledge", "operation_id"],
                },
            },
            "health": {"auto_repair": self._auto_repair_policy()},
            "claim_limit": (
                "This projection uses the canonical SWARM validator and the existing global config file. "
                "Project text is a partial overlay retained in the existing skill-scope row; it is not a copied "
                "global file or a second project registry. Private values are never returned."
            ),
        }

    def config_projection(self, scope: Any = None) -> dict[str, Any]:
        normalized = {"type": "global"} if scope is None else scope
        return self._config_projection_from_state(self._config_state(normalized))

    @staticmethod
    def _config_operation_audit(
        *,
        action: str,
        operation_id: str,
        scope: dict[str, Any],
        expected_revision: str | int,
        request_digest: str,
        new_revision: str | int,
        changed_paths: list[str],
        source_kind: str,
    ) -> dict[str, Any]:
        # Keep the durable event useful for review while making raw config text
        # and private values structurally impossible to retain.
        return {
            "action": action,
            "operation_id": operation_id,
            "scope_type": scope["type"],
            "project_id": scope.get("project_id"),
            "ctrl_id": scope.get("ctrl_id"),
            "accepted_cursor": copy.deepcopy(scope.get("accepted_cursor")),
            "expected_revision": expected_revision,
            "request_digest": request_digest,
            "new_revision": new_revision,
            "changed_paths": sorted(changed_paths),
            "acknowledged": True,
            "source_kind": source_kind,
            "schema_version": CONFIG_CONTRACT_VERSION,
        }

    @staticmethod
    def _config_revision(value: Any, label: str = "expected_revision") -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ConsoleError(f"{label} must be an exact 64-character revision digest")
        return value

    def _config_replay_receipt(
        self,
        retained: dict[str, Any] | None,
        *,
        action: str,
        operation_id: str,
        scope: dict[str, Any],
        expected_revision: str | int,
        request_digest: str,
    ) -> dict[str, Any] | None:
        if retained is None:
            return None
        comparable = {
            "action": action,
            "operation_id": operation_id,
            "scope_type": scope["type"],
            "project_id": scope.get("project_id"),
            "ctrl_id": scope.get("ctrl_id"),
            "accepted_cursor": scope.get("accepted_cursor"),
            "expected_revision": expected_revision,
            "request_digest": request_digest,
        }
        if any(retained.get(key) != value for key, value in comparable.items()):
            raise ConsoleConflict("config operation identity conflicts with retained audit content")
        return {
            "accepted": True,
            "action": action,
            "operation_id": operation_id,
            "replayed": True,
            "scope": copy.deepcopy(scope),
            "expected_revision": expected_revision,
            "new_revision": retained.get("new_revision"),
            "changed_paths": copy.deepcopy(retained.get("changed_paths", [])),
            "acknowledged": True,
            "audit_event": CONFIG_EVENT_KIND,
            "source_kind": retained.get("source_kind"),
            "claim_limit": "This is an idempotent replay of one retained local config mutation receipt.",
        }

    def _config_transaction_rollback_path(self, operation_id: str) -> Path:
        digest = _config_sha256(operation_id.encode("utf-8"))
        return self.config_path.with_name(
            f".{self.config_path.name}.swarm-console-rollback-{digest}"
        )

    @staticmethod
    def _config_write_exact(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary and temporary.exists():
                temporary.unlink(missing_ok=True)

    def _config_write_rollback_snapshot(
        self,
        rollback_path: Path,
        old_bytes: bytes,
        *,
        source_existed: bool,
    ) -> None:
        if not source_existed:
            if rollback_path.exists():
                raise ConsoleError("config rollback snapshot exists for a nonexistent source")
            return
        if rollback_path.exists():
            if rollback_path.is_symlink() or _config_sha256(rollback_path.read_bytes()) != _config_sha256(old_bytes):
                raise ConsoleError("config rollback snapshot conflicts with the current source")
            return
        self._config_write_exact(rollback_path, old_bytes)

    def _config_cleanup_rollback_snapshot(self, transaction: dict[str, Any]) -> None:
        rollback_path = Path(str(transaction["rollback_path"])).resolve()
        expected = self._config_transaction_rollback_path(str(transaction["operation_id"])).resolve()
        if rollback_path != expected:
            raise ConsoleError("config rollback path is outside the canonical source directory")
        if rollback_path.exists():
            if rollback_path.is_symlink():
                raise ConsoleError("config rollback path is a symlink")
            rollback_path.unlink()

    def _config_restore_transaction_source(self, transaction: dict[str, Any]) -> None:
        source_path = Path(str(transaction["source_path"])).resolve()
        if source_path != self.config_path:
            raise ConsoleError("config transaction source does not match the canonical source")
        rollback_path = Path(str(transaction["rollback_path"])).resolve()
        expected_rollback = self._config_transaction_rollback_path(str(transaction["operation_id"])).resolve()
        if rollback_path != expected_rollback:
            raise ConsoleError("config transaction rollback path is not canonical")
        before_revision = str(transaction["before_revision"])
        after_revision = str(transaction["after_revision"])
        source_existed = transaction["source_existed"] is True
        if self.config_path.is_symlink():
            raise ConsoleError("config source is a symlink")
        current_exists = self.config_path.exists()
        current_bytes = self.config_path.read_bytes() if current_exists else b""
        current_revision = _config_sha256(current_bytes) if current_exists else None
        if current_exists and current_revision not in {before_revision, after_revision}:
            raise ConsoleError("config source changed outside the pending transaction")
        if not current_exists and source_existed:
            raise ConsoleError("config source disappeared during the pending transaction")
        if current_revision == after_revision:
            if source_existed:
                if not rollback_path.is_file() or rollback_path.is_symlink():
                    raise ConsoleError("config rollback snapshot is unavailable")
                rollback_bytes = rollback_path.read_bytes()
                if _config_sha256(rollback_bytes) != str(transaction["rollback_digest"]):
                    raise ConsoleError("config rollback snapshot digest does not match")
                self._config_write_exact(self.config_path, rollback_bytes)
            else:
                self.config_path.unlink()
        elif current_revision is None and source_existed:
            raise ConsoleError("config source cannot be recovered from the pending transaction")
        elif current_revision == before_revision and source_existed:
            if not current_exists:
                raise ConsoleError("config source cannot be recovered from the pending transaction")

    def _recover_config_transactions(self) -> None:
        for retained in self.store.pending_config_events():
            transaction = retained["transaction"]
            source_path = Path(str(transaction["source_path"])).resolve()
            if source_path != self.config_path:
                continue
            try:
                self._config_restore_transaction_source(transaction)
                self.store.abort_config_event(retained["operation_id"])
                self._config_cleanup_rollback_snapshot(transaction)
            except Exception as exc:
                raise ConsoleError(
                    "pending config transaction requires recovery before config access"
                ) from exc

    def _commit_global_config_source(
        self,
        state: dict[str, Any],
        *,
        operation_id: str,
        resolved_text: str,
        audit: dict[str, Any],
        new_revision: str,
    ) -> None:
        if state["scope"]["type"] != "global":
            raise ConsoleError("global config transaction requires global scope")
        if self.config_path.is_symlink():
            raise ConsoleError("config source is a symlink")
        source_existed = self.config_path.exists()
        old_bytes = self.config_path.read_bytes() if source_existed else state["global_text"].encode("utf-8")
        if _config_sha256(old_bytes) != state["global_revision"]:
            raise ConsoleConflict("config source changed; reload before saving")
        resolved_bytes = resolved_text.encode("utf-8")
        if _config_sha256(resolved_bytes) != new_revision:
            raise ConsoleError("config transaction revision does not match the proposed source")
        rollback_path = self._config_transaction_rollback_path(operation_id)
        transaction = {
            "operation_id": operation_id,
            "before_revision": state["global_revision"],
            "after_revision": new_revision,
            "source_path": str(self.config_path),
            "source_existed": source_existed,
            "rollback_path": str(rollback_path),
            "rollback_digest": _config_sha256(old_bytes) if source_existed else "",
        }
        prepared = False
        try:
            transaction_state = self.store.prepare_config_event(
                operation_id,
                audit,
                transaction=transaction,
                now_ms=int(time.time() * 1000),
            )
            if transaction_state == CONFIG_TRANSACTION_COMMITTED:
                raise ConsoleConflict("config operation is already committed; replay the original request")
            prepared = True
            self._config_write_rollback_snapshot(
                rollback_path, old_bytes, source_existed=source_existed,
            )
            _atomic_config_write(self.config_path, resolved_bytes, state["module"])
            self.store.retain_config_event(
                operation_id, audit, now_ms=int(time.time() * 1000),
            )
        except Exception as exc:
            if not prepared:
                if rollback_path.exists():
                    rollback_path.unlink(missing_ok=True)
                if isinstance(exc, ConsoleError):
                    raise
                raise ConsoleError(str(exc)[:256]) from exc
            try:
                committed = self.store.config_event(operation_id)
            except Exception:
                committed = None
            if committed is not None:
                try:
                    if not self.config_path.exists() or _config_sha256(self.config_path.read_bytes()) != new_revision:
                        raise ConsoleError("committed config audit does not match the source revision")
                    self._config_cleanup_rollback_snapshot(transaction)
                    return
                except Exception as recovery_exc:
                    raise ConsoleError(
                        f"config audit committed without matching source: {str(recovery_exc)[:180]}"
                    ) from exc
            try:
                self._config_restore_transaction_source(transaction)
                self.store.abort_config_event(operation_id)
                self._config_cleanup_rollback_snapshot(transaction)
            except Exception as recovery_exc:
                raise ConsoleError(
                    f"config mutation failed and recovery could not be proven: {str(recovery_exc)[:180]}"
                ) from exc
            if isinstance(exc, ConsoleError):
                raise
            raise ConsoleError(str(exc)[:256]) from exc
        self._config_cleanup_rollback_snapshot(transaction)

    def update_config_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = {"scope", "expected_revision", "acknowledge", "text", "operation_id"}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ConsoleError("config update requires exact scope, expected_revision, acknowledge, text, and operation_id fields")
        if payload["acknowledge"] is not True:
            raise ConsoleError("config update requires acknowledge=true")
        self._recover_config_transactions()
        operation_id = _auto_id(payload["operation_id"], "operation_id")
        expected_revision = self._config_revision(payload["expected_revision"])
        text = payload["text"]
        if not isinstance(text, str):
            raise ConsoleError("config text is invalid or oversized")
        try:
            text_bytes = text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ConsoleError("config text must be valid UTF-8") from exc
        if len(text_bytes) > CONFIG_TEXT_MAX_BYTES:
            raise ConsoleError("config text is invalid or oversized")
        binding = self._config_scope_binding(payload["scope"], require_cursor=True)
        state = self._config_state(binding["scope"], require_cursor=True)
        request_digest = _config_sha256(text_bytes)
        retained = self.store.config_event(operation_id)
        replay = self._config_replay_receipt(
            retained,
            action="config_update",
            operation_id=operation_id,
            scope=state["scope"],
            expected_revision=expected_revision,
            request_digest=request_digest,
        )
        if replay is not None:
            projection = self._config_projection_from_state(state)
            projection["mutation_receipt"] = replay
            return projection
        if expected_revision != state["revision"]:
            raise ConsoleConflict("config revision changed; reload before saving")
        resolved_text = _config_resolve_opaque_text(text, state["raw_text"], state["revision"])
        _, next_normalized, next_effective = _config_parse_text(
            state["module"], resolved_text, scope_type=state["scope"]["type"],
        )
        if state["scope"]["type"] == "project":
            # The validator's effective result is default-filled.  Merge only
            # the submitted normalized partial overlay so future global
            # changes continue to flow through non-overridden paths.
            next_effective = _config_merge_overlay(state["global_effective"], next_normalized)
            next_effective = state["module"].apply_turbo(next_effective)
            try:
                state["module"].validate(copy.deepcopy(next_effective))
            except Exception as exc:
                raise ConsoleError(f"project config validation failed: {str(exc)[:256]}") from exc
            new_revision = _config_scope_revision(
                "project", state["project_id"], state["cursor"],
                state["global_revision"], resolved_text,
            )
        else:
            new_revision = _config_sha256(resolved_text.encode("utf-8"))
        changed_paths = _config_changed_paths(state["effective"], next_effective)
        audit = self._config_operation_audit(
            action="config_update",
            operation_id=operation_id,
            scope=state["scope"],
            expected_revision=expected_revision,
            request_digest=request_digest,
            new_revision=new_revision,
            changed_paths=changed_paths,
            source_kind=state["source_kind"],
        )
        if state["scope"]["type"] == "global":
            self._commit_global_config_source(
                state,
                operation_id=operation_id,
                resolved_text=resolved_text,
                audit=audit,
                new_revision=new_revision,
            )
        else:
            self.store.update_config_overlay(
                state["project_id"], resolved_text,
                expected_config_revision=state["overlay_revision"],
                operation_id=operation_id,
                audit_payload=audit,
                now_ms=int(time.time() * 1000),
            )
        with self.overview_lock:
            self._store_generation += 1
            self._overview_fingerprint = None
            self._view_fingerprint = None
        projection = self.config_projection(state["scope"])
        projection["mutation_receipt"] = {
            "accepted": True,
            "action": "config_update",
            "operation_id": operation_id,
            "replayed": False,
            "scope": copy.deepcopy(state["scope"]),
            "expected_revision": expected_revision,
            "new_revision": new_revision,
            "changed_paths": changed_paths,
            "acknowledged": True,
            "audit_event": CONFIG_EVENT_KIND,
            "source_kind": state["source_kind"],
            "claim_limit": "This receipt records one canonical local config write; it does not create runtime or host task authority.",
        }
        return projection

    def reset_config_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = {"scope", "expected_revision", "acknowledge", "operation_id"}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ConsoleError("config reset requires exact scope, expected_revision, acknowledge, and operation_id fields")
        if payload["acknowledge"] is not True:
            raise ConsoleError("config reset requires acknowledge=true")
        self._recover_config_transactions()
        operation_id = _auto_id(payload["operation_id"], "operation_id")
        expected_revision = self._config_revision(payload["expected_revision"])
        binding = self._config_scope_binding(payload["scope"], require_cursor=True)
        state = self._config_state(binding["scope"], require_cursor=True)
        if state["scope"]["type"] == "global":
            resolved_text = _canonical_config_defaults_text(state["module"])
            _, next_normalized, next_effective = _config_parse_text(
                state["module"], resolved_text, scope_type="global",
            )
            del next_normalized
            request_digest = _config_sha256(resolved_text.encode("utf-8"))
            new_revision = request_digest
            changed_paths = _config_changed_paths(state["effective"], next_effective)
            action = "global_config_reset"
        else:
            request_digest = _config_sha256(b"project-config-reset")
            new_revision = _config_scope_revision(
                "project", state["project_id"], state["cursor"],
                state["global_revision"], "",
            )
            changed_paths = sorted(
                path
                for path, _ in _config_leaf_items(state.get("overlay_raw") or {})
                if path != "schema_version"
            )
            action = "project_config_reset"
        retained = self.store.config_event(operation_id)
        replay = self._config_replay_receipt(
            retained,
            action=action,
            operation_id=operation_id,
            scope=state["scope"],
            expected_revision=expected_revision,
            request_digest=request_digest,
        )
        if replay is not None:
            projection = self._config_projection_from_state(state)
            projection["mutation_receipt"] = replay
            return projection
        if expected_revision != state["revision"]:
            raise ConsoleConflict("config revision changed; reload before resetting")
        audit = self._config_operation_audit(
            action=action,
            operation_id=operation_id,
            scope=state["scope"],
            expected_revision=expected_revision,
            request_digest=request_digest,
            new_revision=new_revision,
            changed_paths=changed_paths,
            source_kind=state["source_kind"],
        )
        if state["scope"]["type"] == "global":
            self._commit_global_config_source(
                state,
                operation_id=operation_id,
                resolved_text=resolved_text,
                audit=audit,
                new_revision=new_revision,
            )
        else:
            self.store.reset_config_overlay(
                state["project_id"],
                expected_config_revision=state["overlay_revision"],
                operation_id=operation_id,
                audit_payload=audit,
                now_ms=int(time.time() * 1000),
            )
        with self.overview_lock:
            self._store_generation += 1
            self._overview_fingerprint = None
            self._view_fingerprint = None
        projection = self.config_projection(state["scope"])
        projection["mutation_receipt"] = {
            "accepted": True,
            "action": action,
            "operation_id": operation_id,
            "replayed": False,
            "scope": copy.deepcopy(state["scope"]),
            "expected_revision": expected_revision,
            "new_revision": new_revision,
            "changed_paths": copy.deepcopy(changed_paths),
            "acknowledged": True,
            "audit_event": CONFIG_EVENT_KIND,
            "source_kind": state["source_kind"],
            "claim_limit": "Only this project's existing config overlay was removed; global values remain canonical.",
        }
        if action == "global_config_reset":
            projection["mutation_receipt"]["claim_limit"] = (
                "Only the canonical global config source was restored; project overlays and CTRL overrides remain unchanged."
            )
        return projection

    def _project_settings_projection(
        self,
        record: dict[str, Any],
        cursor: dict[str, Any],
        overlay: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from skills_catalog import resolve

        _, effective, _ = load_config(self.config_path)
        global_scope = self.store.skill_scope("global", "global")
        project_scope = overlay if overlay is not None else self.store.skill_scope("project", record["id"])
        skills_config = effective.get("skills", {}) if isinstance(effective, dict) else {}
        resolved = resolve(
            self.store.skill_catalog(),
            global_scope,
            project_scope,
            None,
            global_enabled=bool(skills_config.get("inheritance_enabled", True)),
            global_profile=str(skills_config.get("default_profile", "default")),
            global_preferred=(global_scope or {}).get("preferred_ids", []),
        )
        settings = {
            field: copy.deepcopy(resolved["settings"].get(field))
            for field in sorted(PROJECT_SETTING_FIELDS)
        }
        revision = 0 if project_scope is None else int(project_scope["revision"])
        accepted_cursor = copy.deepcopy(cursor)
        return {
            "ok": True,
            "schema_version": 1,
            "state": "KNOWN",
            "available": True,
            "project": {
                "id": record["id"],
                "display_name": record["display_name"],
            },
            "scope": {
                "type": "project",
                "id": record["id"],
                "project_id": record["id"],
                "accepted_cursor": accepted_cursor,
                "source": "codex_host_projects_and_project_roots",
            },
            "accepted_cursor": accepted_cursor,
            "revision": revision,
            "settings": settings,
            "overlay": copy.deepcopy(project_scope),
            "editable_fields": sorted(PROJECT_SETTING_FIELDS),
            "write_contract": {
                "endpoint": "/api/projects/settings",
                "method": "POST",
                "acknowledgement_field": "acknowledge",
                "accepted_cursor_field": "accepted_cursor",
                "scope": "project",
            },
            "source": "existing_skill_scope_overlays",
            "claim_limit": (
                "Only the existing project skill-scope overlay is writable. The accepted cursor binds the change "
                "to one canonical host project; no project registry or task authority is created."
            ),
        }

    def project_settings(self, project_id: Any) -> dict[str, Any]:
        record, cursor, _ = self._require_saved_project(project_id)
        return self._project_settings_projection(record, cursor)

    def update_project_settings(
        self,
        project_id: Any,
        changes: Any,
        expected_revision: Any,
        accepted_cursor: Any,
        acknowledge: Any,
    ) -> dict[str, Any]:
        if acknowledge is not True:
            raise ConsoleError("project settings update requires acknowledge=true")
        if not isinstance(changes, dict) or not changes:
            raise ConsoleError("project settings changes must be a non-empty object")
        unknown = set(changes) - PROJECT_SETTING_FIELDS
        if unknown:
            raise ConsoleError(
                "project settings changes are limited to: " + ", ".join(sorted(PROJECT_SETTING_FIELDS))
            )
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise ConsoleError("expected_revision must be a non-negative integer")
        if (
            not isinstance(accepted_cursor, dict)
            or set(accepted_cursor) != {"type", "digest"}
            or not all(isinstance(accepted_cursor.get(field), str) for field in ("type", "digest"))
        ):
            raise ConsoleError("accepted_cursor must be the exact project roster cursor")
        record, cursor, _ = self._require_saved_project(project_id)
        if accepted_cursor != cursor:
            raise ConsoleConflict("project roster changed; reload before saving project settings")
        try:
            overlay = self.store.update_skill_scope(
                "project", record["id"], changes,
                expected_revision=expected_revision,
                now_ms=int(time.time() * 1000),
            )
        except ValueError as exc:
            raise ConsoleError(str(exc)) from exc
        with self.overview_lock:
            self._store_generation += 1
        projection = self._project_settings_projection(record, cursor, overlay)
        projection["mutation_receipt"] = {
            "accepted": True,
            "action": "project_settings_update",
            "project_id": record["id"],
            "accepted_cursor": copy.deepcopy(cursor),
            "changed_fields": sorted(changes),
            "revision": int(overlay["revision"]),
            "acknowledged": True,
            "source": "existing_skill_scope_overlays",
            "claim_limit": "This receipt acknowledges a local project settings overlay write only; it does not create host task or runtime authority.",
        }
        return projection

    @staticmethod
    def _project_paths_overlap(left: str, right: str) -> bool:
        left = left.rstrip("/")
        right = right.rstrip("/")
        return left == right or left.startswith(right + "/") or right.startswith(left + "/")

    @classmethod
    def _validated_project_create_root(cls, value: Any) -> tuple[str, str]:
        raw = cls._host_project_text(value, 4096)
        if raw is None or not cls._project_path_is_absolute(raw):
            raise ConsoleError("project root must be an absolute host path")
        candidate = Path(raw)
        try:
            if not candidate.exists() or not candidate.is_dir():
                raise ConsoleError("project root must be an existing directory")
            if any(
                ancestor.exists() and _is_reparse_point(ancestor)
                for ancestor in (candidate, *candidate.parents)
            ):
                raise ConsoleError("project root cannot be a reparse point")
            resolved = candidate.resolve(strict=True)
            if _is_reparse_point(resolved):
                raise ConsoleError("project root cannot be a reparse point")
        except ConsoleError:
            raise
        except OSError as exc:
            raise ConsoleError("project root is unavailable") from exc
        normalized = _normalized_project_path(str(resolved))
        if not normalized or not cls._project_path_is_absolute(str(resolved)):
            raise ConsoleError("project root must resolve to one absolute host path")
        return str(resolved), normalized

    def create_project(self, name: Any, root: Any, acknowledge: Any) -> dict[str, Any]:
        if acknowledge is not True:
            raise ConsoleError("project creation requires acknowledge=true")
        display_name = self._host_project_text(name, 256)
        if display_name is None:
            raise ConsoleError("project name must be non-empty text up to 256 characters")
        canonical_root, normalized_root = self._validated_project_create_root(root)
        inventory_state, records, _, root_owners = self._host_project_records()
        if inventory_state != "KNOWN":
            raise ConsoleError("saved project creation requires a complete canonical host project inventory")
        for record in records:
            binding = self._project_root_binding(record, root_owners)
            if binding.get("status") != "KNOWN":
                raise ConsoleError("saved project creation requires unambiguous existing project roots")

        database = state_database(self.codex_home)
        try:
            with closing(sqlite3.connect(database, timeout=2)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA busy_timeout = 2000")
                tables = {
                    str(row["name"])
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                if not {"projects", "project_roots"}.issubset(tables):
                    raise ConsoleError("saved project creation is unsupported by the host project schema")
                project_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(projects)").fetchall()
                }
                root_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(project_roots)").fetchall()
                }
                if (
                    not {"id", "name", "metadata", "position", "created_at_ms", "updated_at_ms"}.issubset(project_columns)
                    or not {"project_id", "position", "path"}.issubset(root_columns)
                ):
                    raise ConsoleError("saved project creation is unsupported by the host project schema")
                connection.execute("BEGIN IMMEDIATE")
                project_rows = connection.execute(
                    "SELECT id, name, position FROM projects"
                ).fetchall()
                root_rows = connection.execute(
                    "SELECT project_id, position, path FROM project_roots"
                ).fetchall()
                roots_by_project: dict[str, list[tuple[int, str]]] = {}
                for row in root_rows:
                    existing_id = self._host_project_text(row["project_id"], 256)
                    existing_path = self._host_project_text(row["path"], 4096)
                    if (
                        existing_id is None
                        or existing_path is None
                        or not self._project_path_is_absolute(existing_path)
                    ):
                        raise ConsoleError("saved project creation requires valid canonical host project roots")
                    existing_normalized = _normalized_project_path(existing_path)
                    roots_by_project.setdefault(existing_id, []).append((
                        int(row["position"])
                        if isinstance(row["position"], int) and not isinstance(row["position"], bool)
                        else 0,
                        existing_normalized,
                    ))
                existing_by_id = {str(row["id"]): row for row in project_rows}
                for row in project_rows:
                    existing_id = self._host_project_text(row["id"], 256)
                    existing_name = self._host_project_text(row["name"], 256)
                    if existing_id is None or existing_name is None:
                        raise ConsoleError("saved project creation requires valid canonical host project identities")
                    existing_roots = roots_by_project.get(existing_id, [])
                    if len(existing_roots) != 1:
                        raise ConsoleError("saved project creation requires one unambiguous root per existing project")
                    existing_normalized = existing_roots[0][1]
                    if existing_name.casefold() == display_name.casefold():
                        if existing_normalized == normalized_root:
                            connection.rollback()
                            roster = self.project_roster()
                            project = next(item for item in roster["projects"] if item["id"] == existing_id)
                            roster["mutation_receipt"] = {
                                "accepted": True,
                                "action": "project_create",
                                "status": "unchanged",
                                "project_id": existing_id,
                                "acknowledged": True,
                                "source": "codex_host_projects_and_project_roots",
                                "claim_limit": "The explicit create request matched one existing canonical host project; no duplicate row was written.",
                            }
                            roster["project"] = project
                            return roster
                        raise ConsoleConflict("a saved project with this name already exists")
                    if self._project_paths_overlap(existing_normalized, normalized_root):
                        raise ConsoleConflict("project root overlaps an existing saved project root")
                next_position = max(
                    (
                        int(row["position"])
                        for row in project_rows
                        if isinstance(row["position"], int) and not isinstance(row["position"], bool)
                    ),
                    default=-1,
                ) + 1
                project_id = ""
                while not project_id or project_id in existing_by_id:
                    project_id = str(uuid.uuid4())
                now_ms = int(time.time() * 1000)
                connection.execute(
                    "INSERT INTO projects(id, name, metadata, position, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?)",
                    (project_id, display_name, "{}", next_position, now_ms, now_ms),
                )
                connection.execute(
                    "INSERT INTO project_roots(project_id, position, path) VALUES (?, ?, ?)",
                    (project_id, 0, canonical_root),
                )
                connection.commit()
        except ConsoleError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise ConsoleError("saved project creation could not be committed") from exc

        with self.overview_lock:
            self._overview = None
            self._view = None
            self._overview_fingerprint = None
            self._view_fingerprint = None
        roster = self.project_roster()
        project = next((item for item in roster["projects"] if item["id"] == project_id), None)
        if project is None:
            raise ConsoleError("saved project was written but could not be re-read from the host roster")
        roster["project"] = project
        roster["mutation_receipt"] = {
            "accepted": True,
            "action": "project_create",
            "status": "created",
            "project_id": project_id,
            "acknowledged": True,
            "source": "codex_host_projects_and_project_roots",
            "claim_limit": "The explicit create request wrote one Codex host projects row and one project_roots binding; no SWARM.md, logo, task, or second registry was created.",
        }
        return roster
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
            projection = self.progress_ledger.project_role_manifests(self.builtin_role_manifests)
            builtin_by_id = {manifest["id"]: manifest for manifest in self.builtin_role_manifests}
            roles = []
            for role in projection["roles"]:
                builtin = builtin_by_id.get(role["id"])
                avatar = None
                if builtin is not None and role.get("avatar_asset_digest") == builtin["avatar_asset_digest"]:
                    avatar = {
                        "state": "AVAILABLE",
                        "digest": builtin["avatar_asset_digest"],
                        "url": f"/assets/role-avatars/{role['id']}.png",
                    }
                roles.append({**role, "avatar": avatar})
            return {"ok": True, **projection, "roles": roles}
        except ProgressEventError as error:
            raise ConsoleError(str(error)) from error

    def role_avatar_response(self, role_id: str, accept: str) -> dict[str, Any]:
        if not isinstance(role_id, str) or not re.fullmatch(r"[a-z0-9_]+", role_id):
            raise ConsoleError("role avatar not found")
        record = self.builtin_role_avatar_assets.get(role_id)
        if record is None:
            raise ConsoleError("role avatar not found")
        media_type = _preferred_image_media_type(accept)
        if media_type == "image/avif":
            selected = record["derivatives"][(128, "avif")]
        elif media_type == "image/webp":
            selected = record["derivatives"][(128, "webp")]
        else:
            selected = record["source"]
        path = selected["file"]
        body = path.read_bytes()
        if len(body) != selected["bytes"] or hashlib.sha256(body).hexdigest() != selected["sha256"]:
            raise ConsoleError("role avatar asset no longer matches its admitted digest")
        return {"body": body, "media_type": media_type, "digest": selected["sha256"]}

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
            or not _is_observed_ctrl_for_projection(controller)
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

    def _asset_response(self, asset: dict[str, Any], *, action: str, status: str = "accepted") -> dict[str, Any]:
        return {
            "ok": True,
            "asset": asset,
            "mutation": {
                "accepted": True,
                "action": action,
                "status": status,
                "event_cursor": asset.get("event_cursor"),
                "retention_policy": ASSET_RETENTION_POLICY,
                "claim_limit": "The mutation is one server-owned local receipt; no provider call, model call, or file URL is fabricated.",
            },
        }

    def assets_projection(self, *, project_id: str | None = None, projection: str = "active") -> dict[str, Any]:
        if project_id not in (None, ""):
            self._asset_project_scope(project_id)
            project_id = _asset_id(project_id, "project_id")
        if projection not in {"active", "trash"}:
            raise ConsoleError("asset projection must be active or trash")
        try:
            items = self.store.asset_list(
                project_id=project_id,
                projection=projection,
                allowed_root=self.codex_home / PROOF_MEDIA_ROOT,
            )
            events = self.store.asset_event_feed(project_id=project_id, after_sequence=0)
            cursor = self.store.asset_event_cursor()
        except (AttributeError, ConsoleError, OSError, sqlite3.Error, TypeError, ValueError) as error:
            if project_id not in (None, "") and str(error) in {
                "PROJECT_SCOPE_UNAVAILABLE", "PROJECT_ROOT_AMBIGUOUS", "PROJECT_ROOT_UNAVAILABLE",
            }:
                raise
            return {
                "ok": True,
                "status": "unavailable",
                "project_id": project_id,
                "projection": projection,
                "items": [],
                "event_cursor": {"sequence": 0, "identity": None},
                "retention_policy": ASSET_RETENTION_POLICY,
                "reason": "Asset store or event ledger is unavailable; no asset presence is inferred.",
            }
        return {
            "ok": True,
            "status": "available",
            "project_id": project_id,
            "projection": projection,
            "items": items,
            "event_cursor": cursor,
            "event_count": len(events.get("items") or []),
            "retention_policy": ASSET_RETENTION_POLICY,
            "claim_limit": "The default projection excludes soft-trashed assets; the explicit trash projection includes them. Similar files remain distinct assets unless an explicit lineage binds them.",
        }

    def asset_detail(self, asset_id: str, *, project_id: str | None = None) -> dict[str, Any]:
        allowed_root = self.codex_home / PROOF_MEDIA_ROOT
        if project_id not in (None, ""):
            self._asset_project_scope(project_id)
            project_id = _asset_id(project_id, "project_id")
        item = self.store.asset_item(asset_id, allowed_root=allowed_root)
        if project_id is not None and item.get("project_id") != project_id:
            raise ConsoleError("asset is not bound to the requested project")
        return {"ok": True, "status": "available", "asset": item, "retention_policy": ASSET_RETENTION_POLICY}

    def asset_event_projection(
        self,
        *,
        project_id: str | None = None,
        after_sequence: int = 0,
        limit: int = 64,
    ) -> dict[str, Any]:
        if project_id not in (None, ""):
            self._asset_project_scope(project_id)
            project_id = _asset_id(project_id, "project_id")
        try:
            return {"ok": True, **self.store.asset_event_feed(
                project_id=project_id, after_sequence=after_sequence, limit=limit,
            )}
        except (AttributeError, ConsoleError, OSError, sqlite3.Error, TypeError, ValueError) as error:
            if project_id not in (None, "") and str(error) in {
                "PROJECT_SCOPE_UNAVAILABLE", "PROJECT_ROOT_AMBIGUOUS", "PROJECT_ROOT_UNAVAILABLE",
            }:
                raise
            return {
                "ok": True,
                "status": "unavailable",
                "project_id": project_id,
                "after_sequence": after_sequence,
                "cursor": {"sequence": 0, "identity": None},
                "items": [],
                "retention_policy": ASSET_RETENTION_POLICY,
                "claim_limit": "Asset transition events are unavailable; no transition is inferred.",
            }

    def accept_asset_generation(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._asset_project_scope(payload.get("project_id"))
        asset = self.store.reserve_asset_generation(payload, now_ms=int(time.time() * 1000))
        asset = self.store.asset_item(asset["asset_id"], allowed_root=self.codex_home / PROOF_MEDIA_ROOT)
        return self._asset_response(asset, action="generation_reserve", status="queued")

    def advance_asset_generation(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._asset_project_scope(payload.get("project_id"))
        asset_id = _asset_id(payload.get("asset_id"), "asset_id")
        current = self.store.asset_item(asset_id, allowed_root=self.codex_home / PROOF_MEDIA_ROOT)
        if current["project_id"] != _asset_id(payload.get("project_id"), "project_id"):
            raise ConsoleError("asset is not bound to the requested project")
        asset = self.store.advance_asset_generation(
            asset_id,
            expected_revision=payload.get("expected_revision"),
            operation_id=payload.get("operation_id"),
            status=payload.get("status"),
            measured_progress=payload.get("measured_progress"),
            measured_progress_provenance=payload.get("measured_progress_provenance"),
            now_ms=int(time.time() * 1000),
        )
        return self._asset_response(asset, action="generation_transition", status=asset["presentation"]["status"])

    def fail_asset_generation(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._asset_project_scope(payload.get("project_id"))
        asset_id = _asset_id(payload.get("asset_id"), "asset_id")
        current = self.store.asset_item(asset_id)
        if current["project_id"] != _asset_id(payload.get("project_id"), "project_id"):
            raise ConsoleError("asset is not bound to the requested project")
        asset = self.store.fail_asset_generation(
            asset_id,
            expected_revision=payload.get("expected_revision"),
            operation_id=payload.get("operation_id"),
            error_class=payload.get("error_class"),
            retry_eligible=payload.get("retry_eligible"),
            now_ms=int(time.time() * 1000),
        )
        return self._asset_response(asset, action="generation_failure", status="failed")

    def cancel_asset_generation(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._asset_project_scope(payload.get("project_id"))
        asset_id = _asset_id(payload.get("asset_id"), "asset_id")
        current = self.store.asset_item(asset_id)
        if current["project_id"] != _asset_id(payload.get("project_id"), "project_id"):
            raise ConsoleError("asset is not bound to the requested project")
        asset = self.store.cancel_asset_generation(
            asset_id,
            expected_revision=payload.get("expected_revision"),
            operation_id=payload.get("operation_id"),
            now_ms=int(time.time() * 1000),
        )
        return self._asset_response(asset, action="generation_cancel", status="cancelled")

    def admit_asset_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._asset_project_scope(payload.get("project_id"))
        asset_id = _asset_id(payload.get("asset_id"), "asset_id")
        current = self.store.asset_item(asset_id)
        if current["project_id"] != _asset_id(payload.get("project_id"), "project_id"):
            raise ConsoleError("asset is not bound to the requested project")
        asset = self.store.admit_asset_file(
            asset_id,
            expected_revision=payload.get("expected_revision"),
            operation_id=payload.get("operation_id"),
            locator=payload.get("locator"),
            digest=payload.get("digest"),
            provenance=payload.get("provenance"),
            now_ms=int(time.time() * 1000),
            allowed_root=self.codex_home / PROOF_MEDIA_ROOT,
        )
        return self._asset_response(asset, action="generation_ready", status="ready")

    def retry_asset_generation(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._asset_project_scope(payload.get("project_id"))
        asset_id = _asset_id(payload.get("asset_id"), "asset_id")
        current = self.store.asset_item(asset_id)
        if current["project_id"] != _asset_id(payload.get("project_id"), "project_id"):
            raise ConsoleError("asset is not bound to the requested project")
        asset = self.store.retry_asset_generation(
            asset_id,
            expected_revision=payload.get("expected_revision"),
            operation_id=payload.get("operation_id"),
            generation_job_id=payload.get("generation_job_id"),
            now_ms=int(time.time() * 1000),
        )
        return self._asset_response(asset, action="generation_retry", status="queued")

    def trash_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._asset_project_scope(payload.get("project_id"))
        asset_id = _asset_id(payload.get("asset_id"), "asset_id")
        current = self.store.asset_item(asset_id)
        if current["project_id"] != _asset_id(payload.get("project_id"), "project_id"):
            raise ConsoleError("asset is not bound to the requested project")
        actor = payload.get("trashed_by") or payload.get("actor") or "user"
        asset = self.store.trash_asset(
            asset_id,
            expected_revision=payload.get("expected_revision"),
            trashed_by=actor,
            operation_id=payload.get("operation_id"),
            now_ms=int(time.time() * 1000),
        )
        return self._asset_response(asset, action="trash", status="trashed")

    def restore_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._asset_project_scope(payload.get("project_id"))
        asset_id = _asset_id(payload.get("asset_id"), "asset_id")
        current = self.store.asset_item(asset_id)
        if current["project_id"] != _asset_id(payload.get("project_id"), "project_id"):
            raise ConsoleError("asset is not bound to the requested project")
        actor = payload.get("restored_by") or payload.get("actor") or "user"
        asset = self.store.restore_asset(
            asset_id,
            expected_revision=payload.get("expected_revision"),
            restored_by=actor,
            operation_id=payload.get("operation_id"),
            now_ms=int(time.time() * 1000),
        )
        return self._asset_response(asset, action="restore", status="restored")

    def asset_media_item(self, asset_id: str, digest: str) -> dict[str, Any]:
        return self.store.asset_media_item(
            asset_id,
            digest,
            allowed_root=self.codex_home / PROOF_MEDIA_ROOT,
        )

    def purge_assets(self, *, project_id: str | None = None) -> dict[str, Any]:
        if project_id not in (None, ""):
            self._asset_project_scope(project_id)
        return self.store.purge_assets(project_id=project_id)

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

    def _auto_repair_policy(self) -> dict[str, Any]:
        base = {
            "key": AUTO_REPAIR_SETTING_KEY,
            "label": AUTO_REPAIR_LABEL,
            "default": False,
            "manual_available": True,
            "dispatch": "disabled",
            "automatic_request_mode": "bounded_existing_health_requests",
            "claim_limit": (
                "The canonical monitoring.auto_health_enabled setting is presented as Auto fix. "
                "It gates only the existing bounded advisory health-request path; repair dispatch, model use, "
                "and source, config, host, listener, or provider mutation remain disabled."
            ),
        }
        try:
            _, effective, _ = load_config(self.config_path)
        except ConsoleError as exc:
            return {
                **base,
                "state": "UNKNOWN",
                "status": "UNKNOWN",
                "enabled": False,
                "reason": f"canonical config could not be validated: {str(exc)[:256]}",
            }
        monitoring = effective.get("monitoring") if isinstance(effective, dict) else None
        declared = (
            isinstance(monitoring, dict)
            and "auto_health_enabled" in monitoring
            and AUTO_REPAIR_SETTING_KEY in EDITABLE_SETTINGS
            and isinstance(monitoring.get("auto_health_enabled"), bool)
        )
        if not declared:
            return {
                **base,
                "state": "UNAVAILABLE",
                "status": "UNAVAILABLE",
                "enabled": False,
                "automatic_request_mode": "none",
                "reason": "canonical config is missing monitoring.auto_health_enabled; Auto fix is fail-closed",
            }
        enabled = bool(monitoring["auto_health_enabled"])
        return {
            **base,
            "state": "KNOWN",
            "status": "ON" if enabled else "OFF",
            "enabled": enabled,
            "automatic_request_mode": "bounded_existing_health_requests" if enabled else "none",
            "reason": (
                "Auto fix is ON through canonical monitoring.auto_health_enabled; only the existing bounded "
                "advisory health-request path may record requests, while repair dispatch remains disabled because "
                "the path is not an allowlisted low-risk repair executor."
                if enabled else
                "Auto fix is OFF through canonical monitoring.auto_health_enabled; deterministic health checks "
                "remain active and automatic health requests, model use, and repair dispatch are disabled."
            ),
        }

    @staticmethod
    def _health_contract_status(checks: list[dict[str, Any]]) -> str:
        statuses = {str(check.get("status") or "UNKNOWN").upper() for check in checks}
        if "FAIL" in statuses:
            return "FAIL"
        if "UNKNOWN" in statuses:
            return "UNKNOWN"
        if "WARN" in statuses:
            return "WARN"
        return "PASS"

    def health_checks(
        self,
        overview: dict[str, Any] | None = None,
        *,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """Return deterministic local health checks without model calls or repair dispatch."""
        now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        checks: list[dict[str, Any]] = []

        source_server, mirror_server = _server_identity_paths()
        source_digest = mirror_digest = ""
        source_mirror_state = "unavailable"
        distinct = False
        if source_server is not None and mirror_server is not None:
            try:
                distinct = source_server != mirror_server and not os.path.samefile(source_server, mirror_server)
            except (FileNotFoundError, OSError):
                distinct = source_server != mirror_server
        if distinct and source_server.is_file() and mirror_server.is_file():
            try:
                source_digest = hashlib.sha256(source_server.read_bytes()).hexdigest()
                mirror_digest = hashlib.sha256(mirror_server.read_bytes()).hexdigest()
            except (OSError, ValueError):
                source_digest = mirror_digest = ""
            if source_digest and mirror_digest and source_digest == mirror_digest:
                source_mirror_state = "match"
            elif source_digest and mirror_digest:
                source_mirror_state = "mismatch"
        if source_mirror_state == "match":
            checks.append(_health_check(
                "process.source_mirror_parity", "PASS",
                "The local server source and plugin mirror have matching content.",
                observed_at_ms=now_ms,
                evidence=("local:server-source", "local:server-mirror"),
                recommended_action="No source-mirror repair action is required.",
                details={"source_mirror": source_mirror_state, "independent_identities": True},
            ))
        else:
            checks.append(_health_check(
                "process.source_mirror_parity", "FAIL" if source_mirror_state == "mismatch" else "UNKNOWN",
                "The local server source/mirror parity could not be established.",
                observed_at_ms=now_ms,
                evidence=("local:server-source", "local:server-mirror"),
                recommended_action="Restore one reviewed server source/mirror before claiming local parity.",
                details={
                    "source_mirror": source_mirror_state,
                    "independent_identities": distinct,
                },
            ))
        checks.append(_health_check(
            "process.listener_package_parity", "UNKNOWN",
            "The installed listener PID, loaded package, and manifest are not verified by this source-local probe.",
            observed_at_ms=now_ms,
            evidence=("local:process", "local:package-manifest"),
            recommended_action="Use a controlled local integration check to compare the listener command line, loaded path, and package manifest.",
            details={"source_mirror": "verified" if source_digest and source_digest == mirror_digest else "unverified", "installed_listener": "unverified"},
        ))

        roster_state = "UNKNOWN"
        roster_records: list[dict[str, Any]] = []
        root_statuses: Counter[str] = Counter()
        try:
            roster_state, roster_records, cursor, root_owners = self._host_project_records()
            if cursor is not None:
                for record in roster_records:
                    root_statuses[self._project_root_binding(record, root_owners).get("status", "UNKNOWN")] += 1
        except (ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
            roster_state = "UNKNOWN"
        if roster_state != "KNOWN":
            checks.append(_health_check(
                "project.roster_root_binding", "UNKNOWN",
                "The canonical saved-project roster or root bindings are unavailable.",
                observed_at_ms=now_ms,
                evidence=("local:host-projects",),
                recommended_action="Restore readable canonical host project and root tables; do not infer projects from task titles or paths.",
            ))
        elif any(root_statuses.get(status) for status in ("INVALID", "AMBIGUOUS", "UNKNOWN")):
            checks.append(_health_check(
                "project.roster_root_binding", "WARN",
                "The canonical project roster is readable but one or more root bindings are not usable.",
                observed_at_ms=now_ms,
                evidence=("local:host-projects",),
                recommended_action="Review the exact affected canonical root bindings before selecting or mutating a project.",
                details={"project_count": len(roster_records), "root_statuses": dict(root_statuses)},
            ))
        else:
            checks.append(_health_check(
                "project.roster_root_binding", "PASS",
                "The canonical saved-project roster and root bindings are readable.",
                observed_at_ms=now_ms,
                evidence=("local:host-projects",),
                recommended_action="No repair action is required.",
                details={"project_count": len(roster_records), "root_statuses": dict(root_statuses)},
            ))

        if not isinstance(overview, dict):
            try:
                overview = self._host_overview()
            except (ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
                overview = None
        navigation = self._navigation_payload(overview) if isinstance(overview, dict) else {}
        inventory = navigation.get("project_inventory") if isinstance(navigation, dict) else None
        nav_projects = navigation.get("projects") if isinstance(navigation, dict) else None
        nav_controllers = navigation.get("controllers") if isinstance(navigation, dict) else None
        if (
            not isinstance(inventory, dict)
            or inventory.get("state") != "KNOWN"
            or inventory.get("available") is not True
            or not isinstance(nav_projects, list)
            or not isinstance(nav_controllers, list)
        ):
            checks.append(_health_check(
                "projection.ctrl_activity", "UNKNOWN",
                "CTRL activity cannot be classified while the canonical project inventory is unavailable.",
                observed_at_ms=now_ms,
                evidence=("local:host-projects", "local:host-threads"),
                recommended_action="Restore the canonical host project inventory and refresh the read-only projection.",
            ))
        else:
            activity_fields_valid = all(
                isinstance(project, dict)
                and project.get("activity_status") in {"active", "recently_active", "inactive", "unknown"}
                and isinstance(project.get("activity_facts"), dict)
                and isinstance(controller, dict)
                for project in nav_projects
                for controller in [project]
            ) and all(
                isinstance(controller, dict)
                and controller.get("activity_status") in {"active", "recently_active", "inactive"}
                for controller in nav_controllers
            )
            visible_ctrls = [
                controller for controller in nav_controllers
                if controller.get("visibility") == "visible"
                and controller.get("archived") is False
                and _is_observed_ctrl_for_projection(controller)
            ]
            if not activity_fields_valid:
                checks.append(_health_check(
                    "projection.ctrl_activity", "FAIL",
                    "The activity projection is missing a typed status or activity fact.",
                    observed_at_ms=now_ms,
                    evidence=("local:host-threads", "local:navigation"),
                    recommended_action="Keep the affected projection unavailable until its host fields are complete.",
                ))
            else:
                checks.append(_health_check(
                    "projection.ctrl_activity", "PASS",
                    (
                        f"CTRL activity projection is readable ({len(visible_ctrls)} visible qualifying CTRLs)."
                        if visible_ctrls else "No qualifying visible CTRLs were observed; the empty result is known."
                    ),
                    observed_at_ms=now_ms,
                    evidence=("local:host-threads", "local:navigation"),
                    recommended_action="No repair action is required." if visible_ctrls else "Keep the empty result; do not synthesize a CTRL row.",
                    details={
                        "active_now": sum(item.get("activity_status") == "active" for item in visible_ctrls),
                        "recently_active": sum(item.get("activity_status") == "recently_active" for item in visible_ctrls),
                    },
                ))

        overview_controllers = overview.get("controllers") if isinstance(overview, dict) else None
        if not isinstance(overview_controllers, list):
            checks.append(_health_check(
                "host.thread_freshness_parent_edges", "UNKNOWN",
                "Host-thread freshness and parent-edge facts are unavailable.",
                observed_at_ms=now_ms,
                evidence=("local:host-threads",),
                recommended_action="Refresh the read-only host observation before acting on parent or status edges.",
            ))
        else:
            omitted = sum(
                int(item.get("older_lanes_omitted") or 0)
                for item in overview_controllers
                if isinstance(item, dict) and isinstance(item.get("older_lanes_omitted"), int)
            )
            unavailable = sum(
                item.get("controller_classification") == "unavailable"
                for item in overview_controllers
                if isinstance(item, dict)
            )
            status = "WARN" if omitted or unavailable else "PASS"
            checks.append(_health_check(
                "host.thread_freshness_parent_edges", status,
                "Host freshness and parent-edge ambiguity are retained as bounded display facts." if status == "WARN" else "Host freshness and parent-edge facts are readable.",
                observed_at_ms=now_ms,
                evidence=("local:host-threads", "local:spawn-edges"),
                recommended_action=(
                    "Review ambiguous or omitted host edges; do not infer authority from them."
                    if status == "WARN" else "No repair action is required."
                ),
                details={"controllers": len(overview_controllers), "older_lanes_omitted": omitted, "unavailable_classifications": unavailable},
            ))

        progress_projection: dict[str, Any] | None = None
        try:
            progress_projection = self.progress_ledger.replay()
            progress_cursor = progress_projection.get("cursor") if isinstance(progress_projection, dict) else None
            if not isinstance(progress_cursor, dict):
                raise ProgressEventError("progress cursor is unavailable")
            checks.append(_health_check(
                "ledger.cursor_freshness", "PASS", "The persisted work-ledger cursor is readable.",
                observed_at_ms=now_ms, evidence=("local:progress-ledger",),
                recommended_action="No repair action is required.", details={"cursor_fields": sorted(progress_cursor)},
            ))
        except (OSError, ProgressEventError, TypeError, ValueError):
            checks.append(_health_check(
                "ledger.cursor_freshness", "UNKNOWN", "The persisted work-ledger cursor could not be read.",
                observed_at_ms=now_ms, evidence=("local:progress-ledger",),
                recommended_action="Keep progress metrics unavailable until the existing ledger is readable.",
            ))

        try:
            proof_cursor = self.store.proof_cursor()
            proof_items = self.store.proof_feed()
            if not isinstance(proof_cursor.get("identity"), str):
                raise ConsoleError("proof cursor identity is unavailable")
            checks.append(_health_check(
                "asset.evidence_store", "PASS", "The existing asset/evidence store and cursor are readable.",
                observed_at_ms=now_ms, evidence=("local:console-store", "local:proof-store"),
                recommended_action="No repair action is required.", details={"evidence_items": len(proof_items)},
            ))
        except (ConsoleError, OSError, sqlite3.Error, TypeError, ValueError):
            checks.append(_health_check(
                "asset.evidence_store", "FAIL", "The existing asset/evidence store or cursor is unreadable.",
                observed_at_ms=now_ms, evidence=("local:console-store", "local:proof-store"),
                recommended_action="Request a manual diagnostic review; do not fabricate asset availability or file URLs.",
            ))

        config_ok = True
        try:
            load_config(self.config_path)
        except ConsoleError:
            config_ok = False
        if not config_ok:
            checks.append(_health_check(
                "config.schema_compatibility_redaction", "FAIL", "The canonical SWARM config failed validation.",
                observed_at_ms=now_ms, evidence=("local:config",),
                recommended_action="Review the canonical config through its validator; do not apply unknown keys.",
            ))
        else:
            policy = self._auto_repair_policy()
            checks.append(_health_check(
                "config.schema_compatibility_redaction",
                "WARN" if policy["state"] == "UNAVAILABLE" else "PASS",
                "Canonical config validation succeeded, but the canonical Auto fix setting is unavailable."
                if policy["state"] == "UNAVAILABLE" else "Canonical config validation and redacted settings access succeeded.",
                observed_at_ms=now_ms, evidence=("local:config",),
                recommended_action=(
                    "Keep Auto fix disabled and restore monitoring.auto_health_enabled through the canonical schema owner."
                    if policy["state"] == "UNAVAILABLE" else "No repair action is required."
                ),
                details={
                    "auto_repair": policy["status"],
                    "setting_key": AUTO_REPAIR_SETTING_KEY,
                    "redaction": "server_owned",
                },
            ))

        checks.append(_health_check(
            "api.health_endpoint_response", "PASS", "This local health endpoint produced a valid response.",
            observed_at_ms=now_ms, evidence=("local:api",),
            recommended_action="No repair action is required.",
        ))

        refresh_ms = None
        generated_at = overview.get("generated_at") if isinstance(overview, dict) else None
        if isinstance(generated_at, str):
            try:
                refresh_ms = int(datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp() * 1000)
            except (TypeError, ValueError, OverflowError):
                refresh_ms = None
        heartbeat = int(overview.get("heartbeat_minutes") or 30) if isinstance(overview, dict) else 30
        refresh_limit_ms = max(5 * 60 * 1000, heartbeat * 2 * 60 * 1000)
        if refresh_ms is None:
            checks.append(_health_check(
                "refresh.last_success", "UNKNOWN", "No successful host refresh timestamp is available.",
                observed_at_ms=now_ms, evidence=("local:refresh",),
                recommended_action="Refresh the read-only host projection before relying on its status.",
            ))
        else:
            refresh_status = "PASS" if now_ms - refresh_ms <= refresh_limit_ms else "WARN"
            checks.append(_health_check(
                "refresh.last_success", refresh_status,
                "The last host projection refresh is within the documented freshness window." if refresh_status == "PASS" else "The last host projection refresh is older than the documented freshness window.",
                observed_at_ms=refresh_ms, evidence=("local:refresh",),
                recommended_action="Refresh the read-only host projection." if refresh_status == "WARN" else "No repair action is required.",
                details={"age_ms": max(0, now_ms - refresh_ms), "freshness_window_ms": refresh_limit_ms},
            ))

        overview_nodes = overview.get("nodes") if isinstance(overview, dict) else None
        observed_host_tasks = (
            sum(isinstance(node, dict) and not node.get("virtual") for node in overview_nodes)
            if isinstance(overview_nodes, list) else None
        )
        root_degraded = roster_state != "KNOWN" or any(
            root_statuses.get(status) for status in ("INVALID", "AMBIGUOUS", "UNKNOWN")
        )
        snapshot_stale = refresh_ms is None or now_ms - refresh_ms > refresh_limit_ms
        connection_status = (
            "UNAVAILABLE" if not isinstance(overview_nodes, list)
            else "DEGRADED" if root_degraded or snapshot_stale
            else "CONNECTED"
        )
        codex_connection = {
            "status": connection_status,
            "connection_scope": "LOCAL_METADATA_SNAPSHOT",
            "transport_status": "UNVERIFIED",
            "source": "local:codex-state-db+host-project-roster",
            "observed_at_ms": refresh_ms,
            "project_count": len(roster_records) if roster_state != "UNKNOWN" else None,
            "observed_host_tasks": observed_host_tasks,
            "actionable_repair": (
                "Restore the readable canonical Codex state database and required host tables."
                if connection_status == "UNAVAILABLE" else
                "Refresh stale metadata or repair ambiguous saved-project root bindings before relying on project-scoped health."
                if connection_status == "DEGRADED" else
                "No repair action is required."
            ),
            "claim_limit": "CONNECTED means the local metadata snapshot is readable and current; transport remains UNVERIFIED without separate App Server proof.",
        }
        topology = None
        if isinstance(overview, dict) and isinstance(progress_projection, dict):
            try:
                topology = self._topology_projection(overview)
            except (ConsoleError, OSError, sqlite3.Error, ProgressEventError, TypeError, ValueError):
                topology = None
        if (
            roster_state == "UNKNOWN"
            or not isinstance(topology, dict)
            or topology.get("state") in {"UNKNOWN", "LOADING"}
        ):
            coverage_status, coverage_reason, bound_agents, independent_tasks = (
                "UNAVAILABLE", "Binding projection unavailable", None, None,
            )
        else:
            bound_agents = len(topology.get("nodes", []))
            independent_tasks = len(topology.get("independent_nodes", []))
            reconciled = observed_host_tasks == bound_agents + independent_tasks
            if roster_state != "KNOWN":
                coverage_status, coverage_reason = "DEGRADED", "Project roster is partial"
            elif topology.get("state") == "PARTIAL":
                coverage_status, coverage_reason = "DEGRADED", str(topology.get("reason") or "Binding projection is partial")
            elif topology.get("state") in {"KNOWN", "EMPTY"} and reconciled and (observed_host_tasks == 0 or independent_tasks == 0):
                coverage_status, coverage_reason = "CONNECTED", None
            elif not reconciled:
                coverage_status, coverage_reason = "DEGRADED", "Binding counts do not reconcile"
            elif bound_agents == 0 and independent_tasks:
                coverage_status, coverage_reason = "DEGRADED", "No authoritative SWARM bindings"
            else:
                coverage_status, coverage_reason = "DEGRADED", "Some host tasks remain independent"
        binding_coverage = {
            "status": coverage_status,
            "reason": coverage_reason,
            "source": "local:host-threads+progress-ledger",
            "observed_at_ms": refresh_ms,
            "project_count": len(roster_records) if roster_state != "UNKNOWN" else None,
            "observed_host_tasks": observed_host_tasks,
            "bound_agents": bound_agents,
            "independent_tasks": independent_tasks,
            "execution_authority": False,
            "actionable_repair": (
                "Restore readable host and Ledger projections before evaluating binding coverage."
                if coverage_status == "UNAVAILABLE" else
                "No authoritative SWARM bindings. Restore a host-verified custody path before changing topology."
                if coverage_reason == "No authoritative SWARM bindings" else
                "Restore the complete canonical project roster before evaluating binding coverage."
                if coverage_reason == "Project roster is partial" else
                "Resolve missing or conflicting retained bindings before relying on topology coverage."
                if topology.get("state") == "PARTIAL" else
                "Refresh the host and Ledger projections until their binding counts reconcile."
                if coverage_reason == "Binding counts do not reconcile" else
                "Review remaining independent tasks; bind only those with exact host authority."
                if coverage_status == "DEGRADED" else
                "No repair action is required."
            ),
            "claim_limit": "Coverage counts exact retained identity bindings only; execution authority is false and is never inferred from titles, cwd labels, or host activity.",
        }

        health_status = self._health_contract_status(checks)
        if health_status != "FAIL" and "UNAVAILABLE" in {connection_status, coverage_status}:
            health_status = "UNKNOWN"
        elif health_status == "PASS" and "DEGRADED" in {connection_status, coverage_status}:
            health_status = "WARN"
        return {
            "schema_version": 1,
            "status": health_status,
            "observed_at_ms": now_ms,
            "last_successful_refresh_at_ms": refresh_ms,
            "checks": checks,
            "codex_connection": codex_connection,
            "binding_coverage": binding_coverage,
            "repair_policy": self._auto_repair_policy(),
            "claim_limit": (
                "Checks use existing local process, host DB, config, ledger, and console-store facts. "
                "They do not poll providers, call models, mutate source/config/host/listener state, or dispatch "
                "repair work. monitoring.auto_health_enabled is the only canonical Auto fix preference: OFF "
                "keeps deterministic checks active while suppressing automatic health requests; ON permits only "
                "the existing bounded advisory health-request path, not repair execution."
            ),
        }

    def health_contract(self) -> dict[str, Any]:
        return {"ok": True, **self.health_checks()}

    def prepare_health_repair(
        self,
        check_ids: Any,
        *,
        scope: Any,
        acknowledge: Any,
        dry_run: Any,
    ) -> dict[str, Any]:
        if not isinstance(check_ids, list) or not check_ids:
            raise ConsoleError("check_ids must be a non-empty list")
        if len(check_ids) > 16 or any(not isinstance(check_id, str) or not check_id.strip() for check_id in check_ids):
            raise ConsoleError("check_ids contains an invalid value")
        if not isinstance(acknowledge, bool) or not isinstance(dry_run, bool):
            raise ConsoleError("acknowledge and dry_run must be booleans")
        contract = self.health_checks()
        by_id = {check["id"]: check for check in contract["checks"]}
        normalized_ids = list(dict.fromkeys(check_id.strip() for check_id in check_ids))
        if any(check_id not in by_id for check_id in normalized_ids):
            raise ConsoleError("repair check id is unknown")
        selected = [by_id[check_id] for check_id in normalized_ids]
        if any(check["status"] == "PASS" for check in selected):
            raise ConsoleError("repair requires only failing, warning, or unknown checks")
        with self.write_lock:
            result = self.store.prepare_health_repair(
                selected,
                scope=str(scope or "all"),
                acknowledge=acknowledge,
                dry_run=dry_run,
                now_ms=int(time.time() * 1000),
            )
        return {"ok": True, "request": result, "repair_policy": contract["repair_policy"]}

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
        health_contract = self.health_contract()
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
                **health_contract,
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
            "auto_repair": self._auto_repair_policy(),
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
            "claim_limit": (
                "monitoring.auto_health_enabled is the canonical setting presented as Auto fix. OFF leaves "
                "deterministic checks active without automatic health requests or model use. ON can record only "
                "bounded existing advisory health requests; repair dispatch remains disabled because this path is "
                "broader than an allowlisted low-risk repair executor. Manual preparation remains acknowledgement-gated."
            ),
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
            "reset_contract": {
                "endpoint": "/api/ctrl-settings/reset",
                "requires": ["ctrl_id", "expected_revision", "acknowledge", "operation_id"],
                "audit_event": CONFIG_EVENT_KIND,
            },
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

    def reset_ctrl_settings(
        self,
        ctrl_id: str,
        expected_revision: int,
        *,
        acknowledge: Any,
        operation_id: Any,
    ) -> dict[str, Any]:
        _, _, overlay = self._ctrl_context(ctrl_id)
        if acknowledge is not True:
            raise ConsoleError("CTRL reset requires acknowledge=true")
        operation_id = _auto_id(operation_id, "operation_id")
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise ConsoleError("CTRL override revision is invalid")
        normalized_ctrl_id = _safe_metadata_text(ctrl_id, "ctrl_id", maximum=256)
        scope = {"type": "ctrl", "ctrl_id": normalized_ctrl_id}
        request_digest = _config_sha256(b"ctrl-settings-reset")
        changed_paths = sorted(f"ctrl.{key}" for key in overlay["override"])
        audit = self._config_operation_audit(
            action="ctrl_settings_reset",
            operation_id=operation_id,
            scope=scope,
            expected_revision=expected_revision,
            request_digest=request_digest,
            new_revision=0,
            changed_paths=changed_paths,
            source_kind="ctrl_settings_overlay",
        )
        retained = self.store.config_event(operation_id)
        replay = self._config_replay_receipt(
            retained,
            action="ctrl_settings_reset",
            operation_id=operation_id,
            scope=scope,
            expected_revision=expected_revision,
            request_digest=request_digest,
        )
        if replay is not None:
            return {
                **self.ctrl_settings(normalized_ctrl_id),
                "reset": True,
                "mutation_receipt": replay,
            }
        result = self.store.reset_ctrl_override(
            normalized_ctrl_id,
            expected_revision=expected_revision,
            operation_id=operation_id,
            audit_payload=audit,
            now_ms=int(time.time() * 1000),
        )
        with self.overview_lock:
            self._store_generation += 1
        projection = {**self.ctrl_settings(normalized_ctrl_id), "reset": result["reset"]}
        projection["mutation_receipt"] = {
            "accepted": True,
            "action": "ctrl_settings_reset",
            "operation_id": operation_id,
            "replayed": bool(result.get("replayed")),
            "scope": scope,
            "expected_revision": expected_revision,
            "new_revision": result["revision"],
            "changed_paths": changed_paths,
            "acknowledged": True,
            "audit_event": CONFIG_EVENT_KIND,
            "source_kind": "ctrl_settings_overlay",
            "claim_limit": "Only this observed CTRL's model/reasoning overlay was reset; global and project config remain unchanged.",
        }
        return projection

    def clear_history(self) -> dict[str, Any]:
        with self.write_lock, self.proof_lock:
            proof = clear_proof_storage(self.codex_home)
            result = self.store.clear_history()
        with self.overview_lock:
            self._store_generation += 1
        return {**result, "proof": proof}

    def restore_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = {"scope", "expected_revision", "acknowledge", "operation_id"}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ConsoleError("settings restore requires exact scope, expected_revision, acknowledge, and operation_id fields")
        scope = payload["scope"]
        if isinstance(scope, dict) and str(scope.get("type") or "").strip().casefold() == "ctrl":
            if set(scope) != {"type", "ctrl_id"}:
                raise ConsoleError("CTRL restore scope requires exact type and ctrl_id fields")
            return self.reset_ctrl_settings(
                scope["ctrl_id"],
                payload["expected_revision"],
                acknowledge=payload["acknowledge"],
                operation_id=payload["operation_id"],
            )
        return self.reset_config_source(payload)

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

    def _config_payload(self, query: dict[str, str] | None = None) -> dict[str, Any]:
        query = query or {}
        if not query:
            scope: dict[str, Any] = {"type": "global"}
        elif set(query) == {"scope"} and query.get("scope", "").casefold() == "global":
            scope = {"type": "global"}
        elif set(query) == {"scope", "project_id"} and query.get("scope", "").casefold() == "project":
            scope = {"type": "project", "project_id": query.get("project_id", "")}
        else:
            raise ConsoleError("config GET accepts no query or exact scope=global/project selection")
        projection = getattr(self.server.app, "config_projection", None)
        if callable(projection):
            payload = projection(scope)
        else:
            # Keep lightweight handler fixtures and older local embedders
            # readable while the production App owns the revisioned editor.
            legacy = redacted_config_snapshot(self.server.app.config_path)
            payload = {
                **legacy,
                "ok": True,
                "scope": scope,
                "source_path": str(self.server.app.config_path),
                "path": str(self.server.app.config_path),
                "text": "",
                "editable_text": "",
                "opaque_placeholders": [],
                "write_contract": {"available": False, "reason": "config source projection is unavailable"},
            }
        local = self._peer_is_trusted_local()
        payload["read_only"] = not local
        payload["source_path"] = payload["source_path"] if local else ""
        payload["path"] = payload["path"] if local else ""
        if not local:
            payload["text"] = ""
            payload["editable_text"] = ""
            payload["opaque_placeholders"] = []
            payload["write_contract"] = {
                **payload.get("write_contract", {}),
                "available": False,
                "reason": "local same-device access is required for config source reads and writes",
            }
            project = payload.get("project")
            if isinstance(project, dict):
                project["root"] = None
                binding = project.get("root_binding")
                if isinstance(binding, dict):
                    binding["value"] = None
        else:
            payload["write_contract"] = {
                **payload.get("write_contract", {}),
                "available": True,
            }
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
                    {
                        "ok": ready,
                        "service": "swarm-console",
                        "instance_id": INSTANCE_ID,
                        "build_id": SERVER_BUILD_ID,
                    },
                )
                return
            if path == "/api/bootstrap":
                self._json(HTTPStatus.OK, self._bootstrap_payload())
                return
            if path == "/api/profile":
                self._json(HTTPStatus.OK, self.server.app.profile_presentation())
                return
            if path == "/api/projects":
                if not self._peer_is_trusted_local():
                    self._error(HTTPStatus.FORBIDDEN, "project roster requires local access")
                    return
                self._json(HTTPStatus.OK, self.server.app.project_roster())
                return
            if path == "/api/projects/settings":
                if not self._peer_is_trusted_local():
                    self._error(HTTPStatus.FORBIDDEN, "project settings require local access")
                    return
                if set(query) != {"project_id"}:
                    self._error(HTTPStatus.BAD_REQUEST, "project settings requires exact project_id")
                    return
                self._json(HTTPStatus.OK, self.server.app.project_settings(query["project_id"]))
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
            role_avatar_match = re.fullmatch(r"/assets/role-avatars/([a-z0-9_]+)\.png", path)
            if role_avatar_match:
                try:
                    item = self.server.app.role_avatar_response(
                        role_avatar_match.group(1), self.headers.get("Accept", "")
                    )
                except NotAcceptableError as error:
                    self._error(HTTPStatus.NOT_ACCEPTABLE, str(error))
                    return
                except ConsoleError as error:
                    self._error(HTTPStatus.NOT_FOUND, str(error))
                    return
                body = item["body"]
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", item["media_type"])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("ETag", f'"{item["digest"]}"')
                self.send_header("Vary", "Accept")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)
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
            if path == "/api/assets":
                if set(query) - {"project_id", "projection"}:
                    self._error(HTTPStatus.BAD_REQUEST, "asset listing accepts only project_id and projection")
                    return
                self._json(
                    HTTPStatus.OK,
                    self.server.app.assets_projection(
                        project_id=query.get("project_id"),
                        projection=query.get("projection", "active"),
                    ),
                )
                return
            if path == "/api/assets/events":
                if set(query) - {"project_id", "after_sequence", "limit"}:
                    self._error(HTTPStatus.BAD_REQUEST, "asset events accepts only project_id, after_sequence, and limit")
                    return
                try:
                    after_sequence = int(query.get("after_sequence", "0"))
                    limit = int(query.get("limit", "64"))
                except ValueError as exc:
                    raise ConsoleError("asset event cursor and limit must be integers") from exc
                self._json(
                    HTTPStatus.OK,
                    self.server.app.asset_event_projection(
                        project_id=query.get("project_id"),
                        after_sequence=after_sequence,
                        limit=limit,
                    ),
                )
                return
            if path.startswith("/api/assets/") and path.endswith("/preview"):
                if self.headers.get("Origin") and not self._same_origin():
                    self._error(HTTPStatus.FORBIDDEN, "same-origin asset preview request required")
                    return
                asset_id = unquote(path[len("/api/assets/") : -len("/preview")]).strip("/")
                item = self.server.app.asset_media_item(asset_id, query.get("digest", ""))
                self._registered_media(item)
                return
            if path.startswith("/api/assets/"):
                if set(query) - {"project_id"}:
                    self._error(HTTPStatus.BAD_REQUEST, "asset detail accepts only project_id")
                    return
                asset_id = unquote(path[len("/api/assets/") :]).strip("/")
                if not asset_id:
                    self._error(HTTPStatus.NOT_FOUND, "asset not found")
                    return
                self._json(
                    HTTPStatus.OK,
                    self.server.app.asset_detail(asset_id, project_id=query.get("project_id")),
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
            if path == "/api/health":
                self._json(HTTPStatus.OK, self.server.app.health_contract())
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
                self._json(HTTPStatus.OK, self._config_payload(query))
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
            if path == "/api/projects":
                payload = self._payload()
                if set(payload) != {"name", "root", "acknowledge"}:
                    raise ConsoleError("project creation requires exact name, root, and acknowledge fields")
                with self.server.app.write_lock:
                    result = self.server.app.create_project(
                        payload["name"], payload["root"], payload["acknowledge"],
                    )
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/projects/settings":
                payload = self._payload()
                if set(payload) != {"project_id", "changes", "expected_revision", "accepted_cursor", "acknowledge"}:
                    raise ConsoleError(
                        "project settings update requires exact project_id, changes, expected_revision, accepted_cursor, and acknowledge fields"
                    )
                with self.server.app.write_lock:
                    result = self.server.app.update_project_settings(
                        payload["project_id"], payload["changes"], payload["expected_revision"],
                        payload["accepted_cursor"], payload["acknowledge"],
                    )
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/config":
                payload = self._payload()
                with self.server.app.write_lock:
                    result = self.server.app.update_config_source(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/config/reset":
                payload = self._payload()
                with self.server.app.write_lock:
                    result = self.server.app.reset_config_source(payload)
                self._json(HTTPStatus.OK, result)
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
            if path == "/api/assets/generation":
                payload = self._payload()
                required = {
                    "project_id", "logical_asset_id", "generation_job_id", "operation_id",
                    "idempotency_key", "request_summary", "presentation", "provenance",
                }
                allowed = required | {"asset_id", "parent_revision_id", "job_metadata"}
                if not required <= set(payload) or not set(payload) <= allowed:
                    raise ConsoleError(
                        "asset generation acceptance requires the canonical project, identity, operation, request, presentation, and provenance fields"
                    )
                with self.server.app.write_lock:
                    result = self.server.app.accept_asset_generation(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/assets/generation/transition":
                payload = self._payload()
                required = {"project_id", "asset_id", "expected_revision", "operation_id", "status"}
                allowed = required | {"measured_progress", "measured_progress_provenance"}
                if not required <= set(payload) or not set(payload) <= allowed:
                    raise ConsoleError("asset generation transition requires exact identity, revision, operation, and status fields")
                with self.server.app.write_lock:
                    result = self.server.app.advance_asset_generation(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/assets/generation/fail":
                payload = self._payload()
                required = {"project_id", "asset_id", "expected_revision", "operation_id", "error_class", "retry_eligible"}
                if set(payload) != required:
                    raise ConsoleError("asset generation failure requires exact project, identity, revision, operation, error, and retry fields")
                with self.server.app.write_lock:
                    result = self.server.app.fail_asset_generation(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/assets/generation/cancel":
                payload = self._payload()
                required = {"project_id", "asset_id", "expected_revision", "operation_id"}
                if set(payload) != required:
                    raise ConsoleError("asset generation cancellation requires exact project, identity, revision, and operation fields")
                with self.server.app.write_lock:
                    result = self.server.app.cancel_asset_generation(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/assets/generation/admit":
                payload = self._payload()
                required = {"project_id", "asset_id", "expected_revision", "operation_id", "locator", "digest", "provenance"}
                if set(payload) != required:
                    raise ConsoleError("asset file admission requires exact project, identity, revision, operation, file digest, locator, and provenance fields")
                with self.server.app.write_lock:
                    result = self.server.app.admit_asset_file(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/assets/generation/retry":
                payload = self._payload()
                required = {"project_id", "asset_id", "expected_revision", "operation_id", "generation_job_id"}
                if set(payload) != required:
                    raise ConsoleError("asset generation retry requires exact project, identity, revision, new operation, and new job fields")
                with self.server.app.write_lock:
                    result = self.server.app.retry_asset_generation(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/assets/trash":
                payload = self._payload()
                required = {"project_id", "asset_id", "expected_revision", "operation_id"}
                allowed = required | {"actor", "trashed_by"}
                if not required <= set(payload) or not set(payload) <= allowed:
                    raise ConsoleError("asset trash requires exact project, identity, revision, and operation fields")
                with self.server.app.write_lock:
                    result = self.server.app.trash_asset(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/assets/restore":
                payload = self._payload()
                required = {"project_id", "asset_id", "expected_revision", "operation_id"}
                allowed = required | {"actor", "restored_by"}
                if not required <= set(payload) or not set(payload) <= allowed:
                    raise ConsoleError("asset restore requires exact project, identity, revision, and operation fields")
                with self.server.app.write_lock:
                    result = self.server.app.restore_asset(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/assets/purge":
                payload = self._payload()
                if set(payload) - {"project_id"}:
                    raise ConsoleError("asset purge accepts only project_id")
                with self.server.app.write_lock:
                    result = self.server.app.purge_assets(project_id=payload.get("project_id"))
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
                with self.server.app.write_lock:
                    result = self.server.app.update_config_source(payload)
                self._json(HTTPStatus.OK, result)
                return
            if path == "/api/health/repair":
                payload = self._payload()
                if set(payload) != {"check_ids", "scope", "acknowledge", "dry_run"}:
                    raise ConsoleError(
                        "health repair requires exact check_ids, scope, acknowledge, and dry_run fields"
                    )
                result = self.server.app.prepare_health_repair(
                    payload["check_ids"],
                    scope=payload["scope"],
                    acknowledge=payload["acknowledge"],
                    dry_run=payload["dry_run"],
                )
                self._json(HTTPStatus.OK, result)
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
                if not isinstance(payload, dict) or set(payload) != {"ctrl_id", "expected_revision", "acknowledge", "operation_id"}:
                    raise ConsoleError(
                        "CTRL reset requires exact ctrl_id, expected_revision, acknowledge, and operation_id fields"
                    )
                result = self.server.app.reset_ctrl_settings(
                    payload["ctrl_id"],
                    payload["expected_revision"],
                    acknowledge=payload["acknowledge"],
                    operation_id=payload["operation_id"],
                )
                self._json(HTTPStatus.OK, {"ok": True, **result})
                return
            if path in {"/api/logs/clear", "/api/storage/clear"}:
                self._json(HTTPStatus.OK, self.server.app.clear_history())
                return
            if path == "/api/settings/restore":
                payload = self._payload()
                if not isinstance(payload, dict) or set(payload) != {"scope", "expected_revision", "acknowledge", "operation_id"}:
                    raise ConsoleError(
                        "settings restore requires exact scope, expected_revision, acknowledge, and operation_id fields"
                    )
                with self.server.app.write_lock:
                    result = self.server.app.restore_settings(payload)
                self._json(HTTPStatus.OK, {"ok": True, **result})
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
