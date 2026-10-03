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
    path_manifest_digest, release_decision, review_decision,
)
from skills.swarm.scripts.swarm_config import DEFAULTS


class AutomationContractTests(unittest.TestCase):
    now = 20
    owned_paths = ("src/app.py", "tests/test_app.py")
    release_method = "scripts/build_package.py -> codex plugin add swarm@flowwweb"

    def repository(self, *, root="C:/work/swarm", branch="main", remote="origin") -> RepositoryIdentity:
        return RepositoryIdentity("flowwweb/swarm", root, branch, remote, (self.release_method,),
                                  "https://github.com/flowwweb/swarm.git", "https://github.com/flowwweb/swarm.git", "refs/heads/main")

    def checkpoint(self, *, dirty=("src/app.py",), blocker="", repository=None) -> StableCheckpoint:
        return StableCheckpoint(
            repository=repository or self.repository(), task_id="task-1", task_state="complete",
            source_sha="a" * 40, source_tree="b" * 40, source_parent="c" * 40,
            artifact_digest="0" * 64, path_manifest_digest=path_manifest_digest(self.owned_paths),
            dependency_graph_digest="1" * 64, proof_plan_digest="2" * 64,
            review_task_id="review-task-1", owned_paths=self.owned_paths,
            dirty_paths=dirty, proof_manifest=("python -B -m unittest tests.test_app:PASS",),
            claim_limits=("source only",), blocker=blocker, next_action="route independent review",
        )

    def review(self, verdict=DelegatedReceiptVerdict.ACCEPT, *, checkpoint=None, repository=None) -> IndependentReviewReceipt:
        checkpoint = checkpoint or self.checkpoint(dirty=())
        return IndependentReviewReceipt(
            repository=repository or checkpoint.repository, visible_task_id="review-task-1",
            reviewer_id="review-owner", producer_id=checkpoint.task_id,
            candidate_sha=checkpoint.source_sha, candidate_tree=checkpoint.source_tree,
            artifact_digest=checkpoint.artifact_digest,
            path_manifest_digest=checkpoint.path_manifest_digest,
            review_packet_digest=checkpoint.review_packet().packet_digest,
            verdict=verdict, readable_receipt=f"{verdict.value}: exact candidate reviewed",
            observed_at_ms=10, expires_at_ms=30,
        )

    def fetch(self, relationship=GitRelationship.FAST_FORWARD, *, checkpoint=None, repository=None) -> FetchReceipt:
        checkpoint = checkpoint or self.checkpoint(dirty=())
        return FetchReceipt(
            repository=repository or checkpoint.repository, local_head=checkpoint.source_sha,
            candidate_tree=checkpoint.source_tree, artifact_digest=checkpoint.artifact_digest,
            path_manifest_digest=checkpoint.path_manifest_digest,
            remote_head="e" * 40, relationship=relationship, fetched_at_ms=10,
            expires_at_ms=30,
        )

    def policy(self, purpose, operation, *, authority=ReceiptAuthority.REPOSITORY_POLICY,
               checkpoint=None, repository=None, remote_head="", method="",
               subject_artifact_digest="", subject_path="", expires_at_ms=30):
        checkpoint = checkpoint or self.checkpoint(dirty=())
        return BoundPolicyReceipt(
            repository=repository or checkpoint.repository, purpose=purpose, operation=operation,
            candidate_sha=checkpoint.source_sha, candidate_tree=checkpoint.source_tree, authority=authority,
            receipt_ref=f"receipt:{purpose.value}", observed_at_ms=10,
            expires_at_ms=expires_at_ms, method=method, remote_head=remote_head,
            artifact_digest=checkpoint.artifact_digest,
            path_manifest_digest=checkpoint.path_manifest_digest,
            subject_artifact_digest=subject_artifact_digest, subject_path=subject_path,
        )

    def archive_facts(self, *, checkpoint=None, **changes) -> ArchiveFacts:
        checkpoint = checkpoint or self.checkpoint(dirty=())
        custody = HostArchiveCustodyReceipt(
            repository=checkpoint.repository, task_id="task-1",
            candidate_sha=checkpoint.source_sha, candidate_tree=checkpoint.source_tree,
            artifact_digest=checkpoint.artifact_digest,
            path_manifest_digest=checkpoint.path_manifest_digest,
            target_state_digest="f" * 64,
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
                method=self.release_method,
            ),
            source_gate=self.policy(
                ReceiptPurpose.SOURCE_GATE, AutomationAction.RELEASE,
                authority=ReceiptAuthority.INDEPENDENT_REVIEW,
                subject_artifact_digest="0" * 64, subject_path="source.zip",
            ),
            package_gate=self.policy(
                ReceiptPurpose.PACKAGE_GATE, AutomationAction.RELEASE,
                subject_artifact_digest="3" * 64, subject_path="dist/swarm.zip",
            ),
            rollback_receipt=self.policy(
                ReceiptPurpose.ROLLBACK, AutomationAction.RELEASE,
                subject_artifact_digest="4" * 64, subject_path="dist/swarm-previous.zip",
            ),
        )

    def test_raw_manual_fails_closed_for_all_five_public_decisions(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        decisions = (
            commit_decision("manual", self.checkpoint(), attributable_paths=("src/app.py",)),
            review_decision("manual", checkpoint, self.review(checkpoint=checkpoint), now_ms=self.now),
            git_advance_decision("manual", checkpoint, self.review(), self.fetch(), now_ms=self.now),
            release_decision("manual", checkpoint, now_ms=self.now, **self.release_receipts()),
            archive_request_decision("manual", checkpoint, self.archive_facts(), now_ms=self.now),
        )
        self.assertTrue(all(item.status is AutomationStatus.MANUAL for item in decisions))

    def test_standard_allows_only_exact_owned_commit(self) -> None:
        checkpoint = self.checkpoint()
        controls = dict(attributable_paths=("src/app.py",), staged_paths=("src/app.py",),
                        staged_tree=checkpoint.source_tree, now_ms=self.now,
                        guard_receipt=self.policy(ReceiptPurpose.GIT_GUARD, AutomationAction.COMMIT, checkpoint=checkpoint))
        exact = commit_decision("standard", checkpoint, **controls)
        self.assertEqual((exact.action, exact.status, exact.paths), (AutomationAction.COMMIT, AutomationStatus.READY, ("src/app.py",)))
        self.assertEqual(exact.method, "commit_exact_observed_index")
        unrelated = replace(checkpoint, dirty_paths=("src/app.py", "notes/user.txt"))
        self.assertEqual(commit_decision("standard", unrelated, **controls).status, AutomationStatus.READY)
        mixed = commit_decision(
            AutomationMode.STANDARD, unrelated,
            **{**controls, "staged_paths": ("src/app.py", "notes/user.txt")},
        )
        self.assertEqual(mixed.status, AutomationStatus.BLOCKED)
        self.assertIn("mixed", mixed.blocker)

    def test_commit_rejects_changed_index_and_missing_stale_or_wrong_guard(self) -> None:
        checkpoint = self.checkpoint()
        guard = self.policy(ReceiptPurpose.GIT_GUARD, AutomationAction.COMMIT, checkpoint=checkpoint)
        controls = dict(attributable_paths=("src/app.py",), staged_paths=("src/app.py",),
                        staged_tree=checkpoint.source_tree, now_ms=self.now, guard_receipt=guard)
        for changes in (
            {"staged_paths": None}, {"staged_paths": ()}, {"staged_tree": "d" * 40},
            {"guard_receipt": None}, {"now_ms": None},
            {"guard_receipt": replace(guard, expires_at_ms=15)},
            {"guard_receipt": replace(guard, operation=AutomationAction.PUSH)},
            {"guard_receipt": replace(guard, candidate_tree="d" * 40)},
            {"guard_receipt": replace(guard, authority=ReceiptAuthority.INDEPENDENT_REVIEW)},
            {"guard_receipt": replace(guard, repository=replace(checkpoint.repository, push_url="https://github.com/other/repo.git"))},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(commit_decision("standard", checkpoint, **{**controls, **changes}).status, AutomationStatus.BLOCKED)
        runtime = Swarm(automation_mode="standard")
        self.assertEqual(runtime.automation_commit(checkpoint, **controls).status, AutomationStatus.READY)

    def test_readable_exact_repository_review_is_required(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        self.assertEqual(review_decision("standard", checkpoint, None, now_ms=self.now).status, AutomationStatus.BLOCKED)
        for verdict in (DelegatedReceiptVerdict.REJECT, DelegatedReceiptVerdict.BLOCKED):
            with self.subTest(verdict=verdict):
                self.assertEqual(review_decision("standard", checkpoint, self.review(verdict, checkpoint=checkpoint), now_ms=self.now).status, AutomationStatus.BLOCKED)
        wrong_repo = self.review(checkpoint=checkpoint, repository=self.repository(root="D:/other/swarm"))
        self.assertIn("different repository", review_decision("standard", checkpoint, wrong_repo, now_ms=self.now).blocker)
        self.assertEqual(review_decision("standard", checkpoint, self.review(checkpoint=checkpoint), now_ms=self.now).status, AutomationStatus.READY)

    def test_review_packet_invalidates_on_tree_content_paths_graph_or_proof_plan_change(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        receipt = self.review(checkpoint=checkpoint)
        changed_paths = ("src/app.py", "tests/test_app.py", "tests/test_review.py")
        variants = (
            replace(checkpoint, source_tree="d" * 40),
            replace(checkpoint, artifact_digest="3" * 64),
            replace(checkpoint, owned_paths=changed_paths, path_manifest_digest=path_manifest_digest(changed_paths)),
            replace(checkpoint, dependency_graph_digest="4" * 64),
            replace(checkpoint, proof_plan_digest="5" * 64),
        )
        for changed in variants:
            with self.subTest(content_address=changed.content_address(), packet=changed.review_packet().packet_digest):
                decision = review_decision("standard", changed, receipt, now_ms=self.now)
                self.assertEqual(decision.status, AutomationStatus.BLOCKED)
        wrong_producer = replace(receipt, producer_id="other-task")
        self.assertIn("different producer", review_decision("standard", checkpoint, wrong_producer, now_ms=self.now).blocker)

    def test_fetch_divergence_and_push_require_bound_current_receipts(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        review = self.review(checkpoint=checkpoint)
        fetch = self.fetch(GitRelationship.DIVERGED, checkpoint=checkpoint)
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
        self.assertEqual((ready.action, ready.method), (AutomationAction.INTEGRATE, "prepare_reviewed_merge_without_commit"))
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

    def test_integration_never_reuses_pre_result_review_or_guard_for_push(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        for relationship in (GitRelationship.FAST_FORWARD, GitRelationship.DIVERGED):
            compatible = self.policy(ReceiptPurpose.REMOTE_COMPATIBILITY, AutomationAction.INTEGRATE,
                                     authority=ReceiptAuthority.INDEPENDENT_REVIEW, remote_head="e" * 40)
            decision = git_advance_decision("standard", checkpoint, self.review(), self.fetch(relationship), now_ms=self.now,
                remote_compatibility_receipt=compatible,
                push_policy_receipt=self.policy(ReceiptPurpose.PUSH_POLICY, AutomationAction.PUSH, remote_head="e" * 40),
                guard_receipt=self.policy(ReceiptPurpose.GIT_GUARD, AutomationAction.PUSH, remote_head="e" * 40))
            self.assertEqual(decision.action, AutomationAction.INTEGRATE)
        result = replace(checkpoint, source_sha="f" * 40, source_tree="9" * 40, source_parent=checkpoint.source_sha)
        fetch = self.fetch(GitRelationship.UNCHANGED, checkpoint=result)
        controls = dict(now_ms=self.now,
            push_policy_receipt=self.policy(ReceiptPurpose.PUSH_POLICY, AutomationAction.PUSH, checkpoint=result, remote_head=fetch.remote_head),
            guard_receipt=self.policy(ReceiptPurpose.GIT_GUARD, AutomationAction.PUSH, checkpoint=result, remote_head=fetch.remote_head))
        self.assertEqual(git_advance_decision("standard", result, self.review(), fetch, **controls).status, AutomationStatus.BLOCKED)
        self.assertEqual(git_advance_decision("standard", result, self.review(checkpoint=result), fetch, **controls).action, AutomationAction.PUSH)
        runtime = Swarm(automation_mode="standard")
        self.assertEqual(runtime.automation_git_advance(result, self.review(checkpoint=result), fetch, **controls).status, AutomationStatus.READY)

    def test_local_ahead_guarded_push_needs_no_integration(self) -> None:
        checkpoint = replace(self.checkpoint(dirty=()), source_parent="e" * 40)
        fetch = self.fetch(GitRelationship.UNCHANGED, checkpoint=checkpoint)
        self.assertEqual(checkpoint.source_parent, fetch.remote_head)
        self.assertNotEqual(checkpoint.source_sha, fetch.remote_head)
        decision = git_advance_decision("standard", checkpoint, self.review(checkpoint=checkpoint), fetch,
            now_ms=self.now,
            push_policy_receipt=self.policy(ReceiptPurpose.PUSH_POLICY, AutomationAction.PUSH, checkpoint=checkpoint, remote_head=fetch.remote_head),
            guard_receipt=self.policy(ReceiptPurpose.GIT_GUARD, AutomationAction.PUSH, checkpoint=checkpoint, remote_head=fetch.remote_head))
        self.assertEqual((decision.status, decision.action, decision.method),
                         (AutomationStatus.READY, AutomationAction.PUSH, "push_exact_reviewed_candidate"))

    def test_push_requires_current_guard_and_resolved_remote_destination(self) -> None:
        checkpoint = self.checkpoint(dirty=())
        review = self.review()
        fetch = self.fetch(GitRelationship.UNCHANGED)
        guard = self.policy(ReceiptPurpose.GIT_GUARD, AutomationAction.PUSH, remote_head=fetch.remote_head)
        controls = dict(now_ms=self.now, guard_receipt=guard,
            push_policy_receipt=self.policy(ReceiptPurpose.PUSH_POLICY, AutomationAction.PUSH, remote_head=fetch.remote_head))
        for bad_guard in (None, replace(guard, expires_at_ms=15), replace(guard, operation=AutomationAction.COMMIT),
                          replace(guard, remote_head="f" * 40), replace(guard, candidate_tree="f" * 40)):
            self.assertEqual(git_advance_decision("standard", checkpoint, review, fetch, **{**controls, "guard_receipt": bad_guard}).status, AutomationStatus.BLOCKED)
        for target in (replace(checkpoint.repository, fetch_url="https://github.com/other/repo.git"),
                       replace(checkpoint.repository, push_url="https://github.com/other/repo.git"),
                       replace(checkpoint.repository, target_ref="refs/heads/unreviewed")):
            changed = replace(checkpoint, repository=target)
            self.assertEqual(git_advance_decision("standard", changed, review, fetch, **controls).status, AutomationStatus.BLOCKED)
        unknown = replace(checkpoint, repository=replace(checkpoint.repository, push_url=""))
        self.assertIn("resolved", git_advance_decision("standard", unknown, self.review(checkpoint=unknown), self.fetch(checkpoint=unknown), now_ms=self.now).blocker)

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
        self.assertEqual(manual.automation_review(checkpoint, self.review(checkpoint=checkpoint), now_ms=self.now).status, AutomationStatus.MANUAL)
        self.assertEqual(manual.automation_git_advance(checkpoint, self.review(checkpoint=checkpoint), self.fetch(checkpoint=checkpoint), now_ms=self.now).status, AutomationStatus.MANUAL)
        self.assertEqual(manual.automation_release(checkpoint, now_ms=self.now, **self.release_receipts()).status, AutomationStatus.MANUAL)
        self.assertEqual(manual.automation_archive_request(checkpoint, self.archive_facts(), now_ms=self.now).status, AutomationStatus.MANUAL)
        standard = Swarm(automation_mode="standard")
        self.assertEqual(standard.automation_review(checkpoint, self.review(checkpoint=checkpoint), now_ms=self.now).status, AutomationStatus.READY)
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
