#!/usr/bin/env python3
"""Validate SWARM durable-goal and alert-only WATCHDOG contracts."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import RequestDue, Role, Swarm, WatchdogScope, WatchdogSignal
from runtime.core import RotationReadback, rotation_next_step
from runtime.request_ledger import RequestStore


MANDATORY_DURABLE_GOAL_ROLES = frozenset({"ctrl", "lead", "specialist", "architect"})


def _canonical_role(role: str) -> str:
    if not isinstance(role, str) or not role.strip():
        raise ValueError("role must be a non-empty string")
    canonical = role.strip().casefold()
    if canonical in {"lab", "factory"}: return "ctrl"
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
    use_goals: bool = True,
) -> Decision:
    """Return the required host-level action without creating or changing a goal."""

    if not isinstance(use_goals,bool): raise ValueError("use_goals must be a boolean")
    requested_role = _canonical_role(role)
    if requested_role == "ctrl" and not use_goals:
        return Decision("disabled", "explicit root goal persistence opt-out; bounded intake still required")
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

ROTATION_FIELDS = {"predecessor_id": str, "successor_id": str, "authorized": bool, "baseline_pinned": list,
                   "pinned": (list, type(None)), "successor_ack": bool, "expected_title": str,
                   "successor_title": (str, type(None)), "predecessor_archived": (bool, type(None)),
                   "predecessor_in_flight": bool, "user_keep_pinned": bool, "capabilities": list}


def predecessor_obligations(console_state: Path, predecessor_id: str) -> dict:
    """Read the existing execution journal read-only: active Auto leases and unread results owed by a CTRL."""
    uri = Path(console_state).resolve(strict=True).as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute("SELECT snapshot_json FROM execution_dispatch_state").fetchall()
    finally:
        connection.close()
    active = unread = 0
    for (encoded,) in rows:
        item = json.loads(encoded)
        observables = dict(tuple(pair) for pair in item.get("artifact", {}).get("observables", ()))
        if (item.get("artifact", {}).get("purpose") == "swarm-auto-continuation"
                and observables.get("ctrl_id") == predecessor_id
                and item.get("state") == "active" and not item.get("host_completed")):
            active += 1
        if (item.get("collecting_owner_id") == predecessor_id and item.get("request_digest")
                and item.get("result_observation") != "READABLE"):
            unread += 1
    return {"active_leases": active, "unread_results": unread}


def rotation_bridge(envelope: dict, console_state: Path | None = None) -> dict:
    """Return the next rotation step from the caller's fresh host readback; never mutates the host.

    With ``console_state``, retained Auto leases or unread results owed by the
    predecessor block unpin/archive regardless of the caller's flag.
    """
    if not isinstance(envelope, dict) or set(envelope) != set(ROTATION_FIELDS):
        raise ValueError("rotation readback requires exactly: " + ", ".join(sorted(ROTATION_FIELDS)))
    for key, kind in ROTATION_FIELDS.items():
        if type(envelope[key]) not in (kind if isinstance(kind, tuple) else (kind,)):
            raise ValueError(f"rotation readback field has the wrong type: {key}")
    for key in ("baseline_pinned", "pinned", "capabilities"):
        if envelope[key] is not None and not all(isinstance(item, str) and item for item in envelope[key]):
            raise ValueError(f"rotation readback list must hold task IDs or capability names: {key}")
    journal = None if console_state is None else predecessor_obligations(console_state, envelope["predecessor_id"])
    in_flight = envelope["predecessor_in_flight"] or bool(journal and (journal["active_leases"] or journal["unread_results"]))
    read = RotationReadback(**{**envelope, "baseline_pinned": tuple(envelope["baseline_pinned"]),
        "pinned": None if envelope["pinned"] is None else tuple(envelope["pinned"]),
        "capabilities": frozenset(envelope["capabilities"]), "predecessor_in_flight": in_flight})
    step = rotation_next_step(read)
    return {"status": step.status, "step": step.step, "reason": step.reason, "reorder_to": list(step.reorder_to),
            "journal": journal, "host_mutation_authorized_by_runtime": False}


def register(swarm:Swarm, stage_id:str, decision_event_receipt:str, *, accepted_at:int, due:RequestDue):
    """Named live bridge; serialized callers cannot mint authority."""
    if not isinstance(swarm,Swarm): raise ValueError("register requires the current live Swarm")
    return swarm.accept_request(Role.CTRL,stage_id,decision_event_receipt,accepted_at=accepted_at,due=due)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("forward-test", "request", "jev", "rotate"))
    parser.add_argument("--console-state", type=Path, help="rotate: read retained leases and unread results from this console journal")
    args = parser.parse_args()
    if args.command == "jev":
        from swarm_jev import main as jev_main
        return jev_main([])
    if args.command == "forward-test":
        print(json.dumps(forward_cases(), sort_keys=True))
    if args.command in {"request", "rotate"}:
        try:
            envelope=json.load(sys.stdin)
            result=request_bridge(envelope) if args.command == "request" else rotation_bridge(envelope, args.console_state)
            print(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=True))
        except (ValueError, OSError, sqlite3.Error, json.JSONDecodeError) as error:
            print(json.dumps({"error":str(error)},sort_keys=True,separators=(",",":"))); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
