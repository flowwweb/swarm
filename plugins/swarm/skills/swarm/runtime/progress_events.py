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

from .core import CtrlProgressMeasure, InvariantError
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
    "parent_event_id", "topology",
})
LINEAGE_FIELDS = frozenset({"predecessor_block_ids", "split_from", "merged_from"})
MEASUREMENT_FIELDS = frozenset({"state", "committed_weight", "admitted_proof_weight", "basis_receipt_ids"})
PROOF_FIELDS = frozenset({"required_classes", "receipt_ids", "claim_limit"})
ETA_EVENT_FIELDS = frozenset({"start_ms", "end_ms", "confidence", "basis_receipt_ids"})
REWORK_FIELDS = frozenset({"attempt", "count", "invalidated_receipt_ids"})
CUSTODY_FIELDS = frozenset({"surface", "receipt_id"})
TOPOLOGY_FIELDS = frozenset({
    "node_kind", "input_receipt_ids", "dispatch_receipt_id",
    "completion_receipt_id", "cost_receipt_ids", "release_receipt_ids",
})
TOPOLOGY_NODE_KINDS = frozenset({"CTRL", "LEAD", "SUBAGENT", "TASK", "BLOCK"})


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
        return payload


def validate_progress_material_event(payload: Any) -> ProgressMaterialEvent:
    """Validate one compact material event without accepting chat or tool content."""
    if not isinstance(payload, dict):
        raise ProgressEventError("progress material event must be a JSON object")
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
    else:
        if topology is not None:
            raise ProgressEventError("schema-v1 progress events cannot carry topology")
        topology_node_kind = "BLOCK"
        input_receipt_ids = ()
        dispatch_receipt_id = None
        completion_receipt_id = None
        cost_receipt_ids = ()
        release_receipt_ids = ()
    if event_kind is ProgressEventKind.USER_STEERING_ACCEPTED and not steering_receipt_ids:
        raise ProgressEventError("accepted steering requires an exact steering receipt")

    canonical = dict(payload)
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
        digest=hashlib.sha256(encoded).hexdigest(),
        semantic_digest=semantic_digest,
    )


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


class ProgressFeedSubscription:
    """In-process event notification; HTTP/browser transport remains a separate gate."""

    def __init__(self, ledger: "ProgressLedger", project_id: str, cursor: int, limit: int):
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


class ProgressLedger:
    """Append-only material-event authority with a disposable compact projection."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self._state = LockedPrivateState(self.root, PROGRESS_LEDGER_PATH)
        self.projection_path = self.root / PROGRESS_PROJECTION_PATH
        self._condition = Condition()

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
        elif event.material_update_sentence is not None:
            projection["latest_material_signatures"][ProgressLedger._material_key(event)] = ProgressLedger._material_signature(event)
        projection["cursor"] = {
            "event_seq": event_seq,
            "event_id": event.event_id,
            "event_digest": event.digest,
        }

    @staticmethod
    def _apply(projection: dict[str, Any], event: ProgressMaterialEvent, event_seq: int) -> None:
        if event.schema_version == 2:
            ProgressLedger._apply_topology_record(projection, event, event_seq)
            return
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

        block_key = ProgressLedger._block_key(event)
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
            projection["latest_material_signatures"][ProgressLedger._material_key(event)] = ProgressLedger._material_signature(event)
        projection["cursor"] = {"event_seq": event_seq, "event_id": event.event_id, "event_digest": event.digest}

    def _replay_unlocked(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        projection = _empty_progress_projection()
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
            event = validate_progress_material_event(record["event"])
            if record["event_digest"] != event.digest:
                raise ProgressEventError("progress ledger event digest mismatch")
            self._apply(projection, event, expected_seq)
            records.append(record)
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

    def append(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        event = validate_progress_material_event(dict(payload))
        with self._state.locked():
            projection, records = self._replay_unlocked()
            conflicted = False
            retained_digest = projection["events"].get(event.event_id)
            if retained_digest is not None:
                if retained_digest != event.digest:
                    if event.schema_version == 1:
                        raise ProgressEventError("progress event identity conflicts with retained digest")
                    conflicted = True
                else:
                    return {"status": "unchanged", "cursor": projection["cursor"], "event_digest": event.digest}
            retained_semantic = projection["dedupe"].get(event.dedupe_key)
            if retained_semantic is not None:
                if retained_semantic != event.semantic_digest:
                    if event.schema_version == 1:
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
            self._apply(projection, event, event_seq)
            self._state.path.parent.mkdir(parents=True, exist_ok=True)
            with self._state.path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            self._write_projection_unlocked(projection)
        with self._condition:
            self._condition.notify_all()
        return {
            "status": "conflicted" if conflicted else "appended",
            "cursor": projection["cursor"],
            "event_digest": event.digest,
            "bytes": len(line),
        }

    def replay(self) -> dict[str, Any]:
        with self._state.locked():
            projection, _ = self._replay_unlocked()
            self._write_projection_unlocked(projection)
            return projection

    def project(self, project_id: str) -> dict[str, Any]:
        project_id = _safe_id(project_id, "project_id")
        projection = self.replay()
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
        maximum_cursor = len(records)
        cursor = maximum_cursor if through_cursor is None else _positive_int(
            through_cursor, "through_cursor", allow_zero=True
        )
        if cursor > maximum_cursor:
            raise ProgressEventError("through_cursor exceeds retained knowledge")

        known: list[tuple[int, ProgressMaterialEvent]] = []
        for record in records[:cursor]:
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
                event = validate_progress_material_event(record["event"])
            except (json.JSONDecodeError, KeyError, TypeError, ProgressEventError):
                continue
            if record.get("event_digest") == event.digest:
                records.append({**record, "_event": event})
        return records, start > 0

    def feed_snapshot(self, project_id: str, *, limit: int = 4, after_cursor: int = 0) -> dict[str, Any]:
        project_id = _safe_id(project_id, "project_id")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
            raise ProgressEventError("feed limit must be between 1 and 10")
        after_cursor = _positive_int(after_cursor, "feed cursor", allow_zero=True)
        records, truncated = self._bounded_tail_records()
        project_records = [record for record in records if record["_event"].project_id == project_id and record["_event"].material_update_sentence is not None]
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
                "event_id": None if cursor_record is None else cursor_record["_event"].event_id,
                "event_digest": None if cursor_record is None else cursor_record["_event"].digest,
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
