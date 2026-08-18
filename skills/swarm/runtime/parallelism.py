"""Small, project-agnostic lane scheduling and progress-ledger primitives.

The scheduler models only facts that can justify serialization: a shared
mutable surface, an explicit ordering/proof dependency, an exclusive resource
lock, or observed host capacity.  Lane category is descriptive; it is never a
capacity queue by itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterable


class LaneType(StrEnum):
    CODE = "code"
    RESEARCH = "research"
    ARCHITECTURE = "architecture"
    AUTOMATION = "automation"
    PAYMENT = "payment"
    DESIGN = "design"
    QA = "qa"


class ResourceLockType(StrEnum):
    DESTRUCTIVE = "destructive"
    PROVIDER = "provider"
    EXCLUSIVE = "exclusive"


class CapacityException(StrEnum):
    CAPACITY_FULL = "capacity_full"


class WorkLedgerStage(StrEnum):
    REQUEST = "request"
    ASSIGNED = "assigned"
    PROGRESS = "progress"
    BLOCKED = "blocked"
    ACCEPTED = "accepted"
    CLOSED = "closed"


class ParallelismReason(StrEnum):
    INDEPENDENT = "independent"
    SHARED_SURFACE = "shared_surface"
    ORDERING_DEPENDENCY = "ordering_dependency"
    PROOF_DEPENDENCY = "proof_dependency"
    EXCLUSIVE_LOCK = "exclusive_lock"
    HOST_CAPACITY = "host_capacity"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _texts(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(_text(value, label) for value in values)
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must be distinct")
    return result


@dataclass(frozen=True)
class LaneResourceLock:
    """An explicit exclusive resource named by the current task contract."""

    kind: ResourceLockType
    key: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ResourceLockType):
            raise ValueError("resource lock requires a typed kind")
        _text(self.key, "resource lock key")


@dataclass(frozen=True)
class LaneSpec:
    """The minimum facts CTRL needs before deciding whether lanes can overlap."""

    id: str
    lane_type: LaneType
    objective: str
    owner: str
    mutable_surfaces: tuple[str, ...]
    proof_requirements: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    proof_dependencies: tuple[str, ...] = ()
    resource_locks: tuple[LaneResourceLock, ...] = ()
    host_capacity_key: str = "default"
    capacity_units: int = 1
    ledger_id: str = ""

    def __post_init__(self) -> None:
        _text(self.id, "lane id")
        if not isinstance(self.lane_type, LaneType):
            raise ValueError("lane requires a typed lane type")
        _text(self.objective, "lane objective")
        _text(self.owner, "lane owner")
        _texts(self.mutable_surfaces, "mutable surfaces")
        _texts(self.proof_requirements, "proof requirements")
        _texts(self.dependencies, "dependencies")
        _texts(self.proof_dependencies, "proof dependencies")
        if any(not isinstance(item, LaneResourceLock) for item in self.resource_locks):
            raise ValueError("resource locks must be typed")
        if len({(item.kind, item.key) for item in self.resource_locks}) != len(self.resource_locks):
            raise ValueError("resource locks must be distinct")
        _text(self.host_capacity_key, "host capacity key")
        if not isinstance(self.capacity_units, int) or self.capacity_units < 1:
            raise ValueError("lane capacity units must be a positive integer")
        if self.ledger_id:
            _text(self.ledger_id, "ledger id")


@dataclass(frozen=True)
class HostCapacity:
    """A point-in-time host receipt; it does not imply capacity for other keys."""

    key: str
    limit: int
    in_use: int
    observation: str
    release_condition: str

    def __post_init__(self) -> None:
        _text(self.key, "host capacity key")
        if not isinstance(self.limit, int) or self.limit < 1:
            raise ValueError("host capacity limit must be a positive integer")
        if not isinstance(self.in_use, int) or self.in_use < 0:
            raise ValueError("host capacity in-use count must be nonnegative")
        _text(self.observation, "host capacity observation")
        _text(self.release_condition, "host capacity release condition")

    @property
    def available_units(self) -> int:
        return max(0, self.limit - self.in_use)


@dataclass(frozen=True)
class CapacityPending:
    """An explicit pending record; this is never an implicit queue."""

    lane_id: str
    ledger_id: str
    owner: str
    exception: CapacityException
    host_key: str
    host_observation: str
    next_release_condition: str

    def __post_init__(self) -> None:
        _text(self.lane_id, "pending lane id")
        _text(self.ledger_id, "pending ledger id")
        _text(self.owner, "pending owner")
        if self.exception is not CapacityException.CAPACITY_FULL:
            raise ValueError("pending records require a typed capacity exception")
        _text(self.host_key, "pending host key")
        _text(self.host_observation, "pending host observation")
        _text(self.next_release_condition, "pending release condition")


@dataclass(frozen=True)
class LaneDecision:
    lane_id: str
    parallel_group: int | None
    reason: ParallelismReason
    blocking_lane_ids: tuple[str, ...] = ()
    pending: CapacityPending | None = None


@dataclass(frozen=True)
class ParallelismPlan:
    decisions: tuple[LaneDecision, ...]
    parallel_groups: tuple[tuple[str, ...], ...]
    pending: tuple[CapacityPending, ...] = ()

    def decision_for(self, lane_id: str) -> LaneDecision:
        for decision in self.decisions:
            if decision.lane_id == lane_id:
                return decision
        raise KeyError(lane_id)


def _conflict(left: LaneSpec, right: LaneSpec) -> ParallelismReason | None:
    if set(left.mutable_surfaces) & set(right.mutable_surfaces):
        return ParallelismReason.SHARED_SURFACE
    if right.id in left.dependencies or left.id in right.dependencies:
        return ParallelismReason.ORDERING_DEPENDENCY
    if right.id in left.proof_dependencies or left.id in right.proof_dependencies:
        return ParallelismReason.PROOF_DEPENDENCY
    left_locks = {(item.kind, item.key) for item in left.resource_locks}
    right_locks = {(item.kind, item.key) for item in right.resource_locks}
    if left_locks & right_locks:
        return ParallelismReason.EXCLUSIVE_LOCK
    return None


def plan_parallel_lanes(
    lanes: Iterable[LaneSpec],
    capacities: Iterable[HostCapacity],
    *,
    active: Iterable[LaneSpec] = (),
) -> ParallelismPlan:
    """Build deterministic overlap groups from actual conflicts and host facts.

    Each lane is considered independently.  A full capacity key blocks only
    lanes using that key; unrelated keys remain eligible for parallel groups.
    """
    candidates = tuple(lanes)
    if len({lane.id for lane in candidates}) != len(candidates):
        raise ValueError("lane ids must be distinct")
    active_lanes = tuple(active)
    capacity_values = tuple(capacities)
    capacity_by_key = {item.key: item for item in capacity_values}
    if len(capacity_by_key) != len(capacity_values):
        raise ValueError("host capacity keys must be distinct")
    known_ids = {lane.id for lane in (*active_lanes, *candidates)}
    for lane in candidates:
        missing = (set(lane.dependencies) | set(lane.proof_dependencies)) - known_ids
        if missing:
            raise ValueError(f"lane dependencies are not present in the graph: {sorted(missing)}")
    groups: list[list[LaneSpec]] = []
    decisions: list[LaneDecision] = []
    pending: list[CapacityPending] = []

    for lane in candidates:
        capacity = capacity_by_key.get(lane.host_capacity_key)
        used = capacity.in_use if capacity is not None else 0
        used += sum(item.capacity_units for item in active_lanes if item.host_capacity_key == lane.host_capacity_key)
        used += sum(item.capacity_units for group in groups for item in group if item.host_capacity_key == lane.host_capacity_key)
        if capacity is not None and used + lane.capacity_units > capacity.limit:
            record = CapacityPending(
                lane.id,
                lane.ledger_id or lane.id,
                lane.owner,
                CapacityException.CAPACITY_FULL,
                capacity.key,
                capacity.observation,
                capacity.release_condition,
            )
            pending.append(record)
            decisions.append(LaneDecision(lane.id, None, ParallelismReason.HOST_CAPACITY, pending=record))
            continue

        active_blockers = tuple(
            (prior, reason)
            for prior in active_lanes
            if (reason := _conflict(lane, prior)) is not None
        )
        if active_blockers:
            decisions.append(
                LaneDecision(
                    lane.id,
                    None,
                    active_blockers[0][1],
                    tuple(sorted(item[0].id for item in active_blockers)),
                )
            )
            continue

        blockers: list[tuple[int, LaneSpec, ParallelismReason]] = []
        for index, group in enumerate(groups):
            for prior in (*active_lanes, *group):
                reason = _conflict(lane, prior)
                if reason is not None:
                    blockers.append((index, prior, reason))
        if blockers:
            # A conflict is serialized after the latest conflicting group.
            group_index = max(item[0] for item in blockers) + 1
            while len(groups) <= group_index:
                groups.append([])
            groups[group_index].append(lane)
            first_reason = max(blockers, key=lambda item: item[0])[2]
            decisions.append(LaneDecision(lane.id, group_index, first_reason, tuple(sorted({item[1].id for item in blockers}))))
        else:
            if not groups:
                groups.append([])
            groups[0].append(lane)
            decisions.append(LaneDecision(lane.id, 0, ParallelismReason.INDEPENDENT))

    return ParallelismPlan(
        tuple(decisions),
        tuple(tuple(item.id for item in group) for group in groups if group),
        tuple(pending),
    )


_LEDGER_EDGES = {
    WorkLedgerStage.REQUEST: {WorkLedgerStage.ASSIGNED, WorkLedgerStage.BLOCKED, WorkLedgerStage.CLOSED},
    WorkLedgerStage.ASSIGNED: {WorkLedgerStage.PROGRESS, WorkLedgerStage.BLOCKED, WorkLedgerStage.CLOSED},
    WorkLedgerStage.PROGRESS: {WorkLedgerStage.PROGRESS, WorkLedgerStage.BLOCKED, WorkLedgerStage.ACCEPTED, WorkLedgerStage.CLOSED},
    WorkLedgerStage.BLOCKED: {WorkLedgerStage.PROGRESS, WorkLedgerStage.CLOSED},
    WorkLedgerStage.ACCEPTED: {WorkLedgerStage.CLOSED},
    WorkLedgerStage.CLOSED: set(),
}


@dataclass(frozen=True)
class WorkLedgerEntry:
    """One immutable identity carried through the request/progress lifecycle."""

    id: str
    objective: str
    owner: str
    stage: WorkLedgerStage = WorkLedgerStage.REQUEST
    history: tuple[WorkLedgerStage, ...] = (WorkLedgerStage.REQUEST,)
    host_observation: str = ""
    next_release_condition: str = ""
    proof_receipt: str = ""

    def __post_init__(self) -> None:
        _text(self.id, "work-ledger id")
        _text(self.objective, "work-ledger objective")
        _text(self.owner, "work-ledger owner")
        if not isinstance(self.stage, WorkLedgerStage) or not self.history or self.history[-1] is not self.stage:
            raise ValueError("work-ledger stage history is invalid")
        if any(not isinstance(item, WorkLedgerStage) for item in self.history):
            raise ValueError("work-ledger history must be typed")
        for left, right in zip(self.history, self.history[1:]):
            if right not in _LEDGER_EDGES[left]:
                raise ValueError("work-ledger transition is not permitted")
        if self.stage is WorkLedgerStage.BLOCKED:
            _text(self.host_observation, "blocked host observation")
            _text(self.next_release_condition, "blocked release condition")
        if self.stage in {WorkLedgerStage.ACCEPTED, WorkLedgerStage.CLOSED}:
            _text(self.proof_receipt, "accepted proof receipt")

    def transition(
        self,
        stage: WorkLedgerStage,
        *,
        host_observation: str = "",
        next_release_condition: str = "",
        proof_receipt: str = "",
    ) -> "WorkLedgerEntry":
        if not isinstance(stage, WorkLedgerStage) or stage not in _LEDGER_EDGES[self.stage]:
            raise ValueError(f"cannot transition {self.stage} to {stage}")
        return replace(
            self,
            stage=stage,
            history=(*self.history, stage),
            host_observation=host_observation,
            next_release_condition=next_release_condition,
            proof_receipt=proof_receipt,
        )


def new_work_ledger(id: str, objective: str, owner: str) -> WorkLedgerEntry:
    """Start a single ledger identity at the user request stage."""
    return WorkLedgerEntry(id, objective, owner)
