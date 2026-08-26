"""Fail-closed lifecycle automation decisions for SWARM-owned work.

This module plans bounded source and host requests.  It never runs Git, mutates
host tasks, packages a plugin, or claims that a host consumed a request.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import PurePosixPath, PureWindowsPath
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


class ReceiptAuthority(StrEnum):
    HOST = "host"
    REPOSITORY_POLICY = "repository_policy"
    INDEPENDENT_REVIEW = "independent_review"


class ReceiptPurpose(StrEnum):
    REMOTE_COMPATIBILITY = "remote_compatibility"
    PUSH_POLICY = "push_policy"
    RELEASE_POLICY = "release_policy"
    SOURCE_GATE = "source_gate"
    PACKAGE_GATE = "package_gate"
    ROLLBACK = "rollback"


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


def path_manifest_digest(paths: tuple[str, ...]) -> str:
    """Return the canonical digest used to bind proof and review to exact paths."""
    normalized = _paths(paths, "path manifest")
    payload = json.dumps(normalized, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def normalize_automation_mode(mode: AutomationMode | str) -> AutomationMode:
    """Normalize config/runtime input before any identity comparison."""
    if isinstance(mode, AutomationMode):
        return mode
    if isinstance(mode, str):
        try:
            return AutomationMode(mode.strip().casefold())
        except ValueError:
            pass
    raise InvariantError("automation mode must be standard or manual")


@dataclass(frozen=True)
class RepositoryIdentity:
    repository_id: str
    root: str
    branch: str
    remote: str
    release_methods: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _token(self.repository_id, "repository id")
        _token(self.root, "repository root")
        if not (PureWindowsPath(self.root).is_absolute() or PurePosixPath(self.root).is_absolute()):
            raise InvariantError("repository root must be absolute")
        _token(self.branch, "repository branch")
        _token(self.remote, "repository remote")
        if not isinstance(self.release_methods, tuple) or not all(isinstance(item, str) and item.strip() for item in self.release_methods):
            raise InvariantError("repository release methods must be a tuple of exact non-empty methods")
        if len(self.release_methods) != len(set(self.release_methods)):
            raise InvariantError("repository release methods cannot contain duplicates")


@dataclass(frozen=True)
class StableCheckpoint:
    repository: RepositoryIdentity
    task_id: str
    task_state: str
    source_sha: str
    source_tree: str
    source_parent: str
    artifact_digest: str
    path_manifest_digest: str
    dependency_graph_digest: str
    proof_plan_digest: str
    review_task_id: str
    owned_paths: tuple[str, ...]
    dirty_paths: tuple[str, ...]
    proof_manifest: tuple[str, ...]
    claim_limits: tuple[str, ...]
    blocker: str
    next_action: str

    def __post_init__(self) -> None:
        if not isinstance(self.repository, RepositoryIdentity):
            raise InvariantError("checkpoint requires a typed repository identity")
        _token(self.task_id, "checkpoint task id")
        _token(self.task_state, "checkpoint task state")
        _git_object(self.source_sha, "checkpoint source SHA")
        _git_object(self.source_tree, "checkpoint source tree")
        _git_object(self.source_parent, "checkpoint source parent")
        _digest(self.artifact_digest, "checkpoint artifact digest")
        _digest(self.path_manifest_digest, "checkpoint path manifest digest")
        _digest(self.dependency_graph_digest, "checkpoint dependency graph digest")
        _digest(self.proof_plan_digest, "checkpoint proof plan digest")
        _token(self.review_task_id, "checkpoint review task id")
        object.__setattr__(self, "owned_paths", _paths(self.owned_paths, "checkpoint owned paths"))
        object.__setattr__(self, "dirty_paths", _paths(self.dirty_paths, "checkpoint dirty paths", allow_empty=True))
        if self.path_manifest_digest != path_manifest_digest(self.owned_paths):
            raise InvariantError("checkpoint path manifest digest must match the exact owned paths")
        if not self.proof_manifest or not all(isinstance(value, str) and value.strip() for value in self.proof_manifest):
            raise InvariantError("checkpoint requires a readable proof manifest")
        if not self.claim_limits or not all(isinstance(value, str) and value.strip() for value in self.claim_limits):
            raise InvariantError("checkpoint requires explicit claim limits")
        if not isinstance(self.blocker, str):
            raise InvariantError("checkpoint blocker must be text, including empty when clear")
        _token(self.next_action, "checkpoint next action")

    def content_address(self) -> str:
        """Bind the candidate to its exact Git tree, content, and path manifest."""
        return _canonical_digest(
            {
                "repository": self.repository.repository_id,
                "tree": self.source_tree,
                "artifact": self.artifact_digest,
                "paths": self.path_manifest_digest,
            }
        )

    def review_packet(self) -> "ImmutableReviewPacket":
        return ImmutableReviewPacket.from_checkpoint(self)


@dataclass(frozen=True)
class ImmutableReviewPacket:
    """One deterministic, portable packet for an exact independent review."""

    repository: RepositoryIdentity
    producer_task_id: str
    reviewer_task_id: str
    candidate_sha: str
    candidate_tree: str
    candidate_parent: str
    content_address: str
    artifact_digest: str
    path_manifest_digest: str
    dependency_graph_digest: str
    proof_plan_digest: str
    owned_paths: tuple[str, ...]
    proof_manifest: tuple[str, ...]
    claim_limits: tuple[str, ...]
    schema_version: int = 1
    packet_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.repository, RepositoryIdentity):
            raise InvariantError("review packet requires a typed repository identity")
        if self.schema_version != 1:
            raise InvariantError("review packet schema version must be 1")
        _token(self.producer_task_id, "review packet producer task id")
        _token(self.reviewer_task_id, "review packet reviewer task id")
        for value, label in (
            (self.candidate_sha, "review packet candidate SHA"),
            (self.candidate_tree, "review packet candidate tree"),
            (self.candidate_parent, "review packet candidate parent"),
        ):
            _git_object(value, label)
        for value, label in (
            (self.content_address, "review packet content address"),
            (self.artifact_digest, "review packet artifact digest"),
            (self.path_manifest_digest, "review packet path manifest digest"),
            (self.dependency_graph_digest, "review packet dependency graph digest"),
            (self.proof_plan_digest, "review packet proof plan digest"),
        ):
            _digest(value, label)
        object.__setattr__(self, "owned_paths", _paths(self.owned_paths, "review packet owned paths"))
        if self.path_manifest_digest != path_manifest_digest(self.owned_paths):
            raise InvariantError("review packet path manifest digest must match the exact owned paths")
        if not self.proof_manifest or not all(isinstance(value, str) and value.strip() for value in self.proof_manifest):
            raise InvariantError("review packet requires a readable proof manifest")
        if not self.claim_limits or not all(isinstance(value, str) and value.strip() for value in self.claim_limits):
            raise InvariantError("review packet requires explicit claim limits")
        payload = {
            "schema": self.schema_version,
            "repository": (
                self.repository.repository_id,
                self.repository.root,
                self.repository.branch,
                self.repository.remote,
                self.repository.release_methods,
            ),
            "producer": self.producer_task_id,
            "reviewer": self.reviewer_task_id,
            "candidate": (self.candidate_sha, self.candidate_tree, self.candidate_parent),
            "content_address": self.content_address,
            "artifact": self.artifact_digest,
            "path_manifest": self.path_manifest_digest,
            "dependency_graph": self.dependency_graph_digest,
            "proof_plan": self.proof_plan_digest,
            "owned_paths": self.owned_paths,
            "proof_manifest": self.proof_manifest,
            "claim_limits": self.claim_limits,
        }
        object.__setattr__(self, "packet_digest", _canonical_digest(payload))

    @classmethod
    def from_checkpoint(cls, checkpoint: StableCheckpoint) -> "ImmutableReviewPacket":
        if not isinstance(checkpoint, StableCheckpoint):
            raise InvariantError("review packet requires a typed stable checkpoint")
        if checkpoint.dirty_paths or checkpoint.blocker:
            raise InvariantError("review packet requires a clean unblocked immutable checkpoint")
        return cls(
            repository=checkpoint.repository,
            producer_task_id=checkpoint.task_id,
            reviewer_task_id=checkpoint.review_task_id,
            candidate_sha=checkpoint.source_sha,
            candidate_tree=checkpoint.source_tree,
            candidate_parent=checkpoint.source_parent,
            content_address=checkpoint.content_address(),
            artifact_digest=checkpoint.artifact_digest,
            path_manifest_digest=checkpoint.path_manifest_digest,
            dependency_graph_digest=checkpoint.dependency_graph_digest,
            proof_plan_digest=checkpoint.proof_plan_digest,
            owned_paths=checkpoint.owned_paths,
            proof_manifest=checkpoint.proof_manifest,
            claim_limits=checkpoint.claim_limits,
        )


@dataclass(frozen=True)
class IndependentReviewReceipt:
    repository: RepositoryIdentity
    visible_task_id: str
    reviewer_id: str
    producer_id: str
    candidate_sha: str
    candidate_tree: str
    artifact_digest: str
    path_manifest_digest: str
    review_packet_digest: str
    verdict: DelegatedReceiptVerdict
    readable_receipt: str
    observed_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.repository, RepositoryIdentity):
            raise InvariantError("review receipt requires a typed repository identity")
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
        _digest(self.path_manifest_digest, "review path manifest digest")
        _digest(self.review_packet_digest, "review packet digest")
        if not isinstance(self.verdict, DelegatedReceiptVerdict):
            raise InvariantError("review verdict must be ACCEPT, REJECT, or BLOCKED")
        if not isinstance(self.observed_at_ms, int) or self.observed_at_ms < 0:
            raise InvariantError("review observation time must be non-negative")
        if not isinstance(self.expires_at_ms, int) or self.expires_at_ms < self.observed_at_ms:
            raise InvariantError("review receipt expiry must not precede observation")

    def current_at(self, now_ms: int) -> bool:
        return isinstance(now_ms, int) and self.observed_at_ms <= now_ms <= self.expires_at_ms


@dataclass(frozen=True)
class FetchReceipt:
    repository: RepositoryIdentity
    local_head: str
    candidate_tree: str
    artifact_digest: str
    path_manifest_digest: str
    remote_head: str
    relationship: GitRelationship
    fetched_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.repository, RepositoryIdentity):
            raise InvariantError("fetch receipt requires a typed repository identity")
        _git_object(self.local_head, "fetch local head")
        _git_object(self.candidate_tree, "fetch candidate tree")
        _digest(self.artifact_digest, "fetch artifact digest")
        _digest(self.path_manifest_digest, "fetch path manifest digest")
        _git_object(self.remote_head, "fetch remote head")
        if not isinstance(self.relationship, GitRelationship):
            raise InvariantError("fetch relationship must be typed")
        if not isinstance(self.fetched_at_ms, int) or self.fetched_at_ms < 0:
            raise InvariantError("fetch receipt requires a non-negative observation time")
        if not isinstance(self.expires_at_ms, int) or self.expires_at_ms < self.fetched_at_ms:
            raise InvariantError("fetch receipt expiry must not precede observation")

    def current_at(self, now_ms: int) -> bool:
        return isinstance(now_ms, int) and self.fetched_at_ms <= now_ms <= self.expires_at_ms


@dataclass(frozen=True)
class BoundPolicyReceipt:
    repository: RepositoryIdentity
    purpose: ReceiptPurpose
    operation: AutomationAction
    candidate_sha: str
    candidate_tree: str
    authority: ReceiptAuthority
    receipt_ref: str
    observed_at_ms: int
    expires_at_ms: int
    artifact_digest: str
    path_manifest_digest: str
    method: str = ""
    remote_head: str = ""
    subject_artifact_digest: str = ""
    subject_path: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.repository, RepositoryIdentity):
            raise InvariantError("policy receipt requires a typed repository identity")
        if not isinstance(self.purpose, ReceiptPurpose) or not isinstance(self.operation, AutomationAction):
            raise InvariantError("policy receipt requires typed purpose and operation")
        if not isinstance(self.authority, ReceiptAuthority):
            raise InvariantError("policy receipt requires typed authority")
        _git_object(self.candidate_sha, "policy candidate SHA")
        _git_object(self.candidate_tree, "policy candidate tree")
        _token(self.receipt_ref, "policy receipt reference")
        if not isinstance(self.observed_at_ms, int) or self.observed_at_ms < 0:
            raise InvariantError("policy receipt requires a non-negative observation time")
        if not isinstance(self.expires_at_ms, int) or self.expires_at_ms < self.observed_at_ms:
            raise InvariantError("policy receipt expiry must not precede observation")
        if self.method:
            _token(self.method, "policy method")
        if self.remote_head:
            _git_object(self.remote_head, "policy remote head")
        _digest(self.artifact_digest, "policy candidate artifact digest")
        _digest(self.path_manifest_digest, "policy path manifest digest")
        if self.subject_artifact_digest:
            _digest(self.subject_artifact_digest, "policy subject artifact digest")
        if self.subject_path:
            _token(self.subject_path, "policy subject path")

    def current_at(self, now_ms: int) -> bool:
        return isinstance(now_ms, int) and self.observed_at_ms <= now_ms <= self.expires_at_ms


@dataclass(frozen=True)
class HostArchiveCustodyReceipt:
    repository: RepositoryIdentity
    task_id: str
    candidate_sha: str
    candidate_tree: str
    artifact_digest: str
    path_manifest_digest: str
    target_state_digest: str
    receipt_ref: str
    authority: ReceiptAuthority
    observed_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.repository, RepositoryIdentity):
            raise InvariantError("archive custody receipt requires a typed repository identity")
        _token(self.task_id, "host archive task id")
        _git_object(self.candidate_sha, "host archive candidate SHA")
        _git_object(self.candidate_tree, "host archive candidate tree")
        _digest(self.artifact_digest, "host archive artifact digest")
        _digest(self.path_manifest_digest, "host archive path manifest digest")
        _digest(self.target_state_digest, "host archive target state")
        _token(self.receipt_ref, "host archive receipt reference")
        if self.authority is not ReceiptAuthority.HOST:
            raise InvariantError("archive custody receipt must be host-owned")
        if not isinstance(self.observed_at_ms, int) or self.observed_at_ms < 0:
            raise InvariantError("archive custody observation time must be non-negative")
        if not isinstance(self.expires_at_ms, int) or self.expires_at_ms < self.observed_at_ms:
            raise InvariantError("archive custody expiry must not precede observation")

    def current_at(self, now_ms: int) -> bool:
        return isinstance(now_ms, int) and self.observed_at_ms <= now_ms <= self.expires_at_ms


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
    host_custody_receipt: HostArchiveCustodyReceipt | None = None

    def __post_init__(self) -> None:
        _token(self.task_id, "archive target task id")
        _token(self.task_state, "archive target task state")
        values = self.__dict__
        for key, value in values.items():
            if key not in {"task_id", "task_state", "target_state_digest", "host_custody_receipt"} and not isinstance(value, bool):
                raise InvariantError(f"archive fact {key} must be true or false")
        if self.target_state_digest:
            _digest(self.target_state_digest, "archive target state")
        if self.host_custody_receipt is not None and not isinstance(self.host_custody_receipt, HostArchiveCustodyReceipt):
            raise InvariantError("archive custody receipt must be typed")


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


def _policy_receipt_blocker(
    receipt: BoundPolicyReceipt | None,
    checkpoint: StableCheckpoint,
    *,
    purpose: ReceiptPurpose,
    operation: AutomationAction,
    authorities: frozenset[ReceiptAuthority],
    now_ms: int,
    remote_head: str = "",
    require_method: bool = False,
    require_subject: bool = False,
) -> str:
    if receipt is None:
        return f"{purpose.value} receipt required"
    if receipt.repository != checkpoint.repository:
        return f"{purpose.value} receipt targets a different repository, root, branch, or remote"
    if (receipt.candidate_sha, receipt.candidate_tree) != (checkpoint.source_sha, checkpoint.source_tree):
        return f"{purpose.value} receipt targets a different candidate"
    if (receipt.artifact_digest, receipt.path_manifest_digest) != (checkpoint.artifact_digest, checkpoint.path_manifest_digest):
        return f"{purpose.value} receipt targets a different artifact or path manifest"
    if receipt.purpose is not purpose or receipt.operation is not operation:
        return f"{purpose.value} receipt has the wrong purpose or operation"
    if receipt.authority not in authorities:
        return f"{purpose.value} receipt lacks required authority"
    if not receipt.current_at(now_ms):
        return f"{purpose.value} receipt is stale or not yet valid"
    if remote_head and receipt.remote_head != remote_head:
        return f"{purpose.value} receipt targets a different remote head"
    if require_method and (not receipt.method or receipt.method not in checkpoint.repository.release_methods):
        return f"{purpose.value} receipt lacks a repository-declared release method"
    if require_subject and (not receipt.subject_artifact_digest or not receipt.subject_path):
        return f"{purpose.value} receipt lacks exact subject artifact/path binding"
    return ""


def commit_decision(
    mode: AutomationMode | str, checkpoint: StableCheckpoint, *, attributable_paths: tuple[str, ...]
) -> AutomationDecision:
    """Allow an exact owned commit only when the whole dirty set is attributable."""
    mode = normalize_automation_mode(mode)
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
    mode: AutomationMode | str,
    checkpoint: StableCheckpoint,
    receipt: IndependentReviewReceipt | None,
    *,
    now_ms: int,
) -> AutomationDecision:
    """Require one readable exact-candidate independent verdict before integration."""
    mode = normalize_automation_mode(mode)
    if mode is AutomationMode.MANUAL:
        return _manual()
    if receipt is None:
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="independent review receipt required")
    try:
        packet = checkpoint.review_packet()
    except InvariantError as error:
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker=str(error))
    if receipt.visible_task_id != checkpoint.review_task_id:
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="review receipt targets a different visible review task")
    if receipt.producer_id != checkpoint.task_id:
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="review receipt targets a different producer task")
    if receipt.repository != checkpoint.repository:
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="review receipt targets a different repository, root, branch, or remote")
    if (receipt.candidate_sha, receipt.candidate_tree, receipt.artifact_digest, receipt.path_manifest_digest) != (checkpoint.source_sha, checkpoint.source_tree, checkpoint.artifact_digest, checkpoint.path_manifest_digest):
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="review receipt targets a different candidate")
    if receipt.review_packet_digest != packet.packet_digest:
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="review receipt targets a different immutable review packet")
    if not receipt.current_at(now_ms):
        return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.BLOCKED, blocker="review receipt is stale or not yet valid")
    if receipt.verdict is not DelegatedReceiptVerdict.ACCEPT:
        return AutomationDecision(
            AutomationAction.REVIEW,
            AutomationStatus.BLOCKED,
            blocker=f"independent review returned {receipt.verdict.value}",
            claim_limit="REJECT, BLOCKED, silence, activity, timeout, and in-progress state never advance acceptance.",
        )
    return AutomationDecision(AutomationAction.REVIEW, AutomationStatus.READY, method="readable_independent_accept")


def git_advance_decision(
    mode: AutomationMode | str,
    checkpoint: StableCheckpoint,
    review: IndependentReviewReceipt | None,
    fetch: FetchReceipt | None,
    *,
    now_ms: int,
    remote_compatibility_receipt: BoundPolicyReceipt | None = None,
    push_policy_receipt: BoundPolicyReceipt | None = None,
) -> AutomationDecision:
    """Plan a history-preserving integrate/push action after review and fetch."""
    accepted = review_decision(mode, checkpoint, review, now_ms=now_ms)
    if accepted.status is not AutomationStatus.READY:
        return accepted
    if fetch is None:
        return AutomationDecision(AutomationAction.INTEGRATE, AutomationStatus.BLOCKED, blocker="fresh fetch receipt required before integration or push")
    if fetch.repository != checkpoint.repository:
        return AutomationDecision(AutomationAction.INTEGRATE, AutomationStatus.BLOCKED, blocker="fetch receipt targets a different repository, root, branch, or remote")
    if (fetch.local_head, fetch.candidate_tree, fetch.artifact_digest, fetch.path_manifest_digest) != (
        checkpoint.source_sha,
        checkpoint.source_tree,
        checkpoint.artifact_digest,
        checkpoint.path_manifest_digest,
    ):
        return AutomationDecision(AutomationAction.INTEGRATE, AutomationStatus.BLOCKED, blocker="fetch receipt is not bound to the accepted local candidate")
    if not fetch.current_at(now_ms):
        return AutomationDecision(AutomationAction.INTEGRATE, AutomationStatus.BLOCKED, blocker="fetch receipt is stale or not yet valid")
    if fetch.relationship is GitRelationship.DIVERGED:
        blocker = _policy_receipt_blocker(
            remote_compatibility_receipt,
            checkpoint,
            purpose=ReceiptPurpose.REMOTE_COMPATIBILITY,
            operation=AutomationAction.INTEGRATE,
            authorities=frozenset({ReceiptAuthority.INDEPENDENT_REVIEW}),
            now_ms=now_ms,
            remote_head=fetch.remote_head,
        )
        if blocker:
            return AutomationDecision(
                AutomationAction.INTEGRATE,
                AutomationStatus.BLOCKED,
                blocker=blocker,
                claim_limit="Never force-push, rebase, or reset user or remote work.",
            )
    method = "merge_reviewed_remote_history" if fetch.relationship is GitRelationship.DIVERGED else "fast_forward_preserving_history"
    if push_policy_receipt is not None:
        blocker = _policy_receipt_blocker(
            push_policy_receipt,
            checkpoint,
            purpose=ReceiptPurpose.PUSH_POLICY,
            operation=AutomationAction.PUSH,
            authorities=frozenset({ReceiptAuthority.HOST, ReceiptAuthority.REPOSITORY_POLICY}),
            now_ms=now_ms,
            remote_head=fetch.remote_head,
        )
        if blocker:
            return AutomationDecision(AutomationAction.PUSH, AutomationStatus.BLOCKED, blocker=blocker)
    action = AutomationAction.PUSH if push_policy_receipt is not None else AutomationAction.INTEGRATE
    return AutomationDecision(
        action,
        AutomationStatus.READY,
        method=method,
        claim_limit="Only non-destructive fast-forward or reviewed compatible merge is eligible; force-push, rebase, and reset are never emitted.",
    )


def release_decision(
    mode: AutomationMode | str,
    checkpoint: StableCheckpoint,
    *,
    now_ms: int,
    release_policy: BoundPolicyReceipt | None,
    source_gate: BoundPolicyReceipt | None,
    package_gate: BoundPolicyReceipt | None,
    rollback_receipt: BoundPolicyReceipt | None,
) -> AutomationDecision:
    """Permit only the repository-defined release path with source/package gates."""
    mode = normalize_automation_mode(mode)
    if mode is AutomationMode.MANUAL:
        return _manual()
    checks = (
        (release_policy, ReceiptPurpose.RELEASE_POLICY, frozenset({ReceiptAuthority.HOST, ReceiptAuthority.REPOSITORY_POLICY}), True, False),
        (source_gate, ReceiptPurpose.SOURCE_GATE, frozenset({ReceiptAuthority.INDEPENDENT_REVIEW}), False, True),
        (package_gate, ReceiptPurpose.PACKAGE_GATE, frozenset({ReceiptAuthority.INDEPENDENT_REVIEW, ReceiptAuthority.REPOSITORY_POLICY}), False, True),
        (rollback_receipt, ReceiptPurpose.ROLLBACK, frozenset({ReceiptAuthority.HOST, ReceiptAuthority.REPOSITORY_POLICY}), False, True),
    )
    for receipt, purpose, authorities, require_method, require_subject in checks:
        blocker = _policy_receipt_blocker(
            receipt,
            checkpoint,
            purpose=purpose,
            operation=AutomationAction.RELEASE,
            authorities=authorities,
            now_ms=now_ms,
            require_method=require_method,
            require_subject=require_subject,
        )
        if blocker:
            return AutomationDecision(AutomationAction.RELEASE, AutomationStatus.BLOCKED, blocker=blocker)
    assert release_policy is not None
    return AutomationDecision(
        AutomationAction.RELEASE,
        AutomationStatus.READY,
        method=release_policy.method,
        claim_limit="Release eligibility does not promote local installation to provider or production deployment.",
    )


def archive_request_decision(
    mode: AutomationMode | str, checkpoint: StableCheckpoint, facts: ArchiveFacts, *, now_ms: int
) -> AutomationDecision:
    """Emit a host-consumed request; never archive or claim host authority here."""
    mode = normalize_automation_mode(mode)
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
    custody = facts.host_custody_receipt
    if not facts.target_state_digest or custody is None:
        return AutomationDecision(
            AutomationAction.ARCHIVE_REQUEST,
            AutomationStatus.BLOCKED,
            blocker="current host target/custody receipt is unavailable",
            claim_limit="archive_unverified: plugin runtime cannot mint host authority.",
        )
    if (
        custody.repository != checkpoint.repository
        or custody.candidate_sha != checkpoint.source_sha
        or custody.candidate_tree != checkpoint.source_tree
        or custody.artifact_digest != checkpoint.artifact_digest
        or custody.path_manifest_digest != checkpoint.path_manifest_digest
        or custody.task_id != facts.task_id
        or custody.target_state_digest != facts.target_state_digest
        or not custody.current_at(now_ms)
    ):
        return AutomationDecision(
            AutomationAction.ARCHIVE_REQUEST,
            AutomationStatus.BLOCKED,
            blocker="host custody receipt is stale or targets different task state",
            claim_limit="archive_unverified: plugin runtime cannot mint host authority.",
        )
    return AutomationDecision(
        AutomationAction.ARCHIVE_REQUEST,
        AutomationStatus.REQUESTED_UNVERIFIED,
        target_id=facts.task_id,
        target_state_digest=facts.target_state_digest,
        host_custody_receipt_ref=custody.receipt_ref,
        method="host_consume_archive_request",
        claim_limit="archive_unverified: only the host may independently validate current custody, consume the persisted preference, archive the exact task, and return confirmation.",
    )
