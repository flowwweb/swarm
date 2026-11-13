#!/usr/bin/env python3
"""Validate SWARM durable-goal and alert-only WATCHDOG contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import RequestDue, Role, Swarm, WatchdogScope, WatchdogSignal
from runtime.core import RotationReadback, rotation_next_step
from runtime.progress_events import ProgressLedger
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
ROTATION_RETIREMENT_FIELDS = {
    "project_id", "root_digest", "goal_id", "handoff_digest", "automation_id", "collector_id", "ack_digest",
    "release_receipt_id", "automation_target_id", "archive_receipt_id", "active_controller_ids",
    "readback_id", "observed_at_ms", "unresolved_operations",
}


def retain_rotation_claim(envelope: dict, root: Path) -> dict:
    """Retain caller claims in the existing Ledger; they never establish host facts."""
    claim = envelope.get("retirement")
    if not isinstance(claim, dict) or set(claim) != ROTATION_RETIREMENT_FIELDS:
        raise ValueError("rotation retirement claim requires the complete fixed field set")
    for key in ("project_id", "root_digest", "goal_id", "handoff_digest", "automation_id", "collector_id"):
        if type(claim[key]) is not str:
            raise ValueError(f"rotation retirement field must be a string: {key}")
    for key in ("ack_digest", "release_receipt_id", "automation_target_id", "archive_receipt_id", "readback_id"):
        if claim[key] is not None and type(claim[key]) is not str:
            raise ValueError(f"rotation retirement field must be a string or null: {key}")
    if type(claim["observed_at_ms"]) is not int:
        raise ValueError("rotation retirement observation time must be an integer")
    if type(claim["unresolved_operations"]) is not list or (
        claim["active_controller_ids"] is not None and type(claim["active_controller_ids"]) is not list
    ):
        raise ValueError("rotation retirement controller and unresolved-operation claims must be arrays or null")
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("rotation ledger root must be an existing absolute directory")
    observation = {key: claim[key] for key in (
        "ack_digest", "release_receipt_id", "automation_target_id", "archive_receipt_id",
        "active_controller_ids", "readback_id", "observed_at_ms", "unresolved_operations",
    )}
    observation.update({
        "pinned": envelope["pinned"], "predecessor_archived": envelope["predecessor_archived"],
        "predecessor_in_flight": envelope["predecessor_in_flight"], "successor_ack": envelope["successor_ack"],
        "user_keep_pinned": envelope["user_keep_pinned"],
        "observed_title_digest": None if envelope["successor_title"] is None else
            hashlib.sha256(envelope["successor_title"].encode("utf-8")).hexdigest(),
    })
    ledger = ProgressLedger(root)
    current = next((item for item in ledger.project_task_handoffs()["records"]
                    if item.get("handoff_type") == "CTRL_ROTATION"
                    and item["task_id"] == envelope["predecessor_id"]), None)
    handoff_key = json.dumps([claim["project_id"], envelope["predecessor_id"]], separators=(",", ":"))
    handoff_id = "ctrl-rotation-" + hashlib.sha256(handoff_key.encode("utf-8")).hexdigest()
    event = {
        "schema_version": 1, "record_type": "TASK_HANDOFF", "handoff_type": "CTRL_ROTATION",
        "handoff_id": handoff_id, "parent_event_id": None if current is None else current["event_id"],
        "event_kind": "CTRL_ROTATION_PREPARED" if current is None else "CTRL_ROTATION_OBSERVED",
        "goal_id": claim["goal_id"], "task_id": envelope["predecessor_id"],
        "old_owner": envelope["predecessor_id"], "new_owner": envelope["successor_id"],
        "checkpoint_digest": claim["handoff_digest"], "scope_version": 1, "lease_version": 1,
        "receipt_id": "rotation-unverified", "host_issued_at_ms": None,
        "observed_at_ms": claim["observed_at_ms"], "project_id": claim["project_id"], "root_digest": claim["root_digest"],
        "baseline_pinned": envelope["baseline_pinned"], "automation_id": claim["automation_id"],
        "collector_id": claim["collector_id"],
        "expected_title_digest": hashlib.sha256(envelope["expected_title"].encode("utf-8")).hexdigest(),
        "rotation_observation": observation,
    }
    if current is not None and all(current.get(key) == value for key, value in event.items()
                                   if key not in {"parent_event_id", "event_kind"}):
        retained = current
    else:
        identity = hashlib.sha256(json.dumps(event, ensure_ascii=True, sort_keys=True,
                                             separators=(",", ":")).encode("utf-8")).hexdigest()
        event.update(event_id="ctrl-rotation-" + identity, dedupe_key="ctrl-rotation-" + identity)
        ledger.append_task_handoff(event)
        retained = next(item for item in ledger.project_task_handoffs()["records"] if item["handoff_id"] == handoff_id)
    return {"state": "PENDING", "handoff_id": retained["handoff_id"], "event_id": retained["event_id"],
            "event_seq": retained["event_seq"], "successor_id": retained["new_owner"],
            "collector_id": retained["collector_id"], "claims_verified": False}


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


def rotation_bridge(envelope: dict, console_state: Path | None = None, rotation_ledger_root: Path | None = None) -> dict:
    """Classify caller observations and retained collection duties without host mutation.

    With ``console_state``, retained Auto leases or unread results owed by the
    predecessor block unpin/archive regardless of the caller's flag.
    """
    if not isinstance(envelope, dict) or set(envelope) - {"retirement"} != set(ROTATION_FIELDS):
        raise ValueError("rotation readback requires exactly: " + ", ".join(sorted(ROTATION_FIELDS)))
    for key, kind in ROTATION_FIELDS.items():
        if type(envelope[key]) not in (kind if isinstance(kind, tuple) else (kind,)):
            raise ValueError(f"rotation readback field has the wrong type: {key}")
    for key in ("baseline_pinned", "pinned", "capabilities"):
        if envelope[key] is not None and not all(isinstance(item, str) and item for item in envelope[key]):
            raise ValueError(f"rotation readback list must hold task IDs or capability names: {key}")
    journal = None if console_state is None else predecessor_obligations(console_state, envelope["predecessor_id"])
    in_flight = envelope["predecessor_in_flight"] or bool(journal and (journal["active_leases"] or journal["unread_results"]))
    read = RotationReadback(**{**{key: envelope[key] for key in ROTATION_FIELDS}, "baseline_pinned": tuple(envelope["baseline_pinned"]),
        "pinned": None if envelope["pinned"] is None else tuple(envelope["pinned"]),
        "capabilities": frozenset(envelope["capabilities"]), "predecessor_in_flight": in_flight})
    step = rotation_next_step(read)
    retirement = None
    if rotation_ledger_root is not None and "retirement" in envelope and envelope["authorized"]:
        if not envelope["predecessor_id"] or not envelope["successor_id"] or envelope["predecessor_id"] == envelope["successor_id"]:
            raise ValueError("rotation requires distinct predecessor and successor IDs")
        retirement = retain_rotation_claim(envelope, rotation_ledger_root)
    status, name, reason = step.status, step.step, step.reason
    if status not in {"BLOCKED", "PRESERVED"}:
        if journal is None:
            status, name, reason = "UNVERIFIED", "COLLECTION", "the existing execution journal is required to check leases and unread results"
        elif retirement is None:
            status, name, reason = "UNVERIFIED", "RETIREMENT", "a durable rotation claim in the existing progress ledger is required"
        else:
            claim = envelope["retirement"]
            if claim["ack_digest"] is not None and claim["ack_digest"] != claim["handoff_digest"]:
                status, name, reason = "BLOCKED", "ACK", "claimed successor acknowledgement does not match the retained handoff digest"
            elif claim["release_receipt_id"] is not None and claim["ack_digest"] is None:
                status, name, reason = "BLOCKED", "ACK", "release claim lacks the exact acknowledged handoff digest"
            elif claim["automation_target_id"] not in (None, envelope["successor_id"]):
                status, name, reason = "BLOCKED", "AUTOMATION", "automation target claim conflicts with the chosen successor"
            elif (claim["release_receipt_id"] is not None and claim["active_controller_ids"] is not None
                  and claim["active_controller_ids"] != [envelope["successor_id"]]):
                status, name, reason = "BLOCKED", "CONTROLLER", "controller readback claim does not identify exactly the chosen successor"
            else:
                status = "UNVERIFIED"
                reason = ("runtime has no injected verifier for host archive, sidebar, automation and collector wake; "
                          "retained observations are claims and retirement remains pending")
    return {"status": status, "step": name, "reason": reason,
            "reorder_to": list(step.reorder_to) if status == "NEXT" else [],
            "journal": journal, "retirement": retirement, "host_mutation_authorized_by_runtime": False}


def register(swarm:Swarm, stage_id:str, decision_event_receipt:str, *, accepted_at:int, due:RequestDue):
    """Named live bridge; serialized callers cannot mint authority."""
    if not isinstance(swarm,Swarm): raise ValueError("register requires the current live Swarm")
    return swarm.accept_request(Role.CTRL,stage_id,decision_event_receipt,accepted_at=accepted_at,due=due)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("forward-test", "request", "jev", "rotate"))
    parser.add_argument("--console-state", type=Path, help="rotate: read retained leases and unread results from this console journal")
    parser.add_argument("--rotation-ledger-root", type=Path, help="rotate: existing progress ledger root for pending retirement claims")
    args = parser.parse_args()
    if args.command == "jev":
        from swarm_jev import main as jev_main
        return jev_main([])
    if args.command == "forward-test":
        print(json.dumps(forward_cases(), sort_keys=True))
    if args.command in {"request", "rotate"}:
        try:
            envelope=json.load(sys.stdin)
            result=request_bridge(envelope) if args.command == "request" else rotation_bridge(envelope, args.console_state, args.rotation_ledger_root)
            print(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=True))
        except (ValueError, OSError, sqlite3.Error, json.JSONDecodeError) as error:
            print(json.dumps({"error":str(error)},sort_keys=True,separators=(",",":"))); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
