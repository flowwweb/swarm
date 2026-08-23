#!/usr/bin/env python3
"""Validate SWARM durable-goal and alert-only WATCHDOG contracts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import RequestDue, Role, Swarm, WatchdogScope, WatchdogSignal
from runtime.request_ledger import RequestStore


MANDATORY_DURABLE_GOAL_ROLES = frozenset({"ctrl", "lead", "specialist", "architect"})


def _canonical_role(role: str) -> str:
    if not isinstance(role, str) or not role.strip():
        raise ValueError("role must be a non-empty string")
    canonical = role.strip().casefold()
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


def request_bridge(envelope: dict) -> dict:
    """Read the same private ledger used by the runtime; never grants host authority."""
    if not isinstance(envelope,dict) or set(envelope)-{"operation","repo_root","now"}: raise ValueError("request envelope has unknown fields")
    operation, root = envelope.get("operation"), envelope.get("repo_root")
    if operation not in {"list","audit"} or not isinstance(root,str) or not root or not Path(root).is_absolute(): raise ValueError("standalone request bridge requires read-only list/audit and an absolute repo root")
    store=RequestStore(Path(root)); state,digest,attached=store.peek(); swarm=Swarm(); records=swarm._validate_request_state(state); audit=swarm._request_audit_from(state,digest,records,int(envelope.get("now",0))); result={"attached":attached,"sequence":audit.sequence,"digest":audit.digest,"records":[{"id":item.id,"task_id":item.task_id,"owner":item.accepted_owner,"state":item.state.value,"due_at":item.next_due_at} for item in audit.records]}
    if operation == "audit": result.update({"unresolved_ids": audit.unresolved_ids, "orphaned_ids": audit.orphaned_ids, "unsurfaced_ids": audit.unsurfaced_ids, "idle_ids": audit.idle_ids, "blocked_ids": audit.blocked_ids, "provisional_stage_ids": audit.provisional_stage_ids,"integrity_signals":[{"request_id":item.request_id,"scope":item.scope.value,"signal":item.signal.value,"route":item.route.value} for item in audit.integrity_signals]})
    return result

def register(swarm:Swarm, stage_id:str, decision_event_receipt:str, *, accepted_at:int, due:RequestDue):
    """Named live bridge; serialized callers cannot mint authority."""
    if not isinstance(swarm,Swarm): raise ValueError("register requires the current live Swarm")
    return swarm.accept_request(Role.CTRL,stage_id,decision_event_receipt,accepted_at=accepted_at,due=due)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("forward-test", "request"))
    args = parser.parse_args()
    if args.command == "forward-test":
        print(json.dumps(forward_cases(), sort_keys=True))
    if args.command == "request":
        try:
            envelope=json.load(sys.stdin); print(json.dumps(request_bridge(envelope),sort_keys=True,separators=(",",":")))
        except (ValueError, OSError, json.JSONDecodeError) as error:
            print(json.dumps({"error":str(error)},sort_keys=True,separators=(",",":"))); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
