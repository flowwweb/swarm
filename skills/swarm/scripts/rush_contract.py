#!/usr/bin/env python3
"""Validate RUSH's non-disableable role-goal and heartbeat decisions."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.core import heartbeat_action


MANDATORY_DURABLE_GOAL_ROLES = frozenset({"mother", "lead", "architect"})


def _canonical_role(role: str) -> str:
    if not isinstance(role, str) or not role.strip():
        raise ValueError("role must be a non-empty string")
    return role.strip().casefold()


@dataclass(frozen=True)
class Goal:
    role: str
    objective_key: str
    objective: str
    stopping_condition: str
    authority_boundary: str
    required_proof: str
    complete: bool = False


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


@dataclass(frozen=True)
class LaneObservation:
    title: str
    owner_update: bool
    material_change: bool
    unchanged_updates: int
    recovery_attempts: int


def goal_decision(
    role: str,
    current_goal: Goal | None,
    expected_objective_key: str,
    *,
    goal_controls_available: bool = True,
) -> Decision:
    """Return the required host-level action without creating or changing a goal."""

    requested_role = _canonical_role(role)
    if requested_role not in MANDATORY_DURABLE_GOAL_ROLES:
        return Decision("not_required", "finite role does not own a durable goal")
    if not goal_controls_available:
        return Decision("blocked", f"goal controls unavailable for {requested_role.upper()}")
    if current_goal is None or current_goal.complete:
        return Decision("create", "no unfinished matching goal exists")
    if (
        _canonical_role(current_goal.role) == requested_role
        and current_goal.objective_key == expected_objective_key
    ):
        return Decision("continue", "matching unfinished goal exists")
    return Decision("escalate", "conflicting unfinished goal must be reconciled")


def heartbeat_decision(
    observation: LaneObservation,
    *,
    stall_after_updates: int = 2,
) -> Decision:
    """Classify one passive observation; heartbeat itself never wakes a lane."""

    action=heartbeat_action(owner_update=observation.owner_update,material_change=observation.material_change,unchanged_updates=observation.unchanged_updates,recovery_attempts=observation.recovery_attempts,stall_after_updates=stall_after_updates)
    reason={"observe":"healthy, silent, or below threshold","recover":"one bounded same-surface recovery is due","release":"unchanged after the one recovery; return blocker and unblock condition"}[action]
    return Decision(action,reason)


def forward_cases() -> dict[str, dict[str, str]]:
    matching = Goal(
        role="LEAD",
        objective_key="lane-a",
        objective="integrate lane A",
        stopping_condition="review-approved integration receipt",
        authority_boundary="named lane only",
        required_proof="independent review and deployment proof",
    )
    cases = {
        "mother_startup_no_goal": goal_decision("mother", None, "portfolio"),
        "mother_uppercase_no_goal": goal_decision("MOTHER", None, "portfolio"),
        "lead_resume_matching_goal": goal_decision("lead", matching, "lane-a"),
        "lead_mixed_case_matching_goal": goal_decision("LeAd", matching, "lane-a"),
        "architect_startup": goal_decision("architect", None, "system"),
        "heartbeat_healthy": heartbeat_decision(
            LaneObservation("BUILD", True, True, 0, 0)
        ),
        "heartbeat_stalled": heartbeat_decision(
            LaneObservation("BUILD", True, False, 2, 0)
        ),
        "heartbeat_second_unchanged": heartbeat_decision(
            LaneObservation("BUILD", True, False, 3, 1)
        ),
        "missing_goal_tool": goal_decision(
            "mother", None, "portfolio", goal_controls_available=False
        ),
        "architect_uppercase_missing_goal_tool": goal_decision(
            "ARCHITECT", None, "system", goal_controls_available=False
        ),
    }
    return {name: asdict(decision) for name, decision in cases.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("forward-test",))
    args = parser.parse_args()
    if args.command == "forward-test":
        print(json.dumps(forward_cases(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
