"""Fail-closed visible-lane topology and title contracts.

This module plans a SWARM shape. It does not create, rename, pin, reorder, or
archive host tasks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re

from .core import InvariantError, ProfessionAssignment, Role


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
        if parent and not _LANE_ID.fullmatch(parent):
            raise InvariantError("parent lane id must be a safe stable lane id")
        if review_target and not _LANE_ID.fullmatch(review_target):
            raise InvariantError("review target id must be a safe stable lane id")
        if not isinstance(self.direct_production, bool):
            raise InvariantError("direct production must be true or false")
        if self.structural_role is Role.CTRL:
            if parent or self.profession is not None or boundary or artifact or review_target or self.direct_production:
                raise InvariantError("CTRL is the sole administrator and cannot be materialized as a profession or producer lane")
            title = f"{icon}CTRL - {responsibility}"
        else:
            if not parent or not isinstance(self.profession, ProfessionAssignment):
                raise InvariantError("every visible LEAD and DOER requires a parent and typed profession")
            if self.structural_role is Role.LEAD:
                if not boundary:
                    raise InvariantError("LEAD requires one named mutable boundary")
                if self.direct_production != bool(artifact):
                    raise InvariantError("LEAD direct production requires one declared artifact, and only direct production may declare it")
            else:
                if boundary or not artifact or not self.direct_production:
                    raise InvariantError("DOER requires one bounded artifact and cannot own a mutable lane boundary")
            title = f"{icon}{self.profession.label} {self.structural_role.value} - {responsibility}"
        object.__setattr__(self, "responsibility", responsibility)
        object.__setattr__(self, "parent_lane_id", parent)
        object.__setattr__(self, "icon", icon)
        object.__setattr__(self, "mutable_boundary", boundary)
        object.__setattr__(self, "artifact_id", artifact)
        object.__setattr__(self, "review_target_id", review_target)
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
            if lane.structural_role is Role.LEAD and not children[lane.lane_id] and not lane.direct_production:
                raise InvariantError("leaf LEAD without a direct artifact is unnecessary; use a DOER or declare direct production")
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
