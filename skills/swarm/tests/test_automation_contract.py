from __future__ import annotations

import unittest

from skills.swarm.runtime import (
    ArchiveFacts,
    AutomationAction,
    AutomationMode,
    AutomationStatus,
    DelegatedReceiptVerdict,
    FetchReceipt,
    GitRelationship,
    IndependentReviewReceipt,
    StableCheckpoint,
    archive_request_decision,
    commit_decision,
    git_advance_decision,
    release_decision,
    review_decision,
)


class AutomationContractTests(unittest.TestCase):
    def checkpoint(self, *, dirty=("src/app.py",), blocker="") -> StableCheckpoint:
        return StableCheckpoint(
            task_id="task-1",
            task_state="complete",
            source_sha="a" * 40,
            source_tree="b" * 40,
            source_parent="c" * 40,
            owned_paths=("src/app.py", "tests/test_app.py"),
            dirty_paths=dirty,
            proof_manifest=("python -B -m unittest tests.test_app:PASS",),
            claim_limits=("source only",),
            blocker=blocker,
            next_action="route independent review",
        )

    def review(self, verdict=DelegatedReceiptVerdict.ACCEPT) -> IndependentReviewReceipt:
        return IndependentReviewReceipt(
            visible_task_id="review-task-1",
            reviewer_id="review-owner",
            producer_id="implementation-owner",
            candidate_sha="a" * 40,
            candidate_tree="b" * 40,
            artifact_digest="d" * 64,
            verdict=verdict,
            readable_receipt=f"{verdict.value}: exact candidate reviewed",
        )

    def fetch(self, relationship=GitRelationship.FAST_FORWARD, compatibility="") -> FetchReceipt:
        return FetchReceipt(
            branch="main",
            local_head="a" * 40,
            remote_head="e" * 40,
            relationship=relationship,
            fetched_at_ms=1,
            compatible_remote_review_receipt=compatibility,
        )

    def archive_facts(self, **changes) -> ArchiveFacts:
        values = dict(
            task_id="task-1",
            task_state="complete",
            accepted_completion=True,
            process_quiescent=True,
            handles_clear=True,
            logs_quiescent=True,
            target_state_digest="f" * 64,
            host_custody_receipt_ref="host-custody-current-1",
        )
        values.update(changes)
        return ArchiveFacts(**values)

    def test_standard_allows_only_exact_owned_commit_and_manual_opts_out(self) -> None:
        exact = commit_decision(AutomationMode.STANDARD, self.checkpoint(), attributable_paths=("src/app.py",))
        self.assertEqual((exact.action, exact.status, exact.paths), (AutomationAction.COMMIT, AutomationStatus.READY, ("src/app.py",)))
        mixed = commit_decision(
            AutomationMode.STANDARD,
            self.checkpoint(dirty=("src/app.py", "notes/user.txt")),
            attributable_paths=("src/app.py",),
        )
        self.assertEqual(mixed.status, AutomationStatus.BLOCKED)
        self.assertIn("mixed", mixed.blocker)
        manual = commit_decision(AutomationMode.MANUAL, self.checkpoint(), attributable_paths=("src/app.py",))
        self.assertEqual((manual.action, manual.status), (AutomationAction.NONE, AutomationStatus.MANUAL))

    def test_readable_independent_accept_is_required_before_git_advance(self) -> None:
        checkpoint = self.checkpoint()
        self.assertEqual(review_decision(AutomationMode.STANDARD, checkpoint, None).status, AutomationStatus.BLOCKED)
        for verdict in (DelegatedReceiptVerdict.REJECT, DelegatedReceiptVerdict.BLOCKED):
            with self.subTest(verdict=verdict):
                self.assertEqual(review_decision(AutomationMode.STANDARD, checkpoint, self.review(verdict)).status, AutomationStatus.BLOCKED)
        accepted = review_decision(AutomationMode.STANDARD, checkpoint, self.review())
        self.assertEqual(accepted.status, AutomationStatus.READY)

    def test_fetch_divergence_and_push_are_history_preserving(self) -> None:
        checkpoint, review = self.checkpoint(), self.review()
        self.assertIn("fetch", git_advance_decision(AutomationMode.STANDARD, checkpoint, review, None, push_policy_receipt="repo-policy:push-main").blocker)
        diverged = git_advance_decision(
            AutomationMode.STANDARD,
            checkpoint,
            review,
            self.fetch(GitRelationship.DIVERGED),
            push_policy_receipt="repo-policy:push-main",
        )
        self.assertEqual(diverged.status, AutomationStatus.BLOCKED)
        compatible = git_advance_decision(
            AutomationMode.STANDARD,
            checkpoint,
            review,
            self.fetch(GitRelationship.DIVERGED, "review:remote-compatible"),
            push_policy_receipt="repo-policy:push-main",
        )
        self.assertEqual((compatible.action, compatible.method), (AutomationAction.PUSH, "merge_reviewed_remote_history"))
        normal = git_advance_decision(
            AutomationMode.STANDARD,
            checkpoint,
            review,
            self.fetch(),
            push_policy_receipt="repo-policy:push-main",
        )
        self.assertEqual(normal.method, "fast_forward_preserving_history")
        wrong_fetch = FetchReceipt("main", "9" * 40, "e" * 40, GitRelationship.FAST_FORWARD, 1)
        self.assertIn(
            "accepted local candidate",
            git_advance_decision(AutomationMode.STANDARD, checkpoint, review, wrong_fetch).blocker,
        )
        for decision in (compatible, normal):
            text = f"{decision.method} {decision.claim_limit}".casefold()
            self.assertNotIn("force-push eligible", text)
            self.assertIn("never", decision.claim_limit.casefold())

    def test_release_requires_repository_path_gates_and_rollback(self) -> None:
        blocked = release_decision(
            AutomationMode.STANDARD,
            repository_release_path="",
            source_gate_passed=True,
            package_gate_passed=True,
            rollback_receipt="rollback-1",
        )
        self.assertEqual(blocked.status, AutomationStatus.BLOCKED)
        ready = release_decision(
            AutomationMode.STANDARD,
            repository_release_path="scripts/build_package.py -> codex plugin add swarm@flowwweb",
            source_gate_passed=True,
            package_gate_passed=True,
            rollback_receipt="rollback-1",
        )
        self.assertEqual((ready.action, ready.status), (AutomationAction.RELEASE, AutomationStatus.READY))
        self.assertIn("does not promote", ready.claim_limit)

    def test_archive_is_host_consumed_and_fails_closed_for_open_or_user_state(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        request = archive_request_decision(AutomationMode.STANDARD, checkpoint, self.archive_facts())
        self.assertEqual((request.action, request.status), (AutomationAction.ARCHIVE_REQUEST, AutomationStatus.REQUESTED_UNVERIFIED))
        self.assertIn("archive_unverified", request.claim_limit)
        for changes in (
            {"task_state": "active", "accepted_completion": False},
            {"open_goal": True},
            {"open_review": True},
            {"open_dependent": True},
            {"user_pinned": True},
            {"user_renamed": True},
            {"direct_user_control": True},
            {"process_quiescent": False},
            {"handles_clear": False},
            {"logs_quiescent": False},
            {"target_state_digest": "", "host_custody_receipt_ref": ""},
        ):
            with self.subTest(changes=changes):
                decision = archive_request_decision(AutomationMode.STANDARD, checkpoint, self.archive_facts(**changes))
                self.assertEqual(decision.status, AutomationStatus.BLOCKED)
        manual = archive_request_decision(AutomationMode.MANUAL, checkpoint, self.archive_facts())
        self.assertEqual(manual.status, AutomationStatus.MANUAL)
        dirty = archive_request_decision(AutomationMode.STANDARD, self.checkpoint(), self.archive_facts())
        self.assertEqual(dirty.status, AutomationStatus.BLOCKED)


if __name__ == "__main__":
    unittest.main()
