"""Small, local-only usage ledger for successful ChatGPT relay consultations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
from typing import Any


SCHEMA_VERSION = 1
MAX_EVENTS = 100
USAGE_LOG_NAME = "chat-relay-usage.json"


def default_chat_relay_usage_path() -> Path:
    return Path.home() / ".agents" / "swarm" / USAGE_LOG_NAME


def estimate_tokens(text: str) -> int:
    """Return a stable rough token estimate without adding a tokenizer dependency."""

    return max(1, (len(text.encode("utf-8")) + 3) // 4)


@dataclass(frozen=True)
class ChatRelayUsageEvent:
    recorded_at: str
    task_id: str
    purpose: str
    model: str
    effort: str
    estimated_tokens_saved: int


def _empty_payload() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "events": []}


def _safe_events(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return []
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        return []
    events: list[dict[str, Any]] = []
    for raw in raw_events[-MAX_EVENTS:]:
        if not isinstance(raw, dict):
            continue
        if not all(isinstance(raw.get(key), str) for key in ("recorded_at", "task_id", "purpose", "model", "effort")):
            continue
        tokens = raw.get("estimated_tokens_saved")
        if not isinstance(tokens, int) or tokens < 0:
            continue
        events.append({
            "recorded_at": raw["recorded_at"],
            "task_id": raw["task_id"],
            "purpose": raw["purpose"],
            "model": raw["model"],
            "effort": raw["effort"],
            "estimated_tokens_saved": tokens,
        })
    return events


def read_chat_relay_usage(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else default_chat_relay_usage_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8")) if target.exists() else _empty_payload()
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = _empty_payload()
    events = _safe_events(payload)
    task_ids = {event["task_id"] for event in events if event["task_id"]}
    return {
        "schema_version": SCHEMA_VERSION,
        "consultations": len(events),
        "routed_tasks": len(task_ids),
        "estimated_tokens_saved": sum(event["estimated_tokens_saved"] for event in events),
        "events": events,
    }


class ChatRelayUsageLedger:
    """Best-effort atomic persistence; telemetry must never block a relay."""

    def __init__(self, path: str | Path | None = None, *, max_events: int = MAX_EVENTS) -> None:
        self.path = Path(path) if path is not None else default_chat_relay_usage_path()
        self.max_events = max(1, min(int(max_events), MAX_EVENTS))

    def record(
        self,
        *,
        task_id: str,
        purpose: str,
        model: str,
        effort: str,
        prompt: str,
        response: str,
    ) -> None:
        event = ChatRelayUsageEvent(
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            task_id=task_id.strip(),
            purpose=purpose,
            model=model,
            effort=effort,
            estimated_tokens_saved=estimate_tokens(prompt) + estimate_tokens(response),
        )
        existing = read_chat_relay_usage(self.path)
        events = [*existing["events"], asdict(event)][-self.max_events:]
        payload = {"schema_version": SCHEMA_VERSION, "events": events}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                temporary = handle.name
            Path(temporary).replace(self.path)
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
