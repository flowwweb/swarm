#!/usr/bin/env python3
"""Small SWARM projection and acknowledged Settings MCP adapter.

The generic repository tools belong to the selected bridge (Codexify). This
process exposes projections and delegates Settings writes to the existing config
authority. It speaks newline-delimited JSON-RPC so it can be configured as a
Codexify stdio upstream without another model or request broker.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import socket
import stat
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
HQ_SDK_PATH = SWARM_SKILL_ROOT / "assets/ui/swarm-hq-mcp-app.js"
HQ_SDK_SHA256 = "13975ccee16da487ca1be1a3e420c0717ff5c669e287df13e949f9c67d38c8c3"
PROJECTS_ASSETS = {"skills/swarm/assets/ui/swarm-hq-projects.html": "90755ec9e46e46b8f3153820c77b3a4464fb24b63df0b49a4542c014a338632d", "skills/swarm/assets/ui/swarm-hq-host.css": "3cdb043e87cb1031732a5a15ba0d0b513ba2d2bcd431320a86ca84c323c01eb6", "skills/swarm/assets/swarm-wordmark.png": "306c1549fa5195e0211d9d062fccdfc1b1241de3eda82c97ed8cb42ecdbcf6d2"}


PROJECTS_SUPPORT_IMAGES = {
    "__FLOWWWEB_LOGO__": ("skills/swarm/assets/ui/brand/flowwweb-lockup-v2-light.svg", "image/svg+xml", "57253bfef4d4f26c399dbb1d5fb2f258d663b52d31dd1414ab7c9cfef808d7b3"),
    "__FLOWWWEB_LOGO_DARK__": ("skills/swarm/assets/ui/brand/flowwweb-lockup-v2-dark.svg", "image/svg+xml", "cbc1bb458ab73cf7ac89972e7f087ae93a9a65902b1a4926b05484eaa90e9a11"),
}
# Public delivery is separate from inline assets. These exact local bytes retain
# provenance; an img URL does not provide runtime integrity for future responses.
PROJECTS_COMPACT_BADGE = (
    "skills/swarm/assets/ui/brand/road-to-1m-square-transparent.png",
    "https://flowwweb.com/brand/road-to-1m-square-transparent.png",
    "d22259dd1524a1bcec13ce13ff117bf098a493d77d653231658583689aba2155",
    607876,
)
PROJECTS_PUBLIC_IMAGES = {
    "__ROADTO1M_COMPACT__": PROJECTS_COMPACT_BADGE,
    "__SUPPORT_PORTRAIT__": (
        "skills/swarm/assets/ui/brand/support-caricature-light.webp",
        "https://flowwweb.com/brand/swarm/support-caricature-light-20261024-18b223c6.webp",
        "18b223c6075695c4d0fd28d550466323343caafe717372044c82a553a820b94b",
        69636,
    ),
}


TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "swarm_project_ticket_execution", "title": "Ticket execution bindings",
        "description": "Read or explicitly bind an existing host-created block attempt to a reserved project ticket. Never dispatch or complete work.",
        "inputSchema": {"type": "object", "properties": {
            "operation": {"type": "string", "enum": ["read", "bind"]},
            "project_id": {"type": "string"}, "record_id": {"type": "string"},
            "reference_id": {"type": "string"}, "task_id": {"type": "string"},
            "block_id": {"type": "string"}, "manifest_digest": {"type": "string"},
            "attempt": {"type": "integer"}, "membership": {"type": "string", "enum": ["REQUIRED", "SUPPLEMENTAL"]},
            "expected_ledger_revision": {"type": "integer"}, "acknowledge": {"type": "boolean", "enum": [True]}},
            "required": ["operation", "project_id", "record_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        "_meta": {"ui": {"visibility": ["model", "app"]}},
    },
    {
        "name": "swarm_project_tickets", "title": "Project tickets",
        "description": "Read or explicitly create/edit project planning tickets, or explicitly migrate legacy string milestones into typed records. No host dispatch or completion authority.",
        "inputSchema": {"type": "object", "properties": {
            "operation": {"type": "string", "enum": ["read", "create", "update", "migrate_legacy"]},
            "project_id": {"type": "string"}, "expected_digest": {"type": "string"},
            "acknowledge": {"type": "boolean", "enum": [True]},
            "collection": {"type": "string", "enum": ["goals", "milestones", "tasks", "blocks"]},
            "record_id": {"type": "string"}, "changes": {"type": "object"}, "project_code": {"type": "string"}},
            "required": ["operation", "project_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
        "_meta": {"ui": {"visibility": ["model", "app"]}},
    },
    {
        "name": "swarm_library_read", "title": "Read Units or Roles",
        "description": "Read the existing inventory and project-scoped Flow preferences. No dispatch or execution authority.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["ROLE", "LAB", "FACTORY"]}},
            "required": ["project_id", "kind"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": "swarm_flow_save", "title": "Save a project Flow version",
        "description": "Append a validated Flow version to the existing project brief after explicit acknowledgement. Never run it.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"},
            "expected_digest": {"type": "string"}, "definition": {"type": "object"},
            "acknowledge": {"type": "boolean", "enum": [True]}},
            "required": ["project_id", "expected_digest", "definition", "acknowledge"], "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": "swarm_flow_assign", "title": "Save scoped Flow preferences",
        "description": "Append an acknowledged scoped Unit or Role preference version to the project brief. Repeat count is planning metadata, not an automatic loop.",
        "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"},
            "expected_digest": {"type": "string"}, "assignment": {"type": "object"},
            "acknowledge": {"type": "boolean", "enum": [True]}},
            "required": ["project_id", "expected_digest", "assignment", "acknowledge"], "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": "swarm_settings_read", "title": "Read SWARM Settings",
        "description": "Read the existing redacted scoped config projection and revision. No host model change is implied.",
        "inputSchema": {"type": "object", "properties": {"scope": {"type": "object"}}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": "swarm_settings_save", "title": "Save SWARM Settings",
        "description": "Submit an explicitly acknowledged scoped config edit through the existing revision/idempotency authority. Preserve the exact operation identity for uncertain retries.",
        "inputSchema": {"type": "object", "properties": {
            "scope": {"type": "object"}, "expected_revision": {"type": "string"},
            "acknowledge": {"type": "boolean", "enum": [True]}, "text": {"type": "string"},
            "operation_id": {"type": "string"}},
            "required": ["scope", "expected_revision", "acknowledge", "text", "operation_id"],
            "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        "_meta": {"ui": {"visibility": ["app"]}},
    },
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
        "description": "Read locally observed SWARM token history and burn-rate coverage for a bounded time window. Optional project_id reads one observed project through the existing console scope check. Values are local observations, not provider billing or hidden ChatGPT usage. Console initialization may maintain local state and calls append metadata telemetry.",
        "inputSchema": {"type": "object", "properties": {"hours": {"type": "integer", "enum": [1, 12, 24, 168, 720]}, "project_id": {"type": "string"}}, "additionalProperties": False},
        "annotations": {"title": "Read SWARM usage", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
)


class MCPError(Exception):
    def __init__(self, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.data = data


HQ_RESOURCE_URI = re.compile(r"ui://swarm/hq/([0-9a-f]{64})\.html")


def _projects_asset(name: str, digest: str, *, exact_size: int | None = None) -> bytes:
    path = REPO_ROOT / name
    info = path.lstat()
    bound = 524288 if exact_size is None else exact_size
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT or info.st_size > bound:
        raise MCPError("Projects asset must be a bounded regular file")
    with path.open("rb") as stream:
        payload = stream.read(bound + 1)
    if len(payload) > bound or (exact_size is not None and len(payload) != exact_size) or hashlib.sha256(payload).hexdigest() != digest:
        raise MCPError("Projects asset identity mismatch or size exceeded")
    return payload


class HQApp:
    """Serve one explicitly pinned exporter artifact, never load live host state."""

    def __init__(self, path: Path, expected_sha256: str, *, projects: bool = False) -> None:
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise MCPError("HQ export requires an exact SHA-256")
        self.path, self.expected_sha256 = path, expected_sha256
        self.projects = projects
        self.uri = f"ui://swarm/hq/{hashlib.sha256(self.render().encode('utf-8')).hexdigest()}.html"

    def read(self) -> dict[str, Any]:
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise MCPError("HQ export must be a regular file")
        with self.path.open("rb") as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != self.expected_sha256:
            raise MCPError("HQ export changed or exceeds its bound")
        value = json.loads(raw)
        if (not isinstance(value, dict) or value.get("status") != "READY_SOURCE_BOUND_SPACE_HTML_NOT_PUBLISHED"
                or value.get("approval_verified") is not False or value.get("destination") is not None
                or not isinstance(value.get("html"), str)
                or not isinstance(value.get("snapshot_digest"), str)
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", value["snapshot_digest"])):
            raise MCPError("HQ requires an unapproved read-only exporter artifact")
        html = value["html"].encode("utf-8")
        if (not html or len(html) > 262144 or value.get("size_bytes") != len(html)
                or value.get("html_sha256") != hashlib.sha256(html).hexdigest()):
            raise MCPError("HQ HTML identity or size mismatch")
        return value

    def tool(self) -> dict[str, Any]:
        return {"name": "swarm_hq_view", "title": "SWARM" if self.projects else "Open SWARM source snapshot",
                "description": ("Open the Projects shell and scoped Settings. Project observations are read-only; Settings saves require separate acknowledged revision-bound commands. No task authority or native placement is inferred." if self.projects else "Open the configured read-only compact HQ snapshot. No live status, task actions, approval or Space placement is inferred."),
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
                "_meta": {"ui": {"resourceUri": self.uri}, "openai/ui": {"entrypoints": [{"type": "global"}, {"type": "thread"}]}}}

    def render(self) -> str:
        value = self.read()
        info = HQ_SDK_PATH.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT or info.st_size > 524288:
            raise MCPError("HQ SDK must be a regular file")
        raw = HQ_SDK_PATH.read_bytes()
        if len(raw) > 524288 or hashlib.sha256(raw).hexdigest() != HQ_SDK_SHA256:
            raise MCPError("HQ SDK changed or exceeds its bound")
        sdk = raw.decode("utf-8")
        if re.search(r"</script", sdk, re.IGNORECASE):
            raise MCPError("HQ SDK cannot be embedded")
        script = '\n<script type="module" data-swarm-mcp-sdk="' + HQ_SDK_SHA256 + '">' + sdk + '</script>\n'
        html = value["html"]
        if self.projects:
            assets = {name: _projects_asset(name, digest) for name, digest in PROJECTS_ASSETS.items()}
            html = assets["skills/swarm/assets/ui/swarm-hq-projects.html"].decode("utf-8")
            html = html.replace("__CSS__", assets["skills/swarm/assets/ui/swarm-hq-host.css"].decode("utf-8"))
            html = html.replace("__WORDMARK__", "data:image/png;base64," + base64.b64encode(assets["skills/swarm/assets/swarm-wordmark.png"]).decode("ascii"))
            html = html.replace('<script type="module">__SCRIPT__</script>', '')
            for token, (name, mime_type, digest) in PROJECTS_SUPPORT_IMAGES.items():
                if token in html:
                    payload = _projects_asset(name, digest)
                    html = html.replace(token, "data:" + mime_type + ";base64," + base64.b64encode(payload).decode("ascii"))
            for token, (name, url, digest, size) in PROJECTS_PUBLIC_IMAGES.items():
                if token in html:
                    _projects_asset(name, digest, exact_size=size)
                    html = html.replace(token, url)
            if re.search(r"__[A-Z][A-Z0-9_]*__", html):
                raise MCPError("Projects resource contains an unadmitted placeholder")
        # The original export stays immutable; only this MCP response gains the SDK.
        document = html.replace('</body>', script + '</body>', 1) if '</body>' in html else html + script
        if len(document.encode("utf-8")) > (1179648 if self.projects else 1048576):
            raise MCPError("adapted HQ resource exceeds its bound")
        return document

    def resource(self) -> dict[str, Any]:
        document = self.render()
        domains = ["https://flowwweb.com"] if self.projects and any(
            image[1] in document for image in PROJECTS_PUBLIC_IMAGES.values()) else []
        return {"contents": [{"uri": self.uri, "mimeType": "text/html;profile=mcp-app", "text": document,
                              "_meta": {"ui": {"csp": {"connectDomains": [], "resourceDomains": domains}}}}]}

    def result(self) -> dict[str, Any]:
        value = self.read()
        return {"content": [{"type": "text", "text": "Projects and Settings; host observations and acknowledged saves use separate existing tools. Native placement is unverified." if self.projects else "Read-only source snapshot; not live status, approval or verified Space placement."}],
                "structuredContent": {"html_sha256": value["html_sha256"], "snapshot_digest": value["snapshot_digest"],
                                      "served_html_sha256": hashlib.sha256(self.render().encode("utf-8")).hexdigest(),
                                      "sdk_sha256": HQ_SDK_SHA256, "refresh": "EXPLICIT_HOST_READS_ACKNOWLEDGED_SETTINGS" if self.projects else "PINNED_SNAPSHOT_REEXPORT_REQUIRED",
                                      "approval_verified": False, "live": False}, "isError": False}


def _require_hq_read(params: dict[str, Any], hq_app: HQApp | None) -> HQApp:
    """Admit the exact served URI and optional protocol metadata without echoing input."""
    if (set(params) - {"uri", "_meta"} or not isinstance(params.get("uri"), str)
            or ("_meta" in params and not isinstance(params["_meta"], dict))):
        raise MCPError("invalid HQ resource request")
    if hq_app is not None and params["uri"] == hq_app.uri:
        return hq_app
    received = HQ_RESOURCE_URI.fullmatch(params["uri"])
    expected = None if hq_app is None else HQ_RESOURCE_URI.fullmatch(hq_app.uri)
    if received and expected:
        raise MCPError("stale HQ resource identity",
                       {"expected_sha256": expected.group(1), "received_sha256": received.group(1)})
    raise MCPError("unknown HQ resource")


class SwarmProjection:
    def __init__(self, telemetry_path: Path = DEFAULT_TELEMETRY) -> None:
        self.codex_home = DEFAULT_CODEX_HOME.expanduser().resolve()
        self.config_path = DEFAULT_CONFIG.expanduser().resolve()
        self.telemetry_path = telemetry_path
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
        if name == "swarm_project_ticket_execution":
            from console.server import ConsoleError, ConsoleConflict
            try:
                with app.write_lock:
                    return app.project_ticket_execution_command(arguments)
            except ConsoleConflict:
                return {"ok": False, "state": "CONFLICT", "project_id": arguments["project_id"],
                        "message": "The binding changed. Read its retained identity before retrying."}
            except ConsoleError:
                return {"ok": False, "state": "REJECTED", "project_id": arguments["project_id"],
                        "message": "No valid ticket binding. Check the retained task, block and project."}

        if name == "swarm_project_tickets":
            from console.server import ConsoleError, ConsoleConflict
            try:
                return app.project_ticket_command(arguments)
            except ConsoleConflict:
                return {"ok": False, "state": "CONFLICT", "code": "SOURCE_CONFLICT", "project_id": arguments["project_id"],
                        "message": "The project changed. Keep your draft and reload before saving."}
            except ConsoleError as exc:
                code = str(exc).split(":", 1)[0]
                messages = {"PROJECT_CODE_REQUIRED": "Choose a project code of 1–4 letters.",
                            "PROJECT_CODE_INVALID": "Use 1–4 letters for the project code.",
                            "SOURCE_WRITE_UNCERTAIN": "Save is unconfirmed. Keep this draft and reload to reconcile before retrying the same request.",
                            "RECORD_ID_RESERVED": "This draft identity is reserved for an earlier request. Keep its content and start a new draft.",
                            "PROJECT_CODE_CONFLICT": "That project code is already assigned. Keep the existing code or choose another."}
                return {"ok": False, "state": "REJECTED", "code": code if code in messages else "TICKET_REJECTED",
                        "project_id": arguments["project_id"], "message": messages.get(code, "The ticket could not be saved. Keep your draft and check its project and parent.")}
        if name in {"swarm_library_read", "swarm_flow_save", "swarm_flow_assign"}:
            from console.server import ConsoleError, ConsoleConflict
            try:
                if name != "swarm_library_read":
                    return app.project_flow_command({"operation": "save" if name == "swarm_flow_save" else "assign", **arguments})
                result = app.project_flow_command({"operation": "read", "project_id": arguments["project_id"]})
                kind = arguments["kind"]
                if kind == "ROLE":
                    roles = app.role_manifest_projection()
                    inventory = {"roles": [_pick(role, ("id", "name", "active_version", "purpose", "owns", "instructions",
                        "boundaries", "default_skills", "specializations", "accent", "lucide_icon", "avatar"))
                        for role in roles["roles"] if role["id"].casefold() != "critic"], "scope": "global-definitions"}
                else:
                    inventory = app.unit_catalog_projection(kind)
                    inventory["instances"] = [unit for unit in inventory["instances"] if unit["project_id"] == arguments["project_id"]]
                if app.project_flow_command({"operation": "read", "project_id": arguments["project_id"]})["source_digest"] != result["source_digest"]:
                    raise ConsoleConflict("project source changed while reading")
                return {**result, "kind": kind, "inventory": inventory}
            except ConsoleConflict:
                return {"ok": False, "state": "CONFLICT", "project_id": arguments["project_id"],
                        "message": "Source changed. Reload and reconcile before saving."}
            except ConsoleError:
                return {"ok": False, "state": "REJECTED", "project_id": arguments["project_id"],
                        "message": "Invalid or unavailable scoped source. Keep the draft and reload."}
        if name == "swarm_settings_read":
            return app.config_projection(arguments.get("scope"))
        if name == "swarm_settings_save":
            return app.update_config_source(arguments)
        if name == "swarm_status":
            project_id = arguments.get("project_id")
            if project_id is not None and (not isinstance(project_id, str) or not project_id.strip()):
                raise MCPError("project_id must be non-empty text")
            return {**_compact_overview(app.overview(project_id.strip() if project_id else None)),
                    "device": _device_status(self.telemetry_path)}
        if name == "swarm_projects":
            return _compact_roster(app.project_roster())
        if name == "swarm_usage":
            hours = arguments.get("hours", 24)
            if type(hours) is not int or hours not in {1, 12, 24, 168, 720}:
                raise MCPError("hours must be one of 1, 12, 24, 168, or 720")
            if "project_id" not in arguments:
                return _compact_usage(app.usage_history(hours=hours, include_verified_yield=False))
            project_id = arguments["project_id"]
            if not isinstance(project_id, str) or not project_id.strip():
                raise MCPError("project_id must be non-empty text")
            project_id = project_id.strip()
            usage = app.usage_history(project_id=project_id, hours=hours, include_verified_yield=False)
            scope = usage.get("scope") if isinstance(usage, dict) else None
            if not isinstance(scope, dict) or scope.get("type") != "project" or scope.get("project_id") != project_id:
                raise MCPError("usage scope mismatch")
            return _compact_usage(usage)
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
                or field["type"] == "boolean" and type(value) is not bool
                or field["type"] == "object" and not isinstance(value, dict)
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
    for scope in ("all_projects", "projects", "controllers"):
        if isinstance(progress.get(scope), dict):
            scope_value = progress[scope]
            if scope in {"projects", "controllers"}:
                compact_progress[scope] = {
                    str(project_id): _compact_progress_scope(project_value, identity=scope == "projects" and project_id == metrics.get("accepted_scope_id"))
                    for project_id, project_value in list(scope_value.items())[:128]
                    if isinstance(project_value, dict)
                }
                for project_id, project_value in compact_progress[scope].items():
                    if scope == "projects" and project_id != metrics.get("accepted_scope_id"):
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


def _compact_progress_scope(scope: dict[str, Any], *, identity: bool = False) -> dict[str, Any]:
    compact = {key: scope[key] for key in ("scope", "status", "counts", "progress", "progress_display", "current_milestone", "measurement_status", "unmeasured_reason") if key in scope}
    milestone = compact.get("current_milestone")
    if isinstance(milestone, dict):
        compact["current_milestone"] = {key: milestone[key] for key in ("state", "reason", "name") if key in milestone}
    tasks = scope.get("tasks", scope.get("task_rows", []))
    if isinstance(tasks, list):
        compact["tasks"] = [_pick(task, ("id", "project_id", "state", "blocked", "blocker", "progress", "progress_display", "latest_proof_receipt") + (("display_id", "label") if identity else ())) for task in tasks[:128] if isinstance(task, dict)]
        compact["truncated"] = len(tasks) > 128
    return compact


def _compact_usage(view: dict[str, Any]) -> dict[str, Any]:
    compact = dict(view)
    compact.pop("verified_yield", None)
    if isinstance(view.get("task_history"), dict):
        compact["task_history"] = _pick(view["task_history"], ("status", "total_tokens", "coverage", "model_status", "claim_limit"))
    items = view.get("items")
    if isinstance(items, list) and items:
        window = view.get("window", {})
        after, before = window.get("after_ms"), window.get("before_ms")
        if type(after) is not int or type(before) is not int or not 0 <= after <= before <= 2**53 - 1:
            raise MCPError("Invalid usage window")
        previous = after - 1
        for row in items:
            if (not isinstance(row, dict) or type(row.get("bucket_ms")) is not int
                    or not previous < row["bucket_ms"] <= before
                    or type(row.get("delta_tokens")) is not int or row["delta_tokens"] < 0):
                raise MCPError("Invalid token observation")
            previous = row["bucket_ms"]
        total = sum(row["delta_tokens"] for row in items)
        if type(view.get("total_tokens")) is not int or total != view["total_tokens"] or total > 2**53 - 1:
            raise MCPError("Token total mismatch")
        # The existing token_samples authority emits 60-second buckets. Never
        # aggregate across a missing bucket or infer continuity from array order.
        runs = []
        for row in items:
            if not runs or row["bucket_ms"] - runs[-1][-1]["bucket_ms"] != 60_000:
                runs.append([])
            runs[-1].append(row)
        omitted = [row for run in runs[:-256] for row in run]
        runs = runs[-256:]
        target = min(256, sum(len(run) for run in runs))
        capacity = sum(len(run) - 1 for run in runs)
        extra, cumulative, allocated = target - len(runs), 0, 0
        compact["items"] = []
        for run in runs:
            cumulative += len(run) - 1
            next_allocated = cumulative * extra // capacity if capacity else 0
            count = 1 + next_allocated - allocated
            allocated = next_allocated
            for index in range(count):
                group = run[index * len(run) // count:(index + 1) * len(run) // count]
                previous = compact["items"][-1] if compact["items"] else None
                compact["items"].append({**(group[0] if len(group) == 1 else {}),
                    "bucket_ms": group[-1]["bucket_ms"], "bucket_start_ms": group[0]["bucket_ms"],
                    "delta_tokens": sum(row["delta_tokens"] for row in group),
                    "connect_from_previous": previous is not None and group[0]["bucket_ms"] - previous["bucket_ms"] == 60_000})
        if len(items) > 256:
            compact["series_aggregation"] = {"method": "contiguous_observed_sum", "input_count": len(items),
                "output_count": len(compact["items"]), "omitted_input_count": len(omitted),
                "omitted_tokens": sum(row["delta_tokens"] for row in omitted)}
    for key in ("task_usage", "rate_history"):
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


def _device_status(telemetry_path: Path = DEFAULT_TELEMETRY) -> dict[str, Any]:
    """Bounded activation observations from the existing metadata stream."""
    receipts = []
    status = "NO_ACTIVATION_RECEIPTS"
    try:
        with telemetry_path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 65536))
            lines = stream.read(65536).decode("utf-8", errors="replace").splitlines()
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("tool") == "workflow_activation":
                receipts.append(_pick(record, ("timestamp", "host", "hook_event", "session_hash", "plugin_version", "skill_sha256", "success")))
        if receipts:
            status = "OBSERVED_HOOK_OUTPUT"
    except FileNotFoundError:
        pass
    except OSError:
        status = "TELEMETRY_UNREADABLE"
    manifest = json.loads((REPO_ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if str(SWARM_SKILL_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(SWARM_SKILL_ROOT / "scripts"))
    from swarm_telemetry import status as product_status
    return {"product_telemetry": product_status(), "host": socket.gethostname(), "plugin_version": manifest["version"],
            "activation_status": status, "activation_receipts": receipts[-50:],
            "claim_limit": "Local hook output only. Does not prove host context delivery, skill read, workflow compliance or another device. Reads at most the last 64 KiB."}


def _telemetry(path: Path, *, tool: str, started: float, ok: bool, result_bytes: int, error: str = "", activation: dict[str, Any] | None = None) -> bool:
    """Append bounded metadata only; prompts, responses, credentials stay out."""
    record = {
        "timestamp": int(time.time() * 1000),
        "session_hash": hashlib.sha256(os.environ.get("SWARM_MCP_SESSION_HASH", "unknown").encode()).hexdigest()[:16],
        "tool": tool if tool in {item["name"] for item in TOOLS} | {"probe_read_file", "probe_write_file", "probe_delete_file", "workflow_activation"} else "unknown",
        "category": "activation" if tool == "workflow_activation" else "read",
        "host": socket.gethostname(),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "success": ok,
        "result_bytes": result_bytes,
    }
    if activation is not None and tool == "workflow_activation":
        record.update(_pick(activation, ("hook_event", "session_hash", "plugin_version", "skill_sha256")))
    if error:
        record["error"] = "invalid_arguments" if error == "invalid_arguments" else "projection_failed"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        return True
    except OSError:
        return False


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


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


def serve(*, probe_root: Path | None = None, telemetry_path: Path = DEFAULT_TELEMETRY,
          hq_app: HQApp | None = None) -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    projection = SwarmProjection(telemetry_path)
    probe_tools = (
        {"name": "probe_read_file", "description": "Read one scratch probe file.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "additionalProperties": False}},
        {"name": "probe_write_file", "description": "Write one scratch probe file.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "content": {"type": "string"}}, "required": ["content"], "additionalProperties": False}},
        {"name": "probe_delete_file", "description": "Delete one scratch probe file.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "additionalProperties": False}},
    ) if probe_root else ()
    tools = (*TOOLS, hq_app.tool()) if hq_app else (*TOOLS, *probe_tools)
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
                if hq_app:
                    result["capabilities"]["resources"] = {"listChanged": False}
            elif method == "tools/list":
                result = {"tools": list(tools)}
            elif method == "resources/list":
                result = {"resources": [{"uri": hq_app.uri, "name": "swarm-hq", "mimeType": "text/html;profile=mcp-app"}] if hq_app else []}
            elif method == "resources/read":
                served = _require_hq_read(params, hq_app)
                try:
                    result = served.resource()
                except (OSError, ValueError):
                    raise MCPError("HQ export unavailable or invalid") from None
            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments", {})
                spec = next((tool for tool in tools if tool["name"] == name), None)
                if spec is None:
                    raise MCPError("unknown tool")
                if name == "swarm_hq_view":
                    try:
                        _validate_arguments(spec, arguments)
                        result = hq_app.result()
                    except (MCPError, OSError, ValueError):
                        result = {"content": [{"type": "text", "text": "HQ snapshot unavailable or invalid; refresh the configured exact export."}], "isError": True}
                    print(json.dumps(_response(request_id, result), ensure_ascii=False, separators=(",", ":")), flush=True)
                    continue
                started = time.perf_counter()
                try:
                    _validate_arguments(spec, arguments)
                    value = _probe(probe_root, name, arguments) if name.startswith("probe_") else projection.call(name, arguments)
                    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                    if len(encoded.encode("utf-8")) > 262144:
                        raise MCPError("projection exceeds 262144 bytes; narrow the requested scope")
                    rejected = name in {"swarm_library_read", "swarm_flow_save", "swarm_flow_assign", "swarm_project_tickets", "swarm_project_ticket_execution"} and value.get("ok") is False
                    _telemetry(telemetry_path, tool=name, started=started, ok=not rejected,
                               result_bytes=len(encoded.encode("utf-8")), error="projection_rejected" if rejected else "")
                    result = {"content": [{"type": "text", "text": encoded}], "structuredContent": value, "isError": rejected}
                except Exception as exc:
                    error = str(exc) if isinstance(exc, MCPError) else "local projection failed"
                    _telemetry(telemetry_path, tool=name, started=started, ok=False, result_bytes=0, error="invalid_arguments" if isinstance(exc, MCPError) else "projection_failed")
                    result = {"content": [{"type": "text", "text": error}], "isError": True}
            else:
                print(json.dumps(_error(request_id, -32601, "method not found")), flush=True)
                continue
            print(json.dumps(_response(request_id, result), ensure_ascii=False, separators=(",", ":")), flush=True)
        except MCPError as exc:
            print(json.dumps(_error(request_id, -32602, str(exc), exc.data)), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdio", action="store_true", help="serve newline-delimited MCP JSON-RPC")
    parser.add_argument("--probe-root", type=Path, help="enable harmless scratch capability probe tools")
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    parser.add_argument("--hq-export", type=Path, help="explicit read-only Space exporter JSON; no automatic discovery")
    parser.add_argument("--hq-export-sha256", help="exact exporter JSON identity; required with --hq-export")
    parser.add_argument("--hq-projects", action="store_true", help="compose the existing Projects shell and scoped Settings")
    args = parser.parse_args()
    if not args.stdio:
        parser.error("--stdio is required")
    if (args.hq_export is None) != (args.hq_export_sha256 is None):
        parser.error("--hq-export and --hq-export-sha256 must be supplied together")
    if args.hq_projects and args.hq_export is None:
        parser.error("--hq-projects requires the bound source export")
    if args.hq_export is not None and args.probe_root is not None:
        parser.error("HQ view-only mode cannot enable scratch probe tools")
    try:
        hq_app = HQApp(args.hq_export, args.hq_export_sha256, projects=args.hq_projects) if args.hq_export is not None else None
    except (MCPError, OSError, ValueError):
        parser.error("HQ exporter artifact unavailable or invalid")
    return serve(probe_root=args.probe_root, telemetry_path=args.telemetry, hq_app=hq_app)


if __name__ == "__main__":
    raise SystemExit(main())
