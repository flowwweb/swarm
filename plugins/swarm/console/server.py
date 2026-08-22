#!/usr/bin/env python3
"""Local SWARM settings, hierarchy, and analytics console."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import ipaddress
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
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
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
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
TOKEN_RETENTION_DAYS = 30
TOKEN_SOURCE_SQLITE = "host_reported_cumulative_delta"
TOKEN_SOURCE_CODEX_JSONL = "codex_jsonl_token_count"
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
PROOF_EVENT_ROOT = Path("swarm") / "proof-events"
PROOF_MEDIA_ROOT = Path("swarm") / "proof-media"
CTRL_OVERRIDE_FIELDS: dict[str, type] = {
    "model": str,
    "reasoning": str,
    "service_tier": str,
}
MEDIA_KINDS = frozenset({"imagegen", "image", "mockup", "preview", "screenshot", "browser", "recording"})
MEDIA_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"})
MEDIA_TYPES = frozenset({
    "image/png", "image/jpeg", "image/webp", "image/gif", "video/mp4", "video/webm",
})

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/swarm-favicon.svg": ("swarm-favicon.svg", "image/svg+xml"),
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
    "logging.task_event_limit": int,
    "console.open_on_start": bool,
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
                    status TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ctrl_overrides (
                    ctrl_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    fields_json TEXT NOT NULL,
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
            connection.execute(
                "UPDATE proof_media SET disposition='PENDING', receipt='legacy:available', "
                "surface_kind='available_media' WHERE disposition IN ('AVAILABLE', 'SURFACED')"
            )
            connection.commit()

    def _retention_cutoff(self, now_ms: int) -> int:
        return now_ms - TOKEN_RETENTION_DAYS * 24 * 60 * 60 * 1000

    def observe_overview(self, overview: dict[str, Any], *, now_ms: int, trigger: str, heartbeat_minutes: int, codex_home: Path | None = None) -> None:
        nodes = [node for node in overview.get("nodes", []) if not node.get("virtual")]
        node_by_id = {str(node["id"]): node for node in nodes}
        dependencies: dict[str, list[str]] = {}
        for link in overview.get("links", []):
            dependencies.setdefault(str(link["target"]), []).append(str(link["source"]))
        with self._lock, closing(self._connect()) as connection:
            bucket_ms = now_ms - (now_ms % (TOKEN_SAMPLE_SECONDS * 1000))
            for node in nodes:
                thread_id = _safe_metadata_text(str(node["id"]), "thread id", maximum=256)
                project_id = _safe_metadata_text(str(node["project_id"]), "project id", maximum=256)
                sqlite_cumulative = max(0, int(node.get("tokens") or 0))
                jsonl_cumulative = None if codex_home is None else _codex_jsonl_token_count(codex_home, thread_id)
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
                created_at = int(node.get("created_at") or updated_at or now_ms)
                elapsed_ms = max(0, now_ms - created_at)
                quiet_ms = max(0, now_ms - (updated_at or created_at))
                token_signal = max(0, int(node.get("tokens") or 0))
                heartbeat_ms = max(1, heartbeat_minutes) * 60 * 1000
                proof = node.get("proof_snapshot") if isinstance(node.get("proof_snapshot"), dict) else {}
                gates = proof.get("gates") if isinstance(proof.get("gates"), list) else []
                verified_gates = sum(1 for gate in gates if str(gate.get("status", "")).upper() == "PASS")
                proof_ratio = verified_gates / len(gates) if gates else 0.0
                round_to = 15 * 60 * 1000

                def rounded_duration(raw_ms: float, minimum_ms: int, maximum_ms: int) -> int:
                    bounded = max(minimum_ms, min(maximum_ms, int(raw_ms)))
                    return max(round_to, int(round(bounded / round_to)) * round_to)

                if status in {"done", "archived"}:
                    forecast_status, confidence, duration_ms = "complete", 100, 0
                elif blocked_dependency:
                    forecast_status = "blocked"
                    confidence = max(20, min(45, 40 - int(quiet_ms / heartbeat_ms) * 5))
                    duration_ms = rounded_duration(2 * 60 * 60 * 1000 + quiet_ms * 0.5, 2 * 60 * 60 * 1000, 24 * 60 * 60 * 1000)
                elif status == "active":
                    forecast_status = "on_track" if quiet_ms <= heartbeat_ms * 2 else "at_risk"
                    confidence = max(35, min(90, 55 + (20 if quiet_ms <= heartbeat_ms else 0) + round(proof_ratio * 15)))
                    observed_work = min(elapsed_ms, 8 * 60 * 60 * 1000) * 0.25
                    complexity = min(4 * 60 * 60 * 1000, math.log2(token_signal + 1) * 12 * 60 * 1000)
                    remaining_factor = max(0.25, 1.0 - min(0.75, proof_ratio))
                    duration_ms = rounded_duration((45 * 60 * 1000 + observed_work + complexity) * remaining_factor, 30 * 60 * 1000, 8 * 60 * 60 * 1000)
                else:
                    forecast_status = "at_risk"
                    confidence = max(20, min(55, 50 - int(quiet_ms / heartbeat_ms) * 5 + round(proof_ratio * 10)))
                    duration_ms = rounded_duration(90 * 60 * 1000 + quiet_ms * 0.5, 90 * 60 * 1000, 12 * 60 * 60 * 1000)
                signature = json.dumps(
                    ("observed-signals-v2", status, updated_at, tuple(sorted(dependency_ids)), forecast_status),
                    separators=(",", ":"),
                )
                latest = connection.execute(
                    "SELECT * FROM eta_forecasts WHERE task_id = ? ORDER BY revision DESC LIMIT 1",
                    (thread_id,),
                ).fetchone()
                should_append = latest is None or str(latest["signature"]) != signature
                if trigger == "heartbeat" and forecast_status in {"at_risk", "blocked"}:
                    should_append = should_append or latest is None or int(latest["last_calculated_at_ms"]) < now_ms - heartbeat_minutes * 60 * 1000
                if should_append:
                    revision = 1 if latest is None else int(latest["revision"]) + 1
                    eta_start = None if forecast_status == "complete" else now_ms + (30 * 60 * 1000 if forecast_status == "blocked" else 0)
                    eta_end = None if eta_start is None else eta_start + duration_ms
                    reason = (
                        "Completed host task."
                        if forecast_status == "complete"
                        else "Heartbeat found no recent host task update; forecast is at risk."
                        if forecast_status == "at_risk" and trigger == "heartbeat"
                        else "Observed dependency is not complete; forecast is blocked."
                        if forecast_status == "blocked"
                        else "Estimate uses observed task age, activity, token change, proof progress, and dependencies."
                    )
                    connection.execute(
                        """
                        INSERT INTO eta_forecasts(
                            task_id, project_id, revision, eta_start_ms, eta_end_ms,
                            confidence, status, reason, last_progress_at_ms,
                            last_calculated_at_ms, trigger, signature
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            thread_id,
                            project_id,
                            revision,
                            eta_start,
                            eta_end,
                            confidence,
                            forecast_status,
                            reason,
                            updated_at,
                            now_ms,
                            trigger,
                            signature,
                        ),
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
            }
            for row in rows
        }

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
                "SELECT * FROM proof_media WHERE " + " AND ".join(conditions) + " ORDER BY updated_at_ms DESC",
                tuple(args),
            ).fetchall()
        return [self._public_proof_row(row) for row in rows]

    def proof_sequence(self) -> int:
        """Return a cheap local cursor for surfaced proof feed changes."""
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(updated_at_ms), 0) sequence FROM proof_media WHERE disposition='PENDING'"
            ).fetchone()
        return int(row["sequence"] or 0)

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
            connection.commit()
            row = connection.execute("SELECT * FROM proof_media WHERE evidence_id=?", (evidence_id,)).fetchone()
        return self._public_proof_row(row)

    def _proof_event_receipts(self) -> dict[str, tuple[int, int, str]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT event_name, event_mtime_ns, event_size, status FROM proof_event_receipts"
            ).fetchall()
        return {
            str(row["event_name"]): (int(row["event_mtime_ns"]), int(row["event_size"]), str(row["status"]))
            for row in rows
        }

    def _record_proof_event_receipt(
        self,
        event_name: str,
        *,
        mtime_ns: int,
        size: int,
        status: str,
        evidence_id: str,
        now_ms: int,
    ) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO proof_event_receipts(
                    event_name, event_mtime_ns, event_size, status, evidence_id, observed_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_name) DO UPDATE SET
                    event_mtime_ns=excluded.event_mtime_ns,
                    event_size=excluded.event_size,
                    status=excluded.status,
                    evidence_id=excluded.evidence_id,
                    observed_at_ms=excluded.observed_at_ms
                """,
                (event_name, mtime_ns, size, status, evidence_id, now_ms),
            )
            connection.commit()

    def ingest_proof_events(self, codex_home: Path, overview: dict[str, Any], *, now_ms: int) -> int:
        """Import immutable, content-addressed receipts without reading task messages."""
        expected_swarm_root = codex_home.resolve() / "swarm"
        expected_event_root = codex_home.resolve() / PROOF_EVENT_ROOT
        expected_media_root = codex_home.resolve() / PROOF_MEDIA_ROOT
        swarm_root = expected_swarm_root.resolve()
        event_root = expected_event_root.resolve()
        media_root = expected_media_root.resolve()
        if swarm_root != expected_swarm_root or event_root != expected_event_root or media_root != expected_media_root:
            return 0
        if not event_root.is_dir() or not media_root.is_dir():
            return 0
        nodes = {
            str(node.get("id")): node
            for node in overview.get("nodes", [])
            if not node.get("virtual") and node.get("id") and node.get("project_id")
        }
        receipts = self._proof_event_receipts()
        imported = 0
        for event_path in sorted(event_root.glob("*.json")):
            event_stat: os.stat_result | None = None
            evidence_id = ""
            try:
                resolved_event = event_path.resolve(strict=True)
                event_stat = resolved_event.stat()
                if not resolved_event.is_file() or not resolved_event.is_relative_to(event_root) or event_stat.st_size > 16 * 1024:
                    continue
                receipt = receipts.get(resolved_event.name)
                if receipt == (event_stat.st_mtime_ns, event_stat.st_size, "IMPORTED") or receipt == (event_stat.st_mtime_ns, event_stat.st_size, "REJECTED"):
                    continue
                event = json.loads(resolved_event.read_text(encoding="utf-8"))
                if not isinstance(event, dict) or event.get("schema_version") != 1 or event.get("source") != "CtrlEvidence":
                    raise ConsoleError("proof event envelope is invalid")
                evidence_id = _safe_metadata_text(event.get("evidence_id"), "evidence_id", maximum=256)
                task_id = _safe_metadata_text(event.get("task_id"), "task_id", maximum=256)
                node = nodes.get(task_id)
                project_id = str(node["project_id"]) if node is not None else observed_task_project_id(codex_home, task_id)
                if project_id is None:
                    continue
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
                self.record_proof_media(payload, now_ms=now_ms, allowed_root=media_root)
                self._record_proof_event_receipt(
                    resolved_event.name,
                    mtime_ns=event_stat.st_mtime_ns,
                    size=event_stat.st_size,
                    status="IMPORTED",
                    evidence_id=evidence_id,
                    now_ms=now_ms,
                )
                imported += 1
            except (ConsoleError, OSError, ValueError, TypeError, json.JSONDecodeError):
                if event_stat is not None:
                    self._record_proof_event_receipt(
                        event_path.name,
                        mtime_ns=event_stat.st_mtime_ns,
                        size=event_stat.st_size,
                        status="REJECTED",
                        evidence_id=evidence_id,
                        now_ms=now_ms,
                    )
                continue
        return imported

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
        return {
            "ctrl_id": ctrl_id,
            "revision": 0 if row is None else int(row["revision"]),
            "override": {} if row is None else json.loads(row["fields_json"]),
        }

    def update_ctrl_override(self, ctrl_id: str, fields: dict[str, Any], *, expected_revision: int, now_ms: int) -> dict[str, Any]:
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise ConsoleError("expected_revision must be a nonnegative integer")
        if not fields or set(fields) - set(CTRL_OVERRIDE_FIELDS):
            raise ConsoleError("override fields must use the canonical model, reasoning, and service_tier keys")
        for key, value in fields.items():
            if not isinstance(value, CTRL_OVERRIDE_FIELDS[key]) or "\n" in value or len(value) > 128:
                raise ConsoleError(f"override {key} is invalid")
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,)).fetchone()
            current_revision = 0 if row is None else int(row["revision"])
            if current_revision != expected_revision:
                raise ConsoleConflict(f"CTRL override revision conflict; expected {expected_revision}, current {current_revision}")
            current = {} if row is None else json.loads(row["fields_json"])
            current.update(fields)
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
            row = connection.execute("SELECT revision FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,)).fetchone()
            current_revision = 0 if row is None else int(row["revision"])
            if expected_revision != current_revision:
                raise ConsoleConflict(f"CTRL override revision conflict; expected {expected_revision}, current {current_revision}")
            connection.execute("DELETE FROM ctrl_overrides WHERE ctrl_id = ?", (ctrl_id,))
            connection.commit()
        return {"ctrl_id": ctrl_id, "revision": 0, "override": {}, "reset": True}

    def clear_history(self) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            before = self.storage_stats()
            deleted = {}
            for table in (
                "token_samples", "token_cursors", "eta_forecasts", "proof_media", "proof_event_receipts", "store_metadata",
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
                    "token_samples", "eta_forecasts", "proof_media", "proof_event_receipts", "ctrl_overrides",
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
            row = connection.execute(
                "SELECT cwd, git_origin_url FROM threads WHERE id=? AND archived=0",
                (task_id,),
            ).fetchone()
    except (sqlite3.Error, OSError, ConsoleError):
        return None
    return None if row is None else _project_identity(row)[0]


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


def _epoch_ms(milliseconds: Any, seconds: Any) -> int:
    if milliseconds:
        return int(milliseconds)
    if not seconds:
        return 0
    value = int(seconds)
    return value if value > 10**12 else value * 1000


def _codex_jsonl_token_count(codex_home: Path, thread_id: str) -> int | None:
    """Read only local token-count events for one thread; never retain payloads."""
    sessions = codex_home / "sessions"
    if not sessions.is_dir():
        return None
    highest: int | None = None
    try:
        candidates = sorted(
            path for path in sessions.rglob("*.jsonl")
            if path.is_file() and thread_id in path.name
        )
    except OSError:
        return None
    for path in candidates:
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
                    highest = total if highest is None else max(highest, total)
        except (OSError, UnicodeError):
            continue
    return highest


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
    artifact = " ".join(path_tokens) or "Assigned task"
    artifact = re.sub(r"(?i)\bgate\s*(\d+)\b", r"Gate \1", artifact).strip().title()[:48]
    if controller:
        _, artifact = _project_identity(row)
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
        thread_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(threads)").fetchall()
        }
        agent_path_projection = "agent_path" if "agent_path" in thread_columns else "'' AS agent_path"
        goal_placeholders = ",".join("?" for _ in active_goal_ids)
        goal_clause = f" OR id IN ({goal_placeholders})" if active_goal_ids else ""
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
                row["title"], labels, config["role_icons"], config["roles"]
            )
        )
    }
    parent_by_child = {edge["child_thread_id"]: edge["parent_thread_id"] for edge in edge_rows}
    edge_status = {edge["child_thread_id"]: edge["status"] for edge in edge_rows}
    host_projects: dict[str, dict[str, Any]] = {}
    for row in all_rows.values():
        project_key, project_name = _project_identity(row)
        project = host_projects.setdefault(
            project_key,
            {
                "id": project_key,
                "name": project_name,
                "goal_label": project_name,
                "label_source": "repository_origin" if str(row["git_origin_url"] or "").strip() else "working_directory",
                "observed_threads": 0,
                "active_threads": 0,
                "updated_at": 0,
            },
        )
        project["observed_threads"] += 1
        project["active_threads"] += _status(row, edge_status.get(row["id"]), heartbeat, now_ms) == "active"
        project["updated_at"] = max(project["updated_at"], _epoch_ms(row["updated_at_ms"], row["updated_at"]))
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
            observed_role = _generic_agent_role(
                all_rows[thread_id], config["role_icons"], controller=True
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
        project_key, project_name = _project_identity(row)
        created_ms = _epoch_ms(row["created_at_ms"], row["created_at"])
        updated_ms = _epoch_ms(row["updated_at_ms"], row["updated_at"])
        project = projects.setdefault(
            project_key,
            {
                "id": project_key,
                "name": project_name,
                "goal_label": project_name,
                "label_source": "repository_origin" if str(row["git_origin_url"] or "").strip() else "working_directory",
                "nodes": 0,
                "tokens": 0,
                "active": 0,
            },
        )
        if role["role"] == "ctrl" and project["label_source"] == "working_directory":
            project["goal_label"] = role["artifact"] or project["name"]
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
        project = projects[node["project_id"]]
        project["nodes"] -= 1
        project["tokens"] -= node["tokens"]
        project["active"] -= node["status"] == "active"
        if project["nodes"] == 0:
            projects.pop(node["project_id"])

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
        "projects": sorted(projects.values(), key=lambda item: (-item["active_threads"], -item["updated_at"], item["name"])),
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
            "Only unarchived host tasks updated within the current observation window are shown.",
            "Recent active durable goals are read by thread ID only to identify CTRL scopes; objective text is never read or surfaced.",
            "Project navigation includes active observed repositories even when no authoritative CTRL scope is available; those projects remain project-level only.",
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
    def __init__(self, codex_home: Path, config_path: Path, state_path: Path | None = None):
        self.codex_home = codex_home.resolve()
        self.config_path = config_path.resolve()
        self.store = ConsoleStore(state_path or console_state_path(self.codex_home, self.config_path))
        self.diagnostics_collector = DiagnosticsCollector(self.codex_home, self.store.path)
        self.token = secrets.token_urlsafe(24)
        self.write_lock = threading.Lock()
        self.overview_lock = threading.RLock()
        self.overview_refresh_lock = threading.Lock()
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
        self._observer_stop = threading.Event()
        self._observer_thread: threading.Thread | None = None

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

    @staticmethod
    def _progress_for_nodes(nodes: list[dict[str, Any]], scope: dict[str, Any]) -> dict[str, Any]:
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
            task_items.append({
                "id": node["id"],
                "project_id": node.get("project_id"),
                "state": node.get("status", "unknown"),
                "blocked": blocked,
                "blocker": eta.get("reason") if blocked else None,
                "latest_proof_receipt": latest_proof.get("evidence_id"),
            })
        completed = sum(item["state"] in {"done", "archived", "complete"} for item in task_items)
        blocked = sum(bool(item["blocked"]) for item in task_items)
        return {
            "scope": scope,
            "status": "no_tasks" if not task_items else "observed",
            "counts": {"tasks": len(task_items), "completed": completed, "blocked": blocked},
            "tasks": task_items,
            "claim_limit": "Observed non-subagent host task states only; no completion percentage is inferred.",
        }

    @classmethod
    def _progress_payload(cls, view: dict[str, Any]) -> dict[str, Any]:
        nodes = list(view.get("nodes", []))
        project_summaries = {
            str(project["id"]): cls._progress_for_nodes(
                [node for node in nodes if node.get("project_id") == project["id"]],
                {"type": "project", "project_id": project["id"]},
            )
            for project in view.get("projects", [])
        }
        controller_summaries = {
            str(controller["id"]): cls._progress_for_nodes(
                [node for node in nodes if controller["id"] in node.get("controller_ids", [])],
                {"type": "ctrl", "ctrl_id": controller["id"], "project_id": controller.get("project_id")},
            )
            for controller in view.get("controllers", [])
        }
        return {
            "all_projects": cls._progress_for_nodes(nodes, {"type": "all-projects"}),
            "projects": project_summaries,
            "controllers": controller_summaries,
            "claim_limit": "Progress is a read-only projection of observed host tasks; it is not runtime authority.",
        }

    def _project_view(self, overview: dict[str, Any], project_id: str | None) -> dict[str, Any]:
        if not project_id or project_id.casefold() in {"all", "all-projects"}:
            return overview
        view = copy.deepcopy(overview)
        nodes = [node for node in view["nodes"] if node.get("project_id") == project_id]
        node_ids = {node["id"] for node in nodes}
        view["nodes"] = nodes
        view["links"] = [
            link for link in view["links"]
            if link["source"] in node_ids and link["target"] in node_ids
        ]
        view["roots"] = [node_id for node_id in view["roots"] if node_id in node_ids]
        view["controllers"] = [
            controller for controller in view["controllers"]
            if controller.get("project_id") == project_id
        ]
        view["projects"] = [
            project for project in view["projects"] if project.get("id") == project_id
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
        history = self.store.token_history(project_id=project_id)
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

    def usage_history(
        self,
        *,
        project_id: str | None = None,
        ctrl_id: str | None = None,
        hours: int = 24,
    ) -> dict[str, Any]:
        if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 24 * 30:
            raise ConsoleError("hours must be an integer from 1 to 720")
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
        status = "no_data" if not history else (
            "partial" if expected_threads is not None and observed_threads < expected_threads else "ok"
        )
        return {
            "ok": True,
            "status": status,
            "scope": scope,
            "hours": hours,
            "items": history,
            "total_tokens": total_tokens,
            "elapsed_ms": elapsed_ms,
            "tokens_per_minute": round(total_tokens / (elapsed_ms / 60_000), 2) if elapsed_ms else total_tokens,
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
            "claim_limit": "Aggregated token deltas and time only; prompts, responses, tools, credentials, and billing are excluded.",
        }

    def progress_summary(self, *, project_id: str | None = None, ctrl_id: str | None = None) -> dict[str, Any]:
        _, nodes, _, scope = self._observed_scope(project_id=project_id, ctrl_id=ctrl_id)
        return {"ok": True, **self._progress_for_nodes(nodes, scope)}

    @staticmethod
    def _navigation_payload(view: dict[str, Any]) -> dict[str, Any]:
        controllers = [
            {
                "id": controller["id"],
                "project_id": controller.get("project_id", ""),
                "title": controller.get("title", "CTRL"),
                "status": controller.get("status", "unknown"),
                "updated_at": controller.get("updated_at"),
            }
            for controller in view.get("controllers", [])
        ]
        active_controllers = [controller for controller in controllers if controller["status"] == "active"]
        projects = []
        for project in view.get("projects", []):
            project_id = str(project.get("id", ""))
            project_controllers = [controller for controller in controllers if controller["project_id"] == project_id]
            active_ids = [controller["id"] for controller in project_controllers if controller["status"] == "active"]
            projects.append({
                "id": project_id,
                "name": project.get("name", project_id),
                "goal_label": project.get("goal_label", project.get("name", project_id)),
                "label_source": project.get("label_source", "unknown"),
                "active_ctrl_id": active_ids[0] if active_ids else None,
                "ctrl_ids": [controller["id"] for controller in project_controllers],
                "task_count": sum(
                    1 for node in view.get("nodes", [])
                    if node.get("project_id") == project_id and not node.get("virtual")
                ),
            })
        return {
            "active_ctrl_id": active_controllers[0]["id"] if active_controllers else None,
            "active_ctrl_ids": [controller["id"] for controller in active_controllers],
            "controllers": controllers,
            "projects": projects,
            "claim_limit": "Observed host CTRLs only; this is navigation, not runtime authority.",
        }

    def _decorate_overview(self, base: dict[str, Any]) -> dict[str, Any]:
        view = copy.deepcopy(base)
        forecasts = self.store.latest_forecasts()
        for node in view["nodes"]:
            node["eta"] = forecasts.get(node["id"])
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
        return view

    def overview(self, project_id: str | None = None) -> dict[str, Any]:
        with self.overview_lock:
            if (
                self._view is None
                or self._view_fingerprint != self._overview_revision
                or self._view_store_generation != self._store_generation
            ):
                self._view = self._decorate_overview(self._host_overview())
                self._view_fingerprint = self._overview_revision
                self._view_store_generation = self._store_generation
            return self._project_view(self._view, project_id)

    def observe_once(self, trigger: str = "heartbeat") -> None:
        overview = self._host_overview(refresh=trigger in {"startup", "state_change"})
        now_ms = int(time.time() * 1000)
        heartbeat_minutes = max(1, int(overview.get("heartbeat_minutes") or 30))
        self.store.observe_overview(
            overview,
            now_ms=now_ms,
            trigger=trigger,
            heartbeat_minutes=heartbeat_minutes,
            codex_home=self.codex_home,
        )
        with self.proof_lock:
            self.store.ingest_proof_events(self.codex_home, overview, now_ms=now_ms)
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

    def proof_feed(self, *, project_id: str | None = None, task_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.proof_feed(project_id=project_id, task_id=task_id)

    def proof_media_item(self, evidence_id: str, digest: str) -> dict[str, Any]:
        return self.store.proof_media_item(
            evidence_id,
            digest,
            allowed_root=self.codex_home / PROOF_MEDIA_ROOT,
        )

    def proof_sequence(self) -> int:
        return self.store.proof_sequence()

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
                "service_tier": effective["execution"]["service_tier"],
            },
            "override": override,
            "effective": {
                "model": assignment["model"],
                "reasoning": assignment["reasoning"],
                "service_tier": override.get("service_tier", effective["execution"]["service_tier"]),
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
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

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
        if not self._host_allowed():
            self._error(HTTPStatus.FORBIDDEN, "SWARM Console accepts requests from this device only")
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
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
                    self.server.app.overview(query.get("project_id")),
                )
                return
            if path == "/api/usage-history":
                try:
                    hours = int(query.get("hours", "24"))
                except ValueError as exc:
                    raise ConsoleError("hours must be an integer from 1 to 720") from exc
                self._json(
                    HTTPStatus.OK,
                    self.server.app.usage_history(
                        project_id=query.get("project_id"),
                        ctrl_id=query.get("ctrl_id"),
                        hours=hours,
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
            if path == "/api/proof-feed":
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "sequence": self.server.app.proof_sequence(), "items": self.server.app.proof_feed(
                        project_id=query.get("project_id"),
                        task_id=query.get("task_id"),
                    )},
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
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802
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
