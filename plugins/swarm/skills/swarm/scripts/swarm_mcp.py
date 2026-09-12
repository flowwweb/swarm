#!/usr/bin/env python3
"""Small read-only SWARM MCP adapter for a local coding bridge.

The generic repository tools belong to the selected bridge (Codexify). This
process only exposes projections that generic file and shell tools cannot name
cleanly. It speaks newline-delimited JSON-RPC so it can be configured as a
Codexify stdio upstream without another model or request broker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve()
SWARM_SKILL_ROOT = SCRIPT_ROOT.parents[1]
REPO_ROOT = SCRIPT_ROOT.parents[3]
DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
DEFAULT_CONFIG = Path(os.environ.get("SWARM_CONFIG_PATH", Path.home() / ".agents" / "swarm" / "config.toml"))
DEFAULT_TELEMETRY = Path(os.environ.get("SWARM_MCP_TELEMETRY_PATH", Path.home() / ".agents" / "swarm" / "mcp-telemetry.jsonl"))


TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "swarm_status",
        "title": "Read SWARM status",
        "description": "Read the authoritative local SWARM overview: active projects, hierarchy nodes, progress, and current data coverage. No model calls or task mutations; console initialization may maintain local state and calls append metadata telemetry.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "additionalProperties": False},
        "annotations": {"title": "Read SWARM status", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "swarm_projects",
        "title": "List SWARM projects",
        "description": "List the projects currently visible to the local SWARM console, including their saved identity and activity state. No model calls or task mutations; console initialization may maintain local state and calls append metadata telemetry.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"title": "List SWARM projects", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "swarm_usage",
        "title": "Read SWARM usage",
        "description": "Read locally observed SWARM token history and burn-rate coverage for a bounded time window. Values are local observations, not provider billing or hidden ChatGPT usage. Console initialization may maintain local state and calls append metadata telemetry.",
        "inputSchema": {"type": "object", "properties": {"hours": {"type": "integer", "enum": [1, 12, 24, 168, 720]}}, "additionalProperties": False},
        "annotations": {"title": "Read SWARM usage", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
)


class MCPError(Exception):
    pass


class SwarmProjection:
    def __init__(self) -> None:
        self.codex_home = DEFAULT_CODEX_HOME.expanduser().resolve()
        self.config_path = DEFAULT_CONFIG.expanduser().resolve()
        self._app: Any | None = None

    def _load_app(self) -> Any:
        if self._app is not None:
            return self._app
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from console.server import App  # imported only when a SWARM projection is called

        self._app = App(self.codex_home, self.config_path)
        return self._app

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        spec = next((tool for tool in TOOLS if tool["name"] == name), None)
        if spec is None:
            raise MCPError("unknown tool")
        _validate_arguments(spec, arguments)
        app = self._load_app()
        if name == "swarm_status":
            project_id = arguments.get("project_id")
            if project_id is not None and (not isinstance(project_id, str) or not project_id.strip()):
                raise MCPError("project_id must be non-empty text")
            return _compact_overview(app.overview(project_id.strip() if project_id else None))
        if name == "swarm_projects":
            return _compact_roster(app.project_roster())
        if name == "swarm_usage":
            hours = arguments.get("hours", 24)
            if type(hours) is not int or hours not in {1, 12, 24, 168, 720}:
                raise MCPError("hours must be one of 1, 12, 24, 168, or 720")
            return _compact_usage(app.usage_history(hours=hours))
        raise MCPError(f"unknown tool: {name}")


def _validate_arguments(spec: dict[str, Any], arguments: Any) -> None:
    schema = spec["inputSchema"]
    if not isinstance(arguments, dict) or arguments.keys() - schema["properties"].keys():
        raise MCPError("arguments must be an object containing only declared fields")
    if any(key not in arguments for key in schema.get("required", [])):
        raise MCPError("required argument missing")
    for key, value in arguments.items():
        field = schema["properties"][key]
        if (field["type"] == "string" and (not isinstance(value, str) or key != "content" and not value.strip())
                or field["type"] == "integer" and type(value) is not int
                or "enum" in field and value not in field["enum"]):
            raise MCPError("argument has invalid type or value")


def _pick(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value[key] for key in keys if key in value}


def _compact_overview(view: dict[str, Any]) -> dict[str, Any]:
    nodes = [_pick(node, ("id", "project_id", "parent_id", "title", "role", "role_label", "status", "model", "reasoning", "tokens", "eta", "updated_at", "node_kind", "is_subagent", "virtual")) for node in view.get("nodes", [])[:256] if isinstance(node, dict)]
    projects = [_pick(project, ("id", "name", "goal_label", "active", "active_threads", "task_count", "nodes", "tokens", "updated_at")) for project in view.get("projects", [])[:128] if isinstance(project, dict)]
    links = [_pick(link, ("source", "target", "relationship", "status")) for link in view.get("links", [])[:512] if isinstance(link, dict)]
    metrics = view.get("overview_metrics", {}) if isinstance(view.get("overview_metrics"), dict) else {}
    usage = metrics.get("usage", {}) if isinstance(metrics.get("usage"), dict) else {}
    compact_metrics = dict(metrics)
    compact_metrics["usage"] = dict(usage)
    compact_metrics["usage"]["burn_rate_series"] = usage.get("burn_rate_series", [])[-120:]
    analytics = view.get("analytics", {}) if isinstance(view.get("analytics"), dict) else {}
    compact_analytics = _pick(analytics, ("status", "tasks", "independent_count", "roles", "models"))
    burn = analytics.get("burn_rate", {}) if isinstance(analytics.get("burn_rate"), dict) else {}
    compact_analytics["burn_rate"] = {key: burn[key] for key in ("tokens_per_minute", "source", "token_field", "label") if key in burn}
    progress = view.get("progress", {}) if isinstance(view.get("progress"), dict) else {}
    compact_progress = dict(progress)
    for scope in ("all_projects", "projects"):
        if isinstance(progress.get(scope), dict):
            scope_value = progress[scope]
            if scope == "projects":
                compact_progress[scope] = {
                    str(project_id): _compact_progress_scope(project_value)
                    for project_id, project_value in list(scope_value.items())[:128]
                    if isinstance(project_value, dict)
                }
                for project_value in compact_progress[scope].values():
                    project_value.pop("tasks", None)
                    project_value.pop("truncated", None)
            else:
                compact_progress[scope] = _compact_progress_scope(scope_value)
    return {
        "schema_version": 1,
        "generated_at": view.get("generated_at"),
        "source": view.get("source"),
        "projects": projects,
        "nodes": nodes,
        "links": links,
        "overview_metrics": compact_metrics,
        "analytics": compact_analytics,
        "progress": compact_progress,
        "claim_limits": view.get("claim_limits", {}),
        "truncated": len(view.get("nodes", [])) > len(nodes) or len(view.get("projects", [])) > len(projects) or len(view.get("links", [])) > len(links),
    }


def _compact_progress_scope(scope: dict[str, Any]) -> dict[str, Any]:
    compact = {key: scope[key] for key in ("scope", "status", "counts", "progress", "progress_display", "current_milestone", "measurement_status", "unmeasured_reason") if key in scope}
    milestone = compact.get("current_milestone")
    if isinstance(milestone, dict):
        compact["current_milestone"] = {key: milestone[key] for key in ("state", "reason", "name") if key in milestone}
    tasks = scope.get("tasks", scope.get("task_rows", []))
    if isinstance(tasks, list):
        compact["tasks"] = [_pick(task, ("id", "project_id", "state", "blocked", "blocker", "progress", "progress_display", "latest_proof_receipt")) for task in tasks[:128] if isinstance(task, dict)]
        compact["truncated"] = len(tasks) > 128
    return compact


def _compact_usage(view: dict[str, Any]) -> dict[str, Any]:
    compact = dict(view)
    compact.pop("verified_yield", None)
    if isinstance(view.get("task_history"), dict):
        compact["task_history"] = _pick(view["task_history"], ("status", "total_tokens", "coverage", "model_status", "claim_limit"))
    for key in ("items", "task_usage", "rate_history"):
        if isinstance(view.get(key), list):
            compact[key] = view[key][-256:]
    compact["omitted_detail"] = ["verified_yield", "task_history.items"]
    compact["truncated"] = any(isinstance(view.get(key), list) and len(view[key]) > 256 for key in ("items", "task_usage", "rate_history"))
    return compact


def _compact_roster(roster: dict[str, Any]) -> dict[str, Any]:
    current = roster.get("current_work", {})
    current = current if isinstance(current, dict) else {}
    return {
        "ok": roster.get("ok"),
        "state": roster.get("state"),
        "available": roster.get("available"),
        "schema_version": roster.get("schema_version"),
        "cursor": roster.get("cursor"),
        "projects": [_pick(project, ("id", "name", "goal_label", "active_ctrl_id", "active_now_count", "recently_active_count", "activity_status", "status", "task_count", "nodes", "tokens", "updated_at")) for project in roster.get("projects", [])[:128] if isinstance(project, dict)],
        "current_work": {
            **_pick(current, ("state", "available", "source", "claim_limit")),
            "project_ids": current.get("project_ids", [])[:128],
            "projects": [_pick(item, ("id", "name", "status", "activity_status")) for item in current.get("projects", [])[:128]],
            "controllers": [_pick(item, ("id", "project_id", "title", "status", "activity_status", "role", "controller_classification")) for item in current.get("controllers", [])[:256]],
            "truncated": len(current.get("project_ids", [])) > 128 or len(current.get("projects", [])) > 128 or len(current.get("controllers", [])) > 256,
        },
        "truncated": len(roster.get("projects", [])) > 128,
        "claim_limit": roster.get("claim_limit"),
    }


def _telemetry(path: Path, *, tool: str, started: float, ok: bool, result_bytes: int, error: str = "") -> None:
    """Append bounded metadata only; prompts, responses, credentials stay out."""
    record = {
        "timestamp": int(time.time() * 1000),
        "session_hash": hashlib.sha256(os.environ.get("SWARM_MCP_SESSION_HASH", "unknown").encode()).hexdigest()[:16],
        "tool": tool if tool in {item["name"] for item in TOOLS} | {"probe_read_file", "probe_write_file", "probe_delete_file"} else "unknown",
        "category": "read",
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "success": ok,
        "result_bytes": result_bytes,
    }
    if error:
        record["error"] = "invalid_arguments" if error == "invalid_arguments" else "projection_failed"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _probe(root: Path, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Harmless capability probe used by the deterministic local test harness."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    name = arguments.get("name", "probe.txt")
    if not isinstance(name, str) or not name or Path(name).name != name or any(char in name for char in ":/\\") or name in {".", ".."}:
        raise MCPError("probe name must be one filename in the scratch root")
    target = (root / name).resolve()
    if target.parent != root:
        raise MCPError("probe path escaped scratch root")
    if method == "probe_read_file":
        if target.exists() and target.stat().st_size > 4096:
            raise MCPError("probe file exceeds 4096 bytes")
        return {"name": name, "content": target.read_text(encoding="utf-8") if target.exists() else ""}
    if method == "probe_write_file":
        content = arguments.get("content", "")
        if not isinstance(content, str) or len(content.encode("utf-8")) > 4096:
            raise MCPError("probe content must be text up to 4096 bytes")
        target.write_text(content, encoding="utf-8", newline="")
        return {"name": name, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(), "bytes": len(content.encode("utf-8"))}
    if method == "probe_delete_file":
        target.unlink(missing_ok=True)
        return {"name": name, "deleted": not target.exists()}
    raise MCPError(f"unknown probe tool: {method}")


def serve(*, probe_root: Path | None = None, telemetry_path: Path = DEFAULT_TELEMETRY) -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    projection = SwarmProjection()
    probe_tools = (
        {"name": "probe_read_file", "description": "Read one scratch probe file.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "additionalProperties": False}},
        {"name": "probe_write_file", "description": "Write one scratch probe file.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "content": {"type": "string"}}, "required": ["content"], "additionalProperties": False}},
        {"name": "probe_delete_file", "description": "Delete one scratch probe file.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "additionalProperties": False}},
    ) if probe_root else ()
    tools = (*TOOLS, *probe_tools)
    for line in sys.stdin:
        if not line.strip():
            continue
        request_id = None
        try:
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                print(json.dumps(_error(None, -32700, "parse error")), flush=True)
                continue
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                print(json.dumps(_error(None, -32600, "invalid request")), flush=True)
                continue
            request_id = request.get("id")
            if request_id is not None and type(request_id) not in (str, int):
                print(json.dumps(_error(None, -32600, "invalid request id")), flush=True)
                continue
            if request_id is None:
                continue
            method = request["method"]
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise MCPError("params must be an object")
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "swarm-mcp", "version": "1.0.0"}}
            elif method == "tools/list":
                result = {"tools": list(tools)}
            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments", {})
                spec = next((tool for tool in tools if tool["name"] == name), None)
                if spec is None:
                    raise MCPError("unknown tool")
                started = time.perf_counter()
                try:
                    _validate_arguments(spec, arguments)
                    value = _probe(probe_root, name, arguments) if name.startswith("probe_") else projection.call(name, arguments)
                    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                    if len(encoded.encode("utf-8")) > 262144:
                        raise MCPError("projection exceeds 262144 bytes; narrow the requested scope")
                    _telemetry(telemetry_path, tool=name, started=started, ok=True, result_bytes=len(encoded.encode("utf-8")))
                    result = {"content": [{"type": "text", "text": encoded}], "structuredContent": value, "isError": False}
                except Exception as exc:
                    error = str(exc) if isinstance(exc, MCPError) else "local projection failed"
                    _telemetry(telemetry_path, tool=name, started=started, ok=False, result_bytes=0, error="invalid_arguments" if isinstance(exc, MCPError) else "projection_failed")
                    result = {"content": [{"type": "text", "text": error}], "isError": True}
            else:
                print(json.dumps(_error(request_id, -32601, "method not found")), flush=True)
                continue
            print(json.dumps(_response(request_id, result), ensure_ascii=False, separators=(",", ":")), flush=True)
        except MCPError as exc:
            print(json.dumps(_error(request_id, -32602, str(exc))), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdio", action="store_true", help="serve newline-delimited MCP JSON-RPC")
    parser.add_argument("--probe-root", type=Path, help="enable harmless scratch capability probe tools")
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    args = parser.parse_args()
    if not args.stdio:
        parser.error("--stdio is required")
    return serve(probe_root=args.probe_root, telemetry_path=args.telemetry)


if __name__ == "__main__":
    raise SystemExit(main())
