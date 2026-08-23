"""Fail-closed visible-lane topology and title contracts.

This module plans a SWARM shape. It does not create, rename, pin, reorder, or
archive host tasks.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
import re

from .core import ArtifactIdentity, InvariantError, ProfessionAssignment, ProofState, Role, SubordinateBoundaryFacts


_LANE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_STRUCTURAL_ROLES = frozenset({Role.CTRL, Role.LEAD, Role.DOER})


def _single_line(value: str, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()) or any(character in value for character in "\r\n\t"):
        raise InvariantError(f"{label} must be {'empty or ' if allow_empty else ''}single-line text")
    return value.strip()


@dataclass(frozen=True)
class LaneMaterialization:
    """One visible CTRL, LEAD, or DOER lane before host materialization."""

    lane_id: str
    structural_role: Role
    responsibility: str
    parent_lane_id: str = ""
    profession: ProfessionAssignment | None = None
    icon: str = ""
    mutable_boundary: str = ""
    artifact_id: str = ""
    review_target_id: str = ""
    direct_production: bool = False
    durable_boundary: SubordinateBoundaryFacts | None = None
    requested_title: str = ""
    title: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.lane_id, str) or not _LANE_ID.fullmatch(self.lane_id):
            raise InvariantError("lane materialization requires a safe stable lane id")
        if self.structural_role not in _STRUCTURAL_ROLES:
            raise InvariantError("visible structural authority is exactly CTRL, LEAD, or DOER")
        responsibility = _single_line(self.responsibility, "lane responsibility")
        parent = _single_line(self.parent_lane_id, "parent lane id", allow_empty=True)
        icon = _single_line(self.icon, "lane icon", allow_empty=True)
        boundary = _single_line(self.mutable_boundary, "mutable boundary", allow_empty=True)
        artifact = _single_line(self.artifact_id, "artifact id", allow_empty=True)
        review_target = _single_line(self.review_target_id, "review target id", allow_empty=True)
        requested_title = _single_line(self.requested_title, "requested lane title", allow_empty=True)
        if parent and not _LANE_ID.fullmatch(parent):
            raise InvariantError("parent lane id must be a safe stable lane id")
        if review_target and not _LANE_ID.fullmatch(review_target):
            raise InvariantError("review target id must be a safe stable lane id")
        if not isinstance(self.direct_production, bool):
            raise InvariantError("direct production must be true or false")
        if self.structural_role is Role.CTRL:
            if parent or self.profession is not None or boundary or artifact or review_target or self.direct_production or self.durable_boundary is not None:
                raise InvariantError("CTRL is the sole administrator and cannot be materialized as a profession or producer lane")
            title = f"{icon}CTRL - {responsibility}"
        else:
            if not parent or not isinstance(self.profession, ProfessionAssignment) or not icon:
                raise InvariantError("every visible LEAD and DOER requires a parent, typed profession, and configured icon")
            if self.structural_role is Role.LEAD:
                if not boundary:
                    raise InvariantError("LEAD requires one named mutable boundary")
                if self.direct_production != bool(artifact):
                    raise InvariantError("LEAD direct production requires one declared artifact, and only direct production may declare it")
                if self.durable_boundary is not None and not isinstance(self.durable_boundary, SubordinateBoundaryFacts):
                    raise InvariantError("LEAD durable-boundary evidence must use typed subordinate boundary facts")
                if not self.direct_production and not (
                    isinstance(self.durable_boundary, SubordinateBoundaryFacts)
                    and self.durable_boundary.requires_nested_lead()
                ):
                    raise InvariantError("LEAD requires typed durable-boundary evidence or one declared direct artifact")
            else:
                if boundary or not artifact or not self.direct_production or self.durable_boundary is not None:
                    raise InvariantError("DOER requires one bounded artifact and cannot own a mutable lane boundary")
            title = f"{icon}{self.profession.label} {self.structural_role.value} - {responsibility}"
        if requested_title and requested_title != title:
            raise InvariantError("visible lane title must equal the generated icon, profession, structural role, and responsibility")
        object.__setattr__(self, "responsibility", responsibility)
        object.__setattr__(self, "parent_lane_id", parent)
        object.__setattr__(self, "icon", icon)
        object.__setattr__(self, "mutable_boundary", boundary)
        object.__setattr__(self, "artifact_id", artifact)
        object.__setattr__(self, "review_target_id", review_target)
        object.__setattr__(self, "requested_title", requested_title)
        object.__setattr__(self, "title", title)


@dataclass(frozen=True)
class TopologyMaterializationPlan:
    """Small immutable preflight for a visible SWARM task shape."""

    lanes: tuple[LaneMaterialization, ...]
    preferred_lane_width: int = 3
    span_exception_receipt: str = ""
    plan_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.lanes, tuple) or not self.lanes or any(not isinstance(item, LaneMaterialization) for item in self.lanes):
            raise InvariantError("topology materialization requires typed visible lanes")
        if not isinstance(self.preferred_lane_width, int) or isinstance(self.preferred_lane_width, bool) or not 1 <= self.preferred_lane_width <= 8:
            raise InvariantError("preferred lane width must be an integer from 1 to 8")
        span_receipt = _single_line(self.span_exception_receipt, "span exception receipt", allow_empty=True)
        by_id = {lane.lane_id: lane for lane in self.lanes}
        if len(by_id) != len(self.lanes):
            raise InvariantError("visible lane ids must be unique")
        roots = tuple(lane for lane in self.lanes if lane.structural_role is Role.CTRL)
        if len(roots) != 1 or roots[0].parent_lane_id:
            raise InvariantError("topology requires exactly one dependency-free CTRL administrator")
        root = roots[0]
        children: dict[str, list[LaneMaterialization]] = {lane_id: [] for lane_id in by_id}
        for lane in self.lanes:
            if lane is root:
                continue
            parent = by_id.get(lane.parent_lane_id)
            if parent is None:
                raise InvariantError("visible lane parent must exist in the same topology plan")
            if parent.structural_role is Role.DOER:
                raise InvariantError("DOER may use leaf subagents but cannot own another visible lane")
            children[parent.lane_id].append(lane)
        for lane in self.lanes:
            seen: set[str] = set()
            current = lane
            while current.parent_lane_id:
                if current.lane_id in seen:
                    raise InvariantError("visible topology cannot contain a parent cycle")
                seen.add(current.lane_id)
                current = by_id[current.parent_lane_id]
        if len(children[root.lane_id]) > self.preferred_lane_width and not span_receipt:
            raise InvariantError("CTRL fanout exceeds preferred lane width without a concrete span exception receipt")
        for lane in self.lanes:
            if lane.review_target_id:
                if lane.review_target_id not in by_id or lane.review_target_id == lane.lane_id:
                    raise InvariantError("independent review requires a separate existing producer lane")
        artifact_owners = [lane.artifact_id for lane in self.lanes if lane.artifact_id]
        if len(artifact_owners) != len(set(artifact_owners)):
            raise InvariantError("each bounded artifact must have one visible accountable owner")
        for siblings in children.values():
            lead_boundaries = [lane.mutable_boundary for lane in siblings if lane.structural_role is Role.LEAD]
            if len(lead_boundaries) != len(set(lead_boundaries)):
                raise InvariantError("sibling LEADs cannot duplicate the same mutable boundary")
        payload = {
            "preferred_lane_width": self.preferred_lane_width,
            "span_exception_receipt": span_receipt,
            "lanes": tuple(
                {
                    "id": lane.lane_id,
                    "role": lane.structural_role.value,
                    "profession": None if lane.profession is None else lane.profession.profession_id,
                    "title": lane.title,
                    "parent": lane.parent_lane_id,
                    "boundary": lane.mutable_boundary,
                    "artifact": lane.artifact_id,
                    "review_target": lane.review_target_id,
                    "direct_production": lane.direct_production,
                    "durable_boundary": None if lane.durable_boundary is None else {
                        "independent_ownership": lane.durable_boundary.independent_durable_ownership,
                        "heartbeat": lane.durable_boundary.heartbeat_obligation,
                        "integration_review": lane.durable_boundary.integration_review_surface,
                        "worktree": lane.durable_boundary.worktree_isolation,
                        "cross_lane": lane.durable_boundary.cross_lane_dependency,
                        "team": lane.durable_boundary.own_team,
                    },
                }
                for lane in sorted(self.lanes, key=lambda item: item.lane_id)
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        object.__setattr__(self, "span_exception_receipt", span_receipt)
        object.__setattr__(self, "plan_digest", sha256(encoded.encode("utf-8")).hexdigest())

    def disclosure(self) -> tuple[tuple[str, str, str, str], ...]:
        """Return the compact human-visible task identity/title/parent/artifact packet."""
        return tuple(
            (lane.lane_id, lane.title, lane.parent_lane_id, lane.artifact_id or lane.mutable_boundary)
            for lane in self.lanes
        )


class TopologyHostCapability(StrEnum):
    INSTRUCTION_ONLY_UNSUPPORTED = "instruction_only_unsupported"


class TopologyTransportOutcome(StrEnum):
    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


@dataclass(frozen=True)
class TopologyArtifactFreezeReceipt:
    """Runtime-issued binding from accepted proof state to one planned review lane."""

    producer_lane_id: str
    review_lane_id: str
    topology_plan_digest: str
    artifact: ArtifactIdentity
    artifact_content_digest: str
    proof_plan_digest: str
    review_receipt_digest: str
    gate_receipt_digests: tuple[str, ...]
    state: ProofState
    observed_at_ms: int
    valid_until_ms: int
    claim_limit: str
    _authority: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.producer_lane_id, "freeze producer lane"),
            (self.review_lane_id, "freeze review lane"),
        ):
            if not _LANE_ID.fullmatch(value):
                raise InvariantError(f"{label} requires a safe stable lane id")
        for value, label in (
            (self.topology_plan_digest, "freeze topology plan"),
            (self.artifact_content_digest, "freeze artifact content"),
            (self.proof_plan_digest, "freeze proof plan"),
            (self.review_receipt_digest, "freeze review receipt"),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise InvariantError(f"{label} must be a SHA-256 digest")
        if not isinstance(self.artifact, ArtifactIdentity) or not self.artifact.observables:
            raise InvariantError("topology freeze requires an immutable content-observed ArtifactIdentity")
        if self.artifact_content_digest != self.artifact.content_address():
            raise InvariantError("topology freeze artifact digest must match the exact content-addressed identity")
        if not self.gate_receipt_digests or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in self.gate_receipt_digests):
            raise InvariantError("topology freeze requires exact gate receipt digests")
        if len(set(self.gate_receipt_digests)) != len(self.gate_receipt_digests):
            raise InvariantError("topology freeze gate receipt digests must be distinct")
        if self.state is not ProofState.ACCEPTED:
            raise InvariantError("topology freeze requires current ACCEPTED proof state")
        if not isinstance(self.observed_at_ms, int) or not isinstance(self.valid_until_ms, int) or self.observed_at_ms < 0 or self.valid_until_ms <= self.observed_at_ms:
            raise InvariantError("topology freeze requires a bounded freshness interval")
        object.__setattr__(self, "claim_limit", _single_line(self.claim_limit, "topology freeze claim limit"))


@dataclass(frozen=True)
class TopologyDispatchPacket:
    """Current ready wave for a host adapter; never a host mutation itself."""

    plan_digest: str
    root_lane_id: str
    lanes: tuple[LaneMaterialization, ...]
    host_capability: TopologyHostCapability
    claim_limit: str
    packet_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.plan_digest):
            raise InvariantError("topology dispatch packet requires the exact plan digest")
        if not _LANE_ID.fullmatch(self.root_lane_id):
            raise InvariantError("topology dispatch packet requires one safe root CTRL id")
        if not self.lanes or any(not isinstance(lane, LaneMaterialization) or lane.structural_role is Role.CTRL for lane in self.lanes):
            raise InvariantError("topology dispatch packet requires one or more non-root visible lanes")
        if len({lane.lane_id for lane in self.lanes}) != len(self.lanes):
            raise InvariantError("topology dispatch packet lane ids must be unique")
        if self.host_capability is not TopologyHostCapability.INSTRUCTION_ONLY_UNSUPPORTED:
            raise InvariantError("host topology dispatch capability is not implemented")
        claim_limit = _single_line(self.claim_limit, "topology dispatch claim limit")
        payload = {
            "plan": self.plan_digest,
            "root": self.root_lane_id,
            "lanes": tuple((lane.lane_id, lane.title, lane.parent_lane_id, lane.artifact_id, lane.review_target_id) for lane in self.lanes),
            "capability": self.host_capability.value,
            "claim_limit": claim_limit,
        }
        object.__setattr__(self, "claim_limit", claim_limit)
        object.__setattr__(self, "packet_digest", sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest())


@dataclass(frozen=True)
class TopologyLaneReservation:
    lane_id: str
    packet_digest: str
    reservation_digest: str
    outcome: TopologyTransportOutcome | None = None
    host_task_id: str = ""


@dataclass(frozen=True)
class TopologyConfirmedLane:
    lane_id: str
    host_task_id: str
    confirmation_digest: str

    def __post_init__(self) -> None:
        if not _LANE_ID.fullmatch(self.lane_id):
            raise InvariantError("confirmed topology lane requires a safe stable lane id")
        object.__setattr__(self, "host_task_id", _single_line(self.host_task_id, "confirmed host task id"))
        if not re.fullmatch(r"[0-9a-f]{64}", self.confirmation_digest):
            raise InvariantError("confirmed topology lane requires an exact confirmation digest")


class TopologyDispatchPreflight:
    """Deterministic ready-wave and retry guard; it never calls the host."""

    def __init__(
        self,
        *,
        root_lane_id: str,
        root_host_task_id: str,
        freeze_authority: object,
        freeze_validator: Callable[[TopologyArtifactFreezeReceipt], bool],
    ) -> None:
        if not _LANE_ID.fullmatch(root_lane_id) or not isinstance(root_host_task_id, str) or not root_host_task_id.strip() or freeze_authority is None or not callable(freeze_validator):
            raise InvariantError("topology preflight requires one confirmed root and runtime freeze validator")
        self._pending: dict[str, TopologyLaneReservation] = {}
        root_digest = sha256(f"root:{root_lane_id}:{root_host_task_id}".encode("utf-8")).hexdigest()
        self._confirmed: dict[str, TopologyConfirmedLane] = {
            root_lane_id: TopologyConfirmedLane(root_lane_id, root_host_task_id, root_digest)
        }
        self._root_lane_id = root_lane_id
        self._freeze_authority = freeze_authority
        self._freeze_validator = freeze_validator

    def prepare(
        self,
        plan: TopologyMaterializationPlan,
        *,
        ready_lane_ids: tuple[str, ...],
        artifact_freeze_receipts: tuple[TopologyArtifactFreezeReceipt, ...] = (),
    ) -> TopologyDispatchPacket:
        if not isinstance(plan, TopologyMaterializationPlan):
            raise InvariantError("topology preflight requires a typed materialization plan")
        if not ready_lane_ids or len(set(ready_lane_ids)) != len(ready_lane_ids):
            raise InvariantError("topology preflight requires one distinct current ready wave")
        by_id = {lane.lane_id: lane for lane in plan.lanes}
        roots = tuple(lane for lane in plan.lanes if lane.structural_role is Role.CTRL)
        root = roots[0]
        if root.lane_id != self._root_lane_id or root.lane_id not in self._confirmed:
            raise InvariantError("topology plan root must match the already host-confirmed CTRL")
        if any(not isinstance(receipt, TopologyArtifactFreezeReceipt) for receipt in artifact_freeze_receipts):
            raise InvariantError("review readiness requires typed runtime-issued artifact freeze receipts")
        lanes: list[LaneMaterialization] = []
        for lane_id in ready_lane_ids:
            lane = by_id.get(lane_id)
            if lane is None or lane.structural_role is Role.CTRL:
                raise InvariantError("ready wave may contain only known non-root visible lanes")
            if lane.lane_id in self._confirmed:
                raise InvariantError("already confirmed topology lane cannot be prepared again")
            if lane.parent_lane_id not in self._confirmed:
                raise InvariantError("ready lane parent must already be host-confirmed before child dispatch")
            if lane.review_target_id:
                producer = by_id[lane.review_target_id]
                matches = tuple(
                    receipt
                    for receipt in artifact_freeze_receipts
                    if receipt.producer_lane_id == producer.lane_id
                    and receipt.review_lane_id == lane.lane_id
                    and receipt.topology_plan_digest == plan.plan_digest
                )
                if len(matches) != 1:
                    raise InvariantError("review lane requires one exact producer/plan/review artifact freeze receipt")
                freeze = matches[0]
                if freeze._authority is not self._freeze_authority or freeze.artifact.base != producer.artifact_id or not self._freeze_validator(freeze):
                    raise InvariantError("review artifact freeze receipt is untrusted, stale, rejected, mutable, or bound to the wrong producer")
            lanes.append(lane)
        return TopologyDispatchPacket(
            plan.plan_digest,
            root.lane_id,
            tuple(lanes),
            TopologyHostCapability.INSTRUCTION_ONLY_UNSUPPORTED,
            "The packet is a local instruction-only preflight; current Codex create_thread cannot consume or enforce it, so live dispatch remains UNVERIFIED.",
        )

    def reserve(self, packet: TopologyDispatchPacket) -> tuple[TopologyLaneReservation, ...]:
        if not isinstance(packet, TopologyDispatchPacket):
            raise InvariantError("topology reservation requires an exact dispatch packet")
        collisions = tuple(lane.lane_id for lane in packet.lanes if lane.lane_id in self._pending or lane.lane_id in self._confirmed)
        if collisions:
            raise InvariantError(f"pending topology reservation must resolve or be explicitly cancelled before retry: {collisions[0]}")
        reservations = tuple(
            TopologyLaneReservation(
                lane.lane_id,
                packet.packet_digest,
                sha256(f"{packet.packet_digest}:{lane.lane_id}".encode("utf-8")).hexdigest(),
            )
            for lane in packet.lanes
        )
        self._pending.update((reservation.lane_id, reservation) for reservation in reservations)
        return reservations

    def record_transport(
        self,
        reservation: TopologyLaneReservation,
        outcome: TopologyTransportOutcome,
        *,
        host_task_id: str = "",
    ) -> TopologyLaneReservation:
        current = self._pending.get(reservation.lane_id) if isinstance(reservation, TopologyLaneReservation) else None
        if current != reservation or not isinstance(outcome, TopologyTransportOutcome):
            raise InvariantError("topology transport result must match one exact pending reservation")
        if outcome is TopologyTransportOutcome.CONFIRMED:
            host_id = _single_line(host_task_id, "confirmed host task id")
            self._pending.pop(reservation.lane_id)
            confirmed = TopologyConfirmedLane(
                reservation.lane_id,
                host_id,
                sha256(f"{reservation.reservation_digest}:{host_id}".encode("utf-8")).hexdigest(),
            )
            self._confirmed[reservation.lane_id] = confirmed
            return TopologyLaneReservation(reservation.lane_id, reservation.packet_digest, reservation.reservation_digest, outcome, host_id)
        if host_task_id:
            raise InvariantError("ambiguous or failed topology transport cannot claim a host task id")
        pending = TopologyLaneReservation(reservation.lane_id, reservation.packet_digest, reservation.reservation_digest, outcome)
        self._pending[reservation.lane_id] = pending
        return pending

    def cancel(self, reservation: TopologyLaneReservation) -> None:
        current = self._pending.get(reservation.lane_id) if isinstance(reservation, TopologyLaneReservation) else None
        if current != reservation:
            raise InvariantError("topology cancellation must match one exact pending reservation")
        self._pending.pop(reservation.lane_id)

    def pending(self, lane_id: str) -> TopologyLaneReservation | None:
        return self._pending.get(_single_line(lane_id, "topology lane id"))

    def confirmed(self, lane_id: str) -> TopologyConfirmedLane | None:
        return self._confirmed.get(_single_line(lane_id, "topology lane id"))
