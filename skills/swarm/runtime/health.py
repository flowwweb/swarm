"""Typed, advisory Auto Health requests for the active CTRL handoff."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RecoveryRequestType(StrEnum):
    DIAGNOSTICS_REVIEW = "diagnostics_review"
    CAPACITY_REVIEW = "capacity_review"
    CLEANUP_REVIEW = "cleanup_review"


class RecoveryRequestState(StrEnum):
    OPEN = "OPEN"
    CLAIMED = "CLAIMED"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    RECOVERED = "RECOVERED"


_SAFE_TEXT = re.compile(r"^[^\x00\r\n]{1,512}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or not _SAFE_TEXT.fullmatch(value):
        raise ValueError(f"{field} must be safe single-line text")
    return value.strip()


@dataclass(frozen=True)
class HealthRecoveryRequest:
    """A console advisory; it cannot create tasks or mutate host state."""

    request_id: str
    incident_key: str
    request_type: RecoveryRequestType
    severity: str
    scope: str
    evidence_digest: str
    recommended_action: str
    constraints: tuple[str, ...]
    created_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "incident_key", _text(self.incident_key, "incident_key", 256))
        try:
            request_type = RecoveryRequestType(self.request_type)
        except (TypeError, ValueError) as exc:
            raise ValueError("request_type is not supported") from exc
        object.__setattr__(self, "request_type", request_type)
        severity = _text(self.severity, "severity", 16).upper()
        if severity not in {"DEGRADED", "PRESSURED", "CRITICAL"}:
            raise ValueError("severity is not supported")
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "scope", _text(self.scope, "scope", 256))
        digest = _text(self.evidence_digest, "evidence_digest", 64).lower()
        if not _DIGEST.fullmatch(digest):
            raise ValueError("evidence_digest must be a SHA-256 hex digest")
        object.__setattr__(self, "evidence_digest", digest)
        object.__setattr__(self, "recommended_action", _text(self.recommended_action, "recommended_action"))
        constraints = tuple(_text(item, "constraint", 512) for item in self.constraints)
        if len(constraints) > 16:
            raise ValueError("too many constraints")
        object.__setattr__(self, "constraints", constraints)
        if not isinstance(self.created_at_ms, int) or self.created_at_ms <= 0:
            raise ValueError("created_at_ms must be positive")
        if not isinstance(self.expires_at_ms, int) or self.expires_at_ms <= self.created_at_ms:
            raise ValueError("expires_at_ms must be after created_at_ms")

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "incident_id": self.incident_key,
            "request_type": self.request_type.value,
            "severity": self.severity,
            "scope": self.scope,
            "evidence_digest": self.evidence_digest,
            "recommended_action": self.recommended_action,
            "constraints": list(self.constraints),
            "created_at_ms": self.created_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "claim_limit": "Advisory only; active CTRL must use normal host task APIs.",
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode("utf-8")

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "HealthRecoveryRequest":
        if not isinstance(payload, dict):
            raise ValueError("health request payload must be an object")
        return cls(
            request_id=payload.get("request_id", ""),
            incident_key=payload.get("incident_id", ""),
            request_type=payload.get("request_type", ""),
            severity=payload.get("severity", ""),
            scope=payload.get("scope", ""),
            evidence_digest=payload.get("evidence_digest", ""),
            recommended_action=payload.get("recommended_action", ""),
            constraints=tuple(payload.get("constraints", ())),
            created_at_ms=payload.get("created_at_ms", 0),
            expires_at_ms=payload.get("expires_at_ms", 0),
        )
