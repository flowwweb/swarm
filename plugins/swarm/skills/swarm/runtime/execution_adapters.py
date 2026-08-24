"""Optional provider-neutral execution adapters behind SWARM routing authority.

Adapters translate an already-authorized execution request. They do not select
owners, store prompts or responses, review work, accept artifacts, or mutate
host task state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import Mapping

from .core import (
    ArtifactIdentity,
    DelegatedReceiptVerdict,
    DelegatedReturnReceipt,
    ExecutionRoute,
    ExecutionRoutingDecision,
    InvariantError,
    ProofState,
    Swarm,
    TaskState,
)
from .topology import TopologyDispatchPacket


_DIGEST_CHARS = frozenset("0123456789abcdef")
_HOST_EVENT_AUTHORITY = object()
_HOST_RESPONSE_AUTHORITY = object()


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(character in value for character in "\r\n\t"):
        raise InvariantError(f"{label} must be exact non-empty text")
    return value.strip()


def _digest(value: str, label: str) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if len(normalized) != 64 or any(character not in _DIGEST_CHARS for character in normalized):
        raise InvariantError(f"{label} must be a SHA-256 digest")
    return normalized


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


class AdapterCapabilityState(StrEnum):
    NATIVE = "native"
    ENFORCED = "enforced"
    INSTRUCTION_ONLY = "instruction_only"
    UNSUPPORTED = "unsupported"


class AdapterPlanStatus(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AdapterCapability:
    name: str
    state: AdapterCapabilityState
    evidence: str
    claim_limit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "adapter capability name"))
        if not isinstance(self.state, AdapterCapabilityState):
            raise InvariantError("adapter capability state must be typed")
        _text(self.evidence, "adapter capability evidence")
        _text(self.claim_limit, "adapter capability claim limit")


@dataclass(frozen=True)
class AdapterCapabilityMatrix:
    adapter_id: str
    provider_id: str
    optional: bool
    capabilities: tuple[AdapterCapability, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", _text(self.adapter_id, "adapter id"))
        object.__setattr__(self, "provider_id", _text(self.provider_id, "adapter provider id"))
        if not isinstance(self.optional, bool) or not self.capabilities:
            raise InvariantError("adapter matrix requires optional state and capabilities")
        names = tuple(item.name for item in self.capabilities if isinstance(item, AdapterCapability))
        if len(names) != len(self.capabilities) or len(names) != len(set(names)):
            raise InvariantError("adapter matrix capabilities must be typed and distinct")

    def state_for(self, name: str) -> AdapterCapabilityState:
        target = _text(name, "adapter capability lookup")
        for capability in self.capabilities:
            if capability.name == target:
                return capability.state
        return AdapterCapabilityState.UNSUPPORTED

    def execution_ready(self, required: tuple[str, ...]) -> tuple[bool, str]:
        if len(required) != len(set(required)) or any(not isinstance(item, str) or not item.strip() for item in required):
            raise InvariantError("required adapter capabilities must be distinct non-empty names")
        for name in required:
            state = self.state_for(name)
            if state is AdapterCapabilityState.INSTRUCTION_ONLY:
                return False, f"required capability is instruction-only: {name}"
            if state is AdapterCapabilityState.UNSUPPORTED:
                return False, f"required capability is unsupported: {name}"
        return True, ""

    def digest(self) -> str:
        return _canonical_digest(
            {
                "adapter": self.adapter_id,
                "provider": self.provider_id,
                "optional": self.optional,
                "capabilities": tuple(
                    (item.name, item.state.value, item.evidence, item.claim_limit)
                    for item in sorted(self.capabilities, key=lambda value: value.name)
                ),
            }
        )


@dataclass(frozen=True)
class ExecutionAdapterRequest:
    request_id: str
    adapter_id: str
    task_id: str
    accountable_owner: str
    cwd: str
    artifact: ArtifactIdentity
    instruction_digest: str
    required_capabilities: tuple[str, ...]
    routing: ExecutionRoutingDecision
    model: str = ""
    approval_policy: str = ""
    sandbox: str = ""
    request_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.request_id, "adapter request id"),
            (self.adapter_id, "adapter request adapter id"),
            (self.task_id, "adapter request task id"),
            (self.accountable_owner, "adapter request accountable owner"),
            (self.cwd, "adapter request cwd"),
        ):
            _text(value, label)
        if not (PureWindowsPath(self.cwd).is_absolute() or PurePosixPath(self.cwd).is_absolute()):
            raise InvariantError("adapter request cwd must be absolute")
        if not isinstance(self.artifact, ArtifactIdentity):
            raise InvariantError("adapter request requires an exact artifact identity")
        object.__setattr__(self, "instruction_digest", _digest(self.instruction_digest, "adapter instruction"))
        if not isinstance(self.routing, ExecutionRoutingDecision):
            raise InvariantError("adapter request requires a SWARM execution routing decision")
        if self.routing.route is ExecutionRoute.HARD_BLOCKED:
            raise InvariantError("hard-blocked SWARM routing cannot invoke an execution adapter")
        if self.routing.accountable_owner != self.accountable_owner:
            raise InvariantError("adapter request owner must match the SWARM routing owner")
        required = tuple(_text(item, "required adapter capability") for item in self.required_capabilities)
        if len(required) != len(set(required)):
            raise InvariantError("required adapter capabilities must be distinct")
        object.__setattr__(self, "required_capabilities", required)
        for value, label in ((self.model, "adapter model"), (self.approval_policy, "adapter approval policy"), (self.sandbox, "adapter sandbox")):
            if value:
                _text(value, label)
        payload = {
            "request": self.request_id,
            "adapter": self.adapter_id,
            "task": self.task_id,
            "owner": self.accountable_owner,
            "cwd": self.cwd,
            "artifact": self.artifact.content_address(),
            "instruction": self.instruction_digest,
            "required": self.required_capabilities,
            "route": self.routing.route.value,
            "route_receipt": self.routing.host_receipt,
            "model": self.model,
            "approval_policy": self.approval_policy,
            "sandbox": self.sandbox,
        }
        object.__setattr__(self, "request_digest", _canonical_digest(payload))


@dataclass(frozen=True)
class AdapterExecutionPlan:
    status: AdapterPlanStatus
    adapter_id: str
    request_digest: str
    capability_matrix_digest: str
    entrypoint: tuple[str, ...] = ()
    protocol: str = ""
    blocker: str = ""
    claim_limit: str = "Execution transport is not ownership, proof, review, or acceptance authority."

    @property
    def ready(self) -> bool:
        return self.status is AdapterPlanStatus.READY


@dataclass(frozen=True)
class AdapterEvent:
    method: str
    thread_id: str = ""
    turn_id: str = ""
    item_id: str = ""
    status: str = ""
    evidence_digest: str = ""
    _authority: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _text(self.method, "adapter event method")
        if self.evidence_digest:
            object.__setattr__(self, "evidence_digest", _digest(self.evidence_digest, "adapter event evidence"))


class ExecutionDispatchState(StrEnum):
    QUEUED = "queued"
    DEFERRED = "deferred"
    ACTIVE = "active"
    CHECKPOINTED = "checkpointed"
    MATERIAL_RECEIPT = "material_receipt"
    INDEPENDENT_REVIEW = "independent_review"
    COMPLETE = "complete"
    UNVERIFIED = "unverified"


class ExecutionFailureKind(StrEnum):
    SILENCE = "silence"
    EMPTY = "empty"
    UNREADABLE = "unreadable"
    TIMEOUT = "timeout"
    BAD_REQUEST = "http_400_bad_request"
    HOST_FAILED = "host_failed"


class ServiceTierTruth(StrEnum):
    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class ExecutionConfigGeneration:
    """Host-observed dispatch preference; it is not a served-tier receipt."""

    generation_id: str
    service_tier: str
    model: str
    effort: str
    changed_at_ms: int
    host_receipt_id: str

    def __post_init__(self) -> None:
        _text(self.generation_id, "execution config generation id")
        if self.service_tier not in {"default", "fast", "priority"}:
            raise InvariantError("execution config generation requires default, fast, or priority service tier")
        for value, label in ((self.model, "execution config model"), (self.effort, "execution config effort")):
            if value:
                _text(value, label)
        if not isinstance(self.changed_at_ms, int) or isinstance(self.changed_at_ms, bool) or self.changed_at_ms < 0:
            raise InvariantError("execution config generation requires a nonnegative changed-at timestamp")
        _text(self.host_receipt_id, "execution config host receipt")

    @property
    def digest(self) -> str:
        return _canonical_digest((self.generation_id, self.service_tier, self.model, self.effort, self.changed_at_ms, self.host_receipt_id))


@dataclass(frozen=True)
class HostServiceTierReceipt:
    request_digest: str
    actual_service_tier: str
    receipt_id: str
    observed_at_ms: int
    _authority: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_digest", _digest(self.request_digest, "served-tier request"))
        if self.actual_service_tier not in {"default", "fast", "priority"}:
            raise InvariantError("served-tier receipt requires default, fast, or priority")
        _text(self.receipt_id, "served-tier host receipt")
        if not isinstance(self.observed_at_ms, int) or isinstance(self.observed_at_ms, bool) or self.observed_at_ms < 0:
            raise InvariantError("served-tier receipt requires a nonnegative observation time")


@dataclass(frozen=True)
class ContinuationSnapshot:
    """Content-free compaction receipt for one bounded retry."""

    digest: str
    source_bytes: int
    compacted_bytes: int
    observed_at_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "digest", _digest(self.digest, "continuation snapshot"))
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in (self.source_bytes, self.compacted_bytes, self.observed_at_ms)):
            raise InvariantError("continuation snapshot requires nonnegative integer sizes and time")
        if self.source_bytes <= 0 or self.compacted_bytes >= self.source_bytes or self.compacted_bytes > 16384:
            raise InvariantError("continuation snapshot must be provably smaller and bounded to 16 KiB")


@dataclass
class ExecutionReservation:
    reservation_id: str
    task_id: str
    owner_id: str
    artifact: ArtifactIdentity
    state: ExecutionDispatchState = ExecutionDispatchState.QUEUED
    request_digest: str = ""
    request_bytes: int = 0
    generation_id: str = ""
    requested_service_tier: str = ""
    requested_model: str = ""
    requested_effort: str = ""
    actual_service_tier: str = ""
    service_tier_truth: ServiceTierTruth = ServiceTierTruth.UNVERIFIED
    next_generation_id: str = ""
    host_thread_id: str = ""
    host_turn_id: str = ""
    host_completed: bool = False
    material_receipt_id: str = ""
    failure_kind: ExecutionFailureKind | None = None
    retry_count: int = 0
    snapshot_digest: str = ""
    user_tier_receipt_id: str = ""
    updated_at_ms: int = 0

    def __post_init__(self) -> None:
        for value, label in ((self.reservation_id, "execution reservation id"), (self.task_id, "execution task id"), (self.owner_id, "execution owner id")):
            _text(value, label)
        if not isinstance(self.artifact, ArtifactIdentity) or not isinstance(self.state, ExecutionDispatchState):
            raise InvariantError("execution reservation requires exact artifact and typed state")
        if self.request_digest:
            self.request_digest = _digest(self.request_digest, "retained execution request")
        if not isinstance(self.request_bytes, int) or isinstance(self.request_bytes, bool) or self.request_bytes < 0:
            raise InvariantError("execution reservation request size must be nonnegative")
        if self.requested_service_tier and self.requested_service_tier not in {"default", "fast", "priority"}:
            raise InvariantError("retained requested service tier is invalid")
        if self.actual_service_tier and self.actual_service_tier not in {"default", "fast", "priority"}:
            raise InvariantError("retained actual service tier is invalid")
        if not isinstance(self.service_tier_truth, ServiceTierTruth) or self.service_tier_truth is ServiceTierTruth.CONFIRMED and not self.actual_service_tier:
            raise InvariantError("retained served-tier truth requires exact host metadata")
        if self.failure_kind is not None and not isinstance(self.failure_kind, ExecutionFailureKind):
            raise InvariantError("retained execution failure must be typed")
        if not isinstance(self.host_completed, bool):
            raise InvariantError("retained host completion state must be boolean")
        if not isinstance(self.retry_count, int) or isinstance(self.retry_count, bool) or not 0 <= self.retry_count <= 1:
            raise InvariantError("execution reservation permits at most one retry")
        if self.snapshot_digest:
            self.snapshot_digest = _digest(self.snapshot_digest, "retained continuation snapshot")
        if self.user_tier_receipt_id:
            _text(self.user_tier_receipt_id, "retained direct-user tier receipt")
        if not isinstance(self.updated_at_ms, int) or isinstance(self.updated_at_ms, bool) or self.updated_at_ms < 0:
            raise InvariantError("execution reservation requires a nonnegative update time")

    def snapshot(self) -> dict[str, object]:
        return {
            "reservation_id": self.reservation_id,
            "task_id": self.task_id,
            "owner_id": self.owner_id,
            "artifact": {
                "base": self.artifact.base,
                "revision": self.artifact.revision,
                "purpose": self.artifact.purpose,
                "observables": self.artifact.observables,
                "observed_paths": self.artifact.observed_paths,
            },
            "state": self.state.value,
            "request_digest": self.request_digest,
            "request_bytes": self.request_bytes,
            "generation_id": self.generation_id,
            "requested_service_tier": self.requested_service_tier,
            "requested_model": self.requested_model,
            "requested_effort": self.requested_effort,
            "actual_service_tier": self.actual_service_tier,
            "service_tier_truth": self.service_tier_truth.value,
            "next_generation_id": self.next_generation_id,
            "host_thread_id": self.host_thread_id,
            "host_turn_id": self.host_turn_id,
            "host_completed": self.host_completed,
            "material_receipt_id": self.material_receipt_id,
            "failure_kind": None if self.failure_kind is None else self.failure_kind.value,
            "retry_count": self.retry_count,
            "snapshot_digest": self.snapshot_digest,
            "user_tier_receipt_id": self.user_tier_receipt_id,
            "updated_at_ms": self.updated_at_ms,
        }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, object]) -> "ExecutionReservation":
        artifact_payload = payload.get("artifact")
        if not isinstance(artifact_payload, Mapping):
            raise InvariantError("execution reservation snapshot requires an artifact")
        artifact = ArtifactIdentity(
            str(artifact_payload.get("base") or ""),
            str(artifact_payload.get("revision") or ""),
            str(artifact_payload.get("purpose") or ""),
            tuple(tuple(item) for item in artifact_payload.get("observables", ())),  # type: ignore[arg-type]
            tuple(str(item) for item in artifact_payload.get("observed_paths", ())),  # type: ignore[arg-type]
        )
        failure = payload.get("failure_kind")
        return cls(
            reservation_id=str(payload.get("reservation_id") or ""),
            task_id=str(payload.get("task_id") or ""),
            owner_id=str(payload.get("owner_id") or ""),
            artifact=artifact,
            state=ExecutionDispatchState(str(payload.get("state") or "")),
            request_digest=str(payload.get("request_digest") or ""),
            request_bytes=int(payload.get("request_bytes") or 0),
            generation_id=str(payload.get("generation_id") or ""),
            requested_service_tier=str(payload.get("requested_service_tier") or ""),
            requested_model=str(payload.get("requested_model") or ""),
            requested_effort=str(payload.get("requested_effort") or ""),
            actual_service_tier=str(payload.get("actual_service_tier") or ""),
            service_tier_truth=ServiceTierTruth(str(payload.get("service_tier_truth") or "unverified")),
            next_generation_id=str(payload.get("next_generation_id") or ""),
            host_thread_id=str(payload.get("host_thread_id") or ""),
            host_turn_id=str(payload.get("host_turn_id") or ""),
            host_completed=payload.get("host_completed", False),  # type: ignore[arg-type]
            material_receipt_id=str(payload.get("material_receipt_id") or ""),
            failure_kind=None if failure in (None, "") else ExecutionFailureKind(str(failure)),
            retry_count=int(payload.get("retry_count") or 0),
            snapshot_digest=str(payload.get("snapshot_digest") or ""),
            user_tier_receipt_id=str(payload.get("user_tier_receipt_id") or ""),
            updated_at_ms=int(payload.get("updated_at_ms") or 0),
        )


class ExecutionDispatchLedger:
    """Exactly-once local reservation ledger; host transport remains external."""

    def __init__(self, *, generations: tuple[ExecutionConfigGeneration, ...] = (), reservations: tuple[ExecutionReservation, ...] = (), event_digests: tuple[str, ...] = ()) -> None:
        self._generations: dict[str, ExecutionConfigGeneration] = {}
        self._reservations: dict[str, ExecutionReservation] = {}
        self._task_reservations: dict[str, str] = {}
        self._event_digests = {_digest(value, "execution event") for value in event_digests}
        for generation in sorted(generations, key=lambda item: (item.changed_at_ms, item.generation_id)):
            self.observe_generation(generation)
        for reservation in reservations:
            self._add_reservation(reservation)

    @property
    def generations(self) -> tuple[ExecutionConfigGeneration, ...]:
        return tuple(sorted(self._generations.values(), key=lambda item: (item.changed_at_ms, item.generation_id)))

    @property
    def reservations(self) -> tuple[ExecutionReservation, ...]:
        return tuple(sorted(self._reservations.values(), key=lambda item: item.reservation_id))

    @property
    def event_digests(self) -> tuple[str, ...]:
        return tuple(sorted(self._event_digests))

    @property
    def latest_generation(self) -> ExecutionConfigGeneration | None:
        return max(self._generations.values(), key=lambda item: (item.changed_at_ms, item.generation_id), default=None)

    def observe_generation(self, generation: ExecutionConfigGeneration) -> None:
        if not isinstance(generation, ExecutionConfigGeneration):
            raise InvariantError("execution config observation must be typed")
        existing = self._generations.get(generation.generation_id)
        if existing is not None and existing != generation:
            raise InvariantError("execution config generation identity conflicts with retained state")
        latest = self.latest_generation
        if latest is not None and existing is None and generation.changed_at_ms <= latest.changed_at_ms:
            raise InvariantError("stale or ambiguously ordered execution config generation cannot become current")
        self._generations[generation.generation_id] = generation
        if latest is None or (generation.changed_at_ms, generation.generation_id) > (latest.changed_at_ms, latest.generation_id):
            for reservation in self._reservations.values():
                if reservation.state is ExecutionDispatchState.ACTIVE:
                    reservation.next_generation_id = generation.generation_id

    def _add_reservation(self, reservation: ExecutionReservation) -> None:
        if not isinstance(reservation, ExecutionReservation):
            raise InvariantError("execution reservation must be typed")
        if reservation.reservation_id in self._reservations or reservation.task_id in self._task_reservations:
            raise InvariantError("execution reservation or task already exists")
        self._reservations[reservation.reservation_id] = reservation
        self._task_reservations[reservation.task_id] = reservation.reservation_id

    def reserve(self, reservation_id: str, task_id: str, owner_id: str, artifact: ArtifactIdentity, *, observed_at_ms: int) -> ExecutionReservation:
        if reservation_id in self._reservations or task_id in self._task_reservations:
            raise InvariantError("duplicate dispatch reservation is prohibited")
        reservation = ExecutionReservation(reservation_id, task_id, owner_id, artifact, updated_at_ms=observed_at_ms)
        self._add_reservation(reservation)
        return reservation

    def reservation(self, reservation_id: str) -> ExecutionReservation:
        try:
            return self._reservations[reservation_id]
        except KeyError as error:
            raise InvariantError("execution reservation is not observed") from error

    def defer(self, reservation_id: str, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if reservation.state is not ExecutionDispatchState.QUEUED:
            raise InvariantError("only queued work can be deferred without dispatch")
        reservation.state = ExecutionDispatchState.DEFERRED
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def dispatch(self, reservation_id: str, request_digest: str, request_bytes: int, *, observed_at_ms: int, user_service_tier: str = "", user_override_receipt_id: str = "", direct_user_keep_out: bool = False, retry: bool = False) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if direct_user_keep_out:
            raise InvariantError("direct-user CTRL keep-out blocks delegated dispatch")
        generation = self.latest_generation
        if generation is None:
            raise InvariantError("latest host execution config is unavailable; dispatch remains UNVERIFIED")
        if reservation.state is ExecutionDispatchState.ACTIVE:
            raise InvariantError("duplicate dispatch is prohibited while the reservation is active")
        if reservation.state is ExecutionDispatchState.COMPLETE:
            raise InvariantError("completed execution cannot dispatch again")
        if retry and (reservation.failure_kind is not ExecutionFailureKind.BAD_REQUEST or reservation.retry_count != 0):
            raise InvariantError("only one resolved Bad Request may retry")
        if not retry and reservation.state is ExecutionDispatchState.UNVERIFIED and reservation.failure_kind is not None:
            raise InvariantError("failed execution requires an explicit permitted recovery path")
        digest = _digest(request_digest, "execution request")
        if not isinstance(request_bytes, int) or isinstance(request_bytes, bool) or request_bytes <= 0:
            raise InvariantError("execution request requires a positive bounded byte count")
        if bool(user_service_tier) != bool(user_override_receipt_id):
            raise InvariantError("direct user service-tier action requires an exact scoped receipt")
        if user_service_tier and user_service_tier not in {"default", "fast", "priority"}:
            raise InvariantError("direct user service tier must be default, fast, or priority")
        if user_override_receipt_id:
            _text(user_override_receipt_id, "direct user service-tier receipt")
        reservation.request_digest = digest
        reservation.request_bytes = request_bytes
        reservation.generation_id = generation.generation_id
        reservation.requested_service_tier = user_service_tier or generation.service_tier
        reservation.user_tier_receipt_id = user_override_receipt_id
        reservation.requested_model = generation.model
        reservation.requested_effort = generation.effort
        reservation.actual_service_tier = ""
        reservation.service_tier_truth = ServiceTierTruth.UNVERIFIED
        reservation.next_generation_id = ""
        reservation.host_completed = False
        reservation.failure_kind = None
        reservation.state = ExecutionDispatchState.ACTIVE
        reservation.updated_at_ms = observed_at_ms
        if retry:
            reservation.retry_count += 1
        return reservation

    def checkpoint(self, reservation_id: str, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if reservation.state is not ExecutionDispatchState.ACTIVE or not reservation.next_generation_id:
            raise InvariantError("only running work with a fresher host generation can checkpoint")
        reservation.state = ExecutionDispatchState.CHECKPOINTED
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def observe_event(self, reservation_id: str, event: AdapterEvent, *, observed_at_ms: int, served_tier: HostServiceTierReceipt | None = None) -> bool:
        reservation = self.reservation(reservation_id)
        if not isinstance(event, AdapterEvent) or event._authority is not _HOST_EVENT_AUTHORITY or not event.evidence_digest:
            raise InvariantError("host observation requires a typed readable event digest")
        if event.evidence_digest in self._event_digests:
            return False
        if reservation.state is not ExecutionDispatchState.ACTIVE:
            raise InvariantError("host events require an active retained reservation")
        self._event_digests.add(event.evidence_digest)
        reservation.host_thread_id = event.thread_id or reservation.host_thread_id
        reservation.host_turn_id = event.turn_id or reservation.host_turn_id
        status = event.status.casefold()
        if status in {"failed", "error", "cancelled", "canceled"}:
            reservation.failure_kind = ExecutionFailureKind.HOST_FAILED
            reservation.state = ExecutionDispatchState.UNVERIFIED
        elif status in {"completed", "complete"}:
            reservation.host_completed = True
        if served_tier is not None and served_tier._authority is _HOST_RESPONSE_AUTHORITY:
            expected = reservation.requested_service_tier
            actual_ok = served_tier.actual_service_tier == expected or expected == "fast" and served_tier.actual_service_tier == "priority"
            if served_tier.request_digest == reservation.request_digest and actual_ok:
                reservation.actual_service_tier = served_tier.actual_service_tier
                reservation.service_tier_truth = ServiceTierTruth.CONFIRMED
        reservation.updated_at_ms = observed_at_ms
        return True

    def fail_transport(self, reservation_id: str, kind: ExecutionFailureKind, *, observed_at_ms: int, http_status: int = 0, detail: str = "") -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if reservation.state is not ExecutionDispatchState.ACTIVE or not isinstance(kind, ExecutionFailureKind):
            raise InvariantError("transport failure requires an active reservation and typed outcome")
        if kind is ExecutionFailureKind.BAD_REQUEST and (http_status != 400 or detail != "Bad Request"):
            raise InvariantError("Bad Request classification requires exact HTTP 400 detail")
        reservation.failure_kind = kind
        reservation.state = ExecutionDispatchState.UNVERIFIED
        reservation.actual_service_tier = ""
        reservation.service_tier_truth = ServiceTierTruth.UNVERIFIED
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def retry_smaller(self, reservation_id: str, snapshot: ContinuationSnapshot, request_digest: str, request_bytes: int, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if not isinstance(snapshot, ContinuationSnapshot) or snapshot.observed_at_ms < reservation.updated_at_ms or snapshot.source_bytes != reservation.request_bytes or request_bytes >= reservation.request_bytes or request_bytes > snapshot.compacted_bytes:
            raise InvariantError("Bad Request retry requires a fresh provably smaller bounded snapshot")
        if request_digest == reservation.request_digest:
            raise InvariantError("Bad Request retry must be freshly generated")
        reservation.snapshot_digest = snapshot.digest
        override_tier = reservation.requested_service_tier if reservation.user_tier_receipt_id else ""
        override_receipt = reservation.user_tier_receipt_id
        return self.dispatch(
            reservation_id,
            request_digest,
            request_bytes,
            observed_at_ms=observed_at_ms,
            user_service_tier=override_tier,
            user_override_receipt_id=override_receipt,
            retry=True,
        )

    def record_material_receipt(self, reservation_id: str, receipt: DelegatedReturnReceipt, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        if not isinstance(receipt, DelegatedReturnReceipt):
            raise InvariantError("material progress requires an active reservation and typed readable receipt")
        if reservation.state is ExecutionDispatchState.MATERIAL_RECEIPT and reservation.material_receipt_id == receipt.receipt_id:
            return reservation
        if reservation.state is not ExecutionDispatchState.ACTIVE:
            raise InvariantError("material progress requires an active reservation and typed readable receipt")
        if receipt.verdict is not DelegatedReceiptVerdict.ACCEPT or receipt.task_id != reservation.task_id or receipt.owner_id != reservation.owner_id or receipt.artifact != reservation.artifact:
            raise InvariantError("material receipt must be readable ACCEPT bound to the exact task, owner, and artifact")
        if reservation.material_receipt_id and reservation.material_receipt_id != receipt.receipt_id:
            raise InvariantError("conflicting material receipt cannot replace retained evidence")
        reservation.material_receipt_id = receipt.receipt_id
        reservation.state = ExecutionDispatchState.MATERIAL_RECEIPT
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def record_independent_review(self, reservation_id: str, runtime: Swarm, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        task = runtime.tasks.get(reservation.task_id) if isinstance(runtime, Swarm) else None
        if reservation.state is not ExecutionDispatchState.MATERIAL_RECEIPT or task is None or task.owner != reservation.owner_id or task.acceptance_contract is None or task.acceptance_contract.artifact != reservation.artifact or runtime.proof_state(reservation.task_id) is not ProofState.ACCEPTED:
            raise InvariantError("independent review requires current runtime-issued exact-artifact acceptance")
        reservation.state = ExecutionDispatchState.INDEPENDENT_REVIEW
        reservation.updated_at_ms = observed_at_ms
        return reservation

    def record_complete(self, reservation_id: str, runtime: Swarm, *, observed_at_ms: int) -> ExecutionReservation:
        reservation = self.reservation(reservation_id)
        task = runtime.tasks.get(reservation.task_id) if isinstance(runtime, Swarm) else None
        if reservation.state is not ExecutionDispatchState.INDEPENDENT_REVIEW or not reservation.host_completed or task is None or task.state is not TaskState.COMPLETE or runtime.proof_state(reservation.task_id) is not ProofState.ACCEPTED:
            raise InvariantError("completion requires consumed host completion plus current independent runtime acceptance")
        reservation.state = ExecutionDispatchState.COMPLETE
        reservation.updated_at_ms = observed_at_ms
        return reservation


class ExecutionAdapter:
    """Provider-neutral adapter contract with no implicit fallback."""

    def __init__(self, matrix: AdapterCapabilityMatrix, *, entrypoint: tuple[str, ...], protocol: str, enabled: bool = True) -> None:
        if not isinstance(matrix, AdapterCapabilityMatrix):
            raise InvariantError("execution adapter requires a capability matrix")
        if not isinstance(enabled, bool) or not isinstance(entrypoint, tuple) or any(not isinstance(part, str) or not part for part in entrypoint):
            raise InvariantError("execution adapter requires typed enablement and exact argv")
        self.matrix = matrix
        self.entrypoint = entrypoint
        self.protocol = _text(protocol, "adapter protocol")
        self.enabled = enabled

    def plan(self, request: ExecutionAdapterRequest) -> AdapterExecutionPlan:
        if not isinstance(request, ExecutionAdapterRequest) or request.adapter_id != self.matrix.adapter_id:
            raise InvariantError("execution request targets a different adapter")
        matrix_digest = self.matrix.digest()
        if not self.enabled:
            return AdapterExecutionPlan(
                AdapterPlanStatus.DISABLED,
                self.matrix.adapter_id,
                request.request_digest,
                matrix_digest,
                blocker="optional execution adapter is disabled",
            )
        ready, blocker = self.matrix.execution_ready(request.required_capabilities)
        if not ready:
            return AdapterExecutionPlan(
                AdapterPlanStatus.BLOCKED,
                self.matrix.adapter_id,
                request.request_digest,
                matrix_digest,
                blocker=blocker,
            )
        return AdapterExecutionPlan(
            AdapterPlanStatus.READY,
            self.matrix.adapter_id,
            request.request_digest,
            matrix_digest,
            self.entrypoint,
            self.protocol,
        )


class CodexAppServerAdapter(ExecutionAdapter):
    """Native Codex app-server JSONL protocol adapter; transport is host-owned."""

    ADAPTER_ID = "codex-app-server"

    def __init__(self, *, enabled: bool = True) -> None:
        docs = "official OpenAI Codex App Server protocol"
        matrix = AdapterCapabilityMatrix(
            adapter_id=self.ADAPTER_ID,
            provider_id="openai-codex",
            optional=True,
            capabilities=(
                AdapterCapability("thread.start", AdapterCapabilityState.NATIVE, docs, "Creates a Codex thread only."),
                AdapterCapability("thread.resume", AdapterCapabilityState.NATIVE, docs, "Resumes a recorded Codex thread only."),
                AdapterCapability("turn.start", AdapterCapabilityState.NATIVE, docs, "Starts one Codex turn; it does not accept the result."),
                AdapterCapability("turn.steer", AdapterCapabilityState.NATIVE, docs, "Steers an active turn without changing SWARM ownership."),
                AdapterCapability("event.stream", AdapterCapabilityState.NATIVE, docs, "Streams Codex lifecycle events; raw bodies are not retained by this adapter."),
                AdapterCapability("approval.request", AdapterCapabilityState.NATIVE, docs, "Codex may request approval; SWARM cannot forge a user decision."),
                AdapterCapability("swarm.routing", AdapterCapabilityState.ENFORCED, "ExecutionAdapterRequest", "The request must carry a non-blocked SWARM routing decision for the same owner."),
                AdapterCapability("swarm.topology_dispatch", AdapterCapabilityState.INSTRUCTION_ONLY, "TopologyDispatchPacket", "The current Codex host thread creation API cannot consume or enforce the typed ready-wave packet."),
                AdapterCapability("model.instructions", AdapterCapabilityState.INSTRUCTION_ONLY, "model input", "Instructions guide behavior but do not enforce ownership, proof, or policy."),
                AdapterCapability("review.acceptance", AdapterCapabilityState.UNSUPPORTED, "SWARM review contract", "Adapter output cannot independently review or accept its own artifact."),
                AdapterCapability("host.task_mutation", AdapterCapabilityState.UNSUPPORTED, "SWARM user-custody contract", "No title, pin, folder, order, archive, or other host task mutation is exposed."),
            ),
        )
        super().__init__(matrix, entrypoint=("codex", "app-server", "--listen", "stdio://"), protocol="json-rpc-2.0-jsonl", enabled=enabled)

    @staticmethod
    def initialize_request(client_name: str, *, request_id: int = 0) -> dict[str, object]:
        name = _text(client_name, "Codex adapter client name")
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        return {"method": "initialize", "id": request_id, "params": {"clientInfo": {"name": name, "title": name, "version": "1"}}}

    @staticmethod
    def initialized_notification() -> dict[str, object]:
        return {"method": "initialized", "params": {}}

    def plan_topology_dispatch(self, packet: TopologyDispatchPacket) -> AdapterExecutionPlan:
        """Expose the exact host boundary without emitting a create-thread call."""
        if not isinstance(packet, TopologyDispatchPacket):
            raise InvariantError("Codex topology dispatch requires a typed ready-wave packet")
        return AdapterExecutionPlan(
            AdapterPlanStatus.BLOCKED,
            self.matrix.adapter_id,
            packet.packet_digest,
            self.matrix.digest(),
            blocker="required capability is instruction-only: swarm.topology_dispatch",
            claim_limit=packet.claim_limit,
        )

    def thread_request(self, plan: AdapterExecutionPlan, request: ExecutionAdapterRequest, *, request_id: int = 1, thread_id: str = "") -> dict[str, object]:
        self._require_ready(plan, request)
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        params: dict[str, object] = {}
        if thread_id:
            params["threadId"] = _text(thread_id, "Codex thread id")
            method = "thread/resume"
        else:
            method = "thread/start"
            params["cwd"] = request.cwd
        if request.model:
            params["model"] = request.model
        if request.approval_policy:
            params["approvalPolicy"] = request.approval_policy
        if request.sandbox:
            params["sandbox"] = request.sandbox
        return {"method": method, "id": request_id, "params": params}

    def turn_request(self, plan: AdapterExecutionPlan, request: ExecutionAdapterRequest, *, thread_id: str, instruction: str, request_id: int = 2) -> dict[str, object]:
        self._require_ready(plan, request)
        target = _text(thread_id, "Codex thread id")
        if not isinstance(instruction, str) or sha256(instruction.encode("utf-8")).hexdigest() != request.instruction_digest:
            raise InvariantError("Codex turn instruction does not match the authorized request digest")
        if not isinstance(request_id, int) or request_id < 0:
            raise InvariantError("Codex adapter request id must be non-negative")
        params: dict[str, object] = {"threadId": target, "input": [{"type": "text", "text": instruction}], "cwd": request.cwd}
        if request.model:
            params["model"] = request.model
        if request.approval_policy:
            params["approvalPolicy"] = request.approval_policy
        return {"method": "turn/start", "id": request_id, "params": params}

    def translate_event(self, message: Mapping[str, object]) -> AdapterEvent:
        if not isinstance(message, Mapping):
            raise InvariantError("Codex adapter event must be a JSON object")
        method = str(message.get("method") or "unknown")
        params = message.get("params")
        body = params if isinstance(params, Mapping) else {}
        thread = body.get("thread") if isinstance(body.get("thread"), Mapping) else {}
        turn = body.get("turn") if isinstance(body.get("turn"), Mapping) else {}
        item = body.get("item") if isinstance(body.get("item"), Mapping) else {}
        digest = _canonical_digest(message)
        event = AdapterEvent(
            method=method,
            thread_id=str(body.get("threadId") or thread.get("id") or ""),
            turn_id=str(body.get("turnId") or turn.get("id") or ""),
            item_id=str(body.get("itemId") or item.get("id") or ""),
            status=str(body.get("status") or turn.get("status") or item.get("status") or ""),
            evidence_digest=digest,
        )
        object.__setattr__(event, "_authority", _HOST_EVENT_AUTHORITY)
        return event

    @staticmethod
    def translate_service_tier_receipt(message: Mapping[str, object], *, request_digest: str, observed_at_ms: int) -> HostServiceTierReceipt:
        if not isinstance(message, Mapping):
            raise InvariantError("Codex served-tier response must be a JSON object")
        result = message.get("result")
        body = result if isinstance(result, Mapping) else {}
        tier = str(body.get("service_tier") or body.get("serviceTier") or "")
        receipt = HostServiceTierReceipt(request_digest, tier, _canonical_digest(message), observed_at_ms)
        object.__setattr__(receipt, "_authority", _HOST_RESPONSE_AUTHORITY)
        return receipt

    def _require_ready(self, plan: AdapterExecutionPlan, request: ExecutionAdapterRequest) -> None:
        if not isinstance(plan, AdapterExecutionPlan) or not plan.ready or plan.adapter_id != self.matrix.adapter_id:
            raise InvariantError("Codex adapter wire messages require a ready execution plan")
        if plan.request_digest != request.request_digest or plan.capability_matrix_digest != self.matrix.digest():
            raise InvariantError("Codex adapter plan does not match the exact request or capability matrix")


class AdapterRegistry:
    """Explicit adapter selection; missing adapters never trigger a fallback."""

    def __init__(self, adapters: tuple[ExecutionAdapter, ...] = ()) -> None:
        if any(not isinstance(adapter, ExecutionAdapter) for adapter in adapters):
            raise InvariantError("adapter registry accepts execution adapters only")
        self._adapters = {adapter.matrix.adapter_id: adapter for adapter in adapters}
        if len(self._adapters) != len(adapters):
            raise InvariantError("adapter registry ids must be distinct")

    def capability_matrix(self, adapter_id: str) -> AdapterCapabilityMatrix | None:
        adapter = self._adapters.get(_text(adapter_id, "adapter id"))
        return None if adapter is None else adapter.matrix

    def plan(self, request: ExecutionAdapterRequest) -> AdapterExecutionPlan:
        if not isinstance(request, ExecutionAdapterRequest):
            raise InvariantError("adapter registry requires a typed execution request")
        adapter = self._adapters.get(request.adapter_id)
        if adapter is None:
            return AdapterExecutionPlan(
                AdapterPlanStatus.DISABLED,
                request.adapter_id,
                request.request_digest,
                "0" * 64,
                blocker="optional execution adapter is not configured",
            )
        return adapter.plan(request)
