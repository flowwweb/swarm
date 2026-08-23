"""Bounded instruction-only progress pulse sidecars for the SWARM console."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import CtrlProgressMeasure, InvariantError


PULSE_ROOT = Path("swarm") / "progress-pulses"
PULSE_SOURCE = "swarm_local_progress_sidecar"
PULSE_RECEIPT_TYPE = "swarm_ctrl_project_pulse"
MAX_PULSE_BYTES = 16 * 1024
MAX_PULSE_FILES = 1024
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
