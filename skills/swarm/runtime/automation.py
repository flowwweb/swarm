"""Fail-closed lifecycle automation decisions for SWARM-owned work.

This module plans bounded source and host requests.  It never runs Git, mutates
host tasks, packages a plugin, or claims that a host consumed a request.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
import re

from .core import DelegatedReceiptVerdict, InvariantError


_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class AutomationMode(StrEnum):
    STANDARD = "standard"
    MANUAL = "manual"


class AutomationAction(StrEnum):
    NONE = "none"
    COMMIT = "commit"
    REVIEW = "review"
    INTEGRATE = "integrate"
    PUSH = "push"
    RELEASE = "release"
    ARCHIVE_REQUEST = "archive_request"


class AutomationStatus(StrEnum):
    READY = "ready"
    MANUAL = "manual"
    BLOCKED = "blocked"
    REQUESTED_UNVERIFIED = "requested_unverified"


class GitRelationship(StrEnum):
    UNCHANGED = "unchanged"
    FAST_FORWARD = "fast_forward"
    DIVERGED = "diverged"


def _token(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(char in value for char in "\r\n\t"):
        raise InvariantError(f"{label} must be exact non-empty text")
    return value


def _git_object(value: str, label: str) -> str:
    if not isinstance(value, str) or not _GIT_OBJECT.fullmatch(value):
        raise InvariantError(f"{label} must be a full lowercase Git object id")
    return value


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise InvariantError(f"{label} must be a full lowercase SHA-256 digest")
    return value


def _paths(values: tuple[str, ...], label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, tuple) or (not values and not allow_empty):
        raise InvariantError(f"{label} must be a {'possibly empty ' if allow_empty else ''}tuple of repository-relative paths")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or "\\" in value:
            raise InvariantError(f"{label} must use repository-relative POSIX paths")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise InvariantError(f"{label} must use repository-relative POSIX paths")
        normalized.append(path.as_posix())
    if len(normalized) != len(set(normalized)):
        raise InvariantError(f"{label} cannot contain duplicates")
    return tuple(normalized)


@dataclass(frozen=True)
class StableCheckpoint:
    task_id: str
    task_state: str
    source_sha: str
    source_tree: str
    source_parent: str
    owned_paths: tuple[str, ...]
    dirty_paths: tuple[str, ...]
    proof_manifest: tuple[str, ...]
    claim_limits: tuple[str, ...]
    blocker: str
    next_action: str

    def __post_init__(self) -> None:
        _token(self.task_id, "checkpoint task id")
        _token(self.task_state, "checkpoint task state")
        _git_object(self.source_sha, "checkpoint source SHA")
        _git_object(self.source_tree, "checkpoint source tree")
        _git_object(self.source_parent, "checkpoint source parent")
        object.__setattr__(self, "owned_paths", _paths(self.owned_paths, "checkpoint owned paths"))
        object.__setattr__(self, "dirty_paths", _paths(self.dirty_paths, "checkpoint dirty paths", allow_empty=True))
        if not self.proof_manifest or not all(isinstance(value, str) and value.strip() for value in self.proof_manifest):
            raise InvariantError("checkpoint requires a readable proof manifest")
        if not self.claim_limits or not all(isinstance(value, str) and value.strip() for value in self.claim_limits):
            raise InvariantError("checkpoint requires explicit claim limits")
        if not isinstance(self.blocker, str):
            raise InvariantError("checkpoint blocker must be text, including empty when clear")
        _token(self.next_action, "checkpoint next action")


@dataclass(frozen=True)
class IndependentReviewReceipt:
    visible_task_id: str
    reviewer_id: str
    producer_id: str
    candidate_sha: str
    candidate_tree: str
    artifact_digest: str
    verdict: DelegatedReceiptVerdict
    readable_receipt: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.visible_task_id, "visible review task id"),
            (self.reviewer_id, "reviewer id"),
            (self.producer_id, "producer id"),
            (self.readable_receipt, "readable review receipt"),
        ):
            _token(value, label)
        if self.reviewer_id == self.producer_id:
            raise InvariantError("independent review requires a separate owner from the producer")
        _git_object(self.candidate_sha, "review candidate SHA")
        _git_object(self.candidate_tree, "review candidate tree")
        _digest(self.artifact_digest, "review artifact digest")
        if not isinstance(self.verdict, DelegatedReceiptVerdict):
            raise InvariantError("review verdict must be ACCEPT, REJECT, or BLOCKED")


@dataclass(frozen=True)
class FetchReceipt:
    branch: str
    local_head: str
    remote_head: str
    relationship: GitRelationship
    fetched_at_ms: int
    compatible_remote_review_receipt: str = ""

    def __post_init__(self) -> None:
        _token(self.branch, "fetch branch")
        _git_object(self.local_head, "fetch local head")
        _git_object(self.remote_head, "fetch remote head")
        if not isinstance(self.relationship, GitRelationship):
            raise InvariantError("fetch relationship must be typed")
        if not isinstance(self.fetched_at_ms, int) or self.fetched_at_ms < 0:
            raise InvariantError("fetch receipt requires a non-negative observation time")
        if not isinstance(self.compatible_remote_review_receipt, str):
            raise InvariantError("compatible remote review receipt must be text")


@dataclass(frozen=True)
class ArchiveFacts:
    task_id: str
    task_state: str
    accepted_completion: bool
    open_goal: bool = False
    open_request: bool = False
    open_handoff: bool = False
    open_review: bool = False
    open_correction: bool = False
    open_user_choice: bool = False
    open_dependent: bool = False
    user_renamed: bool = False
    user_pinned: bool = False
    direct_user_control: bool = False
    process_quiescent: bool = False
    handles_clear: bool = False
    logs_quiescent: bool = False
    target_state_digest: str = ""
    host_custody_receipt_ref: str = ""

    def __post_init__(self) -> None:
        _token(self.task_id, "archive target task id")
        _token(self.task_state, "archive target task state")
        values = self.__dict__
        for key, value in values.items():
            if key not in {"task_id", "task_state", "target_state_digest", "host_custody_receipt_ref"} and not isinstance(value, bool):
                raise InvariantError(f"archive fact {key} must be true or false")
        if self.target_state_digest:
            _digest(self.target_state_digest, "archive target state")
        if not isinstance(self.host_custody_receipt_ref, str):
            raise InvariantError("archive custody receipt reference must be text")
        if self.host_custody_receipt_ref:
            _token(self.host_custody_receipt_ref, "archive custody receipt reference")


@dataclass(frozen=True)
class AutomationDecision:
    action: AutomationAction
    status: AutomationStatus
    paths: tuple[str, ...] = ()
    method: str = ""
    blocker: str = ""
    target_id: str = ""
    target_state_digest: str = ""
    host_custody_receipt_ref: str = ""
    claim_limit: str = ""

    @property
    def eligible(self) -> bool:
        return self.status in {AutomationStatus.READY, AutomationStatus.REQUESTED_UNVERIFIED}


def _manual() -> AutomationDecision:
    return AutomationDecision(
        AutomationAction.NONE,
        AutomationStatus.MANUAL,
        blocker="automation.mode is manual",
        claim_limit="No Git, release, or host lifecycle action is requested in manual mode.",
    )


def commit_decision(
    mode: AutomationMode, checkpoint: StableCheckpoint, *, attributable_paths: tuple[str, ...]
) -> AutomationDecision:
    """Allow an exact owned commit only when the whole dirty set is attributable."""
    if mode is AutomationMode.MANUAL:
        return _manual()
    paths = _paths(attributable_paths, "attributable paths")
    owned, dirty, attributable = set(checkpoint.owned_paths), set(checkpoint.dirty_paths), set(paths)
    if checkpoint.blocker:
        return AutomationDecision(AutomationAction.COMMIT, AutomationStatus.BLOCKED, blocker=checkpoint.blocker)
    if dirty != attributable or not attributable.issubset(owned):
        return AutomationDecision(
            AutomationAction.COMMIT,
            AutomationStatus.BLOCKED,
            blocker="mixed or unattributable dirty paths",
            claim_limit="Automation never stages, resets, cleans, or absorbs paths outside the exact owned checkpoint.",
        )
    return AutomationDecision(
        AutomationAction.COMMIT,
        AutomationStatus.READY,
        paths=tuple(sorted(attributable)),
        method="stage_exact_paths_then_commit",
        claim_limit="Eligibility is a source decision; the Git command and resulting immutable receipt remain separately observable.",
    )


def review_decision(
    mode: AutomationMode,
    checkpoint: StableCheckpoint,
    receipt: IndependentReviewReceipt | None,
) -> AutomationDecision:
    """Require one readable exact-candidate independent verdict before integration."""
    if mode is AutomationMode.MANUAL:
        return _manual()
    if receipt is None:
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="independent review receipt required")
    if (receipt.candidate_sha, receipt.candidate_tree) != (checkpoint.source_sha, checkpoint.source_tree):
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="review receipt targets a different candidate")
    if receipt.verdict is not DelegatedReceiptVerdict.ACCEPT:
        return AutomationDecision(
            AutomationAction.REVIEW,
            AutomationStatus.BLOCKED,
            blocker=f"independent review returned {receipt.verdict.value}",
            claim_limit="REJECT, BLOCKED, silence, activity, timeout, and in-progress state never advance acceptance.",
        )
    return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.READY, method="readable_independent_accept")


def git_advance_decision(
    mode: AutomationMode,
    checkpoint: StableCheckpoint,
    review: IndependentReviewReceipt | None,
    fetch: FetchReceipt | None,
    *,
    push_policy_receipt: str = "",
) -> AutomationDecision:
    """Plan a history-preserving integrate/push action after review and fetch."""
    accepted = review_decision(mode, checkpoint, review)
    if accepted.status is not AutomationStatus.READY:
        return accepted
    if fetch is None:
        return AutomationDecision(AutomationAction.INTEGRATE, AutomationStatus.BLOCKED, blocker="fresh fetch receipt required before integration or push")
    if fetch.local_head != checkpoint.source_sha:
        return AutomationDecision(AutomationAction.INTEGRATE, AutomationStatus.BLOCKED, blocker="fetch receipt is not bound to the accepted local candidate")
    if fetch.relationship is GitRelationship.DIVERGED and not fetch.compatible_remote_review_receipt.strip():
        return AutomationDecision(
            AutomationAction.INTEGRATE,
            AutomationStatus.BLOCKED,
            blocker="remote history diverged and lacks a reviewed compatibility receipt",
            claim_limit="Never force-push, rebase, or reset user or remote work.",
        )
    method = "merge_reviewed_remote_history" if fetch.relationship is GitRelationship.DIVERGED else "fast_forward_preserving_history"
    if not isinstance(push_policy_receipt, str):
        raise InvariantError("push policy receipt must be text")
    action = AutomationAction.PUSH if push_policy_receipt.strip() else AutomationAction.INTEGRATE
    return AutomationDecision(
        action,
        AutomationStatus.READY,
        method=method,
        claim_limit="Only non-destructive fast-forward or reviewed compatible merge is eligible; force-push, rebase, and reset are never emitted.",
    )


def release_decision(
    mode: AutomationMode,
    *,
    repository_release_path: str,
    source_gate_passed: bool,
    package_gate_passed: bool,
    rollback_receipt: str,
) -> AutomationDecision:
    """Permit only the repository-defined release path with source/package gates."""
    if mode is AutomationMode.MANUAL:
        return _manual()
    if not all((repository_release_path.strip(), source_gate_passed, package_gate_passed, rollback_receipt.strip())):
        return AutomationDecision(AutomationAction.RELEASE, AutomationStatus.BLOCKED, blocker="repository release path, source/package gates, and rollback receipt are required")
    return AutomationDecision(
        AutomationAction.RELEASE,
        AutomationStatus.READY,
        method=repository_release_path,
        claim_limit="Release eligibility does not promote local installation to provider or production deployment.",
    )


def archive_request_decision(
    mode: AutomationMode, checkpoint: StableCheckpoint, facts: ArchiveFacts
) -> AutomationDecision:
    """Emit a host-consumed request; never archive or claim host authority here."""
    if mode is AutomationMode.MANUAL:
        return _manual()
    if facts.task_id != checkpoint.task_id:
        return AutomationDecision(AutomationAction.ARCHIVE_REQUEST, AutomationStatus.BLOCKED, blocker="archive target does not match the checkpoint")
    if checkpoint.dirty_paths:
        return AutomationDecision(AutomationAction.ARCHIVE_REQUEST, AutomationStatus.BLOCKED, blocker="archive requires a clean immutable checkpoint with exact dirty custody")
    if facts.task_state.casefold() not in {"complete", "completed", "accepted"} or not facts.accepted_completion:
        return AutomationDecision(AutomationAction.ARCHIVE_REQUEST, AutomationStatus.BLOCKED, blocker="task is active, stalled, blocked, or not accepted")
    open_gates = tuple(
        name
        for name in ("goal", "request", "handoff", "review", "correction", "user_choice", "dependent")
        if getattr(facts, f"open_{name}")
    )
    if open_gates:
        return AutomationDecision(AutomationAction.ARCHIVE_REQUEST, AutomationStatus.BLOCKED, blocker=f"open task gate(s): {','.join(open_gates)}")
    if facts.user_renamed or facts.user_pinned or facts.direct_user_control:
        return AutomationDecision(AutomationAction.ARCHIVE_REQUEST, AutomationStatus.BLOCKED, blocker="user custody keeps the task visible")
    if not all((facts.process_quiescent, facts.handles_clear, facts.logs_quiescent)):
        return AutomationDecision(AutomationAction.ARCHIVE_REQUEST, AutomationStatus.BLOCKED, blocker="task process, handle, or log state is not quiescent")
    if not facts.target_state_digest or not facts.host_custody_receipt_ref.strip():
        return AutomationDecision(
            AutomationAction.ARCHIVE_REQUEST,
            AutomationStatus.BLOCKED,
            blocker="current host target/custody receipt is unavailable",
            claim_limit="archive_unverified: plugin runtime cannot mint host authority.",
        )
    return AutomationDecision(
        AutomationAction.ARCHIVE_REQUEST,
        AutomationStatus.REQUESTED_UNVERIFIED,
        target_id=facts.task_id,
        target_state_digest=facts.target_state_digest,
        host_custody_receipt_ref=facts.host_custody_receipt_ref,
        method="host_consume_archive_request",
        claim_limit="archive_unverified: only the host may independently validate current custody, consume the persisted preference, archive the exact task, and return confirmation.",
    )
