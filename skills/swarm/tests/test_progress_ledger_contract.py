from __future__ import annotations

import json
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
    validate_progress_material_event,
)


class ProgressLedgerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = ProgressLedger(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

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


if __name__ == "__main__":
    unittest.main()
