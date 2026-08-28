from __future__ import annotations

import json
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from skills.swarm.runtime.progress_events import (
    PROGRESS_LEDGER_PATH,
    PROGRESS_PROJECTION_PATH,
    ProgressEventError,
    ProgressLifecycle,
    ProgressLedger,
    build_role_manifest,
    load_builtin_role_manifests,
    role_material_event,
    validate_progress_material_event,
)
from skills.swarm.runtime.core import InvariantError, Role, Swarm, Task, TaskStartReceipt, Worker


class ProgressLedgerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = ProgressLedger(self.root)

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
            "default_skills", "avatar_asset_digest", "accent",
        )}
        draft.update(changes)
        return draft

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
        record = {**self.ledger._record(event, 10), "_event": event}
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
            "route_receipt_ids": [], "release_authority": None,
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
        with self.assertRaisesRegex(ProgressEventError, "distinct exhausted routes"):
            self.ledger.append_request_lifecycle(blocked)
        self.assertEqual(self.ledger.project_request_lifecycles()["event_count"], before)

    def _continuity_swarm(self, *, user_keep_out: bool = False, owner: str = "owner-old") -> tuple[Swarm, Task, TaskStartReceipt]:
        task = Task("task-life", owner, "creator", 1, {}, goal_id="goal-life", user_custody_required=user_keep_out)
        swarm = Swarm(
            workers={"owner-old": Worker("owner-old", "lead-1", 1), "owner-new": Worker("owner-new", "lead-1", 2)},
            tasks={task.id: task},
            request_lifecycle_ledger=self.ledger,
            task_lifetime_hours=4,
        )
        swarm.workers[owner].task_ids.add(task.id)
        return swarm, task, TaskStartReceipt("start-receipt-1", task.goal_id, task.id, owner, 1_000, 1, 1)

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
        with self.assertRaisesRegex(ProgressEventError, "host target owner"):
            swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt="host:thread:wrong-owner:task-life:1", observed_at_ms=14_401_003)
        self.assertEqual((self.root / PROGRESS_LEDGER_PATH).read_bytes(), before_ack)
        acknowledgement = swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt="host:thread:owner-new:task-life:1", observed_at_ms=14_401_003)
        self.assertEqual(task.owner, "owner-old")
        replay_ack = swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt="host:thread:owner-new:task-life:1", observed_at_ms=14_401_003)
        self.assertEqual(replay_ack["cursor"], acknowledgement["cursor"])
        before = (self.root / PROGRESS_LEDGER_PATH).read_bytes()
        with self.assertRaisesRegex(InvariantError, "conflicts"):
            swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest="b" * 64, host_task_receipt="host:thread:owner-new:task-life:1", observed_at_ms=14_401_004)
        self.assertEqual((self.root / PROGRESS_LEDGER_PATH).read_bytes(), before)
        result = swarm.transfer_task_custody(Role.LEAD, due["handoff_id"], observed_at_ms=14_401_005)
        self.assertEqual((result["owner"], task.owner, result["lease_version"]), ("owner-new", "owner-new", 2))

    def test_task_handoff_restart_keep_out_and_ctrl_authority_boundaries(self) -> None:
        swarm, task, start = self._continuity_swarm()
        due = swarm.task_handoff_due(Role.LEAD, task.id, start, now_ms=14_401_000)
        checkpoint = "c" * 64
        swarm.offer_task_handoff(Role.LEAD, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, observed_at_ms=14_401_001)
        swarm.acknowledge_task_handoff(Role.DOER, due["handoff_id"], new_owner="owner-new", checkpoint_digest=checkpoint, host_task_receipt="host:thread:owner-new:task-life:1", observed_at_ms=14_401_002)
        swarm.transfer_task_custody(Role.LEAD, due["handoff_id"], observed_at_ms=14_401_003)
        restarted_task = Task(task.id, "owner-old", "creator", 1, {}, goal_id=task.goal_id)
        restarted = Swarm(workers={"owner-old": Worker("owner-old", "lead-1", 1), "owner-new": Worker("owner-new", "lead-1", 2)}, tasks={task.id: restarted_task}, request_lifecycle_ledger=ProgressLedger(self.root))
        self.assertEqual(restarted.reconcile_task_handoffs(), (task.id,))
        self.assertEqual(restarted_task.owner, "owner-new")
        self.assertEqual(restarted.scheduled_wakeups, {})

        with tempfile.TemporaryDirectory() as directory:
            keep_ledger = ProgressLedger(directory)
            keep, keep_task, keep_start = self._continuity_swarm(user_keep_out=True)
            keep.request_lifecycle_ledger = keep_ledger
            kept = keep.task_handoff_due(Role.LEAD, keep_task.id, keep_start, now_ms=14_401_000)
            self.assertEqual(kept["state"], "KEEP_OUT")
            with self.assertRaisesRegex(InvariantError, "KEEP_OUT"):
                keep.offer_task_handoff(Role.LEAD, kept["handoff_id"], new_owner="owner-new", checkpoint_digest="d" * 64, observed_at_ms=14_401_001)
            self.assertNotIn("BLOCKED", {item["event_kind"] for item in keep_ledger.project_task_handoffs()["records"]})

        with tempfile.TemporaryDirectory() as directory:
            ctrl_ledger = ProgressLedger(directory)
            ctrl_task = Task("task-ctrl", "CTRL", "creator", 1, {}, goal_id="goal-ctrl")
            ctrl = Swarm(tasks={ctrl_task.id: ctrl_task}, request_lifecycle_ledger=ctrl_ledger)
            ctrl_start = TaskStartReceipt("start-receipt-ctrl", ctrl_task.goal_id, ctrl_task.id, "CTRL", 1_000)
            ctrl_due = ctrl.task_handoff_due(Role.CTRL, ctrl_task.id, ctrl_start, now_ms=14_401_000)
            self.assertEqual(ctrl_due["state"], "NEEDS_AUTHORITY")
            with self.assertRaisesRegex(InvariantError, "successor CTRL"):
                ctrl.offer_task_handoff(Role.CTRL, ctrl_due["handoff_id"], new_owner="owner-new", checkpoint_digest="e" * 64, observed_at_ms=14_401_001)

    def test_source_and_plugin_mirrors_are_exact(self) -> None:
        repository = Path(__file__).resolve().parents[3]
        pairs = (
            (repository / "skills/swarm/runtime/progress_events.py", repository / "plugins/swarm/skills/swarm/runtime/progress_events.py"),
            (repository / "skills/swarm/references/task-contract.md", repository / "plugins/swarm/skills/swarm/references/task-contract.md"),
        )
        for canonical, mirror in pairs:
            with self.subTest(path=canonical.name):
                self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
