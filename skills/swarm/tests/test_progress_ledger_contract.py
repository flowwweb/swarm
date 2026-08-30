from __future__ import annotations

import json
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from skills.swarm.runtime.progress_events import (
    Ledger,
    PROGRESS_LEDGER_PATH,
    PROGRESS_PROJECTION_PATH,
    ROLE_ACCENTS,
    ProgressEventError,
    ProgressLifecycle,
    ProgressLedger,
    build_role_manifest,
    load_builtin_role_manifests,
    request_blocked_release_binding,
    role_material_event,
    task_handoff_host_binding,
    validate_progress_material_event,
    validate_role_manifest,
)
from skills.swarm.runtime.core import AcceptanceContract, ArtifactIdentity, ControlPathFailure, ControlPathFailureKind, ControlPathRecoveryAction, CustodyMutation, DelegationContract, HostCapacityEvidence, HostCustodyReceipt, HostTaskCapacity, InvariantError, OperationClass, ProofClass, ProfessionAssignment, RecoveryCause, Role, RoleFitDisposition, RoleGateDecision, RoutingEconomics, RoutingEvidenceBasis, RoutingScope, Swarm, Task, TaskStartReceipt, Worker, WorkerState, WorkKind, WorkRoutingFacts, WorkSize, _HOST_AUTHORITY_GENERATOR, _HOST_AUTHORITY_PRIME, _custody_message, role_gate, route_execution


