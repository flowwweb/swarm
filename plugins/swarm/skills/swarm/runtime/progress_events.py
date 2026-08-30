"""Typed material-progress ledger plus bounded local progress pulse sidecars."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Condition
from typing import Any, Mapping
from weakref import WeakKeyDictionary

from .core import BUILT_IN_PROFESSIONS, CtrlProgressMeasure, CustodyMutation, HostCustodyReceipt, InvariantError, OperationClass, Role, RoleGateDecision, RetryOutcome, RetryTopologyAction, RetryTopologyLedger, Task, _authority_verify, _custody_message, role_gate
from .private_state import LockedPrivateState


PULSE_ROOT = Path("swarm") / "progress-pulses"
PULSE_SOURCE = "swarm_local_progress_sidecar"
PULSE_RECEIPT_TYPE = "swarm_ctrl_project_pulse"
MAX_PULSE_BYTES = 16 * 1024
MAX_PULSE_FILES = 1024
PROGRESS_LEDGER_PATH = Path("swarm") / "progress-ledger.jsonl"
PROGRESS_PROJECTION_PATH = Path("swarm") / "progress-current.json"
MAX_PROGRESS_EVENT_BYTES = 16 * 1024
MAX_FEED_SCAN_BYTES = 1024 * 1024
MAX_MATERIAL_SENTENCE = 240
MAX_YIELD_SERIES = 96
YIELD_TOKEN_SCALE = 100_000
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
PULSE_STATES = frozenset({"planned", "in_progress", "blocked", "complete", "stale"})
ETA_REASON_CODES = frozenset({
    "scope_discovered", "dependency", "failed_proof", "environment",
    "underestimated_complexity", "owner_capacity_change", "material_progress",
    "state_change", "completion", "heartbeat_stale",
})
ETA_STATES = frozenset({"planned", "in_progress", "blocked", "complete"})
TOP_LEVEL_FIELDS = frozenset({
    "schema_version", "source", "receipt_type", "task_id", "project_id",
    "pulse_receipt", "observed_at_ms", "state", "progress", "eta_report",
})
PROGRESS_FIELDS = frozenset({
    "receipt_id", "plan_id", "previous_plan_id", "unit_id", "unit_kind",
    "total_units", "completed_units", "basis", "observed_at_ms", "source",
})
ETA_FIELDS = frozenset({
    "receipt_type", "source", "receipt", "task_id", "project_id", "reason_code",
    "short_reason", "baseline", "current",
})
ETA_BOUND_FIELDS = frozenset({"eta_start_ms", "eta_end_ms", "confidence"})
ETA_CURRENT_FIELDS = frozenset({"eta_start_ms", "eta_end_ms", "confidence", "status", "progress_basis", "last_progress_at_ms"})

MATERIAL_EVENT_FIELDS = frozenset({
    "schema_version", "event_id", "dedupe_key", "portfolio_id", "project_id",
    "ctrl_id", "milestone_id", "block_id", "task_id", "owner_id",
    "scope_version", "parent_block_id", "dependency_ids", "lineage",
    "event_kind", "lifecycle_state", "measurement", "proof", "eta",
    "rework", "custody", "steering_receipt_ids", "material_update_sentence",
    "flags", "provenance", "source", "observed_at_ms", "causation_id",
    "parent_event_id", "topology", "expected_observation",
})
LINEAGE_FIELDS = frozenset({"predecessor_block_ids", "split_from", "merged_from"})
MEASUREMENT_FIELDS = frozenset({"state", "committed_weight", "admitted_proof_weight", "basis_receipt_ids"})
PROOF_FIELDS = frozenset({"required_classes", "receipt_ids", "claim_limit"})
ETA_EVENT_FIELDS = frozenset({"start_ms", "end_ms", "confidence", "basis_receipt_ids"})
REWORK_FIELDS = frozenset({"attempt", "count", "invalidated_receipt_ids"})
CUSTODY_FIELDS = frozenset({"surface", "receipt_id"})
TOPOLOGY_FIELDS = frozenset({
    "node_kind", "input_receipt_ids", "dispatch_receipt_id",
    "completion_receipt_id", "cost_receipt_ids", "release_receipt_ids", "role_manifest", "routing_evidence",
})
ROUTING_EVIDENCE_FIELDS = frozenset({"disposition", "route", "selected_owner", "selected_task_id", "project_active", "release_event", "scope", "critical_path", "recovery"})
ROUTING_SCOPE_FIELDS = frozenset({"goal_id", "request_id", "task_id", "mutable_surface", "owner_id"})
ROUTING_RECOVERY_FIELDS = frozenset({"state", "action", "attempts", "permitted_route_ids", "failed_route_id", "evidence_receipt_ids", "release_condition", "responsible_authority", "smallest_solution"})
ROLE_FIT_DISPOSITIONS = frozenset({"KEEP_ROLE", "SPECIALIZE_EXISTING", "ADD_INSTANCE", "REASSIGN_EXISTING", "PROPOSE_CUSTOM_ROLE"})
EXECUTION_ROUTES = frozenset({"normal_subagent", "normal_task", "degraded_subagent", "waiting", "hard_blocked"})
TOPOLOGY_NODE_KINDS = frozenset({"CTRL", "LEAD", "SUBAGENT", "TASK", "BLOCK"})
ROLE_MANIFEST_FIELDS = frozenset({
    "id", "name", "purpose", "owns", "instructions", "boundaries",
    "default_skills", "specializations", "avatar_asset_digest", "accent", "version", "source", "provenance",
})
ROLE_PAYLOAD_FIELDS = frozenset({"role_id", "expected_active_version", "assignment_task_id", "manifest"})
ROLE_SOURCES = frozenset({"builtin", "custom", "user_override"})
ROLE_ACCENTS = {
    "manager": "#FF6B4A", "strategist": "#F97316", "researcher": "#22D3EE", "analyst": "#38BDF8",
    "specialist": "#6366F1", "inventor": "#D946EF", "architect": "#FBBF24", "designer": "#F72585",
    "artist": "#8B5CF6", "writer": "#C084FC", "developer": "#2563EB", "producer": "#F43F5E",
    "tester": "#14B8A6", "assistant": "#818CF8", "security": "#FF4D2E", "auditor": "#CBD5E1",
    "legal": "#E11D48", "reviewer": "#A3E635", "operator": "#10B981", "marketer": "#FB7185",
    "support": "#5EEAD4", "accountant": "#2DD4BF", "recruiter": "#A855F7", "educator": "#FDE047",
}
BUILT_IN_ROLE_SPECIALIZATIONS = {
    "manager": ("Product Manager", "Project Manager", "Program Manager", "Operations Manager"),
    "strategist": ("Product Strategist", "Brand Strategist", "Growth Strategist", "Go-to-Market Strategist"),
    "researcher": ("User Researcher", "Market Researcher", "Technical Researcher", "Competitive Researcher"),
    "analyst": ("Data Analyst", "Business Analyst", "Financial Analyst", "Product Analyst"),
    "specialist": ("Domain Specialist", "Integration Specialist", "Compliance Specialist", "Localization Specialist"),
    "inventor": ("Product Inventor", "Systems Inventor", "Interaction Inventor", "Process Inventor"),
    "architect": ("Software Architect", "Systems Architect", "Solution Architect", "Data Architect"),
    "designer": ("Product Designer", "UX Designer", "UI Designer", "Game Design"),
    "artist": ("Brand Artist", "Concept Artist", "3D Artist", "Motion Artist"),
    "writer": ("Technical Writer", "UX Writer", "Copywriter", "Documentation Writer"),
    "developer": ("Frontend Developer", "Backend Developer", "Full-stack Developer", "Game Development"),
    "producer": ("Creative Producer", "Technical Producer", "Content Producer", "Release Producer"),
    "tester": ("QA Tester", "Automation Tester", "Performance Tester", "Accessibility Tester"),
    "assistant": ("Executive Assistant", "Project Assistant", "Research Assistant", "Administrative Assistant"),
    "security": ("Application Security", "Cloud Security", "Infrastructure Security", "Security Operations"),
    "auditor": ("Compliance Auditor", "Security Auditor", "Financial Auditor", "Quality Auditor"),
    "legal": ("Product Counsel", "Privacy Counsel", "Commercial Counsel", "Regulatory Counsel"),
    "reviewer": ("Code Reviewer", "Product Reviewer", "Design Reviewer", "Release Reviewer"),
    "operator": ("Release Operator", "Platform Operator", "Data Operator", "Incident Operator"),
    "marketer": ("Product Marketer", "Growth Marketer", "Content Marketer", "Lifecycle Marketer"),
    "support": ("Customer Support", "Technical Support", "Developer Support", "Community Support"),
    "accountant": ("Financial Accountant", "Management Accountant", "Tax Accountant", "Cost Accountant"),
    "recruiter": ("Technical Recruiter", "Design Recruiter", "Executive Recruiter", "Operations Recruiter"),
    "educator": ("Technical Educator", "Product Educator", "Curriculum Designer", "Enablement Specialist"),
}
REQUEST_LIFECYCLE_EVENT_FIELDS = frozenset({
    "schema_version", "record_type", "event_id", "dedupe_key", "request_id",
    "stage_id", "parent_event_id", "envelope_digest", "lifecycle_state",
    "record", "route_receipt_ids", "permitted_route_ids", "failed_goal_turn_receipt_ids",
    "release_authority", "release_receipt_id", "release_issued_at_ms", "expected_observation",
})
LEGACY_REQUEST_LIFECYCLE_EVENT_FIELDS = frozenset({
    "schema_version", "record_type", "event_id", "dedupe_key", "request_id",
    "stage_id", "parent_event_id", "envelope_digest", "lifecycle_state",
    "record", "route_receipt_ids", "release_authority",
})
REQUEST_RECORD_FIELDS = frozenset({
    "id", "goal_id", "task_id", "accepted_owner", "outcome_kind",
    "outcome_digest", "accepting_route", "accepted_at", "next_due_event",
    "next_due_at", "evidence_receipts", "transitions", "successor_id",
})
REQUEST_TRANSITION_FIELDS = frozenset({"state", "kind", "cursor"})
REQUEST_CURSOR_FIELDS = frozenset({"event_receipt", "message_id", "surface_receipt", "feed_sequence"})
TASK_HANDOFF_EVENT_FIELDS = frozenset({
    "schema_version", "record_type", "event_id", "dedupe_key", "handoff_id",
    "parent_event_id", "event_kind", "goal_id", "task_id", "old_owner",
    "new_owner", "checkpoint_digest", "scope_version", "lease_version",
    "receipt_id", "host_issued_at_ms", "observed_at_ms", "expected_observation",
})
EXPECTED_RECEIPT_FIELDS = frozenset({
    "schema_version", "record_type", "receipt_id", "goal_id",
    "task_id", "owner_id", "lease_version", "target_id", "artifact_digest",
    "expected_event_kind", "due_event", "due_generation", "source_cursor",
    "attempted_route_digests", "observed_at_ms",
})
EXPECTED_OBSERVATION_FIELDS = frozenset({
    "expected_receipt_id", "goal_id", "owner_id", "lease_version", "target_id",
    "artifact_digest", "source_cursor", "route_digest", "outcome", "evidence_receipt_ids",
})
EXPECTED_DUE_EVENTS = frozenset({"MATERIAL_EVENT", "TURN_COMPLETION", "LEASE_EXPIRY", "USER_STEER"})
NON_MATERIAL_RECORD_TYPES = frozenset({"EXPECTED_RECEIPT", "REQUEST_LIFECYCLE", "TASK_HANDOFF", "CONNECTOR"})
CONNECTOR_RECEIPT_FIELDS = frozenset({
    "schema_version", "record_type", "receipt_id", "command_id", "receipt_index",
    "idempotency_key", "command_digest",
    "project_id", "root_digest", "action", "status", "thread_id", "turn_id",
    "observed_root_digest", "observed_at_ms",
})
CONNECTOR_ACTIONS = frozenset({"AUTO", "MANUAL_AGENT", "TASK", "TOPOLOGY_MATERIALIZE", "REPAIR", "LOCAL_HQ"})
CONNECTOR_STATUSES = frozenset({"COMMAND", "ACKNOWLEDGED", "PROGRESS", "RESULT", "UNSUPPORTED"})
CONNECTOR_TERMINAL_STATUSES = frozenset({"RESULT", "UNSUPPORTED"})


class ProgressLifecycle(StrEnum):
    PLANNED = "PLANNED"
    READY = "READY"
    ACTIVE = "ACTIVE"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    RETRYING = "RETRYING"
    REVIEW = "REVIEW"
    VERIFIED = "VERIFIED"
    INVALIDATED_REWORK = "INVALIDATED_REWORK"
    USER_PAUSED = "USER_PAUSED"
    ACCEPTED = "ACCEPTED"
    TOMBSTONED = "TOMBSTONED"


class LedgerLifecycleState(StrEnum):
    OFFERED = "OFFERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ADMITTED = "ADMITTED"
    RUNNING = "RUNNING"
    RESULT_PENDING = "RESULT_PENDING"
    REVIEW_PENDING = "REVIEW_PENDING"
    COMPLETE = "COMPLETE"
    RETRYING = "RETRYING"
    WAITING = "WAITING"
    USER_PAUSED = "USER_PAUSED"
    KEEP_OUT = "KEEP_OUT"
    NEEDS_AUTHORITY = "NEEDS_AUTHORITY"
    STALLED = "STALLED"
    BLOCKED = "BLOCKED"


class ProgressMeasurementState(StrEnum):
    UNMEASURED = "UNMEASURED"
    PARTIAL = "PARTIAL"
    MEASURED = "MEASURED"


class ProgressEventKind(StrEnum):
    BLOCK_CREATED = "BLOCK_CREATED"
    SCOPE_REVISED = "SCOPE_REVISED"
    DEPENDENCY_LINKED = "DEPENDENCY_LINKED"
    STATE_CHANGED = "STATE_CHANGED"
    CURRENT_ACTION_CHANGED = "CURRENT_ACTION_CHANGED"
    PROGRESS_MEASURED = "PROGRESS_MEASURED"
    PROOF_ADMITTED = "PROOF_ADMITTED"
    PROOF_INVALIDATED = "PROOF_INVALIDATED"
    ETA_CHANGED = "ETA_CHANGED"
    WAIT_CHANGED = "WAIT_CHANGED"
    REWORK_REQUESTED = "REWORK_REQUESTED"
    BLOCK_SPLIT = "BLOCK_SPLIT"
    BLOCK_MERGED = "BLOCK_MERGED"
    USER_STEERING_ACCEPTED = "USER_STEERING_ACCEPTED"
    LIVENESS_STALE = "LIVENESS_STALE"
    LIVENESS_RECOVERED = "LIVENESS_RECOVERED"
    RETRY_STARTED = "RETRY_STARTED"
    TAKEOVER_STARTED = "TAKEOVER_STARTED"
    ACCEPTED = "ACCEPTED"
    TOMBSTONED = "TOMBSTONED"
    ROLE_MANIFEST_CREATE = "ROLE_MANIFEST_CREATE"
    ROLE_MANIFEST_REVISE = "ROLE_MANIFEST_REVISE"
    ROLE_MANIFEST_RESET = "ROLE_MANIFEST_RESET"
    ROLE_ASSIGNMENT_BOUND = "ROLE_ASSIGNMENT_BOUND"


class TaskHandoffEventKind(StrEnum):
    HANDOFF_DUE = "HANDOFF_DUE"
    HANDOFF_OFFERED = "HANDOFF_OFFERED"
    HANDOFF_ACKNOWLEDGED = "HANDOFF_ACKNOWLEDGED"
    CUSTODY_TRANSFERRED = "CUSTODY_TRANSFERRED"


PROGRESS_FLAGS = frozenset({
    "warning", "blocked", "waiting_external", "stale", "conflicted",
    "rework", "unverified", "proof", "eta_changed",
})
PROGRESS_EVENT_SOURCES = frozenset({
    "swarm_runtime", "swarm_task_owner", "swarm_proof_registry",
    "swarm_request_ledger", "swarm_execution_adapter",
})


class ProgressEventError(ValueError):
    pass


def _ledger_custody_authority():
    states: WeakKeyDictionary[object, tuple[int | None, dict[str, HostCustodyReceipt]]] = WeakKeyDictionary()

    def install(owner: object, public_key: int | None) -> None:
        if owner in states:
            raise ProgressEventError("host custody verifier is already fixed for this ledger")
        states[owner] = (public_key, {})

    def retain(owner: object, receipt: HostCustodyReceipt) -> HostCustodyReceipt:
        public_key, receipts = states[owner]
        if not _authority_verify(public_key, _custody_message(receipt), receipt._signature):
            raise ProgressEventError("custody receipt requires the ledger's host-pinned signature verifier")
        existing = receipts.get(receipt.receipt)
        if existing is not None and existing != receipt:
            raise ProgressEventError("host custody receipt identity conflicts with retained content")
        if existing is None:
            receipts[receipt.receipt] = receipt
        return existing or receipt

    def current(owner: object, receipt: HostCustodyReceipt) -> bool:
        public_key, receipts = states[owner]
        return receipts.get(receipt.receipt) is receipt and _authority_verify(public_key, _custody_message(receipt), receipt._signature)

    return install, retain, current


_install_ledger_custody_authority, _retain_ledger_custody_receipt, _ledger_custody_receipt_is_current = _ledger_custody_authority()


def _safe_id(value: Any, label: str, *, maximum: int = 256) -> str:
    text = str(value or "").strip()
    if len(text) > maximum or not SAFE_ID.fullmatch(text):
        raise ProgressEventError(f"{label} must be a safe identifier")
    return text


def _safe_text(value: Any, label: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise ProgressEventError(f"{label} must be one bounded line of text")
    text = value.strip()
    if not text or len(text) > maximum or any(character in text for character in "\x00\r\n\t"):
        raise ProgressEventError(f"{label} must be one bounded line of text")
    return text


def _exact_fields(value: dict[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ProgressEventError(f"{label} contains unsupported field(s): {', '.join(sorted(unknown))}")


def _positive_int(value: Any, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ProgressEventError(f"{label} must be a {qualifier} integer")
    return value


def _safe_ids(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProgressEventError(f"{label} must be an array")
    items = tuple(_safe_id(item, label) for item in value)
    if len(items) != len(set(items)):
        raise ProgressEventError(f"{label} must not contain duplicates")
    return items


def _optional_id(value: Any, label: str) -> str | None:
    return None if value in (None, "") else _safe_id(value, label)


def _request_lifecycle_digest(payload: Mapping[str, Any], *, semantic: bool = False) -> str:
    value = dict(payload)
    if semantic:
        value.pop("event_id", None)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _task_handoff_digest(payload: Mapping[str, Any], *, semantic: bool = False) -> str:
    value = dict(payload)
    if semantic:
        value.pop("event_id", None)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _expected_receipt_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha256(value: Any, label: str) -> str:
    text = str(value or "").casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ProgressEventError(f"{label} must be SHA-256")
    return text


def _expected_event_kinds() -> frozenset[str]:
    return frozenset(kind.value for kind in ProgressEventKind) | frozenset({
        LedgerLifecycleState.RESULT_PENDING.value,
        TaskHandoffEventKind.HANDOFF_DUE.value,
    })


def _validate_expected_receipt(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProgressEventError("expected receipt must be an object")
    _exact_fields(payload, EXPECTED_RECEIPT_FIELDS, "expected receipt")
    if payload.get("schema_version") != 1 or payload.get("record_type") != "EXPECTED_RECEIPT":
        raise ProgressEventError("expected receipt requires schema v1 and typed record")
    expected_event_kind = _safe_id(payload.get("expected_event_kind"), "expected event kind")
    due_event = _safe_id(payload.get("due_event"), "expected due event")
    if expected_event_kind not in _expected_event_kinds() or due_event not in EXPECTED_DUE_EVENTS:
        raise ProgressEventError("expected receipt event kind or due event is unsupported")
    routes = _safe_ids(payload.get("attempted_route_digests"), "attempted route digests")
    if not routes:
        raise ProgressEventError("expected receipt requires at least one attempted route digest")
    routes = tuple(_sha256(route, "attempted route digest") for route in routes)
    receipt = {
        "schema_version": 1, "record_type": "EXPECTED_RECEIPT",
        "receipt_id": _safe_id(payload.get("receipt_id"), "expected receipt id"),
        "goal_id": _safe_id(payload.get("goal_id"), "expected goal id"),
        "task_id": _safe_id(payload.get("task_id"), "expected task id"),
        "owner_id": _safe_id(payload.get("owner_id"), "expected owner id"),
        "lease_version": _positive_int(payload.get("lease_version"), "expected lease version"),
        "target_id": _safe_id(payload.get("target_id"), "expected target id"),
        "artifact_digest": _sha256(payload.get("artifact_digest"), "expected artifact digest"),
        "expected_event_kind": expected_event_kind, "due_event": due_event,
        "due_generation": _positive_int(payload.get("due_generation"), "expected due generation"),
        "source_cursor": _positive_int(payload.get("source_cursor"), "expected source cursor", allow_zero=True),
        "attempted_route_digests": list(routes),
        "observed_at_ms": _positive_int(payload.get("observed_at_ms"), "expected observed_at_ms", allow_zero=True),
    }
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_PROGRESS_EVENT_BYTES:
        raise ProgressEventError("expected receipt exceeds the material event byte limit")
    return receipt


def _validate_expected_observation(payload: Any) -> dict[str, Any] | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ProgressEventError("expected observation must be an object")
    _exact_fields(payload, EXPECTED_OBSERVATION_FIELDS, "expected observation")
    outcome = str(payload.get("outcome") or "")
    if outcome not in {"MATERIAL", "EMPTY", "TIMEOUT", "HTTP_400", "MISSING_THREAD", "REPLAY"}:
        raise ProgressEventError("expected observation outcome is invalid")
    return {
        "expected_receipt_id": _safe_id(payload.get("expected_receipt_id"), "expected receipt id"),
        "goal_id": _safe_id(payload.get("goal_id"), "observed goal id"),
        "owner_id": _safe_id(payload.get("owner_id"), "observed owner id"),
        "lease_version": _positive_int(payload.get("lease_version"), "observed lease version"),
        "target_id": _safe_id(payload.get("target_id"), "observed target id"),
        "artifact_digest": _sha256(payload.get("artifact_digest"), "observed artifact digest"),
        "source_cursor": _positive_int(payload.get("source_cursor"), "observed source cursor", allow_zero=True),
        "route_digest": _sha256(payload.get("route_digest"), "observed route digest"),
        "outcome": outcome,
        "evidence_receipt_ids": list(_safe_ids(payload.get("evidence_receipt_ids"), "observed evidence receipt ids")),
    }


def _validate_routing_evidence(payload: Any) -> dict[str, Any] | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ProgressEventError("routing evidence must be an object")
    _exact_fields(payload, ROUTING_EVIDENCE_FIELDS, "routing evidence")
    disposition = _safe_id(payload.get("disposition"), "routing disposition")
    route = _safe_id(payload.get("route"), "routing route")
    if disposition not in ROLE_FIT_DISPOSITIONS or route not in EXECUTION_ROUTES:
        raise ProgressEventError("routing evidence disposition or route is unsupported")
    project_active = payload.get("project_active")
    critical_path = payload.get("critical_path")
    if not isinstance(project_active, bool) or not isinstance(critical_path, bool):
        raise ProgressEventError("routing evidence activity and critical-path facts must be boolean")
    raw_scope = payload.get("scope")
    scope = None
    if raw_scope is not None:
        if not isinstance(raw_scope, dict):
            raise ProgressEventError("routing scope must be an object")
        _exact_fields(raw_scope, ROUTING_SCOPE_FIELDS, "routing scope")
        scope = {
            "goal_id": _safe_id(raw_scope.get("goal_id"), "routing goal_id"),
            "request_id": _safe_id(raw_scope.get("request_id"), "routing request_id"),
            "task_id": _safe_id(raw_scope.get("task_id"), "routing task_id"),
            "mutable_surface": _safe_text(raw_scope.get("mutable_surface"), "routing mutable_surface", maximum=512),
            "owner_id": _safe_id(raw_scope.get("owner_id"), "routing owner_id"),
        }
    raw_recovery = payload.get("recovery")
    recovery = None
    if raw_recovery is not None:
        if not isinstance(raw_recovery, dict):
            raise ProgressEventError("routing recovery must be an object")
        _exact_fields(raw_recovery, ROUTING_RECOVERY_FIELDS, "routing recovery")
        recovery = {
            "state": _safe_id(raw_recovery.get("state"), "routing recovery state"),
            "action": _safe_id(raw_recovery.get("action"), "routing recovery action"),
            "attempts": _positive_int(raw_recovery.get("attempts"), "routing recovery attempts"),
            "permitted_route_ids": list(_safe_ids(raw_recovery.get("permitted_route_ids"), "routing permitted routes")),
            "failed_route_id": _safe_id(raw_recovery.get("failed_route_id"), "routing failed route"),
            "evidence_receipt_ids": list(_safe_ids(raw_recovery.get("evidence_receipt_ids"), "routing recovery evidence")),
            "release_condition": None if raw_recovery.get("release_condition") in (None, "") else _safe_text(raw_recovery.get("release_condition"), "routing release condition", maximum=1024),
            "responsible_authority": _optional_id(raw_recovery.get("responsible_authority"), "routing responsible authority"),
            "smallest_solution": _safe_text(raw_recovery.get("smallest_solution"), "routing smallest solution", maximum=1024),
        }
    release_event = None if payload.get("release_event") in (None, "") else _safe_text(payload.get("release_event"), "routing release event", maximum=1024)
    if route == "waiting" and release_event is None:
        raise ProgressEventError("WAITING routing evidence requires an exact release event")
    if route == "hard_blocked":
        if project_active or scope is None or recovery is None or recovery["attempts"] < 3 or not recovery["permitted_route_ids"] or not recovery["release_condition"] or not recovery["responsible_authority"]:
            raise ProgressEventError("HARD_BLOCKED routing evidence requires scoped retained exhaustion and release authority")
    return {
        "disposition": disposition, "route": route,
        "selected_owner": _safe_id(payload.get("selected_owner"), "routing selected owner"),
        "selected_task_id": _optional_id(payload.get("selected_task_id"), "routing selected task"),
        "project_active": project_active, "release_event": release_event, "scope": scope,
        "critical_path": critical_path, "recovery": recovery,
    }


def task_handoff_host_binding(payload: Mapping[str, Any]) -> str:
    """Bind one opaque host receipt to the exact task-start or acknowledgement fact."""
    event = validate_task_handoff_event({key: payload.get(key) for key in TASK_HANDOFF_EVENT_FIELDS})
    kind = TaskHandoffEventKind(event["event_kind"])
    if kind not in {TaskHandoffEventKind.HANDOFF_DUE, TaskHandoffEventKind.HANDOFF_ACKNOWLEDGED}:
        raise ProgressEventError("host custody binds only task start or handoff acknowledgement")
    values = (
        "task-start" if kind is TaskHandoffEventKind.HANDOFF_DUE else "task-handoff-ack",
        event["handoff_id"], event["goal_id"], event["task_id"], event["old_owner"],
        event["new_owner"], event["checkpoint_digest"], event["scope_version"],
        event["lease_version"], event["host_issued_at_ms"],
    )
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def request_blocked_release_binding(payload: Mapping[str, Any]) -> str:
    """Bind terminal release authority to the retained exhausted-route evidence."""
    event = validate_request_lifecycle_event(dict(payload))
    if event["lifecycle_state"] != LedgerLifecycleState.BLOCKED.value:
        raise ProgressEventError("release custody binds only terminal BLOCKED")
    values = (
        "request-blocked-release", event["request_id"], event["stage_id"],
        event["parent_event_id"], event["envelope_digest"], event["permitted_route_ids"],
        event["route_receipt_ids"], event["failed_goal_turn_receipt_ids"],
        event["release_authority"], event["release_issued_at_ms"],
    )
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_task_handoff_event(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProgressEventError("task handoff event must be an object")
    _exact_fields(payload, TASK_HANDOFF_EVENT_FIELDS, "task handoff event")
    if payload.get("schema_version") != 1 or payload.get("record_type") != "TASK_HANDOFF":
        raise ProgressEventError("task handoff event requires schema v1 and typed record")
    for key in ("event_id", "dedupe_key", "handoff_id", "goal_id", "task_id", "old_owner", "receipt_id"):
        _safe_id(payload.get(key), key)
    parent_event_id = _optional_id(payload.get("parent_event_id"), "parent_event_id")
    new_owner = _optional_id(payload.get("new_owner"), "new_owner")
    checkpoint_digest = payload.get("checkpoint_digest")
    if checkpoint_digest is not None and (
        not isinstance(checkpoint_digest, str)
        or len(checkpoint_digest) != 64
        or any(character not in "0123456789abcdef" for character in checkpoint_digest)
    ):
        raise ProgressEventError("task handoff checkpoint_digest must be SHA-256")
    _positive_int(payload.get("scope_version"), "scope_version")
    _positive_int(payload.get("lease_version"), "lease_version")
    host_issued_at_ms = payload.get("host_issued_at_ms")
    if host_issued_at_ms is not None:
        _positive_int(host_issued_at_ms, "host_issued_at_ms", allow_zero=True)
    _positive_int(payload.get("observed_at_ms"), "observed_at_ms", allow_zero=True)
    try:
        event_kind = TaskHandoffEventKind(str(payload.get("event_kind") or ""))
    except ValueError as error:
        raise ProgressEventError("task handoff event kind is invalid") from error
    if event_kind is TaskHandoffEventKind.HANDOFF_DUE:
        if parent_event_id is not None or new_owner is not None or checkpoint_digest is not None or host_issued_at_ms is None:
            raise ProgressEventError("HANDOFF_DUE cannot claim a target owner or checkpoint")
    elif parent_event_id is None or new_owner is None or checkpoint_digest is None:
        raise ProgressEventError("handoff transition requires its parent, target owner, and checkpoint")
    elif event_kind is TaskHandoffEventKind.HANDOFF_ACKNOWLEDGED and host_issued_at_ms is None:
        raise ProgressEventError("handoff acknowledgement requires host issuance time")
    elif event_kind is not TaskHandoffEventKind.HANDOFF_ACKNOWLEDGED and host_issued_at_ms is not None:
        raise ProgressEventError("host issuance time is reserved for task start and acknowledgement")
    if new_owner == payload["old_owner"]:
        raise ProgressEventError("task handoff requires a distinct target owner")
    if event_kind in {TaskHandoffEventKind.HANDOFF_DUE, TaskHandoffEventKind.HANDOFF_ACKNOWLEDGED} and not re.fullmatch(r"[0-9a-f]{64}", payload["receipt_id"]):
        raise ProgressEventError("task start and acknowledgement require an opaque host receipt")
    observation = _validate_expected_observation(payload.get("expected_observation"))
    if observation is not None and event_kind is not TaskHandoffEventKind.HANDOFF_DUE:
        raise ProgressEventError("only an admitted lease-expiry event may evaluate an expected receipt")
    canonical = dict(payload)
    if observation is None:
        canonical.pop("expected_observation", None)
    else:
        canonical["expected_observation"] = observation
    return canonical


def validate_request_lifecycle_event(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProgressEventError("request lifecycle event must be an object")
    _exact_fields(payload, REQUEST_LIFECYCLE_EVENT_FIELDS, "request lifecycle event")
    if payload.get("schema_version") != 1 or payload.get("record_type") != "REQUEST_LIFECYCLE":
        raise ProgressEventError("request lifecycle event requires schema v1 and typed record")
    for key in ("event_id", "dedupe_key", "request_id", "stage_id"):
        _safe_id(payload.get(key), key)
    parent_event_id = _optional_id(payload.get("parent_event_id"), "parent_event_id")
    envelope_digest = payload.get("envelope_digest")
    if not isinstance(envelope_digest, str) or len(envelope_digest) != 64 or any(character not in "0123456789abcdef" for character in envelope_digest):
        raise ProgressEventError("request lifecycle envelope_digest must be SHA-256")
    try:
        lifecycle_state = LedgerLifecycleState(str(payload.get("lifecycle_state") or ""))
    except ValueError as error:
        raise ProgressEventError("request lifecycle state is invalid") from error
    route_receipts = _safe_ids(payload.get("route_receipt_ids"), "route_receipt_ids")
    permitted_routes = _safe_ids(payload.get("permitted_route_ids"), "permitted_route_ids")
    failed_goal_turns = _safe_ids(payload.get("failed_goal_turn_receipt_ids"), "failed_goal_turn_receipt_ids")
    release_authority = _optional_id(payload.get("release_authority"), "release_authority")
    release_receipt_id = _optional_id(payload.get("release_receipt_id"), "release_receipt_id")
    release_issued_at_ms = payload.get("release_issued_at_ms")
    if release_issued_at_ms is not None:
        _positive_int(release_issued_at_ms, "release_issued_at_ms", allow_zero=True)
    record = payload.get("record")
    if lifecycle_state is LedgerLifecycleState.OFFERED:
        if record is not None or parent_event_id is not None:
            raise ProgressEventError("OFFERED is a transport-bound root event without a lifecycle record")
    else:
        if not isinstance(record, dict):
            raise ProgressEventError("request lifecycle event requires a derived request record")
        _exact_fields(record, REQUEST_RECORD_FIELDS, "request lifecycle record")
        if record.get("id") != payload["request_id"]:
            raise ProgressEventError("request lifecycle record identity does not match its event")
        for key in ("id", "goal_id", "task_id", "accepted_owner", "outcome_kind", "next_due_event"):
            _safe_id(record.get(key), f"request record {key}")
        _optional_id(record.get("successor_id"), "request record successor_id")
        outcome_digest = record.get("outcome_digest")
        if not isinstance(outcome_digest, str) or len(outcome_digest) != 64 or any(character not in "0123456789abcdef" for character in outcome_digest):
            raise ProgressEventError("request lifecycle outcome digest must be SHA-256")
        accepting_route = record.get("accepting_route")
        evidence = record.get("evidence_receipts")
        transitions = record.get("transitions")
        if not isinstance(accepting_route, list) or not accepting_route or any(_safe_id(value, "accepting route") != value for value in accepting_route):
            raise ProgressEventError("request lifecycle accepting route is invalid")
        if not isinstance(evidence, list) or tuple(evidence) != _safe_ids(evidence, "request evidence receipts"):
            raise ProgressEventError("request lifecycle evidence receipts are invalid")
        if not isinstance(record.get("accepted_at"), int) or record["accepted_at"] < 0 or not isinstance(record.get("next_due_at"), int) or record["next_due_at"] < 0:
            raise ProgressEventError("request lifecycle timestamps must be nonnegative integers")
        if not isinstance(transitions, list) or not transitions:
            raise ProgressEventError("request lifecycle record requires retained transitions")
        feed_sequences: list[int] = []
        for transition in transitions:
            if not isinstance(transition, dict):
                raise ProgressEventError("request lifecycle transition must be an object")
            _exact_fields(transition, REQUEST_TRANSITION_FIELDS, "request lifecycle transition")
            _safe_id(transition.get("state"), "request lifecycle transition state")
            _safe_id(transition.get("kind"), "request lifecycle transition kind")
            cursor = transition.get("cursor")
            if not isinstance(cursor, dict):
                raise ProgressEventError("request lifecycle transition cursor must be an object")
            _exact_fields(cursor, REQUEST_CURSOR_FIELDS, "request lifecycle cursor")
            for key in ("event_receipt", "message_id", "surface_receipt"):
                _safe_id(cursor.get(key), f"request lifecycle {key}")
            feed_sequences.append(_positive_int(cursor.get("feed_sequence"), "request lifecycle feed_sequence"))
        if feed_sequences != sorted(set(feed_sequences)):
            raise ProgressEventError("request lifecycle transition cursors must advance exactly once")
    if lifecycle_state is LedgerLifecycleState.BLOCKED:
        if (
            len(permitted_routes) < 3
            or len(route_receipts) < 3
            or len(failed_goal_turns) < 3
            or set(permitted_routes) != set(route_receipts)
            or release_authority is None
            or release_receipt_id is None
            or not re.fullmatch(r"[0-9a-f]{64}", release_receipt_id)
            or release_issued_at_ms is None
        ):
            raise ProgressEventError("terminal BLOCKED requires distinct retained failed goal turns, complete permitted-route exhaustion, and trusted release authority")
    elif lifecycle_state is LedgerLifecycleState.STALLED:
        if len(route_receipts) != 1 or not permitted_routes or route_receipts[0] not in permitted_routes or len(failed_goal_turns) != 1 or release_authority is not None or release_receipt_id is not None or release_issued_at_ms is not None:
            raise ProgressEventError("STALLED must retain one failed route and goal turn against a nonempty permitted-route inventory")
    elif route_receipts or permitted_routes or failed_goal_turns or release_authority is not None or release_receipt_id is not None or release_issued_at_ms is not None:
        raise ProgressEventError("route exhaustion evidence is reserved for terminal BLOCKED")
    observation = _validate_expected_observation(payload.get("expected_observation"))
    if observation is not None and lifecycle_state is not LedgerLifecycleState.RESULT_PENDING:
        raise ProgressEventError("only an admitted turn-completion event may evaluate an expected receipt")
    payload = dict(payload)
    if observation is None:
        payload.pop("expected_observation", None)
    else:
        payload["expected_observation"] = observation
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_PROGRESS_EVENT_BYTES:
        raise ProgressEventError("request lifecycle event exceeds the material event byte limit")
    return json.loads(encoded.decode("utf-8"))


def _validate_retained_request_lifecycle_event(payload: Any, event_digest: str) -> dict[str, Any]:
    """Decode the exact pre-exhaustion schema only after retained-line verification."""
    if not isinstance(payload, dict) or _request_lifecycle_digest(payload) != event_digest:
        raise ProgressEventError("retained request lifecycle digest does not bind its event")
    if set(payload) in {REQUEST_LIFECYCLE_EVENT_FIELDS, REQUEST_LIFECYCLE_EVENT_FIELDS - {"expected_observation"}}:
        return validate_request_lifecycle_event(payload)
    if set(payload) != LEGACY_REQUEST_LIFECYCLE_EVENT_FIELDS:
        raise ProgressEventError("retained request lifecycle schema is unsupported")
    migrated = {
        **payload,
        "permitted_route_ids": [],
        "failed_goal_turn_receipt_ids": [],
        "release_receipt_id": None,
        "release_issued_at_ms": None,
    }
    state = LedgerLifecycleState(str(payload.get("lifecycle_state") or ""))
    routes = _safe_ids(payload.get("route_receipt_ids"), "route_receipt_ids")
    authority = _optional_id(payload.get("release_authority"), "release_authority")
    if state is LedgerLifecycleState.BLOCKED:
        if len(routes) < 3 or authority is None:
            raise ProgressEventError("legacy terminal BLOCKED requires its retained route exhaustion and release authority")
    elif routes or authority is not None:
        raise ProgressEventError("legacy route exhaustion evidence is reserved for terminal BLOCKED")
    validation_copy = dict(migrated)
    if state in {LedgerLifecycleState.STALLED, LedgerLifecycleState.BLOCKED}:
        validation_copy.update({
            "lifecycle_state": LedgerLifecycleState.WAITING.value,
            "route_receipt_ids": [],
            "release_authority": None,
        })
    validate_request_lifecycle_event(validation_copy)
    return json.loads(json.dumps(migrated, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _validate_connector_receipt(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProgressEventError("connector receipt must be an object")
    _exact_fields(payload, CONNECTOR_RECEIPT_FIELDS, "connector receipt")
    if payload.get("schema_version") != 1 or payload.get("record_type") != "CONNECTOR":
        raise ProgressEventError("connector receipt schema is unsupported")
    normalized = dict(payload)
    for key in ("receipt_id", "command_id", "idempotency_key", "project_id", "action", "status"):
        normalized[key] = _safe_id(payload.get(key), f"connector {key}")
    if normalized["action"] not in CONNECTOR_ACTIONS or normalized["status"] not in CONNECTOR_STATUSES:
        raise ProgressEventError("connector action or status is unsupported")
    for key in ("command_digest", "root_digest"):
        value = payload.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ProgressEventError(f"connector {key} must be a lowercase SHA-256 digest")
    observed_root = payload.get("observed_root_digest")
    if observed_root is not None and (not isinstance(observed_root, str) or len(observed_root) != 64 or any(character not in "0123456789abcdef" for character in observed_root)):
        raise ProgressEventError("connector observed_root_digest must be null or a lowercase SHA-256 digest")
    for key in ("thread_id", "turn_id"):
        normalized[key] = None if payload.get(key) is None else _safe_id(payload.get(key), f"connector {key}")
    normalized["receipt_index"] = _positive_int(payload.get("receipt_index"), "connector receipt_index", allow_zero=True)
    normalized["observed_at_ms"] = _positive_int(payload.get("observed_at_ms"), "connector observed_at_ms", allow_zero=True)
    has_thread, has_turn = normalized["thread_id"] is not None, normalized["turn_id"] is not None
    if normalized["status"] in {"COMMAND", "UNSUPPORTED"} and (has_thread or has_turn or normalized["observed_root_digest"] is not None):
        raise ProgressEventError("connector command or unsupported receipt cannot claim host binding")
    if normalized["action"] == "LOCAL_HQ" and (has_thread or has_turn):
        raise ProgressEventError("LOCAL_HQ connector receipt cannot claim Codex host ids")
    if normalized["action"] == "LOCAL_HQ" and normalized["status"] in {"ACKNOWLEDGED", "PROGRESS", "RESULT"} and normalized["observed_root_digest"] != normalized["root_digest"]:
        raise ProgressEventError("LOCAL_HQ lifecycle requires the exact local observed root")
    if normalized["action"] != "LOCAL_HQ" and normalized["status"] == "ACKNOWLEDGED" and (not has_thread or has_turn or normalized["observed_root_digest"] != normalized["root_digest"]):
        raise ProgressEventError("Codex connector acknowledgement requires a thread and exact root binding")
    if normalized["action"] != "LOCAL_HQ" and normalized["status"] in {"PROGRESS", "RESULT"} and (not has_thread or not has_turn or normalized["observed_root_digest"] != normalized["root_digest"]):
        raise ProgressEventError("Codex connector progress or result requires thread, turn, and exact root binding")
    return json.loads(json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _connector_receipt_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProgressMaterialEvent:
    schema_version: int
    event_id: str
    dedupe_key: str
    portfolio_id: str
    project_id: str
    ctrl_id: str
    milestone_id: str
    block_id: str
    task_id: str
    owner_id: str
    scope_version: int
    parent_block_id: str | None
    dependency_ids: tuple[str, ...]
    predecessor_block_ids: tuple[str, ...]
    split_from: str | None
    merged_from: tuple[str, ...]
    event_kind: ProgressEventKind
    lifecycle_state: ProgressLifecycle
    measurement_state: ProgressMeasurementState
    committed_weight: int | None
    admitted_proof_weight: int
    weight_basis_receipt_ids: tuple[str, ...]
    proof_required_classes: tuple[str, ...]
    proof_receipt_ids: tuple[str, ...]
    claim_limit: str
    eta_start_ms: int | None
    eta_end_ms: int | None
    eta_confidence: int | None
    eta_receipt_ids: tuple[str, ...]
    attempt: int
    rework_count: int
    invalidated_receipt_ids: tuple[str, ...]
    custody_surface: str
    custody_receipt_id: str
    steering_receipt_ids: tuple[str, ...]
    material_update_sentence: str | None
    flags: tuple[str, ...]
    provenance: str
    source: str
    observed_at_ms: int
    causation_id: str | None
    parent_event_id: str | None
    topology_node_kind: str
    input_receipt_ids: tuple[str, ...]
    dispatch_receipt_id: str | None
    completion_receipt_id: str | None
    cost_receipt_ids: tuple[str, ...]
    release_receipt_ids: tuple[str, ...]
    role_manifest: dict[str, Any] | None
    routing_evidence: dict[str, Any] | None
    expected_observation: dict[str, Any] | None
    digest: str
    semantic_digest: str

    def canonical_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "dedupe_key": self.dedupe_key,
            "portfolio_id": self.portfolio_id,
            "project_id": self.project_id,
            "ctrl_id": self.ctrl_id,
            "milestone_id": self.milestone_id,
            "block_id": self.block_id,
            "task_id": self.task_id,
            "owner_id": self.owner_id,
            "scope_version": self.scope_version,
            "parent_block_id": self.parent_block_id,
            "dependency_ids": list(self.dependency_ids),
            "lineage": {
                "predecessor_block_ids": list(self.predecessor_block_ids),
                "split_from": self.split_from,
                "merged_from": list(self.merged_from),
            },
            "event_kind": self.event_kind.value,
            "lifecycle_state": self.lifecycle_state.value,
            "measurement": {
                "state": self.measurement_state.value,
                "committed_weight": self.committed_weight,
                "admitted_proof_weight": self.admitted_proof_weight,
                "basis_receipt_ids": list(self.weight_basis_receipt_ids),
            },
            "proof": {
                "required_classes": list(self.proof_required_classes),
                "receipt_ids": list(self.proof_receipt_ids),
                "claim_limit": self.claim_limit,
            },
            "eta": {
                "start_ms": self.eta_start_ms,
                "end_ms": self.eta_end_ms,
                "confidence": self.eta_confidence,
                "basis_receipt_ids": list(self.eta_receipt_ids),
            },
            "rework": {
                "attempt": self.attempt,
                "count": self.rework_count,
                "invalidated_receipt_ids": list(self.invalidated_receipt_ids),
            },
            "custody": {"surface": self.custody_surface, "receipt_id": self.custody_receipt_id},
            "steering_receipt_ids": list(self.steering_receipt_ids),
            "material_update_sentence": self.material_update_sentence,
            "flags": list(self.flags),
            "provenance": self.provenance,
            "source": self.source,
            "observed_at_ms": self.observed_at_ms,
            "causation_id": self.causation_id,
            "parent_event_id": self.parent_event_id,
        }
        if self.schema_version == 2:
            payload["topology"] = {
                "node_kind": self.topology_node_kind,
                "input_receipt_ids": list(self.input_receipt_ids),
                "dispatch_receipt_id": self.dispatch_receipt_id,
                "completion_receipt_id": self.completion_receipt_id,
                "cost_receipt_ids": list(self.cost_receipt_ids),
                "release_receipt_ids": list(self.release_receipt_ids),
            }
            if self.role_manifest is not None:
                payload["topology"]["role_manifest"] = self.role_manifest
            if self.routing_evidence is not None:
                payload["topology"]["routing_evidence"] = self.routing_evidence
        if self.expected_observation is not None:
            payload["expected_observation"] = self.expected_observation
        return payload


def _role_texts(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > 32 or (not value and not allow_empty):
        raise ProgressEventError(f"{label} must be a bounded array")
    return [_safe_text(item, label, maximum=512) for item in value]


def _role_specializations(value: Any, source: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 4:
        raise ProgressEventError("role specializations must contain zero to four labels")
    labels = [_safe_text(item, "role specialization", maximum=80) for item in value]
    if len({label.casefold() for label in labels}) != len(labels):
        raise ProgressEventError("role specializations must be ordered unique labels")
    if source == "builtin" and len(labels) != 4:
        raise ProgressEventError("built-in role manifests require exactly four specializations")
    return labels


def _validate_role_manifest(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProgressEventError("role manifest must be an object")
    _exact_fields(payload, ROLE_MANIFEST_FIELDS, "role manifest")
    source = str(payload.get("source") or "")
    if "specializations" not in payload:
        raise ProgressEventError("current role manifests must explicitly provide specializations")
    digest = str(payload.get("avatar_asset_digest") or "").casefold()
    accent = str(payload.get("accent") or "").casefold()
    if source not in ROLE_SOURCES or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ProgressEventError("role manifest source or avatar digest is invalid")
    if not re.fullmatch(r"#[0-9a-f]{6}", accent):
        raise ProgressEventError("role manifest accent must be a six-digit hex color")
    normalized = {
        "id": _safe_id(payload.get("id"), "role id"),
        "name": _safe_text(payload.get("name"), "role name", maximum=80),
        "purpose": _safe_text(payload.get("purpose"), "role purpose", maximum=512),
        "owns": _role_texts(payload.get("owns"), "role owns"),
        "instructions": _role_texts(payload.get("instructions"), "role instructions"),
        "boundaries": _role_texts(payload.get("boundaries"), "role boundaries"),
        "default_skills": list(_safe_ids(payload.get("default_skills"), "role default_skills")),
        "avatar_asset_digest": digest,
        "accent": accent,
        "source": source,
        "provenance": _role_texts(payload.get("provenance"), "role provenance"),
    }
    normalized["specializations"] = _role_specializations(payload["specializations"], source)
    expected = f"{source}:{hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}"
    version = expected if payload.get("version") in (None, "") else _safe_id(payload.get("version"), "role version")
    if version != expected:
        raise ProgressEventError("role manifest version does not match canonical content")
    return {**normalized, "version": version}


def validate_role_manifest(payload: Any) -> dict[str, Any]:
    return _validate_role_manifest(payload)


def build_role_manifest(role_id: str, draft: Mapping[str, Any], source: str, provenance: list[str]) -> dict[str, Any]:
    allowed = ROLE_MANIFEST_FIELDS - {"id", "version", "source", "provenance"}
    if not isinstance(draft, dict):
        raise ProgressEventError("role manifest draft must be an object")
    _exact_fields(draft, allowed, "role manifest draft")
    return validate_role_manifest({"id": role_id, **draft, "source": source, "provenance": provenance})


def load_builtin_role_manifests(roles_root: Path, avatar_path: Path) -> tuple[dict[str, Any], ...]:
    cards = {path.stem: path for path in Path(roles_root).glob("*.md") if path.is_file()}
    if set(cards) != set(BUILT_IN_PROFESSIONS) or set(BUILT_IN_ROLE_SPECIALIZATIONS) != set(BUILT_IN_PROFESSIONS) or set(ROLE_ACCENTS) != set(BUILT_IN_PROFESSIONS) or not Path(avatar_path).is_file():
        raise ProgressEventError("built-in role inventory must remain exactly 24 roles with one avatar asset")
    avatar_digest = hashlib.sha256(Path(avatar_path).read_bytes()).hexdigest()
    manifests = []
    for role_id, name in BUILT_IN_PROFESSIONS.items():
        text = cards[role_id].read_text(encoding="utf-8")
        instructions = [match.group(1) for line in text.splitlines() if (match := re.fullmatch(r"\d+\.\s+(.+)", line))]
        manifests.append(build_role_manifest(role_id, {
            "name": name,
            "purpose": f"Apply the {name} profession perspective to one bounded SWARM assignment.",
            "owns": [f"{name} profession guidance for the assigned surface."],
            "instructions": instructions,
            "boundaries": [
                "Profession metadata never transfers structural authority.",
                "User direction, custody, proof, and acceptance remain authoritative.",
            ],
            "default_skills": [],
            "specializations": list(BUILT_IN_ROLE_SPECIALIZATIONS[role_id]),
            "avatar_asset_digest": avatar_digest,
            "accent": ROLE_ACCENTS[role_id],
        }, "builtin", [f"role-card:{role_id}:{hashlib.sha256(text.encode()).hexdigest()}"]))
    return tuple(manifests)


def _validate_progress_material_event(
    payload: Any,
    *,
    retained_event: tuple[int, str] | None = None,
) -> ProgressMaterialEvent:
    """Validate one compact material event without accepting chat or tool content."""
    if not isinstance(payload, dict):
        raise ProgressEventError("progress material event must be a JSON object")
    raw_digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if retained_event is not None:
        retained_seq, retained_digest = retained_event
        if not isinstance(retained_seq, int) or retained_seq < 1 or retained_digest != raw_digest:
            raise ProgressEventError("retained progress event provenance does not bind its sequence and digest")
    _exact_fields(payload, MATERIAL_EVENT_FIELDS, "progress material event")
    schema_version = payload.get("schema_version")
    if schema_version not in {1, 2}:
        raise ProgressEventError("progress material event schema_version must be 1 or 2")
    event_id = _safe_id(payload.get("event_id"), "event_id")
    dedupe_key = _safe_id(payload.get("dedupe_key"), "dedupe_key")
    portfolio_id = _safe_id(payload.get("portfolio_id"), "portfolio_id")
    project_id = _safe_id(payload.get("project_id"), "project_id")
    ctrl_id = _safe_id(payload.get("ctrl_id"), "ctrl_id")
    milestone_id = _safe_id(payload.get("milestone_id"), "milestone_id")
    block_id = _safe_id(payload.get("block_id"), "block_id")
    task_id = _safe_id(payload.get("task_id"), "task_id")
    owner_id = _safe_id(payload.get("owner_id"), "owner_id")
    scope_version = _positive_int(payload.get("scope_version"), "scope_version")
    parent_block_id = _optional_id(payload.get("parent_block_id"), "parent_block_id")
    dependency_ids = _safe_ids(payload.get("dependency_ids"), "dependency_ids")

    lineage = payload.get("lineage")
    if not isinstance(lineage, dict):
        raise ProgressEventError("lineage must be an object")
    _exact_fields(lineage, LINEAGE_FIELDS, "lineage")
    predecessor_block_ids = _safe_ids(lineage.get("predecessor_block_ids"), "lineage predecessor_block_ids")
    split_from = _optional_id(lineage.get("split_from"), "lineage split_from")
    merged_from = _safe_ids(lineage.get("merged_from"), "lineage merged_from")

    try:
        event_kind = ProgressEventKind(str(payload.get("event_kind") or ""))
        lifecycle_state = ProgressLifecycle(str(payload.get("lifecycle_state") or ""))
    except ValueError as error:
        raise ProgressEventError("progress event kind or lifecycle state is invalid") from error

    measurement = payload.get("measurement")
    if not isinstance(measurement, dict):
        raise ProgressEventError("measurement must be an object")
    _exact_fields(measurement, MEASUREMENT_FIELDS, "measurement")
    try:
        measurement_state = ProgressMeasurementState(str(measurement.get("state") or ""))
    except ValueError as error:
        raise ProgressEventError("measurement state is invalid") from error
    committed_raw = measurement.get("committed_weight")
    committed_weight = None if committed_raw is None else _positive_int(committed_raw, "measurement committed_weight")
    admitted_proof_weight = _positive_int(measurement.get("admitted_proof_weight"), "measurement admitted_proof_weight", allow_zero=True)
    weight_basis_receipt_ids = _safe_ids(measurement.get("basis_receipt_ids"), "measurement basis_receipt_ids")
    if committed_weight is None:
        if measurement_state is not ProgressMeasurementState.UNMEASURED or admitted_proof_weight:
            raise ProgressEventError("unmeasured work cannot carry committed or admitted proof weight")
    elif not weight_basis_receipt_ids or admitted_proof_weight > committed_weight:
        raise ProgressEventError("measured weight requires receipts and cannot be over-admitted")

    proof = payload.get("proof")
    if not isinstance(proof, dict):
        raise ProgressEventError("proof must be an object")
    _exact_fields(proof, PROOF_FIELDS, "proof")
    proof_required_classes = _safe_ids(proof.get("required_classes"), "proof required_classes")
    proof_receipt_ids = _safe_ids(proof.get("receipt_ids"), "proof receipt_ids")
    claim_limit = _safe_text(proof.get("claim_limit"), "proof claim_limit", maximum=512)
    if admitted_proof_weight and not proof_receipt_ids:
        raise ProgressEventError("admitted proof weight requires exact proof receipts")

    eta = payload.get("eta")
    if not isinstance(eta, dict):
        raise ProgressEventError("eta must be an object")
    _exact_fields(eta, ETA_EVENT_FIELDS, "eta")
    eta_start_ms = eta.get("start_ms")
    eta_end_ms = eta.get("end_ms")
    eta_confidence = eta.get("confidence")
    if any(value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0) for value in (eta_start_ms, eta_end_ms)):
        raise ProgressEventError("eta bounds must be nonnegative integers or null")
    if eta_start_ms is not None and eta_end_ms is not None and eta_start_ms > eta_end_ms:
        raise ProgressEventError("eta range is invalid")
    if eta_confidence is not None and (not isinstance(eta_confidence, int) or isinstance(eta_confidence, bool) or not 0 <= eta_confidence <= 100):
        raise ProgressEventError("eta confidence must be 0..100 or null")
    eta_receipt_ids = _safe_ids(eta.get("basis_receipt_ids"), "eta basis_receipt_ids")
    if any(value is not None for value in (eta_start_ms, eta_end_ms, eta_confidence)) and not eta_receipt_ids:
        raise ProgressEventError("eta requires receipt-backed basis")

    rework = payload.get("rework")
    if not isinstance(rework, dict):
        raise ProgressEventError("rework must be an object")
    _exact_fields(rework, REWORK_FIELDS, "rework")
    attempt = _positive_int(rework.get("attempt"), "rework attempt")
    rework_count = _positive_int(rework.get("count"), "rework count", allow_zero=True)
    invalidated_receipt_ids = _safe_ids(rework.get("invalidated_receipt_ids"), "rework invalidated_receipt_ids")

    custody = payload.get("custody")
    if not isinstance(custody, dict):
        raise ProgressEventError("custody must be an object")
    _exact_fields(custody, CUSTODY_FIELDS, "custody")
    custody_surface = _safe_text(custody.get("surface"), "custody surface", maximum=512)
    custody_receipt_id = _safe_id(custody.get("receipt_id"), "custody receipt_id")
    steering_receipt_ids = _safe_ids(payload.get("steering_receipt_ids"), "steering_receipt_ids")

    sentence_raw = payload.get("material_update_sentence")
    material_update_sentence = None if sentence_raw in (None, "") else _safe_text(
        sentence_raw, "material_update_sentence", maximum=MAX_MATERIAL_SENTENCE
    )
    flags = tuple(str(item) for item in _safe_ids(payload.get("flags"), "flags"))
    if any(item not in PROGRESS_FLAGS for item in flags):
        raise ProgressEventError("progress event flags contain an unsupported value")
    provenance = _safe_text(payload.get("provenance"), "provenance", maximum=256)
    source = _safe_id(payload.get("source"), "source")
    if source not in PROGRESS_EVENT_SOURCES:
        raise ProgressEventError("progress material event source is not an existing SWARM authority seam")
    observed_at_ms = _positive_int(payload.get("observed_at_ms"), "observed_at_ms")
    causation_id = _optional_id(payload.get("causation_id"), "causation_id")
    parent_event_id = _optional_id(payload.get("parent_event_id"), "parent_event_id")
    topology = payload.get("topology")
    if schema_version == 2:
        if not isinstance(topology, dict):
            raise ProgressEventError("schema-v2 topology must be an object")
        _exact_fields(topology, TOPOLOGY_FIELDS, "topology")
        topology_node_kind = _safe_id(topology.get("node_kind"), "topology node_kind")
        if topology_node_kind not in TOPOLOGY_NODE_KINDS:
            raise ProgressEventError("topology node_kind is invalid")
        input_receipt_ids = _safe_ids(topology.get("input_receipt_ids"), "topology input_receipt_ids")
        dispatch_receipt_id = _optional_id(topology.get("dispatch_receipt_id"), "topology dispatch_receipt_id")
        completion_receipt_id = _optional_id(topology.get("completion_receipt_id"), "topology completion_receipt_id")
        cost_receipt_ids = _safe_ids(topology.get("cost_receipt_ids"), "topology cost_receipt_ids")
        release_receipt_ids = _safe_ids(topology.get("release_receipt_ids"), "topology release_receipt_ids")
        role_payload = topology.get("role_manifest")
        routing_evidence = _validate_routing_evidence(topology.get("routing_evidence"))
    else:
        if topology is not None:
            raise ProgressEventError("schema-v1 progress events cannot carry topology")
        topology_node_kind = "BLOCK"
        input_receipt_ids = ()
        dispatch_receipt_id = None
        completion_receipt_id = None
        cost_receipt_ids = ()
        release_receipt_ids = ()
        role_payload = None
        routing_evidence = None
    role_kinds = {
        ProgressEventKind.ROLE_MANIFEST_CREATE,
        ProgressEventKind.ROLE_MANIFEST_REVISE,
        ProgressEventKind.ROLE_MANIFEST_RESET,
        ProgressEventKind.ROLE_ASSIGNMENT_BOUND,
    }
    if event_kind in role_kinds:
        if not isinstance(role_payload, dict):
            raise ProgressEventError("role manifest event requires a typed role payload")
        _exact_fields(role_payload, ROLE_PAYLOAD_FIELDS, "role payload")
        role_id = _safe_id(role_payload.get("role_id"), "role payload role_id")
        expected_version = _optional_id(role_payload.get("expected_active_version"), "role expected_active_version")
        assignment_task = _optional_id(role_payload.get("assignment_task_id"), "role assignment_task_id")
        raw_manifest = role_payload.get("manifest")
        manifest = _validate_role_manifest(raw_manifest)
        if role_id != manifest["id"] or project_id != "swarm-role-manifests" or block_id != role_id:
            raise ProgressEventError("role manifest event identity is not server-bound")
        if source != "swarm_runtime" or custody_surface != "server:role-manifests":
            raise ProgressEventError("role manifest event requires server runtime custody")
        if event_kind is ProgressEventKind.ROLE_MANIFEST_CREATE:
            valid = expected_version is None and assignment_task is None and manifest["source"] == "custom"
        elif event_kind is ProgressEventKind.ROLE_MANIFEST_REVISE:
            valid = expected_version is not None and assignment_task is None and manifest["source"] in {"custom", "user_override"}
        elif event_kind is ProgressEventKind.ROLE_MANIFEST_RESET:
            valid = expected_version is not None and assignment_task is None and manifest["source"] == "builtin"
        else:
            valid = expected_version is not None and assignment_task == task_id
        if not valid:
            raise ProgressEventError("role manifest event transition payload is invalid")
        role_manifest = {
            "role_id": role_id,
            "expected_active_version": expected_version,
            "assignment_task_id": assignment_task,
            "manifest": manifest,
        }
    else:
        if role_payload is not None:
            raise ProgressEventError("non-role progress events cannot carry a role manifest")
        role_manifest = None
    if routing_evidence is not None:
        measurement = payload.get("measurement")
        if measurement_state is not ProgressMeasurementState.UNMEASURED or committed_weight is not None or admitted_proof_weight or proof_receipt_ids or material_update_sentence is not None:
            raise ProgressEventError("routing evidence is non-progress decision evidence")
    if event_kind is ProgressEventKind.USER_STEERING_ACCEPTED and not steering_receipt_ids:
        raise ProgressEventError("accepted steering requires an exact steering receipt")
    expected_observation = _validate_expected_observation(payload.get("expected_observation"))

    canonical = dict(payload)
    if role_manifest is not None:
        canonical["topology"] = {**topology, "role_manifest": role_manifest}
    if expected_observation is None:
        canonical.pop("expected_observation", None)
    else:
        canonical["expected_observation"] = expected_observation
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_PROGRESS_EVENT_BYTES:
        raise ProgressEventError("progress material event exceeds the size guard")
    semantic = dict(canonical)
    semantic.pop("event_id", None)
    semantic.pop("observed_at_ms", None)
    semantic_digest = hashlib.sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return ProgressMaterialEvent(
        schema_version=schema_version, event_id=event_id, dedupe_key=dedupe_key,
        portfolio_id=portfolio_id, project_id=project_id, ctrl_id=ctrl_id,
        milestone_id=milestone_id, block_id=block_id, task_id=task_id,
        owner_id=owner_id, scope_version=scope_version,
        parent_block_id=parent_block_id, dependency_ids=dependency_ids,
        predecessor_block_ids=predecessor_block_ids, split_from=split_from,
        merged_from=merged_from, event_kind=event_kind,
        lifecycle_state=lifecycle_state, measurement_state=measurement_state,
        committed_weight=committed_weight,
        admitted_proof_weight=admitted_proof_weight,
        weight_basis_receipt_ids=weight_basis_receipt_ids,
        proof_required_classes=proof_required_classes,
        proof_receipt_ids=proof_receipt_ids, claim_limit=claim_limit,
        eta_start_ms=eta_start_ms, eta_end_ms=eta_end_ms,
        eta_confidence=eta_confidence, eta_receipt_ids=eta_receipt_ids,
        attempt=attempt, rework_count=rework_count,
        invalidated_receipt_ids=invalidated_receipt_ids,
        custody_surface=custody_surface, custody_receipt_id=custody_receipt_id,
        steering_receipt_ids=steering_receipt_ids,
        material_update_sentence=material_update_sentence, flags=flags,
        provenance=provenance, source=source, observed_at_ms=observed_at_ms,
        causation_id=causation_id, parent_event_id=parent_event_id,
        topology_node_kind=topology_node_kind,
        input_receipt_ids=input_receipt_ids,
        dispatch_receipt_id=dispatch_receipt_id,
        completion_receipt_id=completion_receipt_id,
        cost_receipt_ids=cost_receipt_ids,
        release_receipt_ids=release_receipt_ids,
        role_manifest=role_manifest,
        routing_evidence=routing_evidence,
        expected_observation=expected_observation,
        digest=hashlib.sha256(encoded).hexdigest(),
        semantic_digest=semantic_digest,
    )


def validate_progress_material_event(payload: Any) -> ProgressMaterialEvent:
    return _validate_progress_material_event(payload)


def role_material_event(
    action: str,
    *,
    event_id: str,
    dedupe_key: str,
    role_id: str,
    manifest: Mapping[str, Any],
    expected_active_version: str | None,
    assignment_task_id: str | None,
    provenance: str,
    observed_at_ms: int,
) -> dict[str, Any]:
    try:
        kind = ProgressEventKind(action)
    except ValueError as error:
        raise ProgressEventError("role manifest action is invalid") from error
    if kind not in {
        ProgressEventKind.ROLE_MANIFEST_CREATE, ProgressEventKind.ROLE_MANIFEST_REVISE,
        ProgressEventKind.ROLE_MANIFEST_RESET, ProgressEventKind.ROLE_ASSIGNMENT_BOUND,
    }:
        raise ProgressEventError("role manifest action is invalid")
    role_id = _safe_id(role_id, "role id")
    task_id = assignment_task_id or f"role:{role_id}"
    payload = {
        "schema_version": 2, "event_id": event_id, "dedupe_key": dedupe_key,
        "portfolio_id": "swarm", "project_id": "swarm-role-manifests",
        "ctrl_id": "localhost-server", "milestone_id": "role-library",
        "block_id": role_id, "task_id": task_id, "owner_id": "localhost-server",
        "scope_version": 1, "parent_block_id": None, "dependency_ids": [],
        "lineage": {"predecessor_block_ids": [], "split_from": None, "merged_from": []},
        "event_kind": kind.value, "lifecycle_state": "ACTIVE",
        "measurement": {"state": "UNMEASURED", "committed_weight": None, "admitted_proof_weight": 0, "basis_receipt_ids": []},
        "proof": {"required_classes": [], "receipt_ids": [], "claim_limit": "Role metadata is not task authority or acceptance proof."},
        "eta": {"start_ms": None, "end_ms": None, "confidence": None, "basis_receipt_ids": []},
        "rework": {"attempt": 1, "count": 0, "invalidated_receipt_ids": []},
        "custody": {"surface": "server:role-manifests", "receipt_id": event_id},
        "steering_receipt_ids": [], "material_update_sentence": None, "flags": [],
        "provenance": provenance, "source": "swarm_runtime", "observed_at_ms": observed_at_ms,
        "causation_id": None, "parent_event_id": None,
        "topology": {
            "node_kind": "TASK", "input_receipt_ids": [], "dispatch_receipt_id": None,
            "completion_receipt_id": None, "cost_receipt_ids": [], "release_receipt_ids": [],
            "role_manifest": {
                "role_id": role_id, "expected_active_version": expected_active_version,
                "assignment_task_id": assignment_task_id, "manifest": dict(manifest),
            },
        },
    }
    return validate_progress_material_event(payload).canonical_payload()


def _empty_progress_projection() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "cursor": {"event_seq": 0, "event_id": None, "event_digest": None},
        "events": {},
        "dedupe": {},
        "scopes": {},
        "blocks": {},
        "latest_material_signatures": {},
        "topology_conflicts": [],
        "role_manifests": {},
        "role_assignments": {},
        "request_event_digests": {},
        "request_dedupe_digests": {},
        "request_lifecycles": {},
        "handoff_event_digests": {},
        "handoff_dedupe_digests": {},
        "task_handoffs": {},
        "task_handoff_leases": {},
        "expected_receipts": {},
        "connector_receipts": {},
        "connector_command_ids": {},
        "connector_receipt_ids": {},
    }

_LIFECYCLE_TRANSITIONS: dict[ProgressLifecycle, frozenset[ProgressLifecycle]] = {
    ProgressLifecycle.PLANNED: frozenset({ProgressLifecycle.PLANNED, ProgressLifecycle.READY, ProgressLifecycle.USER_PAUSED, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.READY: frozenset({ProgressLifecycle.READY, ProgressLifecycle.ACTIVE, ProgressLifecycle.WAITING_DEPENDENCY, ProgressLifecycle.WAITING_EXTERNAL, ProgressLifecycle.USER_PAUSED, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.ACTIVE: frozenset({ProgressLifecycle.ACTIVE, ProgressLifecycle.WAITING_DEPENDENCY, ProgressLifecycle.WAITING_EXTERNAL, ProgressLifecycle.RETRYING, ProgressLifecycle.REVIEW, ProgressLifecycle.INVALIDATED_REWORK, ProgressLifecycle.USER_PAUSED, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.WAITING_DEPENDENCY: frozenset({ProgressLifecycle.WAITING_DEPENDENCY, ProgressLifecycle.READY, ProgressLifecycle.ACTIVE, ProgressLifecycle.USER_PAUSED, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.WAITING_EXTERNAL: frozenset({ProgressLifecycle.WAITING_EXTERNAL, ProgressLifecycle.READY, ProgressLifecycle.ACTIVE, ProgressLifecycle.USER_PAUSED, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.RETRYING: frozenset({ProgressLifecycle.RETRYING, ProgressLifecycle.ACTIVE, ProgressLifecycle.WAITING_DEPENDENCY, ProgressLifecycle.WAITING_EXTERNAL, ProgressLifecycle.INVALIDATED_REWORK, ProgressLifecycle.USER_PAUSED, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.REVIEW: frozenset({ProgressLifecycle.REVIEW, ProgressLifecycle.VERIFIED, ProgressLifecycle.INVALIDATED_REWORK, ProgressLifecycle.USER_PAUSED, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.VERIFIED: frozenset({ProgressLifecycle.VERIFIED, ProgressLifecycle.ACCEPTED, ProgressLifecycle.INVALIDATED_REWORK, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.INVALIDATED_REWORK: frozenset({ProgressLifecycle.INVALIDATED_REWORK, ProgressLifecycle.READY, ProgressLifecycle.ACTIVE, ProgressLifecycle.USER_PAUSED, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.USER_PAUSED: frozenset({ProgressLifecycle.USER_PAUSED, ProgressLifecycle.READY, ProgressLifecycle.ACTIVE, ProgressLifecycle.WAITING_DEPENDENCY, ProgressLifecycle.WAITING_EXTERNAL, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.ACCEPTED: frozenset({ProgressLifecycle.ACCEPTED, ProgressLifecycle.INVALIDATED_REWORK, ProgressLifecycle.TOMBSTONED}),
    ProgressLifecycle.TOMBSTONED: frozenset({ProgressLifecycle.TOMBSTONED}),
}

_REQUEST_LIFECYCLE_TRANSITIONS: dict[LedgerLifecycleState, frozenset[LedgerLifecycleState]] = {
    LedgerLifecycleState.OFFERED: frozenset({LedgerLifecycleState.ACKNOWLEDGED}),
    LedgerLifecycleState.ACKNOWLEDGED: frozenset({LedgerLifecycleState.ADMITTED, LedgerLifecycleState.WAITING, LedgerLifecycleState.USER_PAUSED, LedgerLifecycleState.KEEP_OUT, LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.STALLED}),
    LedgerLifecycleState.ADMITTED: frozenset({LedgerLifecycleState.RUNNING, LedgerLifecycleState.RESULT_PENDING, LedgerLifecycleState.RETRYING, LedgerLifecycleState.WAITING, LedgerLifecycleState.USER_PAUSED, LedgerLifecycleState.KEEP_OUT, LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.STALLED}),
    LedgerLifecycleState.RUNNING: frozenset({LedgerLifecycleState.RUNNING, LedgerLifecycleState.RESULT_PENDING, LedgerLifecycleState.RETRYING, LedgerLifecycleState.WAITING, LedgerLifecycleState.USER_PAUSED, LedgerLifecycleState.KEEP_OUT, LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.STALLED}),
    LedgerLifecycleState.RESULT_PENDING: frozenset({LedgerLifecycleState.RUNNING, LedgerLifecycleState.RESULT_PENDING, LedgerLifecycleState.REVIEW_PENDING, LedgerLifecycleState.COMPLETE, LedgerLifecycleState.RETRYING, LedgerLifecycleState.WAITING, LedgerLifecycleState.USER_PAUSED, LedgerLifecycleState.KEEP_OUT, LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.STALLED}),
    LedgerLifecycleState.REVIEW_PENDING: frozenset({LedgerLifecycleState.COMPLETE, LedgerLifecycleState.RETRYING, LedgerLifecycleState.WAITING, LedgerLifecycleState.USER_PAUSED, LedgerLifecycleState.KEEP_OUT, LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.STALLED}),
    LedgerLifecycleState.RETRYING: frozenset({LedgerLifecycleState.RUNNING, LedgerLifecycleState.RESULT_PENDING, LedgerLifecycleState.COMPLETE, LedgerLifecycleState.WAITING, LedgerLifecycleState.USER_PAUSED, LedgerLifecycleState.KEEP_OUT, LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.STALLED}),
    LedgerLifecycleState.WAITING: frozenset({LedgerLifecycleState.WAITING, LedgerLifecycleState.RUNNING, LedgerLifecycleState.RESULT_PENDING, LedgerLifecycleState.COMPLETE, LedgerLifecycleState.RETRYING, LedgerLifecycleState.USER_PAUSED, LedgerLifecycleState.KEEP_OUT, LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.STALLED}),
    LedgerLifecycleState.USER_PAUSED: frozenset({LedgerLifecycleState.USER_PAUSED, LedgerLifecycleState.RUNNING, LedgerLifecycleState.WAITING, LedgerLifecycleState.COMPLETE}),
    LedgerLifecycleState.KEEP_OUT: frozenset({LedgerLifecycleState.KEEP_OUT, LedgerLifecycleState.RUNNING, LedgerLifecycleState.WAITING, LedgerLifecycleState.COMPLETE}),
    LedgerLifecycleState.NEEDS_AUTHORITY: frozenset({LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.RUNNING, LedgerLifecycleState.WAITING, LedgerLifecycleState.COMPLETE, LedgerLifecycleState.BLOCKED}),
    LedgerLifecycleState.STALLED: frozenset({LedgerLifecycleState.STALLED, LedgerLifecycleState.RUNNING, LedgerLifecycleState.RETRYING, LedgerLifecycleState.WAITING, LedgerLifecycleState.COMPLETE, LedgerLifecycleState.NEEDS_AUTHORITY, LedgerLifecycleState.BLOCKED}),
    LedgerLifecycleState.BLOCKED: frozenset({LedgerLifecycleState.BLOCKED}),
    LedgerLifecycleState.COMPLETE: frozenset({LedgerLifecycleState.COMPLETE}),
}

_TASK_HANDOFF_TRANSITIONS: dict[TaskHandoffEventKind, TaskHandoffEventKind] = {
    TaskHandoffEventKind.HANDOFF_DUE: TaskHandoffEventKind.HANDOFF_OFFERED,
    TaskHandoffEventKind.HANDOFF_OFFERED: TaskHandoffEventKind.HANDOFF_ACKNOWLEDGED,
    TaskHandoffEventKind.HANDOFF_ACKNOWLEDGED: TaskHandoffEventKind.CUSTODY_TRANSFERRED,
}


class ProgressFeedSubscription:
    """In-process event notification; HTTP/browser transport remains a separate gate."""

    def __init__(self, ledger: "Ledger", project_id: str, cursor: int, limit: int):
        self._ledger = ledger
        self.project_id = _safe_id(project_id, "project_id")
        self.cursor = _positive_int(cursor, "feed cursor", allow_zero=True)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
            raise ProgressEventError("feed limit must be between 1 and 10")
        self.limit = limit
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def next(self, timeout: float | None = None) -> dict[str, Any]:
        if self.closed:
            raise ProgressEventError("progress feed subscription is closed")
        snapshot = self._ledger.feed_snapshot(self.project_id, limit=self.limit, after_cursor=self.cursor)
        if snapshot["items"] or snapshot["stale_cursor"] or timeout == 0:
            self.cursor = int(snapshot["cursor"]["event_seq"] or self.cursor)
            return snapshot
        with self._ledger._condition:
            self._ledger._condition.wait(timeout)
        if self.closed:
            raise ProgressEventError("progress feed subscription is closed")
        snapshot = self._ledger.feed_snapshot(self.project_id, limit=self.limit, after_cursor=self.cursor)
        self.cursor = int(snapshot["cursor"]["event_seq"] or self.cursor)
        return snapshot


class Ledger:
    """Append-only material-event authority with a disposable compact projection."""

    def __init__(self, root: Path | str, *, host_custody_public_key: int | None = None):
        self.root = Path(root).expanduser().resolve()
        self._state = LockedPrivateState(self.root, PROGRESS_LEDGER_PATH)
        self.projection_path = self.root / PROGRESS_PROJECTION_PATH
        self._condition = Condition()
        self._retry_topology = RetryTopologyLedger()
        if host_custody_public_key is not None and (not isinstance(host_custody_public_key, int) or isinstance(host_custody_public_key, bool) or host_custody_public_key <= 1):
            raise ProgressEventError("host custody verifier requires a valid pinned public key")
        _install_ledger_custody_authority(self, host_custody_public_key)

    def retain_host_custody_receipt(self, receipt: HostCustodyReceipt) -> HostCustodyReceipt:
        """Retain one externally signed receipt without exposing mint or registry authority."""
        if not isinstance(receipt, HostCustodyReceipt):
            raise ProgressEventError("custody receipt requires the ledger's host-pinned signature verifier")
        return _retain_ledger_custody_receipt(self, receipt)

    def require_host_custody_receipt(
        self, receipt: HostCustodyReceipt | None, *, target_id: str, binding: str,
        issued_at: int | None = None, not_before: int | None = None,
    ) -> HostCustodyReceipt:
        if not isinstance(receipt, HostCustodyReceipt):
            raise ProgressEventError("event requires a retained host-verified custody receipt")
        if (
            not _ledger_custody_receipt_is_current(self, receipt)
            or receipt.mutation is not CustodyMutation.STATE
            or receipt.target_id != target_id
            or receipt.target_state_digest != binding
            or issued_at is not None and receipt.issued_at != issued_at
            or not_before is not None and receipt.issued_at < not_before
        ):
            raise ProgressEventError("event requires a retained host-verified custody receipt")
        return receipt

    @staticmethod
    def _decode_non_material_record(raw_event: Any, retained_digest: str) -> tuple[str, str, dict[str, Any], str] | None:
        if not isinstance(raw_event, dict) or raw_event.get("record_type") not in NON_MATERIAL_RECORD_TYPES:
            return None
        kind = str(raw_event["record_type"])
        if kind == "EXPECTED_RECEIPT":
            event = _validate_expected_receipt(raw_event)
            identity, digest = event["receipt_id"], _expected_receipt_digest(event)
        elif kind == "REQUEST_LIFECYCLE":
            event = _validate_retained_request_lifecycle_event(raw_event, retained_digest)
            identity, digest = event["event_id"], retained_digest
        elif kind == "TASK_HANDOFF":
            event = validate_task_handoff_event(raw_event)
            identity, digest = event["event_id"], _task_handoff_digest(event)
        else:
            event = _validate_connector_receipt(raw_event)
            identity, digest = event["receipt_id"], _connector_receipt_digest(event)
        if retained_digest != digest:
            raise ProgressEventError(f"{kind.casefold().replace('_', ' ')} ledger digest mismatch")
        return kind, identity, event, digest

    @staticmethod
    def _is_non_material_record(raw_event: Any) -> bool:
        return isinstance(raw_event, dict) and raw_event.get("record_type") in NON_MATERIAL_RECORD_TYPES

    @staticmethod
    def _apply_connector_receipt(projection: dict[str, Any], event: dict[str, Any], event_seq: int, event_digest: str) -> None:
        commands, command_ids, receipt_ids = (
            projection["connector_receipts"], projection["connector_command_ids"], projection["connector_receipt_ids"],
        )
        identity = (event["command_id"], event["command_digest"], event["project_id"], event["root_digest"], event["action"])
        command_binding = command_ids.get(event["command_id"])
        if command_binding is not None and tuple(command_binding) != (event["idempotency_key"], *identity):
            raise ProgressEventError("connector command_id conflicts with retained command")
        receipt_binding = receipt_ids.get(event["receipt_id"])
        if receipt_binding is not None:
            if receipt_binding != event_digest:
                raise ProgressEventError("connector receipt_id conflicts with retained event")
            return
        command = commands.get(event["idempotency_key"])
        if command is None:
            if event["status"] != "COMMAND" or event["receipt_index"] != 0:
                raise ProgressEventError("connector lifecycle must begin with COMMAND index zero")
            command = {"identity": list(identity), "terminal": False, "receipts": []}
            commands[event["idempotency_key"]] = command
            command_ids[event["command_id"]] = [event["idempotency_key"], *identity]
        elif tuple(command["identity"]) != identity:
            raise ProgressEventError("connector command identity conflicts with retained command")
        if command["terminal"]:
            raise ProgressEventError("connector terminal lifecycle is monotonic")
        if event["receipt_index"] != len(command["receipts"]):
            raise ProgressEventError("connector receipt index must append contiguously")
        previous = command["receipts"][-1]["status"] if command["receipts"] else None
        if command["receipts"] and event["observed_at_ms"] < command["receipts"][-1]["observed_at_ms"]:
            raise ProgressEventError("connector lifecycle observation time cannot regress")
        if previous is not None and not (
            previous == "COMMAND" and event["status"] in {"ACKNOWLEDGED", "UNSUPPORTED"}
            or previous == "ACKNOWLEDGED" and event["status"] in {"PROGRESS", "RESULT"}
            or previous == "PROGRESS" and event["status"] in {"PROGRESS", "RESULT"}
        ):
            raise ProgressEventError("connector lifecycle transition is invalid")
        command["receipts"].append({**event, "event_seq": event_seq, "event_digest": event_digest})
        receipt_ids[event["receipt_id"]] = event_digest
        command["terminal"] = event["status"] in CONNECTOR_TERMINAL_STATUSES
        projection["cursor"] = {"event_seq": event_seq, "event_id": event["receipt_id"], "event_digest": event_digest}

    @staticmethod
    def _record(event: ProgressMaterialEvent, event_seq: int) -> dict[str, Any]:
        return {
            "event_seq": event_seq,
            "event_digest": event.digest,
            "event": event.canonical_payload(),
        }

    @staticmethod
    def _block_key(event: ProgressMaterialEvent) -> str:
        return f"{event.project_id}:{event.block_id}"

    @staticmethod
    def _material_key(event: ProgressMaterialEvent) -> str:
        return f"{event.project_id}:{event.task_id}:{event.block_id}"

    @staticmethod
    def _material_signature(event: ProgressMaterialEvent) -> str:
        payload = {
            "project_id": event.project_id,
            "task_id": event.task_id,
            "block_id": event.block_id,
            "event_kind": event.event_kind.value,
            "lifecycle_state": event.lifecycle_state.value,
            "measurement_state": event.measurement_state.value,
            "committed_weight": event.committed_weight,
            "admitted_proof_weight": event.admitted_proof_weight,
            "proof_receipt_ids": event.proof_receipt_ids,
            "eta": (event.eta_start_ms, event.eta_end_ms, event.eta_confidence, event.eta_receipt_ids),
            "rework": (event.attempt, event.rework_count, event.invalidated_receipt_ids),
            "sentence": event.material_update_sentence,
            "flags": event.flags,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _apply_role_payload(projection: dict[str, Any], event: ProgressMaterialEvent, event_seq: int) -> None:
        payload = event.role_manifest
        if payload is None:
            return
        role_id, manifest = payload["role_id"], payload["manifest"]
        roles = projection["role_manifests"]
        role = roles.get(role_id)
        if event.event_kind is ProgressEventKind.ROLE_MANIFEST_CREATE:
            if role is not None:
                raise ProgressEventError("role manifest create cannot replace an existing role")
            role = {"active_version": None, "canonical_version": None, "versions": {}, "events": []}
            roles[role_id] = role
        elif role is None:
            role = {
                "active_version": payload["expected_active_version"],
                "canonical_version": None,
                "versions": {},
                "events": [],
            }
            roles[role_id] = role
        if event.event_kind is not ProgressEventKind.ROLE_MANIFEST_CREATE and role["active_version"] != payload["expected_active_version"]:
            raise ProgressEventError("role manifest expected active version is stale")
        retained = role["versions"].get(manifest["version"])
        if retained is not None and retained != manifest:
            raise ProgressEventError("role manifest version conflicts with retained content")
        role["versions"][manifest["version"]] = manifest
        if event.event_kind is ProgressEventKind.ROLE_ASSIGNMENT_BOUND:
            task_id = payload["assignment_task_id"]
            binding = projection["role_assignments"].get(task_id)
            if binding and (binding["role_id"], binding["manifest_version"]) != (role_id, manifest["version"]):
                raise ProgressEventError("task role assignment is already bound")
            projection["role_assignments"].setdefault(task_id, {
                "task_id": task_id,
                "role_id": role_id,
                "manifest_version": manifest["version"],
                "event_id": event.event_id,
                "event_seq": event_seq,
            })
        else:
            role["active_version"] = manifest["version"]
            if manifest["source"] == "builtin":
                role["canonical_version"] = manifest["version"]
        role["events"].append(event.event_id)

    @staticmethod
    def _apply_topology_record(projection: dict[str, Any], event: ProgressMaterialEvent, event_seq: int) -> None:
        events = projection["events"]
        dedupe = projection["dedupe"]
        conflict: dict[str, Any] | None = None
        if event.event_id in events:
            if events[event.event_id] == event.digest:
                return
            conflict = {
                "kind": "EVENT_ID",
                "identity": event.event_id,
                "retained_digest": events[event.event_id],
                "conflicting_digest": event.digest,
                "event_seq": event_seq,
            }
        elif event.dedupe_key in dedupe:
            if dedupe[event.dedupe_key] == event.semantic_digest:
                return
            conflict = {
                "kind": "DEDUPE_KEY",
                "identity": event.dedupe_key,
                "retained_digest": dedupe[event.dedupe_key],
                "conflicting_digest": event.semantic_digest,
                "event_seq": event_seq,
            }
        else:
            events[event.event_id] = event.digest
            dedupe[event.dedupe_key] = event.semantic_digest
        if conflict is not None:
            projection["topology_conflicts"].append(conflict)
        else:
            Ledger._apply_role_payload(projection, event, event_seq)
            if event.material_update_sentence is not None:
                projection["latest_material_signatures"][Ledger._material_key(event)] = Ledger._material_signature(event)
        projection["cursor"] = {
            "event_seq": event_seq,
            "event_id": event.event_id,
            "event_digest": event.digest,
        }

    @staticmethod
    def _apply_request_lifecycle(
        projection: dict[str, Any],
        payload: dict[str, Any],
        event_seq: int,
        *,
        event_digest: str | None = None,
        semantic_digest: str | None = None,
    ) -> None:
        event_digest = event_digest or _request_lifecycle_digest(payload)
        semantic_digest = semantic_digest or _request_lifecycle_digest(payload, semantic=True)
        event_id = payload["event_id"]
        dedupe_key = payload["dedupe_key"]
        retained_event = projection["request_event_digests"].get(event_id)
        retained_dedupe = projection["request_dedupe_digests"].get(dedupe_key)
        if retained_event is not None:
            if retained_event != event_digest:
                raise ProgressEventError("request lifecycle event identity conflicts with retained digest")
            return
        if retained_dedupe is not None:
            if retained_dedupe != semantic_digest:
                raise ProgressEventError("request lifecycle dedupe identity conflicts with retained content")
            return
        request_id = payload["request_id"]
        lifecycle_state = LedgerLifecycleState(payload["lifecycle_state"])
        current = projection["request_lifecycles"].get(request_id)
        if current is None:
            if lifecycle_state is not LedgerLifecycleState.OFFERED:
                raise ProgressEventError("request lifecycle must begin with OFFERED")
        else:
            if payload["parent_event_id"] != current["event_id"]:
                raise ProgressEventError("request lifecycle parent must bind the current retained event")
            if payload["stage_id"] != current["stage_id"] or payload["envelope_digest"] != current["envelope_digest"]:
                raise ProgressEventError("request lifecycle immutable envelope binding conflicts")
            if lifecycle_state not in _REQUEST_LIFECYCLE_TRANSITIONS[LedgerLifecycleState(current["lifecycle_state"])]:
                raise ProgressEventError("request lifecycle transition is invalid")
        projection["request_event_digests"][event_id] = event_digest
        projection["request_dedupe_digests"][dedupe_key] = semantic_digest
        projection["request_lifecycles"][request_id] = {
            "request_id": request_id,
            "stage_id": payload["stage_id"],
            "event_id": event_id,
            "event_digest": event_digest,
            "event_seq": event_seq,
            "envelope_digest": payload["envelope_digest"],
            "lifecycle_state": lifecycle_state.value,
            "record": payload["record"],
        }

    @staticmethod
    def _apply_task_handoff(projection: dict[str, Any], payload: dict[str, Any], event_seq: int) -> None:
        event_digest = _task_handoff_digest(payload)
        semantic_digest = _task_handoff_digest(payload, semantic=True)
        event_id, dedupe_key = payload["event_id"], payload["dedupe_key"]
        retained_event = projection["handoff_event_digests"].get(event_id)
        retained_dedupe = projection["handoff_dedupe_digests"].get(dedupe_key)
        if retained_event is not None:
            if retained_event != event_digest:
                raise ProgressEventError("task handoff event identity conflicts with retained digest")
            return
        if retained_dedupe is not None:
            if retained_dedupe != semantic_digest:
                raise ProgressEventError("task handoff dedupe identity conflicts with retained content")
            return
        handoff_id = payload["handoff_id"]
        event_kind = TaskHandoffEventKind(payload["event_kind"])
        current = projection["task_handoffs"].get(handoff_id)
        lease_key = f"{payload['task_id']}:{payload['lease_version']}"
        if current is None:
            if event_kind is not TaskHandoffEventKind.HANDOFF_DUE:
                raise ProgressEventError("task handoff must begin with HANDOFF_DUE")
            retained_handoff = projection["task_handoff_leases"].get(lease_key)
            if retained_handoff is not None and retained_handoff != handoff_id:
                raise ProgressEventError("task lease already binds a different handoff")
        else:
            if payload["parent_event_id"] != current["event_id"]:
                raise ProgressEventError("task handoff parent must bind the current retained event")
            expected = _TASK_HANDOFF_TRANSITIONS.get(TaskHandoffEventKind(current["event_kind"]))
            if event_kind is not expected:
                raise ProgressEventError("task handoff transition is invalid")
            immutable = ("goal_id", "task_id", "old_owner", "scope_version", "lease_version")
            if any(payload[key] != current[key] for key in immutable):
                raise ProgressEventError("task handoff immutable binding conflicts")
            if current["new_owner"] is not None and payload["new_owner"] != current["new_owner"]:
                raise ProgressEventError("task handoff target owner conflicts")
            if current["checkpoint_digest"] is not None and payload["checkpoint_digest"] != current["checkpoint_digest"]:
                raise ProgressEventError("task handoff checkpoint conflicts")
            if payload["observed_at_ms"] < current["observed_at_ms"]:
                raise ProgressEventError("task handoff observation cannot regress")
        projection["handoff_event_digests"][event_id] = event_digest
        projection["handoff_dedupe_digests"][dedupe_key] = semantic_digest
        projection["task_handoff_leases"][lease_key] = handoff_id
        projection["task_handoffs"][handoff_id] = {
            **payload,
            "event_digest": event_digest,
            "event_seq": event_seq,
        }
        projection["cursor"] = {"event_seq": event_seq, "event_id": event_id, "event_digest": event_digest}

    @staticmethod
    def _apply_expected_receipt(
        projection: dict[str, Any], receipt: Mapping[str, Any], event_seq: int, event_digest: str,
    ) -> None:
        payload = dict(receipt)
        receipt_id = payload["receipt_id"]
        retained = projection["expected_receipts"].get(receipt_id)
        if retained is not None:
            if retained["event_digest"] != event_digest:
                raise ProgressEventError("expected receipt identity conflicts with retained digest")
            return
        binding = tuple(payload[key] for key in (
            "goal_id", "task_id", "owner_id", "lease_version", "target_id", "artifact_digest",
        ))
        if any(
            tuple(item["receipt"][key] for key in (
                "goal_id", "task_id", "owner_id", "lease_version", "target_id", "artifact_digest",
            )) == binding
            for item in projection["expected_receipts"].values()
        ):
            raise ProgressEventError("owned outcome already has an immutable expected receipt")
        projection["expected_receipts"][receipt_id] = {
            "receipt": payload,
            "event_seq": event_seq,
            "event_digest": event_digest,
            "last_source_cursor": payload["source_cursor"],
            "result": {"status": "PENDING", "reason": None, "progress_advanced": False},
        }
        projection["cursor"] = {
            "event_seq": event_seq, "event_id": receipt_id, "event_digest": event_digest,
        }

    def _apply_expected_observation(
        self, projection: dict[str, Any], observation: Mapping[str, Any], *, event_seq: int,
        event_id: str, event_digest: str, event_kind: str, due_event: str,
        due_generation: int, task_id: str, goal_id: str, owner_id: str,
        lease_version: int, evidence_receipt_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        retained = projection["expected_receipts"].get(observation["expected_receipt_id"])
        if retained is None:
            return {
                "expected_receipt_id": observation["expected_receipt_id"], "status": "ATTENTION",
                "reason": "MISSING_EXPECTED_RECEIPT", "event_id": event_id,
                "event_seq": event_seq, "progress_advanced": False,
            }
        expected = retained["receipt"]
        if retained["result"]["status"] == "MATCHED":
            return {
                "expected_receipt_id": expected["receipt_id"], "status": "MATCHED",
                "reason": None, "event_id": event_id, "event_seq": event_seq,
                "progress_advanced": False, "matched_event_id": retained["result"]["event_id"],
            }
        binding_reason = None
        for actual, wanted, mismatch in (
            (event_kind, expected["expected_event_kind"], "WRONG_EVENT_KIND"),
            (due_event, expected["due_event"], "WRONG_DUE_EVENT"),
            (due_generation, expected["due_generation"], "WRONG_DUE_GENERATION"),
            (task_id, expected["task_id"], "WRONG_TASK"),
            (goal_id, expected["goal_id"], "WRONG_GOAL"),
            (observation["goal_id"], expected["goal_id"], "WRONG_GOAL"),
            (owner_id, expected["owner_id"], "WRONG_OWNER"),
            (observation["owner_id"], expected["owner_id"], "WRONG_OWNER"),
            (lease_version, expected["lease_version"], "WRONG_LEASE"),
            (observation["lease_version"], expected["lease_version"], "WRONG_LEASE"),
            (observation["target_id"], expected["target_id"], "WRONG_TARGET"),
            (observation["artifact_digest"], expected["artifact_digest"], "WRONG_ARTIFACT"),
        ):
            if actual != wanted:
                binding_reason = mismatch
                break
        reason = binding_reason or {
            "EMPTY": "EMPTY_OUTPUT", "TIMEOUT": "TIMEOUT", "HTTP_400": "HTTP_400",
            "MISSING_THREAD": "MISSING_THREAD", "REPLAY": "REPLAY",
        }.get(observation["outcome"])
        if binding_reason is None and observation["source_cursor"] <= retained["last_source_cursor"]:
            reason = reason or "STALE_CURSOR"
        if not tuple(dict.fromkeys((*evidence_receipt_ids, *observation["evidence_receipt_ids"]))):
            reason = reason or "MISSING_EVIDENCE"
        route_digest = observation["route_digest"]
        if binding_reason is None:
            retained["last_source_cursor"] = max(retained["last_source_cursor"], observation["source_cursor"])
        result = {
            "expected_receipt_id": expected["receipt_id"],
            "status": "ATTENTION" if reason else "MATCHED",
            "reason": reason, "event_id": event_id, "event_seq": event_seq,
            "progress_advanced": reason is None, "route_digest": route_digest,
        }
        if reason and binding_reason is None:
            try:
                outcome = RetryOutcome(observation["outcome"])
            except ValueError:
                outcome = RetryOutcome.FAILED
            decision = self._retry_topology.observe(
                action=route_digest, target=expected["target_id"], outcome=outcome,
                blocker_code=reason.casefold().replace("_", "-"),
            )
            result.update({
                "retry_action": decision.action.value,
                "equivalent_attempts": decision.equivalent_attempts,
                "different_route_required": decision.action in {
                    RetryTopologyAction.REASSESS_ROOT_CAUSE, RetryTopologyAction.STOP_REPEATED_TACTIC,
                },
            })
        retained["result"] = {**result, "event_digest": event_digest}
        return result

    def _apply_request_expected(
        self, projection: dict[str, Any], payload: Mapping[str, Any], event_seq: int, event_digest: str,
    ) -> dict[str, Any] | None:
        observation = payload.get("expected_observation")
        if observation is None:
            return None
        record = payload["record"]
        generation = record["transitions"][-1]["cursor"]["feed_sequence"]
        return self._apply_expected_observation(
            projection, observation, event_seq=event_seq, event_id=payload["event_id"],
            event_digest=event_digest, event_kind=payload["lifecycle_state"],
            due_event="TURN_COMPLETION", due_generation=generation,
            task_id=record["task_id"], goal_id=record["goal_id"],
            owner_id=record["accepted_owner"], lease_version=observation["lease_version"],
            evidence_receipt_ids=tuple(record["evidence_receipts"]),
        )

    def _apply_handoff_expected(
        self, projection: dict[str, Any], payload: Mapping[str, Any], event_seq: int, event_digest: str,
    ) -> dict[str, Any] | None:
        observation = payload.get("expected_observation")
        if observation is None:
            return None
        return self._apply_expected_observation(
            projection, observation, event_seq=event_seq, event_id=payload["event_id"],
            event_digest=event_digest, event_kind=payload["event_kind"],
            due_event="LEASE_EXPIRY", due_generation=payload["lease_version"],
            task_id=payload["task_id"], goal_id=payload["goal_id"],
            owner_id=payload["old_owner"], lease_version=payload["lease_version"],
            evidence_receipt_ids=(payload["receipt_id"],),
        )

    @staticmethod
    def _retain_event_identity_only(projection: dict[str, Any], event: ProgressMaterialEvent, event_seq: int) -> None:
        projection["events"][event.event_id] = event.digest
        projection["dedupe"][event.dedupe_key] = event.semantic_digest
        projection["cursor"] = {"event_seq": event_seq, "event_id": event.event_id, "event_digest": event.digest}

    def _apply(self, projection: dict[str, Any], event: ProgressMaterialEvent, event_seq: int) -> dict[str, Any] | None:
        check = None
        if event.expected_observation is not None:
            check = self._apply_expected_observation(
                projection,
                event.expected_observation,
                event_seq=event_seq,
                event_id=event.event_id,
                event_digest=event.digest,
                event_kind=event.event_kind.value,
                due_event="USER_STEER" if event.event_kind is ProgressEventKind.USER_STEERING_ACCEPTED else "MATERIAL_EVENT",
                due_generation=event.scope_version,
                task_id=event.task_id,
                goal_id=event.expected_observation["goal_id"],
                owner_id=event.owner_id,
                lease_version=event.expected_observation["lease_version"],
                evidence_receipt_ids=event.proof_receipt_ids,
            )
            if not check["progress_advanced"]:
                Ledger._retain_event_identity_only(projection, event, event_seq)
                return check
        if event.schema_version == 2:
            Ledger._apply_topology_record(projection, event, event_seq)
            return check
        events = projection["events"]
        dedupe = projection["dedupe"]
        if event.event_id in events:
            if events[event.event_id] == event.digest:
                return
            raise ProgressEventError("progress event identity conflicts with retained digest")
        if event.dedupe_key in dedupe:
            if dedupe[event.dedupe_key] == event.semantic_digest:
                return
            raise ProgressEventError("progress event dedupe identity conflicts with retained content")
        if event.parent_event_id is not None and event.parent_event_id not in events:
            raise ProgressEventError("progress event parent is not retained")

        scopes = projection["scopes"]
        current_scope = int(scopes.get(event.project_id, 0))
        if current_scope == 0 and event.scope_version != 1:
            raise ProgressEventError("first project scope_version must be 1")
        if event.scope_version < current_scope:
            raise ProgressEventError("stale progress scope_version cannot append")
        if event.scope_version > current_scope:
            if current_scope and (event.event_kind is not ProgressEventKind.SCOPE_REVISED or event.scope_version != current_scope + 1):
                raise ProgressEventError("scope revision must advance exactly one version")
            scopes[event.project_id] = event.scope_version

        block_key = Ledger._block_key(event)
        blocks = projection["blocks"]
        previous = blocks.get(block_key)
        known_blocks = {
            str(item["block_id"])
            for item in blocks.values()
            if item["project_id"] == event.project_id
        }
        references = tuple(filter(None, (
            event.parent_block_id, event.split_from, *event.dependency_ids,
            *event.predecessor_block_ids, *event.merged_from,
        )))
        if any(reference not in known_blocks and reference != event.block_id for reference in references):
            raise ProgressEventError("progress block reference is not retained in the same project")
        if previous is None and event.event_kind not in {ProgressEventKind.BLOCK_CREATED, ProgressEventKind.BLOCK_SPLIT, ProgressEventKind.BLOCK_MERGED}:
            raise ProgressEventError("new progress block requires a creation or lineage event")
        if previous is not None:
            if previous["portfolio_id"] != event.portfolio_id or previous["ctrl_id"] != event.ctrl_id or previous["task_id"] != event.task_id:
                raise ProgressEventError("progress block identity cannot be rebound")
            if previous["owner_id"] != event.owner_id and event.event_kind is not ProgressEventKind.TAKEOVER_STARTED:
                raise ProgressEventError("progress block owner transfer requires a typed takeover event")
            old_state = ProgressLifecycle(previous["lifecycle_state"])
            if event.lifecycle_state not in _LIFECYCLE_TRANSITIONS[old_state]:
                raise ProgressEventError("progress lifecycle transition is invalid")
            if event.observed_at_ms < int(previous["observed_at_ms"]):
                raise ProgressEventError("progress block observation cannot regress")
            if event.scope_version == int(previous["scope_version"]):
                old_admitted = int(previous["admitted_proof_weight"])
                if event.admitted_proof_weight < old_admitted and event.event_kind not in {ProgressEventKind.PROOF_INVALIDATED, ProgressEventKind.REWORK_REQUESTED}:
                    raise ProgressEventError("admitted proof weight can decrease only through invalidation or rework")

        block = {
            "portfolio_id": event.portfolio_id,
            "project_id": event.project_id,
            "ctrl_id": event.ctrl_id,
            "milestone_id": event.milestone_id,
            "block_id": event.block_id,
            "task_id": event.task_id,
            "owner_id": event.owner_id,
            "scope_version": event.scope_version,
            "parent_block_id": event.parent_block_id,
            "dependency_ids": list(event.dependency_ids),
            "predecessor_block_ids": list(event.predecessor_block_ids),
            "split_from": event.split_from,
            "merged_from": list(event.merged_from),
            "lifecycle_state": event.lifecycle_state.value,
            "measurement_state": event.measurement_state.value,
            "committed_weight": event.committed_weight,
            "admitted_proof_weight": event.admitted_proof_weight,
            "weight_basis_receipt_ids": list(event.weight_basis_receipt_ids),
            "proof_required_classes": list(event.proof_required_classes),
            "proof_receipt_ids": list(event.proof_receipt_ids),
            "claim_limit": event.claim_limit,
            "eta": {
                "start_ms": event.eta_start_ms,
                "end_ms": event.eta_end_ms,
                "confidence": event.eta_confidence,
                "basis_receipt_ids": list(event.eta_receipt_ids),
            },
            "attempt": event.attempt,
            "rework_count": event.rework_count,
            "invalidated_receipt_ids": list(event.invalidated_receipt_ids),
            "custody": {"surface": event.custody_surface, "receipt_id": event.custody_receipt_id},
            "steering_receipt_ids": list(event.steering_receipt_ids),
            "flags": list(event.flags),
            "latest_event_id": event.event_id,
            "latest_event_seq": event_seq,
            "latest_event_digest": event.digest,
            "observed_at_ms": event.observed_at_ms,
        }
        blocks[block_key] = block
        events[event.event_id] = event.digest
        dedupe[event.dedupe_key] = event.semantic_digest
        if event.material_update_sentence is not None:
            projection["latest_material_signatures"][Ledger._material_key(event)] = Ledger._material_signature(event)
        projection["cursor"] = {"event_seq": event_seq, "event_id": event.event_id, "event_digest": event.digest}
        return check

    def _replay_unlocked(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        projection = _empty_progress_projection()
        self._retry_topology = RetryTopologyLedger()
        records: list[dict[str, Any]] = []
        payload = self._state.read_bytes_unlocked()
        for expected_seq, raw_line in enumerate(payload.splitlines(), 1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ProgressEventError("progress ledger contains malformed JSON") from error
            if not isinstance(record, dict) or set(record) != {"event_seq", "event_digest", "event"}:
                raise ProgressEventError("progress ledger record schema is invalid")
            if record["event_seq"] != expected_seq:
                raise ProgressEventError("progress ledger sequence is not contiguous")
            raw_event = record["event"]
            replayed_record = record
            decoded = self._decode_non_material_record(raw_event, record["event_digest"])
            if decoded is not None:
                kind, identity, event, event_digest = decoded
                if kind == "EXPECTED_RECEIPT":
                    self._apply_expected_receipt(projection, event, expected_seq, event_digest)
                elif kind == "REQUEST_LIFECYCLE":
                    self._apply_request_lifecycle(
                        projection, event, expected_seq, event_digest=event_digest,
                        semantic_digest=_request_lifecycle_digest(raw_event, semantic=True),
                    )
                    self._apply_request_expected(projection, event, expected_seq, event_digest)
                    replayed_record = {**record, "event": event}
                elif kind == "TASK_HANDOFF":
                    self._apply_task_handoff(projection, event, expected_seq)
                    self._apply_handoff_expected(projection, event, expected_seq, event_digest)
                else:
                    self._apply_connector_receipt(projection, event, expected_seq, event_digest)
            else:
                event = _validate_progress_material_event(
                    raw_event,
                    retained_event=(expected_seq, record["event_digest"]),
                )
                self._apply(projection, event, expected_seq)
            records.append(replayed_record)
        return projection, records

    def _write_projection_unlocked(self, projection: dict[str, Any]) -> None:
        encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        self.projection_path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=self.projection_path.parent, prefix=".progress-", suffix=".json", delete=False) as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, self.projection_path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def append_expected_receipt(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        receipt = _validate_expected_receipt(dict(payload))
        canonical = receipt
        event_digest = _expected_receipt_digest(canonical)
        with self._state.locked():
            projection, records = self._replay_unlocked()
            retained = projection["expected_receipts"].get(receipt["receipt_id"])
            if retained is not None:
                if retained["event_digest"] != event_digest:
                    raise ProgressEventError("expected receipt identity conflicts with retained digest")
                return {"status": "unchanged", "cursor": {"event_seq": retained["event_seq"], "event_id": receipt["receipt_id"], "event_digest": event_digest}, "event_digest": event_digest}
            event_seq = len(records) + 1
            self._apply_expected_receipt(projection, receipt, event_seq, event_digest)
            record = {"event_seq": event_seq, "event_digest": event_digest, "event": canonical}
            line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            self._state.path.parent.mkdir(parents=True, exist_ok=True)
            with self._state.path.open("ab") as handle:
                handle.write(line); handle.flush(); os.fsync(handle.fileno())
            self._write_projection_unlocked(projection)
        with self._condition:
            self._condition.notify_all()
        return {"status": "appended", "cursor": projection["cursor"], "event_digest": event_digest, "bytes": len(line)}

    def append_connector_receipt(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        event = _validate_connector_receipt(dict(payload))
        event_digest = _connector_receipt_digest(event)
        with self._state.locked():
            projection, records = self._replay_unlocked()
            command = projection["connector_receipts"].get(event["idempotency_key"])
            if command is not None:
                retained = next((item for item in command["receipts"] if item["receipt_id"] == event["receipt_id"]), None)
                if retained is not None:
                    if retained["event_digest"] != event_digest:
                        raise ProgressEventError("connector receipt identity conflicts with retained digest")
                    return {"status": "unchanged", "cursor": {"event_seq": retained["event_seq"], "event_id": event["receipt_id"], "event_digest": event_digest}, "event_digest": event_digest}
            event_seq = len(records) + 1
            trial = json.loads(json.dumps(projection, sort_keys=True))
            decoded = self._decode_non_material_record(event, event_digest)
            assert decoded is not None
            kind, identity, canonical, digest = decoded
            self._apply_connector_receipt(trial, canonical, event_seq, digest)
            record = {"event_seq": event_seq, "event_digest": event_digest, "event": event}
            line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            self._state.path.parent.mkdir(parents=True, exist_ok=True)
            with self._state.path.open("ab") as handle:
                handle.write(line); handle.flush(); os.fsync(handle.fileno())
            projection = trial
            self._write_projection_unlocked(projection)
        with self._condition:
            self._condition.notify_all()
        return {"status": "appended", "cursor": projection["cursor"], "event_digest": event_digest, "bytes": len(line)}

    def append(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        event = validate_progress_material_event(dict(payload))
        with self._state.locked():
            projection, records = self._replay_unlocked()
            conflicted = False
            retained_digest = projection["events"].get(event.event_id)
            if retained_digest is not None:
                if retained_digest != event.digest:
                    if event.schema_version == 1 or event.role_manifest is not None:
                        raise ProgressEventError("progress event identity conflicts with retained digest")
                    conflicted = True
                else:
                    return {"status": "unchanged", "cursor": projection["cursor"], "event_digest": event.digest}
            retained_semantic = projection["dedupe"].get(event.dedupe_key)
            if retained_semantic is not None:
                if retained_semantic != event.semantic_digest:
                    if event.schema_version == 1 or event.role_manifest is not None:
                        raise ProgressEventError("progress event dedupe identity conflicts with retained content")
                    conflicted = True
                elif not conflicted:
                    return {"status": "unchanged", "cursor": projection["cursor"], "event_digest": event.digest}
            if not conflicted and event.material_update_sentence is not None:
                signature = self._material_signature(event)
                if projection["latest_material_signatures"].get(self._material_key(event)) == signature:
                    return {"status": "unchanged", "cursor": projection["cursor"], "event_digest": event.digest}
            event_seq = len(records) + 1
            record = self._record(event, event_seq)
            line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            expected_check = self._apply(projection, event, event_seq)
            self._state.path.parent.mkdir(parents=True, exist_ok=True)
            with self._state.path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            self._write_projection_unlocked(projection)
        with self._condition:
            self._condition.notify_all()
        result = {
            "status": "conflicted" if conflicted else "appended",
            "cursor": projection["cursor"],
            "event_digest": event.digest,
            "bytes": len(line),
        }
        if expected_check is not None:
            result["expected_check"] = expected_check
        return result

    def append_admitted(self, payload: Mapping[str, Any], *, task: Task, actor: Role, operation: OperationClass, actor_id: str, lease_version: int) -> dict[str, Any]:
        """Append through the role gate; validation and authorization precede every write."""
        event = validate_progress_material_event(dict(payload))
        if event.task_id != task.id or event.owner_id != task.owner:
            raise ProgressEventError("role-gated Ledger admission conflicts with task or owner custody")
        if role_gate(actor, task, operation, actor_id=actor_id, lease_version=lease_version) is not RoleGateDecision.ALLOW:
            raise ProgressEventError("role gate denied Ledger admission")
        return self.append(payload)

    def append_request_lifecycle(self, payload: Mapping[str, Any], *, custody_receipt: HostCustodyReceipt | None = None) -> dict[str, Any]:
        event = validate_request_lifecycle_event(dict(payload))
        if event["lifecycle_state"] == LedgerLifecycleState.BLOCKED.value:
            self.require_host_custody_receipt(custody_receipt, target_id=event["request_id"], binding=request_blocked_release_binding(event), issued_at=event["release_issued_at_ms"])
        event_digest = _request_lifecycle_digest(event)
        semantic_digest = _request_lifecycle_digest(event, semantic=True)
        with self._state.locked():
            projection, records = self._replay_unlocked()
            if event["lifecycle_state"] == LedgerLifecycleState.BLOCKED.value:
                retained = [item["event"] for item in records if isinstance(item.get("event"), dict) and item["event"].get("record_type") == "REQUEST_LIFECYCLE" and item["event"].get("request_id") == event["request_id"] and item["event"].get("lifecycle_state") == LedgerLifecycleState.STALLED.value]
                retained_routes = {route for item in retained for route in item["route_receipt_ids"]}
                retained_permitted = {route for item in retained for route in item["permitted_route_ids"]}
                retained_turns = {receipt for item in retained for receipt in item["failed_goal_turn_receipt_ids"]}
                if len(retained_routes) < 3 or len(retained_turns) < 3 or retained_routes != retained_permitted or retained_routes != set(event["route_receipt_ids"]) or retained_permitted != set(event["permitted_route_ids"]) or retained_turns != set(event["failed_goal_turn_receipt_ids"]):
                    raise ProgressEventError("terminal BLOCKED requires matching retained distinct failed goal turns and complete permitted-route exhaustion")
            retained_event = projection["request_event_digests"].get(event["event_id"])
            if retained_event is not None:
                if retained_event != event_digest:
                    raise ProgressEventError("request lifecycle event identity conflicts with retained digest")
                retained = next(item for item in records if item["event_digest"] == event_digest)
                return {"status": "unchanged", "cursor": {"event_seq": retained["event_seq"], "event_id": event["event_id"], "event_digest": event_digest}, "event_digest": event_digest}
            retained_dedupe = projection["request_dedupe_digests"].get(event["dedupe_key"])
            if retained_dedupe is not None:
                if retained_dedupe != semantic_digest:
                    raise ProgressEventError("request lifecycle dedupe identity conflicts with retained content")
                retained = next(item for item in records if isinstance(item["event"], dict) and item["event"].get("dedupe_key") == event["dedupe_key"])
                return {"status": "unchanged", "cursor": {"event_seq": retained["event_seq"], "event_id": retained["event"]["event_id"], "event_digest": retained["event_digest"]}, "event_digest": retained["event_digest"]}
            event_seq = len(records) + 1
            self._apply_request_lifecycle(projection, event, event_seq)
            expected_check = self._apply_request_expected(projection, event, event_seq, event_digest)
            record = {"event_seq": event_seq, "event_digest": event_digest, "event": event}
            line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            self._state.path.parent.mkdir(parents=True, exist_ok=True)
            with self._state.path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            self._write_projection_unlocked(projection)
        with self._condition:
            self._condition.notify_all()
        result = {"status": "appended", "cursor": {"event_seq": event_seq, "event_id": event["event_id"], "event_digest": event_digest}, "event_digest": event_digest, "bytes": len(line)}
        if expected_check is not None:
            result["expected_check"] = expected_check
        return result

    def append_task_handoff(self, payload: Mapping[str, Any], *, custody_receipt: HostCustodyReceipt | None = None) -> dict[str, Any]:
        event = validate_task_handoff_event(dict(payload))
        if event["event_kind"] in {TaskHandoffEventKind.HANDOFF_DUE.value, TaskHandoffEventKind.HANDOFF_ACKNOWLEDGED.value}:
            self.require_host_custody_receipt(custody_receipt, target_id=event["task_id"], binding=task_handoff_host_binding(event), issued_at=event["host_issued_at_ms"])
        event_digest = _task_handoff_digest(event)
        semantic_digest = _task_handoff_digest(event, semantic=True)
        with self._state.locked():
            projection, records = self._replay_unlocked()
            retained_event = projection["handoff_event_digests"].get(event["event_id"])
            if retained_event is not None:
                if retained_event != event_digest:
                    raise ProgressEventError("task handoff event identity conflicts with retained digest")
                retained = next(item for item in records if item["event_digest"] == event_digest)
                return {"status": "unchanged", "cursor": {"event_seq": retained["event_seq"], "event_id": event["event_id"], "event_digest": event_digest}, "event_digest": event_digest}
            retained_dedupe = projection["handoff_dedupe_digests"].get(event["dedupe_key"])
            if retained_dedupe is not None:
                if retained_dedupe != semantic_digest:
                    raise ProgressEventError("task handoff dedupe identity conflicts with retained content")
                retained = next(item for item in records if isinstance(item["event"], dict) and item["event"].get("dedupe_key") == event["dedupe_key"])
                return {"status": "unchanged", "cursor": {"event_seq": retained["event_seq"], "event_id": retained["event"]["event_id"], "event_digest": retained["event_digest"]}, "event_digest": retained["event_digest"]}
            event_seq = len(records) + 1
            self._apply_task_handoff(projection, event, event_seq)
            expected_check = self._apply_handoff_expected(projection, event, event_seq, event_digest)
            record = {"event_seq": event_seq, "event_digest": event_digest, "event": event}
            line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            self._state.path.parent.mkdir(parents=True, exist_ok=True)
            with self._state.path.open("ab") as handle:
                handle.write(line); handle.flush(); os.fsync(handle.fileno())
            self._write_projection_unlocked(projection)
        with self._condition:
            self._condition.notify_all()
        result = {"status": "appended", "cursor": {"event_seq": event_seq, "event_id": event["event_id"], "event_digest": event_digest}, "event_digest": event_digest, "bytes": len(line)}
        if expected_check is not None:
            result["expected_check"] = expected_check
        return result

    def project_task_handoffs(self) -> dict[str, Any]:
        with self._state.locked():
            projection, _ = self._replay_unlocked()
        rows = sorted(projection["task_handoffs"].values(), key=lambda item: int(item["event_seq"]))
        return {"records": json.loads(json.dumps(rows, sort_keys=True)), "event_count": len(projection["handoff_event_digests"]), "cursor": projection["cursor"]}

    def project_request_lifecycles(self) -> dict[str, Any]:
        with self._state.locked():
            projection, records = self._replay_unlocked()
        rows = sorted(projection["request_lifecycles"].values(), key=lambda item: int(item["event_seq"]))
        events = {
            item["event"]["event_id"]: {
                "event_digest": item["event_digest"],
                "event_seq": item["event_seq"],
                "request_id": item["event"]["request_id"],
                "lifecycle_state": item["event"]["lifecycle_state"],
            }
            for item in records
            if isinstance(item["event"], dict) and item["event"].get("record_type") == "REQUEST_LIFECYCLE"
        }
        return {"records": json.loads(json.dumps(rows, sort_keys=True)), "events": events, "event_count": len(events)}

    def project_role_manifests(self, builtins: tuple[dict[str, Any], ...]) -> dict[str, Any]:
        builtin_by_id = {manifest["id"]: validate_role_manifest(manifest) for manifest in builtins}
        if set(builtin_by_id) != set(BUILT_IN_PROFESSIONS) or len(builtin_by_id) != 24:
            raise ProgressEventError("role projection requires the exact 24 built-ins")
        with self._state.locked():
            projection, _ = self._replay_unlocked()
        roles = {
            role_id: {
                "active_version": state["active_version"],
                "canonical_version": state["canonical_version"],
                "versions": dict(state["versions"]),
                "events": list(state["events"]),
            }
            for role_id, state in projection["role_manifests"].items()
        }
        for role_id, builtin in builtin_by_id.items():
            role = roles.setdefault(role_id, {"active_version": None, "canonical_version": None, "versions": {}, "events": []})
            role["versions"].setdefault(builtin["version"], builtin)
            role["canonical_version"] = builtin["version"]
            active = role["versions"].get(role["active_version"])
            if active is None or active["source"] == "builtin":
                role["active_version"] = builtin["version"]
        result = []
        for role_id in sorted(roles):
            role = roles[role_id]
            active = role["versions"].get(role["active_version"])
            if active is None:
                raise ProgressEventError("role projection has no active version")
            projected_active = {**active, "specializations": list(active.get("specializations", []))}
            result.append({
                **projected_active,
                "built_in": role_id in builtin_by_id,
                "active_version": role["active_version"],
                "canonical_version": role["canonical_version"],
                "override_active": active["source"] == "user_override",
                "versions": [{**role["versions"][version], "specializations": list(role["versions"][version].get("specializations", [])), "active": version == role["active_version"]} for version in sorted(role["versions"])],
                "source_event_ids": role["events"],
            })
        return {
            "schema_version": 1, "built_in_count": 24, "roles": result,
            "assignments": sorted(projection["role_assignments"].values(), key=lambda item: item["task_id"]),
            "cursor": projection["cursor"],
            "hierarchy_binding": {
                "project_field": "project_id", "ctrl_membership_field": "controller_ids",
                "task_identity_field": "id", "assignment_task_field": "task_id",
                "levels": ["PROJECT", "CTRL", "LEAD", "DOER"],
            },
            "command_contract": {
                "endpoint": "/api/role-manifests/commands",
                "commands": ["ROLE_MANIFEST_CREATE", "ROLE_MANIFEST_REVISE", "ROLE_MANIFEST_RESET"],
                "optimistic_concurrency_field": "expected_active_version",
                "avatar": {
                    "selection_field": "avatar_asset_digest",
                    "selection_commands": ["ROLE_MANIFEST_CREATE", "ROLE_MANIFEST_REVISE"],
                    "requires_retained_immutable_asset": True,
                    "generation_command": None,
                },
            },
            "claim_limit": "The browser projects server-owned ledger state; role metadata never transfers task authority or proves acceptance.",
        }

    def replay(self) -> dict[str, Any]:
        with self._state.locked():
            projection, _ = self._replay_unlocked()
            self._write_projection_unlocked(projection)
            return projection

    @staticmethod
    def _project_from_projection(project_id: str, projection: Mapping[str, Any]) -> dict[str, Any]:
        """Project completion from one already-replayed Ledger snapshot."""
        scope_version = int(projection["scopes"].get(project_id, 0))
        blocks = [
            block for block in projection["blocks"].values()
            if block["project_id"] == project_id
            and int(block["scope_version"]) == scope_version
            and block["lifecycle_state"] != ProgressLifecycle.TOMBSTONED.value
        ]
        measured = [block for block in blocks if block["committed_weight"] is not None]
        unmeasured = [block for block in blocks if block["committed_weight"] is None]
        denominator = sum(int(block["committed_weight"]) for block in measured)
        admitted = sum(int(block["admitted_proof_weight"]) for block in measured)
        status = "UNMEASURED" if not blocks or unmeasured or denominator <= 0 else "MEASURED"
        percent = None if status == "UNMEASURED" else round(admitted * 100 / denominator, 2)
        overlays = sorted({flag.upper() for block in blocks for flag in block["flags"] if flag in {"stale", "conflicted"}})
        return {
            "project_id": project_id,
            "scope_version": scope_version or None,
            "status": status,
            "percent": percent,
            "admitted_proof_weight": admitted,
            "committed_measured_weight": denominator,
            "unmeasured_block_count": len(unmeasured),
            "provisional_block_count": sum(block["measurement_state"] == ProgressMeasurementState.PARTIAL.value for block in blocks),
            "rework_weight": sum(int(block["committed_weight"] or 0) for block in blocks if block["lifecycle_state"] == ProgressLifecycle.INVALIDATED_REWORK.value),
            "overlays": overlays,
            "blocks": sorted(blocks, key=lambda item: (item["milestone_id"], item["block_id"])),
            "cursor": projection["cursor"],
            "claim_limit": "Completion is admitted proof-weight over committed measured weight for one scope version; unmeasured work, narration, activity, tokens, and healthy liveness renewals contribute no percentage.",
        }

    def project(self, project_id: str) -> dict[str, Any]:
        project_id = _safe_id(project_id, "project_id")
        projection = self.replay()
        return self._project_from_projection(project_id, projection)

    def project_verified_yield(
        self,
        project_id: str,
        token_samples: list[Mapping[str, Any]],
        *,
        observed_after_ms: int,
        observed_before_ms: int,
        series_limit: int = MAX_YIELD_SERIES,
    ) -> dict[str, Any]:
        """Join current-scope proof deltas to bounded observed token receipts."""
        project_id = _safe_id(project_id, "project_id")
        observed_after_ms = _positive_int(observed_after_ms, "observed_after_ms", allow_zero=True)
        observed_before_ms = _positive_int(observed_before_ms, "observed_before_ms", allow_zero=True)
        if observed_before_ms < observed_after_ms:
            raise ProgressEventError("verified yield window is inverted")
        if not isinstance(series_limit, int) or isinstance(series_limit, bool) or not 1 <= series_limit <= MAX_YIELD_SERIES:
            raise ProgressEventError(f"verified yield series_limit must be between 1 and {MAX_YIELD_SERIES}")

        with self._state.locked():
            projection, records = self._replay_unlocked()
        scope_version = int(projection["scopes"].get(project_id, 0))
        blocks = {
            block_id: block
            for block_id, block in projection["blocks"].items()
            if block["project_id"] == project_id
            and int(block["scope_version"]) == scope_version
            and block["lifecycle_state"] != ProgressLifecycle.TOMBSTONED.value
        }
        block_ids = {str(block["block_id"]) for block in blocks.values()}
        events: list[tuple[int, ProgressMaterialEvent]] = []
        conflicts = 0
        for record in records:
            if self._is_non_material_record(record["event"]):
                continue
            event = validate_progress_material_event(record["event"])
            if event.project_id != project_id or event.scope_version != scope_version or event.block_id not in block_ids:
                continue
            canonical = (
                projection["events"].get(event.event_id) == event.digest
                and projection["dedupe"].get(event.dedupe_key) == event.semantic_digest
            )
            if not canonical:
                conflicts += 1
                continue
            events.append((int(record["event_seq"]), event))

        scope_started_at_ms = min((event.observed_at_ms for _, event in events), default=None)
        previous_admitted: dict[str, int] = {}
        proof_rows: list[dict[str, Any]] = []
        ownership: dict[str, list[tuple[int, str]]] = {}
        latest_by_task: dict[str, tuple[int, ProgressMaterialEvent]] = {}
        for event_seq, event in events:
            ownership.setdefault(event.task_id, []).append((event.observed_at_ms, event.owner_id))
            latest_by_task[event.task_id] = (event_seq, event)
            prior = previous_admitted.get(event.block_id, 0)
            delta = event.admitted_proof_weight - prior
            previous_admitted[event.block_id] = event.admitted_proof_weight
            if not observed_after_ms <= event.observed_at_ms <= observed_before_ms:
                continue
            scope_boundary = event.observed_at_ms == scope_started_at_ms
            if not delta and not scope_boundary:
                continue
            proof_rows.append({
                "observed_at_ms": event.observed_at_ms,
                "event_seq": event_seq,
                "event_id": event.event_id,
                "event_digest": event.digest,
                "task_id": event.task_id,
                "owner_id": event.owner_id,
                "gross_admitted_delta": max(0, delta),
                "invalidated_delta": max(0, -delta),
                "scope_start": scope_boundary,
            })

        retained_samples: dict[tuple[int, str], dict[str, Any]] = {}
        for raw in token_samples:
            if not isinstance(raw, Mapping):
                raise ProgressEventError("token sample must be an object")
            task_id = _safe_id(raw.get("task_id"), "token sample task_id")
            observed_at_ms = _positive_int(raw.get("observed_at_ms"), "token sample observed_at_ms", allow_zero=True)
            tokens = _positive_int(raw.get("tokens"), "token sample tokens", allow_zero=True)
            if not observed_after_ms <= observed_at_ms <= observed_before_ms:
                continue
            key = (observed_at_ms, task_id)
            retained = retained_samples.get(key)
            sample = {"observed_at_ms": observed_at_ms, "task_id": task_id, "tokens": tokens}
            if retained is not None and retained != sample:
                raise ProgressEventError("token sample identity conflicts with retained value")
            retained_samples[key] = sample
        samples = sorted(retained_samples.values(), key=lambda item: (item["observed_at_ms"], item["task_id"]))

        def committed_for(block_group: list[dict[str, Any]]) -> int | None:
            if not block_group or any(block["committed_weight"] is None for block in block_group):
                return None
            total = sum(int(block["committed_weight"]) for block in block_group)
            return total if total > 0 else None

        def owner_at(task_id: str, observed_at_ms: int) -> str | None:
            assignments = ownership.get(task_id, [])
            eligible = [item for item in assignments if item[0] <= observed_at_ms]
            if eligible:
                return max(eligible, key=lambda item: item[0])[1]
            return assignments[0][1] if assignments else None

        def yield_item(
            scope_type: str,
            scope_id: str,
            item_blocks: list[dict[str, Any]],
            item_proof: list[dict[str, Any]],
            item_samples: list[dict[str, Any]],
        ) -> dict[str, Any]:
            committed = committed_for(item_blocks)
            gross = sum(int(row["gross_admitted_delta"]) for row in item_proof)
            invalidated = sum(int(row["invalidated_delta"]) for row in item_proof)
            tokens = sum(int(row["tokens"]) for row in item_samples)
            expected_tasks = {str(block["task_id"]) for block in item_blocks}
            observed_tasks = {str(row["task_id"]) for row in item_samples}
            waiting = bool(item_blocks) and all(str(block["lifecycle_state"]).startswith("WAITING_") for block in item_blocks)
            complete_coverage = bool(expected_tasks) and expected_tasks <= observed_tasks
            if committed is None:
                state = "UNMEASURED"
            elif not item_samples and waiting and not gross and not invalidated:
                state = "NO_TOKEN_ACTIVITY"
            elif not item_samples or not complete_coverage or (tokens == 0 and (gross or invalidated)):
                state = "UNMEASURED"
            elif tokens == 0:
                state = "NO_TOKEN_ACTIVITY"
            else:
                state = "MEASURED"
            net_points = None if committed is None else round((gross - invalidated) * 100 / committed, 4)
            rework_drag = None if committed is None else round(invalidated * 100 / committed, 4)
            measured_yield = (
                round(net_points * YIELD_TOKEN_SCALE / tokens, 4)
                if state == "MEASURED" and net_points is not None and tokens > 0
                else None
            )
            confidence = "HIGH" if state == "MEASURED" and conflicts == 0 else (
                "PARTIAL" if item_samples or item_proof else "UNKNOWN"
            )
            points_by_time: dict[int, dict[str, Any]] = {}
            for row in item_proof:
                point = points_by_time.setdefault(row["observed_at_ms"], {
                    "observed_at_ms": row["observed_at_ms"], "scope_version": scope_version,
                    "scope_start": False, "gross_admitted_delta": 0, "invalidated_delta": 0,
                    "observed_tokens": 0, "material_sequence": None, "material_digest": None,
                })
                point["gross_admitted_delta"] += row["gross_admitted_delta"]
                point["invalidated_delta"] += row["invalidated_delta"]
                point["scope_start"] = point["scope_start"] or row["scope_start"]
                point["material_sequence"] = row["event_seq"]
                point["material_digest"] = row["event_digest"]
            for row in item_samples:
                point = points_by_time.setdefault(row["observed_at_ms"], {
                    "observed_at_ms": row["observed_at_ms"], "scope_version": scope_version,
                    "scope_start": False, "gross_admitted_delta": 0, "invalidated_delta": 0,
                    "observed_tokens": 0, "material_sequence": None, "material_digest": None,
                })
                point["observed_tokens"] += row["tokens"]
            cumulative_gross = cumulative_invalidated = cumulative_tokens = 0
            series = []
            for point in sorted(points_by_time.values(), key=lambda item: item["observed_at_ms"]):
                cumulative_gross += int(point["gross_admitted_delta"])
                cumulative_invalidated += int(point["invalidated_delta"])
                cumulative_tokens += int(point["observed_tokens"])
                cumulative_points = None if committed is None else round((cumulative_gross - cumulative_invalidated) * 100 / committed, 4)
                series.append({
                    **point,
                    "net_scope_points": cumulative_points,
                    "yield_per_100k": (
                        round(cumulative_points * YIELD_TOKEN_SCALE / cumulative_tokens, 4)
                        if cumulative_points is not None and cumulative_tokens > 0 else None
                    ),
                })
            latest_event = max((row["observed_at_ms"] for row in item_proof), default=None)
            latest_token = max((row["observed_at_ms"] for row in item_samples), default=None)
            return {
                "scope": {"type": scope_type, "id": scope_id, "project_id": project_id},
                "scope_version": scope_version or None,
                "committed_scope_weight": committed,
                "gross_admitted_delta": gross,
                "invalidated_delta": invalidated,
                "net_scope_points": net_points,
                "observed_tokens": tokens,
                "yield_per_100k": measured_yield,
                "measurement_state": state,
                "confidence": confidence,
                "freshness": {
                    "through_event_seq": projection["cursor"]["event_seq"],
                    "event_digest": projection["cursor"]["event_digest"],
                    "event_observed_at_ms": latest_event,
                    "token_sampled_at_ms": latest_token,
                },
                "rework_drag": rework_drag,
                "scope_started_at_ms": scope_started_at_ms,
                "series": series[-series_limit:],
                "series_truncated": len(series) > series_limit,
            }

        project_blocks = list(blocks.values())
        project_item = yield_item("project", project_id, project_blocks, proof_rows, samples)
        task_items = []
        for task_id in sorted({str(block["task_id"]) for block in project_blocks}):
            task_blocks = [block for block in project_blocks if block["task_id"] == task_id]
            task_items.append(yield_item(
                "task", task_id, task_blocks,
                [row for row in proof_rows if row["task_id"] == task_id],
                [row for row in samples if row["task_id"] == task_id],
            ))
        owner_ids = sorted({
            str(owner_id)
            for assignments in ownership.values()
            for _, owner_id in assignments
        })
        owner_items = []
        for owner_id in owner_ids:
            owner_tasks = {
                task_id for task_id, assignments in ownership.items()
                if any(assigned_owner == owner_id for _, assigned_owner in assignments)
            }
            owner_blocks = [block for block in project_blocks if str(block["task_id"]) in owner_tasks]
            owner_items.append(yield_item(
                "owner", owner_id, owner_blocks,
                [row for row in proof_rows if row["owner_id"] == owner_id],
                [row for row in samples if row["task_id"] in owner_tasks and owner_at(row["task_id"], row["observed_at_ms"]) == owner_id],
            ))

        attention = []
        for event_seq, event in latest_by_task.values():
            kind = None
            severity = "warning"
            if event.event_kind in {ProgressEventKind.PROOF_INVALIDATED, ProgressEventKind.REWORK_REQUESTED}:
                kind = "PROOF_INVALIDATED"
            elif event.event_kind is ProgressEventKind.LIVENESS_STALE:
                kind = "STALLED"
            elif event.event_kind is ProgressEventKind.RETRY_STARTED or event.lifecycle_state is ProgressLifecycle.RETRYING:
                kind = "RETRYING"
            elif event.lifecycle_state is ProgressLifecycle.WAITING_EXTERNAL and "blocked" in event.flags:
                kind, severity = "BLOCKER", "critical"
            elif event.eta_end_ms is not None and event.eta_end_ms < observed_before_ms and event.lifecycle_state not in {ProgressLifecycle.ACCEPTED, ProgressLifecycle.VERIFIED}:
                kind = "ETA_DRIFT"
            if kind is None:
                continue
            identity = {
                "kind": kind, "project_id": project_id, "task_id": event.task_id,
                "owner_id": event.owner_id, "event_seq": event_seq, "event_digest": event.digest,
            }
            attention.append({
                "id": hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
                "kind": kind,
                "project_id": project_id,
                "task_id": event.task_id,
                "owner_id": event.owner_id,
                "material_sequence": event_seq,
                "material_digest": event.digest,
                "observed_at_ms": event.observed_at_ms,
                "severity": severity,
                "sentence": {
                    "BLOCKER": "This task is waiting on an exact external release.",
                    "STALLED": "This task has no fresh material receipt.",
                    "RETRYING": "This task is executing a bounded retry.",
                    "PROOF_INVALIDATED": "This task has proof returned for correction.",
                    "ETA_DRIFT": "This task is past its receipt-backed ETA range.",
                }[kind],
                "action_target": {
                    "view": "projects", "project_id": project_id, "task_id": event.task_id,
                },
            })
        return {
            "schema_version": 1,
            "project": project_item,
            "tasks": task_items,
            "owners": owner_items,
            "attention_items": sorted(attention, key=lambda item: (item["material_sequence"], item["id"]), reverse=True),
            "conflict_count": conflicts,
            "claim_limit": "Verified yield is current-scope admitted proof delta per observed local token count; it is not completion percentage, billing, quality, productivity ranking, or provider usage.",
        }

    def project_topology(
        self,
        project_id: str,
        ctrl_id: str,
        *,
        through_cursor: int | None = None,
        effective_at_ms: int | None = None,
    ) -> dict[str, object]:
        """Pure schema-v2 one-CTRL graph replay over the canonical material stream."""
        project_id = _safe_id(project_id, "project_id")
        ctrl_id = _safe_id(ctrl_id, "ctrl_id")
        with self._state.locked():
            _, records = self._replay_unlocked()
        return self._project_topology_from_records(
            project_id,
            ctrl_id,
            records,
            through_cursor=through_cursor,
            effective_at_ms=effective_at_ms,
        )

    def _project_topology_from_records(
        self,
        project_id: str,
        ctrl_id: str,
        records: list[dict[str, Any]],
        *,
        through_cursor: int | None = None,
        effective_at_ms: int | None = None,
    ) -> dict[str, object]:
        """Replay one CTRL topology from an already accepted atomic record set."""
        maximum_cursor = len(records)
        cursor = maximum_cursor if through_cursor is None else _positive_int(
            through_cursor, "through_cursor", allow_zero=True
        )
        if cursor > maximum_cursor:
            raise ProgressEventError("through_cursor exceeds retained knowledge")

        known: list[tuple[int, ProgressMaterialEvent]] = []
        for record in records[:cursor]:
            if self._is_non_material_record(record["event"]):
                continue
            event = validate_progress_material_event(record["event"])
            if event.project_id == project_id and event.ctrl_id == ctrl_id:
                known.append((int(record["event_seq"]), event))
        if effective_at_ms is None:
            effective = max((event.observed_at_ms for _, event in known), default=None)
        else:
            effective = _positive_int(effective_at_ms, "effective_at_ms", allow_zero=True)
        eligible = [item for item in known if effective is None or item[1].observed_at_ms <= effective]

        def authority_digest(event: ProgressMaterialEvent, *, semantic: bool = False) -> str:
            payload = event.canonical_payload()
            payload.pop("material_update_sentence", None)
            if semantic:
                payload.pop("event_id", None)
                payload.pop("observed_at_ms", None)
            return hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

        conflicts: list[dict[str, Any]] = []
        excluded_event_ids: set[str] = set()
        by_event_id: dict[str, list[tuple[int, ProgressMaterialEvent]]] = {}
        for item in eligible:
            by_event_id.setdefault(item[1].event_id, []).append(item)
        for identity, items in sorted(by_event_id.items()):
            digests = sorted({authority_digest(event) for _, event in items})
            if len(digests) > 1:
                excluded_event_ids.add(identity)
                conflicts.append({"kind": "EVENT_ID", "identity": identity, "digests": digests})

        first_receipts: list[tuple[int, ProgressMaterialEvent]] = []
        for identity, items in by_event_id.items():
            if identity not in excluded_event_ids:
                first_receipts.append(min(items, key=lambda item: item[0]))
        by_dedupe: dict[str, list[tuple[int, ProgressMaterialEvent]]] = {}
        for item in first_receipts:
            by_dedupe.setdefault(item[1].dedupe_key, []).append(item)
        excluded_dedupe: set[str] = set()
        for identity, items in sorted(by_dedupe.items()):
            digests = sorted({authority_digest(event, semantic=True) for _, event in items})
            if len(digests) > 1:
                excluded_dedupe.add(identity)
                conflicts.append({"kind": "DEDUPE_KEY", "identity": identity, "digests": digests})
        factual = sorted(
            (item for item in first_receipts if item[1].dedupe_key not in excluded_dedupe),
            key=lambda item: (item[1].observed_at_ms, item[0], item[1].event_id),
        )

        event_ids = {event.event_id for _, event in factual}
        block_ids = {event.block_id for _, event in factual}
        retained_receipts: set[str] = set(event_ids)
        for _, event in factual:
            retained_receipts.update(event.weight_basis_receipt_ids)
            retained_receipts.update(event.proof_receipt_ids)
            retained_receipts.update(event.eta_receipt_ids)
            retained_receipts.update(event.invalidated_receipt_ids)
            retained_receipts.update(event.steering_receipt_ids)
            retained_receipts.update(event.cost_receipt_ids)
            retained_receipts.update(event.release_receipt_ids)
            retained_receipts.add(event.custody_receipt_id)
            if event.dispatch_receipt_id:
                retained_receipts.add(event.dispatch_receipt_id)
            if event.completion_receipt_id:
                retained_receipts.add(event.completion_receipt_id)

        unknown: set[str] = set()
        block_events: dict[str, list[tuple[int, ProgressMaterialEvent]]] = {}
        for item in factual:
            event = item[1]
            block_events.setdefault(event.block_id, []).append(item)
            if event.parent_event_id and event.parent_event_id not in event_ids:
                unknown.add(event.parent_event_id)
            unknown.update(receipt for receipt in event.input_receipt_ids if receipt not in retained_receipts)
            references = tuple(filter(None, (
                event.parent_block_id, event.split_from, *event.dependency_ids,
                *event.predecessor_block_ids, *event.merged_from,
            )))
            unknown.update(reference for reference in references if reference not in block_ids)

        latest_by_block = {
            block_id: max(items, key=lambda item: (item[1].observed_at_ms, item[0], item[1].event_id))
            for block_id, items in block_events.items()
        }
        nodes: list[dict[str, Any]] = [{
            "node_id": ctrl_id,
            "node_kind": "CTRL",
            "project_id": project_id,
            "ctrl_id": ctrl_id,
            "lifecycle_state": "OBSERVED",
            "source_event_ids": [],
        }]
        for block_id, (_, event) in sorted(latest_by_block.items()):
            references = tuple(filter(None, (
                event.parent_block_id, *event.dependency_ids, *event.predecessor_block_ids,
            )))
            node_unknown = sorted(reference for reference in references if reference not in block_ids)
            node_unknown.extend(sorted(receipt for receipt in event.input_receipt_ids if receipt not in retained_receipts))
            nodes.append({
                "node_id": block_id,
                "node_kind": event.topology_node_kind,
                "project_id": project_id,
                "ctrl_id": ctrl_id,
                "milestone_id": event.milestone_id,
                "task_id": event.task_id,
                "owner_id": event.owner_id,
                "scope_version": event.scope_version,
                "lifecycle_state": event.lifecycle_state.value,
                "attempt": event.attempt,
                "parent_block_id": event.parent_block_id,
                "dependency_ids": sorted(event.dependency_ids),
                "proof_receipt_ids": sorted(event.proof_receipt_ids),
                "dispatch_receipt_id": event.dispatch_receipt_id,
                "completion_receipt_id": event.completion_receipt_id,
                "cost_receipt_ids": sorted(event.cost_receipt_ids),
                "release_receipt_ids": sorted(event.release_receipt_ids),
                "routing_evidence": event.routing_evidence,
                "unknown_receipt_ids": sorted(set(node_unknown)),
                "latest_event_id": event.event_id,
                "latest_event_digest": authority_digest(event),
                "effective_at_ms": event.observed_at_ms,
                "source_event_ids": [item[1].event_id for item in block_events[block_id]],
            })

        edge_keys: set[tuple[str, str, str]] = set()
        for block_id, (_, event) in latest_by_block.items():
            if event.parent_block_id:
                edge_keys.add(("PARENT", event.parent_block_id, block_id))
            else:
                edge_keys.add(("CTRL", ctrl_id, block_id))
            for dependency in event.dependency_ids:
                edge_keys.add(("DEPENDENCY", dependency, block_id))
            for predecessor in event.predecessor_block_ids:
                edge_keys.add(("PREDECESSOR", predecessor, block_id))
            if event.split_from:
                edge_keys.add(("SPLIT_FROM", event.split_from, block_id))
            for merged in event.merged_from:
                edge_keys.add(("MERGED_FROM", merged, block_id))
        edges = [
            {"edge_kind": kind, "from_node_id": source, "to_node_id": target}
            for kind, source, target in sorted(edge_keys)
        ]

        terminal = {ProgressLifecycle.VERIFIED.value, ProgressLifecycle.ACCEPTED.value, ProgressLifecycle.TOMBSTONED.value}
        remaining = {
            block_id for block_id, (_, event) in latest_by_block.items()
            if event.lifecycle_state.value not in terminal
        }
        satisfied = {
            block_id for block_id, (_, event) in latest_by_block.items()
            if event.lifecycle_state.value in terminal
        }
        ready_waves: list[list[str]] = []
        while remaining:
            wave = sorted(
                block_id for block_id in remaining
                if set(latest_by_block[block_id][1].dependency_ids).issubset(satisfied)
                and not set(latest_by_block[block_id][1].dependency_ids) - block_ids
            )
            if not wave:
                break
            ready_waves.append(wave)
            remaining.difference_update(wave)
            satisfied.update(wave)

        dependency_map = {
            block_id: tuple(sorted(dep for dep in event.dependency_ids if dep in block_ids))
            for block_id, (_, event) in latest_by_block.items()
        }
        memo: dict[str, tuple[str, ...]] = {}
        visiting: set[str] = set()

        def longest_path(node_id: str) -> tuple[str, ...]:
            if node_id in memo:
                return memo[node_id]
            if node_id in visiting:
                return ()
            visiting.add(node_id)
            candidates = [longest_path(parent) for parent in dependency_map.get(node_id, ())]
            prefix = max(candidates, key=lambda path: (len(path), path), default=())
            visiting.remove(node_id)
            memo[node_id] = (*prefix, node_id)
            return memo[node_id]

        critical_nodes = max(
            (longest_path(block_id) for block_id in sorted(block_ids)),
            key=lambda path: (len(path), path),
            default=(),
        )
        source_event_ids = [
            event_id for _, event_id in sorted(
                {(seq, event.event_id) for seq, event in eligible},
                key=lambda item: (item[0], item[1]),
            )
        ]
        result: dict[str, object] = {
            "schema_version": 2,
            "project_id": project_id,
            "ctrl_id": ctrl_id,
            "through_cursor": cursor,
            "effective_at_ms": effective,
            "projection_digest": "",
            "nodes": sorted(nodes, key=lambda item: (item["node_kind"], item["node_id"])),
            "edges": edges,
            "ready_waves": ready_waves,
            "critical_path": {
                "node_ids": list(critical_nodes),
                "partial": bool(unknown or remaining),
            },
            "unknown_receipt_ids": sorted(unknown),
            "conflicts": sorted(conflicts, key=lambda item: (item["kind"], item["identity"])),
            "source_event_ids": source_event_ids,
        }
        digest_payload = dict(result)
        digest_payload.pop("projection_digest")
        result["projection_digest"] = hashlib.sha256(
            json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return result

    @staticmethod
    def unknown_project_progress_bundle(
        project_id: str,
        reason: str,
        *,
        ctrl_ids: tuple[str, ...] = (),
        cursor: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fail the whole project/progress bundle closed at one scope cursor."""
        project_id = _safe_id(project_id, "project_id")
        normalized_ctrl_ids = tuple(sorted(_safe_id(value, "ctrl_id") for value in ctrl_ids))
        accepted_cursor = None if cursor is None else json.loads(json.dumps(cursor, sort_keys=True))
        scope_binding = {
            "project_id": project_id,
            "ctrl_ids": list(normalized_ctrl_ids),
            "cursor": accepted_cursor,
        }
        resync_reasons = {
            "RESYNC_REQUIRED", "SOURCE_CURSOR_CHANGED", "INVALID_CURSOR",
            "TOPOLOGY_SCOPE_CONFLICT", "MIXED_SCOPE_REJECTED", "SOURCE_DIGEST_CONFLICT", "STALE_SOURCE",
        }
        queue_status = "RESYNC_REQUIRED" if reason in resync_reasons else "UNKNOWN"
        return {
            "project_id": project_id,
            "scope_version": None,
            "status": "UNKNOWN",
            "percent": None,
            "admitted_proof_weight": 0,
            "committed_measured_weight": 0,
            "unmeasured_block_count": 0,
            "provisional_block_count": 0,
            "rework_weight": 0,
            "overlays": ["CONFLICTED"] if queue_status == "RESYNC_REQUIRED" else [],
            "blocks": [],
            "cursor": accepted_cursor or {"event_seq": None, "event_id": None, "event_digest": None},
            "scope_binding": scope_binding,
            "progress_queue": {
                "schema_version": 1,
                "view_id": "view.project.progress",
                "renderer": "table",
                "project_id": project_id,
                "scope_binding": scope_binding,
                "accepted_cursor": accepted_cursor,
                "status": queue_status,
                "reason": reason,
                "available": False,
                "segments": [
                    {"segment_id": "segment.project.progress.active", "label": "Active", "order": 10, "rows": []},
                    {"segment_id": "segment.project.progress.queue", "label": "Queue", "order": 20, "rows": []},
                ],
                "source_digests": {},
                "claim_limit": (
                    "Progress, ETA, readiness, and recovery stay UNKNOWN until one exact CTRL-first "
                    "project scope and retained Ledger cursor can be accepted atomically."
                ),
            },
            "claim_limit": (
                "The accepted source bundle was unavailable or conflicted; no prior progress, ETA, "
                "readiness, or recovery value is carried across the rejected cursor."
            ),
        }

    @staticmethod
    def _progress_queue_recovery(
        release_event: ProgressMaterialEvent,
        event_by_id: Mapping[tuple[str, str], tuple[int, ProgressMaterialEvent]],
        scope_binding: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        routing = release_event.routing_evidence
        if (
            not isinstance(routing, dict)
            or routing.get("route") != "hard_blocked"
            or routing.get("release_event") != release_event.event_id
        ):
            return None
        recovery = routing.get("recovery")
        if not isinstance(recovery, dict):
            return None
        attempts = recovery.get("attempts")
        condition = recovery.get("release_condition")
        authority = recovery.get("responsible_authority")
        action = recovery.get("action")
        route_id = recovery.get("failed_route_id")
        if (
            not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 3
            or not isinstance(condition, str) or not condition.strip()
            or not isinstance(authority, str) or not authority.strip()
            or not isinstance(action, str) or not action
            or not isinstance(route_id, str) or not route_id
        ):
            return None
        evidence = [{"event_id": release_event.event_id, "event_digest": release_event.digest}]
        for receipt_id in recovery.get("evidence_receipt_ids", []):
            retained = event_by_id.get((release_event.ctrl_id, receipt_id))
            if retained is None:
                return None
            _, event = retained
            if event.project_id != release_event.project_id or event.task_id != release_event.task_id:
                return None
            evidence.append({"event_id": event.event_id, "event_digest": event.digest})
        detail = {
            "blocked_attempts": attempts,
            "blocked_release_condition": {
                "release_event_id": release_event.event_id,
                "release_event_digest": release_event.digest,
                "condition": condition.strip(),
            },
            "blocked_critical_path": bool(routing.get("critical_path")),
            "blocked_suggested_recovery": {
                "action": action,
                "route_id": route_id,
                "responsible_authority": authority.strip(),
                "evidence_receipt_refs": evidence,
            },
        }
        detail_digest = hashlib.sha256(
            json.dumps(detail, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            **detail,
            "detail_reference": {
                "detail_ref_id": f"progress-recovery:{release_event.event_id}",
                "scope_binding": json.loads(json.dumps(scope_binding, sort_keys=True)),
                "detail_digest": detail_digest,
            },
        }

    @staticmethod
    def classify_progress_queue_state(
        lifecycle: str,
        *,
        stale: bool,
        routing: Mapping[str, Any] | None,
        flags: set[str],
        task_id: str,
        owner_id: str,
        has_dependencies: bool,
        has_blocked_recovery: bool,
    ) -> tuple[str | None, bool]:
        """Map accepted typed lifecycle/routing facts without inventing readiness."""
        if stale:
            return "UNKNOWN", False
        hard_blocked = isinstance(routing, Mapping) and routing.get("route") == "hard_blocked"
        if hard_blocked:
            return ("SCOPED_BLOCKED", False) if has_blocked_recovery else ("UNKNOWN", False)
        if lifecycle in {"ACTIVE", "RUNNING", "RETRYING", "RESULT_PENDING"}:
            return None, False
        if lifecycle == "READY":
            accepted_route = (
                isinstance(routing, Mapping)
                and routing.get("route") in {"normal_subagent", "normal_task", "degraded_subagent"}
                and routing.get("selected_task_id") == task_id
                and routing.get("selected_owner") == owner_id
                and isinstance(routing.get("scope"), Mapping)
                and routing["scope"].get("task_id") == task_id
                and routing["scope"].get("owner_id") == owner_id
            )
            return ("QUEUED_NOT_STARTED", True) if accepted_route else ("UNKNOWN", False)
        if lifecycle == "WAITING_DEPENDENCY" and has_dependencies:
            return "WAITING_FOR_DEPENDENCY", False
        if lifecycle in {"REVIEW", "REVIEW_PENDING"}:
            return "REVIEW_GATED", False
        if lifecycle == "BLOCKED":
            return ("SCOPED_BLOCKED", False) if has_blocked_recovery else ("UNKNOWN", False)
        if lifecycle == "FAILED":
            return "FAILED", False
        if lifecycle == "WAITING_EXTERNAL" and isinstance(routing, Mapping):
            recovery = routing.get("recovery")
            if routing.get("route") == "hard_blocked":
                return ("SCOPED_BLOCKED", False) if has_blocked_recovery else ("UNKNOWN", False)
            if isinstance(recovery, Mapping) and recovery.get("state") == "WAITING_FOR_CAPACITY":
                return "WAITING_FOR_CAPACITY", False
            if isinstance(recovery, Mapping) and recovery.get("state") == "CONTROL_PATH_FAILURE":
                return "FAILED", False
        if flags & {"failed", "control_path_failure"}:
            return "FAILED", False
        return "UNKNOWN", False

    def project_progress_queue_bundle(
        self,
        project_id: str,
        ctrl_tasks: Mapping[str, Mapping[str, Mapping[str, str]]],
    ) -> dict[str, Any]:
        """Atomically project completion plus Active/Queue from one typed CTRL-first Ledger snapshot."""
        project_id = _safe_id(project_id, "project_id")
        if not isinstance(ctrl_tasks, Mapping) or not ctrl_tasks:
            return self.unknown_project_progress_bundle(project_id, "CTRL_SCOPE_UNAVAILABLE")
        normalized: dict[str, dict[str, dict[str, str]]] = {}
        task_ctrl: dict[str, str] = {}
        try:
            for raw_ctrl_id, raw_tasks in ctrl_tasks.items():
                ctrl_id = _safe_id(raw_ctrl_id, "ctrl_id")
                if not isinstance(raw_tasks, Mapping) or not raw_tasks:
                    raise ProgressEventError("CTRL scope requires at least one host-confirmed task")
                normalized[ctrl_id] = {}
                for raw_task_id, raw_presentation in raw_tasks.items():
                    task_id = _safe_id(raw_task_id, "task_id")
                    if task_id in task_ctrl and task_ctrl[task_id] != ctrl_id:
                        raise ProgressEventError("task identity cannot belong to more than one CTRL")
                    if not isinstance(raw_presentation, Mapping):
                        raise ProgressEventError("task presentation must be an object")
                    task_ctrl[task_id] = ctrl_id
                    normalized[ctrl_id][task_id] = {
                        "task_name": str(raw_presentation.get("task_name") or task_id),
                        "role": str(raw_presentation.get("role") or ""),
                    }
        except (ProgressEventError, TypeError, ValueError):
            return self.unknown_project_progress_bundle(project_id, "CTRL_SCOPE_UNAVAILABLE")

        ctrl_ids = tuple(sorted(normalized))
        with self._state.locked():
            try:
                projection, records = self._replay_unlocked()
                cursor = json.loads(json.dumps(projection["cursor"], sort_keys=True))
                event_seq = cursor.get("event_seq")
                if not isinstance(event_seq, int) or isinstance(event_seq, bool) or event_seq < 0:
                    return self.unknown_project_progress_bundle(
                        project_id, "INVALID_CURSOR", ctrl_ids=ctrl_ids, cursor=cursor,
                    )
                scope_binding = {
                    "project_id": project_id,
                    "ctrl_ids": list(ctrl_ids),
                    "cursor": cursor,
                }
                scope_version = int(projection["scopes"].get(project_id, 0))
                topologies = {
                    ctrl_id: self._project_topology_from_records(
                        project_id, ctrl_id, records, through_cursor=event_seq,
                    )
                    for ctrl_id in ctrl_ids
                }
                if any(
                    topology.get("project_id") != project_id
                    or topology.get("ctrl_id") != ctrl_id
                    or topology.get("through_cursor") != event_seq
                    or topology.get("conflicts")
                    or topology.get("unknown_receipt_ids")
                    or any(
                        isinstance(node, dict) and node.get("unknown_receipt_ids")
                        for node in topology.get("nodes", [])
                    )
                    for ctrl_id, topology in topologies.items()
                ):
                    return self.unknown_project_progress_bundle(
                        project_id, "TOPOLOGY_SCOPE_CONFLICT", ctrl_ids=ctrl_ids, cursor=cursor,
                    )

                material_records: list[tuple[int, ProgressMaterialEvent]] = []
                event_by_id: dict[tuple[str, str], tuple[int, ProgressMaterialEvent]] = {}
                selected_event_digests: dict[str, str] = {}
                observed_boundary_ms: int | None = None
                for record in records:
                    raw_event = record["event"]
                    if self._is_non_material_record(raw_event):
                        continue
                    event = validate_progress_material_event(raw_event)
                    if event.ctrl_id in normalized:
                        if event.project_id != project_id or event.task_id not in normalized[event.ctrl_id]:
                            return self.unknown_project_progress_bundle(
                                project_id, "MIXED_SCOPE_REJECTED", ctrl_ids=ctrl_ids, cursor=cursor,
                            )
                        retained_digest = selected_event_digests.get(event.event_id)
                        if retained_digest is not None and retained_digest != event.digest:
                            return self.unknown_project_progress_bundle(
                                project_id, "SOURCE_DIGEST_CONFLICT", ctrl_ids=ctrl_ids, cursor=cursor,
                            )
                        selected_event_digests[event.event_id] = event.digest
                        material_records.append((int(record["event_seq"]), event))
                        event_by_id[(event.ctrl_id, event.event_id)] = (int(record["event_seq"]), event)
                        observed_boundary_ms = max(observed_boundary_ms or 0, event.observed_at_ms)
                    elif event.project_id == project_id and event.scope_version == scope_version:
                        return self.unknown_project_progress_bundle(
                            project_id, "MIXED_SCOPE_REJECTED", ctrl_ids=ctrl_ids, cursor=cursor,
                        )

                topology_nodes: dict[tuple[str, str], dict[str, Any]] = {}
                for ctrl_id, topology in topologies.items():
                    for node in topology.get("nodes", []):
                        if not isinstance(node, dict) or node.get("node_kind") == "CTRL":
                            continue
                        if (
                            node.get("project_id") != project_id
                            or node.get("ctrl_id") != ctrl_id
                            or node.get("task_id") not in normalized[ctrl_id]
                        ):
                            return self.unknown_project_progress_bundle(
                                project_id, "MIXED_SCOPE_REJECTED", ctrl_ids=ctrl_ids, cursor=cursor,
                            )
                        topology_nodes[(ctrl_id, str(node.get("node_id") or ""))] = node

                completion = self._project_from_projection(project_id, projection)
                if "CONFLICTED" in completion["overlays"]:
                    return self.unknown_project_progress_bundle(
                        project_id, "SOURCE_DIGEST_CONFLICT", ctrl_ids=ctrl_ids, cursor=cursor,
                    )
                if "STALE" in completion["overlays"]:
                    return self.unknown_project_progress_bundle(
                        project_id, "STALE_SOURCE", ctrl_ids=ctrl_ids, cursor=cursor,
                    )
                blocks = completion["blocks"]
                for block in blocks:
                    ctrl_id = str(block.get("ctrl_id") or "")
                    task_id = str(block.get("task_id") or "")
                    if (
                        ctrl_id not in normalized
                        or task_id not in normalized[ctrl_id]
                        or (ctrl_id, str(block.get("block_id") or "")) not in topology_nodes
                    ):
                        return self.unknown_project_progress_bundle(
                            project_id, "MIXED_SCOPE_REJECTED", ctrl_ids=ctrl_ids, cursor=cursor,
                        )

                request_states: dict[str, dict[str, Any]] = {}
                for retained in projection["request_lifecycles"].values():
                    record = retained.get("record")
                    task_id = record.get("task_id") if isinstance(record, dict) else None
                    if task_id not in task_ctrl:
                        continue
                    current = request_states.get(task_id)
                    if current is None or int(retained["event_seq"]) > int(current["event_seq"]):
                        request_states[task_id] = retained

                grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for block in blocks:
                    grouped.setdefault((str(block["ctrl_id"]), str(block["task_id"])), []).append(block)

                active_lifecycles = {"ACTIVE", "RUNNING", "RETRYING", "RESULT_PENDING"}
                terminal_lifecycles = {"VERIFIED", "ACCEPTED", "COMPLETE", "TOMBSTONED"}
                active_rows: list[dict[str, Any]] = []
                queue_rows: list[dict[str, Any]] = []
                for (ctrl_id, task_id), task_blocks in sorted(grouped.items()):
                    candidates = [block for block in task_blocks if block["lifecycle_state"] not in terminal_lifecycles]
                    if not candidates:
                        continue
                    current = max(
                        candidates,
                        key=lambda item: (int(item.get("latest_event_seq") or 0), str(item.get("block_id") or "")),
                    )
                    topology_node = topology_nodes[(ctrl_id, str(current["block_id"]))]
                    latest = event_by_id.get((ctrl_id, str(topology_node.get("latest_event_id") or "")))
                    if latest is None or latest[1].task_id != task_id:
                        return self.unknown_project_progress_bundle(
                            project_id, "SOURCE_DIGEST_CONFLICT", ctrl_ids=ctrl_ids, cursor=cursor,
                        )
                    latest_seq, latest_event = latest
                    flags = {str(flag).casefold() for flag in latest_event.flags}
                    stale = bool(flags & {"stale", "conflicted"}) or bool(topology_node.get("unknown_receipt_ids"))
                    if stale:
                        return self.unknown_project_progress_bundle(
                            project_id, "STALE_SOURCE", ctrl_ids=ctrl_ids, cursor=cursor,
                        )

                    milestone_roots = {
                        str(block["milestone_id"]): block for block in task_blocks
                        if block.get("block_id") == block.get("milestone_id")
                        and block.get("parent_block_id") is None
                        and "MILESTONE_ACCEPTANCE" in block.get("proof_required_classes", [])
                    }
                    completed_milestones = sum(
                        block.get("lifecycle_state") == "ACCEPTED"
                        and block.get("committed_weight") is not None
                        and block.get("admitted_proof_weight") == block.get("committed_weight")
                        and bool(block.get("proof_receipt_ids"))
                        for block in milestone_roots.values()
                    )
                    total_milestones = len(milestone_roots)
                    progress = (
                        {
                            "state": "KNOWN", "completed_milestones": completed_milestones,
                            "total_milestones": total_milestones,
                            "percent": round(completed_milestones * 100 / total_milestones, 2),
                        }
                        if total_milestones and not stale
                        else {"state": "UNKNOWN", "completed_milestones": None, "total_milestones": None, "percent": None}
                    )

                    eta = {
                        "state": "UNKNOWN", "start_ms": None, "end_ms": None,
                        "confidence": None, "basis_receipt_ids": [], "basis_receipts": [],
                    }
                    basis_receipts: list[dict[str, Any]] = []
                    for receipt_id in latest_event.eta_receipt_ids:
                        retained = event_by_id.get((ctrl_id, receipt_id))
                        if retained is None or retained[0] > latest_seq or retained[1].task_id != task_id:
                            basis_receipts = []
                            break
                        basis_receipts.append({"event_id": receipt_id, "event_digest": retained[1].digest})
                    if (
                        not stale and basis_receipts
                        and latest_event.eta_start_ms is not None and latest_event.eta_end_ms is not None
                        and latest_event.eta_start_ms <= latest_event.eta_end_ms
                        and latest_event.eta_confidence is not None
                    ):
                        eta = {
                            "state": "KNOWN", "start_ms": latest_event.eta_start_ms,
                            "end_ms": latest_event.eta_end_ms, "confidence": latest_event.eta_confidence,
                            "basis_receipt_ids": list(latest_event.eta_receipt_ids),
                            "basis_receipts": basis_receipts,
                        }

                    task_events = [item for item in material_records if item[1].ctrl_id == ctrl_id and item[1].task_id == task_id]
                    started_at_ms = min(
                        (event.observed_at_ms for _, event in task_events if event.lifecycle_state.value in active_lifecycles),
                        default=None,
                    )
                    elapsed = (
                        {"state": "KNOWN", "elapsed_ms": max(0, observed_boundary_ms - started_at_ms)}
                        if not stale and observed_boundary_ms is not None and started_at_ms is not None
                        else {"state": "UNKNOWN", "elapsed_ms": None}
                    )
                    signal = {
                        "event_id": latest_event.event_id,
                        "event_digest": latest_event.digest,
                        "event_seq": latest_seq,
                        "observed_at_ms": latest_event.observed_at_ms,
                        "summary": latest_event.material_update_sentence,
                    }

                    lifecycle = latest_event.lifecycle_state.value
                    direct = request_states.get(task_id)
                    if direct is not None and int(direct["event_seq"]) > latest_seq:
                        lifecycle = str(direct["lifecycle_state"])
                    routing = latest_event.routing_evidence
                    blocked_recovery = None
                    if isinstance(routing, dict) and routing.get("route") == "hard_blocked":
                        release_id = routing.get("release_event")
                        retained_release = event_by_id.get((ctrl_id, str(release_id or "")))
                        if retained_release is not None and retained_release[0] <= latest_seq and retained_release[1].task_id == task_id:
                            blocked_recovery = self._progress_queue_recovery(
                                retained_release[1], event_by_id, {**scope_binding, "ctrl_id": ctrl_id},
                            )
                    queue_state, runnable = self.classify_progress_queue_state(
                        lifecycle,
                        stale=stale,
                        routing=routing,
                        flags=flags,
                        task_id=task_id,
                        owner_id=latest_event.owner_id,
                        has_dependencies=bool(topology_node.get("dependency_ids")),
                        has_blocked_recovery=blocked_recovery is not None,
                    )

                    presentation = normalized[ctrl_id][task_id]
                    row = {
                        "scope_binding": {**scope_binding, "ctrl_id": ctrl_id},
                        "task_id": task_id,
                        "task_name": presentation["task_name"],
                        "role": presentation["role"],
                        "owner_id": latest_event.owner_id,
                        "lifecycle": lifecycle,
                        "progress": progress,
                        "last_accepted_signal": signal,
                        "freshness": {
                            "state": "STALE" if stale else "CURRENT",
                            "observed_at_ms": latest_event.observed_at_ms,
                        },
                        "elapsed": elapsed,
                        "eta": eta,
                        "queue_state": queue_state,
                        "runnable": runnable if queue_state is not None else None,
                        "next_operation_or_release_event": routing.get("release_event") if isinstance(routing, dict) else None,
                        "blocked_recovery": blocked_recovery,
                    }
                    (active_rows if queue_state is None else queue_rows).append(row)

                host_scope_payload = [
                    (ctrl_id, task_id, presentation["task_name"], presentation["role"])
                    for ctrl_id, tasks in sorted(normalized.items())
                    for task_id, presentation in sorted(tasks.items())
                ]
                selected_records = [
                    (seq, event.event_id, event.digest, event.ctrl_id, event.task_id)
                    for seq, event in material_records
                ]
                source_digests = {
                    "ledger": str(cursor.get("event_digest") or ""),
                    "topology": {ctrl_id: str(topologies[ctrl_id]["projection_digest"]) for ctrl_id in ctrl_ids},
                    "host_scope": hashlib.sha256(json.dumps(host_scope_payload, separators=(",", ":")).encode("utf-8")).hexdigest(),
                    "material_feed": hashlib.sha256(json.dumps(selected_records, separators=(",", ":")).encode("utf-8")).hexdigest(),
                }
                queue = {
                    "schema_version": 1,
                    "view_id": "view.project.progress",
                    "renderer": "table",
                    "project_id": project_id,
                    "scope_binding": scope_binding,
                    "accepted_cursor": cursor,
                    "status": "CURRENT",
                    "reason": None,
                    "available": True,
                    "segments": [
                        {"segment_id": "segment.project.progress.active", "label": "Active", "order": 10, "rows": active_rows},
                        {"segment_id": "segment.project.progress.queue", "label": "Queue", "order": 20, "rows": queue_rows},
                    ],
                    "source_digests": source_digests,
                    "claim_limit": (
                        "Rows are a read-only CTRL-first projection of one retained Ledger cursor. Progress counts only "
                        "typed whole-milestone acceptance; ETA requires exact same-task receipt digests; only routed Queued is runnable."
                    ),
                }
                queue["projection_digest"] = hashlib.sha256(
                    json.dumps(queue, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                return {**completion, "scope_binding": scope_binding, "progress_queue": queue}
            except ProgressEventError:
                return self.unknown_project_progress_bundle(
                    project_id, "RESYNC_REQUIRED", ctrl_ids=ctrl_ids,
                )

    def _bounded_tail_records(self) -> tuple[list[dict[str, Any]], bool]:
        if not self._state.path.exists():
            return [], False
        size = self._state.path.stat().st_size
        start = max(0, size - MAX_FEED_SCAN_BYTES)
        with self._state.path.open("rb") as handle:
            handle.seek(start)
            payload = handle.read(MAX_FEED_SCAN_BYTES)
        lines = payload.splitlines()
        if start and lines:
            lines = lines[1:]
        records = []
        for line in lines:
            try:
                record = json.loads(line)
                raw_event = record["event"]
                record_type = raw_event.get("record_type") if isinstance(raw_event, dict) else None
                decoded = self._decode_non_material_record(raw_event, str(record.get("event_digest") or ""))
                if decoded is not None:
                    record_type, record_id, _, event_digest = decoded
                    records.append({**record, "_event": None, "_record_id": record_id, "_record_type": record_type})
                    continue
                event = validate_progress_material_event(raw_event)
            except (json.JSONDecodeError, KeyError, TypeError, ProgressEventError):
                continue
            if record.get("event_digest") == event.digest:
                records.append({**record, "_event": event, "_record_id": event.event_id, "_record_type": None})
        return records, start > 0

    def feed_snapshot(self, project_id: str, *, limit: int = 4, after_cursor: int = 0) -> dict[str, Any]:
        project_id = _safe_id(project_id, "project_id")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
            raise ProgressEventError("feed limit must be between 1 and 10")
        after_cursor = _positive_int(after_cursor, "feed cursor", allow_zero=True)
        records, truncated = self._bounded_tail_records()
        project_records = [record for record in records if record["_event"] is not None and record["_event"].project_id == project_id and record["_event"].material_update_sentence is not None]
        oldest_seq = min((int(record["event_seq"]) for record in records), default=0)
        stale_cursor = bool(after_cursor and truncated and after_cursor < oldest_seq)
        eligible = project_records if stale_cursor or not after_cursor else [record for record in project_records if int(record["event_seq"]) > after_cursor]
        selected = sorted(eligible, key=lambda item: int(item["event_seq"]), reverse=True)[:limit]
        items = []
        for record in selected:
            event = record["_event"]
            items.append({
                "event_id": event.event_id,
                "event_seq": int(record["event_seq"]),
                "event_digest": event.digest,
                "project_id": event.project_id,
                "task_id": event.task_id,
                "block_id": event.block_id,
                "owner_id": event.owner_id,
                "material_update_sentence": event.material_update_sentence,
                "observed_at_ms": event.observed_at_ms,
                "event_kind": event.event_kind.value,
                "lifecycle_state": event.lifecycle_state.value,
                "proof_receipt_ids": list(event.proof_receipt_ids),
                "proof_classes": list(event.proof_required_classes),
                "flags": list(event.flags),
                "provenance": event.provenance,
                "source": event.source,
                "claim_limit": event.claim_limit,
            })
        newest = max((int(record["event_seq"]) for record in records), default=after_cursor)
        cursor_record = max(records, key=lambda item: int(item["event_seq"]), default=None)
        return {
            "project_id": project_id,
            "limit": limit,
            "cursor": {
                "event_seq": newest,
                "event_id": None if cursor_record is None else cursor_record["_record_id"],
                "event_digest": None if cursor_record is None else cursor_record["event_digest"],
            },
            "items": items,
            "stale_cursor": stale_cursor,
            "scan_truncated": truncated,
            "transport": {
                "snapshot": "available",
                "incremental": "in_process_event_notification",
                "http_stream": "UNVERIFIED",
            },
            "producer": {
                "status": "typed_runtime_transition_only",
                "native_host_transport": "UNVERIFIED",
            },
            "claim_limit": "The feed contains only validated canonical material events. Relative age is client-local; connection state, healthy liveness renewal, silence, and activity are not progress.",
        }

    def subscribe(self, project_id: str, *, after_cursor: int = 0, limit: int = 4) -> ProgressFeedSubscription:
        return ProgressFeedSubscription(self, project_id, after_cursor, limit)


@dataclass(frozen=True)
class MaterialProgressReceipt:
    receipt_id: str
    plan_id: str
    previous_plan_id: str | None
    unit_id: str
    unit_kind: str
    total_units: int
    completed_units: int
    basis: str
    observed_at_ms: int
    source: str

    def progress_basis(self) -> dict[str, Any]:
        return {
            "receipts": [self.receipt_id],
            "plan_units": {
                "plan_id": self.plan_id,
                "unit_id": self.unit_id,
                "unit_kind": self.unit_kind,
                "total_units": self.total_units,
                "completed_units": self.completed_units,
                "basis": self.basis,
                "observed_at_ms": self.observed_at_ms,
            },
        }


@dataclass(frozen=True)
class ProgressPulseEvent:
    task_id: str
    project_id: str
    pulse_receipt: str
    observed_at_ms: int
    state: str
    progress: MaterialProgressReceipt | None
    eta_report: dict[str, Any] | None
    digest: str


# Compatibility import only: both names construct the exact same Ledger authority.
ProgressLedger = Ledger


def _validate_eta_report(value: Any, task_id: str, project_id: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProgressEventError("eta_report must be an object or null")
    _exact_fields(value, ETA_FIELDS, "eta_report")
    if value.get("receipt_type") != "swarm_task_owner_forecast":
        raise ProgressEventError("eta_report receipt_type is invalid")
    if _safe_id(value.get("task_id"), "eta_report task_id") != task_id or _safe_id(value.get("project_id"), "eta_report project_id") != project_id:
        raise ProgressEventError("eta_report target does not match the pulse")
    _safe_id(value.get("source"), "eta_report source")
    _safe_id(value.get("receipt"), "eta_report receipt", maximum=256)
    reason_code = _safe_id(value.get("reason_code"), "eta_report reason_code", maximum=64)
    if reason_code not in ETA_REASON_CODES:
        raise ProgressEventError("eta_report reason_code is invalid")
    _safe_text(value.get("short_reason"), "eta_report short_reason")
    baseline = value.get("baseline")
    current = value.get("current")
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        raise ProgressEventError("eta_report requires baseline and current objects")
    _exact_fields(baseline, ETA_BOUND_FIELDS, "eta_report baseline")
    _exact_fields(current, ETA_CURRENT_FIELDS, "eta_report current")
    for label, bounds in (("baseline", baseline), ("current", current)):
        for key in ("eta_start_ms", "eta_end_ms"):
            if bounds.get(key) is not None and (not isinstance(bounds[key], int) or isinstance(bounds[key], bool)):
                raise ProgressEventError(f"eta_report {label} {key} must be an integer or null")
        confidence = bounds.get("confidence")
        if not isinstance(confidence, int) or isinstance(confidence, bool) or not 0 <= confidence <= 100:
            raise ProgressEventError(f"eta_report {label} confidence is invalid")
        if bounds.get("eta_start_ms") is not None and bounds.get("eta_end_ms") is not None and bounds["eta_start_ms"] > bounds["eta_end_ms"]:
            raise ProgressEventError(f"eta_report {label} range is invalid")
    if current.get("status") not in ETA_STATES:
        raise ProgressEventError("eta_report current status is invalid")
    last_progress_at_ms = current.get("last_progress_at_ms")
    if last_progress_at_ms is not None and (not isinstance(last_progress_at_ms, int) or isinstance(last_progress_at_ms, bool) or last_progress_at_ms <= 0):
        raise ProgressEventError("eta_report last_progress_at_ms is invalid")
    progress_basis = current.get("progress_basis")
    if not isinstance(progress_basis, dict) or set(progress_basis) != {"receipts"}:
        raise ProgressEventError("eta_report progress_basis may contain receipt identities only")
    receipts = progress_basis.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        raise ProgressEventError("eta_report requires at least one receipt identity")
    for receipt in receipts:
        _safe_id(receipt, "eta_report progress receipt")
    return value


def validate_progress_pulse(payload: Any) -> ProgressPulseEvent:
    if not isinstance(payload, dict):
        raise ProgressEventError("progress pulse must be a JSON object")
    _exact_fields(payload, TOP_LEVEL_FIELDS, "progress pulse")
    if payload.get("schema_version") != 1 or payload.get("source") != PULSE_SOURCE or payload.get("receipt_type") != PULSE_RECEIPT_TYPE:
        raise ProgressEventError("progress pulse envelope is invalid")
    task_id = _safe_id(payload.get("task_id"), "task_id")
    project_id = _safe_id(payload.get("project_id"), "project_id")
    pulse_receipt = _safe_id(payload.get("pulse_receipt"), "pulse_receipt")
    observed_at_ms = payload.get("observed_at_ms")
    if not isinstance(observed_at_ms, int) or isinstance(observed_at_ms, bool) or observed_at_ms <= 0:
        raise ProgressEventError("observed_at_ms must be a positive integer")
    state = str(payload.get("state") or "").strip()
    if state not in PULSE_STATES:
        raise ProgressEventError("progress pulse state is invalid")
    progress_value = payload.get("progress")
    progress = None
    if progress_value is not None:
        if not isinstance(progress_value, dict):
            raise ProgressEventError("progress must be an object or null")
        _exact_fields(progress_value, PROGRESS_FIELDS, "progress")
        receipt_id = _safe_id(progress_value.get("receipt_id"), "progress receipt_id")
        plan_id = _safe_id(progress_value.get("plan_id"), "progress plan_id")
        previous_raw = progress_value.get("previous_plan_id")
        previous_plan_id = None if previous_raw in (None, "") else _safe_id(previous_raw, "progress previous_plan_id")
        unit_id = _safe_id(progress_value.get("unit_id"), "progress unit_id")
        unit_kind = _safe_id(progress_value.get("unit_kind"), "progress unit_kind", maximum=64)
        source = _safe_id(progress_value.get("source"), "progress source")
        basis = _safe_text(progress_value.get("basis"), "progress basis", maximum=128)
        progress_observed_at = progress_value.get("observed_at_ms")
        if not isinstance(progress_observed_at, int) or isinstance(progress_observed_at, bool) or not 0 < progress_observed_at <= observed_at_ms:
            raise ProgressEventError("progress observed_at_ms must be positive and no later than its pulse")
        try:
            CtrlProgressMeasure(
                completed_units=progress_value.get("completed_units"),
                total_units=progress_value.get("total_units"),
                basis=basis,
                receipt_ids=(receipt_id,),
                observed_at=progress_observed_at,
            )
        except InvariantError as error:
            raise ProgressEventError(str(error)) from error
        progress = MaterialProgressReceipt(
            receipt_id=receipt_id,
            plan_id=plan_id,
            previous_plan_id=previous_plan_id,
            unit_id=unit_id,
            unit_kind=unit_kind,
            total_units=int(progress_value["total_units"]),
            completed_units=int(progress_value["completed_units"]),
            basis=basis,
            observed_at_ms=progress_observed_at,
            source=source,
        )
    eta_report = _validate_eta_report(payload.get("eta_report"), task_id, project_id)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_PULSE_BYTES:
        raise ProgressEventError("progress pulse exceeds the size guard")
    return ProgressPulseEvent(task_id, project_id, pulse_receipt, observed_at_ms, state, progress, eta_report, hashlib.sha256(encoded).hexdigest())


def write_progress_pulse(codex_home: Path, payload: Any) -> dict[str, Any]:
    """Atomically replace one task's latest bounded pulse after strict validation."""
    event = validate_progress_pulse(payload)
    effective_payload = payload
    codex_home = Path(codex_home).expanduser().resolve()
    swarm_root = codex_home / "swarm"
    pulse_root = codex_home / PULSE_ROOT
    pulse_root.mkdir(parents=True, exist_ok=True)
    if swarm_root.resolve() != swarm_root or pulse_root.resolve() != pulse_root:
        raise ProgressEventError("progress pulse store must not use links or junctions")
    event_path = pulse_root / f"{hashlib.sha256(event.task_id.encode('utf-8')).hexdigest()}.json"
    if event_path.exists():
        try:
            existing_payload = json.loads(event_path.read_text(encoding="utf-8"))
            existing = validate_progress_pulse(existing_payload)
        except (OSError, json.JSONDecodeError, ProgressEventError) as error:
            raise ProgressEventError("stored progress pulse is unreadable") from error
        if existing.task_id != event.task_id:
            raise ProgressEventError("stored progress pulse target conflicts")
        if existing.observed_at_ms > event.observed_at_ms:
            raise ProgressEventError("progress pulse cannot regress its observed high-water")
        # A liveness-only heartbeat must not erase a material measure that the
        # asynchronous console observer has not consumed yet. Carry the latest
        # validated measure forward; its receipt remains idempotent in SQLite.
        if event.progress is None and existing.progress is not None:
            progress = existing.progress
            effective_payload = {
                **payload,
                "progress": {
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
            }
            event = validate_progress_pulse(effective_payload)
        if existing.observed_at_ms == event.observed_at_ms:
            if existing.digest != event.digest:
                raise ProgressEventError("progress pulse conflicts at the observed high-water")
            return {"status": "unchanged", "task_id": event.task_id, "observed_at_ms": event.observed_at_ms, "digest": event.digest}
    encoded = json.dumps(effective_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=pulse_root, prefix=".pulse-", suffix=".json", encoding="utf-8", delete=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, event_path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"status": "written", "task_id": event.task_id, "observed_at_ms": event.observed_at_ms, "digest": event.digest}


def pulse_template(*, task_id: str, project_id: str, pulse_receipt: str, state: str, observed_at_ms: int | None = None) -> dict[str, Any]:
    """Return the minimal liveness-only envelope used by heartbeat callers."""
    return {
        "schema_version": 1,
        "source": PULSE_SOURCE,
        "receipt_type": PULSE_RECEIPT_TYPE,
        "task_id": task_id,
        "project_id": project_id,
        "pulse_receipt": pulse_receipt,
        "observed_at_ms": int(observed_at_ms if observed_at_ms is not None else time.time() * 1000),
        "state": state,
        "progress": None,
        "eta_report": None,
    }
