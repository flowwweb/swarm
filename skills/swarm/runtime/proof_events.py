"""Deterministic, bounded proof-media receipts for the SWARM console."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


MAX_MEDIA_BYTES = 64 * 1024 * 1024
MEDIA_KINDS = frozenset({"imagegen", "image", "mockup", "preview", "screenshot", "browser", "recording"})
MEDIA_SIGNATURES = (
    ("image/png", ".png", lambda head: head.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", ".jpg", lambda head: head.startswith(b"\xff\xd8\xff")),
    ("image/webp", ".webp", lambda head: head.startswith(b"RIFF") and head[8:12] == b"WEBP"),
    ("image/gif", ".gif", lambda head: head.startswith((b"GIF87a", b"GIF89a"))),
    ("video/mp4", ".mp4", lambda head: len(head) >= 12 and head[4:8] == b"ftyp"),
    ("video/webm", ".webm", lambda head: head.startswith(b"\x1aE\xdf\xa3")),
)
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")


class ProofEventError(ValueError):
    pass


def _safe_id(value: str, label: str) -> str:
    value = str(value or "").strip()
    if not SAFE_ID.fullmatch(value):
        raise ProofEventError(f"{label} must be a safe identifier")
    return value


def _safe_text(value: str, label: str, maximum: int = 512) -> str:
    value = str(value or "").strip()
    if not value or len(value) > maximum or "\x00" in value or "\r" in value or "\n" in value:
        raise ProofEventError(f"{label} must be one bounded line of text")
    return value


def media_signature(path: Path) -> tuple[str, str]:
    try:
        with path.open("rb") as stream:
            head = stream.read(32)
    except OSError as exc:
        raise ProofEventError("proof media could not be read") from exc
    for media_type, suffix, matcher in MEDIA_SIGNATURES:
        if matcher(head):
            return media_type, suffix
    raise ProofEventError("proof media signature is not allowlisted")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matching_existing_event(event_path: Path, event: dict[str, Any]) -> dict[str, Any]:
    try:
        existing = json.loads(event_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProofEventError("stored proof event is unreadable") from exc
    comparable = {key: value for key, value in event.items() if key != "created_at_ms"}
    existing_comparable = {key: value for key, value in existing.items() if key != "created_at_ms"} if isinstance(existing, dict) else {}
    if existing_comparable != comparable:
        raise ProofEventError("evidence_id already names a different proof event")
    return existing


def register_proof_event(
    codex_home: Path,
    source_path: Path,
    *,
    evidence_id: str,
    task_id: str,
    kind: str,
    caption: str,
    claim_limit: str = "Available for review; acceptance is recorded separately.",
    created_at_ms: int | None = None,
) -> dict[str, Any]:
    """Copy one immutable media artifact and append one immutable event receipt."""
    codex_home = Path(codex_home).expanduser().resolve()
    source_path = Path(source_path).expanduser().resolve(strict=True)
    evidence_id = _safe_id(evidence_id, "evidence_id")
    task_id = _safe_id(task_id, "task_id")
    kind = _safe_text(kind, "kind", 64).casefold()
    caption = _safe_text(caption, "caption")
    claim_limit = _safe_text(claim_limit, "claim_limit")
    if kind not in MEDIA_KINDS:
        raise ProofEventError("proof media kind is not allowlisted")
    if not source_path.is_file():
        raise ProofEventError("proof media must be a file")
    size_bytes = source_path.stat().st_size
    if size_bytes <= 0 or size_bytes > MAX_MEDIA_BYTES:
        raise ProofEventError("proof media exceeds the size guard")
    media_type, suffix = media_signature(source_path)
    digest = _digest(source_path)
    swarm_root = codex_home / "swarm"
    media_root = swarm_root / "proof-media"
    event_root = swarm_root / "proof-events"
    media_root.mkdir(parents=True, exist_ok=True)
    event_root.mkdir(parents=True, exist_ok=True)
    if swarm_root.resolve() != swarm_root or media_root.resolve() != media_root or event_root.resolve() != event_root:
        raise ProofEventError("proof evidence store must not use links or junctions")
    media_path = media_root / f"{digest}{suffix}"
    if media_path.exists():
        if not media_path.is_file() or media_path.stat().st_size != size_bytes or _digest(media_path) != digest:
            raise ProofEventError("stored proof media does not match its content address")
    else:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=media_root, prefix=".proof-", suffix=suffix, delete=False) as handle:
                temporary = Path(handle.name)
            shutil.copyfile(source_path, temporary)
            if temporary.stat().st_size != size_bytes or _digest(temporary) != digest:
                raise ProofEventError("proof media changed while it was copied")
            try:
                os.link(temporary, media_path)
            except FileExistsError:
                if not media_path.is_file() or media_path.stat().st_size != size_bytes or _digest(media_path) != digest:
                    raise ProofEventError("stored proof media does not match its content address")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    event = {
        "schema_version": 1,
        "source": "CtrlEvidence",
        "evidence_id": evidence_id,
        "task_id": task_id,
        "kind": kind,
        "locator": f"proof-media/{media_path.name}",
        "caption": caption,
        "claim_limit": claim_limit,
        "digest": digest,
        "size_bytes": size_bytes,
        "media_type": media_type,
        "disposition": "PENDING",
        "created_at_ms": int(created_at_ms if created_at_ms is not None else time.time() * 1000),
    }
    event_name = hashlib.sha256(evidence_id.encode("utf-8")).hexdigest() + ".json"
    event_path = event_root / event_name
    if event_path.exists():
        return _matching_existing_event(event_path, event)
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=event_root, prefix=".event-", suffix=".json", encoding="utf-8", delete=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        try:
            os.link(temporary, event_path)
        except FileExistsError:
            return _matching_existing_event(event_path, event)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return event