class ProgressLedgerContractTests(unittest.TestCase):
    HOST_PRIVATE_KEY = 0x5A17

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = self.host_ledger(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def role_manifests() -> tuple[dict, ...]:
        repository = Path(__file__).resolve().parents[3]
        return load_builtin_role_manifests(
            repository / "skills" / "swarm" / "roles",
            repository / "console" / "static" / "swarm-offline-disconnected.png",
        )

    @staticmethod
    def role_draft(role: dict, **changes: object) -> dict:
        draft = {key: role[key] for key in (
            "name", "purpose", "owns", "instructions", "boundaries",
            "default_skills", "specializations", "avatar_asset_digest", "accent",
        )}
        draft.update(changes)
        return draft

    @classmethod
    def host_ledger(cls, root: Path | str) -> ProgressLedger:
        return ProgressLedger(root, host_custody_public_key=pow(_HOST_AUTHORITY_GENERATOR, cls.HOST_PRIVATE_KEY, _HOST_AUTHORITY_PRIME))

    @classmethod
    def sign_host_receipt(cls, receipt: HostCustodyReceipt, *, private_key: int | None = None) -> HostCustodyReceipt:
        secret = cls.HOST_PRIVATE_KEY if private_key is None else private_key
        message = _custody_message(receipt)
        nonce = int.from_bytes(hashlib.sha256(secret.to_bytes(32, "big") + message).digest(), "big") % (_HOST_AUTHORITY_PRIME - 2) + 1
        commitment = pow(_HOST_AUTHORITY_GENERATOR, nonce, _HOST_AUTHORITY_PRIME)
        width = (_HOST_AUTHORITY_PRIME.bit_length() + 7) // 8
        challenge = int.from_bytes(hashlib.sha256(commitment.to_bytes(width, "big") + message).digest(), "big")
        response = (nonce + secret * challenge) % (_HOST_AUTHORITY_PRIME - 1)
        object.__setattr__(receipt, "_signature", f"{commitment:x}:{response:x}")
        return receipt

    @classmethod
    def host_receipt(cls, swarm: Swarm, receipt_id: str, target_id: str, binding: str, issued_at_ms: int) -> HostCustodyReceipt:
        receipt = HostCustodyReceipt(receipt_id, CustodyMutation.STATE, target_id, binding, issued_at_ms)
        cls.sign_host_receipt(receipt)
        return swarm.record_host_custody_receipt(Role.CTRL, receipt)

    def test_control_path_terminal_blocked_requires_retained_host_release_receipt(self) -> None:
        artifact = ArtifactIdentity("candidate", "revision", "source")
        contract = DelegationContract("task-recovery", "Return the bounded receipt.", "owner-old", ("skills/swarm/runtime",), artifact, ("skills/swarm/runtime/core.py",), (ProofClass.SOURCE,), 100)
        task = Task("task-recovery", "owner-old", "creator", 1, {}, reviewer="owner-new", delegation_contract=contract, subagent_receipt="dispatch-receipt")
        swarm = Swarm(tasks={task.id: task}, request_lifecycle_ledger=self.ledger)

        def failure(turn: int, route: str) -> ControlPathFailure:
            return ControlPathFailure(task.id, task.owner, task.subagent_receipt, f"completion-{turn}", ControlPathFailureKind.EMPTY_COMPLETION, "work/swarm-source", artifact, contract.artifact_paths, route, turn * 10, cause=RecoveryCause.CONTROL_TRANSPORT)

        swarm.resolve_control_path_failure(Role.CTRL, failure(1, "route-failed"), same_owner_route="route-a", safely_resumable=True)
        swarm.resolve_control_path_failure(Role.CTRL, failure(2, "route-a"), same_owner_route="route-b", safely_resumable=True)
        swarm.resolve_control_path_failure(Role.CTRL, failure(3, "route-b"), authorized_handoff_owner="owner-new")
        terminal_failure = failure(4, "handoff-owner-new")
        before = swarm.retry_topology_ledger.control_path_snapshot()
        with self.assertRaisesRegex(InvariantError, "caller-authored release receipt strings"):
            swarm.resolve_control_path_failure(Role.CTRL, terminal_failure, release_condition="user supplies provider authority", responsible_authority="host-user", release_receipt_id="caller-release")
        self.assertEqual(swarm.retry_topology_ledger.control_path_snapshot(), before)
        binding = swarm.retry_topology_ledger.control_path_release_binding(terminal_failure, release_condition="user supplies provider authority", responsible_authority="host-user")
        forged = self.sign_host_receipt(HostCustodyReceipt("e" * 64, CustodyMutation.STATE, task.id, binding, terminal_failure.observed_at_ms), private_key=self.HOST_PRIVATE_KEY + 1)
        object.__setattr__(forged, "_authority", swarm._custody_capability)
        swarm.host_custody_receipts[forged.receipt] = forged
        object.__setattr__(self.ledger, "_ProgressLedger__host_custody_public_key", pow(_HOST_AUTHORITY_GENERATOR, self.HOST_PRIVATE_KEY + 1, _HOST_AUTHORITY_PRIME))
        attacker_ledger = ProgressLedger(self.root / "attacker", host_custody_public_key=pow(_HOST_AUTHORITY_GENERATOR, self.HOST_PRIVATE_KEY + 1, _HOST_AUTHORITY_PRIME))
        with self.assertRaisesRegex(InvariantError, "fixed by the authoritative runtime"):
            swarm.request_lifecycle_ledger = attacker_ledger
        before = (swarm.retry_topology_ledger.control_path_snapshot(), tuple(swarm.events))
        with self.assertRaisesRegex(ProgressEventError, "host-verified"):
            swarm.resolve_control_path_failure(Role.CTRL, terminal_failure, release_condition="user supplies provider authority", responsible_authority="host-user", release_receipt=forged)
        self.assertEqual((swarm.retry_topology_ledger.control_path_snapshot(), tuple(swarm.events)), before)
        release = self.host_receipt(swarm, "d" * 64, task.id, binding, terminal_failure.observed_at_ms)
        blocked = swarm.resolve_control_path_failure(Role.CTRL, terminal_failure, release_condition="user supplies provider authority", responsible_authority="host-user", release_receipt=release)
        self.assertEqual(blocked.action, ControlPathRecoveryAction.TERMINAL_BLOCKED)
        self.assertEqual(blocked.release_receipt_id, release.receipt)

    def test_connector_receipt_is_non_material_idempotent_and_restart_safe(self) -> None:
        base = {
            "schema_version": 1, "record_type": "CONNECTOR", "command_id": "connector-command-1",
            "idempotency_key": "command-1", "command_digest": "1" * 64,
            "project_id": "project-alpha", "root_digest": "2" * 64,
            "action": "TASK", "observed_root_digest": "2" * 64,
        }
        before = self.ledger.project("project-alpha")
        command = {**base, "receipt_id": "connector-1", "receipt_index": 0, "status": "COMMAND", "thread_id": None, "turn_id": None, "observed_at_ms": 10}
        first = self.ledger.append_connector_receipt(command)
        replay = self.ledger.append_connector_receipt(command)
        self.assertEqual((first["status"], replay["status"]), ("appended", "unchanged"))
        for index, status in enumerate(("ACKNOWLEDGED", "PROGRESS", "PROGRESS", "RESULT"), 1):
            self.ledger.append_connector_receipt({**base, "receipt_id": f"connector-{index + 1}", "receipt_index": index, "status": status, "thread_id": "thread-1", "turn_id": "turn-1", "observed_at_ms": 10 + index})
        after = self.ledger.project("project-alpha")
        self.assertEqual(
            {key: value for key, value in after.items() if key != "cursor"},
            {key: value for key, value in before.items() if key != "cursor"},
        )
        restarted = self.host_ledger(self.root)
        command_projection = restarted.replay()["connector_receipts"]["command-1"]
        self.assertEqual([item["status"] for item in command_projection["receipts"]], ["COMMAND", "ACKNOWLEDGED", "PROGRESS", "PROGRESS", "RESULT"])
        self.assertTrue(command_projection["terminal"])
        with self.assertRaisesRegex(ProgressEventError, "terminal"):
            restarted.append_connector_receipt({**base, "receipt_id": "connector-late", "receipt_index": 5, "status": "PROGRESS", "thread_id": "thread-1", "turn_id": "turn-1", "observed_at_ms": 20})

    def test_non_material_decoder_preserves_bytes_and_fails_closed(self) -> None:
        receipt = {
            "schema_version": 1, "record_type": "CONNECTOR", "receipt_id": "connector-corrupt", "command_id": "connector-command-corrupt", "receipt_index": 0,
            "idempotency_key": "command-corrupt", "command_digest": "3" * 64,
            "project_id": "project-alpha", "root_digest": "4" * 64,
            "action": "TASK", "status": "COMMAND", "thread_id": None,
            "turn_id": None, "observed_root_digest": "4" * 64, "observed_at_ms": 1,
        }
        self.ledger.append_connector_receipt(receipt)
        path = self.root / PROGRESS_LEDGER_PATH
        original = path.read_bytes()
        self.host_ledger(self.root).replay()
        self.assertEqual(path.read_bytes(), original)
        record = json.loads(original)
        record["event"]["unknown"] = True
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaises(ProgressEventError):
            self.host_ledger(self.root).replay()

    def test_connector_receipt_rejects_unknown_action_and_status(self) -> None:
        base = {
            "schema_version": 1, "record_type": "CONNECTOR", "receipt_id": "connector-invalid", "command_id": "connector-command-invalid", "receipt_index": 0,
            "idempotency_key": "command-invalid", "command_digest": "5" * 64,
            "project_id": "project-alpha", "root_digest": "6" * 64,
            "action": "TASK", "status": "COMMAND", "thread_id": None, "turn_id": None,
            "observed_root_digest": "6" * 64, "observed_at_ms": 1,
        }
        for change in ({"action": "DELETE_EVERYTHING"}, {"status": "SUCCESSISH"}):
            with self.subTest(change=change), self.assertRaisesRegex(ProgressEventError, "unsupported"):
                self.ledger.append_connector_receipt({**base, **change})
        self.assertFalse((self.root / PROGRESS_LEDGER_PATH).exists())

    def test_connector_receipt_rejects_binding_and_identity_conflicts(self) -> None:
        base = {
            "schema_version": 1, "record_type": "CONNECTOR", "receipt_id": "command-receipt", "command_id": "command-id", "receipt_index": 0,
            "idempotency_key": "command-key", "command_digest": "7" * 64, "project_id": "project-alpha", "root_digest": "8" * 64,
            "action": "TASK", "status": "COMMAND", "thread_id": None, "turn_id": None, "observed_root_digest": "8" * 64, "observed_at_ms": 1,
        }
        self.ledger.append_connector_receipt(base)
        for change in (
            {"receipt_id": "ack-no-host", "receipt_index": 1, "status": "ACKNOWLEDGED"},
            {"receipt_id": "command-host", "thread_id": "forged"},
            {"receipt_id": "ack-root", "receipt_index": 1, "status": "ACKNOWLEDGED", "thread_id": "thread", "observed_root_digest": "9" * 64},
            {"receipt_id": "command-conflict", "command_digest": "a" * 64},
            {"receipt_id": "command-receipt", "observed_at_ms": 2},
        ):
            with self.subTest(change=change), self.assertRaises(ProgressEventError):
                self.ledger.append_connector_receipt({**base, **change})
        local = {**base, "receipt_id": "local-command", "command_id": "local-id", "idempotency_key": "local-key", "command_digest": "b" * 64, "action": "LOCAL_HQ"}
        self.ledger.append_connector_receipt(local)
        with self.assertRaisesRegex(ProgressEventError, "LOCAL_HQ"):
            self.ledger.append_connector_receipt({**local, "receipt_id": "local-result", "receipt_index": 1, "status": "RESULT", "thread_id": "thread"})
        unsupported = {**base, "receipt_id": "unsupported-command", "command_id": "unsupported-id", "idempotency_key": "unsupported-key", "command_digest": "c" * 64}
        self.ledger.append_connector_receipt(unsupported)
        self.ledger.append_connector_receipt({**unsupported, "receipt_id": "unsupported-result", "receipt_index": 1, "status": "UNSUPPORTED", "observed_at_ms": 2})

    @staticmethod
    def event(
        event_id: str,
        block_id: str,
        *,
        task_id: str | None = None,
        kind: str = "BLOCK_CREATED",
        lifecycle: str = "PLANNED",
        scope_version: int = 1,
        sentence: str | None = None,
        committed: int | None = None,
        admitted: int = 0,
        observed_at_ms: int = 1,
        dependencies: list[str] | None = None,
        split_from: str | None = None,
        merged_from: list[str] | None = None,
        proof_receipts: list[str] | None = None,
        flags: list[str] | None = None,
    ) -> dict:
        measured = committed is not None
        return {
            "schema_version": 1,
            "event_id": event_id,
            "dedupe_key": f"dedupe-{event_id}",
            "portfolio_id": "portfolio-main",
            "project_id": "project-alpha",
            "ctrl_id": "ctrl-alpha",
            "milestone_id": "milestone-one",
            "block_id": block_id,
            "task_id": task_id or f"task-{block_id}",
            "owner_id": f"owner-{task_id or block_id}",
            "scope_version": scope_version,
            "parent_block_id": None,
            "dependency_ids": dependencies or [],
            "lineage": {
                "predecessor_block_ids": [],
                "split_from": split_from,
                "merged_from": merged_from or [],
            },
            "event_kind": kind,
            "lifecycle_state": lifecycle,
            "measurement": {
                "state": "MEASURED" if measured else "UNMEASURED",
                "committed_weight": committed,
                "admitted_proof_weight": admitted,
                "basis_receipt_ids": [f"weight-{block_id}"] if measured else [],
            },
            "proof": {
                "required_classes": ["SOURCE"],
                "receipt_ids": proof_receipts or ([f"proof-{event_id}"] if admitted else []),
                "claim_limit": "Source-only progress evidence.",
            },
            "eta": {"start_ms": None, "end_ms": None, "confidence": None, "basis_receipt_ids": []},
            "rework": {"attempt": 1, "count": 0, "invalidated_receipt_ids": []},
            "custody": {"surface": f"surface:{block_id}", "receipt_id": f"custody-{block_id}"},
            "steering_receipt_ids": [],
            "material_update_sentence": sentence,
            "flags": flags or [],
            "provenance": "typed owner material boundary",
            "source": "swarm_runtime",
            "observed_at_ms": observed_at_ms,
            "causation_id": None,
            "parent_event_id": None,
        }

    @staticmethod
    def topology_event(
        event_id: str,
        block_id: str,
        *,
        node_kind: str = "BLOCK",
        parent_block_id: str | None = None,
        parent_event_id: str | None = None,
        owner_id: str | None = None,
        input_receipts: list[str] | None = None,
        dispatch_receipt: str | None = None,
        completion_receipt: str | None = None,
        cost_receipts: list[str] | None = None,
        release_receipts: list[str] | None = None,
        **kwargs: object,
    ) -> dict:
        payload = ProgressLedgerContractTests.event(event_id, block_id, **kwargs)
        payload["schema_version"] = 2
        payload["parent_block_id"] = parent_block_id
        payload["parent_event_id"] = parent_event_id
        if owner_id is not None:
            payload["owner_id"] = owner_id
        payload["topology"] = {
            "node_kind": node_kind,
            "input_receipt_ids": input_receipts or [],
            "dispatch_receipt_id": dispatch_receipt,
            "completion_receipt_id": completion_receipt,
            "cost_receipt_ids": cost_receipts or [],
            "release_receipt_ids": release_receipts or [],
        }
        return payload

    @staticmethod
    def expected_receipt(receipt_id: str, **changes: object) -> dict:
        target = str(changes.pop("target_id", "artifact-alpha"))
        return {
            "schema_version": 1, "record_type": "EXPECTED_RECEIPT", "receipt_id": receipt_id,
            "goal_id": "goal-alpha", "task_id": "task-block-a", "owner_id": "owner-block-a",
            "lease_version": 1, "target_id": target,
            "artifact_digest": hashlib.sha256(target.encode()).hexdigest(),
            "expected_event_kind": "PROOF_ADMITTED", "due_event": "MATERIAL_EVENT",
            "due_generation": 1, "source_cursor": 10,
            "attempted_route_digests": [hashlib.sha256(b"route-initial").hexdigest()],
            "observed_at_ms": 1, **changes,
        }

    @staticmethod
    def observation(receipt: dict, *, route: str = "route-next", source_cursor: int = 11, outcome: str = "MATERIAL", evidence: list[str] | None = None, **changes: object) -> dict:
        payload = {
            "expected_receipt_id": receipt["receipt_id"], "goal_id": receipt["goal_id"],
            "owner_id": receipt["owner_id"], "lease_version": receipt["lease_version"],
            "target_id": receipt["target_id"], "artifact_digest": receipt["artifact_digest"], "source_cursor": source_cursor,
            "route_digest": hashlib.sha256(route.encode()).hexdigest(),
            "outcome": outcome, "evidence_receipt_ids": ["outcome-proof"] if evidence is None else evidence,
        }
        payload.update(changes)
        return payload

    def test_append_replay_idempotency_conflict_and_crash_recovery(self) -> None:
        first = self.event("event-a", "block-a", sentence="The ledger contract is now frozen.")
        appended = self.ledger.append(first)
        self.assertEqual(appended["status"], "appended")
        self.assertEqual(self.ledger.append(first)["status"], "unchanged")
        conflicting = {**first, "material_update_sentence": "Different content."}
        with self.assertRaisesRegex(ProgressEventError, "identity conflicts"):
            self.ledger.append(conflicting)

        second = self.event("event-b", "block-b", sentence="Replay is the next gate.", observed_at_ms=2)
        with mock.patch.object(self.ledger, "_write_projection_unlocked", side_effect=OSError("crash after append")):
            with self.assertRaisesRegex(OSError, "crash after append"):
                self.ledger.append(second)
        projection = ProgressLedger(self.root).replay()
        self.assertEqual(projection["cursor"]["event_seq"], 2)
        self.assertEqual(len(projection["events"]), 2)

    def test_expected_receipt_matches_once_and_restart_replays_exactly(self) -> None:
        self.assertIs(Ledger, ProgressLedger)
        self.ledger.append(self.event("base", "block-a", committed=1))
        expected = self.expected_receipt("expected-alpha")
        first = self.ledger.append_expected_receipt(expected)
        self.assertEqual((first["status"], self.ledger.append_expected_receipt(expected)["status"]), ("appended", "unchanged"))
        conflicting = {**expected, "artifact_digest": hashlib.sha256(b"other").hexdigest()}
        with self.assertRaisesRegex(ProgressEventError, "identity conflicts"):
            self.ledger.append_expected_receipt(conflicting)
        observed = self.event("proof", "block-a", kind="PROOF_ADMITTED", committed=1, admitted=1, proof_receipts=["proof-exact"], observed_at_ms=2)
        observed["expected_observation"] = self.observation(expected)
        result = self.ledger.append(observed)
        self.assertEqual(result["expected_check"]["status"], "MATCHED")
        self.assertTrue(result["expected_check"]["progress_advanced"])
        self.assertEqual(self.ledger.project("project-alpha")["admitted_proof_weight"], 1)
        item = Ledger(self.root).replay()["expected_receipts"]["expected-alpha"]
        self.assertEqual((item["result"]["status"], item["receipt"]), ("MATCHED", expected))
        self.assertEqual(Ledger(self.root).append(observed)["status"], "unchanged")

    def test_expected_mismatch_classes_are_attention_and_never_advance_progress(self) -> None:
        cases = {
            "empty": ({"outcome": "EMPTY"}, {}),
            "timeout": ({"outcome": "TIMEOUT"}, {}),
            "http": ({"outcome": "HTTP_400"}, {}),
            "missing-thread": ({"outcome": "MISSING_THREAD"}, {}),
            "replay": ({"outcome": "REPLAY"}, {}),
            "wrong-target": ({"target_id": "other-target"}, {}),
            "wrong-artifact": ({"artifact_digest": hashlib.sha256(b"other").hexdigest()}, {}),
            "wrong-owner": ({"owner_id": "other-owner"}, {}),
            "wrong-lease": ({"lease_version": 2}, {}),
            "wrong-task": ({}, {"task_id": "other-task"}),
            "wrong-outer-owner": ({}, {"owner_id": "other-owner"}),
            "stale": ({"source_cursor": 10}, {}),
            "wrong-event": ({}, {"kind": "STATE_CHANGED"}),
            "missing-evidence": ({"evidence_receipt_ids": []}, {"admitted": 0, "proof_receipts": []}),
        }
        for index, (label, (observation_changes, event_changes)) in enumerate(cases.items(), 1):
            with self.subTest(label=label):
                root = self.root / label
                ledger = Ledger(root)
                ledger.append(self.event("base", "block-a", committed=1))
                expected = self.expected_receipt(f"expected-{label}")
                ledger.append_expected_receipt(expected)
                event = self.event(
                    f"observed-{index}", "block-a", kind=event_changes.get("kind", "PROOF_ADMITTED"),
                    task_id=event_changes.get("task_id"),
                    committed=1, admitted=event_changes.get("admitted", 1),
                    proof_receipts=event_changes.get("proof_receipts", [f"proof-{index}"]), observed_at_ms=2,
                )
                if "owner_id" in event_changes:
                    event["owner_id"] = event_changes["owner_id"]
                observation = self.observation(expected)
                observation.update(observation_changes)
                event["expected_observation"] = observation
                result = ledger.append(event)
                self.assertEqual(result["expected_check"]["status"], "ATTENTION")
                self.assertFalse(result["expected_check"]["progress_advanced"])
                project = ledger.project("project-alpha")
                self.assertEqual((project["admitted_proof_weight"], project["blocks"][0]["latest_event_id"]), (0, "base"))
                if label.startswith("wrong-"):
                    retained = ledger.replay()["expected_receipts"][expected["receipt_id"]]
                    self.assertEqual(retained["last_source_cursor"], expected["source_cursor"])
                    self.assertEqual(ledger._retry_topology._attempts, {})

    def test_wrong_inner_goal_is_attention_without_progress_or_recovery(self) -> None:
        self.ledger.append(self.event("base", "block-a", committed=1))
        expected = self.expected_receipt("expected-goal")
        self.ledger.append_expected_receipt(expected)
        event = self.event(
            "wrong-goal", "block-a", kind="PROOF_ADMITTED", committed=1,
            admitted=1, proof_receipts=["proof-wrong-goal"], observed_at_ms=2,
        )
        event["expected_observation"] = self.observation(
            expected, source_cursor=999, outcome="TIMEOUT", goal_id="other-goal",
        )
        check = self.ledger.append(event)["expected_check"]
        self.assertEqual((check["status"], check["reason"], check["progress_advanced"]), ("ATTENTION", "WRONG_GOAL", False))
        self.assertNotIn("retry_action", check)
        self.assertEqual(self.ledger._retry_topology._attempts, {})
        retained = self.ledger.replay()["expected_receipts"][expected["receipt_id"]]
        self.assertEqual((retained["last_source_cursor"], retained["result"]["reason"]), (10, "WRONG_GOAL"))
        valid = self.event(
            "valid-goal", "block-a", kind="PROOF_ADMITTED", committed=1,
            admitted=1, proof_receipts=["proof-valid-goal"], observed_at_ms=3,
        )
        valid["expected_observation"] = self.observation(expected, source_cursor=11)
        self.assertEqual(self.ledger.append(valid)["expected_check"]["status"], "MATCHED")
        restarted = Ledger(self.root)
        replayed = restarted.replay()["expected_receipts"][expected["receipt_id"]]
        self.assertEqual((replayed["last_source_cursor"], replayed["result"]["status"]), (11, "MATCHED"))
        self.assertEqual(restarted._retry_topology._attempts, {})

    def test_outer_handoff_bindings_fail_before_expected_cursor_or_retry_mutation(self) -> None:
        cases = {
            "goal": ({"goal_id": "other-goal"}, "WRONG_GOAL"),
            "task": ({"task_id": "other-task"}, "WRONG_TASK"),
            "owner": ({"old_owner": "other-owner"}, "WRONG_OWNER"),
            "lease": ({"lease_version": 2}, "WRONG_LEASE"),
        }
        for index, (label, (changes, expected_reason)) in enumerate(cases.items(), 1):
            with self.subTest(binding=label):
                root = self.root / f"outer-{label}"
                ledger = self.host_ledger(root)
                expected = self.expected_receipt(
                    f"expected-outer-{label}", goal_id="goal-outer", task_id="task-outer",
                    owner_id="owner-outer", expected_event_kind="HANDOFF_DUE",
                    due_event="LEASE_EXPIRY", due_generation=changes.get("lease_version", 1),
                )
                ledger.append_expected_receipt(expected)
                handoff = {
                    "schema_version": 1, "record_type": "TASK_HANDOFF",
                    "event_id": f"handoff-outer-{label}", "dedupe_key": f"handoff-outer-{label}-dedupe",
                    "handoff_id": f"handoff-outer-{label}", "parent_event_id": None,
                    "event_kind": "HANDOFF_DUE", "goal_id": "goal-outer", "task_id": "task-outer",
                    "old_owner": "owner-outer", "new_owner": None, "checkpoint_digest": None,
                    "scope_version": 1, "lease_version": 1, "receipt_id": str(index) * 64,
                    "host_issued_at_ms": 1, "observed_at_ms": 2,
                    "expected_observation": self.observation(expected, source_cursor=999),
                    **changes,
                }
                custody = Swarm(request_lifecycle_ledger=ledger)
                receipt = self.host_receipt(
                    custody, handoff["receipt_id"], handoff["task_id"],
                    task_handoff_host_binding(handoff), handoff["host_issued_at_ms"],
                )
                check = ledger.append_task_handoff(handoff, custody_receipt=receipt)["expected_check"]
                self.assertEqual((check["status"], check["reason"]), ("ATTENTION", expected_reason))
                retained = ledger.replay()["expected_receipts"][expected["receipt_id"]]
                self.assertEqual(retained["last_source_cursor"], expected["source_cursor"])
                self.assertEqual(ledger._retry_topology._attempts, {})

    def test_explicit_none_expected_observation_matches_omission_after_restart(self) -> None:
        omitted = self.event("no-observation", "block-a", committed=1)
        explicit = {**omitted, "expected_observation": None}
        omitted_event = validate_progress_material_event(omitted)
        explicit_event = validate_progress_material_event(explicit)
        self.assertEqual((explicit_event.digest, explicit_event.semantic_digest), (omitted_event.digest, omitted_event.semantic_digest))
        self.assertNotIn("expected_observation", explicit_event.canonical_payload())
        appended = self.ledger.append(explicit)
        self.assertEqual(Ledger(self.root).replay()["cursor"], appended["cursor"])
        self.assertEqual(Ledger(self.root).append(omitted)["status"], "unchanged")

        request_root = self.root / "request"
        request = {
            "schema_version": 1, "record_type": "REQUEST_LIFECYCLE",
            "event_id": "request-offer", "dedupe_key": "request-offer-dedupe",
            "request_id": "request-none", "stage_id": "stage-none", "parent_event_id": None,
            "envelope_digest": "1" * 64, "lifecycle_state": "OFFERED", "record": None,
            "route_receipt_ids": [], "permitted_route_ids": [], "failed_goal_turn_receipt_ids": [],
            "release_authority": None, "release_receipt_id": None, "release_issued_at_ms": None,
        }
        request_ledger = self.host_ledger(request_root)
        request_first = request_ledger.append_request_lifecycle({**request, "expected_observation": None})
        request_record = json.loads((request_root / PROGRESS_LEDGER_PATH).read_text(encoding="utf-8"))
        self.assertNotIn("expected_observation", request_record["event"])
        request_restart = self.host_ledger(request_root)
        self.assertEqual(
            request_restart.project_request_lifecycles()["records"][0]["event_id"],
            request_first["cursor"]["event_id"],
        )
        self.assertEqual(request_restart.append_request_lifecycle(request)["status"], "unchanged")

        handoff_root = self.root / "handoff"
        handoff_ledger = self.host_ledger(handoff_root)
        handoff = {
            "schema_version": 1, "record_type": "TASK_HANDOFF",
            "event_id": "handoff-due", "dedupe_key": "handoff-due-dedupe",
            "handoff_id": "handoff-none", "parent_event_id": None, "event_kind": "HANDOFF_DUE",
            "goal_id": "goal-none", "task_id": "task-none", "old_owner": "owner-none",
            "new_owner": None, "checkpoint_digest": None, "scope_version": 1, "lease_version": 1,
            "receipt_id": "a" * 64, "host_issued_at_ms": 1, "observed_at_ms": 2,
        }
        custody = Swarm(request_lifecycle_ledger=handoff_ledger)
        receipt = self.host_receipt(custody, "a" * 64, "task-none", task_handoff_host_binding(handoff), 1)
        handoff_first = handoff_ledger.append_task_handoff({**handoff, "expected_observation": None}, custody_receipt=receipt)
        handoff_record = json.loads((handoff_root / PROGRESS_LEDGER_PATH).read_text(encoding="utf-8"))
        self.assertNotIn("expected_observation", handoff_record["event"])
        handoff_restart = self.host_ledger(handoff_root)
        handoff_restart.retain_host_custody_receipt(receipt)
        self.assertEqual(handoff_restart.replay()["cursor"], handoff_first["cursor"])
        self.assertEqual(handoff_restart.append_task_handoff(handoff, custody_receipt=receipt)["status"], "unchanged")

    def test_repeated_expected_route_reuses_retry_topology_and_requires_a_different_route(self) -> None:
        self.ledger.append(self.event("base", "block-a", committed=1))
        route = hashlib.sha256(b"route-initial").hexdigest()
        expected = self.expected_receipt(
            "expected-retry", attempted_route_digests=[route], expected_event_kind="STATE_CHANGED",
        )
        self.ledger.append_expected_receipt(expected)
        actions = []
        for index in (1, 2):
            event = self.event(f"timeout-{index}", "block-a", kind="STATE_CHANGED", committed=1, observed_at_ms=index + 1)
            event["expected_observation"] = self.observation(expected, route="route-initial", source_cursor=10 + index, outcome="TIMEOUT", evidence=[])
            check = self.ledger.append(event)["expected_check"]
            actions.append(check["retry_action"])
        self.assertEqual(actions, ["CONTINUE", "REASSESS_ROOT_CAUSE"])
        self.assertEqual(check["equivalent_attempts"], 2)
        self.assertTrue(check["different_route_required"])
        projected = self.ledger.replay()["expected_receipts"]["expected-retry"]
        self.assertEqual(projected["receipt"]["attempted_route_digests"], [route])
        self.assertNotIn("attempted_route_digests", projected)

    def test_matched_expected_result_is_monotonic_across_later_events_and_restart(self) -> None:
        self.ledger.append(self.event("base", "block-a", committed=1))
        expected = self.expected_receipt("expected-terminal")
        self.ledger.append_expected_receipt(expected)
        matched = self.event("matched", "block-a", kind="PROOF_ADMITTED", committed=1, admitted=1, proof_receipts=["proof-exact"], observed_at_ms=2)
        matched["expected_observation"] = self.observation(expected)
        self.assertEqual(self.ledger.append(matched)["expected_check"]["status"], "MATCHED")
        later = self.event("later", "block-a", kind="STATE_CHANGED", committed=1, observed_at_ms=3)
        later["expected_observation"] = self.observation(expected, route="route-later", source_cursor=12, outcome="TIMEOUT", evidence=[])
        check = self.ledger.append(later)["expected_check"]
        self.assertEqual((check["status"], check["progress_advanced"]), ("MATCHED", False))
        self.assertNotIn("retry_action", check)
        self.ledger.append(self.event("base-b", "block-b", committed=1, observed_at_ms=4))
        followup = self.expected_receipt(
            "expected-followup", goal_id="goal-beta", task_id="task-block-b",
            owner_id="owner-block-b", source_cursor=20, expected_event_kind="STATE_CHANGED",
        )
        self.ledger.append_expected_receipt(followup)
        failed = self.event("failed-b", "block-b", kind="STATE_CHANGED", committed=1, observed_at_ms=5)
        failed["expected_observation"] = self.observation(
            followup, route="route-later", source_cursor=21, outcome="TIMEOUT", evidence=[],
        )
        self.assertEqual(self.ledger.append(failed)["expected_check"]["retry_action"], "CONTINUE")
        retained = Ledger(self.root).replay()["expected_receipts"][expected["receipt_id"]]["result"]
        self.assertEqual((retained["status"], retained["event_id"]), ("MATCHED", "matched"))

    def test_expected_receipt_is_explicitly_non_material_in_feed_and_projections(self) -> None:
        expected = self.expected_receipt("expected-projection")
        self.ledger.append_expected_receipt(expected)
        feed = Ledger(self.root).feed_snapshot("project-alpha")
        self.assertEqual((feed["cursor"]["event_seq"], feed["cursor"]["event_id"], feed["items"]), (1, "expected-projection", []))
        self.assertEqual(Ledger(self.root).project_topology("project-alpha", "ctrl-alpha")["source_event_ids"], [])
        measured = Ledger(self.root).project_verified_yield("project-alpha", [], observed_after_ms=0, observed_before_ms=1)
        self.assertEqual((measured["tasks"], measured["conflict_count"]), ([], 0))

    def test_expected_checks_run_only_on_admitted_turn_lease_and_user_steer_events(self) -> None:
        request_root = self.root / "turn"
        request_ledger = Ledger(request_root)
        turn_expected = self.expected_receipt(
            "expected-turn", task_id="request-task", owner_id="request-owner", goal_id="request-goal",
            target_id="request-artifact", expected_event_kind="RESULT_PENDING",
            due_event="TURN_COMPLETION", due_generation=2,
        )
        request_ledger.append_expected_receipt(turn_expected)
        offer = {
            "schema_version": 1, "record_type": "REQUEST_LIFECYCLE", "event_id": "turn-offer",
            "dedupe_key": "turn-offer-dedupe", "request_id": "request-turn", "stage_id": "stage-turn",
            "parent_event_id": None, "envelope_digest": "1" * 64, "lifecycle_state": "OFFERED",
            "record": None, "route_receipt_ids": [], "permitted_route_ids": [],
            "failed_goal_turn_receipt_ids": [], "release_authority": None,
            "release_receipt_id": None, "release_issued_at_ms": None,
        }
        request_ledger.append_request_lifecycle(offer)
        cursor = {"event_receipt": "turn-event-1", "message_id": "turn-message-1", "surface_receipt": "turn-surface-1", "feed_sequence": 1}
        record = {
            "id": "request-turn", "goal_id": "request-goal", "task_id": "request-task",
            "accepted_owner": "request-owner", "outcome_kind": "ARTIFACT",
            "outcome_digest": turn_expected["artifact_digest"], "accepting_route": ["request-owner", "CTRL"],
            "accepted_at": 1, "next_due_event": "turn-due", "next_due_at": 2,
            "evidence_receipts": ["turn-proof"],
            "transitions": [{"state": "OPEN", "kind": "dispatch", "cursor": cursor}], "successor_id": "",
        }
        acknowledged = {**offer, "event_id": "turn-ack", "dedupe_key": "turn-ack-dedupe", "parent_event_id": "turn-offer", "lifecycle_state": "ACKNOWLEDGED", "record": record}
        request_ledger.append_request_lifecycle(acknowledged)
        admitted = {**acknowledged, "event_id": "turn-admitted", "dedupe_key": "turn-admitted-dedupe", "parent_event_id": "turn-ack", "lifecycle_state": "ADMITTED"}
        request_ledger.append_request_lifecycle(admitted)
        turn_record = {**record, "transitions": [*record["transitions"], {"state": "OPEN", "kind": "result", "cursor": {**cursor, "event_receipt": "turn-event-2", "message_id": "turn-message-2", "surface_receipt": "turn-surface-2", "feed_sequence": 2}}]}
        completed = {**admitted, "event_id": "turn-complete", "dedupe_key": "turn-complete-dedupe", "parent_event_id": "turn-admitted", "lifecycle_state": "RESULT_PENDING", "record": turn_record, "expected_observation": self.observation(turn_expected)}
        self.assertEqual(request_ledger.append_request_lifecycle(completed)["expected_check"]["status"], "MATCHED")

        lease_root = self.root / "lease"
        lease_ledger = self.host_ledger(lease_root)
        lease_expected = self.expected_receipt(
            "expected-lease", task_id="lease-task", owner_id="lease-owner", goal_id="lease-goal",
            target_id="lease-target", lease_version=3, expected_event_kind="HANDOFF_DUE", due_event="LEASE_EXPIRY", due_generation=3,
        )
        lease_ledger.append_expected_receipt(lease_expected)
        handoff = {
            "schema_version": 1, "record_type": "TASK_HANDOFF", "event_id": "lease-due",
            "dedupe_key": "lease-due-dedupe", "handoff_id": "lease-handoff", "parent_event_id": None,
            "event_kind": "HANDOFF_DUE", "goal_id": "lease-goal", "task_id": "lease-task",
            "old_owner": "lease-owner", "new_owner": None, "checkpoint_digest": None,
            "scope_version": 1, "lease_version": 3, "receipt_id": "a" * 64,
            "host_issued_at_ms": 5, "observed_at_ms": 6,
            "expected_observation": self.observation(lease_expected, source_cursor=11),
        }
        binding = task_handoff_host_binding(handoff)
        custody = self.sign_host_receipt(HostCustodyReceipt("a" * 64, CustodyMutation.STATE, "lease-task", binding, 5))
        lease_ledger.retain_host_custody_receipt(custody)
        self.assertEqual(lease_ledger.append_task_handoff(handoff, custody_receipt=custody)["expected_check"]["status"], "MATCHED")

        steer_root = self.root / "steer"
        steer_ledger = Ledger(steer_root)
        steer_ledger.append(self.event("steer-base", "block-a", committed=1))
        steer_expected = self.expected_receipt("expected-steer", expected_event_kind="USER_STEERING_ACCEPTED", due_event="USER_STEER")
        steer_ledger.append_expected_receipt(steer_expected)
        steer = self.event("steer-event", "block-a", kind="USER_STEERING_ACCEPTED", committed=1, observed_at_ms=2)
        steer["steering_receipt_ids"] = ["steer-receipt"]
        steer["expected_observation"] = self.observation(steer_expected)
        self.assertEqual(steer_ledger.append(steer)["expected_check"]["status"], "MATCHED")

    def test_role_manifest_revision_is_idempotent_and_reset_retains_history(self) -> None:
        builtins = self.role_manifests()
        initial = self.ledger.project_role_manifests(builtins)
        self.assertEqual((initial["built_in_count"], len(initial["roles"])), (24, 24))
        manager = next(role for role in initial["roles"] if role["id"] == "manager")
        revised = build_role_manifest(
            "manager",
            self.role_draft(manager, instructions=[*manager["instructions"], "Keep one bounded decision explicit."]),
            "user_override",
            ["user-command:manager-revision"],
        )
        event = role_material_event(
            "ROLE_MANIFEST_REVISE", event_id="manager-revision", dedupe_key="manager-revision-dedupe",
            role_id="manager", manifest=revised, expected_active_version=manager["active_version"],
            assignment_task_id=None, provenance="user-command:manager-revision", observed_at_ms=10,
        )
        self.assertEqual(self.ledger.append(event)["status"], "appended")
        self.assertEqual(self.ledger.append(event)["status"], "unchanged")
        overridden = next(role for role in self.ledger.project_role_manifests(builtins)["roles"] if role["id"] == "manager")
        self.assertTrue(overridden["override_active"])
        self.assertEqual(len(overridden["versions"]), 2)

        builtin = next(role for role in builtins if role["id"] == "manager")
        reset = role_material_event(
            "ROLE_MANIFEST_RESET", event_id="manager-reset", dedupe_key="manager-reset-dedupe",
            role_id="manager", manifest=builtin, expected_active_version=overridden["active_version"],
            assignment_task_id=None, provenance="user-command:manager-reset", observed_at_ms=11,
        )
        self.assertEqual(self.ledger.append(reset)["status"], "appended")
        restored = next(role for role in self.ledger.project_role_manifests(builtins)["roles"] if role["id"] == "manager")
        self.assertEqual(restored["active_version"], restored["canonical_version"])
        self.assertFalse(restored["override_active"])
        self.assertEqual(len(restored["versions"]), 2)

    def test_role_assignments_retain_version_and_new_tasks_use_current(self) -> None:
        builtins = self.role_manifests()
        manager = next(role for role in self.ledger.project_role_manifests(builtins)["roles"] if role["id"] == "manager")
        builtin_manager = next(role for role in builtins if role["id"] == "manager")
        before = role_material_event(
            "ROLE_ASSIGNMENT_BOUND", event_id="bind-before", dedupe_key="bind-before-dedupe",
            role_id="manager", manifest=builtin_manager, expected_active_version=manager["active_version"],
            assignment_task_id="task-before", provenance="dispatch:task-before", observed_at_ms=1,
        )
        self.assertEqual(self.ledger.append(before)["status"], "appended")
        revised = build_role_manifest("manager", self.role_draft(manager, accent="#123456"), "user_override", ["user-command:accent"])
        self.ledger.append(role_material_event(
            "ROLE_MANIFEST_REVISE", event_id="revise-between", dedupe_key="revise-between-dedupe",
            role_id="manager", manifest=revised, expected_active_version=manager["active_version"],
            assignment_task_id=None, provenance="user-command:accent", observed_at_ms=2,
        ))
        self.assertEqual(self.ledger.append(before)["status"], "unchanged")
        self.ledger.append(role_material_event(
            "ROLE_ASSIGNMENT_BOUND", event_id="bind-after", dedupe_key="bind-after-dedupe",
            role_id="manager", manifest=revised, expected_active_version=revised["version"],
            assignment_task_id="task-after", provenance="dispatch:task-after", observed_at_ms=3,
        ))
        assignments = {item["task_id"]: item for item in self.ledger.project_role_manifests(builtins)["assignments"]}
        self.assertEqual(assignments["task-before"]["manifest_version"], manager["active_version"])
        self.assertEqual(assignments["task-after"]["manifest_version"], revised["version"])
        self.assertNotEqual(assignments["task-before"]["manifest_version"], assignments["task-after"]["manifest_version"])

    def test_role_avatar_digest_and_version_are_content_bound(self) -> None:
        builtins = self.role_manifests()
        manager = next(role for role in builtins if role["id"] == "manager")
        changed = build_role_manifest("manager", self.role_draft(manager, accent="#abcdef"), "user_override", ["receipt:accent"])
        self.assertNotEqual(changed["version"], manager["version"])
        malformed = {**changed, "avatar_asset_digest": hashlib.sha256(b"other").hexdigest()}
        with self.assertRaisesRegex(ProgressEventError, "version does not match"):
            role_material_event(
                "ROLE_MANIFEST_REVISE", event_id="malformed", dedupe_key="malformed-dedupe",
                role_id="manager", manifest=malformed, expected_active_version=manager["version"],
                assignment_task_id=None, provenance="receipt:malformed", observed_at_ms=4,
            )

    def test_builtin_role_accents_are_exact_unique_and_order_independent(self) -> None:
        expected = {
            "manager": "#FF6B4A", "strategist": "#F97316", "researcher": "#22D3EE", "analyst": "#38BDF8",
            "specialist": "#6366F1", "inventor": "#D946EF", "architect": "#FBBF24", "designer": "#F72585",
            "artist": "#8B5CF6", "writer": "#C084FC", "developer": "#2563EB", "producer": "#F43F5E",
            "tester": "#14B8A6", "assistant": "#818CF8", "security": "#FF4D2E", "auditor": "#CBD5E1",
            "legal": "#E11D48", "reviewer": "#A3E635", "operator": "#10B981", "marketer": "#FB7185",
            "support": "#5EEAD4", "accountant": "#2DD4BF", "recruiter": "#A855F7", "educator": "#FDE047",
        }
        self.assertEqual(ROLE_ACCENTS, expected)
        self.assertEqual((len(ROLE_ACCENTS), len(set(ROLE_ACCENTS.values()))), (24, 24))

        builtins = self.role_manifests()
        actual = {role["id"]: role["accent"] for role in builtins}
        self.assertEqual(actual, {role_id: accent.casefold() for role_id, accent in expected.items()})
        self.assertTrue(all(validate_role_manifest(role) == role for role in builtins))

        from skills.swarm.runtime import progress_events
        reversed_roles = dict(reversed(tuple(progress_events.BUILT_IN_PROFESSIONS.items())))
        repository = Path(__file__).resolve().parents[3]
        with mock.patch.object(progress_events, "BUILT_IN_PROFESSIONS", reversed_roles):
            reordered = load_builtin_role_manifests(
                repository / "skills" / "swarm" / "roles",
                repository / "console" / "static" / "swarm-offline-disconnected.png",
            )
        self.assertEqual({role["id"]: role["accent"] for role in reordered}, actual)
        self.assertEqual({role["id"]: role["version"] for role in reordered}, {role["id"]: role["version"] for role in builtins})

        manager = next(role for role in builtins if role["id"] == "manager")
        historical = build_role_manifest("custom-guide", self.role_draft(manager, accent="#123456"), "custom", ["retained:custom"])
        self.assertEqual(validate_role_manifest(historical), historical)
        self.assertNotEqual(historical["version"], manager["version"])

    def test_role_specializations_are_bounded_metadata_and_version_bound(self) -> None:
        builtins = self.role_manifests()
        self.assertEqual(len(builtins), 24)
        self.assertTrue(all(len(role["specializations"]) == 4 for role in builtins))
        by_id = {role["id"]: role for role in builtins}
        self.assertIn("Game Development", by_id["developer"]["specializations"])
        self.assertIn("Game Design", by_id["designer"]["specializations"])
        self.assertNotIn("Friendly", by_id["reviewer"]["specializations"])
        self.assertNotIn("Hostile", by_id["reviewer"]["specializations"])
        self.assertNotIn("critic", by_id)
        self.assertIn("assistant", by_id)
        self.assertTrue(any("structural ASSIST" in item for item in by_id["assistant"]["instructions"]))
        self.assertTrue(any("Friendly or Hostile" in item for item in by_id["reviewer"]["instructions"]))

        manager = by_id["manager"]
        custom = build_role_manifest("custom-guide", self.role_draft(manager, specializations=[]), "custom", ["user-command:custom"])
        self.assertEqual(custom["specializations"], [])
        missing_specializations = self.role_draft(manager)
        missing_specializations.pop("specializations")
        with self.assertRaisesRegex(ProgressEventError, "explicitly provide specializations"):
            build_role_manifest("custom-missing", missing_specializations, "custom", ["user-command:missing"])
        changed = build_role_manifest("manager", self.role_draft(manager, specializations=["Portfolio Manager"]), "user_override", ["user-command:specialization"])
        self.assertNotEqual(changed["version"], manager["version"])
        for invalid in ([""], ["One", "one"], ["One", "Two", "Three", "Four", "Five"]):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ProgressEventError, "specialization"):
                build_role_manifest("custom-guide", self.role_draft(manager, specializations=invalid), "custom", ["user-command:invalid"])

        projection = self.ledger.project_role_manifests(builtins)
        avatar = projection["command_contract"]["avatar"]
        self.assertEqual(avatar["selection_field"], "avatar_asset_digest")
        self.assertTrue(avatar["requires_retained_immutable_asset"])
        self.assertIsNone(avatar["generation_command"])

        missing_event = role_material_event(
            "ROLE_MANIFEST_CREATE", event_id="current-missing", dedupe_key="current-missing-dedupe",
            role_id="custom-guide", manifest=custom,
            expected_active_version=None, assignment_task_id=None,
            provenance="user-command:current-missing", observed_at_ms=1_787_935_000_000,
        )
        missing_event["topology"]["role_manifest"]["manifest"].pop("specializations")
        ledger_path = self.root / PROGRESS_LEDGER_PATH
        before = ledger_path.read_bytes() if ledger_path.exists() else b""
        with self.assertRaisesRegex(ProgressEventError, "explicitly provide specializations"):
            self.ledger.append(missing_event)
        self.assertEqual(ledger_path.read_bytes() if ledger_path.exists() else b"", before)

        legacy_content = {key: value for key, value in manager.items() if key not in {"specializations", "version"}}
        legacy_version = f"builtin:{hashlib.sha256(json.dumps(legacy_content, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}"
        legacy_manifest = {**legacy_content, "version": legacy_version}
        legacy_event = role_material_event(
            "ROLE_MANIFEST_RESET", event_id="legacy-role", dedupe_key="legacy-role-dedupe",
            role_id="manager", manifest=manager,
            expected_active_version=legacy_version, assignment_task_id=None,
            provenance="legacy-role-replay", observed_at_ms=20,
        )
        legacy_event["topology"]["role_manifest"]["manifest"] = legacy_manifest
        before = ledger_path.read_bytes() if ledger_path.exists() else b""
        with self.assertRaisesRegex(ProgressEventError, "explicitly provide specializations"):
            self.ledger.append(legacy_event)
        self.assertEqual(ledger_path.read_bytes() if ledger_path.exists() else b"", before)

        legacy_digest = hashlib.sha256(json.dumps(legacy_event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        record = {"event_seq": 1, "event_digest": legacy_digest, "event": legacy_event}
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_bytes(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        retained_bytes = ledger_path.read_bytes()
        with self.assertRaisesRegex(ProgressEventError, "explicitly provide specializations"):
            ProgressLedger(self.root).project_role_manifests(builtins)
        self.assertEqual(ledger_path.read_bytes(), retained_bytes)

        late_root = self.root / "late-injection"
        late_event = json.loads(json.dumps(legacy_event))
        late_event.update({"event_id": "late-role", "dedupe_key": "late-role-dedupe", "observed_at_ms": 1_787_935_000_000})
        late_digest = hashlib.sha256(json.dumps(late_event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        late_path = late_root / PROGRESS_LEDGER_PATH
        late_path.parent.mkdir(parents=True, exist_ok=True)
        late_path.write_bytes(json.dumps({"event_seq": 1, "event_digest": late_digest, "event": late_event}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        late_bytes = late_path.read_bytes()
        with self.assertRaisesRegex(ProgressEventError, "explicitly provide specializations"):
            ProgressLedger(late_root).replay()
        self.assertEqual(late_path.read_bytes(), late_bytes)

    def test_normative_lifecycle_is_exact(self) -> None:
        self.assertEqual(
            [state.value for state in ProgressLifecycle],
            [
                "PLANNED", "READY", "ACTIVE", "WAITING_DEPENDENCY",
                "WAITING_EXTERNAL", "RETRYING", "REVIEW", "VERIFIED",
                "INVALIDATED_REWORK", "USER_PAUSED", "ACCEPTED", "TOMBSTONED",
            ],
        )

    def test_scope_dependency_split_merge_rework_and_truthful_rollup(self) -> None:
        self.ledger.append(self.event("a-create", "a", lifecycle="VERIFIED", committed=4, admitted=4, sentence="Block A is verified."))
        self.ledger.append(self.event("b-create", "b", committed=6, admitted=0, sentence="Block B is ready."))
        measured = self.ledger.project("project-alpha")
        self.assertEqual((measured["status"], measured["percent"]), ("MEASURED", 40.0))

        split = self.event("c-split", "c", kind="BLOCK_SPLIT", split_from="b", committed=None, sentence="Block B split into an unmeasured discovery slice.", observed_at_ms=2)
        self.ledger.append(split)
        unmeasured = self.ledger.project("project-alpha")
        self.assertEqual((unmeasured["status"], unmeasured["percent"], unmeasured["unmeasured_block_count"]), ("UNMEASURED", None, 1))

        merged = self.event("d-merge", "d", kind="BLOCK_MERGED", merged_from=["b", "c"], dependencies=["a"], committed=8, sentence="The split slices now share one reviewed boundary.", observed_at_ms=3)
        self.ledger.append(merged)
        rework = self.event("a-rework", "a", kind="REWORK_REQUESTED", lifecycle="INVALIDATED_REWORK", committed=4, admitted=0, sentence="Block A proof was invalidated and returned to rework.", observed_at_ms=4, flags=["rework"])
        self.ledger.append(rework)
        projection = self.ledger.project("project-alpha")
        self.assertGreaterEqual(projection["rework_weight"], 4)

        revised = self.event(
            "scope-two", "d", kind="SCOPE_REVISED", scope_version=2,
            committed=8, observed_at_ms=5,
        )
        self.ledger.append(revised)
        stale = self.event(
            "stale-scope", "d", kind="STATE_CHANGED", lifecycle="ACTIVE",
            scope_version=1, committed=8, observed_at_ms=6,
        )
        with self.assertRaisesRegex(ProgressEventError, "stale progress scope_version"):
            self.ledger.append(stale)

    def test_verified_yield_replays_proof_invalidation_and_duplicate_receipts_once(self) -> None:
        created = self.event(
            "yield-created", "yield", task_id="task-yield", committed=10,
            lifecycle="ACTIVE", observed_at_ms=10,
        )
        admitted = self.event(
            "yield-admitted", "yield", task_id="task-yield", kind="PROOF_ADMITTED",
            committed=10, admitted=4, lifecycle="REVIEW", observed_at_ms=20,
        )
        invalidated = self.event(
            "yield-invalidated", "yield", task_id="task-yield", kind="PROOF_INVALIDATED",
            committed=10, admitted=2, lifecycle="INVALIDATED_REWORK", observed_at_ms=30,
            flags=["rework"], sentence="Two proof points were invalidated.",
        )
        for event in (created, admitted, invalidated):
            self.ledger.append(event)
        self.assertEqual(self.ledger.append(admitted)["status"], "unchanged")

        projection = self.ledger.project_verified_yield(
            "project-alpha",
            [
                {"task_id": "task-yield", "observed_at_ms": 20, "tokens": 1_000},
                {"task_id": "task-yield", "observed_at_ms": 30, "tokens": 1_000},
            ],
            observed_after_ms=0,
            observed_before_ms=40,
        )

        self.assertEqual(projection["project"]["gross_admitted_delta"], 4)
        self.assertEqual(projection["project"]["invalidated_delta"], 2)
        self.assertEqual(projection["project"]["net_scope_points"], 20.0)
        self.assertEqual(projection["project"]["yield_per_100k"], 1_000.0)
        self.assertEqual(projection["project"]["measurement_state"], "MEASURED")
        self.assertEqual(projection["project"]["rework_drag"], 20.0)
        self.assertEqual([item["kind"] for item in projection["attention_items"]], ["PROOF_INVALIDATED"])
        self.assertEqual(len(projection["project"]["series"]), 3)
        self.assertTrue(projection["project"]["series"][0]["scope_start"])

    def test_verified_yield_distinguishes_unmeasured_zero_and_no_token_waiting(self) -> None:
        self.ledger.append(self.event(
            "yield-ready", "ready", task_id="task-ready", committed=5,
            lifecycle="READY", observed_at_ms=10,
        ))
        unmeasured = self.ledger.project_verified_yield(
            "project-alpha", [], observed_after_ms=0, observed_before_ms=20,
        )
        self.assertEqual(unmeasured["project"]["measurement_state"], "UNMEASURED")
        self.assertIsNone(unmeasured["project"]["yield_per_100k"])

        zero = self.ledger.project_verified_yield(
            "project-alpha",
            [{"task_id": "task-ready", "observed_at_ms": 15, "tokens": 400}],
            observed_after_ms=0,
            observed_before_ms=20,
        )
        self.assertEqual(zero["project"]["measurement_state"], "MEASURED")
        self.assertEqual(zero["project"]["yield_per_100k"], 0.0)

        waiting_root = self.root / "waiting"
        waiting_ledger = ProgressLedger(waiting_root)
        waiting_ledger.append(self.event(
            "yield-waiting", "wait", task_id="task-wait", committed=5,
            lifecycle="WAITING_EXTERNAL", observed_at_ms=10,
        ))
        waiting = waiting_ledger.project_verified_yield(
            "project-alpha", [], observed_after_ms=0, observed_before_ms=20,
        )
        self.assertEqual(waiting["project"]["measurement_state"], "NO_TOKEN_ACTIVITY")
        self.assertIsNone(waiting["project"]["yield_per_100k"])

    def test_verified_yield_starts_a_new_scope_segment_and_retains_handoff_cost(self) -> None:
        initial = self.event(
            "scope-one-yield", "yield", task_id="task-yield",
            committed=10, lifecycle="READY", observed_at_ms=5,
        )
        initial["owner_id"] = "owner-before"
        revised = self.event(
            "scope-two-yield", "yield", task_id="task-yield", kind="SCOPE_REVISED",
            scope_version=2, committed=10, lifecycle="ACTIVE", observed_at_ms=10,
        )
        revised["owner_id"] = "owner-before"
        takeover = self.event(
            "scope-two-takeover", "yield", task_id="task-yield", kind="TAKEOVER_STARTED",
            scope_version=2, committed=10, lifecycle="ACTIVE", observed_at_ms=20,
        )
        takeover["owner_id"] = "owner-after"
        admitted = self.event(
            "scope-two-proof", "yield", task_id="task-yield", kind="PROOF_ADMITTED",
            scope_version=2, committed=10, admitted=5, lifecycle="REVIEW", observed_at_ms=25,
        )
        admitted["owner_id"] = "owner-after"
        self.ledger.append(initial)
        self.ledger.append(revised)
        self.ledger.append(takeover)
        self.ledger.append(admitted)
        projection = self.ledger.project_verified_yield(
            "project-alpha",
            [
                {"task_id": "task-yield", "observed_at_ms": 15, "tokens": 250},
                {"task_id": "task-yield", "observed_at_ms": 30, "tokens": 250},
            ],
            observed_after_ms=0,
            observed_before_ms=30,
        )
        self.assertEqual(projection["project"]["scope_version"], 2)
        self.assertTrue(projection["project"]["series"][0]["scope_start"])
        owners = {item["scope"]["id"]: item for item in projection["owners"]}
        self.assertEqual(set(owners), {"owner-before", "owner-after"})
        self.assertEqual(owners["owner-before"]["observed_tokens"], 250)
        self.assertEqual(owners["owner-after"]["observed_tokens"], 250)

    def test_verified_yield_rejects_conflicting_token_identity_without_ledger_mutation(self) -> None:
        self.ledger.append(self.event(
            "yield-created", "yield", task_id="task-yield", committed=10,
            lifecycle="ACTIVE", observed_at_ms=10,
        ))
        before = self.ledger.replay()
        with self.assertRaisesRegex(ProgressEventError, "token sample identity conflicts"):
            self.ledger.project_verified_yield(
                "project-alpha",
                [
                    {"task_id": "task-yield", "observed_at_ms": 15, "tokens": 100},
                    {"task_id": "task-yield", "observed_at_ms": 15, "tokens": 101},
                ],
                observed_after_ms=0,
                observed_before_ms=20,
            )
        self.assertEqual(self.ledger.replay(), before)

    def test_feed_is_newest_first_project_scoped_and_dedupes_unchanged_material(self) -> None:
        for index in range(1, 6):
            self.ledger.append(self.event(
                f"event-{index}",
                "block-a" if index > 1 else "block-a",
                task_id="task-a",
                kind="BLOCK_CREATED" if index == 1 else "CURRENT_ACTION_CHANGED",
                lifecycle="PLANNED",
                sentence=f"Material update {index} is ready.",
                observed_at_ms=index,
            ))
        snapshot = self.ledger.feed_snapshot("project-alpha", limit=4)
        self.assertEqual([item["event_seq"] for item in snapshot["items"]], [5, 4, 3, 2])
        self.assertEqual({item["task_id"] for item in snapshot["items"]}, {"task-a"})
        self.assertEqual(snapshot["producer"]["native_host_transport"], "UNVERIFIED")

        duplicate = self.event("event-duplicate", "block-a", task_id="task-a", kind="CURRENT_ACTION_CHANGED", lifecycle="PLANNED", sentence="Material update 5 is ready.", observed_at_ms=99)
        self.assertEqual(self.ledger.append(duplicate)["status"], "unchanged")
        self.assertEqual(self.ledger.feed_snapshot("project-alpha", limit=10)["cursor"]["event_seq"], 5)

        silent = self.event("event-silent", "block-a", task_id="task-a", kind="CURRENT_ACTION_CHANGED", lifecycle="PLANNED", sentence=None, observed_at_ms=100)
        self.ledger.append(silent)
        after = self.ledger.feed_snapshot("project-alpha", limit=4)
        self.assertEqual([item["event_seq"] for item in after["items"]], [5, 4, 3, 2])

    def test_snapshot_reconnect_and_subscription_are_cursor_idempotent(self) -> None:
        self.ledger.append(self.event("event-a", "a", sentence="First material update.", observed_at_ms=1))
        first = self.ledger.feed_snapshot("project-alpha", limit=4)
        subscription = self.ledger.subscribe("project-alpha", after_cursor=first["cursor"]["event_seq"], limit=4)
        self.assertEqual(subscription.next(timeout=0)["items"], [])
        self.ledger.append(self.event("event-b", "b", sentence="Second material update.", observed_at_ms=2))
        next_snapshot = subscription.next(timeout=0)
        self.assertEqual([item["event_id"] for item in next_snapshot["items"]], ["event-b"])
        self.assertEqual(subscription.next(timeout=0)["items"], [])
        subscription.close()
        with self.assertRaisesRegex(ProgressEventError, "closed"):
            subscription.next(timeout=0)

    def test_stale_cursor_rebuilds_latest_window_without_gap_or_duplicate(self) -> None:
        event = validate_progress_material_event(
            self.event("event-late", "a", sentence="Latest retained material update.", observed_at_ms=10)
        )
        record = {**self.ledger._record(event, 10), "_event": event, "_record_id": event.event_id}
        with mock.patch.object(self.ledger, "_bounded_tail_records", return_value=([record], True)):
            snapshot = self.ledger.feed_snapshot("project-alpha", limit=4, after_cursor=2)
        self.assertTrue(snapshot["stale_cursor"])
        self.assertEqual([item["event_id"] for item in snapshot["items"]], ["event-late"])
        self.assertEqual(snapshot["cursor"]["event_seq"], 10)

    def test_closed_page_has_zero_feed_specific_writes_or_idle_work(self) -> None:
        unopened = ProgressLedger(self.root)
        self.assertFalse((self.root / PROGRESS_LEDGER_PATH).exists())
        self.assertFalse((self.root / PROGRESS_PROJECTION_PATH).exists())
        snapshot = unopened.feed_snapshot("project-alpha", limit=4)
        self.assertEqual(snapshot["items"], [])
        self.assertFalse((self.root / PROGRESS_LEDGER_PATH).exists())
        self.assertFalse((self.root / PROGRESS_PROJECTION_PATH).exists())
        self.assertNotIn("tokens", json.dumps(snapshot).casefold())

    def test_liveness_transition_is_material_but_healthy_renewal_is_not_a_feed_event(self) -> None:
        before = self.ledger.feed_snapshot("project-alpha", limit=4)
        time.sleep(0.001)
        self.assertEqual(before, self.ledger.feed_snapshot("project-alpha", limit=4))
        self.ledger.append(self.event("event-create", "a", lifecycle="ACTIVE", sentence=None, observed_at_ms=1))
        stale = self.event(
            "event-stale", "a", kind="LIVENESS_STALE", lifecycle="RETRYING",
            sentence="Ledger task has not checked in within the retained execution lease.",
            observed_at_ms=10, flags=["stale", "warning"],
        )
        self.ledger.append(stale)
        item = self.ledger.feed_snapshot("project-alpha", limit=4)["items"][0]
        self.assertEqual((item["event_kind"], item["flags"]), ("LIVENESS_STALE", ["stale", "warning"]))

    def test_privacy_fields_and_sentence_bounds_fail_closed(self) -> None:
        payload = self.event("event-private", "a", sentence="Safe material update.")
        payload["prompt"] = "private"
        with self.assertRaisesRegex(ProgressEventError, "unsupported field"):
            self.ledger.append(payload)
        long_sentence = self.event("event-long", "a", sentence="x" * 241)
        with self.assertRaisesRegex(ProgressEventError, "bounded line"):
            self.ledger.append(long_sentence)

    def test_project_topology_replay_is_byte_identical(self) -> None:
        self.ledger.append(self.topology_event("lead-create", "lead", node_kind="LEAD", lifecycle="ACTIVE"))
        self.ledger.append(self.topology_event(
            "task-create", "task", node_kind="SUBAGENT", parent_block_id="lead",
            parent_event_id="lead-create", lifecycle="READY", observed_at_ms=2,
        ))
        first = self.ledger.project_topology("project-alpha", "ctrl-alpha")
        second = ProgressLedger(self.root).project_topology("project-alpha", "ctrl-alpha")
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )

    def test_role_fit_routing_evidence_replays_once_without_progress_credit(self) -> None:
        decision = route_execution(
            facts=WorkRoutingFacts(WorkSize.MEDIUM, True, True, 1, independent_work=True, owner_busy=True),
            economics=RoutingEconomics(0, 1, 0, 0, 0, 0, 0, RoutingEvidenceBasis.CONSERVATIVE_ASSUMPTION, assumptions=("bounded test",)),
            capacity=HostCapacityEvidence(HostTaskCapacity.AVAILABLE, True, "host-capacity"),
            accountable_owner="designer-a", lead_owner="designer-a",
            scope=RoutingScope("goal-a", "request-a", "task-routing", "console/card.css", "designer-a"),
        )
        self.assertEqual(decision.role_fit, RoleFitDisposition.ADD_INSTANCE)
        event = self.topology_event("routing-event", "routing", task_id="task-routing")
        event["topology"]["routing_evidence"] = decision.topology_evidence()
        self.assertEqual(self.ledger.append(event)["status"], "appended")
        self.assertEqual(self.ledger.append(event)["status"], "unchanged")
        restarted = self.host_ledger(self.root).project_topology("project-alpha", "ctrl-alpha")
        node = next(item for item in restarted["nodes"] if item["node_id"] == "routing")
        self.assertEqual(node["routing_evidence"]["disposition"], "ADD_INSTANCE")
        self.assertTrue(node["routing_evidence"]["project_active"])
        self.assertEqual(node["routing_evidence"]["scope"]["mutable_surface"], "console/card.css")

        invalid = self.topology_event("routing-invalid", "routing-invalid", committed=1, admitted=1)
        invalid["topology"]["routing_evidence"] = decision.topology_evidence()
        before = self.host_ledger(self.root).project_topology("project-alpha", "ctrl-alpha")
        with self.assertRaisesRegex(ProgressEventError, "non-progress decision evidence"):
            self.ledger.append(invalid)
        self.assertEqual(self.host_ledger(self.root).project_topology("project-alpha", "ctrl-alpha"), before)

    def test_projection_separates_effective_time_from_knowledge_cursor(self) -> None:
        self.ledger.append(self.topology_event("late-known-first", "late", observed_at_ms=20))
        self.ledger.append(self.topology_event("early-known-later", "early", observed_at_ms=10))
        knowledge_one = self.ledger.project_topology("project-alpha", "ctrl-alpha", through_cursor=1)
        effective_ten = self.ledger.project_topology("project-alpha", "ctrl-alpha", effective_at_ms=10)
        self.assertEqual(knowledge_one["source_event_ids"], ["late-known-first"])
        self.assertEqual(effective_ten["source_event_ids"], ["early-known-later"])
        self.assertEqual((knowledge_one["through_cursor"], effective_ten["through_cursor"]), (1, 2))

    def test_duplicate_receipt_is_noop_and_conflicting_id_is_surfaced(self) -> None:
        event = self.topology_event("event-one", "one", lifecycle="ACTIVE")
        self.assertEqual(self.ledger.append(event)["status"], "appended")
        self.assertEqual(self.ledger.append(event)["status"], "unchanged")
        conflict = {**event, "owner_id": "owner-conflict"}
        self.assertEqual(self.ledger.append(conflict)["status"], "conflicted")
        projection = self.ledger.project_topology("project-alpha", "ctrl-alpha")
        self.assertEqual(projection["conflicts"][0]["kind"], "EVENT_ID")
        self.assertEqual(projection["nodes"], [{
            "node_id": "ctrl-alpha", "node_kind": "CTRL", "project_id": "project-alpha",
            "ctrl_id": "ctrl-alpha", "lifecycle_state": "OBSERVED", "source_event_ids": [],
        }])

    def test_out_of_order_parent_is_unknown_then_resolves_without_history_rewrite(self) -> None:
        child = self.topology_event(
            "child-event", "child", node_kind="SUBAGENT", parent_block_id="parent",
            parent_event_id="parent-event", observed_at_ms=20,
        )
        self.ledger.append(child)
        before = self.ledger.project_topology("project-alpha", "ctrl-alpha", through_cursor=1)
        self.ledger.append(self.topology_event(
            "parent-event", "parent", node_kind="LEAD", observed_at_ms=10,
        ))
        historical = self.ledger.project_topology("project-alpha", "ctrl-alpha", through_cursor=1)
        current = self.ledger.project_topology("project-alpha", "ctrl-alpha")
        self.assertEqual(before, historical)
        self.assertIn("parent-event", before["unknown_receipt_ids"])
        self.assertNotIn("parent-event", current["unknown_receipt_ids"])

    def test_visible_lead_parent_and_subagent_edges_share_one_ctrl_graph(self) -> None:
        self.ledger.append(self.topology_event("lead", "lead", node_kind="LEAD"))
        self.ledger.append(self.topology_event(
            "subagent", "subagent", node_kind="SUBAGENT", parent_block_id="lead",
            parent_event_id="lead", observed_at_ms=2,
        ))
        projection = self.ledger.project_topology("project-alpha", "ctrl-alpha")
        kinds = {(node["node_id"], node["node_kind"]) for node in projection["nodes"]}
        edges = {(edge["edge_kind"], edge["from_node_id"], edge["to_node_id"]) for edge in projection["edges"]}
        self.assertTrue({("ctrl-alpha", "CTRL"), ("lead", "LEAD"), ("subagent", "SUBAGENT")} <= kinds)
        self.assertIn(("PARENT", "lead", "subagent"), edges)

    def test_ready_wave_and_partial_critical_path_are_deterministic(self) -> None:
        self.ledger.append(self.topology_event("a", "a", lifecycle="ACCEPTED"))
        self.ledger.append(self.topology_event("b", "b", lifecycle="READY", dependencies=["a"], observed_at_ms=2))
        self.ledger.append(self.topology_event("c", "c", lifecycle="PLANNED", dependencies=["b"], observed_at_ms=3))
        projection = self.ledger.project_topology("project-alpha", "ctrl-alpha")
        self.assertEqual(projection["ready_waves"], [["b"], ["c"]])
        self.assertEqual(projection["critical_path"]["node_ids"], ["a", "b", "c"])
        self.assertFalse(projection["critical_path"]["partial"])

    def test_empty_retry_handoff_proof_acceptance_timeline(self) -> None:
        events = [
            self.topology_event("create", "work", lifecycle="ACTIVE", dispatch_receipt="dispatch-1"),
            self.topology_event("empty", "work", kind="STATE_CHANGED", lifecycle="RETRYING", parent_event_id="create", observed_at_ms=2, flags=["unverified"]),
            self.topology_event("retry", "work", kind="RETRY_STARTED", lifecycle="RETRYING", parent_event_id="empty", observed_at_ms=3),
            self.topology_event("handoff", "work", kind="TAKEOVER_STARTED", lifecycle="ACTIVE", parent_event_id="retry", owner_id="owner-next", observed_at_ms=4),
            self.topology_event("proof", "work", kind="PROOF_ADMITTED", lifecycle="VERIFIED", parent_event_id="handoff", proof_receipts=["proof-1"], observed_at_ms=5),
            self.topology_event("accepted", "work", kind="ACCEPTED", lifecycle="ACCEPTED", parent_event_id="proof", completion_receipt="complete-1", release_receipts=["accept-1"], owner_id="owner-next", observed_at_ms=6),
        ]
        for event in events:
            self.ledger.append(event)
        node = next(node for node in self.ledger.project_topology("project-alpha", "ctrl-alpha")["nodes"] if node["node_id"] == "work")
        self.assertEqual(node["lifecycle_state"], "ACCEPTED")
        self.assertEqual(node["source_event_ids"], [event["event_id"] for event in events])

    def test_model_prose_private_keys_and_oversize_payloads_fail_closed(self) -> None:
        first_root = self.root / "first"
        second_root = self.root / "second"
        first = self.topology_event("event", "block", sentence="Model prose A.")
        second = self.topology_event("event", "block", sentence="Different model prose B.")
        ProgressLedger(first_root).append(first)
        ProgressLedger(second_root).append(second)
        self.assertEqual(
            ProgressLedger(first_root).project_topology("project-alpha", "ctrl-alpha"),
            ProgressLedger(second_root).project_topology("project-alpha", "ctrl-alpha"),
        )
        private = self.topology_event("private", "private")
        private["prompt"] = "secret"
        with self.assertRaisesRegex(ProgressEventError, "unsupported field"):
            self.ledger.append(private)
        oversized = self.topology_event("large", "large", input_receipts=[f"receipt-{index}-" + "x" * 180 for index in range(100)])
        with self.assertRaisesRegex(ProgressEventError, "size guard"):
            self.ledger.append(oversized)

    def test_projection_recovers_after_append_before_projection_replace(self) -> None:
        event = self.topology_event("crash", "crash", lifecycle="ACTIVE")
        with mock.patch.object(self.ledger, "_write_projection_unlocked", side_effect=OSError("projection replace failed")):
            with self.assertRaisesRegex(OSError, "projection replace failed"):
                self.ledger.append(event)
        projection = ProgressLedger(self.root).project_topology("project-alpha", "ctrl-alpha")
        self.assertIn("crash", projection["source_event_ids"])

    def test_request_lifecycle_replay_conflict_and_nonterminal_guards(self) -> None:
        envelope = "1" * 64
        offer = {
            "schema_version": 1, "record_type": "REQUEST_LIFECYCLE",
            "event_id": "request-offer-1", "dedupe_key": "request-offer-dedupe-1",
            "request_id": "request-1", "stage_id": "stage-1", "parent_event_id": None,
            "envelope_digest": envelope, "lifecycle_state": "OFFERED", "record": None,
            "route_receipt_ids": [], "permitted_route_ids": [], "failed_goal_turn_receipt_ids": [],
            "release_authority": None, "release_receipt_id": None, "release_issued_at_ms": None,
        }
        first = self.ledger.append_request_lifecycle(offer)
        replay = self.ledger.append_request_lifecycle(offer)
        self.assertEqual(replay["status"], "unchanged")
        self.assertEqual(replay["cursor"], first["cursor"])
        conflict = dict(offer, stage_id="stage-other")
        with self.assertRaisesRegex(ProgressEventError, "identity conflicts"):
            self.ledger.append_request_lifecycle(conflict)
        cursor = {"event_receipt": "event-decision-1", "message_id": "message-decision-1", "surface_receipt": "surface-decision-1", "feed_sequence": 1}
        record = {
            "id": "request-1", "goal_id": "goal-1", "task_id": "task-1", "accepted_owner": "lead-1",
            "outcome_kind": "ARTIFACT", "outcome_digest": "2" * 64,
            "accepting_route": ["lead-1", "CTRL"], "accepted_at": 1,
            "next_due_event": "due-1", "next_due_at": 2, "evidence_receipts": ["proof-1"],
            "transitions": [{"state": "OPEN", "kind": "decision", "cursor": cursor}], "successor_id": "",
        }
        acknowledged = dict(offer, event_id="request-ack-1", dedupe_key="request-ack-dedupe-1", parent_event_id=offer["event_id"], lifecycle_state="ACKNOWLEDGED", record=record)
        self.ledger.append_request_lifecycle(acknowledged)
        paused = dict(acknowledged, event_id="request-pause-1", dedupe_key="request-pause-dedupe-1", parent_event_id=acknowledged["event_id"], lifecycle_state="USER_PAUSED")
        self.ledger.append_request_lifecycle(paused)
        self.assertEqual(self.ledger.project_request_lifecycles()["records"][0]["lifecycle_state"], "USER_PAUSED")
        blocked = dict(paused, event_id="request-blocked-1", dedupe_key="request-blocked-dedupe-1", parent_event_id=paused["event_id"], lifecycle_state="BLOCKED")
        before = self.ledger.project_request_lifecycles()["event_count"]
        with self.assertRaisesRegex(ProgressEventError, "retained failed goal turns"):
            self.ledger.append_request_lifecycle(blocked)
        self.assertEqual(self.ledger.project_request_lifecycles()["event_count"], before)

        resumed = dict(paused, event_id="request-resumed-1", dedupe_key="request-resumed-dedupe-1", parent_event_id=paused["event_id"], lifecycle_state="RUNNING")
        self.ledger.append_request_lifecycle(resumed)
        stalled = resumed
        permitted = ["route-a", "route-b", "route-c"]
        for index, route in enumerate(permitted, start=1):
            stalled = dict(stalled, event_id=f"request-stalled-{index}", dedupe_key=f"request-stalled-dedupe-{index}", parent_event_id=stalled["event_id"], lifecycle_state="STALLED", route_receipt_ids=[route], permitted_route_ids=permitted, failed_goal_turn_receipt_ids=[f"turn-{index}"])
            self.ledger.append_request_lifecycle(stalled)
        blocked = dict(stalled, event_id="request-blocked-2", dedupe_key="request-blocked-dedupe-2", parent_event_id=stalled["event_id"], lifecycle_state="BLOCKED")
        repeated = dict(blocked, route_receipt_ids=["route-a", "route-a", "route-a"], permitted_route_ids=["route-a"], failed_goal_turn_receipt_ids=["turn-1", "turn-2", "turn-3"], release_authority="user", release_receipt_id="c" * 64, release_issued_at_ms=4)
        with self.assertRaisesRegex(ProgressEventError, "duplicates"):
            self.ledger.append_request_lifecycle(repeated)
        terminal = dict(blocked, route_receipt_ids=["route-a", "route-b", "route-c"], permitted_route_ids=["route-a", "route-b", "route-c"], failed_goal_turn_receipt_ids=["turn-1", "turn-2", "turn-3"], release_authority="user", release_receipt_id="c" * 64, release_issued_at_ms=4)
        binding = request_blocked_release_binding(terminal)
        custody = Swarm(request_lifecycle_ledger=self.ledger)
        plugin_minted = HostCustodyReceipt("c" * 64, CustodyMutation.STATE, "request-1", binding, 4)
        object.__setattr__(plugin_minted, "_authority", custody._custody_capability)
        custody.host_custody_receipts[plugin_minted.receipt] = plugin_minted
        before_terminal = (self.root / PROGRESS_LEDGER_PATH).read_bytes()
        with self.assertRaisesRegex(ProgressEventError, "host-verified"):
            self.ledger.append_request_lifecycle(terminal, custody_receipt=plugin_minted)
        self.assertEqual((self.root / PROGRESS_LEDGER_PATH).read_bytes(), before_terminal)
        release = self.host_receipt(custody, "c" * 64, "request-1", binding, 4)
        result = self.ledger.append_request_lifecycle(terminal, custody_receipt=release)
        self.assertEqual(result["status"], "appended")
        self.assertEqual(self.ledger.project_request_lifecycles()["records"][0]["lifecycle_state"], "BLOCKED")

    def test_retained_schema_v1_request_lifecycle_replays_without_rewriting(self) -> None:
        offer = {
            "schema_version": 1, "record_type": "REQUEST_LIFECYCLE",
            "event_id": "legacy-offer", "dedupe_key": "legacy-offer-dedupe",
            "request_id": "legacy-request", "stage_id": "legacy-stage",
            "parent_event_id": None, "envelope_digest": "1" * 64,
            "lifecycle_state": "OFFERED", "record": None,
            "route_receipt_ids": [], "release_authority": None,
        }
        cursor = {"event_receipt": "legacy-event", "message_id": "legacy-message", "surface_receipt": "legacy-surface", "feed_sequence": 1}
        request_record = {
            "id": "legacy-request", "goal_id": "legacy-goal", "task_id": "legacy-task",
            "accepted_owner": "legacy-owner", "outcome_kind": "ARTIFACT",
            "outcome_digest": "2" * 64, "accepting_route": ["legacy-owner", "CTRL"],
            "accepted_at": 1, "next_due_event": "legacy-due", "next_due_at": 2,
            "evidence_receipts": ["legacy-proof"],
            "transitions": [{"state": "OPEN", "kind": "decision", "cursor": cursor}],
            "successor_id": "",
        }
        acknowledged = {
            **offer,
            "event_id": "legacy-ack", "dedupe_key": "legacy-ack-dedupe",
            "parent_event_id": offer["event_id"], "lifecycle_state": "ACKNOWLEDGED",
            "record": request_record,
        }
        ledger_path = self.root / PROGRESS_LEDGER_PATH
        before = ledger_path.read_bytes() if ledger_path.exists() else b""
        with self.assertRaisesRegex(ProgressEventError, "must be an array"):
            self.ledger.append_request_lifecycle(offer)
        self.assertEqual(ledger_path.read_bytes() if ledger_path.exists() else b"", before)

        records = []
        stalled = {
            **acknowledged,
            "event_id": "legacy-stalled", "dedupe_key": "legacy-stalled-dedupe",
            "parent_event_id": acknowledged["event_id"], "lifecycle_state": "STALLED",
        }
        for sequence, event in enumerate((offer, acknowledged, stalled), 1):
            digest = hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            records.append({"event_seq": sequence, "event_digest": digest, "event": event})
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_bytes(b"".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n" for record in records))
        retained_bytes = ledger_path.read_bytes()
        projection = ProgressLedger(self.root).project_request_lifecycles()
        self.assertEqual((projection["event_count"], projection["records"][0]["lifecycle_state"]), (3, "STALLED"))
        self.assertEqual(ledger_path.read_bytes(), retained_bytes)

        blocked = {
            **stalled,
            "event_id": "current-blocked", "dedupe_key": "current-blocked-dedupe",
            "parent_event_id": stalled["event_id"], "lifecycle_state": "BLOCKED",
            "route_receipt_ids": ["route-a", "route-b", "route-c"],
            "permitted_route_ids": ["route-a", "route-b", "route-c"],
            "failed_goal_turn_receipt_ids": ["turn-a", "turn-b", "turn-c"],
            "release_authority": "user", "release_receipt_id": "d" * 64,
            "release_issued_at_ms": 4,
        }
        binding = request_blocked_release_binding(blocked)
        custody = Swarm(request_lifecycle_ledger=self.ledger)
        release = self.host_receipt(custody, "d" * 64, "legacy-request", binding, 4)
        with self.assertRaisesRegex(ProgressEventError, "matching retained distinct failed goal turns"):
            self.ledger.append_request_lifecycle(blocked, custody_receipt=release)
        self.assertEqual(ledger_path.read_bytes(), retained_bytes)

    def _continuity_swarm(self, *, user_keep_out: bool = False, owner: str = "owner-old", ledger: ProgressLedger | None = None) -> tuple[Swarm, Task, TaskStartReceipt]:
        task = Task("task-life", owner, "creator", 1, {}, goal_id="goal-life", user_custody_required=user_keep_out)
        swarm = Swarm(
            workers={"owner-old": Worker("owner-old", "lead-1", 1), "owner-new": Worker("owner-new", "lead-1", 2)},
            tasks={task.id: task},
            request_lifecycle_ledger=ledger or self.ledger,
            task_lifetime_hours=4,
        )
        swarm.workers[owner].task_ids.add(task.id)
        receipt_id = "a" * 64
        placeholder = HostCustodyReceipt(receipt_id, CustodyMutation.STATE, task.id, "0" * 64, 1_000)
        provisional = TaskStartReceipt(placeholder, task.goal_id, task.id, owner, 1_000, 1, 1)
        handoff_id = swarm._handoff_id(provisional)
        event = swarm._handoff_event(None, "HANDOFF_DUE", handoff_id=handoff_id, goal_id=task.goal_id, task_id=task.id, old_owner=owner, new_owner=None, checkpoint_digest=None, scope_version=1, lease_version=1, receipt_id=receipt_id, host_issued_at_ms=1_000, observed_at_ms=14_401_000)
        receipt = self.host_receipt(swarm, receipt_id, task.id, task_handoff_host_binding(event), 1_000)
        return swarm, task, TaskStartReceipt(receipt, task.goal_id, task.id, owner, 1_000, 1, 1)

    def _ack_receipt(self, swarm: Swarm, handoff_id: str, checkpoint: str, observed_at_ms: int, *, receipt_id: str = "b" * 64) -> HostCustodyReceipt:
        current = next(item for item in swarm._task_handoff_ledger().project_task_handoffs()["records"] if item["handoff_id"] == handoff_id)
        event = swarm._handoff_event(current, "HANDOFF_ACKNOWLEDGED", handoff_id=handoff_id, goal_id=current["goal_id"], task_id=current["task_id"], old_owner=current["old_owner"], new_owner=current["new_owner"], checkpoint_digest=checkpoint, scope_version=current["scope_version"], lease_version=current["lease_version"], receipt_id=receipt_id, host_issued_at_ms=observed_at_ms, observed_at_ms=observed_at_ms)
        return self.host_receipt(swarm, receipt_id, current["task_id"], task_handoff_host_binding(event), observed_at_ms)

    def test_task_lifetime_due_once_requires_checkpoint_ack_and_exact_replay(self) -> None:
        swarm, task, start = self._continuity_swarm()
        self.assertEqual(swarm.task_handoff_due(Role.LEAD, task.id, start, now_ms=14_400_999)["state"], "RUNNING")
        due = swarm.task_handoff_due(Role.LEAD, task.id, start, now_ms=14_401_000)
        replay = swarm.task_handoff_due(Role.LEAD, task.id, start, now_ms=20_000_000)
        self.assertEqual((due["state"], replay["handoff_id"]), ("HANDOFF_DUE", due["handoff_id"]))
        self.assertEqual(self.ledger.project_task_handoffs()["event_count"], 1)
        self.assertEqual(task.owner, "owner-old")
        with self.assertRaisesRegex((InvariantError, ProgressEventError), "checkpoint"):
            swarm.offer_task_handoff(Role.LEAD, due["handoff_id"], new_owner="owner-new", checkpoint_digest="bad", observed_at_ms=14_401_001)
        checkpoint = "a" * 64
        swarm.offer_task_handoff(Role.LEAD, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, observed_at_ms=14_401_002)
        self.assertEqual(task.owner, "owner-old")
        before_ack = (self.root / PROGRESS_LEDGER_PATH).read_bytes()
        with self.assertRaisesRegex(InvariantError, "typed host-minted"):
            swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt="host:thread:owner-new:task-life:1", observed_at_ms=14_401_003)  # type: ignore[arg-type]
        forged = HostCustodyReceipt("b" * 64, CustodyMutation.STATE, task.id, "0" * 64, 14_401_003)
        with self.assertRaisesRegex((InvariantError, ProgressEventError), "host-verified"):
            swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt=forged, observed_at_ms=14_401_003)
        self.assertEqual((self.root / PROGRESS_LEDGER_PATH).read_bytes(), before_ack)
        host_ack = self._ack_receipt(swarm, due["handoff_id"], checkpoint, 14_401_003)
        acknowledgement = swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt=host_ack, observed_at_ms=14_401_003)
        self.assertEqual(task.owner, "owner-old")
        replay_ack = swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt=host_ack, observed_at_ms=14_401_003)
        self.assertEqual(replay_ack["cursor"], acknowledgement["cursor"])
        before = (self.root / PROGRESS_LEDGER_PATH).read_bytes()
        with self.assertRaisesRegex(InvariantError, "conflicts"):
            swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest="b" * 64, host_task_receipt=host_ack, observed_at_ms=14_401_004)
        self.assertEqual((self.root / PROGRESS_LEDGER_PATH).read_bytes(), before)
        result = swarm.transfer_task_custody(Role.LEAD, due["handoff_id"], observed_at_ms=14_401_005)
        self.assertEqual((result["owner"], task.owner, result["lease_version"]), ("owner-new", "owner-new", 2))
        self.assertEqual(task.current_lease_version, 2)

    def test_task_handoff_restart_keep_out_and_ctrl_authority_boundaries(self) -> None:
        swarm, task, start = self._continuity_swarm()
        due = swarm.task_handoff_due(Role.LEAD, task.id, start, now_ms=14_401_000)
        checkpoint = "c" * 64
        swarm.offer_task_handoff(Role.LEAD, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, observed_at_ms=14_401_001)
        host_ack = self._ack_receipt(swarm, due["handoff_id"], checkpoint, 14_401_002)
        swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt=host_ack, observed_at_ms=14_401_002)
        swarm.transfer_task_custody(Role.LEAD, due["handoff_id"], observed_at_ms=14_401_003)
        restarted_task = Task(task.id, "owner-old", "creator", 1, {}, goal_id=task.goal_id)
        old_worker = Worker("owner-old", "lead-1", 1); old_worker.task_ids.add(task.id)
        restarted = Swarm(workers={"owner-old": old_worker, "owner-new": Worker("owner-new", "lead-1", 2)}, tasks={task.id: restarted_task}, request_lifecycle_ledger=ProgressLedger(self.root))
        self.assertEqual(restarted.reconcile_task_handoffs(), (task.id,))
        self.assertEqual(restarted_task.owner, "owner-new")
        self.assertEqual(restarted_task.current_lease_version, 2)
        self.assertEqual(restarted.reconcile_task_handoffs(), ())
        self.assertEqual(restarted.scheduled_wakeups, {})

        with tempfile.TemporaryDirectory() as directory:
            keep_ledger = self.host_ledger(directory)
            keep, keep_task, keep_start = self._continuity_swarm(user_keep_out=True, ledger=keep_ledger)
            kept = keep.task_handoff_due(Role.LEAD, keep_task.id, keep_start, now_ms=14_401_000)
            self.assertEqual(kept["state"], "KEEP_OUT")
            with self.assertRaisesRegex(InvariantError, "KEEP_OUT"):
                keep.offer_task_handoff(Role.LEAD, kept["handoff_id"], new_owner="owner-new", checkpoint_digest="d" * 64, observed_at_ms=14_401_001)
            self.assertNotIn("BLOCKED", {item["event_kind"] for item in keep_ledger.project_task_handoffs()["records"]})

        with tempfile.TemporaryDirectory() as directory:
            ctrl_ledger = self.host_ledger(directory)
            ctrl_task = Task("task-ctrl", "CTRL", "creator", 1, {}, goal_id="goal-ctrl")
            ctrl = Swarm(tasks={ctrl_task.id: ctrl_task}, request_lifecycle_ledger=ctrl_ledger)
            receipt_id = "d" * 64
            placeholder = HostCustodyReceipt(receipt_id, CustodyMutation.STATE, ctrl_task.id, "0" * 64, 1_000)
            provisional = TaskStartReceipt(placeholder, ctrl_task.goal_id, ctrl_task.id, "CTRL", 1_000)
            handoff_id = ctrl._handoff_id(provisional)
            event = ctrl._handoff_event(None, "HANDOFF_DUE", handoff_id=handoff_id, goal_id=ctrl_task.goal_id, task_id=ctrl_task.id, old_owner="CTRL", new_owner=None, checkpoint_digest=None, scope_version=1, lease_version=1, receipt_id=receipt_id, host_issued_at_ms=1_000, observed_at_ms=14_401_000)
            ctrl_receipt = self.host_receipt(ctrl, receipt_id, ctrl_task.id, task_handoff_host_binding(event), 1_000)
            ctrl_start = TaskStartReceipt(ctrl_receipt, ctrl_task.goal_id, ctrl_task.id, "CTRL", 1_000)
            ctrl_due = ctrl.task_handoff_due(Role.CTRL, ctrl_task.id, ctrl_start, now_ms=14_401_000)
            self.assertEqual(ctrl_due["state"], "NEEDS_AUTHORITY")
            with self.assertRaisesRegex(InvariantError, "successor CTRL"):
                ctrl.offer_task_handoff(Role.CTRL, ctrl_due["handoff_id"], new_owner="owner-new", checkpoint_digest="e" * 64, observed_at_ms=14_401_001)

    def test_handoff_host_receipts_and_transfer_validate_before_mutation(self) -> None:
        swarm, task, start = self._continuity_swarm()
        forged_start = TaskStartReceipt(HostCustodyReceipt("e" * 64, CustodyMutation.STATE, task.id, "0" * 64, 1_000), task.goal_id, task.id, task.owner, 1_000)
        ledger_path = self.root / PROGRESS_LEDGER_PATH
        before = ledger_path.read_bytes() if ledger_path.exists() else b""
        with self.assertRaisesRegex((InvariantError, ProgressEventError), "host-verified"):
            swarm.task_handoff_due(Role.LEAD, task.id, forged_start, now_ms=14_401_000)
        self.assertEqual(ledger_path.read_bytes() if ledger_path.exists() else b"", before)

        due = swarm.task_handoff_due(Role.LEAD, task.id, start, now_ms=14_401_000)
        checkpoint = "f" * 64
        swarm.offer_task_handoff(Role.LEAD, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, observed_at_ms=14_401_001)
        acknowledgement = self._ack_receipt(swarm, due["handoff_id"], checkpoint, 14_401_002)
        swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt=acknowledgement, observed_at_ms=14_401_002)
        expected_worker = swarm.workers["owner-new"]
        for label, replacement in (
            ("missing", None),
            ("retired", Worker("owner-new", "lead-1", 2, WorkerState.RETIRED)),
            ("mismatched", Worker("different-owner", "lead-1", 2)),
        ):
            with self.subTest(target=label):
                before_transfer = ledger_path.read_bytes()
                if replacement is None:
                    swarm.workers.pop("owner-new")
                else:
                    swarm.workers["owner-new"] = replacement
                with self.assertRaisesRegex(InvariantError, "target is unavailable"):
                    swarm.transfer_task_custody(Role.LEAD, due["handoff_id"], observed_at_ms=14_401_003)
                self.assertEqual(ledger_path.read_bytes(), before_transfer)
                self.assertEqual(task.owner, "owner-old")
                swarm.workers["owner-new"] = expected_worker
        restarted_task = Task(task.id, "owner-old", "creator", 1, {}, goal_id=task.goal_id)
        restart_old = Worker("owner-old", "lead-1", 1); restart_old.task_ids.add(task.id)
        restarted = Swarm(workers={"owner-old": restart_old, "owner-new": Worker("owner-new", "lead-1", 2, WorkerState.RETIRED)}, tasks={task.id: restarted_task}, request_lifecycle_ledger=ProgressLedger(self.root))
        self.assertEqual(restarted.reconcile_task_handoffs(), ())
        self.assertEqual(restarted_task.owner, "owner-old")

        mismatch_factories = (
            ("goal", lambda: (Task(task.id, "owner-old", "creator", 1, {}, goal_id="other-goal"), Worker("owner-old", "lead-1", 1), Worker("owner-new", "lead-1", 2))),
            ("scope", lambda: (Task(task.id, "owner-old", "creator", 1, {}, goal_id=task.goal_id, objective_version=2), Worker("owner-old", "lead-1", 1), Worker("owner-new", "lead-1", 2))),
            ("lease", lambda: (Task(task.id, "owner-old", "creator", 1, {}, goal_id=task.goal_id, current_lease_version=2), Worker("owner-old", "lead-1", 1), Worker("owner-new", "lead-1", 2))),
            ("old-owner", lambda: (Task(task.id, "owner-old", "creator", 1, {}, goal_id=task.goal_id), Worker("different-old", "lead-1", 1), Worker("owner-new", "lead-1", 2))),
            ("new-owner", lambda: (Task(task.id, "owner-old", "creator", 1, {}, goal_id=task.goal_id), Worker("owner-old", "lead-1", 1), Worker("different-new", "lead-1", 2))),
            ("target-state", lambda: (Task(task.id, "owner-old", "creator", 1, {}, goal_id=task.goal_id), Worker("owner-old", "lead-1", 1), Worker("owner-new", "lead-1", 2, WorkerState.RETIRED))),
        )
        for label, factory in mismatch_factories:
            with self.subTest(restart_binding=label):
                candidate_task, candidate_old, candidate_new = factory()
                candidate_old.task_ids.add(task.id)
                candidate = Swarm(workers={"owner-old": candidate_old, "owner-new": candidate_new}, tasks={task.id: candidate_task}, request_lifecycle_ledger=ProgressLedger(self.root))
                before_state = (candidate_task.owner, candidate_task.current_lease_version, candidate_task.handoff_active, frozenset(candidate_old.task_ids), frozenset(candidate_new.task_ids))
                self.assertEqual(candidate.reconcile_task_handoffs(), ())
                self.assertEqual((candidate_task.owner, candidate_task.current_lease_version, candidate_task.handoff_active, frozenset(candidate_old.task_ids), frozenset(candidate_new.task_ids)), before_state)

    def test_source_and_plugin_mirrors_are_exact(self) -> None:
        repository = Path(__file__).resolve().parents[3]
        pairs = (
            (repository / "skills/swarm/runtime/core.py", repository / "plugins/swarm/skills/swarm/runtime/core.py"),
            (repository / "skills/swarm/runtime/progress_events.py", repository / "plugins/swarm/skills/swarm/runtime/progress_events.py"),
            (repository / "skills/swarm/references/task-contract.md", repository / "plugins/swarm/skills/swarm/references/task-contract.md"),
        )
        for canonical, mirror in pairs:
            with self.subTest(path=canonical.name):
                self.assertEqual(canonical.read_bytes(), mirror.read_bytes())

    def test_role_gate_preserves_structural_authority_and_exact_custody(self) -> None:
        task = Task("task-gate", "owner-gate", "shaper", 1, {}, owning_lead_id="lead-gate", assigned_profession="designer")
        self.assertEqual(role_gate(Role.CTRL, task, OperationClass.GENERATE, actor_id="CTRL", lease_version=1), RoleGateDecision.DELEGATE)
        self.assertEqual(role_gate(Role.LEAD, task, OperationClass.GENERATE, actor_id="lead-gate", lease_version=1), RoleGateDecision.ALLOW)
        self.assertEqual(role_gate(Role.DOER, task, OperationClass.GENERATE, actor_id="owner-gate", lease_version=1), RoleGateDecision.ALLOW)
        self.assertEqual(role_gate(Role.DOER, task, OperationClass.GENERATE, actor_id="owner-gate", lease_version=2), RoleGateDecision.DENY)
        self.assertEqual(role_gate(Role.DOER, task, "generate", actor_id="owner-gate", lease_version=1), RoleGateDecision.DENY)  # type: ignore[arg-type]
        task.user_custody_required = True
        self.assertEqual(role_gate(Role.LEAD, task, OperationClass.GENERATE, actor_id="lead-gate", lease_version=1), RoleGateDecision.DENY)
        self.assertEqual(role_gate(Role.LEAD, task, OperationClass.INSPECT, actor_id="lead-gate", lease_version=1), RoleGateDecision.ALLOW)

    def test_role_gate_profession_collisions_and_independent_acceptance(self) -> None:
        assistant = Task("task-assistant", "assistant-owner", "creator", 1, {}, owning_lead_id="lead-a", profession_assignment=ProfessionAssignment("assistant"))
        self.assertEqual(role_gate(Role.DOER, assistant, OperationClass.EXECUTE, actor_id="assistant-owner", lease_version=1), RoleGateDecision.ALLOW)
        self.assertEqual(role_gate(Role.DOER, assistant, OperationClass.MUTATE, actor_id="assistant-owner", lease_version=1), RoleGateDecision.DENY)
        reviewer_lane = Task("task-reviewer", "reviewer-owner", "creator", 1, {}, owning_lead_id="lead-r", assigned_profession="reviewer")
        self.assertEqual(role_gate(Role.LEAD, reviewer_lane, OperationClass.ACCEPT, actor_id="lead-r", lease_version=1), RoleGateDecision.DENY)
        artifact = ArtifactIdentity("artifact", "frozen", "review")
        frozen = Task("task-frozen", "producer", "creator", 1, {}, owning_lead_id="lead-p", assigned_profession="reviewer", acceptance_contract=AcceptanceContract(artifact, ("source",)), artifacts={artifact.key(): "producer"})
        self.assertEqual(role_gate(Role.REVIEW, frozen, OperationClass.ACCEPT, actor_id="independent-review", lease_version=1), RoleGateDecision.ALLOW)
        self.assertEqual(role_gate(Role.REVIEW, frozen, OperationClass.ACCEPT, actor_id="producer", lease_version=1), RoleGateDecision.DENY)

    def test_dispatch_and_ledger_admission_fail_before_mutation(self) -> None:
        swarm = Swarm(topology={"lead-gate"}, workers={"owner-gate": Worker("owner-gate", "lead-gate", 1)})
        dispatch_artifact = ArtifactIdentity("dispatch", "role-gate", "source")
        dispatch_contract = DelegationContract("task-denied", "Return one bounded result.", "owner-gate", ("skills/swarm/runtime",), dispatch_artifact, ("skills/swarm/runtime/core.py",), (ProofClass.SOURCE,), 100)
        denied = Task("task-denied", "owner-gate", "creator", 1, {}, subagent_receipt="host:thread:task-denied", user_custody_required=True, delegation_contract=dispatch_contract)
        before = (dict(swarm.tasks), set(swarm.workers["owner-gate"].task_ids))
        with self.assertRaisesRegex(InvariantError, "role gate denied"):
            swarm.assign(Role.LEAD, denied)
        self.assertEqual((swarm.tasks, swarm.workers["owner-gate"].task_ids), before)

        task = Task("task-gate", "owner-task-gate", "creator", 1, {}, owning_lead_id="lead-gate", assigned_profession="designer")
        payload = self.event("role-gate-event", "gate", task_id=task.id)
        ledger_path = self.root / PROGRESS_LEDGER_PATH
        with self.assertRaisesRegex(ProgressEventError, "role gate denied"):
            self.ledger.append_admitted(payload, task=task, actor=Role.DOER, operation=OperationClass.GENERATE, actor_id=task.owner, lease_version=2)
        self.assertFalse(ledger_path.exists())
        result = self.ledger.append_admitted(payload, task=task, actor=Role.DOER, operation=OperationClass.GENERATE, actor_id=task.owner, lease_version=1)
        self.assertEqual(result["status"], "appended")
        restarted = ProgressLedger(self.root)
        self.assertEqual(restarted.append_admitted(payload, task=task, actor=Role.DOER, operation=OperationClass.GENERATE, actor_id=task.owner, lease_version=1)["status"], "unchanged")
        self.assertIs(Ledger, ProgressLedger)


if __name__ == "__main__":
    unittest.main()
