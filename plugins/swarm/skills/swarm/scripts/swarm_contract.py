#!/usr/bin/env python3
"""Validate SWARM durable-goal and alert-only WATCHDOG contracts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import WatchdogScope, WatchdogSignal


MANDATORY_DURABLE_GOAL_ROLES = frozenset({"ctrl", "lead", "specialist", "architect"})


def _canonical_role(role: str) -> str:
    if not isinstance(role, str) or not role.strip():
        raise ValueError("role must be a non-empty string")
    canonical = role.strip().casefold()
    if canonical == "mother":
        return "specialist"
    return "specialist" if canonical.startswith("specialist:") else canonical


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
class WatchdogObservation:
    scope: WatchdogScope
    signal: WatchdogSignal
    evidence: str


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


def watchdog_decision(observation: WatchdogObservation) -> Decision:
    """Render one alert-only WATCHDOG result without selecting an action."""

    if not observation.evidence.strip():
        raise ValueError("watchdog evidence must be non-empty")
    if observation.signal is WatchdogSignal.CLEAR:
        return Decision("clear", f"{observation.scope.value}: evidence is clear; internal receipt only")
    return Decision(
        observation.signal.value.casefold(),
        f"{observation.scope.value}: alert follows the runtime-validated route; WATCHDOG takes no action",
    )


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
        "ctrl_startup_no_goal": goal_decision("ctrl", None, "portfolio"),
        "mother_specialist_startup": goal_decision("specialist:mother", None, "coordination-truth"),
        "lead_resume_matching_goal": goal_decision("lead", matching, "lane-a"),
        "lead_mixed_case_matching_goal": goal_decision("LeAd", matching, "lane-a"),
        "architect_startup": goal_decision("architect", None, "system"),
        "watchdog_clear": watchdog_decision(
            WatchdogObservation(WatchdogScope.TRAJECTORY, WatchdogSignal.CLEAR, "milestone proof")
        ),
        "watchdog_attention": watchdog_decision(
            WatchdogObservation(WatchdogScope.FLOW_INTEGRITY, WatchdogSignal.ATTENTION, "material collision")
        ),
        "watchdog_blocker": watchdog_decision(
            WatchdogObservation(WatchdogScope.OUTCOME_INTEGRITY, WatchdogSignal.BLOCKER, "acceptance proof missing")
        ),
        "missing_goal_tool": goal_decision(
            "ctrl", None, "portfolio", goal_controls_available=False
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
