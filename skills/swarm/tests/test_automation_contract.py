from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import unittest

from skills.swarm.runtime import (
    ArchiveFacts, AutomationAction, AutomationMode, AutomationStatus,
    BoundPolicyReceipt, DelegatedReceiptVerdict, FetchReceipt, GitRelationship,
    HostArchiveCustodyReceipt, IndependentReviewReceipt, ReceiptAuthority,
    ReceiptPurpose, RepositoryIdentity, StableCheckpoint, Swarm,
    archive_request_decision, commit_decision, git_advance_decision,
    release_decision, review_decision,
)
from skills.swarm.scripts.swarm_config import DEFAULTS


class AutomationContractTests(unittest.TestCase):
    now = 20

    def repository(self, *, root="C:/work/swarm", branch="main", remote="origin") -> RepositoryIdentity:
        return RepositoryIdentity("flowwweb/swarm", root, branch, remote)

    def checkpoint(self, *, dirty=("src/app.py",), blocker="", repository=None) -> StableCheckpoint:
        return StableCheckpoint(
            repository=repository or self.repository(), task_id="task-1", task_state="complete",
            source_sha="a" * 40, source_tree="b" * 40, source_parent="c" * 40,
            artifact_digest="0" * 64, owned_paths=("src/app.py", "tests/test_app.py"),
            dirty_paths=dirty, proof_manifest=("python -B -m unittest tests.test_app:PASS",),
            claim_limits=("source only",), blocker=blocker, next_action="route independent review",
        )

    def review(self, verdict=DelegatedReceiptVerdict.ACCEPT, *, repository=None) -> IndependentReviewReceipt:
        return IndependentReviewReceipt(
            repository=repository or self.repository(), visible_task_id="review-task-1",
            reviewer_id="review-owner", producer_id="implementation-owner",
            candidate_sha="a" * 40, candidate_tree="b" * 40, artifact_digest="0" * 64,
            verdict=verdict, readable_receipt=f"{verdict.value}: exact candidate reviewed",
        )

    def fetch(self, relationship=GitRelationship.FAST_FORWARD, *, repository=None) -> FetchReceipt:
        return FetchReceipt(
            repository=repository or self.repository(), local_head="a" * 40,
            remote_head="e" * 40, relationship=relationship, fetched_at_ms=10,
            expires_at_ms=30,
        )

    def policy(self, purpose, operation, *, authority=ReceiptAuthority.REPOSITORY_POLICY,
               repository=None, remote_head="", method="", artifact_digest="", expires_at_ms=30):
        return BoundPolicyReceipt(
            repository=repository or self.repository(), purpose=purpose, operation=operation,
            candidate_sha="a" * 40, candidate_tree="b" * 40, authority=authority,
            receipt_ref=f"receipt:{purpose.value}", observed_at_ms=10,
            expires_at_ms=expires_at_ms, method=method, remote_head=remote_head,
            artifact_digest=artifact_digest,
        )

    def archive_facts(self, **changes) -> ArchiveFacts:
        custody = HostArchiveCustodyReceipt(
            task_id="task-1", target_state_digest="f" * 64,
            receipt_ref="host-custody-current-1", authority=ReceiptAuthority.HOST,
            observed_at_ms=10, expires_at_ms=30,
        )
        values = dict(
            task_id="task-1", task_state="complete", accepted_completion=True,
            process_quiescent=True, handles_clear=True, logs_quiescent=True,
            target_state_digest="f" * 64, host_custody_receipt=custody,
        )
        values.update(changes)
        return ArchiveFacts(**values)

    def release_receipts(self):
        return dict(
            release_policy=self.policy(
                ReceiptPurpose.RELEASE_POLICY, AutomationAction.RELEASE,
                method="scripts/build_package.py -> codex plugin add swarm@flowwweb",
            ),
            source_gate=self.policy(
                ReceiptPurpose.SOURCE_GATE, AutomationAction.RELEASE,
                authority=ReceiptAuthority.INDEPENDENT_REVIEW, artifact_digest="0" * 64,
            ),
            package_gate=self.policy(
                ReceiptPurpose.PACKAGE_GATE, AutomationAction.RELEASE, artifact_digest="2" * 64,
            ),
            rollback_receipt=self.policy(
                ReceiptPurpose.ROLLBACK, AutomationAction.RELEASE, artifact_digest="3" * 64,
            ),
        )

    def test_raw_manual_fails_closed_for_all_five_public_decisions(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        decisions = (
            commit_decision("manual", self.checkpoint(), attributable_paths=("src/app.py",)),
            review_decision("manual", checkpoint, self.review()),
            git_advance_decision("manual", checkpoint, self.review(), self.fetch(), now_ms=self.now),
            release_decision("manual", checkpoint, now_ms=self.now, **self.release_receipts()),
            archive_request_decision("manual", checkpoint, self.archive_facts(), now_ms=self.now),
        )
        self.assertTrue(all(item.status is AutomationStatus.MANUAL for item in decisions))

    def test_standard_allows_only_exact_owned_commit(self) -> None:
        exact = commit_decision("standard", self.checkpoint(), attributable_paths=("src/app.py",))
        self.assertEqual((exact.action, exact.status, exact.paths), (AutomationAction.COMMIT, AutomationStatus.READY, ("src/app.py",)))
        mixed = commit_decision(
            AutomationMode.STANDARD, self.checkpoint(dirty=("src/app.py", "notes/user.txt")),
            attributable_paths=("src/app.py",),
        )
        self.assertEqual(mixed.status, AutomationStatus.BLOCKED)
        self.assertIn("mixed", mixed.blocker)

    def test_readable_exact_repository_review_is_required(self) -> None:
        checkpoint = self.checkpoint()
        self.assertEqual(review_decision("standard", checkpoint, None).status, AutomationStatus.BLOCKED)
        for verdict in (DelegatedReceiptVerdict.REJECT, DelegatedReceiptVerdict.BLOCKED):
            with self.subTest(verdict=verdict):
                self.assertEqual(review_decision("standard", checkpoint, self.review(verdict)).status, AutomationStatus.BLOCKED)
        wrong_repo = self.review(repository=self.repository(root="D:/other/swarm"))
        self.assertIn("different repository", review_decision("standard", checkpoint, wrong_repo).blocker)
        self.assertEqual(review_decision("standard", checkpoint, self.review()).status, AutomationStatus.READY)

    def test_fetch_divergence_and_push_require_bound_current_receipts(self) -> None:
        checkpoint, review, fetch = self.checkpoint(), self.review(), self.fetch(GitRelationship.DIVERGED)
        self.assertEqual(git_advance_decision("standard", checkpoint, review, fetch, now_ms=self.now).status, AutomationStatus.BLOCKED)
        compatible = self.policy(
            ReceiptPurpose.REMOTE_COMPATIBILITY, AutomationAction.INTEGRATE,
            authority=ReceiptAuthority.INDEPENDENT_REVIEW, remote_head="e" * 40,
        )
        push = self.policy(ReceiptPurpose.PUSH_POLICY, AutomationAction.PUSH, remote_head="e" * 40)
        ready = git_advance_decision(
            "standard", checkpoint, review, fetch, now_ms=self.now,
            remote_compatibility_receipt=compatible, push_policy_receipt=push,
        )
        self.assertEqual((ready.action, ready.method), (AutomationAction.PUSH, "merge_reviewed_remote_history"))
        wrong_root = replace(push, repository=self.repository(root="D:/other/swarm"))
        self.assertIn("different repository", git_advance_decision(
            "standard", checkpoint, review, self.fetch(), now_ms=self.now,
            push_policy_receipt=wrong_root,
        ).blocker)
        stale = replace(push, expires_at_ms=15)
        self.assertIn("stale", git_advance_decision(
            "standard", checkpoint, review, self.fetch(), now_ms=self.now,
            push_policy_receipt=stale,
        ).blocker)
        stale_fetch = replace(self.fetch(), expires_at_ms=15)
        self.assertIn("stale", git_advance_decision(
            "standard", checkpoint, review, stale_fetch, now_ms=self.now,
        ).blocker)
        self.assertIn("never", ready.claim_limit.casefold())

    def test_release_requires_bound_policy_gates_and_rollback(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        missing = self.release_receipts(); missing["package_gate"] = None
        self.assertEqual(release_decision("standard", checkpoint, now_ms=self.now, **missing).status, AutomationStatus.BLOCKED)
        receipts = self.release_receipts()
        ready = release_decision("standard", checkpoint, now_ms=self.now, **receipts)
        self.assertEqual((ready.action, ready.status), (AutomationAction.RELEASE, AutomationStatus.READY))
        wrong_artifact = dict(receipts)
        wrong_artifact["source_gate"] = replace(receipts["source_gate"], artifact_digest="4" * 64)
        self.assertIn("different artifact", release_decision(
            "standard", checkpoint, now_ms=self.now, **wrong_artifact,
        ).blocker)
        receipts["release_policy"] = replace(
            receipts["release_policy"], repository=self.repository(branch="release/unreviewed"),
        )
        self.assertIn("different repository", release_decision("standard", checkpoint, now_ms=self.now, **receipts).blocker)

    def test_archive_is_host_consumed_and_fails_closed_for_open_or_user_state(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        request = archive_request_decision("standard", checkpoint, self.archive_facts(), now_ms=self.now)
        self.assertEqual((request.action, request.status), (AutomationAction.ARCHIVE_REQUEST, AutomationStatus.REQUESTED_UNVERIFIED))
        self.assertIn("archive_unverified", request.claim_limit)
        for changes in (
            {"task_state": "active", "accepted_completion": False}, {"open_goal": True},
            {"open_review": True}, {"open_dependent": True}, {"user_pinned": True},
            {"user_renamed": True}, {"direct_user_control": True},
            {"process_quiescent": False}, {"handles_clear": False},
            {"logs_quiescent": False}, {"target_state_digest": "", "host_custody_receipt": None},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(archive_request_decision(
                    "standard", checkpoint, self.archive_facts(**changes), now_ms=self.now,
                ).status, AutomationStatus.BLOCKED)
        stale = replace(self.archive_facts().host_custody_receipt, expires_at_ms=15)
        self.assertIn("stale", archive_request_decision(
            "standard", checkpoint, self.archive_facts(host_custody_receipt=stale), now_ms=self.now,
        ).blocker)

    def test_swarm_runtime_routes_actions_through_fail_closed_decisions(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        manual = Swarm(automation_mode="manual")
        self.assertEqual(manual.automation_commit(self.checkpoint(), attributable_paths=("src/app.py",)).status, AutomationStatus.MANUAL)
        self.assertEqual(manual.automation_review(checkpoint, self.review()).status, AutomationStatus.MANUAL)
        self.assertEqual(manual.automation_git_advance(checkpoint, self.review(), self.fetch(), now_ms=self.now).status, AutomationStatus.MANUAL)
        self.assertEqual(manual.automation_release(checkpoint, now_ms=self.now, **self.release_receipts()).status, AutomationStatus.MANUAL)
        self.assertEqual(manual.automation_archive_request(checkpoint, self.archive_facts(), now_ms=self.now).status, AutomationStatus.MANUAL)
        standard = Swarm(automation_mode="standard")
        self.assertEqual(standard.automation_review(checkpoint, self.review()).status, AutomationStatus.READY)
        self.assertEqual(standard.automation_archive_request(checkpoint, self.archive_facts(), now_ms=self.now).status, AutomationStatus.REQUESTED_UNVERIFIED)

    def test_swarm_from_config_preserves_manual_runtime_mode(self) -> None:
        config = deepcopy(DEFAULTS)
        config["automation"]["mode"] = "manual"
        runtime = Swarm.from_config(config)
        self.assertEqual(runtime.automation_mode, "manual")
        self.assertEqual(
            runtime.automation_commit(self.checkpoint(), attributable_paths=("src/app.py",)).status,
            AutomationStatus.MANUAL,
        )


if __name__ == "__main__":
    unittest.main()
